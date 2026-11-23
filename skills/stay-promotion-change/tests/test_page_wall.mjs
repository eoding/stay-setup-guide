// M3 · M7 클릭 벽 — 프로모션 작업마다 허용 목록 하나(look: 탭 · readPromotion: 탭 · 줄 [편집] · applyPromotion: 그리고 그 프로모션 창의
// [저장] 한 번). 삭제 · 프로모션 추가 · 단 추가 · 단 삭제 · 편집 창의 모든 고르기와 체크 · 적용 범위 카드 · 보관 · 판매 시작/종료 · 다른
// 탭은 어느 작업에서도 막힌다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { promotionPage, plain, HOTEL } from './promotion_harness.mjs';

const OPS = ['look', 'readPromotion', 'applyPromotion'];
const PINS = { hotel: HOTEL.id, offer: '601', promotion: '9002' };
const IN_WINDOW = '#stay_drawer_body [data-stay-screen="promotion"]';
const NEVER_TARGETS = [
  ['프로모션 줄 [삭제]', null, '#stay_promotions tr[data-stay-entity-id="9002"] [data-stay-action="delete"]'],
  ['[프로모션 추가]', null, '[data-stay-entity="offer"][data-stay-entity-id="601"] [data-stay-action="open_create"]'],
  ['전 오퍼 공통 카드의 [프로모션 추가]', null, '#stay_promotions .stay-card:not([data-stay-entity]) [data-stay-action="open_create"]'],
  ['다른 탭의 hx-delete', null, '#stay_tab_charges [hx-delete]'],
  ['보관', null, '[data-stay-action="archive"]'],
  ['판매 종료', null, '[data-stay-action="end"]'],
  ['판매 시작', null, '[data-stay-action="activate"]'],
  ['[단 추가]', '9002', `${IN_WINDOW} [data-stay-action="add_row"]`],
  ['그려진 단 줄의 [삭제]', '9002', `${IN_WINDOW} tr[data-stay-row="0"] [data-stay-action="remove_row"]`],
  ['발동 조건', '9002', `${IN_WINDOW} select[name="trigger_type"]`],
  ['혜택 방식', '9002', `${IN_WINDOW} select[name="basis"]`],
  ['혜택 방식 선택지', '9002', `${IN_WINDOW} select[name="basis"] option`],
  ['적용 단위', '9002', `${IN_WINDOW} select[name="unit"]`],
  ['시즌 한정', '9007', `${IN_WINDOW} select[name="season"]`],
  ['요금제 한정', '9007', `${IN_WINDOW} select[name="rate_plan"]`],
  ['취소 정책', '9007', `${IN_WINDOW} select[name="cancellation_policy"]`],
  ['진행기간 제한 체크', '9006', `${IN_WINDOW} input[name="promotion_apply_flag"]`],
  ['진행기간 제한 체크의 글자', '9006', `${IN_WINDOW} [data-stay-card="scope_and_combination"] label.check_form span`],
  ['중복 허용 체크', '9006', `${IN_WINDOW} input[name="combinability"]`],
  ['적용 범위 모드', '9002', `${IN_WINDOW} [data-stay-card="scope"] select[name="scope_room_mode"]`],
  ['적용 범위 포함 체크', '9002', `${IN_WINDOW} [data-stay-card="scope"] input[name="scope_room_include"]`],
  ['범위 비움 확인 체크', '9002', `${IN_WINDOW} [data-stay-card="scope"] input[name="scope_confirm_deny_all"]`]
];

test('M3 · 금지 단추와 칸은 어느 작업에서도 막히고, 화면(서버)까지 닿지 않으며, 금지 목록이 막았다고 적힌다', async () => {
  for (const op of OPS) {
    for (const [name, show, sel] of NEVER_TARGETS) {
      const page = promotionPage();
      if (show) page.showPromotion(show);
      const el = page.doc.querySelector(sel);
      assert.ok(el, `${name}: 과녁이 화면에 있다`);
      const seen = plain(await page.w.stayPromotion.guard(op, async () => { el.click(); }, PINS));
      assert.ok(seen.blocked.length >= 1, `${op} · ${name}: 막혔다`);
      assert.deepEqual(seen.clicks, [], `${op} · ${name}: 지나간 클릭이 없다`);
      assert.deepEqual([page.log.reached, page.log.posts], [[], []], `${op} · ${name}: 화면에 닿지 않았다`);
      assert.match(seen.blocked[0].why, /이 도우미는 누르지 않습니다$/, `${op} · ${name}: 금지 목록이 막았다`);
      page.w.close();
    }
  }
});

test('M3 · [프로모션] 말고 다른 탭은 모두 막힌다(표식 없는 [기본정보] 도)', async () => {
  for (const op of OPS) {
    const page = promotionPage({ tab: 'calendar' });
    for (const a of page.doc.querySelectorAll('ul.tab-container a:not([data-stay-tab="promotions"])')) {
      const seen = plain(await page.w.stayPromotion.guard(op, async () => { a.click(); }, PINS));
      assert.equal(seen.blocked.length, 1, `${op} · ${a.textContent}`);
    }
    assert.deepEqual(page.log.reached, []);
    page.w.close();
  }
});

test('M3 · 읽는 작업에는 저장 단추가 없다 — readPromotion 에서 [저장] 은 허용 목록에 없다', async () => {
  const page = promotionPage();
  const root = page.showPromotion('9002');
  const seen = plain(await page.w.stayPromotion.guard('readPromotion', async () => { root.querySelector('[data-stay-action="save"]').click(); }, PINS));
  assert.deepEqual(seen.clicks, []);
  assert.match(seen.blocked[0].why, /허용 목록에 없습니다/);
  page.w.close();
});

test('M3 · 줄 [편집] 은 고른 카드 · 고른 프로모션의 것만 지난다 — 다른 줄, 같은 번호라도 다른 카드면 막힌다', async () => {
  const page = promotionPage();
  const other = page.doc.querySelector('#stay_promotions tr[data-stay-entity-id="9003"] [data-stay-action="open_edit"]');
  const seen = plain(await page.w.stayPromotion.guard('readPromotion', async () => { other.click(); }, PINS));
  assert.match(seen.blocked[0].why, /이 작업이 고른 대상이 아닙니다\(promotionOpen\)/);
  const common = page.doc.querySelector('#stay_promotions tr[data-stay-entity-id="9006"] [data-stay-action="open_edit"]');
  const wrongCard = plain(await page.w.stayPromotion.guard('readPromotion', async () => { common.click(); },
    { hotel: HOTEL.id, offer: '601', promotion: '9006' }));
  assert.equal(wrongCard.blocked.length, 1, '전 오퍼 공통 카드의 줄은 offer 0 으로만 지난다');
  const right = plain(await page.w.stayPromotion.guard('readPromotion', async () => { common.click(); },
    { hotel: HOTEL.id, offer: '0', promotion: '9006' }));
  assert.deepEqual(right.clicks, ['promotionOpen']);
  page.w.close();
});

test('M7 · 작업은 도우미를 통틀어 한 번에 하나다 — 부과금 도우미가 같은 탭에 올라 있어도 같은 바쁨 표지를 쓴다', async () => {
  const page = promotionPage({ withCharge: true });
  const first = page.w.stayPromotion.look();
  const second = plain(await page.w.stayCharge.look());
  assert.deepEqual([second.started, second.ok], [false, false]);
  assert.equal(plain(await first).ok, true);
  page.w.close();
});
