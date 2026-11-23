"""장부가 말하는 살아 있는 값 — 칸(항목 하나의 필드 하나)마다 ERP 가 지금 어느 기록이 넣은 값을 갖고 있는지(장부가 아는 만큼),
그리고 기록마다 그 칸에서 그 값이 살아 있는지 · 어느 기록이 되돌렸는지 · 되돌렸다가 다시 살렸는지. 장부는 표지를 달거나 풀지
않는다 — 저장된 값들을 저장한 차례로 따라가며 그때마다 셈한다(walk). 목록 · 되돌리기 · 결과 페이지 · 견주기가 모두 이 셈을
읽는다(ledger).

칸마다 따라가며 쥐는 것은 셋이다 — 장부가 아는 그 칸의 값(마지막으로 넣은 값), 그 값이 누구의 것인지(살아 있는 기록들 — 둘
이상일 수 있다: 되돌리기를 되돌리면 처음 넣은 기록과 그것을 다시 살린 되돌리기가 같은 값을 갖는다), 기록마다 그 칸에 넣을 때
덮은 기록들.

저장된 값 하나(기록 W 가 넣음)마다:

1. W 가 읽은 그 칸의 전 값이 장부가 아는 값과 다르면(없던 항목이었으면 다른 것이다) 그 사이 도우미 밖에서 바뀐 것이다 — 살아
   있던 기록들은 그 앞에 이미 밖에서 덮였고, W 가 덮은 기록은 없다.
2. W 가 되돌리기이고 그것이 되돌리는 기록 R 이 그 칸에 살아 있으면 — R 이 그 칸에 넣을 때 덮은 기록들이 다시 살고 W 도 산다.
3. W 가 저장 상태로 되돌리기이면 — 그 저장 상태를 적을 때 그 칸에 살아 있던 기록들이(그 저장 값이 W 가 넣은 값과 같으면) 다시
   살고 W 도 산다.
4. 그 밖(바꾸기, 되돌리는 기록이 그 칸에 살아 있지 않은 되돌리기 — 「그 사이 달라진 칸도 포함해서 되돌려」)이면 W 만 산다.
5. 2 · 3 이면 덮인 기록은 모두 W 가 되돌린 것이다. 4 면 덮였을 뿐이다(목록이 되돌림으로 세지 않는다) — 다만 되돌리기면 그것이
   되돌리는 기록은 그 칸에서 W 가 되돌린 것이다.
6. 되돌린 기록이 2 · 3 으로 다시 살면 「되돌렸다가 다시 살림」이다 — 그때 되돌린 기록과 다시 살린 기록을 단다.

지금 상태 저장은 적은 차례에서 그 칸에 살아 있던 기록들을 적어 둔다(3 이 쓴다) — 저장 값이 장부가 아는 값과 다르면 없다.

차례는 저장한 시각 · 기록 번호 · 단계 순이고, 지금 상태 저장은 적은 시각이다. 장부의 시각은 초까지라 같은 초의 두 기록은 번호
순으로 본다. 도우미 밖의 변화는 그 칸을 다시 넣을 때(1)에야 안다 — 그 전에는 장부의 셈이 밖에서 바뀐 칸을 아직 그 기록의 것으로
본다(되돌리기 계산은 읽은 값으로 그런 칸을 가려 그대로 둔다).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Mapping

Cell = tuple[str, str, str, str, str]   # (호텔 번호, 오퍼, 항목 종류, 항목 키, 필드)
Order = tuple[datetime, int, int]       # (저장한 · 적은 시각, 기록 번호, 단계 — 지금 상태 저장은 0)


@dataclass(frozen=True)
class Write:
    """저장된 값 하나 — 기록 `record` 가 `cell` 에 넣은 `after`(비움은 None). `before` 는 그 기록이 읽은 전 값, `missing` 은 그때
    그 항목이 없었다는 것. `undoes` 는 되돌리기면 되돌리는 기록, `restores` 는 저장 상태로 되돌리기면 그 저장 번호."""
    order: Order
    record: int
    cell: Cell
    before: Decimal | None
    missing: bool
    after: Decimal | None
    undoes: int | None = None
    restores: int | None = None


@dataclass(frozen=True)
class Saved:
    """지금 상태 저장 하나가 적은 칸 값."""
    order: Order
    record: int
    cell: Cell
    value: Decimal | None
    missing: bool


@dataclass(frozen=True)
class Status:
    """기록 하나가 넣은 칸 하나의 지금 — `live` 그 값이 살아 있다 · `undone_by` 살아 있지 않고 그 기록이 되돌렸다(아니면 덮였을
    뿐 — 뒤 기록이나 도우미 밖) · `redone` 살아 있고, 되돌렸다가 다시 살렸다(되돌린 기록, 다시 살린 기록)."""
    live: bool
    undone_by: int | None = None
    redone: tuple[int, int] | None = None


@dataclass(frozen=True)
class Alive:
    """`status` (기록, 칸) → Status, 그 기록이 저장한 칸만. `alive` 칸 → 지금 살아 있는 기록들, `holder` 칸 → 마지막으로 넣은 기록.
    `held` (지금 상태 저장, 칸) → 그 저장을 적을 때 그 칸에 마지막으로 넣은 기록(저장 값이 장부가 아는 값과 같을 때만)."""
    status: Mapping[tuple[int, Cell], Status]
    alive: Mapping[Cell, frozenset[int]]
    holder: Mapping[Cell, int]
    held: Mapping[tuple[int, Cell], int]
    cells: Mapping[int, tuple[Cell, ...]] = field(default_factory=dict)

    def of(self, record: int) -> dict[tuple[str, str], dict[str, Status]]:
        """그 기록이 저장한 칸을 항목마다 — (종류, 키) → 필드 → Status."""
        found: dict[tuple[str, str], dict[str, Status]] = {}
        for cell in self.cells.get(record, ()):
            found.setdefault((cell[2], cell[3]), {})[cell[4]] = self.status[(record, cell)]
        return found


def walk(writes: Iterable[Write], saved: Iterable[Saved] = ()) -> Alive:
    """저장된 값들과 지금 상태 저장들을 차례로 따라가 칸마다 · 기록마다 지금을 셈한다(모듈 머리글의 1~6)."""
    events = sorted([*((item.order, item) for item in writes), *((item.order, item) for item in saved)], key=lambda pair: pair[0])
    value: dict[Cell, Decimal | None] = {}
    alive: dict[Cell, frozenset[int]] = {}
    holder: dict[Cell, int] = {}
    replaced: dict[tuple[int, Cell], frozenset[int]] = {}
    status: dict[tuple[int, Cell], Status] = {}
    at_saved: dict[tuple[int, Cell], tuple[Decimal | None, frozenset[int]]] = {}
    held: dict[tuple[int, Cell], int] = {}
    cells: dict[int, list[Cell]] = {}
    for _order, item in events:
        cell = item.cell
        if isinstance(item, Saved):
            if cell in value and not item.missing and item.value == value[cell]:
                at_saved[(item.record, cell)] = (item.value, alive[cell])
                held[(item.record, cell)] = holder[cell]
            continue
        before = alive.get(cell, frozenset())
        if cell in value and (item.missing or item.before != value[cell]):   # 1 — 그 사이 도우미 밖에서 바뀜
            for record in before:
                status[(record, cell)] = Status(False)
            before = frozenset()
        replaced[(item.record, cell)] = before
        undo = True
        if item.undoes is not None and item.undoes in before:                   # 2
            now = {item.record} | replaced[(item.undoes, cell)]
        elif item.restores is not None:                                         # 3
            then = at_saved.get((item.restores, cell))
            now = {item.record} | (then[1] if then is not None and then[0] == item.after else frozenset())
        else:                                                                   # 4
            now, undo = {item.record}, False
            if item.undoes is not None and (item.undoes, cell) in status:
                status[(item.undoes, cell)] = Status(False, undone_by=item.record)
        for record in before - now:                                             # 5
            status[(record, cell)] = Status(False, undone_by=item.record if undo else None)
        for record in now - before - {item.record}:                             # 6
            was = status.get((record, cell))
            status[(record, cell)] = Status(True, redone=(was.undone_by, item.record) if was and was.undone_by else None)
        status[(item.record, cell)] = Status(True)
        value[cell], alive[cell], holder[cell] = item.after, frozenset(now), item.record
        cells.setdefault(item.record, []).append(cell)
    return Alive(status, alive, holder, held, {record: tuple(found) for record, found in cells.items()})
