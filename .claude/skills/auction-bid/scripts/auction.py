#!/usr/bin/env python3
"""경매 적정 입찰가 추천.

사용법:
  python auction.py check
  python auction.py init <사건번호> [--out auction-cases]
  python auction.py comps <case.json> [--months 12] [--csv 실거래.csv ...]
  python auction.py analyze <case.json> [--config 내설정.toml]   (기본: auction-cases/config.toml 이 있으면 덮어씀)
  python auction.py record <case.json> --winning-bid 원 [--bidders N] [--my-bid 원]
  python auction.py record-comp --lawd 26350 --market-value 원 --winning-bid 원 [--sale-date YYYY-MM-DD] ...

사건 폴더(auction-cases/<사건번호>/)에 case.json · comps.json · report.html · result.json 이 모인다.
낙찰결과는 auction-cases/_results.csv 에 쌓여 낙찰확률 모델이 된다.
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import config, market, molit, recommend, regions, report, winprob  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATE = SKILL_DIR / "templates" / "case_template.json"


def _key():
    return os.environ.get("DATA_GO_KR_KEY", "").strip()


def _results_path(case_path):
    return Path(case_path).resolve().parent.parent / "_results.csv"


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def cmd_check(_a):
    print(f"python: {sys.version.split()[0]}")
    print("DATA_GO_KR_KEY: " + ("설정됨" if _key() else "없음 — 실거래가 자동 수집 불가 (CSV 나 시세 직접 입력으로 대체 가능)"))
    print(f"설정 파일: {config.DEFAULT_PATH}")
    return 0


def cmd_init(a):
    folder = Path(a.out) / a.case_no
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / "case.json"
    if dest.exists():
        print(f"이미 있음: {dest}")
        return 0
    data = _load(TEMPLATE)
    data["case_no"] = a.case_no
    _save(dest, data)
    print(f"만듦: {dest}")
    return 0


def _ensure_lawd(case):
    prop = case["property"]
    if not prop.get("lawd_cd"):
        prop["lawd_cd"] = regions.resolve(prop.get("region", ""))
    return prop["lawd_cd"]


def cmd_comps(a):
    case = _load(a.case)
    lawd = _ensure_lawd(case)
    _save(a.case, case)
    out = Path(a.case).parent / "comps.json"
    data = {"lawd_cd": lawd, "region": regions.name_of(lawd), "fetched_at": dt.date.today().isoformat(),
            "trades": [], "rents": [], "sources": []}
    for path in a.csv or []:
        rows = molit.load_csv(path)
        data["trades"] += rows
        data["sources"].append(f"CSV {Path(path).name} ({len(rows)}건)")
    if _key() and not a.no_api:
        print(f"실거래가 API 조회: {data['region']} 최근 {a.months}개월")
        try:
            data["trades"] += molit.fetch(lawd, a.months, _key(), "trade")
            data["sources"].append("국토교통부 매매 실거래가 API")
            data["rents"] += molit.fetch(lawd, 12, _key(), "rent")
            data["sources"].append("국토교통부 전월세 API")
        except Exception as e:  # 네트워크·키 오류여도 CSV/직접입력으로 계속 갈 수 있게
            print(f"API_ERROR: {e}")
    elif not a.csv:
        print("NO_DATA_SOURCE: DATA_GO_KR_KEY 도 CSV 도 없다. 키를 설정하거나 --csv 로 실거래 파일을 넣어줘.")
        return 2
    _save(out, data)
    print(f"저장: {out} (매매 {len(data['trades'])}건, 전월세 {len(data['rents'])}건)")
    return 0


def cmd_analyze(a):
    user_cfg = a.config or Path(a.case).resolve().parent.parent / "config.toml"
    cfg = config.load(user_cfg)
    case = _load(a.case)
    _ensure_lawd(case)
    comps_path = Path(a.case).parent / "comps.json"
    comps = _load(comps_path) if comps_path.exists() else {"trades": [], "rents": []}

    mv = market.estimate(case, comps["trades"], cfg)
    if not mv["value"]:
        print("NO_MARKET_VALUE: " + " / ".join(mv["notes"]))
        return 2
    rent = market.rent_estimate(case, comps.get("rents", []), mv["value"], cfg)
    results = winprob.load_results(_results_path(a.case))
    rec = recommend.run(case, cfg, mv["value"], rent, results)

    folder = Path(a.case).parent
    (folder / "report.html").write_text(report.html_report(case, mv, rec, cfg), encoding="utf-8")
    summary = {"case_no": case.get("case_no"), "analyzed_at": dt.datetime.now().isoformat(timespec="seconds"),
               "market_value": mv["value"], "confidence": mv["confidence"], "verdict": rec["verdict"],
               "max_bid": rec["max_bid"], "min_price": rec["min_price"], "picks": rec["picks"],
               "pass_reasons": rec["pass_reasons"], "red_flags": rec["rights"]["red_flags"],
               "yellow_flags": rec["rights"]["yellow_flags"], "next_round": rec["next_round"],
               "scenarios": [{"hold_years": s["hold_years"], "max_bid": s["max_bid"]} for s in rec["scenarios"]],
               "rent_max_bid": rec["rental"]["max_bid"]}
    _save(folder / "result.json", summary)
    print(report.markdown(case, mv, rec))
    print(f"\n리포트: {folder / 'report.html'}")
    return 0


def cmd_record(a):
    case = _load(a.case)
    res_path = Path(a.case).parent / "result.json"
    mv = _load(res_path)["market_value"] if res_path.exists() else a.market_value
    if not mv:
        print("시세가 없다. analyze 를 먼저 돌리거나 --market-value 를 넣어줘.")
        return 2
    auc = case["auction"]
    row = {"recorded_at": dt.date.today().isoformat(), "sale_date": auc.get("sale_date", ""),
           "case_no": case.get("case_no", ""), "lawd_cd": _ensure_lawd(case),
           "property_type": case["property"].get("type", "아파트"), "market_value": mv,
           "appraisal": auc.get("appraisal", ""), "min_price": auc.get("min_price", ""),
           "winning_bid": a.winning_bid, "bidders": a.bidders or "", "failed_count": auc.get("failed_count", ""),
           "my_bid": a.my_bid or "", "source": "내 사건"}
    winprob.append_result(_results_path(a.case), row)
    print(f"기록: 낙찰가 {a.winning_bid:,} / 시세 {int(mv):,} = {a.winning_bid / mv:.1%}")
    return 0


def cmd_record_comp(a):
    lawd = regions.resolve(a.lawd)
    row = {"recorded_at": dt.date.today().isoformat(), "sale_date": a.sale_date or dt.date.today().isoformat(),
           "case_no": a.case_no or "", "lawd_cd": lawd, "property_type": a.type, "market_value": a.market_value,
           "appraisal": a.appraisal or "", "min_price": a.min_price or "", "winning_bid": a.winning_bid,
           "bidders": a.bidders or "", "failed_count": a.failed_count or "", "source": "참고 사례"}
    path = Path(a.out) / "_results.csv"
    winprob.append_result(path, row)
    print(f"기록: {regions.name_of(lawd)} 낙찰가율(시세 대비) {a.winning_bid / a.market_value:.1%} → {path}")
    return 0


def main():
    p = argparse.ArgumentParser(description="경매 적정 입찰가 추천")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    s = sub.add_parser("init")
    s.add_argument("case_no")
    s.add_argument("--out", default="auction-cases")
    s = sub.add_parser("comps")
    s.add_argument("case")
    s.add_argument("--months", type=int, default=12)
    s.add_argument("--csv", nargs="*")
    s.add_argument("--no-api", action="store_true")
    s = sub.add_parser("analyze")
    s.add_argument("case")
    s.add_argument("--config")
    s = sub.add_parser("record")
    s.add_argument("case")
    s.add_argument("--winning-bid", type=int, required=True)
    s.add_argument("--bidders", type=int)
    s.add_argument("--my-bid", type=int)
    s.add_argument("--market-value", type=int)
    s = sub.add_parser("record-comp")
    s.add_argument("--lawd", required=True, help="'부산 해운대구' 또는 26350")
    s.add_argument("--market-value", type=int, required=True)
    s.add_argument("--winning-bid", type=int, required=True)
    s.add_argument("--sale-date")
    s.add_argument("--case-no")
    s.add_argument("--appraisal", type=int)
    s.add_argument("--min-price", type=int)
    s.add_argument("--bidders", type=int)
    s.add_argument("--failed-count", type=int)
    s.add_argument("--type", default="아파트")
    s.add_argument("--out", default="auction-cases")
    a = p.parse_args()
    handlers = {"check": cmd_check, "init": cmd_init, "comps": cmd_comps, "analyze": cmd_analyze,
                "record": cmd_record, "record-comp": cmd_record_comp}
    try:
        return handlers[a.cmd](a)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
