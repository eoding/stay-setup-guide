"""되돌리기 계산 — 그대로인 칸만 돌리고, 달라진 칸은 세 값과 까닭(장부의 나중 변경 / 도우미 밖 / 새로 생긴 칸)을 달아 둔다.

    python3 -m unittest discover -s tests
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from change_core.items import Refused  # noqa: E402
from change_core.rollback import LaterWrite, RecordedChange, RecordedItem  # noqa: E402
from price_model import ITEM_KIND, MISSING, CellKey, CellValue, Snapshot, cell_item_key, cell_name  # noqa: E402
from price_plan import plan_cell_rollback, rollback_writes, save_steps  # noqa: E402

D = Decimal
SAME, LATER, OUTSIDE, LISTED = (CellKey("R", "P", day, "A2", 1) for day in
                                ("2026-12-25", "2026-12-26", "2026-12-27", "2026-12-28"))
REF = {key: (ITEM_KIND, cell_item_key(key)) for key in (SAME, LATER, OUTSIDE, LISTED)}


def value(sell, list_price=None, state="open"):
    return CellValue(D(sell), None if list_price is None else D(list_price), None, state)


def item(key, before: CellValue, **written):
    return RecordedItem(ITEM_KIND, cell_item_key(key), cell_name(key), before.state,
                        dict(sell=before.sell, list=before.list, supply=before.supply),
                        {name: None if text is None else D(text) for name, text in written.items()})


def recorded(*items):
    return RecordedChange(7, "change", "H", "O", "USD", "12월 +10", "2026-11-20T14:02:00+09:00",
                          "2026-11-20T14:05:00+09:00", tuple(items))


def now(cells, reserved=()):
    return Snapshot("H", "O", "USD", "2026-11-25T09:00:00+09:00", cells, frozenset(reserved))


class RollbackTest(unittest.TestCase):
    def setUp(self):
        self.change = recorded(item(SAME, value("100.00"), sell="110.00"), item(LATER, value("100.00"), sell="110.00"),
                               item(OUTSIDE, value("100.00"), sell="110.00"),
                               item(LISTED, value("100.00", "105.00"), sell="110.00", list="115.00"))
        self.later = {REF[LATER]: [LaterWrite(9, "2026-11-24T10:30:00+09:00", "26일 120 으로", {"sell": D("120.00")})]}
        self.now = now({SAME: value("110.00"), LATER: value("120.00"), OUTSIDE: value("130.00"),
                        LISTED: value("110.00", "115.00", "closed")}, reserved={("R", "2026-12-25")})

    def test_only_untouched_cells_are_restored_and_kept_cells_carry_three_values_and_a_cause(self):
        plan = plan_cell_rollback(self.change, self.later, self.now)
        self.assertEqual(plan.restore_to, "2026-11-20T14:02:00+09:00")
        self.assertEqual([i.key for i in plan.restored], [REF[SAME][1], REF[LISTED][1]])
        kept = {i.key: i for i in plan.kept}
        self.assertEqual(set(kept), {REF[LATER][1], REF[OUTSIDE][1]})
        later = kept[REF[LATER][1]]
        self.assertEqual((later.recorded["sell"], later.written["sell"], later.now.fields["sell"]),
                         (D("100.00"), D("110.00"), D("120.00")))
        self.assertEqual((later.cause.change_id, later.cause.at, later.cause.sentence),
                         (9, "2026-11-24T10:30:00+09:00", "26일 120 으로"))
        self.assertTrue(kept[REF[OUTSIDE][1]].cause.outside)

    def test_a_later_change_that_was_itself_overwritten_counts_as_outside(self):
        self.now = now({**self.now.cells, LATER: value("125.00")})
        kept = {i.key: i for i in plan_cell_rollback(self.change, self.later, self.now).kept}
        self.assertTrue(kept[REF[LATER][1]].cause.outside)

    def test_restoring_writes_back_only_the_fields_the_change_wrote(self):
        writes = {w.key: (w.sell, w.list, w.clear) for w in
                  rollback_writes(plan_cell_rollback(self.change, self.later, self.now))}
        self.assertEqual(writes, {SAME: (D("100.00"), None, ()), LISTED: (D("100.00"), D("105.00"), ())})

    def test_a_field_that_was_empty_before_is_cleared_on_restore(self):
        change = recorded(item(SAME, value("100.00"), list="150.00"))
        plan = plan_cell_rollback(change, {}, now({SAME: value("100.00", "150.00")}))
        self.assertEqual([(w.key, w.sell, w.list, w.clear) for w in rollback_writes(plan)], [(SAME, None, None, ("list",))])

    def test_kept_cells_can_be_included_on_request(self):
        plan = plan_cell_rollback(self.change, self.later, self.now, include_kept=True)
        self.assertEqual(len(plan.kept), 2)
        writes = {w.key: w.sell for w in rollback_writes(plan)}
        self.assertEqual(writes, {SAME: D("100.00"), LATER: D("100.00"), OUTSIDE: D("100.00"), LISTED: D("100.00")})
        self.assertEqual([step.dates for step in save_steps(rollback_writes(plan))],
                         [("2026-12-25", "2026-12-26", "2026-12-27"), ("2026-12-28",)])

    def test_a_kept_cell_already_back_at_its_recorded_value_gets_no_save(self):
        self.now = now({**self.now.cells, OUTSIDE: value("100.00")})
        plan = plan_cell_rollback(self.change, self.later, self.now, include_kept=True)
        self.assertNotIn(REF[OUTSIDE][1], [item.key for item in plan.restored])
        self.assertNotIn(OUTSIDE, [write.key for write in rollback_writes(plan)])

    def test_a_cell_gone_since_is_kept_as_outside_and_a_cell_the_change_created_is_never_removed(self):
        created = CellKey("R", "P", "2026-12-25", "A3", 1)
        change = recorded(item(SAME, value("100.00"), sell="110.00"), item(created, MISSING, sell="200.00"))
        plan = plan_cell_rollback(change, {}, now({SAME: MISSING, created: value("200.00")}), include_kept=True)
        kept = {i.key: i for i in plan.kept}
        self.assertEqual(kept[REF[SAME][1]].now.state, "missing")
        self.assertTrue(kept[REF[SAME][1]].cause.outside)
        self.assertTrue(kept[cell_item_key(created)].cause.created)
        self.assertEqual([i.key for i in plan.restored], [REF[SAME][1]])

    def test_nothing_written_or_not_read_now_is_refused(self):
        with self.assertRaises(Refused):
            plan_cell_rollback(recorded(), {}, self.now)
        with self.assertRaises(Refused):
            plan_cell_rollback(self.change, self.later, now({SAME: value("110.00")}))


if __name__ == "__main__":
    unittest.main()
