"""최종 추천: 최저가 ~ 상한가 사이에서 기대수익(낙찰확률 × 순이익)이 가장 큰 입찰가 + 보수/공격 안."""
import math

from .profit import Deal, max_bid_flip, max_bid_rent
from .winprob import WinModel


def odd_price(bid, floor_price, ceiling, cfg):
    """딱 떨어지는 금액을 피한다: 10만 원 단위로 내리고 끝자리를 붙인다. 최저가~상한가 안으로."""
    tail = cfg["recommend"]["odd_tail"]
    out = math.floor(bid / 100_000) * 100_000 + tail
    if ceiling is not None and out > ceiling:
        out -= 100_000
    if out < floor_price:
        out = math.ceil(floor_price / 100_000) * 100_000 + tail
        if ceiling is not None and out > ceiling:
            out = floor_price
    return int(out)


def run(case, cfg, market_value, rent, results, today=None):
    auc, prop = case["auction"], case["property"]
    min_price = int(auc["min_price"])
    strategy = cfg["strategy"]["primary"]
    deal = Deal(case, cfg, market_value, rent)
    wm = WinModel(cfg, prop.get("lawd_cd", ""), prop.get("type", "아파트"), results, today)
    rate = auc.get("reduction_rate") or cfg["winprob"]["reduction_rate"]
    prev_min = round(min_price / (1 - rate)) if int(auc.get("failed_count") or 0) > 0 else None

    # 1) 전략별 상한가
    scenarios = []
    for h in cfg["strategy"]["hold_scenarios_years"]:
        mb = max_bid_flip(deal, h, cfg)
        scenarios.append({"hold_years": h, "max_bid": mb,
                          "at_max": deal.flip(mb, h) if mb else None,
                          "at_min": deal.flip(min_price, h)})
    best_flip = max(scenarios, key=lambda s: s["max_bid"] or 0)
    rent_max = max_bid_rent(deal, cfg)
    rent_info = {"max_bid": rent_max, "at_min": deal.rental(min_price),
                 "at_max": deal.rental(rent_max) if rent_max else None, "rent": rent}

    if strategy == "rent" and rent_max:
        max_bid = rent_max
        profit_of = lambda b: deal.rental(b)["annual_net"]
        primary_label = "임대수익"
    else:
        max_bid = best_flip["max_bid"]
        hold = best_flip["hold_years"]
        profit_of = lambda b: deal.flip(b, hold)["net_profit"]
        primary_label = f"매도차익 ({hold:g}년 보유)" if max_bid else "매도차익"

    resale = bool(auc.get("resale"))
    deposit = round(min_price * cfg["winprob"]["resale_deposit_rate" if resale else "deposit_rate"])
    out = {
        "strategy": primary_label, "min_price": min_price, "max_bid": max_bid, "deposit": deposit,
        "scenarios": scenarios, "rental": rent_info, "win_model": wm.describe(prev_min), "prev_min": prev_min,
        "condition_grade": deal.condition_grade, "repair": deal.repair, "regulated": deal.regulated,
        "rights": deal.rights(max(min_price, max_bid or 0)),
    }

    # 2) 패스 판정
    reasons = []
    if not max_bid:
        reasons.append("목표 수익을 맞추는 입찰가가 없다")
    elif max_bid < min_price:
        reasons.append(f"최저가({min_price:,})가 수익 상한가({max_bid:,})보다 높다")
    if out["rights"]["red_flags"]:
        reasons.append("위험 권리: " + ", ".join(out["rights"]["red_flags"]))

    # 3) 기대수익 곡선
    step = cfg["recommend"]["step"]
    curve = []
    if max_bid and max_bid >= min_price:
        b = min_price
        while b <= max_bid:
            p = wm.prob(b, min_price, market_value, prev_min)
            pr = profit_of(b)
            curve.append({"bid": b, "prob": p, "profit": pr, "ev": p * pr})
            b += step
        if curve[-1]["bid"] != max_bid:
            p = wm.prob(max_bid, min_price, market_value, prev_min)
            pr = profit_of(max_bid)
            curve.append({"bid": max_bid, "prob": p, "profit": pr, "ev": p * pr})
    out["curve"] = curve

    if curve:
        best = max(curve, key=lambda c: c["ev"])
        # 보수 = 기대수익을 추천안의 일정 비율 이상 지키면서 가장 싸게 쓰는 가격
        keep = cfg["recommend"]["conservative_ev_ratio"]
        cons = next(c for c in curve if c["ev"] >= best["ev"] * keep)
        picks = {}
        for name, c in (("보수", cons), ("추천", best), ("공격", curve[-1])):
            bid = odd_price(c["bid"], min_price, max_bid, cfg)
            picks[name] = {"bid": bid, "prob": wm.prob(bid, min_price, market_value, prev_min), "profit": profit_of(bid)}
            picks[name]["ev"] = picks[name]["prob"] * picks[name]["profit"]
        out["picks"] = picks
    else:
        out["picks"] = {}

    # 4) 다음 회차(유찰 시) 시나리오
    nxt_min = round(min_price * (1 - rate))
    p_fail = wm.no_bid_prob(min_price, market_value)
    nxt_best = None
    if max_bid and max_bid >= nxt_min:
        b, best_ev = nxt_min, None
        while b <= max_bid:
            ev = wm.prob(b, nxt_min, market_value, min_price) * profit_of(b)
            if best_ev is None or ev > best_ev[1]:
                best_ev = (b, ev)
            b += step
        nxt_best = {"bid": best_ev[0], "ev": best_ev[1], "prob": wm.prob(best_ev[0], nxt_min, market_value, min_price)}
    now_ev = out["picks"]["추천"]["ev"] if out["picks"] else 0
    wait_ev = p_fail * (nxt_best["ev"] if nxt_best else 0)
    out["next_round"] = {"min_price": nxt_min, "fail_prob": p_fail, "best": nxt_best,
                         "wait_ev": wait_ev, "better_to_wait": wait_ev > now_ev}

    if reasons:
        verdict = "패스"
    elif out["next_round"]["better_to_wait"]:
        verdict = "다음 회차 대기"
    elif out["rights"]["needs_expert"] or out["rights"]["yellow_flags"]:
        verdict = "입찰 검토 (확인 필요)"
    else:
        verdict = "입찰 추천"
    out["verdict"], out["pass_reasons"] = verdict, reasons
    return out
