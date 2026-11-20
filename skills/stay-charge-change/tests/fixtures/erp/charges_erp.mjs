// 부과금 화면의 손 조각 — 캡처가 없어 ERP 템플릿을 따라 손으로 그린다(데이터는 같은 폴더의 charges.json, 모두 지어낸 값).
//
// 따른 것(읽기만 했다, basecamp `stay/` 아래):
//   templates/stay/_section_offer_charges.html  부과금 탭의 지연 로딩 스텁 `#stay_offer_charges`(hx-get · hx-trigger load)
//   templates/stay/_charges_panel.html          목록 `#stay_offer_charges[data-stay-panel="charges"]` — 오퍼 카드 · 표 · 줄 버튼 · 저장 배너
//   templates/stay/_charge_form.html            편집 창 `[data-stay-screen="charge"]` — Alpine 이 돈 뒤의 모양(시간대 행은 `<template x-for>`
//                                               뒤에 그려진 `tr[data-stay-row]`, 템플릿 안에도 같은 행 마크업이 있다)
//   templates/stay/_scope_fields.html           적용 범위 카드 — 부과금은 객실 축 하나(`views/editor._charge_form_fragment`)
//   templates/stay/_saved_scope.html            목록의 「적용 범위」 칸
//   services/charge.py                          ChargeRow — 금액 칸 `amount_text`(`{:,.2f}`) · 오퍼 순서(-priority, -id) · 줄 순서(kind, id)
//   forms.py                                    ChargeEditForm · NativeSelectMixin · AgentMarkupMixin · stay_number_input — id `id_stay_<name>`,
//                                               `data-stay-field` · `data-stay-kind`, 필수 칸만 `data-stay-required="1"`, select 는
//                                               `browser-default`, 숫자 칸은 `type="text" inputmode="decimal"`(시간대 행만 템플릿이 그린
//                                               `type="number"`), 머리 글자를 쓰는 칸은 `aria-label`(templatetags stay_field_label)
//   views/editor.py                             드로어 제목 「부과금 편집 — <이름>」, 저장 단추 hx-post `/stay/<호텔>/charges/<번호>/edit/`
//
// 손으로 줄이거나 짐작한 곳(진짜 화면에서 먼저 볼 것):
//   - Alpine 이 돈 뒤의 DOM 은 짐작이다(jsdom 은 Alpine 을 돌리지 않는다). 시간대 행은 Alpine 이 템플릿 바로 뒤에 복제해 넣고 값은
//     x-model 이 넣는다고 보고 value 속성 · selected 로 그렸다. x-show 로 숨는 칸은 style="display: none;" 으로만 숨겼다.
//   - x-data 식은 짧게 줄였다. 도움말 문구 몇 개는 줄였다.
//   - 적용 룸(room_scope) 체크는 그 오퍼의 객실을 그 차례로 그렸다. ERP 의 후보는 호텔의 객실 카테고리 전부(이름 차례,
//     `services/charge.room_scope_queryset`)다 — 보내는 것은 켠 칸뿐이라 이 시험의 값은 같다.
//   - 오퍼 카드 머리의 오퍼 꼬리표(`_offer_tag.html`)는 그리지 않았다. 「컨펌 불가 시」 줄은 v1 기본값 글자로 적었다.
//   - 서버가 거절할 때의 오류 문구 가운데 숫자 형식 · 자릿수 문구는 지어냈다(폼의 다른 문구는 forms.py 그대로).

export const KINDS = [['0', '얼리 체크인'], ['1', '레이트 체크아웃'], ['9', '기타']];
export const BASES = [['0', '정액'], ['1', '1박 요금의 %']];
export const PERS = [['0', '체류당 1회'], ['1', '박당'], ['2', '인당']];
const VALUE_MODES = [['blank', '미정 (비움)'], ['set', '지정 (0 포함)']];
const DATE_MODES = [['optional', '선택 — 고객이 고를 때만 붙습니다'], ['mandatory', '의무 — 고객 선택 없이 자동으로 붙습니다']];
const SCOPE_MODES = [['0', '기존 범위 그대로'], ['1', '구조 적격 전체'], ['2', '지정한 대상만']];
const FALLBACK = '기본 시간으로 진행(해당 라인만 환불)';
const REQUIRED = '<span class="stay-required" style="color:var(--stay-blocking)" aria-label="필수">*</span>';
const alpineRequired = (cond) => `<span class="stay-required" style="color:var(--stay-blocking)" aria-label="필수" x-show="${cond}">*</span>`;

export const esc = (text) => String(text ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const attr = (name, value) => (value === null || value === undefined || value === '' ? '' : ` ${name}="${esc(value)}"`);
const labelOf = (options, value) => (options.find(([v]) => v === String(value)) || [, ''])[1];

// 부과금 하나와 그 오퍼
export function chargeOf(db, id) {
  for (const offer of db.offers) {
    const charge = offer.charges.find((c) => c.id === id);
    if (charge) return { offer, charge };
  }
  return null;
}
// 화면의 차례 — 오퍼는 (-priority, -id), 줄은 (kind, id)(`services/charge.build_charge_groups`). 우선순위는 데이터에 없어 같다고 본다
const byNumber = (a, b) => Number(a) - Number(b);
export const offersShown = (db) => [...db.offers].sort((a, b) => byNumber(b.id, a.id));
export const chargesShown = (offer) => [...offer.charges].sort((a, b) => a.kind - b.kind || byNumber(a.id, b.id));

// 장고 floatformat:2 · ChargeRow.amount_text 의 `{:,.2f}`
const two = (text) => { const [whole, part = ''] = String(text).split('.'); return `${whole}.${(part + '00').slice(0, 2)}`; };
const grouped = (text) => { const [whole, part] = two(text).split('.'); return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${part}`; };

// `_section_offer_charges.html` — 탭 pane 안의 스텁. 불러오면 같은 id 의 목록으로 갈린다
export function stub(hotelId) {
  return `<div id="stay_offer_charges" class="stay-root"
     hx-get="/stay/${hotelId}/charges/"
     hx-trigger="load, stay:rooms-changed from:body, stay:offers-changed from:body"
     hx-swap="outerHTML">
  <p>부과금을 불러오는 중…</p>
</div>`;
}

const hasAmount = (c) => c.amount !== null || c.pct !== null || c.tiers.some((t) => t.amount !== null || t.pct !== null);
const ageRatesOf = (offer, charge) => offer.bands.filter((b) => b.id in charge.ages || b.id in charge.onsite_ages)
  .map((b) => ({ band: b, amount: charge.ages[b.id] ?? '0.00', onsite: charge.onsite_ages[b.id] ?? null }));
const currencyCode = (db, id) => (db.currencies.find((c) => c.id === id) || {}).code || '';

// 목록 「금액」 칸 — `_charges_panel.html` 의 그 td 그대로
function amountCell(db, offer, c) {
  const cur = db.currency;
  const parts = [];
  if (!hasAmount(c)) {
    parts.push(`<span class="stay-money stay-money--empty">미정</span>`);
    if (c.mandatory) parts.push(`\n              <span class="stay-badge stay-badge--blocking">판매 차단</span>`);
  } else if (c.tiers.length) {
    for (const t of c.tiers) {
      const value = t.basis === 0 ? `${t.amount === null ? '미정' : two(t.amount)} ${cur}` : `${t.pct === null ? '미정' : two(t.pct)}%`;
      parts.push(`\n              <div>${t.from} ~ ${t.to} · ${labelOf(BASES, t.basis)}:\n                ${value}\n              </div>`);
    }
  } else {
    const text = [c.amount !== null ? grouped(c.amount) : null, c.pct !== null ? `${grouped(c.pct)}%` : null].filter(Boolean).join(' · ');
    parts.push(`\n              <span class="stay-money">${text}${c.basis === 0 ? ` ${cur}` : ''}</span>`);
  }
  parts.push(`\n              <br><small>${labelOf(PERS, c.per)}</small>`);
  const rates = ageRatesOf(offer, c);
  if (rates.length) {
    parts.push(`\n              <br><small class="stay-badge stay-badge--tinted">연령별 단가: ${rates.map((r) => esc(r.band.name || r.band.code)).join(' · ')}</small>`);
    parts.push(`\n              ${rates.map((r) => `<div>${esc(r.band.name || r.band.code)}: ${two(r.amount)} ${cur}</div>`).join('')}`);
  }
  if (c.onsite_currency) {
    const code = currencyCode(db, c.onsite_currency);
    parts.push(`\n              <div>현장 결제: ${c.onsite_amount ?? '미설정'} ${code}</div>`);
    parts.push(`\n              ${rates.filter((r) => r.onsite !== null).map((r) => `<div>${esc(r.band.name || r.band.code)} 현장 결제: ${r.onsite} ${code}</div>`).join('')}`);
  }
  return parts.join('');
}
// `_saved_scope.html` — 부과금은 객실 축 하나. 이름에 오퍼를 붙이지 않는다(`services/scope_display.scope_displays`)
function savedScope(offer, scope) {
  const name = (id) => (offer.rooms.find((r) => r.id === id) || { name: '삭제되었거나 이 호텔 밖의 대상' }).name;
  const explicit = scope.mode === '2';
  return `<div data-stay-saved-scope>
  <div><strong>객실</strong>: ${labelOf(SCOPE_MODES, scope.mode)}
    ${explicit ? `<br>포함: ${esc(scope.include.map(name).join(', ') || '없음 — 판매 대상 없음')}` : ''}
    ${scope.exclude.length ? `<br>제외${scope.mode === '0' ? ' (현재 미사용)' : ''}: ${esc(scope.exclude.map(name).join(', '))}` : ''}
    ${!explicit && scope.include.length ? `<br>저장된 포함 (현재 미사용): ${esc(scope.include.map(name).join(', '))}` : ''}
  </div>
</div>`;
}
const LEGACY = { mode: '0', include: [], exclude: [] };
const scopeOf = (c) => c.scope || LEGACY;

function row(db, hotelId, offer, c) {
  const perk = c.kind === 0 || c.kind === 1;
  const scope = scopeOf(c);
  const roomNames = offer.rooms.filter((r) => c.rooms.includes(r.id)).map((r) => r.name);
  const dates = c.mandatory
    ? `<span class="stay-badge stay-badge--tinted">의무</span>\n              ${c.dates.length ? `<small>지정 ${c.dates.length}일</small>\n              <br><small>${c.dates.join(', ')}</small>` : '<small>오퍼 전 기간</small>'}`
    : '<small>선택 항목 (고객이 고를 때만)</small>';
  const blocking = !hasAmount(c) && c.mandatory, dropped = !hasAmount(c) && !c.mandatory;
  return `
          <tr data-stay-entity="charge" data-stay-name="${esc(c.name)}" data-stay-entity-id="${c.id}">
            <td>
              ${esc(c.name)}
              ${c.description ? `<br><small>${esc(c.description)}</small>` : ''}
              <br><small>컨펌 불가 시: ${FALLBACK}</small>
              ${blocking ? `<span class="stay-cond stay-cond--restricted">
                <span class="stay-cond__icon" aria-hidden="true">&#8856;</span>
                의무 부과금에 금액이 없어 판매가 막힙니다.
              </span>` : dropped ? `<span class="stay-cond stay-cond--restricted">
                <span class="stay-cond__icon" aria-hidden="true">&#8856;</span>
                금액이 없어 고객이 고르면 오류가 납니다.
              </span>` : ''}
            </td>
            <td>
              <span class="stay-cond ${perk ? 'stay-cond--perk' : 'stay-cond--included'}">
                <span class="stay-cond__icon" aria-hidden="true">${perk ? '&#9813;' : '&#10003;'}</span>
                ${labelOf(KINDS, c.kind)}
              </span>
            </td>
            <td>${labelOf(BASES, c.basis)}</td>
            <td>${amountCell(db, offer, c)}
            </td>
            <td>
              ${scope.mode === '0' ? (roomNames.length ? esc(roomNames.join(', ')) : '<small>이 오퍼의 모든 객실</small>') : ''}
              ${savedScope(offer, scope)}
            </td>
            <td>
              ${dates}
            </td>
            <td class="td_actions">
              <div class="stay-actions">
              <button type="button" class="stay-btn stay-btn--ghost" data-stay-action="open_questions"
                      hx-get="/stay/${hotelId}/charges/${c.id}/questions/new/"
                      hx-target="#stay_drawer_body" hx-swap="innerHTML">
                정보 수집 폼
              </button>
              <button type="button" class="stay-btn stay-btn--ghost" data-stay-action="open_edit"
                      hx-get="/stay/${hotelId}/charges/${c.id}/edit/"
                      hx-target="#stay_drawer_body" hx-swap="innerHTML">
                편집
              </button>
              <button type="button" class="stay-btn stay-btn--danger" data-stay-action="delete"
                      title="이 부과금과 시간 티어를 함께 지웁니다 — 되돌릴 수 없고, 차단 조건은 없습니다(누르면 바로 지워집니다)"
                      hx-post="/stay/${hotelId}/charges/${c.id}/delete/"
                      hx-target="#stay_offer_charges" hx-swap="outerHTML"
                      hx-confirm="이 부과금을 삭제할까요? 시간 티어도 함께 지워집니다.">
                삭제
              </button>
              </div>
            </td>
          </tr>`;
}

function card(db, hotelId, offer) {
  const list = chargesShown(offer);
  const table = list.length ? `
    <div class="table1 stay-table-scroll">
      <table class="bs-table stay-table stay-aligned-table">
        <colgroup>
          <col style="width:22%"><col style="width:13%"><col style="width:12%"><col style="width:14%">
          <col style="width:13%"><col style="width:15%"><col style="width:11%">
        </colgroup>
        <thead>
          <tr>
            <th>이름</th>
            <th>종류</th>
            <th>부과 방식</th>
            <th>금액</th>
            <th>적용 범위</th>
            <th>적용 날짜</th>
            <th class="stay-column-center">액션</th>
          </tr>
        </thead>
        <tbody>${list.map((c) => row(db, hotelId, offer, c)).join('')}
        </tbody>
      </table>
    </div>` : `
    <p class="stay-description">부과금이 없습니다.</p>`;
  return `
  <div class="stay-card" data-stay-entity="offer" data-stay-name="${esc(offer.name)}" data-stay-entity-id="${offer.id}">
    <div class="stay-card__head">
      <h4 class="stay-card__title">${esc(offer.name)} </h4>
      <button type="button" class="stay-btn stay-btn--primary" data-stay-action="open_create"
              hx-get="/stay/${hotelId}/offers/${offer.id}/charges/new/"
              hx-target="#stay_drawer_body" hx-swap="innerHTML">
        부과금 추가
      </button>
    </div>
${table}
  </div>`;
}

// `_charges_panel.html` — saved 면 저장 배너, oob 면 드로어 저장의 응답(hx-swap-oob)
export function panel(db, hotelId, { saved = false, oob = false } = {}) {
  const offers = offersShown(db);
  return `<div id="stay_offer_charges" class="stay-root stay-readable" data-stay-panel="charges"${oob ? ' hx-swap-oob="true"' : ''}>
  <span hidden
        hx-get="/stay/${hotelId}/charges/"
        hx-trigger="stay:rooms-changed from:body, stay:offers-changed from:body"
        hx-target="#stay_offer_charges"
        hx-swap="outerHTML"></span>
${saved ? '\n  <div class="stay-banner stay-banner--ok" data-stay-result="saved"><span>저장했습니다.</span></div>\n' : ''}
  <div class="stay-panel-intro"><h4 class="stay-section-title">부과금</h4></div>
${offers.length ? offers.map((offer) => card(db, hotelId, offer)).join('\n') : '  <div class="stay-banner stay-banner--warning"><span>오퍼가 없습니다. 부과금은 오퍼에 매답니다.</span></div>'}
</div>`;
}

// ── 편집 창 ──

const select = (name, label, options, value, extra = '') => `<select name="${name}" class="browser-default"${label ? ` aria-label="${esc(label)}"` : ''} data-stay-field="${name}" data-stay-kind="select"${extra} id="id_stay_${name}">
  ${options.map(([v, text]) => `<option value="${esc(v)}"${String(value ?? '') === v ? ' selected' : ''}>${esc(text)}</option>`).join('\n  ')}
</select>`;
const error = (errors, name) => (errors[name] ? `<small class="error" data-stay-error-for="${name}">${esc(errors[name])}</small>` : '');
const number = (name, value, { label = '', placeholder = '', band = '' } = {}) => `<input type="text" name="${name}"${attr('value', value)} inputmode="decimal"${attr('placeholder', placeholder)}${attr('data-stay-band', band)}${attr('aria-label', label)} data-stay-field="${name}" data-stay-kind="number" id="id_stay_${name}">`;

// 편집 창이 그릴 값 — 저장된 부과금(GET) 그대로(`ChargeEditForm` 의 initial · tier_rows). 서버가 거절한 POST 는 보낸 값으로 다시 그린다
export function windowValues(charge) {
  const scope = scopeOf(charge);
  return {
    kind: String(charge.kind), name: charge.name, basis: String(charge.basis), per: String(charge.per),
    amount_mode: charge.amount === null ? 'blank' : 'set', amount: charge.amount ?? '',
    pct_mode: charge.pct === null ? 'blank' : 'set', pct: charge.pct ?? '',
    date_mode: charge.mandatory ? 'mandatory' : 'optional', date_scope: charge.dates.join(', '),
    rooms: [...charge.rooms], onsite_currency: charge.onsite_currency ?? '', onsite_amount: charge.onsite_amount ?? '',
    ages: { ...charge.ages }, onsite_ages: { ...charge.onsite_ages },
    tiers: charge.tiers.map((t) => ({ from: t.from, to: t.to, basis: String(t.basis), amount: t.amount ?? '', pct: t.pct ?? '' })),
    description: charge.description,
    scope: { mode: scope.mode, include: [...scope.include], exclude: [...scope.exclude], confirm: false }
  };
}

// 시간대 행 하나 — `<template x-for>` 안의 마크업(row 없음)과 Alpine 이 그려 낸 행(row = {index, 값})이 같은 틀이다
function tierRow(tier, index) {
  const drawn = !!tier;
  const t = tier || {};
  const v = (value) => (drawn ? attr('value', value) : '');
  const flat = drawn && t.basis !== '1', hide = ' style="display: none;"';
  return `
            <tr ${drawn ? `:data-stay-row="index" data-stay-row="${index}"` : ':data-stay-row="index"'}>
              <td>
                <dmc-datetime>
                  <input type="text" name="tiers_time_from" data-stay-col="time_from" x-model="tier.time_from"
                         x-on:blur="tier.time_from = $event.target.value"
                         input-format="time" data-date-format="H:i" data-form-control="time" data-lang="ko"
                         placeholder="14:00"${v(t.from)}>
                </dmc-datetime>
              </td>
              <td>
                <dmc-datetime>
                  <input type="text" name="tiers_time_to" data-stay-col="time_to" x-model="tier.time_to"
                         x-on:blur="tier.time_to = $event.target.value"
                         input-format="time" data-date-format="H:i" data-form-control="time" data-lang="ko"
                         placeholder="18:00"${v(t.to)}>
                </dmc-datetime>
              </td>
              <td>
                <select name="tiers_basis" class="browser-default" data-stay-col="basis" x-model="tier.basis">
                  ${BASES.map(([value, text]) => `<option value="${value}"${drawn && t.basis === value ? ' selected' : ''}>${text}</option>`).join('\n                  ')}
                </select>
              </td>
              <td>
                <input type="number" name="tiers_amount" step="0.01" min="0" data-stay-col="amount" x-model="tier.amount"
                       x-show="String(tier.basis) !== '1'"${v(t.amount)}${drawn && !flat ? hide : ''}>
                <small x-show="String(tier.basis) === '1'" style="color:var(--stay-text-tertiary)${drawn && flat ? '; display: none;' : ''}">—</small>
              </td>
              <td>
                <input type="number" name="tiers_pct" step="0.01" min="0" data-stay-col="pct" x-model="tier.pct"
                       x-show="String(tier.basis) === '1'"${v(t.pct)}${drawn && flat ? hide : ''}>
                <small x-show="String(tier.basis) !== '1'" style="color:var(--stay-text-tertiary)${drawn && !flat ? '; display: none;' : ''}">—</small>
              </td>
              <td>
                <button type="button" class="stay-btn stay-btn--ghost" data-stay-action="remove_row"
                        x-on:click="tiers.splice(index, 1)">삭제</button>
              </td>
            </tr>`;
}

// `_scope_fields.html` — 객실 축 하나(부과금에는 요금제 축이 없다)
function scopeCard(offer, scope, { scopeError = '' } = {}) {
  const boxes = (kind) => offer.rooms.map((r, i) => `
            <label class="check_form" style="display:inline-block;margin-right:12px">
              <input class="filled-in" type="checkbox" name="scope_room_${kind}"
                     data-stay-field="scope_room_${kind}" data-stay-kind="multicheck"
                     data-stay-options="rooms"
                     value="${r.id}" id="id_stay_scope_room_${kind}_${i}"
                     ${scope[kind].includes(r.id) ? 'checked' : ''}>
              <span for="id_stay_scope_room_${kind}_${i}">${esc(r.name)}</span>
            </label>`).join('') || '\n            <small>고를 수 있는 대상이 아직 없습니다.</small>';
  return `<div class="stay-card" data-stay-card="scope"
     x-data="{ modes: { room: '${scope.mode}' }, scopeIncludes: {}, narrowing(axis) { return this.modes[axis] !== '0' }, denying() { return Object.values(this.modes).some(mode => mode === '2') } }"
     x-init="syncScopePicks()" x-on:change="syncScopePicks()">
  <div class="stay-card__head">
    <h4 class="stay-section-title">적용 범위</h4>
  </div>
  <p>
    <small>한 번 골라 여러 객실·요금제에 걸고, 예외만 제외 목록에 둡니다. '기존 범위 그대로'는 지금까지 저장된 동작을 그대로 씁니다.</small>
  </p>
  ${scopeError ? `<p><small class="error" data-stay-error-for="scope">${esc(scopeError)}</small></p>` : ''}
  <div class="table1">
    <table class="bs-table stay-table">
      <colgroup><col style="width:16%"><col style="width:84%"></colgroup>
      <tbody>
        <tr>
          <th>객실 적용 범위</th>
          <td x-on:change="modes['room'] = $event.target.value">
            ${select('scope_room_mode', '객실 적용 범위', SCOPE_MODES, scope.mode)}
          </td>
        </tr>
        <tr x-show="modes['room'] === '2' || scopeIncludes['room'] || false">
          <th>포함</th>
          <td>
            <small x-show="modes['room'] !== '2'">포함 목록은 '지정한 대상만'에서 적용됩니다. 저장된 선택은 유지됩니다.</small>${boxes('include')}
          </td>
        </tr>
        <tr x-show="narrowing('room')">
          <th>제외</th>
          <td>${boxes('exclude')}
            <small>포함과 제외에 같은 대상이 있으면 제외가 이깁니다.</small>
          </td>
        </tr>
        <tr x-show="denying()">
          <th>확인 ${alpineRequired("Object.keys(modes).some(axis => modes[axis] === '2' && !scopeIncludes[axis])")}</th>
          <td>
            <label class="check_form">
              <input class="filled-in" type="checkbox" name="scope_confirm_deny_all"
                     data-stay-field="scope_confirm_deny_all" data-stay-kind="checkbox"
                     id="id_stay_scope_confirm_deny_all"
                     ${scope.confirm ? 'checked' : ''}>
              <span for="id_stay_scope_confirm_deny_all">범위를 비운 채 저장 (어디서도 판매하지 않음)</span>
            </label>
            <small>포함 목록을 비우면 이 항목은 아무 객실·요금제에서도 판매되지 않습니다.</small>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</div>`;
}

// `_charge_form.html` — 편집 창(드로어 안). morph 는 렌더마다 다른 뿌리 id 조각(morph_bust). errors 는 {칸 이름: 글}, 시간대 오류는
// errors.tiers, 폼 전체 오류는 nonField
export function chargeWindow(db, hotelId, chargeId, { morph = 'c1', values = null, errors = {}, nonField = '', scopeError = '' } = {}) {
  const { offer, charge } = chargeOf(db, chargeId);
  const v = values || windowValues(charge);
  const root = `stay_charge_form_${morph}`;
  const cur = db.currency;
  const amountLabel = cur ? `정액 금액 (${cur})` : '정액 금액';
  const tierJson = JSON.stringify(v.tiers.map((t) => ({ time_from: t.from, time_to: t.to, basis: /^\d+$/.test(t.basis) ? Number(t.basis) : t.basis, amount: t.amount, pct: t.pct })))
    .replace(/</g, '\\u003C').replace(/>/g, '\\u003E').replace(/&/g, '\\u0026');
  const rooms = offer.rooms.map((r, i) => `
              <label class="check_form" style="display:inline-block;margin-right:12px">
                <input class="filled-in" type="checkbox" name="room_scope"
                       data-stay-field="room_scope" data-stay-kind="multicheck"
                       value="${r.id}" id="id_stay_room_scope_${i}"
                       ${v.rooms.includes(r.id) ? 'checked' : ''}>
                <span for="id_stay_room_scope_${i}">${esc(r.name)}</span>
              </label>`).join('');
  const currencies = [['', '---------'], ...db.currencies.map((c) => [c.id, c.code])];
  const onsiteBands = offer.bands.map((b) => `
    <p><label data-stay-label-for="onsite_age_rate_${b.id}" for="id_stay_onsite_age_rate_${b.id}">${esc(b.name || b.code)}</label> ${number(`onsite_age_rate_${b.id}`, v.onsite_ages[b.id], { label: b.name || b.code, placeholder: '25.00', band: b.code })} <small class="error" data-stay-error-for="onsite_age_rate_${b.id}">${esc(errors[`onsite_age_rate_${b.id}`] || '')}</small><small>현장 단가: 비우면 성인가와 같음, 0은 무료</small></p>`).join('');
  // Alpine 이 x-show 를 푼 모양 — 연령별 단가가 있는데 인당 · 정액 · 시간대 없음이 아니면 안내 오류가 보인다(아니면 display: none)
  const hasAgeRates = Object.values(v.ages).some((value) => String(value ?? '').trim() !== '');
  const ageWarning = hasAgeRates && (v.per !== '2' || v.basis !== '0' || v.tiers.length > 0);
  const ageCards = offer.bands.length ? `
  <div class="stay-card" data-stay-card="age_rates" x-show="hasAgeRates || (String(per) === '2' && String(basis) === '0' && tiers.length === 0)" x-cloak>
    <div class="stay-card__head">
      <h4 class="stay-section-title">연령별 단가</h4>
    </div>
    <p>
      <small>비우면 위의 정액 금액(성인가)과 같습니다 — 0 을 넣으면 그 연령은 무료입니다. 성인·소아 단가가 다른 갈라디너 같은 계약에만 씁니다.</small>
      <small class="error" x-show="hasAgeRates && (String(per) !== '2' || String(basis) !== '0' || tiers.length > 0)"${ageWarning ? '' : ' style="display: none;"'}>입력된 연령별 단가가 있습니다. 인당·정액·시간 요율 없음으로 되돌리거나 아래 단가를 비워야 저장할 수 있습니다.</small>
    </p>
    <div class="table1">
      <table class="bs-table stay-table">
        <colgroup><col style="width:30%"><col style="width:24%"><col style="width:46%"></colgroup>
        <thead>
          <tr>
            <th>연령 구간</th>
            <th>나이</th>
            <th>1인 단가${cur ? ` (${cur})` : ''}</th>
          </tr>
        </thead>
        <tbody>${offer.bands.map((b) => `
          <tr>
            <th>${esc(b.name || b.code)}</th>
            <td><small>${esc(b.range)}</small></td>
            <td>
              ${number(`age_rate_${b.id}`, v.ages[b.id], { label: b.name || b.code, placeholder: '50000', band: b.code })}
              ${error(errors, `age_rate_${b.id}`)}
            </td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
  </div>
  <div class="stay-card" data-stay-card="age_rates" x-show="String(per) === '2' && String(basis) === '0' && tiers.length > 0" x-cloak>
    <div class="stay-card__head">
      <h4 class="stay-section-title">연령별 단가</h4>
    </div>
    <p>
      <small>아래 시간대별 요율 표에 행이 있어 연령별 단가를 쓸 수 없습니다 — 요율 행을 모두 지우면 이 자리에 연령별 단가 표가 다시 나옵니다.</small>
    </p>
  </div>` : `
  <div class="stay-card" data-stay-card="age_rates" x-show="String(per) === '2' && String(basis) === '0' && tiers.length === 0" x-cloak>
    <div class="stay-card__head">
      <h4 class="stay-section-title">연령별 단가</h4>
    </div>
    <p>
      <small>이 오퍼에 연령 구간이 없어 성인·소아 단가를 나눌 수 없습니다 — 오퍼 탭의 연령 구간에서 먼저 만드세요. 그때까지는 투숙 인원 전원이 위의 정액 금액으로 계산됩니다.</small>
    </p>
  </div>`;
  return `<div id="${root}" data-stay-screen="charge"
     x-data="{ mandatory: '${v.date_mode}' === 'mandatory', basis: '${v.basis}', per: '${v.per}', tiers: JSON.parse(document.getElementById('stay_charge_tier_rows_initial').textContent) || [], hasAgeRates: false, amountSet: false, pctSet: false, onsiteEntered: false, syncAgeRates() {} }" x-init="syncAgeRates()" x-on:input="syncAgeRates()" x-on:change="syncAgeRates()">
${nonField ? `\n  <div class="stay-banner stay-banner--blocking" data-stay-result="error"><span>${esc(nonField)}</span></div>\n` : ''}
  <div class="stay-card" data-stay-card="main">
    <div class="table1">
      <table class="bs-table stay-table">
        <colgroup><col style="width:16%"><col style="width:34%"><col style="width:16%"><col style="width:34%"></colgroup>
        <tbody>
          <tr>
            <th>종류 ${REQUIRED}</th>
            <td>${select('kind', '종류', KINDS, v.kind, ' data-stay-required="1" required')}${error(errors, 'kind')}</td>
            <th>이름 ${REQUIRED}</th>
            <td><input type="text" name="name"${attr('value', v.name)} maxlength="100" aria-label="이름" data-stay-field="name" data-stay-kind="text" data-stay-required="1" required id="id_stay_name">${error(errors, 'name')}</td>
          </tr>
          <tr>
            <th>부과 방식 ${REQUIRED}</th>
            <td x-on:change="basis = $event.target.value">${select('basis', '부과 방식', BASES, v.basis, ' data-stay-required="1" required')}<small>“1박 요금의 %”의 기준 밤은 위 [종류]가 정합니다 — “얼리 체크인”이면 첫날 밤, 그 외에는 마지막 밤 요금입니다.</small>${error(errors, 'basis')}</td>
            <th>부과 단위 ${REQUIRED}</th>
            <td x-on:change="per = $event.target.value">${select('per', '부과 단위', PERS, v.per, ' data-stay-required="1" required')}<small>금액에 곱해지는 수입니다 — 체류당 1회=객실마다 한 번 · 박당=객실마다 적용되는 박수만큼 · 인당=전체 투숙 인원수만큼.</small>${error(errors, 'per')}</td>
          </tr>
          <tr x-show="tiers.length === 0 && basis !== '1'">
            <th data-stay-label-for="amount_mode">${amountLabel} ${REQUIRED}</th>
            <td colspan="3">
              ${select('amount_mode', amountLabel, VALUE_MODES, v.amount_mode, ' data-stay-required="1" required')} <span x-show="amountSet || ${errors.amount ? 'true' : 'false'}">${alpineRequired('amountSet')} <input type="text" name="amount"${attr('value', v.amount)} inputmode="decimal" placeholder="${cur && cur !== 'KRW' ? '30.00' : '30000'}" data-stay-field="amount" data-stay-kind="number" id="id_stay_amount"></span>
              <small>“미정”은 금액을 정하지 않았다는 뜻입니다 — 0 원으로 저장하려면 “지정”을 고르고 0 을 넣으세요.</small>
              ${error(errors, 'amount_mode')}
              ${error(errors, 'amount')}
            </td>
          </tr>
          <tr x-show="tiers.length === 0 && basis === '1'">
            <th data-stay-label-for="pct_mode">정률(%) ${REQUIRED}</th>
            <td colspan="3">
              ${select('pct_mode', '정률(%)', VALUE_MODES, v.pct_mode, ' data-stay-required="1" required')} <span x-show="pctSet || ${errors.pct ? 'true' : 'false'}">${alpineRequired('pctSet')} <input type="text" name="pct"${attr('value', v.pct)} inputmode="decimal" placeholder="10" data-stay-field="pct" data-stay-kind="number" id="id_stay_pct"></span>
              ${error(errors, 'pct_mode')}
              ${error(errors, 'pct')}
            </td>
          </tr>
          <tr x-show="tiers.length > 0">
            <th>정액 · 정률</th>
            <td colspan="3">
              <small>아래 시간대별 요율 표가 대신 쓰입니다 — 표에 한 줄이라도 있으면 이 값은 계산에 안 쓰입니다. 표를 모두 지우면 이 칸이 다시 나옵니다.</small>
            </td>
          </tr>

          <tr>
            <th>부과 유형 ${REQUIRED}</th>
            <td colspan="3">
              <select name="date_mode" class="browser-default" aria-label="부과 유형"
                      data-stay-field="date_mode" data-stay-kind="select" data-stay-required="1"
                      x-on:change="mandatory = $event.target.value === 'mandatory'">
                ${DATE_MODES.map(([value, text]) => `<option value="${value}"${v.date_mode === value ? ' selected' : ''}>${text}</option>`).join('\n                ')}
              </select>
              <small>“의무”는 고객이 고르지 않아도 붙습니다 — 기본은 이 오퍼의 전 기간이고, 아래 날짜는 특정 날짜에만 붙일 때만 적습니다. 금액이 비어 있으면 판매가 차단됩니다.</small>
              ${error(errors, 'date_mode')}
            </td>
          </tr>
          <tr x-show="mandatory">
            <th>적용 날짜 (선택)</th>
            <td colspan="3">
              <textarea name="date_scope" cols="40" rows="2" placeholder="2026-12-24, 2026-12-31" aria-label="적용 날짜 (선택)" data-stay-field="date_scope" data-stay-kind="textarea" id="id_stay_date_scope">
${esc(v.date_scope)}</textarea>
              <small>YYYY-MM-DD 를 쉼표로 구분해 적습니다 (예: 2026-12-24, 2026-12-31).</small>
              ${error(errors, 'date_scope')}
            </td>
          </tr>

          <tr>
            <th>적용 룸 (선택)</th>
            <td colspan="3">${rooms}
              <small>비우면 이 오퍼의 모든 객실에 적용됩니다</small>
              ${error(errors, 'room_scope')}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="stay-card" data-stay-card="onsite">
    <h4 class="stay-section-title">현장 결제 안내</h4>
    <p><label data-stay-label-for="onsite_currency" for="id_stay_onsite_currency">현장 결제 통화 ${alpineRequired('onsiteEntered')}</label> ${select('onsite_currency', '현장 결제 통화', currencies, v.onsite_currency)} <small class="error" data-stay-error-for="onsite_currency">${esc(errors.onsite_currency || '')}</small></p>
    <p><label data-stay-label-for="onsite_amount" for="id_stay_onsite_amount">현장 결제 단가</label> ${number('onsite_amount', v.onsite_amount, { label: '현장 결제 단가' })} <small class="error" data-stay-error-for="onsite_amount">${esc(errors.onsite_amount || '')}</small><small>비우면 현장 금액 미정, 0이면 무료입니다. 온라인 요금에는 더하지 않습니다.</small></p>${onsiteBands}
  </div>${ageCards}
  <script id="stay_charge_tier_rows_initial" type="application/json">${tierJson}</script>
  <div class="stay-card" data-stay-card="tiers">
    <div class="stay-card__head">
      <h4 class="stay-section-title" data-stay-label-for="tiers">시간대별 요율</h4>
      <button type="button" class="stay-btn stay-btn--ghost" data-stay-action="add_row"
              x-on:click="tiers.push({ time_from: '', time_to: '', basis: '1', amount: '', pct: '' })">
        요율 행 추가
      </button>
    </div>
    ${errors.tiers ? `<div class="stay-banner stay-banner--blocking" data-stay-result="error"><span>${esc(errors.tiers)}</span></div>` : ''}
    <p>
      <small>한 줄이라도 채우면 위의 정액/정률 대신 이 표가 쓰입니다 — 얼리 체크인·레이트 체크아웃처럼 시각에 따라 요율이 갈릴 때만 씁니다.</small>
    </p>
    <div class="table1">
      <input type="hidden" name="tiers_submitted" value="1">
      <table class="bs-table stay-table" data-stay-field="tiers" data-stay-kind="rows" data-stay-rows="tiers">
        <colgroup>
          <col style="width:16%"><col style="width:16%"><col style="width:24%">
          <col style="width:18%"><col style="width:16%"><col style="width:10%">
        </colgroup>
        <thead>
          <tr>
            <th>시작 시각 ${alpineRequired('tiers.length > 0')}</th>
            <th>종료 시각 ${alpineRequired('tiers.length > 0')}</th>
            <th>부과 방식</th>
            <th>정액 금액${cur ? ` (${cur})` : ''} ${alpineRequired("tiers.some(tier => String(tier.basis) !== '1')")}</th>
            <th>정률(%) ${alpineRequired("tiers.some(tier => String(tier.basis) === '1')")}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <template x-for="(tier, index) in tiers" :key="index">${tierRow(null)}
          </template>${v.tiers.map((t, i) => tierRow(t, i)).join('')}
          <tr x-show="tiers.length === 0"${v.tiers.length ? ' style="display: none;"' : ''}>
            <td colspan="6">
              <small>시각에 따라 요율이 갈리지 않으면 비워 두세요 — 위의 정액/정률이 그대로 쓰입니다.</small>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="stay-card" data-stay-card="description">
    <div class="stay-card__head">
      <h4 class="stay-section-title" data-stay-label-for="description">설명</h4>
    </div>
    <textarea name="description" cols="40" rows="2" aria-label="설명" data-stay-field="description" data-stay-kind="textarea" id="id_stay_description">
${esc(v.description)}</textarea>
    ${error(errors, 'description')}
  </div>

  ${scopeCard(offer, v.scope, { scopeError })}

  <div class="stay-drawer__footer">
    <button type="button" class="stay-btn stay-btn--primary" data-stay-action="save"
            hx-post="/stay/${hotelId}/charges/${charge.id}/edit/"
            hx-include="#${root} :is(input,select,textarea)"
            hx-target="#stay_drawer_body" hx-swap="innerHTML"
            hx-disable="this">저장</button>
  </div>
</div>`;
}

// 편집 창 GET 의 드로어 제목(`views/editor.StayChargeEditView.get` — 「부과금 편집 — 부과금 이름」)
export function chargeTitle(db, chargeId) {
  return `부과금 편집 — ${chargeOf(db, chargeId).charge.name}`;
}
