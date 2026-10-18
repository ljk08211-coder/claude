"""반응한잔 정보 그래픽(1080x1920 PNG)과 미업로드 클립 자리표시 카드를 만든다.

사용: python3 gfx.py <에피소드 폴더>
결과: <에피소드>/gfx/*.png
"""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
LIFT = 140
FONTS = Path(__file__).resolve().parent.parent / "_assets" / "fonts"
BG, INK, ACCENT, MUTED, GREEN = (18, 20, 24), (245, 245, 240), (255, 205, 40), (140, 145, 155), (110, 200, 120)


FONT_URLS = {
    "BlackHanSans-Regular.ttf": "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/blackhansans/BlackHanSans-Regular.ttf",
    "NotoSansKR-VF.ttf": "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf",
}


def ensure_fonts():
    """무료 폰트(OFL)를 처음 한 번 내려받는다."""
    import urllib.request
    FONTS.mkdir(parents=True, exist_ok=True)
    for name, url in FONT_URLS.items():
        if not (FONTS / name).exists():
            urllib.request.urlretrieve(url, FONTS / name)


def font(size, title=False):
    if title:
        return ImageFont.truetype(str(FONTS / "BlackHanSans-Regular.ttf"), size)
    f = ImageFont.truetype(str(FONTS / "NotoSansKR-VF.ttf"), size)
    try:
        f.set_variation_by_axes([800])
    except OSError:
        pass
    return f


def canvas():
    im = Image.new("RGB", (W, H), BG)
    return im, ImageDraw.Draw(im)


def center(d, y, text, f, fill=INK):
    w = d.textlength(text, font=f)
    d.text(((W - w) / 2, y), text, font=f, fill=fill)


def abv():
    """과일소주는 와인급 도수라는 해석 1을 받쳐 주는 막대 비교."""
    im, d = canvas()
    center(d, 330, "도수 비교", font(110, True), ACCENT)
    rows = [("맥주", 5, MUTED), ("과일소주", 12, ACCENT), ("와인", 12, MUTED),
            ("오리지널 소주", 16, INK), ("보드카", 40, MUTED)]
    x0, maxw, y = 440, 440, 560
    for name, v, c in rows:
        d.text((70, y + 4), name, font=font(46), fill=c)
        d.rounded_rectangle([x0, y + 8, x0 + maxw * v / 40, y + 70], 14, fill=c)
        d.text((x0 + maxw * v / 40 + 20, y + 4), f"{v}%", font=font(50), fill=c)
        y += 150
    center(d, 1360, "맛은 주스, 도수는 와인급", font(66, True))
    center(d, 1460, "※ 제품마다 다름 · 대표값 기준", font(36), MUTED)
    return im


def shot7():
    """7번째 잔 전환 카드. 원본의 샷 카운터 그래픽을 이어받는다."""
    im, d = canvas()
    y = 520
    for i in range(1, 8):
        x = 120 + (i - 1) * 125
        last = i == 7
        d.rounded_rectangle([x, y, x + 95, y + 140], 16, outline=ACCENT if last else MUTED, width=6,
                            fill=(60, 50, 10) if last else None)
        center_x = x + 47 - d.textlength(str(i), font=font(60)) / 2
        d.text((center_x, y + 30), str(i), font=font(60), fill=ACCENT if last else MUTED)
    center(d, 820, "대망의 7번째 잔", font(120, True), ACCENT)
    center(d, 990, "오리지널 소주", font(90, True))
    return im


def order():
    """바텐더 해석 2: 한국식 순서."""
    im, d = canvas()
    center(d, 300, "바텐더 추천 순서", font(100, True), ACCENT)
    steps = [("1", "오리지널 먼저", "입이 깨끗할 때 첫 잔"), ("2", "안주 한 입", "삼겹살·김부각·두부김치"),
             ("3", "과일소주는 디저트", "마지막에 달게 마무리")]
    y = 560
    for n, head, sub in steps:
        d.ellipse([110, y, 250, y + 140], fill=ACCENT)
        d.text((180 - d.textlength(n, font=font(80, True)) / 2, y + 22), n, font=font(80, True), fill=BG)
        d.text((300, y + 5), head, font=font(72, True), fill=INK)
        d.text((300, y + 95), sub, font=font(42), fill=MUTED)
        y += 270
    for ay in (735, 1005):
        d.text((165, ay), "▼", font=font(40), fill=MUTED)
    center(d, 1440, "영상 속 순서는 정반대였어요", font(56), GREEN)
    return im


def end():
    im, d = canvas()
    center(d, 560, "여러분 첫 잔은?", font(120, True), INK)
    d.rounded_rectangle([110, 800, 520, 1000], 30, fill=(40, 44, 52))
    d.rounded_rectangle([560, 800, 970, 1000], 30, fill=(40, 44, 52))
    center_l = 315 - d.textlength("오리지널", font=font(70, True)) / 2
    d.text((center_l, 855), "오리지널", font=font(70, True), fill=INK)
    center_r = 765 - d.textlength("과일", font=font(70, True)) / 2
    d.text((center_r, 855), "과일", font=font(70, True), fill=ACCENT)
    center(d, 1060, "댓글로 알려주세요", font(52), MUTED)
    center(d, 1300, "다음 편: 막걸리", font(90, True), ACCENT)
    center(d, 1440, "반응한잔", font(64, True), MUTED)
    return im


def placeholder(seg):
    """아직 업로드 안 된 클립 자리. 가편집에서 구간과 내용을 보여준다."""
    im, d = canvas()
    me = seg["kind"] == "me"
    d.rectangle([0, 420, W, 1500], fill=(40, 44, 52))
    center(d, 600, "바텐더 촬영 컷" if me else "원본 클립", font(80, True), ACCENT)
    center(d, 730, seg["clip"] + (".mp4" if me else f"  {seg['in']} – {seg['out']}"), font(60), INK)
    label = seg["label"]
    for i in range(0, len(label), 16):
        center(d, 880 + (i // 16) * 80, label[i:i + 16], font(54), MUTED)
    center(d, 1360, "업로드하면 이 자리에 들어갑니다", font(40), MUTED)
    return im


def main():
    ensure_fonts()
    ep = Path(sys.argv[1])
    out = ep / "gfx"
    out.mkdir(exist_ok=True)
    for name, fn in {"abv": abv, "shot7": shot7, "order": order, "end": end}.items():
        im = fn()
        # 아래쪽은 내레이션 자막과 쇼츠 UI 자리라 내용을 위로 올린다
        lifted = Image.new("RGB", (W, H), BG)
        lifted.paste(im, (0, -LIFT))
        lifted.save(out / f"{name}.png")
    plan = json.loads((ep / "cutplan.json").read_text())
    for s in plan["segments"]:
        if s.get("clip"):
            placeholder(s).save(out / f"ph_{s['clip']}.png")
    print("GFX", out)


if __name__ == "__main__":
    main()
