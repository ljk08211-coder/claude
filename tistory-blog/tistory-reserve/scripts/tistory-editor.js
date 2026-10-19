// 티스토리 글쓰기·예약 발행 도우미 (Aside REPL용)
// 불러오기: eval(await fs.readFile('<skill-dir>/scripts/tistory-editor.js', 'utf8'))
// 모든 함수는 globalThis.TS 아래에 있다. 먼저 TS.use('https://내블로그.tistory.com')으로 블로그를 정한다.
//
// 셀렉터 출처: 2026-07~08 실제 계정에서 검증된 공개 자동화 코드(yoo9857/mytis)의 값이다.
// 티스토리는 공지 없이 마크업을 바꾸므로 후보를 여러 개 두고, 막히면 TS.probe()로 화면 구조를 덤프한다.
// 검증된 것: 제목(#post-title-inp), TinyMCE 본문, 완료(#publish-layer-btn), 공개(#open20/15/0),
//   태그(#tagText, 최대 10개), 카테고리(#category-btn + .mce-menu-item), 예약(button.btn_date '예약',
//   #dateHour/#dateMinute), 발행(#publish-btn), 틀린그림찾기 감지.
// 검증 안 된 것: 오늘이 아닌 날짜를 달력에서 고르는 것(pickDate), 예약 글 목록 읽기(listReserved).
globalThis.TS = (() => {
  const SEL = {
    title: ['#post-title-inp', 'textarea[placeholder*="제목"]', 'input[placeholder*="제목"]'],
    complete: ['#publish-layer-btn', 'button:has-text("완료")'],
    layerReady: '#publish-btn, #open20, #urlPublish',
    publish: ['#publish-btn'],
    categoryBtn: '#category-btn',
    categoryItem: '.mce-menu-item:visible',
    tagInput: ['#tagText', 'input[placeholder*="태그"]'],
    reserveTab: 'button.btn_date',
    reserveShown: 'button.btn_reserve',
    hour: '#dateHour, input[name="dateHour"], select[name="dateHour"]',
    minute: '#dateMinute, input[name="dateMinute"], select[name="dateMinute"]',
    modeBtn: ['#editor-mode-layer-btn-open', '#editor-mode-layer-btn'],
    modeHtml: ['#editor-mode-html-tistory', '#editor-mode-html'],
    modeBasic: ['#editor-mode-kakao-tistory', '#editor-mode-kakao'],
  };
  const VIS = { public: '20', protected: '15', private: '0' };
  const VIS_NAME = { public: '공개', protected: '보호', private: '비공개' };
  const WHEN = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/;
  const pad = (n) => String(n).padStart(2, '0');
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const UA = 'Mozilla/5.0 (tistory-reserve skill; personal blog helper)';
  let HOST = '';

  function use(blog) {
    const m = /^(?:https?:\/\/)?([a-z0-9-]+\.tistory\.com|[a-z0-9.-]+\.[a-z]{2,})\/?$/i.exec(String(blog || '').trim());
    if (!m) throw new Error("TS.use('https://내블로그.tistory.com') 형식으로 블로그 주소를 넣으세요.");
    HOST = 'https://' + m[1].toLowerCase();
    return HOST;
  }
  const host = () => { if (!HOST) throw new Error("NO_BLOG: 먼저 TS.use('https://내블로그.tistory.com')을 실행하세요."); return HOST; };

  async function first(page, sels, timeout = 8000) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      for (const s of sels) {
        const l = page.locator(s).first();
        if (await l.isVisible().catch(() => false)) return l;
      }
      await wait(300);
    }
    return null;
  }
  const today = () => { const d = new Date(); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); };

  // 글쓰기 화면의 confirm 창: 모드 전환은 수락, 그 밖(임시저장 이어쓰기 등)은 거절해 새 글로 시작한다.
  function guardDialogs(page) {
    if (page._tsDialog) return;
    page._tsDialog = true;
    page.on('dialog', async (d) => {
      const msg = d.message() || '';
      try { if (/모드|변경/.test(msg)) await d.accept(); else await d.dismiss(); } catch (e) { /* 이미 처리됨 */ }
    });
  }

  // ---- 로그인 ----
  async function checkLogin() {
    const tab = await openTab(host() + '/manage');
    try {
      await wait(2500);
      const url = tab.url();
      if (/\/auth\/login|accounts\.kakao\.com|kauth\.kakao\.com/.test(url)) {
        return { loggedIn: false, message: 'Aside 브라우저에서 ' + host() + '/manage 에 접속해 카카오 계정으로 티스토리에 로그인해 주세요. "로그인 상태 유지"를 켜 두면 다음부터 다시 로그인하지 않아도 됩니다. 로그인했다고 알려 주시면 이어서 진행할게요.' };
      }
      return { loggedIn: true, url };
    } finally { await closeTab(tab); }
  }

  // ---- 에디터 ----
  async function openEditor() {
    const tab = await openTab(host() + '/manage/newpost/');
    guardDialogs(tab);
    for (let i = 0; i < 50; i++) {
      const url = tab.url();
      if (/\/auth\/login|kakao\.com/.test(url)) throw new Error('LOGIN_REQUIRED: 티스토리 로그인이 필요합니다. 사용자에게 Aside에서 카카오 계정으로 로그인해 달라고 요청하세요.');
      if (await first(tab, SEL.title, 300)) break;
      await wait(400);
    }
    const t = await first(tab, SEL.title, 5000);
    if (!t) throw new Error('EDITOR_NOT_FOUND: 글쓰기 화면의 제목 칸을 찾지 못했습니다. TS.probe()로 화면 구조를 확인하세요.');
    for (let i = 0; i < 30; i++) {
      if (await tab.evaluate(() => !!(window.tinymce || window.tinyMCE)?.activeEditor).catch(() => false)) break;
      await wait(500);
    }
    await wait(1200);
    return { page: tab };
  }

  async function fillTitle(ed, title) {
    const l = await first(ed.page, SEL.title, 8000);
    if (!l) throw new Error('TITLE_NOT_FOUND: 제목 칸을 찾지 못했습니다.');
    await l.click(); await l.fill(''); await l.fill(title); await wait(300);
    if ((await l.inputValue().catch(() => '')) !== title) { await l.fill(''); await ed.page.keyboard.insertText(title); }
  }

  // 본문 글자 수(공백 포함, TinyMCE 기준). 티스토리는 위지윅 모델을 저장하므로 이 값이 실제로 저장될 본문이다.
  const bodyText = (ed) => ed.page.evaluate(() => {
    const e = (window.tinymce || window.tinyMCE)?.activeEditor;
    return e ? String(e.getContent({ format: 'text' }) || '').trim() : '';
  }).catch(() => '');

  async function writeWysiwyg(ed, html) {
    return ed.page.evaluate((value) => {
      const e = (window.tinymce || window.tinyMCE)?.activeEditor;
      if (!e || typeof e.setContent !== 'function') return false;
      e.setContent(value);
      // 화면만 바뀌면 이전(빈) 본문이 저장된다. 입력·변경 이벤트와 원본 textarea 동기화를 모두 일으킨다.
      const b = e.getBody && e.getBody();
      if (b) { b.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' })); b.dispatchEvent(new Event('change', { bubbles: true })); }
      if (e.fire) { e.fire('input'); e.fire('change'); }
      if (e.nodeChanged) e.nodeChanged();
      if (e.save) e.save();
      return true;
    }, html);
  }

  async function setMode(ed, mode) {
    const btn = await first(ed.page, SEL.modeBtn, 5000);
    if (!btn) return false;
    const want = mode === 'html' ? 'HTML' : '기본';
    if (((await btn.innerText().catch(() => '')) || '').includes(want)) return true;
    await btn.click(); await wait(700);
    const item = await first(ed.page, mode === 'html' ? SEL.modeHtml : SEL.modeBasic, 5000);
    if (!item) { await ed.page.keyboard.press('Escape').catch(() => {}); return false; }
    await item.click(); await wait(2200);
    return ((await btn.innerText().catch(() => '')) || '').includes(want);
  }

  // 본문 HTML을 넣는다. 1) TinyMCE API 2) 안 되면 HTML 모드(CodeMirror)에 넣고 기본모드로 되돌려 반영시킨다.
  async function setBody(ed, html) {
    const plain = html.replace(/<[^>]+>/g, '').replace(/\s/g, '').length;
    const need = Math.min(200, Math.floor(plain * 0.5));
    if (await writeWysiwyg(ed, html)) {
      for (let i = 0; i < 15; i++) { await wait(600); if ((await bodyText(ed)).replace(/\s/g, '').length >= need) return { ok: true, via: 'tinymce' }; }
    }
    if (await setMode(ed, 'html')) {
      await ed.page.evaluate((v) => { const w = document.querySelector('.CodeMirror'); if (w && w.CodeMirror) { w.CodeMirror.setValue(v); w.CodeMirror.refresh(); } }, html);
      await wait(800);
      await setMode(ed, 'basic');
      for (let i = 0; i < 25; i++) { await wait(700); if ((await bodyText(ed)).replace(/\s/g, '').length >= need) return { ok: true, via: 'html-mode' }; }
    }
    throw new Error('BODY_FAILED: 본문을 에디터에 넣지 못했습니다. TS.probe()로 에디터 구조를 확인하세요.');
  }

  async function readContent(ed) {
    const title = await (await first(ed.page, SEL.title, 3000))?.inputValue().catch(() => '') || '';
    const info = await ed.page.evaluate(() => {
      const e = (window.tinymce || window.tinyMCE)?.activeEditor;
      const b = e && e.getBody ? e.getBody() : null;
      return { text: e ? String(e.getContent({ format: 'text' }) || '') : '', images: b ? b.querySelectorAll('img').length : 0, heads: b ? b.querySelectorAll('h2,h3').length : 0, links: b ? b.querySelectorAll('a[href]').length : 0 };
    }).catch(() => ({ text: '', images: 0, heads: 0, links: 0 }));
    return { title, chars: info.text.replace(/\s/g, '').length, images: info.images, heads: info.heads, links: info.links, first: info.text.trim().slice(0, 60) };
  }

  // ---- 발행 레이어 ----
  async function openPublish(ed) {
    for (let a = 0; a < 3; a++) {
      const b = await first(ed.page, SEL.complete, 10000);
      if (!b) break;
      await b.click(); await wait(2500);
      if (await ed.page.locator(SEL.layerReady).first().isVisible().catch(() => false)) { await wait(400); return true; }
    }
    throw new Error('LAYER_NOT_OPEN: 발행 설정 창을 열지 못했습니다. TS.probe("layer")로 화면 구조를 확인하세요.');
  }

  // 카테고리 이름 목록. 하위 카테고리는 앞에 '- '가 붙어 나온다.
  async function listCategories(ed) {
    const btn = ed.page.locator(SEL.categoryBtn).first();
    if (!(await btn.isVisible().catch(() => false))) return [];
    await btn.click(); await wait(1200);
    const names = (await ed.page.locator(SEL.categoryItem).allInnerTexts()).map((t) => t.trim()).filter(Boolean);
    await ed.page.keyboard.press('Escape').catch(() => {});
    await wait(300);
    return names;
  }

  // 주의: 카테고리를 건드리지 않으면 '없음'이 아니라 직전 글의 카테고리를 물려받는다. 그래서 비어 있으면 '카테고리 없음'을 고른다.
  async function setCategory(ed, name) {
    const want = String(name || '').trim() || '카테고리 없음';
    const btn = ed.page.locator(SEL.categoryBtn).first();
    await btn.click(); await wait(1200);
    const items = ed.page.locator(SEL.categoryItem);
    const names = (await items.allInnerTexts()).map((t) => t.trim().replace(/^(-\s*)+/, ''));
    let i = names.findIndex((n) => n === want);
    if (i < 0) i = names.findIndex((n) => n.includes(want));
    if (i < 0) { await ed.page.keyboard.press('Escape').catch(() => {}); throw new Error('CATEGORY_NOT_FOUND: "' + want + '" / 있는 카테고리: ' + names.filter(Boolean).join(', ')); }
    await items.nth(i).click(); await wait(800);
    return names[i];
  }

  // 티스토리 태그는 10개가 상한이다. 11번째부터는 입력창이 사라져 멈춘다.
  async function setTags(ed, tags) {
    const list = (tags || []).map((t) => String(t).replace(/[,#\s]/g, '')).filter(Boolean).slice(0, 10);
    const l = await first(ed.page, SEL.tagInput, 6000);
    if (!l) throw new Error('TAG_INPUT_NOT_FOUND: 태그 입력칸을 찾지 못했습니다.');
    let done = 0;
    for (const t of list) {
      try { await l.click({ timeout: 5000 }); await ed.page.keyboard.insertText(t); await wait(200); await ed.page.keyboard.press('Enter'); await wait(350); done++; } catch (e) { break; }
    }
    return { done, tags: list.slice(0, done) };
  }

  async function setVisibility(ed, v) {
    if (!VIS[v]) throw new Error('visibility는 public | protected | private 중 하나');
    const id = 'open' + VIS[v];
    const lab = ed.page.locator('label[for="' + id + '"]').first();
    if (await lab.isVisible().catch(() => false)) await lab.click();
    else await ed.page.locator('#' + id).first().check({ force: true });
    await wait(300);
  }

  // 달력에 지금 보이는 예약 날짜를 읽는다. 연도가 없으면 올해로 본다.
  async function shownDate(ed) {
    const t = ((await ed.page.locator(SEL.reserveShown).first().innerText().catch(() => '')) || '').trim();
    let m = /(\d{4})\D+(\d{1,2})\D+(\d{1,2})/.exec(t);
    if (m) return { text: t, y: +m[1], m: +m[2], d: +m[3] };
    m = /(\d{1,2})\D+(\d{1,2})/.exec(t);
    return m ? { text: t, y: new Date().getFullYear(), m: +m[1], d: +m[2] } : { text: t };
  }

  // [검증 안 됨] 예약 날짜 버튼을 눌러 달력을 열고 원하는 날을 고른다. 결과는 setSchedule이 다시 확인한다.
  async function pickDate(ed, y, mo, d) {
    await ed.page.locator(SEL.reserveShown).first().click().catch(() => {});
    await wait(700);
    for (let k = 0; k < 14; k++) {
      const r = await ed.page.evaluate(({ y, mo, d }) => {
        const vis = (el) => { const b = el.getBoundingClientRect(); const s = getComputedStyle(el); return b.width > 0 && b.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
        const cal = Array.from(document.querySelectorAll('[class*="calendar" i], [class*="datepicker" i], [class*="date_picker" i], [class*="layer_date" i]')).filter(vis)
          .sort((a, b) => b.querySelectorAll('td, button').length - a.querySelectorAll('td, button').length)[0];
        if (!cal) return { err: 'NO_CALENDAR' };
        const head = /(\d{4})\D+(\d{1,2})/.exec(cal.innerText || '');
        if (!head) return { err: 'NO_HEADER' };
        const cy = +head[1], cm = +head[2];
        if (cy * 12 + cm < y * 12 + mo) {
          const next = Array.from(cal.querySelectorAll('button, a, span')).find((e) => vis(e) && /next|다음/i.test((e.className || '') + ' ' + (e.getAttribute('aria-label') || '') + ' ' + (e.innerText || '')));
          if (!next) return { err: 'NO_NEXT' };
          next.click(); return { moved: true };
        }
        if (cy !== y || cm !== mo) return { err: 'PAST_MONTH ' + cy + '-' + cm };
        const cell = Array.from(cal.querySelectorAll('td button, td a, td span, td, button')).find((e) => vis(e) && (e.innerText || '').trim() === String(d)
          && !/disabled|dimmed|dim|other|prev|next|off/i.test((e.className || '') + ' ' + ((e.closest('td') || {}).className || '')) && !e.disabled);
        if (!cell) return { err: 'NO_DAY' };
        cell.click(); return { picked: true };
      }, { y, mo, d });
      if (r.picked) { await wait(600); return true; }
      if (r.err) throw new Error('DATE_UI: 예약 달력에서 날짜를 고르지 못했습니다(' + r.err + '). 오늘 날짜 예약만 쓰거나 TS.probe("layer")로 달력 구조를 확인하세요.');
      await wait(400);
    }
    throw new Error('DATE_UI: 달력 넘김이 끝나지 않았습니다.');
  }

  async function fillTime(loc, value) {
    const tag = await loc.evaluate((e) => e.tagName.toLowerCase());
    if (tag === 'select') {
      const opts = await loc.evaluate((e) => Array.from(e.options).map((o) => o.value));
      const pick = opts.find((o) => Number(o) === value);
      if (pick === undefined) throw new Error('TIME_UI: 시간 선택지에 ' + value + '이(가) 없습니다: ' + opts.join(','));
      await loc.selectOption(pick);
    } else { await loc.fill(String(value)); await loc.press('Tab').catch(() => {}); }
    await wait(250);
    return Number(await loc.inputValue().catch(() => NaN));
  }

  // when: 'YYYY-MM-DD HH:MM' (이 컴퓨터 시각 기준, 지금부터 15분 이후). 즉시 발행으로 넘어가는 일은 없다. 실패하면 던진다.
  async function setSchedule(ed, when) {
    const m = WHEN.exec(when);
    if (!m) throw new Error("예약 시각 형식은 'YYYY-MM-DD HH:MM'");
    const [y, mo, d, h, mi] = m.slice(1).map(Number);
    if (new Date(y, mo - 1, d, h, mi) - Date.now() < 15 * 60000) throw new Error('TOO_SOON: 예약 시각은 지금부터 15분 이후여야 합니다: ' + when);
    const p = ed.page;
    let tab = p.locator(SEL.reserveTab).filter({ hasText: /^\s*예약\s*$/ }).first();
    if (await tab.isVisible().catch(() => false)) await tab.click();
    else {
      const ok = await p.evaluate(() => {
        const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
        const t = Array.from(document.querySelectorAll('label, button, a, li, span')).filter((e) => vis(e) && /^예약$/.test((e.textContent || '').trim()))[0];
        if (!t) return false; t.click(); return true;
      });
      if (!ok) throw new Error('RESERVE_UI: 발행 창에서 "예약"을 찾지 못했습니다. TS.probe("layer")로 확인하세요.');
    }
    await wait(800);
    const same = (s) => s.y === y && s.m === mo && s.d === d;
    let s = await shownDate(ed);
    if (!same(s)) {
      const di = p.locator('input[type="date"], input#publish-date, input[name="publishDate"], input[name="reserveDate"]').first();
      if (await di.count()) await di.fill(y + '-' + pad(mo) + '-' + pad(d));
      else await pickDate(ed, y, mo, d);
      s = await shownDate(ed);
      if (!same(s)) throw new Error('DATE_UI: 예약 날짜가 ' + (s.text || '(표시 없음)') + '로 보입니다. 목표 ' + y + '-' + pad(mo) + '-' + pad(d) + '. 예약하지 않고 멈춥니다.');
    }
    const hl = p.locator(SEL.hour).first(); const ml = p.locator(SEL.minute).first();
    if (!(await hl.count()) || !(await ml.count())) throw new Error('TIME_UI: 예약 시·분 입력칸을 찾지 못했습니다.');
    const gh = await fillTime(hl, h); const gm = await fillTime(ml, mi);
    if (gh !== h || gm !== mi) throw new Error('TIME_UI: 예약 시각이 ' + gh + ':' + gm + '로 들어갔습니다. 목표 ' + h + ':' + mi);
    return { date: s.text, hour: gh, minute: gm };
  }

  // 발행 창에 실제로 설정된 값을 읽는다. 최종 버튼 전에 반드시 확인한다.
  async function readLayer(ed) {
    const L = await ed.page.evaluate(() => {
      const chk = (id) => { const e = document.getElementById(id); return !!(e && e.checked); };
      const vis = chk('open20') ? 'public' : chk('open15') ? 'protected' : chk('open0') ? 'private' : '';
      const rb = Array.from(document.querySelectorAll('button.btn_date')).find((b) => /^\s*예약\s*$/.test(b.textContent || ''));
      const val = (sel) => { const e = document.querySelector(sel); return e ? e.value : ''; };
      const cat = document.getElementById('category-btn');
      const pub = document.getElementById('publish-btn');
      return { visibility: vis, reserve: rb ? rb.classList.contains('on') || rb.getAttribute('aria-pressed') === 'true' : null,
        hour: val('#dateHour, [name="dateHour"]'), minute: val('#dateMinute, [name="dateMinute"]'),
        category: cat ? cat.innerText.split('\n')[0].trim() : '', publishLabel: pub ? pub.innerText.trim() : '' };
    });
    const s = await shownDate(ed);
    return { ...L, date: s.text, dateParsed: s.y ? s.y + '-' + pad(s.m) + '-' + pad(s.d) : '' };
  }

  // 틀린그림찾기(카카오 보안 퍼즐). 짧은 시간에 여러 번 발행하면 뜬다. 자동으로 풀지 않는다.
  async function hasCaptcha(page) {
    for (const f of page.frames()) {
      const found = await f.evaluate(() => {
        const vis = (el) => { for (let c = el, i = 0; c && i < 7; c = c.parentElement, i++) { const s = getComputedStyle(c); if (s.display === 'none' || s.visibility === 'hidden') return false; const r = c.getBoundingClientRect(); if (r.width > 40 && r.height > 40) return true; } return false; };
        const node = Array.from(document.querySelectorAll('[class*="captcha" i],[id*="captcha" i],[class*="kaptcha" i],[id*="kaptcha" i]')).some(vis);
        const text = document.body ? document.body.innerText : '';
        return node || /지도(?:에서|에 있는).{0,80}(?:장소|명칭).{0,40}입력|정답을 입력해주세요|DKAPTCHA/is.test(text);
      }).catch(() => false);
      if (found) return true;
    }
    return false;
  }

  // 최종 예약 버튼. expect = { when, visibility, title, minChars(기본 1500) }.
  // 화면의 제목·글자 수·예약 상태·날짜·시각·공개 범위가 하나라도 다르면 버튼을 누르지 않고 NOT_CONFIRMED를 던진다.
  async function confirm(ed, expect) {
    if (!expect || !expect.when || !expect.visibility) throw new Error('confirm(ed, { when, visibility, title }) 형태로 기대값을 넘기세요.');
    const m = WHEN.exec(expect.when);
    const c = await readContent(ed); const L = await readLayer(ed);
    const problems = [];
    const minChars = expect.minChars || 1500;
    if (c.chars < minChars) problems.push('본문 ' + c.chars + '자 < ' + minChars + '자');
    if (expect.title && c.title !== expect.title) problems.push('제목 불일치: ' + c.title);
    if (L.visibility !== expect.visibility) problems.push('공개 범위 불일치: ' + (L.visibility || '?'));
    if (L.reserve !== true) problems.push('예약이 선택돼 있지 않습니다(즉시 발행 위험)');
    if (!m || L.dateParsed !== m[1] + '-' + m[2] + '-' + m[3]) problems.push('예약 날짜 불일치: ' + (L.date || '?'));
    if (!m || Number(L.hour) !== Number(m[4]) || Number(L.minute) !== Number(m[5])) problems.push('예약 시각 불일치: ' + L.hour + ':' + L.minute);
    if (problems.length) throw new Error('NOT_CONFIRMED: ' + problems.join(' / '));
    const btn = await first(ed.page, SEL.publish, 8000);
    if (!btn) throw new Error('PUBLISH_BTN_NOT_FOUND');
    await btn.click();
    for (let i = 0; i < 60; i++) {
      await wait(1000);
      if (await hasCaptcha(ed.page)) return { ok: false, captcha: true, message: '티스토리 보안 퍼즐(틀린그림찾기)이 떴습니다. 자동으로 풀지 않습니다. 사용자가 Aside 화면에서 직접 풀고 "예약" 버튼을 다시 누르거나, 다음 실행 때 다시 시도합니다.' };
      if (!/\/manage\/newpost/.test(ed.page.url())) return { ok: true, url: ed.page.url() };
    }
    return { ok: false, url: ed.page.url(), message: '버튼을 눌렀지만 글쓰기 화면을 벗어나지 않았습니다. 관리 화면의 글 목록을 확인하세요.' };
  }

  // [검증 안 됨] 관리 화면 글 목록에서 '예약'이 들어간 줄을 읽는다. 제목 앞부분이 목록에 보이면 성공으로 본다.
  async function listReserved() {
    const tab = await openTab(host() + '/manage/posts/');
    try {
      await wait(3000);
      const rows = await tab.evaluate(() => {
        const out = []; const seen = new Set();
        for (const el of document.querySelectorAll('li, tr, [class*="post" i]')) {
          const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
          if (!/예약/.test(t) || t.length > 300 || t.length < 6) continue;
          if (Array.from(el.children).some((c) => /예약/.test(c.innerText || '') && (c.innerText || '').length > 6 && c.matches('li, tr, [class*="post" i]'))) continue;   // 가장 안쪽 줄만
          if (!seen.has(t)) { seen.add(t); out.push(t); }
        }
        return out.slice(0, 40);
      });
      return { url: host() + '/manage/posts/', items: rows };
    } finally { await closeTab(tab); }
  }
  const isReserved = (list, title) => list.items.some((t) => t.replace(/\s/g, '').includes(String(title).replace(/\s/g, '').slice(0, 15)));

  // 화면 구조 덤프. 셀렉터가 바뀌어 막혔을 때 쓴다. where: 'editor'(기본) | 'layer'(발행 창을 연 상태) | 'reserve'(예약 탭까지 누른 상태)
  // 아무것도 발행하지 않고 탭을 닫는다.
  async function probe(where = 'editor') {
    const ed = await openEditor();
    try {
      if (where !== 'editor') { await fillTitle(ed, '구조 확인용(발행 안 함)'); await writeWysiwyg(ed, '<p>' + '구조 확인 '.repeat(30) + '</p>'); await openPublish(ed); }
      if (where === 'reserve') { const t = ed.page.locator(SEL.reserveTab).filter({ hasText: /예약/ }).first(); await t.click().catch(() => {}); await wait(800); await ed.page.locator(SEL.reserveShown).first().click().catch(() => {}); await wait(800); }
      return await ed.page.evaluate(() => {
        const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
        const list = (sel) => Array.from(document.querySelectorAll(sel)).filter(vis).slice(0, 80).map((el) => ({ tag: el.tagName.toLowerCase(), id: el.id || undefined, cls: (el.className && el.className.toString().slice(0, 80)) || undefined, name: el.getAttribute('name') || undefined, type: el.type || undefined, text: ((el.innerText || el.value || '').trim().slice(0, 40)) || undefined, aria: el.getAttribute('aria-label') || undefined }));
        return { url: location.href, tinymce: !!(window.tinymce || window.tinyMCE), codeMirror: !!document.querySelector('.CodeMirror'), buttons: list('button'), inputs: list('input, textarea, select'), labels: list('label'), calendars: list('[class*="calendar" i], [class*="datepicker" i]') };
      });
    } finally { await closeTab(ed.page); }
  }

  // ---- 원고 → HTML ----
  // blocks 문법: '## 소제목' '### 작은 소제목' '- 목록' '> 강조 박스' '[사진: 영어 키워드, 더 넓은 영어 키워드]' '[제품: products의 name]'
  // 빈 문자열 ''은 문단 구분. **굵게**. 그 밖의 줄은 문단(<p>)이 된다.
  const MARK = /^\[(사진|제품)\s*[:：]\s*(.+?)\]$/;
  const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // 무료 사진 찾기: 1) 위키미디어 공용(상업 이용 가능한 CC·퍼블릭 도메인) 2) Openverse(상업 이용 가능 필터).
  // 키워드는 영어가 잘 찾힌다. 출처 표기를 캡션에 붙인다(CC BY 조건).
  async function findPhoto(keywords, used = new Set()) {
    const strip = (h) => String(h || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
    const okLic = (l) => /^(CC0|Public domain|PD|CC BY(-SA)? \d|CC BY(-SA)?$)/i.test(l || '') && !/NC|ND/i.test(l || '');
    for (const kw of keywords) {
      try {
        const u = 'https://commons.wikimedia.org/w/api.php?action=query&format=json&origin=*&generator=search&gsrnamespace=6&gsrlimit=12'
          + '&gsrsearch=' + encodeURIComponent(kw + ' filetype:bitmap') + '&prop=imageinfo&iiprop=url|size|extmetadata&iiurlwidth=1000'
          + '&iiextmetadatafilter=LicenseShortName|Artist';
        const r = await fetch(u, { headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(10000) });
        const pages = Object.values(((await r.json()).query || {}).pages || {}).sort((a, b) => (a.index || 0) - (b.index || 0));
        for (const pg of pages) {
          const ii = (pg.imageinfo || [])[0]; if (!ii) continue;
          const src = ii.thumburl || ii.url; const md = ii.extmetadata || {};
          const lic = strip(md.LicenseShortName && md.LicenseShortName.value);
          if (!src || used.has(src) || !/\.(jpe?g|png)$/i.test(ii.url) || ii.width < 600 || !okLic(lic)) continue;
          used.add(src);
          return { keyword: kw, src, alt: kw, credit: (strip(md.Artist && md.Artist.value) || '작가 미상').slice(0, 60) + ' / ' + lic + ' / Wikimedia Commons', link: ii.descriptionurl };
        }
      } catch (e) { /* 다음 소스로 */ }
      try {
        const u = 'https://api.openverse.org/v1/images/?page_size=12&mature=false&license_type=commercial&q=' + encodeURIComponent(kw);
        const r = await fetch(u, { headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(10000) });
        for (const it of (await r.json()).results || []) {
          if (!it.url || used.has(it.url) || (it.width && it.width < 600) || /nc|nd/i.test(it.license || '')) continue;
          used.add(it.url);
          const lic = (it.license === 'cc0' || it.license === 'pdm') ? it.license.toUpperCase() : 'CC ' + String(it.license).toUpperCase() + ' ' + (it.license_version || '');
          return { keyword: kw, src: it.url, alt: it.title || kw, credit: (it.creator || '작가 미상').slice(0, 60) + ' / ' + lic.trim() + ' / ' + (it.source || 'Openverse'), link: it.foreign_landing_url };
        }
      } catch (e) { /* 다음 키워드로 */ }
    }
    return null;
  }

  function productCard(p) {
    return '<div style="border:1px solid #e3e3e3;border-radius:10px;padding:14px 16px;margin:24px 0;">'
      + '<p style="margin:0 0 6px;font-weight:bold;">' + esc(p.name) + '</p>'
      + (p.desc ? '<p style="margin:0 0 10px;color:#555;">' + esc(p.desc) + '</p>' : '')
      + '<p style="margin:0;"><a href="' + esc(p.url) + '" target="_blank" rel="sponsored nofollow noopener">' + esc(p.cta || '제품 보러 가기') + ' →</a></p></div>';
  }

  // 원고 blocks를 티스토리 본문 HTML로 바꾼다. 사진·제품 줄은 실제 사진·제품 카드로 바뀐다.
  // settings: calendar 폴더의 settings.json (products, disclosure, footer). 반환: { html, photos, products, missed }
  async function toHtml(blocks, settings = {}) {
    const products = settings.products || [];
    const out = []; const photos = []; const usedProducts = []; const missed = []; const used = new Set();
    let list = [];
    const flush = () => { if (list.length) { out.push('<ul>' + list.map((x) => '<li>' + inline(x) + '</li>').join('') + '</ul>'); list = []; } };
    for (const raw of blocks) {
      const line = String(raw || '').trim();
      if (/^- /.test(line)) { list.push(line.slice(2)); continue; }
      flush();
      if (!line) continue;
      const mk = MARK.exec(line);
      if (mk && mk[1] === '사진') {
        const ph = await findPhoto(mk[2].split(/[,，]/).map((s) => s.trim()).filter(Boolean), used);
        if (!ph) { missed.push(line); continue; }
        photos.push(ph);
        out.push('<figure style="margin:24px 0;text-align:center;"><img src="' + esc(ph.src) + '" alt="' + esc(ph.alt) + '" style="max-width:100%;height:auto;" />'
          + '<figcaption style="font-size:12px;color:#888;margin-top:6px;">사진: ' + (ph.link ? '<a href="' + esc(ph.link) + '" target="_blank" rel="nofollow noopener">' + esc(ph.credit) + '</a>' : esc(ph.credit)) + '</figcaption></figure>');
        continue;
      }
      if (mk && mk[1] === '제품') {
        const p = products.find((x) => x.name === mk[2].trim()) || products.find((x) => x.name.includes(mk[2].trim()));
        if (!p || !p.url || /XXXX/.test(p.url)) { missed.push(line); continue; }   // 예시 주소가 그대로 나가지 않게
        if (!usedProducts.includes(p.name)) usedProducts.push(p.name);
        out.push(productCard(p));
        continue;
      }
      if (/^### /.test(line)) out.push('<h3>' + inline(line.slice(4)) + '</h3>');
      else if (/^## /.test(line)) out.push('<h2>' + inline(line.slice(3)) + '</h2>');
      else if (/^> /.test(line)) out.push('<blockquote>' + inline(line.slice(2)) + '</blockquote>');
      else out.push('<p>' + inline(line) + '</p>');
    }
    flush();
    // 제휴 링크가 들어간 글은 첫머리에 대가성 문구를 보이게 넣는다(공정위 추천·보증 심사지침).
    if (usedProducts.length) out.unshift('<p style="font-size:13px;color:#777;">' + esc(settings.disclosure || '이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.') + '</p>');
    const footer = (settings.footer || []).filter((f) => f && f.text && f.url);
    if (footer.length) out.push('<hr />' + footer.map((f) => '<p><a href="' + esc(f.url) + '" target="_blank" rel="noopener">' + esc(f.text) + '</a></p>').join(''));
    return { html: out.join('\n'), photos, products: usedProducts, missed };
  }

  // 키워드에 맞는 제품을 settings.products에서 고른다(keywords 겹침 순). 글에는 최대 2개만 넣는다.
  function matchProducts(text, settings = {}, n = 2) {
    const flat = String(text || '').replace(/\s/g, '');
    return (settings.products || []).filter((p) => p.url && !/XXXX/.test(p.url))
      .map((p) => ({ name: p.name, hits: (p.keywords || []).filter((k) => flat.includes(String(k).replace(/\s/g, ''))).length }))
      .filter((p) => p.hits > 0).sort((a, b) => b.hits - a.hits).slice(0, n);
  }

  // ---- 원고 검사 ----
  function checkDraft(blocks, bp, settings = {}) {
    const lines = blocks.map((b) => String(b || '').trim());
    const marks = lines.map((b) => MARK.exec(b)).filter(Boolean);
    const textLines = lines.filter((b) => b && !MARK.test(b));
    const all = textLines.map((b) => b.replace(/^(#{2,3}|-|>) /, '')).join('\n');
    const chars = all.replace(/\s/g, '').length;
    const heads = lines.filter((b) => /^## /.test(b)).length;
    const photos = marks.filter((m) => m[1] === '사진').length;
    const prods = marks.filter((m) => m[1] === '제품').map((m) => m[2].trim());
    const res = { chars, heads, photos, products: prods, problems: [], warnings: [] };
    const minChars = Math.max(1800, bp ? Math.round(bp.targetChars * 0.9) : 1800);
    const minHeads = Math.max(3, bp ? bp.heads : 3);
    if (chars < minChars) res.problems.push('본문 ' + chars + '자 < 목표 ' + minChars + '자');
    if (heads < minHeads) res.problems.push('## 소제목 ' + heads + '개 < 목표 ' + minHeads + '개');
    const wantPhotos = bp ? bp.photos : 2;
    if (photos < wantPhotos) res.problems.push('사진 자리 ' + photos + '개 < 목표 ' + wantPhotos + '개. 소제목 아래에 [사진: 영어 키워드, 더 넓은 영어 키워드] 줄을 넣으세요(예: [사진: highball cocktail, whisky glass])');
    if (lines.findIndex((b) => /^\[사진/.test(b)) > 6) res.warnings.push('첫 사진이 늦게 나옵니다. 첫 사진이 대표 이미지(썸네일)가 되므로 도입 문단 바로 아래에 두세요');
    if (prods.length > 2) res.problems.push('제품 카드 ' + prods.length + '개 > 2개. 광고처럼 보여서 2개까지만 넣습니다');
    const names = (settings.products || []).map((p) => p.name);
    const unknown = prods.filter((p) => !names.some((n) => n === p || n.includes(p)));
    if (unknown.length) res.problems.push('settings.json에 없는 제품: ' + unknown.join(', ') + ' → products의 name을 그대로 쓰세요');
    if (/https?:\/\/|www\./.test(all)) res.problems.push('본문에 주소가 있습니다. 링크는 [제품: ] 줄과 settings의 footer로만 넣습니다');
    if (bp) {
      const flat = all.replace(/\s/g, '');
      const mk = bp.mainKeyword.replace(/\s/g, '');
      res.mainKeyword = (flat.match(new RegExp(mk.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || []).length;
      if (res.mainKeyword < bp.mainKeywordTimes) res.problems.push('메인 키워드 "' + bp.mainKeyword + '" ' + res.mainKeyword + '회 < ' + bp.mainKeywordTimes + '회');
      const maxMain = Math.max(bp.mainKeywordTimes * 2, Math.ceil(chars / 200));
      if (res.mainKeyword > maxMain) res.problems.push('메인 키워드 "' + bp.mainKeyword + '" ' + res.mainKeyword + '회 > ' + maxMain + '회. 반복된 문장 일부를 다른 표현으로 바꾸세요');
      res.missingKeywords = bp.keywords.filter((k) => !flat.includes(k.replace(/\s/g, '')));
      if (res.missingKeywords.length > Math.floor(bp.keywords.length / 3)) res.problems.push('빠진 키워드: ' + res.missingKeywords.join(', '));
      if (!lines[0] || !lines.slice(0, 4).join('').replace(/\s/g, '').includes(mk)) res.warnings.push('첫 문단에 메인 키워드가 없습니다');
    }
    // 위스키·칵테일은 영어 이름이 정상적으로 나오므로 영어는 경고만 한다. 사진 줄은 영어가 맞다.
    const srcLow = (bp && bp._src ? bp._src : '').toLowerCase();
    const eng = Array.from(new Set(all.match(/[A-Za-z][A-Za-z-]{2,}/g) || [])).filter((w) => !srcLow.includes(w.toLowerCase()));
    if (eng.length > 6) res.warnings.push('영어 단어가 많습니다: ' + eng.slice(0, 10).join(', ') + ' → 브랜드명이 아니면 한국어로 바꾸세요');
    const cjk = Array.from(new Set(all.match(/[぀-ヿ一-鿿]+/g) || [])).filter((w) => !(bp && bp._src || '').includes(w));
    if (cjk.length) res.problems.push('한자·일본어가 섞였습니다: ' + cjk.slice(0, 8).join(', ') + ' → 한국어로 바꾸세요');
    const seen = new Map();
    for (const s of all.split(/(?<=[.!?])\s+|\n+/).map((x) => x.replace(/\s/g, '')).filter((x) => x.length >= 20)) seen.set(s, (seen.get(s) || 0) + 1);
    const dup = Array.from(seen.entries()).filter(([, n]) => n > 1).map(([s]) => s.slice(0, 20));
    if (dup.length) res.problems.push('같은 문장이 반복됩니다 ' + dup.length + '곳: ' + dup.slice(0, 3).join(' / '));
    if (bp && bp._src) {
      const src = bp._src; const flat2 = all.replace(/\s/g, ''); const hits = [];
      for (let i = 0; i + 20 <= flat2.length && hits.length < 5; i += 4) { const piece = flat2.slice(i, i + 20); if (src.includes(piece)) { hits.push(piece); i += 16; } }
      if (hits.length) res.problems.push('참고 글과 똑같은 문장(20자 이상) ' + hits.length + '곳: ' + hits.join(' / ') + ' → 내 말로 새로 쓰세요');
    }
    res.ok = res.problems.length === 0;
    return res;
  }

  // ---- 자료 조사: 다음(Daum) 블로그 검색 상위의 티스토리 글을 읽어 포맷과 키워드를 뽑는다 ----
  const STOP = new Set(['그리고','하지만','그래서','이번','오늘','정말','진짜','바로','있는','있습니다','합니다','하는','해서','하면','이렇게','저는','제가','우리','여러분','그냥','너무','많이','다양한','통해','위해','대한','같은','경우','때문','부분','것을','것이','수가','하기','있어요','해요','입니다','글을','글이','글은','이제','그럼','관련','정도','가능','때문에','있다','한다','된다','있고','다른','사진','안녕하세요','티스토리','공감','댓글','구독','블로그']);
  const JOSA = /(으로|에서|까지|부터|처럼|보다|에게|한테|이랑|이나|이고|이며|이라|라고|하고|으로는|에서는|에는|은|는|이|가|을|를|에|의|와|과|도|만|로|요)$/;
  const tokens = (s) => (s.match(/[가-힣A-Za-z0-9]{2,}/g) || []).map((w) => (w.length > 2 ? w.replace(JOSA, '') : w)).filter((w) => w.length >= 2 && !STOP.has(w) && !/^\d+$/.test(w));

  async function readPost(url) {
    const t = await openTab(url);
    try {
      await wait(2500);
      await t.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); await wait(1000);
      return await t.evaluate(() => {
        const cands = ['.tt_article_useless_p_margin', '.contents_style', '#article-view', '.article-view', '.entry-content', '.article_view', '.area_view', 'article'];
        let main = null;
        for (const s of cands) for (const e of document.querySelectorAll(s)) if (!main || (e.innerText || '').length > (main.innerText || '').length) main = e;
        if (!main) return null;
        const q = (s, r = main) => Array.from(r.querySelectorAll(s));
        const text = (main.innerText || '').replace(/\s+/g, ' ').trim();
        const paras = q('p').map((p) => (p.innerText || '').trim()).filter((x) => x.length > 10);
        const meta = (p) => (document.querySelector('meta[property="' + p + '"]') || {}).content || '';
        return { title: (meta('og:title') || document.title || '').trim(), date: meta('article:published_time').slice(0, 10), chars: text.replace(/\s/g, '').length,
          heads: q('h2, h3, h4').map((h) => (h.innerText || '').replace(/\s+/g, ' ').trim()).filter(Boolean).slice(0, 12),
          images: q('img').filter((i) => !/emoji|icon|profile/i.test(i.src)).length,
          tags: Array.from(new Set(Array.from(document.querySelectorAll('a[rel="tag"], .tags a, .tag_label a, .area_tag a, [class*="tag"] a[href*="/tag/"]')).map((a) => (a.innerText || '').trim().replace(/^#/, '')).filter(Boolean))).slice(0, 15),
          avgParagraph: paras.length ? Math.round(paras.join('').replace(/\s/g, '').length / paras.length) : 0,
          intro: paras.slice(0, 2).join(' ').slice(0, 160), text };
      });
    } finally { await closeTab(t); }
  }

  async function research(query, n = 3, pool = 8) {
    const searchUrl = 'https://search.daum.net/search?w=blog&q=' + encodeURIComponent(query);
    const own = HOST ? HOST.replace(/^https:\/\//, '') : '';
    const tab = await openTab(searchUrl);
    let links = [];
    try {
      await wait(2500);
      links = await tab.evaluate(({ max, own }) => {
        const out = []; const seen = new Set();
        for (const a of document.querySelectorAll('a[href*=".tistory.com/"]')) {
          const m = /^https?:\/\/([a-z0-9-]+\.tistory\.com)\/(entry\/[^?#]+|\d+)/i.exec(a.href);
          if (!m || m[1] === own) continue;
          const k = m[1] + '/' + m[2]; if (seen.has(k)) continue; seen.add(k);
          out.push('https://' + k); if (out.length >= max) break;
        }
        return out;
      }, { max: pool, own });
    } finally { await closeTab(tab); }
    const posts = [];
    for (let i = 0; i < links.length; i++) {
      try { const p = await readPost(links[i]); if (p && p.chars > 800) posts.push({ rank: i + 1, url: links[i], ...p }); } catch (e) { /* 열리지 않는 글은 건너뛴다 */ }
    }
    if (!posts.length) throw new Error('RESEARCH_EMPTY: 다음 블로그 검색에서 읽을 수 있는 티스토리 글을 찾지 못했습니다. 키워드를 바꿔 보세요.');
    const picked = posts.slice(0, n);   // 검색 순위 = 구글·다음이 좋게 본 글
    const bp = blueprint(query, picked);
    Object.defineProperty(bp, '_src', { value: posts.map((p) => p.text.replace(/\s/g, '')).join('|'), enumerable: false });
    return { query, searchUrl, checked: posts.length, picked: picked.map((p) => ({ ...p, text: p.text.slice(0, 3000) })), blueprint: bp };
  }

  function blueprint(query, posts) {
    const med = (xs) => { const s = xs.slice().sort((a, b) => a - b); return s.length ? s[Math.floor((s.length - 1) / 2)] : 0; };
    const df = new Map(); const tf = new Map();
    for (const p of posts) {
      const ws = tokens(p.title + ' ' + p.title + ' ' + p.heads.join(' ') + ' ' + p.text + ' ' + p.tags.join(' '));
      for (const w of ws) tf.set(w, (tf.get(w) || 0) + 1);
      for (const w of new Set(ws)) df.set(w, (df.get(w) || 0) + 1);
    }
    const need = posts.length >= 3 ? 2 : 1;
    const keywords = Array.from(tf.entries()).filter(([w]) => df.get(w) >= need).sort((a, b) => b[1] - a[1]).slice(0, 12).map(([w]) => w);
    const tagCount = new Map();
    for (const p of posts) for (const t of p.tags) tagCount.set(t, (tagCount.get(t) || 0) + 1);
    const mainKeyword = query.trim(); const mk = mainKeyword.replace(/\s/g, '');
    const images = med(posts.map((p) => p.images));
    return {
      mainKeyword,
      mainKeywordTimes: Math.max(4, Math.min(10, med(posts.map((p) => (p.text.replace(/\s/g, '').split(mk).length - 1))))),
      titleExamples: posts.map((p) => p.title),
      titleLength: med(posts.map((p) => p.title.length)),
      targetChars: Math.min(3200, Math.max(1800, med(posts.map((p) => p.chars)))),   // 무료 모델이 끝까지 쓸 수 있는 분량으로 상한
      heads: Math.min(7, Math.max(3, med(posts.map((p) => p.heads.length)))),
      headExamples: posts.map((p) => p.heads.slice(0, 7)),
      images,
      photos: Math.min(4, Math.max(2, Math.ceil(images / 3))),
      avgParagraph: med(posts.map((p) => p.avgParagraph)),
      keywords,
      tags: Array.from(tagCount.entries()).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([t]) => t),
    };
  }

  // ---- 니치 조사: 구글·네이버 자동완성으로 사람들이 실제로 찾는 세부 키워드를 모은다 ----
  // gRank/nRank는 자동완성에 뜬 순서(1이 가장 위)다. 검색량 숫자가 아니다. 둘 다 뜨면(both) 수요가 확실한 편이다.
  async function niche(theme, opt = {}) {
    const base = String(theme || '').trim();
    if (!base) throw new Error('niche(주제): 주제를 넣으세요. 예: TS.niche("위스키")');
    const mods = opt.mods || ['', ' 추천', ' 방법', ' 비용', ' 종류', ' 차이', ' 초보', ' 준비', ' 조건', ' 후기'];
    const found = new Map();
    const add = (k, rank, src, q) => {
      k = String(k || '').replace(/\s+/g, ' ').trim();
      if (!k || k === base || k.length > 30 || !/[가-힣]/.test(k)) return;
      const c = found.get(k) || { keyword: k, gRank: null, nRank: null, from: q };
      if (src === 'g' && (c.gRank === null || rank < c.gRank)) c.gRank = rank;
      if (src === 'n' && (c.nRank === null || rank < c.nRank)) c.nRank = rank;
      found.set(k, c);
    };
    for (const m of mods) {
      const q = (base + m).trim();
      try {
        const r = await fetch('https://suggestqueries.google.com/complete/search?client=firefox&hl=ko&ie=utf-8&oe=utf-8&q=' + encodeURIComponent(q), { headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(8000) });
        ((await r.json())[1] || []).forEach((k, i) => add(k, i + 1, 'g', q));
      } catch (e) { /* 막히면 다음으로 */ }
      try {
        const r = await fetch('https://ac.search.naver.com/nx/ac?q=' + encodeURIComponent(q) + '&con=1&frm=nv&ans=2&r_format=json&r_enc=UTF-8&r_unicode=0&t_koreng=1&run=2&rev=4&q_enc=UTF-8&st=100', { signal: AbortSignal.timeout(8000) });
        (((await r.json()).items || [])[0] || []).forEach((it, i) => add(it && it[0], i + 1, 'n', q));
      } catch (e) { /* 막히면 다음으로 */ }
      await wait(250);
    }
    if (!found.size) throw new Error('NICHE_EMPTY: 자동완성 후보가 없습니다. 주제를 더 넓은 말로 바꿔 보세요.');
    const score = (c) => (c.gRank ? 11 - c.gRank : 0) + (c.nRank ? 11 - c.nRank : 0) + (c.gRank && c.nRank ? 5 : 0);
    const list = Array.from(found.values()).map((c) => ({ ...c, both: !!(c.gRank && c.nRank), score: score(c) })).sort((a, b) => b.score - a.score);
    return { theme: base, candidates: list.slice(0, opt.top || 15) };
  }

  // ---- 시각 도우미 ----
  // 루틴이 글을 예약할 시각. 예약은 오늘 날짜로만 건다(달력 조작 없이 검증된 경로).
  // 캘린더의 시·분을 오늘에 맞추고, 이미 지났거나 40분 안이면 지금부터 40분 뒤(10분 단위 올림)로 민다.
  // 오늘 안에 못 잡으면 null을 돌려준다(그 글은 다음 실행으로 넘긴다).
  function slotFor(when, now = new Date()) {
    const m = WHEN.exec(when);
    const min = new Date(now.getTime() + 40 * 60000);
    let t = m ? new Date(now.getFullYear(), now.getMonth(), now.getDate(), +m[4], +m[5]) : min;
    if (t < min) t = min;
    t.setSeconds(0, 0);
    if (t.getMinutes() % 10) t.setMinutes(t.getMinutes() + (10 - (t.getMinutes() % 10)));
    if (t.toDateString() !== now.toDateString()) return null;
    return t.getFullYear() + '-' + pad(t.getMonth() + 1) + '-' + pad(t.getDate()) + ' ' + pad(t.getHours()) + ':' + pad(t.getMinutes());
  }

  return { SEL, MARK, use, checkLogin, openEditor, fillTitle, setBody, readContent, openPublish, listCategories, setCategory, setTags, setVisibility, setSchedule, readLayer, confirm, hasCaptcha, listReserved, isReserved, probe, toHtml, findPhoto, matchProducts, checkDraft, research, readPost, blueprint, niche, slotFor, today, VIS_NAME };
})();
console.log('TS ready:', Object.keys(TS).join(', '));
