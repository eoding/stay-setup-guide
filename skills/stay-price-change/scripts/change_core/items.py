"""항목 값의 공통 모양과 낡음 확인.

항목 하나 = (종류, 키). 종류는 `price_cell` 같은 글자, 키는 그 항목을 가리키는 칸들을 `item_key` 로 굳힌 글자다.
한 번 읽은 값 전부(Reading)는 (종류, 키) → ItemState(이름, 상태, 필드 → 값) 이다. 상태 `missing` 은 그 항목이 없다는 뜻이다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from .money import money, money_text

MISSING_STATE = "missing"


class Refused(ValueError):
    """요청이 읽은 값·장부와 맞지 않아 진행하지 않는다 — 문장은 담당자에게 그대로 보여 줄 수 있다."""


def item_key(fields: Mapping[str, object]) -> str:
    """항목을 가리키는 칸들 → 장부에 적는 굳은 글자(이름순 JSON). 같은 항목은 언제나 같은 글자가 된다."""
    return json.dumps(dict(fields), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def key_fields(text: str) -> dict:
    return json.loads(text)


@dataclass(frozen=True)
class ItemState:
    label: str
    state: str
    fields: Mapping[str, Decimal | None]

    def same_as(self, other: "ItemState | None") -> bool:
        return other is not None and self.state == other.state and dict(self.fields) == dict(other.fields)


Reading = Mapping[tuple[str, str], ItemState]


def absent(label: str) -> ItemState:
    return ItemState(label, MISSING_STATE, {})


@dataclass(frozen=True)
class Difference:
    kind: str
    key: str
    then: ItemState | None
    now: ItemState | None


def stale_items(then: Reading, now: Reading) -> tuple[Difference, ...]:
    """미리보기 때 읽은 값과 방금 읽은 값이 다른 항목 전부. 한쪽에만 있는 항목도 다른 항목이다."""
    differences = []
    for kind, key in sorted(set(then) | set(now)):
        before, after = then.get((kind, key)), now.get((kind, key))
        if before is None or not before.same_as(after):
            differences.append(Difference(kind, key, before, after))
    return tuple(differences)


def encode_state(state: ItemState | None) -> dict | None:
    if state is None:
        return None
    return dict(label=state.label, state=state.state, fields={name: money_text(v) for name, v in state.fields.items()})


def decode_state(data: Mapping | None) -> ItemState | None:
    if data is None:
        return None
    return ItemState(str(data["label"]), str(data["state"]), {name: money(v) for name, v in data["fields"].items()})
