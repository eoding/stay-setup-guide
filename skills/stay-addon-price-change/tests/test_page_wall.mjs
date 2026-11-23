// A4 클릭 벽 — 부가옵션 작업마다 허용 목록 하나(look: 탭 · readLine: 탭 · 줄 [편집] · applyLine: 그리고 그 줄 창의 [저장] 한 번).
// 삭제 · 부가옵션 추가 · 가격 추가 · 정보 수집 폼 · 부가옵션 [편집] · 부가옵션 설정 저장 · 적용 범위 카드 · 보관 · 판매 시작/종료 · 다른 탭은
// 어느 작업에서도 막힌다. 러너 코드가 직접 부르는 `.click()` 도 걸린다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { addonPage, inPage, plain, takeAll, HOTEL, TABS } from './addon_harness.mjs';

const OPS = ['look', 'readLine', 'applyLine'];
const PINS = { hotel: HOTEL.id, addon: '201', line: '301' };
// [이름, 그릴 창(없으면 그대로), 고르개]
const NEVER_TARGETS = [
  ['가격 줄 [삭제]', null, '#stay_addons tr[data-stay-entity-id="301"] [data-stay-action="delete"]'],
  ['부가옵션 [삭제]', null, '[data-stay-entity-id="201"] .stay-addon__actions [data-stay-action="delete"]'],
  ['[부가옵션 추가]', null, '.stay-panel-intro [data-stay-action="open_create"]'],
  ['[가격 추가]', null, '[data-stay-entity-id="201"] .stay-addon__actions [data-stay-action="open_create"]'],
  ['[정보 수집 폼]', null, '[data-stay-entity-id="201"] [data-stay-action="open_questions"]'],
  ['부가옵션 [편집]', null, '[data-stay-entity-id="201"] .stay-addon__actions [data-stay-action="open_edit"]'],
  ['다른 탭의 hx-delete', null, '#stay_tab_charges [hx-delete]'],
  ['보관', null, '[data-stay-action="archive"]'],
  ['판매 종료', null, '[data-stay-action="end"]'],
  ['판매 시작', null, '[data-stay-action="activate"]'],
  ['부가옵션 설정 창의 [저장]', 'addon', '[data-stay-screen="addon"] [data-stay-action="save"]'],
  ['적용 범위 모드 select', 'price', '[data-stay-card="scope"] select[name="scope_rate_plan_mode"]'],
  ['적용 범위 포함 체크', 'price', '[data-stay-card="scope"] input[name="scope_room_include"]'],
  ['적용 범위 체크의 글자(label)', 'price', '[data-stay-card="scope"] label.check_form span'],
  ['범위 비움 확인 체크', 'price', '[data-stay-card="scope"] input[name="scope_confirm_deny_all"]']
];

test('A4 · 금지 단추와 칸은 어느 작업에서도 막히고, 화면(서버)까지 닿지 않으며, 무엇을 왜 막았는지 적힌다', async () => {
  for (const op of OPS) {
    for (const [name, show, sel] of NEVER_TARGETS) {
      const page = addonPage();
      if (show === 'addon') page.showAddon('201');
      if (show === 'price') page.showPrice('301');
      const el = page.doc.querySelector(sel);
      assert.ok(el, `${name}: 과녁이 화면에 있다`);
      const target = el.querySelector('span') || el;   // 단추 안의 글자를 눌러도 단추로 본다
      const seen = plain(await page.w.stayAddonPrice.guard(op, async () => { target.click(); }, PINS));
      assert.ok(seen.blocked.length >= 1, `${op} · ${name}: 막혔다`);
      assert.deepEqual(seen.clicks, [], `${op} · ${name}: 지나간 클릭이 없다`);
      assert.deepEqual([page.log.reached, page.log.posts], [[], []], `${op} · ${name}: 화면에 닿지 않았다`);
      assert.match(seen.blocked[0].why, /이 도우미는 누르지 않습니다$/, `${op} · ${name}: 금지 목록이 막았다`);
      page.w.close();
    }
  }
});

test('A4 · [부가옵션] 말고 다른 탭은 모두 막힌다(표식 없는 [기본정보] 도)', async () => {
  for (const op of OPS) {
    const page = addonPage({ tab: 'calendar' });
    const others = TABS.filter(([, name]) => name !== 'addons');
    const seen = plain(await page.w.stayAddonPrice.guard(op, async () => {
      for (const [href] of others) page.doc.querySelector(`ul.tab-container a[href="${href}"]`).click();
      page.doc.querySelector('ul.tab-container a[data-stay-tab="addons"]').click();
    }, PINS));
    assert.equal(seen.blocked.length, others.length, op);
    assert.ok(seen.blocked.every((b) => /^다른 탭/.test(b.why)), op);
    assert.deepEqual(seen.clicks, ['tab'], `${op}: [부가옵션] 탭은 지나간다`);
    assert.deepEqual(page.log.reached, ['stay-tab=addons'], op);
    page.w.close();
  }
});

test('A4 · 줄 [편집] 은 고른 카드의 고른 줄만, 창의 [저장] 은 그 호텔 · 그 줄의 창에서 한 번만 지나간다', async () => {
  const page = addonPage();
  const edit = (line) => page.doc.querySelector(`#stay_addons tr[data-stay-entity-id="${line}"] [data-stay-action="open_edit"]`);
  const opened = plain(await page.w.stayAddonPrice.guard('applyLine', async () => {
    edit('302').click();
    edit('305').click();
    edit('301').click();
  }, PINS));
  assert.deepEqual(opened.clicks, ['lineOpen']);
  assert.equal(opened.blocked.length, 2);
  assert.ok(opened.blocked.every((b) => /고른 대상이 아닙니다\(lineOpen\)/.test(b.why)));
  assert.deepEqual(page.log.gets, ['/stay/1/addon-prices/301/edit/']);
  const save = () => page.doc.querySelector('#stay_drawer_body [data-stay-action="save"]').click();
  // 첫 저장이 창을 닫는다 — 같은 창을 다시 그려 한 번 더 눌러 본다. sent 는 fill 이 핀에 두는 보낼 칸(여기서는 친 것 없이 창 그대로)
  const sent = page.w.stayPageKit.sent(page.doc.querySelector('#stay_drawer_body [data-stay-screen="addon-price"]'));
  const saved = plain(await page.w.stayAddonPrice.guard('applyLine', async () => { save(); page.showPrice('301'); save(); }, Object.assign({ sent }, PINS)));
  assert.deepEqual(saved.clicks, ['lineSave']);
  assert.match(saved.blocked[0].why, /같은 저장을 다시 누르지 않습니다/);
  assert.equal(page.log.posts.length, 1, '저장 요청은 하나');
  for (const wrong of [{ line: '302' }, { hotel: '2' }, { line: undefined }]) {
    page.showPrice('301');
    const other = plain(await page.w.stayAddonPrice.guard('applyLine', async () => { save(); }, Object.assign({}, PINS, wrong)));
    assert.deepEqual(other.clicks, [], JSON.stringify(wrong));
    assert.match(other.blocked[0].why, /고른 대상이 아닙니다\(lineSave\)/, JSON.stringify(wrong));
  }
  assert.equal(page.log.posts.length, 1, '다른 줄 · 다른 호텔로 짚은 저장은 나가지 않았다');
  page.w.close();
});

test('A4 · 읽는 작업(look · readLine)에는 저장이 없다', async () => {
  for (const op of ['look', 'readLine']) {
    const page = addonPage();
    page.showPrice('301');
    const seen = plain(await page.w.stayAddonPrice.guard(op, async () => {
      page.doc.querySelector('#stay_drawer_body [data-stay-action="save"]').click();
    }, PINS));
    assert.equal(seen.blocked.length, 1, op);
    assert.match(seen.blocked[0].why, /허용 목록에 없습니다/, op);
    assert.deepEqual(page.log.posts, [], op);
    page.w.close();
  }
});

test('A4 · 작업 중 러너 코드가 직접 부르는 .click() 도 막히고, 그 작업은 저장하지 않고 멈춘다', async () => {
  const page = addonPage();
  const read = plain(await page.w.stayAddonPrice.readLine(inPage(page.w, { hotel: HOTEL, addon: '201', line: '301' })));
  const form = takeAll(page.w, read).body.window.form;
  const calSet = page.w.calSet;
  page.w.calSet = function (el, value) {   // 칸을 치는 러너 부품이 그 김에 줄 [삭제] 를 누른다고 치자
    page.doc.querySelector('#stay_addons tr[data-stay-entity-id="301"] [data-stay-action="delete"]').click();
    return calSet(el, value);
  };
  const r = plain(await page.w.stayAddonPrice.applyLine(inPage(page.w, { no: 1, hotel: HOTEL, addon: '201', line: '301', form, set: { price: '22.00' } })));
  assert.deepEqual([r.ok, r.saved, r.pressed], [false, false, false]);
  assert.match(r.error, /허용 목록에 없는 클릭을 막았습니다: .*data-stay-action=delete.*\(삭제 — 이 도우미는 누르지 않습니다\)/);
  assert.deepEqual(page.log.posts, [], '삭제도 저장도 나가지 않았다');
  assert.ok(!page.log.reached.includes('stay-action=delete'));
  page.w.close();
});

test('A4 · 작업 밖에서는 가격 도우미의 쉬는 벽이 스크립트 클릭을 막고, idle() 이 그것을 보인다', () => {
  const page = addonPage();
  page.doc.querySelector('#stay_addons tr[data-stay-entity-id="301"] [data-stay-action="open_edit"]').click();
  assert.deepEqual(page.log.reached, []);
  const idle = plain(page.w.stayAddonPrice.idle());
  assert.deepEqual([idle.idle, idle.count], [true, 1]);
  page.w.close();
});

test('A4 · 허용 목록은 작업마다 표 한 장이고, 고르개에는 글자가 없다', () => {
  const page = addonPage();
  const ap = page.w.stayAddonPrice;
  assert.deepEqual(plain(ap.ALLOW), { look: ['tab'], readLine: ['tab', 'lineOpen'], applyLine: ['tab', 'lineOpen', 'lineSave'] });
  for (const op of Object.keys(ap.ALLOW)) for (const name of ap.ALLOW[op]) assert.ok(ap.CONTROLS[name], `${op}: ${name}`);
  assert.equal(ap.CONTROLS.lineSave.max, 1);
  for (const name of Object.keys(ap.CONTROLS)) assert.ok(!/[가-힣]/.test(ap.CONTROLS[name].sel), name);
  for (const entry of ap.NEVER) assert.ok(!/[가-힣]/.test(entry.sel), entry.why);
  page.w.close();
});
