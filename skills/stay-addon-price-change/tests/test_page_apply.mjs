// A3 줄 저장 — applyLine({no, hotel, addon, line, form, set}) 은 창을 열고, 치기 전에 창의 칸이 앞서 읽은 form 과 꼭 같은지, 친 뒤에는
// set 의 칸만 바뀌었는지 보고 저장을 한 번 누른다. 공급 원가는 set 이 비우라고(net_amount: "") 할 때만 빈 채로 나간다.
// 저장됐는지는 saved true(창이 사라지고 저장 표지가 왔다) · false(누르지 않았거나 서버가 오류와 함께 창을 다시 그렸다) · "unknown".
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { addonPage, inPage, plain, takeAll, HOTEL } from './addon_harness.mjs';

async function readForm(page, addon, line) {
  const r = plain(await page.w.stayAddonPrice.readLine(inPage(page.w, { hotel: HOTEL, addon, line })));
  assert.equal(r.ok, true, r.error);
  return takeAll(page.w, r).body.window.form;
}
const apply = async (page, payload) => plain(await page.w.stayAddonPrice.applyLine(inPage(page.w, Object.assign({ no: 7, hotel: HOTEL }, payload))));
// form 에서 그 이름의 값만 바꾼 목록 — 저장 요청이 꼭 이것이어야 한다
const replaced = (form, values) => form.map(([name, value]) => [name, name in values ? values[name] : value]);
async function listed(page, line) {
  const r = plain(await page.w.stayAddonPrice.look());
  return takeAll(page.w, r).body.addons.flatMap((a) => a.lines).find((l) => l.id === line);
}
const LINE = { addon: '201', line: '301' };

test('A3 · 창이 읽은 그대로면 저장 요청 하나에 form 에서 판매가만 바꿔 보낸다 — 공급 원가는 그대로 실린다', async () => {
  const page = addonPage();
  const form = await readForm(page, '201', '301');
  const r = await apply(page, Object.assign({ form, set: { price: '22.00' } }, LINE));
  assert.equal(r.ok, true, r.error);
  assert.deepEqual([r.op, r.no, r.saved, r.pressed, r.note], ['applyLine', 7, true, true, '저장했습니다']);
  assert.deepEqual(r.clicks, { lineOpen: 1, lineSave: 1 });
  assert.equal(page.log.posts.length, 1);
  assert.equal(page.log.posts[0].path, '/stay/1/addon-prices/301/edit/');
  assert.deepEqual(page.log.posts[0].pairs, replaced(form, { price: '22.00' }));
  assert.deepEqual(page.log.posts[0].pairs.find(([name]) => name === 'net_amount'), ['net_amount', '15.00'], '공급 원가가 비지 않았다');
  assert.equal(r.rest, true);
  const after = await listed(page, '301');
  assert.deepEqual([after.sell, after.values], ['22.00 USD', ['판매가: 22.00 USD', '공급 원가: 15.00 USD']]);
  page.w.close();
});

test('A3 · 판매가와 공급 원가를 함께 바꾸면 그 둘만 바뀐 요청이 나간다(적용 범위 체크도 그대로)', async () => {
  const page = addonPage();
  const form = await readForm(page, '204', '305');
  const r = await apply(page, { addon: '204', line: '305', form, set: { price: '36.30', net_amount: '30.25' } });
  assert.equal(r.saved, true, r.error);
  assert.deepEqual(page.log.posts[0].pairs, replaced(form, { price: '36.30', net_amount: '30.25' }));
  assert.ok(page.log.posts[0].pairs.some(([name, value]) => name === 'scope_rate_plan_include' && value === '53'));
  page.w.close();
});

test('A3 · 창의 판매가가 읽은 값과 다르면(그 사이 누가 고쳤으면) 한 글자도 치지 않고 저장도 하지 않는다', async () => {
  const page = addonPage();
  const form = await readForm(page, '201', '301');
  page.db.addons[0].lines[0].price = '21.00';   // 다른 사람이 그 사이 저장했다 — 창은 21.00 을 보인다
  const r = await apply(page, Object.assign({ form, set: { price: '22.00' } }, LINE));
  assert.deepEqual([r.ok, r.refused, r.saved, r.pressed], [false, true, false, false]);
  assert.match(r.error, /^창의 값이 읽은 값과 다릅니다\(price\) — 아무것도 치지 않았고 누르지 않았습니다$/, '앞 저장이 됐는지는 페이지가 모른다 — 새 미리보기를 약속하지 않는다');
  assert.deepEqual(r.differ, ['price']);
  assert.deepEqual(page.log.typed, [], '치지 않았다');
  assert.deepEqual(page.log.posts, [], '저장 요청이 없다');
  assert.equal(page.drawerOpen(), false);
  page.w.close();
});

test('A3 · 창의 공급 원가 · 설명 · 범위 칸 어느 것이든 읽은 값과 다르면 그 칸 이름을 대며 거절한다', async () => {
  const page = addonPage();
  const form = await readForm(page, '201', '301');
  const cases = [
    [replaced(form, { net_amount: '14.00' }), ['net_amount']],
    [replaced(form, { description: '메모' }), ['description']],
    [form.filter(([name]) => name !== 'scope_room_mode'), ['scope_room_mode']],
    [[...form, ['scope_rate_plan_include', '51']], ['scope_rate_plan_include']]
  ];
  for (const [stale, names] of cases) {
    const r = await apply(page, Object.assign({ form: stale, set: { price: '22.00' } }, LINE));
    assert.deepEqual([r.refused, r.saved, r.pressed, r.differ], [true, false, false, names], JSON.stringify(names));
  }
  assert.deepEqual([page.log.typed, page.log.posts], [[], []]);
  page.w.close();
});

test('A3 · 판매가를 치자 화면이 공급 원가를 비우면 빈 원가로 저장하지 않는다', async () => {
  const page = addonPage({ onType: 'clearNet' });
  const form = await readForm(page, '201', '301');
  const r = await apply(page, Object.assign({ form, set: { price: '22.00' } }, LINE));
  assert.deepEqual([r.refused, r.saved, r.pressed], [true, false, false]);
  assert.match(r.error, /공급 원가가 빈 채로 저장될 뻔했습니다/);
  assert.deepEqual(page.log.posts, []);
  page.w.close();
});

test('A3 · 공급 원가는 set.net_amount 가 "" 일 때만 비워 보낸다 — 원래 빈 줄은 빈 채로 둔다', async () => {
  const page = addonPage();
  const form = await readForm(page, '201', '302');
  const cleared = await apply(page, { addon: '201', line: '302', form, set: { net_amount: '' } });
  assert.equal(cleared.saved, true, cleared.error);
  assert.deepEqual(page.log.posts[0].pairs, replaced(form, { net_amount: '' }));
  assert.deepEqual((await listed(page, '302')).values, ['판매가: 35.50 USD'], '저장된 원가가 지워졌다');
  const blank = await readForm(page, '202', '303');
  const kept = await apply(page, { addon: '202', line: '303', form: blank, set: { price: '42.00' } });
  assert.equal(kept.saved, true, kept.error);
  assert.deepEqual(page.log.posts[1].pairs, replaced(blank, { price: '42.00' }));
  page.w.close();
});

test('A3 · set 은 price · net_amount 의 금액 글자만, form 은 readLine 의 목록만 받는다 — 아니면 아무것도 누르지 않는다', async () => {
  const page = addonPage();
  const form = await readForm(page, '201', '301');
  const bad = [
    [{ form, set: { name: '새 이름' } }, /price\(판매가\) · net_amount\(공급 원가\)만/],
    [{ form, set: { price: '' } }, /`set\.price` 은 금액 글자/],
    [{ form, set: { price: 22 } }, /`set\.price` 은 금액 글자/],
    [{ form, set: { net_amount: '-1' } }, /`set\.net_amount` 은 금액 글자/],
    [{ form, set: {} }, /`set` 은 바꿀 칸/],
    [{ form: form.filter(([name]) => name !== 'net_amount'), set: { net_amount: '1.00' } }, /`form` 에 net_amount 칸이 하나가 아닙니다/],
    [{ form: [['price']], set: { price: '1.00' } }, /`form` 은 readLine 이 돌려준/]
  ];
  const before = page.log.reached.length;
  for (const [payload, why] of bad) {
    const r = await apply(page, Object.assign({}, LINE, payload));
    assert.deepEqual([r.ok, r.saved, r.pressed], [false, false, false], String(why));
    assert.match(r.error, why);
  }
  assert.equal(page.log.reached.length, before, '아무것도 누르지 않았다');
  page.w.close();
});

test('A3 · 서버가 거절하면(창이 오류와 함께 다시 그려지면) saved false · pressed true 이고 드로어를 닫고 답한다', async () => {
  for (const [how, opts, set, error] of [
    ['적용 범위 오류', { onSave: 'refuse' }, { price: '22.00' }, /부가옵션의 범위 안이어야 합니다/],
    ['폼 검사 오류', {}, { price: '22.555' }, /소수점 아래는 두 자리까지입니다/]
  ]) {
    const page = addonPage(opts);
    const form = await readForm(page, '201', '301');
    const r = await apply(page, Object.assign({ form, set }, LINE));
    assert.deepEqual([r.ok, r.saved, r.pressed], [false, false, true], how);
    assert.match(r.error, /가격 편집 창이 저장을 거절했습니다/, how);
    assert.match(r.errors.join(' '), error, how);
    assert.equal(page.log.posts.length, 1, `${how}: 요청은 하나`);
    assert.equal(page.drawerOpen(), false, `${how}: 다시 그려진 창은 닫았다`);
    assert.equal(r.rest, true, how);
    page.w.close();
  }
});

test('A3 · 눌렀는데 아무 표지도 없으면 "unknown" 이고 다시 누르지 않는다 — 앞 저장이 남긴 배너 · 표지는 표지로 치지 않는다', async () => {
  const page = addonPage();
  const first = await apply(page, Object.assign({ form: await readForm(page, '201', '301'), set: { price: '22.00' } }, LINE));
  assert.equal(first.saved, true, first.error);
  page.answerSavesWith('silent');
  page.w.stayPrice.config({ budgetMs: 1500 });
  const form = await readForm(page, '201', '302');
  const r = await apply(page, { addon: '201', line: '302', form, set: { price: '36.00' } });
  assert.deepEqual([r.ok, r.saved, r.pressed], [false, 'unknown', true]);
  assert.match(r.error, /저장됐는지 알 수 없습니다 — 다시 읽어 확인합니다\(다시 누르지 않았습니다\)/);
  assert.equal(page.log.posts.length, 2, '두 번째 줄의 저장 요청은 하나');
  assert.equal(r.clicks.lineSave, 1);
  page.w.close();
});

test('A3 · 저장 표지는 둘 중 하나면 된다 — 목록 요소를 그대로 두고 안만 갈아도(저장 시각), 저장 시각이 없어도(새 목록의 배너)', async () => {
  for (const [how, opts] of [['목록 안만 갈림', { onSave: 'morph' }], ['저장 시각 없음', { stamp: false }]]) {
    const page = addonPage(opts);
    const form = await readForm(page, '201', '301');
    const r = await apply(page, Object.assign({ form, set: { price: '22.00' } }, LINE));
    assert.equal(r.saved, true, `${how}: ${r.error}`);
    page.w.close();
  }
});

test('A3 · 서버가 다른 줄의 창을 내주면 치지도 저장하지도 않는다', async () => {
  const page = addonPage();
  const form = await readForm(page, '201', '301');
  const wrong = addonPage({ windowFor: { 301: '302' } });
  const r = await apply(wrong, Object.assign({ form, set: { price: '22.00' } }, LINE));
  assert.deepEqual([r.refused, r.saved, r.pressed], [true, false, false]);
  assert.match(r.error, /열린 창이 고른 줄\(301\)의 가격 편집 창이 아닙니다/);
  assert.deepEqual([wrong.log.typed, wrong.log.posts], [[], []]);
  wrong.w.close();
  page.w.close();
});

test('A3 · 다른 호텔의 탭이면 아무것도 누르기 전에 거절하고, 목록에 없는 줄은 누르지 않고 거절한다', async () => {
  const page = addonPage();
  const form = await readForm(page, '201', '301');
  const other = addonPage({ hotel: { id: '2', name: '다른 호텔' } });
  const r = await apply(other, Object.assign({ form, set: { price: '22.00' } }, LINE));
  assert.equal(r.ok, false);
  assert.match(r.error, /이 탭은 호텔 2 \(다른 호텔\) 입니다 — 요청은 호텔 1 \(데모 호텔\) 입니다/);
  assert.deepEqual([other.log.reached, other.log.posts, r.clicks], [[], [], {}]);
  other.w.close();
  const gone = await apply(page, { addon: '201', line: '399', form, set: { price: '22.00' } });
  assert.deepEqual([gone.refused, gone.missing, gone.saved, gone.pressed], [true, true, false, false]);
  assert.equal(page.log.posts.length, 0);
  page.w.close();
});
