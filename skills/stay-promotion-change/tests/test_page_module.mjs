// M7 페이지 모듈 — stay_promotion.js 는 가격 도우미의 kit(벽 · 작업 틀 · press · 답 거르기 · 조각 · 편집 창 부품)을 베끼지 않고 쓴다.
// 이 파일에는 클릭이 없고(`.click()` 은 kit 의 press 하나), 작업 셋과 읽기 셋만 내놓는다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { promotionPage, plain, PROMOTION } from './promotion_harness.mjs';

test('M7 · 이 파일에는 클릭이 없고 kit 의 부품을 베끼지 않는다(누르기는 kit 의 press 하나)', () => {
  assert.equal((PROMOTION.match(/\.click\(\)/g) || []).length, 0);
  for (const copy of ['function Wall(', 'function run(', 'function press(', 'function scrub(', 'function fill(', 'function saveOnce(']) {
    assert.equal(PROMOTION.includes(copy), false, `${copy} 를 베끼지 않는다`);
  }
});

test('M7 · stayPromotion 은 look · readPromotion · applyPromotion 과 take · last · idle · guard 를 내놓고, kit 없이는 서지 않는다', () => {
  const page = promotionPage();
  assert.deepEqual(Object.keys(page.w.stayPromotion).sort(),
    ['ALLOW', 'CONTROLS', 'NEVER', 'applyPromotion', 'guard', 'idle', 'last', 'look', 'readPromotion', 'take', 'version'].sort());
  assert.deepEqual(plain(page.w.stayPromotion.ALLOW), { look: ['tab'], readPromotion: ['tab', 'promotionOpen'], applyPromotion: ['tab', 'promotionOpen', 'promotionSave'] });
  page.w.close();
  const bare = promotionPage({ withPage: false, bare: true });
  assert.throws(() => bare.w.eval(PROMOTION), /stayPageKit 이 없습니다/);
  bare.w.close();
});
