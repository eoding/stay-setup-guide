"""B12 판매일 없는 날 — 가격 수정 창은 그런 날이 끼면 기간을 통째로 거절하므로 읽지 않고, 「판매일 없음」(「가격 없음」과
다르다)으로 알리고, 계산은 그 날을 그 까닭으로 건너뛴다.

    python3 -m unittest discover -s tests
"""

import sys
import unittest
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from browser_replies import reply  # noqa: E402
from erp_read import PairRead, ParseError, build_snapshot, parse_price_page  # noqa: E402
from price_browser import BrowserError, pair_reads  # noqa: E402
from price_model import (  # noqa: E402
    CellKey, ChangeRequest, Target, TargetTable, decode_plan, decode_snapshot, encode_plan, encode_snapshot,
)
from price_pages import render_preview, render_prices  # noqa: E402
from price_plan import plan_change, plan_targets  # noqa: E402

PRICE = (HERE / "fixtures" / "erp" / "price-runs-closed-absent-list.html").read_text(encoding="utf-8")   # 12/24 ~ 12/31
PAGE = parse_price_page(PRICE)
CLOSED_DAYS = ("2027-01-01", "2027-01-02")
ASKED = {"offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-24", "to": "2027-01-02",
         "weekdays": list("월화수목금토일")}


def snapshot():
    return build_snapshot("데모 호텔", "2026-11-20T19:00:00+09:00", [PairRead("샘플 오퍼", "디럭스", "조식 포함", PAGE, CLOSED_DAYS)])


class NoSaleTest(unittest.TestCase):
    def test_the_page_answer_carries_days_with_no_sale_day_and_must_cover_the_question(self):
        read, = pair_reads(reply("readPair", ASKED, {"fragment": PRICE, "noSale": list(CLOSED_DAYS)}))
        self.assertEqual((read.no_sale, sorted(read.page.days)[0]), (CLOSED_DAYS, "2026-12-24"))
        with self.assertRaisesRegex(BrowserError, "물은 날과 맞지 않습니다"):
            pair_reads(reply("readPair", ASKED, {"fragment": PRICE, "noSale": ["2027-01-01"]}))
        with self.assertRaisesRegex(BrowserError, "물은 날과 맞지 않습니다"):
            pair_reads(reply("readPair", ASKED, {"fragment": PRICE, "noSale": [*CLOSED_DAYS, "2026-12-24"]}))
        closed = dict(ASKED, **{"from": "2027-01-01", "to": "2027-01-02"})
        nothing, = pair_reads(reply("readPair", closed, {"fragment": None, "noSale": list(CLOSED_DAYS)}))
        self.assertIsNone(nothing.page)

    def test_the_snapshot_keeps_them_apart_from_days_without_a_price(self):
        snap = decode_snapshot(encode_snapshot(snapshot()))
        self.assertEqual(snap.no_sale, {("디럭스", day) for day in CLOSED_DAYS})
        self.assertEqual(snap.cells[CellKey("디럭스", "조식 포함", "2026-12-28", "A2", 1)].state, "missing", "가격 없음은 칸이 있다")
        self.assertFalse(any(key.date in CLOSED_DAYS for key in snap.cells), "판매일 없음은 칸이 없다")
        page = render_prices(snap)
        self.assertIn("판매일 없는 날 (객실 · 날짜)", page)
        self.assertIn("판매일 없음(판매일이 열리지 않은 날", page)

    def test_a_read_with_no_open_day_counts_as_read_but_not_alone(self):
        only = PairRead("샘플 오퍼", "스위트", "조식 포함", None, CLOSED_DAYS)
        snap = build_snapshot("H", "t", [PairRead.of("디럭스", PAGE), only])
        self.assertIn(("스위트", "조식 포함"), snap.pairs)
        self.assertIn(("스위트", "2027-01-01"), snap.no_sale)
        with self.assertRaisesRegex(ParseError, "모두 판매일 없음"):
            build_snapshot("H", "t", [only])
        with self.assertRaisesRegex(ParseError, "판매일 없음이면서 읽은 화면에도"):
            PairRead("샘플 오퍼", "디럭스", "조식 포함", PAGE, ("2026-12-24",))

    def test_planning_lists_them_as_skipped_with_that_reason_and_changes_the_open_days(self):
        request = ChangeRequest(hotel="데모 호텔", offer="샘플 오퍼", rooms=("디럭스",), rate_plans=("조식 포함",),
                                dates=("2026-12-24", "2027-01-01", "2027-01-02"), operation="amount", value=D("5"))
        plan = plan_change(snapshot(), request)
        self.assertEqual(plan.no_sale, tuple(("디럭스", "조식 포함", day) for day in CLOSED_DAYS))
        self.assertEqual({change.key.date for change in plan.changes}, {"2026-12-24"})
        self.assertEqual(decode_plan(encode_plan(plan)).no_sale, plan.no_sale)
        self.assertIn("판매일 없음(판매일이 열리지 않아 바꿀 수 없는 날", render_preview(plan, None, []))
        self.assertIn("1/1 금 ~ 1/2 토", render_preview(plan, None, []))

    def test_target_tables_skip_them_too(self):
        targets = TargetTable("데모 호텔", "샘플 오퍼", (
            Target(CellKey("디럭스", "조식 포함", "2026-12-24", "A2", 1), (("sell", D("150.00")),)),
            Target(CellKey("디럭스", "조식 포함", "2027-01-01", "A2", 1), (("sell", D("150.00")),))))
        plan = plan_targets(snapshot(), targets)
        self.assertEqual(plan.no_sale, (("디럭스", "조식 포함", "2027-01-01"),))
        self.assertEqual([change.key.date for change in plan.changes], ["2026-12-24"])


if __name__ == "__main__":
    unittest.main()
