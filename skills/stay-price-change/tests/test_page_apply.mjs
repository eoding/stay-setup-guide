// B7 적용 — applyBulk 은 러너의 runCalendarPriceStep 으로 「조합마다 직접 입력」 저장 한 번, applyCell 은 셀 창 저장 한 번.
// 둘 다 저장을 다시 누르지 않고, 화면에 없는 줄이나 다른 날짜의 창이면 손대지 않고 거절한다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { erpPage, inPage, plain, runFixture, charsOf, bulkWas, noCell, cellWas, OFFER, HOTEL } from './page_harness.mjs';

const ROW = { occupancy: '', nights: 1, sell: '125000.00', list: null, supply: null };
const BULK = { no: 1, hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', dates: ['2026-07-01'], rows: [Object.assign({ was: bulkWas(['2026-07-01']) }, ROW)] };
const CELL = { no: 2, hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', date: '2026-07-01', occupancy: '', nights: 1, clear: ['list'], was: cellWas('') };
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
  const gone = ['2026-07-02', '2026-07-02', null, null, null];
  const step = Object.assign({}, BULK, { dates: ['2026-07-01', '2026-07-02'], rows: [
    { occupancy: 'A2', nights: 1, sell: '160000', list: null, supply: null, was: [['2026-07-01', '2026-07-01', '150000.00', null, null], gone] },
    { occupancy: 'A3', nights: 1, sell: '190000', list: null, supply: '120000', was: [['2026-07-01', '2026-07-01', '180000.00', null, null], gone] }] });
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
  const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, Object.assign({}, BULK, { rows: [{ occupancy: 'A2', nights: 1, sell: '150000', was: noCell(['2026-07-01']) }] }))));
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

test('A3 · applyBulk — 저장됨은 서버의 저장 표지로만 안다: 요청이 도는 사이 Esc 로 드로어가 닫히거나 페이지가 떠나면 「알 수 없음」', async () => {
  for (const mode of ['esc', 'reload']) {
    const page = erpPage({ onBulkSave: mode });
    page.w.stayPrice.config({ restMs: 600 });
    const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
    assert.equal(r.pressed, true, mode);
    assert.equal(r.saved, 'unknown', `${mode}: 드로어가 닫혔거나 페이지가 떠난 것은 저장의 표지가 아니다 — ${r.error}`);
    assert.equal(r.ok, false, mode);
    assert.match(r.error, /저장됐는지 알 수 없습니다/, mode);
    assert.equal(page.log.posts.length, 1, `${mode}: 한 번만 눌렀다`);
    page.w.close();
  }
  const late = erpPage({ onBulkSave: 'escLate' });
  const r = plain(await late.w.stayPrice.applyBulk(inPage(late.w, BULK)));
  assert.equal(r.saved, true, `Esc 로 닫힌 뒤에라도 서버의 저장 표지가 오면 저장된 것 — ${r.error}`);
  late.w.close();
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
  const dates = ['2026-07-01', '2026-07-03', '2026-07-04', '2026-07-10'];
  const step = Object.assign({}, BULK, { dates, rows: [Object.assign({ was: bulkWas(dates) }, ROW)] });
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
});

test('A6 · applyCell — 셀 창은 비우기만 한다(넣는 값 `set` 은 받지 않고 화면을 만지지 않는다)', async () => {
  const page = erpPage();
  const r = plain(await page.w.stayPrice.applyCell(inPage(page.w, Object.assign({}, CELL, { occupancy: 'A2', clear: [], set: { supply: '100000.00' } }))));
  assert.equal(r.ok, false);
  assert.match(r.error, /비울 칸이 없습니다/);
  assert.deepEqual(page.log.reached, []);
  assert.deepEqual(page.log.posts, []);
  page.w.close();
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

test('A5 · 사람이 연 드로어가 있으면 작업은 그것을 닫지 않고 시작하지 않는다 · 이 도우미가 닫지 못하고 남긴 드로어는 다음 작업이 닫는다', async () => {
  const ALL_WEEK = ['월', '화', '수', '목', '금', '토', '일'];
  const READ = { hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01', weekdays: ALL_WEEK };
  const page = erpPage();
  page.render('<div data-stay-screen="season"><input name="name" value="사람이 치던 시즌"></div>');
  for (const [op, value] of [['readPair', READ], ['applyBulk', BULK], ['look', {}]]) {
    const r = plain(await page.w.stayPrice[op](inPage(page.w, value)));
    assert.equal(r.ok, false, op);
    assert.match(r.error, /드로어가 열려 있습니다/, op);
    assert.deepEqual(r.clicks, {}, op);
    if (op === 'applyBulk') assert.deepEqual([r.saved, r.pressed], [false, false]);
  }
  assert.equal(page.drawerOpen(), true, '사람의 드로어는 그대로 열려 있다');
  assert.equal(page.doc.querySelector('#stay_drawer_body [name="name"]').value, '사람이 치던 시즌');
  assert.deepEqual(page.log.reached, []);
  page.w.close();

  // 이 도우미가 연 드로어를 닫지 못하고 끝났으면(ERP 가 닫기 신호를 받지 않음) 다음 작업은 그것을 닫고 시작한다
  const left = erpPage();
  const deaf = (e) => e.stopImmediatePropagation();
  left.w.addEventListener('stay-drawer-close', deaf, true);
  left.w.stayPrice.config({ restMs: 600 });
  const first = plain(await left.w.stayPrice.readPair(inPage(left.w, READ)));
  assert.match(first.error, /닫지 못했습니다/);
  assert.equal(left.drawerOpen(), true);
  left.w.removeEventListener('stay-drawer-close', deaf, true);
  const again = plain(await left.w.stayPrice.readPair(inPage(left.w, READ)));
  assert.equal(again.ok, true, again.error);
  assert.equal(left.drawerOpen(), false);
  left.w.close();
});

test('A1 · applyBulk — ② 의 「기존」 이 읽은 값과 다르면(읽을 때 120,000 · 지금 130,000) 한 칸도 치지 않고 누르지 않고, 그 날 · 줄 · 두 값을 대며 거절한다', async () => {
  const page = erpPage({ bulkReview: runFixture('calendar-bulk--price-step2.html').replace('<td class="stay-numeric">120000.00</td>', '<td class="stay-numeric">130000.00</td>') });
  const typed = [];
  page.doc.addEventListener('input', (e) => { if (/^prices-/.test(e.target.name || '')) typed.push(e.target.name); }, true);
  page.doc.addEventListener('change', (e) => { if (/^prices-/.test(e.target.name || '')) typed.push(e.target.name); }, true);
  const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
  assert.deepEqual([r.ok, r.refused, r.saved, r.pressed, r.moved], [false, true, false, false, 1], r.error);
  assert.match(r.error, /^ERP 화면의 값이 읽은 값과 다릅니다\(1칸\) — 2026-07-01 인원 무관 · 1박 이상 — 읽은 값 판매가 120000\.00 · 화면 판매가 130000\.00/);
  assert.deepEqual(r.differ, ['2026-07-01 인원 무관 · 1박 이상 — 읽은 값 판매가 120000.00 · 화면 판매가 130000.00']);
  assert.deepEqual(typed, [], '가격 칸에 아무것도 치지 않았다');
  assert.ok(!r.clicks.bulkSave);
  assert.deepEqual(page.log.posts, [], '저장 요청이 없다');
  assert.equal(page.drawerOpen(), false);
  page.w.close();
});

test('A1 · applyBulk — 칸이 생기거나 사라졌거나 정가 · 공급 원가만 달라도 거절하고, 같은 수를 다르게 적은 것(120,000.0)은 같은 값이다', async () => {
  const step2 = runFixture('calendar-bulk--price-step2.html');
  const existing = '<td class="stay-numeric">120000.00</td><td class="stay-numeric">없음</td><td class="stay-numeric">없음</td>';
  const cases = [
    [existing.replace('<td class="stay-numeric">없음</td><td', '<td class="stay-numeric">150000.00</td><td'), /읽은 값 판매가 120000\.00 · 화면 판매가 120000\.00 · 정가 150000\.00/],
    ['<td class="stay-numeric">가격 없음</td><td></td><td></td>', /읽은 값 판매가 120000\.00 · 화면 칸 없음/]
  ];
  for (const [shown, why] of cases) {
    const page = erpPage({ bulkReview: step2.replace(existing, shown) });
    const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
    assert.deepEqual([r.refused, r.saved, r.pressed, r.moved], [true, false, false, 1], r.error);
    assert.match(r.error, why);
    assert.deepEqual(page.log.posts, []);
    page.w.close();
  }
  const born = erpPage();
  const r = plain(await born.w.stayPrice.applyBulk(inPage(born.w, Object.assign({}, BULK, { rows: [Object.assign({}, BULK.rows[0], { was: noCell(['2026-07-01']) })] }))));
  assert.match(r.error, /읽은 값 칸 없음 · 화면 판매가 120000\.00/, '읽을 때 없던 칸이 생겼다');
  born.w.close();
  const same = erpPage({ bulkReview: step2.replace(existing, existing.replace('120000.00', '120,000.0')) });
  const ok = plain(await same.w.stayPrice.applyBulk(inPage(same.w, BULK)));
  assert.equal(ok.saved, true, ok.error);
  same.w.close();
});

test('A1 · applyBulk — `was` 가 없거나 단계의 날짜를 꼭 한 번씩 덮지 않으면 화면을 만지기 전에 거절한다', async () => {
  const page = erpPage();
  const rowWith = (was) => Object.assign({}, BULK, { dates: ['2026-07-01', '2026-07-03'], rows: [Object.assign({}, ROW, { was })] });
  for (const was of [undefined, [], [['2026-07-01', '2026-07-01', '1', null, null]], [['2026-07-01', '2026-07-03', '1', null]],
    [['2026-07-01', '2026-07-02', '1', null, null], ['2026-07-03', '2026-07-03', '1', null, null]], [['2026-07-01', '2026-07-03', '1,000', null, null]]]) {
    const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, rowWith(was))));
    assert.match(r.error, /`was`\(읽은 값\)가 단계의 날짜와 맞지 않습니다/, JSON.stringify(was));
    assert.deepEqual(r.clicks, {});
  }
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});

test('A1 · applyCell — 셀 창의 그 줄이 읽은 값과 다르면 칸을 비우지 않고 [저장] 도 누르지 않는다 · 쉼표로 적힌 같은 수는 같은 값이다', async () => {
  const page = erpPage();
  const r = plain(await page.w.stayPrice.applyCell(inPage(page.w, Object.assign({}, CELL, { was: ['120000.00', '140000.00', '90000.00'] }))));
  assert.deepEqual([r.refused, r.saved, r.pressed, r.moved], [true, false, false, 1], r.error);
  assert.match(r.error, /2026-07-01 인원 무관 · 1박 이상 — 읽은 값 판매가 120000\.00 · 정가 140000\.00 · 공급 원가 90000\.00 · 화면 판매가 120000\.00 · 정가 150000\.00/);
  assert.deepEqual(page.log.posts, []);
  assert.ok(!r.clicks.cellSave && r.clicks.cellClose === 1, '저장은 누르지 않고 창만 닫았다');
  page.w.close();

  const commas = erpPage({ cell: { rows: [{ pk: '501', key: '', label: '인원 무관 단일가', los: '1', price: '120,000.00', list: '150,000.00', net: '90,000.00' }] } });
  const ok = plain(await commas.w.stayPrice.applyCell(inPage(commas.w, CELL)));
  assert.equal(ok.saved, true, ok.error);
  commas.w.close();
  const bare = erpPage();
  const none = plain(await bare.w.stayPrice.applyCell(inPage(bare.w, Object.assign({}, CELL, { was: undefined }))));
  assert.match(none.error, /`was`\(읽은 값/);
  assert.deepEqual(bare.log.reached, []);
  bare.w.close();
});
