# 윈도우 설치 — Claude Code 에 붙여넣기

맥용 INSTALL.md 대신 이 문서를 따라 하세요. 스크립트는 윈도우와 맥 둘 다에서 돌아가게 고쳐져 있어요.

## 0. 준비 (직접)

1. 받은 zip 을 풀어서 `릴스편집팀` 폴더를 **바탕화면**에 둡니다.
   - 폴더 안에 `.claude` 가 안 보여도 정상이에요. 숨김 폴더예요.
2. **PowerShell** 을 엽니다. 시작 메뉴에서 "PowerShell" 을 검색하면 돼요.
3. Claude Code 가 아직 없다면 먼저 두 가지를 설치합니다.
   ```powershell
   winget install Git.Git
   irm https://claude.ai/install.ps1 | iex
   ```
   - 설치가 끝나면 PowerShell 을 **닫았다가 다시 엽니다**.
   - Git 이 있어야 해요. Claude Code 윈도우판이 Git Bash 로 명령을 실행하기 때문이에요.
4. 릴스편집팀 폴더로 가서 Claude Code 를 켭니다.
   ```powershell
   cd ([Environment]::GetFolderPath('Desktop') + '\릴스편집팀')
   claude
   ```
   - 바탕화면이 OneDrive 에 연결돼 있어도 이 명령은 알아서 찾아가요.
5. "이 폴더를 신뢰하나요?" 창이 뜨면 **Yes** 를 누릅니다.
6. 아래 회색 상자 안 문장을 **통째로 복사해서** 붙여넣고 엔터를 누릅니다.
   - 중간에 "실행해도 될까요?" 가 나오면 내용을 보고 허용하면 돼요.
   - 15~20분쯤 걸려요.

## 1. 붙여넣을 문장

```
지금 폴더(릴스편집팀)에 릴스 편집 키트를 윈도우용으로 설치해줘. 스킬 2개(.claude/skills/reels-edit-lite, grid-dot-cards)는 이미 들어 있고 윈도우를 지원하게 고쳐져 있어.
순서대로 하고, 하나 끝날 때마다 한 줄로 알려줘. 관리자 권한이나 확인 창이 필요하면 나한테 직접 하라고 알려주고 기다려.
winget 명령은 powershell.exe -NoProfile -Command "..." 로 실행해도 돼.

1) 필요한 프로그램 (이미 있으면 건너뛰기):
   - Python: `python --version` 이 3.10 이상으로 나오는지 확인. 없거나 Microsoft Store 안내만 나오면
     `winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements`
   - Node.js: `node --version`. 없으면 `winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements`
   - ffmpeg(자막 굽기용 libass 포함 full 빌드): `winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements`
   새로 설치한 게 있으면 PATH 가 반영되도록 내가 Claude Code 를 껐다 켜야 할 수 있어. 그 경우 알려주고,
   다시 켜면 이 문장을 다시 붙여넣을 테니 이미 된 단계는 건너뛰어.
   확인: `ffmpeg -hide_banner -filters | grep subtitles` 가 한 줄 나와야 해.
2) whisper.cpp (자막 인식):
   GitHub API(https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest)에서 최신 릴리스의
   윈도우 64비트 CPU용 zip(이름이 whisper-bin-x64.zip 인 것)을 받아서 bin/whisper 에 풀어줘.
   그 안에 whisper-cli.exe 가 있어야 해. 확인: 그 whisper-cli.exe 를 --help 로 실행.
   (스크립트는 bin/ 아래 하위 폴더까지 whisper-cli.exe 를 자동으로 찾아.)
3) whisper 모델 (465MB):
   mkdir -p models && curl -L -o models/ggml-small.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
4) 효과음 3개 (mixkit 무료 효과음):
   mkdir -p sfx
   curl -L -o sfx/pop.mp3    https://assets.mixkit.co/active_storage/sfx/2358/2358-preview.mp3
   curl -L -o sfx/click.mp3  https://assets.mixkit.co/active_storage/sfx/1133/1133-preview.mp3
   curl -L -o sfx/whoosh.mp3 https://assets.mixkit.co/active_storage/sfx/1485/1485-preview.mp3
5) 도트 카드용 브라우저: `npm i playwright && npx playwright install chromium`
   (chromium 설치가 실패해도 Google Chrome 이 있으면 괜찮아. 그때는 넘어가.)
6) `mkdir -p input out`
7) 설치 확인:
   `node .claude/skills/grid-dot-cards/scripts/render.mjs .claude/skills/grid-dot-cards/examples/scenes_example.json out/설치확인_카드.mp4`
   를 실행하고, 나온 out/설치확인_카드_s01.png 를 열어서 모눈종이 위 카드가 보이는지 확인해줘.
8) 다 되면 무엇이 설치됐는지 표로 보여주고, 마지막에
   "준비 완료! input 폴더에 얼굴 영상을 넣고 '편집해줘 input/파일명.mp4' 라고 말하세요" 라고 알려줘.
```

## 2. 설치 후 쓰는 법

- 다음부터는 PowerShell 에서 4번 명령(`cd ...` 와 `claude`)으로 켜고 말로 시키면 돼요. 예시는 README.md 에 있어요.
- 자막 글꼴은 윈도우 기본 글꼴인 **맑은 고딕**을 써요(맥은 Apple SD 고딕).

## 잘 안 될 때

| 증상 | 해결 |
|---|---|
| `winget` 이 없다고 나옴 | Microsoft Store 에서 "앱 설치 관리자(App Installer)" 업데이트 |
| `python` 을 치면 Microsoft Store 가 열림 | 1번의 winget Python 설치 후 Claude Code 를 다시 켜기. 그래도 안 되면 설정 > 앱 > 고급 앱 설정 > 앱 실행 별칭에서 python 두 개 끄기 |
| 설치했는데 `ffmpeg`·`node` 를 못 찾음 | PowerShell 과 Claude Code 를 완전히 껐다 다시 켜기 (PATH 반영) |
| 자막이 네모(□)로 나옴 | `C:\Windows\Fonts\malgun.ttf` 가 있는지 확인 |
| `npx playwright install chromium` 실패 | Google Chrome 설치(https://www.google.com/chrome/) 후 그냥 쓰면 됨 |
| 백신이 whisper-cli.exe 를 막음 | GitHub 공식 릴리스에서 받은 파일인지 확인 후 예외 허용 |

키트에는 프로그램(ffmpeg, whisper)과 모델, 효과음 파일이 들어 있지 않아요. 용량과 라이선스 때문에 설치할 때 각 공식 주소에서 받아요.
