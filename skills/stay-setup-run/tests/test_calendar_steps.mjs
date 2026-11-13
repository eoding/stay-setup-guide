// 가격 캘린더 일괄 단계(2026-11-13) — `runCalendarPriceStep` · `runCalendarAdjustStep` · 시즌 입력 기억 비우기 ·
// [판매 시작] 앞 배너 읽기 · 금액 숫자 견주기 손 픽스처 시험.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node tests/test_calendar_steps.mjs
//
// 화면은 ERP 묶음 템플릿의 표식 그대로 흉내 낸다(`_calendar_month.html` 의 칩·일괄 버튼, `_calendar_bulk_form.html` 의 ①·②와
// `연동 방식` 셀렉트, `_calendar_link_result.html`, `_calendar_adjust_form.html` 의 ①·확인·결과, `_season_fill_form.html` 의 [비우기]).
// 셀렉트를 바꾸면 드로어를 다시 그리는 htmx 는 change 이벤트에서 조각을 갈아 끼우는 것으로 흉내 낸다. 도우미는 진짜를 올린다.
// 묶음 전 화면(운영 ERP — 셀렉트 없음 · 금액 칸 `type=number` · 가감 버튼 없음)도 같은 러너로 돈다.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const require = createRequire(import.meta.url);
let JSDOM;
try { ({ JSDOM } = require('jsdom')); } catch (e) {
  console.log('jsdom 이 없어 화면 시험을 건너뜁니다 (NODE_PATH 로 jsdom 이 있는 node_modules 를 주세요)');
  process.exit(0);
}
const here = dirname(fileURLToPath(import.meta.url));
const HELPER = readFileSync(join(here, '../scripts/stay_helper.js'), 'utf8');
const BOOT = readFileSync(join(here, '../scripts/stay_boot.js'), 'utf8');

let pass = 0;
const ok = (cond, name, extra) => { assert.ok(cond, name + (extra === undefined ? '' : ' — ' + JSON.stringify(extra))); pass++; };

const chip = (name, room, cls = 'ghost') =>
  `<button type="button" class="stay-coord-btn stay-btn stay-btn--${cls}" data-stay-action="goto" data-stay-entity="rate_plan" data-stay-name="${name}" hx-get="/stay/1/calendar/?view=coord&amp;option=${room}&amp;rate_plan=1">${name}</button>`;

function calendarPane({ bundle = true, view = 'coord' } = {}) {
  const coords = view === 'coord'
    ? `<div class="stay-coord-group">${chip('Single · 룸온리', 11, 'primary')}${chip('Single · 조식 포함', 11)}${chip('Twin · 룸온리', 12)}</div>
       <div class="stay-calendar-bulk-actions">
         <button type="button" class="stay-btn" data-calendar-bulk-action="price">선택 날짜 가격 수정</button>
         ${bundle ? '<button type="button" class="stay-btn" data-calendar-adjust-action="open">선택 날짜 가격 가감</button>' : ''}
         <button type="button" class="stay-btn" data-calendar-bulk-action="close">판매 마감</button>
       </div>`
    : '';
  return `<div id="stay_tab_calendar">
    <button type="button" class="stay-view-btn stay-btn stay-btn--${view === 'coord' ? 'ghost' : 'primary'}" data-stay-action="goto">전체 보기</button>
    <button type="button" class="stay-view-btn stay-btn stay-btn--${view === 'coord' ? 'primary' : 'ghost'}" data-stay-action="goto" data-view="coord">룸별 입력</button>
    <div class="stay-coord-group stay-selection-group">
      <button type="button" class="stay-offer-btn stay-btn stay-btn--primary" data-stay-action="goto" data-stay-entity="offer" data-stay-name="2026~2027 시즌 요금">2026~2027 시즌 요금</button>
      <button type="button" class="stay-offer-btn stay-btn stay-btn--ghost" data-stay-action="goto" data-stay-entity="offer" data-stay-name="2027 겨울 요금">2027 겨울 요금</button>
    </div>
    <div id="coord_area">${coords}</div>
  </div>
  <div class="stay-drawer"><div id="stay_drawer_body"></div></div>`;
}

const WEEK = '월화수목금토일';
const periodRows = (from = '2026-12-01', to = '2026-12-31') => `
  <input type="text" name="period_from" value="${from}" data-stay-field="period_from"><input type="text" name="period_to" value="${to}" data-stay-field="period_to">
  ${[0, 1, 2, 3, 4, 5, 6].map((d) => `<label class="check_form"><input type="checkbox" name="weekdays" data-stay-field="weekdays" data-calendar-weekday value="${d}" checked><span>${WEEK[d]}</span></label>`).join('')}`;

const BULK_STEP1 = `<div class="stay-root stay-readable" data-stay-screen="calendar-bulk" data-calendar-selection>
  <section class="stay-card">${periodRows()}
  <input type="hidden" name="date_selection_0" data-calendar-selected-ranges value="2026-12-01 ~ 2026-12-31"><input type="hidden" name="date_selection_1" value="">
  </section><div class="stay-drawer__footer"><button type="button" class="stay-btn stay-btn--primary" data-stay-action="next" data-calendar-next>다음</button></div></div>`;

// ② — `mode`: 'legacy'(묶음 전 · 셀렉트 없음 · type=number) | 'manual' | 'base_delta'
function bulkStep2(mode, ranges, baseKey = 'A1', keys = ['A1', 'A1C1_CHD']) {
  const amount = (i, col) => mode === 'legacy'
    ? `<input type="number" name="prices-${i}-${col}" data-stay-col="${col}" min="0" step="0.01">`
    : `<input type="text" name="prices-${i}-${col}" data-stay-col="${col}" inputmode="decimal">`;
  const diff = (i, col) => `<input type="text" name="prices-${i}-${col}_diff" data-stay-col-diff="${col}" placeholder="차액" inputmode="decimal">`;
  const label = (k) => k === '' ? '인원 무관 단일가' : (k === 'A1' ? 'A1 · 성인 1' : k + ' · 소아 1');
  const rows = keys.map((k, i) => {
    const base = mode === 'base_delta' && k === baseKey;
    const derived = mode === 'base_delta' && k !== baseKey;
    return `<tbody class="stay-calendar-bulk-line" data-stay-occupancy-key="${k}" data-stay-los-nights="1"${base ? ' data-calendar-link-base' : ''}>
      <tr class="stay-calendar-bulk-line__head"><th colspan="4"><input type="hidden" name="prices-${i}-occupancy_key" value="${k}"><input type="hidden" name="prices-${i}-los_nights" value="1">${label(k)} · 1박 이상${base ? ' · 기준 조합' : ''}</th></tr>
      <tr data-stay-existing><td>2026-12-01 ~ 2026-12-31</td><td class="stay-numeric">9,500</td><td class="stay-numeric">없음</td><td class="stay-numeric">없음</td></tr>
      ${derived
        ? `<tr class="stay-calendar-bulk-line__new" data-calendar-link-derived><td>새 값</td><td class="stay-numeric"><span class="stay-note">차액 +2,000</span>${diff(i, 'price')}</td><td class="stay-numeric">${diff(i, 'original_price')}</td><td class="stay-numeric">${diff(i, 'net_amount')}</td></tr>`
        : `<tr class="stay-calendar-bulk-line__new"><td>새 값</td><td class="stay-numeric">${amount(i, 'price')}</td><td class="stay-numeric">${amount(i, 'original_price')}</td><td class="stay-numeric">${amount(i, 'net_amount')}</td></tr>`}
    </tbody>`;
  }).join('');
  const link = mode === 'legacy' ? '' : `
    <input type="hidden" name="link_mode" value="${mode}"><input type="hidden" name="base_key" value="${baseKey}">
    <div class="stay-calendar-form" data-calendar-link>
      <span class="stay-calendar-form__label" id="stay_calendar_link_mode_label">연동 방식</span>
      <select name="link_mode_pick" class="browser-default" data-stay-control="link_mode" aria-labelledby="stay_calendar_link_mode_label">
        <option value="base_delta"${mode === 'base_delta' ? ' selected' : ''}>기준 조합만 입력 — 나머지는 현재 차액 유지</option>
        <option value="manual"${mode === 'manual' ? ' selected' : ''}>조합마다 직접 입력</option>
      </select>
      ${mode === 'base_delta' ? `<span class="stay-calendar-form__label" id="stay_calendar_link_base_label">기준 조합</span>
      <select name="base_key_pick" class="browser-default" data-stay-control="base_key">${keys.map((k) => `<option value="${k}"${k === baseKey ? ' selected' : ''}>${label(k)}</option>`).join('')}</select>` : ''}
    </div>
    ${mode === 'manual' ? '<p class="stay-description" data-calendar-link-reason>선택한 날짜에 기준 조합(A1 · 성인 1) 가격이 없어 조합마다 직접 입력으로 열었습니다.</p>' : ''}`;
  return `<div class="stay-root stay-readable" data-stay-screen="calendar-bulk">
    <input type="hidden" name="scope" value="plan"><input type="hidden" name="date_selection_0" value="${ranges}">
    <section class="stay-card"><h4 class="stay-section-title" data-stay-label-for="prices">선택 날짜의 가격</h4>${link}
    <table class="bs-table stay-table stay-calendar-bulk-prices" data-stay-field="prices" data-stay-kind="rows" data-stay-rows="prices">
      <thead><tr><th>기존</th><th>판매가 (JPY)</th><th>정가 (JPY)</th><th>공급 원가 (JPY)</th></tr></thead>${rows}
    </table></section>
    <div class="stay-drawer__footer"><button type="button" data-stay-action="back">기간 다시 선택</button><button type="button" class="stay-btn stay-btn--primary" data-stay-action="save">입력한 가격 적용</button></div></div>`;
}

const LINK_RESULT = `<div class="stay-root stay-readable" data-calendar-link-result>
  <div class="stay-banner stay-banner--ok" data-stay-result="saved"><span>입력한 가격을 적용했습니다.</span></div>
  <section class="stay-card"><div class="stay-banner stay-banner--warning"><span>기준 조합 가격이 없는 날 2일은 건너뛰었습니다</span></div>
  <p class="stay-description">2026-12-24 ~ 2026-12-25</p></section></div>`;

function bulkScreen({ bundle = true, defaultMode = 'manual', skipped = false, view = 'coord', keys } = {}) {
  const dom = new JSDOM(calendarPane({ bundle, view }), { url: 'https://example.test/stay/1/#stay_tab_calendar', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window, doc = w.document;
  const body = doc.getElementById('stay_drawer_body'), drawer = doc.querySelector('.stay-drawer');
  const log = { posts: [], clicks: [], redraws: 0 };
  let ranges = '';
  const render = (html) => { body.innerHTML = html; drawer.classList.add('is-open'); };
  doc.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    log.clicks.push(b.dataset.view === 'coord' ? '룸별 입력' : (b.dataset.calendarBulkAction || b.dataset.stayAction || b.textContent.trim()));
    if (b.dataset.view === 'coord') doc.getElementById('coord_area').innerHTML = calendarPane({ bundle, view: 'coord' }).match(/<div id="coord_area">([\s\S]*?)<\/div>\s*<\/div>\s*<div class="stay-drawer">/)[1];
    if (b.dataset.stayEntity === 'rate_plan' || b.dataset.stayEntity === 'offer') {
      const g = b.dataset.stayEntity;
      doc.querySelectorAll(`[data-stay-entity="${g}"]`).forEach((x) => { x.className = x.className.replace('--primary', '--ghost'); });
      b.className = b.className.replace('--ghost', '--primary');
    }
    if (b.dataset.calendarBulkAction === 'price') render(BULK_STEP1);
    if (b.dataset.stayAction === 'next' && body.querySelector('[data-calendar-selection]')) {
      ranges = body.querySelector('[name=date_selection_0]').value;
      render(bulkStep2(bundle ? defaultMode : 'legacy', ranges, 'A1', keys));
    }
  });
  doc.addEventListener('change', (e) => {
    const el = e.target;
    if (el.name === 'link_mode_pick') { log.redraws++; render(bulkStep2(el.value, ranges, 'A1', keys)); }
    if (el.name === 'base_key_pick') { log.redraws++; render(bulkStep2('base_delta', ranges, el.value, keys)); }
  });
  w.localStorage.setItem('staySteps', JSON.stringify({ steps: [] }));
  w.eval(HELPER);
  Object.assign(w.stayRun, {
    tab: async () => ({ status: 'ok' }),
    waitFor: async (fn) => !!fn(),
    submit: async (_text, opt) => {
      const root = doc.querySelector('[data-stay-screen="calendar-bulk"]');
      const save = root && root.querySelector(`[data-stay-action="${opt.action}"]`);
      if (!save) return { status: 'not-found', errors: [] };
      const post = {};
      root.querySelectorAll('input, select').forEach((i) => { if (i.name && !i.name.endsWith('_pick') && i.value !== '') post[i.name] = i.value; });
      const coord = doc.querySelector('[data-stay-entity="rate_plan"][class*="--primary"]');
      post.coord = coord && coord.dataset.stayName;
      log.posts.push(post);
      if (skipped && post.link_mode === 'base_delta') { body.innerHTML = LINK_RESULT; return { status: 'saved', errors: [] }; }
      body.innerHTML = ''; drawer.classList.remove('is-open');
      return { status: 'closed', errors: [] };
    }
  });
  w.eval(BOOT);
  return { w, doc, log };
}

const F = (label, kind, value, extra = {}) => Object.assign({ label, kind, raw_value: value }, kind === 'multi' ? { values: value } : (value === undefined ? {} : { value }), extra);
const priceLine = (label, kind, value, key, col) => F(label, kind, value, { field: 'prices', occupancy_key: key, los_nights: 1, field_col: col });
const PRICE_STEP = (over = {}) => ({
  no: 50, kind: '선택 날짜 가격 수정', title: '선택 날짜 가격 수정 (1번째, Single × 룸온리)', head: { tab: '가격 캘린더', buttons_parsed: [{ text: '선택 날짜 가격 수정' }] },
  fields: [
    F('오퍼', 'select', '2026~2027 시즌 요금'), F('객실', 'select', 'Single'), F('요금제', 'select', '룸온리'),
    F('시작일', 'typed', '2026-12-01'), F('종료일', 'typed', '2026-12-31'), F('요일', 'multi', ['월', '화', '수', '목', '금', '토', '일']),
    F('연동 방식', 'select', over.link || '기준 조합만 입력 — 나머지는 현재 차액 유지'),
  ].concat(over.noBase ? [] : [F('기준 조합', 'select', 'A1 · 성인 1')])
   .concat(over.lines || [
     priceLine('A1 · 1박 이상 · 판매가', 'typed', '9800', 'A1', 'price'),
     priceLine('A1 · 1박 이상 · 정가', 'empty', undefined, 'A1', 'original_price'),
     priceLine('A1C1_CHD · 1박 이상 · 판매가 차액', 'typed', '+2500', 'A1C1_CHD', 'price_diff')
   ])
   .map((f) => (over.fields && over.fields[f.label]) ? Object.assign({}, f, over.fields[f.label]) : f)
});

// 1) 기준 조합만 입력 — 셀렉트를 먼저 맞추고(드로어가 다시 그려진다) 기준 칸·차액 칸을 친 뒤 저장. 숨은 link_mode 가 base_delta 로 간다
{
  const { w, log } = bulkScreen({ defaultMode: 'manual' });
  const r = await w.runCalendarPriceStep(PRICE_STEP(), {});
  ok(r.submitted === true && !r.error, '기준 방식 단계가 저장된다', r);
  ok(log.redraws === 1, '연동 방식 셀렉트를 바꿔 드로어를 한 번 다시 그렸다', log.redraws);
  const p = log.posts[0];
  ok(p.link_mode === 'base_delta' && p.base_key === 'A1', '저장 POST 의 숨은 link_mode·base_key', p);
  ok(p['prices-0-price'] === '9800' && p['prices-1-price_diff'] === '+2500' && !p['prices-1-price'], '기준 줄은 새 값, 다른 줄은 차액 칸에 들어갔다', p);
  ok(p.date_selection_0 === '2026-12-01 ~ 2026-12-31' && p.coord === 'Single · 룸온리', '날짜 구간과 좌표', p);
  w.close();
}
// 1-b) 화면이 이미 기준 방식으로 열리면 셀렉트를 건드리지 않는다
{
  const { w, log } = bulkScreen({ defaultMode: 'base_delta' });
  const r = await w.runCalendarPriceStep(PRICE_STEP(), {});
  ok(r.submitted === true && log.redraws === 0, '이미 기준 방식이면 다시 그리지 않는다', [r, log.redraws]);
  w.close();
}
// 1-c) 기준 조합을 다른 키로 — base_key_pick 을 바꿔 다시 그린 뒤 친다
{
  const { w, log } = bulkScreen({ defaultMode: 'base_delta' });
  const step = PRICE_STEP({ fields: { '기준 조합': { value: 'A1C1_CHD · 소아 1' } }, lines: [
    priceLine('A1C1_CHD · 1박 이상 · 판매가', 'typed', '12,000', 'A1C1_CHD', 'price'),
    priceLine('A1 · 1박 이상 · 판매가 차액', 'typed', '-2000', 'A1', 'price_diff')] });
  step.fields.forEach((f) => { if (f.field === 'prices' && f.value) f.value = f.value.replace(/,/g, ''); });
  const r = await w.runCalendarPriceStep(step, {});
  ok(r.submitted === true && log.posts[0].base_key === 'A1C1_CHD' && log.posts[0]['prices-1-price'] === '12000' && log.posts[0]['prices-0-price_diff'] === '-2000', '기준 조합을 바꿔 그 줄에 새 값', [r, log.posts[0]]);
  w.close();
}
// 2) 기준 방식에서 건너뛴 날이 있으면 결과 조각이 남는다 — 성공 + 경고
{
  const { w } = bulkScreen({ defaultMode: 'base_delta', skipped: true });
  const r = await w.runCalendarPriceStep(PRICE_STEP(), {});
  ok(r.submitted === true && !r.error && r.submit === 'saved' && r.warn && /건너뛰었습니다/.test(r.warn[0]), '건너뜀은 실패가 아니라 경고다', r);
  ok(!w.stepFailed(r), 'stepFailed 가 실패로 읽지 않는다', r);
  w.close();
}
// 3) 조합마다 직접 입력 — 셀렉트를 manual 로 두고 각 줄의 새 값
{
  const { w, log } = bulkScreen({ defaultMode: 'base_delta' });
  const r = await w.runCalendarPriceStep(PRICE_STEP({ link: '조합마다 직접 입력', noBase: true, lines: [
    priceLine('A1 · 1박 이상 · 판매가', 'typed', '9800', 'A1', 'price'),
    priceLine('A1C1_CHD · 1박 이상 · 판매가', 'typed', '12300', 'A1C1_CHD', 'price')] }), {});
  ok(r.submitted === true && log.posts[0].link_mode === 'manual' && log.posts[0]['prices-1-price'] === '12300', '직접 입력으로 바꿔 저장', [r, log.posts[0]]);
  w.close();
}
// 4) 묶음 전 화면(운영 ERP) — 셀렉트가 없다. 직접 입력은 그대로(쉼표 뗀 숫자 · type=number), 기준 방식은 사람 몫
{
  const { w, log } = bulkScreen({ bundle: false });
  const manual = await w.runCalendarPriceStep(PRICE_STEP({ link: '조합마다 직접 입력', noBase: true, lines: [
    priceLine('A1 · 1박 이상 · 판매가', 'typed', '9800', 'A1', 'price')] }), {});
  ok(manual.submitted === true && log.posts[0]['prices-0-price'] === '9800' && !log.posts[0].link_mode, '묶음 전 화면에서도 직접 입력은 그대로 저장(link_mode 없이)', [manual, log.posts[0]]);
  const base = await w.runCalendarPriceStep(PRICE_STEP(), {});
  ok(base.manualAction === true && base.submitted === false && log.posts.length === 1 && /기준 조합만 입력/.test(base.error), '기준 방식 원고는 저장하지 않고 사람에게 넘긴다', base);
  w.close();
}
// 5) 화면 표에 없는 줄(A2)은 멈춘다 — 저장하지 않는다
{
  const { w, log } = bulkScreen({ defaultMode: 'base_delta' });
  const r = await w.runCalendarPriceStep(PRICE_STEP({ lines: [
    priceLine('A1 · 1박 이상 · 판매가', 'typed', '9800', 'A1', 'price'),
    priceLine('A2 · 1박 이상 · 판매가 차액', 'typed', '+100', 'A2', 'price_diff')] }), {});
  ok(r.submitted === false && log.posts.length === 0 && r.bad.some((b) => /A2/.test(b)), '없는 줄이 있으면 저장하지 않는다', r);
  w.close();
}
// 6) 요일 일부 — 날짜 구간은 기간 ∩ 요일을 줄마다(화면 스크립트와 같은 꼴), dry 는 아무것도 누르지 않는다
{
  const { w, log } = bulkScreen({ defaultMode: 'base_delta' });
  const dry = await w.runCalendarPriceStep(PRICE_STEP({ fields: { '요일': { values: ['금', '토'] }, '종료일': { value: '2026-12-12' } } }), { dry: true });
  ok(dry.dry === true && log.clicks.length === 0, 'dry 는 누르지 않는다', [dry, log.clicks]);
  ok(JSON.stringify(dry.want.dates) === JSON.stringify(['2026-12-04 ~ 2026-12-05', '2026-12-11 ~ 2026-12-12']) && dry.want.days === 4, '금·토만의 날짜 구간', dry.want);
  const r = await w.runCalendarPriceStep(PRICE_STEP({ fields: { '요일': { values: ['금', '토'] }, '종료일': { value: '2026-12-12' } } }), {});
  ok(r.submitted === true && log.posts[0].date_selection_0 === '2026-12-04 ~ 2026-12-05\n2026-12-11 ~ 2026-12-12', '숨은 date_selection_0 에 줄마다 구간', log.posts[0]);
  w.close();
}
// 7) [전체 보기] 에 있으면 [룸별 입력] 으로 바꿔 칩을 고른다
{
  const { w, log } = bulkScreen({ defaultMode: 'base_delta', view: 'overview' });
  const r = await w.runCalendarPriceStep(PRICE_STEP(), {});
  ok(r.submitted === true && log.clicks.indexOf('룸별 입력') >= 0 && log.clicks.indexOf('룸별 입력') < log.clicks.indexOf('price'), '개요 화면이면 룸별 입력으로 바꾼 뒤 연다', [r, log.clicks.slice(0, 4)]);
  w.close();
}

// ─────────────── 선택 날짜 가격 가감 ───────────────
const OFFERS = { '1': { name: '2026~2027 시즌 요금', rooms: [['11', 'Single'], ['12', 'Twin'], ['13', '패밀리룸']], plans: [['p1', '룸온리'], ['p2', '조식 포함']], occ: [['A1', 'A1 · 성인 1'], ['A2', 'A2 · 성인 2'], ['A1C1_CHD', 'A1C1_CHD · 소아 1']] },
                 '2': { name: '2027 겨울 요금', rooms: [['21', 'Single']], plans: [['p1', '룸온리']], occ: [['A1', 'A1 · 성인 1']] } };
function adjustSelect(offerId, { history = [] } = {}) {
  const o = OFFERS[offerId];
  const boxes = (name, rows) => rows.map(([v, l]) => `<label class="check_form"><input type="checkbox" class="filled-in" name="${name}" data-stay-field="${name}" value="${v}" checked><span>${l}</span></label>`).join('');
  const hist = history.length ? `<section class="stay-card"><h4 class="stay-section-title">최근 가감</h4><table><tbody>${history.map((h, i) => `<tr data-stay-row="${i + 1}"><td>${h.when}${h.undone ? ' · 되돌림' : ''}</td><td>${h.offer}</td><td>${h.adjust}</td><td>10</td><td>0</td><td></td></tr>`).join('')}</tbody></table></section>` : '';
  return `<div id="stay_calendar_adjust_x" class="stay-root stay-readable" data-calendar-adjust="select" data-calendar-selection>${hist}
    <section class="stay-card"><h4 class="stay-section-title">대상 선택</h4>
      <select name="offer" data-stay-field="offer" data-adjust-keep>${Object.entries(OFFERS).map(([id, x]) => `<option value="${id}"${id === offerId ? ' selected' : ''}>${x.name}</option>`).join('')}</select>
      ${boxes('rooms', o.rooms)}${boxes('plans', o.plans)}${periodRows()}${boxes('occupancy', o.occ)}
      <label class="check_form"><input type="radio" name="los" value="all" checked><span>전 층</span></label>
      <label class="check_form"><input type="radio" name="los" value="one"><span>1박 층만</span></label>
      <input type="hidden" name="date_selection_0" data-calendar-selected-ranges value="2026-12-01 ~ 2026-12-31"><input type="hidden" name="month" value="2026-12">
    </section>
    <section class="stay-card"><h4 class="stay-section-title">가감 입력</h4>
      <input type="text" name="adjust" value="" data-stay-field="adjust">
      <label class="check_form"><input type="checkbox" class="filled-in" name="adjust_original" value="1"><span>정가도 같이 조정</span></label>
      <label class="check_form"><input type="checkbox" class="filled-in" name="include_manual" value="1"><span>날짜별로 직접 고친 가격도 같이 바꾸기</span></label>
      <label class="check_form"><input type="checkbox" class="filled-in" name="include_extra" value="1"><span>추가 인원 요금도 같이 조정</span></label>
    </section>
    <div class="stay-drawer__footer"><button type="button" class="stay-btn stay-btn--primary" data-stay-action="next" data-calendar-next>다음</button></div></div>`;
}
const adjustConfirm = (applied, skipped) => `<div class="stay-root stay-readable" data-calendar-adjust="confirm">
  <section class="stay-card" data-stay-summary><h4 class="stay-section-title">확인</h4>
  <p class="stay-description"><strong>대상 ${applied + skipped}칸 · 적용 ${applied}칸 · 건너뜀 ${skipped}칸</strong></p></section>
  <div class="stay-drawer__footer"><button type="button" data-stay-action="back">기간 다시 선택</button>
  <button type="button" class="stay-btn stay-btn--primary" data-stay-action="save"${applied ? '' : ' disabled'}>가감 적용</button></div></div>`;
const adjustDone = (applied, skipped) => `<div class="stay-root stay-readable" data-calendar-adjust="done">
  <div class="stay-banner stay-banner--ok" data-stay-result="saved"><span>가감을 적용했습니다 — 적용 ${applied}칸 · 건너뜀 ${skipped}칸</span></div>
  <div class="stay-drawer__footer"><a class="stay-btn stay-btn--ghost" href="/log" data-calendar-adjust-action="log" download>적용 기록 내려받기</a>
  <button type="button" class="stay-btn stay-btn--secondary" data-stay-action="undo" data-calendar-adjust-action="undo">되돌리기</button></div></div>`;

function adjustScreen({ bundle = true, history = [], applied = 40, skipped = 2, refuseAdjust = false } = {}) {
  const dom = new JSDOM(calendarPane({ bundle }), { url: 'https://example.test/stay/1/#stay_tab_calendar', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window, doc = w.document;
  const body = doc.getElementById('stay_drawer_body'), drawer = doc.querySelector('.stay-drawer');
  const log = { gets: [], posts: [], clicks: [] };
  const render = (html) => { body.innerHTML = html; drawer.classList.add('is-open'); };
  const form = () => {
    const out = {};
    body.querySelectorAll('input, select').forEach((i) => {
      if (!i.name) return;
      if ((i.type === 'checkbox' || i.type === 'radio') && !i.checked) return;
      (out[i.name] = out[i.name] || []).push(i.value);
    });
    return out;
  };
  doc.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    log.clicks.push(b.dataset.calendarAdjustAction || b.dataset.stayAction || b.textContent.trim());
    if (b.dataset.stayEntity === 'offer') {   // 캘린더 오퍼 칩 — 드로어가 처음 고를 오퍼가 바뀐다
      doc.querySelectorAll('[data-stay-entity="offer"]').forEach((x) => { x.className = x.className.replace('--primary', '--ghost'); });
      b.className = b.className.replace('--ghost', '--primary');
    }
    if (b.dataset.calendarAdjustAction === 'open') {
      const cur = doc.querySelector('[data-stay-entity="offer"][class*="--primary"]');
      render(adjustSelect(cur && cur.dataset.stayName === '2027 겨울 요금' ? '2' : '1', { history }));
    }
    if (b.dataset.stayAction === 'next' && body.querySelector('[data-calendar-adjust="select"]')) {
      const got = form(); log.gets.push(got);
      if (refuseAdjust) {
        render(adjustSelect(got.offer[0], { history }).replace('<input type="text" name="adjust" value="" data-stay-field="adjust">',
          '<input type="text" name="adjust" value="12" data-stay-field="adjust"><small class="error" data-stay-error-for="adjust">조정 값은 부호를 붙여 주세요 — 예: -8 (8 싸게) · -5% (5% 싸게) · +12 (12 비싸게)</small>'));
        return;
      }
      render(adjustConfirm(applied, skipped));
    }
    if (b.dataset.stayAction === 'undo') log.undo = true;
  });
  doc.addEventListener('change', (e) => {
    if (e.target.name === 'offer' && body.querySelector('[data-calendar-adjust="select"]')) render(adjustSelect(e.target.value, { history }));
  });
  w.localStorage.setItem('staySteps', JSON.stringify({ steps: [{ no: 13, kind: '판매 연결 한 번에 만들기', fields: [{ label: '오퍼별 표시명 · Family', kind: 'typed', value: '패밀리룸' }] }] }));
  w.eval(HELPER);
  Object.assign(w.stayRun, {
    tab: async () => ({ status: 'ok' }),
    waitFor: async (fn) => !!fn(),
    submit: async (_text, opt) => {
      const save = body.querySelector(`[data-stay-action="${opt.action}"]`);
      if (!save || save.disabled) return { status: 'not-found', errors: [] };
      log.posts.push(log.gets[log.gets.length - 1]);
      render(adjustDone(applied, skipped));
      return { status: 'saved', errors: [] };
    }
  });
  w.eval(BOOT);
  return { w, doc, log };
}
const ADJUST_STEP = (over = {}) => ({
  no: 51, kind: '선택 날짜 가격 가감', title: '선택 날짜 가격 가감 (1번째, 2026~2027 시즌 요금 · +5%)', head: { tab: '가격 캘린더' },
  fields: [
    F('오퍼', 'select', '2026~2027 시즌 요금'), F('객실', 'multi', ['Single', 'Family']), F('요금제', 'select', '룸온리'),
    F('시작일', 'typed', '2026-12-01'), F('종료일', 'typed', '2026-12-31'), F('요일', 'multi', ['금', '토']),
    F('인원 조합', 'multi', ['A1', 'A2 · 성인 2']), F('박수 층', 'select', '1박 층만'), F('가감', 'typed', '+5%'),
    F('정가도 같이 조정', 'check'), F('날짜별로 직접 고친 가격도 같이 바꾸기', 'uncheck'), F('추가 인원 요금도 같이 조정', 'check')
  ].map((f) => (over[f.label] ? Object.assign({}, f, over[f.label]) : f))
});

// 8) 가감 — ① 을 원고대로 맞추고(룸 이름 `Family` 는 오퍼별 표시명 `패밀리룸` 칸) 확인 → [가감 적용]. 되돌리기·내려받기는 누르지 않는다
{
  const { w, log } = adjustScreen();
  const r = await w.runCalendarAdjustStep(ADJUST_STEP(), {});
  ok(r.submitted === true && !r.error && r.submit === 'saved', '가감 단계가 저장된다', r);
  const g = log.posts[0];
  ok(JSON.stringify(g.rooms) === JSON.stringify(['11', '13']) && JSON.stringify(g.plans) === JSON.stringify(['p1']), '객실(표시명 포함)·요금제는 적은 것만 켠다', g);
  ok(JSON.stringify(g.occupancy) === JSON.stringify(['A1', 'A2']) && g.los[0] === 'one' && g.adjust[0] === '+5%', '인원 조합(키로)·박수 층·가감', g);
  ok(g.adjust_original && g.include_extra && !g.include_manual, '체크 셋은 원고대로', g);
  ok(g.date_selection_0[0] === '2026-12-04 ~ 2026-12-05\n2026-12-11 ~ 2026-12-12\n2026-12-18 ~ 2026-12-19\n2026-12-25 ~ 2026-12-26', '기간 ∩ 금·토', g.date_selection_0);
  ok(r.preview.applied === 40 && r.preview.skipped === 2 && r.result.skipped === 2 && r.warn && /건너뛴 칸 2칸/.test(r.warn[0]), '확인·결과의 칸 수를 남기고 건너뜀은 경고', r);
  ok(!log.undo && !log.clicks.includes('undo') && !log.clicks.includes('log'), '[되돌리기]·[적용 기록 내려받기] 는 누르지 않는다', log.clicks);
  ok(!w.stepFailed(r), '건너뜀이 있어도 성공이다', r);
  w.close();
}
// 8-b) 오퍼를 바꾸면 다시 그려진 ① 에서 맞춘다
{
  const { w, log } = adjustScreen();
  const r = await w.runCalendarAdjustStep(ADJUST_STEP({ '오퍼': { value: '2027 겨울 요금' }, '객실': { kind: 'select', value: 'Single', values: undefined }, '인원 조합': { kind: 'select', value: 'A1', values: undefined } }), {});
  ok(r.submitted === true && log.posts[0].offer[0] === '2' && JSON.stringify(log.posts[0].rooms) === JSON.stringify(['21']), '오퍼를 먼저 바꾸고 그 오퍼의 객실을 고른다', [r, log.posts[0]]);
  w.close();
}
// 8-c) 캘린더 오퍼 칩이 못 바뀌어도(드로어가 다른 오퍼로 열려도) 드로어의 오퍼 셀렉트를 바꿔 다시 그린 뒤 맞춘다
{
  const { w, doc, log } = adjustScreen();
  doc.querySelectorAll('[data-stay-entity="offer"]').forEach((x) => x.removeAttribute('data-stay-entity'));
  const r = await w.runCalendarAdjustStep(ADJUST_STEP({ '오퍼': { value: '2027 겨울 요금' }, '객실': { kind: 'select', value: 'Single', values: undefined }, '인원 조합': { kind: 'select', value: 'A1', values: undefined } }), {});
  ok(r.submitted === true && log.posts[0].offer[0] === '2' && JSON.stringify(log.posts[0].rooms) === JSON.stringify(['21']), '드로어의 오퍼 셀렉트로 바꾼다', [r, log.posts[0]]);
  w.close();
}
// 9) 두 번 올라가지 않게 — 같은 오퍼·같은 가감·되돌림 아님이면 사람에게 묻는다. 되돌림 줄은 막지 않는다. allowRepeat 이면 간다
{
  const hist = [{ when: '2026-11-13 10:00', offer: '2026~2027 시즌 요금', adjust: '+5%' }];
  const a = adjustScreen({ history: hist });
  const r = await a.w.runCalendarAdjustStep(ADJUST_STEP(), {});
  ok(r.manualAction === true && r.submitted === false && a.log.posts.length === 0 && /이미 적용돼 있습니다/.test(r.error), '같은 가감이 이미 있으면 멈춘다', r);
  const again = await a.w.runCalendarAdjustStep(ADJUST_STEP(), { allowRepeat: true });
  ok(again.submitted === true, 'allowRepeat 이면 사람이 확인한 것으로 보고 간다', again);
  a.w.close();
  const b = adjustScreen({ history: [Object.assign({ undone: true }, hist[0]), { when: '2026-11-12 09:00', offer: '2026~2027 시즌 요금', adjust: '+10%' }] });
  const r2 = await b.w.runCalendarAdjustStep(ADJUST_STEP(), {});
  ok(r2.submitted === true, '되돌린 줄·다른 가감 글자는 막지 않는다', r2);
  b.w.close();
  const c = adjustScreen({ history: [{ when: '2026-11-13 10:00', offer: '2026~2027 시즌 요금', adjust: '+1,000' }] });
  const r3 = await c.w.runCalendarAdjustStep(ADJUST_STEP({ '가감': { value: '+1000', raw_value: '+1000' } }), {});
  ok(r3.manualAction === true, '쉼표만 다른 같은 가감도 같은 것으로 본다', r3);
  c.w.close();
}
// 10) 적용 0칸이면 [가감 적용] 이 꺼져 있다 — 실패로 멈춘다 / ① 오류는 글자 그대로 전한다 / 묶음 전 ERP 는 사람 몫
{
  const a = adjustScreen({ applied: 0, skipped: 5 });
  const r = await a.w.runCalendarAdjustStep(ADJUST_STEP(), {});
  ok(r.submitted === false && /0칸/.test(r.error) && a.log.posts.length === 0, '적용 0칸이면 저장하지 않는다', r);
  a.w.close();
  const b = adjustScreen({ refuseAdjust: true });
  const r2 = await b.w.runCalendarAdjustStep(ADJUST_STEP(), {});
  ok(r2.error && /부호를 붙여 주세요/.test(r2.error) && b.log.posts.length === 0, '① 오류 글자를 그대로 전한다', r2);
  b.w.close();
  const c = adjustScreen({ bundle: false });
  const r3 = await c.w.runCalendarAdjustStep(ADJUST_STEP(), {});
  ok(r3.manualAction === true && /가감\] 창이 없습니다/.test(r3.error), '가감 버튼이 없는 ERP 는 사람에게 넘긴다', r3);
  c.w.close();
}
// 11) runStepCore 가 두 갈래를 전용 러너로 보낸다
{
  const { w } = adjustScreen();
  w.__steps.steps.push(ADJUST_STEP());
  const r = await w.runStepCore(51, { dry: true });
  ok(r.dry === true && r.want && r.want.adjust === '+5%', 'runStepCore → runCalendarAdjustStep', r);
  w.close();
}

// ─────────────── 시즌 [가격 입력] 의 입력 기억 ───────────────
const seasonFill = ({ memory, overwrite }) => `<div id="stay_season_fill_form_x" class="stay-card" data-stay-screen="season-price-fill" data-stay-card="main">
  ${memory ? '<div class="stay-banner stay-banner--info"><span>마지막 입력값을 채웠습니다 — 2026-11-13 14:12</span> <button type="button" class="stay-btn stay-btn--ghost" hx-get="/stay/1/seasons/7/fill/?blank=1">비우기</button></div>' : ''}
  <table class="bs-table stay-table"><tbody>
    <tr><th><label for="p">판매 단가(공급 통화)</label></th><td><input id="p" type="text" name="price" data-stay-field="price" value="${memory ? '180' : ''}"></td></tr>
    <tr><th><label for="k">인원 조합(선택)</label></th><td><input id="k" type="text" name="occupancy_keys" data-stay-field="occupancy_keys" value="${memory ? 'A2,A3' : ''}"></td></tr>
    <tr><th><label for="j">인원 조합별 조정(선택)</label></th><td><input id="j" type="text" name="occupancy_adjust" data-stay-field="occupancy_adjust" value="${memory ? 'A3:+14' : ''}"></td></tr>
    <tr><th><label for="o">이미 값이 있는 날도 덮기</label></th><td><input id="o" type="checkbox" name="overwrite" data-stay-field="overwrite"${overwrite ? ' checked' : ''}></td></tr>
  </tbody></table></div>`;
{
  const dom = new JSDOM(`<div id="stay_tab_seasons"></div><div class="stay-drawer is-open"><div id="stay_drawer_body">${seasonFill({ memory: true, overwrite: true })}</div></div>`,
    { url: 'https://example.test/stay/1/#stay_tab_seasons', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window, doc = w.document;
  let blanks = 0;
  doc.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (b && /blank=1/.test(b.getAttribute('hx-get') || '')) { blanks++; doc.getElementById('stay_drawer_body').innerHTML = seasonFill({ memory: false, overwrite: true }); }
  });
  w.localStorage.setItem('staySteps', JSON.stringify({ steps: [] }));
  w.eval(HELPER);
  w.stayRun.waitFor = async (fn) => !!fn();
  w.eval(BOOT);
  const sf = await w.seasonFillFresh();
  ok(sf.status === 'cleared' && blanks === 1 && /마지막 입력값/.test(sf.note), '[비우기] 로 지난 입력값을 걷어 낸다', sf);
  ok(doc.querySelector('[name=occupancy_adjust]').value === '' && doc.querySelector('[name=price]').value === '', '원고가 적지 않을 칸이 비었다');
  const again = await w.seasonFillFresh();
  ok(again.status === 'no-memory' && blanks === 1, '기억이 없는 창(묶음 전 화면 포함)은 그대로 둔다', again);
  // 원고에 `덮기` 줄이 없으면 종전 기본값(해제)으로 — 체크된 채 열려도 끈다
  const step = { fields: [{ label: '판매 단가(공급 통화)', kind: 'typed', value: '200' }, { label: '인원 조합(선택)', kind: 'typed', value: 'A2' }] };
  const plan = w.seasonFillFields(step, step.fields.slice());
  ok(plan.implied === true && plan.fields.some((f) => f.label === '이미 값이 있는 날도 덮기' && f.kind === 'uncheck'), '덮기 줄이 없으면 해제를 더한다', plan);
  const res = await w.stayRun.fill(plan.fields);
  ok(res.every((x) => x.status === 'ok') && doc.querySelector('[name=overwrite]').checked === false && doc.querySelector('[name=price]').value === '200', '덮기가 해제되고 원고 값이 들어갔다', res);
  const withLine = { fields: step.fields.concat([{ label: '이미 값이 있는 날도 덮기', kind: 'check' }]) };
  ok(w.seasonFillFields(withLine, withLine.fields).implied === false, '덮기 줄이 있으면 원고대로 둔다');
  w.close();
}

// ─────────────── [판매 시작] 앞 배너 ───────────────
{
  const dom = new JSDOM(`<div id="stay_validation_banner" class="stay-root" data-stay-screen="validation">
      <div class="stay-banner stay-banner--blocking"><div><strong>🔴 이대로면 못 팝니다</strong></div>
      <div>오퍼 '2026~2027 시즌 요금'의 연령 구간 — 만 4세가 어느 구간에도 없습니다. 이 나이는 성인 요금으로 계산됩니다.</div></div>
      <div class="stay-gate" data-stay-card="gate"><button type="button" data-stay-action="activate">판매 시작</button></div></div>`,
    { url: 'https://example.test/stay/1/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.localStorage.setItem('staySteps', JSON.stringify({ steps: [] }));
  w.eval(HELPER);
  w.eval(BOOT);
  const b = w.saleStartBanner();
  ok(b.blockers.length === 1 && b.ageBand.length === 1 && /연령 구간/.test(b.note) && /넘어가기로 풀 수 없습니다/.test(b.note), '연령 구간 차단을 사람 말로 남긴다', b);
  // 고리는 `판매 시작` 단계 앞에서 서고, 그때의 배너를 runStatus 에 싣는다(누르지 않는다)
  let pressed = 0;
  w.document.querySelector('[data-stay-action="activate"]').addEventListener('click', () => { pressed++; });
  w.__steps.steps.push({ no: 1, kind: '판매 시작', title: '판매 시작', head: {}, fields: [] });
  const started = w.runAll({ from: 1 });
  for (let i = 0; i < 50 && w.runStatus().running; i++) await new Promise((r) => w.setTimeout(r, 10));
  const st = w.runStatus();
  ok(started && st.reason === 'sale-start' && st.banner && st.banner.ageBand.length === 1 && pressed === 0, '판매 시작 앞에서 서고 배너를 싣는다', st);
  w.stayRun.progressHide();
  w.close();
}

// ─────────────── 금액은 숫자로 견준다 ───────────────
{
  const dom = new JSDOM(`<div class="stay-drawer is-open"><div id="stay_drawer_body"><label for="a">판매가</label><input id="a" type="text" name="price" value="1,234.50"></div></div>`,
    { url: 'https://example.test/stay/1/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window, R = (() => { w.eval(HELPER); return w.stayRun; })();
  ok(R.readback([{ label: '판매가', kind: 'typed', value: '1234.5' }]).ok === 1, '`1,234.50` 과 `1234.5` 는 같다');
  w.document.getElementById('a').value = '15';
  ok(R.readback([{ label: '판매가', kind: 'typed', value: '1.5' }]).mismatch.length === 1, '`15` 와 `1.5` 는 다르다(글자 견주기의 구멍)');
  w.document.getElementById('a').value = '-5%';
  ok(R.readback([{ label: '판매가', kind: 'typed', value: '-5%' }]).ok === 1 && R.readback([{ label: '판매가', kind: 'typed', value: '-5' }]).mismatch.length === 1, '% 는 % 끼리만 같다');
  w.document.getElementById('a').value = '+2,500';
  ok(R.readback([{ label: '판매가', kind: 'typed', value: '+2500' }]).ok === 1, '부호 있는 차액도 쉼표를 떼고 견준다');
  w.close();
}

console.log(`calendar step tests passed (${pass} checks: base/manual link, base key, skipped result, pre-bundle screen, missing row, weekdays, adjust, repeat guard, zero apply, season memory, sale-start banner, numeric readback)`);
