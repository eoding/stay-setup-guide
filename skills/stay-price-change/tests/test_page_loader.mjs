// B10 · B17 · W1 올리개 — 숨은 파일 칸을 만들고, 올라온 세 파일을 이름으로 골라 도우미 → 부트 → 가격 도우미 차례로 실행한다.
// 원본은 stayPrice 로 시작하는 제 키에만 적는다. 러너가 쓰는 키(stayHelperSrc · stayBoot · staySteps · stayRunCursor)는 그대로 둔다.
// 올리개는 설치된 세 파일(디스크의 HELPER · BOOT · PAGE)을 알아 그와 다른 글자는 올리지도 다시 실행하지도 않는다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_loader.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { crc32 } from 'node:zlib';
import { erpPage, inPage, plain, HELPER, BOOT, PAGE, LOADER, RUNNER_STEPS, RUNNER_CURSOR, OFFER, HOTEL } from './page_harness.mjs';

// 플러그인을 새로 깔기 전의 가격 도우미 — 설치된 것과 한 줄 다르다
const OLD_PAGE = PAGE.replace('(function () {', '(function () {\n  // 예전 판');
const crlf = (text) => text.replace(/\n/g, '\r\n');
// 올리개가 설치된 파일을 알아보는 값(바이트 수 · CRC-32 · FNV-1a) — 올리개의 INSTALLED 한 줄을 다른 글자로 바꿔 끼울 때만 쓴다
function identityOf(text) {
  const bytes = Buffer.from(text, 'utf8');
  let fnv = 0x811c9dc5;
  for (const b of bytes) fnv = Math.imul(fnv ^ b, 0x01000193) >>> 0;
  const hex = (n) => n.toString(16).padStart(8, '0');
  return `{ bytes: ${bytes.length}, crc32: '${hex(crc32(bytes))}', fnv: '${hex(fnv)}' }`;
}
const loaderKnowing = (name, text) => LOADER.replace(new RegExp(`'${name.replace('.', '\\.')}': \\{[^}]*\\}`), `'${name}': ${identityOf(text)}`);

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
  assert.deepEqual(started, { ok: true, bridge: 'stay_price_bridge', label: 'stay price file bridge', sets: {
    price: ['stay_helper.js', 'stay_boot.js', 'stay_price.js'],
    addon: ['stay_helper.js', 'stay_boot.js', 'stay_price.js', 'stay_addon_price.js'],
    charge: ['stay_helper.js', 'stay_boot.js', 'stay_price.js', 'stay_charge.js'] } },
    'H4 · 첫 답은 묶음 셋의 파일을 모두 댄다 — 넷이 필요한 도우미에게 셋을 말하지 않는다');
  assert.deepEqual(plain(page.w.stayPriceLoader.bridge('charge')).want, ['stay_helper.js', 'stay_boot.js', 'stay_price.js', 'stay_charge.js'],
    '묶음을 대면 그 묶음의 파일만 댄다');
  const input = page.doc.getElementById('stay_price_bridge');
  assert.ok(input.type === 'file' && input.multiple);
  upload(page, [['stay_price.js', PAGE]]);
  upload(page, [['stay_boot.js', BOOT], ['stay_helper.js', HELPER]]);
  const r = plain(await page.w.stayPriceLoader.load());
  assert.equal(r.ok, true, r.error);
  assert.equal(r.helper, page.w.stayRun.version.split('.').join('·'), '판 번호는 점을 · 로 바꿔 보낸다(도구가 0.15.0 을 가린다)');
  assert.equal(r.price, page.w.stayPrice.version.split('.').join('·'));
  assert.deepEqual(r.loaded.map((f) => f.name), ['stay_helper.js', 'stay_boot.js', 'stay_price.js']);
  assert.deepEqual(r.stored, KEYS);
  assert.ok(!LEAK.test(JSON.stringify(r)), JSON.stringify(r));
  assert.ok(JSON.stringify(r).length <= 800, '상태도 800자 안');
  assert.deepEqual([HELPER, BOOT, PAGE], KEYS.map((k) => page.w.localStorage.getItem(k)));
  assert.deepEqual(Object.keys(page.w.localStorage).filter((k) => !before.includes(k)).sort(), [...KEYS].sort(), '올리개가 새로 쓴 키는 제 키 셋뿐이다(모두 stayPrice 로 시작)');
  runnerKeysUntouched(page);
  const read = plain(await page.w.stayPrice.readPair(inPage(page.w, { hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01', weekdays: ['월', '화', '수', '목', '금', '토', '일'] })));
  assert.equal(read.ok, true, `올린 뒤 작업이 돈다: ${read.error}`);
  page.w.close();
});

test('B18 · 올리개의 파일 칸은 이름(aria-label)으로 찾히고, 보이지 않지만 접근성 트리에 남으며, ERP 의 사진 칸과 헷갈리지 않는다', () => {
  const page = erpPage({ bare: true });
  page.doc.body.insertAdjacentHTML('beforeend', '<input type="file" name="image" accept="image/*" data-stay-field="image">');   // ERP 의 사진 올리기 칸
  const status = plain(page.w.eval(LOADER));
  assert.equal(status.label, 'stay price file bridge', '상태가 찾을 이름을 말한다');
  const named = page.doc.querySelectorAll(`input[type="file"][aria-label="${status.label}"]`);
  assert.equal(named.length, 1);
  assert.equal(named[0].id, 'stay_price_bridge');
  assert.equal(page.doc.querySelectorAll('input[type="file"]').length, 2, '파일 칸이 둘인 화면에서도 이름으로 하나만 걸린다');
  const input = named[0], style = page.w.getComputedStyle(input);
  assert.equal(input.hidden, false, 'hidden 이 아니다(접근성 트리에서 빠지지 않는다)');
  assert.ok(style.display !== 'none' && style.visibility !== 'hidden' && !input.closest('[aria-hidden="true"]'), '접근성 트리에 남는다');
  assert.ok(style.width === '1px' && style.height === '1px' && Number(style.opacity) < 0.05 && style.position === 'fixed', '보이지 않는다');
  assert.notEqual(status.label, 'stay file bridge', '러너의 칸 이름과 다르다');
  input.removeAttribute('aria-label');
  input.hidden = true;
  page.w.eval(LOADER);
  assert.equal(page.doc.querySelectorAll('#stay_price_bridge').length, 1, '다시 실행해도 칸은 하나');
  assert.ok(input.getAttribute('aria-label') === status.label && !input.hidden, '다시 실행하면 이름과 모양을 되잡는다');
  assert.equal(plain(page.w.stayPriceLoader.status()).label, status.label);
  page.w.close();
});

test('B10 · 파일이 모자라거나 하나가 실행 중 멈추면 아무것도 적지 않는다', async () => {
  const page = erpPage({ bare: true });
  runnerLeftovers(page);
  const BROKEN = 'throw new Error("고장 난 부트")';
  page.w.eval(loaderKnowing('stay_boot.js', BROKEN));   // 설치된 부트가 이 탭에서 던진다고 치고
  upload(page, [['stay_helper.js', HELPER], ['stay_price.js', PAGE]]);
  const missing = plain(await page.w.stayPriceLoader.load());
  assert.equal(missing.ok, false);
  assert.match(missing.error, /없는 것: stay_boot\.js/);
  assert.equal(page.w.stayRun, undefined, '하나도 실행하지 않았다');
  assert.deepEqual(KEYS.map((k) => page.w.localStorage.getItem(k)), [null, null, null]);
  upload(page, [['stay_boot.js', BROKEN]]);
  const broken = plain(await page.w.stayPriceLoader.load());
  assert.equal(broken.ok, false);
  assert.match(broken.error, /stay_boot\.js 을 실행하다 멈췄습니다: 고장 난 부트/);
  assert.deepEqual(KEYS.map((k) => page.w.localStorage.getItem(k)), [null, null, null]);
  runnerKeysUntouched(page);
  page.w.close();
});

test('W1 · 올라온 파일이 설치된 것과 다르면(올린 폴더의 예전 복사본) 그 파일을 대며 아무것도 실행하지도 적지도 않는다', async () => {
  const page = erpPage({ bare: true });
  runnerLeftovers(page);
  page.w.eval(LOADER);
  upload(page, [['stay_helper.js', HELPER], ['stay_boot.js', BOOT], ['stay_price.js', OLD_PAGE]]);
  const old = plain(await page.w.stayPriceLoader.load());
  assert.equal(old.ok, false);
  assert.deepEqual(old.wrong, ['stay_price.js'], '다른 것은 가격 도우미 하나뿐이다');
  assert.match(old.error, /^올라온 파일이 설치된 도우미의 것과 다릅니다: stay_price\.js — .*예전 복사본.*다시 올린 뒤 다시 부릅니다$/);
  assert.equal(page.w.stayRun, undefined, '도우미도 실행하지 않았다');
  assert.equal(page.w.stayPrice, undefined);
  assert.deepEqual(KEYS.map((k) => page.w.localStorage.getItem(k)), [null, null, null]);
  upload(page, [['stay_price.js', PAGE]]);
  const fixed = plain(await page.w.stayPriceLoader.load());
  assert.equal(fixed.ok, true, `설치된 파일을 다시 올리면 된다: ${fixed.error}`);
  assert.deepEqual([HELPER, BOOT, PAGE], KEYS.map((k) => page.w.localStorage.getItem(k)));
  runnerKeysUntouched(page);
  page.w.close();
});

test('W1 · 플러그인을 새로 깐 뒤 again() 은 탭에 적어 둔 예전 원본을 되살리지 않고 세 파일을 다시 올리라고 한다', async () => {
  const page = erpPage({ bare: true });
  [['stayPriceHelperSrc', HELPER], ['stayPriceBootSrc', BOOT], ['stayPriceSrc', OLD_PAGE]].forEach(([k, v]) => page.w.localStorage.setItem(k, v));
  runnerLeftovers(page);
  page.w.eval(LOADER);
  const old = plain(page.w.stayPriceLoader.again());
  assert.equal(old.ok, false);
  assert.deepEqual(old.wrong, ['stay_price.js']);
  assert.match(old.error, /^적어 둔 원본이 설치된 도우미와 다릅니다: stay_price\.js — .*예전 판.*세 파일을 다시 올립니다\(load\)$/);
  assert.equal(page.w.stayRun, undefined, '하나도 실행하지 않았다');
  assert.equal(page.w.stayPrice, undefined);
  upload(page, [['stay_helper.js', HELPER], ['stay_boot.js', BOOT], ['stay_price.js', PAGE]]);
  assert.equal(plain(await page.w.stayPriceLoader.load()).ok, true);
  assert.equal(page.w.localStorage.getItem('stayPriceSrc'), PAGE, '다시 올리면 적어 둔 원본도 설치된 것으로 바뀐다');
  runnerKeysUntouched(page);
  page.w.close();
});

test('W1 · 윈도에서 받아 줄 끝이 \\r\\n 인 설치 파일도 설치된 것으로 알아본다', async () => {
  const first = erpPage({ bare: true });
  first.w.eval(LOADER);
  upload(first, [['stay_helper.js', crlf(HELPER)], ['stay_boot.js', crlf(BOOT)], ['stay_price.js', crlf(PAGE)]]);
  const loaded = plain(await first.w.stayPriceLoader.load());
  assert.equal(loaded.ok, true, loaded.error);
  const stored = KEYS.map((k) => [k, first.w.localStorage.getItem(k)]);
  first.w.close();
  const next = erpPage({ bare: true });
  stored.forEach(([k, v]) => next.w.localStorage.setItem(k, v));
  next.w.eval(LOADER);
  assert.equal(plain(next.w.stayPriceLoader.again()).ok, true);
  next.w.close();
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
  assert.equal(next.w.stayRun.version.split('.').join('·'), again.helper, 'again() 은 제 키의 원본을 실행했다(러너 키의 예전 원본이 아니다)');
  runnerKeysUntouched(next);
  next.w.close();

  const empty = erpPage({ bare: true });
  empty.w.eval(LOADER);
  assert.match(plain(empty.w.stayPriceLoader.again()).error, /적어 둔 원본이 없습니다/);
  empty.w.close();
});
