"""이름 · 설명에 적힌 바꾸기 전 값 — 도우미는 이름과 설명을 바꾸지 않는다. 그래서 바꾸는 값이 이름이나 설명에 화면이 쓰는
꼴(50 · 50.00 · 50% · 93.28 · 93,280)로 적혀 있으면 미리보기와 결과가 한 문장으로 알린다. 빨간 줄이 아니라 알림이다.

글 안의 숫자 하나가 그 값인지는 이렇게 가린다 — 값이 같고, 아래의 어느 것도 아닐 때만 그 값이다:

    시각       `:` 에 붙은 숫자 — `14:00` · `12:01~14:00`
    날짜       `/` · `-` · `.` 를 사이에 두고 다른 숫자에 붙은 숫자 — `12/24` · `2026-12-24` · `2026.12.24`
    나이 · 수  바로 뒤에 세 · 살 · 박 · 인 · 명 · 개 · 시 · 분 · 회 · 번 · 층 · 호 · 일 · 월 · 년 이 붙은 숫자, 그리고 `~` 로
               그런 숫자에 이어진 앞 숫자 — `만 6~11세` · `1박` · `2인` · `14시 이후` · `12월 24일`
    코드       바로 앞에 로마자가 붙은 숫자 — `A2` · `C1`

그리고 정률(%) 칸의 값은 `%`(또는 `퍼센트`)가 붙은 숫자만, 금액 칸의 값은 `%` 가 붙지 않은 숫자만 그 값으로 친다 — 정액 10달러인
부과금의 이름 「봉사료 10%」는 알리지 않는다. 숫자는 쉼표와 소수점 아래 0 을 빼고 값으로 견준다(`93,280` = 93280, `50` = 50.00).
한글로 적은 수(「5만 원」)는 보지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable

NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
JOINS = ":/-."                       # 숫자와 숫자 사이에 오면 시각 · 날짜다
UNITS = "세살박인명개시분회번층호일월년"   # 바로 뒤에 붙으면 나이 · 수 · 시각 · 날짜다
RANGE = re.compile(r"\s*[~∼〜]\s*(\d+)([" + UNITS + "])")
PERCENT = re.compile(r"\s?(%|％|퍼센트)")
QUOTE = 60                           # 설명을 옮겨 보일 때의 글자 수(그 값 앞뒤로)


def _touches_number(text: str, at: int, step: int) -> bool:
    """`at` 자리의 글자가 시각 · 날짜의 이음표이고 그 너머가 숫자인지."""
    beyond = at + step
    return 0 <= at < len(text) and text[at] in JOINS and 0 <= beyond < len(text) and text[beyond].isdigit()


def stated(text: str, value: Decimal | None, percent: bool) -> str | None:
    """`text` 안에 `value` 가 적힌 꼴(찾은 글자, 정률이면 `%` 까지) — 없으면 None."""
    if value is None or not text:
        return None
    for found in NUMBER.finditer(text):
        start, end = found.span()
        before, after = text[start - 1] if start else "", text[end] if end < len(text) else ""
        if (before == ":" or after == ":" or _touches_number(text, start - 1, -1) or _touches_number(text, end, 1)
                or (before.isascii() and before.isalpha()) or (after and after in UNITS) or RANGE.match(text, end)):
            continue
        mark = PERCENT.match(text, end)
        if bool(mark) != percent:
            continue
        try:
            number = Decimal(found.group(0).replace(",", ""))
        except InvalidOperation:
            continue
        if number == value:
            return text[start:mark.end()] if mark else found.group(0)
    return None


def quoted(text: str, piece: str) -> str:
    """긴 설명은 찾은 글자 앞뒤만 옮겨 보인다."""
    text = " ".join(text.split())
    if len(text) <= QUOTE:
        return text
    at = max(text.find(piece), 0)
    start = max(0, min(at - QUOTE // 2, len(text) - QUOTE))
    return ("…" if start else "") + text[start:start + QUOTE] + ("…" if start + QUOTE < len(text) else "")


@dataclass(frozen=True)
class NameNote:
    """이름이나 설명 하나에 바꾸기 전 값이 적힌 것 — `what` 은 무엇의(「부과금 「…」」), `where` 는 이름 · 설명, `text` 는 그 글, `piece`
    는 찾은 글자."""
    what: str
    where: str
    text: str
    piece: str

    @property
    def sentence(self) -> str:
        shown = "" if self.where == "이름" else f" “{quoted(self.text, self.piece)}”"
        return (f"{self.what}의 {self.where}{shown}에 바꾸기 전 값({self.piece})이 그대로 적혀 있습니다 — 도우미는 "
                f"{self.where}을 바꾸지 않으니 ERP 에서 사람이 고쳐 주세요.")


def name_notes(found: Iterable[tuple[str, str, str, Decimal | None, bool]]) -> list[NameNote]:
    """(무엇의, 이름 · 설명, 그 글, 바꾸기 전 값, 정률인지)마다 그 글에 그 값이 적혔으면 알림 하나 — 같은 글의 같은 글자는 한 번."""
    notes: dict[tuple[str, str, str, str], NameNote] = {}
    for what, where, text, value, percent in found:
        piece = stated(text, value, percent)
        if piece is not None:
            notes.setdefault((what, where, text, piece), NameNote(what, where, text, piece))
    return list(notes.values())
