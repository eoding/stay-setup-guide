"""계산(M2 · M3 · M6) — 명령이 셈하고 판정한다. 단의 값만 바꾸고, 저장 단계는 단의 값 칸 말고는 아무것도 바꾸지 않으며 표식 없는 창에서는
만들어지지 않는다. 장부의 항목 키는 프로모션 번호와 단의 기준값이다.

    python3 -m unittest discover -s tests
"""

import unittest
from decimal import Decimal

import promotion_scene as scene
from promotion_model import GATE, ORIGIN_UNKNOWN, ModelError, Snapshot, decode_request, promotion_of, snapshot_items, tier_key
from promotion_plan import PlanError, PromotionStep, Edit, plan_change, plan_steps, resolve, step_call
from change_core.answers import attach_bodies
from change_core.rules import Resolution

READ_AT = "2026-11-23T10:00:00+09:00"


def snapshot(*ids, keeps=True, change=None):
    """작은 ERP 에서 읽은 지금 값 — `change(erp)` 로 먼저 데이터를 바꿀 수 있다."""
    erp = scene.Erp(keeps=keeps)
    if change:
        change(erp)
    promotions, asked = {}, []
    for promotion_id in ids:
        offer = next(scene.offer_of(card)["id"] for card, ps in erp.cards() for p in ps if p["id"] == promotion_id)
        answer, = attach_bodies(erp.read_promotion(dict(hotel=scene.HOTEL, offer=offer, promotion=promotion_id)))
        promotions[promotion_id] = promotion_of(answer)
        asked.append((offer, promotion_id))
    return Snapshot(scene.HOTEL["name"], scene.HOTEL["id"], READ_AT, tuple(asked), promotions)


def request(*tiers, **change):
    return decode_request(dict(kind="promotion_change", hotel=scene.HOTEL, sentence="바꿔줘",
                               tiers=[dict(offer=offer, promotion=promotion, tier=tier) for offer, promotion, tier in tiers], **change))


def one(snap, *tier, **change):
    plan = plan_change(snap, request(tier, **change))
    return plan, plan.changes[0]


class ArithmeticTest(unittest.TestCase):
    def test_the_command_adds_scales_or_sets_and_rounds_by_the_basis(self):
        snap = snapshot("9002", "9003", "9004")
        self.assertEqual(one(snap, "601", "9002", "2", amount="2")[1].after, Decimal("9"), "할인율 2% 포인트 올림")
        self.assertEqual(one(snap, "601", "9002", "3", percent="15")[1].after, Decimal("11.5"), "지금 값의 15% 만큼 올림")
        self.assertEqual(one(snap, "601", "9002", "2", value="7.125")[1].after, Decimal("7.13"), "할인율은 소수 둘(반올림)")
        self.assertEqual(one(snap, "601", "9003", "0", value="25.005")[1].after, Decimal("25.01"), "할인 금액은 호텔 통화 자릿수")
        self.assertEqual(one(snap, "601", "9004", "4", amount="1")[1].after, Decimal("2"))
        self.assertEqual(str(one(snap, "601", "9003", "0", amount="5")[1].after), "25", "셈한 값은 끝의 0 을 뺀다")

    def test_the_tier_is_named_by_its_threshold_and_a_missing_tier_is_refused_with_the_ones_there(self):
        snap = snapshot("9002")
        self.assertEqual(one(snap, "601", "9002", "03", value="8")[1].tier, "3")
        with self.assertRaises(ModelError) as caught:
            plan_change(snap, request(("601", "9002", "5"), value="8"))
        self.assertIn("있는 단: 2 · 3", str(caught.exception))

    def test_a_promotion_named_under_another_card_is_refused(self):
        with self.assertRaises(PlanError):
            plan_change(snapshot("9006"), request(("601", "9006", "0"), value="6"))


class RulesTest(unittest.TestCase):
    def verdict(self, snap, *tier, **change):
        return one(snap, *tier, **change)[1].verdict

    def test_results_the_form_refuses_cannot_be_applied(self):
        snap = snapshot("9002", "9004")
        self.assertEqual(self.verdict(snap, "601", "9002", "2", amount="-8"), "NEGATIVE")
        self.assertEqual(self.verdict(snap, "601", "9002", "2", value="101"), "PCT_RANGE")
        self.assertEqual(self.verdict(snap, "601", "9004", "4", value="1.5"), "NOT_WHOLE")

    def test_a_promotion_the_form_would_refuse_as_it_stands_cannot_be_saved(self):
        def broken(erp):
            erp.promotion("9006")["apply_end"] = ""
        plan, change = one(snapshot("9006", change=broken), "0", "9006", "0", value="6")
        self.assertEqual(change.verdict, "FORM_REFUSES")
        self.assertEqual(plan_steps(plan), ())

    def test_red_lines_zero_room_free_inverted_tiers_and_over_30_percent(self):
        snap = snapshot("9002", "9004", "9006")
        self.assertEqual(self.verdict(snap, "601", "9002", "2", value="0"), "ZERO")
        self.assertEqual(self.verdict(snap, "601", "9002", "3", value="100"), "ROOM_FREE")
        self.assertEqual(self.verdict(snap, "601", "9004", "4", value="4"), "ROOM_FREE", "4박 이상 4박 무료 = 숙박 전체 무료")
        self.assertEqual(self.verdict(snap, "601", "9002", "2", value="10"), "OVER_30")
        self.assertEqual(self.verdict(snap, "601", "9002", "3", value="11"), None)
        self.assertEqual(self.verdict(snap, "601", "9002", "3", value="6"), "INVERTS", "3박 단이 2박 단(7%)보다 작아진다")

    def test_a_red_line_waits_for_a_choice_and_keep_means_the_tier_stays(self):
        snap = snapshot("9002")
        plan = plan_change(snap, request(("601", "9002", "2"), value="12"))
        self.assertIsNone(plan_steps(plan))
        kept = resolve(plan, [Resolution("INVERTS", "keep", ("9002 2",), "그대로 둬")])
        self.assertEqual((plan_steps(kept), kept.changes[0].after), ((), Decimal("7")))
        taken = resolve(plan, [Resolution("INVERTS", "include", None, "그대로 바꿔")])
        self.assertEqual(len(plan_steps(taken)), 1)

    def test_a_window_without_the_mark_blocks_every_change_with_the_plain_sentence(self):
        plan, change = one(snapshot("9002", keeps=False), "601", "9002", "2", value="8")
        self.assertEqual(change.verdict, "NO_MARK")
        self.assertEqual(plan_steps(plan), ())
        self.assertEqual([promotion.id for promotion in plan.unmarked], ["9002"])


class StepTest(unittest.TestCase):
    def test_the_step_sends_the_window_as_read_with_only_the_named_tier_value_and_carries_the_marks(self):
        snap = snapshot("9005")
        step, = plan_steps(plan_change(snap, request(("601", "9005", "31"), value="11")))
        form = list(snap.promotions["9005"].form)
        sent = list(step.sent())
        self.assertEqual([pair for pair in sent if pair not in form], [("tiers_value", "11")])
        self.assertEqual(len(sent), len(form))
        call = step_call(1, scene.HOTEL["name"], scene.HOTEL["id"], step)["payload"]
        self.assertEqual((call["set"], call["marks"]), ([["tiers_value", 1, "11"]], [["cancellation"], ["cancellation"]]))

    def test_a_step_refuses_an_unmarked_window_anything_but_a_tier_value_a_blank_or_a_tier_twice(self):
        promotion = snapshot("9002").promotions["9002"]
        key = tier_key("9002", "2")
        build = (lambda edits, keeps=True: PromotionStep("601", "9002", promotion.name, promotion.label, promotion.form,
                                                         promotion.marks, keeps, tuple(edits)))
        self.assertEqual(len(build([Edit(key, 0, "8")]).edits), 1)
        with self.assertRaises(PlanError) as caught:
            build([Edit(key, 0, "8")], keeps=False)
        self.assertIn(GATE, str(caught.exception))
        for edits in ([], [Edit(key, 0, "")], [Edit(key, 0, "-1")], [Edit(key, 0, "8"), Edit(key, 0, "9")],
                      [Edit(key, 1, "8")], [Edit(tier_key("9003", "0"), 0, "8")], [Edit(tier_key("9002"), 0, "8")]):
            with self.assertRaises(PlanError, msg=str(edits)):
                build(edits)
        first = next(index for index, (name, _value) in enumerate(promotion.form) if name == "tiers_origin")
        unsure = tuple(("tiers_origin", "?") if index == first else pair for index, pair in enumerate(promotion.form))
        with self.assertRaises(PlanError) as caught:   # W4 — 단 줄 출처를 ERP 가 모르는 창(`?`)의 저장 단계는 만들지 않는다
            PromotionStep("601", "9002", promotion.name, promotion.label, unsure, promotion.marks, True, (Edit(key, 0, "8"),))
        self.assertIn(ORIGIN_UNKNOWN, str(caught.exception))


class KeysAndRequestTest(unittest.TestCase):
    def test_item_keys_are_the_promotion_and_its_tier_threshold(self):
        items = snapshot_items(snapshot("9002"))
        self.assertEqual(sorted(key for _kind, key in items),
                         sorted([tier_key("9002"), tier_key("9002", "2"), tier_key("9002", "3")]))
        whole = items[("promotion", tier_key("9002"))]
        self.assertEqual(whole.fields, {})
        self.assertEqual(whole.others["mark.화면에 없는 설정을 지키는 표식"], "있음")
        self.assertNotIn("form.tiers_value", whole.others)
        self.assertIn("form.tiers_threshold", whole.others)

    def test_the_request_names_tiers_only_and_never_empties_one(self):
        for bad in (dict(clear=True, value="1"), dict(value="1", amount="2"), dict()):
            with self.assertRaises(ModelError):
                request(("601", "9002", "2"), **bad)
        with self.assertRaises(ModelError):
            request(("601", "9002", "2"), ("601", "9002", "02"), value="8")
        with self.assertRaises(ModelError):
            decode_request(dict(kind="promotion_change", hotel=scene.HOTEL, sentence="x", value="8",
                                tiers=[dict(offer="601", promotion="9002")]))
        self.assertEqual(request(("601", "9002", "2"), value=0).figure, Decimal(0), "0 은 값이다")


if __name__ == "__main__":
    unittest.main()
