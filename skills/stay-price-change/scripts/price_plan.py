"""price_plan.py — 가격 칸 계산: 미리보기, 빨간 줄 고르기, 저장 단계 나누기, 그리고 공통 장부·낡음 확인·되돌리기와 잇기.

브라우저·파일을 모르는 순수 함수만 둔다.

    plan_change(snapshot, request)      → Plan          칸마다 전 → 후, 표시, 판정
    resolve(plan, resolutions)          → (writes, unresolved)   빨간 줄을 고른 뒤 넣을 값
    save_steps(writes)                  → 저장 단계들   객실 × 요금제 × 이어진 날짜(줄마다 같은 값)
    stale_cells(then, now)              → 다른 항목들   (change_core.items.stale_items)
    plan_cell_rollback(recorded, …)     → RollbackPlan (change_core.rollback.plan_rollback)
    preview_rows · snapshot_rows · rollback_rows · step_plans   장부(change_core.ledger)에 넘길 공통 모양
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Callable, Iterable, Mapping, Sequence

from change_core.items import Difference, Refused, stale_items
from change_core.ledger import FieldWrite, StepPlan, ValueRow
from change_core.money import round_money
from change_core.rollback import LaterWrite, RecordedChange, RollbackPlan, plan_rollback
from change_core.rules import BLOCKED, RED, Resolution, decide

from price_model import (
    CELL_RULES, CLOSED, FIELDS, ITEM_KIND, MISSING, RESERVED, BulkStep, CellChange, CellKey, CellValue, CellWrite,
    ChangeRequest, Plan, RowWrite, Skipped, Snapshot, cell_item_key, cell_name, cell_state, day_label, encode_step,
    key_of_item, occupancy_order, snapshot_reading, split_occupancy,
)


class PlanError(Refused):
    """요청과 읽은 값이 맞지 않아 계산할 수 없다 — 문장은 담당자에게 그대로 보여 줄 수 있다."""


def _marks(snapshot: Snapshot, key: CellKey, value: CellValue) -> tuple[str, ...]:
    return tuple(mark for mark, on in ((RESERVED, (key.room, key.date) in snapshot.reserved),
                                       (CLOSED, value.state == "closed")) if on)


def _check_scope(snapshot: Snapshot, request: ChangeRequest, keys: list[CellKey]) -> None:
    if (snapshot.hotel, snapshot.offer) != (request.hotel, request.offer):
        raise PlanError(f"읽은 값은 {snapshot.hotel} · {snapshot.offer} 것이고, 요청은 {request.hotel} · {request.offer} 입니다")
    pairs = {(key.room, key.rate_plan) for key in keys}
    absent = [room for room in request.rooms if all(room != pair[0] for pair in pairs)]
    absent += [plan for plan in request.rate_plans if all(plan != pair[1] for pair in pairs)]
    if absent:
        raise PlanError(f"읽은 값에 없는 객실·요금제: {' · '.join(absent)}")
    gaps = [f"{room} · {plan} · {day}" for room, plan in sorted(pairs) for day in request.dates
            if not snapshot.covers(room, plan, day)]
    if gaps:
        raise PlanError(f"읽은 값에 없는 날짜: {', '.join(gaps[:5])}{' …' if len(gaps) > 5 else ''}")


def _after_sell(snapshot: Snapshot, request: ChangeRequest, key: CellKey, before: CellValue):
    """`(새 판매가, 없는 칸)` — 계산에 필요한 성인만 있는 칸이 없으면 새 판매가 대신 "adult".

    새 값 지정(set)은 그날 기준 인원 1박 칸이 그 값이 되는 만큼(차이)을 그 객실·요금제·날짜의 모든 인원·박수 칸에 더한다.
    박수 층의 할인 차이가 그대로 남는다. 기준 1박 칸이 없는 날은 `plan_change` 가 미리 건너뛴다.
    """
    currency = snapshot.currency

    def sell_of(occupancy: str, nights: int | None = None):
        return snapshot.cells.get(replace(key, occupancy=occupancy, nights=nights or key.nights), MISSING).sell

    if request.operation == "amount":
        return round_money(before.sell + request.value, currency), None
    if request.operation == "set":
        return before.sell + (round_money(request.value, currency) - sell_of(request.base_occupancy, 1)), None
    factor = (100 + request.value) / 100
    adult_key, has_children = (key.occupancy, False) if request.scale_child_surcharge else split_occupancy(key.occupancy)
    if has_children is None:
        return None, "adult"
    if not has_children:
        return round_money(before.sell * factor, currency), None
    adult = sell_of(adult_key)
    if adult is None:
        return None, "adult"
    return round_money(adult * factor, currency) + (before.sell - adult), None


def plan_change(snapshot: Snapshot, request: ChangeRequest) -> Plan:
    rooms = {room: rank for rank, room in enumerate(request.rooms)}
    plans = {plan: rank for rank, plan in enumerate(request.rate_plans)}
    dates = set(request.dates)
    keys = [key for key in snapshot.cells if key.room in rooms and key.rate_plan in plans and key.date in dates]
    _check_scope(snapshot, request, keys)
    keys.sort(key=lambda k: (rooms[k.room], plans[k.rate_plan], occupancy_order(k.occupancy), k.nights, k.date))
    changes, skipped = [], []
    for key in keys:
        before = snapshot.cells[key]
        if before.state == "missing":
            skipped.append(Skipped(key, "no_price"))
            continue
        if request.operation == "set" and snapshot.cells.get(
                replace(key, occupancy=request.base_occupancy, nights=1), MISSING).sell is None:
            skipped.append(Skipped(key, "no_base"))
            continue
        sell, lacking = _after_sell(snapshot, request, key, before)
        after = None if sell is None else replace(before, sell=sell)
        changes.append(CellChange(key, before, after, _marks(snapshot, key, before),
                                  CELL_RULES.verdict(before, after, lacking)))
    return Plan(request, snapshot.currency, snapshot.read_at, tuple(changes), tuple(skipped))


def counts(changes: Sequence[CellChange], skipped: int = 0) -> dict:
    """미리보기 머리 숫자. `cells` 는 가격이 있어 계산한 칸, `will_change` 는 그중 적용할 수 없는 칸을 뺀 수."""
    tally = dict(cells=len(changes), will_change=0, blocked=0, red=0, reserved=0, closed=0, skipped=skipped)
    tally.update({rule.code: 0 for rule in CELL_RULES.rules})
    for change in changes:
        severity = CELL_RULES.severity(change.verdict)
        tally["blocked" if severity == BLOCKED else "will_change"] += 1
        tally["red"] += severity == RED
        if change.verdict:
            tally[change.verdict] += 1
        for mark in change.marks:
            tally[mark] += 1
    return tally


def resolve(plan: Plan, resolutions: Iterable[Resolution]) -> tuple[tuple[CellWrite, ...], tuple[CellChange, ...]]:
    """`(넣을 값, 아직 고르지 않은 빨간 줄 칸)`. 칸을 짚은 고름이 규칙 전체 고름보다 앞선다."""
    flagged = {change.key: change.verdict for change in plan.changes if change.verdict}
    chosen, waiting = decide(CELL_RULES, flagged, resolutions, cell_name)
    by_key = {change.key: change for change in plan.changes}
    writes = []
    for change in plan.changes:
        if CELL_RULES.severity(change.verdict) == BLOCKED or change.key in waiting:
            continue
        choice = chosen.get(change.key, "include")
        if choice == "keep":
            continue
        fields = {name: getattr(change.after, name) for name in change.changed}
        if choice == "raise_list":
            fields["list"] = change.before.list + (change.after.sell - change.before.sell)
        writes.append(CellWrite(change.key, **fields))
    return tuple(writes), tuple(by_key[key] for key in waiting)


def _next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def save_steps(writes: Iterable[CellWrite]) -> tuple[BulkStep, ...]:
    """저장 한 번에 들어가는 날짜는 서로 이어지고, 그 날들에 쓰는 줄과 값이 모두 같다(값을 넣지 않는 줄도 같아야 한다)."""
    grid: dict[tuple[str, str], dict[str, set[RowWrite]]] = {}
    for write in writes:
        rows = grid.setdefault((write.key.room, write.key.rate_plan), {}).setdefault(write.key.date, set())
        row = RowWrite(write.key.occupancy, write.key.nights, write.sell, write.list, write.supply)
        if any((other.occupancy, other.nights) == (row.occupancy, row.nights) for other in rows):
            raise PlanError(f"같은 칸에 넣을 값이 둘입니다: {cell_name(write.key)}")
        rows.add(row)
    steps = []
    for (room, plan), by_day in grid.items():
        runs: list[list[str]] = []
        for day in sorted(by_day):
            if runs and _next_day(runs[-1][-1]) == day and by_day[day] == by_day[runs[-1][-1]]:
                runs[-1].append(day)
            else:
                runs.append([day])
        steps += [BulkStep(room, plan, tuple(run), tuple(sorted(by_day[run[0]], key=lambda r: (
            occupancy_order(r.occupancy), r.nights)))) for run in runs]
    return tuple(steps)


def days_summary(days: Iterable[str]) -> str:
    days = sorted(days)
    runs: list[list[str]] = []
    for day in days:
        if runs and _next_day(runs[-1][-1]) == day:
            runs[-1].append(day)
        else:
            runs.append([day])
    parts = [day_label(run[0]) if len(run) == 1 else f"{day_label(run[0])} ~ {day_label(run[-1])}" for run in runs]
    if len(parts) > 8:
        parts = parts[:8] + ["…"]
    years = sorted({day[:4] for day in days})
    return f"{' · '.join(parts)} ({len(days)}일{', ' + '·'.join(years) + '년' if years else ''})"


def step_label(step: BulkStep) -> str:
    return f"{step.room} · {step.rate_plan} · {days_summary(step.dates)}"


def step_plans(steps: Iterable[BulkStep]) -> list[StepPlan]:
    """저장 단계 → 장부가 받는 공통 모양(단계가 쓰는 (항목, 필드) → 값)."""
    plans = []
    for step in steps:
        writes = tuple(FieldWrite(ITEM_KIND, cell_item_key(CellKey(step.room, step.rate_plan, day, row.occupancy,
                                                                    row.nights)), name, getattr(row, name))
                       for day in step.dates for row in step.rows for name in FIELDS if getattr(row, name) is not None)
        plans.append(StepPlan(step.kind, step_label(step), encode_step(step), writes))
    return plans


def _rows(key: CellKey, before: CellValue, after: CellValue | None, verdict=None, marks=()) -> list[ValueRow]:
    return [ValueRow(ITEM_KIND, cell_item_key(key), cell_name(key), name, before.state, getattr(before, name),
                     getattr(after, name) if after is not None and getattr(after, name) != getattr(before, name) else None,
                     verdict, marks) for name in FIELDS]


def preview_rows(plan: Plan) -> list[ValueRow]:
    return [row for change in plan.changes for row in _rows(change.key, change.before, change.after, change.verdict,
                                                             change.marks)]


def snapshot_rows(snapshot: Snapshot) -> list[ValueRow]:
    return [row for key, value in sorted(snapshot.cells.items())
            for row in _rows(key, value, None, marks=(RESERVED,) if (key.room, key.date) in snapshot.reserved else ())]


def stale_cells(then: Snapshot, now: Snapshot) -> tuple[Difference, ...]:
    """미리보기 때 읽은 값과 방금 읽은 값이 다른 칸 전부. 한쪽에만 있는 칸도 다른 칸이다."""
    return stale_items(snapshot_reading(then), snapshot_reading(now))


def plan_cell_rollback(recorded: RecordedChange, later: Mapping[tuple[str, str], Sequence[LaterWrite]], now: Snapshot,
                       include_kept: bool = False, select: Callable[[CellKey], bool] | None = None) -> RollbackPlan:
    """가격 칸 되돌리기 — 지금 값을 읽은 날짜인지 보고, 공통 되돌리기 계산에 넘긴다. `select` 는 칸을 고르는 조건."""
    if (now.hotel, now.offer) != (recorded.hotel, recorded.offer):
        raise PlanError(f"지금 읽은 값은 {now.hotel} · {now.offer} 것이고, 되돌릴 변경은 {recorded.hotel} · {recorded.offer} 입니다")
    chosen = [item for item in recorded.items if item.kind == ITEM_KIND and (select is None or select(key_of_item(item.key)))]
    gaps = sorted({f"{key.room} · {key.rate_plan} · {key.date}" for key in map(key_of_item, (i.key for i in chosen))
                   if not now.covers(key.room, key.rate_plan, key.date)})
    if gaps:
        raise PlanError(f"지금 값을 읽지 않은 날짜: {', '.join(gaps[:5])}{' …' if len(gaps) > 5 else ''}")
    return plan_rollback(recorded, later, snapshot_reading(now), now.read_at, include_kept,
                         None if select is None else lambda kind, key: kind == ITEM_KIND and select(key_of_item(key)))


def rollback_writes(plan: RollbackPlan) -> tuple[CellWrite, ...]:
    """돌릴 칸마다 그 변경이 썼던 필드에 적어 둔 값을 넣는다(적어 둔 값이 없던 필드는 비운다)."""
    writes = []
    for item in plan.restored:
        targets = dict(item.targets)
        writes.append(CellWrite(key_of_item(item.key), **{name: value for name, value in targets.items() if value is not None},
                                clear=tuple(name for name in FIELDS if name in targets and targets[name] is None)))
    return tuple(writes)


def rollback_rows(plan: RollbackPlan) -> list[ValueRow]:
    rows = []
    for item in plan.restored:
        key = key_of_item(item.key)
        now = item.now if item.now.fields else cell_state(key, MISSING)
        for name in FIELDS:
            target = item.targets.get(name, now.fields.get(name))
            rows.append(ValueRow(ITEM_KIND, item.key, item.label, name, now.state, now.fields.get(name),
                                 target if target != now.fields.get(name) else None))
    return rows
