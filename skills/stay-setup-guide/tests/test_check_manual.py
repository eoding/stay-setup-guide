#!/usr/bin/env python3
"""check_manual.py 검사 규칙 시험.

실행:
    python3 -m unittest discover -s skills/stay-setup-guide/tests -v
    (또는 pytest skills/stay-setup-guide/tests)
"""
import datetime
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.normpath(os.path.join(HERE, os.pardir))
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import check_manual as cm  # noqa: E402

#: 예시 공유 폴더와 그 안의 원고. 원고는 `_원고/` 에 살고, 담당자에게 가는 지시서 HTML 은 맨 위에 있다.
EXAMPLE_SHARE = os.path.join(SKILL, "examples", "우에노_토우가네야")
EXAMPLE = os.path.join(EXAMPLE_SHARE, "_원고", "manual.md")
DICTIONARY = os.path.join(SKILL, "references", "screen-dictionary.json")

HEAD = """# 시험 호텔 — 입력 지시서

## 1. 환율 확인
화면: 환율 관리

| 칸 | 값 |
|---|---|
| 통화 | 선택: JPY |

→ [목록]

## 2. 거래처 확인
화면: 거래처 목록

| 칸 | 값 |
|---|---|
| 거래처 | 자사 |

→ [목록]

## 3. 도시 확인
화면: 호텔 만들기

| 칸 | 값 |
|---|---|
| 도시 | 선택: 도쿄(TYO) |

→ [목록]
"""


def season_step(num, name, card, rows, save="추가"):
    body = "\n".join(f"| {k} | {v} |" for k, v in rows)
    return f"""
## {num}. 시즌 만들기 ({num}번째, {name})
탭: `시즌`
카드: `{card}`
버튼: [시즌 추가]

| 칸 | 값 |
|---|---|
| 시즌명 | {name} |
{body}

→ [{save}]
"""


def fill_step(num, season, room, overwrite="해제", target=None):
    target_row = f"| 대상 룸 | 선택: {target} |\n" if target else ""
    return f"""
## {num}. 시즌 가격 채우기 ({num}회차, {season} × {room})
탭: `시즌`
카드: `{season}`
버튼: [가격]

| 칸 | 값 |
|---|---|
| 판매 단가(공급 통화) | 100 |
{target_row}| 이미 값이 있는 날도 덮기 | {overwrite} |

→ [이 단가로 깔기]
"""


def listed_season(num, name, card, days, save="추가"):
    """`날짜 나열:` 을 표가 아니라 라벨 줄 + 펜스 블록으로 적은 시즌(실제 지시서 표기)."""
    body = "\n".join(days)
    return f"""
## {num}. 시즌 만들기 ({num}번째, {name})
탭: `시즌`
카드: `{card}`
버튼: [시즌 추가]

| 칸 | 값 |
|---|---|
| 시즌명 | {name} |
| 날짜 규칙 유형 | 선택: 비연속 날짜 나열 |
| 우선순위 | 10 |

날짜 나열:
```
{body}
```

→ [{save}]
"""


RANGE = [("날짜 규칙 유형", "선택: 기간 범위"), ("기간 시작", "2026-01-01"), ("기간 종료", "2026-12-31")]
INSIDE = [("날짜 규칙 유형", "선택: 기간 범위"), ("기간 시작", "2026-07-01"), ("기간 종료", "2026-07-10")]
OUTSIDE = [("날짜 규칙 유형", "선택: 기간 범위"), ("기간 시작", "2027-07-01"), ("기간 종료", "2027-07-10")]
FIRST_HALF = [("날짜 규칙 유형", "선택: 기간 범위"), ("기간 시작", "2026-01-01"), ("기간 종료", "2026-06-30")]
SECOND_HALF = [("날짜 규칙 유형", "선택: 기간 범위"), ("기간 시작", "2026-07-01"), ("기간 종료", "2026-12-31")]


def steps_of(text):
    return cm.parse_steps(text.splitlines())


def overlaps(md):
    """같은 오퍼의 시즌끼리 겹치는 곳(오류 목록)."""
    return cm.find_season_overlaps(steps_of(md))


def needless(md):
    """`이미 값이 있는 날도 덮기` 가 체크로 남은 곳(경고 목록)."""
    return cm.find_needless_overwrite(steps_of(md))


def weekday_season(num, name, card, start, end, days):
    rows = [("날짜 규칙 유형", "선택: 요일 규칙"), ("기간 시작", start),
            ("기간 종료", end), ("적용 요일", f"선택: {days}")]
    return season_step(num, name, card, rows)


class SeasonOverlapTest(unittest.TestCase):
    """같은 오퍼의 시즌끼리 날짜가 하루라도 겹치면 오류다(포함도 겹침)."""

    def wide_and_narrow(self, narrow=INSIDE):
        return HEAD + season_step(4, "Regular", "오퍼A", RANGE) + season_step(5, "Peak", "오퍼A", narrow)

    def test_containment_is_error(self):
        problems = overlaps(self.wide_and_narrow())
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("Peak", problems[0])
        self.assertIn("Regular", problems[0])
        self.assertIn("통째로", problems[0])

    def test_not_overlapping_is_ok(self):
        self.assertEqual(overlaps(self.wide_and_narrow(narrow=OUTSIDE)), [])

    def test_one_day_touch_is_error(self):
        narrow = [("날짜 규칙 유형", "선택: 기간 범위"),
                  ("기간 시작", "2026-12-31"), ("기간 종료", "2027-01-10")]
        problems = overlaps(self.wide_and_narrow(narrow=narrow))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("1일 겹친다", problems[0])

    def test_two_wide_seasons_splitting_the_year_are_ok(self):
        md = HEAD + season_step(4, "앞반기", "오퍼A", FIRST_HALF) \
            + season_step(5, "뒷반기", "오퍼A", SECOND_HALF)
        self.assertEqual(overlaps(md), [])

    def test_each_wide_season_is_compared_separately(self):
        """좁은 시즌이 두 넓은 시즌에 걸치면 둘 다 잡는다."""
        md = HEAD + season_step(4, "앞반기", "오퍼A", FIRST_HALF) \
            + season_step(5, "뒷반기", "오퍼A", SECOND_HALF) \
            + listed_season(6, "Peak", "오퍼A", ["2026-06-30 ~ 2026-07-01"])
        problems = overlaps(md)
        self.assertEqual(len(problems), 2, problems)

    def test_other_offer_is_not_compared(self):
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE) + season_step(5, "Peak", "오퍼B", INSIDE)
        self.assertEqual(overlaps(md), [])

    def test_listed_wide_season_excluding_the_days_is_ok(self):
        wide = [("날짜 규칙 유형", "선택: 비연속 날짜 나열"),
                ("날짜 나열", "2026-01-01 ~ 2026-06-30 / 2026-08-01 ~ 2026-12-31")]
        md = HEAD + season_step(4, "Regular", "오퍼A", wide) + season_step(5, "Peak", "오퍼A", INSIDE)
        self.assertEqual(overlaps(md), [])

    def test_listed_wide_season_containing_the_days_is_error(self):
        wide = [("날짜 규칙 유형", "선택: 비연속 날짜 나열"), ("날짜 나열", "2026-01-01 ~ 2026-12-31")]
        md = HEAD + season_step(4, "Regular", "오퍼A", wide) + season_step(5, "Peak", "오퍼A", INSIDE)
        self.assertEqual(len(overlaps(md)), 1)

    def test_month_list_season_is_compared(self):
        wide = [("날짜 규칙 유형", "선택: 월 목록"), ("기간 시작", "2026-01-01"),
                ("기간 종료", "2026-12-31"), ("적용 월", "선택: 7월, 8월")]
        md = HEAD + season_step(4, "Summer", "오퍼A", wide) + season_step(5, "Peak", "오퍼A", INSIDE)
        problems = overlaps(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("Summer", problems[0])

    def test_month_list_season_outside_the_months_is_ok(self):
        wide = [("날짜 규칙 유형", "선택: 월 목록"), ("기간 시작", "2026-01-01"),
                ("기간 종료", "2026-12-31"), ("적용 월", "선택: 9월, 10월")]
        md = HEAD + season_step(4, "Autumn", "오퍼A", wide) + season_step(5, "Peak", "오퍼A", INSIDE)
        self.assertEqual(overlaps(md), [])

    def test_same_season_name_twice_is_skipped(self):
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE) + season_step(5, "Peak", "오퍼A", OUTSIDE) \
            + season_step(6, "Peak", "오퍼B", INSIDE)
        self.assertEqual(overlaps(md), [])

    def test_unreadable_season_is_skipped(self):
        vague = [("날짜 규칙 유형", "비움")]
        md = HEAD + season_step(4, "모름", "오퍼A", vague) + season_step(5, "Peak", "오퍼A", INSIDE)
        self.assertEqual(overlaps(md), [])

    def test_fenced_date_list_is_read(self):
        md = HEAD + listed_season(4, "Peak", "오퍼A", ["2026-01-01", "2026-04-30 ~ 2026-05-01"])
        step = steps_of(md)[-1]
        self.assertEqual(len(cm.season_dates(step)), 3)


class WeekdaySeasonTest(unittest.TestCase):
    """요일 규칙 시즌은 기간 × 요일로 날짜를 정해 겹침을 본다."""

    def test_complementary_weekday_seasons_do_not_overlap(self):
        md = HEAD + weekday_season(4, "여름 평일", "오퍼A", "2026-06-01", "2026-08-31", "일, 월, 화, 수, 목, 금") \
            + weekday_season(5, "여름 토요일", "오퍼A", "2026-06-01", "2026-08-31", "토")
        self.assertEqual(overlaps(md), [])

    def test_same_weekday_in_the_same_period_is_error(self):
        md = HEAD + weekday_season(4, "여름 주말", "오퍼A", "2026-06-01", "2026-08-31", "토, 일") \
            + weekday_season(5, "여름 토요일", "오퍼A", "2026-06-01", "2026-08-31", "토")
        problems = overlaps(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("통째로", problems[0])

    def test_weekday_season_inside_a_range_season_is_error(self):
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE) \
            + weekday_season(5, "토요일", "오퍼A", "2026-06-01", "2026-08-31", "토")
        self.assertEqual(len(overlaps(md)), 1)

    def test_weekday_dates_are_only_that_weekday(self):
        md = HEAD + weekday_season(4, "토요일", "오퍼A", "2026-06-01", "2026-08-31", "토")
        dates = cm.season_dates(steps_of(md)[-1])
        self.assertEqual(len(dates), 13)
        self.assertTrue(all(d.weekday() == 5 for d in dates))

    def test_compact_weekday_form_is_read(self):
        rows = [("날짜 규칙 유형", "선택: 요일 규칙"),
                ("적용 요일", "선택: 2026-06-01 ~ 2026-08-31 중 토")]
        dates = cm.season_dates(steps_of(HEAD + season_step(4, "토요일", "오퍼A", rows))[-1])
        self.assertEqual(len(dates), 13)
        self.assertTrue(all(d.weekday() == 5 for d in dates))

    def test_weekday_season_without_weekdays_is_skipped(self):
        rows = [("날짜 규칙 유형", "선택: 요일 규칙"), ("기간 시작", "2026-06-01"),
                ("기간 종료", "2026-08-31"), ("적용 요일", "비움")]
        md = HEAD + season_step(4, "요일 미정", "오퍼A", rows) + season_step(5, "Peak", "오퍼A", INSIDE)
        self.assertEqual(overlaps(md), [])


class NeedlessOverwriteTest(unittest.TestCase):
    """시즌이 겹치지 않으므로 `이미 값이 있는 날도 덮기` 체크는 남아 있으면 안 된다(경고)."""

    def test_checked_overwrite_is_warning(self):
        warnings = needless(HEAD + fill_step(4, "Peak", "싱글", overwrite="체크"))
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("덮기가 필요 없다", warnings[0])

    def test_cleared_overwrite_is_ok(self):
        self.assertEqual(needless(HEAD + fill_step(4, "Peak", "싱글")), [])


def offer_step(num, title="오퍼 만들기 (1번째, 2026 시즌 요금)",
               policy="선택: 표준 D-7 무료취소", with_row=True):
    row = f"| 기본 취소 정책 | {policy} |\n" if with_row else ""
    return f"""
## {num}. {title}
탭: `오퍼`
버튼: [오퍼 추가]

| 칸 | 값 |
|---|---|
| 관리용 이름 | 2026 시즌 요금 |
{row}
→ [저장]
"""


def room_step(num, name="Single"):
    return f"""
## {num}. 룸 만들기 (1번째, {name})
탭: `객실`
카드: `객실 (룸 타입)`
버튼: [룸 추가]

| 칸 | 값 |
|---|---|
| 룸 이름 | {name} |
| 룸 설명 | 비움 |

→ [저장]
"""


def room_link_step(num, rooms="Single", display="싱글룸"):
    return f"""
## {num}. 판매 연결 한 번에 만들기 (룸 1개)
탭: `객실`
카드: `판매 연결 (오퍼 × 객실)`
버튼: [객실 추가]

| 칸 | 값 |
|---|---|
| 오퍼 | 선택: 2026 시즌 요금 |
| 룸 카테고리 | 선택: {rooms} |
| 오퍼별 표시명 · {rooms} | {display} |
| 새 룸 카테고리명 (선택) | 비움 |
| 새 룸 오퍼별 표시명 (선택) | 비움 |

→ [추가]
"""


#: 판매 구간 시험의 고정된 "오늘" — 검사하는 날에 흔들리지 않게 값으로 준다.
TODAY = datetime.date(2026, 9, 7)
#: 계약(요금표)이 지난 날부터 유효한 시즌 — 판매 구간 밖이라 만들지 않는다.
PAST = [("날짜 규칙 유형", "선택: 기간 범위"), ("기간 시작", "2026-01-05"), ("기간 종료", "2026-03-31")]


def offer_dates_step(num, stay_start="2026-09-07", book_start="2026-09-07 00:00",
                     book_end="2026-12-31 23:59"):
    return f"""
## {num}. 오퍼 만들기 (1번째, 2026 시즌 요금)
탭: `오퍼`
버튼: [오퍼 추가]

| 칸 | 값 |
|---|---|
| 관리용 이름 | 2026 시즌 요금 |
| 예약 시작 | {book_start} |
| 예약 종료 | {book_end} |
| 투숙 시작 | {stay_start} |
| 투숙 종료 | 2026-12-31 |
| 기본 취소 정책 | 선택: 표준 D-7 무료취소 |

→ [저장]
"""


def sale_days_step(num, start="2026-09-07", end="2026-12-31"):
    return f"""
## {num}. 판매일 열기 (116일)
탭: `판매일`
버튼: [판매일 열기]

| 칸 | 값 |
|---|---|
| 시작일 | {start} |
| 종료일 | {end} |
| 요일 | 비움 |

→ [판매일 열기]
"""


class SaleWindowTest(unittest.TestCase):
    """판매 구간은 지시서를 만드는 날(오늘)부터다 — 계약이 지난 날부터 유효해도 지난 날은 못 판다."""

    def starts(self, md):
        return cm.find_past_sale_starts(steps_of(md), TODAY)

    def blanks(self, md):
        return cm.find_blank_booking_window(steps_of(md))

    def seasons(self, md):
        return cm.find_past_seasons(steps_of(md), TODAY)

    # (a) 시작일이 오늘보다 앞이면 오류
    def test_past_sale_open_start_is_error(self):
        problems = self.starts(HEAD + sale_days_step(4, start="2026-01-05"))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("시작일 2026-01-05", problems[0])
        self.assertIn("오늘(2026-09-07)", problems[0])
        self.assertIn("판매 구간은 오늘부터", problems[0])

    def test_past_offer_stay_start_is_error(self):
        problems = self.starts(HEAD + offer_dates_step(4, stay_start="2026-01-05"))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("투숙 시작 2026-01-05", problems[0])

    def test_today_is_not_past(self):
        md = HEAD + offer_dates_step(4, stay_start="2026-09-07") + sale_days_step(5, start="2026-09-07")
        self.assertEqual(self.starts(md), [])

    def test_future_start_is_ok(self):
        md = HEAD + offer_dates_step(4, stay_start="2026-11-01") + sale_days_step(5, start="2026-11-01")
        self.assertEqual(self.starts(md), [])

    def test_end_date_in_the_past_is_not_checked_here(self):
        """종료일은 계약이 값을 주는 마지막 날이라 이 검사가 보지 않는다(시즌 쪽이 본다)."""
        self.assertEqual(self.starts(HEAD + sale_days_step(4, start="2026-11-01", end="2026-01-31")), [])

    # (b) 예약 창을 비우면 경고
    def test_blank_booking_start_is_warning(self):
        problems = self.blanks(HEAD + offer_dates_step(4, book_start="비움"))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`예약 시작` 가 비었다", problems[0])

    def test_blank_booking_end_is_warning(self):
        problems = self.blanks(HEAD + offer_dates_step(4, book_end="비움"))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`예약 종료` 가 비었다", problems[0])

    def test_both_blank_is_two_warnings(self):
        self.assertEqual(len(self.blanks(HEAD + offer_dates_step(4, book_start="비움", book_end="비움"))), 2)

    def test_filled_booking_window_is_ok(self):
        self.assertEqual(self.blanks(HEAD + offer_dates_step(4)), [])

    def test_missing_row_is_left_to_the_dictionary_check(self):
        self.assertEqual(self.blanks(HEAD + offer_step(4)), [])

    def test_blank_booking_window_is_a_warning_not_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(HEAD + "작성일: 2026-09-07\n" + offer_dates_step(4, book_start="비움"))
            self.assertEqual(cm.main([path]), 0)

    # (c) 판매 구간 밖(과거)에서 끝나는 시즌은 만들지 않는다
    def test_season_ending_in_the_past_is_error(self):
        problems = self.seasons(HEAD + season_step(4, "Low", "오퍼A", PAST))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("시즌 `Low`", problems[0])
        self.assertIn("기간 종료 2026-03-31", problems[0])
        self.assertIn("오늘(2026-09-07)", problems[0])

    def test_season_ending_today_is_ok(self):
        rows = [("날짜 규칙 유형", "선택: 기간 범위"), ("기간 시작", "2026-01-05"), ("기간 종료", "2026-09-07")]
        self.assertEqual(self.seasons(HEAD + season_step(4, "Low", "오퍼A", rows)), [])

    def test_future_season_is_ok(self):
        self.assertEqual(self.seasons(HEAD + season_step(4, "Peak", "오퍼A", OUTSIDE)), [])

    def test_listed_season_wholly_in_the_past_is_error(self):
        md = HEAD + listed_season(4, "Low", "오퍼A", ["2026-01-05 ~ 2026-01-20"])
        self.assertEqual(len(self.seasons(md)), 1)

    def test_unreadable_season_is_skipped(self):
        rows = [("날짜 규칙 유형", "선택: 기간 범위"), ("기간 시작", "비움"), ("기간 종료", "비움")]
        self.assertEqual(self.seasons(HEAD + season_step(4, "Low", "오퍼A", rows)), [])

    # 원고가 지닌 `작성일:` 이 그 원고의 "오늘" 이다
    def test_guide_date_comes_from_the_manual(self):
        lines = ("# 시험 호텔 — 입력 지시서\n\n작성일: 2026-09-07\n\n## 1. 환율 확인\n").splitlines()
        self.assertEqual(cm.guide_date(lines), TODAY)

    def test_guide_date_falls_back_to_the_check_day(self):
        other = datetime.date(2027, 1, 1)
        self.assertEqual(cm.guide_date(HEAD.splitlines(), today=other), other)

    def test_a_date_inside_a_step_is_not_the_guide_date(self):
        md = "# 시험 호텔\n\n## 1. 환율 확인\n작성일: 2026-01-05\n"
        self.assertEqual(cm.guide_date(md.splitlines(), today=TODAY), TODAY)

    def test_check_reads_the_guide_date_and_fails_on_a_past_start(self):
        md = "# 시험 호텔 — 입력 지시서\n\n작성일: 2026-09-07\n" + HEAD.split("\n", 1)[1] \
            + offer_dates_step(4, stay_start="2026-01-05")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            r = cm.check(path)
            self.assertEqual(r["guide_date"], TODAY)
            self.assertEqual(len(r["past_sale_starts"]), 1, r["past_sale_starts"])
            self.assertEqual(cm.main([path]), 1)

    def test_past_season_fails_the_run(self):
        md = "# 시험 호텔 — 입력 지시서\n\n작성일: 2026-09-07\n" + HEAD.split("\n", 1)[1] \
            + season_step(4, "Low", "오퍼A", PAST)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            r = cm.check(path)
            self.assertEqual(len(r["past_seasons"]), 1, r["past_seasons"])
            self.assertEqual(cm.main([path]), 1)

    def test_the_example_manual_carries_a_guide_date_and_opens_no_past_day(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        day = cm.guide_date(lines)
        self.assertEqual(day, TODAY)
        steps = cm.parse_steps(lines)
        self.assertEqual(cm.find_past_sale_starts(steps, day), [])
        self.assertEqual(cm.find_past_seasons(steps, day), [])
        self.assertEqual(cm.find_blank_booking_window(steps), [])


class CancelPolicyTest(unittest.TestCase):
    """오퍼마다 `기본 취소 정책` 이 있어야 한다 — `지정 안 함`·빈 값은 배너에 🟡 를 남긴다."""

    def problems(self, md):
        return cm.find_missing_cancel_policy(steps_of(md))

    def test_named_policy_is_ok(self):
        self.assertEqual(self.problems(HEAD + offer_step(4)), [])

    def test_unset_policy_is_error(self):
        problems = self.problems(HEAD + offer_step(4, policy="선택: 지정 안 함"))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("기본 취소 정책", problems[0])

    def test_blank_policy_is_error(self):
        self.assertEqual(len(self.problems(HEAD + offer_step(4, policy="비움"))), 1)

    def test_missing_row_is_error(self):
        problems = self.problems(HEAD + offer_step(4, with_row=False))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("줄이 없다", problems[0])

    def test_offer_create_step_is_checked_too(self):
        md = HEAD + offer_step(4, title="오퍼 만들기 (2개, 조식 포함)", policy="선택: 지정 안 함")
        self.assertEqual(len(self.problems(md)), 1)

    def test_other_steps_are_not_checked(self):
        md = HEAD + offer_step(4, title="시즌 만들기 (1번째, Regular)", with_row=False)
        self.assertEqual(self.problems(md), [])

    def test_legacy_edit_step_is_not_checked_here(self):
        """`오퍼 고치기` 는 이 검사가 아니라 전용 규칙이 잡는다 — 사유가 둘로 갈리지 않게."""
        md = HEAD + offer_step(4, title="오퍼 고치기 (1개)", with_row=False)
        self.assertEqual(self.problems(md), [])


class LegacyOfferEditTest(unittest.TestCase):
    """호텔이 빈 상태로 만들어지므로 `오퍼 고치기` 단계는 성립하지 않는다."""

    def test_legacy_title_is_error(self):
        problems = cm.find_legacy_offer_edit_steps(steps_of(HEAD + offer_step(4, title="오퍼 고치기 (1개)")))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("오퍼 고치기", problems[0])

    def test_create_title_is_ok(self):
        self.assertEqual(cm.find_legacy_offer_edit_steps(steps_of(HEAD + offer_step(4))), [])


class OfferBeforeRoomsTest(unittest.TestCase):
    """오퍼가 없으면 객실 추가가 막힌다 — `룸 만들기`·`판매 연결` 은 첫 오퍼 뒤에 온다."""

    def problems(self, md):
        return cm.find_rooms_before_offer(steps_of(md))

    def test_offer_first_is_ok(self):
        md = HEAD + offer_step(4) + room_step(5) + room_link_step(6)
        self.assertEqual(self.problems(md), [])

    def test_room_before_offer_is_error(self):
        md = HEAD + room_step(4) + offer_step(5)
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("오퍼가 없으면 객실 추가가 막힌다", problems[0])

    def test_room_link_before_offer_is_error(self):
        md = HEAD + room_link_step(4) + offer_step(5)
        self.assertEqual(len(self.problems(md)), 1)

    def test_rooms_without_any_offer_step_are_errors(self):
        md = HEAD + room_step(4) + room_link_step(5)
        self.assertEqual(len(self.problems(md)), 2)


SKIP_STEP = """
## 4. 경고 넘어가기 (시즌 포함)
화면: 편집 화면 맨 위 검증 배너
버튼: `채우면 좋음` 을 펼친 뒤 그 줄의 [이건 넘어가기]

| 칸 | 값 |
|---|---|
| 사유 | 계약이 원래 포함 관계 |

→ [넘어가기]
"""

SELL_STEP = """
## 4. 판매 시작
화면: 편집 화면 맨 위 검증 배너

→ [판매 시작]
"""


class SkipWarningTest(unittest.TestCase):
    """`경고 넘어가기` 단계는 더 이상 쓰지 않는다."""

    def test_skip_step_is_error(self):
        problems = cm.find_skip_warning_steps(steps_of(HEAD + SKIP_STEP))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("경고 넘어가기", problems[0])

    def test_sell_step_is_ok(self):
        self.assertEqual(cm.find_skip_warning_steps(steps_of(HEAD + SELL_STEP)), [])


CAMPAIGN_STEP = """
## 4. 캠페인 만들기 (1개, RETREAT PACKAGE)
화면: Stay 호텔 목록 화면 위 [캠페인]
버튼: [캠페인 만들기]

| 칸 | 값 |
|---|---|
| 캠페인 코드 | RETREAT-26 |
| 고객 노출명 | RETREAT PACKAGE |

→ [추가]
"""


def offer_with_campaign(num, value):
    return f"""
## {num}. 오퍼 만들기 (1번째, 2026 시즌 요금)
탭: `오퍼`
버튼: [오퍼 추가]

| 칸 | 값 |
|---|---|
| 관리용 이름 | 2026 시즌 요금 |
| 캠페인 | {value} |
| 기본 취소 정책 | 선택: 표준 D-7 무료취소 |

→ [저장]
"""


class CampaignTest(unittest.TestCase):
    """캠페인은 2026-09-04 화면에서 없어졌다 — 단계도, 어느 표의 `캠페인` 줄도 두지 않는다."""

    def problems(self, md):
        return cm.find_campaign_uses(steps_of(md))

    def test_campaign_step_is_error(self):
        problems = self.problems(HEAD + CAMPAIGN_STEP)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("캠페인 단계는 만들지 않는다(오퍼 이미지로 대신)", problems[0])

    def test_offer_with_campaign_name_is_error(self):
        problems = self.problems(HEAD + offer_with_campaign(4, "선택: RETREAT PACKAGE"))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`캠페인` 칸은 화면에서 없어졌다 — 줄을 뺀다", problems[0])

    def test_offer_with_none_is_error(self):
        """종전에는 `— 없음 —` 이 정답이었다 — 이제는 칸 자체가 없다."""
        problems = self.problems(HEAD + offer_with_campaign(4, "선택: — 없음 —"))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`캠페인` 칸은 화면에서 없어졌다 — 줄을 뺀다", problems[0])

    def test_campaign_row_outside_offer_is_error(self):
        """오퍼 단계가 아니어도 마찬가지다 — 화면 어디에도 그 칸이 없다."""
        step = offer_with_campaign(4, "선택: — 없음 —").replace(
            "## 4. 오퍼 만들기 (1번째, 2026 시즌 요금)", "## 4. 프로모션 만들기 (1번째)"
        )
        problems = self.problems(HEAD + step)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])

    def test_offer_without_campaign_row_is_ok(self):
        self.assertEqual(self.problems(HEAD + offer_step(4)), [])


ADDON_A = """
## 4. 부가옵션 만들기 (1개, 조식)
탭: `부가옵션`
버튼: [부가옵션 추가]

| 칸 | 값 |
|---|---|
| 오퍼 | 선택: 오퍼A |
| 이름 | 조식 |

→ [추가]
"""

ADDON_B = """
## 5. 부가옵션 만들기 (2개, 조식)
탭: `부가옵션`
버튼: [부가옵션 추가]

| 칸 | 값 |
|---|---|
| 오퍼 | 선택: 오퍼B |
| 이름 | 조식 |

→ [추가]
"""


def addon_price(num, card):
    return f"""
## {num}. 부가옵션 가격 넣기 ({num}개, 조식)
탭: `부가옵션`
카드: {card}
버튼: [가격 추가]

| 칸 | 값 |
|---|---|
| 이름 | 1인 · 1박 |
| 판매가(공급 통화) | 3000 |

→ [추가]
"""


class AddonCardTest(unittest.TestCase):
    """같은 이름의 부가옵션이 오퍼 여럿에 있으면 카드 줄이 오퍼를 한정해야 한다."""

    def test_plain_card_with_two_offers_is_error(self):
        md = HEAD + ADDON_A + ADDON_B + addon_price(6, "`조식`")
        problems = cm.find_addon_card_gaps(steps_of(md))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("오퍼 칸이", problems[0])

    def test_offer_qualified_card_is_ok(self):
        md = HEAD + ADDON_A + ADDON_B + addon_price(6, "`조식` — 오퍼 칸이 `오퍼A` 인 카드")
        self.assertEqual(cm.find_addon_card_gaps(steps_of(md)), [])

    def test_single_offer_plain_card_is_ok(self):
        md = HEAD + ADDON_A + addon_price(5, "`조식`")
        self.assertEqual(cm.find_addon_card_gaps(steps_of(md)), [])


class PromotionCardTest(unittest.TestCase):
    """프로모션 카드 `전 오퍼 공통` 은 실재한다(오퍼 없는 공통 프로모션) — 오류가 아니다."""

    def make(self, card):
        return HEAD + f"""
## 4. 프로모션 만들기 (1번째, 얼리버드)
탭: `프로모션`
카드: `{card}`
버튼: [프로모션 추가]

| 칸 | 값 |
|---|---|
| 프로모션명 | 얼리버드 |

→ [추가]
"""

    def test_common_card_is_ok(self):
        self.assertEqual(cm.find_promo_common_cards(steps_of(self.make("전 오퍼 공통"))), [])

    def test_offer_card_is_ok(self):
        self.assertEqual(cm.find_promo_common_cards(steps_of(self.make("오퍼A"))), [])


def cancel_policy_step(num, save="추가", title=None):
    head = title or f"취소정책 만들기 (1개, 표준 D-7 무료취소)"
    return f"""
## {num}. {head}
탭: `취소정책`
버튼: [정책 만들기]

| 칸 | 값 |
|---|---|
| 정책명 | 표준 D-7 무료취소 |
| 환불 가능 | 체크 |

→ [{save}]
"""


class CancelPolicyCreateButtonTest(unittest.TestCase):
    """`취소정책 만들기` 단계는 `→ [추가]` 로 끝난다 — [저장] 은 이미 있는 정책을 고칠 때다."""

    def test_save_button_is_error(self):
        problems = cm.find_cancel_policy_save_gaps(steps_of(HEAD + cancel_policy_step(4, save="저장")))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`→ [추가]`", problems[0])
        self.assertIn("4단계", problems[0])

    def test_add_button_is_ok(self):
        self.assertEqual(cm.find_cancel_policy_save_gaps(steps_of(HEAD + cancel_policy_step(4))), [])

    def test_policy_edit_step_is_not_checked(self):
        md = HEAD + cancel_policy_step(4, save="저장", title="취소정책 고치기 (1개, 표준 D-7 무료취소)")
        self.assertEqual(cm.find_cancel_policy_save_gaps(steps_of(md)), [])

    def test_the_example_manual_uses_the_add_button(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            steps = cm.parse_steps(handle.read().splitlines())
        self.assertEqual(cm.find_cancel_policy_save_gaps(steps), [])
        made = [s for s in steps if s["title"].startswith("취소정책 만들기")]
        self.assertEqual([s["saves"][-1] for s in made], ["추가"])


class SeasonSaveButtonTest(unittest.TestCase):
    """`시즌 만들기` 단계는 `→ [추가]` 로 끝난다."""

    def test_save_button_is_error(self):
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE, save="저장")
        problems = cm.find_season_save_gaps(steps_of(md))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("추가", problems[0])

    def test_add_button_is_ok(self):
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE, save="추가")
        self.assertEqual(cm.find_season_save_gaps(steps_of(md)), [])

    def test_season_edit_step_is_not_checked(self):
        md = HEAD + """
## 4. 시즌 고치기 (1번째, Regular)
탭: `시즌`
카드: `오퍼A`
버튼: `Regular` 행의 [편집]

| 칸 | 값 |
|---|---|
| 우선순위 | 10 |

→ [저장]
"""
        self.assertEqual(cm.find_season_save_gaps(steps_of(md)), [])


def hotel_step(num, currency):
    row = f"| 공급 통화 | 선택: {currency} |\n" if currency else ""
    return f"""
## {num}. 호텔 만들기
화면: 왼쪽 메뉴 `자유여행` → `상품관리` → 목록 위 [호텔 만들기]

| 칸 | 값 |
|---|---|
| 호텔명 | 시험 호텔 |
{row}
→ [호텔 만들기]
"""


class SupplyCurrencyTest(unittest.TestCase):
    """`호텔 만들기` 의 공급 통화가 USD 가 아니면 경고(막지는 않는다)."""

    def currency_of(self, md):
        return cm.supply_currency(steps_of(md))

    def test_usd_is_read(self):
        self.assertEqual(self.currency_of(HEAD + hotel_step(4, "USD")), "USD")

    def test_other_currency_is_read(self):
        self.assertEqual(self.currency_of(HEAD + hotel_step(4, "VND")), "VND")

    def test_missing_field_is_none(self):
        self.assertIsNone(self.currency_of(HEAD + hotel_step(4, None)))

    def test_missing_step_is_none(self):
        self.assertIsNone(self.currency_of(HEAD))

    def test_non_usd_is_a_warning_not_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(HEAD + hotel_step(4, "VND"))
            r = cm.check(path)
            self.assertEqual(r["currency"], "VND")
            self.assertEqual(cm.main([path]), 0)  # 경고라 통과한다

    def test_usd_manual_has_no_currency_warning(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(HEAD + hotel_step(4, "USD"))
            self.assertEqual(cm.check(path)["currency"], "USD")


class ParseTest(unittest.TestCase):
    def test_step_subject_takes_the_name_after_the_comma(self):
        self.assertEqual(cm.step_subject("시즌 만들기 (1번째, Regular)"), "Regular")
        self.assertEqual(cm.step_subject("시즌 만들기 (2번째, Peak (여름))"), "Peak (여름)")
        self.assertIsNone(cm.step_subject("판매 시작"))

    def test_card_name_reads_the_backticked_name(self):
        steps = steps_of(HEAD + fill_step(4, "Regular", "싱글"))
        self.assertEqual(cm.card_name(steps[-1]), "Regular")


class EndToEndTest(unittest.TestCase):
    """check() 가 새 검사 결과를 결과 dict 에 담고, main() 이 그것으로 실패를 낸다."""

    def run_on(self, md):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            return cm.check(path), cm.main([path])

    def test_bad_manual_fails(self):
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE, save="저장") \
            + season_step(5, "Peak", "오퍼A", INSIDE, save="저장") \
            + fill_step(6, "Regular", "싱글") + fill_step(7, "Peak", "싱글")
        r, code = self.run_on(md)
        self.assertEqual(code, 1)
        self.assertEqual(len(r["season_saves"]), 2)
        self.assertEqual(len(r["season_overlaps"]), 1)

    def test_good_manual_passes(self):
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE) + season_step(5, "Peak", "오퍼A", OUTSIDE) \
            + fill_step(6, "Regular", "싱글") + fill_step(7, "Peak", "싱글") + offer_step(8)
        r, code = self.run_on(md)
        self.assertEqual(code, 0, r)
        self.assertEqual(
            r["season_overlaps"] + r["needless_overwrite"] + r["cancel_policy_gaps"]
            + r["skip_warning_steps"] + r["season_saves"], []
        )

    def test_offer_without_cancel_policy_fails(self):
        md = HEAD + offer_step(4, policy="선택: 지정 안 함")
        r, code = self.run_on(md)
        self.assertEqual(code, 1)
        self.assertEqual(len(r["cancel_policy_gaps"]), 1)

    def test_cancel_policy_step_with_save_button_fails(self):
        r, code = self.run_on(HEAD + cancel_policy_step(4, save="저장"))
        self.assertEqual(code, 1)
        self.assertEqual(len(r["cancel_policy_saves"]), 1)

    def test_cancel_policy_step_with_add_button_passes(self):
        r, code = self.run_on(HEAD + cancel_policy_step(4) + offer_step(5))
        self.assertEqual(code, 0, r)
        self.assertEqual(r["cancel_policy_saves"], [])

    def test_off_value_on_a_multi_check_field_fails(self):
        """이 검사는 사전이 있어야 돈다 — main() 은 사전을 스스로 찾아 실패를 낸다."""
        md = HEAD + rows_step(4, [("요금제(선택)", "해제")])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            r = cm.check(path, dictionary_path=DICTIONARY)
            self.assertEqual(cm.main([path]), 1)
        self.assertEqual(len(r["check_value_classes"]), 1)

    def test_broken_repeat_row_label_fails(self):
        r, code = self.run_on(HEAD + rows_step(4, [("구간 1 ・ 수수료 값", "0")]))
        self.assertEqual(code, 1)
        self.assertEqual(len(r["repeat_row_formats"]), 1)

    def test_skip_warning_step_fails(self):
        r, code = self.run_on(HEAD + SKIP_STEP)
        self.assertEqual(code, 1)
        self.assertEqual(len(r["skip_warning_steps"]), 1)

    def test_legacy_offer_edit_step_fails(self):
        r, code = self.run_on(HEAD + offer_step(4, title="오퍼 고치기 (1개)"))
        self.assertEqual(code, 1)
        self.assertEqual(len(r["legacy_offer_steps"]), 1)

    def test_room_before_offer_fails(self):
        r, code = self.run_on(HEAD + room_step(4) + offer_step(5))
        self.assertEqual(code, 1)
        self.assertEqual(len(r["rooms_before_offer"]), 1)

    def test_offer_then_rooms_passes(self):
        md = HEAD + offer_step(4) + room_step(5) + room_link_step(6)
        r, code = self.run_on(md)
        self.assertEqual(code, 0, r)
        self.assertEqual(r["rooms_before_offer"] + r["legacy_offer_steps"], [])

    def test_campaign_step_fails(self):
        r, code = self.run_on(HEAD + CAMPAIGN_STEP)
        self.assertEqual(code, 1)
        self.assertEqual(len(r["campaign_uses"]), 1)

    def test_offer_with_campaign_fails(self):
        r, code = self.run_on(HEAD + offer_with_campaign(4, "선택: RETREAT PACKAGE"))
        self.assertEqual(code, 1)
        self.assertEqual(len(r["campaign_uses"]), 1)

    def test_example_manual_is_all_ok(self):
        """정답지 예시는 새 검사까지 통과해야 한다(사진 폴더는 저장소에 없어 뺀다)."""
        r = cm.check(EXAMPLE, share_name="우에노_토우가네야", dictionary_path=DICTIONARY)
        self.assertEqual(r["season_overlaps"], [])
        self.assertEqual(r["needless_overwrite"], [])
        self.assertEqual(r["cancel_policy_gaps"], [])
        self.assertEqual(r["skip_warning_steps"], [])
        self.assertEqual(r["legacy_offer_steps"], [])
        self.assertEqual(r["rooms_before_offer"], [])
        self.assertEqual(r["campaign_uses"], [])
        self.assertEqual(r["addon_card_gaps"], [])
        self.assertEqual(r["promo_common"], [])
        self.assertEqual(r["season_saves"], [])
        self.assertEqual(r["forbidden"], {})
        self.assertEqual(r["unknown_fields"], [])
        self.assertEqual(r["bad_folder"], [])
        self.assertTrue(r["seq_ok"])
        self.assertEqual(r["steps"], r["saves"])
        self.assertEqual(cm.main([EXAMPLE, "--share-name", "우에노_토우가네야"]), 0)

    def test_example_manual_share_name_comes_from_the_path(self):
        """예시 원고는 `<이름>/_원고/manual.md` 자리라 `--share-name` 없이도 `폴더:` 줄까지 본다."""
        self.assertEqual(cm.derive_share_name(EXAMPLE), "우에노_토우가네야")
        self.assertEqual(cm.main([EXAMPLE]), 0)


class TestShareNameFromPath(unittest.TestCase):
    """원고가 `<이름>/_원고/manual.md` 자리면 공유 폴더명을 경로에서 알아낸다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.share = os.path.join(self.tmp.name, "시험호텔")
        self.draft = os.path.join(self.share, "_원고")
        os.makedirs(self.draft)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, folder, text):
        path = os.path.join(folder, "manual.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_derive_from_draft_folder(self):
        self.assertEqual(cm.derive_share_name(os.path.join(self.draft, "manual.md")), "시험호텔")

    def test_no_derive_from_the_old_flat_place(self):
        self.assertIsNone(cm.derive_share_name(os.path.join(self.share, "manual.md")))

    def test_derived_name_catches_a_wrong_folder_line(self):
        """`폴더:` 줄이 공유 폴더명과 어긋나면 `--share-name` 없이도 걸린다."""
        md = self.write(self.draft, HEAD + room_photo_step(4, "사진 추가").replace(
            "시험호텔/사진", "다른이름/사진"))
        self.assertEqual(cm.main([md, "--dictionary", DICTIONARY]), 1)
        good = self.write(self.draft, HEAD + room_photo_step(4, "사진 추가"))
        self.assertEqual(cm.main([good, "--dictionary", DICTIONARY]), 0)

    def test_old_flat_place_still_skips_the_folder_check(self):
        """옛 자리(`<이름>/manual.md`)면 예전처럼 건너뛴다 — `--share-name` 을 주면 그대로 본다."""
        md = self.write(self.share, HEAD + room_photo_step(4, "사진 추가").replace(
            "시험호텔/사진", "다른이름/사진"))
        self.assertEqual(cm.main([md, "--dictionary", DICTIONARY]), 0)
        self.assertEqual(cm.main([md, "--dictionary", DICTIONARY, "--share-name", "시험호텔"]), 1)


if __name__ == "__main__":
    unittest.main()


def age_band_step(num, name="초등학생", code="CHILD", card="`2026 시즌 요금`"):
    return f"""
## {num}. 연령 구간 만들기 (1번째, {name})
탭: `오퍼`
카드: {card}
버튼: [연령 구간 추가]

| 칸 | 값 |
|---|---|
| 밴드 코드 | {code} |
| 노출명 | {name} |
| 최소 연령 | 6 |
| 최대 연령 | 11.99 |
| 방 인원수에 포함 | 체크 |
| 요금 기준 유형 | 선택: 성인 요금의 % |
| 요금 기준 값 | 50 |
| 상세(자유텍스트) | 비움 |

→ [추가]
"""


def age_band_range_step(num, name, code, low, high, card="`2026 시즌 요금`"):
    return f"""
## {num}. 연령 구간 만들기 ({num}번째, {name})
탭: `오퍼`
카드: {card}
버튼: [연령 구간 추가]

| 칸 | 값 |
|---|---|
| 밴드 코드 | {code} |
| 노출명 | {name} |
| 최소 연령 | {low} |
| 최대 연령 | {high} |
| 요금 기준 유형 | 선택: 무료 |

→ [추가]
"""


class AgeBandOverlapTest(unittest.TestCase):
    """같은 오퍼의 연령 구간은 양끝 포함으로 한 살도 겹칠 수 없다."""

    def problems(self, md):
        return cm.find_age_band_overlaps(steps_of(md))

    def test_adjacent_bands_are_ok(self):
        md = (HEAD + offer_step(4)
              + age_band_range_step(5, "유아", "INFANT", "0", "5.99")
              + age_band_range_step(6, "초등학생", "CHILD", "6", "11.99"))
        self.assertEqual(self.problems(md), [])

    def test_both_starting_at_zero_is_an_error(self):
        """계약서 문구를 그대로 옮기면 나오는 실수 — 둘 다 0 부터."""
        md = (HEAD + offer_step(4)
              + age_band_range_step(5, "유아", "INFANT", "0", "5.99")
              + age_band_range_step(6, "초등학생", "CHILD", "0", "11.99"))
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("6단계", problems[0])
        self.assertIn("겹친다", problems[0])

    def test_touching_boundary_is_an_error(self):
        """`0~6` 과 `6~11.99` 는 만 6세에서 겹친다."""
        md = (HEAD + offer_step(4)
              + age_band_range_step(5, "유아", "INFANT", "0", "6")
              + age_band_range_step(6, "초등학생", "CHILD", "6", "11.99"))
        self.assertEqual(len(self.problems(md)), 1)

    def test_different_offers_do_not_collide(self):
        """구간은 오퍼에 매달린다 — 다른 카드면 같은 범위여도 괜찮다."""
        md = (HEAD + offer_step(4)
              + age_band_range_step(5, "유아", "INFANT", "0", "5.99")
              + age_band_range_step(6, "유아", "INFANT", "0", "5.99", card="`2027 시즌 요금`"))
        self.assertEqual(self.problems(md), [])

    def test_the_example_manual_has_no_overlap(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(self.problems(handle.read()), [])


def charge_with_age_rate(num, band="초등학생"):
    return f"""
## {num}. 부과금 추가 (1개, 갈라 디너)
탭: `부과금`
카드: `2026 시즌 요금`
버튼: [부과금 추가]

| 칸 | 값 |
|---|---|
| 종류 | 선택: 기타 |
| 이름 | 갈라 디너 |
| 부과 방식 | 선택: 정액 |
| 부과 단위 | 선택: 인당 |
| 정액 금액 (USD) | 선택: 지정 (0 포함) |
| 정액 금액 (USD) 값 | 40.00 |
| 부과 유형 | 선택: 의무 — 고객 선택 없이 자동으로 붙습니다 |
| 연령별 단가 · {band} | 20.00 |

→ [추가]
"""


class AgeBandOrderTest(unittest.TestCase):
    """연령 구간은 오퍼 뒤·부과금 앞이다 — 화면이 그 순서로만 칸을 보여 준다."""

    def problems(self, md):
        return cm.find_age_band_order(steps_of(md))

    def test_band_before_offer_is_error(self):
        md = HEAD + age_band_step(4) + offer_step(5)
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`오퍼 만들기` 보다 앞이다", problems[0])

    def test_band_without_any_offer_step_is_error(self):
        problems = self.problems(HEAD + age_band_step(4))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`오퍼 만들기` 보다 앞이다", problems[0])

    def test_band_after_offer_is_ok(self):
        self.assertEqual(self.problems(HEAD + offer_step(4) + age_band_step(5)), [])

    def test_age_rate_without_band_step_is_error(self):
        md = HEAD + offer_step(4) + charge_with_age_rate(5)
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`연령 구간 만들기` 단계가 없다", problems[0])

    def test_age_rate_before_band_step_is_error(self):
        md = HEAD + offer_step(4) + charge_with_age_rate(5) + age_band_step(6)
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`연령 구간 만들기` 단계보다 앞이다", problems[0])

    def test_age_rate_after_band_step_is_ok(self):
        md = HEAD + offer_step(4) + age_band_step(5) + charge_with_age_rate(6)
        self.assertEqual(self.problems(md), [])

    def test_manual_without_age_bands_is_ok(self):
        self.assertEqual(self.problems(HEAD + offer_step(4) + room_step(5)), [])


def catalog_step(num, title, save, with_apply_now=True):
    row = "| 지금 모든 객실에 배포 | 체크 |\n" if with_apply_now else ""
    return f"""
## {num}. {title}
탭: `요금제`
카드: `요금제 정본`
버튼: [정본 만들기]

| 칸 | 값 |
|---|---|
| 요금제명 | 룸온리 |
| 새 객실에 자동 배포 | 체크 |
{row}
→ [{save}]
"""


def room_photo_step(num, save, title="룸 사진 올리기 (1번째, Single)"):
    return f"""
## {num}. {title}
탭: `객실`
카드: `객실 (룸 타입)`
버튼: `Single` 행의 [편집]
폴더: 시험호텔/사진

파일 선택 → 아래 파일
- room_single_01.jpg

→ [{save}]
"""


def photo_count_step(num, title, files, save="저장", as_field=False):
    if as_field:
        body = "\n".join(f"| 오퍼 이미지 | 파일: {f} |" for f in files)
        body = f"| 칸 | 값 |\n|---|---|\n{body}"
    else:
        body = "파일 선택 → 아래 파일\n" + "\n".join(f"- {f}" for f in files)
    return f"""
## {num}. {title}
탭: `기본정보`
버튼: [이미지 직접등록]
폴더: 시험호텔/사진

{body}

→ [{save}]
"""


class PhotoCountTest(unittest.TestCase):
    """사진 단계 제목의 `(N장)` 과 파일 줄 수가 같아야 한다."""

    def problems(self, md):
        return cm.find_photo_count_gaps(steps_of(md))

    def test_title_promises_more_than_listed(self):
        md = HEAD + photo_count_step(
            4, "상품상세 이미지 올리기 (7장)",
            ["hotel_02.jpg", "hotel_03.jpg", "hotel_04.jpg",
             "hotel_05.jpg", "hotel_06.jpg", "hotel_07.jpg"],
        )
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertEqual(problems[0], "4단계: 제목은 7장인데 파일 줄은 6개다")

    def test_title_promises_fewer_than_listed(self):
        md = HEAD + photo_count_step(
            4, "상품상세 이미지 올리기 (2장)",
            ["hotel_02.jpg", "hotel_03.jpg", "hotel_04.jpg"],
        )
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertEqual(problems[0], "4단계: 제목은 2장인데 파일 줄은 3개다")

    def test_matching_count_is_ok(self):
        md = HEAD + photo_count_step(4, "대표이미지 올리기 (1장)", ["hotel_01.jpg"])
        self.assertEqual(self.problems(md), [])

    def test_source_urls_do_not_break_the_count(self):
        md = HEAD + f"""
## 4. 상품상세 이미지 올리기 (2장)
탭: `기본정보`
폴더: 시험호텔/사진

파일 선택 → 아래 파일
- hotel_02.jpg — 출처: https://example.com/a.jpg
- hotel_03.jpg

→ [저장]
"""
        self.assertEqual(self.problems(md), [])

    def test_file_rows_in_a_table_are_counted(self):
        """`| 오퍼 이미지 | 파일: offer_hero.jpg |` 도 파일 줄이다."""
        md = HEAD + photo_count_step(4, "오퍼 이미지 올리기 (2장)", ["offer_hero.jpg"], as_field=True)
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertEqual(problems[0], "4단계: 제목은 2장인데 파일 줄은 1개다")

    def test_step_without_a_count_is_not_checked(self):
        """룸 사진 단계는 제목에 장수를 약속하지 않는다."""
        md = HEAD + photo_count_step(
            4, "룸 사진 올리기 (1번째, Single)", ["room_single_01.jpg"], save="사진 추가"
        )
        self.assertEqual(self.problems(md), [])

    def test_non_photo_step_is_not_checked(self):
        md = HEAD + photo_count_step(4, "시즌 가격 채우기 (1회차, Regular × Single)", [])
        self.assertEqual(self.problems(md), [])

    def test_the_example_manual_counts_match(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(self.problems(handle.read()), [])


class RoomPhotoSaveTest(unittest.TestCase):
    """룸 사진 카드에는 저장 버튼이 없다 — 파일을 고르면 바로 올라간다."""

    def problems(self, md):
        return cm.find_room_photo_saves(steps_of(md))

    def test_save_button_is_error(self):
        problems = self.problems(HEAD + room_photo_step(4, "저장"))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("사진 추가", problems[0])

    def test_photo_add_button_is_ok(self):
        self.assertEqual(self.problems(HEAD + room_photo_step(4, "사진 추가")), [])

    def test_hotel_image_step_is_not_checked(self):
        """대표이미지·상품상세 이미지는 기본정보 탭이라 [저장] 이 맞다."""
        md = HEAD + room_photo_step(4, "저장", title="대표이미지 올리기 (1장)")
        self.assertEqual(self.problems(md), [])

    def test_the_example_manual_uses_photo_add(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(self.problems(handle.read()), [])


class CreateOnlyFieldTest(unittest.TestCase):
    """`지금 모든 객실에 배포` 는 [정본 만들기] 드로어에만 있는 칸이다."""

    def problems(self, md):
        return cm.find_create_only_fields(steps_of(md))

    def test_edit_step_with_apply_now_is_error(self):
        """제목이 `요금제 고치기` 면 사람 말 그대로 돌려준다(팀 합의 문구)."""
        md = HEAD + catalog_step(4, "요금제 고치기 (1개)", "저장")
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertEqual(
            problems[0],
            "4단계: `지금 모든 객실에 배포` 는 새로 만들 때만 있는 칸이다 — 고치기 표에서 뺀다",
        )

    def test_edit_step_is_caught_even_when_the_save_button_is_wrong(self):
        """고치기 단계면 마지막 버튼이 [만들기] 로 잘못 적혀 있어도 잡는다."""
        md = HEAD + catalog_step(4, "요금제 고치기 (1개)", "만들기")
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("새로 만들 때만 있는 칸이다", problems[0])

    def test_non_edit_step_with_wrong_save_button_falls_back_to_the_button_message(self):
        md = HEAD + catalog_step(4, "요금제 정본 손보기 (1개)", "저장")
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("[만들기] 로 끝나는 만들기 드로어에만 있다", problems[0])

    def test_create_step_with_apply_now_is_ok(self):
        md = HEAD + catalog_step(4, "요금제 정본 만들기 (1개)", "만들기")
        self.assertEqual(self.problems(md), [])

    def test_edit_step_without_apply_now_is_ok(self):
        md = HEAD + catalog_step(4, "요금제 고치기 (1개)", "저장", with_apply_now=False)
        self.assertEqual(self.problems(md), [])

    def test_the_example_manual_has_no_create_only_field(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(self.problems(handle.read()), [])


class AgeBandDictionaryTest(unittest.TestCase):
    """연령 구간 칸과 `연령별 단가 · <노출명>` 이 화면 사전 대조를 통과해야 한다."""

    def setUp(self):
        self.labels = cm.load_dictionary(DICTIONARY)

    def test_age_band_fields_are_in_the_dictionary(self):
        for label in ("밴드 코드", "노출명", "최소 연령", "최대 연령",
                      "방 인원수에 포함", "요금 기준 유형", "요금 기준 값",
                      "참조 밴드 코드", "상세(자유텍스트)"):
            self.assertIn(label, self.labels, label)

    def test_age_rate_row_matches_by_prefix(self):
        self.assertNotIn("연령별 단가 · 초등학생", self.labels)
        self.assertEqual(cm.strip_row_suffix("연령별 단가 · 초등학생"), "연령별 단가")
        self.assertIn(cm.norm_field("연령별 단가 · 〈연령 구간 노출명〉"), self.labels)

    def test_room_link_edit_has_no_offer_field(self):
        """편집 드로어에는 오퍼 칸이 없다 — 사전도 그렇게 적혀 있어야 한다."""
        import json
        with open(DICTIONARY, encoding="utf-8") as handle:
            data = json.load(handle)
        screen = next(s for s in data["screens"] if s["id"] == "room-link-edit")
        labels = [f["label"] for b in screen["blocks"] for f in b["fields"]]
        self.assertNotIn("오퍼", labels)

    def test_apply_now_is_marked_create_only(self):
        """사전이 그 칸을 만들기 전용으로 적어 두어야 검사기 규칙과 어긋나지 않는다."""
        import json
        with open(DICTIONARY, encoding="utf-8") as handle:
            data = json.load(handle)
        screen = next(s for s in data["screens"] if s["id"] == "rate-plan-catalog")
        field = next(f for b in screen["blocks"] for f in b["fields"]
                     if f["label"] == "지금 모든 객실에 배포")
        self.assertIn("정본 만들기", field["visible_when"])
        self.assertIn("편집", field["visible_when"])

    def test_hotel_profile_puts_star_grade_after_the_years(self):
        """화면은 `연식`(개장·리노베이션) 줄 다음에 성급을 세운다."""
        import json
        with open(DICTIONARY, encoding="utf-8") as handle:
            data = json.load(handle)
        screen = next(s for s in data["screens"] if s["id"] == "hotel-profile")
        labels = [f["label"] for b in screen["blocks"] for f in b["fields"]]
        self.assertEqual(labels[:6], ["호텔 영문명", "개장 연도", "리노베이션 연도",
                                      "성급", "총 객실 수", "프런트 운영"])


def rows_step(num, rows, title="호텔 정보 입력", save="저장"):
    body = "\n".join(f"| {k} | {v} |" for k, v in rows)
    return f"""
## {num}. {title}
탭: `호텔 정보`

| 칸 | 값 |
|---|---|
{body}

→ [{save}]
"""


class RepeatRowFormatTest(unittest.TestCase):
    """반복 행 이름은 `<칸 이름> <N> · <하위 칸>` 한 형식뿐이다."""

    def problems(self, label):
        md = HEAD + rows_step(4, [(label, "값")])
        return cm.find_repeat_row_format_gaps(steps_of(md))

    def test_canonical_form_passes(self):
        for label in ("구간 1 · 수수료 값", "추천 포인트 2 · 제목",
                      "포함물 1 · 포함물 이름", "요율 10 · 시작 시각"):
            self.assertEqual(self.problems(label), [], label)

    def test_wide_middot_is_an_error(self):
        problems = self.problems("구간 1 ・ 수수료 값")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("정본 형식이 아니다", problems[0])

    def test_missing_space_is_an_error(self):
        self.assertEqual(len(self.problems("구간 1· 수수료 값")), 1)
        self.assertEqual(len(self.problems("구간 1 ·수수료 값")), 1)

    def test_plain_labels_are_not_touched(self):
        for label in ("호텔명", "연령별 단가 · 초등학생", "오퍼별 표시명 · Single",
                      "정액 금액 (USD) 값", "성급"):
            self.assertEqual(self.problems(label), [], label)

    def test_the_example_manual_is_canonical(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            steps = cm.parse_steps(handle.read().splitlines())
        self.assertEqual(cm.find_repeat_row_format_gaps(steps), [])


class CheckValueClassTest(unittest.TestCase):
    """`체크`/`해제` 는 체크박스 칸에만 쓴다 — 다중 체크는 `선택: …` 또는 `비움`."""

    def setUp(self):
        self.kinds = cm.load_dictionary_kinds(DICTIONARY)

    def gaps(self, label, value):
        md = HEAD + rows_step(4, [(label, value)])
        return cm.find_check_value_class_gaps(steps_of(md), self.kinds)

    def test_multi_check_with_off_is_an_error(self):
        for label in ("요금제(선택)", "적용 룸 scope", "요일"):
            problems = self.gaps(label, "해제")
            self.assertEqual(len(problems), 1, (label, problems))
            self.assertIn("체크박스가 아니라", problems[0])
            self.assertIn("비움", problems[0])

    def test_multi_check_with_empty_or_choice_passes(self):
        for value in ("비움", "선택: 기본 요금제"):
            self.assertEqual(self.gaps("요금제(선택)", value), [], value)

    def test_real_checkbox_keeps_on_off(self):
        for label in ("이미 값이 있는 날도 덮기", "환불 가능", "제공 주기"):
            for value in ("체크", "해제"):
                self.assertEqual(self.gaps(label, value), [], (label, value))

    def test_unknown_labels_are_left_alone(self):
        self.assertEqual(self.gaps("사전에 없는 칸", "해제"), [])

    def test_the_example_manual_uses_the_right_class(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            steps = cm.parse_steps(handle.read().splitlines())
        self.assertEqual(cm.find_check_value_class_gaps(steps, self.kinds), [])


DICTIONARY_MD = os.path.join(SKILL, "references", "screen-dictionary.md")


def read_dictionary_md():
    """사람용 사전(.md)에서 화면 이름과 칸 이름을 차례대로 읽는다.

    `## <번호>. <화면 이름>` 이 화면이고, 그 아래 `| 칸 | 종류 | …` 표의 첫 열이 칸 이름이다.
    (배너 문구 표처럼 머리가 다른 표는 세지 않는다.)
    """
    import re
    screens, cur, in_table = [], None, False
    with open(DICTIONARY_MD, encoding="utf-8") as handle:
        for line in handle.read().splitlines():
            m = re.match(r"^## (\d+)\.\s*(.+?)\s*$", line)
            if m:
                cur = {"num": int(m.group(1)), "name": m.group(2), "fields": []}
                screens.append(cur)
                in_table = False
                continue
            if line.startswith("## "):
                cur, in_table = None, False
                continue
            if cur is None:
                continue
            if line.startswith("| 칸 | 종류 |"):
                in_table = True
                continue
            if in_table:
                if not line.startswith("|"):
                    in_table = False
                    continue
                cells = [c.strip() for c in line.strip("|").split("|")]
                if set("".join(cells)) <= set("- "):   # 표 머리 아래 구분 줄
                    continue
                cur["fields"].append(cells[0])
    return screens


def read_dictionary_json():
    """기계용 사전(.json)에서 같은 것을 읽는다 — 참조(`ref`) 줄은 정본을 따라간다."""
    import json
    with open(DICTIONARY, encoding="utf-8") as handle:
        data = json.load(handle)
    out = []
    for screen in data["screens"]:
        source = data[screen["ref"]] if screen.get("ref") else screen
        labels = [f["label"] for b in (source.get("blocks") or []) for f in (b.get("fields") or [])]
        out.append({"name": screen["name"], "fields": labels})
    return out


class DictionaryMdJsonAgreeTest(unittest.TestCase):
    """`.json` 은 `.md` 의 기계용 사본이다 — 화면 이름·칸 이름·차례가 한 글자도 다르면 안 된다.

    지시서를 쓰는 쪽은 `.md` 를 읽고 검사기는 `.json` 만 읽는다. 둘이 벌어지면 사람이 보고 쓴
    칸을 검사기가 모른다고 하거나, 그 반대가 된다 — 이 시험이 그 벌어짐을 막는다.
    """

    def setUp(self):
        self.md = read_dictionary_md()
        self.js = read_dictionary_json()

    def test_screen_count_matches(self):
        self.assertEqual(len(self.md), len(self.js))

    def test_screen_numbers_run_in_order(self):
        self.assertEqual([s["num"] for s in self.md], list(range(1, len(self.md) + 1)))

    def test_screen_names_match_in_order(self):
        self.assertEqual([s["name"] for s in self.md], [s["name"] for s in self.js])

    def test_field_labels_and_order_match(self):
        for md, js in zip(self.md, self.js):
            self.assertEqual(md["fields"], js["fields"], f"{md['num']}. {md['name']}")

    def test_the_meta_count_matches_the_screens(self):
        import json
        with open(DICTIONARY, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["meta"]["screen_count"], len(self.js))


class ValidationScreenTest(unittest.TestCase):
    """검증 배너는 사전에 **한 벌만** 있다 — 최상위 `validation` 이 정본이고 `screens` 줄은 참조다."""

    def setUp(self):
        import json
        with open(DICTIONARY, encoding="utf-8") as handle:
            self.data = json.load(handle)

    def test_screens_hold_only_a_reference(self):
        rows = [s for s in self.data["screens"] if s["id"] == "validation"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ref"], "validation")
        self.assertNotIn("blocks", rows[0])
        self.assertNotIn("rules", rows[0])

    def test_the_authoritative_copy_has_the_rules(self):
        auth = self.data["validation"]
        self.assertTrue(auth["rules"])
        self.assertTrue(auth["blocks"])
        severities = {r["severity"] for r in auth["rules"]}
        self.assertEqual(severities, {"차단", "경고"})

    def test_the_field_still_loads_into_the_dictionary(self):
        """참조 줄이 됐어도 그 화면의 칸(`사유`)은 사전 대조에 들어와야 한다."""
        self.assertIn("사유", cm.load_dictionary(DICTIONARY))


class AddressCellTest(unittest.TestCase):
    """주소 칸의 필지 번호(`Lot TT13`)는 시트 좌표로 보지 않는다."""

    MD = HEAD + """
## 4. 호텔 정보 입력
탭: `호텔 정보`

| 칸 | 값 |
|---|---|
| 주소(도로명 전체) | Lot TT13, Zone 4, Somewhere |

→ [저장]
"""

    def test_address_lot_number_is_not_a_cell(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.MD)
            self.assertEqual(cm.check(path)["sheet_cells"], [])


def child_addon_step(num, name, title="부가옵션 만들기", extra=()):
    body = "\n".join(f"| {k} | {v} |" for k, v in extra)
    return f"""
## {num}. {title} (1개, {name})
탭: `부가옵션`
버튼: [부가옵션 추가]

| 칸 | 값 |
|---|---|
| 오퍼 | 선택: 오퍼A |
| 이름 | {name} |
{body}

→ [추가]
"""


def free_band_step(num, code, label, low, high):
    return f"""
## {num}. 연령 구간 만들기 (1번째, {label})
탭: `오퍼`
카드: `오퍼A`
버튼: [연령 구간 추가]

| 칸 | 값 |
|---|---|
| 밴드 코드 | {code} |
| 노출명 | {label} |
| 최소 연령 | {low} |
| 최대 연령 | {high} |
| 방 인원수에 포함 | 체크 |
| 요금 기준 유형 | 선택: 무료 |

→ [추가]
"""


class AudienceOnlyNameTest(unittest.TestCase):
    """부가옵션·부과금 이름은 무엇을 파는지로 시작한다 — 대상만 적으면 오류."""

    def test_audience_only_name_is_error(self):
        md = HEAD + child_addon_step(4, "소아 (만6~11세)")
        problems = cm.find_audience_only_names(steps_of(md))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("대상만 적혀 있다", problems[0])
        self.assertIn("하프보드 소아", problems[0])

    def test_bare_audience_name_is_error(self):
        md = HEAD + child_addon_step(4, "유아")
        self.assertEqual(len(cm.find_audience_only_names(steps_of(md))), 1)

    def test_product_first_name_is_ok(self):
        md = HEAD + child_addon_step(4, "하프보드 소아 (만6~11세)")
        self.assertEqual(cm.find_audience_only_names(steps_of(md)), [])

    def test_surcharge_step_is_checked_too(self):
        md = HEAD + child_addon_step(4, "아동", title="부과금 추가")
        self.assertEqual(len(cm.find_audience_only_names(steps_of(md))), 1)

    def test_other_step_kinds_are_not_checked(self):
        md = HEAD + child_addon_step(4, "소아", title="혜택 추가")
        self.assertEqual(cm.find_audience_only_names(steps_of(md)), [])

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            steps = cm.parse_steps(handle.read().splitlines())
        self.assertEqual(cm.find_audience_only_names(steps), [])


class ChildPolicyAgeBandTest(unittest.TestCase):
    """아동이 방에서 잔다는 말이 보이는데 연령 구간 단계가 없으면 경고."""

    FREE_STAY = (("설명", "룸별 최대 인원 내 소아·유아 무료 투숙 (쉐어베드)"),)

    def test_child_free_stay_without_age_band_is_warning(self):
        md = HEAD + child_addon_step(4, "조식 소아", extra=self.FREE_STAY)
        problems = cm.find_child_policy_without_age_band(steps_of(md))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("연령 구간 단계가 없다", problems[0])

    def test_benefit_step_is_checked_too(self):
        md = HEAD + child_addon_step(4, "소아 쉐어베드 무료 투숙", title="혜택 추가")
        self.assertEqual(len(cm.find_child_policy_without_age_band(steps_of(md))), 1)

    def test_age_band_step_silences_it(self):
        md = HEAD + free_band_step(4, "INFANT", "유아", 0, "4.99") + child_addon_step(5, "조식 소아", extra=self.FREE_STAY)
        self.assertEqual(cm.find_child_policy_without_age_band(steps_of(md)), [])

    def test_addon_without_child_words_is_ok(self):
        md = HEAD + child_addon_step(4, "엑스트라베드 (1대)")
        self.assertEqual(cm.find_child_policy_without_age_band(steps_of(md)), [])

    def test_child_word_without_stay_words_is_ok(self):
        md = HEAD + child_addon_step(4, "하프보드 소아 (만6~11세)")
        self.assertEqual(cm.find_child_policy_without_age_band(steps_of(md)), [])

    def test_it_is_a_warning_not_an_error(self):
        md = HEAD + child_addon_step(4, "조식 소아", extra=self.FREE_STAY)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            r = cm.check(path)
        self.assertEqual(len(r["child_policy_gaps"]), 1)
        self.assertEqual(r["audience_only_names"], [])

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            steps = cm.parse_steps(handle.read().splitlines())
        self.assertEqual(cm.find_child_policy_without_age_band(steps), [])


class AgeRateFieldStrictTest(unittest.TestCase):
    """자리표시 라벨(`연령별 단가 · 〈연령 구간 노출명〉`)로만 사전에 있는 칸도 `--strict` 를 지나야 한다.

    사전은 부과금 드로어의 연령별 단가 표를 한 줄로 담는데, 지시서는 그 자리에 실제 구간
    이름을 넣어 쓴다 — 사전 대조가 bare 이름(`연령별 단가`)도 받아야 통과한다.
    """

    #: HEAD 의 `통화` 는 사전에 없는 이름이라 그것만으로 `--strict` 가 걸린다 — 사전 이름으로 바꾼다.
    CLEAN_HEAD = HEAD.replace("| 통화 |", "| 공급 통화 |")

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, md):
        path = os.path.join(self.dir.name, "manual.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(md)
        return path

    def manual(self, field="연령별 단가"):
        md = (self.CLEAN_HEAD + offer_step(4)
              + age_band_step(5, name="소아", code="CHILD")
              + charge_with_age_rate(6, band="소아"))
        return md.replace("연령별 단가 · 소아", f"{field} · 소아")

    def test_age_rate_row_passes_strict(self):
        path = self.write(self.manual())
        self.assertEqual(cm.check(path, dictionary_path=DICTIONARY)["unknown_fields"], [])
        self.assertEqual(cm.main([path, "--dictionary", DICTIONARY, "--strict"]), 0)

    def test_a_wrong_field_name_is_still_caught(self):
        """`연령별 요금` 은 사전에 없다 — 자리표시 완화가 아무 이름이나 받아 주면 안 된다."""
        path = self.write(self.manual(field="연령별 요금"))
        self.assertEqual(cm.check(path, dictionary_path=DICTIONARY)["unknown_fields"],
                         ["연령별 요금 · 소아"])
        self.assertEqual(cm.main([path, "--dictionary", DICTIONARY, "--strict"]), 1)


def gala_addon_step(num, name="갈라디너 (12/24)", rule="선택: 의무 아님 (고객이 원할 때만 선택)"):
    """갈라디너를 `부가옵션 만들기` 로 넣은 단계 — 고객이 뺄 수 있어 그 돈이 청구되지 않는다."""
    return f"""
## {num}. 부가옵션 만들기 (1개, {name})
탭: `부가옵션`
버튼: [부가옵션 추가]

| 칸 | 값 |
|---|---|
| 오퍼 | 선택: 2026 시즌 요금 |
| 이름 | {name} |
| 적용 방식 | 선택: 1회 적용 (박수·날짜와 무관) |
| 화면 섹션 | 선택: 식사 |
| 의무 규칙 | {rule} |

→ [추가]
"""


def gala_charge_step(num, name="갈라디너 (12/24)", unit="선택: 인당", rows=(),
                     card="`2026 시즌 요금`"):
    """갈라디너를 부과금으로 넣은 단계 — 기본형은 연령별 단가 줄 없이 성인 단가만 있는 모습."""
    body = "".join(f"| {k} | {v} |\n" for k, v in rows)
    return f"""
## {num}. 부과금 추가 (1개, {name})
탭: `부과금`
카드: {card}
버튼: [부과금 추가]

| 칸 | 값 |
|---|---|
| 종류 | 선택: 기타 |
| 이름 | {name} |
| 부과 방식 | 선택: 정액 |
| 부과 단위 | {unit} |
| 정액 금액 (USD) | 선택: 지정 (0 포함) |
| 정액 금액 (USD) 값 | 120.00 |
| 부과 유형 | 선택: 의무 — 고객 선택 없이 자동으로 붙습니다 |
| 적용 날짜 (선택) | 2026-12-24 |
| 적용 룸 scope | 비움 |
{body}
→ [추가]
"""


class GalaDinnerAddonTest(unittest.TestCase):
    """갈라디너·컴펄서리 디너는 의무 부과금 하나다 — 부가옵션으로 넣으면 오류."""

    def problems(self, md):
        return cm.find_gala_addons(steps_of(md))

    def test_gala_addon_is_error(self):
        problems = self.problems(HEAD + gala_addon_step(4))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("갈라디너는 의무 부과금", problems[0])
        self.assertIn("(선택) 을 붙인다", problems[0])

    def test_spaced_gala_name_is_error(self):
        self.assertEqual(len(self.problems(HEAD + gala_addon_step(4, "갈라 디너 (12/31)"))), 1)

    def test_english_gala_name_is_error(self):
        self.assertEqual(len(self.problems(HEAD + gala_addon_step(4, "Gala Dinner (12/24)"))), 1)

    def test_compulsory_dinner_name_is_error(self):
        self.assertEqual(len(self.problems(HEAD + gala_addon_step(4, "컴펄서리 디너 (12/31)"))), 1)
        self.assertEqual(len(self.problems(HEAD + gala_addon_step(4, "Compulsory Dinner"))), 1)

    def test_optional_mark_allows_the_addon(self):
        """계약서가 선택이라고 못 박은 디너만 부가옵션이다 — 이름 끝의 `(선택)` 이 그 표시다."""
        self.assertEqual(self.problems(HEAD + gala_addon_step(4, "갈라디너 (선택)")), [])

    def test_ordinary_addon_is_untouched(self):
        self.assertEqual(self.problems(HEAD + gala_addon_step(4, "엑스트라베드 (1대)")), [])

    def test_the_surcharge_route_is_not_flagged(self):
        md = HEAD + gala_charge_step(4, rows=(("연령별 단가 · 소아", "60.00"),))
        self.assertEqual(self.problems(md), [])

    def test_it_is_an_error_not_a_warning(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(HEAD + gala_addon_step(4))
            self.assertEqual(len(cm.check(path)["gala_addons"]), 1)
            self.assertEqual(cm.main([path]), 1)


class GalaDinnerSurchargeTest(unittest.TestCase):
    """갈라디너 부과금은 `인당` 이고, 오퍼에 연령 구간이 있으면 `연령별 단가` 줄을 지닌다."""

    def problems(self, md):
        return cm.find_gala_surcharge_gaps(steps_of(md))

    def with_band(self, charge):
        return HEAD + offer_step(4) + age_band_step(5, name="소아", code="CHILD") + charge

    def test_missing_age_rate_row_is_error(self):
        problems = self.problems(self.with_band(gala_charge_step(6)))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("6단계", problems[0])
        self.assertIn("연령별 단가 줄이 없다", problems[0])
        self.assertIn("성인만이면 유아·소아 0", problems[0])

    def test_age_rate_row_passes(self):
        md = self.with_band(gala_charge_step(6, rows=(("연령별 단가 · 소아", "60.00"),)))
        self.assertEqual(self.problems(md), [])

    def test_zero_for_adults_only_event_passes(self):
        md = self.with_band(gala_charge_step(6, rows=(("연령별 단가 · 소아", "0"),)))
        self.assertEqual(self.problems(md), [])

    def test_wrong_unit_is_error(self):
        md = self.with_band(gala_charge_step(6, unit="선택: 체류당 1회",
                                             rows=(("연령별 단가 · 소아", "60.00"),)))
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("6단계", problems[0])
        self.assertIn("`부과 단위`", problems[0])
        self.assertIn("인당", problems[0])

    def test_no_age_band_means_no_age_rate_row_needed(self):
        """연령 구간이 없는 오퍼에는 그 칸이 화면에 서지 않는다 — 없다고 나무라지 않는다."""
        self.assertEqual(self.problems(HEAD + offer_step(4) + gala_charge_step(5)), [])

    def test_bands_on_another_offer_do_not_count(self):
        md = (HEAD + offer_step(4) + age_band_step(5, name="소아", code="CHILD", card="`오퍼B`")
              + gala_charge_step(6))
        self.assertEqual(self.problems(md), [])

    def test_ordinary_surcharge_is_untouched(self):
        md = self.with_band(gala_charge_step(6, name="리조트피", unit="선택: 박당"))
        self.assertEqual(self.problems(md), [])

    def test_it_is_an_error_not_a_warning(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.with_band(gala_charge_step(6)))
            self.assertEqual(len(cm.check(path)["gala_surcharge_gaps"]), 1)
            self.assertEqual(cm.main([path]), 1)


class AdultOnlyChargeNameTest(unittest.TestCase):
    """부과금 이름이 `(성인)` 으로 끝나면 경고 — 아이 몫이 다른 곳에 남아 있다는 뜻이다."""

    def problems(self, md):
        return cm.find_adult_only_charge_names(steps_of(md))

    def test_adult_suffix_is_warning(self):
        problems = self.problems(HEAD + gala_charge_step(4, name="갈라디너 (성인)"))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("성인·소아를 부과금 하나의 연령별 단가로 합친다", problems[0])

    def test_spaced_suffix_is_warning(self):
        self.assertEqual(len(self.problems(HEAD + gala_charge_step(4, name="갈라디너 ( 성인 )"))), 1)

    def test_adult_in_the_middle_is_ok(self):
        md = HEAD + gala_charge_step(4, name="갈라디너 (12/24)",
                                     rows=(("연령별 단가 · 소아", "60.00"),))
        self.assertEqual(self.problems(md), [])

    def test_it_is_a_warning_not_an_error(self):
        md = (HEAD + offer_step(4) + age_band_step(5, name="소아", code="CHILD")
              + gala_charge_step(6, name="갈라디너 (성인)",
                                 rows=(("연령별 단가 · 소아", "60.00"),)))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            r = cm.check(path)
        self.assertEqual(len(r["adult_only_names"]), 1)
        self.assertEqual(r["gala_addons"], [])
        self.assertEqual(r["gala_surcharge_gaps"], [])


class GalaDinnerCleanManualTest(unittest.TestCase):
    """규칙서 §갈라디너·행사 요금 대로 적은 원고는 세 검사를 모두 지난다."""

    def manual(self):
        return (HEAD + offer_step(4)
                + age_band_step(5, name="소아", code="CHILD")
                + gala_charge_step(6, rows=(("연령별 단가 · 소아", "60.00"),
                                            ("연령별 단가 · 유아", "0"))))

    def test_all_three_checks_pass(self):
        steps = steps_of(self.manual())
        self.assertEqual(cm.find_gala_addons(steps), [])
        self.assertEqual(cm.find_gala_surcharge_gaps(steps), [])
        self.assertEqual(cm.find_adult_only_charge_names(steps), [])

    def test_the_example_manual_is_clean(self):
        """예시 원고에는 갈라디너가 없다 — 세 검사가 아무것도 잡지 않아야 한다."""
        with open(EXAMPLE, encoding="utf-8") as handle:
            steps = cm.parse_steps(handle.read().splitlines())
        self.assertEqual(cm.find_gala_addons(steps), [])
        self.assertEqual(cm.find_gala_surcharge_gaps(steps), [])
        self.assertEqual(cm.find_adult_only_charge_names(steps), [])


def benefit_step(num, title="혜택 추가", name="웰컴 드링크 제공", quantity="비움",
                  frequency_field="제공 주기", frequency="해제", extra=()):
    body = "\n".join(f"| {k} | {v} |" for k, v in extra)
    return f"""
## {num}. {title} (1번째, {name})
탭: `혜택`
버튼: [혜택 추가]

| 칸 | 값 |
|---|---|
| 소속 택1 그룹 | 선택: (그룹 없음 — 상시 포함되는 단독 혜택) |
| 혜택 이름 | {name} |
| 수량 | {quantity} |
| {frequency_field} | {frequency} |
{body}

→ [추가]
"""


class BenefitFrequencyWithoutQuantityTest(unittest.TestCase):
    """`수량` 이 비었는데 `제공 주기` 를 체크했으면 오류 — 그 칸은 수량이 있어야 화면에 선다."""

    def problems(self, md):
        return cm.find_benefit_frequency_without_quantity(steps_of(md))

    def test_checked_frequency_without_quantity_is_error(self):
        problems = self.problems(HEAD + benefit_step(4, quantity="비움", frequency="체크"))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("수량이 비어 있는데 `제공 주기` 를 체크했다", problems[0])
        self.assertIn("수량을 채우거나 제공 주기를 해제한다", problems[0])

    def test_missing_quantity_row_with_checked_frequency_is_error(self):
        """`수량` 줄 자체가 없어도(반려된 행 등) 같은 오류다."""
        md = f"""
## 4. 혜택 추가 (1번째, 웰컴 드링크 제공)
탭: `혜택`
버튼: [혜택 추가]

| 칸 | 값 |
|---|---|
| 혜택 이름 | 웰컴 드링크 제공 |
| 제공 주기 | 체크 |

→ [추가]
"""
        problems = self.problems(HEAD + md)
        self.assertEqual(len(problems), 1, problems)

    def test_checked_frequency_with_quantity_passes(self):
        self.assertEqual(self.problems(HEAD + benefit_step(4, quantity="1", frequency="체크")), [])

    def test_unchecked_frequency_without_quantity_passes(self):
        self.assertEqual(self.problems(HEAD + benefit_step(4, quantity="비움", frequency="해제")), [])

    def test_checkbox_text_suffix_field_name_is_detected(self):
        """원고가 `제공 주기 · 1박당 제공 (비우면 체류당)` 처럼 체크박스 문구를 붙여 써도 잡는다."""
        md = benefit_step(4, quantity="비움",
                           frequency_field="제공 주기 · 1박당 제공 (비우면 체류당)", frequency="체크")
        problems = self.problems(HEAD + md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])

    def test_candidate_title_is_checked_too(self):
        """택1 그룹 후보(`[이 그룹에 혜택 추가]`)도 같은 드로어다."""
        md = benefit_step(4, title="택1 그룹 후보 추가", quantity="비움", frequency="체크")
        problems = self.problems(HEAD + md)
        self.assertEqual(len(problems), 1, problems)

    def test_it_is_an_error_not_a_warning(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(HEAD + benefit_step(4, quantity="비움", frequency="체크"))
            self.assertEqual(len(cm.check(path)["benefit_frequency_gaps"]), 1)
            self.assertEqual(cm.main([path]), 1)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            steps = cm.parse_steps(handle.read().splitlines())
        self.assertEqual(cm.find_benefit_frequency_without_quantity(steps), [])
