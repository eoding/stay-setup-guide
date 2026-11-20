"""G6 — 명령 하나가 "이 변경에 무슨 일이 있었나" 에 답한다: 저장마다 됨 · 안 됨 · 섞임 · 그 사이 바뀜, 그리고 남은 저장을 계획대로
해도 되는지와 까닭. 「모름」인 저장은 방금 읽은 값으로 스스로 가려 장부에 적는다. 멈춘 변경은 check 가 이어서 해도 된다고 해야
calls 가 남은 단계를 낸다.

    python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
from change_core.ledger import DB_NAME, Ledger  # noqa: E402
from price_browser import ask_sum  # noqa: E402
from price_model import CellKey, decode_step, encode_request, encode_snapshot  # noqa: E402


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = {**os.environ, "STAY_PRICE_LEDGER_DIR": str(self.dir / "기록")}
        self.before = scene.snapshot()
        snapshot = self.write("snapshot.json", encode_snapshot(self.before))
        request = self.write("request.json", encode_request(scene.request()))
        choice = self.write("choice.json", [{"rule": "ABOVE_LIST", "choice": "raise_list"}])
        self.change = self.cli("plan", "--snapshot", snapshot, "--request", request, "--resolutions", choice, "--record",
                               "--out", self.dir / "plan.json")["change_id"]
        self.steps = [decode_step(step) for step in json.loads((self.dir / "plan.json").read_text(encoding="utf-8"))["steps"]]
        self.cli("begin", "--change", self.change, "--plan", self.dir / "plan.json")
        self.calls = self.cli("calls", "--change", self.change)["calls"]

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.dir / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def cli(self, *args, code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def answer(self, no, **over):
        call = self.calls[no - 1]
        result = dict({"ok": True, "op": call["op"], "no": no, "ask": ask_sum(call["payload"]), "saved": True, "pressed": True}, **over)
        return self.cli("record-result", "--change", self.change, "--result", self.write(f"answer-{no}.json", result))

    def reading(self, snapshot, name="now.json"):
        return self.write(name, encode_snapshot(snapshot))

    def check(self, snapshot):
        return self.cli("check", "--change", self.change, "--snapshot", self.reading(snapshot))

    def test_an_unknown_save_the_reading_shows_is_settled_as_saved_and_the_rest_can_go_on(self):
        self.answer(1)
        self.assertEqual(self.answer(2, ok=False, saved="unknown", error="모름")["status"], "stopped")
        self.assertIn("check", self.cli("calls", "--change", self.change, code=2)["error"])
        report = self.check(scene.applied(self.before, self.steps[:2]))
        self.assertEqual([(s["no"], s["ledger"], s["seen"], s["settled"]) for s in report["steps"][:3]],
                         [(1, "saved", "saved", None), (2, "unknown", "saved", "saved"), (3, "pending", "not_saved", None)])
        self.assertEqual((report["can_continue"], report["remaining"], report["why"], report["status"]),
                         (True, list(range(3, 9)), [], "applying"))
        self.assertEqual([call["no"] for call in self.cli("calls", "--change", self.change)["calls"]], list(range(3, 9)))
        step = Ledger(self.dir / "기록" / DB_NAME).change(self.change).steps[1]
        self.assertEqual((step.status, step.unknown, step.note), ("saved", False, "다시 읽어 저장된 것을 확인했습니다"), "장부에 적었다")

    def test_an_unknown_save_the_reading_does_not_show_is_settled_as_not_saved_and_called_again(self):
        self.answer(1)
        self.answer(2, ok=False, saved="unknown", error="모름")
        report = self.check(scene.applied(self.before, self.steps[:1]))
        self.assertEqual((report["steps"][1]["settled"], report["can_continue"], report["remaining"]), ("not_saved", True, list(range(2, 9))))
        self.assertEqual(self.cli("calls", "--change", self.change)["calls"][0]["no"], 2)
        again = self.check(scene.applied(self.before, self.steps[:1]))
        self.assertEqual((again["steps"][1]["ledger"], again["steps"][1]["settled"]), ("failed", None), "가린 뒤에는 저장 안 됨으로 남는다")

    def test_a_mixed_step_stays_unknown_and_stops_the_rest_with_the_reason(self):
        self.answer(1)
        self.answer(2, ok=False, saved="unknown", error="모름")
        half = scene.applied(self.before, self.steps[:2])
        step = self.steps[1]
        key = CellKey(step.room, step.rate_plan, step.dates[0], step.rows[0].occupancy, step.rows[0].nights)
        half = replace(half, cells={**half.cells, key: self.before.cells[key]})
        report = self.check(half)
        self.assertEqual((report["steps"][1]["seen"], report["steps"][1]["settled"], report["can_continue"]), ("mixed", None, False))
        self.assertTrue(any("2번째 저장" in why and "가리지 못했습니다" in why for why in report["why"]), report["why"])
        self.assertIn("check", self.cli("calls", "--change", self.change, code=2)["error"], "이어서 할 수 없으면 멈춘 채로 둔다")

    def test_a_saved_step_changed_since_and_a_remaining_cell_moved_since_the_preview_are_named(self):
        self.answer(1)
        self.answer(2, ok=False, saved=False, error="드로어 표에 없는 줄")
        now = scene.applied(self.before, self.steps[:1])
        first = CellKey(self.steps[0].room, self.steps[0].rate_plan, self.steps[0].dates[0], self.steps[0].rows[0].occupancy,
                        self.steps[0].rows[0].nights)
        third = CellKey(self.steps[2].room, self.steps[2].rate_plan, self.steps[2].dates[0], self.steps[2].rows[0].occupancy,
                        self.steps[2].rows[0].nights)
        now = replace(now, cells={**now.cells, first: replace(now.cells[first], sell=D("999.00")),
                                  third: replace(now.cells[third], list=D("888.00"))})
        report = self.check(now)
        self.assertEqual((report["steps"][0]["seen"], report["steps"][2]["seen"], report["steps"][2]["moved"]), ("changed", "not_saved", 1))
        self.assertFalse(report["can_continue"])
        self.assertTrue(any(why.startswith("1번째 저장") and "다른 값이 됐습니다" in why for why in report["why"]), report["why"])
        self.assertTrue(any(why.startswith("3번째 저장") and "1개가 미리보기 때 읽은 값과 다릅니다" in why for why in report["why"]))

    def test_a_reading_of_another_hotel_is_refused_and_a_finished_change_has_nothing_left(self):
        self.answer(1)
        elsewhere = replace(scene.applied(self.before, self.steps[:1]), hotel_id="2")
        self.assertIn("호텔 2", self.cli("check", "--change", self.change, "--snapshot", self.reading(elsewhere), code=2)["error"])
        for no in range(2, 9):
            self.answer(no)
        report = self.check(scene.applied(self.before, self.steps))
        self.assertEqual((report["status"], report["remaining"], report["can_continue"], report["why"]), ("applied", [], False, []))
        self.assertEqual({s["seen"] for s in report["steps"]}, {"saved"})


if __name__ == "__main__":
    unittest.main()
