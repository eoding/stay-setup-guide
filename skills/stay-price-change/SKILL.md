---
name: stay-price-change
description: "이미 판매 중인 호텔 하나의 ERP Stay 가격 캘린더 값(판매가·정가·공급 원가)을 담당자가 로그인해 둔 크롬 탭에서 보여 주고, 미리보기를 거쳐 바꾸고, 되돌리고, 지금 상태를 저장해 둔다. '가격 올려줘', '요금 바꿔줘', '12월 디럭스 +10,000', '지금 가격 보여줘', '어제 바꾼 거 되돌려줘', '지금 상태 저장해 둬', '아침에 저장해 둔 것과 뭐가 달라졌어', '새 요금표로 가격 바꿔줘' 요청에 쓴다. 계약서로 새 호텔을 세팅하는 일은 stay-setup-guide(지시서)와 stay-setup-run(실행)이, 부가옵션 금액은 stay-addon-price-change, 부과금 금액은 stay-charge-change 가 맡는다. 프로모션 할인 값은 stay-promotion-change 가 맡는다."
version: 0.1.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [erp, stay, hotel, price, browser, rollback]
    related_skills: [stay-setup-run, stay-setup-guide]
---

# 가격 바꾸기 도우미

호텔 하나의 가격 캘린더 값을 담당자의 로그인된 크롬 탭에서 읽고, 미리보기를 보여 주고, 담당자가 "적용"이라고 한 뒤에만 저장한다. 저장 전 값과 넣은 값은 이 컴퓨터의 장부에 남아 되돌릴 수 있다. 담당자에게는 이 스킬을 **도우미**라고 부른다.

하는 일은 여섯이다. 1 지금 가격 보기 · 2 지금 상태만 저장 · 3 가격 바꾸기 · 4 되돌리기 · 5 새 요금표로 맞추기 · 6 저장해 둔 상태와 견주기.

- 명령: 이 스킬 폴더의 `scripts/price_change.py`(다른 폴더에서는 절대 경로로). 파일에 쓰는 명령은 `--out` 을 주면 짧은 답만 낸다. 도우미는 짧은 답으로 말하고 정하며, 결과 파일을 통째로 읽지 않는다.
- 페이지: 탭에 올린 `window.stayPrice`.
- 필요할 때만 여는 파일(이 글의 그 자리에서 연다): [references/commands.md](references/commands.md) 명령 · 파일 모양 · 오류, [references/page.md](references/page.md) 페이지 호출 · 답 · 오류, [references/red-lines.md](references/red-lines.md) 빨간 줄, [references/stopped.md](references/stopped.md) 멈춘 변경, [references/failures.md](references/failures.md) 막힐 때, [references/sheet.md](references/sheet.md) 새 요금표, [references/compare.md](references/compare.md) 견주기, [references/rollback.md](references/rollback.md) 되돌리기, [references/not-done.md](references/not-done.md) 하지 않는 일.

## 반드시 지킬 것

- 담당자가 미리보기를 보고 분명히 "적용"(되돌리기는 "되돌려")이라고 하기 전에는 아무것도 저장하지 않는다. 대답이 없거나 애매하면 적용이 아니다. 다시 묻는다.
- 한 번에 호텔 하나. 변경 하나는 오퍼 하나다(오퍼가 둘이면 차례로 두 번).
- 값은 명령이 셈하고 견준다. 도우미는 금액·퍼센트를 담당자의 말 그대로 요청에 적을 뿐이다.
- 호텔·오퍼·객실·요금제 이름은 `stayPrice.look()` 의 답에서만 옮긴다. 호텔은 그 `hotel`(번호와 이름) 그대로다.
- 페이지를 만지는 것은 `stayPrice.look()`, 작업 넷(`readPair`·`readReserved`·`applyBulk`·`applyCell`), [시즌 창](references/season-fill.md) 작업 둘뿐이다. `take`·`last`·`idle` 은 읽기만 한다.
- 러너의 함수(`stayRun.*`, `runStep`, `runCalendarPriceStep`, `cal…` 부트 함수)를 직접 부르지 않는다.
- 브라우저 도구의 클릭·글자 입력·폼 채우기 도구를 ERP 탭에 쓰지 않는다. 화면은 스크린샷과 페이지 읽기로만 본다. 파일 올리기 도구는 도우미를 올릴 때만 쓴다.
- 같은 저장을 두 번 누르지 않는다. 한 번 부른 저장 작업(`apply…`)을 스스로 다시 부르지 않는다. 답이 `started: false`(아무것도 누르지 않음)일 때만 `wait` 초 뒤 같은 값으로 다시 부른다.
- 벽을 내리지 않는다. `stayPrice.standDown()` 을 부르지 않는다. 답의 `blocked` 에 막힌 클릭이 있으면 돌아가는 길을 찾지 말고 담당자에게 그대로 알리고 멈춘다.
- 아이디·비밀번호·인증 코드를 받지도 넣지도 않는다. 채팅으로 보내 와도 넣지 않는다.
- JS 결과로 페이지 주소(`location.href` 같은 것)를 돌려받지 않는다. 브라우저 도구가 답을 통째로 막는다.
- 빨간 줄 칸의 고름은 담당자의 말에서만 나온다. 도우미가 대신 고르지 않는다. 정가를 말없이 올리지 않는다.
- 페이지의 답은 도구가 보인 글자 그대로 저장한다. 잘렸어도(`[TRUNCATED]`) 고치지 않는다. 명령이 알아본다.
- 장부와 기록 폴더의 파일을 지우거나 고치지 않는다.

## 담당자에게 말할 때

- 쉬운 우리말로 한다. 쓰지 않는 말: 스냅샷·플랜·JSON·명령·스크립트·DB·SQLite·API·캐시·payload·stale·verify. 대신 지금 값·미리보기·장부·저장·칸·ERP 화면이라고 한다.
- 숫자는 명령의 짧은 답(`counts` · `saves` · `red` · `chosen` · `restored` …)에서 말한다. 페이지는 시스템의 여는 명령으로 담당자에게 열어 준다(브라우저 도구로는 못 연다)(macOS `open "<경로>"`, Windows `start "" "<경로>"`, Linux `xdg-open "<경로>"` — 경로는 `render` 의 답 `page`). 페이지에 적힌 글을 그대로 옮겨야 하면 같은 `render` 에 `--text` 를 붙여 답의 `text` 에서 옮긴다.
- "날짜별로 펼쳐 줘"면 방금 연 페이지의 `render` 를 `--by-date` 를 붙여 다시 하고 그 페이지를 연다.

## 준비 — 시킨 일마다 3 부터

담당자가 시킨 일 하나(보기 · 저장 · 바꾸기 · 되돌리기 · 견주기 — 같은 대화의 두 번째 요청도)마다 3 부터 새 작업 폴더에서 한다. 그 일의 폴더를 그대로 쓰는 때는 둘뿐이다 — 방금 멈춘 변경을 이어서 할 때, 견주기 바로 다음에 되돌릴 때(compare.md 5). 이 일의 `look.json` 을 `--look` 으로 받는 명령은 `list` · `sheet` · `rooms` 다.

1. **브라우저 도구.** JS 실행 · 파일 올리기 · 스크린샷 · 탭 보기가 되는지 본다(Claude in Chrome 이면 `javascript_tool` · `file_upload` · `computer` · `tabs_context_mcp`).
2. **도우미 올리기.** 탭마다 처음에, 그리고 이동 뒤(새로 고침 · 로그인 · 다른 화면에 갔다 옴, 또는 작업 답이 `stayPrice is not defined`)마다. 시즌 창 묶음도 같은 때다(season-fill.md 1) — 이동 없이 같은 탭이면 다시 하지 않는다.
   1. JS 실행 도구로 `scripts/page/stay_price_loader.js` 의 내용 전체 뒤에 한 줄 `stayPriceLoader.again()` 을 붙여 한 번에 실행한다. 이 탭에 적어 둔 원본이 설치된 도우미와 같을 때만 실행하므로 안전하다. `ok: true` 와 `helper`·`price` 판 번호(`0·15·0` 꼴)가 오면 됐다.
   2. 거절하면(`적어 둔 원본이 없습니다` · `…설치된 도우미와 다릅니다` — 아무것도 실행되지 않았다) 답의 `want` 파일(이 탭에 없거나 예전 판인 것만 — 셋은 러너의 `../stay-setup-run/scripts/stay_helper.js` · `../stay-setup-run/scripts/stay_boot.js`, 이 스킬의 `scripts/page/stay_price.js`)을 파일 올리기 도구로 접근성 이름이 **`stay price file bridge`** 인 파일 칸에 올리고 `await stayPriceLoader.load()`. 이름이 다른 파일 칸(ERP 사진 칸, 러너의 `stay file bridge`)에는 올리지 않는다. 도구가 경로를 거절하거나 `load()` 가 `ok: true` 가 아니면 page.md 「올리기」.
3. **작업 폴더.** `python3 scripts/price_change.py work` 의 `work` 가 이 일의 `<작업>` 이다(장부가 있는 기록 폴더 안). 그 일의 읽기(미리보기 · 적용 직전 · 적용 뒤 · 멈췄을 때)는 모두 그 안의 `읽기-1`, `읽기-2` …(폴더는 명령이 만든다). 경로에 빈칸과 `·` 가 있으니 명령에 넘기는 경로는 언제나 큰따옴표로 감싼다(`--out "<작업>/plan-1.json"`).
4. **어디인지 보기.** `await stayPrice.look()` 의 답을 `<작업>/look/look-1.json` 에 저장하고(도구가 답을 버렸으면 다시 부른다 — 읽기만 한다) `python3 scripts/price_change.py look --answers "<작업>/look" --out "<작업>/look.json"`. 종료 2 의 `refetch` 는 「읽기」 5 처럼 받아 `<작업>/look/` 에 두고 다시 한다. 답의 `offers` 는 오퍼, `offer` 는 탭에 열린 오퍼, `pairs` 는 그 오퍼의 객실 · 요금제다 — 고를 이름은 모두 이 답에서 옮긴다. 담당자가 말한 오퍼가 `offer` 가 아니면 `stayPrice.look({offer: "<이름>"})` 의 답을 `look-2.json` 에 저장하고 같은 명령을 다시 한다(명령은 가장 늦게 끝난 답을 쓴다).
   - `login: true` 면 멈추고 "크롬의 ERP 탭에서 직접 로그인해 주시고, ○○ 호텔 화면이 뜨면 알려 주세요". 돌아오면 2 와 4.
   - `호텔 번호를 찾지 못했습니다` 면 "크롬의 ERP 탭에서 ○○ 호텔의 Stay 화면을 열어 주세요". 도우미는 ERP 주소를 모른다.
   - `hotel.name` 이 말한 호텔이 아니면 "지금 탭에는 △△ 호텔이 열려 있습니다. ○○ 호텔 화면을 열어 주세요."
5. **장부 보기.** `python3 scripts/price_change.py list --look "<작업>/look.json"` — 이 호텔의 기록이 네 도우미 것 모두 나온다(다른 호텔 것은 담당자가 청할 때만 `--all`). 줄마다 `scope` 가 그 번호가 덮는 것이다. 다른 도우미의 줄(`helper`)은 읽어 주기만 하고, 그 번호를 되돌리거나 이어서 하라면 "장부 <`id`>번은 <`helper`>의 기록입니다"라고 하고 그 도우미로 한다. `status: stopped` 인 변경이 있으면 다른 일보다 먼저 **알리기만** 한다: "장부 <`id`>번 변경이 중간에 멈춰 있습니다 — <`scope` 그대로>. 그것부터 볼까요?"(지금 다루는 그 변경이면 하지 않는다) 이어서 할지 되돌릴지는 여기서 묻지 않는다(어디서 멈췄는지는 다시 읽어야 안다). 보자고 하면 [references/stopped.md](references/stopped.md), 다른 일을 먼저 하자고 하면 그 일을 한다.

## 읽기 — 네 일이 모두 이것으로 읽는다

페이지는 읽은 화면(조각)을 페이지에 두고 답에는 짧은 머리(`body`)만 싣는다. 명령은 기록 폴더에서 이미 받은 같은 조각을 스스로 찾아 쓰고, 어디에도 없는 조각만 받아 오라고(`refetch`) 한다. 읽기 한 번에 폴더 하나(`<작업>/읽기-1`, `읽기-2` …, 아래 `<R>`)를 쓴다.

범위는 처음에는 요청 파일(바꾸지 않으면 `kind: range` — commands.md 「요청 파일」)로, 장부 번호가 있는 일(적용 직전·뒤, 되돌리기, 이어서)은 `--record <번호>`(그 번호를 계산할 때 읽은 범위)로 준다.

1. `python3 scripts/price_change.py read-calls --request "<요청 파일>" --out "<R>/calls.json"`(또는 `--record <번호>`).
2. **가격.** 1 의 답의 `pairs` 값마다(i = 1, 2 …) `await stayPrice.readPair(<값 그대로>)` 의 답을 `<R>/pair-<i>.json` 에 저장한다. 조각은 아직 받지 않는다.
3. **예약 있는 날.** `price_change.py reserved --calls "<R>/calls.json" --answers "<R>"` 의 `ask` 값마다(n 은 이어서 1, 2 …) `await stayPrice.readReserved(<값 그대로>)` 의 답을 `<R>/resv-<n>.json` 에 저장한다. `done: true` 까지 되풀이한다.
4. **지금 값으로 묶기.** `price_change.py read --calls "<R>/calls.json" --answers "<R>" --out "<R>/snapshot.json"`. 답의 `read_at` 이 ERP 에서 읽은 시각이다(페이지 작업이 끝난 시각 가운데 가장 이른 것 — 15분 창도 여기서 잰다).
5. **조각 받기.** 3·4 의 명령이 종료 2 에 `refetch` 를 내면 그 `{id, at, size, until, save}` 마다 `stayPrice.take("<id>", <at>, <size>)` → `<R>/<save><at>.json`, 답의 `next` 가 `until` 보다 작으면 `stayPrice.take("<id>", <next>)` → `<R>/<save><next>.json` 으로 이어 받고, 그 명령을 다시 한다. `save` 는 명령이 고른 새 이름이고, `bad` 는 다시 받는 쪽과 까닭이다(failures.md). 잘렸어도 그대로 저장한다.

답이 `started: false` 면 아무것도 하지 않았다 — `wait` 초 뒤 같은 값으로 다시 부른다. 명령의 거절에 `say` 가 있으면 그 문장만 그대로 말하고 멈춘다(고른 날이 모두 판매일 없음 — 더 읽지 않는다). 읽기 작업의 답을 잃었거나(끊김 · 잘림 — `stayPrice.last()`) 그 밖에 막히면(범위가 커서 거절 · `그 조각이 페이지에 없습니다` · `failed`) [references/failures.md](references/failures.md) 「읽기」.

## 1. 지금 가격 보기

1. 오퍼·객실·요금제·기간 가운데 말이 없는 것을 묻는다 — "그 이틀 두 객실"처럼 앞 대화를 가리키면 거기서 채우고 무엇으로 채웠는지 말한다. 고를 이름은 `look` 의 답에서 보여 준다. 범위가 크면(호텔 전체 · 몇 달) "읽는 데 시간이 꽤 걸립니다"라고 먼저 말한다.
2. `<작업>/range.json`(`kind: range`)을 쓰고 「읽기」 → `<R>/snapshot.json`.
3. `save-snapshot --snapshot "<R>/snapshot.json" --sentence "<담당자 말>"` → 장부 번호 S — 보기도 장부에 「지금 상태 저장」 한 줄을 남긴다. 문장은 담당자의 말 그대로다. 말이 "응 저장해" · "그 이틀 두 객실"처럼 무엇을 적었는지 알 수 없으면 읽은 범위를 쓴다: "<오퍼> · <객실 · 요금제> · <날짜> 지금 상태".
4. `render prices --snapshot "<R>/snapshot.json"` → `page` 를 연다.
5. "○시 ○분에 ERP 에서 읽은 지금 가격입니다. 아무것도 바꾸지 않았습니다. 장부 S번에 적어 두었습니다." ○시 ○분은 「읽기」 4 의 `read_at`(ERP 에서 읽은 시각)이다.

## 2. 지금 상태만 저장

말한 범위로 1 의 1~4 를 하고(지금 가격 페이지도 연다) 말한다: "지금 값을 장부 S번(○시 ○분)으로 적어 두었습니다. 나중에 'S번 상태로 되돌려'라고 하시면 되돌리는 미리보기를, 'S번과 견주어 줘'라고 하시면 달라진 칸을 보여 드립니다."

## 3. 가격 바꾸기

**묻고 확인한다.** 빠진 것(호텔·오퍼·객실·요금제·기간·요일·바꾸는 값과 금액)은 묻는다. 그다음 아래 꼴로 보여 주고, 담당자가 "응"·"맞아"처럼 분명히 답한 뒤에 읽는다. 스스로 채운 것은 괄호로 밝힌다.

```
이렇게 이해했습니다. 맞으면 지금 가격을 읽어 미리보기를 만들겠습니다.
호텔 데모 호텔
오퍼 기본 오퍼 (오퍼가 여럿이라 이것으로 골랐습니다)
객실 · 요금제 디럭스(조식 포함 · 룸온리), 스위트(조식 포함 · 룸온리) (말씀이 없어 전부)
날짜 2026-12-20 ~ 2027-01-05 의 금·토 → 12/25, 12/26, 1/1, 1/2 (4일)
바꾸는 값 판매가 +10% (어느 값인지 말씀이 없어 판매가로 했습니다 · 정가 · 공급 원가는 그대로)
칸 모든 인원 조합 · 모든 박수 (말씀이 없어 전부)
"연말"을 12/20 ~ 1/5 로 읽었습니다. 다르면 알려 주세요.
```

- 퍼센트면 한 줄을 더한다. "아동이 있는 칸은 ERP 와 똑같이 성인 몫에만 곱하고 아동 추가분은 그대로 둡니다. 아동 추가분도 같이 바꾸려면 말씀해 주세요." 같이 바꾸라고 하면 `scale_child_surcharge: true`.
- 새 값("350 으로")이거나, "성인 2만" · "1박만"처럼 칸을 좁히거나, 짧은 표(몇 칸의 숫자)를 붙여 넣거나, 금액에 통화를 말하면("1,000엔") commands.md 「바꾸기 요청」 · 「목표 값 표」의 「도우미가 할 일」대로 적고 확인 상자에 쓴다. 말한 통화가 오퍼의 통화와 다르면 읽기 전에 묻는다.

**읽고 미리보기.**

1. `<작업>/request.json` 을 쓴다(commands.md 「요청 파일」). 이것을 범위 파일로 「읽기」 → `<R>/snapshot.json`.
2. `plan --snapshot "<R>/snapshot.json" --request "<작업>/request.json" --record --out "<작업>/plan-1.json"` → 짧은 답의 `change_id` 가 N, `saves` 는 저장 횟수(빨간 줄이 남았으면 null)다. k 번째 계산은 `<작업>/plan-<k>.json` 이다(기록이라 덮어쓰지 않는다).
3. `render preview --plan "<작업>/plan-<k>.json"` → `page` 를 연다.
4. "미리보기를 열었습니다. 아직 아무것도 바뀌지 않았습니다." 그리고 `counts` 로 바뀌는 칸(`will_change`)·적용할 수 없는 칸·예약 있는 날의 칸·판매 마감인 칸·새로 생기는 칸 수를 말한다(0 인 것은 뺀다). 해당되면 덧붙인다: 예약 있는 날도 바꾸고 이미 받은 예약의 금액은 그대로 · 마감인 날은 값만 바뀌고 마감은 그대로 · 새로 생기는 칸은 되돌려도 지울 수 없음 · (인원 · 박수가 없던 목표 값 표면) 미리보기 머리의 「칸」이 넣는 줄. 그다음은 빨간 줄에 따라 다르다.
   - **빨간 줄이 남아 있으면**(`counts.red` 가 0 보다 큼, `saves` 가 null) [references/red-lines.md](references/red-lines.md) 를 열어 그대로 말하고 고르게 한다. 저장 횟수는 아직 말하지 않는다. 고름은 담당자의 말에서만 나오고 도우미가 대신 고르지 않는다. 빨간 줄이 남았는데 "적용"이라고만 하면 저장하지 않는다.
   - **빨간 줄을 다 골랐거나 없으면**(`counts.red` 가 0, `saves` 가 있음) 저장 횟수(`saves`)와, 고른 빨간 줄이 있으면 `chosen` · `unused` 대로 무엇이 바뀌는지 숫자로 말한다(red-lines.md). 그리고 "맞으면 '적용'이라고 해 주세요." 분명한 "적용" 없이는 「적용하기」로 가지 않는다. `saves` 가 0 이면 저장할 것이 없다고만 하고 "적용"을 청하지 않는다(red-lines.md).
   - 적용할 수 없는 칸(`counts.blocked`)이 있으면 어느 쪽이든 red-lines.md 「적용할 수 없는 칸」대로 말한다.

## 4. 되돌리기

[references/rollback.md](references/rollback.md) 를 열어 「줄 고르기」대로 「준비」 5 의 목록에서 맞는 줄을 골라 확인받는다 — 맞는 줄이 하나뿐이어도 묻는다: "이것 맞나요? <그 줄의 `line`>"(변경은 적용한 때, 저장해 둔 상태는 값을 읽은 때와 「저장」). `partly_rolled_back` 은 나머지를 되돌릴 수 있다. `rolled_back` · `previewed` · `empty` · `replaced` 는 그 파일의 「되돌릴 것이 없을 때」다.

**"원래 값으로 되돌려"는 둘로 들린다.** 변경 되돌리기(`rollback`)는 그 변경이 넣은 칸만 넣기 전 값으로(그 사이 바뀐 칸은 그대로), 저장해 둔 상태로 되돌리기(`restore`)는 그 저장의 범위 전체를 저장한 때의 값으로 맞춘다. 번호를 말했으면 그 번호, "방금 · 어제 바꾼 거"처럼 바꾼 일을 말하면 맞는 변경, "아침 상태로" · "저장해 둔 걸로"처럼 때나 저장을 말하면 맞는 `snapshot` 이다. 둘 다 맞으면(견주기에서 바뀐 칸이 모두 한 변경의 것일 때도) 한 낱말로 답하게 묻는다:

"두 가지로 되돌릴 수 있습니다. '변경'이라고 하시면 장부 <N>번이 넣은 칸만 넣기 전 값으로 돌리고, 그 사이 다른 데서 바뀐 칸은 그대로 둡니다. '저장'이라고 하시면 장부 <S>번에 저장해 둔 범위 전체를 저장한 때의 값으로 맞춥니다. 어느 쪽으로 할까요?"

'변경'이면 N 의 `rollback`, '저장'이면 S 의 `restore` 다 — 답한 낱말이 확인이다. 그다음 [references/rollback.md](references/rollback.md) 대로 읽고 되돌리기 미리보기를 연다. 분명한 "되돌려" 없이는 「적용하기」로 가지 않는다.

## 5. 새 요금표로 맞추기

담당자가 호텔의 새 요금표(엑셀 · PDF 같은 파일, 객실 × 시즌 × 인원)를 주며 ERP 가격을 거기에 맞추라고 하면 [references/sheet.md](references/sheet.md) 를 열어 그대로 한다(두 길을 고르게 하는 것부터). 몇 칸만 고치는 짧은 표는 이 길이 아니라 「3. 가격 바꾸기」의 목표 값 표다. 그 파일을 열기 전에도 이 둘은 지킨다.

- 도우미는 셈하지 않는다. 요금표에 적힌 숫자만 옮기고, 차이로 적힌 값("성인 추가 +60", "3박 이상 -10%")은 차이 그대로 적는다. 셈은 명령이 한다. 읽지 못한 숫자 · 뜻이 둘인 줄은 짐작하지 않고 담당자에게 묻는다.
- 요금표로 날짜별 가격을 맞추는 미리보기 · 결과를 말할 때는 이 문장을 꼭 붙인다: "여기서 날짜별로 바꾼 가격은 누가 ERP 시즌 화면에서 그 시즌의 [가격]을 '덮기'(이미 값이 있는 날도 덮기)로 다시 채우면 옛 요금으로 돌아갑니다."

## 6. 저장해 둔 상태와 견주기

"아침에 저장해 둔 것과 뭐가 달라졌어?"처럼 저장해 둔 상태(목록의 `snapshot` 줄)와 지금을 견주라고 하면 [references/compare.md](references/compare.md) 대로 `compare` 하고 말한다 — 다른 칸마다 누가 바꿨는지(장부 번호 · 장부에 없는 변화) 댄다. 아무것도 바꾸지 않는다.

## 장부 보여줘

"장부 보여줘" · "뭐 바꿨는지 보여줘"면 「준비」 1~5 만 하고, 5 의 `changes` 를 새것부터 줄마다 `line` 그대로 읽어 준다. `changes` 가 비었으면 "이 컴퓨터의 장부에 <`hotel.name`> 기록이 하나도 없습니다(객실 가격 · 부가옵션 가격 · 부과금 · 프로모션 모두)." 5 의 알림 말고는 덧붙이지 않고, 읽지도 장부에 적지도 않는다.

## 적용하기 — 바꾸기·되돌리기 공통

필요한 것: 장부 번호 N, 그 번호를 낸 계산 파일(`plan-<k>.json` · `rollback-<k>.json`), 그 미리보기에 담당자가 분명히 한 "적용"(되돌리기는 "되돌려").

1. **직전에 다시 읽고 시작하기.** `read-calls --record N` 으로 「읽기」 → S2. `begin --change N --plan "<계산 파일>" --snapshot "<S2>"` 가 미리보기 때 값과 견준다. `status: applying` 이면 "적용 직전에 ERP 를 다시 읽었습니다. 미리보기 때와 모든 칸이 같아서 그대로 적용합니다." 종료 1(`same: false`)·2 면 아무것도 시작하지 않았다 — failures.md 「적용」.
2. `calls --change N --out "<작업>/적용-N/calls.json"` 의 `calls` 를 차례로 하나씩, 사이에 다른 일 없이 잇달아 한다 — 15분 동안 아무 일이 없으면 변경이 멈추고 stopped.md 로 간다.
   - `await stayPrice.<op>(<payload 그대로>)` — `op` 는 `applyBulk` 또는 `applyCell`.
   - 답을 그대로 `<작업>/적용-N/<no>.json` 에 저장하고 `record-result --change N --result "<그 파일>"`.
   - `saved: true` 이고 `status: applying` 이면 다음으로, `status: applied` 면 3 으로 간다. 그 밖(저장이 안 됐거나 `status: stopped`)이면 다음 저장을 하지 않고 [references/stopped.md](references/stopped.md) 로 간다.
   - 답이 `started: false` 이거나, 호출이 답 없이 끊겼거나 잘렸으면 [references/failures.md](references/failures.md) 「적용」. 어느 때든 같은 저장을 두 번 누르지 않는다 — 한 번 부른 저장은 다시 부르지 않고, 답을 잃었으면 `stayPrice.last()` 로 받는다.
3. **뒤에 다시 읽기.** 다 저장되면 `read-calls --record N` 으로 「읽기」 → S3. `verify --change N --snapshot "<S3>"`.
4. `render result --change N` → `page` 를 연다.
   - `same: true` 면 "적용했고, 다시 읽어 확인했습니다. 손님 화면에는 5분 안에 새 가격이 보입니다. 이미 받은 예약의 금액은 그대로입니다. 되돌리려면 'N번 되돌려'라고 하세요."
   - `same: false`(종료 1)면 "적용했지만 다시 읽었더니 <`mismatches` 의 수>칸이 넣은 값과 다릅니다. 페이지의 빨간 칸을 ERP 에서 확인해 주세요." 다시 저장하지 않는다.

## 중간에 멈췄을 때

적용하다 멈췄을 때, "N번 이어서"라고 할 때, 「준비」 5 에서 알린 멈춘 변경을 보자고 할 때 [references/stopped.md](references/stopped.md) 대로 한다. 다시 읽어 `check` 가 이어서 해도 된다고 하기 전에는 이어서 하지 않는다. 고를 것은 `check` 뒤에 한 번만 묻는다.

## 하지 않는 것

그 밖의 일(손님 화면 미리 보기 · 호텔 둘 · 판매 마감 · 객실 · 요금제 · 취소정책 · 부과금 · 프로모션 · 부가옵션 · 새 칸 지우기 · 다른 컴퓨터 기록)을 시키면 [references/not-done.md](references/not-done.md) 대로 답한다.
