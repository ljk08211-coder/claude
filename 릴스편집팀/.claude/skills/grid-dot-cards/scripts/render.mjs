#!/usr/bin/env node
// grid-dot-cards 렌더러 — scenes.json → mp4 (무음)
//
//   node render.mjs <scenes.json> <출력.mp4> [--size half|full] [--fps 30] [--duration 초]
//
//   --size half  1080x960  (위아래 분할 화면의 위 절반용, 기본)
//   --size full  1080x1920 (풀 화면)
//
// 필요한 것: node 18+, playwright (프로젝트 폴더에서 `npm i playwright && npx playwright install chromium`),
//           ffmpeg (PATH 또는 프로젝트 bin/ffmpeg)
// playwright 는 "지금 폴더 → 위 폴더들 → 이 스크립트 위 폴더들 → 전역 npm" 순서로 찾는다.
// 크로미움을 못 받았으면 설치된 Google Chrome 으로 자동 대체한다.
import fs from 'fs';
import path from 'path';
import { spawn, execSync } from 'child_process';
import { createRequire } from 'module';
import { fileURLToPath, pathToFileURL } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL = path.resolve(HERE, '..');
const TEMPLATE = path.join(SKILL, 'assets', 'template.html');

const die = m => { console.error(`\n[cards] 멈춤: ${m}\n`); process.exit(1); };
const log = m => console.log(`[cards] ${m}`);

// ── 인자
const argv = process.argv.slice(2);
const opt = (name, def) => { const i = argv.indexOf(name); if (i < 0) return def; const v = argv[i + 1]; argv.splice(i, 2); return v; };
const size = opt('--size', 'half');
const FPS = +opt('--fps', 30);
const durArg = opt('--duration', null);
const [scenesPath, outPath] = argv;
if (!scenesPath || !outPath) die('사용법: node render.mjs <scenes.json> <출력.mp4> [--size half|full]');
if (!['half', 'full'].includes(size)) die('--size 는 half 또는 full');
const [W, H] = size === 'full' ? [1080, 1920] : [1080, 960];

let deck;
try { deck = JSON.parse(fs.readFileSync(scenesPath, 'utf8')); } catch (e) { die(`scenes.json 을 못 읽었어요: ${e.message}`); }
if (Array.isArray(deck)) deck = { scenes: deck };
if (!deck.scenes?.length) die('scenes 가 비어 있어요.');
deck.scenes.forEach((s, i) => { if (!(+s.end > +s.start)) die(`${i + 1}번째 장면의 start/end 가 이상해요: ${s.start}~${s.end}`); });
const total = durArg ? +durArg : Math.max(...deck.scenes.map(s => +s.end));
const N = Math.round(total * FPS);

// ── playwright 찾기 (node_modules 위치에 의존하지 않게)
function upDirs(start) { const out = []; let d = path.resolve(start); for (let i = 0; i < 8; i++) { out.push(d); const p = path.dirname(d); if (p === d) break; d = p; } return out; }
async function loadPlaywright() {
  const bases = [...upDirs(process.cwd()), ...upDirs(HERE)];
  try { bases.push(execSync('npm root -g', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim()); } catch {}
  for (const b of bases) {
    for (const pkg of ['playwright', 'playwright-core']) {
      try {
        const req = createRequire(path.join(b, 'noop.js'));
        const p = req.resolve(pkg);
        const mod = await import(pathToFileURL(p).href);
        return mod.chromium ? mod : mod.default;
      } catch {}
    }
  }
  die('playwright 가 없어요. 프로젝트 폴더에서 아래를 실행하세요:\n  npm i playwright && npx playwright install chromium');
}

// ── ffmpeg 찾기
function findFfmpeg() {
  const c = [];
  if (process.env.REELS_FFMPEG) c.push(process.env.REELS_FFMPEG);
  const isWin = process.platform === 'win32';
  for (const d of [...upDirs(process.cwd()), ...upDirs(HERE)]) c.push(path.join(d, 'bin', isWin ? 'ffmpeg.exe' : 'ffmpeg'));
  // brew ffmpeg-full 은 PATH 에 안 걸릴 수 있어서(keg-only) 직접 찾는다
  try { c.push(path.join(execSync('brew --prefix ffmpeg-full', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim(), 'bin', 'ffmpeg')); } catch {}
  c.push('/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg', '/usr/local/opt/ffmpeg-full/bin/ffmpeg');
  for (const f of c) { try { fs.accessSync(f, fs.constants.X_OK); return f; } catch {} }
  try { return execSync(isWin ? 'where ffmpeg' : 'command -v ffmpeg', isWin ? {} : { shell: '/bin/sh' }).toString().split(/\r?\n/)[0].trim(); } catch {}
  die(isWin ? 'ffmpeg 를 못 찾았어요. PowerShell 에서 `winget install Gyan.FFmpeg` 를 실행하세요.'
            : 'ffmpeg 를 못 찾았어요. `brew install ffmpeg` 또는 프로젝트 bin/ffmpeg 를 준비하세요.');
}

const pw = await loadPlaywright();
const ff = findFfmpeg();
let browser;
const prefer = process.env.CARDS_BROWSER; // 'chrome' 로 주면 시스템 크롬 우선
for (const o of prefer === 'chrome' ? [{ channel: 'chrome' }, {}] : [{}, { channel: 'chrome' }]) {
  try { browser = await pw.chromium.launch(o); log(`브라우저: ${o.channel || 'playwright chromium'}`); break; } catch (e) { /* 다음 후보 */ }
}
if (!browser) die('브라우저를 못 켰어요. `npx playwright install chromium` 을 실행하거나 Google Chrome 을 설치하세요.');

const outAbs = path.resolve(outPath);
fs.mkdirSync(path.dirname(outAbs), { recursive: true });
log(`${deck.scenes.length}장면 · ${total.toFixed(2)}초 · ${W}x${H} · ${N}프레임 → ${outAbs}`);

const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
await page.addInitScript(([d, s]) => { window.__DECK = d; window.__SIZE = s; }, [deck, size]);
await page.goto(pathToFileURL(TEMPLATE).href, { waitUntil: 'load' });
await page.waitForFunction(() => window.__ready === true, null, { timeout: 20000 });

// 확인용 정지 이미지 — 장면마다 한 장 (알약까지 다 나온 시점)
const stem = outAbs.replace(/\.mp4$/i, '');
const checks = deck.scenes.map((s, i) => ({ i, t: Math.min(+s.start + 1.7, (+s.start + +s.end) / 2 + .4, +s.end - .05) }));

const enc = spawn(ff, ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-',
  '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p', '-r', String(FPS), '-movflags', '+faststart', outAbs],
  { stdio: ['pipe', 'inherit', 'inherit'] });
const encDone = new Promise((res, rej) => enc.on('close', c => c === 0 ? res() : rej(new Error('ffmpeg 종료 코드 ' + c))));

const t0 = Date.now();
for (let f = 0; f < N; f++) {
  const t = f / FPS;
  await page.evaluate(x => window.setTime(x), t);
  const buf = await page.screenshot({ type: 'png' });
  if (!enc.stdin.write(buf)) await new Promise(r => enc.stdin.once('drain', r));
  for (const c of checks) if (!c.done && t >= c.t) { fs.writeFileSync(`${stem}_s${String(c.i + 1).padStart(2, '0')}.png`, buf); c.done = true; }
  if (f % (FPS * 5) === 0 && f) log(`  ${f}/${N}`);
}
enc.stdin.end();
await encDone;
await browser.close();
log(`완료 (${((Date.now() - t0) / 1000).toFixed(1)}초): ${outAbs}`);
log(`확인용: ${checks.filter(c => c.done).map(c => path.basename(`${stem}_s${String(c.i + 1).padStart(2, '0')}.png`)).join(', ')}`);
