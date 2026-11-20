"""장부 — 자리, 상태 흐름(미리보기 → 적용 중 → 멈춤 / 적용됨), 저장마다 적기, 다시 읽어 확인, 되돌리기 재료, 지우지 않기.

    python3 -m unittest discover -s tests
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import scene  # noqa: E402
from price_ledger import DB_NAME, FOLDER_NAME, LEDGER_ENV, Ledger, LedgerError, ledger_dir  # noqa: E402
from price_model import ChangeRequest, Resolution, SaveStep, Snapshot  # noqa: E402
from price_plan import plan_change, plan_rollback, resolve, rollback_writes, save_steps  # noqa: E402

D = Decimal


def applied(snapshot, steps, read_at="2026-11-20T14:06:00+09:00"):
    """저장 단계를 ERP 가 받은 것처럼 값을 바꾼 새 Snapshot."""
    cells = dict(snapshot.cells)
    for step in steps:
        for day in step.dates:
            for row in step.rows:
                key = next(k for k in cells if (k.room, k.rate_plan, k.date, k.occupancy, k.nights)
                           == (step.room, step.rate_plan, day, row.occupancy, row.nights))
                old = cells[key]
                cells[key] = replace(old, sell=row.sell, list_price=row.list_price or old.list_price)
    return Snapshot(snapshot.hotel, snapshot.offer, snapshot.currency, read_at, cells, snapshot.reserved)


class LocationTest(unittest.TestCase):
    def test_default_is_one_fixed_folder_under_documents_and_the_variable_overrides_it(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"HOME": home}):
            os.environ.pop(LEDGER_ENV, None)
            self.assertEqual(ledger_dir(), Path(home) / "Documents" / FOLDER_NAME)
            self.assertTrue((Path(home) / "Documents" / FOLDER_NAME).is_dir())
            other = Path(home) / "elsewhere"
            with mock.patch.dict(os.environ, {LEDGER_ENV: str(other)}):
                self.assertEqual(Ledger().path, other / DB_NAME)
                self.assertTrue((other / DB_NAME).is_file())


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / DB_NAME)
        self.before = scene.snapshot()
        self.plan = plan_change(self.before, scene.request())
        writes, _ = resolve(self.plan, [Resolution("ABOVE_LIST", "raise_list")])
        self.steps = save_steps(writes)
        self.change_id = self.ledger.record_preview(self.plan)

    def tearDown(self):
        self.tmp.cleanup()

    def test_preview_is_recorded_with_every_priced_cell_and_its_before_value(self):
        record = self.ledger.change(self.change_id)
        self.assertEqual((record.kind, record.status, record.sentence), ("change", "previewed", scene.SENTENCE))
        self.assertEqual(len(record.cells), 90)
        self.assertEqual(sum(cell.reserved for cell in record.cells), 24)
        self.assertEqual({cell.verdict for cell in record.cells}, {None, "ABOVE_LIST"})

    def test_steps_are_written_as_each_finishes_and_a_failure_stops_the_change(self):
        self.ledger.begin(self.change_id, self.steps)
        self.assertEqual(self.ledger.change(self.change_id).status, "applying")
        for index in range(1, 6):
            self.assertEqual(self.ledger.record_step(self.change_id, index, saved=True), "applying")
        self.assertEqual(self.ledger.record_step(self.change_id, 6, saved=False, note="로그인 풀림"), "stopped")
        record = self.ledger.change(self.change_id)
        self.assertEqual([s.status for s in record.steps], ["saved"] * 5 + ["failed", "pending", "pending"])
        self.assertIsNone(record.applied_at)
        written = self.ledger.recorded_change(self.change_id).cells
        self.assertEqual(len(written), sum(len(s.dates) * len(s.rows) for s in self.steps[:5]))
        for index in range(6, 9):
            self.ledger.record_step(self.change_id, index, saved=True)
        record = self.ledger.change(self.change_id)
        self.assertEqual(record.status, "applied")
        self.assertIsNotNone(record.applied_at)

    def test_verification_marks_matching_cells_and_reports_the_rest(self):
        self.ledger.begin(self.change_id, self.steps)
        for index in range(1, 9):
            self.ledger.record_step(self.change_id, index, saved=True)
        after = applied(self.before, self.steps)
        self.assertEqual(self.ledger.verify(self.change_id, after), [])
        self.assertTrue(all(cell.verified for cell in self.ledger.change(self.change_id).cells))
        key = self.steps[0].rows[0]
        odd = next(k for k in after.cells if (k.room, k.rate_plan, k.date, k.occupancy, k.nights)
                   == (self.steps[0].room, self.steps[0].rate_plan, self.steps[0].dates[0], key.occupancy, key.nights))
        changed = Snapshot(after.hotel, after.offer, after.currency, after.read_at,
                           {**after.cells, odd: replace(after.cells[odd], sell=D("1.00"))}, after.reserved)
        mismatches = self.ledger.verify(self.change_id, changed)
        self.assertEqual([(k, w.sell, seen.sell) for k, w, seen in mismatches], [(odd, key.sell, D("1.00"))])
        cell = next(c for c in self.ledger.change(self.change_id).cells if c.key == odd)
        self.assertEqual((cell.verified, cell.seen.sell), (False, D("1.00")))

    def test_begin_twice_with_the_same_steps_changes_nothing_and_other_steps_are_refused(self):
        self.ledger.begin(self.change_id, self.steps)
        self.ledger.record_step(self.change_id, 1, saved=True)
        self.ledger.begin(self.change_id, self.steps)
        self.assertEqual(self.ledger.change(self.change_id).steps[0].status, "saved")
        with self.assertRaises(LedgerError):
            self.ledger.begin(self.change_id, self.steps[:3])

    def test_a_step_for_a_cell_the_preview_did_not_show_is_refused(self):
        stray = SaveStep("디럭스", "조식 포함", ("2026-12-31",), self.steps[0].rows)
        with self.assertRaises(LedgerError):
            self.ledger.begin(self.change_id, (stray,))
        self.assertEqual(self.ledger.change(self.change_id).status, "previewed")

    def test_nothing_is_ever_deleted(self):
        self.ledger.begin(self.change_id, self.steps)
        db = sqlite3.connect(self.ledger.path)
        for table in ("steps", "cells", "changes"):
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute(f"DELETE FROM {table}")
        db.close()
        self.assertEqual(len(self.ledger.change(self.change_id).steps), 8)

    def test_snapshot_is_recorded_whole_and_cannot_be_applied(self):
        snapshot_id = self.ledger.record_snapshot(self.before, "지금 상태만 저장")
        record = self.ledger.change(snapshot_id)
        self.assertEqual((record.kind, record.status, len(record.cells)), ("snapshot", "applied", 96))
        with self.assertRaises(LedgerError):
            self.ledger.begin(snapshot_id, self.steps)
        with self.assertRaises(LedgerError):
            self.ledger.recorded_change(snapshot_id)


class RollbackThroughLedgerTest(unittest.TestCase):
    """변경 A 를 적용 → 한 칸은 이 장부의 변경 B 가, 한 칸은 도우미 밖에서 바꿈 → A 를 되돌리는 계산."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / DB_NAME)
        before = scene.snapshot()
        plan = plan_change(before, scene.request())
        writes, _ = resolve(plan, [Resolution("ABOVE_LIST", "raise_list")])
        steps = save_steps(writes)
        self.a = self.ledger.record_preview(plan)
        self.ledger.begin(self.a, steps)
        for index in range(1, len(steps) + 1):
            self.ledger.record_step(self.a, index, saved=True)
        after_a = applied(before, steps)
        later = ChangeRequest(scene.HOTEL, scene.OFFER, ("디럭스",), ("룸온리",), ("2027-01-02",), "set",
                              D("310"), base_occupancy="A2", sentence="1/2 디럭스 룸온리 310 으로")
        plan_b = plan_change(after_a, later)
        steps_b = save_steps(resolve(plan_b, [])[0])
        self.b = self.ledger.record_preview(plan_b)
        self.ledger.begin(self.b, steps_b)
        self.ledger.record_step(self.b, 1, saved=True)
        now = applied(after_a, steps_b)
        self.outside = next(k for k in now.cells if (k.room, k.rate_plan, k.date, k.occupancy, k.nights)
                            == ("스위트", "조식 포함", "2027-01-01", "A3", 1))
        self.now = Snapshot(now.hotel, now.offer, now.currency, "2026-11-25T09:00:00+09:00",
                            {**now.cells, self.outside: replace(now.cells[self.outside], sell=D("600.00"))}, now.reserved)

    def tearDown(self):
        self.tmp.cleanup()

    def test_kept_cells_name_the_later_change_or_say_outside(self):
        rollback = plan_rollback(self.ledger.recorded_change(self.a), self.ledger.later_writes(self.a), self.now)
        causes = {(c.key.room, c.key.rate_plan, c.key.date, c.key.occupancy, c.key.nights): c.cause for c in rollback.kept}
        self.assertTrue(causes.pop(("스위트", "조식 포함", "2027-01-01", "A3", 1)).outside)
        self.assertEqual({cause.change_id for cause in causes.values()}, {self.b})
        self.assertEqual({cause.sentence for cause in causes.values()}, {"1/2 디럭스 룸온리 310 으로"})
        self.assertEqual(len(causes), 6)
        self.assertEqual(len(rollback.restored), 90 - 7)
        self.assertEqual(rollback.restore_to, "2026-11-20T14:02:00+09:00")

    def test_a_rollback_is_itself_a_recorded_change_that_reverses_the_first(self):
        rollback = plan_rollback(self.ledger.recorded_change(self.a), self.ledger.later_writes(self.a), self.now)
        r = self.ledger.record_rollback_preview(rollback, "방금 것 되돌려")
        steps = save_steps(rollback_writes(rollback))
        self.ledger.begin(r, steps)
        for index in range(1, len(steps) + 1):
            self.ledger.record_step(r, index, saved=True)
        record = self.ledger.change(r)
        self.assertEqual((record.kind, record.status, record.reverses), ("rollback", "applied", self.a))
        listed = {row["id"]: row for row in self.ledger.list_changes()}
        self.assertEqual([listed[i]["kind"] for i in (self.a, self.b, r)], ["change", "change", "rollback"])
        self.assertEqual(listed[r]["written"], 83)
        again = plan_rollback(self.ledger.recorded_change(r), self.ledger.later_writes(r), applied(self.now, steps))
        self.assertEqual((len(again.restored), len(again.kept)), (83, 0))


if __name__ == "__main__":
    unittest.main()
