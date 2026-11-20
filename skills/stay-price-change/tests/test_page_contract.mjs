// 파이썬 ↔ 페이지 약속 — 파이썬이 만든 부를 값을 페이지가 그대로 받고, 페이지의 답을 파이썬이 그 물음의 답으로 받는다(B5 · B6 · B7).
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { erpPage, inPage, plain, takeAll, runFixture, ownFixture, HERE, SKILL, OFFER } from './page_harness.mjs';

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
    assert.deepEqual(python('(lambda o: [o.saved, o.note])(b.step_outcome(args["call"], args["result"]))', { call, result: r }), [true, r.note]);
    page.w.close();
  }
});

test('G7 · 앞 화면이 아직 정리 중이면 저장 작업은 아무것도 누르지 않고 시작하지 않은 것으로 답하고, 파이썬은 그것을 실패로 셈하지 않는다', async () => {
  const [call] = JSON.parse(readFileSync(join(HERE, 'fixtures', 'browser', 'calls.json'), 'utf8')).filter((c) => c.op === 'applyBulk');
  const page = erpPage({ drawerStuck: true });
  page.w.stayPrice.config({ restMs: 600 });
  page.render('<div data-stay-screen="calendar-bulk">닫히는 중</div>');
  page.closeDrawer();
  const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, call.payload)));
  assert.deepEqual([r.ok, r.started, r.wait, r.no], [false, false, 5, call.no], r.error);
  assert.deepEqual(page.log.posts, [], '저장 단추를 누르지 않았다');
  assert.deepEqual(python('(lambda o: [o.saved, o.started, o.wait])(b.step_outcome(args["call"], args["result"]))', { call, result: r }), [null, false, 5]);
  page.w.close();
});

test('B5 · read_calls 의 부를 값으로 읽은 답을 pair_reads 가 받는다(객실은 칩의 이름, 드로어 이름은 옆에)', async () => {
  const [call] = python('b.read_calls(args["offer"], [("디럭스", "조식 포함")], ["2026-07-01"])', { offer: OFFER });
  const page = erpPage();
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, call)));
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(python('[[p.offer, p.room, p.rate_plan, p.page.room, sorted(p.page.days)] for p in b.pair_reads(args)]', [r, ...takeAll(page.w, r).takes]),
    [[OFFER, '디럭스', '조식 포함', `${OFFER} · 디럭스`, ['2026-07-01']]]);
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

test('B11 · 표시명이 있는 호텔 — 칩 이름으로 읽고 묻고, 스냅숏은 칩 이름으로 적고 드로어 이름을 옆에 둔다', async () => {
  const SHOWN = '디럭스 킹 (시티뷰)';
  const page = erpPage({
    panelEdit: (html) => html.replaceAll('data-stay-name="디럭스 · ', `data-stay-name="${SHOWN} · `),
    adjustSelectEdit: (html) => html.replace('<span>디럭스</span>', `<span>${SHOWN}</span>`),
    bulkReview: runFixture('calendar-bulk--price-step2.html').replaceAll('(공급 통화)', '(KRW)'),
    adjustReview: ownFixture('adjust-rejected.html').replaceAll('<td>디럭스</td>', `<td>${SHOWN}</td>`).replaceAll('<td>스위트</td>', `<td>${SHOWN}</td>`)
  });
  const [call] = python('b.read_calls(args["offer"], [(args["room"], "조식 포함")], ["2026-07-01"])', { offer: OFFER, room: SHOWN });
  const [probe] = python('b.reserved_probes(args["offer"], [(args["room"], "조식 포함")], ["2026-12-24", "2026-12-25"])', { offer: OFFER, room: SHOWN });
  const read = plain(await page.w.stayPrice.readPair(inPage(page.w, call)));
  assert.equal(read.ok, true, read.error);
  const reserved = plain(await page.w.stayPrice.readReserved(inPage(page.w, probe)));
  assert.equal(reserved.ok, true, reserved.error);
  const dir = mkdtempSync(join(tmpdir(), 'stay-price-names-'));
  try {
    const file = (name, data) => { const path = join(dir, name); writeFileSync(path, JSON.stringify(data)); return path; };
    const done = spawnSync('python3', [join(SKILL, 'scripts', 'price_change.py'), 'read', '--hotel', '데모 호텔',
      '--pair-result', file('pair.json', [read, ...takeAll(page.w, read).takes]),
      '--reserved-probes', file('probes.json', [probe]), '--reserved-result', file('reserved.json', [reserved, ...takeAll(page.w, reserved).takes])],
    { encoding: 'utf8', env: Object.assign({}, process.env, { STAY_PRICE_LEDGER_DIR: join(dir, 'ledger') }) });
    assert.equal(done.status, 0, done.stderr);
    const snapshot = JSON.parse(done.stdout);
    assert.deepEqual(snapshot.pairs, [{ room: SHOWN, rate_plan: '조식 포함' }]);
    assert.deepEqual(snapshot.room_names, [{ room: SHOWN, drawer: `${OFFER} · 디럭스` }]);
    assert.ok(snapshot.cells.every((cell) => cell.room === SHOWN));
    assert.ok(snapshot.reserved.some((item) => item.room === SHOWN && item.date === '2026-12-24'), JSON.stringify(snapshot.reserved));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
  page.w.close();
});
