"""진짜 페이지 모듈의 답(tests/fixtures/browser/ — jsdom 받침 위의 stay_addon_price.js 가 낸 것, test_page_goldens.mjs 가 지금 코드와
같은지 본다)을 명령의 읽기가 그대로 받고, 파이썬 시험의 답(addon_scene)이 그 답과 같은 것을 말한다. 두 쪽이 따로 놀지 않는다.

    python3 -m unittest discover -s tests
"""

import json
import unittest
from pathlib import Path

import addon_scene as scene
from addon_model import encode_line, line_of, listing_of
from addon_plan import LineStep, step_call
from change_core.answers import ask_sum, attach_bodies, step_outcome

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "browser"


def golden(name):
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))


class GoldenTest(unittest.TestCase):
    def test_the_real_read_answer_becomes_the_same_line_as_the_test_scene_says(self):
        inputs = golden("inputs")
        real, = attach_bodies(golden("readLine"))
        self.assertEqual(real["ask"], ask_sum(inputs["readLine"]), "파이썬의 지문 셈이 페이지의 것과 같다")
        made, = attach_bodies(scene.Erp().read_line(inputs["readLine"]))
        self.assertEqual(encode_line(line_of(real)), encode_line(line_of(made)))
        line = line_of(real)
        self.assertEqual((str(line.sell), str(line.supply), line.doubt), ("20.00", "15.00", None))

    def test_the_real_look_answer_lists_the_lines_the_test_scene_lists(self):
        real, = attach_bodies(golden("look"))
        listing = listing_of(real, "2026-11-21T09:00:00+09:00")
        rows = {line.key.line: line for line in listing.lines}
        for item in scene.demo_lines():
            row = scene.row_of(item)
            listed = rows[item["line"]]
            self.assertEqual((listed.name, listed.sell_text, list(listed.values), listed.target),
                             (row["name"], row["sell"], row["values"], row["target"]), item["line"])
        self.assertEqual(listing.currency, "USD")

    def test_the_real_save_answer_is_read_as_saved_for_the_step_the_command_would_send(self):
        inputs = golden("inputs")["applyLine"]
        step = LineStep(inputs["addon"], inputs["line"], "조식 추가 (성인) · 비수기 조식", tuple(map(tuple, inputs["form"])),
                        inputs["set"])
        call = step_call(inputs["no"], inputs["hotel"]["name"], inputs["hotel"]["id"], step)
        self.assertEqual(call["payload"], inputs, "명령이 내는 부를 값이 받침이 넣은 값과 같다")
        answer, = golden("applyLine")
        self.assertTrue(step_outcome(call, answer).saved)
        self.assertEqual([list(pair) for pair in step.sent()], golden("inputs")["posted"][0], "보낸 칸 = 읽은 칸 + 바꾼 칸")


if __name__ == "__main__":
    unittest.main()
