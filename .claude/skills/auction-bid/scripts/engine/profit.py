"""입찰가 → 총비용·세후 순이익 계산, 목표수익을 맞추는 수익 상한가 역산."""
from . import rights as rights_mod
from . import taxes
from .regions import is_regulated

PYEONG = 3.305785


class Deal:
    """한 사건에 대해 입찰가만 바꿔가며 손익을 계산하는 계산기."""

    def __init__(self, case, cfg, market_value, rent=None):
        self.case, self.cfg, self.mv, self.rent = case, cfg, market_value, rent
        prop, auc = case["property"], case["auction"]
        self.area = float(prop["exclusive_area"])
        self.appraisal = int(auc.get("appraisal") or market_value)
        self.lawd = prop.get("lawd_cd", "")
        self.regulated = bool(prop.get("regulated")) if "regulated" in prop else is_regulated(self.lawd, cfg)
        inv = cfg["investor"]
        self.houses_after = int(inv["houses_owned"]) + 1
        self._rights_cache = {}

        c = cfg["costs"]
        survey = case.get("site_survey") or {}
        grade = (survey.get("condition_grade") or c["unknown_condition_grade"]).upper()
        self.condition_grade = grade
        build_year = prop.get("build_year")
        basis_year = int(str(cfg.get("basis_date", "2026"))[:4])
        self.new_building = bool(build_year) and basis_year - int(build_year) <= c.get("new_building_years", -1)
        if survey.get("repair_cost_override") is not None:
            self.repair = int(survey["repair_cost_override"])
        elif self.new_building:
            self.condition_grade = f"준공 {build_year}년(10년 이내) — 도배·청소만"
            self.repair = int(c["new_building_repair"])
        else:
            self.repair = round(self.area * c["supply_area_ratio"] / PYEONG * c["repair_per_pyeong"][grade], -4)
        op = prop.get("official_price")
        self.official_price = int(op) if op else round(market_value * cfg["tax"].get("official_price_ratio", 0.69), -6)
        self.official_price_estimated = not op
        self.mgmt = round(int(survey.get("unpaid_mgmt_fee") or 0) * c["mgmt_fee_common_ratio"], -4)

    def rights(self, bid):
        key = round(bid, -6)
        if key not in self._rights_cache:
            self._rights_cache[key] = rights_mod.analyze(self.case, bid, self.cfg["costs"]["auction_exec_cost_rate"])
        return self._rights_cache[key]

    def loan(self, bid):
        lc = self.cfg["loan"]
        if self.regulated:
            return min(bid * lc["regulated_ltv_of_bid"], self.appraisal * lc["regulated_ltv_of_appraisal"])
        return min(bid * lc["ltv_of_bid"], self.appraisal * lc["ltv_of_appraisal"])

    def acquisition(self, bid):
        """낙찰 후 '내 집'이 되기까지 드는 돈."""
        c = self.cfg["costs"]
        r = self.rights(bid)
        assumed = r["assumed_amount"]
        acq = taxes.acquisition_tax(bid + assumed, self.area, self.houses_after, self.regulated,
                                    self.cfg["investor"]["first_home_reduction"])
        acq_legal = acq["total"]
        tc = self.cfg["tax"]
        if tc.get("acquisition_rate"):
            base = bid + assumed
            if tc.get("acquisition_base") == "official_price":
                base = self.official_price
            acq = {"total": round(base * tc["acquisition_rate"]), "rate": tc["acquisition_rate"]}
        legal = max(bid * c["legal_fee_rate"], c["legal_fee_min"])
        eviction = c["eviction"][r["eviction_type"]]
        items = {
            "낙찰가": bid,
            "인수금액": assumed,
            "취득세 등": acq["total"],
            "법무·등기비": round(legal, -4),
            "수리비": self.repair,
            "명도비": eviction,
            "체납관리비(공용)": self.mgmt,
        }
        loan = self.loan(bid)
        return {"items": items, "total": sum(items.values()), "loan": round(loan, -4), "acq_legal": acq_legal,
                "acq_tax_rate": acq["rate"], "rights": r}

    def flip(self, bid, hold_years):
        s, c, inv = self.cfg["strategy"], self.cfg["costs"], self.cfg["investor"]
        a = self.acquisition(bid)
        months_total = self.cfg["loan"].get("interest_months") or hold_years * 12 + s["months_to_possession"]
        interest = a["loan"] * self.cfg["loan"]["rate"] * months_total / 12
        holding_tax = self.mv * c["annual_holding_tax_rate"] * hold_years
        upkeep = c["monthly_upkeep"] * s["vacancy_months"]
        rent_income = 0
        if s.get("rent_during_hold") and self.rent and hold_years >= 1:
            rent_income = self.rent["monthly_rent"] * max(hold_years * 12 - s["vacancy_months"], 0)
        sale = self.mv * (1 - s["sale_discount"]) * (1 + s["annual_price_growth"]) ** hold_years
        broker = taxes.broker_fee(sale, c["broker_vat"])
        it = a["items"]
        costs = {**it, "대출이자": round(interest, -4), "보유세": round(holding_tax, -4),
                 "공실 관리비": upkeep, "매도 중개보수": broker}
        pretax = sale + rent_income - sum(costs.values())

        tc = self.cfg["tax"]
        basis = (bid + it["인수금액"] + it["취득세 등"] + it["법무·등기비"]
                 + self.repair * c["capex_ratio"] + broker)
        resided = hold_years if inv["will_reside"] else 0
        cgt, cgt_why = taxes.capital_gains_tax(sale, basis, hold_years, self.houses_after, self.regulated,
                                               resided, tc["multi_home_cgt_surcharge"])
        if inv.get("seller_type") == "business":
            # 매매사업자: 이자·수리비 등 비용을 다 빼고 종합소득세 기본세율. 단기양도세율은 적용 안 됨.
            # 조정지역 다주택 중과 대상이면 비교과세(둘 중 큰 세액)
            tax = taxes.business_income_tax(pretax, tc.get("other_taxable_income", 0))
            why = "매매사업자 종합소득세" + (" (다른 소득 합산)" if tc.get("other_taxable_income") else " (이 건만)")
            if self.regulated and self.houses_after >= 2 and tc["multi_home_cgt_surcharge"] and cgt > tax:
                tax, why = cgt, f"매매사업자 비교과세 → {cgt_why}"
        else:
            tax, why = cgt, cgt_why
        costs["세금(지방세 포함)"] = tax
        net = pretax - tax
        cash = a["total"] - a["loan"]
        return {"bid": bid, "hold_years": hold_years, "sale_price": round(sale, -4), "rent_income": rent_income,
                "costs": costs, "net_pretax": round(pretax), "net_profit": round(net), "cash_needed": round(cash, -4), "loan": a["loan"],
                "roi": net / cash if cash > 0 else None, "cgt_reason": why}

    def rental(self, bid):
        if not self.rent:
            return None
        s, c = self.cfg["strategy"], self.cfg["costs"]
        a = self.acquisition(bid)
        deposit, monthly = self.rent["deposit"], self.rent["monthly_rent"]
        cash = a["total"] - a["loan"] - deposit
        interest = a["loan"] * self.cfg["loan"]["rate"]
        holding_tax = self.mv * c["annual_holding_tax_rate"]
        annual = monthly * 12 - interest - holding_tax
        first_year_cost = (a["loan"] * self.cfg["loan"]["rate"] * s["months_to_possession"] / 12
                           + c["monthly_upkeep"] * s["vacancy_months"])
        return {"bid": bid, "deposit": deposit, "monthly_rent": monthly, "cash_needed": round(cash, -4),
                "annual_net": round(annual, -4), "setup_cost": round(first_year_cost, -4),
                "yield": (annual / cash) if cash > 0 else None, "loan": a["loan"]}


def _scan_max(ok, lo, hi, step):
    best = None
    b = lo
    while b <= hi:
        if ok(b):
            best = b
        b += step
    return best


def profit_key(cfg):
    return "net_pretax" if cfg["strategy"].get("target_basis") == "pretax" else "net_profit"


def max_bid_flip(deal, hold_years, cfg):
    target = cfg["strategy"]["target_net_profit"]
    step = cfg["recommend"]["step"]
    hi = int(deal.mv * 1.1)
    key = profit_key(cfg)
    return _scan_max(lambda b: deal.flip(b, hold_years)[key] >= target, step, hi, step)


def max_bid_rent(deal, cfg):
    if not deal.rent:
        return None
    target = cfg["strategy"]["target_rent_yield"]
    step = cfg["recommend"]["step"]

    def ok(b):
        r = deal.rental(b)
        return r["annual_net"] > 0 and (r["yield"] is None or r["yield"] >= target)

    return _scan_max(ok, step, int(deal.mv * 1.1), step)
