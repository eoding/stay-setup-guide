"""price_compare.py — 저장해 둔 상태와 지금 견주기. 장부에 저장해 둔 상태(지금 상태 저장)와 그 범위를 방금 읽은 값이 칸마다
어떻게 다른지 세고, 다른 칸마다 누가 바꿨는지 장부가 아는 만큼 댄다. 아무것도 바꾸지 않고 장부에도 적지 않는다.

칸마다 종류 하나다(KINDS):

    changed  값(판매가 · 정가 · 공급 원가)이 달라진 칸
    new      저장해 둔 때 없던(가격이 없었거나 그 칸이 아예 없던) 칸에 지금 값이 있다 — 저장해 둔 상태로 되돌려도 지울 수 없다
    gone     저장해 둔 때 값이 있던 칸이 지금 없다
    closed   값은 같고 판매 마감 · 판매 가능만 달라졌다(되돌리기는 이것을 되돌리지 않는다)
    same     그대로

바뀐 칸 · 새로 생긴 칸 · 없어진 칸에는 누가 바꿨는지를 단다:

    written_by  저장한 뒤 이 장부의 기록(변경 · 되돌리기 · 저장 상태로 되돌리기)이 그 칸에 마지막으로 넣은 값이 지금도 그대로이고,
                저장해 둔 때와 다른 필드를 모두 이 장부의 그 뒤 기록들이 넣었으면 그 마지막 기록의 번호다
    (없음)      그 밖은 장부에 없는 변화다 — 도우미 밖(ERP 화면 · 시즌 채우기 · 다른 컴퓨터)에서 바뀌었다. 도우미는 칸을 지우지
                않으므로 없어진 칸은 늘 이쪽이다

그리고 바뀐 칸 · 없어진 칸에는 `edited_by` 를 단다 — 저장해 둔 때 그 칸이 이 장부의 앞선 변경이 날짜별로 넣은 값을 그대로 갖고
있었으면 그 변경 번호다(ERP 가 「손입력」으로 표시하는 칸이다). ERP 화면에서 사람이 직접 고친 칸은 읽은 값으로 가려내지 못한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from change_core.rollback import LaterWrite

from price_model import (
    FIELDS, MISSING, CellKey, CellValue, Snapshot, decode_hotel, decode_key, decode_value, encode_hotel, encode_key, encode_value,
    hotel_label, iso_day, same_hotel,
)
from price_plan import PlanError

KINDS = ("changed", "new", "gone", "closed", "same")
MOVED = ("changed", "new", "gone")      # 누가 바꿨는지 대는 칸 — 마감 · 판매 가능만 바뀐 칸은 값이 그대로라 빠진다


@dataclass(frozen=True)
class CellCompare:
    """칸 하나 — 저장해 둔 값(`then`)과 지금 값(`now`), 없던 칸은 MISSING."""
    key: CellKey
    then: CellValue
    now: CellValue
    kind: str
    edited_by: int | None = None
    written_by: int | None = None


@dataclass(frozen=True)
class Writer:
    """저장한 뒤 칸을 바꾼 이 장부의 기록 하나 — 번호 · 무엇(변경 · 되돌리기 · 저장 상태로 되돌리기) · 담당자의 말 · 마지막 저장 시각 ·
    지금도 그 기록의 값인 칸 수."""
    change_id: int
    what: str
    sentence: str
    at: str
    cells: int


@dataclass(frozen=True)
class Comparison:
    """`saved` 는 저장해 둔 상태의 장부 번호, `saved_at` 은 그 값을 ERP 에서 읽은 시각, `read_at` 은 지금 값을 읽은 시각이다.
    `reserved` 는 지금 읽은 값의 예약 있는 (객실, 날짜) — 저장해 둔 범위 안의 것."""
    saved: int
    sentence: str
    hotel: str
    hotel_id: str
    offer: str
    currency: str
    saved_at: str
    read_at: str
    cells: tuple[CellCompare, ...]
    reserved: frozenset[tuple[str, str]]
    writers: tuple[Writer, ...] = ()

    def of(self, kind: str) -> list[CellCompare]:
        return [cell for cell in self.cells if cell.kind == kind]


def kind_of(then: CellValue, now: CellValue) -> str:
    if then.state == "missing":
        return "same" if now.state == "missing" else "new"
    if now.state == "missing":
        return "gone"
    if any(getattr(then, name) != getattr(now, name) for name in FIELDS):
        return "changed"
    return "closed" if then.state != now.state else "same"


def written_by(then: CellValue, now: CellValue, writes: Sequence[LaterWrite]) -> int | None:
    """그 칸을 저장한 뒤에 바꾼 이 장부의 기록 — 마지막 기록이 넣은 값이 지금도 그대로이고, 저장해 둔 때와 다른 필드를 모두 그 뒤
    기록들이 넣었으면 그 마지막 기록의 번호. 아니면 None(장부에 없는 변화)."""
    if not writes or now.state == "missing":
        return None
    last = writes[-1]
    if any(getattr(now, name) != value for name, value in last.written.items()):
        return None
    moved = {name for name in FIELDS if getattr(then, name) != getattr(now, name)}
    return last.change_id if moved <= {name for write in writes for name in write.written} else None


def compare_saved(saved_id: int, sentence: str, saved: Snapshot, now: Snapshot, edited: Mapping[CellKey, int],
                  later: Mapping[CellKey, Sequence[LaterWrite]] | None = None, what: Mapping[int, str] | None = None) -> Comparison:
    """저장해 둔 상태(`saved` — 그때 읽은 값)와 같은 범위를 지금 읽은 값(`now`)을 칸마다 견준다. `edited` 는 저장해 둔 때 이 장부의
    앞선 변경이 날짜별로 넣은 값을 갖고 있던 칸 → 그 변경 번호. `later` 는 저장한 뒤 이 장부가 칸마다 넣은 값(오래된 것부터 —
    Ledger.later_writes), `what` 은 그 기록 번호 → 무엇(변경 · 되돌리기 · 저장 상태로 되돌리기). 지금 값이 다른 호텔 · 오퍼이거나
    저장한 범위를 다 읽지 않았으면 거절한다. 지금 값을 더 넓게 읽었으면 저장한 범위 안의 칸만 본다."""
    if not same_hotel(saved.hotel, saved.hotel_id, now.hotel, now.hotel_id) or saved.offer != now.offer:
        raise PlanError(f"지금 읽은 값은 {hotel_label(now.hotel, now.hotel_id)} · {now.offer} 것이고, 저장해 둔 상태는 "
                        f"{hotel_label(saved.hotel, saved.hotel_id)} · {saved.offer} 입니다")
    pairs, days = set(saved.pairs), set(saved.dates)
    unread = sorted(pairs - set(now.pairs)) or sorted(days - set(now.dates))
    if unread:
        shown = " · ".join("/".join(item) if isinstance(item, tuple) else item for item in unread[:5])
        raise PlanError(f"지금 값을 저장해 둔 범위만큼 읽지 않았습니다(읽지 않은 것: {shown}{' …' if len(unread) > 5 else ''}) — "
                        f"read-calls --record {saved_id} 로 그 범위를 읽습니다")
    keys = set(saved.cells) | {key for key in now.cells if (key.room, key.rate_plan) in pairs and key.date in days}
    later, what = later or {}, what or {}
    cells, writers = [], {}
    for key in sorted(keys):
        then, current = saved.cells.get(key, MISSING), now.cells.get(key, MISSING)
        kind = kind_of(then, current)
        writer = written_by(then, current, later.get(key, ())) if kind in MOVED else None
        if writer is not None:
            at = max(write.at for write in later[key] if write.change_id == writer)
            sentence_of = next(write.sentence for write in later[key] if write.change_id == writer)
            entry = writers.setdefault(writer, dict(at=at, sentence=sentence_of, cells=0))
            entry["at"], entry["cells"] = max(entry["at"], at), entry["cells"] + 1
        cells.append(CellCompare(key, then, current, kind, edited.get(key) if kind in ("changed", "gone") else None, writer))
    reserved = frozenset((room, day) for room, day in now.reserved if day in days and any(room == r for r, _ in pairs))
    return Comparison(saved_id, sentence, saved.hotel, saved.hotel_id, saved.offer, saved.currency, saved.read_at, now.read_at,
                      tuple(cells), reserved,
                      tuple(Writer(number, what.get(number, "변경"), entry["sentence"], entry["at"], entry["cells"])
                            for number, entry in sorted(writers.items())))


def compare_counts(comparison: Comparison) -> dict:
    """종류마다의 칸 수, 그리고 `edited` 날짜별로 바꿔 두었다가 바뀌거나 없어진 칸 · `reserved` 바뀐 칸 가운데 예약 있는 날의 칸 ·
    `helper` 저장한 뒤 이 장부의 기록이 바꾼 칸 · `outside` 장부에 없는 변화(바뀐 · 새로 생긴 · 없어진 칸 가운데 helper 가 아닌 것)."""
    found = {kind: len(comparison.of(kind)) for kind in KINDS}
    found["edited"] = sum(cell.edited_by is not None for cell in comparison.cells)
    found["helper"] = sum(cell.written_by is not None for cell in comparison.cells)
    found["outside"] = sum(cell.kind in MOVED and cell.written_by is None for cell in comparison.cells)
    found["reserved"] = sum((cell.key.room, cell.key.date) in comparison.reserved for cell in comparison.of("changed"))
    found["cells"] = len(comparison.cells)
    return found


def encode_comparison(comparison: Comparison) -> dict:
    return dict(kind="compare", saved=comparison.saved, sentence=comparison.sentence,
                hotel=encode_hotel(comparison.hotel, comparison.hotel_id), offer=comparison.offer, currency=comparison.currency,
                saved_at=comparison.saved_at, read_at=comparison.read_at,
                reserved=[dict(room=room, date=day) for room, day in sorted(comparison.reserved)],
                written_by=[dict(change_id=w.change_id, what=w.what, sentence=w.sentence, at=w.at, cells=w.cells)
                            for w in comparison.writers],
                cells=[dict(key=encode_key(cell.key), then=encode_value(cell.then), now=encode_value(cell.now), kind=cell.kind,
                            edited_by=cell.edited_by, written_by=cell.written_by) for cell in comparison.cells])


def decode_comparison(data: Mapping) -> Comparison:
    if data.get("kind") != "compare":
        raise ValueError("compare 가 낸 파일이 아닙니다")
    hotel, hotel_id = decode_hotel(data["hotel"])
    return Comparison(int(data["saved"]), str(data["sentence"]), hotel, hotel_id, str(data["offer"]), str(data["currency"]),
                      str(data["saved_at"]), str(data["read_at"]),
                      tuple(CellCompare(decode_key(item["key"]), decode_value(item["then"]), decode_value(item["now"]),
                                        str(item["kind"]), item.get("edited_by"), item.get("written_by")) for item in data["cells"]),
                      frozenset((str(item["room"]), iso_day(item["date"])) for item in data["reserved"]),
                      tuple(Writer(int(w["change_id"]), str(w["what"]), str(w["sentence"]), str(w["at"]), int(w["cells"]))
                            for w in data.get("written_by") or ()))
