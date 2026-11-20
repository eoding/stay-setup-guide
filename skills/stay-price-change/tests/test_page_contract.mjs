// 파이썬 ↔ 페이지 약속 — 파이썬이 만든 부를 값을 페이지가 그대로 받고, 페이지의 답을 파이썬이 그 물음의 답으로 받는다(B5 · B6 · B7).
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { erpPage, inPage, plain, takeAll, HERE, SKILL, OFFER } from './page_harness.mjs';

// price_browser 의 함수 하나를 부른다 — 값은 표준 입력 JSON 으로 주고받는다
function python(fn, args) {
  const code = `import json, sys; sys.path.insert(0, ${JSON.stringify(join(SKILL, 'scripts'))})\n`
    + 'import price_browser as b\nargs = json.load(sys.stdin)\n'
    + `out = ${fn}\nprint(json.dumps(out, ensure_ascii=False, default=str))`;
  const done = spawnSync('python3', ['-I', '-c', code], { input: JSON.stringify(args), encoding: 'utf8' });
  assert.equal(done.status, 0, done.stderr);
  return JSON.parse(done.stdout);
}

test('B7 · 장부의 저장 단계로 만든 부를 값을 페이지가 받아 저장하고, 그 답을 파이썬이 그 단계의 저장으로 받는다', async () => {
  const calls = JSON.parse(readFileSync(join(HERE, 'fixtures', 'browser', 'calls.json'), 'utf8'));
  for (const call of calls) {
    const page = erpPage();
    const r = plain(await page.w.stayPrice[call.op](inPage(page.w, call.payload)));
    assert.equal(r.saved, true, r.error);
    if (call.op === 'applyBulk') assert.equal(page.log.posts[0]['prices-0-price'], call.payload.rows[0].sell);
    else assert.equal(page.log.posts[0].original_price, '');
    assert.deepEqual(python('list(b.step_outcome(args["call"], args["result"]))', { call, result: r }), [true, r.note]);
    page.w.close();
  }
});

test('B5 · read_calls 의 부를 값으로 읽은 답을 price_pages 가 받는다', async () => {
  const [call] = python('b.read_calls(args["offer"], [("디럭스", "조식 포함")], ["2026-07-01"])', { offer: OFFER });
  const page = erpPage();
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, call)));
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(python('[[p.offer, p.room, p.rate_plan, sorted(p.days)] for p in b.price_pages(args)]', [r, ...takeAll(page.w, r).takes]),
    [[OFFER, `${OFFER} · 디럭스`, '조식 포함', ['2026-07-01']]]);
  page.w.close();
});

test('B6 · reserved_probes 의 물음을 페이지가 그대로 묻고, 그 답으로 reserved_round 가 끝난다', async () => {
  const probes = python('b.reserved_probes(args["offer"], [("디럭스", "조식 포함"), ("스위트", "룸온리")], ["2026-12-24", "2026-12-25"])', { offer: OFFER });
  const page = erpPage();
  const r = plain(await page.w.stayPrice.readReserved(inPage(page.w, probes[0])));
  assert.equal(r.ok, true, r.error);
  const round = python('(lambda r: {"done": r.done, "ask": r.ask, "reserved": sorted({(row.room, d) for p in r.pages for row in p.rejected if row.reason == "예약이 있는 날" for d in row.days})})(b.reserved_round(args["probes"], args["results"]))',
    { probes, results: [r, ...takeAll(page.w, r).takes] });
  assert.equal(round.done, true);
  assert.deepEqual(round.ask, []);
  assert.deepEqual(round.reserved, [['디럭스', '2026-12-24'], ['디럭스', '2026-12-25'], ['스위트', '2026-12-28']]);
  page.w.close();
});
