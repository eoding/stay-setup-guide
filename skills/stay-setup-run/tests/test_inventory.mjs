import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const require = createRequire(import.meta.url);
const { JSDOM } = require('jsdom');
const here = dirname(fileURLToPath(import.meta.url));
const script = readFileSync(join(here, '../scripts/stay_boot.js'), 'utf8');

function screen(checked = false) {
  const dom = new JSDOM(`<div id="stay_inventory"><table><tr>
    <td><button role="switch" aria-checked="${checked}" aria-label="가을 계약 · 디럭스 — 수량으로 판매">수량으로 판매</button></td>
    <td><button hx-get="/stay/123/inventory/links/101/days/2026-10-08/?month=2026-10">10</button></td>
  </tr></table></div>`, {url:'https://example.com/stay/123/',runScripts:'outside-only'});
  const w = dom.window;
  w.document.querySelector('[role=switch]').addEventListener('click', e => {
    w.clicks = (w.clicks || 0) + 1;
    e.target.setAttribute('aria-checked', 'true');
  });
  w.stayRun = {tab: async () => ({status:'ok'}),
    waitFor: async fn => !!fn(),
    submit: async (_text, opt) => {
      const button = opt.within.querySelector('[role=switch]');
      button.click();
      return {status:'ok',errors:[]};
    }};
  w.eval(script);
  return w;
}

const on = {no:1,kind:'재고 수량 판매 켜기',title:'재고 수량 판매 켜기',head:{tab:'재고',card:'가을 계약 · 디럭스'},fields:[]};
const w = screen();
assert.equal(typeof w.runInventoryStep, 'function', 'inventory execution is missing');
let r = await w.runInventoryStep(on, {dry:true});
assert.equal(w.clicks, undefined, 'dry mode must not enable quantity selling');
assert.equal(r.submitted, false);
r = await w.runInventoryStep(on, {});
assert.equal(r.submitted, true);
assert.equal(w.clicks, 1);
r = await w.runInventoryStep(on, {});
assert.equal(r.skipped, true);
assert.equal(w.clicks, 1, 'an already-enabled switch must never be toggled off');
const wrong = {...on,head:{tab:'재고',card:'겨울 계약 · 디럭스'}};
r = await w.runInventoryStep(wrong, {});
assert.equal(r.submitted, false);
assert.match(r.error, /찾/);
assert.equal(w.clicks, 1);
w.close();
console.log('inventory browser tests passed');
