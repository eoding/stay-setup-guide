/*!
 * stay_helper.js — ERP Stay 화면 도우미 (stay-setup-run v0.1.0)
 *
 * 브라우저의 자바스크립트 실행 도구로 이 파일 전체를 페이지에서 실행하면 `window.stayRun` 이 생긴다.
 * 두 번 실행해도 안전하다(멱등). 페이지가 새로 뜨거나 주소가 바뀌면 다시 실행한다.
 *
 * 원칙
 *  - 서버로 요청을 직접 보내지 않는다(fetch·XMLHttpRequest 안 씀). 화면의 입력 요소와 버튼만 다룬다.
 *  - 내부 주소·요청 경로를 갖지 않는다. 화면에 보이는 글자와 앞단 컨테이너 클래스만 안다.
 *  - 위험한 버튼(삭제·보관·닫기·공용으로·N월 닫기·확인창이 뜨는 버튼)은 거부한다. [판매 시작] 은 어떤 경우에도 누르지 않는다.
 *  - 돌려주는 값은 전부 JSON 으로 바꿀 수 있는 평범한 객체다.
 *
 * 기다리는 함수(open·fill·submit·addRow·tab·close)는 async 다. `await` 를 못 쓰는 도구라면
 * 호출한 뒤 잠깐 뒤에 `stayRun.last` 를 읽으면 마지막 결과가 들어 있다.
 */
(function () {
  'use strict';

  var VERSION = '0.1.0';
  var WAIT_MS = 10000; // 저장·열기 최대 대기(밀리초)
  var TICK = 100;

  /* ─────────────────────────── 공통 유틸 ─────────────────────────── */

  // 탭이 뒤로 가면 크롬이 페이지 타이머를 1초·1분 단위로 늦춘다 — 워커 타이머는 늦추지 않으므로 대기는 워커로 잰다
  var timerWorker = null, timerSeq = 0, timerCbs = {};
  function workerTimer() {
    if (timerWorker !== null) return timerWorker;
    try {
      var blob = new Blob(['onmessage=function(e){setTimeout(function(){postMessage(e.data.id)},e.data.ms)}'], { type: 'text/javascript' });
      timerWorker = new Worker(URL.createObjectURL(blob));
      timerWorker.onmessage = function (e) { var cb = timerCbs[e.data]; delete timerCbs[e.data]; if (cb) cb(); };
      timerWorker.onerror = function () { timerWorker = false; };
    } catch (e) { timerWorker = false; }
    return timerWorker;
  }
  var sleep = function (ms) {
    var w = workerTimer();
    if (!w) return new Promise(function (r) { setTimeout(r, ms); });
    return new Promise(function (r) {
      var id = ++timerSeq; timerCbs[id] = r;
      try { w.postMessage({ id: id, ms: ms }); } catch (e) { delete timerCbs[id]; setTimeout(r, ms); }
      setTimeout(function () { if (timerCbs[id]) { delete timerCbs[id]; r(); } }, ms + 1500); // 워커가 막히면 페이지 타이머로라도 깨운다
    });
  };

  function nfc(s) { return (s === null || s === undefined ? '' : String(s)).normalize('NFC'); }

  // 라벨·옵션 비교용: 공백·별표·가운뎃점·구두점을 지우고 소문자로
  var RE_PUNCT = /[\s*·・‧∙…,，.。/\\|:;!?"'`~^＊()（）[\]{}<>「」『』〈〉《》〔〕\-–—_=+]+/g;
  function norm(s) { return nfc(s).replace(/ /g, ' ').replace(RE_PUNCT, '').toLowerCase(); }
  function noParen(s) { return nfc(s).replace(/[（(][^）)]*[）)]/g, ' '); }
  function clean(s) { return nfc(s).replace(/ /g, ' ').replace(/\s+/g, ' ').replace(/\s*\*\s*$/, '').trim(); }
  function trunc(s, n) { s = s || ''; return s.length > n ? s.slice(0, n) + '…' : s; }
  function textOf(el) { return el ? clean(el.textContent) : ''; }

  // 글자 일치 등급: 4 완전, 3 괄호 뺀 완전, 2 앞부분, 1 포함, 0 아님
  function tier(cand, want) {
    var a = norm(cand), b = norm(want);
    if (!a || !b) return 0;
    if (a === b) return 4;
    var a2 = norm(noParen(cand)), b2 = norm(noParen(want));
    if (a2 && b2 && a2 === b2) return 3;
    if (a.indexOf(b) === 0 || b.indexOf(a) === 0) return 2;
    if (a.indexOf(b) >= 0 || b.indexOf(a) >= 0) return 1;
    return 0;
  }

  // 후보 목록에서 가장 잘 맞는 하나 고르기
  // 라벨의 머리 부분: `이 호텔 전용 — 설명…` → `이 호텔 전용`. 긴 설명이 붙은 선택지를 머리만으로 견줄 때 쓴다.
  function headOf(t) { return clean(nfc(t).split(/\s+[—–-]\s+|:/)[0]); }
  // `오퍼 · 룸` 처럼 가운뎃점으로 나뉜 이름은 순서를 바꿔 적어도 같은 것으로 본다 (화면은 `룸 · 오퍼` 순일 수 있다)
  function partsKey(t) { var p = nfc(t).split(/\s+[·・‧∙]\s+/).map(norm).filter(Boolean); return p.length >= 2 ? p.sort().join('|') : ''; }
  function tierLoose(cand, want) {
    var t = tier(cand, want); if (t >= 2) return t;
    var hc = headOf(cand), hw = headOf(want);
    if (hc && hw && hc !== clean(cand)) { t = tier(hc, hw); if (t >= 2) return t; }
    var pk = partsKey(want);
    if (pk && pk === partsKey(cand)) return 3;
    var tp = tailPart(want);
    return (tp && tier(cand, tp) >= 3) ? 2 : 0;
  }
  // `오퍼 · 룸` 의 뒤쪽 조각 — 화면 항목이 룸 이름만 보여 줄 때 그 조각으로 맞춘다
  function tailPart(t) { var p = nfc(t).split(/\s+[·・‧∙]\s+/).map(clean).filter(Boolean); return p.length >= 2 ? p[p.length - 1] : ''; }
  // 전체 글자로 못 찾으면 머리 부분끼리, 그다음 가운뎃점 조각 묶음끼리 견주는 2·3차 선택
  function pickLoose(list, getText, want, minTier) {
    var r = pick(list, getText, want, minTier);
    if (r.status !== 'not-found') return r;
    r = pick(list, function (it) { return headOf(getText(it)); }, headOf(want), 3);
    if (r.status !== 'not-found') return r;
    var pk = partsKey(want);
    if (!pk) return r;
    r = pick(list, function (it) { return partsKey(getText(it)); }, pk, 4);
    if (r.status !== 'not-found') return r;
    return pick(list, getText, tailPart(want), 3);
  }
  function pick(list, getText, want, minTier) {
    var min = minTier || 1, best = [], bt = 0;
    for (var i = 0; i < list.length; i++) {
      var t = tier(getText(list[i]), want);
      if (t < min) continue;
      if (t > bt) { bt = t; best = [list[i]]; } else if (t === bt) best.push(list[i]);
    }
    if (!best.length) return { status: 'not-found', el: null, tier: 0 };
    if (best.length > 1) return { status: 'ambiguous', el: best[0], tier: bt, count: best.length };
    return { status: 'ok', el: best[0], tier: bt };
  }

  // 레이아웃이 없는 환경(시험용 DOM 등)에서는 자리 대신 style 로만 판정한다
  function noLayout() {
    var r = document.body.getBoundingClientRect();
    return !r.width && !r.height;
  }
  function shown(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el.hidden) return false;
    var r = el.getBoundingClientRect();
    if (el.offsetParent || r.width || r.height) return true;
    return noLayout() ? usable(el) : false;
  }

  // 입력 요소가 지금 폼에서 쓸 수 있는가 (파일·select2·Materialize 처럼 숨겨진 것도 포함)
  function usable(el) {
    if (!el || el.disabled) return false;
    if (el.type === 'hidden') return false;
    if (el.type === 'file') return true;
    if (el.classList.contains('select2-hidden-accessible')) return true;
    var n = el;
    if (n.tagName === 'SELECT' && n.closest('.select-wrapper')) n = n.closest('.select-wrapper');
    var hops = 0;
    while (n && n.nodeType === 1 && n !== document.documentElement && hops++ < 40) {
      if (n.hidden) return false;
      var st = getComputedStyle(n);
      if (st.display === 'none' || st.visibility === 'hidden') return false;
      n = n.parentElement;
    }
    return true;
  }

  var CTRL_SEL = 'input,select,textarea';
  function isCtrl(el) {
    if (!el || !/^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName)) return false;
    if (el.tagName === 'INPUT' && /^(hidden|submit|button|reset|image)$/.test(el.type)) return false;
    if (el.classList.contains('select-dropdown')) return false;       // Materialize 표시용 칸
    if (el.classList.contains('select2-search__field')) return false; // select2 검색 칸
    return true;
  }

  function docOrder(a, b) {
    var p = a.compareDocumentPosition(b);
    return (p & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1;
  }

  function describe(el) {
    if (!el) return '(없음)';
    if (el === document.body) return 'document';
    return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
      (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  }

  async function waitFor(fn, ms) {
    var t0 = Date.now();
    while (Date.now() - t0 < (ms || WAIT_MS)) {
      try { if (fn()) return true; } catch (e) { /* 교체 중 */ }
      await sleep(TICK);
    }
    try { return !!fn(); } catch (e) { return false; }
  }

  /* ─────────────────────────── htmx 감시 ─────────────────────────── */
  // 저장 뒤 응답이 끝났는지 알려면 htmx 이벤트를 세어야 한다. 재주입해도 한 번만 붙인다.
  function htmxWatch() {
    if (window.__stayRunHtmx) return window.__stayRunHtmx;
    var st = { pending: 0, requests: 0, settles: 0, swaps: 0, error: null, unloading: false };
    var on = function (n, f) { document.body.addEventListener(n, f, true); };
    on('htmx:beforeRequest', function () { st.pending++; st.requests++; });
    on('htmx:afterRequest', function () { st.pending = Math.max(0, st.pending - 1); });
    on('htmx:afterSwap', function () { st.swaps++; });
    on('htmx:afterSettle', function () { st.settles++; });
    on('htmx:responseError', function (e) {
      var code = e && e.detail && e.detail.xhr ? e.detail.xhr.status : '';
      st.error = '서버가 오류로 답했습니다' + (code ? ' (' + code + ')' : '');
    });
    on('htmx:sendError', function () { st.error = '요청을 보내지 못했습니다(네트워크)'; });
    on('htmx:timeout', function () { st.error = '요청이 시간 안에 끝나지 않았습니다'; });
    window.addEventListener('beforeunload', function () { st.unloading = true; });
    window.addEventListener('pagehide', function () { st.unloading = true; });
    window.__stayRunHtmx = st;
    return st;
  }
  var hx = htmxWatch();

  /* ─────────────────────────── 범위(스코프) ─────────────────────────── */

  function drawerRoot() {
    var d = document.querySelector('.stay-drawer.is-open');
    if (!d) return null;
    return d.querySelector('#stay_drawer_body') || d;
  }
  function modalRoot() {
    var list = [].slice.call(document.querySelectorAll('.modal.open')).filter(shown);
    return list.length ? list[list.length - 1] : null;
  }
  function currentTabLink() {
    return document.querySelector('ul.tab-container li a.active') ||
      document.querySelector('ul.tab-container li.active > a');
  }
  function paneRoot() {
    var link = currentTabLink();
    var id = link ? (link.getAttribute('href') || '').replace(/^#/, '') : '';
    if (!id && location.hash) id = location.hash.slice(1);
    var pane = id ? document.getElementById(id) : null;
    return pane && shown(pane) ? pane : null;
  }
  // prefer: 'drawer' 면 드로어/모달만, 'pane' 이면 활성 탭부터
  function baseScope(prefer) {
    var d = drawerRoot(), m = modalRoot(), p = paneRoot();
    if (prefer === 'drawer') return d || m || p || document.body;
    if (prefer === 'pane') return p || document.body;
    return d || m || p || document.body;
  }

  var HEAD_SEL = 'h1,h2,h3,h4,h5,h6,legend,caption,summary,th,.card-title,.head,.stay-card__title,.section-title,.title,strong,b';

  // 머리 글자에서 위로 올라가며 실제 내용이 든 상자를 찾는다
  function containerOf(head, root, need) {
    var n = head.parentElement, hops = 0;
    while (n && root.contains(n) && hops++ < 6) {
      if (n.querySelector(need || CTRL_SEL)) return n;
      n = n.parentElement;
    }
    return null;
  }

  // 제목이 든 머리띠(버튼만 있는 줄)가 아니라 표·목록·칸이 실제로 든 상자까지 올라간다
  function contentBox(h, root) {
    var n = h.parentElement, k = 0;
    while (n && root.contains(n) && k++ < 8) {
      if (n.querySelector('table,tr,li,' + CTRL_SEL)) return n;
      n = n.parentElement;
    }
    return null;
  }

  function narrowCard(root, card) {
    if (!card || !root) return root;
    var heads = [].slice.call(root.querySelectorAll(HEAD_SEL));
    // `오퍼 · 룸` 두 겹 이름은 먼저 표의 행 묶음으로 찾는다 — 앞 조각(오퍼)만 맞는 제목이 앞글자 일치로 먼저 잡히면 안 된다
    if (/[·・‧∙]/.test(nfc(card))) { var g0 = tableGroup(root, heads, card); if (g0) return g0; }
    var best = null, bt = 0, bs = Infinity;
    for (var i = 0; i < heads.length; i++) {
      var t = tier(textOf(heads[i]), card);
      if (t < 2) continue;
      // 제목이 표의 한 행 안에 있으면(예: 시즌 표의 `LOW SEASON`) 그 행이 카드다 — 표 전체로 넓히지 않는다
      var rowBox = heads[i].closest('tr,li');
      // 제목이 카드 상자(.stay-card 등) 안에 있으면 그 상자가 카드다 — 빈 카드(행 없음)도 옆 카드까지 넓히지 않는다
      var cardBox = heads[i].closest('.stay-card,.card,section,fieldset,details');
      var box = (rowBox && rowBox !== root && root.contains(rowBox) && rowBox.querySelector(CTRL_SEL + ',button,a'))
        ? rowBox : (cardBox && cardBox !== root && root.contains(cardBox) && cardBox.querySelector(CTRL_SEL + ',button,a'))
        ? cardBox : (contentBox(heads[i], root) || containerOf(heads[i], root, CTRL_SEL + ',button,a'));
      if (!box) continue;
      var size = box.querySelectorAll('*').length;
      if (t > bt || (t === bt && size < bs)) { best = box; bt = t; bs = size; }
    }
    if (!best) { var g = tableGroup(root, heads, card); if (g) return g; }
    return best || root;
  }

  // `오퍼 · 룸` 두 겹 카드가 표의 행 묶음일 때(요금제 탭): 앞 조각(오퍼)이 맞는 제목 뒤에 나오는 뒤 조각(룸) 제목 행부터,
  // 다음 룸 제목 행(제목 조각이 2개 이상인 행) 전까지를 한 묶음으로 본다. 묶음은 querySelectorAll 을 가진 가벼운 범위 객체로 돌려준다.
  function tableGroup(root, heads, card) {
    var parts = nfc(card).split(/\s+[·・‧∙]\s+/).map(clean).filter(Boolean);
    if (parts.length < 2) return null;
    var headPart = parts.slice(0, -1).join(' · '), tail = parts[parts.length - 1];
    var lastHead = null, hit = null;
    for (var i = 0; i < heads.length; i++) {
      var h = heads[i]; if (!shown(h)) continue;
      var tx = textOf(h);
      if (tier(tx, headPart) >= 2) { lastHead = h; continue; }
      if (lastHead && tier(tx, tail) >= 3) { hit = h; break; }
    }
    if (!hit) return null;
    var tr0 = hit.closest('tr'); if (!tr0 || !root.contains(tr0)) return null;
    var kindSel = hit.tagName.toLowerCase() + (hit.className ? '.' + String(hit.className).trim().split(/\s+/)[0] : '');
    var rows = [tr0], sib = tr0.nextElementSibling;
    while (sib) {
      if (sib.tagName === 'TR' && sib.querySelectorAll(kindSel).length >= 2) break;
      if (sib.tagName === 'TR') rows.push(sib);
      sib = sib.nextElementSibling;
    }
    return groupScope(rows);
  }
  function groupScope(rows) {
    var all = function (sel) { var out = []; rows.forEach(function (r) { if (r.matches && r.matches(sel)) out.push(r); [].push.apply(out, [].slice.call(r.querySelectorAll(sel))); }); return out; };
    return {
      nodeType: 1, tagName: 'STAY-GROUP', id: '', className: 'stay-group', rows: rows,
      querySelectorAll: all,
      querySelector: function (sel) { return all(sel)[0] || null; },
      contains: function (el) { return rows.some(function (r) { return r === el || r.contains(el); }); },
      get textContent() { return rows.map(function (r) { return r.textContent; }).join(' '); },
      get innerHTML() { return rows.map(function (r) { return r.outerHTML; }).join(''); },
      get offsetParent() { return rows[0].offsetParent; },
      get children() { return rows; },
      matches: function () { return false; }, closest: function () { return null; }, getAttribute: function () { return null; }
    };
  }

  var SECTION_HEAD_SEL = 'h1,h2,h3,h4,h5,h6,legend,caption,.card-title,.stay-card__title,.stay-section-title,.section-title';
  // 행 바로 앞(문서 순서)에 있는 절 제목이 card 와 얼마나 맞는지 — 같은 이름의 행이 두 표에 있을 때 가른다
  function sectionTierOf(el, root, card) {
    if (!card) return 0;
    var heads = [].slice.call(root.querySelectorAll(SECTION_HEAD_SEL));
    var last = null;
    for (var i = 0; i < heads.length; i++) {
      var h = heads[i];
      if (el.contains(h) || !shown(h)) continue;
      if (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) last = h; else break;
    }
    return last ? tier(textOf(last), card) : 0;
  }

  // 행이 속한 카드(상자)의 머리글 — `오퍼 · 룸` 처럼 두 겹 이름일 때 앞부분과 맞춘다
  function cardHeadOf(el, root) {
    var box = el.parentElement, k = 0;
    while (box && box !== root && k++ < 12) {
      var h = box.querySelector('.stay-card__head,.card-title,h1,h2,h3,h4,h5,h6,legend,caption');
      if (h && !el.contains(h) && (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)) return textOf(h);
      box = box.parentElement;
    }
    return '';
  }

  var narrowState = { rowMissing: false };

  function rowCandidates(root) {
    return [
      [].slice.call(root.querySelectorAll('tr')),
      [].slice.call(root.querySelectorAll('li,.row,[class*="row"],[class*="item"]'))
    ];
  }

  // 행의 칸 하나가 이름과 얼마나 맞는지 — `디럭스` 를 찾을 때 `그랜드 디럭스` 행(포함, 1)보다 `디럭스` 행(일치, 4)이 이긴다
  function rowTier(el, row) {
    var t = tier(textOf(el), row);
    var cells = [].slice.call(el.children || []);
    // 칸 글자가 이름의 일부(포함, 1)인 것은 세지 않는다 — `오퍼 · 룸` 두 겹 이름이 룸 칸만으로 잡히면 안 된다
    for (var i = 0; i < cells.length; i++) { var ct = tier(textOf(cells[i]), row); if (ct >= 2 && ct > t) t = ct; }
    return t;
  }

  function narrowRow(root, row, card) {
    if (!row || !root) return root;
    var pass = rowCandidates(root);
    for (var p = 0; p < pass.length; p++) {
      var best = null, bs = Infinity, bh = -1, brt = 0;
      for (var i = 0; i < pass[p].length; i++) {
        var el = pass[p][i];
        if (!shown(el)) continue;
        var rt = rowTier(el, row);
        if (rt < 1) continue;
        var size = el.querySelectorAll('*').length;
        var ht = sectionTierOf(el, root, card);
        if (rt > brt || (rt === brt && (ht > bh || (ht === bh && size < bs)))) { best = el; bs = size; bh = ht; brt = rt; }
      }
      if (best) return best;
    }
    // `앞 · 뒤` 두 겹 이름: 뒤는 행 글자, 앞은 행이 든 카드 머리글과 맞춘다
    var parts = nfc(row).split(/\s+[·・‧∙]\s+/).map(clean).filter(Boolean);
    if (parts.length >= 2) {
      var tail = parts[parts.length - 1], head = parts.slice(0, -1).join(' · ');
      for (var q = 0; q < pass.length; q++) {
        var best2 = null, bs2 = Infinity, bt2 = 0;
        for (var j = 0; j < pass[q].length; j++) {
          var el2 = pass[q][j];
          if (!shown(el2)) continue;
          var rt = tier(textOf(el2), tail); if (rt < 1) continue;
          var ct = tier(cardHeadOf(el2, root), head); if (ct < 1) continue;
          var size2 = el2.querySelectorAll('*').length, score = rt + ct;
          if (score > bt2 || (score === bt2 && size2 < bs2)) { best2 = el2; bs2 = size2; bt2 = score; }
        }
        if (best2) return best2;
      }
    }
    return null;
  }

  function narrow(root, o) {
    o = o || {};
    var card = o.card || o.block;
    var s = narrowCard(root, card);
    narrowState.rowMissing = false;
    if (!o.row) {
      // 카드 이름이 제목이 아니라 표의 한 행(예: 시즌 표의 `LOW SEASON`)일 때는 그 행으로 좁힌다
      if (card && s === root) { var asRow = narrowRow(root, card, null); if (asRow) return asRow; }
      return s;
    }
    var r = narrowRow(s, o.row, card);
    if (!r && s !== root) r = narrowRow(root, o.row, card); // 카드 안에서 행을 못 찾으면 전체에서 다시
    if (!r) { narrowState.rowMissing = true; return s; }
    return r;
  }

  /* ─────────────────────────── 라벨 → 입력 요소 ─────────────────────────── */

  // 감싸는 라벨의 자기 글자(안에 든 입력 요소 글자는 뺀다)
  function labelOwnText(lab) {
    var t = '';
    for (var i = 0; i < lab.childNodes.length; i++) {
      var n = lab.childNodes[i];
      if (n.nodeType === 3) t += n.nodeValue;
      else if (n.nodeType === 1 && !isCtrl(n) && !n.querySelector(CTRL_SEL)) t += n.textContent;
    }
    return clean(t) || textOf(lab);
  }

  // 입력 요소 앞에 놓인 제목 글자 (`.head`·`.form_label` 같은 것)
  function headLabel(el) {
    var box = el.closest('.control,.form_item,.input-field,.field,.form-group,td,li');
    if (box) {
      var h = box.querySelector('.head,.form_label,.label,legend');
      if (h && !h.querySelector(CTRL_SEL)) { var t = clean(textOf(h)); if (t) return t; }
    }
    var n = el, hops = 0;
    while (n && hops++ < 4) {
      var sib = n.previousElementSibling;
      while (sib) {
        if (!isCtrl(sib) && !sib.querySelector(CTRL_SEL)) {
          var s = clean(textOf(sib));
          if (s && s.length <= 60) return s;
        }
        sib = sib.previousElementSibling;
      }
      n = n.parentElement;
    }
    return '';
  }

  // 한 입력 요소가 가진 라벨 후보들 (prio 클수록 믿을 만하다)
  function labelsOf(el) {
    var out = [];
    var push = function (t, p) { t = clean(t); if (t) out.push({ text: t, prio: p }); };
    if (el.id) {
      var esc = (window.CSS && CSS.escape) ? CSS.escape(el.id) : el.id.replace(/"/g, '\\"');
      [].slice.call(document.querySelectorAll('label[for="' + esc + '"]')).forEach(function (l) { push(textOf(l), 5); });
    }
    if (el.getAttribute('aria-label')) push(el.getAttribute('aria-label'), 5);
    var wrap = el.closest('label');
    if (wrap) push(labelOwnText(wrap), 4);
    var tr = el.closest('tr');
    if (tr) {
      // 한 줄에 `머리칸 칸 머리칸 칸` 이 이어지면 내 칸 바로 앞의 머리칸이 내 이름표다
      var th = null, cur = el.closest('td');
      while (cur && cur.previousElementSibling) { cur = cur.previousElementSibling; if (cur.tagName === 'TH') { th = cur; break; } }
      if (!th) th = tr.querySelector('th');
      if (th) {
        var thText = textOf(th);
        push(thText, 3);
        // 머리칸 하나에 칸이 둘 이상이고 머리칸 글자가 `전화 / 이메일` 꼴이면 순서대로 한 조각씩 붙인다
        var td = el.closest('td');
        if (td) {
          var mates = [].slice.call(td.querySelectorAll(CTRL_SEL)).filter(function (c) { return isCtrl(c) && usable(c); });
          if (mates.length > 1) {
            var parts = thText.split(/\s*[\/·]\s*/).map(clean).filter(Boolean), idx = mates.indexOf(el);
            if (parts.length === mates.length && idx >= 0) push(parts[idx], 3);
            else parts.forEach(function (pt) { push(pt, 2); }); // `정액 · 정률` 처럼 조각이 칸 수와 안 맞으면 조각 전부를 후보로
          }
        }
      }
    }
    push(headLabel(el), 2);
    // 체크박스 한 개와 짝지어 한 줄에 서는 입력 — 그 체크박스 글자를 이름에 붙인다 (2026-09-04)
    // 판매 연결 일괄 추가 드로어의 룸별 [오퍼별 표시명] 이 그 꼴이다(CO-31667): 라벨 요소가 없고
    // 자리표시 글자가 N 칸 모두 같아서, 룸 이름을 붙이지 않으면 어느 칸인지 가릴 수가 없다.
    // 지시서는 `오퍼별 표시명 · Single` 처럼 적는다(뒤집힌 차례도 받는다).
    var mate = mateBoxLabel(el);
    if (mate) {
      var base = clean(noParen(el.placeholder || '')) || clean(headLabel(el));
      if (base) { push(base + ' · ' + mate, 4); push(mate + ' · ' + base, 4); }
    }
    if (el.placeholder) push(el.placeholder, 1);
    return out;
  }

  // 이 입력과 한 줄에 선 체크박스가 **하나뿐**일 때 그 체크박스의 글자. 아니면 빈 문자열.
  // 조건을 좁게 잡는다 — 어메니티처럼 체크박스가 여럿인 칸에서는 엉뚱한 이름이 붙으면 안 된다.
  function mateBoxLabel(el) {
    if (/^(checkbox|radio)$/.test(el.type)) return '';
    var node = el.parentElement;
    for (var depth = 0; node && depth < 3; depth++, node = node.parentElement) {
      var boxes = [].slice.call(node.querySelectorAll('input[type=checkbox],input[type=radio]'));
      if (!boxes.length) continue;
      if (boxes.length > 1) return '';
      var others = [].slice.call(node.querySelectorAll(CTRL_SEL)).filter(function (c) { return isCtrl(c) && !/^(checkbox|radio)$/.test(c.type); });
      if (others.length !== 1 || others[0] !== el) return '';
      var lab = boxes[0].closest('label');
      return lab ? clean(labelOwnText(lab)) : '';
    }
    return '';
  }

  // 라벨로 입력 요소 찾기 → [{el, tier, prio, matched}] (가장 잘 맞는 등급만)
  function findControls(scope, label) {
    var ctrls = [].slice.call(scope.querySelectorAll(CTRL_SEL)).filter(function (el) { return isCtrl(el) && usable(el); });
    var scored = [];
    for (var i = 0; i < ctrls.length; i++) {
      var el = ctrls[i], labs = labelsOf(el), best = 0, bp = 0, matched = '';
      for (var j = 0; j < labs.length; j++) {
        var t = tier(labs[j].text, label);
        if (t > best || (t === best && labs[j].prio > bp)) { best = t; bp = labs[j].prio; matched = labs[j].text; }
      }
      if (best >= 2) scored.push({ el: el, tier: best, prio: bp, matched: matched });
    }
    if (!scored.length) return [];
    var top = Math.max.apply(null, scored.map(function (s) { return s.tier; }));
    return scored.filter(function (s) { return s.tier === top; })
      .sort(function (a, b) { return b.prio - a.prio || docOrder(a.el, b.el); });
  }

  // 값 종류에 어울리는 입력 요소인가 (한 칸에 입력이 둘일 때 골라내는 데 쓴다)
  function fits(el, kind) {
    var t = el.type;
    if (kind === 'file') return t === 'file';
    if (kind === 'typed') return el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && !/^(checkbox|radio|file)$/.test(t));
    if (kind === 'select' || kind === 'multi') return el.tagName === 'SELECT' || /^(checkbox|radio)$/.test(t);
    if (kind === 'check' || kind === 'uncheck') return /^(checkbox|radio)$/.test(t);
    return true; // empty 등은 아무거나
  }

  /* ─────────────────────────── 반복 행 ─────────────────────────── */

  var ADD_BUTTONS = [
    [/침대/, '침대 행 추가'],
    [/요율|시간대/, '요율 행 추가'],
    [/구간/, '구간 추가'],
    [/^단(tier)?$/i, '단 추가'],
    [/포인트/, '행 추가']
  ];
  function addButtonFor(group) {
    var g = norm(group);
    for (var i = 0; i < ADD_BUTTONS.length; i++) if (ADD_BUTTONS[i][0].test(g)) return ADD_BUTTONS[i][1];
    return '행 추가';
  }

  // `침대 구성 1 · 침대 종류` → {group:'침대 구성', n:1, field:'침대 종류'}
  function splitRepeat(label) {
    var m = nfc(label).match(/^(.*?)\s*(\d+)\s+[·・‧∙]\s+(.+)$/);
    return m && m[1].trim() ? { group: m[1].trim(), n: parseInt(m[2], 10), field: m[3].trim() } : null;
  }
  // `종류#2` → {label:'종류', n:2}
  function splitIndex(label) {
    var m = nfc(label).match(/^(.*?)\s*#\s*(\d+)$/);
    return m ? { label: m[1].trim(), n: parseInt(m[2], 10) } : null;
  }

  // 제목 요소 뒤에 이어지는 형제(또는 조상의 형제) 가운데 입력 칸을 가진 첫 상자
  function followingBox(h, scope) {
    var node = h;
    for (var up = 0; up < 4 && node && node !== scope; up++) {
      var sib = node.nextElementSibling, steps = 0;
      while (sib && steps++ < 8) {
        if (sib.querySelector && sib.querySelector(CTRL_SEL)) return sib;
        sib = sib.nextElementSibling;
      }
      node = node.parentElement;
    }
    return null;
  }
  function findSection(scope, group) {
    var cands = [];
    [].slice.call(scope.querySelectorAll('tr')).forEach(function (tr) {
      var th = tr.querySelector('th'); if (!th) return;
      var t = tier(textOf(th), group); if (!t) return;
      var td = tr.querySelector('td');
      if (td && td.querySelector(CTRL_SEL + ',button')) cands.push({ el: td, tier: t, size: td.querySelectorAll('*').length });
    });
    [].slice.call(scope.querySelectorAll(HEAD_SEL)).forEach(function (h) {
      var t = tier(textOf(h), group); if (!t) return;
      // 제목 '다음에 오는' 표·목록을 먼저 잡는다 — 제목의 조상 컨테이너는 다른 표까지 품고 있을 수 있다
      var box = followingBox(h, scope) || containerOf(h, scope, CTRL_SEL);
      if (box) cands.push({ el: box, tier: t, size: box.querySelectorAll('*').length });
    });
    if (!cands.length) return null;
    cands.sort(function (a, b) { return b.tier - a.tier || a.size - b.size; });
    return cands[0].el;
  }

  // 묶음 안의 행들. 표면 tbody 의 tr, 아니면 입력을 가진 형제 묶음 중 가장 많은 것.
  function sectionRows(sec) {
    if (!sec) return [];
    var tb = sec.querySelector('tbody');
    if (tb) {
      var rs = [].slice.call(tb.children).filter(function (r) { return r.tagName === 'TR' && r.querySelector(CTRL_SEL); });
      if (rs.length) return rs;
    }
    var tr = [].slice.call(sec.querySelectorAll('tr')).filter(function (r) { return r.querySelector(CTRL_SEL); });
    if (tr.length) return tr;
    var best = [], bn = 0;
    var scan = function (node) {
      var kids = [].slice.call(node.children).filter(function (k) { return k.querySelector(CTRL_SEL) || isCtrl(k); });
      if (kids.length > bn) { bn = kids.length; best = kids; }
      for (var i = 0; i < node.children.length; i++) scan(node.children[i]);
    };
    scan(sec);
    return bn >= 1 ? best : [];
  }

  async function ensureRow(scope, group, n, opts) {
    var sec = findSection(scope, group);
    if (!sec) return { error: true, status: 'not-found', detail: '반복 행 묶음 `' + group + '` 을 찾지 못했습니다' };
    var rows = sectionRows(sec);
    if (rows.length < n) {
      var text = (opts && opts.addButton) || addButtonFor(group);
      var guard = 0;
      while (rows.length < n && guard++ < 30) {
        var btn = findButton(sec, text) || findButton(scope, text) || findButton(baseScope(), text);
        if (!btn) return { error: true, status: 'not-found', detail: '행 추가 버튼 [' + text + '] 을 찾지 못했습니다' };
        btn.click();
        await sleep(150);
        sec = findSection(scope, group) || sec;
        rows = sectionRows(sec);
      }
    }
    if (rows.length < n) return { error: true, status: 'not-found', detail: group + ' 행이 ' + rows.length + '개뿐입니다(필요 ' + n + ')' };
    return { row: rows[n - 1], section: sec };
  }

  // 행 안에서 칸 찾기: 표 머리글 열 → 라벨 → 하나뿐이면 그것
  function findInRow(row, field, kind) {
    var table = row.closest ? row.closest('table') : null;
    if (table) {
      var heads = [].slice.call(table.querySelectorAll('thead th, thead td'));
      if (heads.length) {
        var hit = pick(heads, textOf, field, 2);
        if (hit.status === 'ok') {
          var idx = heads.indexOf(hit.el);
          var cells = [].slice.call(row.children);
          var cell = cells[idx] || null;
          if (cell) {
            var cs = [].slice.call(cell.querySelectorAll(CTRL_SEL)).filter(function (e) { return isCtrl(e) && usable(e); });
            var fit = cs.filter(function (e) { return fits(e, kind); });
            var use = fit.length ? fit : cs;
            if (use.length) return use.map(function (e) { return { el: e, tier: 4, prio: 3, matched: textOf(hit.el) }; });
          }
        }
      }
    }
    var found = findControls(row, field);
    if (found.length) return found;
    var all = [].slice.call(row.querySelectorAll(CTRL_SEL)).filter(function (e) { return isCtrl(e) && usable(e) && fits(e, kind); });
    if (all.length === 1) return [{ el: all[0], tier: 1, prio: 0, matched: '(행 안 유일한 칸)' }];
    return [];
  }

  /* ─────────────────────────── 값 넣기 ─────────────────────────── */

  function setNativeValue(el, value) {
    var proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype
      : el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    var d = Object.getOwnPropertyDescriptor(proto, 'value');
    if (d && d.set) d.set.call(el, value); else el.value = value;
  }
  function fire(el, names) {
    (names || ['input', 'change']).forEach(function (n) { el.dispatchEvent(new Event(n, { bubbles: true })); });
  }
  function setText(el, value) {
    setNativeValue(el, value === null || value === undefined ? '' : String(value));
    fire(el);
    return { status: 'ok', detail: el.value };
  }
  function selectedText(sel) {
    var o = sel.options[sel.selectedIndex];
    return o ? clean(o.textContent) : '';
  }
  function pickOption(sel, text) {
    return pick([].slice.call(sel.options), function (o) { return o.textContent; }, text, 1);
  }
  function setSelectValue(sel, value) {
    var d = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
    if (d && d.set) d.set.call(sel, value); else sel.value = value;
    fire(sel);
  }

  function setNativeSelect(sel, text) {
    var hit = pickOption(sel, text);
    if (hit.status === 'not-found') return { status: 'not-found', detail: '`' + text + '` 옵션이 없습니다 · 화면 옵션: ' + optionList(sel) };
    if (hit.status === 'ambiguous') {
      // 글자가 완전히 같은 옵션이 여럿이면 값이 가장 큰(가장 최근에 만든) 것을 고른다.
      // 시즌 드로어의 취소정책 목록이 그랬다 — 다른 호텔의 같은 이름 정책까지 다 들어 있었다.
      // 그 ERP 결함은 고쳐졌다(2026-09-04, CO-31675/31680: `policy_choices_for_master` 로 공용 +
      // 이 호텔 전용만 내려준다). 이 갈래는 다른 목록에서 같은 일이 생길 때를 위한 보루로 남긴다.
      var same = [].slice.call(sel.options).filter(function (o) { return tier(o.textContent, text) === hit.tier; });
      var texts = same.map(function (o) { return clean(o.textContent); });
      var allSame = texts.every(function (t) { return t === texts[0]; });
      var nums = same.map(function (o) { return parseInt(o.value, 10); });
      if (allSame && nums.every(function (n) { return !isNaN(n); })) {
        var best = same.reduce(function (a, o) { return parseInt(o.value, 10) > parseInt(a.value, 10) ? o : a; }, same[0]);
        setSelectValue(sel, best.value);
        return { status: 'ok', detail: selectedText(sel) + ' (같은 이름 ' + same.length + '개 중 최근 것)' };
      }
      return { status: 'ambiguous', detail: '`' + text + '` 에 맞는 옵션이 ' + hit.count + '개입니다' };
    }
    setSelectValue(sel, hit.el.value);
    return { status: 'ok', detail: selectedText(sel) };
  }
  function optionList(sel) {
    return [].slice.call(sel.options).slice(0, 12).map(function (o) { return clean(o.textContent); }).join(' / ');
  }

  // Materialize 셀렉트: 표시 칸 클릭 → 목록 항목 클릭 → 숨은 select 확인
  async function setMaterialize(sel, text) {
    var hit = pickOption(sel, text);
    if (hit.status !== 'ok') return setNativeSelect(sel, text); // 옵션 자체가 없거나 모호하면 그대로 알림
    var wrap = sel.closest('.select-wrapper');
    var trig = wrap ? wrap.querySelector('input.select-dropdown') : null;
    if (trig) {
      trig.click();
      await sleep(180);
      var ul = (wrap && wrap.querySelector('ul.select-dropdown')) || document.querySelector('ul.select-dropdown.dropdown-content');
      var li = null;
      if (ul) {
        var items = [].slice.call(ul.querySelectorAll('li')).filter(function (l) { return !l.classList.contains('disabled'); });
        var r = pick(items, textOf, text, 3);
        if (r.status === 'ok') li = r.el;
      }
      if (li) { li.click(); await sleep(180); }
      else { pressEsc(); }
      if (tier(selectedText(sel), text) >= 3) return { status: 'ok', detail: selectedText(sel) };
    }
    // 목록 조작이 안 되면 값 대입으로 마무리하고 표시 칸도 맞춘다
    setSelectValue(sel, hit.el.value);
    if (trig) trig.value = clean(hit.el.textContent);
    return { status: 'ok', detail: selectedText(sel) + ' (값 대입)' };
  }

  // select2 자동완성: mousedown 으로 열고, 검색 칸에 글자 + input·keyup, 결과에 mouseup
  async function setSelect2(sel, text) {
    var box = sel.nextElementSibling && sel.nextElementSibling.classList.contains('select2') ? sel.nextElementSibling : null;
    var trig = box ? box.querySelector('.select2-selection') : null;
    if (!trig) return { status: 'not-found', detail: '자동완성 위젯을 찾지 못했습니다' };
    // 다른 자동완성 목록이 열려 있으면 먼저 닫는다 — 검색어가 엉뚱한 칸에 들어가는 것을 막는다
    closeSelect2All();
    await sleep(120);
    trig.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
    await sleep(200);
    var field = openSelect2Field();
    if (!field) return { status: 'not-found', detail: '자동완성 검색 칸이 열리지 않았습니다' };
    // 검색어는 전체 → 괄호 앞 → 괄호 안 순서로 시도한다. 화면 옵션은 `다낭(DAD)` 처럼
    // 한글명+공항코드 꼴이라, 지시서의 `푸꾸옥 (PHU QUOC)` 을 통째로 치면 안 걸린다.
    var terms = [text], m = nfc(text).match(/^(.*?)\s*[（(]\s*(.*?)\s*[）)]\s*$/);
    if (m) { if (m[1].trim()) terms.push(m[1].trim()); if (m[2].trim()) terms.push(m[2].trim()); }
    var opt = null, amb = 0;
    for (var ti = 0; ti < terms.length && !opt && !amb; ti++) {
      field = openSelect2Field() || field;
      setNativeValue(field, terms[ti]);
      field.dispatchEvent(new Event('input', { bubbles: true }));
      ['keydown', 'keyup'].forEach(function (n) {
        field.dispatchEvent(new KeyboardEvent(n, { bubbles: true, key: 'a', keyCode: 65, which: 65 }));
      });
      var t0 = Date.now();
      while (Date.now() - t0 < 3500) {
        await sleep(200);
        var items = [].slice.call(document.querySelectorAll('.select2-results__option')).filter(function (o) {
          return !o.classList.contains('loading-results') && !o.classList.contains('select2-results__message') &&
            o.getAttribute('aria-disabled') !== 'true';
        });
        if (!items.length) continue;
        var r = pick(items, textOf, text, 2);
        if (r.status === 'ambiguous') { amb = r.count; break; }
        if (r.status === 'ok') { opt = r.el; break; }
      }
    }
    if (amb) { pressEsc(); return { status: 'ambiguous', detail: '`' + text + '` 에 맞는 검색 결과가 ' + amb + '개입니다' }; }
    if (!opt) { pressEsc(); return { status: 'not-found', detail: '`' + text + '` 이(가) 검색 결과에 없습니다' }; }
    opt.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
    await sleep(300);
    if (!sel.value) { opt.click(); await sleep(300); }
    if (!sel.value) return { status: 'not-found', detail: '고른 값이 화면에 반영되지 않았습니다' };
    closeSelect2All();
    return { status: 'ok', detail: selectedText(sel) || sel.value };
  }

  // 열려 있는 select2 목록의 검색 칸 — 목록 컨테이너는 body 끝에 붙으므로 마지막 것이 지금 연 것이다
  function openSelect2Field() {
    var opens = [].slice.call(document.querySelectorAll('.select2-container--open'));
    for (var i = opens.length - 1; i >= 0; i--) {
      var f = opens[i].querySelector('.select2-dropdown .select2-search__field');
      if (f) return f;
    }
    return document.querySelector('.select2-container--open .select2-search__field');
  }
  function closeSelect2All() {
    var any = false;
    [].slice.call(document.querySelectorAll('select.select2-hidden-accessible')).forEach(function (s) {
      try { if (window.jQuery && jQuery(s).data('select2') && jQuery(s).data('select2').isOpen()) { jQuery(s).select2('close'); any = true; } } catch (e) {}
    });
    if (!any && document.querySelector('.select2-container--open')) pressEsc();
  }

  async function setSelectAny(sel, text) {
    if (sel.classList.contains('select2-hidden-accessible')) return setSelect2(sel, text);
    if (sel.closest('.select-wrapper')) return setMaterialize(sel, text);
    return setNativeSelect(sel, text);
  }

  function setChecked(el, want) {
    if (el.disabled) return { status: 'skipped', detail: '잠긴 칸입니다' };
    if (!!el.checked === !!want) return { status: 'ok', detail: want ? '이미 켜져 있음' : '이미 꺼져 있음' };
    el.click();
    if (!!el.checked !== !!want) { el.checked = !!want; fire(el, ['click', 'input', 'change']); }
    return { status: !!el.checked === !!want ? 'ok' : 'not-found', detail: el.checked ? '켬' : '끔' };
  }

  // 체크·라디오 묶음: 감싸는 라벨 글자로 고른다
  function boxLabel(el) {
    var labs = labelsOf(el).filter(function (l) { return l.prio >= 4; });
    if (labs.length) return labs[0].text;
    var p = el.parentElement;
    return p ? clean(textOf(p)) : '';
  }
  function setGroup(boxes, kind, values) {
    var detail = [], missing = [], amb = [];
    if (kind === 'uncheck' || kind === 'empty' || (!values.length && kind !== 'check')) {
      boxes.forEach(function (b) { if (b.type === 'checkbox' && b.checked) setChecked(b, false); });
      return { status: 'ok', detail: '모두 해제(' + boxes.length + '칸)' };
    }
    if (kind === 'check' && !values.length) {
      if (boxes.length !== 1) return { status: 'ambiguous', detail: '체크할 칸이 ' + boxes.length + '개입니다' };
      var r0 = setChecked(boxes[0], true);
      return { status: r0.status, detail: r0.detail };
    }
    values.forEach(function (v) {
      var r = pickLoose(boxes, boxLabel, v, 2);
      if (r.status !== 'ok') {
        // `오퍼 · 룸 · 요금제` 처럼 겹 이름 칸에서 값이 뒤 조각(요금제)만이면: 뒤 조각이 맞는 칸 가운데
        // 이미 켜 둔 다른 묶음(대상 룸)의 이름을 품은 칸을 전부 켠다 — 없으면 뒤 조각이 맞는 칸 전부
        var tails = boxes.filter(function (b) { var tp = tailPart(boxLabel(b)); return tp && tier(tp, v) >= 3; });
        if (tails.length) {
          var form = boxes[0].closest('form, .stay-drawer, .stay-modal, .modal') || document;
          var onLabels = [].slice.call(form.querySelectorAll('input[type=checkbox]:checked, input[type=radio]:checked')).filter(function (c) { return boxes.indexOf(c) < 0; }).map(boxLabel).filter(Boolean);
          var narrowed = tails.filter(function (b) { var lb = boxLabel(b); return onLabels.some(function (cl) { return lb.indexOf(cl) >= 0; }); });
          (narrowed.length ? narrowed : tails).forEach(function (b) { setChecked(b, true); detail.push(boxLabel(b)); });
          return;
        }
      }
      if (r.status === 'not-found') { missing.push(v); return; }
      if (r.status === 'ambiguous') { amb.push(v); return; }
      if (r.el.type === 'radio') { r.el.click(); if (!r.el.checked) { r.el.checked = true; fire(r.el); } }
      else setChecked(r.el, true);
      detail.push(boxLabel(r.el));
    });
    if (amb.length) return { status: 'ambiguous', detail: '여럿에 맞는 값: ' + amb.join(', ') };
    if (missing.length) return { status: 'not-found', detail: '없는 값: ' + missing.join(', ') + ' · 화면 항목: ' + boxes.slice(0, 12).map(boxLabel).join(' / ') };
    return { status: 'ok', detail: detail.length + '칸 켬 — ' + trunc(detail.join(', '), 160) };
  }

  function clearField(el) {
    if (el.type === 'checkbox' || el.type === 'radio') return setChecked(el, false);
    if (el.tagName === 'SELECT') {
      var empty = [].slice.call(el.options).filter(function (o) { return o.value === '' || /^\(?(선택|없음|선택하세요|지정 안 함)/.test(clean(o.textContent)); });
      var o2 = empty[0] || el.options[0];
      if (o2) { setSelectValue(el, o2.value); return { status: 'ok', detail: selectedText(el) }; }
      return { status: 'skipped', detail: '비울 옵션이 없습니다' };
    }
    if (el.type === 'file') return { status: 'skipped', detail: '파일 칸은 비우지 않습니다' };
    return setText(el, '');
  }

  /* ─────────────────────────── 버튼 ─────────────────────────── */

  var BTN_SEL = 'button,a,input[type=submit],input[type=button],[role=button]';
  function btnText(el) {
    if (el.tagName === 'INPUT') return clean(el.value);
    var t = clean(el.textContent);
    return t.replace(/^\[(.*)\]$/, '$1');
  }
  function findButton(scope, want, strict) {
    if (!scope || !want) return null;
    var w = String(want).replace(/^\[(.*)\]$/, '$1').trim();
    var list = [].slice.call(scope.querySelectorAll(BTN_SEL)).filter(function (b) {
      return !b.disabled && b.getAttribute('aria-disabled') !== 'true' && shown(b);
    });
    // 정확 일치(괄호 무시 포함)를 범위 안 → 문서 전체 순으로 먼저 찾고, 그다음에야 범위 안 접두 일치.
    // 글자 '포함'만으로는 절대 고르지 않는다 — `저장` 을 찾다가 `메모저장` 을 누르는 사고를 막는다.
    var r = pick(list, btnText, w, 3);
    if (r.status === 'not-found' && scope !== document.body) {
      var all = [].slice.call(document.body.querySelectorAll(BTN_SEL)).filter(function (b) {
        return !b.disabled && b.getAttribute('aria-disabled') !== 'true' && shown(b);
      });
      r = pick(all, btnText, w, 3);
    }
    if (r.status === 'not-found' && !strict) r = pick(list, btnText, w, 2); // strict: 앞글자만 맞는 버튼(`추가` → `추가수집정보` 탭)은 고르지 않는다
    return r.el || null;
  }

  var DANGER = [
    [/^삭제$|^그룹\s*삭제$|^선택삭제$/, '삭제 버튼입니다'],
    [/^보관$/, '보관 버튼입니다'],
    [/^닫기$|^\d+월\s*닫기$|^월\s*닫기$/, '닫기(판매일을 닫는) 버튼입니다'],
    [/^공용으로$/, '다른 호텔에도 영향을 주는 버튼입니다'],
    [/^판매\s*종료$|^보관\s*해제$/, '판매 상태를 바꾸는 버튼입니다']
  ];
  function refusal(btn, want) {
    var t = btnText(btn) || String(want || '');
    if (norm(t) === norm('판매 시작')) return { reason: 'sale-start', detail: '[판매 시작] 은 사용자가 직접 누릅니다 — 도우미는 절대 누르지 않습니다' };
    for (var i = 0; i < DANGER.length; i++) if (DANGER[i][0].test(clean(t))) return { reason: 'dangerous', detail: DANGER[i][1] + ' — 사용자 확인 뒤 force 로만 누릅니다' };
    if (btn.hasAttribute('hx-confirm') || btn.hasAttribute('data-confirm') ||
      (btn.hasAttribute('onclick') && /confirm\(/.test(btn.getAttribute('onclick') || '')))
      return { reason: 'confirm', detail: '누르면 확인창이 뜨는 버튼입니다 — 사용자 확인 뒤 force 로만 누릅니다' };
    return null;
  }

  function pressEsc() {
    ['keydown', 'keyup'].forEach(function (t) {
      document.dispatchEvent(new KeyboardEvent(t, { key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true }));
    });
  }

  /* ─────────────────────────── 화면 상태 ─────────────────────────── */

  function loginPage() {
    var p = document.querySelector('input[type=password],input[name=password]');
    return !!(p && usable(p));
  }
  function toastText() {
    var t = document.querySelector('#toast-container .toast');
    return t && shown(t) ? trunc(textOf(t), 200) : '';
  }
  // 요소를 줄 단위로 읽는다. innerText 가 있으면 그것을, 없으면 덩어리 요소마다 한 줄로 모은다.
  function blockLines(root) {
    if (typeof root.innerText === 'string' && root.innerText.trim()) {
      return root.innerText.split('\n').map(clean).filter(Boolean);
    }
    var out = [];
    var BLOCK = /^(DIV|P|LI|TR|SECTION|ARTICLE|H[1-6]|UL|OL|TABLE|TBODY|FORM)$/;
    var walk = function (n) {
      var kids = [].slice.call(n.children);
      if (!kids.some(function (k) { return BLOCK.test(k.tagName); })) {
        var t = clean(n.textContent); if (t) out.push(t);
        return;
      }
      kids.forEach(walk);
    };
    walk(root);
    return out;
  }

  function bannerLines() {
    var b = document.getElementById('stay_validation_banner');
    var out = { blockers: [], warnings: [] };
    if (!b || !shown(b)) return out;
    var bucket = null;
    var lines = blockLines(b);
    for (var i = 0; i < lines.length; i++) {
      var ln = lines[i];
      if (/🔴|이대로면\s*못\s*팝니다/.test(ln)) { bucket = out.blockers; continue; }
      if (/🟡|채우면\s*좋음/.test(ln)) { bucket = out.warnings; continue; }
      if (!bucket) continue;
      if (/^(이건 넘어가기|넘어가기|다시 보기|제안값 보기|세후가로 확정|판매 시작|같은 문제|외 \d+건|넘어감|판매중|판매 없음)/.test(ln)) continue;
      if (ln.length < 6) continue;
      if (bucket.length < 40) bucket.push(trunc(ln, 220));
    }
    return out;
  }
  function readState() {
    var d = document.querySelector('.stay-drawer.is-open');
    var m = modalRoot();
    var lw = document.getElementById('logout-warning-modal');
    var link = currentTabLink();
    var idm = location.pathname.match(/\/stay\/(\d+)(\/|$)/);
    return {
      version: VERSION,
      url: location.href,
      hotelId: idm ? idm[1] : null,
      loginPage: loginPage(),
      loggedIn: !loginPage(),
      logoutWarning: !!(lw && shown(lw)),
      drawer: { open: !!d, title: d ? textOf(d.querySelector('.stay-drawer__title')) : '' },
      modal: { open: !!m, title: m ? trunc(textOf(m.querySelector('.modal-header,h4,h5,.modal-title')) || textOf(m).slice(0, 60), 80) : '' },
      activeTab: link ? textOf(link) : '',
      banner: bannerLines(),
      toast: toastText(),
      scope: describe(baseScope())
    };
  }

  function collectErrors(scope) {
    var out = [];
    var push = function (t) { t = clean(t); if (t && out.indexOf(t) < 0 && out.length < 12) out.push(trunc(t, 200)); };
    var root = scope && scope.querySelectorAll ? scope : document.body;
    [].slice.call(root.querySelectorAll('.errorlist li,.errorlist')).forEach(function (e) { if (shown(e)) push(textOf(e)); });
    [].slice.call(root.querySelectorAll('[class*="error"],[class*="invalid"],.helper-text,.invalid-feedback')).forEach(function (e) {
      if (e.closest('#stay_validation_banner,#logout-warning-modal')) return;
      if (!shown(e) || e.querySelector(CTRL_SEL)) return;
      var st = getComputedStyle(e);
      if (e.classList.contains('helper-text') && !/rgb\(2[0-9]{2},|red|f44336/i.test(st.color)) return;
      push(textOf(e));
    });
    var t = toastText(); if (t) push(t);
    return out;
  }

  /* ─────────────────────────── 공개 API ─────────────────────────── */

  function remember(r) { api.last = r; return r; }

  async function tab(name) {
    var links = [].slice.call(document.querySelectorAll('ul.tab-container a, ul.tabs a'));
    var r = pick(links, textOf, name, 2);
    if (r.status !== 'ok') return remember({ status: r.status, detail: '탭 `' + name + '` 을 찾지 못했습니다', tabs: links.map(textOf) });
    r.el.click();
    await waitFor(function () { return tier(textOf(currentTabLink()), name) >= 2 && paneRoot(); }, 5000);
    await sleep(150);
    return remember({ status: 'ok', tab: textOf(currentTabLink()), hash: location.hash, scope: describe(baseScope()) });
  }

  function rowsIn(root) {
    return rowCandidates(root)[0].filter(shown).map(function (r) { return trunc(textOf(r), 60); }).slice(0, 30);
  }

  async function open(spec) {
    var s = spec || {};
    var root = s.within && s.within.querySelectorAll ? s.within : (s.inDrawer === true ? baseScope('drawer') : baseScope('pane'));
    var scope = s.within ? narrow(root, { row: s.row }) : narrow(root, s);
    if (s.row && narrowState.rowMissing) {
      var d0 = drawerRoot(), scope2 = d0 ? narrow(d0, s) : null;
      if (!scope2 || narrowState.rowMissing) return remember({ status: 'not-found', reason: 'row', detail: '`' + s.row + '` 행을 찾지 못했습니다', scope: describe(scope), rows: rowsIn(root) });
      scope = scope2;
    }
    var btn = s.button ? findButton(scope, s.button) : null;
    if (!btn && s.inDrawer !== true) {
      var d = drawerRoot();
      if (d) btn = findButton(narrow(d, s), s.button);
    }
    if (!btn) return remember({ status: 'not-found', detail: '버튼 [' + s.button + '] 을 찾지 못했습니다', scope: describe(scope), buttons: buttonsIn(scope) });
    var no = refusal(btn, s.button);
    if (no && !s.force) return remember({ status: 'refused', reason: no.reason, detail: no.detail });
    var before = { drawer: !!drawerRoot(), modal: !!modalRoot(), body: (drawerRoot() || {}).innerHTML ? drawerRoot().innerHTML.length : 0 };
    hx.error = null;
    btn.click();
    var ok = await waitFor(function () {
      var d2 = drawerRoot(), m2 = modalRoot();
      if (m2 && !before.modal) return true;
      if (d2 && !before.drawer) return true;
      if (d2 && before.drawer && hx.pending === 0 && d2.innerHTML.length !== before.body) return true;
      return false;
    }, WAIT_MS);
    await sleep(200);
    var st = readState();
    if (st.loginPage) return remember({ status: 'login', detail: '로그인 화면이 나타났습니다 — 사용자가 로그인해야 합니다', url: st.url });
    return remember({
      status: ok ? 'ok' : 'timeout',
      drawer: st.drawer, modal: st.modal,
      errors: hx.error ? [hx.error] : [],
      fields: ok ? fieldsIn() : []
    });
  }

  function buttonsIn(scope) {
    return [].slice.call((scope || baseScope()).querySelectorAll(BTN_SEL)).filter(shown).map(btnText).filter(Boolean).slice(0, 25);
  }

  // 지금 범위에 보이는 칸 목록 (설명서와 대조하거나 라벨을 확인할 때)
  function fieldsIn(opts) {
    var scope = narrow(baseScope(), opts || {});
    var seen = [];
    return [].slice.call(scope.querySelectorAll(CTRL_SEL)).filter(function (e) { return isCtrl(e) && usable(e); }).map(function (e) {
      var labs = labelsOf(e);
      var lab = labs.length ? labs[0].text : '';
      var kind = e.tagName === 'SELECT' ? (e.classList.contains('select2-hidden-accessible') ? 'select2' : e.closest('.select-wrapper') ? 'select(M)' : 'select')
        : e.tagName === 'TEXTAREA' ? 'textarea' : e.type;
      var key = lab + '|' + kind;
      if (seen.indexOf(key) >= 0 && /^(checkbox|radio)$/.test(e.type)) return null;
      seen.push(key);
      return { label: lab, kind: kind, name: e.name || '' };
    }).filter(Boolean).slice(0, 80);
  }

  async function addRow(buttonText, n, opts) {
    var scope = narrow(baseScope(), opts || {});
    var times = n || 1, done = 0;
    for (var i = 0; i < times; i++) {
      var btn = findButton(scope, buttonText) || findButton(baseScope(), buttonText);
      if (!btn) return remember({ status: 'not-found', detail: '버튼 [' + buttonText + '] 을 찾지 못했습니다', clicked: done });
      btn.click(); done++;
      await sleep(150);
    }
    return remember({ status: 'ok', clicked: done });
  }

  function normalizeField(f) {
    if (typeof f === 'string') return { label: f, kind: 'typed', value: '' };
    var o = { label: String(f.label || ''), kind: f.kind || 'typed' };
    o.value = f.text !== undefined ? f.text : f.value;
    o.values = f.values;
    o.file = f.file;
    return o;
  }

  // 라벨이 칸 이름이 아니라 묶음 제목일 때(예 `어메니티` 아래 체크박스 여러 개): 제목으로 묶음을 찾아 그 안의 체크박스를 돌려준다
  function groupBoxes(scope, label) {
    // 제목(예 `어메니티`)을 찾고, 그 뒤에 이어지는 형제 상자들 가운데 체크박스만 든 것을 전부 모은다.
    // 소묶음(구조·욕실…)이 여러 개여도 텍스트·셀렉트 칸이 나오는 상자 앞까지는 한 묶음으로 본다.
    var heads = [].slice.call(scope.querySelectorAll(HEAD_SEL)).filter(function (h) { return tier(textOf(h), label) >= 3 && shown(h); });
    if (!heads.length) return [];
    var h = heads[0], out = [], node = h;
    for (var up = 0; up < 4 && node && node !== scope && !out.length; up++) {
      var sib = node.nextElementSibling, steps = 0;
      while (sib && steps++ < 30) {
        var boxes = [].slice.call(sib.querySelectorAll('input[type=checkbox],input[type=radio]')).filter(usable);
        var others = [].slice.call(sib.querySelectorAll(CTRL_SEL)).filter(function (c) { return isCtrl(c) && usable(c) && !/^(checkbox|radio)$/.test(c.type); });
        if (boxes.length && !others.length) { out = out.concat(boxes); }
        else if (others.length) { break; }
        // 컨트롤이 하나도 없는 형제(숨은 입력·안내문)는 건너뛰고 계속 본다
        sib = sib.nextElementSibling;
      }
      node = node.parentElement;
    }
    if (!out.length) { var sec = findSection(scope, label); if (sec) out = [].slice.call(sec.querySelectorAll('input[type=checkbox],input[type=radio]')).filter(usable); }
    return out.map(function (b) { return { el: b, tier: 3, prio: 3, matched: label }; });
  }
  // 같은 이름의 칸이 여럿일 때 값으로 가른다: select 면 그 값이 옵션에 있는 칸, 글자면 글자 칸(select 아님)
  function disambiguate(list, kind, values) {
    var v = values && values.length ? values[0] : '';
    if (kind === 'select' && v) {
      var withOpt = list.filter(function (c) { return c.el.tagName === 'SELECT' && pickOption(c.el, v).status === 'ok'; });
      if (withOpt.length === 1) return withOpt;
    }
    if (kind === 'typed') {
      var texts = list.filter(function (c) { return c.el.tagName !== 'SELECT' && !/^(checkbox|radio|file)$/.test(c.el.type); });
      if (texts.length === 1) return texts;
    }
    if (kind === 'select') {
      var sels = list.filter(function (c) { return c.el.tagName === 'SELECT'; });
      if (sels.length === 1) return sels;
    }
    // 이름표의 급이 다르면 높은 급만, 그래도 여럿이고 같은 칸(td) 안이면 첫 칸이 그 이름표의 주인이다
    var top = Math.max.apply(null, list.map(function (c) { return c.prio || 0; }));
    var best = list.filter(function (c) { return (c.prio || 0) === top; });
    if (best.length === 1) return best;
    var cell = best[0].el.closest('td,.control,.form_item');
    if (cell && best.every(function (c) { return c.el.closest('td,.control,.form_item') === cell; })) return [best[0]];
    return list;
  }

  async function applyOne(scope, f, opts) {
    var out = { label: f.label, kind: f.kind, status: 'not-found', detail: '' };
    if (f.kind === 'auto') { out.status = 'skipped'; out.detail = '저절로 차는 칸 — 건드리지 않았습니다'; return out; }

    var target = scope, name = f.label, idx = 0;
    var rep = splitRepeat(f.label);
    if (rep) {
      var r = await ensureRow(scope, rep.group, rep.n, opts);
      if (r.error) { out.status = r.status; out.detail = r.detail; return out; }
      target = r.row; name = rep.field;
    }
    var ix = splitIndex(name);
    if (ix) { name = ix.label; idx = ix.n - 1; }

    var cands = rep ? findInRow(target, name, f.kind) : findControls(target, name);
    if (!cands.length && target !== scope) cands = findControls(scope, name);
    if (!cands.length && /^(multi|select|check|uncheck|empty)$/.test(f.kind)) cands = groupBoxes(scope, name);
    if (!cands.length && /[·・‧∙]/.test(name)) { // `제공 주기 · 1박당 제공 (…)` 처럼 두 조각 이름은 뒤 조각(화면 라벨)으로 다시 찾는다
      var tparts = name.split(/\s+[·・‧∙]\s+/).filter(Boolean), tailName = tparts[tparts.length - 1];
      cands = rep ? findInRow(target, tailName, f.kind) : findControls(target, tailName);
      if (!cands.length && target !== scope) cands = findControls(scope, tailName);
      if (!cands.length && /^(multi|select|check|uncheck|empty)$/.test(f.kind)) cands = groupBoxes(scope, tailName);
      if (cands.length) name = tailName;
    }
    if (cands.length && /^(multi|check|uncheck)$/.test(f.kind) && !cands.some(function (c) { return /^(checkbox|radio)$/.test(c.el.type); })) { var gb = groupBoxes(scope, name); if (gb.length) cands = gb; }
    if (!cands.length && (f.kind === 'empty' || f.kind === 'uncheck')) { out.status = 'skipped'; out.detail = '화면에 없는 칸 — 비워 둘 것이 없습니다'; return out; }
    if (!cands.length) {
      out.detail = '`' + name + '` 칸을 찾지 못했습니다 · 화면 칸: ' +
        trunc(fieldsIn().map(function (x) { return x.label; }).filter(Boolean).join(' / '), 300);
      return out;
    }

    var boxes = cands.filter(function (c) { return /^(checkbox|radio)$/.test(c.el.type); }).map(function (c) { return c.el; });
    var values = f.values && f.values.length ? f.values : (f.value !== undefined && f.value !== null && f.value !== '' ? [String(f.value)] : []);

    // 체크·라디오 묶음
    if (boxes.length && (boxes.length === cands.length || f.kind === 'multi' || f.kind === 'check' || f.kind === 'uncheck')) {
      var g = setGroup(boxes, f.kind, f.kind === 'multi' || f.kind === 'select' ? values : (f.kind === 'check' && values.length ? values : []));
      out.status = g.status; out.detail = g.detail; out.matched = cands[0].matched;
      return out;
    }

    var fit = cands.filter(function (c) { return fits(c.el, f.kind); });
    // 글자 값을 체크 칸에 쓰지 않는다 (2026-09-04). `오퍼별 표시명 · Single` 같은 가운뎃점 이름은
    // 못 찾으면 뒤 조각(`Single`)으로 다시 찾는데, 그 조각이 룸 체크박스 글자와 같다 — 막지 않으면
    // 표시명이 체크박스에 조용히 쓰인다. 되읽기 경로(`readOne`)는 쓰지 않으므로 그대로 둔다.
    if (!fit.length && /^(typed|file)$/.test(f.kind) && cands.every(function (c) { return /^(checkbox|radio)$/.test(c.el.type); })) {
      out.detail = '`' + name + '` 에 맞는 것이 체크 칸뿐입니다 — 글자를 넣을 칸이 아닙니다 (' +
        cands.map(function (c) { return c.matched; }).join(' · ') + ')';
      return out;
    }
    var use = fit.length ? fit : cands;
    if (use.length > 1 && !ix) use = disambiguate(use, f.kind, values);
    if (use.length > 1 && !ix && (f.kind === 'empty' || f.kind === 'uncheck')) {
      // 비울 칸이 여럿에 걸리면 이미 비어 있는지만 본다 — 비어 있으면 건너뛴다
      var dirty = use.filter(function (c) { return c.el.tagName === 'SELECT' ? (c.el.value && !/^-+$/.test(c.el.value) && !/^(-+|\(?선택|없음)/.test(optionText(c.el))) : (c.el.type === 'checkbox' ? c.el.checked : !!clean(c.el.value)); });
      if (!dirty.length) { out.status = 'skipped'; out.detail = '여러 칸에 걸리지만 모두 비어 있음'; return out; }
      use = dirty;
    }
    if (use.length > 1 && !ix) {
      out.status = 'ambiguous';
      out.detail = '`' + name + '` 에 맞는 칸이 ' + use.length + '개입니다 — 라벨 뒤에 #2 처럼 순번을 붙여 주세요 (' +
        use.map(function (c) { return c.matched + '/' + (c.el.name || c.el.type); }).join(' · ') + ')';
      return out;
    }
    var el = use[idx] ? use[idx].el : null;
    if (!el) { out.detail = '`' + name + '` 의 ' + (idx + 1) + '번째 칸이 없습니다(' + use.length + '개)'; return out; }
    out.matched = (use[idx] && use[idx].matched) || '';
    return applyToEl(el, f, values, out);
  }

  // 고른 칸에 값을 넣는다 (applyOne 의 뒷부분 — 순서로 찾은 칸에도 같이 쓴다)
  async function applyToEl(el, f, values, out) {
    out.name = el.name || '';
    out._el = el;

    if (el.type === 'file' && (f.kind === 'empty' || (!values.length && !f.file))) {
      out.status = 'skipped'; out.detail = '비워 두는 파일 칸 — 건드리지 않았습니다'; return out;
    }
    if (el.type === 'file') {
      el.setAttribute('data-stay-upload', f.label);
      out.status = 'needs-upload';
      out.detail = '파일 칸입니다 — 브라우저 도구로 올리세요';
      out.multiple = !!el.multiple;
      out.accept = el.getAttribute('accept') || '';
      out.marker = '[data-stay-upload="' + f.label + '"]';
      return out;
    }
    if (f.kind === 'empty' || (!values.length && f.kind !== 'check')) {
      var c1 = clearField(el); out.status = c1.status; out.detail = c1.detail; return out;
    }
    if (el.tagName === 'SELECT') {
      var s1 = await setSelectAny(el, values[0]);
      if (s1.status === 'ok' && values.length > 1 && el.multiple) {
        for (var i = 1; i < values.length; i++) await setSelectAny(el, values[i]);
      }
      out.status = s1.status; out.detail = s1.detail; return out;
    }
    if (el.type === 'checkbox' || el.type === 'radio') {
      var c2 = setChecked(el, f.kind !== 'uncheck'); out.status = c2.status; out.detail = c2.detail; return out;
    }
    var t1 = setText(el, values.join(', '));
    out.status = t1.status; out.detail = trunc(t1.detail, 120);
    return out;
  }

  // 순서로 칸을 찾을 때 세는 칸: 보이는 글자·선택 칸(체크·라디오·파일 제외)
  function orderedControls(scope) {
    return [].slice.call(scope.querySelectorAll(CTRL_SEL)).filter(function (c) { return isCtrl(c) && usable(c) && !/^(checkbox|radio|file)$/.test(c.type); });
  }
  function orderableKind(f) { return /^(typed|select|empty|auto)$/.test(f.kind); }
  function orderable(f) { return orderableKind(f) && !splitRepeat(f.label); }
  // 이름표가 화면과 다른 칸(영문 이름표 등)은 지시서의 순서로 찾는다: 앞(또는 뒤)에서 이름으로 찾은 칸을 기준으로 몇 칸 떨어졌는지 센다
  function guessAmong(ctrls, list, els, idxs, i) {
    var pos = function (el) { return ctrls.indexOf(el); };
    var at = idxs.indexOf(i); if (at < 0) return null;
    var a, gap, j;
    for (a = at - 1, gap = 0; a >= 0; a--) { j = idxs[a]; if (els[j] && pos(els[j]) >= 0) break; gap++; }
    if (a >= 0) { var c = ctrls[pos(els[idxs[a]]) + gap + 1]; if (c && els.indexOf(c) < 0) return c; }
    for (a = at + 1, gap = 0; a < idxs.length; a++) { j = idxs[a]; if (els[j] && pos(els[j]) >= 0) break; gap++; }
    if (a < idxs.length) { var c2 = ctrls[pos(els[idxs[a]]) - gap - 1]; if (c2 && els.indexOf(c2) < 0) return c2; }
    // 기준 칸이 하나도 없고 칸 수가 같으면 자리 그대로
    if (idxs.length === ctrls.length && els.indexOf(ctrls[at]) < 0) return ctrls[at];
    return null;
  }
  function guessByOrder(scope, list, els, i) {
    var f = list[i];
    if (!orderableKind(f)) return null;
    var rep = splitRepeat(f.label);
    if (rep) {
      // 반복 행 안: 같은 묶음·같은 번호의 칸들 사이에서 순서로
      var sec = findSection(scope, rep.group), rows = sectionRows(sec), row = rows[rep.n - 1];
      if (!row) return null;
      var idxs = []; list.forEach(function (g, k) { var r2 = splitRepeat(g.label); if (r2 && r2.group === rep.group && r2.n === rep.n && orderableKind(g)) idxs.push(k); });
      return guessAmong(orderedControls(row), list, els, idxs, i);
    }
    var idxs2 = []; list.forEach(function (g, k) { if (orderable(g)) idxs2.push(k); });
    return guessAmong(orderedControls(scope), list, els, idxs2, i);
  }

  async function fill(fields, opts) {
    var o = opts || {};
    var scope = narrow(baseScope(), o);
    var list = (fields || []).map(normalizeField);
    var res = [], els = [];
    for (var i = 0; i < list.length; i++) {
      try { res.push(await applyOne(scope, list[i], o)); await sleep(60); }
      catch (e) { res.push({ label: list[i].label, kind: list[i].kind, status: 'error', detail: String(e && e.message || e) }); }
      els.push(res[i]._el || null); delete res[i]._el;
    }
    // 2차: 이름으로 못 찾은 칸을 순서로
    for (var k = 0; k < list.length; k++) {
      if (res[k].status !== 'not-found') continue;
      var el = guessByOrder(scope, list, els, k);
      if (!el) continue;
      var f = list[k], values = f.values && f.values.length ? f.values : (f.value !== undefined && f.value !== null && f.value !== '' ? [String(f.value)] : []);
      var out2 = { label: f.label, kind: f.kind, status: 'not-found', detail: '' };
      try { out2 = await applyToEl(el, f, values, out2); } catch (e) { out2.status = 'error'; out2.detail = String(e && e.message || e); }
      out2.byOrder = true; out2.matched = '(순서로 찾음: ' + (labelsOf(el)[0] || {}).text + ')';
      els[k] = out2._el || el; delete out2._el;
      res[k] = out2; await sleep(60);
    }
    return remember(res);
  }

  // 범위 안 파일 칸 목록. 표식(data-stay-upload)을 남겨 브라우저 도구가 찾을 수 있게 한다.
  function fileInputs(opts) {
    var scope = narrow(baseScope(), opts || {});
    return [].slice.call(scope.querySelectorAll('input[type=file]')).map(function (el, i) {
      var labs = labelsOf(el);
      var lab = labs.length ? labs[0].text : ('파일 ' + (i + 1));
      el.setAttribute('data-stay-upload', lab);
      return { label: lab, name: el.name || '', multiple: !!el.multiple, accept: el.getAttribute('accept') || '', files: el.files ? el.files.length : 0 };
    });
  }

  async function submit(buttonText, opts) {
    var o = opts || {};
    var scope = narrow(baseScope(), o);
    var drawerEl = document.querySelector('.stay-drawer.is-open');
    var btn = findButton(scope, buttonText) || (drawerEl && findButton(drawerEl, buttonText)) || findButton(document.body, buttonText, true);
    if (!btn) return remember({ status: 'not-found', detail: '버튼 [' + buttonText + '] 을 찾지 못했습니다', buttons: buttonsIn(scope), url: location.href, errors: [] });
    var no = refusal(btn, buttonText);
    if (no && (no.reason === 'sale-start' || !o.force)) return remember({ status: 'refused', reason: no.reason, detail: no.detail, errors: [], url: location.href });

    var before = { drawer: !!drawerRoot(), modal: !!modalRoot(), url: location.href, path: location.pathname, settles: hx.settles, swaps: hx.swaps };
    hx.error = null;
    var origConfirm = null;
    if (o.force) { origConfirm = window.confirm; window.confirm = function () { return true; }; }
    try { btn.click(); } finally {
      if (origConfirm) { window.confirm = origConfirm; }
    }

    var status = 'timeout', t0 = Date.now();
    while (Date.now() - t0 < WAIT_MS) {
      await sleep(TICK);
      if (hx.unloading || location.pathname !== before.path) { status = 'navigated'; break; }
      if (hx.error) { status = 'settled'; break; }
      if (hx.pending === 0 && (hx.settles > before.settles || hx.swaps > before.swaps)) { await sleep(250); status = 'settled'; break; }
      if (before.drawer && !drawerRoot()) { status = 'settled'; break; }
      if (before.modal && !modalRoot()) { status = 'settled'; break; }
    }

    var st = readState();
    var after = narrow(baseScope(), o);
    var errors = collectErrors(after);
    if (hx.error) errors.unshift(hx.error);
    var out = { status: status, errors: errors, toast: st.toast, url: st.url, banner: st.banner };
    if (st.loginPage) out.status = 'login';
    else if (status === 'settled') {
      var closed = (before.drawer && !st.drawer.open) || (before.modal && !st.modal.open);
      out.status = closed ? 'closed' : 'stayed';
    }
    out.drawer = st.drawer; out.modal = st.modal;
    return remember(out);
  }

  function readOne(scope, f) {
    var out = { label: f.label, kind: f.kind, actual: null, same: null };
    if (f.kind === 'auto') { out.same = null; out.actual = '(자동)'; return out; }
    var target = scope, name = f.label;
    var rep = splitRepeat(f.label);
    if (rep) {
      var sec = findSection(scope, rep.group);
      var rows = sectionRows(sec);
      if (rows.length < rep.n) { out.actual = '(행 없음)'; out.same = false; return out; }
      target = rows[rep.n - 1]; name = rep.field;
    }
    var ix = splitIndex(name); var idx = 0;
    if (ix) { name = ix.label; idx = ix.n - 1; }
    var cands = rep ? findInRow(target, name, f.kind) : findControls(target, name);
    if (!cands.length && /^(multi|select|check|uncheck|empty)$/.test(f.kind)) cands = groupBoxes(scope, name);
    if (cands.length && /^(multi|check|uncheck)$/.test(f.kind) && !cands.some(function (c) { return /^(checkbox|radio)$/.test(c.el.type); })) { var gb = groupBoxes(scope, name); if (gb.length) cands = gb; }
    if (!cands.length) { out.actual = '(칸 없음)'; out.same = false; return out; }
    var boxes = cands.filter(function (c) { return /^(checkbox|radio)$/.test(c.el.type); }).map(function (c) { return c.el; });
    var values = f.values && f.values.length ? f.values : (f.value !== undefined && f.value !== null && f.value !== '' ? [String(f.value)] : []);

    if (boxes.length && (boxes.length === cands.length || f.kind === 'multi' || f.kind === 'check' || f.kind === 'uncheck')) {
      var on = boxes.filter(function (b) { return b.checked; }).map(boxLabel);
      out.actual = on;
      if (f.kind === 'uncheck' || f.kind === 'empty') out.same = on.length === 0;
      else if (f.kind === 'check' && !values.length) out.same = on.length > 0;
      else out.same = values.every(function (v) { return on.some(function (a) { return tierLoose(a, v) >= 2; }); });
      return out;
    }
    var fit = cands.filter(function (c) { return fits(c.el, f.kind); });
    var use = fit.length ? fit : cands;
    if (use.length > 1 && !ix) use = disambiguate(use, f.kind, values);
    var el = use[idx] ? use[idx].el : use[0].el;
    return readEl(el, f, values, out);
  }

  // 고른 칸의 값을 읽어 비교한다 (readOne 의 뒷부분)
  function readEl(el, f, values, out) {
    out._el = el;
    if (el.type === 'file') {
      var box = el.closest('td,.control,.card,section,div') || el.parentElement;
      out.actual = { files: el.files ? el.files.length : 0, thumbnails: box ? box.querySelectorAll('img').length : 0 };
      out.same = null; return out;
    }
    if (el.tagName === 'SELECT') {
      out.actual = selectedText(el);
      out.same = f.kind === 'empty' ? (!el.value || tier(out.actual, '선택') >= 1) : (values.length ? tier(out.actual, values[0]) >= 2 : null);
      return out;
    }
    if (el.type === 'checkbox' || el.type === 'radio') {
      out.actual = el.checked; out.same = f.kind === 'uncheck' || f.kind === 'empty' ? !el.checked : !!el.checked; return out;
    }
    out.actual = el.value;
    out.same = f.kind === 'empty' ? !clean(el.value) : (values.length ? norm(el.value) === norm(values.join(', ')) : null);
    return out;
  }

  function readback(fields, opts) {
    var scope = narrow(baseScope(), opts || {});
    var list = (fields || []).map(normalizeField);
    var els = [];
    var res = list.map(function (f) {
      try { return readOne(scope, f); }
      catch (e) { return { label: f.label, kind: f.kind, actual: null, same: false, error: String(e && e.message || e) }; }
    });
    res.forEach(function (r) { els.push(r._el || null); delete r._el; });
    // 이름으로 못 찾은 칸은 채울 때와 같은 순서 규칙으로 되읽는다
    for (var k = 0; k < list.length; k++) {
      if (res[k].actual !== '(칸 없음)') continue;
      var el = guessByOrder(scope, list, els, k);
      if (!el) continue;
      var f = list[k], values = f.values && f.values.length ? f.values : (f.value !== undefined && f.value !== null && f.value !== '' ? [String(f.value)] : []);
      var o2 = readEl(el, f, values, { label: f.label, kind: f.kind, actual: null, same: null });
      o2.byOrder = true; els[k] = o2._el || el; delete o2._el; res[k] = o2;
    }
    var checked = res.filter(function (r) { return r.same !== null; });
    return remember({
      fields: res,
      ok: checked.filter(function (r) { return r.same; }).length,
      total: checked.length,
      mismatch: res.filter(function (r) { return r.same === false; }).map(function (r) { return r.label; })
    });
  }

  async function close() {
    var m = modalRoot();
    if (m) {
      var b = findButton(m, '닫기') || m.querySelector('.modal-close,[data-dismiss],.close');
      if (b && !b.hasAttribute('hx-confirm')) b.click(); else pressEsc();
      await waitFor(function () { return !modalRoot(); }, 3000);
    }
    if (drawerRoot()) {
      pressEsc();
      try { window.dispatchEvent(new CustomEvent('stay-drawer-close')); } catch (e) { /* 무시 */ }
      await waitFor(function () { return !drawerRoot(); }, 3000);
    }
    return remember({ drawer: !!drawerRoot(), modal: !!modalRoot() });
  }

  // 파일 다리: 페이지에 고정된 숨은 파일 입력. 브라우저 도구가 여기에 파일을 올리면
  // takeFiles() 가 그 파일을 실제 대상 칸으로 옮겨 담는다(모달이 열릴 때마다 칸을 다시 찾지 않아도 된다).
  function bridge() {
    var el = document.getElementById('stay_file_bridge');
    if (!el) {
      el = document.createElement('input');
      el.type = 'file'; el.multiple = true; el.id = 'stay_file_bridge';
      el.setAttribute('aria-label', 'stay file bridge');
      el.style.cssText = 'position:fixed;left:0;bottom:0;width:1px;height:1px;opacity:0.01;z-index:2147483647;';
      document.body.appendChild(el);
    }
    return remember({ id: el.id, files: [].slice.call(el.files || []).map(function (f) { return f.name; }) });
  }
  // spec: {label, names:[…]} — label 로 대상 파일 칸을 찾고(없으면 범위 안 유일한 파일 칸), names 에 든 파일만 옮긴다(없으면 전부).
  async function takeFiles(spec) {
    spec = spec || {};
    var src = document.getElementById('stay_file_bridge');
    if (!src || !src.files || !src.files.length) return remember({ status: 'not-found', detail: '파일 다리에 올라온 파일이 없습니다' });
    var scope = narrow(baseScope(), spec);
    var target = null;
    if (spec.label) {
      var hits = findControls(scope, spec.label).filter(function (h) { return h.el.type === 'file'; });
      if (hits.length) target = hits[0].el;
    }
    if (!target) {
      var files = [].slice.call(scope.querySelectorAll('input[type=file]')).filter(function (f) { return f.id !== 'stay_file_bridge' && f.id !== 'stay_steps_upload'; });
      if (files.length === 1) target = files[0];
      else if (files.length > 1 && spec.index !== undefined) target = files[spec.index];
      else if (files.length > 1) return remember({ status: 'ambiguous', detail: '파일 칸이 ' + files.length + '개입니다 — label 이나 index 를 주세요', labels: files.map(function (f) { return labelsOf(f).map(function (c) { return c.text; })[0] || f.name; }) });
    }
    if (!target) return remember({ status: 'not-found', detail: '대상 파일 칸을 찾지 못했습니다' });
    var want = spec.names && spec.names.length ? spec.names : null;
    var dt = new DataTransfer(), moved = [];
    [].slice.call(src.files).forEach(function (f) {
      if (!want || want.indexOf(f.name) >= 0) { if (!target.multiple && dt.items.length) return; dt.items.add(f); moved.push(f.name); }
    });
    if (!moved.length) return remember({ status: 'not-found', detail: '옮길 파일이 없습니다: ' + (want || []).join(', '), have: [].slice.call(src.files).map(function (f) { return f.name; }) });
    target.files = dt.files;
    fire(target, ['input', 'change']);
    // 화면이 파일을 읽어 미리보기를 만들 시간을 준다(이미지 모달은 이걸 기다리지 않으면 "등록해주세요" 가 뜬다)
    await sleep(spec.wait === undefined ? 900 : spec.wait);
    return remember({ status: 'ok', moved: moved, target: target.name || target.id || '(file)', targetMultiple: !!target.multiple });
  }
  function clearBridge() { var el = document.getElementById('stay_file_bridge'); if (el) el.value = ''; return remember({ ok: true }); }

  function keepAlive() {
    var lw = document.getElementById('logout-warning-modal');
    if (!lw || !shown(lw)) return remember({ clicked: false, logoutWarning: false });
    var b = findButton(lw, '확인');
    if (b) b.click();
    return remember({ clicked: !!b, logoutWarning: shown(lw) });
  }

  var api = {
    version: VERSION,
    last: null,
    state: readState,
    fields: fieldsIn,
    buttons: function (o) { return buttonsIn(narrow(baseScope(), o || {})); },
    fileInputs: fileInputs,
    tab: tab,
    open: open,
    fill: fill,
    addRow: addRow,
    submit: submit,
    readback: readback,
    close: close,
    keepAlive: keepAlive,
    bridge: bridge,
    takeFiles: takeFiles,
    clearBridge: clearBridge,
    sleep: sleep, waitFor: waitFor, tier: tier, findButton: findButton
  };

  window.stayRun = api;
  return { ok: true, version: VERSION, state: readState() };
})();
