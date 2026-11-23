"""season_expand.py — ERP 시즌 [가격 입력] 창("시즌 [가격] 채우기")이 칸마다 무엇을 넣는지 셈하는 순수 함수. 브라우저 · 파일 ·
장부를 모른다. 돈은 전부 `Decimal` 이다.

ERP 의 규칙을 우리말로 옮겨 다시 쓴 것이다(코드를 베끼지 않았다). 근거는 basecamp `stay/services/season.py`(창의 입력 문법 ·
금액표 · 아동 조합 · 박수 층), `stay/services/occupancy_key.py`(인원 조합 키의 꼴), `stay/services/occupancy_combo.py`(객실의
허용 인원 조합), `stay/forms.py` `SeasonPriceFillForm`(창 칸의 문법)이고, 기대값은 `tests/test_season_expand.py` 가 손으로 셈한다.

    parse_inputs(save 의 글자들, child_rates)  → Inputs        창이 거절할 입력이면 SeasonRefused(ERP 의 그 문장)
    los_matrix(inputs)                        → {박수: (기준 요금제 표, 조정 요금제 표)}   표는 인원 조합 키 → (판매가, 정가, 공급 원가)
    normalize_key(key) · parse_key(key)       인원 조합 키의 정규형(`2` → `A2`, `A2C1_CHD_C1_TEEN`)
    parse_combos(text) · key_allowed(combos, key)   객실의 허용 인원 조합과 그 안의 좌표인지

규칙(요약):
- 금액 칸은 비우거나 0 이상 · 소수 둘째 자리까지. 판매가는 꼭 있다. 정가를 적으면 판매가 이상이어야 한다.
- 조정(`-8` · `+5%`)은 부호가 꼭 있다. 퍼센트는 -100% 아래로 못 간다. 조정한 금액은 0.01 로 반올림(반 올림)하고, 조정하지 않은
  금액은 친 글자 그대로다.
- 인원 조합은 `[,\\s]+` 로 나눈 키들이다. 맨 숫자는 성인 수(`2` → `A2`), 같은 키는 한 번만, 32자까지. 비우면 인원 무관 한 좌표("").
- 인원 조합별 조정(`A3:+30`)의 키는 같은 정규화를 지나고, 인원 조합 칸에 없는 키 · 두 번 적은 키는 거절이다.
- 요금제 조정이 먼저, 그 위에 인원 조합 조정, 아동 조합은 맨 나중이다(정률이 끼면 차례가 값을 바꾼다).
- 아동 조합: 성인 키(A<n>)마다 쓸 수 있는 아동 구간(금액이나 비율이 있는 구간)의 `A<n>C1_<코드>` 가 붙는다(이미 있으면 그대로).
  금액 구간은 성인 칸 + 금액, 비율 구간은 성인 칸 + 성인 1인 추가분(A<n+1> − A<n>, 없으면 A<n> / n) × 비율. 세 금액 모두에
  더하고 0.01 로 반올림한다. 직접 친 아동 키는 조정을 적었으면 그 조정 값이, 아니면 같은 셈이 이긴다.
- 박수 층(`3:160`)은 그 박수부터의 1박 판매가다 — 부호 없음 · 2~30박 · 6층까지 · 겹침 없음. 정가 · 공급 원가는 층이 갈리지 않는다
  (모든 층이 1박의 정가 · 공급 원가). 정가를 적었으면 층 판매가도 정가 이하여야 한다.
- 어느 칸이든 음수가 되면 창이 통째로 거절한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Mapping

from change_core.items import Refused

CENT = Decimal("0.01")
MONEY = re.compile(r"^(0|[1-9]\d{0,9})(\.\d{1,2})?$")      # 창의 금액 칸(DecimalField 12자리 · 소수 둘) — 쉼표 없이
ADJUST = re.compile(r"^([+-])\s*(\d+(?:\.\d+)?)\s*(%?)$")  # 요금제 조정 · 인원 조합별 조정의 값
ADJUST_ENTRY = re.compile(r"^\s*([^:]+?)\s*:\s*(.+?)\s*$")
LOS_ENTRY = re.compile(r"^\s*(\d+)\s*:\s*(\d+(?:\.\d+)?)\s*$")
KEY_SPLIT = re.compile(r"[,\s]+")
BAND = re.compile(r"^[A-Z0-9]{2,8}$")
CHILD_HEAD = re.compile(r"^C(\d+)$")
KEY_MAX = 32
MAX_LOS_TIERS, MAX_LOS_NIGHTS = 6, 30
FIELD_LIMITS = {"plan_adjust": 20, "occupancy_keys": 120, "occupancy_adjust": 200, "los_prices": 120}   # 창 칸의 max_length
AMOUNT_LABELS = ("판매 단가", "정가", "공급 원가")
NO_COMBOS = "조합 제한 없음 — 인원 상한 적용"   # 객실 타입 표의 「허용 인원 조합」 칸이 비었을 때의 글자(_room_types_panel.html)

Triple = tuple  # (판매가, 정가 또는 None, 공급 원가 또는 None)


class SeasonRefused(Refused):
    """ERP 창이 거절할 입력 — 문장은 ERP 가 보일 말과 같은 뜻이다(담당자에게 그대로 보인다). 저장 하나가 통째로 막힌다."""


# ─── 인원 조합 키 ───


@dataclass(frozen=True)
class Key:
    """인원 조합 키를 읽은 것. `adults` 가 None 이면 인원 무관("") 이거나 맨 숫자(`total` 만 안다). `children` 은 (아동 수, 구간 코드
    또는 None) — 코드 없는 조각은 예전 꼴 `A2C1` 하나뿐이다."""
    adults: int | None
    children: tuple[tuple[int, str | None], ...]
    total: int | None


def parse_key(text: str) -> Key:
    """키 글자 → Key. 대문자로 굳혀 읽는다. 읽지 못하면 ValueError(까닭)."""
    key = (text or "").strip().upper()
    if not key:
        return Key(None, (), None)
    if key.isdigit():
        return Key(None, (), int(key))
    head = re.match(r"^A(\d+)", key)
    if head is None:
        raise ValueError(f"인원 조합 키를 읽지 못했습니다 — 'A2' · 'A2C1_CHD' 형식이거나 인원수 숫자여야 합니다: {text!r}")
    adults, rest, parts = int(head.group(1)), key[head.end():], []
    if rest:
        if rest.startswith("_"):
            raise ValueError(f"첫 아동 조각은 성인 자리에 붙여 씁니다('A2C1_CHD', 'A2_C1_CHD' 아님) — 읽지 못한 값: {text!r}")
        for token in rest.split("_"):
            if not token:
                raise ValueError(f"인원 조합 키에 빈 조각이 있습니다 — 읽지 못한 값: {text!r}")
            child = CHILD_HEAD.match(token)
            if child is not None:
                if int(child.group(1)) <= 0:
                    raise ValueError(f"아동 수가 0인 조각은 좌표가 될 수 없습니다 — 읽지 못한 값: {text!r}")
                parts.append([int(child.group(1)), None])
                continue
            if not parts:
                raise ValueError(f"구간 코드 '{token}' 앞에 아동 조각(C+숫자)이 없습니다 — 읽지 못한 값: {text!r}")
            if parts[-1][1] is not None:
                raise ValueError(f"아동 조각 하나에 구간 코드가 둘입니다 — 읽지 못한 값: {text!r}")
            if not BAND.match(token):
                raise ValueError(f"구간 코드는 영대문자·숫자 2~8자여야 합니다 — 읽지 못한 값: {token!r} (키 {text!r})")
            parts[-1][1] = token
        if any(code is None for _count, code in parts) and len(parts) != 1:
            raise ValueError(f"구간 코드 없는 아동 조각은 'A2C1' 한 모양뿐입니다 — 조각이 둘 이상이면 코드를 모두 적어야 합니다: {text!r}")
    children = tuple((count, code) for count, code in parts)
    return Key(adults, children, adults + sum(count for count, _code in children))


def build_key(adults: int, children: Iterable[tuple[int, str]] = ()) -> str:
    """(성인 수, [(아동 수, 코드)…]) → 정규형 키 — 같은 코드는 합치고 코드는 알파벳순, 첫 조각만 성인 자리에 붙는다. 32자를 넘으면 ValueError."""
    merged: dict[str, int] = {}
    for count, code in children:
        if count > 0:
            merged[code] = merged.get(code, 0) + count
    key = f"A{adults}" + "_".join(f"C{merged[code]}_{code}" for code in sorted(merged))
    if len(key) > KEY_MAX:
        raise ValueError(f"인원 조합 키가 너무 깁니다({KEY_MAX}자까지) — {key} ({len(key)}자). 구간 코드를 짧게 하거나 조합을 줄이세요")
    return key


def normalize_key(text: str) -> str:
    """저장 전 정규형 — 맨 숫자는 전원 성인(`2` → `A2`), 코드 없는 `A2C1` 은 그대로, 나머지는 build_key. 못 읽으면 ValueError."""
    key = parse_key(text)
    if key.adults is None:
        out = "" if key.total is None else f"A{key.total}"
        if len(out) > KEY_MAX:
            raise ValueError(f"인원 조합 키가 너무 깁니다({KEY_MAX}자까지) — {out} ({len(out)}자)")
        return out
    if any(code is None for _count, code in key.children):
        return (text or "").strip().upper()
    return build_key(key.adults, key.children)


def key_children(key: str) -> int | None:
    """키의 아동 수(아동 조각의 합) — 읽지 못하면 None."""
    try:
        return sum(count for count, _code in parse_key(key).children)
    except ValueError:
        return None


# ─── 입력 문법 ───


@dataclass(frozen=True)
class Adjust:
    """조정 하나 — 금액(`+30`)이나 퍼센트(`-5%`). `raw` 는 친 글자."""
    value: Decimal
    percent: bool
    raw: str

    def apply(self, amount: Decimal | None) -> Decimal | None:
        if amount is None:
            return None
        moved = amount * (Decimal(100) + self.value) / Decimal(100) if self.percent else amount + self.value
        return moved.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_money(text: str, label: str, required: bool = False) -> Decimal | None:
    value = (text or "").strip()
    if not value:
        if required:
            raise SeasonRefused(f"{label}를 입력해주세요")
        return None
    if not MONEY.match(value):
        raise SeasonRefused(f"{label}는 0 이상 숫자로, 쉼표 없이 소수 둘째 자리까지 적습니다(예: 180 · 23.18): {text!r}")
    return Decimal(value)


def parse_adjust(text: str) -> Adjust | None:
    value = (text or "").strip()
    if not value:
        return None
    found = ADJUST.match(value)
    if found is None:
        raise SeasonRefused("조정 값은 부호를 붙여 주세요 — 예: -8 (8 싸게) · -5% (5% 싸게) · +12 (12 비싸게)")
    sign, digits, percent = found.groups()
    number = Decimal(digits) * (Decimal(-1) if sign == "-" else Decimal(1))
    if percent and number < Decimal(-100):
        raise SeasonRefused("정률 조정은 -100% 보다 작을 수 없습니다 — 가격이 음수가 됩니다")
    return Adjust(number, bool(percent), value)


def adjusted(adjust: Adjust | None, triple: Triple) -> Triple:
    """조정을 세 금액에 함께 건다. 조정이 없으면 그대로(반올림하지 않는다). 음수가 되면 거절."""
    if adjust is None:
        return triple
    out = tuple(adjust.apply(amount) for amount in triple)
    for label, amount in zip(AMOUNT_LABELS, out):
        if amount is not None and amount < 0:
            raise SeasonRefused(f"조정 {adjust.raw} 을 걸면 {label}가 음수({amount})가 됩니다 — 조정 값을 확인하세요")
    return out


def _key_error(error: ValueError) -> SeasonRefused:
    return SeasonRefused("인원 조합을 읽지 못했습니다 — 성인은 A2, 아동을 더하면 A2C1_CHD 처럼 씁니다(인원수 숫자 2, 3, 4 … 로 적으면 "
                         f"A2, A3, A4 로 저장됩니다): {error}")


def parse_keys(text: str) -> list[str] | None:
    """인원 조합 칸 → 정규화한 키들(친 차례, 같은 키는 한 번). 비우면 None — 인원 무관 한 좌표("")다."""
    keys: list[str] = []
    for item in KEY_SPLIT.split(str(text or "")):
        key = item.strip().upper()
        if not key:
            continue
        if len(key) > KEY_MAX:
            raise SeasonRefused(f"인원 조합 키가 너무 깁니다({KEY_MAX}자까지) — {key}")
        try:
            key = normalize_key(key)
        except ValueError as error:
            raise _key_error(error) from None
        if key not in keys:
            keys.append(key)
    return keys or None


def parse_occupancy_adjust(text: str) -> dict[str, Adjust]:
    """`A3:+30,A4:+50` → 키 → 조정. 키는 인원 조합 칸과 같은 정규화를 지난다. 두 번 적은 키 · 빈 값은 거절."""
    out: dict[str, Adjust] = {}
    for chunk in str(text or "").strip().split(","):
        entry = chunk.strip()
        if not entry:
            continue
        found = ADJUST_ENTRY.match(entry)
        if found is None:
            raise SeasonRefused(f"인원 조합별 조정은 `키:조정` 으로 씁니다 — 예: 3:+14,4:+26 (읽지 못한 값: {entry})")
        try:
            key = normalize_key(found.group(1).strip().upper())
        except ValueError as error:
            raise SeasonRefused("인원 조합별 조정의 키를 읽지 못했습니다 — 성인은 A2, 아동을 더하면 A2C1_CHD 처럼 씁니다(인원수 숫자 "
                                f"3, 4 … 로 적으면 A3, A4 로 읽습니다): {error}") from None
        try:
            adjust = parse_adjust(found.group(2).strip())
        except SeasonRefused as error:
            raise SeasonRefused(f"{key or '인원 무관 단일가'} 의 조정 — {error}") from None
        if adjust is None:
            raise SeasonRefused(f"{key} 의 조정 값이 비어 있습니다 — 값을 적거나 그 항목을 빼주세요")
        if key in out:
            raise SeasonRefused(f"{key} 의 조정이 두 번 적혀 있습니다 — 어느 쪽을 쓸지 정해지지 않습니다")
        out[key] = adjust
    return out


def parse_los(text: str) -> dict[int, Decimal]:
    """`3:160,5:150` → 박수 → 그 박수부터의 1박 판매가(박수 오름차순). 부호 · 1박 · 30박 넘음 · 겹침 · 6층 넘음은 거절."""
    tiers: dict[int, Decimal] = {}
    for chunk in str(text or "").strip().split(","):
        entry = chunk.strip()
        if not entry:
            continue
        found = LOS_ENTRY.match(entry)
        if found is None:
            raise SeasonRefused("박수별 단가는 `박수:1박 단가` 로 씁니다 — 예: 3:100,5:90 (차액이 아니라 단가라 부호를 붙이지 않습니다 · "
                                f"읽지 못한 값: {entry})")
        nights = int(found.group(1))
        if nights <= 1:
            raise SeasonRefused(f"박수는 2 이상이어야 합니다 — 1박 단가는 위 [판매 단가] 칸입니다 (읽지 못한 값: {entry})")
        if nights > MAX_LOS_NIGHTS:
            raise SeasonRefused(f"박수가 너무 큽니다({MAX_LOS_NIGHTS}박까지) — {nights}")
        if nights in tiers:
            raise SeasonRefused(f"{nights}박 단가가 두 번 적혀 있습니다 — 어느 쪽을 쓸지 정해지지 않습니다")
        tiers[nights] = Decimal(found.group(2))
    if len(tiers) > MAX_LOS_TIERS:
        raise SeasonRefused(f"박수 층이 너무 많습니다({MAX_LOS_TIERS}개까지) — 층 하나가 셀 수를 통째로 곱합니다")
    return dict(sorted(tiers.items()))


# ─── 아동 구간 ───


@dataclass(frozen=True)
class ChildRate:
    """쓸 수 있는 아동 구간 하나 — 금액(`amount`)이나 성인 1인 추가분의 비율(`percent`) 가운데 하나. 둘 다 없으면 쓰지 않는다."""
    code: str
    amount: Decimal | None = None
    percent: Decimal | None = None

    @property
    def usable(self) -> bool:
        return self.amount is not None or self.percent is not None


# ─── 금액표 ───


@dataclass(frozen=True)
class Inputs:
    """저장 하나의 창 입력을 읽은 것 — 금액표를 셈하는 데 쓰는 모양."""
    price: Decimal
    original: Decimal | None
    net: Decimal | None
    plan_adjust: Adjust | None
    keys: tuple[str, ...]                 # 친 키(정규화) — 비면 ("",)
    typed_keys: bool                      # 인원 조합을 적었는지(적지 않으면 인원 무관 한 좌표)
    occupancy_adjust: Mapping[str, Adjust]
    los: Mapping[int, Decimal]
    rates: tuple[ChildRate, ...] = ()     # 쓸 수 있는 아동 구간만, 코드 차례

    @property
    def usable_rates(self) -> tuple[ChildRate, ...]:
        return tuple(rate for rate in self.rates if rate.usable)


def parse_inputs(texts: Mapping[str, str], rates: Iterable[ChildRate]) -> Inputs:
    """저장 하나의 글자들(창 칸 이름 → 글자) + 쓸 수 있는 아동 구간 → Inputs. 창이 거절할 것은 여기서 SeasonRefused 로 거절하고,
    금액표를 한 번 셈해 음수 · 빠진 성인 키 같은 거절도 미리 낸다(창이 저장 전에 같은 셈을 해 본다)."""
    for name, limit in FIELD_LIMITS.items():
        if len(str(texts.get(name) or "")) > limit:
            raise SeasonRefused(f"{name} 칸은 {limit}자까지입니다")
    price = parse_money(texts.get("price", ""), "판매 단가", required=True)
    original = parse_money(texts.get("original_price", ""), "정가")
    net = parse_money(texts.get("net_price", ""), "공급 원가")
    if original is not None and original < price:
        raise SeasonRefused("정가는 판매가보다 작을 수 없습니다")
    keys = parse_keys(texts.get("occupancy_keys", ""))
    occupancy_adjust = parse_occupancy_adjust(texts.get("occupancy_adjust", ""))
    if occupancy_adjust and not keys:
        raise SeasonRefused("조정은 인원 조합을 적은 전개에서만 쓰입니다 — 인원 조합 칸을 채우거나 이 칸을 비워주세요")
    rates = tuple(sorted((rate for rate in rates if rate.usable), key=lambda rate: rate.code))
    if rates and not keys:
        raise SeasonRefused("이 오퍼의 아동 요금을 적용하려면 A2처럼 기준 성인 수를 입력해주세요. 추가 금액을 비워도 연령 구간의 기본 "
                            "요금이 적용됩니다.")
    los = parse_los(texts.get("los_prices", ""))
    over = [nights for nights, value in los.items() if original is not None and value > original]
    if over:
        raise SeasonRefused("정가보다 비싼 박수 단가가 있습니다 — 정가를 올리거나 그 단가를 낮춰주세요 ("
                            + " · ".join(f"{nights}박" for nights in over) + ")")
    inputs = Inputs(price, original, net, parse_adjust(texts.get("plan_adjust", "")), tuple(keys or ("",)), keys is not None,
                    occupancy_adjust, los, rates)
    los_matrix(inputs)
    return inputs


def occupancy_matrix(inputs: Inputs, triple: Triple) -> dict[str, Triple]:
    """키 → 세 금액 — 인원 조합별 조정을 건 값(조정 없는 키는 그대로). 인원 조합 칸에 없는 키의 조정은 거절."""
    unknown = [key for key in inputs.occupancy_adjust if key not in inputs.keys]
    if unknown:
        raise SeasonRefused("인원 조합 칸에 없는 키의 조정입니다 — 키를 추가하거나 조정을 빼주세요 (" + " · ".join(unknown) + ")")
    out = {}
    for key in inputs.keys:
        try:
            out[key] = adjusted(inputs.occupancy_adjust.get(key), triple)
        except SeasonRefused as error:
            raise SeasonRefused(f"{key or '인원 무관 단일가'} — {error}") from None
    return out


def _adult_index(matrix: Mapping[str, Triple]) -> dict[int, str]:
    """성인 수 → 그 성인 키. 정규형(A3)이 맨 숫자("3")보다 앞선다."""
    index: dict[int, str] = {}
    for key in matrix:
        try:
            parsed = parse_key(key)
        except ValueError:
            continue
        if parsed.children:
            continue
        adults = parsed.adults if parsed.adults is not None else parsed.total
        if adults is None:
            continue
        if parsed.adults is not None or adults not in index:
            index[adults] = key
    return index


def _marginal(matrix, adults_index, adults: int, place: int, here: Decimal) -> Decimal:
    """성인 1인 추가분 — A<n+1> − A<n>, A<n+1> 이 없으면 A<n> / n."""
    upper = adults_index.get(adults + 1)
    if upper is not None and matrix[upper][place] is not None:
        return Decimal(matrix[upper][place]) - Decimal(here)
    if adults <= 0:
        raise SeasonRefused("성인이 0명인 좌표에는 `성인 요금의 %` 아동가를 걸 수 없습니다 — 성인 좌표(A1 이상)를 함께 적거나 그 구간에 "
                            "아동 추가 금액을 정액으로 적어주세요")
    return Decimal(here) / Decimal(adults)


def _combo(matrix, adults_index, rates: Mapping[str, ChildRate], key: str, parsed: Key) -> Triple:
    """아동 조합 키 하나의 세 금액 — 성인 키 + Σ(아동 수 × 구간 추가분), 0.01 반올림. 성인 키가 없거나 구간이 없으면 거절."""
    parent = adults_index.get(parsed.adults)
    if parent is None:
        raise SeasonRefused(f"{key} 의 성인 좌표 A{parsed.adults} 가 인원 조합 칸에 없습니다 — A{parsed.adults} 를 함께 적어주세요"
                            "(아동 금액은 성인 좌표 위에 얹힙니다)")
    out = []
    for place, amount in enumerate(matrix[parent]):
        if amount is None:
            out.append(None)
            continue
        total = Decimal(amount)
        for count, code in parsed.children:
            rate = rates.get(code)
            if rate is None:
                raise SeasonRefused(f"{key} 를 깔 값이 없습니다 — '{code}' 구간의 아동 추가 금액을 적거나 그 좌표를 인원 조합 칸에서 빼주세요")
            extra = (Decimal(rate.amount) if rate.amount is not None
                     else _marginal(matrix, adults_index, parsed.adults, place, amount) * Decimal(rate.percent) / Decimal(100))
            total += Decimal(count) * extra
        total = total.quantize(CENT, rounding=ROUND_HALF_UP)
        if total < 0:
            raise SeasonRefused(f"{key} 의 {AMOUNT_LABELS[place]}가 음수({total})가 됩니다 — 아동 추가 금액을 확인하세요")
        out.append(total)
    return tuple(out)


def expand_children(matrix: Mapping[str, Triple], rates: Iterable[ChildRate], explicit: Iterable[str]) -> dict[str, Triple]:
    """금액표에 아동 조합 키를 더한다 — 성인 키마다 그 바로 뒤에 쓸 수 있는 구간의 `A<n>C1_<코드>`(이미 있으면 건너뜀), 그리고 직접 친
    아동 키(조정을 적지 않은 것)는 같은 셈으로 다시 센다. 맨 숫자 · 코드 없는 키에는 매달지 않는다."""
    usable = [rate for rate in rates if rate.usable]
    if not usable:
        return dict(matrix)
    by_code, index, explicit = {rate.code: rate for rate in usable}, _adult_index(matrix), set(explicit)
    out: dict[str, Triple] = {}
    for key, amounts in matrix.items():
        try:
            parsed = parse_key(key)
        except ValueError:
            out[key] = amounts
            continue
        if parsed.children and parsed.adults is not None and key not in explicit and all(code for _count, code in parsed.children):
            out[key] = _combo(matrix, index, by_code, key, parsed)
            continue
        out[key] = amounts
        if parsed.adults is None or parsed.children:
            continue
        for rate in usable:
            child = build_key(parsed.adults, [(1, rate.code)])
            if child in matrix or child in out:
                continue
            out[child] = _combo(matrix, index, by_code, child, parse_key(child))
    return out


def amount_matrix(inputs: Inputs, price: Decimal) -> tuple[dict[str, Triple], dict[str, Triple]]:
    """한 박수 층의 (기준 요금제 표, 조정 요금제 표) — `price` 는 그 층의 1박 판매가, 정가 · 공급 원가는 1박의 것."""
    triple = (price, inputs.original, inputs.net)
    base = occupancy_matrix(inputs, triple)
    plan = base if inputs.plan_adjust is None else occupancy_matrix(inputs, adjusted(inputs.plan_adjust, triple))
    if not inputs.usable_rates:
        return base, plan
    wide_base = expand_children(base, inputs.usable_rates, inputs.occupancy_adjust)
    wide_plan = wide_base if plan is base else expand_children(plan, inputs.usable_rates, inputs.occupancy_adjust)
    return wide_base, wide_plan


def los_matrix(inputs: Inputs) -> dict[int, tuple[dict[str, Triple], dict[str, Triple]]]:
    """박수 층마다 amount_matrix — 1박이 첫 층이다. 층의 거절은 「N박 단가 — 」를 붙여 말한다."""
    out = {}
    for nights, price in [(1, inputs.price), *inputs.los.items()]:
        try:
            out[nights] = amount_matrix(inputs, price)
        except SeasonRefused as error:
            if nights == 1:
                raise
            raise SeasonRefused(f"{nights}박 단가 — {error}") from None
    return out


# ─── 객실의 허용 인원 조합 ───


@dataclass(frozen=True, order=True)
class Combo:
    """허용 조합 하나 — 성인 · 유료 아동 각각의 천장."""
    adults: int
    children: int = 0

    @property
    def total(self) -> int:
        return self.adults + self.children


COMBO_SPLIT = re.compile(r"\s*(?:[,/;\n]|\bOR\b|또는)\s*", re.IGNORECASE)
COMBO_FORMS = (re.compile(r"^(\d+)\s*A(?:\s*\+?\s*(\d+)\s*C)?$"), re.compile(r"^A\s*(\d+)(?:\s*C\s*(\d+))?$"))
COMBO_KOREAN = re.compile(r"^성인\s*(\d+)\s*명?(?:\s*\+?\s*(?:소아|아동)\s*(\d+)\s*명?)?$")


def parse_combos(text: str | None) -> tuple[Combo, ...] | None:
    """객실 타입 표의 「허용 인원 조합」 글자 → 조합들. 비었거나 「조합 제한 없음」이면 `()`(제한 없음). 읽지 못하면 None(모름)."""
    raw = (text or "").strip()
    if not raw or raw == NO_COMBOS:
        return ()
    combos = []
    for item in COMBO_SPLIT.split(raw):
        item = item.strip()
        if not item:
            continue
        found = next((form.match(item.upper()) for form in COMBO_FORMS if form.match(item.upper())), None) or COMBO_KOREAN.match(item)
        if found is None or "_" in item:
            return None
        combos.append(Combo(int(found.group(1)), int(found.group(2) or 0)))
    return tuple(sorted(set(combos)))


def key_allowed(combos: Iterable[Combo], key: str) -> bool:
    """그 좌표를 그 객실에 깔아도 되는지 — 아동 조각이 있으면 (성인, 아동 합)이 어느 조합의 천장 안, 없으면 머릿수가 가장 큰 조합의
    총원 이하. 조합이 없거나(제한 없음) 인원 무관 · 읽지 못하는 키는 참."""
    combos = tuple(combos)
    if not combos:
        return True
    try:
        parsed = parse_key(key)
    except ValueError:
        return True
    if parsed.adults is None and parsed.total is None:
        return True
    if not parsed.children:
        heads = parsed.adults if parsed.adults is not None else parsed.total
        return heads <= max(combo.total for combo in combos)
    children = sum(count for count, _code in parsed.children)
    return any(parsed.adults <= combo.adults and children <= combo.children for combo in combos)
