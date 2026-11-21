"""addon_model.py — 부가옵션 가격 줄의 모양: 목록 줄, 편집 창이 보내는 칸, 읽은 값, 바꾸기 요청, 장부 항목.

가격 줄 하나 = 항목 하나(`addon_price`). 키는 ERP 의 번호 둘(부가옵션 번호 · 가격 줄 번호)을 굳힌 글자다. 필드는 둘 — `sell`
판매가(편집 창의 `price`, 엔진이 쓰는 값) · `supply` 공급 원가(`net_amount`, 비면 없음). 편집 창은 저장할 때 모든 칸을 덮어쓰므로
나머지 칸(이름 · 시즌 · 날짜 · 요금제 · 설명 · 적용 범위)은 딸린 칸으로 들고 다니며, 바꾸지 않고 창이 보인 그대로 다시 보낸다.

한 줄은 두 곳에서 읽는다. 목록 줄(`Listed` — 판매가 칸, 통화별 금액, 적용 대상)과 편집 창(`Line.form` — 저장 단추가 보낼 [이름, 값]
쌍 전부). 둘이 금액을 다르게 말하거나, 목록에 그 줄의 금액 기록(통화별 금액의 판매가)이 보이지 않으면 그 줄은 의심스럽다(`doubt`) —
편집 창이 저장된 원가를 보지 못해 빈칸으로 열린 줄일 수 있어서, 저장하면 그 원가가 지워진다. 계산은 그런 줄을 바꾸지 않는다.

브라우저 · 파일을 모르는 순수한 모양과 변환만 둔다.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "stay-price-change" / "scripts"))

from change_core.answers import BrowserError  # noqa: E402
from change_core.items import ItemState, Reading as Items, Refused, absent, item_key, key_fields  # noqa: E402
from change_core.money import money, money_text  # noqa: E402
from change_core.names import NameNote, name_notes  # noqa: E402
from change_core.window import Form, form_value, form_values  # noqa: E402

ITEM_KIND = "addon_price"
FIELDS = ("sell", "supply")
FIELD_LABELS = {"sell": "판매가", "supply": "공급 원가"}
FORM_NAMES = {"sell": "price", "supply": "net_amount"}        # 장부의 필드 → 편집 창이 보내는 칸 이름
PRESENT = "present"
SELL_POINT, NET_POINT = "판매가", "공급 원가"                # 목록의 통화별 금액 줄 머리(ERP PricePoint 라벨)
HIDDEN, DIFFER = "hidden", "differ"                          # 의심스러운 줄의 까닭
DOUBT_LABELS = {
    HIDDEN: "이 줄의 금액 기록이 ERP 화면에 보이지 않습니다(통화별 금액이 「별도 금액 없음」) — 편집 창이 저장된 공급 원가를 못 보고 "
            "빈칸으로 열렸을 수 있어, 저장하면 그 원가가 지워질 수 있습니다",
    DIFFER: "목록과 편집 창이 이 줄의 금액을 다르게 보입니다",
}
OFFERLESS = ""          # 부가옵션 변경은 오퍼 하나에 묶이지 않는다 — 장부의 오퍼 칸은 비운다(키가 호텔 안에서 하나다)


class ModelError(Refused):
    """요청 · 파일이 모양에 맞지 않는다 — 문장은 담당자에게 그대로 보여 줄 수 있다."""


@dataclass(frozen=True, order=True)
class LineKey:
    addon: str
    line: str


def line_item_key(key: LineKey) -> str:
    return item_key({"addon": key.addon, "line": key.line})


def key_of_item(text: str) -> LineKey:
    fields = key_fields(text)
    return LineKey(str(fields["addon"]), str(fields["line"]))


def hotel_label(name: str, hotel_id: str) -> str:
    return f"{name} (번호 {hotel_id})" if hotel_id else name


def decode_hotel(data) -> tuple[str, str]:
    if not isinstance(data, Mapping) or not str(data.get("id") or "").strip():
        raise ModelError("호텔은 stayAddonPrice.look() 의 hotel({id, name}) 그대로 적습니다")
    return str(data.get("name") or ""), str(data["id"]).strip()


def encode_hotel(name: str, hotel_id: str) -> dict:
    return {"id": hotel_id, "name": name}


# ───────────── 목록 줄 ─────────────

AMOUNT = re.compile(r"^(-?[\d,]+(?:\.\d+)?)\s+([A-Z]{3})$")
VALUE = re.compile(r"^(.+?):\s*(-?[\d,]+(?:\.\d+)?)\s+([A-Z]{3})$")


def amount_of(text: str, what: str) -> tuple[Decimal, str]:
    found = AMOUNT.match(" ".join(str(text).split()))
    if not found:
        raise BrowserError(f"{what}의 금액을 읽지 못했습니다: {text!r}")
    return money(found.group(1)), found.group(2)


@dataclass(frozen=True)
class Listed:
    """목록의 가격 줄 하나 — 화면이 보인 그대로. `values` 는 통화별 금액 줄의 원문(「판매가: 20.00 USD」 …)."""
    key: LineKey
    addon: str
    name: str
    sell_text: str
    values: tuple[str, ...]
    target: str
    scope: str = ""
    band: str = ""
    offer: str = ""

    @property
    def sell(self) -> Decimal:
        return amount_of(self.sell_text, f"{self.addon} · {self.name} 의 판매가")[0]

    @property
    def currency(self) -> str:
        return amount_of(self.sell_text, f"{self.addon} · {self.name} 의 판매가")[1]

    @property
    def title(self) -> str:
        """담당자에게 말하는 줄 이름 — 오퍼 · 부가옵션 · 가격 줄. 오퍼마다 이름이 같은 부가옵션 · 줄이 있어 오퍼부터 댄다."""
        return " · ".join(part for part in (self.offer, self.addon, self.name) if part)

    @property
    def label(self) -> str:
        """줄 이름에 적용 대상(시즌 · 날짜 · 요금제)까지 — 미리보기 · 장부 · 결과가 줄을 이것으로 부른다."""
        return f"{self.title} · {self.target}" if self.target else self.title

    def points(self) -> dict[str, Decimal]:
        """통화별 금액 가운데 호텔 통화(판매가 칸의 통화)의 줄 — 머리(판매가 · 공급 원가 …) → 금액. 다른 통화의 줄은 뺀다."""
        found = {}
        for text in self.values:
            match = VALUE.match(" ".join(text.split()))
            if not match:
                raise BrowserError(f"{self.addon} · {self.name} 의 통화별 금액을 읽지 못했습니다: {text!r}")
            if match.group(3) == self.currency:
                found[match.group(1).strip()] = money(match.group(2))
        return found


def decode_listed(addon: Mapping, row: Mapping) -> Listed:
    return Listed(LineKey(str(addon["id"]), str(row["id"])), str(addon["name"]), str(row["name"]), str(row["sell"]),
                  tuple(str(text) for text in row.get("values") or ()), str(row.get("target") or ""),
                  str(row.get("scope") or ""), str(row.get("band") or ""), str(addon.get("offer") or ""))


def encode_listed(item: Listed) -> dict:
    return dict(addon=item.key.addon, line=item.key.line, addon_name=item.addon, name=item.name, sell=item.sell_text,
                values=list(item.values), target=item.target, scope=item.scope, band=item.band, offer=item.offer)


def listed_from(data: Mapping) -> Listed:
    return Listed(LineKey(str(data["addon"]), str(data["line"])), str(data["addon_name"]), str(data["name"]), str(data["sell"]),
                  tuple(data["values"]), str(data["target"]), str(data.get("scope") or ""), str(data.get("band") or ""),
                  str(data.get("offer") or ""))


@dataclass(frozen=True)
class Listing:
    """look 의 답 — 호텔의 부가옵션과 가격 줄 전부(목록이 보인 그대로)."""
    hotel: str
    hotel_id: str
    read_at: str
    addons: tuple[tuple[str, str, str], ...]      # (번호, 이름, 오퍼)
    lines: tuple[Listed, ...]

    @property
    def currency(self) -> str:
        found = {line.currency for line in self.lines}
        if len(found) > 1:
            raise BrowserError(f"가격 줄의 통화가 하나가 아닙니다: {', '.join(sorted(found))}")
        return found.pop() if found else ""


def encode_listing(listing: Listing) -> dict:
    return dict(kind="addon_listing", hotel=encode_hotel(listing.hotel, listing.hotel_id), read_at=listing.read_at,
                currency=listing.currency,
                addons=[dict(id=addon_id, name=name, offer=offer) for addon_id, name, offer in listing.addons],
                lines=[encode_listed(line) for line in listing.lines])


def decode_listing(data: Mapping) -> Listing:
    if data.get("kind") != "addon_listing":
        raise ModelError("look 명령이 낸 파일(kind addon_listing)이 아닙니다")
    name, hotel_id = decode_hotel(data["hotel"])
    return Listing(name, hotel_id, str(data["read_at"]),
                   tuple((str(a["id"]), str(a["name"]), str(a.get("offer") or "")) for a in data["addons"]),
                   tuple(listed_from(line) for line in data["lines"]))


def listing_of(answer: Mapping, read_at: str) -> Listing:
    """stayAddonPrice.look() 의 답(조각을 붙인 것) → Listing."""
    name, hotel_id = decode_hotel(answer.get("hotel"))
    addons, lines = [], []
    for addon in answer.get("addons") or ():
        addons.append((str(addon["id"]), str(addon["name"]), str(addon.get("offer") or "")))
        lines += [decode_listed(addon, row) for row in addon.get("lines") or ()]
    keys = [line.key for line in lines]
    if len(set(keys)) != len(keys):
        raise BrowserError("목록에 같은 번호의 가격 줄이 둘 이상 있습니다")
    return Listing(name, hotel_id, read_at, tuple(addons), tuple(lines))


# ───────────── 편집 창 · 읽은 값 ─────────────

@dataclass(frozen=True)
class Line:
    """읽은 가격 줄 하나 — 목록 줄과 편집 창이 보낼 칸 전부. `labels` 는 고르는 칸이 보인 글자(시즌 · 요금제 이름 …)."""
    listed: Listed
    form: Form
    labels: Mapping[str, str] = field(default_factory=dict)
    title: str = ""

    @property
    def key(self) -> LineKey:
        return self.listed.key

    @property
    def name(self) -> str:
        return self.listed.title

    @property
    def label(self) -> str:
        return self.listed.label

    @property
    def sell(self) -> Decimal:
        text = form_value(self.form, FORM_NAMES["sell"], self.name)
        value = money(text)
        if value is None or not text.strip():
            raise BrowserError(f"{self.name} 편집 창의 판매가가 비었습니다")
        return value

    @property
    def supply(self) -> Decimal | None:
        text = form_value(self.form, FORM_NAMES["supply"], self.name)
        return None if not text.strip() else money(text)

    @property
    def doubt(self) -> str | None:
        points = self.listed.points()
        if SELL_POINT not in points:
            return HIDDEN
        if not (self.listed.sell == points[SELL_POINT] == self.sell) or points.get(NET_POINT) != self.supply:
            return DIFFER
        return None

    def fields(self) -> dict[str, Decimal | None]:
        return {"sell": self.sell, "supply": self.supply}

    def others(self) -> dict[str, str]:
        """딸린 칸 — 금액 둘 말고 편집 창이 보내는 칸 전부(같은 이름이 여럿이면 줄바꿈으로 잇는다), 그리고 목록 줄의 글자."""
        found: dict[str, list[str]] = {}
        for name, value in self.form:
            if name not in FORM_NAMES.values():
                found.setdefault(name, []).append(value)
        others = {f"form.{name}": "\n".join(values) for name, values in found.items()}
        others.update({"addon": self.listed.addon, "name": self.listed.name, "list.sell": self.listed.sell_text,
                       "list.values": "\n".join(self.listed.values), "list.target": self.listed.target})
        return others


def encode_line(line: Line) -> dict:
    return dict(listed=encode_listed(line.listed), form=[list(pair) for pair in line.form], labels=dict(line.labels),
                title=line.title)


def decode_line(data: Mapping) -> Line:
    return Line(listed_from(data["listed"]), tuple((str(name), str(value)) for name, value in data["form"]),
                {str(k): str(v) for k, v in (data.get("labels") or {}).items()}, str(data.get("title") or ""))


@dataclass(frozen=True)
class Snapshot:
    """읽기 한 번 — 물은 줄(`asked`, 읽은 범위)과 그 가운데 목록에 있던 줄(`lines`). 물었는데 없는 줄은 지워졌거나 번호가 바뀐 줄이다."""
    hotel: str
    hotel_id: str
    read_at: str
    asked: tuple[LineKey, ...]
    lines: Mapping[LineKey, Line]

    @property
    def currency(self) -> str:
        found = {line.listed.currency for line in self.lines.values()}
        if len(found) > 1:
            raise BrowserError(f"가격 줄의 통화가 하나가 아닙니다: {', '.join(sorted(found))}")
        return found.pop() if found else ""

    def missing(self) -> tuple[LineKey, ...]:
        return tuple(key for key in self.asked if key not in self.lines)

    def covers(self, key: LineKey) -> bool:
        return key in self.asked


def encode_snapshot(snapshot: Snapshot) -> dict:
    return dict(kind="addon_snapshot", hotel=encode_hotel(snapshot.hotel, snapshot.hotel_id), read_at=snapshot.read_at,
                currency=snapshot.currency, asked=[dict(addon=key.addon, line=key.line) for key in snapshot.asked],
                lines=[encode_line(line) for line in snapshot.lines.values()])


def decode_snapshot(data: Mapping) -> Snapshot:
    if data.get("kind") != "addon_snapshot":
        raise ModelError("read 명령이 낸 지금 값(kind addon_snapshot)이 아닙니다")
    name, hotel_id = decode_hotel(data["hotel"])
    lines = [decode_line(line) for line in data["lines"]]
    return Snapshot(name, hotel_id, str(data["read_at"]), tuple(LineKey(str(k["addon"]), str(k["line"])) for k in data["asked"]),
                    {line.key: line for line in lines})


def item_state(line: Line) -> ItemState:
    return ItemState(line.label, PRESENT, line.fields(), line.others())


def name_notes_of(snapshot: Snapshot, written: Iterable[tuple[str, str, Decimal | None]]) -> list[NameNote]:
    """바꾸는(바꾼) 필드마다(항목 키, 필드, 바꾸기 전 값) 그 가격 줄의 이름 · 설명과 그 부가옵션의 이름에 바꾸기 전 값이 적혔는지 —
    도우미는 이름과 설명을 바꾸지 않으므로 알린다(change_core.names). 부가옵션 자체의 설명은 목록에 보이지 않아 보지 않는다."""
    found = []
    for key, _field, before in written:
        line = snapshot.lines.get(key_of_item(key))
        if line is None:
            continue
        what = f"가격 줄 「{line.listed.title}」"
        addon = "부가옵션 「" + " · ".join(part for part in (line.listed.offer, line.listed.addon) if part) + "」"
        found += [(what, "이름", line.listed.name, before, False),
                  (what, "설명", "\n".join(form_values(line.form, "description")), before, False),
                  (addon, "이름", line.listed.addon, before, False)]
    return name_notes(found)


def snapshot_items(snapshot: Snapshot) -> Items:
    """읽은 값 → 공통 모양(항목 → 이름 · 상태 · 금액 · 딸린 칸). 물었는데 없는 줄은 없는 항목이다."""
    items = {}
    for key in snapshot.asked:
        line = snapshot.lines.get(key)
        items[(ITEM_KIND, line_item_key(key))] = item_state(line) if line else absent(f"가격 줄 {key.line}번")
    return items


def line_of(answer: Mapping) -> Line | None:
    """readLine 의 답(조각을 붙인 것) 하나 → Line. 목록에 그 줄이 없으면(missing) None. 답이 물은 호텔 · 부가옵션 · 줄의 것인지,
    편집 창이 그 부가옵션의 것인지 본다 — 아니면 BrowserError(페이지가 먼저 거절하지만 여기서 다시 본다)."""
    asked = answer.get("asked") or {}
    if not answer.get("ok"):
        raise BrowserError(f"가격 줄 {asked.get('line')}번을 읽지 못했습니다: {answer.get('error')}")
    if answer.get("missing"):
        return None
    hotel, addon, row, window = answer.get("hotel") or {}, answer["addon"], answer["line"], answer["window"]
    if str(hotel.get("id")) != str((asked.get("hotel") or {}).get("id")):
        raise BrowserError(f"readLine 의 답이 물은 호텔({(asked.get('hotel') or {}).get('id')})이 아닌 {hotel.get('id')} 에서 읽은 것입니다")
    if (str(addon["id"]), str(row["id"])) != (str(asked.get("addon")), str(asked.get("line"))):
        raise BrowserError(f"readLine 의 답이 물은 줄({asked.get('addon')} · {asked.get('line')})이 아닙니다")
    if str(window.get("addon")) != str(addon["name"]):
        raise BrowserError(f"가격 줄 {row['id']}번의 편집 창이 다른 부가옵션({window.get('addon')})의 것입니다")
    if window.get("errors"):
        raise BrowserError(f"가격 줄 {row['id']}번의 편집 창이 오류를 보입니다: {' / '.join(window['errors'])}")
    line = Line(decode_listed(addon, row), tuple((str(name), str(value)) for name, value in window["form"]),
                {str(k): str(v) for k, v in (window.get("labels") or {}).items()}, str(window.get("title") or ""))
    line.fields()                   # 금액 칸이 하나씩이고 읽히는지 지금 본다(아니면 BrowserError)
    return line


# ───────────── 바꾸기 요청 ─────────────

HOWS = ("amount", "percent", "value", "clear")


@dataclass(frozen=True)
class ChangeRequest:
    """줄 고르기(번호를 댄 줄 · 부가옵션의 모든 줄 · 전부) + 바꾸는 필드 하나 + 방법 하나(금액 · 퍼센트 · 새 값 · 비우기)."""
    hotel: str
    hotel_id: str
    field: str
    how: str
    figure: Decimal | None
    sentence: str
    lines: tuple[LineKey, ...] = ()
    addons: tuple[str, ...] = ()
    every: bool = False

    def selects(self, key: LineKey) -> bool:
        return self.every or key in self.lines or key.addon in self.addons

    def describe(self) -> str:
        what = FIELD_LABELS[self.field]
        if self.how == "clear":
            return f"{what} 비우기"
        if self.how == "value":
            return f"{what} {money_text(self.figure)} 으로"
        sign = "+" if self.figure >= 0 else ""
        return f"{what} {sign}{money_text(self.figure)}{'%' if self.how == 'percent' else ''}"


def decode_request(data: Mapping) -> ChangeRequest:
    if data.get("kind") != "addon_change":
        raise ModelError("바꾸기 요청은 kind addon_change 입니다")
    name, hotel_id = decode_hotel(data.get("hotel"))
    field_name = data.get("field", "sell")
    if field_name not in FIELDS:
        raise ModelError(f"field 는 sell(판매가) 또는 supply(공급 원가)입니다: {field_name!r}")
    given = [how for how in HOWS if data.get(how) is not None and data.get(how) is not False]   # 0 은 값이다(0 == False 라 `in` 으로 가리지 않는다)
    if len(given) != 1:
        raise ModelError("amount · percent · value · clear 가운데 하나만 적습니다")
    how = given[0]
    if how == "clear" and data["clear"] is not True:
        raise ModelError("clear 는 true 로 적습니다")
    if how == "clear" and field_name == "sell":
        raise ModelError("판매가는 비울 수 없습니다(ERP 가 비운 판매가를 받지 않습니다) — 무료면 value 0 이 아니라 그대로 둡니다")
    figure = None if how == "clear" else money(data[how])
    if how == "value" and figure < 0:
        raise ModelError("새 값은 0 이상입니다")
    lines = tuple(LineKey(str(item["addon"]), str(item["line"])) for item in data.get("lines") or ())
    addons = tuple(str(addon) for addon in data.get("addons") or ())
    every = data.get("all") is True
    if sum((bool(lines), bool(addons), every)) != 1:
        raise ModelError("고를 줄은 lines(줄 번호) · addons(부가옵션 번호) · all(true) 가운데 하나로 적습니다")
    sentence = str(data.get("sentence") or "").strip()
    if not sentence:
        raise ModelError("sentence(담당자가 한 말)가 비었습니다")
    return ChangeRequest(name, hotel_id, field_name, how, figure, sentence, lines, addons, every)


def encode_request(request: ChangeRequest) -> dict:
    data = dict(kind="addon_change", hotel=encode_hotel(request.hotel, request.hotel_id), field=request.field,
                sentence=request.sentence)
    data[request.how] = True if request.how == "clear" else money_text(request.figure)
    if request.lines:
        data["lines"] = [dict(addon=key.addon, line=key.line) for key in request.lines]
    elif request.addons:
        data["addons"] = list(request.addons)
    else:
        data["all"] = True
    return data


def chosen_lines(request: ChangeRequest, listing: Listing | None) -> tuple[LineKey, ...]:
    """요청이 고른 줄 — 번호를 댄 줄은 그대로, 부가옵션 · 전부로 고른 줄은 목록(look)에서 찾는다."""
    if request.lines:
        if listing is not None:
            known = {line.key for line in listing.lines}
            unknown = [key for key in request.lines if key not in known]
            if unknown:
                raise ModelError(f"목록에 없는 가격 줄입니다: {', '.join(f'{k.addon} · {k.line}' for k in unknown)} — look 의 번호를 씁니다")
        return tuple(dict.fromkeys(request.lines))
    if listing is None:
        raise ModelError("부가옵션 · 전부로 고른 요청은 목록이 필요합니다 — --look 으로 look 명령이 낸 파일을 줍니다")
    if listing.hotel_id != request.hotel_id:
        raise ModelError(f"목록은 {hotel_label(listing.hotel, listing.hotel_id)} 이고 요청은 "
                         f"{hotel_label(request.hotel, request.hotel_id)} 입니다")
    unknown = [addon for addon in request.addons if addon not in {a for a, _n, _o in listing.addons}]
    if unknown:
        raise ModelError(f"목록에 없는 부가옵션 번호입니다: {', '.join(unknown)}")
    keys = tuple(line.key for line in listing.lines if request.selects(line.key))
    if not keys:
        raise ModelError("고른 부가옵션에 가격 줄이 없습니다")
    return keys


def keys_text(keys: Iterable[LineKey]) -> list[dict]:
    return [dict(addon=key.addon, line=key.line) for key in keys]
