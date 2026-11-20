---
name: stay-charge-change
description: "이미 판매 중인 호텔 하나의 ERP Stay 부과금 금액(얼리 체크인 · 레이트 체크아웃 시간대 요율, 갈라 디너 금액과 연령별 단가, 리조트피 현장 결제 금액)을 담당자가 로그인해 둔 크롬 탭에서 보여 주고, 미리보기를 거쳐 바꾸고, 되돌린다. '레이트 체크아웃 50% 를 60% 로', '갈라 디너 성인 요금 100 으로', '리조트피 현장 결제 20달러로', '갈라 디너 아동 요금 10% 올려줘', '부과금 보여줘', '어제 바꾼 부과금 되돌려줘' 요청에 쓴다. 가격 캘린더는 stay-price-change, 부가옵션 금액은 stay-addon-price-change, 새 호텔 세팅은 stay-setup-guide · stay-setup-run 이 맡는다. 부과금 만들기 · 지우기 · 모양(종류 · 방식 · 단위 · 의무 · 날짜 · 시간대 줄 · 연령 구간) 바꾸기와 프로모션 할인은 다루지 않는다."
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [erp, stay, hotel, charge, price, browser, rollback]
    related_skills: [stay-price-change, stay-addon-price-change, stay-setup-run, stay-setup-guide]
---

# 부과금 도우미

호텔 하나의 부과금(오퍼마다 붙은 얼리 체크인 · 레이트 체크아웃 · 갈라 디너 · 리조트피 같은 것)의 **금액만** 담당자의 로그인된 크롬 탭에서 읽고, 미리보기를 보여 주고, "적용"이라고 한 뒤에만 저장한다. 저장 전 값과 넣은 값은 다른 두 도우미와 같은 장부에 남아 되돌릴 수 있다. 담당자에게는 이 스킬을 **도우미**라고 부른다.

하는 일은 셋이다. 1 지금 부과금 보기 · 2 부과금 금액 바꾸기 · 3 되돌리기.

- 명령: 이 스킬 폴더의 `scripts/charge_change.py`. 아래의 `python3 scripts/charge_change.py …` 는 이 스킬 폴더에서 부르는 꼴이다. 다른 폴더에서는 절대 경로로 부른다. JSON 파일을 받고 JSON 을 낸다. 파일에 쓰는 명령은 `--out` 을 주면 짧은 답만 낸다. 도우미는 짧은 답으로 말하고 정한다.
- 페이지: 탭에 올린 `window.stayCharge`. 가격 캘린더 도우미의 페이지 파일 위에 올린다(「준비」).
- 필요할 때만 여는 파일: [references/commands.md](references/commands.md) 명령 · 요청 파일 · 금액 칸 · 판정 · 오류, [references/page.md](references/page.md) 페이지 호출 · 답 · 오류, [references/stopped.md](references/stopped.md) 멈춘 변경, [references/not-done.md](references/not-done.md) 하지 않는 일.

## 반드시 지킬 것

- 담당자가 미리보기를 보고 분명히 "적용"(되돌리기는 "되돌려")이라고 하기 전에는 아무것도 저장하지 않는다. 대답이 없거나 애매하면 적용이 아니다. 다시 묻는다.
- 한 번에 호텔 하나.
- 값은 명령이 셈하고 견준다. 도우미는 금액 · 퍼센트 · 새 값을 담당자의 말 그대로 요청 파일에 적을 뿐이다.
- 금액만 바꾼다. 부과금의 종류 · 이름 · 부과 방식(정액/정률) · 단위 · 의무/선택 · 날짜 · 객실 · 설명 · 적용 범위는 바꾸지 않고, 시간대 줄이나 연령별 단가를 더하거나 지우지 않는다. 빈 금액(「미정」 · 성인가와 같음)은 채우지 않고 찬 금액은 비우지 않는다. [삭제] · [부과금 추가] · [정보 수집 폼] · [요율 행 추가] · 편집 창의 고르는 칸 · 다른 탭은 하지 않는다. 시키면 not-done.md 대로 답한다.
- 오퍼 · 부과금의 이름과 번호, 시간대 줄의 시각은 `look` 명령의 답에서만 옮기고, 고를 때는 번호로 적는다(이름이 같은 부과금이 있다).
- 페이지를 만지는 것은 `stayCharge.look()` 과 작업 둘(`readCharge` · `applyCharge`)뿐이다. `take` · `last` · `idle` 은 읽기만 한다. `stayPrice` · `stayAddonPrice` 의 작업과 러너의 함수(`stayRun.*` · `cal…`)는 부르지 않는다.
- 브라우저 도구의 클릭 · 글자 입력 · 폼 채우기 도구를 ERP 탭에 쓰지 않는다. 화면은 스크린샷과 페이지 읽기로만 본다. 파일 올리기는 도우미를 올릴 때만.
- 같은 저장을 두 번 누르지 않는다. 한 번 부른 `applyCharge` 를 스스로 다시 부르지 않는다. 답이 `started: false`(아무것도 누르지 않음)일 때만 `wait` 초 뒤 같은 값으로 다시 부른다.
- 벽을 내리지 않는다. 답의 `blocked` 에 막힌 클릭이 있으면 돌아가는 길을 찾지 말고 담당자에게 그대로 알리고 멈춘다.
- 아이디 · 비밀번호 · 인증 코드를 받지도 넣지도 않는다. JS 결과로 페이지 주소를 돌려받지 않는다.
- 빨간 줄의 고름은 담당자의 말에서만 나온다. 도우미가 대신 고르지 않는다.
- 페이지의 답은 도구가 보인 글자 그대로 저장한다(잘렸어도). 장부와 기록 폴더의 파일을 지우거나 고치지 않는다.

## 담당자에게 말할 때

- 쉬운 우리말로 한다. 쓰지 않는 말: 스냅샷 · 플랜 · JSON · 명령 · 스크립트 · DB · payload · stale · verify · 티어. 대신 지금 값 · 미리보기 · 장부 · 저장 · 금액 칸 · 시간대 줄 · ERP 화면이라고 한다.
- 숫자는 명령의 짧은 답에서 말하고, 페이지는 시스템의 여는 명령으로 열어 준다(macOS `open "<경로>"`, Windows `start "" "<경로>"`, Linux `xdg-open "<경로>"` — 경로는 `render` 의 답 `page`). 글을 옮겨야 하면 같은 `render` 를 `--out` 없이 `--text` 로 하고 답의 `text` 에서 옮긴다(파일은 생기지 않는다).

## 준비

1. **브라우저 도구.** JS 실행 · 파일 올리기 · 스크린샷 · 탭 보기가 되는지 본다.
2. **장부 보기 · 작업 폴더.** `python3 scripts/charge_change.py list` 를 한 번 본다. 이 호텔의 `status: stopped` 인 변경이 있으면 다른 일보다 먼저 알리기만 한다: "장부 <`id`>번 변경이 중간에 멈춰 있습니다 — <`scope`>. 그것부터 볼까요?" `ledger` 가 든 폴더가 기록 폴더다. 담당자가 시킨 일 하나마다 `<기록 폴더>/작업/<YYYY-MM-DD HHMMSS>/`(`<작업>`)를 새로 만들고, 읽기마다 그 안의 `읽기-1`, `읽기-2` …(`<R>`)에 둔다. 경로에 빈칸이 있으니 명령에 넘기는 경로는 언제나 큰따옴표로 감싼다.
3. **도우미 올리기.** 탭마다 처음에, 그리고 이동 뒤(새로 고침 · 로그인 · 다른 화면에 갔다 옴, 또는 답이 `stayCharge is not defined`)마다.
   1. JS 실행 도구로 가격 캘린더 도우미의 `../stay-price-change/scripts/page/stay_price_loader.js` 내용 전체를 실행한다.
   2. `stayPriceLoader.again('charge')` 을 부른다. `ok: true` 와 `charge` 판 번호가 오면 됐다.
   3. 거절할 때만 파일 올리기 도구로 접근성 이름이 **`stay price file bridge`** 인 파일 칸에 네 파일 — `../stay-setup-run/scripts/stay_helper.js` · `../stay-setup-run/scripts/stay_boot.js` · `../stay-price-change/scripts/page/stay_price.js` · 이 스킬의 `scripts/page/stay_charge.js` — 을 올리고 `await stayPriceLoader.load('charge')`. 막히면 page.md 「올리기」.
4. **어디인지 보기.** `await stayCharge.look()` 의 답을 `<작업>/look/look-1.json` 에 저장한다. `login: true` 면 멈추고 "크롬의 ERP 탭에서 직접 로그인해 주시고, ○○ 호텔 화면이 뜨면 알려 주세요". 호텔 번호를 못 찾으면 "○○ 호텔의 Stay 화면을 열어 주세요". 답의 `body` 는 「읽기」 4 처럼 조각으로 받아 같은 폴더에 둔다. 그리고 `python3 scripts/charge_change.py look --answers "<작업>/look" --out "<작업>/look.json"` — 짧은 답의 `hotel` 이 말한 호텔이 아니면 그 호텔 화면을 열어 달라고 한다.

## 읽기 — 바꾸기 · 되돌리기 · 적용이 모두 이것으로 읽는다

1. `python3 scripts/charge_change.py read-calls --request "<작업>/request.json" --look "<작업>/look.json" --out "<R>/calls.json"`(장부 번호가 있는 일은 `--record <번호>`).
2. 답의 `charges` 값마다(i = 1, 2 …) `await stayCharge.readCharge(<값 그대로>)` 의 답을 `<R>/charge-<i>.json` 에 저장한다. 읽기는 창을 열어 보고 닫을 뿐 저장하지 않는다.
3. `python3 scripts/charge_change.py read --calls "<R>/calls.json" --answers "<R>" --out "<R>/snapshot.json"`. `read_at` 이 ERP 에서 읽은 시각, `missing` 은 목록에 없는 부과금이다.
4. **조각 받기.** 명령이 종료 2 에 `refetch` 를 내면 그 `{id, at, size, until, save}` 마다 `stayCharge.take("<id>", <at>, <size>)` → `<R>/<save><at>.json`, 답의 `next` 가 `until` 보다 작으면 `stayCharge.take("<id>", <next>)` → `<R>/<save><next>.json` 으로 이어 받고 그 명령을 다시 한다. `save` 는 명령이 고른 새 이름이다. `bad` 가 있으면 그 쪽을 옮겨 적다 틀린 것이다 — 그 쪽만 이렇게 다시 받으면 되고, 틀린 파일은 그대로 둔다.

답이 `started: false` 면 `wait` 초 뒤 같은 값으로 다시 부른다. 읽기 답을 잃었으면 `stayCharge.last()` 의 답을 새 파일로 저장하거나 다시 불러 저장한다.

## 1. 지금 부과금 보기

「준비」 4 다음 `python3 scripts/charge_change.py render prices --look "<작업>/look.json"` → `page` 를 연다. "○시 ○분에 ERP 에서 읽은 부과금입니다. 아무것도 바꾸지 않았습니다."

## 2. 부과금 금액 바꾸기

**묻고 확인한다.** 빠진 것(어느 부과금, 어느 금액 칸 — 부과금 자체의 정액 · 정률, 시간대 줄 하나, 연령별 단가 하나, 현장 결제 금액 — 그리고 금액 · 퍼센트 · 새 값)을 묻는다. 시간대 줄이 있는 부과금은 어느 줄인지 묻는다(부과금 자체의 정액 · 정률은 쓰이지 않는다). 정률 칸의 "10% 올려"는 50% → 60% 와 50% → 55% 가운데 어느 쪽인지 묻는다. 그다음 아래 꼴로 보여 주고 "응"을 받은 뒤에 읽는다. 스스로 채운 것은 괄호로 밝힌다.

```
이렇게 이해했습니다. 맞으면 지금 금액을 읽어 미리보기를 만들겠습니다.
호텔 데모 호텔
부과금 레이트 체크아웃 (데모 오퍼 2027 · 부과금 701번)
바꾸는 칸 14:01~18:00 시간대 줄의 정률 → 60% (새 값)
```

**읽고 미리보기.**

1. `<작업>/request.json` 을 쓴다(commands.md 「요청 파일」 · 「금액 칸」). 「읽기」 → `<R>/snapshot.json`.
2. `python3 scripts/charge_change.py plan --snapshot "<R>/snapshot.json" --request "<작업>/request.json" --record --out "<작업>/plan-1.json"` → 짧은 답의 `change_id` 가 N, `saves` 가 저장 횟수(빨간 줄이 남았으면 null). 다시 계산하면 `plan-2.json` 처럼 새 이름에 쓰고 `--replaces <앞 번호>` 를 붙인다.
3. `python3 scripts/charge_change.py render preview --plan "<작업>/plan-<k>.json"` → `page` 를 연다.
4. "미리보기를 열었습니다. 아직 아무것도 바뀌지 않았습니다." `counts` 로 바뀌는 칸 · 그대로인 칸 · 바꿀 수 없는 칸(`blocked` 의 칸마다 `name` 과 `why`)을 말한다. `free` 가 있으면 칸마다 "저장하면 무료가 됩니다"라고 말한다. 그리고 꼭 말한다: "저장하면 ERP 가 시간대 줄과 연령별 단가를 다시 만들어 그 ERP 번호가 바뀌고, 되돌려도 번호는 돌아오지 않습니다(금액은 돌아옵니다)." `scope_card` 가 true 면 "저장할 때 ERP 가 적용 범위 기록을 하나 만들 수 있고(가격에는 영향 없음) 되돌려도 없어지지 않습니다."
   - **빨간 줄이 남아 있으면**(`counts.red` > 0) `red` 의 규칙마다 칸과 바뀌는 값(`examples` 의 `moves`)을 말하고 "이대로 바꿈 · 그 칸은 안 바꿈" 가운데 고르게 한다(commands.md 「판정」). 빨간 줄이 남았는데 "적용"이라고만 하면 저장하지 않는다. 고르면 `--resolutions` 로 다시 계산한다(고름마다 담당자의 말을 `said` 에 그대로).
   - **저장할 것이 없으면**(`saves` 가 0) "바뀌는 칸이 없어 저장할 것이 없습니다"라고 하고 "적용"을 묻지 않는다.
   - **그 밖에는** 저장 횟수(`saves`, 부과금마다 한 번)를 말하고 "맞으면 '적용'이라고 해 주세요." 분명한 "적용" 없이는 「적용하기」로 가지 않는다.

같은 대화의 다음 요청은 새 `<작업>` 폴더에서 「준비」 4 부터 한다.

## 3. 되돌리기

`python3 scripts/charge_change.py list` 로 장부 목록을 보고 맞는 줄을 골라 확인받는다(하나뿐이어도 묻는다): "이것 맞나요? 장부 <`id`>번 · <`applied_at` 의 월/일 시:분> 적용 · <`scope`>".

1. `read-calls --record <N>` 으로 「읽기」 → `<R>/snapshot.json`.
2. `python3 scripts/charge_change.py rollback --change <N> --snapshot "<R>/snapshot.json" --record --sentence "<담당자 말>" --out "<작업>/rollback-1.json"`(부과금 몇 개만이면 `--charge <부과금 번호>` 를 여러 번). 짧은 답의 `change_id` 가 M.
3. `python3 scripts/charge_change.py render rollback --plan "<작업>/rollback-1.json"` → `page` 를 연다. "○월 ○일 ○시 ○분에 적어 둔 값으로 되돌립니다(`restore_to`)." 되돌리는 칸 수, 그대로 두는 것(`kept` — 그 사이 값이 달라진 것)의 수와 까닭(`kept_why`)을 반드시 말한다. ERP 번호와 적용 범위 기록은 되돌아오지 않는다고 말한다. `restored` 가 0 이면 되돌릴 것이 없다고만 하고 "되돌려"를 청하지 않는다.
4. "되돌려" → 「적용하기」(번호 M, 계산 파일 `rollback-1.json`). "그것도 되돌려"면 2 에 `--include-kept --replaces <M>` 을 붙여 `rollback-2.json` 으로 다시 계산하고 3 부터 한다.

## 적용하기 — 바꾸기 · 되돌리기 공통

필요한 것: 장부 번호 N, 그 번호를 낸 계산 파일, 그 미리보기에 담당자가 분명히 한 "적용"(되돌리기는 "되돌려").

1. **직전에 다시 읽고 시작하기.** `read-calls --record N` 으로 「읽기」 → S2. `python3 scripts/charge_change.py begin --change N --plan "<계산 파일>" --snapshot "<S2>"`. `status: applying` 이면 "적용 직전에 ERP 를 다시 읽었습니다. 미리보기 때와 모든 칸이 같아서 그대로 적용합니다." 종료 1(`same: false`)이면 아무것도 저장하지 않았다 — "미리보기 뒤에 ERP 의 값이 바뀌었습니다(<`differences` 의 부과금>)." 하고 「2」 의 읽기부터 새 미리보기를 만든다.
2. `python3 scripts/charge_change.py calls --change N` 의 `calls` 를 차례로 하나씩: `await stayCharge.applyCharge(<payload 그대로>)` → 답을 그대로 `<작업>/적용-N/<no>.json` 에 저장 → `python3 scripts/charge_change.py record-result --change N --result "<그 파일>"`. `saved: true` 이고 `status: applying` 이면 다음, `applied` 면 3. 그 밖이면 다음 저장을 하지 않고 [references/stopped.md](references/stopped.md) 로 간다 — 다시 읽어 `check` 가 이어서 해도 된다고 하기 전에는 이어서 하지 않는다. 답을 잃었으면 다시 부르지 말고 `stayCharge.last()` 로 받는다. 같은 저장을 두 번 누르지 않는다.
3. **뒤에 다시 읽기.** `read-calls --record N` 으로 「읽기」 → S3. `python3 scripts/charge_change.py verify --change N --snapshot "<S3>"`.
4. `python3 scripts/charge_change.py render result --change N --snapshot "<S3>"` → `page` 를 연다.
   - `same: true` 면 "적용했고, 다시 읽어 확인했습니다. 그 부과금의 다른 금액과 칸도 그대로입니다. 이미 받은 예약의 금액은 그대로입니다. 되돌리려면 'N번 되돌려'라고 하세요."
   - `same: false`(종료 1)면 "적용했지만 다시 읽었더니 다른 곳이 있습니다" 하고 `mismatches`(넣은 값과 다름) · `moved`(그대로여야 할 것이 달라짐)를 하나씩 말한다. 다시 저장하지 않는다.

## 하지 않는 것

그 밖의 일(삭제 · 만들기 · 부과금의 모양 바꾸기 · 빈 금액 채우기 · 가격 캘린더 · 부가옵션 · 프로모션 · 호텔 둘 · 다른 컴퓨터 기록)을 시키면 [references/not-done.md](references/not-done.md) 대로 답한다.
