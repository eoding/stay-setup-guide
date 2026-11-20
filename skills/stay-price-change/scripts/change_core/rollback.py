"""되돌리기 계산 — 장부의 변경 하나(또는 그 일부)를 적어 둔 값으로 돌린다.

항목마다 본다: 그 변경이 쓴 필드가 지금도 모두 그때 넣은 값이면 적어 둔 값으로 돌리고, 하나라도 다르면 그대로 둔다.
그대로 두는 항목에는 세 값(적어 둔 값 · 넣은 값 · 지금 값)과 까닭을 단다. 까닭은 이 장부의 나중 변경 가운데 지금 값을
넣은 가장 최근 것, 없으면 도우미 밖이다. 그 변경이 새로 만든 항목(전 상태가 missing)은 지울 길이 없어 늘 그대로 둔다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Mapping, Sequence

from .items import MISSING_STATE, ItemState, Reading, Refused, absent, decode_state, encode_state
from .money import money, money_text

Fields = Mapping[str, Decimal | None]


@dataclass(frozen=True)
class RecordedItem:
    """장부의 항목 하나 — 적어 둔 전 값(필드 전부)과 그 변경이 실제로 저장했고 아직 되돌리지 않은 필드의 넣은 값.

    넣은 값이 None 이면 그 필드를 비웠다는 뜻이다.
    """
    kind: str
    key: str
    label: str
    state: str
    before: Fields
    written: Fields


@dataclass(frozen=True)
class RecordedChange:
    id: int
    kind: str
    hotel: str
    offer: str
    currency: str
    sentence: str
    read_at: str
    applied_at: str | None
    items: tuple[RecordedItem, ...]


@dataclass(frozen=True)
class LaterWrite:
    change_id: int
    at: str
    sentence: str
    written: Fields


@dataclass(frozen=True)
class Cause:
    change_id: int | None = None
    at: str | None = None
    sentence: str | None = None
    created: bool = False

    @property
    def outside(self) -> bool:
        return self.change_id is None and not self.created


@dataclass(frozen=True)
class RestoredItem:
    kind: str
    key: str
    label: str
    now: ItemState
    targets: Fields


@dataclass(frozen=True)
class KeptItem:
    kind: str
    key: str
    label: str
    recorded: Fields
    written: Fields
    now: ItemState
    cause: Cause


@dataclass(frozen=True)
class RollbackPlan:
    reverses: int
    hotel: str
    offer: str
    currency: str
    restore_to: str
    original_sentence: str
    original_applied_at: str | None
    read_at: str
    restored: tuple[RestoredItem, ...]
    kept: tuple[KeptItem, ...]
    include_kept: bool


def holds(state: ItemState, written: Fields) -> bool:
    return state.state != MISSING_STATE and all(state.fields.get(name) == value for name, value in written.items())


def plan_rollback(recorded: RecordedChange, later: Mapping[tuple[str, str], Sequence[LaterWrite]], now: Reading,
                  read_at: str, include_kept: bool = False,
                  select: Callable[[str, str], bool] | None = None) -> RollbackPlan:
    """`select(종류, 키)` 로 고른 항목만 본다(없으면 전부). `include_kept` 면 그 사이 달라진 항목도 돌린다."""
    if not recorded.items:
        raise Refused("이 변경으로 저장된 것 가운데 아직 되돌리지 않은 것이 없습니다")
    items = [item for item in recorded.items if select is None or select(item.kind, item.key)]
    if not items:
        raise Refused("고른 범위에 되돌릴 것이 없습니다")
    restored, kept = [], []
    for item in items:
        current = now.get((item.kind, item.key)) or absent(item.label)
        recorded_values = {name: item.before.get(name) for name in item.written}
        if item.state == MISSING_STATE:
            kept.append(KeptItem(item.kind, item.key, item.label, recorded_values, item.written, current, Cause(created=True)))
            continue
        restore = RestoredItem(item.kind, item.key, item.label, current, recorded_values)
        if holds(current, item.written):
            restored.append(restore)
            continue
        cause = next((Cause(write.change_id, write.at, write.sentence)
                      for write in reversed(later.get((item.kind, item.key), ())) if holds(current, write.written)), Cause())
        kept.append(KeptItem(item.kind, item.key, item.label, recorded_values, item.written, current, cause))
        if include_kept:
            restored.append(restore)
    return RollbackPlan(recorded.id, recorded.hotel, recorded.offer, recorded.currency, recorded.read_at,
                        recorded.sentence, recorded.applied_at, read_at, tuple(restored), tuple(kept), include_kept)


def _fields(values: Fields) -> dict:
    return {name: money_text(value) for name, value in values.items()}


def _read_fields(data: Mapping) -> dict:
    return {name: money(value) for name, value in data.items()}


def encode_rollback(plan: RollbackPlan) -> dict:
    return dict(
        reverses=plan.reverses, hotel=plan.hotel, offer=plan.offer, currency=plan.currency, restore_to=plan.restore_to,
        original_sentence=plan.original_sentence, original_applied_at=plan.original_applied_at, read_at=plan.read_at,
        include_kept=plan.include_kept,
        restored=[dict(kind=item.kind, key=item.key, label=item.label, now=encode_state(item.now),
                       targets=_fields(item.targets)) for item in plan.restored],
        kept=[dict(kind=item.kind, key=item.key, label=item.label, recorded=_fields(item.recorded),
                   written=_fields(item.written), now=encode_state(item.now),
                   cause=dict(change_id=item.cause.change_id, at=item.cause.at, sentence=item.cause.sentence,
                              created=item.cause.created)) for item in plan.kept],
    )


def decode_rollback(data: Mapping) -> RollbackPlan:
    return RollbackPlan(
        int(data["reverses"]), str(data["hotel"]), str(data["offer"]), str(data["currency"]), str(data["restore_to"]),
        str(data.get("original_sentence") or ""), data.get("original_applied_at"), str(data["read_at"]),
        tuple(RestoredItem(item["kind"], item["key"], item["label"], decode_state(item["now"]),
                           _read_fields(item["targets"])) for item in data["restored"]),
        tuple(KeptItem(item["kind"], item["key"], item["label"], _read_fields(item["recorded"]),
                       _read_fields(item["written"]), decode_state(item["now"]), Cause(**item["cause"]))
              for item in data.get("kept") or ()),
        bool(data.get("include_kept")),
    )
