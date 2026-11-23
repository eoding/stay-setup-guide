// B14 작업은 화면이 쉴 때 끝난다 · B15 호출 하나는 45초 안 — 시간이 다 되면 그 뒤로 아무것도 누르지 않고, 저장 여부를 모르면 "unknown".
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { erpPage, inPage, plain, bulkWas, OFFER, HOTEL } from './page_harness.mjs';

const ALL_WEEK = ['월', '화', '수', '목', '금', '토', '일'];
const PAIR = { hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01', weekdays: ALL_WEEK };
const BULK = { no: 1, hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', dates: ['2026-07-01'], rows: [{ occupancy: '', nights: 1, sell: '125000.00', was: bulkWas(['2026-07-01']) }] };
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const SAVE = '[data-stay-screen="calendar-bulk"] [data-stay-action="save"]';

test('B14 · readPair 는 드로어가 다 닫히고 내용까지 빈 뒤에 돌려준다(ERP 는 닫고 0.35초 뒤에 비운다)', async () => {
  const page = erpPage();
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, PAIR)));
  const body = page.doc.getElementById('stay_drawer_body');
  assert.equal(r.ok, true, r.error);
  assert.equal(r.rest, true);
  assert.equal(body.children.length, 0, '돌려받은 순간 드로어 내용이 비어 있다');
  assert.equal(page.drawerOpen(), false);
  const again = plain(await page.w.stayPrice.readPair(inPage(page.w, PAIR)));
  assert.equal(again.ok, true, '곧바로 다음 작업을 불러도 된다');
  page.w.close();
});

test('B14 · 드로어가 끝내 비지 않으면 결과에 그렇게 적고, 다음 작업은 정리되지 않은 화면에서 시작하지 않는다', async () => {
  const page = erpPage({ drawerStuck: true });
  page.w.stayPrice.config({ restMs: 600 });
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, PAIR)));
  assert.equal(r.ok, true, '읽은 값은 그대로 쓸 수 있다');
  assert.equal(r.rest, false);
  assert.ok(r.ms < 3000, `정리는 restMs 만큼만 기다린다: ${r.ms}ms`);
  assert.match(r.warn, /화면이 아직 정리되지 않았습니다/);
  const next = plain(await page.w.stayPrice.readPair(inPage(page.w, PAIR)));
  assert.equal(next.ok, false);
  assert.match(next.error, /앞 화면\(드로어·요청\)이 아직 정리되지 않았습니다/);
  assert.deepEqual(next.clicks, {}, '아무것도 누르지 않았다');
  assert.deepEqual([next.started, next.wait], [false, 5], 'G7 — 지나가는 까닭이라 시작하지 않은 작업으로 알린다');
  page.w.close();
});

test('B15 · 기본 시간 천장은 45초 안이고, config 로는 낮추기만 한다', () => {
  const page = erpPage();
  const limits = plain(page.w.stayPrice.config());
  assert.equal(limits.callMs, 45000);
  assert.ok(limits.hardMs + limits.restMs <= 40000, JSON.stringify(limits));
  assert.ok(limits.budgetMs <= limits.hardMs);
  assert.equal(plain(page.w.stayPrice.config({ hardMs: 60000 })).hardMs, limits.hardMs, '올리지 못한다');
  assert.equal(plain(page.w.stayPrice.config({ hardMs: 1000 })).hardMs, 1000);
  page.w.close();
});

test('B15 · 저장 요청이 끝나지 않으면 천장에서 돌려주고 "unknown"(다시 읽어 확인)이라 말한다', async () => {
  const page = erpPage({ onBulkSave: 'hang' });
  page.w.stayPrice.config({ hardMs: 1500, restMs: 300 });
  page.w.stayRun.config({ waitMs: 2500 });
  const t0 = Date.now();
  const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
  const took = Date.now() - t0;
  assert.ok(took < 2600, `천장 1.5초 + 정리 0.3초 안팎에서 돌려준다: ${took}ms`);
  assert.equal(r.saved, 'unknown');
  assert.equal(r.pressed, true);
  assert.equal(r.ok, false);
  assert.match(r.error, /알 수 없으니 다시 읽어 확인합니다/);
  assert.equal(page.log.posts.length, 1, '저장 요청은 한 번');
  const busy = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
  assert.match(busy.error, /앞 작업\(applyBulk\)이 아직 끝나지 않았습니다/, '뒤에 남은 러너가 끝날 때까지 다음 작업을 받지 않는다');
  for (let i = 0; i < 90 && page.w.__stayPriceBusy; i++) await pause(100);   // 러너의 저장 뒤 기다림(최대 5초)이 끝날 때까지
  assert.equal(page.w.__stayPriceBusy, null, '러너가 끝나면 다음 작업을 받는다');
  assert.equal(page.log.posts.length, 1, '그 사이에도 저장은 한 번뿐');
  page.w.close();
});

test('B15 · 천장 뒤에 러너가 이어서 누르려 해도 아무것도 눌리지 않고, 저장 전이었으면 "저장 안 됨"이다', async () => {
  const page = erpPage();
  page.w.stayPrice.config({ hardMs: 1200, restMs: 300 });
  const fill = page.w.stayRun.fill;   // 칸 치기가 늦어져 천장을 넘긴다 — 그 뒤의 [입력한 가격 적용] 클릭은 화면에 닿지 않아야 한다
  page.w.stayRun.fill = (fields) => new page.w.Promise((resolve) => page.w.setTimeout(() => resolve(fill(fields)), 1600));
  const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
  assert.equal(r.saved, false);
  assert.equal(r.pressed, false);
  assert.match(r.error, /안에 끝나지 않아 멈췄습니다/);
  const reached = page.log.reached.length;
  await pause(2500);
  assert.equal(page.log.reached.length, reached, '천장 뒤 남은 코드의 클릭(저장)은 화면에 닿지 않았다');
  assert.deepEqual(page.log.posts, []);
  page.w.close();
});
