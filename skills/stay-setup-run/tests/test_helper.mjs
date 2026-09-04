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

let JSDOM = null;
try { ({ JSDOM } = require('jsdom')); } catch (e) {
  console.log('SKIP — jsdom 이 없어 브라우저 시험을 건너뜁니다 (설치하지 않습니다).');
  console.log('       손으로 보려면 tests/helper_fixture.html 을 크롬에서 열고 콘솔에 scripts/stay_helper.js 를 붙여 넣으세요.');
  process.exit(0);
}

let pass = 0, fail = 0;
const ok = (cond, name, extra) => {
  if (cond) { pass++; console.log('  ok   ' + name); }
  else { fail++; console.log('  FAIL ' + name + (extra !== undefined ? ' — ' + JSON.stringify(extra) : '')); }
};

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

  // 5. 위험한 버튼은 거부
  const del = await R.submit('삭제');
  ok(del.status === 'refused' && del.reason === 'dangerous', 'submit: [삭제] 거부', del);
  const sale = await R.submit('판매 시작', { force: true });
  ok(sale.status === 'refused' && sale.reason === 'sale-start', 'submit: [판매 시작] 은 force 로도 거부', sale);

  // 6. 저장 → 드로어가 닫히면 closed
  const sv = await R.submit('저장');
  ok(sv.status === 'closed', 'submit: 저장 뒤 드로어가 닫히면 closed', sv);
  ok(/저장했습니다/.test(sv.toast || ''), 'submit: 안내 띠 글자를 함께 돌려준다', sv.toast);

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

  // 10. 부과금의 연령별 단가 — [부과 방식]을 고른 뒤에야 서는 카드
  win.openFragment('stay_charge_form', '부과금 추가 — 2026 계약');
  const chg = { card: '부과금' };
  const r11 = await R.fill([
    { label: '이름', kind: 'typed', value: '갈라디너' },
    { label: '부과 방식', kind: 'select', value: '인당' },
    { label: '정액 금액', kind: 'typed', value: '100' },
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
  win.document.getElementById('stay_cell_edit').style.display = 'none';

  console.log('\n' + pass + ' 통과 · ' + fail + ' 실패');
  process.exit(fail ? 1 : 0);
};

run().catch((e) => { console.error(e); process.exit(1); });
