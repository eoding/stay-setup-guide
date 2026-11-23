"""price_model.py — 가격 칸의 값 모양. 칸 계산·ERP 화면 읽기·칸 표 페이지가 이 모양 위에 서고, 장부·낡음 확인·되돌리기는
`change_core` 의 공통 모양((종류, 키, 필드) → 값)으로 바꿔 넘긴다. 돈은 전부 `Decimal` 이다.

    CellKey      칸 하나의 자리 — 객실 · 요금제 · 날짜 · 인원 조합 · 박수 층
    CellValue    그 칸의 값 — 판매가(sell) · 정가(list) · 공급 원가(supply) · 상태(open / closed / mixed / missing). 화면은 판매
                 상태를 (객실, 요금제, 날)마다 하나로 보여 칸의 상태가 섞인 날의 칸은 모두 mixed 다(어느 칸이 마감인지 모른다 — as_read)
    Snapshot     ERP 에서 한 번 읽은 값 전부 + 예약 있는 (객실, 날짜) + 지속 마감인 (객실, 요금제, 날). 호텔은 페이지가 알아본
                 번호(hotel_id)와 이름
    Skipped      건너뛰는 칸과 까닭(가격 없음 · 바꿀 값 없음 · 이미 그 값)
    ReadRange    읽을 범위 — 호텔 · 오퍼 · (객실, 요금제) 쌍 · 날짜. 바꾸는 방법 없이 읽기만 할 때의 요청(kind range)
    ChangeRequest  담당자의 요청 — 범위 · 바꾸는 값 하나 · 바꾸는 방법 · 원래 문장
    TargetTable  칸마다 목표 값을 적은 표 — 지금 값과 다른 칸만 바뀐다. 새 요금표(price_sheet)도 이 모양으로 펼쳐 들어온다
    Gap          요금표로 맞출 때 넣지 않는 것 하나(요금표에 없는 칸 · 없는 인원 조합 · 판매일 없는 날 · 없는 객실) — Plan.coverage
    CellChange   칸 하나의 전 → 저장한 뒤 · 표시(예약 있는 날 · 마감) · 규칙 표의 판정 하나 · 빨간 줄에 고른 것.
                 저장 단계와 장부의 줄은 이것에서만 나온다
    CELL_RULES   칸 판정 규칙 표 — 적용할 수 없음(blocked) · 빨간 줄(red) · 같이 그대로(held)
    CellWrite    칸 하나에 넣을 값(필드마다 새 값 또는 비움)
    BulkStep     [선택 날짜 가격 수정] 저장 한 번 — 객실 × 요금제 × 줄과 값이 같은 날들(떨어져 있어도), 줄(RowWrite)마다 새 값
    CellEditStep 날짜 칸을 눌러 여는 셀 창 저장 한 번 — 칸 하나의 정가·공급 원가를 비운다
    Plan         미리보기 한 장의 내용
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from functools import cached_property
from typing import Iterable, Mapping

from change_core.items import ItemState, Reading, item_key, key_fields
from change_core.money import money, money_text
from change_core.rules import BLOCKED, RED, Rule, RuleTable, moved_far

ITEM_KIND = "price_cell"
FIELDS = ("sell", "list", "supply")
FIELD_LABELS = {"sell": "판매가", "list": "정가", "supply": "공급 원가"}
STATES = ("open", "closed", "mixed", "missing")
OPERATIONS = ("amount", "percent", "set", "clear")
RESERVED, CLOSED, NEW = "reserved", "closed", "new"
WEEKDAYS = "월화수목금토일"
# ERP 가 날짜 고르기 한 번에 받는 날 — basecamp `stay/date_selection.py` 의 MAX_DAYS(구간 하나의 길이도, 고른 날 수도 550일까지).
# 드로어 ① 의 시작일 ~ 종료일도 이 길이까지다(러너 `CAL_MAX_DAYS`). 구간 줄의 수 자체는 정해 두지 않았다(글자 12,000자 칸).
ERP_MAX_DAYS = 550


def iso_day(text: str) -> str:
    return date.fromisoformat(text).isoformat()


def day_windows(days, span: int) -> list[list[str]]:
    """오름차순 날짜 → 첫 날부터 끝 날까지가 `span` 일을 넘지 않게 앞에서부터 나눈 묶음들."""
    windows: list[list[str]] = []
    for day in days:
        if windows and (date.fromisoformat(day) - date.fromisoformat(windows[-1][0])).days < span:
            windows[-1].append(day)
        else:
            windows.append([day])
    return windows


def same_hotel(name: str, hotel_id: str, other_name: str, other_id: str) -> bool:
    """같은 호텔인지는 번호로 정한다(이름이 같은 호텔이 있다). 번호가 없는 값끼리만 이름으로 본다(시험에서 만든 값)."""
    return hotel_id == other_id and (bool(hotel_id) or name == other_name)


def hotel_label(name: str, hotel_id: str) -> str:
    return f"호텔 {hotel_id} ({name})" if hotel_id else name


def encode_hotel(name: str, hotel_id: str) -> dict:
    """JSON 의 호텔 — stayPrice.look() 의 `hotel` 과 같은 모양 {id, name}."""
    return dict(id=hotel_id, name=name)


def decode_hotel(data) -> tuple[str, str]:
    """`{id, name}` → (이름, 번호). 번호는 페이지가 알아본 것이어야 한다 — 이름만으로는 호텔을 정하지 않는다."""
    if not isinstance(data, Mapping) or not str(data.get("id") or "").strip():
        raise ValueError("hotel 은 stayPrice.look() 이 준 {id, name} 을 그대로 적습니다(호텔 번호 없이 이름만으로는 정하지 않습니다)")
    return str(data.get("name") or ""), str(data["id"]).strip()


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


def guest_counts(key: str) -> tuple[int, int] | None:
    """(성인 수, 아동 수) — `A2` (2, 0) · `A2C1` · `A2C1_CHD` (2, 1) · `A2C1_CHD_C1_TEEN` (2, 2). 키는 ERP 의 꼴
    (`A<성인>C<아동>_<밴드 코드>`, 아동 조각이 더 있으면 `_C<아동>_<밴드 코드>`)이다. 인원 무관 · 맨 숫자 · 읽지 못한 키는 None."""
    head = re.fullmatch(r"A(\d+)(?:C(\d+)((?:_[A-Z0-9]+)*))?", key.strip().upper())
    if head is None:
        return None
    adults, first, tail = head.groups()
    return int(adults), int(first or 0) + sum(int(count) for count in re.findall(r"_C(\d+)(?=_|$)", tail or ""))


def matching_rows(name: str, keys) -> tuple[str, ...]:
    """읽은 인원 조합 키들 가운데 `name` 이 가리키는 줄. 같은 키가 있으면 그 줄 하나, 밴드 코드 없이 성인 · 아동 수만 적은 이름
    (`A2C1` — 요금표의 "성인 2 + 아동 1")이면 그 수의 줄 전부(아동 밴드가 여럿이면 여럿), 그 밖은 없다."""
    keys = tuple(dict.fromkeys(keys))
    if name in keys:
        return (name,)
    if re.fullmatch(r"A\d+C\d+", name.strip().upper()) is None:
        return ()
    return tuple(sorted((key for key in keys if guest_counts(key) == guest_counts(name)), key=occupancy_order))


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
    """ERP 에서 한 번 읽은 값. `pairs` 는 읽은 (객실, 요금제) 전부 — 칸이 하나도 없어도 읽었으면 여기 있다.

    객실은 캘린더 칩에 보이는 이름으로 적는다. `room_names` 는 그 이름 → 가격 수정 드로어가 같은 객실을 부르는 이름이다.
    `no_sale` 은 (객실, 날짜) — 판매일이 없어 칸이 없는 날(「판매일 없음」, 「가격 없음」과 다르다). 읽은 날로 친다.
    `dates` 는 읽은 날 전부 — `pairs` 와 함께 읽은 범위다(`range`). 주지 않으면 칸과 판매일 없는 날에서 모은다.
    `row_labels` 는 인원 조합 키 → 가격 수정 드로어가 그 줄을 부르는 이름(`A2C1_CHD · 소아 1`) — 담당자에게 줄을 고르게 할 때 쓴다.
    `closures` 는 (객실, 요금제, 날) — 그날 상태가 「요금제 마감」 · 「객실 전체 마감」(지속 마감)인 것. ERP 는 그날 새로 만드는 칸도
    마감으로 만든다. 셀 창에서 칸마다 마감한 날(「기존 가격 …」)은 여기 없다 — ERP 가 그날 새로 만드는 칸은 판매 가능이다.
    """
    hotel: str
    offer: str
    currency: str
    read_at: str
    cells: Mapping[CellKey, CellValue]
    reserved: frozenset[tuple[str, str]]
    pairs: frozenset[tuple[str, str]]
    room_names: Mapping[str, str] = field(default_factory=dict)
    no_sale: frozenset[tuple[str, str]] = frozenset()
    hotel_id: str = ""
    dates: tuple[str, ...] = ()
    row_labels: Mapping[str, str] = field(default_factory=dict)
    closures: frozenset[tuple[str, str, str]] = frozenset()

    def __post_init__(self):
        stray = sorted({(key.room, key.rate_plan) for key in self.cells} - set(self.pairs))
        if stray:
            raise ValueError(f"읽었다고 적지 않은 객실·요금제의 칸이 있습니다: {' · '.join(f'{r}/{p}' for r, p in stray)}")
        days = set(self.dates) or {key.date for key in self.cells} | {day for _room, day in self.no_sale}
        object.__setattr__(self, "dates", tuple(sorted(days)))

    @property
    def range(self) -> "ReadRange":
        """이 값을 읽은 범위 — 같은 범위를 다시 읽을 때(적용 직전 · 적용 뒤 · 되돌리기 · 이어서) 이것을 쓴다."""
        return ReadRange(self.hotel, self.hotel_id, self.offer, tuple(sorted(self.pairs)), self.dates)

    @cached_property
    def days_read(self) -> frozenset[tuple[str, str, str]]:
        return frozenset((key.room, key.rate_plan, key.date) for key in self.cells)

    def covers(self, room: str, rate_plan: str, day: str) -> bool:
        return (room, rate_plan) in self.pairs and (room, rate_plan, day) in self.days_read

    @cached_property
    def rows(self) -> Mapping[tuple[str, str], frozenset[str]]:
        """(객실, 요금제) → 읽은 값에 나온 인원 조합 키들."""
        found: dict[tuple[str, str], set[str]] = {}
        for key in self.cells:
            found.setdefault((key.room, key.rate_plan), set()).add(key.occupancy)
        return {pair: frozenset(keys) for pair, keys in found.items()}

    def row_label(self, key: str) -> str:
        """ERP 가 그 줄을 부르는 이름 — 읽은 화면의 것, 없으면 키와 우리말 이름."""
        return self.row_labels.get(key) or (f"{key} · {occupancy_label(key)}" if key else occupancy_label(key))


@dataclass(frozen=True)
class ReadRange:
    """읽을 범위. 요청 파일의 `kind: range` 가 이 모양이고, 바꾸기 요청 · 목표 값 표도 범위를 하나씩 갖는다(`request_range`)."""
    hotel: str
    hotel_id: str
    offer: str
    pairs: tuple[tuple[str, str], ...]
    dates: tuple[str, ...]

    def __post_init__(self):
        if not self.pairs or not self.dates:
            raise ValueError("읽을 범위에는 객실 · 요금제와 날짜가 하나 이상 있어야 합니다")
        if list(self.dates) != sorted({iso_day(day) for day in self.dates}):
            raise ValueError("날짜는 겹치지 않게 오름차순 ISO 형식(2026-12-25)으로 적습니다")


@dataclass(frozen=True)
class ChangeRequest:
    """범위 안의 칸에서 값 하나(`field`: 판매가 sell · 정가 list · 공급 원가 supply)를 바꾸는 요청.

    amount ±금액 · percent ±% · set 기준 인원 · 1박 이상 칸을 그 값으로(나머지는 같은 만큼) · clear 비움(정가·공급 원가만).

    범위는 (객실, 요금제) 쌍 `pairs` 다. 객실과 요금제를 따로 주면 "적은 객실마다 그 객실에 있는 적은 요금제"이고,
    계산(`plan_change`)이 읽은 쌍으로 풀어 `pairs` 를 채운다. 쌍만 주면 객실·요금제는 쌍에서 나온 차례로 채운다.

    칸은 따로 말하지 않으면 모든 인원 조합 · 모든 박수 층이다(결정 14). `occupancies`(인원 조합 키) · `nights`(박수 층의 시작
    박수)를 적으면 그 칸만 움직인다. 새 값 지정의 기준 칸(기준 인원 · 1박 이상)은 적은 칸 안에 있어야 한다.
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
    pairs: tuple[tuple[str, str], ...] = ()
    hotel_id: str = ""
    occupancies: tuple[str, ...] = ()
    nights: tuple[int, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "occupancies", tuple(str(key) for key in self.occupancies))
        object.__setattr__(self, "nights", tuple(int(n) for n in self.nights))
        if len(set(self.occupancies)) != len(self.occupancies) or len(set(self.nights)) != len(self.nights):
            raise ValueError("고른 인원 조합 · 박수가 두 번 있습니다")
        if any(n < 1 for n in self.nights):
            raise ValueError("박수 층은 1 이상의 시작 박수로 적습니다(1, 3 …)")
        if self.operation == "set" and ((self.occupancies and self.base_occupancy not in self.occupancies)
                                        or (self.nights and 1 not in self.nights)):
            raise ValueError(f"새 값 지정의 기준 칸({occupancy_label(self.base_occupancy or '')} · 1박 이상)이 고른 칸에 없습니다 — "
                             "기준 칸을 고른 칸에 넣거나, 고른 칸을 금액(amount)이나 퍼센트(percent)로 바꿉니다")
        pairs = tuple((str(room), str(plan)) for room, plan in self.pairs)
        if len(set(pairs)) != len(pairs):
            raise ValueError("같은 객실·요금제 쌍이 두 번 있습니다")
        object.__setattr__(self, "pairs", pairs)
        if pairs and not self.rooms:
            object.__setattr__(self, "rooms", tuple(dict.fromkeys(room for room, _plan in pairs)))
        if pairs and not self.rate_plans:
            object.__setattr__(self, "rate_plans", tuple(dict.fromkeys(plan for _room, plan in pairs)))
        if any(room not in self.rooms or plan not in self.rate_plans for room, plan in pairs):
            raise ValueError("쌍의 객실·요금제가 적은 객실·요금제 안에 있어야 합니다")
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
    """칸 하나의 목표 값. 적지 않은 필드는 그대로, None 으로 적은 필드(정가·공급 원가)는 비운다.

    담당자의 표에는 인원 조합 · 박수가 없을 때가 많다. 그러면 `key.occupancy`·`key.nights` 가 None 이고, 계산(`plan_targets`)이
    읽은 값에서 그 객실 · 요금제의 줄이 하나뿐일 때만 그 줄로 채운다(여럿이면 고를 줄을 대며 거절한다)."""
    key: CellKey
    values: tuple[tuple[str, Decimal | None], ...]


@dataclass(frozen=True)
class TargetTable:
    """`from_sheet` 는 새 요금표를 펼친 표다(price_sheet.plan_sheet) — 미리보기 · 결과가 시즌 [가격] 덮기 한 문장을 단다."""
    hotel: str
    offer: str
    targets: tuple[Target, ...]
    sentence: str = ""
    hotel_id: str = ""
    from_sheet: bool = False

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
    """칸 하나 — 미리보기 · 저장 단계 · 장부가 모두 이것에서 나온다.

    `after` 는 저장하면 그 칸이 될 값이다. 빨간 줄을 고른 칸은 고른 대로다(정가도 올림이면 올린 정가, 정가 지움이면 빈 정가,
    안 바꿈이면 전 값 그대로). `verdict` 는 계산한 값이 걸린 규칙이고 고른 뒤에도 남는다. `choice` 는 그 빨간 줄에 담당자가 고른
    것(CHOICE_LABELS)이고, 아직 고르지 않았으면 None — 그때 `after` 는 계산한 값이다. `said` 는 그렇게 고르며 담당자가 한 말이다. 적용할 수 없는 칸의 `after` 는 계산한
    값(셈하지 못했으면 None)이고 저장하지 않는다. 같이 그대로 두는 칸(ADULT_HELD)도 계산한 값이고 저장하지 않는다 — 성인 칸의
    고름이 바뀌어 다시 계산할 때(price_plan.resolve) 그 값으로 다시 본다.

    `list_follow` 는 정가보다 비싸지는 칸(ABOVE_LIST)에서 「정가도 같이 올림」을 고르면 정가가 될 값이다 — ERP 의 「정가도 같이
    조정」과 같은 규칙으로 계산 때 셈해 둔다(price_plan._list_follow). 다른 칸은 None.
    """
    key: CellKey
    before: CellValue
    after: CellValue | None
    marks: tuple[str, ...]
    verdict: str | None
    choice: str | None = None
    list_follow: Decimal | None = None
    said: str | None = None

    @property
    def changed(self) -> tuple[str, ...]:
        return () if self.after is None else tuple(f for f in FIELDS if getattr(self.after, f) != getattr(self.before, f))

    @property
    def waiting(self) -> bool:
        """아직 고르지 않은 빨간 줄."""
        return CELL_RULES.severity(self.verdict) == RED and self.choice is None

    @property
    def writes(self) -> dict[str, Decimal | None]:
        """저장이 이 칸에 넣는 필드 → 값(비우면 None). 적용할 수 없는 칸 · 같이 그대로 두는 칸 · 아직 고르지 않은 빨간 줄은 넣지 않는다."""
        if CELL_RULES.severity(self.verdict) in (BLOCKED, HELD) or self.waiting:
            return {}
        return {name: getattr(self.after, name) for name in self.changed}


def _moved_far(before: CellValue, after: CellValue | None) -> bool:
    return after is not None and any(moved_far(getattr(before, name), getattr(after, name)) for name in FIELDS)


CHOICE_LABELS = {
    "include": "이대로 바꿈",
    "keep": "그 칸은 안 바꿈",
    "raise_list": "정가도 같이 올림",   # 요청마다 정가가 어떻게 되는지는 price_pages.choice_words 가 숫자와 함께 말한다
    "clear_list": "정가 지움",
}

# 판정 함수는 (전 값, 계산한 후 값 또는 None, 계산하지 못한 까닭 또는 None, 박수 층 규칙에 걸림) 을 받는다. 까닭은 "adult"(성인만
# 있는 칸이 없음) · "base"(새 값 지정에서 그날 기준 인원 · 1박 이상 칸에 값이 없음) · "sell"(새로 생기는 칸에 판매가가 없음) ·
# "row"(읽은 값에 없는 인원 조합·박수라 칸을 새로 만들지 않음). 박수 층 규칙은 칸 하나로 정할 수 없어(같은 날 다른 층의 값 — 고른
# 뒤의 값 — 과 견준다) 계산(price_plan._tier_breaks)이 정해 넘긴다.
# 정가·원가 규칙은 계산 뒤의 칸(후 값의 판매가·정가·원가)끼리 견준다. 표의 차례는 ERP [선택 날짜 가격 가감]이 건너뛸 까닭을 보는
# 차례를 따른다 — 정가보다 비싸짐 → 1박 가격보다 비싸짐(`bulk_price_adjust.build_preview`). 공급 원가 · 30% 는 ERP 에 없는 도우미의
# 확인이라 그 뒤다.
TIER_RULE = "ABOVE_ONE_NIGHT"
HELD = "held"           # 같이 그대로 — 다른 칸을 따라 저장하지 않는다(고를 것이 아니고, ERP 가 받지 않는 값도 아니다)
HELD_RULE = "ADULT_HELD"
CELL_RULES = RuleTable(
    Rule("NOT_POSITIVE", "0 이하가 됩니다", BLOCKED, (),
         lambda before, after, lacking, tier: after is not None and after.sell <= 0),
    Rule("NEGATIVE_SUPPLY", "공급 원가가 0 아래가 됩니다", BLOCKED, (),
         lambda before, after, lacking, tier: after is not None and after.supply is not None and after.supply < 0),
    Rule("NO_ADULT_CELL", "같은 날 성인만 있는 칸이 없습니다", BLOCKED, (),
         lambda before, after, lacking, tier: lacking == "adult"),
    Rule("NO_BASE_CELL", "그날 기준 인원 · 1박 이상 칸에 값이 없습니다", BLOCKED, (),
         lambda before, after, lacking, tier: lacking == "base"),
    Rule("NEW_WITHOUT_SELL", "새로 생기는 칸에 판매가가 없습니다", BLOCKED, (),
         lambda before, after, lacking, tier: lacking == "sell"),
    Rule("NEW_NOT_SHOWN", "이 객실·요금제에 없는 인원 조합·박수라 칸을 새로 만들지 않습니다", BLOCKED, (),
         lambda before, after, lacking, tier: lacking == "row"),
    # 아동이 든 칸은 같은 객실 · 요금제 · 날짜 · 박수 층의 성인만 있는 칸이 새 값을 받지 않으면 같이 그대로 둔다 — 칸 하나로 정할 수
    # 없어(같은 날 성인 칸의 고름 · 판정 · 박수 층 규칙) 계산(price_plan.resolve)이 정해 단다. ERP `_skip_followers_of_skipped_adult_cells`.
    Rule(HELD_RULE, "성인만 있는 칸을 바꾸지 않아 같이 그대로 둡니다", HELD, (),
         lambda before, after, lacking, tier: False),
    Rule("ABOVE_LIST", "정가보다 비싸집니다", RED, ("raise_list", "clear_list", "keep"),
         lambda before, after, lacking, tier: after is not None and after.list is not None and after.sell > after.list),
    Rule(TIER_RULE, "박수 층이 1박 이상 가격보다 비싸집니다", RED, ("include", "keep"),
         lambda before, after, lacking, tier: tier),
    Rule("BELOW_COST", "공급 원가보다 싸집니다", RED, ("include", "keep"),
         lambda before, after, lacking, tier: after is not None and after.supply is not None and after.sell < after.supply),
    Rule("OVER_30", "30% 넘게 바뀝니다", RED, ("include", "keep"),
         lambda before, after, lacking, tier: _moved_far(before, after)),
)


# 적용할 수 없는 칸의 까닭 — 규칙마다 (왜 바꿀 수 없는지, 담당자가 대신 할 수 있는 것). 값이 문제인 것(0 이하 · 공급 원가 0 아래)만
# 금액을 바꾸라고 한다. 칸 · 줄이 없어서인 것은 어떤 금액이어도 같다고 말하고 그 길을 댄다(시운전 11 — 없는 줄 「성인 2 · 5박 이상」을
# 「ERP 가 받지 않는 값」이라 하고 금액을 바꾸라고 했다). 미리보기 페이지와 plan 의 답(`blocked[].said`)이 같은 말을 쓴다.
BLOCKED_WORDS = {
    "NOT_POSITIVE": ("계산하면 판매가가 0 이하가 되어 바꿀 수 없습니다", "금액을 바꿔 다시 말씀해 주세요."),
    "NEGATIVE_SUPPLY": ("계산하면 공급 원가가 0 아래가 되어 바꿀 수 없습니다", "금액을 바꿔 다시 말씀해 주세요."),
    "NO_ADULT_CELL": ("아동이 든 칸은 같은 날 성인만 있는 칸에 비율을 곱하는데 그 칸이 없어 셈할 수 없습니다 — 비율을 바꿔도 같습니다",
                      "아동 추가분까지 같은 비율로 바꾸라고 하시거나, 금액(+ · −)으로 말씀해 주세요."),
    "NO_BASE_CELL": ("새 값은 그날 기준 인원 · 1박 이상 칸을 기준으로 셈하는데 그 칸에 값이 없어 셈할 수 없습니다 — 금액을 바꿔도 "
                     "같습니다", "칸마다 넣을 값을 짧은 표로 주시거나, 금액(+ · −)으로 말씀해 주세요."),
    "NEW_WITHOUT_SELL": ("지금 가격이 없는 칸이라 판매가 없이는 새로 만들 수 없습니다", "그 칸의 판매가도 같이 말씀해 주세요."),
    "NEW_NOT_SHOWN": ("이 객실 · 요금제에는 그 인원 조합 · 박수 줄이 없어 넣을 수 없습니다 — 금액을 바꿔도 같습니다",
                      "그 줄은 ERP 에서 사람이 만듭니다 — 그날 가격 수정 창의 「추가할 인원 조합」이나 시즌의 [가격 입력] 창에서요. "
                      "박수 층이면 그 시즌을 다시 채우라고 하실 때 도우미가 만들 수 있습니다."),
}


ALREADY_BELOW = "이미 공급 원가보다 쌉니다 — 이번에도 그대로"


def below_cost_label(pairs: Iterable[tuple[CellValue, CellValue]]) -> str:
    """공급 원가 빨간 줄의 이름 — `(전 값, 후 값)` 칸들 가운데 바꾸기 전부터 판매가가 공급 원가보다 쌌던 칸이 있으면 그렇게 말한다.
    모두 그랬으면 「이미 공급 원가보다 쌉니다 — 이번에도 그대로」(시운전 9 · 12 — 50.00 < 52.00 이던 칸이 51.00 이 되는데 「싸집니다」라고
    했다), 일부면 그 수를 덧붙인다. 가격 캘린더(날짜별)와 시즌 다시 채우기가 같은 말을 쓴다."""
    pairs = list(pairs)
    already = sum(1 for before, _after in pairs
                  if before.sell is not None and before.supply is not None and before.sell < before.supply)
    if pairs and already == len(pairs):
        return ALREADY_BELOW
    label = CELL_RULES.by_code["BELOW_COST"].label
    return f"{label}(그 가운데 {already:,}칸은 {ALREADY_BELOW})" if already else label


def blocked_said(code: str, cells: int, example: str) -> str:
    """적용할 수 없는 칸 한 묶음(규칙 하나)을 담당자에게 하는 말 — 칸 수 · 예 · 까닭 · 대신 할 수 있는 것."""
    why, instead = BLOCKED_WORDS[code]
    shown = f"({example})" if cells == 1 else f"(예: {example})"
    return f"적용할 수 없는 {cells:,}칸{shown}은 {why}. {instead}"


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
    """[선택 날짜 가격 수정] 저장 한 번 — 객실 하나 × 요금제 하나 × 쓰는 줄과 값이 같은 날들(떨어져 있어도 된다 — 드로어가
    날짜 구간을 여럿 받는다), 줄마다 같은 값."""
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

# 요금표로 맞출 때 넣지 않는 것의 종류 → 미리보기 머리. 차례가 곧 보이는 차례다.
GAP_KINDS = {
    "untouched": "요금표에 없는 칸 — 그대로 둡니다",
    "unseen": "이 객실 · 요금제에 없는 인원 조합 · 박수 — 칸을 새로 만들지 않습니다",
    "no_sale": "판매일 없는 날 — 이 길로는 넣을 수 없습니다",
    "unknown": "호텔에 없는 객실 · 요금제 — 넣지 않습니다",
    "unnamed": "요금표에 없는 객실 · 요금제 — 그대로 둡니다",
}


@dataclass(frozen=True)
class Gap:
    """요금표로 맞출 때 넣지 않는 것 하나. 종류마다 쓰는 칸:

        untouched  호텔에 가격이 있는데 요금표가 말하지 않은 칸 — 객실 · 요금제 · 인원 · 박수 · 날짜들. 그대로 둔다
        unseen     읽은 값에 그 객실 · 요금제의 줄로 나온 적 없는 인원 · 박수 — 줄 번호들 · 날짜들. 새 종류의 칸은 만들지 않는다(R6)
        no_sale    판매일이 없어 칸이 없는 날 — 객실 · 요금제 · 날짜들
        unknown    요금표에 있는데 호텔(이 오퍼)에 없는 객실 · 요금제 — 줄 번호들
        unnamed    호텔에 있는데 요금표가 말하지 않은 객실 · 요금제 — 그대로 둔다
    """
    kind: str
    room: str
    rate_plan: str
    occupancy: str | None = None
    nights: int | None = None
    dates: tuple[str, ...] = ()
    lines: tuple[int, ...] = ()

    def __post_init__(self):
        if self.kind not in GAP_KINDS:
            raise ValueError(f"넣지 않는 것의 종류를 모릅니다: {self.kind!r}")


@dataclass(frozen=True)
class Skipped:
    """바꾸지 않고 건너뛰는 칸과 그 까닭(SKIP_LABELS)."""
    key: CellKey
    reason: str


@dataclass(frozen=True)
class UnusedChoice:
    """담당자가 고른 빨간 줄 고름 가운데 이번 계산에서 어느 칸도 쓰지 않는 것 — 고름 하나 · 까닭 하나에 하나. `cells` 는 그 고름을
    말한 칸(규칙 전체 고름이면 그 규칙에 걸린 칸 가운데 그 고름이 덮던 칸, 덮던 칸이 없으면 빈 것), `why` 는 까닭의 코드
    (UNUSED_WHY), `words` 는 담당자에게 그 까닭을 말하는 한 마디다. 미리보기 · plan 의 답 · 도우미의 말이 같은 것을 말한다."""
    rule: str
    choice: str
    said: str
    why: str
    words: str
    cells: tuple[CellKey, ...] = ()


UNUSED_WHY = {   # 고른 것이 어느 칸에도 쓰이지 않은 까닭 → 담당자에게 하는 한 마디(같이 그대로 둔 칸은 성인 칸이 왜 그대로인지에 따라)
    "held_kept": "성인만 있는 칸을 그대로 두셔서 같이 그대로 둡니다",
    "held_blocked": "성인만 있는 칸을 바꿀 수 없어 같이 그대로 둡니다",
    "held_waiting": "성인만 있는 칸을 아직 고르지 않으셔서 같이 그대로 둡니다",
    "held": "성인만 있는 칸이 바뀌지 않아 같이 그대로 둡니다",
    "tier": "1박 이상보다 비싸지는 박수 층 빨간 줄로 넘어가 그 고름을 따릅니다",
    "pinned": "그 빨간 줄의 칸을 모두 칸마다 따로 고르셨습니다",
    "replaced": "같은 칸 · 같은 빨간 줄에 뒤에 고르신 것이 앞섭니다",
    "none": "이번 계산에는 그 빨간 줄에 걸린 칸이 없습니다",
}


@dataclass(frozen=True)
class Plan:
    """`empty_pairs` 는 요청한 (객실, 요금제) 가운데 읽었지만 칸이 하나도 없던 것 — 건너뜀으로 알린다.

    `absent_pairs` 는 객실·요금제를 따로 받았을 때 그 객실에 없어(읽은 쌍에 없어) 요청에서 뺀 조합 — 미리보기가 이름을 댄다.
    `no_sale` 은 요청한 (객실, 요금제, 날짜) 가운데 판매일이 없어 바꿀 수 없는 날 — 「판매일 없음」으로 건너뛴다.
    `coverage` 는 새 요금표로 맞출 때 넣지 않는 것 전부(Gap) — 요금표에서 온 계획만 갖는다.
    `tiers` 는 판매가가 바뀌는 칸과 같은 객실 · 요금제 · 날짜 · 인원 조합의 모든 박수 층의 지금 판매가 — 박수 층 규칙(1박 이상보다
    비싼 층)을 고른 뒤에 다시 볼 때 바꾸지 않는 층의 값이다. `above_one_night_before` 는 읽은 값에서 바꾸기 전부터 같은 날 1박 이상
    층보다 비싼 박수 층 칸의 수다(이번 변경과 상관없이 — 미리보기가 알린다). `unused` 는 고른 빨간 줄 고름 가운데 이번 계산에서 어느
    칸도 쓰지 않는 것(UnusedChoice — price_plan.resolve 가 단다).
    """
    request: ChangeRequest | TargetTable
    currency: str
    read_at: str
    changes: tuple[CellChange, ...]
    skipped: tuple[Skipped, ...]
    empty_pairs: tuple[tuple[str, str], ...] = ()
    absent_pairs: tuple[tuple[str, str], ...] = ()
    no_sale: tuple[tuple[str, str, str], ...] = ()
    coverage: tuple[Gap, ...] = ()
    tiers: Mapping[CellKey, Decimal] = field(default_factory=dict)
    above_one_night_before: int = 0
    unused: tuple[UnusedChoice, ...] = ()


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
    children = sum(int(count) for count in re.findall(r"C(\d+)", key.upper()))
    return f"{adults} + 아동 {children}"


def nights_label(nights: int) -> str:
    """박수 층의 이름 — ERP 가 부르는 그대로(`Labels.nights`: "1박 이상", "3박 이상"). 층은 그 박수 이상의 숙박을 덮는다."""
    return f"{nights}박 이상"


def line_label(occupancy: str | None, nights: int | None) -> str:
    """인원 · 박수 줄 하나의 이름. 표에 없던 것(None)은 「인원 조합 ?」 · 「박수 ?」."""
    return (f"{'인원 조합 ?' if occupancy is None else occupancy_label(occupancy)} · "
            f"{'박수 ?' if nights is None else nights_label(nights)}")


def cell_name(key: CellKey) -> str:
    return f"{day_label(key.date)} · {key.room} · {key.rate_plan} · {line_label(key.occupancy, key.nights)}"


# ─── 공통 모양(change_core)으로 ───


def encode_key(key: CellKey) -> dict:
    return dict(room=key.room, rate_plan=key.rate_plan, date=key.date, occupancy=key.occupancy, nights=key.nights)


def decode_key(data: Mapping) -> CellKey:
    return CellKey(str(data["room"]), str(data["rate_plan"]), iso_day(data["date"]),
                   str(data.get("occupancy") or ""), int(data["nights"]))


def decode_target_key(data: Mapping) -> CellKey:
    """목표 값 표의 칸 — 인원 조합 · 박수를 적지 않았거나 null 이면 None(줄이 하나뿐일 때 계산이 채운다). `""` 는 인원 무관이다."""
    occupancy, nights = data.get("occupancy"), data.get("nights")
    return CellKey(str(data["room"]), str(data["rate_plan"]), iso_day(data["date"]),
                   None if occupancy is None else str(occupancy), None if nights is None else int(nights))


def cell_item_key(key: CellKey) -> str:
    return item_key(encode_key(key))


def key_of_item(text: str) -> CellKey:
    return decode_key(key_fields(text))


def cell_state(key: CellKey, value: CellValue) -> ItemState:
    return ItemState(cell_name(key), value.state, {name: getattr(value, name) for name in FIELDS})


def value_of(state: ItemState) -> CellValue:
    return CellValue(*(state.fields.get(name) for name in FIELDS), state.state)


def new_cell_state(snapshot: Snapshot, key: CellKey) -> str:
    """ERP 가 새로 만드는 칸의 판매 상태 — 판매 가능, 그날 지속 마감(요금제 마감 · 객실 전체 마감)이 덮으면 마감(ERP `protect_price_cells`).
    셀 창에서 칸마다 마감한 날은 덮지 않는다. 날짜별 변경([선택 날짜 가격 수정])과 시즌 창이 같은 규칙이다."""
    return "closed" if (key.room, key.rate_plan, key.date) in snapshot.closures else "open"


def as_read(cells: Mapping[CellKey, CellValue]) -> dict[CellKey, CellValue]:
    """칸들 → ERP 의 [선택 날짜 가격 수정] 화면이 보일 모양. 화면은 판매 상태를 칸마다가 아니라 (객실, 요금제, 날)마다 하나로 보인다 —
    가격 있는 칸의 상태가 하나가 아니면(또는 이미 섞였으면) 그날 그 요금제의 칸은 모두 「인원·박수별 상태 다름」(mixed)으로 읽힌다.
    저장 뒤에 무엇을 읽을지 예상할 때 쓴다(지속 마감인 날은 칸이 모두 마감이라 섞이지 않는다)."""
    states: dict[tuple[str, str, str], set[str]] = {}
    for key, value in cells.items():
        if value.state != "missing":
            states.setdefault((key.room, key.rate_plan, key.date), set()).add(value.state)
    mixed = {day for day, found in states.items() if len(found) > 1 or "mixed" in found}
    return {key: CellValue(value.sell, value.list, value.supply, "mixed")
            if value.state != "missing" and (key.room, key.rate_plan, key.date) in mixed else value for key, value in cells.items()}


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
        hotel=encode_hotel(snapshot.hotel, snapshot.hotel_id), offer=snapshot.offer, currency=snapshot.currency,
        read_at=snapshot.read_at,
        cells=[dict(encode_key(key), **encode_value(value)) for key, value in sorted(snapshot.cells.items())],
        reserved=[dict(room=room, date=day) for room, day in sorted(snapshot.reserved)],
        pairs=[dict(room=room, rate_plan=plan) for room, plan in sorted(snapshot.pairs)],
        room_names=[dict(room=room, drawer=drawer) for room, drawer in sorted(snapshot.room_names.items())],
        no_sale=[dict(room=room, date=day) for room, day in sorted(snapshot.no_sale)],
        dates=list(snapshot.dates),
        row_labels=[dict(occupancy=key, label=label) for key, label in sorted(snapshot.row_labels.items())],
        closures=[dict(room=room, rate_plan=plan, date=day) for room, plan, day in sorted(snapshot.closures)],
    )


def decode_snapshot(data: Mapping) -> Snapshot:
    cells = {}
    for item in data["cells"]:
        key = decode_key(item)
        if key in cells:
            raise ValueError(f"같은 칸이 두 번 있습니다: {encode_key(key)}")
        cells[key] = decode_value(item)
    hotel, hotel_id = decode_hotel(data["hotel"])
    return Snapshot(hotel, str(data["offer"]), str(data["currency"]).upper(), str(data["read_at"]),
                    cells, frozenset((str(item["room"]), iso_day(item["date"])) for item in data.get("reserved") or []),
                    frozenset((str(item["room"]), str(item["rate_plan"])) for item in data["pairs"]),
                    {str(item["room"]): str(item["drawer"]) for item in data.get("room_names") or []},
                    frozenset((str(item["room"]), iso_day(item["date"])) for item in data.get("no_sale") or []), hotel_id,
                    tuple(iso_day(day) for day in data.get("dates") or ()),
                    {str(item["occupancy"]): str(item["label"]) for item in data.get("row_labels") or []},
                    frozenset((str(item["room"]), str(item["rate_plan"]), iso_day(item["date"])) for item in data.get("closures") or []))


def encode_request(request: ChangeRequest | TargetTable) -> dict:
    if isinstance(request, TargetTable):
        return dict(kind="targets", hotel=encode_hotel(request.hotel, request.hotel_id), offer=request.offer,
                    sentence=request.sentence, from_sheet=request.from_sheet,
                    targets=[dict(key=encode_key(target.key), values={name: money_text(value) for name, value in
                                                                      target.values}) for target in request.targets])
    return dict(kind="change", hotel=encode_hotel(request.hotel, request.hotel_id), offer=request.offer,
                rooms=list(request.rooms),
                rate_plans=list(request.rate_plans), dates=list(request.dates), field=request.field,
                pairs=[dict(room=room, rate_plan=plan) for room, plan in request.pairs],
                operation=dict(kind=request.operation, value=money_text(request.value),
                               base_occupancy=request.base_occupancy),
                occupancies=list(request.occupancies), nights=list(request.nights),
                scale_child_surcharge=request.scale_child_surcharge, sentence=request.sentence)


def decode_request(data: Mapping) -> ChangeRequest | TargetTable:
    if data.get("kind") in ("sheet", "sheet_check"):
        raise ValueError("요금표 파일(kind sheet)은 sheet 명령으로 확인하고, 그 명령이 낸 파일(kind sheet_check)을 --request 로 줍니다")
    hotel, hotel_id = decode_hotel(data["hotel"])
    if data.get("kind") == "targets":
        return TargetTable(hotel, str(data["offer"]),
                           tuple(Target(decode_target_key(item["key"]), tuple((str(name), money(value)) for name, value in
                                                                      item["values"].items())) for item in data["targets"]),
                           str(data.get("sentence") or ""), hotel_id, bool(data.get("from_sheet")))
    operation = data["operation"]
    return ChangeRequest(
        hotel=hotel, hotel_id=hotel_id, offer=str(data["offer"]), rooms=tuple(data["rooms"]),
        rate_plans=tuple(data["rate_plans"]), dates=tuple(data["dates"]), operation=operation["kind"],
        value=money(operation.get("value")), base_occupancy=operation.get("base_occupancy"),
        scale_child_surcharge=bool(data.get("scale_child_surcharge", False)), sentence=str(data.get("sentence") or ""),
        field=str(data.get("field") or "sell"),
        pairs=tuple((item["room"], item["rate_plan"]) for item in data.get("pairs") or ()),
        occupancies=tuple(str(key) for key in data.get("occupancies") or ()),
        nights=tuple(int(n) for n in data.get("nights") or ()),
    )


def request_range(data: Mapping) -> ReadRange:
    """요청 파일(읽을 범위 `kind: range` · 바꾸기 요청 · 목표 값 표) → 읽을 범위. 객실과 요금제를 따로 주면 그 모든 짝이다."""
    if data.get("kind") != "range":
        request = decode_request(data)
        if isinstance(request, TargetTable):
            keys = [target.key for target in request.targets]
            pairs, dates = dict.fromkeys((key.room, key.rate_plan) for key in keys), sorted({key.date for key in keys})
        else:
            pairs = request.pairs or tuple((room, plan) for room in request.rooms for plan in request.rate_plans)
            dates = request.dates
        return ReadRange(request.hotel, request.hotel_id, request.offer, tuple(pairs), tuple(dates))
    hotel, hotel_id = decode_hotel(data["hotel"])
    pairs = tuple((str(item["room"]), str(item["rate_plan"])) for item in data.get("pairs") or ())
    pairs = pairs or tuple((str(room), str(plan)) for room in data.get("rooms") or () for plan in data.get("rate_plans") or ())
    if len(set(pairs)) != len(pairs):
        raise ValueError("같은 객실·요금제 쌍이 두 번 있습니다")
    return ReadRange(hotel, hotel_id, str(data["offer"]), pairs, tuple(str(day) for day in data.get("dates") or ()))


def encode_change(change: CellChange) -> dict:
    return dict(key=encode_key(change.key), before=encode_value(change.before), after=encode_value(change.after),
                marks=list(change.marks), verdict=change.verdict, choice=change.choice, list_follow=money_text(change.list_follow),
                said=change.said)


def decode_change(data: Mapping) -> CellChange:
    return CellChange(decode_key(data["key"]), decode_value(data["before"]), decode_value(data.get("after")),
                      tuple(data.get("marks") or ()), data.get("verdict"), data.get("choice"), money(data.get("list_follow")),
                      data.get("said"))


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


def encode_gap(gap: Gap) -> dict:
    return dict(kind=gap.kind, room=gap.room, rate_plan=gap.rate_plan, occupancy=gap.occupancy, nights=gap.nights,
                dates=list(gap.dates), lines=list(gap.lines))


def decode_gap(data: Mapping) -> Gap:
    return Gap(str(data["kind"]), str(data["room"]), str(data["rate_plan"]),
               None if data.get("occupancy") is None else str(data["occupancy"]),
               None if data.get("nights") is None else int(data["nights"]),
               tuple(iso_day(day) for day in data.get("dates") or ()), tuple(int(no) for no in data.get("lines") or ()))


def encode_plan(plan: Plan) -> dict:
    return dict(request=encode_request(plan.request), currency=plan.currency, read_at=plan.read_at,
                changes=[encode_change(change) for change in plan.changes],
                skipped=[dict(key=encode_key(item.key), reason=item.reason) for item in plan.skipped],
                empty_pairs=[dict(room=room, rate_plan=plan_name) for room, plan_name in plan.empty_pairs],
                absent_pairs=[dict(room=room, rate_plan=plan_name) for room, plan_name in plan.absent_pairs],
                no_sale=[dict(room=room, rate_plan=plan_name, date=day) for room, plan_name, day in plan.no_sale],
                coverage=[encode_gap(gap) for gap in plan.coverage],
                tiers=[dict(encode_key(key), sell=money_text(sell)) for key, sell in sorted(plan.tiers.items())],
                above_one_night_before=plan.above_one_night_before,
                unused=[encode_unused(item) for item in plan.unused])


def encode_unused(item: UnusedChoice) -> dict:
    """쓰지 않는 고름 하나 — 계산 파일(plan.json)과 장부(결과 페이지의 「고르신 빨간 줄」)가 같은 모양으로 둔다."""
    return dict(rule=item.rule, choice=item.choice, said=item.said, why=item.why, words=item.words,
                cells=[encode_key(key) for key in item.cells])


def decode_unused(item: Mapping) -> UnusedChoice:
    return UnusedChoice(str(item["rule"]), str(item["choice"]), str(item.get("said") or ""), str(item["why"]), str(item["words"]),
                        tuple(decode_key(key) for key in item.get("cells") or ()))


def decode_plan(data: Mapping) -> Plan:
    return Plan(decode_request(data["request"]), str(data["currency"]).upper(), str(data["read_at"]),
                tuple(decode_change(item) for item in data["changes"]),
                tuple(Skipped(decode_key(item["key"]), str(item["reason"])) for item in data.get("skipped") or ()),
                tuple((str(item["room"]), str(item["rate_plan"])) for item in data.get("empty_pairs") or ()),
                tuple((str(item["room"]), str(item["rate_plan"])) for item in data.get("absent_pairs") or ()),
                tuple((str(item["room"]), str(item["rate_plan"]), iso_day(item["date"])) for item in data.get("no_sale") or ()),
                tuple(decode_gap(item) for item in data.get("coverage") or ()),
                {decode_key(item): money(item["sell"]) for item in data.get("tiers") or ()},
                int(data.get("above_one_night_before") or 0),
                tuple(decode_unused(item) for item in data.get("unused") or ()))
