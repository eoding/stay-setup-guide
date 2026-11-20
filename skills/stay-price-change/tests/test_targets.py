"""목표 값 표 — 지금 값과 다른 칸만, 필드 여럿, 비우기, 새로 생기는 칸(판매가 필요 · 보인 적 있는 인원·박수만), 같은 규칙.

    python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
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
from price_plan import counts, plan_steps, plan_targets, unresolved  # noqa: E402
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
        self.assertEqual(unresolved(plan), ())
        steps = plan_steps(plan)
        self.assertEqual([s.kind for s in steps], ["bulk", "cell_edit"])
        self.assertEqual([(r.sell, r.list, r.supply) for r in steps[0].rows], [(D("210.00"), D("260.00"), D("150.00"))])

    def test_a_target_on_a_day_without_price_is_a_new_cell_written_in_the_bulk_save(self):
        new = key("2027-01-02", room="스위트", plan="룸온리")
        plan = plan_targets(self.snapshot, table((new, {"sell": "450.00", "supply": "300.00"})))
        change = plan.changes[0]
        self.assertEqual((change.marks, change.verdict, change.after.state), (("new",), None, "open"))
        self.assertEqual(counts(plan.changes)["new"], 1)
        steps = plan_steps(plan)
        self.assertEqual([(s.dates, [(r.occupancy, r.sell, r.supply) for r in s.rows]) for s in steps],
                         [(("2027-01-02",), [("A2", D("450.00"), D("300.00"))])])

    def test_a_new_cell_needs_a_sell_price_and_an_occupancy_the_room_already_shows(self):
        plan = plan_targets(self.snapshot, table(
            (key("2027-01-02", room="스위트", plan="룸온리"), {"list": "500.00"}),
            (key("2026-12-25", occupancy="A4"), {"sell": "400.00"}),
            (key("2026-12-25", nights=7), {"sell": "150.00"})))
        self.assertEqual(sorted((c.key.occupancy, c.key.nights, c.verdict) for c in plan.changes),
                         [("A2", 1, "NEW_WITHOUT_SELL"), ("A2", 7, "NEW_NOT_SHOWN"), ("A4", 1, "NEW_NOT_SHOWN")])
        self.assertEqual(plan_steps(plan), ())

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


class TargetLinesTest(unittest.TestCase):
    """T6 — 담당자의 표는 객실 · 요금제 · 날짜 · 값만 적는다. 그 객실 · 요금제에 읽힌 줄이 하나뿐이면 그 줄이다."""

    def setUp(self):
        whole = scene.snapshot()
        # 디럭스 조식 포함은 성인 2 · 1박 줄 하나만 읽힌 호텔처럼
        self.snapshot = replace(whole, cells={k: v for k, v in whole.cells.items()
                                              if (k.room, k.rate_plan) != (ROOM, PLAN) or (k.occupancy, k.nights) == ("A2", 1)})

    def test_a_target_without_occupancy_or_nights_means_the_only_line(self):
        request = table((key("2026-12-25", occupancy=None, nights=None), {"sell": "210.00"}))
        plan = plan_targets(self.snapshot, request)
        self.assertEqual([(c.key.occupancy, c.key.nights, c.after.sell) for c in plan.changes], [("A2", 1, D("210.00"))])
        self.assertEqual(plan.request.targets[0].key, key("2026-12-25"), "미리보기 · 장부의 요청은 채운 줄이다")
        text = visible(render_preview(plan))
        self.assertIn("칸 성인 2 · 1박", text, "미리보기 머리가 어느 줄인지 말한다")

    def test_several_lines_are_refused_with_the_lines_to_choose_from(self):
        with self.assertRaises(Refused) as caught:
            plan_targets(scene.snapshot(), table((key("2026-12-25", occupancy=None, nights=None), {"sell": "210.00"})))
        message = str(caught.exception)
        for line in ("성인 2 · 1박(A2 · 1)", "성인 2 · 3박 이상(A2 · 3)", "성인 2 + 아동 1 · 3박 이상(A2C1_CHD · 3)"):
            self.assertIn(line, message)
        self.assertIn("인원 조합(occupancy)과 박수(nights)를 적습니다", message)
        # 인원 조합만 적고 박수가 없으면 그 인원 조합의 박수 층이 하나일 때만
        with self.assertRaises(Refused) as caught:
            plan_targets(scene.snapshot(), table((key("2026-12-25", nights=None), {"sell": "210.00"})))
        self.assertIn("성인 2 · 1박(A2 · 1) / 성인 2 · 3박 이상(A2 · 3)", str(caught.exception))
        one_tier = replace(scene.snapshot(), cells={k: v for k, v in scene.snapshot().cells.items() if k.nights == 1})
        plan = plan_targets(one_tier, table((key("2026-12-25", occupancy="A3", nights=None), {"sell": "300.00"})))
        self.assertEqual([(c.key.occupancy, c.key.nights) for c in plan.changes], [("A3", 1)])

    def test_a_table_file_may_leave_the_line_out_and_an_empty_occupancy_still_means_no_occupancy(self):
        data = encode_request(table((key("2026-12-25"), {"sell": "210.00"})))
        data["targets"][0]["key"] = {"room": ROOM, "rate_plan": PLAN, "date": "2026-12-25"}
        self.assertEqual(decode_request(data).targets[0].key, key("2026-12-25", occupancy=None, nights=None))
        data["targets"][0]["key"].update(occupancy="", nights=1)
        self.assertEqual(decode_request(data).targets[0].key, key("2026-12-25", occupancy="", nights=1), "빈 키는 인원 무관 줄이다")
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            data["targets"][0]["key"] = {"room": ROOM, "rate_plan": PLAN, "date": "2026-12-25"}
            (folder / "s.json").write_text(json.dumps(encode_snapshot(self.snapshot), ensure_ascii=False), encoding="utf-8")
            (folder / "t.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            done = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "price_change.py"), "plan", "--record",
                                   "--snapshot", str(folder / "s.json"), "--request", str(folder / "t.json")],
                                  capture_output=True, text=True, env={**os.environ, "STAY_PRICE_LEDGER_DIR": str(folder)})
            self.assertEqual(done.returncode, 0, done.stderr)
            result = json.loads(done.stdout)
            self.assertEqual(result["plan"]["request"]["targets"][0]["key"], encode_key(key("2026-12-25")))
            self.assertEqual(len(result["steps"]), 1)


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
