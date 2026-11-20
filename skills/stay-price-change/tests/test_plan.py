"""미리보기 계산 — 바꾸는 방법 셋, 반올림, 아동 추가분, 규칙 표의 줄마다, 표시, 빨간 줄 고르기, 저장 단계, 낡음 확인.

    python3 -m unittest discover -s tests
"""

import sys
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import scene  # noqa: E402
from change_core.items import Refused  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from price_model import MISSING, CellKey, CellValue, CellWrite, ChangeRequest, Snapshot, key_of_item  # noqa: E402
from price_plan import PlanError, counts, plan_change, plan_steps, resolve, save_steps, stale_cells, unresolved  # noqa: E402

D = Decimal
DAY, NEXT, LATER = "2026-12-25", "2026-12-26", "2026-12-28"


def snap(cells, currency="USD", reserved=(), pairs=(("R", "P"),)):
    """`{(날짜, 인원, 박수): CellValue}` → 객실 R · 요금제 P 한 곳(과 `pairs` 에 적은 읽은 쌍)의 Snapshot."""
    return Snapshot("H", "O", currency, "2026-11-20T10:00:00+09:00",
                    {CellKey("R", "P", day, occ, nights): value for (day, occ, nights), value in cells.items()},
                    frozenset(reserved), frozenset(pairs))


def open_(sell, list_price=None, supply=None):
    return CellValue(D(sell), None if list_price is None else D(list_price), None if supply is None else D(supply), "open")


def ask(operation, value, dates=(DAY,), **over):
    return ChangeRequest("H", "O", ("R",), ("P",), tuple(dates), operation, D(value), **over)


def after_of(plan):
    return {(c.key.date, c.key.occupancy, c.key.nights): (c.after.sell if c.after else None) for c in plan.changes}


def verdicts(plan):
    return {(c.key.date, c.key.occupancy, c.key.nights): c.verdict for c in plan.changes}


class SceneTest(unittest.TestCase):
    """그림이 보인 숫자: 바뀌는 칸 90 · 예약 있는 날의 칸 24 · 마감 칸 6 · 건너뛰는 칸 6 · 정가 넘는 칸 2 · 저장 8번."""

    def setUp(self):
        self.plan = plan_change(scene.snapshot(), scene.request())

    def test_counts(self):
        tally = counts(self.plan.changes, len(self.plan.skipped))
        self.assertEqual((tally["cells"], tally["reserved"], tally["closed"], tally["skipped"], tally["ABOVE_LIST"]),
                         (90, 24, 6, 6, 2))
        self.assertEqual((tally["blocked"], tally["OVER_30"], tally["red"]), (0, 0, 2))

    def test_save_steps_after_choosing_for_the_two_cells_above_list_price(self):
        for choice in ("raise_list", "keep"):
            chosen = resolve(self.plan, [Resolution("ABOVE_LIST", choice)])
            self.assertEqual(unresolved(chosen), ())
            self.assertEqual(len(plan_steps(chosen)), 8, choice)

    def test_values_from_the_picture(self):
        values = {(c.key.room, c.key.rate_plan, c.key.date, c.key.occupancy, c.key.nights): c for c in self.plan.changes}
        child = values[("디럭스", "조식 포함", "2026-12-25", "A2C1_CHD", 1)]
        self.assertEqual((child.before.sell, child.after.sell), (D("230.00"), D("250.00")))
        half = values[("스위트", "룸온리", "2026-12-25", "A2", 1)]
        self.assertEqual(half.after.sell, D("373.95"))
        over = values[("스위트", "조식 포함", "2027-01-01", "A2", 1)]
        self.assertEqual((over.after.sell, over.verdict, over.marks), (D("528.00"), "ABOVE_LIST", ("reserved",)))

    def test_a_hundred_percent_by_mistake_puts_every_cell_on_a_red_line_once(self):
        tally = counts(plan_change(scene.snapshot(), scene.request("100")).changes)
        self.assertEqual((tally["red"], tally["OVER_30"], tally["ABOVE_LIST"]), (90, 88, 2))


class RuleOrderTest(unittest.TestCase):
    def test_verdict_order_is_kept(self):
        from price_model import CELL_RULES
        codes = [rule.code for rule in CELL_RULES.rules]
        kept = ["NOT_POSITIVE", "NO_ADULT_CELL", "NO_BASE_CELL", "ABOVE_LIST", "BELOW_COST", "OVER_30"]
        self.assertEqual([code for code in codes if code in kept], kept)
        self.assertEqual({rule.code for rule in CELL_RULES.rules if rule.severity == "blocked"},
                         {"NOT_POSITIVE", "NEGATIVE_SUPPLY", "NO_ADULT_CELL", "NO_BASE_CELL", "NEW_WITHOUT_SELL", "NEW_NOT_SHOWN"})


class OperationTest(unittest.TestCase):
    def test_flat_amount_moves_every_occupancy_and_nights_tier_by_the_same_amount(self):
        snapshot = snap({(DAY, "A2", 1): open_("100000"), (DAY, "A3", 1): open_("130000"),
                         (DAY, "A2C1_CHD", 3): open_("110000")}, currency="KRW")
        plan = plan_change(snapshot, ask("amount", "-5000"))
        self.assertEqual(after_of(plan), {(DAY, "A2", 1): D("95000"), (DAY, "A3", 1): D("125000"),
                                          (DAY, "A2C1_CHD", 3): D("105000")})

    def test_set_moves_every_cell_of_the_day_by_the_base_one_night_difference_so_tiers_keep_their_gap(self):
        snapshot = snap({(DAY, "A2", 1): open_("300.00"), (DAY, "A3", 1): open_("360.00"),
                         (DAY, "A2", 3): open_("270.00"), (DAY, "A3", 3): open_("320.00"),
                         (NEXT, "A2", 1): open_("310.00"), (NEXT, "A3", 1): open_("380.00")})
        plan = plan_change(snapshot, ask("set", "350", dates=(DAY, NEXT), base_occupancy="A2"))
        after = after_of(plan)
        self.assertEqual(after, {
            (DAY, "A2", 1): D("350.00"), (DAY, "A3", 1): D("410.00"),
            (DAY, "A2", 3): D("320.00"), (DAY, "A3", 3): D("370.00"),
            (NEXT, "A2", 1): D("350.00"), (NEXT, "A3", 1): D("420.00"),
        })
        self.assertEqual(after[(DAY, "A2", 1)] - after[(DAY, "A2", 3)], D("30.00"))

    def test_set_cannot_apply_a_day_without_a_base_one_night_value_and_says_why(self):
        snapshot = snap({(DAY, "A2", 1): MISSING, (DAY, "A3", 1): open_("360.00"), (DAY, "A2", 3): open_("270.00"),
                         (NEXT, "A2", 1): open_("300.00")})
        plan = plan_change(snapshot, ask("set", "350", dates=(DAY, NEXT), base_occupancy="A2"))
        self.assertEqual(verdicts(plan), {(DAY, "A3", 1): "NO_BASE_CELL", (DAY, "A2", 3): "NO_BASE_CELL",
                                          (NEXT, "A2", 1): None})
        self.assertEqual(after_of(plan)[(NEXT, "A2", 1)], D("350.00"))
        self.assertEqual([(item.key.occupancy, item.reason) for item in plan.skipped], [("A2", "no_price")])
        self.assertEqual([(c.key.date, c.writes) for c in plan.changes if c.writes], [(NEXT, {"sell": D("350.00")})])

    def test_percent_multiplies_adults_only_cells(self):
        plan = plan_change(snap({(DAY, "A2", 1): open_("200.00"), (DAY, "", 1): open_("150.00")}), ask("percent", "-10"))
        self.assertEqual(after_of(plan), {(DAY, "A2", 1): D("180.00"), (DAY, "", 1): D("135.00")})

    def test_percent_keeps_the_child_surcharge_unless_asked_to_scale_it(self):
        cells = {(DAY, "A2", 1): open_("200.00"), (DAY, "A2C1_CHD", 1): open_("230.00")}
        plain = plan_change(snap(cells), ask("percent", "10"))
        self.assertEqual(after_of(plain)[(DAY, "A2C1_CHD", 1)], D("250.00"))
        scaled = plan_change(snap(cells), ask("percent", "10", scale_child_surcharge=True))
        self.assertEqual(after_of(scaled)[(DAY, "A2C1_CHD", 1)], D("253.00"))

    def test_rounding_at_a_half_goes_up_in_the_currency_unit(self):
        usd = plan_change(snap({(DAY, "A2", 1): open_("339.95")}), ask("percent", "10"))
        self.assertEqual(after_of(usd)[(DAY, "A2", 1)], D("373.95"))
        krw = plan_change(snap({(DAY, "A2", 1): open_("15005")}, currency="KRW"), ask("percent", "10"))
        self.assertEqual(after_of(krw)[(DAY, "A2", 1)], D("16506"))
        amount = plan_change(snap({(DAY, "A2", 1): open_("10.00")}), ask("amount", "0.005"))
        self.assertEqual(after_of(amount)[(DAY, "A2", 1)], D("10.01"))


class RuleTableTest(unittest.TestCase):
    def verdict(self, cell, operation, value, **over):
        plan = plan_change(snap({(DAY, "A2", 1): cell, **over.pop("more", {})}), ask(operation, value, **over))
        return verdicts(plan)

    def test_zero_or_below_cannot_be_applied(self):
        self.assertEqual(self.verdict(open_("150.00"), "amount", "-150")[(DAY, "A2", 1)], "NOT_POSITIVE")
        self.assertEqual(self.verdict(open_("150.00"), "amount", "-200")[(DAY, "A2", 1)], "NOT_POSITIVE")

    def test_child_cell_without_an_adults_only_cell_cannot_be_applied(self):
        result = self.verdict(open_("100.00"), "percent", "10", more={(DAY, "A3C1_CHD", 1): open_("230.00")})
        self.assertEqual(result[(DAY, "A3C1_CHD", 1)], "NO_ADULT_CELL")
        scaled = self.verdict(open_("100.00"), "percent", "10", scale_child_surcharge=True,
                              more={(DAY, "A3C1_CHD", 1): open_("230.00")})
        self.assertIsNone(scaled[(DAY, "A3C1_CHD", 1)])
        unreadable = self.verdict(open_("100.00"), "percent", "10", more={(DAY, "2A+1유아", 1): open_("230.00")})
        self.assertEqual(unreadable[(DAY, "2A+1유아", 1)], "NO_ADULT_CELL")
        flat = self.verdict(open_("100.00"), "amount", "10", more={(DAY, "A3C1_CHD", 1): open_("230.00")})
        self.assertIsNone(flat[(DAY, "A3C1_CHD", 1)])

    def test_more_than_thirty_percent_is_a_red_line_and_exactly_thirty_is_not(self):
        self.assertIsNone(self.verdict(open_("100.00"), "percent", "30")[(DAY, "A2", 1)])
        self.assertIsNone(self.verdict(open_("100.00"), "percent", "-30")[(DAY, "A2", 1)])
        self.assertEqual(self.verdict(open_("100.00"), "amount", "30.01")[(DAY, "A2", 1)], "OVER_30")
        self.assertEqual(self.verdict(open_("100.00"), "amount", "-30.01")[(DAY, "A2", 1)], "OVER_30")

    def test_below_known_supply_cost_is_a_red_line(self):
        self.assertEqual(self.verdict(open_("200.00", supply="180.00"), "amount", "-30")[(DAY, "A2", 1)], "BELOW_COST")
        self.assertIsNone(self.verdict(open_("200.00", supply="180.00"), "amount", "-20")[(DAY, "A2", 1)])
        self.assertIsNone(self.verdict(open_("200.00"), "amount", "-30")[(DAY, "A2", 1)])

    def test_above_list_price_is_a_red_line_and_wins_over_thirty_percent(self):
        self.assertEqual(self.verdict(open_("200.00", list_price="210.00"), "amount", "20")[(DAY, "A2", 1)], "ABOVE_LIST")
        self.assertIsNone(self.verdict(open_("200.00", list_price="220.00"), "amount", "20")[(DAY, "A2", 1)])
        self.assertEqual(self.verdict(open_("200.00", list_price="210.00"), "percent", "100")[(DAY, "A2", 1)],
                         "ABOVE_LIST")


class MarksTest(unittest.TestCase):
    def test_missing_days_are_skipped_closed_stay_closed_reserved_are_changed_and_marked(self):
        snapshot = snap({(DAY, "A2", 1): open_("100.00"), (NEXT, "A2", 1): CellValue(D("100.00"), None, None, "closed"),
                         (LATER, "A2", 1): MISSING}, reserved={("R", DAY)})
        plan = plan_change(snapshot, ask("amount", "10", dates=(DAY, NEXT, LATER)))
        self.assertEqual([(item.key.date, item.reason) for item in plan.skipped], [(LATER, "no_price")])
        by_day = {c.key.date: c for c in plan.changes}
        self.assertEqual((by_day[DAY].marks, by_day[DAY].after.sell), (("reserved",), D("110.00")))
        self.assertEqual((by_day[NEXT].marks, by_day[NEXT].after.state, by_day[NEXT].after.sell),
                         (("closed",), "closed", D("110.00")))


class ScopeTest(unittest.TestCase):
    def test_request_outside_what_was_read_is_refused(self):
        snapshot = snap({(DAY, "A2", 1): open_("100.00")})
        with self.assertRaises(PlanError):
            plan_change(snapshot, ask("amount", "10", dates=(DAY, NEXT)))
        with self.assertRaises(PlanError):
            plan_change(snapshot, ChangeRequest("H", "O", ("R", "Other"), ("P",), (DAY,), "amount", D("1")))
        with self.assertRaises(PlanError):
            plan_change(snapshot, ChangeRequest("Other hotel", "O", ("R",), ("P",), (DAY,), "amount", D("1")))


class FieldTest(unittest.TestCase):
    """판매가뿐 아니라 정가·공급 원가도 바꾼다 — 같은 방법(금액·퍼센트·새 값·비우기), 같은 규칙 표."""

    def changed(self, plan, name):
        return {(c.key.occupancy, c.key.nights): getattr(c.after, name) for c in plan.changes}

    def test_amount_on_list_price_and_percent_on_supply_cost(self):
        cells = {(DAY, "A2", 1): open_("200.00", list_price="250.00", supply="150.00"),
                 (DAY, "A2C1_CHD", 1): open_("230.00", list_price="280.00", supply="170.00")}
        listed = plan_change(snap(cells), ask("amount", "20", field="list"))
        self.assertEqual(self.changed(listed, "list"), {("A2", 1): D("270.00"), ("A2C1_CHD", 1): D("300.00")})
        self.assertEqual({c.changed for c in listed.changes}, {("list",)})
        supply = plan_change(snap(cells), ask("percent", "10", field="supply"))
        self.assertEqual(self.changed(supply, "supply"), {("A2", 1): D("165.00"), ("A2C1_CHD", 1): D("185.00")})

    def test_set_on_list_price_uses_the_base_one_night_list_price(self):
        cells = {(DAY, "A2", 1): open_("200.00", list_price="250.00"), (DAY, "A2", 3): open_("180.00", list_price="230.00")}
        plan = plan_change(snap(cells), ask("set", "300", field="list", base_occupancy="A2"))
        self.assertEqual(self.changed(plan, "list"), {("A2", 1): D("300.00"), ("A2", 3): D("280.00")})

    def test_clearing_supply_cost_goes_through_the_cell_window_and_cells_without_one_are_skipped(self):
        cells = {(DAY, "A2", 1): open_("200.00", supply="150.00"), (DAY, "A3", 1): open_("260.00")}
        plan = plan_change(snap(cells), ChangeRequest("H", "O", ("R",), ("P",), (DAY,), "clear", None, field="supply"))
        self.assertEqual(self.changed(plan, "supply"), {("A2", 1): None})
        self.assertEqual([(item.key.occupancy, item.reason) for item in plan.skipped], [("A3", "no_supply")])
        self.assertEqual([(c.key.occupancy, c.writes) for c in plan.changes if c.writes], [("A2", {"supply": None})])
        steps = plan_steps(plan)
        self.assertEqual([(step.kind, step.key.occupancy, step.clear) for step in steps], [("cell_edit", "A2", ("supply",))])

    def test_a_negative_supply_cost_cannot_be_applied(self):
        plan = plan_change(snap({(DAY, "A2", 1): open_("200.00", supply="150.00")}), ask("amount", "-200", field="supply"))
        self.assertEqual(verdicts(plan), {(DAY, "A2", 1): "NEGATIVE_SUPPLY"})

    def test_rules_look_at_the_resulting_cell_whichever_value_moved(self):
        lower_list = plan_change(snap({(DAY, "A2", 1): open_("200.00", list_price="210.00")}), ask("amount", "-20", field="list"))
        self.assertEqual(verdicts(lower_list), {(DAY, "A2", 1): "ABOVE_LIST"})
        raise_cost = plan_change(snap({(DAY, "A2", 1): open_("200.00", supply="150.00")}), ask("amount", "60", field="supply"))
        self.assertEqual(verdicts(raise_cost), {(DAY, "A2", 1): "BELOW_COST"})
        big_list = plan_change(snap({(DAY, "A2", 1): open_("200.00", list_price="300.00")}), ask("percent", "40", field="list"))
        self.assertEqual(verdicts(big_list), {(DAY, "A2", 1): "OVER_30"})


class ListChoiceTest(unittest.TestCase):
    """정가를 넘는 두 칸(그림 장면): 정가도 올림 · 정가 지움 · 안 바꿈."""

    def setUp(self):
        self.plan = plan_change(scene.snapshot(), scene.request())
        self.over = CellKey("스위트", "조식 포함", "2027-01-01", "A2", 1)

    def test_raise_list_puts_both_columns_on_the_bulk_row(self):
        steps = plan_steps(resolve(self.plan, [Resolution("ABOVE_LIST", "raise_list")]))
        step = next(s for s in steps if s.kind == "bulk" and s.room == "스위트" and s.rate_plan == "조식 포함"
                    and "2027-01-01" in s.dates)
        row = next(r for r in step.rows if (r.occupancy, r.nights) == ("A2", 1))
        self.assertEqual((row.sell, row.list, row.supply), (D("528.00"), D("548.00"), None))

    def test_clear_list_adds_a_cell_window_save_before_the_bulk_saves_of_that_room_and_plan(self):
        steps = plan_steps(resolve(self.plan, [Resolution("ABOVE_LIST", "clear_list")]))
        self.assertEqual((len(steps), sum(s.kind == "bulk" for s in steps)), (10, 8))
        suite = [s for s in steps if s.kind == "cell_edit" or (s.room, s.rate_plan) == ("스위트", "조식 포함")]
        self.assertEqual([s.kind for s in suite], ["cell_edit", "cell_edit", "bulk", "bulk"])
        self.assertEqual([(s.key.date, s.clear) for s in suite[:2]], [("2027-01-01", ("list",)), ("2027-01-02", ("list",))])
        self.assertLess(steps.index(suite[1]), steps.index(suite[2]))
        row = next(r for r in suite[3].rows if (r.occupancy, r.nights) == ("A2", 1))
        self.assertEqual((row.sell, row.list), (D("528.00"), None))


class NoEmptySaveTest(unittest.TestCase):
    """R10 — 아무 값도 바꾸지 않는 저장은 만들지 않는다."""

    def test_a_cell_already_at_its_new_value_is_skipped_and_never_saved(self):
        snapshot = snap({(DAY, "A2", 1): open_("350.00"), (DAY, "A3", 1): open_("410.00"), (NEXT, "A2", 1): open_("300.00")})
        plan = plan_change(snapshot, ask("set", "350", dates=(DAY, NEXT), base_occupancy="A2"))
        self.assertEqual([(i.key.date, i.key.occupancy, i.reason) for i in plan.skipped],
                         [(DAY, "A2", "same"), (DAY, "A3", "same")])
        steps = plan_steps(plan)
        self.assertEqual([(s.dates, [r.occupancy for r in s.rows]) for s in steps], [((NEXT,), ["A2"])])

    def test_a_change_that_moves_nothing_produces_no_save_at_all(self):
        plan = plan_change(snap({(DAY, "A2", 1): open_("100.00"), (NEXT, "A2", 1): open_("100.00")}),
                           ask("percent", "0", dates=(DAY, NEXT)))
        self.assertEqual((plan.changes, len(plan.skipped)), ((), 2))
        self.assertEqual(plan_steps(plan), ())

    def test_a_write_without_any_value_is_ignored_by_save_steps(self):
        self.assertEqual(save_steps([CellWrite(CellKey("R", "P", DAY, "A2", 1))]), ())


class ReadPairsTest(unittest.TestCase):
    """R9 — 읽지 않은 객실·요금제를 말없이 빼지 않는다. 읽었지만 칸이 없는 쌍은 건너뜀으로 알린다."""

    def test_a_requested_pair_that_was_not_read_is_refused_by_name(self):
        snapshot = snap({(DAY, "A2", 1): open_("100.00")})
        with self.assertRaises(PlanError) as caught:
            plan_change(snapshot, ChangeRequest("H", "O", ("R",), ("P", "Q"), (DAY,), "amount", D("1")))
        self.assertIn("R · Q", str(caught.exception))

    def test_a_pair_read_with_no_priced_cells_is_reported_as_skipped(self):
        snapshot = snap({(DAY, "A2", 1): open_("100.00")}, pairs=(("R", "P"), ("R", "Q")))
        plan = plan_change(snapshot, ChangeRequest("H", "O", ("R",), ("P", "Q"), (DAY,), "amount", D("1")))
        self.assertEqual((len(plan.changes), plan.empty_pairs), (1, (("R", "Q"),)))

    def test_a_snapshot_cannot_hold_cells_of_a_pair_it_does_not_say_it_read(self):
        with self.assertRaises(ValueError):
            snap({(DAY, "A2", 1): open_("100.00")}, pairs=(("R", "Q"),))


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.plan = plan_change(snap({
            (DAY, "A2", 1): open_("200.00", list_price="210.00"),
            (NEXT, "A2", 1): open_("200.00", list_price="205.00"),
            (DAY, "A3", 1): open_("100.00"),
            (NEXT, "A3", 1): open_("10.00"),
        }), ask("amount", "20", dates=(DAY, NEXT)))

    def test_red_line_cells_wait_for_a_choice(self):
        plan = resolve(self.plan, [])
        self.assertEqual(sorted((c.key.date, c.key.occupancy) for c in unresolved(plan)),
                         [(DAY, "A2"), (NEXT, "A2"), (NEXT, "A3")])
        self.assertEqual([(c.key.date, c.key.occupancy, c.writes) for c in plan.changes if c.writes],
                         [(DAY, "A3", {"sell": D("120.00")})])
        self.assertIsNone(plan_steps(plan), "빨간 줄이 남아 있으면 저장 단계가 없다")

    def test_blocked_cells_are_never_written_and_need_no_choice(self):
        plan = plan_change(snap({(DAY, "A2", 1): open_("150.00"), (DAY, "A3", 1): open_("300.00")}),
                           ask("amount", "-150"))
        chosen = resolve(plan, [Resolution("OVER_30", "include")])
        self.assertEqual(unresolved(chosen), ())
        self.assertEqual([(c.key.occupancy, c.writes) for c in chosen.changes if c.writes], [("A3", {"sell": D("150.00")})])

    def test_raise_list_moves_the_list_price_by_the_same_amount_and_a_named_cell_overrides(self):
        nxt = CellKey("R", "P", NEXT, "A2", 1)
        chosen = resolve(self.plan, [Resolution("ABOVE_LIST", "raise_list"), Resolution("OVER_30", "include"),
                                     Resolution("ABOVE_LIST", "keep", (nxt,))])
        self.assertEqual(unresolved(chosen), ())
        self.assertEqual({(c.key.date, c.key.occupancy): c.writes for c in chosen.changes if c.writes}, {
            (DAY, "A2"): {"sell": D("220.00"), "list": D("230.00")}, (DAY, "A3"): {"sell": D("120.00")},
            (NEXT, "A3"): {"sell": D("30.00")}})
        cells = {(c.key.date, c.key.occupancy): c for c in chosen.changes}
        self.assertEqual({key: (c.verdict, c.choice) for key, c in cells.items()}, {
            (DAY, "A2"): ("ABOVE_LIST", "raise_list"), (NEXT, "A2"): ("ABOVE_LIST", "keep"), (DAY, "A3"): (None, None),
            (NEXT, "A3"): ("OVER_30", "include")}, "고른 칸은 걸린 규칙과 고른 것을 함께 갖는다")
        self.assertEqual(cells[(NEXT, "A2")].after, cells[(NEXT, "A2")].before, "안 바꾸는 칸의 후 값은 전 값 그대로")
        self.assertEqual(cells[(DAY, "A2")].after.list, D("230.00"), "정가도 올린 칸의 후 값은 올린 정가")

    def test_naming_a_cell_that_is_not_on_that_red_line_is_refused(self):
        with self.assertRaises(Refused):
            resolve(self.plan, [Resolution("OVER_30", "include", (CellKey("R", "P", DAY, "A2", 1),))])

    def test_only_listed_choices_and_red_line_rules_are_accepted(self):
        with self.assertRaises(Refused):
            resolve(self.plan, [Resolution("ABOVE_LIST", "multiply")])
        with self.assertRaises(Refused):
            resolve(self.plan, [Resolution("NOT_POSITIVE", "include")])


class SaveStepTest(unittest.TestCase):
    def write(self, day, occ, sell, nights=1, plan="P", list_price=None):
        return CellWrite(CellKey("R", plan, day, occ, nights), D(sell), None if list_price is None else D(list_price))

    def test_adjacent_days_with_the_same_rows_share_one_save(self):
        steps = save_steps([self.write(DAY, "A2", "10"), self.write(DAY, "A3", "12"),
                            self.write(NEXT, "A3", "12"), self.write(NEXT, "A2", "10")])
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].dates, (DAY, NEXT))
        self.assertEqual([(r.occupancy, r.sell) for r in steps[0].rows], [("A2", D("10")), ("A3", D("12"))])

    def test_t7_days_apart_with_the_same_rows_share_one_save_ordered_by_their_first_day(self):
        steps = save_steps([self.write(DAY, "A2", "10"), self.write(NEXT, "A2", "11"), self.write(LATER, "A2", "10")])
        self.assertEqual([(s.dates, s.rows[0].sell) for s in steps], [((DAY, LATER), D("10")), ((NEXT,), D("11"))])
        # 2026년 12월의 금·토 여덟 날 — 값이 같으면 쌍마다 저장 한 번(전에는 이어진 날마다라 주마다 한 번, 네 번)
        weekend = [f"2026-12-{day:02d}" for day in (4, 5, 11, 12, 18, 19, 25, 26)]
        self.assertEqual([s.dates for s in save_steps([self.write(day, "A2", "10") for day in weekend])], [tuple(weekend)])

    def test_t7_one_save_spans_at_most_the_550_days_erp_takes_at_once(self):
        first = date.fromisoformat(DAY)
        last_in = (first + timedelta(days=549)).isoformat()      # 첫 날부터 550일째
        steps = save_steps([self.write(DAY, "A2", "10"), self.write(last_in, "A2", "10")])
        self.assertEqual([s.dates for s in steps], [(DAY, last_in)])
        past = (first + timedelta(days=550)).isoformat()
        steps = save_steps([self.write(DAY, "A2", "10"), self.write(last_in, "A2", "10"), self.write(past, "A2", "10")])
        self.assertEqual([s.dates for s in steps], [(DAY, last_in), (past,)])

    def test_a_different_value_a_missing_row_or_a_different_list_price_splits_the_save(self):
        self.assertEqual(len(save_steps([self.write(DAY, "A2", "10"), self.write(NEXT, "A2", "11")])), 2)
        self.assertEqual(len(save_steps([self.write(DAY, "A2", "10"), self.write(DAY, "A3", "12"),
                                         self.write(NEXT, "A2", "10")])), 2)
        self.assertEqual(len(save_steps([self.write(DAY, "A2", "10", list_price="20"),
                                         self.write(NEXT, "A2", "10", list_price="21")])), 2)

    def test_each_rate_plan_is_its_own_save(self):
        steps = save_steps([self.write(DAY, "A2", "10"), self.write(DAY, "A2", "10", plan="Q")])
        self.assertEqual([s.rate_plan for s in steps], ["P", "Q"])

    def test_two_values_for_one_cell_are_refused(self):
        with self.assertRaises(PlanError):
            save_steps([self.write(DAY, "A2", "10"), self.write(DAY, "A2", "11")])


class StaleTest(unittest.TestCase):
    def test_every_differing_cell_is_reported(self):
        then = snap({(DAY, "A2", 1): open_("100.00"), (NEXT, "A2", 1): open_("100.00"), (LATER, "A2", 1): open_("1.00")})
        self.assertEqual(stale_cells(then, then), ())
        now = snap({(DAY, "A2", 1): open_("101.00"), (NEXT, "A2", 1): CellValue(D("100.00"), None, None, "closed"),
                    (LATER, "A3", 1): open_("1.00")})
        self.assertEqual([(key_of_item(d.key).date, key_of_item(d.key).occupancy) for d in stale_cells(then, now)],
                         [(DAY, "A2"), (NEXT, "A2"), (LATER, "A2"), (LATER, "A3")])


if __name__ == "__main__":
    unittest.main()
