// 블로그 원고 엔진 (Aside REPL용, 네이버·티스토리 공통)
// 불러오기: eval(await fs.readFile('<blog-writer 스킬 폴더>/scripts/writer.js', 'utf8'))
// 모든 함수는 globalThis.W 아래에 있다.
//
// 흐름: W.brief(키워드) → W.next(raw)로 섹션 하나씩 raw에 쓰기 → W.finish(raw) → 플랫폼 검사(NV/TS.checkDraft)
// 모델은 문단 나누기를 신경 쓰지 않고 섹션마다 3~6문장 산문으로 쓴다. 줄바꿈·빈 줄은 W.format이 플랫폼에 맞게 기계적으로 만든다.
//
// 기준 숫자(BENCH)는 2026-10-19에 우리 주제 키워드 24개(하이볼·위스키·칵테일·전통주·조주기능사·바텐더·술집/바 창업·소상공인 지원금 등)의
// 네이버 블로그 검색 상위 글 127개와 티스토리 상위 글 29개를 분석한 값이다. 자세한 근거는 references/benchmark-2026-10.md.
globalThis.W = (() => {
  const BENCH = {
    naver: {
      chars: [1500, 2200],      // (NV.checkDraft 최소 1,500자에 맞춤) 반응 좋은 글(공감 상위 1/3) 중앙값 1,552자. 하위 1/3은 2,314자로 더 길었다
      lineMax: 22,              // 상위 글 한 줄(문단) 중앙값 19자, 76%가 35자 이하. 문장 중간에서도 줄을 바꾼다
      linesPerBlock: [1, 3],    // 빈 줄 사이 줄 수: 1줄이 가장 많고 2~3줄 묶음이 다음
      photos: [5, 8],           // 상위 글 사진 중앙값 6장, 반응 좋은 글 7.5장. 첫 사진은 첫머리(0~1번째)
      photoEvery: 4,            // 사진 사이 텍스트 줄 수 중앙값 1~2줄(줄 단위가 짧기 때문). 4~6줄마다 사진 1장
      heads: [3, 6],            // 인용구 소제목 중앙값 1개, 상위 1/3은 4개 이상. ■ 줄로 넣는다
      voice: '해요체',          // 반응 좋은 글은 해요체 비중이 높았다(20% 대 4%). 하위 글은 합니다체(42%)가 많았다
    },
    tistory: {
      chars: [1800, 3000],      // 티스토리 상위 글 중앙값 1,931자(p25 1,454, p75 2,689)
      paraMax: 90,              // 문단 중앙값 33자. 한 문단 1~2문장
      photos: [2, 5],           // 중앙값 5장(p25 1장)
      heads: [4, 8],            // 잘 정리된 정보 글은 h2 6~11개. 질문형·번호형 소제목
      voice: '해요체',
    },
  };

  // ---- 글 유형과 목차 틀 ----
  const TYPES = [
    { id: '시험', re: /조주기능사|자격증|필기|실기|시험|기출|합격/ },
    { id: '지원', re: /지원금|정책자금|보조금|바우처|지원사업|대출|융자|소상공인|희망리턴|신청\s*방법/ },
    { id: '창업', re: /창업|오픈|인테리어|상권|권리금|임대|매장|운영|원가|메뉴\s*가격|술집|바\s*차리/ },
    { id: '레시피', re: /만들기|만드는|레시피|비율|홈텐딩|제조|칵테일\s*\S+\s*법/ },
    { id: '추천', re: /추천|순위|베스트|비교|가성비|선물|top|TOP/ },
    { id: '입문', re: /.*/ },
  ];
  const T = {
    레시피: [
      { h: '한눈에 보는 레시피', goal: '재료와 용량(ml)·잔·얼음을 목록(- )으로 먼저 보여 준다. 바쁜 독자는 여기서 끝나도 되게', must: ['ml', '목록'] },
      { h: '재료 고르는 법', goal: '베이스 술·탄산·가니쉬를 무엇으로 고르면 되는지, 집에 없을 때 대체재', must: [] },
      { h: '만드는 순서', goal: '1. 2. 3. 번호 단계로. 단계마다 왜 그렇게 하는지 한 줄', must: ['번호'] },
      { h: '맛이 밍밍해지는 실수 3가지', goal: '현장에서 손님·초보가 자주 하는 실수와 고치는 법(경험)', must: ['경험'] },
      { h: '바텐더가 쓰는 한 끗 팁', goal: '지식 노트의 내 팁·내 바에서 하는 방식. 1인칭으로', must: ['경험'] },
      { h: '자주 묻는 질문', goal: 'Q. 질문 / A. 답 형식으로 2~3개', must: ['Q'] },
    ],
    추천: [
      { h: '고르기 전에 알아둘 기준', goal: '무엇을 보고 고르면 되는지 기준 2~3개(맛 방향·가격대·용도)', must: [] },
      { h: '추천 1', goal: '이름 → 어떤 맛인지 → 어떤 사람에게 맞는지 → 확인된 가격대만. 이 형식을 추천마다 반복', must: [] },
      { h: '추천 2', goal: '추천 1과 같은 형식. 추천 1과 무엇이 다른지 한 줄', must: [] },
      { h: '추천 3', goal: '같은 형식', must: [] },
      { h: '상황별로 고르면', goal: '입문용·선물용·하이볼용처럼 상황별 한 줄 정리(목록)', must: ['목록'] },
      { h: '현직 바텐더 한마디', goal: '손님들이 실제로 많이 고르는 것, 내가 권하는 순서(경험)', must: ['경험'] },
    ],
    입문: [
      { h: '한 줄로 말하면', goal: '이 주제를 한 문장으로 정의하고 왜 알아두면 좋은지', must: [] },
      { h: '종류와 차이', goal: '헷갈리는 종류를 기준 하나로 나눠 설명(목록 활용)', must: ['목록'] },
      { h: '처음이라면 이렇게', goal: '처음 마시는/시작하는 순서, 실패 줄이는 방법', must: [] },
      { h: '입문자가 자주 하는 실수', goal: '바에서 본 실제 사례(경험)', must: ['경험'] },
      { h: '자주 묻는 질문', goal: 'Q. / A. 2~3개', must: ['Q'] },
    ],
    지원: [
      { h: '한눈에 보기', goal: '대상·내용(금액)·기간·신청처를 목록으로. 공식 공고에서 확인한 것만, 공고 연도 표기', must: ['목록', '연도'] },
      { h: '누가 받을 수 있나', goal: '조건을 쉬운 말로. 애매한 경우 예시', must: [] },
      { h: '얼마나, 무엇을 지원하나', goal: '확인된 숫자만. 모르면 "공고에서 확인"으로', must: [] },
      { h: '신청 방법', goal: '1. 2. 3. 단계. 어디서 무엇을 누르는지', must: ['번호'] },
      { h: '준비 서류와 탈락 포인트', goal: '서류 목록 + 자주 떨어지는 이유', must: ['목록'] },
      { h: '자영업자로서 해 본 경험', goal: '바를 운영하며 실제로 써 본/준비해 본 경험이 있으면(지식 노트). 없으면 이 섹션을 "신청 전 체크리스트"로', must: [] },
      { h: '자주 묻는 질문', goal: 'Q. / A. 2~3개', must: ['Q'] },
    ],
    시험: [
      { h: '시험 한눈에 보기', goal: '시행처(큐넷)·필기/실기 구성·합격 기준. 공식 정보로 확인한 것만', must: ['목록'] },
      { h: '필기는 이렇게', goal: '공부 순서와 범위, 외우는 요령', must: [] },
      { h: '실기는 여기서 갈린다', goal: '과제·시간·감점 포인트. 손이 익어야 하는 동작', must: [] },
      { h: '현직 바텐더가 본 합격 팁', goal: '실무자로서 보이는 실수·연습법(경험)', must: ['경험'] },
      { h: '준비물과 비용', goal: '확인된 응시료·도구만', must: [] },
      { h: '자주 묻는 질문', goal: 'Q. / A. 2~3개', must: ['Q'] },
    ],
    창업: [
      { h: '먼저 정해야 할 것', goal: '컨셉·상권·규모 중 무엇을 먼저 정해야 하는지(경험)', must: ['경험'] },
      { h: '돈은 어디에 드나', goal: '비용 항목을 목록으로. 숫자는 내 경험이나 확인된 범위만, 출처 표시', must: ['목록'] },
      { h: '준비 순서', goal: '1. 2. 3. 단계(인허가·인테리어·주류 거래처·메뉴)', must: ['번호'] },
      { h: '직접 해 보니 후회한 것', goal: '바결을 열며 겪은 실수와 다시 한다면(지식 노트, 1인칭)', must: ['경험'] },
      { h: '써먹을 지원 제도', goal: '이름과 어디서 찾는지만. 금액은 공고 확인 안내', must: [] },
      { h: '자주 묻는 질문', goal: 'Q. / A. 2~3개', must: ['Q'] },
    ],
  };
  const TITLES = {
    레시피: ['{k}, {핵심 숫자 하나}만 기억하세요', '현직 바텐더의 {k} | {세부}부터 {세부}까지', '{k} 집에서 {시간}분 만에, 맛이 달라지는 {숫자}가지'],
    추천: ['{k} {숫자}가지 | {가격대·용도} 기준으로 골랐어요', '{k}, 바텐더가 손님에게 먼저 권하는 {숫자}병', '{k} 총정리 | {입문}부터 {상급}까지 무엇이 다를까'],
    입문: ['{k} 처음이라면 이것부터 | {세부} 정리', '{k}, {헷갈리는 점} 한 번에 정리', '바텐더가 알려주는 {k} {숫자}가지'],
    지원: ['{연도} {k} 총정리 | 대상·금액·신청방법', '{k} 신청 전 꼭 볼 {숫자}가지 | 탈락 이유까지', '{k}, 누가 얼마나 받나 | {연도} 공고 기준'],
    시험: ['{k} {숫자}주 합격 | 현직 바텐더 공부법', '{k} 여기서 떨어진다 | 감점 포인트 {숫자}가지', '{k} 총정리 | 필기부터 실기까지'],
    창업: ['{k}, 직접 차려 보고 알게 된 {숫자}가지', '{k} 얼마 들까 | 항목별 실제 비용', '{k} 준비 순서 | 바 사장이 다시 한다면'],
  };
  const HOOKS = [
    '공감형: 독자가 지금 겪는 상황을 2줄로 그린다 (예: "집에서 하이볼을 만들면 이상하게 밍밍하죠?")',
    '장면형: 내 바에서 있었던 한 장면으로 시작한다 (예: "어제도 손님 한 분이 똑같이 물으셨어요.")',
    '결론형: 답을 먼저 한 줄로 주고 이유를 뒤에서 푼다 (예: "결론부터 말하면 비율은 1:3이에요.")',
    '숫자형: 구체적인 숫자로 시작한다 (예: "실기 첫 연습 때 9분 40초가 걸렸어요. 시험은 7분이에요.")',
  ];

  const detect = (k) => (TYPES.find((t) => t.re.test(k)) || TYPES[TYPES.length - 1]).id;

  // ---- 지식 노트(내 경험) ----
  // knowledge.md는 '## 제목' 단위로 나뉜다. 키워드와 겹치는 섹션을 골라 원고에 경험으로 쓴다.
  let KN = [];
  function loadKnowledge(md) {
    KN = String(md || '').split(/\n(?=## )/).map((s) => s.trim()).filter((s) => /^## /.test(s) && !/^## .*\(예시\)/.test(s))
      .map((s) => ({ title: s.split('\n')[0].slice(3).trim(), body: s.split('\n').slice(1).join('\n').trim() })).filter((s) => s.body && !/^<.*>$/.test(s.body));
    return KN.map((s) => s.title);
  }
  const words = (s) => (String(s).match(/[가-힣A-Za-z0-9]{2,}/g) || []).map((w) => w.replace(/(으로|에서|은|는|이|가|을|를|의|와|과|도)$/, ''));
  function knowledgeFor(text, n = 3) {
    const q = new Set(words(text));
    return KN.map((s) => ({ ...s, score: words(s.title + ' ' + s.body).filter((w) => q.has(w)).length + (words(s.title).some((w) => q.has(w)) ? 3 : 0) }))
      .filter((s) => s.score > 0).sort((a, b) => b.score - a.score).slice(0, n).map((s) => ({ title: s.title, body: s.body.slice(0, 900) }));
  }

  // ---- 브리프 ----
  // bp: 플랫폼 조사 결과(NV.research / TS.research의 blueprint). 있으면 분량·사진·키워드를 그쪽에 맞춘다.
  function brief(keyword, platform = 'naver', bp = null, opt = {}) {
    const B = BENCH[platform]; if (!B) throw new Error("platform은 'naver' 또는 'tistory'");
    const type = opt.type || detect(keyword);
    const sections = T[type].slice();
    if (platform === 'naver' && type !== '지원' && type !== '시험') { const i = sections.findIndex((s) => s.h === '자주 묻는 질문'); if (i >= 0 && sections.length > 5) sections.splice(i, 1); }   // 네이버는 FAQ보다 경험·사진 비중
    const targetChars = Math.round(Math.min(B.chars[1], Math.max(B.chars[0], bp && bp.targetChars ? bp.targetChars : B.chars[0])));
    const photos = Math.min(B.photos[1], Math.max(B.photos[0], bp && bp.photos ? bp.photos : B.photos[0]));
    const kn = knowledgeFor(keyword + ' ' + type, 3);
    return {
      keyword, platform, type, voice: B.voice, targetChars, photos, perSection: Math.round(targetChars / (sections.length + 1)),
      titleIdeas: TITLES[type].map((t) => t.replace(/\{k\}/g, keyword)),
      titleRules: '메인 키워드를 맨 앞에, 25~38자, 구체적인 숫자 1개, "완벽 가이드·총정리해 드립니다" 같은 빈말 금지, 과장 금지',
      hooks: HOOKS,
      sections: sections.map((s, i) => ({ n: i + 1, ...s })),
      outro: '마지막 2~3문장: 한 줄 요약 → (네이버) 댓글로 질문 유도 또는 (티스토리) 관련 글 안내. "도움이 되셨길 바랍니다" 금지',
      knowledge: kn.length ? kn : '지식 노트에 맞는 경험이 없습니다. 경험 섹션은 일반론 대신 "바에서 자주 받는 질문" 형식으로 쓰고, 사용자에게 이 주제 경험을 knowledge.md에 적어 달라고 보고에 남기세요.',
      keywords: bp && bp.keywords ? bp.keywords.slice(0, 10) : [],
      mainKeywordTimes: bp && bp.mainKeywordTimes ? bp.mainKeywordTimes : 4,
    };
  }

  // ---- 섹션 단위 작성 안내 ----
  // raw: 모델이 채우는 배열. '## 소제목', 산문 문단(3~6문장, 줄바꿈 신경 쓰지 않음), '[사진: ...]', '[제품: ...]', '- 목록'.
  function next(raw, br) {
    const lines = raw.map((x) => String(x || '').trim()).filter(Boolean);
    const heads = lines.filter((x) => /^(## |■ )/.test(x));
    const tail = "\nconsole.log(JSON.stringify(W.next(raw, BR)));";
    const photoHint = br.platform === 'naver' ? '[사진: 한국어 구체 키워드, 넓은 키워드]' : '[사진: english keyword, broader keyword]';
    if (!lines.length) {
      return { step: '도입', next: '도입 3~4문장. 아래 훅 중 하나로 시작하고, 메인 키워드 "' + br.keyword + '"를 넣고, 이 글을 읽으면 무엇을 얻는지 말한다. 말투는 ' + br.voice + '. 바로 아래 사진 줄 1개.',
        hooks: br.hooks, code: "raw.push('<도입 3~4문장을 한 문자열로>', '" + photoHint + "');" + tail };
    }
    if (heads.length < br.sections.length) {
      const s = br.sections[heads.length];
      const usePhoto = br.platform === 'naver' || s.n % 2 === 1;
      const kn = s.must.includes('경험') && Array.isArray(br.knowledge) ? ' 지식 노트에서 쓸 것: ' + br.knowledge.map((k) => k.title).join(' / ') : '';
      return { step: '섹션 ' + s.n + '/' + br.sections.length, heading: s.h, goal: s.goal + kn, length: '약 ' + br.perSection + '자(3~6문장)',
        next: '소제목은 "' + s.h + '"를 이 글에 맞게 구체적으로 바꿔 쓴다(질문형·숫자 환영). 문단은 줄바꿈 신경 쓰지 말고 산문 1~2개 문자열로.',
        code: "raw.push('## <소제목>', '<문단 1>', '<문단 2>'" + (usePhoto ? ", '" + photoHint + "'" : '') + ');' + tail };
    }
    const out = lines.slice(lines.lastIndexOf(heads[heads.length - 1]) + 1);
    if (!lines.some((x) => /^\[마무리\]/.test(x))) {
      return { step: '마무리', next: br.outro, code: "raw.push('[마무리]', '<마무리 2~3문장>');" + tail };
    }
    return { step: '완료', next: '이제 W.finish(raw, BR)를 실행해 플랫폼 형식으로 바꾸고 품질 검사를 보세요.', code: 'globalThis.F = W.finish(raw, BR); console.log(JSON.stringify(F.lint));' };
  }

  // ---- 자동 문단 정리 ----
  const splitSent = (t) => String(t).replace(/\s+/g, ' ').trim().split(/(?<=[.!?…~])\s+(?=\S)/).map((s) => s.trim()).filter(Boolean);
  const len = (s) => s.replace(/\s/g, '').length;
  // 네이버식 줄: 긴 문장을 자연스러운 자리(쉼표·연결어미·조사 뒤)에서 나눈다.
  const BREAK = /(,|，|고|며|서|면|는데|지만|니까|도록|려면|이라|라서|에서|으로|에는|은|는|이|가|을|를|도|만)$/;
  function wrap(sentence, max) {
    const ws = sentence.split(' ').filter(Boolean);
    if (len(sentence) <= max * 1.15) return [ws.join(' ')];
    const lines = []; let start = 0;
    while (start < ws.length) {
      let L = 0, end = start, lastGood = -1;
      for (let i = start; i < ws.length; i++) {
        const nl = L + len(ws[i]);
        if (nl > max && i > start) break;
        L = nl; end = i;
        if (BREAK.test(ws[i]) && L >= max * 0.45) lastGood = i;
      }
      if (end < ws.length - 1 && lastGood >= start && lastGood < end) end = lastGood;   // 자연스러운 자리에서 끊는다
      lines.push(ws.slice(start, end + 1).join(' '));
      start = end + 1;
    }
    // 마지막 줄이 너무 짧으면(7자 미만) 앞줄에 붙인다
    if (lines.length > 1 && len(lines[lines.length - 1]) < 7 && len(lines[lines.length - 2]) + len(lines[lines.length - 1]) <= max * 1.35) { const t = lines.pop(); lines[lines.length - 1] += ' ' + t; }
    return lines;
  }
  const isMark = (x) => /^\[(사진|지도|제품)\s*[:：]/.test(x);

  // raw → 플랫폼 blocks. naver: 한 줄씩, 2~3줄마다 빈 줄, 소제목 '■ '(NV.checkDraft 형식). tistory: 1~2문장 문단, 소제목 '## '.
  function format(raw, platform = 'naver') {
    const B = BENCH[platform]; const out = [];
    const blank = () => { if (out.length && out[out.length - 1] !== '') out.push(''); };
    for (let x of raw) {
      x = String(x || '').trim();
      if (!x || /^\[마무리\]$/.test(x)) continue;
      if (/^(## |■ |### )/.test(x)) {
        const h = x.replace(/^(## |■ |### )/, '').trim();
        blank(); out.push(platform === 'naver' ? '■ ' + h : (/^### /.test(x) ? '### ' : '## ') + h); out.push(platform === 'naver' ? '' : '');
        continue;
      }
      if (isMark(x)) { blank(); out.push(x); out.push(''); continue; }
      if (/^(- |\d+\. |Q\. |A\. )/.test(x)) {
        if (platform === 'naver') { for (const l of wrap(x, B.lineMax + 6)) out.push(l); if (/^A\. /.test(x)) out.push(''); }
        else out.push(x);
        continue;
      }
      const sents = splitSent(x);
      if (platform === 'naver') {
        let inBlock = 0;
        for (const s of sents) {
          const ls = wrap(s, B.lineMax);
          if (inBlock && inBlock + ls.length > B.linesPerBlock[1]) { out.push(''); inBlock = 0; }
          for (const l of ls) out.push(l);
          inBlock += ls.length;
          if (inBlock >= 2 && /[?!]$/.test(s)) { out.push(''); inBlock = 0; }   // 질문·감탄 뒤에는 숨 쉴 자리
        }
        out.push('');
      } else {
        let para = '';
        for (const s of sents) {
          if (para && (len(para) + len(s) > B.paraMax || para.split(/(?<=[.!?])\s/).length >= 2)) { out.push(para); para = ''; }
          para = para ? para + ' ' + s : s;
        }
        if (para) out.push(para);
      }
    }
    while (out.length && out[out.length - 1] === '') out.pop();
    while (out.length && out[0] === '') out.shift();
    return out.filter((x, i) => !(x === '' && out[i - 1] === ''));
  }

  // ---- 품질 검사 ----
  const CLICHE = ['결론적으로', '요약하자면', '다양한', '에 대해 알아보겠습니다', '알아보도록 하겠습니다', '살펴보겠습니다', '살펴보도록', '중요합니다', '필수적입니다',
    '도움이 되셨기를', '도움이 되셨길', '도움이 되길 바랍니다', '마무리하겠습니다', '많은 분들이', '여러분', '완벽 가이드', '완벽하게', '총정리해 드리겠습니다', '하는 것이 좋습니다',
    '매력적인', '특별한 경험', '잊지 못할', '한층 더', '극대화', '선사합니다', '선사해', '것입니다', '라고 할 수 있습니다', '뿐만 아니라', '이처럼', '그렇다면'];
  const EXP = /(제가|저는|저도|저희|바결|우리 바|손님|현장|직접 (만들|해|써|가)|실제로 (해|써|만들)|해 보니|해보니|운영하면서|바를 하면서)/g;
  const ending = (s) => { s = s.replace(/[\s.!?~…"')\]]+$/, ''); return /(습니다|입니다|니다|십시오)$/.test(s) ? '합니다' : /(요|죠)$/.test(s) ? '해요' : /다$/.test(s) ? '해라' : '기타'; };

  function lint(raw, br = {}) {
    const text = raw.map((x) => String(x || '').trim()).filter((x) => x && !isMark(x) && !/^(## |■ |### |\[마무리\])/.test(x)).join('\n');
    const sents = splitSent(text.replace(/\n/g, ' '));
    const P = []; const Wn = [];
    const cl = CLICHE.map((c) => [c, (text.match(new RegExp(c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || []).length]).filter(([, n]) => n);
    const clTotal = cl.reduce((a, [, n]) => a + n, 0);
    if (clTotal > 3) P.push('AI 티 나는 표현 ' + clTotal + '회: ' + cl.map(([c, n]) => c + (n > 1 ? '×' + n : '')).join(', ') + ' → 구체적인 사실·장면으로 바꾸세요');
    else if (clTotal) Wn.push('상투적 표현: ' + cl.map(([c]) => c).join(', '));
    const ends = sents.map(ending);
    const cnt = ends.reduce((m, e) => (m[e] = (m[e] || 0) + 1, m), {});
    const want = br.voice === '합니다체' ? '합니다' : '해요';
    const other = want === '해요' ? (cnt['합니다'] || 0) : (cnt['해요'] || 0);
    if (sents.length > 6 && other / sents.length > 0.25) P.push('말투가 섞였습니다(' + want + '체로 통일): 다른 어미 ' + other + '/' + sents.length + '문장');
    let run = 1, maxRun = 1, runEnd = '';
    for (let i = 1; i < sents.length; i++) { const a = sents[i].replace(/[\s.!?~]+$/, '').slice(-2), b = sents[i - 1].replace(/[\s.!?~]+$/, '').slice(-2); if (a === b) { run++; if (run > maxRun) { maxRun = run; runEnd = a; } } else run = 1; }
    if (maxRun >= 4) P.push('같은 어미 "' + runEnd + '"가 ' + maxRun + '문장 연속 → 질문·짧은 문장·다른 어미로 리듬을 바꾸세요');
    const long = sents.filter((s) => len(s) > 60);
    if (long.length > 2) P.push('60자 넘는 긴 문장 ' + long.length + '개 → 두 문장으로 나누세요: ' + long.slice(0, 2).map((s) => s.slice(0, 25) + '…').join(' / '));
    const exp = (text.match(EXP) || []).length;
    if (exp < 2) P.push('현직 바텐더 경험 문장이 ' + exp + '개 → 2개 이상(지식 노트 활용, 1인칭: "저희 바에서는…", "손님들이 가장 많이 묻는 건…")');
    const first = sents.slice(0, 3).join(' ');
    if (!/[?？]|\d|제가|저는|저희|손님|결론/.test(first)) Wn.push('첫 3문장에 훅이 약합니다(질문·숫자·장면·결론 중 하나로 시작)');
    if (br.keyword && !first.replace(/\s/g, '').includes(br.keyword.replace(/\s/g, ''))) Wn.push('첫 3문장에 메인 키워드 "' + br.keyword + '"가 없습니다');
    const digits = (text.match(/\d+/g) || []).length;
    if (['레시피', '지원', '시험', '창업'].includes(br.type) && digits < 5) P.push('숫자가 ' + digits + '개뿐입니다. 이 유형은 용량·비율·기간·금액 같은 구체 숫자가 핵심입니다(확인된 것만)');
    const starts = (text.match(/(^|[.!?]\s)(또한|그리고|하지만|또|그래서)/g) || []).length;
    if (starts > 4) Wn.push('"또한/그리고/하지만"으로 시작하는 문장 ' + starts + '개 → 접속사 없이 써도 됩니다');
    if (/여러분/.test(text)) Wn.push('"여러분" 대신 독자를 직접 부르지 말고 상황으로 말하세요');
    if (br.platform === 'tistory' && br.type !== '추천' && !raw.some((x) => /^(## |■ ).*(질문|FAQ)/.test(String(x)))) Wn.push('자주 묻는 질문 섹션이 없습니다(구글 검색 노출에 유리)');
    const chars = len(text);
    if (br.targetChars && chars < br.targetChars * 0.85) P.push('분량 ' + chars + '자 < 목표 ' + br.targetChars + '자. 새 문단을 더하세요(이미 쓴 문단은 그대로)');
    return { ok: P.length === 0, chars, sentences: sents.length, experience: exp, cliches: clTotal, problems: P, warnings: Wn };
  }

  // raw를 검사하고 플랫폼 blocks로 바꾼다. 반환: { blocks, lint, preview }
  function finish(raw, br) {
    const L = lint(raw, br);
    const blocks = format(raw, br.platform);
    return { blocks, lint: L, preview: blocks.slice(0, 30).join('\n') };
  }

  // ---- 벤치마크 갱신(학습) ----
  // 네이버 상위 글을 읽어 구조 지표를 다시 잰다. 결과를 BENCH에 반영하고 저장할 수 있게 돌려준다. 키워드당 30초 안팎.
  async function bench(keywords, opt = {}) {
    const per = opt.per || 5; const posts = []; const accounts = new Map();
    for (const kw of keywords) {
      const tab = await openTab('https://search.naver.com/search.naver?ssc=tab.blog.all&query=' + encodeURIComponent(kw) + '&nso=so%3Ar%2Cp%3A3m');
      let links = [];
      try {
        await new Promise((r) => setTimeout(r, 2000));
        links = await tab.evaluate((max) => { const o = []; const s = new Set(); for (const a of document.querySelectorAll('a[href*="blog.naver.com/"]')) { const m = /blog\.naver\.com\/([A-Za-z0-9_-]+)\/(\d{6,})/.exec(a.href); if (m && !s.has(m[1] + m[2])) { s.add(m[1] + m[2]); o.push([m[1], m[2]]); } if (o.length >= max) break; } return o; }, per);
      } finally { await closeTab(tab); }
      for (const [bid, no] of links) {
        const t = await openTab('https://m.blog.naver.com/PostView.naver?blogId=' + bid + '&logNo=' + no);
        try {
          await new Promise((r) => setTimeout(r, 2000));
          const p = await t.evaluate(() => {
            const main = document.querySelector('.se-main-container'); if (!main) return null;
            const paras = Array.from(main.querySelectorAll('.se-component.se-text .se-text-paragraph')).map((e) => (e.innerText || '').replace(/[​﻿]/g, '').trim());
            const nonEmpty = paras.filter(Boolean);
            return { title: ((document.querySelector('.se-title-text') || {}).innerText || '').trim(), chars: nonEmpty.join('').replace(/\s/g, '').length,
              lineMed: nonEmpty.map((x) => x.replace(/\s/g, '').length).sort((a, b) => a - b)[Math.floor(nonEmpty.length / 2)] || 0,
              blanks: paras.length - nonEmpty.length, lines: nonEmpty.length, images: main.querySelectorAll('.se-component.se-image, .se-component.se-imageGroup').length,
              quotes: main.querySelectorAll('.se-component.se-quotation').length, intro: nonEmpty.slice(0, 4) };
          });
          if (p && p.chars > 500) posts.push({ kw, blogId: bid, logNo: no, ...p });
        } catch (e) { /* 건너뜀 */ } finally { await closeTab(t); }
        accounts.set(bid, (accounts.get(bid) || 0) + 1);
      }
    }
    for (const bid of Array.from(accounts.keys())) {
      try {
        const r = await fetch('https://m.blog.naver.com/api/blogs/' + bid + '/post-list?categoryNo=0&itemCount=20&page=1', { headers: { Referer: 'https://m.blog.naver.com/' } });
        const items = ((await r.json()).result || {}).items || [];
        for (const it of items) { const p = posts.find((x) => x.blogId === bid && String(x.logNo) === String(it.logNo)); if (p) p.like = it.sympathyCnt; }
      } catch (e) { /* 공감 수 없이 진행 */ }
    }
    const med = (a) => { const s = a.slice().sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : 0; };
    const liked = posts.filter((p) => p.like != null).sort((a, b) => b.like - a.like);
    const top = liked.slice(0, Math.max(3, Math.ceil(liked.length / 3)));
    const g = top.length >= 3 ? top : posts;
    const summary = { date: new Date().toISOString().slice(0, 10), keywords, posts: posts.length, chars: med(g.map((p) => p.chars)), lineMed: med(g.map((p) => p.lineMed)), images: med(g.map((p) => p.images)), quotes: med(g.map((p) => p.quotes)),
      topIntros: top.slice(0, 5).map((p) => ({ like: p.like, title: p.title, intro: p.intro })), repeatAccounts: Array.from(accounts.entries()).filter(([, n]) => n > 1).map(([b, n]) => b + '×' + n) };
    if (opt.apply !== false) applyBench(summary);
    return summary;
  }
  function applyBench(s) {
    if (!s || !s.posts) return BENCH;
    const N = BENCH.naver;
    if (s.chars) N.chars = [Math.round(Math.max(1200, s.chars * 0.85)), Math.round(Math.min(3000, s.chars * 1.3))];
    if (s.lineMed) N.lineMax = Math.min(34, Math.max(20, Math.round(s.lineMed * 1.4)));
    if (s.images) N.photos = [Math.max(3, s.images - 2), Math.min(10, s.images + 1)];
    return BENCH;
  }

  return { BENCH, TYPES, T, detect, loadKnowledge, knowledgeFor, brief, next, format, lint, finish, bench, applyBench, wrap, splitSent };
})();
console.log('W ready:', Object.keys(W).join(', '));
