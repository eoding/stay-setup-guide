"""새 요금표(kind sheet) — 파일 모양(S1), 차이로 적은 값의 셈(S2), 칸으로 펼침과 거절(S3), 넣지 않는 것(S4), 읽을 범위(S6).

    python3 -m unittest discover -s tests
"""

import copy
import re
import sys
import unittest
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import sheet_scene as S  # noqa: E402
from change_core.items import Refused  # noqa: E402
from price_browser import PAGE_KEEPS  # noqa: E402
from price_model import CellKey, MISSING, decode_request  # noqa: E402
from price_plan import plan_steps, unresolved  # noqa: E402
from price_sheet import (  # noqa: E402
    Part, SheetCheck, coverage_counts, decode_sheet, encode_sheet, expand, line_figures, plan_sheet,
)

PAIRS = (("디럭스", S.PLAN), ("스위트", S.PLAN), ("패밀리", S.PLAN))


def one_line(rows, periods=None, currency="USD", **line):
    return decode_sheet(dict(S.sheet_data(currency=currency), lines=[dict(
        {"room": "디럭스", "rate_plan": S.PLAN, "periods": periods or [{"from": "2027-01-04", "to": "2027-01-04"}], "rows": rows},
        **line)]))


def figures(rows, currency="USD"):
    sheet = one_line(rows, currency=currency)
    return {at: {name: figure.value for name, figure in values.items()}
            for at, values in line_figures(sheet.lines[0], currency).items()}


class SheetShapeTest(unittest.TestCase):
    """S1 — 요금표 모양의 요청: 줄 = 객실 · 요금제 · 기간(요일은 골라서), 그 안에 인원 · 박수마다 값. 숫자만 옮긴다."""

    def test_a_sheet_file_reads_into_lines_and_writes_back_the_same(self):
        sheet = decode_sheet(S.sheet_data())
        self.assertEqual(len(sheet.lines), 8)
        line = sheet.lines[1]
        self.assertEqual((line.no, line.room, line.season, line.days), (2, "디럭스", "비수기", ("2027-01-08", "2027-01-09")))
        self.assertEqual([(row.occupancy, row.nights) for row in line.rows], [("A2", 1), ("A3", 1), ("A2C1_CHD", 1), ("A2", 3)])
        self.assertEqual(decode_sheet(encode_sheet(sheet)), sheet)

    def test_only_copied_numbers_or_a_difference_from_another_row_are_values(self):
        for bad in ("240+60", "약 240", 240.5, True):
            with self.assertRaises(ValueError, msg=bad):
                one_line([{"occupancy": "A2", "nights": 1, "sell": bad}])
        with self.assertRaises(ValueError):   # 가리키는 값은 금액이나 퍼센트 하나
            one_line([{"occupancy": "A2", "nights": 1, "sell": "200"},
                      {"occupancy": "A3", "nights": 1, "sell": {"from": {"occupancy": "A2"}, "add": "60", "percent": "5"}}])
        with self.assertRaises(ValueError):
            one_line([{"occupancy": "A2", "nights": 1, "list": "300"}])   # 판매가가 없다
        with self.assertRaises(ValueError):
            one_line([{"occupancy": "A2", "nights": 1, "sell": "200"}, {"occupancy": "A2", "nights": 1, "sell": "210"}])
        with self.assertRaises(ValueError):
            decode_sheet(dict(S.sheet_data(), currency=""))
        with self.assertRaises(ValueError):
            decode_sheet(dict(S.sheet_data(), hotel={"name": S.HOTEL}))

    def test_other_commands_send_a_raw_sheet_back_to_the_sheet_command(self):
        with self.assertRaises(ValueError) as caught:
            decode_request(S.sheet_data())
        self.assertIn("sheet 명령", str(caught.exception))


class SheetDifferenceTest(unittest.TestCase):
    """S2 — 차이로 적은 값(+금액 · %)은 명령이 셈한다. 반올림은 기존 계산의 통화 규칙. 없는 줄 · 고리는 이름을 대고 거절."""

    def test_amounts_percentages_and_chains_are_calculated(self):
        values = figures([
            {"occupancy": "A2", "nights": 1, "sell": "240", "list": "300"},
            {"occupancy": "A3", "nights": 1, "sell": {"from": {"occupancy": "A2"}, "add": "60"},
             "list": {"from": {"occupancy": "A2"}, "add": "60"}},
            {"occupancy": "A1", "nights": 1, "sell": {"from": {"occupancy": "A2"}, "add": "-20"}},
            {"occupancy": "A3", "nights": 3, "sell": {"from": {"nights": 1}, "percent": "-10"}},
            {"occupancy": "A2", "nights": 3, "sell": {"from": {"nights": 1}, "percent": "-12.5"}}])
        self.assertEqual(values, {("A2", 1): {"sell": D("240.00"), "list": D("300.00")},
                                  ("A3", 1): {"sell": D("300.00"), "list": D("360.00")},
                                  ("A1", 1): {"sell": D("220.00")},
                                  ("A3", 3): {"sell": D("270.00")},
                                  ("A2", 3): {"sell": D("210.00")}})

    def test_rounding_follows_the_currency(self):
        self.assertEqual(figures([{"occupancy": "A2", "nights": 1, "sell": "99.99"},
                                  {"occupancy": "A2", "nights": 3, "sell": {"from": {"nights": 1}, "percent": "-15"}}])[("A2", 3)],
                         {"sell": D("84.99")})   # 84.9915 → 센트
        self.assertEqual(figures([{"occupancy": "A2", "nights": 1, "sell": "123455"},
                                  {"occupancy": "A2", "nights": 3, "sell": {"from": {"nights": 1}, "percent": "-10"}}],
                                 currency="KRW")[("A2", 3)], {"sell": D("111110")})   # 111109.5 → 원, 반 올림

    def test_the_formula_names_the_row_it_came_from(self):
        sheet = one_line(S.rows("240"))
        found = line_figures(sheet.lines[0], "USD")
        self.assertIsNone(found[("A2", 1)]["sell"].formula)
        self.assertEqual(found[("A3", 1)]["sell"].formula, "성인 2 · 1박 이상 240.00 + 60")
        self.assertEqual(found[("A2", 3)]["sell"].formula, "성인 2 · 1박 이상 240.00 - 10%")

    def test_a_missing_row_or_field_is_refused_by_name(self):
        with self.assertRaises(Refused) as caught:
            figures([{"occupancy": "A3", "nights": 1, "sell": {"from": {"occupancy": "A2"}, "add": "60"}}])
        self.assertIn("1번째 줄(디럭스 · 조식 포함 · 1/4)", str(caught.exception))
        self.assertIn("성인 3 · 1박 이상 판매가가 가리키는 성인 2 · 1박 이상 판매가가 그 줄에 없습니다", str(caught.exception))
        with self.assertRaises(Refused) as caught:   # 줄은 있어도 그 필드가 없다
            figures([{"occupancy": "A2", "nights": 1, "sell": "240"},
                     {"occupancy": "A3", "nights": 1, "sell": "300", "list": {"from": {"occupancy": "A2"}, "add": "60"}}])
        self.assertIn("성인 2 · 1박 이상 정가가 그 줄에 없습니다", str(caught.exception))

    def test_a_cycle_is_refused_with_the_rows_in_it(self):
        with self.assertRaises(Refused) as caught:
            figures([{"occupancy": "A2", "nights": 1, "sell": {"from": {"occupancy": "A3"}, "add": "-60"}},
                     {"occupancy": "A3", "nights": 1, "sell": {"from": {"occupancy": "A2"}, "add": "60"}}])
        self.assertIn("고리", str(caught.exception))
        self.assertIn("성인 2 · 1박 이상 → 성인 3 · 1박 이상 → 성인 2 · 1박 이상", str(caught.exception))
        with self.assertRaises(Refused):
            figures([{"occupancy": "A2", "nights": 1, "sell": {"from": {"occupancy": "A2"}, "add": "1"}}])


class SheetExpandTest(unittest.TestCase):
    """S3 — 기간마다 칸으로 펼친다. 두 줄이 한 칸에 다른 값이면 두 줄을, 틀린 기간 · 읽기 한 번을 넘는 범위면 까닭을 대고 거절."""

    def test_periods_and_weekdays_become_one_target_per_day_and_row(self):
        sheet = decode_sheet(S.sheet_data())
        cells = expand(sheet.lines, "USD")
        self.assertEqual(len(cells), 2 * 14 * 4)
        self.assertEqual(cells[CellKey("디럭스", S.PLAN, "2027-01-08", "A3", 1)].values, (("sell", D("300.00")),))   # 비수기 금
        self.assertEqual(cells[CellKey("디럭스", S.PLAN, "2027-01-10", "A3", 1)].values, (("sell", D("260.00")),))   # 비수기 일
        self.assertEqual(cells[CellKey("스위트", S.PLAN, "2027-01-16", "A2", 3)].values, (("sell", D("450.00")),))   # 성수기 토
        self.assertEqual(cells[CellKey("스위트", S.PLAN, "2027-01-16", "A2", 3)].line, 8)

    def test_two_lines_giving_one_cell_different_values_are_refused_naming_both(self):
        data = S.sheet_data()
        data["lines"].append(copy.deepcopy(data["lines"][0]) | {"season": "연초", "periods": [{"from": "2027-01-06", "to": "2027-01-07"}]})
        data["lines"][-1]["rows"][0]["sell"] = "205"
        with self.assertRaises(Refused) as caught:
            SheetCheck(decode_sheet(data), PAIRS)
        message = str(caught.exception)
        self.assertIn("1번째 줄(디럭스 · 조식 포함 · 비수기 · 1/4 ~ 1/10 월·화·수·목·일)", message)
        self.assertIn("9번째 줄(디럭스 · 조식 포함 · 연초 · 1/6 ~ 1/7)", message)
        self.assertIn("2027-01-06 · 성인 2 · 1박 이상 칸에 다른 값을 줍니다(판매가 200.00 / 판매가 205.00)", message)
        # 같은 값이면 겹쳐도 된다
        data["lines"][-1]["rows"][0]["sell"] = "200.00"
        self.assertEqual(len(SheetCheck(decode_sheet(data), PAIRS).cells), 2 * 14 * 4)

    def test_a_period_that_is_not_a_date_range_is_refused(self):
        for period, words in (({"from": "2027-01-10", "to": "2027-01-04"}, "시작일(2027-01-10)이 종료일(2027-01-04)보다 뒤"),
                              ({"from": "2027-02-30", "to": "2027-03-01"}, "ISO 형식"),
                              ({"from": "2027-01-04", "to": "2027-01-05", "weekdays": ["토"]}, "하루도 없습니다"),
                              ({"from": "2027-01-04", "to": "2027-01-05", "weekdays": ["Sat"]}, "요일은")):
            with self.assertRaises(ValueError, msg=period) as caught:
                one_line(S.rows("200"), periods=[period])
            self.assertIn(words, str(caught.exception))

    def test_a_span_beyond_one_reading_is_refused_with_the_limit_and_where_it_comes_from(self):
        rooms = [f"객실 {n}" for n in range(1, PAGE_KEEPS // 2 + 1)]   # 1년은 객실마다 가격 읽기 2번 — 예약 읽기 1번을 더하면 하나 넘친다
        data = dict(S.sheet_data(), lines=[{"room": room, "rate_plan": S.PLAN, "periods": [{"from": "2027-01-01", "to": "2027-12-31"}],
                                            "rows": S.rows("200")} for room in rooms])
        check = SheetCheck(decode_sheet(data), tuple((room, S.PLAN) for room in rooms))
        self.assertEqual(check.reads, {"readPair": 2 * len(rooms), "readReserved": 1, "limit": PAGE_KEEPS, "fits": False})
        with self.assertRaises(Refused) as caught:
            check.fitting_range()
        message = str(caught.exception)
        for words in (f"가격 읽기 {2 * len(rooms)}번 + 예약 있는 날 읽기 1번", f"{PAGE_KEEPS}번까지", "stay_price.js KEEP_BODIES", "--room", "--from"):
            self.assertIn(words, message)
        # 한 부분씩이면 든다 — 객실 하나, 또는 상반기
        self.assertTrue(replace(check, part=Part(rooms=("객실 1",))).reads["fits"])
        half = replace(check, part=Part(first="2027-01-01", last="2027-06-30"))
        self.assertEqual((half.reads["readPair"], half.reads["fits"], half.range.dates[-1]), (len(rooms), True, "2027-06-30"))


class SheetReadingRangeTest(unittest.TestCase):
    """S6 — 읽을 범위는 요금표의 객실 · 요금제(호텔에 있는 것) × 첫 날부터 끝 날까지. 1년이면 객실 · 요금제마다 readPair 2번."""

    def test_the_range_is_the_named_pairs_over_the_whole_span(self):
        check = SheetCheck(decode_sheet(S.sheet_data()), PAIRS)
        self.assertEqual(check.range.pairs, (("디럭스", S.PLAN), ("스위트", S.PLAN)))
        self.assertEqual(check.range.dates, S.DAYS)
        self.assertEqual(check.reads, {"readPair": 2, "readReserved": 1, "limit": PAGE_KEEPS, "fits": True})

    def test_a_year_costs_two_price_reads_per_room_and_rate_plan(self):
        data = dict(S.sheet_data(), lines=[{"room": "디럭스", "rate_plan": S.PLAN, "periods": [{"from": "2027-01-01", "to": "2027-12-31"}],
                                            "rows": S.rows("200")}])
        self.assertEqual(SheetCheck(decode_sheet(data), PAIRS).reads["readPair"], 2)

    def test_one_room_or_one_season_at_a_time(self):
        check = SheetCheck(decode_sheet(S.sheet_data()), PAIRS, Part(rooms=("스위트",)))
        self.assertEqual((check.range.pairs, len(check.cells)), ((("스위트", S.PLAN),), 14 * 4))
        season = SheetCheck(decode_sheet(S.sheet_data()), PAIRS, Part(first="2027-01-11", last="2027-01-17"))
        self.assertEqual((season.range.dates[0], season.range.dates[-1], len(season.cells)), ("2027-01-11", "2027-01-17", 2 * 7 * 4))
        with self.assertRaises(Refused):
            SheetCheck(decode_sheet(S.sheet_data()), PAIRS, Part(rooms=("패밀리",)))

    def test_the_page_keeps_as_many_fragments_as_the_command_assumes(self):
        page = (HERE.parent / "scripts" / "page" / "stay_price.js").read_text(encoding="utf-8")
        self.assertEqual(int(re.search(r"var KEEP_BODIES = (\d+);", page).group(1)), PAGE_KEEPS)


class SheetPlanTest(unittest.TestCase):
    """S3 · S4 — 지금 값과 다른 칸만 바뀌고, 넣지 않는 것은 모두 이름을 대고 센다."""

    def setUp(self):
        self.check = SheetCheck(decode_sheet(S.sheet_data()), PAIRS)
        self.plan = plan_sheet(S.reading(), self.check)

    def test_only_cells_that_differ_from_the_reading_change(self):
        changed = {(c.key.room, S.season_of(c.key.date)) for c in self.plan.changes}
        self.assertEqual(changed, {("디럭스", "성수기"), ("스위트", "비수기"), ("스위트", "성수기")})
        self.assertEqual(len(self.plan.changes), 7 * 4 + 13 * 4)
        self.assertTrue(self.plan.request.from_sheet)
        change = next(c for c in self.plan.changes if c.key == CellKey("디럭스", S.PLAN, "2027-01-15", "A2C1_CHD", 1))
        self.assertEqual((change.before.sell, change.after.sell), (D("315.00"), D("330.00")))

    def test_the_coverage_names_every_kind_of_cell_the_sheet_leaves_out(self):
        gaps = {(gap.kind, gap.room, gap.occupancy, gap.nights): gap for gap in self.plan.coverage}
        untouched = gaps[("untouched", "스위트", "A1", 1)]
        self.assertEqual(untouched.dates, tuple(day for day in S.DAYS if day != "2027-01-13"))
        self.assertEqual(gaps[("no_sale", "스위트", None, None)].dates, ("2027-01-13",))
        self.assertIn(("unnamed", "패밀리", None, None), gaps)
        self.assertEqual(coverage_counts(self.plan.coverage), {"untouched": 13, "unseen": 0, "no_sale": 1, "unknown": 0, "unnamed": 1})

    def test_rows_the_reading_never_shows_are_reported_and_not_created(self):
        """R6 — 그 객실 · 요금제에 읽힌 적 없는 인원 · 박수는 새 종류의 칸이라 만들지 않는다."""
        data = S.sheet_data()
        data["lines"][0]["rows"].append({"occupancy": "A4", "nights": 1, "sell": {"from": {"occupancy": "A2"}, "add": "120"}})
        plan = plan_sheet(S.reading(), SheetCheck(decode_sheet(data), PAIRS))
        self.assertFalse([c for c in plan.changes if c.key.occupancy == "A4"])
        unseen = [gap for gap in plan.coverage if gap.kind == "unseen"]
        self.assertEqual([(g.room, g.occupancy, g.nights, g.lines, len(g.dates)) for g in unseen], [("디럭스", "A4", 1, (1,), 5)])

    def test_a_day_with_a_row_but_no_price_gets_a_new_cell(self):
        reading = S.reading()
        key = CellKey("디럭스", S.PLAN, "2027-01-12", "A3", 1)
        plan = plan_sheet(replace(reading, cells={**reading.cells, key: MISSING}), self.check)
        change = next(c for c in plan.changes if c.key == key)
        self.assertEqual((change.marks, change.after.sell), (("new",), D("320.00")))

    def test_rooms_the_hotel_lacks_are_reported_and_left_out_of_the_range(self):
        data = S.sheet_data()
        data["lines"].append(dict(copy.deepcopy(data["lines"][0]), room="디럭스", rate_plan="룸온리"))
        data["lines"].append(dict(copy.deepcopy(data["lines"][0]), room="펜트하우스"))
        check = SheetCheck(decode_sheet(data), PAIRS)
        self.assertEqual([(g.kind, g.room, g.rate_plan, g.lines) for g in check.gaps],
                         [("unknown", "디럭스", "룸온리", (9,)), ("unknown", "펜트하우스", S.PLAN, (10,)),
                          ("unnamed", "패밀리", S.PLAN, ())])
        self.assertEqual(check.range.pairs, (("디럭스", S.PLAN), ("스위트", S.PLAN)))
        self.assertEqual(coverage_counts(plan_sheet(S.reading(), check).coverage)["unknown"], 2)

    def test_the_save_steps_are_one_per_pair_and_identical_rows(self):
        self.assertEqual(unresolved(self.plan), ())
        steps = plan_steps(self.plan)
        self.assertEqual([(s.room, s.dates) for s in steps], [
            ("디럭스", ("2027-01-11", "2027-01-12", "2027-01-13", "2027-01-14", "2027-01-17")),
            ("디럭스", ("2027-01-15", "2027-01-16")),
            ("스위트", ("2027-01-04", "2027-01-05", "2027-01-06", "2027-01-07", "2027-01-10")),
            ("스위트", ("2027-01-08", "2027-01-09")),
            ("스위트", ("2027-01-11", "2027-01-12", "2027-01-14", "2027-01-17")),
            ("스위트", ("2027-01-15", "2027-01-16"))])
        self.assertEqual({(r.occupancy, r.nights): r.sell for r in steps[1].rows},
                         {("A2", 1): D("300.00"), ("A2", 3): D("270.00"), ("A3", 1): D("360.00"), ("A2C1_CHD", 1): D("330.00")})

    def test_a_reading_of_another_currency_or_range_is_refused(self):
        with self.assertRaises(Refused) as caught:
            plan_sheet(replace(S.reading(), currency="KRW"), self.check)
        self.assertIn("요금표의 통화는 USD 인데 ERP 의 이 오퍼는 KRW", str(caught.exception))
        short = S.reading()
        short = replace(short, dates=S.DAYS[:-1], cells={k: v for k, v in short.cells.items() if k.date != S.DAYS[-1]})
        with self.assertRaises(Refused) as caught:
            plan_sheet(short, self.check)
        self.assertIn("읽은 값에 없는 날짜: 2027-01-17", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
