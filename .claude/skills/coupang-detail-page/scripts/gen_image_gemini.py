#!/usr/bin/env python3
"""제미나이 이미지 모델로 연출컷을 만든다. 힉스필드 크레딧이 없을 때 쓴다. 표준 라이브러리만 사용.

API 키는 환경변수 GEMINI_API_KEY 에서만 읽는다. 키는 출력하거나 파일에 쓰지 않으며,
URL 이 아니라 요청 헤더(x-goog-api-key)로만 보낸다.

  check                                     : 키와 사용할 모델 확인
  run --ref 제품.jpg --prompt "..." --out assets/hero.png [--aspect 3:4] [--n 2]

--ref 는 여러 번 줄 수 있다(제품 사진 여러 각도). 참조 사진의 제품을 그대로 유지하라는
지시를 프롬프트 앞에 자동으로 붙인다.
"""
import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://generativelanguage.googleapis.com"
FALLBACK_MODEL = "gemini-2.5-flash-image"
KEEP_PRODUCT = (
    "Use the product in the reference image(s) exactly as it is: same shape, proportions, color, "
    "material, logo placement and parts. Do not redesign, recolor or add parts to the product. "
    "No text, no letters, no watermark in the image. Photorealistic commercial product photography.\n\n"
)


class GeminiError(Exception):
    pass


def api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise GeminiError("NO_KEY")
    return key


def request(method, url, key, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("x-goog-api-key", key)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = json.loads(detail)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            pass
        raise GeminiError(f"HTTP {e.code}: {detail[:400]}") from None
    except urllib.error.URLError as e:
        raise GeminiError(f"연결 실패: {e.reason}") from None


def pick_model(key):
    """GEMINI_IMAGE_MODEL 이 있으면 그것, 없으면 최신 정식 flash 이미지 모델."""
    if os.environ.get("GEMINI_IMAGE_MODEL"):
        return os.environ["GEMINI_IMAGE_MODEL"]
    try:
        models = request("GET", f"{API}/v1beta/models?pageSize=1000", key).get("models", [])
    except GeminiError:
        return FALLBACK_MODEL
    best = None
    for m in models:
        hit = re.fullmatch(r"models/gemini-(\d+(?:\.\d+)?)-flash-image", m.get("name", ""))
        if hit and (best is None or float(hit.group(1)) > best[0]):
            best = (float(hit.group(1)), m["name"].split("/", 1)[1])
    return best[1] if best else FALLBACK_MODEL


def image_part(path):
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        return {"inline_data": {"mime_type": mime, "data": base64.b64encode(f.read()).decode()}}


def generate(key, model, refs, prompt, aspect):
    parts = [image_part(p) for p in refs]
    parts.append({"text": (KEEP_PRODUCT if refs else "") + prompt})
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
    if aspect:
        body["generationConfig"]["imageConfig"] = {"aspectRatio": aspect}
    res = request("POST", f"{API}/v1beta/models/{model}:generateContent", key, body)
    for cand in res.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            blob = part.get("inline_data") or part.get("inlineData")
            if blob and blob.get("data"):
                return base64.b64decode(blob["data"]), blob.get("mime_type") or blob.get("mimeType")
    reason = (res.get("promptFeedback") or {}).get("blockReason") or \
        ",".join(c.get("finishReason", "?") for c in res.get("candidates", [])) or "응답 없음"
    raise GeminiError(f"이미지가 오지 않음 ({reason})")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    r = sub.add_parser("run")
    r.add_argument("--ref", action="append", default=[], help="제품 참조 사진 (여러 번 가능)")
    r.add_argument("--prompt")
    r.add_argument("--prompt-file")
    r.add_argument("--out", required=True, help="저장 경로. --n 2 이상이면 _1, _2 가 붙는다")
    r.add_argument("--aspect", help="1:1, 3:4, 4:3, 9:16, 16:9 등")
    r.add_argument("--n", type=int, default=1)
    a = ap.parse_args()

    try:
        key = api_key()
    except GeminiError:
        print("GEMINI_SKIPPED_NO_KEY")
        sys.exit(3)
    model = pick_model(key)
    if a.cmd == "check":
        print(f"OK (GEMINI_API_KEY: 설정됨, 모델: {model})")
        return

    prompt = a.prompt or (open(a.prompt_file, encoding="utf-8").read() if a.prompt_file else None)
    if not prompt:
        sys.exit("--prompt 또는 --prompt-file 이 필요합니다")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    stem, ext = os.path.splitext(a.out)
    saved = []
    for i in range(1, a.n + 1):
        try:
            data, mime = generate(key, model, a.ref, prompt, a.aspect)
        except GeminiError as e:
            print(f"GEMINI_FAILED: {e}")
            sys.exit(1 if not saved else 0)
        real_ext = mimetypes.guess_extension(mime or "") or ext or ".png"
        path = (stem if a.n == 1 else f"{stem}_{i}") + (ext or real_ext)
        with open(path, "wb") as f:
            f.write(data)
        saved.append(path)
    print(f"OK 모델={model}")
    for p in saved:
        print(p)


if __name__ == "__main__":
    main()
