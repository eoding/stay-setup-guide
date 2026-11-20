// G1 이 탭은 어디인가 — stayPrice.look() 하나로 로그인 화면인지, 어느 호텔인지(페이지가 말하는 번호·이름), 캘린더의 오퍼,
// 한 오퍼의 객실 × 요금제 칩 이름을 안다. 누르는 것은 [가격 캘린더] 탭 · [룸별 입력] · 그 오퍼 칩뿐이다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { erpPage, inPage, plain, charsOf, takeAll, OFFER, HOTEL, SKILL } from './page_harness.mjs';

const PAIRS = [['디럭스', '조식 포함'], ['디럭스', '룸온리'], ['디럭스', '직접 만든 요금제'], ['스위트', '조식 포함'], ['스위트', '룸온리']]
  .map(([room, plan]) => ({ room, rate_plan: plan }));
const SECOND = '2027 계약';
// 오퍼가 둘인 캘린더 — 고정 글자 대신 오퍼 칩 둘(ERP `_calendar_month.html` 의 오퍼 라디오 표식 그대로)
const twoOffers = (html) => html.replace(/<div class="stay-offer-label stay-selection-group">[\s\S]*?<\/div>/,
  `<div class="stay-coord-group stay-selection-group">
    <button type="button" class="stay-offer-btn stay-btn stay-btn--primary" data-stay-action="goto" data-stay-entity="offer" data-stay-name="${OFFER}" data-stay-entity-id="{offer:1}" hx-get="/stay/{master:1}/calendar/?month=2026-07&amp;view=coord&amp;offer={offer:1}" hx-target="#stay_calendar" hx-swap="outerHTML"><span class="stay-card__title">${OFFER}</span></button>
    <button type="button" class="stay-offer-btn stay-btn stay-btn--ghost" data-stay-action="goto" data-stay-entity="offer" data-stay-name="${SECOND}" data-stay-entity-id="{offer:2}" hx-get="/stay/{master:1}/calendar/?month=2026-07&amp;view=coord&amp;offer={offer:2}" hx-target="#stay_calendar" hx-swap="outerHTML"><span class="stay-card__title">${SECOND}</span></button>
  </div>`);

test('G1 · look() — 호텔은 페이지가 말하는 번호와 이름, 오퍼와 그 오퍼의 객실 × 요금제를 칩 이름 그대로 알려 주고 아무것도 열지 않는다', async () => {
  const page = erpPage();
  const r = plain(await page.w.stayPrice.look());
  assert.equal(r.ok, true, r.error);
  assert.deepEqual([r.login, r.hotel, r.offer, r.offers, r.pairs], [false, HOTEL, OFFER, [OFFER], PAIRS]);
  assert.deepEqual(page.log.reached, [], '이미 캘린더의 룸별 입력이면 아무것도 누르지 않는다');
  assert.equal(page.drawerOpen(), false);
  assert.ok(charsOf(r) <= 800, String(charsOf(r)));
  page.w.close();
});

test('G1 · look() — 다른 탭 · 전체 보기에서 부르면 [가격 캘린더] 탭과 [룸별 입력] 만 누른다', async () => {
  const page = erpPage({ tab: 'offers', start: 'overview' });
  const r = plain(await page.w.stayPrice.look());
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.pairs, PAIRS);
  assert.deepEqual(Object.keys(r.clicks).sort(), ['tab', 'view']);
  assert.deepEqual(page.log.reached, ['stay-tab=calendar', 'stay-action=goto'], '탭 하나와 [룸별 입력] 하나');
  page.w.close();
});

test('G1 · look({offer}) — 오퍼가 둘이면 그 오퍼 칩을 눌러 그 오퍼의 칩을 보이고, 없는 오퍼는 보이는 오퍼를 대며 거절한다', async () => {
  const page = erpPage({ panelEdit: twoOffers });
  const first = plain(await page.w.stayPrice.look());
  assert.deepEqual([first.offer, first.offers], [OFFER, [OFFER, SECOND]]);
  const second = plain(await page.w.stayPrice.look(inPage(page.w, { offer: SECOND })));
  assert.equal(second.ok, true, second.error);
  assert.equal(second.offer, SECOND);
  assert.deepEqual(Object.keys(second.clicks), ['offer']);
  const none = plain(await page.w.stayPrice.look(inPage(page.w, { offer: '없는 계약' })));
  assert.equal(none.ok, false);
  assert.match(none.error, /없는 계약/);
  assert.match(none.error, new RegExp(SECOND));
  page.w.close();
});

test('G1 · look() — 로그인 화면이면 그렇게만 말하고 아무것도 누르지 않는다', async () => {
  const page = erpPage({ login: true });
  const r = plain(await page.w.stayPrice.look());
  assert.deepEqual([r.ok, r.login, r.hotel], [true, true, undefined]);
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});

test('G1 · look() — 호텔 번호가 없거나 화면 두 곳이 다른 번호를 말하면 거절한다', async () => {
  const bare = erpPage({ hotel: null });
  const r = plain(await bare.w.stayPrice.look());
  assert.equal(r.ok, false);
  assert.match(r.error, /호텔 번호를 찾지 못했습니다/);
  bare.w.close();
  const split = erpPage({ hotel: { id: '1', said: '2' } });
  const s = plain(await split.w.stayPrice.look());
  assert.equal(s.ok, false);
  assert.match(s.error, /두 곳에서 다릅니다\(1 · 2\)/);
  split.w.close();
});

test('G1 · look() — 칩이 많아 800자를 넘으면 목록은 조각으로 두고, take 로 받은 답을 명령 look 이 하나로 잇는다', async () => {
  const many = (html) => html.replace(/(<button type="button"\s+class="stay-coord-btn[\s\S]*?<\/button>)/, (chip) =>
    chip + Array.from({ length: 25 }, (_, i) => chip.replace(/data-stay-name="[^"]*"/, `data-stay-name="객실 ${i + 1}호 · 조식 포함 요금제 ${i + 1}"`)
      .replace('stay-btn--primary', 'stay-btn--ghost')).join(''));
  const page = erpPage({ panelEdit: many });
  const r = plain(await page.w.stayPrice.look());
  assert.equal(r.ok, true, r.error);
  assert.ok(charsOf(r) <= 800 && r.body && !r.pairs, JSON.stringify(r).slice(0, 300));
  assert.deepEqual(r.count, { offers: 1, pairs: 30 });
  const dir = mkdtempSync(join(tmpdir(), 'stay-price-look-'));
  try {
    writeFileSync(join(dir, 'look-1.json'), JSON.stringify(r));
    takeAll(page.w, r).takes.forEach((piece, i) => writeFileSync(join(dir, `look-1-${i}.json`), JSON.stringify(piece)));
    const done = spawnSync('python3', [join(SKILL, 'scripts', 'price_change.py'), 'look', '--answers', dir], { encoding: 'utf8' });
    assert.equal(done.status, 0, done.stderr);
    const joined = JSON.parse(done.stdout);
    assert.deepEqual([joined.hotel, joined.offer, joined.pairs.length], [HOTEL, OFFER, 30]);
    assert.deepEqual(joined.pairs[1], { room: '객실 1호', rate_plan: '조식 포함 요금제 1' });
  } finally { rmSync(dir, { recursive: true, force: true }); }
  page.w.close();
});
