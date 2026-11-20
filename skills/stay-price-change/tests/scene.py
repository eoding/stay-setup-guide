"""그림(화면 다섯 장)의 장면 — "데모 호텔 연말 금·토, 디럭스랑 스위트 10% 올려줘". 값은 전부 지어낸 것이다.

그림의 스크립트와 같은 재료다: 객실 2 × 요금제 2, 금·토 네 날, 인원 조합 3(A2 · A3 = A2 + 60 · A2C1_CHD = A2 + 30),
박수 층 2(3박 이상 = 그 값 × 0.9, 센트 반올림), 스위트 룸온리 1/2 는 가격 없음, 디럭스 룸온리 12/26 은 판매 마감,
예약 있는 날은 디럭스 12/25 · 스위트 1/1, 스위트 조식 포함 1/1 · 1/2 의 성인 2 · 1박 칸만 정가 500.
"""

from dataclasses import replace
from decimal import Decimal

from change_core.money import round_money
from price_model import MISSING, CellKey, CellValue, ChangeRequest, Snapshot

HOTEL, OFFER = "데모 호텔", "기본 오퍼"
HOTEL_ID = "1"                       # 지어낸 호텔 번호(페이지의 #master_id)
HOTEL_REF = {"id": HOTEL_ID, "name": HOTEL}
DATES = ("2026-12-25", "2026-12-26", "2027-01-01", "2027-01-02")
OCCUPANCIES = (("A2", 0), ("A3", 60), ("A2C1_CHD", 30))
NIGHTS = (1, 3)
GROUPS = (
    ("디럭스", "조식 포함", ("200", "200", "300", "300")),
    ("디럭스", "룸온리", ("170", "170", "270", "270")),
    ("스위트", "조식 포함", ("380", "380", "480", "480")),
    ("스위트", "룸온리", ("339.95", "339.95", "440", None)),
)
CLOSED_DAYS = {("디럭스", "룸온리", "2026-12-26")}
RESERVED = frozenset({("디럭스", "2026-12-25"), ("스위트", "2027-01-01")})
LIST_PRICES = {("스위트", "조식 포함", day, "A2", 1): Decimal("500.00") for day in ("2027-01-01", "2027-01-02")}
SENTENCE = "데모 호텔 연말 금·토, 디럭스랑 스위트 10% 올려줘"


def snapshot(read_at="2026-11-20T14:02:00+09:00") -> Snapshot:
    cells = {}
    for room, plan, bases in GROUPS:
        for day, base in zip(DATES, bases):
            for occupancy, extra in OCCUPANCIES:
                for nights in NIGHTS:
                    key = CellKey(room, plan, day, occupancy, nights)
                    if base is None:
                        cells[key] = MISSING
                        continue
                    sell = Decimal(base) + extra
                    sell = round_money(sell * Decimal("0.9") if nights == 3 else sell, "USD")
                    state = "closed" if (room, plan, day) in CLOSED_DAYS else "open"
                    cells[key] = CellValue(sell, LIST_PRICES.get((room, plan, day, occupancy, nights)), None, state)
    return Snapshot(HOTEL, OFFER, "USD", read_at, cells, RESERVED, frozenset((room, plan) for room, plan, _ in GROUPS),
                    hotel_id=HOTEL_ID)


def request(percent="10", **over) -> ChangeRequest:
    fields = dict(hotel=HOTEL, hotel_id=HOTEL_ID, offer=OFFER, rooms=("디럭스", "스위트"), rate_plans=("조식 포함", "룸온리"),
                  dates=DATES, operation="percent", value=Decimal(percent), sentence=SENTENCE)
    fields.update(over)
    return ChangeRequest(**fields)


def applied(snapshot: Snapshot, steps, read_at="2026-11-20T14:06:00+09:00") -> Snapshot:
    """저장 단계를 ERP 가 받은 것처럼 값을 바꾼 새 Snapshot — 묶음 저장은 적은 칸만, 셀 창은 비운 칸만 바꾼다."""
    cells = dict(snapshot.cells)
    for step in steps:
        if step.kind == "cell_edit":
            cells[step.key] = replace(cells[step.key], **{name: None for name in step.clear})
            continue
        for day in step.dates:
            for row in step.rows:
                key = CellKey(step.room, step.rate_plan, day, row.occupancy, row.nights)
                old = cells.get(key, MISSING)
                new = {name: getattr(row, name) for name in ("sell", "list", "supply") if getattr(row, name) is not None}
                cells[key] = CellValue(new.get("sell", old.sell), new.get("list", old.list), new.get("supply", old.supply),
                                       "open" if old.state == "missing" else old.state)
    return replace(snapshot, read_at=read_at, cells=cells)


def with_cells(snapshot: Snapshot, changes: dict, read_at=None) -> Snapshot:
    return replace(snapshot, read_at=read_at or snapshot.read_at, cells={**snapshot.cells, **changes})
