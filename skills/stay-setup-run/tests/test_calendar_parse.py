#!/usr/bin/env python3
"""parse_guide.py — 가격 캘린더 일괄 단계(2026-11-13)와 연령 구간 빈 나이 훑기.

    python3 -m unittest discover -s skills/stay-setup-run/tests
"""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "parse_guide.py"
REPO = HERE.parents[2]
RENDER = REPO / "skills" / "stay-setup-guide" / "scripts" / "render_card.py"

sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(RENDER.parent))
import parse_guide  # noqa: E402
import render_card  # noqa: E402

PRICE = """
## 50. 선택 날짜 가격 수정 (1번째, Single × 룸온리 · 2026-12-01 ~ 2026-12-31)
탭: `가격 캘린더`
버튼: [선택 날짜 가격 수정]

| 칸 | 값 |
|---|---|
| 오퍼 | 선택: 2026~2027 시즌 요금 |
| 객실 | 선택: Single |
| 요금제 | 선택: 룸온리 |
| 시작일 | 2026-12-01 |
| 종료일 | 2026-12-31 |
| 요일 | 선택: 월, 화, 수, 목, 금, 토, 일 |
| 연동 방식 | 선택: 기준 조합만 입력 — 나머지는 현재 차액 유지 |
| 기준 조합 | 선택: A1 · 성인 1 |
| A1 · 1박 이상 · 판매가 | 9,800 |
| A1 · 1박 이상 · 정가 | 비움 |
| 인원 무관 단일가 · 3박 이상 · 공급 원가 차액 | -1,000 |
| A1C1_CHD · 1박 이상 · 판매가 차액 | +2500 |

→ [입력한 가격 적용]
"""

ADJUST = """
## 51. 선택 날짜 가격 가감 (1번째, 2026~2027 시즌 요금 · +5%)
탭: `가격 캘린더`
버튼: [선택 날짜 가격 가감]

| 칸 | 값 |
|---|---|
| 오퍼 | 선택: 2026~2027 시즌 요금 |
| 객실 | 선택: Single, Twin |
| 요금제 | 선택: 룸온리 |
| 시작일 | 2026-12-01 |
| 종료일 | 2026-12-31 |
| 요일 | 선택: 금, 토 |
| 인원 조합 | 선택: A1, A2 |
| 박수 층 | 선택: 전 층 |
| 가감 | +5% |
| 정가도 같이 조정 | 해제 |
| 날짜별로 직접 고친 가격도 같이 바꾸기 | 해제 |
| 추가 인원 요금도 같이 조정 | 해제 |

→ [가감 적용]
"""


def steps_of(md):
    _title, raws = parse_guide.parse_markdown("# 시험 호텔\n" + md)
    return [parse_guide.build_step(r) for r in raws]


def field(step, label):
    return next(f for f in step["fields"] if f["label"] == label)


def problem(md):
    return parse_guide.calendar_step_problem(steps_of(md)[0])


class TestCalendarKinds(unittest.TestCase):
    def test_kinds_are_known(self):
        for kind in ("선택 날짜 가격 수정", "선택 날짜 가격 가감"):
            self.assertIn(kind, parse_guide.KNOWN_KINDS)
        pre = parse_guide.preflight(steps_of(PRICE + ADJUST))
        self.assertEqual(pre["unknown_kinds"], [])
        self.assertEqual(pre["value_format"], [])

    def test_price_lines_carry_screen_hooks(self):
        step = steps_of(PRICE)[0]
        base = field(step, "A1 · 1박 이상 · 판매가")
        self.assertEqual((base["field"], base["occupancy_key"], base["los_nights"], base["field_col"]), ("prices", "A1", 1, "price"))
        self.assertEqual(base["value"], "9800")           # 쉼표를 뗐다 — 묶음 전 화면의 type=number 칸
        self.assertEqual(base["raw_value"], "9,800")      # 원문은 그대로
        blank = field(step, "인원 무관 단일가 · 3박 이상 · 공급 원가 차액")
        self.assertEqual((blank["occupancy_key"], blank["los_nights"], blank["field_col"], blank["value"]), ("", 3, "net_amount_diff", "-1000"))
        diff = field(step, "A1C1_CHD · 1박 이상 · 판매가 차액")
        self.assertEqual(diff["field_col"], "price_diff")
        empty = field(step, "A1 · 1박 이상 · 정가")
        self.assertEqual((empty["kind"], empty["field_col"]), ("empty", "original_price"))
        for label in ("오퍼", "객실", "연동 방식"):
            self.assertNotIn("occupancy_key", field(step, label))

    def test_other_kinds_are_not_annotated(self):
        """같은 꼴의 줄이 다른 갈래에 있어도 표식을 달지 않는다(그 줄은 그 갈래의 칸이 아니다)."""
        md = PRICE.replace("선택 날짜 가격 수정 (1번째", "가격 셀 손으로 고치기 (1번째")
        step = steps_of(md)[0]
        self.assertNotIn("field_col", field(step, "A1 · 1박 이상 · 판매가"))

    def test_rendered_html_keeps_the_hooks(self):
        """지시서 HTML 을 거쳐도(실행 입력) 같은 표식이 나온다."""
        md = "# 시험 호텔\n" + PRICE
        html, _ = render_card.render_card(md, "manual.md", None, None, None,
                                          render_card.build_stamp(hashlib.sha256(md.encode()).hexdigest(), True))
        _title, raws = parse_guide.parse_html(html)
        step = parse_guide.build_step(raws[0])
        diff = field(step, "A1C1_CHD · 1박 이상 · 판매가 차액")
        self.assertEqual((diff["field"], diff["occupancy_key"], diff["field_col"], diff["value"]), ("prices", "A1C1_CHD", "price_diff", "+2500"))


class TestCalendarPreflight(unittest.TestCase):
    def test_contract_examples_pass(self):
        self.assertIsNone(problem(PRICE))
        self.assertIsNone(problem(ADJUST))

    def test_price_problems(self):
        cases = [
            (PRICE.replace("| 연동 방식 | 선택: 기준 조합만 입력 — 나머지는 현재 차액 유지 |", "| 연동 방식 | 선택: 아무거나 |"), "연동 방식"),
            (PRICE.replace("| 기준 조합 | 선택: A1 · 성인 1 |\n", ""), "기준 조합"),
            (PRICE.replace("| A1 · 1박 이상 · 판매가 | 9,800 |", "| A1 · 1박 이상 · 판매가 | 비움 |"), "판매가"),
            (PRICE.replace("+2500", "2500"), "차액"),
            (PRICE.replace("| 9,800 |", "| +9800 |"), "새 값"),
            (PRICE + "", None),
            (PRICE.replace("| 객실 | 선택: Single |", "| 객실 | 선택: Single, Twin |"), "객실"),
            (PRICE.replace("| A1C1_CHD · 1박 이상 · 판매가 차액 | +2500 |", "| A1C1_CHD · 1박 이상 · 판매가 | 2500 |"), "차액 열"),
            (PRICE.replace("| A1 · 1박 이상 · 정가 | 비움 |", "| A1 · 정가 | 비움 |"), "이 단계의 줄이 아닙니다"),
        ]
        for md, want in cases:
            got = problem(md)
            if want is None:
                self.assertIsNone(got)
            else:
                self.assertIsNotNone(got, want)
                self.assertIn(want, got)

    def test_manual_mode(self):
        md = (PRICE.replace("기준 조합만 입력 — 나머지는 현재 차액 유지", "조합마다 직접 입력")
              .replace("| 기준 조합 | 선택: A1 · 성인 1 |\n", "")
              .replace("| 인원 무관 단일가 · 3박 이상 · 공급 원가 차액 | -1,000 |\n", "")
              .replace("| A1C1_CHD · 1박 이상 · 판매가 차액 | +2500 |", "| A1C1_CHD · 1박 이상 · 판매가 | 12300 |"))
        self.assertIsNone(problem(md))
        self.assertIn("기준 조합", problem(md.replace("| A1 · 1박 이상 · 판매가 |", "| 기준 조합 | 선택: A1 |\n| A1 · 1박 이상 · 판매가 |")))

    def test_adjust_problems(self):
        cases = [
            (ADJUST.replace("| 가감 | +5% |", "| 가감 | 5% |"), "가감"),
            (ADJUST.replace("| 가감 | +5% |", "| 가감 | +0 |"), "0"),
            (ADJUST.replace("| 가감 | +5% |", "| 가감 | -150% |"), "-100%"),
            (ADJUST.replace("| 박수 층 | 선택: 전 층 |", "| 박수 층 | 선택: 2박 |"), "박수 층"),
            (ADJUST.replace("| 정가도 같이 조정 | 해제 |\n", ""), "빠졌습니다"),
            (ADJUST.replace("| 정가도 같이 조정 | 해제 |", "| 정가도 같이 조정 | 선택: 예 |"), "체크"),
            (ADJUST + "", None),
            (ADJUST.replace("| 가감 | +5% |", "| 가감 | +1,000 |"), None),
        ]
        for md, want in cases:
            got = problem(md)
            if want is None:
                self.assertIsNone(got, md)
            else:
                self.assertIsNotNone(got, want)
                self.assertIn(want, got)


def band(no, name, lo, hi, card="2026 계약"):
    return f"""
## {no}. 연령 구간 만들기 ({no}번째, {name})
탭: `오퍼`
카드: `{card}`
버튼: [연령 구간 추가]

| 칸 | 값 |
|---|---|
| 밴드 코드 | {name.upper()} |
| 노출명 | {name} |
| 최소 연령 (만 나이) | {lo} |
| 최대 연령 (만 나이) | {hi} |

→ [추가]
"""


class TestAgeBandGap(unittest.TestCase):
    def test_gap_blocks_like_the_erp(self):
        gaps = parse_guide.preflight(steps_of(band(5, "inf", "0", "3") + band(6, "chd", "5", "11.99")))["age_gap"]
        self.assertEqual(len(gaps), 1, gaps)
        self.assertIn("만 4세가 어느 구간에도 없습니다", gaps[0]["why"])
        self.assertIn("[판매 시작]", gaps[0]["why"])

    def test_continuous_bands_pass(self):
        self.assertEqual(parse_guide.preflight(steps_of(band(5, "inf", "0", "4.99") + band(6, "chd", "5", "11.99")))["age_gap"], [])

    def test_offers_are_separate(self):
        md = band(5, "inf", "0", "4.99") + band(6, "chd", "5", "11.99", card="2027 계약")
        gaps = parse_guide.preflight(steps_of(md))["age_gap"]
        self.assertEqual(len(gaps), 1, gaps)
        self.assertIn("만 0~4세가", gaps[0]["why"])

    def test_summary_counts_it_as_blocking(self):
        doc = {"guide": {"preflight": parse_guide.preflight(steps_of(band(5, "inf", "0", "3") + band(6, "chd", "5", "11.99")))},
               "steps": steps_of(band(5, "inf", "0", "3") + band(6, "chd", "5", "11.99"))}
        text, _unknown, _missing, blocking = parse_guide.summarize(doc)
        self.assertGreaterEqual(blocking, 1)
        self.assertIn("연령 구간에 빈 나이가 있는 오퍼: 1", text)

    def test_old_steps_json_without_the_key_still_summarizes(self):
        doc = {"guide": {"preflight": {"stale": [], "unknown_kinds": [], "charge_order": [], "age_overlap": []}}, "steps": []}
        text, *_ = parse_guide.summarize(doc)
        self.assertIn("연령 구간에 빈 나이가 있는 오퍼: 0", text)


if __name__ == "__main__":
    unittest.main()
