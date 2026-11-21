// 부가옵션 페이지 시험의 받침 — jsdom 위에 ERP Stay 편집 화면(탭 · 호텔 표식 · 부가옵션 탭 · 드로어)을 세우고, 러너의 도우미 · 부트,
// 가격 도우미 `stay_price.js`, 이 스킬의 `stay_addon_price.js` 를 그대로 올린다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
//
// 화면은 손 조각이다(`fixtures/erp/addons_erp.mjs` 가 ERP 템플릿을 따라 그린다 · 데이터는 `fixtures/erp/addons.json`, 모두 지어낸 값).
// 가짜 서버는 문서에 붙인 클릭 듣개다 — 벽(window 캡처 단계)이 막은 클릭은 여기 닿지 않으므로 `log.reached` 가 증거다. 저장 단추를
// 받으면 그 단추의 `hx-include` 고르개를 문서에 그대로 걸어 보낼 칸을 모으고(`log.posts[].pairs`), 폼처럼 검사해 저장하거나
// (목록을 저장 배너와 함께 다시 그리고 드로어를 닫고 `#stay_save_result` 의 저장 시각을 바꾼다) 오류와 함께 창을 다시 그린다.
// htmx 4 처럼 htmx 단추는 연결돼야(`data-htmx-powered`) 눌린다.
//
// 가격 도우미의 받침(`stay-price-change/tests/page_harness.mjs`)에서 jsdom 찾기 · 러너 파일 · 호텔 표식 · 값 넘기기 · 사람의 클릭을
// 빌린다(그 파일은 고치지 않는다).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadJsdom, HELPER, BOOT, PAGE, LOADER, HOTEL, RUNNER_STEPS, RUNNER_CURSOR, hotelMarks, inPage, plain, charsOf, personClick } from '../../stay-price-change/tests/page_harness.mjs';
import { panel, stub, priceWindow, priceTitle, addonWindow, lineOf, windowValues } from './fixtures/erp/addons_erp.mjs';

export { HELPER, BOOT, PAGE, LOADER, HOTEL, RUNNER_STEPS, RUNNER_CURSOR, inPage, plain, charsOf, personClick };
const JSDOM = loadJsdom();

export const HERE = dirname(fileURLToPath(import.meta.url));
export const SKILL = join(HERE, '..');
export const ADDON = readFileSync(join(SKILL, 'scripts', 'page', 'stay_addon_price.js'), 'utf8');
export const DB = Object.freeze(JSON.parse(readFileSync(join(HERE, 'fixtures', 'erp', 'addons.json'), 'utf8')));
const copy = (value) => JSON.parse(JSON.stringify(value));

const HTMX = ['action', 'get', 'post', 'put', 'patch', 'delete'].map((v) => `[hx-${v}],[data-hx-${v}]`).join(',');
const wire = (root) => { if (root) [root, ...root.querySelectorAll(HTMX)].filter((el) => el.matches(HTMX)).forEach((el) => el.setAttribute('data-htmx-powered', 'true')); };

// 탭 줄(`master_editor.html` 의 `ul.tab_style1.tab-container`) — 표식 없는 [기본정보] 와 다른 탭들도 벽의 과녁이다
export const TABS = [['#baseinfo', null, '기본정보'], ['#stay_tab_offers', 'offers', '오퍼'], ['#stay_tab_calendar', 'calendar', '가격 캘린더'],
  ['#stay_tab_charges', 'charges', '부과금'], ['#stay_tab_addons', 'addons', '부가옵션'], ['#stay_tab_promotions', 'promotions', '프로모션']];
// 다른 탭의 위험한 단추 — 벽이 막는지 볼 과녁(ERP 템플릿의 표식 그대로)
const OTHER_PANES = `
<div id="stay_tab_offers" class="col s12 stay-pane stay-root" data-stay-tab="offers" style="display:none">
  <button type="button" class="stay-btn stay-btn--ghost" data-stay-action="archive">보관</button>
  <button type="button" class="stay-btn stay-btn--danger" data-stay-action="end">판매 종료</button>
</div>
<div id="stay_tab_charges" class="col s12 stay-pane stay-root" data-stay-tab="charges" style="display:none">
  <button type="button" class="stay-btn stay-btn--danger" data-stay-action="delete" hx-delete="/stay/1/charges/9/">삭제</button>
</div>
<div class="stay-banner" data-stay-card="gate"><button type="button" class="stay-btn stay-btn--primary" data-stay-action="activate">판매 시작</button></div>`;

const DEC = /^\d+(\.\d+)?$/;
const money = (text) => { const [whole, part = ''] = text.split('.'); return `${String(Number(whole))}.${(part + '00').slice(0, 2)}`; };

/**
 * ERP 한 장. `opts`:
 *   tab        처음 켜진 탭(기본 'addons') — 'calendar' 면 [부가옵션] 탭을 눌러야 목록이 보인다
 *   addons     'loaded'(기본: 목록이 이미 왔다) | 'stub'(스텁만 있고, 스텁의 hx-trigger load 처럼 stubMs(기본 60ms) 뒤에 목록이 온다)
 *   db         addons.json 대신 쓸 데이터(복사해 쓴다)
 *   onSave     'ok'(기본: 폼처럼 검사해 저장 · 틀리면 오류와 함께 다시 그린다) | 'refuse'(늘 적용 범위 오류로 다시 그린다) |
 *              'silent'(요청은 끝나지만 아무것도 바뀌지 않는다) | 'morph'(저장하고 목록 요소는 그대로 둔 채 안만 갈아 끼운다)
 *   stamp      false 면 저장 응답이 `#stay_save_result` 를 갈아 끼우지 않는다(목록 배너만 표지)
 *   onType     'clearNet' 면 판매가 칸에 글자를 치면 화면 스크립트가 공급 원가 칸을 비운다
 *   windowFor  {줄 번호: 다른 줄 번호} — 서버가 그 줄의 [편집] 에 다른 줄의 창을 내준다(서버 결함 흉내)
 *   hotel · login · withScripts · withPage · bare   가격 도우미 받침과 같은 뜻(bare 면 아무것도 올리지 않는다 — 올리개 시험)
 */
export function addonPage(opts = {}) {
  const o = Object.assign({ tab: 'addons', addons: 'loaded', onSave: 'ok', stamp: true, withScripts: true, withPage: true }, opts);
  const db = copy(o.db || DB);
  const hotelId = (o.hotel && o.hotel.id) || HOTEL.id;
  const marks = o.hotel === null ? '' : hotelMarks(o.hotel || {});
  const tabs = TABS.map(([href, name, label]) => `<li class="tab"><a href="${href}"${name ? ` data-stay-tab="${name}"` : ''}${name === o.tab ? ' class="active"' : ''}><span>${label}</span></a></li>`).join('\n  ');
  const html = o.login ? '<form method="post" action="/accounts/login/"><input type="text" name="username"><input type="password" name="password"><button type="submit">로그인</button></form>'
    : `${marks}<ul class="tab_style1 tab-container">
  ${tabs}
</ul>${OTHER_PANES}
<div id="stay_tab_addons" class="col s12 stay-pane stay-root" ajax_loaded data-stay-tab="addons"${o.tab === 'addons' ? '' : ' style="display:none"'}>
${o.addons === 'stub' ? stub(hotelId) : panel(db, hotelId)}
</div>
<div class="stay-drawer">
  <div class="stay-drawer__mask" aria-hidden="true"></div>
  <aside class="stay-drawer__panel" role="dialog" aria-modal="true">
    <header class="stay-drawer__header">
      <h4 class="stay-drawer__title"></h4>
      <button type="button" class="stay-drawer__close" aria-label="닫기">&times;</button>
    </header>
    <div class="stay-drawer__context" id="stay_drawer_context"></div>
    <div class="stay-drawer__body" id="stay_drawer_body"></div>
  </aside>
</div>
<div id="stay_save_result" hidden></div>`;
  const dom = new JSDOM(html, { url: `https://erp.example.test/stay/${hotelId}/#stay_tab_addons`, runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window, doc = w.document;
  wire(doc.body);
  const drawer = doc.querySelector('.stay-drawer'), body = doc.getElementById('stay_drawer_body'), title = doc.querySelector('.stay-drawer__title');
  const log = { reached: [], gets: [], posts: [], typed: [], dead: [] };
  let morphs = 0, saves = 0;
  const morph = () => `m${++morphs}`;
  const fire = (name, detail) => doc.dispatchEvent(new w.CustomEvent(name, { detail, bubbles: true }));
  // 서버 요청 하나 — htmx 4 의 차례: 요청 시작 → 조각 끼우기 → 정착 → 연결 → 요청 끝
  const swap = (apply) => {
    fire('htmx:before:request', {});
    const root = apply();
    fire('htmx:after:swap', {}); fire('htmx:after:settle', {}); wire(root);
    fire('htmx:finally:request', {});
  };
  const open = (fragment, heading = '') => { body.innerHTML = fragment; title.textContent = heading; drawer.classList.add('is-open'); return body; };
  // ERP 드로어처럼 닫는다 — `is-open` 과 제목은 바로 빠지고 내용은 0.35초 뒤에 비운다(`_drawer.html` hide())
  const closeDrawer = () => {
    drawer.classList.remove('is-open');
    title.textContent = '';
    const stale = body.firstElementChild;
    if (stale) w.setTimeout(() => { if (!drawer.classList.contains('is-open') && body.firstElementChild === stale) body.replaceChildren(); }, 350);
  };
  const nameOf = (b) => {
    for (const a of ['data-stay-action', 'data-stay-tab']) if (b.hasAttribute(a)) return `${a.replace(/^data-/, '')}=${b.getAttribute(a)}`;
    return `${b.localName}${b.name ? '[name=' + b.name + ']' : ''}`;
  };
  // 저장 단추가 보내는 칸 — 그 단추의 hx-include 고르개를 문서에 그대로 걸고 htmx 처럼 고른다(이름 있고 막히지 않은 칸 · 켜진 체크)
  const collect = (save) => [...doc.querySelectorAll(save.getAttribute('hx-include'))].flatMap((el) => {
    if (!el.name || el.matches(':disabled')) return [];
    if (el.type === 'checkbox' || el.type === 'radio') return el.checked ? [[el.name, el.value]] : [];
    if (el.localName === 'select' && el.multiple) return [...el.selectedOptions].map((op) => [el.name, op.value]);
    return [[el.name, el.value]];
  });
  // 보낸 칸을 폼(`StayAddonPriceForm`)처럼 검사한다 — 틀린 칸 → 오류 문구
  const check = (get) => {
    const errors = {};
    const name = (get('name') || '').trim(), price = (get('price') || '').trim(), net = (get('net_amount') || '').trim();
    if (!name) errors.name = '가격행 이름을 입력해주세요';
    if (!price) errors.price = '판매가를 입력해주세요 (무료면 0)';
    else if (/^-/.test(price)) errors.price = '판매가는 0 이상이어야 합니다';
    else if (!DEC.test(price)) errors.price = '숫자를 입력하세요.';
    else if ((price.split('.')[1] || '').length > 2) errors.price = '소수점 아래는 두 자리까지입니다';
    if (net && (!DEC.test(net) || (net.split('.')[1] || '').length > 2)) errors.net_amount = '숫자를 입력하세요.';
    if (get('season') && get('date')) errors.date = '시즌과 개별 날짜를 동시에 지정할 수 없습니다 — 좌표가 둘이 됩니다';
    return errors;
  };
  const boundValues = (line, pairs) => {
    const get = (n) => (pairs.find(([k]) => k === n) || [])[1] ?? '';
    const every = (n) => pairs.filter(([k]) => k === n).map(([, v]) => v);
    const v = windowValues(line);
    Object.assign(v, { name: get('name'), price: get('price'), net_amount: get('net_amount'), season: get('season'), date: get('date'), rate_plan: get('rate_plan'), description: get('description') });
    for (const axis of ['rate_plan', 'room']) v.scope[axis] = { mode: get(`scope_${axis}_mode`) || '0', include: every(`scope_${axis}_include`), exclude: every(`scope_${axis}_exclude`) };
    v.scope.confirm = every('scope_confirm_deny_all').length > 0;
    return v;
  };
  const savePrice = (save) => {
    const path = save.getAttribute('hx-post');
    const pairs = collect(save);
    log.posts.push({ path, pairs });
    const lineId = /\/addon-prices\/(\d+)\/edit\/$/.exec(path)[1];
    const { line } = lineOf(db, lineId);
    if (o.onSave === 'silent') {   // 요청은 끝나지만 화면은 그대로다(응답이 비었거나 htmx 가 버린 응답)
      fire('htmx:before:request', {});
      w.setTimeout(() => fire('htmx:finally:request', {}), 20);
      return;
    }
    const get = (n) => (pairs.find(([k]) => k === n) || [])[1];
    const errors = o.onSave === 'refuse' ? {} : check(get);
    const scopeError = o.onSave === 'refuse' ? '가격 줄의 적용 범위는 부가옵션의 범위 안이어야 합니다 — 저장하지 않았습니다' : '';
    if (scopeError || Object.keys(errors).length) {   // 실패도 200 — 보낸 값으로 창을 다시 그린다(뿌리 id 가 새로 난다)
      swap(() => { body.innerHTML = priceWindow(db, hotelId, lineId, { morph: morph(), values: boundValues(line, pairs), errors, scopeError }); return body; });
      return;
    }
    const net = (get('net_amount') || '').trim();
    Object.assign(line, { name: get('name').trim(), price: money(get('price').trim()), net: net ? money(net) : null, sell_row: true,
      season: get('season') || '', date: get('date') || '', rate_plan: get('rate_plan') || '', description: get('description') || '' });
    const v = boundValues(line, pairs);
    line.scope = { rate_plan: v.scope.rate_plan, room: v.scope.room };
    saves++;
    // 성공 — 목록은 hx-swap-oob 로 제자리에, 드로어 바디에는 남는 것이 없고, 저장 표지를 갈아 끼우고, 드로어를 닫는다
    swap(() => {
      const old = doc.getElementById('stay_addons');
      if (o.onSave === 'morph') old.innerHTML = new w.DOMParser().parseFromString(panel(db, hotelId, { saved: true }), 'text/html').getElementById('stay_addons').innerHTML;
      else old.outerHTML = panel(db, hotelId, { saved: true });
      body.replaceChildren();
      if (o.stamp) {
        const mark = doc.getElementById('stay_save_result');
        mark.setAttribute('data-stay-result', 'saved');
        mark.setAttribute('data-stay-saved-at', `2026-11-21T10:00:00.${String(saves).padStart(3, '0')}+09:00`);
      }
      closeDrawer();
      return doc.getElementById('stay_addons');
    });
  };
  doc.addEventListener('submit', (e) => { e.preventDefault(); });
  doc.addEventListener('input', (e) => {
    if (!e.target.closest('#stay_drawer_body')) return;
    log.typed.push(e.target.name);
    if (o.onType === 'clearNet' && e.target.name === 'price') {
      const net = e.target.closest('[data-stay-screen]').querySelector('[name="net_amount"]');
      if (net) net.value = '';
    }
  });
  doc.addEventListener('click', (e) => {
    const b = e.target.closest('button, a, input, label, select');
    if (!b) return;
    log.reached.push(nameOf(b));
    if (b.matches(HTMX) && !b.hasAttribute('data-htmx-powered')) { log.dead.push(nameOf(b)); return; }
    if (b.matches('ul.tab-container a')) {
      doc.querySelectorAll('ul.tab-container a').forEach((a) => a.classList.toggle('active', a === b));
      doc.querySelectorAll('.stay-pane').forEach((pane) => { pane.style.display = pane.getAttribute('data-stay-tab') === b.getAttribute('data-stay-tab') ? '' : 'none'; });
    } else if (b.matches('tr[data-stay-entity="addon_price"] [data-stay-action="open_edit"]')) {
      const asked = b.closest('tr').getAttribute('data-stay-entity-id');
      const lineId = (o.windowFor && o.windowFor[asked]) || asked;
      log.gets.push(b.getAttribute('hx-get'));
      swap(() => open(priceWindow(db, hotelId, lineId, { morph: morph() }), priceTitle(db, lineId)));
    } else if (b.matches('[data-stay-screen="addon-price"] [data-stay-action="save"]')) {
      savePrice(b);
    } else if (b.matches('[hx-post]')) {
      log.posts.push({ path: b.getAttribute('hx-post') });   // 삭제 · 설정 저장 — 벽이 막았어야 하는 요청
    }
  });
  w.addEventListener('stay-drawer-close', closeDrawer);
  // 스텁의 hx-trigger load — 페이지가 뜨면 목록을 불러와 같은 id 로 갈아 끼운다(탭이 꺼져 있어도)
  const waiting = doc.querySelector('#stay_addons:not([data-stay-panel])');
  if (waiting) {
    log.gets.push(waiting.getAttribute('hx-get'));
    w.setTimeout(() => swap(() => { waiting.outerHTML = panel(db, hotelId); return doc.getElementById('stay_addons'); }), o.stubMs ?? 60);
  }
  w.localStorage.setItem('staySteps', RUNNER_STEPS);
  w.localStorage.setItem('stayRunCursor', RUNNER_CURSOR);
  if (!o.bare) {
    if (o.withScripts) { w.eval(HELPER); w.eval(BOOT); }
    if (o.withPage) w.eval(PAGE);
    w.eval(ADDON);
  }
  return {
    dom, w, doc, log, db, closeDrawer,
    drawerOpen: () => drawer.classList.contains('is-open'),
    // 저장 응답을 바꾼다(앞 저장은 그대로 두고 다음 저장부터) — onSave 와 같은 값
    answerSavesWith: (mode) => { o.onSave = mode; },
    // 드로어에 조각을 바로 그린다(벽 시험) — 가격 편집 창(줄 번호) · 부가옵션 설정 창
    showPrice: (lineId) => { open(priceWindow(db, hotelId, lineId, { morph: morph() }), priceTitle(db, lineId)); wire(body); return body.firstElementChild; },
    showAddon: (addonId) => { open(addonWindow(db, hotelId, addonId, { morph: morph() })); wire(body); return body.firstElementChild; }
  };
}

const LEGACY = '요금제: 기존 범위 그대로 · 객실: 기존 범위 그대로 · 부가옵션 범위와 모두 일치하는 대상에만 적용';
// fixtures/erp/addons.json 이 그리는 목록 — 화면의 글자 그대로(손으로 적은 기대값)
export const LISTED = [
  { id: '201', name: '조식 추가 (성인)', offer: '데모 오퍼 2027', lines: [
    { id: '301', name: '비수기 조식', sell: '20.00 USD', values: ['판매가: 20.00 USD', '공급 원가: 15.00 USD'], target: '비수기', scope: LEGACY, band: '전체' },
    { id: '302', name: '연말 조식', sell: '35.50 USD', values: ['판매가: 35.50 USD', '공급 원가: 28.00 USD'], target: '2026-12-31', scope: LEGACY, band: '전체' }] },
  { id: '202', name: '공항 픽업', offer: '데모 오퍼 2027', lines: [
    { id: '303', name: '편도 픽업', sell: '40.00 USD', values: [], target: '전체', scope: LEGACY, band: '전체' }] },
  { id: '203', name: '엑스트라베드', offer: '데모 오퍼 2027', lines: [
    { id: '304', name: '엑스트라베드 1개', sell: '30.00 USD', values: ['판매가: 30.00 USD', '공급 원가: 25.00 USD'], target: '전체', scope: LEGACY, band: '전체' }] },
  { id: '204', name: '엑스트라베드', offer: '데모 연말 오퍼', lines: [
    { id: '305', name: '엑스트라베드 1개', sell: '33.00 USD', values: ['판매가: 33.00 USD', '공급 원가: 27.50 USD'], target: '연말 시즌',
      scope: '요금제: 지정한 대상만 / 포함: 데모 연말 오퍼 · 디럭스 · 조식 포함 · 객실: 기존 범위 그대로 · 부가옵션 범위와 모두 일치하는 대상에만 적용', band: '전체' }] }
];

// 답의 조각을 take 로 자리(at)를 따라 모두 받아 잇는다
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
    const piece = plain(size === undefined ? w.stayAddonPrice.take(meta.id, at) : w.stayAddonPrice.take(meta.id, at, size));
    if (!piece.ok) throw new Error(piece.error);
    takes.push(piece);
    at = piece.next;
  }
  const text = takes.map((t) => t.text).join('');
  return { takes, text, body: unpack(text) };
}
