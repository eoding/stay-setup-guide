---
name: stay-setup-run
description: "입력 지시서(`<이름>_입력지시서.html` 또는 manual.md)를 사용자가 로그인해 둔 크롬 탭에서 그대로 실행해 ERP Stay 화면을 1단계부터 채우고 저장한다. '설명서대로 ERP에 깔아줘', '입력지시서 실행', '호텔 자동 세팅', '지시서대로 브라우저에서 입력해줘', 'run the stay setup guide in the browser' 요청에 쓴다. [판매 시작] 은 절대 누르지 않는다."
version: 0.2.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [erp, stay, hotel, browser, run, automation]
    related_skills: [stay-setup-guide]
---

# 입력 지시서 실행하기

`stay-setup-guide` 가 만든 지시서가 계획이고, 이 스킬이 실행이다. **지시서에 적힌 값만** 화면에 넣는다.
지시서에 없는 값은 판단하지 않고 사용자에게 묻는다. **[판매 시작] 은 사용자가 누른다.**

화면의 동작(탭·드로어·모달·배너·위젯)은 `references/screen-mechanics.md`, 로그 형식은 `references/run-log-spec.md` 가 정본이다.

## 입력

1. 공유 폴더: `<이름>_입력지시서.html`(필수) + `사진/`. 같은 폴더에 `manual.md` 가 있으면 그것을 먼저 읽는다.
2. 사용자가 로그인해 둔 크롬 탭. 호텔 목록 화면에서 시작하거나, 이미 만든 호텔의 편집 화면에서 이어서 한다. **주소는 사용자에게 받는다 — 이 스킬은 주소를 모른다.**
3. 옵션: `--title-prefix`(호텔명·상품명 앞에 붙일 접두, 시험용), `--photos`(사진 폴더), 모드(연속/검토).

사진과 도우미 파일은 **브라우저 도구가 읽을 수 있는 폴더**(프로젝트 경로)에 있어야 하고, 한 번에 **10MB** 까지 올라간다. 장당 4~5MB 사진이면 1~3장씩 나눠 올린다.

## 준비

```bash
python3 scripts/parse_guide.py <지시서 또는 공유 폴더> --photos <사진 폴더> --title-prefix <접두> -o <실행 폴더>/steps.json
npx esbuild scripts/stay_helper.js --minify --outfile=<실행 폴더>/stay_helper.min.js
npx esbuild scripts/stay_boot.js   --minify --outfile=<실행 폴더>/stay_boot.min.js
```

- 요약에 `알 수 없는 값`·`없는 사진` 이 있으면 그 목록을 **먼저 사용자에게 보여 주고** 시작한다. 사진이 없는 단계는 건너뛰고 로그에 남긴다.
- 산출물은 공유 폴더 옆 `<공유 폴더명>_실행/` 에 둔다(`steps.json`, `stay_helper.min.js`, `stay_boot.min.js`, `run-log.md`).
- minify 는 브라우저 JS 도구의 한 번 호출 크기를 줄이려는 것이다. esbuild 가 없으면 원본 파일을 그대로 올려도 된다.
- 탭이 편집 화면이면 `호텔 만들기` 단계는 `건너뜀 · 이미 있음` 으로 두고 이어서 한다.

## 페이지에 도우미 올리기 (파일 다리)

브라우저 JS 도구는 한 호출이 **45초**에서 끊기고 긴 글자를 넣기 힘들다. 그래서 파일을 **페이지 안 파일 칸(파일 다리)** 으로 올리고, 페이지가 스스로 읽게 한다.

1. `scripts/stay_helper.js` 내용을 **그대로 한 번 실행**한다 → `window.stayRun` 이 생긴다(두 번 넣어도 안전).
2. `stayRun.bridge()` 로 파일 다리를 만든다 — 숨은 `input#stay_file_bridge`(aria-label `stay file bridge`).
3. 브라우저 업로드 도구로 `stay_helper.min.js` · `stay_boot.min.js` · `steps.json` 을 그 다리에 올린다.
4. 페이지 안에서 `FileReader` 로 읽어 `localStorage` 에 `stayHelperSrc` · `stayBoot` · `staySteps` 로 저장하고 `stayRun.clearBridge()`.
5. 부트:

```js
(0,eval)(localStorage.getItem('stayHelperSrc'));   // window.stayRun
(0,eval)(localStorage.getItem('stayBoot'));        // step · stepFields · titleHint · existsInList · runStep · runCellStep · runWarnStep
```

- **화면이 통째로 넘어간 뒤에는 5번 두 줄만 다시 실행**한다. 파일은 다시 올리지 않는다.
- 부트는 `staySteps` 를 메모리에 올려 둔다. **localStorage 의 단계 값을 고쳤으면 부트를 다시 eval** 해야 반영된다.
- 도우미는 서버로 요청을 보내지 않는다. 화면의 칸과 버튼만 다룬다.

자주 쓰는 도우미:

```js
stayRun.state()                    // {url, hotelId, loginPage, logoutWarning, drawer, modal, activeTab, banner, toast}
stayRun.tab("객실") · stayRun.open({button, row, card, block}) · stayRun.fill(fields)
stayRun.submit("저장")             // {status:"closed|stayed|navigated|login|timeout|refused|not-found", errors, toast}
stayRun.readback(fields) · stayRun.fileInputs() · stayRun.takeFiles({label, index, names, wait})
stayRun.bridge() · stayRun.clearBridge() · stayRun.sleep(ms) · stayRun.waitFor(fn, ms) · stayRun.findButton(scope, "저장")
```

## 단계 반복

`steps.json` 의 단계를 **번호 순서대로** 돈다. 한 번의 JS 호출에 **3~10 단계**, 단계마다 시간 제한을 걸고 누적 **30초** 예산에서 끊는다.

```js
(async () => {
  const out = [];
  for (const n of [12,13,14,15,16]) {
    const r = await Promise.race([runStep(n), stayRun.sleep(12000).then(() => ({no:n, timeout:true}))]);
    out.push(r);
    if (r.timeout || (r.bad && r.bad.length) || (r.submitted && r.submit !== 'closed')) break;
  }
  return out;
})()
```

- 뒤로 간 탭은 크롬이 페이지 타이머를 늦춘다. 도우미의 대기는 워커 타이머로 재므로 탭을 앞에 두지 않아도 되지만, **스크린샷은 탭이 앞에 있어야** 찍힌다.
- `runStep` 이 돌려주는 키: `open`·`openDetail`·`fill`·`bad`·`warn`·`mismatch`·`submit`·`submitAs`·`skipped`·`cardPick`·`rowHint`·`uploads`.
- `bad`(칸 못 찾음·후보 여럿)가 하나라도 있으면 **저장하지 않고** 그 단계에서 멈춘다.
- `submit` 이 `closed` 가 아니면 화면을 보고 판단한다. `skipped: true` 는 같은 이름이 이미 목록에 있어 건너뛴 것이다(정상).
- `mismatch`(되읽기 불일치)는 대개 되읽기의 한계다 — 포함물 행, 제공 주기, 요금제 scope, 정률 값, 침대 구성. **화면 값을 따로 확인**하고 맞으면 로그 비고에 `되읽기만` 이라고 적는다.
- 지시서의 저장 글자와 화면 버튼 글자가 다르면(시즌 드로어는 [추가]) 도우미가 `저장·추가·만들기·등록·확인` 을 차례로 시도하고 `submitAs` 로 알려 준다.

## 화면이 통째로 바뀌는 단계

- **호텔 만들기** — 목록의 [호텔 만들기] 는 전체 화면 폼이다. `stayRun.fill(stepFields(n))` 로 채우고 [호텔 만들기] 를 누른 뒤, **스크린샷을 한 번 찍어 JS 컨텍스트를 다시 맞추고** 새 편집 화면에서 부트를 다시 eval 한다. 호텔 번호는 `stayRun.state().hotelId` 로 읽어 로그 머리에 적는다.
- **기본정보 글 입력 · 호텔 정보 입력** — 저장이 전체 화면 저장이라 `submit` 이 `timeout` 으로 보일 수 있다. **스크린샷과 토스트("저장되었습니다")로 확인**하고 완료로 적는다.
- **캠페인 만들기** — 더 이상 지시서에 나오지 않는 단계다(캠페인은 걷혔고 오퍼가 `오퍼 이미지` 로 겉면을 갖는다). 이 단계가 보이면 실행하지 말고 멈춰서 보고한다.

## 사진 단계

1. `runStep(n, {dry:true})` — 드로어·모달만 열고 값까지만 채운다.
2. 드로어 제목이 **대상 룸인지 확인**한다.
3. 파일 다리에 그 단계의 사진만 올린다(10MB 넘으면 나눠서).
4. 옮겨 담기:
   - 룸 사진(여러 장 한 번에): `stayRun.takeFiles({label:'사진 추가', names:[...], wait:2500})`
   - 기본정보 이미지 모달(**한 번에 한 장**): `stayRun.takeFiles({index:0, names:['<파일 1개>'], wait:1200})` → 장수만큼 반복
5. `stayRun.submit('저장')` → `stayRun.clearBridge()`.

파일 대화상자를 못 다루는 브라우저 도구면 사진 단계는 `건너뜀 · 사용자 업로드 필요` 로 남기고 계속한다.

## 단계가 실패했을 때

1. `runStep(n, {dry:true})` 로 열기만 해 보고 `stayRun.fields()` · `stayRun.buttons()` · `stayRun.state()` 로 화면에 뭐가 있는지 본다.
2. 스크린샷을 찍어 사용자에게 보인다.
3. 화면과 지시서가 다르면 **페이지 안 단계 값만** 고쳐 다시 돌린다(`localStorage.staySteps` 수정 → 부트 다시 eval). 고친 이유를 **로그 비고에 반드시 남긴다**.
4. **저장소의 `steps.json` 과 지시서는 고치지 않는다.** 지시서 결함은 아래 `지시서 쪽에 요청할 것` 으로 모아 보고한다.
5. 두 번 실패하면 멈추고 사용자에게 묻는다.

## 반드시 지킬 것
- **판매 시작 전 배너 🟡 0 이 합격선이다.** `경고 넘어가기` 로 사유를 적고 넘기지 않는다 — 🟡 가 남으면 지시서 결함이므로 원인을 지시서에서 고쳐 다시 깐다.
- **호텔 만들기 전에 지시서의 `공급 통화` 를 본다.** USD 가 아니면 호텔을 만들지 말고 사용자에게 그 통화가 맞는지 확인받는다. 러너는 통화도 금액도 바꾸지 않는다 — 지시서에 적힌 대로만 넣는다.

- **[판매 시작] 은 누르지 않는다.** 도우미가 거부하고 `force` 로도 안 된다. 검증 배너를 확인하고 판매를 시작하는 것은 사용자다.
- **위험 버튼**([삭제]·[보관]·[N월 닫기]·[공용으로]·[그룹 삭제]·[판매 종료])은 러너가 거부한다(`refused`). 지시서가 요구하면 **감독하는 에이전트나 사람이 대상 행을 눈으로 확인한 뒤** 직접 누른다. 확인창(hx-confirm)은 페이지 안에서 대체한 뒤 누르고, 무엇을 왜 눌렀는지 로그 `마무리` 에 적는다.
- **만들기 단계는 같은 이름이 목록에 이미 있으면 건너뛴다**(`existsInList`). 오퍼별 카드가 있는 화면은 그 카드 안에서만 본다.
- 호텔 만들기가 만들어 두는 `기본 오퍼`·룸 `스탠다드`·자동 연결행·`기본 요금제` 는 **새로 만들지 말고 고쳐 쓴다.**
- `거래처` 는 지시서 값 그대로 고른다(계약 주체가 `자사` 면 `자사`). 고르면 수수료 네 칸이 저절로 차니 `자동 입력됨 · 그대로 둠` 은 건드리지 않는다.
- `도시` 는 지시서 값(한글명(공항코드)) 그대로 검색해 고른다. 화면 목록에 없으면 **멈추고 지시서 쪽을 고친다** — 비슷한 도시를 대신 고르지 않는다.
- 지시서에 없는 값을 지어내지 않는다. 비어 있으면 비운 채 두고 마지막 보고에 적는다.
- 로그인 화면이 나오면 즉시 멈춘다. 비밀번호는 대신 넣지 않는다. 로그아웃 경고가 뜨면 `stayRun.keepAlive()`.

## 하지 말 것

- 내부 요청 경로·API 를 부르지 않는다. 화면 조작만 한다.
- 지시서에 없는 호텔·오퍼·룸·요금제를 새로 만들지 않는다.
- 드로어를 연 채 새로 고치지 않는다. 닫고(`stayRun.close()`) 다시 연다.
- 값 넣기에 브라우저의 폼 입력 도구를 쓰지 않는다. `stayRun.fill` 을 쓴다(라벨·위젯·자동완성 처리가 들어 있다).
- 로그의 앞 줄을 고쳐 쓰지 않는다. 다시 한 단계는 아래에 한 줄 더 붙인다.

## 실행 로그

`<공유 폴더명>_실행/run-log.md` 에 단계마다 한 줄로 적는다(형식은 `references/run-log-spec.md`).
같은 호텔을 다시 실행하면 마지막 `완료` 다음 단계부터 이어서 한다.

## 지시서 쪽에 요청할 것

실행하면서 **지시서가 화면과 맞지 않는 곳**을 모아 마지막 보고와 로그 `마무리` 에 적는다. 지금까지 나온 것:

1. 넓은 시즌 위에 좁은 시즌(Peak)을 얹는데 `이미 값이 있는 날도 덮기` 가 해제라 0셀이 깔린다 → 덮기를 체크하거나 넓은 시즌 날짜에서 그 날을 빼야 한다.
2. 같은 이름의 부가옵션이 두 오퍼에 있는데 `가격 넣기` 카드에 오퍼 한정이 없다.
3. 사본 요금제 편집 드로어에는 `기준 요금제` 체크 하나뿐인데 지시서는 정본 칸을 전부 나열한다.
4. `가격 셀 만들기` 단계인데 시즌 전개로 셀이 이미 있다 → 기존 행의 [저장] 이 맞다.
5. (정정) 프로모션 카드 `전 오퍼 공통` 은 실재한다 — 오퍼 없는 공통 프로모션이며 이 호텔의 모든 오퍼에 붙는다. 다만 공통 프로모션이 0건이면 화면이 그 카드를 감춰 첫 건을 만들 버튼이 없다(ERP 화면 개선 요청). 러너는 이때 오퍼 카드의 [프로모션 추가] 요청에서 오퍼 번호를 0으로 바꿔 공통 드로어를 연다.
6. 시즌 드로어의 저장 버튼은 [추가] 인데 지시서는 [저장] 으로 적는다.

## 끝낼 때

- 완료·건너뜀·실패·재실행 단계 수와 목록
- 되읽기 불일치와 비워 둔 칸
- `stayRun.state().banner` 의 남은 막힘(🔴)·권고(🟡)
- 감독자가 직접 누른 위험 버튼 목록
- 지시서 쪽에 요청할 것
- 마지막 줄: **"[판매 시작] 은 화면에서 직접 눌러 주세요"**
