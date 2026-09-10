/*!
 * stay_helper.js — ERP Stay 화면 도우미 (stay-setup-run v0.9.3)
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
 * `stayRun.progress({done, total, current, …})` 는 화면 오른쪽 위에 진행 표시 띠 한 줄을 그린다.
 * 지켜보는 사람이 콘솔을 열지 않고도 몇 번째 단계인지, 무엇이 실패했는지 본다. 준 값만 덮고 나머지는
 * 그대로 두며, 화면 조각이 갈려 띠가 사라지면 다시 붙인다. `progressState()` 로 지금 값을 읽고
 * `progressHide()`(또는 띠의 ✕)로 지운다.
 *
 * 기다리는 함수(open·fill·submit·addRow·tab·close)는 async 다. `await` 를 못 쓰는 도구라면
 * 호출한 뒤 잠깐 뒤에 `stayRun.last` 를 읽으면 마지막 결과가 들어 있다.
 */
(function () {
  'use strict';

  var VERSION = '0.6.2'; // 운영 2026-09-09 배포판 화면 기준(빈 상태 안내문 제외 · 비움+칸 없음 · 모달 재열기 · 페이지 [저장])
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
  // `A2C1_CHD · 성인 2 · 소아 1` 의 **앞쪽 조각** — 키가 앞에 서는 목록(가격 셀 편집 모달의
  // [인원 조합] 셀렉트, `forms.occupancy_select_label`)에서 그 키만으로 항목을 고를 때 쓴다.
  // 가운뎃점이 없는 항목(`인원 무관 단일가`)은 빈 글자를 돌려준다 — 조각이 아니라 이름 전부다.
  function leadPart(t) { var p = nfc(t).split(/\s+[·・‧∙]\s+/).map(clean).filter(Boolean); return p.length >= 2 ? p[0] : ''; }
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
  // 저장 뒤 응답이 끝났는지, 그리고 **서버가 거부했는지**를 알려면 htmx 이벤트를 세어야 한다.
  // 재주입해도 한 번만 붙인다.
  //
  // ── 이름이 두 벌이다 (2026-09-09 실측 · Codex 지적) ────────────────────────────
  // Stay 화면은 htmx **4.0.0-beta6** 을 싣는다(`common/templates/common/_htmx_stay.html`).
  // htmx 4 는 이벤트 이름을 **콜론 표기**로 바꿨다 — `htmx:afterSettle` 이 아니라
  // `htmx:after:settle` 이다. 카멜 이름만 듣던 종전 감시자는 **한 번도 깨어나지 않았고**,
  // 그래서 `error` 가 영영 null 이라 500·CSRF 403·네트워크 실패가 `errors: []` 로,
  // 셀 단계는 `submit:'settled'` 로 **성공 보고**됐다(`noSwap` 설정 때문에 화면에 배너도
  // 안 남는다 — 저장이 안 됐다는 표시가 아무 데도 없다).
  // 옛 화면(레거시 3개)은 아직 htmx 1·2 카멜 이름이므로 **두 표기를 다 듣는다.**
  //
  // ── 무엇을 들어야 하는가 (beta6 번들 소스 실측) ────────────────────────────────
  // 요청 한 건의 차례:
  //   htmx:before:request → (fetch) → htmx:before:response → htmx:after:request
  //   → 400+ 이면 htmx:response:error → (noSwap 이면 여기서 끝)
  //   → swap: htmx:after:swap · htmx:after:settle
  //   → 던져지면 htmx:error → **언제나** htmx:finally:request
  // 그래서 `pending--` 는 `after:request` 가 아니라 **`finally:request`** 에 건다 —
  // fetch 가 던지면(네트워크 끊김) `after:request` 는 아예 안 오고 `finally` 만 온다.
  // htmx 1·2 쪽의 언제나 오는 짝은 `afterRequest` 다. 한 요청에 감소가 두 번 걸리지
  // 않도록 **버전마다 하나씩만** 건다.
  //
  // ── 왜 document 에 거는가 ──────────────────────────────────────────────────────
  // htmx 4 코어는 元 element 가 DOM 에서 떨어져 있으면 이벤트를 `document` 에 쏜다
  // (`target = on?.isConnected ? on : document`). Stay 는 "패널 안 저장 버튼이 그 패널을
  // outerHTML 로 갈아끼우는" 모양이 대부분이라 swap 뒤에는 늘 떨어져 있다 —
  // `document` 에 직접 쏜 이벤트는 그 **아래**인 `document.body` 에 영영 닿지 않는다.
  function htmxWatch() {
    if (window.__stayRunHtmx) return window.__stayRunHtmx;
    // `errorStatus` 는 `error` 를 낸 응답의 코드다 — CSRF 403 만 골라 재시도하려면 이것이 있어야 한다
    // (다른 4xx·5xx 는 재시도하지 않는다: 저장이 실제로 들어간 뒤 난 오류일 수 있다).
    var st = { pending: 0, requests: 0, settles: 0, swaps: 0, error: null, errorStatus: null, lastStatus: null, unloading: false };
    var on = function (names, f) {
      names.forEach(function (n) { document.addEventListener(n, f, true); });
    };
    // 응답 코드 — htmx 1·2 는 `detail.xhr`, htmx 4 는 `detail.ctx.response` 다.
    var statusOf = function (e) {
      var d = (e && e.detail) || {};
      if (d.xhr && d.xhr.status) return d.xhr.status;
      if (d.ctx && d.ctx.response && d.ctx.response.status) return d.ctx.response.status;
      return '';
    };
    on(['htmx:beforeRequest', 'htmx:before:request'], function () { st.pending++; st.requests++; });
    on(['htmx:afterRequest', 'htmx:finally:request'], function () { st.pending = Math.max(0, st.pending - 1); });
    on(['htmx:afterSwap', 'htmx:after:swap'], function () { st.swaps++; });
    on(['htmx:afterSettle', 'htmx:after:settle'], function () { st.settles++; });
    // 응답 코드는 오류 이벤트뿐 아니라 `before:response`(htmx 4 · `detail.ctx.response.status`)
    // 에서도 온다. ERP 는 `noSwap` 이라 4xx·5xx 에서 화면이 그대로라, 오류 이벤트를 한 번이라도
    // 놓치면 거부가 통째로 안 보인다 — 두 자리 다 듣는다.
    on(['htmx:beforeResponse', 'htmx:before:response'], function (e) {
      var code = statusOf(e);
      if (!code) return;
      st.lastStatus = code;
      if (code >= 400 && !st.error) {
        st.error = '서버가 오류로 답했습니다 (' + code + ')';
        st.errorStatus = code;
      }
    });
    on(['htmx:responseError', 'htmx:response:error'], function (e) {
      var code = statusOf(e);
      st.error = '서버가 오류로 답했습니다' + (code ? ' (' + code + ')' : '');
      if (code) st.errorStatus = code;
    });
    on(['htmx:sendError'], function () { st.error = '요청을 보내지 못했습니다(네트워크)'; });
    on(['htmx:timeout'], function () { st.error = '요청이 시간 안에 끝나지 않았습니다'; });
    // htmx 4 에는 `sendError`·`timeout` 이 없다 — fetch 가 던지거나(네트워크·중단) 스왑 중
    // 스크립트가 터지면 전부 `htmx:error` 하나로 온다. 이미 응답 코드를 잡아 뒀으면
    // 그쪽이 더 또렷하므로 덮지 않는다.
    on(['htmx:error'], function (e) {
      if (st.error) return;
      var err = (e && e.detail && e.detail.error) || null;
      var msg = err ? (err.message || String(err)) : '';
      st.error = '요청이 끝나지 못했습니다(네트워크·스크립트)' + (msg ? ': ' + trunc(msg, 120) : '');
    });
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
  // 모달은 두 계열이다 — ERP 공용 Materialize(`.modal.open`, 기본정보 탭의 이미지 모달)와
  // Stay 자체의 2층 모달(`.stay-modal`, 가격 캘린더의 셀 편집 `#stay_cell_edit`).
  // 뒤엣것은 열려 있을 때만 DOM 에 있다(닫으면 조각째 사라진다) — 그래서 `shown` 만으로 갈린다.
  function modalRoot() {
    var list = [].slice.call(document.querySelectorAll('.modal.open, .stay-modal')).filter(function (el) {
      // 확인창(`#stay_confirm`)은 모달로 세지 않는다 — 따로 `confirmRoot()` 가 다룬다.
      return shown(el) && el.id !== CONFIRM_ID && !el.closest('#' + CONFIRM_ID);
    });
    return list.length ? list[list.length - 1] : null;
  }

  /* ─────────────────────── 페이지 안 확인창(hx-confirm) ───────────────────────
     ERP 2026-09-08 이후 `hx-confirm` 은 브라우저 네이티브 confirm 대신 페이지 안 확인창을
     띄운다. 열려 있는 동안 `document.documentElement` 에 `data-stay-confirm-open="1"` 이
     붙고, 루트는 `#stay_confirm`(role=dialog), 문구는 `#stay_confirm_text`,
     버튼은 `[data-stay-confirm="ok"]` / `[data-stay-confirm="cancel"]` 이다.
     네이티브 다이얼로그가 아니므로 탭이 멈추지 않는다 — 도구가 직접 눌러도 된다. */
  var CONFIRM_ID = 'stay_confirm';
  function confirmRoot() {
    var el = document.getElementById(CONFIRM_ID);
    if (!el) return null;
    if (document.documentElement.getAttribute('data-stay-confirm-open') === '1') return el;
    return shown(el) ? el : null;
  }
  function confirmState() {
    var el = confirmRoot();
    if (!el) return null;
    var t = el.querySelector('#stay_confirm_text');
    return { open: true, text: trunc(textOf(t) || textOf(el), 300) };
  }
  function confirmButton(kind) {
    var el = confirmRoot();
    return el ? el.querySelector('button[data-stay-confirm="' + kind + '"]') : null;
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
    // 2층 모달은 드로어 **안**에 뜬다(`.stay-modal__mask` 로 덮인다). 그때는 모달이 먼저다 —
    // 드로어를 골라 버리면 위에 덮인 모달 대신 아래 가려진 폼을 만지게 된다.
    if (m && d && d.contains(m) && prefer !== 'pane') return m;
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

  // 상자 안에 그 글자의 버튼이 정말 있는가 (문서 전체로 넓히지 않는다 — 여기서는 상자를 가르는 데만 쓴다)
  function boxHasButton(box, want) {
    if (!want || !box || !box.querySelectorAll) return false;
    var w = String(want).replace(/^\[(.*)\]$/, '$1').trim();
    return [].slice.call(box.querySelectorAll(BTN_SEL)).some(function (b) {
      return !b.disabled && b.getAttribute('aria-disabled') !== 'true' && shown(b) && tier(btnText(b), w) >= 3;
    });
  }

  // wantButton: 같은 이름이 여러 상자에 있을 때 **그 버튼을 가진 상자**를 먼저 고른다.
  // 오퍼 이름이 그런 이름이다 — [오퍼] 탭에서 오퍼 목록의 행에도, 그 아래 `연령 구간` 카드의
  // 머리에도 같은 이름이 있다. 행 쪽이 글자가 더 정확히 맞아(카드 머리에는 상태 표가 붙는다)
  // 이름만으로 고르면 [연령 구간 추가] 가 없는 행이 잡히고, 그다음 문서 전체 찾기가
  // **첫 오퍼의** 버튼을 눌러 버린다.
  function narrowCard(root, card, wantButton) {
    if (!card || !root) return root;
    var heads = [].slice.call(root.querySelectorAll(HEAD_SEL));
    // `오퍼 · 룸` 두 겹 이름은 먼저 표의 행 묶음으로 찾는다 — 앞 조각(오퍼)만 맞는 제목이 앞글자 일치로 먼저 잡히면 안 된다
    if (/[·・‧∙]/.test(nfc(card))) { var g0 = tableGroup(root, heads, card); if (g0) return g0; }
    var best = null, bt = 0, bs = Infinity, bh = 0;
    for (var i = 0; i < heads.length; i++) {
      // 접힌 제목은 후보가 아니다 — `tableGroup`·`sectionTierOf` 와 같은 규칙이다. 2026-09-09
      // 배포판부터 에이전트 모달 둘(`#stay_agent_install`·`#stay_agent_resume`)이 `hidden` 으로
      // **늘 실려 있어**, 이 걸음이 없으면 안 보이는 제목이 카드로 잡힐 수 있다.
      if (!shown(heads[i])) continue;
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
      var has = boxHasButton(box, wantButton) ? 1 : 0;
      // 순서: 그 버튼을 가졌는가 → 글자가 얼마나 맞는가 → 작은 상자
      if (has > bh || (has === bh && (t > bt || (t === bt && size < bs)))) { best = box; bt = t; bs = size; bh = has; }
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

  /* ────────────── 표의 rowspan 을 푼 열 자리 (2026-09-09 배포판) ──────────────
     가격 셀 편집 창의 위 표는 행이 아니라 **좌표 묶음**을 그린다 — 같은 인원 조합의 박수 층이
     한 묶음이고, `인원 조합` 칸은 그룹 첫 행이 `rowspan` 으로 층 전체(오류 배너 행까지)를
     덮는다. 그래서 층 둘째 행부터는 `<td>` 수가 열 수보다 하나 적다.

     자리(`row.children[i]`)로 세면 그 행에서 열이 통째로 한 칸씩 밀린다 — `판매가` 에 적을
     값이 `정가` 칸에 들어가고, 화면은 아무 것도 말하지 않는다. 그래서 표를 위에서부터 훑어
     격자를 만들고 **열 번호로** 칸을 돌려준다. colspan(오류 배너의 `colspan=6`)도 같이 푼다.

     캐시하지 않는다 — htmx 가 이 조각을 통째로 갈아 끼우므로 오래된 격자는 떨어져 나간
     노드를 가리킨다. 한 표는 많아야 수십 행이라 매번 세도 싸다. */
  function gridCells(table) {
    var out = [], carry = [];
    [].slice.call(table.querySelectorAll('tr')).filter(function (tr) {
      return tr.closest('table') === table; // 중첩 표의 행은 이 격자의 것이 아니다
    }).forEach(function (tr) {
      var cells = [].slice.call(tr.children).filter(function (c) { return /^(TD|TH)$/.test(c.tagName); });
      var line = [], i = 0, c = 0, guard = 0;
      while ((i < cells.length || (carry[c] && carry[c].left > 0)) && guard++ < 200) {
        if (carry[c] && carry[c].left > 0) { line[c] = carry[c].el; carry[c].left--; c++; continue; }
        var td = cells[i++];
        var rs = parseInt(td.getAttribute('rowspan') || '1', 10) || 1;
        var cs = parseInt(td.getAttribute('colspan') || '1', 10) || 1;
        for (var k = 0; k < cs; k++) {
          line[c] = td;
          if (rs > 1) carry[c] = { el: td, left: rs - 1 };
          c++;
        }
      }
      out.push({ row: tr, cells: line });
    });
    return out;
  }
  // 한 행의 열 자리 배열. 표 밖이거나 rowspan 이 없으면 `row.children` 그대로다.
  function rowCells(row) {
    if (!row || !row.closest) return [];
    var table = row.tagName === 'TR' ? row.closest('table') : null;
    if (!table) return [].slice.call(row.children || []);
    if (!table.querySelector('[rowspan]')) return [].slice.call(row.children || []);
    var grid = gridCells(table);
    for (var i = 0; i < grid.length; i++) if (grid[i].row === row) return grid[i].cells;
    return [].slice.call(row.children || []);
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
    // 행을 따로 주지 않은 열기(`open({button, card})`)는 버튼으로 상자를 가른다 — `narrowCard` 주석
    var s = narrowCard(root, card, o.row ? null : o.button);
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
    // 판매 연결 일괄 추가 드로어의 룸별 [오퍼별 표시명] 이 그 꼴이다: 라벨 요소가 없고
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

  /* ────────────────── 어메니티 카드의 `다른 룸에서 복사…` 셀렉트 ────────────────── */
  // 룸 만들기 드로어의 어메니티 카드에는 체크박스와 **나란히** 이름 없는 셀렉트가 하나 있다.
  // 첫 옵션이 `다른 룸에서 복사…` 이고 그 뒤로 다른 룸 이름이 늘어선다 — 다른 룸의 어메니티를
  // 통째로 베껴 오는 칸이지 지시서의 칸이 아니다. 걷어내지 않으면 `어메니티 | 선택: 욕조` 가
  // 이 셀렉트로 가서 "`욕조` 옵션이 없습니다 · 화면 옵션: 다른 룸에서 복사… / …" 로 끝나고
  // 어메니티는 한 칸도 켜지지 않는다 (2026-09-07 운영 실행에서 확인).
  function boxesNear(el) {
    var node = el.parentElement;
    for (var d = 0; node && d < 4; d++, node = node.parentElement) {
      var found = [].slice.call(node.querySelectorAll('input[type=checkbox]')).filter(usable);
      if (found.length) return found;
    }
    return [];
  }
  function isCopySelect(el) {
    if (!el || el.tagName !== 'SELECT') return false;
    var o0 = el.options && el.options[0];
    if (o0 && /복사/.test(clean(o0.textContent || ''))) return true;
    // 이름 없는 셀렉트가 체크 묶음과 한 상자에 있으면 제출되지 않는 보조 칸이다
    return !el.name && boxesNear(el).length > 0;
  }
  // 체크 묶음 칸에서 복사 셀렉트를 걷어낸다. 걷어낸 뒤 체크박스가 남지 않으면 제목으로 묶음을 다시 찾는다.
  function dropCopySelect(scope, cands, kind, name) {
    if (!cands.length || !/^(select|multi|check|uncheck|empty)$/.test(kind)) return cands;
    var kept = cands.filter(function (c) { return !isCopySelect(c.el); });
    if (kept.length === cands.length) return cands;
    if (kept.some(function (c) { return /^(checkbox|radio)$/.test(c.el.type); })) return kept;
    var gb = groupBoxes(scope, name);
    return gb.length ? gb : kept;
  }
  // 체크·라디오 묶음으로 다룰 칸인가. `선택: 욕조` 처럼 값이 하나여도 셀렉트가 없으면 묶음이다 —
  // 그러지 않으면 값 하나짜리 어메니티가 순서로 골라져 엉뚱한 칸이 켜진다.
  function groupable(cands, boxes, kind) {
    if (!boxes.length) return false;
    if (boxes.length === cands.length) return true;
    if (/^(multi|check|uncheck)$/.test(kind)) return true;
    return kind === 'select' && !cands.some(function (c) { return c.el.tagName === 'SELECT'; });
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
  // **정본 꼴만 받는다**: `<칸 이름> <N> · <하위 칸>` — 빈칸은 하나씩이고 가운뎃점은 앞뒤에 빈칸이
  // 있는 U+00B7 이다. 지시서 검사기·`parse_guide.py` `ROW_LABEL_RE` 와 한 글자도 다르면 안 된다 —
  // 한쪽만 반복 행으로 읽으면 N번째 행이 아니라 첫 행에 값이 들어간다.
  function splitRepeat(label) {
    var m = nfc(label).match(/^(\S(?:.*?\S)?) (\d+) · (.+)$/);
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
    // 형제 묶음 후보는 두 갈래다: **칸을 품은 상자들**의 묶음과 **칸 자체**의 묶음.
    // 상자 쪽이 먼저다. 요금제의 `포함물` 이 그 차이가 드러나는 자리다 —
    // `<div><input 이름><input 설명></div>` 가 되풀이되는데(열 제목이 없다),
    // 깊이만 보고 가장 많은 묶음을 고르면 **한 행의 두 입력**을 두 행으로 읽어
    // `포함물 2 · 포함물 이름` 이 1행의 설명 칸에 들어간다(2026-09-04 실측).
    var boxes = [], ctrls = [];
    var scan = function (node) {
      var kids = [].slice.call(node.children).filter(function (k) { return k.querySelector(CTRL_SEL) || isCtrl(k); });
      if (kids.length) {
        var allBoxes = kids.every(function (k) { return !isCtrl(k) && k.querySelector(CTRL_SEL); });
        if (allBoxes) { if (kids.length > boxes.length) boxes = kids; }
        else if (kids.length > ctrls.length) ctrls = kids;
      }
      for (var i = 0; i < node.children.length; i++) scan(node.children[i]);
    };
    scan(sec);
    return boxes.length ? boxes : ctrls;
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
          // 자리가 아니라 **열 번호**로 잡는다 — 좌표 묶음 표는 `인원 조합` 칸이 rowspan 이라
          // 층 둘째 행부터 `row.children` 이 한 칸씩 밀린다(`rowCells` 주석).
          var cells = rowCells(row);
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
  // 2026-09-08: 가격 셀 편집 모달의 [인원 조합] 이 텍스트 → 셀렉트로 바뀌었고, 항목 글자는
  // **키가 앞**이다 (`A2 · 성인 2` · `A2C1_CHD · 성인 2 · 소아 1`). 원고는 좌표만 적으므로
  // (`A2`) 글자 전체로는 앞부분 일치(2)가 둘 다에 걸려 `모호` 로 끝난다 — `A2` 는 `A2C1_CHD`
  // 의 앞글자이기도 하기 때문이다. 그래서 전체 글자로 하나가 안 나오면 **앞 조각끼리 완전히
  // 같은** 항목을 한 번 더 찾는다. 하나일 때만 쓰므로 종전에 잘 골라지던 목록은 그대로다.
  function pickOption(sel, text) {
    var opts = [].slice.call(sel.options);
    var r = pick(opts, function (o) { return o.textContent; }, text, 1);
    if (r.status === 'ok') return r;
    var lead = pick(opts, function (o) { return leadPart(o.textContent); }, text, 4);
    return lead.status === 'ok' ? lead : r;
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
      // 그 ERP 결함은 고쳐졌다(2026-09-04: 공용 +
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

  // 운영 2026-09-04 배포판 화면에서 실제로 쓰이는 글자다.
  // 이 목록에 없어도 `hx-confirm` 이 붙은 버튼은 아래 `refusal()` 이 따로 막는다 — 목록은
  // 확인창이 없어도 되돌릴 수 없는 버튼까지 잡기 위한 것이다.
  // 파일 고르개 라벨 — `<label class="stay-btn">사진 추가<input type="file" hidden …></label>`.
  // 버튼처럼 생겼지만 `<button>` 이 아니고, 눌러 봐야 파일 대화상자가 열릴 뿐이다. 올리는 일은
  // 파일을 칸에 담는 것(`takeFiles`)이 하고, 담는 순간 `change` 로 요청이 나간다.
  // 이것을 저장 버튼으로 착각하면 **드로어의 [저장] 을 대신 누르는** 사고가 난다(룸 사진 단계).
  function uploadLabel(scope, want) {
    if (!want) return null;
    var w = String(want).replace(/^\[(.*)\]$/, '$1').trim();
    var roots = [];
    if (scope && scope.querySelectorAll && scope !== document.body) roots.push(scope);
    roots.push(document.body);
    for (var i = 0; i < roots.length; i++) {
      var hit = [].slice.call(roots[i].querySelectorAll('label')).find(function (l) {
        return l.querySelector('input[type=file]') && tier(labelOwnText(l), w) >= 3;
      });
      if (hit) return hit;
    }
    return null;
  }

  var DANGER = [
    [/^삭제$|^그룹\s*삭제$|^선택삭제$/, '삭제 버튼입니다'],
    [/^보관$/, '보관 버튼입니다'],
    // 판매일 [닫기] 는 `1월 닫기` · `2026-01 닫기` 두 꼴로 그려진다.
    [/^(?:.*\s)?닫기$/, '닫기(판매일을 닫는) 버튼입니다'],
    [/^공용으로$/, '다른 호텔에도 영향을 주는 버튼입니다'],
    [/^판매\s*종료$|^보관\s*해제$|^판매\s*재개$/, '판매 상태를 바꾸는 버튼입니다'],
    // 룸 카테고리를 이 호텔 전용으로 갈라낸다 — 다른 호텔이 쓰던 카탈로그가 끊긴다
    [/^전용으로\s*분리$/, '룸 카테고리를 갈라내는 버튼입니다'],
    // 검증 배너의 [세후가로 확정] — 저장된 금액을 통째로 환산해 덮는다
    [/^세후가로\s*확정$/, '저장된 금액을 환산해 덮는 버튼입니다']
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
      modal: { open: !!m, id: m ? (m.id || '') : '', title: m ? trunc(textOf(m.querySelector('.stay-modal__title,.modal-header,h4,h5,.modal-title')) || textOf(m).slice(0, 60), 80) : '' },
      // 페이지 안 확인창이 떠 있으면 {open:true, text} — 아니면 null.
      confirm: confirmState(),
      activeTab: link ? textOf(link) : '',
      banner: bannerLines(),
      toast: toastText(),
      scope: describe(baseScope())
    };
  }

  // 오류로 세지 않고 **넘긴** 배경 안내문. 버리지는 않는다 — `submit` 이 `pageNotes` 로 돌려주므로
  // 담당자가 "무엇을 안 실었는지" 를 로그에서 볼 수 있다.
  var pageNotes = [];
  function collectErrors(scope) {
    var out = [];
    pageNotes = [];
    var push = function (t) { t = clean(t); if (t && out.indexOf(t) < 0 && out.length < 12) out.push(trunc(t, 200)); };
    var note = function (e) {
      if (!shown(e)) return;
      var t = clean(textOf(e));
      if (t && pageNotes.indexOf(t) < 0 && pageNotes.length < 6) pageNotes.push(trunc(t, 200));
    };
    var root = scope && scope.querySelectorAll ? scope : document.body;
    [].slice.call(root.querySelectorAll('.errorlist li,.errorlist')).forEach(function (e) { if (shown(e)) push(textOf(e)); });
    [].slice.call(root.querySelectorAll('[class*="error"],[class*="invalid"],.helper-text,.invalid-feedback')).forEach(function (e) {
      if (e.closest('#stay_validation_banner,#logout-warning-modal')) return;
      if (!shown(e) || e.querySelector(CTRL_SEL)) return;
      var st = getComputedStyle(e);
      if (e.classList.contains('helper-text') && !/rgb\(2[0-9]{2},|red|f44336/i.test(st.color)) return;
      push(textOf(e));
    });
    // 저장 거부 띠(`.stay-banner--blocking`) — 클래스에 `error` 가 없어 위 두 훑기가 통째로
    // 놓치던 자리다. 가격 셀 편집 창은 필드 오류를 칸 옆이 아니라 **한 배너에 모아** 그리므로
    // (`_calendar_cell_edit.html`: 컴팩트 표라 칸 옆에 둘 자리가 없다), 이것을 안 읽으면
    // "같은 인원 조합의 가격 행이 이미 있습니다" · "판매 가능한 셀은 0원일 수 없습니다" 같은
    // 거부가 `errors: []` 로 보고돼 담당자가 저장된 줄로 읽는다. 드로어 폼의 non_field_errors ·
    // 전개 불가 사유(`error_message`)도 같은 상자다.
    // `--warning` · `--info` · `--ok` 는 담지 않는다 — 저장이 **성공**해도 서는 안내다
    // (통화 미지정 경고 · "이 날짜에 아직 가격이 없습니다" · "저장했습니다").
    // 훑는 자리는 좁힌 범위 + **지금 열린 드로어·모달**이다. 배너는 좁힌 행의 형제라
    // (오류 배너도 제 `<tr>` 이다) 행으로 좁히면 안 보이고, 반대로 탭 화면 전체를 훑으면
    // 앞 단계가 남긴 패널 배너까지 이번 저장의 오류로 읽힌다. 드로어·모달은 요청마다 통째로
    // 다시 그려지므로 그 안의 배너는 언제나 이번 응답의 것이다.
    // 배경(드로어·모달 **밖**)에서는 **카드 안에 든 띠를 담지 않는다** — 그것은 이번 저장의
    // 응답이 아니라 목록 한 칸의 **빈 상태 안내문**이다. ERP 는 두 가지를 같은 클래스로
    // 그린다(`--blocking` 은 색이지 뜻이 아니다): 저장 거부·전개 불가는 패널 머리에 **한 번**
    // 서고(`_rooms_panel.html` 의 `{{ error_message }}` 등), 빈 상태는 `{% for %}` 안 카드마다
    // 선다(`_rooms_panel.html`: `{% if not group.rooms %}` → "이 오퍼에 연결된 객실이
    // 없습니다 — …"). 룸을 오퍼 A 에 붙이면 오퍼 B 카드의 그 안내문이 화면에 그대로 남는데,
    // 종전에는 그것이 이번 저장의 오류로 실려 `룸 만들기`·`판매 연결` 이 매번 `stepFailed`
    // 참이 됐다(2026-09-10 운영 실행에서 5회). 저장은 정상이었다.
    // 드로어·모달 **안**의 카드 띠는 그대로 담는다 — 그 조각은 요청마다 다시 그려지므로
    // 카드 안이든 밖이든 이번 응답의 글자다(가격 셀 편집 모달은 오류를 행 단위로 그린다).
    var dRoot = drawerRoot(), mRoot = modalRoot();
    var inOverlay = function (e) { return !!((dRoot && dRoot.contains(e)) || (mRoot && mRoot.contains(e))); };
    var banners = [root, mRoot, dRoot].filter(Boolean);
    banners.forEach(function (box, i) {
      if (banners.indexOf(box) !== i) return;
      [].slice.call(box.querySelectorAll('.stay-banner--blocking')).forEach(function (e) {
        if (e.closest('#stay_validation_banner')) return; // 검증 배너는 `state().banner` 가 따로 읽는다
        if (!inOverlay(e) && e.closest('.stay-card')) { note(e); return; }
        if (shown(e)) push(textOf(e));
      });
    });
    // 안내 띠(토스트)는 여기서 담지 않는다 — 저장이 **성공**할 때도 뜨기 때문이다
    // ("저장되었습니다."). 종전에는 그것이 `errors` 에 들어가 드로어 저장마다 오류가 난 것처럼
    // 보였다(2026-09-04 운영 실행에서 확인). 띠 글자는 `submit` 이 `toast` 로 따로 돌려주고,
    // **실패로 읽히는 글자일 때만** `errors` 에 얹는다(`failToast`).
    return out;
  }

  // 안내 띠가 실패를 말하는가. 성공 문구("저장되었습니다." · "3장을 추가했습니다.")를 오류로
  // 세지 않는 것이 목적이라, **실패로 읽히는 말이 있을 때만** 참이다. 새로운 실패 문구를
  // 놓치더라도 저장 결과(`stayed`)와 폼 오류가 따로 알려 준다 — SKILL.md 의
  // "`stayed` 인데 `errors` 가 비어 있으면 화면을 눈으로 확인한다" 가 그 자리다.
  var FAIL_TOAST_RE = /실패|오류|에러|잘못|불가|권한|없습니다|할\s*수\s*없|다시\s*시도|초과|거부/;
  function failToast(t) { return !!t && FAIL_TOAST_RE.test(nfc(t)); }

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

  // 마지막으로 `open` 이 연 모달과 그때의 요청 서명. 같은 단계를 다시 부를 때
  // "이미 열려 있다" 를 가리는 데만 쓴다.
  var lastOpen = { key: null, modal: null, within: null };
  function openKey(s) {
    return [s.button || '', s.row || '', s.card || '', s.block || ''].join('|');
  }
  function sameOpener(s) {
    return lastOpen.key === openKey(s) && lastOpen.within === (s.within || null);
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
    // **이 버튼이 연 모달이 아직 열려 있으면 다시 누르지 않는다.** 사진 단계(`대표이미지 올리기`·
    // `상품상세 이미지 올리기`)는 첫 `runStep` 이 모달만 열고 `submitted:false` 로 끝나는 규약이라
    // 같은 단계를 다시 부르는 것이 정상 경로인데, 종전에는 이미 열린 `#content-modal` 을 또 열려다
    // `open: 'timeout'` 으로 끝났다(2026-09-10 운영 실행). 모달이 화면을 덮고 있어 뒤의 버튼을
    // 눌러도 아무 일이 일어나지 않으므로 `waitFor` 가 붙잡을 변화가 없다.
    // 드로어는 이 갈래가 필요 없다 — 다시 누르면 조각이 새로 그려져 `innerHTML` 이 바뀌고,
    // 그 변화를 아래 `waitFor` 가 이미 성공으로 읽는다.
    var openedNow = modalRoot();
    if (openedNow && lastOpen.modal === openedNow && sameOpener(s) && !openedNow.contains(btn)) {
      var stA = readState();
      return remember({
        status: 'already',
        detail: '[' + s.button + '] 이 연 모달이 이미 열려 있어 다시 누르지 않았습니다',
        drawer: stA.drawer, modal: stA.modal, errors: [], fields: fieldsIn()
      });
    }
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
    // 무엇이 이 버튼으로 열렸는지 적어 둔다 — 같은 단계를 다시 부를 때 위 갈래가 이것으로 갈린다.
    lastOpen = ok ? { key: openKey(s), modal: modalRoot(), within: s.within || null } : { key: null, modal: null, within: null };
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
    cands = dropCopySelect(scope, cands, f.kind, name);
    if (!cands.length && (f.kind === 'empty' || f.kind === 'uncheck')) { out.status = 'skipped'; out.detail = '화면에 없는 칸 — 비워 둘 것이 없습니다'; return out; }
    if (!cands.length) {
      out.detail = '`' + name + '` 칸을 찾지 못했습니다 · 화면 칸: ' +
        trunc(fieldsIn().map(function (x) { return x.label; }).filter(Boolean).join(' / '), 300);
      return out;
    }

    var boxes = cands.filter(function (c) { return /^(checkbox|radio)$/.test(c.el.type); }).map(function (c) { return c.el; });
    var values = f.values && f.values.length ? f.values : (f.value !== undefined && f.value !== null && f.value !== '' ? [String(f.value)] : []);

    // 체크·라디오 묶음
    if (groupable(cands, boxes, f.kind)) {
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
    // 2차: 이름으로 못 찾았지만 **앞 칸이 화면을 바꿔 이제 서 있을** 칸을 한 번 더 시도한다.
    // Stay 폼은 앞 칸의 값이 뒤 칸을 세우고 접는다(Alpine `x-show`): 부과금의 [정액 금액]·
    // [연령별 단가] 는 [부과 단위]가 `인당` 이고 [부과 방식]이 `정액` 일 때만, 연령 구간의 [요금 기준 값]·
    // [참조 밴드 코드] 는 [요금 기준 유형]에 따라 선다. 1차에서는 그 칸이 아직 `display:none`
    // 이라 `usable()` 이 거른다 — Alpine 이 한 틱 뒤에 세우므로 잠깐 쉬고 같은 이름으로 다시 찾는다.
    var retry = [];
    for (var m0 = 0; m0 < list.length; m0++) if (res[m0].status === 'not-found') retry.push(m0);
    if (retry.length) {
      await sleep(300);
      scope = narrow(baseScope(), o);
      for (var m1 = 0; m1 < retry.length; m1++) {
        var j1 = retry[m1];
        var again;
        try { again = await applyOne(scope, list[j1], o); }
        catch (e) { again = { label: list[j1].label, kind: list[j1].kind, status: 'error', detail: String(e && e.message || e) }; }
        if (again.status === 'not-found') { delete again._el; continue; }
        again.retried = true;
        els[j1] = again._el || null; delete again._el;
        res[j1] = again;
        await sleep(60);
      }
    }
    // 3차: 그래도 이름으로 못 찾은 칸을 순서로
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

  /* ──────────────────── CSRF 토큰 다시 읽기 (403 재시도용) ────────────────────
     오래 열려 있던 탭에서 저장하면 첫 요청이 **CSRF 403** 으로 거부되는 일이 있다.
     ERP 는 htmx 헤더에 넣을 토큰을 **페이지가 그려질 때 한 번** 박아 둔다
     (`common/templates/common/_htmx.html` 의 `htmx:config:request` 리스너가
     `'{{ csrf_token }}'` 을 그대로 쓴다) — 토큰이 갈리면 그 값은 낡은 채로 남으므로
     같은 버튼을 다시 눌러도 **같은 낡은 토큰**이 나가 또 403 이 난다.
     Django 는 거부 응답에 새 `csrftoken` 쿠키를 실어 주므로, 재시도 전에 그 쿠키(없으면
     화면의 `csrfmiddlewaretoken`)를 읽어 **우리 리스너가 헤더를 덮어쓰게** 해야 통한다.
     403 은 CsrfViewMiddleware 가 뷰를 부르기 **전에** 끊는 것이라 저장이 들어가지 않았다 —
     그래서 이 코드에서만 재시도가 안전하다(다른 4xx·5xx 는 재시도하지 않는다).
     토큰 값 자체는 어디에도 싣지 않는다 — 어디서 읽었는지만 돌려준다. */
  function readCookie(name) {
    var m = (document.cookie || '').match(new RegExp('(?:^|;\\s*)' + name + '=([^;]*)'));
    return m ? decodeURIComponent(m[1]) : '';
  }
  function csrfDomToken() {
    var el = [].slice.call(document.querySelectorAll('input[name=csrfmiddlewaretoken]'))
      .find(function (i) { return i.value; });
    return el ? el.value : '';
  }
  function csrfToken() { return readCookie('csrftoken') || csrfDomToken(); }
  var csrfHooked = false;
  // 우리 리스너는 ERP 것보다 **뒤에** 걸린다(같은 버블 단계라 나중에 건 쪽이 나중에 돈다) —
  // 그래서 페이지에 박힌 낡은 토큰을 덮어쓴다. 매번 쿠키를 다시 읽으므로 한 번 걸어 두면
  // 토큰이 또 갈려도 따라간다.
  function hookCsrfHeader() {
    if (csrfHooked) return false;
    var set = function (e) {
      var tok = csrfToken();
      if (!tok) return;
      var d = (e && e.detail) || {};
      var h = (d.ctx && d.ctx.request && d.ctx.request.headers) || d.headers; // htmx 4 / htmx 1·2
      if (h) h['X-CSRFToken'] = tok;
    };
    document.addEventListener('htmx:config:request', set);  // htmx 4
    document.addEventListener('htmx:configRequest', set);   // htmx 1·2
    csrfHooked = true;
    return true;
  }
  function refreshCsrf() {
    var tok = csrfToken();
    if (!tok) return { ok: false, reason: 'no-token', detail: '페이지에서도 쿠키에서도 CSRF 토큰을 찾지 못했습니다' };
    var from = readCookie('csrftoken') ? 'cookie' : 'dom';
    var n = 0;
    [].slice.call(document.querySelectorAll('input[name=csrfmiddlewaretoken]')).forEach(function (i) {
      if (i.value !== tok) { i.value = tok; n++; }
    });
    var hooked = hookCsrfHeader();
    return { ok: true, from: from, inputs: n, hooked: hooked };  // 토큰 값은 싣지 않는다
  }

  async function submit(buttonText, opts) {
    var o = opts || {};
    var scope = narrow(baseScope(), o);
    var drawerEl = document.querySelector('.stay-drawer.is-open');
    var btn = findButton(scope, buttonText) || (drawerEl && findButton(drawerEl, buttonText)) || findButton(document.body, buttonText, true);
    // 저장 버튼이 아니라 파일 고르개인가 — 그렇다면 **다른 버튼을 대신 찾지 않는다**.
    // `not-found` 로 돌려주면 부르는 쪽이 `저장·추가·…` 대안을 훑다가 드로어의 [저장] 을 누른다.
    if (!btn) {
      var up = uploadLabel(scope, buttonText);
      if (up) return remember({
        status: 'upload-label', reason: 'upload-label',
        detail: '[' + buttonText + '] 는 저장 버튼이 아니라 파일 고르개입니다 — stayRun.takeFiles({label:"' + clean(labelOwnText(up)) + '"}) 로 올립니다. 이 화면에는 누를 저장 버튼이 없습니다.',
        errors: [], url: location.href
      });
    }
    if (!btn) return remember({ status: 'not-found', detail: '버튼 [' + buttonText + '] 을 찾지 못했습니다', buttons: buttonsIn(scope), url: location.href, errors: [] });
    var no = refusal(btn, buttonText);
    if (no && (no.reason === 'sale-start' || !o.force)) return remember({ status: 'refused', reason: no.reason, detail: no.detail, errors: [], url: location.href });

    var before = { drawer: !!drawerRoot(), modal: !!modalRoot(), url: location.href, path: location.pathname, settles: hx.settles, swaps: hx.swaps };
    hx.error = null; hx.errorStatus = null;
    var origConfirm = null;
    // 옛 ERP(2026-09-08 이전)는 `hx-confirm` 을 브라우저 네이티브 confirm 으로 띄운다 —
    // 그때는 이 교체가 대신 [확인] 을 누른다. 새 ERP 는 페이지 안 확인창(`#stay_confirm`)을
    // 띄우므로 **이 교체는 쓰이지 않고** 아래 확인창 처리가 [확인] 을 누른다.
    // 두 판 모두에서 force 가 통하도록 둘 다 남겨 둔다.
    if (o.force) { origConfirm = window.confirm; window.confirm = function () { return true; }; }
    try { btn.click(); } finally {
      if (origConfirm) { window.confirm = origConfirm; }
    }

    var confirmText = null;
    if (o.force) {
      // 페이지 안 확인창이 뜨는지 최대 2초 지켜본다. 옛 ERP 처럼 확인창 없이 곧장 요청이
      // 나갔으면 기다리지 않고 빠져나온다.
      var tc = Date.now(), cOpen = false;
      while (Date.now() - tc < 2000) {
        if (confirmRoot()) { cOpen = true; break; }
        if (hx.pending > 0 || hx.settles > before.settles || hx.swaps > before.swaps ||
          hx.unloading || location.pathname !== before.path) break;
        await sleep(TICK);
      }
      if (cOpen) {
        var cs = confirmState();
        confirmText = cs ? cs.text : '';
        var okBtn = confirmButton('ok');
        if (okBtn) okBtn.click();
        await waitFor(function () { return !confirmRoot(); }, 3000);
      }
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

    // ── CSRF 403 이면 **딱 한 번** 다시 보낸다 ────────────────────────────────
    // 403 은 CsrfViewMiddleware 가 뷰를 부르기 전에 끊은 것이라 **저장이 들어가지 않았다** —
    // 그래서 같은 값을 두 번 만들 걱정이 없다. 다른 4xx·5xx 는 재시도하지 않는다.
    // 그냥 다시 누르면 페이지에 박힌 낡은 토큰이 또 나가므로, 먼저 `refreshCsrf()` 로
    // 새 토큰을 읽어 헤더를 덮어쓸 리스너를 걸어 둔다(위 주석).
    if (hx.error && hx.errorStatus === 403 && status !== 'navigated' && !hx.unloading &&
        !o.__csrfRetried && o.csrfRetry !== false) {
      // 대기 고리는 `hx.error` 를 보는 순간 끊는다 — 거부된 요청의 `finally:request` 가
      // 아직 안 왔을 수 있다. 그대로 다시 보내면 `pending` 이 0 으로 안 떨어져 재시도가
      // 통째로 `timeout` 이 된다. 잠깐 비는 것을 보고 간다.
      await waitFor(function () { return hx.pending === 0; }, 2000);
      var fix = refreshCsrf();
      hx.error = null; hx.errorStatus = null;
      var o2 = {}; for (var ok2 in o) if (Object.prototype.hasOwnProperty.call(o, ok2)) o2[ok2] = o[ok2];
      o2.__csrfRetried = true;
      var again = await submit(buttonText, o2);
      again.csrfRefresh = fix;
      // 두 번째도 403 이면 `error` 그대로 멈춘다 — 세 번은 없다.
      if (again.status === 'error') again.csrfRetryFailed = true;
      else again.csrfRetried = true;
      return remember(again);
    }

    var st = readState();
    var after = narrow(baseScope(), o);
    var errors = collectErrors(after);
    // 안내 띠는 실패로 읽힐 때만 오류로 센다 — 성공 띠("저장되었습니다.")는 `toast` 로만 간다
    if (failToast(st.toast) && errors.indexOf(clean(st.toast)) < 0) errors.push(trunc(clean(st.toast), 200));
    if (hx.error) errors.unshift(hx.error);
    var out = { status: status, errors: errors, toast: st.toast, url: st.url, banner: st.banner };
    // 오류로 세지 않고 넘긴 배경 안내문(빈 상태 카드 등) — 있으면 참고로만 싣는다
    if (pageNotes.length) out.pageNotes = pageNotes.slice();
    // 페이지 안 확인창이 떠서 러너가 [확인] 을 대신 눌렀으면 그 문구를 돌려준다.
    if (confirmText !== null) out.confirmText = confirmText;
    if (st.confirm) out.confirm = st.confirm;
    if (st.loginPage) out.status = 'login';
    // 요청 자체가 거부되거나 끝나지 못했으면 **저장은 안 된 것**이다 — 드로어가 우연히
    // 닫혔더라도 `closed`(성공)로 읽으면 안 된다. ERP 는 `noSwap` 이라 500·403 에서 화면이
    // 그대로 남으므로, 이 갈래가 없으면 거부가 아무 표시 없이 지나간다.
    else if (hx.error) out.status = 'error';
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
    if (!cands.length && target !== scope) cands = findControls(scope, name);
    if (!cands.length && /^(multi|select|check|uncheck|empty)$/.test(f.kind)) cands = groupBoxes(scope, name);
    // 두 조각 이름(`연령별 단가 · 초등학생` · `제공 주기 · 1박당 제공 (…)`)은 뒤 조각이 화면 라벨이다.
    // 채울 때(`applyOne`)는 이 갈래가 있었는데 되읽기에는 없어서, 그런 칸은 **늘** 어긋난 것으로
    // 보고됐다(SKILL.md 가 "되읽기의 한계" 로 적어 둔 것이 이것이다). 같은 규칙을 여기에도 둔다.
    if (!cands.length && /[·・‧∙]/.test(name)) {
      var tparts = name.split(/\s+[·・‧∙]\s+/).filter(Boolean), tailName = tparts[tparts.length - 1];
      var tc = rep ? findInRow(target, tailName, f.kind) : findControls(target, tailName);
      if (!tc.length && target !== scope) tc = findControls(scope, tailName);
      if (!tc.length && /^(multi|select|check|uncheck|empty)$/.test(f.kind)) tc = groupBoxes(scope, tailName);
      // 글자 값을 체크 칸에서 읽지 않는다 — `오퍼별 표시명 · Single` 의 뒤 조각은 룸 체크박스 글자와 같다
      if (tc.length && /^(typed|file)$/.test(f.kind) && tc.every(function (c) { return /^(checkbox|radio)$/.test(c.el.type); })) tc = [];
      if (tc.length) { cands = tc; name = tailName; }
    }
    cands = dropCopySelect(scope, cands, f.kind, name);   // `다른 룸에서 복사…` 는 되읽기에서도 칸이 아니다
    // **비움 지시 + 칸 없음 = 만족**이다. 화면이 그 칸을 아예 세우지 않는 경우가 있고
    // (부과금의 `적용 날짜 (선택)` 은 부과 유형이 `선택` 이면 서지 않는다), 지시가 "비워 둔다"
    // 이면 없는 칸은 이미 비어 있는 것이다. 종전에는 `same:false` 라 믿을 수 있는 칸(날짜)이면
    // `mismatch` 로 저장 앞에서 멈췄다 — 2026-09-10 운영 실행에서 부과금 4단계가 이것으로 막혔다.
    // 값 지시(`typed`·`select`·`check`…) + 칸 없음은 그대로 불일치다 — 넣어야 할 값이
    // 갈 자리가 없다는 뜻이라 사람이 봐야 한다.
    if (!cands.length && f.kind === 'empty') { out.actual = '(칸 없음)'; out.absent = true; out.same = true; return out; }
    if (!cands.length) { out.actual = '(칸 없음)'; out.same = false; return out; }
    var boxes = cands.filter(function (c) { return /^(checkbox|radio)$/.test(c.el.type); }).map(function (c) { return c.el; });
    var values = f.values && f.values.length ? f.values : (f.value !== undefined && f.value !== null && f.value !== '' ? [String(f.value)] : []);

    if (groupable(cands, boxes, f.kind)) {
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
      // 비움 지시라 "칸 없음" 을 이미 만족으로 매듭지은 칸은 순서로 다시 찾지 않는다 —
      // 순서 짐작이 엉뚱한 칸을 집으면 멀쩡한 단계가 다시 불일치가 된다.
      if (res[k].absent) continue;
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
    // 페이지 안 확인창이 떠 있으면 먼저 [취소] 로 닫는다 — 그 위에서는 모달/드로어를 못 닫는다.
    if (confirmRoot()) {
      var cx = confirmButton('cancel');
      if (cx) cx.click(); else pressEsc();
      await waitFor(function () { return !confirmRoot(); }, 3000);
    }
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
    // 손으로 닫았으면 "이 버튼이 연 모달" 기억도 지운다 — 다음 `open` 은 다시 눌러야 한다.
    if (!modalRoot()) lastOpen = { key: null, modal: null, within: null };
    return remember({ drawer: !!drawerRoot(), modal: !!modalRoot(), confirm: confirmState() });
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
    // 파일을 고르는 것만으로 올라가는 칸인가 — 룸 사진 칸이 그렇다(`hx-trigger="change"` 가 붙어
    // 고르는 즉시 올라간다). 그런 칸은 뒤에 [저장] 을 누르면 안 된다.
    var auto = /(^|[\s,])change([\s,]|$)/.test(target.getAttribute('hx-trigger') || '');
    var swaps0 = hx.swaps, settles0 = hx.settles;
    target.files = dt.files;
    fire(target, ['input', 'change']);
    // 화면이 파일을 읽어 미리보기를 만들 시간을 준다(이미지 모달은 이걸 기다리지 않으면 "등록해주세요" 가 뜬다)
    await sleep(spec.wait === undefined ? 900 : spec.wait);
    var out = { status: 'ok', moved: moved, target: target.name || target.id || '(file)', targetMultiple: !!target.multiple, autoUpload: auto };
    if (auto) {
      // 올리는 요청이 끝날 때까지 기다린다 — 끝나면 목록이 제자리에서 갈린다(패널 outerHTML 스왑)
      out.uploaded = await waitFor(function () { return hx.pending === 0 && (hx.swaps > swaps0 || hx.settles > settles0); }, spec.uploadWait === undefined ? 20000 : spec.uploadWait);
      out.errors = hx.error ? [hx.error] : [];
      out.toast = toastText();
    }
    return remember(out);
  }
  function clearBridge() { var el = document.getElementById('stay_file_bridge'); if (el) el.value = ''; return remember({ ok: true }); }

  /* ────────────────── 페이지 머리의 [저장] — 전체 화면 폼 저장 ──────────────────
     기본정보 탭의 이미지 모달(`#content-modal`)은 헤더 [저장] 으로 **이미지 행만**
     만든다(`contents_imagecontent`). 호텔과의 연결(`fit_masterimages`)은 그 뒤에
     **기본정보 폼 전체가 저장될 때** 생긴다 — ERP `fit/views/master.py` 의
     `after_save_model` 이 폼이 실어 보낸 `main_image_sort`·`image_sort` 를 읽어
     `MasterImages` 를 bulk_create 한다. 모달만 저장하고 끝내면 화면에는 사진이
     보이는데 DB 에는 연결이 0행이라 고객 화면에 "사진 준비 중" 이 뜬다
     (2026-09-10 운영 호텔 44000 실측).

     그 저장 버튼은 드로어·모달 **밖**, 페이지 우상단 머리(`.right_header`)의 `#save` 다
     (`fit/templates/fit/master_form.html`). 누르면 htmx 가 아니라 **ajax POST** 가
     나가고(새 화면으로 넘어가지 않는다) 성공하면 Materialize 안내 띠가 뜬다 —
     그래서 `submit()` 의 htmx 기다림으로는 정착을 못 본다. 여기서는 띠가 새로 뜨는
     것과 화면이 넘어가는 것 둘 다 본다. 필수 칸이 비어 있으면 ERP 는 요청을 아예
     보내지 않고 칸에 `.not-valid` 만 붙인다 — 그것도 갈라 읽는다. */
  function pageSaveButton() {
    var inOver = function (el) {
      return !!(el.closest('.stay-drawer') || el.closest('.modal') || el.closest('.stay-modal') ||
        el.closest('#' + CONFIRM_ID) || el.closest('#logout-warning-modal'));
    };
    var cands = [].slice.call(document.querySelectorAll('#save, .right_header button, .right_header a.btn'));
    for (var i = 0; i < cands.length; i++) {
      var b = cands[i];
      if (!b || b.disabled || b.getAttribute('aria-disabled') === 'true' || !shown(b) || inOver(b)) continue;
      if (b.id === 'save') return b;                       // 페이지 머리의 저장 버튼(ERP 공통 id)
      if (tier(btnText(b), '저장') >= 3) return b;          // id 가 다른 화면 대비
    }
    return null;
  }
  // 필수 칸 미입력 표시(`.not-valid`) — ERP 는 이걸 붙이고 요청을 보내지 않는다
  function invalidFields() {
    return [].slice.call(document.querySelectorAll('.not-valid')).filter(shown).slice(0, 12).map(function (el) {
      var lab = labelsOf(el).map(function (c) { return c.text; })[0];
      return clean(lab || el.getAttribute('name') || el.id || textOf(el)).slice(0, 60) || '(이름 없는 칸)';
    });
  }
  async function pageSave(opts) {
    var o = opts || {};
    var btn = pageSaveButton();
    if (!btn) return remember({
      status: 'not-found', saved: false, errors: [],
      detail: '페이지 우상단의 [저장] 버튼이 없습니다 — 기본정보 같은 전체 화면 폼에서만 있습니다',
      url: location.href
    });
    // 모달·드로어가 열린 채로 폼을 저장하면 아직 화면에 안 붙은 값이 빠진 채 굳는다.
    // 이미지 단계라면 **먼저 모달 헤더 [저장]** 으로 사진을 화면에 붙여야 한다.
    var mOpen = !!modalRoot(), dOpen = !!drawerRoot();
    if (!o.force && (mOpen || dOpen)) return remember({
      status: 'blocked', saved: false, reason: mOpen ? 'modal' : 'drawer', errors: [],
      detail: (mOpen ? '모달' : '드로어') + '이 아직 열려 있습니다 — 그 안의 [저장] 으로 닫은 뒤에 부르세요'
        + ' (정말 지금 저장해야 하면 `stayRun.pageSave({force:true})`)',
      url: location.href
    });

    var before = {
      url: location.href, path: location.pathname,
      settles: hx.settles, swaps: hx.swaps, toast: toastText()
    };
    hx.error = null; hx.errorStatus = null;
    btn.click();

    var status = 'timeout', t0 = Date.now();
    while (Date.now() - t0 < WAIT_MS) {
      await sleep(TICK);
      if (hx.unloading || location.pathname !== before.path) { status = 'navigated'; break; }
      if (hx.error) { status = 'error'; break; }
      // ajax 저장은 안내 띠로만 끝을 알린다("저장되었습니다.")
      var tNow = toastText();
      if (tNow && tNow !== before.toast) { await sleep(200); status = 'settled'; break; }
      // htmx 로 저장하는 화면(Stay 쪽 전체 화면 폼)도 있으니 그 신호도 같이 본다
      if (hx.pending === 0 && (hx.settles > before.settles || hx.swaps > before.swaps)) { await sleep(250); status = 'settled'; break; }
      // 필수 칸이 비어 있으면 요청 자체가 안 나간다 — 표시가 붙는 즉시 끊는다
      if (invalidFields().length) { status = 'invalid'; break; }
    }

    var st = readState();
    var errors = collectErrors(baseScope());
    if (failToast(st.toast) && errors.indexOf(clean(st.toast)) < 0) errors.push(trunc(clean(st.toast), 200));
    if (hx.error) { errors.unshift(hx.error); status = 'error'; }
    var bad = invalidFields();
    if (bad.length && status !== 'navigated') status = 'invalid';
    var out = {
      status: status,
      saved: (status === 'navigated' || status === 'settled') && !errors.length,
      errors: errors, toast: st.toast, url: st.url, banner: st.banner
    };
    if (bad.length) {
      out.invalid = bad;
      out.detail = '필수 칸이 비어 저장 요청이 나가지 않았습니다: ' + bad.join(' · ');
    }
    if (status === 'timeout') out.detail = '저장이 끝난 표시(안내 띠·화면 갈림)를 못 봤습니다 — 스크린샷으로 확인하세요';
    if (st.loginPage) out.status = 'login';
    return remember(out);
  }

  function keepAlive() {
    var lw = document.getElementById('logout-warning-modal');
    if (!lw || !shown(lw)) return remember({ clicked: false, logoutWarning: false });
    var b = findButton(lw, '확인');
    if (b) b.click();
    return remember({ clicked: !!b, logoutWarning: shown(lw) });
  }

  /* ─────────────────────────── 진행 표시 띠 ─────────────────────────── */
  // 화면 오른쪽 위에 늘 떠 있는 한 줄이다. 지켜보는 사람이 콘솔을 열지 않고도 몇 번째 단계인지,
  // 무엇이 실패했는지 본다. 화면 조각이 통째로 갈려도(htmx) 다시 붙는다.
  // 상태는 `window.__stayProgress` 에 둔다 — 도우미를 다시 주입해도 띠도 감시자도 하나뿐이다.

  var PROG_ID = 'stay_progress';
  var PROG_COLOR = {
    running: { bg: '#1F7A3D', fg: '#FFFFFF' },
    failed: { bg: '#B3261E', fg: '#FFFFFF' },
    done: { bg: '#5E6E82', fg: '#FFFFFF' },
    idle: { bg: '#5E6E82', fg: '#FFFFFF' }
  };

  function progStore() {
    var s = window.__stayProgress;
    if (!s) {
      s = window.__stayProgress = {
        state: { total: 0, done: 0, skipped: 0, failed: 0, current: '', note: '', status: 'idle', startedAt: null, updatedAt: null },
        hidden: false, observer: null, fixing: false
      };
    }
    return s;
  }
  // 기록으로 남기기 좋게 JSON 으로 바꿀 수 있는 평범한 객체로 베껴 준다
  function progCopy(st) {
    return {
      total: st.total, done: st.done, skipped: st.skipped, failed: st.failed,
      current: st.current, note: st.note, status: st.status,
      startedAt: st.startedAt, updatedAt: st.updatedAt
    };
  }

  function progText(st) {
    var processed = st.done + st.skipped + st.failed;
    var t = st.total > 0 ? processed + ' / ' + st.total : processed + ' 단계';
    if (st.status === 'done') t = '끝 · ' + t;               // 끝났으면 `지금:` 은 적지 않는다
    else if (st.current) t += ' · 지금: ' + trunc(st.current, 48);
    t += ' · 완료 ' + st.done;
    if (st.skipped > 0) t += ' · 건너뜀 ' + st.skipped;
    if (st.failed > 0) t += ' · 실패 ' + st.failed;
    if (st.note) t += ' · ' + st.note;
    return t;
  }

  // 띠 요소. 없거나 화면에서 떨어져 나갔으면 다시 만들어 붙인다.
  function progEl() {
    var el = document.getElementById(PROG_ID);
    if (el && el.isConnected) return el;
    if (el && el.parentNode) el.parentNode.removeChild(el);
    el = document.createElement('div');
    el.id = PROG_ID;
    // 색은 하나도 빼지 않고 적는다 — ERP 화면의 제 색이 배어들면 글자가 안 보인다.
    // 겹 차례는 파일 다리(2147483647)보다 하나 아래고, 눌림은 통과시킨다(검증 배너·드로어를 가리지 않는다).
    el.style.cssText = 'position:fixed;top:6px;right:6px;z-index:2147483646;pointer-events:none;' +
      'max-width:min(46vw,560px);padding:4px 10px;border-radius:6px;border:0;' +
      'font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;' +
      'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;box-shadow:0 1px 5px rgba(0,0,0,0.28);' +
      'background:#5E6E82;color:#FFFFFF;';
    var txt = document.createElement('span');
    txt.id = 'stay_progress_text';
    el.appendChild(txt);
    var x = document.createElement('button');
    x.type = 'button';
    x.id = 'stay_progress_close';
    x.textContent = '✕';
    x.setAttribute('aria-label', '진행 표시 닫기');
    x.setAttribute('title', '진행 표시 닫기');
    x.style.cssText = 'pointer-events:auto;background:transparent;color:inherit;border:0;' +
      'margin-left:8px;padding:0 2px;font:inherit;line-height:1;cursor:pointer;';
    x.addEventListener('click', function () { progressHide(); });
    el.appendChild(x);
    document.body.appendChild(el);
    return el;
  }

  function progRender(store) {
    if (store.hidden || !document.body) return;
    store.fixing = true;
    try {
      var el = progEl(), st = store.state;
      var c = PROG_COLOR[st.status] || PROG_COLOR.idle;
      el.style.background = c.bg;
      el.style.color = c.fg;
      var txt = el.querySelector('#stay_progress_text') || el;
      txt.textContent = progText(st); // 상태 글자는 절대 innerHTML 로 넣지 않는다
    } finally {
      store.fixing = false;
    }
  }

  // ERP 는 화면 조각을 통째로 갈아 끼운다(htmx). 띠가 사라지면 다시 붙인다 — 한 번만 단다.
  function progObserve(store) {
    if (store.observer || typeof MutationObserver !== 'function' || !document.body) return;
    try {
      store.observer = new MutationObserver(function () {
        if (store.fixing || store.hidden) return;         // 다시 붙이는 동안의 되돌이를 막는다
        var el = document.getElementById(PROG_ID);
        if (el && el.isConnected) return;
        try { progRender(store); } catch (e) { /* 그리기가 막혀도 실행은 계속한다 */ }
      });
      store.observer.observe(document.body, { childList: true });
    } catch (e) { store.observer = null; }
  }

  // stayRun.progress({done, total, current, skipped, failed, note, status})
  // 준 값만 덮고 나머지는 그대로 둔다. 인자 없이 부르면 다시 그리기만 한다. 절대 예외를 던지지 않는다.
  function progress(patch) {
    var store = progStore(), st = store.state;
    try {
      if (patch && typeof patch === 'object') {
        var changed = false, seed = false;
        ['total', 'done', 'skipped', 'failed'].forEach(function (k) {
          if (!(k in patch) || patch[k] === null || patch[k] === undefined) return;
          var v = parseInt(patch[k], 10);
          if (isNaN(v) || v < 0) return;
          if (k === 'total' || k === 'done') seed = true;
          if (st[k] !== v) { st[k] = v; changed = true; }
        });
        ['current', 'note'].forEach(function (k) {
          if (!(k in patch) || patch[k] === null || patch[k] === undefined) return;
          if (k === 'current') seed = true;
          var v = clean(patch[k]);
          if (st[k] !== v) { st[k] = v; changed = true; }
        });
        if (seed && !st.startedAt) { st.startedAt = new Date().toISOString(); changed = true; }
        // 상태는 따로 주지 않으면 숫자에서 뽑는다
        var next = patch.status ? String(patch.status)
          : st.failed > 0 ? 'failed'
          : (st.total > 0 && st.done + st.skipped + st.failed >= st.total) ? 'done'
          : (st.startedAt || st.current || st.done + st.skipped + st.failed > 0) ? 'running'
          : 'idle';
        if (st.status !== next) { st.status = next; changed = true; }
        if (changed) st.updatedAt = new Date().toISOString();
      }
    } catch (e) { /* 값이 이상해도 실행을 막지 않는다 */ }
    try { progObserve(store); progRender(store); } catch (e) { /* 그리기 실패는 삼킨다 */ }
    return progCopy(st);
  }
  function progressState() { return progCopy(progStore().state); }
  // ✕ 를 누르면 여기로 온다 — 지운 뒤에는 다시 부르더라도 붙이지 않는다
  function progressHide() {
    var store = progStore();
    store.hidden = true;
    try {
      var el = document.getElementById(PROG_ID);
      if (el && el.parentNode) el.parentNode.removeChild(el);
    } catch (e) { /* 무시 */ }
    return progCopy(store.state);
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
    progress: progress,
    progressState: progressState,
    progressHide: progressHide,
    bridge: bridge,
    takeFiles: takeFiles,
    clearBridge: clearBridge,
    pageSave: pageSave,
    refreshCsrf: refreshCsrf,
    pageSaveButton: pageSaveButton,
    sleep: sleep, waitFor: waitFor, tier: tier, findButton: findButton,
    // 부트(`stay_boot.js`)의 가격 셀 단계가 같은 격자를 쓴다 — 두 벌이 되면 한쪽만 고쳐진다.
    rowCells: rowCells
  };

  window.stayRun = api;
  return { ok: true, version: VERSION, state: readState() };
})();
