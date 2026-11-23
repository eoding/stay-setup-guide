/* stay_price_season.js — 가격 캘린더 도우미의 시즌 창 쪽 (stay-price-change). `window.stayPriceSeason` 을 만든다.
 *
 * 러너의 도우미(`stay_helper.js`)·부트(`stay_boot.js`), 가격 도우미(`stay_price.js`)를 먼저 올리고 이 파일을 올린다(올리개
 * `stayPriceLoader.load('season')` 가 그 차례로 올린다). 벽 · 작업 틀 · 누르기 · 답 거르기 · 조각 · 바쁨 표지는 가격 도우미의
 * `window.stayPageKit` 을 이 파일의 표(SPEC)로 쓴다 — 베끼지 않는다. 그래서 도우미들을 통틀어 작업은 한 번에 하나다.
 *
 *   stayPriceSeason.readSeason({hotel, offer, season: {id} | {name}, datesOnly})
 *        시즌 탭의 그 시즌 [가격 입력] 창을 열어 읽고 닫는다 — 열린 그대로의 칸(form) · 칸 차례(order) · 객실 · 요금제 · 아동 칸 ·
 *        시즌 날(창의 data-date-allowed), 마지막 입력값이 채워져 열렸으면 [비우기] 한 창의 칸(blank). 편집 화면에 이미 있는 요금제
 *        탭 목록(요금제 번호 → 캘린더의 객실 · 요금제 이름, 기준 ✓, 정렬) · 객실 타입 목록(허용 인원 조합) · 시즌 목록도 클릭 없이
 *        읽는다. 답은 늘 조각(body)이다. datesOnly 면 시즌 날까지만 읽고 닫는다
 *   stayPriceSeason.applySeason({no, hotel, offer, season, dates, form, want, candidates, child})
 *        그 창을 열어, 창이 미리보기 때와 같은지 먼저 보고(시즌 · 날 · 객실 · 요금제 · 아동 글 · 보낼 칸 = form), 같을 때만 금액 · 글
 *        칸을 치고 객실 → 요금제 → 덮기 체크를 want 쪽으로 누르고 날짜 칸을 친 뒤, 보낼 칸이 want 와 꼭 같을 때만 [가격 적용]을 한
 *        번 누른다. 저장됨은 ERP 의 저장 표지와 시즌 목록의 저장 띠(새로 · 덮어쓴 · 건너뛴 칸 수)로 안다
 *   stayPriceSeason.take(id, at, size) · last() · idle()     조각 받기 · 마지막 답 · 쉬는 벽 보기(가격 도우미와 같은 것)
 *
 * 지키는 것
 *  - 이 파일에는 클릭이 없다. 누르기는 모두 `stayPageKit.press` 를 지나고, 벽은 작업마다 이 파일의 허용 목록(ALLOW)만 지나게 한다.
 *    삭제 · 시즌 [편집] · 판매 마감·해제 · 「이번에 고르지 않은 인원·요금제 가격 지우기」 · 날짜 달력의 단추 · 보관 · 판매 시작·종료 ·
 *    다른 탭은 금지(NEVER)다. 지우기 칸은 무슨 일이 있어도 켜지 않는다 — want 에 있으면 아무것도 누르지 않는다.
 *  - 체크는 그것을 want 쪽으로 옮기는 클릭만 지난다(toward). [가격 적용]은 창이 그 호텔 · 그 시즌의 것이고 보낼 칸이 want 와 꼭 같은
 *    순간에만, 한 번만 지난다(target · max 1). 시간이 다 돼도 다시 누르지 않는다 — 눌린 뒤면 saved 는 "unknown".
 *  - 날짜 칸(textarea)은 러너의 calSet 이 다루지 못해(input 의 값 setter) 같은 방식(값 setter + input · change 사건)으로 친다.
 *  - 저장 단추의 주소(hx-post)는 페이지 안에서 견주기만 하고 돌려주지 않는다.
 */
(function () {
  'use strict';

  var K = window.stayPageKit;
  if (!K) throw new Error('가격 도우미(stay_price.js)를 먼저 올려 주세요 — stayPageKit 이 없습니다');
  var VERSION = '0.1.0';
  var C = K.C, all = K.all, fail = K.fail, clip = K.clip;
  var SCREEN = '[data-stay-screen="season-price-fill"]';
  var IN_DRAWER = '#stay_drawer_body ' + SCREEN;

  /* ───────────── 1. 벽의 표 ───────────── */

  var NEVER = [
    { sel: '[data-stay-action="delete"],[hx-delete]', why: '삭제' },
    { sel: '#stay_seasons [data-stay-action="open_edit"]', why: '시즌 [편집]' },
    { sel: '#stay_seasons [data-stay-action="open_tab"]', why: '판매 마감·해제' },
    { sel: SCREEN + ' input[name="stale_cleanup"]', why: '이번에 고르지 않은 인원·요금제 가격 지우기' },
    { sel: SCREEN + ' [data-date-mode],' + SCREEN + ' [data-date-month],' + SCREEN + ' [data-date-clear],' + SCREEN + ' [data-date-grid]', why: '날짜 달력' },
    { sel: '[data-stay-action="archive"]', why: '보관' },
    { sel: '[data-stay-action="activate"],[data-stay-action="end"],[data-stay-card="gate"]', why: '판매 시작·종료' },
    { sel: 'ul.tab-container a:not([data-stay-tab="seasons"])', why: '다른 탭' }
  ];
  var CONTROLS = {
    tab: { sel: 'ul.tab-container a[data-stay-tab="seasons"]' },
    fillOpen: { sel: '#stay_seasons tr[data-stay-entity="season"] [data-stay-action="fill"]', when: 'season' },
    blank: { sel: IN_DRAWER + ' [data-stay-action="reset"]', when: 'window' },
    room: { sel: IN_DRAWER + ' input[type="checkbox"][name="rooms"]', when: 'toward' },
    plan: { sel: IN_DRAWER + ' input[type="checkbox"][name="rate_plans"]', when: 'toward' },
    overwrite: { sel: IN_DRAWER + ' input[type="checkbox"][name="overwrite"]', when: 'toward' },
    save: { sel: IN_DRAWER + ' [data-stay-action="save"]', when: 'target', max: 1 }
  };
  var ALLOW = {
    readSeason: ['tab', 'fillOpen', 'blank'],
    applySeason: ['tab', 'fillOpen', 'room', 'plan', 'overwrite', 'save']
  };
  function hxPost(el) { return (el && (el.getAttribute('hx-post') || el.getAttribute('data-hx-post'))) || ''; }
  function endsWith(text, tail) { return text.length >= tail.length && text.slice(-tail.length) === tail; }
  function fillPath(hotel, season) { return '/stay/' + hotel + '/seasons/' + season + '/fill/'; }
  function windowRoot() { return document.querySelector(IN_DRAWER); }
  function saveOf(root) { return root ? root.querySelector('[data-stay-action="save"]') : null; }
  // 열린 창이 그 호텔 · 그 시즌의 [가격 입력] 창인가 — 저장 단추의 주소로 본다
  function ours(root, pins) { return !!(root && pins.hotel && pins.season) && endsWith(hxPost(saveOf(root)), fillPath(pins.hotel, pins.season)); }
  function wanted(pins, el) { return (pins.want || []).some(function (x) { return x[0] === el.name && x[1] === el.value; }); }
  var WHEN = {
    season: function (el, pins) { var tr = el.closest('tr[data-stay-entity="season"]'); return !!(tr && pins.season) && tr.getAttribute('data-stay-entity-id') === pins.season; },
    window: function (el, pins) { return ours(el.closest(SCREEN), pins); },
    // 체크의 클릭 사건이 벽에 닿을 때 브라우저는 이미 체크를 바꿔 두었다(막으면 되돌린다) — 바뀐 상태가 want 와 같아야 지난다
    toward: function (el, pins) { return !!pins.want && ours(el.closest(SCREEN), pins) && el.checked === wanted(pins, el); },
    target: function (el, pins) {
      var root = el.closest(SCREEN);
      if (!pins.want || !ours(root, pins)) return false;
      var sent = K.sent(root);
      return !!sent && K.differs(sent, pins.want).length === 0;
    }
  };
  var SPEC = {
    name: 'stayPriceSeason', allow: ALLOW, controls: CONTROLS, when: WHEN, never: NEVER, late: [],
    saves: { applySeason: 'save' }, needs: [], loose: [],
    // 저장 요청이 아직 돌면 드로어를 닫지 않는다 — 닫으면 그 저장의 끝을 못 본다(다음 작업은 요청이 끝날 때까지 시작하지 않는다)
    tidy: function (op, untilMs) { return K.quiet() ? K.closeDrawer(untilMs) : null; },
    // 시즌이 길면 ERP 가 저장에 10초를 넘게 쓴다 — 45초 호출 안에서 더 기다린다(hardMs 40초 + 정리 4초)
    limits: { applySeason: { budgetMs: 38000, hardMs: 40000 } }
  };

  /* ───────────── 2. 시즌 목록과 편집 화면에 이미 있는 목록 ───────────── */

  function tab() { return document.querySelector(CONTROLS.tab.sel); }
  function panel() { return document.querySelector('#stay_seasons[data-stay-panel="seasons"]'); }
  function tabOn() { var a = tab(); return !!a && (a.classList.contains('active') || !!a.closest('li.active')); }
  async function toSeasons(ctx) {
    if (!tabOn()) {
      if (!tab()) fail('[시즌] 탭을 찾지 못했습니다');
      await K.press(ctx, '[시즌] 탭', tab);
    }
    return K.settle(ctx, panel, function () { return tabOn(); }, '시즌 목록이 열리지 않았습니다');
  }
  function cardOf(root, offer) {
    return all('[data-stay-entity="offer"]', root).filter(function (card) { return C(card.getAttribute('data-stay-name')) === offer; })[0] || null;
  }
  function seasonRows(card) { return all('tr[data-stay-entity="season"]', card); }
  function numbers(tr) { return all('td.stay-numeric', tr).map(function (td) { return C(td.textContent); }); }
  function seasonOf(tr) { return { id: tr.getAttribute('data-stay-entity-id') || '', name: C(tr.getAttribute('data-stay-name')), days: numbers(tr)[1] || '' }; }
  // 그 오퍼의 그 시즌 줄 — 번호로, 번호가 없으면 이름으로(이름이 같은 시즌이 둘이면 번호를 대라고 거절)
  function rowOf(card, want) {
    var rows = seasonRows(card);
    var hit = rows.filter(function (tr) {
      return want.id ? tr.getAttribute('data-stay-entity-id') === want.id : C(tr.getAttribute('data-stay-name')) === want.name;
    });
    var names = rows.map(function (tr) { var s = seasonOf(tr); return s.name + '(' + s.id + ')'; }).join(' / ') || '없음';
    if (!hit.length) fail('그 오퍼에 시즌 `' + clip(want.id || want.name, 40) + '` 이 없습니다 — 이 오퍼의 시즌: ' + clip(names, 200));
    if (hit.length > 1) fail('이름이 `' + clip(want.name, 40) + '` 인 시즌이 둘 이상입니다 — season 에 번호(id)를 줍니다: ' + clip(names, 200));
    return hit[0];
  }
  // 요금제 탭 목록(편집 화면이 열릴 때 함께 불러온다) — 그 오퍼의 요금제 줄마다 번호 · 객실 번호와 이름 · 요금제 이름 · 기준(✓) · 정렬
  function ratePlans(offer) {
    return all('#stay_rate_plans tbody[data-workspace-room-name]').filter(function (body) {
      return C(body.getAttribute('data-workspace-offer-name')) === offer;
    }).reduce(function (out, body) {
      return out.concat(all('tr[data-stay-entity="rate_plan"]', body).map(function (tr) {
        var tick = all('.stay-badge--tinted', tr).some(function (b) { return C(b.textContent) === '✓'; });
        return { id: tr.getAttribute('data-stay-entity-id') || '', roomId: body.getAttribute('data-workspace-room') || '',
          room: C(body.getAttribute('data-workspace-room-name')), plan: C(tr.getAttribute('data-stay-name')), base: tick,
          sort: numbers(tr)[0] || '' };
      }));
    }, []);
  }
  // 객실 타입 목록 — 이름과 「허용 인원 조합」 칸(머리로 그 칸을 찾는다)
  function roomTypes() {
    var table = document.querySelector('#stay_room_types tr[data-stay-entity="room_type"]');
    table = table && table.closest('table');
    if (!table) return [];
    var head = all('thead th', table).map(function (th) { return C(th.textContent); });
    var at = head.indexOf('허용 인원 조합');
    return all('tr[data-stay-entity="room_type"]', table).map(function (tr) {
      var td = [].slice.call(tr.children).filter(function (el) { return el.localName === 'td'; })[at];
      return { name: C(tr.getAttribute('data-stay-name')), combos: at >= 0 && td ? C(td.textContent) : null };
    });
  }
  function bannerText() {
    var banner = document.querySelector('#stay_seasons [data-stay-result="saved"]');
    return banner ? clip(C(banner.textContent), 300) : null;
  }

  /* ───────────── 3. 창 ───────────── */

  async function openWindow(ctx, seasonId, refusal) {
    await K.press(ctx, '시즌 [가격 입력]', function () {
      var tr = all('#stay_seasons tr[data-stay-entity="season"]').filter(function (row) { return row.getAttribute('data-stay-entity-id') === seasonId; })[0];
      return tr ? tr.querySelector('[data-stay-action="fill"]') : null;
    });
    var root = await K.settle(ctx, windowRoot, function (r) { return !!saveOf(r) && K.drawerOpen(); }, '시즌 [가격 입력] 창이 열리지 않았습니다');
    if (!ours(root, ctx.pins)) fail('열린 창이 고른 시즌(' + seasonId + ')의 [가격 입력] 창이 아닙니다 — 아무것도 치지 않았습니다', refusal);
    return root;
  }
  function allowed(root) {
    var box = root.querySelector('[data-stay-date-selection]');
    return box ? (box.getAttribute('data-date-allowed') || '').split(',').map(C).filter(Boolean) : [];
  }
  function labelOf(input) { var label = input.closest('label'); return C(label ? label.textContent : ''); }
  function boxes(root, name) { return all('input[type="checkbox"][name="' + name + '"]', root); }
  function childFields(root) {
    return all('input[name^="child_extra_"]', root).map(function (el) {
      return { field: el.name, editable: !el.disabled, value: el.value, text: el.disabled ? C(el.value) : '' };
    });
  }
  function order(root) {
    var seen = [];
    all('input,select,textarea', root).forEach(function (el) { if (el.name && !el.matches(':disabled') && seen.indexOf(el.name) < 0) seen.push(el.name); });
    return seen;
  }
  function facts(root) {
    var form = K.sent(root);
    if (!form) fail('시즌 [가격 입력] 창의 저장 단추가 무엇을 보내는지 알 수 없어(hx-include) 읽지 않았습니다');
    var note = root.querySelector('.stay-banner--info [data-stay-action="reset"]');
    return {
      form: form, order: order(root),
      rooms: boxes(root, 'rooms').map(function (b) { return { id: b.value, label: labelOf(b) }; }),
      plans: boxes(root, 'rate_plans').map(function (b) { return { id: b.value, roomId: b.getAttribute('data-room-id') || '', label: labelOf(b) }; }),
      child: childFields(root),
      note: note ? C(note.closest('.stay-banner--info').querySelector('span').textContent) : ''
    };
  }
  function seasonWant(p) {
    var s = p.season && typeof p.season === 'object' ? p.season : null;
    var id = s && typeof s.id === 'string' && /^\d+$/.test(s.id) ? s.id : '';
    var name = s && typeof s.name === 'string' ? C(s.name) : '';
    if (!id && !name) fail('`season` 은 {id: "8801"} 이나 {name: "Peak"} 입니다(시즌 목록의 번호 · 이름 그대로)');
    if (typeof p.offer !== 'string' || !C(p.offer)) fail('`offer` 는 오퍼 이름입니다(look() 의 offer 그대로)');
    return { offer: C(p.offer), id: id, name: name };
  }

  /* ───────────── 4. 작업 둘 ───────────── */

  function readSeason(input) {
    return K.run('readSeason', input, async function (p, ctx) {
      var want = seasonWant(p);
      var root = await toSeasons(ctx);
      var card = cardOf(root, want.offer);
      if (!card) fail('시즌 목록에 오퍼 `' + clip(want.offer, 40) + '` 이 없습니다');
      var row = rowOf(card, want), season = seasonOf(row);
      ctx.pins.hotel = ctx.hotel.id;
      ctx.pins.season = season.id;
      var win = await openWindow(ctx, season.id, {});
      var dates = allowed(win);
      var what = clip(want.offer + ' · ' + season.name, 120);
      if (p.datesOnly) {
        await K.closeDrawer(Date.now() + 3000);
        return { ok: true, what: what, count: { dates: dates.length }, keep: { offer: want.offer, season: season, dates: dates } };
      }
      var read = facts(win), blank = null;
      var title = C((document.querySelector('.stay-drawer__title') || {}).textContent);
      if (read.note) {
        // 마지막 입력값이 채워져 열렸다 — [비우기] 로 기본값(구간 기본 금액 · 덮기)을 본다. 기억은 지워지지 않는다(ERP `?blank=1`)
        await K.press(ctx, '[비우기]', function () { var r = windowRoot(); return r === win ? r.querySelector('[data-stay-action="reset"]') : null; });
        var fresh = await K.settle(ctx, windowRoot, function (r) { return r !== win && !!saveOf(r); }, '[비우기] 한 창이 오지 않았습니다');
        if (!ours(fresh, ctx.pins)) fail('[비우기] 한 창이 그 시즌의 창이 아닙니다');
        blank = { form: K.sent(fresh), child: childFields(fresh) };
      }
      await K.closeDrawer(Date.now() + 3000);
      if (K.drawerOpen()) fail('읽은 뒤 드로어를 닫지 못했습니다');
      return {
        ok: true, what: what, count: { dates: dates.length, rooms: read.rooms.length, plans: read.plans.length },
        keep: { offer: want.offer, season: season, title: title, dates: dates, form: read.form, order: read.order, rooms: read.rooms,
          plans: read.plans, child: read.child, note: read.note, blank: blank, ratePlans: ratePlans(want.offer), roomTypes: roomTypes(),
          seasons: seasonRows(card).map(seasonOf), banner: bannerText() }
      };
    }, SPEC);
  }

  var TEXT = ['price', 'original_price', 'net_price', 'plan_adjust', 'occupancy_keys', 'occupancy_adjust', 'los_prices'];
  var BOXES = [['rooms', '객실'], ['rate_plans', '요금제'], ['overwrite', '덮기']];
  function valueOf(list, name) { var hit = list.filter(function (x) { return x[0] === name; }); return hit.length === 1 ? hit[0][1] : null; }
  // 글 칸 하나에 값을 넣는다 — 값 setter(input · textarea 저마다의 것) + input · change 사건. 화면 스크립트(Alpine)가 듣는다
  function setText(el, value) {
    var proto = el.localName === 'textarea' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    var dsc = Object.getOwnPropertyDescriptor(proto, 'value');
    if (dsc && dsc.set) dsc.set.call(el, value); else el.value = value;
    ['input', 'change'].forEach(function (e) { el.dispatchEvent(new Event(e, { bubbles: true })); });
  }
  function typeAll(root, want, names) {
    names.forEach(function (name) {
      var value = valueOf(want, name);
      if (value === null) return;
      var els = all('[name="' + name + '"]', root).filter(function (el) { return !el.matches(':disabled'); });
      if (els.length !== 1 || !(els[0].localName === 'textarea' || (els[0].localName === 'input' && els[0].type !== 'checkbox' && els[0].type !== 'radio'))) {
        fail('창에 `' + clip(name, 30) + '` 글 칸이 하나가 아닙니다 — 저장하지 않았습니다', { refused: true });
      }
      if (els[0].value === value) return;
      setText(els[0], value);
      if (els[0].value !== value) fail('`' + clip(name, 30) + '` 칸에 값이 들어가지 않았습니다 — 저장하지 않았습니다', { refused: true });
    });
  }
  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function checkInput(p) {
    var want = K.pairs(p.want, 'calls 의 want'), form = K.pairs(p.form, 'calls 의 form');
    if (want.some(function (x) { return x[0] === 'stale_cleanup'; })) fail('「이번에 고르지 않은 인원·요금제 가격 지우기」는 켜지 않습니다 — 저장하지 않았습니다', { refused: true });
    if (!Array.isArray(p.dates) || !p.dates.length || p.dates.some(function (d) { return typeof d !== 'string'; })) fail('`dates` 는 시즌 날 목록입니다');
    var cand = p.candidates;
    if (!cand || !Array.isArray(cand.rooms) || !Array.isArray(cand.plans)) fail('`candidates` 는 {rooms, plans} 입니다(readSeason 의 객실 · 요금제 그대로)');
    if (!Array.isArray(p.child)) fail('`child` 는 [칸 이름, 읽기 전용 글] 목록입니다');
    return { want: want, form: form };
  }

  function applySeason(input) {
    return K.run('applySeason', input, async function (p, ctx) {
      var want = seasonWant(p);
      if (!want.id) fail('`season` 에 번호(id)가 있어야 저장합니다', { refused: true });
      var lists = checkInput(p);
      ctx.pins.hotel = ctx.hotel.id;
      ctx.pins.season = want.id;
      ctx.pins.want = lists.want;
      var root = await toSeasons(ctx);
      var card = cardOf(root, want.offer);
      if (!card) fail('시즌 목록에 오퍼 `' + clip(want.offer, 40) + '` 이 없습니다 — 저장하지 않았습니다', { refused: true });
      rowOf(card, want);
      var win = await openWindow(ctx, want.id, { refused: true });
      // 창이 미리보기 때(또는 앞 저장이 남긴) 모양 그대로인지 — 하나라도 다르면 한 글자도 치지 않는다
      var read = facts(win), differ = [];
      if (!same(allowed(win), p.dates)) differ.push('시즌 날');
      if (!same(read.rooms.map(function (r) { return [r.id, r.label]; }), p.candidates.rooms) ||
          !same(read.plans.map(function (r) { return [r.id, r.roomId, r.label]; }), p.candidates.plans)) differ.push('객실 · 요금제');
      if (!same(read.child.filter(function (c) { return !c.editable; }).map(function (c) { return [c.field, c.text]; }), p.child)) differ.push('아동 구간');
      differ = differ.concat(K.differs(read.form, lists.form));
      if (differ.length) {
        fail('시즌 창이 미리보기 때와 다릅니다(' + clip(differ.join(', '), 120) + ') — 아무것도 치지 않았고 누르지 않았습니다',
          { refused: true, differ: differ.slice(0, 8) });
      }
      typeAll(win, lists.want, TEXT.concat(read.child.filter(function (c) { return c.editable; }).map(function (c) { return c.field; })));
      for (var i = 0; i < BOXES.length; i++) {
        var name = BOXES[i][0];
        var targets = boxes(win, name).filter(function (b) { return b.checked !== wanted(ctx.pins, b); }).map(function (b) { return b.value; });
        for (var j = 0; j < targets.length; j++) {
          var value = targets[j];
          await K.press(ctx, BOXES[i][1] + ' 체크(' + clip(value, 12) + ')', function () {
            return windowRoot() === win ? boxes(win, name).filter(function (b) { return b.value === value; })[0] || null : null;
          });
        }
      }
      typeAll(win, lists.want, ['date_selection_0', 'date_selection_1']);
      ctx.check();
      var after = K.sent(win) || [];
      var off = K.differs(after, lists.want);
      if (off.length) fail('친 뒤의 시즌 창이 보낼 값과 다릅니다(' + clip(off.join(', '), 120) + ') — 저장하지 않았습니다', { refused: true, differ: off.slice(0, 8) });
      var out = await K.saveOnce(ctx, { root: win, panel: 'stay_seasons', window: '시즌 창', what: clip(want.offer + ' · ' + want.name, 60),
        waitMs: ctx.left(), banner: true });
      if (out.saved === true) {
        var told = /새로 ([\d,]+)칸 · 덮어쓴 ([\d,]+)칸 \(룸 (\d+)개 × (\d+)일\)/.exec(out.banner || '');
        var skipped = /판매일이 없어 건너뛴 칸 ([\d,]+)개/.exec(out.banner || '');
        var n = function (t) { return Number(String(t).replace(/,/g, '')); };
        if (told) out.counts = { created: n(told[1]), updated: n(told[2]), rooms: n(told[3]), days: n(told[4]), skipped: skipped ? n(skipped[1]) : 0 };
        var warn = document.querySelector('#stay_seasons [data-stay-banner="no_supply_currency"]');
        if (warn) out.warn = clip(C(warn.textContent), 80);
        // 띠의 요금제 · 인원 · 박수 줄까지 실으면 답이 800자를 넘어 수가 잘린다 — 수는 위에서 셌고 띠는 앞부분만 장부 메모로 싣는다
        out.banner = clip(out.banner || '', 160);
      }
      return out;
    }, SPEC);
  }

  window.stayPriceSeason = {
    version: VERSION,
    readSeason: readSeason,
    applySeason: applySeason,
    take: function (id, at, size) { return K.take(id, at, size); },
    last: function () { return K.last(); },
    idle: function () { return K.idle(); },
    ALLOW: ALLOW, CONTROLS: CONTROLS, NEVER: NEVER,
    // 시험·점검용: 작업 하나의 벽을 이 파일의 표로 세운 채 fn 을 돌린다(막기만 하고 풀어 주는 것은 없다)
    guard: function (op, fn, pins) { return K.guard(SPEC, op, fn, pins); }
  };
  return K.scrub({ ok: true, version: VERSION });
})();
