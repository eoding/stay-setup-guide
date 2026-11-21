# 적용하기 — 바꾸기 · 되돌리기 공통

SKILL.md 「적용하기」가 이 파일을 연다. 담당자가 미리보기(되돌리기 미리보기)를 보고 분명히 "적용"("되돌려")이라고 한 뒤다.

놓치면 안 되는 것: 같은 저장을 두 번 누르지 않는다 — 한 번 부른 `applyCharge` 는 다시 부르지 않고, 답을 잃었으면 `stayCharge.last()` 로 받는다. 저장이 안 됐거나 멈추면 다음 저장을 하지 않는다.

필요한 것: 장부 번호 N, 그 번호를 낸 계산 파일, 그 미리보기에 담당자가 분명히 한 "적용"(되돌리기는 "되돌려").

1. **직전에 다시 읽고 시작하기.** `read-calls --record N` 으로 SKILL.md 「읽기」 → S2. `python3 scripts/charge_change.py begin --change N --plan "<계산 파일>" --snapshot "<S2>"`. `status: applying` 이면 "적용 직전에 ERP 를 다시 읽었습니다. 미리보기 때와 모든 칸이 같아서 그대로 적용합니다." 종료 1(`same: false`)이면 아무것도 저장하지 않았다 — "미리보기 뒤에 ERP 의 값이 바뀌었습니다(<`differences` 의 부과금>)." 하고 SKILL.md 「2」 의 읽기부터 새 미리보기를 만든다.
2. `python3 scripts/charge_change.py calls --change N` 의 `calls` 를 차례로 하나씩: `await stayCharge.applyCharge(<payload 그대로>)` → 답을 그대로 `<작업>/적용-N/<no>.json` 에 저장 → `python3 scripts/charge_change.py record-result --change N --result "<그 파일>"`. `saved: true` 이고 `status: applying` 이면 다음, `applied` 면 3. 그 밖이면 다음 저장을 하지 않고 [stopped.md](stopped.md) 로 간다 — 다시 읽어 `check` 가 이어서 해도 된다고 하기 전에는 이어서 하지 않는다. 답을 잃었으면 다시 부르지 말고 `stayCharge.last()` 로 받는다.
3. **뒤에 다시 읽기.** `read-calls --record N` 으로 SKILL.md 「읽기」 → S3. `python3 scripts/charge_change.py verify --change N --snapshot "<S3>"`.
4. `python3 scripts/charge_change.py render result --change N --snapshot "<S3>"` → `page` 를 연다. 3 의 `names` 가 있으면 그 문장도 그대로 말한다.
   - `same: true` 면 "적용했고, 다시 읽어 확인했습니다. 그 부과금의 다른 금액과 칸도 그대로입니다. 이미 받은 예약의 금액은 그대로입니다. 되돌리려면 'N번 되돌려'라고 하세요."
   - `same: false`(종료 1)면 "적용했지만 다시 읽었더니 다른 곳이 있습니다" 하고 `mismatches`(넣은 값과 다름) · `moved`(그대로여야 할 것이 달라짐)를 하나씩 말한다. 다시 저장하지 않는다.
