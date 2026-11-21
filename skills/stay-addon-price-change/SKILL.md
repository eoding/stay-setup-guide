---
name: stay-addon-price-change
description: "이미 판매 중인 호텔 하나의 ERP Stay 부가옵션 가격 줄(판매가 · 공급 원가)을 담당자가 로그인해 둔 크롬 탭에서 보여 주고, 미리보기를 거쳐 바꾸고, 되돌린다. '조식 추가 가격 5,000원 올려줘', '공항 픽업 120,000 으로', '부가옵션 전부 10% 올려줘', '부가옵션 가격 보여줘', '어제 바꾼 부가옵션 되돌려줘' 요청에 쓴다. 객실 가격(가격 캘린더)은 stay-price-change, 부과금 금액은 stay-charge-change, 새 호텔 세팅은 stay-setup-guide · stay-setup-run 이 맡는다. 프로모션 할인은 ERP 에서 사람이 바꾼다(화면으로 저장하면 화면에 안 보이는 설정이 지워질 수 있어서)."
version: 0.1.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [erp, stay, hotel, addon, price, browser, rollback]
    related_skills: [stay-price-change, stay-setup-run, stay-setup-guide]
---

# 부가옵션 가격 도우미

호텔 하나의 부가옵션 가격 줄(조식 · 엑스트라베드 · 공항 픽업 같은 부가옵션마다 시즌 · 날짜 · 요금제별로 붙은 금액 줄)을 담당자의 로그인된 크롬 탭에서 읽고, 미리보기를 보여 주고, 담당자가 "적용"이라고 한 뒤에만 저장한다. 저장 전 값과 넣은 값은 가격 캘린더 도우미와 같은 장부에 남아 되돌릴 수 있다. 담당자에게는 이 스킬을 **도우미**라고 부른다.

하는 일은 셋이다. 1 지금 부가옵션 가격 보기(가격 줄 하나의 설정 전부도) · 2 부가옵션 가격 바꾸기 · 3 되돌리기.

- 명령: 이 스킬 폴더의 `scripts/addon_change.py`(다른 폴더에서는 절대 경로로). JSON 파일을 받고 JSON 을 낸다. 파일에 쓰는 명령은 `--out` 을 주면 짧은 답만 낸다. 도우미는 짧은 답으로 말하고 정한다.
- 페이지: 탭에 올린 `window.stayAddonPrice`. 가격 캘린더 도우미의 페이지 파일 위에 올린다(「준비」).
- 필요할 때만 여는 파일: [references/commands.md](references/commands.md) 명령 · 요청 파일 · 판정 · 오류, [references/page.md](references/page.md) 페이지 호출 · 답 · 오류, [references/stopped.md](references/stopped.md) 멈춘 변경, [references/not-done.md](references/not-done.md) 하지 않는 일.

## 반드시 지킬 것

- 담당자가 미리보기를 보고 분명히 "적용"(되돌리기는 "되돌려")이라고 하기 전에는 아무것도 저장하지 않는다. 대답이 없거나 애매하면 적용이 아니다. 다시 묻는다.
- 한 번에 호텔 하나.
- 값은 명령이 셈하고 견준다. 도우미는 금액 · 퍼센트 · 새 값을 담당자의 말 그대로 요청 파일에 적을 뿐이다.
- 호텔 · 오퍼 · 부가옵션 · 가격 줄의 이름과 번호는 `look` 명령의 답(짧은 답의 `items` — 길면 같은 `look` 에 `--find <담당자의 낱말>` 을 붙여 좁힌다)에서만 옮긴다. 오퍼마다 이름이 같은 부가옵션 · 줄이 있으니 고를 때는 번호로 적고, 담당자에게 줄을 말할 때는 오퍼 이름(`offer`)부터 댄다 — 명령의 답과 페이지도 줄을 「오퍼 · 부가옵션 · 줄」로 부른다.
- 페이지를 만지는 것은 `stayAddonPrice.look()` 과 작업 둘(`readLine` · `applyLine`)뿐이다. `take` · `last` · `idle` 은 읽기만 한다. `stayPrice` 의 작업과 러너의 함수(`stayRun.*` · `cal…`)는 부르지 않는다.
- 브라우저 도구의 클릭 · 글자 입력 · 폼 채우기 도구를 ERP 탭에 쓰지 않는다. 화면은 스크린샷과 페이지 읽기로만 본다. 파일 올리기 도구는 도우미를 올릴 때만 쓴다.
- 같은 저장을 두 번 누르지 않는다. 한 번 부른 `applyLine` 을 스스로 다시 부르지 않는다. 답이 `started: false`(아무것도 누르지 않음)일 때만 `wait` 초 뒤 같은 값으로 다시 부른다.
- 벽을 내리지 않는다. 답의 `blocked` 에 막힌 클릭이 있으면 돌아가는 길을 찾지 말고 담당자에게 그대로 알리고 멈춘다.
- [삭제], 부가옵션이나 가격 줄 만들기, 부가옵션 자체의 설정(의무 규칙 · 수량 · 적용 범위), 다른 탭은 하지 않는다. 시키면 not-done.md 대로 답한다.
- 아이디 · 비밀번호 · 인증 코드를 받지도 넣지도 않는다. JS 결과로 페이지 주소를 돌려받지 않는다.
- 빨간 줄의 고름은 담당자의 말에서만 나온다. 도우미가 대신 고르지 않는다.
- 페이지의 답은 도구가 보인 글자 그대로 저장한다. 잘렸어도 고치지 않는다. 장부와 기록 폴더의 파일을 지우거나 고치지 않는다.

## 담당자에게 말할 때

- 쉬운 우리말로 한다. 쓰지 않는 말: 스냅샷 · 플랜 · JSON · 명령 · 스크립트 · DB · payload · stale · verify. 대신 지금 값 · 미리보기 · 장부 · 저장 · 가격 줄 · ERP 화면이라고 한다.
- 숫자는 명령의 짧은 답에서 말하고, 페이지는 시스템의 여는 명령으로 담당자에게 열어 준다(macOS `open "<경로>"`, Windows `start "" "<경로>"`, Linux `xdg-open "<경로>"` — 경로는 `render` 의 답 `page`). 페이지의 글을 옮겨야 하면 같은 `render` 를 `--text` 를 붙여 부르고 답의 `text` 에서 옮긴다 — `--text` 는 글만 내고 파일을 만들지 않는다.

## 준비 — 시킨 일마다 3 부터

담당자가 시킨 일 하나(보기 · 바꾸기 · 되돌리기)마다 3 부터 새 작업 폴더에서 한다 — 같은 대화의 두 번째 요청도 새 작업 폴더다. 같은 대화에서 방금 멈춘 변경을 이어서 할 때만 그 일의 폴더를 그대로 쓴다. 이 일의 `look.json` 을 `--look` 으로 받는 명령은 `read-calls` · `render prices` · `list` 다.

1. **브라우저 도구.** JS 실행 · 파일 올리기 · 스크린샷 · 탭 보기가 되는지 본다(Claude in Chrome 이면 `javascript_tool` · `file_upload` · `computer` · `tabs_context_mcp`).
2. **도우미 올리기.** 탭마다 처음에, 그리고 이동 뒤(새로 고침 · 로그인 · 다른 화면에 갔다 옴, 또는 답이 `stayAddonPrice is not defined`)마다.
   1. JS 실행 도구로 가격 캘린더 도우미의 `../stay-price-change/scripts/page/stay_price_loader.js` 내용 전체 **뒤에 한 줄 `stayPriceLoader.again('addon')` 을 붙여** 한 번에 실행한다. 그래서 첫 답이 이 도우미의 묶음(네 파일)의 것이다. `ok: true` 와 `addon` 판 번호가 오면 됐다.
   2. 거절하면(`ok: false` — 아무것도 실행되지 않았다) 답의 `want` 에 든 파일만(이 탭에 없거나 예전 판인 것 — 넷은 `../stay-setup-run/scripts/stay_helper.js` · `../stay-setup-run/scripts/stay_boot.js` · `../stay-price-change/scripts/page/stay_price.js` · 이 스킬의 `scripts/page/stay_addon_price.js`) 파일 올리기 도구로 접근성 이름이 **`stay price file bridge`** 인 파일 칸에 올리고 `await stayPriceLoader.load('addon')`. 막히면 page.md 「올리기」.
3. **작업 폴더.** `python3 scripts/addon_change.py work` 의 `work` 가 이 일의 `<작업>` 이다. 읽기마다 그 안의 `읽기-1`, `읽기-2` …(`<R>` — 폴더는 명령이 만든다)를 쓴다. 경로에 빈칸이 있으니 명령에 넘기는 경로는 언제나 큰따옴표로 감싼다. 파일 이름은 폴더마다 처음부터다: `look/look-1.json` · `look.json` · `request.json` · `읽기-1` … · `plan-1.json` · `rollback-1.json`. `plan-2.json` · `--replaces <앞 번호>` 는 한 일 안에서 다시 계산할 때만 쓴다(새 요청의 계산에는 붙이지 않는다).
4. **어디인지 보기.** `await stayAddonPrice.look()` 의 답을 `<작업>/look/look-1.json` 에 저장하고 `python3 scripts/addon_change.py look --answers "<작업>/look" --out "<작업>/look.json"`. 종료 2 의 `refetch` 가 받을 조각이다 — 「읽기」 4 처럼 받아 `<작업>/look/` 에 두고 이 명령을 다시 한다. `login: true` 면 멈추고 "크롬의 ERP 탭에서 직접 로그인해 주시고, ○○ 호텔 화면이 뜨면 알려 주세요". 호텔 번호를 못 찾거나 짧은 답의 `hotel` 이 말한 호텔이 아니면 "○○ 호텔의 Stay 화면을 열어 주세요".
5. **장부 보기.** `python3 scripts/addon_change.py list --look "<작업>/look.json"` — 이 호텔의 기록이 세 도우미(객실 가격 · 부가옵션 가격 · 부과금) 것 모두 나온다(다른 호텔 것은 담당자가 청할 때만 `--all`). 다른 도우미의 줄(`helper`)은 읽어 주기만 하고, 그 번호를 되돌리거나 이어서 하라면 "장부 <`id`>번은 <`helper`>의 기록입니다"라고 하고 그 도우미로 한다. `status: stopped` 인 변경이 있으면 다른 일보다 먼저 알리기만 한다: "장부 <`id`>번 변경이 중간에 멈춰 있습니다 — <`scope`>. 그것부터 볼까요?" `empty` 는 저장할 것이 없던 미리보기다.

## 읽기 — 바꾸기 · 되돌리기 · 적용이 모두 이것으로 읽는다

1. `python3 scripts/addon_change.py read-calls --request "<작업>/request.json" --look "<작업>/look.json" --out "<R>/calls.json"`(장부 번호가 있는 일은 `--record <번호>`).
2. 답의 `lines` 값마다(i = 1, 2 …) `await stayAddonPrice.readLine(<값 그대로>)` 의 답을 `<R>/line-<i>.json` 에 저장한다. 읽기는 편집 창을 열어 보고 닫을 뿐 저장하지 않는다.
3. `python3 scripts/addon_change.py read --calls "<R>/calls.json" --answers "<R>" --out "<R>/snapshot.json"`. 답의 `read_at` 이 ERP 에서 읽은 시각, `doubt` 는 목록과 편집 창이 금액을 다르게 보이는 줄(바꾸지 않는다), `missing` 은 목록에 없는 줄이다.
4. **조각 받기.** 명령이 종료 2 에 `refetch` 를 내면 그 `{id, at, size, until, save}` 마다 `stayAddonPrice.take("<id>", <at>, <size>)` → `<R>/<save><at>.json`, 답의 `next` 가 `until` 보다 작으면 `stayAddonPrice.take("<id>", <next>)` → `<R>/<save><next>.json` 으로 이어 받고 그 명령을 다시 한다. `save` 는 명령이 고른 새 이름이다. `bad` 가 있으면 그 쪽을 옮겨 적다 틀린 것이다 — 그 쪽만 이렇게 다시 받으면 되고, 틀린 파일은 그대로 둔다.

답이 `started: false` 면 `wait` 초 뒤 같은 값으로 다시 부른다. 읽기 답을 잃었으면 `stayAddonPrice.last()` 의 답을 새 파일로 저장하거나 같은 값으로 다시 불러 저장한다.

## 1. 지금 부가옵션 가격 보기

「준비」 다음 `python3 scripts/addon_change.py render prices --look "<작업>/look.json"` → `page` 를 연다. "○시 ○분에 ERP 에서 읽은 부가옵션 가격입니다. 아무것도 바꾸지 않았습니다." 「알 수 없음」 줄이 있으면 덧붙인다: "이 줄은 ERP 화면에 금액 기록이 보이지 않아 도우미가 바꾸지 않습니다." 담당자가 부가옵션 · 줄을 말했으면("조식 가격 보여줘") 「준비」 4 의 `look` 에 `--find "<그 낱말>"` 을 붙여 다시 하고, 짧은 답의 `items` 만 「오퍼 · 부가옵션 · 줄」과 판매가로 말한다(페이지는 호텔 전부다).

"이 가격 줄 설정 다 보여줘"면 「읽기」를 `read-calls --line <줄 번호> --look "<작업>/look.json" --out "<R>/calls.json"` 으로 하고 `python3 scripts/addon_change.py render window --snapshot "<R>/snapshot.json"` → `page` 를 연다. 바꾸지 않고 장부에도 적지 않는다.

## 2. 부가옵션 가격 바꾸기

**묻고 확인한다.** 빠진 것(어느 부가옵션 · 줄, 금액 · 퍼센트 · 새 값)을 묻는다. 판매가인지 공급 원가인지 말이 없으면 묻지 않고 판매가로 하고 확인 상자에 그렇게 밝힌다(아래 보기). 그다음 아래 꼴로 보여 주고 "응"을 받은 뒤에 읽는다. 스스로 채운 것은 괄호로 밝힌다.

```
이렇게 이해했습니다. 맞으면 지금 가격을 읽어 미리보기를 만들겠습니다.
호텔 데모 호텔
가격 줄 데모 오퍼 · 조식 추가 (성인) — 비수기 조식(줄 301), 연말 조식(줄 302) (부가옵션의 줄 전부)
바꾸는 값 판매가 +5,000 (어느 값인지 말씀이 없어 판매가로 했습니다 · 공급 원가는 그대로)
```

**읽고 미리보기.**

1. `<작업>/request.json` 을 쓴다(commands.md 「요청 파일」 — 줄은 `lines` · `addons` · `all` 가운데 하나). 「읽기」 → `<R>/snapshot.json`.
2. `python3 scripts/addon_change.py plan --snapshot "<R>/snapshot.json" --request "<작업>/request.json" --record --out "<작업>/plan-1.json"` → 짧은 답의 `change_id` 가 N, `saves` 가 저장 횟수(빨간 줄이 남았으면 null). 다시 계산하면 `plan-2.json` 처럼 새 이름에 쓰고 `--replaces <앞 번호>` 를 붙인다.
3. `python3 scripts/addon_change.py render preview --plan "<작업>/plan-<k>.json"` → `page` 를 연다.
4. "미리보기를 열었습니다. 아직 아무것도 바뀌지 않았습니다." `counts` 로 바뀌는 줄 · 그대로인 줄 · 바꿀 수 없는 줄(`blocked` 의 줄마다 `label`)을 말한다. `names` 가 있으면 그 문장을 그대로 말한다(알림이다). 짧은 답의 `scope_card` 가 true 면(저장할 줄의 편집 창에 적용 범위 카드가 있음) "저장할 때 ERP 가 그 줄의 적용 범위 기록을 하나 만들 수 있고(가격에는 영향 없음) 되돌려도 없어지지 않습니다."
   - **빨간 줄이 남아 있으면**(`counts.red` > 0) `red` 의 규칙마다 줄과 바뀌는 값(`examples` 의 `moves`)을 말하고 "이대로 바꿈 · 그 줄은 안 바꿈" 가운데 고르게 한다(commands.md 「판정」). 고름은 담당자의 말에서만 나온다. 빨간 줄이 남았는데 "적용"이라고만 하면 저장하지 않는다. 고르면 `--resolutions` 로 다시 계산한다(고름마다 담당자가 한 말을 `said` 에 그대로 — commands.md 「판정」).
   - **빨간 줄이 없고 저장할 것이 있으면**(`saves` 가 1 이상 — 빨간 줄을 고른 뒤의 계산도) 저장 횟수(`saves`)를 말하고 꼭 덧붙인다: "저장하면 ERP 가 이 줄들의 금액 출처를 'ERP 손입력'으로 적고, 되돌려도 그 표시는 돌아오지 않습니다." 그리고 "맞으면 '적용'이라고 해 주세요." 분명한 "적용" 없이는 「적용하기」로 가지 않는다.
   - **`saves` 가 0 이면 저장할 것이 없다** — 빨간 줄을 모두 안 바꾸기로 골랐거나 바뀌는 줄이 없다(`counts.will_change` 가 0). 이렇게만 말한다: "고르신 대로면 바꿀 줄이 없어 저장할 것이 없습니다. 아무것도 바뀌지 않았습니다." 저장 횟수를 말하지 않고 "적용"을 청하지 않는다. 미리보기 페이지도 그렇게 말하고, 그 번호는 `begin` 이 받지 않는다. 다른 값으로 바꾸려면 담당자의 새 말로 처음부터 한다.

## 3. 되돌리기

「준비」 5 의 목록에서 맞는 줄을 골라 확인받는다(하나뿐이어도 묻는다): "이것 맞나요? <그 줄의 `line`>". `rolled_back` · `previewed` · `empty` · `replaced` 는 「되돌릴 것이 없을 때」다.

1. `read-calls --record <N>` 으로 「읽기」 → `<R>/snapshot.json`.
2. `python3 scripts/addon_change.py rollback --change <N> --snapshot "<R>/snapshot.json" --record --sentence "<담당자 말>" --out "<작업>/rollback-1.json"`(줄 몇 개만이면 `--line <줄 번호>` 를 여러 번). 짧은 답의 `change_id` 가 M.
3. `python3 scripts/addon_change.py render rollback --plan "<작업>/rollback-1.json"` → `page` 를 연다. "○월 ○일 ○시 ○분에 적어 둔 값으로 되돌립니다(`restore_to`)." 되돌리는 줄 수, 그대로 두는 줄(`kept`)의 수와 까닭(`kept_why`)을 반드시 말한다. 출처 표시('ERP 손입력')는 되돌아오지 않는다고 말한다. `saves` 가 0 이면 되돌릴 줄이 없다고만 하고 "되돌려"를 청하지 않는다(그 번호는 `begin` 이 받지 않는다).
4. "되돌려" → 「적용하기」(번호 M, 계산 파일 `rollback-1.json`). "그 줄도 되돌려"면 2 에 `--include-kept --replaces <M>` 을 붙여 `rollback-2.json` 으로 다시 계산하고 3 부터 한다.

## 되돌릴 것이 없을 때

되돌리라고 한 줄이 목록에서 `rolled_back` 이면 읽지도 장부에 적지도 않고 목록으로만 답한다: "장부 <`id`>번은 장부 <`undone_by`>번이 이미 모두 되돌렸습니다. 되돌릴 것이 없어 아무것도 하지 않았습니다." `previewed` · `empty` · `replaced` 면: "장부 <`id`>번은 미리보기만 하고 적용하지 않아 ERP 에 넣은 것이 없습니다. 되돌릴 것이 없어 아무것도 하지 않았습니다."

## 장부 보여줘

"장부 보여줘" · "뭐 바꿨는지 보여줘"면 「준비」 1~5 만 하고, 5 의 `changes` 를 새것부터 줄마다 `line` 그대로 읽어 준다. `changes` 가 비었으면 "이 컴퓨터의 장부에 <`hotel.name`> 기록이 하나도 없습니다(객실 가격 · 부가옵션 가격 · 부과금 모두)." 5 의 알림 말고는 덧붙이지 않고, 읽지도 장부에 적지도 않는다.

## 적용하기 — 바꾸기 · 되돌리기 공통

필요한 것: 장부 번호 N, 그 번호를 낸 계산 파일, 그 미리보기에 담당자가 분명히 한 "적용"(되돌리기는 "되돌려").

1. **직전에 다시 읽고 시작하기.** `read-calls --record N` 으로 「읽기」 → S2. `python3 scripts/addon_change.py begin --change N --plan "<계산 파일>" --snapshot "<S2>"`. `status: applying` 이면 "적용 직전에 ERP 를 다시 읽었습니다. 미리보기 때와 모든 줄이 같아서 그대로 적용합니다." 종료 1(`same: false`)이면 아무것도 저장하지 않았다 — "미리보기 뒤에 ERP 의 값이 바뀌었습니다(<`differences` 의 줄>)." 하고 「2」 의 읽기부터 새 미리보기를 만든다.
2. `python3 scripts/addon_change.py calls --change N --out "<작업>/적용-N/calls.json"` 의 `calls` 를 차례로 하나씩, 사이에 다른 일 없이 잇달아(15분 동안 아무 일이 없으면 변경이 멈춘다): `await stayAddonPrice.applyLine(<payload 그대로>)` → 답을 그대로 `<작업>/적용-N/<no>.json` 에 저장 → `python3 scripts/addon_change.py record-result --change N --result "<그 파일>"`. `saved: true` 이고 `status: applying` 이면 다음, `applied` 면 3. 그 밖이면 다음 저장을 하지 않고 [references/stopped.md](references/stopped.md) 로 간다 — 다시 읽어 `check` 가 이어서 해도 된다고 하기 전에는 이어서 하지 않는다. 답을 잃었으면 다시 부르지 말고 `stayAddonPrice.last()` 로 받는다. 같은 저장을 두 번 누르지 않는다.
3. **뒤에 다시 읽기.** `read-calls --record N` 으로 「읽기」 → S3. `python3 scripts/addon_change.py verify --change N --snapshot "<S3>"`.
4. `python3 scripts/addon_change.py render result --change N --snapshot "<S3>"` → `page` 를 연다. 3 의 `names` 가 있으면 그 문장도 그대로 말한다.
   - `same: true` 면 "적용했고, 다시 읽어 확인했습니다. 손님 화면에는 곧 새 금액이 보입니다. 이미 받은 예약의 금액은 그대로입니다. 되돌리려면 'N번 되돌려'라고 하세요."(되돌리기면 끝 문장 없이)
   - `same: false`(종료 1)면 "적용했지만 다시 읽었더니 다른 곳이 있습니다" 하고 `mismatches`(넣은 값과 다름) · `moved`(그대로여야 할 칸이 달라짐)를 줄마다 말한다. 다시 저장하지 않는다.

## 하지 않는 것

그 밖의 일(삭제 · 만들기 · 부가옵션 설정 · 가격 캘린더 · 부과금 · 프로모션 · 호텔 둘 · 다른 컴퓨터 기록)을 시키면 [references/not-done.md](references/not-done.md) 대로 답한다.
