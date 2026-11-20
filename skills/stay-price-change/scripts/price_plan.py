"""price_plan.py — 미리보기 계산, 빨간 줄 고르기, 저장 단계 나누기, 낡음 확인, 되돌리기 계산.

브라우저·파일·장부를 모르는 순수 함수만 둔다. 입력과 출력은 `price_model` 의 값 모양이다.

    plan_change(snapshot, request)        → Plan        칸마다 전 → 후, 표시, 판정
    resolve(plan, resolutions)            → (writes, unresolved)   빨간 줄을 고른 뒤 넣을 값
    save_steps(writes)                    → SaveStep…   객실 × 요금제 × 이어진 날짜(줄마다 같은 값)
    stale_cells(then, now)                → Difference… 미리보기 뒤 달라진 칸
    plan_rollback(recorded, later, now)   → RollbackPlan
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Iterable, Mapping, Sequence

from price_model import (
    BLOCKED, CLOSED, MISSING, RED, RESERVED, RULE_BY_CODE, RULES, CellChange, CellKey, CellValue, CellWrite,
    ChangeRequest, Cause, KeptCell, LaterWrite, Plan, RecordedChange, Resolution, RollbackPlan, RowWrite, SaveStep,
    Snapshot, occupancy_order, round_money, split_occupancy, verdict_of,
)


class PlanError(ValueError):
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
    """`(새 판매가, 없는 칸)` — 계산에 필요한 칸이 없으면 새 판매가 대신 그 칸 이름("adult"·"base")."""
    currency = snapshot.currency

    def sell_of(occupancy: str):
        return snapshot.cells.get(replace(key, occupancy=occupancy), MISSING).sell

    if request.operation == "amount":
        return round_money(before.sell + request.value, currency), None
    if request.operation == "set":
        base = sell_of(request.base_occupancy)
        if base is None:
            return None, "base"
        return round_money(request.value, currency) + (before.sell - base), None
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
            skipped.append(key)
            continue
        sell, lacking = _after_sell(snapshot, request, key, before)
        after = None if sell is None else replace(before, sell=sell)
        changes.append(CellChange(key, before, after, _marks(snapshot, key, before), verdict_of(before, after, lacking)))
    return Plan(request, snapshot.currency, snapshot.read_at, tuple(changes), tuple(skipped))


def counts(changes: Sequence[CellChange], skipped: int = 0) -> dict:
    """미리보기 머리 숫자. `cells` 는 가격이 있어 계산한 칸, `will_change` 는 그중 적용할 수 없는 칸을 뺀 수."""
    tally = dict(cells=len(changes), will_change=0, blocked=0, red=0, reserved=0, closed=0, skipped=skipped)
    tally.update({rule.code: 0 for rule in RULES})
    for change in changes:
        rule = RULE_BY_CODE.get(change.verdict)
        tally["blocked" if rule and rule.severity == BLOCKED else "will_change"] += 1
        tally["red"] += bool(rule and rule.severity == RED)
        if rule:
            tally[rule.code] += 1
        for mark in change.marks:
            tally[mark] += 1
    return tally


def resolve(plan: Plan, resolutions: Iterable[Resolution]) -> tuple[tuple[CellWrite, ...], tuple[CellChange, ...]]:
    """`(넣을 값, 아직 고르지 않은 빨간 줄 칸)`. 칸을 짚은 고름이 규칙 전체 고름보다 앞선다."""
    flagged = {change.key: change for change in plan.changes if change.verdict}
    by_rule, by_cell = {}, {}
    for resolution in resolutions:
        if resolution.cells is None:
            by_rule[resolution.rule] = resolution.choice
            continue
        for key in resolution.cells:
            if getattr(flagged.get(key), "verdict", None) != resolution.rule:
                raise PlanError(f"{RULE_BY_CODE[resolution.rule].label} 칸이 아닙니다: "
                                f"{key.room} · {key.rate_plan} · {key.date} · {key.occupancy or '인원 무관'} · {key.nights}박")
            by_cell[key] = resolution.choice
    writes, unresolved = [], []
    for change in plan.changes:
        rule = RULE_BY_CODE.get(change.verdict)
        if rule is not None and rule.severity == BLOCKED:
            continue
        choice = None if rule is None else by_cell.get(change.key, by_rule.get(rule.code))
        if rule is not None and choice is None:
            unresolved.append(change)
            continue
        if choice == "keep":
            continue
        raised = change.before.list_price + (change.after.sell - change.before.sell) if choice == "raise_list" else None
        writes.append(CellWrite(change.key, change.after.sell, raised))
    return tuple(writes), tuple(unresolved)


def _next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def save_steps(writes: Iterable[CellWrite]) -> tuple[SaveStep, ...]:
    """저장 한 번에 들어가는 날짜는 서로 이어지고, 그 날들에 쓰는 줄과 값이 모두 같다(값을 넣지 않는 줄도 같아야 한다)."""
    grid: dict[tuple[str, str], dict[str, set[RowWrite]]] = {}
    for write in writes:
        rows = grid.setdefault((write.key.room, write.key.rate_plan), {}).setdefault(write.key.date, set())
        row = RowWrite(write.key.occupancy, write.key.nights, write.sell, write.list_price)
        if any((other.occupancy, other.nights) == (row.occupancy, row.nights) for other in rows):
            raise PlanError(f"같은 칸에 넣을 값이 둘입니다: {write.key}")
        rows.add(row)
    steps = []
    for (room, plan), by_day in grid.items():
        runs: list[list[str]] = []
        for day in sorted(by_day):
            if runs and _next_day(runs[-1][-1]) == day and by_day[day] == by_day[runs[-1][-1]]:
                runs[-1].append(day)
            else:
                runs.append([day])
        steps += [SaveStep(room, plan, tuple(run), tuple(sorted(by_day[run[0]], key=lambda r: (
            occupancy_order(r.occupancy), r.nights)))) for run in runs]
    return tuple(steps)


@dataclass(frozen=True)
class Difference:
    key: CellKey
    then: CellValue | None
    now: CellValue | None


def stale_cells(then: Snapshot, now: Snapshot) -> tuple[Difference, ...]:
    """미리보기 때 읽은 값과 방금 읽은 값이 다른 칸 전부. 한쪽에만 있는 칸도 다른 칸이다."""
    return tuple(Difference(key, then.cells.get(key), now.cells.get(key))
                 for key in sorted(set(then.cells) | set(now.cells)) if then.cells.get(key) != now.cells.get(key))


def _holds(value: CellValue, write: CellWrite) -> bool:
    return value.sell == write.sell and (write.list_price is None or value.list_price == write.list_price)


def plan_rollback(recorded: RecordedChange, later: Mapping[CellKey, Sequence[LaterWrite]], now: Snapshot,
                  include_kept: bool = False) -> RollbackPlan:
    """지금 값이 그때 넣은 값과 같은 칸만 적어 둔 값으로 돌린다. 다른 칸은 세 값과 까닭을 달아 그대로 둔다.

    까닭은 이 장부의 나중 변경 가운데 지금 값을 넣은 가장 최근 것, 없으면 도우미 밖이다. `include_kept` 면 그 칸도 돌린다.
    """
    if not recorded.cells:
        raise PlanError("이 변경으로 실제로 저장된 칸이 없어 되돌릴 것이 없습니다")
    if (now.hotel, now.offer) != (recorded.hotel, recorded.offer):
        raise PlanError(f"지금 읽은 값은 {now.hotel} · {now.offer} 것이고, 되돌릴 변경은 {recorded.hotel} · {recorded.offer} 입니다")
    gaps = sorted({f"{c.key.room} · {c.key.rate_plan} · {c.key.date}" for c in recorded.cells
                   if not now.covers(c.key.room, c.key.rate_plan, c.key.date)})
    if gaps:
        raise PlanError(f"지금 값을 읽지 않은 날짜: {', '.join(gaps[:5])}{' …' if len(gaps) > 5 else ''}")
    restored, kept = [], []
    for cell in recorded.cells:
        current = now.cells.get(cell.key, MISSING)
        target = CellValue(cell.before.sell,
                           cell.before.list_price if cell.written.list_price is not None else current.list_price,
                           current.supply_cost, cell.before.state if current.state == "missing" else current.state)
        change = CellChange(cell.key, current, target, _marks(now, cell.key, current), None)
        if _holds(current, cell.written):
            restored.append(change)
            continue
        cause = next((Cause(w.change_id, w.at, w.sentence) for w in reversed(later.get(cell.key, ()))
                      if _holds(current, w.write)), Cause())
        kept.append(KeptCell(cell.key, cell.before, cell.written, current, cause))
        if include_kept:
            restored.append(change)
    return RollbackPlan(recorded.id, recorded.hotel, recorded.offer, recorded.currency, recorded.read_at,
                        recorded.sentence, recorded.applied_at, tuple(restored), tuple(kept), include_kept, now.read_at)


def rollback_writes(plan: RollbackPlan) -> tuple[CellWrite, ...]:
    """돌릴 칸마다 적어 둔 판매가를, 그때 정가를 바꿨던 칸은 적어 둔 정가도 넣는다."""
    return tuple(CellWrite(c.key, c.after.sell, c.after.list_price if c.after.list_price != c.before.list_price else None)
                 for c in plan.restored)
