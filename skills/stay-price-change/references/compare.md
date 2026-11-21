# 저장해 둔 상태와 견주기

SKILL.md 「6. 저장해 둔 상태와 견주기」와 [sheet.md](sheet.md) 「(가) 시즌 원판 바꾸기」 3 이 이 파일을 연다. 담당자가 "아침에 저장해 둔 것과 뭐가 달라졌어?"처럼 저장해 둔 상태(목록의 `snapshot` 줄)와 지금을 견주라고 할 때다. 아무것도 바꾸지 않고 장부에도 적지 않는다.

1. **어느 저장인지.** SKILL.md 「준비」 를 하고 「준비」 5 의 목록에서 맞는 `snapshot` 줄을 골라 확인받는다(하나뿐이어도 묻는다): "이것 맞나요? 장부 <`id`>번 · <`read_at` 의 월/일 시:분> 저장 · <`scope`>". 아래 S 는 그 번호다.
2. **읽기.** `read-calls --record S` 로 SKILL.md 「읽기」 → `<R>/snapshot.json`.
3. **견주기.**

   ```bash
   python3 scripts/price_change.py compare --saved S --snapshot "<R>/snapshot.json" --out "<작업>/compare-1.json"
   python3 scripts/price_change.py render compare --plan "<작업>/compare-1.json"
   ```

   페이지를 연다. 그 작업에서 k 번째 견주기는 `compare-<k>.json` 이다.
4. **말하기.** 짧은 답의 `counts` 로 말한다(0 인 것은 뺀다): "장부 S번에 저장해 둔 값과 지금 값을 칸마다 견주었습니다. 아무것도 바꾸지 않았습니다. 바뀐 칸 ○칸(그 가운데 예약 있는 날의 칸 ○칸), 새로 생긴 칸 ○칸, 없어진 칸 ○칸, 판매 마감 · 판매 가능만 바뀐 칸 ○칸입니다." 바뀐 칸의 예는 `example` 하나를 숫자로(그 칸 · 그 값(`field` — 판매가 · 정가 · 공급 원가) `then` → `now`). 그리고 누가 바꿨는지:
   - `written_by` 의 기록마다: "그 가운데 ○칸(`cells`)은 저장한 뒤 이 컴퓨터의 도우미가 바꾼 것입니다 — 장부 <`change_id`>번 <`what`>(“<`sentence`>”, <`at` 의 월/일 시:분>)." `what` 이 「변경」이면 덧붙인다: "그 변경만 되돌리려면 '<`change_id`>번 되돌려'라고 하세요."
   - `counts.outside` 가 있으면: "○칸은 장부에 없는 변화입니다 — 도우미 밖(ERP 화면 · 시즌 채우기 · 다른 컴퓨터)에서 바뀌었습니다. ERP 화면에서 직접 고치셨던 칸이 덮였는지는 도우미가 가려내지 못합니다." (ERP 의 '손입력' 표시를 도우미가 읽지 못한다.) `counts.outside` 가 0 이면 이 말은 하지 않는다.
   - `edited` 가 있으면: "전에 날짜별로 바꿔 두었던 칸 ○칸(장부 <`edited_by`>번)이 다른 값으로 바뀌었습니다."
   - `reserved` 가 있으면: 예약 있는 날의 칸도 바뀌었고, 이미 받은 예약의 금액은 바뀌지 않는다.
   - `new` 가 있으면: 새로 생긴 칸은 저장해 둔 상태로 되돌려도 지울 수 없다(ERP 에 칸을 지우는 길이 없다).
   - 모두 0 이면: "저장해 둔 때와 모든 칸이 같습니다." 하고 끝낸다.
5. **되돌리기(원할 때만).** "S번 상태로 되돌려"면 SKILL.md 「4. 되돌리기」의 저장해 둔 상태로 되돌리기다. 1 의 읽기는 2 의 `<R>/snapshot.json` 을 그대로 쓰고 그 2 부터 한다: `restore --saved S --snapshot "<R>/snapshot.json" --record --sentence "<담당자 말>" --out "<작업>/rollback-1.json"`. 바뀐 칸이 모두 한 변경의 것이면 그 변경만 되돌리는 길(「4」의 `rollback`)도 있다고 말하고 고르게 한다.
