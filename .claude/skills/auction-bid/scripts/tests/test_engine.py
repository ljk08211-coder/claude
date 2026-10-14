"""엔진 단위 테스트 (네트워크 없이 가상 실거래 데이터로).

실행: python3 -m unittest discover -s .claude/skills/auction-bid/scripts/tests
"""
import datetime as dt
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import config, market, recommend, regions, report, rights, taxes  # noqa: E402
from engine.profit import Deal, max_bid_flip  # noqa: E402
from engine.winprob import WinModel  # noqa: E402

TODAY = dt.date(2026, 10, 14)


def fake_trades(seed=1):
    """해운대구 가상 실거래: 대상 단지 84㎡ ≈ 2억5천, 동네 다른 단지 포함."""
    rnd = random.Random(seed)
    rows = []
    for m in range(12):
        d = (TODAY.replace(day=1) - dt.timedelta(days=30 * m)).replace(day=10)
        for _ in range(8):  # 지역 지수용 잡음 거래
            area = rnd.choice([59.9, 84.9, 114.8])
            rows.append({"date": d.isoformat(), "apt_name": f"다른단지{rnd.randint(1, 9)}", "dong": "반여동",
                         "area": area, "floor": rnd.randint(1, 20), "build_year": 2000,
                         "price": int(area * 3_000_000 * rnd.uniform(0.95, 1.05)), "dealing": "중개거래"})
        if m % 2 == 0:
            rows.append({"date": d.isoformat(), "apt_name": "해운대테스트", "dong": "좌동", "area": 84.9,
                         "floor": rnd.randint(3, 15), "build_year": 1997,
                         "price": int(250_000_000 * rnd.uniform(0.97, 1.03)), "dealing": "중개거래"})
    rows.append({"date": TODAY.replace(day=1).isoformat(), "apt_name": "해운대테스트", "dong": "좌동",
                 "area": 84.9, "floor": 7, "build_year": 1997, "price": 150_000_000, "dealing": "직거래"})
    return rows


def fake_rents():
    return [{"date": (TODAY - dt.timedelta(days=20 * i)).isoformat(), "apt_name": "해운대테스트", "dong": "좌동",
             "area": 84.9, "floor": 5, "build_year": 1997, "deposit": 20_000_000, "monthly_rent": 800_000}
            for i in range(5)]


def base_case():
    return {
        "case_no": "2026타경99999",
        "property": {"type": "아파트", "region": "부산 해운대구", "lawd_cd": "26350", "dong": "좌동",
                     "apt_name": "해운대테스트", "exclusive_area": 84.9, "floor": 9, "build_year": 1997},
        "auction": {"appraisal": 260_000_000, "min_price": 166_400_000, "failed_count": 2,
                    "sale_date": "2026-11-20"},
        "occupancy": {"type": "owner"},
        "rights": [{"type": "근저당", "date": "2019-05-02", "amount": 180_000_000, "holder": "○○은행"},
                   {"type": "가압류", "date": "2025-01-10", "amount": 30_000_000, "holder": "○○카드"}],
        "tenants": [],
        "flags": [],
        "site_survey": {"condition_grade": "B", "unpaid_mgmt_fee": 1_000_000},
        "overrides": {},
    }


class TestRegions(unittest.TestCase):
    def test_resolve(self):
        self.assertEqual(regions.resolve("해운대구"), "26350")
        self.assertEqual(regions.resolve("부산 해운대구"), "26350")
        self.assertEqual(regions.resolve("서울 강서구"), "11500")
        self.assertEqual(regions.resolve("26350"), "26350")
        with self.assertRaises(ValueError):
            regions.resolve("강서구")  # 부산·서울 둘 다 있음

    def test_regulated(self):
        cfg = config.load()
        self.assertTrue(regions.is_regulated("11500", cfg))
        self.assertFalse(regions.is_regulated("26350", cfg))
        self.assertTrue(regions.is_regulated("41465", cfg))


class TestTaxes(unittest.TestCase):
    def test_acquisition_one_home(self):
        t = taxes.acquisition_tax(250_000_000, 84.9, 1, False)
        self.assertAlmostEqual(t["total"], 250_000_000 * 0.011)

    def test_acquisition_over_85(self):
        t = taxes.acquisition_tax(250_000_000, 114.8, 1, False)
        self.assertAlmostEqual(t["total"], 250_000_000 * 0.013)

    def test_acquisition_regulated_two_homes(self):
        self.assertEqual(taxes.acquisition_tax(300_000_000, 59, 2, True)["rate"], 0.08)
        self.assertEqual(taxes.acquisition_tax(300_000_000, 59, 2, False)["rate"], 0.01)

    def test_cgt_short_term(self):
        tax, why = taxes.capital_gains_tax(250_000_000, 200_000_000, 0.5, 1, False, 0)
        self.assertIn("70%", why)
        self.assertEqual(tax, round((50_000_000 - 2_500_000) * 0.7 * 1.1))

    def test_cgt_exempt(self):
        tax, why = taxes.capital_gains_tax(250_000_000, 200_000_000, 2.0, 1, False, 0)
        self.assertEqual(tax, 0)
        tax, _ = taxes.capital_gains_tax(250_000_000, 200_000_000, 2.0, 1, True, 0)
        self.assertGreater(tax, 0)  # 조정지역 취득은 2년 거주해야 비과세

    def test_broker(self):
        self.assertEqual(taxes.broker_fee(150_000_000, 0), 750_000)
        self.assertEqual(taxes.broker_fee(190_000_000, 0), 800_000)  # 한도
        self.assertEqual(taxes.broker_fee(250_000_000, 0), 1_000_000)

    def test_korean_amount(self):
        self.assertEqual(report.korean_amount(231_070_000), "이억삼천일백칠만원")
        self.assertEqual(report.eok(231_070_000), "2억 3,107만원")
        self.assertEqual(report.eok(203_374_930), "2억 337만원")


class TestRights(unittest.TestCase):
    def test_opposable_tenant_not_claimed(self):
        case = base_case()
        case["tenants"] = [{"name": "김", "move_in": "2018-03-01", "fixed_date": "2018-03-01",
                            "deposit": 50_000_000, "claimed_dividend": False}]
        r = rights.analyze(case, 220_000_000)
        self.assertEqual(r["assumed_amount"], 50_000_000)
        self.assertTrue(r["red_flags"])

    def test_opposable_tenant_paid_in_full(self):
        case = base_case()
        case["tenants"] = [{"name": "김", "move_in": "2018-03-01", "fixed_date": "2018-03-02",
                            "deposit": 50_000_000, "claimed_dividend": True}]
        r = rights.analyze(case, 220_000_000)
        self.assertEqual(r["assumed_amount"], 0)  # 근저당보다 먼저 배당

    def test_junior_tenant(self):
        case = base_case()
        case["occupancy"] = {"type": "tenant"}
        case["tenants"] = [{"name": "이", "move_in": "2022-03-01", "fixed_date": "2022-03-01",
                            "deposit": 30_000_000, "claimed_dividend": True}]
        r = rights.analyze(case, 200_000_000)
        self.assertEqual(r["assumed_amount"], 0)
        self.assertFalse(r["tenants"][0]["opposable"])
        self.assertEqual(r["eviction_type"], "tenant_partial")  # 근저당 1.8억 뒤라 일부만 배당

    def test_red_keyword(self):
        case = base_case()
        case["flags"] = ["유치권 신고 있음"]
        self.assertIn("유치권 신고", rights.analyze(case, 2e8)["red_flags"])


class TestEngine(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()

    def test_market_value(self):
        mv = market.estimate(base_case(), fake_trades(), self.cfg, TODAY)
        self.assertEqual(mv["comps"][0]["tier"], "같은 단지·같은 평형")
        self.assertTrue(240_000_000 <= mv["value"] <= 265_000_000, mv["value"])
        self.assertTrue(any("이상거래" in n for n in mv["notes"]))  # 1.5억 직거래 제외

    def test_low_confidence_takes_lowest(self):
        case = base_case()
        case["site_survey"]["asking_prices"] = [215_000_000, 230_000_000]
        mv = market.estimate(case, fake_trades(), self.cfg, TODAY)
        self.assertEqual(mv["confidence"], "낮음")
        self.assertEqual(mv["value"], 215_000_000)

    def test_max_bid_hits_target(self):
        deal = Deal(base_case(), self.cfg, 250_000_000)
        mb = max_bid_flip(deal, 2.0, self.cfg)
        target = self.cfg["strategy"]["target_net_profit"]
        self.assertGreaterEqual(deal.flip(mb, 2.0)["net_profit"], target)
        self.assertLess(deal.flip(mb + 100_000, 2.0)["net_profit"], target)

    def test_two_year_hold_beats_short(self):
        deal = Deal(base_case(), self.cfg, 250_000_000)
        self.assertGreater(max_bid_flip(deal, 2.0, self.cfg), max_bid_flip(deal, 0.5, self.cfg))

    def test_win_prob_monotonic(self):
        wm = WinModel(self.cfg, "26350", "아파트", [], TODAY)
        ps = [wm.prob(b, 200_000_000, 250_000_000) for b in range(200_000_000, 250_000_001, 5_000_000)]
        self.assertEqual(ps, sorted(ps))
        self.assertEqual(wm.prob(199_000_000, 200_000_000, 250_000_000), 0.0)

    def test_win_model_uses_results(self):
        results = [{"lawd_cd": "26350", "property_type": "아파트", "sale_date": "2026-09-01",
                    "winning_bid": str(int(250_000_000 * r)), "market_value": "250000000"}
                   for r in (0.8, 0.82, 0.85, 0.86, 0.87, 0.9, 0.91, 0.93, 0.95)]
        wm = WinModel(self.cfg, "26350", "아파트", results, TODAY)
        self.assertIn("낙찰사례 9건", wm.source)

    def test_full_run(self):
        case = base_case()
        mv = market.estimate(case, fake_trades(), self.cfg, TODAY)
        rent = market.rent_estimate(case, fake_rents(), mv["value"], self.cfg, TODAY)
        rec = recommend.run(case, self.cfg, mv["value"], rent, [], TODAY)
        self.assertIn(rec["verdict"], ("입찰 추천", "입찰 검토 (확인 필요)", "다음 회차 대기"))
        picks = rec["picks"]
        self.assertTrue(rec["min_price"] <= picks["보수"]["bid"] <= picks["추천"]["bid"]
                        <= picks["공격"]["bid"] <= rec["max_bid"])
        self.assertEqual(picks["추천"]["bid"] % 100_000, self.cfg["recommend"]["odd_tail"])
        html = report.html_report(case, mv, rec, self.cfg)
        self.assertIn("추천 입찰가", html)

    def test_pass_when_min_above_max(self):
        case = base_case()
        case["auction"]["min_price"] = 260_000_000
        mv = market.estimate(case, fake_trades(), self.cfg, TODAY)
        rec = recommend.run(case, self.cfg, mv["value"], None, [], TODAY)
        self.assertEqual(rec["verdict"], "패스")
        self.assertEqual(rec["picks"], {})


if __name__ == "__main__":
    unittest.main()
