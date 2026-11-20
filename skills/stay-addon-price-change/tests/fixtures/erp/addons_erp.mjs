// 부가옵션 화면의 손 조각 — 캡처가 없어 ERP 템플릿을 따라 손으로 그린다(데이터는 같은 폴더의 addons.json, 모두 지어낸 값).
//
// 따른 템플릿(읽기만 했다, basecamp `stay/templates/stay/` 아래):
//   _section_addons.html   부가옵션 탭의 지연 로딩 스텁 `#stay_addons`(hx-get · hx-trigger load)
//   _addons_panel.html     목록 `#stay_addons[data-stay-panel="addons"]` — 카드 · 메타 표 · 가격 표 · 줄 버튼 · 저장 배너
//   _addon_price_form.html 가격 편집 창 `[data-stay-screen="addon-price"]` — 카드 main · coordinates · description · 저장 단추
//   _scope_fields.html     적용 범위 카드 `[data-stay-card="scope"]` — 축마다 모드 select · 포함/제외 체크 · 확인 체크
//   _saved_scope.html      목록의 「적용 범위」 칸
//   _addon_form.html       부가옵션 설정 창 `[data-stay-screen="addon"]` — 뿌리와 저장 단추만(벽 시험의 과녁)
// 칸 표식은 `stay/forms.py`(NativeSelectMixin · AgentMarkupMixin · StayAddonPriceForm · StayScopeForm)와 `stay/agent_markup.py` 의
// 규칙을 따른다: id `id_stay_<name>`, `data-stay-field` · `data-stay-kind` · 필수 칸만 `data-stay-required="1"`, select 는
// `browser-default`, 숫자 칸은 `type="text" inputmode="decimal"`, 머리 글자는 `aria-label` 로도 심긴다(stay_field_label).
//
// 손으로 줄이거나 지어낸 곳(화면에서 확인해야 할 것): Alpine 의 x-data 식은 짧게 줄였다(jsdom 은 Alpine 을 돌리지 않는다).
// 날짜 픽커의 바깥 틀(`stay/widgets/_picker_input.html`)은 따랐지만 공용 위젯이 더하는 속성은 모른다. 요금제 select 는 평평한
// 목록이다(ERP 는 연결 룸이 없는 부가옵션에서 정본별 optgroup 으로 묶는다). 오류 문구 가운데 형식 오류 두 개는 지어냈다.
// 값 줄(통화별 금액)의 차례는 판매가 → 공급 원가로 두었다(facts-extras-data.md 1절의 차례).

const MODES = [['0', '기존 범위 그대로'], ['1', '구조 적격 전체'], ['2', '지정한 대상만']];
const APPLY = {
  0: { label: '1회 적용 (박수·날짜와 무관)', chip: '' },
  1: { label: '날짜연동 (박수 따라감 — 엑스트라베드)', chip: '<span class="stay-cond stay-cond--included">\n          <span class="stay-cond__icon" aria-hidden="true">&#10003;</span>\n          날짜연동\n        </span>' },
  2: { label: '일자선택 (원하는 날만 — 조식)', chip: '<span class="stay-cond stay-cond--perk">\n          <span class="stay-cond__icon" aria-hidden="true">&#9813;</span>\n          일자선택\n        </span>' }
};
const REQUIRED = '<span class="stay-required" style="color:var(--stay-blocking)" aria-label="필수">*</span>';
const LEGACY = { mode: '0', include: [], exclude: [] };

export const esc = (text) => String(text ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const attr = (name, value) => (value === null || value === undefined || value === '' ? '' : ` ${name}="${esc(value)}"`);

export const addonOf = (db, id) => db.addons.find((a) => a.id === id);
export function lineOf(db, id) {
  for (const addon of db.addons) {
    const line = addon.lines.find((l) => l.id === id);
    if (line) return { addon, line };
  }
  return null;
}
const scopeOf = (line) => ({ rate_plan: (line.scope && line.scope.rate_plan) || LEGACY, room: (line.scope && line.scope.room) || LEGACY });
const offerName = (db, id) => (db.offers.find((o) => o.id === id) || {}).name || '';
// 축의 후보 — 요금제 축은 호텔 전체 요금제, 객실 축은 그 오퍼의 객실(`StayScopeForm` · `services/scope.target_queryset`)
function targets(db, axis, offer) {
  if (axis === 'rate_plan') return db.rate_plans.map((p) => ({ id: p.id, name: p.name }));
  return db.rooms.filter((r) => r.offer === offer).map((r) => ({ id: r.id, name: `${offerName(db, r.offer)} · ${r.name}` }));
}
// 목록 「통화별 금액」 칸의 값 줄 — 보이는 값 줄이 없으면 「별도 금액 없음」
function valueRows(db, line) {
  const rows = [];
  if (line.sell_row) rows.push(['판매가', line.price]);
  if (line.net !== null && line.net !== undefined) rows.push(['공급 원가', line.net]);
  return rows.map(([label, amount]) => `<div>${label}: ${esc(amount)} ${db.currency}</div>`).join('') || '<small>별도 금액 없음</small>';
}
// 「적용 대상」 — 시즌 · 날짜 · 요금제를 ` · ` 로 잇고, 없으면 「전체」(`services/addon._price_scope_label`)
function scopeLabel(db, line) {
  const parts = [];
  if (line.season) parts.push(db.seasons.find((s) => s.id === line.season).name);
  if (line.date) parts.push(line.date);
  if (line.rate_plan) parts.push(db.rate_plans.find((p) => p.id === line.rate_plan).name);
  return esc(parts.join(' · ') || '전체');
}
// `_saved_scope.html`
function savedScope(db, scope, offer) {
  const axes = [['rate_plan', '요금제'], ['room', '객실']].map(([axis, label]) => {
    const state = scope[axis];
    const mode = MODES.find(([v]) => v === state.mode)[1];
    const names = (ids) => ids.map((id) => (targets(db, axis, offer).find((t) => t.id === id) || { name: '삭제되었거나 이 호텔 밖의 대상' }).name);
    const explicit = state.mode === '2';
    return `
  <div><strong>${label}</strong>: ${mode}
    ${explicit ? `<br>포함: ${esc(names(state.include).join(', ') || '없음 — 판매 대상 없음')}` : ''}
    ${state.exclude.length ? `<br>제외${state.mode === '0' ? ' (현재 미사용)' : ''}: ${esc(names(state.exclude).join(', '))}` : ''}
    ${!explicit && state.include.length ? `<br>저장된 포함 (현재 미사용): ${esc(names(state.include).join(', '))}` : ''}
  </div>`;
  }).join('');
  return `<div data-stay-saved-scope>${axes}\n</div>`;
}

// `_section_addons.html` — 탭 pane 안의 스텁. 불러오면 같은 id 의 목록으로 갈린다
export function stub(hotelId) {
  return `<div id="stay_addons" class="stay-root"
     hx-get="/stay/${hotelId}/addons/"
     hx-trigger="load, stay:rooms-changed from:body, stay:offers-changed from:body"
     hx-swap="outerHTML">
  <p>부가옵션을 불러오는 중…</p>
</div>`;
}

function priceRow(db, hotelId, addon, line) {
  return `
          <tr data-stay-entity="addon_price" data-stay-name="${esc(line.name)}" data-stay-entity-id="${line.id}">
            <td>${esc(line.name || '—')}${line.description ? `<br><small>${esc(line.description)}</small>` : ''}</td>
            <td class="stay-numeric">${esc(line.price)} ${db.currency}</td>
            <td>${valueRows(db, line)}</td>
            <td>${scopeLabel(db, line)}</td>
            <td>${savedScope(db, scopeOf(line), addon.offer)}<small>부가옵션 범위와 모두 일치하는 대상에만 적용</small></td>
            <td>전체</td>
            <td class="td_actions">
              <div class="stay-actions">
              <button type="button" class="stay-btn stay-btn--ghost" data-stay-action="open_edit"
                      hx-get="/stay/${hotelId}/addon-prices/${line.id}/edit/"
                      hx-target="#stay_drawer_body" hx-swap="innerHTML">
                편집
              </button>
              <button type="button" class="stay-btn stay-btn--danger" data-stay-action="delete"
                      title="이 금액 줄만 지웁니다 — 부가옵션 자체는 남습니다"
                      hx-post="/stay/${hotelId}/addon-prices/${line.id}/delete/"
                      hx-target="#stay_addons" hx-swap="outerHTML"
                      hx-confirm="이 가격을 삭제할까요?">
                삭제
              </button>
              </div>
            </td>
          </tr>`;
}

function card(db, hotelId, addon) {
  const prices = addon.lines.length ? `
    <div class="table1 stay-addon__prices stay-table-scroll">
      <table class="bs-table stay-table stay-aligned-table">
        <colgroup><col style="width:16%"><col style="width:12%"><col style="width:14%"><col style="width:14%"><col style="width:24%"><col style="width:8%"><col style="width:12%"></colgroup>
        <thead>
          <tr>
            <th>가격행 이름</th>
            <th class="stay-numeric">판매가</th>
            <th>통화별 금액</th>
            <th>적용 대상</th>
            <th>적용 범위</th>
            <th>인원 밴드</th>
            <th class="stay-column-center">액션</th>
          </tr>
        </thead>
        <tbody>${addon.lines.map((line) => priceRow(db, hotelId, addon, line)).join('')}
        </tbody>
      </table>
    </div>` : `
    <p class="stay-description">가격이 없어 고객 화면에 팔리지 않습니다.</p>`;
  return `
  <div class="stay-card stay-addon" data-stay-entity="addon" data-stay-name="${esc(addon.name)}" data-stay-entity-id="${addon.id}">
    <div class="stay-card__head">
      <div class="stay-addon__ident">
        <h4 class="stay-addon__name">${esc(addon.name)}</h4>
        ${APPLY[addon.date_apply].chip}
      </div>
      <span class="stay-addon__actions">
        <button type="button" class="stay-btn stay-btn--primary" data-stay-action="open_create"
                title="이 부가옵션의 금액 줄을 하나 더 만듭니다 — 시즌·날짜·요금제마다 금액이 다르면 줄을 나눠 넣습니다"
                hx-get="/stay/${hotelId}/addons/${addon.id}/prices/new/"
                hx-target="#stay_drawer_body" hx-swap="innerHTML">
          가격 추가
        </button>
        <button type="button" class="stay-btn stay-btn--ghost" data-stay-action="open_questions"
                hx-get="/stay/${hotelId}/addons/${addon.id}/questions/new/"
                hx-target="#stay_drawer_body" hx-swap="innerHTML">
          정보 수집 폼
        </button>
        <button type="button" class="stay-btn stay-btn--ghost" data-stay-action="open_edit"
                hx-get="/stay/${hotelId}/addons/${addon.id}/edit/"
                hx-target="#stay_drawer_body" hx-swap="innerHTML">
          편집
        </button>
        <button type="button" class="stay-btn stay-btn--danger" data-stay-action="delete"
                title="이 부가옵션과 아래 가격 줄을 통째로 지웁니다 — 막는 조건이 없어 누르면 바로 지워지고 되돌릴 수 없습니다"
                hx-post="/stay/${hotelId}/addons/${addon.id}/delete/"
                hx-target="#stay_addons" hx-swap="outerHTML"
                hx-confirm="이 부가옵션을 삭제할까요? 등록된 가격도 함께 지워집니다.">
          삭제
        </button>
      </span>
    </div>

    <div class="table1 stay-addon__meta">
      <table class="bs-table stay-table stay-aligned-table">
        <colgroup><col style="width:16%"><col style="width:34%"><col style="width:16%"><col style="width:34%"></colgroup>
        <tbody>
          <tr>
            <th>적용 방식</th>
            <td>${APPLY[addon.date_apply].label}</td>
            <th>화면 섹션</th>
            <td>—</td>
          </tr>
          <tr>
            <th>연결 룸</th>
            <td>${esc(addon.room ? db.rooms.find((r) => r.id === addon.room).name : '—')}</td>
            <th>인원 밴드</th>
            <td>전체</td>
          </tr>
          <tr>
            <th>오퍼</th>
            <td>${addon.offer ? esc(offerName(db, addon.offer)) : '<small>미지정</small>'}</td>
            <th>기존 요금제 (미사용)</th>
            <td><small>미설정</small></td>
          </tr>
          <tr>
            <th>수량 상한</th>
            <td>${esc(addon.max_quantity ?? '—')}</td>
            <th>무료 제공 수량</th>
            <td>${esc(addon.foc_quantity ?? '—')}</td>
          </tr>
          <tr><th>적용 범위</th><td colspan="3">${savedScope(db, { rate_plan: LEGACY, room: LEGACY }, addon.offer)}</td></tr>
          <tr><th>고객 안내</th><td colspan="3">없음</td></tr>
          <tr><th>옵션 유형</th><td>선택</td><th>정렬</th><td>미설정</td></tr>
        </tbody>
      </table>
    </div>

    <h5 class="stay-addon__sub">가격</h5>${prices}
  </div>`;
}

// `_addons_panel.html` — saved 면 저장 배너, oob 면 드로어 저장의 응답(hx-swap-oob)
export function panel(db, hotelId, { saved = false, oob = false } = {}) {
  return `<div id="stay_addons" class="stay-root stay-readable" data-stay-panel="addons"${oob ? ' hx-swap-oob="true"' : ''}>
  <span hidden
        hx-get="/stay/${hotelId}/addons/"
        hx-trigger="stay:rooms-changed from:body, stay:offers-changed from:body"
        hx-target="#stay_addons"
        hx-swap="outerHTML"></span>
${saved ? '\n  <div class="stay-banner stay-banner--ok" data-stay-result="saved"><span>저장했습니다.</span></div>\n' : ''}
  <div class="stay-card stay-panel-intro">
    <div class="stay-card__head">
      <h4 class="stay-section-title">부가옵션 ${db.addons.length}건</h4>
      <span>
        ${db.has_offers ? `<button type="button" class="stay-btn stay-btn--primary" data-stay-action="open_create"
                hx-get="/stay/${hotelId}/addons/new/"
                hx-target="#stay_drawer_body" hx-swap="innerHTML">
          부가옵션 추가
        </button>` : ''}
      </span>
    </div>
    <p class="stay-description">엑스트라베드처럼 투숙 박수를 따라가는 항목은 [날짜연동], 조식처럼 고객이 먹는 날만 고르는 항목은 [일자선택]으로 만듭니다. 금액은 부가옵션을 만든 뒤 카드 안에서 <span class="stay-action-guide__btn stay-action-guide__btn--primary">가격 추가</span>로 채웁니다.</p>
  </div>
${db.addons.map((addon) => card(db, hotelId, addon)).join('\n')}
</div>`;
}

const select = (name, label, options, value, extra = '') => `<select name="${name}" class="browser-default" aria-label="${esc(label)}" data-stay-field="${name}" data-stay-kind="select"${extra} id="id_stay_${name}">
  ${options.map(([v, text]) => `<option value="${esc(v)}"${String(value ?? '') === v ? ' selected' : ''}>${esc(text)}</option>`).join('\n  ')}
</select>`;
const error = (errors, name) => (errors[name] ? `<small class="error" data-stay-error-for="${name}">${esc(errors[name])}</small>` : '');

// `_scope_fields.html` — 값은 { rate_plan: {mode, include, exclude}, room: {…}, confirm }
function scopeCard(db, offer, scope, { scopeError = '' } = {}) {
  const rows = [['rate_plan', '요금제 적용 범위', 'rate_plans'], ['room', '객실 적용 범위', 'rooms']].map(([axis, label, source]) => {
    const state = scope[axis];
    const boxes = (kind) => targets(db, axis, offer).map((t, i) => `
            <label class="check_form" style="display:inline-block;margin-right:12px">
              <input class="filled-in" type="checkbox" name="scope_${axis}_${kind}"
                     data-stay-field="scope_${axis}_${kind}" data-stay-kind="multicheck"
                     data-stay-options="${source}"
                     value="${t.id}" id="id_stay_scope_${axis}_${kind}_${i}"
                     ${state[kind].includes(t.id) ? 'checked' : ''}>
              <span for="id_stay_scope_${axis}_${kind}_${i}">${esc(t.name)}</span>
            </label>`).join('') || '\n            <small>고를 수 있는 대상이 아직 없습니다.</small>';
    return `
        <tr>
          <th>${label}</th>
          <td x-on:change="modes['${axis}'] = $event.target.value">
            ${select(`scope_${axis}_mode`, label, MODES, state.mode)}
          </td>
        </tr>
        <tr x-show="modes['${axis}'] === '2' || scopeIncludes['${axis}'] || false">
          <th>포함</th>
          <td>
            <small x-show="modes['${axis}'] !== '2'">포함 목록은 '지정한 대상만'에서 적용됩니다. 저장된 선택은 유지됩니다.</small>${boxes('include')}
          </td>
        </tr>
        <tr x-show="narrowing('${axis}')">
          <th>제외</th>
          <td>${boxes('exclude')}
            <small>포함과 제외에 같은 대상이 있으면 제외가 이깁니다.</small>
          </td>
        </tr>`;
  }).join('');
  return `<div class="stay-card" data-stay-card="scope"
     x-data="{ modes: { rate_plan: '${scope.rate_plan.mode}', room: '${scope.room.mode}' }, scopeIncludes: {}, narrowing(axis) { return this.modes[axis] !== '0' }, denying() { return Object.values(this.modes).some(mode => mode === '2') } }"
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
      <tbody>${rows}
        <tr x-show="denying()">
          <th>확인 <span class="stay-required" style="color:var(--stay-blocking)" aria-label="필수" x-show="Object.keys(modes).some(axis => modes[axis] === '2' && !scopeIncludes[axis])">*</span></th>
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

// 편집 창이 그릴 값 — 저장된 줄(GET) 그대로. 서버가 거절한 POST 는 보낸 값으로 다시 그린다(`bound`)
export function windowValues(line) {
  const scope = scopeOf(line);
  return { name: line.name, price: line.price, net_amount: line.net === null || line.net === undefined ? '' : line.net,
    season: line.season, date: line.date, rate_plan: line.rate_plan, description: line.description,
    scope: { rate_plan: { ...scope.rate_plan }, room: { ...scope.room }, confirm: false } };
}

// `_addon_price_form.html` — 편집 창(드로어 안). morph 는 렌더마다 다른 뿌리 id 조각(morph_bust)
export function priceWindow(db, hotelId, lineId, { morph = 'a1', values = null, errors = {}, nonField = '', scopeError = '' } = {}) {
  const { addon, line } = lineOf(db, lineId);
  const v = values || windowValues(line);
  const seasons = [['', '---------'], ...db.seasons.filter((s) => s.offer === addon.offer || s.id === line.season).map((s) => [s.id, s.name])];
  const plans = [['', '---------'], ...db.rate_plans.filter((p) => p.offer === addon.offer || p.id === line.rate_plan).map((p) => [p.id, p.name])];
  const root = `stay_addon_price_form_${morph}`;
  return `<div id="${root}" data-stay-screen="addon-price">
${nonField ? `\n  <div class="stay-banner stay-banner--blocking" data-stay-result="error"><span>${esc(nonField)}</span></div>\n` : ''}
  <div class="stay-card" data-stay-card="main">
    <div class="stay-card__head">
      <h4 class="stay-section-title">${esc(addon.name)}</h4>
    </div>
    <div class="table1">
      <table class="bs-table stay-table">
        <colgroup><col style="width:16%"><col style="width:34%"><col style="width:16%"><col style="width:34%"></colgroup>
        <tbody>
          <tr>
            <th>이름 ${REQUIRED}</th>
            <td colspan="3">
              <input type="text" name="name"${attr('value', v.name)} maxlength="200" aria-label="이름" data-stay-field="name" data-stay-kind="text" data-stay-required="1" required id="id_stay_name">
              <small>목록에서 이 금액이 어떤 조건인지 알아볼 이름입니다 (예: 성수기 조식).</small>
              ${error(errors, 'name')}
            </td>
          </tr>
          <tr>
            <th>판매가(공급 통화) ${REQUIRED}</th>
            <td>
              <input type="text" name="price"${attr('value', v.price)} inputmode="decimal" aria-label="판매가(공급 통화)" data-stay-field="price" data-stay-kind="number" data-stay-required="1" required id="id_stay_price">
              <small>무료면 0 을 넣습니다 — 비우면 저장되지 않습니다.</small>
              ${error(errors, 'price')}
            </td>
            <th>공급 원가(선택)</th>
            <td>
              <input type="text" name="net_amount"${attr('value', v.net_amount)} inputmode="decimal" aria-label="공급 원가(선택)" data-stay-field="net_amount" data-stay-kind="number" id="id_stay_net_amount">
              <small>공급처에 지급하는 원가입니다 — 모르면 비워 둡니다(고객 화면과 무관).</small>
              ${error(errors, 'net_amount')}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="stay-card" data-stay-card="coordinates">
    <div class="stay-card__head">
      <h4 class="stay-section-title">적용 좌표 (비우면 언제나)</h4>
    </div>
    <div class="table1">
      <table class="bs-table stay-table">
        <colgroup><col style="width:16%"><col style="width:34%"><col style="width:16%"><col style="width:34%"></colgroup>
        <tbody>
          <tr>
            <th>적용 시즌 (선택)</th>
            <td>
              ${select('season', '적용 시즌 (선택)', seasons, v.season, ' data-stay-options="seasons"')}
              ${error(errors, 'season')}
            </td>
            <th>개별 날짜</th>
            <td>
              <div class="select-field"
     x-data
     x-on:focusin="if (window.jQuery) { var jq = window.jQuery; }">
    <div class="select-wrapper">
        <dmc-datetime>
            <input type="text" name="date"${attr('value', v.date)} placeholder="2026-01-01" aria-label="개별 날짜" data-stay-field="date" data-stay-kind="date" id="id_stay_date">
        </dmc-datetime>
    </div>
</div>
              <small>갈라 디너처럼 특정 하루만 다른 금액일 때 씁니다 — 시즌과 함께 쓸 수 없습니다.</small>
              ${error(errors, 'date')}
            </td>
          </tr>
          <tr>
            <th>적용 요금제 (선택)</th>
            <td colspan="3">
              ${select('rate_plan', '적용 요금제 (선택)', plans, v.rate_plan, ' data-stay-options="rate_plans"')}
              ${error(errors, 'rate_plan')}
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
    <input type="text" name="description"${attr('value', v.description)} maxlength="200" aria-label="설명" data-stay-field="description" data-stay-kind="text" id="id_stay_description">
    ${error(errors, 'description')}
  </div>

  ${scopeCard(db, addon.offer, v.scope, { scopeError })}

  <div class="stay-drawer__footer">
    <button type="button" class="stay-btn stay-btn--primary" data-stay-action="save"
            hx-post="/stay/${hotelId}/addon-prices/${line.id}/edit/"
            hx-include="#${root} :is(input,select,textarea)"
            hx-target="#stay_drawer_body" hx-swap="innerHTML"
            hx-disable="this">저장</button>
  </div>
</div>`;
}

// `_addon_form.html` 의 뿌리와 저장 단추만 — 부가옵션 설정 창(필수 규칙 · 수량 · 범위). 벽이 그 저장을 막는지 볼 과녁
export function addonWindow(db, hotelId, addonId, { morph = 'b1' } = {}) {
  const addon = addonOf(db, addonId);
  return `<div id="stay_addon_form_${morph}" data-stay-screen="addon">
  <div class="stay-card" data-stay-card="main">
    <input type="text" name="name" value="${esc(addon.name)}" data-stay-field="name" data-stay-kind="text" data-stay-required="1" id="id_stay_name">
    <input type="text" name="max_quantity" value="${esc(addon.max_quantity ?? '')}" inputmode="numeric" data-stay-field="max_quantity" data-stay-kind="number" id="id_stay_max_quantity">
  </div>
  <div class="stay-drawer__footer">
    <button type="button" class="stay-btn stay-btn--primary" data-stay-action="save"
            hx-post="/stay/${hotelId}/addons/${addon.id}/edit/"
            hx-include="#stay_addon_form_${morph} :is(input,select,textarea)"
            hx-target="#stay_drawer_body" hx-swap="innerHTML"
            hx-disable="this">저장</button>
  </div>
</div>`;
}

// 편집 창 GET 의 드로어 제목(`views/addon.py` StayAddonPriceEditView.get — 「가격 편집 — 줄 이름(없으면 부가옵션 이름)」)
export function priceTitle(db, lineId) {
  const { addon, line } = lineOf(db, lineId);
  return `가격 편집 — ${line.name || addon.name}`;
}
