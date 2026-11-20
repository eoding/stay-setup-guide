"""price_model.py — 가격 변경 도우미의 값 모양. 계산·장부·화면 읽기·HTML 이 모두 이 모양 위에 선다.

돈은 전부 `Decimal` 이다(float 를 쓰지 않는다). JSON 에서는 문자열("373.95")로 오간다.

    CellKey      칸 하나의 자리 — 객실 · 요금제 · 날짜 · 인원 조합 · 박수 층
    CellValue    그 칸의 값 — 판매가 · 정가 · 공급 원가 · 상태(open / closed / missing)
    Snapshot     ERP 에서 한 번 읽은 값 전부 + 예약 있는 (객실, 날짜)
    ChangeRequest  담당자의 요청 — 범위 · 바꾸는 방법(amount / percent / set) · 원래 문장
    CellChange   칸 하나의 전 → 후 · 표시(예약 있는 날 · 마감) · 규칙 표의 판정 하나
    RULES        판정 규칙 표 — 적용할 수 없음(blocked) · 빨간 줄(red)
    CellWrite / RowWrite / SaveStep   ERP [선택 날짜 가격 수정] 저장 한 번에 들어가는 값
    Plan / RollbackPlan               미리보기 · 되돌리기 미리보기 한 장의 내용
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import cached_property
from typing import Callable, Mapping

ZERO_DECIMAL_CURRENCIES = frozenset({"KRW", "VND", "JPY", "IDR", "CLP", "ISK"})
STATES = ("open", "closed", "missing")
OPERATIONS = ("amount", "percent", "set")
BLOCKED, RED = "blocked", "red"
RESERVED, CLOSED = "reserved", "closed"
RED_LINE_SHARE = Decimal("0.30")


def scale_of(currency: str) -> int:
    return 0 if currency.upper() in ZERO_DECIMAL_CURRENCIES else 2


def round_money(value: Decimal, currency: str) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-scale_of(currency)), rounding=ROUND_HALF_UP)


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
    list_price: Decimal | None
    supply_cost: Decimal | None
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
    hotel: str
    offer: str
    rooms: tuple[str, ...]
    rate_plans: tuple[str, ...]
    dates: tuple[str, ...]
    operation: str
    value: Decimal
    base_occupancy: str | None = None
    scale_child_surcharge: bool = False
    sentence: str = ""

    def __post_init__(self):
        if self.operation not in OPERATIONS:
            raise ValueError(f"바꾸는 방법을 모릅니다: {self.operation!r}")
        if (self.operation == "set") != (self.base_occupancy is not None):
            raise ValueError("새 값 지정(set)에만, 그리고 반드시 기준 인원 조합을 적습니다")
        if not (self.rooms and self.rate_plans and self.dates):
            raise ValueError("객실·요금제·날짜를 하나 이상 적어야 합니다")
        if list(self.dates) != sorted({iso_day(day) for day in self.dates}):
            raise ValueError("날짜는 겹치지 않게 오름차순 ISO 형식(2026-12-25)으로 적습니다")


@dataclass(frozen=True)
class CellChange:
    key: CellKey
    before: CellValue
    after: CellValue | None
    marks: tuple[str, ...]
    verdict: str | None


@dataclass(frozen=True)
class Rule:
    code: str
    label: str
    severity: str
    choices: tuple[str, ...]
    applies: Callable[[CellValue, CellValue | None, str | None], bool]


CHOICE_LABELS = {
    "include": "이대로 바꿈",
    "keep": "이 칸은 안 바꿈",
    "raise_list": "정가도 같은 만큼 올림",
}

# 위에서부터 처음 맞는 한 줄이 칸의 판정이다. 세 번째 인자는 계산에 필요한 칸이 없을 때 그 칸 이름("adult"·"base")이다.
RULES = (
    Rule("NOT_POSITIVE", "0 이하가 됩니다", BLOCKED, (),
         lambda before, after, lacking: after is not None and after.sell <= 0),
    Rule("NO_ADULT_CELL", "같은 날 성인만 있는 칸이 없습니다", BLOCKED, (),
         lambda before, after, lacking: lacking == "adult"),
    Rule("NO_BASE_CELL", "같은 날 기준 인원 가격이 없습니다", BLOCKED, (),
         lambda before, after, lacking: lacking == "base"),
    Rule("ABOVE_LIST", "정가보다 비싸집니다", RED, ("raise_list", "keep"),
         lambda before, after, lacking: after is not None and before.list_price is not None
         and after.sell > before.list_price),
    Rule("BELOW_COST", "공급 원가보다 싸집니다", RED, ("include", "keep"),
         lambda before, after, lacking: after is not None and before.supply_cost is not None
         and after.sell < before.supply_cost),
    Rule("OVER_30", "30% 넘게 바뀝니다", RED, ("include", "keep"),
         lambda before, after, lacking: after is not None
         and abs(after.sell - before.sell) > abs(before.sell) * RED_LINE_SHARE),
)
RULE_BY_CODE = {rule.code: rule for rule in RULES}


def verdict_of(before: CellValue, after: CellValue | None, lacking: str | None) -> str | None:
    return next((rule.code for rule in RULES if rule.applies(before, after, lacking)), None)


@dataclass(frozen=True)
class Resolution:
    rule: str
    choice: str
    cells: tuple[CellKey, ...] | None = None

    def __post_init__(self):
        rule = RULE_BY_CODE.get(self.rule)
        if rule is None or rule.severity != RED:
            raise ValueError(f"고를 수 있는 것은 빨간 줄 규칙뿐입니다: {self.rule!r}")
        if self.choice not in rule.choices:
            raise ValueError(f"{self.rule} 에서 고를 수 있는 것: {', '.join(rule.choices)} (받은 값 {self.choice!r})")


@dataclass(frozen=True)
class CellWrite:
    """칸 하나에 넣을 값. `list_price` 가 None 이면 정가 칸은 비워 보내 지금 정가를 그대로 둔다."""
    key: CellKey
    sell: Decimal
    list_price: Decimal | None = None


@dataclass(frozen=True, order=True)
class RowWrite:
    occupancy: str
    nights: int
    sell: Decimal
    list_price: Decimal | None = None


@dataclass(frozen=True)
class SaveStep:
    """[선택 날짜 가격 수정] 저장 한 번 — 객실 하나 × 요금제 하나 × 이어진 날짜, 줄마다 같은 값."""
    room: str
    rate_plan: str
    dates: tuple[str, ...]
    rows: tuple[RowWrite, ...]


@dataclass(frozen=True)
class Plan:
    request: ChangeRequest
    currency: str
    read_at: str
    changes: tuple[CellChange, ...]
    skipped: tuple[CellKey, ...]


@dataclass(frozen=True)
class RecordedCell:
    """장부에 적힌, 실제로 저장된 칸 하나 — 적어 둔 전 값과 넣은 값."""
    key: CellKey
    before: CellValue
    written: CellWrite


@dataclass(frozen=True)
class RecordedChange:
    id: int
    kind: str
    hotel: str
    offer: str
    currency: str
    sentence: str
    read_at: str
    applied_at: str | None
    cells: tuple[RecordedCell, ...]


@dataclass(frozen=True)
class LaterWrite:
    change_id: int
    at: str
    sentence: str
    write: CellWrite


@dataclass(frozen=True)
class Cause:
    """되돌리지 않고 두는 까닭 — 이 장부의 나중 변경(번호·시각·문장) 또는 도우미 밖."""
    change_id: int | None = None
    at: str | None = None
    sentence: str | None = None

    @property
    def outside(self) -> bool:
        return self.change_id is None


@dataclass(frozen=True)
class KeptCell:
    key: CellKey
    recorded: CellValue
    written: CellWrite
    now: CellValue
    cause: Cause


@dataclass(frozen=True)
class RollbackPlan:
    reverses: int
    hotel: str
    offer: str
    currency: str
    restore_to: str
    original_sentence: str
    original_applied_at: str | None
    restored: tuple[CellChange, ...]
    kept: tuple[KeptCell, ...]
    include_kept: bool
    read_at: str


# ─── JSON ───


def money(text) -> Decimal | None:
    if text is None:
        return None
    try:
        value = Decimal(str(text).replace(",", "").strip())
    except InvalidOperation:
        raise ValueError(f"금액을 읽지 못했습니다: {text!r}") from None
    if not value.is_finite():
        raise ValueError(f"금액을 읽지 못했습니다: {text!r}")
    return value


def money_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def encode_key(key: CellKey) -> dict:
    return dict(room=key.room, rate_plan=key.rate_plan, date=key.date, occupancy=key.occupancy, nights=key.nights)


def decode_key(data: Mapping) -> CellKey:
    return CellKey(str(data["room"]), str(data["rate_plan"]), iso_day(data["date"]),
                   str(data.get("occupancy") or ""), int(data["nights"]))


def encode_value(value: CellValue | None) -> dict | None:
    if value is None:
        return None
    return dict(sell=money_text(value.sell), list=money_text(value.list_price),
                supply=money_text(value.supply_cost), state=value.state)


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


def encode_request(request: ChangeRequest) -> dict:
    return dict(hotel=request.hotel, offer=request.offer, rooms=list(request.rooms),
                rate_plans=list(request.rate_plans), dates=list(request.dates),
                operation=dict(kind=request.operation, value=str(request.value),
                               base_occupancy=request.base_occupancy),
                scale_child_surcharge=request.scale_child_surcharge, sentence=request.sentence)


def decode_request(data: Mapping) -> ChangeRequest:
    operation = data["operation"]
    return ChangeRequest(
        hotel=str(data["hotel"]), offer=str(data["offer"]), rooms=tuple(data["rooms"]),
        rate_plans=tuple(data["rate_plans"]), dates=tuple(data["dates"]), operation=operation["kind"],
        value=money(operation["value"]), base_occupancy=operation.get("base_occupancy"),
        scale_child_surcharge=bool(data.get("scale_child_surcharge", False)), sentence=str(data.get("sentence") or ""),
    )


def encode_change(change: CellChange) -> dict:
    return dict(key=encode_key(change.key), before=encode_value(change.before), after=encode_value(change.after),
                marks=list(change.marks), verdict=change.verdict)


def decode_change(data: Mapping) -> CellChange:
    return CellChange(decode_key(data["key"]), decode_value(data["before"]), decode_value(data.get("after")),
                      tuple(data.get("marks") or ()), data.get("verdict"))


def encode_write(write: CellWrite) -> dict:
    return dict(key=encode_key(write.key), sell=str(write.sell), list=money_text(write.list_price))


def decode_write(data: Mapping) -> CellWrite:
    return CellWrite(decode_key(data["key"]), money(data["sell"]), money(data.get("list")))


def encode_step(step: SaveStep) -> dict:
    return dict(room=step.room, rate_plan=step.rate_plan, dates=list(step.dates),
                rows=[dict(occupancy=row.occupancy, nights=row.nights, sell=str(row.sell),
                           list=money_text(row.list_price)) for row in step.rows])


def decode_step(data: Mapping) -> SaveStep:
    return SaveStep(str(data["room"]), str(data["rate_plan"]), tuple(iso_day(day) for day in data["dates"]),
                    tuple(RowWrite(str(row.get("occupancy") or ""), int(row["nights"]), money(row["sell"]),
                                   money(row.get("list"))) for row in data["rows"]))


def decode_resolution(data: Mapping) -> Resolution:
    cells = data.get("cells")
    return Resolution(str(data["rule"]), str(data["choice"]),
                      None if cells is None else tuple(decode_key(item) for item in cells))


def encode_plan(plan: Plan) -> dict:
    return dict(request=encode_request(plan.request), currency=plan.currency, read_at=plan.read_at,
                changes=[encode_change(change) for change in plan.changes],
                skipped=[encode_key(key) for key in plan.skipped])


def decode_plan(data: Mapping) -> Plan:
    return Plan(decode_request(data["request"]), str(data["currency"]).upper(), str(data["read_at"]),
                tuple(decode_change(item) for item in data["changes"]),
                tuple(decode_key(item) for item in data.get("skipped") or ()))


def encode_rollback(plan: RollbackPlan) -> dict:
    return dict(
        reverses=plan.reverses, hotel=plan.hotel, offer=plan.offer, currency=plan.currency,
        restore_to=plan.restore_to, original_sentence=plan.original_sentence,
        original_applied_at=plan.original_applied_at, include_kept=plan.include_kept, read_at=plan.read_at,
        restored=[encode_change(change) for change in plan.restored],
        kept=[dict(key=encode_key(cell.key), recorded=encode_value(cell.recorded), written=encode_write(cell.written),
                   now=encode_value(cell.now),
                   cause=dict(change_id=cell.cause.change_id, at=cell.cause.at, sentence=cell.cause.sentence))
              for cell in plan.kept],
    )


def decode_rollback(data: Mapping) -> RollbackPlan:
    kept = tuple(
        KeptCell(decode_key(item["key"]), decode_value(item["recorded"]), decode_write(item["written"]),
                 decode_value(item["now"]), Cause(**item["cause"]))
        for item in data.get("kept") or ()
    )
    return RollbackPlan(
        int(data["reverses"]), str(data["hotel"]), str(data["offer"]), str(data["currency"]).upper(),
        str(data["restore_to"]), str(data.get("original_sentence") or ""), data.get("original_applied_at"),
        tuple(decode_change(item) for item in data["restored"]), kept, bool(data.get("include_kept")),
        str(data["read_at"]),
    )
