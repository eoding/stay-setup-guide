"""통화 자릿수와 반올림(ERP `pricing.money.normalize` 와 같다), 금액 글자 ↔ Decimal. float 는 쓰지 않는다."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ZERO_DECIMAL_CURRENCIES = frozenset({"KRW", "VND", "JPY", "IDR", "CLP", "ISK"})


def scale_of(currency: str) -> int:
    return 0 if currency.upper() in ZERO_DECIMAL_CURRENCIES else 2


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
