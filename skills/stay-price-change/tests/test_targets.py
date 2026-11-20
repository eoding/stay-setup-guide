"""목표 값 표 — 지금 값과 다른 칸만, 필드 여럿, 비우기, 새로 생기는 칸(판매가 필요 · 보인 적 있는 인원·박수만), 같은 규칙.

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
from price_model import (  # noqa: E402
    CellKey, Target, TargetTable, decode_request, encode_key, encode_request, encode_snapshot,
)
from price_pages import render_preview  # noqa: E402
from price_plan import counts, plan_targets, resolve, save_steps  # noqa: E402
from test_pages import visible  # noqa: E402

D = Decimal
ROOM, PLAN = "디럭스", "조식 포함"


def key(day, occupancy="A2", nights=1, room=ROOM, plan=PLAN):
    return CellKey(room, plan, day, occupancy, nights)


def table(*targets, sentence="새 요금표"):
    return TargetTable(scene.HOTEL, scene.OFFER, tuple(Target(k, tuple((name, None if v is None else D(v))
                                                                       for name, v in values.items()))
                                                       for k, values in targets), sentence, scene.HOTEL_ID)


class TargetPlanTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = scene.snapshot()

    def test_only_cells_that_differ_are_kept_and_several_fields_move_at_once(self):
        plan = plan_targets(self.snapshot, table(
            (key("2026-12-25"), {"sell": "200.00"}),
            (key("2026-12-26"), {"sell": "210.00", "list": "260.00", "supply": "150.00"}),
            (key("2027-01-01", room="스위트"), {"list": None})))
        self.assertEqual([(c.key.date, c.changed) for c in plan.changes],
                         [("2026-12-26", ("sell", "list", "supply")), ("2027-01-01", ("list",))])
        writes, unresolved = resolve(plan, [])
        self.assertEqual(unresolved, ())
        steps = save_steps(writes)
        self.assertEqual([s.kind for s in steps], ["bulk", "cell_edit"])
        self.assertEqual([(r.sell, r.list, r.supply) for r in steps[0].rows], [(D("210.00"), D("260.00"), D("150.00"))])

    def test_a_target_on_a_day_without_price_is_a_new_cell_written_in_the_bulk_save(self):
        new = key("2027-01-02", room="스위트", plan="룸온리")
        plan = plan_targets(self.snapshot, table((new, {"sell": "450.00", "supply": "300.00"})))
        change = plan.changes[0]
        self.assertEqual((change.marks, change.verdict, change.after.state), (("new",), None, "open"))
        self.assertEqual(counts(plan.changes)["new"], 1)
        steps = save_steps(resolve(plan, [])[0])
        self.assertEqual([(s.dates, [(r.occupancy, r.sell, r.supply) for r in s.rows]) for s in steps],
                         [(("2027-01-02",), [("A2", D("450.00"), D("300.00"))])])

    def test_a_new_cell_needs_a_sell_price_and_an_occupancy_the_room_already_shows(self):
        plan = plan_targets(self.snapshot, table(
            (key("2027-01-02", room="스위트", plan="룸온리"), {"list": "500.00"}),
            (key("2026-12-25", occupancy="A4"), {"sell": "400.00"}),
            (key("2026-12-25", nights=7), {"sell": "150.00"})))
        self.assertEqual(sorted((c.key.occupancy, c.key.nights, c.verdict) for c in plan.changes),
                         [("A2", 1, "NEW_WITHOUT_SELL"), ("A2", 7, "NEW_NOT_SHOWN"), ("A4", 1, "NEW_NOT_SHOWN")])
        self.assertEqual(resolve(plan, [])[0], ())

    def test_the_same_rules_apply_to_the_resulting_cell(self):
        plan = plan_targets(self.snapshot, table(
            (key("2026-12-25"), {"sell": "120.00"}),
            (key("2026-12-26"), {"sell": "210.00", "supply": "250.00"}),
            (key("2027-01-01", room="스위트"), {"sell": "520.00"}),
            (key("2027-01-02", room="스위트"), {"sell": "0"})))
        self.assertEqual([c.verdict for c in plan.changes], ["OVER_30", "BELOW_COST", "ABOVE_LIST", "NOT_POSITIVE"])

    def test_targets_outside_what_was_read_and_bad_tables_are_refused(self):
        with self.assertRaises(Refused):
            plan_targets(self.snapshot, table((key("2026-12-31"), {"sell": "200.00"})))
        with self.assertRaises(Refused) as caught:
            plan_targets(self.snapshot, table((key("2026-12-25", room="패밀리"), {"sell": "200.00"})))
        self.assertIn("패밀리 · 조식 포함", str(caught.exception))
        with self.assertRaises(ValueError):
            table((key("2026-12-25"), {"sell": "1"}), (key("2026-12-25"), {"sell": "2"}))
        with self.assertRaises(ValueError):
            table((key("2026-12-25"), {"sell": None}))
        with self.assertRaises(ValueError):
            table((key("2026-12-25"), {"tax": "1"}))

    def test_json_round_trip(self):
        request = table((key("2026-12-25"), {"sell": "200.00", "list": None}))
        self.assertEqual(decode_request(encode_request(request)), request)


class TargetPageAndCommandTest(unittest.TestCase):
    def test_preview_lists_new_cells_and_the_command_plans_a_target_table(self):
        request = table((key("2027-01-02", room="스위트", plan="룸온리"), {"sell": "450.00"}),
                        (key("2026-12-25"), {"sell": "205.00"}))
        text = visible(render_preview(plan_targets(scene.snapshot(), request)))
        self.assertIn("미리보기 · 데모 호텔 · 기본 오퍼 · 목표 값 2칸", text)
        self.assertIn("1 새로 생기는 칸", text)
        self.assertIn("새로 → 450.00 새 칸", text)
        self.assertIn("새로 생기는 칸 — 지금은 가격이 없는 칸입니다", text)
        self.assertIn("새로 생기는 칸은 나중에 되돌리기로 지울 수 없습니다", text)
        # T5 — 있던 칸에 정가 · 공급 원가를 넣는 것은 새 칸이 아니다(되돌리면 비워진다). 그 말은 새 칸이 있을 때만 나온다
        onto = visible(render_preview(plan_targets(scene.snapshot(), table((key("2026-12-25"), {"list": "260.00", "supply": "150.00"})))))
        self.assertIn("1 바뀌는 칸", onto)
        self.assertNotIn("새로 생기는 칸", onto)
        self.assertNotIn("지울 수 없습니다", onto)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "s.json").write_text(json.dumps(encode_snapshot(scene.snapshot()), ensure_ascii=False), encoding="utf-8")
            (folder / "t.json").write_text(json.dumps(encode_request(request), ensure_ascii=False), encoding="utf-8")
            done = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "price_change.py"), "plan",
                                   "--snapshot", str(folder / "s.json"), "--request", str(folder / "t.json")],
                                  capture_output=True, text=True, env={**os.environ, "STAY_PRICE_LEDGER_DIR": str(folder)})
            self.assertEqual(done.returncode, 0, done.stderr)
            result = json.loads(done.stdout)
            self.assertEqual((result["counts"]["new"], len(result["steps"])), (1, 2))
            self.assertEqual(result["plan"]["changes"][0]["key"], encode_key(key("2027-01-02", room="스위트", plan="룸온리")))


if __name__ == "__main__":
    unittest.main()
