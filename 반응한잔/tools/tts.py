"""cutplan.json의 narr 문장을 제미나이 TTS로 읽어 narr/<세그먼트ID>.wav 로 저장한다.
가편집용 임시 내레이션이다. 최종본은 직접 녹음한 목소리로 바꾸는 것을 권장한다.

사용: python3 tts.py <에피소드 폴더> [--force]
"""
import base64, json, os, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

# 무료 등급은 모델마다 하루 10회 제한이라, 막히면 다음 모델로 넘어간다
MODELS = [os.environ["GEMINI_TTS_MODEL"]] if os.environ.get("GEMINI_TTS_MODEL") else [
    "gemini-2.5-flash-preview-tts", "gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-pro-preview-tts"]
STYLE = ""


def speak(text, voice, out, tempo=1.0):
    key = os.environ["GEMINI_API_KEY"]
    body = {
        "contents": [{"parts": [{"text": STYLE + text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    res = None
    for model in list(MODELS):
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
        for wait in (0, 20, 40):
            time.sleep(wait)
            try:
                res = json.load(urllib.request.urlopen(req, timeout=180))
                break
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    raise
                if "PerDay" in e.read().decode(errors="ignore"):
                    MODELS.remove(model)  # 오늘 한도 소진, 다음 모델로
                    break
        if res:
            break
    if not res:
        raise SystemExit("TTS 사용량 제한(429): 모든 모델이 막힘. 내일 다시 실행하거나 직접 녹음하세요")
    pcm = base64.b64decode(res["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    raw = out.with_suffix(".pcm")
    raw.write_bytes(pcm)
    # 앞뒤 무음을 잘라 컷 사이 리듬을 붙인다
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(raw),
                    "-af", "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                           "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                           f"atempo={tempo}",
                    "-ar", "48000", str(out)], check=True)
    raw.unlink()


def main():
    ep = Path(sys.argv[1])
    force = "--force" in sys.argv
    plan = json.loads((ep / "cutplan.json").read_text())
    (ep / "narr").mkdir(exist_ok=True)
    made = 0
    for s in plan["segments"]:
        if not s.get("narr"):
            continue
        out = ep / "narr" / f"{s['id']}.wav"
        stamp = out.with_suffix(".txt")  # 읽은 문장을 기록해 두고, 대본이 바뀐 줄만 다시 만든다
        if out.exists() and not force and stamp.exists() and stamp.read_text() == s["narr"]:
            continue
        if made:
            time.sleep(8)  # 무료 TTS 요청 간격
        speak(s["narr"], plan.get("voice", "Charon"), out, plan.get("tempo", 1.0))
        stamp.write_text(s["narr"])
        made += 1
        print("TTS", s["id"], out)


if __name__ == "__main__":
    main()
