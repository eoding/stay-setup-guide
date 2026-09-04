/**
 * stay_boot.js 자동 시험 — 가격 캘린더의 셀 편집(`runCellStep`)만 본다.
 *
 *   node tests/test_boot.mjs
 *   NODE_PATH=<jsdom 이 있는 node_modules> node tests/test_boot.mjs
 *
 * jsdom 이 없으면 아무것도 설치하지 않고 건너뛴다(종료 코드 0).
 *
 * 여기서 잡는 것은 `가격 셀 만들기` 다. 그 날짜에 셀이 하나도 없으면 편집창에 표가 **하나뿐**이고
 * 그 표의 인원 칸은 셀렉트다(`_calendar_cell_edit.html` · `PriceCellForm._use_occupancy_select`).
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

  console.log('\n' + pass + ' 통과 · ' + fail + ' 실패');
  process.exit(fail ? 1 : 0);
};

run().catch((e) => { console.error(e); process.exit(1); });
