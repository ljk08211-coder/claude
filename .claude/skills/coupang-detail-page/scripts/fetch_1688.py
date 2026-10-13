#!/usr/bin/env python3
"""1688 상품 페이지에서 제목, 옵션, 속성, 대표/상세 이미지를 모은다.

1688은 로그인 벽과 슬라이더 캡차가 잦아서 직접 접속이 자주 막힌다.
그래서 세 가지 입력을 받는다.

  run <URL>            : 직접 접속 시도 (막히면 BLOCKED를 출력하고 끝)
  run --html <파일>     : 브라우저에서 "다른 이름으로 저장"한 HTML을 분석
  run --html <파일> --url <URL> : 저장한 HTML + 원래 링크(기록용)

결과: <out>/source.json, <out>/images/main_*.jpg, <out>/images/detail_*.jpg
중국어 번역은 하지 않는다. 번역은 이미지를 직접 보고 Claude가 한다.
"""
import argparse
import html as htmllib
import json
import os
import re
import sys
import time
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
IMG_RE = re.compile(
    r'(?:https?:)?//(?:cbu01|img|gw|gd\d)\.alicdn\.com/[^"\'\s<>\\)]+?\.(?:jpg|jpeg|png|webp)',
    re.I)
BLOCK_MARKERS = ("punish", "x5secdata", "nocaptcha", "login.1688.com",
                 "login.taobao.com", "滑动验证", "验证码")


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9,ko;q=0.8",
        "Referer": "https://www.1688.com/",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
    for enc in (charset, "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def looks_blocked(text):
    low = text[:20000].lower()
    return len(text) < 3000 or any(m.lower() in low for m in BLOCK_MARKERS)


def clean_img(url):
    url = url.replace("\\/", "/")
    if url.startswith("//"):
        url = "https:" + url
    # 썸네일 접미사(_60x60.jpg, .jpg_.webp 등)를 떼고 원본을 받는다
    url = re.sub(r"(\.(?:jpg|jpeg|png))_.*$", r"\1", url, flags=re.I)
    url = re.sub(r"\.\d+x\d+(\.(?:jpg|jpeg|png))$", r"\1", url, flags=re.I)
    url = re.sub(r"\.(?:search|summ|\d+x\d+xz?)\.jpg$", "", url, flags=re.I)
    return url


def seller_of(url):
    m = re.search(r"!!(\d+)-\d+-cib", url)
    return m.group(1) if m else None


def uniq(seq):
    seen, out = set(), []
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def json_field(text, key):
    m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % re.escape(key), text)
    if not m:
        return None
    try:
        return json.loads('"%s"' % m.group(1))
    except json.JSONDecodeError:
        return m.group(1)


def parse(text):
    data = {}
    t = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
    data["title"] = htmllib.unescape(t.group(1)).strip() if t else None
    data["subject"] = json_field(text, "subject") or json_field(text, "offerTitle")
    data["price_text"] = json_field(text, "priceDisplay") or json_field(text, "price")
    data["unit"] = json_field(text, "unit")
    data["detail_url"] = json_field(text, "detailUrl")

    # 속성: {"name":"材质","value":"不锈钢"} 형태가 흔하다
    attrs = []
    # {"name":"材质","value":"不锈钢"} 또는 {"fid":..,"name":..,"outputType":0,"value":..} 형태
    for m in re.finditer(
            r'\{[^{}]*?"name"\s*:\s*"((?:[^"\\]|\\.)*)"[^{}]*?"value"\s*:\s*"((?:[^"\\]|\\.)*)"', text):
        try:
            attrs.append([json.loads('"%s"' % m.group(1)), json.loads('"%s"' % m.group(2))])
        except json.JSONDecodeError:
            pass
    data["attributes"] = uniq([tuple(a) for a in attrs])[:60]

    # 옵션(SKU) 이름: "skuProps" 안의 "name"/"value" 묶음. 형식이 자주 바뀌어 넓게 잡는다
    sku = []
    for m in re.finditer(r'"skuProps"\s*:\s*(\[.*?\])\s*,\s*"', text, re.S):
        try:
            for prop in json.loads(m.group(1)):
                vals = [v.get("name") for v in prop.get("value", []) if isinstance(v, dict)]
                sku.append({"prop": prop.get("prop"), "values": vals})
        except (json.JSONDecodeError, AttributeError):
            pass
    # 옵션별 공급가
    prices = {}
    m = re.search(r'"skuInfoMap"\s*:\s*\{', text)
    if m:
        for sm in re.finditer(r'"((?:[^"\\]|\\.)*)"\s*:\s*\{[^{}]*?"price"\s*:\s*"([\d.]+)"', text[m.end() - 1:m.end() + 20000]):
            prices.setdefault(sm.group(1), sm.group(2))
    data["sku_prices"] = prices

    # 포장 무게·치수 표 (HTML 표)
    pack = []
    pm = re.search(r'class="offer-pack-info-list".*?<table[^>]*>(.*?)</table>', text, re.S)
    if pm:
        for row in re.findall(r"<tr>(.*?)</tr>", pm.group(1), re.S):
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)]
            if cells:
                pack.append(cells)
    data["pack_table"] = pack

    # 구매자 리뷰 키워드 (예: 质量好 141)
    data["review_tags"] = uniq([(t.group(2), int(t.group(1))) for t in re.finditer(
        r'\{"count"\s*:\s*(\d+)\s*,\s*"name"\s*:\s*"([^"]+)"\s*,\s*"type"\s*:\s*"impr"', text)])[:20]

    data["sku"] = [dict(t) for t in uniq([tuple((k, tuple(v) if isinstance(v, list) else v) for k, v in d.items()) for d in sku])]
    for d in data["sku"]:
        d["values"] = list(d["values"])

    imgs = [clean_img(u) for u in IMG_RE.findall(text.replace("\\/", "/"))]
    # 상품 사진은 img/ibank 경로에 있다. imgextra 쪽은 대부분 아이콘·배너라 뺀다
    imgs = [u for u in uniq(imgs) if "/img/ibank/" in u]
    # 추천 상품 사진이 섞이므로 가장 많이 나온 판매자 ID의 사진만 남긴다
    sellers = [seller_of(u) for u in imgs if seller_of(u) and seller_of(u) != "0"]
    if sellers:
        top = max(set(sellers), key=sellers.count)
        imgs = [u for u in imgs if seller_of(u) in (top, "0")]
    data["main_images"] = imgs
    return data


def parse_detail(text):
    # desc 응답은 var offer_details={"content":"<img src=...>"} 형태가 흔하다
    content = json_field(text, "content") or text
    imgs = [clean_img(u) for u in IMG_RE.findall(content.replace("\\/", "/"))]
    words = re.sub(r"<[^>]+>", " ", htmllib.unescape(content))
    words = re.sub(r"\s+", " ", words).strip()
    return uniq(imgs), words[:5000]


def too_small(path, min_side=300):
    """상세 영역에 섞여 들어온 아이콘·배너(가로세로 300px 미만)는 버린다."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return min(im.size) < min_side
    except Exception:  # noqa: BLE001 - Pillow가 없거나 깨진 파일이면 그대로 둔다
        return False


def download(urls, folder, prefix, limit):
    os.makedirs(folder, exist_ok=True)
    saved = []
    for i, u in enumerate(urls[:limit], 1):
        ext = os.path.splitext(u)[1].lower() or ".jpg"
        path = os.path.join(folder, "%s_%02d%s" % (prefix, i, ext))
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA, "Referer": "https://detail.1688.com/"})
            with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
                f.write(r.read())
            if too_small(path):
                os.remove(path)
                continue
            saved.append({"file": path, "url": u})
        except Exception as e:  # noqa: BLE001 - 한 장 실패는 건너뛴다
            saved.append({"file": None, "url": u, "error": str(e)[:120]})
        time.sleep(0.3)
    return saved


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("url", nargs="?")
    r.add_argument("--html", help="브라우저에서 저장한 1688 상품 페이지 HTML")
    r.add_argument("--url", dest="url_opt", help="--html과 함께 쓸 원래 링크(기록용)")
    r.add_argument("--out", required=True)
    r.add_argument("--max-main", type=int, default=12)
    r.add_argument("--max-detail", type=int, default=40)
    r.add_argument("--no-download", action="store_true")
    a = ap.parse_args()

    url = a.url or a.url_opt
    if not url and not a.html:
        sys.exit("URL 또는 --html 중 하나는 필요합니다")
    os.makedirs(a.out, exist_ok=True)

    if a.html:
        with open(a.html, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8", "replace")
        source = "saved_html"
    else:
        try:
            text = fetch(url)
        except Exception as e:  # noqa: BLE001
            print("BLOCKED: 접속 실패 (%s)" % str(e)[:150])
            sys.exit(2)
        if looks_blocked(text):
            print("BLOCKED: 로그인/캡차 페이지가 돌아왔습니다")
            sys.exit(2)
        source = "direct"

    data = parse(text)
    data.update({"source": source, "url": url})

    detail_imgs, detail_text = [], ""
    if data.get("detail_url"):
        try:
            detail_imgs, detail_text = parse_detail(fetch(data["detail_url"]))
        except Exception as e:  # noqa: BLE001
            data["detail_error"] = str(e)[:150]
    page_imgs = data["main_images"]
    if detail_imgs:
        # 저장한 HTML에는 상세 이미지도 펼쳐져 있으니 대표 이미지에서 뺀다
        data["main_images"] = [u for u in page_imgs if u not in detail_imgs][:a.max_main]
    else:
        detail_imgs = page_imgs[a.max_main:]
        data["main_images"] = page_imgs[:a.max_main]
    data["detail_images"] = detail_imgs
    data["detail_text"] = detail_text

    if not a.no_download:
        img_dir = os.path.join(a.out, "images")
        data["main_saved"] = download(data["main_images"], img_dir, "main", a.max_main)
        data["detail_saved"] = download(data["detail_images"], img_dir, "detail", a.max_detail)

    with open(os.path.join(a.out, "source.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    ok_main = sum(1 for s in data.get("main_saved", []) if s.get("file"))
    ok_detail = sum(1 for s in data.get("detail_saved", []) if s.get("file"))
    print("OK source=%s" % source)
    print("제목: %s" % (data.get("subject") or data.get("title")))
    print("속성 %d개, 옵션 %d묶음, 옵션가격 %d개, 포장표 %d줄, 리뷰키워드 %d개" % (
        len(data["attributes"]), len(data["sku"]), len(data.get("sku_prices", {})),
        len(data.get("pack_table", [])), len(data.get("review_tags", []))))
    print("대표 이미지 %d장, 상세 이미지 %d장 저장 -> %s" % (ok_main, ok_detail, a.out))
    if not a.no_download and ok_main + ok_detail == 0:
        print("NO_IMAGES: 이미지를 찾지 못했습니다. 상세 영역 스크린샷을 받아 진행하세요")


if __name__ == "__main__":
    main()
