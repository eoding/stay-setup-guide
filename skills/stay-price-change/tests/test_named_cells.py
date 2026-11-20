"""G3 — 요청이 칸을 짚을 수 있다. 결정 14 는 따로 말하지 않으면 모든 인원 조합 · 박수 층이 움직인다는 것이고, 이것이 그
"따로 말한" 경우다: 인원 조합 키 · 박수 층을 적으면 그 칸만 움직이고, 규칙 · 표시 · 저장 단계는 다른 변경과 같다. 새 값 지정의
기준 칸은 짚은 칸 안에 있어야 한다. 도우미가 값을 셈할 일은 없다.

    python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import scene  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from price_model import CellKey, decode_request, encode_request, encode_snapshot  # noqa: E402
from price_pages import render_preview  # noqa: E402
from price_plan import PlanError, counts, plan_change, plan_steps, resolve, unresolved  # noqa: E402
from test_pages import visible  # noqa: E402


class NamedCellsTest(unittest.TestCase):
    def test_only_the_named_occupancies_and_nights_move(self):
        everything = plan_change(scene.snapshot(), scene.request())
        adults = plan_change(scene.snapshot(), scene.request(occupancies=("A2",)))
        self.assertEqual((len(everything.changes), len(adults.changes)), (90, 30))
        self.assertEqual({change.key.occupancy for change in adults.changes}, {"A2"})
        one_night = plan_change(scene.snapshot(), scene.request(occupancies=("A2",), nights=(1,)))
        self.assertEqual({(c.key.occupancy, c.key.nights) for c in one_night.changes}, {("A2", 1)})
        self.assertEqual(len(one_night.changes), 15)
        same = {change.key: change.after for change in everything.changes}
        self.assertTrue(all(change.after == same[change.key] for change in one_night.changes), "짚은 칸의 새 값은 전부일 때와 같다")

    def test_rules_marks_and_saves_follow_as_for_any_change(self):
        plan = plan_change(scene.snapshot(), scene.request(occupancies=("A2",), nights=(1,)))
        tally = counts(plan.changes, len(plan.skipped))
        self.assertEqual((tally["ABOVE_LIST"], tally["reserved"], tally["closed"]), (2, 4, 1))
        self.assertEqual(len(unresolved(plan)), 2, "정가를 넘는 칸은 여전히 빨간 줄이다")
        steps = plan_steps(resolve(plan, [Resolution("ABOVE_LIST", "keep")]))
        self.assertTrue(all(row.occupancy == "A2" and row.nights == 1 for step in steps for row in step.rows), "저장은 짚은 줄만 보낸다")

    def test_a_child_cell_named_alone_still_scales_the_adult_share_only(self):
        plan = plan_change(scene.snapshot(), scene.request(occupancies=("A2C1_CHD",), nights=(1,)))
        cell = next(c for c in plan.changes if c.key == CellKey("디럭스", "조식 포함", "2026-12-25", "A2C1_CHD", 1))
        self.assertEqual((cell.before.sell, cell.after.sell), (D("230.00"), D("250.00")), "성인 2 칸(200)에만 10%, 아동 추가 30 그대로")

    def test_set_needs_its_base_cell_among_the_named_cells(self):
        with self.assertRaisesRegex(ValueError, "기준 칸\\(성인 2 · 1박\\)이 고른 칸에 없습니다"):
            scene.request(operation="set", value=D("350"), base_occupancy="A2", occupancies=("A3",))
        with self.assertRaisesRegex(ValueError, "기준 칸"):
            scene.request(operation="set", value=D("350"), base_occupancy="A2", nights=(3,))
        plan = plan_change(scene.snapshot(), scene.request(operation="set", value=D("350"), base_occupancy="A2",
                                                           occupancies=("A2", "A3"), nights=(1,), rooms=("디럭스",)))
        moved = {(c.key.rate_plan, c.key.date, c.key.occupancy): (c.before.sell, c.after.sell) for c in plan.changes}
        self.assertEqual(moved[("조식 포함", "2026-12-25", "A2")], (D("200.00"), D("350.00")))
        self.assertEqual(moved[("조식 포함", "2026-12-25", "A3")], (D("260.00"), D("410.00")), "차이는 그대로 옮긴다")
        self.assertFalse(any(c.key.nights == 3 for c in plan.changes))

    def test_a_cell_that_was_not_read_is_refused_by_name(self):
        with self.assertRaisesRegex(PlanError, "읽은 값에 없는 인원 조합: 성인 5\\(A5\\)"):
            plan_change(scene.snapshot(), scene.request(occupancies=("A2", "A5")))
        with self.assertRaisesRegex(PlanError, "읽은 값에 없는 박수 층: 7"):
            plan_change(scene.snapshot(), scene.request(nights=(7,)))
        with self.assertRaises(ValueError):
            scene.request(occupancies=("A2", "A2"))

    def test_the_request_travels_in_json_and_the_preview_says_which_cells(self):
        request = scene.request(occupancies=("A2",), nights=(1,))
        self.assertEqual(decode_request(encode_request(request)), request)
        text = visible(render_preview(plan_change(scene.snapshot(), request)))
        self.assertIn("칸 성인 2 / 1박", text)
        self.assertIn("칸 모든 인원 조합 · 모든 박수", visible(render_preview(plan_change(scene.snapshot(), scene.request()))))

    def test_the_command_plans_a_request_with_named_cells(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "s.json").write_text(json.dumps(encode_snapshot(scene.snapshot()), ensure_ascii=False), encoding="utf-8")
            data = dict(encode_request(scene.request()), occupancies=["A2"], nights=[1])
            (folder / "r.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            done = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "price_change.py"), "plan", "--snapshot",
                                   str(folder / "s.json"), "--request", str(folder / "r.json")],
                                  capture_output=True, text=True, env={**os.environ, "STAY_PRICE_LEDGER_DIR": str(folder)})
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(json.loads(done.stdout)["counts"]["cells"], 15)


if __name__ == "__main__":
    unittest.main()
