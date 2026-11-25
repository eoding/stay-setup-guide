---
name: stay-promotion-change
description: "이미 판매 중인 호텔 하나의 ERP Stay 프로모션 할인 값(할인율 · 정액 할인 금액 · 무료 숙박 박수 — 프로모션의 단마다)을 담당자가 로그인해 둔 크롬 탭에서 보여 주고, 미리보기를 거쳐 바꾸고, 되돌린다. '얼리버드 10% 를 12% 로', '3박 이상 할인 15% 로', '연박 무료 1박을 2박으로', '정액 20달러 할인을 25달러로', '얼리버드 할인 2% 포인트 올려줘', '프로모션 보여줘', '어제 바꾼 프로모션 되돌려줘' 요청에 쓴다. 화면에 안 보이는 설정을 지키는 표식이 있는 ERP 에서만 저장한다. 객실 가격은 stay-price-change, 부가옵션 금액은 stay-addon-price-change, 부과금은 stay-charge-change, 새 호텔 세팅은 stay-setup-guide · stay-setup-run 이 맡는다. 프로모션 만들기 · 지우기 · 조건 바꾸기는 하지 않는다."
version: 0.1.1
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [erp, stay, hotel, promotion, discount, browser, rollback]
    related_skills: [stay-price-change, stay-addon-price-change, stay-charge-change, stay-setup-run, stay-setup-guide]
---

# 프로모션 할인 도우미

호텔 하나의 프로모션(오퍼마다 붙은 것과 「전 오퍼 공통」)의 **단마다 할인 값만** 담당자의 로그인된 크롬 탭에서 읽고, 미리보기를 보여 주고, "적용"이라고 한 뒤에만 저장한다. 저장 전 값과 넣은 값은 다른 세 도우미와 같은 장부에 남아 되돌릴 수 있다. 담당자에게는 이 스킬을 **도우미**라고 부른다.

하는 일은 셋이다. 1 지금 프로모션 보기(한 프로모션의 설정 전부도) · 2 할인 값 바꾸기 · 3 되돌리기.

- 명령: 이 스킬 폴더의 `scripts/promotion_change.py`(다른 폴더에서는 절대 경로로). 파일에 쓰는 명령은 `--out` 을 주면 짧은 답만 낸다. 도우미는 짧은 답으로 말하고 정한다.
- 페이지: 탭에 올린 `window.stayPromotion`. 가격 캘린더 도우미의 페이지 파일 위에 올린다(「준비」).
- 필요할 때만 여는 파일: [references/commands.md](references/commands.md) 명령 · 요청 파일 · 단 · 판정 · 오류, [references/page.md](references/page.md) 페이지 호출 · 답 · 오류, [references/stopped.md](references/stopped.md) 멈춘 변경, [references/rollback.md](references/rollback.md) 되돌리기, [references/apply.md](references/apply.md) 적용하기, [references/not-done.md](references/not-done.md) 하지 않는 일.

## 반드시 지킬 것

- 담당자가 미리보기를 보고 분명히 "적용"(되돌리기는 "되돌려")이라고 하기 전에는 아무것도 저장하지 않는다. 대답이 없거나 애매하면 적용이 아니다. 다시 묻는다.
- **표식 없는 ERP 에서는 저장하지 않는다.** 편집 창에 화면 밖 설정을 지키는 표식이 없으면(짧은 답의 `gate`) 계산은 보여 주되 "적용"을 묻지 않고 그 문장(`said`)을 그대로 말한다. 명령도 페이지도 저장하지 않는다.
- 한 번에 호텔 하나.
- 값은 명령이 셈하고 견준다. 도우미는 할인율 · 금액 · 박수 · 퍼센트를 담당자의 말 그대로 요청 파일에 적을 뿐이다.
- 단의 값만 바꾼다. 프로모션명 · 코드 · 발동 조건 · 혜택 방식 · 적용 단위 · 단의 기준값 · 적용 숙박일 · 진행기간 제한과 그 기간 · 시즌 · 요금제 · 취소 정책 · 적용 범위는 바꾸지 않고, 단을 더하거나 지우지 않는다. [삭제] · [프로모션 추가] · [단 추가] · 단 [삭제] · 편집 창의 고르는 칸과 체크 · 다른 탭은 하지 않는다. 시키면 not-done.md 대로 답한다.
- 카드 · 프로모션의 이름과 번호, 단의 기준값은 `look` 명령의 답(짧은 답의 `items` — 길면 같은 `look` 에 `--find <담당자의 낱말>` 을 붙여 좁힌다)에서만 옮기고, 고를 때는 번호로 적는다. 「전 오퍼 공통」 카드는 오퍼 번호 `0` 이다.
- 페이지를 만지는 것은 `stayPromotion.look()` 과 작업 둘(`readPromotion` · `applyPromotion`)뿐이다. `take` · `last` · `idle` 은 읽기만 한다. `stayPrice` · `stayAddonPrice` · `stayCharge` 의 작업과 러너의 함수(`stayRun.*` · `cal…`)는 부르지 않는다.
- 브라우저 도구의 클릭 · 글자 입력 · 폼 채우기 도구를 ERP 탭에 쓰지 않는다. 화면은 스크린샷과 페이지 읽기로만 본다.
- 같은 저장을 두 번 누르지 않는다. 한 번 부른 `applyPromotion` 을 스스로 다시 부르지 않는다. 답이 `started: false`(아무것도 누르지 않음)일 때만 `wait` 초 뒤 같은 값으로 다시 부른다.
- 벽을 내리지 않는다. 답의 `blocked` 에 막힌 클릭이 있으면 돌아가는 길을 찾지 말고 담당자에게 그대로 알리고 멈춘다.
- 아이디 · 비밀번호를 받지도 넣지도 않는다. JS 결과로 페이지 주소를 돌려받지 않는다.
- 빨간 줄의 고름은 담당자의 말에서만 나온다. 도우미가 대신 고르지 않는다.
- 페이지의 답은 도구가 보인 글자 그대로 저장한다(잘렸어도). 장부와 기록 폴더의 파일을 지우거나 고치지 않는다.

## 담당자에게 말할 때

- 쉬운 우리말로 한다. 쓰지 않는 말: 스냅샷 · 플랜 · JSON · 명령 · 스크립트 · DB · payload · verify · 티어 · 트리거. 대신 지금 값 · 미리보기 · 장부 · 저장 · 단 · 할인 값이라고 한다.
- 숫자는 명령의 짧은 답에서 말하고, 페이지는 시스템의 여는 명령으로 열어 준다(macOS `open "<경로>"`, Windows `start "" "<경로>"`, Linux `xdg-open "<경로>"` — 경로는 `render` 의 답 `page`). 글을 옮길 때는 같은 `render` 를 `--text` 로 하고 답의 `text` 에서 옮긴다.

## 준비 — 시킨 일마다 3 부터

담당자가 시킨 일 하나(보기 · 바꾸기 · 되돌리기 — 같은 대화의 두 번째 요청도)마다 3 부터 새 작업 폴더에서 한다. 방금 멈춘 변경을 이어서 할 때만 그 일의 폴더를 그대로 쓴다. 이 일의 `look.json` 을 `--look` 으로 받는 명령은 `read-calls` · `render prices` · `list` 다.

1. **브라우저 도구.** JS 실행 · 파일 올리기 · 스크린샷 · 탭 보기가 되는지 본다.
2. **도우미 올리기.** 탭마다 처음에, 그리고 이동 뒤(새로 고침 · 로그인 · 다른 화면에 갔다 옴, 또는 답이 `stayPromotion is not defined`)마다.
   1. JS 실행 도구로 `../stay-price-change/scripts/page/stay_price_loader.js` 내용 전체 뒤에 한 줄 `stayPriceLoader.again('promotion')` 을 붙여 한 번에 실행한다. `ok: true` 와 `promotion` 판 번호가 오면 됐다.
   2. 거절하면 답의 `want` 에 든 파일만(넷은 page.md 「올리기」) 파일 올리기 도구로 접근성 이름이 **`stay price file bridge`** 인 파일 칸에 올리고 `await stayPriceLoader.load('promotion')`. 막히면 page.md 「올리기」.
3. **작업 폴더.** `python3 scripts/promotion_change.py work` 의 `work` 가 이 일의 `<작업>` 이다. 읽기마다 그 안의 `읽기-1`, `읽기-2` …(`<R>` — 폴더는 명령이 만든다)를 쓴다. 경로에 빈칸이 있으니 명령에 넘기는 경로는 언제나 큰따옴표로 감싼다.
4. **어디인지 보기.** `await stayPromotion.look()` 의 답을 `<작업>/look/look-1.json` 에 저장하고(도구가 답을 버렸으면 다시 부른다 — 읽기만 한다) `python3 scripts/promotion_change.py look --answers "<작업>/look" --out "<작업>/look.json"`. 종료 2 의 `refetch` 가 받을 조각이다 — 「읽기」 4 처럼 받아 `<작업>/look/` 에 두고 이 명령을 다시 한다. `login: true` 면 멈추고 "크롬의 ERP 탭에서 직접 로그인해 주시고, ○○ 호텔 화면이 뜨면 알려 주세요". 호텔 번호를 못 찾거나 짧은 답의 `hotel` 이 말한 호텔이 아니면 "○○ 호텔의 Stay 화면을 열어 주세요".
5. **장부 보기.** `python3 scripts/promotion_change.py list --look "<작업>/look.json"` — 이 호텔의 기록이 네 도우미 것 모두 나온다(다른 호텔 것은 담당자가 청할 때만 `--all`). 다른 도우미의 줄(`helper`)은 읽어 주기만 하고, 그 번호를 되돌리거나 이어서 하라면 "장부 <`id`>번은 <`helper`>의 기록입니다"라고 하고 그 도우미로 한다. `status: stopped` 인 변경이 있으면 다른 일보다 먼저 알리기만 한다: "장부 <`id`>번 변경이 중간에 멈춰 있습니다 — <`scope`>. 그것부터 볼까요?"(지금 다루는 그 변경이면 하지 않는다)

## 읽기 — 바꾸기 · 되돌리기 · 적용이 모두 이것으로 읽는다

1. `python3 scripts/promotion_change.py read-calls --request "<작업>/request.json" --look "<작업>/look.json" --out "<R>/calls.json"`(장부 번호가 있는 일은 `--record <번호>`).
2. 답의 `promotions` 값마다(i = 1, 2 …) `await stayPromotion.readPromotion(<값 그대로>)` 의 답을 `<R>/promotion-<i>.json` 에 저장한다. 읽기는 창을 열고 닫을 뿐 저장하지 않는다.
3. `python3 scripts/promotion_change.py read --calls "<R>/calls.json" --answers "<R>" --out "<R>/snapshot.json"`. `read_at` 은 ERP 에서 읽은 시각, `missing` 은 목록에 없는 프로모션, `unmarked` 는 표식 없는 창의 프로모션(저장하지 않는다).
4. **조각 받기.** 명령이 종료 2 에 `refetch` 를 내면 그 `{id, at, size, until, save}` 마다 `stayPromotion.take("<id>", <at>, <size>)` → `<R>/<save><at>.json`(답의 `next` 가 `until` 보다 작으면 `take("<id>", <next>)` → `<R>/<save><next>.json` 으로 이어서) 받고 그 명령을 다시 한다. `bad` 의 쪽만 다시 받고 틀린 파일은 그대로 둔다.

답이 `started: false` 면 `wait` 초 뒤 같은 값으로 다시 부른다. 읽기 · 조각(`take`) 답을 잃었으면(읽기만 하니 아무것도 바뀌지 않았다) `stayPromotion.last()` 의 답을 새 파일로 저장하거나 다시 불러 저장한다.

## 1. 지금 프로모션 보기

「준비」 다음 「읽기」를 `read-calls --all --look "<작업>/look.json" --out "<R>/calls.json"` 으로 하고(프로모션마다 편집 창을 열고 닫는다) `render prices --look "<작업>/look.json" --snapshot "<R>/snapshot.json"` → `page` 를 연다. "○시 ○분에 ERP 에서 읽은 프로모션입니다. 아무것도 바꾸지 않았습니다." `read` 의 `unmarked` 가 비었으면 "이 ERP 에서는 도우미가 할인 값을 바꿀 수 있습니다(화면에 안 보이는 설정을 지킵니다)", 아니면 "이 ERP 에는 표식이 없어 도우미가 저장하지 않습니다".

"이 프로모션 설정 다 보여줘"면(맞는 것이 여럿이면 카드 · 이름 · 번호로 묻는다 — "모두"면 `--promotion` 을 여러 번) 「읽기」를 `read-calls --promotion <번호> --look "<작업>/look.json"` 으로 하고 `render window --snapshot "<R>/snapshot.json"` → `page`: "○시 ○분에 ERP 에서 읽은 <카드> · <프로모션> 설정 전부입니다. 바꾸지 않았고 장부에도 적지 않았습니다."

## 2. 할인 값 바꾸기

**묻고 확인한다.** 말을 단으로 옮기는 것은 commands.md 「담당자의 말 → 단」대로다 — "3박 이상"은 기준값 3 인 단, 단이 하나뿐인 프로모션은 그 단이다. 할인율 단의 "2% 올려"가 2% 포인트인지 지금 값의 2% 인지, 어느 단인지 분명하지 않으면 짐작하지 않고 묻는다. 그다음 아래 꼴로 보여 주고 "응"을 받은 뒤에 읽는다. 「바꾸는 단」은 늘 ERP 의 말(`look` 의 혜택 줄 그대로)로 적고, 스스로 채운 것은 괄호로 밝힌다.

```
이렇게 이해했습니다. 맞으면 지금 값을 읽어 미리보기를 만들겠습니다.
호텔 데모 호텔
프로모션 롱스테이 2박 7% / 3박 10% (데모 오퍼 2027 · 프로모션 9002번)
바꾸는 단 「최소 숙박(박) 3 → 10%」 의 할인율 → 12% (새 값)
```

**읽고 미리보기.**

1. `<작업>/request.json` 을 쓴다(commands.md 「요청 파일」 · 「단」). 「읽기」 → `<R>/snapshot.json`.
2. `python3 scripts/promotion_change.py plan --snapshot "<R>/snapshot.json" --request "<작업>/request.json" --record --out "<작업>/plan-1.json"` → 짧은 답의 `change_id` 가 N, `saves` 가 저장 횟수(빨간 줄이 남았으면 null). 다시 계산하면 `plan-2.json` 처럼 새 이름에 쓰고 `--replaces <앞 번호>` 를 붙인다.
3. `python3 scripts/promotion_change.py render preview --plan "<작업>/plan-<k>.json"` → `page` 를 연다.
4. "미리보기를 열었습니다. 아직 아무것도 바뀌지 않았습니다." **표식이 없거나 단 줄 출처를 모르면**(`gate` 가 비어 있지 않음) 그 `said` 만 그대로 말하고 끝낸다 — 수 · 저장하면 생기는 것 · "적용"을 말하지 않는다. 그 밖에는 `counts` 로 바뀌는 단 · 그대로인 단(`unchanged` 와 짚지 않아 그대로 보내는 `sent`) · 바꿀 수 없는 단(`blocked` 의 단마다 `name` 과 `label` · `why`)을 말하고, `guest` 를 그대로 말한다. `off` 가 있으면 그 문장마다 그대로 말한다(화면에 안 보이는 설정은 그대로 둔다는 알림이다). `names` 가 있으면 그 문장을 그대로 말한다. `scope_card` 가 true 면(저장할 것이 있을 때만 true) "저장할 때 적용 범위 기록이 하나 생길 수 있고(가격 영향 없음) 되돌려도 없어지지 않습니다."
   - **빨간 줄이 남아 있으면**(`counts.red` > 0) `red` 의 규칙마다 단과 바뀌는 값(`examples` 의 `moves`)을 말하고 "이대로 바꿈 · 그 단은 안 바꿈" 가운데 고르게 한다(commands.md 「판정」). 빨간 줄이 남았는데 "적용"이라고만 하면 저장하지 않는다. 고르면 `--resolutions` 로 다시 계산한다(고름마다 담당자의 말을 `said` 에 그대로).
   - **저장할 것이 없으면**(`saves` 가 0) "바뀌는 단이 없어 저장할 것이 없습니다"라고 하고 "적용"을 묻지 않는다.
   - **그 밖에는** 저장 횟수(`saves`)를 말하고 "맞으면 '적용'이라고 해 주세요." 분명한 "적용" 없이는 「적용하기」로 가지 않는다.

## 3. 되돌리기

"어제 바꾼 프로모션 되돌려줘"면 [references/rollback.md](references/rollback.md) 대로 — 그 파일의 「줄 고르기」("방금 것" · "처음 값으로")대로 목록에서 맞는 줄을 골라 확인받고(하나뿐이어도), 되돌리기 미리보기를 연다. 분명한 "되돌려" 없이는 「적용하기」로 가지 않는다. `restored` 가 0 이면 "되돌려"를 청하지 않는다. 줄이 `rolled_back` · `previewed` · `empty` · `replaced` 면 그 파일의 「되돌릴 것이 없을 때」.

## 장부 보여줘

"장부 보여줘"면 「준비」 1~5 만 하고, 5 의 `changes` 를 새것부터 줄마다 `line` 그대로 읽어 준다. 비었으면 "이 컴퓨터의 장부에 <`hotel.name`> 기록이 하나도 없습니다." 읽지도 장부에 적지도 않는다.

## 적용하기 — 바꾸기 · 되돌리기 공통

필요한 것: 장부 번호 N, 그 번호를 낸 계산 파일, 그 미리보기에 담당자가 분명히 한 "적용"(되돌리기는 "되돌려"). 그다음 [references/apply.md](references/apply.md) 대로 한다(직전에 다시 읽어 `begin` — 표식이 없거나 다르면 저장하지 않는다. 저장은 사이에 다른 일 없이 잇달아 — 15분 동안 아무 일이 없으면 멈춘다). 저장이 안 됐거나 `status: stopped` 면 다음 저장을 하지 않고 [references/stopped.md](references/stopped.md) 로 간다 — 다시 읽어 `check` 가 이어서 해도 된다고 하기 전에는 이어서 하지 않는다. 답을 잃었으면 다시 부르지 말고 `stayPromotion.last()` 로 받는다.

## 하지 않는 것

그 밖의 일(삭제 · 만들기 · 조건이나 단의 모양 바꾸기 · 가격 캘린더 · 부가옵션 · 부과금 · 호텔 둘 · 다른 컴퓨터 기록)을 시키면 [references/not-done.md](references/not-done.md) 대로 답한다.
