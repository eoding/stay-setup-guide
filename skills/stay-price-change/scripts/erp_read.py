"""erp_read.py — ERP 화면 조각(HTML) 두 가지를 읽어 Snapshot 을 만든다. 표준 라이브러리 `html.parser` 만 쓴다.

    parse_price_page(html)   [선택 날짜 가격 수정] 확인 단계 → 객실·요금제, 날짜별 상태, 인원·박수 줄마다 날짜별 기존 값
    parse_adjust_page(html)  [선택 날짜 가격 가감] 확인 단계 → 건너뛰는 칸 줄(날짜·객실·요금제·인원·박수·사유)과 숨긴 줄 수
    build_snapshot(...)      읽은 객실 × 요금제들(PairRead)과 가감 확인 단계를 합쳐 Snapshot — 예약 있는 날은 가감의 사유
                             "예약이 있는 날" 로 안다

객실 이름은 둘이다. 캘린더 칩은 객실의 표시 이름(오퍼별 표시명 → 객실 타입 이름 → 저장된 이름)을 보이고, 가격 수정
드로어는 판매 연결의 저장된 이름(흔히 「오퍼 · 객실」)을 보인다. 담당자는 칩의 이름으로 말하므로 Snapshot 은 칸을 칩의
이름으로 적고 드로어의 이름을 옆에 둔다(`room_names`). 가감 화면의 객실 이름은 이 짝으로 맞춘다 — 글자를 잘라 맞추지 않는다.

값은 표의 **칸 위치**로 열에 붙인다(기존 · 판매가 · 정가 · 공급 원가). 글자를 순서대로 읽으면 정가가 빈 줄에서
공급 원가가 정가 자리로 밀린다. 날짜 칸은 하루(`2026-07-01`) 또는 이어진 구간(`2026-07-01 ~ 2026-07-05 (5일)`)이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from html.parser import HTMLParser
from typing import Iterable

from change_core.money import money
from price_model import MISSING, CellKey, CellValue, Snapshot

VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"})
ABSENT = ("", "없음")
NO_PRICE = "가격 없음"
RESERVED_REASON = "예약이 있는 날"
ANY_PARTY = "인원 무관 단일가"
NOT_OPENED = " · 판매일 미개설"
DAY_STATES = {"가격 없음": "missing", "가격 판매 가능": "open", "판매가 확인 필요": "open",
              "요금제 마감": "closed", "객실 전체 마감": "closed"}
CLOSED_PREFIX = "기존 가격 "
DAY_LABEL = re.compile(r"^(\d{4}-\d{2}-\d{2})(?: ~ (\d{4}-\d{2}-\d{2}) \((\d+)일\))?$")


class ParseError(ValueError):
    """화면 조각이 기대한 모양이 아니다 — 읽은 값을 쓰지 않고 멈춘다."""


@dataclass
class Node:
    tag: str
    attrs: dict
    children: list

    def walk(self) -> Iterable["Node"]:
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.walk()

    def find_all(self, tag: str, **attrs) -> list["Node"]:
        return [node for node in self.walk() if node.tag == tag and all(
            node.attrs.get(name.replace("_", "-")) == value if value is not True else name.replace("_", "-") in node.attrs
            for name, value in attrs.items())]

    def kids(self, tag: str) -> list["Node"]:
        return [child for child in self.children if isinstance(child, Node) and child.tag == tag]

    def text(self) -> str:
        parts = []

        def collect(node):
            for child in node.children:
                if isinstance(child, str):
                    parts.append(child)
                elif child.tag not in ("style", "script"):
                    collect(child)

        collect(self)
        return " ".join("".join(parts).split())


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, [])
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {name: value if value is not None else "" for name, value in attrs}, [])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, {name: value or "" for name, value in attrs}, []))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(html: str) -> Node:
    builder = _Builder()
    builder.feed(html)
    builder.close()
    return builder.root


def expand_days(label: str) -> tuple[str, ...]:
    match = DAY_LABEL.match(label.strip())
    if match is None:
        raise ParseError(f"날짜 칸을 읽지 못했습니다: {label!r}")
    first, last, count = match.groups()
    if last is None:
        return (date.fromisoformat(first).isoformat(),)
    start, end = date.fromisoformat(first), date.fromisoformat(last)
    days = tuple((start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1))
    if len(days) != int(count):
        raise ParseError(f"구간의 날 수가 맞지 않습니다: {label!r}")
    return days


def _facts(root: Node) -> dict[str, str]:
    for card in root.find_all("section", data_stay_summary=True):
        for facts in card.find_all("dl"):
            return {dt.text(): dd.text() for dt, dd in zip(facts.kids("dt"), facts.kids("dd"))}
    raise ParseError("화면 머리의 오퍼·객실 칸을 찾지 못했습니다")


def _body_rows(table: Node) -> list[Node]:
    return [row for body in table.kids("tbody") for row in body.kids("tr")]


def _header(table: Node) -> list[str]:
    return [cell.text() for head in table.kids("thead") for row in head.kids("tr") for cell in row.kids("th")]


def day_state(label: str) -> str:
    text = label[:-len(NOT_OPENED)] if label.endswith(NOT_OPENED) else label
    if text in DAY_STATES:
        return DAY_STATES[text]
    if text.startswith(CLOSED_PREFIX):
        return "closed"
    raise ParseError(f"날짜의 가격·마감 상태를 모릅니다: {label!r}")


@dataclass(frozen=True)
class PriceRow:
    """`values` 는 날짜 → (판매가, 정가, 공급 원가). 가격 없는 날은 None. 정가·원가가 「없음」이면 그 자리가 None."""
    occupancy: str
    nights: int
    label: str
    values: dict[str, tuple | None]


@dataclass(frozen=True)
class PricePage:
    offer: str
    room: str
    rate_plan: str
    currency: str
    days: dict[str, str]
    rows: tuple[PriceRow, ...]


def _amount(text: str):
    return None if text in ABSENT else money(text)


def parse_price_page(html: str) -> PricePage:
    root = parse_html(html)
    tables = root.find_all("table", data_stay_rows="prices")
    if root.find_all("div", data_stay_screen="calendar-bulk") == [] or len(tables) != 1:
        raise ParseError("[선택 날짜 가격 수정] 확인 단계의 가격 표가 아닙니다")
    prices = tables[0]
    facts = _facts(root)
    heading = _header(prices)
    currency = re.search(r"\(([^)]+)\)", heading[1] if len(heading) > 1 else "")
    if currency is None:
        raise ParseError("가격 표 머리에서 통화를 찾지 못했습니다")

    status = next((table for table in root.find_all("table") if _header(table)[:2] == ["숙박일", "현재 가격·마감 상태"]),
                  None)
    if status is None:
        raise ParseError("날짜별 가격·마감 상태 표를 찾지 못했습니다")
    days = {}
    for row in _body_rows(status):
        cells = [cell.text() for cell in row.kids("td")]
        if len(cells) != 2:
            raise ParseError(f"날짜별 상태 줄의 칸이 둘이 아닙니다: {cells}")
        for day in expand_days(cells[0]):
            days[day] = cells[1]

    rows = []
    for body in prices.kids("tbody"):
        occupancy, nights = body.attrs.get("data-stay-occupancy-key"), body.attrs.get("data-stay-los-nights")
        if occupancy is None or not (nights or "").isdigit():
            raise ParseError("가격 표 줄에 인원 조합·박수 표식이 없습니다")
        head = body.find_all("th")
        values = {}
        for line in body.kids("tr"):
            if "data-stay-existing" not in line.attrs:
                continue
            cells = [cell.text() for cell in line.kids("td")]
            if len(cells) != 4:
                raise ParseError(f"기존 값 줄의 칸이 넷(기존·판매가·정가·공급 원가)이 아닙니다: {cells}")
            label, sell, list_price, supply = cells
            for day in expand_days(label):
                values[day] = None if sell == NO_PRICE else (money(sell), _amount(list_price), _amount(supply))
        if set(values) != set(days):
            raise ParseError(f"{occupancy or ANY_PARTY} · {nights}박 줄의 날짜가 상태 표의 날짜와 다릅니다")
        rows.append(PriceRow(occupancy, int(nights), head[0].text() if head else "", values))
    return PricePage(facts.get("오퍼", ""), facts.get("객실", ""), facts.get("요금제", ""), currency.group(1).strip(),
                     days, tuple(rows))


@dataclass(frozen=True)
class RejectedRow:
    days: tuple[str, ...]
    room: str
    rate_plan: str
    occupancy: str
    nights: int
    reason: str


@dataclass(frozen=True)
class AdjustPage:
    offer: str
    rejected: tuple[RejectedRow, ...]
    hidden: int


def occupancy_from_label(label: str) -> str:
    return "" if label == ANY_PARTY else label.split(" · ")[0]


def parse_adjust_page(html: str) -> AdjustPage:
    root = parse_html(html)
    if not root.find_all("div", data_calendar_adjust="confirm"):
        raise ParseError("[선택 날짜 가격 가감] 확인 단계가 아닙니다")
    facts = _facts(root)
    rejected, hidden = [], 0
    for card in root.find_all("section"):
        title = card.kids("h4")
        if not title or not title[0].text().startswith("건너뛰는 칸"):
            continue
        for table in card.find_all("table"):
            if _header(table) != ["숙박일", "객실", "요금제", "인원 조합", "박수", "사유"]:
                raise ParseError(f"건너뛰는 칸 표의 머리가 다릅니다: {_header(table)}")
            for row in _body_rows(table):
                cells = [cell.text() for cell in row.kids("td")]
                if len(cells) != 6:
                    raise ParseError(f"건너뛰는 칸 줄의 칸이 여섯이 아닙니다: {cells}")
                day, room, plan, occupancy, nights, reason = cells
                count = re.match(r"^(\d+)박", nights)
                if count is None:
                    raise ParseError(f"박수 칸을 읽지 못했습니다: {nights!r}")
                rejected.append(RejectedRow(expand_days(day), room, plan, occupancy_from_label(occupancy),
                                            int(count.group(1)), reason))
        for note in card.find_all("p"):
            found = re.search(r"목록이 길어 ([\d,]+)줄은 줄였습니다", note.text())
            if found:
                hidden = int(found.group(1).replace(",", ""))
    return AdjustPage(facts.get("오퍼", ""), tuple(rejected), hidden)


@dataclass(frozen=True)
class PairRead:
    """객실 × 요금제 하나를 읽은 것. `room` 은 캘린더 칩에 보이는 이름(담당자가 말하는 이름)이고 칸의 키가 된다.
    `page` 는 그 칩으로 연 [선택 날짜 가격 수정] 확인 단계 — 화면의 오퍼·요금제가 물은 것과 다르면 만들어지지 않는다."""
    offer: str
    room: str
    rate_plan: str
    page: PricePage

    def __post_init__(self):
        if (self.page.offer, self.page.rate_plan) != (self.offer, self.rate_plan):
            raise ParseError(f"{self.offer} · {self.room} · {self.rate_plan} 를 물었는데 화면은 {self.page.offer} · "
                             f"{self.page.rate_plan} 입니다")

    @classmethod
    def of(cls, room: str, page: PricePage) -> "PairRead":
        """캘린더의 객실 이름을 따로 아는 화면 조각 — 오퍼·요금제는 화면의 것."""
        return cls(page.offer, room, page.rate_plan, page)


def build_snapshot(hotel: str, read_at: str, reads: Iterable[PairRead],
                   adjust_pages: Iterable[AdjustPage] = ()) -> Snapshot:
    reads, adjust_pages = list(reads), list(adjust_pages)
    if not reads:
        raise ParseError("가격 수정 확인 단계를 하나 이상 읽어야 합니다")
    offers = {read.offer for read in reads} | {page.offer for page in adjust_pages}
    currencies = {read.page.currency for read in reads}
    if len(offers) != 1:
        raise ParseError(f"오퍼가 섞였습니다: {' · '.join(sorted(offers))}")
    if len(currencies) != 1 or not re.fullmatch(r"[A-Z]{3}", next(iter(currencies))):
        raise ParseError(f"통화를 하나로 정하지 못했습니다: {' · '.join(sorted(currencies))}")
    offer = offers.pop()
    cells, pairs, names = {}, set(), {}
    for read in reads:
        page, room = read.page, read.room
        if names.setdefault(room, page.room) != page.room:
            raise ParseError(f"캘린더의 객실 {room} 이 드로어에서 두 이름으로 보입니다: {names[room]} · {page.room}")
        pairs.add((room, page.rate_plan))
        for row in page.rows:
            for day, value in row.values.items():
                key = CellKey(room, page.rate_plan, day, row.occupancy, row.nights)
                if key in cells:
                    raise ParseError(f"같은 칸이 두 번 읽혔습니다: {room} · {page.rate_plan} · {day}")
                state = day_state(page.days[day])
                if value is None:
                    cells[key] = MISSING
                elif state == "missing":
                    raise ParseError(f"{room} · {page.rate_plan} · {day} 는 가격 없음인데 값이 있는 줄이 있습니다")
                else:
                    cells[key] = CellValue(*value, state)
    for page in adjust_pages:
        if page.hidden:
            raise ParseError(f"가감 확인 단계가 {page.hidden}줄을 숨겼습니다. 범위를 좁혀 다시 읽어야 예약 있는 날을 모두 압니다")
    by_drawer: dict[str, set[str]] = {}
    for shown, drawer in names.items():
        by_drawer.setdefault(drawer, set()).add(shown)

    def shown_name(name: str) -> str | None:
        """가감 화면의 객실 이름 → 칩의 이름. 칩의 이름이면 그대로, 드로어의 이름이면 그 짝(둘 이상이 같은 드로어 이름이면 모른다)."""
        if name in names:
            return name
        hits = by_drawer.get(name, set())
        return next(iter(hits)) if len(hits) == 1 else None

    reserved, unknown = set(), set()
    for row in (row for page in adjust_pages for row in page.rejected if row.reason == RESERVED_REASON):
        room = shown_name(row.room)
        if room is None:
            unknown.add(row.room)
        else:
            reserved.update((room, day) for day in row.days)
    if unknown:
        raise ParseError(f"가감 화면의 객실 이름이 가격 수정 화면과 맞지 않습니다: {' · '.join(sorted(unknown))}")
    return Snapshot(hotel, offer, currencies.pop(), read_at, cells, frozenset(reserved), frozenset(pairs), names)
