"""되돌리기 계산 — 장부의 변경 하나(또는 그 일부)를 적어 둔 값으로 돌리거나(plan_rollback), 저장해 둔 상태로 돌린다(plan_restore).

되돌리기는 항목마다 본다: 그 변경이 쓴 필드가 지금도 모두 그때 넣은 값이면 적어 둔 값으로 돌리고, 하나라도 다르면 그대로 둔다.
그대로 두는 항목에는 세 값(적어 둔 값 · 넣은 값 · 지금 값)과 까닭을 단다. 까닭은 이 장부의 나중 변경 가운데 지금 값을
넣은 가장 최근 것, 없으면 도우미 밖이다. 그 변경이 새로 만든 항목(전 상태가 missing)은 지울 길이 없어 「지울 수 없는 것」이다.

저장해 둔 상태로 돌리기는 그 범위의 모든 항목을 저장해 둔 값으로 맞춘다. 그때 없던 항목(없음으로 적었거나 아예 적지 않은 것 —
그 뒤에 새로 생긴 줄 · 박수 층 같은)이 지금 있으면 「지울 수 없는 것」이다.
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
    hotel_id: str = ""


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

    @property
    def outside(self) -> bool:
        return self.change_id is None


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
    """`mode` 가 rollback 이면 `reverses` 변경을 되돌리고, restore 면 `reverses` 번 저장해 둔 상태로 돌린다."""
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
    unremovable: tuple[KeptItem, ...] = ()
    mode: str = "rollback"
    hotel_id: str = ""


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
    restored, kept, unremovable = [], [], []
    for item in items:
        current = now.get((item.kind, item.key)) or absent(item.label)
        recorded_values = {name: item.before.get(name) for name in item.written}
        if item.state == MISSING_STATE:
            unremovable.append(KeptItem(item.kind, item.key, item.label, recorded_values, item.written, current, Cause()))
            continue
        targets = {name: value for name, value in recorded_values.items()
                   if current.state == MISSING_STATE or current.fields.get(name) != value}
        restore = RestoredItem(item.kind, item.key, item.label, current, targets) if targets else None
        if holds(current, item.written):
            if restore:
                restored.append(restore)
            continue
        cause = next((Cause(write.change_id, write.at, write.sentence)
                      for write in reversed(later.get((item.kind, item.key), ())) if holds(current, write.written)), Cause())
        kept.append(KeptItem(item.kind, item.key, item.label, recorded_values, item.written, current, cause))
        if include_kept and restore:
            restored.append(restore)
    return RollbackPlan(recorded.id, recorded.hotel, recorded.offer, recorded.currency, recorded.read_at,
                        recorded.sentence, recorded.applied_at, read_at, tuple(restored), tuple(kept), include_kept,
                        tuple(unremovable), hotel_id=recorded.hotel_id)


def plan_restore(snapshot: RecordedChange, now: Reading, read_at: str,
                 select: Callable[[str, str], bool] | None = None) -> RollbackPlan:
    """저장해 둔 상태(장부의 snapshot)로 돌리기 — 고른 범위의 항목마다 지금 값과 다른 필드를 저장해 둔 값으로 맞춘다.

    그때 있었고 지금 없는 항목은 저장해 둔 값으로 다시 만든다. 그때 없었고 지금 있는 항목은 지울 수 없는 것으로 둔다 — 없음으로
    적어 둔 항목도, 저장해 둔 상태에 아예 없는 항목도. 지금 읽은 값(`now`)에서는 `select` 가 고른 항목만 본다(저장해 둔 범위 밖의
    항목을 고르지 않는 것은 부르는 쪽의 몫이다).
    """
    chosen = select or (lambda _kind, _key: True)
    items = [item for item in snapshot.items if chosen(item.kind, item.key)]
    if not items:
        raise Refused("고른 범위에 저장해 둔 값이 없습니다")
    held = {(item.kind, item.key) for item in snapshot.items}
    restored, unremovable = [], []
    for item in items:
        current = now.get((item.kind, item.key)) or absent(item.label)
        if item.state == MISSING_STATE:
            if current.state != MISSING_STATE:
                unremovable.append(KeptItem(item.kind, item.key, item.label, {}, {}, current, Cause()))
            continue
        if current.state == MISSING_STATE:
            targets = {name: value for name, value in item.before.items() if value is not None}
        else:
            targets = {name: value for name, value in item.before.items() if current.fields.get(name) != value}
        if targets:
            restored.append(RestoredItem(item.kind, item.key, item.label, current, targets))
    for (kind, key), current in sorted(now.items()):
        if (kind, key) not in held and current.state != MISSING_STATE and chosen(kind, key):
            unremovable.append(KeptItem(kind, key, current.label, {}, {}, current, Cause()))
    return RollbackPlan(snapshot.id, snapshot.hotel, snapshot.offer, snapshot.currency, snapshot.read_at, snapshot.sentence,
                        None, read_at, tuple(restored), (), False, tuple(unremovable), "restore", snapshot.hotel_id)


def _fields(values: Fields) -> dict:
    return {name: money_text(value) for name, value in values.items()}


def _read_fields(data: Mapping) -> dict:
    return {name: money(value) for name, value in data.items()}


def _encode_kept(item: KeptItem) -> dict:
    return dict(kind=item.kind, key=item.key, label=item.label, recorded=_fields(item.recorded),
                written=_fields(item.written), now=encode_state(item.now),
                cause=dict(change_id=item.cause.change_id, at=item.cause.at, sentence=item.cause.sentence))


def _decode_kept(item: Mapping) -> KeptItem:
    return KeptItem(item["kind"], item["key"], item["label"], _read_fields(item["recorded"]), _read_fields(item["written"]),
                    decode_state(item["now"]), Cause(**item["cause"]))


def encode_rollback(plan: RollbackPlan) -> dict:
    return dict(
        mode=plan.mode, reverses=plan.reverses, hotel=plan.hotel, hotel_id=plan.hotel_id, offer=plan.offer, currency=plan.currency, restore_to=plan.restore_to,
        original_sentence=plan.original_sentence, original_applied_at=plan.original_applied_at, read_at=plan.read_at,
        include_kept=plan.include_kept,
        restored=[dict(kind=item.kind, key=item.key, label=item.label, now=encode_state(item.now),
                       targets=_fields(item.targets)) for item in plan.restored],
        kept=[_encode_kept(item) for item in plan.kept],
        unremovable=[_encode_kept(item) for item in plan.unremovable],
    )


def decode_rollback(data: Mapping) -> RollbackPlan:
    return RollbackPlan(
        int(data["reverses"]), str(data["hotel"]), str(data["offer"]), str(data["currency"]), str(data["restore_to"]),
        str(data.get("original_sentence") or ""), data.get("original_applied_at"), str(data["read_at"]),
        tuple(RestoredItem(item["kind"], item["key"], item["label"], decode_state(item["now"]),
                           _read_fields(item["targets"])) for item in data["restored"]),
        tuple(_decode_kept(item) for item in data.get("kept") or ()),
        bool(data.get("include_kept")),
        tuple(_decode_kept(item) for item in data.get("unremovable") or ()),
        str(data.get("mode") or "rollback"),
        str(data.get("hotel_id") or ""),
    )
