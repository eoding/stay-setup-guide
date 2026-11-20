// B10 · B17 올리개 — 숨은 파일 칸을 만들고, 올라온 세 파일을 이름으로 골라 도우미 → 부트 → 가격 도우미 차례로 실행한다.
// 원본은 stayPrice 로 시작하는 제 키에만 적는다. 러너가 쓰는 키(stayHelperSrc · stayBoot · staySteps · stayRunCursor)는 그대로 둔다.
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
const KEYS = ['stayPriceHelperSrc', 'stayPriceBootSrc', 'stayPriceSrc'];
// 예전 러너 실행이 남긴 원본(다른 판) — 올리개는 이 둘을 건드리지 않는다
const OLD_HELPER = '/* 예전 러너 실행의 도우미 원본(축소판) */', OLD_BOOT = '/* 예전 러너 실행의 부트 원본(축소판) */';
function runnerLeftovers(page) {
  page.w.localStorage.setItem('stayHelperSrc', OLD_HELPER);
  page.w.localStorage.setItem('stayBoot', OLD_BOOT);
}
function runnerKeysUntouched(page) {
  assert.equal(page.w.localStorage.getItem('stayHelperSrc'), OLD_HELPER, 'stayHelperSrc 를 덮지 않았다');
  assert.equal(page.w.localStorage.getItem('stayBoot'), OLD_BOOT, 'stayBoot 를 덮지 않았다');
  assert.equal(page.w.localStorage.getItem('staySteps'), RUNNER_STEPS, '러너 계획을 그대로 둔다');
  assert.equal(page.w.localStorage.getItem('stayRunCursor'), RUNNER_CURSOR);
}

test('B10 · 올리개를 실행하면 숨은 파일 칸이 생기고, 세 파일을 하나씩 올려도 이름으로 골라 차례대로 실행한다', async () => {
  const page = erpPage({ bare: true });
  runnerLeftovers(page);
  const before = Object.keys(page.w.localStorage);
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
  assert.deepEqual(r.stored, KEYS);
  assert.ok(!LEAK.test(JSON.stringify(r)), JSON.stringify(r));
  assert.ok(JSON.stringify(r).length <= 800, '상태도 800자 안');
  assert.deepEqual([HELPER, BOOT, PAGE], KEYS.map((k) => page.w.localStorage.getItem(k)));
  assert.deepEqual(Object.keys(page.w.localStorage).filter((k) => !before.includes(k)).sort(), [...KEYS].sort(), '올리개가 새로 쓴 키는 제 키 셋뿐이다(모두 stayPrice 로 시작)');
  runnerKeysUntouched(page);
  const read = plain(await page.w.stayPrice.readPair(inPage(page.w, { offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01', weekdays: ['월', '화', '수', '목', '금', '토', '일'] })));
  assert.equal(read.ok, true, `올린 뒤 작업이 돈다: ${read.error}`);
  page.w.close();
});

test('B10 · 파일이 모자라거나 하나가 실행 중 멈추면 아무것도 적지 않는다', async () => {
  const page = erpPage({ bare: true });
  runnerLeftovers(page);
  page.w.eval(LOADER);
  upload(page, [['stay_helper.js', HELPER], ['stay_price.js', PAGE]]);
  const missing = plain(await page.w.stayPriceLoader.load());
  assert.equal(missing.ok, false);
  assert.match(missing.error, /없는 것: stay_boot\.js/);
  assert.equal(page.w.stayRun, undefined, '하나도 실행하지 않았다');
  assert.deepEqual(KEYS.map((k) => page.w.localStorage.getItem(k)), [null, null, null]);
  upload(page, [['stay_boot.js', 'throw new Error("고장 난 부트")']]);
  const broken = plain(await page.w.stayPriceLoader.load());
  assert.equal(broken.ok, false);
  assert.match(broken.error, /stay_boot\.js 을 실행하다 멈췄습니다: 고장 난 부트/);
  assert.deepEqual(KEYS.map((k) => page.w.localStorage.getItem(k)), [null, null, null]);
  runnerKeysUntouched(page);
  page.w.close();
});

test('B10 · 전체 페이지 이동 뒤에는 올리개를 다시 실행하고 again() 으로 적어 둔 원본을 다시 올린다', async () => {
  const first = erpPage({ bare: true });
  first.w.eval(LOADER);
  upload(first, [['stay_helper.js', HELPER], ['stay_boot.js', BOOT], ['stay_price.js', PAGE]]);
  assert.equal(plain(await first.w.stayPriceLoader.load()).ok, true);
  const stored = KEYS.map((k) => [k, first.w.localStorage.getItem(k)]);
  first.w.close();

  const next = erpPage({ bare: true });   // 새 페이지 — 같은 출처의 localStorage 는 남는다
  stored.forEach(([k, v]) => next.w.localStorage.setItem(k, v));
  runnerLeftovers(next);
  assert.equal(plain(next.w.eval(LOADER)).ok, true);
  const again = plain(next.w.stayPriceLoader.again());
  assert.equal(again.ok, true, again.error);
  assert.equal(typeof next.w.stayPrice.readPair, 'function');
  assert.equal(next.w.stayRun.version, again.helper, 'again() 은 제 키의 원본을 실행했다(러너 키의 예전 원본이 아니다)');
  runnerKeysUntouched(next);
  next.w.close();

  const empty = erpPage({ bare: true });
  empty.w.eval(LOADER);
  assert.match(plain(empty.w.stayPriceLoader.again()).error, /적어 둔 원본이 없습니다/);
  empty.w.close();
});
