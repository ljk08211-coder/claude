#!/bin/bash
# youtube-digest 스킬용 도구(yt-dlp) 자동 설치 — 클라우드 세션에서만 실행
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

if ! command -v yt-dlp >/dev/null 2>&1; then
  pip install -q -U yt-dlp >/dev/null 2>&1 || pip install -q -U --break-system-packages yt-dlp
fi
