"""결과 → 콘솔 요약(마크다운) + HTML 리포트."""
import html

DIGITS = "영일이삼사오육칠팔구"


def won(n):
    return "-" if n is None else f"{int(round(n)):,}원"


def eok(n):
    """231070000 → '2억 3,107만원'. 만 원 단위로 반올림."""
    if n is None:
        return "-"
    n = int(round(n, -4))
    sign, n = ("-" if n < 0 else ""), abs(n)
    e, rest = divmod(n, 100_000_000)
    man, one = divmod(rest, 10_000)
    parts = [f"{e}억"] * bool(e) + [f"{man:,}만"] * bool(man) + [f"{one:,}"] * bool(one)
    return sign + (" ".join(parts) or "0") + "원"


def korean_amount(n):
    """입찰표 확인용 한글 금액: 231070000 → '이억삼천일백칠만원'."""
    def four(x):
        out = ""
        for unit, d in (("천", x // 1000), ("백", x // 100 % 10), ("십", x // 10 % 10), ("", x % 10)):
            if d:
                out += DIGITS[d] + unit
        return out
    n = int(n)
    parts = []
    for unit, size in (("억", 100_000_000), ("만", 10_000), ("", 1)):
        q, n = divmod(n, size)
        if q:
            parts.append(four(q) + unit)
    return "".join(parts) + "원"


def pct(x):
    return "-" if x is None else f"{x:.0%}"


EVICTION_LABEL = {
    "vacant": "공실", "owner": "소유자 점유", "tenant_paid": "임차인 (배당·보증금 회수로 협조 기대)",
    "tenant_partial": "임차인 (일부만 배당 — 협상 필요)", "tenant_unpaid": "임차인 (배당 못 받음 — 명도 어려움)",
    "unknown": "점유자 미확인",
}


def low_prob_note(rec):
    top = rec["picks"].get("공격")
    if top and top["prob"] < 0.15:
        return (f"상한가로 써도 낙찰확률이 {top['prob']:.0%} 정도다. 목표 수익이 이 시장 기준으로 높은 편 — "
                "목표를 낮추거나 유찰을 기다리는 물건으로 보는 게 맞다.")
    return ""


def markdown(case, mv, rec):
    auc = case["auction"]
    lines = [f"## {case.get('case_no', '')} — {rec['verdict']}", ""]
    lines.append(f"- 시세: **{eok(mv['value'])}** (신뢰도 {mv['confidence']}, 비교사례 {len(mv['comps'])}건)")
    lines.append(f"- 감정가 {eok(auc.get('appraisal'))} / 최저가 **{eok(rec['min_price'])}** "
                 f"(시세의 {rec['min_price'] / mv['value']:.0%}) / 유찰 {auc.get('failed_count', 0)}회")
    lines.append(f"- 전략: {rec['strategy']} / 수익 상한가 **{eok(rec['max_bid'])}**")
    if rec["pass_reasons"]:
        lines.append("- 패스 이유: " + " / ".join(rec["pass_reasons"]))
    if rec["picks"]:
        b = rec.get("basis_label", "세후")
        if b == "세전":
            lines += ["", "| 안 | 입찰가 | 낙찰확률 | 세전 순이익 | 세후 |", "|---|---|---|---|---|"]
            for name, p in rec["picks"].items():
                lines.append(f"| {name} | {eok(p['bid'])} | {pct(p['prob'])} | {eok(p['profit'])} | {eok(p.get('after_tax'))} |")
        else:
            lines += ["", "| 안 | 입찰가 | 낙찰확률 | 세후 순이익 |", "|---|---|---|---|"]
            for name, p in rec["picks"].items():
                lines.append(f"| {name} | {eok(p['bid'])} | {pct(p['prob'])} | {eok(p['profit'])} |")
    nr = rec["next_round"]
    lines.append("")
    lines.append(f"- 이번 회차 유찰 확률 {pct(nr['fail_prob'])} → 유찰 시 다음 최저가 {eok(nr['min_price'])}"
                 + (" — **기다리는 쪽이 기대수익이 더 크다**" if nr["better_to_wait"] else ""))
    if low_prob_note(rec):
        lines.append("- ⚠️ " + low_prob_note(rec))
    r = rec["rights"]
    if r["red_flags"]:
        lines.append("- 🔴 " + " / ".join(r["red_flags"]))
    if r["yellow_flags"]:
        lines.append("- 🟡 " + " / ".join(r["yellow_flags"]))
    lines.append(f"- 낙찰확률 근거: {rec['win_model']}")
    return "\n".join(lines)


CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e3e3e0;--accent:#2b5bd7;
--good:#1f8a4c;--warn:#b7791f;--bad:#c53030}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1d1d20;--ink:#ececee;--muted:#9a9aa2;
--line:#2e2e33;--accent:#7aa2ff;--good:#4cc38a;--warn:#e0b45a;--bad:#ff7b7b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:920px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 10px}
.sub{color:var(--muted);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}
.verdict{font-size:20px;font-weight:700}.pass{color:var(--bad)}.go{color:var(--good)}.wait{color:var(--warn)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(150px,100%),1fr));gap:10px}
.kpi .l{color:var(--muted);font-size:12px}.kpi .v{font-size:18px;font-weight:700}
.picks{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(200px,100%),1fr));gap:10px}
.pick{border:1px solid var(--line);border-radius:10px;padding:12px}.pick.main{border:2px solid var(--accent)}
.pick .bid{font-size:20px;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--line);
text-align:right}th:first-child,td:first-child{text-align:left}th{color:var(--muted);font-weight:600}
.scroll{overflow-x:auto}ul{margin:6px 0;padding-left:20px}.flag-red{color:var(--bad)}.flag-y{color:var(--warn)}
svg text{fill:var(--muted);font-size:13px}
.note{color:var(--warn);margin-top:8px}
"""


def _chart(curve, pick_bid):
    if len(curve) < 2:
        return ""
    w, h, pad = 860, 220, 40
    bids = [c["bid"] for c in curve]
    lo, hi = bids[0], bids[-1]
    ev_max = max(max(c["ev"] for c in curve), 1)
    x = lambda b: pad + (b - lo) / (hi - lo) * (w - 2 * pad)
    yp = lambda p: h - pad + 10 - p * (h - 2 * pad)
    ye = lambda e: h - pad + 10 - max(e, 0) / ev_max * (h - 2 * pad)
    prob = " ".join(f"{x(c['bid']):.1f},{yp(c['prob']):.1f}" for c in curve)
    ev = " ".join(f"{x(c['bid']):.1f},{ye(c['ev']):.1f}" for c in curve)
    best = max(curve, key=lambda c: c["ev"])
    return f"""<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="입찰가별 낙찰확률과 기대수익">
<polyline points="{prob}" fill="none" stroke="var(--accent)" stroke-width="2"/>
<polyline points="{ev}" fill="none" stroke="var(--good)" stroke-width="2"/>
<line x1="{x(best['bid']):.1f}" x2="{x(best['bid']):.1f}" y1="{pad - 20}" y2="{h - pad + 10}" stroke="var(--warn)" stroke-dasharray="4 4"/>
<text x="{pad}" y="{h - 8}">{eok(lo)}</text><text x="{w - pad}" y="{h - 8}" text-anchor="end">{eok(hi)}</text>
<text x="{x(best['bid']) + (-4 if x(best['bid']) > w / 2 else 4):.1f}" y="{pad - 8}" text-anchor="{'end' if x(best['bid']) > w / 2 else 'start'}">추천 {eok(pick_bid or best['bid'])}</text>
<line x1="{pad}" x2="{w - pad}" y1="{h - pad + 10}" y2="{h - pad + 10}" stroke="var(--line)"/>
<text x="{pad}" y="14">━ 낙찰확률(파랑, 위끝 100%)  ━ 기대수익(초록)</text></svg>"""


def html_report(case, mv, rec, cfg):
    e = html.escape
    prop, auc = case["property"], case["auction"]
    v = rec["verdict"]
    vcls = "pass" if v == "패스" else "wait" if "대기" in v or "확인" in v else "go"

    picks = ""
    for name, p in rec["picks"].items():
        picks += (f'<div class="pick{" main" if name == "추천" else ""}"><div class="sub">{name}</div>'
                  f'<div class="bid">{eok(p["bid"])}</div><div>낙찰확률 {pct(p["prob"])} · {rec.get("basis_label", "세후")} 순이익 {eok(p["profit"])}'
                  + (f' (세후 {eok(p.get("after_tax"))})' if rec.get("basis_label") == "세전" else "") + '</div>'
                  f'<div class="sub">입찰표: {p["bid"]:,}원 ({korean_amount(p["bid"])})</div></div>')

    comps = "".join(
        f"<tr><td>{e(c['date'])}</td><td>{e(c['apt_name'])}</td><td>{c['area']:.1f}</td><td>{c['floor'] or '-'}</td>"
        f"<td>{eok(c['price'])}</td><td>{eok(c['adjusted'])}</td><td>{e(c['tier'])}</td></tr>"
        for c in mv["comps"][:15])
    checks = " · ".join(f"{k} {eok(val)}" for k, val in mv.get("checks", {}).items())

    scen = ""
    for s in rec["scenarios"]:
        a = s["at_max"] or s["at_min"]
        scen += (f"<tr><td>{s['hold_years']:g}년</td><td>{eok(s['max_bid'])}</td>"
                 f"<td>{eok(s['at_min'].get('net_pretax'))} / {eok(s['at_min']['net_profit'])}</td><td>{e(a['cgt_reason'])}</td>"
                 f"<td>{eok(s['at_min']['cash_needed'])}</td></tr>")

    main_bid = rec["picks"].get("추천", {}).get("bid") or rec["min_price"]
    best_s = max(rec["scenarios"], key=lambda s: s["max_bid"] or 0)
    from .profit import Deal
    detail = Deal(case, cfg, mv["value"], rec["rental"]["rent"]).flip(main_bid, best_s["hold_years"])
    cost_rows = "".join(f"<tr><td>{e(k)}</td><td>{won(val)}</td></tr>" for k, val in detail["costs"].items())
    cost_rows += (f"<tr><td><b>매도가</b></td><td><b>{won(detail['sale_price'])}</b></td></tr>"
                  f"<tr><td>보유 중 월세 수입</td><td>{won(detail['rent_income'])}</td></tr>"
                  f"<tr><td><b>세전 순이익</b></td><td><b>{won(detail['net_pretax'])}</b></td></tr>"
                  f"<tr><td><b>세후 순이익</b></td><td><b>{won(detail['net_profit'])}</b></td></tr>"
                  f"<tr><td>대출</td><td>{won(detail['loan'])}</td></tr>"
                  f"<tr><td>실투자금</td><td>{won(detail['cash_needed'])}</td></tr>")

    r = rec["rights"]
    base = r["base_right"]
    tenant_rows = "".join(
        f"<tr><td>{e(t.get('name', ''))}</td><td>{e(t.get('move_in') or '-')}</td><td>{e(t.get('fixed_date') or '-')}</td>"
        f"<td>{won(t.get('deposit'))}</td><td>{'있음' if t['opposable'] else '없음'}</td>"
        f"<td>{won(t['dividend'])}</td><td>{won(t['assumed'])}</td></tr>" for t in r["tenants"])
    flags = "".join(f'<li class="flag-red">🔴 {e(f)}</li>' for f in r["red_flags"])
    flags += "".join(f'<li class="flag-y">🟡 {e(f)}</li>' for f in r["yellow_flags"])

    rent = rec["rental"]
    rent_html = "<p class='sub'>월세 시세 자료가 없어 임대수익 분석을 건너뛰었다.</p>"
    if rent["rent"]:
        rr = rent["at_max"] or rent["at_min"]
        rent_html = (f"<p>월세 시세 보증금 {eok(rent['rent']['deposit'])} / 월 {eok(rent['rent']['monthly_rent'])} "
                     f"({e(rent['rent']['source'])}, {rent['rent']['count']}건)</p>"
                     f"<p>목표 수익률 {pct(cfg['strategy']['target_rent_yield'])} 기준 상한가 <b>{eok(rent['max_bid'])}</b>"
                     f" · 그 가격에서 실투자금 {eok(rr['cash_needed'])}, 연 순수익 {eok(rr['annual_net'])}, "
                     f"수익률 {pct(rr['yield']) if rr['yield'] is not None else '무피(실투자금 0 이하)'}</p>")

    nr = rec["next_round"]
    nxt = (f"이번 회차 유찰 확률 <b>{pct(nr['fail_prob'])}</b>. 유찰되면 다음 최저가 {eok(nr['min_price'])}"
           + (f", 그때 추천가 {eok(nr['best']['bid'])} (낙찰확률 {pct(nr['best']['prob'])})" if nr["best"] else "")
           + (". <b>기다리는 쪽의 기대수익이 더 크다.</b>" if nr["better_to_wait"] else ". 이번 회차 입찰이 기대수익이 더 크다."))

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(case.get('case_no', '경매 분석'))} 입찰가 분석</title>
<style>{CSS}</style></head><body><main>
<h1>{e(case.get('case_no', ''))} {e(prop.get('apt_name', ''))}</h1>
<div class="sub">{e(case.get('court', ''))} · {e(prop.get('address', ''))} · 전용 {prop['exclusive_area']}㎡ · {prop.get('floor', '-')}층
 · 매각기일 {e(auc.get('sale_date', '-'))} · 기준일 {e(cfg['basis_date'])}{' · 조정대상지역' if rec['regulated'] else ''}</div>

<div class="card"><div class="verdict {vcls}">{e(v)}</div>
{''.join(f'<div>{e(x)}</div>' for x in rec['pass_reasons'])}
<div class="grid" style="margin-top:12px">
<div class="kpi"><div class="l">추정 시세 (신뢰도 {e(mv['confidence'])})</div><div class="v">{eok(mv['value'])}</div></div>
<div class="kpi"><div class="l">감정가</div><div class="v">{eok(auc.get('appraisal'))}</div></div>
<div class="kpi"><div class="l">최저가 (유찰 {auc.get('failed_count', 0)}회)</div><div class="v">{eok(rec['min_price'])}</div></div>
<div class="kpi"><div class="l">수익 상한가 · {e(rec['strategy'])}</div><div class="v">{eok(rec['max_bid'])}</div></div>
<div class="kpi"><div class="l">입찰보증금</div><div class="v">{eok(rec['deposit'])}</div></div>
</div></div>

<h2>추천 입찰가</h2>
<div class="picks">{picks or '<p>추천할 수 있는 입찰가가 없다.</p>'}</div>
{f'<div class="note">{e(low_prob_note(rec))}</div>' if low_prob_note(rec) else ''}
<div class="card">{_chart(rec['curve'], rec['picks'].get('추천', {}).get('bid'))}<div class="sub">{e(rec['win_model'])}</div></div>
<div class="card">{nxt}</div>

<h2>보유기간별 비교 (매도차익)</h2>
<div class="card scroll"><table><tr><th>보유</th><th>수익 상한가</th><th>최저가 낙찰 시 순이익 (세전 / 세후)</th><th>세금</th><th>최저가 낙찰 시 실투자금</th></tr>{scen}</table>
<div class="sub">목표 {rec.get('basis_label', '세후')} 순이익 {eok(cfg['strategy']['target_net_profit'])} · 취득 후 {cfg['investor']['houses_owned'] + 1}주택 기준
 · {'부동산매매사업자 (종합소득세)' if cfg['investor'].get('seller_type') == 'business' else '개인 양도 (양도소득세)'} · 대출금리 {cfg['loan']['rate']:.1%}</div></div>

<h2>추천가 기준 손익 상세 ({best_s['hold_years']:g}년 보유 후 매도)</h2>
<div class="card scroll"><table>{cost_rows}</table>
<div class="sub">컨디션 {e(rec['condition_grade'])}등급 가정 수리비 {eok(rec['repair'])}</div></div>

<h2>임대수익 (차선 전략)</h2><div class="card">{rent_html}</div>

<h2>권리분석</h2>
<div class="card">
<div>말소기준권리: {e(base['type'] + ' ' + base['date'] + ' ' + (base.get('holder') or '')) if base else '확인 안 됨'}</div>
<div>인수금액 합계: <b>{won(r['assumed_amount'])}</b> · 명도: {e(EVICTION_LABEL.get(r['eviction_type'], r['eviction_type']))}</div>
{'<div class="scroll"><table><tr><th>임차인</th><th>전입</th><th>확정일자</th><th>보증금</th><th>대항력</th><th>예상배당</th><th>인수</th></tr>' + tenant_rows + '</table></div>' if tenant_rows else ''}
<ul>{flags or '<li>위험 신호 없음</li>'}</ul>
{'<div class="flag-red">전문가(법무사) 확인 후 입찰할 것</div>' if r['needs_expert'] else ''}
</div>

<h2>시세 근거</h2>
<div class="card scroll"><div class="sub">{e(checks)}</div>
<table><tr><th>계약일</th><th>단지</th><th>전용㎡</th><th>층</th><th>거래가</th><th>보정가</th><th>구분</th></tr>{comps}</table>
{''.join(f'<div class="sub">· {e(n)}</div>' for n in mv['notes'])}</div>

<h2>입찰 전 체크</h2>
<div class="card"><ul>
<li>사건번호 {e(case.get('case_no', ''))} / 물건번호 {e(str(case.get('item_no', 1)))} 확인</li>
<li>입찰보증금 {won(rec['deposit'])} (최저가의 {'20' if auc.get('resale') else '10'}%) 수표 1장</li>
<li>입찰가 자릿수를 한 번 더 확인 (0 하나 더 쓰면 보증금 몰수)</li>
<li>매각기일 아침 법원 게시판에서 취하·변경 여부 확인</li>
</ul><div class="sub">이 리포트는 판단 보조용이며 투자·법률 자문이 아니다. 세율·대출 규제는 기준일 이후 바뀌었을 수 있다.</div></div>
</main></body></html>"""
