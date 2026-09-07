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

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));

let JSDOM = null;
try { ({ JSDOM } = require('jsdom')); } catch (e) {
  console.log('SKIP — jsdom 이 없어 브라우저 시험을 건너뜁니다 (설치하지 않습니다).');
  process.exit(0);
}

let pass = 0, fail = 0;
const ok = (cond, name, extra) => {
  if (cond) { pass++; console.log('  ok   ' + name); }
  else { fail++; console.log('  FAIL ' + name + (extra !== undefined ? ' — ' + JSON.stringify(extra) : '')); }
};

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
    }
  ]
};

//: 룸 사진 올리기 — 마지막 줄이 `→ [사진 추가]` 인 단계. `버튼:` 줄은 룸 행의 [편집] 하나뿐이다.
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

  // 5) `경고 넘어가기` 는 금지된 단계다 — 실행하지 않고 거부한다(🟡 0 이 합격선)
  const r5 = await w3.runStep(2);
  ok(r5.refused === true && r5.fatal === true, 'runStep: `경고 넘어가기` 를 거부한다', r5);
  ok(/금지된 단계/.test(r5.error || ''), 'runStep: 왜 거부하는지 알려 준다', r5.error);
  ok(typeof w3.runWarnStep === 'undefined', 'runWarnStep: 갈래 자체가 없어졌다');
  ok(w3.checkGuide().some((x) => x.no === 2), 'checkGuide: 금지된 단계를 실행 전에 잡는다', w3.checkGuide());

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

  console.log('\n' + pass + ' 통과 · ' + fail + ' 실패');
  process.exit(fail ? 1 : 0);
};

run().catch((e) => { console.error(e); process.exit(1); });
