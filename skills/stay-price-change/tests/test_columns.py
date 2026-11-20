"""U2 (결정 33A) — 긴 기간의 날짜 열. 8일이 넘는 표는 모든 줄이 똑같이 보이는 날끼리, 떨어져 있어도 열 하나를 쓴다.

열 머리는 날 수와 그 열의 날짜 구간 전부다 — 어느 날이든 꼭 한 열 머리에 나온다. 예약 있는 날은 열을 가르지 않고 머리에
적힌다. 7일까지는 날짜마다 열 하나(승인된 그림 그대로)이고, `--by-date` 는 길이와 상관없이 날짜마다 열 하나다.

    python3 -m unittest discover -s tests
"""

import html
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
from change_core.ledger import DB_NAME, Ledger, now_text  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from price_model import MISSING, CellKey, CellValue, ChangeRequest, Snapshot, encode_snapshot  # noqa: E402
from price_pages import ONE_COLUMN_PER_DATE_UP_TO, render_preview, render_prices, render_result, render_rollback  # noqa: E402
from price_plan import plan_cell_rollback, plan_change, plan_steps, preview_rows, resolve, step_plans  # noqa: E402

ROOM, PLAN = "디럭스", "조식 포함"
DECEMBER = [(date(2026, 12, 1) + timedelta(days=offset)).isoformat() for offset in range(31)]
SPECIAL = {"2026-12-24", "2026-12-31"}
NO_PRICE, BOOKED = "2026-12-15", "2026-12-10"


def december() -> Snapshot:
    """평일 100 · 금토 150 · 특별한 날 둘 200(성인 3 은 각 +30), 12/15 가격 없음, 12/10 예약 있음."""
    cells = {}
    for day in DECEMBER:
        weekend = date.fromisoformat(day).weekday() in (4, 5)
        base = Decimal("200") if day in SPECIAL else Decimal("150") if weekend else Decimal("100")
        for occupancy, extra in (("A2", 0), ("A3", 30)):
            key = CellKey(ROOM, PLAN, day, occupancy, 1)
            cells[key] = MISSING if day == NO_PRICE else CellValue(base + extra, None, None, "open")
    return Snapshot(scene.HOTEL, scene.OFFER, "USD", "2026-11-20T14:02:00+09:00", cells, frozenset({(ROOM, BOOKED)}),
                    frozenset({(ROOM, PLAN)}), hotel_id=scene.HOTEL_ID)


def heads(page: str) -> list[list[str]]:
    """표마다 날짜 열 머리의 글 — 첫 칸(인원 · 박수)은 뺀다."""
    out = []
    for table in re.findall(r"<table>(.*?)</table>", page, re.S):
        first = re.search(r"<tr>(.*?)</tr>", table, re.S).group(1)
        out.append([html.unescape(re.sub(r"<[^>]+>", " ", th)).split()
                    for th in re.findall(r"<th[^>]*>(.*?)</th>", first, re.S)][1:])
    return [[" ".join(words) for words in table] for table in out]


def dates_in(head: str, year: int = 2026) -> list[str]:
    """열 머리 "8일 · 12/4 금 ~ 12/5 토, 12/11 ~ 12/12 예약 있는 날 12/5" → 그 열의 날짜(예약 표시는 뺀다)."""
    head = head.split(" 예약 있는 날")[0].split(" 판매 마감")[0].split(" · ", 1)[1]
    days = []
    for part in head.split(", "):
        ends = [re.match(r"(\d+)/(\d+)", end.strip()) for end in part.split("~")]
        first, last = (date(year, int(m.group(1)), int(m.group(2))) for m in (ends[0], ends[-1]))
        days += [(first + timedelta(days=offset)).isoformat() for offset in range((last - first).days + 1)]
    return days


class GroupedColumnsTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = december()

    def assert_every_date_once(self, columns):
        found = [day for head in columns for day in dates_in(head)]
        self.assertEqual(sorted(found), DECEMBER, "31일 모두, 꼭 한 번씩")

    def test_a_month_of_prices_folds_into_four_columns_and_every_date_is_named_once(self):
        columns, = heads(render_prices(self.snapshot))
        self.assertEqual(columns, [
            "20일 · 12/1 화 ~ 12/3 목, 12/6 ~ 12/10, 12/13 ~ 12/14, 12/16 ~ 12/17, 12/20 ~ 12/23, 12/27 ~ 12/30 예약 있는 날 12/10",
            "8일 · 12/4 금 ~ 12/5 토, 12/11 ~ 12/12, 12/18 ~ 12/19, 12/25 ~ 12/26",
            "1일 · 12/15 화",
            "2일 · 12/24 목, 12/31 목"])
        self.assert_every_date_once(columns)

    def test_the_preview_result_and_rollback_fold_the_same_way(self):
        request = ChangeRequest(hotel=scene.HOTEL, hotel_id=scene.HOTEL_ID, offer=scene.OFFER, rooms=(ROOM,), rate_plans=(PLAN,),
                                dates=tuple(DECEMBER), operation="amount", value=Decimal("10"), sentence="12월 +10")
        plan = plan_change(self.snapshot, request)
        preview, = heads(render_preview(plan))
        self.assertEqual(len(preview), 4, preview)
        self.assert_every_date_once(preview)
        self.assertIn('<span class="was">100.00</span><span class="arrow">→</span><span class="now">110.00</span>', render_preview(plan),
                      "묶인 열에도 바뀌는 값이 그대로 있다")

        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder) / DB_NAME)
            plan = resolve(plan, [Resolution("OVER_30", "include")])
            change = ledger.record_preview(hotel=scene.HOTEL, hotel_id=scene.HOTEL_ID, offer=scene.OFFER, currency="USD",
                                           sentence=request.sentence, read_at=plan.read_at, rows=preview_rows(plan))
            steps = plan_steps(plan)
            ledger.begin(change, step_plans(steps), read_at=now_text())
            for index in range(1, len(steps) + 1):
                ledger.record_step(change, index, saved=True)
            result, = heads(render_result(ledger.change(change)))
            self.assertEqual(len(result), 3, f"장부에는 바꾼 칸만 있다 — 가격 없던 12/15 는 없다: {result}")
            self.assertEqual(sorted(day for head in result for day in dates_in(head)), sorted(set(DECEMBER) - {NO_PRICE}))
            now = scene.applied(self.snapshot, steps)
            back = plan_cell_rollback(ledger.recorded_change(change), ledger.later_writes(change), now)
            rollback, = heads(render_rollback(back, [(ROOM, BOOKED)]))
            self.assertEqual(len(rollback), 3, f"가격 없던 12/15 는 되돌릴 칸이 아니다: {rollback}")
            self.assertEqual(sorted(day for head in rollback for day in dates_in(head)), sorted(set(DECEMBER) - {NO_PRICE}))
            self.assertIn("예약 있는 날 12/10", rollback[0])

    def test_a_difference_in_any_row_or_mark_keeps_days_apart(self):
        a3 = CellKey(ROOM, PLAN, "2026-12-02", "A3", 1)
        closed = CellKey(ROOM, PLAN, "2026-12-03", "A2", 1)
        cells = {**self.snapshot.cells, a3: CellValue(Decimal("999"), None, None, "open"),
                 closed: CellValue(Decimal("100"), None, None, "closed")}
        columns, = heads(render_prices(Snapshot(**{**self.snapshot.__dict__, "cells": cells})))
        self.assertIn("1일 · 12/2 수", columns, "성인 3 줄 하나만 달라도 따로")
        self.assertIn("1일 · 12/3 목", columns, "같은 값이어도 마감 표시가 다르면 따로")
        self.assertEqual(len(columns), 6)

    def test_up_to_seven_dates_stay_one_column_per_date_and_by_date_unfolds_any_length(self):
        self.assertEqual(ONE_COLUMN_PER_DATE_UP_TO, 7)
        week = Snapshot(**{**self.snapshot.__dict__, "cells": {k: v for k, v in self.snapshot.cells.items() if k.date <= "2026-12-07"},
                           "dates": ()})
        self.assertEqual(heads(render_prices(week))[0], ["12/1 화", "12/2 수", "12/3 목", "12/4 금", "12/5 토", "12/6 일", "12/7 월"])
        eight = Snapshot(**{**self.snapshot.__dict__, "cells": {k: v for k, v in self.snapshot.cells.items() if k.date <= "2026-12-08"},
                            "dates": ()})
        self.assertEqual(len(heads(render_prices(eight))[0]), 2, "8일부터 묶는다")
        by_date, = heads(render_prices(self.snapshot, by_date=True))
        self.assertEqual(len(by_date), 31)
        self.assertIn("12/10 목 예약 있는 날", by_date)

        # 승인된 그림의 장면(날짜 넷)은 그대로 — 날짜마다 열 하나
        plan = plan_change(scene.snapshot(), scene.request())
        self.assertEqual(render_preview(plan), render_preview(plan, by_date=True))
        self.assertEqual(heads(render_preview(plan))[0], ["12/25 금 예약 있는 날", "12/26 토", "1/1 금", "1/2 토"])

    def test_the_command_renders_by_date_when_asked(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "s.json").write_text(json.dumps(encode_snapshot(self.snapshot), ensure_ascii=False), encoding="utf-8")
            env = {**os.environ, "STAY_PRICE_LEDGER_DIR": str(folder)}
            for flags, count in (((), 4), (("--by-date",), 31)):
                done = subprocess.run([sys.executable, str(SCRIPT), "render", "prices", "--snapshot", str(folder / "s.json"),
                                       "--out", str(folder / "p.html"), *flags], capture_output=True, text=True, env=env)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(len(heads((folder / "p.html").read_text(encoding="utf-8"))[0]), count, flags)


if __name__ == "__main__":
    unittest.main()
