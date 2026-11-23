"""ERP 화면 조각 읽기 — 실제 캡처 셋과 손으로 만든 조각 둘.

    python3 -m unittest discover -s tests

실제 캡처(`calendar-*.html`)는 stay-setup-run 의 ERP 픽스처 사본이다(basecamp 가 실제 템플릿으로 그린 조각).
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from erp_read import (  # noqa: E402
    PairRead, ParseError, build_snapshot, expand_days, parse_adjust_page, parse_price_page,
)
from price_model import MISSING, CellKey, CellValue  # noqa: E402

D = Decimal
ERP = HERE / "fixtures" / "erp"


def fixture(name):
    return (ERP / name).read_text(encoding="utf-8")


class DayLabelTest(unittest.TestCase):
    def test_one_day_and_a_run(self):
        self.assertEqual(expand_days("2026-07-01"), ("2026-07-01",))
        self.assertEqual(expand_days("2026-12-30 ~ 2027-01-02 (4일)"),
                         ("2026-12-30", "2026-12-31", "2027-01-01", "2027-01-02"))

    def test_a_run_whose_count_disagrees_or_an_unknown_label_is_refused(self):
        with self.assertRaises(ParseError):
            expand_days("2026-07-01 ~ 2026-07-05 (4일)")
        with self.assertRaises(ParseError):
            expand_days("7월 1일")


class PricePageTest(unittest.TestCase):
    def test_real_capture_single_price(self):
        page = parse_price_page(fixture("calendar-bulk--price-step2.html"))
        self.assertEqual((page.offer, page.room, page.rate_plan, page.currency),
                         ("〈오퍼 관리용 이름〉", "〈오퍼 관리용 이름〉 · 디럭스", "조식 포함", "공급 통화"))
        self.assertEqual(page.days, {"2026-07-01": "가격 판매 가능"})
        self.assertEqual([(row.occupancy, row.nights, row.values) for row in page.rows],
                         [("", 1, {"2026-07-01": (D("120000.00"), None, None)})])

    def test_real_capture_linked_rows_with_a_day_without_price(self):
        page = parse_price_page(fixture("calendar-bulk--price-link-step2.html"))
        self.assertEqual([(row.occupancy, row.values["2026-07-01"][0], row.values["2026-07-02"]) for row in page.rows],
                         [("", D("120000.00"), None), ("A2", D("150000.00"), None), ("A3", D("180000.00"), None)])
        self.assertEqual(page.days, {"2026-07-01": "가격 판매 가능", "2026-07-02": "가격 없음"})

    def test_values_follow_the_cell_position_not_the_reading_order(self):
        page = parse_price_page(fixture("price-runs-closed-absent-list.html"))
        adults, child = page.rows
        self.assertEqual((adults.occupancy, adults.nights, child.occupancy, child.nights), ("A2", 1, "A2C1_CHD", 3))
        self.assertEqual(adults.values["2026-12-31"], (D("160.00"), None, D("120.00")))
        self.assertEqual(adults.values["2026-12-24"], (D("140.00"), None, D("110.00")))
        self.assertEqual(adults.values["2026-12-26"], (D("150.00"), D("180.00"), None))
        self.assertEqual(child.values["2026-12-31"], (D("125.50"), D("130.00"), D("90.00")))

    def test_runs_expand_to_every_day(self):
        page = parse_price_page(fixture("price-runs-closed-absent-list.html"))
        self.assertEqual(sorted(page.days), [f"2026-12-{day}" for day in range(24, 32)])
        self.assertEqual([page.rows[1].values[f"2026-12-{day}"] for day in (24, 25, 26)], [(D("120.00"), None, None)] * 3)
        self.assertEqual({page.rows[0].values[f"2026-12-{day}"] for day in range(27, 31)}, {None})

    def test_a_row_with_too_few_cells_is_refused_rather_than_guessed(self):
        broken = fixture("price-runs-closed-absent-list.html").replace(
            '<td class="stay-numeric">160.00</td><td class="stay-numeric"></td>', '<td class="stay-numeric">160.00</td>')
        with self.assertRaises(ParseError):
            parse_price_page(broken)

    def test_another_screen_is_refused(self):
        with self.assertRaises(ParseError):
            parse_price_page(fixture("calendar-adjust--step2.html"))


class AdjustPageTest(unittest.TestCase):
    def test_real_capture_has_no_rejected_rows(self):
        page = parse_adjust_page(fixture("calendar-adjust--step2.html"))
        self.assertEqual((page.offer, page.rejected, page.hidden), ("〈오퍼 관리용 이름〉", (), 0))

    def test_rejected_rows_with_runs_and_reasons(self):
        page = parse_adjust_page(fixture("adjust-rejected.html"))
        self.assertEqual(page.hidden, 0)
        self.assertEqual([(row.days, row.room, row.rate_plan, row.occupancy, row.nights, row.reason) for row in page.rejected], [
            (("2026-12-24", "2026-12-25"), "디럭스", "조식 포함", "A2", 1, "예약이 있는 날"),
            (("2026-12-24", "2026-12-25"), "디럭스", "조식 포함", "A2C1_CHD", 3, "예약이 있는 날"),
            (("2026-12-28",), "스위트", "룸온리", "A3", 1, "예약이 있는 날"),
            (("2026-12-31",), "스위트", "룸온리", "", 1, "정가보다 비싸짐"),
        ])

    def test_three_hundred_shown_rows_and_the_hidden_count(self):
        rows = "".join(f"<tr><td>2026-{month:02d}-{day:02d}</td><td>디럭스</td><td>조식 포함</td><td>A2 · 성인 2</td>"
                       f"<td>1박 이상</td><td>예약이 있는 날</td></tr>"
                       for month in range(1, 13) for day in range(1, 26))
        html = fixture("adjust-rejected.html")
        start, end = html.index("<tbody><tr><td>2026-12-24"), html.index("</tbody>", html.index("<tbody><tr><td>2026-12-24"))
        html = html[:start] + "<tbody>" + rows + html[end:]
        html = html.replace("</table>\n    </div>\n  </section>\n  <div class=\"stay-banner",
                            "</table>\n    </div>\n    <p class=\"stay-description\">목록이 길어 1,025줄은 줄였습니다. "
                            "적용한 뒤 적용 기록에서 모두 볼 수 있습니다.</p>\n  </section>\n  <div class=\"stay-banner")
        page = parse_adjust_page(html)
        self.assertEqual((len(page.rejected), page.hidden), (300, 1025))

    def test_the_first_step_is_refused(self):
        with self.assertRaises(ParseError):
            parse_adjust_page(fixture("calendar-bulk--price-step2.html"))


class SnapshotTest(unittest.TestCase):
    def test_pages_become_one_snapshot_with_states_and_reserved_days(self):
        price = parse_price_page(fixture("price-runs-closed-absent-list.html"))
        adjust = parse_adjust_page(fixture("adjust-rejected.html").replace("<td>스위트</td><td>룸온리</td><td>A3",
                                                                           "<td>디럭스</td><td>룸온리</td><td>A3"))
        snapshot = build_snapshot("데모 호텔", "2026-11-20T14:02:00+09:00", [PairRead.of("디럭스", price)], [adjust])
        self.assertEqual((snapshot.hotel, snapshot.offer, snapshot.currency), ("데모 호텔", "샘플 오퍼", "USD"))
        key = lambda day, occ="A2", nights=1: CellKey("디럭스", "조식 포함", day, occ, nights)  # noqa: E731
        self.assertEqual(snapshot.cells[key("2026-12-24")], CellValue(D("140.00"), None, D("110.00"), "open"))
        self.assertEqual(snapshot.cells[key("2026-12-26")], CellValue(D("150.00"), D("180.00"), None, "closed"))
        self.assertEqual(snapshot.cells[key("2026-12-26", "A2C1_CHD", 3)], CellValue(D("120.00"), None, None, "closed"))
        self.assertEqual(snapshot.cells[key("2026-12-28")], MISSING)
        self.assertEqual(len(snapshot.cells), 16)
        self.assertEqual(snapshot.reserved, {("디럭스", "2026-12-24"), ("디럭스", "2026-12-25"), ("디럭스", "2026-12-28")})
        self.assertEqual(snapshot.pairs, {("디럭스", "조식 포함")})
        self.assertEqual(snapshot.row_labels, {"A2": "A2 · 성인 2", "A2C1_CHD": "A2C1_CHD · 소아 1"},
                         "줄을 고르게 할 때 쓰는 ERP 의 이름 — 줄 머리에서 박수 층을 뺀 것")
        self.assertEqual(snapshot.closures, {("디럭스", "조식 포함", "2026-12-26")},
                         "「요금제 마감」은 지속 마감 — ERP 가 그날 새로 만드는 칸도 마감이다(검토 2 의 0)")

    def test_hidden_rows_unknown_rooms_mixed_offers_and_placeholder_currency_are_refused(self):
        price = parse_price_page(fixture("price-runs-closed-absent-list.html"))
        adjust = parse_adjust_page(fixture("adjust-rejected.html"))
        with self.assertRaises(ParseError):
            build_snapshot("H", "t", [PairRead.of("디럭스", price)], [adjust])
        hidden = parse_adjust_page(fixture("adjust-rejected.html").replace(
            "<td>스위트</td>", "<td>디럭스</td>").replace(
            "</table>\n    </div>\n  </section>\n  <div class=\"stay-banner",
            "</table>\n    </div>\n    <p class=\"stay-description\">목록이 길어 3줄은 줄였습니다.</p>\n  </section>\n"
            "  <div class=\"stay-banner"))
        self.assertEqual(hidden.hidden, 3)
        with self.assertRaises(ParseError):
            build_snapshot("H", "t", [PairRead.of("디럭스", price)], [hidden])
        with self.assertRaises(ParseError):
            build_snapshot("H", "t", [PairRead.of("디럭스", price), PairRead.of("디럭스", parse_price_page(fixture("calendar-bulk--price-step2.html")))])
        with self.assertRaises(ParseError):
            build_snapshot("H", "t", [PairRead.of("디럭스", parse_price_page(fixture("calendar-bulk--price-step2.html")))])

    def test_a_day_whose_cells_differ_in_state_reads_as_mixed_and_a_hand_closed_day_is_not_a_closure(self):
        """검토 2 의 0 — 셀 창에서 칸마다 마감해 상태가 섞인 날(「인원·박수별 상태 다름」)은 칸마다 어느 쪽인지 화면에 없다 — 그날의 칸은
        모두 mixed 로 읽는다(시즌 다시 채우기가 그런 날을 만든 뒤에도 확인 · 되돌리기가 된다). 「기존 가격 마감」은 지속 마감이 아니다."""
        page = fixture("price-runs-closed-absent-list.html")
        mixed = build_snapshot("H", "t", [PairRead.of("디럭스", parse_price_page(page.replace(
            "<td>2026-12-26</td><td>요금제 마감</td>", "<td>2026-12-26</td><td>인원·박수별 상태 다름</td>")))])
        key = lambda occ, nights=1: CellKey("디럭스", "조식 포함", "2026-12-26", occ, nights)  # noqa: E731
        self.assertEqual((mixed.cells[key("A2")].state, mixed.cells[key("A2C1_CHD", 3)].state, mixed.closures), ("mixed", "mixed", frozenset()))
        hand = build_snapshot("H", "t", [PairRead.of("디럭스", parse_price_page(page.replace(
            "<td>2026-12-26</td><td>요금제 마감</td>", "<td>2026-12-26</td><td>기존 가격 마감</td>")))])
        self.assertEqual((hand.cells[key("A2")].state, hand.closures), ("closed", frozenset()))

    def test_a_day_state_the_helper_does_not_know_is_refused(self):
        unknown = parse_price_page(fixture("price-runs-closed-absent-list.html").replace(
            "<td>2026-12-26</td><td>요금제 마감</td>", "<td>2026-12-26</td><td>새로운 상태</td>"))
        with self.assertRaises(ParseError):
            build_snapshot("H", "t", [PairRead.of("디럭스", unknown)])

    def test_real_capture_with_a_currency_code(self):
        page = parse_price_page(fixture("calendar-bulk--price-link-step2.html").replace("(공급 통화)", "(KRW)"))
        snapshot = build_snapshot("H", "t", [PairRead.of("디럭스", page)])
        self.assertEqual(snapshot.currency, "KRW")
        self.assertEqual(snapshot.cells[CellKey("디럭스", "조식 포함", "2026-07-01", "A3", 1)],
                         CellValue(D("180000.00"), None, None, "open"))
        self.assertEqual(snapshot.cells[CellKey("디럭스", "조식 포함", "2026-07-02", "A3", 1)], MISSING)


if __name__ == "__main__":
    unittest.main()
