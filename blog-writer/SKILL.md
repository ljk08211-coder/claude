---
name: "blog-writer"
description: "네이버 블로그·티스토리 원고를 쓰는 공통 절차. 상위 글 벤치마크 기준(짧은 줄·빈 줄·사진 간격·해요체·공감형 첫 문장)과 사용자의 현직 바텐더 경험(지식 노트)으로 섹션별 원고를 쓰고, 플랫폼에 맞게 문단을 자동으로 나누고, AI 말투·반복 어미·긴 문장·경험 부족을 검사한다. naver-blog-reserve나 tistory-reserve로 글을 쓰거나 예약할 때, 그 스킬의 조사·원고 단계 대신 반드시 이 스킬을 쓴다. 지식 노트 추가, 벤치마크 갱신 요청에도 사용한다."
---

# 블로그 원고 쓰기 (네이버·티스토리 공통)

예약은 각 플랫폼 스킬(naver-blog-reserve, tistory-reserve)이 한다. 이 스킬은 그 앞의 **조사 → 원고** 단계를 바꾼다. 원고가 끝나면 `blocks`를 만들어 플랫폼 스킬의 에디터 입력 단계로 넘긴다.

**진행 규칙:** 모든 응답은 repl 호출로 끝난다. 계획이나 "작성해 보겠습니다" 같은 예고를 글로 쓰지 않는다. 다음에 무엇을 할지 모르겠으면 `console.log(JSON.stringify(W.next(raw, BR)))`를 실행하고, 그 결과의 code를 채워 바로 실행한다.

경로: 이 스킬 폴더는 `<계정 폴더>/skills/user/blog-writer`다. 계정 폴더는 세 단계 위다. 지식 노트와 벤치마크는 `<계정 폴더>/blog-knowledge/`에 둔다. 읽고 쓰기는 repl의 `fs`로 한다.

## 1. 준비

플랫폼 스킬의 0단계(도우미 불러오기·로그인 확인)를 먼저 한다. 그다음:

```js
eval(await fs.readFile('<this-skill-dir>/scripts/writer.js', 'utf8'));
globalThis.KD = '<계정 폴더>/blog-knowledge';
await fs.mkdir(KD, { recursive: true });
try { console.log('지식 노트:', W.loadKnowledge(await fs.readFile(KD + '/knowledge.md', 'utf8'))); }
catch (e) { await fs.writeFile(KD + '/knowledge.md', await fs.readFile('<this-skill-dir>/knowledge.example.md', 'utf8')); console.log('지식 노트 새로 만듦(비어 있음)'); }
try { W.applyBench(JSON.parse(await fs.readFile(KD + '/benchmark.json', 'utf8'))); } catch (e) {}
```

지식 노트가 비어 있으면 경험 문장을 지어내지 않는다. 경험 섹션은 "바에서 자주 받는 질문" 형식의 일반론으로 쓰고, 보고 끝에 "이 주제 경험을 지식 노트에 적어 주시면 다음 글부터 반영돼요"라고 남긴다.

## 2. 조사와 브리프

플랫폼 스킬의 조사 함수로 상위 글을 읽은 뒤 브리프를 만든다. 별도 repl 호출 두 번이다.

```js
globalThis.R = await NV.research('<키워드>');   // 티스토리면 TS.research
```

```js
globalThis.BR = W.brief(R.query, 'naver', R.blueprint);   // 'naver' 또는 'tistory'
console.log(JSON.stringify({ type: BR.type, target: BR.targetChars, photos: BR.photos, sections: BR.sections.map(s => s.h), titleIdeas: BR.titleIdeas, knowledge: BR.knowledge, refTitles: R.picked.map(p => p.title) }, null, 1));
```

## 3. 제목

titleIdeas 중 하나를 골라 `{...}` 자리를 이 글의 실제 내용으로 채운다. 규칙: 메인 키워드를 맨 앞에, 25~38자, 숫자 1개, 빈말·과장 금지. 참고 글 제목(refTitles)과 겹치지 않게 쓴다.

```js
globalThis.title = '<제목>';
globalThis.raw = [];
console.log(JSON.stringify(W.next(raw, BR)));
```

## 4. 섹션별 작성

W.next가 알려 주는 섹션 하나를 `raw.push(...)` 한 번으로 쓰고, 이어서 W.next를 다시 본다. 도입 → 섹션 1…N → 마무리 → 완료 순서다.

쓰는 법:
- **문단은 산문으로 쓴다.** 3~6문장을 한 문자열에 넣는다. 줄바꿈·빈 줄은 W.format이 플랫폼에 맞게 만든다. 직접 줄을 쪼개지 않는다.
- **말투는 해요체 하나로.** 친근하지만 가볍지 않게. 현직 바텐더가 손님에게 설명하듯 쓴다.
- **문장은 짧게.** 한 문장 60자 이내. 같은 어미를 세 번 넘게 잇지 않는다. 가끔 질문으로 끊는다.
- **구체적으로.** "다양한·매력적인·특별한" 대신 숫자·이름·장면을 쓴다(45ml, 1:3, 7분, 글렌피딕 12년).
- **경험은 지식 노트에서 가져온다.** 1인칭으로 쓴다("저희 바에서는…", "손님들이 제일 많이 묻는 건…"). 노트에 없는 경험·후기·가격은 지어내지 않는다.
- **숫자는 출처가 있는 것만.** 참고 글 본문(R.picked[i].text), 공식 사이트, 지식 노트에서 확인한 것만 쓴다. 지원금·시험 정보는 공고 연도를 밝힌다.
- **사진 줄은 섹션마다.** 네이버는 `[사진: 한국어 구체 키워드, 넓은 키워드]`, 티스토리는 `[사진: english keyword, broader keyword]`.
- **목록과 Q&A.** 목록은 `- `로 시작하는 문자열을 줄마다 따로, 질문은 `Q. …`, 답은 `A. …` 문자열로 넣는다.
- 티스토리 제휴 제품은 이때 `[제품: name]` 줄로 넣는다(tistory-reserve의 제품 카드 규칙).

## 5. 마무리와 검사

W.next가 '완료'를 알리면:

```js
globalThis.F = W.finish(raw, BR);
console.log(JSON.stringify(F.lint, null, 1));
console.log(F.preview);
```

- `lint.problems`가 있으면 고친다. 고칠 때는 문제 있는 문단 하나만 바꾼다(`raw[i] = '<고친 문단>'`). 분량이 모자라면 해당 섹션 뒤에 새 문단을 끼워 넣는다(`raw.splice(i + 1, 0, '<새 문단>')`). 원고 전체를 다시 쓰지 않는다. 고친 뒤 W.finish를 다시 실행한다.
- 세 번 고쳐도 남는 문제가 경험 부족이나 숫자 부족뿐이면 그대로 진행하고 보고에 적는다. 그 밖의 문제(AI 표현, 말투 섞임, 긴 문장)는 반드시 고친다.
- `warnings`는 고치면 좋지만 막지 않는다.

그다음 플랫폼 검사를 통과시킨다.

```js
globalThis.blocks = F.blocks;
console.log(NV.checkDraft(blocks, R.blueprint));          // 네이버
// console.log(TS.checkDraft(blocks, R.blueprint, S));    // 티스토리
```

플랫폼 검사의 문제(키워드 횟수, 참고 글과 같은 문장 등)도 raw를 고친 뒤 W.finish → 검사 순서로 다시 돌린다. 둘 다 통과하면 플랫폼 스킬의 **에디터 입력 단계**(네이버 3단계 / 티스토리 3단계)로 간다. 이때 제목은 `title`, 본문은 `blocks`다.

## 6. 보고에 더할 것

플랫폼 스킬의 보고에 다음을 더한다.
- 글 유형, 분량, 경험 문장 수, 고친 lint 문제
- 지식 노트에서 쓴 항목
- 지식 노트에 없어서 일반론으로 쓴 부분(사용자가 채우면 좋은 것)
- 네이버라면 한 줄: "예약 글을 열어 본문 전체를 가운데 정렬하면 반응 좋은 글과 같은 모양이 돼요(선택)."

## 7. 지식 노트 추가

사용자가 "지식 노트에 추가해 줘: …"라고 하면 knowledge.md 끝에 `## <주제 키워드가 들어간 제목>`과 내용을 붙여 저장하고 `W.loadKnowledge`를 다시 실행한다. 사용자가 말한 내용만 적는다. 다듬거나 부풀리지 않는다.

## 8. 벤치마크 갱신 (한 달에 한 번, 또는 요청 시)

```js
globalThis.BM = await W.bench(['하이볼 만들기', '위스키 입문', '칵테일 레시피', '조주기능사 실기', '술집 창업', '소상공인 지원금']);
await fs.writeFile(KD + '/benchmark.json', JSON.stringify(BM, null, 1));
console.log(JSON.stringify(BM, null, 1));
```

키워드 6개에 3~5분 걸린다. 결과의 chars(분량), lineMed(한 줄 길이), images(사진 수), topIntros(반응 좋은 글의 첫 문장)를 사용자에게 짧게 요약한다. 지난번과 달라진 점이 있으면 함께 알린다. W.applyBench가 다음 글부터 기준을 바꾼다.

## 9. 처음 설치 후 한 번: 루틴이 이 스킬을 쓰게 하기

이미 만든 정기 루틴의 prompt를 바꿔야 루틴도 이 절차로 글을 쓴다. routine_update로 각 루틴의 prompt만 아래로 바꾼다(mode `update`, 그 id, prompt). 루틴 모델과 상태는 건드리지 않는다.

- 네이버 블로그 정기 예약:

```text
naver-blog-reserve 스킬의 '7. 루틴 실행' 절차대로 캘린더에서 앞으로 8일 안의 대기 글을 써서 예약해 줘. 단, 각 글의 조사·원고(1~2단계)는 blog-writer 스킬 절차(2~5단계)로 쓰고, 통과한 blocks로 에디터 입력부터 이어 가. 캘린더 승인으로 예약 확인을 대신하니 확인 없이 예약해. 끝나면 예약한 글 제목·시각, 실패한 글과 이유, 남은 대기 글 수, 지식 노트에 없어 일반론으로 쓴 부분을 짧게 남겨.
```

- 티스토리 정기 예약:

```text
tistory-reserve 스킬의 '7. 루틴 실행' 절차대로 캘린더에서 오늘 처리할 대기 글 1편을 써서 오늘 날짜로 예약해 줘. 단, 조사·원고는 blog-writer 스킬 절차(2~5단계)로 쓰고, 통과한 blocks로 에디터 입력부터 이어 가. 캘린더 승인으로 예약 확인을 대신하니 확인 없이 예약해. 끝나면 예약한 글 제목·시각, 실패했으면 이유, 남은 대기 글 수를 짧게 남겨.
```
