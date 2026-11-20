// C1 · C4 부과금 읽기 — readCharge({hotel, offer, charge}) 는 그 오퍼 카드의 그 줄 [편집] 을 눌러 창을 열고, 창이 그 호텔 · 그
// 부과금의 것인지 보고, 저장 단추가 보낼 칸(form — 시간대 행 · 연령별 단가 · 금액의 뜻까지 차례 그대로)과 고르기의 보이는 글자 ·
// 정액 통화 · 연령 구간 칸 · 오류를 읽고 드로어를 `stay-drawer-close` 로 닫는다. 저장은 누르지 않는다. 목록에 그 줄이 없으면
// {missing: true} 이고 더 누르지 않는다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { chargePage, inPage, plain, takeAll, HOTEL, DB, LISTED, rowOf } from './charge_harness.mjs';

const read = (page, offer, charge, hotel = HOTEL) => page.w.stayCharge.readCharge(inPage(page.w, { hotel, offer, charge }));
const NO_ONSITE = [['onsite_currency', ''], ['onsite_amount', '']];
const TAIL = (description) => [['description', description], ['scope_room_mode', '0']];
// fixtures/erp/charges.json 의 여섯 창이 보낼 칸 — 손으로 적은 기대값(창의 칸 차례 그대로)
const FORMS = {
  701: [['kind', '1'], ['name', '레이트 체크아웃 (14시 이후 · 1박 요금의 50%)'], ['basis', '1'], ['per', '0'],
    ['amount_mode', 'blank'], ['amount', ''], ['pct_mode', 'set'], ['pct', '50.00'], ['date_mode', 'optional'], ['date_scope', ''], ...NO_ONSITE,
    ['tiers_submitted', '1'],
    ['tiers_time_from', '12:01'], ['tiers_time_to', '14:00'], ['tiers_basis', '0'], ['tiers_amount', '0.00'], ['tiers_pct', ''],
    ['tiers_time_from', '14:01'], ['tiers_time_to', '18:00'], ['tiers_basis', '1'], ['tiers_amount', ''], ['tiers_pct', '50.00'], ...TAIL('')],
  702: [['kind', '0'], ['name', '얼리 체크인 (07시부터 · 1박 요금의 30%)'], ['basis', '1'], ['per', '0'],
    ['amount_mode', 'blank'], ['amount', ''], ['pct_mode', 'set'], ['pct', '30.00'], ['date_mode', 'optional'], ['date_scope', ''], ...NO_ONSITE,
    ['tiers_submitted', '1'],
    ['tiers_time_from', '00:00'], ['tiers_time_to', '06:59'], ['tiers_basis', '1'], ['tiers_amount', ''], ['tiers_pct', '100.00'],
    ['tiers_time_from', '07:00'], ['tiers_time_to', '12:00'], ['tiers_basis', '1'], ['tiers_amount', ''], ['tiers_pct', '30.00'],
    ...TAIL('체크인 시각은 호텔 확인 뒤 정해집니다')],
  703: [['kind', '9'], ['name', '크리스마스 갈라 디너 (12/24 · 의무 · 성인)'], ['basis', '0'], ['per', '2'],
    ['amount_mode', 'set'], ['amount', '90.00'], ['pct_mode', 'blank'], ['pct', ''], ['date_mode', 'mandatory'], ['date_scope', '2026-12-24'],
    ['room_scope', '51'], ...NO_ONSITE, ['tiers_submitted', '1'], ...TAIL('')],
  704: [['kind', '9'], ['name', '현장 결제 리조트피'], ['basis', '0'], ['per', '0'],
    ['amount_mode', 'set'], ['amount', '0.00'], ['pct_mode', 'blank'], ['pct', ''], ['date_mode', 'optional'], ['date_scope', ''],
    ['onsite_currency', '2'], ['onsite_amount', '15.00'], ['tiers_submitted', '1'], ...TAIL('체크인 때 호텔에 직접 냅니다')],
  705: [['kind', '9'], ['name', '연말 갈라 디너 (12/31 · 의무 · 연령별)'], ['basis', '0'], ['per', '2'],
    ['amount_mode', 'set'], ['amount', '100.00'], ['pct_mode', 'blank'], ['pct', ''], ['date_mode', 'mandatory'], ['date_scope', '2026-12-31'],
    ...NO_ONSITE, ['onsite_age_rate_81', ''], ['onsite_age_rate_82', ''], ['age_rate_81', '0.00'], ['age_rate_82', '50.00'],
    ['tiers_submitted', '1'], ...TAIL('')],
  706: [['kind', '9'], ['name', '공항 픽업 (금액 미정)'], ['basis', '0'], ['per', '0'],
    ['amount_mode', 'blank'], ['amount', ''], ['pct_mode', 'blank'], ['pct', ''], ['date_mode', 'optional'], ['date_scope', ''], ...NO_ONSITE,
    ['onsite_age_rate_81', ''], ['onsite_age_rate_82', ''], ['age_rate_81', ''], ['age_rate_82', ''], ['tiers_submitted', '1'], ...TAIL('')]
};
const OFFER = { 701: '601', 702: '601', 703: '601', 704: '601', 705: '602', 706: '602' };
const OPTIONAL = '선택 — 고객이 고를 때만 붙습니다', MANDATORY = '의무 — 고객 선택 없이 자동으로 붙습니다';

test('C1 · 여섯 부과금 모두 저장 단추가 보낼 칸을 [이름, 값] 차례 그대로 읽는다 — 시간대 행 · 금액의 뜻 · 연령별 단가 · 현장 결제까지', async () => {
  const page = chargePage();
  for (const id of Object.keys(FORMS)) {
    const r = plain(await read(page, OFFER[id], id));
    assert.equal(r.ok, true, `${id}: ${r.error}`);
    const { body } = takeAll(page.w, r);
    assert.deepEqual(body.window.form, FORMS[id], id);
    assert.deepEqual(body.charge, rowOf(id), `${id}: 목록 줄도 같이 싣는다`);
    assert.deepEqual(body.offer, { id: OFFER[id], name: LISTED.find((o) => o.id === OFFER[id]).name }, id);
    assert.equal(body.window.title, `부과금 편집 — ${FORMS[id][1][1]}`, id);
    assert.equal(body.window.currency, 'USD', id);
    assert.deepEqual(body.window.errors, [], `${id}: 숨은 안내 오류는 오류가 아니다`);
  }
  assert.deepEqual(page.log.posts, [], '저장 요청이 없다');
  page.w.close();
});

test('C1 · 한 번 읽기는 그 줄의 창 하나만 열고, 저장은 누르지 않고, 드로어를 닫은 뒤 답한다', async () => {
  const page = chargePage();
  const r = plain(await read(page, '601', '701'));
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.clicks, { chargeOpen: 1 });
  assert.equal(r.what, '데모 오퍼 2027 · 레이트 체크아웃 (14시 이후 · 1박 요금의 50%)');
  assert.deepEqual(page.log.gets, ['/stay/1/charges/701/edit/']);
  assert.equal(r.rest, true);
  assert.equal(page.drawerOpen(), false);
  assert.equal(page.doc.getElementById('stay_drawer_body').children.length, 0, '드로어 내용까지 비었다');
  assert.ok(!/\/stay\/|charges\/\d/.test(JSON.stringify(r) + JSON.stringify(takeAll(page.w, r).body)), '저장 주소는 돌려주지 않는다');
  page.w.close();
});

test('C1 · 고르기의 보이는 글자를 이름마다 싣고(시간대 행의 요율 방식은 줄바꿈으로 이어), 연령 구간 칸은 칸 이름 · 구간 코드 · 이름으로 싣는다', async () => {
  const page = chargePage();
  const late = takeAll(page.w, plain(await read(page, '601', '701'))).body.window;
  assert.deepEqual(late.labels, {
    kind: '레이트 체크아웃', basis: '1박 요금의 %', per: '체류당 1회', amount_mode: '미정 (비움)', pct_mode: '지정 (0 포함)',
    date_mode: OPTIONAL, onsite_currency: '---------', tiers_basis: '정액\n1박 요금의 %', scope_room_mode: '기존 범위 그대로'
  });
  assert.deepEqual(late.bands, []);
  const gala = takeAll(page.w, plain(await read(page, '602', '705'))).body.window;
  assert.deepEqual([gala.labels.per, gala.labels.amount_mode, gala.labels.date_mode], ['인당', '지정 (0 포함)', MANDATORY]);
  assert.deepEqual(gala.bands, [
    { field: 'onsite_age_rate_81', code: 'INF', label: '유아' }, { field: 'onsite_age_rate_82', code: 'CHD', label: '소아' },
    { field: 'age_rate_81', code: 'INF', label: '유아' }, { field: 'age_rate_82', code: 'CHD', label: '소아' }
  ]);
  const resort = takeAll(page.w, plain(await read(page, '601', '704'))).body.window;
  assert.equal(resort.labels.onsite_currency, 'USD');
  page.w.close();
});

test('C1 · 정액 통화는 「정액 금액 (USD)」 머리에서 읽고, 통화가 없는 호텔이면 빈 글자다', async () => {
  const db = JSON.parse(JSON.stringify(DB));
  db.currency = '';
  const page = chargePage({ db });
  const w = takeAll(page.w, plain(await read(page, '601', '703'))).body.window;
  assert.equal(w.currency, '');
  page.w.close();
});

test('C1 · 목록에 그 줄이 없으면(다른 오퍼 카드의 줄이어도) {missing: true} 이고 아무것도 열지 않는다', async () => {
  const page = chargePage();
  for (const [offer, charge] of [['601', '799'], ['602', '701'], ['699', '701']]) {
    const r = plain(await read(page, offer, charge));
    assert.deepEqual([r.ok, r.missing, r.body], [true, true, undefined], `${offer}/${charge}`);
    assert.deepEqual(r.clicks, {}, `${offer}/${charge}`);
  }
  assert.deepEqual([page.log.reached, page.log.gets], [[], []]);
  const off = chargePage({ tab: 'calendar' });
  const r = plain(await read(off, '601', '799'));
  assert.deepEqual([r.missing, r.clicks], [true, { tab: 1 }], '목록을 보려고 탭만 눌렀다');
  off.w.close();
  page.w.close();
});

test('C1 · 다른 호텔의 탭이면 아무것도 누르기 전에 두 호텔을 대며 거절하고, 호텔을 짚지 않은 요청은 시작하지 않는다', async () => {
  const page = chargePage({ hotel: { id: '2', name: HOTEL.name } });
  const r = plain(await read(page, '601', '701'));
  assert.equal(r.ok, false);
  assert.match(r.error, /이 탭은 호텔 2 \(데모 호텔\) 입니다 — 요청은 호텔 1 \(데모 호텔\) 입니다/);
  assert.deepEqual([page.log.reached, r.clicks], [[], {}]);
  page.w.close();
  const same = chargePage();
  const none = plain(await same.w.stayCharge.readCharge(inPage(same.w, { offer: '601', charge: '701' })));
  assert.match(none.error, /`hotel` 이 없습니다 — stayCharge\.look\(\) 의 hotel/);
  assert.deepEqual(same.log.reached, []);
  same.w.close();
});

test('C1 · 서버가 다른 부과금의 창을 내주면 읽지 않고 멈춘다', async () => {
  const page = chargePage({ windowFor: { 701: '702' } });
  const r = plain(await read(page, '601', '701'));
  assert.equal(r.ok, false);
  assert.match(r.error, /열린 창이 고른 부과금\(701\)의 편집 창이 아닙니다 — 아무것도 치지 않았습니다/);
  assert.equal(r.body, undefined);
  assert.equal(page.drawerOpen(), false, '열린 창은 닫았다');
  page.w.close();
});

test('C4 · 시간대 행이 덜 그려진 창(화면 스크립트가 아직 행을 안 그렸다)은 읽지 않는다 — 행 없는 form 을 보내면 시간대가 지워진다', async () => {
  const page = chargePage();
  // 창이 열리자마자 그려진 시간대 행 하나를 빼 본다(Alpine 이 아직 다 그리지 않은 모양)
  const observer = new page.w.MutationObserver(() => {
    const drawn = page.doc.querySelector('#stay_drawer_body [data-stay-card="tiers"] tr[data-stay-row="1"]');
    if (drawn) drawn.remove();
  });
  observer.observe(page.doc.getElementById('stay_drawer_body'), { childList: true, subtree: true });
  page.w.stayPrice.config({ budgetMs: 6000 });
  const r = plain(await read(page, '601', '701'));
  observer.disconnect();
  assert.equal(r.ok, false);
  assert.match(r.error, /시간대별 요율 행이 다 그려지지 않았습니다/);
  assert.equal(r.body, undefined);
  page.w.close();
});

test('C1 · 번호는 look() 의 id 글자 그대로만 받는다', async () => {
  const page = chargePage();
  for (const [offer, charge, name] of [['601', 701, 'charge'], ['601', '', 'charge'], ['60 1', '701', 'offer'], [null, '701', 'offer']]) {
    const r = plain(await page.w.stayCharge.readCharge(inPage(page.w, { hotel: HOTEL, offer, charge })));
    assert.equal(r.ok, false, `${offer}/${charge}`);
    assert.match(r.error, new RegExp('`' + name + '` 은 ERP 가 매긴 번호 글자입니다'));
  }
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});
