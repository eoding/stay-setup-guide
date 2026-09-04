#!/usr/bin/env python3
"""convert_currency.py 환산 규칙 시험.

실행:
    python3 -m unittest discover -s skills/stay-setup-guide/tests -v
    (또는 pytest skills/stay-setup-guide/tests)
"""
import decimal
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.normpath(os.path.join(HERE, os.pardir))
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import convert_currency as cc  # noqa: E402

RATE = decimal.Decimal("25500")


def convert(text, rate=RATE, decimals=2, extra=()):
    return cc.convert_text(text, "VND", "USD", rate, decimals, extra)


class TestConvertAmount(unittest.TestCase):
    def test_round_half_up(self):
        # 3498000 / 25500 = 137.176470… → 137.18
        self.assertEqual(cc.convert_amount("3498000", RATE, 2), "137.18")
        # 3882780 / 25500 = 152.265882… → 152.27
        self.assertEqual(cc.convert_amount("3882780", RATE, 2), "152.27")
        # 3300000 / 25500 = 129.411764… → 129.41
        self.assertEqual(cc.convert_amount("3300000", RATE, 2), "129.41")

    def test_half_up_not_bankers(self):
        # 2.125 는 사사오입이면 2.13 (은행가 반올림이면 2.12 가 된다)
        self.assertEqual(cc.convert_amount("2.125", decimal.Decimal(1), 2), "2.13")

    def test_trailing_zeros_dropped(self):
        # 127500 / 25500 = 5.00 → `5`
        self.assertEqual(cc.convert_amount("127500", RATE, 2), "5")
        # 357000 / 25500 = 14.00 → `14`
        self.assertEqual(cc.convert_amount("357000", RATE, 2), "14")
        self.assertEqual(cc.convert_amount("0", RATE, 2), "0")

    def test_no_thousands_separator(self):
        self.assertEqual(cc.convert_amount("100,000,000", RATE, 2), "3921.57")

    def test_sign_kept(self):
        self.assertEqual(cc.convert_amount("+1390000", RATE, 2), "+54.51")
        self.assertEqual(cc.convert_amount("-510000", RATE, 2), "-20")

    def test_non_numeric_left_alone(self):
        for value in ("+24.5%", "선택: VND", "비움", "체크", "해제",
                      "자동 입력됨 · 그대로 둠", "2026-07-01", "10:00"):
            self.assertIsNone(cc.convert_amount(value, RATE, 2))


class TestCurrencyField(unittest.TestCase):
    def test_supply_currency_row(self):
        text = "| 칸 | 값 |\n|---|---|\n| 공급 통화 | 선택: VND |\n"
        new, summary = convert(text)
        self.assertIn("| 공급 통화 | 선택: USD |", new)
        self.assertEqual(summary["currency_rows"], 1)

    def test_other_currency_untouched(self):
        text = "| 공급 통화 | 선택: JPY |\n"
        new, summary = convert(text)
        self.assertIn("선택: JPY", new)
        self.assertEqual(summary["currency_rows"], 0)


class TestTableValues(unittest.TestCase):
    def test_price_fields(self):
        text = (
            "## 44. 시즌 가격 채우기 (1회차, Medium × 디럭스)\n"
            "\n| 칸 | 값 |\n|---|---|\n"
            "| 판매 단가(공급 통화) | 3498000 |\n"
            "| 정가(취소선, 선택) | 3882780 |\n"
            "| 공급 원가(net, 선택) | 3300000 |\n"
            "| 인원 조합(선택) | 비움 |\n"
            "| 이미 값이 있는 날도 덮기 | 해제 |\n"
        )
        new, summary = convert(text)
        self.assertIn("| 판매 단가(공급 통화) | 137.18 |", new)
        self.assertIn("| 정가(취소선, 선택) | 152.27 |", new)
        self.assertIn("| 공급 원가(net, 선택) | 129.41 |", new)
        self.assertIn("| 인원 조합(선택) | 비움 |", new)
        self.assertIn("| 이미 값이 있는 날도 덮기 | 해제 |", new)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["per_field"]["판매 단가(공급 통화)"], 1)

    def test_addon_and_charge_fields(self):
        text = (
            "| 판매가(공급 통화) | 952500 |\n"
            "| 공급 원가(선택) | 900000 |\n"
            "| 판매가 | 2173000 |\n"
            "| 정가 | 2412030 |\n"
            "| 공급 원가 | 2050000 |\n"
        )
        new, _ = convert(text)
        self.assertIn("| 판매가(공급 통화) | 37.35 |", new)
        self.assertIn("| 공급 원가(선택) | 35.29 |", new)
        self.assertIn("| 판매가 | 85.22 |", new)
        self.assertIn("| 정가 | 94.59 |", new)
        self.assertIn("| 공급 원가 | 80.39 |", new)

    def test_zero_price_kept_as_zero(self):
        new, _ = convert("| 판매가(공급 통화) | 0 |\n")
        self.assertIn("| 판매가(공급 통화) | 0 |", new)


class TestAdjustmentFields(unittest.TestCase):
    def test_absolute_adjustment_converted(self):
        new, summary = convert("| 기준 요금제 대비 조정(선택) | +1390000 |\n")
        self.assertIn("| 기준 요금제 대비 조정(선택) | +54.51 |", new)
        self.assertEqual(summary["total"], 1)

    def test_percentage_adjustment_untouched(self):
        text = (
            "| 기준 요금제 대비 조정(선택) | +24.5% |\n"
            "| 인원 조합별 조정(선택) | -10% |\n"
        )
        new, summary = convert(text)
        self.assertEqual(new.rstrip("\n"), text.rstrip("\n"))
        self.assertEqual(summary["total"], 0)

    def test_percent_only_fields_untouched(self):
        text = (
            "| 단 1 · 할인율(%) | 23 |\n"
            "| 정률(%) 값 | 5 |\n"
            "| 우선순위 | 100 |\n"
            "| 무료 제공 수량 | 2 |\n"
            "| 최소 숙박(박) | 3 |\n"
            "| 얼리버드 리드타임(체크인 D-N일) | 17 |\n"
        )
        new, summary = convert(text)
        self.assertEqual(new.rstrip("\n"), text.rstrip("\n"))
        self.assertEqual(summary["total"], 0)


class TestLabelRename(unittest.TestCase):
    def test_currency_tag_in_label(self):
        text = (
            "| 정액 금액 (VND) | 선택: 지정 (0 포함) |\n"
            "| 정액 금액 (VND) 값 | 357000 |\n"
            "| 금액 가치 (VND) | 비움 |\n"
        )
        new, summary = convert(text)
        self.assertIn("| 정액 금액 (USD) | 선택: 지정 (0 포함) |", new)
        self.assertIn("| 정액 금액 (USD) 값 | 14 |", new)
        self.assertIn("| 금액 가치 (USD) | 비움 |", new)
        self.assertEqual(summary["renamed"]["금액 가치 (VND)"], "금액 가치 (USD)")
        self.assertEqual(summary["total"], 1)

    def test_free_text_supply_currency(self):
        text = "주의: 이 호텔은 공급 통화 VND 로 판다\n"
        new, summary = convert(text)
        self.assertIn("공급 통화 USD 로 판다", new)
        self.assertEqual(summary["free_text"], 1)


class TestUntouched(unittest.TestCase):
    def test_dates_codes_and_text_kept(self):
        text = (
            "## 20. 시즌 만들기 (1번째, Medium)\n"
            "탭: `시즌`\n"
            "\n| 칸 | 값 |\n|---|---|\n"
            "| 시즌 코드 | VD26-MED |\n"
            "| 기간 시작 | 2026-01-01 |\n"
            "| 기간 종료 | 2026-12-31 |\n"
            "| 호텔 예약 코드 | 4000 |\n"
            "| 조식 정보 | 뷔페 · 06:00~10:00 |\n"
            "\n→ [추가]\n"
        )
        new, summary = convert(text)
        self.assertEqual(new, text)
        self.assertEqual(summary["total"], 0)

    def test_trailing_newline_preserved(self):
        self.assertTrue(convert("| 판매가 | 2550000 |\n")[0].endswith("\n"))
        self.assertFalse(convert("| 판매가 | 2550000 |")[0].endswith("\n"))


class TestExtraField(unittest.TestCase):
    def test_extra_field_opt_in(self):
        text = "| 보증금 | 510000 |\n"
        self.assertEqual(convert(text)[1]["total"], 0)
        new, summary = convert(text, extra={"보증금"})
        self.assertIn("| 보증금 | 20 |", new)
        self.assertEqual(summary["total"], 1)


class TestCli(unittest.TestCase):
    def test_in_place_rewrite(self):
        text = "| 공급 통화 | 선택: VND |\n| 판매 단가(공급 통화) | 3498000 |\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "manual.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            code = cc.main([path, "--from", "VND", "--to", "USD", "--rate", "25500"])
            self.assertEqual(code, 0)
            with open(path, encoding="utf-8") as handle:
                out = handle.read()
        self.assertIn("선택: USD", out)
        self.assertIn("137.18", out)

    def test_dry_run_leaves_file(self):
        text = "| 판매 단가(공급 통화) | 3498000 |\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "manual.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            cc.main([path, "--from", "VND", "--to", "USD", "--rate", "25500", "--dry-run"])
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), text)

    def test_output_path(self):
        text = "| 판매 단가(공급 통화) | 3498000 |\n"
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "manual.md")
            dst = os.path.join(tmp, "out.md")
            with open(src, "w", encoding="utf-8") as handle:
                handle.write(text)
            cc.main([src, "--from", "VND", "--to", "USD", "--rate", "25500", "-o", dst])
            with open(src, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), text)
            with open(dst, encoding="utf-8") as handle:
                self.assertIn("137.18", handle.read())

    def test_bad_rate_reports_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "manual.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("| 판매가 | 100 |\n")
            self.assertEqual(
                cc.main([path, "--from", "VND", "--to", "USD", "--rate", "0"]), 1
            )


if __name__ == "__main__":
    unittest.main()
