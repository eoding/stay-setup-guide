// B2 클릭 벽 — 작업마다 허용 목록 하나, 나머지는 막고 적는다. 러너 코드가 직접 부르는 `.click()` 도 걸린다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { erpPage, plain, runFixture, cellWindow } from './page_harness.mjs';

const OPS = ['readPair', 'readReserved', 'applyBulk', 'applyCell'];
const UNDO = '<button type="button" class="stay-btn stay-btn--secondary" data-stay-action="undo" data-calendar-adjust-action="undo" hx-post="/stay/1/calendar/adjust/7/undo/" hx-confirm="되돌립니다">되돌리기</button>';

// 화면에 그려 둔 뒤 누를 과녁 — [이름, 그릴 드로어 조각(없으면 그대로), 고르개]
const NEVER_TARGETS = [
  ['판매 마감 창', null, '#stay_calendar [data-calendar-bulk-action="close"]'],
  ['마감 해제 창', null, '#stay_calendar [data-calendar-bulk-action="reopen"]'],
  ['[가감 적용]', runFixture('calendar-adjust--step2.html'), '[data-stay-screen="calendar-adjust"] [data-stay-action="save"]'],
  ['[되돌리기]', runFixture('calendar-adjust--applied.html').replace('</div>\n</div>', UNDO + '</div>\n</div>'), '[data-calendar-adjust-action="undo"]'],
  ['[적용 기록 내려받기]', runFixture('calendar-adjust--applied.html'), '[data-calendar-adjust-action="log"]'],
  ['최근 가감의 [적용 기록 내려받기]', runFixture('calendar-adjust--step1-history.html'), '[data-stay-card="adjust_history"] [data-calendar-adjust-action="log"]'],
  ['[N월 닫기]', null, '[data-stay-action="close_month"]'],
  ['삭제', null, '#stay_tab_offers [data-stay-action="delete"]'],
  ['보관', null, '[data-stay-action="archive"]'],
  ['판매 종료', null, '[data-stay-action="end"]'],
  ['판매 시작', null, '[data-stay-action="activate"]'],
  ['다른 탭', null, 'ul.tab-container a[data-stay-tab="offers"]'],
  ['판매 마감 ② 의 저장', runFixture('calendar-bulk--close-step2.html'), '[data-stay-screen="calendar-bulk"] [data-stay-action="save"]']
];

test('B2 · 금지 단추는 어느 작업에서도 막히고, 무엇을 막았는지 적힌다', async () => {
  for (const op of OPS) {
    for (const [name, drawer, sel] of NEVER_TARGETS) {
      const page = erpPage();
      if (drawer) page.render(drawer);
      const el = page.doc.querySelector(sel);
      assert.ok(el, `${name}: 과녁이 화면에 있다`);
      const target = el.querySelector('span') || el;      // 단추 안의 글자를 눌러도 단추로 본다
      const seen = plain(await page.w.stayPrice.guard(op, async () => { target.click(); }));
      assert.equal(seen.blocked.length, 1, `${op} · ${name}: 막혔다`);
      assert.deepEqual(seen.clicks, [], `${op} · ${name}: 통과한 클릭이 없다`);
      assert.deepEqual(page.log.reached, [], `${op} · ${name}: 화면(서버)까지 닿지 않았다`);
      assert.ok(seen.blocked[0].control && seen.blocked[0].why, `${op} · ${name}: 막은 단추와 까닭을 적는다`);
      page.w.close();
    }
  }
});

test('B2 · 읽는 작업에는 저장 단추가 없다 — 가격 수정 ② 의 [입력한 가격 적용]·셀 창 [저장] 도 막힌다', async () => {
  for (const op of ['readPair', 'readReserved']) {
    const page = erpPage();
    page.render(runFixture('calendar-bulk--price-step2.html'));
    const seen = plain(await page.w.stayPrice.guard(op, async () => {
      page.doc.querySelector('[data-stay-screen="calendar-bulk"] [data-stay-action="save"]').click();
      page.doc.getElementById('stay_cell_slot').innerHTML = cellWindow();
      page.doc.querySelector('[data-stay-action="save_cell"]').click();
    }, { chip: '디럭스 · 조식 포함', ratePlanId: '{rate_plan:1}', ranges: ['2026-07-01'], row: '501' }));
    assert.equal(seen.blocked.length, 2, op);
    assert.deepEqual(page.log.reached, [], op);
    page.w.close();
  }
});

test('B2 · 허용 목록의 단추는 지나가고, 작업이 고른 칩이 아니면 같은 종류여도 막힌다', async () => {
  const page = erpPage();
  const q = (sel) => page.doc.querySelector(sel);
  const seen = plain(await page.w.stayPrice.guard('readPair', async () => {
    q('ul.tab-container a[data-stay-tab="calendar"]').click();
    q('[data-stay-name="디럭스 · 룸온리"]').click();
    q('[data-stay-name="스위트 · 조식 포함"]').click();
    q('#stay_calendar [data-calendar-bulk-action="price"]').click();
    page.doc.querySelector('[data-stay-screen="calendar-bulk"] input[name="weekdays"]').click();
  }, { chip: '디럭스 · 룸온리' }));
  assert.deepEqual(seen.clicks, ['tab', 'chip', 'bulkOpen', 'bulkDay']);
  assert.equal(seen.blocked.length, 1);
  assert.match(seen.blocked[0].control, /스위트 · 조식 포함/);
  assert.match(seen.blocked[0].why, /고른 대상이 아닙니다/);
  assert.ok(q('[data-stay-name="디럭스 · 룸온리"]').className.includes('--primary'), '허용된 칩 클릭은 화면에 닿았다');
  page.w.close();
});

test('B2 · 표식 없이 글자만 같은 단추, ERP 가 나중에 더한 단추는 지나가지 못한다', async () => {
  const page = erpPage();
  page.render(runFixture('calendar-bulk--price-step2.html'));
  page.doc.getElementById('stay_calendar').insertAdjacentHTML('beforeend', '<button type="button" id="fake">선택 날짜 가격 수정</button>');
  page.doc.querySelector('.stay-drawer__footer').insertAdjacentHTML('beforeend', '<button type="button" data-stay-action="publish" id="later">바로 공개</button>');
  const seen = plain(await page.w.stayPrice.guard('applyBulk', async () => {
    page.doc.getElementById('fake').click();
    page.doc.getElementById('later').click();
    page.doc.querySelector('.stay-drawer__close').click();
  }, { chip: '디럭스 · 조식 포함', ratePlanId: '{rate_plan:1}', ranges: ['2026-07-01'] }));
  assert.equal(seen.blocked.length, 3);
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});

test('B2 · 러너 코드가 직접 누르는 .click() 도 벽에 걸린다 — 읽는 작업의 벽 안에서는 러너의 저장이 막힌다', async () => {
  const page = erpPage();
  page.w.stayRun.config({ waitMs: 1000 });
  const F = (label, kind, value, extra = {}) => Object.assign({ label, kind, raw_value: value }, kind === 'multi' ? { values: value } : { value }, extra);
  const step = { no: 9, kind: '선택 날짜 가격 수정', title: '시험', fields: [
    F('오퍼', 'select', '〈오퍼 관리용 이름〉'), F('객실', 'select', '디럭스'), F('요금제', 'select', '조식 포함'),
    F('시작일', 'typed', '2026-07-01'), F('종료일', 'typed', '2026-07-01'), F('요일', 'multi', ['월', '화', '수', '목', '금', '토', '일']),
    F('연동 방식', 'select', '조합마다 직접 입력'),
    F('인원 무관 · 1박 이상 · 판매가', 'typed', '125000', { field: 'prices', occupancy_key: '', los_nights: 1, field_col: 'price' })] };
  let runner;
  const seen = plain(await page.w.stayPrice.guard('readPair', async () => {
    runner = plain(await page.w.runCalendarPriceStep(step, {}));
    const other = page.doc.querySelector('[data-stay-name="스위트 · 룸온리"]');
    plain(await page.w.calSelectChip(other, '스위트 · 룸온리'));
  }, { chip: '디럭스 · 조식 포함' }));
  assert.deepEqual(page.log.posts, [], '저장 요청이 나가지 않았다');
  assert.ok(seen.clicks.includes('bulkOpen') && seen.clicks.includes('bulkNext'), '읽기에 필요한 러너의 클릭은 지나갔다');
  assert.ok(seen.blocked.some((b) => /data-stay-action=save/.test(b.control)), '러너의 저장 클릭이 막혔다');
  assert.ok(seen.blocked.some((b) => /스위트 · 룸온리/.test(b.control)), '러너의 다른 칩 클릭이 막혔다');
  assert.ok(runner.error, '러너는 저장하지 못했다고 답한다');
  page.w.close();
});

test('B2 · 저장 단추는 그 객실·날짜일 때 한 번만 지나간다', async () => {
  const pins = { chip: '디럭스 · 조식 포함', ratePlanId: '{rate_plan:1}', ranges: ['2026-07-01'] };
  const page = erpPage();
  const save = () => page.doc.querySelector('[data-stay-screen="calendar-bulk"] [data-stay-action="save"]').click();
  const seen = plain(await page.w.stayPrice.guard('applyBulk', async () => {
    page.render(runFixture('calendar-bulk--price-step2.html')); save();
    page.render(runFixture('calendar-bulk--price-step2.html')); save();
  }, pins));
  assert.deepEqual(seen.clicks, ['bulkSave']);
  assert.match(seen.blocked[0].why, /다시 누르지 않습니다/);
  assert.equal(page.log.posts.length, 1);
  for (const wrong of [{ ratePlanId: '{rate_plan:2}' }, { ranges: ['2026-07-01 ~ 2026-07-02'] }, { ratePlanId: undefined }]) {
    const other = plain(await page.w.stayPrice.guard('applyBulk', async () => {
      page.render(runFixture('calendar-bulk--price-step2.html')); save();
    }, Object.assign({}, pins, wrong)));
    assert.deepEqual(other.clicks, [], JSON.stringify(wrong));
    assert.match(other.blocked[0].why, /고른 대상이 아닙니다/);
  }
  assert.equal(page.log.posts.length, 1, '다른 객실·날짜를 연 드로어에서는 저장이 나가지 않았다');
  page.w.close();
});

test('B2 · 폼 제출도 허용된 단추가 보낸 것이 아니면 막고, 작업이 끝나면 벽을 걷는다', async () => {
  const page = erpPage();
  page.doc.body.insertAdjacentHTML('beforeend', '<form id="f"><input name="q"><button type="submit" id="go">보내기</button></form>');
  const form = page.doc.getElementById('f');
  const seen = plain(await page.w.stayPrice.guard('applyBulk', async () => {
    form.requestSubmit();
    page.doc.getElementById('go').click();
  }));
  assert.equal(seen.blocked.length, 2);
  assert.equal(page.log.submits, 0, '제출이 화면에 닿지 않았다');
  form.requestSubmit();
  assert.equal(page.log.submits, 1, '작업의 벽을 걷은 뒤에는 제출이 닿는다(브라우저가 낸 제출 사건)');
  page.w.stayPrice.standDown();
  page.doc.querySelector('ul.tab-container a[data-stay-tab="offers"]').click();
  assert.deepEqual(page.log.reached.slice(-1), ['stay-tab=offers'], '작업의 벽을 걷고 쉬는 벽도 내리면 클릭이 닿는다');
  page.w.close();
});

test('B2 · 허용 목록은 작업마다 표 한 장이고, 금지 목록은 브리프의 단추를 모두 덮는다', () => {
  const page = erpPage();
  const sp = page.w.stayPrice;
  assert.deepEqual(Object.keys(sp.ALLOW).sort(), OPS.slice().sort());
  for (const op of OPS) for (const name of sp.ALLOW[op]) assert.ok(sp.CONTROLS[name], `${op}: ${name} 이 표에 있다`);
  for (const op of ['readPair', 'readReserved']) assert.ok(!sp.ALLOW[op].some((name) => /Save$/.test(name)), `${op} 에는 저장이 없다`);
  for (const name of Object.keys(sp.CONTROLS)) assert.ok(!/[가-힣]/.test(sp.CONTROLS[name].sel), `${name}: 고르개에 글자가 없다`);
  page.w.close();
});
