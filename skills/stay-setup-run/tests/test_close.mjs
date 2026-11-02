// 셀 상태 바꾸기 → 가격 캘린더 판매 마감(2026-10-28) — `runCloseStep` 손 픽스처 시험.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node tests/test_close.mjs
//
// 흔한 길(룸마다 모든 요금제 · 요금제별 · 사람 몫 상태 · dry)은 실제 렌더(`test_erp_fixtures.mjs` 5)로 본다. 여기는
// 실제 렌더로 만들 수 없는 경우만 남긴다 — 사본의 캘린더는 오퍼 하나 · 괄호 겹침 없는 이름 · 성공하는 확인 화면 하나뿐이다:
//   · 확인 화면이 거절하는 응답 · 오퍼가 둘인 캘린더 · [판매 마감] 이 없는 배포 전 캘린더
//   · 괄호만 다른 칩 이름(`Room Only` ↔ `Room Only (Non-refundable)`, `Deluxe (City View)` ↔ `Deluxe (Ocean View)`)
//   · 이름이 같은 시즌이 오퍼 둘에 있는 원고 · 시즌 날짜 밖이 섞인 기간
// 화면은 ERP 표식 그대로 흉내 낸다(`_calendar_month.html` 의 칩·[판매 마감], `_calendar_bulk_form.html` 의 ①·②).
// 도우미(`stay_helper.js`)는 진짜를 올리고 탭 이동·기다림·저장만 흉내 낸다 — 시즌 날짜 펼치기(`seasonDays`)는 진짜다.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const require = createRequire(import.meta.url);
const { JSDOM } = require('jsdom');
const here = dirname(fileURLToPath(import.meta.url));
const HELPER = readFileSync(join(here, '../scripts/stay_helper.js'), 'utf8');
const BOOT = readFileSync(join(here, '../scripts/stay_boot.js'), 'utf8');

const chip = (name, room, cls = 'ghost') =>
  `<button type="button" class="stay-coord-btn stay-btn stay-btn--${cls}" data-stay-action="goto" data-stay-entity="rate_plan" data-stay-name="${name}" hx-get="/stay/1/calendar/?view=coord&amp;option=${room}&amp;rate_plan=1">${name}</button>`;
const COORDS = [
  chip('Single · Room Only', 11, 'primary'), chip('Single · Room Only (Non-refundable)', 11), chip('Single · 조식 포함', 11),
  chip('Deluxe (City View) · Room Only', 12), chip('Deluxe (Ocean View) · Room Only', 13)
].join('\n');
const CALENDAR = (offers = 2) => `
<div id="stay_tab_calendar">
  <div class="stay-coord-group">
    <button type="button" class="stay-offer-btn stay-btn stay-btn--primary" data-stay-action="goto" data-stay-entity="offer" data-stay-name="2026 계약">2026 계약</button>
    ${offers > 1 ? '<button type="button" class="stay-offer-btn stay-btn stay-btn--ghost" data-stay-action="goto" data-stay-entity="offer" data-stay-name="2027 계약">2027 계약</button>' : ''}
  </div>
  <div class="stay-coord-group" id="coords">${COORDS}</div>
  <button type="button" data-calendar-bulk-action="close">판매 마감</button>
</div>
<div class="stay-drawer"><div id="stay_drawer_body"></div></div>`;

// ① 단계 — 요일 값은 0=월(2026-10-29 ERP, 시즌 폼과 같은 축)
const STEP1 = `<div class="stay-root" data-stay-screen="calendar-bulk" data-calendar-selection>
  <input type="text" name="period_from" value="2026-12-01"><input type="text" name="period_to" value="2026-12-31">
  ${[0, 1, 2, 3, 4, 5, 6].map((d) => `<label><input type="checkbox" name="weekdays" data-stay-field="weekdays" value="${d}" checked><span>${'월화수목금토일'[d]}</span></label>`).join('')}
  <label><input type="radio" name="scope" value="plan" checked><span>이 요금제</span></label>
  <label><input type="radio" name="scope" value="all"><span>객실 전체</span></label>
  <input type="hidden" name="date_selection_0" data-calendar-selected-ranges value="2026-12-01 ~ 2026-12-31">
  <button type="button" data-stay-action="next">다음</button>
</div>`;

const season = (no, offer, name, fields) => ({ no, kind: '시즌 만들기', title: `시즌 만들기 (${no}번째, ${name})`, head: { card: offer },
  fields: [{ label: '시즌명', kind: 'typed', value: name }].concat(fields), longtexts: [] });
const RANGE_DEC = [{ label: '날짜 규칙 유형', kind: 'select', value: '기간 범위' },
  { label: '기간 시작', kind: 'typed', value: '2026-12-01' }, { label: '기간 종료', kind: 'typed', value: '2026-12-31' }];
const SATURDAYS = [{ label: '날짜 규칙 유형', kind: 'select', value: '요일 규칙' },
  { label: '기간 시작', kind: 'typed', value: '2026-12-01' }, { label: '기간 종료', kind: 'typed', value: '2026-12-31' },
  { label: '적용 요일', kind: 'select', value: '토' }];

function screen({ refuse = false, offers = 2, seasons = [season(26, '2026 계약', 'Peak', RANGE_DEC)], calendar = true, failOffer = false, failCoord = false, tabStatus = 'ok' } = {}) {
  const dom = new JSDOM(calendar ? CALENDAR(offers) : '<div id="stay_tab_seasons"></div>', { url: 'https://example.com/stay/123/#stay_tab_calendar', runScripts: 'outside-only' });
  const w = dom.window, doc = w.document;
  w.localStorage.setItem('staySteps', JSON.stringify({ steps: seasons }));
  const log = { posts: [], tabs: [], waitFailures: 0 };
  doc.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.stayEntity === 'rate_plan' || b.dataset.stayEntity === 'offer') {
      const group = b.dataset.stayEntity;
      if ((group === 'offer' && failOffer) || (group === 'rate_plan' && failCoord)) return;
      doc.querySelectorAll(`[data-stay-entity="${group}"]`).forEach((x) => { x.className = x.className.replace('--primary', '--ghost'); });
      b.className = b.className.replace('--ghost', '--primary');
    }
    if (b.dataset.calendarBulkAction === 'close') doc.getElementById('stay_drawer_body').innerHTML = STEP1;
    if (b.dataset.stayAction === 'next') {
      const d = doc.querySelector('[data-stay-screen="calendar-bulk"]');
      const sel = { ranges: d.querySelector('[name=date_selection_0]').value, scope: d.querySelector('[name=scope]:checked').value };
      const offer = doc.querySelector('[data-stay-entity="offer"][class*="--primary"]');
      const coord = doc.querySelector('[data-stay-entity="rate_plan"][class*="--primary"]').dataset.stayName;
      doc.getElementById('stay_drawer_body').innerHTML = `<div class="stay-root" data-stay-screen="calendar-bulk">
        <input type="hidden" name="period_from" value="2026-12-24"><input type="hidden" name="period_to" value="2026-12-26">
        <input type="hidden" name="scope" value="${sel.scope}"><input type="hidden" name="date_selection_0" value="${sel.ranges}">
        ${refuse ? '<div class="stay-banner stay-banner--blocking" data-stay-result="error"><span>이 오퍼의 객실만 선택해주세요</span></div>' : ''}
        <button type="button" data-stay-action="save" data-coord="${coord}" data-offer="${offer ? offer.dataset.stayName : ''}">선택 날짜 마감</button></div>`;
    }
  });
  w.eval(HELPER);
  Object.assign(w.stayRun, {
    tab: async (name) => { log.tabs.push(name); return { status: tabStatus }; },
    waitFor: async (fn) => { const ok = !!fn(); if (!ok) log.waitFailures++; return ok; },
    submit: async (_text, opt) => {
      const save = doc.querySelector(`[data-stay-action="${opt.action}"]`);
      const d = doc.querySelector('[data-stay-screen="calendar-bulk"]');
      log.posts.push({ coord: save.dataset.coord, offer: save.dataset.offer, scope: d.querySelector('[name=scope]').value,
                       ranges: d.querySelector('[name=date_selection_0]').value });
      doc.getElementById('stay_drawer_body').innerHTML = '';
      return { status: 'closed', errors: [] };
    }
  });
  w.eval(BOOT);
  return { w, log };
}

const step = (fields, card = 'Peak') => ({
  no: 40, kind: '셀 상태 바꾸기', title: '셀 상태 바꾸기 (1번째, Peak)', head: { tab: '시즌', card },
  fields: [
    { label: '바꿀 상태', kind: 'select', value: '마감' },
    { label: '시작 날짜', kind: 'typed', value: '2026-12-24' },
    { label: '종료 날짜', kind: 'typed', value: '2026-12-26' },
    { label: '대상 룸', kind: 'multi', values: ['Single'] }
  ].map((f) => fields[f.label] === undefined ? f : Object.assign({}, f, fields[f.label])).concat(fields.extra || [])
});

// ① 괄호만 다른 칩 — 이름이 꼭 같은 칩이 먼저다(`Room Only` 를 `Room Only (Non-refundable)` 로 착각하지 않는다)
{
  const { w, log } = screen();
  const r = await w.runCloseStep(step({ extra: [{ label: '요금제(선택)', kind: 'typed', value: 'Room Only' }] }), {});
  assert.equal(r.submitted, true, JSON.stringify(r));
  assert.deepEqual(log.posts.map((p) => [p.coord, p.scope]), [['Single · Room Only', 'plan']], '맨 글자 요금제 이름도 그 요금제만(scope=plan)');
  log.posts.length = 0;
  const nr = await w.runCloseStep(step({ extra: [{ label: '요금제(선택)', kind: 'select', value: 'Room Only (Non-refundable)' }] }), {});
  assert.equal(nr.submitted, true, JSON.stringify(nr));
  assert.deepEqual(log.posts.map((p) => p.coord), ['Single · Room Only (Non-refundable)']);
  // `Deluxe` 는 정확히 같은 칩이 없고 괄호만 다른 룸이 둘이다 — 고르지 않는다
  log.posts.length = 0;
  const amb = await w.runCloseStep(step({ '대상 룸': { values: ['Deluxe'] } }), {});
  assert.match(amb.error, /2개 칩 묶음에 걸립니다/);
  assert.equal(log.posts.length, 0);
  // 정확한 이름이면 그 룸만
  const one = await w.runCloseStep(step({ '대상 룸': { values: ['Deluxe (City View)'] } }), {});
  assert.equal(one.submitted, true, JSON.stringify(one));
  assert.deepEqual(log.posts.map((p) => [p.coord, p.scope]), [['Deluxe (City View) · Room Only', 'all']]);
  w.close();
}
// ② 같은 이름의 시즌이 오퍼 둘에 — 카드가 오퍼를 밝히지 않으면 사람 몫. `카드: <오퍼> · <시즌>` 이면 그 오퍼로 그 시즌의 날만
{
  const seasons = [season(26, '2026 계약', 'Peak', RANGE_DEC),
                   season(27, '2027 계약', 'Peak', [{ label: '날짜 규칙 유형', kind: 'select', value: '기간 범위' },
                     { label: '기간 시작', kind: 'typed', value: '2026-12-25' }, { label: '기간 종료', kind: 'typed', value: '2026-12-25' }])];
  const { w, log } = screen({ seasons });
  const amb = await w.runCloseStep(step({}), {});
  assert.equal(amb.manualAction, true);
  assert.match(amb.error, /오퍼 여럿\(2026 계약, 2027 계약\)/);
  assert.equal(log.posts.length + log.tabs.length, 0);
  const named = await w.runCloseStep(step({}, '2027 계약 · Peak'), {});
  assert.equal(named.submitted, true, JSON.stringify(named));
  assert.deepEqual(log.posts.map((p) => [p.offer, p.ranges]), [['2027 계약', '2026-12-25']], '2027 계약으로 바꾸고 그 시즌의 날(12/25)만 닫는다');
  w.close();
}
// ③ 기간 ∩ 시즌 날짜 — 토요일 시즌이면 그 기간의 토요일만 닫는다. 시즌을 원고에서 못 읽거나 겹치는 날이 없으면 사람 몫
{
  const { w, log } = screen({ seasons: [season(26, '2026 계약', 'Peak', SATURDAYS)] });
  const r = await w.runCloseStep(step({ '시작 날짜': { value: '2026-12-01' }, '종료 날짜': { value: '2026-12-14' } }), {});
  assert.equal(r.submitted, true, JSON.stringify(r));
  assert.deepEqual(log.posts.map((p) => p.ranges), ['2026-12-05', '2026-12-12'], '기간을 통째로가 아니라 시즌의 날(토)만');
  assert.match(r.warn[0], /12일/);
  log.posts.length = 0;
  const none = await w.runCloseStep(step({ '시작 날짜': { value: '2026-12-07' }, '종료 날짜': { value: '2026-12-11' } }), {});
  assert.equal(none.manualAction, true);
  assert.match(none.error, /하루도 없습니다/);
  w.close();
  const missing = screen({ seasons: [] });
  const m = await missing.w.runCloseStep(step({}), {});
  assert.equal(m.manualAction, true);
  assert.match(m.error, /찾지 못했습니다/);
  assert.equal(missing.log.posts.length + missing.log.tabs.length, 0);
  missing.w.close();
}
// ④ 확인 화면이 거절하면 저장하지 않는다
{
  const { w, log } = screen({ refuse: true });
  const r = await w.runCloseStep(step({}), {});
  assert.equal(r.submitted, undefined);
  assert.match(r.error, /거절했습니다 — 이 오퍼의 객실만/);
  assert.equal(log.posts.length, 0);
  w.close();
}
// ⑤ 오퍼가 둘인데 이 시즌의 오퍼를 원고에서 못 읽으면 멈춘다(시즌 단계에 카드가 없다) — 보이는 오퍼에 걸지 않는다
{
  const { w, log } = screen({ seasons: [season(26, '', 'Peak', RANGE_DEC)] });
  const r = await w.runCloseStep(step({}), {});
  assert.match(r.error, /오퍼를 원고에서 찾지 못했습니다/);
  assert.equal(log.posts.length, 0);
  w.close();
}
// ⑥ 캘린더에 [판매 마감] 이 없는 ERP — 종전 시즌 드로어로 간다(available=false)
{
  const { w } = screen({ calendar: false });
  assert.equal(await w.calendarCloseAvailable(), false);
  w.close();
}
// 이동 실패는 저장 전에 멈춘다. 화면에 남은 이전 오퍼·좌표를 대신 닫지 않는다.
{
  const seasons = [season(26, '2026 계약', 'Peak', RANGE_DEC), season(27, '2027 계약', 'Peak', RANGE_DEC)];
  const { w, log } = screen({ seasons, failOffer: true });
  const r = await w.runCloseStep(step({}, '2027 계약 · Peak'), {});
  assert.notEqual(r.submitted, true, '오퍼 이동 실패를 성공으로 처리하면 안 된다');
  assert.ok(r.error);
  assert.equal(log.posts.length, 0, '이전 오퍼에 마감을 걸면 안 된다');
  w.close();
}
{
  const { w, log } = screen({ failCoord: true });
  const r = await w.runCloseStep(step({ '대상 룸': { values: ['Deluxe (City View)'] } }), {});
  assert.notEqual(r.submitted, true);
  assert.ok(r.error);
  assert.equal(log.posts.length, 0, '객실 이동 실패 뒤 이전 객실에 마감을 걸면 안 된다');
  w.close();
}
{
  const { w, log } = screen({ tabStatus: 'not-found' });
  const r = await w.runCloseStep(step({}), {});
  assert.notEqual(r.submitted, true);
  assert.ok(r.error);
  assert.equal(log.posts.length, 0, '탭 이동 실패 뒤 저장하면 안 된다');
  w.close();
}
{
  const { w, log } = screen();
  const r = await w.runCloseStep(step({}), {});
  assert.equal(r.submitted, true);
  assert.equal(log.waitFailures, 0, '확인 단계의 숨은 기간 칸을 첫 단계로 오인하면 안 된다');
  w.close();
}

console.log('calendar close hand tests passed (exact chips, offer-named season, season-day intersection, review refusal, two offers, pre-deploy calendar)');
