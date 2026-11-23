"""계산(C2 · C3) — 셈은 명령이 하고, 판정은 바꾼 결과로 한다. 부과금의 모양(방식 · 시간대 · 연령별 · 현장 결제)은 바꾸지 않는다.

    python3 -m unittest discover -s tests
"""

import unittest
from decimal import Decimal

import charge_scene as scene
from charge_model import Charge, ModelError, Place, Snapshot, charge_of, decode_request, snapshot_items
from charge_plan import ChargeStep, Edit, PlanError, counts, plan_change, plan_steps, resolve, step_call
from change_core.answers import attach_bodies
from change_core.rules import Resolution
from change_core.window import with_values

OFFER_OF = {charge["id"]: offer["id"] for offer in scene.DATA["offers"] for charge in offer["charges"]}


def read(erp: scene.Erp, *charge_ids: str) -> Snapshot:
    charges = {}
    for charge_id in charge_ids:
        call = {"hotel": scene.HOTEL, "offer": OFFER_OF[charge_id], "charge": charge_id}
        charge = charge_of(attach_bodies(erp.read_charge(call))[0])
        charges[charge.id] = charge
    return Snapshot(scene.HOTEL["name"], scene.HOTEL["id"], "2026-11-21T10:00:00+09:00",
                    tuple((OFFER_OF[c], c) for c in charge_ids), charges)


def request(*amounts, **change):
    return decode_request(dict(kind="charge_change", hotel=scene.HOTEL, amounts=list(amounts), sentence="바꿔줘", **change))


def place(charge, field, time=None, age=None):
    item = {"offer": OFFER_OF[charge], "charge": charge, "field": field}
    if time:
        item["time"] = time
    if age:
        item["age"] = age
    return item


class RulesTest(unittest.TestCase):
    def setUp(self):
        self.erp = scene.Erp()
        self.snapshot = read(self.erp, "701", "702", "703", "704", "705", "706")

    def verdict(self, target, **change):
        plan = plan_change(self.snapshot, request(target, **change))
        only, = plan.changes
        return only.verdict, only.before, only.after

    def test_the_command_does_the_arithmetic_by_amount_percent_or_new_value_and_rounds_like_the_erp(self):
        self.assertEqual(self.verdict(place("701", "pct", "14:01-18:00"), value="60")[1:], (Decimal("50.00"), Decimal("60.00")))
        self.assertEqual(self.verdict(place("703", "amount"), amount="5.555")[2], Decimal("95.56"))
        self.assertEqual(self.verdict(place("705", "amount", age="CHD"), percent="10")[2], Decimal("55.00"))
        self.assertEqual(self.verdict(place("702", "pct", "07:00-12:00"), percent="15")[2], Decimal("34.50"))

    def test_an_age_band_may_be_named_as_the_screen_shows_it_and_a_time_band_with_a_tilde(self):
        plan = plan_change(self.snapshot, request(place("705", "amount", age="소아"), place("701", "pct", "14:01 ~ 18:00"), value="52"))
        self.assertEqual([change.id for change in plan.changes], ["705 CHD amount", "701 14:01-18:00 pct"])
        with self.assertRaises(PlanError):
            plan_change(self.snapshot, request(place("705", "amount", age="소아"), place("705", "amount", age="CHD"), value="1"))

    def test_an_amount_the_charge_shape_does_not_use_cannot_be_applied(self):
        for amount in (place("701", "pct"), place("701", "amount"), place("703", "pct"), place("703", "onsite"),
                       place("701", "amount", "14:01-18:00"), place("701", "pct", "12:01-14:00")):
            self.assertEqual(self.verdict(amount, value="40")[0], "NOT_USED", amount)

    def test_an_empty_amount_is_never_filled(self):
        self.assertEqual(self.verdict(place("706", "amount"), value="10")[0], "UNDECIDED", "금액이 「미정」인 부과금")
        self.assertEqual(self.verdict(place("706", "amount"), amount="5")[2], None, "셈할 바탕이 없다")

    def test_a_negative_result_and_a_percentage_outside_0_to_100_cannot_be_applied(self):
        self.assertEqual(self.verdict(place("703", "amount"), amount="-100")[0], "NEGATIVE")
        self.assertEqual(self.verdict(place("702", "pct", "00:00-06:59"), amount="10")[0], "PCT_RANGE")
        self.assertEqual(self.verdict(place("702", "pct", "00:00-06:59"), value="100")[0], None, "100% 는 된다(그대로)")

    def test_a_value_the_form_would_refuse_for_the_charge_shape_cannot_be_applied(self):
        self.assertEqual(self.verdict(place("704", "amount"), value="5")[0], "FORM_REFUSES", "현장 결제 부과금의 온라인 금액은 0")
        self.assertEqual(self.verdict(place("703", "amount"), value="20000000000")[0], "FORM_REFUSES", "정수 10자리까지")

    def test_more_than_30_percent_is_a_red_line_with_two_choices_and_zero_is_allowed_and_counted_as_free(self):
        plan = plan_change(self.snapshot, request(place("703", "amount"), place("705", "amount", age="CHD"), value="0"))
        self.assertEqual([c.verdict for c in plan.changes], ["OVER_30", "OVER_30"])
        self.assertIsNone(plan_steps(plan))
        chosen = resolve(plan, [Resolution("OVER_30", "include", ("703 amount",)), Resolution("OVER_30", "keep", ("705 CHD amount",))])
        self.assertEqual((counts(chosen)["free"], counts(chosen)["will_change"], counts(chosen)["unchanged"]), (1, 1, 1))
        step, = plan_steps(chosen)
        self.assertEqual([(e.name, e.value) for e in step.edits], [("amount", "0.00")])
        with self.assertRaises(ValueError):
            resolve(plan, [Resolution("NOT_USED", "include")])

    def test_a_plan_with_nothing_to_save_has_no_steps(self):
        plan = plan_change(self.snapshot, request(place("703", "amount"), value="90"))
        self.assertEqual((plan_steps(plan), counts(plan)["unchanged"]), ((), 1))

    def test_the_request_names_amounts_only_and_never_empties_one(self):
        for bad in (dict(clear=True), dict(value="-1"), dict()):
            with self.assertRaises(ModelError, msg=bad):
                request(place("703", "amount"), **bad)
        with self.assertRaises(ModelError):
            request({"offer": "601", "charge": "703", "field": "kind"}, value="1")
        with self.assertRaises(ModelError):
            plan_change(self.snapshot, request(place("701", "pct", "15:00-18:00"), value="1"))
        with self.assertRaises(PlanError):
            plan_change(self.snapshot, request({"offer": "602", "charge": "703", "field": "amount"}, value="1"))

    def test_a_zero_written_as_a_json_number_is_a_value(self):
        free = request(place("703", "amount"), value=0)
        self.assertEqual((free.how, free.figure), ("value", 0), "무료면 value 0 — 0 == False 여도 0 은 값이다")
        with self.assertRaisesRegex(ModelError, "하나만"):
            request(place("703", "amount"), amount=0, percent="2")


class StepTest(unittest.TestCase):
    """C3 · C4 — 저장 단계는 금액 칸만, 짚은 칸만 바꾸고 나머지 칸(금액의 뜻 포함)은 창이 보인 그대로 보낸다."""

    def setUp(self):
        self.snapshot = read(scene.Erp(), "701", "705")
        self.late: Charge = self.snapshot.charges["701"]

    def test_a_time_band_amount_the_plan_did_not_touch_is_sent_as_read(self):
        step, = plan_steps(plan_change(self.snapshot, request(place("701", "pct", "14:01-18:00"), value="60")))
        self.assertEqual([(e.name, e.nth, e.value) for e in step.edits], [("tiers_pct", 1, "60.00")])
        sent = step.sent()
        self.assertEqual([v for k, v in sent if k == "tiers_pct"], ["", "60.00"])
        self.assertEqual([v for k, v in sent if k == "tiers_amount"], ["0.00", ""])
        self.assertEqual([pair for pair in sent if pair[0] != "tiers_pct"], [pair for pair in self.late.form if pair[0] != "tiers_pct"])

    def test_mode_fields_go_back_as_the_window_presented_them(self):
        step, = plan_steps(plan_change(self.snapshot, request(place("705", "amount", age="CHD"), percent="10")))
        sent = dict(step.sent())
        self.assertEqual((sent["amount_mode"], sent["pct_mode"]), ("set", "blank"))

    def test_a_step_refuses_anything_but_an_amount_a_blank_an_empty_value_or_a_place_twice(self):
        key = Place("701", "time", "14:01-18:00", "pct").key
        good = Edit(key, "pct", "tiers_pct", 1, "60.00")
        ChargeStep("601", "701", self.late.name, "라벨", self.late.form, (good,))
        for bad in (Edit(key, "pct", "amount_mode", 0, "blank"), Edit(key, "pct", "pct_mode", 0, "blank"),
                    Edit(key, "pct", "tiers_time_from", 0, "13:00"), Edit(key, "pct", "kind", 0, "9"),
                    Edit(key, "pct", "tiers_pct", 0, "10"),          # 빈 칸(정액 줄의 정률)을 채운다
                    Edit(key, "pct", "tiers_pct", 1, ""),            # 비운다
                    Edit(key, "pct", "tiers_pct", 2, "10"),          # 없는 줄
                    Edit(Place("705", "main", "", "amount").key, "amount", "amount", 0, "1")):   # 다른 부과금의 칸
            with self.assertRaises(PlanError, msg=bad):
                ChargeStep("601", "701", self.late.name, "라벨", self.late.form, (bad,))
        with self.assertRaises(PlanError):
            ChargeStep("601", "701", self.late.name, "라벨", self.late.form, (good, good))

    def test_the_call_carries_the_form_as_read_and_the_places_by_name_and_position(self):
        step, = plan_steps(plan_change(self.snapshot, request(place("701", "pct", "14:01-18:00"), value="60")))
        call = step_call(3, "데모 호텔", "1", step)
        self.assertEqual(call["payload"]["set"], [["tiers_pct", 1, "60.00"]])
        self.assertEqual(call["payload"]["form"], [list(pair) for pair in self.late.form])
        self.assertEqual((call["op"], call["payload"]["offer"], call["payload"]["charge"], call["payload"]["name"]),
                         ("applyCharge", "601", "701", self.late.name))


class ItemsTest(unittest.TestCase):
    """C6 — 장부 항목 키는 바뀌지 않는 것(부과금 번호 · 시각 · 구간 코드)으로 정하고, 금액 아닌 칸은 부과금 항목의 딸린 칸이다."""

    def test_item_keys_for_the_charge_its_time_bands_and_its_age_rates(self):
        items = snapshot_items(read(scene.Erp(), "701", "705"))
        self.assertEqual(sorted(key for _kind, key in items), sorted([
            '{"charge":"701"}', '{"charge":"701","time":"12:01-14:00"}', '{"charge":"701","time":"14:01-18:00"}',
            '{"charge":"705"}', '{"age":"INF","charge":"705"}', '{"age":"CHD","charge":"705"}']))
        main = items[("charge", '{"charge":"701"}')]
        self.assertEqual(main.others["form.tiers_time_from"], "12:01\n14:01")
        self.assertNotIn("form.tiers_pct", main.others, "금액 칸은 딸린 칸이 아니라 필드다")
        child = items[("charge", '{"age":"CHD","charge":"705"}')]
        self.assertEqual(dict(child.fields), {"amount": Decimal("50.00"), "onsite": None})


class WindowStepTest(unittest.TestCase):
    """공유 걸음(change_core.window.with_values) — 같은 이름의 칸이 여럿이면 몇 번째인지로 짚는다."""

    def test_with_values_changes_only_the_named_occurrence_and_refuses_one_the_window_lacks(self):
        form = (("tiers_pct", "1"), ("name", "x"), ("tiers_pct", "2"))
        self.assertEqual(with_values(form, {("tiers_pct", 1): "9"}), (("tiers_pct", "1"), ("name", "x"), ("tiers_pct", "9")))
        with self.assertRaises(ValueError):
            with_values(form, {("tiers_pct", 2): "9"})


if __name__ == "__main__":
    unittest.main()
