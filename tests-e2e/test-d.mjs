import { boot, click, waitForText, waitFor, evalAny, errors, sleep, page } from './lib-test.mjs';
import fs from 'fs';
const DL = '/tmp/mbsite/dl';
fs.rmSync(DL, {recursive: true, force: true});
fs.mkdirSync(DL, {recursive: true});
const browser = await boot();
const cdp = await page.createCDPSession();
await cdp.send('Browser.setDownloadBehavior', {behavior: 'allow', downloadPath: DL});

// build an analysis so report buttons exist
await click('[data-s="f02"]');
await waitFor('#f02-sym');
await evalAny(() => { document.getElementById('f02-sym').value = 'ALPHA'; });
await click('[data-act="research"]');
await waitForText('Agent execution', 120000);
await click('[data-tabgroup="f02"][data-tab="Report"]');
await sleep(300);
await click('[data-act="make_report"]');
await waitForText('Download buttons for the files appear below', 60000);

// click each native download button in the OUTER page and collect files
const labels = await page.evaluate(() => Array.from(document.querySelectorAll('button')).filter(b => b.textContent.toLowerCase().includes('download')).map(b => b.textContent.trim()));
console.log('download buttons:', JSON.stringify(labels));
for (let i = 0; i < labels.length; i++){
  await page.evaluate(idx => { Array.from(document.querySelectorAll('button')).filter(b => b.textContent.toLowerCase().includes('download'))[idx].click(); }, i);
  await sleep(1800);
}
await sleep(2500);
const files = fs.readdirSync(DL);
console.log('downloaded files:', JSON.stringify(files));
for (const f of files){
  const txt = fs.readFileSync(`${DL}/${f}`, 'utf8');
  const head = txt.slice(0, 80).replace(/\n/g, ' ');
  let ok = false;
  if (f.endsWith('.html')) ok = txt.includes('<h1>') && txt.includes('Multibagger Scout AI');
  if (f.endsWith('.json')) { try { const j = JSON.parse(txt); ok = j.symbol === 'ALPHA' && !!j.agents; } catch(e) {} }
  if (f.endsWith('.csv')) ok = txt.split('\n')[0].trim() === 'path,value';
  console.log(f, '->', ok ? 'CONTENT OK' : 'CONTENT BAD', '|', head);
}

// mobile header + svg label check
await page.setViewport({width: 390, height: 800});
await sleep(800);
await click('[data-s="overview"]');
await sleep(1200);
await page.screenshot({path: '/tmp/mbsite/shots/15-mobile-fixed.png'});
await page.setViewport({width: 1280, height: 1400});
await sleep(800);
await page.screenshot({path: '/tmp/mbsite/shots/16-overview-svg.png'});
console.log('page errors:', errors.length ? errors : 'none');
await browser.close();
console.log('E2E-D DONE');
