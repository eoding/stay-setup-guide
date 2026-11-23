"""계산(M2 · M3 · M6) — 명령이 셈하고 판정한다. 단의 값만 바꾸고, 저장 단계는 단의 값 칸 말고는 아무것도 바꾸지 않으며 표식 없는 창에서는
만들어지지 않는다. 장부의 항목 키는 프로모션 번호와 단의 기준값이다.

    python3 -m unittest discover -s tests
"""

import unicodedata
import unittest
from unittest import mock
from decimal import Decimal

import promotion_scene as scene
from promotion_model import GATE, ORIGIN_UNKNOWN, ModelError, Refused, Snapshot, decode_request, promotion_of, snapshot_items, tier_key
from promotion_plan import RULES, PlanError, PromotionStep, Edit, plan_change, plan_steps, resolve, step_call
from change_core.answers import BrowserError, attach_bodies
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


class NameTest(unittest.TestCase):
    """P3 (리뷰 2 · 페이지 6) — 이름에 빈칸 둘 · 앞뒤 빈칸 · 풀어 쓴 한글(NFD)이 든 프로모션도 읽고 바꾼다: 목록의 이름(페이지가 맞춰 읽은
    글자)과 편집 창의 이름 칸(날 글자)을 같은 셈으로 맞춰 견준다. 다른 이름의 창은 여전히 거절한다."""

    NAME = "롱스테이 2박 7% / 3박 10%"

    def test_a_name_with_doubled_or_end_spaces_or_decomposed_hangul_is_read_and_planned(self):
        for raw in ("롱스테이  2박 7% / 3박 10%", " 롱스테이 2박 7% / 3박 10% ", unicodedata.normalize("NFD", self.NAME)):
            snap = snapshot("9002", change=lambda erp, raw=raw: erp.promotion("9002").update(title=raw))
            promotion = snap.promotions["9002"]
            self.assertEqual((promotion.name, promotion.one("title")), (self.NAME, raw), repr(raw))
            step, = plan_steps(plan_change(snap, request(("601", "9002", "3"), value="12")))
            self.assertEqual(step_call(1, scene.HOTEL["name"], scene.HOTEL["id"], step)["payload"]["title"], self.NAME,
                             "페이지에 주는 이름은 목록의 이름")
            self.assertIn(("title", raw), step.form, "창의 이름 칸은 읽은 날 글자 그대로 보낸다")

    def test_a_window_whose_name_is_another_promotions_is_still_refused(self):
        erp = scene.Erp()
        answer, = attach_bodies(erp.read_promotion(dict(hotel=scene.HOTEL, offer="601", promotion="9002")))
        answer["window"]["form"] = [[name, "롱스테이 2박 8% / 3박 10%" if name == "title" else value] for name, value in answer["window"]["form"]]
        with self.assertRaises(BrowserError) as caught:
            promotion_of(answer)
        self.assertIn("목록의 이름(롱스테이 2박 7% / 3박 10%)과 다릅니다", str(caught.exception))


def both(*tiers):
    return tuple(("601", "9002", tier) for tier in tiers)


class LadderTest(unittest.TestCase):
    """P4 (리뷰 2 · 파이썬 4) — 빨간 줄은 저장될 값으로 판정한다. 한 단은 「안 바꿈」, 다른 단은 「이대로 바꿈」으로 고르면 단 사다리가
    뒤집힐 수 있다(더 오래 묵는 손님이 덜 할인받음) — 그것은 고를 새 빨간 줄(INVERTS)이 되고, 고를 때까지 저장 단계가 없다. 새 빨간 줄의
    고름이 또 다른 단을 뒤집으면 그것도 빨간 줄이 될 때까지 되풀이한다. 0 · 무료 · 30% 는 단 하나의 값으로만 정해져 고름이 바꾸지 않는다 —
    그 고름 뒤에 생기는 뒤집힘도 같은 새 빨간 줄이다."""

    def test_keeping_one_tier_and_including_another_raises_the_inverted_ladder_as_a_red_line_to_choose_on(self):
        plan = plan_change(snapshot("9002"), request(*both("2", "3"), amount="5"))
        self.assertEqual([(c.verdict, c.after) for c in plan.changes], [("OVER_30", Decimal("12")), ("OVER_30", Decimal("15"))],
                         "고르기 전: 12 < 15 라 뒤집힘이 없다(리뷰의 재현)")
        said = [Resolution("OVER_30", "include", ("9002 2",), "2박은 올려"), Resolution("OVER_30", "keep", ("9002 3",), "3박은 둬")]
        for chosen in (resolve(plan, said), resolve(plan, [Resolution("OVER_30", "include", None, "올려"), said[1]])):
            two, three = chosen.changes
            self.assertEqual((two.verdict, two.choice, two.after, two.waiting), ("INVERTS", None, Decimal("12"), True))
            self.assertEqual((three.verdict, three.choice, three.after), ("OVER_30", "keep", Decimal("10")))
            self.assertIsNone(plan_steps(chosen), "새 빨간 줄을 고를 때까지 저장하지 않는다")
        taken = resolve(plan, said + [Resolution("INVERTS", "include", ("9002 2",), "그래도 2박은 올려")])
        step, = plan_steps(taken)
        self.assertEqual([(edit.key, edit.value) for edit in step.edits], [(tier_key("9002", "2"), "12")])
        self.assertEqual((taken.changes[0].verdict, taken.changes[0].choice, taken.changes[0].said), ("INVERTS", "include", "그래도 2박은 올려"))
        self.assertEqual(plan_steps(resolve(plan, said + [Resolution("INVERTS", "keep", ("9002 2",), "그럼 둘 다 둬")])), ())

    def test_the_same_holds_after_a_choice_on_zero_or_room_free(self):
        snap = snapshot("9002")
        zero = plan_change(snap, request(*both("2", "3"), value="0"))
        self.assertEqual([c.verdict for c in zero.changes], ["ZERO", "ZERO"])
        chosen = resolve(zero, [Resolution("ZERO", "keep", ("9002 2",), "2박은 둬"), Resolution("ZERO", "include", ("9002 3",), "3박은 없애")])
        self.assertEqual([(c.verdict, c.choice) for c in chosen.changes], [("ZERO", "keep"), ("INVERTS", None)],
                         "3박 단 0% 가 2박 단 7% 보다 작아진다")
        free = plan_change(snap, request(*both("2", "3"), value="100"))
        self.assertEqual([c.verdict for c in free.changes], ["ROOM_FREE", "ROOM_FREE"])
        chosen = resolve(free, [Resolution("ROOM_FREE", "include", ("9002 2",), "2박은 무료"), Resolution("ROOM_FREE", "keep", ("9002 3",), "3박은 둬")])
        self.assertEqual([(c.verdict, c.choice) for c in chosen.changes], [("INVERTS", None), ("ROOM_FREE", "keep")])

    def test_a_tier_that_cannot_be_changed_counts_at_its_current_value(self):
        plan = resolve(plan_change(snapshot("9002"), request(*both("2", "3"), amount="-8")), [])
        self.assertEqual([(c.verdict, c.after) for c in plan.changes], [("NEGATIVE", Decimal("-1")), ("INVERTS", Decimal("2"))],
                         "2박 단은 바꿀 수 없어 7% 로 남고, 3박 단 2% 가 그보다 작아진다(고르기 전 판정은 -1 과 견줘 30% 였다)")
        self.assertIsNone(plan_steps(plan))

    def test_a_choice_on_a_new_red_line_is_judged_again_until_no_new_one_appears(self):
        def three(erp):
            erp.promotion("9002")["trigger"]["tiers"] = [{"threshold": 2, "pct": "10"}, {"threshold": 3, "pct": "30"}, {"threshold": 4, "pct": "40"}]
        plan = plan_change(snapshot("9002", change=three), request(*both("2", "3", "4"), percent="-70"))
        self.assertEqual([(c.verdict, c.after) for c in plan.changes], [("OVER_30", Decimal("3")), ("OVER_30", Decimal("9")), ("OVER_30", Decimal("12"))])
        said = [Resolution("OVER_30", "keep", ("9002 2",), "2박은 둬"), Resolution("OVER_30", "include", None, "나머지는 내려")]
        self.assertEqual([(c.verdict, c.choice) for c in resolve(plan, said).changes],
                         [("OVER_30", "keep"), ("INVERTS", None), ("OVER_30", "include")], "3박 9% < 2박 10%")
        said.append(Resolution("INVERTS", "keep", ("9002 3",), "3박도 둬"))
        self.assertEqual([(c.verdict, c.choice) for c in resolve(plan, said).changes],
                         [("OVER_30", "keep"), ("INVERTS", "keep"), ("INVERTS", None)], "3박을 30% 로 두면 4박 12% 가 그보다 작아진다")
        said.append(Resolution("INVERTS", "include", ("9002 4",), "4박은 그래도 내려"))
        done = resolve(plan, said)
        step, = plan_steps(done)
        self.assertEqual([(edit.key, edit.value) for edit in step.edits], [(tier_key("9002", "4"), "12")])

    def test_a_choice_naming_a_tier_that_never_meets_the_rule_is_refused(self):
        plan = plan_change(snapshot("9002"), request(*both("2", "3"), amount="5"))
        with self.assertRaises(Refused) as caught:
            resolve(plan, [Resolution("INVERTS", "include", ("9002 2",), "올려")])
        self.assertIn("항목이 아닙니다: 단 9002 2", str(caught.exception))


class CurrencyTest(unittest.TestCase):
    """P5 (리뷰 2 · 파이썬 10) — 정액 할인인데 호텔 통화를 읽지 못하면(목록의 할인 금액 줄에 통화가 없음) 소수가 생기는 셈은 짐작한
    자릿수(소수 둘)로 반올림하지 않고 바꿀 수 없는 단(NO_CURRENCY)으로 둔다. 소수 없는 값은 어느 통화로도 그대로라 바꾼다."""

    def snap(self):
        with mock.patch.dict(scene.DATA, {"currency": ""}):
            return snapshot("9003")

    def test_a_fixed_amount_that_would_need_a_guessed_scale_is_refused_with_a_sentence(self):
        snap = self.snap()
        self.assertEqual((snap.currency, snap.promotions["9003"].currency), ("", ""))
        for change, after in (({"percent": "7"}, "21.4"), ({"value": "25.5"}, "25.5"), ({"amount": "0.25"}, "20.25")):
            plan, tier = one(snap, "601", "9003", "0", **change)
            self.assertEqual((tier.verdict, tier.after, tier.writes), ("NO_CURRENCY", Decimal(after), False), change)
            self.assertEqual(plan_steps(plan), (), change)
        self.assertEqual(RULES.by_code["NO_CURRENCY"].label,
                         "호텔 통화를 읽지 못해(목록의 할인 금액에 통화가 없습니다) 소수가 생기는 할인 금액을 몇 자리로 맞출지 몰라 바꾸지 않습니다 — "
                         "소수 없는 금액으로 말씀해 주시면 바꿉니다")

    def test_a_whole_result_needs_no_scale_and_is_changed(self):
        snap = self.snap()
        for change, after in (({"amount": "5"}, "25"), ({"percent": "10"}, "22"), ({"value": "24"}, "24")):
            plan, tier = one(snap, "601", "9003", "0", **change)
            self.assertEqual((tier.verdict, tier.after), (None, Decimal(after)), change)
            step, = plan_steps(plan)
            self.assertEqual([edit.value for edit in step.edits], [after])

    def test_a_known_currency_still_rounds_to_its_scale(self):
        self.assertEqual(one(snapshot("9003"), "601", "9003", "0", percent="7")[1].after, Decimal("21.4"), "USD 소수 둘")
        self.assertEqual(one(snapshot("9003"), "601", "9003", "0", value="25.005")[1].after, Decimal("25.01"))
