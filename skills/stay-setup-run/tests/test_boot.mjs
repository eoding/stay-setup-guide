/**
 * stay_boot.js 자동 시험 — 가격 캘린더의 셀 편집(`runCellStep`)만 본다.
 *
 *   node tests/test_boot.mjs
 *   NODE_PATH=<jsdom 이 있는 node_modules> node tests/test_boot.mjs
 *
 * jsdom 이 없으면 아무것도 설치하지 않고 건너뛴다(종료 코드 0).
 *
 * 여기서 잡는 것은 `가격 셀 만들기` 다. 그 날짜에 셀이 하나도 없으면 편집창에 표가 **하나뿐**이고
 * 그 표의 인원 칸은 셀렉트다(이미 쓰는 인원 키만 고르게 한다).
 * 종전 러너는 표가 둘일 때만 새 행을 찾고 인원 칸도 `input` 으로만 봐서 이 단계가 통째로 실패했다.
 */
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));

let pass = 0, fail = 0;
const ok = (cond, name, extra) => {
  if (cond) { pass++; console.log('  ok   ' + name); }
  else { fail++; console.log('  FAIL ' + name + (extra !== undefined ? ' — ' + JSON.stringify(extra) : '')); }
};

/* ────────────────────────────────────────────────────────────────────────────
   jsdom 없이 도는 부분 — 떼어 놓고 도는 실행 고리 (`runAll` · `runStatus` · `runStop`)

   고리가 하는 일은 **차례와 멈춤 판정**이지 화면 조작이 아니다. `runStep` 을 가짜로 바꾸면
   DOM 없이도 그대로 볼 수 있다 — 그래서 이 대목은 jsdom 이 없는 곳에서도 돈다.
   멈춤 판정만은 가짜로 바꾸지 않는다: 진짜 `stepFailed` 를 그대로 쓴다.
   ──────────────────────────────────────────────────────────────────────────── */

const BOOT_SRC = readFileSync(join(here, '..', 'scripts', 'stay_boot.js'), 'utf8');
const HELPER_SRC_FOR_BOOT = readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8');

// 도우미의 `config({waitMs})` 를 표시 사이만 떼어 낸다 — `runAll({waitMs})` 가 **진짜 그 함수**에
// 닿는지 보려는 것이다(흉내를 세우면 닿지 않아도 통과한다).
function loadHelperConfig() {
  const a = HELPER_SRC_FOR_BOOT.indexOf('/* @config:start');
  const b = HELPER_SRC_FOR_BOOT.indexOf('/* @config:end');
  if (a < 0 || b <= a) return null;
  return new Function('var WAIT_MS = 10000;\n' + HELPER_SRC_FOR_BOOT.slice(a, b) +
    '\nreturn { config: config, waitMs: function () { return WAIT_MS; } };')();
}

function bootSandbox(steps) {
  const store = {};
  const cfgHolder = { value: null };
  const ctx = vm.createContext({
    console,
    setTimeout, clearTimeout,
    localStorage: {
      getItem: (k) => (Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: (k) => { delete store[k]; }
    },
    document: {
      getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
      addEventListener: () => {}, body: null, documentElement: { getAttribute: () => null }
    },
    location: { hash: '', href: 'https://example.test/stay/43900/', pathname: '/stay/43900/' }
  });
  ctx.window = ctx;
  ctx.addEventListener = () => {};
  // 도우미(`stayRun`) 가운데 고리가 쓰는 것만 세운다
  ctx.stayRun = {
    sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
    // 고리가 **무엇을 기다리는지** 보려면 흉내도 조건을 봐야 한다 — 참이 될 때까지 짧게 돈다
    settleOr: async (cond, ms) => {
      if (typeof cond !== 'function') { await new Promise((r) => setTimeout(r, ms || 0)); return false; }
      const t0 = Date.now();
      for (;;) {
        try { if (cond()) return true; } catch (e) { /* 교체 중 */ }
        if (Date.now() - t0 >= (ms === undefined ? 100 : ms)) { try { return !!cond(); } catch (e) { return false; } }
        await new Promise((r) => setTimeout(r, 10));
      }
    },
    waitFor: async (fn, ms) => {
      const t0 = Date.now();
      while (Date.now() - t0 < (ms || 10000)) {
        try { if (fn()) return true; } catch (e) { /* 교체 중 */ }
        await new Promise((r) => setTimeout(r, 10));
      }
      try { return !!fn(); } catch (e) { return false; }
    },
    config: (cfgHolder.value = loadHelperConfig()) ? cfgHolder.value.config : undefined,
    tier: () => 0,
    findButton: () => null,
    progress: () => ({}),
    progressState: () => ({ done: 0, skipped: 0, failed: 0, total: 0, current: '', note: '', status: 'idle' })
  };
  ctx.localStorage.setItem('staySteps', JSON.stringify(steps));
  ctx.__cfg = cfgHolder.value;        // 시험이 지금 천장을 읽는 자리
  vm.runInContext(BOOT_SRC, ctx);
  return ctx;
}

const stepOf = (no, kind, extra) => Object.assign({
  no, title: kind + ' (' + no + ')', kind,
  head: { tab: null, card: null, block: null, screen: null, buttons: [], buttons_parsed: [] },
  fields: [], longtexts: [], photos: [], submit: '저장'
}, extra || {});

const okResult = (n) => ({ no: n, submit: 'closed', submitted: true, drawer: { open: false }, modal: { open: false } });

// 고리가 설 때까지 기다린다(시험용 — 실제 에이전트는 30초에 한 번 `runStatus()` 를 읽는다)
async function waitLoop(ctx, ms) {
  const t0 = Date.now();
  while (Date.now() - t0 < (ms || 4000)) {
    if (!ctx.runStatus().running) return ctx.runStatus();
    await new Promise((r) => setTimeout(r, 10));
  }
  return ctx.runStatus();
}

async function loopTests() {
  console.log('stay_boot 시험 — 떼어 놓고 도는 고리 (jsdom 없이)');

  const steps = { guide: { title: '시험 호텔' }, steps: [1, 2, 3, 4, 5].map((n) => stepOf(n, '룸 만들기')) };

  // 1. 끝까지 돈다
  {
    const ctx = bootSandbox(steps);
    const seen = [];
    ctx.runStep = async (n) => { seen.push(n); return okResult(n); };
    const started = ctx.runAll();
    ok(started.started === true && started.from === 1 && started.to === 5, 'runAll: 곧바로 돌아온다', started);
    ok(!!started.token, 'runAll: 표(token)를 준다', started.token);
    ok(ctx.runStatus().running === true, 'runStatus: 도구 호출이 끝나도 고리는 돌고 있다');
    const st = await waitLoop(ctx);
    ok(st.running === false && st.reason === 'done', 'runAll: 마지막 단계까지 가면 reason=done', st.reason);
    ok(seen.join(',') === '1,2,3,4,5', 'runAll: 번호 차례대로 한 단계씩 부른다', seen);
    ok(st.results.length === 5 && st.results[0].no === 1, 'runStatus: results 는 차례대로 쌓인다', st.results.map((r) => r.no));
    ok(st.lastResult.no === 5, 'runStatus: lastResult 는 마지막 단계다', st.lastResult);
    ok(st.doneCount === 5, 'runStatus: doneCount', st.doneCount);
    ok(st.cursor.lastDone === 5 && !st.cursor.pending, 'runAll: 이어서 하기 자리가 5로 올라갔다', st.cursor);
    ok(st.elapsedMs >= 0 && st.startedAt, 'runStatus: 걸린 시간을 준다', { e: st.elapsedMs, s: st.startedAt });
    ok(st.marks.length === 5 && st.marks[0].status === '완료', 'runStatus: 지시서 탭에 넘길 줄을 모아 둔다', st.marks[0]);
  }

  // 2. 실패하면 그 단계에서 선다 — 판정은 진짜 `stepFailed` 가 한다
  {
    const ctx = bootSandbox(steps);
    const seen = [];
    ctx.runStep = async (n) => { seen.push(n); return n === 3 ? { no: n, bad: ['판매가: not-found'] } : okResult(n); };
    ctx.runAll();
    const st = await waitLoop(ctx);
    ok(st.reason === 'failed' && st.stoppedAt === 3, 'runAll: 실패하면 그 단계에서 선다', { r: st.reason, at: st.stoppedAt });
    ok(seen.join(',') === '1,2,3', 'runAll: 실패 뒤 단계는 부르지 않는다', seen);
    ok(st.cursor.lastDone === 2 && st.cursor.pending === 3, 'runAll: 실패한 단계는 이어서 하기 자리에 남는다', st.cursor);
    ok(ctx.runAll().from === 3, 'runAll: 다시 부르면 실패한 단계부터다', ctx.runStatus().from);
    ctx.runStop();
    await waitLoop(ctx);
  }

  // 3. 옛 화면·금지된 단계(`refused`+`fatal`)는 fatal 로 선다
  {
    const ctx = bootSandbox(steps);
    ctx.runStep = async (n) => (n === 2 ? { no: n, refused: true, fatal: true, error: '금지된 단계' } : okResult(n));
    ctx.runAll();
    const st = await waitLoop(ctx);
    ok(st.reason === 'fatal' && st.stoppedAt === 2, 'runAll: refused+fatal 은 fatal 로 선다', st);
  }

  // 4. 사진 단계는 **파일 다리를 기다리는 넘김**이지 실패가 아니다 — files 로 서고,
  //    파일을 올린 뒤 `runAll()` 을 다시 부르면 그 단계를 `{uploaded:true}` 로 이어 부른다.
  {
    const photoSteps = { guide: {}, steps: [stepOf(1, '룸 만들기'), stepOf(2, '룸 사진 올리기', { photos: ['a.jpg'] }), stepOf(3, '룸 만들기')] };
    const ctx = bootSandbox(photoSteps);
    const calls = [];
    ctx.runStep = async (n, o) => {
      calls.push([n, (o && o.uploaded) ? 'uploaded' : '']);
      if (n === 2 && !(o && o.uploaded)) return { no: n, submitted: false, uploads: ['사진 추가'] };
      return okResult(n);
    };
    ctx.runAll();
    const st1 = await waitLoop(ctx);
    ok(st1.reason === 'files' && st1.stoppedAt === 2, 'runAll: 사진 단계는 files 로 선다(실패가 아니다)', st1.reason);
    ok(st1.cursor.files === 2 && st1.cursor.lastDone === 1, 'runAll: 기다리는 사진 단계를 자리에 적어 둔다', st1.cursor);
    ctx.runAll();                                   // 파일을 다리에 올린 뒤 다시 부른다
    const st2 = await waitLoop(ctx);
    ok(calls.map((c) => c.join('')).join(' ') === '1 2 2uploaded 3',
       'runAll: 같은 사진 단계를 {uploaded:true} 로 한 번만 다시 부른다', calls);
    ok(st2.reason === 'done' && st2.cursor.lastDone === 3, 'runAll: 사진 뒤 단계까지 이어서 끝낸다', st2.cursor);
  }

  // 4b. **룸 사진**에는 누를 저장 버튼이 없다 — 파일을 옮기는 것이 곧 `→ [사진 추가]` 줄의
  //     실행이라, `{uploaded:true}` 로 이어 부르면 도우미가 `submit:'upload-label'` 로 돌려준다.
  //     종전에는 그것을 **또** 「파일 기다림」 으로 읽어 고리가 같은 단계에서 영영 섰고
  //     (`files` → `runAll` → `files` …), 진행 띠는 그 단계를 어느 숫자에도 세지 않은 채
  //     실행 로그·지시서 탭에는 `stepFailed` 가 참이라 **실패**로 적혔다 — 사진은 멀쩡히
  //     올라간 채로(2026-09-22 운영 실행: 66단계 호텔이 `50 완료 / 5 실패` 로 보였다).
  {
    const photoSteps = { guide: {}, steps: [stepOf(1, '룸 만들기'),
      stepOf(2, '룸 사진 올리기', { photos: ['a.jpg'], submit: '사진 추가' }), stepOf(3, '룸 만들기')] };
    const ctx = bootSandbox(photoSteps);
    const calls = [];
    // `runStepCore` 의 규약 그대로 흉내 낸다 — 파일 전에는 기다림, 파일 뒤에는 이미 실행된 줄이다
    ctx.runStep = async (n, o) => {
      calls.push([n, (o && o.uploaded) ? 'uploaded' : '']);
      if (n !== 2) return okResult(n);
      return (o && o.uploaded)
        ? { no: n, submit: 'upload-label', submitted: false, uploadDone: true }
        : { no: n, submit: 'upload-label', submitted: false, waitingFiles: true };
    };
    ctx.runAll();
    const st1 = await waitLoop(ctx);
    ok(st1.reason === 'files' && st1.stoppedAt === 2, 'runAll: 룸 사진도 파일 앞에서는 files 로 선다', st1.reason);
    ctx.runAll();                                   // 파일을 옮긴 뒤 다시 부른다
    const st2 = await waitLoop(ctx);
    ok(calls.map((c) => c.join('')).join(' ') === '1 2 2uploaded 3',
       'runAll: 룸 사진 단계를 {uploaded:true} 로 한 번만 부르고 다음으로 간다', calls);
    ok(st2.reason === 'done' && st2.cursor.lastDone === 3,
       'runAll: 올린 뒤의 `upload-label` 은 끝난 것이다 — 같은 자리에 다시 서지 않는다', st2.cursor);
    ok(ctx.stepFailed({ submit: 'upload-label', submitted: false, uploadDone: true }) === false,
       'stepFailed: 파일을 올린 뒤의 `upload-label` 은 실패가 아니다');
    ok(ctx.stepFailed({ submit: 'upload-label', submitted: false, waitingFiles: true }) === false,
       'stepFailed: 파일을 기다리는 `upload-label` 도 실패가 아니다(넘김이다)');
    ok((ctx.guideMark({ no: 2, submit: 'upload-label', submitted: false, uploadDone: true }) || {}).status === '완료',
       'guideMark: 올린 뒤의 룸 사진 단계는 지시서 탭에 완료로 넘긴다');
    ok(ctx.guideMark({ no: 2, submit: 'upload-label', submitted: false, waitingFiles: true }) === null,
       'guideMark: 아직 파일을 기다리는 단계는 넘기지 않는다 — 완료로 체크하면 안 된다');
  }

  // 5. 화면이 통째로 넘어가는 단계에서 선다(페이지 JS 가 곧 죽는다)
  {
    const ctx = bootSandbox(steps);
    ctx.runStep = async (n) => (n === 2 ? { no: n, submit: 'navigated', submitted: true } : okResult(n));
    ctx.runAll();
    const st = await waitLoop(ctx);
    ok(st.reason === 'navigated' && st.stoppedAt === 2, 'runAll: 화면이 넘어가면 navigated 로 선다', st.reason);
    ok(st.cursor.lastDone === 2, 'runAll: 넘어간 단계는 마친 것으로 적는다 — 다시 부르면 3단계부터다', st.cursor);
    const again = ctx.runAll();
    ok(again.from === 3, 'runAll: 새 화면에서 다시 부르면 그다음 단계부터다', again);
    ctx.runStop(); await waitLoop(ctx);
  }

  // 6. `runStop()` 은 지금 단계까지만 끝내고 선다
  {
    const ctx = bootSandbox(steps);
    const seen = [];
    ctx.runStep = async (n) => { seen.push(n); await new Promise((r) => setTimeout(r, 30)); return okResult(n); };
    ctx.runAll();
    await new Promise((r) => setTimeout(r, 45));
    const s0 = ctx.runStop();
    ok(s0.stopping === true, 'runStop: 멈추라고 적는다', s0);
    const st = await waitLoop(ctx);
    ok(st.reason === 'stopped', 'runStop: 고리가 stopped 로 선다', st.reason);
    ok(seen.length < 5 && seen.length >= 1, 'runStop: 남은 단계는 부르지 않는다', seen);
    ok(ctx.runStop().running === false, 'runStop: 돌고 있지 않으면 그렇다고 말한다', ctx.runStop());
  }

  // 7. [판매 시작] 은 사람이 누른다 — 고리는 그 단계를 열지도 않는다
  {
    const saleSteps = { guide: {}, steps: [stepOf(1, '룸 만들기'), stepOf(2, '판매 시작')] };
    const ctx = bootSandbox(saleSteps);
    const seen = [];
    ctx.runStep = async (n) => { seen.push(n); return okResult(n); };
    ctx.runAll();
    const st = await waitLoop(ctx);
    ok(st.reason === 'sale-start' && st.stoppedAt === 2, 'runAll: [판매 시작] 앞에서 선다', st.reason);
    ok(seen.join(',') === '1', 'runAll: [판매 시작] 단계는 부르지도 않는다', seen);
  }

  // 8. 한 단계가 끝나지 않아도 고리가 매달리지 않는다
  {
    const ctx = bootSandbox(steps);
    ctx.runStep = () => new Promise(() => {});          // 영영 끝나지 않는다
    ctx.runAll({ from: 1, to: 2, stepTimeoutMs: 120 });
    const st = await waitLoop(ctx, 3000);
    ok(st.running === false && st.reason === 'failed', 'runAll: 단계 제한에서 끊고 선다', st.reason);
    ok(st.lastResult && st.lastResult.timeout === true, 'runAll: 끊긴 단계를 timeout 으로 적는다', st.lastResult);
  }

  // 9. `runStep` 이 던져도 고리는 매달리지 않는다
  {
    const ctx = bootSandbox(steps);
    ctx.runStep = async (n) => { if (n === 2) throw new Error('터졌다'); return okResult(n); };
    ctx.runAll();
    const st = await waitLoop(ctx);
    ok(st.reason === 'failed' && /터졌다/.test(String(st.lastResult.error)), 'runAll: 던진 것은 실패로 적는다', st.lastResult);
  }

  // 10. 이미 돌고 있으면 두 번 시작하지 않는다
  {
    const ctx = bootSandbox(steps);
    ctx.runStep = async (n) => { await new Promise((r) => setTimeout(r, 25)); return okResult(n); };
    const a = ctx.runAll();
    const b = ctx.runAll();
    ok(a.started === true && b.started === false && b.running === true, 'runAll: 두 번 부르면 두 번째는 시작하지 않는다', b);
    await waitLoop(ctx);
  }

  // 11. 이어서 하기 자리는 JSON 으로 오간다 — 새 화면에서 부트를 다시 eval 해도 살아 있다
  {
    const ctx = bootSandbox(steps);
    ctx.runStep = async (n) => (n === 3 ? { no: n, submit: 'navigated' } : okResult(n));
    ctx.runAll();
    await waitLoop(ctx);
    const saved = JSON.parse(ctx.localStorage.getItem('stayRunCursor'));
    ok(saved.lastDone === 3 && Array.isArray(saved.results) && saved.results.length === 3,
       '이어서 하기: 단계마다 자리와 결과를 적어 둔다', { lastDone: saved.lastDone, n: saved.results.length });
    ok(saved.results.every((r) => r.fields === undefined && r.drawer === undefined),
       '이어서 하기: DOM 이 실릴 수 있는 칸은 빼고 적는다', saved.results[0]);
    ok(ctx.progressReset && ctx.progressReset() && ctx.localStorage.getItem('stayRunCursor') === null,
       'progressReset: 앞 호텔의 자리를 지운다', ctx.localStorage.getItem('stayRunCursor'));
  }

  // 12. `stayRun` 에도 얹는다 — SKILL.md 가 그 이름으로 적는다
  {
    const ctx = bootSandbox(steps);
    ok(typeof ctx.stayRun.runAll === 'function' && typeof ctx.stayRun.runStatus === 'function' &&
       typeof ctx.stayRun.runStop === 'function', 'stayRun.runAll · runStatus · runStop 이 선다');
  }

  // 13. 지시서 탭에 넘길 줄의 판정 — SKILL.md 「지시서 HTML 탭의 체크」 그대로다
  {
    const ctx = bootSandbox(steps);
    const m = (r) => ctx.guideMark(r);
    ok(m({ no: 1, skipped: true, reason: '이미 있음: 디럭스' }).status === '건너뜀', 'guideMark: skipped → 건너뜀');
    ok(m({ no: 2, bad: ['카드 없음'] }).status === '실패', 'guideMark: bad → 실패');
    ok(m({ no: 3, mismatch: ['판매가'], submitted: false }).status === '확인 필요', 'guideMark: mismatch 만 → 확인 필요');
    ok(m({ no: 4, mismatch: ['판매가'], errors: ['서버 거부'] }).status === '실패', 'guideMark: 다른 실패가 같이 있으면 실패');
    const done = m({ no: 5, submit: 'closed', drawer: { open: false }, modal: { open: false }, mismatchWarn: ['설명'] });
    ok(done.status === '완료' && done.note === '되읽기만', 'guideMark: 되읽기 한계뿐이면 완료 · 되읽기만', done);
  }

  // 14. 0단계 확인이 확인을 못 마쳤으면 **마친 것으로 적지 않는다** — 이어서 할 때 건너뛰면 안 된다
  {
    const checkSteps = { guide: {}, steps: [stepOf(1, '환율 확인'), stepOf(2, '룸 만들기')] };
    const ctx = bootSandbox(checkSteps);
    ctx.onHotelForm = () => true;                       // 폼은 이미 서 있다(다시 부르기가 곧바로 돈다)
    const calls = [];
    ctx.runStep = async (n) => { calls.push(n); return n === 1 ? { no: 1, checked: false, found: [], navigated: true } : okResult(n); };
    ctx.runAll();
    const st = await waitLoop(ctx);
    ok(calls.join(',') === '1,1', '확인 단계: navigated 면 그 자리에서 **한 번만** 다시 부른다', calls);
    ok(st.reason === 'navigated' && st.stoppedAt === 1, '확인 단계: 다시 불러도 navigated 면 그때 선다', { r: st.reason, at: st.stoppedAt });
    ok(st.cursor.pending === 1 && !st.cursor.lastDone, '확인 단계: checked:false 는 자리에 pending 으로 남는다', st.cursor);
    ok(ctx.runAll().from === 1, '확인 단계: 다시 부르면 **그 단계부터** 다시 한다');
    ctx.runStop(); await waitLoop(ctx);
  }

  // 15. 폼이 뜬 뒤 다시 부른 것이 되면 그대로 이어간다(고리가 서지 않는다)
  {
    const checkSteps = { guide: {}, steps: [stepOf(1, '도시 확인'), stepOf(2, '룸 만들기')] };
    const ctx = bootSandbox(checkSteps);
    let formUp = false;
    ctx.onHotelForm = () => formUp;
    setTimeout(() => { formUp = true; }, 60);           // 폼은 조금 뒤에 선다(htmx 로 화면만 갈린다)
    const calls = [];
    ctx.runStep = async (n) => {
      calls.push(n);
      if (n !== 1) return okResult(n);
      return formUp ? { no: 1, checked: true, found: ['도시: 서울'], left: true } : { no: 1, checked: false, found: [], navigated: true };
    };
    ctx.runAll();
    const st = await waitLoop(ctx);
    ok(calls.join(',') === '1,1,2', '확인 단계: 폼이 설 때까지 기다렸다 다시 부르고 이어간다', calls);
    ok(st.reason === 'done' && st.cursor.lastDone === 2, '확인 단계: 확인을 마치면 자리가 올라간다', { r: st.reason, c: st.cursor });
    ok(st.doneCount === 2 && st.results.length === 2, '확인 단계: 다시 부른 것은 한 단계로 센다', { d: st.doneCount, n: st.results.length });
    ok(st.results[0].rerun === true && st.results[0].checked === true, '확인 단계: 마지막 판정 하나만 남는다', st.results[0]);
  }

  // 16. 단계를 시작하기 전에 **조각 다시 그리기**가 끝나기를 기다린다
  //     (알맹이 `runStepCore` 를 가짜로 바꾼다 — 기다림은 껍데기 `runStep` 에 있다)
  {
    const ctx = bootSandbox({ guide: {}, steps: [stepOf(1, '룸 만들기')] });
    const hx = { pending: 1, requests: 9, swaps: 0, settles: 0, unloading: false };
    ctx.__stayRunHtmx = hx;
    const marks = [];
    const t0 = Date.now();
    ctx.runStepCore = async (n) => { marks.push(Date.now() - t0); return okResult(n); };
    setTimeout(() => { hx.pending = 0; }, 120);         // 아홉 벌의 조각이 그때 다 온다
    ctx.runAll();
    const st = await waitLoop(ctx, 5000);
    ok(marks.length === 1 && marks[0] >= 110, '고리: 요청이 빌 때까지 기다렸다 단계를 시작한다', marks);
    ok(st.reason === 'done', '고리: 기다린 뒤 그대로 끝낸다', st.reason);
    ok(st.results[0].waitedMs >= 110, '고리: 기다린 시간을 결과에 적는다', st.results[0].waitedMs);
  }

  // 16b. 돌고 있는 요청이 없으면 **거의 공짜다**(조용한 틱 하나)
  {
    const ctx = bootSandbox({ guide: {}, steps: [stepOf(1, '룸 만들기')] });
    ctx.__stayRunHtmx = { pending: 0, requests: 9, swaps: 3, settles: 3, unloading: false };
    ctx.runStepCore = async (n) => okResult(n);
    const t0 = Date.now();
    ctx.runAll();
    const st = await waitLoop(ctx, 4000);
    ok(st.reason === 'done' && Date.now() - t0 < 300, '고리: 잠잠하면 기다림이 한 틱뿐이다', Date.now() - t0);
  }

  // 17. `runAll({waitMs})` 는 **도우미의 천장**까지 간다 — 느린 서버(로컬)에서 쓴다
  {
    const ctx = bootSandbox(steps);
    ok(!!ctx.__cfg, 'config: 도우미에서 `@config:start`…`@config:end` 를 떼어 냈다');
    ok(ctx.__cfg.waitMs() === 10000, 'config: 기본 천장은 10초 그대로다', ctx.__cfg.waitMs());
    ctx.runStep = async (n) => okResult(n);
    const a = ctx.runAll({ waitMs: 40000 });
    ok(a.started === true && a.waitMs === 40000 && ctx.__cfg.waitMs() === 40000,
       'runAll({waitMs}): 도우미의 `config` 까지 닿는다', { a: a.waitMs, cfg: ctx.__cfg.waitMs() });
    await waitLoop(ctx);
    ok(ctx.runStatus().waitMs === 40000, 'runStatus: 올린 천장을 그대로 보여 준다', ctx.runStatus().waitMs);
    const bad = ctx.runAll({ waitMs: 10 });
    ok(bad.started === false && /1000/.test(String(bad.error)) && ctx.__cfg.waitMs() === 40000,
       'runAll({waitMs}): 너무 작은 값이면 시작하지 않고 값을 지킨다', bad);
  }

  // 18. 「같은 이름이면 건너뜀」 은 **고른 카드 안에서만** 본다 (2026-09-21 실측 결함)
  {
    const ctx = bootSandbox(steps);
    ctx.stayRun.tier = (x, y) => {
      const n = (t) => String(t || '').replace(/\s+/g, '').toLowerCase();
      if (!n(x) || !n(y)) return 0;
      if (n(x) === n(y)) return 4;
      return n(x).indexOf(n(y)) >= 0 ? 2 : 0;
    };
    const row = (t) => ({ innerText: t, querySelector: () => null, closest: () => null });
    const card = (head, rows) => ({
      querySelector: (sel) => (/stay-card__head|stay-card__title/.test(sel) ? { textContent: head } : null),
      querySelectorAll: () => rows.map(row)
    });
    const cards = [card('홀리데이 NRF 2026-12', ['유아  0~3세', '소아  4~11세']), card('기본 오퍼 2026', [])];
    const bodyWith = (list) => ({ querySelectorAll: (sel) => (sel === '.stay-card' ? list : []) });
    ctx.document.body = bodyWith(cards);
    ok(ctx.existsInList('유아', '홀리데이 NRF 2026-12') === true, 'existsInList: 그 카드 안에 있으면 「이미 있음」');
    ok(ctx.existsInList('유아', '기본 오퍼 2026') === false, 'existsInList: **옆 카드**의 행은 건너뛸 근거가 아니다');
    ok(ctx.existsInList('유아', '아직 안 그려진 오퍼') === false,
       'existsInList: 카드를 못 찾으면 「없음」 이다 — 탭 전체로 넓혀 보지 않는다');
    // 카드가 늦게 그려지면 기다렸다 본다(요청이 도는 사이에 「없음」 으로 읽고 또 만들지 않는다)
    ctx.document.body = bodyWith([]);
    setTimeout(() => { ctx.document.body = bodyWith([card('늦은 오퍼', ['유아  0~3세'])]); }, 80);
    const tL = Date.now();
    const late = await ctx.existsInListWait('유아', '늦은 오퍼', null, 1500);
    ok(late === true && Date.now() - tL >= 70, 'existsInListWait: 카드가 늦게 그려지면 기다렸다 본다', { late, ms: Date.now() - tL });
    ctx.document.body = bodyWith(cards);
    const tQ = Date.now();
    ok((await ctx.existsInListWait('없는 이름', '홀리데이 NRF 2026-12', null, 1500)) === false && Date.now() - tQ < 200,
       'existsInListWait: 카드가 이미 있으면 기다리지 않는다', Date.now() - tQ);
  }

  console.log('  — 고리 시험 ' + pass + ' 통과 · ' + fail + ' 실패\n');
}

await loopTests();

let JSDOM = null;
try { ({ JSDOM } = require('jsdom')); } catch (e) {
  console.log('SKIP — jsdom 이 없어 화면 시험(가격 셀·열기·거부·0단계 확인)은 건너뜁니다 (설치하지 않습니다).');
  process.exit(fail ? 1 : 0);
}

const STEPS = {
  guide: { title: '시험 호텔' },
  steps: [
    {
      no: 1,
      title: '가격 셀 만들기 (2026-01-01)',
      kind: '가격 셀 만들기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원별 가격 추가', buttons: [], buttons_parsed: [] },
      fields: [
        { label: '판매가', kind: 'typed', value: '120' },
        { label: '정가', kind: 'typed', value: '150' },
        { label: '공급 원가', kind: 'typed', value: '90' }
      ],
      longtexts: [], photos: [], submit: '추가'
    },
    {
      no: 2,
      title: '가격 셀 만들기 (2026-01-02)',
      kind: '가격 셀 만들기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원 조합 2 행', buttons: [], buttons_parsed: [] },
      fields: [{ label: '판매가', kind: 'typed', value: '200' }],
      longtexts: [], photos: [], submit: '추가'
    },
    {
      // 2026-09-08 에 화면의 카드 이름이 `인원별 가격 추가` → `인원별 · 박수별 가격 추가` 로
      // 바뀌었다(박수 축이 돌아오면서 제목이 두 축을 함께 부른다). 지시서는 사전의 글자를
      // 그대로 쓰므로 새 원고는 긴 이름으로 온다 — 옛 이름만 읽으면 그 단계가 통째로 멈춘다.
      no: 3,
      title: '가격 셀 만들기 (2026-01-01)',
      kind: '가격 셀 만들기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원별 · 박수별 가격 추가', buttons: [], buttons_parsed: [] },
      fields: [{ label: '판매가', kind: 'typed', value: '130' }],
      longtexts: [], photos: [], submit: '추가'
    },
    {
      // 규칙서가 새 행 단계의 카드 줄을 `… 의 인원별 · 박수별 가격 추가` 로 쓰라고 한다 — 그 꼴은
      // 카드에 좌표가 없으므로 `인원 조합` 칸이 좌표를 정해야 한다. 종전에는 무조건 `무관` 으로
      // 굳어, 칸에 `A2` 를 적어도 아무도 팔지 않는 좌표가 생겼다.
      no: 4,
      title: '가격 셀 만들기 (2026-01-02)',
      kind: '가격 셀 만들기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원별 · 박수별 가격 추가', buttons: [], buttons_parsed: [] },
      fields: [
        { label: '인원 조합', kind: 'select', value: '선택: A2 · 성인 2' },
        { label: '판매가', kind: 'typed', value: '140' }
      ],
      longtexts: [], photos: [], submit: '추가'
    },
    {
      // 2026-09-09 배포판: 셀이 있는 날의 위 표는 **좌표 묶음**이다. `A2` 묶음의 둘째 층은
      // `인원 조합` 칸이 `rowspan` 에 덮여 `<td>` 가 하나 적다 — 자리로 세면 `판매가` 에 적을
      // 값이 `정가` 칸에 들어간다. 층을 안 고르면 첫 층(1박~)을 덮는다.
      no: 5,
      title: '가격 셀 손으로 고치기 (2026-01-03)',
      kind: '가격 셀 손으로 고치기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원 조합 A2 행', buttons: [], buttons_parsed: [] },
      fields: [
        // 규칙서(MANUAL-SPEC §가격 셀)가 기존 행 단계에도 이 줄을 적으라고 한다. 화면의 그
        // 열에는 채울 칸이 없으므로(그룹 머리 글자 + 행마다 hidden) **입력이 아니라 좌표
        // 대조 정보**다 — 칸으로 찾으면 늘 `not-found` 가 되어 이 단계가 저장까지 못 갔다.
        { label: '인원 조합', kind: 'typed', value: 'A2' },
        { label: '박수~', kind: 'typed', value: '3' },
        { label: '판매가', kind: 'typed', value: '95' }
      ],
      longtexts: [], photos: [], submit: '저장'
    },
    {
      // 같은 카드인데 `박수~` 를 안 부르면 종전대로 첫 층(1박~)이다.
      no: 6,
      title: '가격 셀 고치기 (2026-01-03)',
      kind: '가격 셀 고치기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원 조합 A2 행', buttons: [], buttons_parsed: [] },
      fields: [{ label: '판매가', kind: 'typed', value: '125' }],
      longtexts: [], photos: [], submit: '저장'
    },
    {
      // 인원 무관 묶음 — 층이 하나라 `rowspan="1"` 이다. 그룹 머리 글자로 잡힌다.
      no: 7,
      title: '가격 셀 고치기 (2026-01-03)',
      kind: '가격 셀 고치기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원 무관 단일가 행', buttons: [], buttons_parsed: [] },
      fields: [{ label: '판매가', kind: 'typed', value: '111' }],
      longtexts: [], photos: [], submit: '저장'
    },
    {
      // 2026-01-04 는 `인원 무관 / 1박 / 110` **한 행뿐**인 날이다. 여기에 3박 층을 다는
      // 단계다 — 층은 좌표의 일부라 새 좌표를 만드는 일이고, 그래서 **새 행 표**로 가야 한다.
      // 종전에는 "행이 하나뿐" 이라는 이유로 그 1박 행을 잡아 110 을 111 로 덮었다.
      no: 8,
      title: '가격 셀 만들기 (2026-01-04)',
      kind: '가격 셀 만들기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원별 · 박수별 가격 추가', buttons: [], buttons_parsed: [] },
      fields: [
        { label: '박수~', kind: 'typed', value: '3' },
        { label: '판매가', kind: 'typed', value: '111' }
      ],
      longtexts: [], photos: [], submit: '추가'
    },
    {
      // 같은 날·같은 값인데 제목이 **기존 행을 고치는 단계**다. 그 층이 화면에 없으므로
      // 고칠 행이 없다 — 다른 층을 대신 덮지 말고 멈춰야 한다.
      no: 9,
      title: '가격 셀 손으로 고치기 (2026-01-04)',
      kind: '가격 셀 손으로 고치기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원 무관 단일가 행', buttons: [], buttons_parsed: [] },
      fields: [
        { label: '박수~', kind: 'typed', value: '3' },
        { label: '판매가', kind: 'typed', value: '111' }
      ],
      longtexts: [], photos: [], submit: '저장'
    },
    {
      // `인원 조합` 줄이 화면의 좌표와 다르다 — 그대로 저장하면 **다른 좌표**를 덮는다.
      no: 10,
      title: '가격 셀 손으로 고치기 (2026-01-03)',
      kind: '가격 셀 손으로 고치기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원 조합 A2 행', buttons: [], buttons_parsed: [] },
      fields: [
        { label: '인원 조합', kind: 'typed', value: 'A2C1_CHD' },
        { label: '판매가', kind: 'typed', value: '999' }
      ],
      longtexts: [], photos: [], submit: '저장'
    },
    {
      // 화면 배지 글자를 그대로 옮겨 적은 원고 — 파서가 벗기지만 옛 산출물에는 남아 있다.
      // 종전에는 비숫자라며 층 조건을 조용히 버리고 첫 층을 덮었다.
      no: 11,
      title: '가격 셀 손으로 고치기 (2026-01-03)',
      kind: '가격 셀 손으로 고치기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원 조합 A2 행', buttons: [], buttons_parsed: [] },
      fields: [
        { label: '박수~', kind: 'typed', value: '세 밤' },
        { label: '판매가', kind: 'typed', value: '999' }
      ],
      longtexts: [], photos: [], submit: '저장'
    },
    {
      // 셀렉트 칸을 **항목 글자 그대로** 적은 원고(`선택: 판매`). 파서는 `선택:` 을 벗겨 두지만
      // 손으로 만든 원고·옛 산출물에는 그대로 남아 있고, 러너의 `keyOfValue` 도 그 꼴을
      // 벗기려고 있다. 칸 채우기 고리만 그 꼴을 못 읽어 멀쩡한 항목을 `not-found` 로 적었다.
      no: 12,
      title: '가격 셀 만들기 (2026-01-02)',
      kind: '가격 셀 만들기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원별 · 박수별 가격 추가', buttons: [], buttons_parsed: [] },
      fields: [
        { label: '상태', kind: 'select', value: '선택: 판매' },
        { label: '판매가', kind: 'typed', value: '160' }
      ],
      longtexts: [], photos: [], submit: '추가'
    },
    {
      // 그러면서도 **진짜 없는 값**은 여전히 `not-found` 여야 한다 — 느슨해진 맞추기가
      // 아무 항목이나 고르면 화면에 없는 값이 조용히 다른 항목으로 저장된다.
      no: 13,
      title: '가격 셀 만들기 (2026-01-02)',
      kind: '가격 셀 만들기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원별 · 박수별 가격 추가', buttons: [], buttons_parsed: [] },
      fields: [
        { label: '상태', kind: 'select', value: '선택: 없는 상태' },
        { label: '판매가', kind: 'typed', value: '161' }
      ],
      longtexts: [], photos: [], submit: '추가'
    },
    {
      // 새 행의 `인원 조합` 셀렉트를 **항목 값이 아니라 항목 글자**로만 맞춰야 하는 판.
      // 화면이 항목 값에 내부 번호를 싣고 좌표는 글자에만 두면(`<option value="77">A2 · 성인 2`),
      // 값끼리 견주는 갈래는 `A2` 를 못 찾아 "목록에 `A2` 이(가) 없습니다" 로 단계를 세운다 —
      // 화면에는 `A2 · 성인 2` 가 버젓이 있는데도.
      no: 14,
      title: '가격 셀 만들기 (2026-01-02)',
      kind: '가격 셀 만들기',
      head: { tab: '가격 캘린더', card: '2026 계약 · Single × 기본 요금제 의 인원 조합 A2 행', buttons: [], buttons_parsed: [] },
      fields: [{ label: '판매가', kind: 'typed', value: '170' }],
      longtexts: [], photos: [], submit: '추가'
    }
  ]
};

//: 룸 사진 올리기 — 마지막 줄이 `→ [사진 추가]` 인 단계. `버튼:` 줄은 룸 행의 [편집] 하나뿐이다.
// 기본정보 탭의 이미지 모달 단계(`대표이미지 올리기`) — 여는 버튼이 [이미지 직접등록] 이고
// 저장은 모달 헤더 [저장] 이다. 한 번에 한 장이라 같은 단계를 장수만큼 다시 부른다.
const IMAGE_STEPS = {
  guide: { title: '시험 호텔' },
  steps: [{
    no: 1,
    title: '대표이미지 올리기 (1장)',
    kind: '대표이미지 올리기',
    head: {
      tab: '기본정보', card: '대표이미지', block: null, screen: null,
      notice: null,
      buttons: ['[이미지 직접등록]'],
      buttons_parsed: [{ raw: '[이미지 직접등록]', text: '이미지 직접등록', row: null, card: null, group: null, drawer: false, times: 1 }]
    },
    fields: [{ label: '이미지설명(Alt)', kind: 'typed', value: '호텔 외관' }],
    longtexts: [],
    photos: [{ file: 'hotel_01.jpg', source: null }],
    submit: '저장'
  }]
};

//: CSRF 403 재시도 — 룸 드로어의 [저장] 하나만 있는 단계다(칸은 보지 않는다).
const CSRF_STEPS = {
  guide: { title: '시험 호텔' },
  steps: [{
    no: 1,
    title: '룸 고치기 (스탠다드)',
    kind: '룸 고치기',
    head: {
      tab: '객실', card: '객실 (룸 타입)', block: null, screen: null, notice: null,
      buttons: ['`스탠다드` 행의 [편집]'],
      buttons_parsed: [{ raw: '`스탠다드` 행의 [편집]', text: '편집', row: '스탠다드', card: null, group: null, drawer: false, times: 1 }]
    },
    fields: [], longtexts: [], photos: [], submit: '저장'
  }]
};

const PHOTO_STEPS = {
  guide: { title: '시험 호텔' },
  steps: [{
    no: 1,
    title: '룸 사진 올리기 (1번째, 스탠다드)',
    kind: '룸 사진 올리기',
    head: {
      tab: '객실', card: '객실 (룸 타입)', block: null, screen: null,
      notice: '파일을 고르면 바로 올라간다 — 드로어 아래 [저장] 은 누르지 않는다.',
      buttons: ['`스탠다드` 행의 [편집]'],
      buttons_parsed: [{ raw: '`스탠다드` 행의 [편집]', text: '편집', row: '스탠다드', card: null, group: null, drawer: false, times: 1 }]
    },
    fields: [], longtexts: [],
    photos: [{ file: 'room_01.jpg', source: null }],
    submit: '사진 추가'
  }]
};

//: 연령 구간 만들기 — 여는 버튼이 `연령 구간 추가` 다. 글자가 `구간 추가` 로 끝나지만
//: 반복 행 추가가 아니라 **드로어를 여는 버튼**이라, 행 추가 낱말로 거르면 드로어가 안 열린다.
const AGE_STEPS = {
  guide: { title: '시험 호텔' },
  steps: [{
    no: 1,
    title: '연령 구간 만들기 (1번째, 초등학생)',
    kind: '연령 구간 만들기',
    head: {
      tab: '오퍼', card: '2027 계약', block: null, screen: null,
      buttons: ['`2027 계약` 묶음의 [연령 구간 추가]'],
      buttons_parsed: [{ raw: '`2027 계약` 묶음의 [연령 구간 추가]', text: '연령 구간 추가', row: null, card: '2027 계약', group: null, drawer: false, times: 1 }]
    },
    fields: [
      { label: '밴드 코드', kind: 'typed', value: 'CHILD' },
      { label: '노출명', kind: 'typed', value: '초등학생' },
      { label: '최소 연령', kind: 'typed', value: '6' },
      { label: '최대 연령', kind: 'typed', value: '11.99' },
      { label: '요금 기준 유형', kind: 'select', value: '성인 요금의 %' },
      { label: '요금 기준 값', kind: 'typed', value: '50' }
    ],
    longtexts: [], photos: [], submit: '추가'
  }, {
    no: 2,
    title: '경고 넘어가기 (오퍼에 취소정책이 없습니다)',
    kind: '경고 넘어가기',
    head: { tab: null, card: null, block: null, screen: null, buttons: [], buttons_parsed: [] },
    fields: [{ label: '사유', kind: 'typed', value: '계약서에 없음' }],
    longtexts: [], photos: [], submit: '넘어가기'
  }, {
    //: 화면에 없는 카드를 가리키는 단계 — 열지 못하고 실패로 끝난다(진행 표시 띠가 실패로 세는지 본다)
    no: 3,
    title: '오퍼 만들기 (없는 카드)',
    kind: '오퍼 만들기',
    head: {
      tab: null, card: '있지도 않은 카드', block: null, screen: null,
      buttons: ['`있지도 않은 카드` 묶음의 [있지도 않은 버튼]'],
      buttons_parsed: [{ raw: '`있지도 않은 카드` 묶음의 [있지도 않은 버튼]', text: '있지도 않은 버튼', row: null, card: '있지도 않은 카드', group: null, drawer: false, times: 1 }]
    },
    fields: [{ label: '이름', kind: 'typed', value: '없는오퍼' }],
    longtexts: [], photos: [], submit: '저장'
  }]
};

//: 0단계 확인 — [호텔 만들기] 폼의 목록에 값이 뜨는지만 보고 `→ [목록]` 으로 돌아온다. 저장이 없다.
const CHECK_STEPS = {
  guide: { title: '시험 호텔' },
  steps: [
    {
      no: 1, title: '환율 확인', kind: '환율 확인',
      head: { tab: null, card: null, block: null, screen: '왼쪽 메뉴 `자유여행` → `상품관리` → 목록 위 [호텔 만들기]', buttons: [], buttons_parsed: [] },
      fields: [{ label: '공급 통화', kind: 'select', value: 'JPY' }], longtexts: [], photos: [], submit: '목록'
    },
    {
      no: 2, title: '거래처 확인 (없는 거래처)', kind: '거래처 확인',
      head: { tab: null, card: null, block: null, screen: '왼쪽 메뉴 `자유여행` → `상품관리` → 목록 위 [호텔 만들기]', buttons: [], buttons_parsed: [] },
      fields: [{ label: '거래처', kind: 'select', value: '없는거래처' }], longtexts: [], photos: [], submit: '목록'
    },
    {
      no: 3, title: '도시 확인', kind: '도시 확인',
      head: { tab: null, card: null, block: null, screen: '왼쪽 메뉴 `자유여행` → `상품관리` → 목록 위 [호텔 만들기]', buttons: [], buttons_parsed: [] },
      fields: [{ label: '도시', kind: 'select', value: '도쿄(TYO)' }], longtexts: [], photos: [], submit: '목록'
    }
  ]
};

//: [호텔 만들기] 단계 — 0단계 확인과 같은 폼에서 값을 채우고 저장한다.
const HOTEL_STEPS = {
  guide: { title: '시험 호텔' },
  steps: [
    {
      no: 1, title: '호텔 만들기 (시험 호텔)', kind: '호텔 만들기',
      head: { tab: null, card: null, block: null, screen: '왼쪽 메뉴 `자유여행` → `상품관리` → 목록 위 [호텔 만들기]', buttons: [], buttons_parsed: [] },
      fields: [
        { label: '호텔명', kind: 'typed', value: '시험 호텔' },
        { label: '도시', kind: 'select', value: '도쿄(TYO)' },
        { label: '공급 통화', kind: 'select', value: 'JPY' },
        { label: '거래처', kind: 'select', value: '자사' }
      ],
      longtexts: [], photos: [], submit: '호텔 만들기'
    }
  ]
};

//: [호텔 만들기] 폼 — 목록 화면에서 [호텔 만들기] 로 들어간 전체 화면 폼이다(저장 버튼은 [호텔 만들기] 하나).
const CREATE_FORM_HTML = `<!doctype html><html lang="ko"><body>
  <div class="erp_cont_head"><h4>호텔 만들기</h4></div>
  <form>
    <table class="bs-table"><tbody>
      <tr><th>호텔명</th><td><input type="text" name="title"></td></tr>
      <tr><th>도시</th><td><select class="browser-default" name="city">
        <option value="">선택</option><option value="1">도쿄(TYO)</option><option value="2">오사카(OSA)</option></select></td></tr>
      <tr><th>공급 통화</th><td><select class="browser-default" name="currency">
        <option value="">선택</option><option value="JPY">JPY</option><option value="USD">USD</option></select></td></tr>
      <tr><th>거래처</th><td><select class="browser-default" name="vendor">
        <option value="">선택</option><option value="9">자사</option></select></td></tr>
    </tbody></table>
    <button type="button">목록</button>
    <button type="button">호텔 만들기</button>
  </form>
</body></html>`;

const dom = new JSDOM(readFileSync(join(here, 'calendar_fixture.html'), 'utf8'), {
  url: 'https://example.test/stay/43900/#stay_tab_calendar',
  runScripts: 'dangerously',
  pretendToBeVisual: true
});
const win = dom.window;
win.localStorage.setItem('staySteps', JSON.stringify(STEPS));
win.eval(readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8'));
win.eval(readFileSync(join(here, '..', 'scripts', 'stay_boot.js'), 'utf8'));

const run = async () => {
  console.log('stay_boot 시험 (가격 캘린더)');

  ok(win.checkGuide().length === 0, 'checkGuide: 새 화면 기준 지시서는 걸리지 않는다', win.checkGuide());

  // 1) 셀이 하나도 없는 날짜 — 표가 하나뿐이고 인원 칸이 셀렉트다
  const r1 = await win.runCellStep(1);
  ok(!r1.error, 'runCellStep: 셀이 없는 날짜에서도 새 행을 찾는다', r1.error);
  ok(r1.newRow === true, 'runCellStep: 새 행으로 잡는다', r1);
  ok(r1.display === '싱글룸', 'runCellStep: 룸 이름을 오퍼별 표시명으로 바꿔 읽는다', r1.display);
  ok(r1.month === '2026-01', 'runCellStep: 달이 맞다', r1.month);
  ok((r1.bad || []).length === 0, 'runCellStep: 못 찾은 칸이 없다', r1.bad);
  ok(r1.occSet === '', 'runCellStep: 인원 무관은 셀렉트의 빈 값이다', r1.occSet);
  ok(r1.saveAs === '추가', 'runCellStep: 새 행의 저장 버튼은 [추가] 다', r1.saveAs);
  ok(r1.submitted === true && r1.submit === 'settled', 'runCellStep: 저장까지 갔다', { s: r1.submitted, r: r1.submit });

  // 2) 인원 조합이 있는 카드 — 셀렉트에서 그 키를 고른다
  const r2 = await win.runCellStep(2, { dry: true });
  ok(!r2.error, 'runCellStep: 인원 조합 카드도 새 행으로 잡는다', r2.error);
  ok(r2.want.occ === '2', 'runCellStep: 카드에서 인원 조합을 읽는다', r2.want);
  ok(r2.occSet === '2', 'runCellStep: 새 행의 인원 셀렉트를 그 조합으로 맞춘다', r2.occSet);

  // 2-b) 새 카드 이름(`인원별 · 박수별 가격 추가`) — 2026-09-08 화면 변경. 두 표기를 다 받는다.
  const r2b = await win.runCellStep(3, { dry: true });
  ok(!r2b.error, 'runCellStep: 새 카드 이름 `인원별 · 박수별 가격 추가` 도 읽는다', r2b.error);
  ok(r2b.newRow === true, 'runCellStep: 새 카드 이름도 새 행으로 잡는다', r2b);
  ok(r2b.want && r2b.want.ratePlan === '기본 요금제',
     'runCellStep: 새 카드 이름에서 요금제를 그대로 읽는다', r2b.want);
  ok(r2b.want.occ === '무관',
     'runCellStep: 좌표를 안 부르는 카드 + 인원 조합 칸 없음 → 무관', r2b.want);

  // 2-c) 같은 카드 꼴이지만 `인원 조합` 칸이 좌표를 준다 — 칸이 이겨야 한다.
  const r2c = await win.runCellStep(4, { dry: true });
  ok(!r2c.error, 'runCellStep: 새 행 카드 + 인원 조합 칸도 읽는다', r2c.error);
  ok(r2c.want && r2c.want.occ === 'A2',
     'runCellStep: 카드가 좌표를 안 부르면 `인원 조합` 칸(`선택: A2 · 성인 2`)에서 읽는다', r2c.want);
  //      그리고 **그 칸을 못 찾은 칸으로 세지 않는다.** 셀렉트를 이미 `A2` 로 맞춰 놓고도
  //      칸 채우기 고리가 글자(`선택: A2 · 성인 2`)를 항목(`A2 · 성인 2`)과 맞추지 못해
  //      `not-found` 를 적으면, `bad` 가 차서 그 단계는 **저장까지 못 간다** — 값은 이미
  //      맞는데 러너만 못 찾았다고 하는 자리다(2026-09-22 운영 실행에서 가격 셀 3단계).
  ok((r2c.bad || []).length === 0,
     'runCellStep: 이미 맞춘 `인원 조합` 을 not-found 로 세지 않는다', r2c.bad);
  ok(((r2c.fields || []).find((f) => f.label === '인원 조합') || {}).status === 'ok',
     'runCellStep: 항목 글자(`A2 · 성인 2`)로 적은 값도 그 항목에 닿는다', r2c.fields);
  ok(r2c.occSet === 'A2', 'runCellStep: 새 행 셀렉트가 그 좌표로 서 있다', r2c.occSet);

  // 2-c-2) 같은 일이 `인원 조합` 만의 것이 아니다 — 아무 셀렉트 칸이나 항목 글자 그대로 적으면
  //        (`선택: 판매`) 종전 맞추기는 멀쩡한 항목을 `not-found` 로 적었다.
  const rsel = await win.runCellStep(12, { dry: true });
  ok((rsel.bad || []).length === 0, 'runCellStep: `선택: 판매` 를 not-found 로 세지 않는다', rsel.bad);
  ok(((rsel.fields || []).find((f) => f.label === '상태') || {}).detail === '판매',
     'runCellStep: 그 항목을 골랐다', rsel.fields);

  // 2-c-3) 그러면서도 **진짜 없는 값**은 그대로 not-found 다 — 느슨해진 맞추기가 아무 항목이나
  //        고르면 화면에 없는 값이 조용히 다른 항목으로 저장된다.
  const rselx = await win.runCellStep(13, { dry: true });
  ok((rselx.bad || []).some((b) => /^상태: not-found/.test(b)),
     'runCellStep: 화면에 없는 값은 그대로 not-found 다', rselx.bad);

  // 2-c-4) 새 행의 `인원 조합` 이 항목 **값**에는 내부 번호를, 글자에만 좌표를 싣는 판.
  //        값끼리만 견주면 `A2 · 성인 2` 가 화면에 버젓이 있는데도 "목록에 `A2` 이(가) 없습니다" 로 선다.
  {
    const CELL_EDIT_ORIG = win.CELL_EDIT;
    win.CELL_EDIT = CELL_EDIT_ORIG.replace('value="A2">', 'value="77">');
    const rkey = await win.runCellStep(14, { dry: true });
    ok(!rkey.error, 'runCellStep: 항목 글자에만 좌표가 있어도 그 항목을 찾는다', rkey.error);
    ok(rkey.occSet === '77', 'runCellStep: 화면이 쓰는 항목 값으로 맞춘다', rkey.occSet);
    win.CELL_EDIT = CELL_EDIT_ORIG;
  }

  // 2-d) 좌표 묶음(2026-09-09 배포판) — `A2` 묶음의 둘째 층은 `인원 조합` 칸이 rowspan 에
  //      덮여 `<td>` 가 하나 적다. 자리로 세면 `판매가` 값이 `정가` 칸에 들어간다.
  const rg3 = await win.runCellStep(5, { dry: true });
  ok(!rg3.error, 'runCellStep: 좌표 묶음 표에서도 행을 찾는다', rg3.error);
  ok(rg3.newRow !== true, 'runCellStep: 이미 있는 좌표는 기존 행이다', rg3);
  ok(rg3.wantLos === '3', 'runCellStep: 카드가 아니라 `박수~` 칸에서 층을 읽는다', rg3.wantLos);
  ok((rg3.bad || []).length === 0, 'runCellStep: 묶음 둘째 층에서도 못 찾은 칸이 없다', rg3.bad);
  {
    const row = win.document.getElementById('cell_row_102');
    const v = (n) => row.querySelector('[name=' + n + ']').value;
    ok(v('price') === '95', 'runCellStep: rowspan 에 덮인 층에도 `판매가` 를 제 칸에 넣는다', v('price'));
    ok(v('original_price') === '150', 'runCellStep: 옆 칸(`정가`)을 덮어쓰지 않았다', v('original_price'));
    ok(v('los_nights') === '3', 'runCellStep: 그 층의 `박수~` 는 그대로다', v('los_nights'));
    const first = win.document.getElementById('cell_row_101');
    ok(first.querySelector('[name=price]').value === '120',
       'runCellStep: 층을 골랐으므로 첫 층(1박~)은 손대지 않았다', first.querySelector('[name=price]').value);
  }

  // 2-e) `박수~` 를 안 부르면 종전대로 첫 층이다.
  const rg1 = await win.runCellStep(6, { dry: true });
  ok(rg1.wantLos === null, 'runCellStep: `박수~` 칸이 없으면 층을 고르지 않는다', rg1.wantLos);
  ok(win.document.getElementById('cell_row_101').querySelector('[name=price]').value === '125',
     'runCellStep: 층을 안 고르면 묶음의 첫 층에 넣는다');

  // 2-f) 인원 무관 묶음 — 층이 하나라 rowspan="1" 이다.
  const rgu = await win.runCellStep(7, { dry: true });
  ok(!rgu.error, 'runCellStep: 인원 무관 묶음도 찾는다', rgu.error);
  ok(win.document.getElementById('cell_row_103').querySelector('[name=price]').value === '111',
     'runCellStep: 인원 무관 묶음의 `판매가` 를 제 칸에 넣는다');

  // 2-g) 저장 거부는 `.stay-banner--blocking` 배너 한 줄로 돌아온다 — 이 표는 필드 오류를
  //      칸 옆에 못 두고 한 배너에 모은다. 안 읽으면 `errors: []` 로 저장된 줄처럼 보고된다.
  win.__refuseNextSave = true;
  const rgx = await win.runCellStep(7);
  ok(rgx.submitted === true, 'runCellStep: 저장을 눌렀다', rgx.submitted);
  ok(rgx.submit === 'refused', 'runCellStep: 배너가 서면 거부로 읽는다', rgx.submit);
  ok((rgx.errors || []).some((e) => /같은 인원 조합의 가격 행이 이미 있습니다/.test(e)),
     'runCellStep: 거부 문구를 errors 로 돌려준다', rgx.errors);

  // 2-h) 되읽기 — 인원 조합이 hidden 이라도 좌표를 읽어야 한다(안 읽으면 after 가 통째로 빈다).
  win.openCell(3);
  await win.stayRun.sleep(50);
  const rgb = await win.runCellStep(6);
  ok((rgb.after || []).length > 0, 'runCellStep: 숨은 `인원 조합` 칸으로도 되읽는다', rgb.after);
  ok((rgb.after || []).every((x) => x.indexOf('occupancy_key=A2 ') === 0),
     'runCellStep: 되읽기가 그 좌표의 층만 담는다', rgb.after);

  // 2-i) 규칙서대로 `인원 조합` 줄을 적은 기존 행 단계 — 그 줄은 입력이 아니라 좌표 대조다.
  //      칸으로 찾으면 늘 `not-found` 라 저장까지 못 갔다(2026-09-09 Codex 지적 [차단 2]).
  const rocc = await win.runCellStep(5, { dry: true });
  ok(!rocc.error, 'runCellStep: `인원 조합` 줄이 있는 기존 행 단계도 읽는다', rocc.error);
  ok((rocc.bad || []).length === 0,
     'runCellStep: `인원 조합` 줄을 not-found 로 세지 않는다', rocc.bad);
  ok((rocc.fields || []).some((f) => f.label === '인원 조합' && f.status === 'ok' && /좌표 대조/.test(f.detail || '')),
     'runCellStep: `인원 조합` 은 hidden 좌표와 대조만 한다', rocc.fields);
  ok(win.document.getElementById('cell_row_102').querySelector('[name=price]').value === '95',
     'runCellStep: 대조가 맞으면 그 층에 값을 넣는다');

  // 2-j) 대조가 어긋나면 **다른 좌표를 덮지 않고** 멈춘다.
  const rbadocc = await win.runCellStep(10);
  ok(rbadocc.refused === true, 'runCellStep: `인원 조합` 이 화면 좌표와 다르면 거부한다', rbadocc);
  ok(/A2C1_CHD/.test(rbadocc.error || '') && /A2/.test(rbadocc.error || ''),
     'runCellStep: 원고 값과 화면 값을 함께 알려 준다', rbadocc.error);
  ok(rbadocc.submitted === false, 'runCellStep: 거부한 단계는 저장하지 않는다', rbadocc.submitted);
  ok(win.document.getElementById('cell_row_101').querySelector('[name=price]').value !== '999',
     'runCellStep: 거부한 단계는 화면 값을 바꾸지 않는다');

  // 2-k) 못 읽는 `박수~` — 조용히 첫 층을 덮지 않고 멈춘다.
  const rlosbad = await win.runCellStep(11);
  ok(rlosbad.refused === true, 'runCellStep: 숫자가 아닌 `박수~` 는 거부한다', rlosbad);
  ok(win.document.getElementById('cell_row_101').querySelector('[name=price]').value !== '999',
     'runCellStep: 그 단계도 화면 값을 바꾸지 않는다');

  // 2-l) [차단 1] 층 추가가 기존 1박 행을 덮지 않는다.
  //      2026-01-04 는 `인원 무관 / 1박 / 110` 한 행뿐인 날이다. `박수~=3, 판매가=111` 을
  //      적으면 종전에는 "행이 하나뿐" 폴백이 그 1박 행을 잡아 110 을 111 로 덮었다.
  const rnew = await win.runCellStep(8, { dry: true });
  ok(!rnew.error, 'runCellStep: 한 행뿐인 날에 새 층을 다는 단계도 읽는다', rnew.error);
  ok(rnew.wantLos === '3', 'runCellStep: 층을 읽는다', rnew.wantLos);
  ok(rnew.newRow === true, 'runCellStep: 없는 층은 **새 행 표**로 간다 — 기존 행이 아니다', rnew);
  {
    const one = win.document.getElementById('cell_row_201');
    ok(one.querySelector('[name=price]').value === '110',
       'runCellStep: 기존 1박 행의 판매가가 그대로다', one.querySelector('[name=price]').value);
    ok(one.querySelector('[name=los_nights]').value === '1',
       'runCellStep: 기존 1박 행의 박수도 그대로다', one.querySelector('[name=los_nights]').value);
    const add = win.document.querySelector('#stay_cell_edit input[type=hidden][name=date]').closest('table');
    ok(add.querySelector('[name=los_nights]').value === '3',
       'runCellStep: 새 행에 층을 넣었다', add.querySelector('[name=los_nights]').value);
    ok(add.querySelector('[name=price]').value === '111',
       'runCellStep: 새 행에 판매가를 넣었다', add.querySelector('[name=price]').value);
  }
  const rnew2 = await win.runCellStep(8);
  ok(rnew2.saveAs === '추가', 'runCellStep: 새 행이므로 [추가] 를 누른다', rnew2.saveAs);
  ok(rnew2.submitted === true && rnew2.submit === 'settled',
     'runCellStep: 새 행 저장까지 갔다', { s: rnew2.submitted, r: rnew2.submit });

  // 2-m) 같은 값인데 제목이 **기존 행을 고치는 단계**면 고칠 행이 없으므로 멈춘다.
  const rmiss = await win.runCellStep(9);
  ok(rmiss.refused === true, 'runCellStep: 없는 층을 고치라는 단계는 거부한다', rmiss);
  ok(/박수~ 3/.test(rmiss.error || '') && /가격 셀 만들기/.test(rmiss.error || ''),
     'runCellStep: 왜 멈췄고 원고를 어떻게 고칠지 알려 준다', rmiss.error);
  ok(win.document.getElementById('cell_row_201').querySelector('[name=price]').value === '110',
     'runCellStep: 거부해도 기존 1박 행은 그대로다');

  // 2-n) 실패 판정 — `error` · `errors` · `mismatch` · 드로어가 남은 `stayed` 를 다 실패로 본다.
  //      종전에는 셋 다 안 봐서, 시즌 거부 배너를 모아 놓고도 그 단계를 완료로 셌다.
  ok(win.stepFailed({ error: '날짜 칸 편집창이 열리지 않았습니다' }) === true,
     'stepFailed: `error` 는 실패다');
  ok(win.stepFailed({ submit: 'stayed', errors: ['전개 날짜가 0일입니다'] }) === true,
     'stepFailed: 서버가 거부한 사유(`errors`)는 실패다');
  ok(win.stepFailed({ submit: 'closed', mismatch: ['판매가'] }) === true,
     'stepFailed: 되읽기 불일치(`mismatch`)는 실패다');
  ok(win.stepFailed({ refused: true, error: '거부' }) === true, 'stepFailed: 거부한 단계는 실패다');
  ok(win.stepFailed({ submit: 'stayed', drawer: { open: true }, modal: { open: false } }) === true,
     'stepFailed: 저장 뒤 드로어가 남았으면 실패다');
  ok(win.stepFailed({ submit: 'stayed', drawer: { open: false }, modal: { open: false } }) === false,
     'stepFailed: 드로어가 없는 전체 화면 폼의 `stayed` 는 실패가 아니다');
  ok(win.stepFailed({ submit: 'closed', errors: [], mismatch: [], bad: [] }) === false,
     'stepFailed: 깨끗하게 닫힌 저장은 완료다');
  ok(win.SUBMIT_OK.indexOf('stayed') < 0, 'SUBMIT_OK: `stayed` 를 무조건 성공으로 세지 않는다', win.SUBMIT_OK);

  // 2-o) 서버가 500 으로 답한 저장 (2026-09-09 Codex 지적 [차단 · htmx 4 이벤트 이름])
  //      ERP 는 `htmx.config.noSwap = [204,304,'4xx','5xx']` 이라 오류 응답으로 화면을
  //      갈아끼우지 않는다 — 거부 배너도 안 붙고 모달도 그대로다. 저장이 안 됐다는 표시가
  //      화면 어디에도 없으므로 **htmx 이벤트가 유일한 단서**이고, 종전에는 그 이름을
  //      htmx 1 카멜로만 들어서 이 저장이 `submit:'settled'` · `errors:[]` 로 완료가 됐다.
  win.progressReset();
  win.__failNextSave = true;
  const r500 = await win.runStep(8);
  ok(r500.submit === 'error', 'runCellStep: 서버가 500 으로 답하면 `error` 다', r500.submit);
  ok((r500.errors || []).some((e) => /500/.test(e)), 'runCellStep: 응답 코드를 errors 에 담는다', r500.errors);
  ok(win.stepFailed(r500) === true, 'stepFailed: 서버 오류는 실패다', r500);
  ok(win.stayRun.progressState().failed === 1 && win.stayRun.progressState().done === 0,
     'runStep: 띠도 실패로 센다 — 완료로 세지 않는다', win.stayRun.progressState());
  win.progressReset();
  win.__stayRunHtmx.error = null;
  win.__stayRunHtmx.errorStatus = null;

  // 2-p) CSRF 403 은 **한 번만** 스스로 다시 보낸다 (2026-09-10 실측).
  //      오래 열려 있던 탭의 첫 저장이 403 으로 거부되는데, 그것은 CsrfViewMiddleware 가
  //      뷰를 부르기 **전에** 끊은 것이라 저장이 들어가지 않았다 — 그래서 다시 보내도
  //      같은 값이 두 번 만들어지지 않는다. 가격 셀은 한 실행에 수백 번 저장하는 자리라
  //      여기서 멈추면 실행이 통째로 선다.
  win.__csrf403Once = true;
  const rcsrf = await win.runCellStep(6);
  ok(rcsrf.csrfRetried === true, 'runCellStep: 403 을 스스로 넘기고 저장했다', rcsrf);
  ok(rcsrf.submit === 'settled', 'runCellStep: 재시도 뒤 정착까지 갔다', rcsrf.submit);
  ok((rcsrf.errors || []).length === 0, 'runCellStep: 재시도가 통했으면 오류를 남기지 않는다', rcsrf.errors);
  ok(win.stepFailed(rcsrf) === false, 'stepFailed: 재시도로 저장이 끝났으면 실패가 아니다', rcsrf);
  ok(!!rcsrf.csrfRefresh, 'runCellStep: 새 토큰을 다시 읽었다는 것을 남긴다', rcsrf.csrfRefresh);

  //      500 은 다시 보내지 않는다 — 저장이 들어간 뒤 났을 수 있어 두 번 만들면 안 된다
  win.__failNextSave = true;
  const rc500 = await win.runCellStep(6);
  ok(rc500.submit === 'error', 'runCellStep: 500 은 그대로 error 다', rc500.submit);
  ok(rc500.csrfRetried === undefined, 'runCellStep: 500 에는 재시도 표시가 붙지 않는다', rc500.csrfRetried);
  win.progressReset();
  win.__stayRunHtmx.error = null;
  win.__stayRunHtmx.errorStatus = null;

  // 3) 룸 사진 올리기 — 지시서가 `→ [사진 추가]` 로 끝나는 단계(2026-09-04 합의).
  //    그 버튼은 파일 고르개이고 이 화면에는 저장 버튼이 없다. 러너가 대안(`저장`…)을 훑으면
  //    룸 폼의 [저장] 을 눌러 사진이 붙기 전에 드로어를 닫는다 — 그러지 않는지 본다.
  const dom2 = new JSDOM(readFileSync(join(here, 'helper_fixture.html'), 'utf8'), {
    url: 'https://example.test/stay/43900/#stay_tab_room_types',
    runScripts: 'dangerously',
    pretendToBeVisual: true
  });
  const w2 = dom2.window;
  w2.localStorage.setItem('staySteps', JSON.stringify(PHOTO_STEPS));
  w2.eval(readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8'));
  w2.eval(readFileSync(join(here, '..', 'scripts', 'stay_boot.js'), 'utf8'));

  const r3 = await w2.runStep(1, { uploaded: true });
  ok(r3.open === 'ok', 'runStep: 룸 행의 [편집] 로 드로어를 연다', r3.open);
  ok(r3.submit === 'upload-label', 'runStep: [사진 추가] 를 저장으로 누르지 않는다', r3);
  ok(r3.submitted === false, 'runStep: 저장한 것으로 세지 않는다', r3.submitted);
  ok(w2.stayRun.state().drawer.open === true, 'runStep: 드로어가 닫히지 않았다 — 룸 폼 [저장] 을 누르지 않았다');
  ok(!/저장|추가|만들기|등록|확인/.test(r3.submitAs || ''), 'runStep: 대안 버튼을 훑지 않았다', r3.submitAs);

  //    이 호출은 **파일을 옮긴 뒤**(`{uploaded:true}`)다 — `→ [사진 추가]` 줄은 이미 실행됐고
  //    이 화면에는 더 누를 저장 버튼이 없다. 그러므로 이것이 그 단계의 끝이다.
  //    종전에는 `upload-label` 을 무조건 넘김으로 읽어 띠에서 어느 숫자에도 세지 않았고
  //    (`pending`), 같은 결과를 `stepFailed` 는 **실패**로 읽어 지시서 탭·실행 로그에
  //    `실패` 로 적혔다 — 사진은 멀쩡히 올라간 채로(2026-09-22 운영 실행).
  ok(r3.uploadDone === true, 'runStep: 파일 줄을 이미 실행했다는 것을 결과에 싣는다', r3);
  ok(w2.stepFailed(r3) === false, 'stepFailed: 올린 뒤의 `upload-label` 은 실패가 아니다', r3);
  ok((w2.guideMark(r3) || {}).status === '완료', 'guideMark: 지시서 탭에도 완료로 넘긴다', w2.guideMark(r3));
  const p3 = w2.stayRun.progressState();
  ok(p3.done === 1 && p3.skipped === 0 && p3.failed === 0,
    'runStep: 파일을 올린 룸 사진 단계는 완료로 센다', p3);
  ok(p3.current === PHOTO_STEPS.steps[0].title, 'runStep: 그 단계 제목이 띠에 그대로 있다', p3);
  ok(p3.status !== 'failed', 'runStep: 그 단계를 실패로 물들이지 않는다', p3);
  ok(w2.__pageSaveClicks === 0,
    'runStep: 룸 사진 단계는 페이지 머리의 [저장] 을 누르지 않는다 — 룸 폼이지 기본정보 폼이 아니다', w2.__pageSaveClicks);

  // 3a) 그 앞 호출 — 고리가 사진 단계를 처음 부르면 드로어를 열고 값까지 채운 뒤
  //     **파일 다리를 기다리며** `submitted:false` 로 돌아온다. 아직 아무 사진도 안 올라갔다.
  //     종전에는 이 결과에 실패 표시가 하나도 없다는 이유로 `stepFailed` 가 거짓 →
  //     띠에 **완료**로 세고 `runStatus().marks` 가 지시서 탭에 `완료` 를 넘겼다.
  //     사진이 하나도 없는 단계가 체크되면 사람이 빠진 것을 영영 못 본다.
  {
    const domW = new JSDOM(readFileSync(join(here, 'helper_fixture.html'), 'utf8'), {
      url: 'https://example.test/stay/43900/#stay_tab_room_types',
      runScripts: 'dangerously',
      pretendToBeVisual: true
    });
    const wW = domW.window;
    wW.localStorage.setItem('staySteps', JSON.stringify(PHOTO_STEPS));
    wW.eval(readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8'));
    wW.eval(readFileSync(join(here, '..', 'scripts', 'stay_boot.js'), 'utf8'));

    const q1 = await wW.runStep(1);
    ok(q1.submitted === false, 'runStep: 파일 앞에서는 저장하지 않는다', q1.submitted);
    ok(q1.waitingFiles === true, 'runStep: 파일 다리를 기다린다는 것을 결과에 싣는다', q1);
    ok(wW.stepFailed(q1) === false, 'stepFailed: 파일을 기다리는 단계는 실패가 아니다', q1);
    const pq = wW.stayRun.progressState();
    ok(pq.done === 0 && pq.skipped === 0 && pq.failed === 0,
      'runStep: 사진이 아직 안 올라간 단계를 완료로 세지 않는다', pq);
    ok(wW.guideMark(q1) === null,
      'guideMark: 그 단계는 지시서 탭에 아무 것도 넘기지 않는다 — 완료로 체크하면 안 된다', wW.guideMark(q1));
  }

  // 3b) 기본정보 이미지 모달 — 첫 `runStep` 이 모달만 열고 `submitted:false` 로 끝나는 규약이라
  //     **같은 단계를 다시 부르는 것이 정상 경로**다(파일을 다리에 올린 뒤 다시 부른다).
  //     종전에는 이미 열린 `#content-modal` 을 또 열려다 `open: 'timeout'` 으로 끝났다
  //     (2026-09-10 운영 실행). 모달이 화면을 덮어 뒤의 여는 버튼은 눌러도 아무 변화가 없다.
  {
    const domI = new JSDOM(readFileSync(join(here, 'helper_fixture.html'), 'utf8'), {
      url: 'https://example.test/stay/43900/#stay_tab_room_types',
      runScripts: 'dangerously',
      pretendToBeVisual: true
    });
    const wI = domI.window;
    wI.localStorage.setItem('staySteps', JSON.stringify(IMAGE_STEPS));
    wI.eval(readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8'));
    wI.eval(readFileSync(join(here, '..', 'scripts', 'stay_boot.js'), 'utf8'));

    const i1 = await wI.runStep(1);
    ok(i1.open === 'ok', 'runStep: [이미지 직접등록] 으로 모달을 연다', i1.open);
    ok(i1.submitted === false, 'runStep: 사진 단계는 모달만 열고 끝난다', i1.submitted);
    ok(wI.stayRun.state().modal.open === true, 'runStep: 모달이 열린 채로 남는다', wI.stayRun.state().modal);

    const i2 = await wI.runStep(1);
    ok(i2.open === 'already', 'runStep: 다시 불러도 열려 있으면 already 다 — timeout 이 아니다', i2.open);
    ok(!i2.openDetail, 'runStep: already 는 끊지 않고 칸 채우기로 이어간다', i2.openDetail);
    ok((i2.bad || []).length === 0, 'runStep: already 뒤에도 모달 안 칸을 다 찾는다', i2.bad);
    ok(wI.stepFailed(i2) === false, 'stepFailed: already 는 실패가 아니다', i2);

    // 3c) 사진을 올린 뒤 `{uploaded:true}` 로 부르면 **모달 [저장] + 기본정보 폼 [저장]** 이다.
    //     모달 헤더 [저장] 은 `contents_imagecontent` 행만 만들고, 호텔과 사진의 연결
    //     (`fit_masterimages`)은 폼이 저장될 때 생긴다(ERP `fit/views/master.py`
    //     `after_save_model` 이 `main_image_sort`·`image_sort` 를 읽어 bulk_create).
    //     2026-09-10 운영 호텔에서 러너가 모달까지만 저장해 고객 화면에
    //     "사진 준비 중" 이 떴다 — DB 의 `fit_masterimages` 가 0행이었다.
    wI.__pageSaveClicks = 0;
    const i3 = await wI.runStep(1, { uploaded: true });
    ok(i3.submitted === true && wI.SUBMIT_OK.indexOf(String(i3.submit)) >= 0,
      'runStep: 모달 헤더 [저장] 까지 갔다', { s: i3.submitted, r: i3.submit });
    ok(wI.stayRun.state().modal.open === false, 'runStep: 모달이 닫혔다', wI.stayRun.state().modal);
    ok(i3.pageSaved === true, 'runStep: 이미지 단계는 기본정보 폼의 [저장] 까지 누른다', i3);
    ok(wI.__pageSaveClicks === 1, 'runStep: 페이지 머리의 [저장] 을 실제로 눌렀다', wI.__pageSaveClicks);
    ok(i3.pageSave === 'settled', 'runStep: 폼 저장이 끝난 것을 확인하고 돌아온다', i3.pageSave);
    ok(wI.stepFailed(i3) === false, 'stepFailed: 폼 저장까지 간 이미지 단계는 완료다', i3);

    // 폼 저장이 막히면(필수 칸 미입력) **완료가 아니다** — 사진이 고객에게 안 보인다
    wI.__pageSaveClicks = 0;
    wI.__pageSaveInvalid = true;
    wI.document.getElementById('toast-container').innerHTML = '';
    const i4 = await wI.runStep(1, { uploaded: true });
    ok(i4.pageSaved === false, 'runStep: 폼 저장이 막히면 pageSaved 가 거짓이다', i4);
    ok(i4.pageSave === 'invalid', 'runStep: 왜 막혔는지 그대로 들고 온다', i4.pageSave);
    ok((i4.pageInvalid || []).some((x) => /상품명/.test(x)), 'runStep: 어느 칸이 비었는지 알려 준다', i4.pageInvalid);
    ok(wI.stepFailed(i4) === true, 'stepFailed: 모달만 저장하고 끝난 이미지 단계는 실패다', i4);
    ok(/기본정보 폼의 \[저장\]/.test(i4.note || ''), 'runStep: 무엇을 더 해야 하는지 비고에 적는다', i4.note);
    wI.__pageSaveInvalid = false;
    [].slice.call(wI.document.querySelectorAll('.not-valid')).forEach((el) => el.classList.remove('not-valid'));

    ok(wI.isImageStep({ kind: '대표이미지 올리기' }) === true, 'isImageStep: `대표이미지 올리기` 는 이미지 단계다');
    ok(wI.isImageStep({ kind: '상품상세 이미지 올리기' }) === true, 'isImageStep: `상품상세 이미지 올리기` 는 이미지 단계다');
    ok(wI.isImageStep({ kind: '룸 사진 올리기' }) === false, 'isImageStep: 룸 사진은 이미지 단계가 아니다 — 페이지 저장이 없다');
  }

  // 3d) CSRF 403 을 도우미가 넘겼으면 **로그에 남길 수 있게** 그 사실을 들고 나온다.
  //     저장은 제대로 된 것이라 실패로 세지 않는다 — 첫 요청이 낡은 토큰으로 거부됐을 뿐이다.
  {
    const domC = new JSDOM(readFileSync(join(here, 'helper_fixture.html'), 'utf8'), {
      url: 'https://example.test/stay/43900/#stay_tab_room_types',
      runScripts: 'dangerously',
      pretendToBeVisual: true
    });
    const wC = domC.window;
    wC.localStorage.setItem('staySteps', JSON.stringify(CSRF_STEPS));
    wC.eval(readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8'));
    wC.eval(readFileSync(join(here, '..', 'scripts', 'stay_boot.js'), 'utf8'));

    wC.document.cookie = 'csrftoken=fresh-token; path=/';
    wC.__csrfCheck = true;
    wC.__hxRequests = 0;
    const rc = await wC.runStep(1);
    ok(rc.submitted === true && rc.submit === 'closed', 'runStep: 403 을 넘기고 드로어 저장까지 끝냈다', rc);
    ok(rc.csrfRetried === true, 'runStep: 재시도했다는 사실을 결과에 싣는다', rc.csrfRetried);
    ok((rc.warn || []).some((w) => /403 재시도 후 저장/.test(w)),
      'runStep: 로그 비고에 적을 한 줄을 warn 으로 준다', rc.warn);
    ok(wC.__hxRequests === 2, 'runStep: 요청은 딱 두 번 나갔다', wC.__hxRequests);
    ok(wC.stepFailed(rc) === false, 'stepFailed: 재시도로 저장이 끝난 단계는 완료다', rc);
    ok(wC.stayRun.progressState().done === 1 && wC.stayRun.progressState().failed === 0,
      'runStep: 띠도 완료로 센다', wC.stayRun.progressState());
  }

  // 4) 여는 버튼 거르개 — 반복 행 추가만 걸러야 한다.
  //    `연령 구간 추가` 는 글자가 `구간 추가` 로 끝나지만 오퍼 탭 `연령 구간` 카드의 **드로어를 여는 버튼**이다.
  ok(w2.isRowAddButton('행 추가') === true, 'isRowAddButton: `행 추가` 는 걸러진다');
  ok(w2.isRowAddButton('구간 추가') === true, 'isRowAddButton: `구간 추가` 는 걸러진다');
  ok(w2.isRowAddButton('단 추가') === true, 'isRowAddButton: `단 추가` 는 걸러진다');
  ok(w2.isRowAddButton('요율 행 추가') === true, 'isRowAddButton: `요율 행 추가` 는 걸러진다');
  ok(w2.isRowAddButton('침대 행 추가') === true, 'isRowAddButton: `침대 행 추가` 는 걸러진다');
  ok(w2.isRowAddButton('추천 포인트 추가') === true, 'isRowAddButton: `추천 포인트 추가` 는 걸러진다');
  ok(w2.isRowAddButton('연령 구간 추가') === false, 'isRowAddButton: `연령 구간 추가` 는 여는 버튼이다 — 걸러지지 않는다');
  ok(w2.isRowAddButton('오퍼 추가') === false, 'isRowAddButton: `오퍼 추가` 는 여는 버튼이다');

  //    그리고 실제로 그 드로어가 열린다 (종전에는 여는 버튼이 하나도 안 남아 드로어 없이 칸을 찾았다)
  const dom3 = new JSDOM(readFileSync(join(here, 'helper_fixture.html'), 'utf8'), {
    url: 'https://example.test/stay/43900/#stay_tab_room_types',
    runScripts: 'dangerously',
    pretendToBeVisual: true
  });
  const w3 = dom3.window;
  w3.localStorage.setItem('staySteps', JSON.stringify(AGE_STEPS));
  w3.eval(readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8'));
  w3.eval(readFileSync(join(here, '..', 'scripts', 'stay_boot.js'), 'utf8'));

  const r4 = await w3.runStep(1, { dry: true });
  ok(r4.open === 'ok', 'runStep: [연령 구간 추가] 로 드로어를 연다', r4);
  ok(/2027 계약/.test(w3.stayRun.state().drawer.title || ''), 'runStep: 그 오퍼 카드의 드로어가 열렸다', w3.stayRun.state().drawer);
  ok((r4.bad || []).length === 0, 'runStep: 연령 구간 칸을 다 찾았다', r4.bad);
  ok(w3.document.querySelector('[name=rate_basis_value]').value === '50', 'runStep: 유형을 고른 뒤 늦게 선 `요금 기준 값` 도 채운다');

  //    진행 표시 띠 — runStep 이 스스로 갱신한다(부르는 쪽은 따로 손댈 것이 없다)
  ok(typeof w3.runStepCore === 'function', 'runStepCore: 알맹이가 이름을 바꿔 그대로 남아 있다');
  const p4 = w3.stayRun.progressState();
  ok(p4.current === AGE_STEPS.steps[0].title, 'runStep: 띠에 지금 하는 단계 제목이 든다', p4);
  ok(p4.done === 0 && p4.failed === 0 && p4.skipped === 0,
    'runStep: 시험 삼아 돌린 단계(dry)는 어느 숫자에도 세지 않는다', p4);
  ok(p4.total === AGE_STEPS.steps.length, 'runStep: 전체 단계 수를 지시서에서 읽어 넣는다', p4);

  // 5) `경고 넘어가기` 는 금지된 단계다 — 실행하지 않고 거부한다(🟡 0 이 합격선)
  const r5 = await w3.runStep(2);
  ok(r5.refused === true && r5.fatal === true, 'runStep: `경고 넘어가기` 를 거부한다', r5);
  ok(/금지된 단계/.test(r5.error || ''), 'runStep: 왜 거부하는지 알려 준다', r5.error);
  ok(typeof w3.runWarnStep === 'undefined', 'runWarnStep: 갈래 자체가 없어졌다');
  ok(w3.checkGuide().some((x) => x.no === 2), 'checkGuide: 금지된 단계를 실행 전에 잡는다', w3.checkGuide());

  const p5 = w3.stayRun.progressState();
  ok(p5.failed === 1 && p5.status === 'failed', 'runStep: 거부된 단계는 실패로 센다', p5);
  ok(p5.current === AGE_STEPS.steps[1].title, 'runStep: 실패한 단계 제목이 띠에 그대로 남는다', p5);

  // 5b) 카드를 못 찾아 열지 못한 단계도 실패다
  const r6 = await w3.runStep(3);
  ok(r6.open === 'not-found', 'runStep: 화면에 없는 카드는 열지 못한다', r6);
  const p6 = w3.stayRun.progressState();
  ok(p6.failed === 2 && p6.done === 0, 'runStep: 열지 못한 단계도 실패로 센다', p6);
  ok(p6.current === AGE_STEPS.steps[2].title, 'runStep: 어느 단계에서 깨졌는지 띠에 남는다', p6);
  ok((p6.note || '').length > 0, 'runStep: 왜 실패했는지 한 줄을 남긴다', p6.note);

  // 5c) 실행을 시작하기 전에 부르는 되돌리기
  const p7 = w3.progressReset();
  ok(p7.done === 0 && p7.skipped === 0 && p7.failed === 0, 'progressReset: 숫자를 0 으로 되돌린다', p7);
  ok(p7.status === 'idle' && p7.current === '', 'progressReset: 상태와 지금 단계도 비운다', p7);
  ok(p7.total === AGE_STEPS.steps.length, 'progressReset: 전체 단계 수는 지시서에서 읽는다', p7);
  ok(Object.keys(w3.__stayRunStatus).length === 0, 'progressReset: 단계별 판정도 함께 비운다', w3.__stayRunStatus);

  // 6) 0단계 확인 — [호텔 만들기] 폼의 목록을 보고 `→ [목록]` 으로 돌아온다. 저장은 없다.
  const dom4 = new JSDOM(CREATE_FORM_HTML, {
    url: 'https://example.test/stay/create/',
    runScripts: 'dangerously',
    pretendToBeVisual: true
  });
  const w4 = dom4.window;
  w4.localStorage.setItem('staySteps', JSON.stringify(CHECK_STEPS));
  w4.eval(readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8'));
  w4.eval(readFileSync(join(here, '..', 'scripts', 'stay_boot.js'), 'utf8'));

  const c1 = await w4.runStep(1);
  ok(c1.checked === true, 'runCheckStep: 환율 확인 — 목록에서 값을 찾았다', c1);
  ok(c1.submitted === false, 'runCheckStep: 저장하는 단계가 아니다', c1.submitted);
  ok((c1.found || []).join(' ').indexOf('JPY') >= 0, 'runCheckStep: 무엇을 봤는지 돌려준다', c1.found);
  ok(c1.stayOnForm === true, 'runCheckStep: 다음 단계도 이 폼을 쓰면 [목록] 을 누르지 않는다', c1);

  const c2 = await w4.runStep(2);
  ok(c2.checked === false && (c2.bad || []).length === 1, 'runCheckStep: 목록에 없는 값은 알린다', c2);
  ok(c2.stayOnForm === true, 'runCheckStep: 값을 못 찾으면 폼에 남아 화면을 볼 수 있게 둔다', c2);

  const c3 = await w4.runStep(3);
  ok(c3.checked === true, 'runCheckStep: 도시 확인 — 목록에서 값을 찾았다', c3);
  ok(c3.left === true, 'runCheckStep: 폼을 다 봤으면 `→ [목록]` 으로 돌아온다', c3);

  // 저장이 없는 확인 단계도 끝난 단계다 — 완료로 센다(`submitted:false` 로 가르면 안 된다)
  const p8 = w4.stayRun.progressState();
  ok(p8.done === 2 && p8.failed === 1 && p8.skipped === 0,
    'runStep: 저장 없는 확인 단계도 완료로 센다 (값을 못 찾은 2단계만 실패)', p8);
  // 같은 단계를 다시 돌려도(사진 올린 뒤·고친 뒤) 두 번 세지 않는다 — 단계마다 판정 하나뿐이다
  await w4.runStep(1);
  const p9 = w4.stayRun.progressState();
  ok(p9.done === 2 && p9.failed === 1, 'runStep: 같은 단계를 다시 돌려도 두 번 세지 않는다', p9);
  ok(w4.__stayRunStatus[1] === 'done' && w4.__stayRunStatus[2] === 'failed',
    'runStep: 단계별 판정을 하나씩만 들고 있다', w4.__stayRunStatus);

  // 7) 늦게 그려지는 [호텔 만들기] 폼 (2026-09-07 운영 실행)
  //    이 폼은 뼈대를 먼저 그리고 통화 목록을 나중에 채우며 도시·거래처 select2 는 가장 늦게 붙는다.
  //    기다리지 않으면 0단계 확인이 `{checked:false, found:[]}` 로, 호텔 만들기가 칸마다
  //    `not-found` 로 끝난다 — 여기서는 그 차례를 그대로 흉내 내 본다.
  const DELAYED_CREATE_HTML = `<!doctype html><html lang="ko"><body>
  <div class="erp_cont_head"><h4>호텔 만들기 폼</h4></div>
  <div id="form_host"></div>
  <script>
    // 이 화면은 select2(jQuery 플러그인)를 쓴다 — 실려 있다는 표시는 처음부터 있고, 칸에 붙는 것은 가장 늦다
    window.jQuery = { fn: { select2: function () {} } };
    // (1) 250ms — 폼 뼈대(목록은 아직 '선택' 한 줄뿐)
    setTimeout(function () {
      document.getElementById('form_host').innerHTML =
        '<form><table class="bs-table"><tbody>' +
        '<tr><th>호텔명</th><td><input type="text" name="title"></td></tr>' +
        '<tr><th>도시</th><td><select name="city"><option value="">선택</option></select></td></tr>' +
        '<tr><th>공급 통화</th><td><select name="currency"><option value="">선택</option></select></td></tr>' +
        '<tr><th>거래처</th><td><select name="vendor"><option value="">선택</option></select></td></tr>' +
        '</tbody></table><button type="button">목록</button>' +
        '<button type="button">호텔 만들기</button></form>';
    }, 250);
    // (2) 500ms — 목록이 찬다
    setTimeout(function () {
      var add = function (sel, rows) {
        rows.forEach(function (r) { var o = document.createElement('option'); o.value = r[0]; o.textContent = r[1]; sel.appendChild(o); });
      };
      add(document.querySelector('select[name=currency]'), [['JPY', 'JPY'], ['USD', 'USD']]);
      add(document.querySelector('select[name=city]'), [['1', '도쿄(TYO)'], ['2', '오사카(OSA)']]);
      add(document.querySelector('select[name=vendor]'), [['9', '자사']]);
    }, 500);
    // (3) 750ms — 도시·거래처에 select2 가 붙는다(가장 늦다)
    setTimeout(function () {
      ['city', 'vendor'].forEach(function (n) {
        var sel = document.querySelector('select[name=' + n + ']');
        sel.classList.add('select2-hidden-accessible');
        var box = document.createElement('span');
        box.className = 'select2 select2-container';
        box.innerHTML = '<span class="select2-selection" role="combobox"><span class="select2-selection__rendered"></span></span>';
        sel.parentElement.appendChild(box);
      });
    }, 750);
    // select2 흉내 — mousedown 으로 열고 keyup 이 와야 검색된다(helper_fixture 와 같은 조건)
    document.addEventListener('mousedown', function (e) {
      var trig = e.target.closest ? e.target.closest('.select2-selection') : null;
      if (!trig) return;
      var sel = trig.closest('td').querySelector('select.select2-hidden-accessible');
      var dd = document.createElement('span');
      dd.className = 'select2-container select2-container--open';
      dd.innerHTML = '<input class="select2-search__field"><ul class="select2-results__options"></ul>';
      document.body.appendChild(dd);
      var field = dd.querySelector('.select2-search__field');
      field.addEventListener('keyup', function () {
        var q = field.value.trim();
        setTimeout(function () {
          var ul = dd.querySelector('ul');
          var rows = [].slice.call(sel.options).map(function (o) { return o.textContent; })
            .filter(function (r) { return r && r !== '선택' && r.indexOf(q) >= 0; });
          ul.innerHTML = rows.map(function (r) { return '<li class="select2-results__option">' + r + '</li>'; }).join('')
            || '<li class="select2-results__option select2-results__message">결과 없음</li>';
          ul.querySelectorAll('.select2-results__option').forEach(function (li) {
            li.addEventListener('mouseup', function () {
              var txt = li.textContent.trim();
              var hit = [].slice.call(sel.options).find(function (o) { return o.textContent.trim() === txt; });
              if (hit) { sel.value = hit.value; }
              trig.querySelector('.select2-selection__rendered').textContent = txt;
              dd.remove();
              sel.dispatchEvent(new Event('change', { bubbles: true }));
            });
          });
        }, 120);
      });
    });
  <\/script>
</body></html>`;

  const dom5 = new JSDOM(DELAYED_CREATE_HTML, {
    url: 'https://example.test/stay/create/',
    runScripts: 'dangerously',
    pretendToBeVisual: true
  });
  const w5 = dom5.window;
  w5.localStorage.setItem('staySteps', JSON.stringify(CHECK_STEPS));
  w5.eval(readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8'));
  w5.eval(readFileSync(join(here, '..', 'scripts', 'stay_boot.js'), 'utf8'));

  ok(w5.hotelFormReady() === false, 'hotelFormReady: 아직 아무것도 안 그려졌으면 거짓이다');
  ok(w5.stayRun.fields().length === 0, 'fixture: 처음에는 화면에 칸이 하나도 없다', w5.stayRun.fields());

  const t5a = Date.now();
  const c5 = await w5.runStep(1);
  const spent5 = Date.now() - t5a;
  ok(c5.checked === true, 'runCheckStep: 늦게 그려지는 폼도 기다렸다가 본다', c5);
  ok(c5.formReady === true, 'runCheckStep: 폼이 다 선 뒤에 읽었다', c5);
  // select2 는 750ms 에 붙는다 — 그 전에 끝났다면 기다리지 않고 읽었다는 뜻이다
  ok(spent5 >= 750, 'runCheckStep: select2 가 붙을 때까지 기다렸다', { spent: spent5, formWaited: c5.formWaited });
  ok((c5.found || []).join(' ').indexOf('JPY') >= 0, 'runCheckStep: 늦게 찬 통화 목록에서 값을 찾았다', c5.found);
  ok(w5.hotelFormReady() === true, 'hotelFormReady: 통화 목록이 차고 select2 가 붙으면 참이다');

  // 이미 다 선 폼에서는 기다리지 않는다 — 서 있는 화면에 8초를 버리면 안 된다
  const t5 = Date.now();
  const w5b = await w5.waitHotelForm();
  ok(w5b.ready === true && w5b.waited === 0 && Date.now() - t5 < 200,
    'waitHotelForm: 이미 선 폼에서는 곧바로 돌아온다', w5b);

  // 끝내 서지 않는 화면에서도 막지 않는다 — 한도까지만 기다리고 `{ready:false}` 로 알린다
  const dom6 = new JSDOM('<!doctype html><html lang="ko"><body><div>빈 화면</div></body></html>', {
    url: 'https://example.test/stay/create/', runScripts: 'dangerously', pretendToBeVisual: true
  });
  const w6 = dom6.window;
  w6.localStorage.setItem('staySteps', JSON.stringify(CHECK_STEPS));
  w6.eval(readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8'));
  w6.eval(readFileSync(join(here, '..', 'scripts', 'stay_boot.js'), 'utf8'));
  const w6r = await w6.waitHotelForm(400);
  ok(w6r.ready === false && w6r.waited >= 400, 'waitHotelForm: 끝내 안 서면 한도까지만 기다리고 알린다', w6r);

  //    [호텔 만들기] 단계도 같은 기다림을 쓴다 — 폼이 다 서기 전에 채우면 칸마다 not-found 로 끝난다
  const dom7 = new JSDOM(DELAYED_CREATE_HTML, {
    url: 'https://example.test/stay/create/', runScripts: 'dangerously', pretendToBeVisual: true
  });
  const w7 = dom7.window;
  w7.localStorage.setItem('staySteps', JSON.stringify(HOTEL_STEPS));
  w7.eval(readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8'));
  w7.eval(readFileSync(join(here, '..', 'scripts', 'stay_boot.js'), 'utf8'));
  const t7 = Date.now();
  const h7 = await w7.runStep(1, { dry: true });
  ok(h7.formReady === true, 'runStep: 호텔 만들기도 폼이 다 설 때까지 기다린다', h7);
  ok(Date.now() - t7 >= 750, 'runStep: select2 가 붙기 전에는 채우지 않는다', Date.now() - t7);
  ok((h7.bad || []).length === 0, 'runStep: 기다린 뒤에는 칸을 다 찾는다', h7.bad);
  ok(w7.document.querySelector('[name=currency]').value === 'JPY', 'DOM: 늦게 찬 통화 목록에서 골랐다',
    w7.document.querySelector('[name=currency]').value);

  // 8) 되읽기 불일치 — **믿을 수 있는 칸에서만** 저장을 막는다 (2026-09-09)
  //    저장은 되돌리기 어렵다: 금액·좌표가 어긋난 채로 저장하면 그 값이 그대로 굳는다.
  //    그렇다고 아무 칸에서나 멈추면 되읽기 한계(포함물 행·정률 값·침대 구성·글상자) 때문에
  //    아무 문제 없는 단계마다 로봇이 서서 리허설이 끊긴다. 그래서 둘로 가른다.
  //    아래 두 칸은 화면이 입력을 되받아 제 값으로 고친다 — 채우기는 `ok` 인데 되읽기가 어긋난다.
  const MISMATCH_HTML = `<!doctype html><html lang="ko"><body>
  <div class="erp_cont_head"><h4>되읽기 시험</h4></div>
  <form>
    <table class="bs-table"><tbody>
      <tr><th>정책명</th><td><input type="text" name="title"></td></tr>
      <tr><th>판매가</th><td><input type="text" name="price"></td></tr>
      <tr><th>설명</th><td><input type="text" name="memo"></td></tr>
    </tbody></table>
    <button type="button" id="save">저장</button>
  </form>
  <script>
    document.querySelector('[name=price]').addEventListener('input', function () { this.value = '999'; });
    document.querySelector('[name=memo]').addEventListener('input', function () { this.value = '화면이 고친 값'; });
    document.getElementById('save').addEventListener('click', function () {
      window.__saved = (window.__saved || 0) + 1;
      document.body.dispatchEvent(new CustomEvent('htmx:before:request', { bubbles: true }));
      document.body.dispatchEvent(new CustomEvent('htmx:after:swap', { bubbles: true }));
      document.body.dispatchEvent(new CustomEvent('htmx:after:settle', { bubbles: true }));
      document.body.dispatchEvent(new CustomEvent('htmx:finally:request', { bubbles: true }));
    });
  <\/script>
</body></html>`;

  const MISMATCH_STEPS = {
    guide: { title: '시험 호텔' },
    steps: [
      {
        //: 되읽기 한계 쪽만 어긋난다 — 경고만 남기고 그대로 저장한다
        no: 1, title: '취소정책 고치기 (되읽기 한계)', kind: '취소정책 고치기',
        head: { tab: null, card: null, block: null, screen: null, buttons: [], buttons_parsed: [] },
        fields: [
          { label: '정책명', kind: 'typed', value: '표준' },
          { label: '설명', kind: 'typed', value: '원고가 적은 값' }
        ],
        longtexts: [], photos: [], submit: '저장'
      },
      {
        //: 금액이 어긋난다 — 값이 그대로 되읽히는 칸이므로 저장 전에 멈춘다
        no: 2, title: '취소정책 고치기 (금액 어긋남)', kind: '취소정책 고치기',
        head: { tab: null, card: null, block: null, screen: null, buttons: [], buttons_parsed: [] },
        fields: [
          { label: '정책명', kind: 'typed', value: '표준' },
          { label: '판매가', kind: 'typed', value: '120' }
        ],
        longtexts: [], photos: [], submit: '저장'
      }
    ]
  };

  const dom8 = new JSDOM(MISMATCH_HTML, {
    url: 'https://example.test/stay/43900/', runScripts: 'dangerously', pretendToBeVisual: true
  });
  const w8 = dom8.window;
  w8.localStorage.setItem('staySteps', JSON.stringify(MISMATCH_STEPS));
  w8.eval(readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8'));
  w8.eval(readFileSync(join(here, '..', 'scripts', 'stay_boot.js'), 'utf8'));

  // 8a) 믿을 수 있는 칸(금액)이 어긋났다 — 저장 전에 멈춘다
  const m1 = await w8.runStep(2);
  ok((m1.mismatch || []).indexOf('판매가') >= 0, 'runStep: 금액 불일치를 `mismatch` 로 잡는다', m1.mismatch);
  ok(m1.submitted === false && m1.stoppedBy === 'mismatch',
     'runStep: 믿을 수 있는 칸이 어긋나면 저장 전에 멈춘다', m1);
  ok(w8.__saved === undefined, 'runStep: 저장 버튼을 누르지 않았다', w8.__saved);
  ok(/ignoreMismatch/.test(m1.note || ''), 'runStep: 다음에 무엇을 할지 알려 준다', m1.note);
  ok(w8.stayRun.progressState().failed === 1, 'runStep: 띠도 실패로 센다', w8.stayRun.progressState());

  // 8b) 되읽기 한계 쪽만 어긋났다 — 경고만 남기고 **그대로 간다**(리허설이 여기서 끊기면 안 된다)
  const m2 = await w8.runStep(1);
  ok((m2.mismatch || []).length === 0, 'runStep: 못 믿는 칸은 `mismatch` 에 넣지 않는다', m2.mismatch);
  ok((m2.mismatchWarn || []).indexOf('설명') >= 0, 'runStep: 대신 `mismatchWarn` 에 남긴다', m2.mismatchWarn);
  ok((m2.warn || []).some((w) => /설명/.test(w) && /되읽기만/.test(w)),
     'runStep: `warn` 으로도 남겨 로그에 적을 수 있게 한다', m2.warn);
  ok(m2.submitted === true && w8.__saved === 1, 'runStep: 멈추지 않고 저장한다', { s: m2.submitted, n: w8.__saved });
  ok(w8.stepFailed(m2) === false, 'stepFailed: 되읽기 한계뿐이면 실패가 아니다', m2);
  ok(m2.submit === 'stayed' && m2.drawer && m2.drawer.open === false,
     'runStep: 드로어 없는 전체 화면 폼은 `stayed` 로 돌아온다', m2);

  // 8c) 사람이 화면을 눈으로 확인했으면 막힌 단계를 `{ignoreMismatch:true}` 로 다시 부른다
  const m3 = await w8.runStep(2, { ignoreMismatch: true });
  ok(m3.submitted === true && w8.__saved === 2, 'runStep: 눈으로 확인했으면 넘어갈 길이 있다', m3);

  // 8d) 어느 칸을 믿는가 — 값이 그대로 되읽히는 것만이다
  [['판매가', true], ['정가', true], ['공급 원가', true], ['아동 추가 금액 — 소아', true],
   ['박수~', true], ['인원 조합', true], ['밴드 코드', true], ['호텔명', true],
   ['룸 이름', true], ['최소 연령 (만 나이)', true], ['시작일', true],
   ['포함물 1 · 포함물 이름', false], ['침대 구성 1 · 침대 종류', false],
   ['제공 주기 · 1박당 제공', false], ['연령별 단가 · 초등학생', false],
   ['요금 기준 값', false], ['한줄설명', false], ['어메니티', false]
  ].forEach(function (pair) {
    ok(w8.readbackTrusted(pair[0]) === pair[1],
       'readbackTrusted: `' + pair[0] + '` → ' + (pair[1] ? '믿는다' : '경고만'), w8.readbackTrusted(pair[0]));
  });

  // 9) 떼어 놓고 도는 고리를 **진짜 화면 위에서** — 1단계는 저장되고, 2단계는 믿을 수 있는 칸이
  //    어긋나 저장 전에 선다. 고리는 그 판정을 그대로 물려받아 `failed` 로 멈춘다.
  w8.progressReset();
  const started9 = w8.stayRun.runAll({ from: 1, to: 2 });
  ok(started9.started === true && started9.from === 1, 'runAll: 화면 위에서도 곧바로 돌아온다', started9);
  const t9 = Date.now();
  while (w8.stayRun.runStatus().running && Date.now() - t9 < 20000) await new Promise((r) => setTimeout(r, 20));
  const st9 = w8.stayRun.runStatus();
  ok(st9.running === false && st9.reason === 'failed' && st9.stoppedAt === 2,
     'runAll: 되읽기 불일치 단계에서 선다', { r: st9.reason, at: st9.stoppedAt });
  ok(st9.results.length === 2 && st9.results[1].stoppedBy === 'mismatch',
     'runStatus: results 에 runStep 이 돌려준 것이 그대로 들어 있다', st9.lastResult);
  ok(st9.cursor.lastDone === 1 && st9.cursor.pending === 2,
     'runAll: 1단계까지 마치고 2단계를 자리에 남긴다', st9.cursor);
  ok(st9.marks.length === 2 && st9.marks[0].status === '완료' && st9.marks[1].status === '확인 필요',
     'runStatus: 지시서 탭에 넘길 줄도 같은 판정이다', st9.marks);

  console.log('\n' + pass + ' 통과 · ' + fail + ' 실패');
  process.exit(fail ? 1 : 0);
};

run().catch((e) => { console.error(e); process.exit(1); });
