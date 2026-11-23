"""charge_model.py — 부과금의 모양: 목록 줄, 편집 창이 보내는 칸, 금액 칸의 자리, 읽은 값, 바꾸기 요청, 장부 항목.

부과금 하나는 저장 한 번에 통째로 다시 쓰인다 — 편집 창은 모든 칸을 보내고, 서버는 시간대 요율 줄과 연령별 단가를 지우고 받은
대로 다시 만든다(그래서 그 줄들의 ERP 번호는 저장마다 바뀐다). 장부의 항목 종류는 `charge` 하나이고, 키는 번호가 아니라 바뀌지 않는
것으로 정한다:

    {"charge": "701"}                            부과금 자체 — 필드 amount(정액 금액) · pct(정률 %) · onsite(현장 결제 금액)
    {"charge": "701", "time": "14:01-18:00"}     시간대 요율 줄 하나(시작~종료 시각) — 필드 amount · pct
    {"charge": "705", "age": "CHD"}              연령별 단가 하나(연령 구간 코드) — 필드 amount(1인 단가) · onsite(현장 1인 단가)

금액 칸 하나(`Place`)는 그 항목의 필드 하나다. 창에서는 (칸 이름, 같은 이름 가운데 몇 번째)로 짚는다 — 시간대 줄의 정률은
`tiers_pct` 의 그 줄 차례, 연령별 단가는 `age_rate_<구간 번호>`. 금액이 아닌 칸(종류 · 이름 · 방식 · 단위 · 금액의 뜻(미정/지정) ·
의무 · 날짜 · 객실 · 현장 통화 · 시간대의 시각과 방식 · 설명 · 적용 범위)은 부과금 항목의 딸린 칸으로 들고 다니며 창이 보인
그대로 다시 보낸다.

브라우저 · 파일을 모르는 순수한 모양과 변환만 둔다.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "stay-price-change" / "scripts"))

from change_core.answers import BrowserError  # noqa: E402
from change_core.items import ItemState, Reading, Refused, absent, item_key, key_fields  # noqa: E402
from change_core.money import money, money_text  # noqa: E402
from change_core.words import josa  # noqa: E402
from change_core.names import NameNote, name_notes  # noqa: E402
from change_core.window import Form, form_value, form_values  # noqa: E402

ITEM_KIND = "charge"
PRESENT = "present"
OFFERLESS = ""           # 부과금 변경은 호텔 안의 부과금 번호로 짚는다 — 장부의 오퍼 칸은 비운다(부가옵션 도우미와 같다)

MAIN, TIME, AGE = "main", "time", "age"
PART_FIELDS = {MAIN: ("amount", "pct", "onsite"), TIME: ("amount", "pct"), AGE: ("amount", "onsite")}
FIELD_LABELS = {(MAIN, "amount"): "정액 금액", (MAIN, "pct"): "정률(%)", (MAIN, "onsite"): "현장 결제 금액",
                (TIME, "amount"): "정액 금액", (TIME, "pct"): "정률(%)",
                (AGE, "amount"): "1인 단가", (AGE, "onsite"): "현장 1인 단가"}
# 바꿀 수 있는 금액 칸의 이름 — 페이지의 applyCharge 가 받는 이름과 같다. 이 밖의 칸은 저장 단계가 만들어질 때 거절한다
AMOUNT_NAME = re.compile(r"^(amount|pct|onsite_amount|tiers_amount|tiers_pct|age_rate_\d+|onsite_age_rate_\d+)$")
TYPED = re.compile(r"^\d+(\.\d+)?$")
FLAT, PCT = "0", "1"                 # basis — 정액 · 1박 요금의 %
PER_PERSON = "2"                     # per — 인당
SET, BLANK = "set", "blank"          # amount_mode · pct_mode — 지정 · 미정
MANDATORY = "mandatory"
UNSET_LABEL = "---------"
ADULT_WORDS = ("성인", "어른", "대인")   # 연령별 단가가 있는 부과금에서도 성인 금액은 부과금 자체의 금액이다(commands.md 「담당자의 말 → 금액 칸」)


class ModelError(Refused):
    """요청 · 파일이 모양에 맞지 않는다 — 문장은 담당자에게 그대로 보여 줄 수 있다."""


def hotel_label(name: str, hotel_id: str) -> str:
    return f"{name} (번호 {hotel_id})" if hotel_id else name


def decode_hotel(data) -> tuple[str, str]:
    if not isinstance(data, Mapping) or not str(data.get("id") or "").strip():
        raise ModelError("호텔은 stayCharge.look() 의 hotel({id, name}) 그대로 적습니다")
    return str(data.get("name") or ""), str(data["id"]).strip()


def encode_hotel(name: str, hotel_id: str) -> dict:
    return {"id": hotel_id, "name": name}


# ───────────── 금액 칸의 자리 ─────────────

@dataclass(frozen=True, order=True)
class Place:
    """금액 칸 하나 — 부과금 번호, 어느 부분(main · time · age), 그 부분을 가리키는 글자(시각 「14:01-18:00」 · 구간 코드), 필드."""
    charge: str
    part: str
    at: str
    field: str

    def __post_init__(self):
        if self.part not in PART_FIELDS or self.field not in PART_FIELDS[self.part]:
            raise ModelError(f"그런 금액 칸은 없습니다: {self.part} · {self.field} — 부과금 자체는 amount · pct · onsite, "
                             "시간대 줄은 amount · pct, 연령별 단가는 amount · onsite 입니다")
        if (self.part == MAIN) != (self.at == ""):
            raise ModelError("시간대 줄은 시각(「14:01-18:00」)으로, 연령별 단가는 구간 코드로 짚습니다")

    @property
    def key(self) -> str:
        return part_key(self.charge, self.part, self.at)

    @property
    def field_label(self) -> str:
        return FIELD_LABELS[(self.part, self.field)]


def part_key(charge: str, part: str, at: str) -> str:
    fields = {"charge": charge}
    if part == TIME:
        fields["time"] = at
    elif part == AGE:
        fields["age"] = at
    return item_key(fields)


def part_of_key(text: str) -> tuple[str, str, str]:
    """장부의 항목 키 → (부과금 번호, 부분, 가리키는 글자)."""
    fields = key_fields(text)
    if "time" in fields:
        return str(fields["charge"]), TIME, str(fields["time"])
    if "age" in fields:
        return str(fields["charge"]), AGE, str(fields["age"])
    return str(fields["charge"]), MAIN, ""


def charge_of_key(text: str) -> str:
    """저장 한 번이 다시 쓰는 단위 — 부과금 번호(시간대 · 연령별 단가 항목도 그 부과금에 든다)."""
    return part_of_key(text)[0]


def field_label_of(key: str, field_name: str) -> str:
    return FIELD_LABELS[(part_of_key(key)[1], field_name)]


# ───────────── 목록 줄 ─────────────

@dataclass(frozen=True)
class Listed:
    """목록의 부과금 줄 하나 — 화면이 보인 그대로. `amount` 는 금액 칸의 줄들(시간대 · 연령별 · 현장 결제 줄, 단위)."""
    offer: str
    offer_name: str
    id: str
    name: str
    kind: str
    basis: str
    amount: tuple[str, ...]
    scope: str
    dates: str


def decode_listed(offer: Mapping, row: Mapping) -> Listed:
    return Listed(str(offer["id"]), str(offer.get("name") or ""), str(row["id"]), str(row["name"]), str(row.get("kind") or ""),
                  str(row.get("basis") or ""), tuple(str(line) for line in row.get("amount") or ()), str(row.get("scope") or ""),
                  str(row.get("dates") or ""))


def encode_listed(item: Listed) -> dict:
    return dict(offer=item.offer, offer_name=item.offer_name, id=item.id, name=item.name, kind=item.kind, basis=item.basis,
                amount=list(item.amount), scope=item.scope, dates=item.dates)


def listed_from(data: Mapping) -> Listed:
    return Listed(str(data["offer"]), str(data["offer_name"]), str(data["id"]), str(data["name"]), str(data["kind"]),
                  str(data["basis"]), tuple(data["amount"]), str(data["scope"]), str(data["dates"]))


@dataclass(frozen=True)
class Listing:
    """look 의 답 — 호텔의 오퍼마다 부과금 줄 전부(목록이 보인 그대로)."""
    hotel: str
    hotel_id: str
    read_at: str
    offers: tuple[tuple[str, str], ...]          # (번호, 이름)
    charges: tuple[Listed, ...]


def listing_of(answer: Mapping, read_at: str) -> Listing:
    """stayCharge.look() 의 답(조각을 붙인 것) → Listing."""
    name, hotel_id = decode_hotel(answer.get("hotel"))
    offers, charges = [], []
    for offer in answer.get("offers") or ():
        offers.append((str(offer["id"]), str(offer.get("name") or "")))
        charges += [decode_listed(offer, row) for row in offer.get("charges") or ()]
    ids = [item.id for item in charges]
    if len(set(ids)) != len(ids):
        raise BrowserError("목록에 같은 번호의 부과금이 둘 이상 있습니다")
    return Listing(name, hotel_id, read_at, tuple(offers), tuple(charges))


def encode_listing(listing: Listing) -> dict:
    return dict(kind="charge_listing", hotel=encode_hotel(listing.hotel, listing.hotel_id), read_at=listing.read_at,
                offers=[dict(id=offer_id, name=name) for offer_id, name in listing.offers],
                charges=[encode_listed(item) for item in listing.charges])


def decode_listing(data: Mapping) -> Listing:
    if data.get("kind") != "charge_listing":
        raise ModelError("look 명령이 낸 파일(kind charge_listing)이 아닙니다")
    name, hotel_id = decode_hotel(data["hotel"])
    return Listing(name, hotel_id, str(data["read_at"]), tuple((str(o["id"]), str(o["name"])) for o in data["offers"]),
                   tuple(listed_from(item) for item in data["charges"]))


# ───────────── 편집 창 ─────────────

@dataclass(frozen=True)
class Band:
    """연령 구간 칸 하나 — 칸 이름(`age_rate_<구간 번호>` · `onsite_age_rate_<구간 번호>`), 구간 코드, 화면의 이름."""
    field: str
    code: str
    label: str


@dataclass(frozen=True)
class TimeBand:
    index: int
    start: str
    end: str
    basis: str
    amount: str
    pct: str

    @property
    def at(self) -> str:
        return f"{self.start}-{self.end}"


@dataclass(frozen=True)
class AgeRate:
    code: str
    label: str
    amount_field: str | None
    onsite_field: str | None


@dataclass(frozen=True)
class Charge:
    """읽은 부과금 하나 — 목록 줄과 편집 창이 보낼 칸 전부. `labels` 는 고르는 칸이 보인 글자, `currency` 는 호텔 통화(창의 「정액
    금액 (USD)」), `bands` 는 연령 구간 칸들."""
    listed: Listed
    form: Form
    labels: Mapping[str, str] = field(default_factory=dict)
    bands: tuple[Band, ...] = ()
    title: str = ""
    currency: str = ""

    @property
    def id(self) -> str:
        return self.listed.id

    @property
    def offer(self) -> str:
        return self.listed.offer

    @property
    def name(self) -> str:
        return self.listed.name

    @property
    def label(self) -> str:
        return f"{self.listed.offer_name} · {self.name}" if self.listed.offer_name else self.name

    def one(self, name: str) -> str:
        return form_value(self.form, name, f"부과금 {self.id}번")

    @property
    def basis(self) -> str:
        return self.one("basis")

    @property
    def per(self) -> str:
        return self.one("per")

    @property
    def onsite_currency(self) -> str:
        """현장 결제 통화 코드(창의 고른 글자) — 없으면 빈 글자."""
        if not self.one("onsite_currency").strip():
            return ""
        return (self.labels.get("onsite_currency") or "").strip()

    def times(self) -> tuple[TimeBand, ...]:
        columns = [form_values(self.form, f"tiers_{name}") for name in ("time_from", "time_to", "basis", "amount", "pct")]
        if len({len(column) for column in columns}) != 1:
            raise BrowserError(f"부과금 {self.id}번 편집 창의 시간대 줄 칸 수가 서로 다릅니다 — 창이 생각한 모양이 아닙니다")
        bands = tuple(TimeBand(index, *values) for index, values in enumerate(zip(*columns)))
        keys = [band.at for band in bands]
        if len(set(keys)) != len(keys):
            raise BrowserError(f"부과금 {self.id}번에 같은 시각의 시간대 줄이 둘 이상 있습니다")
        return bands

    def ages(self) -> tuple[AgeRate, ...]:
        found: dict[str, dict] = {}
        for band in self.bands:
            onsite = band.field.startswith("onsite_age_rate_")
            entry = found.setdefault(band.code, dict(label=band.label, amount=None, onsite=None))
            slot = "onsite" if onsite else "amount"
            if entry[slot] is not None:
                raise BrowserError(f"부과금 {self.id}번에 연령 구간 코드 {band.code} 의 칸이 둘 이상 있습니다")
            entry[slot] = band.field
            if not onsite:
                entry["label"] = band.label
        return tuple(AgeRate(code, entry["label"], entry["amount"], entry["onsite"]) for code, entry in found.items())

    def normal(self, place: Place) -> Place:
        """요청이 연령 구간을 화면의 이름(「소아」)으로 짚었으면 구간 코드로 바꾼 자리 — 장부의 키는 코드로 적는다. 성인은 연령 구간이
        아니다 — 부과금 자체의 금액이 성인 금액이다(연령별 단가가 비면 「성인가와 같음」)."""
        if place.part != AGE or any(rate.code == place.at for rate in self.ages()):
            return place
        named = [rate.code for rate in self.ages() if rate.label == place.at]
        if not named and place.at.strip() in ADULT_WORDS:
            raise ModelError(f"부과금 {self.id}번의 「{place.at}」 요금은 연령별 단가가 아니라 부과금 자체의 금액입니다 — "
                             '"age" 없이 "field": "amount" 로 적습니다')
        if len(named) != 1:
            raise ModelError(f"부과금 {self.id}번에 연령 구간 {josa(place.at, '이가')} {'둘 이상' if named else '없습니다'} — 구간 코드로 적습니다")
        return Place(place.charge, place.part, named[0], place.field)

    def where(self, place: Place) -> tuple[str, int]:
        """금액 칸 → 창의 (칸 이름, 몇 번째). 창에 그 칸이 없으면 ModelError."""
        if place.part == MAIN:
            return {"amount": ("amount", 0), "pct": ("pct", 0), "onsite": ("onsite_amount", 0)}[place.field]
        if place.part == TIME:
            band = next((band for band in self.times() if band.at == place.at), None)
            if band is None:
                raise ModelError(f"부과금 {self.id}번에 {place.at.replace('-', '~')} 시간대 줄이 없습니다")
            return f"tiers_{place.field}", band.index
        rate = next((rate for rate in self.ages() if rate.code == place.at), None)
        name = None if rate is None else rate.amount_field if place.field == "amount" else rate.onsite_field
        if name is None:
            raise ModelError(f"부과금 {self.id}번에 연령 구간 {place.at} 의 {place.field_label} 칸이 없습니다")
        return name, 0

    def text(self, place: Place) -> str:
        name, nth = self.where(place)
        values = form_values(self.form, name)
        if nth >= len(values):
            raise BrowserError(f"부과금 {self.id}번 편집 창에 {name} {nth + 1}번째 칸이 없습니다")
        return values[nth]

    def value(self, place: Place) -> Decimal | None:
        """그 칸의 금액. 비었으면 None — 「미정」(정액 · 정률은 금액의 뜻이 「미정」이면 칸에 무엇이 있든 ERP 가 비워 저장한다),
        연령별 단가는 「성인가와 같음」, 현장 결제는 「현장 금액 미정」."""
        if place.part == MAIN and place.field in ("amount", "pct") and self.one(f"{place.field}_mode") != SET:
            return None
        text = self.text(place).strip()
        return None if not text else money(text)

    def places(self) -> tuple[Place, ...]:
        """이 부과금의 금액 칸 전부 — 부과금 자체 셋, 시간대 줄마다 둘, 연령 구간마다 둘."""
        out = [Place(self.id, MAIN, "", name) for name in PART_FIELDS[MAIN]]
        for band in self.times():
            out += [Place(self.id, TIME, band.at, name) for name in PART_FIELDS[TIME]]
        for rate in self.ages():
            out += [Place(self.id, AGE, rate.code, name) for name in PART_FIELDS[AGE]
                    if (rate.amount_field if name == "amount" else rate.onsite_field)]
        return tuple(out)

    def part_label(self, part: str, at: str) -> str:
        if part == TIME:
            return f"{self.label} · {at.replace('-', '~')} 시간대"
        if part == AGE:
            rate = next((rate for rate in self.ages() if rate.code == at), None)
            return f"{self.label} · {rate.label if rate else at} 단가"
        return self.label

    def place_label(self, place: Place) -> str:
        return f"{self.part_label(place.part, place.at)} {place.field_label}"

    def others(self) -> dict[str, str]:
        """딸린 칸 — 금액 칸 말고 편집 창이 보내는 칸 전부(같은 이름이 여럿이면 줄바꿈으로 잇는다), 그리고 목록 줄의 글자."""
        found: dict[str, list[str]] = {}
        for name, value in self.form:
            if not AMOUNT_NAME.match(name):
                found.setdefault(name, []).append(value)
        others = {f"form.{name}": "\n".join(values) for name, values in found.items()}
        others.update({"name": self.name, "offer": self.offer, "list.kind": self.listed.kind, "list.basis": self.listed.basis,
                       "list.amount": "\n".join(self.listed.amount), "list.scope": self.listed.scope,
                       "list.dates": self.listed.dates})
        return others

    def items(self) -> dict[str, ItemState]:
        """장부 항목 → 상태. 부과금 자체에 딸린 칸이 모두 붙고, 시간대 · 연령별 단가 항목은 금액만 든다."""
        grouped: dict[tuple[str, str], dict] = {}
        for place in self.places():
            grouped.setdefault((place.part, place.at), {})[place.field] = self.value(place)
        out = {}
        for (part, at), values in grouped.items():
            out[part_key(self.id, part, at)] = ItemState(self.part_label(part, at), PRESENT, values,
                                                         self.others() if part == MAIN else {})
        return out


def encode_charge(charge: Charge) -> dict:
    return dict(listed=encode_listed(charge.listed), form=[list(pair) for pair in charge.form], labels=dict(charge.labels),
                bands=[dict(field=band.field, code=band.code, label=band.label) for band in charge.bands],
                title=charge.title, currency=charge.currency)


def decode_charge(data: Mapping) -> Charge:
    return Charge(listed_from(data["listed"]), tuple((str(name), str(value)) for name, value in data["form"]),
                  {str(k): str(v) for k, v in (data.get("labels") or {}).items()},
                  tuple(Band(str(b["field"]), str(b["code"]), str(b.get("label") or "")) for b in data.get("bands") or ()),
                  str(data.get("title") or ""), str(data.get("currency") or ""))


def charge_of(answer: Mapping) -> Charge | None:
    """readCharge 의 답(조각을 붙인 것) 하나 → Charge. 목록에 그 부과금이 없으면(missing) None. 답이 물은 호텔 · 오퍼 · 부과금의
    것인지, 편집 창이 그 부과금(이름)의 것인지 본다 — 아니면 BrowserError(페이지가 먼저 거절하지만 여기서 다시 본다)."""
    asked = answer.get("asked") or {}
    if not answer.get("ok"):
        raise BrowserError(f"부과금 {asked.get('charge')}번을 읽지 못했습니다: {answer.get('error')}")
    if answer.get("missing"):
        return None
    hotel, offer, row, window = answer.get("hotel") or {}, answer["offer"], answer["charge"], answer["window"]
    if str(hotel.get("id")) != str((asked.get("hotel") or {}).get("id")):
        raise BrowserError(f"readCharge 의 답이 물은 호텔({(asked.get('hotel') or {}).get('id')})이 아닌 {hotel.get('id')} 에서 읽은 것입니다")
    if (str(offer["id"]), str(row["id"])) != (str(asked.get("offer")), str(asked.get("charge"))):
        raise BrowserError(f"readCharge 의 답이 물은 부과금({asked.get('offer')} · {asked.get('charge')})이 아닙니다")
    if window.get("errors"):
        raise BrowserError(f"부과금 {row['id']}번의 편집 창이 오류를 보입니다: {' / '.join(window['errors'])}")
    charge = Charge(decode_listed(offer, row), tuple((str(name), str(value)) for name, value in window["form"]),
                    {str(k): str(v) for k, v in (window.get("labels") or {}).items()},
                    tuple(Band(str(b["field"]), str(b["code"]), str(b.get("label") or "")) for b in window.get("bands") or ()),
                    str(window.get("title") or ""), str(window.get("currency") or ""))
    if charge.one("name") != charge.name:
        raise BrowserError(f"부과금 {row['id']}번의 편집 창 이름({charge.one('name')})이 목록의 이름({charge.name})과 다릅니다")
    charge.items()                  # 칸이 생각한 모양인지 지금 본다(아니면 BrowserError)
    return charge


# ───────────── 읽은 값 ─────────────

ChargeRef = tuple[str, str]          # (오퍼 번호, 부과금 번호)


@dataclass(frozen=True)
class Snapshot:
    """읽기 한 번 — 물은 부과금(`asked`, 읽은 범위)과 그 가운데 목록에 있던 부과금(`charges`, 부과금 번호 → Charge)."""
    hotel: str
    hotel_id: str
    read_at: str
    asked: tuple[ChargeRef, ...]
    charges: Mapping[str, Charge]

    @property
    def currency(self) -> str:
        found = {charge.currency for charge in self.charges.values() if charge.currency}
        if len(found) > 1:
            raise BrowserError(f"부과금 창의 호텔 통화가 하나가 아닙니다: {', '.join(sorted(found))}")
        return found.pop() if found else ""

    def missing(self) -> tuple[ChargeRef, ...]:
        return tuple(ref for ref in self.asked if ref[1] not in self.charges)

    def covers(self, charge: str) -> bool:
        return any(ref[1] == charge for ref in self.asked)


def encode_snapshot(snapshot: Snapshot) -> dict:
    return dict(kind="charge_snapshot", hotel=encode_hotel(snapshot.hotel, snapshot.hotel_id), read_at=snapshot.read_at,
                currency=snapshot.currency, asked=[dict(offer=offer, charge=charge) for offer, charge in snapshot.asked],
                charges=[encode_charge(charge) for charge in snapshot.charges.values()])


def decode_snapshot(data: Mapping) -> Snapshot:
    if data.get("kind") != "charge_snapshot":
        raise ModelError("read 명령이 낸 지금 값(kind charge_snapshot)이 아닙니다")
    name, hotel_id = decode_hotel(data["hotel"])
    charges = [decode_charge(item) for item in data["charges"]]
    return Snapshot(name, hotel_id, str(data["read_at"]), tuple((str(r["offer"]), str(r["charge"])) for r in data["asked"]),
                    {charge.id: charge for charge in charges})


def snapshot_items(snapshot: Snapshot) -> Reading:
    """읽은 값 → 공통 모양(항목 → 이름 · 상태 · 금액 · 딸린 칸). 물었는데 없는 부과금은 그 부과금 항목이 없는 것이다."""
    items = {}
    for _offer, charge_id in snapshot.asked:
        charge = snapshot.charges.get(charge_id)
        if charge is None:
            items[(ITEM_KIND, part_key(charge_id, MAIN, ""))] = absent(f"부과금 {charge_id}번")
            continue
        items.update({(ITEM_KIND, key): state for key, state in charge.items().items()})
    return items


def name_notes_of(snapshot: Snapshot, written: Iterable[tuple[str, str, Decimal | None]]) -> list[NameNote]:
    """바꾸는(바꾼) 금액 칸마다(항목 키, 필드, 바꾸기 전 값) 그 부과금의 이름 · 설명에 바꾸기 전 값이 적혔는지 — 도우미는 이름과
    설명을 바꾸지 않으므로 알린다(change_core.names). 정률 칸은 `%` 가 붙은 숫자만 본다."""
    found = []
    for key, field_name, before in written:
        charge = snapshot.charges.get(charge_of_key(key))
        if charge is None:
            continue
        what, percent = f"부과금 「{charge.label}」", field_name == "pct"
        found += [(what, "이름", charge.name, before, percent),
                  (what, "설명", "\n".join(form_values(charge.form, "description")), before, percent)]
    return name_notes(found)


# ───────────── 바꾸기 요청 ─────────────

HOWS = ("amount", "percent", "value")


@dataclass(frozen=True)
class Target:
    offer: str
    place: Place


@dataclass(frozen=True)
class ChangeRequest:
    """바꿀 금액 칸들(부과금마다 오퍼 번호와 함께) + 방법 하나(금액 · 퍼센트 · 새 값). 칸을 비우는 방법은 없다."""
    hotel: str
    hotel_id: str
    targets: tuple[Target, ...]
    how: str
    figure: Decimal
    sentence: str

    def charges(self) -> tuple[ChargeRef, ...]:
        return tuple(dict.fromkeys((target.offer, target.place.charge) for target in self.targets))

    def describe(self, parts: Mapping[str, str] | None = None) -> str:
        """장부 한 줄의 한 일 — 「정률(%) 60으로」. `parts` 는 금액 칸의 부분(항목 키) → 그 부분의 이름(「소아 단가」 ·
        「14:01~18:00 시간대」) — 연령별 단가 · 시간대 줄이면 어느 것인지 앞에 댄다(같은 종류가 여럿인 부과금 — 시운전 9)."""
        names = " · ".join(dict.fromkeys(
            f"{(parts or {})[target.place.key]} · {target.place.field_label}" if (parts or {}).get(target.place.key)
            else target.place.field_label for target in self.targets))
        if self.how == "value":
            return f"{names} {josa(money_text(self.figure), '으로')}"
        sign = "+" if self.figure >= 0 else ""
        return f"{names} {sign}{money_text(self.figure)}{'%' if self.how == 'percent' else ''}"


def decode_target(item: Mapping) -> Target:
    offer, charge = str(item.get("offer") or "").strip(), str(item.get("charge") or "").strip()
    if not offer.isdigit() or not charge.isdigit():
        raise ModelError("금액 칸마다 offer(오퍼 번호)와 charge(부과금 번호)를 look 의 번호 그대로 적습니다")
    time, age = item.get("time"), item.get("age")
    if time is not None and age is not None:
        raise ModelError("한 금액 칸에는 time(시간대) 과 age(연령 구간) 가운데 하나만 적습니다")
    part, at = (TIME, str(time)) if time is not None else (AGE, str(age).strip()) if age is not None else (MAIN, "")
    if part == TIME:
        at = re.sub(r"\s*[~\-]\s*", "-", at.strip())
    if part == TIME and not re.fullmatch(r"\d{2}:\d{2}-\d{2}:\d{2}", at):
        raise ModelError(f"시간대는 창에 보이는 시작~종료 시각을 「14:01-18:00」 꼴로 적습니다: {at!r}")
    return Target(offer, Place(charge, part, at, str(item.get("field") or "")))


def encode_target(target: Target) -> dict:
    data = dict(offer=target.offer, charge=target.place.charge, field=target.place.field)
    if target.place.part == TIME:
        data["time"] = target.place.at
    elif target.place.part == AGE:
        data["age"] = target.place.at
    return data


def decode_request(data: Mapping) -> ChangeRequest:
    if data.get("kind") != "charge_change":
        raise ModelError("바꾸기 요청은 kind charge_change 입니다")
    name, hotel_id = decode_hotel(data.get("hotel"))
    if data.get("clear") is not None:
        raise ModelError("부과금 금액은 비우지 않습니다(비우면 ERP 가 그 금액을 「미정」으로 바꿉니다) — 무료면 value 0 으로 적습니다")
    given = [how for how in HOWS if data.get(how) is not None and data.get(how) is not False]   # 0 은 값이다(0 == False 라 `in` 으로 가리지 않는다)
    if len(given) != 1:
        raise ModelError("amount · percent · value 가운데 하나만 적습니다")
    how = given[0]
    figure = money(data[how])
    if how == "value" and figure < 0:
        raise ModelError("새 값은 0 이상입니다")
    targets = tuple(decode_target(item) for item in data.get("amounts") or ())
    if not targets:
        raise ModelError("amounts(바꿀 금액 칸 목록)가 비었습니다")
    places = [target.place for target in targets]
    if len(set(places)) != len(places):
        raise ModelError("같은 금액 칸을 두 번 적었습니다")
    offers: dict[str, str] = {}
    for target in targets:
        if offers.setdefault(target.place.charge, target.offer) != target.offer:
            raise ModelError(f"부과금 {target.place.charge}번의 오퍼 번호가 칸마다 다릅니다")
    sentence = str(data.get("sentence") or "").strip()
    if not sentence:
        raise ModelError("sentence(담당자가 한 말)가 비었습니다")
    return ChangeRequest(name, hotel_id, targets, how, figure, sentence)


def encode_request(request: ChangeRequest) -> dict:
    return dict(kind="charge_change", hotel=encode_hotel(request.hotel, request.hotel_id),
                amounts=[encode_target(target) for target in request.targets], sentence=request.sentence,
                **{request.how: money_text(request.figure)})


def known_charges(request: ChangeRequest, listing: Listing | None) -> tuple[ChargeRef, ...]:
    """요청이 짚은 부과금 — 목록(look)이 있으면 그 오퍼의 그 부과금이 목록에 있는지 본다."""
    refs = request.charges()
    if listing is None:
        return refs
    if listing.hotel_id != request.hotel_id:
        raise ModelError(f"목록은 {hotel_label(listing.hotel, listing.hotel_id)} 이고 요청은 "
                         f"{hotel_label(request.hotel, request.hotel_id)} 입니다")
    known = {(item.offer, item.id) for item in listing.charges}
    unknown = [f"{offer} · {charge}" for offer, charge in refs if (offer, charge) not in known]
    if unknown:
        raise ModelError(f"목록에 없는 부과금입니다(오퍼 · 부과금): {', '.join(unknown)} — look 의 번호를 씁니다")
    return refs
