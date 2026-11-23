// B13 쉬는 벽 — 작업 밖에서도 stayPrice 가 올라 있으면 스크립트가 만든 클릭을 막는다. 사람이 누른 클릭은 지난다. standDown() 으로 내린다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { erpPage, inPage, plain, personClick, PAGE, OFFER, HOTEL } from './page_harness.mjs';

test('B13 · 작업 밖에서 러너 함수를 바로 불러도 아무것도 누르지 못한다', async () => {
  const page = erpPage();
  const chip = page.doc.querySelector('[data-stay-name="스위트 · 룸온리"]');
  const picked = plain(await page.w.calSelectChip(chip, '스위트 · 룸온리'));
  assert.match(picked.error, /이동하지 못했습니다/, '러너는 칩을 못 옮겼다고 답한다');
  page.doc.querySelector('#stay_calendar [data-calendar-bulk-action="price"]').click();
  page.doc.querySelector('#stay_calendar [data-calendar-bulk-action="close"]').click();
  assert.deepEqual(page.log.reached, [], '화면(서버)에 닿은 클릭이 없다');
  const idle = plain(page.w.stayPrice.idle());
  assert.equal(idle.idle, true);
  assert.equal(idle.count, 3);
  assert.match(idle.blocked.join(' / '), /스위트 · 룸온리.*data-calendar-bulk-action=price.*data-calendar-bulk-action=close/);
  page.w.close();
});

test('B13 · 사람이 누른 클릭은 쉬는 벽을 지난다', () => {
  const page = erpPage();
  personClick(page.w, page.doc.querySelector('ul.tab-container a[data-stay-tab="offers"]'));
  personClick(page.w, page.doc.querySelector('[data-stay-name="스위트 · 룸온리"]'));
  assert.deepEqual(page.log.reached, ['stay-tab=offers', 'stay-action=goto']);
  assert.equal(plain(page.w.stayPrice.idle()).count, 0);
  page.w.close();
});

test('B13 · standDown() 하나로 내리고, standUp() 이나 다시 올리면 선다', () => {
  const page = erpPage();
  const button = page.doc.querySelector('#stay_calendar [data-calendar-bulk-action="price"]');
  assert.equal(plain(page.w.stayPrice.standDown()).idle, false);
  button.click();
  assert.deepEqual(page.log.reached, ['calendar-bulk-action=price'], '내린 뒤에는 스크립트 클릭이 닿는다');
  page.closeDrawer();
  page.w.stayPrice.standUp();
  button.click();
  assert.equal(page.log.reached.length, 1, '다시 세우면 막는다');
  page.w.stayPrice.standDown();
  page.w.eval(PAGE);
  button.click();
  assert.equal(page.log.reached.length, 1, '파일을 다시 올리면 다시 선다');
  page.w.close();
});

test('B13 · 작업 중에는 그 작업의 허용 목록이 판단하고, 끝나면 쉬는 벽으로 돌아온다', async () => {
  const page = erpPage();
  const ALL_WEEK = ['월', '화', '수', '목', '금', '토', '일'];
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, { hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01', weekdays: ALL_WEEK })));
  assert.equal(r.ok, true, r.error);
  const reached = page.log.reached.length;
  page.doc.querySelector('#stay_calendar [data-calendar-bulk-action="price"]').click();
  assert.equal(page.log.reached.length, reached, '작업이 끝난 뒤 스크립트 클릭은 다시 막힌다');
  page.w.close();
});

// 브라우저의 사람 움직임 표지 — 사람이 누른 뒤 몇 초 켜진다. jsdom 에는 없어 시험이 세운다
const activation = (w, on) => Object.defineProperty(w.navigator, 'userActivation', { configurable: true, value: { isActive: on, hasBeenActive: true } });

test('A4 · 작업 밖에서 사람이 방금 움직였으면 화면 스크립트의 클릭(확인창이 누르는 저장 · 탭 링크)이 지나고, 아니면 막힌다', () => {
  const page = erpPage();
  const save = page.doc.querySelector('#stay_calendar [data-calendar-bulk-action="price"]');
  activation(page.w, false);
  save.click();
  assert.deepEqual(page.log.reached, [], '사람이 움직이지 않았을 때(도구의 스크립트) 스크립트 클릭은 막힌다');
  assert.equal(plain(page.w.stayPrice.idle()).count, 1);
  // 사람이 누른 [그래도 새로 만들기] 의 처리 안에서 ERP 가 저장 단추를 `.click()` 한다 — 그 클릭은 isTrusted 가 아니지만 사람이 방금 움직였다
  const confirm = page.doc.createElement('button');
  confirm.textContent = '그래도 새로 만들기';
  page.doc.body.appendChild(confirm);
  confirm.addEventListener('click', () => { activation(page.w, true); save.click(); });
  personClick(page.w, confirm);
  assert.deepEqual([...page.log.reached].sort(), ['button', 'calendar-bulk-action=price'], '사람의 클릭과 그것이 부른 화면 스크립트의 클릭이 닿았다');
  assert.equal(plain(page.w.stayPrice.idle()).count, 1, '더 막은 것이 없다');
  page.w.close();
});

test('A4 · 작업 안의 벽은 사람이 방금 움직였어도 허용 목록에 없는 스크립트 클릭을 막는다', async () => {
  const page = erpPage();
  activation(page.w, true);
  const close = page.doc.querySelector('#stay_calendar [data-calendar-bulk-action="close"]');
  const seen = await page.w.stayPrice.guard('readPair', () => { close.click(); });
  assert.deepEqual(plain(seen).blocked.map((b) => b.why), ['판매 마감·마감 해제 창 — 이 도우미는 누르지 않습니다']);
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});
