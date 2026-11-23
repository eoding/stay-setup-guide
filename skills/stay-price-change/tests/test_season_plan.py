"""시즌 다시 채우기의 미리보기 계산 — 바구니 · 규칙 · 고름(「그 날은 빼고 채움」은 다시 셈) · 저장 단계의 창 모양(form · want).

창은 칸 하나를 뺄 수 없다: 고름은 저장 · 규칙마다이고, 「그 칸은 안 바꿈」은 없다. 「이번에 고르지 않은 인원·요금제 가격 지우기」는
어떤 경우에도 켜지 않는다.
"""

import sys
import unittest
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import season_scene as scene  # noqa: E402
from price_model import CellKey, CellValue  # noqa: E402
from season_expand import NO_COMBOS  # noqa: E402
from season_pages import rollback_notes  # noqa: E402
from price_season import (  # noqa: E402
    SeasonChoice, SeasonError, counts, opened_form, plan_season, preview_rows, rule_label, rule_said, season_steps, want_form,
    window_of,
)

DAYS = scene.CASES["hotel"]["season"]
DELUXE = ("디럭스", "조식 포함")


def cell(sell, state="open", listed=None, supply=None):
    return CellValue(D(sell), None if listed is None else D(listed), None if supply is None else D(supply), state)


def cells(prices, key="A2", nights=1, pair=DELUXE):
    """날 → 판매가(디럭스 · 조식 포함 · A2 · 1박 기본)."""
    return {CellKey(pair[0], pair[1], day, key, nights): cell(sell) for day, sell in prices.items()}


def snap(cell_map, pairs=(DELUXE,), dates=DAYS, **over):
    base = scene.snapshot((), pairs=pairs, dates=dates, **over)
    return replace(base, cells={**base.cells, **cell_map})


def plan(cell_map, choices=(), window=None, edited=None, pairs=(DELUXE,), reserved=(), **save):
    fields = dict(pairs=[list(pair) for pair in pairs], price="180", occupancy_keys="A2", overwrite=True,
                  dates=[day for day in DAYS if day != "2026-12-03"])
    fields.update(save)
    return plan_season(snap(cell_map, pairs=pairs, reserved=reserved), window or scene.window(), scene.fill_of(scene.save_of(fields)),
                       choices, edited)


class BucketsTest(unittest.TestCase):
    def test_same_value_overwrites_are_counted_not_listed_and_changed_cells_keep_their_marks(self):
        moved = plan(cells({"2026-12-01": "180", "2026-12-02": "170"}), reserved={("디럭스", "2026-12-02")}).saves[0]
        self.assertEqual(moved.same, 1)
        self.assertEqual([(change.key.date, change.marks) for change in moved.changes if change.before.state != "missing"],
                         [("2026-12-02", ("reserved",))], "값이 둘뿐이면(180 · 170) 가장 흔한 값이 없어 따로 넣은 칸으로 보지 않는다")
        self.assertEqual(moved.counts.updated, 2, "ERP 는 같은 값으로 덮은 칸도 「덮어쓴」에 센다")

    def test_looks_edited_only_against_a_single_most_common_value_and_never_on_a_tie(self):
        odd = plan(cells({"2026-12-01": "170", "2026-12-02": "170", "2026-12-04": "175"})).saves[0]
        self.assertEqual([change.key.date for change in odd.changes if "looks_edited" in change.marks], ["2026-12-04"])
        tie = plan(cells({"2026-12-01": "170", "2026-12-02": "175"})).saves[0]
        self.assertEqual([change.key.date for change in tie.changes if "looks_edited" in change.marks], [],
                         "가장 흔한 값이 둘이면 누가 따로 넣은 것인지 정하지 않는다")

    def test_helper_edited_names_the_ledger_number_and_is_certain(self):
        key = CellKey(*DELUXE, "2026-12-04", "A2", 1)
        edited = plan(cells({"2026-12-01": "170", "2026-12-02": "170", "2026-12-04": "175"}), edited={key: 7}).saves[0]
        marks = next(change.marks for change in edited.changes if change.key == key)
        self.assertIn("helper_edited:7", marks)
        self.assertNotIn("looks_edited", marks, "장부가 넣은 칸은 짐작하지 않는다")

    def test_other_season_days_and_left_old_and_no_sale_days(self):
        window = scene.window(others=[("8800", "Normal", ("2026-12-01",))])
        left = cells({"2026-12-01": "200"}, key="A3")
        done = plan({**cells({"2026-12-01": "170"}), **left}, window=window).saves[0]
        self.assertIn("other_season:8800", next(change.marks for change in done.changes if change.key.date == "2026-12-01"))
        self.assertEqual(done.left_old, tuple(left))
        with_no_sale = plan(cells({"2026-12-01": "170"}), dates=["2026-12-02", "2026-12-03"]).saves[0]
        self.assertEqual((with_no_sale.no_sale, with_no_sale.counts.skipped), ((("디럭스", "2026-12-03"),), 1))

    def test_overwrite_off_leaves_existing_cells_untouched(self):
        done = plan(cells({"2026-12-01": "170"}), overwrite=False).saves[0]
        self.assertEqual((done.untouched, [change.key.date for change in done.changes]),
                         (1, ["2026-12-02", "2026-12-04", "2026-12-05"]))

    def test_auto_child_keys_in_a_room_whose_combos_are_unknown_are_marked_and_may_be_left_out(self):
        window = scene.window(bands=[{"code": "CHD", "basis": "flat", "value": "20"}])
        window = replace(window, combos={**window.combos, "디럭스": None})
        done = plan({}, window=window, dates=["2026-12-01"]).saves[0]
        marked = {change.key.occupancy: "combo_unknown" in change.marks for change in done.changes}
        self.assertEqual(marked, {"A2": False, "A2C1_CHD": True})
        self.assertEqual((done.counts.created, done.counts.maybe_created), (2, 1))


class SeasonWordsTest(unittest.TestCase):
    """W7 (시운전 12) — 시즌 빨간 줄은 도우미가 그대로 하는 말(`rule_said`)이 있고, 채우기 전부터 공급 원가보다 쌌던 칸은 「싸집니다」가
    아니라 그렇게 부른다. 창의 객실 타입이 모두 「조합 제한 없음」이면 객실 이름을 못 맞춰도 조합으로 빠질 칸이 없다(짐작이 아니다)."""

    def test_a_season_red_line_on_cells_already_below_cost_has_a_true_label_and_a_sentence_to_say(self):
        below = {CellKey("디럭스", "조식 포함", day, "A2", 1): cell("50", supply="52") for day in ("2026-12-01", "2026-12-02")}
        done = plan(below, price="51", dates=["2026-12-01", "2026-12-02"]).saves[0]
        self.assertEqual(rule_label(done, "BELOW_COST"), "이미 공급 원가보다 쌉니다 — 이번에도 그대로")
        self.assertEqual(rule_said(done, "BELOW_COST", "USD"),
                         "1번째 저장의 2칸(2일) — 이미 공급 원가보다 쌉니다 — 이번에도 그대로. 예: 12/1 화 · 디럭스 · 조식 포함 · 성인 2 · "
                         "1박 이상 — 판매가 50.00 → 51.00(공급 원가 52.00). 창은 칸 하나를 뺄 수 없어 이 저장에서 고를 것은 「이대로 채움」 · "
                         "「그 날은 빼고 채움」(남는 날이 없어 이 저장을 통째로 뺌) · 「요청을 고침」입니다. 어떻게 할까요?")
        fresh = plan({key: cell("60", supply="52") for key in below}, price="51", dates=["2026-12-01", "2026-12-02"]).saves[0]
        self.assertEqual(rule_label(fresh, "BELOW_COST"), "공급 원가보다 싸집니다")

    def test_a_window_whose_room_types_all_have_no_limit_leaves_nothing_out_even_when_names_differ(self):
        window = scene.window(bands=[{"code": "CHD", "basis": "flat", "value": "20"}])
        body = dict(scene.answer_body(window, room_types=[{"name": "Deluxe", "combos": NO_COMBOS}]), hotel={"id": scene.HOTEL_ID, "name": scene.HOTEL})
        unlimited = window_of(body, {})
        self.assertEqual(set(unlimited.combos.values()), {NO_COMBOS})
        done = plan({}, window=unlimited, dates=["2026-12-01"]).saves[0]
        self.assertFalse(any("combo_unknown" in change.marks for change in done.changes))
        limited = window_of(dict(body, roomTypes=[{"name": "Deluxe", "combos": "A2"}]), {})
        self.assertEqual(set(limited.combos.values()), {None}, "제한이 있는 타입이 있으면 이름을 못 맞춘 객실은 모른다(짐작)")

    def test_the_undo_preview_names_the_child_field_in_plain_words(self):
        page = rollback_notes({"season": "Peak", "form": [["price", ""], ["child_extra_CHD", "8.46"]]})
        self.assertIn("<dt>아동 추가 금액 CHD</dt><dd>8.46</dd>", page)
        self.assertNotIn("child_extra_CHD", page)


class RulesTest(unittest.TestCase):
    def test_new_row_when_no_keys_are_typed_while_adult_rows_exist(self):
        done = plan(cells({"2026-12-01": "170"}), occupancy_keys="").saves[0]
        self.assertTrue(done.hits["NEW_ROW"])
        self.assertTrue(all(key.occupancy == "" for key in done.hits["NEW_ROW"]))

    def test_whole_unit_fraction_blocks_a_percent_that_makes_cents_in_won(self):
        won = plan_season(scene.snapshot((), pairs=[DELUXE, ("디럭스", "룸온리")], currency="KRW"), scene.window(),
                          scene.fill_of(scene.save_of({"pairs": [list(DELUXE), ["디럭스", "룸온리"]], "price": "80001",
                                                       "occupancy_keys": "A2", "plan_adjust": "-5%", "dates": ["2026-12-01"]}),
                                        currency="KRW")).saves[0]
        self.assertEqual({key.rate_plan for key in won.hits["WHOLE_UNIT_FRACTION"]}, {"룸온리"})
        self.assertIn("WHOLE_UNIT_FRACTION", won.waiting())

    def test_erp_refusal_blocks_the_whole_save_with_the_erp_sentence_and_offers_no_choice(self):
        done = plan({}, plan_adjust="8").saves[0]
        self.assertIn("부호를 붙여", done.refused)
        self.assertEqual(done.waiting(), ["ERP_REFUSES"])
        with self.assertRaises(SeasonError):
            plan({}, [SeasonChoice(1, "ERP_REFUSES", "include", "그냥 해")], plan_adjust="8")

    def test_above_one_night_catches_an_old_tier_left_above_a_lowered_one_night(self):
        old = {**cells({"2026-12-01": "170"}), **cells({"2026-12-01": "165"}, nights=3)}
        done = plan(old, price="150", dates=["2026-12-01"]).saves[0]
        self.assertEqual(done.hits["ABOVE_ONE_NIGHT"], (CellKey(*DELUXE, "2026-12-01", "A2", 1),))

    def test_over_30_and_above_list_on_the_predicted_value(self):
        priced = {CellKey(*DELUXE, "2026-12-01", "A2", 1): cell("100", listed="150")}
        done = plan(priced, price="160", dates=["2026-12-01"]).saves[0]
        self.assertEqual(set(done.hits), {"OVER_30", "ABOVE_LIST"})


class ChoicesTest(unittest.TestCase):
    def test_a_cell_cannot_be_kept_on_its_own(self):
        with self.assertRaises(SeasonError) as caught:
            plan(cells({"2026-12-01": "100"}), [SeasonChoice(1, "OVER_30", "keep", "그 칸은 두고")])
        self.assertIn("include · exclude_dates", str(caught.exception))

    def test_exclude_dates_drops_the_hit_days_recomputes_and_lists_them(self):
        old = cells({"2026-12-01": "100", "2026-12-02": "175"})
        done = plan(old, [SeasonChoice(1, "OVER_30", "exclude_dates", "그 날은 빼고")]).saves[0]
        self.assertEqual((done.excluded, done.save.dates), (("2026-12-01",), ("2026-12-02", "2026-12-04", "2026-12-05")))
        self.assertNotIn("OVER_30", done.hits)
        self.assertEqual(done.waiting(), [])

    def test_excluding_every_date_drops_the_save(self):
        old = cells({day: "100" for day in DAYS if day != "2026-12-03"})
        whole = plan(old, [SeasonChoice(1, "OVER_30", "exclude_dates", "다 빼")])
        self.assertTrue(whole.saves[0].dropped)
        self.assertEqual((whole.live, counts(whole)["dropped"]), ((), 1))

    def test_red_lines_wait_for_a_choice_and_rows_carry_no_writes_until_then(self):
        waiting = plan(cells({"2026-12-01": "100"}))
        self.assertEqual(waiting.saves[0].waiting(), ["OVER_30"])
        self.assertIsNone(season_steps(waiting))
        self.assertFalse(any(row.action for row in preview_rows(waiting)))
        chosen = plan(cells({"2026-12-01": "100"}), [SeasonChoice(1, "OVER_30", "include", "괜찮아 그대로")])
        self.assertTrue(chosen.ready)
        self.assertTrue(any(row.action and row.choice == "include" and row.said == "괜찮아 그대로" for row in preview_rows(chosen)))

    def test_a_choice_no_cell_used_is_reported_unused(self):
        done = plan(cells({"2026-12-01": "175"}), [SeasonChoice(1, "OVER_30", "include", "그대로")])
        self.assertEqual([choice.rule for choice in done.unused], ["OVER_30"])


class WindowFormTest(unittest.TestCase):
    def test_want_follows_the_window_order_ticks_only_chosen_boxes_and_never_the_delete_box(self):
        window = scene.window()
        window = replace(window, form=window.form + (("stale_cleanup", "on"),))
        want = want_form(window, scene.save_of({"pairs": [list(DELUXE), ["디럭스", "룸온리"]], "price": "180", "occupancy_keys": "A2,A3",
                                                "occupancy_adjust": "A3:+20", "overwrite": True}))
        self.assertEqual([name for name, _value in want],
                         ["date_selection_0", "date_selection_1", "price", "original_price", "net_price", "rooms", "rate_plans",
                          "rate_plans", "plan_adjust", "occupancy_keys", "occupancy_adjust", "los_prices", "overwrite"])
        self.assertEqual([value for name, value in want if name in ("rooms", "rate_plans")], ["301", "9001", "9002"])
        self.assertNotIn("stale_cleanup", [name for name, _value in want], "지우기 칸은 창이 켜진 채 열려도 켜지 않는다")
        self.assertEqual(want[0], ["date_selection_0", "2026-12-01 ~ 2026-12-05"], "dates 가 없으면 창이 연 날짜 그대로")

    def test_the_next_step_opens_with_the_last_inputs_the_previous_step_typed(self):
        window = scene.window(bands=[{"code": "CHD", "basis": "flat", "value": "20"}], overwrite=False)
        first = plan({}, [SeasonChoice(1, "NEW_ROW", "include", "새 줄 만들어")], window=window, price="180.5", occupancy_keys=" A2 ",
                     child_extra={"CHD": ""})
        steps = season_steps(first)
        self.assertEqual(steps[0].body["payload"]["form"], [list(pair) for pair in window.form], "첫 단계는 미리보기 때 읽은 창 그대로")
        after = opened_form(window, first.saves[0].save, True)
        self.assertEqual(dict(after)["price"], "180.5")
        self.assertEqual(dict(after)["occupancy_keys"], "A2", "글 칸은 앞뒤 빈칸을 걷어 기억한다")
        self.assertEqual(dict(after)["child_extra_CHD"], "", "빈 아동 칸은 빈 채로 기억한다")
        self.assertEqual(dict(after)["overwrite"], "on", "앞 저장이 칸을 만들었으면 덮기가 켜진 채 열린다")
        self.assertNotIn("rooms", dict(after))

    def test_steps_write_exactly_the_changed_fields_of_their_save(self):
        done = plan(cells({"2026-12-01": "170", "2026-12-02": "180"}), [], dates=["2026-12-01", "2026-12-02"])
        [step] = season_steps(done)
        self.assertEqual([(write.field, write.after) for write in step.writes], [("sell", D("180"))])
        self.assertEqual(step.body["predicted"]["updated"], 2)


if __name__ == "__main__":
    unittest.main()
