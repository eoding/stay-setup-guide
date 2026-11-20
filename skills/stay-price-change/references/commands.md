# price_change.py — 명령과 파일

차례: 공통 · 하위 명령 · 요청 파일 · 빨간 줄 고름 파일 · 오류와 할 일

## 공통

```bash
python3 scripts/price_change.py <하위 명령> [플래그] [--out <파일>]
```

- 결과는 표준 출력에 JSON 으로 쓴다. `--out` 을 주면 그 파일에도 쓴다(`render` 는 HTML 을 그 파일에 쓰고 표준 출력에는 `{page}` 만).
- 종료 코드: 0 됨 · 1 다른 값이 있음(`stale`·`verify` 의 `same: false`) · 2 입력이나 순서가 맞지 않음. 2 일 때 표준 오류에 `{"error": "…"}`, 잘린 조각이 있으면 `"refetch": [{"id", "at", "size"}]` 도 온다.
- 장부: `~/Documents/어딩 Stay 가격 변경 기록/가격장부.sqlite3`. 환경 변수 `STAY_PRICE_LEDGER_DIR` 로 폴더를 바꿀 수 있다. 장부는 지우지 않는다.
- 각 명령의 플래그는 `--help` 가 정본이다.

## 하위 명령

| 명령 | 플래그 | 하는 일 · 답 |
|---|---|---|
| `read-calls` | `--request` | 요청의 범위 → `{pairs: [readPair 부를 값], reserved: [readReserved 첫 물음]}`. 기간은 고른 날만 덮게 끊는다(readPair 186일씩). |
| `reserved` | `--probes` (reserved 목록 파일) · `--result` (여러 번) | readReserved 물음과 답 → `{done, ask, answered, failed}`. 숨긴 줄이 있던 물음은 객실 → 요금제 → 날짜 반쪽 순으로 쪼개 `ask` 에 다시 낸다. 답은 덧붙여 다시 부르면 처음부터 다시 셈한다. |
| `read` | `--hotel` · `--pair-result` (여러 번) · `--reserved-probes` · `--reserved-result` (여러 번) · `--read-at` · `--price-page`·`--adjust-page`(화면 조각 파일, 시험용) | 브라우저 답 → 지금 값 `{hotel, offer, currency, read_at, cells, reserved, pairs, room_names, no_sale}`. 예약 물음이 남았으면 거절한다. |
| `plan` | `--snapshot` · `--request` · `--resolutions` · `--record` | 미리보기 계산 → `{change_id, counts, plan, unresolved, steps}`. `--record` 면 장부에 미리보기로 적고 `change_id` 를 준다. 빨간 줄을 다 고르지 않았으면 `steps` 가 null. |
| `render` | `preview`·`result`·`rollback`·`prices` 중 하나 + `--plan` (preview·rollback) · `--change` (result) · `--snapshot` (prices) | 페이지 HTML. `--out` 이 없으면 기록 폴더에 `<날짜 시각> · <호텔> · <페이지 이름>.html` 로 쓴다. 답 `{page}` 는 그 경로. |
| `begin` | `--change` · `--plan` (`steps` 가 든 plan.json 또는 rollback.json) | 적용 시작. 저장 단계를 장부에 적는다. 같은 단계로 다시 부르면 아무것도 바꾸지 않는다. → `{change_id, status, steps}` |
| `calls` | `--change` | 아직 저장되지 않은 단계(멈춘 단계 포함) → `{change_id, status, calls: [{no, op, payload}]}`. `op` 는 `applyBulk` 또는 `applyCell`, `payload` 는 그 작업에 그대로 넘긴다. |
| `record-result` | `--change` · `--result` (답 파일 하나) | 브라우저 답 하나 → 그 단계를 됨·멈춤으로 적는다 → `{change_id, step, saved, note, status}`. 다른 단계·다른 값을 물은 답이면 거절한다. `saved: "unknown"` 은 멈춤으로 적힌다. |
| `record-step` | `--change` · `--step` · `--saved` 또는 `--failed` · `--note` | 저장 한 번의 결과를 손으로 적는다. 「알 수 없음」을 다시 읽어 저장된 것으로 확인했을 때 `--saved` 로 쓴다. 이미 저장됨인 단계는 바꾸지 않는다. |
| `verify` | `--change` · `--snapshot` | 적용 뒤 다시 읽은 값과 견준다 → `{change_id, same, mismatches: [{key, label, field, after, seen, seen_state}]}`. 저장된 단계의 값만 본다. |
| `stale` | `--before` · `--after` | 미리보기 때 읽은 값과 방금 읽은 값 → `{same, differences: [{key, then, now}]}`. 한쪽에만 있는 칸도 다른 칸이다(같은 범위로 읽어야 한다). 예약 표시는 견주지 않는다. |
| `rollback` | `--change` · `--snapshot` · `--include-kept` · `--room`·`--rate-plan`·`--occupancy` (여러 번) · `--from`·`--to` · `--record` · `--sentence` | 변경 하나(또는 고른 일부)를 되돌리는 계산 → `{change_id, scope, rollback, steps, reserved}`. 저장된 단계의 칸만 되돌린다. `rollback` 안에 `restore_to`(적어 둔 값의 시각)·`restored`·`kept`(세 값과 `cause`)·`unremovable`. |
| `restore` | `--saved` · `--snapshot` · 고르기 플래그 · `--record` · `--sentence` | 지금 상태 저장으로 적은 상태로 되돌리는 계산. 답은 `rollback` 과 같은 모양. 장부에는 변경으로 적혀 이것도 되돌릴 수 있다. |
| `save-snapshot` | `--snapshot` · `--sentence` | 지금 값을 장부에만 적는다 → `{change_id}`. |
| `list` | 없음 | `{ledger, changes: [{id, kind, status, hotel, offer, sentence, read_at, created_at, applied_at, verified_at, reverses, items, written, rolled_back}]}`. 새것부터. `kind`: change · snapshot · rollback. `status`: previewed → applying → stopped / applied. |

`counts` 의 칸: `cells`(계산한 칸) · `will_change`(그중 적용할 수 없는 칸을 뺀 수) · `blocked` · `red` · `reserved` · `closed` · `new` · `skipped`, 그리고 규칙 코드마다의 수(`ABOVE_LIST` 등).

## 요청 파일

### 바꾸기 요청과 범위 요청 (`kind: change`)

```json
{"kind": "change", "hotel": "데모 호텔", "offer": "기본 오퍼",
 "rooms": [], "rate_plans": [],
 "pairs": [{"room": "디럭스", "rate_plan": "조식 포함"}, {"room": "디럭스", "rate_plan": "룸온리"},
           {"room": "스위트", "rate_plan": "조식 포함"}, {"room": "스위트", "rate_plan": "룸온리"}],
 "dates": ["2026-12-25", "2026-12-26", "2027-01-01", "2027-01-02"],
 "field": "sell",
 "operation": {"kind": "percent", "value": "10"},
 "scale_child_surcharge": false,
 "sentence": "데모 호텔 연말 금·토, 디럭스랑 스위트 10% 올려줘"}
```

- `hotel` 은 `read --hotel` 과 같은 글자, `offer`·`pairs` 의 이름은 가격 캘린더의 오퍼 칩·객실 · 요금제 칩에 보이는 그대로다. `pairs` 를 적고 `rooms`·`rate_plans` 는 빈 목록으로 둔다(쌍에서 채워진다).
- `dates`: 겹치지 않는 오름차순 ISO 날짜 목록. 요일 조건은 날짜로 풀어 적는다.
- `field`: `sell`(판매가) · `list`(정가) · `supply`(공급 원가).
- `operation`:

| `kind` | `value` | 뜻 |
|---|---|---|
| `amount` | `"10000"`, `"-5000"` | 칸마다 그만큼 더한다 |
| `percent` | `"10"`, `"-5"` | 칸마다 그 비율. 아동이 있는 칸은 성인 몫에만 곱한다(`scale_child_surcharge: true` 면 칸 전체) |
| `set` | `"350"` + `"base_occupancy": "A2"` | 그날 기준 인원 1박 칸을 그 값으로, 다른 칸은 같은 만큼 옮겨 차이를 둔다 |
| `clear` | `null` | 정가·공급 원가를 비운다(판매가는 비울 수 없다) |

- 범위 요청은 같은 모양에 `"operation": {"kind": "amount", "value": "0"}` 을 넣는다. 읽기 명령은 범위(오퍼·쌍·날짜)만 본다.

### 목표 값 표 (`kind: targets`)

칸마다 넣을 값을 적는다. 지금 값과 다른 칸만 바뀐다. 적지 않은 필드는 그대로, `null` 로 적은 필드(정가·공급 원가)는 비운다.

```json
{"kind": "targets", "hotel": "데모 호텔", "offer": "기본 오퍼", "sentence": "2027 요금표로 날짜별 가격 바꿔줘",
 "targets": [
   {"key": {"room": "디럭스", "rate_plan": "조식 포함", "date": "2027-01-02", "occupancy": "A2", "nights": 1},
    "values": {"sell": "330", "list": "380"}},
   {"key": {"room": "디럭스", "rate_plan": "조식 포함", "date": "2027-01-02", "occupancy": "A2", "nights": 3},
    "values": {"sell": "297", "list": null}}]}
```

- `occupancy` 는 읽은 값의 인원 조합 키 그대로다: `""` 인원 무관 · `A2` 성인 2 · `A3` 성인 3 · `A2C1_CHD` 성인 2 + 아동 1(뒤는 그 호텔의 밴드 코드). `nights` 는 박수 층의 시작 박수(1, 3 …).
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
| `예약 있는 날 물음이 N개 남았습니다` | `reserved` 가 `done` 이 될 때까지 「읽기」 4 를 마저 한다 |
| `… 를 읽지 못했습니다: …` | readPair 답이 실패였다. 뒤의 페이지 오류를 page.md 에서 찾는다 |
| `refetch` 가 있는 오류 · `받지 못했거나 잘린 쪽이 있습니다` | 「읽기」 5 의 refetch 처리 |
| `… 의 답이 잘렸습니다` | 작업의 답이 잘렸다. `stayPrice.last()` 로 다시 받아 그 파일을 갈아 끼운다(읽기 작업이면 다시 불러도 된다) |
| `조각 … 을 이어 보니 바이트 수나 CRC-32 가 맞지 않습니다` · `… 두 번 왔는데 서로 다릅니다` · `이 답의 물음에서 나온 것이 아닙니다` | 옮겨 적은 쪽이 틀렸거나 다른 읽기의 파일이 섞였다. 새 폴더로 읽기를 다시 한다 |
| `readPair 의 답이 아닙니다` · `readReserved 의 답이 아닙니다` | 파일이 섞였다. pair-·resv- 파일을 나눠 넘긴다 |
| `읽은 날과 판매일 없는 날을 합쳐도 물은 날과 맞지 않습니다` · `… 를 물었는데 화면은 …` | 화면이 물은 것과 다르다. 멈추고 보고한다 |
| `판매일 있는 날을 하나도 읽지 못해 통화를 모릅니다` | 고른 날이 모두 판매일 없음이다. 담당자에게 그 날들은 판매일이 열려 있지 않다고 알린다 |
| `가감 확인 단계가 N줄을 숨겼습니다` | 예약 물음이 덜 쪼개졌다. `reserved` 의 `ask` 를 마저 묻는다 |
| `읽은 값은 H · O 것이고, 요청은 …` | `read --hotel` 과 요청의 `hotel`·`offer` 글자가 다르다. 맞춘다 |
| `읽지 않은 객실·요금제가 있습니다` · `읽은 값에 없는 날짜` · `지금 값을 읽지 않은 날짜` | 읽은 범위가 좁다. 범위를 넓혀 다시 읽는다 |
| `날짜는 겹치지 않게 오름차순 ISO 형식…` · `새 값 지정(set)에만, 그리고 반드시 기준 인원 조합을 적습니다` · `비우기(clear)에만 금액이 없습니다` · `판매가는 비울 수 없습니다` · `같은 객실·요금제 쌍이 두 번 있습니다` · `입력 JSON 에 필요한 칸이 없습니다` | 요청 파일 모양을 고친다 |
| `고를 수 있는 것은 빨간 줄 규칙뿐입니다` · `… — 고를 수 있는 것: …` · `「…」 항목이 아닙니다` | 고름 파일을 고친다 |
| `정가를 같은 만큼 올릴 수 없는 칸입니다(전 정가가 없음)` | 그 칸은 정가가 없다. 담당자에게 다른 고름을 묻는다 |
| `저장 단계가 없습니다. 빨간 줄 칸을 먼저 골라 주세요` | 빨간 줄을 다 고르지 않았다 |
| `…번 변경의 요청과 다른 계산입니다. 미리보기를 다시 만들어 주세요` | `begin` 에 다른 번호의 계산 파일을 줬다. 그 번호를 낸 `plan` 의 파일을 쓴다 |
| `이미 다른 저장 단계로 적용을 시작했습니다` | 그 번호는 이미 적용을 시작했다. `calls` 로 남은 단계만 한다 |
| `아직 적용을 시작하지 않았습니다(begin)` | `begin` 을 먼저 |
| `…번 저장(…)의 답이 아닙니다` · `…의 답이 장부의 그 단계와 다른 값을 물었습니다` · `…번째 저장이 없습니다` | 다른 단계의 답이거나, payload 를 바꿔 넣었거나, 저장 번호가 없는 답(`앞 작업이 아직 끝나지 않았습니다` 같은)이다. 장부에 적히지 않았다. 그 단계를 다시 부르지 말고 `stayPrice.last()` 로 맞는 답을 찾는다 |
| `이 변경으로 저장된 것 가운데 아직 되돌리지 않은 것이 없습니다` | 적용된 적이 없거나 이미 다 되돌렸다. 담당자에게 그렇게 알린다 |
| `…번은 저장해 둔 상태입니다` / `…번은 저장해 둔 상태가 아닙니다` | `rollback` 과 `restore` 를 바꿔 쓴다 |
| `고른 범위에 되돌릴 것이 없습니다` · `고른 범위에 저장해 둔 값이 없습니다` | 고르기 플래그가 맞는 칸이 없다. 객실·요금제·날짜·인원 조합 키를 다시 본다 |
| `이 장부는 더 새 판 도우미가 만든 것입니다` | 담당자에게 도우미를 새로 받아 달라고 한다 |
