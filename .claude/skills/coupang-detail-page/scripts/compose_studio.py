#!/usr/bin/env python3
"""생성 AI 없이 제품컷을 만든다. Pillow만 사용.

  cutout  제품.jpg --out product_cut.png [--tol 28]
          단색(흰색·회색) 배경 사진의 배경을 모서리부터 지워 누끼 PNG를 만든다.
          배경이 복잡한 사진은 깔끔하게 안 지워진다. 그때는 배경 제거 도구를 쓴다.

  compose product_cut.png --out hero.jpg [--bg 배경.jpg | --color "#f2efe9" --color2 "#d9d3c7"]
          [--size 1720x2300] [--scale 0.62] [--y 0.58] [--no-shadow] [--floor]
          누끼를 배경 위에 올리고 바닥 그림자를 넣어 스튜디오 컷처럼 만든다.
          --bg 에는 캔바 등으로 만든 "제품 없는 배경"을 넣을 수 있다.
"""
import argparse
import sys
from collections import deque

from PIL import Image, ImageDraw, ImageFilter


def hex_rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def cutout(a):
    img = Image.open(a.src).convert("RGBA")
    w, h = img.size
    px = img.load()
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    ref = tuple(sum(c[i] for c in corners) // 4 for i in range(3))
    tol2 = a.tol ** 2 * 3

    def near(c):
        return sum((c[i] - ref[i]) ** 2 for i in range(3)) <= tol2

    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        q.extend([(x, 0), (x, h - 1)])
    for y in range(h):
        q.extend([(0, y), (w - 1, y)])
    while q:
        x, y = q.popleft()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        if not near(px[x, y]):
            continue
        seen[i] = 2
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                q.append((nx, ny))

    mask = Image.new("L", (w, h), 255)
    mp = mask.load()
    for y in range(h):
        row = y * w
        for x in range(w):
            if seen[row + x] == 2:
                mp[x, y] = 0
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
    img.putalpha(mask)
    bbox = mask.point(lambda v: 255 if v > 20 else 0).getbbox()
    if not bbox:
        sys.exit("FAILED: 제품을 찾지 못했습니다 (배경과 제품 색이 너무 비슷함)")
    img.crop(bbox).save(a.out)
    removed = sum(1 for v in seen if v == 2) / (w * h)
    print(f"OK 배경 {removed:.0%} 제거 -> {a.out}")
    if removed < 0.15:
        print("WARN: 지운 배경이 적습니다. 결과를 직접 보고 필요하면 배경 제거 도구를 쓰세요")


def gradient(size, c1, c2):
    w, h = size
    top, bot = hex_rgb(c1), hex_rgb(c2)
    g = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        g.putpixel((0, y), tuple(round(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    return g.resize((w, h))


def compose(a):
    w, h = (int(v) for v in a.size.lower().split("x"))
    if a.bg:
        bg = Image.open(a.bg).convert("RGB")
        r = max(w / bg.width, h / bg.height)
        bg = bg.resize((round(bg.width * r), round(bg.height * r)), Image.LANCZOS)
        left, top = (bg.width - w) // 2, (bg.height - h) // 2
        bg = bg.crop((left, top, left + w, top + h))
    else:
        bg = gradient((w, h), a.color, a.color2 or a.color)

    prod = Image.open(a.src).convert("RGBA")
    r = min(w * a.scale / prod.width, h * a.scale / prod.height)
    prod = prod.resize((round(prod.width * r), round(prod.height * r)), Image.LANCZOS)
    x = (w - prod.width) // 2
    y = round(h * a.y - prod.height / 2)
    base = y + prod.height

    canvas = bg.convert("RGBA")
    if a.floor:
        floor = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(floor).rectangle((0, base - 10, w, h), fill=(0, 0, 0, 18))
        canvas = Image.alpha_composite(canvas, floor.filter(ImageFilter.GaussianBlur(30)))
    if not a.no_shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sw = prod.width * 0.9
        ImageDraw.Draw(sh).ellipse((w / 2 - sw / 2, base - prod.height * 0.04, w / 2 + sw / 2, base + prod.height * 0.05),
                                   fill=(0, 0, 0, 110))
        canvas = Image.alpha_composite(canvas, sh.filter(ImageFilter.GaussianBlur(max(8, prod.width // 25))))
        contact = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        alpha = prod.split()[3].point(lambda v: 90 if v > 128 else 0)
        contact.paste((0, 0, 0, 255), (x, y + 6), alpha)
        canvas = Image.alpha_composite(canvas, contact.filter(ImageFilter.GaussianBlur(6)))
    canvas.alpha_composite(prod, (x, y))
    out = canvas.convert("RGB") if a.out.lower().endswith((".jpg", ".jpeg")) else canvas
    out.save(a.out, quality=92)
    print(f"OK {w}x{h} -> {a.out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cutout")
    c.add_argument("src")
    c.add_argument("--out", required=True)
    c.add_argument("--tol", type=int, default=28, help="배경 색 허용 범위. 그림자까지 지우려면 올린다")
    m = sub.add_parser("compose")
    m.add_argument("src")
    m.add_argument("--out", required=True)
    m.add_argument("--bg")
    m.add_argument("--color", default="#f3f1ec")
    m.add_argument("--color2", default="#dcd7cd")
    m.add_argument("--size", default="1720x1720")
    m.add_argument("--scale", type=float, default=0.62, help="캔버스 대비 제품 크기")
    m.add_argument("--y", type=float, default=0.55, help="제품 중심 세로 위치(0~1)")
    m.add_argument("--no-shadow", action="store_true")
    m.add_argument("--floor", action="store_true", help="제품 아래 바닥면 톤 추가")
    a = ap.parse_args()
    cutout(a) if a.cmd == "cutout" else compose(a)


if __name__ == "__main__":
    main()
