#!/usr/bin/env python3
"""상세페이지 HTML을 쿠팡 업로드용 이미지로 뽑는다.

  check                       : 필요한 프로그램 확인
  run page.html --out out/    : 전체 1장(full.png) + 섹션별 JPG 조각

조각은 <section> 단위로 자른다. 한 섹션이 --max-height보다 길면 그 안에서 다시 나눈다.
브라우저는 파이썬 playwright가 있으면 그걸 쓰고, 없으면 node playwright를 쓴다.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

NODE_JS = r"""
const { chromium } = require('playwright');
(async () => {
  const [html, png, boxes, width, scale] = process.argv.slice(2);
  const opts = {};
  if (process.env.CHROMIUM_PATH) opts.executablePath = process.env.CHROMIUM_PATH;
  const browser = await chromium.launch(opts);
  const page = await browser.newPage({ viewport: { width: +width, height: 1200 }, deviceScaleFactor: +scale });
  await page.goto('file://' + html, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
  const b = await page.evaluate(() => [...document.querySelectorAll('section')].map((s, i) => {
    const r = s.getBoundingClientRect();
    return { id: s.id || ('s' + (i + 1)), y: r.top + window.scrollY, h: r.height };
  }));
  require('fs').writeFileSync(boxes, JSON.stringify(b));
  await page.screenshot({ path: png, fullPage: true });
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
"""


def has_py_playwright():
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


def node_playwright_dir():
    node = shutil.which("node")
    if not node:
        return None
    try:
        root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        root = ""
    for d in (root, os.path.join(os.getcwd(), "node_modules")):
        if d and os.path.isdir(os.path.join(d, "playwright")):
            return d
    return None


def chromium_path():
    p = os.environ.get("CHROMIUM_PATH")
    if p:
        return p
    p = "/opt/pw-browsers/chromium"
    return p if os.path.exists(p) else None


def check():
    missing = []
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append("Pillow  (설치: python3 -m pip install Pillow)")
    if not has_py_playwright() and not node_playwright_dir():
        missing.append("playwright  (설치: python3 -m pip install playwright && python3 -m playwright install chromium)")
    if missing:
        print("MISSING: " + " / ".join(missing))
        sys.exit(1)
    print("OK (브라우저: %s)" % ("python playwright" if has_py_playwright() else "node playwright"))


def shoot_python(html, png, width, scale):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        kw = {}
        if chromium_path():
            kw["executable_path"] = chromium_path()
        browser = p.chromium.launch(**kw)
        page = browser.new_page(viewport={"width": width, "height": 1200}, device_scale_factor=scale)
        page.goto("file://" + html, wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(400)
        boxes = page.evaluate("""() => [...document.querySelectorAll('section')].map((s, i) => {
            const r = s.getBoundingClientRect();
            return { id: s.id || ('s' + (i + 1)), y: r.top + window.scrollY, h: r.height };
        })""")
        page.screenshot(path=png, full_page=True)
        browser.close()
    return boxes


def shoot_node(html, png, width, scale):
    mod_dir = node_playwright_dir()
    with tempfile.TemporaryDirectory() as td:
        js = os.path.join(td, "shoot.js")
        boxes_path = os.path.join(td, "boxes.json")
        with open(js, "w") as f:
            f.write(NODE_JS)
        env = dict(os.environ, NODE_PATH=mod_dir)
        if chromium_path():
            env["CHROMIUM_PATH"] = chromium_path()
        subprocess.run(["node", js, html, png, boxes_path, str(width), str(scale)], check=True, env=env)
        with open(boxes_path) as f:
            return json.load(f)


def run(a):
    from PIL import Image
    html = os.path.abspath(a.html)
    os.makedirs(a.out, exist_ok=True)
    full = os.path.join(a.out, "full.png")
    shoot = shoot_python if has_py_playwright() else shoot_node
    boxes = shoot(html, full, a.width, a.scale)

    img = Image.open(full).convert("RGB")
    if a.scale != 1:  # 레티나 배율로 찍고 업로드 폭으로 줄여 글자를 선명하게
        img = img.resize((a.width, round(img.height / a.scale)), Image.LANCZOS)
        img.save(full)
    slice_dir = os.path.join(a.out, "slices")
    if os.path.isdir(slice_dir):
        shutil.rmtree(slice_dir)
    os.makedirs(slice_dir)

    cuts = []
    for b in boxes:
        top, bottom = round(b["y"]), round(b["y"] + b["h"])
        if bottom - top < 2:
            continue
        parts = max(1, -(-(bottom - top) // a.max_height))
        step = -(-(bottom - top) // parts)
        for k in range(parts):
            y0 = top + k * step
            y1 = min(bottom, y0 + step)
            cuts.append((b["id"] + ("" if parts == 1 else "_%d" % (k + 1)), y0, y1))

    listing = []
    for n, (name, y0, y1) in enumerate(cuts, 1):
        path = os.path.join(slice_dir, "%02d_%s.jpg" % (n, name))
        img.crop((0, y0, a.width, min(y1, img.height))).save(path, "JPEG", quality=a.quality, optimize=True)
        kb = os.path.getsize(path) // 1024
        listing.append({"file": path, "height": y1 - y0, "kb": kb})

    with open(os.path.join(a.out, "slices.json"), "w", encoding="utf-8") as f:
        json.dump(listing, f, ensure_ascii=False, indent=2)
    print("OK 전체 %dx%d -> %s" % (img.width, img.height, full))
    print("조각 %d개 -> %s" % (len(listing), slice_dir))
    big = [x for x in listing if x["kb"] > a.warn_kb]
    if big:
        print("WARN_SIZE: %s" % ", ".join(os.path.basename(x["file"]) for x in big))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    r = sub.add_parser("run")
    r.add_argument("html")
    r.add_argument("--out", required=True)
    r.add_argument("--width", type=int, default=860)
    r.add_argument("--scale", type=float, default=2)
    r.add_argument("--max-height", type=int, default=2000)
    r.add_argument("--quality", type=int, default=90)
    r.add_argument("--warn-kb", type=int, default=3000)
    a = ap.parse_args()
    if a.cmd == "check":
        check()
    else:
        run(a)


if __name__ == "__main__":
    main()
