#!/usr/bin/env python3
"""가격 캘린더 일괄 단계(`선택 날짜 가격 수정` · `선택 날짜 가격 가감`)와 연령 구간 빈 나이 검사 시험 (2026-11-13).

실행:
    python3 -m unittest discover -s skills/stay-setup-guide/tests -v
"""
import datetime
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.normpath(os.path.join(HERE, os.pardir))
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import check_manual as cm  # noqa: E402

EXAMPLE = os.path.join(SKILL, "examples", "우에노_토우가네야", "_원고", "manual.md")
TODAY = datetime.date(2026, 11, 13)


def steps_of(text):
    return cm.parse_steps(text.splitlines())


def table(rows):
    return "\n".join(f"| {k} | {v} |" for k, v in rows)


PRICE_ROWS = [
    ("오퍼", "선택: 2026~2027 시즌 요금"),
    ("객실", "선택: Single"),
    ("요금제", "선택: 룸온리"),
    ("시작일", "2026-12-01"),
    ("종료일", "2026-12-31"),
    ("요일", "선택: 월, 화, 수, 목, 금, 토, 일"),
    ("연동 방식", "선택: 기준 조합만 입력 — 나머지는 현재 차액 유지"),
    ("기준 조합", "선택: A1 · 성인 1"),
    ("A1 · 1박 이상 · 판매가", "9800"),
    ("A1 · 1박 이상 · 정가", "비움"),
    ("A1 · 1박 이상 · 공급 원가", "비움"),
    ("A1C1_CHD · 1박 이상 · 판매가 차액", "+2500"),
]

ADJUST_ROWS = [
    ("오퍼", "선택: 2026~2027 시즌 요금"),
    ("객실", "선택: Single, Twin"),
    ("요금제", "선택: 룸온리"),
    ("시작일", "2026-12-01"),
    ("종료일", "2026-12-31"),
    ("요일", "선택: 금, 토"),
    ("인원 조합", "선택: A1, A2"),
    ("박수 층", "선택: 전 층"),
    ("가감", "+5%"),
    ("정가도 같이 조정", "해제"),
    ("날짜별로 직접 고친 가격도 같이 바꾸기", "해제"),
    ("추가 인원 요금도 같이 조정", "해제"),
]


def price_step(num, rows=None):
    return f"""
## {num}. 선택 날짜 가격 수정 (1번째, Single × 룸온리 · 2026-12-01 ~ 2026-12-31)
탭: `가격 캘린더`
버튼: [선택 날짜 가격 수정]

| 칸 | 값 |
|---|---|
{table(rows if rows is not None else PRICE_ROWS)}

→ [입력한 가격 적용]
"""


def adjust_step(num, rows=None):
    return f"""
## {num}. 선택 날짜 가격 가감 (1번째, 2026~2027 시즌 요금 · 2026-12-01 ~ 2026-12-31 · +5%)
탭: `가격 캘린더`
버튼: [선택 날짜 가격 가감]

| 칸 | 값 |
|---|---|
{table(rows if rows is not None else ADJUST_ROWS)}

→ [가감 적용]
"""


def replace(rows, name, value):
    """줄 하나의 값을 바꾼다. `value` 가 None 이면 그 줄을 뺀다."""
    out = []
    for k, v in rows:
        if k == name:
            if value is not None:
                out.append((k, value))
        else:
            out.append((k, v))
    return out


def price_problems(rows):
    return cm.find_calendar_price_gaps(steps_of(price_step(4, rows)), TODAY)


def adjust_result(rows):
    return cm.find_calendar_adjust_gaps(steps_of(adjust_step(4, rows)), TODAY)


def with_example(extra):
    """예시 원고의 `부과금 추가` 앞(시즌 가격 채우기 뒤)에 단계를 끼워 넣고 번호를 다시 매긴다."""
    with open(EXAMPLE, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    added = [ln for ln in extra.strip("\n").split("\n")]
    n_extra = sum(1 for ln in added if re.match(r"^## \d+\.", ln))
    out, inserted = [], False
    for line in lines:
        m = re.match(r"^## (\d+)\.(.*)$", line)
        if m and int(m.group(1)) == 50 and not inserted:
            k = 50
            for ln in added:
                mm = re.match(r"^## \d+\.(.*)$", ln)
                if mm:
                    out.append(f"## {k}.{mm.group(1)}")
                    k += 1
                else:
                    out.append(ln)
            out.append("")
            inserted = True
        if m and int(m.group(1)) >= 50:
            line = f"## {int(m.group(1)) + n_extra}.{m.group(2)}"
        out.append(line)
    return "\n".join(out)


class KindListTest(unittest.TestCase):
    def test_both_kinds_are_canonical(self):
        for kind in cm.CALENDAR_STEP_KINDS:
            self.assertIn(kind, cm.STEP_KINDS)

    def test_step_kinds_table_maps_the_screens(self):
        import json
        with open(os.path.join(SKILL, "references", "step-kinds.json"), encoding="utf-8") as handle:
            kinds = json.load(handle)["kinds"]
        self.assertEqual(kinds["선택 날짜 가격 수정"]["screens"], ["calendar-bulk"])
        self.assertEqual(kinds["선택 날짜 가격 가감"]["screens"], ["calendar-adjust"])


class CalendarPriceTest(unittest.TestCase):
    def test_contract_example_passes(self):
        self.assertEqual(price_problems(PRICE_ROWS), [])

    def test_manual_mode_passes_with_plain_columns(self):
        rows = replace(PRICE_ROWS, "연동 방식", "선택: 조합마다 직접 입력")
        rows = replace(rows, "기준 조합", None)
        rows = replace(rows, "A1C1_CHD · 1박 이상 · 판매가 차액", None) + [("A1C1_CHD · 1박 이상 · 판매가", "12,300")]
        self.assertEqual(price_problems(rows), [])

    def test_link_head_fragment_is_accepted(self):
        rows = replace(PRICE_ROWS, "연동 방식", "선택: 기준 조합만 입력")
        self.assertEqual(price_problems(rows), [])

    def test_commas_and_signs(self):
        rows = replace(PRICE_ROWS, "A1 · 1박 이상 · 판매가", "9,800")
        rows = replace(rows, "A1C1_CHD · 1박 이상 · 판매가 차액", "+2,500")
        self.assertEqual(price_problems(rows), [])
        for bad in ("+9800", "9,80", "98.123", "-1"):
            got = price_problems(replace(PRICE_ROWS, "A1 · 1박 이상 · 판매가", bad))
            self.assertTrue(any("부호 없는 새 값" in p for p in got), (bad, got))
        for bad in ("2500", "+2,50", "+1.234"):
            got = price_problems(replace(PRICE_ROWS, "A1C1_CHD · 1박 이상 · 판매가 차액", bad))
            self.assertTrue(any("부호를 붙인 차액" in p for p in got), (bad, got))
        self.assertEqual(price_problems(replace(PRICE_ROWS, "A1C1_CHD · 1박 이상 · 판매가 차액", "0")), [])

    def test_link_mode_is_required(self):
        got = price_problems(replace(PRICE_ROWS, "연동 방식", None))
        self.assertTrue(any("`연동 방식`" in p for p in got), got)
        got = price_problems(replace(PRICE_ROWS, "연동 방식", "선택: 기준만"))
        self.assertTrue(any("`연동 방식`" in p for p in got), got)

    def test_base_mode_needs_base_key_and_its_price(self):
        got = price_problems(replace(PRICE_ROWS, "기준 조합", None))
        self.assertTrue(any("`기준 조합` 줄을" in p for p in got), got)
        got = price_problems(replace(PRICE_ROWS, "A1 · 1박 이상 · 판매가", "비움"))
        self.assertTrue(any("비었다" in p for p in got), got)
        got = price_problems(replace(PRICE_ROWS, "A1 · 1박 이상 · 판매가", None))
        self.assertTrue(any("`판매가` 줄이 없다" in p for p in got), got)

    def test_base_mode_columns(self):
        rows = PRICE_ROWS + [("A1C1_CHD · 1박 이상 · 정가", "12000")]
        got = price_problems(rows)
        self.assertTrue(any("기준이 아닌 줄은 차액 열" in p for p in got), got)
        rows = PRICE_ROWS + [("A1 · 1박 이상 · 정가 차액", "+100")]
        rows = replace(rows, "A1 · 1박 이상 · 정가", None)
        got = price_problems(rows)
        self.assertTrue(any("기준 조합 줄은 새 값 열" in p for p in got), got)

    def test_manual_mode_rules(self):
        rows = replace(PRICE_ROWS, "연동 방식", "선택: 조합마다 직접 입력")
        got = price_problems(rows)
        self.assertTrue(any("`기준 조합` 줄을 쓰지 않는다" in p for p in got), got)
        self.assertTrue(any("차액 열은" in p for p in got), got)
        empty = [r for r in rows if r[0] not in ("기준 조합", "A1C1_CHD · 1박 이상 · 판매가 차액")]
        empty = replace(empty, "A1 · 1박 이상 · 판매가", "비움")
        got = price_problems(empty)
        self.assertTrue(any("저장할 것이 없다" in p for p in got), got)

    def test_one_room_and_one_plan(self):
        got = price_problems(replace(PRICE_ROWS, "객실", "선택: Single, Twin"))
        self.assertTrue(any("객실 하나" in p for p in got), got)
        got = price_problems(replace(PRICE_ROWS, "요금제", "선택: 룸온리, 조식 포함"))
        self.assertTrue(any("요금제 하나" in p for p in got), got)

    def test_line_names(self):
        for bad in ("A1 · 판매가", "A1 1박 이상 · 판매가", "A1 · 1박~ · 판매가", "A1 · 1박 이상 · 원가"):
            got = price_problems(PRICE_ROWS + [(bad, "100")])
            self.assertTrue(any("이 단계의 줄이 아니다" in p for p in got), (bad, got))
        got = price_problems(PRICE_ROWS + [("2 · 1박 이상 · 판매가 차액", "+1")])
        self.assertTrue(any("옛 숫자 표기" in p for p in got), got)
        got = price_problems(PRICE_ROWS + [("a2 · 1박 이상 · 판매가 차액", "+1")])
        self.assertTrue(any("대문자" in p for p in got), got)
        got = price_problems(PRICE_ROWS + [("A2 · 31박 이상 · 판매가 차액", "+1")])
        self.assertTrue(any("1~30" in p for p in got), got)
        got = price_problems(PRICE_ROWS + [("인원 무관 단일가 · 1박 이상 · 판매가 차액", "+1")])
        self.assertEqual(got, [])

    def test_duplicate_line_is_an_error(self):
        got = price_problems(PRICE_ROWS + [("A1C1_CHD · 1박 이상 · 판매가 차액", "+3000")])
        self.assertTrue(any("2번 적혔다" in p for p in got), got)

    def test_original_below_price(self):
        got = price_problems(replace(PRICE_ROWS, "A1 · 1박 이상 · 정가", "9000"))
        self.assertTrue(any("정가 9000 가 판매가 9800 보다 작다" in p for p in got), got)

    def test_period_rules(self):
        got = price_problems(replace(PRICE_ROWS, "요일", "비움"))
        self.assertTrue(any("`요일`" in p for p in got), got)
        got = price_problems(replace(PRICE_ROWS, "종료일", "2026-11-30"))
        self.assertTrue(any("보다 앞이다" in p for p in got), got)
        got = price_problems(replace(PRICE_ROWS, "종료일", "2028-07-01"))
        self.assertTrue(any("550일까지" in p for p in got), got)
        got = price_problems(replace(replace(PRICE_ROWS, "종료일", "2026-12-04"), "요일", "선택: 토, 일"))
        self.assertTrue(any("하루도 없다" in p for p in got), got)  # 12-01(화)~12-04(금)
        got = price_problems(replace(PRICE_ROWS, "시작일", "2026-12-1"))
        self.assertTrue(any("`시작일` 은 `YYYY-MM-DD`" in p for p in got), got)

    def test_past_only_step_is_an_error(self):
        rows = replace(replace(PRICE_ROWS, "시작일", "2026-10-01"), "종료일", "2026-10-31")
        got = price_problems(rows)
        self.assertTrue(any("작성일(2026-11-13)보다 앞" in p for p in got), got)


class CalendarAdjustTest(unittest.TestCase):
    def test_contract_example_passes(self):
        self.assertEqual(adjust_result(ADJUST_ROWS), ([], []))

    def test_adjust_values(self):
        for good in ("+12", "-5%", "+1,000", "-12.5", "+0.25%", "-100%"):
            self.assertEqual(adjust_result(replace(ADJUST_ROWS, "가감", good))[0], [], good)
        for bad, why in (("12", "부호를"), ("+0", "0이다"), ("-0%", "0이다"), ("+1.234", "소수 둘째"),
                         ("-101%", "-100%"), ("+1,00", "부호를"), ("비움", "부호를")):
            got = adjust_result(replace(ADJUST_ROWS, "가감", bad))[0]
            self.assertTrue(any(why in p for p in got), (bad, got))

    def test_flat_with_extra_people_check_warns(self):
        rows = replace(replace(ADJUST_ROWS, "가감", "+1000"), "추가 인원 요금도 같이 조정", "체크")
        problems, warnings = adjust_result(rows)
        self.assertEqual(problems, [])
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("정률(%)일 때만", warnings[0])
        rows = replace(ADJUST_ROWS, "추가 인원 요금도 같이 조정", "체크")
        self.assertEqual(adjust_result(rows), ([], []))

    def test_every_line_is_required_and_no_others(self):
        got = adjust_result(replace(ADJUST_ROWS, "박수 층", None))[0]
        self.assertTrue(any("줄이 빠졌다" in p for p in got), got)
        got = adjust_result(ADJUST_ROWS + [("판매가", "100")])[0]
        self.assertTrue(any("이 단계의 줄이 아니다" in p for p in got), got)

    def test_choices(self):
        got = adjust_result(replace(ADJUST_ROWS, "박수 층", "선택: 2박 층"))[0]
        self.assertTrue(any("`박수 층`" in p for p in got), got)
        got = adjust_result(replace(ADJUST_ROWS, "정가도 같이 조정", "선택: 예"))[0]
        self.assertTrue(any("`체크` / `해제`" in p for p in got), got)
        got = adjust_result(replace(ADJUST_ROWS, "객실", "비움"))[0]
        self.assertTrue(any("`객실`" in p for p in got), got)
        got = adjust_result(replace(ADJUST_ROWS, "오퍼", "선택: A, B"))[0]
        self.assertTrue(any("오퍼 하나" in p for p in got), got)
        got = adjust_result(replace(ADJUST_ROWS, "인원 조합", "선택: A2 · 성인 2, 3 · 3인"))[0]
        self.assertTrue(any("옛 숫자 표기" in p for p in got), got)
        self.assertEqual(adjust_result(replace(ADJUST_ROWS, "인원 조합", "선택: A2 · 성인 2, A2C1_CHD · 소아 1"))[0], [])


class CalendarStepsInGuideTest(unittest.TestCase):
    """예시 원고에 두 단계를 끼워 넣어도 검사 전체가 통과한다 — 사전·반복 행·좌표·인원 조합 검사가 새 줄을 오해하지 않는다."""

    def run_check(self, md):
        with tempfile.TemporaryDirectory() as d:
            share = os.path.join(d, "우에노_토우가네야", "_원고")
            os.makedirs(share)
            path = os.path.join(share, "manual.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(md)
            return cm.check(path, share_name="우에노_토우가네야", dictionary_path=os.path.join(SKILL, "references", "screen-dictionary.json")), cm.main([path])

    def test_example_with_both_steps_is_all_ok(self):
        md = with_example(price_step(1) + adjust_step(2))
        r, code = self.run_check(md)
        self.assertEqual(code, 0)
        self.assertEqual(r["calendar_price_gaps"] + r["calendar_adjust_gaps"], [])
        self.assertEqual(r["unknown_fields"], [], r["unknown_fields"])
        self.assertEqual(r["off_screen_fields"], [], r["off_screen_fields"])
        self.assertEqual(r["sheet_cells"], [])
        self.assertEqual(r["repeat_row_formats"], [])
        self.assertEqual(r["calendar_step_order"], [])

    def test_season_fill_after_the_step_warns(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            text = handle.read()
        # 예시의 시즌 가격 채우기 32단계 앞으로 가감을 옮긴다 — 그 뒤에 같은 오퍼의 채우기가 온다
        steps = steps_of(text)
        steps.insert(0, steps_of(adjust_step(1))[0])
        got = cm.find_calendar_step_order(steps)
        self.assertTrue(got and "시즌 가격 채우기" in got[0], got)

    def test_example_manual_is_unchanged_and_still_ok(self):
        self.assertEqual(cm.main([EXAMPLE]), 0)


def band(num, name, code, low, high, card="`2026 시즌 요금`"):
    return f"""
## {num}. 연령 구간 만들기 ({num}번째, {name})
탭: `오퍼`
카드: {card}
버튼: [연령 구간 추가]

| 칸 | 값 |
|---|---|
| 밴드 코드 | {code} |
| 노출명 | {name} |
| 최소 연령 (만 나이) | {low} |
| 최대 연령 (만 나이) | {high} |
| 요금 기준 유형 | 선택: 무료 |

→ [추가]
"""


class AgeBandCoverageTest(unittest.TestCase):
    """ERP `age_band.age_coverage` 와 같은 판정 — 빈 나이·겹침이면 [판매 시작] 이 막힌다."""

    def problems(self, md):
        return cm.find_age_band_coverage(steps_of(md))

    def test_continuous_bands_pass(self):
        self.assertEqual(self.problems(band(5, "유아", "INF", "0", "4.99") + band(6, "소아", "CHD", "5", "11.99")), [])

    def test_gap_is_reported_with_erp_words(self):
        got = self.problems(band(5, "유아", "INF", "0", "3") + band(6, "소아", "CHD", "5", "11"))
        self.assertEqual(len(got), 1, got)
        self.assertIn("만 4세가 어느 구간에도 없습니다. 이 나이는 성인 요금으로 계산됩니다.", got[0])
        self.assertIn("'성인 요금의 100%' 구간", got[0])
        self.assertIn("`2026 시즌 요금`", got[0])

    def test_spans_are_folded(self):
        got = self.problems(band(5, "유아", "INF", "0", "3") + band(6, "소아", "CHD", "6", "8") + band(7, "청소년", "TEEN", "11", "15"))
        self.assertIn("만 4~5세, 만 9~10세가", got[0])

    def test_first_band_not_from_zero_is_a_gap(self):
        got = self.problems(band(5, "소아", "CHD", "2", "11.99"))
        self.assertIn("만 0~1세가", got[0])

    def test_overlap_is_reported(self):
        got = self.problems(band(5, "유아", "INF", "0", "6") + band(6, "소아", "CHD", "6", "11.99"))
        self.assertEqual(len(got), 1, got)
        self.assertIn("만 6세가 두 구간에 겹칩니다. 한 구간에만 들어가게 고쳐 주세요.", got[0])

    def test_fractional_edges_cover_integer_ages(self):
        """`0~5.5` · `5.6~11` 은 정수 나이로 빈 곳이 없다(엔진은 나이를 정수로 받는다)."""
        self.assertEqual(self.problems(band(5, "유아", "INF", "0", "5.5") + band(6, "소아", "CHD", "5.6", "11")), [])

    def test_offers_are_separate(self):
        md = band(5, "유아", "INF", "0", "4.99") + band(6, "소아", "CHD", "5", "11.99", card="`2027 시즌 요금`")
        got = self.problems(md)
        self.assertEqual(len(got), 1, got)
        self.assertIn("2027 시즌 요금", got[0])
        self.assertIn("만 0~4세가", got[0])

    def test_it_fails_the_check(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("# 시험 호텔\n" + band(1, "유아", "INF", "0", "3") + band(2, "소아", "CHD", "5", "11"))
            self.assertEqual(len(cm.check(path)["age_band_coverage"]), 1)
            self.assertEqual(cm.main([path]), 1)

    def test_example_manual_has_no_gap(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(self.problems(handle.read()), [])


if __name__ == "__main__":
    unittest.main()
