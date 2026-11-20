// C3 · C7 클릭 벽 — 부과금 작업마다 허용 목록 하나(look: 탭 · readCharge: 탭 · 줄 [편집] · applyCharge: 그리고 그 부과금 창의 [저장]
// 한 번). 삭제 · 부과금 추가 · 정보 수집 폼 · 요율 행 추가·삭제 · 편집 창의 모든 고르기 · 적용 룸 체크 · 적용 범위 카드 · 보관 ·
// 판매 시작/종료 · 다른 탭은 어느 작업에서도 막힌다. 러너 코드가 직접 부르는 `.click()` 도 걸린다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { chargePage, inPage, plain, takeAll, HOTEL, TABS } from './charge_harness.mjs';

const OPS = ['look', 'readCharge', 'applyCharge'];
const PINS = { hotel: HOTEL.id, offer: '601', charge: '701' };
const IN_WINDOW = '#stay_drawer_body [data-stay-screen="charge"]';
// [이름, 그릴 창(부과금 번호, 없으면 그대로), 고르개]
const NEVER_TARGETS = [
  ['부과금 줄 [삭제]', null, '#stay_offer_charges tr[data-stay-entity-id="701"] [data-stay-action="delete"]'],
  ['[부과금 추가]', null, '[data-stay-entity="offer"][data-stay-entity-id="601"] [data-stay-action="open_create"]'],
  ['[정보 수집 폼]', null, '#stay_offer_charges tr[data-stay-entity-id="701"] [data-stay-action="open_questions"]'],
  ['다른 탭의 hx-delete', null, '#stay_tab_addons [hx-delete]'],
  ['보관', null, '[data-stay-action="archive"]'],
  ['판매 종료', null, '[data-stay-action="end"]'],
  ['판매 시작', null, '[data-stay-action="activate"]'],
  ['[요율 행 추가]', '701', `${IN_WINDOW} [data-stay-action="add_row"]`],
  ['그려진 시간대 행의 [삭제]', '701', `${IN_WINDOW} tr[data-stay-row="0"] [data-stay-action="remove_row"]`],
  ['종류', '701', `${IN_WINDOW} select[name="kind"]`],
  ['부과 방식', '701', `${IN_WINDOW} select[name="basis"]`],
  ['부과 단위', '701', `${IN_WINDOW} select[name="per"]`],
  ['정액 금액의 뜻', '701', `${IN_WINDOW} select[name="amount_mode"]`],
  ['정률의 뜻', '701', `${IN_WINDOW} select[name="pct_mode"]`],
  ['부과 유형', '701', `${IN_WINDOW} select[name="date_mode"]`],
  ['현장 결제 통화', '704', `${IN_WINDOW} select[name="onsite_currency"]`],
  ['시간대 행의 요율 방식', '701', `${IN_WINDOW} tr[data-stay-row="1"] select[name="tiers_basis"]`],
  ['시간대 행의 요율 방식 선택지', '701', `${IN_WINDOW} tr[data-stay-row="1"] select[name="tiers_basis"] option`],
  ['적용 룸 체크', '703', `${IN_WINDOW} input[name="room_scope"]`],
  ['적용 룸 체크의 글자(label)', '703', `${IN_WINDOW} [data-stay-card="main"] label.check_form span`],
  ['적용 범위 모드', '701', `${IN_WINDOW} [data-stay-card="scope"] select[name="scope_room_mode"]`],
  ['적용 범위 포함 체크', '701', `${IN_WINDOW} [data-stay-card="scope"] input[name="scope_room_include"]`],
  ['범위 비움 확인 체크', '701', `${IN_WINDOW} [data-stay-card="scope"] input[name="scope_confirm_deny_all"]`]
];

test('C3 · 금지 단추와 칸은 어느 작업에서도 막히고, 화면(서버)까지 닿지 않으며, 금지 목록이 막았다고 적힌다', async () => {
  for (const op of OPS) {
    for (const [name, show, sel] of NEVER_TARGETS) {
      const page = chargePage();
      if (show) page.showCharge(show);
      const el = page.doc.querySelector(sel);
      assert.ok(el, `${name}: 과녁이 화면에 있다`);
      const target = el.localName === 'button' ? (el.querySelector('span') || el) : el;
      const seen = plain(await page.w.stayCharge.guard(op, async () => { target.click(); }, PINS));
      assert.ok(seen.blocked.length >= 1, `${op} · ${name}: 막혔다`);
      assert.deepEqual(seen.clicks, [], `${op} · ${name}: 지나간 클릭이 없다`);
      assert.deepEqual([page.log.reached, page.log.posts], [[], []], `${op} · ${name}: 화면에 닿지 않았다`);
      assert.match(seen.blocked[0].why, /이 도우미는 누르지 않습니다$/, `${op} · ${name}: 금지 목록이 막았다`);
      page.w.close();
    }
  }
});

test('C3 · [부과금] 말고 다른 탭은 모두 막힌다(표식 없는 [기본정보] 도)', async () => {
  for (const op of OPS) {
    const page = chargePage({ tab: 'calendar' });
    const others = TABS.filter(([, name]) => name !== 'charges');
    const seen = plain(await page.w.stayCharge.guard(op, async () => {
      for (const [href] of others) page.doc.querySelector(`ul.tab-container a[href="${href}"]`).click();
      page.doc.querySelector('ul.tab-container a[data-stay-tab="charges"]').click();
    }, PINS));
    assert.equal(seen.blocked.length, others.length, op);
    assert.ok(seen.blocked.every((b) => /^다른 탭/.test(b.why)), op);
    assert.deepEqual(seen.clicks, ['tab'], `${op}: [부과금] 탭은 지나간다`);
    assert.deepEqual(page.log.reached, ['stay-tab=charges'], op);
    page.w.close();
  }
});

test('C7 · 줄 [편집] 은 고른 오퍼 카드의 고른 줄만, 창의 [저장] 은 그 호텔 · 그 부과금의 창에서 한 번만 지나간다', async () => {
  const page = chargePage();
  const edit = (id) => page.doc.querySelector(`#stay_offer_charges tr[data-stay-entity-id="${id}"] [data-stay-action="open_edit"]`);
  const opened = plain(await page.w.stayCharge.guard('applyCharge', async () => {
    edit('702').click();
    edit('705').click();
    edit('701').click();
  }, PINS));
  assert.deepEqual(opened.clicks, ['chargeOpen']);
  assert.equal(opened.blocked.length, 2);
  assert.ok(opened.blocked.every((b) => /고른 대상이 아닙니다\(chargeOpen\)/.test(b.why)));
  assert.deepEqual(page.log.gets, ['/stay/1/charges/701/edit/']);
  const wrongOffer = plain(await page.w.stayCharge.guard('applyCharge', async () => { edit('701').click(); }, Object.assign({}, PINS, { offer: '602' })));
  assert.match(wrongOffer.blocked[0].why, /고른 대상이 아닙니다\(chargeOpen\)/, '번호가 맞아도 다른 오퍼 카드로 짚었으면 막힌다');
  const save = () => page.doc.querySelector('#stay_drawer_body [data-stay-action="save"]').click();
  for (const wrong of [{ charge: '702' }, { hotel: '2' }, { charge: undefined }]) {
    page.showCharge('701');
    const other = plain(await page.w.stayCharge.guard('applyCharge', async () => { save(); }, Object.assign({}, PINS, wrong)));
    assert.deepEqual(other.clicks, [], JSON.stringify(wrong));
    assert.match(other.blocked[0].why, /고른 대상이 아닙니다\(chargeSave\)/, JSON.stringify(wrong));
  }
  assert.equal(page.log.posts.length, 0, '다른 부과금 · 다른 호텔로 짚은 저장은 나가지 않았다');
  page.w.close();
});

test('C7 · 읽는 작업(look · readCharge)에는 저장이 없다', async () => {
  for (const op of ['look', 'readCharge']) {
    const page = chargePage();
    page.showCharge('701');
    const seen = plain(await page.w.stayCharge.guard(op, async () => {
      page.doc.querySelector('#stay_drawer_body [data-stay-action="save"]').click();
    }, PINS));
    assert.equal(seen.blocked.length, 1, op);
    assert.match(seen.blocked[0].why, /허용 목록에 없습니다/, op);
    assert.deepEqual(page.log.posts, [], op);
    page.w.close();
  }
});

test('C7 · 작업 중 러너 코드가 직접 부르는 .click() 도 막히고, 그 작업은 저장하지 않고 멈춘다', async () => {
  const page = chargePage();
  const read = plain(await page.w.stayCharge.readCharge(inPage(page.w, { hotel: HOTEL, offer: '601', charge: '701' })));
  const form = takeAll(page.w, read).body.window.form;
  const calSet = page.w.calSet;
  page.w.calSet = function (el, value) {   // 칸을 치는 러너 부품이 그 김에 [요율 행 추가] 를 누른다고 치자
    page.doc.querySelector('#stay_drawer_body [data-stay-action="add_row"]').click();
    return calSet(el, value);
  };
  const r = plain(await page.w.stayCharge.applyCharge(inPage(page.w, { no: 1, hotel: HOTEL, offer: '601', charge: '701', name: form[1][1], form, set: [['tiers_pct', 1, '60.00']] })));
  assert.deepEqual([r.ok, r.saved, r.pressed], [false, false, false]);
  assert.match(r.error, /허용 목록에 없는 클릭을 막았습니다: .*data-stay-action=add_row.*\(요율 행 추가·삭제 — 이 도우미는 누르지 않습니다\)/);
  assert.deepEqual(page.log.posts, [], '저장이 나가지 않았다');
  page.w.close();
});

test('C7 · 작업 밖에서는 가격 도우미의 쉬는 벽이 스크립트 클릭을 막고, idle() 이 그것을 보인다', () => {
  const page = chargePage();
  page.doc.querySelector('#stay_offer_charges tr[data-stay-entity-id="701"] [data-stay-action="open_edit"]').click();
  assert.deepEqual(page.log.reached, []);
  const idle = plain(page.w.stayCharge.idle());
  assert.deepEqual([idle.idle, idle.count], [true, 1]);
  page.w.close();
});

test('C7 · 허용 목록은 작업마다 표 한 장이고, 고르개에는 글자가 없다', () => {
  const page = chargePage();
  const sc = page.w.stayCharge;
  assert.deepEqual(plain(sc.ALLOW), { look: ['tab'], readCharge: ['tab', 'chargeOpen'], applyCharge: ['tab', 'chargeOpen', 'chargeSave'] });
  for (const op of Object.keys(sc.ALLOW)) for (const name of sc.ALLOW[op]) assert.ok(sc.CONTROLS[name], `${op}: ${name}`);
  assert.equal(sc.CONTROLS.chargeSave.max, 1);
  for (const name of Object.keys(sc.CONTROLS)) assert.ok(!/[가-힣]/.test(sc.CONTROLS[name].sel), name);
  for (const entry of sc.NEVER) assert.ok(!/[가-힣]/.test(entry.sel), entry.why);
  page.w.close();
});
