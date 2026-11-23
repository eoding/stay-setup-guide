// 시즌 창 페이지 시험의 받침 — jsdom 위에 ERP Stay 편집 화면(탭 · 호텔 표식 · 시즌 탭 · 요금제 탭 · 객실 타입 탭 · 드로어)을 세우고,
// 러너의 도우미 · 부트, 가격 도우미 `stay_price.js`, 시즌 창 모듈 `stay_price_season.js` 를 그대로 올린다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
//
// 화면은 러너가 ERP 에서 맞춰 둔 캡처다(`stay-setup-run/tests/fixtures/erp/` — season-price-fill · season-price-fill--last-fill ·
// panel--seasons · panel--rate_plans · panel--room_types--1). 캡처의 자리 표시(`{room:1}` …)는 지어낸 번호로 바꾼다. 저장 뒤의 시즌
// 목록(저장 띠)과 거절한 창은 캡처가 없어 ERP 템플릿(`_seasons_panel.html` 의 filled 띠 · `_season_fill_form.html` 의 error_message
// 띠)의 표식을 따라 손으로 그린다 — 진짜 화면에서 먼저 확인할 것이다. 가짜 서버는 문서에 붙인 클릭 듣개다 — 벽(window 캡처 단계)이
// 막은 클릭은 여기 닿지 않으므로 `log.reached` 가 증거다. 저장 단추를 받으면 그 단추의 `hx-include` 고르개로 보낼 칸을 모은다.
import { readFileSync } from 'node:fs';
import { loadJsdom, HELPER, BOOT, PAGE, HOTEL, hotelMarks, inPage, plain, runFixture, SKILL, personClick } from './page_harness.mjs';
import { join } from 'node:path';

export { HELPER, BOOT, PAGE, HOTEL, inPage, plain, personClick };
const JSDOM = loadJsdom();
export const SEASON = readFileSync(join(SKILL, 'scripts', 'page', 'stay_price_season.js'), 'utf8');

export const OFFER = '〈오퍼 관리용 이름〉';
export const IDS = { master: '1', season: '8801', offer: '11', room: { 1: '301', 2: '302' }, plan: { 1: '9001', 2: '9002', 3: '9003', 4: '9004', 5: '9005' } };
// 캡처의 자리 표시 → 지어낸 번호
export function filled(html) {
  return html.replaceAll('{master:1}', IDS.master).replaceAll('{season:1}', IDS.season).replaceAll('{offer:1}', IDS.offer)
    .replace(/\{room:(\d)\}/g, (_, n) => IDS.room[n]).replace(/\{rate_plan:(\d)\}/g, (_, n) => IDS.plan[n])
    .replace(/\{room_type:(\d)\}/g, (_, n) => `7${n}`).replaceAll('{color}', '999999');
}
export const WINDOW = filled(runFixture('season-price-fill.html'));
export const LAST_FILL = filled(runFixture('season-price-fill--last-fill.html'));
const SEASONS = filled(runFixture('panel--seasons.html'));
const RATE_PLANS = filled(runFixture('panel--rate_plans.html'));
const ROOM_TYPES = filled(runFixture('panel--room_types--1.html'));

const HTMX = ['action', 'get', 'post', 'put', 'patch', 'delete'].map((v) => `[hx-${v}],[data-hx-${v}]`).join(',');
const wire = (root) => { if (root) [root, ...root.querySelectorAll(HTMX)].filter((el) => el.matches(HTMX)).forEach((el) => el.setAttribute('data-htmx-powered', 'true')); };

const TABS = [['#stay_tab_offers', 'offers', '오퍼'], ['#stay_tab_room_types', 'room_types', '객실 타입'], ['#stay_tab_seasons', 'seasons', '시즌'],
  ['#stay_tab_rate_plans', 'rate_plans', '요금제'], ['#stay_tab_calendar', 'calendar', '가격 캘린더']];

// 시즌 날을 바꾼 창 — 창의 data-date-allowed · [기간 · 직접 입력] 칸(시즌 날을 이어진 날끼리)
export function withDates(html, days) {
  const runs = [];
  days.forEach((day) => {
    const last = runs[runs.length - 1];
    if (last && Date.parse(`${day}T00:00:00Z`) - Date.parse(`${last[1]}T00:00:00Z`) === 86400000) last[1] = day; else runs.push([day, day]);
  });
  const text = runs.map(([a, b]) => (a === b ? a : `${a} ~ ${b}`)).join('\n');
  return html.replaceAll('data-date-allowed="2026-07-01"', `data-date-allowed="${days.join(',')}"`)
    .replaceAll('allowed_dates="2026-07-01"', `allowed_dates="${days.join(',')}"`)
    .replace(/(<textarea name="date_selection_0"[^>]*>)\n2026-07-01<\/textarea>/, `$1\n${text}</textarea>`);
}
// 소아 칸을 「성인 요금의 %」 구간의 읽기 전용 글로 — `_build_child_extra_fields` 의 그 가지
export function childPercent(html, pct = '50') {
  return html.replace(/<input type="text" name="child_extra_CHILD"[^>]*>/,
    `<input type="text" name="child_extra_CHILD" value="성인 1인 추가분의 ${pct}% 로 계산됨" readonly disabled data-stay-field="child_extra_CHILD" id="id_stay_child_extra_CHILD">`);
}

/**
 * ERP 한 장. `opts`:
 *   tab        처음 켜진 탭(기본 'calendar' — [시즌] 탭을 눌러야 목록이 보인다)
 *   window     [가격 입력] 이 여는 창(기본 WINDOW — 기억 없음) · LAST_FILL 이면 마지막 입력값을 채워 연 창
 *   windowEdit 열 때마다 창 HTML 을 바꾸는 함수(시즌 날 · 아동 칸 · 다른 사람이 친 값)
 *   onSave     'saved'(기본: 드로어를 닫고 시즌 목록을 저장 띠와 함께 다시 그리고 저장 표지를 바꾼다) | 'refused'(창을 오류와 함께 다시
 *              그린다) | 'hang'(요청이 끝나지 않는다) | 'slow'(slowMs 뒤에 저장) | 'nosupply'(저장 + 공급 통화 없음 띠)
 *   banner     저장 띠 글(기본 「가격을 넣었습니다 — 새로 1칸 · 덮어쓴 0칸 (룸 1개 × 1일).」)
 *   onType     'clearNet' 면 인원 조합별 조정 칸에 글자를 치면 화면 스크립트가 공급 원가 칸을 비운다(친 뒤 확인이 잡을 것)
 */
export function seasonPage(opts = {}) {
  const o = Object.assign({ tab: 'calendar', window: WINDOW, onSave: 'saved', slowMs: 200,
    banner: '가격을 넣었습니다 — 새로 1칸 · 덮어쓴 0칸 (룸 1개 × 1일).' }, opts);
  const tabs = TABS.map(([href, name, label]) => `<li class="tab"><a href="${href}" data-stay-tab="${name}"${name === o.tab ? ' class="active"' : ''}><span>${label}</span></a></li>`).join('');
  const pane = (name, inner) => `<div id="stay_tab_${name}" class="col s12 stay-pane stay-root" data-stay-tab="${name}"${name === o.tab ? '' : ' style="display:none"'}>${inner}</div>`;
  const html = `${hotelMarks()}<ul class="tab_style1 tab-container">${tabs}</ul>
${pane('offers', '<button type="button" class="stay-btn stay-btn--danger" data-stay-action="delete" hx-post="/stay/1/offers/11/delete/">삭제</button>')}
${pane('room_types', ROOM_TYPES)}${pane('seasons', SEASONS)}${pane('rate_plans', RATE_PLANS)}${pane('calendar', '<div id="stay_calendar"></div>')}
<div class="stay-banner" data-stay-card="gate"><button type="button" class="stay-btn stay-btn--primary" data-stay-action="activate">판매 시작</button></div>
<div class="stay-drawer"><aside class="stay-drawer__panel" role="dialog"><header class="stay-drawer__header"><h4 class="stay-drawer__title"></h4>
  <button type="button" class="stay-drawer__close" aria-label="닫기">&times;</button></header>
  <div class="stay-drawer__context" id="stay_drawer_context"></div><div class="stay-drawer__body" id="stay_drawer_body"></div></aside></div>
<div id="stay_save_result" hidden></div>`;
  const dom = new JSDOM(html, { url: `https://erp.example.test/stay/${HOTEL.id}/#stay_tab_calendar`, runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window, doc = w.document;
  wire(doc.body);
  const drawer = doc.querySelector('.stay-drawer'), body = doc.getElementById('stay_drawer_body'), title = doc.querySelector('.stay-drawer__title');
  const log = { reached: [], posts: [], typed: [], dead: [] };
  let morphs = 0, saves = 0;
  const fire = (name, detail) => doc.dispatchEvent(new w.CustomEvent(name, { detail, bubbles: true }));
  const swap = (apply) => { fire('htmx:before:request', {}); const root = apply(); fire('htmx:after:swap', {}); fire('htmx:after:settle', {}); wire(root); fire('htmx:finally:request', {}); };
  const morph = (fragment) => fragment.replaceAll('stay_season_fill_form_00000000', `stay_season_fill_form_m${++morphs}`);
  const edit = (fragment) => (o.windowEdit ? o.windowEdit(fragment) : fragment);
  const open = (fragment) => { body.innerHTML = morph(edit(fragment)); title.textContent = `가격 일괄 입력 — ${OFFER} · PEAK`; drawer.classList.add('is-open'); return body; };
  const closeDrawer = () => {
    drawer.classList.remove('is-open'); title.textContent = '';
    const stale = body.firstElementChild;
    if (stale) w.setTimeout(() => { if (!drawer.classList.contains('is-open') && body.firstElementChild === stale) body.replaceChildren(); }, 350);
  };
  const collect = (save) => [...doc.querySelectorAll(save.getAttribute('hx-include'))].flatMap((el) => {
    if (!el.name || el.matches(':disabled')) return [];
    if (el.type === 'checkbox' || el.type === 'radio') return el.checked ? [[el.name, el.value]] : [];
    return [[el.name, el.value]];
  });
  const saved = (extra = '') => {
    saves++;
    const panel = doc.getElementById('stay_seasons');
    panel.outerHTML = SEASONS.replace('<div class="stay-panel-intro">',
      `<div class="stay-banner stay-banner--ok" data-stay-result="saved"><span>${o.banner}</span></div>${extra}<div class="stay-panel-intro">`);
    body.replaceChildren();
    const mark = doc.getElementById('stay_save_result');
    mark.setAttribute('data-stay-result', 'saved');
    mark.setAttribute('data-stay-saved-at', `2026-11-23T10:00:00.${String(saves).padStart(3, '0')}+09:00`);
    closeDrawer();
    return doc.getElementById('stay_seasons');
  };
  doc.addEventListener('submit', (e) => { e.preventDefault(); });
  doc.addEventListener('input', (e) => {
    if (!e.target.closest('#stay_drawer_body')) return;
    log.typed.push(e.target.name);
    if (o.onType === 'clearNet' && e.target.name === 'occupancy_adjust') e.target.closest('[data-stay-screen]').querySelector('[name="net_price"]').value = '';
  });
  doc.addEventListener('click', (e) => {
    const b = e.target.closest('button, a, input, label');
    if (!b) return;
    const name = b.getAttribute('data-stay-action') || b.getAttribute('data-stay-tab') || `${b.localName}${b.name ? `[name=${b.name}]` : ''}`;
    log.reached.push(name);
    if (b.matches(HTMX) && !b.hasAttribute('data-htmx-powered')) { log.dead.push(name); return; }
    if (b.matches('ul.tab-container a')) {
      doc.querySelectorAll('ul.tab-container a').forEach((a) => a.classList.toggle('active', a === b));
      doc.querySelectorAll('.stay-pane').forEach((p) => { p.style.display = p.getAttribute('data-stay-tab') === b.getAttribute('data-stay-tab') ? '' : 'none'; });
    } else if (b.matches('#stay_seasons [data-stay-action="fill"]')) {
      swap(() => open(o.window));
    } else if (b.matches('[data-stay-screen="season-price-fill"] [data-stay-action="reset"]')) {
      swap(() => { body.innerHTML = morph(edit(WINDOW)); return body; });
    } else if (b.matches('[data-stay-screen="season-price-fill"] [data-stay-action="save"]')) {
      log.posts.push({ path: b.getAttribute('hx-post'), pairs: collect(b) });
      if (o.onSave === 'hang') { fire('htmx:before:request', {}); return; }
      if (o.onSave === 'slow') { fire('htmx:before:request', {}); w.setTimeout(() => { const root = saved(); fire('htmx:after:swap', {}); wire(root); fire('htmx:finally:request', {}); }, o.slowMs); return; }
      if (o.onSave === 'refused') {
        swap(() => {
          const sent = collect(b);
          let fragment = morph(edit(o.window)).replace('<div class="table1">', '<div class="stay-banner stay-banner--blocking" data-stay-result="error"><span>조정 값은 부호를 붙여 주세요</span></div><div class="table1">');
          body.innerHTML = fragment;
          sent.forEach(([n, v]) => { const el = body.querySelector(`[name="${n}"]:not([type="checkbox"])`); if (el) el.value = v; });
          return body;
        });
        return;
      }
      swap(() => saved(o.onSave === 'nosupply' ? '<div class="stay-banner stay-banner--blocking" data-stay-result="error" data-stay-banner="no_supply_currency"><span>공급 통화가 없어 가격 원장을 기록하지 못했습니다.</span></div>' : ''));
    } else if (b.matches('[hx-post],[hx-get]')) {
      log.posts.push({ path: b.getAttribute('hx-post') || b.getAttribute('hx-get') });
    }
  });
  w.addEventListener('stay-drawer-close', closeDrawer);
  w.eval(HELPER); w.eval(BOOT); w.eval(PAGE); w.eval(SEASON);
  return { dom, w, doc, log, opts: o, drawerOpen: () => drawer.classList.contains('is-open'), answerSavesWith: (mode) => { o.onSave = mode; },
    // 드로어에 창을 바로 그린다(벽 시험)
    showWindow: () => { open(o.window); wire(body); return body.firstElementChild; } };
}

// 페이지가 둔 조각의 모양(따옴표 없는 JSON)을 푼다 — 파이썬 `change_core.answers.unpack` 과 같은 셈
export function unpack(text) {
  const back = (s) => s.replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)));
  const walk = (v) => (typeof v === 'string' ? back(v) : Array.isArray(v) ? v.map(walk)
    : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, x]) => [back(k), walk(x)])) : v);
  return walk(JSON.parse(text.replace(/'/g, '"')));
}
export function takeAll(w, result) {
  const meta = result.body, takes = [];
  for (let at = 0; at < meta.chars;) {
    const piece = plain(w.stayPriceSeason.take(meta.id, at));
    if (!piece.ok) throw new Error(piece.error);
    takes.push(piece);
    at = piece.next;
  }
  return { takes, body: unpack(takes.map((t) => t.text).join('')) };
}
// 시즌 창 저장의 부를 값을 읽은 창에서 손으로 만든다(파이썬 `price_season.want_form` 과 같은 차례) — 계약 시험은 파이썬이 만든 값을 쓴다
export function payloadFrom(read, save, no = 1) {
  const want = [];
  read.order.forEach((name) => {
    if (name === 'rooms') read.rooms.filter((r) => save.rooms.includes(r.id)).forEach((r) => want.push(['rooms', r.id]));
    else if (name === 'rate_plans') read.plans.filter((r) => save.plans.includes(r.id)).forEach((r) => want.push(['rate_plans', r.id]));
    else if (name === 'overwrite') { if (save.overwrite !== false) want.push(['overwrite', 'on']); }
    else if (name === 'stale_cleanup') { /* 켜지 않는다 */ }
    else if (name in save.texts) want.push([name, save.texts[name]]);
    else { const hit = read.form.find((x) => x[0] === name); if (hit) want.push([name, hit[1]]); else if (name.startsWith('child_extra_') || ['price', 'original_price', 'net_price', 'plan_adjust', 'occupancy_keys', 'occupancy_adjust', 'los_prices'].includes(name)) want.push([name, '']); }
  });
  return { no, hotel: HOTEL, offer: OFFER, season: { id: IDS.season, name: 'PEAK' }, dates: read.dates, form: read.form, want,
    candidates: { rooms: read.rooms.map((r) => [r.id, r.label]), plans: read.plans.map((r) => [r.id, r.roomId, r.label]) },
    child: read.child.filter((c) => !c.editable).map((c) => [c.field, c.text]) };
}
