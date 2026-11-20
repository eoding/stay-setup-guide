"""price_plan.py — 가격 칸 계산: 미리보기, 빨간 줄 고르기, 저장 단계 나누기, 그리고 공통 장부·낡음 확인·되돌리기와 잇기.

브라우저·파일을 모르는 순수 함수만 둔다.

    plan_change(snapshot, request)      → Plan          칸마다 전 → 후, 표시, 판정
    plan_targets(snapshot, table)       → Plan          목표 값 표 — 다른 칸만, 새로 생기는 칸 포함. 인원·박수가 없는 줄은 하나뿐인 줄로
    resolve(plan, resolutions)          → Plan          빨간 줄 고름을 칸에 단다 — 고른 칸의 후 값은 고른 대로(정가도 올림 · 지움 · 안 바꿈),
                                                        그 값으로 박수 층 규칙(1박 이상보다 비싼 층)을 다시 본다
    plan_steps(plan)                    → 저장 단계들   칸이 넣는 값(CellChange.writes)에서만. 고르지 않은 빨간 줄이 있으면 None
    save_steps(writes)                  → 저장 단계들   객실 × 요금제 × 줄과 값이 같은 날들(떨어져 있어도 한 번, 550일까지)
    stale_cells(then, now)              → 다른 항목들   (change_core.items.stale_items)
    plan_cell_rollback(recorded, …)     → RollbackPlan (change_core.rollback.plan_rollback) — cell_filter 로 일부만
    preview_rows · snapshot_rows · rollback_rows · step_plans   장부(change_core.ledger)에 넘길 공통 모양
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Iterable, Mapping, Sequence

from change_core.items import Difference, Refused, stale_items
from change_core.ledger import FieldWrite, StepPlan, ValueRow
from change_core.money import round_money
from change_core.rollback import LaterWrite, RecordedChange, RollbackPlan, plan_restore, plan_rollback
from change_core.rules import BLOCKED, Resolution, decide

from price_model import (
    CELL_RULES, CLOSED, ERP_MAX_DAYS, FIELD_LABELS, FIELDS, ITEM_KIND, MISSING, NEW, RESERVED, TIER_RULE, BulkStep, CellChange, CellEditStep, CellKey,
    CellValue, CellWrite, ChangeRequest, Plan, RowWrite, Skipped, Snapshot, TargetTable, cell_item_key, cell_name,
    day_label, day_windows, encode_step, hotel_label, key_of_item, line_label, matching_rows, occupancy_label, occupancy_order,
    same_hotel, snapshot_reading, split_occupancy, value_of,
)


class PlanError(Refused):
    """요청과 읽은 값이 맞지 않아 계산할 수 없다 — 문장은 담당자에게 그대로 보여 줄 수 있다."""


class ChooseRows(PlanError):
    """밴드 코드 없이 성인 · 아동 수만 적은 인원 조합(`A2C1`)에 맞는 줄이 그 객실 · 요금제에 여럿이다(아동 밴드가 여럿). 아무것도
    셈하거나 적지 않고, 고를 줄을 ERP 가 부르는 이름으로 댄다 — `choose` 는 `[{room, rate_plan, occupancy, choices: [{occupancy, label}]}]`."""

    def __init__(self, message: str, choose: list[dict]):
        super().__init__(message)
        self.choose = choose


def matched_rows(snapshot: Snapshot, wanted: Iterable[tuple[str, str, str]], fix: str) -> dict[tuple[str, str, str], tuple[str, ...]]:
    """(객실, 요금제, 적은 인원 조합) → 그 객실 · 요금제의 읽은 줄 가운데 그 이름이 가리키는 줄(`matching_rows` — 같은 키, 또는 밴드
    코드 없이 적은 이름이면 같은 성인 · 아동 수의 줄). 없으면 빈 묶음이다(부르는 쪽이 없는 줄로 알린다). 여럿인 이름이 하나라도 있으면
    모두 모아 ChooseRows — `fix` 는 고른 키를 어디에 적어 다시 하는지다."""
    found, choose = {}, []
    for room, plan, name in dict.fromkeys(wanted):
        rows = matching_rows(name, snapshot.rows.get((room, plan), ()))
        found[(room, plan, name)] = rows
        if len(rows) > 1:
            choose.append(dict(room=room, rate_plan=plan, occupancy=name,
                               choices=[dict(occupancy=key, label=snapshot.row_label(key)) for key in rows]))
    if choose:
        shown = "; ".join(f"{item['room']} · {item['rate_plan']} 의 {occupancy_label(item['occupancy'])}({item['occupancy']}) → "
                          + " / ".join(choice["label"] for choice in item["choices"]) for item in choose)
        raise ChooseRows(f"밴드 코드 없이 적은 인원 조합에 맞는 줄이 여럿입니다(아동 밴드가 여럿) — {shown}. 아무것도 적지 않았습니다. "
                         f"담당자에게 이 ERP 이름으로 어느 줄인지 묻고, {fix}", choose)
    return found


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

    새 값 지정(set)은 그날 기준 인원 · 1박 이상 칸이 그 값이 되는 만큼(차이)을 그 객실·요금제·날짜의 모든 인원·박수 칸에 더한다.
    박수 층의 할인 차이가 그대로 남는다. 기준 칸에 값이 없는 날은 "base"(적용할 수 없음)다. 퍼센트는 ERP 가감과 같이
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


def _list_follow(snapshot: Snapshot, request: ChangeRequest | TargetTable, key: CellKey, before: CellValue,
                 after: CellValue) -> Decimal | None:
    """「정가도 같이 올림」이면 정가가 될 값 — ERP [선택 날짜 가격 가감]의 「정가도 같이 조정」과 같은 규칙
    (basecamp `stay/services/bulk_price_adjust.py` build_preview): 판매가를 금액으로 옮기면 정가도 같은 금액, 퍼센트면 같은 비율이다.
    아동이 있는 칸의 퍼센트는 판매가처럼 성인 몫에만 곱한다 — 정가의 아동 추가분은 판매가의 추가분(칸 − 성인만 있는 칸)과 같다고
    보고 `반올림((정가 − 추가분) × 비율) + 추가분`(아동 추가분도 같이 바꾸면 칸 전체). 반올림은 판매가와 같다(통화 최소 단위, 반 올림).
    새 값 지정 · 목표 값처럼 ERP 에 짝이 없는 것은 판매가가 옮긴 만큼 정가도 옮긴다. 정가가 없는 칸은 None."""
    if before.list is None or before.sell is None:
        return None
    if isinstance(request, ChangeRequest) and request.field == "sell" and request.operation == "amount":
        return round_money(before.list + request.value, snapshot.currency)
    if isinstance(request, ChangeRequest) and request.field == "sell" and request.operation == "percent":
        factor = (100 + request.value) / 100
        adult_key, has_children = (key.occupancy, False) if request.scale_child_surcharge else split_occupancy(key.occupancy)
        if not has_children:
            return round_money(before.list * factor, snapshot.currency)
        extra = before.sell - snapshot.cells[replace(key, occupancy=adult_key)].sell
        return round_money((before.list - extra) * factor, snapshot.currency) + extra
    return before.list + (after.sell - before.sell)


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


def _resolve_occupancies(snapshot: Snapshot, request: ChangeRequest) -> ChangeRequest:
    """고른 인원 조합을 읽은 줄로 — 밴드 코드 없이 적은 이름(`A2C1`)은 객실 · 요금제마다 맞는 줄 하나(여럿이면 ChooseRows). 맞는 줄이
    하나도 없는 이름은 그대로 둔다(`_check_cells` 가 읽은 것을 대며 멈춘다). 새 값 지정의 기준 인원도 같은 줄로 옮긴다."""
    if not request.occupancies:
        return request
    found = matched_rows(snapshot, [(room, plan, name) for room, plan in request.pairs for name in request.occupancies],
                         "요청의 occupancies 에 고른 키를 적어 plan 을 다시 합니다")
    named = {name: tuple(dict.fromkeys(key for room, plan in request.pairs for key in found[(room, plan, name)])) or (name,)
             for name in request.occupancies}
    base = request.base_occupancy
    if base in named and len(named[base]) == 1:
        base = named[base][0]
    return replace(request, occupancies=tuple(dict.fromkeys(key for keys in named.values() for key in keys)), base_occupancy=base)


def plan_change(snapshot: Snapshot, request: ChangeRequest) -> Plan:
    """칸마다 전 → 후. `request.occupancies`·`nights` 를 적었으면 그 칸만 — 규칙 · 표시 · 저장 단계는 다른 변경과 같다. 미리보기의
    요청은 고른 인원 조합을 읽은 줄 키로 푼 것이다(밴드 코드 없이 적은 `A2C1` → `A2C1_CHD`)."""
    pairs, absent = requested_pairs(snapshot, request)
    request = replace(request, pairs=pairs)
    rooms = {room: rank for rank, room in enumerate(request.rooms)}
    plans = {plan: rank for rank, plan in enumerate(request.rate_plans)}
    dates, wanted = set(request.dates), set(pairs)
    keys = [key for key in snapshot.cells if (key.room, key.rate_plan) in wanted and key.date in dates]
    empty = _check_scope(snapshot, request, pairs,
                         [(room, plan, day) for room, plan in pairs for day in request.dates])
    request = _resolve_occupancies(snapshot, request)
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
        changes.append(_change(snapshot, request, key, before, after, lacking))
    return _judged(Plan(request, snapshot.currency, snapshot.read_at, tuple(changes), tuple(skipped), empty, absent, no_sale),
                   snapshot)


def _change(snapshot: Snapshot, request: ChangeRequest | TargetTable, key: CellKey, before: CellValue,
            after: CellValue | None, lacking: str | None) -> CellChange:
    """칸 하나의 판정 — 정가보다 비싸지는 칸이면 「정가도 같이 올림」일 때의 정가도 셈해 둔다."""
    verdict = CELL_RULES.verdict(before, after, lacking, False)
    follow = _list_follow(snapshot, request, key, before, after) if verdict == "ABOVE_LIST" else None
    return CellChange(key, before, after, _marks(snapshot, key, before), verdict, list_follow=follow)


def fill_lines(snapshot: Snapshot, table: TargetTable) -> TargetTable:
    """인원 조합 · 박수를 적지 않은 목표 → 읽은 값에서 그 객실 · 요금제의 줄 가운데 적은 것과 맞는 줄이 꼭 하나면 그 줄.
    없거나 여럿이면 고를 수 있는 줄을 대며 거절한다(담당자의 표는 보통 객실 · 요금제 · 날짜 · 값만 적는다). 밴드 코드 없이 성인 · 아동
    수만 적은 인원 조합(`A2C1`)은 먼저 그 수의 줄로 푼다(`matched_rows` — 여럿이면 ChooseRows)."""
    lines: dict[tuple[str, str], set[tuple[str, int]]] = {}
    for key in snapshot.cells:
        lines.setdefault((key.room, key.rate_plan), set()).add((key.occupancy, key.nights))
    found = matched_rows(snapshot, [(t.key.room, t.key.rate_plan, t.key.occupancy) for t in table.targets if t.key.occupancy],
                         "그 목표의 occupancy 에 고른 키를 적어 plan 을 다시 합니다")
    targets = []
    for target in table.targets:
        key = target.key
        rows = found.get((key.room, key.rate_plan, key.occupancy), ())
        if len(rows) == 1:
            key = replace(key, occupancy=rows[0])
            target = replace(target, key=key)
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
        changes.append(_change(snapshot, table, key, before, after, lacking))
    return _judged(Plan(table, snapshot.currency, snapshot.read_at, tuple(changes), (), no_sale=tuple(sorted(no_sale))), snapshot)


def _tier_group(key: CellKey) -> tuple[str, str, str, str]:
    """박수 층끼리 견주는 묶음 — 같은 객실 · 요금제 · 날짜 · 인원 조합(ERP 의 판매일 · 요금제 · 인원 조합)."""
    return key.room, key.rate_plan, key.date, key.occupancy


def _judged(plan: Plan, snapshot: Snapshot) -> Plan:
    """계산을 마친 미리보기 — 박수 층 규칙에 쓸 바꾸지 않는 층의 지금 값(`tiers`)과, 바꾸기 전부터 1박 이상 층보다 비싼 박수 층 칸
    수를 달고, 아직 아무것도 고르지 않은 채로 박수 층 규칙을 본다(resolve)."""
    moved = {_tier_group(change.key) for change in plan.changes
             if change.after is not None and change.after.sell != change.before.sell}
    tiers = {key: value.sell for key, value in snapshot.cells.items() if value.sell is not None and _tier_group(key) in moved}
    one_night = {_tier_group(key): value.sell for key, value in snapshot.cells.items() if key.nights == 1 and value.sell is not None}
    above = sum(1 for key, value in snapshot.cells.items() if key.nights > 1 and value.sell is not None
                and one_night.get(_tier_group(key)) is not None and value.sell > one_night[_tier_group(key)])
    return resolve(replace(plan, tiers=tiers, above_one_night_before=above), ())


CHOICES = ("include", "keep", "raise_list", "clear_list")


def counts(changes: Sequence[CellChange], skipped: int = 0) -> dict:
    """미리보기 머리 숫자. `cells` 는 계산한 칸, `will_change` 는 그중 저장할 칸(적용할 수 없는 칸과 안 바꾸기로 고른 칸을 뺀 수,
    아직 고르지 않은 빨간 줄은 든다), `red` 는 아직 고르지 않은 빨간 줄, `chosen` 은 고른 빨간 줄, 고름마다(`raise_list` 등)
    그 수, `new` 는 새로 생기는 칸. 규칙 코드마다의 수는 고르기 전이든 뒤든 그 규칙에 걸린 칸이다."""
    tally = dict(cells=len(changes), will_change=0, blocked=0, red=0, chosen=0, reserved=0, closed=0, new=0, skipped=skipped)
    tally.update({rule.code: 0 for rule in CELL_RULES.rules})
    tally.update({choice: 0 for choice in CHOICES})
    for change in changes:
        severity = CELL_RULES.severity(change.verdict)
        tally["blocked"] += severity == BLOCKED
        tally["will_change"] += severity != BLOCKED and change.choice != "keep"
        tally["red"] += change.waiting
        if change.verdict:
            tally[change.verdict] += 1
        if change.choice:
            tally["chosen"] += 1
            tally[change.choice] += 1
        for mark in change.marks:
            tally[mark] += 1
    return tally


def resolve(plan: Plan, resolutions: Iterable[Resolution]) -> Plan:
    """빨간 줄 고름을 칸에 단 미리보기. 받는 것은 계산이 막 낸 미리보기(plan_change · plan_targets — 아직 고른 것이 없다)다.

    두 번에 나눠 단다. 먼저 칸 하나로 정하는 규칙(정가 · 공급 원가 · 30%)의 고름을 달고, 그 뒤의 값으로 박수 층 규칙을 본다 — 같은 날
    1박 이상 층보다 비싼 박수 층이 되는지는 다른 칸이 고른 뒤 어떤 값이 되는지에 달렸다(안 바꾸기로 고른 칸은 지금 값으로 남는다).
    박수 층 규칙의 판정이 공급 원가 · 30% 보다 앞선다(ERP 차례 — 정가보다 비싸짐 다음). 정가보다 비싸지는 칸은 정가 고름(정가도
    같이 올림 · 정가 지움)으로 판매가가 바뀔 때만 박수 층 규칙을 본다. 그 칸이 걸리면 판정은 박수 층 규칙이 되고 정가 고름은 후 값
    (올린 · 지운 정가)으로 남는다.

    고른 칸의 후 값은 고른 대로다 — include 계산한 값 그대로 · keep 전 값 그대로 · raise_list 정가를 계산 때 셈해 둔 값으로
    (CellChange.list_follow — ERP 「정가도 같이 조정」의 규칙) · clear_list 정가를 비움. 저장 단계(plan_steps)와 장부의
    줄(preview_rows)이 이 값에서 나온다. 칸을 짚은 고름이 규칙 전체 고름보다 앞서고, 고르지 않은 빨간 줄 칸은 그대로 둔다.
    """
    resolutions = tuple(resolutions)
    fresh = {change.key: replace(change, verdict=_own_verdict(change)) for change in plan.changes}
    flagged = {key: change.verdict for key, change in fresh.items() if change.verdict}
    chosen, _waiting = decide(CELL_RULES, flagged, [item for item in resolutions if item.rule != TIER_RULE], cell_name)
    first = {key: _choose(change, chosen.get(key)) for key, change in fresh.items()}
    tier_choices = [item for item in resolutions if item.rule == TIER_RULE]
    included: set[CellKey] = set()
    for _round in range(len(first) + 1):    # 「이대로 바꿈」으로 바꾼 값이 다른 칸의 견줌을 바꾼다 — 고름이 더 늘지 않을 때까지
        breaks = _tier_breaks(plan, first, included)
        picked, _waiting = decide(CELL_RULES, dict.fromkeys(breaks, TIER_RULE), tier_choices, cell_name)
        now = {key for key, picked_one in picked.items() if picked_one.choice == "include"}
        if now == included:
            break
        included = now
    return replace(plan, changes=tuple(
        _choose(replace(first[change.key], verdict=TIER_RULE, choice=None), picked.get(change.key)) if change.key in breaks
        else first[change.key] for change in plan.changes))


def _own_verdict(change: CellChange) -> str | None:
    """칸 하나로 정하는 판정 — 막 계산한 칸이 박수 층 규칙에 걸려 있으면 그 밑의 판정(공급 원가 · 30% · 없음)을 다시 본다."""
    if change.verdict != TIER_RULE:
        return change.verdict
    return CELL_RULES.verdict(change.before, change.after, None, False)


def _saves_sell(change: CellChange) -> bool:
    """저장이 판매가를 바꾸는 칸 — 적용할 수 없는 칸 · 안 바꾸기로 고른 칸이 아니고 판매가가 달라진다. 아직 고르지 않은 빨간 줄은
    미리보기가 보이는 계산한 값으로 본다."""
    return (CELL_RULES.severity(change.verdict) != BLOCKED and change.choice != "keep" and change.after is not None
            and change.after.sell != change.before.sell)


def _tier_breaks(plan: Plan, cells: Mapping[CellKey, CellChange], included: set[CellKey]) -> set[CellKey]:
    """박수 층 규칙에 걸리는 칸 — ERP 의 `bulk_price_adjust._check_los_tiers` 와 같은 판정이다.

    박수 층은 같은 객실 · 요금제 · 날짜 · 인원 조합의 1박 이상 층보다 비싸면 안 된다. 바꾼 뒤의 값(바꾸지 않는 칸 · 안 바꾸기로 고른
    칸은 지금 값)끼리 견준다. ① 2박 이상 층의 칸이 그날 1박 이상 칸보다 비싸지면 그 칸 ② 1박 이상 칸을 내려 위 층보다 싸지면 그 1박
    이상 칸 ③ ② 로 걸린 칸이 지금 값으로 돌아가면 ① 을 한 번 더. 걸린 칸은 ERP 처럼 안 바꾸는 것으로 보고(담당자가 「이대로
    바꿈」을 고른 칸 `included` 만 바꾼 값으로 본다) 더 걸리는 칸이 없을 때까지 돈다. 한 번 걸린 칸은 풀지 않는다(ERP 와 같다).

    보는 칸은 저장이 판매가를 바꾸는 칸이다. 아직 고르지 않은 「정가보다 비싸짐」 칸은 보지 않는다 — ERP 차례에서 그 규칙이 앞선다.
    바꾸기 전부터 규칙을 어긴 칸이라도 이번에 바꾸면 본다. 바꾸지 않는 칸은 보지 않는다(Plan.above_one_night_before 가 그 수를 센다).
    """
    flagged: set[CellKey] = set()
    candidates = [change for change in cells.values()
                  if _saves_sell(change) and not (change.verdict == "ABOVE_LIST" and change.choice is None)]
    groups: dict[tuple, set[int]] = defaultdict(set)
    for key in [*plan.tiers, *(key for key, change in cells.items() if _saves_sell(change))]:
        groups[_tier_group(key)].add(key.nights)

    def price_at(key: CellKey) -> Decimal | None:
        change = cells.get(key)
        if change is None:
            return plan.tiers.get(key)
        if _saves_sell(change) and (key not in flagged or key in included):
            return change.after.sell
        return change.before.sell

    def upper_tiers():
        for change in candidates:
            if change.key in flagged or change.key.nights == 1:
                continue
            one_night = price_at(replace(change.key, nights=1))
            if one_night is not None and change.after.sell > one_night:
                flagged.add(change.key)

    def one_night_cells():
        for change in candidates:
            if change.key in flagged or change.key.nights != 1:
                continue
            for nights in sorted(groups[_tier_group(change.key)] - {1}):
                upper = price_at(replace(change.key, nights=nights))
                if upper is not None and upper > change.after.sell:
                    flagged.add(change.key)
                    break

    while True:
        count = len(flagged)
        upper_tiers()
        one_night_cells()
        upper_tiers()
        if len(flagged) == count:
            return flagged


def _choose(change: CellChange, resolution: Resolution | None) -> CellChange:
    """고름을 칸에 단다 — 고른 것(`choice`)과 그렇게 고르며 담당자가 한 말(`said`), 그리고 고른 대로의 후 값."""
    if resolution is None:
        return change
    choice = resolution.choice
    after = change.after
    if choice == "keep":
        after = change.before
    elif choice == "raise_list":
        if change.list_follow is None:
            raise PlanError(f"정가를 같이 올릴 수 없는 칸입니다(전 정가가 없음): {cell_name(change.key)}")
        if change.list_follow < after.sell:   # ERP 도 이 칸은 건너뛴다(정가보다 비싸짐) — 지금도 정가가 판매가보다 낮은 칸이다
            raise PlanError(f"정가를 같이 올려도 판매가보다 낮은 칸입니다(지금도 정가가 판매가보다 낮음): {cell_name(change.key)} — "
                            "정가 지움이나 그 칸은 안 바꿈을 고릅니다")
        after = replace(after, list=change.list_follow)
    elif choice == "clear_list":
        after = replace(after, list=None)
    return replace(change, after=after, choice=choice, said=resolution.said or None)


def unresolved(plan: Plan) -> tuple[CellChange, ...]:
    """아직 고르지 않은 빨간 줄 칸."""
    return tuple(change for change in plan.changes if change.waiting)


def plan_steps(plan: Plan) -> tuple[BulkStep | CellEditStep, ...] | None:
    """칸이 넣는 값(CellChange.writes)만으로 나눈 저장 단계. 고르지 않은 빨간 줄이 있으면 None — 아직 저장할 수 없다."""
    if unresolved(plan):
        return None
    writes = (_write(change.key, change.before, change.writes) for change in plan.changes)
    return save_steps(write for write in writes if write is not None)


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


def _rows(key: CellKey, before: CellValue, after: CellValue | None, writes: Mapping[str, Decimal | None],
          verdict=None, marks=(), choice=None, said=None) -> list[ValueRow]:
    """칸 하나 → 필드마다 장부 한 줄. `after` 는 그 칸의 후 값(전과 다른 필드만 적힌다), `writes` 는 저장이 넣는 필드(비움은 None)."""
    rows = []
    for name in FIELDS:
        old, new = getattr(before, name), None if after is None else getattr(after, name)
        action = None if name not in writes else "clear" if writes[name] is None else "set"
        rows.append(ValueRow(ITEM_KIND, cell_item_key(key), cell_name(key), name, before.state, old, None if new == old else new,
                             verdict, marks, action, choice, said))
    return rows


def preview_rows(plan: Plan) -> list[ValueRow]:
    """미리보기의 칸 그대로 — 필드마다 전 값 · 후 값 · 넣는지(set · clear) · 판정 · 표시 · 고른 것과 고르며 한 말."""
    return [row for change in plan.changes for row in _rows(change.key, change.before, change.after, change.writes,
                                                             change.verdict, change.marks, change.choice, change.said)]


def snapshot_rows(snapshot: Snapshot) -> list[ValueRow]:
    return [row for key, value in sorted(snapshot.cells.items())
            for row in _rows(key, value, None, {}, marks=(RESERVED,) if (key.room, key.date) in snapshot.reserved else ())]


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


def _restores(plan: RollbackPlan) -> list[tuple[CellKey, CellValue, CellWrite]]:
    """돌릴 칸마다 `(칸, 지금 값, 넣을 값)` — 적어 둔 값을 넣고(적어 둔 값이 없던 필드는 비운다), 이미 그 값인 필드는 넣지 않는다."""
    out = []
    for item in plan.restored:
        key = key_of_item(item.key)
        now = value_of(item.now) if item.now.fields else MISSING
        write = _write(key, now, item.targets)
        if write is not None:
            out.append((key, now, write))
    return out


def rollback_writes(plan: RollbackPlan) -> tuple[CellWrite, ...]:
    return tuple(write for _key, _now, write in _restores(plan))


def rollback_rows(plan: RollbackPlan) -> list[ValueRow]:
    """되돌리기의 장부 줄 — rollback_writes 와 같은 넣을 값에서."""
    rows = []
    for key, now, write in _restores(plan):
        fields = write.fields()
        after = CellValue(*(fields.get(name, getattr(now, name)) for name in FIELDS),
                          "open" if now.state == "missing" else now.state)
        rows += _rows(key, now, after, fields)
    return rows
