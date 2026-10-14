"""시세 추정: 실거래 비교사례 → 시점·층 보정 → 가중 중앙값 → KB·호가 교차검증."""
import datetime as dt
import statistics
from collections import defaultdict

from .molit import norm_name


def _date(s):
    return dt.date.fromisoformat(s)


def _months_between(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def regional_index(trades, today):
    """시군구 전체 거래의 월별 ㎡당 중앙값(3개월 이동평균) → {YYYY-MM: 지수}. 오늘 기준 1.0."""
    by_month = defaultdict(list)
    for t in trades:
        by_month[t["date"][:7]].append(t["price"] / t["area"])
    months = sorted(m for m, v in by_month.items() if len(v) >= 5)
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
    return 1.0 if months_ago <= 3 else 0.7 if months_ago <= 6 else 0.5


def estimate(case, trades, cfg, today=None):
    today = today or dt.date.today()
    mc = cfg["market"]
    prop = case["property"]
    area = float(prop["exclusive_area"])
    target_name = norm_name(prop.get("apt_name", ""))
    target_dong = prop.get("dong", "")
    target_floor_adj = floor_adj(prop.get("floor"), prop.get("top_floor"), cfg)
    by = prop.get("build_year")

    recent = [t for t in trades if _months_between(_date(t["date"]), today) <= mc["comp_months"]]
    index = regional_index(trades, today)

    def same_apt(t):
        n = norm_name(t["apt_name"])
        name_ok = bool(target_name) and (target_name in n or n in target_name)
        return name_ok and (not target_dong or t["dong"] == target_dong)

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
        result["confidence"] = "높음" if n >= 5 else "보통" if n >= 3 else "낮음"
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
    name, dong = norm_name(prop.get("apt_name", "")), prop.get("dong", "")
    conv = cfg["market"]["rent_conversion_rate"]
    base_deposit = round(market_value * 0.1, -6)
    recent = [r for r in rents if r["monthly_rent"] > 0
              and _months_between(_date(r["date"]), today) <= 12
              and abs(r["area"] - area) <= area * 0.1]
    for label, pick in (("같은 단지", lambda r: name and name in norm_name(r["apt_name"])),
                        ("같은 동네", lambda r: r["dong"] == dong)):
        rows = [r for r in recent if pick(r)]
        if len(rows) >= 3:
            adj = [r["monthly_rent"] + (r["deposit"] - base_deposit) * conv / 12 for r in rows]
            return {"deposit": int(base_deposit), "monthly_rent": int(round(statistics.median(adj), -4)),
                    "count": len(rows), "source": label}
    return None
