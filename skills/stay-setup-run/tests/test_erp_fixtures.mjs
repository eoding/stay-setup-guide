// ERP 가 실제 템플릿으로 그린 화면 조각(`tests/fixtures/erp/`, basecamp `stay/tests/fixtures/html/` 사본)으로 도는 러너 시험.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node tests/test_erp_fixtures.mjs
//
// 사본은 `scripts/sync_erp_fixtures.py` 가 맞추고 `test_erp_fixtures.py` 가 낡았는지 본다. 조각은 뷰 응답 그대로라
// htmx · Alpine 이 없다 — 화면이 하는 일 중 시험에 필요한 것만 아래에서 흉내 낸다(드로어 갈아 끼우기 · 반복 행 하나 세우기).
// 손 픽스처(`helper_fixture.html`)는 **표식이 없는 배포 전 화면**(글자로 찾는 길)과 실제 렌더로 못 만드는 경우만 남긴다.
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
const frag = (name) => readFileSync(join(here, 'fixtures', 'erp', name), 'utf8');

let pass = 0;
const ok = (cond, name, extra) => {
  assert.ok(cond, name + (extra === undefined ? '' : ' — ' + JSON.stringify(extra)));
  pass++;
};

// 탭 패널 하나 + 열린 드로어 하나. 조각은 뷰 응답이라 그 자리에 그대로 붓는다(스크립트는 돌리지 않는다).
function page({ pane = '', drawer = '', steps = [] } = {}) {
  const dom = new JSDOM(`<!doctype html><body>
    <a class="stay-tab active" href="#stay_tab_test" data-stay-tab="test">시험</a>
    <div id="stay_tab_test">${pane}</div>
    <div class="stay-drawer${drawer ? ' is-open' : ''}"><div id="stay_drawer_body">${drawer}</div></div>
  </body>`, { url: 'https://example.test/stay/1/#stay_tab_test', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.localStorage.setItem('staySteps', JSON.stringify({ steps }));
  w.eval(HELPER);
  w.stayRun.config({ waitMs: 1000 });
  return w;
}

// 1) 시즌 드로어(편집) — 표식으로 칸을 찾고, 시즌 날짜 줄은 날짜 선택 두 칸에 통째로 갈아 끼운다
{
  const w = page({ drawer: frag('season--edit.html') });
  const R = w.stayRun, d = w.document;
  const box0 = d.querySelector('[data-stay-field="date_selection_0"]'), box1 = d.querySelector('[data-stay-field="date_selection_1"]');
  ok(box0 && box1, '실제 시즌 드로어에 날짜 선택 두 칸이 있다');
  const before = box0.value;
  const fields = [
    { label: '시즌명', field: 'name', kind: 'typed', value: 'PEAK 2027' },
    { label: '우선순위', field: 'priority', kind: 'typed', value: '30' },
    { label: '시즌 코드', kind: 'typed', value: 'PK27' },            // 표식 key 없이 — 실제 화면 글자로 찾는다
    { label: '날짜 규칙 유형', field: 'dateset_rule_type', kind: 'select', value: '요일 규칙' },
    { label: '기간 시작', field: 'date_selection_0', kind: 'typed', value: '2027-06-01' },
    { label: '기간 종료', field: 'date_selection_0', kind: 'typed', value: '2027-06-30' },
    { label: '적용 요일', field: 'weekdays', kind: 'select', value: '토' },
    { label: '추가 날짜', kind: 'typed', value: '2027-06-10' }
  ];
  const res = await R.fill(fields);
  ok(res.every((r) => r.status === 'ok'), '시즌 드로어: 모든 줄이 들어간다', res.filter((r) => r.status !== 'ok'));
  ok(res[0].matchedBy === 'hook' && res[1].matchedBy === 'hook' && res[2].matchedBy === 'label', '표식 칸은 표식으로, key 없는 줄은 글자로 찾는다', res.map((r) => r.matchedBy));
  ok(d.querySelector('[data-stay-field="name"]').value === 'PEAK 2027' && d.querySelector('[name="code"]').value === 'PK27', '값이 실제 칸에 들어갔다');
  ok(box0.value === '2027-06-01 ~ 2027-06-30' && box1.value === '2027-06-10' && box0.value !== before, '날짜는 두 칸을 갈아 끼운다', [before, box0.value, box1.value]);
  ok(box0.closest('details').open === true, '닫힌 직접 입력 칸을 펼친다');
  const back = R.readback(fields);
  ok(back.mismatch.length === 0, '되읽기가 맞다', back.mismatch);
  w.close();
}

// 1-b) 시즌 드로어(신설) — 표식이 글자보다 먼저다(지시서 글자가 화면과 전혀 달라도). 저장은 동사(`save`)로 누른다(화면 글자 [추가])
{
  const w = page({ drawer: frag('season--new.html') });
  const R = w.stayRun, d = w.document;
  const res = await R.fill([{ label: '전혀 다른 지시서 글자', field: 'name', kind: 'typed', value: 'LOW' }]);
  ok(res[0].status === 'ok' && res[0].matchedBy === 'hook' && d.querySelector('[data-stay-field="name"]').value === 'LOW', '표식이 글자보다 먼저다', res[0]);
  let saved = 0;
  d.querySelector('[data-stay-action="save"]').addEventListener('click', () => { saved++; });
  const sub = await R.submit('저장', { action: 'save' });
  ok(sub.status !== 'not-found' && saved === 1, '글자 [저장] 으로는 없는 버튼을 동사 `save` 로 누른다(화면은 [추가])', { st: sub.status, saved });
  // 옛 지시서 글자(2026-10-28 이전) — 표식 key 없이 실제 화면의 새 글자를 별칭으로 찾는다
  const old = await R.fill([{ label: '최소 숙박 override', kind: 'typed', value: '2' }]);
  ok(old[0].status === 'ok' && d.querySelector('[data-stay-field="min_nights"]').value === '2', '옛 글자 `최소 숙박 override` 가 실제 화면의 `최소 숙박 (시즌 예외)` 칸에 간다', old[0]);
  w.close();
}

// 1-c) 시즌 날짜 — 비연속 나열은 줄 모양을 맞추고, 추가 날짜가 없는 고치기는 `_1` 을 비우고, 틀린 줄은 칸을 건드리지 않는다
{
  const w = page({ drawer: frag('season--edit.html') });
  const R = w.stayRun, d = w.document;
  const box0 = d.querySelector('[data-stay-field="date_selection_0"]'), box1 = d.querySelector('[data-stay-field="date_selection_1"]');
  box1.value = '2026-02-14';
  await R.fill([{ label: '날짜 규칙 유형', kind: 'select', value: '비연속 날짜 나열' },
                { label: '날짜 나열', kind: 'typed', value: '2026-7-1~2026-7-3\n\n2026-12-24' }]);
  ok(box0.value === '2026-07-01 ~ 2026-07-03\n2026-12-24' && box1.value === '', '날짜 나열 줄을 맞추고 옛 추가 날짜를 비운다', [box0.value, box1.value]);
  const bad = await R.fill([{ label: '기간 시작', kind: 'typed', value: '2027-10-01' }, { label: '기간 종료', kind: 'typed', value: '2027-10-05' },
                            { label: '추가 날짜', kind: 'typed', value: '2027-12-01 ~ 2027-12-03' }]);
  ok(bad.every((r) => r.status === 'error' && /하루씩/.test(r.detail)) && box0.value === '2026-07-01 ~ 2026-07-03\n2026-12-24',
     '추가 날짜에 기간을 적으면 오류이고 칸은 그대로다', bad);
  w.close();
}

// 1-d) 화면 사전 표시 동사 — 실제 [비우기](`clear`, 확인창 있음). 사전 위험 → 거부, `allow` 는 동사만 풀고 확인창은 그대로, 절대 금지는 force 도 안 된다
{
  const w = page({ drawer: frag('inventory-bulk.html') });
  const R = w.stayRun, d = w.document;
  let cleared = 0;
  d.querySelector('[data-stay-action="clear"]').addEventListener('click', () => { cleared++; });
  // 사전 표시(`#stay-action-flags`)가 없는 옛 지시서에서도 막는다 — 도우미 자체 표에 `clear` 와 글자 `비우기` 가 있다
  const bare = await R.submit('비우기');
  ok(bare.status === 'refused' && bare.reason === 'dangerous' && cleared === 0, '사전 표시가 없어도 [비우기](`clear`)는 거부한다', bare);
  R.actionFlags({ danger: ['clear'] });
  const a = await R.submit('비우기');
  ok(a.status === 'refused' && a.reason === 'dangerous', '사전이 위험으로 표시한 동사는 거부한다', a);
  const b = await R.submit('비우기', { allow: ['clear'] });
  ok(b.status === 'refused' && b.reason === 'confirm' && cleared === 0, '`allow` 는 동사 거부만 풀고 확인창은 그대로 막는다', b);
  R.actionFlags({ never_press: ['clear'] });
  const c = await R.submit('비우기', { force: true, allow: ['clear'] });
  ok(c.status === 'refused' && c.reason === 'never-press' && cleared === 0, '절대 금지 동사는 force·allow 로도 안 된다', c);
  w.close();
}

// 1-e) 재고 탭 — [수량으로 판매](`toggle_quantity`)는 사전 표시 없이도 위험이다. 재고 단계만 그 동사를 푼다(`allow`)
{
  const w = page({ pane: frag('panel--inventory.html') });
  const R = w.stayRun, d = w.document;
  const sw = d.querySelector('[data-stay-action="toggle_quantity"]');
  let toggled = 0;
  sw.addEventListener('click', () => { toggled++; });
  const no = await R.submit('수량으로 판매', { within: sw.closest('td') || sw.parentElement });
  ok(no.status === 'refused' && no.reason !== 'sale-start' && toggled === 0, '[수량으로 판매] 는 그냥은 누르지 않는다', no);
  w.close();
}

// 1-f) 저장 표지(2026-10-29) — 드로어가 닫히지 않는 저장도 `#stay_save_result[data-stay-result=saved]` 의 새 시각으로 성공을 안다
{
  const w = page({ drawer: frag('season--new.html') });
  const R = w.stayRun, d = w.document;
  const mark = d.createElement('div');
  mark.id = 'stay_save_result'; mark.hidden = true;   // `_drawer.html` 의 빈 자리
  d.body.appendChild(mark);
  let n = 0;
  d.querySelector('[data-stay-action="save"]').addEventListener('click', () => {
    n++;
    setTimeout(() => { mark.setAttribute('data-stay-result', 'saved'); mark.setAttribute('data-stay-saved-at', '2026-10-29T10:00:0' + n + '.000Z'); }, 20);
  });
  const a = await R.submit('추가', { action: 'save' });
  ok(a.status === 'saved' && a.saveMark && n === 1, '드로어가 남아도 이번 저장 표지가 서면 `saved` 다', a);
  // 표지가 안 바뀌면(묵은 표지 그대로) 저장으로 읽지 않는다
  d.querySelector('[data-stay-action="save"]').replaceWith(d.querySelector('[data-stay-action="save"]').cloneNode(true));
  const b = await R.submit('추가', { action: 'save' });
  ok(b.status !== 'saved' && b.status !== 'closed', '묵은 저장 표지로는 저장이라 하지 않는다', b.status);
  w.close();
}

// 2) 프로모션 드로어 — 할인 단계 행이 0개(새 프로모션). 표식(`data-stay-rows=tiers`)으로 묶음을 찾고 그 카드의 `add_row` 로 세운다
{
  const w = page({ drawer: frag('promotion--zero-tiers.html') });
  const R = w.stayRun, d = w.document;
  const tbody = d.querySelector('[data-stay-rows="tiers"] tbody');
  ok(tbody && tbody.querySelectorAll('[data-stay-col]').length === 0, '실제 렌더의 할인 단계 표에는 행이 하나도 없다');
  // Alpine 흉내: [단 추가] 를 누르면 `<template x-for>` 의 행 하나를 세운다
  d.querySelector('[data-stay-card="tiers"] [data-stay-action="add_row"]').addEventListener('click', () => {
    const tpl = tbody.querySelector('template');
    tbody.insertBefore(tpl.content.firstElementChild.cloneNode(true), tpl.nextSibling);
  });
  const fields = [
    { label: '할인 단계 1 · 기준값', field: 'tiers', field_row: 1, field_col: '기준값', kind: 'typed', value: '30' },
    { label: '할인 단계 1 · 값', field: 'tiers', field_row: 1, field_col: '값', kind: 'typed', value: '10' }
  ];
  const res = await R.fill(fields);
  ok(res.every((r) => r.status === 'ok'), '행 0개인 할인 단계에 행을 세워 넣는다', res);
  ok(tbody.querySelector('[data-stay-col="threshold"]').value === '30' && tbody.querySelector('[data-stay-col="value"]').value === '10', '기준값·값이 그 행에 들어갔다');
  w.close();
}

// 3) 검증 배너 — [판매 시작] 은 표식(`activate` · `gate`)으로 force 로도 거부한다
{
  const w = page({ pane: frag('validation.html') });
  const R = w.stayRun, d = w.document;
  let clicked = 0;
  d.querySelector('[data-stay-action="activate"]').addEventListener('click', () => { clicked++; });
  const s1 = await R.submit('판매 시작', { force: true });
  const s2 = await R.open({ button: '판매 시작', action: 'activate', force: true });
  ok(s1.status === 'refused' && s1.reason === 'sale-start' && s2.status === 'refused' && clicked === 0, '실제 배너의 [판매 시작] 을 누르지 않는다', [s1, s2]);
  w.close();
}

// 4) 객실 탭 패널 — 같은 [편집] 이 룸마다 있다. 대상·이름(`data-stay-entity` · `data-stay-name`)으로 그 행만 누른다. [삭제] 는 거부
{
  const w = page({ pane: frag('panel--room_types--1.html') });
  const R = w.stayRun, d = w.document;
  const clicks = [];
  d.querySelectorAll('[data-stay-action]').forEach((b) => b.addEventListener('click', () => {
    const owner = b.closest('[data-stay-entity]');
    clicks.push(b.dataset.stayAction + ':' + (owner ? owner.dataset.stayName : '-'));
  }));
  await R.open({ button: '편집', action: 'open_edit', entity: 'room_type', row: '스위트' });
  ok(clicks.join() === 'open_edit:스위트', '룸 타입 `스위트` 행의 [편집] 만 눌렀다', clicks);
  clicks.length = 0;
  // 룸 타입 [삭제] 는 실제 렌더에서 꺼져 있다(그 룸을 파는 오퍼가 있다) — 꺼진 버튼은 찾지도 누르지도 않는다
  const off = await R.open({ button: '삭제', row: '스위트' });
  ok(off.status === 'not-found' && clicks.length === 0, '꺼진 [삭제] 는 누르지 않는다', off);
  w.close();
}
// 4') 판매 연결 표 — [판매 연결 삭제] 는 글자 정규식(`^삭제$`)을 빠져나가지만 표식 동사(`delete`)로 거부한다
{
  const w = page({ pane: frag('panel--room_types--2.html') });
  const R = w.stayRun, d = w.document;
  let clicked = 0;
  d.querySelectorAll('[data-stay-action="delete"]').forEach((b) => b.addEventListener('click', () => { clicked++; }));
  const del = await R.open({ button: '판매 연결 삭제', row: '스위트' });
  ok(del.status === 'refused' && del.reason === 'dangerous' && clicked === 0, '[판매 연결 삭제] 는 표식 동사로 거부한다', del);
  w.close();
}

// 5) 셀 상태 바꾸기 → 가격 캘린더 판매 마감 — 실제 캘린더 패널(좌표 보기)과 일괄 드로어 두 단계
{
  // 원고의 시즌 — 판매 마감은 이 시즌의 날 안에서만 건다(7월 전체)
  const peak = { no: 8, kind: '시즌 만들기', title: '시즌 만들기 (1번째, PEAK)', head: { card: '2026 계약' }, longtexts: [],
    fields: [{ label: '시즌명', kind: 'typed', value: 'PEAK' }, { label: '날짜 규칙 유형', kind: 'select', value: '기간 범위' },
             { label: '기간 시작', kind: 'typed', value: '2026-07-01' }, { label: '기간 종료', kind: 'typed', value: '2026-07-31' }] };
  const steps = [{ no: 12, kind: '셀 상태 바꾸기', title: '셀 상태 바꾸기 (1번째, PEAK)', head: { tab: '시즌', card: 'PEAK' },
    fields: [
      { label: '바꿀 상태', kind: 'select', value: '마감' },
      { label: '시작 날짜', kind: 'typed', value: '2026-07-10' },
      { label: '종료 날짜', kind: 'typed', value: '2026-07-12' },
      { label: '대상 룸', kind: 'multi', values: ['디럭스', '스위트'] }
    ] }];
  const w = page({ pane: frag('panel--calendar--2.html'), steps: [peak].concat(steps) });
  w.eval(BOOT);
  const d = w.document, posts = [];
  w.stayRun.tab = async () => ({ status: 'ok' });
  const body = d.getElementById('stay_drawer_body'), drawer = d.querySelector('.stay-drawer');
  d.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.stayEntity === 'rate_plan') {  // 좌표 칩 — 고른 칩만 --primary
      d.querySelectorAll('[data-stay-entity="rate_plan"]').forEach((x) => { x.className = x.className.replace('stay-btn--primary', 'stay-btn--ghost'); });
      b.className = b.className.replace('stay-btn--ghost', 'stay-btn--primary');
    }
    if (b.dataset.calendarBulkAction === 'close') { body.innerHTML = frag('calendar-bulk--close-step1.html'); drawer.classList.add('is-open'); }
    if (b.dataset.stayAction === 'next') {      // ① → ② : 서버는 고른 날·범위를 숨은 칸에 되돌려 그린다
      const sel = { ranges: body.querySelector('[name="date_selection_0"]').value, scope: body.querySelector('[name="scope"]:checked').value };
      body.innerHTML = frag('calendar-bulk--close-step2.html');
      body.querySelector('[name="date_selection_0"]').value = sel.ranges;
      const scope = body.querySelector('input[type=hidden][name="scope"]');
      if (scope) scope.value = sel.scope;
    }
    if (b.dataset.stayAction === 'save' && body.querySelector('[data-stay-screen="calendar-bulk"]')) {
      const coord = d.querySelector('[data-stay-entity="rate_plan"].stay-btn--primary');
      posts.push({ coord: coord && coord.dataset.stayName, ranges: body.querySelector('[name="date_selection_0"]').value,
                   scope: body.querySelector('[name="scope"]').value });
      body.innerHTML = ''; drawer.classList.remove('is-open');
    }
  });
  ok(await w.calendarCloseAvailable(), '실제 캘린더 패널(좌표 보기)에 [판매 마감] 이 있다');
  const r = await w.runCloseStep(steps[0], {});
  ok(r.submitted === true, '판매 마감 두 룸을 걸었다', r);
  ok(JSON.stringify(posts.map((p) => [p.coord.split(' · ')[0], p.ranges, p.scope])) ===
     JSON.stringify([['디럭스', '2026-07-10 ~ 2026-07-12', 'all'], ['스위트', '2026-07-10 ~ 2026-07-12', 'all']]),
     '룸마다 그 룸의 모든 요금제로 같은 기간을 마감한다', posts);
  // 요금제를 적었으면 룸마다 그 요금제 칩에서 scope=plan
  posts.length = 0;
  const withPlan = { ...steps[0], fields: steps[0].fields.concat([{ label: '요금제(선택)', kind: 'select', value: '조식 포함' }]) };
  const r2 = await w.runCloseStep(withPlan, {});
  ok(r2.submitted === true && JSON.stringify(posts.map((p) => [p.coord, p.scope])) ===
     JSON.stringify([['디럭스 · 조식 포함', 'plan'], ['스위트 · 조식 포함', 'plan']]), '요금제를 적으면 그 칩에서 이 요금제만 마감한다', posts);
  // 마감이 아닌 상태는 사람 몫 · dry 는 아무것도 누르지 않는다
  posts.length = 0;
  for (const status of ['추후 공지', '판매 금지', '미공급', '판매 가능']) {
    const m = await w.runCloseStep({ ...steps[0], fields: [{ label: '바꿀 상태', kind: 'select', value: status }].concat(steps[0].fields.slice(1)) }, {});
    ok(m.manualAction === true && new RegExp(status).test(m.error), '`' + status + '` 은 사람 몫이다', m);
  }
  const dry = await w.runCloseStep(steps[0], { dry: true });
  ok(dry.dry === true && posts.length === 0, 'dry 는 아무것도 누르지 않는다', dry);
  w.close();
}

// 6) 선택 날짜 가격 수정(2026-11-13) — 실제 캘린더 패널 · ① · ② 의 `연동 방식`(기준 A2) · 직접 입력으로 다시 그린 ② · 건너뜀 결과 조각
{
  const F = (label, kind, value, extra = {}) => Object.assign({ label, kind, raw_value: value }, kind === 'multi' ? { values: value } : (value === undefined ? {} : { value }), extra);
  const line = (label, kind, value, key, col) => F(label, kind, value, { field: 'prices', occupancy_key: key, los_nights: 1, field_col: col });
  const step = (link, lines, base = 'A2 · 성인 2') => ({ no: 30, kind: '선택 날짜 가격 수정', title: '선택 날짜 가격 수정 (1번째, 디럭스 × 조식 포함)', head: { tab: '가격 캘린더' },
    fields: [F('오퍼', 'select', '〈오퍼 관리용 이름〉'), F('객실', 'select', '디럭스'), F('요금제', 'select', '조식 포함'),
             F('시작일', 'typed', '2026-07-01'), F('종료일', 'typed', '2026-07-02'), F('요일', 'multi', ['월', '화', '수', '목', '금', '토', '일']),
             F('연동 방식', 'select', link)].concat(base ? [F('기준 조합', 'select', base)] : []).concat(lines) });
  const run = async (s, { skipped = false } = {}) => {
    const w = page({ pane: frag('panel--calendar--2.html'), steps: [] });
    w.eval(BOOT);
    const d = w.document, posts = [], redraws = [];
    w.stayRun.tab = async () => ({ status: 'ok' });
    const body = d.getElementById('stay_drawer_body'), drawer = d.querySelector('.stay-drawer');
    d.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      if (b.dataset.stayEntity === 'rate_plan') {
        d.querySelectorAll('[data-stay-entity="rate_plan"]').forEach((x) => { x.className = x.className.replace('stay-btn--primary', 'stay-btn--ghost'); });
        b.className = b.className.replace('stay-btn--ghost', 'stay-btn--primary');
      }
      if (b.dataset.calendarBulkAction === 'price') { body.innerHTML = frag('calendar-bulk--price-step1.html'); drawer.classList.add('is-open'); }
      if (b.dataset.stayAction === 'next' && body.querySelector('[data-calendar-selection]')) body.innerHTML = frag('calendar-bulk--price-link-step2.html');
    });
    d.addEventListener('change', (e) => {
      if (e.target.name === 'link_mode_pick') { redraws.push(e.target.value); body.innerHTML = frag(e.target.value === 'manual' ? 'calendar-bulk--price-link-manual.html' : 'calendar-bulk--price-link-step2.html'); }
    });
    w.stayRun.submit = async (_t, opt) => {
      const root = d.querySelector('[data-stay-screen="calendar-bulk"]');
      const post = {};
      root.querySelectorAll('input, select').forEach((i) => { if (i.name && !i.name.endsWith('_pick') && i.value !== '') post[i.name] = i.value; });
      posts.push(post);
      if (skipped) { body.innerHTML = frag('calendar-bulk--price-link-result.html'); return { status: 'saved', errors: [] }; }
      body.innerHTML = ''; drawer.classList.remove('is-open');
      return { status: 'closed', errors: [] };
    };
    const r = await w.runCalendarPriceStep(s, {});
    w.close();
    return { r, posts, redraws };
  };
  const base = await run(step('기준 조합만 입력 — 나머지는 현재 차액 유지', [
    line('A2 · 1박 이상 · 판매가', 'typed', '160000', 'A2', 'price'),
    line('A3 · 1박 이상 · 판매가 차액', 'typed', '+30000', 'A3', 'price_diff'),
    line('인원 무관 단일가 · 1박 이상 · 판매가 차액', 'empty', undefined, '', 'price_diff')]));
  const bp = base.posts[0] || {};
  const idx = (key) => Object.keys(bp).find((k) => /-occupancy_key$/.test(k) && bp[k] === key);
  const a3 = (Object.keys(bp).find((k) => /-occupancy_key$/.test(k) && bp[k] === 'A3') || '').replace('occupancy_key', '');
  ok(base.r.submitted === true && base.redraws.length === 0 && bp.link_mode === 'base_delta' && bp.base_key === 'A2', '실제 ② 가 이미 기준 방식(A2)이면 셀렉트를 건드리지 않고 저장', [base.r, base.redraws, bp.link_mode]);
  ok(bp['prices-1-price'] === '160000' && bp[a3 + 'price_diff'] === '+30000' && !bp[a3 + 'price'], '실제 표의 기준 칸과 차액 칸에 들어갔다', [idx('A2'), a3, bp]);
  const manual = await run(step('조합마다 직접 입력', [line('A3 · 1박 이상 · 판매가', 'typed', '200000', 'A3', 'price')], null));
  const mp = manual.posts[0] || {};
  const ma3 = (Object.keys(mp).find((k) => /-occupancy_key$/.test(k) && mp[k] === 'A3') || '').replace('occupancy_key', '');
  ok(manual.r.submitted === true && JSON.stringify(manual.redraws) === '["manual"]' && mp[ma3 + 'price'] === '200000', '셀렉트를 직접 입력으로 바꿔 다시 그린 실제 ② 에서 저장', [manual.r, manual.redraws, mp]);
  const skipped = await run(step('기준 조합만 입력', [line('A2 · 1박 이상 · 판매가', 'typed', '160000', 'A2', 'price')]), { skipped: true });
  ok(skipped.r.submitted === true && skipped.r.submit === 'saved' && !skipped.r.error && skipped.r.warn && skipped.r.warn.length === 1, '실제 건너뜀 결과 조각은 성공 + 경고', skipped.r);
}

// 7) 선택 날짜 가격 가감 — 실제 ① · 확인 · 결과 조각. `최근 가감` 에 같은 가감이 있으면 멈춘다. [되돌리기] 는 누르지 않는다
{
  const F = (label, kind, value) => Object.assign({ label, kind, raw_value: value }, kind === 'multi' ? { values: value } : (value === undefined ? {} : { value }));
  const step = { no: 31, kind: '선택 날짜 가격 가감', title: '선택 날짜 가격 가감 (1번째, 〈오퍼 관리용 이름〉 · +5%)', head: { tab: '가격 캘린더' },
    fields: [F('오퍼', 'select', '〈오퍼 관리용 이름〉'), F('객실', 'multi', ['디럭스', '스위트']), F('요금제', 'multi', ['조식 포함', '룸온리']),
             F('시작일', 'typed', '2026-07-01'), F('종료일', 'typed', '2026-07-31'), F('요일', 'multi', ['월', '화', '수', '목', '금', '토', '일']),
             F('인원 조합', 'multi', ['A2', 'A3 · 성인 3']), F('박수 층', 'select', '전 층'), F('가감', 'typed', '+5%'),
             F('정가도 같이 조정', 'uncheck'), F('날짜별로 직접 고친 가격도 같이 바꾸기', 'uncheck'), F('추가 인원 요금도 같이 조정', 'uncheck')] };
  const run = async (opener, opt = {}) => {
    const w = page({ pane: frag('panel--calendar--2.html'), steps: [] });
    w.eval(BOOT);
    const d = w.document, posts = [], clicks = [];
    w.stayRun.tab = async () => ({ status: 'ok' });
    const body = d.getElementById('stay_drawer_body'), drawer = d.querySelector('.stay-drawer');
    d.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      clicks.push(b.dataset.calendarAdjustAction || b.dataset.stayAction || '');
      if (b.dataset.calendarAdjustAction === 'open') { body.innerHTML = frag(opener); drawer.classList.add('is-open'); }
      if (b.dataset.stayAction === 'next' && body.querySelector('[data-calendar-adjust="select"]')) {
        const got = {};
        body.querySelectorAll('input, select').forEach((i) => { if (!i.name || ((i.type === 'checkbox' || i.type === 'radio') && !i.checked)) return; (got[i.name] = got[i.name] || []).push(i.value); });
        posts.push(got);
        body.innerHTML = frag('calendar-adjust--step2.html');
      }
    });
    w.stayRun.submit = async (_t, o) => {
      const save = body.querySelector(`[data-stay-action="${o.action}"]`);
      if (!save || save.disabled) return { status: 'not-found', errors: [] };
      body.innerHTML = frag('calendar-adjust--applied.html');
      return { status: 'saved', errors: [] };
    };
    const r = await w.runCalendarAdjustStep(step, opt);
    w.close();
    return { r, posts, clicks };
  };
  const a = await run('calendar-adjust--step1.html');
  const g = a.posts[0] || {};
  ok(a.r.submitted === true && a.r.submit === 'saved' && a.r.preview.applied === 3 && a.r.result.applied === 3, '실제 가감 ① → 확인 → 결과', a.r);
  ok(JSON.stringify(g.rooms) === '["{room:1}","{room:2}"]' && JSON.stringify(g.plans) === '["source:{catalog:1}","source:{catalog:2}"]' && JSON.stringify(g.occupancy) === '["A2","A3"]', '실제 ① 의 객실·요금제·인원 조합을 원고대로(나머지는 끔)', g);
  ok(g.adjust[0] === '+5%' && g.los[0] === 'all' && !g.adjust_original && !g.include_manual && !g.include_extra && g.date_selection_0[0] === '2026-07-01 ~ 2026-07-31', '가감·박수 층·체크·날짜', g);
  ok(!a.clicks.includes('undo') && !a.clicks.includes('log'), '[되돌리기]·[적용 기록 내려받기] 는 누르지 않았다', a.clicks);
  const h = await run('calendar-adjust--step1-history.html');
  ok(h.r.manualAction === true && h.posts.length === 0 && /이미 적용돼 있습니다/.test(h.r.error), '실제 `최근 가감` 의 같은 가감 앞에서 멈춘다', h.r);
}

// 8) 시즌 [가격 입력] 의 입력 기억 — 실제 조각의 [비우기](`?blank=1`)를 눌러 빈 창을 받는다
{
  const w = page({ drawer: frag('season-price-fill--last-fill.html') });
  w.eval(BOOT);
  const d = w.document;
  ok(d.querySelector('[name="price"]').value === '180000', '실제 조각은 지난 입력값으로 열린다');
  d.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (b && /blank=1/.test(b.getAttribute('hx-get') || '')) d.getElementById('stay_drawer_body').innerHTML = frag('season-price-fill.html');
  });
  const sf = await w.seasonFillFresh();
  ok(sf.status === 'cleared' && d.querySelector('[name="price"]').value === '' && d.querySelector('[name="overwrite"]').checked === true, '[비우기] 뒤 빈 창(가격이 있는 시즌이라 덮기는 켜진 채)', [sf, d.querySelector('[name="overwrite"]').checked]);
  const plan = w.seasonFillFields({ fields: [] }, [{ label: '판매 단가(공급 통화)', kind: 'typed', value: '200000' }]);
  const res = await w.stayRun.fill(plan.fields);
  ok(res.every((x) => x.status === 'ok') && d.querySelector('[name="overwrite"]').checked === false && d.querySelector('[name="price"]').value === '200000', '덮기 줄이 없는 원고는 덮기를 끈다', res);
  w.close();
}

// 9) 검증 배너 — 연령 구간 빈 나이 차단을 사람 말로 넘긴다
{
  const w = page({ pane: frag('validation--age-gap.html') });
  w.eval(BOOT);
  const b = w.saleStartBanner();
  ok(b.blockers.length >= 1 && b.ageBand.length === 1 && /연령 구간/.test(b.note), '실제 배너의 연령 구간 차단 줄을 읽는다', b);
  w.close();
}

console.log(`real ERP fixture tests passed (${pass} checks: hooks, season dates, zero tiers, flags, activate, panel openers, calendar close, price link, adjust, season memory, age-gap banner)`);
