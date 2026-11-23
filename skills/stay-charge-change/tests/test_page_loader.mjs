// C7 올리개의 부과금 묶음 — 가격 도우미의 올리개(`stay_price_loader.js`) 하나가 묶음 셋을 안다. `load('charge')` · `again('charge')` ·
// `status('charge')` 는 네 파일(러너의 도우미 · 부트, 가격 도우미, 부과금 도우미)을 그 차례로 다루고, 인자 없이는 세 파일이다.
// 설치된 것과 다른 stay_charge.js 는 올리지도 다시 실행하지도 않는다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { chargePage, inPage, plain, takeAll, HELPER, BOOT, PAGE, CHARGE, ADDON, LOADER, HOTEL } from './charge_harness.mjs';

const FOUR = [['stay_helper.js', HELPER], ['stay_boot.js', BOOT], ['stay_price.js', PAGE], ['stay_charge.js', CHARGE]];
const KEYS = ['stayPriceHelperSrc', 'stayPriceBootSrc', 'stayPriceSrc', 'stayPriceChargeSrc'];
const OLD_CHARGE = CHARGE.replace('(function () {', '(function () {\n  // 예전 판');
const stored = (page) => KEYS.map((k) => page.w.localStorage.getItem(k));

// 업로드 도구가 하는 일 — 파일 칸에 파일을 놓고 change 를 낸다(jsdom 에서는 files 를 직접 덮는다)
function upload(page, files) {
  const input = page.doc.getElementById('stay_price_bridge');
  Object.defineProperty(input, 'files', { configurable: true, value: files.map(([name, text]) => new page.w.File([text], name, { type: 'text/javascript' })) });
  input.dispatchEvent(new page.w.Event('change', { bubbles: true }));
}

test('C7 · load("charge") 는 네 파일을 하나씩 올려도 이름으로 골라 차례대로 실행하고, stayPrice 키 넷에만 적는다', async () => {
  const page = chargePage({ bare: true });
  plain(page.w.eval(LOADER));
  assert.deepEqual(plain(page.w.stayPriceLoader.bridge('charge')).want, FOUR.map(([name]) => name));
  for (const file of [...FOUR].reverse()) upload(page, [file]);
  const before = Object.keys(page.w.localStorage);
  const r = plain(await page.w.stayPriceLoader.load('charge'));
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.loaded.map((f) => f.name), FOUR.map(([name]) => name));
  assert.equal(r.charge, '0·1·0', '부과금 도우미의 판(점은 · 로)');
  assert.equal(r.addon, undefined, '부가옵션 판은 이 묶음의 상태가 아니다');
  assert.deepEqual(r.stored, KEYS);
  assert.deepEqual(stored(page), FOUR.map(([, text]) => text));
  assert.deepEqual(Object.keys(page.w.localStorage).filter((k) => !before.includes(k)).sort(), [...KEYS].sort());
  assert.ok(JSON.stringify(r).length <= 800);
  const look = plain(await page.w.stayCharge.look());
  assert.equal(look.ok, true, `올린 뒤 작업이 돈다: ${look.error}`);
  const status = plain(page.w.stayPriceLoader.status('charge'));
  assert.deepEqual([status.ok, status.charge, status.stored], [true, '0·1·0', KEYS]);
  page.w.close();
});

test('C7 · status("charge") 는 부과금 도우미가 없으면 charge: null 이고 ok 가 아니다', () => {
  const page = chargePage({ bare: true });
  page.w.eval(LOADER);
  const r = plain(page.w.stayPriceLoader.status('charge'));
  assert.deepEqual([r.ok, r.charge, r.stored], [false, null, []]);
  assert.deepEqual(Object.keys(r).sort(), ['charge', 'helper', 'label', 'ok', 'price', 'stored']);
  page.w.close();
});

test('C7 · 부과금 파일이 빠지면 무엇이 없는지 말하고 그 파일을 올리라고 하며 아무것도 실행하지 않는다 — 부가옵션 파일로는 대신하지 않는다', async () => {
  const page = chargePage({ bare: true });
  page.w.eval(LOADER);
  upload(page, [...FOUR.slice(0, 3), ['stay_addon_price.js', ADDON]]);
  const r = plain(await page.w.stayPriceLoader.load('charge'));
  assert.equal(r.ok, false);
  assert.match(r.error, /^올라온 파일에 없는 것: stay_charge\.js — 그 파일을 「stay price file bridge」 칸에 올린 뒤 다시 부릅니다$/);
  assert.deepEqual(r.want, ['stay_charge.js']);
  assert.equal(page.w.stayRun, undefined);
  assert.deepEqual(stored(page), [null, null, null, null]);
  page.w.close();
});

test('C7 · 설치된 것과 다른 stay_charge.js 는 올리지도(load) 다시 실행하지도(again) 않는다', async () => {
  const page = chargePage({ bare: true });
  page.w.eval(LOADER);
  upload(page, [...FOUR.slice(0, 3), ['stay_charge.js', OLD_CHARGE]]);
  const old = plain(await page.w.stayPriceLoader.load('charge'));
  assert.deepEqual([old.ok, old.wrong], [false, ['stay_charge.js']]);
  assert.match(old.error, /올라온 파일이 설치된 도우미의 것과 다릅니다: stay_charge\.js/);
  assert.equal(page.w.stayRun, undefined, '하나도 실행하지 않았다');
  page.w.close();
  const next = chargePage({ bare: true });
  FOUR.forEach(([, text], i) => next.w.localStorage.setItem(KEYS[i], i === 3 ? OLD_CHARGE : text));
  next.w.eval(LOADER);
  const again = plain(next.w.stayPriceLoader.again('charge'));
  assert.deepEqual([again.ok, again.wrong], [false, ['stay_charge.js']]);
  assert.deepEqual(again.want, ['stay_charge.js']);
  assert.match(again.error, /이 파일을 「stay price file bridge」 칸에 다시 올립니다\(load\) — 나머지는 이 탭에 적어 둔 원본을 씁니다$/);
  assert.equal(next.w.stayCharge, undefined);
  next.w.close();
});

test('C7 · 페이지 이동 뒤 again("charge") 는 적어 둔 네 원본을 다시 실행하고, 인자 없는 load 는 부과금 도우미를 올리지 않는다', async () => {
  const first = chargePage({ bare: true });
  first.w.eval(LOADER);
  upload(first, FOUR);
  assert.equal(plain(await first.w.stayPriceLoader.load('charge')).ok, true);
  const saved = KEYS.map((k) => [k, first.w.localStorage.getItem(k)]);
  first.w.close();
  const next = chargePage({ bare: true });
  saved.forEach(([k, v]) => next.w.localStorage.setItem(k, v));
  next.w.eval(LOADER);
  const again = plain(next.w.stayPriceLoader.again('charge'));
  assert.equal(again.ok, true, again.error);
  const read = plain(await next.w.stayCharge.readCharge(inPage(next.w, { hotel: HOTEL, offer: '601', charge: '701' })));
  assert.equal(takeAll(next.w, read).body.window.form[7][1], '50.00');
  next.w.close();

  const price = chargePage({ bare: true });
  price.w.eval(LOADER);
  upload(price, FOUR);
  const r = plain(await price.w.stayPriceLoader.load());
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.loaded.map((f) => f.name), ['stay_helper.js', 'stay_boot.js', 'stay_price.js']);
  assert.equal(r.charge, undefined);
  assert.equal(price.w.stayCharge, undefined, '부과금 도우미는 올리지 않았다');
  assert.equal(price.w.localStorage.getItem('stayPriceChargeSrc'), null);
  price.w.close();
});

test('C7 · 모르는 묶음 이름은 아무것도 하지 않고 거절하며 묶음마다의 이름을 댄다', async () => {
  const page = chargePage({ bare: true });
  page.w.eval(LOADER);
  for (const call of [(l) => l.bridge('promo'), (l) => l.status('promo'), (l) => l.again('promo')]) {
    const r = plain(call(page.w.stayPriceLoader));
    assert.match(r.error, /^모르는 묶음입니다: promo — 비우면 가격 캘린더, "addon" 이면 부가옵션 가격, "charge" 면 부과금, "promotion" 이면 프로모션 할인, "season" 이면 가격 캘린더의 시즌 창입니다$/);
  }
  assert.match(plain(await page.w.stayPriceLoader.load('promo')).error, /^모르는 묶음입니다: promo/);
  page.w.close();
});
