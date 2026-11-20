"""price_sheet.py — 새 요금표로 날짜별 가격을 맞추는 길(결정 32 의 (나)): 요금표 파일 → 셈한 값 → 칸마다 목표 값 → 기존 계산.

요금표 파일(`kind: sheet`)은 도우미가 종이 요금표에서 숫자만 옮겨 적은 것이다. 줄 하나 = 객실 · 요금제 · 기간(여럿, 요일은 골라서)
이고, 그 안에 인원 조합 · 박수마다 값(판매가, 골라서 정가 · 공급 원가)이 있다. 값은 숫자이거나, 같은 줄의 다른 인원 · 박수 값에
금액이나 퍼센트를 더한 것이다("성인 추가 +60", "아동 +30", "3박 이상 −10%"). 셈은 이 모듈이 하고, 반올림은 기존 계산과 같은
통화 규칙(`round_money`)이다.

    decode_sheet(data)                     → Sheet        모양 확인 — 기간 · 요일 · 값 · 가리킴
    line_figures(line, currency)           → 인원 · 박수 → 필드 → Figure(값과 셈)   없는 줄을 가리키거나 고리면 이름을 대고 거절
    expand(lines, currency)                → CellKey → SheetCell   날짜마다 칸으로. 두 줄이 한 칸에 다른 값을 주면 두 줄을 대고 거절
    SheetCheck(sheet, hotel_pairs, part)   읽기 전에 알 수 있는 것 — 호텔에 없는 · 요금표에 없는 객실 · 요금제, 읽을 범위, 페이지 작업 수
    plan_sheet(snapshot, check)            → Plan         목표 값 표로 기존 계산(plan_targets)에 넘기고, 넣지 않는 것(Gap)을 단다

읽을 범위는 요금표(고른 부분)의 객실 · 요금제 가운데 호텔에 있는 것 × 첫 날부터 끝 날까지 모든 날이다. 요금표가 비운 날도 읽어야
「요금표에 없는 칸」을 빠짐없이 댈 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from functools import cached_property
from typing import Iterable, Mapping

from change_core.chrome import fmt_money
from change_core.money import money, money_text, round_money
from price_browser import PAGE_KEEPS, read_calls, reading_size, reserved_probes, too_big
from price_model import (
    FIELD_LABELS, FIELDS, GAP_KINDS, WEEKDAYS, CellKey, Gap, Plan, ReadRange, Snapshot, Target, TargetTable,
    decode_hotel, encode_gap, encode_hotel, hotel_label, iso_day, line_label, occupancy_label, occupancy_order, same_hotel,
)
from price_plan import PlanError, day_runs, matched_rows, plan_targets


@dataclass(frozen=True)
class Period:
    """기간 하나 — 시작일 ~ 종료일(둘 다 포함), 요일을 고르면 그 요일만. 요일은 「월화수목금토일」 글자."""
    first: str
    last: str
    weekdays: tuple[str, ...] = ()

    def days(self) -> list[str]:
        start, end = date.fromisoformat(self.first), date.fromisoformat(self.last)
        wanted = {WEEKDAYS.index(day) for day in self.weekdays} if self.weekdays else set(range(7))
        return [(start + timedelta(days=n)).isoformat() for n in range((end - start).days + 1)
                if (start + timedelta(days=n)).weekday() in wanted]


@dataclass(frozen=True)
class Ref:
    """같은 줄의 다른 인원 · 박수 값(같은 필드)에서 셈한 값 — 금액을 더하거나(`add`) 퍼센트만큼 바꾼다(`percent`)."""
    occupancy: str
    nights: int
    add: Decimal | None = None
    percent: Decimal | None = None


@dataclass(frozen=True)
class SheetRow:
    """줄 안의 인원 조합 · 박수 하나와 그 값들(필드 → 숫자 또는 Ref). 판매가는 반드시 있다."""
    occupancy: str
    nights: int
    values: tuple[tuple[str, Decimal | Ref], ...]


@dataclass(frozen=True)
class SheetLine:
    no: int                              # 파일의 차례(1 부터) — 담당자 · 도우미가 줄을 이 번호로 부른다
    room: str
    rate_plan: str
    season: str
    periods: tuple[Period, ...]
    rows: tuple[SheetRow, ...]

    @cached_property
    def days(self) -> tuple[str, ...]:
        return tuple(sorted({day for period in self.periods for day in period.days()}))


@dataclass(frozen=True)
class Sheet:
    hotel: str
    hotel_id: str
    offer: str
    currency: str
    lines: tuple[SheetLine, ...]
    sentence: str = ""


@dataclass(frozen=True)
class Figure:
    """셈한 값 하나. `formula` 는 셈한 값이면 그 셈("성인 2 · 1박 이상 240.00 + 60"), 옮긴 숫자면 None."""
    value: Decimal
    formula: str | None = None


@dataclass(frozen=True)
class SheetCell:
    """칸 하나의 목표 값과 그 값을 준 줄."""
    values: tuple[tuple[str, Decimal], ...]
    line: int


@dataclass(frozen=True)
class Part:
    """요금표의 한 부분만 할 때 — 객실(비면 전부)과 날짜 창(비면 전부). 시즌 하나는 그 시즌의 날짜 창이다."""
    rooms: tuple[str, ...] = ()
    first: str | None = None
    last: str | None = None

    @property
    def whole(self) -> bool:
        return not (self.rooms or self.first or self.last)


# ─── 이름 ───


def _short(day: str) -> str:
    return f"{int(day[5:7])}/{int(day[8:10])}"


def period_label(period: Period) -> str:
    span = _short(period.first) if period.first == period.last else f"{_short(period.first)} ~ {_short(period.last)}"
    return f"{span} {'·'.join(period.weekdays)}" if period.weekdays else span


def periods_label(periods: Iterable[Period]) -> str:
    return ", ".join(period_label(period) for period in periods)


def line_name(line: SheetLine) -> str:
    season = f" · {line.season}" if line.season else ""
    return f"{line.no}번째 줄({line.room} · {line.rate_plan}{season} · {periods_label(line.periods)})"


def _value_name(occupancy: str, nights: int, name: str) -> str:
    return f"{line_label(occupancy, nights)} {FIELD_LABELS[name]}"


def _amount(value: Decimal) -> str:
    return f"{'+' if value >= 0 else '-'} {abs(value).normalize():f}"


# ─── 파일 ↔ 모양 ───


def _text(data: Mapping, name: str, where: str) -> str:
    value = str(data.get(name) or "").strip()
    if not value:
        raise ValueError(f"{where}: `{name}` 이 비어 있습니다")
    return value


def _day(text, where: str) -> str:
    try:
        return iso_day(str(text))
    except ValueError:
        raise ValueError(f"{where}: 날짜는 ISO 형식(2027-07-01)으로 적습니다 — {text!r}") from None


def _period(data: Mapping, where: str) -> Period:
    first, last = _day(data.get("from"), where), _day(data.get("to"), where)
    if first > last:
        raise ValueError(f"{where}: 기간의 시작일({first})이 종료일({last})보다 뒤입니다")
    weekdays = tuple(str(day) for day in data.get("weekdays") or ())
    unknown = [day for day in weekdays if day not in WEEKDAYS or len(day) != 1]
    if unknown or len(set(weekdays)) != len(weekdays):
        raise ValueError(f"{where}: 요일은 「월 화 수 목 금 토 일」 가운데 한 글자씩, 한 번씩 적습니다 — {list(weekdays)}")
    period = Period(first, last, tuple(sorted(weekdays, key=WEEKDAYS.index)))
    if not period.days():
        raise ValueError(f"{where}: {first} ~ {last} 에 고른 요일({'·'.join(period.weekdays)})이 하루도 없습니다")
    return period


def _nights(value, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value).strip().isdigit() or int(value) < 1:
        raise ValueError(f"{where}: 박수(nights)는 1 이상의 정수입니다(1박 이상 1, 3박 이상 3) — {value!r}")
    return int(value)


def _value(data, occupancy: str, nights: int, where: str) -> Decimal | Ref:
    if not isinstance(data, Mapping):
        if isinstance(data, (bool, float)) or data is None:
            raise ValueError(f"{where}: 금액은 글자 숫자(\"240\")로 적습니다 — {data!r}")
        return money(data)
    source = data.get("from")
    if not isinstance(source, Mapping) or not source or not set(source) <= {"occupancy", "nights"}:
        raise ValueError(f"{where}: 가리키는 값은 `from` 에 인원 조합(occupancy) · 박수(nights) 가운데 하나 이상을 적습니다")
    if (data.get("add") is None) == (data.get("percent") is None) or not set(data) <= {"from", "add", "percent"}:
        raise ValueError(f"{where}: 가리키는 값은 `add`(금액) 또는 `percent`(퍼센트) 하나를 적습니다")
    return Ref(str(source["occupancy"]) if "occupancy" in source else occupancy,
               _nights(source["nights"], where) if "nights" in source else nights,
               money(data.get("add")), money(data.get("percent")))


def _row(data: Mapping, where: str) -> SheetRow:
    if "occupancy" not in data or data["occupancy"] is None:
        raise ValueError(f"{where}: 인원 조합(occupancy)을 적습니다 — 성인 2 는 \"A2\", 인원 무관은 \"\"")
    occupancy, nights = str(data["occupancy"]).strip(), _nights(data.get("nights"), where)
    where = f"{where} {line_label(occupancy, nights)}"
    extra = set(data) - {"occupancy", "nights", *FIELDS}
    if extra:
        raise ValueError(f"{where}: 모르는 칸 {sorted(extra)} — 값은 sell · list · supply 만 적습니다")
    if data.get("sell") is None:
        raise ValueError(f"{where}: 판매가(sell)가 없습니다")
    return SheetRow(occupancy, nights, tuple((name, _value(data[name], occupancy, nights, f"{where} {FIELD_LABELS[name]}"))
                                             for name in FIELDS if data.get(name) is not None))


def _line(data: Mapping, no: int) -> SheetLine:
    where = f"{no}번째 줄"
    room, plan = _text(data, "room", where), _text(data, "rate_plan", where)
    periods = tuple(_period(item, f"{where}({room} · {plan})") for item in data.get("periods") or ())
    if not periods:
        raise ValueError(f"{where}({room} · {plan}): 기간(periods)이 없습니다")
    line = SheetLine(no, room, plan, str(data.get("season") or "").strip(), periods, ())
    rows = tuple(_row(item, line_name(line)) for item in data.get("rows") or ())
    if not rows:
        raise ValueError(f"{line_name(line)}: 인원 · 박수마다의 값(rows)이 없습니다")
    seen = [(row.occupancy, row.nights) for row in rows]
    twice = sorted({line_label(*item) for item in seen if seen.count(item) > 1})
    if twice:
        raise ValueError(f"{line_name(line)}: 같은 인원 · 박수가 두 번 있습니다 — {', '.join(twice)}")
    return replace(line, rows=rows)


def decode_sheet(data: Mapping) -> Sheet:
    if data.get("kind") != "sheet":
        raise ValueError("요금표 파일은 \"kind\": \"sheet\" 입니다")
    hotel, hotel_id = decode_hotel(data.get("hotel"))
    currency = str(data.get("currency") or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("요금표의 통화(currency)를 세 글자로 적습니다(USD · KRW …) — 요금표에 적힌 통화 그대로")
    lines = tuple(_line(item, no) for no, item in enumerate(data.get("lines") or (), 1))
    if not lines:
        raise ValueError("요금표에 줄(lines)이 없습니다")
    return Sheet(hotel, hotel_id, _text(data, "offer", "요금표"), currency, lines, str(data.get("sentence") or ""))


def _encode_value(value: Decimal | Ref):
    if not isinstance(value, Ref):
        return money_text(value)
    out = {"from": dict(occupancy=value.occupancy, nights=value.nights)}
    return dict(out, add=money_text(value.add)) if value.add is not None else dict(out, percent=money_text(value.percent))


def encode_sheet(sheet: Sheet) -> dict:
    return dict(kind="sheet", hotel=encode_hotel(sheet.hotel, sheet.hotel_id), offer=sheet.offer, currency=sheet.currency,
                sentence=sheet.sentence,
                lines=[dict(room=line.room, rate_plan=line.rate_plan, season=line.season,
                            periods=[dict({"from": period.first, "to": period.last},
                                          **({"weekdays": list(period.weekdays)} if period.weekdays else {}))
                                     for period in line.periods],
                            rows=[dict(occupancy=row.occupancy, nights=row.nights,
                                       **{name: _encode_value(value) for name, value in row.values}) for row in line.rows])
                       for line in sheet.lines])


# ─── 셈 ───


def line_figures(line: SheetLine, currency: str) -> dict[tuple[str, int], dict[str, Figure]]:
    """줄의 인원 · 박수마다 필드 → Figure. 가리키는 값은 같은 줄 · 같은 필드에서 셈하고 통화 규칙으로 반올림한다.

    가리킨 인원 · 박수가 그 줄에 없거나 그 필드를 적지 않았으면, 또는 서로를 가리키면(고리) 이름을 대고 거절한다."""
    rows = {(row.occupancy, row.nights): dict(row.values) for row in line.rows}
    done: dict[tuple[str, int, str], Figure] = {}

    def figure(at: tuple[str, int], name: str, chain: tuple[tuple[str, int], ...]) -> Figure:
        if (*at, name) in done:
            return done[(*at, name)]
        if at in chain:
            loop = " → ".join(line_label(*item) for item in (*chain[chain.index(at):], at))
            raise PlanError(f"{line_name(line)} 의 {FIELD_LABELS[name]}가 서로를 가리킵니다(고리): {loop}")
        value = rows[at][name]
        if isinstance(value, Ref):
            source = (value.occupancy, value.nights)
            if name not in rows.get(source, {}):
                raise PlanError(f"{line_name(line)} 의 {_value_name(*at, name)}가 가리키는 {_value_name(*source, name)}가 "
                                "그 줄에 없습니다 — 요금표의 그 줄에 그 값을 옮겨 적거나 숫자로 적습니다")
            base = figure(source, name, (*chain, at)).value
            if value.add is not None:
                result, how = round_money(base + value.add, currency), _amount(value.add)
            else:
                result, how = round_money(base * (100 + value.percent) / 100, currency), f"{_amount(value.percent)}%"
            found = Figure(result, f"{line_label(*source)} {fmt_money(base, currency)} {how}")
        else:
            found = Figure(round_money(value, currency))
        done[(*at, name)] = found
        return found

    return {at: {name: figure(at, name, ()) for name in values} for at, values in rows.items()}


def expand(lines: Iterable[SheetLine], currency: str) -> dict[CellKey, SheetCell]:
    """줄들을 날짜마다 칸으로 펼친다. 두 줄이 한 칸에 다른 값(필드와 값이 하나라도 다름)을 주면 두 줄을 대고 거절한다."""
    cells: dict[CellKey, SheetCell] = {}
    clashes: list[tuple[CellKey, SheetCell, SheetCell]] = []
    names: dict[int, SheetLine] = {}
    for line in lines:
        names[line.no] = line
        for (occupancy, nights), figures in line_figures(line, currency).items():
            values = tuple((name, figures[name].value) for name in FIELDS if name in figures)
            for day in line.days:
                key, cell = CellKey(line.room, line.rate_plan, day, occupancy, nights), SheetCell(values, line.no)
                other = cells.setdefault(key, cell)
                if other.values != values:
                    clashes.append((key, other, cell))
    if clashes:
        key, first, second = clashes[0]
        shown = " / ".join(" · ".join(f"{FIELD_LABELS[name]} {value}" for name, value in cell.values) for cell in (first, second))
        more = f" (이런 칸이 모두 {len(clashes):,}개)" if len(clashes) > 1 else ""
        raise PlanError(f"{line_name(names[first.line])} 과 {line_name(names[second.line])} 이 {key.date} · "
                        f"{line_label(key.occupancy, key.nights)} 칸에 다른 값을 줍니다({shown}){more} — "
                        "요금표에서 어느 값이 맞는지 담당자에게 묻습니다")
    return cells


# ─── 읽기 전 확인 ───


def _clip(line: SheetLine, part: Part) -> SheetLine | None:
    if part.rooms and line.room not in part.rooms:
        return None
    periods = []
    for period in line.periods:
        clipped = replace(period, first=max(period.first, part.first or period.first),
                          last=min(period.last, part.last or period.last))
        if clipped.first <= clipped.last and clipped.days():
            periods.append(clipped)
    return replace(line, periods=tuple(periods)) if periods else None


@dataclass(frozen=True)
class SheetCheck:
    """요금표 + 호텔의 객실 · 요금제(look 의 pairs) + 고른 부분 → 읽기 전에 알 수 있는 것. 만들 때 요금표 전체의 셈과 펼침을
    한 번 해 본다(없는 값을 가리킴 · 고리 · 두 줄이 한 칸에 다른 값이면 여기서 거절)."""
    sheet: Sheet
    hotel_pairs: tuple[tuple[str, str], ...]
    part: Part = Part()

    def __post_init__(self):
        expand(self.sheet.lines, self.sheet.currency)
        rooms = {line.room for line in self.sheet.lines}
        unknown = [room for room in self.part.rooms if room not in rooms]
        if unknown:
            raise PlanError(f"고른 객실이 요금표에 없습니다: {', '.join(unknown)} (요금표의 객실: {', '.join(sorted(rooms))})")
        if self.part.first and self.part.last and self.part.first > self.part.last:
            raise PlanError(f"고른 날짜 창의 시작일({self.part.first})이 종료일({self.part.last})보다 뒤입니다")
        if not self.selected:
            raise PlanError("고른 부분에 요금표 줄이 하나도 없습니다 — 객실 · 날짜 창을 다시 봅니다")

    @cached_property
    def selected(self) -> tuple[SheetLine, ...]:
        """고른 부분의 줄(날짜 창으로 기간을 자른 것) — 호텔에 없는 객실 · 요금제의 줄도 든다."""
        return tuple(line for line in (_clip(line, self.part) for line in self.sheet.lines) if line is not None)

    @cached_property
    def lines(self) -> tuple[SheetLine, ...]:
        """넣을 줄 — 고른 부분 가운데 호텔에 있는 객실 · 요금제의 줄."""
        known = set(self.hotel_pairs)
        return tuple(line for line in self.selected if (line.room, line.rate_plan) in known)

    @cached_property
    def cells(self) -> dict[CellKey, SheetCell]:
        return expand(self.lines, self.sheet.currency)

    @cached_property
    def range(self) -> ReadRange | None:
        """읽을 범위 — 넣을 줄의 객실 · 요금제 × 첫 날부터 끝 날까지 모든 날. 넣을 줄이 없으면 None."""
        if not self.lines:
            return None
        days = [day for line in self.lines for day in line.days]
        start, end = date.fromisoformat(min(days)), date.fromisoformat(max(days))
        return ReadRange(self.sheet.hotel, self.sheet.hotel_id, self.sheet.offer,
                         tuple(dict.fromkeys((line.room, line.rate_plan) for line in self.lines)),
                         tuple((start + timedelta(days=n)).isoformat() for n in range((end - start).days + 1)))

    @cached_property
    def reads(self) -> dict:
        """읽기 한 번의 페이지 작업 수(`reading_size`) — readPair 는 객실 · 요금제마다 READ_SPAN 일씩, readReserved 는 첫 물음
        (ERP_MAX_DAYS 일씩, 숨은 줄이 있으면 쪼개져 늘어난다)."""
        if self.range is None:
            return dict(readPair=0, readReserved=0, limit=PAGE_KEEPS, fits=False)
        hotel = encode_hotel(self.sheet.hotel, self.sheet.hotel_id)
        return reading_size(dict(pairs=read_calls(hotel, self.sheet.offer, self.range.pairs, self.range.dates),
                                 reserved=reserved_probes(hotel, self.sheet.offer, self.range.pairs, self.range.dates)))

    def fitting_range(self) -> ReadRange:
        """읽을 범위 — 넣을 줄이 없거나 읽기 한 번에 들지 않으면 까닭과 한도를 대고 거절한다."""
        if self.range is None:
            raise PlanError("넣을 요금표 줄이 없습니다 — 고른 부분의 객실 · 요금제가 모두 호텔(이 오퍼)에 없습니다")
        reads = self.reads
        if not reads["fits"]:
            raise PlanError(f"이 요금표(부분)는 읽기 한 번에 들지 않습니다 — {too_big(reads)}. 객실(--room)이나 날짜 창(--from · --to)으로 "
                            "나눠 sheet 를 다시 합니다")
        return self.range

    @cached_property
    def gaps(self) -> tuple[Gap, ...]:
        """읽기 전에 알 수 있는 넣지 않는 것 — 호텔에 없는 객실 · 요금제(고른 부분의 줄), 요금표에 없는 객실 · 요금제(요금표 전체 기준)."""
        known = set(self.hotel_pairs)
        unknown: dict[tuple[str, str], list[int]] = {}
        for line in self.selected:
            if (line.room, line.rate_plan) not in known:
                unknown.setdefault((line.room, line.rate_plan), []).append(line.no)
        named = {(line.room, line.rate_plan) for line in self.sheet.lines}
        return (tuple(Gap("unknown", room, plan, lines=tuple(nos)) for (room, plan), nos in unknown.items())
                + tuple(Gap("unnamed", room, plan) for room, plan in self.hotel_pairs if (room, plan) not in named))


def decode_check(data: Mapping) -> SheetCheck:
    """`sheet` 명령이 낸 파일(kind sheet_check) — 요금표 · 호텔의 객실 · 요금제 · 고른 부분만 읽고 나머지는 다시 셈한다."""
    if data.get("kind") != "sheet_check":
        raise ValueError("sheet 명령이 낸 파일(\"kind\": \"sheet_check\")이 아닙니다")
    part = data.get("part") or {}
    return SheetCheck(decode_sheet(data["sheet"]),
                      tuple((str(item["room"]), str(item["rate_plan"])) for item in data["hotel_pairs"]),
                      Part(tuple(str(room) for room in part.get("rooms") or ()),
                           None if not part.get("from") else iso_day(part["from"]),
                           None if not part.get("to") else iso_day(part["to"])))


def encode_check(check: SheetCheck) -> dict:
    scope = check.range
    return dict(kind="sheet_check", sheet=encode_sheet(check.sheet),
                hotel_pairs=[dict(room=room, rate_plan=plan) for room, plan in check.hotel_pairs],
                part=dict(rooms=list(check.part.rooms), **{"from": check.part.first, "to": check.part.last}),
                lines=len(check.selected), cells=len(check.cells), currency=check.sheet.currency,
                gaps=[encode_gap(gap) for gap in check.gaps],
                range=None if scope is None else dict(pairs=[dict(room=room, rate_plan=plan) for room, plan in scope.pairs],
                                                      first=scope.dates[0], last=scope.dates[-1], days=len(scope.dates)),
                reads=check.reads)


# ─── 미리보기 계산 ───


def _group(keys: Iterable[CellKey]) -> dict[tuple[str, str, str, int], list[str]]:
    groups: dict[tuple[str, str, str, int], list[str]] = {}
    for key in keys:
        groups.setdefault((key.room, key.rate_plan, key.occupancy, key.nights), []).append(key.date)
    return groups


def _order(item: tuple[str, str, str, int]) -> tuple:
    return item[0], item[1], occupancy_order(item[2]), item[3]


def matched_cells(snapshot: Snapshot, check: SheetCheck) -> dict[CellKey, tuple[CellKey, SheetCell]]:
    """요금표의 칸을 읽은 줄에 맞춘다 → 읽은 줄의 칸 키 → (요금표의 칸 키 그대로, 값). 요금표가 성인 · 아동 수만 적은 인원 조합
    (`A2C1`, "성인 2 + 아동 1")은 그 객실 · 요금제의 그 수의 줄(`A2C1_CHD`)이다. 그 줄이 여럿(아동 밴드가 여럿)이면 아무것도 셈하지
    않고 고를 줄을 대며 거절한다(ChooseRows). 맞는 줄이 없으면 적은 그대로 둔다(「읽은 값에 없는 인원 조합」). 두 요금표 칸이 같은
    줄을 가리키는데 값이 다르면 두 줄을 대고 거절한다."""
    found = matched_rows(snapshot, [(line.room, line.rate_plan, row.occupancy) for line in check.lines for row in line.rows],
                         "요금표 파일의 그 인원 조합에 고른 키를 적어 sheet 와 plan 을 다시 합니다(sheet.md 「요금표를 고칠 때」)")
    cells: dict[CellKey, tuple[CellKey, SheetCell]] = {}
    for key, cell in check.cells.items():
        rows = found[(key.room, key.rate_plan, key.occupancy)]
        matched = replace(key, occupancy=rows[0]) if len(rows) == 1 else key
        first, other = cells.setdefault(matched, (key, cell))
        if other.values != cell.values:
            raise PlanError(f"{other.line}번째 줄의 {occupancy_label(first.occupancy)}({first.occupancy})와 {cell.line}번째 줄의 "
                            f"{occupancy_label(key.occupancy)}({key.occupancy})가 ERP 의 같은 줄 {snapshot.row_label(matched.occupancy)} 을 "
                            f"가리키는데 {matched.date} 값이 다릅니다 — 요금표 파일에서 하나를 고칩니다")
    return cells


def plan_sheet(snapshot: Snapshot, check: SheetCheck) -> Plan:
    """요금표 → 미리보기. 펼친 칸 가운데 읽은 값에서 그 객실 · 요금제의 줄로 나온 인원 · 박수이고 판매일이 있는 날의 칸만 목표
    값 표로 기존 계산(`plan_targets`)에 넘긴다 — 지금 값과 다른 칸만 바뀌고, 규칙 · 빨간 줄 · 저장 단계는 다른 변경과 같다.
    넣지 않는 것은 모두 `coverage` 에 단다."""
    sheet, scope = check.sheet, check.fitting_range()
    if not same_hotel(snapshot.hotel, snapshot.hotel_id, sheet.hotel, sheet.hotel_id) or snapshot.offer != sheet.offer:
        raise PlanError(f"읽은 값은 {hotel_label(snapshot.hotel, snapshot.hotel_id)} · {snapshot.offer} 것이고, 요금표는 "
                        f"{hotel_label(sheet.hotel, sheet.hotel_id)} · {sheet.offer} 입니다")
    if snapshot.currency != sheet.currency:
        raise PlanError(f"요금표의 통화는 {sheet.currency} 인데 ERP 의 이 오퍼는 {snapshot.currency} 입니다 — 요금표의 통화를 다시 보고, "
                        "다르면 담당자에게 묻습니다(통화를 바꿔 셈하지 않습니다)")
    unread = [f"{room} · {plan}" for room, plan in scope.pairs if (room, plan) not in snapshot.pairs]
    if unread:
        raise PlanError(f"읽지 않은 객실·요금제가 있습니다: {', '.join(unread)}. read-calls --request 에 이 sheet 파일을 주어 읽습니다")
    gaps = sorted(set(scope.dates) - set(snapshot.dates))
    if gaps:
        raise PlanError(f"읽은 값에 없는 날짜: {', '.join(gaps[:5])}{' …' if len(gaps) > 5 else ''}. "
                        "read-calls --request 에 이 sheet 파일을 주어 읽습니다")
    shown = {(key.room, key.rate_plan, key.occupancy, key.nights) for key in snapshot.cells}
    cells = matched_cells(snapshot, check)
    targets = [Target(key, cell.values) for key, (_sheet_key, cell) in cells.items()
               if (key.room, key.rate_plan, key.occupancy, key.nights) in shown and (key.room, key.date) not in snapshot.no_sale]
    no_sale: dict[tuple[str, str], set] = {}
    for line in check.lines:
        no_sale.setdefault((line.room, line.rate_plan), set()).update(day for day in line.days if (line.room, day) in snapshot.no_sale)
    named = {(key.room, key.rate_plan, sheet_key.occupancy): key.occupancy for key, (sheet_key, _cell) in cells.items()}
    unseen: dict[tuple[str, str, str, int], tuple[set, set]] = {}
    for line in check.lines:
        for row in line.rows:
            at = (line.room, line.rate_plan, named.get((line.room, line.rate_plan, row.occupancy), row.occupancy), row.nights)
            if at not in shown:
                days, nos = unseen.setdefault(at, (set(), set()))
                days.update(line.days)
                nos.add(line.no)
    in_range, wanted = set(scope.dates), set(scope.pairs)
    untouched = _group(key for key, value in snapshot.cells.items()
                       if value.state != "missing" and (key.room, key.rate_plan) in wanted and key.date in in_range
                       and key not in cells)
    coverage = (tuple(Gap("untouched", *at[:2], at[2], at[3], tuple(sorted(days))) for at, days in sorted(untouched.items(), key=lambda i: _order(i[0])))
                + tuple(Gap("unseen", *at[:2], at[2], at[3], tuple(sorted(days)), tuple(sorted(nos)))
                        for at, (days, nos) in sorted(unseen.items(), key=lambda i: _order(i[0])))
                + tuple(Gap("no_sale", room, plan, dates=tuple(sorted(days))) for (room, plan), days in no_sale.items() if days)
                + check.gaps)
    if not targets:
        counts = coverage_counts(coverage)
        raise PlanError(f"요금표에서 넣을 수 있는 칸이 없습니다 — 읽은 값에 없는 인원 조합 · 박수의 칸 {counts['unseen']:,}개, "
                        f"판매일 없는 날 {counts['no_sale']:,}일뿐입니다")
    table = TargetTable(sheet.hotel, sheet.offer, tuple(targets), sheet.sentence, sheet.hotel_id, from_sheet=True)
    return replace(plan_targets(snapshot, table), coverage=coverage)


def coverage_counts(gaps: Iterable[Gap]) -> dict[str, int]:
    """종류마다의 수 — 요금표에 없는 칸 · 없는 인원 조합은 칸 수, 판매일 없는 날은 (객실 · 요금제, 날) 수, 객실 · 요금제는 그 수."""
    gaps = list(gaps)
    return {kind: sum(len(gap.dates) if kind in ("untouched", "unseen", "no_sale") else 1 for gap in gaps if gap.kind == kind)
            for kind in GAP_KINDS}


def runs_label(days: Iterable[str]) -> str:
    """날짜 → "1/4 ~ 1/7, 1/10" — 이어진 날끼리."""
    return ", ".join(_short(run[0]) if len(run) == 1 else f"{_short(run[0])} ~ {_short(run[-1])}" for run in day_runs(days))
