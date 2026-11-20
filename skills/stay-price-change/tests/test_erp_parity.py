"""ERP 와 같은 계산 — 「정가도 같이 올림」의 정가(Y1).

기대값은 도우미를 돌려 얻은 것이 아니라 ERP 소스를 읽고 손으로 셈한 것이다. 근거는 basecamp
`stay/services/bulk_price_adjust.py` 의 `build_preview` 가 「정가도 같이 조정」(`adjust_original`)을 켰을 때 정가를 옮기는 줄이다:

    정액   after_original = normalize(original + value, code)
    정률   factor = (100 + value) / 100,  scaled(x) = normalize(x * factor, code)
           아동 없는 칸(또는 '추가 인원 요금도 같이 조정')   after_original = scaled(original)
           아동 있는 칸   extra = cell.price - adult        (adult = 같은 날 · 요금제 · 박수 층의 성인만 있는 칸의 판매가)
                          after_original = scaled(original - extra) + extra
    normalize = `pricing.money.normalize` — 공급 통화 최소 단위로 ROUND_HALF_UP(USD 2자리, KRW · VND · JPY · IDR 0자리)

새 값 지정(set)은 ERP 에 짝이 없다 — 브리프대로 판매가가 옮긴 만큼 정가도 옮긴다.

    python3 -m unittest discover -s tests
"""

import re
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from change_core.rules import Resolution  # noqa: E402
from price_model import CellKey, CellValue, ChangeRequest, Snapshot  # noqa: E402
from price_pages import render_preview  # noqa: E402
from price_plan import plan_change, plan_steps, resolve  # noqa: E402

D = Decimal
DAY = "2026-12-25"


def snap(cells, currency="USD"):
    """`{인원 조합: (판매가, 정가)}` → 객실 R · 요금제 P · 하루 · 1박 이상 층의 Snapshot."""
    return Snapshot("H", "O", currency, "2026-11-20T10:00:00+09:00",
                    {CellKey("R", "P", DAY, key, 1): CellValue(D(sell), None if lst is None else D(lst), None, "open")
                     for key, (sell, lst) in cells.items()}, frozenset(), frozenset({("R", "P")}), hotel_id="9")


def ask(operation, value, **over):
    return ChangeRequest("H", "O", ("R",), ("P",), (DAY,), operation, D(value), hotel_id="9", **over)


def raised_list(snapshot, request, occupancy):
    """정가보다 비싸지는 칸에서 「정가도 같이 올림」을 골랐을 때 그 칸이 저장할 (판매가, 정가)."""
    plan = plan_change(snapshot, request)
    change = next(c for c in plan.changes if c.key.occupancy == occupancy)
    assert change.verdict == "ABOVE_LIST", (occupancy, change.verdict)
    chosen = next(c for c in resolve(plan, [Resolution("ABOVE_LIST", "raise_list")]).changes if c.key == change.key)
    return chosen.after.sell, chosen.after.list


# (이름, 통화, 칸들 {인원: (판매가, 정가)}, 요청, 보는 칸, 기대 판매가, 기대 정가, ERP 줄로 손으로 셈한 것)
CASES = (
    ("정액 +10", "USD", {"A2": ("95.00", "100.00")}, ask("amount", "10"), "A2",
     "105.00", "110.00", "normalize(100.00 + 10) = 110.00"),
    ("정률 +12 — 시운전의 숫자", "USD", {"A2": ("60.00", "61.18")}, ask("percent", "12"), "A2",
     "67.20", "68.52", "normalize(61.18 × 1.12 = 68.5216) = 68.52 (종전 도우미는 판매가가 오른 7.20 을 더해 68.38)"),
    ("정률 +10 · 아동 하나", "USD", {"A2": ("100.00", "120.00"), "A2C1_CHD": ("130.00", "138.00")}, ask("percent", "10"),
     "A2C1_CHD", "140.00", "148.80", "extra = 130 − 100 = 30 · scaled(138 − 30 = 108) = 118.80 · + 30 = 148.80"),
    ("정률 +10 · 아동 둘", "USD", {"A2": ("100.00", "120.00"), "A2C2_CHD": ("160.00", "165.00")}, ask("percent", "10"),
     "A2C2_CHD", "170.00", "175.50", "extra = 160 − 100 = 60 · scaled(165 − 60 = 105) = 115.50 · + 60 = 175.50"),
    ("정률 +10 · 아동 추가분도 같이", "USD", {"A2": ("100.00", "120.00"), "A2C1_CHD": ("130.00", "138.00")},
     ask("percent", "10", scale_child_surcharge=True), "A2C1_CHD", "143.00", "151.80", "scaled(138) = 151.80"),
    ("정률 +10 · 반 센트 반올림", "USD", {"A2": ("10.00", "10.15")}, ask("percent", "10"), "A2",
     "11.00", "11.17", "10.15 × 1.1 = 11.165 → ROUND_HALF_UP 11.17 (짝수 맞춤이면 11.16)"),
    ("정률 +12 · 소수 없는 통화", "KRW", {"A2": ("60000", "61180")}, ask("percent", "12"), "A2",
     "67200", "68522", "normalize(61180 × 1.12 = 68521.6, KRW) = 68522"),
    ("정률 +10 · 소수 없는 통화의 반", "KRW", {"A2": ("130", "135")}, ask("percent", "10"), "A2",
     "143", "149", "135 × 1.1 = 148.5 → ROUND_HALF_UP 149 (짝수 맞춤이면 148)"),
    ("정액 +5,000 · 소수 없는 통화", "KRW", {"A2": ("60000", "62000")}, ask("amount", "5000"), "A2",
     "65000", "67000", "normalize(62000 + 5000) = 67000"),
)


class ListFollowsTheErpRuleTest(unittest.TestCase):
    def test_the_list_price_moves_by_the_erp_rule_for_the_kind_of_change(self):
        for name, currency, cells, request, occupancy, sell, lst, worked in CASES:
            with self.subTest(name, worked=worked):
                self.assertEqual(raised_list(snap(cells, currency), request, occupancy), (D(sell), D(lst)))

    def test_a_new_value_has_no_erp_counterpart_and_moves_the_list_by_what_the_sell_price_moved(self):
        snapshot = snap({"A2": ("100.00", "110.00")})
        self.assertEqual(raised_list(snapshot, ask("set", "120", base_occupancy="A2"), "A2"), (D("120.00"), D("130.00")))

    def test_the_words_name_what_happens_with_the_number(self):
        snapshot = snap({"A2": ("60.00", "61.18")})
        page = render_preview(plan_change(snapshot, ask("percent", "12")))
        text = " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", " ", page, flags=re.S)).split())
        self.assertIn("정가도 12% 올림: 61.18 → 68.52 / 정가 지움 / 그 칸은 안 바꿈", text)
        page = render_preview(plan_change(snap({"A2": ("100.00", "110.00")}), ask("set", "120", base_occupancy="A2")))
        self.assertIn("정가도 판매가가 오른 만큼 올림: 110.00 → 130.00", page, "ERP 에 짝이 없으면 그렇다고 말한다")

    def test_the_saved_value_is_the_one_the_preview_shows(self):
        snapshot = snap({"A2": ("100.00", "120.00"), "A2C1_CHD": ("130.00", "138.00")})
        plan = resolve(plan_change(snapshot, ask("percent", "10")), [Resolution("ABOVE_LIST", "raise_list")])
        rows = {row.occupancy: row for step in plan_steps(plan) for row in step.rows}
        self.assertEqual((rows["A2C1_CHD"].sell, rows["A2C1_CHD"].list), (D("140.00"), D("148.80")))

    def test_a_cell_whose_list_is_already_below_its_sell_price_is_refused_like_the_erp_skips_it(self):
        snapshot = snap({"A2": ("100.00", "90.00")})   # 지금도 정가 < 판매가 — ERP 는 정가를 옮겨도 「정가보다 비싸짐」으로 건너뛴다
        plan = plan_change(snapshot, ask("percent", "10"))
        with self.assertRaisesRegex(ValueError, "정가를 같이 올려도 판매가보다 낮은 칸"):
            resolve(plan, [Resolution("ABOVE_LIST", "raise_list")])


if __name__ == "__main__":
    unittest.main()
