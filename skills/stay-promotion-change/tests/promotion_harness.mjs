// 프로모션 페이지 시험의 받침 — jsdom 위에 ERP Stay 편집 화면(탭 · 호텔 표식 · 프로모션 탭 · 드로어)을 세우고, 러너의 도우미 · 부트,
// 가격 도우미 `stay_price.js`, 이 스킬의 `stay_promotion.js` 를 그대로 올린다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
//
// 화면은 손 조각이다(`fixtures/erp/promotions_erp.mjs` 가 ERP 템플릿을 따라 그린다 · 데이터는 `fixtures/erp/promotions.json`, 모두 지어낸 값).
// 가짜 서버는 문서에 붙인 클릭 듣개다 — 벽(window 캡처 단계)이 막은 클릭은 여기 닿지 않으므로 `log.reached` 가 증거다. 저장 단추를
// 받으면 그 단추의 `hx-include` 고르개를 문서에 그대로 걸어 보낼 칸을 모으고(`log.posts[].pairs`), `PromotionEditForm` 처럼 검사해
// 저장하거나(화면 밖 설정을 지키는 ERP 면 행이 불러온 저장 단의 설정을 잇고, 목록을 저장 배너와 함께 다시 그리고 드로어를 닫고
// `#stay_save_result` 의 저장 시각을 바꾼다) 오류와 함께 창을 다시 그린다. htmx 4 처럼 htmx 단추는 연결돼야(`data-htmx-powered`) 눌린다.
//
// 가격 도우미의 받침(`stay-price-change/tests/page_harness.mjs`)에서 jsdom 찾기 · 러너 파일 · 호텔 표식 · 값 넘기기 · 조각 풀기를
// 빌린다(그 파일은 고치지 않는다).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadJsdom, HELPER, BOOT, PAGE, LOADER, HOTEL, RUNNER_STEPS, RUNNER_CURSOR, hotelMarks, inPage, plain, charsOf, unpack } from '../../stay-price-change/tests/page_harness.mjs';
import { panel, stub, promotionWindow, promotionTitle, promotionOf, windowValues, offKeys, VALUE_KEYS } from './fixtures/erp/promotions_erp.mjs';

export { HELPER, BOOT, PAGE, LOADER, HOTEL, RUNNER_STEPS, RUNNER_CURSOR, inPage, plain, charsOf };
const JSDOM = loadJsdom();

export const HERE = dirname(fileURLToPath(import.meta.url));
export const SKILL = join(HERE, '..');
export const PROMOTION = readFileSync(join(SKILL, 'scripts', 'page', 'stay_promotion.js'), 'utf8');
export const CHARGE = readFileSync(join(SKILL, '..', 'stay-charge-change', 'scripts', 'page', 'stay_charge.js'), 'utf8');
export const DB = Object.freeze(JSON.parse(readFileSync(join(HERE, 'fixtures', 'erp', 'promotions.json'), 'utf8')));
export const ORIGIN_UNKNOWN = '이 프로모션의 편집 창은 ERP 가 할인 단 줄이 어느 저장된 단에서 왔는지 모르는 상태라(앞선 저장이 거절된 뒤 다시 그려진 창), 저장하면 화면에 안 보이는 설정이 다른 단에 붙거나 빠질 수 있어 도우미가 저장하지 않습니다 — ERP 에서 그 프로모션의 편집 창을 닫았다가 다시 열어 주시면 다시 해 보겠습니다';
export const GATE = '이 ERP 는 아직 프로모션을 화면으로 저장하면 화면에 안 보이는 설정이 지워질 수 있어, 도우미가 저장하지 않습니다 — ERP 가 고쳐진 뒤에 됩니다';
const copy = (value) => JSON.parse(JSON.stringify(value));

const HTMX = ['action', 'get', 'post', 'put', 'patch', 'delete'].map((v) => `[hx-${v}],[data-hx-${v}]`).join(',');
const wire = (root) => { if (root) [root, ...root.querySelectorAll(HTMX)].filter((el) => el.matches(HTMX)).forEach((el) => el.setAttribute('data-htmx-powered', 'true')); };

export const TABS = [['#baseinfo', null, '기본정보'], ['#stay_tab_offers', 'offers', '오퍼'], ['#stay_tab_calendar', 'calendar', '가격 캘린더'],
  ['#stay_tab_charges', 'charges', '부과금'], ['#stay_tab_addons', 'addons', '부가옵션'], ['#stay_tab_promotions', 'promotions', '프로모션']];
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
const same = (a, b) => DEC.test(String(a)) && DEC.test(String(b)) && Number(a) === Number(b);

// 보낸 칸을 `PromotionEditForm` 처럼 읽고 검사한다(이 시험에 걸리는 규칙만) — {errors, values(다시 그릴 값), saved(저장할 프로모션)}
function judge(db, card, promotion, pairs, keeps) {
  const get = (n) => { const hit = pairs.find(([k]) => k === n); return hit ? hit[1] : ''; };
  const every = (n) => pairs.filter(([k]) => k === n).map(([, v]) => v);
  const errors = {};
  if (!get('title').trim()) errors.title = '필수 항목입니다.';
  const type = get('trigger_type'), basis = get('basis');
  if (!VALUE_KEYS[basis]) errors.basis = '올바르게 선택해 주세요.';
  const thresholds = every('tiers_threshold'), values = every('tiers_value'), origins = every('tiers_origin');
  const rows = thresholds.map((t, i) => ({ threshold: t.trim(), value: (values[i] || '').trim(), origin: keeps ? (origins[i] || '') : null }))
    .filter((r) => r.threshold || r.value);
  rows.forEach((r, i) => {
    if (errors.tiers) return;
    if (!/^\d+$/.test(r.threshold)) errors.tiers = `${i + 1}번째 단의 기준값은 정수여야 합니다`;
    else if (!DEC.test(r.value)) errors.tiers = `${i + 1}번째 단의 값은 0 이상이어야 합니다`;
    else if (basis === 'PCT' && Number(r.value) > 100) errors.tiers = `${i + 1}번째 단의 할인율은 0~100 사이여야 합니다`;
    else if (basis === 'FREE_NIGHT' && !/^\d+(\.0+)?$/.test(r.value)) errors.tiers = `${i + 1}번째 단의 무료 숙박은 박 단위 정수여야 합니다`;
  });
  if (!rows.length) errors.tiers = '최소 한 단은 있어야 합니다';
  if (!errors.tiers && type === 'ALWAYS' && rows.some((r) => Number(r.threshold) !== 0)) errors.tiers = '‘상시’ 는 기준값을 보지 않습니다';
  if (!errors.tiers && new Set(rows.map((r) => Number(r.threshold))).size !== rows.length) errors.tiers = '기준값이 같은 단이 둘 이상입니다';
  const flag = every('promotion_apply_flag').length > 0;
  if (flag && !get('promotion_apply_start_date')) errors.promotion_apply_start_date = '진행기간 제한을 켜면 시작일이 필요합니다';
  if (flag && !get('promotion_apply_end_date')) errors.promotion_apply_end_date = '진행기간 제한을 켜면 종료일이 필요합니다';
  const values_ = Object.assign(windowValues(promotion), {
    title: get('title'), code: get('code'), trigger_type: type, basis, unit: get('unit'),
    tiers: rows.map((r) => ({ threshold: r.threshold, value: r.value, origin: r.origin || '', off: [] })),
    start: get('start_date'), end: get('end_date'), apply_flag: flag, apply_start: get('promotion_apply_start_date'),
    apply_end: get('promotion_apply_end_date'), season: get('season'), rate_plan: get('rate_plan'),
    combinability: every('combinability').length > 0, group: get('exclusivity_group'), policy: get('cancellation_policy')
  });
  // 저장 — 할인 규칙을 다시 만들고, 지키는 ERP 는 행이 불러온 저장 단의 화면 밖 설정과 같은 숫자의 저장된 표기를 잇는다
  const stored = promotion.trigger, oldKey = VALUE_KEYS[stored.basis], key = VALUE_KEYS[basis];
  const tiers = rows.map((r) => {
    const out = { threshold: Number(r.threshold) };
    out[key] = basis === 'FREE_NIGHT' ? Number(r.value) : r.value;
    const source = keeps && r.origin ? stored.tiers.find((t) => String(t.threshold) === r.origin) : null;
    if (source) {
      if (key === oldKey && same(source[key], r.value)) out[key] = source[key];
      for (const name of offKeys(promotion, source)) if (!(name in out)) out[name] = source[name];
    }
    return out;
  });
  const saved = {
    title: get('title'), code: get('code'), unit: Number(get('unit')),
    trigger: { type, basis, unit: get('unit') === '1' ? 'PER_STAY' : 'PER_NIGHT', tiers },
    combinability: every('combinability').length > 0, group: get('exclusivity_group'), season: get('season') || null,
    rate_plan: get('rate_plan') || null, start: get('start_date'), end: get('end_date'), apply_flag: flag,
    apply_start: get('promotion_apply_start_date'), apply_end: get('promotion_apply_end_date'), policy: get('cancellation_policy') || null
  };
  return { errors, values: values_, saved };
}

/**
 * ERP 한 장. `opts`:
 *   tab          처음 켜진 탭(기본 'promotions') — 'calendar' 면 [프로모션] 탭을 눌러야 목록이 보인다
 *   promotions   'loaded'(기본) | 'stub'(스텁만 있고, stubMs(기본 60ms) 뒤에 목록이 온다)
 *   db           promotions.json 대신 쓸 데이터(복사해 쓴다)
 *   keeps        false 면 화면 밖 설정을 지키지 않는 예전 ERP — 표식 · 숨은 칸이 없고 저장이 그 설정을 지운다(기본은 데이터의 keeps)
 *   onSave       'ok'(기본) | 'refuse'(늘 창 맨 위 오류로 다시 그린다 — 글은 refusal, 기본은 적용 범위 오류) | 'silent'(요청은
 *                끝나지만 아무것도 바뀌지 않는다) | 'late'(요청이 lateMs(기본 1500ms) 동안 돌다가 'refuse' 처럼 거절된 창을 드로어
 *                몸통에 넣는다 — 드로어가 닫혀 있어도. ERP 는 거절에 드로어를 다시 열지 않는다)
 *   refusal      'refuse' 일 때 창 맨 위 오류의 글(ERP 가 단을 짚어 거절하는 글 — services/promotion_trigger.keep_off_form_keys)
 *   windowFor    {프로모션 번호: 다른 번호} — 서버가 그 프로모션의 [편집] 에 다른 프로모션의 창을 내준다(서버 결함 흉내)
 *   withCharge   true 면 부과금 도우미(stay_charge.js)도 올린다(모듈을 통틀어 작업은 하나인지 볼 때)
 *   hotel · login · withScripts · withPage · bare   가격 도우미 받침과 같은 뜻
 */
export function promotionPage(opts = {}) {
  const o = Object.assign({ tab: 'promotions', promotions: 'loaded', onSave: 'ok', withScripts: true, withPage: true }, opts);
  const db = copy(o.db || DB);
  const keeps = () => (o.keeps === undefined ? db.keeps !== false : o.keeps);
  const hotelId = (o.hotel && o.hotel.id) || HOTEL.id;
  const marks = o.hotel === null ? '' : hotelMarks(o.hotel || {});
  const tabs = TABS.map(([href, name, label]) => `<li class="tab"><a href="${href}"${name ? ` data-stay-tab="${name}"` : ''}${name === o.tab ? ' class="active"' : ''}><span>${label}</span></a></li>`).join('\n  ');
  const html = o.login ? '<form method="post" action="/accounts/login/"><input type="text" name="username"><input type="password" name="password"><button type="submit">로그인</button></form>'
    : `${marks}<ul class="tab_style1 tab-container">
  ${tabs}
</ul>${OTHER_PANES}
<div id="stay_tab_promotions" class="col s12 stay-pane stay-root" data-stay-tab="promotions"${o.tab === 'promotions' ? '' : ' style="display:none"'}>
${o.promotions === 'stub' ? stub(hotelId) : panel(db, hotelId)}
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
  const dom = new JSDOM(html, { url: `https://erp.example.test/stay/${hotelId}/#stay_tab_promotions`, runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window, doc = w.document;
  wire(doc.body);
  const drawer = doc.querySelector('.stay-drawer'), body = doc.getElementById('stay_drawer_body'), title = doc.querySelector('.stay-drawer__title');
  const log = { reached: [], gets: [], posts: [], typed: [], dead: [] };
  let morphs = 0, saves = 0;
  const morph = () => `m${++morphs}`;
  const fire = (name, detail) => doc.dispatchEvent(new w.CustomEvent(name, { detail, bubbles: true }));
  const swap = (apply) => {
    fire('htmx:before:request', {});
    const root = apply();
    fire('htmx:after:swap', {}); fire('htmx:after:settle', {}); wire(root);
    fire('htmx:finally:request', {});
  };
  const open = (fragment, heading = '') => { body.innerHTML = fragment; title.textContent = heading; drawer.classList.add('is-open'); return body; };
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
  const collect = (save) => [...doc.querySelectorAll(save.getAttribute('hx-include'))].flatMap((el) => {
    if (!el.name || el.matches(':disabled')) return [];
    if (el.type === 'checkbox' || el.type === 'radio') return el.checked ? [[el.name, el.value]] : [];
    if (el.localName === 'select' && el.multiple) return [...el.selectedOptions].map((op) => [el.name, op.value]);
    return [[el.name, el.value]];
  });
  const windowOf = (promotionId, extra = {}) => {
    if (o.origin !== undefined && !extra.values) {   // 손으로 지은 줄 — 거절된 요청 뒤 다시 그린 창처럼 첫 단 줄의 tiers_origin 이 o.origin(「?」)
      const values = windowValues(promotionOf(db, promotionId).promotion);
      values.tiers = values.tiers.map((tier, i) => (i === 0 ? Object.assign({}, tier, { origin: o.origin }) : tier));
      extra = Object.assign({}, extra, { values });
    }
    return promotionWindow(db, hotelId, promotionId, Object.assign({ morph: morph(), keeps: keeps() }, extra));
  };
  const savePromotion = (save) => {
    const path = save.getAttribute('hx-post');
    const pairs = collect(save);
    log.posts.push({ path, pairs });
    const promotionId = /\/promotions\/(\d+)\/edit\/$/.exec(path)[1];
    const { card, promotion } = promotionOf(db, promotionId);
    if (o.onSave === 'silent') {
      fire('htmx:before:request', {});
      w.setTimeout(() => fire('htmx:finally:request', {}), 20);
      return;
    }
    const { errors, values, saved } = judge(db, card, promotion, pairs, keeps());
    const nonField = ['refuse', 'late'].includes(o.onSave) ? (o.refusal || '이 프로모션의 적용 범위가 맞지 않습니다 — 저장하지 않았습니다') : '';
    if (o.onSave === 'late') {
      fire('htmx:before:request', {});
      w.setTimeout(() => {
        body.innerHTML = windowOf(promotionId, { values, errors, nonField });
        fire('htmx:after:swap', {}); fire('htmx:after:settle', {}); wire(body);
        fire('htmx:finally:request', {});
      }, o.lateMs ?? 1500);
      return;
    }
    if (nonField || Object.keys(errors).length) {
      swap(() => { body.innerHTML = windowOf(promotionId, { values, errors, nonField }); return body; });
      return;
    }
    Object.assign(promotion, saved);
    saves++;
    swap(() => {
      doc.getElementById('stay_promotions').outerHTML = panel(db, hotelId, { saved: true });
      body.replaceChildren();
      const mark = doc.getElementById('stay_save_result');
      mark.setAttribute('data-stay-result', 'saved');
      mark.setAttribute('data-stay-saved-at', `2026-11-23T10:00:00.${String(saves).padStart(3, '0')}+09:00`);
      closeDrawer();
      return doc.getElementById('stay_promotions');
    });
  };
  doc.addEventListener('submit', (e) => { e.preventDefault(); });
  doc.addEventListener('input', (e) => { if (e.target.closest('#stay_drawer_body')) log.typed.push(e.target.name); });
  doc.addEventListener('click', (e) => {
    const b = e.target.closest('button, a, input, label, select');
    if (!b) return;
    log.reached.push(nameOf(b));
    if (b.matches(HTMX) && !b.hasAttribute('data-htmx-powered')) { log.dead.push(nameOf(b)); return; }
    if (b.matches('ul.tab-container a')) {
      doc.querySelectorAll('ul.tab-container a').forEach((a) => a.classList.toggle('active', a === b));
      doc.querySelectorAll('.stay-pane').forEach((pane) => { pane.style.display = pane.getAttribute('data-stay-tab') === b.getAttribute('data-stay-tab') ? '' : 'none'; });
    } else if (b.matches('tr[data-stay-entity="promotion"] [data-stay-action="open_edit"]')) {
      const asked = b.closest('tr').getAttribute('data-stay-entity-id');
      const promotionId = (o.windowFor && o.windowFor[asked]) || asked;
      log.gets.push(b.getAttribute('hx-get'));
      swap(() => open(windowOf(promotionId), promotionTitle(db, promotionId)));
    } else if (b.matches('[data-stay-screen="promotion"] [data-stay-action="save"]')) {
      savePromotion(b);
    } else if (b.matches('[hx-post]')) {
      log.posts.push({ path: b.getAttribute('hx-post') });   // 삭제 — 벽이 막았어야 하는 요청
    }
  });
  w.addEventListener('stay-drawer-close', closeDrawer);
  const waiting = doc.querySelector('#stay_promotions:not([data-stay-panel])');
  if (waiting) {
    log.gets.push(waiting.getAttribute('hx-get'));
    w.setTimeout(() => swap(() => { waiting.outerHTML = panel(db, hotelId); return doc.getElementById('stay_promotions'); }), o.stubMs ?? 60);
  }
  w.localStorage.setItem('staySteps', RUNNER_STEPS);
  w.localStorage.setItem('stayRunCursor', RUNNER_CURSOR);
  if (!o.bare) {
    if (o.withScripts) { w.eval(HELPER); w.eval(BOOT); }
    if (o.withPage) w.eval(PAGE);
    if (o.withCharge) w.eval(CHARGE);
    w.eval(PROMOTION);
  }
  return {
    dom, w, doc, log, db, closeDrawer,
    drawerOpen: () => drawer.classList.contains('is-open'),
    answerSavesWith: (mode) => { o.onSave = mode; },
    setKeeps: (value) => { o.keeps = value; },
    setOrigin: (value) => { o.origin = value; },
    promotion: (id) => promotionOf(db, id).promotion,
    showPromotion: (promotionId) => { open(windowOf(promotionId), promotionTitle(db, promotionId)); wire(body); return body.querySelector('[data-stay-screen="promotion"]'); }
  };
}

// promotions.json 이 그리는 목록 — 화면의 글자 그대로, 화면의 차례 그대로(데이터의 카드 차례)
export const LISTED = [
  { id: '602', name: '데모 연말 오퍼', promotions: [
    { id: '9007', title: '연말 얼리버드 31일 전 10%', code: '', trigger: '얼리버드', benefit: ['체크인 D-N일 전 31 → 10%'], combo: ['택일'],
      limits: ['시즌 연말 성수기', '요금제: 기존 범위 그대로', '객실: 기존 범위 그대로', '요금제 디럭스 · 조식 포함', '숙박일 2026-12-20 ~ 2027-01-05'], warnings: [] }] },
  { id: '601', name: '데모 오퍼 2027', promotions: [
    { id: '9002', title: '롱스테이 2박 7% / 3박 10%', code: '', trigger: '연박',
      benefit: ['최소 숙박(박) 2 → 7%', '최소 숙박(박) 3 → 10%', '※ 만족하는 단 중 가장 높은 하나만 적용'], combo: ['택일', '배타 그룹 DEMO-PROMO'],
      limits: ['요금제: 기존 범위 그대로', '객실: 기존 범위 그대로', '숙박일 제한 없음'], warnings: [] },
    { id: '9003', title: '상시 정액 할인', code: 'FLAT-20', trigger: '상시 · 조건 없이 항상', benefit: ['20 USD'], combo: ['택일'],
      limits: ['요금제: 기존 범위 그대로', '객실: 기존 범위 그대로', '숙박일 제한 없음'], warnings: [] },
    { id: '9004', title: '4박 이상이면 1박 무료', code: '', trigger: '연박', benefit: ['최소 숙박(박) 4 → 1박 무료'], combo: ['택일'],
      limits: ['요금제: 기존 범위 그대로', '객실: 기존 범위 그대로', '숙박일 제한 없음'], warnings: [] },
    { id: '9005', title: '얼리버드 46일 15% 환불 불가 / 31일 10% 컷오프', code: '', trigger: '얼리버드',
      benefit: ['체크인 D-N일 전 46 → 15.0%', '체크인 D-N일 전 31 → 10.0%', '※ 만족하는 단 중 가장 높은 하나만 적용'], combo: ['택일'],
      limits: ['요금제: 기존 범위 그대로', '객실: 기존 범위 그대로', '숙박일 제한 없음'], warnings: [] }] },
  { id: '0', name: '전 오퍼 공통', promotions: [
    { id: '9006', title: '전 오퍼 공통 상시 5%', code: 'ALL-5', trigger: '상시 · 조건 없이 항상', benefit: ['5%'], combo: ['중복 가능', '배타 그룹 DEMO-ALL'],
      limits: ['요금제: 기존 범위 그대로', '객실: 기존 범위 그대로', '숙박일 제한 없음', '예약일 2026-11-01 ~ 2027-02-28'], warnings: [] }] }
];
export const offerOfPromotion = (id) => LISTED.find((o) => o.promotions.some((p) => p.id === id)).id;

// 답의 조각을 take 로 자리(at)를 따라 모두 받아 잇는다
export function takeAll(w, result, size) {
  const meta = result.body;
  const takes = [];
  for (let at = 0; at < meta.chars;) {
    const piece = plain(size === undefined ? w.stayPromotion.take(meta.id, at) : w.stayPromotion.take(meta.id, at, size));
    if (!piece.ok) throw new Error(piece.error);
    takes.push(piece);
    at = piece.next;
  }
  const text = takes.map((t) => t.text).join('');
  return { takes, text, body: unpack(text) };
}
