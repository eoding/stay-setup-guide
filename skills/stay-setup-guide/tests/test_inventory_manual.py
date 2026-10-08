"""Optional inventory must neither affect old guides nor accept incomplete stock writes."""
import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_check_manual import HEAD, DICTIONARY, cm


def inventory_steps(qty="10", end="2026-10-31", rooms="선택: 가을 계약 · Deluxe", weekdays="선택: 월, 화, 수, 목, 금, 토, 일"):
    return f"""
## 4. 재고 수량 판매 켜기 (가을 계약 · Deluxe)
탭: `재고`
카드: `가을 계약 · Deluxe`
→ [수량으로 판매]

## 5. 재고 한꺼번에 넣기 (1회차)
탭: `재고`
버튼: [한꺼번에 넣기]
| 칸 | 값 |
|---|---|
| 시작일 | 2026-10-08 |
| 종료일 | {end} |
| 요일 | {weekdays} |
| 판매 연결 | {rooms} |
| 총 수량 | {qty} |
→ [넣기]
"""


class TestOptionalInventory(unittest.TestCase):
    def check(self, body):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "manual.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(HEAD + body)
            return cm.check(path, dictionary_path=DICTIONARY)

    def test_old_guide_needs_no_inventory(self):
        result = self.check("")
        self.assertEqual(result.get("inventory_gaps", []), [])

    def test_explicit_inventory_is_recognized(self):
        result = self.check(inventory_steps())
        self.assertEqual(result["unknown_step_kinds"], [])
        self.assertEqual(result["unknown_fields"], self.check("")["unknown_fields"])
        self.assertEqual(result.get("inventory_gaps", []), [])

    def test_missing_negative_fractional_and_overflow_quantity_are_rejected(self):
        for qty in ("비움", "-1", "1.5", "10000", "2147483648", "자동 입력됨 · 그대로 둠"):
            with self.subTest(qty=qty):
                self.assertTrue(self.check(inventory_steps(qty=qty)).get("inventory_gaps"))

    def test_zero_is_valid_and_not_an_empty_inventory(self):
        self.assertEqual(self.check(inventory_steps(qty="0")).get("inventory_gaps", []), [])

    def test_bulk_range_includes_both_endpoints(self):
        start = datetime.date(2026, 10, 8)
        for days, rejected in ((400, False), (401, True)):
            end = (start + datetime.timedelta(days=days - 1)).isoformat()
            self.assertEqual(bool(self.check(inventory_steps(end=end)).get("inventory_gaps")), rejected)

    def test_no_unqualified_or_default_selection(self):
        for rooms in ("비움", "선택: Deluxe"):
            self.assertTrue(self.check(inventory_steps(rooms=rooms)).get("inventory_gaps"))
        self.assertTrue(self.check(inventory_steps(weekdays="비움")).get("inventory_gaps"))

    def test_missing_enable_step_does_not_silently_enable_stock(self):
        body = inventory_steps().split("## 5.", 1)[1]
        self.assertTrue(self.check("\n## 4." + body).get("inventory_gaps"))

    def test_cell_write_requires_exact_date_and_total_quantity(self):
        base = inventory_steps().split("## 5.", 1)[0]
        for day, label, rejected in (("2026-10-08", "총 수량", False), ("", "총 수량", True),
                                     ("2026-02-30", "총 수량", True), ("2026-10-08", "남음", True)):
            body = base + f"\n## 5. 재고 수량 고치기\n탭: `재고`\n카드: `가을 계약 · Deluxe`\n블록: `{day}`\n| 칸 | 값 |\n|---|---|\n| {label} | 0 |\n→ [저장]\n"
            self.assertEqual(bool(self.check(body).get("inventory_gaps")), rejected)


if __name__ == "__main__":
    unittest.main()
