"""cutplan.json대로 쇼츠 가편집(1080x1920, 30fps)을 렌더링한다.

소스 우선순위 (세그먼트마다):
  src: upload/<clip>.mp4(직접 잘라 올린 클립) → upload/source.mp4에서 in~out 구간 → 자리표시 카드
  me : upload/<clip>.mp4(바텐더 세로 촬영)     → 자리표시 카드
내레이션: narr/<세그먼트ID>.wav. 직접 녹음한 파일로 같은 이름으로 바꾸면 그 목소리로 들어간다.
me 세그먼트에 "audio": "clip"을 주면 내레이션 대신 촬영본 소리를 쓰고 길이도 촬영본을 따른다.

사용: python3 render.py <에피소드 폴더>
결과: <에피소드>/draft/draft.mp4, subtitles.ass, timeline.md
"""
import json, re, subprocess, sys
from pathlib import Path

W, H, FPS, AR = 1080, 1920, 30, 48000
FONTS = Path(__file__).resolve().parent.parent / "_assets" / "fonts"
VIDEO_Y, VIDEO_SIZE = 380, 1080  # 원본 클립은 정사각으로 잘라 이 위치에 둔다


def sh(*cmd):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *map(str, cmd)], check=True)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    return float(info["format"]["duration"]), any(s["codec_type"] == "audio" for s in info["streams"])


def secs(ts):
    m, s = ts.split(":")
    return int(m) * 60 + float(s)


def asstime(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


ENC = ["-r", FPS, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-ar", AR, "-ac", "2"]
SILENCE = ["-f", "lavfi", "-i", f"anullsrc=r={AR}:cl=stereo"]
LOUD = "loudnorm=I=-16:TP=-1.5:LRA=11"


def still(png, dur, audio, out):
    """PNG 한 장 + 오디오(없으면 무음)로 세그먼트를 만든다."""
    a = ["-i", audio] if audio else SILENCE
    af = LOUD if audio else "anull"
    sh("-loop", 1, "-t", f"{dur:.3f}", "-i", png, *a, "-t", f"{dur:.3f}",
       "-filter_complex", f"[0:v]scale={W}:{H},format=yuv420p[v];[1:a]{af},apad[a]",
       "-map", "[v]", "-map", "[a]", *ENC, out)


def src_segment(seg, ep, out):
    up = ep / "upload"
    clip, whole = up / f"{seg['clip']}.mp4", up / "source.mp4"
    dur = secs(seg["out"]) - secs(seg["in"])
    if clip.exists():
        inp, dur = ["-i", clip], probe(clip)[0]
        has_audio = probe(clip)[1]
    elif whole.exists():
        inp, has_audio = ["-ss", secs(seg["in"]), "-t", f"{dur:.3f}", "-i", whole], probe(whole)[1]
    else:
        still(ep / "gfx" / f"ph_{seg['clip']}.png", dur, None, out)
        return dur, "자리표시"
    anchor = seg.get("anchor", 0.5)
    # 가로 원본을 정사각으로 자르되 anchor(0~1) 위치의 인물을 가운데로 둔다. 배경은 같은 영상을 흐리게 깐다
    crop = f"crop=ih:ih:'max(0,min(iw-ih,iw*{anchor}-ih/2))':0"
    vf = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"boxblur=30:2,eq=brightness=-0.25[bg];[b]{crop},scale={VIDEO_SIZE}:{VIDEO_SIZE}[fg];"
          f"[bg][fg]overlay=(W-w)/2:{VIDEO_Y},format=yuv420p[v]")
    a = [] if has_audio else SILENCE
    amap = "0:a" if has_audio else "1:a"
    sh(*inp, *a, "-t", f"{dur:.3f}", "-filter_complex", vf + f";[{amap}]{LOUD},apad[aout]",
       "-map", "[v]", "-map", "[aout]", *ENC, out)
    return dur, "업로드" if clip.exists() else "source.mp4"


def me_segment(seg, ep, out, narr):
    clip = ep / "upload" / f"{seg['clip']}.mp4"
    use_clip_audio = seg.get("audio") == "clip" and clip.exists()
    dur = probe(clip)[0] if use_clip_audio else probe(narr)[0] + 0.25
    gfx = ep / "gfx" / f"{seg['gfx']}.png" if seg.get("gfx") else None
    # gfx가 있으면 앞 40%는 바텐더, 나머지는 정보 그래픽
    cut = dur * 0.4 if gfx else dur
    parts = []
    tmp1 = out.with_name(out.stem + "_a.mp4")
    if clip.exists():
        extra = [] if use_clip_audio else SILENCE
        sh("-i", clip, *extra, "-t", f"{cut:.3f}", "-filter_complex",
           f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=yuv420p[v]",
           "-map", "[v]", "-map", "0:a" if use_clip_audio else "1:a", *ENC, tmp1)
        status = "업로드"
    else:
        still(ep / "gfx" / f"ph_{seg['clip']}.png", cut, None, tmp1)
        status = "자리표시"
    parts.append(tmp1)
    if gfx:
        tmp2 = out.with_name(out.stem + "_b.mp4")
        still(gfx, dur - cut, None, tmp2)
        parts.append(tmp2)
    concat(parts, out, None if use_clip_audio else narr, dur)
    return dur, status


def concat(parts, out, audio, dur):
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    if audio:
        sh("-f", "concat", "-safe", 0, "-i", lst, "-i", audio, "-t", f"{dur:.3f}",
           "-filter_complex", f"[1:a]{LOUD},apad[a]", "-map", "0:v", "-map", "[a]", *ENC, out)
    else:
        sh("-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", out)


def chunks(text, dur, start):
    """내레이션을 쇼츠 자막 길이(약 14자)로 잘라 글자 수 비율로 시간을 나눈다."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and (len(cur) + 1 + len(w) > 14 or re.search(r"[.?!]$", cur)):
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    total = sum(len(l) for l in lines)
    t, out = start, []
    for l in lines:
        d = dur * len(l) / total
        out.append((t, t + d, l))
        t += d
    return out


ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KO,Black Han Sans,78,&H0028CDFF,&H0028CDFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,6,2,2,60,60,330,1
Style: EN,Noto Sans KR,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,0,2,60,60,450,1
Style: NARR,Black Han Sans,74,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,6,2,2,60,60,330,1
Style: BIG,Black Han Sans,120,&H0028CDFF,&H0028CDFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,8,3,8,40,40,170,1
Style: CREDIT,Noto Sans KR,30,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,7,40,40,330,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def main():
    from gfx import ensure_fonts
    ensure_fonts()
    ep = Path(sys.argv[1])
    plan = json.loads((ep / "cutplan.json").read_text())
    out_dir = ep / "draft"
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    t, files, events, rows = 0.0, [], [], []
    for seg in plan["segments"]:
        f = work / f"{seg['id']}.mp4"
        narr = ep / "narr" / f"{seg['id']}.wav"
        if seg["kind"] == "src":
            dur, status = src_segment(seg, ep, f)
            events.append(f"Dialogue: 0,{asstime(t)},{asstime(t + dur)},CREDIT,,0,0,0,,{plan['source']['credit']}")
            for s0, s1, en, ko in seg.get("subs", []):
                a, b = t + float(s0), t + min(float(s1), dur)
                events.append(f"Dialogue: 0,{asstime(a)},{asstime(b)},EN,,0,0,0,,{en}")
                events.append(f"Dialogue: 0,{asstime(a)},{asstime(b)},KO,,0,0,0,,{ko}")
        else:
            if seg["kind"] == "me":
                dur, status = me_segment(seg, ep, f, narr)
            else:
                dur, status = probe(narr)[0] + 0.25, "그래픽"
                still(ep / "gfx" / f"{seg['gfx']}.png", dur, narr, f)
            if seg.get("narr"):
                for a, b, line in chunks(seg["narr"], dur - 0.25, t):
                    events.append(f"Dialogue: 0,{asstime(a)},{asstime(b)},NARR,,0,0,0,,{line}")
        if seg.get("big"):
            events.append(f"Dialogue: 1,{asstime(t)},{asstime(t + dur)},BIG,,0,0,0,,{seg['big']}")
        rows.append(f"| {seg['id']} | {asstime(t)[2:]} | {dur:.1f}s | {seg['label']} | {status} |")
        files.append(f)
        t += dur
        print(f"{seg['id']} {dur:5.1f}s {status}")

    ass = out_dir / "subtitles.ass"
    ass.write_text(ASS_HEAD + "\n".join(events) + "\n", encoding="utf-8")
    joined = work / "joined.mp4"
    concat(files, joined, None, t)
    sh("-i", joined, "-vf", f"subtitles={ass}:fontsdir={FONTS}", "-c:a", "copy",
       "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
       out_dir / "draft.mp4")
    (out_dir / "timeline.md").write_text(
        f"# 가편집 타임라인 (총 {t:.1f}초)\n\n| 컷 | 시작 | 길이 | 내용 | 소스 |\n|---|---|---|---|---|\n"
        + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"DRAFT {out_dir / 'draft.mp4'} ({t:.1f}s)")


if __name__ == "__main__":
    main()
