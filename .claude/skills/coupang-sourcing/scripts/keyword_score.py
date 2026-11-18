#!/usr/bin/env python3
"""쿠팡 검색 결과(JSON)로 키워드 경쟁강도 점수를 계산해 마크다운으로 출력한다.

사용법:
    python3 keyword_score.py search.json [--track season|evergreen|bluelake] [--keyword 키워드]

입력: Apify 쿠팡 검색 Actor 결과(리스트 JSON, 또는 JSON Lines).
여러 Actor의 필드명 변형을 받아준다(ratingCount/reviewCount, rocketDelivery/isRocket 등).
여러 키워드가 섞여 있으면 keyword 필드로 나눠 각각 점수를 낸다.
"""
import argparse
import json
import statistics
import sys
from collections import defaultdict

FIELD_ALIASES = {
    "name": ["name", "title", "productName"],
    "price": ["price", "salePrice", "finalPrice", "currentPrice"],
    "reviews": ["ratingCount", "reviewCount", "reviewsCount", "reviews", "numberOfReviews"],
    "rating": ["ratingAverage", "rating", "stars", "averageRating"],
    "rocket": ["rocketDelivery", "isRocket", "rocket", "isRocketDelivery"],
    "sponsored": ["sponsored", "isAd", "isSponsored", "ad"],
    "rank": ["searchRank", "rank", "position"],
    "url": ["url", "productUrl", "link"],
    "keyword": ["keyword", "searchTerm", "query"],
}

# 트랙별 가중치(합 100). 시즌은 빨리 상위에 붙어야 해서 진입장벽 비중을 키우고,
# 사계절은 독점·광고 경쟁, 저경쟁 트랙은 불만(평점)·신규 진입 증거 비중을 키운다.
WEIGHTS = {
    "season":    {"barrier": 30, "concentration": 10, "rocket": 15, "ads": 10, "rating_gap": 10, "price_room": 10, "newcomers": 15},
    "evergreen": {"barrier": 20, "concentration": 20, "rocket": 15, "ads": 15, "rating_gap": 10, "price_room": 10, "newcomers": 10},
    "bluelake":  {"barrier": 25, "concentration": 10, "rocket": 10, "ads": 10, "rating_gap": 20, "price_room": 5,  "newcomers": 20},
}

LABELS = {
    "barrier": "진입장벽(상위10 리뷰 중앙값)",
    "concentration": "독점도(1위 리뷰 비중)",
    "rocket": "로켓배송 장악도",
    "ads": "광고 경쟁",
    "rating_gap": "불만 여지(평균 평점)",
    "price_room": "가격 경쟁 여유(가격 분산)",
    "newcomers": "신규 진입 증거",
}


# 상품명 기반 1차 수입검사·인증 자동 표시. 구성품(토치·충전 여부)은 상세를 보고 사람이 확정한다.
INSPECTION_RULES = [
    ("🧪", ["잔", "컵", "글라스", "텀블러", "쉐이커", "셰이커", "지거", "바스푼", "머들러", "디캔터",
            "병", "마개", "푸어러", "스토퍼", "얼음", "아이스", "몰드", "빨대", "스트로", "도마", "쟁반",
            "칵테일", "와인", "위스키", "하이볼", "소주", "맥주", "식기", "주방", "보틀", "피처", "칠러"]),
    ("⚡", ["전기", "전동", "충전", "USB", "usb", "자동", "배터리", "LED", "led", "전자"]),
    ("📡", ["블루투스", "무선", "bluetooth"]),
    ("🔥", ["토치", "부탄", "가스", "라이터"]),
    ("👶", ["유아", "아기", "어린이", "키즈"]),
]


def inspection_flags(text):
    flags = [tag for tag, words in INSPECTION_RULES if any(w in text for w in words)]
    return " ".join(flags) if flags else "—"


def pick(item, key):
    for alias in FIELD_ALIASES[key]:
        if alias in item and item[alias] is not None:
            return item[alias]
    return None


def to_num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = "".join(ch for ch in str(v) if ch.isdigit() or ch == ".")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def to_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "y")
    return bool(v)


def load(path):
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return []
    if text[0] == "[":
        return json.loads(text)
    if text[0] == "{":
        obj = json.loads(text)
        for k in ("items", "data", "results"):
            if isinstance(obj.get(k), list):
                return obj[k]
        return [obj]
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def normalize(raw):
    rows = []
    for i, it in enumerate(raw):
        rows.append({
            "name": str(pick(it, "name") or "")[:60],
            "price": to_num(pick(it, "price")),
            "reviews": to_num(pick(it, "reviews")) or 0.0,
            "rating": to_num(pick(it, "rating")),
            "rocket": to_bool(pick(it, "rocket")),
            "sponsored": to_bool(pick(it, "sponsored")),
            "rank": to_num(pick(it, "rank")) or float(i + 1),
            "url": pick(it, "url") or "",
            "keyword": pick(it, "keyword") or "(키워드 없음)",
        })
    rows.sort(key=lambda r: r["rank"])
    return rows


def lin(value, good, bad):
    """value가 good이면 1, bad이면 0, 사이는 선형."""
    if value is None:
        return 0.5
    if good == bad:
        return 0.5
    t = (value - bad) / (good - bad)
    return max(0.0, min(1.0, t))


def score(rows, track):
    organic = [r for r in rows if not r["sponsored"]] or rows
    top10 = organic[:10]
    top40 = rows[:40]

    rev10 = [r["reviews"] for r in top10]
    med_rev = statistics.median(rev10) if rev10 else None
    total_rev = sum(rev10)
    concentration = (max(rev10) / total_rev) if total_rev else None
    rocket_ratio = sum(r["rocket"] for r in top40) / len(top40) if top40 else None
    ad_ratio = sum(r["sponsored"] for r in top40) / len(top40) if top40 else None
    ratings = [r["rating"] for r in top10 if r["rating"]]
    avg_rating = statistics.mean(ratings) if ratings else None
    prices = [r["price"] for r in top10 if r["price"]]
    price_cv = (statistics.pstdev(prices) / statistics.mean(prices)) if len(prices) >= 3 else None
    newcomers = sum(1 for r in top10 if r["reviews"] < 100)
    low_rated = sum(1 for r in top10 if r["rating"] and r["rating"] < 4.3)

    metrics = {
        "barrier": (med_rev, lin(med_rev, 100, 3000), f"{med_rev:,.0f}개" if med_rev is not None else "-"),
        "concentration": (concentration, lin(concentration, 0.15, 0.6), f"{concentration:.0%}" if concentration is not None else "-"),
        "rocket": (rocket_ratio, lin(rocket_ratio, 0.2, 0.9), f"{rocket_ratio:.0%}" if rocket_ratio is not None else "-"),
        "ads": (ad_ratio, lin(ad_ratio, 0.1, 0.5), f"{ad_ratio:.0%}" if ad_ratio is not None else "-"),
        "rating_gap": (avg_rating, lin(avg_rating, 4.0, 4.8), f"{avg_rating:.2f}점" if avg_rating is not None else "-"),
        "price_room": (price_cv, lin(price_cv, 0.4, 0.05), f"CV {price_cv:.2f}" if price_cv is not None else "-"),
        "newcomers": (newcomers, lin(newcomers, 3, 0), f"리뷰<100 상품 {newcomers}개"),
    }
    w = WEIGHTS[track]
    total = sum(w[k] * metrics[k][1] for k in w)
    extra = {
        "top10": top10,
        "prices": prices,
        "low_rated": low_rated,
        "n": len(rows),
        "organic_n": len(organic),
    }
    return total, metrics, extra


def verdict(total, n):
    if n < 10:
        tag = " (표본 부족: 참고용)"
    else:
        tag = ""
    if total >= 70:
        return "🟢 진입" + tag
    if total >= 50:
        return "🟡 보류 — 차별점이 분명할 때만" + tag
    return "🔴 탈락" + tag


def render(keyword, track, total, metrics, extra):
    w = WEIGHTS[track]
    out = [f"## {keyword}  ·  트랙: {track}", ""]
    out.append(f"**경쟁강도 점수: {total:.0f} / 100 → {verdict(total, extra['n'])}**")
    kw_flags = set()
    for r in extra["top10"]:
        kw_flags.update(f for f in inspection_flags(r["name"] + " " + keyword).split() if f != "—")
    flag_text = " ".join(t for t, _ in INSPECTION_RULES if t in kw_flags) or "—"
    out.append(f"**수입검사·인증: {flag_text}** (상품명 기반 자동 표시 · 상세 확인 후 확정 · 기준은 references/import-inspection.md)")
    out.append(f"(수집 {extra['n']}개, 광고 제외 {extra['organic_n']}개 기준)")
    out.append("")
    out.append("| 지표 | 값 | 점수 | 가중치 |")
    out.append("|---|---|---|---|")
    for k in w:
        _, s, label = metrics[k]
        out.append(f"| {LABELS[k]} | {label} | {s * w[k]:.1f} | {w[k]} |")
    out.append("")
    if extra["prices"]:
        p = sorted(extra["prices"])
        out.append(f"- 상위10 가격대: 최저 {p[0]:,.0f}원 · 중앙 {statistics.median(p):,.0f}원 · 최고 {p[-1]:,.0f}원")
    out.append(f"- 상위10 중 평점 4.3 미만: {extra['low_rated']}개 (3개 이상이면 품질 보완 기회)")
    rev = [r["reviews"] for r in extra["top10"]]
    total_rev, top_rev = sum(rev), max(rev) if rev else 0
    if total_rev >= 10000:
        size = "큼 → 주력(하루 25개 이상) 후보 가능"
    elif total_rev >= 2000:
        size = "중간 → 보조 상품(하루 5~10개) 수준"
    else:
        size = "작음 → 테스트 슬롯만"
    out.append(f"- **시장 크기(월 1억 기준): {size}** — 상위10 리뷰 합계 {total_rev:,.0f}개, 1위 {top_rev:,.0f}개. "
               "리뷰 수는 누적 판매량의 대리 지표일 뿐이므로 bestSelling 정렬 결과·데이터랩 검색량과 함께 판단")
    out.append("")
    out.append("### 광고 제외 상위 10개")
    out.append("| 순위 | 상품명 | 가격 | 평점 | 리뷰 | 로켓 | 검사 |")
    out.append("|---|---|---|---|---|---|---|")
    for r in extra["top10"]:
        price = f"{r['price']:,.0f}" if r["price"] else "-"
        rating = f"{r['rating']:.1f}" if r["rating"] else "-"
        name = r["name"].replace("|", "/")
        if r["url"]:
            name = f"[{name}]({r['url']})"
        out.append(f"| {r['rank']:.0f} | {name} | {price} | {rating} | {r['reviews']:,.0f} | {'O' if r['rocket'] else ''} | {inspection_flags(r['name'])} |")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--track", choices=list(WEIGHTS), default="evergreen")
    ap.add_argument("--keyword", help="여러 키워드 중 하나만 계산")
    args = ap.parse_args()

    rows = normalize(load(args.path))
    if not rows:
        sys.exit("입력에 상품이 없습니다.")
    groups = defaultdict(list)
    for r in rows:
        groups[r["keyword"]].append(r)
    if args.keyword:
        groups = {args.keyword: groups.get(args.keyword, [])}

    print("# 쿠팡 키워드 경쟁강도\n")
    print("판정 기준: 70점 이상 진입 / 50~69 보류 / 50 미만 탈락. 점수가 높을수록 들어가기 쉽다.\n")
    for kw, items in groups.items():
        if not items:
            print(f"## {kw}\n\n데이터 없음\n")
            continue
        items.sort(key=lambda r: r["rank"])
        total, metrics, extra = score(items, args.track)
        print(render(kw, args.track, total, metrics, extra))


if __name__ == "__main__":
    main()
