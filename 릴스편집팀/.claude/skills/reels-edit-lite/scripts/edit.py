#!/usr/bin/env python3
"""reels-edit-lite: 캡컷 없이 세로 릴스 완성본 만들기.

순서: 1) 무음 컷 → 2) 한국어 자막(whisper-cli) → 3) 효과음 → 4) 문장 경계 줌 펀치인 → 5) 1080x1920 mp4

사용법:
    python3 edit.py <입력영상> [출력폴더]

위아래 분할(위 = 화면 자료 1080x960, 아래 = 얼굴 1080x960):
    python3 edit.py 얼굴.mp4 out/ --top 화면녹화.mp4          # 영상·이미지·카드 mp4 아무거나
    # 문장마다 도트 카드를 위에 넣을 때 (컷 이후 타임라인 기준):
    python3 edit.py 얼굴.mp4 out/ --plan                     # ① 무음컷+전사 → ② out/<이름>_scenes.json 초안
    #   (scenes.json 의 title/pills 를 문장 요약으로 다듬는다)
    python3 edit.py 얼굴.mp4 out/ --reuse out/work_<이름> --cards out/<이름>_scenes.json   # ③ 카드 렌더 ④ 합성
옵션:
    --model PATH      whisper 모델(.bin). 기본: ./models/ggml-small.bin 를 찾아봄
    --noise -35       무음 판정 기준(dB). 숨소리까지 잘리면 -40, 덜 잘리면 -30
    --min-silence 0.3 이 길이(초)보다 긴 공백만 자른다
    --no-sfx          효과음 끄기
    --no-zoom         줌 펀치인 끄기
    --top PATH        위 절반에 넣을 영상/이미지 (켜면 위아래 분할 모드)
    --top-fit cover   cover=꽉 채우고 넘치는 부분 자름(기본) / contain=다 보이게 줄이고 여백
    --top-sync        top 영상에도 같은 무음 컷 적용 (얼굴과 동시에 녹화한 화면일 때만)
    --face-y 0.33     아래 얼굴 칸의 세로 위치(0=맨 위, 1=맨 아래). 얼굴이 잘리면 조정
    --plan            무음컷+전사까지만 하고 문장별 scenes.json 초안을 만든 뒤 멈춤
    --reuse DIR       --plan 으로 만든 work 폴더를 다시 써서 컷·전사를 건너뜀
    --cards JSON      scenes.json 으로 도트 카드를 렌더해서 --top 으로 사용 (grid-dot-cards 스킬 필요)

자막 오타 고치기: 작업 폴더에 '자막수정.txt' 를 만들고 한 줄에 하나씩
    틀린말=맞는말
형식으로 적은 뒤 다시 실행하면 자막에 반영된다.

필요한 것: python3(표준 라이브러리만), ffmpeg(자막 굽기는 libass 포함 빌드), whisper-cli(whisper.cpp)
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------- 설정값
W, H, FPS = 1080, 1920, 30
PAD = 0.08                 # 컷 앞뒤 여유(초)
MAX_CHARS = 11             # 자막 한 줄 글자 수(공백 포함) 안팎
IS_WIN = sys.platform.startswith("win")
EXE = ".exe" if IS_WIN else ""
IS_MAC = sys.platform == "darwin"
# 자막 글꼴: 맥은 Apple SD 고딕, 윈도우는 맑은 고딕, 리눅스(클라우드)는 Noto Sans CJK KR(시스템 글꼴로 찾음)
FONT = "Malgun Gothic" if IS_WIN else ("Apple SD Gothic Neo" if IS_MAC else "Noto Sans CJK KR")
FONT_FILES = ([r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunbd.ttf"] if IS_WIN
              else ["/System/Library/Fonts/AppleSDGothicNeo.ttc"] if IS_MAC else [])
FONT_SIZE = 84
BOX_COLOR = "&H33000000"   # 검정, 불투명도 80% (ASS는 &HAABBGGRR, AA=투명도 0x33≈20%)
SUB_MARGIN_V = 560         # 화면 아래에서 560px 위 = 하단 1/3 지점
SPLIT_H = 960              # 분할 모드: 위/아래 칸 높이. 자막은 두 칸 경계(y=960) 가운데
TOP_BG = "0xF2F2F2"        # --top-fit contain 일 때 여백 색
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".heic"}
SFX_VOL = 0.35
ZOOM_IN = 1.08             # 펀치인 배율
ZOOM_EASE = 0.15           # 줌 전환 시간(초)
SENT_END = re.compile(r"[.?!。]$")
# whisper 한국어 전사는 마침표를 거의 안 찍는다 → 종결어미·쉼으로 문장 끝을 추정
KO_END = re.compile(r"(요|다|죠|까|네|군|니다)$")   # 돼요·했다·하죠·할까·하네요·했군
KO_END_NOT = {"중요", "필요", "주요", "수요", "요요", "아까", "바다", "보다", "모두다", "가까"}  # 명사·조사
KO_SOFT = re.compile(r"(는데|은데|인데|한데|데|면|고|서|니까|지만|는지|라서|해서|거든)$")  # 긴 문장 쪼갤 자리
PAUSE_SEC = 0.25           # 단어 사이 이 이상 쉬면 문장 끝으로 본다
SENT_MAX = 5.0             # 카드·문장 1개 최대 길이(초). 넘으면 다음 쪼갤 자리에서 자름
SENT_MIN = 1.5             # 쪼갤 때 앞 조각 최소 길이(초)

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent


if IS_WIN:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def log(msg):
    print(f"[edit] {msg}", flush=True)


def die(msg):
    print(f"\n[edit] 멈춤: {msg}\n", file=sys.stderr, flush=True)
    sys.exit(1)


def run(cmd, cwd=None, quiet=True):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-15:])
        die(f"명령 실패: {' '.join(map(str, cmd[:3]))} ...\n{tail}")
    return p


# ---------------------------------------------------------------- 도구 찾기
def search_dirs():
    """현재 폴더와 그 위 3단계 + 스킬 폴더 기준 위쪽."""
    out, seen = [], set()
    for base in (Path.cwd(), SKILL_DIR):
        d = base
        for _ in range(6):
            if d not in seen:
                out.append(d)
                seen.add(d)
            d = d.parent
    return out


def has_filter(ff, name):
    try:
        p = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        return re.search(rf"\s{name}\s", p.stdout) is not None
    except OSError:
        return False


def find_ffmpeg():
    cands = []
    if os.environ.get("REELS_FFMPEG"):
        cands.append(os.environ["REELS_FFMPEG"])
    brew = shutil.which("brew")
    if brew:
        try:
            pre = subprocess.run([brew, "--prefix", "ffmpeg-full"], capture_output=True, text=True).stdout.strip()
            if pre:
                cands.append(f"{pre}/bin/ffmpeg")
        except OSError:
            pass
    for d in search_dirs():
        cands.append(str(d / "bin" / f"ffmpeg{EXE}"))
    if shutil.which("ffmpeg"):
        cands.append(shutil.which("ffmpeg"))
    plain = None
    for c in cands:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            if has_filter(c, "subtitles"):
                return c, True
            plain = plain or c
    if plain:
        return plain, False
    die("ffmpeg 를 못 찾았어요. " + ("PowerShell 에서 `winget install Gyan.FFmpeg` 를 실행하세요." if IS_WIN
        else "터미널에서 `brew install ffmpeg-full` 을 먼저 실행하세요."))


def find_whisper():
    w = os.environ.get("WHISPER_CLI") or shutil.which("whisper-cli")
    if not w:
        # 윈도우: 릴스편집팀/bin/ 에 풀어 둔 whisper-cli.exe (하위 폴더 포함)
        for d in search_dirs():
            hits = sorted((d / "bin").glob(f"**/whisper-cli{EXE}")) if (d / "bin").is_dir() else []
            if hits:
                return str(hits[0])
        die("whisper-cli 가 없어요. " + ("INSTALL_WINDOWS.md 대로 bin/ 에 whisper.cpp 를 풀어 주세요." if IS_WIN
            else "터미널에서 `brew install whisper-cpp` 를 실행하세요."))
    return w


def find_model(arg):
    if arg:
        p = Path(arg).expanduser()
        if p.is_file():
            return p
        die(f"모델 파일이 없어요: {p}")
    if os.environ.get("WHISPER_MODEL") and Path(os.environ["WHISPER_MODEL"]).is_file():
        return Path(os.environ["WHISPER_MODEL"])
    for d in search_dirs():
        for name in ("ggml-small.bin", "ggml-medium.bin", "ggml-large-v3-turbo.bin", "ggml-base.bin"):
            p = d / "models" / name
            if p.is_file():
                return p
    die("whisper 모델이 없어요. models/ggml-small.bin 을 받아주세요:\n"
        "  mkdir -p models && curl -L -o models/ggml-small.bin "
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin")


def find_sfx_dir():
    for d in [Path.cwd() / "sfx", SKILL_DIR / "sfx"] + [x / "sfx" for x in search_dirs()]:
        if d.is_dir():
            return d
    return None


# ---------------------------------------------------------------- 미디어 정보 (ffprobe 없이)
def probe(ff, path):
    p = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    err = p.stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if not m:
        die(f"영상 정보를 못 읽었어요: {path}")
    dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    fps_m = re.search(r"Video:.*?([\d.]+) fps", err)
    size_m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
    has_audio = "Audio:" in err
    if not size_m:
        die("영상 트랙이 없어요.")
    return {
        "duration": dur,
        "fps": float(fps_m[1]) if fps_m else 30.0,
        "w": int(size_m[1]),
        "h": int(size_m[2]),
        "audio": has_audio,
    }


# ---------------------------------------------------------------- 1. 무음 컷
def detect_keep(ff, src, dur, fps, noise, min_sil):
    p = subprocess.run(
        [ff, "-hide_banner", "-nostats", "-i", str(src), "-vn",
         "-af", f"silencedetect=n={noise}dB:d={min_sil}", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", p.stderr)]
    silences = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else dur
        silences.append((s, e))
    # 무음 구간을 앞뒤 PAD 만큼 줄여서 제거
    cuts = []
    for s, e in silences:
        cs = 0.0 if s <= 0.01 else s + PAD
        ce = dur if e >= dur - 0.01 else e - PAD
        if ce - cs > 0.05:
            cuts.append((cs, ce))
    keep, t = [], 0.0
    for cs, ce in cuts:
        if cs > t:
            keep.append((t, cs))
        t = max(t, ce)
    if t < dur:
        keep.append((t, dur))
    # 프레임 격자에 맞춰 영상/오디오 길이를 정확히 일치시킨다
    snapped = []
    for a, b in keep:
        a2 = round(a * fps) / fps
        b2 = round(b * fps) / fps
        if b2 - a2 >= 2 / fps:
            snapped.append((a2, b2))
    if not snapped:
        die("전부 무음으로 판정됐어요. --noise -45 처럼 기준을 낮춰서 다시 실행해보세요.")
    return snapped, silences


def render_cut(ff, src, keep, fps, out):
    half = 0.5 / fps
    vexpr = "+".join(f"between(t,{a - half:.4f},{b - half:.4f})" for a, b in keep)
    aexpr = "+".join(f"between(t,{a:.4f},{b:.4f})" for a, b in keep)
    crop = f"crop='min(iw,ih*{W}/{H})':'min(ih,iw*{H}/{W})',scale={W}:{H}:flags=lanczos,setsar=1"
    fc = (f"[0:v]select='{vexpr}',setpts=N/FRAME_RATE/TB,{crop},fps={FPS}[v];"
          f"[0:a]aselect='{aexpr}',asetpts=N/SR/TB,aresample=48000[a]")
    script = out.with_suffix(".filter.txt")
    script.write_text(fc, encoding="utf-8")
    run([ff, "-hide_banner", "-y", "-i", str(src), "-filter_complex", fc,
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
         "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(out)])
    # 컷이 이어붙은 지점(새 타임라인)
    joins, acc = [], 0.0
    for a, b in keep[:-1]:
        acc += b - a
        joins.append(round(acc, 3))
    return joins


# ---------------------------------------------------------------- 2. 자막
def transcribe(ff, whisper, model, video, work):
    wav = work / "voice16k.wav"
    run([ff, "-hide_banner", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    base = work / "whisper"
    run([whisper, "-m", str(model), "-l", "ko", "-f", str(wav), "-ml", "1", "-sow",
         "-oj", "-of", str(base), "-np"])
    return transcribe_cached(work)


def transcribe_cached(work):
    data = json.loads((work / "whisper.json").read_bytes().decode("utf-8", errors="replace"))
    words = []
    for seg in data.get("transcription", []):
        text = seg.get("text", "").strip()
        if not text:
            continue
        a = seg["offsets"]["from"] / 1000
        b = seg["offsets"]["to"] / 1000
        # -ml 1 에서도 가끔 여러 단어가 한 덩어리로 옴 → 시간 비례 분배
        parts = text.split()
        total = sum(len(x) for x in parts) or 1
        t = a
        for part in parts:
            d = (b - a) * len(part) / total
            words.append({"w": part, "s": t, "e": t + d})
            t += d
    return words


def load_fixes():
    f = Path.cwd() / "자막수정.txt"
    fixes = []
    if f.is_file():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                a, b = line.split("=", 1)
                if a.strip():
                    fixes.append((a.strip(), b.strip()))
    return fixes


def clean(word):
    return re.sub(r"[\"'“”‘’「」『』]", "", word)


def bare(word):
    return re.sub(r"[.,?!。…~]+$", "", clean(word))


def is_sentence_end(word):
    w = clean(word)
    if SENT_END.search(w):
        return True
    b = bare(w)
    return len(b) >= 2 and b not in KO_END_NOT and bool(KO_END.search(b))


def split_sentences(words, joins=()):
    """단어열을 문장 단위로 묶는다. 경계 = 마침표 / 한국어 종결어미 / 0.25초 이상 쉼 / 무음컷 이음점.
    SENT_MAX 초를 넘는 문장은 연결어미(…는데, …고, …면) 자리에서 다시 자른다."""
    words = [w for w in words if clean(w["w"]).strip()]
    sents, cur = [], []
    for i, wd in enumerate(words):
        cur.append(wd)
        nxt = words[i + 1] if i + 1 < len(words) else None
        end = nxt is None or is_sentence_end(wd["w"])
        if nxt is not None and not end:
            gap = nxt["s"] - wd["e"]
            joined = any(wd["e"] - 0.15 <= j <= nxt["s"] + 0.15 for j in joins)
            end = gap >= PAUSE_SEC or joined
        if end:
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)

    out = []
    for s in sents:
        while s[-1]["e"] - s[0]["s"] > SENT_MAX and len(s) > 1:
            # SENT_MIN 초 이후 첫 연결어미 자리, 없으면 가운데에 가장 가까운 단어 경계
            k = None
            for j in range(len(s) - 1):
                if s[j]["e"] - s[0]["s"] >= SENT_MIN and KO_SOFT.search(bare(s[j]["w"])) \
                        and s[-1]["e"] - s[j + 1]["s"] >= 1.0:
                    k = j + 1
                    break
            if k is None:
                mid = s[0]["s"] + (s[-1]["e"] - s[0]["s"]) / 2
                k = min(range(1, len(s)), key=lambda j: abs(s[j]["s"] - mid))
            out.append(s[:k])
            s = s[k:]
        out.append(s)
    return out


def apply_fixes(sent, fixes):
    """자막수정.txt 치환을 문장 전체 글자열에 먼저 적용한다(단어·줄 경계를 넘는 '컵 편집' 도 잡힘).
    글자마다 원래 단어 번호를 기억해 두었다가 다시 띄어쓰기로 나눠 단어별 시간을 복원한다."""
    chars, owner = [], []
    for i, wd in enumerate(sent):
        if chars:
            chars.append(" ")
            owner.append(None)
        for c in clean(wd["w"]):
            chars.append(c)
            owner.append(i)
    for a, b in fixes:
        pos = 0
        while True:
            text = "".join(chars)
            k = text.find(a, pos)
            if k < 0:
                break
            span = [o for o in owner[k:k + len(a)] if o is not None] or [owner[k - 1] if k else 0]
            new_owner = [span[min(len(span) - 1, int(n * len(span) / max(1, len(b))))] for n in range(len(b))]
            new_owner = [None if c == " " else o for c, o in zip(b, new_owner)]
            chars[k:k + len(a)] = list(b)
            owner[k:k + len(a)] = new_owner
            pos = k + max(1, len(b))
    toks, cur = [], []
    for c, o in zip(chars + [" "], owner + [None]):
        if c == " ":
            if cur:
                idx = [x for _, x in cur if x is not None]
                if idx:
                    toks.append({"w": "".join(ch for ch, _ in cur),
                                 "s": sent[min(idx)]["s"], "e": sent[max(idx)]["e"]})
                cur = []
        else:
            cur.append((c, o))
    return toks


def wrap_sentence(toks):
    """한 문장을 MAX_CHARS 안팎 줄로 나눈다. 줄 길이를 고르게, 한 글자 단어('첫','두')에서 끊는 건 피한다."""
    texts = [t["w"] for t in toks]
    n = len(texts)
    INF = float("inf")
    best = [INF] * (n + 1)
    prev = [0] * (n + 1)
    best[0] = 0.0
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            ln = len(" ".join(texts[i:j]))
            if ln > MAX_CHARS and j - i > 1:
                break
            cost = best[i] + (MAX_CHARS - ln) ** 2 + 30  # 줄 수가 적을수록, 길이가 고를수록 좋음
            if j < n and len(texts[j - 1]) == 1:
                cost += 200                              # '첫 / 번째' 처럼 끊기 금지
            if cost < best[j]:
                best[j], prev[j] = cost, i
    cuts, j = [], n
    while j > 0:
        cuts.append((prev[j], j))
        j = prev[j]
    return [toks[i:j] for i, j in reversed(cuts)]


def build_lines(words, fixes, total_dur, joins=()):
    """문장 경계를 먼저 정하고(줄이 문장을 넘지 않게), 치환을 문장 단위로 적용한 뒤 줄로 나눈다."""
    lines = []
    for sent in split_sentences(words, joins):
        toks = apply_fixes(sent, fixes)
        first = True
        for chunk in wrap_sentence(toks) if toks else []:
            text = " ".join(t["w"] for t in chunk)
            text = re.sub(r"[.,]+$", "", text).replace(",", "").strip()
            if not text:
                continue
            lines.append({"text": text, "s": chunk[0]["s"], "e": chunk[-1]["e"], "sentence_start": first})
            first = False
    # 끝 시간: 다음 줄 시작까지 붙이되 공백이 길면 0.3초 뒤에 내림
    for i, ln in enumerate(lines):
        nxt = lines[i + 1]["s"] if i + 1 < len(lines) else total_dur
        ln["e"] = min(nxt, max(ln["e"] + 0.3, ln["s"] + 0.5))
        ln["e"] = min(ln["e"], total_dur)
    return lines


def ass_time(t):
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def write_ass(lines, path, split=False):
    # 분할 모드: Alignment 5(정가운데) → 박스 중심이 y=960, 두 칸 경계에 걸친다
    align, margin_v = (5, 0) if split else (2, SUB_MARGIN_V)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT},{FONT_SIZE},&H00FFFFFF,&H00FFFFFF,{BOX_COLOR},{BOX_COLOR},-1,0,0,0,100,100,0,0,3,16,0,{align},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = "".join(
        f"Dialogue: 0,{ass_time(l['s'])},{ass_time(l['e'])},Default,,0,0,0,,{l['text']}\n" for l in lines)
    path.write_text(head + body, encoding="utf-8")


# ---------------------------------------------------------------- 3. 효과음
def pick_sfx(sfx_dir):
    if not sfx_dir:
        return {}
    found = {}
    for kind in ("pop", "click", "whoosh"):
        for ext in ("mp3", "wav", "m4a"):
            hits = sorted(sfx_dir.glob(f"*{kind}*.{ext}"))
            if hits:
                found[kind] = hits[0]
                break
    return found


def plan_sfx(lines, transitions, sfx):
    """문장 시작 줄에만 소리. 기본 pop, 3번째마다 click, 줌 전환 지점은 whoosh. 같은 소리 3연속 금지."""
    if not sfx:
        return []
    events = []
    n = 0
    for ln in lines:
        if not ln["sentence_start"]:
            continue
        at_trans = any(abs(ln["s"] - t) < 0.6 for t in transitions)
        if at_trans and "whoosh" in sfx:
            kind = "whoosh"
        elif n % 3 == 2 and "click" in sfx:
            kind = "click"
        else:
            kind = "pop" if "pop" in sfx else next(iter(sfx))
        if len(events) >= 2 and events[-1]["kind"] == events[-2]["kind"] == kind:
            alts = [k for k in sfx if k != kind]
            if alts:
                kind = alts[0]
        lead = 0.12 if kind == "whoosh" else 0.0
        events.append({"kind": kind, "t": round(max(0.0, ln["s"] - lead), 3), "line": ln["text"]})
        n += 1
    return events


# ---------------------------------------------------------------- 4. 줌 펀치인
def plan_zoom(lines, joins):
    """문장 경계이면서 실제로 컷이 붙은 지점(±0.5초)에서 배율을 1.0 ↔ ZOOM_IN 으로 번갈아 바꾼다."""
    pts = []
    for ln in lines[1:]:
        if not ln["sentence_start"]:
            continue
        near = [j for j in joins if abs(j - ln["s"]) <= 0.5]
        if near:
            pts.append(near[0])
    pts = sorted(set(pts))
    return pts


def zoom_expr(points):
    if not points:
        return None
    terms = []
    level = 1.0
    for p in points:
        target = ZOOM_IN if abs(level - 1.0) < 1e-6 else 1.0
        delta = target - level
        prog = f"clip((it-{p:.3f})/{ZOOM_EASE},0,1)"
        terms.append(f"{delta:+.3f}*(1-pow(1-{prog},3))")
        level = target
    return "1" + "".join(terms)


# ---------------------------------------------------------------- 5. 최종 렌더
def top_chain(top, dur, fit, sync_keep):
    """위 칸(1080xSPLIT_H) 필터. 이미지면 정지 화면, 영상이면 길이를 맞춘다(짧으면 마지막 프레임 유지)."""
    f = []
    if sync_keep:
        expr = "+".join(f"between(t,{a:.4f},{b:.4f})" for a, b in sync_keep)
        f += [f"fps={FPS}", f"select='{expr}'", f"setpts=N/{FPS}/TB"]
    if fit == "contain":
        f += [f"scale={W}:{SPLIT_H}:force_original_aspect_ratio=decrease:flags=lanczos",
              f"pad={W}:{SPLIT_H}:(ow-iw)/2:(oh-ih)/2:color={TOP_BG}"]
    else:
        f += [f"scale={W}:{SPLIT_H}:force_original_aspect_ratio=increase:flags=lanczos",
              f"crop={W}:{SPLIT_H}"]
    f += ["setsar=1", f"fps={FPS}",
          f"tpad=stop_mode=clone:stop_duration={dur + 1:.3f}",
          f"trim=duration={dur:.3f}", "setpts=PTS-STARTPTS"]
    return ",".join(f)


def render_final(ff, can_sub, cut, ass, events, sfx, zpoints, out, work, split=None):
    inputs = ["-i", str(cut)]
    vchain = "[0:v]"
    vf = []
    pre = []
    n_extra = 0
    if split:
        # 아래 칸: 9:16 컷 영상에서 얼굴 위치(face_y) 기준으로 1080x960 을 잘라낸다
        y = max(0, min(H - SPLIT_H, int(round(H * split["face_y"] - SPLIT_H / 2))))
        top = Path(split["top"])
        if top.suffix.lower() in IMG_EXT:
            inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{split['dur']:.3f}", "-i", str(top)]
        else:
            inputs += ["-i", str(top)]
        n_extra = 1
        pre.append(f"[1:v]{top_chain(top, split['dur'], split['fit'], split.get('sync_keep'))}[top]")
        face = [f"crop={W}:{SPLIT_H}:0:{y}"]
        ze = zoom_expr(zpoints)
        if ze:
            face.append(f"zoompan=z='{ze}':d=1:x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':s={W}x{SPLIT_H}:fps={FPS}")
        pre.append(f"[0:v]{','.join(face)}[face]")
        pre.append("[top][face]vstack=inputs=2[stk]")
        vchain = "[stk]"
    else:
        ze = zoom_expr(zpoints)
        if ze:
            vf.append(f"zoompan=z='{ze}':d=1:x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':s={W}x{H}:fps={FPS}")
    if can_sub:
        fonts = work / "fonts"
        fonts.mkdir(exist_ok=True)
        for f in FONT_FILES:
            link = fonts / Path(f).name
            if os.path.exists(f) and not link.exists():
                if IS_WIN:
                    shutil.copy(f, link)  # 윈도우는 심볼릭 링크에 관리자 권한이 필요해서 복사
                else:
                    os.symlink(f, link)
        vf.append(f"subtitles=filename={ass.name}:fontsdir=fonts")
    vf.append("format=yuv420p")
    fc = pre + [f"{vchain}{','.join(vf)}[v]"]
    amix_in = ["[0:a]"]
    for i, ev in enumerate(events):
        inputs += ["-i", str(sfx[ev["kind"]])]
        ms = int(ev["t"] * 1000)
        trim = "atrim=0:0.6,afade=t=out:st=0.4:d=0.2," if ev["kind"] == "whoosh" else ""
        fc.append(
            f"[{i + 1 + n_extra}:a]silenceremove=start_periods=1:start_threshold=-45dB,{trim}"
            f"aresample=48000,aformat=channel_layouts=stereo,volume={SFX_VOL},adelay={ms}|{ms}[s{i}]")
        amix_in.append(f"[s{i}]")
    if events:
        fc.append(f"[0:a]aformat=channel_layouts=stereo[nar];"
                  f"[nar]{''.join(amix_in[1:])}amix=inputs={len(amix_in)}:duration=first:normalize=0[a]")
    else:
        fc.append("[0:a]aformat=channel_layouts=stereo[a]")
    fc = ";".join(fc)
    (work / "final.filter.txt").write_text(fc, encoding="utf-8")
    # 자막 파일 경로에 한글·공백이 있어도 깨지지 않도록 work 폴더에서 실행
    run([ff, "-hide_banner", "-y", *inputs, "-filter_complex", fc,
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", str(out.resolve())], cwd=str(work))


# ---------------------------------------------------------------- 분할 모드: 문장별 카드 초안
def two_lines(text):
    """제목 초안: 공백 기준으로 가운데에서 두 줄로 나눈다."""
    words = text.split()
    if len(words) < 2:
        return text
    best, cut = None, 1
    for i in range(1, len(words)):
        diff = abs(len(" ".join(words[:i])) - len(" ".join(words[i:])))
        if best is None or diff < best:
            best, cut = diff, i
    return " ".join(words[:cut]) + "\n" + " ".join(words[cut:])


def make_scenes(lines, total, max_len=5.0, min_len=1.0):
    """컷 이후 타임라인 기준으로 문장마다 카드 1장. 5초 넘는 문장은 줄 경계에서 나누고 1초 미만은 앞 카드에 합친다."""
    groups = []
    for ln in lines:
        if ln["sentence_start"] or not groups:
            groups.append([ln])
        else:
            groups[-1].append(ln)
    split = []
    for g in groups:
        while len(g) > 1 and g[-1]["e"] - g[0]["s"] > max_len:
            mid = g[0]["s"] + (g[-1]["e"] - g[0]["s"]) / 2
            k = min(range(1, len(g)), key=lambda j: abs(g[j]["s"] - mid))
            split.append(g[:k])
            g = g[k:]
        split.append(g)
    merged = []
    for g in split:
        if merged and g[-1]["e"] - g[0]["s"] < min_len:
            merged[-1] = merged[-1] + g
        else:
            merged.append(g)
    scenes = []
    for i, g in enumerate(merged):
        start = 0.0 if i == 0 else round(max(0.0, g[0]["s"] - 0.05), 3)
        text = " ".join(x["text"] for x in g)
        scenes.append({"start": start, "end": None, "step": f"STEP {i + 1:02d}",
                       "title": two_lines(text), "pills": [], "footer": "", "_sentence": text})
    for i, sc in enumerate(scenes):
        sc["end"] = scenes[i + 1]["start"] if i + 1 < len(scenes) else round(total, 3)
    return {"label": "", "scenes": scenes}


def render_cards(scenes_json, out_mp4, dur):
    script = SKILL_DIR.parent / "grid-dot-cards" / "scripts" / "render.mjs"
    if not script.is_file():
        die(f"grid-dot-cards 스킬이 없어요: {script}")
    node = shutil.which("node")
    if not node:
        die("node 가 없어요. " + ("`winget install OpenJS.NodeJS.LTS`" if IS_WIN else "`brew install node`")
            + " 후 `npm i playwright && npx playwright install chromium`")
    p = subprocess.run([node, str(script), str(scenes_json), str(out_mp4), "--size", "half",
                        "--duration", f"{dur:.3f}"], text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0 or not out_mp4.is_file():
        die("도트 카드 렌더 실패 (위 [cards] 메시지 확인)")


# ---------------------------------------------------------------- 출력 이름(덮어쓰기 금지)
def free_name(folder, stem, suffix):
    p = folder / f"{stem}{suffix}"
    v = 2
    while p.exists():
        p = folder / f"{stem}_v{v}{suffix}"
        v += 1
    return p


def main():
    ap = argparse.ArgumentParser(description="세로 릴스 자동 편집 (무음컷·자막·효과음·줌)")
    ap.add_argument("input")
    ap.add_argument("outdir", nargs="?", default="out")
    ap.add_argument("--model")
    ap.add_argument("--noise", type=float, default=-35)
    ap.add_argument("--min-silence", type=float, default=0.3)
    ap.add_argument("--no-sfx", action="store_true")
    ap.add_argument("--no-zoom", action="store_true")
    ap.add_argument("--top")
    ap.add_argument("--top-fit", choices=["cover", "contain"], default="cover")
    ap.add_argument("--top-sync", action="store_true")
    ap.add_argument("--face-y", type=float, default=0.33)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--reuse")
    ap.add_argument("--cards")
    args = ap.parse_args()
    if args.top and args.cards:
        die("--top 과 --cards 는 하나만 쓰세요.")
    if args.top_sync and not args.top:
        die("--top-sync 는 --top 영상과 같이 써야 해요.")
    top_path = None
    if args.top:
        top_path = Path(args.top).expanduser().resolve()
        if not top_path.is_file():
            die(f"--top 파일이 없어요: {top_path}")
    if not 0.0 <= args.face_y <= 1.0:
        die("--face-y 는 0~1 사이")

    t0 = time.time()
    src = Path(args.input).expanduser().resolve()
    if not src.is_file():
        die(f"입력 영상이 없어요: {src}")
    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    stem = src.stem

    ff, can_sub = find_ffmpeg()
    whisper = find_whisper()
    model = find_model(args.model)
    sfx = {} if args.no_sfx else pick_sfx(find_sfx_dir())
    log(f"ffmpeg: {ff} (자막 굽기 {'가능' if can_sub else '불가 — .ass 파일만 만듦'})")
    log(f"whisper: {whisper} / 모델: {model.name}")
    log(f"효과음: {', '.join(sfx) if sfx else '없음'}")

    split_mode = bool(top_path or args.cards)
    final = free_name(outdir, f"{stem}_{'분할' if split_mode else '편집'}", ".mp4")

    info = probe(ff, src)
    if not info["audio"]:
        die("소리 트랙이 없는 영상이에요. 나레이션이 들어간 영상을 넣어주세요.")
    log(f"입력: {info['w']}x{info['h']} {info['fps']:.2f}fps {info['duration']:.2f}초")

    cut_info = None
    if args.reuse:
        work = Path(args.reuse).expanduser().resolve()
        try:
            cut_info = json.loads((work / "cut.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            die(f"--reuse 폴더에 cut.json 이 없어요: {work}  (--plan 으로 만든 work 폴더를 주세요)")
        if cut_info.get("input") != str(src) or not (work / "1_cut.mov").is_file() or not (work / "whisper.json").is_file():
            die(f"--reuse 폴더가 이 영상({src.name}) 것이 아니거나 파일이 빠졌어요: {work}")
    else:
        work = free_name(outdir, f"work_{stem}", "")
        work.mkdir(parents=True)

    # 1
    cut = work / "1_cut.mov"
    if cut_info:
        keep, silences, joins = cut_info["keep"], cut_info["silences"], cut_info["joins"]
        cut_dur = sum(b - a for a, b in keep)
        log(f"1/5 무음 컷 — 재사용 ({cut_dur:.2f}초)")
    else:
        log("1/5 무음 컷")
        keep, silences = detect_keep(ff, src, info["duration"], info["fps"], args.noise, args.min_silence)
        joins = render_cut(ff, src, keep, info["fps"], cut)
        cut_dur = sum(b - a for a, b in keep)
        log(f"    공백 {len(silences)}곳 발견 → {info['duration']:.2f}초 → {cut_dur:.2f}초")
        (work / "cut.json").write_text(json.dumps(
            {"input": str(src), "keep": keep, "silences": silences, "joins": joins}, ensure_ascii=False), encoding="utf-8")

    # 2
    log("2/5 자막 (whisper 한국어 전사)" + (" — 재사용" if cut_info else ""))
    words = transcribe_cached(work) if cut_info else transcribe(ff, whisper, model, cut, work)
    lines = build_lines(words, load_fixes(), cut_dur, joins)

    if args.plan:
        sj = free_name(outdir, f"{stem}_scenes", ".json")
        sj.write_text(json.dumps(make_scenes(lines, cut_dur), ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"    자막 {len(lines)}줄 → 카드 초안 {len(json.loads(sj.read_text(encoding='utf-8'))['scenes'])}장")
        log(f"계획 완료: {sj}")
        log(f"다음: title/pills 를 다듬고 → python3 {Path(sys.argv[0]).as_posix()} \"{args.input}\" {args.outdir} "
            f"--reuse \"{work}\" --cards \"{sj}\"")
        return

    if args.cards:
        sj = Path(args.cards).expanduser().resolve()
        if not sj.is_file():
            die(f"scenes.json 이 없어요: {sj}")
        top_path = free_name(outdir, f"{stem}_cards", ".mp4")
        log("    도트 카드 렌더 (grid-dot-cards, 1080x960)")
        render_cards(sj, top_path, cut_dur)

    ass = work / "subs.ass"
    write_ass(lines, ass, split=split_mode)
    txt = free_name(outdir, f"{stem}_자막", ".txt")
    txt.write_text("\n".join(f"{ass_time(l['s'])}  {l['text']}" for l in lines) + "\n", encoding="utf-8")
    shutil.copy(ass, free_name(outdir, f"{stem}", ".ass"))
    log(f"    자막 {len(lines)}줄")

    # 4 (효과음 배치가 전환 위치를 알아야 해서 먼저 계산)
    zpoints = [] if args.no_zoom else plan_zoom(lines, joins)
    # 3
    events = plan_sfx(lines, zpoints, sfx)
    log(f"3/5 효과음 {len(events)}개: " + ", ".join(f"{e['kind']}@{e['t']:.2f}s" for e in events))
    log(f"4/5 줌 펀치인 {len(zpoints)}곳: " + ", ".join(f"{p:.2f}s" for p in zpoints))

    # 5
    log("5/5 최종 렌더")
    split = None
    if split_mode:
        split = {"top": str(top_path), "dur": cut_dur, "fit": args.top_fit, "face_y": args.face_y,
                 "sync_keep": keep if args.top_sync else None}
        log(f"    분할: 위 {top_path.name} ({args.top_fit}{', 무음컷 동기' if args.top_sync else ''}) / 아래 얼굴 face-y {args.face_y}")
    render_final(ff, can_sub, cut, ass, events, sfx, zpoints, final, work, split)

    report = {
        "input": str(src), "output": str(final),
        "input_sec": round(info["duration"], 3), "output_sec": round(cut_dur, 3),
        "silences": silences, "keep": keep, "joins": joins,
        "lines": lines, "sfx": events, "zoom_points": zpoints,
        "subtitles_burned": can_sub, "elapsed_sec": round(time.time() - t0, 1),
        "split": split,
    }
    (work / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"완료 ({report['elapsed_sec']}초): {final}")
    log(f"자막 확인용: {txt}")
    if not can_sub:
        log("주의: 이 ffmpeg 는 자막 굽기를 못 해요. `brew install ffmpeg-full` 후 다시 실행하세요.")


if __name__ == "__main__":
    main()
