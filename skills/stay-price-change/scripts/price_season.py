"""price_season.py — 시즌 [가격 입력] 창으로 시즌 가격을 다시 채우는 길(시즌 원판 바꾸기). 브라우저 · 파일 · 장부를 모르는 순수
함수와 그 값의 모양이다. 셈은 `season_expand`(ERP 와 같은 금액표)가 하고, 여기서는 칸마다 무엇이 될지 · 미리보기 바구니 · 빨간 줄 ·
고름 · 저장 단계(창에 칠 값)를 만든다.

    decode_window(answers …)        readSeason 답들 → SeasonWindow(창이 열린 그대로의 칸 · 객실 · 요금제 · 아동 구간 · 시즌 날)
    decode_fill(data)               요청 파일(kind season_fill) → SeasonFill
    plan_season(snapshot, window, fill, choices, edited)  → SeasonPlan   저장마다 칸 · 바구니 · 빨간 줄 · ERP 가 말할 칸 수
    season_steps(plan)              → 저장 단계(StepPlan) — 창을 한 번 누르는 것이 한 단계. 고를 것이 남았으면 None
    step_payload(…)                 단계의 부를 값 — 창이 열려야 할 모양(form) · 저장이 보낼 모양(want)
    fresh_problem(…)                저장 하나를 내기 전의 다시 읽은 값 확인(120초 · 그 사이 바뀐 칸)

한 변경 = 한 시즌(저장 여럿). 저장 하나 = 창 한 번 누름. 한 (객실, 요금제)는 한 저장에만 든다. 창은 칸 하나를 뺄 수 없어 고름은
저장 · 규칙마다다: 이대로 채움(include) · 그 날은 빼고 채움(exclude_dates) · 요청을 고침(새 요청).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from change_core.items import ItemState, Refused, item_key
from change_core.ledger import FieldWrite, StepPlan, ValueRow
from change_core.money import money, money_text, round_money, scale_of
from change_core.rules import BLOCKED, RED, moved_far
from price_model import (
    CELL_RULES, CLOSED, FIELDS, ITEM_KIND, MISSING, NEW, RESERVED, CellChange, CellKey, CellValue, Snapshot, below_cost_label,
    cell_item_key,
    cell_name, day_label, decode_change, decode_hotel, decode_key, encode_change, encode_hotel, encode_key, iso_day,
    new_cell_state, same_hotel,
)
from season_expand import (
    NO_COMBOS, ChildRate, SeasonRefused, key_allowed, los_matrix, parse_combos, parse_inputs, parse_key, parse_money, stored,
)

KIND = "season_fill"
WINDOW_KIND = "season_window"
PLAN_KIND = "season_plan"
OP = "applySeason"
FRESH_SECONDS = 120                  # 저장 하나의 부를 값은 그 저장 범위를 이만큼 안에 다시 읽은 값으로만 낸다(A2)
MONEY_FIELDS = ("price", "original_price", "net_price")
TEXT_FIELDS = ("plan_adjust", "occupancy_keys", "occupancy_adjust", "los_prices")
INPUT_FIELDS = MONEY_FIELDS + TEXT_FIELDS
CHILD_PREFIX = "child_extra_"
DATE_FIELDS = ("date_selection_0", "date_selection_1")
PERCENT_TEXT = re.compile(r"성인 1인 추가분의 (\d+(?:\.\d+)?)% 로 계산됨")
NO_SUPPLY = "공급 통화가 없어"       # ERP 가 칸은 썼지만 팔리지 않는다고 하는 띠의 머리(_seasons_panel.html no_supply_currency)
INPUT_LABELS = {"price": "판매 단가", "original_price": "정가", "net_price": "공급 원가", "plan_adjust": "기준 요금제 대비 조정",
                "occupancy_keys": "인원 조합", "occupancy_adjust": "인원 조합별 조정", "los_prices": "박수별 단가"}


class SeasonError(Refused):
    """요청 · 창 · 읽은 값이 맞지 않아 계산하지 않는다 — 문장은 담당자에게 그대로 보여 줄 수 있다."""


class AskSeasons(SeasonError):
    """다른 시즌의 날짜를 아직 읽지 않았다 — `ask` 는 readSeason 에 그대로 넘길 값들({hotel, offer, season, datesOnly})."""

    def __init__(self, message: str, ask: list[dict]):
        super().__init__(message)
        self.ask = ask


# ─── 창 ───


@dataclass(frozen=True)
class WindowRoom:
    id: str
    label: str
    room: str                         # 캘린더의 객실 이름(요금제 탭 목록에서) — 모르면 ""


@dataclass(frozen=True)
class WindowPlan:
    id: str
    room_id: str
    label: str
    room: str
    rate_plan: str
    base: bool                        # 요금제 탭의 ✓(기준 요금제)
    sort: int | None = None


@dataclass(frozen=True)
class WindowChild:
    """창의 아동 추가 금액 칸 하나. `kind` — amount(고칠 수 있는 금액 칸) · percent(「성인 1인 추가분의 N% 로 계산됨」) · none(이 구간은
    깔리지 않는다는 읽기 전용 글). `blank` 는 [비우기] 한 창(기본값)의 그 칸 값 — 요청이 ""(구간 기본값)라고 하면 이 값을 쓴다."""
    code: str
    field: str
    kind: str
    percent: Decimal | None = None
    text: str = ""
    blank: str = ""


@dataclass(frozen=True)
class OtherSeason:
    id: str
    name: str
    dates: tuple[str, ...]


@dataclass(frozen=True)
class SeasonWindow:
    """시즌 [가격 입력] 창을 열어 읽은 것. `form` 은 창이 열린 그대로 저장 단추가 보낼 [이름, 값](켠 체크만, 막힌 칸 빼고), `order` 는
    창의 이름 있는 칸의 차례(같은 이름은 한 번), `blank` 는 [비우기] 한 창의 form(마지막 입력값이 채워져 열렸을 때만). `combos` 는
    객실(캘린더 이름) → 허용 인원 조합 글자(None 이면 객실 타입을 이름으로 하나로 정하지 못해 모름)."""
    hotel: str
    hotel_id: str
    offer: str
    season_id: str
    season_name: str
    title: str
    dates: tuple[str, ...]
    form: tuple[tuple[str, str], ...]
    order: tuple[str, ...]
    rooms: tuple[WindowRoom, ...]
    plans: tuple[WindowPlan, ...]
    child: tuple[WindowChild, ...] = ()
    blank: tuple[tuple[str, str], ...] | None = None
    last_fill_note: str = ""
    combos: Mapping[str, str | None] = field(default_factory=dict)
    seasons: tuple[OtherSeason, ...] = ()
    banner: str | None = None
    supply_warn: str | None = None    # 시즌 목록의 「공급 통화 없음」 띠(readSeason 의 supplyWarn) — 그 호텔의 시즌 채우기 칸이 팔리지 않는다
    read_at: str = ""                 # 그 창을 읽은 때(readSeason 의 doneAt) — check 가 「모름」인 저장 뒤에 읽은 것인지 본다

    def plan_of(self, room: str, rate_plan: str) -> WindowPlan:
        found = [plan for plan in self.plans if plan.room == room and plan.rate_plan == rate_plan]
        if len(found) != 1:
            names = ", ".join(f"{plan.room} · {plan.rate_plan}" for plan in self.plans)
            raise SeasonError(f"시즌 창에 {room} · {rate_plan} 요금제가 {'둘 이상' if found else '없'}습니다 — 창에 있는 것: {names}")
        return found[0]

    def room(self, room_id: str) -> WindowRoom:
        return next(room for room in self.rooms if room.id == room_id)

    def base_plan(self, room_id: str) -> WindowPlan | None:
        """그 객실의 기준 요금제 — ✓ 가 있으면 그것, 없으면 정렬(빈 정렬이 앞) · 번호가 가장 앞선 것(ERP base_rate_plan)."""
        plans = [plan for plan in self.plans if plan.room_id == room_id]
        marked = [plan for plan in plans if plan.base]
        if marked:
            return marked[0]
        return min(plans, key=lambda plan: (plan.sort is not None, plan.sort or 0, int(plan.id) if plan.id.isdigit() else 0),
                   default=None)

    def form_value(self, name: str) -> str | None:
        return next((value for key, value in self.form if key == name), None)


def _pairs(value) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list) or any(not (isinstance(item, list) and len(item) == 2) for item in value):
        raise SeasonError("readSeason 의 form 이 [이름, 값] 목록이 아닙니다 — 도우미를 다시 올리고 다시 읽습니다")
    return tuple((str(name), str(text)) for name, text in value)


def _child(item: Mapping, blank: Mapping[str, str]) -> WindowChild:
    name = str(item["field"])
    code = name[len(CHILD_PREFIX):]
    text = str(item.get("text") or item.get("value") or "")
    if item.get("editable"):
        return WindowChild(code, name, "amount", None, text, blank.get(name, str(item.get("value") or "")))
    found = PERCENT_TEXT.search(text)
    if found:
        return WindowChild(code, name, "percent", Decimal(found.group(1)), text)
    return WindowChild(code, name, "none", None, text)


def window_of(main: Mapping, dated: Mapping[str, tuple[str, ...]]) -> SeasonWindow:
    """readSeason 의 답(조각을 푼 것) 하나 + 다른 시즌의 날짜들 → SeasonWindow."""
    hotel, hotel_id = decode_hotel(main["hotel"])
    blank = main.get("blank")
    blank_form = _pairs(blank["form"]) if blank else None
    blank_children = {str(item["field"]): str(item.get("value") or "") for item in (blank or {}).get("child") or ()
                      if item.get("editable")}
    by_plan = {str(item["id"]): item for item in main.get("ratePlans") or ()}
    room_names = {str(item["roomId"]): str(item["room"]) for item in main.get("ratePlans") or ()}
    plans = []
    for item in main["plans"]:
        row = by_plan.get(str(item["id"]))
        sort = None if row is None or not str(row.get("sort") or "").strip().isdigit() else int(str(row["sort"]).strip())
        plans.append(WindowPlan(str(item["id"]), str(item["roomId"]), str(item["label"]),
                                "" if row is None else str(row["room"]), "" if row is None else str(row["plan"]),
                                bool(row and row.get("base")), sort))
    rooms = tuple(WindowRoom(str(item["id"]), str(item["label"]), room_names.get(str(item["id"]), "")) for item in main["rooms"])
    types: dict[str, list[str | None]] = {}
    for item in main.get("roomTypes") or ():
        # 표에 「허용 인원 조합」 칸이 없으면(페이지가 null) 모른다 — 제한 없음이 아니다(검토 2 의 9)
        types.setdefault(str(item["name"]), []).append(None if item.get("combos") is None else str(item["combos"]))
    # 객실 타입의 「허용 인원 조합」 — 객실 이름으로 그 타입을 찾는다. 이름이 달라 못 찾아도, 창의 객실 타입이 모두 「조합 제한 없음」이면
    # 어느 객실도 조합으로 빠지는 칸이 없다(짐작이 아니다 — 시운전 12, 칩 이름 「디럭스」 · 타입 이름 「Deluxe」).
    texts = [text for found in types.values() for text in found]
    unlimited = bool(texts) and all(text is not None and parse_combos(text) == () for text in texts)
    combos = {room.room: (types[room.room][0] if len(types.get(room.room, ())) == 1 else NO_COMBOS if unlimited else None)
              for room in rooms if room.room}
    season = main["season"]
    others = []
    for item in main.get("seasons") or ():
        if str(item["id"]) == str(season["id"]):
            continue
        others.append(OtherSeason(str(item["id"]), str(item["name"]), tuple(dated.get(str(item["id"]), ()))))
    return SeasonWindow(hotel, hotel_id, str(main["offer"]), str(season["id"]), str(season["name"]), str(main.get("title") or ""),
                        tuple(sorted(iso_day(day) for day in main["dates"])), _pairs(main["form"]),
                        tuple(dict.fromkeys(str(name) for name in main["order"])), rooms, tuple(plans),
                        tuple(_child(item, blank_children) for item in main.get("child") or ()), blank_form,
                        str(main.get("note") or ""), combos, tuple(others), main.get("banner"), main.get("supplyWarn") or None,
                        str(main.get("doneAt") or ""))


def missing_seasons(main: Mapping, dated: Mapping[str, tuple[str, ...]]) -> list[dict]:
    """날짜를 아직 읽지 않은 같은 오퍼의 다른 시즌 — readSeason({datesOnly}) 에 넘길 값."""
    return [dict(hotel=main["hotel"], offer=main["offer"], season=dict(id=str(item["id"]), name=str(item["name"])), datesOnly=True)
            for item in main.get("seasons") or ()
            if str(item["id"]) != str(main["season"]["id"]) and str(item["id"]) not in dated]


def encode_window(window: SeasonWindow) -> dict:
    return dict(kind=WINDOW_KIND, hotel=encode_hotel(window.hotel, window.hotel_id), offer=window.offer,
                season=dict(id=window.season_id, name=window.season_name), title=window.title, dates=list(window.dates),
                form=[list(pair) for pair in window.form], order=list(window.order),
                blank=None if window.blank is None else [list(pair) for pair in window.blank], last_fill_note=window.last_fill_note,
                rooms=[dict(id=room.id, label=room.label, room=room.room) for room in window.rooms],
                rate_plans=[dict(id=plan.id, room_id=plan.room_id, label=plan.label, room=plan.room, rate_plan=plan.rate_plan,
                                 base=plan.base, sort=plan.sort) for plan in window.plans],
                child=[dict(code=item.code, field=item.field, kind=item.kind, percent=money_text(item.percent), text=item.text,
                            blank=item.blank) for item in window.child],
                combos=[dict(room=room, text=text) for room, text in sorted(window.combos.items())],
                seasons=[dict(id=item.id, name=item.name, dates=list(item.dates)) for item in window.seasons], banner=window.banner,
                supply_warn=window.supply_warn, read_at=window.read_at)


def decode_window(data: Mapping) -> SeasonWindow:
    if data.get("kind") != WINDOW_KIND:
        raise SeasonError("season 명령이 낸 파일(\"kind\": \"season_window\")이 아닙니다 — readSeason 의 답을 season 명령으로 묶습니다")
    hotel, hotel_id = decode_hotel(data["hotel"])
    return SeasonWindow(
        hotel, hotel_id, str(data["offer"]), str(data["season"]["id"]), str(data["season"]["name"]), str(data.get("title") or ""),
        tuple(iso_day(day) for day in data["dates"]), _pairs(data["form"]), tuple(str(name) for name in data["order"]),
        tuple(WindowRoom(str(item["id"]), str(item["label"]), str(item.get("room") or "")) for item in data["rooms"]),
        tuple(WindowPlan(str(item["id"]), str(item["room_id"]), str(item["label"]), str(item["room"]), str(item["rate_plan"]),
                         bool(item.get("base")), item.get("sort")) for item in data["rate_plans"]),
        tuple(WindowChild(str(item["code"]), str(item["field"]), str(item["kind"]), money(item.get("percent")),
                          str(item.get("text") or ""), str(item.get("blank") or "")) for item in data.get("child") or ()),
        None if data.get("blank") is None else _pairs(data["blank"]), str(data.get("last_fill_note") or ""),
        {str(item["room"]): item.get("text") for item in data.get("combos") or ()},
        tuple(OtherSeason(str(item["id"]), str(item["name"]), tuple(iso_day(day) for day in item.get("dates") or ()))
              for item in data.get("seasons") or ()), data.get("banner"), data.get("supply_warn") or None, str(data.get("read_at") or ""))


# ─── 요청 ───


@dataclass(frozen=True)
class SeasonSave:
    """창 한 번 누름. 칸은 창에 칠 글자 그대로다(금액은 쉼표 없이). `child_extra` 는 고칠 수 있는 아동 칸마다 — ""는 구간 기본값.
    `dates` 가 None 이면 시즌 전체(창이 열린 그대로), 있으면 시즌 날 가운데 그 날들만. `sources` 는 칸마다 어디서 온 값인지(말씀 ·
    요금표 N번째 줄)."""
    pairs: tuple[tuple[str, str], ...]
    price: str
    original_price: str = ""
    net_price: str = ""
    plan_adjust: str = ""
    occupancy_keys: str = ""
    occupancy_adjust: str = ""
    los_prices: str = ""
    child_extra: tuple[tuple[str, str], ...] = ()
    overwrite: bool = True
    dates: tuple[str, ...] | None = None
    sources: tuple[tuple[str, str], ...] = ()

    def text(self, name: str) -> str:
        return str(getattr(self, name) or "").strip()

    def child(self) -> dict[str, str]:
        return {code: str(value).strip() for code, value in self.child_extra}


@dataclass(frozen=True)
class SeasonFill:
    """시즌 하나를 다시 채우는 요청. `sheet` 는 요금표에서 끌어낸 요청이면 그 요금표 확인 파일(kind sheet_check)이다 — 계산이 요금표의
    칸과 견준다(A1)."""
    hotel: str
    hotel_id: str
    offer: str
    season_id: str
    season_name: str
    currency: str
    sentence: str
    saves: tuple[SeasonSave, ...]
    sheet: Mapping | None = None


def _save(data: Mapping, where: str) -> SeasonSave:
    pairs = tuple((str(item["room"]), str(item["rate_plan"])) for item in data.get("pairs") or ())
    if not pairs:
        raise SeasonError(f"{where}: pairs(객실 · 요금제)가 없습니다")
    dates = data.get("dates")
    child = data.get("child_extra") or {}
    if not isinstance(child, Mapping):
        raise SeasonError(f"{where}: child_extra 는 {{구간 코드: 금액 글자}} 입니다")
    sources = data.get("sources") or {}
    return SeasonSave(pairs, str(data.get("price") or ""), str(data.get("original_price") or ""), str(data.get("net_price") or ""),
                      str(data.get("plan_adjust") or ""), str(data.get("occupancy_keys") or ""),
                      str(data.get("occupancy_adjust") or ""), str(data.get("los_prices") or ""),
                      tuple((str(code).upper(), str(value or "")) for code, value in child.items()),
                      bool(data.get("overwrite", True)), None if dates is None else tuple(sorted({iso_day(day) for day in dates})),
                      tuple((str(name), str(value)) for name, value in sources.items()))


def decode_fill(data: Mapping) -> SeasonFill:
    if data.get("kind") != KIND:
        raise SeasonError("시즌 다시 채우기 요청(\"kind\": \"season_fill\")이 아닙니다")
    hotel, hotel_id = decode_hotel(data["hotel"])
    season = data.get("season") or {}
    if not str(season.get("id") or "").strip():
        raise SeasonError("season 은 season 명령이 낸 파일의 season({id, name}) 그대로 적습니다")
    saves = tuple(_save(item, f"{index}번째 저장") for index, item in enumerate(data.get("saves") or (), 1))
    if not saves:
        raise SeasonError("saves(창 한 번 누름마다 하나)가 없습니다")
    return SeasonFill(hotel, hotel_id, str(data["offer"]), str(season["id"]), str(season.get("name") or ""),
                      str(data.get("currency") or "").upper(), str(data.get("sentence") or ""), saves, data.get("sheet"))


def encode_save(save: SeasonSave) -> dict:
    return dict(pairs=[dict(room=room, rate_plan=plan) for room, plan in save.pairs], price=save.price,
                original_price=save.original_price, net_price=save.net_price, plan_adjust=save.plan_adjust,
                occupancy_keys=save.occupancy_keys, occupancy_adjust=save.occupancy_adjust, los_prices=save.los_prices,
                child_extra=dict(save.child_extra), overwrite=save.overwrite,
                dates=None if save.dates is None else list(save.dates), sources=dict(save.sources))


def encode_fill(fill: SeasonFill) -> dict:
    out = dict(kind=KIND, hotel=encode_hotel(fill.hotel, fill.hotel_id), offer=fill.offer,
               season=dict(id=fill.season_id, name=fill.season_name), currency=fill.currency, sentence=fill.sentence,
               saves=[encode_save(save) for save in fill.saves])
    if fill.sheet is not None:
        out["sheet"] = fill.sheet
    return out


def check_fill(fill: SeasonFill, window: SeasonWindow) -> None:
    """요청이 그 창의 것인지 — 같은 호텔(번호) · 오퍼 · 시즌, 쌍마다 창에 있는 요금제, 한 쌍은 한 저장에만, 날짜는 시즌 날, 아동 칸은
    고칠 수 있는 칸만."""
    if not same_hotel(fill.hotel, fill.hotel_id, window.hotel, window.hotel_id) or fill.offer != window.offer:
        raise SeasonError(f"요청은 호텔 {fill.hotel_id} · {fill.offer} 이고 시즌 창은 호텔 {window.hotel_id} · {window.offer} 입니다")
    if fill.season_id != window.season_id:
        raise SeasonError(f"요청은 시즌 {fill.season_id}({fill.season_name}) 이고 창은 시즌 {window.season_id}({window.season_name}) 입니다")
    seen: dict[tuple[str, str], int] = {}
    editable = {item.code for item in window.child if item.kind == "amount"}
    for index, save in enumerate(fill.saves, 1):
        for pair in save.pairs:
            window.plan_of(*pair)
            if pair in seen:
                raise SeasonError(f"{pair[0]} · {pair[1]} 이 {seen[pair]}번째와 {index}번째 저장에 둘 다 있습니다 — 한 요금제는 한 저장에만 넣습니다")
            seen[pair] = index
        outside = sorted(set(save.dates or ()) - set(window.dates))
        if outside:
            raise SeasonError(f"{index}번째 저장의 날짜 가운데 시즌 「{window.season_name}」의 날이 아닌 것: {', '.join(outside[:5])}")
        if save.dates is not None and not save.dates:
            raise SeasonError(f"{index}번째 저장에 날짜가 하나도 없습니다")
        unknown = sorted(set(save.child()) - editable)
        if unknown:
            raise SeasonError(f"{index}번째 저장의 child_extra 에 창에서 고칠 수 없는 아동 구간이 있습니다: {', '.join(unknown)} "
                              f"(고칠 수 있는 칸: {', '.join(sorted(editable)) or '없음'})")


# ─── 칸마다 ───

RULES = {   # 시즌 다시 채우기의 규칙 → (이름, 무게). 차례가 곧 칸의 판정(맨 앞에 맞은 것) 차례다
    "ERP_REFUSES": ("ERP 창이 이 입력을 거절합니다", BLOCKED),
    "NOT_POSITIVE": (CELL_RULES.by_code["NOT_POSITIVE"].label, BLOCKED),
    "NEGATIVE_SUPPLY": (CELL_RULES.by_code["NEGATIVE_SUPPLY"].label, BLOCKED),
    "WHOLE_UNIT_FRACTION": ("소수가 없는 통화에서 소수가 생깁니다", BLOCKED),
    "OPENS_ON_CLOSED_DAY": ("셀 창에서 판매 마감한 칸이 있는 날에 판매 가능한 새 칸이 생깁니다", RED),
    "NEW_ROW": ("이 객실 · 요금제에 없던 인원 조합 · 박수 줄이 생깁니다", RED),
    "ABOVE_LIST": (CELL_RULES.by_code["ABOVE_LIST"].label, RED),
    "ABOVE_ONE_NIGHT": (CELL_RULES.by_code["ABOVE_ONE_NIGHT"].label, RED),
    "BELOW_COST": (CELL_RULES.by_code["BELOW_COST"].label, RED),
    "OVER_30": (CELL_RULES.by_code["OVER_30"].label, RED),
    "SHEET_DIFFERS": ("요금표와 다르게 채워지는 칸", RED),
}
KEEPS = {   # 빨간 줄은 아니지만 담당자가 지키자고 하면 「그 날은 빼고 채움」을 내는 바구니
    "helper_edited": "장부가 날짜별로 바꿔 둔 칸", "looks_edited": "날짜별로 따로 넣은 것으로 보이는 칸",
    "reserved": "예약 있는 날의 칸", "other_season": "다른 시즌 날짜에도 드는 날의 칸", "left_old": "이번 채우기에 없는 예전 칸",
}
CHOICE_WORDS = {"include": "이대로 채움", "exclude_dates": "그 날은 빼고 채움"}
FRACTION_SENTENCE = "원화처럼 소수가 없는 통화에서 퍼센트 조정이 소수를 만듭니다 — 요금표의 금액 차이로 적어 주세요."
CLOSED_DAY_SENTENCE = ("그날 이 객실 · 요금제에는 셀 창에서 판매 마감한 칸이 있지만(요금제 마감 · 객실 전체 마감은 아닙니다), ERP 시즌 창은 "
                       "새 칸을 판매 가능으로 만듭니다 — 손님이 그 칸으로 예약할 수 있습니다. 되돌려도 새 칸은 지울 수 없어 판매 가능으로 "
                       "남습니다(셀 창에서 사람이 마감해야 합니다).")


def rule_label(save: "SavePlan", code: str) -> str:
    """저장 하나의 규칙 · 바구니 이름 — 공급 원가는 채우기 전부터 공급 원가보다 쌌던 칸이면 그렇게(below_cost_label)."""
    if code == "BELOW_COST":
        hit = set(save.hits.get(code, ()))
        return below_cost_label((change.before, change.after) for change in save.changes if change.key in hit)
    return RULES[code][0] if code in RULES else KEEPS[code]


def rule_said(save: "SavePlan", code: str, currency: str) -> str:
    """아직 고르지 않은 규칙(빨간 줄 · 막힘) 하나를 담당자에게 하는 말 — 몇 칸 · 며칠, 이름, 칸의 예, 고를 것(시운전 12 — 시즌의 빨간
    줄에는 할 말이 없어 도우미가 지어 말했다). 미리보기 페이지의 띠와 plan 의 답(`per_save[].rules[].said`)이 같은 말을 쓴다."""
    keys, days = save.hits.get(code, ()), save.hit_dates(code)
    if code == "ERP_REFUSES":
        return f"{save.index}번째 저장은 ERP 창이 거절할 입력입니다 — “{save.refused}”. 요청을 고쳐야 합니다."
    change = next((change for change in save.changes if change.key in set(keys)), None)
    example = ""
    if change is not None:
        before, after = change.before, change.after
        shown = (lambda value: money_text(round_money(value, currency)))   # noqa: E731 — 통화의 자릿수로(51 → 51.00)
        was = "새로" if before.sell is None else shown(before.sell)
        extra = (f"(공급 원가 {shown(after.supply)})" if code == "BELOW_COST" and after.supply is not None
                 else f"(정가 {shown(after.list)})" if code == "ABOVE_LIST" and after.list is not None else "")
        example = f" 예: {cell_name(change.key)} — 판매가 {was} → {shown(after.sell)}{extra}."
    whole = len(days) >= len(save.dates)
    offered = [f"「{CHOICE_WORDS[choice]}」" + ("(남는 날이 없어 이 저장을 통째로 뺌)" if choice == "exclude_dates" and whole else "")
               for choice in rule_choices(code)] + ["「요청을 고침」"]
    fraction = {"WHOLE_UNIT_FRACTION": f" {FRACTION_SENTENCE}", "OPENS_ON_CLOSED_DAY": f" {CLOSED_DAY_SENTENCE}"}.get(code, "")
    return (f"{save.index}번째 저장의 {len(keys):,}칸({len(days):,}일) — {rule_label(save, code)}.{example}{fraction} 창은 칸 하나를 뺄 수 "
            f"없어 이 저장에서 고를 것은 {' · '.join(offered)}입니다. 어떻게 할까요?")


def rule_choices(code: str) -> tuple[str, ...]:
    if code == "ERP_REFUSES":
        return ()
    if code in KEEPS:
        return ("exclude_dates",)
    return ("include", "exclude_dates") if RULES[code][1] == RED else ("exclude_dates",)


@dataclass(frozen=True)
class SeasonChoice:
    """저장 하나 · 규칙(또는 바구니) 하나의 고름과 고르며 담당자가 한 말."""
    save: int
    rule: str
    choice: str
    said: str


@dataclass(frozen=True)
class Miss:
    """요금표의 칸 가운데 이 채우기로 그 값이 되지 않는 칸 — 요금표 값과 채운 뒤 값(필드 → 금액, 칸이 없으면 None)."""
    key: CellKey
    sheet: Mapping[str, Decimal | None]
    fill: Mapping[str, Decimal | None] | None
    save: int | None
    line: int


@dataclass(frozen=True)
class SaveCounts:
    """ERP 가 저장 뒤 띠에 말할 수(예상) — 새로 · 덮어쓴(같은 값 포함) · 판매일이 없어 건너뛴 칸, 룸 수 × 날 수. 허용 인원 조합을 몰라
    ERP 가 뺄 수 있는 칸은 따로 센다(그만큼 적게 말할 수 있다)."""
    created: int = 0
    updated: int = 0
    skipped: int = 0
    rooms: int = 0
    days: int = 0
    maybe_created: int = 0
    maybe_updated: int = 0
    maybe_skipped: int = 0


@dataclass(frozen=True)
class SavePlan:
    index: int
    save: SeasonSave                  # 고름을 단 뒤의 저장(빼기로 한 날이 빠진 dates)
    dates: tuple[str, ...]            # 이 저장이 쓰는 날
    excluded: tuple[str, ...] = ()
    refused: str | None = None
    changes: tuple[CellChange, ...] = ()
    same: int = 0
    untouched: int = 0
    left_old: tuple[CellKey, ...] = ()
    no_sale: tuple[tuple[str, str], ...] = ()
    combo_skipped: tuple[tuple[str, str], ...] = ()
    counts: SaveCounts = SaveCounts()
    hits: Mapping[str, tuple[CellKey, ...]] = field(default_factory=dict)
    choices: Mapping[str, SeasonChoice] = field(default_factory=dict)

    @property
    def dropped(self) -> bool:
        return not self.dates

    def hit_dates(self, code: str) -> tuple[str, ...]:
        return tuple(sorted({key.date for key in self.hits.get(code, ())}))

    def waiting(self) -> list[str]:
        """아직 고르지 않은 규칙 · 막는 규칙(이 저장을 누를 수 없게 하는 것)."""
        out = []
        for code, keys in self.hits.items():
            if not keys or code in KEEPS:
                continue
            choice = self.choices.get(code)
            if choice is None or (RULES[code][1] == BLOCKED and choice.choice != "exclude_dates"):
                out.append(code)
        if self.refused:
            out.insert(0, "ERP_REFUSES")
        return out


@dataclass(frozen=True)
class SeasonPlan:
    fill: SeasonFill                  # 담당자가 준 요청 그대로
    window: SeasonWindow
    currency: str
    read_at: str
    saves: tuple[SavePlan, ...]
    misses: tuple[Miss, ...] = ()
    unused: tuple[SeasonChoice, ...] = ()

    @property
    def live(self) -> tuple[SavePlan, ...]:
        return tuple(save for save in self.saves if not save.dropped)

    @property
    def pressed(self) -> tuple[SavePlan, ...]:
        """창을 누를 저장 — 빠지지 않았고 값이 바뀌는 칸이 있는 것. 바뀌는 칸이 없는 저장은 누르지 않는다(검토 2 의 8 — 누르면 같은
        값으로 덮을 뿐이고, 장부의 단계가 되면 check 가 그 단계를 가릴 칸이 없다)."""
        return tuple(save for save in self.live if save.changes)

    @property
    def ready(self) -> bool:
        return all(not save.waiting() for save in self.live)

    @property
    def changes(self) -> tuple[CellChange, ...]:
        return tuple(change for save in self.live for change in save.changes)


def child_rates(window: SeasonWindow, save: SeasonSave) -> list[ChildRate]:
    """창의 아동 칸 + 요청의 금액 → 쓸 수 있는 구간. 금액 칸은 친 값, ""는 [비우기] 한 창의 값(구간 기본값), 그것도 비면 쓰지 않음.
    비율 칸은 읽기 전용 글의 비율. 그 밖의 칸 · 칸이 없는 무료 구간은 쓰지 않는다. 금액은 창의 다른 금액 칸과 같은 규칙이다(ERP 폼 —
    0 이상, 쉼표 없이, 소수 둘째 자리까지): 어긋나면 창이 거절할 입력(SeasonRefused — 그 저장이 막힌다)."""
    typed = save.child()
    out = []
    for item in window.child:
        if item.kind == "percent" and item.percent is not None:
            out.append(ChildRate(item.code, percent=item.percent))
        elif item.kind == "amount":
            text = typed.get(item.code, "") or item.blank.strip()
            if text:
                out.append(ChildRate(item.code, amount=parse_money(text, f"아동 추가 금액 {item.code}")))
    return out


def save_texts(save: SeasonSave) -> dict[str, str]:
    return {name: save.text(name) for name in INPUT_FIELDS}


def _supply(net: Decimal | None, currency: str) -> Decimal | None:
    return None if net is None else round_money(net, currency)


def _mode(values: Iterable) -> object | None:
    """가장 흔한 값 — 둘 이상이 같은 수로 가장 흔하면 None(누가 따로 넣은 것인지 정하지 못한다)."""
    counted = Counter(values).most_common()
    if not counted or (len(counted) > 1 and counted[0][1] == counted[1][1]):
        return None
    return counted[0][0]


def expand_save(snapshot: Snapshot, window: SeasonWindow, save: SeasonSave, index: int, dates: Sequence[str],
                edited: Mapping[CellKey, int]) -> SavePlan:
    """저장 하나를 칸으로 — ERP `fill_season_price` 와 같은 차례. 거절할 입력이면 refused 만 단 SavePlan."""
    currency = snapshot.currency
    try:
        inputs = parse_inputs(save_texts(save), child_rates(window, save))
        matrices = los_matrix(inputs)
    except SeasonRefused as error:
        return SavePlan(index, save, tuple(dates), refused=str(error))
    plans = [window.plan_of(*pair) for pair in save.pairs]
    room_ids = list(dict.fromkeys(plan.room_id for plan in plans))
    keys = list(matrices[1][0])
    _refuse_odd_keys(snapshot, save, keys)
    typed = set(inputs.keys)
    shown = {(key.room, key.rate_plan, key.occupancy, key.nights) for key, value in snapshot.cells.items() if value.state != "missing"}
    other_days = {day: item for item in window.seasons for day in item.dates}
    changes, left_old, no_sale, combo_skipped = [], [], [], []
    same = untouched = created = updated = skipped = maybe_created = maybe_updated = maybe_skipped = 0
    for room_id in room_ids:
        room = window.room(room_id)
        text = window.combos.get(room.room)
        combos = None if text is None else parse_combos(text)
        if combos is not None:
            outside = [key for key in typed if not key_allowed(combos, key)]
            if outside:
                return SavePlan(index, save, tuple(dates), refused=(
                    f"{room.room or room.label}의 허용 인원 조합 밖인 인원 조합을 적었습니다({', '.join(outside)}) — 그 객실을 빼고 따로 채우거나 "
                    f"인원 조합을 고칩니다(허용: {text})"))
        room_keys = [key for key in keys if combos is None or key_allowed(combos, key)]
        combo_skipped += [(room.room, key) for key in keys if key not in room_keys]
        base = window.base_plan(room_id)
        for plan in [plan for plan in plans if plan.room_id == room_id]:
            is_base = inputs.plan_adjust is not None and base is not None and plan.id == base.id
            for nights, (tier_base, tier_plan) in matrices.items():
                table = tier_base if is_base else tier_plan
                for occupancy in room_keys:
                    sell, listed, net = table[occupancy]
                    sell, listed = stored(sell), stored(listed)   # ERP 가 칸에 넣는 값(소수 둘째 자리 — 박수별 단가만 더 길 수 있다)
                    maybe = combos is None and occupancy not in typed and parse_key(occupancy).children
                    for day in dates:
                        key = CellKey(plan.room, plan.rate_plan, day, occupancy, nights)
                        if (plan.room, day) in snapshot.no_sale:
                            skipped += 1
                            maybe_skipped += bool(maybe)   # 허용 조합을 몰라 ERP 가 그 줄을 빼면 건너뛴 칸으로도 세지 않는다
                            no_sale.append((plan.room, day))
                            continue
                        before = snapshot.cells.get(key, MISSING)
                        if before.state == "missing":
                            # ERP 는 새 칸을 판매 가능으로 만들고, 지속 마감(요금제 마감 · 객실 전체 마감)이 덮는 날에만 마감으로 둔다 —
                            # 셀 창에서 칸마다 마감한 날은 덮지 않는다(검토 2 의 0, ERP season.fill_season_price · sales_closure)
                            after = CellValue(sell, listed, _supply(net, currency), new_cell_state(snapshot, key))
                            created += 1
                            maybe_created += bool(maybe)
                        elif save.overwrite:
                            after = CellValue(sell, before.list if listed is None else listed,
                                              before.supply if net is None else _supply(net, currency), before.state)
                            updated += 1
                            maybe_updated += bool(maybe)
                        else:
                            untouched += 1
                            continue
                        if after == before:
                            same += 1
                            continue
                        marks = [mark for mark, on in ((RESERVED, (key.room, key.date) in snapshot.reserved),
                                                       (CLOSED, before.state == "closed"), (NEW, before.state == "missing")) if on]
                        if before.state != "missing" and key in edited:
                            marks.append(f"helper_edited:{edited[key]}")
                        if before.state != "missing" and day in other_days:
                            marks.append(f"other_season:{other_days[day].id}")
                        if maybe:
                            marks.append("combo_unknown")
                        if before.state == "missing" and (key.room, key.rate_plan, key.occupancy, key.nights) not in shown:
                            marks.append("new_row")
                        changes.append(CellChange(key, before, after, tuple(marks), None))
        written = {(plan.room, plan.rate_plan, occupancy, nights) for plan in plans if plan.room_id == room_id
                   for occupancy in room_keys for nights in matrices}
        for key, value in snapshot.cells.items():
            if (value.state != "missing" and key.date in dates and any(key.room == plan.room and key.rate_plan == plan.rate_plan
                                                                       for plan in plans if plan.room_id == room_id)
                    and (key.room, key.rate_plan, key.occupancy, key.nights) not in written):
                left_old.append(key)
    changes = _looks_edited(snapshot, changes, dates)
    counts = SaveCounts(created, updated, skipped, len(room_ids), len(dates), maybe_created, maybe_updated, maybe_skipped)
    plan = SavePlan(index, save, tuple(dates), (), None, tuple(changes), same, untouched, tuple(sorted(left_old)),
                    tuple(sorted(set(no_sale))), tuple(dict.fromkeys(combo_skipped)), counts)
    return replace(plan, hits=_hits(snapshot, plan))


def _refuse_odd_keys(snapshot: Snapshot, save: SeasonSave, keys: Sequence[str]) -> None:
    """저장의 쌍에 대문자가 아닌 예전 인원 조합 키(`a2`)의 칸이 있고 이 저장이 그 키(`A2`)를 쓰면 계산하지 않는다 — ERP 시즌 창은
    대소문자를 가리지 않고 그 칸을 덮는데(MySQL 기본 대조), 읽은 값과 도우미는 그 칸을 다른 칸으로 보아 미리보기가 새 칸을 말하고
    확인이 맞지 않는다. 도우미는 키를 맞춰 읽지 않는다(드문 예전 칸이다) — 사람이 그 칸의 키를 고친 뒤 다시 읽는다."""
    pairs, wanted = set(save.pairs), set(keys)
    odd = sorted({(key.room, key.rate_plan, key.occupancy) for key in snapshot.cells if (key.room, key.rate_plan) in pairs
                  and key.occupancy != key.occupancy.strip().upper() and key.occupancy.strip().upper() in wanted})
    if odd:
        room, rate_plan, occupancy = odd[0]
        raise SeasonError(f"{room} · {rate_plan} 에 인원 조합 키가 소문자인 예전 칸(`{occupancy}`)이 있습니다 — ERP 시즌 창은 대소문자를 가리지 "
                          f"않고 그 칸을 `{occupancy.strip().upper()}` 로 덮는데, 도우미는 그 칸을 다른 칸으로 읽어 미리보기가 ERP 와 달라집니다. "
                          "이 시즌 다시 채우기는 계산하지 않습니다 — 그 칸의 인원 조합을 ERP 셀 창에서 사람이 대문자로 고친 뒤 다시 읽습니다"
                          f"{f'(그런 칸 {len(odd)}줄)' if len(odd) > 1 else ''}")


def _looks_edited(snapshot: Snapshot, changes: list[CellChange], dates: Sequence[str]) -> list[CellChange]:
    """덮는 칸 가운데 이 저장의 날에서 같은 객실 · 요금제 · 인원 · 박수의 가장 흔한 값과 다른 칸 — 날짜별로 따로 넣은 것으로 보이는
    칸(짐작이다). 가장 흔한 값이 둘이면 달지 않는다. 장부가 넣은 칸(helper_edited)은 확실하니 달지 않는다."""
    days = set(dates)
    groups: dict[tuple, list] = {}
    for key, value in snapshot.cells.items():
        if value.state != "missing" and key.date in days:
            groups.setdefault((key.room, key.rate_plan, key.occupancy, key.nights), []).append((value.sell, value.list, value.supply))
    modes = {group: _mode(values) for group, values in groups.items()}
    out = []
    for change in changes:
        group = (change.key.room, change.key.rate_plan, change.key.occupancy, change.key.nights)
        before = change.before
        if (before.state != "missing" and not any(mark.startswith("helper_edited:") for mark in change.marks)
                and modes.get(group) is not None and (before.sell, before.list, before.supply) != modes[group]):
            change = replace(change, marks=change.marks + ("looks_edited",))
        out.append(change)
    return out


def _hits(snapshot: Snapshot, plan: SavePlan) -> dict[str, tuple[CellKey, ...]]:
    """규칙 · 바구니마다 걸린 칸. 박수 층 규칙은 채운 뒤의 값끼리 — 같은 객실 · 요금제 · 날 · 인원의 1박 이상보다 비싼 층(그대로 남는 예전
    층 포함). 칸을 쓰는 쪽(층 칸, 또는 1박 칸)에 단다."""
    currency = snapshot.currency
    whole = scale_of(currency) == 0
    hits: dict[str, list[CellKey]] = {code: [] for code in list(RULES) + list(KEEPS)}
    # 셀 창에서 칸마다 마감한 칸이 있는 날(지속 마감이 아닌 날의 마감 · 섞인 칸) — ERP 는 그날 새 칸을 판매 가능으로 만든다
    hand_closed = {(key.room, key.rate_plan, key.date) for key, value in snapshot.cells.items()
                   if value.state in ("closed", "mixed")} - set(snapshot.closures)
    after = {key: value for key, value in snapshot.cells.items() if value.state != "missing"}
    after.update({change.key: change.after for change in plan.changes})
    written = {change.key for change in plan.changes}
    for change in plan.changes:
        value, before, key = change.after, change.before, change.key
        if value.sell <= 0:
            hits["NOT_POSITIVE"].append(key)
        if value.supply is not None and value.supply < 0:
            hits["NEGATIVE_SUPPLY"].append(key)
        if whole and any(amount is not None and amount != amount.to_integral_value() for amount in (value.sell, value.list)):
            hits["WHOLE_UNIT_FRACTION"].append(key)
        if before.state == "missing" and value.state == "open" and (key.room, key.rate_plan, key.date) in hand_closed:
            hits["OPENS_ON_CLOSED_DAY"].append(key)
        if "new_row" in change.marks:
            hits["NEW_ROW"].append(key)
        if value.list is not None and value.sell > value.list:
            hits["ABOVE_LIST"].append(key)
        if value.supply is not None and value.sell < value.supply:
            hits["BELOW_COST"].append(key)
        if any(moved_far(getattr(before, name), getattr(value, name)) for name in FIELDS):
            hits["OVER_30"].append(key)
        if any(mark.startswith("helper_edited:") for mark in change.marks):
            hits["helper_edited"].append(key)
        if "looks_edited" in change.marks:
            hits["looks_edited"].append(key)
        if RESERVED in change.marks:
            hits["reserved"].append(key)
        if any(mark.startswith("other_season:") for mark in change.marks):
            hits["other_season"].append(key)
        one = after.get(replace(key, nights=1))
        if key.nights > 1 and one is not None and value.sell > one.sell:
            hits["ABOVE_ONE_NIGHT"].append(key)
        if key.nights == 1:
            uppers = [other for other, other_value in after.items() if (other.room, other.rate_plan, other.date, other.occupancy)
                      == (key.room, key.rate_plan, key.date, key.occupancy) and other.nights > 1 and other not in written
                      and other_value.sell > value.sell]
            if uppers:
                hits["ABOVE_ONE_NIGHT"].append(key)
    hits["left_old"] = list(plan.left_old)
    return {code: tuple(dict.fromkeys(keys)) for code, keys in hits.items() if keys}


def plan_season(snapshot: Snapshot, window: SeasonWindow, fill: SeasonFill, choices: Sequence[SeasonChoice] = (),
                edited: Mapping[CellKey, int] | None = None, targets: Mapping[CellKey, tuple[tuple[str, Decimal], int]] | None = None
                ) -> SeasonPlan:
    """요청 + 창 + 읽은 값(+ 고름 · 장부가 날짜별로 넣은 칸 · 요금표의 칸) → 미리보기. 「그 날은 빼고 채움」은 그 규칙이 걸린 날을 그
    저장의 날에서 빼고 다시 셈한다(뺀 날이 다른 규칙을 바꿀 수 있어, 더 빠지는 날이 없을 때까지). 남은 날이 없으면 그 저장은 빠진다."""
    check_fill(fill, window)
    _check_reading(snapshot, window, fill)
    edited, targets = edited or {}, targets or {}
    by_save: dict[int, list[SeasonChoice]] = {}
    for choice in choices:
        if not 1 <= choice.save <= len(fill.saves):
            raise SeasonError(f"고름의 저장 번호 {choice.save} 가 없습니다(저장 {len(fill.saves)}개)")
        code = choice.rule
        if code not in RULES and code not in KEEPS:
            raise SeasonError(f"모르는 규칙입니다: {code!r}")
        if choice.choice not in rule_choices(code):
            allowed = " · ".join(rule_choices(code)) or "없음 — 요청을 고쳐 다시 계산합니다"
            raise SeasonError(f"{RULES.get(code, (KEEPS.get(code),))[0]} — 고를 수 있는 것: {allowed} (받은 값 {choice.choice!r})")
        by_save.setdefault(choice.save, []).append(choice)
    saves = []
    for index, save in enumerate(fill.saves, 1):
        dates = list(save.dates or window.dates)
        excluded: list[str] = []
        mine = {choice.rule: choice for choice in by_save.get(index, ())}
        while True:
            plan = expand_save(snapshot, window, save, index, dates, edited)
            plan = _with_misses(plan, targets, snapshot)
            drop = {day for code, choice in mine.items() if choice.choice == "exclude_dates" for day in plan.hit_dates(code)}
            drop &= set(dates)
            if not drop:
                break
            excluded += sorted(drop)
            dates = [day for day in dates if day not in drop]
        effective = replace(save, dates=None if save.dates is None and not excluded else tuple(dates))
        saves.append(replace(plan, save=effective, excluded=tuple(sorted(excluded)), choices=mine))
    unused = tuple(choice for plan in saves for code, choice in plan.choices.items()
                   if choice.choice == "include" and not plan.hits.get(code))
    misses = _misses(saves, targets, snapshot, window)
    return SeasonPlan(fill, window, snapshot.currency, snapshot.read_at, tuple(saves), misses, unused)


def _check_reading(snapshot: Snapshot, window: SeasonWindow, fill: SeasonFill) -> None:
    if not same_hotel(snapshot.hotel, snapshot.hotel_id, window.hotel, window.hotel_id) or snapshot.offer != window.offer:
        raise SeasonError(f"읽은 값은 호텔 {snapshot.hotel_id} · {snapshot.offer} 것이고 시즌 창은 호텔 {window.hotel_id} · {window.offer} 입니다")
    if fill.currency and fill.currency != snapshot.currency:
        raise SeasonError(f"요청의 통화는 {fill.currency} 인데 ERP 의 이 오퍼는 {snapshot.currency} 입니다 — 바꿔 셈하지 않습니다. 어느 통화의 "
                          "금액인지 담당자에게 여쭙니다")
    for save in fill.saves:
        for pair in save.pairs:
            if pair not in snapshot.pairs:
                raise SeasonError(f"읽지 않은 객실·요금제가 있습니다: {pair[0]} · {pair[1]}. read-calls 에 이 요청과 --season 을 주어 읽습니다")
        days = set(save.dates or window.dates)
        unread = sorted(days - set(snapshot.dates))
        if unread:
            raise SeasonError(f"읽은 값에 없는 날짜: {', '.join(unread[:5])}{' …' if len(unread) > 5 else ''} — 시즌 날을 모두 읽습니다")


def season_range(window: SeasonWindow, fill: SeasonFill) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    """읽을 범위 — 저장들의 (객실, 요금제) × 저장들의 날(시즌 전체면 시즌 날)."""
    pairs = tuple(dict.fromkeys(pair for save in fill.saves for pair in save.pairs))
    days = sorted({day for save in fill.saves for day in (save.dates or window.dates)})
    return pairs, tuple(days)


# ─── 요금표와 견주기(A1) ───


def _with_misses(plan: SavePlan, targets, snapshot: Snapshot) -> SavePlan:
    """요금표에서 끌어낸 요청이면 이 저장의 쌍 · 날에 든 요금표 칸 가운데 채운 뒤 값이 요금표 값이 아닌 칸을 SHEET_DIFFERS 로 단다."""
    if not targets or plan.refused:
        return plan
    pairs, days = set(plan.save.pairs), set(plan.dates)
    final = _final(plan, snapshot)
    keys = [key for key in targets if (key.room, key.rate_plan) in pairs and key.date in days and (key.room, key.date) not in snapshot.no_sale
            and not _reproduced(key, targets, final)]
    if not keys:
        return plan
    return replace(plan, hits={**plan.hits, "SHEET_DIFFERS": tuple(keys)})


def _final(plan: SavePlan, snapshot: Snapshot) -> dict[CellKey, CellValue]:
    out = dict(snapshot.cells)
    out.update({change.key: change.after for change in plan.changes})
    return out


def _reproduced(key: CellKey, targets, final: Mapping[CellKey, CellValue]) -> bool:
    values, _line = targets[key]
    value = final.get(key, MISSING)
    if value.state == "missing":
        return False
    return all(getattr(value, name) == wanted for name, wanted in values)


def _misses(saves: Sequence[SavePlan], targets, snapshot: Snapshot, window: SeasonWindow) -> tuple[Miss, ...]:
    """요금표 칸 가운데 채운 뒤 그 값이 되지 않는 칸 전부 — 어느 저장에도 들지 않는 쌍 · 날의 칸도(그 칸은 날짜별 변경으로 맞춘다)."""
    if not targets:
        return ()
    final = dict(snapshot.cells)
    owner: dict[tuple[str, str, str], int] = {}
    for plan in saves:
        if plan.dropped or plan.refused:
            continue
        final.update({change.key: change.after for change in plan.changes})
        owner.update({(room, rate_plan, day): plan.index for room, rate_plan in plan.save.pairs for day in plan.dates})
    out = []
    for key, (values, line) in sorted(targets.items()):
        if (key.room, key.date) in snapshot.no_sale or _reproduced(key, targets, final):   # 판매일 없는 날은 어느 길로도 넣지 못한다
            continue
        value = final.get(key, MISSING)
        out.append(Miss(key, dict(values), None if value.state == "missing" else {name: getattr(value, name) for name in FIELDS},
                        owner.get((key.room, key.rate_plan, key.date)), line))
    return tuple(out)


def followup_targets(plan: SeasonPlan) -> list[dict]:
    """요금표와 다르게 채워지는 칸을 날짜별로 맞출 목표 값 표의 줄(kind targets 의 targets) — 결과 뒤에 도우미가 내놓는 변경. 채우는 날의
    칸만이다 — 담당자가 빼라고 한 날(「그 날은 빼고 채움」)의 칸은 그대로 두라는 말이라 내놓지 않는다."""
    return [dict(key=encode_key(miss.key), values={name: money_text(value) for name, value in miss.sheet.items()})
            for miss in plan.misses if miss.save is not None]


# ─── 장부 · 저장 단계 ───


def verdict(save: SavePlan, key: CellKey) -> str | None:
    """칸의 판정 — 걸린 규칙 가운데 표의 차례로 맨 앞(바구니는 판정이 아니다)."""
    return next((code for code in RULES if key in save.hits.get(code, ())), None)


def preview_rows(plan: SeasonPlan) -> list[ValueRow]:
    """장부의 줄 — 바뀌는 칸마다 필드마다 한 줄. 넣는 값(action)은 고를 것이 없는 저장의 칸에만 단다(창은 칸 하나를 뺄 수 없다)."""
    rows = []
    for save in plan.live:
        ready = not save.waiting()
        for change in save.changes:
            code = verdict(save, change.key)
            choice = save.choices.get(code) if code else None
            for name in FIELDS:
                old, new = getattr(change.before, name), getattr(change.after, name)
                action = "set" if ready and new != old and new is not None else None
                rows.append(ValueRow(ITEM_KIND, cell_item_key(change.key), cell_name(change.key), name, change.before.state, old,
                                     None if new == old else new, code, change.marks, action,
                                     None if choice is None else choice.choice, None if choice is None else choice.said))
    return rows


def has_writes(plan: SeasonPlan) -> bool:
    return any(change.after != change.before for save in plan.live for change in save.changes)


def date_runs(days: Iterable[str]) -> list[str]:
    """날짜 → 이어진 날(달력으로)끼리 한 줄 — `YYYY-MM-DD` 또는 `YYYY-MM-DD ~ YYYY-MM-DD`. 창의 [기간 · 직접 입력] 칸 모양이다."""
    runs: list[list[str]] = []
    for day in sorted(days):
        if runs and (date.fromisoformat(day) - date.fromisoformat(runs[-1][-1])).days == 1:
            runs[-1].append(day)
        else:
            runs.append([day])
    return [run[0] if len(run) == 1 else f"{run[0]} ~ {run[-1]}" for run in runs]


def want_form(window: SeasonWindow, save: SeasonSave) -> list[list[str]]:
    """저장이 보내야 할 [이름, 값] — 창의 칸 차례대로, 금액 · 글 칸은 요청의 글자, 체크는 고른 객실 · 요금제(번호)와 덮기, 날짜는 dates
    를 줬을 때만 그 날들의 구간. 「이번에 고르지 않은 인원·요금제 가격 지우기」는 켜지 않는다."""
    plans = [window.plan_of(*pair) for pair in save.pairs]
    room_ids, plan_ids = {plan.room_id for plan in plans}, {plan.id for plan in plans}
    typed = save.child()
    out: list[list[str]] = []
    for name in window.order:
        if name == "rooms":
            out += [["rooms", room.id] for room in window.rooms if room.id in room_ids]
        elif name == "rate_plans":
            out += [["rate_plans", plan.id] for plan in window.plans if plan.id in plan_ids]
        elif name == "overwrite":
            if save.overwrite:
                out.append(["overwrite", "on"])
        elif name == "stale_cleanup":
            continue
        elif name in INPUT_FIELDS:
            out.append([name, save.text(name)])
        elif name.startswith(CHILD_PREFIX):
            out.append([name, typed.get(name[len(CHILD_PREFIX):], "")])
        elif name == "date_selection_0":
            out.append([name, "\n".join(date_runs(save.dates)) if save.dates is not None else window.form_value(name) or ""])
        elif name == "date_selection_1":
            out.append([name, "" if save.dates is not None else window.form_value(name) or ""])
        else:
            value = window.form_value(name)
            if value is not None:
                out.append([name, value])
    return out


def opened_form(window: SeasonWindow, previous: SeasonSave | None, has_prices: bool) -> list[list[str]]:
    """그 단계에서 창이 열려야 할 모양. 첫 단계는 미리보기 때 읽은 그대로다. 다음 단계부터는 앞 저장이 남긴 마지막 입력값이 채워져 열린다
    — 금액 · 글 칸과 고칠 수 있는 아동 칸은 앞 저장의 글자(""는 ""), 체크는 꺼짐, 덮기는 시즌에 가격이 있으면 켜짐, 날짜는 시즌 전체."""
    if previous is None:
        return [list(pair) for pair in window.form]
    typed = previous.child()
    out: list[list[str]] = []
    for name in window.order:
        if name in INPUT_FIELDS:
            out.append([name, previous.text(name)])
        elif name.startswith(CHILD_PREFIX):
            out.append([name, typed.get(name[len(CHILD_PREFIX):], "")])
        elif name == "overwrite":
            if has_prices:
                out.append(["overwrite", "on"])
        elif name in ("rooms", "rate_plans", "stale_cleanup"):
            continue
        else:
            value = window.form_value(name)
            if value is not None:
                out.append([name, value])
    return out


def step_label(window: SeasonWindow, save: SavePlan) -> str:
    rooms: dict[str, list[str]] = {}
    for room, rate_plan in save.save.pairs:
        rooms.setdefault(room, []).append(rate_plan)
    pairs = ", ".join(f"{room}({' · '.join(plans)})" for room, plans in rooms.items())
    return f"시즌 「{window.season_name}」 [가격 입력] · {pairs} · {_days(save.dates)}"


def _days(days: Sequence[str]) -> str:
    runs = date_runs(days)
    shown = ", ".join(f"{day_label(run)}" if "~" not in run else f"{day_label(run.split(' ~ ')[0])} ~ {day_label(run.split(' ~ ')[1])}"
                      for run in runs[:4])
    return f"{shown}{' …' if len(runs) > 4 else ''} ({len(days)}일)"


def step_payload(plan: SeasonPlan, save: SavePlan, no: int, previous: SeasonSave | None, has_prices: bool) -> dict:
    """페이지 `stayPriceSeason.applySeason` 에 넘길 값 — 그 시즌 창이 열려야 할 모양(form)과 보낼 모양(want), 창이 보일 날 · 객실 ·
    요금제 · 읽기 전용 아동 글(미리보기 때 읽은 그대로). 페이지는 창이 이것과 다르면 아무것도 치지 않는다."""
    window = plan.window
    return {"no": no, "hotel": encode_hotel(window.hotel, window.hotel_id), "offer": window.offer,
            "season": {"id": window.season_id, "name": window.season_name}, "dates": list(window.dates),
            "form": opened_form(window, previous, has_prices), "want": want_form(window, save.save),
            "candidates": {"rooms": [[room.id, room.label] for room in window.rooms],
                           "plans": [[item.id, item.room_id, item.label] for item in window.plans]},
            "child": [[item.field, item.text] for item in window.child if item.kind != "amount"]}


def season_steps(plan: SeasonPlan) -> list[StepPlan] | None:
    """저장 단계 — 누를 저장마다 하나(창 한 번 누름, `plan.pressed` — 바뀌는 칸이 없는 저장은 단계가 아니다). 고를 것이 남은 저장이
    있으면 None. 단계가 쓰는 값은 그 저장의 바뀌는 칸의 필드다(같은 값으로 덮는 칸은 장부에 적지 않는다). 다음 단계의 창 모양은 앞
    단계가 남긴 마지막 입력값으로 정한다."""
    if not plan.ready:
        return None
    steps, previous, has_prices = [], None, any(name == "overwrite" for name, _value in plan.window.form)
    for no, save in enumerate(plan.pressed, 1):
        writes = tuple(FieldWrite(ITEM_KIND, cell_item_key(change.key), name, getattr(change.after, name))
                       for change in save.changes for name in FIELDS
                       if getattr(change.after, name) != getattr(change.before, name) and getattr(change.after, name) is not None)
        body = {"save": save.index, "payload": step_payload(plan, save, no, previous, has_prices), "predicted": encode_counts(save.counts)}
        steps.append(StepPlan(KIND, step_label(plan.window, save), body, writes))
        previous, has_prices = save.save, has_prices or save.counts.created > 0
    return steps


def encode_counts(counts: SaveCounts) -> dict:
    return dict(created=counts.created, updated=counts.updated, skipped=counts.skipped, rooms=counts.rooms, days=counts.days,
                maybe_created=counts.maybe_created, maybe_updated=counts.maybe_updated, maybe_skipped=counts.maybe_skipped)


def decode_counts(data: Mapping) -> SaveCounts:
    return SaveCounts(*(int(data.get(name) or 0) for name in ("created", "updated", "skipped", "rooms", "days", "maybe_created",
                                                              "maybe_updated", "maybe_skipped")))


def step_call(step_no: int, body: Mapping, until_ms: int) -> dict:
    """장부의 단계 → `{no, op, payload}` — 페이로드는 begin 때 정해져 장부에 그대로 있고, calls 가 그 범위를 다시 읽은 값의 기한
    (`freshUntil` — 이 컴퓨터 시계의 1970년부터 ms)을 얹는다. 페이지는 기한이 없거나 지난 페이로드로는 창을 열지도 누르지도 않는다
    (계산 파일 · 장부의 페이로드는 기한이 없어 누를 수 없다)."""
    return {"no": step_no, "op": OP, "payload": dict(body["payload"], no=step_no, freshUntil=until_ms)}


def fresh_until(read_at: str) -> int:
    """다시 읽은 값의 시각 → 그 값으로 낸 부를 값을 누를 수 있는 마지막 때(1970년부터 ms) — 읽은 때부터 FRESH_SECONDS."""
    return int(_moment(read_at).timestamp() * 1000) + FRESH_SECONDS * 1000


# ─── 저장 하나를 내기 전에 — 그 범위를 다시 읽은 값(A2) ───


def _moment(text: str) -> datetime:
    moment = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.astimezone()


def fresh_problem(read_at: str, since: str, now: datetime) -> str | None:
    """다시 읽은 값이 쓸 만큼 새로운지 — 앞 단계가 끝난 뒤(앞 단계가 없으면 그 번호를 계산한 뒤, 같은 초는 뒤로 친다)이고 FRESH_SECONDS
    안이어야 한다. 아니면 까닭."""
    read = _moment(read_at)
    if read.replace(microsecond=0) < _moment(since):
        return (f"이 읽은 값({read:%H:%M:%S})은 장부가 마지막으로 적은 때({_moment(since):%H:%M:%S}) 앞에 읽은 것입니다 — 그 뒤의 ERP 를 "
                "모릅니다. 이 저장의 범위를 새 읽기 폴더에 다시 읽고 calls 를 부릅니다")
    age = (now - read).total_seconds()
    if age > FRESH_SECONDS:
        return (f"이 읽은 값은 {int(age)}초 전 것입니다 — 시즌 창 저장은 그 범위를 {FRESH_SECONDS}초 안에 다시 읽은 값으로만 냅니다(창이 칸 값을 "
                "보이지 않아 누르는 순간 견주지 못합니다). 이 저장의 범위를 새 읽기 폴더에 다시 읽고 calls 를 부릅니다")
    return None


def step_range(window: SeasonWindow, body: Mapping) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    """단계 하나(장부의 body)의 범위 — 그 저장의 (객실, 요금제) × 그 저장의 날."""
    payload = body["payload"]
    plan_ids = {value for name, value in payload["want"] if name == "rate_plans"}
    pairs = tuple((plan.room, plan.rate_plan) for plan in window.plans if plan.id in plan_ids)
    runs = next((value for name, value in payload["want"] if name == "date_selection_0"), "")
    days = set()
    for line in str(runs).splitlines():
        if not line.strip():
            continue
        first, _sep, last = line.partition("~")
        start, end = date.fromisoformat(first.strip()), date.fromisoformat((last or first).strip())
        days |= {(start + timedelta(days=n)).isoformat() for n in range((end - start).days + 1)}
    return pairs, tuple(sorted(days & set(window.dates)))


def expected_cells(then: Snapshot, rows_written: Mapping[CellKey, CellValue], pairs, days) -> dict[CellKey, CellValue]:
    """저장 하나의 범위에서 지금 있어야 할 칸 — 미리보기 때 읽은 값 위에 앞 저장들이 넣은(예상한) 값을 얹은 것."""
    wanted, days = set(pairs), set(days)
    cells = {key: value for key, value in then.cells.items() if (key.room, key.rate_plan) in wanted and key.date in days}
    cells.update({key: value for key, value in rows_written.items() if (key.room, key.rate_plan) in wanted and key.date in days})
    return cells


def range_differences(expected: Mapping[CellKey, CellValue], now: Snapshot, pairs, days) -> list[tuple[CellKey, CellValue, CellValue]]:
    """그 범위에서 있어야 할 값과 다시 읽은 값이 다른 칸 — (칸, 있어야 할 값, 읽은 값). 한쪽에만 있는 칸도(없는 칸은 MISSING)."""
    wanted, days = set(pairs), set(days)
    seen = {key: value for key, value in now.cells.items() if (key.room, key.rate_plan) in wanted and key.date in days}
    out = []
    for key in sorted(set(expected) | set(seen)):
        then, here = expected.get(key, MISSING), seen.get(key, MISSING)
        if then != here:
            out.append((key, then, here))
    return out


DAY_KIND = "season_day"   # 날의 사정(판매일 없음 · 예약 있음)을 견주기의 항목으로 — 검토 2 의 7


def day_items(snapshot: Snapshot, pairs, days) -> dict:
    """그 범위의 객실 · 날 가운데 판매일 없는 날 · 예약 있는 날 — 하나에 항목 하나(있을 때만). 미리보기가 쓴 사정이다(판매일 없는 날은
    건너뛴 칸, 예약 있는 날은 바구니). 적용 직전(begin)과 저장마다(calls)의 다시 읽은 값이 칸과 함께 견준다 — 그 사이 판매일이 열리면
    미리보기에 없던 칸이 생기고, 예약이 들면 담당자가 고른 「예약 있는 날은 빼고」가 그 날을 모른다."""
    rooms, days = {room for room, _plan in pairs}, set(days)
    out = {}
    for what, said, facts in (("no_sale", "판매일 없음", snapshot.no_sale), ("reserved", "예약 있음", snapshot.reserved)):
        for room, day in sorted(facts):
            if room in rooms and day in days:
                out[(DAY_KIND, item_key({"room": room, "date": day, "what": what}))] = ItemState(f"{room} · {day} {said}", what, {})
    return out


def covers(now: Snapshot, pairs, days) -> list[str]:
    """다시 읽은 값이 그 범위를 덮는지 — 덮지 않는 (객실 · 요금제 · 날)."""
    gaps = [f"{room} · {rate_plan}" for room, rate_plan in pairs if (room, rate_plan) not in now.pairs]
    gaps += [day for day in days if day not in set(now.dates)]
    return gaps


# ─── ERP 의 답(띠) ───

BANNER = re.compile(r"새로 ([\d,]+)칸 · 덮어쓴 ([\d,]+)칸 \(룸 (\d+)개 × (\d+)일\)")
BANNER_SKIPPED = re.compile(r"판매일이 없어 건너뛴 칸 ([\d,]+)개")


def banner_counts(text: str | None) -> SaveCounts | None:
    """ERP 의 저장 띠 글 → 수. 띠가 아니면 None."""
    found = BANNER.search(text or "")
    if found is None:
        return None
    skipped = BANNER_SKIPPED.search(text or "")
    number = lambda value: int(value.replace(",", ""))   # noqa: E731
    return SaveCounts(number(found.group(1)), number(found.group(2)), number(skipped.group(1)) if skipped else 0,
                      int(found.group(3)), int(found.group(4)))


def counts_agree(predicted: SaveCounts, told: SaveCounts) -> bool:
    """ERP 가 말한 수가 예상과 맞는지 — 허용 인원 조합을 몰라 ERP 가 뺄 수 있는 칸(새로 · 덮어쓴 · 판매일이 없어 건너뛴)만큼은 적어도
    맞다(그만큼은 도우미의 짐작이다)."""
    return (predicted.created - predicted.maybe_created <= told.created <= predicted.created
            and predicted.updated - predicted.maybe_updated <= told.updated <= predicted.updated
            and predicted.skipped - predicted.maybe_skipped <= told.skipped <= predicted.skipped
            and (told.rooms, told.days) == (predicted.rooms, predicted.days))


def step_note(result: Mapping) -> str:
    """저장 답 → 장부의 메모 — 저장됐으면 ERP 의 띠 글(공급 통화가 없다는 띠도 덧붙여), 아니면 페이지의 까닭."""
    if result.get("saved") is True:
        banner = str(result.get("banner") or "").strip() or "저장했습니다"
        return f"{banner} · {result['warn']}" if result.get("warn") else banner
    return str(result.get("error") or "저장하지 못했습니다")


# ─── 계산 파일(plan-k.json) ───


def encode_choice(choice: SeasonChoice) -> dict:
    return dict(save=choice.save, rule=choice.rule, choice=choice.choice, said=choice.said)


def decode_choices(items) -> list[SeasonChoice]:
    out = []
    for item in items or ():
        said = str(item.get("said") or "").strip()
        if not said:
            raise SeasonError(f"고름마다 담당자가 그렇게 고르며 한 말을 그대로 적습니다(said): {item.get('save')}번째 저장 · {item.get('rule')}")
        out.append(SeasonChoice(int(item["save"]), str(item["rule"]), str(item["choice"]), said))
    return out


def encode_plan(plan: SeasonPlan) -> dict:
    return dict(kind=PLAN_KIND, request=encode_fill(plan.fill), window=encode_window(plan.window), currency=plan.currency,
                read_at=plan.read_at, saves=[encode_save_plan(save) for save in plan.saves],
                misses=[dict(key=encode_key(miss.key), sheet={k: money_text(v) for k, v in miss.sheet.items()},
                             fill=None if miss.fill is None else {k: money_text(v) for k, v in miss.fill.items()}, save=miss.save,
                             line=miss.line) for miss in plan.misses],
                unused=[encode_choice(choice) for choice in plan.unused])


def encode_save_plan(save: SavePlan) -> dict:
    return dict(index=save.index, save=encode_save(save.save), dates=list(save.dates), excluded=list(save.excluded),
                refused=save.refused, changes=[encode_change(change) for change in save.changes], same=save.same,
                untouched=save.untouched, left_old=[encode_key(key) for key in save.left_old],
                no_sale=[dict(room=room, date=day) for room, day in save.no_sale],
                combo_skipped=[dict(room=room, occupancy=key) for room, key in save.combo_skipped], counts=encode_counts(save.counts),
                hits={code: [encode_key(key) for key in keys] for code, keys in save.hits.items()},
                choices={code: encode_choice(choice) for code, choice in save.choices.items()})


def decode_save_plan(data: Mapping) -> SavePlan:
    return SavePlan(int(data["index"]), _save(data["save"], "저장"), tuple(data["dates"]), tuple(data.get("excluded") or ()),
                    data.get("refused"), tuple(decode_change(item) for item in data.get("changes") or ()), int(data.get("same") or 0),
                    int(data.get("untouched") or 0), tuple(decode_key(item) for item in data.get("left_old") or ()),
                    tuple((str(item["room"]), iso_day(item["date"])) for item in data.get("no_sale") or ()),
                    tuple((str(item["room"]), str(item["occupancy"])) for item in data.get("combo_skipped") or ()),
                    decode_counts(data.get("counts") or {}),
                    {code: tuple(decode_key(item) for item in keys) for code, keys in (data.get("hits") or {}).items()},
                    {code: SeasonChoice(int(item["save"]), str(item["rule"]), str(item["choice"]), str(item["said"]))
                     for code, item in (data.get("choices") or {}).items()})


def decode_plan(data: Mapping) -> SeasonPlan:
    if data.get("kind") != PLAN_KIND:
        raise SeasonError("시즌 다시 채우기의 계산 파일(\"kind\": \"season_plan\")이 아닙니다")
    return SeasonPlan(decode_fill(data["request"]), decode_window(data["window"]), str(data["currency"]), str(data["read_at"]),
                      tuple(decode_save_plan(item) for item in data["saves"]),
                      tuple(Miss(decode_key(item["key"]), {k: money(v) for k, v in item["sheet"].items()},
                                 None if item.get("fill") is None else {k: money(v) for k, v in item["fill"].items()},
                                 item.get("save"), int(item.get("line") or 0)) for item in data.get("misses") or ()),
                      tuple(SeasonChoice(int(item["save"]), str(item["rule"]), str(item["choice"]), str(item["said"]))
                            for item in data.get("unused") or ()))


def recorded_request(plan: SeasonPlan) -> dict:
    """장부에 적는 요청 — 누를 저장들(고른 대로 날을 뺀 것, 빠진 저장 · 바뀌는 칸이 없어 누르지 않는 저장은 없음) + 창(띠는 빼고).
    되돌리기 페이지가 창의 이전 입력값을 여기서 보인다."""
    window = encode_window(plan.window)
    for name in ("banner", "supply_warn", "read_at"):   # 그때 시즌 목록의 띠 · 읽은 때 — 창의 모양이 아니다
        window.pop(name, None)
    return dict(encode_fill(replace(plan.fill, saves=tuple(save.save for save in plan.pressed))), window=window)


def counts(plan: SeasonPlan) -> dict:
    """미리보기 머리 숫자 — 바구니마다의 수와 빨간 줄 · 막힘 · 저장 횟수."""
    live = plan.live
    tally = dict(changes=0, new=0, same=sum(save.same for save in live), untouched=sum(save.untouched for save in live),
                 left_old=sum(len(save.left_old) for save in live), no_sale=sum(save.counts.skipped for save in live),
                 combo_unknown=0, closed_new=0, combo_skipped=sum(len(save.combo_skipped) for save in live), red=0, blocked=0,
                 saves=len(plan.pressed), dropped=len(plan.saves) - len(live), unpressed=len(live) - len(plan.pressed),
                 misses=len(plan.misses))
    for save in live:
        for change in save.changes:
            tally["new" if change.before.state == "missing" else "changes"] += 1
            tally["combo_unknown"] += "combo_unknown" in change.marks
            tally["closed_new"] += change.before.state == "missing" and change.after.state == "closed"   # 지속 마감인 날의 새 칸
        for code in KEEPS:
            if code != "left_old":
                tally[code] = tally.get(code, 0) + len(save.hits.get(code, ()))
        for code in save.waiting():
            if code == "ERP_REFUSES" or RULES[code][1] == BLOCKED:
                tally["blocked"] += 1
            else:
                tally["red"] += 1
    return tally



WINDOW_REMEMBERS = ("시즌 「{season}」의 [가격 입력] 창은 이번에 친 금액을 기억하지만 고른 날짜는 기억하지 않습니다 — 다음에 누가 그 창을 "
                    "열면 시즌 전체({span})로 열리고, 그대로 [가격 적용]을 누르면 이번 금액이 시즌의 모든 날에 들어갑니다. 그 창을 열면 "
                    "[비우기]를 누르거나 날짜를 확인한 뒤 눌러야 합니다.")


def window_remembers(request: Mapping) -> str | None:
    """날짜 일부만 채우는(채운) 저장이 있으면 시즌 창의 기억에 대한 한 문장(시운전 12 — 12/9~11 만 채운 뒤 창이 그 금액과 시즌 전체
    날짜로 열렸다. 누가 그대로 누르면 115일에 퍼진다), 없으면 None. `request` 는 장부에 적는 시즌 채우기 요청(recorded_request)."""
    if not any(save.get("dates") is not None for save in request.get("saves") or ()):
        return None
    dates = (request.get("window") or {}).get("dates") or ()
    return WINDOW_REMEMBERS.format(season=(request.get("season") or {}).get("name") or "",
                                   span=f"{dates[0]} ~ {dates[-1]}" if dates else "시즌의 모든 날")


def season_what(request: Mapping) -> str:
    """장부 목록의 한 일 — 「시즌 「Peak」 다시 채우기(덮기) · 저장 2번」. 저장이 모두 덮기를 끄면 「(빈 칸만)」, 날짜를 고른 저장이 있으면
    「 · 날짜 일부」. 저장 수는 창을 누를 횟수다(빠진 저장은 세지 않는다 — 장부에 적힌 요청은 담당자가 준 그대로라 그 수다)."""
    saves = request.get("saves") or ()
    overwrite = "(빈 칸만)" if saves and not any(save.get("overwrite", True) for save in saves) else "(덮기)"
    part = " · 날짜 일부" if any(save.get("dates") is not None for save in saves) else ""
    name = (request.get("season") or {}).get("name") or ""
    return f"시즌 「{name}」 다시 채우기{overwrite}{part} · 저장 {len(saves)}번"
