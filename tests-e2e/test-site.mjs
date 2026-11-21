import puppeteer from 'puppeteer-core';
import fs from 'fs';

const SHOTS = '/tmp/mbsite/shots';
fs.mkdirSync(SHOTS, {recursive: true});
const errors = [];
const browser = await puppeteer.launch({executablePath: '/usr/bin/google-chrome', headless: 'new', args: ['--no-sandbox', '--disable-dev-shm-usage']});
const page = await browser.newPage();
await page.setViewport({width: 1280, height: 900});
page.on('pageerror', e => errors.push('pageerror: ' + String(e).slice(0, 300)));

async function frame(){
  let f = null;
  for (let i = 0; i < 120 && !f; i++) {
    f = page.frames().find(fr => fr.url().includes('component'));
    if (!f) await new Promise(r => setTimeout(r, 500));
  }
  return f;
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function shot(name){ await sleep(400); await page.screenshot({path: `${SHOTS}/${name}.png`}); console.log('shot:', name); }
async function waitText(fr, text, timeout = 90000){
  await fr.waitForFunction(t => document.getElementById('main') && document.getElementById('main').textContent.includes(t), {timeout}, text);
}

await page.goto('http://127.0.0.1:8598', {waitUntil: 'networkidle2', timeout: 90000});
const fr = await frame();
if (!fr) { console.log('FAIL: no component iframe'); process.exit(1); }
await fr.waitForSelector('[data-s="f00"]', {timeout: 30000});
await waitText(fr, 'Building overview');
await waitText(fr, 'connections', 30000);
await shot('01-overview');

// walk floors
for (const [id, marker] of [['f00','Central Command'],['f01','Market Scanner'],['f03','Risk Manager'],['f04','Paper Executor'],['f05','Monitor'],['f06','Portfolio Manager'],['f07','Final Decision Engine']]){
  await fr.click(`[data-s="${id}"]`);
  await waitText(fr, marker);
  await sleep(1200);
  await shot('02-' + id);
}

// Floor 02 research flow
await fr.click('[data-s="f02"]');
await fr.waitForSelector('#f02-sym', {timeout: 15000});
await fr.type('#f02-sym', 'ALPHA');
await fr.click('[data-act="research"]');
await waitText(fr, 'Agent execution', 180000);
await waitText(fr, 'Balanced', 60000);
await shot('03-f02-analysis');

// tabs
for (const t of ['Fundamental','Technical','Valuation','News','Score detail']){
  await fr.evaluate(tt => { document.querySelector(`[data-tabgroup="f02"][data-tab="${tt}"]`).click(); }, t);
  await sleep(300);
}
await fr.evaluate(() => { document.querySelector('[data-tabgroup="f02"][data-tab="Chart"]').click(); });
await sleep(600);
await shot('04-f02-chart');

// report generation + viewer
await fr.evaluate(() => { document.querySelector('[data-tabgroup="f02"][data-tab="Report"]').click(); });
await sleep(300);
await fr.click('[data-act="make_report"]');
await fr.waitForSelector('iframe.report', {timeout: 60000});
await shot('05-f02-report');
// native download buttons appeared under the app?
const dlCount = await page.evaluate(() => Array.from(document.querySelectorAll('button')).filter(b => b.textContent.toLowerCase().includes('download')).length);
console.log('native download buttons on page:', dlCount);

// Floor 03 assess
await fr.click('[data-s="f03"]');
await waitText(fr, 'Risk Manager');
await fr.waitForSelector('[data-act="assess"]', {timeout: 30000});
await fr.click('[data-act="assess"]');
await waitText(fr, 'Verdict:', 30000);
await shot('06-f03-assess');

// Floor 04 place simulated order
await fr.click('[data-s="f04"]');
await waitText(fr, 'Paper Executor');
await fr.waitForSelector('#po-sym', {timeout: 15000});
await fr.evaluate(() => { document.getElementById('po-sym').value = 'ALPHA'; document.getElementById('po-qty').value = '5'; document.getElementById('po-px').value = '100'; });
await fr.click('[data-act="place_order"]');
await waitText(fr, 'Order processed', 30000);
await shot('07-f04-order');

// Floor 07 decisions (research above persisted one)
await fr.click('[data-s="f07"]');
await waitText(fr, 'Final Decision Engine');
await sleep(1500);
await shot('08-f07');

// mobile pass
await page.setViewport({width: 390, height: 800});
await sleep(800);
await fr.click('[data-s="overview"]').catch(() => {});
await sleep(1200);
await shot('09-mobile-overview');
const mnav = await fr.$('#mnav');
if (mnav) { await fr.select('#mnav', 'f02'); await sleep(1500); await shot('10-mobile-f02'); }

console.log('page errors:', errors.length ? errors : 'none');
await browser.close();
console.log('E2E DONE');
