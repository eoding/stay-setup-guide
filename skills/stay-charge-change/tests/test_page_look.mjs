// C1 보기 — stayCharge.look() 하나로 로그인 화면인지, 어느 호텔인지, 오퍼마다 부과금 줄 전부(목록 그대로의 글자 · 차례)를 안다.
// 금액 칸은 화면의 줄 그대로다(시간대 · 부과 단위 · 연령별 단가 · 현장 결제). 누르는 것은 목록이 안 보일 때의 [부과금] 탭 하나뿐이다.
// 목록은 늘 페이지에 두고(body) take 로 받는다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { chargePage, plain, charsOf, takeAll, HOTEL, DB, LISTED } from './charge_harness.mjs';

test('C1 · 부과금 탭이면 아무것도 누르지 않고, 오퍼 둘과 부과금 여섯을 목록의 글자 · 차례 그대로 조각으로 돌려준다', async () => {
  const page = chargePage();
  const r = plain(await page.w.stayCharge.look());
  assert.equal(r.ok, true, r.error);
  assert.deepEqual([r.op, r.login, r.hotel, r.count], ['look', false, HOTEL, { offers: 2, charges: 6 }]);
  assert.deepEqual(r.clicks, {});
  assert.deepEqual(page.log.reached, [], '목록이 보이면 누르지 않는다');
  assert.ok(charsOf(r) <= 800, String(charsOf(r)));
  const { takes, body } = takeAll(page.w, r);
  assert.ok(takes.length >= 2, '목록은 800자를 넘어 조각 여럿으로 온다');
  for (const piece of takes) assert.ok(charsOf(piece) <= 800, `쪽 하나도 800자 안: ${charsOf(piece)}`);
  for (const piece of takes) assert.ok(!/["\\]/.test(piece.text) && !JSON.stringify(piece).includes('\\'), `쪽 ${piece.at} 에 큰따옴표나 역슬래시가 있다`);
  assert.deepEqual(body.hotel, HOTEL);
  assert.deepEqual(body.offers, LISTED);
  page.w.close();
});

test('C1 · 금액 칸은 화면의 줄 그대로다 — 시간대 행 · 부과 단위 · 연령별 단가 · 현장 결제 · 미정이 한 줄씩', async () => {
  const page = chargePage();
  const { body } = takeAll(page.w, plain(await page.w.stayCharge.look()));
  const amount = (id) => body.offers.flatMap((o) => o.charges).find((c) => c.id === id).amount;
  assert.deepEqual(amount('701'), ['12:01 ~ 14:00 · 정액: 0.00 USD', '14:01 ~ 18:00 · 1박 요금의 %: 50.00%', '체류당 1회']);
  assert.deepEqual(amount('703'), ['90.00 USD', '인당']);
  assert.deepEqual(amount('704'), ['0.00 USD', '체류당 1회', '현장 결제: 15.00 USD']);
  assert.deepEqual(amount('705'), ['100.00 USD', '인당', '연령별 단가: 유아 · 소아', '유아: 0.00 USD', '소아: 50.00 USD']);
  assert.deepEqual(amount('706'), ['미정', '체류당 1회']);
  page.w.close();
});

test('C1 · 다른 탭에서 부르면 [부과금] 탭 하나만 누르고, 목록이 아직 스텁이어도 목록이 온 뒤에 읽는다', async () => {
  const page = chargePage({ tab: 'calendar', charges: 'stub' });
  const r = plain(await page.w.stayCharge.look());
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.clicks, { tab: 1 });
  assert.deepEqual(page.log.reached, ['stay-tab=charges']);
  assert.deepEqual(takeAll(page.w, r).body.offers, LISTED);
  page.w.close();
});

test('C1 · 부과금 탭이 이미 켜졌는데 목록이 아직 스텁이면 탭을 누르지 않고 목록이 스스로 올 때까지 기다린다', async () => {
  const page = chargePage({ charges: 'stub', stubMs: 300 });
  const r = plain(await page.w.stayCharge.look());
  assert.equal(r.ok, true, r.error);
  assert.deepEqual([r.clicks, page.log.reached], [{}, []]);
  assert.deepEqual(page.log.gets, ['/stay/1/charges/'], '스텁이 스스로 부른 목록 하나');
  assert.deepEqual(takeAll(page.w, r).body.offers, LISTED);
  page.w.close();
});

test('C1 · 로그인 화면이면 그렇게만 말하고 아무것도 누르지 않는다(러너가 없어도)', async () => {
  const page = chargePage({ login: true, withScripts: false });
  const r = plain(await page.w.stayCharge.look());
  assert.deepEqual([r.ok, r.login, r.hotel, r.body], [true, true, undefined, undefined]);
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});

test('C1 · 호텔 번호가 없는 화면이면 거절한다', async () => {
  const page = chargePage({ hotel: null });
  const r = plain(await page.w.stayCharge.look());
  assert.equal(r.ok, false);
  assert.match(r.error, /호텔 번호를 찾지 못했습니다/);
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});

test('C1 · 부과금 표의 머리가 그 일곱 칸이 아니거나 줄의 칸 수가 다르면 다른 칸을 값으로 읽지 않고 멈춘다', async () => {
  const page = chargePage();
  const th = [...page.doc.querySelectorAll('[data-stay-entity-id="601"] thead th')].find((el) => el.textContent.trim() === '금액');
  th.textContent = '정액';
  const r = plain(await page.w.stayCharge.look());
  assert.equal(r.ok, false);
  assert.match(r.error, /부과금 표의 머리가 「이름 \/ 종류 \/ 부과 방식 \/ 금액 \/ 적용 범위 \/ 적용 날짜 \/ 액션」 가 아닙니다/);
  assert.equal(r.body, undefined);
  page.w.close();
  const short = chargePage();
  short.doc.querySelector('tr[data-stay-entity-id="703"] td:nth-child(5)').remove();
  const r2 = plain(await short.w.stayCharge.look());
  assert.equal(r2.ok, false);
  assert.match(r2.error, /부과금 줄의 칸이 6개입니다 — 7칸이어야 읽습니다/);
  short.w.close();
});

test('C1 · 부과금이 없는 오퍼는 charges 가 빈 목록이고, 오퍼가 없으면 offers 가 빈 목록이다', async () => {
  const db = JSON.parse(JSON.stringify(DB));
  db.offers[1].charges = [];
  const page = chargePage({ db });
  const { body } = takeAll(page.w, plain(await page.w.stayCharge.look()));
  assert.deepEqual(body.offers.map((o) => [o.id, o.charges.length]), [['602', 0], ['601', 4]]);
  page.w.close();
  const none = chargePage({ db: Object.assign({}, db, { offers: [] }) });
  const r = plain(await none.w.stayCharge.look());
  assert.deepEqual([r.ok, r.count], [true, { offers: 0, charges: 0 }]);
  none.w.close();
});

test('C1 · 부과금이 많아도 답과 쪽은 800자 안이고(쪽 크기 200 도), 이은 목록에 줄이 모두 있다', async () => {
  const db = JSON.parse(JSON.stringify(DB));
  const base = db.offers[0];
  for (let i = 0; i < 12; i++) {
    db.offers.push(Object.assign({}, base, { id: String(610 + i), name: `늘린 오퍼 ${i + 1}`,
      charges: base.charges.map((c, j) => Object.assign({}, c, { id: String(800 + i * 4 + j), name: `${c.name} ${i + 1}` })) }));
  }
  const page = chargePage({ db });
  const r = plain(await page.w.stayCharge.look());
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.count, { offers: 14, charges: 54 });
  for (const size of [undefined, 200]) {
    const { takes, body } = takeAll(page.w, r, size);
    for (const piece of takes) assert.ok(charsOf(piece) <= 800, `${size}: ${charsOf(piece)}`);
    assert.equal(body.offers.flatMap((o) => o.charges).length, 54, String(size));
    assert.deepEqual(body.offers[0].charges.map((c) => c.id), ['845', '844', '846', '847'], '번호 큰 오퍼가 먼저, 줄은 종류 · 번호 차례');
  }
  page.w.close();
});
