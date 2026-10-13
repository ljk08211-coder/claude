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
    return url


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
    for m in re.finditer(
            r'\{"name"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"value"\s*:\s*"((?:[^"\\]|\\.)*)"', text):
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
    data["sku"] = sku

    imgs = [clean_img(u) for u in IMG_RE.findall(text.replace("\\/", "/"))]
    imgs = [u for u in uniq(imgs) if "ibank" in u or "imgextra" in u]
    data["main_images"] = imgs
    return data


def parse_detail(text):
    # desc 응답은 var offer_details={"content":"<img src=...>"} 형태가 흔하다
    content = json_field(text, "content") or text
    imgs = [clean_img(u) for u in IMG_RE.findall(content.replace("\\/", "/"))]
    words = re.sub(r"<[^>]+>", " ", htmllib.unescape(content))
    words = re.sub(r"\s+", " ", words).strip()
    return uniq(imgs), words[:5000]


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
    if not detail_imgs:
        # 저장한 HTML에는 상세 영역이 이미 펼쳐져 있는 경우가 많다
        detail_imgs = [u for u in data["main_images"][a.max_main:]]
        data["main_images"] = data["main_images"][:a.max_main]
    data["detail_images"] = [u for u in detail_imgs if u not in data["main_images"]]
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
    print("속성 %d개, 옵션 %d묶음" % (len(data["attributes"]), len(data["sku"])))
    print("대표 이미지 %d장, 상세 이미지 %d장 저장 -> %s" % (ok_main, ok_detail, a.out))
    if not a.no_download and ok_main + ok_detail == 0:
        print("NO_IMAGES: 이미지를 찾지 못했습니다. 상세 영역 스크린샷을 받아 진행하세요")


if __name__ == "__main__":
    main()
