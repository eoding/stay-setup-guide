"""promotion_model.py — 프로모션 할인의 모양: 목록 줄, 편집 창이 보내는 칸, 할인 단(티어), 읽은 값, 바꾸기 요청, 장부 항목.

프로모션 하나는 저장 한 번에 통째로 다시 쓰인다 — 편집 창은 모든 칸을 보내고, 서버는 할인 규칙(발동 조건 · 혜택 방식 · 단위 · 단)을
받은 칸으로 다시 만든다. 단에는 화면에 칸이 없는 설정(취소 조건 같은 것)이 붙어 있을 수 있다. 그 설정을 지키는 ERP 는 편집 창의
뿌리에 표식(`data-stay-keeps-off-form-keys="1"`)을 달고, 그런 설정이 있는 단의 줄에 그 이름을 단다(`data-stay-off-form-keys`). 표식이
없는 ERP 는 저장하면 그 설정을 지운다 — 도우미는 읽고 미리보기만 하고 저장하지 않는다(`GATE`).

장부의 항목 종류는 `promotion` 하나이고, 키는 번호와 기준값이다:

    {"promotion": "9001"}                    프로모션 자체 — 금액 필드 없음. 딸린 칸(창이 보내는 칸 전부 · 표식 · 목록 줄의 글자)을 들고
                                             다니며 창이 보인 그대로 다시 보낸다
    {"promotion": "9001", "tier": "21"}      할인 단 하나(기준값 21) — 필드 value(할인율 · 할인 금액 · 무료 숙박 박수)

단의 줄마다 창이 보내는 숨은 칸 `tiers_origin` 은 그 줄이 저장된 어느 단에서 왔는지다 — 저장된 단의 기준값 글자, 「단 추가」로 더한
줄은 빈 값. ERP 는 저장할 때 이 값으로 줄과 저장된 단을 짝지어 그 단의 화면 밖 설정을 잇는다. 도우미는 읽은 그대로 보내고 치지 않는다
(`form` 에 그대로 있고, 저장 단계가 치는 칸은 `tiers_value` 뿐이다). `?`(UNSURE_ORIGIN)는 ERP 가 그 줄이 어느 단에서 왔는지 모른다는
뜻이다 — 숨은 칸 없이 보낸 요청이 거절된 뒤 다시 그린 창에만 나온다. 그런 창은 저장하지 않는다(ORIGIN_UNKNOWN — 명령의 계산 · begin
· 페이지가 모두 거절한다). 도우미는 읽을 때마다 창을 새로 열므로 보통은 나오지 않는다.

단의 이름이 기준값인 것은 ERP 와 같다(저장된 단의 정체성 `tiers_origin` 이 기준값 글자다). 도우미는 기준값을 바꾸지 않으므로 그 사이
다른 사람이 기준값을 바꾸지 않는 한 같은 단을 가리킨다. 바꿨으면 그 키의 단이 없어진 것이다 — 적용 직전 견주기가 멈추고, 되돌리기는
그 단을 「도우미 밖」으로 그대로 둔다.

브라우저 · 파일을 모르는 순수한 모양과 변환만 둔다.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "stay-price-change" / "scripts"))

from change_core.answers import BrowserError  # noqa: E402
from change_core.items import ItemState, Reading, Refused, absent, item_key, key_fields  # noqa: E402
from change_core.money import money, money_text  # noqa: E402
from change_core.words import josa  # noqa: E402
from change_core.names import NameNote, name_notes  # noqa: E402
from change_core.window import Form, form_value, form_values  # noqa: E402

ITEM_KIND = "promotion"
PRESENT = "present"
OFFERLESS = ""           # 프로모션 변경은 호텔 안의 프로모션 번호로 짚는다 — 장부의 오퍼 칸은 비운다(부가옵션 · 부과금 도우미와 같다)
COMMON, COMMON_NAME = "0", "전 오퍼 공통"   # 오퍼 표식이 없는 카드 — 오퍼 번호 대신 0(ERP 의 새로 만들기 주소 `offers/0/` 과 같다)
VALUE = "tiers_value"    # 도우미가 치는 단 하나의 칸 — 이 밖의 칸은 저장 단계가 만들어질 때 거절한다
TYPED = re.compile(r"^\d+(\.\d+)?$")
# 페이지의 글자 맞추기(stay_price.js 의 C)가 빈칸으로 보는 글자 — 자바스크립트 정규식의 \s 와 같은 묶음
_SPACES = re.compile("[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+")


def shown_name(text: str) -> str:
    """이름을 페이지가 목록의 글자를 읽는 대로(stay_price.js 의 C) — NFC, 빈칸 묶음은 하나로, 앞뒤 빈칸 없이. 목록의 이름은 페이지가 이미
    이렇게 읽어 오고 편집 창의 이름 칸은 날 글자라, 둘을 견줄 때는 둘 다 이것으로 맞춘다(빈칸 둘 · 끝 빈칸 · 풀어 쓴 한글(NFD)이 든
    이름도 같은 이름이다). 페이지의 applyPromotion 도 창의 이름 칸을 같은 셈으로 맞춰 견준다."""
    return _SPACES.sub(" ", unicodedata.normalize("NFC", str(text))).strip(" ")
GATE = ("이 ERP 는 아직 프로모션을 화면으로 저장하면 화면에 안 보이는 설정이 지워질 수 있어, 도우미가 저장하지 않습니다 — ERP 가 "
        "고쳐진 뒤에 됩니다")
UNSURE_ORIGIN = "?"      # 숨은 칸 tiers_origin 의 이 값 — ERP 가 그 줄이 어느 저장된 단에서 왔는지 모른다(거절된 요청 뒤 다시 그린 창)
ORIGIN_UNKNOWN = ("이 프로모션의 편집 창은 ERP 가 할인 단 줄이 어느 저장된 단에서 왔는지 모르는 상태라(앞선 저장이 거절된 뒤 다시 그려진 "
                  "창), 저장하면 화면에 안 보이는 설정이 다른 단에 붙거나 빠질 수 있어 도우미가 저장하지 않습니다 — ERP 에서 그 프로모션의 "
                  "편집 창을 닫았다가 다시 열어 주시면 다시 해 보겠습니다")
TRIGGERS = {"ALWAYS": "상시", "LOS": "연박", "LEAD_TIME": "얼리버드", "ROOM_COUNT": "객실 수"}
BASES = {"PCT": "할인율(%)", "FLAT": "할인 금액", "FREE_NIGHT": "무료 숙박(박)"}
UNITS = {"0": "박당", "1": "체류당 1회"}
OFF_WORDS = {"cancellation": "취소 조건"}   # 화면 밖 설정의 이름 → 담당자에게 말하는 말(모르는 이름은 그대로)
KEEPS_MARK = "mark.화면에 없는 설정을 지키는 표식"
NONE = "없음"


class ModelError(Refused):
    """요청 · 파일이 모양에 맞지 않는다 — 문장은 담당자에게 그대로 보여 줄 수 있다."""


def hotel_label(name: str, hotel_id: str) -> str:
    return f"{name} (번호 {hotel_id})" if hotel_id else name


def decode_hotel(data) -> tuple[str, str]:
    if not isinstance(data, Mapping) or not str(data.get("id") or "").strip():
        raise ModelError("호텔은 stayPromotion.look() 의 hotel({id, name}) 그대로 적습니다")
    return str(data.get("name") or ""), str(data["id"]).strip()


def encode_hotel(name: str, hotel_id: str) -> dict:
    return {"id": hotel_id, "name": name}


def threshold_key(text: str) -> str:
    """단을 가리키는 기준값 글자 — 정수면 정수 글자(「021」 · 「21.0」 → 「21」), 아니면 앞뒤 빈칸만 뺀 글자."""
    text = str(text).strip()
    try:
        number = Decimal(text)
    except InvalidOperation:
        return text
    return str(int(number)) if number.is_finite() and number == number.to_integral_value() else text


def off_words(names: Iterable[str]) -> str:
    return " · ".join(OFF_WORDS.get(name, name) for name in names)


def tier_key(promotion: str, tier: str | None = None) -> str:
    return item_key({"promotion": promotion} if tier is None else {"promotion": promotion, "tier": tier})


def part_of_key(text: str) -> tuple[str, str | None]:
    """장부의 항목 키 → (프로모션 번호, 단의 기준값 — 프로모션 자체면 None)."""
    fields = key_fields(text)
    return str(fields["promotion"]), (None if "tier" not in fields else str(fields["tier"]))


def promotion_of_key(text: str) -> str:
    """저장 한 번이 다시 쓰는 단위 — 프로모션 번호(단 항목도 그 프로모션에 든다)."""
    return part_of_key(text)[0]


# ───────────── 목록 줄 ─────────────

@dataclass(frozen=True)
class Listed:
    """목록의 프로모션 줄 하나 — 화면이 보인 그대로. `benefit` 은 혜택 칸의 줄들(단마다 「기준 → 값」), `combo` 는 중복 칸, `limits` 는
    한정 칸(시즌 · 적용 범위 · 요금제 · 숙박일 · 예약일), `warnings` 는 프로모션 칸의 경고."""
    offer: str
    offer_name: str
    id: str
    title: str
    code: str
    trigger: str
    benefit: tuple[str, ...]
    combo: tuple[str, ...]
    limits: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.offer_name} · {self.title}" if self.offer_name else self.title

    @property
    def currency(self) -> str:
        """정액 할인의 통화 — 목록의 혜택 줄이 「20 USD」처럼 호텔 통화를 붙인다. 없으면 빈 글자."""
        found = {match.group(1) for line in self.benefit for match in [re.search(r"\b([A-Z]{3})\s*$", line)] if match}
        return found.pop() if len(found) == 1 else ""


def decode_listed(offer: Mapping, row: Mapping) -> Listed:
    lines = (lambda name: tuple(str(line) for line in row.get(name) or ()))
    return Listed(str(offer["id"]), str(offer.get("name") or ""), str(row["id"]), str(row["title"]), str(row.get("code") or ""),
                  str(row.get("trigger") or ""), lines("benefit"), lines("combo"), lines("limits"), lines("warnings"))


def encode_listed(item: Listed) -> dict:
    return dict(offer=item.offer, offer_name=item.offer_name, id=item.id, title=item.title, code=item.code, trigger=item.trigger,
                benefit=list(item.benefit), combo=list(item.combo), limits=list(item.limits), warnings=list(item.warnings))


def listed_from(data: Mapping) -> Listed:
    return decode_listed(dict(id=data["offer"], name=data["offer_name"]), data)


@dataclass(frozen=True)
class Listing:
    """look 의 답 — 호텔의 카드마다(오퍼 · 전 오퍼 공통) 프로모션 줄 전부(목록이 보인 그대로)."""
    hotel: str
    hotel_id: str
    read_at: str
    offers: tuple[tuple[str, str], ...]          # (번호, 이름) — 전 오퍼 공통은 (0, 「전 오퍼 공통」)
    promotions: tuple[Listed, ...]


def listing_of(answer: Mapping, read_at: str) -> Listing:
    """stayPromotion.look() 의 답(조각을 붙인 것) → Listing."""
    name, hotel_id = decode_hotel(answer.get("hotel"))
    offers, promotions = [], []
    for offer in answer.get("offers") or ():
        offers.append((str(offer["id"]), str(offer.get("name") or "")))
        promotions += [decode_listed(offer, row) for row in offer.get("promotions") or ()]
    ids = [item.id for item in promotions]
    if len(set(ids)) != len(ids):
        raise BrowserError("목록에 같은 번호의 프로모션이 둘 이상 있습니다")
    if sum(offer_id == COMMON for offer_id, _ in offers) > 1:
        raise BrowserError("목록에 「전 오퍼 공통」 카드가 둘 이상 있습니다")
    return Listing(name, hotel_id, read_at, tuple(offers), tuple(promotions))


def encode_listing(listing: Listing) -> dict:
    return dict(kind="promotion_listing", hotel=encode_hotel(listing.hotel, listing.hotel_id), read_at=listing.read_at,
                offers=[dict(id=offer_id, name=name) for offer_id, name in listing.offers],
                promotions=[encode_listed(item) for item in listing.promotions])


def decode_listing(data: Mapping) -> Listing:
    if data.get("kind") != "promotion_listing":
        raise ModelError("look 명령이 낸 파일(kind promotion_listing)이 아닙니다")
    name, hotel_id = decode_hotel(data["hotel"])
    return Listing(name, hotel_id, str(data["read_at"]), tuple((str(o["id"]), str(o["name"])) for o in data["offers"]),
                   tuple(listed_from(item) for item in data["promotions"]))


# ───────────── 편집 창 ─────────────

@dataclass(frozen=True)
class Tier:
    """할인 단 하나 — 창의 차례(0 부터), 기준값 · 값의 글자, 그 단이 불러온 저장 단(`tiers_origin`, 표식 없는 ERP 에는 없다), 화면 밖
    설정의 이름들(줄의 표식)."""
    index: int
    threshold: str
    value: str
    origin: str | None
    off: tuple[str, ...]

    @property
    def at(self) -> str:
        return threshold_key(self.threshold)


@dataclass(frozen=True)
class Promotion:
    """읽은 프로모션 하나 — 목록 줄과 편집 창이 보낼 칸 전부. `labels` 는 고르는 칸이 보인 글자, `keeps` 는 뿌리의 표식(화면 밖 설정을
    지키는 ERP 인지), `marks` 는 단 줄마다(창의 차례) 화면 밖 설정의 이름들."""
    listed: Listed
    form: Form
    labels: Mapping[str, str] = field(default_factory=dict)
    keeps: bool = False
    marks: tuple[tuple[str, ...], ...] = ()
    title: str = ""

    @property
    def id(self) -> str:
        return self.listed.id

    @property
    def offer(self) -> str:
        return self.listed.offer

    @property
    def name(self) -> str:
        return self.listed.title

    @property
    def label(self) -> str:
        return self.listed.label

    @property
    def currency(self) -> str:
        return self.listed.currency

    def one(self, name: str) -> str:
        return form_value(self.form, name, f"프로모션 {self.id}번")

    @property
    def trigger(self) -> str:
        return self.one("trigger_type")

    @property
    def basis(self) -> str:
        return self.one("basis")

    @property
    def field_label(self) -> str:
        return BASES.get(self.basis, "값")

    @property
    def origin_known(self) -> bool:
        """단 줄마다 ERP 가 그 줄이 어느 저장된 단에서 왔는지 안다 — 숨은 칸 tiers_origin 에 `?` 가 하나도 없다."""
        return all(value.strip() != UNSURE_ORIGIN for value in form_values(self.form, "tiers_origin"))

    def tiers(self) -> tuple[Tier, ...]:
        thresholds, values = form_values(self.form, "tiers_threshold"), form_values(self.form, VALUE)
        origins = form_values(self.form, "tiers_origin")
        if len(thresholds) != len(values) or len(self.marks) != len(values) or (origins and len(origins) != len(values)):
            raise BrowserError(f"프로모션 {self.id}번 편집 창의 할인 단 칸 수가 서로 다릅니다(기준값 {len(thresholds)} · 값 {len(values)} · "
                               f"표식 {len(self.marks)}) — 창이 생각한 모양이 아닙니다")
        tiers = tuple(Tier(index, threshold, value, origins[index] if origins else None, tuple(self.marks[index]))
                      for index, (threshold, value) in enumerate(zip(thresholds, values)))
        keys = [tier.at for tier in tiers]
        if len(set(keys)) != len(keys):
            raise BrowserError(f"프로모션 {self.id}번에 같은 기준값의 단이 둘 이상 있습니다")
        return tiers

    def tier(self, at: str) -> Tier:
        found = next((tier for tier in self.tiers() if tier.at == threshold_key(at)), None)
        if found is None:
            shown = " · ".join(tier.at for tier in self.tiers()) or "없음"
            raise ModelError(f"프로모션 {self.id}번에 기준값 {at} 단이 없습니다(있는 단: {shown}) — look 의 혜택 줄의 기준값을 씁니다")
        return found

    def value(self, tier: Tier) -> Decimal | None:
        """그 단의 값. 비었거나 숫자가 아니면 None(그런 단은 채우거나 셈하지 않는다)."""
        text = tier.value.strip()
        try:
            return None if not text else money(text)
        except ValueError:
            return None

    def threshold_words(self, tier: Tier) -> str:
        """단의 조건을 화면의 뜻으로 — 「체크인 21일 전」 · 「3박 이상」 · 「객실 2개 이상」 · 「상시」."""
        return {"LEAD_TIME": f"체크인 {tier.at}일 전", "LOS": f"{tier.at}박 이상", "ROOM_COUNT": f"객실 {tier.at}개 이상",
                "ALWAYS": "상시"}.get(self.trigger, f"기준값 {tier.at}")

    def tier_label(self, tier: Tier) -> str:
        return f"{self.label} · {self.threshold_words(tier)} 단"

    def others(self) -> dict[str, str]:
        """딸린 칸 — 단의 값 말고 편집 창이 보내는 칸 전부(같은 이름이 여럿이면 줄바꿈으로 잇는다), 표식(화면 밖 설정을 지키는지 ·
        단마다 그 설정의 이름), 목록 줄의 글자."""
        found: dict[str, list[str]] = {}
        for name, value in self.form:
            if name != VALUE:
                found.setdefault(name, []).append(value)
        others = {f"form.{name}": "\n".join(values) for name, values in found.items()}
        others[KEEPS_MARK] = "있음" if self.keeps else NONE
        for tier in self.tiers():
            others[f"mark.기준값 {tier.at} 단의 화면에 없는 설정"] = " ".join(tier.off) or NONE
        others.update({"name": self.name, "offer": self.offer, "list.code": self.listed.code, "list.trigger": self.listed.trigger,
                       "list.benefit": "\n".join(self.listed.benefit), "list.combo": "\n".join(self.listed.combo),
                       "list.limits": "\n".join(self.listed.limits), "list.warnings": "\n".join(self.listed.warnings)})
        return others

    def items(self) -> dict[str, ItemState]:
        """장부 항목 → 상태. 프로모션 자체에 딸린 칸이 모두 붙고, 단 항목은 값만 든다."""
        out = {tier_key(self.id): ItemState(self.label, PRESENT, {}, self.others())}
        for tier in self.tiers():
            out[tier_key(self.id, tier.at)] = ItemState(self.tier_label(tier), PRESENT, {"value": self.value(tier)}, {})
        return out


def encode_promotion(promotion: Promotion) -> dict:
    return dict(listed=encode_listed(promotion.listed), form=[list(pair) for pair in promotion.form], labels=dict(promotion.labels),
                keeps=promotion.keeps, marks=[list(names) for names in promotion.marks], title=promotion.title)


def decode_promotion(data: Mapping) -> Promotion:
    return Promotion(listed_from(data["listed"]), tuple((str(name), str(value)) for name, value in data["form"]),
                     {str(k): str(v) for k, v in (data.get("labels") or {}).items()}, bool(data.get("keeps")),
                     tuple(tuple(str(name) for name in names) for names in data.get("marks") or ()), str(data.get("title") or ""))


def promotion_of(answer: Mapping) -> Promotion | None:
    """readPromotion 의 답(조각을 붙인 것) 하나 → Promotion. 목록에 그 프로모션이 없으면(missing) None. 답이 물은 호텔 · 카드 · 프로모션의
    것인지, 편집 창이 그 프로모션(이름)의 것인지 본다 — 아니면 BrowserError(페이지가 먼저 거절하지만 여기서 다시 본다)."""
    asked = answer.get("asked") or {}
    if not answer.get("ok"):
        raise BrowserError(f"프로모션 {asked.get('promotion')}번을 읽지 못했습니다: {answer.get('error')}")
    if answer.get("missing"):
        return None
    hotel, offer, row, window = answer.get("hotel") or {}, answer["offer"], answer["promotion"], answer["window"]
    if str(hotel.get("id")) != str((asked.get("hotel") or {}).get("id")):
        raise BrowserError(f"readPromotion 의 답이 물은 호텔({(asked.get('hotel') or {}).get('id')})이 아닌 {hotel.get('id')} 에서 읽은 것입니다")
    if (str(offer["id"]), str(row["id"])) != (str(asked.get("offer")), str(asked.get("promotion"))):
        raise BrowserError(f"readPromotion 의 답이 물은 프로모션({asked.get('offer')} · {asked.get('promotion')})이 아닙니다")
    if window.get("errors"):
        raise BrowserError(f"프로모션 {row['id']}번의 편집 창이 오류를 보입니다: {' / '.join(window['errors'])}")
    promotion = Promotion(decode_listed(offer, row), tuple((str(name), str(value)) for name, value in window["form"]),
                          {str(k): str(v) for k, v in (window.get("labels") or {}).items()}, window.get("keeps") is True,
                          tuple(tuple(str(name) for name in names) for names in window.get("marks") or ()),
                          str(window.get("title") or ""))
    if shown_name(promotion.one("title")) != shown_name(promotion.name):
        raise BrowserError(f"프로모션 {row['id']}번의 편집 창 이름({promotion.one('title')})이 목록의 이름({promotion.name})과 다릅니다")
    promotion.items()               # 칸이 생각한 모양인지 지금 본다(아니면 BrowserError)
    return promotion


# ───────────── 읽은 값 ─────────────

PromotionRef = tuple[str, str]          # (카드의 오퍼 번호 — 전 오퍼 공통은 0, 프로모션 번호)


@dataclass(frozen=True)
class Snapshot:
    """읽기 한 번 — 물은 프로모션(`asked`, 읽은 범위)과 그 가운데 목록에 있던 프로모션(`promotions`, 번호 → Promotion)."""
    hotel: str
    hotel_id: str
    read_at: str
    asked: tuple[PromotionRef, ...]
    promotions: Mapping[str, Promotion]

    @property
    def currency(self) -> str:
        found = {promotion.currency for promotion in self.promotions.values() if promotion.currency}
        if len(found) > 1:
            raise BrowserError(f"정액 할인의 통화가 하나가 아닙니다: {', '.join(sorted(found))}")
        return found.pop() if found else ""

    def missing(self) -> tuple[PromotionRef, ...]:
        return tuple(ref for ref in self.asked if ref[1] not in self.promotions)

    def covers(self, promotion: str) -> bool:
        return any(ref[1] == promotion for ref in self.asked)


def encode_snapshot(snapshot: Snapshot) -> dict:
    return dict(kind="promotion_snapshot", hotel=encode_hotel(snapshot.hotel, snapshot.hotel_id), read_at=snapshot.read_at,
                currency=snapshot.currency, asked=[dict(offer=offer, promotion=promotion) for offer, promotion in snapshot.asked],
                promotions=[encode_promotion(promotion) for promotion in snapshot.promotions.values()])


def decode_snapshot(data: Mapping) -> Snapshot:
    if data.get("kind") != "promotion_snapshot":
        raise ModelError("read 명령이 낸 지금 값(kind promotion_snapshot)이 아닙니다")
    name, hotel_id = decode_hotel(data["hotel"])
    promotions = [decode_promotion(item) for item in data["promotions"]]
    return Snapshot(name, hotel_id, str(data["read_at"]), tuple((str(r["offer"]), str(r["promotion"])) for r in data["asked"]),
                    {promotion.id: promotion for promotion in promotions})


def snapshot_items(snapshot: Snapshot) -> Reading:
    """읽은 값 → 공통 모양(항목 → 이름 · 상태 · 값 · 딸린 칸). 물었는데 없는 프로모션은 그 프로모션 항목이 없는 것이다."""
    items = {}
    for _offer, promotion_id in snapshot.asked:
        promotion = snapshot.promotions.get(promotion_id)
        if promotion is None:
            items[(ITEM_KIND, tier_key(promotion_id))] = absent(f"프로모션 {promotion_id}번")
            continue
        items.update({(ITEM_KIND, key): state for key, state in promotion.items().items()})
    return items


def name_notes_of(snapshot: Snapshot, written: Iterable[tuple[str, Decimal | None]]) -> list[NameNote]:
    """바꾸는(바꾼) 단마다(항목 키, 바꾸기 전 값) 그 프로모션의 이름 · 코드에 바꾸기 전 값이 적혔는지 — 도우미는 이름을 바꾸지 않으므로
    알린다(change_core.names). 할인율 단은 `%` 가 붙은 숫자만 본다(「얼리버드 10%」). 무료 숙박은 「1박」처럼 수가 붙어 보지 않는다."""
    found = []
    for key, before in written:
        promotion = snapshot.promotions.get(promotion_of_key(key))
        if promotion is None:
            continue
        what, percent = f"프로모션 「{promotion.label}」", promotion.basis == "PCT"
        found += [(what, "이름", promotion.name, before, percent), (what, "코드", promotion.listed.code, before, percent)]
    return name_notes(found)


# ───────────── 바꾸기 요청 ─────────────

HOWS = ("amount", "percent", "value")


@dataclass(frozen=True)
class Target:
    """바꿀 단 하나 — 카드의 오퍼 번호(전 오퍼 공통은 0), 프로모션 번호, 단의 기준값."""
    offer: str
    promotion: str
    tier: str

    @property
    def key(self) -> str:
        return tier_key(self.promotion, threshold_key(self.tier))


@dataclass(frozen=True)
class ChangeRequest:
    """바꿀 단들 + 방법 하나(더하기 · 퍼센트 · 새 값). 단을 비우는 방법은 없다."""
    hotel: str
    hotel_id: str
    targets: tuple[Target, ...]
    how: str
    figure: Decimal
    sentence: str

    def promotions(self) -> tuple[PromotionRef, ...]:
        return tuple(dict.fromkeys((target.offer, target.promotion) for target in self.targets))

    def describe(self) -> str:
        if self.how == "value":
            return f"할인 값 {josa(money_text(self.figure), '으로')}"
        sign = "+" if self.figure >= 0 else ""
        return f"할인 값 {sign}{money_text(self.figure)}{'%' if self.how == 'percent' else ''}"


def decode_target(item: Mapping) -> Target:
    offer, promotion = str(item.get("offer") or "").strip(), str(item.get("promotion") or "").strip()
    if not offer.isdigit() or not promotion.isdigit():
        raise ModelError("단마다 offer(카드의 오퍼 번호, 전 오퍼 공통은 0)와 promotion(프로모션 번호)을 look 의 번호 그대로 적습니다")
    tier = str(item.get("tier") if item.get("tier") is not None else "").strip()
    if not tier:
        raise ModelError("단마다 tier(그 단의 기준값 — look 의 혜택 줄의 숫자, 상시는 0)를 적습니다")
    return Target(offer, promotion, threshold_key(tier))


def encode_target(target: Target) -> dict:
    return dict(offer=target.offer, promotion=target.promotion, tier=target.tier)


def decode_request(data: Mapping) -> ChangeRequest:
    if data.get("kind") != "promotion_change":
        raise ModelError("바꾸기 요청은 kind promotion_change 입니다")
    name, hotel_id = decode_hotel(data.get("hotel"))
    if data.get("clear") is not None:
        raise ModelError("할인 단의 값은 비우지 않습니다(ERP 가 그 저장을 거절합니다) — 할인을 없애려면 value 0 으로 적습니다")
    given = [how for how in HOWS if data.get(how) is not None and data.get(how) is not False]   # 0 은 값이다(0 == False 라 `in` 으로 가리지 않는다)
    if len(given) != 1:
        raise ModelError("amount · percent · value 가운데 하나만 적습니다")
    how = given[0]
    figure = money(data[how])
    targets = tuple(decode_target(item) for item in data.get("tiers") or ())
    if not targets:
        raise ModelError("tiers(바꿀 단 목록)가 비었습니다")
    keys = [target.key for target in targets]
    if len(set(keys)) != len(keys):
        raise ModelError("같은 단을 두 번 적었습니다")
    offers: dict[str, str] = {}
    for target in targets:
        if offers.setdefault(target.promotion, target.offer) != target.offer:
            raise ModelError(f"프로모션 {target.promotion}번의 오퍼 번호가 단마다 다릅니다")
    sentence = str(data.get("sentence") or "").strip()
    if not sentence:
        raise ModelError("sentence(담당자가 한 말)가 비었습니다")
    return ChangeRequest(name, hotel_id, targets, how, figure, sentence)


def encode_request(request: ChangeRequest) -> dict:
    return dict(kind="promotion_change", hotel=encode_hotel(request.hotel, request.hotel_id),
                tiers=[encode_target(target) for target in request.targets], sentence=request.sentence,
                **{request.how: money_text(request.figure)})


def known_promotions(request: ChangeRequest, listing: Listing | None) -> tuple[PromotionRef, ...]:
    """요청이 짚은 프로모션 — 목록(look)이 있으면 그 카드의 그 프로모션이 목록에 있는지 본다."""
    refs = request.promotions()
    if listing is None:
        return refs
    if listing.hotel_id != request.hotel_id:
        raise ModelError(f"목록은 {hotel_label(listing.hotel, listing.hotel_id)} 이고 요청은 "
                         f"{hotel_label(request.hotel, request.hotel_id)} 입니다")
    known = {(item.offer, item.id) for item in listing.promotions}
    unknown = [f"{offer} · {promotion}" for offer, promotion in refs if (offer, promotion) not in known]
    if unknown:
        raise ModelError(f"목록에 없는 프로모션입니다(오퍼 · 프로모션): {', '.join(unknown)} — look 의 번호를 씁니다(전 오퍼 공통은 오퍼 0)")
    return refs
