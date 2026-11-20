"""값 모양 — 반올림 자릿수, 칸 상태의 규칙, 인원 조합 키, JSON 왕복.

    python3 -m unittest discover -s tests
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from price_model import (  # noqa: E402
    CellKey, CellValue, ChangeRequest, Snapshot, decode_request, decode_snapshot, encode_request,
    encode_snapshot, round_money, split_occupancy,
)

D = Decimal


class RoundingTest(unittest.TestCase):
    def test_two_decimal_currency_rounds_half_up(self):
        self.assertEqual(round_money(D("373.945"), "USD"), D("373.95"))
        self.assertEqual(round_money(D("0.005"), "EUR"), D("0.01"))
        self.assertEqual(round_money(D("-0.005"), "USD"), D("-0.01"))

    def test_zero_decimal_currencies(self):
        for code in ("KRW", "VND", "JPY", "IDR", "CLP", "ISK", "krw"):
            self.assertEqual(round_money(D("1234.5"), code), D("1235"), code)
            self.assertEqual(round_money(D("1234.49"), code), D("1234"), code)


class CellValueTest(unittest.TestCase):
    def test_missing_has_no_sell_price_and_only_missing_does(self):
        with self.assertRaises(ValueError):
            CellValue(D("10"), None, None, "missing")
        with self.assertRaises(ValueError):
            CellValue(None, None, None, "open")
        with self.assertRaises(ValueError):
            CellValue(D("10"), None, None, "sold")


class RequestTest(unittest.TestCase):
    def base(self, **over):
        fields = dict(hotel="H", offer="O", rooms=("R",), rate_plans=("P",), dates=("2026-12-25",),
                      operation="amount", value=D("10"))
        fields.update(over)
        return ChangeRequest(**fields)

    def test_set_needs_base_occupancy_and_only_set_takes_it(self):
        with self.assertRaises(ValueError):
            self.base(operation="set")
        with self.assertRaises(ValueError):
            self.base(base_occupancy="A2")
        self.assertEqual(self.base(operation="set", base_occupancy="A2").base_occupancy, "A2")

    def test_dates_must_be_sorted_unique_iso(self):
        with self.assertRaises(ValueError):
            self.base(dates=("2026-12-26", "2026-12-25"))
        with self.assertRaises(ValueError):
            self.base(dates=("2026-12-25", "2026-12-25"))
        with self.assertRaises(ValueError):
            self.base(dates=("12/25",))

    def test_unknown_operation(self):
        with self.assertRaises(ValueError):
            self.base(operation="multiply")


class OccupancyKeyTest(unittest.TestCase):
    def test_split(self):
        self.assertEqual(split_occupancy(""), ("", False))
        self.assertEqual(split_occupancy("3"), ("3", False))
        self.assertEqual(split_occupancy("A2"), ("A2", False))
        self.assertEqual(split_occupancy("A2C1_CHD"), ("A2", True))
        self.assertEqual(split_occupancy("A2C1_CHD_C1_TEEN"), ("A2", True))
        self.assertEqual(split_occupancy("A2C1"), ("A2", True))
        self.assertEqual(split_occupancy("2A+1유아"), (None, None))


class JsonTest(unittest.TestCase):
    def test_snapshot_and_request_round_trip_keep_exact_money(self):
        key = CellKey("디럭스", "조식 포함", "2026-12-25", "A2C1_CHD", 3)
        snapshot = Snapshot("데모 호텔", "기본 오퍼", "USD", "2026-11-20T14:02:00+09:00",
                            {key: CellValue(D("339.95"), None, D("0.10"), "closed")},
                            frozenset({("디럭스", "2026-12-25")}))
        self.assertEqual(decode_snapshot(encode_snapshot(snapshot)), snapshot)
        request = ChangeRequest("데모 호텔", "기본 오퍼", ("디럭스",), ("조식 포함",), ("2026-12-25",),
                                "set", D("350.00"), base_occupancy="A2", sentence="350 으로")
        self.assertEqual(decode_request(encode_request(request)), request)

    def test_duplicate_cell_in_snapshot_is_refused(self):
        cell = dict(room="R", rate_plan="P", date="2026-12-25", occupancy="A2", nights=1,
                    sell="1", list=None, supply=None, state="open")
        with self.assertRaises(ValueError):
            decode_snapshot(dict(hotel="H", offer="O", currency="USD", read_at="t", cells=[cell, cell]))


if __name__ == "__main__":
    unittest.main()
