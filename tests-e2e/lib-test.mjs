import puppeteer from 'puppeteer-core';
import fs from 'fs';
export const SHOTS = '/tmp/mbsite/shots';
export const errors = [];
export let page = null;
export const sleep = ms => new Promise(r => setTimeout(r, ms));
export async function boot(){
  fs.mkdirSync(SHOTS, {recursive: true});
  const browser = await puppeteer.launch({executablePath: '/usr/bin/google-chrome', headless: 'new', args: ['--no-sandbox', '--disable-dev-shm-usage']});
  page = await browser.newPage();
  await page.setViewport({width: 1280, height: 900});
  page.on('pageerror', e => errors.push('pageerror: ' + String(e).slice(0, 300)));
  await page.goto('http://127.0.0.1:8598', {waitUntil: 'domcontentloaded', timeout: 60000});
  await waitForText('Building overview', 90000);
  return browser;
}
export function frames(){ return page.frames().filter(f => f.url().includes('component') && !f.detached); }
export async function evalAny(fn, arg){
  for (const f of frames()){
    try { const r = await f.evaluate(fn, arg); if (r) return r; } catch(e) {}
  }
  return null;
}
export async function waitForText(text, timeout = 60000){
  const t0 = Date.now();
  while (Date.now() - t0 < timeout){
    if (await evalAny(t => { const m = document.getElementById('main'); return m && m.textContent.includes(t); }, text)) return;
    await sleep(400);
  }
  throw new Error('timeout waiting for text: ' + text);
}
export async function click(sel){
  const ok = await evalAny(s => { const el = document.querySelector(s); if (el) { el.click(); return true; } return false; }, sel);
  if (!ok) throw new Error('click target not found: ' + sel);
}
export async function shot(name){ await sleep(250); await page.screenshot({path: `${SHOTS}/${name}.png`}); console.log('shot:', name); }
export async function waitFor(sel, timeout = 30000){
  const t0 = Date.now();
  while (Date.now() - t0 < timeout){
    if (await evalAny(s => !!document.querySelector(s), sel)) return;
    await sleep(300);
  }
  throw new Error('timeout waiting for selector: ' + sel);
}
