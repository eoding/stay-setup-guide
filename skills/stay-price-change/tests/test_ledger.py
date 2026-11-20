"""장부 — 자리, 판, 상태 흐름(미리보기 → 적용 중 → 멈춤 / 적용됨), 저장마다 적기, 다시 읽어 확인, 되돌리기 재료, 지우지 않기,
그리고 가격 칸이 아닌 종류도 같은 장부에 적히는지.

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
from change_core.items import ItemState, item_key  # noqa: E402
from change_core.ledger import (  # noqa: E402
    DB_NAME, FOLDER_NAME, LEDGER_ENV, SCHEMA_VERSION, FieldWrite, Ledger, LedgerError, StepPlan, ValueRow, ledger_dir,
)
from change_core.rollback import plan_rollback  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from price_model import BulkStep, CellKey, ChangeRequest, encode_request, snapshot_reading  # noqa: E402
from price_plan import (  # noqa: E402
    plan_cell_rollback, plan_change, preview_rows, resolve, rollback_rows, rollback_writes, save_steps, snapshot_rows,
    step_plans,
)

D = Decimal


def record_preview(ledger, plan):
    request = plan.request
    return ledger.record_preview(hotel=request.hotel, offer=request.offer, currency=plan.currency,
                                 sentence=request.sentence, read_at=plan.read_at, rows=preview_rows(plan),
                                 request=encode_request(request))


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

    def test_a_ledger_from_a_newer_helper_is_refused_and_the_version_is_written(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / DB_NAME
            Ledger(path)
            db = sqlite3.connect(path)
            self.assertEqual(db.execute("SELECT value FROM meta WHERE name = 'schema_version'").fetchone()[0],
                             str(SCHEMA_VERSION))
            db.execute("UPDATE meta SET value = ? WHERE name = 'schema_version'", (str(SCHEMA_VERSION + 1),))
            db.commit()
            db.close()
            with self.assertRaises(LedgerError):
                Ledger(path)


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / DB_NAME)
        self.before = scene.snapshot()
        self.plan = plan_change(self.before, scene.request())
        writes, _ = resolve(self.plan, [Resolution("ABOVE_LIST", "raise_list")])
        self.steps = save_steps(writes)
        self.change_id = record_preview(self.ledger, self.plan)

    def tearDown(self):
        self.tmp.cleanup()

    def items(self, record):
        return {row.item_key for row in record.rows}

    def test_preview_is_recorded_with_every_field_of_every_priced_cell(self):
        record = self.ledger.change(self.change_id)
        self.assertEqual((record.kind, record.status, record.sentence), ("change", "previewed", scene.SENTENCE))
        self.assertEqual((len(self.items(record)), len(record.rows)), (90, 270))
        self.assertEqual({row.field for row in record.rows}, {"sell", "list", "supply"})
        self.assertEqual(len({row.item_key for row in record.rows if "reserved" in row.marks}), 24)
        self.assertEqual({row.verdict for row in record.rows}, {None, "ABOVE_LIST"})
        self.assertEqual(record.request, encode_request(scene.request()))

    def test_steps_are_written_as_each_finishes_and_a_failure_stops_the_change(self):
        self.ledger.begin(self.change_id, step_plans(self.steps))
        self.assertEqual(self.ledger.change(self.change_id).status, "applying")
        for index in range(1, 6):
            self.assertEqual(self.ledger.record_step(self.change_id, index, saved=True), "applying")
        self.assertEqual(self.ledger.record_step(self.change_id, 6, saved=False, note="로그인 풀림"), "stopped")
        record = self.ledger.change(self.change_id)
        self.assertEqual([s.status for s in record.steps], ["saved"] * 5 + ["failed", "pending", "pending"])
        self.assertIsNone(record.applied_at)
        self.assertEqual(len(self.ledger.recorded_change(self.change_id).items),
                         sum(len(s.dates) * len(s.rows) for s in self.steps[:5]))
        for index in range(6, 9):
            self.ledger.record_step(self.change_id, index, saved=True)
        record = self.ledger.change(self.change_id)
        self.assertEqual(record.status, "applied")
        self.assertIsNotNone(record.applied_at)

    def test_verification_marks_matching_values_and_reports_the_rest(self):
        self.ledger.begin(self.change_id, step_plans(self.steps))
        for index in range(1, 9):
            self.ledger.record_step(self.change_id, index, saved=True)
        after = scene.applied(self.before, self.steps)
        self.assertEqual(self.ledger.verify(self.change_id, snapshot_reading(after)), [])
        self.assertTrue(all(row.verified for row in self.ledger.change(self.change_id).rows if row.written))
        odd = CellKey("디럭스", "조식 포함", "2026-12-25", "A2", 1)
        changed = scene.with_cells(after, {odd: replace(after.cells[odd], sell=D("1.00"))})
        mismatches = self.ledger.verify(self.change_id, snapshot_reading(changed))
        self.assertEqual([(m.label, m.field, m.after, m.seen) for m in mismatches],
                         [("12/25 금 · 디럭스 · 조식 포함 · 성인 2 · 1박", "sell", D("220.00"), D("1.00"))])

    def test_begin_twice_with_the_same_steps_changes_nothing_and_other_steps_are_refused(self):
        self.ledger.begin(self.change_id, step_plans(self.steps))
        self.ledger.record_step(self.change_id, 1, saved=True)
        self.ledger.begin(self.change_id, step_plans(self.steps))
        self.assertEqual(self.ledger.change(self.change_id).steps[0].status, "saved")
        with self.assertRaises(LedgerError):
            self.ledger.begin(self.change_id, step_plans(self.steps[:3]))

    def test_a_step_for_a_value_the_preview_did_not_show_or_another_request_is_refused(self):
        stray = BulkStep("디럭스", "조식 포함", ("2026-12-31",), self.steps[0].rows)
        with self.assertRaises(LedgerError):
            self.ledger.begin(self.change_id, step_plans((stray,)))
        with self.assertRaises(LedgerError):
            self.ledger.begin(self.change_id, step_plans(self.steps), encode_request(scene.request("15")))
        self.assertEqual(self.ledger.change(self.change_id).status, "previewed")

    def test_nothing_is_ever_deleted(self):
        self.ledger.begin(self.change_id, step_plans(self.steps))
        db = sqlite3.connect(self.ledger.path)
        for table in ("steps", "item_values", "changes", "meta"):
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute(f"DELETE FROM {table}")
        db.close()
        self.assertEqual(len(self.ledger.change(self.change_id).steps), 8)

    def test_snapshot_is_recorded_whole_and_cannot_be_applied(self):
        snapshot_id = self.ledger.record_snapshot(hotel=scene.HOTEL, offer=scene.OFFER, currency="USD",
                                                  sentence="지금 상태만 저장", read_at=self.before.read_at,
                                                  rows=snapshot_rows(self.before))
        record = self.ledger.change(snapshot_id)
        self.assertEqual((record.kind, record.status, len(self.items(record))), ("snapshot", "applied", 96))
        with self.assertRaises(LedgerError):
            self.ledger.begin(snapshot_id, step_plans(self.steps))
        with self.assertRaises(LedgerError):
            self.ledger.recorded_change(snapshot_id)


class OtherKindTest(unittest.TestCase):
    """가격 칸이 아닌 종류(예: 부과금) — 키와 필드만 정하면 같은 장부·같은 되돌리기 계산을 쓴다."""

    def test_a_record_kind_with_named_fields_goes_through_preview_apply_and_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder) / DB_NAME)
            key = item_key({"charge": "리조트 요금", "season": "성수기"})
            change = ledger.record_preview(hotel="H", offer="", currency="USD", sentence="리조트 요금 25 로", read_at="t1",
                                           rows=[ValueRow("charge", key, "리조트 요금 · 성수기", "amount", "on", D("20"), D("25")),
                                                 ValueRow("charge", key, "리조트 요금 · 성수기", "per", "on", D("1"))])
            ledger.begin(change, [StepPlan("charge_edit", "리조트 요금", {"charge": "리조트 요금"},
                                           (FieldWrite("charge", key, "amount", D("25")),))])
            self.assertEqual(ledger.record_step(change, 1, saved=True), "applied")
            now = {("charge", key): ItemState("리조트 요금 · 성수기", "on", {"amount": D("25"), "per": D("1")})}
            self.assertEqual(ledger.verify(change, now), [])
            plan = plan_rollback(ledger.recorded_change(change), ledger.later_writes(change), now, "t2")
            self.assertEqual([(i.kind, dict(i.targets)) for i in plan.restored], [("charge", {"amount": D("20")})])


class RollbackThroughLedgerTest(unittest.TestCase):
    """변경 A 를 적용 → 한 칸은 이 장부의 변경 B 가, 한 칸은 도우미 밖에서 바꿈 → A 를 되돌리는 계산."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / DB_NAME)
        before = scene.snapshot()
        plan = plan_change(before, scene.request())
        steps = save_steps(resolve(plan, [Resolution("ABOVE_LIST", "raise_list")])[0])
        self.a = record_preview(self.ledger, plan)
        self.ledger.begin(self.a, step_plans(steps))
        for index in range(1, len(steps) + 1):
            self.ledger.record_step(self.a, index, saved=True)
        after_a = scene.applied(before, steps)
        later = ChangeRequest(scene.HOTEL, scene.OFFER, ("디럭스",), ("룸온리",), ("2027-01-02",), "set",
                              D("310"), base_occupancy="A2", sentence="1/2 디럭스 룸온리 310 으로")
        plan_b = plan_change(after_a, later)
        steps_b = save_steps(resolve(plan_b, [])[0])
        self.b = record_preview(self.ledger, plan_b)
        self.ledger.begin(self.b, step_plans(steps_b))
        self.ledger.record_step(self.b, 1, saved=True)
        now = scene.applied(after_a, steps_b)
        self.outside = CellKey("스위트", "조식 포함", "2027-01-01", "A3", 1)
        self.now = scene.with_cells(now, {self.outside: replace(now.cells[self.outside], sell=D("600.00"))},
                                    "2026-11-25T09:00:00+09:00")

    def tearDown(self):
        self.tmp.cleanup()

    def test_kept_cells_name_the_later_change_or_say_outside(self):
        rollback = plan_cell_rollback(self.ledger.recorded_change(self.a), self.ledger.later_writes(self.a), self.now)
        causes = {item.label: item.cause for item in rollback.kept}
        self.assertTrue(causes.pop("1/1 금 · 스위트 · 조식 포함 · 성인 3 · 1박").outside)
        self.assertEqual({cause.change_id for cause in causes.values()}, {self.b})
        self.assertEqual({cause.sentence for cause in causes.values()}, {"1/2 디럭스 룸온리 310 으로"})
        self.assertEqual(len(causes), 6)
        self.assertEqual(len(rollback.restored), 90 - 7)
        self.assertEqual(rollback.restore_to, "2026-11-20T14:02:00+09:00")

    def test_a_rollback_is_itself_a_recorded_change_that_reverses_the_first(self):
        rollback = plan_cell_rollback(self.ledger.recorded_change(self.a), self.ledger.later_writes(self.a), self.now)
        r = self.ledger.record_preview(hotel=rollback.hotel, offer=rollback.offer, currency=rollback.currency,
                                       sentence="방금 것 되돌려", read_at=rollback.read_at, rows=rollback_rows(rollback),
                                       reverses=self.a)
        steps = save_steps(rollback_writes(rollback))
        self.ledger.begin(r, step_plans(steps))
        for index in range(1, len(steps) + 1):
            self.ledger.record_step(r, index, saved=True)
        record = self.ledger.change(r)
        self.assertEqual((record.kind, record.status, record.reverses), ("rollback", "applied", self.a))
        listed = {row["id"]: row for row in self.ledger.list_changes()}
        self.assertEqual([listed[i]["kind"] for i in (self.a, self.b, r)], ["change", "change", "rollback"])
        self.assertEqual((listed[r]["written"], listed[self.a]["rolled_back"]), (83, 83))
        again = plan_cell_rollback(self.ledger.recorded_change(r), self.ledger.later_writes(r), scene.applied(self.now, steps))
        self.assertEqual((len(again.restored), len(again.kept)), (83, 0))


if __name__ == "__main__":
    unittest.main()
