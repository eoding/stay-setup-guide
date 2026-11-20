// C4 부과금 저장 — applyCharge({no, hotel, offer, charge, name, form, set}) 는 창을 열고, 창의 이름이 고른 부과금인지, 치기 전에 창의
// 칸이 앞서 읽은 form 과 꼭 같은지, 친 뒤에는 set 의 자리([이름, 몇 번째])만 바뀌었는지 보고 저장을 한 번 누른다. 금액의 뜻 · 다른
// 시간대 행 · 연령별 단가 · 범위는 읽은 그대로 나간다. 저장됐는지는 saved true · false · "unknown".
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { chargePage, inPage, plain, takeAll, HOTEL } from './charge_harness.mjs';

const OFFER = { 701: '601', 702: '601', 703: '601', 704: '601', 705: '602', 706: '602' };
async function readForm(page, charge) {
  const r = plain(await page.w.stayCharge.readCharge(inPage(page.w, { hotel: HOTEL, offer: OFFER[charge], charge })));
  assert.equal(r.ok, true, r.error);
  return takeAll(page.w, r).body.window.form;
}
const nameIn = (form) => form.find(([name]) => name === 'name')[1];
const apply = async (page, charge, form, set, extra = {}) => plain(await page.w.stayCharge.applyCharge(inPage(page.w,
  Object.assign({ no: 7, hotel: HOTEL, offer: OFFER[charge], charge, name: nameIn(form), form, set }, extra))));
// form 에서 그 자리([이름, 몇 번째])만 바꾼 목록 — 저장 요청이 꼭 이것이어야 한다(요구에서 바로 셈한다)
function replaced(form, set) {
  const seen = {};
  return form.map(([name, value]) => {
    seen[name] = (seen[name] ?? -1) + 1;
    const hit = set.find(([n, nth]) => n === name && nth === seen[name]);
    return [name, hit ? hit[2] : value];
  });
}
const values = (pairs, name) => pairs.filter(([n]) => n === name).map(([, v]) => v);
async function listed(page, id) {
  const r = plain(await page.w.stayCharge.look());
  return takeAll(page.w, r).body.offers.flatMap((o) => o.charges).find((c) => c.id === id);
}

test('C4 · 고치지 않은 시간대 행의 금액이 바뀌어 나가지 않는다 — 701 의 둘째 행 정률만 바꾸면 첫째 행은 읽은 그대로 실린다', async () => {
  const page = chargePage();
  const form = await readForm(page, '701');
  const set = [['tiers_pct', 1, '60.00']];
  const r = await apply(page, '701', form, set);
  assert.equal(r.ok, true, r.error);
  assert.deepEqual([r.op, r.no, r.saved, r.pressed, r.note], ['applyCharge', 7, true, true, '저장했습니다']);
  assert.deepEqual(r.clicks, { chargeOpen: 1, chargeSave: 1 });
  assert.equal(page.log.posts.length, 1);
  assert.equal(page.log.posts[0].path, '/stay/1/charges/701/edit/');
  const posted = page.log.posts[0].pairs;
  assert.deepEqual(posted, replaced(form, set));
  assert.deepEqual(values(posted, 'tiers_pct'), ['', '60.00']);
  assert.deepEqual(values(posted, 'tiers_amount'), ['0.00', ''], '첫째 행의 정액 0.00 은 그대로');
  assert.deepEqual([values(posted, 'tiers_time_from'), values(posted, 'tiers_time_to'), values(posted, 'tiers_basis')],
    [['12:01', '14:01'], ['14:00', '18:00'], ['0', '1']]);
  assert.equal(r.rest, true);
  assert.deepEqual((await listed(page, '701')).amount, ['12:01 ~ 14:00 · 정액: 0.00 USD', '14:01 ~ 18:00 · 1박 요금의 %: 60.00%', '체류당 1회']);
  page.w.close();
});

test('C4 · 첫째 행만 바꿔도, 두 행을 함께 바꿔도 그 자리만 바뀐 요청 하나가 나간다', async () => {
  const page = chargePage();
  const form = await readForm(page, '702');
  const first = [['tiers_pct', 0, '90.00']];
  assert.equal((await apply(page, '702', form, first)).saved, true);
  assert.deepEqual(page.log.posts[0].pairs, replaced(form, first));
  assert.deepEqual(values(page.log.posts[0].pairs, 'tiers_pct'), ['90.00', '30.00']);
  const again = await readForm(page, '702');
  const both = [['tiers_pct', 1, '40.00'], ['tiers_pct', 0, '95.00']];
  const r = await apply(page, '702', again, both);
  assert.equal(r.saved, true, r.error);
  assert.deepEqual(page.log.posts[1].pairs, replaced(again, both));
  assert.deepEqual((await listed(page, '702')).amount.slice(0, 2), ['00:00 ~ 06:59 · 1박 요금의 %: 95.00%', '07:00 ~ 12:00 · 1박 요금의 %: 40.00%']);
  page.w.close();
});

test('C4 · 금액의 뜻은 창이 「지정」이면 「지정」 그대로 나간다(미정으로 바뀌어 나가지 않는다)', async () => {
  const page = chargePage();
  const gala = await readForm(page, '703');
  assert.equal((await apply(page, '703', gala, [['amount', 0, '99.00']])).saved, true);
  assert.deepEqual(values(page.log.posts[0].pairs, 'amount_mode'), ['set']);
  assert.deepEqual(values(page.log.posts[0].pairs, 'amount'), ['99.00']);
  const early = await readForm(page, '702');
  assert.equal((await apply(page, '702', early, [['pct', 0, '35.00']])).saved, true);
  assert.deepEqual([values(page.log.posts[1].pairs, 'pct_mode'), values(page.log.posts[1].pairs, 'amount_mode')], [['set'], ['blank']]);
  assert.deepEqual((await listed(page, '703')).amount, ['99.00 USD', '인당']);
  page.w.close();
});

test('C4 · 금액을 치자 화면 스크립트가 금액의 뜻을 「미정」으로 바꾸면 저장하지 않는다', async () => {
  const page = chargePage({ onType: 'flipMode' });
  const form = await readForm(page, '703');
  const r = await apply(page, '703', form, [['amount', 0, '99.00']]);
  assert.deepEqual([r.ok, r.refused, r.saved, r.pressed], [false, true, false, false]);
  assert.match(r.error, /친 뒤의 창이 바꾼 칸 말고도 다릅니다\(amount_mode\) — 저장하지 않았습니다/);
  assert.deepEqual(r.differ, ['amount_mode']);
  assert.deepEqual(page.log.posts, [], '저장 요청이 없다');
  assert.equal(page.drawerOpen(), false);
  page.w.close();
});

test('C4 · 창이 읽은 값과 다른 금액을 보이면(그 사이 누가 고쳤으면) 한 글자도 치지 않고 저장도 하지 않는다', async () => {
  const page = chargePage();
  const form = await readForm(page, '701');
  page.charge('701').tiers[1].pct = '55.00';   // 다른 사람이 그 사이 저장했다 — 창은 55.00 을 보인다
  const r = await apply(page, '701', form, [['tiers_pct', 1, '60.00']]);
  assert.deepEqual([r.ok, r.refused, r.saved, r.pressed], [false, true, false, false]);
  assert.match(r.error, /창의 값이 읽은 값과 다릅니다\(tiers_pct\) — 아무것도 치지 않았습니다/);
  assert.deepEqual(r.differ, ['tiers_pct']);
  assert.deepEqual(page.log.typed, [], '치지 않았다');
  assert.deepEqual(page.log.posts, [], '저장 요청이 없다');
  const gala = await readForm(page, '703');
  page.charge('703').amount = '95.00';
  const r2 = await apply(page, '703', gala, [['amount', 0, '99.00']]);
  assert.deepEqual([r2.refused, r2.saved, r2.pressed, r2.differ], [true, false, false, ['amount']]);
  assert.deepEqual([page.log.typed, page.log.posts], [[], []]);
  page.w.close();
});

test('C4 · 시간대 행 · 금액의 뜻 · 연령별 단가 · 범위 · 설명 어느 것이든 읽은 값과 다르면 그 칸 이름을 대며 거절한다', async () => {
  const page = chargePage();
  const form = await readForm(page, '705');
  const set = [['age_rate_82', 0, '55.00']];
  const cases = [
    [replaced(form, [['amount_mode', 0, 'blank']]), ['amount_mode']],
    [replaced(form, [['age_rate_81', 0, '1.00']]), ['age_rate_81']],
    [replaced(form, [['description', 0, '메모']]), ['description']],
    [form.filter(([name]) => name !== 'scope_room_mode'), ['scope_room_mode']],
    [[...form, ['room_scope', '53']], ['room_scope']],
    [[...form.slice(0, 3), form[4], form[3], ...form.slice(5)], ['(칸 순서)']]
  ];
  for (const [stale, names] of cases) {
    const r = await apply(page, '705', stale, set, { name: nameIn(form) });
    assert.deepEqual([r.refused, r.saved, r.pressed, r.differ], [true, false, false, names], JSON.stringify(names));
  }
  const bands = await readForm(page, '701');
  const r = await apply(page, '701', [...bands, ['tiers_time_from', '19:00']], [['tiers_pct', 1, '60.00']]);
  assert.deepEqual([r.refused, r.differ], [true, ['tiers_time_from']], '읽을 때 없던 시간대 행');
  assert.deepEqual([page.log.typed, page.log.posts], [[], []]);
  page.w.close();
});

test('C4 · 저장을 두 번 누르는 것은 지나가지 않는다 — 한 작업의 벽 안에서 두 번째 [저장] 은 막히고 요청은 하나다', async () => {
  const page = chargePage();
  const pins = { hotel: HOTEL.id, offer: '601', charge: '701' };
  const save = () => page.doc.querySelector('#stay_drawer_body [data-stay-action="save"]').click();
  page.showCharge('701');
  // 첫 저장이 창을 닫는다 — 같은 창을 다시 그려 한 번 더 눌러 본다
  const seen = plain(await page.w.stayCharge.guard('applyCharge', async () => { save(); page.showCharge('701'); save(); }, pins));
  assert.deepEqual(seen.clicks, ['chargeSave']);
  assert.equal(seen.blocked.length, 1);
  assert.match(seen.blocked[0].why, /같은 저장을 다시 누르지 않습니다/);
  assert.equal(page.log.posts.length, 1, '저장 요청은 하나');
  page.w.close();
});

test('C4 · 연령별 단가 · 현장 결제 금액 · 정액 0 도 그 칸만 바꿔 저장한다', async () => {
  const page = chargePage();
  for (const [id, set, line] of [
    ['705', [['age_rate_82', 0, '55.00']], '소아: 55.00 USD'],
    ['705', [['age_rate_81', 0, '0'], ['amount', 0, '110.00']], '110.00 USD'],
    ['704', [['onsite_amount', 0, '20.00']], '현장 결제: 20.00 USD']
  ]) {
    const form = await readForm(page, id);
    const r = await apply(page, id, form, set);
    assert.equal(r.saved, true, `${id}: ${r.error}`);
    assert.deepEqual(page.log.posts.at(-1).pairs, replaced(form, set), id);
    assert.ok((await listed(page, id)).amount.includes(line), `${id}: ${line}`);
  }
  page.w.close();
});

test('C3 · set 은 금액 칸 · 금액 글자 · 읽은 form 에 있는 빈칸 아닌 자리만 받는다 — 아니면 아무것도 누르지 않는다', async () => {
  const page = chargePage();
  const form = await readForm(page, '701');
  const blank = await readForm(page, '706');
  const bad = [
    [form, [['amount_mode', 0, 'set']], /`set` 에는 금액 칸만 넣습니다/],
    [form, [['kind', 0, '9']], /`set` 에는 금액 칸만 넣습니다/],
    [form, [['tiers_time_from', 0, '12:00']], /`set` 에는 금액 칸만 넣습니다/],
    [form, [['tiers_basis', 1, '0']], /`set` 에는 금액 칸만 넣습니다/],
    [form, [['description', 0, '1']], /`set` 에는 금액 칸만 넣습니다/],
    [form, [['tiers_pct', 1, '']], /값은 금액 글자입니다\(예: "60\.00"\) — 이 도우미는 금액을 비우지 않습니다/],
    [form, [['tiers_pct', 1, '-5']], /값은 금액 글자입니다/],
    [form, [['tiers_pct', 1, 60]], /값은 금액 글자입니다/],
    [form, [['tiers_pct', 2, '60.00']], /`form` 에 tiers_pct 칸의 3번째가 없습니다/],
    [form, [['tiers_pct', -1, '60.00']], /0 부터 세는 정수입니다/],
    [form, [['tiers_pct', 1.5, '60.00']], /0 부터 세는 정수입니다/],
    [form, [['tiers_pct', '1', '60.00']], /0 부터 세는 정수입니다/],
    [form, [['tiers_pct', 0, '60.00']], /`form` 의 tiers_pct 1번째 칸이 비어 있습니다 — 이 도우미는 빈 금액을 채우지 않습니다/],
    [form, [['amount', 0, '10.00']], /`form` 의 amount 1번째 칸이 비어 있습니다/],
    [blank, [['age_rate_82', 0, '10.00']], /`form` 의 age_rate_82 1번째 칸이 비어 있습니다/],
    [form, [['tiers_pct', 1, '60.00'], ['tiers_pct', 1, '61.00']], /`set` 에 tiers_pct 의 2번째가 두 번 있습니다/],
    [form, [], /`set` 은 바꿀 칸 목록입니다/],
    [form, { tiers_pct: '60.00' }, /`set` 은 바꿀 칸 목록입니다/],
    [form, [['tiers_pct', 1]], /`set` 의 한 줄은 \[이름, 몇 번째, 금액 글자\]/],
    [[['name']], [['amount', 0, '1.00']], /`form` 은 readCharge 이 돌려준 window\.form/]
  ];
  const before = page.log.reached.length;
  for (const [f, set, why] of bad) {
    const charge = f === blank ? '706' : '701';
    const r = await apply(page, charge, f, set, { name: f === blank ? nameIn(blank) : nameIn(form) });
    assert.deepEqual([r.ok, r.saved, r.pressed], [false, false, false], String(why));
    assert.match(r.error, why);
  }
  const noName = await apply(page, '701', form, [['tiers_pct', 1, '60.00']], { name: '' });
  assert.match(noName.error, /`name` 은 readCharge 가 읽은 부과금 이름/);
  assert.equal(page.log.reached.length, before, '아무것도 누르지 않았다');
  page.w.close();
});

test('C4 · 창의 이름 칸이 고른 부과금의 이름이 아니면 치지도 저장하지도 않는다', async () => {
  const page = chargePage();
  const form = await readForm(page, '701');
  const r = await apply(page, '701', form, [['tiers_pct', 1, '60.00']], { name: '얼리 체크인 (07시부터 · 1박 요금의 30%)' });
  assert.deepEqual([r.ok, r.refused, r.saved, r.pressed], [false, true, false, false]);
  assert.match(r.error, /창의 부과금 이름이 고른 부과금\(「얼리 체크인/);
  assert.deepEqual([page.log.typed, page.log.posts], [[], []]);
  page.w.close();
});

test('C4 · 서버가 거절하면(창이 오류와 함께 다시 그려지면) saved false · pressed true 이고 드로어를 닫고 답한다', async () => {
  for (const [how, opts, id, set, error] of [
    ['적용 범위 오류', { onSave: 'refuse' }, '701', [['tiers_pct', 1, '60.00']], /오퍼가 파는 객실 안이어야 합니다/],
    ['폼 검사 오류', {}, '703', [['amount', 0, '90.555']], /소수점 아래는 두 자리까지입니다/],
    ['현장 결제 규칙', {}, '704', [['amount', 0, '5.00']], /현장 결제 항목의 온라인 정액·연령별 금액은 0으로 두고/]
  ]) {
    const page = chargePage(opts);
    const form = await readForm(page, id);
    const r = await apply(page, id, form, set);
    assert.deepEqual([r.ok, r.saved, r.pressed], [false, false, true], how);
    assert.match(r.error, /부과금 편집 창이 저장을 거절했습니다/, how);
    assert.match(r.errors.join(' '), error, how);
    assert.equal(page.log.posts.length, 1, `${how}: 요청은 하나`);
    assert.equal(page.drawerOpen(), false, `${how}: 다시 그려진 창은 닫았다`);
    assert.equal(r.rest, true, how);
    page.w.close();
  }
});

test('C4 · 눌렀는데 아무 표지도 없으면 "unknown" 이고 다시 누르지 않는다 — 앞 저장이 남긴 배너 · 표지는 표지로 치지 않는다', async () => {
  const page = chargePage();
  const first = await apply(page, '701', await readForm(page, '701'), [['tiers_pct', 1, '60.00']]);
  assert.equal(first.saved, true, first.error);
  page.answerSavesWith('silent');
  page.w.stayPrice.config({ budgetMs: 1500 });
  const form = await readForm(page, '703');
  const r = await apply(page, '703', form, [['amount', 0, '99.00']]);
  assert.deepEqual([r.ok, r.saved, r.pressed], [false, 'unknown', true]);
  assert.match(r.error, /저장됐는지 알 수 없습니다 — 다시 읽어 확인합니다\(다시 누르지 않았습니다\)/);
  assert.equal(page.log.posts.length, 2, '두 번째 부과금의 저장 요청은 하나');
  assert.equal(r.clicks.chargeSave, 1);
  page.w.close();
});

test('C4 · 서버가 다른 부과금의 창을 내주면 치지도 저장하지도 않는다', async () => {
  const page = chargePage();
  const form = await readForm(page, '701');
  const wrong = chargePage({ windowFor: { 701: '702' } });
  const r = await apply(wrong, '701', form, [['tiers_pct', 1, '60.00']]);
  assert.deepEqual([r.refused, r.saved, r.pressed], [true, false, false]);
  assert.match(r.error, /열린 창이 고른 부과금\(701\)의 편집 창이 아닙니다/);
  assert.deepEqual([wrong.log.typed, wrong.log.posts], [[], []]);
  wrong.w.close();
  page.w.close();
});

test('C4 · 다른 호텔의 탭이면 아무것도 누르기 전에 거절하고, 목록에 없는 부과금은 누르지 않고 거절한다', async () => {
  const page = chargePage();
  const form = await readForm(page, '701');
  const other = chargePage({ hotel: { id: '2', name: '다른 호텔' } });
  const r = await apply(other, '701', form, [['tiers_pct', 1, '60.00']]);
  assert.equal(r.ok, false);
  assert.match(r.error, /이 탭은 호텔 2 \(다른 호텔\) 입니다 — 요청은 호텔 1 \(데모 호텔\) 입니다/);
  assert.deepEqual([other.log.reached, other.log.posts, r.clicks], [[], [], {}]);
  other.w.close();
  const gone = await apply(page, '701', form, [['tiers_pct', 1, '60.00']], { charge: '799' });
  assert.deepEqual([gone.refused, gone.missing, gone.saved, gone.pressed], [true, true, false, false]);
  assert.match(gone.error, /목록에 그 오퍼의 그 부과금이 없습니다 — 저장하지 않았습니다/);
  assert.equal(page.log.posts.length, 0);
  page.w.close();
});
