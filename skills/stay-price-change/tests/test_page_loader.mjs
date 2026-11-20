// B10 올리개 — 숨은 파일 칸을 만들고, 올라온 세 파일을 이름으로 골라 도우미 → 부트 → 가격 도우미 차례로 실행한다.
// 원본은 러너의 두 키와 stayPriceSrc 에만 적고, 러너의 staySteps·stayRunCursor 는 그대로 둔다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_loader.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { erpPage, inPage, plain, HELPER, BOOT, PAGE, LOADER, RUNNER_STEPS, RUNNER_CURSOR, OFFER } from './page_harness.mjs';

// 업로드 도구가 하는 일 — 파일 칸에 파일을 놓고 change 를 낸다(jsdom 에서는 files 를 직접 덮는다)
function upload(page, files) {
  const input = page.doc.getElementById('stay_price_bridge');
  Object.defineProperty(input, 'files', { configurable: true, value: files.map(([name, text]) => new page.w.File([text], name, { type: 'text/javascript' })) });
  input.dispatchEvent(new page.w.Event('change', { bubbles: true }));
}
const LEAK = /https?:|\/stay\/|\?|erp\.example/;

test('B10 · 올리개를 실행하면 숨은 파일 칸이 생기고, 세 파일을 하나씩 올려도 이름으로 골라 차례대로 실행한다', async () => {
  const page = erpPage({ bare: true });
  const started = plain(page.w.eval(LOADER));
  assert.deepEqual(started, { ok: true, bridge: 'stay_price_bridge', want: ['stay_helper.js', 'stay_boot.js', 'stay_price.js'] });
  const input = page.doc.getElementById('stay_price_bridge');
  assert.ok(input.type === 'file' && input.multiple && input.hidden);
  upload(page, [['stay_price.min.js', PAGE]]);
  upload(page, [['stay_boot.js', BOOT], ['stay_helper.js', HELPER]]);
  const r = plain(await page.w.stayPriceLoader.load());
  assert.equal(r.ok, true, r.error);
  assert.equal(r.helper, page.w.stayRun.version);
  assert.equal(r.price, page.w.stayPrice.version);
  assert.deepEqual(r.loaded.map((f) => f.name), ['stay_helper.js', 'stay_boot.js', 'stay_price.js']);
  assert.deepEqual(r.stored, ['stayHelperSrc', 'stayBoot', 'stayPriceSrc']);
  assert.ok(!LEAK.test(JSON.stringify(r)), JSON.stringify(r));
  assert.equal(page.w.localStorage.getItem('stayPriceSrc'), PAGE);
  assert.equal(page.w.localStorage.getItem('staySteps'), RUNNER_STEPS, '러너 계획을 그대로 둔다');
  assert.equal(page.w.localStorage.getItem('stayRunCursor'), RUNNER_CURSOR);
  const read = plain(await page.w.stayPrice.readPair(inPage(page.w, { offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01', weekdays: ['월', '화', '수', '목', '금', '토', '일'] })));
  assert.equal(read.ok, true, `올린 뒤 작업이 돈다: ${read.error}`);
  page.w.close();
});

test('B10 · 파일이 모자라거나 하나가 실행 중 멈추면 아무것도 적지 않는다', async () => {
  const page = erpPage({ bare: true });
  page.w.eval(LOADER);
  upload(page, [['stay_helper.js', HELPER], ['stay_price.js', PAGE]]);
  const missing = plain(await page.w.stayPriceLoader.load());
  assert.equal(missing.ok, false);
  assert.match(missing.error, /없는 것: stay_boot\.js/);
  assert.equal(page.w.stayRun, undefined, '하나도 실행하지 않았다');
  assert.equal(page.w.localStorage.getItem('stayHelperSrc'), null);
  upload(page, [['stay_boot.js', 'throw new Error("고장 난 부트")']]);
  const broken = plain(await page.w.stayPriceLoader.load());
  assert.equal(broken.ok, false);
  assert.match(broken.error, /stay_boot\.js 을 실행하다 멈췄습니다: 고장 난 부트/);
  assert.deepEqual(['stayHelperSrc', 'stayBoot', 'stayPriceSrc'].map((k) => page.w.localStorage.getItem(k)), [null, null, null]);
  page.w.close();
});

test('B10 · 전체 페이지 이동 뒤에는 올리개를 다시 실행하고 again() 으로 적어 둔 원본을 다시 올린다', async () => {
  const first = erpPage({ bare: true });
  first.w.eval(LOADER);
  upload(first, [['stay_helper.js', HELPER], ['stay_boot.js', BOOT], ['stay_price.js', PAGE]]);
  assert.equal(plain(await first.w.stayPriceLoader.load()).ok, true);
  const stored = ['stayHelperSrc', 'stayBoot', 'stayPriceSrc'].map((k) => [k, first.w.localStorage.getItem(k)]);
  first.w.close();

  const next = erpPage({ bare: true });   // 새 페이지 — 같은 출처의 localStorage 는 남는다
  stored.forEach(([k, v]) => next.w.localStorage.setItem(k, v));
  assert.equal(plain(next.w.eval(LOADER)).ok, true);
  const again = plain(next.w.stayPriceLoader.again());
  assert.equal(again.ok, true, again.error);
  assert.equal(typeof next.w.stayPrice.readPair, 'function');
  assert.equal(next.w.localStorage.getItem('staySteps'), RUNNER_STEPS);
  next.w.close();

  const empty = erpPage({ bare: true });
  empty.w.eval(LOADER);
  assert.match(plain(empty.w.stayPriceLoader.again()).error, /적어 둔 원본이 없습니다/);
  empty.w.close();
});
