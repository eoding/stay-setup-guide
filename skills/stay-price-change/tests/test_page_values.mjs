// A2 값은 그대로 돌아온다 — 브라우저 도구가 가리는 모양(점으로 이은 조각 셋 · 32자 넘는 글자 줄 · 주소)이 든 이름과 키도 명령에
// 돌아갈 때는 한 글자도 바뀌지 않는다. 조각(take 의 쪽)은 그 자리만 `&#번호;` 로 적어 도구가 가리지 않고, 명령이 되돌린다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { erpPage, inPage, plain, takeAll, runFixture, ownFixture, OFFER, HOTEL } from './page_harness.mjs';
import { priceFlow } from './price_flow.mjs';

const ALL_WEEK = ['월', '화', '수', '목', '금', '토', '일'];
// 리뷰가 든 모양 그대로 — 점으로 이은 호텔 이름 · 오퍼 이름, 35자 한 줄의 객실 이름, 32자 인원 조합 키(칸 길이가 32자다)
const NAMED_HOTEL = Object.freeze({ id: '1', name: 'Hotel.Bali.Resort' });
const DOTTED_OFFER = '2026.04.01';
const LONG_ROOM = 'Deluxe_Ocean_View_Room_with_Balcony';
const LONG_COMBO = 'A2C1_CHILD01_C1_INFANT1_C1_TEEN1';
const TOOL_BLOCKS = [/^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2,}$/, /[A-Za-z0-9_-]{32,}/, /[a-z][a-z0-9+.-]*:\/\//i];

function namedPage() {
  const offer = (html) => html.replaceAll(OFFER, DOTTED_OFFER);
  return erpPage({
    hotel: NAMED_HOTEL,
    panelEdit: (html) => offer(html).replaceAll('data-stay-name="디럭스 · ', `data-stay-name="${LONG_ROOM} · `),
    adjustSelectEdit: (html) => offer(html).replace('<span>디럭스</span>', `<span>${LONG_ROOM}</span>`),
    bulkReview: offer(runFixture('calendar-bulk--price-step2.html')).replaceAll('(공급 통화)', '(USD)')
      .replace('data-stay-occupancy-key=""', `data-stay-occupancy-key="${LONG_COMBO}"`)
      .replace('name="prices-0-occupancy_key" id=', `name="prices-0-occupancy_key" value="${LONG_COMBO}" id=`)
      .replace('인원 무관 단일가 · 1박 이상', `${LONG_COMBO} · 성인 2 + 아동 3 · 1박 이상`),
    adjustReview: offer(ownFixture('adjust-rejected.html')).replaceAll('<td>디럭스</td>', `<td>${LONG_ROOM}</td>`).replaceAll('<td>스위트</td>', `<td>${LONG_ROOM}</td>`)
  });
}

test('A2 · 점으로 이은 호텔 · 오퍼 이름, 35자 객실 이름, 32자 인원 조합 키 — look 의 이름 그대로 읽고, 미리보기를 만들고, 저장한다', async () => {
  const page = namedPage();
  const flow = priceFlow(page);
  try {
    const looked = await flow.look();
    assert.ok(looked.answer.body, '거르기가 바꿀 이름은 답의 칸이 아니라 조각으로 온다');
    assert.deepEqual([looked.hotel, looked.offer], [NAMED_HOTEL, DOTTED_OFFER]);
    assert.ok(looked.pairs.some((p) => p.room === LONG_ROOM && p.rate_plan === '조식 포함'), JSON.stringify(looked.pairs));
    const request = { kind: 'change', hotel: looked.hotel, offer: looked.offer, rooms: [], rate_plans: [], pairs: [{ room: LONG_ROOM, rate_plan: '조식 포함' }],
      dates: ['2026-07-01'], field: 'sell', operation: { kind: 'amount', value: '1000' }, occupancies: [], nights: [], scale_child_surcharge: false, sentence: '시험' };
    const { change, plan, short } = await flow.preview(request);
    assert.equal(short.saves, 1, JSON.stringify(short));
    const snapshot = flow.must('list', '--all').changes.find((c) => c.id === change);
    assert.equal(snapshot.hotel, NAMED_HOTEL.name, '장부의 호텔 이름도 그대로');
    assert.equal((await flow.begin(change, plan)).status, 'applying');
    const steps = await flow.apply(change);
    assert.deepEqual(steps.map((s) => [s.answer.saved, s.recorded.saved, s.recorded.status]), [[true, true, 'applied']], JSON.stringify(steps.map((s) => s.answer)));
    assert.equal(steps[0].call.payload.rows[0].occupancy, LONG_COMBO);
    assert.equal(page.log.posts.length, 1);
    assert.equal(page.log.posts[0]['prices-0-occupancy_key'], LONG_COMBO);
    assert.equal(page.log.posts[0]['prices-0-price'], '121000.00');
  } finally {
    flow.close();
    page.w.close();
  }
});

test('A2 · 조각의 쪽에는 도구가 가리는 모양이 없고, 이으면 화면의 글자 · 물은 값이 그대로다(주소가 든 글자도)', async () => {
  const LINKED = '조식 안내 https://hotel.example/menu?day=1 · /stay/1/x/ · www.example.test';
  const page = erpPage({ hotel: NAMED_HOTEL, bulkReview: runFixture('calendar-bulk--price-step2.html').replace('인원 무관 단일가 · 1박 이상', `${LINKED} · ${LONG_COMBO}`) });
  const asked = { hotel: NAMED_HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01', weekdays: ALL_WEEK };
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, asked)));
  assert.equal(r.ok, true, r.error);
  const { takes, body } = takeAll(page.w, r, 300);
  for (const t of takes) {
    for (const shape of TOOL_BLOCKS) assert.ok(!shape.test(t.text), `쪽 ${t.at} 에 도구가 가리는 모양 ${shape}: ${t.text}`);
    assert.deepEqual(plain(page.w.stayPrice.scrub(inPage(page.w, t))), t, `쪽 ${t.at} 은 거르기를 지나도 그대로다`);
  }
  assert.deepEqual(body.asked, asked, '물은 값이 그대로 — 명령이 답의 지문(ask)과 맞춘다');
  assert.equal(body.hotel.name, NAMED_HOTEL.name);
  assert.ok(body.fragment.includes(`${LINKED.replaceAll('&', '&amp;')} · ${LONG_COMBO}`), '화면 조각의 글자가 그대로');
  page.w.close();
});
