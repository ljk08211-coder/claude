"""주택 취득세·양도소득세·중개보수. 세율표는 2026년 기준(입찰 전 꼭 확인)."""

# 양도소득세 기본세율 (과세표준 상한, 세율, 누진공제)
CGT_BRACKETS = [
    (14_000_000, 0.06, 0),
    (50_000_000, 0.15, 1_260_000),
    (88_000_000, 0.24, 5_760_000),
    (150_000_000, 0.35, 15_440_000),
    (300_000_000, 0.38, 19_940_000),
    (500_000_000, 0.40, 25_940_000),
    (1_000_000_000, 0.42, 35_940_000),
    (float("inf"), 0.45, 65_940_000),
]

# 매매 중개보수 상한 (거래가 상한, 요율, 한도액)
BROKER_TABLE = [
    (50_000_000, 0.006, 250_000),
    (200_000_000, 0.005, 800_000),
    (900_000_000, 0.004, None),
    (1_200_000_000, 0.005, None),
    (1_500_000_000, 0.006, None),
    (float("inf"), 0.007, None),
]

CGT_EXEMPT_LIMIT = 1_200_000_000


def acquisition_tax(price, area, houses_after, regulated, first_home_reduction=False):
    """취득세 + 지방교육세 + 농어촌특별세. houses_after = 취득 후 주택 수."""
    standard = houses_after == 1 or (houses_after == 2 and not regulated)
    if standard:
        if price <= 600_000_000:
            rate = 0.01
        elif price <= 900_000_000:
            rate = (price * 2 / 300_000_000 - 3) / 100
        else:
            rate = 0.03
        edu = rate * 0.1
        rural = 0.002 if area > 85 else 0.0
    else:
        rate = 0.08 if (houses_after == 2 or (houses_after == 3 and not regulated)) else 0.12
        edu = 0.004
        rural = (0.006 if rate == 0.08 else 0.01) if area > 85 else 0.0
    acq = price * rate
    if first_home_reduction and standard and houses_after == 1 and price <= 1_200_000_000:
        acq -= min(acq, 2_000_000)
    total = acq + price * (edu + rural)
    return {"total": round(total), "rate": rate, "effective_rate": total / price if price else 0}


def broker_fee(price, vat=0.1):
    for cap, rate, limit in BROKER_TABLE:
        if price < cap:
            fee = price * rate
            if limit:
                fee = min(fee, limit)
            return round(fee * (1 + vat))
    return 0


def _progressive(base):
    for cap, rate, ded in CGT_BRACKETS:
        if base <= cap:
            return max(base * rate - ded, 0)
    return 0


def capital_gains_tax(sale, basis, hold_years, houses_at_sale, regulated_at_acq, resided_years, surcharge_on=True):
    """양도소득세 + 지방소득세(10%). 반환: (세액, 설명)."""
    gain = sale - basis
    if gain <= 0:
        return 0, "양도차익 없음"
    if houses_at_sale == 1 and hold_years >= 2 and sale <= CGT_EXEMPT_LIMIT:
        if not regulated_at_acq or resided_years >= 2:
            return 0, "1세대1주택 비과세 (2년 보유" + (", 2년 거주" if regulated_at_acq else "") + ")"
    ltsd = 0.0
    if hold_years >= 3:
        ltsd = min(0.02 * int(hold_years), 0.30)
    base = max(gain * (1 - ltsd) - 2_500_000, 0)
    surcharge = 0.0
    if surcharge_on and regulated_at_acq and houses_at_sale >= 2:
        surcharge = 0.20 if houses_at_sale == 2 else 0.30
        ltsd = 0.0
        base = max(gain - 2_500_000, 0)
    general = _progressive(base) + base * surcharge
    if hold_years < 1:
        tax, why = max(base * 0.70, general), "단기양도 70% (1년 미만)"
    elif hold_years < 2:
        tax, why = max(base * 0.60, general), "단기양도 60% (2년 미만)"
    else:
        tax, why = general, "기본세율" + (f" + 중과 {surcharge:.0%}p" if surcharge else "")
    return round(tax * 1.1), why
