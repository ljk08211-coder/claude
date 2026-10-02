---
name: reels-edit-lite
description: 캡컷 없이 세로 릴스 완성본 mp4를 만든다 — 무음 컷, 한국어 자막(검은 박스 80%), 효과음, 문장 경계 줌, 1080x1920 출력까지 한 번에. 위아래 분할(위 = 화면 녹화·이미지·도트 카드, 아래 = 얼굴)도 된다. "편집해줘 <파일>", "릴스 편집해줘", "자막 넣어줘", "무음 잘라줘", "위에 카드 넣어서 편집해줘", "위에 화면 녹화 넣어줘", "분할 화면으로 편집해줘", "/reels-edit-lite" 요청에 사용.
---

# reels-edit-lite — 클로드로 영상 편집팀

> **윈도우에서 실행할 때:** 아래 명령의 `python3` 는 `python` 으로, `open out/` 은 `explorer out` 으로 바꿔서 실행한다.
> (Claude Code 윈도우판은 Git Bash 로 명령을 실행한다. 자막 글꼴은 자동으로 맑은 고딕을 쓴다.)

말로 찍은 영상 하나를 넣으면 순서대로 처리해서 `out/` 에 완성 mp4를 만든다.

1. **무음 컷** — 0.3초 넘는 공백을 자르고 이어붙인다 (앞뒤 0.08초 여유)
2. **자막** — whisper-cli 로 한국어 전사 → 문장 끝 추정 → 11자 안팎 짧은 줄 → 흰 글자 + 검은 박스(불투명도 80%), 화면 하단 1/3에 굽기
   - whisper 한국어는 마침표를 거의 안 찍어서, 종결어미(…요/…다/…죠/…까/…네요)·0.25초 이상 쉼·무음컷 자리를 문장 끝으로 본다.
     자막 한 줄은 문장 경계를 절대 넘지 않는다. 5초 넘는 문장은 연결어미(…는데/…고/…면) 자리에서 한 번 더 나눈다.
   - `자막수정.txt` 치환은 줄로 나누기 **전에** 문장 전체 글자열에 적용된다 → `컵 편집=컷편집` 처럼 띄어쓰기를 낀 말도 고쳐진다.
3. **효과음** — 문장 시작에만 pop, 3번째마다 click, 장면 전환에는 whoosh (같은 소리 3연속 금지, 볼륨 0.35)
4. **장면 전환** — 문장이 바뀌면서 컷이 붙은 자리에 0.15초 살짝 줌 펀치인 (검은 화면 없음)
5. **출력** — 1080x1920 h264/aac mp4. 가로 영상이면 가운데를 잘라 세로로 만든다

## 실행 순서 (사용자가 "편집해줘 <파일>" 이라고 하면)

1. 파일 경로를 확인한다. 경로가 없으면 `input/` 폴더 안 영상을 보여주고 어떤 걸 할지 묻는다.
   "위에 카드", "위에 화면 녹화", "분할" 같은 말이 있으면 아래 **위아래 분할** 절차로 간다.
2. 아래 명령을 프로젝트 폴더(이 `.claude` 가 있는 폴더)에서 실행한다. 시간 제한은 넉넉히(10분).
   ```bash
   python3 .claude/skills/reels-edit-lite/scripts/edit.py "<입력파일>" out/
   ```
3. `[edit] 멈춤:` 이 나오면 아래 "막혔을 때" 표대로 안내하고 멈춘다. 설치 명령은 사용자가 직접 치게 한다.
4. 끝나면 `out/<이름>_자막*.txt` 를 읽고, 문맥상 틀린 단어(고유명사·영어 단어가 특히 잘 틀림)가 있으면
   사용자에게 고칠 목록을 보여준다. 사용자가 OK 하면 프로젝트 폴더의 `자막수정.txt` 에
   `틀린말=맞는말` 한 줄씩 추가하고 2번을 다시 실행한다. (기존 결과는 덮어쓰지 않고 `_v2` 로 저장된다)
5. 결과 mp4 경로, 몇 초 → 몇 초로 줄었는지, 자막 줄 수, 효과음 개수를 짧게 알려주고
   `open out/` 으로 폴더를 열어준다.

## 위아래 분할 (위 = 화면 자료, 아래 = 얼굴)

최종 1080x1920 = 위 1080x960 화면 자료 + 아래 1080x960 얼굴. 자막은 두 칸 경계(y=960) 가운데에 걸친다.
얼굴 칸은 무음 컷·줌·자막이 그대로 적용되고, 위 칸은 아래 셋 중 하나다.

### A. "위에 카드 넣어서 편집해줘 <얼굴영상>" — 문장마다 도트 카드 (grid-dot-cards 스킬 사용)

카드는 **무음 컷 이후 타임라인** 기준으로 만들어야 문장과 맞는다. 그래서 순서가 정해져 있다.

1. **무음컷 + 전사 + 카드 초안**
   ```bash
   python3 .claude/skills/reels-edit-lite/scripts/edit.py "<얼굴영상>" out/ --plan
   ```
   → `out/<이름>_scenes.json` (문장마다 카드 1장 — 보통 2~5초, 5초 넘는 문장은 연결어미 자리에서 둘로, 1초 미만은 앞 카드에 합침. 35초 영상이면 8~10장 안팎)
   → 마지막 줄에 4번에서 쓸 명령(`--reuse out/work_<이름>…`)이 찍힌다.
2. **자막 오타 확인** — `out/<이름>_자막*.txt` 를 읽고 틀린 단어가 있으면 위 "실행 순서" 4번처럼 `자막수정.txt` 에 적고 1번을 다시 한다.
3. **카드 문구 다듬기 (클로드가 직접)** — scenes.json 의 각 장면에서 `_sentence`(원래 문장)를 읽고
   - `title`: 핵심만 두 줄(`\n`), 한 줄 8~10자. 문장을 그대로 옮기지 않는다
   - `pills`: 키워드 2~3개, 한 개당 2~6자
   - `footer`: 필요할 때만 (`[강조]` = 검정 알약, `→` = 화살표 배지)
   - `start`/`end` 는 건드리지 않는다 (컷 이후 타이밍)
   고친 내용을 사용자에게 표로 짧게 보여주고 OK 받은 뒤 다음으로.
4. **카드 렌더 + 분할 합성 + 자막 + 효과음** (1번에서 찍힌 명령 그대로)
   ```bash
   python3 .claude/skills/reels-edit-lite/scripts/edit.py "<얼굴영상>" out/ --reuse out/work_<이름> --cards out/<이름>_scenes.json
   ```
   → `out/<이름>_cards.mp4`(위 칸 카드), `out/<이름>_cards_s01.png…`(카드 확인용), `out/<이름>_분할.mp4`(완성본)
5. 완성본에서 프레임 3장을 뽑아 직접 확인한다(아래 "분할 확인"). 문제없으면 결과 알려주고 `open out/`.

### B. "위에 화면 녹화 넣어서 편집해줘" — 녹화 영상·이미지를 그대로

```bash
python3 .claude/skills/reels-edit-lite/scripts/edit.py "<얼굴영상>" out/ --top "<화면녹화.mp4 또는 이미지.png>"
```
- 위 칸은 처음부터 재생되고, 얼굴보다 짧으면 마지막 프레임에서 멈춰 있다. 길면 얼굴 길이에서 잘린다.
- 이미지는 그대로 정지 화면으로 깔린다.
- 가로로 긴 화면 녹화(16:9)는 기본(cover)이면 양옆이 많이 잘린다. 글씨가 잘리면 `--top-fit contain`(전체가 보이게 줄이고 위아래 연회색 여백).
- **얼굴과 화면을 동시에 녹화**해서 길이·타이밍이 같다면 `--top-sync` — 얼굴에서 자른 무음 구간을 화면 녹화에서도 똑같이 잘라 싱크를 맞춘다. 따로 녹화한 자료에는 쓰지 않는다.

**크롬 화면 녹화를 위 자료로 쓰는 경우 (Claude in Chrome 등)**
- 클로드가 브라우저를 조작하는 장면을 녹화한 mp4(또는 macOS `Cmd+Shift+5` 화면 녹화 .mov)를 그대로 `--top` 에 넣으면 된다.
- 위 칸이 1080x960(가로:세로 = 9:8)이라 **브라우저 창을 정사각형에 가깝게 줄여서 녹화**하면 잘림 없이 크게 보인다. 가로로 넓게 녹화했으면 `--top-fit contain`.
- 녹화가 나레이션보다 훨씬 길면 먼저 필요한 구간만 잘라 달라고 하거나, 녹화를 나레이션 길이에 맞춰 다시 녹화한다(배속 조정은 이 스킬에 없음).

### C. 이미 만든 도트 카드 mp4 를 위에

```bash
python3 .claude/skills/reels-edit-lite/scripts/edit.py "<얼굴영상>" out/ --top out/cards.mp4
```
카드를 컷 **이전** 원본 타이밍으로 만들었다면 문장과 어긋난다. 문장에 맞추려면 A 순서로 한다.

### 분할 확인 (끝나면 꼭)

```bash
for t in 1.5 4 6.5; do bin/ffmpeg -loglevel error -y -ss $t -i out/<이름>_분할.mp4 -frames:v 1 out/check_split_$t.png; done
```
(`bin/ffmpeg` 가 없으면 `ffmpeg`.) 이미지를 직접 열어서 확인:
- **얼굴이 잘리지 않았나** — 아래 칸에서 머리 위가 잘리면 `--face-y` 를 낮추고(0.28), 턱이 잘리면 높인다(0.40). 기본 0.33 (머리 위 여유 확보)
- 자막이 경계(y≈960) 가운데, 흰 글자 + 검은 박스(80%)인지
- 위 칸 글씨가 잘리지 않았나 (잘리면 `--top-fit contain`)

## 옵션 (사용자가 원할 때만)

| 요청 | 붙일 옵션 |
|---|---|
| 숨소리까지 잘려요 / 너무 많이 잘려요 | `--noise -40` |
| 공백이 덜 잘려요 | `--noise -30` |
| 효과음 빼줘 | `--no-sfx` |
| 줌 빼줘 | `--no-zoom` |
| 다른 whisper 모델 | `--model models/ggml-medium.bin` |
| 위 칸에 영상·이미지 | `--top <파일>` |
| 위 칸 글씨가 잘려요 | `--top-fit contain` |
| 위 화면이 얼굴과 동시 녹화 | `--top-sync` |
| 아래 얼굴 위치 | `--face-y 0.28` (머리 잘림) / `0.40` (턱 잘림), 기본 0.33 |
| 카드가 너무 많이/적게 나뉨 | `scripts/edit.py` 맨 위 `SENT_MAX`(기본 5초)·`PAUSE_SEC`(0.25초) 조정 |

자막 크기·색·위치는 `scripts/edit.py` 맨 위 설정값(FONT_SIZE, BOX_COLOR, SUB_MARGIN_V)만 바꾼다.

## 필요한 것 (처음 한 번)

```bash
brew install ffmpeg-full whisper-cpp          # ffmpeg-full = 자막 굽기 되는 ffmpeg
mkdir -p models sfx input out
curl -L -o models/ggml-small.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
curl -L -o sfx/pop.mp3    https://assets.mixkit.co/active_storage/sfx/2358/2358-preview.mp3
curl -L -o sfx/click.mp3  https://assets.mixkit.co/active_storage/sfx/1133/1133-preview.mp3
curl -L -o sfx/whoosh.mp3 https://assets.mixkit.co/active_storage/sfx/1485/1485-preview.mp3
```

도트 카드(분할 A)를 쓸 때만 추가로:
```bash
brew install node                              # node 가 없을 때만
npm i playwright && npx playwright install chromium
```

`brew install ffmpeg-full` 이 "no bottle available" 로 실패하면(구버전 macOS) 설치 대신
자막 굽기 되는 ffmpeg 단일 파일을 프로젝트 `bin/` 에 받는다. 스크립트가 `bin/ffmpeg` 를 자동으로 찾는다.
```bash
mkdir -p bin && curl -L -o bin/ffmpeg.zip https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip
cd bin && unzip ffmpeg.zip && xattr -d com.apple.quarantine ffmpeg; cd ..
```

## 막혔을 때

| 메시지 | 할 일 |
|---|---|
| ffmpeg 를 못 찾았어요 | `brew install ffmpeg-full` |
| 자막 굽기 불가 — .ass 파일만 만듦 | 위 ffmpeg-full 또는 bin/ffmpeg 설치 후 다시 실행 |
| whisper-cli 가 없어요 | `brew install whisper-cpp` |
| whisper 모델이 없어요 | 위 `curl ... ggml-small.bin` |
| 전부 무음으로 판정됐어요 | `--noise -45` 로 다시 |
| 소리 트랙이 없는 영상 | 나레이션 있는 영상을 넣어야 함 |
| --reuse 폴더에 cut.json 이 없어요 | `--plan` 을 먼저 실행. 찍힌 `--reuse` 경로를 그대로 쓰기 |
| playwright 가 없어요 / node 가 없어요 | 위 "도트 카드를 쓸 때만" 설치 |
| 효과음: 없음 | `sfx/` 폴더에 pop/click/whoosh mp3 넣기 (없어도 나머지는 정상 동작) |

## 결과물

- `out/<이름>_편집.mp4` — 완성본 (분할 모드면 `out/<이름>_분할.mp4`)
- `out/<이름>_scenes.json`, `out/<이름>_cards.mp4`, `out/<이름>_cards_s01.png…` — 분할 A 의 카드 초안·카드 영상·확인용 이미지
- `out/<이름>_자막.txt` — 자막 확인용 (시간 + 문장)
- `out/<이름>.ass` — 자막 파일 (다른 편집기에서 다시 쓸 때)
- `out/work_<이름>/report.json` — 잘린 구간, 효과음 위치, 줌 위치 기록
