"""권리분석 자동 플래그: 말소기준권리, 임차인 대항력, 배당 시뮬레이션, 인수금액, 위험 키워드.

판단이 애매하면 보수적으로(낙찰자에게 불리하게) 계산하고 '전문가 확인 필요'를 띄운다.
"""
import datetime as dt

BASE_TYPES = ("근저당", "저당", "압류", "가압류", "담보가등기", "경매개시결정")
SECURED = ("근저당", "저당", "담보가등기")
TAX_HOLDERS = ("세무서", "시청", "구청", "군청", "국민건강", "국민연금", "근로복지", "국세", "지방세")

# 하나라도 있으면 초보 단계에선 패스
RED_KEYWORDS = {
    "유치권": "유치권 신고",
    "법정지상권": "법정지상권 성립 여지",
    "지분": "지분 경매",
    "대지권미등기": "대지권 미등기",
    "대지권 미등기": "대지권 미등기",
    "토지별도등기": "토지 별도등기",
    "위반건축물": "위반건축물",
    "재매각": "재매각 사건 (보증금 20%)",
    "특별매각조건": "특별매각조건 있음",
}
YELLOW_KEYWORDS = {
    "폐문부재": "현황조사 때 폐문부재 — 점유자 확인 안 됨",
    "전입세대": "전입세대열람으로 점유자 재확인 필요",
    "관리비": "관리비 체납 확인 필요",
    "선순위 전세권": "선순위 전세권 — 배당요구 여부 확인",
}


def _d(s):
    return dt.date.fromisoformat(s) if s else None


def analyze(case, bid, exec_cost_rate=0.005):
    rights = sorted(case.get("rights") or [], key=lambda r: r["date"])
    tenants = case.get("tenants") or []
    red, yellow = [], []

    base = next((r for r in rights if any(t in r["type"] for t in BASE_TYPES)), None)
    base_date = _d(base["date"]) if base else None
    if not base:
        yellow.append("말소기준권리를 못 찾았다 — 등기부를 확인해서 rights 에 넣어야 한다")

    assumed_rights = []
    for r in rights:
        if base and _d(r["date"]) < base_date and not any(t in r["type"] for t in BASE_TYPES):
            assumed_rights.append(r)
            if any(k in r["type"] for k in ("가처분", "가등기", "지상권", "임차권")):
                red.append(f"선순위 {r['type']} ({r['date']}) — 낙찰자가 인수")
            elif "전세권" in r["type"]:
                yellow.append(f"선순위 전세권 ({r['date']}) — 배당요구 안 했으면 인수")
    for r in rights:
        if "압류" in r["type"] and any(h in (r.get("holder") or "") for h in TAX_HOLDERS):
            yellow.append(f"조세·공과금 압류({r.get('holder')}) — 당해세가 임차인보다 먼저 배당될 수 있음")
            break

    # 배당 시뮬레이션 (최우선변제·당해세는 생략 → 임차인 배당을 다소 과대평가할 수 있어 위 경고로 보완)
    pool = bid * (1 - exec_cost_rate)
    claims = []
    for r in rights:
        if any(t in r["type"] for t in SECURED + ("압류", "가압류")) and r.get("amount"):
            claims.append((_d(r["date"]), r["type"], int(r["amount"]), None))
    for i, t in enumerate(tenants):
        if t.get("claimed_dividend") and t.get("fixed_date") and t.get("move_in"):
            prio = max(_d(t["move_in"]) + dt.timedelta(days=1), _d(t["fixed_date"]))
            claims.append((prio, "임차인", int(t.get("deposit") or 0), i))
    paid = {}
    for date_, kind, amount, ti in sorted(claims, key=lambda c: c[0]):
        got = min(amount, max(pool, 0))
        pool -= got
        if ti is not None:
            paid[ti] = got

    tenant_rows, assumed_amount = [], sum(int(r.get("amount") or 0) for r in assumed_rights)
    for i, t in enumerate(tenants):
        deposit = int(t.get("deposit") or 0)
        move_in = _d(t.get("move_in"))
        opposable = bool(move_in and base_date and move_in < base_date)
        if move_in and not base_date:
            opposable = True  # 기준을 모르면 대항력 있다고 가정
        got = paid.get(i, 0)
        if opposable:
            assumed = deposit - got if t.get("claimed_dividend") else deposit
        else:
            assumed = 0
        assumed_amount += assumed
        if opposable and not t.get("claimed_dividend"):
            red.append(f"대항력 있는 임차인 {t.get('name', '')} 배당요구 안 함 → 보증금 {deposit:,}원 전액 인수")
        elif opposable and assumed > 0:
            yellow.append(f"대항력 있는 임차인 {t.get('name', '')} 미배당 {assumed:,}원 인수")
        if opposable and not t.get("fixed_date"):
            yellow.append(f"임차인 {t.get('name', '')} 확정일자 정보 없음 — 명세서 재확인")
        tenant_rows.append({**t, "opposable": opposable, "dividend": got, "assumed": assumed})

    text = " ".join([*(case.get("flags") or []), case.get("notes") or "",
                     (case.get("auction") or {}).get("special_conditions") or ""])
    for kw, label in RED_KEYWORDS.items():
        if kw in text and label not in red:
            red.append(label)
    for kw, label in YELLOW_KEYWORDS.items():
        if kw in text and label not in yellow:
            yellow.append(label)
    if (case.get("auction") or {}).get("resale") and "재매각 사건 (보증금 20%)" not in red:
        red.append("재매각 사건 (보증금 20%)")

    occ = (case.get("occupancy") or {}).get("type", "unknown")
    if occ == "unknown":
        yellow.append("점유자 미확인 — 현황조사서·전입세대열람으로 누가 사는지 확인 (명도비는 보수적으로 가정)")
    if occ == "tenant" and tenant_rows:
        main = max(tenant_rows, key=lambda t: int(t.get("deposit") or 0))
        dep = int(main.get("deposit") or 0)
        if main["opposable"] or (dep and main["dividend"] >= dep):
            eviction = "tenant_paid"
        elif main["dividend"] > 0:
            eviction = "tenant_partial"
        else:
            eviction = "tenant_unpaid"
    else:
        eviction = occ if occ in ("vacant", "owner") else "unknown"

    return {
        "base_right": base,
        "assumed_rights": assumed_rights,
        "tenants": tenant_rows,
        "assumed_amount": assumed_amount,
        "eviction_type": eviction,
        "red_flags": red,
        "yellow_flags": yellow,
        "needs_expert": bool(red) or any("인수" in y for y in yellow),
    }
