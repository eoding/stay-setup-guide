"""요청은 정확한 (객실, 요금제) 쌍을 가진다(R12) — 객실마다 요금제가 달라도 한 문장은 변경 하나다.

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
from change_core.rules import Resolution  # noqa: E402
from price_model import ChangeRequest, Snapshot, decode_request, encode_request, encode_snapshot  # noqa: E402
from price_pages import render_preview  # noqa: E402
from price_plan import PlanError, counts, plan_change, resolve, save_steps  # noqa: E402
from test_pages import visible  # noqa: E402

D = Decimal


def suite_without_room_only() -> Snapshot:
    """그림 장면에서 스위트에 룸온리 요금제가 없는 호텔 — 그 쌍을 읽지 않았다(없으니까)."""
    full = scene.snapshot()
    return replace(full, cells={k: v for k, v in full.cells.items() if (k.room, k.rate_plan) != ("스위트", "룸온리")},
                   pairs=full.pairs - {("스위트", "룸온리")})


class PairsTest(unittest.TestCase):
    def test_rooms_and_rate_plans_given_apart_mean_each_listed_plan_the_room_has_in_one_change(self):
        plan = plan_change(suite_without_room_only(), scene.request())
        self.assertEqual(plan.request.pairs, (("디럭스", "조식 포함"), ("디럭스", "룸온리"), ("스위트", "조식 포함")))
        self.assertEqual(plan.absent_pairs, (("스위트", "룸온리"),))
        self.assertEqual({(c.key.room, c.key.rate_plan) for c in plan.changes},
                         {("디럭스", "조식 포함"), ("디럭스", "룸온리"), ("스위트", "조식 포함")})
        steps = save_steps(resolve(plan, [Resolution("ABOVE_LIST", "raise_list")])[0])
        self.assertEqual((counts(plan.changes, len(plan.skipped))["cells"], len(steps)), (72, 6))

    def test_the_preview_names_which_rooms_lack_which_rate_plan(self):
        text = visible(render_preview(plan_change(suite_without_room_only(), scene.request())))
        self.assertIn("객실 · 요금제 디럭스(조식 포함 · 룸온리), 스위트(조식 포함)", text)
        self.assertIn("없는 요금제 스위트에는 룸온리 요금제가 없어 뺐습니다", text)

    def test_explicit_pairs_cover_exactly_those_pairs(self):
        request = scene.request(rooms=(), rate_plans=(), pairs=(("스위트", "룸온리"), ("디럭스", "조식 포함")))
        self.assertEqual((request.rooms, request.rate_plans), (("스위트", "디럭스"), ("룸온리", "조식 포함")))
        plan = plan_change(scene.snapshot(), request)
        self.assertEqual({(c.key.room, c.key.rate_plan) for c in plan.changes}, {("스위트", "룸온리"), ("디럭스", "조식 포함")})
        self.assertEqual(plan.absent_pairs, ())

    def test_an_explicit_pair_that_was_not_read_is_refused_by_name(self):
        request = scene.request(rooms=(), rate_plans=(), pairs=(("디럭스", "조식 포함"), ("스위트", "룸온리")))
        with self.assertRaises(PlanError) as caught:
            plan_change(suite_without_room_only(), request)
        self.assertIn("스위트 · 룸온리", str(caught.exception))

    def test_a_listed_room_or_rate_plan_with_nothing_read_is_refused_not_dropped(self):
        with self.assertRaises(PlanError) as caught:
            plan_change(scene.snapshot(), scene.request(rooms=("디럭스", "패밀리")))
        self.assertIn("패밀리 · 조식 포함", str(caught.exception))
        with self.assertRaises(PlanError):
            plan_change(scene.snapshot(), scene.request(rate_plans=("조식 포함", "반값 요금")))

    def test_the_scene_resolves_to_its_four_pairs_and_keeps_its_numbers(self):
        plan = plan_change(scene.snapshot(), scene.request())
        self.assertEqual((len(plan.request.pairs), plan.absent_pairs), (4, ()))
        tally = counts(plan.changes, len(plan.skipped))
        self.assertEqual((tally["cells"], tally["reserved"], tally["closed"], tally["skipped"], tally["ABOVE_LIST"]),
                         (90, 24, 6, 6, 2))

    def test_pairs_travel_in_json_and_bad_pairs_are_refused(self):
        request = scene.request(rooms=(), rate_plans=(), pairs=(("디럭스", "룸온리"),))
        self.assertEqual(decode_request(encode_request(request)), request)
        with self.assertRaises(ValueError):
            scene.request(rooms=(), rate_plans=(), pairs=(("디럭스", "룸온리"), ("디럭스", "룸온리")))
        with self.assertRaises(ValueError):
            scene.request(pairs=(("패밀리", "룸온리"),))
        with self.assertRaises(ValueError):
            ChangeRequest("H", "O", (), (), ("2026-12-25",), "amount", D("1"))

    def test_the_command_records_the_resolved_pairs(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "s.json").write_text(json.dumps(encode_snapshot(suite_without_room_only()), ensure_ascii=False),
                                           encoding="utf-8")
            (folder / "r.json").write_text(json.dumps(encode_request(scene.request()), ensure_ascii=False), encoding="utf-8")
            done = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "price_change.py"), "plan", "--snapshot",
                                   str(folder / "s.json"), "--request", str(folder / "r.json"), "--record"],
                                  capture_output=True, text=True, env={**os.environ, "STAY_PRICE_LEDGER_DIR": str(folder)})
            self.assertEqual(done.returncode, 0, done.stderr)
            result = json.loads(done.stdout)
            self.assertEqual(len(result["plan"]["request"]["pairs"]), 3)
            self.assertEqual(result["plan"]["absent_pairs"], [{"room": "스위트", "rate_plan": "룸온리"}])
            listed = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "price_change.py"), "list"],
                                    capture_output=True, text=True, env={**os.environ, "STAY_PRICE_LEDGER_DIR": str(folder)})
            self.assertEqual(json.loads(listed.stdout)["changes"][0]["id"], result["change_id"])


if __name__ == "__main__":
    unittest.main()
