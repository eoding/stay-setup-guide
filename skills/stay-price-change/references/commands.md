# price_change.py — 명령과 파일

차례: 공통 · 하위 명령 · 요청 파일 · 빨간 줄 고름 파일 · 오류와 할 일

## 공통

```bash
python3 scripts/price_change.py <하위 명령> [플래그] [--out <파일>]
```

- 결과는 표준 출력에 JSON 으로 쓴다. `--out` 을 주면 그 파일에도 쓴다(`render` 는 HTML 을 그 파일에 쓰고 표준 출력에는 `{page}` 만).
- 종료 코드: 0 됨 · 1 다른 값이 있음(`stale`·`verify` 의 `same: false`) · 2 입력이나 순서가 맞지 않음. 2 일 때 표준 오류에 `{"error": "…"}`, 받아야 할 조각이 있으면 `"refetch": [{"id", "at", "size"}]` 도 온다.
- 장부: `~/Documents/어딩 Stay 가격 변경 기록/가격장부.sqlite3`. 환경 변수 `STAY_PRICE_LEDGER_DIR` 로 폴더를 바꿀 수 있다. 장부는 지우지 않는다. 번호마다(미리보기 · 지금 상태 저장 · 되돌리기) 호텔(페이지가 알아본 번호와 이름)과 그 계산이 바탕으로 삼은 읽은 값을 적는다. 그래서 같은 범위를 다시 읽거나 견줄 때는 번호만 준다.
- 답 폴더(`--answers <폴더>`)에서는 이름이 `look-`·`pair-`·`resv-`·`take-` 로 시작하는 `.json`·`.txt` 파일을 답으로 읽는다.
- 앞선 읽기 폴더(`--earlier <폴더>`, 여러 번): 그 안의 답은 이번 읽기의 답으로 치지 않고, 다 받아 맞춰 본 조각만 빌린다. 조각은 알아볼 값 넷(글자 수 · 바이트 수 · CRC-32 · FNV-1a)이 모두 같을 때만 같은 조각이다. 이번 답들과 앞선 폴더 어디에도 없는 조각만 `refetch` 에 나온다.
- 각 명령의 플래그는 `--help` 가 정본이다.

## 하위 명령

| 명령 | 플래그 | 하는 일 · 답 |
|---|---|---|
| `look` | `--answers` (여러 번) | `stayPrice.look()` 의 답과 그 조각 → `{login, hotel, offer, offers, pairs}`. 목록이 길어 `body` 로 왔을 때만 쓴다. |
| `read-calls` | `--request` 또는 `--record` | 읽을 범위 → `{pairs: [readPair 부를 값], reserved: [readReserved 첫 물음]}`. `--request` 는 범위 파일(`kind: range`)·바꾸기 요청·목표 값 표, `--record` 는 장부 번호(그 번호의 계산이 바탕으로 삼은 범위). 부를 값마다 `hotel` 이 든다. 기간은 고른 날만 덮게 끊는다(readPair 186일씩). |
| `reserved` | `--calls` · `--answers` (여러 번) · `--earlier` (여러 번) | `read-calls` 가 낸 파일과 readReserved 답들 → `{done, ask, answered, failed}`. 숨긴 줄이 있던 물음은 객실 → 요금제 → 날짜 반쪽 순으로 쪼개 `ask` 에 다시 낸다. 답 폴더를 통째로 주면 된다. 예약 조각이 어디에도 없으면 종료 2 와 `refetch`. |
| `read` | `--calls` · `--answers` (여러 번) · `--earlier` (여러 번) · `--read-at` | 브라우저 답 → 지금 값 `{hotel, offer, currency, read_at, cells, reserved, pairs, room_names, no_sale, dates}`. 호텔은 페이지가 알아본 것이다. readPair 답이 없는 부를 값이나 남은 예약 물음이 있으면 거절하고, 어디에도 없는 조각이 있으면 종료 2 와 `refetch`. `--hotel`·`--hotel-id`·`--price-page`·`--adjust-page` 는 화면 조각 파일로 읽는 시험용이다. |
| `plan` | `--snapshot` · `--request` · `--resolutions` · `--record` | 미리보기 계산 → `{change_id, counts, plan, unresolved, steps}`. `--record` 면 장부에 미리보기와 그 읽은 값을 적고 `change_id` 를 준다. 빨간 줄을 다 고르지 않았으면 `steps` 가 null. |
| `render` | `preview`·`result`·`rollback`·`prices` 중 하나 + `--plan` (preview·rollback) · `--change` (result) · `--snapshot` (prices) | 페이지 HTML. `--out` 이 없으면 기록 폴더에 `<날짜 시각> · <호텔> · <페이지 이름>.html` 로 쓴다. 답 `{page}` 는 그 경로. |
| `begin` | `--change` · `--plan` (`steps` 가 든 plan.json 또는 rollback.json) | 적용 시작. 저장 단계를 장부에 적는다. 같은 단계로 다시 부르면 아무것도 바꾸지 않는다. → `{change_id, status, steps}` |
| `calls` | `--change` | 아직 저장되지 않은 단계 → `{change_id, status, calls: [{no, op, payload}]}`. `op` 는 `applyBulk` 또는 `applyCell`, `payload` 는 그 작업에 그대로 넘긴다(장부의 호텔이 든다). 멈춘 변경은 `check` 가 이어서 해도 된다고 한 뒤에만 낸다. |
| `record-result` | `--change` · `--result` (답 파일 하나) | 브라우저 답 하나 → 그 단계를 됨·멈춤으로 적는다 → `{change_id, step, started, saved, note, status}`. 답이 `started: false` 면 적지 않고 `{started: false, wait}` 만 돌려준다(그 초만큼 기다려 같은 값으로 다시 부른다). `saved: "unknown"` 은 「모름」 표시를 달아 멈춤으로 적는다. 다른 단계·다른 값을 물은 답이면 거절한다. |
| `check` | `--change` · `--snapshot` | 방금 같은 범위로 읽은 값으로 → `{change_id, status, steps: [{no, label, ledger, seen, settled, moved}], remaining, can_continue, why}`. `seen`: `saved` 넣은 값 그대로 · `not_saved` 전 값 그대로 · `mixed` 섞임 · `changed` 그 사이 다른 값. 「모름」인 단계는 읽은 값이 말하는 대로 가려 장부에 적는다(`settled`). `can_continue` 면 멈춘 변경을 적용 중으로 돌린다. |
| `verify` | `--change` · `--snapshot` | 적용 뒤 다시 읽은 값과 견준다 → `{change_id, same, mismatches: [{key, label, field, after, seen, seen_state}]}`. 저장된 단계의 값만 본다. |
| `stale` | `--change` · `--snapshot` | 그 번호의 계산이 바탕으로 삼은 읽은 값과 방금 읽은 값 → `{same, differences: [{key, then, now}]}`. 한쪽에만 있는 칸도 다른 칸이다. 예약 표시는 견주지 않는다. 다른 호텔의 값이면 거절한다. |
| `rollback` | `--change` · `--snapshot` · `--include-kept` · `--room`·`--rate-plan`·`--occupancy` (여러 번) · `--from`·`--to` · `--record` · `--sentence` | 변경 하나(또는 고른 일부)를 되돌리는 계산 → `{change_id, scope, rollback, steps, reserved}`. 저장된 단계의 칸만 되돌린다. `rollback` 안에 `restore_to`(적어 둔 값의 시각)·`restored`·`kept`(세 값과 `cause`)·`unremovable`. 다른 호텔의 값이면 거절한다. |
| `restore` | `--saved` · `--snapshot` · 고르기 플래그 · `--record` · `--sentence` | 지금 상태 저장으로 적은 상태로 되돌리는 계산. 답은 `rollback` 과 같은 모양. 장부에는 변경으로 적혀 이것도 되돌릴 수 있다. |
| `save-snapshot` | `--snapshot` · `--sentence` | 지금 값을 장부에만 적는다 → `{change_id}`. |
| `list` | 없음 | `{ledger, changes: [{id, kind, status, hotel, hotel_id, offer, sentence, read_at, created_at, applied_at, verified_at, reverses, items, written, rolled_back}]}`. 새것부터. `kind`: change · snapshot · rollback. `status`: previewed → applying → stopped / applied. |

`counts` 의 칸: `cells`(계산한 칸) · `will_change`(그중 적용할 수 없는 칸을 뺀 수) · `blocked` · `red` · `reserved` · `closed` · `new` · `skipped`, 그리고 규칙 코드마다의 수(`ABOVE_LIST` 등).

## 요청 파일

세 모양 모두 `hotel` 은 `stayPrice.look()` 의 `hotel`(`{id, name}`)을 그대로 적는다. 번호 없이 이름만이면 거절한다. `offer` 와 객실 · 요금제 이름은 `look()` 의 `offer`·`pairs` 에서 고른 그대로다.

### 읽을 범위 (`kind: range`)

```json
{"kind": "range", "hotel": {"id": "1", "name": "데모 호텔"}, "offer": "기본 오퍼",
 "pairs": [{"room": "디럭스", "rate_plan": "조식 포함"}, {"room": "스위트", "rate_plan": "룸온리"}],
 "dates": ["2026-12-25", "2026-12-26", "2027-01-01", "2027-01-02"]}
```

- `dates`: 겹치지 않는 오름차순 ISO 날짜 목록. 요일 조건은 날짜로 풀어 적는다.
- 바꾸기 요청과 목표 값 표도 범위 파일로 쓸 수 있다. 그 요청의 객실 · 요금제 · 날짜를 읽는다.

### 바꾸기 요청 (`kind: change`)

```json
{"kind": "change", "hotel": {"id": "1", "name": "데모 호텔"}, "offer": "기본 오퍼",
 "rooms": [], "rate_plans": [],
 "pairs": [{"room": "디럭스", "rate_plan": "조식 포함"}, {"room": "디럭스", "rate_plan": "룸온리"},
           {"room": "스위트", "rate_plan": "조식 포함"}, {"room": "스위트", "rate_plan": "룸온리"}],
 "dates": ["2026-12-25", "2026-12-26", "2027-01-01", "2027-01-02"],
 "field": "sell",
 "operation": {"kind": "percent", "value": "10"},
 "occupancies": [], "nights": [],
 "scale_child_surcharge": false,
 "sentence": "데모 호텔 연말 금·토, 디럭스랑 스위트 10% 올려줘"}
```

- `pairs` 를 적고 `rooms`·`rate_plans` 는 빈 목록으로 둔다(쌍에서 채워진다).
- `field`: `sell`(판매가) · `list`(정가) · `supply`(공급 원가).
- `operation`:

| `kind` | `value` | 뜻 |
|---|---|---|
| `amount` | `"10000"`, `"-5000"` | 칸마다 그만큼 더한다 |
| `percent` | `"10"`, `"-5"` | 칸마다 그 비율. 아동이 있는 칸은 성인 몫에만 곱한다(`scale_child_surcharge: true` 면 칸 전체) |
| `set` | `"350"` + `"base_occupancy": "A2"` | 그날 기준 인원 1박 칸을 그 값으로, 다른 칸은 같은 만큼 옮겨 차이를 둔다 |
| `clear` | `null` | 정가·공급 원가를 비운다(판매가는 비울 수 없다) |

- `occupancies`·`nights`: 칸을 좁힐 때만 적는다. 비우면 모든 인원 조합 · 모든 박수 층이다. `occupancies` 는 인원 조합 키(`""` 인원 무관 · `A2` 성인 2 · `A3` 성인 3 · `A2C1_CHD` 성인 2 + 아동 1, 뒤는 그 호텔의 밴드 코드), `nights` 는 박수 층의 시작 박수(1, 3 …)다. 적은 칸만 움직이고 규칙 · 표시 · 저장은 그대로다. `set` 이면 `base_occupancy` 와 1박이 그 안에 있어야 한다. 읽은 값에 없는 키 · 층이면 `plan` 이 읽은 것을 대며 거절한다.

### 목표 값 표 (`kind: targets`)

짧은 표를 붙여 넣었을 때 칸마다 넣을 값을 그대로 옮긴다. 지금 값과 다른 칸만 바뀐다. 적지 않은 필드는 그대로, `null` 로 적은 필드(정가·공급 원가)는 비운다.

```json
{"kind": "targets", "hotel": {"id": "1", "name": "데모 호텔"}, "offer": "기본 오퍼", "sentence": "1/2 디럭스 조식 성인 2 는 330, 3박은 297",
 "targets": [
   {"key": {"room": "디럭스", "rate_plan": "조식 포함", "date": "2027-01-02", "occupancy": "A2", "nights": 1},
    "values": {"sell": "330", "list": "380"}},
   {"key": {"room": "디럭스", "rate_plan": "조식 포함", "date": "2027-01-02", "occupancy": "A2", "nights": 3},
    "values": {"sell": "297", "list": null}}]}
```

- `occupancy`·`nights` 는 위 바꾸기 요청과 같은 키다.
- 가격 없던 칸의 목표는 새로 생기는 칸이다. 판매가가 있어야 하고, 그 객실 · 요금제에 읽힌 적 있는 인원 조합 · 박수여야 한다.

## 빨간 줄 고름 파일

```json
[{"rule": "ABOVE_LIST", "choice": "clear_list"},
 {"rule": "OVER_30", "choice": "include",
  "cells": [{"room": "디럭스", "rate_plan": "조식 포함", "date": "2026-12-25", "occupancy": "A2", "nights": 1}]}]
```

`cells` 가 없으면 그 규칙의 모든 칸, 있으면 그 칸만이다(칸을 짚은 고름이 앞선다). 칸 키는 `plan` 답의 `unresolved[].key` 를 그대로 옮긴다. 고를 수 있는 값: `ABOVE_LIST` → `raise_list`·`clear_list`·`keep`, `BELOW_COST` → `include`·`keep`, `OVER_30` → `include`·`keep`. 적용할 수 없는 칸(`NOT_POSITIVE`·`NEGATIVE_SUPPLY`·`NO_ADULT_CELL`·`NO_BASE_CELL`·`NEW_WITHOUT_SELL`·`NEW_NOT_SHOWN`)은 고를 수 없다.

## 오류와 할 일

문장은 담당자에게 쉬운 말로 옮겨 전할 수 있다. 아래에 없는 오류는 멈추고 문장 그대로 보고한다.

| 오류 (앞부분) | 뜻 · 할 일 |
|---|---|
| `hotel 은 stayPrice.look() 이 준 {id, name} 을 그대로 적습니다` | 요청 파일의 `hotel` 에 번호가 없다. `look()` 의 `hotel` 을 그대로 옮긴다 |
| `readPair 답이 없는 부를 값이 N개 있습니다` | 「읽기」 2 를 마저 한다. 그 값으로 readPair 를 부른다 |
| `예약 있는 날 물음이 N개 남았습니다` | `reserved` 가 `done` 이 될 때까지 「읽기」 3 을 마저 한다 |
| `… 를 읽지 못했습니다: …` | readPair 답이 실패였다. 뒤의 페이지 오류를 page.md 에서 찾는다. 범위를 고쳤으면 새 폴더로 다시 읽는다 |
| `refetch` 가 있는 오류 · `받지 못했거나 잘린 쪽이 있습니다` | 「읽기」 5 의 조각 받기 |
| `… 의 답이 잘렸습니다` | 작업의 답이 잘렸다. `stayPrice.last()` 로 다시 받아 그 파일을 갈아 끼운다(읽기 작업이면 다시 불러도 된다) |
| `조각 … 을 이어 보니 바이트 수나 CRC-32 · FNV-1a 가 맞지 않습니다` · `… 두 번 왔는데 서로 다릅니다` · `이 답의 물음에서 나온 것이 아닙니다` | 옮겨 적은 쪽이 틀렸거나 다른 읽기의 파일이 섞였다. 앞선 읽기의 조각은 `--earlier` 로만 준다(파일을 베껴 오지 않는다). 새 폴더로 읽기를 다시 한다 |
| `… 의 답이 물은 호텔(…)이 아닌 … 호텔에서 읽은 것입니다` · `읽기 답에서 호텔을 하나로 정하지 못했습니다` | 다른 호텔의 탭에서 읽은 답이 섞였다. 새 폴더로 읽기를 다시 한다 |
| `읽은 날과 판매일 없는 날을 합쳐도 물은 날과 맞지 않습니다` · `… 를 물었는데 화면은 …` | 화면이 물은 것과 다르다. 멈추고 보고한다 |
| `판매일 있는 날을 하나도 읽지 못해 통화를 모릅니다` | 고른 날이 모두 판매일 없음이다. 담당자에게 그 날들은 판매일이 열려 있지 않다고 알린다 |
| `가감 확인 단계가 N줄을 숨겼습니다` | 예약 물음이 덜 쪼개졌다. `reserved` 의 `ask` 를 마저 묻는다 |
| `읽은 값은 호텔 … 것이고, 요청은 …` · `방금 읽은 값은 호텔 … 것이고` · `지금 읽은 값은 호텔 … 것이고` | 다른 호텔(또는 오퍼)의 값이다. 이름이 같아도 번호가 다르면 다른 호텔이다. 「준비」 3 으로 탭을 확인한다 |
| `읽지 않은 객실·요금제가 있습니다` · `읽은 값에 없는 날짜` · `지금 값을 읽지 않은 날짜` | 읽은 범위가 좁다. 범위를 넓혀 다시 읽는다 |
| `읽은 값에 없는 인원 조합: …` · `읽은 값에 없는 박수 층: …` | 좁힌 칸이 그 객실 · 요금제에 없다. 괄호 안의 읽은 것을 담당자에게 보여 주고 다시 받는다 |
| `새 값 지정의 기준 칸(…)이 고른 칸에 없습니다` | 새 값 지정은 기준 칸을 움직여 나머지를 옮긴다. 기준 칸을 넣을지, 금액(+/−)이나 퍼센트로 말할지 담당자에게 묻는다 |
| `날짜는 겹치지 않게 오름차순 ISO 형식…` · `새 값 지정(set)에만, 그리고 반드시 기준 인원 조합을 적습니다` · `비우기(clear)에만 금액이 없습니다` · `판매가는 비울 수 없습니다` · `같은 객실·요금제 쌍이 두 번 있습니다` · `읽을 범위에는 객실 · 요금제와 날짜가 하나 이상 있어야 합니다` · `입력 JSON 에 필요한 칸이 없습니다` | 요청 파일 모양을 고친다 |
| `고를 수 있는 것은 빨간 줄 규칙뿐입니다` · `… — 고를 수 있는 것: …` · `「…」 항목이 아닙니다` | 고름 파일을 고친다 |
| `정가를 같은 만큼 올릴 수 없는 칸입니다(전 정가가 없음)` | 그 칸은 정가가 없다. 담당자에게 다른 고름을 묻는다 |
| `저장 단계가 없습니다. 빨간 줄 칸을 먼저 골라 주세요` | 빨간 줄을 다 고르지 않았다 |
| `…번 변경의 요청과 다른 계산입니다. 미리보기를 다시 만들어 주세요` | `begin` 에 다른 번호의 계산 파일을 줬다. 그 번호를 낸 `plan` 의 파일을 쓴다 |
| `이미 다른 저장 단계로 적용을 시작했습니다` | 그 번호는 이미 적용을 시작했다. `calls` 로 남은 단계만 한다 |
| `아직 적용을 시작하지 않았습니다(begin)` | `begin` 을 먼저 |
| `…번 변경은 멈춰 있습니다` | 「중간에 멈췄을 때」. 다시 읽고 `check` 가 이어서 해도 된다고 하면 `calls` 를 다시 부른다 |
| `…번 저장(…)의 답이 아닙니다` · `…의 답이 장부의 그 단계와 다른 값을 물었습니다` · `…번째 저장이 없습니다` | 다른 단계의 답이거나 payload 를 바꿔 넣었다. 장부에 적히지 않았다. 그 단계를 다시 부르지 말고 `stayPrice.last()` 로 맞는 답을 찾는다 |
| `이 변경으로 저장된 것 가운데 아직 되돌리지 않은 것이 없습니다` | 적용된 적이 없거나 이미 다 되돌렸다. 담당자에게 그렇게 알린다 |
| `…번은 저장해 둔 상태입니다` / `…번은 저장해 둔 상태가 아닙니다` | `rollback` 과 `restore` 를 바꿔 쓴다 |
| `고른 범위에 되돌릴 것이 없습니다` · `고른 범위에 저장해 둔 값이 없습니다` | 고르기 플래그가 맞는 칸이 없다. 객실·요금제·날짜·인원 조합 키를 다시 본다 |
| `이 장부는 더 새 판 도우미가 만든 것입니다` | 담당자에게 도우미를 새로 받아 달라고 한다 |
