"""낙찰 확률: 비슷한 물건들의 '낙찰가 ÷ 시세' 분포로 입찰가별 낙찰 확률을 추정한다.

P(낙찰 | 입찰가 b) = P(유찰될 회차) + (1 − P(유찰)) × P(경쟁자 최고가 < b | 경쟁자는 최저가 이상)
낙찰결과(results.csv)가 쌓이면 지역 실제 분포로 바뀐다.
"""
import csv
import datetime as dt
from pathlib import Path

RESULT_FIELDS = ["recorded_at", "sale_date", "case_no", "lawd_cd", "property_type", "market_value",
                 "appraisal", "min_price", "winning_bid", "bidders", "failed_count", "my_bid", "source"]


def _interp(points, x):
    pts = sorted(points)
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 != x0 else y1
    return pts[-1][1]


def _quantiles(values):
    values = sorted(values)
    n = len(values)
    out = []
    for q in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
        pos = q * (n - 1)
        i = int(pos)
        frac = pos - i
        v = values[i] + (values[min(i + 1, n - 1)] - values[i]) * frac
        out.append([q, v])
    # 끝을 조금 넓혀서 관측 범위 밖도 0/1 이 되도록
    out[0][1] -= 0.03
    out[-1][1] += 0.03
    return out


def load_results(path):
    if not path or not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_result(path, row):
    path = Path(path)
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in RESULT_FIELDS})


class WinModel:
    def __init__(self, cfg, lawd_cd, property_type, results, today=None):
        wc = cfg["winprob"]
        today = today or dt.date.today()
        cutoff = today - dt.timedelta(days=30 * wc["lookback_months"])
        ratios = []
        for r in results:
            try:
                if r.get("property_type", "아파트") != property_type:
                    continue
                if (r.get("lawd_cd") or "")[:5] != lawd_cd[:5]:
                    continue
                if r.get("sale_date") and dt.date.fromisoformat(r["sale_date"]) < cutoff:
                    continue
                win, mv = float(r["winning_bid"]), float(r["market_value"])
                if win > 0 and mv > 0:
                    ratios.append(win / mv)
            except (KeyError, ValueError):
                continue
        self.case_count = len(ratios)
        if len(ratios) >= wc["min_cases"]:
            self.quantiles = _quantiles(ratios)
            self.source = f"이 지역 최근 {wc['lookback_months']}개월 낙찰사례 {len(ratios)}건"
        else:
            self.quantiles = [list(p) for p in wc["default_quantiles"]]
            self.source = (f"기본 분포 (지역 낙찰사례 {len(ratios)}건 < {wc['min_cases']}건) — "
                           "record 로 낙찰결과를 쌓을수록 정확해진다")
        self.empirical = len(ratios) >= wc["min_cases"]
        self.gap_quantiles = wc["failed_gap_quantiles"]
        self.no_bid_curve = wc["no_bid_curve"]

    def cdf(self, ratio):
        """경쟁 낙찰가율이 ratio 이하일 확률."""
        pts = [(v, q) for q, v in self.quantiles]
        return min(max(_interp(pts, ratio), 0.0), 1.0)

    def ratio_at(self, q):
        return _interp([(qq, v) for qq, v in self.quantiles], q)

    def no_bid_prob(self, min_price, mv):
        return min(max(_interp(self.no_bid_curve, min_price / mv), 0.0), 1.0)

    def describe(self, prev_min):
        if prev_min and not self.empirical:
            return ("유찰 물건 기본 가정 (직전 회차 최저가 근처에서 낙찰되는 경향) — "
                    f"지역 낙찰사례 {self.case_count}건, record 로 쌓을수록 정확해진다")
        return self.source

    def prob(self, bid, min_price, mv, prev_min=None):
        if bid < min_price:
            return 0.0
        p_none = self.no_bid_prob(min_price, mv)
        if prev_min and prev_min > min_price and not self.empirical:
            g = (bid - min_price) / (prev_min - min_price)
            f = _interp([(v, q) for q, v in self.gap_quantiles], g)
            return p_none + (1 - p_none) * min(max(f, 0.0), 1.0)
        f_min = self.cdf(min_price / mv)
        if f_min >= 1.0:
            return 1.0
        f = (self.cdf(bid / mv) - f_min) / (1 - f_min)
        return p_none + (1 - p_none) * min(max(f, 0.0), 1.0)
