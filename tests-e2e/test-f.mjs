import puppeteer from 'puppeteer-core';
import fs from 'fs';
const SHOTS = '/tmp/mbsite/shots';
const errors = [];
const sleep = ms => new Promise(r => setTimeout(r, ms));
fs.mkdirSync(SHOTS, {recursive: true});
fs.writeFileSync('/tmp/nse-test.csv', 'symbol,name of company,isin number,series\nAAA,Test Alpha Ltd,INE000A00001,EQ\nBBB,Test Beta Ltd,INE000B00002,EQ\n');

const browser = await puppeteer.launch({executablePath: '/usr/bin/google-chrome', headless: 'new', args: ['--no-sandbox', '--disable-dev-shm-usage']});

function cframe(p){ return p.frames().find(f => f.url().includes('component') && !f.detached); }
async function ev(p, fn, arg){ const f = cframe(p); if (!f) return null; try { return await f.evaluate(fn, arg); } catch(e) { return null; } }
async function waitText(p, text, timeout = 90000){
  const t0 = Date.now();
  while (Date.now() - t0 < timeout){
    if (await ev(p, t => { const m = document.getElementById('main'); return m && m.textContent.includes(t); }, text)) return;
    await sleep(400);
  }
  throw new Error('timeout: ' + text);
}
async function clickIn(p, sel){ const ok = await ev(p, s => { const el = document.querySelector(s); if (el){ el.click(); return true; } return false; }, sel); if (!ok) throw new Error('no click target: ' + sel); }
async function newVisitor(ctx, tag){
  const p = await ctx.newPage();
  await p.setViewport({width: 1280, height: 900});
  p.on('pageerror', e => errors.push(tag + ' pageerror: ' + String(e).slice(0, 200)));
  await p.goto('http://127.0.0.1:8599', {waitUntil: 'domcontentloaded', timeout: 60000});
  await waitText(p, 'Research assistant for NSE/BSE stocks');
  return p;
}
const shot = (p, n) => sleep(300).then(() => p.screenshot({path: `${SHOTS}/${n}.png`})).then(() => console.log('shot:', n));

// ---- A loads and imports its universe
const pageA = await newVisitor(browser.defaultBrowserContext(), 'A');
await clickIn(pageA, '[data-s="f01"]'); await waitText(pageA, 'will be scanned');
let fileInput = null;
for (let i = 0; i < 20 && !fileInput; i++){ fileInput = await cframe(pageA).$('#up-file'); if (!fileInput) await sleep(400); }
await fileInput.uploadFile('/tmp/nse-test.csv');
await clickIn(pageA, '[data-act="upload_csv"]');
await waitText(pageA, 'Imported 2 rows');

// ---- B loads (separate context = separate session)
const ctxB = await browser.createBrowserContext();
const pageB = await newVisitor(ctxB, 'B');

// ---- CONCURRENT research: A on ALPHA, B on GAMMA at the same time
await clickIn(pageA, '[data-s="f02"]'); await waitText(pageA, 'AI Analyst');
await ev(pageA, () => { document.getElementById('f02-sym').value = 'ALPHA'; });
await clickIn(pageB, '[data-s="f02"]'); await waitText(pageB, 'AI Analyst');
await ev(pageB, () => { document.getElementById('f02-sym').value = 'GAMMA'; });
await ev(pageA, () => document.querySelector('[data-act="research"]').click());
await ev(pageB, () => document.querySelector('[data-act="research"]').click());
await Promise.all([waitText(pageA, 'Agent execution', 120000), waitText(pageB, 'Agent execution', 120000)]);
console.log('A result bound to ALPHA:', await ev(pageA, () => document.getElementById('f02-sym').value === 'ALPHA' && !!document.querySelector('table')));
console.log('B result bound to GAMMA:', await ev(pageB, () => document.getElementById('f02-sym').value === 'GAMMA' && !!document.querySelector('table')));
await shot(pageA, 'f01-A-concurrent-research');

// ---- after concurrent load, universes still correctly bound
await clickIn(pageA, '[data-s="f01"]'); await waitText(pageA, 'will be scanned');
console.log('A still 2 NSE:', await ev(pageA, () => document.getElementById('main').textContent.includes('2 NSE')));
await clickIn(pageB, '[data-s="f01"]'); await waitText(pageB, 'will be scanned');
console.log('B still 0 NSE:', await ev(pageB, () => document.getElementById('main').textContent.includes('0 NSE')));

// ---- demo-mode guard: direct NSE download gives a truthful unavailable notice, no probe
await clickIn(pageA, '[data-act="download_nse"]');
await waitText(pageA, 'disabled in this demo');
console.log('A demo NSE-download notice: true');
await shot(pageA, 'f02-A-demo-download-notice');

// ---- missing/invalid session identity is rejected, never falls back to shared state
await ev(pageA, () => { window.S && (S.vid = null); });
await clickIn(pageA, '[data-s="f00"]');
await waitText(pageA, 'workspace session identity missing');
console.log('A missing-vid rejection: true');
await shot(pageA, 'f03-A-missing-vid-rejected');

// ---- recovery: fresh load gets a fresh workspace and the app still works
await pageA.goto('http://127.0.0.1:8599', {waitUntil: 'domcontentloaded', timeout: 60000});
await waitText(pageA, 'Research assistant for NSE/BSE stocks');
console.log('A reload recovers clean:', true);

console.log('page errors:', errors.length ? errors : 'none');
await browser.close();
console.log('E2E-F DONE');
