"""price_plan.py — 가격 칸 계산: 미리보기, 빨간 줄 고르기, 저장 단계 나누기, 그리고 공통 장부·낡음 확인·되돌리기와 잇기.

브라우저·파일을 모르는 순수 함수만 둔다.

    plan_change(snapshot, request)      → Plan          칸마다 전 → 후, 표시, 판정
    plan_targets(snapshot, table)       → Plan          목표 값 표 — 다른 칸만, 새로 생기는 칸 포함. 인원·박수가 없는 줄은 하나뿐인 줄로
    resolve(plan, resolutions)          → (writes, unresolved)   빨간 줄을 고른 뒤 넣을 값
    save_steps(writes)                  → 저장 단계들   객실 × 요금제 × 줄과 값이 같은 날들(떨어져 있어도 한 번, 550일까지)
    stale_cells(then, now)              → 다른 항목들   (change_core.items.stale_items)
    plan_cell_rollback(recorded, …)     → RollbackPlan (change_core.rollback.plan_rollback) — cell_filter 로 일부만
    preview_rows · snapshot_rows · rollback_rows · step_plans   장부(change_core.ledger)에 넘길 공통 모양
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Iterable, Mapping, Sequence

from change_core.items import Difference, Refused, stale_items
from change_core.ledger import FieldWrite, StepPlan, ValueRow
from change_core.money import round_money
from change_core.rollback import LaterWrite, RecordedChange, RollbackPlan, plan_restore, plan_rollback
from change_core.rules import BLOCKED, RED, Resolution, decide

from price_model import (
    CELL_RULES, CLOSED, ERP_MAX_DAYS, FIELD_LABELS, FIELDS, ITEM_KIND, MISSING, NEW, RESERVED, BulkStep, CellChange, CellEditStep, CellKey,
    CellValue, CellWrite, ChangeRequest, Plan, RowWrite, Skipped, Snapshot, TargetTable, cell_item_key, cell_name,
    cell_state, day_label, day_windows, encode_step, hotel_label, key_of_item, line_label, occupancy_label, occupancy_order, same_hotel,
    snapshot_reading, split_occupancy, value_of,
)


class PlanError(Refused):
    """요청과 읽은 값이 맞지 않아 계산할 수 없다 — 문장은 담당자에게 그대로 보여 줄 수 있다."""


def _marks(snapshot: Snapshot, key: CellKey, value: CellValue) -> tuple[str, ...]:
    return tuple(mark for mark, on in ((RESERVED, (key.room, key.date) in snapshot.reserved),
                                       (CLOSED, value.state == "closed"), (NEW, value.state == "missing")) if on)


def _check_scope(snapshot: Snapshot, request: ChangeRequest | TargetTable, pairs: Iterable[tuple[str, str]],
                 days: Iterable[tuple[str, str, str]]) -> tuple[tuple[str, str], ...]:
    """요청과 읽은 값이 같은 호텔(번호) · 같은 오퍼인지, 요청한 (객실, 요금제) 가 모두 읽혔는지, 칸이 있는 쌍은 요청한 날이 모두
    읽혔는지 본다 — 하나라도 아니면 이름을 대고 멈춘다.

    읽었지만 칸이 하나도 없는 쌍은 멈추지 않고 돌려준다(건너뜀으로 알린다).
    """
    if not same_hotel(snapshot.hotel, snapshot.hotel_id, request.hotel, request.hotel_id) or snapshot.offer != request.offer:
        raise PlanError(f"읽은 값은 {hotel_label(snapshot.hotel, snapshot.hotel_id)} · {snapshot.offer} 것이고, 요청은 "
                        f"{hotel_label(request.hotel, request.hotel_id)} · {request.offer} 입니다")
    pairs = list(dict.fromkeys(pairs))
    unread = [f"{room} · {plan}" for room, plan in pairs if (room, plan) not in snapshot.pairs]
    if unread:
        raise PlanError(f"읽지 않은 객실·요금제가 있습니다: {', '.join(unread)}. 그 객실·요금제의 가격을 먼저 읽어야 합니다")
    filled = {(key.room, key.rate_plan) for key in snapshot.cells}
    gaps = sorted({f"{room} · {plan} · {day}" for room, plan, day in days
                   if (room, plan) in filled and not snapshot.covers(room, plan, day) and (room, day) not in snapshot.no_sale})
    if gaps:
        raise PlanError(f"읽은 값에 없는 날짜: {', '.join(gaps[:5])}{' …' if len(gaps) > 5 else ''}")
    return tuple(pair for pair in pairs if pair not in filled)


def _after_value(snapshot: Snapshot, request: ChangeRequest, key: CellKey, before: CellValue):
    """`(바꾸는 값의 새 값, 없는 칸)` — 계산에 필요한 성인만 있는 칸(그 값)이 없으면 새 값 대신 "adult".

    새 값 지정(set)은 그날 기준 인원 1박 칸이 그 값이 되는 만큼(차이)을 그 객실·요금제·날짜의 모든 인원·박수 칸에 더한다.
    박수 층의 할인 차이가 그대로 남는다. 기준 1박 칸에 값이 없는 날은 "base"(적용할 수 없음)다. 퍼센트는 ERP 가감과 같이
    아동이 있는 칸이면 같은 성인 수의 성인만 있는 칸에만 곱하고 아동 추가분을 그대로 더한다(바꾸는 값마다 같은 규칙).
    """
    name, currency, current = request.field, snapshot.currency, getattr(before, request.field)

    def value_at(occupancy: str, nights: int | None = None):
        return getattr(snapshot.cells.get(replace(key, occupancy=occupancy, nights=nights or key.nights), MISSING), name)

    if request.operation == "amount":
        return round_money(current + request.value, currency), None
    if request.operation == "set":
        base = value_at(request.base_occupancy, 1)
        if base is None:
            return None, "base"
        return current + (round_money(request.value, currency) - base), None
    factor = (100 + request.value) / 100
    adult_key, has_children = (key.occupancy, False) if request.scale_child_surcharge else split_occupancy(key.occupancy)
    if has_children is None:
        return None, "adult"
    if not has_children:
        return round_money(current * factor, currency), None
    adult = value_at(adult_key)
    if adult is None:
        return None, "adult"
    return round_money(adult * factor, currency) + (current - adult), None


def _skip_reason(snapshot: Snapshot, request: ChangeRequest, key: CellKey, before: CellValue) -> str | None:
    if before.state == "missing":
        return "no_price"
    if getattr(before, request.field) is None:
        return f"no_{request.field}"
    return None


def requested_pairs(snapshot: Snapshot, request: ChangeRequest) -> tuple[tuple[tuple[str, str], ...],
                                                                         tuple[tuple[str, str], ...]]:
    """`(요청하는 쌍, 그 객실에 없어 뺀 조합)`.

    쌍을 짚은 요청은 그대로다(읽지 않은 쌍은 `_check_scope` 가 이름을 대고 멈춘다). 객실·요금제를 따로 받았으면 읽은 쌍만
    요청하고, 나머지 조합은 그 객실에 없는 요금제로 돌려준다. 단 적은 객실이 적은 요금제를 하나도 읽지 않았거나 적은 요금제를
    어느 적은 객실도 읽지 않았으면, 없는 것이 아니라 읽지 않은 것이라 이름을 대고 멈춘다.
    """
    if request.pairs:
        return request.pairs, ()
    combos = [(room, plan) for room in request.rooms for plan in request.rate_plans]
    read = [pair for pair in combos if pair in snapshot.pairs]
    rooms, plans = {room for room, _plan in read}, {plan for _room, plan in read}
    unread = [f"{room} · {plan}" for room, plan in combos if room not in rooms or plan not in plans]
    if unread:
        raise PlanError(f"읽지 않은 객실·요금제가 있습니다: {', '.join(unread)}. 그 객실·요금제의 가격을 먼저 읽어야 합니다")
    return tuple(read), tuple(pair for pair in combos if pair not in snapshot.pairs)


def _check_cells(request: ChangeRequest, keys: Iterable[CellKey]) -> None:
    """고른 인원 조합 · 박수 층이 범위 안에서 읽혔는지 — 없는 것을 고르면 아무 칸도 움직이지 않으니 이름을 대고 멈춘다."""
    keys = list(keys)
    seen_occupancies, seen_nights = {key.occupancy for key in keys}, {key.nights for key in keys}
    unknown = [occupancy_label(key) + (f"({key})" if key else "") for key in request.occupancies if key not in seen_occupancies]
    if unknown:
        raise PlanError(f"읽은 값에 없는 인원 조합: {', '.join(unknown)} (읽은 것: "
                        f"{' · '.join(f'{occupancy_label(key)}({key})' for key in sorted(seen_occupancies, key=occupancy_order))})")
    unknown_nights = [n for n in request.nights if n not in seen_nights]
    if unknown_nights:
        raise PlanError(f"읽은 값에 없는 박수 층: {', '.join(map(str, unknown_nights))} (읽은 것: {' · '.join(map(str, sorted(seen_nights)))})")


def plan_change(snapshot: Snapshot, request: ChangeRequest) -> Plan:
    """칸마다 전 → 후. `request.occupancies`·`nights` 를 적었으면 그 칸만 — 규칙 · 표시 · 저장 단계는 다른 변경과 같다."""
    pairs, absent = requested_pairs(snapshot, request)
    request = replace(request, pairs=pairs)
    rooms = {room: rank for rank, room in enumerate(request.rooms)}
    plans = {plan: rank for rank, plan in enumerate(request.rate_plans)}
    dates, wanted = set(request.dates), set(pairs)
    keys = [key for key in snapshot.cells if (key.room, key.rate_plan) in wanted and key.date in dates]
    empty = _check_scope(snapshot, request, pairs,
                         [(room, plan, day) for room, plan in pairs for day in request.dates])
    _check_cells(request, keys)
    keys = [key for key in keys if (not request.occupancies or key.occupancy in request.occupancies)
            and (not request.nights or key.nights in request.nights)]
    no_sale = tuple((room, plan, day) for room, plan in pairs for day in sorted(set(request.dates))
                    if (room, day) in snapshot.no_sale)
    empty = tuple(pair for pair in empty if not all((pair[0], day) in snapshot.no_sale for day in request.dates))
    keys.sort(key=lambda k: (rooms[k.room], plans[k.rate_plan], occupancy_order(k.occupancy), k.nights, k.date))
    changes, skipped = [], []
    for key in keys:
        before = snapshot.cells[key]
        reason = _skip_reason(snapshot, request, key, before)
        if reason:
            skipped.append(Skipped(key, reason))
            continue
        value, lacking = (None, None) if request.operation == "clear" else _after_value(snapshot, request, key, before)
        after = None if lacking else replace(before, **{request.field: value})
        if after == before:
            skipped.append(Skipped(key, "same"))
            continue
        changes.append(CellChange(key, before, after, _marks(snapshot, key, before),
                                  CELL_RULES.verdict(before, after, lacking)))
    return Plan(request, snapshot.currency, snapshot.read_at, tuple(changes), tuple(skipped), empty, absent, no_sale)


def fill_lines(snapshot: Snapshot, table: TargetTable) -> TargetTable:
    """인원 조합 · 박수를 적지 않은 목표 → 읽은 값에서 그 객실 · 요금제의 줄 가운데 적은 것과 맞는 줄이 꼭 하나면 그 줄.
    없거나 여럿이면 고를 수 있는 줄을 대며 거절한다(담당자의 표는 보통 객실 · 요금제 · 날짜 · 값만 적는다)."""
    lines: dict[tuple[str, str], set[tuple[str, int]]] = {}
    for key in snapshot.cells:
        lines.setdefault((key.room, key.rate_plan), set()).add((key.occupancy, key.nights))
    targets = []
    for target in table.targets:
        key = target.key
        if key.occupancy is not None and key.nights is not None:
            targets.append(target)
            continue
        seen = sorted(lines.get((key.room, key.rate_plan), ()), key=lambda line: (occupancy_order(line[0]), line[1]))
        fits = [line for line in seen if key.occupancy in (None, line[0]) and key.nights in (None, line[1])]
        if len(fits) != 1:
            shown = " / ".join(f"{line_label(*line)}({line[0] or '빈 키'} · {line[1]})" for line in (fits or seen)) or "없음"
            raise PlanError(f"{key.room} · {key.rate_plan} 의 {line_label(key.occupancy, key.nights)} 에 맞는 줄이 "
                            f"{'여럿' if fits else '없'}습니다 — 고를 줄: {shown}. 표의 줄마다 인원 조합(occupancy)과 박수(nights)를 적습니다")
        targets.append(replace(target, key=replace(key, occupancy=fits[0][0], nights=fits[0][1])))
    return replace(table, targets=tuple(targets))


def plan_targets(snapshot: Snapshot, table: TargetTable) -> Plan:
    """목표 값 표 → 미리보기. 지금 값과 다른 칸만 남긴다. 인원 조합 · 박수를 적지 않은 줄은 `fill_lines` 로 채운다(미리보기의
    요청은 채운 표다). 가격 없던 칸의 목표는 새로 생기는 칸이다 — 판매가가 있어야 하고, 읽은 값에서 그 객실·요금제에 보인 적
    없는 인원 조합·박수라면 만들지 않는다(적용할 수 없음)."""
    keys = [target.key for target in table.targets]
    _check_scope(snapshot, table, [(k.room, k.rate_plan) for k in keys],
                 [(k.room, k.rate_plan, k.date) for k in keys])
    table = fill_lines(snapshot, table)
    shown = {(key.room, key.rate_plan, key.occupancy, key.nights) for key in snapshot.cells}
    rooms = {room: rank for rank, room in enumerate(dict.fromkeys(t.key.room for t in table.targets))}
    plans = {plan: rank for rank, plan in enumerate(dict.fromkeys(t.key.rate_plan for t in table.targets))}
    changes, no_sale = [], {}
    for target in sorted(table.targets, key=lambda t: (rooms[t.key.room], plans[t.key.rate_plan],
                                                      occupancy_order(t.key.occupancy), t.key.nights, t.key.date)):
        key = target.key
        if (key.room, key.date) in snapshot.no_sale:
            no_sale[(key.room, key.rate_plan, key.date)] = None
            continue
        before = snapshot.cells.get(key, MISSING)
        wanted = {name: None if value is None else round_money(value, snapshot.currency) for name, value in target.values}
        merged = {name: wanted[name] if name in wanted else getattr(before, name) for name in FIELDS}
        lacking = None
        if before.state == "missing" and (key.room, key.rate_plan, key.occupancy, key.nights) not in shown:
            lacking = "row"
        elif before.state == "missing" and merged["sell"] is None:
            lacking = "sell"
        after = None if lacking else CellValue(merged["sell"], merged["list"], merged["supply"],
                                               "open" if before.state == "missing" else before.state)
        if after == before:
            continue
        changes.append(CellChange(key, before, after, _marks(snapshot, key, before), CELL_RULES.verdict(before, after, lacking)))
    return Plan(table, snapshot.currency, snapshot.read_at, tuple(changes), (), no_sale=tuple(sorted(no_sale)))


def counts(changes: Sequence[CellChange], skipped: int = 0) -> dict:
    """미리보기 머리 숫자. `cells` 는 계산한 칸, `will_change` 는 그중 적용할 수 없는 칸을 뺀 수, `new` 는 새로 생기는 칸."""
    tally = dict(cells=len(changes), will_change=0, blocked=0, red=0, reserved=0, closed=0, new=0, skipped=skipped)
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
    """`(넣을 값, 아직 고르지 않은 빨간 줄 칸)`. 칸을 짚은 고름이 규칙 전체 고름보다 앞선다.

    정가를 넘는 칸: raise_list 는 정가도 판매가와 같은 만큼 옮기고(정가 − 판매가 차이 유지), clear_list 는 정가를 비운다.
    """
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
            if change.before.list is None or change.before.sell is None:
                raise PlanError(f"정가를 같은 만큼 올릴 수 없는 칸입니다(전 정가가 없음): {cell_name(change.key)}")
            fields["list"] = change.after.sell + (change.before.list - change.before.sell)
        if choice == "clear_list":
            fields["list"] = None
        write = _write(change.key, change.before, fields)
        if write is not None:
            writes.append(write)
    return tuple(writes), tuple(by_key[key] for key in waiting)


def _write(key: CellKey, current: CellValue, fields: Mapping[str, Decimal | None]) -> CellWrite | None:
    """지금 값과 다른 필드만 넣는 값. 다른 필드가 없으면 None — 아무것도 바꾸지 않는 저장은 만들지 않는다."""
    fields = {name: value for name, value in fields.items() if getattr(current, name) != value}
    if not fields:
        return None
    return CellWrite(key, **{name: value for name, value in fields.items() if value is not None},
                     clear=tuple(name for name in FIELDS if name in fields and fields[name] is None))


def _next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def save_steps(writes: Iterable[CellWrite]) -> tuple[BulkStep | CellEditStep, ...]:
    """넣을 값 → 저장 단계. 새 값은 [선택 날짜 가격 수정] 묶음 저장, 비우기는 셀 창 저장(칸 하나씩)으로 간다.

    묶음 저장 한 번은 객실 · 요금제 하나에서 쓰는 줄과 값이 모두 같은 날들이다(값을 넣지 않는 줄도 같아야 한다). 날이 떨어져
    있어도 한 번이다 — 드로어가 날짜 구간 여럿을 한 번에 받는다("12월 금·토"는 쌍마다 한 번). 첫 날부터 끝 날까지가 ERP 가
    한 번에 받는 ERP_MAX_DAYS(550일)를 넘으면 거기서 나눈다. 객실·요금제마다 셀 창 저장을 묶음 저장보다 먼저 두고, 묶음 저장은
    첫 날 차례다 — 묶음 저장은 남은 정가보다 비싼 판매가를 거절한다.
    """
    grid: dict[tuple[str, str], dict[str, set[RowWrite]]] = {}
    edits: dict[tuple[str, str], list[CellEditStep]] = {}
    for write in writes:
        if not write.fields():
            continue
        pair = (write.key.room, write.key.rate_plan)
        if write.clear:
            edits.setdefault(pair, []).append(CellEditStep(write.key, write.clear))
            grid.setdefault(pair, {})
        if write.sell is None and write.list is None and write.supply is None:
            continue
        rows = grid.setdefault(pair, {}).setdefault(write.key.date, set())
        row = RowWrite(write.key.occupancy, write.key.nights, write.sell, write.list, write.supply)
        if any((other.occupancy, other.nights) == (row.occupancy, row.nights) for other in rows):
            raise PlanError(f"같은 칸에 넣을 값이 둘입니다: {cell_name(write.key)}")
        rows.add(row)
    steps: list[BulkStep | CellEditStep] = []
    for (room, plan), by_day in grid.items():
        steps += edits.get((room, plan), [])
        same: dict[frozenset[RowWrite], list[str]] = {}
        for day in sorted(by_day):
            same.setdefault(frozenset(by_day[day]), []).append(day)
        groups = sorted(((tuple(days), rows) for rows, group in same.items() for days in day_windows(group, ERP_MAX_DAYS)),
                        key=lambda item: item[0][0])
        steps += [BulkStep(room, plan, days, tuple(sorted(rows, key=lambda r: (occupancy_order(r.occupancy), r.nights))))
                  for days, rows in groups]
    return tuple(steps)


def day_runs(days: Iterable[str]) -> list[list[str]]:
    """날짜 → 이어진 날끼리 묶은 목록(날짜 차례)."""
    runs: list[list[str]] = []
    for day in sorted(days):
        if runs and _next_day(runs[-1][-1]) == day:
            runs[-1].append(day)
        else:
            runs.append([day])
    return runs


def days_summary(days: Iterable[str]) -> str:
    days = sorted(days)
    runs = day_runs(days)
    parts = [day_label(run[0]) if len(run) == 1 else f"{day_label(run[0])} ~ {day_label(run[-1])}" for run in runs]
    if len(parts) > 8:
        parts = parts[:8] + ["…"]
    years = sorted({day[:4] for day in days})
    return f"{' · '.join(parts)} ({len(days)}일{', ' + '·'.join(years) + '년' if years else ''})"


def step_label(step: BulkStep | CellEditStep) -> str:
    if step.kind == "cell_edit":
        return f"{cell_name(step.key)} · {' · '.join(FIELD_LABELS[name] for name in step.clear)} 지움 (셀 창)"
    return f"{step.room} · {step.rate_plan} · {days_summary(step.dates)}"


def step_writes(step: BulkStep | CellEditStep) -> tuple[FieldWrite, ...]:
    if step.kind == "cell_edit":
        return tuple(FieldWrite(ITEM_KIND, cell_item_key(step.key), name, None) for name in step.clear)
    return tuple(FieldWrite(ITEM_KIND, cell_item_key(CellKey(step.room, step.rate_plan, day, row.occupancy, row.nights)),
                            name, getattr(row, name))
                 for day in step.dates for row in step.rows for name in FIELDS if getattr(row, name) is not None)


def step_plans(steps: Iterable[BulkStep | CellEditStep]) -> list[StepPlan]:
    """저장 단계 → 장부가 받는 공통 모양(단계가 쓰는 (항목, 필드) → 값, 비우기는 None)."""
    return [StepPlan(step.kind, step_label(step), encode_step(step), step_writes(step)) for step in steps]


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


def cell_filter(rooms: Iterable[str] = (), rate_plans: Iterable[str] = (), date_from: str | None = None,
                date_to: str | None = None, occupancies: Iterable[str] = ()) -> tuple[Callable[[CellKey], bool] | None, str]:
    """일부만 되돌릴 때 칸을 고르는 조건과 그 범위를 사람이 읽는 글. 아무것도 주지 않으면 `(None, "")` — 변경 전체다."""
    rooms, rate_plans, occupancies = set(rooms), set(rate_plans), set(occupancies)
    if not (rooms or rate_plans or date_from or date_to or occupancies):
        return None, ""
    first, last = (date.fromisoformat(day).isoformat() if day else None for day in (date_from, date_to))

    def select(key: CellKey) -> bool:
        return ((not rooms or key.room in rooms) and (not rate_plans or key.rate_plan in rate_plans)
                and (first is None or key.date >= first) and (last is None or key.date <= last)
                and (not occupancies or key.occupancy in occupancies))

    parts = [" · ".join(sorted(rooms)), " · ".join(sorted(rate_plans)),
             f"{day_label(first) if first else '처음'} ~ {day_label(last) if last else '끝'}" if first or last else "",
             " · ".join(occupancy_label(occupancy) for occupancy in sorted(occupancies))]
    return select, " / ".join(part for part in parts if part)


def plan_cell_rollback(recorded: RecordedChange, later: Mapping[tuple[str, str], Sequence[LaterWrite]], now: Snapshot,
                       include_kept: bool = False, select: Callable[[CellKey], bool] | None = None) -> RollbackPlan:
    """가격 칸 되돌리기 — 지금 값을 읽은 날짜인지 보고, 공통 되돌리기 계산에 넘긴다. `select` 는 칸을 고르는 조건."""
    if not same_hotel(now.hotel, now.hotel_id, recorded.hotel, recorded.hotel_id) or now.offer != recorded.offer:
        raise PlanError(f"지금 읽은 값은 {hotel_label(now.hotel, now.hotel_id)} · {now.offer} 것이고, 되돌릴 변경은 "
                        f"{hotel_label(recorded.hotel, recorded.hotel_id)} · {recorded.offer} 입니다")
    chosen = [item for item in recorded.items if item.kind == ITEM_KIND and (select is None or select(key_of_item(item.key)))]
    gaps = sorted({f"{key.room} · {key.rate_plan} · {key.date}" for key in map(key_of_item, (i.key for i in chosen))
                   if not now.covers(key.room, key.rate_plan, key.date)})
    if gaps:
        raise PlanError(f"지금 값을 읽지 않은 날짜: {', '.join(gaps[:5])}{' …' if len(gaps) > 5 else ''}")
    return plan_rollback(recorded, later, snapshot_reading(now), now.read_at, include_kept,
                         None if select is None else lambda kind, key: kind == ITEM_KIND and select(key_of_item(key)))


def plan_cell_restore(snapshot: RecordedChange, now: Snapshot,
                      select: Callable[[CellKey], bool] | None = None) -> RollbackPlan:
    """저장해 둔 상태(장부의 지금 상태 저장)로 돌리기 — 지금 값을 그 범위만큼 읽었는지 보고 공통 계산에 넘긴다."""
    if not same_hotel(now.hotel, now.hotel_id, snapshot.hotel, snapshot.hotel_id) or now.offer != snapshot.offer:
        raise PlanError(f"지금 읽은 값은 {hotel_label(now.hotel, now.hotel_id)} · {now.offer} 것이고, 저장해 둔 상태는 "
                        f"{hotel_label(snapshot.hotel, snapshot.hotel_id)} · {snapshot.offer} 입니다")
    chosen = [key_of_item(item.key) for item in snapshot.items
              if item.kind == ITEM_KIND and (select is None or select(key_of_item(item.key)))]
    gaps = sorted({f"{key.room} · {key.rate_plan} · {key.date}" for key in chosen
                   if not now.covers(key.room, key.rate_plan, key.date)})
    if gaps:
        raise PlanError(f"지금 값을 읽지 않은 날짜: {', '.join(gaps[:5])}{' …' if len(gaps) > 5 else ''}")
    return plan_restore(snapshot, snapshot_reading(now), now.read_at,
                        None if select is None else lambda kind, key: kind == ITEM_KIND and select(key_of_item(key)))


def rollback_writes(plan: RollbackPlan) -> tuple[CellWrite, ...]:
    """돌릴 칸마다 적어 둔 값을 넣는다(적어 둔 값이 없던 필드는 비운다). 이미 그 값인 필드는 넣지 않는다."""
    writes = (_write(key_of_item(item.key), value_of(item.now), item.targets) for item in plan.restored)
    return tuple(write for write in writes if write is not None)


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
