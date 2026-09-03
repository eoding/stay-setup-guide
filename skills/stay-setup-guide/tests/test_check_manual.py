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


def gaps(md):
    """(오류 목록, 경고 목록)."""
    return cm.find_overwrite_gaps(steps_of(md))


def errors(md):
    return gaps(md)[0]


def warns(md):
    return gaps(md)[1]


class SeasonOverwriteTest(unittest.TestCase):
    """먼저 깐 시즌들이 덮은 날짜 위에 `덮기` 해제로 다시 까는 단계를 잡는다."""

    def wide_then_narrow(self, overwrite="해제", narrow=INSIDE):
        """넓은 시즌을 먼저 깔고 좁은 시즌을 나중에 까는 지시서."""
        return HEAD + season_step(4, "Regular", "오퍼A", RANGE) \
            + season_step(5, "Peak", "오퍼A", narrow) \
            + fill_step(6, "Regular", "싱글") + fill_step(7, "Peak", "싱글", overwrite=overwrite)

    def test_inside_without_overwrite_is_error(self):
        problems = errors(self.wide_then_narrow())
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("Peak", problems[0])
        self.assertIn("Regular", problems[0])

    def test_inside_with_overwrite_is_ok(self):
        self.assertEqual(gaps(self.wide_then_narrow(overwrite="체크")), ([], []))

    def test_not_overlapping_is_ok(self):
        self.assertEqual(gaps(self.wide_then_narrow(narrow=OUTSIDE)), ([], []))

    def test_wide_season_filled_first_is_not_flagged(self):
        """넓은 시즌이 먼저면 그 단계에는 앞서 깐 것이 없다 — 오류도 경고도 아니다."""
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE) + season_step(5, "Peak", "오퍼A", INSIDE) \
            + fill_step(6, "Regular", "싱글")
        self.assertEqual(gaps(md), ([], []))

    def test_narrow_filled_first_is_not_flagged(self):
        """좁은 시즌을 먼저 깔았으면 넓은 시즌 채우기는 그 셀을 건드리지 않는다 — 경고만."""
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE) + season_step(5, "Peak", "오퍼A", INSIDE) \
            + fill_step(6, "Peak", "싱글") + fill_step(7, "Regular", "싱글")
        problems, alerts = gaps(md)
        self.assertEqual(problems, [])
        self.assertEqual(len(alerts), 1, alerts)

    def test_union_of_two_wide_seasons_is_error(self):
        """한 시즌이 아니라 여러 시즌의 합집합이 덮는 경우(실제 결함 모양)."""
        md = HEAD + season_step(4, "앞반기", "오퍼A", FIRST_HALF) \
            + season_step(5, "뒷반기", "오퍼A", SECOND_HALF) \
            + listed_season(6, "Peak", "오퍼A", ["2026-01-01", "2026-06-30 ~ 2026-07-01", "2026-12-31"]) \
            + fill_step(7, "앞반기", "싱글") + fill_step(8, "뒷반기", "싱글") \
            + fill_step(9, "Peak", "싱글")
        problems, alerts = gaps(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("Peak", problems[0])
        self.assertIn("앞반기", problems[0])
        self.assertIn("뒷반기", problems[0])
        self.assertEqual(alerts, [])

    def test_union_with_overwrite_is_ok(self):
        md = HEAD + season_step(4, "앞반기", "오퍼A", FIRST_HALF) \
            + season_step(5, "뒷반기", "오퍼A", SECOND_HALF) \
            + listed_season(6, "Peak", "오퍼A", ["2026-01-01", "2026-12-31"]) \
            + fill_step(7, "앞반기", "싱글") + fill_step(8, "뒷반기", "싱글") \
            + fill_step(9, "Peak", "싱글", overwrite="체크")
        self.assertEqual(gaps(md), ([], []))

    def test_partial_coverage_is_warning(self):
        """일부 날짜만 앞 시즌과 겹치면 경고(막지는 않는다)."""
        md = HEAD + season_step(4, "앞반기", "오퍼A", FIRST_HALF) \
            + listed_season(5, "Peak", "오퍼A", ["2026-06-30", "2026-12-31"]) \
            + fill_step(6, "앞반기", "싱글") + fill_step(7, "Peak", "싱글")
        problems, alerts = gaps(md)
        self.assertEqual(problems, [])
        self.assertEqual(len(alerts), 1, alerts)
        self.assertIn("Peak", alerts[0])
        self.assertIn("앞반기", alerts[0])

    def test_other_room_is_not_compared(self):
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE) + season_step(5, "Peak", "오퍼A", INSIDE) \
            + fill_step(6, "Regular", "싱글", target="오퍼A · 싱글") \
            + fill_step(7, "Peak", "트윈", target="오퍼A · 트윈")
        self.assertEqual(gaps(md), ([], []))

    def test_same_room_is_compared(self):
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE) + season_step(5, "Peak", "오퍼A", INSIDE) \
            + fill_step(6, "Regular", "싱글", target="오퍼A · 싱글") \
            + fill_step(7, "Peak", "싱글", target="오퍼A · 싱글")
        self.assertEqual(len(errors(md)), 1)

    def test_other_offer_is_not_compared(self):
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE) + season_step(5, "Peak", "오퍼B", INSIDE) \
            + fill_step(6, "Regular", "싱글") + fill_step(7, "Peak", "싱글")
        self.assertEqual(gaps(md), ([], []))

    def test_listed_wide_season_excluding_the_days_is_ok(self):
        wide = [("날짜 규칙 유형", "선택: 비연속 날짜 나열"),
                ("날짜 나열", "2026-01-01 ~ 2026-06-30 / 2026-08-01 ~ 2026-12-31")]
        md = HEAD + season_step(4, "Regular", "오퍼A", wide) + season_step(5, "Peak", "오퍼A", INSIDE) \
            + fill_step(6, "Regular", "싱글") + fill_step(7, "Peak", "싱글")
        self.assertEqual(gaps(md), ([], []))

    def test_listed_wide_season_containing_the_days_is_error(self):
        wide = [("날짜 규칙 유형", "선택: 비연속 날짜 나열"), ("날짜 나열", "2026-01-01 ~ 2026-12-31")]
        md = HEAD + season_step(4, "Regular", "오퍼A", wide) + season_step(5, "Peak", "오퍼A", INSIDE) \
            + fill_step(6, "Regular", "싱글") + fill_step(7, "Peak", "싱글")
        self.assertEqual(len(errors(md)), 1)

    def test_month_list_season_is_compared(self):
        wide = [("날짜 규칙 유형", "선택: 월 목록"), ("기간 시작", "2026-01-01"),
                ("기간 종료", "2026-12-31"), ("적용 월", "선택: 7월, 8월")]
        md = HEAD + season_step(4, "Summer", "오퍼A", wide) + season_step(5, "Peak", "오퍼A", INSIDE) \
            + fill_step(6, "Summer", "싱글") + fill_step(7, "Peak", "싱글")
        problems = errors(md)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("Summer", problems[0])

    def test_weekday_rule_is_skipped(self):
        wide = [("날짜 규칙 유형", "선택: 요일 규칙"), ("기간 시작", "2026-01-01"),
                ("기간 종료", "2026-12-31"), ("적용 요일", "선택: 토, 일")]
        md = HEAD + season_step(4, "주말", "오퍼A", wide) + season_step(5, "Peak", "오퍼A", INSIDE) \
            + fill_step(6, "주말", "싱글") + fill_step(7, "Peak", "싱글")
        self.assertEqual(gaps(md), ([], []))

    def test_same_season_name_twice_is_skipped(self):
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE) + season_step(5, "Peak", "오퍼A", INSIDE) \
            + season_step(6, "Peak", "오퍼B", INSIDE) \
            + fill_step(7, "Regular", "싱글") + fill_step(8, "Peak", "싱글")
        self.assertEqual(gaps(md), ([], []))

    def test_fenced_date_list_is_read(self):
        md = HEAD + listed_season(4, "Peak", "오퍼A", ["2026-01-01", "2026-04-30 ~ 2026-05-01"])
        step = steps_of(md)[-1]
        self.assertEqual(len(cm.season_dates(step)), 3)


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
        self.assertEqual(len(r["overwrite_gaps"]), 1)

    def test_good_manual_passes(self):
        md = HEAD + season_step(4, "Regular", "오퍼A", RANGE) + season_step(5, "Peak", "오퍼A", INSIDE) \
            + fill_step(6, "Regular", "싱글") + fill_step(7, "Peak", "싱글", overwrite="체크")
        r, code = self.run_on(md)
        self.assertEqual(code, 0, r)
        self.assertEqual(r["overwrite_gaps"] + r["season_saves"], [])

    def test_example_manual_is_all_ok(self):
        """정답지 예시는 새 검사까지 통과해야 한다(사진 폴더는 저장소에 없어 뺀다)."""
        r = cm.check(EXAMPLE, share_name="우에노_토우가네야", dictionary_path=DICTIONARY)
        self.assertEqual(r["overwrite_gaps"], [])
        self.assertEqual(r["overwrite_overlaps"], [])
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
