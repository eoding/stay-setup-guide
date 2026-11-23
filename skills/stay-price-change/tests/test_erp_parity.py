"""ERP 와 같은 계산 — 「정가도 같이 올림」의 정가(Y1), 1박 이상보다 비싼 박수 층(Y2).

기대값은 도우미를 돌려 얻은 것이 아니라 ERP 소스를 읽고 손으로 셈한 것이다. 근거는 basecamp
`stay/services/bulk_price_adjust.py` 의 `build_preview` 가 「정가도 같이 조정」(`adjust_original`)을 켰을 때 정가를 옮기는 줄이다:

    정액   after_original = normalize(original + value, code)
    정률   factor = (100 + value) / 100,  scaled(x) = normalize(x * factor, code)
           아동 없는 칸(또는 '추가 인원 요금도 같이 조정')   after_original = scaled(original)
           아동 있는 칸   extra = cell.price - adult        (adult = 같은 날 · 요금제 · 박수 층의 성인만 있는 칸의 판매가)
                          after_original = scaled(original - extra) + extra
    normalize = `pricing.money.normalize` — 공급 통화 최소 단위로 ROUND_HALF_UP(USD 2자리, KRW · VND · JPY · IDR 0자리)

새 값 지정(set)은 ERP 에 짝이 없다 — 브리프대로 판매가가 옮긴 만큼 정가도 옮긴다.

박수 층의 기대값은 같은 파일의 `_check_los_tiers` 를 읽고 손으로 정했다(바꾼 뒤의 값, 건너뛴 칸은 지금 값으로 견준다):

    ① upper_tiers   2박 이상 칸의 after > 그날 같은 인원 조합의 1박 칸(price_at) 이면 그 칸을 건너뜀
    ② 1박 칸        같은 좌표의 다른 층(고르지 않은 층도 — `tiers`) 가운데 price_at > 1박 칸의 after 가 있으면 1박 칸을 건너뜀
    ③ upper_tiers   ② 로 1박 칸이 지금 값으로 돌아갔으니 한 번 더 — 건너뛰는 칸이 더 늘지 않을 때까지(`while True`)
    차례            … → 정가보다 비싸짐(ABOVE_ORIGINAL) → 1박 가격보다 비싸짐(ABOVE_ONE_NIGHT) — 칸마다 첫 사유 하나

도우미에서 ERP 의 「건너뜀」은 빨간 줄 ABOVE_ONE_NIGHT(이대로 바꿈 / 그 칸은 안 바꿈)다. 「정가도 같이 조정」을 끈 ERP 는 도우미에서
정가 빨간 줄에 「그 칸은 안 바꿈」을, 켠 ERP 는 「정가도 같이 올림」을 고른 것과 같다.

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


def tiers(cells, currency="USD"):
    """`{(인원, 박수): 판매가 또는 (판매가, 정가)}` → 객실 R · 요금제 P · 하루의 Snapshot."""
    def value(item):
        sell, lst = item if isinstance(item, tuple) else (item, None)
        return CellValue(D(sell), None if lst is None else D(lst), None, "open")
    return Snapshot("H", "O", currency, "2026-11-20T10:00:00+09:00",
                    {CellKey("R", "P", DAY, occ, nights): value(item) for (occ, nights), item in cells.items()},
                    frozenset(), frozenset({("R", "P")}), hotel_id="9")


def tier_red(snapshot, request, choices=()):
    """박수 층 빨간 줄에 걸린 칸 {(인원, 박수)} 와 그 미리보기."""
    plan = resolve(plan_change(snapshot, request), choices)
    return {(c.key.occupancy, c.key.nights) for c in plan.changes if c.verdict == "ABOVE_ONE_NIGHT"}, plan


A2_1, A2_2, A2_3 = ("A2", 1), ("A2", 2), ("A2", 3)
# (이름, 칸들, 요청, 고름, ERP 가 1박 가격보다 비싸짐으로 건너뛰는 칸, _check_los_tiers 로 손으로 셈한 것)
TIER_CASES = (
    ("1박만 10% 내림 — 브리프의 예", {A2_1: "100.00", A2_3: "95.00"}, ask("percent", "-10", nights=(1,)), (),
     {A2_1}, "② 1박 90.00 < 3박 이상 95.00(고르지 않은 층) → 1박 칸"),
    ("1박만 4% 내림 — 아직 3박 이상보다 비쌈", {A2_1: "100.00", A2_3: "95.00"}, ask("percent", "-4", nights=(1,)), (),
     set(), "② 1박 96.00 > 3박 이상 95.00 → 건너뛰지 않음"),
    ("3박 이상만 10% 올림", {A2_1: "100.00", A2_3: "95.00"}, ask("percent", "10", nights=(3,)), (),
     {A2_3}, "① 3박 이상 104.50 > 1박 100.00 → 3박 이상 칸"),
    ("3박 이상만 5% 올림", {A2_1: "100.00", A2_3: "95.00"}, ask("percent", "5", nights=(3,)), (),
     set(), "① 99.75 < 100.00"),
    ("같으면 비싸진 것이 아니다", {A2_1: "100.00", A2_3: "95.00"}, ask("amount", "5", nights=(3,)), (),
     set(), "① 100.00 > 100.00 은 거짓(엄격히 큼)"),
    ("모든 층 10% 올림", {A2_1: "100.00", A2_3: "95.00"}, ask("percent", "10"), (),
     set(), "① 104.50 < 110.00"),
    ("② 다음 ① 한 번 더", {A2_1: "100.00", A2_2: "98.00", A2_3: "130.00"}, ask("amount", "20", nights=(1, 2)), (),
     {A2_1, A2_2}, "① 2박 118 < 1박 120 · ② 1박 120 < 3박 이상 130 → 1박 건너뜀 · ③ 2박 118 > 1박 지금 값 100 → 2박 건너뜀"),
    ("정가 빨간 줄을 안 바꿈 = 「정가도 같이 조정」을 끈 ERP", {A2_1: ("100.00", "105.00"), A2_3: "95.00"}, ask("percent", "10"),
     (Resolution("ABOVE_LIST", "keep"),), {A2_3}, "1박 110 > 정가 105 → 정가보다 비싸짐으로 건너뜀 · ① 3박 이상 104.50 > 1박 지금 값 100"),
    ("정가도 같이 올림 = 「정가도 같이 조정」을 켠 ERP", {A2_1: ("100.00", "105.00"), A2_3: "95.00"}, ask("percent", "10"),
     (Resolution("ABOVE_LIST", "raise_list"),), set(), "1박 110 · 정가 115.50 저장 · ① 104.50 < 110"),
    ("바꾸기 전부터 어긴 칸도 이번에 바꾸면 본다", {A2_1: "100.00", A2_3: "105.00"}, ask("percent", "10"), (),
     {A2_3}, "① 3박 이상 115.50 > 1박 110.00"),
    ("바꾸지 않는 칸은 보지 않는다", {A2_1: "100.00", A2_3: "105.00"}, ask("percent", "10", nights=(1,)), (),
     set(), "② 1박 110 > 3박 이상 105 — 고르지 않은 3박 이상은 cells 에 없다"),
    ("아동 칸도 제 1박 이상과 견준다", {A2_1: "100.00", A2_3: "90.00", ("A2C1_CHD", 1): "130.00", ("A2C1_CHD", 3): "117.00"},
     ask("percent", "-20", nights=(1,)), (), {A2_1},
     "② 성인 1박 80 < 90 · 아동 1박 scaled(100) + 30 = 110 < 117 — ERP 는 아동 1박도 이 까닭으로 건너뛴다. 도우미는 고를 것을 성인 "
     "1박 하나로 두고 아동 1박은 그 성인 칸을 따라 같이 그대로(ADULT_HELD) 둔다(T5 — 저장하지 않는 것은 같다)"),
    ("아동 칸 — 걸리지 않는 만큼", {A2_1: "100.00", A2_3: "90.00", ("A2C1_CHD", 1): "130.00", ("A2C1_CHD", 3): "117.00"},
     ask("percent", "-10", nights=(1,)), (), set(), "② 성인 1박 90 = 90 · 아동 1박 120 > 117"),
)


class TierRuleTest(unittest.TestCase):
    def test_a_red_line_where_the_erp_skips_a_cell_for_the_one_night_price_and_none_where_it_does_not(self):
        for name, cells, request, choices, expected, worked in TIER_CASES:
            with self.subTest(name, worked=worked):
                self.assertEqual(tier_red(tiers(cells), request, choices)[0], expected)

    def test_the_two_choices_and_what_each_saves(self):
        snapshot, request = tiers({A2_1: "100.00", A2_3: "95.00"}), ask("percent", "-10", nights=(1,))
        red, plan = tier_red(snapshot, request)
        self.assertIsNone(plan_steps(plan), "고르기 전에는 저장할 수 없다")
        for choice, written in (("include", D("90.00")), ("keep", None)):
            chosen = resolve(plan_change(snapshot, request), [Resolution("ABOVE_ONE_NIGHT", choice)])
            rows = [row.sell for step in plan_steps(chosen) for row in step.rows]
            self.assertEqual(rows, [written] if written else [], choice)

    def test_the_erp_order_where_both_rules_apply(self):
        snapshot = tiers({A2_1: "100.00", A2_3: ("95.00", "100.00")})
        request = ask("percent", "10", nights=(3,))      # 3박 이상 104.50 — 정가 100 도, 1박 100 도 넘는다
        plan = plan_change(snapshot, request)
        self.assertEqual([c.verdict for c in plan.changes], ["ABOVE_LIST"], "ERP 차례: 정가보다 비싸짐이 먼저")
        raised = resolve(plan, [Resolution("ABOVE_LIST", "raise_list")])
        self.assertEqual([(c.verdict, c.choice, c.after.list) for c in raised.changes], [("ABOVE_ONE_NIGHT", None, D("110.00"))],
                         "정가를 같이 올려 판매가가 바뀌면(「정가도 같이 조정」을 켠 ERP) 그다음 규칙이 걸린다")
        lowered = plan_change(tiers({A2_1: "100.00", A2_3: "95.00"}), ask("percent", "-40", nights=(1,)))
        self.assertEqual([c.verdict for c in lowered.changes], ["ABOVE_ONE_NIGHT"], "박수 층 규칙이 30% 보다 앞선다")

    def test_the_preview_says_how_many_cells_already_broke_the_rule(self):
        snapshot = tiers({A2_1: "100.00", A2_3: "105.00", ("A3", 1): "160.00", ("A3", 3): "170.00"})
        plan = plan_change(snapshot, ask("percent", "10", nights=(1,)))
        self.assertEqual(plan.above_one_night_before, 2)
        self.assertIn("바꾸기 전부터 같은 날 1박 이상 가격보다 비싼 박수 층 칸이 2칸", render_preview(plan))
        page = render_preview(tier_red(tiers({A2_1: "100.00", A2_3: "95.00"}), ask("percent", "-10", nights=(1,)))[1])
        self.assertIn("같은 날 1박 이상 가격보다 비싼 박수 층이 됩니다.", page)
        self.assertIn("이 칸은 골라 주세요: 이대로 바꿈 / 그 칸은 안 바꿈.", page)


if __name__ == "__main__":
    unittest.main()
