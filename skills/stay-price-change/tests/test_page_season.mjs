// 시즌 창 모듈 `stay_price_season.js` — 벽, readSeason(창 · 기본값 · 날 · 객실 · 요금제 · 아동 칸 · 요금제 탭의 이름 · 허용 조합),
// applySeason(창이 다르면 치지 않음 · 치는 차례 · 친 뒤 확인 · 한 번 누름 · 저장 띠의 수 · 답이 늦으면 「모름」 · 요청이 도는 동안 드로어를
// 닫지 않음).
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { seasonPage, inPage, plain, takeAll, payloadFrom, withDates, childPercent, WINDOW, LAST_FILL, OFFER, IDS, HOTEL, SEASON, personClick } from './season_harness.mjs';
import { SKILL } from './page_harness.mjs';

const ask = (season = { id: IDS.season }) => ({ hotel: HOTEL, offer: OFFER, season });
async function read(page, input = ask()) {
  const r = plain(await page.w.stayPriceSeason.readSeason(inPage(page.w, input)));
  assert.equal(r.ok, true, r.error);
  return { r, body: takeAll(page.w, r).body };
}
const DELUXE = { rooms: [IDS.room[1]], plans: [IDS.plan[1], IDS.plan[2]], texts: { price: '180', occupancy_keys: 'A2,A3', occupancy_adjust: 'A3:+30000' } };

test('S5 · 이 파일에는 제 클릭 · 폼 제출 · 꾸민 사건 · localStorage 가 없다 — 누르기는 stayPageKit.press 뿐이다', () => {
  const code = SEASON.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
  for (const banned of ['.click(', '.submit(', 'requestSubmit', 'localStorage', 'new MouseEvent', 'dispatchEvent(new CustomEvent']) {
    assert.ok(!code.includes(banned), `${banned} 가 있습니다`);
  }
});

test('S5 · 벽 — 삭제 · 시즌 [편집] · 판매 마감·해제 · 지우기 칸 · 날짜 달력 · 다른 탭 · 판매 시작은 어느 작업에서도 막힌다', async () => {
  const page = seasonPage({ tab: 'seasons' });
  const root = page.showWindow();
  const targets = [
    page.doc.querySelector('#stay_seasons [data-stay-action="delete"]'), page.doc.querySelector('#stay_seasons [data-stay-action="open_edit"]'),
    page.doc.querySelector('#stay_seasons [data-stay-action="open_tab"]'), root.querySelector('input[name="stale_cleanup"]'),
    root.querySelector('[data-date-mode="single"]'), root.querySelector('[data-date-month="1"]'), root.querySelector('[data-date-clear]'),
    page.doc.querySelector('ul.tab-container a[data-stay-tab="offers"]'), page.doc.querySelector('[data-stay-action="activate"]')];
  for (const op of ['readSeason', 'applySeason']) {
    const pins = { hotel: '1', season: IDS.season, want: [['stale_cleanup', 'on']] };
    const r = plain(await page.w.stayPriceSeason.guard(op, () => targets.forEach((el) => el.click()), pins));
    assert.equal(r.blocked.length, targets.length, op);
    assert.match(r.blocked[3].why, /^이번에 고르지 않은 인원·요금제 가격 지우기 — 이 도우미는 누르지 않습니다$/,
      '지우기 칸은 허용 목록보다 먼저 보는 금지 목록이 막는다(허용 줄이 잘못 넓어져도 막힌다)');
  }
  assert.equal(root.querySelector('input[name="stale_cleanup"]').checked, false, '지우기 칸은 켜지지 않았다');
  assert.deepEqual(page.log.reached, [], '막힌 클릭은 화면에 닿지 않는다');
  page.w.close();
});

test('S5 · 벽 — 체크는 want 쪽으로만, [가격 적용]은 보낼 칸이 want 와 같을 때 한 번만 지난다', async () => {
  const page = seasonPage({ tab: 'seasons' });
  const root = page.showWindow();
  const room = root.querySelector(`input[name="rooms"][value="${IDS.room[1]}"]`);
  const overwrite = root.querySelector('input[name="overwrite"]');
  const save = root.querySelector('[data-stay-action="save"]');
  room.checked = true; overwrite.checked = false;
  const want = plain(page.w.stayPageKit.sent(root));
  room.checked = false; overwrite.checked = true;
  const pins = { hotel: '1', season: IDS.season, want, until: Date.now() + 60000 };
  let r = plain(await page.w.stayPriceSeason.guard('applySeason', () => { room.click(); room.click(); }, pins));
  assert.deepEqual([r.clicks, r.blocked.length, room.checked], [['room'], 1, true], '켜는 클릭은 지나고, 다시 끄는 클릭은 막힌다');
  r = plain(await page.w.stayPriceSeason.guard('applySeason', () => save.click(), pins));
  assert.match(r.blocked[0].why, /고른 대상이 아닙니다/, '덮기가 아직 켜져 있어 보낼 칸이 want 와 다르면 막힌다');
  overwrite.checked = false;
  page.answerSavesWith('hang');
  r = plain(await page.w.stayPriceSeason.guard('applySeason', () => { save.click(); save.click(); }, pins));
  assert.deepEqual([r.clicks, r.blocked.map((b) => b.why)], [['save'], ['같은 저장을 다시 누르지 않습니다']], '두 번째 누름은 막힌다');
  assert.equal(page.log.posts.length, 1);
  page.w.close();
});

test('S1 · readSeason — 창이 열린 그대로의 칸 · 차례 · 날 · 객실 · 요금제 · 아동 칸, 요금제 탭의 이름 · 객실 타입 · 시즌 목록', async () => {
  const page = seasonPage();
  const { r, body } = await read(page);
  assert.deepEqual(r.clicks, { tab: 1, fillOpen: 1 });
  assert.equal(page.drawerOpen(), false, '읽은 뒤 닫는다');
  assert.equal(body.offer, OFFER);
  assert.deepEqual(body.season, { id: IDS.season, name: 'PEAK', days: '1' });
  assert.deepEqual(body.dates, ['2026-07-01']);
  assert.equal(body.blank, null, '마지막 입력값이 없으면 [비우기] 를 누르지 않는다');
  assert.deepEqual(body.form.slice(0, 3), [['date_selection_0', '2026-07-01'], ['date_selection_1', ''], ['price', '']]);
  assert.deepEqual(body.form.filter(([n]) => n === 'overwrite'), [['overwrite', 'on']]);
  assert.deepEqual(body.order, ['date_selection_0', 'date_selection_1', 'price', 'original_price', 'net_price', 'rooms', 'rate_plans', 'plan_adjust',
    'occupancy_keys', 'occupancy_adjust', 'los_prices', 'child_extra_INFANT', 'child_extra_CHILD', 'overwrite', 'stale_cleanup']);
  assert.deepEqual(body.rooms, [{ id: '301', label: `${OFFER} · 디럭스` }, { id: '302', label: `${OFFER} · 스위트` }]);
  assert.deepEqual(body.plans[0], { id: '9001', roomId: '301', label: `${OFFER} · 디럭스 · 조식 포함` });
  assert.deepEqual(body.child, [{ field: 'child_extra_INFANT', editable: true, value: '0.00', text: '' },
    { field: 'child_extra_CHILD', editable: true, value: '30000.00', text: '' }]);
  assert.deepEqual(body.ratePlans.map((p) => [p.id, p.roomId, p.room, p.plan, p.base]).slice(0, 2),
    [['9001', '301', '디럭스', '조식 포함', false], ['9002', '301', '디럭스', '룸온리', false]]);
  assert.deepEqual(body.roomTypes.map((t) => t.name), ['디럭스', '스위트']);
  assert.ok(body.roomTypes.every((t) => typeof t.combos === 'string'), '허용 인원 조합 칸을 머리로 찾아 읽는다');
  assert.deepEqual(body.seasons, [{ id: IDS.season, name: 'PEAK', days: '1' }]);
  page.w.close();
});

test('S1 · readSeason — 마지막 입력값이 채워져 열리면 [비우기] 한 창(기본값)도 읽고, 읽기 전용 아동 글은 그대로, 날만 읽기도 된다', async () => {
  const page = seasonPage({ window: LAST_FILL, windowEdit: (html) => childPercent(withDates(html, ['2026-07-01', '2026-07-02', '2026-07-04'])) });
  const { r, body } = await read(page);
  assert.deepEqual(r.clicks, { tab: 1, fillOpen: 1, blank: 1 });
  assert.match(body.note, /^마지막 입력값을 채웠습니다/);
  assert.deepEqual(body.form.find(([n]) => n === 'price'), ['price', '180000']);
  assert.deepEqual(body.blank.form.find(([n]) => n === 'price'), ['price', '']);
  assert.deepEqual(body.form[0], ['date_selection_0', '2026-07-01 ~ 2026-07-02\n2026-07-04']);
  assert.deepEqual(body.child[1], { field: 'child_extra_CHILD', editable: false, value: '성인 1인 추가분의 50% 로 계산됨', text: '성인 1인 추가분의 50% 로 계산됨' });
  assert.ok(!body.order.includes('child_extra_CHILD'), '막힌 칸은 보낼 칸의 차례에 없다');
  const dated = plain(await page.w.stayPriceSeason.readSeason(inPage(page.w, Object.assign(ask(), { datesOnly: true }))));
  assert.deepEqual([dated.clicks, takeAll(page.w, dated).body.dates], [{ fillOpen: 1 }, ['2026-07-01', '2026-07-02', '2026-07-04']]);
  page.w.close();
});

test('S1 · 이름으로 고른 시즌이 그 오퍼에 없으면 아무것도 열지 않고 시즌 목록을 댄다', async () => {
  const page = seasonPage({ tab: 'seasons' });
  const r = plain(await page.w.stayPriceSeason.readSeason(inPage(page.w, ask({ name: 'Normal' }))));
  assert.equal(r.ok, false);
  assert.match(r.error, /시즌 `Normal` 이 없습니다 — 이 오퍼의 시즌: PEAK\(8801\)/);
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});

test('S5 · applySeason — 치는 차례(글 칸 → 객실 → 요금제 → 덮기 → 날짜), 친 뒤 보낼 칸이 want 와 같을 때 한 번 누르고 저장 띠의 수를 싣는다', async () => {
  const page = seasonPage({ banner: '가격을 넣었습니다 — 새로 4칸 · 덮어쓴 0칸 (룸 1개 × 1일). 판매일이 없어 건너뛴 칸 2개 — 판매일 탭에서 날짜를 먼저 여세요.' });
  const { body } = await read(page);
  const payload = payloadFrom(body, DELUXE);
  const r = plain(await page.w.stayPriceSeason.applySeason(inPage(page.w, payload)));
  assert.equal(r.saved, true, r.error);
  assert.deepEqual(r.clicks, { fillOpen: 1, room: 1, plan: 2, save: 1 }, '시즌 탭은 앞의 읽기가 이미 켜 두었다');
  assert.deepEqual(page.log.typed.filter((n) => n !== 'rate_plans' && n !== 'rooms'), ['price', 'occupancy_keys', 'occupancy_adjust']);
  assert.deepEqual(page.log.posts.map((p) => p.pairs), [payload.want], '보낸 칸이 want 그대로다');
  assert.deepEqual(r.counts, { created: 4, updated: 0, rooms: 1, days: 1, skipped: 2 });
  assert.match(r.banner, /^가격을 넣었습니다 — 새로 4칸/);
  page.w.close();
});

test('S5 · applySeason — 창이 미리보기 때와 다르면(다른 사람이 친 값 · 다른 시즌 날) 한 글자도 치지 않고 누르지 않는다', async () => {
  const page = seasonPage();
  const { body } = await read(page);
  const payload = payloadFrom(body, DELUXE);
  for (const edit of [(html) => html.replace('name="price"', 'name="price" value="175"'), (html) => withDates(html, ['2026-07-01', '2026-07-02'])]) {
    page.opts.windowEdit = edit;
    page.log.typed.length = 0;
    const r = plain(await page.w.stayPriceSeason.applySeason(inPage(page.w, payload)));
    assert.deepEqual([r.saved, r.pressed, r.refused], [false, false, true], r.error);
    assert.match(r.error, /시즌 창이 미리보기 때와 다릅니다/);
    assert.deepEqual(page.log.typed, [], '아무것도 치지 않았다');
    assert.deepEqual(Object.keys(r.clicks).filter((name) => name !== 'tab'), ['fillOpen'], '창을 연 것 말고는 누르지 않았다');
  }
  assert.deepEqual(page.log.posts, []);
  page.w.close();
});

test('S5 · applySeason — 친 뒤 화면 스크립트가 다른 칸을 바꿔 보낼 칸이 want 와 다르면 누르지 않는다', async () => {
  const page = seasonPage({ onType: 'clearNet', windowEdit: (html) => html.replace('name="net_price"', 'name="net_price" value="150"') });
  const { body } = await read(page);
  const payload = payloadFrom(body, Object.assign({}, DELUXE, { texts: Object.assign({}, DELUXE.texts, { net_price: '150' }) }));
  assert.deepEqual(body.form.find(([n]) => n === 'net_price'), ['net_price', '150']);
  const r = plain(await page.w.stayPriceSeason.applySeason(inPage(page.w, payload)));
  assert.deepEqual([r.saved, r.pressed, r.refused], [false, false, true], r.error);
  assert.match(r.error, /친 뒤의 시즌 창이 보낼 값과 다릅니다\(net_price\)/);
  assert.deepEqual(page.log.posts, []);
  page.w.close();
});

test('S5 · applySeason — 지우기 칸을 켜라는 want 는 아무것도 열지 않고 거절한다', async () => {
  const page = seasonPage();
  const { body } = await read(page);
  const payload = payloadFrom(body, DELUXE);
  payload.want.push(['stale_cleanup', 'on']);
  const r = plain(await page.w.stayPriceSeason.applySeason(inPage(page.w, payload)));
  assert.deepEqual([r.saved, r.pressed], [false, false]);
  assert.match(r.error, /지우기」는 켜지 않습니다/);
  assert.deepEqual(r.clicks, {});
  page.w.close();
});

test('S5 · applySeason — ERP 가 창을 오류와 함께 다시 그리면 저장 안 됨, 공급 통화 없음 띠는 저장됨에 경고를 단다', async () => {
  let page = seasonPage({ onSave: 'refused' });
  let payload = payloadFrom((await read(page)).body, DELUXE);
  let r = plain(await page.w.stayPriceSeason.applySeason(inPage(page.w, payload)));
  assert.deepEqual([r.saved, r.pressed], [false, true]);
  assert.match(r.error, /시즌 창이 저장을 거절했습니다 — 조정 값은 부호를 붙여 주세요/);
  page.w.close();
  page = seasonPage({ onSave: 'nosupply' });
  payload = payloadFrom((await read(page)).body, DELUXE);
  r = plain(await page.w.stayPriceSeason.applySeason(inPage(page.w, payload)));
  assert.equal(r.saved, true);
  assert.match(r.warn, /공급 통화가 없어/);
  page.w.close();
});

test('S5 · applySeason — 저장이 호출보다 오래 걸리면 「모름」(눌림 · 다시 누르지 않음), 요청이 도는 동안 다음 작업은 드로어를 닫지 않고 기다리라고 한다', async () => {
  const page = seasonPage({ onSave: 'slow', slowMs: 1500 });
  const { body } = await read(page);
  page.w.stayPrice.config({ budgetMs: 600, hardMs: 900, restMs: 300 });
  const r = plain(await page.w.stayPriceSeason.applySeason(inPage(page.w, payloadFrom(body, DELUXE))));
  assert.deepEqual([r.saved, r.pressed], ['unknown', true], r.error);
  assert.equal(page.log.posts.length, 1);
  assert.equal(page.drawerOpen(), true, '요청이 도는 동안 드로어를 닫지 않았다');
  const waiting = plain(await page.w.stayPriceSeason.readSeason(inPage(page.w, ask())));
  assert.deepEqual([waiting.started, waiting.wait], [false, 5], waiting.error);
  assert.match(waiting.error, /앞 저장 요청이 아직 끝나지 않았습니다/);
  await new Promise((done) => setTimeout(done, 1700));
  const after = plain(await page.w.stayPriceSeason.readSeason(inPage(page.w, ask())));
  assert.equal(after.ok, true, after.error);
  assert.match(takeAll(page.w, after).body.banner, /^가격을 넣었습니다/, '끝난 저장의 띠가 시즌 목록에 남아 있다');
  assert.equal(page.log.posts.length, 1, '다시 누르지 않았다');
  page.w.close();
});

test('검토 2 의 3 · applySeason — 부를 값의 기한이 없거나 지났으면 창을 열지 않고, 누르는 순간 지났으면 벽이 [가격 적용]을 막는다', async () => {
  const page = seasonPage();
  const { body } = await read(page);
  const late = plain(await page.w.stayPriceSeason.applySeason(inPage(page.w, payloadFrom(body, DELUXE, 1, Date.now() - 1))));
  assert.deepEqual([late.saved, late.pressed, late.expired, late.clicks], [false, false, true, {}], late.error);
  assert.match(late.error, /기한\(그 범위를 다시 읽은 지 2분\)이 지났습니다 — 아무것도 누르지 않았습니다/);
  const bare = payloadFrom(body, DELUXE);
  delete bare.freshUntil;
  const none = plain(await page.w.stayPriceSeason.applySeason(inPage(page.w, bare)));
  assert.deepEqual([none.saved, none.pressed, none.expired, none.clicks], [false, false, true, {}], none.error);
  assert.match(none.error, /calls 가 그 범위를 다시 읽은 값으로 낸 부를 값으로만 누릅니다/);
  assert.deepEqual(page.log.posts, []);
  const root = page.showWindow();
  const want = plain(page.w.stayPageKit.sent(root));
  const r = plain(await page.w.stayPriceSeason.guard('applySeason', () => root.querySelector('[data-stay-action="save"]').click(),
    { hotel: '1', season: IDS.season, want, until: Date.now() - 1 }));
  assert.match(r.blocked[0].why, /고른 대상이 아닙니다/, '보낼 칸이 want 그대로여도 기한이 지나면 누르는 순간 막는다');
  assert.deepEqual(page.log.posts, []);
  page.w.close();
});

test('검토 2 의 page 2 · 공급 통화 없음 띠는 저장 뒤 화면이 쉬지 않아도 답의 warn 에 남고, 파이썬이 그 저장 뒤에 변경을 멈춘다', async () => {
  // 검토자의 재현 — 저장 응답의 HX-Trigger 가 부르는 다시 읽기처럼, 저장의 정착(after:settle) 안에서 htmx 요청 하나를 더 시작한다
  const page = seasonPage({ onSave: 'nosupply' });
  const { body } = await read(page);
  page.w.stayPrice.config({ budgetMs: 3000, hardMs: 3500, restMs: 1000 });   // 검토자는 6 · 7 · 1.5초 — 같은 셈을 짧게
  let refetch = false;
  page.doc.addEventListener('htmx:after:settle', () => {
    if (refetch || !page.doc.querySelector('#stay_seasons [data-stay-banner="no_supply_currency"]')) return;
    refetch = true;
    page.doc.dispatchEvent(new page.w.CustomEvent('htmx:before:request', { bubbles: true, detail: {} }));
    page.w.setTimeout(() => page.doc.dispatchEvent(new page.w.CustomEvent('htmx:finally:request', { bubbles: true, detail: {} })), 4500);
  });
  const r = plain(await page.w.stayPriceSeason.applySeason(inPage(page.w, payloadFrom(body, DELUXE))));
  assert.deepEqual([r.saved, r.rest, refetch], [true, false, true], r.error);
  assert.match(r.warn, /^공급 통화가 없어/, '화면이 아직 정리되지 않았다는 말이 경고를 덮지 않는다');
  const stop = spawnSync('python3', ['-I', '-c', `import json, sys; sys.path.insert(0, ${JSON.stringify(join(SKILL, 'scripts'))})
from price_season import NO_SUPPLY, step_note
result = json.load(sys.stdin)
print(json.dumps([NO_SUPPLY in step_note(result), bool(result.get("warn"))]))`], { input: JSON.stringify(r), encoding: 'utf8' });
  assert.equal(stop.status, 0, stop.stderr);
  assert.deepEqual(JSON.parse(stop.stdout), [true, true], '장부 메모에 그 띠가 들고 record-result 가 halt 로 변경을 멈춘다(W8)');
  await new Promise((done) => setTimeout(done, 1500));
  const again = plain(await page.w.stayPriceSeason.readSeason(inPage(page.w, ask())));
  assert.match(takeAll(page.w, again).body.supplyWarn, /^공급 통화가 없어/, '시즌 창 읽기도 그 띠를 싣는다(「모름」 뒤의 check --season)');
  page.w.close();
});

test('검토 2 의 page 4 · 「모름」으로 끝난 저장을 ERP 가 늦게 거절해 다시 그린 창은 그 저장의 답(lateSave)으로 알리고 닫는다', async () => {
  const page = seasonPage({ onSave: 'hang' });
  const { body } = await read(page);
  page.w.stayPrice.config({ budgetMs: 600, hardMs: 900, restMs: 300 });
  const unknown = plain(await page.w.stayPriceSeason.applySeason(inPage(page.w, payloadFrom(body, DELUXE, 2))));
  assert.deepEqual([unknown.saved, unknown.pressed], ['unknown', true], unknown.error);
  // ERP 가 늦게 거절하고 창(도우미가 친 값이 든 그 창)을 오류와 함께 새 요소로 다시 그린다
  const refused = WINDOW.replace('<div class="table1">', '<div class="stay-banner stay-banner--blocking" data-stay-result="error"><span>조정 값은 부호를 붙여 주세요</span></div><div class="table1">');
  page.doc.getElementById('stay_drawer_body').innerHTML = refused;
  page.doc.dispatchEvent(new page.w.CustomEvent('htmx:finally:request', { bubbles: true, detail: {} }));
  // 다음 작업이 다른 모듈(가격 캘린더 읽기)이어도 그 창을 알아본다
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, { hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01' })));
  assert.deepEqual([r.ok, r.started], [false, false], r.error);
  assert.doesNotMatch(r.error, /사람이 닫은 뒤/, '사람에게 그 창을 닫거나 저장하라고 하지 않는다');
  assert.deepEqual([r.lateSave.op, r.lateSave.no, r.lateSave.ask, r.lateSave.saved, r.lateSave.pressed, r.lateSave.refused],
    ['applySeason', 2, unknown.ask, false, true, true], '그 저장(2번째)의 답 — record-result 가 그 저장으로 받는다');
  assert.deepEqual(r.lateSave.errors, ['조정 값은 부호를 붙여 주세요'], 'ERP 의 오류 글 그대로');
  assert.equal(page.drawerOpen(), false, '도우미가 친 창이라 닫았다');
  await new Promise((done) => setTimeout(done, 400));
  const next = plain(await page.w.stayPriceSeason.readSeason(inPage(page.w, ask())));
  assert.equal(next.ok, true, next.error);
  assert.equal(page.log.posts.length, 1, '다시 누르지 않았다');
  page.w.close();
});

test('S5 · 사람이 연 드로어는 닫지 않는다 — 시즌 창 작업은 시작하지 않는다', async () => {
  const page = seasonPage({ tab: 'seasons' });
  personClick(page.w, page.doc.querySelector('#stay_seasons [data-stay-action="fill"]'));
  const r = plain(await page.w.stayPriceSeason.readSeason(inPage(page.w, ask())));
  assert.equal(r.ok, false);
  assert.match(r.error, /드로어가 열려 있습니다/);
  page.w.close();
});

test('S9 · 시즌 창 모듈의 머리글이 페이지 작업 둘을 댄다', () => {
  assert.match(readFileSync(join(SKILL, 'scripts', 'page', 'stay_price_season.js'), 'utf8'), /stayPriceSeason\.readSeason\(/);
});
