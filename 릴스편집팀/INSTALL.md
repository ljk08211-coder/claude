# 설치 — Claude Code 에 붙여넣기

## 0. 준비 (직접)

1. 받은 폴더를 바탕화면에 두고 이름을 `릴스편집팀` 으로 바꿉니다. (폴더 안에 `.claude` 가 보이지 않아도 정상입니다. 숨김 폴더예요)
2. 터미널을 열고 아래 두 줄을 칩니다.
   ```bash
   cd ~/Desktop/릴스편집팀
   claude
   ```
   Claude Code 가 없다면 먼저 `curl -fsSL https://claude.ai/install.sh | bash`
3. 처음 켤 때 "이 폴더를 신뢰하나요?" 창이 뜨면 **Yes** 를 누릅니다.
4. 아래 회색 상자 안 문장을 **통째로 복사해서** Claude Code 에 붙여넣고 엔터.
   중간에 "실행해도 될까요?" 가 나오면 내용을 보고 허용하면 됩니다. 15~20분 걸릴 수 있어요(처음 맥 기준).

## 1. 붙여넣을 문장

```
지금 폴더(릴스편집팀)에 릴스 편집 키트를 설치해줘. 스킬 2개(.claude/skills/reels-edit-lite, grid-dot-cards)는 이미 들어 있어.
순서대로 하고, 하나 끝날 때마다 한 줄로 알려줘. 비밀번호가 필요한 명령은 나한테 직접 치라고 알려주고 기다려.

1) Homebrew 확인: `brew --version`. 없으면 설치 명령
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   를 내가 직접 터미널에 치게 안내하고 기다려 (비밀번호 필요).
2) `brew install whisper-cpp node` (이미 있으면 건너뛰기).
3) 자막 굽기 되는 ffmpeg:
   - 먼저 `brew install ffmpeg-full` 을 시도해.
   - "no bottle available" 등으로 실패하면 brew 대신 이 폴더의 bin/ 에 정적 ffmpeg 하나만 받아줘.
     `uname -m` 이 arm64 면 arm64, x86_64 면 amd64 주소를 써:
       mkdir -p bin
       curl -L -o bin/ffmpeg.zip https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip
       (인텔 맥: https://ffmpeg.martin-riedl.de/redirect/latest/macos/amd64/release/ffmpeg.zip)
       cd bin && unzip -o ffmpeg.zip && xattr -d com.apple.quarantine ffmpeg; cd ..
   - 확인: 쓰게 될 ffmpeg 로 `ffmpeg -hide_banner -filters | grep subtitles` 가 한 줄 나와야 해.
4) whisper 모델 (465MB):
   mkdir -p models && curl -L -o models/ggml-small.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
5) 효과음 3개 (mixkit 무료 효과음):
   mkdir -p sfx
   curl -L -o sfx/pop.mp3    https://assets.mixkit.co/active_storage/sfx/2358/2358-preview.mp3
   curl -L -o sfx/click.mp3  https://assets.mixkit.co/active_storage/sfx/1133/1133-preview.mp3
   curl -L -o sfx/whoosh.mp3 https://assets.mixkit.co/active_storage/sfx/1485/1485-preview.mp3
6) 도트 카드용 브라우저: `npm i playwright && npx playwright install chromium`
   (chromium 설치가 실패해도 Google Chrome 이 있으면 괜찮아. 그때는 넘어가.)
7) `mkdir -p input out`
8) 설치 확인: `node .claude/skills/grid-dot-cards/scripts/render.mjs .claude/skills/grid-dot-cards/examples/scenes_example.json out/설치확인_카드.mp4`
   를 실행하고, 나온 out/설치확인_카드_s01.png 를 열어서 모눈종이 위 카드가 보이는지 확인해줘.
9) 다 되면 무엇이 설치됐는지 표로 보여주고, 마지막에
   "준비 완료! input 폴더에 얼굴 영상을 넣고 '편집해줘 input/파일명.mp4' 라고 말하세요" 라고 알려줘.
```

## 2. 설치 후 쓰는 법

- 다음부터는 `cd ~/Desktop/릴스편집팀 && claude` 로 켜고 말로 시키면 됩니다. 예시는 README.md 에 있어요.
- `brew install` 을 다시 할 필요는 없습니다.

## 잘 안 될 때

| 증상 | 해결 |
|---|---|
| `brew: command not found` | 1번 Homebrew 설치 명령을 직접 치고, 끝에 나오는 "Next steps" 두 줄도 그대로 치기 |
| `ffmpeg-full` 설치 실패 | 3번의 정적 ffmpeg 방법으로 (Claude 가 알아서 함) |
| 정적 ffmpeg 실행 시 "확인되지 않은 개발자" | `xattr -d com.apple.quarantine bin/ffmpeg` 를 다시 실행 |
| 모델 다운로드가 느림 | 와이파이 확인 후 4번만 다시. 465MB 라 몇 분 걸릴 수 있음 |
| `npx playwright install chromium` 실패 | Google Chrome 설치(https://www.google.com/chrome/) 후 그냥 쓰면 됨 |
| 매번 "실행해도 될까요?" 가 뜸 | 폴더를 처음 열 때 신뢰 창에서 Yes 를 눌렀는지 확인. 아니면 `claude` 를 껐다 다시 켜기 |

키트에는 프로그램(ffmpeg)·모델·효과음 파일이 들어 있지 않습니다. 용량과 라이선스 때문에 설치할 때 각 공식 주소에서 받습니다.
