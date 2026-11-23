// A2 줄 읽기 — readLine({hotel, addon, line}) 은 그 카드의 그 줄 [편집] 을 눌러 창을 열고, 저장 단추가 보낼 칸(form)을 읽고, 드로어를
// `stay-drawer-close` 로 닫는다. 저장은 누르지 않는다. 목록에 그 줄이 없으면 {missing: true} 이고 더 누르지 않는다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { addonPage, inPage, plain, takeAll, HOTEL, LISTED } from './addon_harness.mjs';

const read = (page, addon, line, hotel = HOTEL) => page.w.stayAddonPrice.readLine(inPage(page.w, { hotel, addon, line }));
const LEGACY_SCOPE = [['scope_rate_plan_mode', '0'], ['scope_room_mode', '0']];

test('A2 · 저장 단추가 보낼 칸을 [이름, 값] 차례 그대로 읽고, 저장은 누르지 않고, 드로어를 닫은 뒤 답한다', async () => {
  const page = addonPage();
  const r = plain(await read(page, '201', '301'));
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.clicks, { lineOpen: 1 });
  assert.deepEqual(page.log.gets, ['/stay/1/addon-prices/301/edit/'], '그 줄의 창 하나만 열었다');
  assert.deepEqual(page.log.posts, [], '저장 요청이 없다');
  assert.equal(r.rest, true);
  assert.equal(page.drawerOpen(), false);
  assert.equal(page.doc.getElementById('stay_drawer_body').children.length, 0, '드로어 내용까지 비었다');
  const { body } = takeAll(page.w, r);
  assert.deepEqual(body.addon, { id: '201', name: '조식 추가 (성인)', offer: '데모 오퍼 2027' });
  assert.deepEqual(body.line, LISTED[0].lines[0]);
  assert.deepEqual(body.window, {
    title: '가격 편집 — 비수기 조식', addon: '조식 추가 (성인)',
    form: [['name', '비수기 조식'], ['price', '20.00'], ['net_amount', '15.00'], ['season', '41'], ['date', ''], ['rate_plan', ''], ['description', ''], ...LEGACY_SCOPE],
    labels: { season: '비수기', rate_plan: '---------', scope_rate_plan_mode: '기존 범위 그대로', scope_room_mode: '기존 범위 그대로' },
    errors: []
  });
  assert.ok(!/\/stay\/|addon-prices/.test(JSON.stringify(r) + JSON.stringify(body)), '저장 주소는 돌려주지 않는다');
  page.w.close();
});

test('A2 · 이름이 같은 부가옵션 둘은 번호로 가르고, 읽은 답이 저마다의 오퍼를 싣는다 — 켜진 적용 범위 체크도 보낼 칸에 든다', async () => {
  const page = addonPage();
  const second = takeAll(page.w, plain(await read(page, '204', '305'))).body;
  assert.deepEqual(second.addon, { id: '204', name: '엑스트라베드', offer: '데모 연말 오퍼' });
  assert.equal(second.line.target, '연말 시즌');
  assert.deepEqual(second.window.form, [['name', '엑스트라베드 1개'], ['price', '33.00'], ['net_amount', '27.50'], ['season', '43'], ['date', ''], ['rate_plan', ''],
    ['description', ''], ['scope_rate_plan_mode', '2'], ['scope_rate_plan_include', '53'], ['scope_room_mode', '0']]);
  assert.equal(second.window.labels.scope_rate_plan_mode, '지정한 대상만');
  const first = takeAll(page.w, plain(await read(page, '203', '304'))).body;
  assert.deepEqual(first.addon, { id: '203', name: '엑스트라베드', offer: '데모 오퍼 2027' });
  assert.deepEqual(first.window.form.slice(0, 4), [['name', '엑스트라베드 1개'], ['price', '30.00'], ['net_amount', '25.00'], ['season', '']]);
  assert.deepEqual(page.log.gets, ['/stay/1/addon-prices/305/edit/', '/stay/1/addon-prices/304/edit/']);
  page.w.close();
});

test('A2 · 목록이 「별도 금액 없음」 인 줄은 값 줄이 비고, 창의 공급 원가도 빈칸이다 — 둘 다 그대로 알린다', async () => {
  const page = addonPage();
  const { body } = takeAll(page.w, plain(await read(page, '202', '303')));
  assert.deepEqual(body.line.values, []);
  assert.deepEqual(body.window.form.slice(1, 3), [['price', '40.00'], ['net_amount', '']]);
  page.w.close();
});

test('A2 · 목록에 그 줄이 없으면(다른 카드의 줄이어도) {missing: true} 이고 아무것도 열지 않는다', async () => {
  const page = addonPage();
  for (const [addon, line] of [['201', '399'], ['203', '305'], ['299', '301']]) {
    const r = plain(await read(page, addon, line));
    assert.deepEqual([r.ok, r.missing, r.body], [true, true, undefined], `${addon}/${line}`);
    assert.deepEqual(r.clicks, {}, `${addon}/${line}`);
  }
  assert.deepEqual([page.log.reached, page.log.gets], [[], []]);
  const off = addonPage({ tab: 'calendar' });
  const r = plain(await read(off, '201', '399'));
  assert.deepEqual([r.missing, r.clicks], [true, { tab: 1 }], '목록을 보려고 탭만 눌렀다');
  off.w.close();
  page.w.close();
});

test('A2 · 다른 호텔의 탭이면 아무것도 누르기 전에 두 호텔을 대며 거절하고, 호텔을 짚지 않은 요청은 시작하지 않는다', async () => {
  const page = addonPage({ hotel: { id: '2', name: HOTEL.name } });
  const r = plain(await read(page, '201', '301'));
  assert.equal(r.ok, false);
  assert.match(r.error, /이 탭은 호텔 2 \(데모 호텔\) 입니다 — 요청은 호텔 1 \(데모 호텔\) 입니다/);
  assert.deepEqual([page.log.reached, r.clicks], [[], {}]);
  page.w.close();
  const same = addonPage();
  const none = plain(await same.w.stayAddonPrice.readLine(inPage(same.w, { addon: '201', line: '301' })));
  assert.match(none.error, /`hotel` 이 없습니다 — stayAddonPrice\.look\(\) 의 hotel/);
  assert.deepEqual(same.log.reached, []);
  same.w.close();
});

test('A2 · 서버가 다른 줄의 창을 내주면 읽지 않고 멈춘다', async () => {
  const page = addonPage({ windowFor: { 301: '302' } });
  const r = plain(await read(page, '201', '301'));
  assert.equal(r.ok, false);
  assert.match(r.error, /열린 창이 고른 줄\(301\)의 가격 편집 창이 아닙니다/);
  assert.equal(r.body, undefined);
  assert.equal(page.drawerOpen(), false, '열린 창은 닫았다');
  page.w.close();
});

test('A2 · 줄 번호는 look() 의 id 글자 그대로만 받는다', async () => {
  const page = addonPage();
  for (const bad of [301, '', '30 1', null]) {
    const r = plain(await page.w.stayAddonPrice.readLine(inPage(page.w, { hotel: HOTEL, addon: '201', line: bad })));
    assert.equal(r.ok, false, String(bad));
    assert.match(r.error, /`line` 은 ERP 가 매긴 번호 글자입니다/);
  }
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});
