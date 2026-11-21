# 되돌리기

SKILL.md 「3. 되돌리기」가 이 파일을 연다. 담당자가 "어제 바꾼 부과금 되돌려줘"처럼 장부의 변경을 되돌리라고 할 때다. 「준비」 를 먼저 하고(새 작업 폴더), 「준비」 5 의 목록에서 맞는 줄을 골라 확인받는다 — 맞는 줄이 하나뿐이어도 묻는다: "이것 맞나요? <그 줄의 `line`>". 상태가 `previewed` · `empty` · `replaced` · `rolled_back` 인 줄은 되돌릴 것이 없다 — 읽지 않고 SKILL.md 「되돌릴 것이 없을 때」의 문장으로 답한다. 담당자가 "응"·"맞아"처럼 분명히 답한 뒤에 읽는다.

1. `read-calls --record <N>` 으로 SKILL.md 「읽기」 → `<R>/snapshot.json`.
2. `python3 scripts/charge_change.py rollback --change <N> --snapshot "<R>/snapshot.json" --record --sentence "<담당자 말>" --out "<작업>/rollback-1.json"`(부과금 몇 개만이면 `--charge <부과금 번호>` 를 여러 번). 짧은 답의 `change_id` 가 M.
3. `python3 scripts/charge_change.py render rollback --plan "<작업>/rollback-1.json"` → `page` 를 연다. "○월 ○일 ○시 ○분에 적어 둔 값으로 되돌립니다(`restore_to`)." 되돌리는 칸 수, 그대로 두는 것(`kept` — 그 사이 값이 달라진 것)의 수와 까닭(`kept_why`)을 반드시 말한다. ERP 번호와 적용 범위 기록은 되돌아오지 않는다고 말한다. `restored` 가 0 이면 되돌릴 것이 없다고만 하고 "되돌려"를 청하지 않는다.
4. "되돌려" → SKILL.md 「적용하기」(번호 M, 계산 파일 `rollback-1.json`). "그것도 되돌려"면 2 에 `--include-kept --replaces <M>` 을 붙여 `rollback-2.json` 으로 다시 계산하고 3 부터 한다.
