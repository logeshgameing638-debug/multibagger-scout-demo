import { boot, click, shot, waitForText, evalAny, errors, sleep, page } from './lib-test.mjs';
const browser = await boot();
for (const [id, marker] of [['f00','Central Command'],['f01','Market Scanner'],['f03','Risk Manager'],['f04','Paper Executor'],['f05','Monitor'],['f06','Portfolio Manager'],['f07','Final Decision Engine']]){
  await click(`[data-s="${id}"]`);
  await waitForText(marker);
  await shot('02-' + id);
}
await click('[data-s="f02"]');
await waitForText('AI Analyst');
await evalAny(() => { document.getElementById('f02-sym').value = 'ALPHA'; });
await click('[data-act="research"]');
await waitForText('Agent execution', 120000);
await waitForText('Balanced', 30000);
await shot('03-f02-analysis');
for (const t of ['Fundamental','Technical','Valuation','News','Score detail']){
  await click(`[data-tabgroup="f02"][data-tab="${t}"]`); await sleep(200);
}
await click('[data-tabgroup="f02"][data-tab="Chart"]'); await sleep(500);
await shot('04-f02-chart');
await click('[data-tabgroup="f02"][data-tab="Report"]'); await sleep(300);
await click('[data-act="make_report"]');
await waitForText('Download buttons for the files appear below', 60000);
await shot('05-f02-report');
const dlCount = await page.evaluate(() => Array.from(document.querySelectorAll('button')).filter(b => b.textContent.toLowerCase().includes('download')).length);
console.log('native download buttons on page:', dlCount);
console.log('page errors:', errors.length ? errors : 'none');
await browser.close();
console.log('E2E-A DONE');
