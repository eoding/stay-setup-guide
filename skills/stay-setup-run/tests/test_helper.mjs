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

  console.log('\n' + pass + ' 통과 · ' + fail + ' 실패');
  process.exit(fail ? 1 : 0);
};

run().catch((e) => { console.error(e); process.exit(1); });
