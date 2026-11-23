"""H1 — 이름 · 설명에 적힌 바꾸기 전 값(change_core.names). 화면이 쓰는 꼴의 그 값은 알리고, 우연히 같은 숫자(날짜 · 시각 · 나이 · 수 ·
코드)는 알리지 않는다. 정률 칸은 `%` 가 붙은 숫자만, 금액 칸은 `%` 가 붙지 않은 숫자만 그 값이다.

    python3 -m unittest discover -s tests
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from change_core.names import name_notes, stated  # noqa: E402

D = Decimal


class StatedTest(unittest.TestCase):
    def test_the_amount_as_the_screen_writes_it_is_found(self):
        for text, value, percent, piece in (
                ("레이트 체크아웃 (14시 이후 · 1박 요금의 50%)", "50.00", True, "50%"),
                ("레이트 체크아웃 50.00%", "50.00", True, "50.00%"),
                ("레이트 체크아웃 50 %", "50", True, "50 %"),
                ("얼리 체크인 30퍼센트", "30.00", True, "30퍼센트"),
                ("갈라 디너 93.28", "93.28", False, "93.28"),
                ("갈라 디너 1인 93,280원", "93280", False, "93,280"),
                ("리조트피 $15 (현장 결제)", "15.00", False, "15"),
                ("체크인 때 15 USD 를 호텔에 냅니다", "15.00", False, "15"),
                ("조식 1인 20달러, 만 6~11세 10달러", "20.00", False, "20"),
                ("공항 픽업 (편도 40)", "40.00", False, "40"),
        ):
            with self.subTest(text=text):
                self.assertEqual(stated(text, D(value), percent), piece)

    def test_a_number_that_only_happens_to_be_the_same_is_not_the_amount(self):
        for text, value, percent, why in (
                ("레이트 체크아웃 14:00 까지", "14.00", False, "시각"),
                ("레이트 체크아웃 12:01~14:00", "1.00", False, "시각"),
                ("레이트 체크아웃 (14시 이후 · 1박 요금의 50%)", "14.00", False, "「14시」는 시각"),
                ("레이트 체크아웃 (14시 이후 · 1박 요금의 50%)", "1.00", False, "「1박」은 박수"),
                ("크리스마스 갈라 디너 (12/24 · 의무 · 성인)", "24.00", False, "날짜"),
                ("갈라 디너 2026-12-31", "31.00", False, "날짜"),
                ("갈라 디너 2026.12.31", "12.00", False, "날짜"),
                ("갈라 디너 12월 24일", "24.00", False, "날짜"),
                ("아동 요금 (만 6~11세)", "6.00", False, "나이"),
                ("아동 요금 (만 6~11세)", "11.00", False, "나이"),
                ("아동 요금 (6-11세)", "6.00", False, "나이"),
                ("엑스트라베드 1개", "1.00", False, "수"),
                ("가족 2인 조식", "2.00", False, "수"),
                ("A2 객실 전용", "2.00", False, "코드"),
                ("봉사료 10%", "10.00", False, "금액 칸 — 「10%」는 금액이 아니다"),
                ("갈라 디너 50", "50.00", True, "정률 칸 — 「%」가 없다"),
                ("갈라 디너 150", "50.00", False, "다른 수"),
                ("갈라 디너 50,000원", "50.00", False, "다른 수"),
                ("갈라 디너 오만 원", "50000", False, "한글로 적은 수는 보지 않는다"),
                ("", "50.00", False, "빈 글"),
        ):
            with self.subTest(text=text, why=why):
                self.assertIsNone(stated(text, D(value), percent))

    def test_an_empty_amount_is_never_stated(self):
        self.assertIsNone(stated("미정 50", None, False))


class NotesTest(unittest.TestCase):
    def test_one_plain_sentence_names_the_text_and_says_a_person_changes_it_in_the_erp(self):
        name, description = name_notes([
            ("부과금 「데모 오퍼 · 레이트 체크아웃 (1박 요금의 50%)」", "이름", "레이트 체크아웃 (1박 요금의 50%)", D("50.00"), True),
            ("부과금 「데모 오퍼 · 레이트 체크아웃 (1박 요금의 50%)」", "설명", "18:00 까지 1박 요금의 50% 를 받습니다", D("50.00"), True),
            ("부과금 「데모 오퍼 · 레이트 체크아웃 (1박 요금의 50%)」", "이름", "레이트 체크아웃 (1박 요금의 50%)", D("50.00"), True),
            ("부과금 「데모 오퍼 · 레이트 체크아웃 (1박 요금의 50%)」", "설명", "", D("50.00"), True),
        ])
        self.assertEqual(name.sentence, "부과금 「데모 오퍼 · 레이트 체크아웃 (1박 요금의 50%)」의 이름에 바꾸기 전 값(50%)이 그대로 "
                                        "적혀 있습니다 — 도우미는 이름을 바꾸지 않으니 ERP 에서 사람이 고쳐 주세요.")
        self.assertEqual(description.sentence, "부과금 「데모 오퍼 · 레이트 체크아웃 (1박 요금의 50%)」의 설명 “18:00 까지 1박 요금의 50% 를 "
                                               "받습니다”에 바꾸기 전 값(50%)이 그대로 적혀 있습니다 — 도우미는 설명을 바꾸지 않으니 "
                                               "ERP 에서 사람이 고쳐 주세요.")

    def test_a_long_description_is_quoted_around_the_amount(self):
        long = "체크인 안내 " * 20 + "현장 결제 15달러" + " 기타 안내" * 20
        note, = name_notes([("부과금 「리조트피」", "설명", long, D("15.00"), False)])
        self.assertIn("…", note.sentence)
        self.assertIn("현장 결제 15달러", note.sentence)


if __name__ == "__main__":
    unittest.main()
