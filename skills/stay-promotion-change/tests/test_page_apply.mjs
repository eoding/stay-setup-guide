// M4 · M7 저장 — applyPromotion 은 표식 있는 창에서만, 창이 읽은 칸 · 단 표식과 꼭 같을 때만 set 의 단 값만 치고 저장을 한 번 누른다.
// 저장 요청은 읽은 form 에서 그 자리만 바꾼 것이다(진행기간 체크 · 숨은 칸 tiers_origin · 다른 단까지 그대로).
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { promotionPage, inPage, plain, takeAll, HOTEL, GATE } from './promotion_harness.mjs';

async function readWindow(page, offer, promotion) {
  const r = plain(await page.w.stayPromotion.readPromotion(inPage(page.w, { hotel: HOTEL, offer, promotion })));
  assert.equal(r.ok, true, r.error);
  return takeAll(page.w, r).body.window;
}
const titleOf = (form) => form.find(([name]) => name === 'title')[1];
function replaced(form, edits) {
  const seen = {};
  return form.map(([name, value]) => { const nth = seen[name] = (seen[name] ?? -1) + 1; const hit = edits.find(([n, i]) => n === name && i === nth); return [name, hit ? hit[2] : value]; });
}
async function apply(page, offer, promotion, win, set, extra = {}) {
  const input = Object.assign({ no: 1, hotel: HOTEL, offer, promotion, title: titleOf(win.form), form: win.form, marks: win.marks, set }, extra);
  return plain(await page.w.stayPromotion.applyPromotion(inPage(page.w, input)));
}

test('M4 · 두 단 할인율의 첫 단만 바꾸면 저장 요청은 읽은 form 에서 그 자리만 바뀐 것이고 저장 표지로 saved true 다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9002');
  const r = await apply(page, '601', '9002', win, [['tiers_value', 0, '8']]);
  assert.deepEqual([r.ok, r.saved, r.pressed], [true, true, true], r.error);
  assert.deepEqual(r.clicks, { promotionOpen: 1, promotionSave: 1 });
  assert.equal(page.log.posts.length, 1);
  assert.deepEqual(page.log.posts[0].pairs, replaced(win.form, [['tiers_value', 0, '8']]));
  assert.deepEqual(page.promotion('9002').trigger.tiers, [{ threshold: 2, pct: '8' }, { threshold: 3, pct: '10' }]);
  page.w.close();
});

test('M4 · 전 오퍼 공통 프로모션의 진행기간 제한은 켜진 채, 중복 허용도 켜진 채 간다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '0', '9006');
  const r = await apply(page, '0', '9006', win, [['tiers_value', 0, '6']]);
  assert.equal(r.saved, true, r.error);
  const sent = page.log.posts[0].pairs;
  assert.deepEqual(sent, replaced(win.form, [['tiers_value', 0, '6']]));
  assert.ok(sent.some(([n, v]) => n === 'promotion_apply_flag' && v === 'on'));
  assert.equal(page.promotion('9006').apply_flag, true);
  page.w.close();
});

test('M4 · 화면 밖 설정이 붙은 단은 숨은 칸 tiers_origin 이 그대로 가서 서버가 그 설정을 잇는다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9005');
  const r = await apply(page, '601', '9005', win, [['tiers_value', 0, '16']]);
  assert.equal(r.saved, true, r.error);
  assert.deepEqual(page.promotion('9005').trigger.tiers, [{ threshold: 46, pct: '16', cancellation: 'NRF' },
    { threshold: 31, pct: '10.0', cancellation: 'CUTOFF_AT_THRESHOLD' }]);
  page.w.close();
});

test('M4 · 표식 없는 창이면 아무것도 치지 않고 누르지 않는다 — 그 까닭을 쉬운 말로 말한다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9005');
  page.setKeeps(false);
  const bare = Object.assign({}, win, { form: win.form.filter(([name]) => name !== 'tiers_origin') });
  const r = await apply(page, '601', '9005', bare, [['tiers_value', 0, '16']]);
  assert.deepEqual([r.ok, r.saved, r.pressed, r.refused, r.gate], [false, false, false, true, true]);
  assert.ok(r.error.startsWith(GATE), r.error);
  assert.deepEqual([page.log.typed, page.log.posts], [[], []]);
  page.w.close();
});

test('M4 · 단 줄의 화면 밖 설정 이름이 읽은 것과 다르면 아무것도 치지 않는다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9005');
  delete page.promotion('9005').trigger.tiers[1].cancellation;
  const r = await apply(page, '601', '9005', win, [['tiers_value', 0, '16']]);
  assert.deepEqual([r.saved, r.pressed, r.refused], [false, false, true]);
  assert.match(r.error, /단 표식/);
  assert.deepEqual([page.log.typed, page.log.posts], [[], []]);
  page.w.close();
});

test('M4 · 창이 읽은 값과 다른 단 값을 보이면 아무것도 치지 않고 누르지 않는다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9002');
  page.promotion('9002').trigger.tiers[1].pct = '11';
  const r = await apply(page, '601', '9002', win, [['tiers_value', 0, '8']]);
  assert.deepEqual([r.saved, r.pressed, r.refused], [false, false, true]);
  assert.deepEqual(r.differ, ['tiers_value']);
  assert.deepEqual([page.log.typed, page.log.posts], [[], []]);
  page.w.close();
});

test('M4 · set 에는 단의 값 칸만, 숫자 글자만, 빈 칸이 아닌 자리만 — 아니면 창을 열지도 않는다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9002');
  for (const set of [[['tiers_threshold', 0, '5']], [['title', 0, 'x']], [['tiers_value', 0, '']], [['tiers_value', 0, '-1']],
    [['tiers_value', 5, '8']], [['tiers_value', 0, '8'], ['tiers_value', 0, '9']]]) {
    const r = await apply(page, '601', '9002', win, set);
    assert.deepEqual([r.ok, r.saved, r.pressed], [false, false, false], JSON.stringify(set));
  }
  assert.deepEqual(page.log.posts, []);
  page.w.close();
});

test('M4 · 서버가 거절하면 saved false 이고, 응답이 없으면 "unknown" 이며 다시 누르지 않는다', async () => {
  for (const [mode, saved] of [['refuse', false], ['silent', 'unknown']]) {
    const page = promotionPage({ onSave: mode });
    const win = await readWindow(page, '601', '9003');
    const r = await apply(page, '601', '9003', win, [['tiers_value', 0, '25']]);
    assert.deepEqual([r.saved, r.pressed], [saved, true], mode);
    assert.equal(page.log.posts.length, 1, `${mode}: 한 번만 눌렀다`);
    page.w.close();
  }
});

test('M7 · 한 작업 안에서 저장 단추를 두 번 누르면 두 번째는 벽이 막는다(서버가 아직 답하지 않아 창이 그대로일 때)', async () => {
  const page = promotionPage({ onSave: 'silent' });
  const root = page.showPromotion('9002');
  const save = root.querySelector('[data-stay-action="save"]');
  const seen = plain(await page.w.stayPromotion.guard('applyPromotion', async () => { save.click(); save.click(); },
    { hotel: HOTEL.id, offer: '601', promotion: '9002' }));
  assert.deepEqual(seen.clicks, ['promotionSave']);
  assert.equal(seen.blocked.length, 1);
  assert.match(seen.blocked[0].why, /같은 저장을 다시 누르지 않습니다/);
  assert.equal(page.log.posts.length, 1, '서버에 닿은 저장은 하나다');
  page.w.close();
});

test('M7 · 표식 없는 창의 [저장] 은 벽이 막는다(누르는 순간 그 창의 표식을 본다)', async () => {
  const page = promotionPage({ keeps: false });
  const root = page.showPromotion('9002');
  const seen = plain(await page.w.stayPromotion.guard('applyPromotion', async () => { root.querySelector('[data-stay-action="save"]').click(); },
    { hotel: HOTEL.id, offer: '601', promotion: '9002' }));
  assert.deepEqual(seen.clicks, []);
  assert.match(seen.blocked[0].why, /이 작업이 고른 대상이 아닙니다\(promotionSave\)/);
  assert.deepEqual(page.log.posts, []);
  page.w.close();
});
