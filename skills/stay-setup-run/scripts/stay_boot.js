/* stay_boot.js — 페이지 안 실행 묶음 (stay_helper.js 위에 얹는다)
 * localStorage.staySteps 에 올려 둔 steps.json 을 읽어 window.step / stepFields / runStep 을 만든다.
 * 값은 절대 손으로 옮겨 적지 않는다 — steps.json 그대로 읽어 채운다.
 */
(function () {
  'use strict';
  var d = JSON.parse(localStorage.getItem('staySteps') || '{"steps":[]}');
  window.__steps = d;

  window.step = function (n) { return d.steps.find(function (x) { return x.no === n; }); };

  window.stepFields = function (n) {
    var s = window.step(n);
    var f = s.fields.map(function (x) { return { label: x.label, kind: x.kind, value: x.value, values: x.values }; });
    return f.concat((s.longtexts || []).map(function (l) { return { label: l.label, kind: 'typed', value: l.text }; }));
  };

  // 만들기 단계의 "이름" 칸 — 목록에 같은 이름이 이미 있으면 그 단계를 건너뛴다(공용 정책 포함)
  window.nameOf = function (s) {
    var keys = ['정책명', '룸 이름', '시즌명', '관리용 이름', '프로모션명', '혜택 이름', '이름', '그룹 이름', '요금제명'];
    for (var i = 0; i < keys.length; i++) {
      var f = s.fields.find(function (x) { return x.label === keys[i] && x.kind === 'typed' && x.value; });
      if (f) return f.value;
    }
    return null;
  };

  window.existsInList = function (name, card, mustContain) {
    if (!name) return false;
    var pane = document.getElementById((location.hash || '').slice(1)) || document.body;
    var norm = function (t) { return String(t || '').normalize('NFC').replace(/\s+/g, ' ').trim(); };
    // 카드(오퍼)가 있으면 그 카드 안에서만 본다 — 같은 이름이 다른 오퍼에 있어도 이 오퍼에는 새로 만든다
    var scope = pane;
    if (card) {
      var hit = Array.from(pane.querySelectorAll('.stay-card')).find(function (c) { var h = c.querySelector('.stay-card__head,.stay-card__title'); return h && stayRun.tier(norm(h.textContent).split('#')[0], card) >= 2; });
      if (hit) scope = hit;
    }
    var rows = Array.from(scope.querySelectorAll('tbody tr, .stay-card, li')).filter(function (r) { return r.querySelector && !r.closest('.stay-drawer'); });
    // 오퍼 칸이 있는 단계면 같은 오퍼가 적힌 항목만 "이미 있음"으로 본다 (부가옵션처럼 카드가 오퍼별이 아닐 때)
    if (mustContain) rows = rows.filter(function (r) { return norm(r.innerText).indexOf(norm(mustContain)) >= 0; });
    var esc = norm(name).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return rows.some(function (r) {
      var t = norm(r.innerText);
      return t.indexOf(norm(name)) === 0 || t.split(/\s{2,}|\n/)[0] === norm(name) || new RegExp('(^|\\s)' + esc + '(\\s|$)').test(t);
    });
  };

  // 제목 "(3번째, QUOTATION 2026-2027 · 씨뷰 빌라)" 에서 실제 이름을 뽑는다 — 화면에서 이미 이름이 바뀐 행을 찾을 때 쓴다
  window.titleHint = function (s) {
    // `(1번째, CONTRACT RATE 2026 · 디럭스 (킹/트윈))` 처럼 안에 괄호가 있어도 마지막 닫는 괄호까지 읽는다
    var m = String(s.title || '').normalize('NFC').match(/\(\s*\d+\s*(?:번째|회차|개)?\s*,\s*(.+)\)\s*$/);
    return m ? m[1].trim() : null;
  };

  // 가격 캘린더의 날짜 칸 편집 — 오퍼 줄 고르기 → 룸 줄 고르기 → 달 이동 → 날짜 칸 클릭 → 인원 조합 행의 칸 채우기 → 그 행의 [저장]
  window.runCellStep = async function (n, opt) {
    opt = opt || {};
    var s = window.step(n), out = { no: n, title: s.title, kind: s.kind };
    var sleep = stayRun.sleep, waitFor = stayRun.waitFor, tier = stayRun.tier, hx = window.__stayRunHtmx;
    var nfc = function (t) { return String(t || '').normalize('NFC'); };
    var clean = function (t) { return nfc(t).replace(/\s+/g, ' ').trim(); };
    if (s.head.tab) { var t = await stayRun.tab(s.head.tab); out.tab = t.status; }
    var pane = document.getElementById((location.hash || '').slice(1)) || document.body;
    var date = (nfc(s.title).match(/(\d{4}-\d{2}-\d{2})/) || [])[1];
    var raw = nfc(s.head.card || '');
    // `오퍼 · 룸 × 요금제 의 인원 조합 N 행` — 곱셈 기호는 앞뒤에 빈칸이 있는 × (또는 x) 만 인정한다 (Deluxe 의 x 는 아님)
    // `… × 요금제 의 인원 조합 N 행` · `… × 요금제 의 인원 무관 단일가 행` · `… × 요금제 행`(인원 구분 없음) 세 꼴
    var m = raw.match(/^(.*)\s+[×xX]\s+(.*?)\s*(?:의\s*(?:인원\s*조합\s*(\S+)|인원\s*무관\s*단일가))?\s*행\s*$/);
    // 네 번째 꼴: `오퍼 의 표시명 × 요금제` (행 낱말 없음, 인원 구분 없음 → 무관)
    var m2 = !m && raw.match(/^(.*?)\s+의\s+(.*?)\s+[×xX]\s+(.*?)\s*$/);
    if (m2) m = [m2[0], m2[1] + ' · ' + m2[2], m2[3], null];
    // 다섯 번째 꼴: `오퍼 · 룸 × 요금제 의 인원별 가격 추가` — 기존 행이 없어 새 행 표에 넣는 단계(가격 셀 만들기)
    var m3 = !m && raw.match(/^(.*)\s+[×xX]\s+(.*?)\s+의\s+인원별\s+가격\s+추가\s*$/);
    if (m3) m = [m3[0], m3[1], m3[2], null];
    if (!date || !m) { out.error = '제목의 날짜나 카드의 `오퍼 · 룸 × 요금제 의 인원 조합 N 행` 꼴을 읽지 못했습니다'; return out; }
    var linkName = clean(m[1]), ratePlan = clean(m[2]), occ = m[3] ? clean(m[3]) : '무관'; // `인원 무관 단일가 행` 이면 무관
    if (/^(빈|없음|-)$/.test(occ)) occ = '무관'; // `인원 조합 빈 행` = 인원 무관 행
    var parts = linkName.split(/\s+[·・‧∙]\s+/); var offerName = parts.slice(0, -1).join(' · '), roomName = parts[parts.length - 1];
    out.want = { date: date, offer: offerName, room: roomName, ratePlan: ratePlan, occ: occ };
    // 룸 이름 → 오퍼별 표시명 (객실 탭의 판매 연결 표: 객실 / 룸 이름 / 표시명)
    var display = roomName;
    var linkPane = document.getElementById('stay_tab_room_types');
    if (linkPane) {
      [].slice.call(linkPane.querySelectorAll('.stay-card')).forEach(function (c) {
        var h = c.querySelector('.stay-card__head,.stay-card__title');
        if (!h || tier(clean(h.textContent).split('#')[0], offerName) < 2) return;
        var ths2 = [].slice.call(c.querySelectorAll('thead th')).map(function (h) { return clean(h.textContent); });
        var di = -1; ths2.forEach(function (h, i) { if (di < 0 && h.indexOf('표시명') >= 0) di = i; });
        if (di < 0) di = 1;
        [].slice.call(c.querySelectorAll('tbody tr')).forEach(function (r) {
          var cells = [].slice.call(r.querySelectorAll('td')).map(function (x) { return clean(x.textContent); });
          var first = cells[0] || '';
          if (cells.length > di && (tier(first, roomName) >= 2 || first.indexOf(roomName) >= 0) && cells[di] && !/^[-–]$/.test(cells[di])) display = cells[di];
        });
      });
    }
    out.display = display;
    // 클릭 뒤 화면이 바뀔 때까지: htmx 정착 횟수 또는 화면 내용(길이)이 바뀌면 끝, 최대 ms
    var settled = async function (fn, ms) {
      var sw = hx.settles, sp = hx.swaps, len = pane.innerHTML.length;
      fn();
      await waitFor(function () { return hx.pending === 0 && (hx.settles > sw || hx.swaps > sp || pane.innerHTML.length !== len); }, ms || 6000);
      await sleep(250);
    };
    // 1) 오퍼 줄
    var chips = [].slice.call(pane.querySelectorAll('.stay-offer-btn'));
    var chip = chips.find(function (c) { return tier(clean(c.textContent).split('#')[0], offerName) >= 2; });
    if (chips.length && !chip) { out.error = '오퍼 줄에서 `' + offerName + '` 을 찾지 못했습니다'; return out; }
    if (chip && !/--primary/.test(chip.className)) await settled(function () { chip.click(); });
    // 오퍼가 하나뿐이면 오퍼 줄이 없다 — 그대로 진행
    // 2) 달 이동 (개요 화면은 판매일이 열린 달에만 룸 줄이 보인다 — 먼저 그 달로 간다)
    var monthOf = function () { var h = [].slice.call(pane.querySelectorAll('h1,h2,h3,h4,h5,h6,strong,span,div')).map(function (e) { return clean(e.textContent); }).find(function (x) { return /^\d{4}-\d{2}$/.test(x); }); return h || ''; };
    var target = date.slice(0, 7);
    var goMonth = async function () {
      var guard = 0;
      while (monthOf() !== target && guard++ < 30) {
        var cur = monthOf(); if (!cur) break;
        var dir = cur < target ? '다음 달' : '이전 달';
        var nb = [].slice.call(pane.querySelectorAll('button,a')).find(function (b) { return b.textContent.indexOf(dir) >= 0; });
        if (!nb) break;
        await settled(function () { nb.click(); });
      }
      return monthOf() === target;
    };
    if (!(await goMonth())) { out.error = '달을 ' + target + ' 로 옮기지 못했습니다 (지금 ' + monthOf() + ')'; return out; }
    // 3) 룸 줄 — 개요 화면의 룸 버튼(title: `표시명 · 요금제`) 또는 좌표 화면의 룸 칩. 이미 그 룸의 좌표 화면이면 건너뛴다
    var onCoord = function () { return [].slice.call(pane.querySelectorAll('.stay-coord-group button')).some(function (b) { var tt = clean(b.textContent); return /--primary/.test(b.className) && tier(tt.split(/\s+[·・‧∙]\s+/)[0], display) >= 3 && (!ratePlan || tt.indexOf(ratePlan) >= 0); }); };
    var findRoomBtn = function () {
      return [].slice.call(pane.querySelectorAll('button.stay-ov-row, .stay-coord-group button')).find(function (b) {
        var tt = clean(b.getAttribute('title') || b.textContent), head = tt.split(/\s+[·・‧∙]\s+/)[0];
        return tier(head, display) >= 3 && (!ratePlan || tt.indexOf(ratePlan) >= 0);
      });
    };
    if (!onCoord()) {
      var rb = findRoomBtn();
      if (!rb) { out.error = '룸 줄에서 `' + display + ' · ' + ratePlan + '` 을 찾지 못했습니다 (' + monthOf() + ')'; return out; }
      await settled(function () { rb.click(); });
      // 개요 화면에 머물면 [룸별 입력] 보기로 바꾼다 (룸은 방금 고른 것이 유지된다)
      if (!pane.querySelector('.stay-coord-group button')) {
        var vb = [].slice.call(pane.querySelectorAll('.stay-view-btn, button')).find(function (x) { return /룸별 입력/.test(x.textContent) && !/--primary/.test(x.className); });
        var hasCoord = function () { return !!pane.querySelector('.stay-coord-group button'); };
        for (var vi = 0; vi < 2 && vb && !hasCoord(); vi++) { // 화면 전환이 늦게 끝나기도 해서 칩이 보일 때까지 기다리고 한 번 더 누른다
          await settled(function () { vb.click(); });
          await waitFor(function () { return hx.pending === 0 && hasCoord(); }, 8000);
          vb = [].slice.call(pane.querySelectorAll('.stay-view-btn, button')).find(function (x) { return /룸별 입력/.test(x.textContent) && !/--primary/.test(x.className); });
        }
      }
      // 좌표 화면의 룸 칩이 다른 룸을 가리키면 이 룸 칩을 눌러 바꾼다 (최대 3번)
      for (var ci = 0; ci < 3 && !onCoord(); ci++) {
        var chip2 = [].slice.call(pane.querySelectorAll('.stay-coord-group button')).find(function (x) { var tt = clean(x.textContent); return tier(tt.split(/\s+[·・‧∙]\s+/)[0], display) >= 3 && (!ratePlan || tt.indexOf(ratePlan) >= 0); });
        if (!chip2) break;
        chip2.click();
        await waitFor(function () { return hx.pending === 0 && onCoord(); }, 6000); await sleep(300);
      }
      if (!(await goMonth())) { out.error = '룸 화면에서 달을 ' + target + ' 로 옮기지 못했습니다'; return out; }
      if (!onCoord()) { out.error = '룸별 입력 화면으로 바뀌지 않았습니다'; return out; }
    }
    out.month = monthOf();
    // 4) 날짜 칸
    var day = String(parseInt(date.slice(8, 10), 10));
    var findCell = function () { return [].slice.call(pane.querySelectorAll('button.stay-cal-cell')).find(function (b) { return (clean(b.textContent).match(/^(\d{1,2})\b/) || [])[1] === day; }); };
    var cell = findCell();
    if (!cell) { out.error = date + ' 칸이 눌리는 칸이 아닙니다(판매일이 안 열렸을 수 있음)'; return out; }
    var openCell = async function () {
      var c0 = findCell(); if (!c0) return false;
      await settled(function () { c0.click(); });
      await waitFor(function () { var e0 = document.getElementById('stay_cell_edit'); return e0 && e0.querySelector('table') && hx.pending === 0; }, 6000);
      await sleep(200);
      var e1 = document.getElementById('stay_cell_edit'); return !!(e1 && e1.querySelector('table'));
    };
    if (!(await openCell())) { await sleep(800); await openCell(); } // 화면이 다시 그려져 칸이 바뀌었을 수 있어 한 번 더
    var ed = document.getElementById('stay_cell_edit');
    if (!ed || !ed.querySelector('table')) { out.error = '날짜 칸 편집창이 열리지 않았습니다'; return out; }
    // 5) 인원 조합 행 (기존 행 표 → 없으면 `인원별 가격 추가` 표의 새 행)
    var tables = [].slice.call(ed.querySelectorAll('table')), found = null, isNew = false;
    tables.forEach(function (tb) {
      if (found) return;
      [].slice.call(tb.querySelectorAll('tbody tr')).forEach(function (r) {
        if (found) return;
        var oc = r.querySelector('input[name=occupancy_key]');
        if (!oc) return;
        var v = clean(oc.value);
        if (occ === '무관' ? (v === '' || v === '0' || /무관/.test(clean(r.textContent))) : v === occ) found = { row: r, table: tb };
      });
    });
    // 인원 구분이 없는 카드면 기존 행이 하나뿐일 때 그 행을 쓴다
    if (!found && occ === '무관' && tables.length) { var only = tables[0].querySelectorAll('tbody tr'); if (only.length === 1 && only[0].querySelector('input[name=occupancy_key]')) found = { row: only[0], table: tables[0] }; }
    if (!found && tables.length > 1) { var nr = tables[tables.length - 1].querySelector('tbody tr'); if (nr) { found = { row: nr, table: tables[tables.length - 1] }; isNew = true; } }
    if (!found) { out.error = '인원 조합 ' + occ + ' 행을 찾지 못했습니다'; return out; }
    out.newRow = isNew;
    // 6) 열 제목으로 칸을 찾아 채운다
    var ths = [].slice.call(found.table.querySelectorAll('thead th')).map(function (h) { return clean(h.textContent); });
    var tds = [].slice.call(found.row.children);
    var setNative = function (el, v) { var proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : (el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype); var d = Object.getOwnPropertyDescriptor(proto, 'value'); if (d && d.set) d.set.call(el, v); else el.value = v; ['input', 'change'].forEach(function (ev) { el.dispatchEvent(new Event(ev, { bubbles: true })); }); };
    var results = [];
    window.stepFields(n).forEach(function (f) {
      var ci = -1; ths.forEach(function (h, i) { if (ci < 0 && tier(h, f.label) >= 3) ci = i; });
      var td = ci >= 0 ? tds[ci] : null;
      var el = td ? td.querySelector('input:not([type=hidden]),select,textarea') : null;
      if (f.kind === 'auto') { results.push({ label: f.label, status: 'skipped' }); return; }
      if (!el) { results.push({ label: f.label, status: 'not-found', detail: '열 제목: ' + ths.join(' / ') }); return; }
      if (f.kind === 'empty') { setNative(el, ''); results.push({ label: f.label, status: 'ok' }); return; }
      var val = f.value !== undefined && f.value !== null ? String(f.value) : ((f.values || [])[0] || '');
      if (el.tagName === 'SELECT') {
        var opts = [].slice.call(el.options);
        var o2 = opts.find(function (o) { return tier(o.textContent, val) >= 3; }) || opts.find(function (o) { return tier(o.textContent, val) >= 2; });
        if (!o2) { results.push({ label: f.label, status: 'not-found', detail: '`' + val + '` 옵션 없음' }); return; }
        setNative(el, o2.value); results.push({ label: f.label, status: 'ok', detail: clean(o2.textContent) }); return;
      }
      setNative(el, val); results.push({ label: f.label, status: 'ok', detail: el.value });
    });
    out.fields = results;
    out.bad = results.filter(function (r) { return r.status !== 'ok' && r.status !== 'skipped'; }).map(function (r) { return r.label + ': ' + r.status + ' ' + (r.detail || ''); });
    if (opt.dry || out.bad.length) { out.submitted = false; return out; }
    // 7) 그 행의 [저장]
    // 지시서는 새 행이면 [추가], 기존 행이면 [저장]을 적지만, 화면에 이미 행이 있으면(가격 셀 만들기인데 셀이 이미 있음) 그 행의 [저장]으로 간다
    var rowBtns = [].slice.call(found.row.querySelectorAll('button'));
    var save = rowBtns.find(function (b) { return tier(b.textContent, s.submit || '저장') >= 3; }) || rowBtns.find(function (b) { return tier(b.textContent, isNew ? '추가' : '저장') >= 3; });
    if (!save) { out.error = '행의 [' + (s.submit || '저장') + '] 버튼이 없습니다'; out.submitted = false; return out; }
    out.saveAs = clean(save.textContent);
    hx.error = null;
    await settled(function () { save.click(); }, 10000);
    out.submitted = true; out.submit = hx.error ? 'error' : 'settled'; out.errors = hx.error ? [hx.error] : [];
    var ed2 = document.getElementById('stay_cell_edit');
    out.after = ed2 ? [].slice.call(ed2.querySelectorAll('tbody tr')).map(function (r) { return [].slice.call(r.querySelectorAll('input:not([type=hidden]),select')).map(function (i) { return i.name + '=' + (i.tagName === 'SELECT' ? clean((i.options[i.selectedIndex] || {}).textContent) : i.value); }).join(' '); }).filter(function (x) { return occ === '무관' ? /^occupancy_key=(0)?\s/.test(x) : x.indexOf('occupancy_key=' + occ) === 0; }) : [];
    var closeBtn = ed2 && [].slice.call(ed2.querySelectorAll('button')).find(function (b) { return tier(b.textContent, '닫기') >= 3; });
    if (closeBtn) { closeBtn.click(); await sleep(300); }
    return out;
  };

  // 점검 배너의 경고 넘어가기 — `채우면 좋음` 을 펼치고, 줄 글자가 지시서 패턴(… 은 아무 글자)과 맞는 줄마다 [이건 넘어가기] → 사유 → [넘어가기]
  window.runWarnStep = async function (n, opt) {
    opt = opt || {};
    var s = window.step(n), out = { no: n, title: s.title, kind: s.kind, done: [] };
    var sleep = stayRun.sleep, waitFor = stayRun.waitFor, hx = window.__stayRunHtmx;
    var clean = function (t) { return String(t || '').normalize('NFC').replace(/\s+/g, ' ').trim(); };
    var bp = (s.head.buttons_parsed || []).find(function (x) { return x && x.text && /넘어가기/.test(x.text); }) || (s.head.buttons_parsed || [])[0] || {};
    var pat = clean(bp.row || '');
    if (!pat) { // `노란 목록에서 \`…\` 가 들어간 줄의 [이건 넘어가기]` — 백틱 안 문구가 줄 패턴
      var rawLine = String(bp.raw || (s.head.buttons || [])[0] || ''), bm = rawLine.match(/`([^`]+)`/);
      if (bm) pat = clean(bm[1]);
    }
    if (!pat) { // `경고 넘어가기 (시즌 기간이 겹칩니다)` 처럼 제목 괄호 안 문구가 줄 패턴인 꼴 (번호 없음)
      var tm = String(s.title || '').normalize('NFC').match(/\(([^()]*[가-힣][^()]*)\)\s*$/);
      if (tm && !/^\s*\d+\s*(번째|회차|개)?\s*,/.test(tm[1])) pat = clean(tm[1].replace(/^\d+\s*(번째|회차|개)?\s*,\s*/, ''));
    }
    if (!pat) { out.error = '넘어갈 경고 줄 패턴이 없습니다'; return out; }
    // 패턴의 낱말(빈칸·… 으로 나눔)이 그 순서대로 들어 있으면 맞는 줄로 본다 — `시즌 기간이 겹칩니다` 도 `시즌 'A'과 'B'의 기간이 3일 겹칩니다` 에 맞는다
    // 낱말 끝 조사(에·이·가·을·를…) 앞에도 `.*` 를 허용한다 — `오퍼에 취소정책이 없습니다` 가 `오퍼 'X'에 취소정책이 없습니다` 에 맞도록
    var esc = function (x) { return x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); };
    var re = new RegExp(pat.split(/…|\.\.\.|\s+/).map(function (x) { return x.trim(); }).filter(Boolean).map(function (x) {
      var pm = x.match(/^(.{2,}?)(에서|으로|에|이|가|을|를|은|는|의|와|과|로)$/);
      return pm ? esc(pm[1]) + '.*' + esc(pm[2]) : esc(x);
    }).join('.*'));
    var reason = ((s.fields || []).find(function (f) { return /사유/.test(f.label); }) || {}).value || '';
    var banner = function () { return document.getElementById('stay_validation_banner'); };
    if (!banner()) { out.error = '점검 배너가 없습니다'; return out; }
    var rowOf = function (btn) { var li = btn.closest('li,tr'); if (li && banner().contains(li)) return li; var b = banner(), node = btn.parentElement; while (node && node !== b && node.querySelectorAll('button').length <= 2) node = node.parentElement; return node === b ? btn.parentElement : node; };
    var expand = async function () {
      var b = banner();
      var hidden = [].slice.call(b.querySelectorAll('button')).filter(function (x) { return /이건 넘어가기/.test(x.textContent) && !x.offsetParent; });
      if (!hidden.length) return;
      var tg = [].slice.call(b.querySelectorAll('*')).find(function (e) { return e.children.length <= 3 && /채우면 좋음/.test(e.textContent) && clean(e.textContent).length < 40 && (e.tagName === 'BUTTON' || e.tagName === 'SUMMARY' || e.hasAttribute('@click') || e.hasAttribute('x-on:click') || /pointer/.test(getComputedStyle(e).cursor)); });
      if (tg) { tg.click(); await sleep(300); }
    };
    for (var guard = 0; guard < 8; guard++) {
      await expand();
      var b = banner(); if (!b) break;
      var btn = [].slice.call(b.querySelectorAll('button')).filter(function (x) { return /이건 넘어가기/.test(x.textContent) && x.offsetParent; })
        .find(function (x) { return re.test(clean(rowOf(x).textContent)); });
      if (!btn) break;
      var row = rowOf(btn), rowText = clean(row.textContent).slice(0, 120);
      // 사유 칸이 아직 안 보일 때만 [이건 넘어가기] 를 누른다 (다시 누르면 접힌다)
      var inp = [].slice.call(row.querySelectorAll('input:not([type=hidden]),textarea')).find(function (i) { return i.offsetParent; });
      if (!inp) { btn.click(); await sleep(300); inp = [].slice.call(row.querySelectorAll('input:not([type=hidden]),textarea')).find(function (i) { return i.offsetParent; }); }
      if (inp) { var proto = inp.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype; var d = Object.getOwnPropertyDescriptor(proto, 'value'); d && d.set ? d.set.call(inp, reason) : (inp.value = reason); ['input', 'change'].forEach(function (ev) { inp.dispatchEvent(new Event(ev, { bubbles: true })); }); }
      var go = [].slice.call(row.querySelectorAll('button')).find(function (x) { return clean(x.textContent) === (s.submit || '넘어가기') && x.offsetParent; });
      if (!go) { out.done.push({ row: rowText, error: '[' + (s.submit || '넘어가기') + '] 버튼이 없습니다' }); break; }
      hx.error = null; go.click();
      // 그 줄에 `넘어감` 이 찍히거나 [넘어가기] 가 사라질 때까지 기다린다
      var okRow = await waitFor(function () { var b2 = banner(); if (!b2) return true; var again = [].slice.call(b2.querySelectorAll('li,tr')).find(function (li) { return re.test(clean(li.textContent)) && !/넘어감/.test(li.textContent); }); return hx.pending === 0 && (!again || !again.contains(go) || !go.isConnected); }, 10000);
      await sleep(400);
      out.done.push({ row: rowText, reason: reason, error: hx.error || (okRow ? null : '응답 없음') });
      if (hx.error || !okRow) break;
    }
    out.remaining = stayRun.state().banner;
    if (!out.done.length) out.note = '패턴에 맞는 경고 줄이 없습니다 (이미 넘어갔거나 경고가 없음)';
    return out;
  };

  window.runStep = async function (n, opt) {
    opt = opt || {};
    var s = window.step(n);
    var out = { no: n, title: s.title };
    if (/가격 셀/.test(s.kind || '')) return window.runCellStep(n, opt);
    if (/경고 넘어가기/.test(s.kind || '')) return window.runWarnStep(n, opt);
    if (s.head.tab) { var t = await stayRun.tab(s.head.tab); out.tab = t.status; }

    // 같은 이름이 이미 있으면 만들지 않는다
    if (/만들기|추가/.test(s.kind) && !/고치기|표시명|가격|사진|이미지|넘어가기|판매 연결/.test(s.kind)) {
      var nm = window.nameOf(s);
      var offerF = (s.fields || []).find(function (x) { return x.label === '오퍼' && x.kind === 'select' && x.value; });
      var offerV = offerF ? offerF.value : null;
      if (nm && window.existsInList(nm, s.head.card, offerV)) return { no: n, title: s.title, skipped: true, reason: '이미 있음: ' + nm + (s.head.card || offerV ? ' (' + (s.head.card || offerV) + ')' : '') };
    }

    // 여는 버튼만 고른다 — 드로어 안 버튼과 행 추가류(행/구간/단/요율 행 추가)는 칸을 채우면서 도우미가 누른다
    var bps = (s.head.buttons_parsed || []).filter(function (b) { return b.text && !b.drawer && !/(행|구간|단|포인트)\s*추가$/.test(b.text.trim()); });
    // 버튼 줄이 없고 `화면:` 설명이 `… [호텔 만들기]` 처럼 대괄호 버튼으로 끝나면 그 버튼을 연다
    if (!bps.length && s.head.screen) { var sm = String(s.head.screen).normalize('NFC').match(/\[([^\]]+)\]\s*$/); if (sm) bps = [{ text: sm[1].trim(), row: null, card: null }]; }
    if (bps.length) {
      var bp = bps[0];
      var spec = { button: bp.text, row: bp.row, card: bp.card || s.head.card, block: s.head.block };
      // 판매 연결(오퍼 × 객실) 단계는 같은 룸 행이 오퍼마다 있으므로 제목의 `오퍼 · 룸` 을 행 이름으로 먼저 쓴다
      var th0 = window.titleHint(s);
      if (/판매 연결/.test(s.kind || '') && th0 && /[·・‧∙]/.test(th0) && bp.row) spec.row = th0;
      // 카드가 `이름 중 오퍼가 X 인 카드` 꼴이면: 머리글이 이름과 맞고 본문에 그 오퍼가 적힌 카드를 직접 고른다
      var cardStr = String(spec.card || '').normalize('NFC');
      var cm = cardStr.match(/^(.*?)\s*중\s*오퍼가\s*(.*?)\s*인\s*카드\s*$/)           // `이름 중 오퍼가 X 인 카드`
        || cardStr.match(/^(.*?)\s*[—–-]\s*오퍼\s*칸이\s*(.*?)\s*인\s*카드\s*$/);     // `이름 — 오퍼 칸이 X 인 카드`
      if (!cm && /부가옵션/.test(s.kind || '')) {                                          // `오퍼 의 이름` (부가옵션 가격 넣기)
        var cm2 = cardStr.match(/^(.*?)\s+의\s+(.+?)\s*$/);
        if (cm2) cm = [cm2[0], cm2[2], cm2[1]];
      }
      if (cm) {
        var pane0 = document.getElementById((location.hash || '').slice(1)) || document.body;
        var hit = Array.from(pane0.querySelectorAll('.stay-card')).find(function (c) {
          var h = c.querySelector('.stay-card__head,.stay-card__title'); if (!h) return false;
          var ht = h.textContent.normalize('NFC').replace(/\s+/g, ' ').trim();
          return stayRun.tier(ht, cm[1].trim()) >= 2 && c.textContent.normalize('NFC').replace(/\s+/g, ' ').indexOf(cm[2].trim()) >= 0;
        });
        if (hit) { spec = { button: bp.text, row: bp.row, within: hit }; out.cardPick = cm[1].trim() + ' / ' + cm[2].trim(); }
        else { out.open = 'not-found'; out.openDetail = '`' + spec.card + '` 카드를 찾지 못했습니다'; return out; }
      }
      var o = await stayRun.open(spec);
      if (o.status === 'not-found' && o.reason === 'row') {
        var hint = window.titleHint(s);
        if (hint && hint !== bp.row) { spec.row = hint; o = await stayRun.open(spec); out.rowHint = hint; }
      }
      out.open = o.status;
      if (o.status !== 'ok') { out.openDetail = o.detail; out.buttons = o.buttons; out.rows = o.rows; return out; }
    }

    var F = window.stepFields(n);
    var r = await stayRun.fill(F);
    // 화면에 없는 체크 칸(예: 저장 뒤에만 뜨는 `지금 모든 객실에 배포`)은 막지 않고 경고로만 남긴다
    out.warn = r.filter(function (x) { return x.status === 'not-found' && /^(check|uncheck)$/.test(x.kind); }).map(function (x) { return x.label + ': 화면에 없는 칸'; });
    out.bad = r.filter(function (x) { return x.status !== 'ok' && x.status !== 'skipped' && x.status !== 'needs-upload' && !(x.status === 'not-found' && /^(check|uncheck)$/.test(x.kind)); })
      .map(function (x) { return x.label + ': ' + x.status + ' ' + (x.detail || '').slice(0, 140); });
    out.uploads = r.filter(function (x) { return x.status === 'needs-upload'; }).map(function (x) { return x.label; });
    var rb = stayRun.readback(F);
    out.readback = rb.ok + '/' + rb.total; out.mismatch = rb.mismatch;
    if (opt.dry || out.bad.length || (out.uploads.length && !opt.uploaded) || (s.photos && s.photos.length && !opt.uploaded)) { out.submitted = false; return out; }
    var sub = await stayRun.submit(s.submit);
    // 지시서의 저장 글자와 화면 버튼 글자가 다를 때(예: 시즌 드로어는 [추가]) 흔한 대안을 차례로 시도한다
    if (sub.status === 'not-found') {
      var alts = ['저장', '추가', '만들기', '등록', '확인'].filter(function (a) { return a !== s.submit; });
      for (var k = 0; k < alts.length && sub.status === 'not-found'; k++) { sub = await stayRun.submit(alts[k]); if (sub.status !== 'not-found') out.submitAs = alts[k]; }
    }
    out.submit = sub.status; out.errors = sub.errors; out.toast = sub.toast; out.submitted = true;
    return out;
  };
})();
