// 페이지 쪽 시험의 받침 — jsdom 위에 ERP Stay 화면을 세우고 러너의 도우미·부트와 `stay_price.js` 를 그대로 올린다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
//
// 화면은 캡처한 ERP 마크업이다: 가격 캘린더(`panel--calendar--1/2.html`), 가격 수정 ①·②, 가감 ①·②
// (`stay-setup-run/tests/fixtures/erp/`), 가격 수정 ②·가감 ② 의 손 조각(`tests/fixtures/erp/`). 셀 창은 캡처가 없어
// ERP 템플릿 `_calendar_cell_edit.html` 의 표식을 따라 손으로 그린다(`cellWindow`). htmx 대신 문서에 붙인 클릭 듣개가
// 서버처럼 조각을 갈아 끼운다 — 벽(window 캡처 단계)이 막은 클릭은 여기 닿지 않으므로 `log.reached` 가 증거다.
// htmx 4 처럼 htmx 단추(`hx-get` 등)는 연결돼야(`data-htmx-powered`) 눌린다. 연결 전에 누르면 아무 일도 없고 `log.dead` 에 남는다.
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
export const LOADER = readFileSync(join(SKILL, 'scripts', 'page', 'stay_price_loader.js'), 'utf8');
export const runFixture = (name) => readFileSync(join(RUNNER, 'tests', 'fixtures', 'erp', name), 'utf8');
export const ownFixture = (name) => readFileSync(join(SKILL, 'tests', 'fixtures', 'erp', name), 'utf8');
export const OWN_FIXTURES = join(SKILL, 'tests', 'fixtures', 'erp');

export const OFFER = '〈오퍼 관리용 이름〉';
// htmx 가 맡는 단추 — htmx 4 는 이것들에 듣개를 붙이며 `data-htmx-powered` 를 단다(htmx.org 4.0.0-beta6 `#initializeElement`)
const HTMX = ['action', 'get', 'post', 'put', 'patch', 'delete'].map((v) => `[hx-${v}],[data-hx-${v}]`).join(',');
const wire = (root) => { if (root) [root, ...root.querySelectorAll(HTMX)].filter((el) => el.matches(HTMX)).forEach((el) => el.setAttribute('data-htmx-powered', 'true')); };
// 시험 호텔 — 지어낸 번호와 이름. 페이지는 `#master_id` 와 [에이전트에 복사] 문구로 이 호텔을 알아본다
export const HOTEL = Object.freeze({ id: '1', name: '데모 호텔' });

// 편집 화면이 호텔을 스스로 말하는 두 곳 — fit 기본정보의 숨은 칸(`fit/master_form.html`)과 [에이전트에 복사] 모달의 붙여 넣기
// 문구(`stay/_agent_resume_modal.html`, 자동화 약속 이름 그대로)
export function hotelMarks({ id = HOTEL.id, name = HOTEL.name, said = id } = {}) {
  return `<input type="hidden" id="master_id" value="${id}">
  <input type="text" id="id_title" name="title" value="${name}">
  <div class="stay-root" data-stay-screen="agent-resume"><div id="stay_agent_resume" class="stay-modal stay-modal--page stay-agent-modal" hidden>
    <textarea class="stay-agent__text" data-agent-text="resume" readonly>
/stay-setup:stay-setup-run Chrome 에 열려 있는 ERP 호텔 ${said} (${name}) 편집 화면에, 산출물 폴더의 입력 지시서를 이어서 깔아줘.</textarea>
    <textarea class="stay-agent__text" data-agent-text="verify" readonly>
/stay-setup:stay-setup-run Chrome 에 열려 있는 ERP 호텔 ${said} (${name}) 편집 화면을 입력 지시서와 대조해서 다른 값·빠진 단계만 표로 알려줘. 아무것도 고치지 마.</textarea>
  </div></div>`;
}
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

// 저장 단계가 싣는 읽은 값(`was`, 명령 `step_calls`) — 받침의 화면과 같은 값. 가격 수정 ② 캡처(price-step2)의 인원 무관 1박 줄은
// 날마다 판매가 120000.00 · 정가 · 공급 원가 없음이고(받은 날짜대로 다시 그려도 같다), 셀 창의 줄은 ROWS 의 그 줄이다
export const bulkWas = (dates, sell = '120000.00') => [[dates[0], dates[dates.length - 1], sell, null, null]];
export const noCell = (dates) => [[dates[0], dates[dates.length - 1], null, null, null]];
export const cellWas = (occupancy = '') => { const r = ROWS.find((x) => x.key === occupancy); return r ? [r.price, r.list || null, r.net || null] : [null, null, null]; };

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
// 가격 수정 ② 의 상태 표와 기존 값 줄을 받은 날짜 구간대로 다시 그린다(캡처 price-step2 의 7/1 줄을 구간마다 되풀이) — 서버와 같이
function echoDays(html, ranges) {
  const label = (line) => {
    const [a, b] = line.split(' ~ ');
    if (!b) return a;
    const n = Math.round((Date.parse(b) - Date.parse(a)) / 86400000) + 1;
    return `${a} ~ ${b} (${n}일)`;
  };
  const lines = String(ranges || '').split('\n').map((x) => x.trim()).filter(Boolean).map(label);
  return html
    .replace('<tbody><tr><td>2026-07-01</td><td>가격 판매 가능</td></tr></tbody>', `<tbody>${lines.map((d) => `<tr><td>${d}</td><td>가격 판매 가능</td></tr>`).join('')}</tbody>`)
    .replace('<tr data-stay-existing><td>2026-07-01</td><td class="stay-numeric">120000.00</td><td class="stay-numeric">없음</td><td class="stay-numeric">없음</td></tr>',
      lines.map((d) => `<tr data-stay-existing><td>${d}</td><td class="stay-numeric">120000.00</td><td class="stay-numeric">없음</td><td class="stay-numeric">없음</td></tr>`).join(''));
}
// 가격 수정 ② 를 받은 날마다 한 줄씩 — 날마다 값이 다를 수 있다(bulkValues). 값이 없는 날은 「가격 없음」
function dayRows(html, ranges, values) {
  const days = [];
  String(ranges || '').split('\n').map((x) => x.trim()).filter(Boolean).forEach((line) => {
    const [a, b] = line.split(' ~ ');
    for (let d = Date.parse(`${a}T00:00:00Z`); d <= Date.parse(`${b || a}T00:00:00Z`); d += 86400000) days.push(new Date(d).toISOString().slice(0, 10));
  });
  const cell = (day) => (values[day] ? `<td class="stay-numeric">${values[day]}</td><td class="stay-numeric">없음</td><td class="stay-numeric">없음</td>` : '<td class="stay-numeric">가격 없음</td><td></td><td></td>');
  return html
    .replace('<tbody><tr><td>2026-07-01</td><td>가격 판매 가능</td></tr></tbody>', `<tbody>${days.map((d) => `<tr><td>${d}</td><td>${values[d] ? '가격 판매 가능' : '가격 없음'}</td></tr>`).join('')}</tbody>`)
    .replace('<tr data-stay-existing><td>2026-07-01</td><td class="stay-numeric">120000.00</td><td class="stay-numeric">없음</td><td class="stay-numeric">없음</td></tr>',
      days.map((d) => `<tr data-stay-existing><td>${d}</td>${cell(d)}</tr>`).join(''));
}
const formValues = (root, names) => Object.fromEntries(names.map((name) => [name, [...root.querySelectorAll(`[name="${name}"]`)]
  .filter((el) => !(el.type === 'checkbox' || el.type === 'radio') || el.checked).map((el) => el.value)]));

/**
 * ERP 한 장. `opts`:
 *   start        'coord'(기본, 룸별 입력 · 2026-07) | 'overview'(전체 보기 — [룸별 입력] 을 눌러야 칩이 선다)
 *   tab          'offers' 면 오퍼 탭이 켜진 채로 연다(가격 캘린더 탭을 눌러야 한다)
 *   bulkReview   가격 수정 ② 조각(기본: 캡처 price-step2)       bulkReviewManual  연동 방식을 「직접 입력」으로 바꾼 ②
 *   adjustReview 가감 ② 조각(기본: 손 조각 adjust-rejected)
 *   onBulkSave   'saved'(기본: 드로어 닫고 저장 표지) | '403'(CSRF 거절 — 드로어가 남는다) | 'hang'(요청이 끝나지 않는다) |
 *                'esc'(요청이 도는 사이 사람이 Esc — 드로어가 닫히고, 요청은 저장 표지 없이 끝난다) | 'escLate'(Esc 로 닫힌 뒤
 *                200ms 에 저장 표지가 온다) | 'reload'(요청이 도는 사이 페이지가 떠난다 — pagehide, 요청은 끝나지 않는다)
 *   drawerStuck  true 면 드로어가 닫혀도 내용이 비지 않는다(쉬는 화면이 오지 않는다)
 *   cell         셀 창 그리기 값 {date, plan, rows} · cellSave 'ok'|'error'
 *   echoDays     true 면 가격 수정 ② 의 상태 표·기존 값 줄을 받은 날짜 구간대로 다시 그린다
 *   bulkValues   {날짜: 판매가} — 주면 가격 수정 ② 의 인원 무관 1박 줄을 받은 날마다 그 값으로 그리고(없는 날은 가격 없음), 저장하면
 *                그 날들의 값을 보낸 판매가로 바꾼다(서버처럼). 시험 중에 `page.opts.bulkValues` 를 고치면 다른 사람이 저장한 것이다
 *   panelEdit · adjustSelectEdit  캘린더 판 · 가감 ① 조각을 바꾸는 함수(객실 이름 변형 등)
 *   withScripts  false 면 도우미·부트 없이 `stay_price.js` 만 올린다 · bare 면 아무것도 올리지 않는다(올리개 시험)
 *   lateWire     {ms, on, untracked} — `on` 의 조각('calendar' 칩·오퍼·보기·달·셀 창 닫기 | 'drawer' 드로어 ① | 'step' 드로어 ② ·
 *                「직접 입력」 다시 그리기 · 가감 ② | 'cell' 셀 창 열기·저장 뒤)을 끼운 뒤 ms 지나서 연결한다(실측: 달력은 3~4ms 늦다).
 *                요청은 htmx 4 처럼 연결 뒤에 끝난다. untracked 면 요청이 끼우자마자 끝난다 — 요청 수로는 그 틈이 안 보인다
 *   hotel        호텔 표식 `hotelMarks` 의 값({id, name, said}) · null 이면 표식이 없다 · login true 면 로그인 화면(비밀번호 칸만)
 *   ratePlans    요금제 탭 목록(`_rate_plans_panel.html` 의 표식 — 편집 화면이 열릴 때 함께 불러온다)의 줄 [{id, room, plan}]. 주지 않으면 없다
 */
export function erpPage(opts = {}) {
  const o = Object.assign({ start: 'coord', bulkReview: runFixture('calendar-bulk--price-step2.html'), adjustReview: ownFixture('adjust-rejected.html'),
    cell: {}, cellSave: 'ok', withScripts: true }, opts);
  // 캡처한 7월 판을 다른 달로 — 달 머리·칸 날짜·[이전 달]/[다음 달] 의 달을 옮긴다
  const shift = (month, by) => { const d = new Date(month + '-01T00:00:00Z'); d.setUTCMonth(d.getUTCMonth() + by); return d.toISOString().slice(0, 7); };
  const edit = o.panelEdit || ((html) => html);
  const panelOf = (start, month = '2026-07') => edit(start === 'overview' ? runFixture('panel--calendar--1.html')
    : runFixture('panel--calendar--2.html').replaceAll('2026-06', '@prev').replaceAll('2026-08', '@next').replaceAll('2026-07', month)
      .replaceAll('@prev', shift(month, -1)).replaceAll('@next', shift(month, 1)));
  const marks = o.hotel === null ? '' : hotelMarks(o.hotel || {});
  const attr = (v) => String(v).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
  const plans = o.ratePlans ? `<div id="stay_tab_rate_plans" class="stay-pane" data-stay-tab="rate_plans" style="display:none"><div id="stay_rate_plans" data-stay-panel="rate_plans"><table>
    ${o.ratePlans.map((r) => `<tbody data-workspace-item data-workspace-room-name="${attr(r.room)}"><tr data-stay-entity="rate_plan" data-stay-name="${attr(r.plan)}" data-stay-entity-id="${attr(r.id)}"><td>${r.room}</td><td>${r.plan}</td></tr></tbody>`).join('')}
  </table></div></div>` : '';
  const html = o.login ? `<form method="post" action="/accounts/login/"><input type="text" name="username"><input type="password" name="password"><button type="submit">로그인</button></form>`
    : `${marks}<ul class="tab_style1 tab-container">
    <li class="tab"><a href="#stay_tab_offers" data-stay-tab="offers"${o.tab === 'offers' ? ' class="active"' : ''}><span>오퍼</span></a></li>
    <li class="tab"><a href="#stay_tab_sale_days" data-stay-tab="sale_days"><span>판매일</span></a></li>
    <li class="tab"><a href="#stay_tab_calendar" data-stay-tab="calendar"${o.tab === 'offers' ? '' : ' class="active"'}><span>가격 캘린더</span></a></li>
  </ul>${OTHER_TABS}${plans}
  <div id="stay_tab_calendar" class="col s12 stay-pane stay-root" data-stay-tab="calendar">${panelOf(o.start)}</div>
  <div class="stay-drawer"><aside class="stay-drawer__panel" role="dialog"><header class="stay-drawer__header"><h4 class="stay-drawer__title"></h4>
    <button type="button" class="stay-drawer__close" aria-label="닫기">&times;</button></header>
    <div class="stay-drawer__context" id="stay_drawer_context"></div><div class="stay-drawer__body" id="stay_drawer_body"></div></aside></div>
  <div id="stay_save_result" hidden></div>`;
  const dom = new JSDOM(html, { url: 'https://erp.example.test/stay/1/?month=2026-07&view=coord&offer=9#stay_tab_calendar', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window, doc = w.document;
  wire(doc.body);   // 처음 그린 화면은 htmx 가 이미 연결했다
  const drawer = doc.querySelector('.stay-drawer'), body = doc.getElementById('stay_drawer_body');
  const log = { reached: [], posts: [], submits: 0, dead: [] };
  const put = (fragment) => { body.innerHTML = fragment; drawer.classList.add('is-open'); return body; };
  const render = (fragment) => wire(put(fragment));
  // ERP 드로어처럼 닫는다 — `is-open` 은 바로 빠지고 내용은 0.35초 뒤에 비운다(`_drawer.html` hide()). drawerStuck 이면 안 비운다
  const closeDrawer = () => {
    drawer.classList.remove('is-open');
    const stale = body.firstElementChild;
    if (!stale || o.drawerStuck) return;
    w.setTimeout(() => { if (!drawer.classList.contains('is-open') && body.firstElementChild === stale) body.replaceChildren(); }, 350);
  };
  const slot = () => doc.getElementById('stay_cell_slot');
  const fire = (name, detail) => doc.dispatchEvent(new w.CustomEvent(name, { detail, bubbles: true }));
  // 서버 요청 하나 — htmx 4 의 차례: 요청 시작 → 조각 끼우기(apply, 끼운 뿌리를 돌려준다) → 정착 → 연결 → 요청 끝
  const late = Object.assign({ ms: 0, on: [], untracked: false }, o.lateWire);
  const swap = (name, apply) => {
    fire('htmx:before:request', {});
    const root = apply();
    const settle = () => { fire('htmx:after:settle', {}); wire(root); fire('htmx:after:swap', {}); };
    if (!late.ms || !late.on.includes(name)) { settle(); fire('htmx:finally:request', {}); return; }
    if (late.untracked) fire('htmx:finally:request', {});
    w.setTimeout(() => { settle(); if (!late.untracked) fire('htmx:finally:request', {}); }, late.ms);
  };
  // 달력 조각 — 서버가 그리듯 고른 칩(객실·요금제, 오퍼)을 칠해 그린다
  const picks = {};
  const shownMonth = () => doc.getElementById('stay_calendar').getAttribute('data-cal-month');
  const drawCalendar = (start, month) => {
    doc.getElementById('stay_calendar').outerHTML = panelOf(start, month);
    const cal = doc.getElementById('stay_calendar');
    Object.entries(picks).forEach(([kind, name]) => cal.querySelectorAll(`[data-stay-entity="${kind}"]`).forEach((x) => {
      x.className = x.className.replace(/stay-btn--(primary|ghost)/, x.getAttribute('data-stay-name') === name ? 'stay-btn--primary' : 'stay-btn--ghost');
    }));
    return cal;
  };
  const nameOf = (b) => {
    for (const a of ['data-calendar-bulk-action', 'data-calendar-adjust-action', 'data-stay-action', 'data-stay-tab']) if (b.hasAttribute(a)) return `${a.replace(/^data-/, '')}=${b.getAttribute(a)}`;
    return `${b.localName}${b.name ? '[name=' + b.name + ']' : ''}`;
  };
  doc.addEventListener('submit', (e) => { log.submits++; e.preventDefault(); });
  doc.addEventListener('click', (e) => {
    const b = e.target.closest('button, a, input, label');
    if (!b) return;
    log.reached.push(nameOf(b));
    if (b.matches(HTMX) && !b.hasAttribute('data-htmx-powered')) { log.dead.push(nameOf(b)); return; }   // htmx 가 아직 듣지 않는다
    if (b.matches('#stay_calendar .erp_cont_head_right > [data-stay-action="goto"]:not(.stay-view-btn):not(.stay-promo-btn)')) {
      swap('calendar', () => drawCalendar('coord', /[?&]month=(\d{4}-\d{2})/.exec(b.getAttribute('hx-get'))[1]));
    } else if (b.matches('ul.tab-container a')) {
      doc.querySelectorAll('ul.tab-container a').forEach((a) => a.classList.toggle('active', a === b));
    } else if (b.matches('.stay-view-btn') && /view=coord/.test(b.getAttribute('hx-get') || '')) {
      swap('calendar', () => drawCalendar('coord'));
    } else if (b.matches('[data-stay-entity="rate_plan"], [data-stay-entity="offer"]')) {
      picks[b.getAttribute('data-stay-entity')] = b.getAttribute('data-stay-name');
      swap('calendar', () => drawCalendar('coord', shownMonth()));
    } else if (b.matches('[data-calendar-bulk-action="price"]')) {
      swap('drawer', () => put(runFixture('calendar-bulk--price-step1.html')));
    } else if (b.matches('[data-calendar-bulk-action]')) {
      swap('drawer', () => put(runFixture('calendar-bulk--close-step1.html')));
    } else if (b.matches('[data-calendar-adjust-action="open"]')) {
      swap('drawer', () => put((o.adjustSelectEdit || ((html) => html))(runFixture('calendar-adjust--step1.html'))));
    } else if (b.closest('[data-stay-screen="calendar-bulk"]') && b.matches('[data-stay-action="next"]')) {
      const sent = formValues(body, ['date_selection_0']);
      const review = o.bulkValues ? dayRows(o.bulkReview, sent.date_selection_0[0], o.bulkValues) : o.echoDays ? echoDays(o.bulkReview, sent.date_selection_0[0]) : o.bulkReview;
      swap('step', () => put(echoHidden(review, sent)));
    } else if (b.closest('[data-stay-screen="calendar-bulk"]') && b.matches('[data-stay-action="save"]')) {
      const root = b.closest('[data-stay-screen="calendar-bulk"]');
      const post = { screen: 'calendar-bulk' };
      root.querySelectorAll('input, select').forEach((i) => { if (i.name && !i.name.endsWith('_pick') && i.value !== '' && i.name !== 'weekdays') post[i.name] = i.value; });
      log.posts.push(post);
      fire('htmx:before:request', {});
      if (o.onBulkSave === 'hang') return;   // 요청이 끝나지 않는다(서버가 답하지 않음)
      if (o.onBulkSave === 'reload') { w.dispatchEvent(new w.Event('pagehide')); return; }
      if (o.onBulkSave === 'esc' || o.onBulkSave === 'escLate') {
        closeDrawer();   // ERP 의 `@keydown.escape.window` 처럼 — 클릭이 아니라 벽을 지나지 않는다
        w.setTimeout(() => {
          if (o.onBulkSave === 'escLate') { const m = doc.getElementById('stay_save_result'); m.setAttribute('data-stay-result', 'saved'); m.setAttribute('data-stay-saved-at', String(Date.now())); }
          fire('htmx:finally:request', {});
        }, o.onBulkSave === 'escLate' ? 200 : 30);
        return;
      }
      if (o.onBulkSave === '403') {
        fire('htmx:response:error', { ctx: { response: { status: 403 } } });
        fire('htmx:finally:request', {});
        return;
      }
      closeDrawer();
      if (o.bulkValues && post['prices-0-price']) {
        String(post.date_selection_0 || '').split('\n').map((x) => x.trim()).filter(Boolean).forEach((line) => {
          const [a, b] = line.split(' ~ ');
          for (let d = Date.parse(`${a}T00:00:00Z`); d <= Date.parse(`${b || a}T00:00:00Z`); d += 86400000) o.bulkValues[new Date(d).toISOString().slice(0, 10)] = post['prices-0-price'];
        });
      }
      const mark = doc.getElementById('stay_save_result');
      mark.setAttribute('data-stay-result', 'saved'); mark.setAttribute('data-stay-saved-at', String(Date.now()) + log.posts.length);
      fire('htmx:after:swap', {}); fire('htmx:after:settle', {}); fire('htmx:finally:request', {});
    } else if (b.closest('[data-stay-screen="calendar-adjust"]') && b.matches('[data-stay-action="next"]')) {
      const picked = formValues(body, ['rooms', 'plans', 'occupancy', 'offer', 'los', 'adjust', 'date_selection_0']);
      const offerName = [...body.querySelector('select[name="offer"]').options].find((x) => x.selected).textContent.trim();
      swap('step', () => put(echoHidden(o.adjustReview, picked, offerName)));
    } else if (b.closest('[data-stay-screen]') && b.matches('[data-stay-action="save"]')) {
      log.posts.push({ screen: b.closest('[data-stay-screen]').getAttribute('data-stay-screen') });
    } else if (b.matches('[data-stay-action="open_cell"]')) {
      swap('cell', () => { slot().innerHTML = cellWindow(o.cell); return slot(); });
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
      swap('cell', () => {
        doc.getElementById('stay_cell_edit').outerHTML = cellWindow(Object.assign({}, o.cell, { rows: fresh, notice: saved ? '저장했습니다' : '', error: saved ? '' : '정가는 판매가보다 작을 수 없습니다' }));
        return doc.getElementById('stay_cell_edit');
      });
    } else if (b.matches('#stay_cell_edit [data-stay-action="close"]')) {
      swap('calendar', () => drawCalendar('coord', shownMonth()));   // ERP 의 [닫기] 는 달력을 다시 가져온다(셀 창 자리는 달력 안)
    }
  });
  // 연동 방식 셀렉트를 바꾸면 ERP 가 ② 를 다시 그린다(hx-trigger="change") — 「직접 입력」 캡처로 갈아 끼운다
  doc.addEventListener('change', (e) => {
    if (e.target.name !== 'link_mode_pick' || e.target.value !== 'manual') return;
    log.reached.push('change:link_mode_pick');
    if (!e.target.hasAttribute('data-htmx-powered')) { log.dead.push('change:link_mode_pick'); return; }
    const sent = formValues(body, ['date_selection_0']);
    swap('step', () => put(echoHidden(o.bulkReviewManual || runFixture('calendar-bulk--price-link-manual.html'), sent)));
  });
  w.addEventListener('stay-drawer-close', closeDrawer);
  w.localStorage.setItem('staySteps', RUNNER_STEPS);
  w.localStorage.setItem('stayRunCursor', RUNNER_CURSOR);
  if (o.withScripts && !o.bare) { w.eval(HELPER); w.eval(BOOT); }
  if (!o.bare) w.eval(PAGE);
  return { dom, w, doc, log, render, closeDrawer, opts: o, drawerOpen: () => drawer.classList.contains('is-open') };
}

// 페이지 안에서 만든 값으로 바꿔 넘긴다(다른 realm 의 객체는 scrub 이 평범한 객체로 보지 않을 수 있다)
export const inPage = (w, value) => w.JSON.parse(JSON.stringify(value));
export const plain = (value) => JSON.parse(JSON.stringify(value));

// B9 · B16 — 답과 쪽은 도구가 보이는 모양(JSON 글자)으로 800자 안이다. 읽기 답의 조각은 take 로 자리(at)를 따라 받는다
export const charsOf = (value) => JSON.stringify(value).length;
// 페이지가 둔 조각의 모양(따옴표 없는 JSON)을 푼다 — 파이썬 `change_core.answers.unpack` 과 같은 셈. 큰따옴표 · 역슬래시가 있으면
// 페이지가 둔 모양이 아니다
export function unpack(text) {
  if (/["\\]/.test(text)) throw new Error('조각 글자에 큰따옴표나 역슬래시가 있습니다');
  const back = (s) => s.replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)));
  const walk = (v) => (typeof v === 'string' ? back(v) : Array.isArray(v) ? v.map(walk)
    : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, x]) => [back(k), walk(x)])) : v);
  return walk(JSON.parse(text.replace(/'/g, '"')));
}
export function takeAll(w, result, size) {
  const meta = result.body;
  const takes = [];
  for (let at = 0; at < meta.chars;) {
    const piece = plain(size === undefined ? w.stayPrice.take(meta.id, at) : w.stayPrice.take(meta.id, at, size));
    if (!piece.ok) throw new Error(piece.error);
    takes.push(piece);
    at = piece.next;
  }
  const text = takes.map((t) => t.text).join('');
  return { takes, text, body: unpack(text) };
}

// 사람이 누른 클릭 — jsdom 에서는 스크립트가 만든 사건이 늘 isTrusted=false 다. jsdom 안쪽 길로 사람의 클릭(isTrusted=true)을
// 흉내 낸다(시험 전용, jsdom 22 의 generated/utils.js). 브라우저에서는 사람이 누르면 이렇게 된다.
const jsdomUtils = require('jsdom/lib/jsdom/living/generated/utils.js');
export function personClick(w, el) {
  const event = new w.MouseEvent('click', { bubbles: true, cancelable: true, view: w });
  const impl = jsdomUtils.implForWrapper(event);
  impl.isTrusted = true;
  jsdomUtils.implForWrapper(el)._dispatch(impl);
  return event;
}
