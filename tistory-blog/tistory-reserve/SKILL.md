---
name: "tistory-reserve"
description: "티스토리 블로그 글을 상위 글 포맷·키워드 분석부터 작성, 티스토리 에디터 입력(제목·본문 HTML·무료 사진·제휴 제품 카드·태그·카테고리), 오늘 날짜 예약 발행, 예약 확인까지 처리한다. 블로그 주제의 니치 키워드 조사, 2주 발행 캘린더, 매일 그날 글을 써서 예약하는 정기 루틴도 만든다. 사용자가 티스토리 글쓰기, 티스토리 예약 발행, 티스토리 자동 발행, 티스토리 정기 발행, 티스토리 니치 조사를 요청하거나 루틴이 티스토리 정기 예약을 실행할 때 사용한다."
---

# 티스토리 글쓰기와 예약 발행

글은 지금 쓰고, 발행은 티스토리가 예약 시각에 한다. 예약을 걸고 나면 컴퓨터가 꺼져 있어도 글이 올라간다.

이 스킬의 원칙 세 가지:
- **예약은 오늘 날짜로만 건다.** 다른 날짜는 달력을 눌러야 해서 실패할 수 있다. 그래서 루틴은 매일 돌면서 그날 글만 예약한다.
- **한 번 실행에 최대 1편이다.** 티스토리는 짧은 시간에 여러 번 발행하면 보안 퍼즐(틀린그림찾기)을 띄운다. 퍼즐은 풀지 않는다. 우회도 계정 정지 사유라 하지 않는다.
- **즉시 발행으로 넘어가지 않는다.** 예약 설정이 하나라도 확인되지 않으면 버튼을 누르지 않고 멈춘다.

**진행 규칙 (가장 중요):** 1~5단계에서는 모든 응답이 repl 호출로 끝난다. 제목·분량·소제목 수 같은 계획을 글로 적지 않는다. "원고를 작성해 보겠습니다" 같은 예고도 쓰지 않는다. 같은 말을 다시 쓰려 하고 있으면 그 자리에서 멈추고 `console.log(JSON.stringify(TS.nextStep(blocks, R.blueprint, S)))`를 실행한 뒤, 결과의 code를 채워 바로 실행한다. 사용자에게 말하는 것은 사용자가 할 일이 있을 때(로그인·확인·오류)와 5단계 보고 때뿐이다.

## 0. 준비 (매 작업 처음)

도우미와 설정 파일(6-1)을 불러오고 블로그를 정한다. 설정 파일이 아직 없으면 S는 빈 값이고, 블로그 주소는 사용자에게 물어본다.

```js
eval(await fs.readFile('<this-skill-dir>/scripts/tistory-editor.js', 'utf8'));
globalThis.AP = '<계정 폴더>/tistory-autopilot';   // 6-1 참고
try { globalThis.S = JSON.parse(await fs.readFile(AP + '/settings.json', 'utf8')); } catch (e) { globalThis.S = {}; }
TS.use(S.blog || '<사용자가 알려 준 블로그 주소>');
console.log(await TS.checkLogin());
```

loggedIn이 false면 멈추고 message를 그대로 사용자에게 전한다. 로그인했다고 하면 checkLogin을 다시 실행해 true를 확인한다. 비밀번호를 대신 입력하거나 카카오 보안 확인을 우회하지 않는다.

repl 변수는 호출 사이에 남는다. 같은 이름으로 const를 다시 선언하지 말고 `globalThis.x = ...`를 쓴다. TS가 없다는 오류가 나면 위 eval 줄과 TS.use만 다시 실행한다.

## 1. 상위 글 분석 (건너뛰지 않는다)

티스토리 유입은 주로 구글·다음 검색이다. 다음 블로그 검색 상위의 티스토리 글을 읽어 포맷과 키워드를 뽑는다. 1분 정도 걸린다. 별도 repl 호출로 실행한다.

```js
globalThis.R = await TS.research('<키워드>');
console.log(JSON.stringify({ checked: R.checked, picked: R.picked.map(p => ({ url: p.url, title: p.title, date: p.date, chars: p.chars, heads: p.heads, images: p.images, tags: p.tags })), blueprint: R.blueprint }, null, 1));
```

위 출력이 설계도다(사용자에게도 그대로 보인다). 따로 요약해 적지 않고 바로 2단계 코드를 실행한다.

1. 따라 하는 것은 포맷과 키워드다. 문장은 새로 쓴다. checkDraft가 참고 글과 20자 이상 같은 문장을 막는다.
2. 숫자(가격·도수·용량·지원 금액·신청 기간·시험 일정·합격률)는 R.picked[i].text나 공식 출처에서 확인한 것만 쓴다. 확인하지 못한 숫자·후기·개인 경험은 지어내지 않는다.
3. **지원금·정책·자격증 글은 공식 출처를 따로 연다.** `const P = await TS.readPost('<공식 공고 url>')`로 본문을 읽어 숫자를 확인한다. 공식 출처는 기업마당(bizinfo.go.kr), 소상공인24(sbiz24.kr), 소상공인시장진흥공단(semas.or.kr), K-Startup(k-startup.go.kr), 큐넷(q-net.or.kr, 조주기능사) 같은 곳이다. 확인하지 못하면 "올해 공고에서 정확한 금액·기간을 확인하세요"라고 쓰고 숫자를 비운다. 공고 연도를 본문에 밝힌다.

## 2. 원고 (설계도대로)

- 제목: 설계도의 제목 패턴과 길이를 따른다. 메인 키워드를 앞쪽에 넣는다. 40자 안쪽.
- 본문: 공백 제외 targetChars자 이상(최소 1,800자). 첫 문단(2–3문장)에 메인 키워드와 이 글이 해결해 주는 것을 넣는다. 마지막에 한 줄 요약.
- 소제목은 `## `로 heads개 이상, 필요하면 `### `. 정보 글이면 마지막 소제목을 `## 자주 묻는 질문`으로 하고 질문 2–3개에 짧게 답한다(구글 검색에 유리하다).
- 목록은 `- `, 강조 박스는 `> `, 굵게는 `**굵게**`.
- 사진: 도입 문단 바로 아래에 1장(첫 사진이 대표 이미지가 된다), 나머지는 소제목 아래에 `[사진: 영어 키워드, 더 넓은 영어 키워드]` 한 줄. 예: `[사진: whisky tasting glass, whisky]`. 무료 사진은 영어로 검색해야 잘 나온다. 사진 자리는 blueprint.photos개.
- 제품: 아래 "제품 카드" 규칙을 따른다.
- 외부 주소·광고 문구·과장된 효능(숙취 해소, 건강 효과 등)은 본문에 쓰지 않는다. 술을 권하는 표현보다 정보·방법 중심으로 쓴다.
- 원고 전체를 한 번에 쓰지 않는다. repl 한 번에 소제목 하나만 이어 붙인다. 앞 문단을 다시 쓰지 않는다.

첫 호출에서 제목을 정하고 시작한다:

```js
globalThis.title = '<제목>';
globalThis.blocks = [];
console.log(JSON.stringify(TS.nextStep(blocks, R.blueprint, S)));
```

그다음부터는 매번 nextStep 결과의 `next`(무엇을 쓸지)와 `code`(실행할 모양)를 따라 `<...>` 자리를 실제 문장으로 채워 **바로 실행한다**. 한 번 실행할 때마다 nextStep이 다음 할 일을 다시 알려 준다. `done: true`가 나오면 곧바로 3단계를 실행한다. problems는 막는 문제, warnings는 고치면 좋은 것이다.

**제품 카드** (settings.json의 products에 사용자가 넣어 둔 제휴 링크만 쓴다. 링크를 지어내지 않는다)
1. `console.log(TS.matchProducts(R.query + ' ' + blocks.join(' '), S))`로 이 글에 맞는 제품을 고른다(최대 2개).
2. 맞는 제품이 있으면 그 제품이 자연스럽게 쓰이는 문단 아래에 `[제품: name]` 한 줄을 넣는다. 없으면 넣지 않는다. 억지로 끼우지 않는다.
3. 제품이 들어가면 대가성 문구(settings.disclosure)가 글 첫머리에 자동으로 붙는다. 지우지 않는다.
4. 술 자체는 온라인 판매 링크를 넣지 않는다(전통주 외 주류 통신판매 금지). 바 도구·잔·책·안주·논알코올 재료 같은 것만 넣는다.

태그 10개를 정해 둔다: blueprint.tags를 먼저, 모자라면 keywords에서. 띄어쓰기 없이. `globalThis.tags = ['태그1', ...]`

## 3. 에디터 입력

```js
globalThis.H = await TS.toHtml(blocks, S);   // 사진 검색이 여기서 일어난다
console.log(JSON.stringify({ photos: H.photos.map(p => p.credit), products: H.products, missed: H.missed }));
globalThis.ed = await TS.openEditor();
await TS.fillTitle(ed, title);
console.log(await TS.setBody(ed, H.html));
console.log(await TS.readContent(ed));
```

- H.missed는 넣지 못한 사진·제품 줄이다. 사진이 하나도 안 들어갔으면 사진 줄의 키워드를 더 넓은 영어 단어로 바꿔 toHtml을 다시 한다. 그래도 없으면 사진 없이 진행하고 보고에 적는다.
- `LOGIN_REQUIRED`면 멈추고 로그인을 부탁한다.
- readContent의 title이 원고 제목과 같고 chars가 원고 글자 수의 80% 이상인지 본다. 아니면 탭을 닫고(`await closeTab(ed.page)`) 새 에디터로 다시 한다.
- `BODY_FAILED`, `EDITOR_NOT_FOUND`처럼 화면 구조 오류가 나면 `console.log(JSON.stringify(await TS.probe()))`(발행 창이면 `TS.probe('layer')`) 결과를 사용자에게 보여 주고 멈춘다. 셀렉터를 추측해서 고치지 않는다.

## 4. 예약 설정과 확인

```js
await TS.openPublish(ed);
console.log(await TS.setCategory(ed, '<카테고리>'));   // 6-4에서 정한 카테고리. 비우면 '카테고리 없음'
console.log(await TS.setTags(ed, tags));
await TS.setVisibility(ed, 'private');               // 받은 공개 범위: public | protected | private
console.log(await TS.setSchedule(ed, '2026-10-20 19:00'));   // 반드시 오늘 날짜
console.log(await TS.readLayer(ed));
```

- setSchedule은 오늘 날짜로만 부른다. 시각은 지금부터 40분 이후, 10분 단위로 잡는다. `TS.slotFor(캘린더시각)`이 그 값을 만들어 준다.
- `DATE_UI`, `TIME_UI`, `RESERVE_UI`가 나면 예약하지 말고 `TS.probe('reserve')` 결과를 보여 주고 멈춘다.
- readLayer에서 reserve가 true, visibility, dateParsed, hour, minute가 맞는지 본다.

사용자가 "확인 없이 예약해"라고 하지 않았다면 최종 버튼 전에 제목·예약 시각·공개 범위·카테고리를 보여 주고 확인받는다.

```js
globalThis.done = await TS.confirm(ed, { when: '2026-10-20 19:00', visibility: 'private', title });
console.log(done);
```

- confirm은 화면의 제목·글자 수·예약 상태·날짜·시각·공개 범위를 다시 읽고 하나라도 다르면 NOT_CONFIRMED를 던지며 버튼을 누르지 않는다.
- `captcha: true`면 보안 퍼즐이 뜬 것이다. 풀지 않는다. 사람이 대화 중이면 "Aside 화면에서 퍼즐을 풀고 예약 버튼을 다시 눌러 주세요"라고 하고 기다린다. 루틴이면 실패로 기록하고 끝낸다(오늘은 더 발행하지 않는다).

## 5. 성공 판정과 보고

```js
const L = await TS.listReserved(); console.log(L.items, TS.isReserved(L, title));
```

- done.ok가 true이고 isReserved가 true면 성공이다. listReserved는 화면 구조가 검증되지 않았다. done.ok는 true인데 목록에서 못 찾으면, 성공으로 기록하되 "관리 화면(블로그주소/manage/posts)에서 예약 글을 한 번 확인해 주세요"라고 보고한다. 같은 글을 다시 예약하지 않는다.
- 보고: 제목, 예약 시각, 공개 범위, 카테고리, 태그, 사진 수(출처), 넣은 제품, 넣지 못한 사진·제품, 참고한 글 3개 주소.

## 6. 정기 발행 설정 (처음 한 번)

사용자가 정기 발행·자동 발행·니치 조사를 요청하면 따른다. 글 한 편만 요청했으면 건너뛴다.

**6-1. 설정 파일.** 위치는 Aside 계정 폴더 안의 `tistory-autopilot/`이다. 계정 폴더는 이 스킬 폴더(`<계정 폴더>/skills/user/tistory-reserve`)에서 세 단계 위다. 루틴이 승인 질문 없이 읽고 쓸 수 있는 곳이라 다른 곳에 두지 않는다. 읽고 쓰기는 repl의 `fs`로 한다(Aside 터미널은 계정 폴더에 접근할 수 없다).

```js
await fs.mkdir(AP, { recursive: true });
if (!S.blog) globalThis.S = JSON.parse(await fs.readFile('<this-skill-dir>/settings.example.json', 'utf8'));
console.log(JSON.stringify(S, null, 1));
```

settings.json이 없으면 예시에서 시작해 사용자와 함께 채운다: blog, visibility(처음엔 private 권장), pillars(블로그 주제 묶음), products(제휴 링크), footer(유튜브·가게 링크, 주소가 빈 줄은 안 나간다). 제품은 "예시)"로 시작하는 항목을 지우고 사용자가 준 이름·링크·키워드로 바꾼다. 링크는 사용자가 쿠팡 파트너스에서 직접 만든 것만 쓴다. 저장: `await fs.writeFile(AP + '/settings.json', JSON.stringify(S, null, 2))`.

**6-2. 받을 값**: 한 주 편수(기본 3), 발행 요일·시각(기본 월·수·금 19:00), 공개 범위, 루틴 실행 시각(기본 매일 10:40). 말하지 않은 값은 기본값으로 표에 적어 보여 준다.

**6-3. 니치 조사.** pillars마다 실행한다(주제당 20초 안팎).

```js
globalThis.NZ = [];
for (const p of S.pillars) { const r = await TS.niche(p); NZ.push(r); console.log(p, JSON.stringify(r.candidates.slice(0, 8).map(c => [c.keyword, c.gRank, c.nRank]))); }
```

사용자에게 표로 보여 준다: 주제 · 키워드 · 구글 자동완성 순위 · 네이버 자동완성 순위. 순위는 자동완성에 뜬 순서이고 검색량 숫자가 아니라고 한 줄 적는다.

**6-4. 카테고리.** 에디터를 열어 블로그 카테고리를 읽고 pillars마다 어느 카테고리에 넣을지 사용자에게 정해 받는다. `S.categories = { '위스키': '위스키 이야기', ... }`로 저장한다. 맞는 카테고리가 없으면 사용자가 티스토리 관리 화면에서 만들게 안내한다.

```js
globalThis.ed = await TS.openEditor(); await TS.openPublish(ed).catch(() => {});
console.log(await TS.listCategories(ed)); await closeTab(ed.page);
```

**6-5. 2주 캘린더.** 한 주 편수 × 2개를 고른다.
- 구글·네이버 둘 다 뜨는(both) 세부 키워드를 먼저 고른다. 주제 그대로의 넓은 말보다 방법·비용·종류·차이·준비·조건 같은 세부 키워드를 고른다.
- pillars를 돌아가며 섞는다. 같은 주에 같은 주제가 두 번 나오지 않게 한다. 의도(정보·비교·방법·후기)도 섞는다.
- 같은 질문을 다르게 쓴 키워드는 하나만 고른다.
- 날짜·시각은 받은 요일·시각을 따른다. 하루 1편이다.

표(날짜 · 시각 · 주제 · 키워드 · 카테고리)를 보여 주고 승인받는다. 승인 전에는 저장·루틴 등록·예약을 하지 않는다.

**6-6. 저장.** `AP + '/calendar.json'`:

```json
{
  "theme": "술집 창업·위스키·칵테일",
  "visibility": "private",
  "perWeek": 3,
  "slots": ["MO 19:00", "WE 19:00", "FR 19:00"],
  "items": [
    { "when": "2026-10-20 19:00", "pillar": "위스키", "keyword": "위스키 입문 추천", "category": "위스키 이야기", "status": "대기" }
  ]
}
```

status는 `대기` · `예약됨` · `실패` · `확인필요` 중 하나다. 예약되면 `title`·`reservedAt`, 실패하면 `note`(이유 한 줄)를 더한다. 사용자가 나중에 공개 범위를 바꾸라고 하면 calendar.json의 visibility만 바꾼다. 이미 예약된 글은 관리 화면에서 직접 바꿀 수 있다고 안내한다.

**6-7. 루틴 등록 (일시정지 상태로).** routine_update 도구에 mode `create`, name `티스토리 정기 예약`, status `paused`, rrule은 두 줄로 `DTSTART;TZID=Asia/Seoul:<내일 YYYYMMDD>T104000`과 `RRULE:FREQ=DAILY;BYHOUR=10;BYMINUTE=40`(받은 실행 시각으로)을 넣고, prompt는 아래 문장을 그대로 쓴다. 도구가 kind·scheduleKind·timezone 칸을 따로 받으면 `cron`·`recurring`·`Asia/Seoul`을 넣는다. 같은 이름의 루틴이 있으면 새로 만들지 말고 그 루틴으로 6-8을 한다.

```text
tistory-reserve 스킬의 '7. 루틴 실행' 절차대로 캘린더에서 오늘 처리할 대기 글 1편을 써서 오늘 날짜로 예약해 줘. 캘린더 승인으로 예약 확인을 대신하니 확인 없이 예약해. 끝나면 예약한 글 제목·시각, 실패했으면 이유, 남은 대기 글 수를 짧게 남겨.
```

**6-8. 루틴 모델을 무료로.** 루틴은 이 채팅의 모델을 저장해 그 모델로 돈다. FreeLLMAPI Auto로 바꾼 것을 확인한 뒤에만 켠다.

```js
const r = aside.routines.list({ limit: 50 }).find(x => x.name === '티스토리 정기 예약');
if (r) { const { prompt, ...info } = r; console.log(JSON.stringify({ id: info.id, status: info.status, model: info.sessionConfig?.model ?? info.model, nextRunAt: info.nextRunAt })); } else console.log('루틴 없음');
```

1. model이 `freellmapi` / `auto`면 3으로 간다.
2. 아니면 이 문장을 그대로 전하고 멈춘다: "채팅에 생긴 '티스토리 정기 예약' 카드의 Edit를 누르고, Model을 눌러 검색창에 FreeLLMAPI를 입력한 뒤 'FreeLLMAPI Auto (무료)'를 고르고 Update를 눌러 주세요. 끝나면 '완료'라고 보내 주세요." 완료라고 하면 다시 확인한다. 두 번 안내해도 다르면 켜지 말고 멈춘다. 목록에 FreeLLMAPI가 없다고 하면 네이버 키트(naver-blog-free)의 무료 AI 연결을 먼저 하라고 안내한다.
3. routine_update로 mode `update`, 그 id, status `active`를 보내 켠다. 다시 확인해 active이고 model이 무료인지 보고 다음 실행 시각과 함께 알린다.
4. 이 채팅을 지우거나 보관하지 말라고 한 줄 알린다. 루틴이 이 채팅에 붙어 있다.
5. 루틴은 실행 시각에 컴퓨터·Aside·FreeLLMAPI가 켜져 있어야 돈다. 이미 걸린 예약 글은 컴퓨터가 꺼져 있어도 올라간다. 무료 플랜은 켜진 루틴이 3개까지다(네이버 루틴과 합쳐 2개). 세 가지를 한 줄씩 알린다.

**6-9.** 오늘 날짜 글이 캘린더에 있으면 지금 바로 예약할지 묻는다. 원하면 7과 같은 방법으로 이 대화에서 진행한다.

## 7. 루틴 실행 (정기 예약)

루틴이 부르거나 사용자가 "티스토리 캘린더대로 예약해"라고 할 때 쓴다. **한 번 실행에 1편만** 처리한다.

1. 0단계(도우미·TS.use·로그인 확인)를 한다. `AP + '/settings.json'`을 S로, `AP + '/calendar.json'`을 읽는다. 없으면 '정기 발행 설정을 먼저 해 주세요'라고 남기고 끝낸다. 로그인이 풀려 있으면 아무것도 하지 말고 checkLogin의 message를 남기고 끝낸다.
2. 처리할 글을 하나 고른다: `대기` 중 when 날짜가 오늘인 글. 없으면 when이 오늘 이전인 `대기`(밀린 글) 중 가장 오래된 글. 둘 다 없으면 8번으로 간다.
3. `const when = TS.slotFor(item.when)`로 오늘 예약 시각을 정한다. null이면(오늘 안에 못 잡음) 아무것도 하지 않고 "내일 다시"라고 남기고 끝낸다.
4. 1~5단계(조사 → 원고 → 에디터 → 예약)를 따른다. 공개 범위는 calendar의 visibility, 카테고리는 item.category, 4단계의 사용자 확인은 생략하고 바로 TS.confirm을 부른다(confirm의 검사는 그대로).
5. 결과 기록 후 바로 calendar.json을 저장한다:
   - 성공: status `예약됨`, title, reservedAt(=when). 목록에서 못 찾았으면 status `확인필요`.
   - 보안 퍼즐: status는 `대기`로 두고 note `보안 퍼즐로 중단(날짜)`. 오늘은 더 하지 않는다.
   - 그 밖의 실패: status `실패`, note에 이유 한 줄. 같은 실행에서 다시 시도하지 않는다.
6. 에디터 탭이 남아 있으면 닫는다(`await closeTab(ed.page)`). 다음 글을 위해 `globalThis.blocks = []`.
7. 남은 `대기` 글이 한 주 편수보다 적으면 캘린더를 2주 늘린다: S.pillars 순서대로 TS.niche를 돌려 이미 있는 키워드와 겹치지 않는 세부 키워드를 6-5 기준으로 고르고, slots의 요일·시각으로 날짜를 이어 붙여 `대기`로 저장한다.
8. 마지막에 처리한 글(제목·시각) 또는 실패 이유, 남은 대기 글 수, 새로 붙인 키워드를 짧게 남긴다.

## 하지 않는 것

- 사용자가 요청하지 않은 즉시 발행, 예약 취소·삭제, 기존 글 수정.
- 보안 퍼즐(틀린그림찾기)·카카오 로그인 보안 확인을 풀거나 우회하는 것.
- 하루 2편 이상 예약, 같은 내용을 여러 블로그에 반복 게시.
- 사용자가 settings.json에 넣지 않은 링크, 지어낸 숫자·후기.
