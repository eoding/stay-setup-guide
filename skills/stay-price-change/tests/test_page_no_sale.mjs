// B12 판매일 없는 날 — readPair 는 그 객실·요금제 달력의 칸으로 열린 날을 먼저 알고, 열린 날만 가격 수정 창에 고르며,
// 나머지는 「판매일 없음」으로 알린다. 캡처한 7월 판은 1일만 열려 있다(다른 날은 「판매일 없음」 칸).
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { erpPage, inPage, plain, takeAll, runFixture, SKILL, OFFER, HOTEL } from './page_harness.mjs';

const ALL_WEEK = ['월', '화', '수', '목', '금', '토', '일'];
const ASK = (from, to) => ({ hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from, to, weekdays: ALL_WEEK });
function sentRanges(page) {
  const sent = [];
  page.doc.addEventListener('click', (e) => {
    if (e.target.matches('[data-stay-screen="calendar-bulk"][data-calendar-selection] [data-stay-action="next"]')) {
      sent.push(page.doc.querySelector('[data-stay-screen="calendar-bulk"] [name="date_selection_0"]').value);
    }
  }, true);
  return sent;
}

test('B12 · 판매일 없는 날이 끼어도 읽기가 통째로 실패하지 않는다 — 열린 날만 고르고 나머지는 「판매일 없음」', async () => {
  const page = erpPage();
  const sent = sentRanges(page);
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, ASK('2026-07-01', '2026-07-03'))));
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.days, { asked: 3, open: 1, noSale: 2 });
  assert.deepEqual(sent, ['2026-07-01'], '가격 수정 창에는 열린 날만 보냈다');
  const { body } = takeAll(page.w, r);
  assert.deepEqual(body.noSale, ['2026-07-02', '2026-07-03']);
  assert.ok(body.fragment.includes('2026-07-01'));
  page.w.close();
});

test('B12 · 고른 날이 모두 판매일 없음이면 창을 열지 않고 그 날들만 알린다', async () => {
  const page = erpPage();
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, ASK('2026-07-02', '2026-07-04'))));
  assert.equal(r.ok, true, r.error);
  assert.equal(r.clicks.bulkOpen, undefined, '가격 수정 창을 열지 않았다');
  const { body } = takeAll(page.w, r);
  assert.equal(body.fragment, null);
  assert.deepEqual(body.noSale, ['2026-07-02', '2026-07-03', '2026-07-04']);
  page.w.close();
});

test('B12 · 두 달에 걸치면 달마다 칸을 보고 열린 날만 구간 줄로 보내며, 파이썬이 판매일 없음을 건너뛰는 칸으로 셈한다', async () => {
  const page = erpPage({ echoDays: true, bulkReview: runFixture('calendar-bulk--price-step2.html').replaceAll('(공급 통화)', '(KRW)') });
  const sent = sentRanges(page);
  const ask = ASK('2026-07-01', '2026-08-31');
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, ask)));
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.days, { asked: 62, open: 2, noSale: 60 });
  assert.equal(r.clicks.month, 1, '8월로 한 번 넘겼다');
  assert.deepEqual(sent, ['2026-07-01\n2026-08-01']);
  const results = [r, ...takeAll(page.w, r).takes];
  const code = `import json, sys; sys.path.insert(0, ${JSON.stringify(join(SKILL, 'scripts'))})
from decimal import Decimal
import price_browser as b, erp_read as e, price_model as m, price_plan as p
reads = b.pair_reads(json.load(sys.stdin))
snap = e.build_snapshot("H", "t", reads)
req = m.ChangeRequest(hotel="H", offer=snap.offer, rooms=("디럭스",), rate_plans=("조식 포함",), dates=("2026-07-01", "2026-07-02", "2026-08-01"), operation="amount", value=Decimal("1000"))
plan = p.plan_change(snap, req)
print(json.dumps({"no_sale": len(snap.no_sale), "plan_no_sale": [d for _, _, d in plan.no_sale], "changed": sorted({c.key.date for c in plan.changes})}))`;
  const done = spawnSync('python3', ['-I', '-c', code], { input: JSON.stringify(results), encoding: 'utf8' });
  assert.equal(done.status, 0, done.stderr);
  assert.deepEqual(JSON.parse(done.stdout), { no_sale: 60, plan_no_sale: ['2026-07-02'], changed: ['2026-07-01', '2026-08-01'] });
  page.w.close();
});
