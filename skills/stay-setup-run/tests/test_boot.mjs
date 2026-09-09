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

  //    그 단계는 파일을 올린 뒤 다시 부른다 — 아직 끝난 것이 아니므로 어느 숫자에도 세지 않는다
  const p3 = w2.stayRun.progressState();
  ok(p3.done === 0 && p3.skipped === 0 && p3.failed === 0,
    'runStep: `사진 추가` 로 넘긴 단계는 아직 어느 숫자에도 세지 않는다', p3);
  ok(p3.current === PHOTO_STEPS.steps[0].title, 'runStep: 넘긴 단계 제목이 띠에 그대로 있다', p3);
  ok(p3.status === 'running', 'runStep: 넘긴 단계를 실패로 물들이지 않는다', p3);

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

  console.log('\n' + pass + ' 통과 · ' + fail + ' 실패');
  process.exit(fail ? 1 : 0);
};

run().catch((e) => { console.error(e); process.exit(1); });
