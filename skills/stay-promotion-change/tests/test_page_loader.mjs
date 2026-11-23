// M7 올리개의 프로모션 묶음 — 가격 도우미의 올리개(`stay_price_loader.js`) 하나가 묶음 넷을 안다. `load('promotion')` · `again('promotion')` ·
// `status('promotion')` 은 네 파일(러너의 도우미 · 부트, 가격 도우미, 프로모션 할인 도우미)을 그 차례로 다룬다. 설치된 것과 다른
// stay_promotion.js 는 올리지도 다시 실행하지도 않는다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { promotionPage, plain, HELPER, BOOT, PAGE, PROMOTION, LOADER } from './promotion_harness.mjs';

const FOUR = [['stay_helper.js', HELPER], ['stay_boot.js', BOOT], ['stay_price.js', PAGE], ['stay_promotion.js', PROMOTION]];
const KEYS = ['stayPriceHelperSrc', 'stayPriceBootSrc', 'stayPriceSrc', 'stayPricePromotionSrc'];
const OLD = PROMOTION.replace('(function () {', '(function () {\n  // 예전 판');

function upload(page, files) {
  const input = page.doc.getElementById('stay_price_bridge');
  Object.defineProperty(input, 'files', { configurable: true, value: files.map(([name, text]) => new page.w.File([text], name, { type: 'text/javascript' })) });
  input.dispatchEvent(new page.w.Event('change', { bubbles: true }));
}

test('M7 · load("promotion") 은 네 파일을 이름으로 골라 차례대로 실행하고 stayPrice 키 넷에만 적으며, 올린 뒤 작업이 돈다', async () => {
  const page = promotionPage({ bare: true });
  const first = plain(page.w.eval(LOADER));
  assert.deepEqual(first.sets.promotion, FOUR.map(([name]) => name));
  assert.deepEqual(plain(page.w.stayPriceLoader.bridge('promotion')).want, FOUR.map(([name]) => name));
  for (const file of [...FOUR].reverse()) upload(page, [file]);
  const before = Object.keys(page.w.localStorage);
  const r = plain(await page.w.stayPriceLoader.load('promotion'));
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.loaded.map((f) => f.name), FOUR.map(([name]) => name));
  assert.equal(r.promotion, '0·1·0');
  assert.deepEqual(Object.keys(page.w.localStorage).filter((k) => !before.includes(k)).sort(), [...KEYS].sort());
  const look = plain(await page.w.stayPromotion.look());
  assert.equal(look.ok, true, look.error);
  page.w.close();
});

test('M7 · 설치된 것과 다른 stay_promotion.js 는 올리지 않고, again("promotion") 은 적어 둔 원본이 없거나 예전 판이면 그 파일만 댄다', async () => {
  const page = promotionPage({ bare: true });
  page.w.eval(LOADER);
  upload(page, [...FOUR.slice(0, 3), ['stay_promotion.js', OLD]]);
  const wrong = plain(await page.w.stayPriceLoader.load('promotion'));
  assert.deepEqual([wrong.ok, wrong.wrong], [false, ['stay_promotion.js']]);
  assert.equal(page.w.stayPromotion, undefined);
  const missing = plain(page.w.stayPriceLoader.again('promotion'));
  assert.deepEqual([missing.ok, missing.want], [false, FOUR.map(([name]) => name)]);
  for (const [i, key] of KEYS.entries()) page.w.localStorage.setItem(key, FOUR[i][1]);
  page.w.localStorage.setItem('stayPricePromotionSrc', OLD);
  const stale = plain(page.w.stayPriceLoader.again('promotion'));
  assert.deepEqual([stale.ok, stale.want, stale.wrong], [false, ['stay_promotion.js'], ['stay_promotion.js']]);
  page.w.localStorage.setItem('stayPricePromotionSrc', PROMOTION);
  const again = plain(page.w.stayPriceLoader.again('promotion'));
  assert.deepEqual([again.ok, again.promotion], [true, '0·1·0']);
  page.w.close();
});
