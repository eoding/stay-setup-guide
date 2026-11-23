// 파이썬 ↔ 시즌 창 모듈의 약속 — 페이지가 읽은 창(readSeason 의 답)을 파이썬 `season` 이 묶고, 파이썬이 그 창으로 만든 저장의 부를
// 값(applySeason)을 페이지가 그대로 받아 창에 쳐서 한 번 누르고, 그 답을 파이썬이 그 단계의 저장으로 받는다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { seasonPage, inPage, plain, takeAll, LAST_FILL, OFFER, IDS, HOTEL } from './season_harness.mjs';
import { SKILL } from './page_harness.mjs';

function python(code, args) {
  const prelude = `import json, sys; sys.path.insert(0, ${JSON.stringify(join(SKILL, 'scripts'))})\nargs = json.load(sys.stdin)\n`;
  const done = spawnSync('python3', ['-I', '-c', prelude + code], { input: JSON.stringify(args), encoding: 'utf8' });
  assert.equal(done.status, 0, done.stderr);
  return JSON.parse(done.stdout);
}

// 창 · 빈 칸 읽은 값 · 저장 하나(디럭스 두 요금제)로 계산하고, 첫 저장의 부를 값과 그 단계의 예상 수를 돌려준다
const PLAN = `
import price_season as ps
from change_core.answers import attach_bodies
from price_model import Snapshot
main = attach_bodies(args["answers"], page="stayPriceSeason")[0]
window = ps.window_of(main, {})
snap = Snapshot(window.hotel, window.offer, "KRW", "2026-11-23T10:00:00+09:00", {}, frozenset(),
                frozenset({("디럭스", "조식 포함"), ("디럭스", "룸온리")}), hotel_id=window.hotel_id, dates=window.dates)
save = ps.SeasonSave(pairs=(("디럭스", "조식 포함"), ("디럭스", "룸온리")), price="180000", occupancy_keys="A2,A3",
                     occupancy_adjust="A3:+30000", plan_adjust="-8000", child_extra=(("CHILD", ""), ("INFANT", "")))
fill = ps.SeasonFill(window.hotel, window.hotel_id, window.offer, window.season_id, window.season_name, "KRW", "", (save,))
plan = ps.plan_season(snap, window, fill, [ps.SeasonChoice(1, "NEW_ROW", "include", "응")])
steps = ps.season_steps(plan)
print(json.dumps({"call": ps.step_call(1, steps[0].body), "predicted": steps[0].body["predicted"],
                  "window": {"child": [[c.code, c.kind, c.blank] for c in window.child], "pairs": [[p.room, p.rate_plan] for p in window.plans]}},
                 ensure_ascii=False))
`;

test('S1 · S5 · 페이지가 읽은 창을 파이썬이 묶고, 파이썬이 만든 저장을 페이지가 그대로 쳐서 한 번 누르고, 그 답을 파이썬이 그 단계의 저장으로 받는다', async () => {
  const page = seasonPage({ window: LAST_FILL, banner: '가격을 넣었습니다 — 새로 12칸 · 덮어쓴 0칸 (룸 1개 × 1일).' });
  const r = plain(await page.w.stayPriceSeason.readSeason(inPage(page.w, { hotel: HOTEL, offer: OFFER, season: { id: IDS.season } })));
  assert.equal(r.ok, true, r.error);
  const { takes } = takeAll(page.w, r);
  const out = python(PLAN, { answers: [r, ...takes] });
  assert.deepEqual(out.window.child, [['INFANT', 'amount', '0.00'], ['CHILD', 'amount', '30000.00']], '빈 칸 기본값은 [비우기] 한 창의 값');
  assert.deepEqual(out.window.pairs.slice(0, 2), [['디럭스', '조식 포함'], ['디럭스', '룸온리']], '요금제 번호 → 캘린더 이름은 요금제 탭에서');
  assert.equal(out.predicted.created, 12, '디럭스 두 요금제 × (A2 · A3 · 아동 둘씩 넷) — 하루');
  const call = out.call;
  const answer = plain(await page.w.stayPriceSeason.applySeason(inPage(page.w, call.payload)));
  assert.equal(answer.saved, true, answer.error);
  assert.deepEqual(page.log.posts.map((p) => p.pairs), [call.payload.want], '보낸 칸이 파이썬이 만든 want 그대로');
  assert.ok(!page.log.posts[0].pairs.some(([name]) => name === 'stale_cleanup'), '지우기 칸은 켜지 않았다');
  assert.deepEqual(page.log.posts[0].pairs.filter(([name]) => name === 'price' || name === 'plan_adjust'), [['price', '180000'], ['plan_adjust', '-8000']]);
  const settled = python(`
from change_core.answers import step_outcome
import price_season as ps
o = step_outcome(args["call"], args["result"])
told = ps.banner_counts(ps.step_note(args["result"]))
print(json.dumps([o.saved, told.created, ps.counts_agree(ps.decode_counts(args["predicted"]), told)]))`, { call, result: answer, predicted: out.predicted });
  assert.deepEqual(settled, [true, 12, true], 'ERP 의 띠가 말한 수가 예상과 맞는다');
  page.w.close();
});
