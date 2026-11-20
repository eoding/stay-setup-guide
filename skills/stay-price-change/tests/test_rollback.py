"""되돌리기 계산 — 그대로인 칸만 돌리고, 달라진 칸은 세 값과 까닭(장부의 나중 변경 / 도우미 밖)을 달아 둔다.

    python3 -m unittest discover -s tests
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from price_model import (  # noqa: E402
    MISSING, CellKey, CellValue, CellWrite, LaterWrite, RecordedCell, RecordedChange, Snapshot,
)
from price_plan import PlanError, plan_rollback, rollback_writes, save_steps  # noqa: E402

D = Decimal
SAME, LATER, OUTSIDE, LISTED = (CellKey("R", "P", day, "A2", 1) for day in
                                ("2026-12-25", "2026-12-26", "2026-12-27", "2026-12-28"))


def value(sell, list_price=None, state="open"):
    return CellValue(D(sell), None if list_price is None else D(list_price), None, state)


def recorded(*cells):
    return RecordedChange(7, "change", "H", "O", "USD", "12월 +10", "2026-11-20T14:02:00+09:00",
                          "2026-11-20T14:05:00+09:00", tuple(cells))


def now(cells, reserved=()):
    return Snapshot("H", "O", "USD", "2026-11-25T09:00:00+09:00", cells, frozenset(reserved))


class RollbackTest(unittest.TestCase):
    def setUp(self):
        self.change = recorded(
            RecordedCell(SAME, value("100.00"), CellWrite(SAME, D("110.00"))),
            RecordedCell(LATER, value("100.00"), CellWrite(LATER, D("110.00"))),
            RecordedCell(OUTSIDE, value("100.00"), CellWrite(OUTSIDE, D("110.00"))),
            RecordedCell(LISTED, value("100.00", "105.00"), CellWrite(LISTED, D("110.00"), D("115.00"))),
        )
        self.later = {LATER: [LaterWrite(9, "2026-11-24T10:30:00+09:00", "26일 120 으로", CellWrite(LATER, D("120.00")))]}
        self.now = now({SAME: value("110.00"), LATER: value("120.00"), OUTSIDE: value("130.00"),
                        LISTED: value("110.00", "115.00", "closed")}, reserved={("R", "2026-12-25")})

    def test_only_untouched_cells_are_restored_and_kept_cells_carry_three_values_and_a_cause(self):
        plan = plan_rollback(self.change, self.later, self.now)
        self.assertEqual(plan.restore_to, "2026-11-20T14:02:00+09:00")
        self.assertEqual([c.key for c in plan.restored], [SAME, LISTED])
        self.assertEqual(plan.restored[0].marks, ("reserved",))
        kept = {cell.key: cell for cell in plan.kept}
        self.assertEqual(set(kept), {LATER, OUTSIDE})
        self.assertEqual((kept[LATER].recorded.sell, kept[LATER].written.sell, kept[LATER].now.sell),
                         (D("100.00"), D("110.00"), D("120.00")))
        self.assertEqual((kept[LATER].cause.change_id, kept[LATER].cause.at, kept[LATER].cause.sentence),
                         (9, "2026-11-24T10:30:00+09:00", "26일 120 으로"))
        self.assertTrue(kept[OUTSIDE].cause.outside)

    def test_a_later_change_that_was_itself_overwritten_counts_as_outside(self):
        self.now = now({**self.now.cells, LATER: value("125.00")})
        kept = {cell.key: cell for cell in plan_rollback(self.change, self.later, self.now).kept}
        self.assertTrue(kept[LATER].cause.outside)

    def test_restoring_writes_back_the_recorded_price_and_a_list_price_we_had_raised(self):
        writes = {w.key: (w.sell, w.list_price) for w in rollback_writes(plan_rollback(self.change, self.later, self.now))}
        self.assertEqual(writes, {SAME: (D("100.00"), None), LISTED: (D("100.00"), D("105.00"))})

    def test_kept_cells_can_be_included_on_request(self):
        plan = plan_rollback(self.change, self.later, self.now, include_kept=True)
        self.assertEqual(len(plan.kept), 2)
        writes = {w.key: w.sell for w in rollback_writes(plan)}
        self.assertEqual(writes, {SAME: D("100.00"), LATER: D("100.00"), OUTSIDE: D("100.00"), LISTED: D("100.00")})
        self.assertEqual([step.dates for step in save_steps(rollback_writes(plan))],
                         [("2026-12-25", "2026-12-26", "2026-12-27"), ("2026-12-28",)])

    def test_a_cell_gone_since_is_kept_as_outside(self):
        self.now = now({**self.now.cells, SAME: MISSING})
        kept = {cell.key: cell for cell in plan_rollback(self.change, self.later, self.now).kept}
        self.assertEqual(kept[SAME].now.state, "missing")
        self.assertTrue(kept[SAME].cause.outside)

    def test_nothing_written_or_not_read_now_is_refused(self):
        with self.assertRaises(PlanError):
            plan_rollback(recorded(), {}, self.now)
        with self.assertRaises(PlanError):
            plan_rollback(self.change, self.later, now({SAME: value("110.00")}))


if __name__ == "__main__":
    unittest.main()
