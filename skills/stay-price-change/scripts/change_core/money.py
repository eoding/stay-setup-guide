"""통화 자릿수와 반올림(ERP `pricing.money.normalize` 와 같다), 금액 글자 ↔ Decimal. float 는 쓰지 않는다."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ZERO_DECIMAL_CURRENCIES = frozenset({"KRW", "VND", "JPY", "IDR", "CLP", "ISK"})


def scale_of(currency: str) -> int:
    return 0 if currency.upper() in ZERO_DECIMAL_CURRENCIES else 2


EXAMPLE_STEPS = {"KRW": "10,000", "VND": "100,000", "IDR": "100,000", "JPY": "1,000"}


def example_step(currency: str) -> str:
    """페이지가 「이렇게 말씀해 주세요」의 보기에 쓰는 올림 금액 — 그 통화에 맞는 크기(원은 만, 동 · 루피아는 십만, 엔은 천, 소수 둘인
    통화는 10). 달러 호텔에 「+10,000」을 보기로 들지 않는다."""
    code = currency.upper()
    return EXAMPLE_STEPS.get(code, "1,000" if scale_of(code) == 0 else "10")


def round_money(value: Decimal, currency: str) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-scale_of(currency)), rounding=ROUND_HALF_UP)


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
