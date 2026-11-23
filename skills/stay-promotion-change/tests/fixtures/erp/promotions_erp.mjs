// 프로모션 화면의 손 조각 — 캡처가 없어 ERP 템플릿을 따라 손으로 그린다(데이터는 같은 폴더의 promotions.json, 모두 지어낸 값).
//
// 따른 것(읽기만 했다, basecamp `stay/` 아래 — 화면 밖 설정을 지키는 고침 브랜치의 작업 사본):
//   templates/stay/_promotions_panel.html   목록 `#stay_promotions[data-stay-panel="promotions"]` — 카드(오퍼 표식 · 전 오퍼 공통은 표식 없음) ·
//                                           표 머리 여섯 칸 · 줄 버튼 · 저장 배너
//   templates/stay/_promotion_form.html     편집 창 `[data-stay-screen="promotion"]` — 뿌리 표식 `data-stay-keeps-off-form-keys="1"`, Alpine 이
//                                           돈 뒤의 단 줄(`<template x-for>` 뒤에 그려진 `tr[data-stay-row]`, 화면 밖 설정이 있는 줄만
//                                           `data-stay-off-form-keys`), 숨은 칸 `tiers_origin`, 뿌리 앞의 `#stay_promotion_tier_rows_initial`
//   templates/stay/_saved_scope.html        목록의 「한정」 칸의 적용 범위 줄
//   forms.py · services/promotion.py        PromotionEditForm(칸 · 고르기 글자) · promotion_initial · tier_rows · keep_off_form_keys
//   views/editor.py                         드로어 제목 「프로모션 편집 — <이름>」, 저장 단추 hx-post `/stay/<호텔>/promotions/<번호>/edit/`
//
// 손으로 줄이거나 짐작한 곳(진짜 화면에서 먼저 볼 것):
//   - Alpine 이 돈 뒤의 DOM 은 짐작이다(jsdom 은 Alpine 을 돌리지 않는다). 단 줄은 템플릿 바로 뒤에 복제해 넣고 값은 x-model 이 넣는다고
//     보고 value 속성으로 그렸다. 표식 `data-stay-off-form-keys` 는 `:data-stay-off-form-keys` 가 null 이면 속성이 없다고 보았다.
//   - 날짜 칸(StayDatePickerField)은 `type="text"` 에 `YYYY-MM-DD` 값으로, 고르기의 글자는 forms.py 의 choices 와 empty_label 로 그렸다.
//     적용 단위 글자(DiscountUnit.choices)와 적용 범위 축의 이름 · 차례(요금제 → 객실)는 짐작이다.
//   - 「예약기간 전 · 지남」 배지(오늘 날짜로 정해진다)는 그리지 않았다 — 데이터의 진행기간은 오늘을 품는다.
//   - 서버가 거절할 때의 오류 문구 몇 개는 줄였다.

export const TRIGGERS = [['ALWAYS', '상시 — 조건 없이 항상'], ['LOS', '연박 — N박 이상 묵으면'], ['LEAD_TIME', '얼리버드 — 체크인 D-N일 전에 예약하면'],
  ['ROOM_COUNT', '객실 수 — N개 이상 잡으면']];
export const BASES = [['PCT', '정률 — 요금의 %'], ['FLAT', '정액 — 금액을 뺀다'], ['FREE_NIGHT', '무료 숙박 — N박을 공짜로 (STAY5PAY4형)']];
export const UNITS = [['0', '박당'], ['1', '체류당 1회']];
export const VALUE_KEYS = { PCT: 'pct', FLAT: 'amount', FREE_NIGHT: 'free_nights' };
const THRESHOLD_LABELS = { LOS: '최소 숙박(박)', LEAD_TIME: '체크인 D-N일 전', ROOM_COUNT: '최소 객실 수', ALWAYS: '기준 없음' };
const SCOPE_MODES = [['0', '기존 범위 그대로'], ['1', '구조 적격 전체'], ['2', '지정한 대상만']];
export const COMMON = { id: '0', name: '전 오퍼 공통' };

export const esc = (text) => String(text ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const attr = (name, value) => (value === null || value === undefined || value === '' ? '' : ` ${name}="${esc(value)}"`);
const text = (value) => (value === null || value === undefined ? '' : String(value));

export const offerOf = (card) => card.offer || COMMON;
export function promotionOf(db, id) {
  for (const card of db.cards) for (const promotion of card.promotions) if (promotion.id === id) return { card, promotion };
  throw new Error(`없는 프로모션: ${id}`);
}
// 단의 화면 밖 설정의 이름 — 기준값과 저장된 혜택 방식의 값 키를 뺀 나머지(services/promotion._off_form)
export const offKeys = (promotion, tier) => Object.keys(tier).filter((key) => key !== 'threshold' && key !== VALUE_KEYS[promotion.trigger.basis]);

export function stub(hotelId) {
  return `<div id="stay_promotions" hx-get="/stay/${hotelId}/promotions/" hx-trigger="load" hx-swap="outerHTML"></div>`;
}

function benefitCell(db, promotion) {
  const { type, basis, tiers } = promotion.trigger;
  const lines = tiers.map((tier) => {
    const value = tier[VALUE_KEYS[basis]];
    const shown = basis === 'PCT' ? `${value}%` : basis === 'FLAT' ? `${value} ${db.currency}` : `${value}박 무료`;
    return `<div>\n${type !== 'ALWAYS' ? `<small>${esc(THRESHOLD_LABELS[type])} ${esc(tier.threshold)} →</small>\n` : ''}<span class="stay-money">\n${esc(shown)}\n</span>\n</div>`;
  });
  return lines.join('\n') + (tiers.length > 1 ? '\n<small>※ 만족하는 단 중 가장 높은 하나만 적용</small>' : '');
}

function triggerCell(type) {
  if (type === 'ALWAYS') return '<span class="stay-badge stay-badge--tinted">상시</span>\n<br><small>조건 없이 항상</small>';
  return `<span class="stay-badge stay-badge--tinted">${{ LOS: '연박', LEAD_TIME: '얼리버드', ROOM_COUNT: '객실 수' }[type]}</span>`;
}

function limitsCell(db, card, p) {
  const season = card.seasons.find((s) => s.id === p.season);
  const plan = db.rate_plans.find((r) => r.id === p.rate_plan);
  return (season ? `<small>시즌 ${esc(season.name)}</small><br>\n` : '')
    + '<div data-stay-saved-scope>\n  <div><strong>요금제</strong>: 기존 범위 그대로\n  </div>\n  <div><strong>객실</strong>: 기존 범위 그대로\n  </div>\n</div>\n'
    + (plan ? `<small>요금제 ${esc(plan.name)}</small><br>\n` : '')
    + (p.start || p.end ? `<small>숙박일 ${esc(p.start || '…')} ~ ${esc(p.end || '…')}</small>` : '<small>숙박일 제한 없음</small>')
    + (p.apply_flag ? `\n<br><small>예약일 ${esc(p.apply_start || '…')} ~ ${esc(p.apply_end || '…')}</small>` : '');
}

function row(db, hotelId, card, p) {
  const warn = p.apply_flag && !(p.apply_start && p.apply_end)
    ? '\n<div class="stay-cond stay-cond--restricted">\n<span class="stay-cond__icon">⊘</span>진행기간이 비어 있습니다. 후보에서 빠져 고객이 고르면 예약이 거부됩니다.\n</div>' : '';
  return `<tr data-stay-entity="promotion" data-stay-name="${esc(p.title)}" data-stay-entity-id="${p.id}">
  <td>
    <span class="stay-card__title">${esc(p.title)}</span>
    ${p.code ? `<br><small>${esc(p.code)}</small>` : ''}${warn}
  </td>
  <td>${triggerCell(p.trigger.type)}</td>
  <td>${benefitCell(db, p)}</td>
  <td>${p.combinability ? '<span class="stay-badge stay-badge--active">중복 가능</span>' : '<small>택일</small>'}${p.group ? `\n<br><small>배타 그룹 ${esc(p.group)}</small>` : ''}</td>
  <td>${limitsCell(db, card, p)}</td>
  <td class="td_actions">
    <div class="stay-actions">
    <button type="button" class="stay-btn stay-btn--ghost" data-stay-action="open_edit" hx-get="/stay/${hotelId}/promotions/${p.id}/edit/" hx-target="#stay_drawer_body" hx-swap="innerHTML">편집</button>
    <button type="button" class="stay-btn stay-btn--danger" data-stay-action="delete" hx-post="/stay/${hotelId}/promotions/${p.id}/delete/" hx-target="#stay_promotions" hx-swap="outerHTML" hx-confirm="이 프로모션을 삭제할까요? 되돌릴 수 없습니다.">삭제</button>
    </div>
  </td>
</tr>`;
}

function cardHtml(db, hotelId, card) {
  const offer = card.offer;
  const marks = offer ? ` data-stay-entity="offer" data-stay-name="${esc(offer.name)}" data-stay-entity-id="${offer.id}"` : '';
  const head = `<div class="stay-card__head">
      <h4 class="stay-card__title">${offer ? esc(offer.name) : '전 오퍼 공통'}</h4>
      <button type="button" class="stay-btn stay-btn--primary" data-stay-action="open_create" hx-get="/stay/${hotelId}/offers/${offer ? offer.id : 0}/promotions/new/" hx-target="#stay_drawer_body" hx-swap="innerHTML">프로모션 추가</button>
    </div>${offer ? '' : '\n    <p class="stay-description">오퍼를 지정하지 않은 할인이라 이 호텔의 모든 오퍼에 붙습니다.</p>'}`;
  const table = card.promotions.length ? `<div class="table1 stay-table-scroll">
      <table class="bs-table stay-table stay-aligned-table">
        <thead><tr><th>프로모션</th><th>발동 조건</th><th>혜택</th><th>중복</th><th>한정</th><th class="stay-column-center">액션</th></tr></thead>
        <tbody>
${card.promotions.map((p) => row(db, hotelId, card, p)).join('\n')}
        </tbody>
      </table>
    </div>` : `<p class="stay-description">${offer ? '프로모션이 없습니다.' : '전 오퍼 공통 프로모션이 없습니다.'}</p>`;
  return `<div class="stay-card"${marks}>\n    ${head}\n    ${table}\n  </div>`;
}

export function panel(db, hotelId, { saved = false } = {}) {
  return `<div id="stay_promotions" class="stay-root stay-readable" data-stay-panel="promotions">
  <span hidden hx-get="/stay/${hotelId}/promotions/" hx-trigger="stay:offers-changed from:body" hx-target="#stay_promotions" hx-swap="outerHTML"></span>
  ${saved ? '<div class="stay-banner stay-banner--ok" data-stay-result="saved"><span>저장했습니다.</span></div>' : ''}
  <div class="stay-panel-intro"><h4 class="stay-section-title">프로모션</h4></div>
  ${db.cards.map((card) => cardHtml(db, hotelId, card)).join('\n  ')}
</div>`;
}

const select = (name, label, options, value, extra = '') => `<select name="${name}" class="browser-default"${label ? ` aria-label="${esc(label)}"` : ''} data-stay-field="${name}" data-stay-kind="select"${extra} id="id_stay_${name}">
${options.map(([v, l]) => `  <option value="${esc(v)}"${String(v) === String(value) ? ' selected' : ''}>${esc(l)}</option>`).join('\n')}
</select>`;
const textInput = (name, value, extra = '') => `<input type="text" name="${name}"${attr('value', value)} data-stay-field="${name}" data-stay-kind="text" id="id_stay_${name}"${extra}>`;
const checkbox = (name, on, label) => `<label class="check_form">
  <input class="filled-in" type="checkbox" name="${name}" data-stay-field="${name}" data-stay-kind="checkbox" id="id_stay_${name}"${on ? ' checked' : ''}>
  <span for="id_stay_${name}">${esc(label)}</span>
</label>`;
const error = (errors, name) => (errors[name] ? `<small class="error" data-stay-error-for="${name}">${esc(errors[name])}</small>` : '');

// 편집 창이 다시 그리는 값 — 저장된 프로모션에서(PromotionEditForm 의 initial · tier_rows)
export function windowValues(promotion) {
  const t = promotion.trigger;
  return {
    title: promotion.title, code: promotion.code, trigger_type: t.type, basis: t.basis, unit: String(promotion.unit),
    tiers: t.tiers.map((tier) => ({ threshold: text(tier.threshold), value: text(tier[VALUE_KEYS[t.basis]]), origin: text(tier.threshold), off: offKeys(promotion, tier) })),
    start: promotion.start, end: promotion.end, apply_flag: promotion.apply_flag, apply_start: promotion.apply_start, apply_end: promotion.apply_end,
    season: text(promotion.season), rate_plan: text(promotion.rate_plan), combinability: promotion.combinability, group: promotion.group,
    policy: text(promotion.policy)
  };
}

function tierRow(tier, index, keeps) {
  const off = keeps && tier.off.length ? ` data-stay-off-form-keys="${esc(tier.off.join(' '))}"` : '';
  return `<tr data-stay-row="${index}"${off}>
              <td>
                ${keeps ? `<input type="hidden" name="tiers_origin" value="${esc(tier.origin)}">` : ''}
                <input type="number" name="tiers_threshold" step="1" min="0" data-stay-col="threshold" aria-label="기준값"${attr('value', tier.threshold)}>
              </td>
              <td><input type="number" name="tiers_value" step="0.01" min="0" data-stay-col="value" aria-label="값"${attr('value', tier.value)}></td>
              <td><button type="button" class="stay-btn stay-btn--ghost" data-stay-action="remove_row">삭제</button></td>
            </tr>`;
}

/**
 * 편집 창 하나 — 저장된 프로모션(또는 거절한 POST 의 값 `values`)을 Alpine 이 그린 뒤의 모양으로. `keeps` 가 false 면 표식 · 숨은 칸 ·
 * 단 목록의 origin/off_form_keys 가 없는 예전 ERP 의 창이다.
 */
export function promotionWindow(db, hotelId, promotionId, { morph = 'p1', values = null, errors = {}, nonField = '', keeps = true } = {}) {
  const { card, promotion } = promotionOf(db, promotionId);
  const v = values || windowValues(promotion);
  const offer = offerOf(card);
  const seasons = [['', '(전 시즌)'], ...card.seasons.map((s) => [s.id, `${offer.name} · ${s.name}`])];
  const plans = [['', '(전 요금제)'], ...db.rate_plans.map((r) => [r.id, r.name])];
  const policies = [['', '(요금제·오퍼 정책을 따름)'], ...db.policies.map((p) => [p.id, p.name])];
  const initial = v.tiers.map((t) => (keeps ? { threshold: t.threshold, value: t.value, origin: t.origin, off_form_keys: t.off } : { threshold: t.threshold, value: t.value }));
  const id = `stay_promotion_form_${morph}`;
  return `<script id="stay_promotion_tier_rows_initial" type="application/json">${JSON.stringify(initial).replace(/</g, '\\u003C')}</script>
<div id="${id}" data-stay-screen="promotion"${keeps ? ' data-stay-keeps-off-form-keys="1"' : ''} x-data="{ tiers: [], trigger: '${v.trigger_type}', basis: '${v.basis}' }">
  ${nonField ? `<div class="stay-banner stay-banner--blocking" data-stay-result="error"><span>${esc(nonField)}</span></div>` : ''}
  <div class="stay-card" data-stay-card="main">
    <div class="table1"><table class="bs-table stay-table"><tbody>
      <tr><th>프로모션명</th><td>${textInput('title', v.title, ' maxlength="200" required')}${error(errors, 'title')}</td></tr>
      <tr><th>코드</th><td>${textInput('code', v.code, ' maxlength="64"')}<small>계약서·채널 연동에서 이 할인을 가리키는 약칭입니다. 비워도 됩니다.</small></td></tr>
      <tr><th>발동 조건</th><td>${select('trigger_type', '발동 조건', TRIGGERS, v.trigger_type, ' data-stay-required="1" x-model="trigger"')}</td></tr>
      <tr><th>혜택 방식</th><td>${select('basis', '혜택 방식', BASES, v.basis, ' data-stay-required="1" x-model="basis"')}</td></tr>
      <tr><th>적용 단위</th><td>${select('unit', '', UNITS, v.unit, ' data-stay-required="1"')}</td></tr>
    </tbody></table></div>
  </div>
  <div class="stay-card" data-stay-card="tiers">
    <div class="stay-card__head">
      <h4 class="stay-section-title" data-stay-label-for="tiers">할인 단계</h4>
      <button type="button" class="stay-btn stay-btn--ghost" data-stay-action="add_row">단 추가</button>
    </div>
    ${errors.tiers ? `<div class="stay-banner stay-banner--blocking" data-stay-result="error"><span>${esc(errors.tiers)}</span></div>` : ''}
    <div class="table1">
      <input type="hidden" name="tiers_submitted" value="1">
      <table class="bs-table stay-table" data-stay-field="tiers" data-stay-kind="rows" data-stay-rows="tiers" data-stay-required="1">
        <thead><tr><th><span>기준값</span></th><th><span>값</span></th><th></th></tr></thead>
        <tbody>
          <template x-for="(tier, index) in tiers" :key="index">
            <tr :data-stay-row="index"><td>${keeps ? '<input type="hidden" name="tiers_origin" :value="tier.origin || \'\'">' : ''}<input type="number" name="tiers_threshold" x-model="tier.threshold"></td><td><input type="number" name="tiers_value" x-model="tier.value"></td><td><button type="button" data-stay-action="remove_row">삭제</button></td></tr>
          </template>
          ${v.tiers.map((t, i) => tierRow(t, i, keeps)).join('\n          ')}
          <tr style="display: none;"><td colspan="3"><small>단이 없으면 고객이 이 할인을 고르는 순간 예약이 실패합니다 — 최소 한 단은 넣으세요.</small></td></tr>
        </tbody>
      </table>
    </div>
  </div>
  <div class="stay-card" data-stay-card="scope_and_combination">
    <div class="table1"><table class="bs-table stay-table"><tbody>
      <tr><th>적용 숙박일 시작</th><td>${textInput('start_date', v.start)}</td><th>적용 숙박일 종료</th><td>${textInput('end_date', v.end)}${error(errors, 'end_date')}</td></tr>
      <tr><th>진행기간 제한</th><td colspan="3">${checkbox('promotion_apply_flag', v.apply_flag, '이 기간에 예약한 건만')}</td></tr>
      <tr${v.apply_flag ? '' : ' style="display: none;"'}><th>진행기간 시작</th><td>${textInput('promotion_apply_start_date', v.apply_start)}${error(errors, 'promotion_apply_start_date')}</td>
        <th>진행기간 종료</th><td>${textInput('promotion_apply_end_date', v.apply_end)}${error(errors, 'promotion_apply_end_date')}</td></tr>
      <tr><th>시즌 한정</th><td>${select('season', '', seasons, v.season)}</td><th>요금제 한정</th><td>${select('rate_plan', '', plans, v.rate_plan)}</td></tr>
      <tr><th>다른 프로모션과 중복 적용</th><td>${checkbox('combinability', v.combinability, '중복 허용')}</td><th>배타 그룹</th><td>${textInput('exclusivity_group', v.group, ' maxlength="64"')}</td></tr>
      <tr><th>프로모션 전용 취소 정책</th><td colspan="3">${select('cancellation_policy', '', policies, v.policy)}</td></tr>
    </tbody></table></div>
  </div>
  <div class="stay-card" data-stay-card="scope">
    <div class="stay-card__head"><h4 class="stay-section-title">적용 범위</h4></div>
    <div class="table1"><table class="bs-table stay-table"><tbody>
      <tr><th>요금제 범위</th><td>${select('scope_rate_plan_mode', '', SCOPE_MODES, '0')}</td></tr>
      <tr style="display: none;"><th>요금제 포함</th><td><label class="check_form"><input class="filled-in" type="checkbox" name="scope_rate_plan_include" value="41"><span>디럭스 · 조식 포함</span></label></td></tr>
      <tr><th>객실 범위</th><td>${select('scope_room_mode', '', SCOPE_MODES, '0')}</td></tr>
      <tr style="display: none;"><th>객실 포함</th><td><label class="check_form"><input class="filled-in" type="checkbox" name="scope_room_include" value="51"><span>디럭스</span></label></td></tr>
    </tbody></table>
    <label class="check_form" style="display: none;"><input class="filled-in" type="checkbox" name="scope_confirm_deny_all" value="1"><span>판매 대상 없음을 확인합니다</span></label></div>
  </div>
  <div class="erp_cont_head"><div class="erp_cont_head_right">
    <button type="button" class="stay-btn stay-btn--primary" data-stay-action="save" hx-post="/stay/${hotelId}/promotions/${promotionId}/edit/" hx-include="#${id} :is(input,select,textarea)" hx-target="#stay_drawer_body" hx-swap="innerHTML" hx-disable="this">저장</button>
  </div></div>
</div>`;
}

export const promotionTitle = (db, id) => `프로모션 편집 — ${promotionOf(db, id).promotion.title}`;
