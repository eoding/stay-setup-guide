"""두 번째 시운전의 모양 — "그 날짜들 두 객실 조식 포함 12% 올려줘". 값과 이름은 전부 지어낸 것이다(시운전 호텔의 값이 아니다).

객실 둘 × 요금제 하나, 떨어진 네 날, 인원 조합 셋(성인 2 · 성인 2 + 아동 1 · 성인 2 + 아동 2). 첫 객실만 박수 층이 둘(1박 ·
3박 이상)이다. 1박 줄은 모두 정가와 공급 원가가 있고 12% 올리면 모두 정가를 넘는다(36칸 가운데 24칸). 3박 줄은 정가가 없다.
첫 객실 12/10 은 예약 있는 날이다. 정가도 같이 올리면 저장은 객실마다 한 번, 두 번이다.
"""

from decimal import Decimal

from price_model import CellKey, CellValue, ChangeRequest, Snapshot

HOTEL, HOTEL_ID, OFFER = "시운전 모양 호텔", "2", "기본 오퍼"
HOTEL_REF = {"id": HOTEL_ID, "name": HOTEL}
PLAN = "조식 포함"
DATES = ("2026-12-07", "2026-12-08", "2026-12-10", "2026-12-14")
CHILDREN = (("A2", "0"), ("A2C1_CHD", "15"), ("A2C2_CHD", "30"))
ROOMS = (                        # 객실 · 박수 층 · 성인 2 1박 판매가 · 정가는 판매가 + 이만큼
    ("스탠다드", (1, 3), "100.00", "10.00"),
    ("스탠다드 바다 전망", (1,), "120.00", "12.00"),
)
RESERVED = frozenset({("스탠다드", "2026-12-10")})
SENTENCE = "그 날짜들 두 객실 조식 포함 12% 올려줘"


def snapshot(read_at="2026-11-20T23:33:00+09:00") -> Snapshot:
    cells = {}
    for room, tiers, base, gap in ROOMS:
        for day in DATES:
            for occupancy, extra in CHILDREN:
                sell = Decimal(base) + Decimal(extra)
                for nights in tiers:
                    key = CellKey(room, PLAN, day, occupancy, nights)
                    if nights == 1:
                        cells[key] = CellValue(sell, sell + Decimal(gap), sell - Decimal("10.00"), "open")
                    else:
                        cells[key] = CellValue((sell * Decimal("0.9")).quantize(Decimal("0.01")), None, None, "open")
    return Snapshot(HOTEL, OFFER, "USD", read_at, cells, RESERVED, frozenset((room, PLAN) for room, *_ in ROOMS),
                    hotel_id=HOTEL_ID)


def request() -> ChangeRequest:
    return ChangeRequest(HOTEL, OFFER, (), (), DATES, "percent", Decimal("12"), sentence=SENTENCE, hotel_id=HOTEL_ID,
                         pairs=tuple((room, PLAN) for room, *_ in ROOMS))
