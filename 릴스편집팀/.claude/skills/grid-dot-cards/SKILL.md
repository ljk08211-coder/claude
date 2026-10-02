---
name: grid-dot-cards
description: 모눈종이 배경 + 파스텔 오로라 + 도트 폰트(한글 가능) 카드 영상을 만든다. 문장마다 카드가 바뀌는 scenes.json 을 받아 1080x960(위 절반용) 또는 1080x1920(풀) 무음 mp4로 렌더. "도트 카드 만들어줘", "모눈종이 카드", "그리드 도트 스타일", "카드 영상 만들어줘", "위에 카드 넣어줘", "/grid-dot-cards" 요청에 사용.
---

# grid-dot-cards — 모눈종이 도트 카드

> **윈도우에서 실행할 때:** 아래 명령의 `open out/` 은 `explorer out` 으로 바꿔서 실행한다.
> (Claude Code 윈도우판은 Git Bash 로 명령을 실행한다. 자막 글꼴은 자동으로 맑은 고딕을 쓴다.)

흰 모눈종이 위에 파스텔 오로라가 천천히 흐르고, 도트 글씨 카드가 장면마다 바뀌는 영상 소스.
릴스 위아래 분할 화면의 **위 절반**(1080x960)이나 풀 화면(1080x1920) 정보 카드로 쓴다. 소리는 없다.

## 쓰는 법

1. `scenes.json` 을 만든다 (형식은 아래). 예시: `examples/scenes_example.json`
2. 프로젝트 폴더(이 `.claude` 가 있는 폴더)에서 렌더:
   ```bash
   node .claude/skills/grid-dot-cards/scripts/render.mjs scenes.json out/cards.mp4 --size half   # 1080x960
   node .claude/skills/grid-dot-cards/scripts/render.mjs scenes.json out/cards.mp4 --size full   # 1080x1920
   ```
   `--duration 7.7` 로 전체 길이를 강제할 수 있다(기본은 마지막 장면 end).
3. 렌더가 끝나면 `out/cards_s01.png, _s02.png …` (장면마다 1장)를 **직접 열어 보고** 글자 넘침·겹침을 확인한다.
4. 결과를 알려주고 `open out/` 으로 폴더를 열어준다.

속도: 실시간의 약 4배 (6초 영상 → 약 24초, 60초 영상 → 약 4분). 긴 영상이면 미리 말해준다.

## scenes.json 형식

```json
{
  "label": "",
  "scenes": [
    { "start": 0, "end": 2.4, "step": "STEP 01", "title": "말로 찍은 영상\n그대로 넣기",
      "pills": ["무음컷", "자막", "효과음"], "footer": "[클로드코드]가 편집합니다 →" }
  ]
}
```

| 키 | 뜻 | 쓰는 요령 |
|---|---|---|
| `start`, `end` | 초. 이 구간에 카드가 보인다 | 다음 장면 start = 이전 장면 end 로 빈틈없이 |
| `step` | 카드 위 작은 회색 글씨 | `STEP 01`, `TIP`, `01/05` 등. 비워도 됨 |
| `title` | 큰 도트 제목, **두 줄까지** (`\n` 으로 줄바꿈) | 한 줄 8~10자. 길면 자동으로 글자가 작아지지만 짧게 쓰는 게 낫다 |
| `pills` | 알약 0~4개. 앞은 검정, 마지막 하나는 테두리 | 2~3개, 한 개당 2~6자 키워드. `"o:글자"` 로 강제 테두리 |
| `footer` | 카드 아래 한 줄 | `[대괄호]` = 검정 알약, `→` = 원형 화살표 배지. 비워도 됨 |
| `label` | 맨 위 줄 오른쪽 테두리 알약 (전체 공통) | 채널명·시리즈명. 비우면 안 나옴 |

배열만(`[{...}, {...}]`) 줘도 된다. 맨 위에는 장면 번호 원형 배지와 진행 점이 자동으로 나온다.

**문장 → 카드 변환 요령**: 나레이션 문장을 그대로 옮기지 말고 핵심만 두 줄로 줄인다.
"오퍼스한테 제 고양이 그림이랑 스타일 이름만 줬어요" → 제목 `고양이 그림\n하나만 줬다`, 알약 `오퍼스 / 그림 / 스타일 이름`.
문장으로 쓰면 톤이 죽는다 — 정보는 알약·배지로 **조각내서** 얹는다.

## 디자인 값 (바꾸지 말 것)

| 요소 | 값 |
|---|---|
| 배경 | `#FFFFFF` |
| 가는 격자 | 15px 간격 · `rgba(0,0,0,.055)` · 1px |
| 굵은 격자 | 75px 간격 · `rgba(0,0,0,.10)` · 1.5px (화면보다 16% 크게 깔아 줌에도 가장자리 안 보임) |
| 오로라 | 세이지 `#B9CCAE` · 블루 `#78A6FB` · 핑크 `#E9C4D6` 원 3개, `blur(90px)` `opacity .55`, sin/cos 로 천천히 흐름 |
| 잉크 | `#0A0A08` (순검정 아님) |
| 폰트 | Neo둥근모 (도트, 한글 지원) |
| UI 4개 | `.pill` 검정 알약 · `.pill-o` 테두리 알약 · `.circle` 원형 배지 · `.card` 흰 카드(radius 26px, 은은한 그림자) |

모션
- **카드**: `rotateY(-30°) → 0`, `rotateX(10°) → 0`, `scale .9 → 1`, 그림자 56px → 18px 로 좁아짐
- **알약**: 스프링으로 튕기며 커짐(`.5 → 1`), 0.13초 시차
- **장면 전환**: 이전 카드가 0.16초 동안 옆으로 돌며 빠지고, 0.12초 뒤 새 카드가 들어온다 (글자 겹침 없음, 검은 화면 없음)
- **카메라**: 시작할 때 한 번 1.06 → 1.0
- 장면이 1.8초보다 짧으면 진입 모션을 자동으로 압축한다

디자인을 고칠 땐 `assets/template.html` 만 고친다. 브라우저로 그 파일을 직접 열면 예시 장면이 보이고,
개발자 도구 콘솔에서 `setTime(1.2)` 처럼 시간을 넣어 볼 수 있다.

## 규칙

- 이모지 쓰지 않는다. 배지·알약으로 대신한다
- 핑크는 오로라 블러 뒤 보조색까지만. 글씨·알약은 잉크색
- 자막은 이 영상에 넣지 않는다 (편집 단계에서 얹는다)

## 처음 한 번 설치

프로젝트 폴더에서:
```bash
npm i playwright && npx playwright install chromium
```
`npx playwright install chromium` 이 실패해도 Google Chrome 이 깔려 있으면 자동으로 그걸 쓴다
(`CARDS_BROWSER=chrome` 을 앞에 붙이면 크롬을 먼저 시도). ffmpeg 는 PATH 의 것이나 프로젝트 `bin/ffmpeg` 를 쓴다.

## 막혔을 때

| 메시지 | 할 일 |
|---|---|
| playwright 가 없어요 | 프로젝트 폴더에서 `npm i playwright && npx playwright install chromium` |
| 브라우저를 못 켰어요 | `npx playwright install chromium` 또는 Google Chrome 설치 |
| ffmpeg 를 못 찾았어요 | `brew install ffmpeg` (또는 reels-edit-lite 안내대로 bin/ffmpeg) |
| N번째 장면의 start/end 가 이상해요 | 그 장면 end 가 start 보다 커야 함 |

## 폰트 라이선스

`assets/fonts/NeoDunggeunmo.ttf` — **Neo둥근모 (NeoDunggeunmo) v1.530**
- 만든 사람: Eunbin Jeong (Dalgona.) — 원본 둥근모꼴은 1990년대 김중태 님이 퍼블릭 도메인으로 공개
- 출처: https://github.com/neodgm/neodgm
- 라이선스: SIL Open Font License 1.1 — 전문은 `assets/fonts/OFL.txt`
- 영상·이미지에 써서 판매하는 것은 자유. 폰트 파일만 따로 판매하는 것은 금지. 같이 배포할 땐 OFL.txt 를 함께 둔다
