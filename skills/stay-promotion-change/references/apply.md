# 적용하기 — 바꾸기 · 되돌리기 공통

SKILL.md 「적용하기」가 이 파일을 연다. 담당자가 미리보기(되돌리기 미리보기)를 보고 분명히 "적용"("되돌려")이라고 한 뒤다.

놓치면 안 되는 것: 같은 저장을 두 번 누르지 않는다 — 한 번 부른 `applyPromotion` 은 다시 부르지 않고, 답을 잃었으면 `stayPromotion.last()` 로 받는다. 저장이 안 됐거나 멈추면 다음 저장을 하지 않는다. 표식 없는 창에서는 저장하지 않는다.

필요한 것: 장부 번호 N, 그 번호를 낸 계산 파일, 그 미리보기에 담당자가 분명히 한 "적용"(되돌리기는 "되돌려").

읽기마다 SKILL.md 「읽기」를 그대로 한다. `read-calls --record N` 에는 `--look` 을 주지 않아도 된다 — 장부 번호가 읽을 프로모션을 정한다(주어도 쓰지 않는다).

1. **직전에 다시 읽고 시작하기.** `read-calls --record N` 으로 SKILL.md 「읽기」 → S2. `python3 scripts/promotion_change.py begin --change N --plan "<계산 파일>" --snapshot "<S2>"`. `status: applying` 이면 "적용 직전에 ERP 를 다시 읽었습니다. 미리보기 때와 모든 칸이 같아서 그대로 적용합니다." 종료 1(`same: false`)이면 아무것도 저장하지 않았다 — "미리보기 뒤에 ERP 의 값이 바뀌었습니다(<`differences` 의 프로모션>)." 하고 SKILL.md 「2」 의 읽기부터 새 미리보기를 만든다. 종료 2 면 아무것도 시작하지 않았다 — `이 ERP 는 아직 …` · `이 프로모션의 편집 창은 ERP 가 할인 단 줄이 어느 저장된 단에서 왔는지 모르는 상태라…`(단 줄 출처를 ERP 가 모르는 창 — 편집 창을 닫았다가 다시 열라는 말이 들어 있다)이면 그 문장을 그대로 말하고 끝낸다. 그 밖은 commands.md 「오류」.
2. `python3 scripts/promotion_change.py calls --change N --out "<작업>/적용-N/calls.json"` 의 `calls` 를 차례로 하나씩, 사이에 다른 일 없이 잇달아 한다 — 15분 동안 아무 일이 없으면 변경이 멈추고 [stopped.md](stopped.md) 로 간다: `await stayPromotion.applyPromotion(<payload 그대로>)` → 답을 그대로 `<작업>/적용-N/<no>.json` 에 저장 → `python3 scripts/promotion_change.py record-result --change N --result "<그 파일>"`. `saved: true` 이고 `status: applying` 이면 다음, `applied` 면 3. 그 밖이면 다음 저장을 하지 않고 [stopped.md](stopped.md) 로 간다.
3. **뒤에 다시 읽기.** `read-calls --record N` 으로 SKILL.md 「읽기」 → S3. `python3 scripts/promotion_change.py verify --change N --snapshot "<S3>"`.
4. `python3 scripts/promotion_change.py render result --change N --snapshot "<S3>"` → `page` 를 연다. 3 의 `names` 가 있으면 그 문장도 그대로 말한다.
   - `same: true` 면 "적용했고, 다시 읽어 확인했습니다. 그 프로모션의 다른 단 · 설정 · 화면에 안 보이는 설정도 그대로입니다." 3 의 `kept` 가 있으면 그 문장마다 그대로 말한다(「…단: 화면에 안 보이는 취소 조건은 저장 뒤에도 그대로입니다」 — 저장 전과 뒤에 읽은 창의 표식을 견준 것이다. 결과 페이지에도 있다). 그리고 "새 견적부터 바뀌고 이미 받은 예약의 금액은 그대로입니다. 되돌리려면 'N번 되돌려'라고 하세요." 되돌리기를 적용했으면 끝 문장 대신 "이 되돌리기도 'N번 되돌려'로 되돌릴 수 있습니다"라고 한다.
   - `same: false`(종료 1)면 "적용했지만 다시 읽었더니 다른 곳이 있습니다" 하고 `mismatches`(넣은 값과 다름) · `moved`(그대로여야 할 것이 달라짐)를 하나씩 말한다. 다시 저장하지 않는다.
