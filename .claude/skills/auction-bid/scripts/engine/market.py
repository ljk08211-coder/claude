"""시세 추정: 실거래 비교사례 → 시점·층 보정 → 가중 중앙값 → KB·호가 교차검증."""
import datetime as dt
import statistics
from collections import defaultdict

from .molit import exact_name, norm_name


def _date(s):
    return dt.date.fromisoformat(s)


def _months_between(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def apt_matcher(prop, rows):
    """같은 단지 판정. 단지 고유번호(apt_seq) → 정확한 단지명 → (그래도 없으면) 부분 일치 순서."""
    seq, dong = prop.get("apt_seq"), prop.get("dong", "")
    if seq:
        return lambda t: t.get("apt_seq") == seq
    exact, loose = exact_name(prop.get("apt_name", "")), norm_name(prop.get("apt_name", ""))
    in_dong = lambda t: not dong or t["dong"] == dong
    if exact and any(exact_name(t["apt_name"]) == exact and in_dong(t) for t in rows):
        return lambda t: exact_name(t["apt_name"]) == exact and in_dong(t)
    return lambda t: bool(loose) and (loose in norm_name(t["apt_name"]) or norm_name(t["apt_name"]) in loose) and in_dong(t)


def regional_index(trades, today):
    """시군구 시세 지수 {YYYY-MM: 지수}, 마지막 완성월 = 1.0.

    같은 단지·같은 평형끼리만 비교한다(각 거래가 ÷ 그 단지·평형 중앙값의 월별 중앙값).
    ㎡당 중앙값으로 만들면 그 달에 어떤 단지가 팔렸는지에 따라 ±10% 넘게 출렁인다(부산진구에서 확인).
    """
    # 실거래 신고기한이 30일이라 최근 두 달은 아직 덜 들어온 상태 → 지수에서 뺀다 (예전엔 가짜 하락으로 보였다)
    cutoff = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1).isoformat()[:7]
    groups = defaultdict(list)
    for t in trades:
        if t["date"][:7] < cutoff:
            groups[(t.get("apt_seq") or (t["apt_name"], t["dong"]), round(t["area"]))].append(t)
    by_month = defaultdict(list)
    for rows in groups.values():
        if len(rows) < 4:
            continue
        med = statistics.median(r["price"] for r in rows)
        for r in rows:
            by_month[r["date"][:7]].append(r["price"] / med)
    months = sorted(m for m, v in by_month.items() if len(v) >= 10)
    if len(months) < 3:
        return {}
    med = {m: statistics.median(by_month[m]) for m in months}
    smooth = {}
    for i, m in enumerate(months):
        window = [med[x] for x in months[max(0, i - 1): i + 2]]
        smooth[m] = sum(window) / len(window)
    latest = smooth[months[-1]]
    return {m: v / latest for m, v in smooth.items()}


def time_factor(index, date_str):
    if not index:
        return 1.0
    key = date_str[:7]
    if key in index:
        return 1.0 / index[key]
    if key > max(index):  # 지수 기준월 이후(신고 진행 중인 달)는 보정하지 않는다
        return 1.0
    older = [m for m in index if m <= key]
    return 1.0 / index[max(older)] if older else 1.0 / index[min(index)]


def floor_adj(floor, top, cfg):
    fa = cfg["market"]["floor_adjust"]
    if top:
        return fa.get("top", 0.0)
    return fa.get(str(floor), 0.0) if floor is not None else 0.0


def _weighted_median(pairs):
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= total / 2:
            return v
    return pairs[-1][0]


def _recency_weight(months_ago):
    # 해운대구 실거래 백테스트에서 최근 거래를 강하게 반영할 때 오차가 가장 작았다
    return 1.0 if months_ago <= 1 else 0.6 if months_ago <= 3 else 0.3 if months_ago <= 6 else 0.15


def estimate(case, trades, cfg, today=None):
    today = today or dt.date.today()
    mc = cfg["market"]
    prop = case["property"]
    area = float(prop["exclusive_area"])
    target_dong = prop.get("dong", "")
    target_floor_adj = floor_adj(prop.get("floor"), prop.get("top_floor"), cfg)
    by = prop.get("build_year")

    recent = [t for t in trades if _months_between(_date(t["date"]), today) <= mc["comp_months"]]
    index = regional_index(trades, today)

    same_apt = apt_matcher(prop, trades)

    tiers = [
        ("같은 단지·같은 평형", 1.0, lambda t: same_apt(t) and abs(t["area"] - area) <= mc["same_type_area_tol"]),
        ("같은 단지·유사 평형", 0.8, lambda t: same_apt(t) and abs(t["area"] - area) <= area * mc["area_tolerance"]
            and abs(t["area"] - area) > mc["same_type_area_tol"]),
        ("같은 동네 유사 단지", 0.5, lambda t: not same_apt(t) and t["dong"] == target_dong
            and abs(t["area"] - area) <= area * 0.15
            and (by is None or t["build_year"] is None or abs(t["build_year"] - by) <= mc["build_year_tolerance"])),
    ]

    comps = []
    for label, tier_w, pred in tiers:
        for t in recent:
            if not pred(t):
                continue
            months_ago = _months_between(_date(t["date"]), today)
            tf = time_factor(index, t["date"])
            fa = floor_adj(t["floor"], False, cfg)
            per_m2 = t["price"] / t["area"] * tf / (1 + fa) * (1 + target_floor_adj)
            comps.append({**t, "tier": label, "adjusted": round(per_m2 * area),
                          "weight": tier_w * _recency_weight(months_ago), "time_factor": round(tf, 4)})
        if len(comps) >= mc["min_comps"]:
            break

    result = {"comps": [], "index_months": len(index), "model_value": None, "value": None,
              "confidence": "없음", "notes": []}
    if comps:
        med = statistics.median(c["adjusted"] for c in comps)
        kept = [c for c in comps if abs(c["adjusted"] / med - 1) <= mc["outlier_band"]]
        if not kept:  # 사례가 적고 서로 멀면 전부 걸러질 수 있다 → 걸러내지 않고 신뢰도로 경고
            kept = comps
            result["notes"].append("비교사례 가격이 서로 크게 달라 이상거래를 걸러내지 못함")
        dropped = len(comps) - len(kept)
        if dropped:
            result["notes"].append(f"이상거래 {dropped}건 제외 (중앙값 ±{mc['outlier_band']:.0%} 밖)")
        result["model_value"] = round(_weighted_median([(c["adjusted"], c["weight"]) for c in kept]), -5)
        result["comps"] = sorted(kept, key=lambda c: c["date"], reverse=True)

    survey = case.get("site_survey") or {}
    checks = {}
    if result["model_value"]:
        checks["실거래 추정"] = result["model_value"]
    if survey.get("kb_price"):
        checks["KB시세"] = int(survey["kb_price"])
    asks = [int(a) for a in survey.get("asking_prices") or [] if a]
    if asks:
        checks["최저 호가"] = min(asks)
    result["checks"] = checks

    override = (case.get("overrides") or {}).get("market_value")
    if override:
        result.update(value=int(override), confidence="직접 입력")
        result["notes"].append("시세를 직접 입력한 값으로 사용")
        return result
    if not checks:
        result["notes"].append("비교 사례가 없다. 실거래 CSV 를 넣거나 overrides.market_value 로 시세를 직접 입력해야 한다.")
        return result

    lo, hi = min(checks.values()), max(checks.values())
    n = len(result["comps"])
    if hi / lo - 1 > mc["low_confidence_spread"]:
        result.update(value=lo, confidence="낮음")
        result["notes"].append(f"실거래·KB·호가 차이 {hi / lo - 1:.0%} → 가장 낮은 값 사용")
    elif result["model_value"]:
        result["value"] = result["model_value"]
        same_complex = sum(c["tier"] != "같은 동네 유사 단지" for c in result["comps"])
        if not same_complex:
            result["confidence"] = "낮음"
            result["notes"].append("같은 단지 거래가 없어 인근 유사 단지로만 추정")
        else:
            result["confidence"] = "높음" if same_complex >= 5 else "보통" if same_complex >= 3 else "낮음"
    else:
        result.update(value=lo, confidence="낮음")
        result["notes"].append("실거래 비교사례 없이 KB·호가만으로 추정")
    return result


def rent_estimate(case, rents, market_value, cfg, today=None):
    """월세 시세를 '보증금 = 시세의 10%' 기준으로 환산한 중앙값."""
    today = today or dt.date.today()
    override = case.get("overrides") or {}
    if override.get("monthly_rent"):
        return {"deposit": int(override.get("rent_deposit") or 0), "monthly_rent": int(override["monthly_rent"]),
                "count": 0, "source": "직접 입력"}
    if not rents or not market_value:
        return None
    prop = case["property"]
    area = float(prop["exclusive_area"])
    dong = prop.get("dong", "")
    conv = cfg["market"]["rent_conversion_rate"]
    base_deposit = round(market_value * 0.1, -6)
    recent = [r for r in rents if r["monthly_rent"] > 0
              and _months_between(_date(r["date"]), today) <= 12
              and abs(r["area"] - area) <= area * 0.1]
    same = apt_matcher(prop, rents)
    for label, pick in (("같은 단지", same),
                        ("같은 동네", lambda r: r["dong"] == dong)):
        rows = [r for r in recent if pick(r)]
        if len(rows) >= 3:
            adj = [r["monthly_rent"] + (r["deposit"] - base_deposit) * conv / 12 for r in rows]
            return {"deposit": int(base_deposit), "monthly_rent": int(round(statistics.median(adj), -4)),
                    "count": len(rows), "source": label}
    return None
