/* stay_charge.js — 부과금 도우미의 페이지 쪽 (stay-charge-change). `window.stayCharge` 를 만든다.
 *
 * 러너의 도우미(`stay_helper.js`)·부트(`stay_boot.js`), 가격 도우미(`stay-price-change/scripts/page/stay_price.js`)를 먼저 올리고
 * 이 파일을 올린다(올리개 `stayPriceLoader.load('charge')` 가 그 차례로 올린다). 벽 · 작업 틀 · 누르기 · 답 거르기 · 조각 · 바쁨 표지 ·
 * 편집 창 부품(sent · fill · saveOnce)은 가격 도우미의 `window.stayPageKit` 을 이 파일의 표(SPEC)로 쓴다 — 베끼지 않는다. 그래서
 * 도우미를 통틀어 작업은 한 번에 하나다.
 *
 *   stayCharge.look()                                                   이 탭이 어디인지 — 로그인 화면 · 호텔 · 오퍼마다 부과금 줄 전부(body)
 *   stayCharge.readCharge({hotel, offer, charge})                       부과금 하나의 편집 창을 열어 저장 단추가 보낼 칸을 읽고 닫는다
 *   stayCharge.applyCharge({no, hotel, offer, charge, name, form, set}) 그 창에 set 의 금액 칸만 치고 저장을 한 번 누른다
 *   stayCharge.take(id, at, size) · last() · idle()                     조각 받기 · 마지막 답 · 쉬는 벽 보기(가격 도우미와 같은 것)
 *
 * 지키는 것
 *  - 이 파일에는 클릭이 없다. 누르기는 모두 `stayPageKit.press` 를 지나고, 벽은 작업마다 이 파일의 허용 목록(ALLOW)만 지나게 한다.
 *    삭제 · 부과금 추가 · 정보 수집 폼 · 요율 행 추가·삭제 · 편집 창의 모든 고르기(종류 · 부과 방식 · 부과 단위 · 금액의 뜻 · 부과 유형 ·
 *    현장 결제 통화 · 요율 방식) · 적용 룸 체크 · 적용 범위 카드 · 다른 탭은 금지(NEVER)다.
 *  - 금액만 바꾼다. set 의 칸은 금액 칸(amount · pct · onsite_amount · tiers_amount · tiers_pct · age_rate_<번호> · onsite_age_rate_<번호>)
 *    뿐이고, 값은 금액 글자다 — 비우지 않고, 빈 칸을 채우지 않는다. 몇 번째(nth)는 그 이름의 보낼 칸 가운데 자리다(시간대 행 차례).
 *  - applyCharge 는 kit 의 fill 로 친다 — 치기 전에 창이 보낼 칸이 앞서 읽은 form 과 꼭 같아야 하고, 친 뒤에는 form 에서 set 의 자리만
 *    바뀌어야 한다. 금액의 뜻(amount_mode · pct_mode)도 다른 시간대 행도 읽은 그대로 나간다. 저장은 kit 의 saveOnce 로 한 번 누르고,
 *    벽은 누르는 그 순간에도 창이 친 뒤의 칸 그대로인지 본다(kit holds — 아니면 요청이 나가지 않는다).
 *  - 저장 단추의 주소(hx-post)는 페이지 안에서 견주기만 하고 돌려주지 않는다.
 */
(function () {
  'use strict';

  var K = window.stayPageKit;
  if (!K) throw new Error('가격 도우미(stay_price.js)를 먼저 올려 주세요 — stayPageKit 이 없습니다');
  var VERSION = '0.1.0';
  var C = K.C, all = K.all, fail = K.fail, clip = K.clip;

  /* ───────────── 1. 벽의 표 ───────────── */

  var HEAD = ['이름', '종류', '부과 방식', '금액', '적용 범위', '적용 날짜', '액션'];
  var SCREEN = '[data-stay-screen="charge"]';
  // 어떤 작업에서도 누르지 않는 것 — 허용 목록보다 먼저 본다
  var NEVER = [
    { sel: '[data-stay-action="delete"],[hx-delete]', why: '삭제' },
    { sel: '[data-stay-action="open_create"]', why: '부과금 추가' },
    { sel: '[data-stay-action="open_questions"]', why: '정보 수집 폼' },
    { sel: '[data-stay-action="add_row"],[data-stay-action="remove_row"]', why: '요율 행 추가·삭제' },
    { sel: SCREEN + ' select', why: '종류 · 부과 방식 · 부과 단위 · 금액의 뜻 · 부과 유형 · 현장 결제 통화 · 요율 방식' },
    { sel: SCREEN + ' input[type="checkbox"],' + SCREEN + ' label.check_form', why: '적용 룸' },
    { sel: '[data-stay-card="scope"]', why: '적용 범위' },
    { sel: '[data-stay-action="archive"]', why: '보관' },
    { sel: '[data-stay-action="activate"],[data-stay-action="end"],[data-stay-card="gate"]', why: '판매 시작·종료' },
    { sel: 'ul.tab-container a:not([data-stay-tab="charges"])', why: '다른 탭' }
  ];
  var CONTROLS = {
    tab: { sel: 'ul.tab-container a[data-stay-tab="charges"]' },
    chargeOpen: { sel: '#stay_offer_charges tr[data-stay-entity="charge"] [data-stay-action="open_edit"]', when: 'charge' },
    chargeSave: { sel: '#stay_drawer_body ' + SCREEN + ' [data-stay-action="save"]', when: 'chargeTarget', max: 1 }
  };
  var ALLOW = {
    look: ['tab'],
    readCharge: ['tab', 'chargeOpen'],
    applyCharge: ['tab', 'chargeOpen', 'chargeSave']
  };
  function hxPost(el) { return (el && (el.getAttribute('hx-post') || el.getAttribute('data-hx-post'))) || ''; }
  function editPath(hotel, charge) { return '/stay/' + hotel + '/charges/' + charge + '/edit/'; }
  function endsWith(text, tail) { return text.length >= tail.length && text.slice(-tail.length) === tail; }
  var WHEN = {
    // 그 오퍼 카드(오퍼 번호)의 그 줄(부과금 번호)의 [편집] 만
    charge: function (el, pins) {
      var tr = el.closest('tr[data-stay-entity="charge"]'), card = el.closest('[data-stay-entity="offer"]');
      return !!(pins.charge && pins.offer && tr && card) && tr.getAttribute('data-stay-entity-id') === pins.charge && card.getAttribute('data-stay-entity-id') === pins.offer;
    },
    // 그 호텔 · 그 부과금의 편집 주소로 저장하는 단추만, 그리고 누르는 순간 그 창이 친 뒤의 칸(fill 의 pins.sent)을 꼭 그대로 보낼 때만
    // (아니면 그 까닭 글로 막는다)
    chargeTarget: function (el, pins) {
      return !!(pins.hotel && pins.charge) && endsWith(hxPost(el), editPath(pins.hotel, pins.charge)) && K.holds(el.closest(SCREEN), pins);
    }
  };
  var SPEC = {
    name: 'stayCharge', allow: ALLOW, controls: CONTROLS, when: WHEN, never: NEVER, late: [],
    saves: { applyCharge: 'chargeSave' }, needs: ['calSet'], loose: ['look'],
    tidy: function (op, untilMs) { return K.closeDrawer(untilMs); }
  };

  /* ───────────── 2. 목록 — 부과금 탭의 오퍼 카드와 부과금 줄 ───────────── */

  function tab() { return document.querySelector(CONTROLS.tab.sel); }
  function panel() { return document.querySelector('#stay_offer_charges[data-stay-panel="charges"]'); }
  function tabOn() { var a = tab(); return !!a && (a.classList.contains('active') || !!a.closest('li.active')); }
  function shown() { return tabOn() && !!panel(); }
  // 목록이 보이지 않을 때만 [부과금] 탭을 누르고(탭이 이미 켜졌으면 누르지 않는다 — 스텁이 스스로 목록을 불러온다), 목록 조각이 오고
  // 도는 요청이 없을 때 넘어간다
  async function toCharges(ctx) {
    if (!tabOn()) {
      if (!tab()) fail('[부과금] 탭을 찾지 못했습니다');
      await K.press(ctx, '[부과금] 탭', tab);
    }
    return K.settle(ctx, panel, shown, '부과금 목록이 열리지 않았습니다');
  }
  function cards(root) { return all('[data-stay-entity="offer"]', root); }
  function rowsOf(card) { return all('tr[data-stay-entity="charge"]', card); }
  function withId(list, id) { return list.filter(function (el) { return el.getAttribute('data-stay-entity-id') === id; })[0] || null; }
  function cells(row) { return [].slice.call(row.children).filter(function (el) { return el.localName === 'td'; }); }
  // 화면에 보이는 글자 — 꾸밈 아이콘(aria-hidden)은 뺀다
  function shownText(el) {
    var copy = el.cloneNode(true);
    all('[aria-hidden="true"]', copy).forEach(function (icon) { icon.remove(); });
    return C(copy.textContent);
  }
  // 금액 칸의 줄들 — br 이 줄을 끝내고, div 는 제 줄이고, 나머지 글자는 지금 줄에 붙는다(빈 줄은 버린다)
  function linesOf(cell) {
    var out = [], line = '';
    [].forEach.call(cell.childNodes, function (node) {
      if (node.nodeType === 1 && node.localName === 'br') { out.push(line); line = ''; return; }
      if (node.nodeType === 1 && node.localName === 'div') { out.push(line, node.textContent); line = ''; return; }
      if (node.nodeType === 1 || node.nodeType === 3) line += ' ' + node.textContent;
    });
    out.push(line);
    return out.map(C).filter(Boolean);
  }
  // 줄 하나 — 표의 머리가 꼭 그 일곱 칸일 때만 읽는다(ERP 가 칸을 바꿨으면 다른 칸을 값으로 읽지 않게)
  function rowOf(row) {
    var table = row.closest('table');
    var head = table ? all('thead th', table).map(function (th) { return C(th.textContent); }) : [];
    if (head.join('/') !== HEAD.join('/')) {
      fail('부과금 표의 머리가 「' + HEAD.join(' / ') + '」 가 아닙니다(화면: ' + (head.join(' / ') || '없음') + ') — ERP 화면이 바뀌었을 수 있어 읽지 않습니다');
    }
    var td = cells(row);
    if (td.length !== HEAD.length) fail('부과금 줄의 칸이 ' + td.length + '개입니다 — ' + HEAD.length + '칸이어야 읽습니다');
    return {
      id: row.getAttribute('data-stay-entity-id') || '',
      name: C(row.getAttribute('data-stay-name')),
      kind: shownText(td[1]),
      basis: C(td[2].textContent),
      amount: linesOf(td[3]),
      scope: K.scopeText(td[4]),
      dates: C(td[5].textContent)
    };
  }
  function offerOf(card) { return { id: card.getAttribute('data-stay-entity-id') || '', name: C(card.getAttribute('data-stay-name')) }; }

  /* ───────────── 3. 편집 창 — 연 창이 그 호텔 · 그 부과금의 것인지, 시간대 행이 다 그려졌는지 ───────────── */

  function windowRoot() { return document.querySelector('#stay_drawer_body ' + SCREEN); }
  function saveOf(root) { return root ? root.querySelector('[data-stay-action="save"]') : null; }
  // Alpine 이 시간대 행을 다 그렸다 — 그려진 행 수가 창에 실린 행 목록(`#stay_charge_tier_rows_initial`)의 길이와 같다. 덜 그려진
  // 창을 읽으면 행 없는 form 이 되고, 그대로 보내면 ERP 가 시간대를 모두 지운다
  function tiersDrawn(root) {
    var script = root.querySelector('script#stay_charge_tier_rows_initial');
    var rows;
    try { rows = JSON.parse(script ? script.textContent : 'null'); } catch (e) { rows = null; }
    return Array.isArray(rows) && all('[data-stay-card="tiers"] tr[data-stay-row]', root).length === rows.length;
  }
  function windowFacts(root, form) {
    var labels = {};
    all('select', root).forEach(function (s) {
      if (!s.name) return;
      var text = s.selectedIndex >= 0 ? C(s.options[s.selectedIndex].textContent) : '';
      labels[s.name] = labels[s.name] === undefined ? text : labels[s.name] + '\n' + text;
    });
    var label = root.querySelector('[data-stay-label-for="amount_mode"]');
    var code = label ? /\(([A-Z]{3})\)/.exec(C(label.textContent)) : null;
    return {
      title: C((document.querySelector('.stay-drawer__title') || {}).textContent),
      currency: code ? code[1] : '',
      form: form, labels: labels,
      bands: all('input', root).filter(function (el) { return /^(onsite_)?age_rate_\d+$/.test(el.name); }).map(function (el) {
        return { field: el.name, code: el.getAttribute('data-stay-band') || '', label: C(el.getAttribute('aria-label')) };
      }),
      errors: K.errors(root)
    };
  }
  // 그 오퍼 카드의 그 줄을 찾아 [편집] 을 누르고, 열린 창이 그 호텔 · 그 부과금의 편집 창인지 본다. 목록에 그 줄이 없으면 아무것도
  // 누르지 않고 null
  async function openCharge(ctx, want, refusal) {
    var root = await toCharges(ctx);
    var card = withId(cards(root), want.offer);
    var row = card && withId(rowsOf(card), want.charge);
    if (!row) return null;
    var charge = rowOf(row);
    ctx.pins.hotel = ctx.hotel.id;
    ctx.pins.offer = want.offer;
    ctx.pins.charge = want.charge;
    await K.press(ctx, '`' + charge.name + '` 줄 [편집]', function () {
      var c = withId(cards(panel() || document), want.offer), r = c && withId(rowsOf(c), want.charge);
      return r ? r.querySelector('[data-stay-action="open_edit"]') : null;
    });
    var win = await K.settle(ctx, windowRoot, function (r) { return !!saveOf(r) && K.drawerOpen(); }, '부과금 편집 창이 열리지 않았습니다');
    if (!endsWith(hxPost(saveOf(win)), editPath(ctx.hotel.id, want.charge))) fail('열린 창이 고른 부과금(' + want.charge + ')의 편집 창이 아닙니다 — 아무것도 치지 않았습니다', refusal);
    await ctx.wait(function () { return windowRoot() === win && tiersDrawn(win); }, 3000);
    if (windowRoot() !== win || !tiersDrawn(win)) fail('부과금 편집 창의 시간대별 요율 행이 다 그려지지 않았습니다 — 아무것도 치지 않았습니다', refusal);
    return { root: win, offer: offerOf(card), charge: charge };
  }
  function ids(p) {
    var id = function (value, name) {
      if (typeof value !== 'string' || !/^\d+$/.test(value)) fail('`' + name + '` 은 ERP 가 매긴 번호 글자입니다(look() 의 id 그대로, 예: "701")');
      return value;
    };
    return { offer: id(p.offer, 'offer'), charge: id(p.charge, 'charge') };
  }

  /* ───────────── 4. 보기 하나와 작업 둘 ───────────── */

  // 이 탭이 어디인지와 오퍼마다 부과금 줄 전부. 저장하지 않는다. 누르는 것은 (목록이 안 보이면) [부과금] 탭 하나다. 목록은 늘 body 로 둔다
  function look(input) {
    input = input && typeof input === 'object' ? input : {};
    return K.run('look', input, async function (p, ctx) {
      var root = await toCharges(ctx);
      var offers = cards(root).map(function (card) {
        var offer = offerOf(card);
        return { id: offer.id, name: offer.name, charges: rowsOf(card).map(rowOf) };
      });
      var charges = offers.reduce(function (n, o) { return n + o.charges.length; }, 0);
      return { ok: true, login: false, hotel: ctx.hotel, count: { offers: offers.length, charges: charges }, keep: { hotel: ctx.hotel, offers: offers } };
    }, SPEC);
  }

  // 부과금 하나의 편집 창 — 연 창이 그 부과금의 것인지 본 뒤 저장 단추가 보낼 칸(form) · 고르기의 보이는 글자 · 정액 통화 · 연령 구간 칸 ·
  // 오류를 읽고 드로어를 `stay-drawer-close` 로 닫는다. 저장은 누르지 않는다. 목록에 그 줄이 없으면 {missing: true} 이고 더 누르지 않는다
  function readCharge(input) {
    return K.run('readCharge', input, async function (p, ctx) {
      var want = ids(p);
      var win = await openCharge(ctx, want, {});
      if (!win) return { ok: true, missing: true, note: '목록에 그 오퍼의 그 부과금이 없습니다 — 아무것도 열지 않았습니다' };
      var form = K.sent(win.root);
      if (!form) fail('부과금 편집 창의 저장 단추가 무엇을 보내는지 알 수 없어(hx-include) 읽지 않았습니다');
      var facts = windowFacts(win.root, form);
      await K.closeDrawer(Date.now() + 3000);
      if (K.drawerOpen()) fail('읽은 뒤 드로어를 닫지 못했습니다');
      return { ok: true, what: clip(win.offer.name + ' · ' + win.charge.name, 120),
        keep: { hotel: ctx.hotel, offer: win.offer, charge: win.charge, window: facts } };
    }, SPEC);
  }

  var AMOUNT = /^\d+(\.\d+)?$/;
  var FIELD = /^(amount|pct|onsite_amount|tiers_amount|tiers_pct|age_rate_\d+|onsite_age_rate_\d+)$/;
  var LABELS = { amount: '정액 금액', pct: '정률(%)', onsite_amount: '현장 결제 금액', tiers_amount: '시간대 정액', tiers_pct: '시간대 정률' };
  function settable(name) {
    if (!FIELD.test(name)) return null;
    return LABELS[name] || (/^onsite_/.test(name) ? '현장 연령별 단가' : '연령별 단가');
  }
  // set — [이름, 몇 번째, 금액 글자] 목록. 금액 칸만, 금액 글자만(비우지 않는다), form 에 그 자리가 있고 비어 있지 않을 때만(빈 칸을
  // 채우지 않는다), 같은 자리는 한 번만
  function editsOf(set, form) {
    if (!Array.isArray(set) || !set.length) fail('`set` 은 바꿀 칸 목록입니다 — [이름, 몇 번째, 금액 글자] 꼴(예: [["tiers_pct", 1, "60.00"]])');
    var seen = {};
    return set.map(function (edit) {
      if (!Array.isArray(edit) || edit.length !== 3) fail('`set` 의 한 줄은 [이름, 몇 번째, 금액 글자] 입니다');
      var name = edit[0], nth = edit[1], value = edit[2];
      if (typeof name !== 'string' || !FIELD.test(name)) {
        fail('`set` 에는 금액 칸만 넣습니다(amount · pct · onsite_amount · tiers_amount · tiers_pct · age_rate_<번호> · onsite_age_rate_<번호>): ' + clip(String(name), 30));
      }
      if (typeof nth !== 'number' || nth !== Math.floor(nth) || nth < 0) fail('`set` 의 몇 번째(' + name + ')는 0 부터 세는 정수입니다');
      if (typeof value !== 'string' || !AMOUNT.test(value)) fail('`set` 의 ' + name + ' 값은 금액 글자입니다(예: "60.00") — 이 도우미는 금액을 비우지 않습니다');
      var key = name + '#' + nth;
      if (seen[key]) fail('`set` 에 ' + name + ' 의 ' + (nth + 1) + '번째가 두 번 있습니다');
      seen[key] = true;
      var values = form.filter(function (x) { return x[0] === name; });
      if (nth >= values.length) fail('`form` 에 ' + name + ' 칸의 ' + (nth + 1) + '번째가 없습니다 — readCharge 의 form 을 그대로 넣습니다');
      if (C(values[nth][1]) === '') fail('`form` 의 ' + name + ' ' + (nth + 1) + '번째 칸이 비어 있습니다 — 이 도우미는 빈 금액을 채우지 않습니다');
      return [name, nth, value];
    });
  }

  // 부과금 하나 저장 — 창을 readCharge 처럼 열고, 창의 이름 칸이 고른 부과금의 이름인지 본 뒤 kit 의 fill(치기 전 창 = form, 친 뒤 창 =
  // form 에서 set 의 자리만 바꾼 것)로 치고 kit 의 saveOnce 로 저장을 한 번 누른다. 누르기 전에 멈추면 refused · saved false · pressed false
  function applyCharge(input) {
    return K.run('applyCharge', input, async function (p, ctx) {
      var want = ids(p);
      if (typeof p.name !== 'string' || !C(p.name)) fail('`name` 은 readCharge 가 읽은 부과금 이름(window.form 의 name)입니다');
      var form = K.pairs(p.form, 'readCharge');
      var edits = editsOf(p.set, form);
      var win = await openCharge(ctx, want, { refused: true });
      if (!win) fail('목록에 그 오퍼의 그 부과금이 없습니다 — 저장하지 않았습니다', { refused: true, missing: true });
      var names = all('input,select,textarea', win.root).filter(function (el) { return el.name === 'name' && !el.matches(':disabled'); });
      if (names.length !== 1 || names[0].value !== p.name) {
        fail('창의 부과금 이름이 고른 부과금(「' + clip(p.name, 40) + '」)이 아닙니다 — 아무것도 치지 않았습니다', { refused: true });
      }
      K.fill(ctx, win.root, form, edits, { window: '부과금 편집 창', settable: settable });
      return K.saveOnce(ctx, { root: win.root, panel: 'stay_offer_charges', window: '부과금 편집 창', what: clip(win.offer.name + ' · ' + win.charge.name, 120) });
    }, SPEC);
  }

  window.stayCharge = {
    version: VERSION,
    look: look,
    readCharge: readCharge,
    applyCharge: applyCharge,
    take: function (id, at, size) { return K.take(id, at, size); },
    last: function () { return K.last(); },
    idle: function () { return K.idle(); },
    ALLOW: ALLOW, CONTROLS: CONTROLS, NEVER: NEVER,
    // 시험·점검용: 작업 하나의 벽을 이 파일의 표로 세운 채 fn 을 돌린다(막기만 하고 풀어 주는 것은 없다)
    guard: function (op, fn, pins) { return K.guard(SPEC, op, fn, pins); }
  };
  return K.scrub({ ok: true, version: VERSION });
})();
