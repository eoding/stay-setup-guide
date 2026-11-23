// 부과금 페이지 시험의 받침 — jsdom 위에 ERP Stay 편집 화면(탭 · 호텔 표식 · 부과금 탭 · 드로어)을 세우고, 러너의 도우미 · 부트,
// 가격 도우미 `stay_price.js`, 이 스킬의 `stay_charge.js` 를 그대로 올린다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
//
// 화면은 손 조각이다(`fixtures/erp/charges_erp.mjs` 가 ERP 템플릿을 따라 그린다 · 데이터는 `fixtures/erp/charges.json`, 모두 지어낸 값).
// 가짜 서버는 문서에 붙인 클릭 듣개다 — 벽(window 캡처 단계)이 막은 클릭은 여기 닿지 않으므로 `log.reached` 가 증거다. 저장 단추를
// 받으면 그 단추의 `hx-include` 고르개를 문서에 그대로 걸어 보낼 칸을 모으고(`log.posts[].pairs`), `ChargeEditForm` 처럼 검사해
// 저장하거나(시간대 · 연령별 단가를 보낸 값으로 다시 만들고, 목록을 저장 배너와 함께 다시 그리고 드로어를 닫고 `#stay_save_result` 의
// 저장 시각을 바꾼다) 오류와 함께 창을 다시 그린다. htmx 4 처럼 htmx 단추는 연결돼야(`data-htmx-powered`) 눌린다.
//
// 가격 도우미의 받침(`stay-price-change/tests/page_harness.mjs`)에서 jsdom 찾기 · 러너 파일 · 호텔 표식 · 값 넘기기 · 조각 풀기를
// 빌린다(그 파일은 고치지 않는다).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadJsdom, HELPER, BOOT, PAGE, LOADER, HOTEL, RUNNER_STEPS, RUNNER_CURSOR, hotelMarks, inPage, plain, charsOf, unpack } from '../../stay-price-change/tests/page_harness.mjs';
import { panel, stub, chargeWindow, chargeTitle, chargeOf, windowValues } from './fixtures/erp/charges_erp.mjs';

export { HELPER, BOOT, PAGE, LOADER, HOTEL, RUNNER_STEPS, RUNNER_CURSOR, inPage, plain, charsOf };
const JSDOM = loadJsdom();

export const HERE = dirname(fileURLToPath(import.meta.url));
export const SKILL = join(HERE, '..');
export const CHARGE = readFileSync(join(SKILL, 'scripts', 'page', 'stay_charge.js'), 'utf8');
export const ADDON = readFileSync(join(SKILL, '..', 'stay-addon-price-change', 'scripts', 'page', 'stay_addon_price.js'), 'utf8');
export const DB = Object.freeze(JSON.parse(readFileSync(join(HERE, 'fixtures', 'erp', 'charges.json'), 'utf8')));
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
<div id="stay_tab_addons" class="col s12 stay-pane stay-root" data-stay-tab="addons" style="display:none">
  <button type="button" class="stay-btn stay-btn--danger" data-stay-action="delete" hx-delete="/stay/1/addons/9/">삭제</button>
</div>
<div class="stay-banner" data-stay-card="gate"><button type="button" class="stay-btn stay-btn--primary" data-stay-action="activate">판매 시작</button></div>`;

const DEC = /^-?\d+(\.\d+)?$/;
const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;
const money = (text) => { const [whole, part = ''] = text.split('.'); return `${String(Number(whole))}.${(part + '00').slice(0, 2)}`; };
const places = (text) => (text.split('.')[1] || '').length;
const norm = (text) => (text.startsWith('-') ? `-${money(text.slice(1))}` : money(text));

// 보낸 칸을 `ChargeEditForm` 처럼 읽고 검사한다(이 시험에 걸리는 규칙만) — {errors, values(다시 그릴 값), saved(저장할 값)}
function judge(db, offer, charge, pairs) {
  const get = (n) => { const hit = pairs.find(([k]) => k === n); return hit ? hit[1] : ''; };
  const every = (n) => pairs.filter(([k]) => k === n).map(([, v]) => v);
  const errors = {};
  const decimal = (name, text, { min = null, digits = 12 } = {}) => {
    const value = text.trim();
    if (value === '') return null;
    if (!DEC.test(value)) { errors[name] = '숫자를 입력하세요.'; return null; }
    if (places(value) > 2) { errors[name] = '소수점 아래는 두 자리까지입니다'; return null; }
    if (value.replace('-', '').split('.')[0].replace(/^0+(?=\d)/, '').length > digits - 2) { errors[name] = `전체 ${digits}자리를 넘을 수 없습니다`; return null; }
    if (min !== null && Number(value) < min) { errors[name] = `${min} 이상이어야 합니다`; return null; }
    return norm(value);
  };
  const name = get('name').trim();
  if (!name) errors.name = '필수 항목입니다.';
  const kind = get('kind'), basis = get('basis'), per = get('per');
  if (!['0', '1', '9'].includes(kind)) errors.kind = '올바르게 선택해 주세요.';
  if (!['0', '1'].includes(basis)) errors.basis = '올바르게 선택해 주세요.';
  if (!['0', '1', '2'].includes(per)) errors.per = '올바르게 선택해 주세요.';
  // ① 방식과 무관한 칸은 비운다 ② 「비움」이면 버리고 「지정」이면 값을 받는다(0 도 값이다)
  const ignored = { 0: 'pct', 1: 'amount' }[basis];
  const amounts = {};
  for (const [key, mode, label, digits] of [['amount', 'amount_mode', '정액 금액', 12], ['pct', 'pct_mode', '정률(%)', 5]]) {
    if (!['blank', 'set'].includes(get(mode))) errors[mode] = '올바르게 선택해 주세요.';
    const value = decimal(key, get(key), { digits });
    if (key === ignored || get(mode) === 'blank') amounts[key] = null;
    else if (get(mode) === 'set' && value === null && !errors[key]) errors[key] = `${label} 값을 입력하세요 — 0 도 유효한 값입니다`;
    else amounts[key] = value;
  }
  const mandatory = get('date_mode') === 'mandatory';
  if (!['optional', 'mandatory'].includes(get('date_mode'))) errors.date_mode = '올바르게 선택해 주세요.';
  const dates = [];
  for (const token of get('date_scope').trim().split(/[,\s]+/).filter(Boolean)) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(token)) { errors.date_scope = `날짜 형식이 올바르지 않습니다: ${token} (YYYY-MM-DD)`; break; }
    if (!dates.includes(token)) dates.push(token);
  }
  dates.sort();
  const rooms = every('room_scope');
  // 시간대 — 보낸 행을 짝지어 읽고(두 시각이 다 빈 행은 버린다), 두 시각 · 앞뒤 · 겹침 · 정액은 금액 · 정률은 비율
  const starts = every('tiers_time_from'), ends = every('tiers_time_to'), bases = every('tiers_basis'), tamounts = every('tiers_amount'), tpcts = every('tiers_pct');
  const tiers = [];
  starts.forEach((start, i) => {
    const from = start.trim(), to = (ends[i] || '').trim();
    if (!from && !to) return;
    tiers.push({ from, to, basis: /^\d+$/.test(bases[i] || '') ? Number(bases[i]) : 1, amount: (tamounts[i] || '').trim(), pct: (tpcts[i] || '').trim() });
  });
  const spans = [];
  tiers.forEach((t, i) => {
    if (errors.tiers) return;
    const n = i + 1;
    if (!TIME.test(t.from) || !TIME.test(t.to)) { errors.tiers = `${n}번째 티어의 시작·종료 시각을 모두 입력하세요`; return; }
    if (t.from >= t.to) { errors.tiers = `${n}번째 티어의 종료 시각은 시작 시각보다 뒤여야 합니다`; return; }
    const num = (text) => (text === '' || !DEC.test(text) ? null : norm(text));
    if (t.basis === 0) {
      t.amount = num(t.amount); t.pct = null;
      if (t.amount === null) { errors.tiers = `${n}번째 티어는 정액이라 금액이 필요합니다 — 0 도 유효한 값입니다`; return; }
    } else {
      t.pct = num(t.pct); t.amount = null;
      if (t.pct === null) { errors.tiers = `${n}번째 티어는 정률이라 비율이 필요합니다 — 0 도 유효한 값입니다`; return; }
    }
    const hit = spans.find(([a, b]) => t.from <= b && a <= t.to);
    if (hit) { errors.tiers = `${hit[0]}~${hit[1]} 와 ${t.from}~${t.to} 가 겹칩니다 — 경계 시각이 양쪽에 들어가 그 시각의 요율이 행 순서에 따라 갈립니다. 앞 단의 종료를 1분 당기세요(예: 09:00 이 아니라 08:59).`; return; }
    spans.push([t.from, t.to]);
  });
  // 연령별 단가 · 현장 연령별 단가 — 비우면 행이 없다(= 성인가), 0 은 무료. 0 미만은 거절
  const ages = {}, onsiteAges = {};
  for (const b of offer.bands) {
    const a = decimal(`age_rate_${b.id}`, get(`age_rate_${b.id}`), { min: 0 });
    if (a !== null) ages[b.id] = a;
    const o = decimal(`onsite_age_rate_${b.id}`, get(`onsite_age_rate_${b.id}`), { min: 0 });
    if (o !== null) onsiteAges[b.id] = o;
  }
  if (Object.keys(ages).length) {
    if (per !== '2') errors.per = '연령별 단가를 넣으려면 부과 단위가 “인당”이어야 합니다 — 아니면 소아 단가를 비우세요.';
    if (basis !== '0') errors.basis = '연령별 단가는 부과 방식이 “정액”일 때만 쓰입니다 — 아니면 소아 단가를 비우세요.';
    if (tiers.length) errors.tiers = '시간대별 요율이 있으면 연령별 단가가 계산에 쓰이지 않습니다 — 둘 중 하나만 두세요.';
  }
  const onsiteCurrency = get('onsite_currency');
  if (onsiteCurrency && !db.currencies.some((c) => c.id === onsiteCurrency)) errors.onsite_currency = '올바르게 선택해 주세요.';
  const onsiteAmount = decimal('onsite_amount', get('onsite_amount'), { min: 0 });
  if ((onsiteAmount !== null || Object.keys(onsiteAges).length) && !onsiteCurrency) errors.onsite_currency = '현장 결제 통화를 선택하세요.';
  if (onsiteCurrency && (basis !== '0' || amounts.amount === null || Number(amounts.amount) !== 0 || tiers.length || Object.values(ages).some((v) => Number(v) !== 0))) {
    errors.onsite_currency = '현장 결제 항목의 온라인 정액·연령별 금액은 0으로 두고 시간 티어를 비우세요.';
  }
  if (Object.keys(onsiteAges).length && per !== '2') errors.per = '현장 연령별 단가는 인당 부과에만 사용할 수 있습니다.';
  const mode = get('scope_room_mode');
  if (!['0', '1', '2'].includes(mode)) errors.scope_room_mode = '올바르게 선택해 주세요.';
  const scope = { mode: mode || '0', include: every('scope_room_include'), exclude: every('scope_room_exclude') };

  // 거절한 POST 는 보낸 글자 그대로 다시 그린다(`ChargeEditForm.tier_rows` 는 보낸 행을, 칸은 보낸 값을 싣는다)
  const values = Object.assign(windowValues(charge), {
    kind, name: get('name'), basis, per, amount_mode: get('amount_mode'), amount: get('amount'), pct_mode: get('pct_mode'), pct: get('pct'),
    date_mode: get('date_mode'), date_scope: get('date_scope'), rooms, onsite_currency: onsiteCurrency, onsite_amount: get('onsite_amount'),
    ages: Object.fromEntries(offer.bands.map((b) => [b.id, get(`age_rate_${b.id}`)])),
    onsite_ages: Object.fromEntries(offer.bands.map((b) => [b.id, get(`onsite_age_rate_${b.id}`)])),
    tiers: starts.map((start, i) => ({ from: start, to: ends[i] || '', basis: bases[i] || '1', amount: tamounts[i] || '', pct: tpcts[i] || '' }))
      .filter((t) => t.from.trim() || t.to.trim()),
    description: get('description'), scope: Object.assign({}, scope, { confirm: every('scope_confirm_deny_all').length > 0 })
  });
  const saved = {
    kind: Number(kind), name, basis: Number(basis), per: Number(per), amount: amounts.amount ?? null, pct: amounts.pct ?? null,
    mandatory, dates: mandatory ? dates : [], rooms, onsite_currency: onsiteCurrency || null, onsite_amount: onsiteAmount,
    ages, onsite_ages: onsiteAges, tiers: tiers.map((t) => ({ from: t.from, to: t.to, basis: t.basis, amount: t.amount, pct: t.pct })),
    description: get('description'), scope
  };
  return { errors, values, saved };
}

/**
 * ERP 한 장. `opts`:
 *   tab        처음 켜진 탭(기본 'charges') — 'calendar' 면 [부과금] 탭을 눌러야 목록이 보인다
 *   charges    'loaded'(기본: 목록이 이미 왔다) | 'stub'(스텁만 있고, 스텁의 hx-trigger load 처럼 stubMs(기본 60ms) 뒤에 목록이 온다)
 *   db         charges.json 대신 쓸 데이터(복사해 쓴다)
 *   onSave     'ok'(기본: 폼처럼 검사해 저장 · 틀리면 오류와 함께 다시 그린다) | 'refuse'(늘 적용 범위 오류로 다시 그린다) |
 *              'silent'(요청은 끝나지만 아무것도 바뀌지 않는다) | 'late'(요청이 lateMs(기본 1500ms) 동안 돌다가 'refuse' 처럼 거절된
 *              창을 드로어 몸통에 넣는다 — 드로어가 닫혀 있어도. ERP 는 거절에 드로어를 다시 열지 않는다)
 *   onType     'flipMode' 면 금액 칸에 글자를 치면 화면 스크립트가 「지정」인 금액의 뜻(amount_mode · pct_mode)을 「미정」으로 바꾼다
 *   windowFor  {부과금 번호: 다른 부과금 번호} — 서버가 그 부과금의 [편집] 에 다른 부과금의 창을 내준다(서버 결함 흉내)
 *   withAddon  true 면 부가옵션 가격 도우미(stay_addon_price.js)도 올린다(모듈을 통틀어 작업은 하나인지 볼 때)
 *   hotel · login · withScripts · withPage · bare   가격 도우미 받침과 같은 뜻(bare 면 아무것도 올리지 않는다 — 올리개 시험)
 */
export function chargePage(opts = {}) {
  const o = Object.assign({ tab: 'charges', charges: 'loaded', onSave: 'ok', withScripts: true, withPage: true }, opts);
  const db = copy(o.db || DB);
  const hotelId = (o.hotel && o.hotel.id) || HOTEL.id;
  const marks = o.hotel === null ? '' : hotelMarks(o.hotel || {});
  const tabs = TABS.map(([href, name, label]) => `<li class="tab"><a href="${href}"${name ? ` data-stay-tab="${name}"` : ''}${name === o.tab ? ' class="active"' : ''}><span>${label}</span></a></li>`).join('\n  ');
  const html = o.login ? '<form method="post" action="/accounts/login/"><input type="text" name="username"><input type="password" name="password"><button type="submit">로그인</button></form>'
    : `${marks}<ul class="tab_style1 tab-container">
  ${tabs}
</ul>${OTHER_PANES}
<div id="stay_tab_charges" class="col s12 stay-pane stay-root" ajax_loaded data-stay-tab="charges"${o.tab === 'charges' ? '' : ' style="display:none"'}>
${o.charges === 'stub' ? stub(hotelId) : panel(db, hotelId)}
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
  const dom = new JSDOM(html, { url: `https://erp.example.test/stay/${hotelId}/#stay_tab_charges`, runScripts: 'outside-only', pretendToBeVisual: true });
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
  const saveCharge = (save) => {
    const path = save.getAttribute('hx-post');
    const pairs = collect(save);
    log.posts.push({ path, pairs });
    const chargeId = /\/charges\/(\d+)\/edit\/$/.exec(path)[1];
    const { offer, charge } = chargeOf(db, chargeId);
    if (o.onSave === 'silent') {   // 요청은 끝나지만 화면은 그대로다(응답이 비었거나 htmx 가 버린 응답)
      fire('htmx:before:request', {});
      w.setTimeout(() => fire('htmx:finally:request', {}), 20);
      return;
    }
    const { errors, values, saved } = judge(db, offer, charge, pairs);
    const scopeError = ['refuse', 'late'].includes(o.onSave) ? '이 부과금의 객실 범위는 오퍼가 파는 객실 안이어야 합니다 — 저장하지 않았습니다' : '';
    if (o.onSave === 'late') {
      fire('htmx:before:request', {});
      w.setTimeout(() => {
        body.innerHTML = chargeWindow(db, hotelId, chargeId, { morph: morph(), values, errors, scopeError });
        fire('htmx:after:swap', {}); fire('htmx:after:settle', {}); wire(body);
        fire('htmx:finally:request', {});
      }, o.lateMs ?? 1500);
      return;
    }
    if (scopeError || Object.keys(errors).length) {   // 실패도 200 — 보낸 값으로 창을 다시 그린다(뿌리 id 가 새로 난다)
      swap(() => { body.innerHTML = chargeWindow(db, hotelId, chargeId, { morph: morph(), values, errors, scopeError }); return body; });
      return;
    }
    // 저장 — 시간대 · 연령별 단가는 지우고 보낸 것으로 다시 만든다(`services/charge.save_charge`)
    Object.assign(charge, saved);
    saves++;
    swap(() => {
      doc.getElementById('stay_offer_charges').outerHTML = panel(db, hotelId, { saved: true });
      body.replaceChildren();
      const mark = doc.getElementById('stay_save_result');
      mark.setAttribute('data-stay-result', 'saved');
      mark.setAttribute('data-stay-saved-at', `2026-11-21T10:00:00.${String(saves).padStart(3, '0')}+09:00`);
      closeDrawer();
      return doc.getElementById('stay_offer_charges');
    });
  };
  const AMOUNT_FIELDS = /^(amount|pct|onsite_amount|tiers_amount|tiers_pct|age_rate_\d+|onsite_age_rate_\d+)$/;
  doc.addEventListener('submit', (e) => { e.preventDefault(); });
  doc.addEventListener('input', (e) => {
    if (!e.target.closest('#stay_drawer_body')) return;
    log.typed.push(e.target.name);
    if (o.onType === 'flipMode' && AMOUNT_FIELDS.test(e.target.name)) {
      for (const mode of e.target.closest('[data-stay-screen]').querySelectorAll('select[name="amount_mode"], select[name="pct_mode"]')) {
        if (mode.value === 'set') mode.value = 'blank';
      }
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
    } else if (b.matches('tr[data-stay-entity="charge"] [data-stay-action="open_edit"]')) {
      const asked = b.closest('tr').getAttribute('data-stay-entity-id');
      const chargeId = (o.windowFor && o.windowFor[asked]) || asked;
      log.gets.push(b.getAttribute('hx-get'));
      swap(() => open(chargeWindow(db, hotelId, chargeId, { morph: morph() }), chargeTitle(db, chargeId)));
    } else if (b.matches('[data-stay-screen="charge"] [data-stay-action="save"]')) {
      saveCharge(b);
    } else if (b.matches('[hx-post]')) {
      log.posts.push({ path: b.getAttribute('hx-post') });   // 삭제 — 벽이 막았어야 하는 요청
    }
  });
  w.addEventListener('stay-drawer-close', closeDrawer);
  // 스텁의 hx-trigger load — 페이지가 뜨면 목록을 불러와 같은 id 로 갈아 끼운다(탭이 꺼져 있어도)
  const waiting = doc.querySelector('#stay_offer_charges:not([data-stay-panel])');
  if (waiting) {
    log.gets.push(waiting.getAttribute('hx-get'));
    w.setTimeout(() => swap(() => { waiting.outerHTML = panel(db, hotelId); return doc.getElementById('stay_offer_charges'); }), o.stubMs ?? 60);
  }
  w.localStorage.setItem('staySteps', RUNNER_STEPS);
  w.localStorage.setItem('stayRunCursor', RUNNER_CURSOR);
  if (!o.bare) {
    if (o.withScripts) { w.eval(HELPER); w.eval(BOOT); }
    if (o.withPage) w.eval(PAGE);
    if (o.withAddon) w.eval(ADDON);
    w.eval(CHARGE);
  }
  return {
    dom, w, doc, log, db, closeDrawer,
    drawerOpen: () => drawer.classList.contains('is-open'),
    // 저장 응답을 바꾼다(앞 저장은 그대로 두고 다음 저장부터) — onSave 와 같은 값
    answerSavesWith: (mode) => { o.onSave = mode; },
    charge: (id) => chargeOf(db, id).charge,
    // 드로어에 부과금 편집 창을 바로 그린다(벽 시험)
    showCharge: (chargeId) => { open(chargeWindow(db, hotelId, chargeId, { morph: morph() }), chargeTitle(db, chargeId)); wire(body); return body.firstElementChild; }
  };
}

const LEGACY = '객실: 기존 범위 그대로';
const OPTIONAL = '선택 항목 (고객이 고를 때만)';
// fixtures/erp/charges.json 이 그리는 목록 — 화면의 글자 그대로, 화면의 차례 그대로(오퍼는 번호 큰 것부터, 줄은 종류 · 번호 차례)
export const LISTED = [
  { id: '602', name: '데모 연말 오퍼', charges: [
    { id: '705', name: '연말 갈라 디너 (12/31 · 의무 · 연령별)', kind: '기타', basis: '정액',
      amount: ['100.00 USD', '인당', '연령별 단가: 유아 · 소아', '유아: 0.00 USD', '소아: 50.00 USD'],
      scope: `이 오퍼의 모든 객실 · ${LEGACY}`, dates: '의무 지정 1일 2026-12-31' },
    { id: '706', name: '공항 픽업 (금액 미정)', kind: '기타', basis: '정액', amount: ['미정', '체류당 1회'],
      scope: `이 오퍼의 모든 객실 · ${LEGACY}`, dates: OPTIONAL }] },
  { id: '601', name: '데모 오퍼 2027', charges: [
    { id: '702', name: '얼리 체크인 (07시부터 · 1박 요금의 30%)', kind: '얼리 체크인', basis: '1박 요금의 %',
      amount: ['00:00 ~ 06:59 · 1박 요금의 %: 100.00%', '07:00 ~ 12:00 · 1박 요금의 %: 30.00%', '체류당 1회'],
      scope: `이 오퍼의 모든 객실 · ${LEGACY}`, dates: OPTIONAL },
    { id: '701', name: '레이트 체크아웃 (14시 이후 · 1박 요금의 50%)', kind: '레이트 체크아웃', basis: '1박 요금의 %',
      amount: ['12:01 ~ 14:00 · 정액: 0.00 USD', '14:01 ~ 18:00 · 1박 요금의 %: 50.00%', '체류당 1회'],
      scope: `이 오퍼의 모든 객실 · ${LEGACY}`, dates: OPTIONAL },
    { id: '703', name: '크리스마스 갈라 디너 (12/24 · 의무 · 성인)', kind: '기타', basis: '정액', amount: ['90.00 USD', '인당'],
      scope: `디럭스 · ${LEGACY}`, dates: '의무 지정 1일 2026-12-24' },
    { id: '704', name: '현장 결제 리조트피', kind: '기타', basis: '정액', amount: ['0.00 USD', '체류당 1회', '현장 결제: 15.00 USD'],
      scope: `이 오퍼의 모든 객실 · ${LEGACY}`, dates: OPTIONAL }] }
];
export const rowOf = (id) => LISTED.flatMap((o) => o.charges).find((c) => c.id === id);
export const offerOfCharge = (id) => LISTED.find((o) => o.charges.some((c) => c.id === id)).id;

// 답의 조각을 take 로 자리(at)를 따라 모두 받아 잇는다
export function takeAll(w, result, size) {
  const meta = result.body;
  const takes = [];
  for (let at = 0; at < meta.chars;) {
    const piece = plain(size === undefined ? w.stayCharge.take(meta.id, at) : w.stayCharge.take(meta.id, at, size));
    if (!piece.ok) throw new Error(piece.error);
    takes.push(piece);
    at = piece.next;
  }
  const text = takes.map((t) => t.text).join('');
  return { takes, text, body: unpack(text) };
}
