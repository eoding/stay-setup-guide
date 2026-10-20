/**
 * stay_helper.js 자동 시험 — jsdom 이 이미 깔려 있을 때만 돈다.
 *
 *   node tests/test_helper.mjs
 *   NODE_PATH=<jsdom 이 있는 node_modules> node tests/test_helper.mjs   # 다른 곳의 jsdom 을 빌려 쓸 때
 *
 * jsdom 이 없으면 아무것도 설치하지 않고 건너뛴다(종료 코드 0).
 * jsdom 에는 레이아웃이 없어서 화면 좌표로는 아무것도 판정할 수 없다 — 도우미는 그런 환경에서
 * 스타일(display/visibility)만 보고 판정하도록 되어 있다.
 */
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));

let pass = 0, fail = 0;
const ok = (cond, name, extra) => {
  if (cond) { pass++; console.log('  ok   ' + name); }
  else { fail++; console.log('  FAIL ' + name + (extra !== undefined ? ' — ' + JSON.stringify(extra) : '')); }
};

/* ────────────────────────────────────────────────────────────────────────────
   jsdom 없이 도는 부분 — 고정 대기를 상태 대기로 바꾼 `settleOr`

   `settleOr(cond, maxMs)` 는 DOM 이 필요 없다(조건은 부르는 쪽이 준다). 그래서 도우미에서
   그 대목만(`@settleOr:start`…`@settleOr:end`) 떼어 내 `sleep` 을 가짜로 물려 돌린다 —
   jsdom 이 없는 곳에서도 **이 시험은 돈다.** 지켜야 할 약속은 둘이다:
     ① 조건이 참이 되면 곧바로 끝난다. ② 끝내 참이 아니면 **종전의 고정 대기 값**에서 끝난다.
   ──────────────────────────────────────────────────────────────────────────── */

const HELPER_SRC = readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8');
const SETTLE_BLOCK = (() => {
  const a = HELPER_SRC.indexOf('/* @settleOr:start');
  const b = HELPER_SRC.indexOf('/* @settleOr:end');
  return (a >= 0 && b > a) ? HELPER_SRC.slice(a, b) : null;
})();

// `sleep` 과 `document` 를 가짜로 물린 settleOr. `calls` 에 어떤 대기를 걸었는지 남는다.
function loadSettleOr(env) {
  const e = env || {};
  const calls = [];
  const sleep = (ms) => { calls.push(ms); return new Promise((r) => setTimeout(r, ms)); };
  const doc = { visibilityState: e.visibility || 'hidden' };
  const make = new Function('sleep', 'TICK', 'document', 'requestAnimationFrame',
    SETTLE_BLOCK + '\nreturn { settleOr: settleOr, rafTick: rafTick, FAST_TICK: FAST_TICK };');
  const mod = make(sleep, 100, doc, e.raf);
  mod.calls = calls;
  return mod;
}

async function settleOrTests() {
  console.log('stay_helper 시험 — settleOr (jsdom 없이)');
  if (!SETTLE_BLOCK) {
    ok(false, 'settleOr: 도우미에서 `@settleOr:start`…`@settleOr:end` 표시를 찾지 못했습니다');
    return;
  }
  const M = loadSettleOr();

  // ① 이미 참이면 한 번도 쉬지 않는다
  let t = Date.now();
  let r = await M.settleOr(() => true, 900);
  ok(r === true && Date.now() - t < 30 && M.calls.length === 0,
     'settleOr: 조건이 이미 참이면 기다리지 않는다', { ms: Date.now() - t, calls: M.calls });

  // ② 참이 되는 즉시 끝난다 — 종전 고정 대기(900ms)의 몇 분의 일이다
  const M2 = loadSettleOr();
  let flag = false;
  setTimeout(() => { flag = true; }, 80);
  t = Date.now();
  r = await M2.settleOr(() => flag, 900);
  const early = Date.now() - t;
  ok(r === true && early >= 60 && early < 300, 'settleOr: 조건이 참이 되면 곧바로 끝난다', early);

  // ③ 끝내 참이 아니면 **종전과 같은 값**에서 끝난다 (최악이 나빠지지 않는다)
  const M3 = loadSettleOr();
  t = Date.now();
  r = await M3.settleOr(() => false, 250);
  const late = Date.now() - t;
  ok(r === false && late >= 230 && late < 450, 'settleOr: 끝내 아니면 종전 고정 대기 값에서 끝난다', late);
  ok(M3.calls.every((ms) => ms <= M3.FAST_TICK), 'settleOr: 바탕은 짧은 워커 타이머 틱이다', M3.calls);

  // ④ 조건이 터져도 삼키고 기다린다 — 화면이 갈리는 중에는 조건이 던질 수 있다
  const M4 = loadSettleOr();
  t = Date.now();
  r = await M4.settleOr(() => { throw new Error('교체 중'); }, 120);
  ok(r === false && Date.now() - t >= 100, 'settleOr: 조건이 던지면 거짓으로 보고 계속 기다린다', Date.now() - t);

  // ⑤ 조건이 없으면 종전 그대로 한 번 쉰다
  const M5 = loadSettleOr();
  r = await M5.settleOr(null, 80);
  ok(r === false && M5.calls.length === 1 && M5.calls[0] === 80,
     'settleOr: 조건이 없으면 종전처럼 통째로 쉰다', M5.calls);

  // ⑥ 뒤로 간 탭에서는 화면 프레임(rAF)을 쓰지 않는다 — rAF 는 멈춰 있어 바탕으로 쓸 수 없다
  let rafCalls = 0;
  const rafStub = (fn) => { rafCalls++; setTimeout(fn, 1); };
  const hidden = loadSettleOr({ visibility: 'hidden', raf: rafStub });
  await hidden.settleOr(() => false, 90);
  ok(rafCalls === 0 && hidden.calls.length > 0, 'settleOr: 뒤로 간 탭은 워커 타이머로만 잰다', { rafCalls, calls: hidden.calls });

  // ⑦ 앞에 있는 탭에서는 프레임을 가속기로 함께 건다(바탕은 그대로 워커 타이머다)
  rafCalls = 0;
  const visible = loadSettleOr({ visibility: 'visible', raf: rafStub });
  await visible.settleOr(() => false, 90);
  ok(rafCalls > 0 && visible.calls.length > 0, 'settleOr: 앞에 있는 탭은 프레임을 함께 건다', { rafCalls, calls: visible.calls });

  console.log('  — settleOr 시험 ' + pass + ' 통과 · ' + fail + ' 실패\n');
}

await settleOrTests();

/* ────────────────────────────────────────────────────────────────────────────
   jsdom 없이 도는 부분 ② — 저장·열기 천장 `config({waitMs})`

   기본 10초는 **운영 서버** 기준이다. 로컬처럼 느린 서버에서는 큰 채우기 한 번이 28초쯤 걸려
   저장이 실제로 들어갔는데도 `submit:'timeout'` 으로 러너가 섰다(2026-09-21 실측).
   지켜야 할 약속은 셋이다: ① 기본값은 그대로 10초다 ② 올린 값이 곧바로 먹는다
   ③ 말이 안 되는 값(1000 미만·숫자 아님)은 거부하고 지금 값을 지킨다.
   ──────────────────────────────────────────────────────────────────────────── */
const CONFIG_BLOCK = (() => {
  const a = HELPER_SRC.indexOf('/* @config:start');
  const b = HELPER_SRC.indexOf('/* @config:end');
  return (a >= 0 && b > a) ? HELPER_SRC.slice(a, b) : null;
})();
function loadConfig() {
  return new Function('var WAIT_MS = 10000;\n' + CONFIG_BLOCK +
    '\nreturn { config: config, waitMs: function () { return WAIT_MS; } };')();
}

async function configTests() {
  console.log('stay_helper 시험 — config({waitMs}) (jsdom 없이)');
  if (!CONFIG_BLOCK) {
    ok(false, 'config: 도우미에서 `@config:start`…`@config:end` 표시를 찾지 못했습니다');
    return;
  }
  const M = loadConfig();
  ok(M.config().waitMs === 10000 && M.waitMs() === 10000, 'config: 기본 천장은 10초다 (바뀌지 않았다)', M.config());
  const up = M.config({ waitMs: 40000 });
  ok(up.ok === true && up.waitMs === 40000 && M.waitMs() === 40000, 'config: 느린 서버용으로 올린다', up);
  const small = M.config({ waitMs: 900 });
  ok(small.ok === false && M.waitMs() === 40000, 'config: 1000 보다 작으면 거부하고 지금 값을 지킨다', small);
  const nan = M.config({ waitMs: '느리게' });
  ok(nan.ok === false && M.waitMs() === 40000, 'config: 숫자가 아니면 거부한다', nan);
  ok(M.config().waitMs === 40000 && M.config({}).waitMs === 40000,
     'config: 값을 안 주면 읽기만 한다', M.config());
  ok(M.config({ waitMs: '20000' }).waitMs === 20000, 'config: 글자로 온 숫자도 받는다', M.config());
  ok(loadConfig().waitMs() === 10000, 'config: 기본값 자체는 그대로다(다음 페이지는 10초로 시작한다)');
  console.log('  — config 시험 끝\n');
}

await configTests();

/* ────────────────────────────────────────────────────────────────────────────
   jsdom 없이 도는 부분 ③ — htmx 아닌 ajax 감시 `netWatch`

   기본정보 폼의 [저장] 은 htmx 가 아니라 제 손으로 쓴 ajax 다 — `hx.pending` 도 `swaps` 도
   안 움직여서 끝을 알 길이 안내 띠뿐이었고, 앞 저장의 띠가 안 사라지면 그마저 못 봤다
   (2026-09-21 운영 실측, `pageSave:'timeout'`). 그래서 오가는 요청의 **수와 주소·응답 코드**를
   세어 둔다. 지켜야 할 약속은 넷이다:
     ① fetch 가 끝나면 `xhrPending` 이 0 으로 내려오고 `xhrDone`·`xhrLast` 가 선다
     ② XHR 도 같다(주소는 `open`, 코드는 `status`)
     ③ **한 번만 감싼다** — 도우미를 다시 주입해도 두 겹이 되지 않는다(두 겹이면 두 번 세어진다)
     ④ 못 감싸는 환경(속성이 잠겨 던지는 곳)이면 **조용히** 넘어간다
   몸통(요청·응답 본문)은 건드리지 않는다 — 감싼 함수가 인자를 그대로 넘기는지도 함께 본다.
   ──────────────────────────────────────────────────────────────────────────── */
const NET_BLOCK = (() => {
  const a = HELPER_SRC.indexOf('/* @netWatch:start');
  const b = HELPER_SRC.indexOf('/* @netWatch:end');
  return (a >= 0 && b > a) ? HELPER_SRC.slice(a, b) : null;
})();
// 도우미 본체는 `'use strict'` 안에서 돈다 — 잠긴 속성에 넣으면 **던진다**. 그 조건을 그대로 흉내 낸다.
function loadNetWatch() {
  return new Function('window', 'trunc',
    "'use strict';\n" + NET_BLOCK + '\nreturn { netWatch: netWatch };');
}
// 가짜 XMLHttpRequest — `loadend` 를 들려주고 `status` 를 내놓는다.
function makeFakeXHR(status, delay) {
  function FakeXHR() { this.__ls = {}; this.status = 0; this.readyState = 0; }
  FakeXHR.prototype.open = function (m, u) { this.method = m; this.url = u; this.readyState = 1; };
  FakeXHR.prototype.addEventListener = function (n, f) { (this.__ls[n] = this.__ls[n] || []).push(f); };
  FakeXHR.prototype.send = function (body) {
    const self = this;
    self.sentBody = body;                                   // 몸통을 **건드리지 않고** 그대로 넘기는지 본다
    setTimeout(() => {
      self.status = status; self.readyState = 4;
      (self.__ls.loadend || []).forEach((f) => f());
    }, delay === undefined ? 20 : delay);
  };
  return FakeXHR;
}

async function netWatchTests() {
  console.log('stay_helper 시험 — netWatch (jsdom 없이)');
  if (!NET_BLOCK) {
    ok(false, 'netWatch: 도우미에서 `@netWatch:start`…`@netWatch:end` 표시를 찾지 못했습니다');
    return;
  }
  const make = loadNetWatch();
  const trunc = (s, n) => (s && s.length > n ? s.slice(0, n) + '…' : (s || ''));

  // ① fetch — 끝나면 셈이 선다
  const fetchCalls = [];
  const win = {
    fetch(input, init) { fetchCalls.push([input, init]); return Promise.resolve({ status: 200 }); },
    XMLHttpRequest: makeFakeXHR(302)
  };
  const M = make(win, trunc);
  const st = { xhrPending: 0, xhrDone: 0, xhrLast: null };
  M.netWatch(st);
  const wrappedFetch = win.fetch;
  const p = win.fetch('/fit/master/43900/change/', { method: 'POST', body: 'x=1' });
  ok(st.xhrPending === 1, 'netWatch: fetch 가 나가면 도는 요청으로 센다', st.xhrPending);
  await p;
  await new Promise((r) => setTimeout(r, 5));
  ok(st.xhrPending === 0 && st.xhrDone === 1, 'netWatch: fetch 가 끝나면 도는 수가 0 으로 내려온다', st);
  ok(st.xhrLast && st.xhrLast.status === 200 && /\/change\/$/.test(st.xhrLast.url),
     'netWatch: 끝난 요청의 주소와 응답 코드를 남긴다', st.xhrLast);
  ok(fetchCalls.length === 1 && fetchCalls[0][1] && fetchCalls[0][1].body === 'x=1',
     'netWatch: 요청 몸통은 그대로 넘긴다 (건드리지 않는다)', fetchCalls[0][1]);

  // ② XHR — 주소는 open, 코드는 status
  const x = new win.XMLHttpRequest();
  x.open('POST', '/fit/master/43900/change/');
  x.send('name=값');
  ok(st.xhrPending === 1, 'netWatch: XHR 도 도는 요청으로 센다', st.xhrPending);
  await new Promise((r) => setTimeout(r, 60));
  ok(st.xhrPending === 0 && st.xhrDone === 2, 'netWatch: XHR 이 끝나면 셈이 선다', st);
  ok(st.xhrLast && st.xhrLast.status === 302 && st.xhrLast.url === '/fit/master/43900/change/',
     'netWatch: XHR 의 주소는 open 에서, 코드는 status 에서 읽는다', st.xhrLast);
  ok(x.sentBody === 'name=값', 'netWatch: XHR 몸통도 그대로 넘긴다', x.sentBody);

  // ③ 다시 불러도 **두 겹이 되지 않는다** — 도우미를 다시 주입하는 자리다
  M.netWatch(st);
  make(win, trunc).netWatch(st);                            // 아예 다른 벌로 불러도 같다
  ok(win.fetch === wrappedFetch, 'netWatch: 다시 불러도 fetch 를 두 번 감싸지 않는다');
  await win.fetch('/fit/master/43900/change/');
  await new Promise((r) => setTimeout(r, 5));
  ok(st.xhrDone === 3, 'netWatch: 두 겹이 아니므로 한 요청은 한 번만 세어진다', st.xhrDone);
  const x2 = new win.XMLHttpRequest();
  x2.open('GET', '/fit/master/43900/');
  x2.send();
  await new Promise((r) => setTimeout(r, 60));
  ok(st.xhrDone === 4 && st.xhrPending === 0, 'netWatch: XHR 도 한 번만 세어진다', st);

  // ④ 못 감싸는 환경 — 조용히 넘어간다(터지지 않는다)
  const locked = { __stayRunNet: null };
  Object.defineProperty(locked, 'fetch', {
    configurable: true,
    get() { return function () { return Promise.resolve({ status: 200 }); }; },
    set() { throw new Error('잠긴 속성'); }
  });
  Object.defineProperty(locked, 'XMLHttpRequest', {
    configurable: true,
    get() { throw new Error('닿을 수 없음'); }
  });
  let threw = null;
  try { make(locked, trunc).netWatch({ xhrPending: 0, xhrDone: 0, xhrLast: null }); }
  catch (e) { threw = e; }
  ok(threw === null, 'netWatch: 감싸다 터지는 환경이면 조용히 넘어간다', threw && threw.message);

  console.log('  — netWatch 시험 끝\n');
}

await netWatchTests();

let JSDOM = null;
try { ({ JSDOM } = require('jsdom')); } catch (e) {
  console.log('SKIP — jsdom 이 없어 화면 시험(칸 찾기·값 넣기·저장)은 건너뜁니다 (설치하지 않습니다).');
  console.log('       손으로 보려면 tests/helper_fixture.html 을 크롬에서 열고 콘솔에 scripts/stay_helper.js 를 붙여 넣으세요.');
  process.exit(fail ? 1 : 0);
}

const dom = new JSDOM(readFileSync(join(here, 'helper_fixture.html'), 'utf8'), {
  url: 'https://example.test/stay/43900/',
  runScripts: 'dangerously',
  pretendToBeVisual: true
});
const win = dom.window;
win.eval(readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8'));
const R = win.stayRun;

const FIELDS = [
  { label: '룸 이름', kind: 'typed', value: 'Single' },
  { label: '상위 동/윙', kind: 'select', value: '(없음)' },
  { label: '면적(㎡)', kind: 'typed', value: '12' },
  { label: '전망', kind: 'empty' },
  { label: '엑스트라베드 가능', kind: 'select', value: '불가능' },
  { label: '침대 구성 1 · 침대 종류', kind: 'select', value: '싱글' },
  { label: '침대 구성 1 · 개수', kind: 'typed', value: '1' },
  { label: '침대 구성 2 · 침대 종류', kind: 'select', value: '벙크 (2층 침대)' },
  { label: '침대 구성 2 · 개수', kind: 'typed', value: '1' },
  { label: '어메니티', kind: 'multi', values: ['욕조', '무료 Wi-Fi'] },
  { label: '직접 입력 (목록에 없을 때만, 콤마로 구분)', kind: 'typed', value: '비데, 짐받이' },
  { label: '종류', kind: 'select', value: '리조트피' },
  { label: '반려동물', kind: 'select', value: '가능' },
  { label: '거래처', kind: 'select', value: '자사' },
  { label: '룸 사진', kind: 'file', file: 'room_01.jpg' }
];

const run = async () => {
  console.log('stay_helper 시험');

  // 1. 화면 상태
  const s0 = R.state();
  ok(s0.hotelId === '43900', 'state: 주소에서 호텔 번호를 읽는다', s0.hotelId);
  ok(s0.activeTab === '객실', 'state: 활성 탭 이름', s0.activeTab);
  ok(s0.drawer.open === false, 'state: 드로어는 아직 닫혀 있다');
  ok(s0.banner.blockers.length === 1 && s0.banner.warnings.length === 2,
    'state: 검증 배너를 막힘/권고로 나눈다', s0.banner);

  // 2. 행 안 버튼으로 드로어 열기
  const op = await R.open({ button: '편집', row: '스탠다드', card: '객실 (룸 타입)' });
  ok(op.status === 'ok' && /스탠다드/.test(op.drawer.title), 'open: 스탠다드 행의 [편집]', op);

  // 3. 값 넣기
  const res = await R.fill(FIELDS);
  const by = {};
  res.forEach((r) => { by[r.label] = r; });
  const bad = res.filter((r) => r.status !== 'ok' && r.status !== 'needs-upload');
  ok(bad.length === 0, 'fill: 모든 칸이 ok', bad);
  ok(by['룸 이름'].status === 'ok', 'fill: 표 안 텍스트 칸(같은 행 th 라벨)');
  ok(by['전망'].detail === '', 'fill: 비움은 값을 지운다', by['전망']);
  ok(by['침대 구성 2 · 침대 종류'].status === 'ok', 'fill: 행이 모자라면 [침대 행 추가] 를 눌러 만든다', by['침대 구성 2 · 침대 종류']);
  ok(/2칸 켬/.test(by['어메니티'].detail), 'fill: 체크 묶음은 라벨 글자로 켠다', by['어메니티'].detail);
  ok(by['종류'].status === 'ok', 'fill: 한 칸에 입력이 둘이면 값 종류로 고른다', by['종류']);
  ok(by['반려동물'].status === 'ok', 'fill: Materialize 셀렉트', by['반려동물']);
  ok(by['거래처'].status === 'ok', 'fill: select2 자동완성(keyup 필요)', by['거래처']);
  ok(by['룸 사진'].status === 'needs-upload' && by['룸 사진'].multiple === true,
    'fill: 파일 칸은 needs-upload 로 돌려준다', by['룸 사진']);
  ok(!!win.document.querySelector('[data-stay-upload]'), 'fill: 파일 칸에 표식을 남긴다');

  // 3b. 반복 행 칸 이름은 **정본 꼴**(`<칸 이름> <N> · <하위 칸>`)만 반복 행으로 읽는다.
  //     빈칸이나 가운뎃점이 어긋난 이름은 반복 행이 아니라 그냥 칸 이름으로 찾다가 못 찾는다 —
  //     파서의 `ROW_LABEL_RE` 와 같은 판정이라야 한다. 한쪽만 반복 행으로 읽으면 N번째 행이
  //     아니라 첫 행에 값이 들어간다.
  //     눈으로 가릴 수 없는 글자(가운뎃점 종류·붙임 빈칸)는 **코드포인트로 적는다** — 글자 그대로
  //     적으면 편집·복사 과정에서 정본 꼴로 바뀌어 시험이 조용히 무력해진다.
  const SP = '\u0020', DOT = '\u00b7', NBSP = '\u00a0', FULL_DOT = '\u30fb';
  const rep = await R.fill([
    { label: '침대 구성' + SP + '2' + SP + DOT + '개수', kind: 'typed', value: '9' },        // 가운뎃점 뒤 빈칸 없음
    { label: '침대 구성' + '2' + SP + DOT + SP + '개수', kind: 'typed', value: '9' },        // 숫자 앞 빈칸 없음
    { label: '침대 구성' + SP + '2' + SP + FULL_DOT + SP + '개수', kind: 'typed', value: '9' }, // 전각 가운뎃점(U+30FB)
    { label: '침대 구성' + NBSP + '2' + SP + DOT + SP + '개수', kind: 'typed', value: '9' }  // 붙임 빈칸(NBSP)
  ]);
  ok(rep.every((r) => r.status !== 'ok'), 'fill: 정본이 아닌 반복 행 이름은 받지 않는다', rep);
  ok([].slice.call(win.document.querySelectorAll('[name=bed_qty]')).every((i) => i.value !== '9'),
    'fill: 정본이 아닌 이름이 엉뚱한 침대 행에 값을 넣지 않는다',
    [].slice.call(win.document.querySelectorAll('[name=bed_qty]')).map((i) => i.value));

  // 실제 DOM 값 확인
  const q = (sel) => win.document.querySelector(sel);
  ok(q('[name=title]').value === 'Single', 'DOM: 룸 이름', q('[name=title]').value);
  ok(q('[name=view]').value === '', 'DOM: 전망이 비었다');
  ok(q('[name=extra]').value === 'n', 'DOM: 엑스트라베드 가능 = 불가능', q('[name=extra]').value);
  ok(q('[name=pet]').value === '가능', 'DOM: Materialize 숨은 select 가 바뀌었다', q('[name=pet]').value);
  ok(q('[name=agent]').value === '자사', 'DOM: select2 가 값을 넣었다', q('[name=agent]').value);
  ok(win.document.querySelectorAll('#bed-rows tr').length === 2, 'DOM: 침대 행이 2개다');

  // 4. 되읽어 대조
  const rb = R.readback(FIELDS);
  ok(rb.mismatch.length === 0, 'readback: 어긋난 칸이 없다', rb.mismatch);
  ok(rb.ok === rb.total && rb.total >= 13, 'readback: 대조 개수', { ok: rb.ok, total: rb.total });

  // 4b. 어메니티 카드의 `다른 룸에서 복사…` 셀렉트 (2026-09-07 운영 실행에서 드러났다)
  //     체크박스와 한 칸에 선 이름 없는 셀렉트다. 지시서의 칸이 아니므로 값은 늘 체크박스로 가야 한다.
  const amBoxes = () => [...win.document.querySelectorAll('[name=amenities_code]')];
  const amCopy = [...win.document.querySelectorAll('select')]
    .find((s) => s.options.length && /복사/.test(s.options[0].textContent));
  ok(!!amCopy, 'fixture: 어메니티 카드에 `다른 룸에서 복사…` 셀렉트가 있다');
  amBoxes().forEach((b) => { b.checked = false; });
  amCopy.selectedIndex = 0;
  const r4b = await R.fill([{ label: '어메니티', kind: 'multi', values: ['욕조'] }]);
  ok(r4b[0].status === 'ok', 'fill: 어메니티(선택 목록)가 ok', r4b[0]);
  const on4b = amBoxes().filter((b) => b.checked).map((b) => b.value);
  ok(on4b.length === 1 && on4b[0] === 'bath', 'fill: 욕조 한 칸만 켠다 — 복사 셀렉트로 가지 않는다', on4b);
  ok(amCopy.selectedIndex === 0, 'fill: `다른 룸에서 복사…` 셀렉트는 그대로 둔다', amCopy.value);
  const rb4b = R.readback([{ label: '어메니티', kind: 'multi', values: ['욕조'] }]);
  ok(rb4b.mismatch.length === 0, 'readback: 어메니티를 체크 묶음으로 되읽는다', rb4b.mismatch);

  //     값이 하나인 `선택: 샤워실` 은 파서가 kind=select 로 준다 — 운영에서 깨진 것이 바로 이 꼴이다
  //     (`어메니티` 가 복사 셀렉트로 풀려 "`욕조` 옵션이 없습니다" 로 끝났다).
  amBoxes().forEach((b) => { b.checked = false; });
  const r4c = await R.fill([{ label: '어메니티', kind: 'select', value: '샤워실' }]);
  ok(r4c[0].status === 'ok', 'fill: 값이 하나인 어메니티도 체크 묶음으로 간다', r4c[0]);
  const on4c = amBoxes().filter((b) => b.checked).map((b) => b.value);
  ok(on4c.length === 1 && on4c[0] === 'shower', 'fill: 샤워실만 켜졌다 — 첫 칸(욕조)이 아니다', on4c);
  ok(amCopy.selectedIndex === 0, 'fill: 값이 하나여도 복사 셀렉트를 건드리지 않는다', amCopy.value);
  const rb4c = R.readback([{ label: '어메니티', kind: 'select', value: '샤워실' }]);
  ok(rb4c.mismatch.length === 0, 'readback: 값 하나짜리 어메니티도 체크 묶음으로 되읽는다', rb4c.mismatch);

  // 5. 위험한 버튼은 거부
  const del = await R.submit('삭제');
  ok(del.status === 'refused' && del.reason === 'dangerous', 'submit: [삭제] 거부', del);
  const sale = await R.submit('판매 시작', { force: true });
  ok(sale.status === 'refused' && sale.reason === 'sale-start', 'submit: [판매 시작] 은 force 로도 거부', sale);

  // 5a. force 로 누르면 페이지 안 확인창(ERP 2026-09-08~)의 [확인] 을 러너가 대신 누른다.
  win.stayConfirmResult = null;
  const delF = await R.submit('삭제', { force: true });
  ok(delF.status !== 'refused', 'submit: force 면 [삭제] 를 실제로 누른다', delF.status);
  ok(delF.confirmText === '정말 삭제할까요?', 'submit: 확인창 문구를 confirmText 로 돌려준다', delF.confirmText);
  ok(win.stayConfirmResult === 'ok', 'submit: 확인창의 [확인] 을 눌렀다', win.stayConfirmResult);
  ok(R.state().confirm === null, 'state: 확인창이 닫히면 confirm 은 null', R.state().confirm);

  // 5a-2. 확인창이 떠 있으면 state() 가 알려 주고 close() 는 [취소] 로 닫는다.
  win.stayConfirmResult = null;
  win.document.querySelector('button[hx-confirm]').click();
  const cs = R.state().confirm;
  ok(cs && cs.open === true && cs.text === '정말 삭제할까요?', 'state: 열린 확인창을 confirm 으로 알려 준다', cs);
  ok(R.state().modal.open === false, 'state: 확인창을 모달로 세지 않는다', R.state().modal);
  await R.close();
  ok(win.stayConfirmResult === 'cancel', 'close: 확인창은 [취소] 로 닫는다', win.stayConfirmResult);
  ok(R.state().confirm === null, 'close: 확인창이 닫혔다', R.state().confirm);
  win.openRoomDrawer('스탠다드');

  // 5b. 룸 사진의 [사진 추가] 는 저장 버튼이 아니라 파일 고르개다.
  //     `not-found` 로 돌려주면 부르는 쪽이 대안을 훑다가 드로어의 [저장] 을 눌러
  //     사진이 붙기 전에 드로어가 닫힌다 — 그래서 따로 알려 준다.
  const up = await R.submit('사진 추가');
  ok(up.status === 'upload-label', 'submit: [사진 추가] 는 파일 고르개라고 알려 준다', up);
  ok(/takeFiles/.test(up.detail || ''), 'submit: 무엇으로 올려야 하는지 함께 알려 준다', up.detail);
  ok(R.state().drawer.open === true, 'submit: [사진 추가] 때문에 드로어가 닫히지 않았다');

  // 6. 저장 → 드로어가 닫히면 closed
  const sv = await R.submit('저장');
  ok(sv.status === 'closed', 'submit: 저장 뒤 드로어가 닫히면 closed', sv);
  ok(/저장되었습니다/.test(sv.toast || ''), 'submit: 안내 띠 글자를 함께 돌려준다', sv.toast);
  // 성공 띠는 오류가 아니다 — 종전에는 이것이 errors 에 들어가 저장마다 실패로 보였다
  ok(sv.errors.length === 0, 'submit: 성공 안내 띠를 errors 에 넣지 않는다', sv.errors);

  // 6b. 실패로 읽히는 띠는 그대로 오류다 — 성공 띠만 걸러낸다
  win.openRoomDrawer('스탠다드');
  const fv = await R.submit('등록');
  ok(fv.errors.some((e) => /실패/.test(e)), 'submit: 실패 안내 띠는 errors 에 남긴다', fv.errors);
  ok(/실패/.test(fv.toast || ''), 'submit: 실패 띠도 toast 로 함께 돌려준다', fv.toast);

  // 7. 자동 로그아웃 경고
  win.document.getElementById('logout-warning-modal').style.display = 'block';
  ok(R.state().logoutWarning === true, 'state: 자동 로그아웃 경고를 알아본다');
  const ka = R.keepAlive();
  ok(ka.clicked === true && ka.logoutWarning === false, 'keepAlive: [확인] 을 누른다', ka);

  // 8. 판매 연결 일괄 추가 드로어의 룸별 [오퍼별 표시명] — 이름에 룸을 붙여 가려낸다
  win.openFragment('stay_bulk_rooms', '객실 추가');
  const bulk = { card: '판매 연결 (오퍼 × 객실)' };
  const r8 = await R.fill([
    { label: '오퍼별 표시명 · Single', kind: 'typed', value: '싱글룸' },
    { label: '오퍼별 표시명 · Standard Double', kind: 'typed', value: '스탠다드 더블룸' }
  ], bulk);
  ok(r8.every((x) => x.status === 'ok'), 'fill: 룸별 표시명 두 칸이 다 찼다', r8);
  ok(win.document.getElementById('id_display_name_11').value === '싱글룸', 'fill: Single 칸에 싱글룸');
  ok(win.document.getElementById('id_display_name_12').value === '스탠다드 더블룸', 'fill: Standard Double 칸에 스탠다드 더블룸');
  // 새 카테고리 한 쌍은 룸별 칸에 끌려가지 않는다
  const r9 = await R.fill([{ label: '새 룸 오퍼별 표시명 (선택)', kind: 'typed', value: '새룸' }], bulk);
  ok(r9[0].status === 'ok' && win.document.getElementById('id_new_category_display_name').value === '새룸',
     'fill: `새 룸 오퍼별 표시명 (선택)` 은 제 칸으로 간다', r9);
  ok(win.document.getElementById('id_display_name_11').value === '싱글룸', 'fill: 룸별 칸이 덮이지 않았다');

  // 9. 연령 구간 드로어 (2026-09-04 신설)
  //    ① 같은 오퍼 이름이 오퍼 목록 행과 연령 구간 카드에 둘 다 있다 — 버튼을 가진 상자를 골라야 한다
  //    ② 늦게 서는 [요금 기준 값] 을 2차 재시도가 잡는다
  const tb = await R.tab('오퍼');
  ok(tb.status === 'ok' && tb.tab === '오퍼', 'tab: [오퍼] 탭으로 옮긴다', tb);
  // 두 번째 오퍼를 고른다 — "첫 카드를 누른다" 는 실수가 그대로 드러나게
  const opBand = await R.open({ button: '연령 구간 추가', card: '2027 계약' });
  ok(opBand.status === 'ok', 'open: 오퍼 카드의 [연령 구간 추가]', opBand);
  ok(/2027 계약/.test(opBand.drawer.title),
    'open: 이름이 같은 목록 행이 아니라 **그 버튼을 가진 카드**를 고른다', opBand.drawer);
  const band = { card: '연령 구간' };
  const r10 = await R.fill([
    { label: '밴드 코드', kind: 'typed', value: 'CHILD' },
    { label: '노출명', kind: 'typed', value: '초등학생' },
    { label: '최소 연령', kind: 'typed', value: '0' },
    { label: '최대 연령', kind: 'typed', value: '11.99' },
    { label: '방 인원수에 포함', kind: 'check' },
    { label: '요금 기준 유형', kind: 'select', value: '성인 요금의 %' },
    { label: '요금 기준 값', kind: 'typed', value: '50' },
    { label: '상세(자유텍스트)', kind: 'empty' }
  ], band);
  const bad10 = r10.filter((x) => x.status !== 'ok');
  ok(bad10.length === 0, 'fill: 연령 구간 칸이 모두 ok', bad10);
  ok(q('[name=code]').value === 'CHILD', 'DOM: 밴드 코드', q('[name=code]').value);
  ok(q('[name=included_in_occupancy]').checked === true, 'DOM: 방 인원수에 포함이 켜졌다');
  ok(q('[name=rate_basis_type]').value === '0', 'DOM: 요금 기준 유형 = 성인 요금의 %', q('[name=rate_basis_type]').value);
  ok(q('[name=rate_basis_value]').value === '50', 'DOM: 늦게 선 [요금 기준 값] 이 찼다', q('[name=rate_basis_value]').value);
  ok(r10[6].retried === true, 'fill: [요금 기준 값] 은 2차 재시도에서 잡혔다', r10[6]);

  // 10. 부과금의 연령별 단가 — [부과 단위]=인당 **과** [부과 방식]=정액 둘 다여야 서는 카드.
  //     화면 차례 그대로 적는다: 종류 → 이름 → 부과 방식 → 부과 단위 → 정액 금액 → 적용 룸 scope → 연령별 단가
  win.openFragment('stay_charge_form', '부과금 추가 — 2026 계약');
  const chg = { card: '부과금' };
  const r11 = await R.fill([
    { label: '종류', kind: 'select', value: '기타' },
    { label: '이름', kind: 'typed', value: '갈라디너' },
    { label: '부과 방식', kind: 'select', value: '정액' },
    { label: '부과 단위', kind: 'select', value: '인당' },
    { label: '정액 금액', kind: 'typed', value: '100' },
    { label: '적용 룸 scope', kind: 'multi', values: ['싱글룸'] },
    { label: '연령별 단가 · 초등학생', kind: 'typed', value: '50' },
    { label: '연령별 단가 · 유아', kind: 'typed', value: '0' }
  ], chg);
  const bad11 = r11.filter((x) => x.status !== 'ok');
  ok(bad11.length === 0, 'fill: 연령별 단가 칸이 모두 ok', bad11);
  ok(q('[name=age_rate_51]').value === '50', 'DOM: 초등학생 단가', q('[name=age_rate_51]').value);
  // 0 은 "무료" 라는 뜻이라 비움으로 접히면 안 된다
  ok(q('[name=age_rate_52]').value === '0', 'DOM: 유아 단가 0(무료)이 그대로 들어갔다', q('[name=age_rate_52]').value);
  const rb11 = R.readback([{ label: '연령별 단가 · 유아', kind: 'typed', value: '0' }], chg);
  ok(rb11.mismatch.length === 0, 'readback: 0 을 비움으로 읽지 않는다', rb11.mismatch);

  // 10b. 요금제 정본의 `포함물` 반복 행 — 열 제목이 없어 자리표시 글자로만 갈린다
  win.openFragment('stay_rate_plan_catalog', '요금제 정본 만들기');
  const cat = { card: '요금제 정본' };
  const r12 = await R.fill([
    { label: '요금제명', kind: 'typed', value: '조식 포함' },
    { label: '포함물 1 · 포함물 이름', kind: 'typed', value: '조식 2인' },
    { label: '포함물 1 · 설명 (선택)', kind: 'typed', value: '뷔페' },
    { label: '포함물 2 · 포함물 이름', kind: 'typed', value: '웰컴 드링크' }
  ], cat);
  const bad12 = r12.filter((x) => x.status !== 'ok');
  ok(bad12.length === 0, 'fill: 열 제목 없는 포함물 행을 자리표시 글자로 찾는다', bad12);
  const incl = [...win.document.querySelectorAll('[name=inclusions_name]')].map((e) => e.value);
  const desc = [...win.document.querySelectorAll('[name=inclusions_description]')].map((e) => e.value);
  ok(incl[0] === '조식 2인' && incl[1] === '웰컴 드링크', 'DOM: 포함물 이름 두 행', incl);
  ok(desc[0] === '뷔페' && desc[1] === '', 'DOM: 설명은 제 칸에만 들어갔다', desc);
  ok(win.document.querySelectorAll('[name=inclusions_name]').length === 2,
    'fill: 행이 모자라면 [행 추가] 를 눌러 만든다');

  // 10c. 포함물 되읽기 — 열 제목이 없어 자리표시 글자로만 갈리는 칸이라
  //      되읽기가 못 찾으면 값이 화면에 있는데도 매번 어긋난 것으로 보고된다(운영 실행에서 확인).
  const inclFields = [
    { label: '요금제명', kind: 'typed', value: '조식 포함' },
    { label: '포함물 1 · 포함물 이름', kind: 'typed', value: '조식 2인' },
    { label: '포함물 1 · 설명 (선택)', kind: 'typed', value: '뷔페' },
    { label: '포함물 2 · 포함물 이름', kind: 'typed', value: '웰컴 드링크' }
  ];
  const rbIncl = R.readback(inclFields, cat);
  ok(rbIncl.mismatch.length === 0, 'readback: 포함물 행을 자리표시 글자로 되읽는다', rbIncl.mismatch);
  ok(rbIncl.ok === rbIncl.total && rbIncl.total === 4, 'readback: 네 칸을 모두 대조했다', { ok: rbIncl.ok, total: rbIncl.total });
  // runStep 은 범위를 주지 않고 부른다 — 그 꼴에서도 같아야 한다
  const rbIncl2 = R.readback(inclFields);
  ok(rbIncl2.mismatch.length === 0, 'readback: 범위를 주지 않아도 같다', rbIncl2.mismatch);

  // 10d. 시즌 [가격] 드로어의 2026-09-08 신설 칸 둘.
  //      ① `아동 추가 금액 — 소아` 는 구분자가 EM DASH(U+2014) 앞뒤 공백이다 — `norm()` 이
  //         가운뎃점·대시를 지우므로 화면 라벨과 tier 4 로 맞아야 한다(눈으로 못 가리는 글자라
  //         **코드포인트로 적는다**: 편집·복사 과정에서 하이픈으로 바뀌면 시험이 조용히 무력해진다).
  //      ② `성인 요금의 %` 구간의 칸은 `disabled`+`readonly` 다 — 지시서가 적는
  //         `자동 입력됨 · 그대로 둠`(kind `auto`)을 만나면 **건드리지 않고 지나가야** 한다.
  const EMDASH = '—';
  win.openFragment('stay_season_fill_form', '가격 채우기 — Low');
  const seasonScope = { card: '가격 채우기' };
  const autoBefore = q('[name=child_extra_INF]').value;
  const r13 = await R.fill([
    { label: '판매 단가(공급 통화)', kind: 'typed', value: '92.00' },
    { label: '인원 조합(선택)', kind: 'typed', value: 'A2,A3' },
    { label: '인원 조합별 조정(선택)', kind: 'typed', value: 'A3:+30' },
    { label: '박수별 단가(선택)', kind: 'typed', value: '3:100,5:90' },
    { label: '아동 추가 금액 ' + EMDASH + ' 소아', kind: 'typed', value: '23.18' },
    { label: '아동 추가 금액 ' + EMDASH + ' 유아', kind: 'auto' },
    { label: '이미 값이 있는 날도 덮기', kind: 'uncheck' }
  ], seasonScope);
  const bad13 = r13.filter((x) => x.status !== 'ok' && x.status !== 'skipped');
  ok(bad13.length === 0, 'fill: 시즌 가격 채우기 칸이 모두 ok', bad13);
  ok(q('[name=los_prices]').value === '3:100,5:90', 'DOM: 박수별 단가(선택)', q('[name=los_prices]').value);
  ok(q('[name=occupancy_keys]').value === 'A2,A3', 'DOM: 인원 조합(선택)', q('[name=occupancy_keys]').value);
  ok(q('[name=occupancy_adjust]').value === 'A3:+30', 'DOM: 인원 조합별 조정(선택)', q('[name=occupancy_adjust]').value);
  ok(q('[name=child_extra_CHD]').value === '23.18',
    'fill: `아동 추가 금액 — 소아` 를 EM DASH 라벨로 찾는다', q('[name=child_extra_CHD]').value);
  ok(r13[4].tier === undefined || r13[4].status === 'ok', 'fill: 소아 칸이 ok', r13[4]);
  ok(r13[5].status === 'skipped', 'fill: `자동 입력됨` 칸은 건너뛴다', r13[5]);
  ok(q('[name=child_extra_INF]').value === autoBefore,
    'fill: 읽기 전용(`성인 요금의 %`) 아동 금액 칸을 건드리지 않았다', q('[name=child_extra_INF]').value);
  const rb13 = R.readback([{ label: '아동 추가 금액 ' + EMDASH + ' 소아', kind: 'typed', value: '23.18' },
                           { label: '박수별 단가(선택)', kind: 'typed', value: '3:100,5:90' }], seasonScope);
  ok(rb13.mismatch.length === 0, 'readback: 신설 칸 둘을 되읽는다', rb13.mismatch);

  // 10e. ERP CO-32105(2026-10-20) — 저장 버튼 [이 단가로 깔기] → [가격 적용],
  //      `이 시즌이 예전에 깐 다른 인원 조합·요금제 셀 지우기` → `이번에 고르지 않은 인원·요금제 가격 지우기`.
  //      배포 전에 쓴 지시서는 옛 글자, 뒤에 쓴 지시서는 새 글자다 — 배포 전후 어느 화면에서든 둘 다 같은 것을 찾아야 한다.
  const OLD_SAVE = '이 단가로 깔기', NEW_SAVE = '가격 적용';
  const OLD_STALE = '이 시즌이 예전에 깐 다른 인원 조합·요금제 셀 지우기';
  const NEW_STALE = '이번에 고르지 않은 인원·요금제 가격 지우기';
  const seasonSec = win.document.getElementById('stay_season_fill_form');
  const saveBtn = seasonSec.querySelector('[data-stay-action="save"]');
  ok(R.findButton(seasonSec, NEW_SAVE) === saveBtn, 'findButton: 새 화면에서 [가격 적용] 을 찾는다');
  ok(R.findButton(seasonSec, OLD_SAVE) === saveBtn, 'findButton: 옛 지시서의 [이 단가로 깔기] 로도 새 화면의 저장 버튼을 찾는다');
  ok(R.findButton(win.document.body, '[' + OLD_SAVE + ']') === saveBtn, 'findButton: 대괄호 붙은 옛 글자도, 문서 전체 범위에서도');
  // 화면 표식이 없어도(옛 배포판) 글자 별칭만으로 찾는다
  saveBtn.removeAttribute('data-stay-action');
  ok(R.findButton(seasonSec, OLD_SAVE) === saveBtn, 'findButton: 표식 없이도 글자 별칭으로 찾는다');
  // 옛 화면 + 새 지시서. 같은 범위에 시즌 카드의 [가격](드로어를 여는 버튼)이 있다 —
  // `가격` 은 `가격 적용` 의 앞글자라, 앞글자 일치로 고르면 저장 대신 [가격] 을 누른다.
  saveBtn.textContent = OLD_SAVE;
  seasonSec.insertAdjacentHTML('afterbegin', '<button type="button" id="season_price_opener">가격</button>');
  const opener = win.document.getElementById('season_price_opener');
  ok(R.findButton(seasonSec, NEW_SAVE) === saveBtn, 'findButton: 옛 화면에서 [가격 적용] 은 [이 단가로 깔기] 를 찾는다 — [가격] 이 아니다');
  ok(R.findButton(seasonSec, NEW_SAVE, true) === saveBtn, 'findButton: strict 여도 같다');
  // 두 글자 다 없으면 **아무것도 고르지 않는다** — 앞글자가 같은 [가격] 으로 흘러가지 않는다
  saveBtn.textContent = '다른 버튼';
  ok(R.findButton(seasonSec, NEW_SAVE) === null, 'findButton: 두 글자가 다 없으면 null — [가격] 을 고르지 않는다');
  ok(R.findButton(seasonSec, OLD_SAVE) === null, 'findButton: 옛 글자로 찾아도 null');
  // 표식이 붙어 있으면 글자가 무엇이든 그 저장 버튼이다 — 단, 이 화면(season-price-fill) 안에서만
  saveBtn.setAttribute('data-stay-action', 'save');
  ok(R.findButton(seasonSec, NEW_SAVE) === saveBtn, 'findButton: `data-stay-action="save"` 가 글자보다 먼저다');
  seasonSec.removeAttribute('data-stay-screen');
  ok(R.findButton(seasonSec, NEW_SAVE) === null, 'findButton: 다른 화면의 `data-stay-action="save"` 는 이 글자로 고르지 않는다');
  ok(R.findButton(seasonSec, '가격') === opener, 'findButton: [가격] 은 여전히 [가격] 이다');
  // 되돌린다
  seasonSec.setAttribute('data-stay-screen', 'season-price-fill');
  saveBtn.textContent = NEW_SAVE;
  opener.remove();

  // 체크박스 — 옛 지시서는 옛 글자로 `체크` 를 적는다. `해제` 는 칸을 못 찾아도 건너뛰지만
  // `체크` 는 경고만 남고 칸이 꺼진 채 저장된다 — 그래서 별칭이 꼭 있어야 한다.
  const stale = q('[name=stale_cleanup]');
  const rStaleOld = await R.fill([{ label: OLD_STALE, kind: 'check' }], seasonScope);
  ok(rStaleOld[0].status === 'ok' && stale.checked === true, 'fill: 옛 글자로 새 화면의 `stale_cleanup` 을 켠다', rStaleOld[0]);
  const rbStaleOld = R.readback([{ label: OLD_STALE, kind: 'check' }], seasonScope);
  ok(rbStaleOld.mismatch.length === 0 && rbStaleOld.ok === 1, 'readback: 옛 글자로 되읽는다', rbStaleOld);
  const rStaleNew = await R.fill([{ label: NEW_STALE, kind: 'uncheck' }], seasonScope);
  ok(rStaleNew[0].status === 'ok' && stale.checked === false, 'fill: 새 글자로 끈다', rStaleNew[0]);
  // 옛 화면(라벨이 옛 글자) + 새 지시서
  const staleLabels = [stale.closest('tr').querySelector('th'), stale.closest('label').querySelector('span')];
  staleLabels.forEach((el) => { el.textContent = OLD_STALE; });
  const rStaleOldScreen = await R.fill([{ label: NEW_STALE, kind: 'check' }], seasonScope);
  ok(rStaleOldScreen[0].status === 'ok' && stale.checked === true, 'fill: 새 글자로 옛 화면의 칸을 켠다', rStaleOldScreen[0]);
  staleLabels.forEach((el) => { el.textContent = NEW_STALE; });
  stale.checked = false;

  // 11. 2026-09-04 화면의 위험 버튼 — 이름만으로도 거부한다
  win.closeDrawer();
  const danger = { card: '위험 버튼' };
  for (const [label, reason] of [['전용으로 분리', 'dangerous'], ['2026-01 닫기', 'dangerous'],
                                 ['판매 재개', 'dangerous'], ['세후가로 확정', 'dangerous']]) {
    const r = await R.submit(label, danger);
    ok(r.status === 'refused' && r.reason === reason, 'submit: [' + label + '] 거부', r);
  }

  // 12. 가격 캘린더의 2층 모달은 `.modal.open` 이 아니라 `.stay-modal` 이다
  ok(R.state().modal.open === false, 'state: 닫힌 `.stay-modal` 은 열린 것으로 세지 않는다');
  win.document.getElementById('stay_cell_edit').style.display = 'block';
  const sm = R.state().modal;
  ok(sm.open === true && sm.id === 'stay_cell_edit' && /싱글룸/.test(sm.title),
    'state: 열린 `.stay-modal` 을 알아본다', sm);

  // 12b. 그 모달의 `인원 조합` 이 텍스트 → **셀렉트**로 바뀌었다(2026-09-08).
  //      항목 글자는 키가 앞이다: `A2C1_CHD · 성인 2 · 소아 1`. 원고는 좌표만 적으므로
  //      `A2` 는 `A2C1_CHD` 의 앞글자이기도 해서 글자 전체로는 둘 다에 걸린다 —
  //      앞 조각이 **완전히 같은** 항목을 골라야 한다.
  // 아래 추가 카드의 셀렉트다 — 위 좌표 묶음 표에도 같은 이름의 **숨은** 칸이 행마다 있으므로
  // 문서 전체에서 첫 것을 집으면 그 hidden 을 읽는다(2026-09-09 배포판).
  const occSel = () => win.document.querySelector('#stay_cell_add_1 [name=occupancy_key]');
  const cell = { card: '인원별 · 박수별 가격 추가' };
  for (const [want, value, why] of [
    ['A2C1_CHD', 'A2C1_CHD', '키만 적어도 `A2C1_CHD · 성인 2 · 소아 1` 을 고른다'],
    ['A2', 'A2', '`A2` 는 `A2C1_CHD` 가 아니라 `A2 · 성인 2` 다'],
    ['인원 무관 단일가', '', '`인원 무관 단일가` 는 빈 값이다']
  ]) {
    occSel().selectedIndex = 1;
    const r = await R.fill([{ label: '인원 조합', kind: 'select', value: want }], cell);
    ok(r[0].status === 'ok', 'fill: [인원 조합] `' + want + '` — ' + why, r[0]);
    ok(occSel().value === value, 'DOM: [인원 조합] = `' + value + '`', occSel().value);
  }
  // 목록에 없는 좌표는 지어내지 않는다 — 그 계약에 없는 조합을 조용히 만들면 안 된다
  const noOcc = await R.fill([{ label: '인원 조합', kind: 'select', value: 'A9C9_ZZZ' }], cell);
  ok(noOcc[0].status !== 'ok', 'fill: 목록에 없는 좌표는 고르지 않는다', noOcc[0]);

  // 12b-1. 그 판정을 **부트도 그대로 쓴다**(`stay_boot.js` 의 가격 셀 단계). 두 벌로 두었더니
  //        한쪽에만 앞 조각 폴백이 있어, 항목 글자를 그대로 적은 원고(`선택: A2 · 성인 2`)가
  //        칸은 이미 맞춰 놓고도 `not-found` 로 끝났다(2026-09-22 운영 실행). 내보내는 이름이
  //        사라지면 부트가 조용히 옛 맞추기로 되돌아가므로 여기서 함께 지킨다.
  {
    ok(typeof R.pickOption === 'function', 'stayRun.pickOption 이 선다');
    const sel = occSel();
    ok((R.pickOption(sel, 'A2').el || {}).value === 'A2',
      'pickOption: `A2` 는 앞 조각이 같은 `A2 · 성인 2` 다 — `A2C1_CHD` 가 아니다');
    ok((R.pickOption(sel, 'A2 · 성인 2').el || {}).value === 'A2',
      'pickOption: 항목 글자 전체로 적어도 같은 항목이다');
    ok((R.pickOption(sel, '선택: A2 · 성인 2').el || {}).value === 'A2',
      'pickOption: `선택:` 이 붙은 옛 꼴도 그 항목에 닿는다');
    ok(R.pickOption(sel, 'A9C9_ZZZ').status === 'not-found',
      'pickOption: 없는 좌표는 그대로 not-found 다 — 아무 항목이나 고르지 않는다');
  }

  // 12b-2. 에이전트 모달(2026-09-09 신설)은 `.stay-modal` 인데 `hidden` 으로 **늘 실려 있다**.
  //        열린 모달로 세면 안 되고, 그 안의 제목·버튼이 카드·저장 버튼으로 잡혀서도 안 된다.
  {
    ok(!!win.document.getElementById('stay_agent_resume'), '픽스처: 에이전트 모달이 DOM 에 있다');
    // 위 12번이 셀 편집 모달을 열어 둔 상태다 — 그때도 잡히는 것은 그쪽 하나여야 한다.
    ok(R.state().modal.id === 'stay_cell_edit',
      'state: 접힌 에이전트 모달을 열린 모달로 세지 않는다', R.state().modal);
    ok(R.findButton(win.document.body, '복사') === null,
      'findButton: 접힌 모달의 [복사] 는 고르지 않는다');
    const agentBtns = R.buttons({ card: '이 호텔을 에이전트로 이어서 하기' });
    ok(!agentBtns.includes('복사'), 'buttons: 접힌 모달 제목으로 좁혀도 그 안 버튼은 안 나온다', agentBtns);
  }

  // 12c. 좌표 묶음의 열 자리 (2026-09-09 배포판) — 그룹 머리가 `rowspan` 으로 층 전체를 덮어
  //      층 둘째 행은 `<td>` 가 하나 적다. 자리로 세면 `판매가` 값이 `정가` 칸에 들어간다.
  {
    const rows = ['cell_row_101', 'cell_row_102', 'cell_row_103'].map((id) => win.document.getElementById(id));
    const cols = rows.map((r) => R.rowCells(r).length);
    ok(cols.every((n) => n === 7), 'rowCells: 층 둘째 행도 7열로 푼다', cols);
    // 첫 열은 그룹 머리 — 묶음의 두 층이 **같은 칸**을 가리킨다(rowspan 이 덮은 자리다).
    ok(R.rowCells(rows[0])[0] === R.rowCells(rows[1])[0],
      'rowCells: rowspan 으로 덮인 첫 열은 두 층이 같은 칸이다');
    ok(R.rowCells(rows[1])[2] === rows[1].querySelector('[name=price]').closest('td'),
      'rowCells: 층 둘째 행의 3열이 `판매가` 칸이다');
    // 자리로 세던 종전 방식이면 여기서 `정가` 칸이 나온다 — 그 차이가 이 시험의 값이다.
    ok(rows[1].children[2] !== R.rowCells(rows[1])[2],
      'rowCells: 자리(`row.children`)와 열 번호가 실제로 어긋난다(시험이 의미가 있다)');
  }

  // 12d. 액션 칸의 버튼이 `div.stay-actions` 안으로 한 겹 더 들어갔다(2026-09-09) —
  //      버튼을 찾는 길이 그대로여야 한다.
  {
    const row = win.document.getElementById('cell_row_102');
    ok(!!row.querySelector('.stay-actions button'), '픽스처: 액션 버튼이 `.stay-actions` 안이다');
    ok(!!R.findButton(row, '저장'), 'findButton: 한 겹 더 싸여도 행의 [저장] 을 찾는다');
  }

  win.document.getElementById('stay_cell_edit').style.display = 'none';

  // 12e. 저장 거부는 `.stay-banner--blocking` 한 줄로 온다 — 클래스에 `error` 가 없어
  //      종전 훑기가 통째로 놓치던 자리다. 드로어가 **열린 채**라 `stayed` 로 끝난다.
  win.openRoomDrawer('스탠다드');
  const refused = await R.submit('거부 저장');
  ok(refused.status === 'stayed', 'submit: 거부되면 드로어가 열린 채다', refused.status);
  ok((refused.errors || []).some((e) => /전개 날짜가 0일입니다/.test(e)),
    'submit: `.stay-banner--blocking` 의 사유를 errors 로 돌려준다', refused.errors);
  win.closeDrawer();

  // 12f. 서버 오류(500 · CSRF 403) — ERP 는 `htmx.config.noSwap` 이라 **화면이 그대로 남는다.**
  //      저장이 안 됐다는 표시가 화면 어디에도 없으므로 htmx 이벤트가 유일한 단서다.
  win.openRoomDrawer('스탠다드');
  win.__failNextSave = true;
  const failed = await R.submit('저장');
  ok(failed.status === 'error', 'submit: 서버가 오류로 답하면 error 다', failed);
  ok((failed.errors || []).some((e) => /서버가 오류로 답했습니다 \(500\)/.test(e)),
    'submit: 응답 코드를 사유에 담는다', failed.errors);
  ok(R.state().drawer.open === true, 'submit: 오류면 드로어가 그대로다');
  ok(win.__stayRunHtmx.errorStatus === 500, 'htmx 감시자: 어느 코드로 거부됐는지 따로 들고 있다', win.__stayRunHtmx.errorStatus);
  win.closeDrawer();
  win.__stayRunHtmx.error = null;
  win.__stayRunHtmx.errorStatus = null;

  // 12f-2. **CSRF 403 은 한 번만 자동으로 다시 보낸다** (2026-09-10 실측).
  //   오래 열려 있던 탭에서 저장하면 첫 요청이 403 으로 거부된다. ERP 는 htmx 헤더에 넣을
  //   토큰을 **페이지가 그려질 때 한 번** 박아 두므로(`common/templates/common/_htmx.html`),
  //   같은 버튼을 그냥 다시 눌러도 같은 낡은 토큰이 나가 또 403 이다 — 러너가 Django 가
  //   새로 내려 준 `csrftoken` 쿠키를 읽어 헤더를 덮어써야 두 번째가 통한다.
  //   403 은 CsrfViewMiddleware 가 뷰를 부르기 **전에** 끊은 것이라 저장이 들어가지 않았다 —
  //   그래서 이 코드에서만 재시도가 안전하다(같은 값을 두 번 만들지 않는다).
  {
    win.document.cookie = 'csrftoken=fresh-token; path=/';
    ok(/fresh-token/.test(win.document.cookie || ''), '픽스처: 새 토큰이 쿠키에 들어갔다', win.document.cookie);

    win.openRoomDrawer('스탠다드');
    win.__csrfCheck = true;
    win.__hxRequests = 0;
    const rt = await R.submit('저장');
    ok(rt.status === 'closed', 'submit: 403 을 스스로 넘기고 저장까지 끝냈다', rt);
    ok(rt.csrfRetried === true, 'submit: 재시도했다는 것을 결과에 싣는다(로그의 `403 재시도 후 저장`)', rt.csrfRetried);
    ok(win.__hxRequests === 2, 'submit: 요청은 딱 두 번 나갔다 — 첫 거부와 재시도', win.__hxRequests);
    ok((rt.errors || []).length === 0, 'submit: 재시도가 통했으면 오류를 남기지 않는다', rt.errors);
    ok(rt.csrfRefresh && rt.csrfRefresh.from === 'cookie', 'submit: 새 토큰을 쿠키에서 읽었다', rt.csrfRefresh);
    ok(!/token/i.test(JSON.stringify(rt.csrfRefresh || {}).replace(/"(from|inputs|hooked|ok)"/g, '')),
      'submit: 토큰 값 자체는 결과에 싣지 않는다', rt.csrfRefresh);
    ok(win.document.querySelector('input[name=csrfmiddlewaretoken]').value === 'fresh-token',
      'submit: 화면의 숨은 토큰 칸도 새 값으로 맞춘다(ajax·일반 폼 저장이 그걸 쓴다)');
    ok(R.state().drawer.open === false, 'submit: 재시도로 저장이 끝나 드로어가 닫혔다');

    // 두 번째도 403 이면 그대로 멈춘다 — 세 번은 없다
    win.__csrfValid = 'another-token';   // 쿠키를 읽어도 서버가 인정하지 않는 값
    win.openRoomDrawer('스탠다드');
    win.__hxRequests = 0;
    const st2 = await R.submit('저장');
    ok(st2.status === 'error', 'submit: 두 번째도 403 이면 error 로 멈춘다', st2);
    ok(st2.csrfRetryFailed === true, 'submit: 재시도가 통하지 않았다는 것도 남긴다', st2.csrfRetryFailed);
    ok(st2.csrfRetried === undefined, 'submit: 실패한 재시도를 성공으로 적지 않는다', st2.csrfRetried);
    ok(win.__hxRequests === 2, 'submit: 세 번 보내지 않는다 — 무한 재시도가 없다', win.__hxRequests);
    ok(R.state().drawer.open === true, 'submit: 거부된 저장은 드로어가 그대로다');
    win.closeDrawer();
    win.__csrfValid = 'fresh-token';
    win.__csrfCheck = false;
    win.__stayRunHtmx.error = null;
    win.__stayRunHtmx.errorStatus = null;

    // 403 **만** 다시 보낸다 — 500 은 저장이 들어간 뒤 났을 수 있어 두 번 만들면 안 된다
    win.openRoomDrawer('스탠다드');
    win.__failNextSave = true;
    win.__hxRequests = 0;
    const f5 = await R.submit('저장');
    ok(f5.status === 'error', 'submit: 500 은 그대로 error 다', f5.status);
    ok(win.__hxRequests === 1, 'submit: 500 은 다시 보내지 않는다 — 요청은 한 번뿐이다', win.__hxRequests);
    ok(f5.csrfRetried === undefined && f5.csrfRetryFailed === undefined,
      'submit: 500 에는 재시도 표시가 붙지 않는다', { a: f5.csrfRetried, b: f5.csrfRetryFailed });
    win.closeDrawer();
    win.__stayRunHtmx.error = null;
    win.__stayRunHtmx.errorStatus = null;
  }

  // 12g. htmx 이벤트 이름이 두 벌이다 — 운영 Stay 화면은 htmx **4**(콜론 표기)를 싣고
  //      레거시 3화면은 아직 1·2(카멜)다. 한쪽만 들으면 그 화면에서 감시자가 **통째로 침묵**하고,
  //      `error` 가 영영 null 이라 500·403·네트워크 실패가 성공으로 보고된다(2026-09-09).
  {
    const hx = win.__stayRunHtmx;
    const reset = () => { hx.pending = 0; hx.requests = 0; hx.swaps = 0; hx.settles = 0; hx.error = null; };
    const fire = (n, d) => win.document.body.dispatchEvent(new win.CustomEvent(n, { bubbles: true, detail: d || {} }));

    reset();
    fire('htmx:before:request');
    ok(hx.pending === 1 && hx.requests === 1, 'htmx4: `before:request` 를 센다', { p: hx.pending, r: hx.requests });
    fire('htmx:after:swap'); fire('htmx:after:settle');
    ok(hx.swaps === 1 && hx.settles === 1, 'htmx4: `after:swap` · `after:settle` 을 센다', { s: hx.swaps, t: hx.settles });
    fire('htmx:after:request');
    ok(hx.pending === 1, 'htmx4: `after:request` 로는 pending 을 빼지 않는다(fetch 가 던지면 안 온다)', hx.pending);
    fire('htmx:finally:request');
    ok(hx.pending === 0, 'htmx4: 언제나 오는 `finally:request` 로 pending 을 뺀다', hx.pending);

    // 네트워크가 끊기면 htmx 4 는 `after:request` 를 아예 안 쏘고 `error` → `finally` 만 쏜다
    reset();
    fire('htmx:before:request');
    fire('htmx:error', { error: { message: 'Failed to fetch' } });
    fire('htmx:finally:request');
    ok(hx.pending === 0, 'htmx4: 요청이 던져져도 pending 이 새지 않는다', hx.pending);
    ok(/Failed to fetch/.test(hx.error || ''), 'htmx4: `htmx:error` 의 사유를 담는다', hx.error);

    reset();
    fire('htmx:response:error', { ctx: { response: { status: 403 } } });
    ok(/403/.test(hx.error || ''), 'htmx4: `response:error` 의 응답 코드를 담는다(detail.ctx.response)', hx.error);

    // 코어는 元 element 가 DOM 에서 떨어져 있으면 이벤트를 **document 에 쏜다.**
    // Stay 는 패널이 제 자신을 outerHTML 로 갈아끼우는 모양이라 늘 그렇게 된다 —
    // `document.body` 에 걸어 두면 그 이벤트가 영영 안 닿는다(그 아래이기 때문이다).
    reset();
    win.document.dispatchEvent(new win.CustomEvent('htmx:after:settle', { bubbles: true, detail: {} }));
    ok(hx.settles === 1, 'htmx4: 코어가 document 에 쏜 이벤트도 듣는다(body 가 아니라 document 에 건다)', hx.settles);

    // 레거시 화면(htmx 1·2)의 카멜 이름도 그대로 듣는다 — 호환 한 벌
    reset();
    fire('htmx:beforeRequest'); fire('htmx:afterSwap'); fire('htmx:afterSettle'); fire('htmx:afterRequest');
    ok(hx.pending === 0 && hx.requests === 1 && hx.swaps === 1 && hx.settles === 1,
      'htmx1·2: 카멜 이름도 그대로 센다(레거시 화면 호환)',
      { p: hx.pending, r: hx.requests, s: hx.swaps, t: hx.settles });
    reset();
    fire('htmx:responseError', { xhr: { status: 500 } });
    ok(/500/.test(hx.error || ''), 'htmx1·2: `responseError` 의 `xhr.status` 를 담는다', hx.error);
    reset();
  }

  // 12h. 카드 안의 **빈 상태 안내문**은 오류가 아니다 (2026-09-10 운영 실행).
  //      `_rooms_panel.html` 은 객실이 없는 오퍼 카드마다 `.stay-banner--blocking` 을 그린다.
  //      룸을 오퍼 하나에 붙여도 다른 오퍼 카드의 그 안내문은 화면에 그대로 남으므로,
  //      저장이 정상(closed · 되읽기 17/17)인데도 `errors` 가 차서 `stepFailed` 가 참이 됐다.
  //      패널 **머리**의 거부 띠는 진짜 오류라 그대로 담아야 한다 — 카드 안이냐 밖이냐로 가른다.
  {
    await R.tab('객실');
    const card = win.document.querySelector('#stay_rooms_panel .stay-card:last-child .stay-banner--blocking');
    ok(!!card && /연결된 객실이 없습니다/.test(card.textContent), '픽스처: 오퍼 카드에 빈 상태 안내문이 있다');

    win.openRoomDrawer('스탠다드');
    const sv2 = await R.submit('저장');
    ok(sv2.status === 'closed', 'submit: 룸 저장이 정상으로 닫혔다', sv2.status);
    ok(!(sv2.errors || []).some((e) => /연결된 객실이 없습니다/.test(e)),
      'submit: 카드 안 빈 상태 안내문을 errors 에 싣지 않는다', sv2.errors);
    ok((sv2.pageNotes || []).some((e) => /연결된 객실이 없습니다/.test(e)),
      'submit: 넘긴 안내문은 pageNotes 로 남긴다', sv2.pageNotes);

    // 패널 머리의 거부 띠(카드 **밖**)는 그대로 오류다 — 이 갈래를 잃으면 진짜 거부를 놓친다
    win.showPanelError(true);
    win.openRoomDrawer('스탠다드');
    const sv3 = await R.submit('저장');
    ok((sv3.errors || []).some((e) => /판매일이 열려 있어/.test(e)),
      'submit: 패널 머리의 거부 띠는 그대로 errors 다', sv3.errors);
    ok(!(sv3.errors || []).some((e) => /연결된 객실이 없습니다/.test(e)),
      'submit: 진짜 오류가 있어도 빈 상태 안내문은 섞지 않는다', sv3.errors);
    win.showPanelError(false);

    // 드로어 **안**의 카드 띠는 그대로 담는다 — 그 조각은 요청마다 다시 그려진다
    win.openRoomDrawer('스탠다드');
    const body = win.document.getElementById('stay_drawer_body');
    body.insertAdjacentHTML('afterbegin',
      '<div class="stay-card"><div class="stay-banner stay-banner--blocking"><span>구간이 겹칩니다</span></div></div>');
    const sv4 = await R.submit('거부 저장');
    ok((sv4.errors || []).some((e) => /구간이 겹칩니다/.test(e)),
      'submit: 드로어 안이면 카드 안의 띠도 오류로 담는다', sv4.errors);
    win.closeDrawer();
  }

  // 12i. **비움 지시 + 칸 없음 = 만족** (2026-09-10 운영 실행).
  //      부과금의 `적용 날짜 (선택)` 은 부과 유형이 `선택` 이면 화면에 서지 않는다.
  //      비우라는 지시인데 칸 자체가 없으면 이미 비어 있는 것이다 — 종전에는 `same:false` 라
  //      믿을 수 있는 칸(날짜)이면 `mismatch` 로 저장 앞에서 멈췄다(부과금 4단계가 막혔다).
  {
    const chg2 = { card: '부과금' };
    ok(!win.document.querySelector('#stay_charge_form [name*=apply_date]'),
      '픽스처: 부과금 폼에 `적용 날짜 (선택)` 칸이 없다');

    const rbAbsent = R.readback([{ label: '적용 날짜 (선택)', kind: 'empty' }], chg2);
    ok(rbAbsent.mismatch.length === 0, 'readback: 비움 지시 + 칸 없음은 불일치가 아니다', rbAbsent.mismatch);
    ok(rbAbsent.ok === 1 && rbAbsent.total === 1, 'readback: 만족한 칸으로 센다', { ok: rbAbsent.ok, total: rbAbsent.total });
    ok(rbAbsent.fields[0].absent === true && rbAbsent.fields[0].actual === '(칸 없음)',
      'readback: 왜 만족인지 `absent` 로 밝힌다', rbAbsent.fields[0]);

    // 값 지시 + 칸 없음은 그대로 불일치다 — 넣어야 할 값이 갈 자리가 없다
    const rbNeed = R.readback([{ label: '적용 날짜 (선택)', kind: 'typed', value: '2026-12-24' }], chg2);
    ok(rbNeed.mismatch.length === 1, 'readback: 값 지시 + 칸 없음은 그대로 불일치다', rbNeed.mismatch);
    ok(rbNeed.fields[0].absent !== true, 'readback: 값 지시는 absent 로 접지 않는다', rbNeed.fields[0]);
  }

  // 12j. 이미 열린 모달을 다시 열려 하지 않는다 (2026-09-10 운영 실행).
  //      사진 단계는 첫 `runStep` 이 모달만 열고 `submitted:false` 로 끝나는 규약이라
  //      같은 단계를 다시 부르는 것이 정상 경로인데, 종전에는 `open: 'timeout'` 이 났다 —
  //      모달이 화면을 덮고 있어 뒤의 여는 버튼을 눌러도 아무 변화가 없기 때문이다.
  {
    await R.tab('기본정보');
    const spec = { button: '이미지 직접등록' };
    const o1 = await R.open(spec);
    ok(o1.status === 'ok', 'open: 이미지 모달을 연다', o1.status);
    ok(o1.modal.open === true && /이미지 등록\/변경/.test(o1.modal.title || ''), 'open: 그 모달이 열렸다', o1.modal);

    const o2 = await R.open(spec);
    ok(o2.status === 'already', 'open: 이미 열려 있으면 already 로 이어간다', o2.status);
    ok(o2.modal.open === true, 'open: already 여도 모달은 열린 그대로다', o2.modal);
    ok((o2.fields || []).some((f) => /이미지설명/.test(f.label || '')), 'open: already 도 칸 목록을 돌려준다', o2.fields);

    // 저장으로 닫힌 뒤에는 다시 눌러 연다
    await R.submit('저장');
    ok(R.state().modal.open === false, 'submit: 모달 헤더 [저장] 이 모달을 닫았다', R.state().modal);
    const o3 = await R.open(spec);
    ok(o3.status === 'ok', 'open: 닫힌 뒤에는 다시 눌러 연다', o3.status);
    await R.close();
    ok(R.state().modal.open === false, 'close: 모달을 닫았다', R.state().modal);
    await R.tab('객실');
  }

  // 12k. 페이지 우상단 [저장] — **기본정보 폼 전체 저장** (2026-09-10 운영 호텔 실측).
  //      이미지 모달의 헤더 [저장] 은 `contents_imagecontent` 행만 만들고, 호텔과 사진의
  //      연결(`fit_masterimages`)은 기본정보 폼이 저장될 때 생긴다 — ERP `fit/views/master.py`
  //      의 `after_save_model` 이 `main_image_sort`·`image_sort` 를 읽어 bulk_create 한다.
  //      모달까지만 저장하고 끝내 고객 화면에 "사진 준비 중" 이 떴다(DB 연결 0행).
  {
    await R.close();
    await R.tab('기본정보');
    win.__pageSaveClicks = 0;
    win.__pageSaveInvalid = false;
    win.document.getElementById('toast-container').innerHTML = '';

    // 모달 안에도 `id="save"` 인 저장 버튼을 두는 화면이 ERP 에 있다 — 페이지 머리 것을 골라야 한다
    const pb = R.pageSaveButton();
    ok(!!pb && !!pb.closest('.right_header'),
      'pageSaveButton: 페이지 머리(.right_header)의 [저장] 을 고른다', pb && pb.outerHTML);
    ok(!!pb && !pb.closest('.modal'),
      'pageSaveButton: 모달 안의 같은 id 버튼은 고르지 않는다', pb && pb.outerHTML);

    // 모달이 열려 있는 동안에는 누르지 않는다 — 사진이 화면에 붙기 전에 폼을 굳히면 안 된다
    await R.open({ button: '이미지 직접등록' });
    const blocked = await R.pageSave();
    ok(blocked.status === 'blocked' && blocked.reason === 'modal',
      'pageSave: 모달이 열려 있으면 누르지 않는다', blocked);
    ok(win.__pageSaveClicks === 0, 'pageSave: 막혔으면 버튼을 아예 안 눌렀다', win.__pageSaveClicks);
    ok(blocked.saved === false, 'pageSave: 막힌 것은 저장이 아니다', blocked.saved);

    // 모달 헤더 [저장] 으로 사진을 화면에 붙인 뒤라야 폼 저장이 뜻을 갖는다
    await R.submit('저장');
    const ps = await R.pageSave();
    ok(ps.status === 'settled' && ps.saved === true, 'pageSave: 폼 저장이 안내 띠로 끝났다', ps);
    ok(win.__pageSaveClicks === 1, 'pageSave: 페이지 머리의 버튼을 한 번 눌렀다', win.__pageSaveClicks);
    ok(/저장되었습니다/.test(ps.toast || ''), 'pageSave: 안내 띠 글자를 그대로 돌려준다', ps.toast);
    ok((ps.errors || []).length === 0, 'pageSave: 성공 띠를 오류로 세지 않는다', ps.errors);
    ok(ps.toastNew === true, 'pageSave: 이번 저장으로 새로 뜬 띠임을 toastNew 로 알려 준다', ps.toastNew);

    // 12k-2. **앞 저장의 띠가 안 사라진 판** — 2026-09-21 운영 실행에서 두 번 났다.
    //        지금 ERP 의 Materialize 띠는 `display:flex` 로 60초 넘게 화면에 남는다. 그 뒤의
    //        저장은 띠 **글자**가 똑같아서(`저장되었습니다.`) 종전 판정(글자 견주기)은 새 띠를
    //        영영 못 봤고, POST(`/fit/master/<id>/change/` → 302 → GET)가 잘 끝났는데도
    //        `pageSave:'timeout'` 으로 러너가 섰다. 혼자 부를 때만(앞 띠가 없을 때) 멀쩡했다.
    //        그래서 글자가 아니라 **마디(노드)** 로 가린다.
    win.document.getElementById('toast-container').innerHTML =
      '<div class="toast">저장되었습니다.</div>';                 // 앞 단계의 묵은 띠
    const staleToast = win.document.querySelector('#toast-container .toast');
    ok(/저장되었습니다/.test(R.state().toast || ''),
       'fixture: 묵은 띠가 화면에 그대로 떠 있다(글자가 새 띠와 같다)', R.state().toast);
    win.__pageSaveClicks = 0;
    const t2k = Date.now();
    const ps2 = await R.pageSave();
    ok(ps2.status === 'settled' && ps2.saved === true,
       'pageSave: 앞 띠와 글자가 같아도 새 띠를 알아본다 (종전에는 timeout 이었다)', ps2);
    ok(ps2.toastNew === true, 'pageSave: 마디가 갈렸음을 toastNew 로 알려 준다', ps2.toastNew);
    ok(win.document.querySelector('#toast-container .toast') !== staleToast,
       'fixture: 저장이 띠 마디를 새로 갈아 끼웠다 — 글자만 같다');
    ok(Date.now() - t2k < 3000, 'pageSave: 묵은 띠에 걸려 천장(10초)까지 매달리지 않는다', Date.now() - t2k);
    ok(win.__pageSaveClicks === 1, 'pageSave: 그래도 버튼은 한 번만 누른다', win.__pageSaveClicks);

    // 12k-3. 띠가 **아예 안 갈리는** 판 — 그물(끝난 요청)로 끝을 안다.
    //        폼 저장은 htmx 가 아니라 제 손으로 쓴 ajax 라 `hx.pending`·`swaps`·`settles` 가
    //        한 번도 안 움직인다. `netWatch` 가 세어 둔 `xhrPending`·`xhrDone`·`xhrLast` 를
    //        여기서 읽는다(위 jsdom 없는 절이 `netWatch` 자체를 따로 시험한다).
    const pbtn3 = R.pageSaveButton();
    const origClick = pbtn3.onclick;
    win.__pageSaveClicks = 0;
    pbtn3.onclick = () => {
      win.__pageSaveClicks++;
      const h = R.hx;                                            // `window.__stayRunHtmx` 와 같은 객체다
      h.xhrPending = (h.xhrPending || 0) + 1;
      win.setTimeout(() => {                                     // 302 를 따라간 뒤 200 으로 끝난다
        h.xhrPending = 0;
        h.xhrDone = (h.xhrDone || 0) + 1;
        h.xhrLast = { url: '/fit/master/43900/change/', status: 200 };
      }, 120);
    };
    const t3k = Date.now();
    const ps3 = await R.pageSave();
    pbtn3.onclick = origClick;
    ok(ps3.status === 'settled' && ps3.saved === true,
       'pageSave: 띠가 안 갈려도 끝난 요청으로 저장을 읽는다', ps3);
    ok(ps3.xhr && ps3.xhr.status === 200 && /\/change\//.test(ps3.xhr.url),
       'pageSave: 그물로 본 응답 코드와 주소를 xhr 로 돌려준다', ps3.xhr);
    ok(!ps3.toastNew, 'pageSave: 새 띠가 없었으면 toastNew 를 달지 않는다', ps3.toastNew);
    ok(Date.now() - t3k < 3000, 'pageSave: 그물로 보면 천장까지 기다리지 않는다', Date.now() - t3k);
    ok(win.__pageSaveClicks === 1, 'pageSave: 버튼을 한 번 눌렀다', win.__pageSaveClicks);

    // 엉뚱한 주소로 끝난 요청은 저장으로 세지 않는다 — 배경 조회가 저장을 흉내 내면 안 된다
    win.__pageSaveClicks = 0;
    pbtn3.onclick = () => {
      win.__pageSaveClicks++;
      const h = R.hx;
      h.xhrPending = (h.xhrPending || 0) + 1;
      win.setTimeout(() => {
        h.xhrPending = 0;
        h.xhrDone = (h.xhrDone || 0) + 1;
        h.xhrLast = { url: '/common/ping/', status: 200 };
      }, 120);
    };
    R.config({ waitMs: 1200 });                                  // 천장까지 가는 시험이라 잠깐 낮춘다
    const ps4 = await R.pageSave();
    R.config({ waitMs: 10000 });
    pbtn3.onclick = origClick;
    ok(ps4.status === 'timeout' && ps4.saved === false,
       'pageSave: 저장 주소가 아닌 요청은 끝난 표시로 세지 않는다', ps4);
    ok(!ps4.xhr, 'pageSave: 그러면 xhr 도 달지 않는다', ps4.xhr);

    // 필수 칸이 비어 있으면 ERP 는 요청을 아예 보내지 않고 칸에 `.not-valid` 만 붙인다
    // (`common/error.ts`). 안내 띠도 안 뜨므로 이것을 못 읽으면 저장된 줄로 오해한다.
    win.__pageSaveInvalid = true;
    win.document.getElementById('toast-container').innerHTML = '';
    const inv = await R.pageSave();
    ok(inv.status === 'invalid' && inv.saved === false,
      'pageSave: 필수 칸이 비면 저장이 안 된 것으로 읽는다', inv);
    ok((inv.invalid || []).some((x) => /상품명/.test(x)), 'pageSave: 어느 칸이 비었는지 알려 준다', inv.invalid);
    win.__pageSaveInvalid = false;
    [].slice.call(win.document.querySelectorAll('.not-valid')).forEach((el) => el.classList.remove('not-valid'));
    win.document.getElementById('toast-container').innerHTML = '';
    await R.tab('객실');
  }

  // 13. 진행 표시 띠 — 화면 오른쪽 위에 늘 떠 있는 한 줄. 지켜보는 사람이 콘솔 없이도 읽는다.
  const strip = () => win.document.getElementById('stay_progress');
  const stripText = () => (strip() ? strip().textContent : '');
  const P1 = R.progress({ total: 77, done: 11, skipped: 1, current: '룸 만들기 (2번째, 씨뷰 빌라)' });
  ok(!!strip(), 'progress: 띠를 화면에 붙인다');
  ok(/12 \/ 77/.test(stripText()), 'progress: 처리한 수 / 전체 수', stripText());
  ok(/지금:/.test(stripText()) && /룸 만들기/.test(stripText()), 'progress: 지금 하는 단계를 적는다', stripText());
  ok(/완료 11/.test(stripText()), 'progress: 완료 수', stripText());
  ok(/건너뜀 1/.test(stripText()), 'progress: 건너뛴 수', stripText());
  ok(P1.done === 11 && P1.skipped === 1 && P1.total === 77 && P1.status === 'running',
    'progressState: 지금 값을 그대로 돌려준다', P1);
  ok(JSON.stringify(R.progressState()) === JSON.stringify(P1), 'progressState: progress 가 돌려주는 것과 같다', R.progressState());

  // 준 값만 덮는다 — 나머지는 그대로 있어야 한다
  const P2 = R.progress({ done: 12 });
  ok(P2.total === 77 && P2.current === '룸 만들기 (2번째, 씨뷰 빌라)', 'progress: 준 값만 덮고 나머지는 그대로 둔다', P2);

  // 실패해도 그 단계 제목은 남는다 — 어느 단계에서 깨졌는지 띠만 보고 알아야 한다
  const P3 = R.progress({ failed: 1, current: '시즌 만들기' });
  ok(P3.status === 'failed', 'progress: 실패가 있으면 상태가 실패다', P3);
  ok(/시즌 만들기/.test(stripText()), 'progress: 실패해도 그 단계 제목을 보여 준다', stripText());

  // 전체 수를 다 채우면 끝
  const P4 = R.progress({ failed: 0, done: 76 });
  ok(P4.status === 'done', 'progress: 전체 수를 채우면 상태가 끝이다', P4);
  ok(/^끝 · /.test(stripText()), 'progress: 끝나면 앞에 `끝` 을 붙인다', stripText());

  // 화면 조각이 통째로 갈려도(htmx) 다시 붙는다
  strip().remove();
  ok(!strip(), 'progress: 띠를 화면에서 떼어 냈다');
  R.progress({});
  ok(!!strip(), 'progress: 화면 조각이 갈려 없어져도 다시 붙인다');

  const xbtn = strip().querySelector('button');
  ok(!!xbtn && xbtn.getAttribute('aria-label') === '진행 표시 닫기', 'progress: 닫기 단추가 있다', xbtn && xbtn.outerHTML);

  // 도우미를 다시 주입해도 띠는 하나다(멱등)
  win.eval(readFileSync(join(here, '..', 'scripts', 'stay_helper.js'), 'utf8'));
  win.stayRun.progress({});
  ok(win.document.querySelectorAll('#stay_progress').length === 1, 'progress: 다시 주입해도 띠가 둘로 늘지 않는다',
    win.document.querySelectorAll('#stay_progress').length);

  // 13z. 지우기는 맨 끝에 둔다 — 지운 뒤에는 아무리 불러도 다시 붙지 않으므로 위 시험을 망가뜨릴 수 있다
  xbtn.click();
  ok(!strip(), 'progressHide: ✕ 를 누르면 띠가 사라진다');
  win.stayRun.progress({ done: 1 });
  ok(!strip(), 'progressHide: 지운 뒤에는 다시 붙지 않는다');
  ok(win.stayRun.progressHide().done === 1, 'progressHide: 이미 지웠어도 지금 값을 돌려준다');

  // 14. 적용 범위 카드 (2026-09-21 배포) — 축마다 `포함`·`제외` 줄이 있고 **두 축이 같은 표에** 선다.
  //     지시서는 `요금제 포함` 처럼 축을 앞에 붙여 적는데 화면 머리칸은 `포함` 한 낱말이라,
  //     이름만으로 찾으면 ① 어느 축인지 못 가리고 ② `조식 포함` 같은 체크박스 글자에 걸린다.
  win.openFragment('stay_promotion_form', '프로모션 추가 — 2026 계약');
  const promo = { card: '프로모션' };
  const r14 = await R.fill([
    { label: '프로모션명', kind: 'typed', value: '얼리버드' },
    { label: '요금제 한정', kind: 'empty' },
    { label: '요금제 적용 범위', kind: 'select', value: '지정한 대상만' },
    { label: '요금제 포함', kind: 'multi', values: ['조식 포함', '룸온리'] },
    { label: '요금제 제외', kind: 'empty' },
    { label: '객실 적용 범위', kind: 'select', value: '구조 적격 전체' },
    { label: '객실 포함', kind: 'empty' },
    // 값이 하나뿐인 줄은 파서가 `select` 로 낸다(`선택: A`) — 체크 묶음에서도 같은 길로 켜져야 한다
    { label: '객실 제외', kind: 'select', value: '가든 윙 · Suite Ocean' }
  ], promo);
  // `비움` 줄이 `skipped` 로 끝나는 것은 정상이다 — 그 줄이 아직 접혀 있으면 비울 것도 없다
  // (이 픽스처는 일부러 200ms 늦게 펼친다 — 실제 화면의 Alpine 은 같은 틱에 편다).
  const bad14 = r14.filter((x) => x.status !== 'ok' && x.status !== 'skipped');
  ok(bad14.length === 0, 'fill: 적용 범위 줄이 모두 ok', bad14);
  ok(q('[name=scope_rate_plan_mode]').value === '2', 'DOM: 요금제 축 = 지정한 대상만', q('[name=scope_rate_plan_mode]').value);
  ok(q('[name=scope_room_mode]').value === '1', 'DOM: 객실 축 = 구조 적격 전체', q('[name=scope_room_mode]').value);
  const on = (name) => [].slice.call(win.document.querySelectorAll('[name=' + name + ']'))
    .filter((b) => b.checked).map((b) => b.parentElement.textContent.trim());
  ok(JSON.stringify(on('scope_rate_plan_include')) === JSON.stringify(['조식 포함', '룸온리']),
    'DOM: 요금제 포함에 고른 둘이 켜졌다', on('scope_rate_plan_include'));
  ok(on('scope_rate_plan_exclude').length === 0, 'DOM: 요금제 제외는 비었다', on('scope_rate_plan_exclude'));
  ok(JSON.stringify(on('scope_room_exclude')) === JSON.stringify(['가든 윙 · Suite Ocean']),
    'DOM: 객실 제외에 스위트만 켜졌다', on('scope_room_exclude'));
  ok(on('scope_room_include').length === 0, 'DOM: 객실 포함은 비었다', on('scope_room_include'));
  // 옛 칸(`요금제 한정`)으로 새지 않았는지 — 그 셀렉트는 `조식 포함` 을 옵션으로 들고 있다
  ok(q('[name=rate_plan]').value === '', 'DOM: 옛 칸 `요금제 한정` 은 그대로 비어 있다', q('[name=rate_plan]').value);
  // 포함·제외 줄은 모드를 고친 **뒤에** 서므로 1차에서 못 찾고 2차 재시도가 잡는다
  ok(r14[3].retried === true, 'fill: `요금제 포함` 은 2차 재시도에서 잡혔다', r14[3]);
  const rb14 = R.readback([
    { label: '요금제 포함', kind: 'multi', values: ['조식 포함', '룸온리'] },
    { label: '객실 제외', kind: 'multi', values: ['가든 윙 · Suite Ocean'] }
  ], promo);
  ok(rb14.mismatch.length === 0, 'readback: 적용 범위 줄을 같은 자리에서 되읽는다', rb14.mismatch);

  // 14b. 전면 거부 확인란 — 지시서가 `Y` 로 적고 파서가 체크로 옮긴 칸이다.
  const r14b = await R.fill([
    { label: '객실 적용 범위', kind: 'select', value: '지정한 대상만' },
    { label: '범위를 비운 채 저장', kind: 'check' }
  ], promo);
  ok(r14b.every((x) => x.status === 'ok'), 'fill: 확인란까지 ok', r14b);
  ok(q('[name=scope_confirm_deny_all]').checked === true, 'DOM: 범위를 비운 채 저장이 켜졌다');

  // 14c. 축이 `기존 범위 그대로` 면 그 줄은 화면에 없다 — 도우미는 찾지 못했다고 말해야 한다.
  await R.fill([{ label: '요금제 적용 범위', kind: 'select', value: '기존 범위 그대로' }], promo);
  await R.sleep(300);   // 이 픽스처는 200ms 뒤에 접는다(실제 화면은 같은 틱에 접힌다)
  const before14c = on('scope_rate_plan_include').join(',');
  const r14c = await R.fill([{ label: '요금제 포함', kind: 'multi', values: ['조식 포함'] }], promo);
  ok(r14c[0].status === 'not-found', 'fill: 접힌 축의 포함 줄은 찾지 못한다(조용히 다른 칸에 쓰지 않는다)', r14c[0]);
  ok(on('scope_rate_plan_include').join(',') === before14c, 'DOM: 접힌 줄의 체크는 그대로다', on('scope_rate_plan_include'));
  ok(q('[name=rate_plan]').value === '', 'DOM: 접힌 줄의 값이 옛 칸으로 새지 않았다', q('[name=rate_plan]').value);

  // 15. settleOr 가 도우미 밖으로도 서 있다 — 부트의 가격 셀 단계가 같은 것을 쓴다
  ok(typeof R.settleOr === 'function', 'stayRun.settleOr 이 선다');
  let t15 = Date.now();
  ok((await R.settleOr(() => true, 900)) === true && Date.now() - t15 < 60,
     'settleOr: 화면 위에서도 참이면 기다리지 않는다', Date.now() - t15);
  t15 = Date.now();
  ok((await R.settleOr(() => false, 200)) === false && Date.now() - t15 >= 180,
     'settleOr: 화면 위에서도 끝내 아니면 종전 값에서 끊는다', Date.now() - t15);
  // 화면 상태를 조건으로 준 꼴 — 칸이 서는 것을 보고 끝낸다
  const box15 = win.document.createElement('div');
  win.setTimeout(() => { box15.id = 'stay_test_late'; win.document.body.appendChild(box15); }, 60);
  t15 = Date.now();
  const hit15 = await R.settleOr(() => !!win.document.getElementById('stay_test_late'), 1000);
  ok(hit15 === true && Date.now() - t15 < 400, 'settleOr: 칸이 서는 것을 보고 끝낸다', Date.now() - t15);
  box15.remove();

  // 16. 저장·열기 천장 — 화면 위에서도 `stayRun.config({waitMs})` 로 바꾼다
  ok(typeof R.config === 'function', 'stayRun.config 이 선다');
  ok(R.config().waitMs === 10000, 'config: 화면 위에서도 기본은 10초다', R.config());
  ok(R.config({ waitMs: 40000 }).waitMs === 40000 && R.config().waitMs === 40000, 'config: 천장을 올린다');
  ok(R.config({ waitMs: 10 }).ok === false && R.config().waitMs === 40000, 'config: 너무 작은 값은 거부한다');

  // 17. 조각이 아직 안 그려졌으면 버튼을 다시 찾아본다 (2026-09-21 운영 실측 결함)
  //     — 드로어를 닫는 저장 뒤 ERP 가 탭을 조각 아홉 벌로 다시 그리는 사이에 다음 단계가
  //       [연령 구간 추가] 를 찾다가 `open:'not-found'` 로 났다. 2초 뒤에 부르니 그대로 됐다.
  ok(typeof R.settleRefresh === 'function', 'stayRun.settleRefresh 이 선다');
  const hx17 = win.__stayRunHtmx;
  hx17.pending = 0; hx17.requests = 0;
  const tRef = Date.now();
  const ref17 = await R.settleRefresh(5000, 300);
  ok(typeof ref17 === 'number' && Date.now() - tRef < 400,
     'settleRefresh: 잠잠하면 한 틱만 쓰고 걸린 시간을 돌려준다', ref17);
  R.config({ waitMs: 1000 });          // 아래 두 시험이 빨리 끝나도록 잠깐 낮춘다
  const tMiss = Date.now();
  const miss17 = await R.open({ button: '있지도 않은 버튼 ZZZ' });
  ok(miss17.status === 'not-found' && Date.now() - tMiss < 600,
     'open: 화면이 잠잠하면 없는 버튼은 그 자리에서 not-found 다', { ms: Date.now() - tMiss, st: miss17.status });
  let clicked17 = 0;
  hx17.pending = 1; hx17.requests = 1;   // 조각이 아직 오는 중이다
  win.setTimeout(() => {
    const b = win.document.createElement('button');
    b.textContent = '늦게 오는 버튼';
    b.addEventListener('click', () => { clicked17++; });
    win.document.body.appendChild(b);
    hx17.pending = 0;
  }, 150);
  const late17 = await R.open({ button: '늦게 오는 버튼' });
  ok(late17.status !== 'not-found' && clicked17 === 1,
     'open: 그리는 중이면 최대 3초까지 다시 찾아 누른다', { st: late17.status, clicked: clicked17 });
  hx17.pending = 0; hx17.requests = 0;
  R.config({ waitMs: 10000 });

  console.log('\n' + pass + ' 통과 · ' + fail + ' 실패');
  process.exit(fail ? 1 : 0);
};

run().catch((e) => { console.error(e); process.exit(1); });
