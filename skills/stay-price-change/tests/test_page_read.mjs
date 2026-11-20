// B5 지금 값 읽기 · B6 예약 있는 날 읽기 — 저장하지 않고, 드로어를 닫고 끝나며, 물은 것과 다른 화면이면 실패한다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { erpPage, inPage, plain, runFixture, ownFixture, takeAll, charsOf, HERE, OFFER, HOTEL } from './page_harness.mjs';

const ALL_WEEK = ['월', '화', '수', '목', '금', '토', '일'];
const PAIR = { hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01', weekdays: ALL_WEEK };
const RESERVED = { hotel: HOTEL, offer: OFFER, rooms: ['디럭스', '스위트'], ratePlans: ['조식 포함', '룸온리'], from: '2026-12-24', to: '2026-12-31', weekdays: ALL_WEEK, occupancy: '*', nights: 'all' };

function pythonRead(kind, html) {
  const dir = mkdtempSync(join(tmpdir(), 'stay-price-read-'));
  try {
    const file = join(dir, 'fragment.html');
    writeFileSync(file, html);
    const done = spawnSync('python3', ['-I', join(HERE, 'reduced_reader.py'), kind, file], { encoding: 'utf8' });
    assert.equal(done.status, 0, done.stderr);
    return JSON.parse(done.stdout)[0];
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
const noSave = (page, r) => {
  assert.deepEqual(page.log.posts, [], '저장 요청이 하나도 나가지 않았다');
  assert.ok(!Object.keys(r.clicks).some((name) => /Save$/.test(name)), '저장 단추를 누르지 않았다');
  assert.ok(charsOf(r) <= 800, `답이 JSON 으로 800자 안: ${charsOf(r)}`);
  assert.equal(page.drawerOpen(), false, '드로어가 닫혀 있다');
};

test('B5 · readPair — 객실 × 요금제 칩을 고르고 ② 를 줄여 돌려준 뒤 저장 없이 드로어를 닫는다', async () => {
  const page = erpPage();
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, Object.assign({}, PAIR, { ratePlan: '룸온리' }))));
  assert.equal(r.ok, false, '룸온리 칩으로 옮겼는데 ② 의 요금제가 조식 포함이면(캡처 조각) 실패한다');
  assert.match(r.error, /다른 객실·요금제|요금제가 `조식 포함`/);
  noSave(page, r);
  page.w.close();

  const ok = erpPage();
  const read = plain(await ok.w.stayPrice.readPair(inPage(ok.w, PAIR)));
  assert.equal(read.ok, true, read.error);
  const { body, takes } = takeAll(ok.w, read);
  assert.deepEqual(body.asked, PAIR);
  assert.equal(read.what, '디럭스 · 조식 포함 · 2026-07-01');
  assert.deepEqual(read.days, { asked: 1, open: 1, noSale: 0 });
  assert.deepEqual(body.noSale, []);
  assert.deepEqual([read.clicks.bulkOpen, read.clicks.bulkNext], [1, 1]);
  assert.ok(takes.every((t) => t.ok && charsOf(t) <= 800));
  assert.deepEqual(read.blocked, []);
  noSave(ok, read);
  const parsed = pythonRead('price', body.fragment);
  assert.equal(parsed.page.rate_plan, '조식 포함');
  assert.deepEqual(parsed.page.days, { '2026-07-01': '가격 판매 가능' });
  assert.equal(parsed.page.rows[0].values['2026-07-01'][0], '120000.00');
  ok.w.close();
});

test('B5 · readPair — 다른 탭·전체 보기에서 시작하면 [가격 캘린더] 탭과 [룸별 입력] 을 눌러 칩을 고른다', async () => {
  const page = erpPage({ start: 'overview', tab: 'offers' });
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, PAIR)));
  assert.equal(r.ok, true, r.error);
  assert.deepEqual([r.clicks.tab, r.clicks.view], [1, 1]);
  noSave(page, r);
  page.w.close();
});

test('B5 · readPair — 화면이 다른 객실·다른 기간·다른 오퍼를 보여 주면 읽은 것을 돌려주지 않는다', async () => {
  const cases = [
    ['다른 객실(드로어의 rate_plan)', { bulkReview: runFixture('calendar-bulk--price-step2.html').replace('name="rate_plan" value="{rate_plan:1}"', 'name="rate_plan" value="{rate_plan:2}"') }, PAIR, /다른 객실·요금제/],
    ['다른 기간(상태 표의 날)', { bulkReview: runFixture('calendar-bulk--price-step2.html').replace('<tr><td>2026-07-01</td><td>가격 판매 가능</td></tr>', '<tr><td>2026-07-02</td><td>가격 판매 가능</td></tr>') }, PAIR, /드로어의 날짜.*와 다릅니다/],
    ['다른 오퍼', {}, Object.assign({}, PAIR, { offer: '다른 계약' }), /오퍼가 `〈오퍼 관리용 이름〉`/],
    ['없는 칩', {}, Object.assign({}, PAIR, { room: '디럭스 (시티뷰)' }), /칩이 없습니다/],
    ['요일 글자가 아님', {}, Object.assign({}, PAIR, { weekdays: ['Mon'] }), /weekdays/],
    ['ERP 가 기간을 거절', { bulkReview: runFixture('calendar-bulk--price-step1.html').replace('<section', '<div class="stay-banner stay-banner--blocking" data-stay-result="error"><div>판매일이 열리지 않은 날짜가 있습니다: 2026-07-01</div></div><section') }, PAIR, /거절했습니다 — 판매일이 열리지 않은/]
  ];
  for (const [name, opts, ask, why] of cases) {
    const page = erpPage(opts);
    const r = plain(await page.w.stayPrice.readPair(inPage(page.w, ask)));
    assert.equal(r.ok, false, name);
    assert.match(r.error, why, name);
    assert.equal(r.body, undefined, `${name}: 조각을 남기지 않는다`);
    noSave(page, r);
    page.w.close();
  }
});

test('B6 · readReserved — 가감 ① 을 채워 [다음] 만 누르고, ② 의 「건너뛰는 칸」 을 줄여 돌려준 뒤 드로어를 닫는다', async () => {
  const page = erpPage();
  const r = plain(await page.w.stayPrice.readReserved(inPage(page.w, RESERVED)));
  assert.equal(r.ok, true, r.error);
  const { body } = takeAll(page.w, r);
  assert.deepEqual(body.asked, RESERVED);
  assert.deepEqual([r.clicks.adjustOpen, r.clicks.adjustNext], [1, 1]);
  assert.ok(!Object.keys(r.clicks).some((c) => /Save|save/.test(c)), '[가감 적용] 을 누르지 않았다');
  noSave(page, r);
  const parsed = pythonRead('adjust', body.fragment);
  assert.equal(parsed.page.hidden, 0);
  assert.ok(parsed.page.rejected.some((row) => row.reason === '예약이 있는 날' && row.room === '디럭스'), JSON.stringify(parsed.page.rejected));
  page.w.close();
});

test('B6 · readReserved — 고른 객실·요금제·인원만 체크하고 해가 없는 내림 정액을 넣으며, 넣은 값을 서버가 받은 값과 견준다', async () => {
  const page = erpPage();
  const seen = {};
  page.doc.addEventListener('click', (e) => {
    if (!e.target.matches('[data-calendar-adjust="select"] [data-stay-action="next"]')) return;
    const root = page.doc.querySelector('[data-calendar-adjust="select"]');
    const on = (name) => [...root.querySelectorAll(`input[name="${name}"]`)].filter((b) => b.checked).map((b) => b.value);
    Object.assign(seen, { rooms: on('rooms'), plans: on('plans'), occupancy: on('occupancy'), los: on('los'), adjust: root.querySelector('[name="adjust"]').value,
      flags: ['adjust_original', 'include_manual', 'include_extra'].filter((n) => root.querySelector(`[name="${n}"]`).checked) });
  }, true);
  const ask = Object.assign({}, RESERVED, { rooms: ['디럭스'], ratePlans: ['룸온리'], occupancy: ['A2'], nights: 'one' });
  const r = plain(await page.w.stayPrice.readReserved(inPage(page.w, ask)));
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(seen, { rooms: ['{room:1}'], plans: ['source:{catalog:2}'], occupancy: ['A2'], los: ['one'], adjust: '-1', flags: ['include_manual'] });
  noSave(page, r);
  page.w.close();

  const bad = erpPage();
  for (const [ask2, why] of [[Object.assign({}, RESERVED, { adjust: '+5%' }), /내리는 정액/], [Object.assign({}, RESERVED, { rooms: ['펜트하우스'] }), /`객실` 에서 `펜트하우스`/],
    [Object.assign({}, RESERVED, { nights: 2 }), /nights/], [Object.assign({}, RESERVED, { occupancy: [] }), /occupancy/]]) {
    const r2 = plain(await bad.w.stayPrice.readReserved(inPage(bad.w, ask2)));
    assert.equal(r2.ok, false);
    assert.match(r2.error, why);
    noSave(bad, r2);
  }
  bad.w.close();
});

test('B6 · readReserved — 확인 단계가 고른 범위와 다르면(서버가 다른 값을 받았으면) 실패한다', async () => {
  const page = erpPage({ adjustReview: ownFixture('adjust-rejected.html').replace('<section class="stay-card" data-stay-summary>', '<input name="rooms" type="hidden" value="{room:9}"><section class="stay-card" data-stay-summary>') });
  const r = plain(await page.w.stayPrice.readReserved(inPage(page.w, RESERVED)));
  assert.equal(r.ok, false);
  assert.match(r.error, /다른 범위/);
  noSave(page, r);
  page.w.close();
});

test('T3 · 예약 있는 날 조각에는 가격이 없어 저장 뒤에 다시 읽어도 같은 조각이다(앞선 읽기의 것을 그대로 쓴다)', async () => {
  const bodies = [];
  for (const [now, after] of [['140.00 ~ 160.00', '141.00 ~ 161.00'], ['154.00 ~ 176.00', '155.00 ~ 177.00']]) {
    const page = erpPage({ adjustReview: ownFixture('adjust-rejected.html').replace('140.00 ~ 160.00', now).replace('141.00 ~ 161.00', after) });
    const r = plain(await page.w.stayPrice.readReserved(inPage(page.w, RESERVED)));
    assert.equal(r.ok, true, r.error);
    const { body } = takeAll(page.w, r);
    assert.ok(!body.fragment.includes('현재가') && !body.fragment.includes(now), '확인 머리의 「현재가 → 변경 후」 표는 조각에 없다');
    assert.ok(body.fragment.includes('건너뛰는 칸') && body.fragment.includes('예약이 있는 날'), '예약 있는 날을 가리는 표는 그대로');
    bodies.push([r.body.chars, r.body.bytes, r.body.crc32, r.body.fnv]);
    page.w.close();
  }
  assert.deepEqual(bodies[0], bodies[1], '가격만 달라진 두 읽기의 조각은 알아볼 값 넷이 같다');
});

