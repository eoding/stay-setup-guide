"""변경의 일부만 되돌리기 — 객실·요금제·날짜 범위·인원 조합으로 고르고, 장부는 값마다 어느 되돌리기가 되돌렸는지 적는다.
나중에 "나머지" 를 되돌리면 아직 도우미 것인 칸만 건드린다. 변경 전체 되돌리기는 고르지 않은 같은 길이다.

    python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import scene  # noqa: E402
from change_core.items import Refused  # noqa: E402
from change_core.ledger import DB_NAME, Ledger  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from price_model import encode_request, encode_snapshot, key_of_item, snapshot_reading  # noqa: E402
from price_pages import render_result, render_rollback  # noqa: E402
from price_plan import (  # noqa: E402
    cell_filter, plan_cell_rollback, plan_change, preview_rows, resolve, rollback_rows, rollback_writes, save_steps,
    step_plans,
)
from test_pages import visible  # noqa: E402


class PartialRollbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / DB_NAME)
        plan = plan_change(scene.snapshot(), scene.request())
        steps = save_steps(resolve(plan, [Resolution("ABOVE_LIST", "raise_list")])[0])
        self.change = self.ledger.record_preview(hotel=scene.HOTEL, offer=scene.OFFER, currency="USD",
                                                 sentence=scene.SENTENCE, read_at=plan.read_at, rows=preview_rows(plan),
                                                 request=encode_request(plan.request))
        self.ledger.begin(self.change, step_plans(steps))
        for index in range(1, len(steps) + 1):
            self.ledger.record_step(self.change, index, saved=True)
        self.now = scene.applied(scene.snapshot(), steps, "2026-11-25T09:00:00+09:00")

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, **choose):
        select, scope = cell_filter(**choose)
        return plan_cell_rollback(self.ledger.recorded_change(self.change), self.ledger.later_writes(self.change),
                                  self.now, select=select), scope

    def apply(self, rollback, saved=None):
        rid = self.ledger.record_preview(hotel=rollback.hotel, offer=rollback.offer, currency=rollback.currency,
                                         sentence="일부 되돌려", read_at=rollback.read_at, rows=rollback_rows(rollback),
                                         reverses=self.change)
        steps = save_steps(rollback_writes(rollback))
        self.ledger.begin(rid, step_plans(steps))
        for index in range(1, (len(steps) if saved is None else saved) + 1):
            self.ledger.record_step(rid, index, saved=True)
        self.now = scene.applied(self.now, steps[:saved] if saved is not None else steps)
        return rid, steps

    def test_choosing_by_room_rate_plan_date_range_or_occupancy(self):
        by_room, scope = self.plan(rooms=["디럭스"])
        self.assertEqual((len(by_room.restored), scope), (48, "디럭스"))
        by_plan, _ = self.plan(rate_plans=["룸온리"])
        self.assertEqual(len(by_plan.restored), 42)
        by_dates, scope = self.plan(date_from="2027-01-01", date_to="2027-01-31")
        self.assertEqual((len(by_dates.restored), scope), (42, "1/1 금 ~ 1/31 일"))
        by_occupancy, _ = self.plan(rooms=["스위트"], occupancies=["A2C1_CHD"])
        self.assertEqual({key_of_item(item.key).occupancy for item in by_occupancy.restored}, {"A2C1_CHD"})
        self.assertEqual(len(by_occupancy.restored), 14)
        with self.assertRaises(Refused):
            self.plan(rooms=["없는 객실"])

    def test_the_ledger_marks_what_was_rolled_back_and_the_rest_touches_only_what_is_still_ours(self):
        first, _ = self.plan(rooms=["디럭스"])
        rid, _ = self.apply(first)
        record = self.ledger.change(self.change)
        undone = {row.item_key for row in record.rows if row.rolled_back_by == rid}
        self.assertEqual(len(undone), 48)
        self.assertEqual({key_of_item(key).room for key in undone}, {"디럭스"})
        self.assertEqual(len(self.ledger.recorded_change(self.change).items), 42)
        rest, scope = self.plan()
        self.assertEqual(scope, "")
        self.assertEqual({key_of_item(item.key).room for item in rest.restored}, {"스위트"})
        self.assertEqual((len(rest.restored), len(rest.kept)), (42, 0))
        second, _ = self.apply(rest)
        self.assertEqual({row.rolled_back_by for row in self.ledger.change(self.change).rows if row.action},
                         {rid, second})
        listed = {row["id"]: row for row in self.ledger.list_changes()}
        self.assertEqual(listed[self.change]["rolled_back"], 90)
        with self.assertRaises(Refused):
            self.plan()
        self.assertEqual(self.now.cells, scene.snapshot().cells)

    def test_a_rollback_stopped_half_way_leaves_the_unsaved_cells_ours(self):
        whole, _ = self.plan()
        rid, steps = self.apply(whole, saved=3)
        still = self.ledger.recorded_change(self.change).items
        self.assertEqual(len(still), 90 - sum(len(s.dates) * len(s.rows) for s in steps[:3]))
        self.assertEqual(self.ledger.change(rid).status, "applying")

    def test_pages_show_the_range_and_the_rolled_back_cells(self):
        first, scope = self.plan(rooms=["디럭스"], date_from="2026-12-25", date_to="2026-12-26")
        text = visible(render_rollback(first, self.now.reserved, scope))
        self.assertIn("되돌리는 범위: 디럭스 / 12/25 금 ~ 12/26 토", text)
        self.assertIn("24 되돌리는 칸", text)
        rid, _ = self.apply(first)
        self.ledger.verify(self.change, snapshot_reading(self.now))
        text = visible(render_result(self.ledger.change(self.change)))
        self.assertIn(f"200.00 → 220.00 되돌림 · 장부 {rid}번", text)
        self.assertIn("적용했고, 다시 읽어 확인했습니다. 66칸 모두 넣은 값과 같습니다.", text)
        self.assertIn(f"이 변경의 24칸은 뒤에 되돌렸습니다(장부 {rid}번).", text)
        self.assertIn("300.00 → 330.00 확인", text)

    def test_the_command_takes_the_same_choices(self):
        folder = Path(self.tmp.name)
        (folder / "now.json").write_text(json.dumps(encode_snapshot(self.now), ensure_ascii=False), encoding="utf-8")
        done = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "price_change.py"), "rollback",
                               "--change", str(self.change), "--snapshot", str(folder / "now.json"), "--room", "스위트",
                               "--rate-plan", "룸온리", "--from", "2027-01-01"],
                              capture_output=True, text=True, env={**os.environ, "STAY_PRICE_LEDGER_DIR": str(folder)})
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual((result["scope"], len(result["rollback"]["restored"]), len(result["steps"])),
                         ("스위트 / 룸온리 / 1/1 금 ~ 끝", 6, 1))


if __name__ == "__main__":
    unittest.main()
