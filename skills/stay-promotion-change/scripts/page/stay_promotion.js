/* stay_promotion.js — 프로모션 할인 도우미의 페이지 쪽 (stay-promotion-change). `window.stayPromotion` 을 만든다.
 *
 * 러너의 도우미(`stay_helper.js`)·부트(`stay_boot.js`), 가격 도우미(`stay-price-change/scripts/page/stay_price.js`)를 먼저 올리고
 * 이 파일을 올린다(올리개 `stayPriceLoader.load('promotion')` 이 그 차례로 올린다). 벽 · 작업 틀 · 누르기 · 답 거르기 · 조각 · 바쁨 표지 ·
 * 편집 창 부품(sent · fill · saveOnce)은 가격 도우미의 `window.stayPageKit` 을 이 파일의 표(SPEC)로 쓴다 — 베끼지 않는다. 그래서
 * 도우미를 통틀어 작업은 한 번에 하나다.
 *
 *   stayPromotion.look()                                                        이 탭이 어디인지 — 로그인 화면 · 호텔 · 카드마다
 *                                                                               (오퍼 · 전 오퍼 공통) 프로모션 줄 전부(body)
 *   stayPromotion.readPromotion({hotel, offer, promotion})                      프로모션 하나의 편집 창을 열어 저장 단추가 보낼 칸 ·
 *                                                                               표식을 읽고 닫는다(전 오퍼 공통은 offer "0")
 *   stayPromotion.applyPromotion({no, hotel, offer, promotion, title, form,
 *                                 marks, set})                                  그 창에 set 의 단 값만 치고 저장을 한 번 누른다
 *   stayPromotion.take(id, at, size) · last() · idle()                          조각 받기 · 마지막 답 · 쉬는 벽 보기(가격 도우미와 같은 것)
 *
 * 지키는 것
 *  - 이 파일에는 클릭이 없다. 누르기는 모두 `stayPageKit.press` 를 지나고, 벽은 작업마다 이 파일의 허용 목록(ALLOW)만 지나게 한다.
 *    삭제 · 프로모션 추가 · 단 추가 · 단 삭제 · 편집 창의 모든 고르기(발동 조건 · 혜택 방식 · 적용 단위 · 시즌 · 요금제 · 취소 정책 ·
 *    적용 범위) · 모든 체크(진행기간 제한 · 중복 허용 · 적용 범위 · 붙일 오퍼) · 적용 범위 카드 · 다른 탭은 금지(NEVER)다.
 *  - 화면 밖 설정을 지키는 ERP 에서만 저장한다. 편집 창 뿌리의 표식(`data-stay-keeps-off-form-keys="1"`)이 없으면 applyPromotion 은
 *    아무것도 치지 않고, 벽도 그 창의 [저장] 을 막는다(promotionTarget). 표식은 누르는 순간 저장할 그 창에서 읽는다.
 *  - 단의 값만 바꾼다. set 의 칸은 `tiers_value` 뿐이고, 값은 숫자 글자다 — 비우지 않고, 빈 칸을 채우지 않는다. 몇 번째(nth)는 단 줄의
 *    차례다. 치기 전에 단 줄마다 화면 밖 설정의 이름(`data-stay-off-form-keys`)이 읽은 marks 와 같아야 한다.
 *  - applyPromotion 은 kit 의 fill 로 친다 — 치기 전에 창이 보낼 칸이 앞서 읽은 form 과 꼭 같아야 하고(`tiers_origin` · 진행기간
 *    체크까지), 친 뒤에는 form 에서 set 의 자리만 바뀌어야 한다. 저장은 kit 의 saveOnce 로 한 번 누르고, 벽은 누르는 그 순간에도 창이
 *    친 뒤의 칸 그대로인지 본다(kit holds — 아니면 요청이 나가지 않는다).
 *  - 단 줄의 숨은 칸 `tiers_origin`(그 줄이 저장된 어느 단에서 왔는지 — 저장된 단의 기준값, 새 줄은 빈 값)은 읽은 그대로 두고 치지
 *    않는다. 줄마다 그 값이 그 줄이 실려 온 단의 기준값 글자와 꼭 같아야 친다 — `?`(ERP 가 모름 — 거절된 요청 뒤 다시 그린 창) · 빈 값
 *    · 다른 값 · ERP 가 앞으로 더할 다른 표시가 한 줄이라도 있으면 applyPromotion 은 아무것도 치지 않는다.
 *  - 저장 단추의 주소(hx-post)는 페이지 안에서 견주기만 하고 돌려주지 않는다.
 */
(function () {
  'use strict';

  var K = window.stayPageKit;
  if (!K) throw new Error('가격 도우미(stay_price.js)를 먼저 올려 주세요 — stayPageKit 이 없습니다');
  var VERSION = '0.1.0';
  var C = K.C, all = K.all, fail = K.fail, clip = K.clip;
  var GATE = '이 ERP 는 아직 프로모션을 화면으로 저장하면 화면에 안 보이는 설정이 지워질 수 있어, 도우미가 저장하지 않습니다 — ERP 가 고쳐진 뒤에 됩니다';
  // 단 줄의 숨은 칸 tiers_origin 이 「?」 — ERP 가 그 줄이 어느 저장된 단에서 왔는지 모른다(숨은 칸 없이 보낸 요청이 거절된 뒤 다시
  // 그린 창). 그런 창에서는 치지 않는다(명령의 ORIGIN_UNKNOWN 과 같은 문장)
  var UNSURE = '?';
  var ORIGIN_UNKNOWN = '이 프로모션의 편집 창은 ERP 가 할인 단 줄이 어느 저장된 단에서 왔는지 모르는 상태라(앞선 저장이 거절된 뒤 다시 그려진 창), 저장하면 화면에 안 보이는 설정이 다른 단에 붙거나 빠질 수 있어 도우미가 저장하지 않습니다 — ERP 에서 그 프로모션의 편집 창을 닫았다가 다시 열어 주시면 다시 해 보겠습니다';
  // 그 밖에 숨은 칸이 그 줄이 실려 온 단의 기준값이 아닌 줄(빈 값 · 다른 값 · ERP 가 앞으로 더할 다른 표시) — 짝을 도우미가 알아볼 수 없다
  function notOwn(row) {
    return '이 프로모션의 편집 창은 할인 단 ' + row + '번째 줄이 어느 저장된 단에서 왔는지 도우미가 알아볼 수 없어(숨은 칸이 그 줄의 기준값이 아닙니다), 저장하면 화면에 안 보이는 설정이 다른 단에 붙거나 빠질 수 있어 도우미가 저장하지 않습니다';
  }
  var COMMON = { id: '0', name: '전 오퍼 공통' };

  /* ───────────── 1. 벽의 표 ───────────── */

  var HEAD = ['프로모션', '발동 조건', '혜택', '중복', '한정', '액션'];
  var SCREEN = '[data-stay-screen="promotion"]';
  var KEEPS = 'data-stay-keeps-off-form-keys', OFF = 'data-stay-off-form-keys';
  // 어떤 작업에서도 누르지 않는 것 — 허용 목록보다 먼저 본다
  var NEVER = [
    { sel: '[data-stay-action="delete"],[hx-delete]', why: '삭제' },
    { sel: '[data-stay-action="open_create"]', why: '프로모션 추가' },
    { sel: '[data-stay-action="add_row"],[data-stay-action="remove_row"]', why: '단 추가·삭제' },
    { sel: SCREEN + ' select', why: '발동 조건 · 혜택 방식 · 적용 단위 · 시즌 · 요금제 · 취소 정책 · 적용 범위' },
    { sel: SCREEN + ' input[type="checkbox"],' + SCREEN + ' input[type="radio"],' + SCREEN + ' label.check_form', why: '진행기간 제한 · 중복 허용 · 적용 범위 · 붙일 오퍼' },
    { sel: '[data-stay-card="scope"]', why: '적용 범위' },
    { sel: '[data-stay-action="archive"]', why: '보관' },
    { sel: '[data-stay-action="activate"],[data-stay-action="end"],[data-stay-card="gate"]', why: '판매 시작·종료' },
    { sel: 'ul.tab-container a:not([data-stay-tab="promotions"])', why: '다른 탭' }
  ];
  var CONTROLS = {
    tab: { sel: 'ul.tab-container a[data-stay-tab="promotions"]' },
    promotionOpen: { sel: '#stay_promotions tr[data-stay-entity="promotion"] [data-stay-action="open_edit"]', when: 'promotion' },
    promotionSave: { sel: '#stay_drawer_body ' + SCREEN + ' [data-stay-action="save"]', when: 'promotionTarget', max: 1 }
  };
  var ALLOW = {
    look: ['tab'],
    readPromotion: ['tab', 'promotionOpen'],
    applyPromotion: ['tab', 'promotionOpen', 'promotionSave']
  };
  function hxPost(el) { return (el && (el.getAttribute('hx-post') || el.getAttribute('data-hx-post'))) || ''; }
  function editPath(hotel, promotion) { return '/stay/' + hotel + '/promotions/' + promotion + '/edit/'; }
  function endsWith(text, tail) { return text.length >= tail.length && text.slice(-tail.length) === tail; }
  // 목록의 카드 하나의 오퍼 — 오퍼 표식이 있으면 그 번호, 없으면 전 오퍼 공통(0)
  function cardOffer(card) { return card.getAttribute('data-stay-entity') === 'offer' ? card.getAttribute('data-stay-entity-id') || '' : COMMON.id; }
  var WHEN = {
    // 그 카드(오퍼 번호 · 전 오퍼 공통은 0)의 그 줄(프로모션 번호)의 [편집] 만
    promotion: function (el, pins) {
      var tr = el.closest('tr[data-stay-entity="promotion"]'), card = el.closest('#stay_promotions .stay-card');
      return !!(pins.promotion && pins.offer && tr && card) && tr.getAttribute('data-stay-entity-id') === pins.promotion && cardOffer(card) === pins.offer;
    },
    // 그 호텔 · 그 프로모션의 편집 주소로 저장하는 단추만, 그 창에 화면 밖 설정을 지키는 표식이 있을 때만, 그리고 누르는 순간 그 창이
    // 친 뒤의 칸(fill 의 pins.sent)을 꼭 그대로 보낼 때만(아니면 그 까닭 글로 막는다)
    promotionTarget: function (el, pins) {
      var root = el.closest(SCREEN);
      return !!(pins.hotel && pins.promotion && root) && root.getAttribute(KEEPS) === '1' && endsWith(hxPost(el), editPath(pins.hotel, pins.promotion)) &&
        K.holds(root, pins);
    }
  };
  var SPEC = {
    name: 'stayPromotion', allow: ALLOW, controls: CONTROLS, when: WHEN, never: NEVER, late: [],
    saves: { applyPromotion: 'promotionSave' }, needs: ['calSet'], loose: ['look'],
    tidy: function (op, untilMs) { return K.closeDrawer(untilMs); }
  };

  /* ───────────── 2. 목록 — 프로모션 탭의 카드와 프로모션 줄 ───────────── */

  function tab() { return document.querySelector(CONTROLS.tab.sel); }
  function panel() { return document.querySelector('#stay_promotions[data-stay-panel="promotions"]'); }
  function tabOn() { var a = tab(); return !!a && (a.classList.contains('active') || !!a.closest('li.active')); }
  function shown() { return tabOn() && !!panel(); }
  // 목록이 보이지 않을 때만 [프로모션] 탭을 누르고, 목록 조각이 오고 도는 요청이 없을 때 넘어간다
  async function toPromotions(ctx) {
    if (!tabOn()) {
      if (!tab()) fail('[프로모션] 탭을 찾지 못했습니다');
      await K.press(ctx, '[프로모션] 탭', tab);
    }
    return K.settle(ctx, panel, shown, '프로모션 목록이 열리지 않았습니다');
  }
  function cards(root) {
    var found = all('.stay-card', root);
    if (found.filter(function (card) { return cardOffer(card) === COMMON.id; }).length > 1) fail('프로모션 목록에 「전 오퍼 공통」 카드가 둘 이상 있습니다 — 읽지 않습니다');
    return found;
  }
  function rowsOf(card) { return all('tr[data-stay-entity="promotion"]', card); }
  function withId(list, id) { return list.filter(function (el) { return el.getAttribute('data-stay-entity-id') === id; })[0] || null; }
  function cardOf(root, offer) { return cards(root).filter(function (card) { return cardOffer(card) === offer; })[0] || null; }
  function cells(row) { return [].slice.call(row.children).filter(function (el) { return el.localName === 'td'; }); }
  // 칸의 줄들 — br 이 줄을 끝내고, div · p 는 제 줄(안의 div 도 저마다 제 줄)이고, 나머지 글자는 지금 줄에 붙는다. 꾸밈 아이콘
  // (aria-hidden · stay-cond__icon)은 뺀다. 빈 줄은 버린다
  function linesOf(cell) {
    var out = [], line = '';
    (function walk(node) {
      [].forEach.call(node.childNodes, function (n) {
        if (n.nodeType === 1 && n.localName === 'br') { out.push(line); line = ''; return; }
        if (n.nodeType === 1 && (n.getAttribute('aria-hidden') === 'true' || n.classList.contains('stay-cond__icon'))) return;
        if (n.nodeType === 1 && (n.localName === 'div' || n.localName === 'p')) { out.push(line); line = ''; walk(n); out.push(line); line = ''; return; }
        if (n.nodeType === 1 || n.nodeType === 3) line += n.textContent;
      });
    })(cell);
    out.push(line);
    return out.map(C).filter(Boolean);
  }
  // 줄 하나 — 표의 머리가 꼭 그 여섯 칸일 때만 읽는다(ERP 가 칸을 바꿨으면 다른 칸을 값으로 읽지 않게)
  function rowOf(row) {
    var table = row.closest('table');
    var head = table ? all('thead th', table).map(function (th) { return C(th.textContent); }) : [];
    if (head.join('/') !== HEAD.join('/')) {
      fail('프로모션 표의 머리가 「' + HEAD.join(' / ') + '」 가 아닙니다(화면: ' + (head.join(' / ') || '없음') + ') — ERP 화면이 바뀌었을 수 있어 읽지 않습니다');
    }
    var td = cells(row);
    if (td.length !== HEAD.length) fail('프로모션 줄의 칸이 ' + td.length + '개입니다 — ' + HEAD.length + '칸이어야 읽습니다');
    var code = [].slice.call(td[0].children).filter(function (el) { return el.localName === 'small'; })[0];
    return {
      id: row.getAttribute('data-stay-entity-id') || '',
      title: C(row.getAttribute('data-stay-name')),
      code: code ? C(code.textContent) : '',
      trigger: linesOf(td[1]).join(' · '),
      benefit: linesOf(td[2]),
      combo: linesOf(td[3]),
      limits: linesOf(td[4]),
      warnings: all('.stay-cond', td[0]).map(function (el) { return linesOf(el).join(' '); })
    };
  }
  function offerOf(card) {
    return cardOffer(card) === COMMON.id ? { id: COMMON.id, name: COMMON.name } : { id: cardOffer(card), name: C(card.getAttribute('data-stay-name')) };
  }

  /* ───────────── 3. 편집 창 — 연 창이 그 호텔 · 그 프로모션의 것인지, 단 줄이 다 그려졌는지, 표식 ───────────── */

  function windowRoot() { return document.querySelector('#stay_drawer_body ' + SCREEN); }
  function saveOf(root) { return root ? root.querySelector('[data-stay-action="save"]') : null; }
  function tierRows(root) { return all('table[data-stay-rows="tiers"] tr[data-stay-row]', root); }
  // 창에 실린 단 목록(`#stay_promotion_tier_rows_initial` — 창 뿌리 앞의 형제)
  function initialRows() {
    var script = document.querySelector('#stay_drawer_body script#stay_promotion_tier_rows_initial');
    try { return JSON.parse(script ? script.textContent : 'null'); } catch (e) { return null; }
  }
  // Alpine 이 단 줄을 다 그렸다 — 그려진 줄 수가 창에 실린 단 목록의 길이와 같다. 덜 그려진 창을 읽으면 단 없는 form 이 된다
  function tiersDrawn(root) { var rows = initialRows(); return Array.isArray(rows) && tierRows(root).length === rows.length; }
  // 단 줄마다 화면 밖 설정의 이름들(줄의 표식, 창의 차례). 창에 실린 목록이 이름을 들고 있으면 그것과 같아야 한다 — Alpine 이 표식을 다
  // 달았는지 본다
  function marksOf(root) {
    var marks = tierRows(root).map(function (tr) { return C(tr.getAttribute(OFF)).split(' ').filter(Boolean); });
    var rows = initialRows() || [];
    rows.forEach(function (row, i) {
      if (row && Array.isArray(row.off_form_keys) && row.off_form_keys.join(' ') !== (marks[i] || []).join(' ')) {
        fail('단 줄 ' + (i + 1) + '의 화면 밖 설정 표식이 창에 실린 단 목록과 다릅니다 — 아무것도 치지 않았습니다', { refused: true });
      }
    });
    return marks;
  }
  function windowFacts(root, form) {
    var labels = {};
    all('select', root).forEach(function (s) {
      if (!s.name) return;
      var text = s.selectedIndex >= 0 ? C(s.options[s.selectedIndex].textContent) : '';
      labels[s.name] = labels[s.name] === undefined ? text : labels[s.name] + '\n' + text;
    });
    return {
      title: C((document.querySelector('.stay-drawer__title') || {}).textContent),
      form: form, labels: labels, keeps: root.getAttribute(KEEPS) === '1', marks: marksOf(root),
      errors: K.errors(root)
    };
  }
  // 그 카드의 그 줄을 찾아 [편집] 을 누르고, 열린 창이 그 호텔 · 그 프로모션의 편집 창인지 본다. 목록에 그 줄이 없으면 아무것도
  // 누르지 않고 null
  async function openPromotion(ctx, want, refusal) {
    var root = await toPromotions(ctx);
    var card = cardOf(root, want.offer);
    var row = card && withId(rowsOf(card), want.promotion);
    if (!row) return null;
    var promotion = rowOf(row);
    ctx.pins.hotel = ctx.hotel.id;
    ctx.pins.offer = want.offer;
    ctx.pins.promotion = want.promotion;
    await K.press(ctx, '`' + promotion.title + '` 줄 [편집]', function () {
      var c = cardOf(panel() || document, want.offer), r = c && withId(rowsOf(c), want.promotion);
      return r ? r.querySelector('[data-stay-action="open_edit"]') : null;
    });
    var win = await K.settle(ctx, windowRoot, function (r) { return !!saveOf(r) && K.drawerOpen(); }, '프로모션 편집 창이 열리지 않았습니다');
    if (!endsWith(hxPost(saveOf(win)), editPath(ctx.hotel.id, want.promotion))) fail('열린 창이 고른 프로모션(' + want.promotion + ')의 편집 창이 아닙니다 — 아무것도 치지 않았습니다', refusal);
    await ctx.wait(function () { return windowRoot() === win && tiersDrawn(win); }, 3000);
    if (windowRoot() !== win || !tiersDrawn(win)) fail('프로모션 편집 창의 할인 단 줄이 다 그려지지 않았습니다 — 아무것도 치지 않았습니다', refusal);
    return { root: win, offer: offerOf(card), promotion: promotion };
  }
  function ids(p) {
    var id = function (value, name) {
      if (typeof value !== 'string' || !/^\d+$/.test(value)) fail('`' + name + '` 은 ERP 가 매긴 번호 글자입니다(look() 의 id 그대로, 예: "9001" · 전 오퍼 공통 카드는 offer "0")');
      return value;
    };
    return { offer: id(p.offer, 'offer'), promotion: id(p.promotion, 'promotion') };
  }

  /* ───────────── 4. 보기 하나와 작업 둘 ───────────── */

  // 이 탭이 어디인지와 카드마다 프로모션 줄 전부. 저장하지 않는다. 누르는 것은 (목록이 안 보이면) [프로모션] 탭 하나다
  function look(input) {
    input = input && typeof input === 'object' ? input : {};
    return K.run('look', input, async function (p, ctx) {
      var root = await toPromotions(ctx);
      var offers = cards(root).map(function (card) {
        var offer = offerOf(card);
        return { id: offer.id, name: offer.name, promotions: rowsOf(card).map(rowOf) };
      });
      var promotions = offers.reduce(function (n, o) { return n + o.promotions.length; }, 0);
      return { ok: true, login: false, hotel: ctx.hotel, count: { offers: offers.length, promotions: promotions }, keep: { hotel: ctx.hotel, offers: offers } };
    }, SPEC);
  }

  // 프로모션 하나의 편집 창 — 연 창이 그 프로모션의 것인지 본 뒤 저장 단추가 보낼 칸(form) · 고르기의 보이는 글자 · 표식(뿌리 ·
  // 단 줄마다) · 오류를 읽고 드로어를 `stay-drawer-close` 로 닫는다. 저장은 누르지 않는다. 목록에 그 줄이 없으면 {missing: true}
  // 결과를 못 본 이 창의 저장(saved "unknown")에 ERP 가 늦게 거절로 답했으면 그 한 문장(kit late)을 읽기 답의 `late` 로 한 번 싣는다
  function withLate(result) { var said = K.late('promotion'); if (said) result.late = said; return result; }
  function readPromotion(input) {
    return K.run('readPromotion', input, async function (p, ctx) {
      var want = ids(p);
      var win = await openPromotion(ctx, want, {});
      if (!win) return withLate({ ok: true, missing: true, note: '목록에 그 카드의 그 프로모션이 없습니다 — 아무것도 열지 않았습니다' });
      var form = K.sent(win.root);
      if (!form) fail('프로모션 편집 창의 저장 단추가 무엇을 보내는지 알 수 없어(hx-include) 읽지 않았습니다');
      var facts = windowFacts(win.root, form);
      await K.closeDrawer(Date.now() + 3000);
      if (K.drawerOpen()) fail('읽은 뒤 드로어를 닫지 못했습니다');
      return withLate({ ok: true, what: clip(win.offer.name + ' · ' + win.promotion.title, 120), keeps: facts.keeps,
        keep: { hotel: ctx.hotel, offer: win.offer, promotion: win.promotion, window: facts } });
    }, SPEC);
  }

  var VALUE = /^\d+(\.\d+)?$/;
  function settable(name) { return name === 'tiers_value' ? '할인 값' : null; }
  // set — [이름, 몇 번째, 값 글자] 목록. 단의 값 칸(tiers_value)만, 숫자 글자만(비우지 않는다), form 에 그 자리가 있고 비어 있지 않을
  // 때만(빈 칸을 채우지 않는다), 같은 자리는 한 번만
  function editsOf(set, form) {
    if (!Array.isArray(set) || !set.length) fail('`set` 은 바꿀 단 목록입니다 — [이름, 몇 번째, 값 글자] 꼴(예: [["tiers_value", 0, "12"]])');
    var seen = {};
    return set.map(function (edit) {
      if (!Array.isArray(edit) || edit.length !== 3) fail('`set` 의 한 줄은 [이름, 몇 번째, 값 글자] 입니다');
      var name = edit[0], nth = edit[1], value = edit[2];
      if (name !== 'tiers_value') fail('`set` 에는 단의 값 칸(tiers_value)만 넣습니다: ' + clip(String(name), 30));
      if (typeof nth !== 'number' || nth !== Math.floor(nth) || nth < 0) fail('`set` 의 몇 번째는 0 부터 세는 정수입니다');
      if (typeof value !== 'string' || !VALUE.test(value)) fail('`set` 의 값은 0 이상의 숫자 글자입니다(예: "12") — 이 도우미는 단의 값을 비우지 않습니다');
      if (seen[nth]) fail('`set` 에 ' + (nth + 1) + '번째 단이 두 번 있습니다');
      seen[nth] = true;
      var values = form.filter(function (x) { return x[0] === name; });
      if (nth >= values.length) fail('`form` 에 ' + (nth + 1) + '번째 단이 없습니다 — readPromotion 의 form 을 그대로 넣습니다');
      if (C(values[nth][1]) === '') fail('`form` 의 ' + (nth + 1) + '번째 단의 값이 비어 있습니다 — 이 도우미는 빈 값을 채우지 않습니다');
      return [name, nth, value];
    });
  }
  // marks — 단 줄마다 화면 밖 설정의 이름 목록(readPromotion 의 window.marks 그대로), 줄 수는 form 의 단 수와 같다
  function marksIn(value, form) {
    var count = form.filter(function (x) { return x[0] === 'tiers_value'; }).length;
    var bad = !Array.isArray(value) || value.length !== count || value.some(function (names) {
      return !Array.isArray(names) || names.some(function (n) { return typeof n !== 'string'; });
    });
    if (bad) fail('`marks` 는 readPromotion 이 돌려준 window.marks(단 줄마다 이름 목록, ' + count + '줄) 그대로입니다');
    return value.map(function (names) { return names.join(' '); });
  }

  // 프로모션 하나 저장 — 창을 readPromotion 처럼 열고, 창의 이름 칸이 고른 프로모션의 이름인지, 창에 표식이 있는지, 단 줄의 표식이
  // 읽은 것과 같은지 본 뒤 kit 의 fill(치기 전 창 = form, 친 뒤 창 = form 에서 set 의 자리만 바꾼 것)로 치고 kit 의 saveOnce 로 저장을
  // 한 번 누른다. 누르기 전에 멈추면 refused · saved false · pressed false
  function applyPromotion(input) {
    return K.run('applyPromotion', input, async function (p, ctx) {
      var want = ids(p);
      if (typeof p.title !== 'string' || !C(p.title)) fail('`title` 은 그 프로모션의 이름입니다(명령의 calls 가 준 그대로)');
      var form = K.pairs(p.form, 'readPromotion');
      var marks = marksIn(p.marks, form);
      var edits = editsOf(p.set, form);
      var win = await openPromotion(ctx, want, { refused: true });
      if (!win) fail('목록에 그 카드의 그 프로모션이 없습니다 — 저장하지 않았습니다', { refused: true, missing: true });
      // 이름은 목록이 읽는 대로 맞춰 견준다(C — NFC · 빈칸 묶음 하나로 · 앞뒤 빈칸 없이): 명령이 주는 title 은 목록의 이름이고 창의 이름
      // 칸은 날 글자다. 그 창이 그 프로모션의 것인지는 열 때 저장 주소(프로모션 번호)로 이미 봤다
      var titles = all('input,select,textarea', win.root).filter(function (el) { return el.name === 'title' && !el.matches(':disabled'); });
      if (titles.length !== 1 || C(titles[0].value) !== C(p.title)) {
        fail('창의 프로모션 이름이 고른 프로모션(「' + clip(p.title, 40) + '」)이 아닙니다 — 아무것도 치지 않았습니다', { refused: true });
      }
      if (win.root.getAttribute(KEEPS) !== '1') fail(GATE + ' — 아무것도 치지 않았고 누르지 않았습니다', { refused: true, gate: true });
      // 단 줄마다 숨은 칸 tiers_origin 이 그 줄이 실려 온 단의 기준값 글자(창에 실린 단 목록의 threshold)와 꼭 같을 때만 친다 — ERP 가
      // 그 줄을 그 저장된 단과 짝짓는 것을 아는 경우 하나만 받는다. 명령이 읽은 창을 그대로 넘겼어도 페이지가 스스로 본다
      var loaded = initialRows() || [];
      var origins = tierRows(win.root).map(function (tr, i) {
        var input = tr.querySelector('input[name="tiers_origin"]'), row = loaded[i];
        var threshold = row && row.threshold !== undefined && row.threshold !== null ? String(row.threshold) : null;
        return { origin: input ? input.value : null, own: !!input && input.value !== '' && input.value === threshold };
      });
      if (origins.some(function (o) { return o.origin !== null && C(o.origin) === UNSURE; })) fail(ORIGIN_UNKNOWN + ' — 아무것도 치지 않았고 누르지 않았습니다', { refused: true });
      var stray = origins.map(function (o) { return o.own; }).indexOf(false);
      if (stray >= 0) fail(notOwn(stray + 1) + ' — 아무것도 치지 않았고 누르지 않았습니다', { refused: true });
      var seen = marksOf(win.root).map(function (names) { return names.join(' '); });
      if (seen.join('\n') !== marks.join('\n')) {
        fail('창의 단 표식(화면에 없는 설정)이 읽은 것과 다릅니다 — 아무것도 치지 않았고 누르지 않았습니다', { refused: true, differ: ['marks'] });
      }
      K.fill(ctx, win.root, form, edits, { window: '프로모션 편집 창', settable: settable });
      return K.saveOnce(ctx, { root: win.root, panel: 'stay_promotions', window: '프로모션 편집 창', what: clip(win.offer.name + ' · ' + win.promotion.title, 120),
        no: p.no });
    }, SPEC);
  }

  window.stayPromotion = {
    version: VERSION,
    look: look,
    readPromotion: readPromotion,
    applyPromotion: applyPromotion,
    take: function (id, at, size) { return K.take(id, at, size); },
    last: function () { return K.last(); },
    idle: function () { return K.idle(); },
    ALLOW: ALLOW, CONTROLS: CONTROLS, NEVER: NEVER,
    // 시험·점검용: 작업 하나의 벽을 이 파일의 표로 세운 채 fn 을 돌린다(막기만 하고 풀어 주는 것은 없다)
    guard: function (op, fn, pins) { return K.guard(SPEC, op, fn, pins); }
  };
  return K.scrub({ ok: true, version: VERSION });
})();
