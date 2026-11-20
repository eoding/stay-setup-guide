// 페이지 쪽 시험의 받침 — jsdom 위에 ERP Stay 화면을 세우고 러너의 도우미·부트와 `stay_price.js` 를 그대로 올린다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
//
// 화면은 캡처한 ERP 마크업이다: 가격 캘린더(`panel--calendar--1/2.html`), 가격 수정 ①·②, 가감 ①·②
// (`stay-setup-run/tests/fixtures/erp/`), 가격 수정 ②·가감 ② 의 손 조각(`tests/fixtures/erp/`). 셀 창은 캡처가 없어
// ERP 템플릿 `_calendar_cell_edit.html` 의 표식을 따라 손으로 그린다(`cellWindow`). htmx 대신 문서에 붙인 클릭 듣개가
// 서버처럼 조각을 갈아 끼운다 — 벽(window 캡처 단계)이 막은 클릭은 여기 닿지 않으므로 `log.reached` 가 증거다.
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const require = createRequire(import.meta.url);
export const JSDOM_MISSING = 'jsdom 을 찾지 못해 화면 시험을 돌릴 수 없습니다(건너뛰지 않고 실패합니다). jsdom 이 있는 node_modules 를 '
  + 'NODE_PATH 로 주세요 — 예: NODE_PATH=/path/to/node_modules node --test tests/test_page_*.mjs';
export function loadJsdom(load = require) {
  try { return load('jsdom').JSDOM; } catch (e) { throw new Error(JSDOM_MISSING); }
}
let JSDOM;
try { JSDOM = loadJsdom(); } catch (e) { console.error(e.message); process.exit(1); }

export const HERE = dirname(fileURLToPath(import.meta.url));
export const SKILL = join(HERE, '..');
const RUNNER = join(SKILL, '..', 'stay-setup-run');
export const HELPER = readFileSync(join(RUNNER, 'scripts', 'stay_helper.js'), 'utf8');
export const BOOT = readFileSync(join(RUNNER, 'scripts', 'stay_boot.js'), 'utf8');
export const PAGE = readFileSync(join(SKILL, 'scripts', 'page', 'stay_price.js'), 'utf8');
export const runFixture = (name) => readFileSync(join(RUNNER, 'tests', 'fixtures', 'erp', name), 'utf8');
export const ownFixture = (name) => readFileSync(join(SKILL, 'tests', 'fixtures', 'erp', name), 'utf8');
export const OWN_FIXTURES = join(SKILL, 'tests', 'fixtures', 'erp');

export const OFFER = '〈오퍼 관리용 이름〉';
export const RUNNER_STEPS = JSON.stringify({ steps: [{ no: 1, kind: '러너가 올려 둔 단계' }] });
export const RUNNER_CURSOR = JSON.stringify({ at: 7 });

// 다른 탭의 위험한 단추들 — 벽이 막는지 볼 과녁(ERP 템플릿의 표식 그대로)
const OTHER_TABS = `
<div id="stay_tab_offers" class="stay-pane" data-stay-tab="offers" style="display:none">
  <button type="button" class="stay-btn stay-btn--danger" data-stay-action="delete">삭제</button>
  <button type="button" class="stay-btn stay-btn--ghost" data-stay-action="archive">보관</button>
  <button type="button" class="stay-btn stay-btn--danger" data-stay-action="end">판매 종료</button>
</div>
<div id="stay_tab_sale_days" class="stay-pane" data-stay-tab="sale_days" style="display:none">
  <button type="button" class="stay-btn stay-btn--ghost" data-stay-action="close_month">7월 닫기</button>
</div>
<div class="stay-banner" data-stay-card="gate"><button type="button" class="stay-btn stay-btn--primary" data-stay-action="activate">판매 시작</button></div>`;

const ROWS = [
  { pk: '501', key: '', label: '인원 무관 단일가', los: '1', price: '120000.00', list: '150000.00', net: '90000.00' },
  { pk: '502', key: 'A2', label: 'A2 · 성인 2', los: '1', price: '150000.00', list: '', net: '110000.00' }
];

// 셀 창 — `_calendar_cell_edit.html` 의 뿌리·머리·[닫기]·행·[저장]·추가 줄 표식
export function cellWindow({ date = '2026-07-01', room = '〈오퍼 관리용 이름〉 · 디럭스', plan = '조식 포함', rows = ROWS, notice = '', error = '' } = {}) {
  const body = rows.map((r) => `
    <tr id="cell_row_${r.pk}" data-stay-row="${r.pk}">
      <td rowspan="1" class="stay-cell-group">${r.label}</td>
      <td><input type="hidden" name="occupancy_key" value="${r.key}"><input type="text" name="los_nights" value="${r.los}" data-stay-field="los_nights" data-stay-kind="number"></td>
      <td><input type="text" name="price" value="${r.price}" data-stay-field="price"></td>
      <td><input type="text" name="original_price" value="${r.list}" data-stay-field="original_price"></td>
      <td><input type="text" name="net_amount" value="${r.net}" data-stay-field="net_amount"></td>
      <td><select name="availability_status" data-stay-field="availability_status"><option value="1" selected>판매 가능</option></select></td>
      <td><button type="button" class="stay-btn stay-btn--primary" data-stay-action="save_cell" hx-post="/stay/1/cells/${r.pk}/save/" hx-include="#cell_row_${r.pk} :is(input,select)" hx-target="#stay_cell_edit" hx-swap="outerHTML" hx-disable="this">저장</button></td>
    </tr>${error && r.pk === rows[0].pk ? `<tr><td colspan="6"><div class="stay-banner stay-banner--blocking" data-stay-result="error"><span>${error}</span></div></td></tr>` : ''}`).join('');
  return `<div id="stay_cell_edit" class="stay-modal stay-modal--page" data-stay-screen="price-cell">
  <div class="stay-modal__mask"><div class="stay-modal__panel" role="dialog" aria-modal="true" aria-label="가격 셀 편집">
    <div class="stay-modal__head">
      <h4 class="stay-modal__title"><span class="stay-card__title">${room}</span> · ${plan} · ${date}</h4>
      <button data-stay-action="close" type="button" class="stay-btn stay-btn--ghost" hx-get="/stay/1/calendar/?month=${date.slice(0, 7)}&amp;view=coord&amp;option=11&amp;rate_plan=21" hx-target="#stay_calendar" hx-swap="outerHTML">닫기</button>
    </div>
    ${notice ? `<div class="stay-banner stay-banner--ok"><span>${notice}</span></div>` : ''}
    <div class="table1" data-stay-card="main"><table class="bs-table stay-table">
      <thead><tr><th data-stay-label-for="occupancy_key">인원 조합</th><th data-stay-label-for="los_nights">박수~</th><th data-stay-label-for="price">판매가</th><th data-stay-label-for="original_price">정가</th><th data-stay-label-for="net_amount">공급 원가</th><th data-stay-label-for="availability_status">상태</th><th>액션</th></tr></thead>
      <tbody>${body}</tbody></table></div>
    <h4 class="stay-section-title">인원별 · 박수별 가격 추가</h4>
    <div id="stay_cell_add_x" class="table1" data-stay-card="add"><table class="bs-table stay-table"><tbody><tr data-stay-row="new">
      <td><input type="text" name="occupancy_key" data-stay-field="occupancy_key"></td><td><input type="text" name="los_nights" value="1"></td>
      <td><input type="text" name="price"></td><td><input type="text" name="original_price"></td><td><input type="text" name="net_amount"></td><td></td>
      <td><input type="hidden" name="option" value="{room:1}"><input type="hidden" name="rate_plan" value="{rate_plan:1}"><input type="hidden" name="date" value="${date}">
        <button type="button" class="stay-btn stay-btn--primary" data-stay-action="add_cell" hx-post="/stay/1/cells/new/">추가</button></td>
    </tr></tbody></table></div>
  </div></div>
</div>`;
}

// ②(확인) 조각에 서버가 받은 값을 숨은 칸으로 되싣는다 — ERP 가 고른 그대로 그리는 것과 같다
function echoHidden(html, values, offerName) {
  let out = html;
  Object.keys(values).forEach((name) => { out = out.replace(new RegExp(`<input type="hidden" name="${name}"[^>]*>`, 'g'), ''); });
  const inputs = Object.entries(values).flatMap(([name, list]) => list.map((v) => `<input type="hidden" name="${name}" value="${v.replace(/"/g, '&quot;')}">`)).join('');
  out = out.replace(/(<div [^>]*data-stay-screen="calendar-(?:bulk|adjust)"[^>]*>)/, `$1${inputs}`);
  if (offerName) out = out.replace(/<dt>오퍼<\/dt><dd>[^<]*<\/dd>/, `<dt>오퍼</dt><dd>${offerName}</dd>`);
  return out;
}
const formValues = (root, names) => Object.fromEntries(names.map((name) => [name, [...root.querySelectorAll(`[name="${name}"]`)]
  .filter((el) => !(el.type === 'checkbox' || el.type === 'radio') || el.checked).map((el) => el.value)]));

/**
 * ERP 한 장. `opts`:
 *   start        'coord'(기본, 룸별 입력 · 2026-07) | 'overview'(전체 보기 — [룸별 입력] 을 눌러야 칩이 선다)
 *   tab          'offers' 면 오퍼 탭이 켜진 채로 연다(가격 캘린더 탭을 눌러야 한다)
 *   bulkReview   가격 수정 ② 조각(기본: 캡처 price-step2)       bulkReviewManual  연동 방식을 「직접 입력」으로 바꾼 ②
 *   adjustReview 가감 ② 조각(기본: 손 조각 adjust-rejected)
 *   onBulkSave   (page) => 'saved'(기본: 드로어 닫고 저장 표지) | '403'(CSRF 거절 — 드로어가 남는다)
 *   cell         셀 창 그리기 값 {date, plan, rows} · cellSave 'ok'|'error'
 *   withScripts  false 면 도우미·부트 없이 `stay_price.js` 만 올린다
 */
export function erpPage(opts = {}) {
  const o = Object.assign({ start: 'coord', bulkReview: runFixture('calendar-bulk--price-step2.html'), adjustReview: ownFixture('adjust-rejected.html'),
    cell: {}, cellSave: 'ok', withScripts: true }, opts);
  // 캡처한 7월 판을 다른 달로 — 달 머리·칸 날짜·[이전 달]/[다음 달] 의 달을 옮긴다
  const shift = (month, by) => { const d = new Date(month + '-01T00:00:00Z'); d.setUTCMonth(d.getUTCMonth() + by); return d.toISOString().slice(0, 7); };
  const panelOf = (start, month = '2026-07') => start === 'overview' ? runFixture('panel--calendar--1.html')
    : runFixture('panel--calendar--2.html').replaceAll('2026-06', '@prev').replaceAll('2026-08', '@next').replaceAll('2026-07', month)
      .replaceAll('@prev', shift(month, -1)).replaceAll('@next', shift(month, 1));
  const html = `<ul class="tab_style1 tab-container">
    <li class="tab"><a href="#stay_tab_offers" data-stay-tab="offers"${o.tab === 'offers' ? ' class="active"' : ''}><span>오퍼</span></a></li>
    <li class="tab"><a href="#stay_tab_sale_days" data-stay-tab="sale_days"><span>판매일</span></a></li>
    <li class="tab"><a href="#stay_tab_calendar" data-stay-tab="calendar"${o.tab === 'offers' ? '' : ' class="active"'}><span>가격 캘린더</span></a></li>
  </ul>${OTHER_TABS}
  <div id="stay_tab_calendar" class="col s12 stay-pane stay-root" data-stay-tab="calendar">${panelOf(o.start)}</div>
  <div class="stay-drawer"><aside class="stay-drawer__panel" role="dialog"><header class="stay-drawer__header"><h4 class="stay-drawer__title"></h4>
    <button type="button" class="stay-drawer__close" aria-label="닫기">&times;</button></header>
    <div class="stay-drawer__context" id="stay_drawer_context"></div><div class="stay-drawer__body" id="stay_drawer_body"></div></aside></div>
  <div id="stay_save_result" hidden></div>`;
  const dom = new JSDOM(html, { url: 'https://erp.example.test/stay/1/?month=2026-07&view=coord&offer=9#stay_tab_calendar', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window, doc = w.document;
  const drawer = doc.querySelector('.stay-drawer'), body = doc.getElementById('stay_drawer_body');
  const log = { reached: [], posts: [], submits: 0 };
  const render = (fragment) => { body.innerHTML = fragment; drawer.classList.add('is-open'); };
  const closeDrawer = () => { drawer.classList.remove('is-open'); body.innerHTML = ''; };
  const slot = () => doc.getElementById('stay_cell_slot');
  const fire = (name, detail) => doc.dispatchEvent(new w.CustomEvent(name, { detail, bubbles: true }));
  const nameOf = (b) => {
    for (const a of ['data-calendar-bulk-action', 'data-calendar-adjust-action', 'data-stay-action', 'data-stay-tab']) if (b.hasAttribute(a)) return `${a.replace(/^data-/, '')}=${b.getAttribute(a)}`;
    return `${b.localName}${b.name ? '[name=' + b.name + ']' : ''}`;
  };
  doc.addEventListener('submit', (e) => { log.submits++; e.preventDefault(); });
  doc.addEventListener('click', (e) => {
    const b = e.target.closest('button, a, input, label');
    if (!b) return;
    log.reached.push(nameOf(b));
    if (b.matches('#stay_calendar .erp_cont_head_right > [data-stay-action="goto"]:not(.stay-view-btn):not(.stay-promo-btn)')) {
      doc.getElementById('stay_calendar').outerHTML = panelOf('coord', /[?&]month=(\d{4}-\d{2})/.exec(b.getAttribute('hx-get'))[1]);
    } else if (b.matches('ul.tab-container a')) {
      doc.querySelectorAll('ul.tab-container a').forEach((a) => a.classList.toggle('active', a === b));
    } else if (b.matches('.stay-view-btn') && /view=coord/.test(b.getAttribute('hx-get') || '')) {
      doc.getElementById('stay_calendar').outerHTML = panelOf('coord');
    } else if (b.matches('[data-stay-entity="rate_plan"], [data-stay-entity="offer"]')) {
      const kind = b.getAttribute('data-stay-entity');
      doc.querySelectorAll(`[data-stay-entity="${kind}"]`).forEach((x) => { x.className = x.className.replace('--primary', '--ghost'); });
      b.className = b.className.replace('--ghost', '--primary');
    } else if (b.matches('[data-calendar-bulk-action="price"]')) {
      render(runFixture('calendar-bulk--price-step1.html'));
    } else if (b.matches('[data-calendar-bulk-action]')) {
      render(runFixture('calendar-bulk--close-step1.html'));
    } else if (b.matches('[data-calendar-adjust-action="open"]')) {
      render(runFixture('calendar-adjust--step1.html'));
    } else if (b.closest('[data-stay-screen="calendar-bulk"]') && b.matches('[data-stay-action="next"]')) {
      render(echoHidden(o.bulkReview, formValues(body, ['date_selection_0'])));
    } else if (b.closest('[data-stay-screen="calendar-bulk"]') && b.matches('[data-stay-action="save"]')) {
      const root = b.closest('[data-stay-screen="calendar-bulk"]');
      const post = { screen: 'calendar-bulk' };
      root.querySelectorAll('input, select').forEach((i) => { if (i.name && !i.name.endsWith('_pick') && i.value !== '' && i.name !== 'weekdays') post[i.name] = i.value; });
      log.posts.push(post);
      fire('htmx:before:request', {});
      if (o.onBulkSave === '403') {
        fire('htmx:response:error', { ctx: { response: { status: 403 } } });
        fire('htmx:finally:request', {});
        return;
      }
      closeDrawer();
      const mark = doc.getElementById('stay_save_result');
      mark.setAttribute('data-stay-result', 'saved'); mark.setAttribute('data-stay-saved-at', String(Date.now()) + log.posts.length);
      fire('htmx:after:swap', {}); fire('htmx:after:settle', {}); fire('htmx:finally:request', {});
    } else if (b.closest('[data-stay-screen="calendar-adjust"]') && b.matches('[data-stay-action="next"]')) {
      const picked = formValues(body, ['rooms', 'plans', 'occupancy', 'offer', 'los', 'adjust', 'date_selection_0']);
      const offerName = [...body.querySelector('select[name="offer"]').options].find((x) => x.selected).textContent.trim();
      render(echoHidden(o.adjustReview, picked, offerName));
    } else if (b.closest('[data-stay-screen]') && b.matches('[data-stay-action="save"]')) {
      log.posts.push({ screen: b.closest('[data-stay-screen]').getAttribute('data-stay-screen') });
    } else if (b.matches('[data-stay-action="open_cell"]')) {
      slot().innerHTML = cellWindow(o.cell);
    } else if (b.matches('[data-stay-action="save_cell"]')) {
      const tr = b.closest('tr[data-stay-row]');
      const post = { screen: 'price-cell', row: tr.getAttribute('data-stay-row') };
      tr.querySelectorAll('input, select').forEach((i) => { post[i.name] = i.value; });
      log.posts.push(post);
      const rows = [...doc.querySelectorAll('#stay_cell_edit [data-stay-card="main"] tr[data-stay-row]')].map((r) => ({
        pk: r.getAttribute('data-stay-row'), key: r.querySelector('[name="occupancy_key"]').value, label: r.querySelector('td').textContent.trim(),
        los: r.querySelector('[name="los_nights"]').value, price: r.querySelector('[name="price"]').value,
        list: r.querySelector('[name="original_price"]').value, net: r.querySelector('[name="net_amount"]').value
      }));
      const saved = o.cellSave === 'ok';
      const fresh = saved ? rows : (o.cell.rows || ROWS);
      doc.getElementById('stay_cell_edit').outerHTML = cellWindow(Object.assign({}, o.cell, { rows: fresh, notice: saved ? '저장했습니다' : '', error: saved ? '' : '정가는 판매가보다 작을 수 없습니다' }));
    } else if (b.matches('#stay_cell_edit [data-stay-action="close"]')) {
      slot().innerHTML = '';
    }
  });
  // 연동 방식 셀렉트를 바꾸면 ERP 가 ② 를 다시 그린다(hx-trigger="change") — 「직접 입력」 캡처로 갈아 끼운다
  doc.addEventListener('change', (e) => {
    if (e.target.name !== 'link_mode_pick' || e.target.value !== 'manual') return;
    log.reached.push('change:link_mode_pick');
    render(echoHidden(o.bulkReviewManual || runFixture('calendar-bulk--price-link-manual.html'), formValues(body, ['date_selection_0'])));
  });
  w.addEventListener('stay-drawer-close', closeDrawer);
  w.localStorage.setItem('staySteps', RUNNER_STEPS);
  w.localStorage.setItem('stayRunCursor', RUNNER_CURSOR);
  if (o.withScripts) { w.eval(HELPER); w.eval(BOOT); }
  w.eval(PAGE);
  return { dom, w, doc, log, render, closeDrawer, drawerOpen: () => drawer.classList.contains('is-open') };
}

// 페이지 안에서 만든 값으로 바꿔 넘긴다(다른 realm 의 객체는 scrub 이 평범한 객체로 보지 않을 수 있다)
export const inPage = (w, value) => w.JSON.parse(JSON.stringify(value));
export const plain = (value) => JSON.parse(JSON.stringify(value));
