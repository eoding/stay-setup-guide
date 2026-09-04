#!/usr/bin/env python3
"""check_manual.py 검사 규칙 시험.

실행:
    python3 -m unittest discover -s skills/stay-setup-guide/tests -v
    (또는 pytest skills/stay-setup-guide/tests)
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.normpath(os.path.join(HERE, os.pardir))
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import check_manual as cm  # noqa: E402

EXAMPLE = os.path.join(SKILL, "examples", "우에노_토우가네야", "manual.md")
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


def charge_with_age_rate(num, band="초등학생"):
    return f"""
## {num}. 부과금 만들기 (1개, 갈라 디너)
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
