#!/usr/bin/env python3
"""check_manual.py 검사 규칙 시험.

실행:
    python3 -m unittest discover -s skills/stay-setup-guide/tests -v
    (또는 pytest skills/stay-setup-guide/tests)
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
        #: `작성일:` 은 **첫 단계 앞**에 있어야 "오늘" 로 읽힌다 — 뒤에 두면 검사하는 날이 오늘이
        #: 되어 시험이 날짜에 흔들린다(2026-09-08 에 실제로 깨졌다).
        md = "# 시험 호텔 — 입력 지시서\n\n작성일: 2026-09-07\n" + HEAD.split("\n", 1)[1] \
            + offer_dates_step(4, book_start="비움")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
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

    def test_the_man_nai_labels_are_read_too(self):
        """나이 칸 이름이 `최소 연령 (만 나이)` 로 바뀌어도 겹침을 잡는다.

        2026-09-08 에 화면 라벨이 바뀌었다(`OfferAgeBandForm.__init__`). 이름 하나만 보던
        동안에는 새 라벨을 쓴 원고에서 이 검사가 **조용히 건너뛰었다** — 화면이 거부하는
        원고가 검사를 통과해, 담당자는 그 단계에 가서야 막힌다.
        """
        md = (HEAD + offer_step(4)
              + age_band_range_step(5, "유아", "INF", "0", "6")
              + age_band_range_step(6, "소아", "CHD", "6", "11.99"))
        md = md.replace("| 최소 연령 |", "| 최소 연령 (만 나이) |")
        md = md.replace("| 최대 연령 |", "| 최대 연령 (만 나이) |")
        self.assertIn("최소 연령 (만 나이)", md)
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("겹친다", problems[0])


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


def read_dictionary_md_rows():
    """`.md` 의 칸 표를 `{(화면, 칸): (언제 보임, 거부 문구 목록)}` 으로 읽는다."""
    import re
    rows, screen, in_table = {}, None, False
    with open(DICTIONARY_MD, encoding="utf-8") as handle:
        for line in handle.read().splitlines():
            m = re.match(r"^## \d+\.\s*(.+?)\s*$", line)
            if m:
                screen, in_table = m.group(1), False
                continue
            if line.startswith("| 칸 | 종류 |"):
                in_table = True
                continue
            if not in_table:
                continue
            if not line.startswith("|"):
                in_table = False
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) != 6 or set("".join(cells)) <= set("- "):
                continue
            reject = [p.strip() for p in cells[5].split(" / ") if p.strip()]
            rows[(screen, cells[0])] = (cells[4], reject)
    return rows


def read_dictionary_json_rows():
    """`.json` 에서 같은 것을 — 참조(`ref`) 줄은 정본을 따라간다."""
    import json
    with open(DICTIONARY, encoding="utf-8") as handle:
        data = json.load(handle)
    rows = {}
    for screen in data["screens"]:
        source = data[screen["ref"]] if screen.get("ref") else screen
        for block in source.get("blocks") or []:
            for field in block.get("fields") or []:
                rows[(screen["name"], field["label"])] = (
                    field.get("visible_when") or "", list(field.get("reject") or [])
                )
    return rows


class DictionaryRejectAndVisibilityAgreeTest(unittest.TestCase):
    """두 사본은 **거부 문구와 보임 조건**까지 같은 글자여야 한다.

    라벨만 견주던 동안 한쪽만 고친 내용이 오래 남았다(2026-09-09 Codex 리뷰 12): `.json` 은
    연령 범위를 옛 표기 `만 N~M세` 로 설명하고 있었고, 시간대별 요율이 있을 때 연령별 단가
    표가 사라진다는 조건은 `.md` 에만 있었다. 거부 문구·보임 조건은 화면이 실제로 뱉는 글자라
    두 사본이 다르면 한쪽을 보고 쓴 원고가 다른 쪽 검사와 어긋난다.

    도움말 산문까지 글자로 묶지는 않는다 — 같은 뜻을 다른 문장으로 적는 자리라, 여기서
    묶으면 사전을 손보는 일이 시험을 고치는 일이 된다.
    """

    def setUp(self):
        self.md = read_dictionary_md_rows()
        self.js = read_dictionary_json_rows()

    def test_the_same_rows_are_in_both(self):
        self.assertEqual(sorted(self.md), sorted(self.js))

    def test_reject_messages_match(self):
        for key in sorted(self.md):
            self.assertEqual(self.md[key][1], self.js[key][1], key)

    def test_visible_conditions_match(self):
        for key in sorted(self.md):
            self.assertEqual(self.md[key][0], self.js[key][0], key)

    def test_the_age_range_wording_is_the_current_one(self):
        """`만 N~M세` 는 2026-09-08 에 없어진 표기다 — 두 사본 어디에도 남으면 안 된다."""
        for path in (DICTIONARY_MD, DICTIONARY):
            with open(path, encoding="utf-8") as handle:
                self.assertNotIn("만 N~M세", handle.read(), path)


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


class OccupancyKeyIsNotASheetCellTest(unittest.TestCase):
    """인원 조합 줄의 A-형 좌표(`A2,A3`)는 시트 좌표가 아니다 — **행으로** 거른다.

    `CELL_EXCLUDE` 에 `^A\\d{1,2}$` 를 더하는 길도 있었지만 쓰지 않는다: `A2` 를 통과시키는
    대신 **진짜 시트 A열 좌표 `A70` 까지 눈감아** 오탐을 미탐으로 바꾼다. 아래 두 시험이
    그 둘을 함께 잠근다.
    """

    def cells(self, body):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(HEAD + body)
            return cm.check(path)["sheet_cells"]

    FILL = """
## 4. 시즌 가격 채우기 (1회차, Low × Deluxe)
탭: `시즌`
카드: `Low`
버튼: [가격]

| 칸 | 값 |
|---|---|
| 판매 단가(공급 통화) | 92.00 |
| 인원 조합(선택) | A2,A3 |
| 인원 조합별 조정(선택) | A3:+30 |

→ [이 단가로 깔기]
"""

    def test_a_form_occupancy_keys_are_not_sheet_cells(self):
        self.assertEqual(self.cells(self.FILL), [])

    def test_a_column_sheet_coordinate_is_still_caught(self):
        """`A70` 은 여전히 의심이다 — 인원 조합 줄이 아닌 자리에 있으면 시트 좌표다."""
        body = """
## 4. 호텔 정보 입력
탭: `호텔 정보`

| 칸 | 값 |
|---|---|
| 소개 | 요금표 A70 참고 |

→ [저장]
"""
        self.assertEqual(self.cells(body), ["A70"])

    def test_other_columns_are_still_caught(self):
        body = """
## 4. 호텔 정보 입력
탭: `호텔 정보`

| 칸 | 값 |
|---|---|
| 소개 | 요금표 B47 참고 |

→ [저장]
"""
        self.assertEqual(self.cells(body), ["B47"])

    def test_head_lines_that_name_an_occupancy_key_are_clean(self):
        """`카드:`·`주의:` 줄도 A-형을 부른다 — 표 행만 걸러서는 모자라다."""
        body = """
## 4. 가격 셀 손으로 고치기 (1번째, 2026-09-15)
탭: `가격 캘린더`
카드: `기본 · Deluxe` × `조식 포함` 의 인원 조합 `A2` 행
주의: 이 룸만 인원 조합이 `A2` 하나다. 인원 조합별 조정은 비운다

| 칸 | 값 |
|---|---|
| 판매가 | 120.00 |

→ [저장]
"""
        self.assertEqual(self.cells(body), [])

    def test_a_real_coordinate_on_an_occupancy_line_is_still_caught(self):
        """줄만 보고 통째로 건너뛰면 안 된다 — 그 줄의 `B47` 은 여전히 시트 좌표다."""
        body = """
## 4. 호텔 정보 입력
탭: `호텔 정보`
주의: 인원 조합은 요금표 B47 참고

| 칸 | 값 |
|---|---|
| 소개 | 바다 앞 |

→ [저장]
"""
        self.assertEqual(self.cells(body), ["B47"])

    def test_a_multi_band_key_is_not_a_sheet_cell(self):
        """`A2C1_CHD_C1_INF` 의 둘째 조각 머리 `_C1` 은 C열 좌표가 아니다.

        좌표를 **조각**으로 거르던 동안 그 `C1` 이 「좌표 의심」으로 남았고, 서버가 정상으로
        받는 키에 전체 검사기가 종료 코드 1을 냈다(2026-09-09 Codex 리뷰 3).
        """
        body = self.FILL.replace("| 인원 조합(선택) | A2,A3 |",
                                 "| 인원 조합(선택) | A2C1_CHD_C1_INF |")
        body = body.replace("| 인원 조합별 조정(선택) | A3:+30 |", "")
        self.assertEqual(self.cells(body), [])

    def test_a_multi_band_key_passes_the_whole_checker(self):
        """조각 검사만 고치면 모자란다 — `check`/`main` 전체 경로까지 통과해야 한다."""
        with open(EXAMPLE, encoding="utf-8") as handle:
            text = handle.read()
        text = text.replace("| 인원 조합(선택) | A1 |",
                            "| 인원 조합(선택) | A2C1_CHD_C1_INF |", 1)
        with tempfile.TemporaryDirectory() as d:
            share = os.path.join(d, "우에노_토우가네야", "_원고")
            os.makedirs(share)
            path = os.path.join(share, "manual.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            self.assertEqual(cm.check(path)["sheet_cells"], [])
            self.assertEqual(cm.main([path, "--dictionary", DICTIONARY]), 0)


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

    def test_child_named_addon_without_age_band_is_warning(self):
        """파는 것이 식사라도 그 아이를 인원으로 고를 수 없으면 아무도 살 수 없다(§E-7)."""
        md = HEAD + child_addon_step(4, "하프보드 소아 (만6~11세)")
        problems = cm.find_child_policy_without_age_band(steps_of(md))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("연령 구간 단계가 없다", problems[0])

    def test_it_is_reported_once_per_step(self):
        """이름과 글 둘 다 걸려도 한 단계는 한 번만 알린다."""
        md = HEAD + child_addon_step(4, "쉐어베드 소아", extra=self.FREE_STAY)
        self.assertEqual(len(cm.find_child_policy_without_age_band(steps_of(md))), 1)

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
        """택1 그룹 후보(`[이 그룹에 혜택 추가]`)도 같은 드로어다 — 정본과 별칭 셋 다 본다.

        정본 `그룹에 혜택 추가` 가 빠져 있던 동안, 정본으로 적은 원고는 이 검사를 통째로
        건너뛰었다(D·F 의 6단계가 그 표기로 정규화되면서 드러났다).
        """
        for title in ("그룹에 혜택 추가", "택1 그룹 후보 추가", "택1 후보 혜택 추가"):
            md = benefit_step(4, title=title, quantity="비움", frequency="체크")
            problems = self.problems(HEAD + md)
            self.assertEqual(len(problems), 1, (title, problems))

    def test_the_benefit_titles_are_known_step_kinds(self):
        """혜택 드로어 제목은 전부 러너가 아는 갈래다 — 오타면 검사가 조용히 헛돈다."""
        for title in cm.BENEFIT_STEP_TITLES:
            self.assertIn(title, cm.KNOWN_STEP_KINDS, title)

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


class HangulRoomNameTest(unittest.TestCase):
    """`룸 만들기` 의 `룸 이름` 에 한글이 있으면 경고 — 룸 이름은 계약서 원어 그대로다."""

    def problems(self, md):
        return cm.find_hangul_room_names(steps_of(md))

    def test_hangul_room_name_is_warning(self):
        problems = self.problems(HEAD + room_step(4, name="슈페리어 오션뷰"))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("룸 이름 슈페리어 오션뷰 에 한글이 있다", problems[0])
        self.assertIn("룸 이름은 계약서 원어, 한글은 오퍼별 표시명에", problems[0])

    def test_contract_name_passes(self):
        self.assertEqual(self.problems(HEAD + room_step(4, name="Superior Ocean View")), [])
        self.assertEqual(self.problems(HEAD + room_step(4, name="Deluxe Bungalow")), [])

    def test_mixed_name_is_warning(self):
        """원어 한 낱말만 남기고 옮겨 적은 이름도 같은 경고다."""
        self.assertEqual(len(self.problems(HEAD + room_step(4, name="디럭스 Bungalow"))), 1)

    def test_offer_display_name_is_not_checked(self):
        """`오퍼별 표시명` 은 한글이 정답이다 — 판매 연결 단계는 이 검사가 보지 않는다."""
        md = HEAD + room_link_step(4, rooms="Superior Ocean View", display="슈페리어 오션뷰")
        self.assertEqual(self.problems(md), [])

    def test_it_is_a_warning_not_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(HEAD + offer_step(4) + room_step(5, name="슈페리어 오션뷰"))
            self.assertEqual(len(cm.check(path)["hangul_room_names"]), 1)
            self.assertEqual(cm.main([path]), 0)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            steps = cm.parse_steps(handle.read().splitlines())
        self.assertEqual(cm.find_hangul_room_names(steps), [])


def extra_bed_step(num, name="엑스트라베드 (1대)",
                   rule="선택: 기준 성인 초과 시 의무 (엑스트라베드)"):
    """엑스트라베드 부가옵션 단계 — `의무 규칙` 만 바꿔 가며 쓴다."""
    return f"""
## {num}. 부가옵션 만들기 (1번째, {name})
탭: `부가옵션`
버튼: [부가옵션 추가]

| 칸 | 값 |
|---|---|
| 오퍼 | 선택: 2026 시즌 요금 |
| 이름 | {name} |
| 적용 방식 | 선택: 날짜연동 (박수 따라감 — 엑스트라베드) |
| 화면 섹션 | 선택: 침대 추가 |
| 의무 규칙 | {rule} |
| 수량 상한 | 1 |

→ [추가]
"""


class ExtraBedMandatoryRuleTest(unittest.TestCase):
    """엑스트라베드 부가옵션의 `의무 규칙` 이 `의무 아님` 이면 경고."""

    def problems(self, md):
        return cm.find_extra_bed_optional_rules(steps_of(md))

    def test_optional_rule_is_warning(self):
        md = HEAD + extra_bed_step(4, rule="선택: 의무 아님 (고객이 원할 때만 선택)")
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("엑스트라베드 의무 규칙이 `의무 아님`", problems[0])
        self.assertIn("`기준 성인 초과 시 의무`", problems[0])

    def test_over_adult_rule_passes(self):
        self.assertEqual(self.problems(HEAD + extra_bed_step(4)), [])

    def test_name_with_trailing_words_is_checked(self):
        """이름은 상품으로 시작하기만 하면 된다 — 뒤에 무엇이 붙어도 같은 검사다."""
        md = HEAD + extra_bed_step(4, name="엑스트라베드 성인 (조식 포함)",
                                   rule="선택: 의무 아님 (고객이 원할 때만 선택)")
        self.assertEqual(len(self.problems(md)), 1)

    def test_other_addons_are_not_checked(self):
        """침대가 아닌 부가옵션은 `의무 아님` 이 정상이다."""
        md = HEAD + extra_bed_step(4, name="풀보드 (중식+석식)",
                                   rule="선택: 의무 아님 (고객이 원할 때만 선택)")
        self.assertEqual(self.problems(md), [])

    def test_it_is_a_warning_not_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(HEAD + extra_bed_step(4, rule="선택: 의무 아님 (고객이 원할 때만 선택)"))
            self.assertEqual(len(cm.check(path)["extra_bed_rules"]), 1)
            self.assertEqual(cm.main([path]), 0)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            steps = cm.parse_steps(handle.read().splitlines())
        self.assertEqual(cm.find_extra_bed_optional_rules(steps), [])


# ─────────────────────────────────────────────────────────────────────────────
# 아동 요금 좌표·LOS·밴드 코드 (2026-09-08 정본) — 아이가 방에서 자는 1박 요금은
# `시즌 가격 채우기` 의 `아동 추가 금액 — <노출명>` 한 곳에만 둔다.
# ─────────────────────────────────────────────────────────────────────────────

def paid_band_step(num, name="소아", code="CHD", kind="정액", card="`2026 시즌 요금`"):
    """유료 연령 구간 — `요금 기준 유형` 이 `무료` 가 아니라 시즌 채우기에 아동 금액 칸이 선다."""
    return f"""
## {num}. 연령 구간 만들기 ({num}번째, {name})
탭: `오퍼`
카드: {card}
버튼: [연령 구간 추가]

| 칸 | 값 |
|---|---|
| 밴드 코드 | {code} |
| 노출명 | {name} |
| 최소 연령 (만 나이) | 5 |
| 최대 연령 (만 나이) | 11.99 |
| 방 인원수에 포함 | 체크 |
| 요금 기준 유형 | 선택: {kind} |
| 상세(자유텍스트) | 비움 |

→ [추가]
"""


def price_fill_step(num, season="Regular", room="Single", rows=()):
    """`시즌 가격 채우기` — 새 칸(인원 조합·박수별 단가·아동 추가 금액)을 줄로 더해 쓴다."""
    body = "".join(f"| {k} | {v} |\n" for k, v in rows)
    return f"""
## {num}. 시즌 가격 채우기 ({num}회차, {season} × {room})
탭: `시즌`
카드: `{season}`
버튼: [가격]

| 칸 | 값 |
|---|---|
| 판매 단가(공급 통화) | 92.00 |
| 대상 룸 | 선택: {room} |
{body}| 이미 값이 있는 날도 덮기 | 해제 |

→ [이 단가로 깔기]
"""


def child_price_manual(fill_rows=(), band_kind="정액", band_name="소아"):
    """오퍼 → 유료 연령 구간 → 시즌 → 가격 채우기 한 벌."""
    return (HEAD + offer_step(4)
            + paid_band_step(5, name=band_name, kind=band_kind)
            + season_step(6, "Regular", "2026 시즌 요금", RANGE)
            + price_fill_step(7, rows=fill_rows))


class ChildExtraAmountTest(unittest.TestCase):
    """유료 연령 구간마다 `아동 추가 금액 — <노출명>` 줄이 시즌 가격 채우기에 있어야 한다."""

    def problems(self, md):
        return cm.find_child_extra_missing(steps_of(md))

    def test_row_present_is_ok(self):
        md = child_price_manual(fill_rows=[("아동 추가 금액 — 소아", "23.18")])
        self.assertEqual(self.problems(md), [])

    def test_missing_row_is_error(self):
        md = child_price_manual(fill_rows=[("인원 조합(선택)", "A2,A3")])
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("5단계", problems[0])
        self.assertIn("아동 추가 금액 — 소아", problems[0])
        self.assertIn("그 칸 한 곳에만", problems[0])

    def test_free_band_needs_no_row(self):
        """`무료` 구간은 화면에 칸이 서지 않는다 — 줄을 적지 않는 것이 정본이다."""
        md = child_price_manual(band_kind="무료")
        self.assertEqual(self.problems(md), [])

    def test_percent_band_still_needs_the_row(self):
        """`성인 요금의 %` 구간도 칸은 선다(읽기 전용) — `자동 입력됨 · 그대로 둠` 으로 적는다."""
        rows = [("아동 추가 금액 — 소아", "자동 입력됨 · 그대로 둠")]
        self.assertEqual(self.problems(child_price_manual(fill_rows=rows, band_kind="성인 요금의 %")), [])
        self.assertEqual(len(self.problems(child_price_manual(band_kind="성인 요금의 %"))), 1)

    def test_typo_separators_are_accepted(self):
        """정본은 EM DASH 지만 원고 오타(EN DASH·하이픈·가운뎃점)로 검사가 헛돌면 안 된다."""
        for label in ("아동 추가 금액 – 소아", "아동 추가 금액 - 소아", "아동 추가 금액 · 소아"):
            md = child_price_manual(fill_rows=[(label, "23.18")])
            self.assertEqual(self.problems(md), [], label)

    def test_a_different_band_name_does_not_count(self):
        md = child_price_manual(fill_rows=[("아동 추가 금액 — 유아", "0")])
        self.assertEqual(len(self.problems(md)), 1)

    def test_another_offers_row_does_not_count(self):
        """구간은 오퍼의 자식이다 — 다른 오퍼의 시즌에 적힌 줄로는 채워지지 않는다."""
        md = (HEAD + offer_step(4)
              + paid_band_step(5, card="`2027 시즌 요금`")
              + season_step(6, "Regular", "2026 시즌 요금", RANGE)
              + price_fill_step(7, rows=[("아동 추가 금액 — 소아", "23.18")])
              + season_step(8, "Peak", "2027 시즌 요금", OUTSIDE)
              + price_fill_step(9, season="Peak"))
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("5단계", problems[0])

    def test_manual_without_price_fill_steps_is_skipped(self):
        """가격을 셀로 손입력하는 원고는 이 검사를 건너뛴다."""
        md = HEAD + offer_step(4) + paid_band_step(5)
        self.assertEqual(self.problems(md), [])

    def test_it_is_an_error_not_a_warning(self):
        md = child_price_manual()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            r = cm.check(path)
            self.assertEqual(len(r["child_extra_missing"]), 1, r["child_extra_missing"])
            self.assertEqual(cm.main([path]), 1)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(self.problems(handle.read()), [])


class ChildLodgingAddonTest(unittest.TestCase):
    """부가옵션은 **따로 사는 것**만 판다 — 아이의 잠자리는 `아동 추가 금액` 이다(§D-1)."""

    def problems(self, md):
        return cm.find_child_lodging_addon(steps_of(md))

    def test_share_bed_child_addon_is_error(self):
        md = HEAD + child_addon_step(4, "쉐어베드 소아 (만 5세 이하)")
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("아이의 1박 요금이다", problems[0])
        self.assertIn("아동 추가 금액", problems[0])

    def test_breakfast_bundled_share_bed_is_still_error(self):
        """파는 것이 잠자리면 조식이 묶여 있어도 그 값은 아이 1박 요금이다."""
        md = HEAD + child_addon_step(4, "쉐어베드 소아 (만 6~11세 · 조식 포함)")
        self.assertEqual(len(self.problems(md)), 1)

    def test_sofa_bed_and_bed_share_are_errors(self):
        for name in ("조식 + 소파베드 소아 (만 5~12세)", "소아 베드셰어 (만 8~11세)",
                     "child share bed (age 5-11)", "정원 내 유아 무료 투숙"):
            md = HEAD + child_addon_step(4, name)
            self.assertEqual(len(self.problems(md)), 1, name)

    def test_child_night_without_goods_is_error(self):
        md = HEAD + child_addon_step(4, "소아 추가 (만 5~11세) · 1박")
        self.assertEqual(len(self.problems(md)), 1)

    def test_meal_and_pickup_addons_are_ok(self):
        """식사 업그레이드·픽업은 따로 사는 것이라 이름에 아이가 들어가도 부가옵션이 맞다."""
        for name in ("하프보드 소아 (만 6~11세)", "조식 소아 (만 6~11세) 1박 1인",
                     "풀보드 소아 (만6~11세)", "공항 픽업 소아 · 1인",
                     "Halfboard child 6-11.99"):
            md = HEAD + child_addon_step(4, name)
            self.assertEqual(self.problems(md), [], name)

    def test_extra_bed_is_always_an_addon(self):
        """엑스트라베드는 방 정원 밖에 침대를 더 놓는 물건이라 언제나 부가옵션이다."""
        for name in ("엑스트라베드 소아 (만 6~11세) · 1박", "추가 침대 소아 (만 6세~12세 미만 · 조식 포함)"):
            md = HEAD + child_addon_step(4, name)
            self.assertEqual(self.problems(md), [], name)

    def test_adult_addon_is_not_checked(self):
        md = HEAD + child_addon_step(4, "성인 엑스트라베드 (만 12세 이상 · 조식 포함) · 1박")
        self.assertEqual(self.problems(md), [])

    def test_surcharge_step_is_not_checked(self):
        """부과금은 다른 갈래다 — 여기서는 `부가옵션 만들기` 만 본다."""
        md = HEAD + child_addon_step(4, "쉐어베드 소아", title="부과금 추가")
        self.assertEqual(self.problems(md), [])

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(self.problems(handle.read()), [])


class BandCodeFormatTest(unittest.TestCase):
    """밴드 코드는 영대문자·숫자 2~8자다 — 그 코드가 가격 셀 좌표에 그대로 실린다(A2C1_CHD)."""

    def problems(self, code):
        md = HEAD + offer_step(4) + paid_band_step(5, code=code)
        return cm.find_band_code_format(steps_of(md))

    def test_canonical_codes_are_ok(self):
        for code in ("CHD", "INF", "TEEN", "CHILD", "CH2", "CHD2026"):
            self.assertEqual(self.problems(code), [], code)

    def test_c_plus_number_is_error(self):
        """`C2` 는 정규식은 지나지만 좌표의 아동 조각 표기와 글자가 같다 — 서버가 따로 막는다.

        `occupancy_key.validate_band_code` 가 `^C\\d+$` 를 거부하는 이유는 왕복이 깨지기
        때문이다: 코드 `C1` 로 만든 `A2C1_C1` 을 `parse_key` 가 "1명 + 1명" 으로 읽는다.
        """
        problems = self.problems("C2")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("아동 조각 표기", problems[0])

    def test_lowercase_is_ok(self):
        """소문자로 쳐도 서버가 대문자로 굳힌다 — 막지 않는다."""
        self.assertEqual(self.problems("chd"), [])

    def test_underscore_is_error(self):
        problems = self.problems("CHILD_1")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("5단계", problems[0])
        self.assertIn("CHILD_1", problems[0])
        self.assertIn("2~8자", problems[0])

    def test_hangul_space_and_length_are_errors(self):
        for code in ("소아", "CH D", "C", "CHILDBAND9", "CHD-1"):
            self.assertEqual(len(self.problems(code)), 1, code)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_band_code_format(steps_of(handle.read())), [])


class OccupancyKeyTest(unittest.TestCase):
    """인원 조합 좌표는 A-형이다 — 옛 숫자 키(`2,3` · `3:+14`)는 오류."""

    def problems(self, rows):
        md = HEAD + price_fill_step(4, rows=rows)
        return cm.find_occupancy_key_legacy(steps_of(md))

    def test_a_form_keys_are_ok(self):
        rows = [("인원 조합(선택)", "A2,A3,A2C1_CHD,A2C1_CHD_C1_TEEN"),
                ("인원 조합별 조정(선택)", "A3:+14,A4:-5%")]
        self.assertEqual(self.problems(rows), [])

    def test_blank_is_ok(self):
        self.assertEqual(self.problems([("인원 조합(선택)", "비움"),
                                        ("인원 조합별 조정(선택)", "비움")]), [])

    def test_bare_number_keys_are_error(self):
        problems = self.problems([("인원 조합(선택)", "2,3")])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("옛 숫자 표기", problems[0])
        self.assertIn("A2,A3", problems[0])

    def test_bare_number_adjust_keys_are_error(self):
        problems = self.problems([("인원 조합별 조정(선택)", "3:+14,4:+26")])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("인원 조합별 조정", problems[0])
        self.assertIn("옛 숫자 표기", problems[0])

    def test_unreadable_key_is_error(self):
        problems = self.problems([("인원 조합(선택)", "성인 2명")])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("읽지 못한다", problems[0])

    def test_both_fields_are_reported(self):
        problems = self.problems([("인원 조합(선택)", "2,3"), ("인원 조합별 조정(선택)", "3:+14")])
        self.assertEqual(len(problems), 2, problems)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_occupancy_key_legacy(steps_of(handle.read())), [])


class LosPricesTest(unittest.TestCase):
    """`박수별 단가(선택)` 는 `박수:1박 단가` 목록이다 — 부호 없음 · 박수 2 이상 · 중복 없음."""

    def problems(self, value):
        md = HEAD + price_fill_step(4, rows=[("박수별 단가(선택)", value)])
        return cm.find_los_prices_format(steps_of(md))

    def test_canonical_value_is_ok(self):
        self.assertEqual(self.problems("3:100,5:90"), [])
        self.assertEqual(self.problems("2:120.50"), [])

    def test_blank_is_ok(self):
        self.assertEqual(self.problems("비움"), [])

    def test_signed_price_is_error(self):
        problems = self.problems("3:+100")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("부호를 붙이지 않는다", problems[0])

    def test_one_night_is_error(self):
        problems = self.problems("1:120,3:100")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("박수는 2 이상", problems[0])

    def test_duplicate_nights_is_error(self):
        problems = self.problems("3:100,3:90")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("두 번", problems[0])

    def test_prose_value_is_error(self):
        self.assertEqual(len(self.problems("3박부터 100")), 1)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_los_prices_format(steps_of(handle.read())), [])


class AgeBandBeforeSeasonFillTest(unittest.TestCase):
    """`연령 구간 만들기` 는 그 오퍼의 첫 `시즌 가격 채우기` 보다 앞이다(§D-2)."""

    def problems(self, md):
        return cm.find_age_band_order(steps_of(md))

    def test_band_before_fill_is_ok(self):
        self.assertEqual(self.problems(child_price_manual(
            fill_rows=[("아동 추가 금액 — 소아", "23.18")])), [])

    def test_band_after_fill_is_error(self):
        md = (HEAD + offer_step(4)
              + season_step(5, "Regular", "2026 시즌 요금", RANGE)
              + price_fill_step(6)
              + paid_band_step(7))
        problems = self.problems(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("7단계", problems[0])
        self.assertIn("시즌 가격 채우기", problems[0])
        self.assertIn("아동 추가 금액", problems[0])

    def test_another_offers_fill_does_not_count(self):
        md = (HEAD + offer_step(4)
              + season_step(5, "Regular", "2026 시즌 요금", RANGE)
              + price_fill_step(6)
              + paid_band_step(7, card="`2027 시즌 요금`"))
        self.assertEqual(self.problems(md), [])

    def test_manual_without_fill_steps_is_ok(self):
        self.assertEqual(self.problems(HEAD + offer_step(4) + paid_band_step(5)), [])

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(self.problems(handle.read()), [])


class ChildExtraWithoutOccupancyTest(unittest.TestCase):
    """아동 금액은 성인 좌표 위에 얹힌다 — `인원 조합` 이 비면 화면이 저장을 막는다(ERP 실측)."""

    def problems(self, rows):
        md = HEAD + price_fill_step(4, rows=rows)
        return cm.find_child_extra_without_occupancy(steps_of(md))

    def test_occupancy_with_child_extra_is_ok(self):
        rows = [("인원 조합(선택)", "A2,A3"), ("아동 추가 금액 — 소아", "23.18")]
        self.assertEqual(self.problems(rows), [])

    def test_blank_occupancy_with_child_extra_is_error(self):
        rows = [("인원 조합(선택)", "비움"), ("아동 추가 금액 — 소아", "23.18")]
        problems = self.problems(rows)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("인원 조합이 비어 있다", problems[0])
        self.assertIn("A2", problems[0])

    def test_no_child_extra_row_keeps_blank_occupancy_ok(self):
        """아동 줄이 없으면 인원 무관 단일가 한 좌표가 정본이다."""
        self.assertEqual(self.problems([("인원 조합(선택)", "비움")]), [])

    def test_readonly_percent_row_is_not_an_exception(self):
        """`성인 요금의 %` 구간의 `자동 입력됨 · 그대로 둠` 도 아동 금액 목록에 실린다."""
        rows = [("인원 조합(선택)", "비움"), ("아동 추가 금액 — 소아", "자동 입력됨 · 그대로 둠")]
        self.assertEqual(len(self.problems(rows)), 1)

    def test_missing_occupancy_row_is_error(self):
        self.assertEqual(len(self.problems([("아동 추가 금액 — 소아", "23.18")])), 1)

    def test_blank_child_amount_does_not_trigger(self):
        """값을 비운 아동 줄은 그 구간의 셀을 아예 만들지 않는다(§B-4)."""
        rows = [("인원 조합(선택)", "비움"), ("아동 추가 금액 — 소아", "비움")]
        self.assertEqual(self.problems(rows), [])

    def test_it_is_an_error_not_a_warning(self):
        md = (HEAD + offer_step(4) + paid_band_step(5)
              + season_step(6, "Regular", "2026 시즌 요금", RANGE)
              + price_fill_step(7, rows=[("인원 조합(선택)", "비움"),
                                         ("아동 추가 금액 — 소아", "23.18")]))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            r = cm.check(path)
            self.assertEqual(len(r["child_extra_no_occupancy"]), 1, r["child_extra_no_occupancy"])
            self.assertEqual(cm.main([path]), 1)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_child_extra_without_occupancy(steps_of(handle.read())), [])


def cell_step(num, card, occupancy="비움", title="가격 셀 손으로 고치기 (1번째, 2026-12-24)",
              save="저장", nights=None):
    """`가격 캘린더` 의 날짜 칸을 열어 고치는(또는 만드는) 단계.

    `nights` 를 주면 `박수~` 줄을 함께 적는다 — 비우면 그 칸의 초깃값 1(박수 무관)이다.
    """
    nights_row = f"| 박수~ | {nights} |\n" if nights is not None else ""
    return f"""
## {num}. {title}
탭: `가격 캘린더`
버튼: 달력의 `2026-12-24` 칸 클릭
카드: {card}

| 칸 | 값 |
|---|---|
| 인원 조합 | {occupancy} |
{nights_row}| 판매가 | 2173000 |
| 정가 | 비움 |
| 공급 원가 | 비움 |
| 상태 | 선택: 판매 가능 |

→ [{save}]
"""


#: 카드 줄 꼴 — 러너가 좌표를 읽는 곳이다.
CARD_KEYED = "`2026 시즌 요금 · Single` × `조식 포함` 의 인원 조합 `A2` 행"
CARD_SINGLE = "`2026 시즌 요금 · Single` × `조식 포함` 의 인원 무관 단일가 행"
CARD_EMPTY_ROW = "`2026 시즌 요금 · Single` × `조식 포함` 의 인원 조합 빈 행"
CARD_NO_CLAUSE = "`2026 시즌 요금 · Single` × `조식 포함` 행"
CARD_NEW_ROW = "`2026 시즌 요금 · Single` × `조식 포함` 의 `인원별 · 박수별 가격 추가`"


class CellStepOccupancyMismatchTest(unittest.TestCase):
    """가격 셀 단계는 `카드:` 줄과 `인원 조합` 칸이 같은 좌표를 불러야 한다(러너는 카드 줄을 읽는다)."""

    def problems(self, card, occupancy="비움", **kw):
        md = HEAD + cell_step(4, card, occupancy=occupancy, **kw)
        return cm.find_cell_step_occupancy_mismatch(steps_of(md))

    def test_both_sides_keyed_is_ok(self):
        self.assertEqual(self.problems(CARD_KEYED, "A2"), [])

    def test_both_sides_blank_is_ok(self):
        self.assertEqual(self.problems(CARD_SINGLE, "비움"), [])
        self.assertEqual(self.problems(CARD_EMPTY_ROW, "비움"), [])
        self.assertEqual(self.problems(CARD_NO_CLAUSE, "비움"), [])

    def test_card_without_clause_but_keyed_field_is_error(self):
        """좌표 절을 빼면 러너는 `인원 무관 단일가` 를 연다 — 칸에 `A2` 를 적어도 다른 행이다."""
        problems = self.problems(CARD_NO_CLAUSE, "A2")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("인원 무관 단일가 행", problems[0])
        self.assertIn("`A2` 다", problems[0])
        self.assertIn("카드 줄에서 좌표를 읽으므로", problems[0])

    def test_keyed_card_with_blank_field_is_error(self):
        problems = self.problems(CARD_KEYED, "비움")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("인원 조합 `A2` 행", problems[0])
        self.assertIn("비었다", problems[0])

    def test_different_keys_are_error(self):
        self.assertEqual(len(self.problems(CARD_KEYED, "A3")), 1)

    def test_select_item_label_is_read_by_its_key(self):
        """셀렉트 항목 글자는 `키 · 사람 수` 다 — 앞의 키로 견준다."""
        card = "`2026 시즌 요금 · Single` × `조식 포함` 의 인원 조합 `A2C1_CHD` 행"
        self.assertEqual(self.problems(card, "선택: A2C1_CHD · 성인 2 · 소아 1"), [])

    def test_new_row_card_is_skipped(self):
        """새 행 표는 카드에 좌표 절이 없는 것이 정본이다 — 좌표는 표 안의 셀렉트가 정한다."""
        self.assertEqual(self.problems(CARD_NEW_ROW, "선택: A2 · 성인 2",
                                       title="가격 셀 만들기 (1번째, 2026-12-24)", save="추가"), [])

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_cell_step_occupancy_mismatch(steps_of(handle.read())), [])


class CellStepCoordinateTest(unittest.TestCase):
    """가격 셀 단계의 좌표는 그 룸의 `시즌 가격 채우기` 가 실제로 깐 좌표여야 한다."""

    def manual(self, card, fill_keys="A2", occupancy="비움", extra_fill=None, **kw):
        rows = [("인원 조합(선택)", fill_keys)]
        md = (HEAD + offer_step(4)
              + season_step(5, "Regular", "2026 시즌 요금", RANGE)
              + price_fill_step(6, season="Regular", room="Single", rows=rows))
        if extra_fill is not None:
            md += price_fill_step(7, season="Regular", room="Single",
                                  rows=[("인원 조합(선택)", extra_fill)])
        return md + cell_step(8, card, occupancy=occupancy, **kw)

    def problems(self, *args, **kw):
        return cm.find_cell_step_without_filled_coordinate(steps_of(self.manual(*args, **kw)))

    def test_keyed_fill_with_keyed_cell_is_ok(self):
        self.assertEqual(self.problems(CARD_KEYED, fill_keys="A2", occupancy="A2"), [])

    def test_blank_fill_with_blank_cell_is_ok(self):
        """G-chicland 꼴 — 채우기도 비움, 셀 단계도 인원 무관 단일가 행이면 맞는 짝이다."""
        self.assertEqual(self.problems(CARD_SINGLE, fill_keys="비움", occupancy="비움"), [])

    def test_blank_cell_with_keyed_fill_is_error(self):
        problems = self.problems(CARD_SINGLE, fill_keys="A2", occupancy="비움")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("8단계", problems[0])
        self.assertIn("인원 무관 단일가 행", problems[0])
        self.assertIn("`A2` 로 깐다", problems[0])
        self.assertIn("그 행은 만들어지지 않는다", problems[0])

    def test_keyed_cell_with_blank_fill_is_error(self):
        problems = self.problems(CARD_KEYED, fill_keys="비움", occupancy="A2")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("인원 조합 `A2` 행", problems[0])
        self.assertIn("그 좌표는 깔리지 않는다", problems[0])

    def test_new_row_card_uses_its_select(self):
        """새 행 표는 카드에 좌표가 없다 — 셀렉트가 비면 아무도 팔지 않는 좌표가 하나 더 생긴다."""
        problems = self.problems(CARD_NEW_ROW, fill_keys="A2", occupancy="비움",
                                 title="가격 셀 만들기 (1번째, 2026-12-24)", save="추가")
        self.assertEqual(len(problems), 1, problems)

    def test_mixed_fills_are_skipped(self):
        """한 룸의 채우기가 섞여 있으면 근거가 모자라 말하지 않는다."""
        self.assertEqual(self.problems(CARD_SINGLE, fill_keys="A2", occupancy="비움",
                                       extra_fill="비움"), [])

    def test_another_rooms_fill_does_not_decide(self):
        md = (HEAD + offer_step(4)
              + season_step(5, "Regular", "2026 시즌 요금", RANGE)
              + price_fill_step(6, season="Regular", room="Twin",
                                rows=[("인원 조합(선택)", "A2")])
              + cell_step(7, CARD_SINGLE))
        self.assertEqual(cm.find_cell_step_without_filled_coordinate(steps_of(md)), [])

    def test_manual_without_fill_steps_is_skipped(self):
        md = HEAD + offer_step(4) + cell_step(5, CARD_SINGLE)
        self.assertEqual(cm.find_cell_step_without_filled_coordinate(steps_of(md)), [])

    def test_it_is_an_error_not_a_warning(self):
        md = self.manual(CARD_SINGLE, fill_keys="A2", occupancy="비움")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            r = cm.check(path)
            self.assertEqual(len(r["cell_coordinate_gaps"]), 1, r["cell_coordinate_gaps"])
            self.assertEqual(cm.main([path]), 1)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(
                cm.find_cell_step_without_filled_coordinate(steps_of(handle.read())), [])


class CellOccupancySelectTest(unittest.TestCase):
    """가격 셀 모달의 `인원 조합` 은 **셀렉트**다 — 정본 표기는 `선택: <옵션 글자 그대로>` 다.

    옵션 글자는 키가 앞이라(`A2C1_CHD · 성인 2 · 소아 1`) 좌표를 읽는 자리는 모두 같은 문
    (`_occupancy_key_of_value`)을 지난다. `시즌 가격 채우기` 의 `인원 조합(선택)` 은 텍스트라
    `A2,A3` 쉼표 목록 그대로이고 ` · ` 로 자르지 않는다.
    """

    def cell(self, occupancy, card=None):
        md = HEAD + cell_step(4, card or CARD_NEW_ROW, occupancy=occupancy,
                              title="가격 셀 만들기 (1번째, 2026-12-24)", save="추가")
        return cm.find_occupancy_key_legacy(steps_of(md))

    def test_the_gate_reads_the_key_from_the_option_text(self):
        self.assertEqual(cm._occupancy_key_of_value("선택: A2C1_CHD · 성인 2 · 소아 1"), "A2C1_CHD")
        self.assertEqual(cm._occupancy_key_of_value("선택:A2 · 성인 2"), "A2")
        self.assertEqual(cm._occupancy_key_of_value("선택: 인원 무관 단일가"), "")
        self.assertEqual(cm._occupancy_key_of_value("A2"), "A2")
        self.assertEqual(cm._occupancy_key_of_value("비움"), "")

    def test_canonical_select_text_passes(self):
        self.assertEqual(self.cell("선택: A2C1_CHD · 성인 2 · 소아 1"), [])
        self.assertEqual(self.cell("선택: A2 · 성인 2"), [])

    def test_single_price_option_is_a_blank_key(self):
        self.assertEqual(self.cell("선택: 인원 무관 단일가"), [])

    def test_bare_key_still_passes(self):
        """옛 원고가 키만 적어 둔 것도 받는다."""
        self.assertEqual(self.cell("A2"), [])

    def test_legacy_numeric_option_is_error(self):
        problems = self.cell("선택: 3 · 3인")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("옛 숫자 표기", problems[0])
        self.assertIn("선택: A2 · 성인 2", problems[0])

    def test_season_fill_text_is_not_split_by_the_middle_dot(self):
        fill = HEAD + price_fill_step(4, rows=[("인원 조합(선택)", "A2,A3")])
        self.assertEqual(cm.find_occupancy_key_legacy(steps_of(fill)), [])
        legacy = HEAD + price_fill_step(4, rows=[("인원 조합(선택)", "2,3")])
        self.assertEqual(len(cm.find_occupancy_key_legacy(steps_of(legacy))), 1)

    def test_the_same_gate_feeds_the_card_comparison(self):
        """카드 줄 좌표와 셀렉트 항목 글자를 같은 키로 견준다."""
        card = "`2026 시즌 요금 · Single` × `조식 포함` 의 인원 조합 `A2C1_CHD` 행"
        md = HEAD + cell_step(4, card, occupancy="선택: A2C1_CHD · 성인 2 · 소아 1")
        self.assertEqual(cm.find_cell_step_occupancy_mismatch(steps_of(md)), [])
        md = HEAD + cell_step(4, card, occupancy="선택: A2 · 성인 2")
        self.assertEqual(len(cm.find_cell_step_occupancy_mismatch(steps_of(md))), 1)

    def test_it_passes_the_whole_run(self):
        md = (HEAD + offer_step(4)
              + season_step(5, "Regular", "2026 시즌 요금", RANGE)
              + price_fill_step(6, season="Regular", room="Single",
                                rows=[("인원 조합(선택)", "A2")])
              + cell_step(7, "`2026 시즌 요금 · Single` × `조식 포함` 의 인원 조합 `A2` 행",
                          occupancy="선택: A2 · 성인 2"))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            r = cm.check(path)
        self.assertEqual(r["occupancy_key_legacy"], [])
        self.assertEqual(r["cell_occupancy_mismatch"], [])
        self.assertEqual(r["cell_coordinate_gaps"], [])


# ─────────────────────────────────────────────────────────────────────────────
# 2026-09-09 배포 규칙 — 좌표 파서(`services/occupancy_key`)·LOS 의미 변경·아동 금액 칸.
# ─────────────────────────────────────────────────────────────────────────────

class OccupancyKeyReaderTest(unittest.TestCase):
    """`read_occupancy_key` 는 ERP `parse_key` 와 같은 문이다 — 정규식 흉내는 어긋난다."""

    def kind(self, key):
        judged = cm.read_occupancy_key(key)
        return None if judged is None else judged[0]

    def test_canonical_keys_pass(self):
        for key in ("", "A2", "A10", "A2C1_CHD", "A2C1_CHD_C1_TEEN", "A2C2_CHD"):
            self.assertIsNone(self.kind(key), key)

    def test_bare_number_is_legacy(self):
        self.assertEqual(self.kind("3"), "legacy")

    def test_codeless_pair_is_its_own_kind(self):
        """`A2C1` 은 서버가 읽어 주지만 뜻이 오퍼에 달렸다 — 지시서에는 못 쓴다."""
        self.assertEqual(self.kind("A2C1"), "codeless")

    def test_mixed_key_is_unread(self):
        """코드 있는 조각과 없는 조각이 섞이면 서버도 거부한다(`parse_key`)."""
        for key in ("A2C1_C1_CHD", "A2C1_C1"):
            self.assertEqual(self.kind(key), "unread", key)

    def test_leading_underscore_is_unread(self):
        self.assertEqual(self.kind("A2_C1_CHD"), "unread")

    def test_bad_band_code_in_the_key_is_unread(self):
        for key in ("A2C1_C", "A2C1_CHILDBAND9", "A2C1_CHD_TEEN"):
            self.assertEqual(self.kind(key), "unread", key)

    def test_over_32_chars_is_long(self):
        """컬럼이 32자다 — 넘는 좌표의 셀은 만들어지지 않는다."""
        key = "A2C1_CHD_C1_TEEN_C1_JUNIOR_C1_YOUTH"  # 35자
        self.assertEqual(len(key), 35)
        self.assertEqual(self.kind(key), "long")

    def test_exactly_32_chars_is_not_long(self):
        key = "A2C1_CHD_C1_TEEN_C1_JUNIOR_C1_YT"  # 32자
        self.assertEqual(len(key), 32)
        self.assertIsNone(self.kind(key))


class OccupancyKeyShapeTest(unittest.TestCase):
    """칸·카드 줄의 좌표가 2026-09-09 규칙을 지키는지 — `find_occupancy_key_legacy`."""

    def fill(self, value):
        md = HEAD + price_fill_step(4, rows=[("인원 조합(선택)", value)])
        return cm.find_occupancy_key_legacy(steps_of(md))

    def test_codeless_pair_is_error(self):
        problems = self.fill("A2,A2C1")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("`A2C1`", problems[0])
        self.assertIn("구간 코드가 없다", problems[0])

    def test_coded_pair_is_ok(self):
        self.assertEqual(self.fill("A2,A2C1_CHD"), [])

    def test_mixed_key_is_error(self):
        problems = self.fill("A2C1_C1_CHD")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("읽지 못한다", problems[0])

    def test_over_32_chars_is_error(self):
        problems = self.fill("A2C1_CHD_C1_TEEN_C1_JUNIOR_C1_YOUTH")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("32자를 넘는다", problems[0])
        self.assertIn("셀은 만들어지지 않는다", problems[0])

    def test_one_line_per_field_even_with_several_bad_keys(self):
        """칸 하나를 키 수만큼 반복해 적지 않는다 — 고치는 자리는 그 칸 하나다."""
        self.assertEqual(len(self.fill("A2C1,A3C1")), 1)

    def test_space_separated_keys_are_read_like_the_server(self):
        """서버는 쉼표와 빈칸을 함께 가른다(`season._OCCUPANCY_SPLIT`) — 검사기도 같아야 한다."""
        self.assertEqual(self.fill("A2 A3"), [])
        self.assertEqual(len(self.fill("A2 A2C1")), 1)

    def test_the_card_line_is_checked_too(self):
        """러너는 카드 줄에서 좌표를 읽는다 — 칸만 보면 카드 줄의 `A2C1` 이 그대로 남는다."""
        card = "`2026 시즌 요금 · Single` × `조식 포함` 의 인원 조합 `A2C1` 행"
        md = HEAD + cell_step(4, card, occupancy="선택: A2C1 · 성인 2 · 아동 1(구간 미지정)")
        problems = cm.find_occupancy_key_legacy(steps_of(md))
        self.assertEqual(len(problems), 1, problems)  # 칸에서 이미 말했으므로 카드 줄은 겹치지 않는다
        self.assertIn("구간 코드가 없다", problems[0])

    def test_a_bad_card_line_alone_is_reported(self):
        card = "`2026 시즌 요금 · Single` × `조식 포함` 의 인원 조합 `A2C1` 행"
        md = HEAD + cell_step(4, card, occupancy="선택: A2 · 성인 2")
        problems = cm.find_occupancy_key_legacy(steps_of(md))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("카드 줄", problems[0])

    def test_a_good_card_line_is_ok(self):
        card = "`2026 시즌 요금 · Single` × `조식 포함` 의 인원 조합 `A2C1_CHD` 행"
        md = HEAD + cell_step(4, card, occupancy="선택: A2C1_CHD · 성인 2 · 소아 1")
        self.assertEqual(cm.find_occupancy_key_legacy(steps_of(md)), [])

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_occupancy_key_legacy(steps_of(handle.read())), [])


class OccupancyAdjustTest(unittest.TestCase):
    """`인원 조합별 조정(선택)` — 부호 필수 · 인원 조합 칸에 있는 키만 · 같은 키 한 번."""

    def problems(self, adjust, keys="A2,A3"):
        rows = [("인원 조합(선택)", keys), ("인원 조합별 조정(선택)", adjust)]
        md = HEAD + price_fill_step(4, rows=rows)
        return cm.find_occupancy_adjust_gaps(steps_of(md))

    def test_canonical_value_is_ok(self):
        self.assertEqual(self.problems("A3:+14"), [])
        self.assertEqual(self.problems("A3:-5%"), [])
        self.assertEqual(self.problems("A2:+10,A3:+14"), [])

    def test_blank_is_ok(self):
        self.assertEqual(self.problems("비움"), [])

    def test_missing_sign_is_error(self):
        problems = self.problems("A3:14")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("부호가 없다", problems[0])

    def test_key_outside_the_occupancy_field_is_error(self):
        problems = self.problems("A4:+26")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`A4`", problems[0])
        self.assertIn("아무 좌표에도 닿지 않는다", problems[0])

    def test_adjust_without_occupancy_keys_is_error(self):
        problems = self.problems("A3:+14", keys="비움")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("인원 조합이 비어 있다", problems[0])

    def test_duplicate_key_is_error(self):
        problems = self.problems("A3:+14,A3:+20")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("두 번", problems[0])

    def test_bare_numbers_are_compared_after_normalizing(self):
        """서버가 두 칸을 같은 문으로 정규화한다 — `2,3` + `3:+14` 는 맞물린다(A-형 강제는 다른 검사다)."""
        self.assertEqual(self.problems("3:+14", keys="2,3"), [])

    def test_unreadable_entry_is_error(self):
        self.assertEqual(len(self.problems("A3 plus 14")), 1)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_occupancy_adjust_gaps(steps_of(handle.read())), [])


class ChildExtraValueTest(unittest.TestCase):
    """`아동 추가 금액 — <노출명>` 줄의 값이 그 구간의 `요금 기준 유형` 과 맞아야 한다."""

    def problems(self, fill_rows, band_kind="정액"):
        md = child_price_manual(fill_rows=fill_rows, band_kind=band_kind)
        return cm.find_child_extra_value_gaps(steps_of(md))

    def test_amount_on_a_flat_band_is_ok(self):
        self.assertEqual(self.problems([("아동 추가 금액 — 소아", "23.18")]), [])

    def test_zero_is_a_value_not_a_blank(self):
        """`0` 은 「무료로 깐다」라 빈 칸과 뜻이 다르다."""
        self.assertEqual(self.problems([("아동 추가 금액 — 소아", "0")]), [])

    def test_blank_amount_on_a_paid_band_is_error(self):
        problems = self.problems([("아동 추가 금액 — 소아", "비움")])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("7단계", problems[0])
        self.assertIn("비어 있다", problems[0])
        self.assertIn("아동 조합 셀을 만들지 않는다", problems[0])

    def test_free_band_with_a_row_is_error(self):
        problems = self.problems([("아동 추가 금액 — 소아", "23.18")], band_kind="무료")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("무료", problems[0])
        self.assertIn("줄을 적지 않는다", problems[0])

    def test_free_band_without_a_row_is_ok(self):
        self.assertEqual(self.problems([("인원 조합(선택)", "A2")], band_kind="무료"), [])

    def test_percent_band_with_an_amount_is_error(self):
        problems = self.problems([("아동 추가 금액 — 소아", "23.18")], band_kind="성인 요금의 %")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("읽기 전용", problems[0])
        self.assertIn("자동 입력됨", problems[0])

    def test_percent_band_with_the_auto_text_is_ok(self):
        rows = [("아동 추가 금액 — 소아", "자동 입력됨 · 그대로 둠")]
        self.assertEqual(self.problems(rows, band_kind="성인 요금의 %"), [])

    def test_auto_text_on_a_flat_band_is_error(self):
        """반대 방향의 같은 사고 — 정액 구간의 칸은 담당자가 적는 숫자다."""
        rows = [("아동 추가 금액 — 소아", "자동 입력됨 · 그대로 둠")]
        problems = self.problems(rows)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("담당자가 적는 숫자", problems[0])

    def test_missing_row_is_left_to_the_other_check(self):
        """줄이 아예 없는 유료 구간은 `find_child_extra_missing` 이 말한다."""
        self.assertEqual(self.problems([("인원 조합(선택)", "A2")]), [])

    def test_it_is_an_error_not_a_warning(self):
        md = child_price_manual(fill_rows=[("아동 추가 금액 — 소아", "비움")])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            r = cm.check(path)
            self.assertEqual(len(r["child_extra_values"]), 1, r["child_extra_values"])
            self.assertEqual(cm.main([path]), 1)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_child_extra_value_gaps(steps_of(handle.read())), [])


class LosTierLimitTest(unittest.TestCase):
    """`박수별 단가` 의 상한 — 박수 30까지 · 층 6개까지(`season.MAX_LOS_NIGHTS`·`MAX_LOS_TIERS`)."""

    def problems(self, value):
        md = HEAD + price_fill_step(4, rows=[("박수별 단가(선택)", value)])
        return cm.find_los_prices_format(steps_of(md))

    def test_thirty_nights_is_ok(self):
        self.assertEqual(self.problems("30:80"), [])

    def test_over_thirty_nights_is_error(self):
        problems = self.problems("31:80")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("30박까지다", problems[0])

    def test_six_tiers_are_ok(self):
        self.assertEqual(self.problems("2:100,3:98,4:96,5:94,6:92,7:90"), [])

    def test_seven_tiers_are_error(self):
        problems = self.problems("2:100,3:98,4:96,5:94,6:92,7:90,8:88")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("층이 7개다", problems[0])


class LosWithoutBasePriceTest(unittest.TestCase):
    """`박수별 단가` 는 1박 층 **위에** 층을 더한다 — 1박 층이 없으면 어느 박수로도 안 팔린다."""

    def manual(self, price="92.00", los="3:100"):
        rows = [("판매 단가(공급 통화)", price), ("대상 룸", "선택: Single"),
                ("박수별 단가(선택)", los), ("이미 값이 있는 날도 덮기", "해제")]
        body = "".join(f"| {k} | {v} |\n" for k, v in rows)
        return HEAD + f"""
## 4. 시즌 가격 채우기 (1회차, Regular × Single)
탭: `시즌`
카드: `Regular`
버튼: [가격]

| 칸 | 값 |
|---|---|
{body}
→ [이 단가로 깔기]
"""

    def problems(self, **kw):
        return cm.find_los_without_base_price(steps_of(self.manual(**kw)))

    def test_price_and_los_together_are_ok(self):
        self.assertEqual(self.problems(), [])

    def test_blank_price_with_los_is_error(self):
        problems = self.problems(price="비움")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("1박 층", problems[0])

    def test_blank_price_without_los_is_not_this_check(self):
        self.assertEqual(self.problems(price="비움", los="비움"), [])

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_los_without_base_price(steps_of(handle.read())), [])


class CellLosNightsTest(unittest.TestCase):
    """가격 셀 모달의 `박수~` 는 1~30이다 — 1이 「박수 무관」이라 시즌 칸과 하한이 다르다."""

    def problems(self, nights):
        md = HEAD + cell_step(4, CARD_SINGLE, nights=nights)
        return cm.find_cell_los_nights(steps_of(md))

    def test_one_is_ok(self):
        """시즌의 `박수별 단가` 와 달리 여기는 1을 받는다 — 언제나 집히는 바닥 층이다."""
        self.assertEqual(self.problems("1"), [])

    def test_common_steps_are_ok(self):
        for nights in ("2", "3", "7", "30"):
            self.assertEqual(self.problems(nights), [], nights)

    def test_blank_is_ok(self):
        self.assertEqual(self.problems("비움"), [])

    def test_zero_is_error(self):
        problems = self.problems("0")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("1 이상", problems[0])

    def test_over_thirty_is_error(self):
        problems = self.problems("31")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("30 이하", problems[0])

    def test_prose_is_error(self):
        problems = self.problems("사흘")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("읽지 못한다", problems[0])

    def test_badge_form_is_an_error(self):
        """화면 배지를 따라 적은 `3박~` 는 **오류**다 — 러너가 그 칸에서 층 조건을 잃는다.

        종전에는 같은 숫자로 읽어 통과시켰다. 그 원고를 러너가 실행하면 부트가 비숫자라는
        이유로 `wantLos` 를 비우고 같은 인원 조합의 첫 층을 골라, 3박 층을 만들려던 단계가
        1박 행을 고치고 끝난다(2026-09-09 Codex 리뷰 9).
        """
        problems = self.problems("3박~")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("배지", problems[0])
        self.assertIn("`3`", problems[0])

    def test_other_badge_spellings_are_errors_too(self):
        for typed in ("3박", "3~", "3 박 ~"):
            problems = self.problems(typed)
            self.assertEqual(len(problems), 1, (typed, problems))
            self.assertIn("`3`", problems[0], typed)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_cell_los_nights(steps_of(handle.read())), [])


class PlanAdjustTest(unittest.TestCase):
    """`기준 요금제 대비 조정(선택)` — 부호 필수 · 요금제 필수 · 결과가 음수면 오류.

    종전 검사기는 이 칸을 아예 보지 않아 서버가 거부하는 원고를 `ALL OK` 로 내보냈다
    (2026-09-09 Codex 리뷰 6).
    """

    def problems(self, adjust, plans="선택: 조식 포함", **rows):
        fields = [("기준 요금제 대비 조정(선택)", adjust), ("요금제(선택)", plans)]
        fields += list(rows.items())
        md = HEAD + price_fill_step(4, rows=fields)
        return cm.find_plan_adjust_gaps(steps_of(md))

    def test_signed_adjust_with_a_plan_is_ok(self):
        self.assertEqual(self.problems("-8"), [])
        self.assertEqual(self.problems("-5%"), [])

    def test_blank_is_ok(self):
        self.assertEqual(self.problems("비움", plans="비움"), [])

    def test_missing_sign_is_an_error(self):
        problems = self.problems("8")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("부호가 없다", problems[0])

    def test_adjust_without_a_rate_plan_is_an_error(self):
        """조정은 기준이 아닌 요금제에만 걸린다 — 요금제를 비우면 아무 데도 닿지 않는다."""
        problems = self.problems("-8", plans="비움")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("요금제가 비어 있다", problems[0])

    def test_percent_below_minus_hundred_is_an_error(self):
        problems = self.problems("-101%")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("-100%", problems[0])

    def test_a_negative_result_is_an_error(self):
        """기준가 92.00 에 `-100` 을 걸면 판매 단가가 음수다 — 깔기 전에 막힌다."""
        problems = self.problems("-100")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("음수", problems[0])

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_plan_adjust_gaps(steps_of(handle.read())), [])


class OccupancyAdjustAmountTest(unittest.TestCase):
    """`인원 조합별 조정(선택)` 의 **크기** — 정률 -100% 이상 · 결과 0 이상."""

    def problems(self, adjust, keys="A1,A2", price="92.00"):
        rows = [("인원 조합(선택)", keys), ("인원 조합별 조정(선택)", adjust)]
        md = HEAD + price_fill_step(4, rows=rows).replace(
            "| 판매 단가(공급 통화) | 92.00 |", f"| 판매 단가(공급 통화) | {price} |")
        return cm.find_occupancy_adjust_gaps(steps_of(md))

    def test_ordinary_adjust_is_ok(self):
        self.assertEqual(self.problems("A2:+14"), [])

    def test_percent_below_minus_hundred_is_an_error(self):
        problems = self.problems("A1:-101%")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("-100%", problems[0])

    def test_minus_hundred_percent_is_still_ok(self):
        """`-100%` 는 값이 0이라 하한 그 자체다 — 하한을 넘지 않았으므로 통과다."""
        self.assertEqual(self.problems("A1:-100%"), [])

    def test_a_flat_adjust_below_the_base_price_is_an_error(self):
        """기준가 8500에 `A1:-9000` — 결과가 -500이라 화면이 깔기 전에 막는다."""
        problems = self.problems("A1:-9000", price="8500")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("음수", problems[0])
        self.assertIn("-500", problems[0])


class OccupancyKeyNormalizationTest(unittest.TestCase):
    """좌표 존재·중복은 **서버와 같은 정규화 뒤에** 판정한다(`normalize_key`)."""

    def test_normalization_matches_the_server(self):
        for raw, want in (
            ("A02", "A2"),
            ("3", "A3"),
            ("A2C1_TEEN_C1_CHD", "A2C1_CHD_C1_TEEN"),
            ("A2C1_CHD_C1_CHD", "A2C2_CHD"),
            ("a2c1_chd", "A2C1_CHD"),
            ("", ""),
        ):
            self.assertEqual(cm.normalize_occupancy_key(raw), want, raw)

    def test_unreadable_and_codeless_keys_are_left_alone(self):
        """읽지 못하는 값과 코드 없는 `A2C1` 은 그대로 둔다 — 지어내면 다른 구간을 덮는다."""
        for raw in ("A2C1", "A2C1_C1_CHD", "2A+1유아"):
            self.assertEqual(cm.normalize_occupancy_key(raw), raw.upper(), raw)

    def test_a_zero_padded_key_matches_the_adjust_key(self):
        """`인원 조합=A02` 에 `조정=A2:+10` 은 서버에서 맞물린다 — 없는 키가 아니다."""
        rows = [("인원 조합(선택)", "A02"), ("인원 조합별 조정(선택)", "A2:+10")]
        md = HEAD + price_fill_step(4, rows=rows)
        self.assertEqual(cm.find_occupancy_adjust_gaps(steps_of(md)), [])

    def test_two_spellings_of_one_key_are_a_duplicate(self):
        """`A02,A2` 는 서버가 한 좌표로 접는다 — 두 인원의 셀을 깐다고 믿으면 안 된다."""
        md = HEAD + price_fill_step(4, rows=[("인원 조합(선택)", "A02,A2")])
        problems = cm.find_occupancy_key_duplicates(steps_of(md))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`A02`", problems[0])
        self.assertIn("같은 좌표", problems[0])

    def test_a_select_field_is_not_split_on_spaces(self):
        """가격 셀의 `인원 조합` 은 셀렉트다 — `선택: A2 · 성인 2` 의 끝 `2` 는 좌표가 아니다."""
        md = HEAD + cell_step(4, CARD_KEYED, occupancy="선택: A2 · 성인 2")
        self.assertEqual(cm.find_occupancy_key_duplicates(steps_of(md)), [])

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_occupancy_key_duplicates(steps_of(handle.read())), [])


class OccupancyKeyNormalFormTest(unittest.TestCase):
    """원고는 서버 정규형으로만 적는다 — 저장되는 글자가 달라지면 러너가 없는 행을 찾는다."""

    def fill(self, keys="A2", adjust=None):
        rows = [("인원 조합(선택)", keys)]
        if adjust:
            rows.append(("인원 조합별 조정(선택)", adjust))
        md = HEAD + price_fill_step(4, rows=rows)
        return cm.find_occupancy_key_denormalized(steps_of(md))

    def test_a_normal_form_key_is_ok(self):
        for key in ("A2", "A2C1_CHD", "A2C1_CHD_C1_TEEN", "A2C2_CHD"):
            self.assertEqual(self.fill(key), [], key)

    def test_band_order_is_an_error_with_the_normal_form(self):
        """`A2C1_TEEN_C1_CHD` 는 서버가 코드 알파벳순으로 다시 세워 저장한다."""
        problems = self.fill("A2C1_TEEN_C1_CHD")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`A2C1_TEEN_C1_CHD` → `A2C1_CHD_C1_TEEN`", problems[0])

    def test_repeated_band_parts_are_merged(self):
        problems = self.fill("A2C1_CHD_C1_CHD")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`A2C2_CHD`", problems[0])

    def test_a_zero_padded_adult_count_is_an_error(self):
        problems = self.fill("A02")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`A02` → `A2`", problems[0])

    def test_the_adjust_field_is_checked_too(self):
        problems = self.fill(keys="A2,A2C1_CHD_C1_TEEN", adjust="A2C1_TEEN_C1_CHD:+10")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("인원 조합별 조정", problems[0])

    def test_the_card_line_is_checked_too(self):
        """러너가 좌표를 실제로 읽는 자리는 카드 줄이다."""
        card = "`2026 시즌 요금 · Single` × `조식 포함` 의 인원 조합 `A2C1_TEEN_C1_CHD` 행"
        md = HEAD + cell_step(4, card, occupancy="선택: A2C1_CHD_C1_TEEN · 성인 2 · 소아 1 · 청소년 1")
        problems = cm.find_occupancy_key_denormalized(steps_of(md))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("카드 줄", problems[0])

    def test_a_broken_key_is_left_to_the_shape_check(self):
        """모양이 어긋난 좌표는 `find_occupancy_key_legacy` 의 몫이다 — 두 줄로 말하지 않는다."""
        for key in ("A2C1", "A2C1_C1_CHD", "3"):
            self.assertEqual(self.fill(key), [], key)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_occupancy_key_denormalized(steps_of(handle.read())), [])


class BlankBandCodeTest(unittest.TestCase):
    """`밴드 코드` 는 서버 필수다 — `비움` 은 화면이 「필수 항목입니다.」로 막는다."""

    def problems(self, code):
        md = HEAD + offer_step(4) + paid_band_step(5, code=code)
        return cm.find_band_code_format(steps_of(md))

    def test_a_code_is_ok(self):
        self.assertEqual(self.problems("CHD"), [])

    def test_a_blank_code_is_an_error(self):
        problems = self.problems("비움")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("5단계", problems[0])
        self.assertIn("필수 항목입니다.", problems[0])

    def test_a_dash_is_also_blank(self):
        self.assertEqual(len(self.problems("—")), 1)


class AmountFormatTest(unittest.TestCase):
    """금액 칸의 서버 `DecimalField` 규칙과 정가 관계 — 화면 거부를 원고에서 먼저 잡는다."""

    def fill(self, **rows):
        md = HEAD + price_fill_step(4, rows=list(rows.items()))
        return cm.find_amount_format_gaps(steps_of(md))

    def cell(self, body):
        return cm.find_amount_format_gaps(steps_of(HEAD + body))

    def test_ordinary_amounts_are_ok(self):
        self.assertEqual(self.fill(**{"정가(취소선, 선택)": "120.00",
                                      "공급 원가(net, 선택)": "60"}), [])

    def test_a_negative_price_is_an_error(self):
        md = HEAD + price_fill_step(4).replace(
            "| 판매 단가(공급 통화) | 92.00 |", "| 판매 단가(공급 통화) | -1 |")
        problems = cm.find_amount_format_gaps(steps_of(md))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("0보다 작을 수 없다", problems[0])

    def test_a_non_numeric_child_amount_is_an_error(self):
        problems = self.fill(**{"아동 추가 금액 — 소아": "abc"})
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("숫자만 받는다", problems[0])

    def test_three_decimal_places_are_an_error(self):
        problems = self.fill(**{"아동 추가 금액 — 소아": "1.234"})
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("소수 자릿수가 3자리", problems[0])

    def test_too_many_digits_are_an_error(self):
        """12자리 상한 · 소수 2자리 — 소수점 앞은 10자리까지다."""
        problems = self.fill(**{"공급 원가(net, 선택)": "12345678901"})
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("소수점 앞", problems[0])

    def test_an_original_price_below_the_sale_price_is_an_error(self):
        problems = self.fill(**{"정가(취소선, 선택)": "80"})
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("정가는 판매가보다 작을 수 없습니다", problems[0])

    def test_a_los_tier_above_the_original_price_is_an_error(self):
        problems = self.fill(**{"정가(취소선, 선택)": "120", "박수별 단가(선택)": "3:200"})
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("정가보다 비싼 박수 단가가 있습니다", problems[0])

    def test_the_cell_net_amount_allows_fourteen_digits(self):
        """가격 셀의 `공급 원가` 만 14자리다 — 같은 뜻의 칸이라도 화면이 다르면 상한이 다르다."""
        body = cell_step(4, CARD_SINGLE).replace(
            "| 공급 원가 | 비움 |", "| 공급 원가 | 123456789012 |")
        self.assertEqual(self.cell(body), [])

    def test_an_auto_filled_child_row_is_not_an_amount(self):
        """`자동 입력됨 · 그대로 둠` 은 값이 아니라 상태다 — 다른 검사가 옳고 그름을 말한다."""
        self.assertEqual(self.fill(**{"아동 추가 금액 — 소아": "자동 입력됨 · 그대로 둠"}), [])

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_amount_format_gaps(steps_of(handle.read())), [])


class SpecWordingTest(unittest.TestCase):
    """검사기 오류 문구가 규칙서 §의 말과 같은지 — 두 글이 다른 낱말을 쓰면 같은 규칙으로 안 읽힌다.

    화면이 실제로 뱉는 문구(「인원 조합 키가 너무 깁니다(32자까지)」)와 규칙서가 고른 표현
    (「코드가 없는 형식은 정확히 `A<성인수>C<아동수>` 한 가지」·「그 조합이 통째로 마감으로
    보인다」·「그 나이의 아이는 성인으로 계산된다」)을 문구에 박아 둔다. 규칙서가 말을 바꾸면
    이 시험이 먼저 깨져서 두 곳을 함께 고치게 된다.
    """

    def fill(self, value):
        md = HEAD + price_fill_step(4, rows=[("인원 조합(선택)", value)])
        return cm.find_occupancy_key_legacy(steps_of(md))[0]

    def test_long_key_quotes_the_screen_message(self):
        message = self.fill("A2C1_CHD_C1_TEEN_C1_JUNIOR_C1_YOUTH")
        self.assertIn("인원 조합 키가 너무 깁니다(32자까지)", message)
        self.assertIn("구간 코드를 짧게 하거나 조합을 줄인다", message)

    def test_codeless_key_says_the_manual_always_writes_the_code(self):
        message = self.fill("A2C1")
        self.assertIn("원고는 언제나 구간 코드가 붙은 키", message)
        self.assertIn("TEEN 값이 CHD 로 팔릴 수 있다", message)

    def test_mixed_key_says_the_one_codeless_shape(self):
        self.assertIn("코드가 없는 형식은 정확히 `A<성인수>C<아동수>` 한 가지다",
                      self.fill("A2C1_C1_CHD"))

    def test_leading_underscore_quotes_the_spelling_rule(self):
        self.assertIn("`A2C1_CHD`, `A2_C1_CHD` 아님", self.fill("A2_C1_CHD"))

    def test_unreadable_band_code_says_the_child_is_counted_as_an_adult(self):
        md = HEAD + offer_step(4) + paid_band_step(5, code="CHILD_UNDER12")
        self.assertIn("그 나이의 아이는 성인으로 계산된다",
                      cm.find_band_code_format(steps_of(md))[0])

    def test_missing_child_amount_says_the_pair_looks_closed(self):
        blank = child_price_manual(fill_rows=[("아동 추가 금액 — 소아", "비움")])
        self.assertIn("그 조합이 통째로 마감으로 보인다",
                      cm.find_child_extra_value_gaps(steps_of(blank))[0])
        missing = child_price_manual(fill_rows=[("인원 조합(선택)", "A2")])
        self.assertIn("그 조합이 통째로 마감으로 보인다",
                      cm.find_child_extra_missing(steps_of(missing))[0])


class ChildExtraPerFillTest(unittest.TestCase):
    """아동 금액 줄은 그 오퍼의 채우기 **회차마다** 있어야 한다 — 빠진 회차의 날짜만 마감으로 팔린다."""

    def manual(self, first_rows, second_rows):
        return (HEAD + offer_step(4)
                + paid_band_step(5)
                + season_step(6, "Regular", "2026 시즌 요금", RANGE)
                + price_fill_step(7, season="Regular", rows=first_rows)
                + season_step(8, "Peak", "2026 시즌 요금", OUTSIDE)
                + price_fill_step(9, season="Peak", rows=second_rows))

    def problems(self, first_rows, second_rows):
        return cm.find_child_extra_missing(steps_of(self.manual(first_rows, second_rows)))

    def test_every_fill_has_the_row_is_ok(self):
        rows = [("아동 추가 금액 — 소아", "23.18")]
        self.assertEqual(self.problems(rows, rows), [])

    def test_one_fill_without_the_row_is_error(self):
        """종전에는 어느 회차엔가 있으면 통과였다 — 시즌 하나가 통째로 빠진 원고가 지나갔다."""
        problems = self.problems([("아동 추가 금액 — 소아", "23.18")],
                                 [("인원 조합(선택)", "A2")])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("5단계", problems[0])
        self.assertIn("9단계", problems[0])
        self.assertIn("그 칸 한 곳에만", problems[0])

    def test_a_fill_of_another_offer_is_not_counted(self):
        """구간은 오퍼의 자식이다 — 다른 오퍼의 회차는 이 구간의 줄을 요구하지 않는다."""
        md = (HEAD + offer_step(4)
              + paid_band_step(5, card="`2026 시즌 요금`")
              + season_step(6, "Regular", "2026 시즌 요금", RANGE)
              + price_fill_step(7, season="Regular", rows=[("아동 추가 금액 — 소아", "23.18")])
              + season_step(8, "Peak", "2027 시즌 요금", OUTSIDE)
              + price_fill_step(9, season="Peak", rows=[("인원 조합(선택)", "A2")]))
        self.assertEqual(cm.find_child_extra_missing(steps_of(md)), [])

    def test_a_fill_whose_offer_is_unreadable_is_skipped(self):
        """오퍼를 못 읽은 회차는 이 구간의 것인지 알 수 없어 묻지 않는다(경고가 따로 나간다)."""
        md = (HEAD + offer_step(4)
              + paid_band_step(5)
              + season_step(6, "Regular", "2026 시즌 요금", RANGE)
              + price_fill_step(7, season="Regular", rows=[("아동 추가 금액 — 소아", "23.18")])
              + price_fill_step(9, season="2026 시즌 요금", rows=[("인원 조합(선택)", "A2")]))
        self.assertEqual(cm.find_child_extra_missing(steps_of(md)), [])

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_child_extra_missing(steps_of(handle.read())), [])


class UnmatchedFillStepTest(unittest.TestCase):
    """`시즌 가격 채우기` 의 `카드:` 는 그 회차가 여는 **시즌 이름**이다 — 오퍼 이름이면 경고."""

    def manual(self, card):
        return (HEAD + offer_step(4)
                + season_step(5, "Regular", "2026 시즌 요금", RANGE)
                + price_fill_step(6, season=card))

    def problems(self, card):
        return cm.find_unmatched_fill_steps(steps_of(self.manual(card)))

    def test_season_name_on_the_card_is_ok(self):
        self.assertEqual(self.problems("Regular"), [])

    def test_offer_name_on_the_card_is_a_warning(self):
        """실측 사례(E-empyrean) — 카드에 오퍼 이름을 적어 16회차가 통째로 검사에서 빠졌다."""
        problems = self.problems("2026 시즌 요금")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("6단계", problems[0])
        self.assertIn("시즌 이름", problems[0])

    def test_it_is_a_warning_not_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.manual("2026 시즌 요금"))
            r = cm.check(path)
            self.assertEqual(len(r["unmatched_fills"]), 1, r["unmatched_fills"])
            self.assertEqual(cm.main([path]), 0)

    def test_many_steps_are_folded(self):
        md = (HEAD + offer_step(4) + season_step(5, "Regular", "2026 시즌 요금", RANGE)
              + "".join(price_fill_step(6 + i, season="2026 시즌 요금") for i in range(8)))
        problems = cm.find_unmatched_fill_steps(steps_of(md))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("8회차", problems[0])

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_unmatched_fill_steps(steps_of(handle.read())), [])


#: 러너의 단계 갈래 목록 — 검사기가 통과시킨 제목을 러너가 모르면 그 단계에서 멈춘다.
RUNNER_PARSE_GUIDE = os.path.normpath(
    os.path.join(SKILL, os.pardir, "stay-setup-run", "scripts", "parse_guide.py")
)


def runner_known_kinds():
    """러너 `parse_guide.py` 의 `KNOWN_KINDS` 를 **읽어서**(실행하지 않고) 가져온다.

    import 하지 않는 이유는 그 스크립트가 러너 실행을 전제로 쓰였기 때문이다 — 목록 하나를
    보려고 남의 스킬 모듈을 돌리지 않는다. `ast` 로 대입문만 찾아 값을 읽는다.
    """
    import ast
    with open(RUNNER_PARSE_GUIDE, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            getattr(target, "id", "") == "KNOWN_KINDS" for target in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise AssertionError("러너 parse_guide.py 에서 KNOWN_KINDS 를 찾지 못했다")


def spec_table_kinds():
    """규칙서 §단계 갈래별 마지막 줄 표의 백틱 갈래 — 두 열을 모두 읽는다.

    `가격 셀 손으로 고치기`·`요금제 배포`·`택1 그룹 만들기` 는 둘째 열(예외 설명)에만 있어서
    첫 열만 읽으면 정본이 셋 빠진다.
    """
    with open(os.path.join(SKILL, "references", "MANUAL-SPEC.md"), encoding="utf-8") as handle:
        spec = handle.read()
    block = spec.split("### 단계 갈래별 마지막 줄", 1)[1].split("\n## ", 1)[0]
    kinds = set()
    for line in block.splitlines():
        if not line.startswith("|") or line.startswith("|---") or "단계 갈래" in line:
            continue
        for cell in line.strip("|").split("|"):
            for m in re.finditer(r"`([^`]+)`", cell):
                token = m.group(1).strip()
                if token.startswith("→") or token.startswith("["):
                    continue  # `→ [추가]` 는 마지막 줄이지 갈래가 아니다
                kinds.add(token)
    return kinds


def kind_step(num, title, save="저장"):
    """갈래만 갈아 끼우는 단계 하나."""
    return f"""
## {num}. {title}
탭: `프로모션`
카드: `전 오퍼 공통`
버튼: [추가]

| 칸 | 값 |
|---|---|
| 이름 | 얼리버드 |

→ [{save}]
"""


class StepKindTest(unittest.TestCase):
    """단계 제목의 갈래는 규칙서 표의 정본(또는 러너가 받는 별칭)이어야 한다."""

    def problems(self, title):
        return cm.find_unknown_step_kinds(steps_of(HEAD + kind_step(4, title)))

    def test_canonical_kind_is_ok(self):
        self.assertEqual(self.problems("프로모션 추가 (1개, 얼리버드)"), [])

    def test_unknown_kind_is_error(self):
        """실측(E-empyrean 51단계) — 화면도 버튼도 맞는데 갈래 글자가 달라 러너가 멈췄다."""
        problems = self.problems("프로모션 만들기 (1개, 얼리버드)")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("4단계", problems[0])
        self.assertIn("`프로모션 만들기`", problems[0])
        self.assertIn("`프로모션 추가`", problems[0])

    def test_the_nearest_canonical_is_suggested(self):
        """실측(D-amiana·F-grandvrio 6단계) — `택1 그룹에 혜택 추가` 는 `그룹에 혜택 추가` 다."""
        problems = self.problems("택1 그룹에 혜택 추가 (1번째, 조식)")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`그룹에 혜택 추가`", problems[0])

    def test_runner_aliases_pass(self):
        """러너가 받는 표기는 실행이 되므로 막지 않는다 — 정본으로 옮기는 것은 원고의 몫이다."""
        for title in ("택1 그룹 후보 추가 (1번째, 조식)", "택1 후보 혜택 추가 (1번째, 조식)"):
            self.assertEqual(self.problems(title), [], title)

    def test_nested_parentheses_are_stripped_like_the_runner(self):
        self.assertEqual(cm.step_kind("가격 셀 손으로 고치기 (1번째, 2026-12-24 (성수기))"),
                         "가격 셀 손으로 고치기")
        self.assertEqual(cm.step_kind("판매 시작"), "판매 시작")

    def test_forbidden_kinds_are_left_to_their_own_checks(self):
        """`오퍼 고치기`·`경고 넘어가기` 는 갈래를 몰라서가 아니라 쓰면 안 되는 단계다."""
        for title in ("오퍼 고치기 (1번째, 기본 오퍼)", "경고 넘어가기 (1번째)"):
            self.assertEqual(self.problems(title), [], title)

    def test_it_is_an_error_not_a_warning(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manual.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(HEAD + kind_step(4, "프로모션 만들기 (1개, 얼리버드)"))
            r = cm.check(path)
            self.assertEqual(len(r["unknown_step_kinds"]), 1, r["unknown_step_kinds"])
            self.assertEqual(cm.main([path]), 1)

    def test_the_example_manual_is_clean(self):
        with open(EXAMPLE, encoding="utf-8") as handle:
            self.assertEqual(cm.find_unknown_step_kinds(steps_of(handle.read())), [])


class StepKindListsAgreeTest(unittest.TestCase):
    """갈래 목록은 세 곳에 있다 — 규칙서 표 · 검사기 · 러너. 셋이 어긋나면 여기서 깨진다."""

    def test_the_checker_matches_the_spec_table(self):
        self.assertEqual(set(cm.STEP_KINDS), spec_table_kinds())

    def test_the_checker_matches_the_runner(self):
        """검사기가 받는 갈래 전부(정본 + 별칭)가 러너 `KNOWN_KINDS` 와 같아야 한다."""
        self.assertEqual(set(cm.KNOWN_STEP_KINDS), runner_known_kinds())

    def test_the_aliases_are_not_in_the_spec_table(self):
        """별칭은 정본이 아니다 — 표에 들어가면 그것은 별칭이 아니라 정본이다."""
        self.assertEqual(set(cm.STEP_KIND_ALIASES) & spec_table_kinds(), set())

    def test_the_zero_steps_are_canonical_kinds(self):
        for want in ("환율 확인", "거래처 확인", "도시 확인"):
            self.assertIn(want, cm.STEP_KINDS)
