/* stay_price.js — 가격 변경 도우미의 페이지 쪽 (stay-price-change). `window.stayPrice` 를 만든다.
 *
 * 러너의 도우미(`stay-setup-run/scripts/stay_helper.js`)와 부트(`stay_boot.js`)를 먼저 올리고 이 파일을 올린다.
 * 러너 파일은 고치지 않는다 — 화면을 모는 부품(cal*, runCalendarPriceStep, stayRun.waitFor)을 빌려 쓴다.
 *
 *   stayPrice.look({offer})                                                    이 탭이 어디인지 — 로그인 화면 · 호텔(번호 · 이름) ·
 *                                                                              오퍼 · 그 오퍼의 객실 × 요금제 칩. 저장하지 않는다
 *   stayPrice.readPair({offer, room, ratePlan, from, to, weekdays})            지금 값 읽기 — 저장하지 않는다. 판매일 없는 날은
 *                                                                              읽지 않고 「판매일 없음」으로 알린다
 *   stayPrice.readReserved({offer, rooms, ratePlans, from, to, weekdays,
 *                           occupancy, nights})                                예약 있는 날 읽기 — [가감 적용] 은 누르지 않는다
 *   stayPrice.applyBulk({no, offer, room, ratePlan, dates, rows})              [선택 날짜 가격 수정] 저장 한 번
 *   stayPrice.applyCell({no, offer, room, ratePlan, date, occupancy, nights,
 *                        clear, set})                                          셀 창 저장 한 번(정가·공급 원가 비우기·넣기)
 *   stayPrice.take(id, at, size)                                               읽은 조각의 한 쪽 — at=0 부터 next 를 따라 end 까지
 *   stayPrice.last()                                                           마지막 작업의 결과(45초에 잘렸을 때 읽는다)
 *   stayPrice.standDown() · standUp() · idle()                                 작업 밖의 쉬는 벽 내리기 · 다시 세우기 · 보기
 *
 * 지키는 것
 *  - 작업 하나 = 호출 하나. 34초에 답을 정하고 화면이 쉴 때(드로어가 다 닫힌 뒤) 돌려준다 — 45초 안이다. 저장은 다시 누르지
 *    않는다. 저장 단추를 누르고도 저장됐는지 모르면 saved 는 "unknown"(다시 읽어 확인)이다.
 *  - 작업이 도는 동안 페이지 맨 바깥(window, 캡처 단계)에서 모든 클릭과 폼 제출을 먼저 보고, 그 작업의
 *    허용 목록(ALLOW)에 없는 것은 막고 적는다. 러너 코드가 직접 부르는 `.click()` 도 여기에 걸린다. 막힌 것이
 *    하나라도 있으면 그 작업은 실패다. 버튼은 글자가 아니라 화면 뿌리 + `data-stay-*`·`data-calendar-*` 표식으로 찾는다.
 *    작업 밖에서도 이 파일이 올라 있는 동안은 스크립트가 만든 클릭을 막는다(사람의 클릭은 지난다) — `standDown()` 으로 내린다.
 *  - 돌려주는 값은 전부 `scrub` 을 지난다 — 주소 같은 키, 주소·쿼리 붙은 경로·토큰 같은 글자는 나가지 않는다.
 *    러너 함수의 결과는 그대로 넘기지 않는다.
 *  - 화면 조각은 `reduce` 로 줄인다 — 태그 구조 · 글자 · `data-stay-*`/`data-calendar-*` · colspan/rowspan 만. 줄인 조각은
 *    페이지에 두고 답에는 `body`(id · 글자 수 · 바이트 수 · CRC-32 · 쪽 수)만 싣는다. 답 하나·쪽 하나는 JSON 으로 800자 안이다.
 *  - localStorage 는 `stayPrice` 로 시작하는 키만 쓴다(`stayPriceLast`). 러너의 `staySteps`·`stayRunCursor` 는 쓰지 않는다.
 */
(function () {
  'use strict';

  var VERSION = '0.1.0';
  var LAST_KEY = 'stayPriceLast';
  // 브라우저 도구는 JS 호출 하나를 45초에 자른다. 작업은 hardMs 에 무조건 답을 정하고, 화면 정리(restMs)까지 마쳐도 45초 안이다.
  // budgetMs 는 이 파일의 기다림 천장, hardMs 는 러너 함수까지 포함한 작업 전체의 천장이다. config() 로는 낮추기만 한다(시험).
  var DEFAULTS = { budgetMs: 30000, hardMs: 34000, restMs: 4000 };
  var LIMITS = Object.assign({}, DEFAULTS);
  var CALL_MS = 45000;
  var WEEK = '월화수목금토일';
  var MANUAL = '조합마다 직접 입력';
  var C = function (t) { return String(t === undefined || t === null ? '' : t).normalize('NFC').replace(/\s+/g, ' ').trim(); };
  var all = function (sel, root) { return [].slice.call((root || document).querySelectorAll(sel)); };

  /* ───────────── 1. 주소·토큰 거르기 (밖으로 나가는 모든 값) ───────────── */

  // 키 이름만으로 버린다 — 값이 무엇이든 나가지 않는다
  var ADDRESS_KEY = /url|uri|href|src|hash|path|location|host|origin|referr?er|cookie|token|csrf|^hx/i;
  // 글자 안의 주소·토큰: scheme:// · //host · ?key= 가 붙은 경로 · /a/b 꼴 절대 경로 · www. · JWT · 32자 넘는 토큰
  var ADDRESS_SOURCE = [
    '[a-z][a-z0-9+.-]*:\\/\\/[^\\s"\'<>]*',
    '(?<=^|[\\s"\'(=>])\\/\\/[^\\s"\'<>]+',
    '[^\\s"\'<>]*\\?[^\\s"\'<>=&]+=[^\\s"\'<>]*',
    '(?<=^|[\\s"\'(=>])\\/[\\w.~%{}:-]+\\/[^\\s"\'<>]*',
    '\\bwww\\.[^\\s"\'<>]+',
    '\\beyJ[\\w-]+\\.[\\w-]+\\.[\\w-]*',
    '[A-Za-z0-9_-]{32,}'
  ].join('|');
  var GONE = '[주소 지움]';
  function addressLike(text) { return new RegExp(ADDRESS_SOURCE, 'i').test(String(text)); }
  function scrubText(text) {
    var out = text.replace(new RegExp(ADDRESS_SOURCE, 'gi'), GONE);
    if (out !== text && !out.split(GONE).join('').trim()) return undefined;   // 글자 전체가 주소였다
    return out;
  }
  function scrub(value, depth) {
    depth = depth || 0;
    if (value === null || typeof value === 'boolean') return value;
    if (typeof value === 'number') return isFinite(value) ? value : null;
    if (typeof value === 'string') return scrubText(value);
    if (depth > 8 || typeof value !== 'object') return undefined;            // 함수 · 너무 깊은 값
    if (Array.isArray(value)) {
      return value.map(function (item) { return scrub(item, depth + 1); }).filter(function (item) { return item !== undefined; });
    }
    if (Object.prototype.toString.call(value) !== '[object Object]') return undefined;   // 화면 마디 · window 같은 것
    var out = {};
    Object.keys(value).forEach(function (key) {
      if (ADDRESS_KEY.test(key)) return;
      var item = scrub(value[key], depth + 1);
      if (item !== undefined) out[key] = item;
    });
    return out;
  }

  /* ───────────── 2. 화면 조각 줄이기 — 파이썬 읽기(erp_read.py)가 받는 모양 ───────────── */

  var DROP_TAGS = { input: 1, select: 1, textarea: 1, button: 1, script: 1, style: 1, template: 1 };
  // 표·목록 뼈대 사이의 빈칸은 뜻이 없다(브라우저도 버린다) — 지운다. 다른 빈칸 줄은 한 칸으로 줄인다(읽기는 빈칸을 한 칸으로 본다)
  var QUIET_PARENTS = { table: 1, thead: 1, tbody: 1, tfoot: 1, tr: 1, colgroup: 1, dl: 1, ul: 1, ol: 1 };
  var VOID_TAGS = { area: 1, base: 1, br: 1, col: 1, embed: 1, hr: 1, img: 1, link: 1, meta: 1, source: 1, track: 1, wbr: 1 };
  function keepAttr(name) { return /^data-(stay|calendar)-/.test(name) || name === 'colspan' || name === 'rowspan'; }
  function esc(text, quote) {
    var out = String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return quote ? out.replace(/"/g, '&quot;') : out;
  }
  function reduce(node) {
    var out = [];
    (function walk(n) {
      if (n.nodeType === 3) {
        var text = n.nodeValue.replace(/[ \t\n\r\f]+/g, ' ');
        if (text === ' ' && n.parentNode && QUIET_PARENTS[n.parentNode.localName]) return;
        if (text[0] === ' ' && out.length && / $/.test(out[out.length - 1])) text = text.slice(1);   // 지운 칸 양옆의 빈칸이 겹치면 하나만
        if (text) out.push(esc(text));
        return;
      }
      if (n.nodeType !== 1) return;                                          // 주석 등
      var tag = n.localName;
      if (DROP_TAGS[tag]) return;
      var attrs = [].slice.call(n.attributes).filter(function (a) { return keepAttr(a.name) && !addressLike(a.value); })
        .map(function (a) { return ' ' + a.name + (a.value === '' ? '' : '="' + esc(a.value, true) + '"'); });
      out.push('<' + tag + attrs.join('') + '>');
      if (VOID_TAGS[tag]) return;
      [].forEach.call(n.childNodes, walk);
      out.push('</' + tag + '>');
    })(node);
    return out.join('');
  }

  /* ───────────── 2b. 답의 크기 — 브라우저 도구는 답을 1,000자쯤에서 자른다 ───────────── */

  // 작업의 답과 쪽 하나는 도구가 보이는 모양(JSON 으로 적은 글자)으로 800자 안이다 — 쪽 글자 안의 따옴표는 \" 로 두 자다.
  // 화면 조각은 페이지에 두고(`keep`) `take(id, at, size)` 로 글자 자리 at 부터 size 자 안의 쪽을 받는다(size 는 200~800).
  // 쪽마다 다음 자리(next) · 전체 길이(end) · 전체의 UTF-8 바이트 수와 CRC-32 를 싣는다 — 파이썬이 0 부터 end 까지 이어 붙이고
  // 둘 다 맞을 때만 쓴다(`price_browser.attach_bodies`). 잘린 쪽은 같은 자리에서 더 작은 size 로 다시 받으면 된다.
  var RESULT_CHARS = 800;
  var PIECE_MIN = 200;
  var KEEP_BODIES = 40;
  function shownLength(value) { return JSON.stringify(value).length; }
  function utf8(text) {
    var out = [];
    for (var i = 0; i < text.length; i++) {
      var c = text.codePointAt(i);
      if (c > 0xffff) i++;
      if (c < 0x80) out.push(c);
      else if (c < 0x800) out.push(0xc0 | c >> 6, 0x80 | c & 63);
      else if (c < 0x10000) out.push(0xe0 | c >> 12, 0x80 | c >> 6 & 63, 0x80 | c & 63);
      else out.push(0xf0 | c >> 18, 0x80 | c >> 12 & 63, 0x80 | c >> 6 & 63, 0x80 | c & 63);
    }
    return out;
  }
  function byteLength(text) { return utf8(text).length; }
  var CRC_TABLE = (function () {
    var table = [];
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c >>> 0;
    }
    return table;
  })();
  function crc32(text) {
    var c = 0xffffffff;
    utf8(text).forEach(function (b) { c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8); });
    return ('0000000' + ((c ^ 0xffffffff) >>> 0).toString(16)).slice(-8);
  }
  // 물은 값의 지문 — `no` 를 뺀 입력을 키 정렬 JSON 으로 적은 것의 CRC-32. 파이썬 `ask_sum` 이 같은 값을 셈한다
  function canon(value) {
    if (Array.isArray(value)) return '[' + value.map(canon).join(',') + ']';
    if (value && typeof value === 'object') {
      return '{' + Object.keys(value).filter(function (k) { return value[k] !== undefined; }).sort()
        .map(function (k) { return JSON.stringify(k) + ':' + canon(value[k]); }).join(',') + '}';
    }
    return JSON.stringify(value === undefined ? null : value);
  }
  function askedOf(input) {
    var copy = {};
    Object.keys(input || {}).forEach(function (k) { if (k !== 'no') copy[k] = input[k]; });
    return copy;
  }

  var BODIES = window.__stayPriceBodies = window.__stayPriceBodies || { order: [], items: {} };
  // at 부터 size 자 안의 쪽 하나. 되도록 `>`·`,` 바로 뒤에서 자른다(거르기가 쪽마다 같은 답을 내도록). 한 글자도 못 담으면 null
  function pieceAt(item, id, at, size) {
    var text = item.text;
    var piece = { op: 'take', ok: true, id: id, at: at, size: size, next: text.length, end: text.length, bytes: item.bytes, crc32: item.crc32, text: '' };
    var room = size - shownLength(piece), cost = 0, stop = at, good = -1;
    for (var i = at; i < text.length;) {
      var step = text.codePointAt(i) > 0xffff ? 2 : 1, ch = text.substr(i, step), c = JSON.stringify(ch).length - 2;
      if (cost + c > room) break;
      cost += c;
      i += step;
      stop = i;
      if (ch === '>' || ch === ',') good = i;
    }
    if (stop < text.length && good > at) stop = good;
    if (stop === at) return null;
    piece.next = stop;
    piece.text = text.slice(at, stop);
    return piece;
  }
  function keep(body) {
    var text = JSON.stringify(scrub(body));
    var id = 'b' + Date.now().toString(36) + (BODIES.order.length + 1);
    var item = BODIES.items[id] = { text: text, bytes: byteLength(text), crc32: crc32(text) };
    BODIES.order.push(id);
    while (BODIES.order.length > KEEP_BODIES) delete BODIES.items[BODIES.order.shift()];
    var count = 0;
    for (var at = 0; at < text.length; count++) at = pieceAt(item, id, at, RESULT_CHARS).next;
    return { id: id, chars: text.length, bytes: item.bytes, crc32: item.crc32, pieces: count };
  }
  function take(id, at, size) {
    at = at === undefined ? 0 : at;
    size = size === undefined ? RESULT_CHARS : size;
    var whole = function (n) { return typeof n === 'number' && n === Math.floor(n); };
    var item = BODIES.items[id];
    if (!item) return fit({ op: 'take', ok: false, id: String(id), error: '그 조각이 페이지에 없습니다 — 페이지가 바뀌었으면 다시 읽습니다' });
    if (!whole(at) || at < 0 || at >= item.text.length) return fit({ op: 'take', ok: false, id: id, error: '자리(at)는 0 부터 ' + (item.text.length - 1) + ' 까지입니다' });
    if (!whole(size) || size < PIECE_MIN || size > RESULT_CHARS) return fit({ op: 'take', ok: false, id: id, error: '크기(size)는 ' + PIECE_MIN + ' 부터 ' + RESULT_CHARS + ' 까지입니다' });
    var piece = pieceAt(item, id, at, size);
    if (!piece) return fit({ op: 'take', ok: false, id: id, at: at, error: '이 크기로는 한 글자도 담지 못합니다 — 더 큰 size 로 받습니다' });
    var out = scrub(piece);
    if (out.text !== piece.text) return fit({ op: 'take', ok: false, id: id, at: at, error: '이 자리에서 자르면 글자가 바뀝니다 — 다른 size 로 받습니다' });
    return out;
  }
  // 거르기를 지나 800자 안으로. 넘으면 꼭 필요한 칸만 남기고 줄였다고 적는다
  var ESSENTIAL = ['op', 'ok', 'no', 'ask', 'started', 'wait', 'saved', 'pressed', 'refused', 'rest', 'body', 'ms', 'error'];
  function fit(result) {
    var out = scrub(result);
    if (shownLength(out) <= RESULT_CHARS) return out;
    var small = {};
    ESSENTIAL.forEach(function (k) { if (out[k] !== undefined) small[k] = out[k]; });
    small.cut = true;
    if (typeof small.error === 'string') small.error = clip(small.error, 150);
    return small;
  }
  function clip(text, n) { text = String(text || ''); return text.length > n ? text.slice(0, n) + '…' : text; }

  /* ───────────── 3. 클릭 벽 — 작업마다 허용 목록 하나 ───────────── */

  // 어떤 작업에서도 누르지 않는 것 — 허용 목록보다 먼저 본다(허용 줄이 잘못 넓어도 이것은 막힌다)
  var NEVER = [
    { sel: '[data-calendar-bulk-action="close"],[data-calendar-bulk-action="reopen"]', why: '판매 마감·마감 해제 창' },
    { sel: '[data-stay-screen="calendar-adjust"] [data-stay-action="save"]', why: '[가감 적용]' },
    { sel: '[data-calendar-adjust-action="undo"],[data-stay-action="undo"]', why: '[되돌리기]' },
    { sel: '[data-calendar-adjust-action="log"]', why: '[적용 기록 내려받기]' },
    { sel: '[data-stay-action="close_month"]', why: '[N월 닫기]' },
    { sel: '[data-stay-action="delete"],[hx-delete]', why: '삭제' },
    { sel: '[data-stay-action="archive"]', why: '보관' },
    { sel: '[data-stay-action="activate"],[data-stay-action="end"],[data-stay-card="gate"]', why: '판매 시작·종료' },
    { sel: 'ul.tab-container a:not([data-stay-tab="calendar"])', why: '다른 탭' }
  ];
  // 허용 목록의 낱말 — 화면 뿌리 + 표식. `when` 은 그 작업이 정해 둔 값(pins)과 맞아야 통과하는 조건이다
  var CONTROLS = {
    tab: { sel: 'ul.tab-container a[data-stay-tab="calendar"]' },
    offer: { sel: '#stay_calendar [data-stay-entity="offer"][data-stay-action="goto"]', when: 'offer' },
    view: { sel: '#stay_calendar .stay-view-btn[data-stay-action="goto"][hx-get*="view=coord"]' },
    chip: { sel: '#stay_calendar [data-stay-entity="rate_plan"][data-stay-action="goto"]', when: 'chip' },
    month: { sel: '#stay_calendar .erp_cont_head_right > [data-stay-action="goto"]:not(.stay-view-btn):not(.stay-promo-btn)' },
    bulkOpen: { sel: '#stay_calendar [data-calendar-bulk-action="price"]' },
    bulkDay: { sel: '[data-stay-screen="calendar-bulk"][data-calendar-selection] input[type="checkbox"][name="weekdays"]' },
    bulkNext: { sel: '[data-stay-screen="calendar-bulk"][data-calendar-selection] [data-stay-action="next"]' },
    bulkSave: { sel: '[data-stay-screen="calendar-bulk"]:not([data-calendar-selection]) [data-stay-action="save"]', when: 'bulkTarget', max: 1 },
    adjustOpen: { sel: '#stay_calendar [data-calendar-adjust-action="open"]' },
    adjustPick: {
      sel: ['rooms', 'plans', 'occupancy', 'weekdays', 'adjust_original', 'include_manual', 'include_extra'].map(function (name) {
        return '[data-calendar-adjust="select"] input[type="checkbox"][name="' + name + '"]';
      }).concat(['[data-calendar-adjust="select"] input[type="radio"][name="los"]']).join(',')
    },
    adjustNext: { sel: '[data-calendar-adjust="select"] [data-stay-action="next"]' },
    cellOpen: { sel: '#stay_calendar td[data-stay-date] > [data-stay-action="open_cell"]', when: 'date' },
    cellSave: { sel: '#stay_cell_edit [data-stay-card="main"] tr[data-stay-row] [data-stay-action="save_cell"]', when: 'row', max: 1 },
    cellClose: { sel: '#stay_cell_edit .stay-modal__head [data-stay-action="close"]' }
  };
  // 작업별 허용 목록 — 여기 없는 클릭은 모두 막는다(ERP 가 나중에 더한 버튼도). 읽는 작업에는 저장 단추가 없다
  var ALLOW = {
    look: ['tab', 'view', 'offer'],
    readPair: ['tab', 'offer', 'view', 'chip', 'month', 'bulkOpen', 'bulkDay', 'bulkNext'],
    readReserved: ['tab', 'view', 'adjustOpen', 'adjustPick', 'adjustNext'],
    applyBulk: ['tab', 'offer', 'view', 'chip', 'bulkOpen', 'bulkDay', 'bulkNext', 'bulkSave'],
    applyCell: ['tab', 'offer', 'view', 'chip', 'month', 'cellOpen', 'cellSave', 'cellClose']
  };
  function hiddenValue(root, name) { var el = root && root.querySelector('input[type="hidden"][name="' + name + '"]'); return el ? el.value : null; }
  function sameRanges(text, ranges) { return (text || '').split('\n').map(C).filter(Boolean).join('\n') === ranges.join('\n'); }
  var WHEN = {
    offer: function (el, pins) { return !!pins.offer && C(el.getAttribute('data-stay-name')) === pins.offer; },
    chip: function (el, pins) { return !!pins.chip && C(el.getAttribute('data-stay-name')) === pins.chip; },
    date: function (el, pins) { var td = el.closest('td[data-stay-date]'); return !!pins.date && !!td && td.getAttribute('data-stay-date') === pins.date; },
    row: function (el, pins) { var tr = el.closest('tr[data-stay-row]'); return !!pins.row && !!tr && tr.getAttribute('data-stay-row') === pins.row; },
    // 저장 직전에 드로어가 그 객실·요금제·날짜를 연 것인지 본다 — 아니면 누르지 않는다
    bulkTarget: function (el, pins) {
      var root = el.closest('[data-stay-screen="calendar-bulk"]');
      return !!(root && pins.ratePlanId && pins.ranges) && hiddenValue(root, 'operation') === 'price' &&
        hiddenValue(root, 'rate_plan') === pins.ratePlanId && sameRanges(hiddenValue(root, 'date_selection_0'), pins.ranges);
    }
  };
  var CONTROL = 'a,button,input,select,textarea,label,summary,[role="button"],[data-stay-action],[hx-get],[hx-post],[hx-put],[hx-patch],[hx-delete],[onclick]';
  function describe(el) {
    if (!el || el.nodeType !== 1) return '(알 수 없음)';
    var marks = [].slice.call(el.attributes).filter(function (a) { return /^data-(stay|calendar)-/.test(a.name) && !addressLike(a.value); })
      .slice(0, 2).map(function (a) { return a.name + (a.value ? '=' + a.value.slice(0, 30) : ''); });
    var text = C(el.textContent).slice(0, 20);
    return el.localName + (marks.length ? '[' + marks.join(' ') + ']' : '') + (text ? ' "' + text + '"' : '');
  }

  function Wall(op) {
    var names = ALLOW[op], counts = {}, pins = {}, log = { clicks: [], blocked: [] };
    var judge = function (target, counting) {
      var el = target && target.nodeType === 1 ? target : target && target.parentElement;
      var ctl = el ? (el.closest(CONTROL) || el) : null;
      if (!ctl) return { why: '대상을 알 수 없는 클릭' };
      for (var i = 0; i < NEVER.length; i++) if (ctl.closest(NEVER[i].sel)) return { ctl: ctl, why: NEVER[i].why + ' — 이 도우미는 누르지 않습니다' };
      for (var j = 0; j < names.length; j++) {
        var entry = CONTROLS[names[j]];
        if (!ctl.matches(entry.sel)) continue;
        if (entry.when && !WHEN[entry.when](ctl, pins)) return { ctl: ctl, why: '이 작업이 고른 대상이 아닙니다(' + names[j] + ')' };
        if (counting && entry.max && (counts[names[j]] || 0) >= entry.max) return { ctl: ctl, why: '같은 저장을 다시 누르지 않습니다' };
        return { allow: names[j] };
      }
      return { ctl: ctl, why: '허용 목록에 없습니다' };
    };
    var block = function (e, verdict) {
      e.preventDefault();
      e.stopImmediatePropagation();
      log.blocked.push({ control: describe(verdict.ctl), why: verdict.why });
    };
    var frozen = false;
    var wall = {
      pins: pins, log: log,
      handle: function (e) {
        // 시간이 다 된 작업: 사람의 클릭과 셀 창 [닫기] 만 지나고, 뒤에 남은 러너 코드의 클릭은 모두 막는다
        if (frozen) {
          var at = e.target && e.target.nodeType === 1 ? e.target : e.target && e.target.parentElement;
          var shut = at && at.closest(CONTROL);
          if (e.isTrusted || (e.type === 'click' && shut && shut.matches(CONTROLS.cellClose.sel))) return;
          return block(e, { ctl: shut || at, why: '시간이 다 된 작업의 클릭입니다' });
        }
        if (e.type === 'submit') {
          var sent = e.submitter ? judge(e.submitter, false) : { ctl: e.target, why: '누른 단추 없이 보낸 폼입니다' };
          if (!sent.allow) block(e, sent);
          return;
        }
        var verdict = judge(e.target, true);
        if (!verdict.allow) return block(e, verdict);
        counts[verdict.allow] = (counts[verdict.allow] || 0) + 1;
        log.clicks.push(verdict.allow);
      },
      pressed: function (name) { return (counts[name] || 0) > 0; },
      freeze: function () { frozen = true; },
      frozen: function () { return frozen; },
      stop: function () { if (GUARD.wall === wall) GUARD.wall = null; }
    };
    GUARD.wall = wall;
    return wall;
  }

  /* ── 벽은 하나다: 작업이 돌면 그 작업의 허용 목록이, 작업 밖에서는 스크립트가 만든 클릭(isTrusted 아님)을 막는 쉬는 벽이 선다.
     사람이 직접 누른 클릭은 쉬는 벽을 지난다. 러너 함수를 손으로 불러도 아무것도 누르지 못한다. `standDown()` 으로 내린다. */
  var GUARD = window.__stayPriceGuard || { wall: null };
  window.__stayPriceGuard = GUARD;
  if (GUARD.listen) { window.removeEventListener('click', GUARD.listen, true); window.removeEventListener('submit', GUARD.listen, true); }
  GUARD.idle = true;                 // 이 파일을 올릴 때마다 다시 선다
  GUARD.idleBlocked = [];
  GUARD.listen = function (e) {
    if (GUARD.wall) return GUARD.wall.handle(e);
    if (!GUARD.idle || e.isTrusted) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    var target = e.type === 'submit' ? (e.submitter || e.target) : e.target;
    var el = target && target.nodeType === 1 ? target : target && target.parentElement;
    GUARD.idleBlocked.push(describe(el ? (el.closest(CONTROL) || el) : null));
    if (GUARD.idleBlocked.length > 20) GUARD.idleBlocked.shift();
  };
  window.addEventListener('click', GUARD.listen, true);
  window.addEventListener('submit', GUARD.listen, true);
  function idleState() { return fit({ idle: GUARD.idle, blocked: GUARD.idleBlocked.slice(-5), count: GUARD.idleBlocked.length }); }

  /* ───────────── 4. 작업 틀 — 벽 세우기 · 시간 · 결과 남기기 ───────────── */

  var NEEDS = ['calDayRanges', 'calSetPeriod', 'calSet', 'calCheck', 'calSelectOffer', 'calEnsureCoord', 'calSelectChip',
    'calRedraw', 'calErrors', 'runCalendarPriceStep'];
  function Stop(message, extra) { this.message = message; this.extra = extra || {}; }
  function fail(message, extra) { throw new Stop(message, extra); }

  function remember(result) {
    try { localStorage.setItem(LAST_KEY, JSON.stringify(result)); } catch (e) { /* 못 적어도 결과는 돌려준다 */ }
    return result;
  }
  function last() {
    try { return JSON.parse(localStorage.getItem(LAST_KEY) || 'null'); } catch (e) { return null; }
  }

  var SAVES = { applyBulk: 'bulkSave', applyCell: 'cellSave' };
  function at(ms) { var wait = Math.max(1, ms - Date.now()); return window.stayRun.sleep ? window.stayRun.sleep(wait) : new Promise(function (r) { setTimeout(r, wait); }); }

  // 시작하지 않은 작업 — 아무것도 누르기 전에 지나가는 까닭(앞 작업이 아직 끝나는 중, 앞 화면이 아직 정리 중)으로 멈췄다.
  // `started: false` 와 기다릴 초(`wait`)를 싣는다. 실패가 아니다 — 명령은 장부에 적지 않고, 그만큼 기다린 뒤 같은 값으로 다시 부른다
  var BUSY_WAIT = 10, REST_WAIT = 5;
  function notStarted(op, input, message, wait) {
    var no = input && typeof input.no === 'number' ? input.no : undefined;
    return fit(Object.assign({ op: op }, no !== undefined ? { no: no } : {}, {
      ok: false, started: false, wait: wait, ask: crc32(canon(askedOf(input))), clicks: {},
      error: message + ' — 아무것도 누르지 않았습니다. ' + wait + '초 뒤 같은 값으로 다시 부릅니다'
    }));
  }

  async function run(op, input, body) {
    var missing = NEEDS.filter(function (name) { return typeof window[name] !== 'function'; });
    if (!window.stayRun || typeof window.stayRun.waitFor !== 'function') missing.unshift('stayRun');
    if (missing.length) return remember(fit({ ok: false, op: op, error: '러너의 도우미(stay_helper.js)와 부트(stay_boot.js)를 먼저 올려 주세요 — 없는 것: ' + missing.join(', ') }));
    var busy = window.__stayPriceBusy;
    if (busy) return notStarted(op, input, '앞 작업(' + busy.op + ')이 아직 끝나지 않았습니다', BUSY_WAIT);
    // 작업 넷은 요청이 짚은 호텔에서만 돈다 — 무엇이든 누르기 전에 탭이 그 번호의 호텔인지 본다(이름은 같은 호텔이 있어 보지 않는다)
    var here = op === 'look' ? pageHotel() : boundHotel(op, input);
    if (here.refusal) return remember(here.refusal);
    var token = window.__stayPriceBusy = { op: op };
    var started = Date.now(), limits = Object.assign({}, LIMITS);
    var hardAt = started + limits.hardMs, endAt = hardAt + limits.restMs;
    var no = input && typeof input.no === 'number' ? input.no : undefined;
    remember({ running: { op: op, no: no, at: new Date(started).toISOString() } });
    var wall = Wall(op), out;
    var ctx = {
      wall: wall, pins: wall.pins,
      left: function () { return Math.max(0, Math.min(started + limits.budgetMs, hardAt) - Date.now()); },
      wait: function (cond, ms) { return window.stayRun.waitFor(cond, Math.max(1, Math.min(ms, ctx.left()))); },
      check: function () {
        if (wall.frozen()) fail('시간이 다 돼 멈춘 작업입니다');
        if (wall.log.blocked.length) fail('허용 목록에 없는 클릭이 있어 멈췄습니다');
        if (!ctx.left()) fail('시간(' + Math.round(ctx.limit() / 1000) + '초)이 다 돼 멈췄습니다');
      },
      limit: function () { return Math.min(limits.budgetMs, limits.hardMs); }
    };
    var work = (async function () {
      // 앞 화면이 쉬고 있을 때만 시작한다 — 닫히는 중인 드로어의 조각을 새 화면으로 읽지 않게
      await closeDrawer(started + limits.restMs);
      if (!await window.stayRun.waitFor(atRest, Math.max(1, Math.min(limits.restMs, ctx.left())))) {
        if (cellWindow()) fail('셀 창이 열려 있습니다 — 사람이 닫은 뒤 다시 부릅니다');
        fail('앞 화면(드로어·요청)이 아직 정리되지 않았습니다 — 아무것도 누르지 않았습니다. ' + REST_WAIT + '초 뒤 같은 값으로 다시 부릅니다',
          { started: false, wait: REST_WAIT });
      }
      var result = await body(input || {}, ctx);
      if (result.keep) { result.body = keep(Object.assign({ op: op, asked: askedOf(input), hotel: here }, result.keep)); delete result.keep; }
      return result;
    })().then(function (value) { return { value: value }; }, function (error) { return { error: error }; });
    var first = await Promise.race([work, at(hardAt).then(function () { return { late: true }; })]);
    var late = !!first.late;
    if (late) {
      // 뒤에 남은 코드(러너의 기다림)는 아무것도 더 누르지 못한다. 그 코드가 끝나면 벽을 걷고 다음 작업을 받는다
      wall.freeze();
      var pressed = SAVES[op] && wall.pressed(SAVES[op]);
      out = { ok: false, error: '시간(' + Math.round(limits.hardMs / 1000) + '초) 안에 끝나지 않아 멈췄습니다 — 그 뒤로는 아무것도 누르지 않습니다' };
      if (SAVES[op]) {
        out.pressed = !!pressed;
        out.saved = pressed ? 'unknown' : false;
        if (pressed) out.error += ' · 저장 단추는 눌렸습니다. 저장됐는지 알 수 없으니 다시 읽어 확인합니다';
      }
      work.then(function () { wall.stop(); if (window.__stayPriceBusy === token) window.__stayPriceBusy = null; });
    } else if (first.error) {
      var e = first.error;
      out = e instanceof Stop ? Object.assign({ ok: false, error: e.message }, e.extra) : { ok: false, error: '페이지 쪽 코드가 멈췄습니다: ' + C(e && e.message) };
    } else {
      out = first.value;
    }
    // 정리는 restMs 안에서(늦어도 endAt 까지) — 쉬지 않는 화면 때문에 답을 더 붙잡지 않는다
    var restUntil = Math.min(endAt, Date.now() + limits.restMs);
    try { await closeAll(op, restUntil); } catch (e) { /* 닫기 실패는 아래 결과에 남는다 */ }
    // 화면이 쉴 때 돌려준다 — 드로어가 다 닫히고(내용까지 비고) 셀 창이 없고 도는 요청이 없을 때
    out.rest = !!(await window.stayRun.waitFor(atRest, Math.max(1, restUntil - Date.now())));
    if (!out.rest) out.warn = '화면이 아직 정리되지 않았습니다(드로어·셀 창·요청) — 다음 작업은 정리된 뒤에 시작합니다';
    if (!late) { wall.stop(); window.__stayPriceBusy = null; }
    var blocked = wall.log.blocked;
    if (blocked.length) {
      out.ok = false;
      out.error = (out.error && out.error.indexOf('허용 목록') < 0 ? out.error + ' · ' : '') + '허용 목록에 없는 클릭을 막았습니다: ' +
        blocked.slice(0, 2).map(function (b) { return b.control + ' (' + b.why + ')'; }).join(' / ') + (blocked.length > 2 ? ' 외 ' + (blocked.length - 2) + '건' : '');
    }
    if (drawerOpen()) { out.ok = false; out.error = (out.error ? out.error + ' · ' : '') + '드로어를 닫지 못했습니다'; }
    out = Object.assign({ op: op }, no !== undefined ? { no: no } : {}, { ok: out.ok }, out);
    out.ask = crc32(canon(askedOf(input)));
    out.clicks = {};
    wall.log.clicks.forEach(function (name) { out.clicks[name] = (out.clicks[name] || 0) + 1; });
    out.blocked = blocked.slice(0, 2);
    if (blocked.length > 2) out.blockedMore = blocked.length - 2;
    if (out.error) out.error = clip(out.error, 200);
    out.ms = Date.now() - started;
    return remember(fit(out));
  }

  /* ───────────── 4b. 이 탭은 어느 호텔인가 · 로그인 화면인가 ───────────── */

  // 호텔은 페이지가 스스로 적어 둔 번호로 안다. 두 곳을 본다 —
  //  · fit 기본정보 폼의 숨은 칸 `input#master_id`(fit/master_form.html 의 form 블록, Stay 편집 화면이 그대로 물려받는다)
  //  · [에이전트에 복사] 모달의 붙여 넣기 문구 `#stay_agent_resume [data-agent-text]`(_agent_resume_modal.html — 자동화가 잡는
  //    이름으로 약속된 자리). 문구는 "ERP 호텔 <번호> (<이름>) 편집 화면" 이다.
  // 둘 다 있으면 번호가 같아야 한다. 이름은 그 문구에서, 없으면 기본정보 상품명 칸의 저장된 값(`#id_title` 의 value 속성)에서 —
  // 이름은 보여 주기만 하고, 같은 호텔인지는 번호로만 정한다(이름이 같은 호텔이 있을 수 있다).
  var RESUME_TEXT = /ERP 호텔 (\S+) \((.*)\) 편집 화면/;
  function loginShown() {
    if (window.stayRun && typeof window.stayRun.state === 'function') {
      try { return !!window.stayRun.state().loginPage; } catch (e) { /* 아래 길로 */ }
    }
    var p = document.querySelector('input[type=password],input[name=password]');
    return !!p && !p.disabled;
  }
  function pageHotel() {
    var idEl = document.getElementById('master_id');
    var id = idEl ? C(idEl.value) : '';
    var area = document.querySelector('#stay_agent_resume [data-agent-text="verify"]') || document.querySelector('#stay_agent_resume [data-agent-text="resume"]');
    var said = area ? RESUME_TEXT.exec(C(typeof area.value === 'string' ? area.value : area.textContent)) : null;
    var title = document.getElementById('id_title');
    var name = said ? C(said[2]) : (title ? C(title.getAttribute('value') || '') : '');
    if (!id) return { error: loginShown() ? '탭이 로그인 화면입니다 — 담당자가 직접 로그인한 뒤 다시 부릅니다' : '이 탭에서 호텔 번호를 찾지 못했습니다 — 호텔의 Stay 편집 화면이 아닙니다' };
    if (said && C(said[1]) !== id) return { error: '이 탭의 호텔 번호가 화면 두 곳에서 다릅니다(' + id + ' · ' + C(said[1]) + ') — 새로 고친 뒤 다시 부릅니다' };
    return { id: id, name: name };
  }
  // 작업의 `hotel`({id, name} — look() 의 hotel 그대로)이 이 탭의 호텔인지. 맞으면 이 탭의 호텔, 아니면 {refusal: 답}
  function boundHotel(op, input) {
    var no = input && typeof input.no === 'number' ? input.no : undefined;
    var refuse = function (message, extra) {
      return { refusal: fit(Object.assign({ op: op }, no !== undefined ? { no: no } : {}, { ok: false, ask: crc32(canon(askedOf(input))), clicks: {}, error: message }, extra || {})) };
    };
    var want = input && input.hotel;
    if (!want || typeof want !== 'object' || !C(want.id)) return refuse('`hotel` 이 없습니다 — stayPrice.look() 의 hotel({id, name})을 그대로 넣습니다. 아무것도 누르지 않았습니다');
    var here = pageHotel();
    if (here.error) return refuse(here.error + ' — 아무것도 누르지 않았습니다');
    if (C(want.id) !== here.id) {
      return refuse('이 탭은 호텔 ' + here.id + ' (' + here.name + ') 입니다 — 요청은 호텔 ' + C(want.id) + ' (' + C(want.name) + ') 입니다. 아무것도 누르지 않았습니다', { hotel: here });
    }
    return here;
  }

  /* ───────────── 5. 화면 부품 — 가격 캘린더 · 칩 · 드로어 ───────────── */

  function drawerOpen() { return !!document.querySelector('.stay-drawer.is-open'); }
  function cellWindow() { return document.getElementById('stay_cell_edit'); }
  // 쉬는 화면 — 드로어가 닫혔고 내용도 비었고(ERP 는 닫고 0.35초 뒤에 비운다), 셀 창이 없고, 도는 htmx 요청이 없다
  function atRest() {
    var body = document.getElementById('stay_drawer_body');
    var hx = window.stayRun && window.stayRun.hx;
    return !drawerOpen() && !(body && body.firstElementChild) && !cellWindow() && !(hx && hx.pending > 0);
  }
  // 드로어는 ERP 가 듣는 `stay-drawer-close` 로 닫는다(러너 `stayRun.close()` 와 같은 길) — 클릭이 아니다
  async function closeDrawer(untilMs) {
    if (!drawerOpen()) return;
    window.dispatchEvent(new CustomEvent('stay-drawer-close'));
    await window.stayRun.waitFor(function () { return !drawerOpen(); }, Math.max(1, Math.min(3000, (untilMs || Infinity) - Date.now())));
  }
  async function closeAll(op, untilMs) {
    var modal = cellWindow();
    if (modal && op === 'applyCell') {
      var x = modal.querySelector('.stay-modal__head [data-stay-action="close"]');
      if (x) { x.click(); await window.stayRun.waitFor(function () { return !cellWindow(); }, Math.max(1, Math.min(3000, untilMs - Date.now()))); }
    }
    await closeDrawer(untilMs);
  }

  function calendarReady() {
    var link = document.querySelector('ul.tab-container a[data-stay-tab="calendar"]');
    var active = !!link && (link.classList.contains('active') || !!link.closest('li.active'));
    return active && !!document.querySelector('#stay_calendar[data-cal-month]');
  }
  async function toCalendar(ctx) {
    if (!calendarReady()) {
      var link = document.querySelector('ul.tab-container a[data-stay-tab="calendar"]');
      if (!link) fail('[가격 캘린더] 탭을 찾지 못했습니다');
      link.click();
      await ctx.wait(calendarReady, 8000);
    }
    ctx.check();
    if (!calendarReady()) fail('가격 캘린더가 열리지 않았습니다');
  }
  // 오퍼 칩은 오퍼가 둘 이상일 때만 선다. 이름이 **꼭 같은** 칩 하나만 고른다(러너의 느슨한 맞춤으로 넘어가지 않게)
  async function pickOffer(ctx, offer) {
    var chips = all('#stay_calendar [data-stay-entity="offer"][data-stay-action="goto"]');
    if (!chips.length) return;
    var hits = chips.filter(function (c) { return C(c.getAttribute('data-stay-name')) === offer; });
    if (hits.length !== 1) fail('캘린더의 오퍼 칩에서 `' + offer + '` 을 ' + (hits.length ? '하나로 못 골랐습니다' : '찾지 못했습니다') + ' (보이는 오퍼: ' + chips.map(function (c) { return C(c.getAttribute('data-stay-name')); }).join(' / ') + ')');
    ctx.pins.offer = offer;
    var picked = await window.calSelectOffer(offer);
    ctx.check();
    if (picked.error) fail(picked.error);
  }
  async function coordView(ctx) {
    var ok = await window.calEnsureCoord();
    ctx.check();
    if (!ok) fail('[룸별 입력] 화면으로 바꾸지 못했습니다');
  }
  // 객실·요금제는 캘린더가 보여 주는 칩 이름(`객실 · 요금제`)과 꼭 같은 하나만 — 지시서의 다른 이름은 보지 않는다
  async function pickChip(ctx, room, ratePlan) {
    var name = C(room) + ' · ' + C(ratePlan);
    var chips = all('#stay_calendar [data-stay-entity="rate_plan"][data-stay-action="goto"]');
    var hits = chips.filter(function (c) { return C(c.getAttribute('data-stay-name')) === name; });
    if (hits.length !== 1) fail('캘린더에 `' + name + '` 칩이 ' + (hits.length ? hits.length + '개라 하나로 못 골랐습니다' : '없습니다') + ' (보이는 칩: ' + chips.map(function (c) { return C(c.getAttribute('data-stay-name')); }).join(' / ') + ')');
    ctx.pins.chip = name;
    ctx.pins.ratePlanId = hits[0].getAttribute('data-stay-entity-id') || '';
    var picked = await window.calSelectChip(hits[0], name);
    ctx.check();
    if (picked.error) fail(picked.error);
  }
  async function toPair(ctx, offer, room, ratePlan) {
    await toCalendar(ctx);
    await pickOffer(ctx, offer);
    await coordView(ctx);
    await pickChip(ctx, room, ratePlan);
  }

  function expandDays(labels) {
    var days = [];
    labels.forEach(function (label) {
      var m = /^(\d{4}-\d{2}-\d{2})(?: ~ (\d{4}-\d{2}-\d{2}))?/.exec(C(label));
      if (!m) { days.push('?' + label); return; }
      for (var d = new Date(m[1] + 'T00:00:00Z'), end = new Date((m[2] || m[1]) + 'T00:00:00Z'); d <= end; d = new Date(d.getTime() + 86400000)) {
        days.push(d.toISOString().slice(0, 10));
      }
    });
    return days;
  }
  function facts(root) {
    var out = {}, dl = root.querySelector('[data-stay-summary] dl');
    if (!dl) return out;
    var dts = all('dt', dl), dds = all('dd', dl);
    dts.forEach(function (dt, i) { if (dds[i]) out[C(dt.textContent)] = C(dds[i].textContent); });
    return out;
  }
  function period(from, to, weekdays) {
    if (!Array.isArray(weekdays) || !weekdays.length || weekdays.some(function (w) { return WEEK.indexOf(w) < 0 || w.length !== 1; })) {
      fail('`weekdays` 는 월·화·수·목·금·토·일 글자 목록이어야 합니다');
    }
    var p = window.calDayRanges(from, to, weekdays);
    if (p.error) fail(p.error);
    return { ranges: p.ranges, days: expandDays(p.ranges) };
  }
  function text(value, name) {
    if (typeof value !== 'string' || !C(value)) fail('`' + name + '` 이 비었습니다');
    return C(value);
  }
  function list(value, name) {
    if (!Array.isArray(value) || !value.length) fail('`' + name + '` 은 하나 이상의 목록이어야 합니다');
    return value.map(function (item) { return text(item, name); });
  }

  // [선택 날짜 가격 수정] ① 기간 → [다음] → ② 확인. ② 가 그 객실·요금제·기간인지 본 뒤 뿌리를 돌려준다(저장하지 않는다)
  async function openBulkReview(ctx, want, span) {
    var root = function () { return document.querySelector('[data-stay-screen="calendar-bulk"]'); };
    var opener = document.querySelector('#stay_calendar [data-calendar-bulk-action="price"]');
    if (!opener) fail('[선택 날짜 가격 수정] 버튼이 없습니다');
    opener.click();
    await ctx.wait(function () { var r = root(); return !!(r && r.hasAttribute('data-calendar-selection') && r.querySelector('[name="period_from"]')); }, 8000);
    ctx.check();
    var r1 = root();
    if (!r1 || !r1.hasAttribute('data-calendar-selection')) fail('[선택 날짜 가격 수정] 드로어 ① 이 열리지 않았습니다');
    var set = window.calSetPeriod(r1, want.from, want.to, want.weekdays, span.ranges);
    if (set.error) fail(set.error);
    var next = r1.querySelector('[data-stay-action="next"]');
    await ctx.wait(function () { return !!next && !next.disabled; }, 3000);
    if (!next || next.disabled) fail('[다음] 이 눌리지 않습니다 — 화면이 기간을 받지 않았습니다');
    next.click();
    await ctx.wait(function () {
      var r = root();
      return !!r && ((!r.hasAttribute('data-calendar-selection') && !!r.querySelector('[data-stay-rows="prices"]')) || window.calErrors(r).length > 0);
    }, 8000);
    ctx.check();
    var r2 = root();
    if (r2 && window.calErrors(r2).length) fail('[선택 날짜 가격 수정] 이 기간을 거절했습니다 — ' + window.calErrors(r2).join(' / '));
    if (!r2 || r2.hasAttribute('data-calendar-selection') || !r2.querySelector('[data-stay-rows="prices"]')) fail('[선택 날짜 가격 수정] ② 가 뜨지 않았습니다');
    // 화면이 물은 것과 다른 것을 보여 주면 읽지 않는다
    var seen = facts(r2);
    if (hiddenValue(r2, 'operation') !== 'price') fail('드로어가 가격 수정 창이 아닙니다');
    if (ctx.pins.ratePlanId && hiddenValue(r2, 'rate_plan') !== ctx.pins.ratePlanId) fail('드로어가 고른 칩과 다른 객실·요금제를 열었습니다(화면: ' + (seen['객실'] || '?') + ' · ' + (seen['요금제'] || '?') + ')');
    if (seen['오퍼'] !== want.offer) fail('드로어의 오퍼가 `' + (seen['오퍼'] || '?') + '` 입니다 — `' + want.offer + '` 을 물었습니다');
    if (seen['요금제'] !== want.ratePlan) fail('드로어의 요금제가 `' + (seen['요금제'] || '?') + '` 입니다 — `' + want.ratePlan + '` 을 물었습니다');
    if (!sameRanges(hiddenValue(r2, 'date_selection_0'), span.ranges)) fail('드로어가 다른 날짜를 골랐습니다(화면: ' + C(hiddenValue(r2, 'date_selection_0')) + ')');
    var status = all('table', r2).filter(function (t) {
      var heads = all('thead th', t).map(function (th) { return C(th.textContent); });
      return heads[0] === '숙박일' && heads[1] === '현재 가격·마감 상태';
    })[0];
    var shown = status ? expandDays(all('tbody tr', status).map(function (tr) { var td = tr.querySelector('td'); return td ? td.textContent : ''; })) : [];
    if (shown.join(',') !== span.days.join(',')) fail('드로어의 날짜(' + shown.length + '일)가 물은 날짜(' + span.days.length + '일)와 다릅니다');
    return r2;
  }

  /* ───────────── 6. 보기 하나와 작업 넷 ───────────── */

  // 캘린더의 오퍼 — 오퍼가 둘 이상이면 칩(`data-stay-name`), 하나면 칩 대신 고정 글자(`.stay-offer-label .stay-card__title`).
  // 둘 다 오퍼 이름(offer.name)이라 드로어의 「오퍼」 와 같은 글자다
  function offersShown() {
    var chips = all('#stay_calendar [data-stay-entity="offer"][data-stay-action="goto"]');
    if (chips.length) {
      var on = chips.filter(function (c) { return /\bstay-btn--primary\b/.test(c.className); })[0];
      return { names: chips.map(function (c) { return C(c.getAttribute('data-stay-name')); }), picked: on ? C(on.getAttribute('data-stay-name')) : '' };
    }
    var label = document.querySelector('#stay_calendar .stay-offer-label .stay-card__title');
    var name = label ? C(label.textContent) : '';
    return { names: name ? [name] : [], picked: name };
  }
  // 칩 이름은 「객실 · 요금제」 다(ERP CalendarCoord.label). 객실 이름에 ` · ` 가 든 호텔이 있어 마지막 ` · ` 에서 가른다 —
  // 잘못 갈라도 readPair 가 드로어의 요금제와 견주어 읽지 않고 거절한다
  function pairOf(label) {
    var at = label.lastIndexOf(' · ');
    return at < 0 ? { room: label, rate_plan: '' } : { room: label.slice(0, at), rate_plan: label.slice(at + 3) };
  }

  // 이 탭이 어디인지 — 로그인 화면인지, 어느 호텔인지(페이지가 말하는 번호·이름), 캘린더의 오퍼, 그리고 한 오퍼의 객실 × 요금제
  // 칩 이름. 저장하지 않는다. 누르는 것은 [가격 캘린더] 탭 · [룸별 입력] · (offer 를 주면) 그 오퍼 칩뿐이다 — 캘린더는 고른 오퍼의
  // 칩만 그린다. 목록이 길면 `body` 로 두고 take 로 받는다
  function look(input) {
    input = input && typeof input === 'object' ? input : {};
    var ask = crc32(canon(askedOf(input)));
    if (loginShown()) return remember(fit({ op: 'look', ok: true, login: true, ask: ask, note: '탭이 로그인 화면입니다 — 담당자가 직접 로그인해야 합니다', clicks: {} }));
    var hotel = pageHotel();
    if (hotel.error) return remember(fit({ op: 'look', ok: false, login: false, ask: ask, error: hotel.error, clicks: {} }));
    return run('look', input, async function (p, ctx) {
      var offer = p.offer === undefined || p.offer === null ? null : text(p.offer, 'offer');
      await toCalendar(ctx);
      await coordView(ctx);
      if (offer) await pickOffer(ctx, offer);
      var shown = offersShown();
      if (offer && shown.picked !== offer) fail('캘린더에 오퍼 `' + offer + '` 이 없습니다 (보이는 오퍼: ' + shown.names.join(' / ') + ')');
      var pairs = all('#stay_calendar [data-stay-entity="rate_plan"][data-stay-action="goto"]').map(function (c) { return pairOf(C(c.getAttribute('data-stay-name'))); });
      var whole = { ok: true, login: false, hotel: hotel, offer: shown.picked, offers: shown.names, pairs: pairs };
      // 답의 나머지 칸(ask · clicks · rest · ms …)이 200자 안팎이다 — 목록까지 800자에 들면 그대로, 아니면 조각으로
      if (shownLength(whole) <= RESULT_CHARS - 260) return whole;
      return { ok: true, login: false, hotel: hotel, offer: shown.picked, count: { offers: shown.names.length, pairs: pairs.length },
        keep: { hotel: hotel, offer: shown.picked, offers: shown.names, pairs: pairs } };
    });
  }

  function runsOf(days) {
    var runs = [];
    days.forEach(function (day) {
      var prev = runs[runs.length - 1];
      if (prev && nextDay(prev.to) === day) prev.to = day; else runs.push({ from: day, to: day });
    });
    return runs.map(function (r) { return r.from === r.to ? r.from : r.from + ' ~ ' + r.to; });
  }
  // 고른 날 가운데 판매일이 열린 날 — 그 객실·요금제 달력의 칸으로 안다(열린 날은 칸이 [셀 창] 단추, 안 열린 날은 「판매일 없음」 글자)
  async function openDays(ctx, days) {
    var open = [];
    var months = days.map(function (d) { return d.slice(0, 7); }).filter(function (m, i, list) { return list.indexOf(m) === i; });
    for (var i = 0; i < months.length; i++) {
      await toMonth(ctx, months[i] + '-01');
      days.filter(function (d) { return d.slice(0, 7) === months[i]; }).forEach(function (day) {
        var td = document.querySelector('#stay_calendar td[data-stay-date="' + day + '"]');
        if (!td) fail('달력에서 ' + day + ' 칸을 찾지 못했습니다');
        if ([].slice.call(td.children).some(function (el) { return el.matches('[data-stay-action="open_cell"]'); })) open.push(day);
      });
    }
    return open;
  }

  function readPair(input) {
    return run('readPair', input, async function (p, ctx) {
      var want = { offer: text(p.offer, 'offer'), room: text(p.room, 'room'), ratePlan: text(p.ratePlan, 'ratePlan'), from: p.from, to: p.to, weekdays: p.weekdays };
      var span = period(want.from, want.to, want.weekdays);
      await toPair(ctx, want.offer, want.room, want.ratePlan);
      var open = await openDays(ctx, span.days);
      var noSale = span.days.filter(function (d) { return open.indexOf(d) < 0; });
      var counts = { asked: span.days.length, open: open.length, noSale: noSale.length };
      if (!open.length) return { ok: true, what: clip(ctx.pins.chip + ' · 고른 날이 모두 판매일 없음', 120), days: counts, keep: { fragment: null, noSale: noSale } };
      // 열린 날만 고른다 — 날은 숨은 date_selection_0 의 구간 줄이 정한다(기간·요일 칸은 그 바깥 테두리)
      var openSpan = { ranges: runsOf(open), days: open };
      var review = await openBulkReview(ctx, { offer: want.offer, ratePlan: want.ratePlan, from: open[0], to: open[open.length - 1], weekdays: want.weekdays }, openSpan);
      var fragment = reduce(review);
      await closeDrawer(Date.now() + 3000);
      if (drawerOpen()) fail('읽은 뒤 드로어를 닫지 못했습니다');
      return { ok: true, what: clip(ctx.pins.chip + ' · ' + openSpan.ranges[0] + (openSpan.ranges.length > 1 ? ' 외 ' + (openSpan.ranges.length - 1) + '구간' : ''), 120),
        days: counts, keep: { fragment: fragment, noSale: noSale } };
    });
  }

  var LOS = { all: 'all', one: 'one' };
  function readReserved(input) {
    return run('readReserved', input, async function (p, ctx) {
      var want = {
        offer: text(p.offer, 'offer'), rooms: list(p.rooms, 'rooms'), ratePlans: list(p.ratePlans, 'ratePlans'),
        from: p.from, to: p.to, weekdays: p.weekdays, occupancy: p.occupancy === '*' ? '*' : null, nights: p.nights
      };
      if (want.occupancy === null) {
        if (!Array.isArray(p.occupancy) || !p.occupancy.length || p.occupancy.some(function (k) { return typeof k !== 'string'; })) fail('`occupancy` 는 인원 조합 키 목록이거나 "*"(화면의 전부)입니다');
        want.occupancy = p.occupancy.slice();
      }
      if (!LOS[want.nights]) fail('`nights` 는 "all"(전 층) 또는 "one"(1박 층만)입니다');
      // 적용하지 않으므로 값은 무엇이든 해가 없다. 판매가를 내리는 정액이면 「정가보다 비싸짐」 줄이 생기지 않는다
      var adjust = p.adjust === undefined ? '-1' : String(p.adjust);
      if (!/^-\d+(\.\d{1,2})?$/.test(adjust) || Number(adjust) === 0) fail('`adjust` 는 내리는 정액(예: -1)만 받습니다');
      var span = period(want.from, want.to, want.weekdays);

      await toCalendar(ctx);
      await coordView(ctx);
      var root = function () { return document.querySelector('[data-stay-screen="calendar-adjust"]'); };
      var stepOf = function () { var r = root(); return r ? r.getAttribute('data-calendar-adjust') : ''; };
      var opener = document.querySelector('#stay_calendar [data-calendar-adjust-action="open"]');
      if (!opener) fail('이 화면에는 [선택 날짜 가격 가감] 창이 없습니다');
      opener.click();
      await ctx.wait(function () { return stepOf() === 'select' && !!root().querySelector('select[name="offer"]'); }, 8000);
      ctx.check();
      if (stepOf() !== 'select') fail('[선택 날짜 가격 가감] ① 이 열리지 않았습니다');

      var offerSelect = root().querySelector('select[name="offer"]');
      var offerHits = [].slice.call(offerSelect.options).filter(function (o) { return C(o.textContent) === want.offer; });
      if (offerHits.length !== 1) fail('`오퍼` 목록에서 `' + want.offer + '` 을 ' + (offerHits.length ? '하나로 못 골랐습니다' : '찾지 못했습니다'));
      var offerValue = offerHits[0].value;
      if (offerSelect.value !== offerValue) {
        var redrawn = await window.calRedraw(offerSelect, offerValue, root, function (r) {
          var s = r.querySelector('select[name="offer"]');
          return r.getAttribute('data-calendar-adjust') === 'select' && !!s && s !== offerSelect && s.value === offerValue;
        });
        ctx.check();
        if (!redrawn) fail('`오퍼` 를 `' + want.offer + '` 로 바꾸지 못했습니다');
      }

      var r1 = root();
      var labelOf = function (box) { var label = box.closest('label'); return C(label ? label.textContent : ''); };
      var pickBoxes = function (name, wants, keyOf, what) {
        var boxes = all('input[type="checkbox"][name="' + name + '"]', r1);
        if (!boxes.length) fail('`' + what + '` 에 고를 항목이 없습니다');
        var on = wants === '*' ? boxes.slice() : wants.map(function (w) {
          var hits = boxes.filter(function (b) { return keyOf(b) === w; });
          if (hits.length !== 1) fail('`' + what + '` 에서 `' + (w || '인원 무관 단일가') + '` 을 ' + (hits.length ? '하나로 못 골랐습니다' : '찾지 못했습니다') + ' (보이는 것: ' + boxes.map(labelOf).join(' / ') + ')');
          return hits[0];
        });
        boxes.forEach(function (b) { window.calCheck(b, on.indexOf(b) >= 0); });
        return on.map(function (b) { return b.value; }).sort();
      };
      var picked = {
        rooms: pickBoxes('rooms', want.rooms, labelOf, '객실'),
        plans: pickBoxes('plans', want.ratePlans, labelOf, '요금제'),
        occupancy: pickBoxes('occupancy', want.occupancy, function (b) { return b.value; }, '인원 조합')
      };
      var los = r1.querySelector('input[type="radio"][name="los"][value="' + want.nights + '"]');
      if (!los) fail('`박수 층` 라디오가 없습니다');
      if (!los.checked) los.click();
      var set = window.calSetPeriod(r1, want.from, want.to, want.weekdays, span.ranges);
      if (set.error) fail(set.error);
      var adjustInput = r1.querySelector('input[name="adjust"]');
      if (!adjustInput) fail('`가감` 칸이 없습니다');
      window.calSet(adjustInput, adjust);
      var flags = { adjust_original: false, include_manual: true, include_extra: false };
      Object.keys(flags).forEach(function (name) {
        var box = r1.querySelector('input[type="checkbox"][name="' + name + '"]');
        if (!box) fail('체크 칸 `' + name + '` 이 없습니다');
        window.calCheck(box, flags[name]);
      });
      ctx.check();
      var next = r1.querySelector('[data-stay-action="next"]');
      await ctx.wait(function () { return !!next && !next.disabled; }, 3000);
      if (!next || next.disabled) fail('[다음] 이 눌리지 않습니다 — 화면이 기간을 받지 않았습니다');
      next.click();
      await ctx.wait(function () { var r = root(); return !!r && (stepOf() === 'confirm' || (r !== r1 && window.calErrors(r).length > 0)); }, 8000);
      ctx.check();
      var r2 = root();
      if (stepOf() !== 'confirm') fail('[선택 날짜 가격 가감] ① 을 화면이 받지 않았습니다' + (r2 && window.calErrors(r2).length ? ' — ' + window.calErrors(r2).join(' / ') : ''));
      // 확인 단계가 고른 그대로인지 — 숨은 칸(서버가 받은 값)으로 본다
      var hiddenAll = function (name) { return all('input[type="hidden"][name="' + name + '"]', r2).map(function (i) { return i.value; }).sort(); };
      var same = hiddenAll('rooms').join('\n') === picked.rooms.join('\n') && hiddenAll('plans').join('\n') === picked.plans.join('\n') &&
        hiddenAll('occupancy').join('\n') === picked.occupancy.join('\n') && hiddenValue(r2, 'offer') === offerValue &&
        hiddenValue(r2, 'los') === want.nights && hiddenValue(r2, 'adjust') === adjust && sameRanges(hiddenValue(r2, 'date_selection_0'), span.ranges);
      if (!same) fail('가감 확인 단계가 고른 것과 다른 범위를 보여 줍니다');
      if (facts(r2)['오퍼'] !== want.offer) fail('가감 확인 단계의 오퍼가 `' + (facts(r2)['오퍼'] || '?') + '` 입니다');
      var fragment = reduce(r2);
      await closeDrawer(Date.now() + 3000);
      if (drawerOpen()) fail('읽은 뒤 드로어를 닫지 못했습니다');
      return { ok: true, what: clip(want.rooms.length + '객실 · ' + want.ratePlans.length + '요금제 · ' + want.from + ' ~ ' + want.to, 120),
        days: span.days.length, keep: { fragment: fragment } };
    });
  }

  var AMOUNT = /^\d+(\.\d+)?$/;
  var BULK_COLS = [{ key: 'sell', col: 'price', label: '판매가' }, { key: 'list', col: 'original_price', label: '정가' }, { key: 'supply', col: 'net_amount', label: '공급 원가' }];
  function nextDay(day) { return new Date(new Date(day + 'T00:00:00Z').getTime() + 86400000).toISOString().slice(0, 10); }

  // 러너의 `runCalendarPriceStep` 이 받는 단계 객체 — 연동 방식은 「조합마다 직접 입력」, 줄마다 넣을 값만 적는다
  function bulkStepFor(p) {
    var F = function (label, kind, value, extra) {
      var f = { label: label, kind: kind, raw_value: value };
      if (kind === 'multi') f.values = value; else f.value = value;
      return Object.assign(f, extra || {});
    };
    var fields = [F('오퍼', 'select', p.offer), F('객실', 'select', p.room), F('요금제', 'select', p.ratePlan),
      F('시작일', 'typed', p.dates[0]), F('종료일', 'typed', p.dates[p.dates.length - 1]), F('요일', 'multi', WEEK.split('')),
      F('연동 방식', 'select', MANUAL)];
    p.rows.forEach(function (row) {
      BULK_COLS.forEach(function (c) {
        if (row[c.key] === null || row[c.key] === undefined) return;
        fields.push(F((row.occupancy || '인원 무관') + ' · ' + row.nights + '박 이상 · ' + c.label, 'typed', String(row[c.key]),
          { field: 'prices', occupancy_key: row.occupancy, los_nights: row.nights, field_col: c.col }));
      });
    });
    return { no: p.no, kind: '선택 날짜 가격 수정', title: '가격 변경 도우미 저장 ' + p.no, fields: fields };
  }

  function applyBulk(input) {
    return run('applyBulk', input, async function (p, ctx) {
      var want = { offer: text(p.offer, 'offer'), room: text(p.room, 'room'), ratePlan: text(p.ratePlan, 'ratePlan'), dates: p.dates, rows: p.rows };
      if (!Array.isArray(want.dates) || !want.dates.length || want.dates.some(function (d, i) { return !/^\d{4}-\d{2}-\d{2}$/.test(d) || (i && nextDay(want.dates[i - 1]) !== d); })) {
        fail('`dates` 는 이어진 날짜 목록이어야 합니다');
      }
      if (!Array.isArray(want.rows) || !want.rows.length) fail('`rows` 가 비었습니다');
      want.rows.forEach(function (row) {
        if (typeof row.occupancy !== 'string' || !(row.nights >= 1 && row.nights === Math.floor(row.nights))) fail('줄마다 `occupancy`(글자)와 `nights`(1 이상 정수)가 있어야 합니다');
        var values = BULK_COLS.filter(function (c) { return row[c.key] !== null && row[c.key] !== undefined; });
        if (!values.length || values.some(function (c) { return !AMOUNT.test(String(row[c.key])); })) fail('줄 ' + (row.occupancy || '인원 무관') + ' · ' + row.nights + '박 에 넣을 금액이 없거나 숫자가 아닙니다');
      });
      var span = period(want.dates[0], want.dates[want.dates.length - 1], WEEK.split(''));
      if (span.days.join(',') !== want.dates.join(',')) fail('`dates` 를 기간으로 바꾸지 못했습니다');
      await toPair(ctx, want.offer, want.room, want.ratePlan);
      ctx.pins.ranges = span.ranges;   // 저장 단추는 드로어가 이 날짜·이 칩일 때만 눌린다(WHEN.bulkTarget)
      var r = await window.runCalendarPriceStep(bulkStepFor(Object.assign({ no: p.no }, want)), {});
      var pressed = ctx.wall.pressed('bulkSave');
      var confirmed = pressed && !!r && r.submitted === true && !r.error && !r.manualAction;
      // 눌렀는데 드로어가 오류를 보이며 남았으면 서버가 거절한 것(저장 안 됨). 그 밖에 확인 못 한 것은 「알 수 없음」이다
      var refusedByServer = pressed && !!r && r.submit === 'stayed' && (r.errors || []).length > 0;
      var saved = confirmed ? true : (pressed && !refusedByServer ? 'unknown' : false);
      var out = { ok: saved === true, what: clip(want.room + ' · ' + want.ratePlan + ' · ' + span.ranges.join(', '), 120), saved: saved, pressed: pressed };
      if (saved === true) { out.note = '저장했습니다'; return out; }
      var reason = r && r.bad && r.bad.length ? '드로어 표에 없는 줄이나 칸이 있어 저장하지 않았습니다 — ' + r.bad.join(' / ')
        : r && r.stoppedBy === 'mismatch' ? '넣은 값을 다시 읽으니 달라 저장하지 않았습니다 — ' + (r.mismatch || []).join(' / ') : null;
      if (reason && !pressed) out.refused = true;
      out.error = reason || (r && r.error) || '저장하지 못했습니다';
      if (saved === 'unknown') out.error += ' — 저장 단추는 눌렸고 저장됐는지 알 수 없습니다. 다시 읽어 확인합니다(다시 누르지 않았습니다)';
      if (r && r.errors && r.errors.length) out.errors = r.errors.slice(0, 2).map(function (e) { return clip(e, 60); });
      return out;
    });
  }

  var CELL_FIELDS = { list: 'original_price', supply: 'net_amount' };
  async function toMonth(ctx, day) {
    var want = day.slice(0, 7);
    for (var hop = 0; hop < 24; hop++) {
      var cal = document.querySelector('#stay_calendar[data-cal-month]');
      var month = cal && cal.getAttribute('data-cal-month');
      if (month === want) return;
      var goes = all(CONTROLS.month.sel).map(function (b) { var m = /[?&]month=(\d{4}-\d{2})/.exec(b.getAttribute('hx-get') || ''); return { b: b, month: m && m[1] }; })
        .filter(function (x) { return x.month && (want > month ? x.month > month : x.month < month); });
      if (goes.length !== 1) fail('달력을 ' + want + ' 로 넘길 단추를 찾지 못했습니다');
      goes[0].b.click();
      await ctx.wait(function () { var c = document.querySelector('#stay_calendar[data-cal-month]'); return !!c && c.getAttribute('data-cal-month') !== month; }, 6000);
      ctx.check();
    }
    fail('달력을 ' + want + ' 로 넘기지 못했습니다');
  }

  function applyCell(input) {
    return run('applyCell', input, async function (p, ctx) {
      var want = { offer: text(p.offer, 'offer'), room: text(p.room, 'room'), ratePlan: text(p.ratePlan, 'ratePlan'), date: p.date, occupancy: p.occupancy, nights: p.nights,
        clear: Array.isArray(p.clear) ? p.clear.slice() : [], set: p.set && typeof p.set === 'object' ? Object.assign({}, p.set) : {} };
      if (!/^\d{4}-\d{2}-\d{2}$/.test(want.date || '')) fail('`date` 는 YYYY-MM-DD 입니다');
      if (typeof want.occupancy !== 'string' || !(want.nights >= 1 && want.nights === Math.floor(want.nights))) fail('`occupancy`(글자)와 `nights`(1 이상 정수)가 있어야 합니다');
      var targets = {};
      want.clear.forEach(function (name) { if (!CELL_FIELDS[name]) fail('셀 창에서는 정가(list)·공급 원가(supply)만 비웁니다: ' + name); targets[name] = ''; });
      Object.keys(want.set).forEach(function (name) {
        if (!CELL_FIELDS[name] || targets[name] !== undefined || !AMOUNT.test(String(want.set[name]))) fail('`set` 은 정가(list)·공급 원가(supply)의 금액이고 비우기와 겹치지 않아야 합니다');
        targets[name] = String(want.set[name]);
      });
      if (!Object.keys(targets).length) fail('비우거나 넣을 칸이 없습니다');
      var cellName = want.room + ' · ' + want.ratePlan + ' · ' + want.date + ' · ' + (want.occupancy || '인원 무관') + ' · ' + want.nights + '박 이상';

      await toPair(ctx, want.offer, want.room, want.ratePlan);
      await toMonth(ctx, want.date);
      var td = document.querySelector('#stay_calendar td[data-stay-date="' + want.date + '"]');
      var opener = td && [].slice.call(td.children).filter(function (el) { return el.matches('[data-stay-action="open_cell"]'); })[0];
      if (!opener) fail(want.date + ' 칸을 누를 수 없습니다(판매일이 없거나 이 달에 없는 날) — 저장하지 않았습니다');
      ctx.pins.date = want.date;
      opener.click();
      await ctx.wait(function () { var m = cellWindow(); return !!m && m.getAttribute('data-stay-screen') === 'price-cell'; }, 8000);
      ctx.check();
      var modal = cellWindow();
      if (!modal) fail('셀 창이 열리지 않았습니다');
      // 아무것도 만지기 전에 연 창이 그 날짜·요금제인지 본다 — 러너의 셀 단계는 달 머리와 일 숫자만 본다
      var title = C((modal.querySelector('.stay-modal__title') || {}).textContent);
      var shownDay = (/(\d{4}-\d{2}-\d{2})$/.exec(title) || [])[1] || '?';
      var tail = ' · ' + want.ratePlan + ' · ' + want.date;
      var addDate = modal.querySelector('input[type="hidden"][name="date"]'), addPlan = modal.querySelector('input[type="hidden"][name="rate_plan"]');
      if (shownDay !== want.date || (addDate && addDate.value !== want.date)) fail('연 셀 창의 날짜(' + shownDay + ')가 저장할 날짜(' + want.date + ')와 달라 아무것도 바꾸지 않았습니다', { refused: true });
      if (title.slice(-tail.length) !== tail || (addPlan && ctx.pins.ratePlanId && addPlan.value !== ctx.pins.ratePlanId)) fail('연 셀 창이 다른 요금제입니다(' + title + ') — 아무것도 바꾸지 않았습니다', { refused: true });
      var rows = all('[data-stay-card="main"] tr[data-stay-row]', modal).filter(function (tr) {
        var key = tr.querySelector('input[name="occupancy_key"]'), los = tr.querySelector('input[name="los_nights"]');
        return !!key && !!los && key.value === want.occupancy && C(los.value) === String(want.nights);
      });
      if (rows.length !== 1) fail('셀 창에 `' + (want.occupancy || '인원 무관') + ' · ' + want.nights + '박 이상` 줄이 ' + (rows.length ? rows.length + '개라' : '없어') + ' 저장하지 않았습니다', { refused: true });
      var row = rows[0], rowId = row.getAttribute('data-stay-row');
      Object.keys(targets).forEach(function (name) {
        var el = row.querySelector('input[name="' + CELL_FIELDS[name] + '"]');
        if (!el) fail('셀 창 줄에 ' + name + ' 칸이 없습니다');
        window.calSet(el, targets[name]);
        if (el.value !== targets[name]) fail('셀 창 칸에 값이 들어가지 않았습니다(' + name + ')');
      });
      var save = row.querySelector('[data-stay-action="save_cell"]');
      if (!save) fail('셀 창 줄에 [저장] 이 없습니다');
      ctx.pins.row = rowId;
      save.click();
      var pressed = ctx.wall.pressed('cellSave');
      await ctx.wait(function () { var m = cellWindow(); return !m || m !== modal || window.calErrors(modal).length > 0; }, 10000);
      var after = cellWindow();
      var row2 = after && after !== modal ? after.querySelector('tr[data-stay-row="' + rowId + '"]') : null;
      var errors = after ? window.calErrors(after) : [];
      var landed = !!row2 && Object.keys(targets).every(function (name) { var el = row2.querySelector('input[name="' + CELL_FIELDS[name] + '"]'); return !!el && el.value === targets[name]; });
      var saved = pressed && landed && !errors.length ? true : (pressed && !errors.length ? 'unknown' : false);
      var out = { ok: saved === true, what: clip(cellName, 120), saved: saved, pressed: pressed };
      if (saved === true) out.note = '저장했습니다';
      else if (errors.length) out.error = '셀 창이 저장을 거절했습니다 — ' + errors.join(' / ');
      else out.error = '셀 창 저장을 확인하지 못했습니다' + (pressed ? ' — [저장] 은 눌렸고 저장됐는지 알 수 없습니다. 다시 읽어 확인합니다(다시 누르지 않았습니다)' : '');
      var x = after && after.querySelector('.stay-modal__head [data-stay-action="close"]');
      if (x) { x.click(); await ctx.wait(function () { return !cellWindow(); }, 5000); }
      if (cellWindow()) { out.ok = false; out.error = (out.error ? out.error + ' · ' : '') + '셀 창을 닫지 못했습니다'; }
      return out;
    });
  }

  window.stayPrice = {
    version: VERSION,
    look: look,
    readPair: readPair,
    readReserved: readReserved,
    applyBulk: applyBulk,
    applyCell: applyCell,
    last: last,
    take: take,
    // 쉬는 벽 — 작업 밖에서 스크립트가 만든 클릭을 막는다. 러너를 그대로 쓰려면 standDown() 으로 내린다
    idle: idleState,
    standDown: function () { GUARD.idle = false; return idleState(); },
    standUp: function () { GUARD.idle = true; return idleState(); },
    // 시간 천장 — 부르면 지금 값, 값을 주면 낮추기만 한다(시험용). 기본값은 hardMs + restMs 가 45초 안이다
    config: function (patch) {
      Object.keys(patch || {}).forEach(function (k) {
        if (DEFAULTS[k] !== undefined && typeof patch[k] === 'number' && patch[k] > 0 && patch[k] <= DEFAULTS[k]) LIMITS[k] = patch[k];
      });
      return fit(Object.assign({ callMs: CALL_MS }, LIMITS));
    },
    scrub: function (value) { return scrub(value); },
    reduce: reduce,
    ALLOW: ALLOW, CONTROLS: CONTROLS, NEVER: NEVER,
    // 시험·점검용: 작업 하나의 벽을 세운 채 fn 을 돌린다(막기만 하고 풀어 주는 것은 없다)
    guard: async function (op, fn, pins) {
      if (!ALLOW[op]) throw new Error('모르는 작업: ' + op);
      var wall = Wall(op);
      Object.assign(wall.pins, pins || {});
      try { await fn(); } finally { wall.stop(); }
      return { clicks: wall.log.clicks.slice(), blocked: wall.log.blocked.slice() };
    }
  };
  return { ok: true, version: VERSION };
})();
