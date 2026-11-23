"""진짜 페이지 모듈의 답(tests/fixtures/browser/ — jsdom 받침 위의 stay_promotion.js 가 낸 것, test_page_goldens.mjs 가 지금 코드와 같은지
본다)을 명령의 읽기가 그대로 받고, 파이썬 시험의 답(promotion_scene)이 그 답과 같은 것을 말한다. 두 쪽이 따로 놀지 않는다.

    python3 -m unittest discover -s tests
"""

import json
import unittest
from pathlib import Path

import promotion_scene as scene
from promotion_model import Snapshot, decode_request, encode_promotion, listing_of, promotion_of
from promotion_plan import plan_change, plan_steps, step_call
from change_core.answers import ask_sum, attach_bodies, step_outcome

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "browser"


def golden(name):
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))


class GoldenTest(unittest.TestCase):
    def test_the_real_read_answer_becomes_the_same_promotion_as_the_test_scene_says(self):
        inputs = golden("inputs")
        real, = attach_bodies(golden("readPromotion"))
        self.assertEqual(real["ask"], ask_sum(inputs["readPromotion"]), "파이썬의 지문 셈이 페이지의 것과 같다")
        made, = attach_bodies(scene.Erp().read_promotion(inputs["readPromotion"]))
        self.assertEqual(encode_promotion(promotion_of(real)), encode_promotion(promotion_of(made)))
        promotion = promotion_of(real)
        self.assertEqual([(tier.at, tier.value, tier.origin, tier.off) for tier in promotion.tiers()],
                         [("46", "15.0", "46", ("cancellation",)), ("31", "10.0", "31", ("cancellation",))])
        self.assertTrue(promotion.keeps)

    def test_the_real_look_answer_lists_every_promotion_the_test_scene_lists(self):
        real, = attach_bodies(golden("look"))
        made, = attach_bodies(scene.look_answer(scene.Erp()))
        self.assertEqual(listing_of(real, "2026-11-23T09:00:00+09:00"), listing_of(made, "2026-11-23T09:00:00+09:00"))

    def test_the_real_save_answer_is_read_as_saved_for_the_step_the_command_would_send(self):
        inputs = golden("inputs")
        real, = attach_bodies(golden("readPromotion"))
        promotion = promotion_of(real)
        snapshot = Snapshot(scene.HOTEL["name"], scene.HOTEL["id"], "2026-11-23T09:00:00+09:00", (("601", "9005"),),
                            {promotion.id: promotion})
        request = decode_request(dict(kind="promotion_change", hotel=scene.HOTEL, value="16", sentence="얼리버드 46일 16% 로",
                                      tiers=[{"offer": "601", "promotion": "9005", "tier": "46"}]))
        step, = plan_steps(plan_change(snapshot, request))
        call = step_call(inputs["applyPromotion"]["no"], scene.HOTEL["name"], scene.HOTEL["id"], step)
        self.assertEqual(call["payload"], inputs["applyPromotion"], "명령이 내는 부를 값이 받침이 넣은 값과 같다")
        answer, = golden("applyPromotion")
        self.assertIs(step_outcome(call, answer).saved, True)
        self.assertEqual([list(pair) for pair in step.sent()], inputs["posted"][0], "보낸 칸 = 읽은 칸 + 바꾼 단의 값")


if __name__ == "__main__":
    unittest.main()
