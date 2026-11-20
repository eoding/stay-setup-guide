"""새 요금표 장면 — 값은 전부 지어낸 것이다.

요금표: 객실 2(디럭스 · 스위트, 둘 다 조식 포함) × 시즌 2(비수기 1/4~1/10 · 성수기 1/11~1/17, 2027) × 주중(일~목) · 주말(금·토)
= 8줄. 줄마다 성인 2 · 1박은 숫자, 성인 3 은 성인 2 +60, 성인 2 + 아동 1 은 성인 2 +30, 성인 2 · 3박 이상은 1박 -10%.

읽은 값(USD): 디럭스 비수기는 이미 요금표와 같고, 디럭스 성수기와 스위트는 옛 값(성인 2 가 낮고 성인 3 +50 · 아동 +25 · 3박 -10%).
스위트에는 요금표가 말하지 않는 성인 1 · 1박 줄이 있고, 스위트 1/13 은 판매일이 없다. 호텔(look)에는 요금표에 없는 패밀리도 있다.
"""

from datetime import date, timedelta
from decimal import Decimal

from change_core.money import round_money
from price_model import CellKey, CellValue, Snapshot
from scene import HOTEL, HOTEL_ID, HOTEL_REF, OFFER

FIRST, LAST = date(2027, 1, 4), date(2027, 1, 17)
DAYS = tuple((FIRST + timedelta(days=n)).isoformat() for n in range((LAST - FIRST).days + 1))
WEEKEND, WEEKDAY = ["금", "토"], ["일", "월", "화", "수", "목"]
SEASONS = (("비수기", "2027-01-04", "2027-01-10"), ("성수기", "2027-01-11", "2027-01-17"))
# 요금표의 성인 2 · 1박 — 객실 → 시즌 → (주중, 주말)
SHEET_A2 = {"디럭스": {"비수기": ("200", "240"), "성수기": ("260", "300")},
            "스위트": {"비수기": ("380", "420"), "성수기": ("450", "500")}}
# 읽은 값의 성인 2 · 1박 — 디럭스 비수기는 요금표와 같다
READ_A2 = {"디럭스": {"비수기": ("200", "240"), "성수기": ("250", "290")},
           "스위트": {"비수기": ("360", "400"), "성수기": ("430", "480")}}
NO_SALE = ("스위트", "2027-01-13")
PLAN = "조식 포함"


def rows(a2: str) -> list[dict]:
    return [{"occupancy": "A2", "nights": 1, "sell": a2},
            {"occupancy": "A3", "nights": 1, "sell": {"from": {"occupancy": "A2"}, "add": "60"}},
            {"occupancy": "A2C1_CHD", "nights": 1, "sell": {"from": {"occupancy": "A2"}, "add": "30"}},
            {"occupancy": "A2", "nights": 3, "sell": {"from": {"nights": 1}, "percent": "-10"}}]


def sheet_data(**over) -> dict:
    lines = [{"room": room, "rate_plan": PLAN, "season": season,
              "periods": [{"from": first, "to": last, "weekdays": days}], "rows": rows(prices[season][index])}
             for room, prices in SHEET_A2.items() for season, first, last in SEASONS
             for index, days in enumerate((WEEKDAY, WEEKEND))]
    return dict({"kind": "sheet", "hotel": HOTEL_REF, "offer": OFFER, "currency": "USD",
                 "sentence": "1월 새 요금표로 디럭스 · 스위트 날짜별 가격 맞춰줘", "lines": lines}, **over)


def look_data() -> dict:
    return {"login": False, "hotel": HOTEL_REF, "offer": OFFER, "offers": [OFFER],
            "pairs": [{"room": room, "rate_plan": PLAN} for room in ("디럭스", "스위트", "패밀리")]}


def season_of(day: str) -> str:
    return "비수기" if day <= "2027-01-10" else "성수기"


def weekend(day: str) -> bool:
    return date.fromisoformat(day).weekday() in (4, 5)


def reading(read_at="2026-11-20T14:02:00+09:00") -> Snapshot:
    cells = {}
    for room, prices in READ_A2.items():
        for day in DAYS:
            if (room, day) == NO_SALE:
                continue
            a2 = Decimal(prices[season_of(day)][weekend(day)])
            adult, child = (60, 30) if (room, season_of(day)) == ("디럭스", "비수기") else (50, 25)
            values = {("A2", 1): a2, ("A3", 1): a2 + adult, ("A2C1_CHD", 1): a2 + child,
                      ("A2", 3): round_money(a2 * Decimal("0.9"), "USD")}
            if room == "스위트":
                values[("A1", 1)] = a2 - 20
            for (occupancy, nights), sell in values.items():
                cells[CellKey(room, PLAN, day, occupancy, nights)] = CellValue(round_money(sell, "USD"), None, None, "open")
    return Snapshot(HOTEL, OFFER, "USD", read_at, cells, frozenset(), frozenset((room, PLAN) for room in READ_A2),
                    no_sale=frozenset({NO_SALE}), hotel_id=HOTEL_ID, dates=DAYS)
