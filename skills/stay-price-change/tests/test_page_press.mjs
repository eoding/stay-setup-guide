// P1~P3 누르기 — htmx 가 갈아 끼운 조각은 htmx 가 연결하기 몇 ms 전에 먼저 보인다(2026-11-20 로컬 ERP 실측: 달을 넘긴 그 틱에
// 새 [선택 날짜 가격 수정] 을 눌러 아무 일도 없었고, 2차 실험의 첫 저장은 칩을 바꾼 뒤 같은 자리에서 멈췄다). 이 파일의 시험은
// 그 틈을 받침(`lateWire`)으로 만들고, 작업이 연결된 단추를 한 번만 누르는지 본다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { erpPage, inPage, plain, runFixture, PAGE, OFFER, HOTEL } from './page_harness.mjs';

const BULK = { no: 1, hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', dates: ['2026-07-01'], rows: [{ occupancy: '', nights: 1, sell: '125000.00', list: null, supply: null }] };
const CELL = { no: 2, hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', date: '2026-08-01', occupancy: '', nights: 1, clear: ['list'] };
const READ = { hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', weekdays: ['월', '화', '수', '목', '금', '토', '일'] };
// 다른 칩이 골라진 채로 연다 — 작업이 [디럭스 · 조식 포함] 칩을 눌러 달력을 갈아야 한다(2차 실험과 같은 길)
const startOn = (name) => (html) => html.replace(/<button\b[^>]*data-stay-entity="rate_plan"[^>]*>/g, (tag) =>
  tag.replace(/stay-btn--(primary|ghost)/, tag.includes(`data-stay-name="${name}"`) ? 'stay-btn--primary' : 'stay-btn--ghost'));
// 요청 수가 그 틈을 덮는 페이지(htmx 4 그대로)와 덮지 않는 페이지 — 어느 쪽이든 단추의 연결 표식을 본다
const LATE = [['요청이 연결 뒤에 끝난다', {}], ['요청이 연결 전에 끝난다', { untracked: true }]];

for (const [how, extra] of LATE) {
  test(`P1·P3 · 칩을 눌러 갈린 달력의 [선택 날짜 가격 수정] 이 5ms 늦게 연결돼도 드로어를 열고 한 번 저장한다(${how})`, async () => {
    const page = erpPage({ panelEdit: startOn('디럭스 · 룸온리'), lateWire: Object.assign({ ms: 5, on: ['calendar'] }, extra) });
    const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
    assert.equal(r.ok, true, r.error);
    assert.equal(r.saved, true);
    assert.deepEqual([r.clicks.chip, r.clicks.bulkOpen, r.clicks.bulkSave], [1, 1, 1], JSON.stringify(r.clicks));
    assert.deepEqual(page.log.dead, [], '연결되기 전의 단추를 누르지 않았다');
    assert.equal(page.log.posts.length, 1);
    page.w.close();
  });
}

test('P1·P3 · 실측 순서 — 칩과 달을 바꾼 뒤 드로어를 여는 읽기 여섯 번이 모두 된다(달력은 5ms 늦게 연결된다)', async () => {
  const page = erpPage({ panelEdit: startOn('디럭스 · 룸온리'), lateWire: { ms: 5, on: ['calendar'] }, echoDays: true });
  for (const month of ['2026-08', '2026-07', '2026-08', '2026-07', '2026-08', '2026-07']) {
    const r = plain(await page.w.stayPrice.readPair(inPage(page.w, Object.assign({}, READ, { from: `${month}-01`, to: `${month}-01` }))));
    assert.equal(r.ok, true, `${month}: ${r.error}`);
    assert.equal(r.clicks.month, 1, `${month}: 달을 넘겼다`);
    assert.equal(r.clicks.bulkOpen, 1, `${month}: 드로어를 열었다`);
    assert.equal(r.rest, true, `${month}: 쉬는 화면으로 답했다`);
  }
  assert.deepEqual(page.log.dead, []);
  assert.deepEqual(page.log.posts, [], '읽기는 저장하지 않는다');
  page.w.close();
});

test('P1·P3 · 달을 넘긴 뒤 늦게 연결되는 날짜 칸을 열고, 저장으로 갈린 셀 창의 [닫기] 도 연결된 뒤 누른다', async () => {
  for (const [how, extra] of LATE) {
    const page = erpPage({ cell: { date: '2026-08-01' }, lateWire: Object.assign({ ms: 5, on: ['calendar', 'cell'] }, extra) });
    const r = plain(await page.w.stayPrice.applyCell(inPage(page.w, CELL)));
    assert.equal(r.ok, true, `${how}: ${r.error}`);
    assert.equal(r.saved, true, how);
    assert.deepEqual([r.clicks.month, r.clicks.cellOpen, r.clicks.cellSave, r.clicks.cellClose], [1, 1, 1, 1], `${how}: ${JSON.stringify(r.clicks)}`);
    assert.deepEqual(page.log.dead, [], how);
    assert.equal(page.log.posts.length, 1, how);
    assert.equal(page.doc.getElementById('stay_cell_edit'), null, `${how}: 셀 창을 닫았다`);
    page.w.close();
  }
});

// 「기준 조합만 입력」 으로 열리는 ② (캡처는 7/1 · 7/2 두 날, 조합 A2 · A3)
const LINKED = Object.assign({}, BULK, { dates: ['2026-07-01', '2026-07-02'], rows: [{ occupancy: 'A2', nights: 1, sell: '160000', list: null, supply: null }] });
// ② 의 저장 단추 앞에는 러너 fill 이 칸마다 60ms 쉰다 — 5ms 틈은 그 사이에 저절로 닫히므로 저장 단추의 기다림을 보려면 틈을 400ms 로 연다
for (const [what, ms, late, opts, step] of [
  ['드로어 ① 의 [다음]', 5, ['drawer'], {}, BULK],
  ['[다음] 뒤 ② 의 「연동 방식」 과 다시 그린 ② 의 저장', 5, ['step'], { bulkReview: runFixture('calendar-bulk--price-link-step2.html') }, LINKED],
  ['[다음] 뒤 ② 의 [입력한 가격 적용]', 400, ['step'], {}, BULK]
]) {
  test(`P1·P2 · 단계가 바뀐 드로어 — ${what} 이 ${ms}ms 늦게 연결돼도 연결된 뒤 한 번씩만 누른다`, async () => {
    for (const [how, extra] of LATE) {
      const page = erpPage(Object.assign({ lateWire: Object.assign({ ms, on: late }, extra) }, opts));
      page.w.stayRun.config({ waitMs: 1000 });
      const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, step)));
      assert.equal(r.ok, true, `${how}: ${r.error}`);
      assert.equal(r.saved, true, how);
      assert.equal(r.clicks.bulkNext, 1, how);
      assert.equal(r.clicks.bulkSave, 1, `${how}: 저장은 한 번`);
      assert.equal(page.log.posts.length, 1, `${how}: 저장 요청 하나`);
      assert.deepEqual(page.log.dead, [], how);
      if (opts.bulkReview) assert.equal(page.log.posts[0].link_mode, 'manual', how);
      page.w.close();
    }
  });
}

test('P1 · 끝내 연결되지 않는 단추는 누르지 않고, 어느 단추가 왜 준비되지 않았는지 말하며 멈춘다', async () => {
  const page = erpPage();
  page.doc.querySelector('#stay_calendar [data-calendar-bulk-action="price"]').removeAttribute('data-htmx-powered');
  page.w.stayPrice.config({ budgetMs: 1200 });
  const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
  assert.equal(r.ok, false);
  assert.match(r.error, /^\[선택 날짜 가격 수정\] 이 준비되지 않았습니다\(htmx 가 아직 연결하지 않았습니다\) — 누르지 않았습니다/);
  assert.equal(r.saved, false);
  assert.equal(r.pressed, false);
  assert.ok(!r.clicks.bulkOpen, JSON.stringify(r.clicks));
  assert.deepEqual(page.log.reached, [], '아무것도 누르지 않았다');
  assert.deepEqual(page.log.posts, []);
  page.w.close();
});

test('P1 · stay_price.js 의 클릭은 press 안의 하나뿐이고, 러너의 누르는 부품은 press 를 지나서만 부른다', () => {
  const code = PAGE.split('\n').filter((line) => !/^\s*(\/\/|\/\*|\*)/.test(line));   // 주석 줄은 뺀다
  const clicks = code.filter((line) => /\.click\s*\(/.test(line));
  assert.equal(clicks.length, 1, `클릭이 한 곳이어야 한다:\n${clicks.join('\n')}`);
  const start = PAGE.indexOf('async function press(');
  const end = PAGE.indexOf('\n  }\n', start);
  const at = PAGE.indexOf(clicks[0]);
  assert.ok(start > 0 && at > start && at < end, `그 클릭은 press 안에 있다:\n${clicks[0]}`);
  // 안에서 바로 누르는 러너 부품 — 이 파일은 부르지 않는다(press 로 같은 일을 한다)
  for (const name of ['calSelectOffer', 'calSelectChip', 'calEnsureCoord', 'calCheck', 'calSetPeriod', 'runCalendarPriceStep', 'stayRun.tab', 'stayRun.close']) {
    assert.ok(!code.some((line) => line.includes(`${name}(`)), `${name} 을 부르지 않는다`);
  }
  // 그 자리에서 단추를 누르거나 바꾸는 러너 부품 — press 의 act 로만 부른다(같은 줄에 press 가 있다)
  for (const name of ['stayRun.submit(', 'calRedraw(']) {
    const lines = code.filter((line) => line.includes(name));
    assert.ok(lines.length > 0, name);
    for (const line of lines) assert.match(line, /\bpress\(/, `${name} 은 press 의 act 로만 부른다:\n${line}`);
  }
});
