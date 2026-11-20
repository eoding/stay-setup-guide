"""price_model.py — 가격 칸의 값 모양. 칸 계산·ERP 화면 읽기·칸 표 페이지가 이 모양 위에 서고, 장부·낡음 확인·되돌리기는
`change_core` 의 공통 모양((종류, 키, 필드) → 값)으로 바꿔 넘긴다. 돈은 전부 `Decimal` 이다.

    CellKey      칸 하나의 자리 — 객실 · 요금제 · 날짜 · 인원 조합 · 박수 층
    CellValue    그 칸의 값 — 판매가(sell) · 정가(list) · 공급 원가(supply) · 상태(open / closed / missing)
    Snapshot     ERP 에서 한 번 읽은 값 전부 + 예약 있는 (객실, 날짜)
    Skipped      건너뛰는 칸과 까닭(가격 없음 · 바꿀 값 없음 · 이미 그 값)
    ChangeRequest  담당자의 요청 — 범위 · 바꾸는 값 하나 · 바꾸는 방법 · 원래 문장
    TargetTable  칸마다 목표 값을 적은 표(새 요금표가 이 모양으로 들어온다) — 지금 값과 다른 칸만 바뀐다
    CellChange   칸 하나의 전 → 후 · 표시(예약 있는 날 · 마감) · 규칙 표의 판정 하나
    CELL_RULES   칸 판정 규칙 표 — 적용할 수 없음(blocked) · 빨간 줄(red)
    CellWrite    칸 하나에 넣을 값(필드마다 새 값 또는 비움)
    BulkStep     [선택 날짜 가격 수정] 저장 한 번 — 객실 × 요금제 × 이어진 날짜, 줄(RowWrite)마다 바뀌는 칸의 새 값
    CellEditStep 날짜 칸을 눌러 여는 셀 창 저장 한 번 — 칸 하나의 정가·공급 원가를 비운다
    Plan         미리보기 한 장의 내용
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cached_property
from typing import Mapping

from change_core.items import ItemState, Reading, item_key, key_fields
from change_core.money import money, money_text
from change_core.rules import BLOCKED, RED, Rule, RuleTable

ITEM_KIND = "price_cell"
FIELDS = ("sell", "list", "supply")
FIELD_LABELS = {"sell": "판매가", "list": "정가", "supply": "공급 원가"}
STATES = ("open", "closed", "missing")
OPERATIONS = ("amount", "percent", "set", "clear")
RESERVED, CLOSED, NEW = "reserved", "closed", "new"
RED_LINE_SHARE = Decimal("0.30")
WEEKDAYS = "월화수목금토일"


def iso_day(text: str) -> str:
    return date.fromisoformat(text).isoformat()


def split_occupancy(key: str) -> tuple[str | None, bool | None]:
    """`(성인만 있는 키, 아동 있음)`. 빈 키·맨 숫자는 칸 전체가 성인 몫이고, 읽지 못한 키는 `(None, None)` 이다."""
    text = key.strip().upper()
    if not text or text.isdigit():
        return key, False
    head = re.match(r"^A(\d+)(.*)$", text)
    if head is None:
        return None, None
    if not head.group(2):
        return key, False
    if re.match(r"^C\d+", head.group(2)):
        return f"A{head.group(1)}", True
    return None, None


def occupancy_order(key: str) -> tuple:
    """인원 무관 → 성인 수 → 아동 없는 칸 먼저."""
    adults = re.match(r"^A(\d+)", key.strip().upper())
    return (bool(key), int(adults.group(1)) if adults else 0, bool(split_occupancy(key)[1]), key)


@dataclass(frozen=True, order=True)
class CellKey:
    room: str
    rate_plan: str
    date: str
    occupancy: str
    nights: int


@dataclass(frozen=True)
class CellValue:
    sell: Decimal | None
    list: Decimal | None
    supply: Decimal | None
    state: str

    def __post_init__(self):
        if self.state not in STATES:
            raise ValueError(f"칸 상태를 모릅니다: {self.state!r}")
        if (self.state == "missing") != (self.sell is None):
            raise ValueError("가격 없는 칸(missing)만 판매가가 비어 있을 수 있습니다")


MISSING = CellValue(None, None, None, "missing")


@dataclass(frozen=True)
class Snapshot:
    hotel: str
    offer: str
    currency: str
    read_at: str
    cells: Mapping[CellKey, CellValue]
    reserved: frozenset[tuple[str, str]]

    @cached_property
    def days_read(self) -> frozenset[tuple[str, str, str]]:
        return frozenset((key.room, key.rate_plan, key.date) for key in self.cells)

    def covers(self, room: str, rate_plan: str, day: str) -> bool:
        return (room, rate_plan, day) in self.days_read


@dataclass(frozen=True)
class ChangeRequest:
    """범위 안의 칸에서 값 하나(`field`: 판매가 sell · 정가 list · 공급 원가 supply)를 바꾸는 요청.

    amount ±금액 · percent ±% · set 기준 인원 1박 칸을 그 값으로(나머지는 같은 만큼) · clear 비움(정가·공급 원가만).
    """
    hotel: str
    offer: str
    rooms: tuple[str, ...]
    rate_plans: tuple[str, ...]
    dates: tuple[str, ...]
    operation: str
    value: Decimal | None
    base_occupancy: str | None = None
    scale_child_surcharge: bool = False
    sentence: str = ""
    field: str = "sell"

    def __post_init__(self):
        if self.operation not in OPERATIONS:
            raise ValueError(f"바꾸는 방법을 모릅니다: {self.operation!r}")
        if self.field not in FIELDS:
            raise ValueError(f"바꾸는 값을 모릅니다: {self.field!r} (sell · list · supply)")
        if self.operation == "clear" and self.field == "sell":
            raise ValueError("판매가는 비울 수 없습니다")
        if (self.operation == "clear") != (self.value is None):
            raise ValueError("비우기(clear)에만 금액이 없습니다")
        if (self.operation == "set") != (self.base_occupancy is not None):
            raise ValueError("새 값 지정(set)에만, 그리고 반드시 기준 인원 조합을 적습니다")
        if not (self.rooms and self.rate_plans and self.dates):
            raise ValueError("객실·요금제·날짜를 하나 이상 적어야 합니다")
        if list(self.dates) != sorted({iso_day(day) for day in self.dates}):
            raise ValueError("날짜는 겹치지 않게 오름차순 ISO 형식(2026-12-25)으로 적습니다")


@dataclass(frozen=True)
class Target:
    """칸 하나의 목표 값. 적지 않은 필드는 그대로, None 으로 적은 필드(정가·공급 원가)는 비운다."""
    key: CellKey
    values: tuple[tuple[str, Decimal | None], ...]


@dataclass(frozen=True)
class TargetTable:
    hotel: str
    offer: str
    targets: tuple[Target, ...]
    sentence: str = ""

    def __post_init__(self):
        if not self.targets:
            raise ValueError("목표 값이 하나도 없습니다")
        seen = set()
        for target in self.targets:
            names = [name for name, _value in target.values]
            if not names or len(names) != len(set(names)) or not set(names) <= set(FIELDS):
                raise ValueError(f"목표 값의 칸 이름이 맞지 않습니다: {names} ({cell_name(target.key)})")
            if dict(target.values).get("sell", 0) is None:
                raise ValueError(f"판매가는 비울 수 없습니다: {cell_name(target.key)}")
            if target.key in seen:
                raise ValueError(f"같은 칸의 목표 값이 둘입니다: {cell_name(target.key)}")
            seen.add(target.key)


@dataclass(frozen=True)
class CellChange:
    key: CellKey
    before: CellValue
    after: CellValue | None
    marks: tuple[str, ...]
    verdict: str | None

    @property
    def changed(self) -> tuple[str, ...]:
        return () if self.after is None else tuple(f for f in FIELDS if getattr(self.after, f) != getattr(self.before, f))


def _moved_far(before: CellValue, after: CellValue | None) -> bool:
    if after is None:
        return False
    for name in FIELDS:
        old, new = getattr(before, name), getattr(after, name)
        if old is not None and new is not None and abs(new - old) > abs(old) * RED_LINE_SHARE:
            return True
    return False


CHOICE_LABELS = {
    "include": "이대로 바꿈",
    "keep": "이 칸은 안 바꿈",
    "raise_list": "정가도 같은 만큼 올림",
    "clear_list": "정가 지움",
}

# 판정 함수는 (전 값, 계산한 후 값 또는 None, 계산하지 못한 까닭 또는 None) 을 받는다. 까닭은 "adult"(성인만 있는 칸이
# 없음) · "base"(새 값 지정에서 그날 기준 인원 1박 칸에 값이 없음) · "sell"(새로 생기는 칸에 판매가가 없음) ·
# "row"(읽은 값에 없는 인원 조합·박수라 칸을 새로 만들지 않음).
# 정가·원가 규칙은 계산 뒤의 칸(후 값의 판매가·정가·원가)끼리 견준다.
CELL_RULES = RuleTable(
    Rule("NOT_POSITIVE", "0 이하가 됩니다", BLOCKED, (),
         lambda before, after, lacking: after is not None and after.sell <= 0),
    Rule("NEGATIVE_SUPPLY", "공급 원가가 0 아래가 됩니다", BLOCKED, (),
         lambda before, after, lacking: after is not None and after.supply is not None and after.supply < 0),
    Rule("NO_ADULT_CELL", "같은 날 성인만 있는 칸이 없습니다", BLOCKED, (),
         lambda before, after, lacking: lacking == "adult"),
    Rule("NO_BASE_CELL", "그날 기준 인원 1박 칸에 값이 없습니다", BLOCKED, (),
         lambda before, after, lacking: lacking == "base"),
    Rule("NEW_WITHOUT_SELL", "새로 생기는 칸에 판매가가 없습니다", BLOCKED, (),
         lambda before, after, lacking: lacking == "sell"),
    Rule("NEW_NOT_SHOWN", "이 객실·요금제에 없는 인원 조합·박수라 칸을 새로 만들지 않습니다", BLOCKED, (),
         lambda before, after, lacking: lacking == "row"),
    Rule("ABOVE_LIST", "정가보다 비싸집니다", RED, ("raise_list", "clear_list", "keep"),
         lambda before, after, lacking: after is not None and after.list is not None and after.sell > after.list),
    Rule("BELOW_COST", "공급 원가보다 싸집니다", RED, ("include", "keep"),
         lambda before, after, lacking: after is not None and after.supply is not None and after.sell < after.supply),
    Rule("OVER_30", "30% 넘게 바뀝니다", RED, ("include", "keep"),
         lambda before, after, lacking: _moved_far(before, after)),
)


@dataclass(frozen=True)
class CellWrite:
    """칸 하나에 넣을 값. None 인 필드는 그대로 두고, `clear` 에 든 필드는 비운다."""
    key: CellKey
    sell: Decimal | None = None
    list: Decimal | None = None
    supply: Decimal | None = None
    clear: tuple[str, ...] = ()

    def fields(self) -> dict[str, Decimal | None]:
        """쓰는 필드 → 넣을 값(비우는 필드는 None)."""
        written = {name: getattr(self, name) for name in FIELDS if getattr(self, name) is not None}
        written.update({name: None for name in self.clear})
        return written


@dataclass(frozen=True, order=True)
class RowWrite:
    """[선택 날짜 가격 수정] 표의 한 줄 — 칸마다 넣을 값, None 은 그 칸을 비워 보내 지금 값을 둔다."""
    occupancy: str
    nights: int
    sell: Decimal | None = None
    list: Decimal | None = None
    supply: Decimal | None = None


@dataclass(frozen=True)
class BulkStep:
    """[선택 날짜 가격 수정] 저장 한 번 — 객실 하나 × 요금제 하나 × 이어진 날짜, 줄마다 같은 값."""
    room: str
    rate_plan: str
    dates: tuple[str, ...]
    rows: tuple[RowWrite, ...]
    kind = "bulk"


@dataclass(frozen=True)
class CellEditStep:
    """셀 창 저장 한 번 — 칸 하나의 정가·공급 원가를 비운다(묶음 저장은 빈칸을 '그대로'로 읽어 비우지 못한다)."""
    key: CellKey
    clear: tuple[str, ...]
    kind = "cell_edit"


SKIP_LABELS = {"no_price": "가격 없음", "no_list": "정가 없음", "no_supply": "공급 원가 없음", "same": "이미 그 값"}


@dataclass(frozen=True)
class Skipped:
    """바꾸지 않고 건너뛰는 칸과 그 까닭(SKIP_LABELS)."""
    key: CellKey
    reason: str


@dataclass(frozen=True)
class Plan:
    request: ChangeRequest | TargetTable
    currency: str
    read_at: str
    changes: tuple[CellChange, ...]
    skipped: tuple[Skipped, ...]


# ─── 사람이 읽는 이름 ───


def day_label(day: str) -> str:
    value = date.fromisoformat(day)
    return f"{value.month}/{value.day} {WEEKDAYS[value.weekday()]}"


def occupancy_label(key: str) -> str:
    if not key:
        return "인원 무관"
    if key.isdigit():
        return f"{key}명"
    adult_key, has_children = split_occupancy(key)
    if adult_key is None:
        return key
    adults = f"성인 {adult_key[1:]}"
    if not has_children:
        return adults
    return f"{adults} + 아동 {sum(int(count) for count in re.findall(r'C(\d+)', key.upper()))}"


def nights_label(nights: int) -> str:
    return "1박" if nights == 1 else f"{nights}박 이상"


def cell_name(key: CellKey) -> str:
    return f"{day_label(key.date)} · {key.room} · {key.rate_plan} · {occupancy_label(key.occupancy)} · {nights_label(key.nights)}"


# ─── 공통 모양(change_core)으로 ───


def encode_key(key: CellKey) -> dict:
    return dict(room=key.room, rate_plan=key.rate_plan, date=key.date, occupancy=key.occupancy, nights=key.nights)


def decode_key(data: Mapping) -> CellKey:
    return CellKey(str(data["room"]), str(data["rate_plan"]), iso_day(data["date"]),
                   str(data.get("occupancy") or ""), int(data["nights"]))


def cell_item_key(key: CellKey) -> str:
    return item_key(encode_key(key))


def key_of_item(text: str) -> CellKey:
    return decode_key(key_fields(text))


def cell_state(key: CellKey, value: CellValue) -> ItemState:
    return ItemState(cell_name(key), value.state, {name: getattr(value, name) for name in FIELDS})


def value_of(state: ItemState) -> CellValue:
    return CellValue(*(state.fields.get(name) for name in FIELDS), state.state)


def snapshot_reading(snapshot: Snapshot) -> Reading:
    return {(ITEM_KIND, cell_item_key(key)): cell_state(key, value) for key, value in snapshot.cells.items()}


# ─── JSON ───


def encode_value(value: CellValue | None) -> dict | None:
    if value is None:
        return None
    return dict(sell=money_text(value.sell), list=money_text(value.list), supply=money_text(value.supply),
                state=value.state)


def decode_value(data: Mapping | None) -> CellValue | None:
    if data is None:
        return None
    return CellValue(money(data.get("sell")), money(data.get("list")), money(data.get("supply")), data["state"])


def encode_snapshot(snapshot: Snapshot) -> dict:
    return dict(
        hotel=snapshot.hotel, offer=snapshot.offer, currency=snapshot.currency, read_at=snapshot.read_at,
        cells=[dict(encode_key(key), **encode_value(value)) for key, value in sorted(snapshot.cells.items())],
        reserved=[dict(room=room, date=day) for room, day in sorted(snapshot.reserved)],
    )


def decode_snapshot(data: Mapping) -> Snapshot:
    cells = {}
    for item in data["cells"]:
        key = decode_key(item)
        if key in cells:
            raise ValueError(f"같은 칸이 두 번 있습니다: {encode_key(key)}")
        cells[key] = decode_value(item)
    return Snapshot(str(data["hotel"]), str(data["offer"]), str(data["currency"]).upper(), str(data["read_at"]),
                    cells, frozenset((str(item["room"]), iso_day(item["date"])) for item in data.get("reserved") or []))


def encode_request(request: ChangeRequest | TargetTable) -> dict:
    if isinstance(request, TargetTable):
        return dict(kind="targets", hotel=request.hotel, offer=request.offer, sentence=request.sentence,
                    targets=[dict(key=encode_key(target.key), values={name: money_text(value) for name, value in
                                                                      target.values}) for target in request.targets])
    return dict(kind="change", hotel=request.hotel, offer=request.offer, rooms=list(request.rooms),
                rate_plans=list(request.rate_plans), dates=list(request.dates), field=request.field,
                operation=dict(kind=request.operation, value=money_text(request.value),
                               base_occupancy=request.base_occupancy),
                scale_child_surcharge=request.scale_child_surcharge, sentence=request.sentence)


def decode_request(data: Mapping) -> ChangeRequest | TargetTable:
    if data.get("kind") == "targets":
        return TargetTable(str(data["hotel"]), str(data["offer"]),
                           tuple(Target(decode_key(item["key"]), tuple((str(name), money(value)) for name, value in
                                                                      item["values"].items())) for item in data["targets"]),
                           str(data.get("sentence") or ""))
    operation = data["operation"]
    return ChangeRequest(
        hotel=str(data["hotel"]), offer=str(data["offer"]), rooms=tuple(data["rooms"]),
        rate_plans=tuple(data["rate_plans"]), dates=tuple(data["dates"]), operation=operation["kind"],
        value=money(operation.get("value")), base_occupancy=operation.get("base_occupancy"),
        scale_child_surcharge=bool(data.get("scale_child_surcharge", False)), sentence=str(data.get("sentence") or ""),
        field=str(data.get("field") or "sell"),
    )


def encode_change(change: CellChange) -> dict:
    return dict(key=encode_key(change.key), before=encode_value(change.before), after=encode_value(change.after),
                marks=list(change.marks), verdict=change.verdict)


def decode_change(data: Mapping) -> CellChange:
    return CellChange(decode_key(data["key"]), decode_value(data["before"]), decode_value(data.get("after")),
                      tuple(data.get("marks") or ()), data.get("verdict"))


def encode_step(step: BulkStep | CellEditStep) -> dict:
    if step.kind == "cell_edit":
        return dict(kind=step.kind, key=encode_key(step.key), clear=list(step.clear))
    return dict(kind=step.kind, room=step.room, rate_plan=step.rate_plan, dates=list(step.dates),
                rows=[dict(occupancy=row.occupancy, nights=row.nights,
                           **{name: money_text(getattr(row, name)) for name in FIELDS}) for row in step.rows])


def decode_step(data: Mapping) -> BulkStep | CellEditStep:
    if data.get("kind") == "cell_edit":
        clear = tuple(str(name) for name in data["clear"])
        if not clear or not set(clear) <= {"list", "supply"}:
            raise ValueError(f"셀 창 단계는 정가·공급 원가만 비웁니다: {clear}")
        return CellEditStep(decode_key(data["key"]), clear)
    return BulkStep(str(data["room"]), str(data["rate_plan"]), tuple(iso_day(day) for day in data["dates"]),
                    tuple(RowWrite(str(row.get("occupancy") or ""), int(row["nights"]),
                                   *(money(row.get(name)) for name in FIELDS)) for row in data["rows"]))


def decode_resolution_items(items) -> tuple[CellKey, ...] | None:
    return None if items is None else tuple(decode_key(item) for item in items)


def encode_plan(plan: Plan) -> dict:
    return dict(request=encode_request(plan.request), currency=plan.currency, read_at=plan.read_at,
                changes=[encode_change(change) for change in plan.changes],
                skipped=[dict(key=encode_key(item.key), reason=item.reason) for item in plan.skipped])


def decode_plan(data: Mapping) -> Plan:
    return Plan(decode_request(data["request"]), str(data["currency"]).upper(), str(data["read_at"]),
                tuple(decode_change(item) for item in data["changes"]),
                tuple(Skipped(decode_key(item["key"]), str(item["reason"])) for item in data.get("skipped") or ()))
