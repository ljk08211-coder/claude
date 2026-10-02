#!/usr/bin/env python3
"""유튜브 영상 → 자막 + 장면 캡처 + 장면 목록.

사용법:
  python youtube_digest.py check
  python youtube_digest.py run <유튜브URL> [--out 폴더] [--threshold 0.3]
                           [--min-gap 2] [--max-scenes 40] [--keep-video]
                           [--cookies-from-browser chrome] [--gemini auto|always|off]

자막이 없거나 부족하면 GEMINI_API_KEY 로 제미나이에게 영상을 보여주고 gemini_summary.md 를 받는다.
설치는 절대 하지 않는다. 필요한 프로그램이 없으면 목록과 설치 명령만 출력하고 종료(코드 2).
자막이 없으면 meta.json 의 subtitle.status 가 "none" 이 되고 콘솔에 NO_SUBTITLES 를 출력한다.
"""
import argparse
import html
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

REQUIRED = ["yt-dlp", "ffmpeg"]

INSTALL_HINTS = {
    "Darwin": {"yt-dlp": "brew install yt-dlp", "ffmpeg": "brew install ffmpeg"},
    "Windows": {"yt-dlp": "winget install yt-dlp.yt-dlp", "ffmpeg": "winget install Gyan.FFmpeg"},
    "Linux": {"yt-dlp": "python3 -m pip install -U yt-dlp", "ffmpeg": "sudo apt install ffmpeg"},
}


def missing_deps():
    return [name for name in REQUIRED if shutil.which(name) is None]


def cmd_check(_args):
    missing = missing_deps()
    key = "설정됨" if os.environ.get("GEMINI_API_KEY", "").strip() else "없음 (자막 부족 시 제미나이 보강 불가)"
    print(f"GEMINI_API_KEY: {key}")
    if not missing:
        print("OK: yt-dlp, ffmpeg 모두 설치되어 있음")
        return 0
    hints = INSTALL_HINTS.get(platform.system(), INSTALL_HINTS["Linux"])
    print("MISSING: " + ", ".join(missing))
    for name in missing:
        print(f"  - {name}: {hints[name]}")
    return 2


# ---------- 자막 ----------

def pick_subtitle(info):
    """(종류, 언어) 를 고른다. 수동 자막 우선, 없으면 자동 자막. 둘 다 없으면 None."""
    video_lang = (info.get("language") or "").split("-")[0]
    manual = info.get("subtitles") or {}
    manual = {k: v for k, v in manual.items() if k != "live_chat"}
    auto = info.get("automatic_captions") or {}

    def first_match(tracks, prefs):
        for pref in prefs:
            if pref and pref in tracks:
                return pref
        for pref in prefs:
            if not pref:
                continue
            for lang in tracks:
                if lang.split("-")[0] == pref:
                    return lang
        return None

    lang = first_match(manual, ["ko", video_lang, "en"]) or next(iter(manual), None)
    if lang:
        return "manual", lang
    # 자동 자막은 원어 트랙(-orig)이 가장 정확하다. 번역 자동자막은 그다음.
    lang = first_match(auto, [f"{video_lang}-orig" if video_lang else "", video_lang, "ko", "en"])
    if lang:
        return "auto", lang
    return None


def parse_srt(path, dedupe=False):
    """[(start, end, text)] — 태그 제거. dedupe=True 면 자동자막의 반복 줄 제거."""
    text = path.read_text(encoding="utf-8", errors="replace")
    cues = []
    prev_lines = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = [l for l in block.strip().split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        idx = 1 if "-->" in lines[1] else 0
        m = re.match(r"(\S+)\s*-->\s*(\S+)", lines[idx])
        if not m:
            continue
        body = []
        for line in lines[idx + 1:]:
            line = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
            # 자동자막은 직전 큐의 줄을 다시 보여주므로 이미 나온 줄은 건너뛴다
            if line and not (dedupe and line in prev_lines) and line not in body:
                body.append(line)
        prev_lines = [html.unescape(re.sub(r"<[^>]+>", "", l)).strip() for l in lines[idx + 1:]]
        if body:
            cues.append((to_seconds(m.group(1)), to_seconds(m.group(2)), " ".join(body)))
    return cues


def to_seconds(ts):
    h, m, s = ts.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def fmt_time(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


# ---------- 장면 ----------

def detect_scenes(video, scene_dir, threshold):
    scene_dir.mkdir(parents=True, exist_ok=True)
    vf = f"select='eq(n\\,0)+gt(scene\\,{threshold})',showinfo,scale=640:-2"
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", str(video), "-vf", vf,
         "-vsync", "vfr", "-q:v", "3", str(scene_dir / "raw_%04d.jpg")],
        capture_output=True, text=True, errors="replace",
    )
    if proc.returncode != 0:
        sys.exit("ffmpeg 장면 감지 실패:\n" + proc.stderr[-2000:])
    times = [float(t) for t in re.findall(r"pts_time:\s*([\d.]+)", proc.stderr)]
    files = sorted(scene_dir.glob("raw_*.jpg"))
    return list(zip(times, files))


def capture_interval(video, scene_dir, duration, count=10):
    """장면 전환이 거의 없는 영상(고정 화면 등)용: 일정 간격 캡처."""
    scene_dir.mkdir(parents=True, exist_ok=True)
    step = max(duration / count, 1)
    result = []
    for i in range(count):
        t = i * step
        if t >= duration:
            break
        out = scene_dir / f"raw_i{i:04d}.jpg"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-ss", f"{t:.2f}", "-i", str(video),
             "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", str(out)],
            capture_output=True,
        )
        if out.exists():
            result.append((t, out))
    return result


def thin_scenes(scenes, min_gap, max_scenes):
    kept, dropped = [], []
    for t, f in scenes:
        if kept and t - kept[-1][0] < min_gap:
            dropped.append(f)
        else:
            kept.append((t, f))
    if len(kept) > max_scenes:
        step = len(kept) / max_scenes
        picked = {int(i * step) for i in range(max_scenes)}
        dropped += [f for i, (_, f) in enumerate(kept) if i not in picked]
        kept = [s for i, s in enumerate(kept) if i in picked]
    for f in dropped:
        f.unlink(missing_ok=True)
    return kept


def text_between(cues, start, end, limit=120):
    parts = [c[2] for c in cues if c[1] > start and c[0] < end]
    text = " ".join(parts)
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


# ---------- 실행 ----------

def ytdlp_base(args):
    base = ["yt-dlp", "--no-playlist", "--no-warnings"]
    if args.cookies_from_browser:
        base += ["--cookies-from-browser", args.cookies_from_browser]
    return base


def cmd_run(args):
    if missing_deps():
        return cmd_check(args)

    proc = subprocess.run(ytdlp_base(args) + ["-J", args.url], capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        sys.exit("영상 정보를 가져오지 못함:\n" + proc.stderr[-2000:])
    info = json.loads(proc.stdout)
    vid = info["id"]
    out = Path(args.out) / vid
    out.mkdir(parents=True, exist_ok=True)
    duration = float(info.get("duration") or 0)

    meta = {
        "url": args.url,
        "id": vid,
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "duration": fmt_time(duration),
        "upload_date": info.get("upload_date"),
        "description": (info.get("description") or "")[:2000],
        "subtitle": {"status": "none"},
    }

    # 1) 자막
    cues = []
    choice = pick_subtitle(info)
    if choice:
        kind, lang = choice
        flag = "--write-subs" if kind == "manual" else "--write-auto-subs"
        subprocess.run(
            ytdlp_base(args) + ["--skip-download", flag, "--sub-langs", lang,
                                "--sub-format", "srt/vtt/best", "--convert-subs", "srt",
                                "-o", str(out / "subtitles.%(ext)s"), args.url],
            capture_output=True, text=True, errors="replace",
        )
        srt = next(iter(sorted(out.glob("subtitles*.srt"))), None)
        if srt:
            cues = parse_srt(srt, dedupe=(kind == "auto"))
            transcript = out / "transcript.txt"
            transcript.write_text(
                "\n".join(f"[{fmt_time(s)}] {t}" for s, _, t in cues) + "\n", encoding="utf-8")
            meta["subtitle"] = {"status": kind, "lang": lang, "file": srt.name,
                                "transcript": transcript.name, "cues": len(cues)}
    if meta["subtitle"]["status"] == "none":
        print("NO_SUBTITLES: 이 영상에는 다운로드 가능한 자막(수동/자동)이 없음")

    # 2) 영상(장면 감지용 저화질) 다운로드
    subprocess.run(
        ytdlp_base(args) + ["-f", "bv*[height<=480]/b[height<=480]/wv*/w",
                            "-o", str(out / "video.%(ext)s"), args.url],
        capture_output=True, text=True, errors="replace",
    )
    video = next((p for p in out.glob("video.*") if p.suffix not in (".part", ".ytdl")), None)

    # 3) 장면 전환 캡처
    rows, method = [], None
    if video:
        rows, method = make_scenes(video, out, vid, duration, cues, meta, args)
        meta["scenes"] = {"status": "ok", "method": method, "count": len(rows),
                          "threshold": args.threshold}
    else:
        meta["scenes"] = {"status": "video_download_failed"}
        print("VIDEO_DOWNLOAD_FAILED: 영상을 받지 못해 장면 캡처를 못함")

    # 4) 자막이 부족하면 제미나이에게 영상을 보여주고 요약 받기
    meta["gemini"] = run_gemini(args, out, video, cues, duration, meta)

    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if video and not args.keep_video:
        video.unlink(missing_ok=True)

    print(f"DONE: {out}")
    print(f"  자막: {meta['subtitle']['status']}" + (f" ({meta['subtitle'].get('lang')})" if cues else ""))
    print(f"  장면: {len(rows)}개 ({method})" if video else "  장면: 없음 (영상 다운로드 실패)")
    print(f"  제미나이: {meta['gemini']['status']}")
    return 0 if video or meta["gemini"]["status"] == "ok" else 1


def make_scenes(video, out, vid, duration, cues, meta, args):
    scene_dir = out / "scenes"
    scenes = detect_scenes(video, scene_dir, args.threshold)
    method = "scene_change"
    if len(scenes) < 3 and duration > 0:
        for _, f in scenes:
            f.unlink(missing_ok=True)
        scenes = capture_interval(video, scene_dir, duration)
        method = "interval"
    scenes = thin_scenes(scenes, args.min_gap, args.max_scenes)

    rows = []
    for i, (t, f) in enumerate(scenes, 1):
        name = f"scene_{i:03d}_{fmt_time(t).replace(':', '-')}.jpg"
        f.rename(scene_dir / name)
        end = scenes[i][0] if i < len(scenes) else (duration or t + 10)
        rows.append({"no": i, "time": fmt_time(t), "seconds": round(t, 2),
                     "image": f"scenes/{name}", "subtitle": text_between(cues, t, end)})

    lines = [f"# 장면 목록 — {meta['title']}", "",
             f"- 링크: {args.url}",
             f"- 길이: {meta['duration']} · 장면 {len(rows)}개 ({'장면 전환 감지' if method == 'scene_change' else '일정 간격 캡처'})",
             "", "| # | 시간 | 캡처 | 그 구간 자막 | 장면 설명 |", "|---|---|---|---|---|"]
    for r in rows:
        sub = r["subtitle"].replace("|", "\\|") or "—"
        lines.append(f"| {r['no']} | [{r['time']}](https://www.youtube.com/watch?v={vid}&t={int(r['seconds'])}s) "
                     f"| ![]({r['image']}) | {sub} |  |")
    (out / "scenes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "scenes.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows, method


# ---------- 제미나이 ----------

def subtitle_shortfall(cues, duration):
    """자막만으로 부족한 이유. 충분하면 None."""
    if not cues:
        return "자막 없음"
    chars = sum(len(c[2]) for c in cues)
    if chars < 200:
        return f"자막이 너무 짧음({chars}자)"
    if duration >= 60 and chars / (duration / 60) < 60:
        return f"자막 밀도가 낮음(분당 {int(chars / (duration / 60))}자, 말보다 화면 위주 영상)"
    return None


def run_gemini(args, out, video, cues, duration, meta):
    if args.gemini == "off":
        return {"status": "off"}
    reason = subtitle_shortfall(cues, duration)
    if args.gemini == "auto" and not reason:
        return {"status": "not_needed"}
    reason = reason or "사용자 요청(--gemini always)"

    import gemini_video  # 같은 폴더의 스크립트
    context = (f"참고: 제목 '{meta['title']}', 채널 '{meta['channel']}'. "
               f"이 영상은 {reason}이라 화면 내용까지 봐야 한다.")
    try:
        text, how, model = gemini_video.summarize(args.url, video, context, duration)
    except gemini_video.GeminiError as e:
        if str(e) == "NO_KEY":
            print("GEMINI_SKIPPED_NO_KEY: 자막이 부족하지만 GEMINI_API_KEY 가 설정되지 않음")
            return {"status": "no_key", "reason": reason}
        print(f"GEMINI_FAILED: {e}")
        return {"status": "failed", "reason": reason, "error": str(e)}
    (out / "gemini_summary.md").write_text(
        f"<!-- 제미나이 {model} · {how} · 이유: {reason} -->\n{text}\n", encoding="utf-8")
    print(f"GEMINI_OK: gemini_summary.md ({model})")
    return {"status": "ok", "reason": reason, "model": model, "method": how,
            "file": "gemini_summary.md"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    r = sub.add_parser("run")
    r.add_argument("url")
    r.add_argument("--out", default="youtube-digest")
    r.add_argument("--threshold", type=float, default=0.3, help="장면 전환 민감도 (낮을수록 많이 잡음)")
    r.add_argument("--min-gap", type=float, default=2.0, help="장면 사이 최소 간격(초)")
    r.add_argument("--max-scenes", type=int, default=40)
    r.add_argument("--keep-video", action="store_true")
    r.add_argument("--cookies-from-browser", default=None)
    r.add_argument("--gemini", choices=["auto", "always", "off"], default="auto",
                   help="auto: 자막이 부족할 때만 제미나이 사용 (기본)")
    args = p.parse_args()
    sys.exit({"check": cmd_check, "run": cmd_run}[args.cmd](args))


if __name__ == "__main__":
    main()
