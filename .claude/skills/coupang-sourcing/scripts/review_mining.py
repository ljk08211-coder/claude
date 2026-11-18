#!/usr/bin/env python3
"""쿠팡 리뷰(JSON)에서 불만·칭찬 유형 빈도를 세서 마크다운으로 출력한다.

사용법:
    python3 review_mining.py top3_reviews.json [--samples 3]

1~3점 리뷰 → 불만 유형, 4~5점 리뷰 → 구매 이유를 키워드 사전으로 분류한다.
분류는 거칠다. 결과표를 본 뒤 반드시 대표 원문을 직접 읽고 판단한다.
상품별(productId/url)로 나눠 보여주고, 전체 합계도 낸다.
"""
import argparse
import json
from collections import Counter, defaultdict

COMPLAINTS = {
    "품질·내구성": ["부러", "깨졌", "깨짐", "금방", "약해", "약함", "찢어", "고장", "망가", "헐거", "내구", "얇아", "얇고", "녹슬", "녹이", "벗겨", "갈라"],
    "불량·마감": ["불량", "마감", "흠집", "기스", "스크래치", "찍힘", "이물", "실밥", "본드"],
    "사이즈·규격": ["작아", "작네", "작음", "커요", "크네", "너무 커", "사이즈", "안 맞", "안맞", "규격", "생각보다 작", "생각보다 크"],
    "냄새·소재": ["냄새", "화학", "플라스틱 냄", "실리콘 냄", "독한", "고무 냄"],
    "새는 문제·밀폐": ["새요", "샌다", "새서", "누수", "밀폐", "흘러"],
    "사용 불편": ["불편", "어렵", "힘들", "뻑뻑", "안 빠", "안빠", "잘 안", "설명서"],
    "세척·관리": ["세척", "씻기", "닦기", "곰팡", "물때", "얼룩"],
    "배송·포장": ["배송", "포장", "파손", "박스", "늦게", "찌그러"],
    "구성품 누락·오배송": ["누락", "빠져", "없어요", "오배송", "다른 제품", "개수가"],
    "사진과 다름": ["사진과", "사진이랑", "실물", "색상이", "색이 달", "상세페이지와"],
    "가성비·가격": ["비싸", "가격 대비", "가격대비", "돈 아깝", "돈아깝", "이 가격"],
}

PRAISES = {
    "튼튼함·품질": ["튼튼", "견고", "탄탄", "품질 좋", "퀄리티", "고급", "묵직", "마감 좋", "마감이 좋"],
    "가성비": ["가성비", "저렴", "싸게", "가격 대비 좋", "이 가격에"],
    "디자인·예쁨": ["예뻐", "이뻐", "예쁘", "이쁘", "디자인", "감성", "고급스"],
    "사용 편함": ["편해", "편하", "간편", "쉽게", "쉬워", "편리"],
    "사이즈 적당": ["딱 좋", "적당", "사이즈 좋", "크기 좋"],
    "세척 쉬움": ["세척 쉽", "세척이 쉽", "씻기 편", "닦기 편"],
    "배송 빠름": ["빠른 배송", "배송 빠", "빨리 왔", "로켓"],
    "선물용": ["선물", "선물용", "선물했"],
    "재구매·추천": ["재구매", "또 샀", "추가 구매", "추천", "강추"],
}

ALIASES = {
    "text": ["content", "text", "reviewText", "review", "body", "comment", "headline"],
    "title": ["title", "headline", "summary"],
    "rating": ["rating", "stars", "score", "ratingValue", "star"],
    "product": ["productId", "productUrl", "url", "productName", "itemId"],
    "date": ["date", "createdAt", "reviewDate", "writtenAt"],
}


def pick(it, key):
    for a in ALIASES[key]:
        v = it.get(a)
        if v not in (None, ""):
            return v
    return None


def load(path):
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return []
    if text[0] == "[":
        data = json.loads(text)
    elif text[0] == "{":
        obj = json.loads(text)
        data = next((obj[k] for k in ("items", "reviews", "data", "results") if isinstance(obj.get(k), list)), [obj])
    else:
        data = [json.loads(l) for l in text.splitlines() if l.strip()]
    # 일부 Actor는 상품 1행 안에 reviews 배열을 넣는다 → 펼친다
    flat = []
    for it in data:
        if isinstance(it.get("reviews"), list):
            for rv in it["reviews"]:
                rv = dict(rv)
                rv.setdefault("productId", it.get("productId") or it.get("url"))
                flat.append(rv)
        else:
            flat.append(it)
    return flat


def rating_of(it):
    v = pick(it, "rating")
    try:
        return float(str(v).split("/")[0])
    except (TypeError, ValueError):
        return None


def classify(text, dictionary):
    hits = []
    for label, words in dictionary.items():
        if any(w in text for w in words):
            hits.append(label)
    return hits


def table(counter, base, samples, title, n_samples):
    out = [f"#### {title} (대상 리뷰 {base}개)", ""]
    if not base or not counter:
        out.append("해당 리뷰 없음\n")
        return out
    out.append("| 유형 | 언급 수 | 비율 | 대표 원문 |")
    out.append("|---|---|---|---|")
    for label, cnt in counter.most_common():
        ex = " / ".join(f"“{s}”" for s in samples[label][:n_samples])
        out.append(f"| {label} | {cnt} | {cnt / base:.0%} | {ex} |")
    out.append("")
    return out


def short(text, n=70):
    t = " ".join(text.split())
    return (t[:n] + "…") if len(t) > n else t


def analyze(reviews, n_samples):
    neg = [r for r in reviews if r["rating"] is not None and r["rating"] <= 3]
    pos = [r for r in reviews if r["rating"] is not None and r["rating"] >= 4]
    c_neg, c_pos = Counter(), Counter()
    s_neg, s_pos = defaultdict(list), defaultdict(list)
    for r in neg:
        for lab in classify(r["text"], COMPLAINTS):
            c_neg[lab] += 1
            s_neg[lab].append(short(r["text"]).replace("|", "/"))
    for r in pos:
        for lab in classify(r["text"], PRAISES):
            c_pos[lab] += 1
            s_pos[lab].append(short(r["text"]).replace("|", "/"))
    ratings = [r["rating"] for r in reviews if r["rating"] is not None]
    dist = Counter(int(x) for x in ratings)
    out = []
    if ratings:
        out.append(f"- 리뷰 {len(reviews)}개 · 평균 {sum(ratings) / len(ratings):.2f}점 · "
                   + " ".join(f"{k}점 {dist.get(k, 0)}" for k in (5, 4, 3, 2, 1)))
        out.append(f"- 1~3점 비율: {len(neg) / len(ratings):.0%}")
        out.append("")
    out += table(c_neg, len(neg), s_neg, "불만 유형 (1~3점)", n_samples)
    out += table(c_pos, len(pos), s_pos, "구매 이유 (4~5점)", n_samples)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--samples", type=int, default=2, help="유형별 대표 원문 개수")
    args = ap.parse_args()

    raw = load(args.path)
    reviews = []
    for it in raw:
        text = " ".join(str(x) for x in (pick(it, "title"), pick(it, "text")) if x)
        reviews.append({
            "text": text,
            "rating": rating_of(it),
            "product": str(pick(it, "product") or "(상품 미상)"),
        })
    if not reviews:
        raise SystemExit("입력에 리뷰가 없습니다.")

    print("# 리뷰 마이닝\n")
    print("> 키워드 사전 기반 자동 분류라 오차가 있다. 표를 보고 원문을 직접 읽어 확인할 것.\n")
    print("## 전체 합계\n")
    print("\n".join(analyze(reviews, args.samples)))

    by_product = defaultdict(list)
    for r in reviews:
        by_product[r["product"]].append(r)
    if len(by_product) > 1:
        for i, (prod, items) in enumerate(by_product.items(), 1):
            print(f"## 상품 {i}: {prod}\n")
            print("\n".join(analyze(items, 1)))


if __name__ == "__main__":
    main()
