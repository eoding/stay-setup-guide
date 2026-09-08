/* stay_boot.js — 페이지 안 실행 묶음 (stay_helper.js 위에 얹는다)
 * localStorage.staySteps 에 올려 둔 steps.json 을 읽어 window.step / stepFields / runStep 을 만든다.
 * 값은 절대 손으로 옮겨 적지 않는다 — steps.json 그대로 읽어 채운다.
 * runStep 은 알맹이(runStepCore)를 감싸며 화면 오른쪽 위 진행 표시 띠를 스스로 갱신한다.
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
    // `노출명`·`밴드 코드` 는 연령 구간 단계의 이름 칸이다(2026-09-04 신설 화면).
    // 코드보다 노출명이 앞이다 — 목록 표의 첫 칸이 코드라도, 사람이 같은 것으로 읽는 이름은 노출명이다.
    var keys = ['정책명', '룸 이름', '시즌명', '관리용 이름', '프로모션명', '혜택 이름', '노출명', '밴드 코드', '이름', '그룹 이름', '요금제명'];
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

  // 반복 행을 하나 늘리는 버튼인가 — 그런 버튼은 **여는 버튼이 아니다**(칸을 채우면서 도우미가 누른다).
  // `연령 구간 추가` 는 글자가 `구간 추가` 로 끝나지만 **오퍼 탭 `연령 구간` 카드의 드로어를 여는
  // 버튼**이다(2026-09-04 신설). 낱말만 보고 거르면 그 드로어가 영영 열리지 않는다.
  window.ROW_ADD_RE = /(행|구간|단|포인트)\s*추가$/;
  window.ROW_ADD_EXCEPT_RE = /^연령\s*구간\s*추가$/;
  window.isRowAddButton = function (text) {
    var t = String(text || '').normalize('NFC').trim();
    return window.ROW_ADD_RE.test(t) && !window.ROW_ADD_EXCEPT_RE.test(t);
  };

  // ── 지시서가 ERP 2026-09-04 이전 화면 기준인가 ────────────────────────────────────────
  // 그전에는 [호텔 만들기]가 오퍼 `기본 오퍼` · 룸 `스탠다드` · 그 둘의 연결행을 미리 만들어 두었고,
  // 지시서는 그것들을 **고쳐 쓰는** 단계(`오퍼 고치기`, `스탠다드` 행의 [편집])를 적었다.
  // 지금은 오퍼 0 · 룸 0 으로 시작하므로 그 단계는 누를 행이 화면에 아예 없다 — 엉뚱한 행을
  // 고치는 사고를 막으려고 실행하지 않고 거부한다. 고쳐 쓸 방법은 없다: 지시서를 다시 만들어야 한다.
  window.staleStep = function (s) {
    var nfc = function (t) { return String(t || '').normalize('NFC'); };
    var kind = nfc(s && s.kind), title = nfc(s && s.title);
    var head = nfc(JSON.stringify((s && s.head) || {}));
    if (/^오퍼 고치기/.test(kind) || /^오퍼 고치기/.test(title)) return '`오퍼 고치기` 단계 — 고쳐 쓸 `기본 오퍼` 가 없습니다';
    if (/룸 만들기/.test(kind) && /스탠다드/.test(head)) return '`룸 만들기` 단계가 `스탠다드` 행의 [편집] 을 가리킵니다';
    if (/기본 오퍼/.test(head)) return '`기본 오퍼` 를 가리키는 단계입니다';
    return null;
  };
  window.STALE_GUIDE_MSG = '지시서가 ERP 2026-09-04 이전 화면 기준입니다 — 이 러너는 오퍼 0 · 룸 0 으로 시작하는 화면만 다룹니다. 지시서를 다시 만드세요(옛 화면이면 러너 v0.2.x 를 쓰세요).';

  // `경고 넘어가기` 는 **금지된 단계**다. 합격선은 판매 시작 전 🟡 0 이라 사유를 적어 넘기는 길이 없다 —
  // 🟡 가 남으면 지시서 결함이므로 원인을 지시서에서 고쳐 다시 깐다.
  window.FORBIDDEN_WARN_MSG = '`경고 넘어가기` 는 금지된 단계입니다 — 합격선은 판매 시작 전 🟡 0 입니다. 사유를 적어 넘기지 말고 지시서에서 원인을 고쳐 다시 까세요.';

  // 실행을 거부하는 이유 한 줄 (없으면 null) — 옛 화면 기준 단계와 금지된 단계를 함께 본다
  window.refusedStep = function (s) {
    var nfc = function (t) { return String(t || '').normalize('NFC'); };
    if (/경고 넘어가기/.test(nfc(s && s.kind)) || /^경고 넘어가기/.test(nfc(s && s.title))) return window.FORBIDDEN_WARN_MSG;
    return window.staleStep(s);
  };

  // 실행 전 한 번에 훑기 — 걸리는 단계 번호를 돌려준다 (빈 배열이면 이 지시서로 진행해도 된다)
  window.checkGuide = function () {
    return d.steps.map(function (s) { var why = window.refusedStep(s); return why ? { no: s.no, title: s.title, why: why } : null; })
      .filter(Boolean);
  };
  (function () {
    var bad = window.checkGuide();
    if (bad.length && window.console) console.warn('[stay-run] 실행을 거부하는 단계가 있습니다: ' + bad.map(function (x) { return x.no + '단계 — ' + x.why; }).join(' / '));
  })();

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
    // 2026-09-08 에 화면의 카드 이름이 `인원별 가격 추가` → `인원별 · 박수별 가격 추가` 로 바뀌었다
    // (박수 축이 돌아오면서 제목이 두 축을 함께 부른다). 지시서는 사전의 글자를 그대로 쓰므로
    // 새 원고는 긴 이름으로 오는데, 옛 원고·옛 산출물은 짧은 이름 그대로다 — **두 표기를 다 받는다.**
    // 한쪽만 읽으면 그 원고의 `가격 셀 만들기` 단계가 카드를 못 읽어 통째로 멈춘다.
    var m3 = !m && raw.match(/^(.*)\s+[×xX]\s+(.*?)\s+의\s+인원별\s*(?:[·・‧∙]\s*박수별\s*)?가격\s+추가\s*$/);
    if (m3) m = [m3[0], m3[1], m3[2], null];
    if (!date || !m) { out.error = '제목의 날짜나 카드의 `오퍼 · 룸 × 요금제 의 인원 조합 N 행` 꼴을 읽지 못했습니다'; return out; }
    var linkName = clean(m[1]), ratePlan = clean(m[2]), occ = m[3] ? clean(m[3]) : '무관'; // `인원 무관 단일가 행` 이면 무관
    // 카드 줄이 좌표를 안 부르는 꼴(새 행 표 이름 · `… × 요금제 행`)이면 **`인원 조합` 칸으로 되돌아본다.**
    // 규칙서(§가격 셀)가 새 행 단계의 카드 줄을 `… 의 인원별 · 박수별 가격 추가` 로 쓰라고 하는데,
    // 그 꼴은 위 m3 가지에서 `m[3]=null` 이라 종전에는 무조건 `무관` 으로 굳었다 — 칸에 `A2` 를
    // 적어 두어도 새 행 셀렉트가 `인원 무관 단일가` 로 맞춰져, 그 룸이 `A2` 로 깔리는 계약에서는
    // **아무도 팔지 않는 좌표**가 하나 생긴다(2026-09-08 C-voco 에서 실제로 났다).
    // 칸 값은 셀렉트 항목 글자(`선택: A2 · 성인 2`)로 오므로 접두·꼬리를 벗겨 키만 남긴다 —
    // 검사기 `_occupancy_key_of_value` 와 **같은 판정**이다(두 벌이 되면 또 어긋난다).
    if (!m[3]) {
      var occField = (s.fields || []).filter(function (f) {
        return /^인원\s*조합$/.test(clean(f.label || '').replace(/\(선택\)$/, ''));
      })[0];
      var occRaw = occField ? clean(occField.value || occField.raw_value || '') : '';
      occRaw = occRaw.replace(/^선택\s*:\s*/, '').split(/\s+[·・‧∙]\s+/)[0];
      if (occRaw && !/^(비움|인원\s*무관\s*단일가)$/.test(occRaw)) occ = occRaw;
    }
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
    // 좌표 칩은 `.stay-coord-btn` 이다. `.stay-coord-group` 은 **오퍼 줄에도 쓰인다**
    // (오퍼가 둘 이상이면 오퍼 라디오도 같은 상자에 든다) — 그 상자의
    // 아무 버튼이나 잡으면 오퍼 칩을 룸 칩으로 오인한다.
    var coordBtns = function () { return [].slice.call(pane.querySelectorAll('.stay-coord-btn')); };
    var onCoord = function () { return coordBtns().some(function (b) { var tt = clean(b.textContent); return /--primary/.test(b.className) && tier(tt.split(/\s+[·・‧∙]\s+/)[0], display) >= 3 && (!ratePlan || tt.indexOf(ratePlan) >= 0); }); };
    var findRoomBtn = function () {
      return [].slice.call(pane.querySelectorAll('button.stay-ov-row')).concat(coordBtns()).find(function (b) {
        var tt = clean(b.getAttribute('title') || b.textContent), head = tt.split(/\s+[·・‧∙]\s+/)[0];
        return tier(head, display) >= 3 && (!ratePlan || tt.indexOf(ratePlan) >= 0);
      });
    };
    if (!onCoord()) {
      var rb = findRoomBtn();
      if (!rb) { out.error = '룸 줄에서 `' + display + ' · ' + ratePlan + '` 을 찾지 못했습니다 (' + monthOf() + ')'; return out; }
      await settled(function () { rb.click(); });
      // 개요 화면에 머물면 [룸별 입력] 보기로 바꾼다 (룸은 방금 고른 것이 유지된다)
      if (!pane.querySelector('.stay-coord-btn')) {
        var vb = [].slice.call(pane.querySelectorAll('.stay-view-btn, button')).find(function (x) { return /룸별 입력/.test(x.textContent) && !/--primary/.test(x.className); });
        var hasCoord = function () { return !!pane.querySelector('.stay-coord-btn'); };
        for (var vi = 0; vi < 2 && vb && !hasCoord(); vi++) { // 화면 전환이 늦게 끝나기도 해서 칩이 보일 때까지 기다리고 한 번 더 누른다
          await settled(function () { vb.click(); });
          await waitFor(function () { return hx.pending === 0 && hasCoord(); }, 8000);
          vb = [].slice.call(pane.querySelectorAll('.stay-view-btn, button')).find(function (x) { return /룸별 입력/.test(x.textContent) && !/--primary/.test(x.className); });
        }
      }
      // 좌표 화면의 룸 칩이 다른 룸을 가리키면 이 룸 칩을 눌러 바꾼다 (최대 3번)
      for (var ci = 0; ci < 3 && !onCoord(); ci++) {
        var chip2 = coordBtns().find(function (x) { var tt = clean(x.textContent); return tier(tt.split(/\s+[·・‧∙]\s+/)[0], display) >= 3 && (!ratePlan || tt.indexOf(ratePlan) >= 0); });
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
    // 두 표의 인원 칸은 **위젯이 다르다**:
    // 기존 행은 글자 칸, `인원별 가격 추가` 의 새 행은 이미 쓰는 키만 고르게 하는 셀렉트다.
    // 그리고 그 날짜에 셀이 하나도 없으면 **기존 행 표 자체가 안 그려진다** — 표가 하나뿐이라
    // 종전의 `tables.length > 1` 갈래로는 `가격 셀 만들기` 가 통째로 실패했다.
    var tables = [].slice.call(ed.querySelectorAll('table')), found = null, isNew = false;
    var keyCtl = function (r) { return r.querySelector('input[name=occupancy_key],select[name=occupancy_key]'); };
    // 새 행 표는 좌표를 숨은 칸으로 들고 있다(option · rate_plan · date) — 기존 행 표에는 없다
    var isNewTable = function (tb) { return !!tb.querySelector('input[type=hidden][name=date],input[type=hidden][name=option]'); };
    var oldTables = tables.filter(function (tb) { return !isNewTable(tb); });
    var newTable = tables.filter(isNewTable)[0] || (tables.length > 1 ? tables[tables.length - 1] : null);
    oldTables.forEach(function (tb) {
      if (found) return;
      [].slice.call(tb.querySelectorAll('tbody tr')).forEach(function (r) {
        if (found) return;
        var oc = keyCtl(r);
        if (!oc) return;
        var v = clean(oc.value);
        if (occ === '무관' ? (v === '' || v === '0' || /무관/.test(clean(r.textContent))) : v === occ) found = { row: r, table: tb };
      });
    });
    // 인원 구분이 없는 카드면 기존 행이 하나뿐일 때 그 행을 쓴다
    if (!found && occ === '무관' && oldTables.length) { var only = [].slice.call(oldTables[0].querySelectorAll('tbody tr')).filter(keyCtl); if (only.length === 1) found = { row: only[0], table: oldTables[0] }; }
    if (!found && newTable) {
      var nr = [].slice.call(newTable.querySelectorAll('tbody tr')).filter(keyCtl)[0] || newTable.querySelector('tbody tr');
      if (nr) { found = { row: nr, table: newTable }; isNew = true; }
    }
    if (!found) { out.error = '인원 조합 ' + occ + ' 행을 찾지 못했습니다 (표 ' + tables.length + '개)'; return out; }
    out.newRow = isNew;
    // 새 행은 인원 칸을 먼저 맞춘다 — 지시서 카드가 말한 조합 그대로다(값을 지어내지 않는다).
    // 그 칸이 셀렉트면 `무관` 은 빈 값(`인원 무관 단일가`)이다.
    if (isNew) {
      var oc0 = keyCtl(found.row);
      if (oc0) {
        var want0 = occ === '무관' ? '' : occ;
        if (oc0.tagName === 'SELECT') {
          var hit0 = [].slice.call(oc0.options).find(function (o) { return clean(o.value) === want0; });
          if (!hit0 && want0) { out.error = '새 행의 인원 조합 목록에 `' + occ + '` 이(가) 없습니다 (' + [].slice.call(oc0.options).map(function (o) { return clean(o.textContent); }).join(' / ') + ')'; return out; }
          if (hit0) { oc0.value = hit0.value; ['input', 'change'].forEach(function (ev) { oc0.dispatchEvent(new Event(ev, { bubbles: true })); }); }
        } else if (want0) {
          var dsc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
          dsc && dsc.set ? dsc.set.call(oc0, want0) : (oc0.value = want0);
          ['input', 'change'].forEach(function (ev) { oc0.dispatchEvent(new Event(ev, { bubbles: true })); });
        }
        out.occSet = oc0.value;
      }
    }
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
    // 되읽기 — 인원 칸은 글자 칸일 수도 셀렉트일 수도 있으므로 **값**으로 읽는다(셀렉트의 보이는
    // 글자는 `인원 무관 단일가` 라 값(빈 문자열)과 다르다).
    out.after = ed2 ? [].slice.call(ed2.querySelectorAll('tbody tr')).map(function (r) {
      return [].slice.call(r.querySelectorAll('input:not([type=hidden]),select')).map(function (i) {
        return i.name + '=' + (i.tagName === 'SELECT' && i.name !== 'occupancy_key' ? clean((i.options[i.selectedIndex] || {}).textContent) : i.value);
      }).join(' ');
    }).filter(function (x) { return occ === '무관' ? /^occupancy_key=(0)?\s/.test(x) : x.indexOf('occupancy_key=' + occ + ' ') === 0; }) : [];
    var closeBtn = ed2 && [].slice.call(ed2.querySelectorAll('button')).find(function (b) { return tier(b.textContent, '닫기') >= 3; });
    if (closeBtn) { closeBtn.click(); await sleep(300); }
    return out;
  };

  /* ──────────── [호텔 만들기] 폼이 다 그려질 때까지 기다리기 (2026-09-07) ──────────── */
  // 이 폼은 뼈대를 먼저 그리고 **그 뒤에** 통화 목록을 채우고 도시·거래처에 select2 를 붙인다.
  // 그전에 읽거나 채우면 아무 칸도 못 찾는다 — 운영 실행에서 0단계 확인 세 개가 모두
  // `{checked:false, found:[]}` 로, [호텔 만들기] 는 칸마다 `not-found` 로 끝났고
  // 몇 초 뒤 그대로 다시 부르니 한 번에 됐다. 그래서 읽기·채우기 앞에서 늘 기다린다.
  window.HOTEL_FORM_WAIT_MS = 8000;
  // [호텔 만들기] 폼 위에 서 있는가 (목록 화면과 가르는 기준)
  window.onHotelForm = function () {
    var nfc0 = function (t) { return String(t || '').normalize('NFC').replace(/\s+/g, ' ').trim(); };
    try { return stayRun.fields().some(function (f) { return /^(호텔명|공급 통화|거래처|도시)$/.test(nfc0(f.label)); }); }
    catch (e) { return false; }
  };
  window.hotelFormReady = function () {
    var nfc = function (t) { return String(t || '').normalize('NFC').replace(/\s+/g, ' ').trim(); };
    var fs = [];
    try { fs = stayRun.fields(); } catch (e) { return false; }
    var byLabel = function (re) { return fs.find(function (x) { return re.test(nfc(x.label)); }); };
    var ctlOf = function (f) { return f && f.name ? document.querySelector('[name="' + f.name + '"]') : null; };
    // ① 공급 통화 목록이 찼는가 (뼈대만 그려진 사이에는 빈 `선택` 한 줄뿐이다)
    var cur = document.querySelector('select[name=currency]') || ctlOf(byLabel(/통화/));
    if (!cur || cur.tagName !== 'SELECT' || cur.options.length < 2) return false;
    // ② 도시·거래처가 쓸 수 있는 꼴인가.
    //    select2 를 쓰는 화면이면(라이브러리가 실려 있거나 이미 붙은 칸이 있으면) **붙을 때까지** 기다린다 —
    //    붙기 전에는 그냥 셀렉트로 보여서 "다 됐다" 고 잘못 읽기 쉽다. 이것이 운영에서 깨진 지점이다.
    var s2 = !!(window.jQuery && window.jQuery.fn && window.jQuery.fn.select2) || !!document.querySelector('.select2-container');
    return [/도시/, /거래처/].every(function (re) {
      var f = byLabel(re);
      if (!f) return false;
      var el = ctlOf(f);
      if (s2) return f.kind === 'select2' && !!document.querySelector('.select2-container');
      return el && el.tagName === 'SELECT' ? el.options.length >= 2 : true;
    });
  };
  // 폼이 다 설 때까지 기다린다. 끝내 서지 않아도 막지 않고 `{ready:false}` 로 알린 뒤 그대로 이어 간다 —
  // 화면이 조금 다른 경우까지 여기서 멈추면 실행이 통째로 서기 때문이다.
  window.waitHotelForm = async function (ms) {
    var t0 = Date.now();
    if (window.hotelFormReady()) return { ready: true, waited: 0 };
    var ready = await stayRun.waitFor(window.hotelFormReady, ms || window.HOTEL_FORM_WAIT_MS);
    return { ready: ready, waited: Date.now() - t0 };
  };

  // 0단계 확인(`환율 확인` · `거래처 확인` · `도시 확인`) — **저장이 없는 단계**다.
  // [호텔 만들기] 폼을 열어 지시서 값이 그 화면의 목록(셀렉트·자동완성)에 뜨는지만 보고 돌아온다.
  // 지시서 마지막 줄의 `→ [목록]` 은 저장 버튼이 아니라 **목록으로 돌아오는 행위**를 가리킨다.
  window.CHECK_KIND_RE = /^(환율|거래처|도시)\s*확인/;
  window.runCheckStep = async function (n, opt) {
    opt = opt || {};
    var s = window.step(n), out = { no: n, title: s.title, kind: s.kind, checked: false, found: [] };
    var sleep = stayRun.sleep, waitFor = stayRun.waitFor;
    var clean = function (t) { return String(t || '').normalize('NFC').replace(/\s+/g, ' ').trim(); };
    var onForm = window.onHotelForm;
    // 폼이 화면에 없으면 목록의 [호텔 만들기] 로 연다. 그 이동은 **전체 화면 이동**이라 JS 호출이
    // 결과를 못 돌려주고 끊길 수 있다 — 그때는 새 화면에서 부트를 다시 eval 하고 이 단계를 다시 부른다.
    // 화면이 아직 그려지는 중이면 폼도 [호텔 만들기] 버튼도 없다 — 둘 중 하나가 설 때까지만 잠깐 본다
    if (!onForm()) await waitFor(function () { return onForm() || !!stayRun.findButton(document.body, '호텔 만들기'); }, 4000);
    if (!onForm()) {
      var opener = stayRun.findButton(document.body, '호텔 만들기');
      if (!opener) { out.error = '[호텔 만들기] 폼도 그 버튼도 화면에 없습니다 — 호텔 목록에서 시작하세요'; return out; }
      opener.click();
      await waitFor(onForm, 8000);
      if (!onForm()) { out.navigated = true; out.note = '[호텔 만들기] 폼으로 넘어갑니다 — 새 화면에서 부트를 다시 eval 하고 이 단계를 다시 부르세요'; return out; }
    }
    // 통화 목록이 차고 도시·거래처 select2 가 붙을 때까지 기다린다 — 그전에 읽으면 다 못 찾는다
    var fw = await window.waitHotelForm();
    out.formReady = fw.ready; if (fw.waited) out.formWaited = fw.waited;
    // 값을 골라 목록에 있는지 본다. 고르기만 할 뿐 **아무 것도 저장하지 않는다**
    // (이 화면의 저장 버튼은 [호텔 만들기] 하나뿐이고 이 단계는 누르지 않는다).
    var F = window.stepFields(n);
    var r = await stayRun.fill(F);
    out.found = r.filter(function (x) { return x.status === 'ok'; }).map(function (x) { return x.label + ': ' + (x.detail || ''); });
    out.bad = r.filter(function (x) { return x.status !== 'ok' && x.status !== 'skipped'; })
      .map(function (x) { return x.label + ': ' + x.status + ' ' + (x.detail || '').slice(0, 140); });
    out.checked = out.bad.length === 0;
    out.submitted = false; // 저장하는 단계가 아니다
    // `→ [목록]` — 다음 단계도 이 폼을 쓰면(확인 단계·호텔 만들기) 그대로 두고, 아니면 목록으로 돌아온다.
    // 값이 목록에 없으면(bad) 화면을 눈으로 볼 수 있게 폼에 남는다.
    var nx = window.step(n + 1);
    var sameForm = !!(nx && (window.CHECK_KIND_RE.test(nx.kind || '') || /^호텔 만들기/.test(nx.kind || '')));
    if (opt.back === false || sameForm || out.bad.length) { out.stayOnForm = true; return out; }
    var back = stayRun.findButton(document.body, s.submit || '목록') || stayRun.findButton(document.body, '목록');
    if (!back) { out.stayOnForm = true; out.note = '[목록] 버튼을 찾지 못했습니다 — 폼에 그대로 있습니다'; return out; }
    back.click(); await sleep(300);
    out.left = true;
    return out;
  };

  window.runStepCore = async function (n, opt) {
    opt = opt || {};
    var s = window.step(n);
    var out = { no: n, title: s.title };
    // 옛 화면(자동 생성물 고쳐 쓰기) 기준 단계와 금지된 단계(`경고 넘어가기`)는 실행하지 않는다 — 위 `refusedStep`
    var why = window.refusedStep(s);
    if (why) return { no: n, title: s.title, refused: true, fatal: true, error: why === window.FORBIDDEN_WARN_MSG ? why : window.STALE_GUIDE_MSG + ' (' + why + ')' };
    if (/가격 셀/.test(s.kind || '')) return window.runCellStep(n, opt);
    if (window.CHECK_KIND_RE.test(s.kind || '')) return window.runCheckStep(n, opt);
    if (s.head.tab) { var t = await stayRun.tab(s.head.tab); out.tab = t.status; }

    // 같은 이름이 이미 있으면 만들지 않는다
    if (/만들기|추가/.test(s.kind) && !/고치기|표시명|가격|사진|이미지|넘어가기|판매 연결/.test(s.kind)) {
      var nm = window.nameOf(s);
      var offerF = (s.fields || []).find(function (x) { return x.label === '오퍼' && x.kind === 'select' && x.value; });
      var offerV = offerF ? offerF.value : null;
      if (nm && window.existsInList(nm, s.head.card, offerV)) return { no: n, title: s.title, skipped: true, reason: '이미 있음: ' + nm + (s.head.card || offerV ? ' (' + (s.head.card || offerV) + ')' : '') };
    }

    // 여는 버튼만 고른다 — 드로어 안 버튼과 행 추가류(행/구간/단/요율 행 추가)는 칸을 채우면서 도우미가 누른다
    var bps = (s.head.buttons_parsed || []).filter(function (b) { return b.text && !b.drawer && !window.isRowAddButton(b.text); });
    // 버튼 줄이 없고 `화면:` 설명이 `… [호텔 만들기]` 처럼 대괄호 버튼으로 끝나면 그 버튼을 연다
    if (!bps.length && s.head.screen) { var sm = String(s.head.screen).normalize('NFC').match(/\[([^\]]+)\]\s*$/); if (sm) bps = [{ text: sm[1].trim(), row: null, card: null }]; }
    // [호텔 만들기] 단계는 목록에서 시작할 수도, 0단계 확인이 끝나 이미 그 폼 위에 있을 수도 있다.
    // ① 화면이 아직 그려지는 중이면 목록의 [호텔 만들기] 도 폼도 없다 — 둘 중 하나가 설 때까지 기다린다.
    // ② 이미 폼 위라면 여는 버튼을 누르지 않는다: 이 화면의 [호텔 만들기] 는 **저장 버튼**이라
    //    누르는 순간 빈 폼이 그대로 저장된다.
    if (/^호텔 만들기/.test(s.kind || '')) {
      await stayRun.waitFor(function () {
        return window.onHotelForm() || !!stayRun.findButton(document.body, '호텔 만들기');
      }, window.HOTEL_FORM_WAIT_MS);
      if (window.onHotelForm()) { bps = []; out.onForm = true; }
    }
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
      // (2026-09-04) `전 오퍼 공통` 카드는 공통 프로모션이 0건이어도 늘 그려진다.
      // 종전에는 카드가 감춰져서 아무 오퍼 카드의 [프로모션 추가] 요청 URL 의 오퍼 번호를 0 으로
      // 바꿔 여는 우회가 있었다 — ERP 가 고쳐졌으므로 그 우회는 지웠다. 보통 카드처럼 연다.
      var o = await stayRun.open(spec);
      if (o.status === 'not-found' && o.reason === 'row') {
        var hint = window.titleHint(s);
        if (hint && hint !== bp.row) { spec.row = hint; o = await stayRun.open(spec); out.rowHint = hint; }
      }
      out.open = o.status;
      if (o.status !== 'ok') { out.openDetail = o.detail; out.buttons = o.buttons; out.rows = o.rows; return out; }
    }

    // [호텔 만들기] 는 전체 화면 폼이다 — 통화 목록·select2 가 다 설 때까지 기다린 뒤에 채운다
    if (/^호텔 만들기/.test(s.kind || '')) {
      var fw2 = await window.waitHotelForm();
      out.formReady = fw2.ready; if (fw2.waited) out.formWaited = fw2.waited;
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
    // 마지막 버튼이 저장이 아니라 **파일 고르개**인 단계가 있다(룸 사진 올리기 — 지시서는
    // `→ [사진 추가]` 로 끝난다, 2026-09-04 dict-audit 합의). 그 화면에는 누를 저장 버튼이
    // 아예 없고 파일을 담는 순간 올라간다. 여기서 대안(`저장`…)을 훑으면 룸 폼의 [저장] 을
    // 눌러 사진이 붙기 전에 드로어를 닫는다 — 그래서 대안 훑기 전에 끊는다.
    if (sub.status === 'upload-label') {
      out.uploadAction = s.submit; out.submit = 'upload-label'; out.submitted = false;
      out.note = sub.detail;
      return out;
    }
    // 지시서의 저장 글자와 화면 버튼 글자가 다를 때(예: 시즌 드로어는 [추가]) 흔한 대안을 차례로 시도한다
    if (sub.status === 'not-found') {
      var alts = ['저장', '추가', '만들기', '등록', '확인'].filter(function (a) { return a !== s.submit; });
      for (var k = 0; k < alts.length && sub.status === 'not-found'; k++) { sub = await stayRun.submit(alts[k]); if (sub.status !== 'not-found') out.submitAs = alts[k]; }
    }
    out.submit = sub.status; out.errors = sub.errors; out.toast = sub.toast; out.submitted = true;
    return out;
  };

  /* ─────────────────────────── 진행 표시 띠 갱신 ─────────────────────────── */
  // `runStep` 은 알맹이(`runStepCore`)를 감싼 얇은 껍데기다 — 부르는 쪽은 따로 손댈 것이 없다.
  // 페이지에 옛 도우미가 깔려 있어 `progress` 가 없을 수도 있으므로 모든 호출을 감싼다.
  function progSafe(patch) {
    try {
      if (window.stayRun && typeof window.stayRun.progress === 'function') return window.stayRun.progress(patch);
    } catch (e) { /* 표시가 막혀도 실행은 계속한다 */ }
    return null;
  }
  // 같은 단계를 두 번 부르는 일이 정상으로 있다 — 룸 사진 올리기는 파일 다리로 사진을 올린 뒤
  // `{uploaded:true}` 로 다시 부르고, 고친 뒤 다시 돌리기도 한다. 숫자를 그때마다 +1 하면
  // 전체 수를 넘어서고 한 단계가 실패이면서 완료로도 세어진다.
  // 그래서 **단계마다 판정 하나만** 들고(덮어쓴다), 숫자는 그 판정을 세어 낸다.
  // `pending` 은 아직 끝나지 않은 단계다 — 지도에는 있지만 셋 중 어디에도 세지 않는다.
  function stepStatusMap() {
    if (!window.__stayRunStatus) window.__stayRunStatus = {};
    return window.__stayRunStatus;
  }
  function progCount() {
    var map = stepStatusMap(), c = { done: 0, skipped: 0, failed: 0 };
    Object.keys(map).forEach(function (k) { if (c[map[k]] !== undefined) c[map[k]]++; });
    return c;
  }
  function progMark(n, klass, patch) {
    stepStatusMap()[n] = klass;
    var c = progCount(), p = { done: c.done, skipped: c.skipped, failed: c.failed };
    Object.keys(patch || {}).forEach(function (k) { p[k] = patch[k]; });
    return progSafe(p);
  }
  // 왜 실패했는지 한 줄 — 띠에 들어갈 만큼만 자른다
  function progReason(r) {
    var t = '';
    if (r && r.bad && r.bad.length) t = String(r.bad[0]);
    else if (r && r.error) t = String(r.error);
    else if (r && r.openDetail) t = String(r.openDetail);
    t = String(t).normalize('NFC').replace(/\s+/g, ' ').trim();
    return t.length > 60 ? t.slice(0, 60) + '…' : t;
  }
  // 저장이 잘 끝난 상태들 — `stayRun.submit` 은 `ok` 를 돌려주지 않는다(`closed`·`stayed`·`settled`·`navigated`).
  // 그래서 `submit !== 'ok'` 만 보면 저장이 성공한 단계까지 전부 실패로 세게 된다.
  window.SUBMIT_OK = ['ok', 'closed', 'stayed', 'settled', 'navigated'];
  window.stepFailed = function (r) {
    if (!r) return false;
    if (r.refused || r.fatal) return true;
    if (r.bad && r.bad.length) return true;
    if (r.open === 'not-found' || r.open === 'ambiguous') return true;
    if (r.submit !== undefined && r.submit !== null && window.SUBMIT_OK.indexOf(String(r.submit)) < 0) return true;
    return false;
  };

  window.runStep = async function (n, opt) {
    opt = opt || {};
    var s = null;
    try { s = window.step(n); } catch (e) { s = null; }
    var title = (s && s.title) || (n + '단계');
    progSafe({ current: title, total: d.steps.length });
    var r;
    try {
      r = await window.runStepCore(n, opt);
    } catch (e) {
      progMark(n, 'failed', { current: title, note: progReason({ error: (e && e.message) || String(e) }) });
      throw e;
    }
    // 아직 끝나지 않은 단계는 어느 숫자에도 세지 않는다 —
    // `upload-label` 은 파일 다리로 사진을 올린 뒤 다시 부르라는 넘김이지 실패가 아니고,
    // 시험 삼아 돌린 단계(dry)도 마찬가지다. 다시 부르면 그때 판정이 덮인다.
    // 판정은 `submit` 글자와 `dry` 로만 가른다 — `runCheckStep` 은 저장이 없는 정상 단계라
    // `submitted:false` 에 `submit` 칸이 아예 없다(그것으로 가르면 확인 단계가 통째로 안 세어진다).
    if (opt.dry || (r && r.submit === 'upload-label')) progMark(n, 'pending', { current: title, note: '' });
    // 실패한 단계는 제목을 그대로 남긴다 — 지켜보는 사람이 어느 단계에서 깨졌는지 띠만 보고 안다
    else if (window.stepFailed(r)) progMark(n, 'failed', { current: title, note: progReason(r) });
    else if (r && r.skipped) progMark(n, 'skipped', { note: '' });
    else progMark(n, 'done', { note: '' });
    return r;
  };

  // 실행을 시작하기 전에 한 번 부른다 — 단계별 판정과 숫자를 0 으로 되돌리고 전체 단계 수를 넣는다
  window.progressReset = function (total) {
    window.__stayRunStatus = {};
    return progSafe({
      done: 0, skipped: 0, failed: 0, current: '', note: '',
      total: total === undefined ? d.steps.length : total, status: 'idle'
    });
  };
})();
