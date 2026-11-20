// B7 적용 — applyBulk 은 러너의 runCalendarPriceStep 으로 「조합마다 직접 입력」 저장 한 번, applyCell 은 셀 창 저장 한 번.
// 둘 다 저장을 다시 누르지 않고, 화면에 없는 줄이나 다른 날짜의 창이면 손대지 않고 거절한다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { erpPage, inPage, plain, runFixture, charsOf, OFFER, HOTEL } from './page_harness.mjs';

const BULK = { no: 1, hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', dates: ['2026-07-01'], rows: [{ occupancy: '', nights: 1, sell: '125000.00', list: null, supply: null }] };
const CELL = { no: 2, hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', date: '2026-07-01', occupancy: '', nights: 1, clear: ['list'] };
const LEAKS = ['erp.example.test', '?month', '/stay/', 'offer=9', 'stay_tab_calendar'];
const priceOf = (post, key, col) => {
  const n = Object.keys(post).map((k) => /^prices-(\d+)-los_nights$/.exec(k)).filter(Boolean).map((m) => m[1])
    .find((i) => (post[`prices-${i}-occupancy_key`] || '') === key);
  return n === undefined ? undefined : post[`prices-${n}-${col}`];
};

test('B7 · applyBulk — 러너의 가격 수정 단계로 넣을 값만 친 뒤 한 번 저장하고, 결과에는 주소가 없다', async () => {
  const page = erpPage();
  const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
  assert.equal(r.ok, true, r.error);
  assert.equal(r.saved, true);
  assert.equal(r.pressed, true);
  assert.equal(r.no, 1);
  assert.equal(r.clicks.bulkSave, 1);
  assert.ok(charsOf(r) <= 800, `답이 JSON 으로 800자 안: ${charsOf(r)}`);
  assert.equal(page.log.posts.length, 1);
  const post = page.log.posts[0];
  assert.equal(post['prices-0-price'], '125000.00');
  assert.equal(post['prices-0-original_price'], undefined, '적지 않은 칸은 비워 보내 그대로 둔다');
  assert.equal(post.date_selection_0, '2026-07-01');
  assert.equal(page.drawerOpen(), false);
  const text = JSON.stringify(r);
  for (const leak of LEAKS) assert.ok(!text.includes(leak), `결과에 ${leak} 가 남았다: ${text}`);
  page.w.close();
});

test('B7 · applyBulk — 화면이 「기준 조합만 입력」 으로 열려도 「조합마다 직접 입력」 으로 바꿔 줄마다 값을 친다', async () => {
  const page = erpPage({ bulkReview: runFixture('calendar-bulk--price-link-step2.html') });
  const step = Object.assign({}, BULK, { dates: ['2026-07-01', '2026-07-02'], rows: [
    { occupancy: 'A2', nights: 1, sell: '160000', list: null, supply: null },
    { occupancy: 'A3', nights: 1, sell: '190000', list: null, supply: '120000' }] });
  const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, step)));
  assert.equal(r.saved, true, r.error);
  const post = page.log.posts[0];
  assert.equal(post.link_mode, 'manual');
  assert.equal(priceOf(post, 'A2', 'price'), '160000');
  assert.equal(priceOf(post, 'A3', 'price'), '190000');
  assert.equal(priceOf(post, 'A3', 'net_amount'), '120000');
  assert.equal(priceOf(post, '', 'price'), undefined, '단계에 없는 줄은 건드리지 않는다');
  assert.ok(page.log.reached.includes('change:link_mode_pick'));
  page.w.close();
});

test('B7 · applyBulk — 드로어 표에 없는 줄이 필요한 단계는 저장하지 않고 까닭을 말한다', async () => {
  const page = erpPage();
  const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, Object.assign({}, BULK, { rows: [{ occupancy: 'A2', nights: 1, sell: '150000' }] }))));
  assert.equal(r.ok, false);
  assert.equal(r.saved, false);
  assert.equal(r.pressed, false);
  assert.equal(r.refused, true);
  assert.match(r.error, /드로어 표에 없는 줄/);
  assert.deepEqual(page.log.posts, []);
  assert.equal(page.drawerOpen(), false, '거절한 뒤 드로어를 닫았다');
  page.w.close();
});

test('B7 · applyBulk — 저장을 다시 누르지 않는다(러너의 CSRF 재전송도 벽이 막는다)', async () => {
  const page = erpPage({ onBulkSave: '403' });
  page.w.stayRun.config({ waitMs: 1000 });
  const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
  assert.equal(r.saved, 'unknown', '눌렀지만 확인하지 못했으니 「알 수 없음」');
  assert.equal(r.pressed, true);
  assert.equal(page.log.posts.length, 1, '저장 요청은 한 번만 나갔다');
  assert.ok(r.blocked.some((b) => /다시 누르지 않습니다/.test(b.why)), JSON.stringify(r.blocked));
  assert.match(r.error, /다시 누르지 않았습니다/);
  assert.equal(page.drawerOpen(), false);
  page.w.close();
});

test('B7 · applyBulk — 드로어가 다른 객실·날짜를 열었으면 칸을 치기 전에 멈추고 저장 단추를 누르지 않는다', async () => {
  for (const review of [runFixture('calendar-bulk--price-step2.html').replace('name="rate_plan" value="{rate_plan:1}"', 'name="rate_plan" value="{rate_plan:2}"'),
    runFixture('calendar-bulk--price-step2.html').replace('<tbody><tr><td>2026-07-01</td>', '<tbody><tr><td>2026-07-02</td>')]) {
    const page = erpPage({ bulkReview: review });
    page.w.stayRun.config({ waitMs: 1000 });
    const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
    assert.equal(r.saved, false);
    assert.equal(r.pressed, false);
    assert.ok(!r.clicks.bulkSave);
    assert.deepEqual(page.log.posts, []);
    assert.match(r.error, /다른 객실·요금제|드로어의 날짜/);
    page.w.close();
  }
});

test('T7 · applyBulk — 떨어진 날들도 그 날들만 골라 한 번에 저장한다(날은 숨은 구간 줄이 정한다)', async () => {
  const page = erpPage({ echoDays: true });
  const step = Object.assign({}, BULK, { dates: ['2026-07-01', '2026-07-03', '2026-07-04', '2026-07-10'] });
  const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, step)));
  assert.equal(r.saved, true, r.error);
  assert.equal(r.clicks.bulkSave, 1);
  assert.equal(page.log.posts.length, 1, '저장 한 번');
  assert.equal(page.log.posts[0].date_selection_0, '2026-07-01\n2026-07-03 ~ 2026-07-04\n2026-07-10', '고른 날만 — 7/2 · 7/5~9 는 고르지 않았다');
  assert.equal(page.log.posts[0]['prices-0-price'], '125000.00');
  page.w.close();
});

test('B7 · applyBulk — 차례가 어긋나거나 겹친 날짜 · 금액 없는 줄은 화면을 만지기 전에 거절한다', async () => {
  const page = erpPage();
  for (const [step, why] of [[Object.assign({}, BULK, { dates: ['2026-07-03', '2026-07-01'] }), /겹치지 않는 오름차순/],
    [Object.assign({}, BULK, { dates: ['2026-07-01', '2026-07-01'] }), /겹치지 않는 오름차순/],
    [Object.assign({}, BULK, { rows: [{ occupancy: '', nights: 1 }] }), /넣을 금액이 없거나/], [Object.assign({}, BULK, { rows: [{ occupancy: '', nights: 1, sell: '1,000' }] }), /숫자가 아닙니다/]]) {
    const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, step)));
    assert.equal(r.ok, false);
    assert.match(r.error, why);
    assert.deepEqual(r.clicks, {});
  }
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});

test('B7 · applyCell — 연 셀 창의 날짜가 단계와 다르면 아무것도 만지지 않고 거절한다', async () => {
  const page = erpPage({ cell: { date: '2026-07-02' } });
  let atClose = null;
  page.doc.addEventListener('click', (e) => {
    if (e.target.matches('#stay_cell_edit [data-stay-action="close"]')) atClose = page.doc.querySelector('tr[data-stay-row="501"] [name="original_price"]').value;
  }, true);
  const r = plain(await page.w.stayPrice.applyCell(inPage(page.w, CELL)));
  assert.equal(r.ok, false);
  assert.equal(r.refused, true);
  assert.match(r.error, /날짜\(2026-07-02\)가 저장할 날짜\(2026-07-01\)와 달라/);
  assert.equal(atClose, '150000.00', '칸에 손대지 않고 닫았다');
  assert.deepEqual(page.log.posts, []);
  assert.ok(!r.clicks.cellSave && r.clicks.cellClose === 1);
  assert.equal(page.doc.getElementById('stay_cell_edit'), null, '셀 창을 닫았다');
  page.w.close();
});

test('B7 · applyCell — 인원·박수 줄을 찾아 정가를 비우고 그 줄의 [저장] 을 한 번 눌러 확인한 뒤 닫는다', async () => {
  const page = erpPage();
  const r = plain(await page.w.stayPrice.applyCell(inPage(page.w, CELL)));
  assert.equal(r.ok, true, r.error);
  assert.equal(r.saved, true);
  assert.deepEqual([r.clicks.cellOpen, r.clicks.cellSave, r.clicks.cellClose], [1, 1, 1]);
  assert.equal(page.log.posts.length, 1);
  assert.equal(page.log.posts[0].row, '501');
  assert.equal(page.log.posts[0].original_price, '');
  assert.equal(page.log.posts[0].net_amount, '90000.00', '다른 칸은 그대로 실린다');
  assert.equal(page.doc.getElementById('stay_cell_edit'), null);
  page.w.close();

  const two = erpPage();
  const r2 = plain(await two.w.stayPrice.applyCell(inPage(two.w, Object.assign({}, CELL, { occupancy: 'A2', clear: [], set: { supply: '100000.00' } }))));
  assert.equal(r2.saved, true, r2.error);
  assert.equal(two.log.posts[0].row, '502');
  assert.equal(two.log.posts[0].net_amount, '100000.00');
  two.w.close();
});

test('B7 · applyCell — 화면에 없는 줄은 거절하고, 저장이 거절되면 다시 누르지 않는다', async () => {
  const page = erpPage();
  const r = plain(await page.w.stayPrice.applyCell(inPage(page.w, Object.assign({}, CELL, { occupancy: 'A3' }))));
  assert.equal(r.refused, true);
  assert.match(r.error, /`A3 · 1박 이상` 줄이 없어/);
  assert.deepEqual(page.log.posts, []);
  page.w.close();

  const bad = erpPage({ cellSave: 'error' });
  const r2 = plain(await bad.w.stayPrice.applyCell(inPage(bad.w, CELL)));
  assert.equal(r2.saved, false);
  assert.equal(r2.pressed, true);
  assert.match(r2.error, /거절했습니다 — 정가는 판매가보다/);
  assert.equal(bad.log.posts.length, 1);
  assert.equal(bad.doc.getElementById('stay_cell_edit'), null);
  bad.w.close();

  const sell = erpPage();
  const r3 = plain(await sell.w.stayPrice.applyCell(inPage(sell.w, Object.assign({}, CELL, { clear: ['sell'] }))));
  assert.match(r3.error, /정가\(list\)·공급 원가\(supply\)만/);
  assert.deepEqual(sell.log.reached, []);
  sell.w.close();
});

test('B7 · applyCell — 다른 달의 날짜면 달력을 그 달로 넘긴 뒤 그 날짜 칸을 연다', async () => {
  const page = erpPage({ cell: { date: '2026-09-01' } });
  const r = plain(await page.w.stayPrice.applyCell(inPage(page.w, Object.assign({}, CELL, { date: '2026-09-01' }))));
  assert.equal(r.saved, true, r.error);
  assert.equal(r.clicks.month, 2);
  assert.equal(page.doc.getElementById('stay_calendar').getAttribute('data-cal-month'), '2026-09');
  page.w.close();
});

test('U1 · applyBulk — 친 값이 칸에 그대로 남지 않으면(화면이 고쳐 쓰거나 받지 않음) 저장 단추를 누르지 않는다', async () => {
  for (const [shown, why] of [['1250.00', '화면이 금액을 고쳐 쓴다'], ['', '화면이 글자를 받지 않는다']]) {
    const page = erpPage();
    // ERP 화면 스크립트가 친 뒤 한 틱 늦게 칸을 고쳐 쓰는 것처럼 — 칠 때의 확인은 지나고, 저장 직전의 되읽기에서만 드러난다
    page.doc.addEventListener('change', (e) => {
      if (/^prices-\d+-price$/.test(e.target.name || '')) page.w.setTimeout(() => { e.target.value = shown; }, 0);
    });
    const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
    assert.equal(r.saved, false, why);
    assert.equal(r.pressed, false, why);
    assert.equal(r.refused, true, why);
    assert.match(r.error, /넣은 값을 다시 읽으니 달라 저장하지 않았습니다/, why);
    assert.ok(!r.clicks.bulkSave, why);
    assert.deepEqual(page.log.posts, [], `${why} — 저장 요청이 나가지 않았다`);
    page.w.close();
  }
});

test('U1 · applyBulk — ② 의 숨은 날짜 구간이 단계와 다르면(보이는 날 목록은 맞아도) 칸을 하나도 치지 않는다', async () => {
  // 서버가 ② 를 다른 구간으로 되싣는다 — 상태 표의 날 목록(7/1)은 물은 그대로인데 저장이 믿는 date_selection_0 만 다르다.
  // 받침의 [다음] 듣개가 ② 를 그린 바로 뒤(같은 클릭)에 숨은 칸을 바꾼다
  const page = erpPage();
  const typed = [];
  page.doc.addEventListener('input', (e) => { if (/^prices-/.test(e.target.name || '')) typed.push(e.target.name); }, true);
  page.doc.addEventListener('click', (e) => {
    if (!e.target.closest('[data-stay-screen="calendar-bulk"]') || !e.target.matches('[data-stay-action="next"]')) return;
    page.doc.querySelector('[data-stay-screen="calendar-bulk"] input[type="hidden"][name="date_selection_0"]').value = '2026-07-01 ~ 2026-07-02';
  });
  const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
  assert.equal(r.saved, false);
  assert.equal(r.pressed, false);
  assert.match(r.error, /드로어가 다른 날짜를 골랐습니다/);
  assert.deepEqual(typed, [], '가격 칸에 아무것도 치지 않았다');
  assert.ok(!r.clicks.bulkSave);
  assert.deepEqual(page.log.posts, []);
  page.w.close();
});
