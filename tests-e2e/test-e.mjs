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

// ---- visitor A
const pageA = await newVisitor(browser.defaultBrowserContext(), 'A');
console.log('A overview workspace note:', await ev(pageA, () => document.getElementById('main').textContent.includes('Workspace: private to this browser session')));
await shot(pageA, 'e01-A-overview');
await clickIn(pageA, '[data-s="f01"]'); await waitText(pageA, 'will be scanned');
let fileInput = null;
for (let i = 0; i < 20 && !fileInput; i++){ fileInput = await cframe(pageA).$('#up-file'); if (!fileInput) await sleep(400); }
if (!fileInput) throw new Error('up-file input never appeared');
await fileInput.uploadFile('/tmp/nse-test.csv');
await clickIn(pageA, '[data-act="upload_csv"]');
await waitText(pageA, 'Imported 2 rows');
console.log('A f01 counts visible:', await ev(pageA, () => { const m = document.getElementById('main').textContent; return m.includes('2 NSE'); }));
await shot(pageA, 'e02-A-f01-loaded');
await clickIn(pageA, '[data-s="f02"]'); await waitText(pageA, 'AI Analyst');
await ev(pageA, () => { document.getElementById('f02-sym').value = 'ALPHA'; });
await clickIn(pageA, '[data-act="research"]');
await waitText(pageA, 'Agent execution', 120000);
await shot(pageA, 'e03-A-research');
await clickIn(pageA, '[data-s="f00"]'); await waitText(pageA, 'Database health');
console.log('A f00 workspace banner:', await ev(pageA, () => document.getElementById('main').textContent.includes('Private session workspace')));
console.log('A f00 host-log block hidden:', await ev(pageA, () => !Array.from(document.querySelectorAll('summary')).some(s => s.textContent.includes('Application log'))));
await clickIn(pageA, '[data-act="backup_db"]');
await waitText(pageA, 'workspace backup');
await sleep(1500); // streamlit rerun renders the native download button
console.log('A native backup button:', await pageA.evaluate(() => Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('workspace backup'))));
await shot(pageA, 'e04-A-f00-backup');

// ---- visitor B (separate browser context = separate Streamlit session)
const ctxB = await browser.createBrowserContext();
const pageB = await newVisitor(ctxB, 'B');
await clickIn(pageB, '[data-s="f01"]'); await waitText(pageB, 'will be scanned');
console.log('B universe empty:', await ev(pageB, () => { const m = document.getElementById('main').textContent; return m.includes('0 NSE') && m.includes('universe is empty'); }));
await shot(pageB, 'e05-B-f01-empty');
await clickIn(pageB, '[data-s="f00"]'); await waitText(pageB, 'Database health');
console.log('B f00 workspace banner:', await ev(pageB, () => document.getElementById('main').textContent.includes('Private session workspace')));
console.log('B f00 host-log block hidden:', await ev(pageB, () => !Array.from(document.querySelectorAll('summary')).some(s => s.textContent.includes('Application log'))));
await shot(pageB, 'e06-B-f00');
await clickIn(pageB, '[data-act="backup_db"]');
await waitText(pageB, 'workspace backup');
await sleep(1500);
console.log('B native backup button:', await pageB.evaluate(() => Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('workspace backup'))));

console.log('page errors:', errors.length ? errors : 'none');
await browser.close();
console.log('E2E-E DONE');
