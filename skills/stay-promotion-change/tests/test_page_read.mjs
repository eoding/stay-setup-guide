// M1 · M7 보기와 읽기 — look 은 카드마다(오퍼 · 전 오퍼 공통) 프로모션 줄을 화면의 글자 그대로 싣고, readPromotion 은 편집 창을 열어 저장
// 단추가 보낼 칸 · 표식(뿌리 · 단 줄마다)을 읽고 닫는다. 어느 쪽도 저장을 누르지 않는다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { promotionPage, inPage, plain, takeAll, charsOf, HOTEL, LISTED } from './promotion_harness.mjs';

const read = async (page, offer, promotion) => plain(await page.w.stayPromotion.readPromotion(inPage(page.w, { hotel: HOTEL, offer, promotion })));

test('M1 · look 은 카드마다 프로모션 줄을 화면의 글자 그대로 싣고 전 오퍼 공통 카드는 오퍼 0 이며, 탭이 꺼져 있을 때만 탭을 누른다', async () => {
  for (const tab of ['promotions', 'calendar']) {
    const page = promotionPage({ tab });
    const r = plain(await page.w.stayPromotion.look());
    assert.equal(r.ok, true, r.error);
    assert.deepEqual(r.count, { offers: 3, promotions: 6 });
    assert.ok(charsOf(r) <= 800);
    assert.deepEqual(r.clicks, tab === 'promotions' ? {} : { tab: 1 });
    const { body } = takeAll(page.w, r);
    assert.deepEqual(body.offers, LISTED);
    assert.deepEqual(page.log.posts, []);
    page.w.close();
  }
});

test('M1 · 로그인 화면이면 look 은 아무것도 누르지 않고 login: true 다', async () => {
  const page = promotionPage({ login: true });
  const r = plain(await page.w.stayPromotion.look());
  assert.deepEqual([r.ok, r.login, r.clicks], [true, true, {}]);
  page.w.close();
});

test('M1 · readPromotion 은 창이 보낼 칸 · 고르기의 글자 · 뿌리 표식 · 단 줄마다 화면 밖 설정의 이름을 읽고 드로어를 닫는다', async () => {
  const page = promotionPage();
  const r = await read(page, '601', '9005');
  assert.equal(r.ok, true, r.error);
  assert.deepEqual([r.keeps, r.clicks], [true, { promotionOpen: 1 }]);
  const { body } = takeAll(page.w, r);
  const win = body.window;
  assert.deepEqual(win.marks, [['cancellation'], ['cancellation']]);
  assert.equal(win.keeps, true);
  assert.deepEqual(win.form.filter(([name]) => name.startsWith('tiers_')),
    [['tiers_submitted', '1'], ['tiers_origin', '46'], ['tiers_threshold', '46'], ['tiers_value', '15.0'],
      ['tiers_origin', '31'], ['tiers_threshold', '31'], ['tiers_value', '10.0']]);
  assert.equal(win.labels.trigger_type, '얼리버드 — 체크인 D-N일 전에 예약하면');
  assert.equal(win.title, '프로모션 편집 — 얼리버드 46일 15% 환불 불가 / 31일 10% 컷오프');
  assert.deepEqual([page.drawerOpen(), page.log.posts], [false, []]);
  page.w.close();
});

test('M1 · 전 오퍼 공통 카드의 프로모션은 offer "0" 으로 읽고, 진행기간 체크 · 중복 허용 체크가 켜진 대로 form 에 든다', async () => {
  const page = promotionPage();
  const r = await read(page, '0', '9006');
  assert.equal(r.ok, true, r.error);
  const win = takeAll(page.w, r).body.window;
  assert.ok(win.form.some(([n, v]) => n === 'promotion_apply_flag' && v === 'on'));
  assert.ok(win.form.some(([n, v]) => n === 'combinability' && v === 'on'));
  assert.deepEqual(takeAll(page.w, r).body.offer, { id: '0', name: '전 오퍼 공통' });
  page.w.close();
});

test('M1 · 다른 카드의 번호로 물으면 목록에 없는 것이고 아무것도 열지 않는다', async () => {
  const page = promotionPage();
  const r = await read(page, '601', '9006');
  assert.deepEqual([r.ok, r.missing, r.clicks], [true, true, {}]);
  page.w.close();
});

test('M7 · 서버가 다른 프로모션의 창을 내주면 읽지 않는다', async () => {
  const page = promotionPage({ windowFor: { 9002: '9003' } });
  const r = await read(page, '601', '9002');
  assert.equal(r.ok, false);
  assert.match(r.error, /고른 프로모션\(9002\)의 편집 창이 아닙니다/);
  page.w.close();
});

test('M7 · 화면 밖 설정을 지키지 않는 ERP 의 창은 표식 없이 읽힌다 — keeps false, 숨은 칸 없음, 줄마다 빈 이름', async () => {
  const page = promotionPage({ keeps: false });
  const r = await read(page, '601', '9005');
  assert.equal(r.ok, true, r.error);
  const win = takeAll(page.w, r).body.window;
  assert.deepEqual([r.keeps, win.keeps, win.marks], [false, false, [[], []]]);
  assert.equal(win.form.some(([name]) => name === 'tiers_origin'), false);
  page.w.close();
});
