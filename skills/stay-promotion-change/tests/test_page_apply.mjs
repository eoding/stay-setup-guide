// M4 · M7 저장 — applyPromotion 은 표식 있는 창에서만, 창이 읽은 칸 · 단 표식과 꼭 같을 때만 set 의 단 값만 치고 저장을 한 번 누른다.
// 저장 요청은 읽은 form 에서 그 자리만 바꾼 것이다(진행기간 체크 · 숨은 칸 tiers_origin · 다른 단까지 그대로).
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { promotionPage, inPage, plain, takeAll, HOTEL, GATE, ORIGIN_UNKNOWN, DB } from './promotion_harness.mjs';

async function readWindow(page, offer, promotion) {
  const r = plain(await page.w.stayPromotion.readPromotion(inPage(page.w, { hotel: HOTEL, offer, promotion })));
  assert.equal(r.ok, true, r.error);
  return takeAll(page.w, r).body.window;
}
const titleOf = (form) => form.find(([name]) => name === 'title')[1];
function replaced(form, edits) {
  const seen = {};
  return form.map(([name, value]) => { const nth = seen[name] = (seen[name] ?? -1) + 1; const hit = edits.find(([n, i]) => n === name && i === nth); return [name, hit ? hit[2] : value]; });
}
// 창에 `typed` 칸을 치는 순간 htmx 요청 하나를 열고, 150ms 뒤 그 창의 `field` 칸(nth 번째)을 `value` 로 고쳐 쓰고, 300ms 뒤 요청을
// 닫는다 — 저장 단추가 도는 요청을 기다리는 사이(press 의 quiet) 무엇이 창을 바꾸는 것(앞 저장의 다시 읽기 · 화면 스크립트) 흉내
function rewriteWhileWaiting(page, typed, field, nth, value) {
  let done = false;
  const fire = (name) => page.doc.dispatchEvent(new page.w.CustomEvent(name, { detail: {}, bubbles: true }));
  page.doc.addEventListener('input', (e) => {
    if (done || e.target.name !== typed) return;
    done = true;
    fire('htmx:before:request');
    page.w.setTimeout(() => {
      const el = page.doc.querySelectorAll(`#stay_drawer_body [name="${field}"]`)[nth];
      el.value = value;
      el.dispatchEvent(new page.w.Event('input', { bubbles: true }));
    }, 150);
    page.w.setTimeout(() => fire('htmx:finally:request'), 300);
  });
}
async function apply(page, offer, promotion, win, set, extra = {}) {
  const input = Object.assign({ no: 1, hotel: HOTEL, offer, promotion, title: titleOf(win.form), form: win.form, marks: win.marks, set }, extra);
  return plain(await page.w.stayPromotion.applyPromotion(inPage(page.w, input)));
}

test('M4 · 두 단 할인율의 첫 단만 바꾸면 저장 요청은 읽은 form 에서 그 자리만 바뀐 것이고 저장 표지로 saved true 다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9002');
  const r = await apply(page, '601', '9002', win, [['tiers_value', 0, '8']]);
  assert.deepEqual([r.ok, r.saved, r.pressed], [true, true, true], r.error);
  assert.deepEqual(r.clicks, { promotionOpen: 1, promotionSave: 1 });
  assert.equal(page.log.posts.length, 1);
  assert.deepEqual(page.log.posts[0].pairs, replaced(win.form, [['tiers_value', 0, '8']]));
  assert.deepEqual(page.promotion('9002').trigger.tiers, [{ threshold: 2, pct: '8' }, { threshold: 3, pct: '10' }]);
  page.w.close();
});

test('M4 · 전 오퍼 공통 프로모션의 진행기간 제한은 켜진 채, 중복 허용도 켜진 채 간다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '0', '9006');
  const r = await apply(page, '0', '9006', win, [['tiers_value', 0, '6']]);
  assert.equal(r.saved, true, r.error);
  const sent = page.log.posts[0].pairs;
  assert.deepEqual(sent, replaced(win.form, [['tiers_value', 0, '6']]));
  assert.ok(sent.some(([n, v]) => n === 'promotion_apply_flag' && v === 'on'));
  assert.equal(page.promotion('9006').apply_flag, true);
  page.w.close();
});

test('M4 · 화면 밖 설정이 붙은 단은 숨은 칸 tiers_origin 이 그대로 가서 서버가 그 설정을 잇는다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9005');
  const r = await apply(page, '601', '9005', win, [['tiers_value', 0, '16']]);
  assert.equal(r.saved, true, r.error);
  assert.deepEqual(page.promotion('9005').trigger.tiers, [{ threshold: 46, pct: '16', cancellation: 'NRF' },
    { threshold: 31, pct: '10.0', cancellation: 'CUTOFF_AT_THRESHOLD' }]);
  page.w.close();
});

test('M4 · 표식 없는 창이면 아무것도 치지 않고 누르지 않는다 — 그 까닭을 쉬운 말로 말한다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9005');
  page.setKeeps(false);
  const bare = Object.assign({}, win, { form: win.form.filter(([name]) => name !== 'tiers_origin') });
  const r = await apply(page, '601', '9005', bare, [['tiers_value', 0, '16']]);
  assert.deepEqual([r.ok, r.saved, r.pressed, r.refused, r.gate], [false, false, false, true, true]);
  assert.ok(r.error.startsWith(GATE), r.error);
  assert.deepEqual([page.log.typed, page.log.posts], [[], []]);
  page.w.close();
});

test('W4 · 단 줄의 숨은 칸 tiers_origin 이 「?」(ERP 가 그 줄의 저장된 단을 모름 — 거절된 요청 뒤 다시 그린 창)인 창에서는 아무것도 치지 않고 창을 다시 열라고 한다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9005');
  page.setOrigin('?');
  const r = await apply(page, '601', '9005', win, [['tiers_value', 0, '16']]);
  assert.deepEqual([r.ok, r.saved, r.pressed, r.refused], [false, false, false, true]);
  assert.ok(r.error.startsWith(ORIGIN_UNKNOWN), r.error);
  assert.match(r.error, /편집 창을 닫았다가 다시 열어/);
  assert.deepEqual([page.log.typed, page.log.posts], [[], []]);
  page.setOrigin(undefined);
  const ok = await apply(page, '601', '9005', win, [['tiers_value', 0, '16']]);
  assert.equal(ok.saved, true, ok.error);
  page.w.close();
});

test('P6 · 단 줄의 숨은 칸 tiers_origin 이 그 줄이 실려 온 단의 기준값이 아니면(「?」 · 빈 값 · 다른 단의 기준값 · ERP 가 더할 다른 표시) 명령이 그 창을 읽은 그대로 넘겨도 페이지가 치지 않는다', async () => {
  const notOwn = '이 프로모션의 편집 창은 할인 단 1번째 줄이 어느 저장된 단에서 왔는지 도우미가 알아볼 수 없어(숨은 칸이 그 줄의 기준값이 아닙니다), 저장하면 화면에 안 보이는 설정이 다른 단에 붙거나 빠질 수 있어 도우미가 저장하지 않습니다 — 아무것도 치지 않았고 누르지 않았습니다';
  for (const [origin, said] of [['?', ORIGIN_UNKNOWN], ['', notOwn], ['31', notOwn], ['46.0', notOwn], ['stored:none', notOwn]]) {
    const page = promotionPage();
    page.setOrigin(origin);
    const win = await readWindow(page, '601', '9005');
    assert.equal(win.form.find(([name]) => name === 'tiers_origin')[1], origin, '읽은 창이 그 값을 들고 있다');
    const r = await apply(page, '601', '9005', win, [['tiers_value', 0, '16']]);
    assert.deepEqual([r.ok, r.saved, r.pressed, r.refused], [false, false, false, true], JSON.stringify(origin));
    assert.ok(r.error.startsWith(said.slice(0, 150)), `${JSON.stringify(origin)}: ${r.error}`);
    assert.deepEqual([page.log.typed, page.log.posts], [[], []], JSON.stringify(origin));
    page.w.close();
  }
});

test('M4 · 단 줄의 화면 밖 설정 이름이 읽은 것과 다르면 아무것도 치지 않는다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9005');
  delete page.promotion('9005').trigger.tiers[1].cancellation;
  const r = await apply(page, '601', '9005', win, [['tiers_value', 0, '16']]);
  assert.deepEqual([r.saved, r.pressed, r.refused], [false, false, true]);
  assert.match(r.error, /단 표식/);
  assert.deepEqual([page.log.typed, page.log.posts], [[], []]);
  page.w.close();
});

test('M4 · 창이 읽은 값과 다른 단 값을 보이면 아무것도 치지 않고 누르지 않는다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9002');
  page.promotion('9002').trigger.tiers[1].pct = '11';
  const r = await apply(page, '601', '9002', win, [['tiers_value', 0, '8']]);
  assert.deepEqual([r.saved, r.pressed, r.refused], [false, false, true]);
  assert.deepEqual(r.differ, ['tiers_value']);
  assert.deepEqual([page.log.typed, page.log.posts], [[], []]);
  page.w.close();
});

test('M4 · set 에는 단의 값 칸만, 숫자 글자만, 빈 칸이 아닌 자리만 — 아니면 창을 열지도 않는다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9002');
  for (const set of [[['tiers_threshold', 0, '5']], [['title', 0, 'x']], [['tiers_value', 0, '']], [['tiers_value', 0, '-1']],
    [['tiers_value', 5, '8']], [['tiers_value', 0, '8'], ['tiers_value', 0, '9']]]) {
    const r = await apply(page, '601', '9002', win, set);
    assert.deepEqual([r.ok, r.saved, r.pressed], [false, false, false], JSON.stringify(set));
  }
  assert.deepEqual(page.log.posts, []);
  page.w.close();
});

test('M4 · 서버가 거절하면 saved false 이고, 응답이 없으면 "unknown" 이며 다시 누르지 않는다', async () => {
  for (const [mode, saved] of [['refuse', false], ['silent', 'unknown']]) {
    const page = promotionPage({ onSave: mode });
    const win = await readWindow(page, '601', '9003');
    const r = await apply(page, '601', '9003', win, [['tiers_value', 0, '25']]);
    assert.deepEqual([r.saved, r.pressed], [saved, true], mode);
    assert.equal(page.log.posts.length, 1, `${mode}: 한 번만 눌렀다`);
    page.w.close();
  }
});

test('M4 · ERP 가 단을 짚어 저장을 거절하면(화면 밖 설정을 이을 단을 정할 수 없음) saved false 이고 그 글을 그대로 돌려주며 다시 누르지 않는다', async () => {
  const refusal = '발동 조건을 바꾸면 기준값 46 단에 저장된 화면에 없는 설정(cancellation)의 뜻이 달라집니다 — 발동 조건을 되돌리거나, 그 단을 지우고 새로 넣어 그 설정 없이 저장하세요';
  const page = promotionPage({ onSave: 'refuse', refusal });
  const win = await readWindow(page, '601', '9005');
  const r = await apply(page, '601', '9005', win, [['tiers_value', 0, '16']]);
  assert.deepEqual([r.ok, r.saved, r.pressed], [false, false, true]);
  assert.ok(r.error.includes('기준값 46 단'), r.error);
  assert.match(r.errors[0], /^발동 조건을 바꾸면 기준값 46 단/);
  assert.equal(page.log.posts.length, 1);
  assert.deepEqual(page.promotion('9005').trigger.tiers[0], { threshold: 46, pct: '15.0', cancellation: 'NRF' }, '저장되지 않았다');
  page.w.close();
});

test('P1 · 친 뒤 저장 단추가 도는 요청을 기다리는 사이 창의 다른 단 값이 바뀌면 벽이 그 클릭을 막는다 — 요청이 나가지 않고 창이 바뀌었다고 말한다', async () => {
  const page = promotionPage();
  const win = await readWindow(page, '601', '9002');
  rewriteWhileWaiting(page, 'tiers_value', 'tiers_value', 1, '50');
  const r = await apply(page, '601', '9002', win, [['tiers_value', 0, '8']]);
  assert.deepEqual([r.ok, r.saved, r.pressed, r.refused], [false, false, false, true], r.error);
  assert.ok(r.error.startsWith('친 뒤에 창이 바뀌었습니다(tiers_value) — 저장을 누르지 않았습니다'), r.error);
  assert.match(r.blocked[0].why, /^친 뒤에 창이 바뀌었습니다\(tiers_value\)$/);
  assert.deepEqual(r.clicks, { promotionOpen: 1 });
  assert.deepEqual(page.log.posts, [], '저장 요청이 나가지 않았다');
  assert.deepEqual(page.promotion('9002').trigger.tiers, [{ threshold: 2, pct: '7' }, { threshold: 3, pct: '10' }], '저장된 단 그대로');
  page.w.close();
});

test('M7 · 한 작업 안에서 저장 단추를 두 번 누르면 두 번째는 벽이 막는다(서버가 아직 답하지 않아 창이 그대로일 때)', async () => {
  const page = promotionPage({ onSave: 'silent' });
  const root = page.showPromotion('9002');
  const save = root.querySelector('[data-stay-action="save"]');
  // sent — fill 이 친 뒤 핀에 두는 보낼 칸(여기서는 친 것 없이 창 그대로)
  const seen = plain(await page.w.stayPromotion.guard('applyPromotion', async () => { save.click(); save.click(); },
    { hotel: HOTEL.id, offer: '601', promotion: '9002', sent: page.w.stayPageKit.sent(root) }));
  assert.deepEqual(seen.clicks, ['promotionSave']);
  assert.equal(seen.blocked.length, 1);
  assert.match(seen.blocked[0].why, /같은 저장을 다시 누르지 않습니다/);
  assert.equal(page.log.posts.length, 1, '서버에 닿은 저장은 하나다');
  page.w.close();
});

test('M7 · 표식 없는 창의 [저장] 은 벽이 막는다(누르는 순간 그 창의 표식을 본다)', async () => {
  const page = promotionPage({ keeps: false });
  const root = page.showPromotion('9002');
  const seen = plain(await page.w.stayPromotion.guard('applyPromotion', async () => { root.querySelector('[data-stay-action="save"]').click(); },
    { hotel: HOTEL.id, offer: '601', promotion: '9002' }));
  assert.deepEqual(seen.clicks, []);
  assert.match(seen.blocked[0].why, /이 작업이 고른 대상이 아닙니다\(promotionSave\)/);
  assert.deepEqual(page.log.posts, []);
  page.w.close();
});

test('P2 · 결과를 못 본 저장을 ERP 가 늦게 거절해도(거절된 창이 닫힌 드로어에 남음) 다음 작업이 돌고, 다음 읽기 답의 late 가 그 거절 글을 그 저장의 결과로 한 번 말한다', async () => {
  const refusal = '이 프로모션의 적용 범위가 맞지 않습니다 — 저장하지 않았습니다';
  const page = promotionPage({ onSave: 'late', lateMs: 2500, refusal });
  const win = await readWindow(page, '601', '9003');
  page.w.stayPrice.config({ budgetMs: 1500, hardMs: 2000, restMs: 500 });
  const r = await apply(page, '601', '9003', win, [['tiers_value', 0, '25']]);
  assert.deepEqual([r.saved, r.pressed], ['unknown', true], r.error);
  const body = page.doc.getElementById('stay_drawer_body');
  assert.ok(await page.w.stayRun.waitFor(() => !!body.firstElementChild && !(page.w.stayRun.hx.pending > 0), 5000), '거절된 창이 늦게 들어왔다');
  assert.equal(page.drawerOpen(), false, '드로어는 닫힌 채다');
  const look = plain(await page.w.stayPromotion.look());
  assert.equal(look.ok, true, look.error);
  assert.equal(look.late, undefined, '보기 답에는 싣지 않는다(읽기가 싣는다)');
  assert.equal(body.firstElementChild, null, '닫힌 드로어의 남은 창을 비웠다');
  const read = plain(await page.w.stayPromotion.readPromotion(inPage(page.w, { hotel: HOTEL, offer: '601', promotion: '9003' })));
  assert.equal(read.ok, true, read.error);
  assert.equal(read.late, `앞서 저장됐는지 알 수 없던 1번째 저장은 ERP 가 거절했습니다 — ${refusal}`);
  const again = plain(await page.w.stayPromotion.readPromotion(inPage(page.w, { hotel: HOTEL, offer: '601', promotion: '9003' })));
  assert.deepEqual([again.ok, again.late], [true, undefined], '한 번만 말한다');
  assert.equal(page.promotion('9003').trigger.tiers[0].amount, '20', '저장되지 않았다');
  page.w.close();
});

test('P3 · 이름에 빈칸 둘 · 끝 빈칸 · 풀어 쓴 한글(NFD)이 든 프로모션도 저장한다(명령은 목록의 이름을 준다) — 다른 이름이면 여전히 거절한다', async () => {
  const name = '롱스테이 2박 7% / 3박 10%';
  for (const raw of ['롱스테이  2박 7% / 3박 10%', `${name} `, name.normalize('NFD')]) {
    const db = JSON.parse(JSON.stringify(DB));
    db.cards.flatMap((card) => card.promotions).find((p) => p.id === '9002').title = raw;
    const page = promotionPage({ db });
    const win = await readWindow(page, '601', '9002');
    const r = await apply(page, '601', '9002', win, [['tiers_value', 0, '8']], { title: name });
    assert.equal(r.saved, true, `${JSON.stringify(raw)}: ${r.error}`);
    assert.equal(page.log.posts[0].pairs.find(([n]) => n === 'title')[1], raw, '창의 이름 칸은 날 글자 그대로 나간다');
    page.w.close();
  }
  const page = promotionPage();
  const win = await readWindow(page, '601', '9002');
  const r = await apply(page, '601', '9002', win, [['tiers_value', 0, '8']], { title: '롱스테이 2박 8% / 3박 10%' });
  assert.deepEqual([r.saved, r.pressed, r.refused], [false, false, true]);
  assert.match(r.error, /^창의 프로모션 이름이 고른 프로모션/);
  assert.deepEqual([page.log.typed, page.log.posts], [[], []]);
  page.w.close();
});
