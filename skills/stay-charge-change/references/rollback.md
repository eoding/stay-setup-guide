# 되돌리기

SKILL.md 「3. 되돌리기」가 이 파일을 연다. 담당자가 "어제 바꾼 부과금 되돌려줘"처럼 장부의 변경을 되돌리라고 할 때다. 「준비」 를 먼저 하고(새 작업 폴더), 「준비」 5 의 목록에서 맞는 줄을 골라 확인받는다 — 맞는 줄이 하나뿐이어도 묻는다: "이것 맞나요? <그 줄의 `line`>". 상태가 `previewed` · `empty` · `replaced` · `rolled_back` 인 줄은 되돌릴 것이 없다 — 읽지 않고 SKILL.md 「되돌릴 것이 없을 때」의 문장으로 답한다. 담당자가 "응"·"맞아"처럼 분명히 답한 뒤에 읽는다.

**되돌리기를 되돌려 달라면.** 되돌리기(목록의 `kind: rollback`)는 다시 되돌리지 않는다 — 되돌린 것을 되돌리면 장부가 어느 값이 ERP 에 살아 있는지 말하지 못하게 되어 `rollback` 이 `…다시 되돌리지 않습니다` 로 거절한다(ERP 의 [되돌리기]도 한 번만 된다). 확인받은 줄이 그것이면 읽지 않고 말한다: "장부 <`id`>번은 되돌리기라 다시 되돌리지 않습니다. 되돌린 값으로 다시 바꾸려면 같은 내용으로 새로 바꾸면 됩니다 — <되돌린 변경의 `line`>. 그렇게 할까요?" 되돌린 변경은 목록에서 `undone_by` 에 그 번호가 든 줄이다. "응"이면 그 변경과 같은 요청(그 줄의 범위와 한 일)으로 SKILL.md 「2. 부과금 금액 바꾸기」를 새 작업 폴더에서 처음부터 한다 — 새로 읽어 새 미리보기를 보이고, 빨간 줄도 다시 고르고, 분명한 "적용"을 받는다.

1. `read-calls --record <N>` 으로 SKILL.md 「읽기」 → `<R>/snapshot.json`.
2. `python3 scripts/charge_change.py rollback --change <N> --snapshot "<R>/snapshot.json" --record --sentence "<담당자 말>" --out "<작업>/rollback-1.json"`(부과금 몇 개만이면 `--charge <부과금 번호>` 를 여러 번). 짧은 답의 `change_id` 가 M.
3. `python3 scripts/charge_change.py render rollback --plan "<작업>/rollback-1.json"` → `page` 를 연다. "○월 ○일 ○시 ○분에 적어 둔 값으로 되돌립니다(`restore_to`)." 되돌리는 칸 수, 그대로 두는 것(`kept` — 그 사이 값이 달라진 것)의 수와 까닭(`kept_why`)을 반드시 말한다. ERP 번호와 적용 범위 기록은 되돌아오지 않는다고 말한다. `restored` 가 0 이면 되돌릴 것이 없다고만 하고 "되돌려"를 청하지 않는다.
4. "되돌려" → SKILL.md 「적용하기」(번호 M, 계산 파일 `rollback-1.json`). "그것도 되돌려"면 2 에 `--include-kept --replaces <M>` 을 붙여 `rollback-2.json` 으로 다시 계산하고 3 부터 한다.
