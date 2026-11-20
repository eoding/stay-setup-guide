// A6 올리개의 부가옵션 묶음 — 가격 도우미의 올리개(`stay_price_loader.js`) 하나가 묶음 둘을 안다. `load('addon')` · `again('addon')` ·
// `status('addon')` 는 네 파일(러너의 도우미 · 부트, 가격 도우미, 부가옵션 가격 도우미)을 그 차례로 다루고, 인자 없이는 지금처럼 세 파일이다.
// 설치된 것과 다른 stay_addon_price.js 는 올리지도 다시 실행하지도 않는다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { addonPage, inPage, plain, takeAll, HELPER, BOOT, PAGE, ADDON, LOADER, HOTEL } from './addon_harness.mjs';

const FOUR = [['stay_helper.js', HELPER], ['stay_boot.js', BOOT], ['stay_price.js', PAGE], ['stay_addon_price.js', ADDON]];
const KEYS = ['stayPriceHelperSrc', 'stayPriceBootSrc', 'stayPriceSrc', 'stayPriceAddonSrc'];
const OLD_ADDON = ADDON.replace('(function () {', '(function () {\n  // 예전 판');
const stored = (page) => KEYS.map((k) => page.w.localStorage.getItem(k));

// 업로드 도구가 하는 일 — 파일 칸에 파일을 놓고 change 를 낸다(jsdom 에서는 files 를 직접 덮는다)
function upload(page, files) {
  const input = page.doc.getElementById('stay_price_bridge');
  Object.defineProperty(input, 'files', { configurable: true, value: files.map(([name, text]) => new page.w.File([text], name, { type: 'text/javascript' })) });
  input.dispatchEvent(new page.w.Event('change', { bubbles: true }));
}

test('A6 · load("addon") 은 네 파일을 하나씩 올려도 이름으로 골라 차례대로 실행하고, stayPrice 키 넷에만 적는다', async () => {
  const page = addonPage({ bare: true });
  plain(page.w.eval(LOADER));
  assert.deepEqual(plain(page.w.stayPriceLoader.bridge('addon')).want, FOUR.map(([name]) => name));
  for (const file of [...FOUR].reverse()) upload(page, [file]);
  const before = Object.keys(page.w.localStorage);
  const r = plain(await page.w.stayPriceLoader.load('addon'));
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.loaded.map((f) => f.name), FOUR.map(([name]) => name));
  assert.equal(r.addon, page.w.stayAddonPrice.version.split('.').join('·'));
  assert.deepEqual(r.stored, KEYS);
  assert.deepEqual(stored(page), FOUR.map(([, text]) => text));
  assert.deepEqual(Object.keys(page.w.localStorage).filter((k) => !before.includes(k)).sort(), [...KEYS].sort());
  assert.ok(JSON.stringify(r).length <= 800);
  const look = plain(await page.w.stayAddonPrice.look());
  assert.equal(look.ok, true, `올린 뒤 작업이 돈다: ${look.error}`);
  assert.deepEqual(plain(page.w.stayPriceLoader.status('addon')).stored, KEYS);
  page.w.close();
});

test('A6 · 부가옵션 파일이 빠지면 무엇이 없는지 말하고 네 파일을 올리라고 하며 아무것도 실행하지 않는다', async () => {
  const page = addonPage({ bare: true });
  page.w.eval(LOADER);
  upload(page, FOUR.slice(0, 3));
  const r = plain(await page.w.stayPriceLoader.load('addon'));
  assert.equal(r.ok, false);
  assert.match(r.error, /^올라온 파일에 없는 것: stay_addon_price\.js — 네 파일을 「stay price file bridge」 칸에 올린 뒤 다시 부릅니다$/);
  assert.equal(page.w.stayRun, undefined);
  assert.deepEqual(stored(page), [null, null, null, null]);
  page.w.close();
});

test('A6 · 설치된 것과 다른 stay_addon_price.js 는 올리지도(load) 다시 실행하지도(again) 않는다', async () => {
  const page = addonPage({ bare: true });
  page.w.eval(LOADER);
  upload(page, [...FOUR.slice(0, 3), ['stay_addon_price.js', OLD_ADDON]]);
  const old = plain(await page.w.stayPriceLoader.load('addon'));
  assert.deepEqual([old.ok, old.wrong], [false, ['stay_addon_price.js']]);
  assert.equal(page.w.stayRun, undefined, '하나도 실행하지 않았다');
  page.w.close();
  const next = addonPage({ bare: true });
  FOUR.forEach(([, text], i) => next.w.localStorage.setItem(KEYS[i], i === 3 ? OLD_ADDON : text));
  next.w.eval(LOADER);
  const again = plain(next.w.stayPriceLoader.again('addon'));
  assert.deepEqual([again.ok, again.wrong], [false, ['stay_addon_price.js']]);
  assert.deepEqual(again.want, FOUR.map(([name]) => name), '거절한 답이 올릴 네 파일을 댄다');
  assert.match(again.error, /네 파일을 다시 올립니다\(load\)$/);
  assert.equal(next.w.stayAddonPrice, undefined);
  next.w.close();
});

test('A6 · 페이지 이동 뒤 again("addon") 은 적어 둔 네 원본을 다시 실행하고, 인자 없는 load · status 는 지금처럼 세 파일만 다룬다', async () => {
  const first = addonPage({ bare: true });
  first.w.eval(LOADER);
  upload(first, FOUR);
  assert.equal(plain(await first.w.stayPriceLoader.load('addon')).ok, true);
  const saved = KEYS.map((k) => [k, first.w.localStorage.getItem(k)]);
  first.w.close();
  const next = addonPage({ bare: true });
  saved.forEach(([k, v]) => next.w.localStorage.setItem(k, v));
  next.w.eval(LOADER);
  const again = plain(next.w.stayPriceLoader.again('addon'));
  assert.equal(again.ok, true, again.error);
  const read = plain(await next.w.stayAddonPrice.readLine(inPage(next.w, { hotel: HOTEL, addon: '201', line: '301' })));
  assert.equal(takeAll(next.w, read).body.window.form[1][1], '20.00');
  next.w.close();

  const price = addonPage({ bare: true });
  price.w.eval(LOADER);
  upload(price, FOUR);
  const r = plain(await price.w.stayPriceLoader.load());
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.loaded.map((f) => f.name), ['stay_helper.js', 'stay_boot.js', 'stay_price.js']);
  assert.deepEqual(r.stored, KEYS.slice(0, 3));
  assert.equal(r.addon, undefined);
  assert.equal(price.w.stayAddonPrice, undefined, '부가옵션 도우미는 올리지 않았다');
  assert.equal(price.w.localStorage.getItem('stayPriceAddonSrc'), null);
  assert.deepEqual(Object.keys(plain(price.w.stayPriceLoader.status())).sort(), ['helper', 'label', 'ok', 'price', 'stored']);
  price.w.close();
});

test('F8 · 올리개 전체 뒤에 again("addon") 을 붙여 한 번에 실행하면, 첫 답이 부가옵션 묶음의 네 파일을 댄다(가격 캘린더의 세 파일이 아니다)', async () => {
  const page = addonPage({ bare: true });
  const first = plain(page.w.eval(LOADER + "\nstayPriceLoader.again('addon')"));
  assert.equal(first.ok, false);
  assert.deepEqual(first.want, FOUR.map(([name]) => name));
  assert.match(first.error, /^적어 둔 원본이 없습니다: .* — 네 파일을 다시 올립니다\(load\)$/);
  upload(page, FOUR);
  assert.equal(plain(await page.w.stayPriceLoader.load('addon')).ok, true);
  const saved = KEYS.map((k) => [k, page.w.localStorage.getItem(k)]);
  page.w.close();
  const next = addonPage({ bare: true });
  saved.forEach(([k, v]) => next.w.localStorage.setItem(k, v));
  const again = plain(next.w.eval(LOADER + "\nstayPriceLoader.again('addon')"));
  assert.equal(again.ok, true, again.error);
  assert.deepEqual(again.loaded.map((f) => f.name), FOUR.map(([name]) => name));
  next.w.close();
});

test('A6 · 모르는 묶음 이름은 아무것도 하지 않고 거절한다', async () => {
  const page = addonPage({ bare: true });
  page.w.eval(LOADER);
  for (const call of [(l) => l.bridge('promo'), (l) => l.status('promo'), (l) => l.again('promo')]) {
    assert.match(plain(call(page.w.stayPriceLoader)).error, /^모르는 묶음입니다: promo/);
  }
  assert.match(plain(await page.w.stayPriceLoader.load('promo')).error, /^모르는 묶음입니다: promo/);
  page.w.close();
});
