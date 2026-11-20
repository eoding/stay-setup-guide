"""저장해 둔 상태로 되돌리기(R8) — 지금 상태 저장으로 적은 값으로 그 범위를 맞추고, 같은 미리보기로 보이고, 변경으로 적혀 다시 되돌릴 수
있다. 그 뒤에 새로 생긴 칸은 지울 수 없는 칸으로 남는다.

    python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import scene  # noqa: E402
from change_core.items import Refused  # noqa: E402
from change_core.ledger import DB_NAME, Ledger, LedgerError  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from price_model import (  # noqa: E402
    CellKey, Snapshot, Target, TargetTable, cell_item_key, encode_request, encode_snapshot, snapshot_reading,
)
from price_pages import render_preview, render_rollback  # noqa: E402
from price_plan import (  # noqa: E402
    cell_filter, plan_cell_restore, plan_cell_rollback, plan_change, plan_targets, preview_rows, resolve, rollback_rows,
    rollback_writes, save_steps, snapshot_rows, step_plans,
)
from test_pages import visible  # noqa: E402

D = Decimal
CREATED = CellKey("스위트", "룸온리", "2027-01-02", "A2", 1)


class RestoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / DB_NAME)
        self.saved_state = scene.snapshot()
        self.saved = self.ledger.record_snapshot(hotel=scene.HOTEL, offer=scene.OFFER, currency="USD",
                                                 sentence="연말 가격 바꾸기 전에 저장", read_at=self.saved_state.read_at,
                                                 rows=snapshot_rows(self.saved_state))
        now = self.apply(plan_change(self.saved_state, scene.request()), self.saved_state,
                         [Resolution("ABOVE_LIST", "raise_list")])
        self.now = self.apply(plan_targets(now, TargetTable(scene.HOTEL, scene.OFFER,
                                                            (Target(CREATED, (("sell", D("450.00")),)),))), now)

    def tearDown(self):
        self.tmp.cleanup()

    def apply(self, plan, current, resolutions=()):
        change = self.ledger.record_preview(hotel=scene.HOTEL, offer=scene.OFFER, currency="USD",
                                            sentence=plan.request.sentence, read_at=plan.read_at, rows=preview_rows(plan),
                                            request=encode_request(plan.request))
        steps = save_steps(resolve(plan, resolutions)[0])
        self.ledger.begin(change, step_plans(steps))
        for index in range(1, len(steps) + 1):
            self.ledger.record_step(change, index, saved=True)
        return scene.applied(current, steps, "2026-11-26T09:00:00+09:00")

    def test_restore_brings_every_cell_of_the_range_back_and_leaves_cells_created_since(self):
        plan = plan_cell_restore(self.ledger.recorded_snapshot(self.saved), self.now)
        self.assertEqual((plan.mode, plan.reverses, plan.restore_to), ("restore", self.saved, self.saved_state.read_at))
        self.assertEqual(len(plan.restored), 90)
        self.assertEqual([item.key for item in plan.unremovable], [cell_item_key(CREATED)])
        steps = save_steps(rollback_writes(plan))
        self.assertEqual(len(steps), 8)
        after = scene.applied(self.now, steps)
        self.assertEqual({k: v for k, v in after.cells.items() if k != CREATED},
                         {k: v for k, v in self.saved_state.cells.items() if k != CREATED})

    def test_a_restore_is_recorded_as_a_change_and_can_itself_be_rolled_back(self):
        plan = plan_cell_restore(self.ledger.recorded_snapshot(self.saved), self.now)
        restore = self.ledger.record_preview(hotel=plan.hotel, offer=plan.offer, currency=plan.currency,
                                             sentence="저장해 둔 상태로", read_at=plan.read_at, rows=rollback_rows(plan),
                                             request=dict(kind="restore_snapshot", snapshot=self.saved))
        steps = save_steps(rollback_writes(plan))
        self.ledger.begin(restore, step_plans(steps))
        for index in range(1, len(steps) + 1):
            self.ledger.record_step(restore, index, saved=True)
        restored = scene.applied(self.now, steps, "2026-11-27T09:00:00+09:00")
        self.assertEqual(self.ledger.verify(restore, snapshot_reading(restored)), [])
        record = self.ledger.change(restore)
        self.assertEqual((record.kind, record.status, record.request["kind"]), ("change", "applied", "restore_snapshot"))
        back = plan_cell_rollback(self.ledger.recorded_change(restore), self.ledger.later_writes(restore), restored)
        self.assertEqual((len(back.restored), len(back.kept), back.unremovable), (90, 0, ()))
        self.assertEqual(scene.applied(restored, save_steps(rollback_writes(back))).cells, self.now.cells)

    def test_part_of_the_saved_range_can_be_restored(self):
        select, scope = cell_filter(rooms=["디럭스"], date_from="2027-01-01")
        plan = plan_cell_restore(self.ledger.recorded_snapshot(self.saved), self.now, select)
        self.assertEqual((len(plan.restored), plan.unremovable, scope), (24, (), "디럭스 / 1/1 금 ~ 끝"))

    def test_only_a_saved_state_can_be_restored_and_the_range_must_be_read_now(self):
        with self.assertRaises(LedgerError):
            self.ledger.recorded_snapshot(self.saved + 1)
        with self.assertRaises(LedgerError):
            self.ledger.recorded_change(self.saved)
        partial = Snapshot(self.now.hotel, self.now.offer, "USD", self.now.read_at,
                           {k: v for k, v in self.now.cells.items() if k.room == "디럭스"}, self.now.reserved,
                           frozenset(pair for pair in self.now.pairs if pair[0] == "디럭스"))
        with self.assertRaises(Refused):
            plan_cell_restore(self.ledger.recorded_snapshot(self.saved), partial)

    def test_the_restore_preview_and_the_command(self):
        plan = plan_cell_restore(self.ledger.recorded_snapshot(self.saved), self.now)
        text = visible(render_rollback(plan, self.now.reserved))
        self.assertIn("저장해 둔 상태로 되돌리기 미리보기 · 데모 호텔 · 기본 오퍼", text)
        self.assertIn("2026-11-20 14:02 에 저장해 둔 상태로 되돌립니다. 저장할 때 하신 말: “연말 가격 바꾸기 전에 저장”", text)
        self.assertIn("90 되돌리는 칸 0 그대로 두는 칸 1 지울 수 없는 칸", text)
        self.assertIn("지울 수 없는 칸 — ERP 에 지우는 길이 없어 지금 값 그대로 남습니다", text)
        self.assertIn("1/2 토 · 스위트 · 룸온리 · 성인 2 · 1박 판매가 450.00", text)
        self.assertIn("528.00 → 480.00 정가 548.00 → 500.00", text)
        folder = Path(self.tmp.name)
        (folder / "now.json").write_text(json.dumps(encode_snapshot(self.now), ensure_ascii=False), encoding="utf-8")
        env = {**os.environ, "STAY_PRICE_LEDGER_DIR": str(folder / "cli")}
        script = str(HERE.parent / "scripts" / "price_change.py")

        def run(*args, code=0):
            done = subprocess.run([sys.executable, script, *map(str, args)], capture_output=True, text=True, env=env)
            self.assertEqual(done.returncode, code, done.stderr)
            return json.loads(done.stdout if code == 0 else done.stderr)

        (folder / "saved.json").write_text(json.dumps(encode_snapshot(self.saved_state), ensure_ascii=False), encoding="utf-8")
        saved = run("save-snapshot", "--snapshot", folder / "saved.json")["change_id"]
        result = run("restore", "--saved", saved, "--snapshot", folder / "now.json", "--record", "--out", folder / "r.json")
        self.assertEqual((len(result["rollback"]["restored"]), len(result["rollback"]["unremovable"]), len(result["steps"])),
                         (90, 1, 8))
        self.assertEqual(run("begin", "--change", result["change_id"], "--plan", folder / "r.json")["steps"], 8)
        page = Path(run("render", "rollback", "--plan", folder / "r.json")["page"]).read_text(encoding="utf-8")
        self.assertIn("저장해 둔 상태로 되돌리기 미리보기", page)
        refused = run("restore", "--saved", result["change_id"], "--snapshot", folder / "now.json", code=2)
        self.assertIn("저장해 둔 상태가 아닙니다", refused["error"])


class UnremovableTest(unittest.TestCase):
    """R6 — 변경이 만든 칸은 되돌려도 지울 수 없다. 적용 전 미리보기와 되돌리기 계획이 그렇게 말한다."""

    def test_rolling_back_a_target_table_lists_the_new_cell_as_unremovable(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(Path(folder) / DB_NAME)
            before = scene.snapshot()
            plan = plan_targets(before, TargetTable(scene.HOTEL, scene.OFFER, (
                Target(CREATED, (("sell", D("450.00")),)),
                Target(CellKey("디럭스", "조식 포함", "2026-12-25", "A2", 1), (("sell", D("205.00")),))), "새 요금표"))
            preview = visible(render_preview(plan))
            self.assertIn("이 칸들은 나중에 되돌려도 지울 수 없습니다", preview)
            change = ledger.record_preview(hotel=scene.HOTEL, offer=scene.OFFER, currency="USD", sentence="새 요금표",
                                           read_at=plan.read_at, rows=preview_rows(plan), request=encode_request(plan.request))
            steps = save_steps(resolve(plan, [])[0])
            ledger.begin(change, step_plans(steps))
            for index in range(1, len(steps) + 1):
                ledger.record_step(change, index, saved=True)
            now = scene.applied(before, steps)
            rollback = plan_cell_rollback(ledger.recorded_change(change), ledger.later_writes(change), now)
            self.assertEqual([item.key for item in rollback.unremovable], [cell_item_key(CREATED)])
            self.assertEqual(len(rollback.restored), 1)
            text = visible(render_rollback(rollback, now.reserved))
            self.assertIn("1 되돌리는 칸 0 그대로 두는 칸 1 지울 수 없는 칸", text)
            self.assertIn("이 변경으로 새로 생겼습니다", text)
            self.assertIn("지울 수 없는 1칸은 그대로 남습니다", text)


if __name__ == "__main__":
    unittest.main()
