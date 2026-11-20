/* stay_addon_price.js — 부가옵션 가격 도우미의 페이지 쪽 (stay-addon-price-change). `window.stayAddonPrice` 를 만든다.
 *
 * 러너의 도우미(`stay_helper.js`)·부트(`stay_boot.js`), 가격 도우미(`stay-price-change/scripts/page/stay_price.js`)를 먼저 올리고
 * 이 파일을 올린다(올리개 `stayPriceLoader.load('addon')` 가 그 차례로 올린다). 벽 · 작업 틀 · 누르기 · 답 거르기 · 조각 · 바쁨 표지는
 * 가격 도우미의 `window.stayPageKit` 을 이 파일의 표(SPEC)로 쓴다 — 베끼지 않는다. 그래서 두 도우미를 통틀어 작업은 한 번에 하나다.
 *
 *   stayAddonPrice.look()                                         이 탭이 어디인지 — 로그인 화면 · 호텔 · 부가옵션과 가격 줄 전부(body)
 *   stayAddonPrice.readLine({hotel, addon, line})                 가격 줄 하나의 편집 창을 열어 저장 단추가 보낼 칸을 읽고 닫는다
 *   stayAddonPrice.applyLine({no, hotel, addon, line, form, set}) 그 창에 판매가 · 공급 원가만 치고 저장을 한 번 누른다
 *   stayAddonPrice.take(id, at, size) · last() · idle()           조각 받기 · 마지막 답 · 쉬는 벽 보기(가격 도우미와 같은 것)
 *
 * 지키는 것
 *  - 이 파일에는 클릭이 없다. 누르기는 모두 `stayPageKit.press` 를 지나고, 벽은 작업마다 이 파일의 허용 목록(ALLOW)만 지나게 한다.
 *    삭제 · 부가옵션 추가 · 가격 추가 · 정보 수집 폼 · 부가옵션의 [편집] · 부가옵션 설정 저장 · 적용 범위 카드 · 다른 탭은 금지(NEVER)다.
 *  - 저장 단추가 보내는 칸은 그 단추의 `hx-include`(`#<창 뿌리> :is(input,select,textarea)`)가 고르는 칸 그대로다 — 이름이 있고 막히지
 *    않은 칸, 체크·라디오는 켜진 것만, 여러 고르기는 고른 것마다 한 쌍. 이 목록(SENT)을 [이름, 값] 쌍으로 읽고 견준다.
 *  - applyLine 은 치기 전에 창의 SENT 가 앞서 읽은 form 과 꼭 같아야 하고, 친 뒤에는 form 에서 set 의 값만 바뀌어야 누른다. 공급 원가는
 *    set 이 `net_amount: ""` 로 비우라고 할 때만 빈 채로 보낸다(비면 ERP 가 저장된 원가를 지운다). 저장은 다시 누르지 않는다.
 *  - 저장 단추의 주소(hx-post)는 페이지 안에서 견주기만 하고 돌려주지 않는다.
 */
(function () {
  'use strict';

  var K = window.stayPageKit;
  if (!K) throw new Error('가격 도우미(stay_price.js)를 먼저 올려 주세요 — stayPageKit 이 없습니다');
  var VERSION = '0.1.0';
  var C = K.C, all = K.all, fail = K.fail, clip = K.clip;

  /* ───────────── 1. 벽의 표 ───────────── */

  var HEAD = ['가격행 이름', '판매가', '통화별 금액', '적용 대상', '적용 범위', '인원 밴드', '액션'];
  // 어떤 작업에서도 누르지 않는 것 — 허용 목록보다 먼저 본다
  var NEVER = [
    { sel: '[data-stay-action="delete"],[hx-delete]', why: '삭제' },
    { sel: '[data-stay-action="open_create"]', why: '부가옵션 추가 · 가격 추가' },
    { sel: '[data-stay-action="open_questions"]', why: '정보 수집 폼' },
    { sel: '.stay-addon__actions [data-stay-action="open_edit"]', why: '부가옵션 [편집]' },
    { sel: '[data-stay-screen="addon"] [data-stay-action="save"]', why: '부가옵션 설정 저장' },
    { sel: '[data-stay-card="scope"]', why: '적용 범위' },
    { sel: '[data-stay-action="archive"]', why: '보관' },
    { sel: '[data-stay-action="activate"],[data-stay-action="end"],[data-stay-card="gate"]', why: '판매 시작·종료' },
    { sel: 'ul.tab-container a:not([data-stay-tab="addons"])', why: '다른 탭' }
  ];
  var CONTROLS = {
    tab: { sel: 'ul.tab-container a[data-stay-tab="addons"]' },
    lineOpen: { sel: '#stay_addons tr[data-stay-entity="addon_price"] [data-stay-action="open_edit"]', when: 'line' },
    lineSave: { sel: '#stay_drawer_body [data-stay-screen="addon-price"] [data-stay-action="save"]', when: 'lineTarget', max: 1 }
  };
  var ALLOW = {
    look: ['tab'],
    readLine: ['tab', 'lineOpen'],
    applyLine: ['tab', 'lineOpen', 'lineSave']
  };
  function hxPost(el) { return (el && (el.getAttribute('hx-post') || el.getAttribute('data-hx-post'))) || ''; }
  function editPath(hotel, line) { return '/stay/' + hotel + '/addon-prices/' + line + '/edit/'; }
  function endsWith(text, tail) { return text.length >= tail.length && text.slice(-tail.length) === tail; }
  var WHEN = {
    // 그 카드(부가옵션 번호)의 그 줄(가격 줄 번호)의 [편집] 만
    line: function (el, pins) {
      var tr = el.closest('tr[data-stay-entity="addon_price"]'), card = el.closest('[data-stay-entity="addon"]');
      return !!(pins.line && pins.addon && tr && card) && tr.getAttribute('data-stay-entity-id') === pins.line && card.getAttribute('data-stay-entity-id') === pins.addon;
    },
    // 그 호텔 · 그 줄의 편집 주소로 저장하는 단추만
    lineTarget: function (el, pins) { return !!(pins.hotel && pins.line) && endsWith(hxPost(el), editPath(pins.hotel, pins.line)); }
  };
  var SPEC = {
    name: 'stayAddonPrice', allow: ALLOW, controls: CONTROLS, when: WHEN, never: NEVER, late: [],
    saves: { applyLine: 'lineSave' }, needs: ['calSet'], loose: ['look'],
    tidy: function (op, untilMs) { return K.closeDrawer(untilMs); }
  };

  /* ───────────── 2. 목록 — 부가옵션 탭의 카드와 가격 줄 ───────────── */

  function tab() { return document.querySelector(CONTROLS.tab.sel); }
  function panel() { return document.querySelector('#stay_addons[data-stay-panel="addons"]'); }
  function tabOn() { var a = tab(); return !!a && (a.classList.contains('active') || !!a.closest('li.active')); }
  function shown() { return tabOn() && !!panel(); }
  // 목록이 보이지 않을 때만 [부가옵션] 탭을 누르고(탭이 이미 켜졌으면 누르지 않는다 — 스텁이 스스로 목록을 불러온다), 목록 조각이 오고
  // 도는 요청이 없을 때 넘어간다
  async function toAddons(ctx) {
    if (!tabOn()) {
      if (!tab()) fail('[부가옵션] 탭을 찾지 못했습니다');
      await K.press(ctx, '[부가옵션] 탭', tab);
    }
    return K.settle(ctx, panel, shown, '부가옵션 목록이 열리지 않았습니다');
  }
  function cards(root) { return all('[data-stay-entity="addon"]', root); }
  function rowsOf(card) { return all('tr[data-stay-entity="addon_price"]', card); }
  function withId(list, id) { return list.filter(function (el) { return el.getAttribute('data-stay-entity-id') === id; })[0] || null; }
  function cells(row) { return [].slice.call(row.children).filter(function (el) { return el.localName === 'td'; }); }
  // 줄 하나 — 표의 머리가 꼭 그 일곱 칸일 때만 읽는다(ERP 가 칸을 바꿨으면 다른 칸을 값으로 읽지 않게)
  function lineOf(row) {
    var table = row.closest('table');
    var head = table ? all('thead th', table).map(function (th) { return C(th.textContent); }) : [];
    if (head.join('/') !== HEAD.join('/')) {
      fail('부가옵션 가격 표의 머리가 「' + HEAD.join(' / ') + '」 가 아닙니다(화면: ' + (head.join(' / ') || '없음') + ') — ERP 화면이 바뀌었을 수 있어 읽지 않습니다');
    }
    var td = cells(row);
    if (td.length !== HEAD.length) fail('부가옵션 가격 줄의 칸이 ' + td.length + '개입니다 — ' + HEAD.length + '칸이어야 읽습니다');
    return {
      id: row.getAttribute('data-stay-entity-id') || '',
      name: C(row.getAttribute('data-stay-name')),
      sell: C(td[1].textContent),
      values: [].slice.call(td[2].children).filter(function (el) { return el.localName === 'div'; }).map(function (el) { return C(el.textContent); }),
      target: C(td[3].textContent),
      scope: C(td[4].textContent),
      band: C(td[5].textContent)
    };
  }
  // 카드 메타 표에서 머리 「오퍼」 옆 칸
  function offerOf(card) {
    var th = all('.stay-addon__meta th', card).filter(function (el) { return C(el.textContent) === '오퍼'; })[0];
    var td = th && th.nextElementSibling;
    return td ? C(td.textContent) : '';
  }
  function addonOf(card) { return { id: card.getAttribute('data-stay-entity-id') || '', name: C(card.getAttribute('data-stay-name')) }; }

  /* ───────────── 3. 편집 창 — 연 창이 그 호텔 · 그 줄의 것인지, 저장 단추가 보낼 칸 ───────────── */

  function windowRoot() { return document.querySelector('#stay_drawer_body [data-stay-screen="addon-price"]'); }
  function saveOf(root) { return root ? root.querySelector('[data-stay-action="save"]') : null; }
  // 저장 단추가 보낼 [이름, 값] 목록 — hx-include 가 이 창 뿌리의 칸 전부일 때만 안다(아니면 null)
  function sent(root) {
    var save = saveOf(root);
    var include = save ? (save.getAttribute('hx-include') || save.getAttribute('data-hx-include') || '') : '';
    if (!root.id || include !== '#' + root.id + ' :is(input,select,textarea)') return null;
    var out = [];
    all('input,select,textarea', root).forEach(function (el) {
      if (!el.name || el.matches(':disabled')) return;
      if (el.localName === 'input' && (el.type === 'checkbox' || el.type === 'radio')) { if (el.checked) out.push([el.name, el.value]); return; }
      if (el.localName === 'select' && el.multiple) { [].forEach.call(el.options, function (o) { if (o.selected) out.push([el.name, o.value]); }); return; }
      out.push([el.name, el.value]);
    });
    return out;
  }
  function errorsOf(root) { return all('[data-stay-result="error"], small.error', root).map(function (el) { return C(el.textContent); }).filter(Boolean); }
  function windowFacts(root, form) {
    var labels = {};
    all('select', root).forEach(function (s) { if (s.name) labels[s.name] = s.selectedIndex >= 0 ? C(s.options[s.selectedIndex].textContent) : ''; });
    return {
      title: C((document.querySelector('.stay-drawer__title') || {}).textContent),
      addon: C((root.querySelector('[data-stay-card="main"] .stay-section-title') || {}).textContent),
      form: form, labels: labels, errors: errorsOf(root)
    };
  }
  // 그 카드의 그 줄을 찾아 [편집] 을 누르고, 열린 창이 그 호텔 · 그 줄의 편집 창인지 본다. 목록에 그 줄이 없으면 아무것도 누르지 않고 null
  async function openLine(ctx, want, refusal) {
    var root = await toAddons(ctx);
    var card = withId(cards(root), want.addon);
    var row = card && withId(rowsOf(card), want.line);
    if (!row) return null;
    var line = lineOf(row);
    ctx.pins.hotel = ctx.hotel.id;
    ctx.pins.addon = want.addon;
    ctx.pins.line = want.line;
    await K.press(ctx, '`' + line.name + '` 줄 [편집]', function () {
      var c = withId(cards(panel() || document), want.addon), r = c && withId(rowsOf(c), want.line);
      return r ? r.querySelector('[data-stay-action="open_edit"]') : null;
    });
    var win = await K.settle(ctx, windowRoot, function (r) { return !!saveOf(r) && K.drawerOpen(); }, '가격 편집 창이 열리지 않았습니다');
    if (!endsWith(hxPost(saveOf(win)), editPath(ctx.hotel.id, want.line))) fail('열린 창이 고른 줄(' + want.line + ')의 가격 편집 창이 아닙니다 — 아무것도 치지 않았습니다', refusal);
    return { root: win, addon: addonOf(card), line: line };
  }
  function ids(p) {
    var id = function (value, name) {
      if (typeof value !== 'string' || !/^\d+$/.test(value)) fail('`' + name + '` 은 ERP 가 매긴 번호 글자입니다(look() 의 id 그대로, 예: "301")');
      return value;
    };
    return { addon: id(p.addon, 'addon'), line: id(p.line, 'line') };
  }

  /* ───────────── 4. 보기 하나와 작업 둘 ───────────── */

  // 이 탭이 어디인지와 부가옵션 · 가격 줄 전부. 저장하지 않는다. 누르는 것은 (목록이 안 보이면) [부가옵션] 탭 하나다. 목록은 늘 body 로 둔다
  function look(input) {
    input = input && typeof input === 'object' ? input : {};
    return K.run('look', input, async function (p, ctx) {
      var root = await toAddons(ctx);
      var addons = cards(root).map(function (card) {
        var addon = addonOf(card);
        return { id: addon.id, name: addon.name, offer: offerOf(card), lines: rowsOf(card).map(lineOf) };
      });
      var lines = addons.reduce(function (n, a) { return n + a.lines.length; }, 0);
      return { ok: true, login: false, hotel: ctx.hotel, count: { addons: addons.length, lines: lines }, keep: { hotel: ctx.hotel, addons: addons } };
    }, SPEC);
  }

  // 가격 줄 하나의 편집 창 — 연 창이 그 줄의 것인지 본 뒤 저장 단추가 보낼 칸(form) · select 의 보이는 글자 · 오류를 읽고 드로어를
  // `stay-drawer-close` 로 닫는다. 저장은 누르지 않는다. 목록에 그 줄이 없으면 {missing: true} 이고 더 누르지 않는다
  function readLine(input) {
    return K.run('readLine', input, async function (p, ctx) {
      var want = ids(p);
      var win = await openLine(ctx, want, {});
      if (!win) return { ok: true, missing: true, note: '목록에 그 부가옵션의 그 가격 줄이 없습니다 — 아무것도 열지 않았습니다' };
      var form = sent(win.root);
      if (!form) fail('가격 편집 창의 저장 단추가 무엇을 보내는지 알 수 없어(hx-include) 읽지 않았습니다');
      var facts = windowFacts(win.root, form);
      await K.closeDrawer(Date.now() + 3000);
      if (K.drawerOpen()) fail('읽은 뒤 드로어를 닫지 못했습니다');
      return { ok: true, what: clip(win.addon.name + ' · ' + win.line.name, 120),
        keep: { hotel: ctx.hotel, addon: win.addon, line: win.line, window: facts } };
    }, SPEC);
  }

  var AMOUNT = /^\d+(\.\d+)?$/;
  var SETTABLE = { price: '판매가', net_amount: '공급 원가' };
  function pairs(value) {
    var bad = !Array.isArray(value) || !value.length || value.some(function (x) {
      return !Array.isArray(x) || x.length !== 2 || typeof x[0] !== 'string' || typeof x[1] !== 'string';
    });
    if (bad) fail('`form` 은 readLine 이 돌려준 window.form([이름, 값] 목록) 그대로입니다');
    return value.map(function (x) { return [x[0], x[1]]; });
  }
  function valueOf(list, name) { var hit = list.filter(function (x) { return x[0] === name; })[0]; return hit ? hit[1] : null; }
  // 두 [이름, 값] 목록이 다른 칸 이름들. 이름마다 값 목록을 견주고, 같은데 차례만 다르면 「(칸 순서)」
  function differs(seen, want) {
    var group = function (list) { var out = Object.create(null); list.forEach(function (x) { (out[x[0]] = out[x[0]] || []).push(x[1]); }); return out; };
    var a = group(seen), b = group(want), names = [];
    Object.keys(a).concat(Object.keys(b)).forEach(function (name) {
      if (names.indexOf(name) < 0 && JSON.stringify(a[name] || []) !== JSON.stringify(b[name] || [])) names.push(name);
    });
    if (!names.length && JSON.stringify(seen) !== JSON.stringify(want)) names.push('(칸 순서)');
    return names;
  }
  // 저장됐다는 표지 — ERP 저장 응답이 갈아 끼우는 `#stay_save_result` 의 저장 시각과, 새로 온 목록의 저장 배너
  function saveSigns() {
    var mark = document.getElementById('stay_save_result'), list = document.getElementById('stay_addons');
    return {
      stamp: mark && mark.getAttribute('data-stay-result') === 'saved' ? mark.getAttribute('data-stay-saved-at') : null,
      panel: list, banner: list ? list.querySelector('[data-stay-result="saved"]') : null
    };
  }

  // 가격 줄 하나 저장 — 창을 readLine 처럼 연다. 치기 전에 창의 SENT 가 form 과 꼭 같고, 친 뒤에는 form 에서 set 의 칸만 바뀌어야
  // 저장 단추를 한 번 누른다. 누르기 전에 멈추면 refused · saved false · pressed false
  function applyLine(input) {
    return K.run('applyLine', input, async function (p, ctx) {
      var want = ids(p);
      var form = pairs(p.form);
      var set = p.set && typeof p.set === 'object' && !Array.isArray(p.set) ? p.set : null;
      if (!set || !Object.keys(set).length) fail('`set` 은 바꿀 칸(price · net_amount)과 금액 글자입니다');
      Object.keys(set).forEach(function (name) {
        if (!SETTABLE[name]) fail('`set` 에는 price(판매가) · net_amount(공급 원가)만 넣습니다: ' + clip(name, 30));
        var value = set[name];
        if (typeof value !== 'string' || !(AMOUNT.test(value) || (name === 'net_amount' && value === ''))) {
          fail('`set.' + name + '` 은 금액 글자(예: "24.22")입니다' + (name === 'net_amount' ? ' — 공급 원가를 지울 때만 ""' : ''));
        }
        if (form.filter(function (x) { return x[0] === name; }).length !== 1) fail('`form` 에 ' + name + ' 칸이 하나가 아닙니다 — readLine 의 form 을 그대로 넣습니다');
      });
      var refused = { refused: true };
      var win = await openLine(ctx, want, refused);
      if (!win) fail('목록에 그 부가옵션의 그 가격 줄이 없습니다 — 저장하지 않았습니다', { refused: true, missing: true });
      var before = sent(win.root);
      if (!before) fail('가격 편집 창의 저장 단추가 무엇을 보내는지 알 수 없어(hx-include) 저장하지 않았습니다', refused);
      var off = differs(before, form);
      if (off.length) {
        fail('창의 값이 읽은 값과 다릅니다(' + off.join(', ') + ') — 아무것도 치지 않았습니다. 다시 읽고 미리보기를 새로 만듭니다', { refused: true, differ: off });
      }
      Object.keys(set).forEach(function (name) {
        var hits = all('input,select,textarea', win.root).filter(function (el) { return el.name === name; });
        if (hits.length !== 1 || hits[0].localName !== 'input') fail('창에 ' + SETTABLE[name] + '(' + name + ') 칸이 하나가 아닙니다 — 저장하지 않았습니다', refused);
        window.calSet(hits[0], set[name]);
        if (hits[0].value !== set[name]) fail(SETTABLE[name] + ' 칸에 값이 들어가지 않았습니다 — 저장하지 않았습니다', refused);
      });
      ctx.check();
      var after = sent(win.root) || [];
      var expected = form.map(function (x) { return [x[0], Object.prototype.hasOwnProperty.call(set, x[0]) ? set[x[0]] : x[1]]; });
      // 공급 원가는 비우라고 한 때만 빈 채로 보낸다 — 비면 ERP 가 저장된 원가를 지운다
      var hadNet = C(valueOf(form, 'net_amount') || '') !== '', nowNet = C(valueOf(after, 'net_amount') || '');
      if (hadNet && !nowNet && set.net_amount !== '') fail('공급 원가가 빈 채로 저장될 뻔했습니다(비면 저장된 원가가 지워집니다) — 저장하지 않았습니다', refused);
      var off2 = differs(after, expected);
      if (off2.length) fail('친 뒤의 창이 바꾼 칸 말고도 다릅니다(' + off2.join(', ') + ') — 저장하지 않았습니다', { refused: true, differ: off2 });

      var signs = saveSigns(), rootId = win.root.id;
      await K.press(ctx, '가격 편집 창 [저장]', function () { return windowRoot() === win.root ? saveOf(win.root) : null; });
      var pressed = ctx.wall.pressed('lineSave');
      // 저장됨: 창이 사라지고 저장 표지(저장 시각이 바뀌었거나 새 목록의 저장 배너)가 왔다. 거절: 창이 오류와 함께 다시 그려졌다
      var outcome = function () {
        var now = saveSigns(), r = windowRoot();
        var stamped = !!now.stamp && now.stamp !== signs.stamp;
        var fresh = !!now.banner && (now.panel !== signs.panel || now.banner !== signs.banner);
        var redrawn = !!r && (r !== win.root || r.id !== rootId) && errorsOf(r).length > 0;
        return { saved: !r && (stamped || fresh), refused: redrawn, errors: redrawn ? errorsOf(r) : [] };
      };
      await ctx.wait(function () { var o = outcome(); return K.quiet() && (o.saved || o.refused); }, 10000);
      var done = outcome();
      var saved = !pressed ? false : done.saved ? true : done.refused ? false : 'unknown';
      var out = { ok: saved === true, what: clip(win.addon.name + ' · ' + win.line.name, 120), saved: saved, pressed: pressed };
      if (saved === true) out.note = '저장했습니다';
      else if (pressed && done.refused) {
        out.error = '가격 편집 창이 저장을 거절했습니다 — ' + done.errors.join(' / ');
        out.errors = done.errors.slice(0, 3).map(function (e) { return clip(e, 60); });
      } else if (pressed) out.error = '[저장] 은 눌렸고 저장됐는지 알 수 없습니다 — 다시 읽어 확인합니다(다시 누르지 않았습니다)';
      else out.error = '저장 단추를 누르지 못했습니다';
      return out;
    }, SPEC);
  }

  window.stayAddonPrice = {
    version: VERSION,
    look: look,
    readLine: readLine,
    applyLine: applyLine,
    take: function (id, at, size) { return K.take(id, at, size); },
    last: function () { return K.last(); },
    idle: function () { return K.idle(); },
    ALLOW: ALLOW, CONTROLS: CONTROLS, NEVER: NEVER,
    // 시험·점검용: 작업 하나의 벽을 이 파일의 표로 세운 채 fn 을 돌린다(막기만 하고 풀어 주는 것은 없다)
    guard: function (op, fn, pins) { return K.guard(SPEC, op, fn, pins); }
  };
  return K.scrub({ ok: true, version: VERSION });
})();
