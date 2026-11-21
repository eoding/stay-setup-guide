// A1 저장은 누르는 순간 화면이 읽은 값 그대로일 때만 누른다 — 진짜 명령과 페이지로 한 바퀴: 미리보기 · 적용 직전 다시 읽기 · begin
// 뒤에 다른 사람이 ERP 에서 칸을 바꾸면, 그 칸을 쓰는 저장(첫 저장이든 뒤의 저장이든)은 치지도 누르지도 않고 거절하고, 명령은 그
// 단계를 저장 안 됨으로 적어 변경을 멈추고, 다시 읽은 값으로 check 가 그 칸이 움직였다고 말한다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { erpPage, runFixture, ownFixture, OFFER, HOTEL } from './page_harness.mjs';
import { priceFlow } from './price_flow.mjs';

const REVIEW = runFixture('calendar-bulk--price-step2.html').replaceAll('(공급 통화)', '(USD)');
// 예약 있는 날 읽기의 건너뛰는 칸 — 읽는 객실(디럭스)의 줄로만
const RESERVED = ownFixture('adjust-rejected.html').replaceAll('<td>스위트</td>', '<td>디럭스</td>');
const request = (dates) => ({ kind: 'change', hotel: HOTEL, offer: OFFER, rooms: [], rate_plans: [], pairs: [{ room: '디럭스', rate_plan: '조식 포함' }],
  dates, field: 'sell', operation: { kind: 'percent', value: '10' }, occupancies: [], nights: [], scale_child_surcharge: false, sentence: '판매가 10% 올려줘' });
// 캡처한 달력에서 판매일이 있는 날은 7/1 뿐이다 — 다른 날도 7/1 의 칸처럼 판매일이 있게 그린다
const openDays = (days) => (html) => {
  const first = /<td data-stay-date="2026-07-01">[\s\S]*?<\/td>/.exec(html)[0];
  return days.reduce((out, day) => out.replace(new RegExp(`<td data-stay-date="${day}">[\\s\\S]*?</td>`), first.replaceAll('2026-07-01', day).replace('7/1', `7/${Number(day.slice(8))}`)), html);
};

test('A1 · 미리보기 뒤 다른 사람이 그 칸을 130,000 으로 바꿨으면 첫 저장은 누르지 않고, 장부는 저장 안 됨 · 멈춤, check 는 칸이 움직였다고 한다', async () => {
  const page = erpPage({ bulkReview: REVIEW, adjustReview: RESERVED, bulkValues: { '2026-07-01': '120000.00' } });
  const flow = priceFlow(page);
  try {
    const { change, plan, short } = await flow.preview(request(['2026-07-01']));
    assert.equal(short.saves, 1, JSON.stringify(short));
    assert.equal((await flow.begin(change, plan)).status, 'applying');
    page.opts.bulkValues['2026-07-01'] = '130000.00';   // 적용 직전에 읽은 뒤, 누르기 전에 — 다른 사람이 ERP 에서 저장했다
    const [step, ...rest] = await flow.apply(change);
    assert.deepEqual(rest, [], '멈춘 뒤로는 부르지 않는다');
    assert.deepEqual([step.answer.refused, step.answer.saved, step.answer.pressed, step.answer.moved], [true, false, false, 1], step.answer.error);
    assert.match(step.answer.error, /2026-07-01 인원 무관 · 1박 이상 — 읽은 값 판매가 120000\.00 · 화면 판매가 130000\.00/);
    assert.deepEqual([step.recorded.saved, step.recorded.moved, step.recorded.status], [false, 1, 'stopped']);
    assert.deepEqual(page.log.posts, [], '저장 요청이 나가지 않았다 — 다른 사람의 130,000 이 그대로다');
    assert.equal(page.opts.bulkValues['2026-07-01'], '130000.00');
    assert.match(flow.cli('calls', '--change', change).error, /멈춰 있습니다/);
    const check = flow.must('check', '--change', change, '--snapshot', await flow.read(change));
    assert.equal(check.can_continue, false);
    assert.deepEqual(check.steps.map((s) => [s.no, s.ledger, s.seen, s.moved]), [[1, 'failed', 'changed', 1]]);
    assert.ok(check.why.some((why) => /1번째 저장.*미리보기 때 읽은 값과 다릅니다/.test(why)), JSON.stringify(check.why));
  } finally {
    flow.close();
    page.w.close();
  }
});

test('A1 · 첫 저장 뒤 다른 사람이 두 번째 저장의 칸을 바꿨으면 그 저장도 누르기 직전에 견주어 누르지 않는다', async () => {
  const page = erpPage({ bulkReview: REVIEW, adjustReview: RESERVED, panelEdit: openDays(['2026-07-02']), bulkValues: { '2026-07-01': '120000.00', '2026-07-02': '125000.00' } });
  const flow = priceFlow(page);
  try {
    const { change, plan, short } = await flow.preview(request(['2026-07-01', '2026-07-02']));
    assert.equal(short.saves, 2, '날마다 값이 달라 저장이 둘');
    await flow.begin(change, plan);
    const steps = await flow.apply(change, (call) => { if (call.no === 2) page.opts.bulkValues['2026-07-02'] = '130000.00'; });
    assert.deepEqual(steps.map((s) => [s.call.no, s.answer.saved, s.recorded.saved, s.recorded.status]), [[1, true, true, 'applying'], [2, false, false, 'stopped']]);
    assert.equal(steps[1].answer.moved, 1);
    assert.match(steps[1].answer.error, /2026-07-02 인원 무관 · 1박 이상 — 읽은 값 판매가 125000\.00 · 화면 판매가 130000\.00/);
    assert.equal(page.log.posts.length, 1, '첫 저장만 나갔다');
    assert.deepEqual(page.opts.bulkValues, { '2026-07-01': '132000.00', '2026-07-02': '130000.00' });
    const check = flow.must('check', '--change', change, '--snapshot', await flow.read(change));
    assert.equal(check.can_continue, false);
    assert.deepEqual(check.steps.map((s) => [s.no, s.ledger, s.seen, s.moved]), [[1, 'saved', 'saved', 0], [2, 'failed', 'changed', 1]]);
    // T1 — 그 check 뒤의 결과 페이지: 이어서는 없고, 그 칸은 미리보기 때 값과 check 가 읽은 값을 그 시각과 함께 보이며(지금 값이라고
    // 하지 않는다 — 시운전 8 F1), 페이지 오류의 날글은 없다
    const { text } = flow.must('render', 'result', '--change', change, '--text');
    assert.ok(!/이어서 —|이어서 하면|나중에 이어서/.test(text), text);
    assert.match(text, /다시 읽어 보니 이어서 할 수 없습니다\./);
    assert.match(text, /미리보기 때 125,000\.00 · \d+시 \d+분에 다시 읽으니 130,000\.00 그 사이 ERP 에서 바뀜 · 넣지 않음/);
    assert.match(text, /다시 읽은 값은 그때 ERP 에 있던 값이고, 그 뒤에 또 바뀌었을 수 있습니다\./);
    assert.ok(!/지금 [\d,.]+/.test(text), text);
    assert.match(text, /도우미는 이 칸에 아무것도 넣지 않았습니다\./);
    assert.ok(!/로그인|읽은 값 판매가|화면 판매가|미리보기를 새로 만듭니다/.test(text), text);
    // 시운전 8 F3 — 멈춘 변경의 페이지는 이름도 파일 이름도 「적용하다 멈춤」, 첫 줄은 바뀐 칸 수를 댄다
    assert.match(text, /^적용하다 멈춤 · /);
    assert.match(text, /2번째 저장에서 멈췄습니다 \(미리보기 뒤에 ERP 에서 그 저장의 칸 1개가 바뀌어 아무것도 넣지 않았습니다\)/);
    const { page: file } = flow.must('render', 'result', '--change', change);
    assert.match(file, / · 적용하다 멈춤\.html$/);
  } finally {
    flow.close();
    page.w.close();
  }
});
