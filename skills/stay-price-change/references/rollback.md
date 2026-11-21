# 되돌리기 — 읽기 · 계산 · 미리보기 · 되돌려

SKILL.md 「4. 되돌리기」가 이 파일을 연다. 되돌릴 줄(변경이면 `rollback`, 저장해 둔 상태면 `restore`)을 담당자가 확인한 뒤다. 「준비」 를 먼저 한다(새 작업 폴더 — 견주기 바로 다음의 저장 상태로 되돌리기만 그 견주기의 폴더와 읽은 값을 그대로 쓴다, [compare.md](compare.md) 5).

놓치면 안 되는 것: 분명한 "되돌려" 없이는 「적용하기」로 가지 않는다. 그대로 두는 칸(`kept`)이 있으면 그 수와 까닭을 반드시 말한다. `restored` 가 0 이면 되돌릴 칸이 없다고 하고 "되돌려"를 청하지 않는다.

**되돌리기를 되돌려 달라면.** 되돌리기(목록의 `kind: rollback`)와 저장 상태로 되돌리기(범위 한 줄이 「…번 저장 상태로 되돌리기」)는 다시 되돌리지 않는다 — 되돌린 것을 되돌리면 장부가 어느 값이 ERP 에 살아 있는지 말하지 못하게 되어 `rollback` 이 `…다시 되돌리지 않습니다` 로 거절한다(ERP 의 [되돌리기]도 한 번만 된다). 확인받은 줄이 그것이면 읽지 않고 말한다: "장부 <`id`>번은 되돌리기라 다시 되돌리지 않습니다. 되돌린 값으로 다시 바꾸려면 같은 내용으로 새로 바꾸면 됩니다 — <되돌린 변경의 `line`>. 그렇게 할까요?" 되돌린 변경은 목록에서 `undone_by` 에 그 번호가 든 줄이다. "응"이면 그 변경과 같은 요청(그 줄의 범위와 한 일)으로 SKILL.md 「3. 가격 바꾸기」를 새 작업 폴더에서 처음부터 한다 — 새로 읽어 새 미리보기를 보이고, 빨간 줄도 다시 고르고, 분명한 "적용"을 받는다.

1. `read-calls --record <번호>` 로 SKILL.md 「읽기」 → `<R>/snapshot.json`.
2. 되돌리기 계산 — 변경(`change`)은 `rollback`, 저장해 둔 상태(`snapshot`)는 `restore`. 일부만이면 고르기 플래그를 붙인다: `--room`·`--rate-plan`(여러 번)·`--from`·`--to`(날짜)·`--occupancy`(읽은 값의 인원 조합 키, 성인 2 는 `A2`).

   ```bash
   python3 scripts/price_change.py rollback --change <N> --snapshot "<R>/snapshot.json" --record --sentence "<담당자 말>" --out "<작업>/rollback-1.json"
   python3 scripts/price_change.py restore --saved <S> --snapshot "<R>/snapshot.json" --record --sentence "<담당자 말>" --out "<작업>/rollback-1.json"
   ```

   짧은 답의 `change_id` 가 이 되돌리기의 번호 M 이다(나머지 칸은 commands.md 의 `rollback`). k 번째 계산은 `<작업>/rollback-<k>.json` 이다.
3. `render rollback --plan "<작업>/rollback-<k>.json"` → `page` 를 연다. 그리고 말한다: "○월 ○일 ○시 ○분에 적어 둔 값으로 되돌립니다(`restore_to`)." 되돌리는 칸 수, 지울 수 없는 칸 수(새로 생긴 칸 — ERP 에 지우는 길이 없다), 예약 있는 날의 칸이 있으면 그 날도 되돌리고 받은 예약의 금액은 그대로라는 것, `undone` 이 있으면 이미 되돌린 칸 수와 그 번호. 그대로 두는 칸(`kept`, 그 사이 값이 달라진 칸)이 있으면 반드시 그 수와 까닭(`kept_why`)을 말한다. `restored` 가 0 이면 되돌릴 칸이 없다고 하고 "되돌려"를 청하지 않는다.
4. "되돌려" → SKILL.md 「적용하기」(이 되돌리기의 번호 M, 계산 파일 `rollback-<k>.json`). "○칸도 포함해서 되돌려"면 2 의 `rollback` 에 `--include-kept --replaces <M>` 을 붙여 다음 이름으로 다시 계산하고 3 부터 한다(앞 번호 M 은 `replaced` 가 되어 `begin` 이 받지 않는다).
