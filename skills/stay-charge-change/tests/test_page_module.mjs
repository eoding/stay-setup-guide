// C7 페이지 모듈 — 가격 도우미(`stay_price.js`)의 stayPageKit 위에 올라, 제 클릭이 없고, 작업 하나는 호출 하나, 답은 800자 안의
// 평범한 객체, 세 도우미를 통틀어 작업은 한 번에 하나, localStorage 는 가격 도우미의 `stayPriceLast` 하나만.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { chargePage, inPage, plain, charsOf, takeAll, CHARGE, DB, HOTEL, RUNNER_STEPS, RUNNER_CURSOR } from './charge_harness.mjs';

const CODE = CHARGE.split('\n').filter((line) => !/^\s*(\/\/|\/\*|\*)/.test(line));   // 주석 줄은 뺀다
const READ = { hotel: HOTEL, offer: '601', charge: '701' };

test('C7 · stay_charge.js 에는 제 클릭 · 폼 제출 · 꾸민 마우스 사건 · 사건 쏘기 · localStorage 가 없다 — 누르기는 stayPageKit.press 뿐이다', () => {
  for (const [what, pattern] of [['.click(', /\.click\s*\(/], ['.submit(', /\.submit\s*\(/], ['requestSubmit', /requestSubmit/],
    ['MouseEvent', /MouseEvent|PointerEvent/], ['dispatchEvent', /dispatchEvent/], ['localStorage', /localStorage/]]) {
    assert.ok(!CODE.some((line) => pattern.test(line)), `${what} 이 없다`);
  }
  assert.ok(CODE.some((line) => /K\.press\(/.test(line)), '누르기는 kit 의 press 로 한다');
  assert.ok(CODE.some((line) => /K\.fill\(/.test(line)) && CODE.some((line) => /K\.saveOnce\(/.test(line)), '치기 · 저장은 kit 의 fill · saveOnce 로 한다');
});

test('C7 · window.stayCharge 는 약속한 이름만 내고(standDown · standUp 은 없다), 올리면 판 번호를 답한다', () => {
  const page = chargePage();
  assert.deepEqual(Object.keys(page.w.stayCharge).sort(),
    ['ALLOW', 'CONTROLS', 'NEVER', 'applyCharge', 'guard', 'idle', 'last', 'look', 'readCharge', 'take', 'version'].sort());
  assert.equal(page.w.stayCharge.version, '0.1.0');
  assert.deepEqual(plain(page.w.eval(CHARGE)), { ok: true, version: '0·1·0' }, '판 번호는 점을 · 로 바꿔 답한다');
  const kit = page.w.stayPageKit;
  for (const name of ['sent', 'differs', 'pairs', 'errors', 'fill', 'saveOnce']) assert.equal(typeof kit[name], 'function', name);
  page.w.close();
});

test('C7 · 가격 도우미(stay_price.js) 없이 올리면 올라가지 않고 무엇이 먼저인지 말한다', () => {
  assert.throws(() => chargePage({ withPage: false }), /stay_price\.js/);
});

test('C7 · 러너의 도우미 · 부트 없이 부르면 무엇이 없는지 말하고 아무것도 누르지 않는다', async () => {
  const page = chargePage({ withScripts: false });
  const r = plain(await page.w.stayCharge.readCharge(inPage(page.w, READ)));
  assert.equal(r.ok, false);
  assert.match(r.error, /stay_helper\.js.*stay_boot\.js.*없는 것: stayRun, calSet/);
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});

test('C7 · 작업 셋은 호출 하나로 끝나고, 답은 JSON 그대로 오가는 800자 안의 객체다', async () => {
  const page = chargePage();
  const sc = page.w.stayCharge;
  const look = await sc.look();
  const read = await sc.readCharge(inPage(page.w, READ));
  const form = takeAll(page.w, plain(read)).body.window.form;
  const apply = await sc.applyCharge(inPage(page.w, Object.assign({ no: 3, name: form[1][1], form, set: [['tiers_pct', 1, '60.00']] }, READ)));
  for (const [name, r] of [['look', look], ['readCharge', read], ['applyCharge', apply]]) {
    assert.equal(r.ok, true, `${name}: ${r.error}`);
    assert.equal(r.op, name);
    assert.equal(page.w.JSON.stringify(r), JSON.stringify(plain(r)), `${name}: JSON 으로 그대로 오간다`);
    assert.ok(charsOf(plain(r)) <= 800, `${name}: ${charsOf(plain(r))}자`);
    assert.ok(r.ms < 45000);
  }
  page.w.close();
});

test('C7 · 이름이 아주 길거나 값이 많거나 서버 오류가 길어도 답은 800자 안이다', async () => {
  const db = JSON.parse(JSON.stringify(DB));
  const long = '아주 긴 "이름" '.repeat(40);
  db.offers[0].name = long;
  db.offers[0].charges[0].name = long;
  const page = chargePage({ db });
  const read = plain(await page.w.stayCharge.readCharge(inPage(page.w, READ)));
  assert.equal(read.ok, true, read.error);
  assert.ok(charsOf(read) <= 800, String(charsOf(read)));
  const form = takeAll(page.w, read).body.window.form;
  const cases = [
    Object.assign({ name: long, form: [...form, ...Array.from({ length: 60 }, (_, i) => [`칸_${i}_${long.slice(0, 20)}`, long])], set: [['tiers_pct', 1, '60.00']] }, READ),
    Object.assign({ name: long, form, set: [['tiers_pct', 1, '60.00']] }, READ),
    Object.assign({ name: long, form, set: [[`age_rate_${'9'.repeat(400)}`, 0, '1.00']] }, READ)
  ];
  for (const payload of cases) {
    const r = plain(await page.w.stayCharge.applyCharge(inPage(page.w, payload)));
    assert.ok(charsOf(r) <= 800, `${charsOf(r)}자`);
  }
  page.w.close();
});

test('C7 · 세 도우미를 통틀어 작업은 한 번에 하나다 — 도는 동안의 다른 작업은 시작하지 않은 것으로 답한다', async () => {
  const page = chargePage({ withAddon: true });
  const first = page.w.stayCharge.readCharge(inPage(page.w, READ));
  const mine = plain(await page.w.stayCharge.look());
  assert.deepEqual([mine.ok, mine.started, mine.wait], [false, false, 10]);
  assert.match(mine.error, /앞 작업\(readCharge\)이 아직 끝나지 않았습니다/);
  const price = plain(await page.w.stayPrice.readPair(inPage(page.w, { hotel: HOTEL, offer: '오퍼', room: '디럭스', ratePlan: '조식 포함',
    from: '2026-07-01', to: '2026-07-01', weekdays: ['월'] })));
  assert.deepEqual([price.started, price.wait], [false, 10]);
  assert.match(price.error, /앞 작업\(readCharge\)이 아직 끝나지 않았습니다/);
  const addon = plain(await page.w.stayAddonPrice.readLine(inPage(page.w, { hotel: HOTEL, addon: '201', line: '301' })));
  assert.deepEqual([addon.started, addon.wait], [false, 10]);
  assert.match(addon.error, /앞 작업\(readCharge\)이 아직 끝나지 않았습니다/);
  assert.equal(plain(await first).ok, true);
  assert.equal(plain(await page.w.stayCharge.look()).ok, true, '끝난 뒤에는 다음 작업을 받는다');
  page.w.close();
});

test('C7 · localStorage 에는 stayPriceLast 하나만 더하고 러너의 키는 그대로 두며, last() 가 마지막 답을 돌려준다', async () => {
  const page = chargePage();
  const before = Object.keys(page.w.localStorage);
  plain(await page.w.stayCharge.look());
  const read = plain(await page.w.stayCharge.readCharge(inPage(page.w, READ)));
  const form = takeAll(page.w, read).body.window.form;
  const apply = plain(await page.w.stayCharge.applyCharge(inPage(page.w, Object.assign({ no: 4, name: form[1][1], form, set: [['tiers_pct', 1, '60.00']] }, READ))));
  assert.equal(apply.saved, true, apply.error);
  assert.deepEqual(Object.keys(page.w.localStorage).filter((k) => !before.includes(k)), ['stayPriceLast']);
  assert.equal(page.w.localStorage.getItem('staySteps'), RUNNER_STEPS);
  assert.equal(page.w.localStorage.getItem('stayRunCursor'), RUNNER_CURSOR);
  assert.deepEqual(plain(page.w.stayCharge.last()), apply);
  page.w.close();
});
