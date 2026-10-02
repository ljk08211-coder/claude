#!/usr/bin/env python3
"""제미나이(Gemini)에게 영상을 보여주고 요약을 받아온다. 표준 라이브러리만 사용.

API 키는 환경변수 GEMINI_API_KEY 에서만 읽는다. 키는 출력하거나 파일에 쓰지 않으며,
URL 이 아니라 요청 헤더(x-goog-api-key)로만 보낸다.

  python gemini_video.py <유튜브URL> [--video 로컬영상] [--out gemini_summary.md]

1순위: 유튜브 링크를 그대로 제미나이에 전달 (공개 영상만 가능)
2순위: 실패하면 로컬 영상 파일을 Files API 로 올려서 전달 (업로드 파일은 끝나면 삭제)
"""
import argparse
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://generativelanguage.googleapis.com"
FALLBACK_MODEL = "gemini-2.5-flash"

PROMPT = """이 유튜브 영상을 처음부터 끝까지 보고 한국어로 정리해줘.
{context}
아래 형식의 마크다운으로만 답해. 영상에서 실제로 보이거나 들리는 것만 쓰고 추측은 쓰지 마.

## 핵심 요약
1. (영상 흐름 순서대로 정확히 5줄. 한 줄에 한 문장. 근거 시간을 (MM:SS) 형식으로 붙여)

## 장면 타임라인
- MM:SS — 화면 설명 / 그때 하는 말이나 화면 자막

## 화면 속 텍스트
- (화면에 나온 자막, 제품명, 가격, 레시피 수치 등 중요한 글자. 없으면 "없음")
"""


class GeminiError(Exception):
    pass


def api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise GeminiError("NO_KEY")
    return key


def request(method, url, key, body=None, headers=None, raw=False, timeout=600):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("x-goog-api-key", key)
    if body is not None and not isinstance(body, bytes):
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
            return (resp, payload) if raw else json.loads(payload or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = json.loads(detail)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            pass
        raise GeminiError(f"HTTP {e.code}: {detail[:500]}") from None
    except urllib.error.URLError as e:
        raise GeminiError(f"연결 실패: {e.reason}") from None


def pick_model(key):
    """GEMINI_MODEL 이 있으면 그것, 없으면 사용 가능한 최신 정식 flash 모델."""
    if os.environ.get("GEMINI_MODEL"):
        return os.environ["GEMINI_MODEL"]
    try:
        models = request("GET", f"{API}/v1beta/models?pageSize=1000", key).get("models", [])
    except GeminiError:
        return FALLBACK_MODEL
    best = None
    for m in models:
        match = re.fullmatch(r"models/gemini-(\d+(?:\.\d+)?)-flash", m.get("name", ""))
        if match and "generateContent" in m.get("supportedGenerationMethods", []):
            version = float(match.group(1))
            if best is None or version > best[0]:
                best = (version, m["name"].split("/", 1)[1])
    return best[1] if best else FALLBACK_MODEL


def youtube_watch_url(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([\w-]{11})", url)
    return f"https://www.youtube.com/watch?v={m.group(1)}" if m else url


def upload_video(key, path):
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "video/mp4"
    size = path.stat().st_size
    resp, _ = request(
        "POST", f"{API}/upload/v1beta/files", key, body={"file": {"display_name": path.name}},
        headers={"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                 "X-Goog-Upload-Header-Content-Length": str(size),
                 "X-Goog-Upload-Header-Content-Type": mime},
        raw=True,
    )
    upload_url = resp.headers.get("X-Goog-Upload-URL")
    if not upload_url:
        raise GeminiError("업로드 주소를 받지 못함")
    info = request(
        "POST", upload_url, key, body=path.read_bytes(),
        headers={"Content-Length": str(size), "X-Goog-Upload-Offset": "0",
                 "X-Goog-Upload-Command": "upload, finalize"},
    )["file"]
    # 영상은 서버 처리(PROCESSING)가 끝나야 쓸 수 있다
    for _ in range(120):
        if info.get("state") == "ACTIVE":
            return info
        if info.get("state") == "FAILED":
            raise GeminiError("제미나이 쪽 영상 처리 실패")
        time.sleep(5)
        info = request("GET", f"{API}/v1beta/{info['name']}", key)
    raise GeminiError("영상 처리 대기 시간 초과(10분)")


def generate(key, model, file_part, prompt, duration):
    config = {"temperature": 0.2}
    if duration and duration > 20 * 60:
        # 긴 영상은 저해상도로 보내 토큰(비용)을 줄인다
        config["mediaResolution"] = "MEDIA_RESOLUTION_LOW"
    body = {"contents": [{"parts": [{"file_data": file_part}, {"text": prompt}]}],
            "generationConfig": config}
    result = request("POST", f"{API}/v1beta/models/{model}:generateContent", key, body=body)
    try:
        parts = result["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError):
        reason = result.get("promptFeedback", {}).get("blockReason") or \
            (result.get("candidates") or [{}])[0].get("finishReason", "응답 없음")
        raise GeminiError(f"요약을 받지 못함 ({reason})")
    return "".join(p.get("text", "") for p in parts).strip()


def summarize(url, video_path=None, context="", duration=0):
    """(마크다운, 방식, 모델) 을 돌려준다. 실패하면 GeminiError."""
    key = api_key()
    model = pick_model(key)
    prompt = PROMPT.format(context=context)
    try:
        text = generate(key, model, {"file_uri": youtube_watch_url(url)}, prompt, duration)
        return text, "youtube_url", model
    except GeminiError as first:
        if not video_path or not Path(video_path).exists():
            raise
        info = upload_video(key, video_path)
        try:
            text = generate(key, model, {"mime_type": info["mimeType"], "file_uri": info["uri"]},
                            prompt, duration)
            return text, f"upload (유튜브 링크 실패: {first})", model
        finally:
            try:
                request("DELETE", f"{API}/v1beta/{info['name']}", key)
            except GeminiError:
                pass


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("url")
    p.add_argument("--video", help="유튜브 링크가 안 될 때 올릴 로컬 영상 파일")
    p.add_argument("--out", default="gemini_summary.md")
    args = p.parse_args()
    try:
        text, method, model = summarize(args.url, args.video)
    except GeminiError as e:
        if str(e) == "NO_KEY":
            sys.exit("GEMINI_SKIPPED_NO_KEY: 환경변수 GEMINI_API_KEY 가 없음")
        sys.exit(f"GEMINI_FAILED: {e}")
    Path(args.out).write_text(f"<!-- 제미나이 {model} · {method} -->\n{text}\n", encoding="utf-8")
    print(f"GEMINI_OK: {args.out} ({model}, {method})")


if __name__ == "__main__":
    main()
