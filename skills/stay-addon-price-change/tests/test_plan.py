"""바꾸기 계산(X2 · X3) — 금액 · 퍼센트 · 새 값 · 비우기, 통화 자릿수, 적용할 수 없는 줄과 빨간 줄, 고름, 저장 단계가 공급 원가를
지키는지, 목록과 편집 창이 다른 줄.

    python3 -m unittest discover -s tests
"""

import unittest
from decimal import Decimal

import addon_scene as scene
from addon_model import Line, LineKey, Listed, ModelError, Snapshot, decode_request, line_of
from addon_pages import render_preview
from addon_plan import LineStep, PlanError, counts, plan_change, plan_steps, preview_rows, resolve
from change_core.answers import attach_bodies
from change_core.chrome import page_text
from change_core.items import Refused
from change_core.rules import Resolution

D = Decimal


def snapshot(*items):
    erp = scene.Erp(list(items))
    lines = {}
    for item in items:
        answer, = attach_bodies(erp.read_line({"hotel": scene.HOTEL, "addon": item["addon"], "line": item["line"]}))
        line = line_of(answer)
        lines[line.key] = line
    return Snapshot(scene.HOTEL["name"], scene.HOTEL["id"], "2026-11-21T10:00:00+09:00", tuple(lines), lines)


def request(field="sell", lines=None, **how):
    return decode_request(dict(kind="addon_change", hotel=scene.HOTEL, field=field, sentence="말", **how,
                               **({"lines": lines} if lines else {"all": True})))


def plan(snap, **how):
    return plan_change(snap, request(**how))


def moves(result):
    """줄 번호 → (후 판매가, 후 공급 원가, 판정). 셈하지 못한 줄은 후 값이 없다."""
    return {change.key.line: (*((change.after["sell"], change.after["supply"]) if change.after else (None, None)), change.verdict)
            for change in result.changes}


class ArithmeticTest(unittest.TestCase):
    def test_amount_percent_and_new_value_round_to_the_currency(self):
        snap = snapshot(scene.line("201", "조식", "1", "a", "33.33", "20.00"), scene.line("201", "조식", "2", "b", "12.25", ""))
        self.assertEqual(moves(plan(snap, percent="10")), {"1": (D("36.66"), D("20.00"), None), "2": (D("13.48"), None, None)})
        self.assertEqual(moves(plan(snap, amount="-1.5"))["1"], (D("31.83"), D("20.00"), None))
        self.assertEqual(moves(plan(snap, value="35"))["1"][0], D("35.00"))

    def test_a_zero_decimal_currency_keeps_whole_numbers(self):
        snap = snapshot(scene.line("201", "조식", "1", "a", "45000", "40000", currency="KRW"))
        self.assertEqual(snap.currency, "KRW")
        self.assertEqual(moves(plan(snap, percent="3.3"))["1"][0], D("46485"))
        self.assertEqual(moves(plan(snap, amount="5000"))["1"][0], D("50000"))


class RuleTest(unittest.TestCase):
    def test_a_sell_price_of_zero_or_below_cannot_be_applied_but_a_free_lines_cost_can_change(self):
        snap = snapshot(scene.line("201", "조식", "1", "a", "20.00", "15.00"), scene.line("202", "픽업", "2", "free", "0.00", "5.00"))
        result = plan(snap, value="0", lines=[{"addon": "201", "line": "1"}])
        self.assertEqual(result.changes[0].verdict, "NOT_POSITIVE")
        self.assertEqual(plan_steps(result), ())
        self.assertEqual(moves(plan(snap, amount="-25"))["1"][2], "NOT_POSITIVE")
        free = plan(snap, field="supply", amount="1", lines=[{"addon": "202", "line": "2"}])
        self.assertEqual(free.changes[0].verdict, "BELOW_COST", "무료 줄의 원가 바꾸기는 막지 않는다 — 원가보다 싼 줄이라 고르게 한다")
        taken = resolve(free, [Resolution("BELOW_COST", "include")])
        self.assertEqual(taken.changes[0].writes, {"supply": D("6.00")})

    def test_below_cost_and_over_thirty_percent_are_red_lines_the_user_chooses_per_line(self):
        snap = snapshot(scene.line("201", "조식", "1", "a", "20.00", "15.00"), scene.line("201", "조식", "2", "b", "100.00", "50.00"))
        result = plan(snap, amount="-6")
        self.assertEqual({key: verdict for key, (_s, _c, verdict) in moves(result).items()}, {"1": "BELOW_COST", "2": None})
        self.assertIsNone(plan_steps(result), "고르지 않은 빨간 줄이 있으면 저장 단계가 없다")
        self.assertEqual(counts(result)["red"], 1)
        kept = resolve(result, [Resolution("BELOW_COST", "keep", ("1",))])
        self.assertEqual([step.line for step in plan_steps(kept)], ["2"])
        self.assertEqual(moves(kept)["1"][:2], (D("20.00"), D("15.00")), "안 바꾸기로 고른 줄은 후 값이 전 값이다")
        found = counts(kept)
        self.assertEqual((found["will_change"], found["unchanged"], found["blocked"], found["red"], found["chosen"]), (1, 1, 0, 0, 1))
        rows = {(row.item_key, row.field): row for row in preview_rows(kept)}
        self.assertTrue(all(row.after is None and row.action is None for (key, _f), row in rows.items() if '"1"' in key))
        taken = resolve(result, [Resolution("BELOW_COST", "include")])
        self.assertEqual([step.line for step in plan_steps(taken)], ["1", "2"])
        self.assertEqual(moves(plan(snap, percent="30"))["2"][2], None, "30% 는 넘지 않았다")
        self.assertEqual(moves(plan(snap, percent="30.01"))["2"][2], "OVER_30")
        with self.assertRaises(Refused):
            resolve(result, [Resolution("BELOW_COST", "include", ("2",))])
        with self.assertRaises(Refused):
            resolve(result, [Resolution("NOT_POSITIVE", "include")])

    def test_a_relative_change_to_a_missing_cost_cannot_be_computed_and_a_new_value_can(self):
        snap = snapshot(scene.line("201", "조식", "1", "a", "20.00", ""))
        self.assertEqual(moves(plan(snap, field="supply", percent="5"))["1"][2], "NO_SUPPLY")
        self.assertEqual(moves(plan(snap, field="supply", value="9"))["1"][:2], (D("20.00"), D("9.00")))

    def test_lines_whose_list_and_window_disagree_or_whose_amount_records_are_hidden_are_never_saved(self):
        hidden = scene.line("202", "픽업", "3", "편도", "40.00", "", hidden=True)
        differ = scene.line("203", "베드", "4", "1개", "30.00", "25.00", listed=["판매가: 30.00 USD"])
        same = scene.line("203", "베드", "5", "2개", "50.00", "", listed=["판매가: 50.00 USD", "판매가: 70000 KRW"])
        result = plan(snapshot(hidden, differ, same), percent="1")
        self.assertEqual({key: verdict for key, (_s, _c, verdict) in moves(result).items()},
                         {"3": "HIDDEN", "4": "DIFFER", "5": None}, "다른 통화의 금액 줄은 견주지 않는다")
        self.assertEqual([step.line for step in plan_steps(result)], ["5"])


class StepTest(unittest.TestCase):
    def test_the_save_sends_every_field_as_read_and_carries_the_supply_cost(self):
        snap = snapshot(scene.line("201", "조식", "1", "a", "20.00", "15.00", season="41", description="뷔페"))
        step, = plan_steps(plan(snap, percent="10"))
        self.assertEqual(step.set, {"price": "22.00"})
        self.assertEqual(dict(step.sent()), {"name": "a", "price": "22.00", "net_amount": "15.00", "season": "41", "date": "",
                                             "rate_plan": "", "description": "뷔페", "scope_rate_plan_mode": "0",
                                             "scope_room_mode": "0"})
        self.assertEqual([(write.field, write.after) for write in step.writes()], [("sell", D("22.00"))])

    def test_a_step_refuses_to_blank_the_cost_or_touch_any_other_field(self):
        form = (("name", "a"), ("price", "20.00"), ("net_amount", "15.00"))
        with self.assertRaisesRegex(PlanError, "공급 원가가 빈 채로"):
            LineStep("201", "1", "a", form, {"net_amount": " "})
        with self.assertRaisesRegex(PlanError, r"공급 원가\(net_amount\)만"):
            LineStep("201", "1", "a", form, {"name": "b"})
        cleared = LineStep("201", "1", "a", form, {"net_amount": ""})
        self.assertEqual([(write.field, write.after) for write in cleared.writes()], [("supply", None)])

    def test_clearing_the_cost_is_a_clear_in_the_ledger_rows(self):
        snap = snapshot(scene.line("201", "조식", "1", "a", "20.00", "15.00"))
        rows = {row.field: row for row in preview_rows(plan(snap, field="supply", clear=True))}
        self.assertEqual((rows["supply"].action, rows["supply"].after, rows["sell"].action), ("clear", None, None))


class SentFieldsTest(unittest.TestCase):
    def test_the_preview_shows_each_scope_axis_with_its_mode_and_how_many_targets_are_picked(self):
        listed = Listed(LineKey("204", "305"), "엑스트라베드", "엑스트라베드 1개", "33.00 USD", ("판매가: 33.00 USD", "공급 원가: 27.50 USD"),
                        "연말 시즌", offer="데모 연말 오퍼")
        form = (("name", "엑스트라베드 1개"), ("price", "33.00"), ("net_amount", "27.50"), ("season", "43"), ("date", ""),
                ("rate_plan", ""), ("description", ""), ("scope_rate_plan_mode", "2"), ("scope_rate_plan_include", "53"),
                ("scope_room_mode", "0"))
        labels = {"season": "연말 시즌", "rate_plan": "---------", "scope_rate_plan_mode": "지정한 대상만",
                  "scope_room_mode": "기존 범위 그대로"}
        line = Line(listed, form, labels)
        snap = Snapshot(scene.HOTEL["name"], scene.HOTEL["id"], "2026-11-21T10:00:00+09:00", (line.key,), {line.key: line})
        result = plan_change(snap, request(percent="1"))
        text = page_text(render_preview(result, 1, plan_steps(result)))
        self.assertIn("시즌 연말 시즌 · 날짜 비어 있음 · 요금제 비어 있음 · 설명 비어 있음 · "
                      "적용 범위 요금제 지정한 대상만(포함 1개) · 객실 기존 범위 그대로", text)


class RequestTest(unittest.TestCase):
    def test_a_request_names_one_way_to_choose_lines_one_field_and_one_way_to_change(self):
        with self.assertRaisesRegex(ModelError, "하나만"):
            decode_request(dict(kind="addon_change", hotel=scene.HOTEL, all=True, amount="1", percent="2", sentence="말"))
        with self.assertRaisesRegex(ModelError, "판매가는 비울 수 없습니다"):
            decode_request(dict(kind="addon_change", hotel=scene.HOTEL, all=True, clear=True, sentence="말"))
        with self.assertRaisesRegex(ModelError, "가운데 하나로"):
            decode_request(dict(kind="addon_change", hotel=scene.HOTEL, all=True, addons=["201"], amount="1", sentence="말"))
        self.assertEqual(request(amount="-5000").describe(), "판매가 -5000")
        self.assertEqual(request(field="supply", percent="3").describe(), "공급 원가 +3%")

    def test_a_zero_written_as_a_json_number_is_a_value(self):
        self.assertEqual(request(field="supply", value=0).figure, 0, "0 == False 여도 0 은 값이다")
        self.assertEqual(request(amount=0).how, "amount")
        with self.assertRaisesRegex(ModelError, "하나만"):
            request(amount=0, percent="2")
        self.assertEqual(request(value="5", clear=False).how, "value", "clear: false 는 적지 않은 것이다")

    def test_a_plan_refuses_a_reading_of_another_hotel_or_one_that_did_not_read_the_named_lines(self):
        snap = snapshot(scene.line("201", "조식", "1", "a", "20.00", "15.00"))
        other = Snapshot("다른 호텔", "9", snap.read_at, snap.asked, snap.lines)
        with self.assertRaisesRegex(PlanError, "다른 호텔"):
            plan_change(other, request(amount="1"))
        with self.assertRaisesRegex(PlanError, "읽지 않은 줄"):
            plan(snap, amount="1", lines=[{"addon": "201", "line": "2"}])


if __name__ == "__main__":
    unittest.main()
