"""시험용 — 시즌 [가격 입력] 창의 장면. 창(SeasonWindow) · 읽은 값(Snapshot) · 요청(SeasonFill)을 `fixtures/season_fill_cases.json`
의 호텔과 경우에서 만든다. 값은 전부 지어낸 것이다. unittest 가 찾지 않도록 이름이 test_ 로 시작하지 않는다.
"""

import json
from decimal import Decimal
from pathlib import Path

from price_model import CellKey, CellValue, Snapshot
from price_season import (
    CHILD_PREFIX, OtherSeason, SeasonFill, SeasonSave, SeasonWindow, WindowChild, WindowPlan, WindowRoom, date_runs,
)

HERE = Path(__file__).resolve().parent
CASES = json.loads((HERE / "fixtures" / "season_fill_cases.json").read_text(encoding="utf-8"))
HOTEL, HOTEL_ID, OFFER = "데모 호텔", "1", "기본 오퍼"
SEASON_ID, SEASON_NAME = "591", "Peak"
ROOM_IDS = {"디럭스": "301", "스위트": "302"}
PLAN_IDS = {("디럭스", "조식 포함"): "9001", ("디럭스", "룸온리"): "9002", ("스위트", "조식 포함"): "9003",
            ("스위트", "룸온리"): "9004"}
BAD_CODE = "구간 코드를 가격 셀 좌표에 실을 수 없어 이 구간은 깔리지 않습니다"


def money(text):
    return None if text is None else Decimal(text)


def children(bands) -> tuple[WindowChild, ...]:
    """경우의 아동 구간 → 창의 아동 칸 — 정액(코드가 좌표에 실리면 금액 칸, 아니면 읽기 전용 글), 비율(읽기 전용 글), 무료(칸 없음)."""
    out = []
    for band in bands or ():
        code, basis = band["code"], band["basis"]
        name = CHILD_PREFIX + code
        if basis == "free":
            continue
        if basis == "percent":
            out.append(WindowChild(code, name, "percent", Decimal(band["value"]), f"성인 1인 추가분의 {band['value']}% 로 계산됨"))
        elif len(code) > 8 or "_" in code:
            out.append(WindowChild(code, name, "none", None, BAD_CODE))
        else:
            out.append(WindowChild(code, name, "amount", None, band.get("value") or "", band.get("value") or ""))
    return tuple(out)


def window(bands=(), combos=None, dates=None, rooms=None, overwrite=True, others=(), last_fill=None) -> SeasonWindow:
    """창 하나 — 호텔(CASES["hotel"])의 객실 · 요금제, 시즌 날, 아동 칸, 허용 조합(객실 이름 → 글자, 없으면 제한 없음). `last_fill` 을
    주면 그 값(칸 이름 → 글자)으로 채워져 열린 창이다(blank 는 기본값)."""
    hotel = CASES["hotel"]
    dates = tuple(dates or hotel["season"])
    rooms = [room for room in hotel["rooms"] if rooms is None or room["name"] in rooms]
    child = children(bands)
    texts = {"price": "", "original_price": "", "net_price": "", "plan_adjust": "", "occupancy_keys": "", "occupancy_adjust": "",
             "los_prices": ""}
    blank = ([["date_selection_0", "\n".join(date_runs(dates))], ["date_selection_1", ""]] + [[name, ""] for name in texts]
             + [[item.field, item.blank] for item in child if item.kind == "amount"] + ([["overwrite", "on"]] if overwrite else []))
    form = [list(pair) for pair in blank]
    if last_fill:
        form = [[name, last_fill.get(name, value)] for name, value in form]
    order = (["date_selection_0", "date_selection_1", "price", "original_price", "net_price", "rooms", "rate_plans", "plan_adjust",
              "occupancy_keys", "occupancy_adjust", "los_prices"] + [item.field for item in child if item.kind == "amount"]
             + ["overwrite", "stale_cleanup"])
    return SeasonWindow(
        HOTEL, HOTEL_ID, OFFER, SEASON_ID, SEASON_NAME, f"가격 일괄 입력 — {OFFER} · {SEASON_NAME}", dates,
        tuple(tuple(pair) for pair in form), tuple(order),
        tuple(WindowRoom(ROOM_IDS[room["name"]], f"{OFFER} · {room['name']}", room["name"]) for room in rooms),
        tuple(WindowPlan(PLAN_IDS[(room["name"], plan["name"])], ROOM_IDS[room["name"]], f"{OFFER} · {room['name']} · {plan['name']}",
                         room["name"], plan["name"], plan["base"], plan["sort"]) for room in rooms for plan in room["plans"]),
        child, tuple(tuple(pair) for pair in blank) if last_fill else None,
        "마지막 입력값을 채웠습니다 — 2026-11-13 14:12" if last_fill else "",
        {room["name"]: (combos or {}).get(room["name"], "조합 제한 없음 — 인원 상한 적용") for room in rooms},
        tuple(OtherSeason(*item) for item in others))


def snapshot(before=(), pairs=(), dates=None, read_at="2026-11-21T10:00:00+09:00", reserved=(), currency=None) -> Snapshot:
    """읽은 값 — 경우의 before 칸(나머지는 칸 없음), 읽은 쌍 · 날, 호텔의 판매일 없는 날, 예약 있는 (객실, 날)."""
    hotel = CASES["hotel"]
    dates = tuple(dates or hotel["season"])
    cells = {}
    for item in before:
        sell, listed, net, state = item["cell"]
        cells[CellKey(item["room"], item["plan"], item["date"], item["key"], item["nights"])] = CellValue(money(sell), money(listed),
                                                                                                          money(net), state)
    pairs = frozenset(tuple(pair) for pair in pairs) | {(key.room, key.rate_plan) for key in cells}
    rooms = {room for room, _plan in pairs}
    no_sale = frozenset((room, day) for room, day in hotel["no_sale"] if room in rooms and day in dates)
    return Snapshot(HOTEL, OFFER, currency or hotel["currency"], read_at, cells, frozenset(reserved), pairs, no_sale=no_sale,
                    hotel_id=HOTEL_ID, dates=dates)


def save_of(fill: dict, **over) -> SeasonSave:
    fields = dict(pairs=tuple(tuple(pair) for pair in fill["pairs"]), price=fill.get("price", ""),
                  original_price=fill.get("original_price", ""), net_price=fill.get("net_price", ""),
                  plan_adjust=fill.get("plan_adjust", ""), occupancy_keys=fill.get("occupancy_keys", ""),
                  occupancy_adjust=fill.get("occupancy_adjust", ""), los_prices=fill.get("los_prices", ""),
                  child_extra=tuple((fill.get("child_extra") or {}).items()), overwrite=fill.get("overwrite", True),
                  dates=None if fill.get("dates") is None else tuple(fill["dates"]))
    fields.update(over)
    return SeasonSave(**fields)


def fill_of(*saves: SeasonSave, sentence="Peak 시즌 다시 채워줘", currency="USD", sheet=None) -> SeasonFill:
    return SeasonFill(HOTEL, HOTEL_ID, OFFER, SEASON_ID, SEASON_NAME, currency, sentence, tuple(saves), sheet)


def case(case_id: str) -> dict:
    return next(item for item in CASES["fills"] if item["id"] == case_id)
