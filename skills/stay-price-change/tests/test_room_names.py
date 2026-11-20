"""B11 객실 하나, 이름 둘 — 캘린더 칩의 이름(담당자가 말하는 이름)으로 칸을 적고, 드로어의 이름은 옆에 둔다.
가감 화면의 객실 이름은 그 짝으로 맞춘다(글자를 잘라 맞추지 않는다). 조각은 손 조각의 객실 이름만 바꾼 변형이다.

    python3 -m unittest discover -s tests
"""

import sys
import unittest
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from erp_read import PairRead, ParseError, build_snapshot, parse_adjust_page, parse_price_page  # noqa: E402
from price_model import ChangeRequest, CellKey, decode_snapshot, encode_snapshot  # noqa: E402
from price_plan import plan_change  # noqa: E402

ERP = HERE / "fixtures" / "erp"
PRICE = (ERP / "price-runs-closed-absent-list.html").read_text(encoding="utf-8")     # 드로어: 「샘플 오퍼 · 디럭스」
ADJUST = (ERP / "adjust-rejected.html").read_text(encoding="utf-8")                  # 가감: 「디럭스」·「스위트」
SHOWN = "디럭스 킹 (시티뷰)"                                                        # 오퍼별 표시명이 있는 호텔의 칩 이름


def adjust_naming(room: str) -> str:
    """가감 화면의 객실 칸을 모두 `room` 으로 — 표시명 호텔에서 가감 화면은 칩과 같은 이름(room_label)을 쓴다."""
    return ADJUST.replace("<td>디럭스</td>", f"<td>{room}</td>").replace("<td>스위트</td>", f"<td>{room}</td>")


def snapshot(shown: str, adjust: str, price: str = PRICE):
    return build_snapshot("데모 호텔", "2026-11-20T19:00:00+09:00", [PairRead.of(shown, parse_price_page(price))],
                          [parse_adjust_page(adjust)])


class RoomNamesTest(unittest.TestCase):
    def test_a_hotel_with_display_names_keys_rooms_by_the_calendar_name(self):
        snap = snapshot(SHOWN, adjust_naming(SHOWN))
        self.assertEqual({key.room for key in snap.cells}, {SHOWN})
        self.assertEqual(snap.pairs, {(SHOWN, "조식 포함")})
        self.assertEqual(snap.room_names, {SHOWN: "샘플 오퍼 · 디럭스"})
        self.assertIn((SHOWN, "2026-12-24"), snap.reserved)
        self.assertIn((SHOWN, "2026-12-28"), snap.reserved)

    def test_adjust_rows_named_like_the_drawer_go_through_the_pairing(self):
        snap = snapshot(SHOWN, adjust_naming("샘플 오퍼 · 디럭스"))
        self.assertIn((SHOWN, "2026-12-24"), snap.reserved)

    def test_no_string_surgery_a_drawer_name_without_the_offer_prefix_still_pairs(self):
        price = PRICE.replace("<dt>객실</dt><dd>샘플 오퍼 · 디럭스</dd>", "<dt>객실</dt><dd>Deluxe Room 2F</dd>")
        snap = snapshot("디럭스", adjust_naming("디럭스"), price)
        self.assertEqual(snap.room_names, {"디럭스": "Deluxe Room 2F"})
        self.assertIn(("디럭스", "2026-12-24"), snap.reserved)
        with self.assertRaisesRegex(ParseError, "맞지 않습니다: 샘플 오퍼 · 디럭스"):
            snapshot("디럭스", adjust_naming("샘플 오퍼 · 디럭스"), price)

    def test_one_calendar_name_with_two_drawer_names_or_one_drawer_name_for_two_rooms_is_refused(self):
        page, other = parse_price_page(PRICE), parse_price_page(PRICE.replace("샘플 오퍼 · 디럭스", "샘플 오퍼 · 디럭스 B")
                                                                   .replace("<dd>조식 포함</dd>", "<dd>룸온리</dd>"))
        with self.assertRaisesRegex(ParseError, "두 이름으로 보입니다"):
            build_snapshot("H", "t", [PairRead.of(SHOWN, page), PairRead.of(SHOWN, other)])
        twins = [PairRead.of("디럭스 A", page), PairRead.of("디럭스 B", page)]
        self.assertEqual(len(build_snapshot("H", "t", twins).pairs), 2, "칩 이름이 다르면 드로어 이름이 같아도 읽는다")
        with self.assertRaisesRegex(ParseError, "맞지 않습니다: 샘플 오퍼 · 디럭스"):
            build_snapshot("H", "t", twins, [parse_adjust_page(adjust_naming("샘플 오퍼 · 디럭스"))])

    def test_the_pairing_survives_json_and_the_request_names_the_calendar_room(self):
        snap = decode_snapshot(encode_snapshot(snapshot(SHOWN, adjust_naming(SHOWN))))
        self.assertEqual(snap.room_names, {SHOWN: "샘플 오퍼 · 디럭스"})
        request = ChangeRequest(hotel="데모 호텔", offer="샘플 오퍼", rooms=(SHOWN,), rate_plans=("조식 포함",),
                                dates=("2026-12-24",), operation="amount", value=D("5"))
        plan = plan_change(snap, request)
        self.assertEqual({change.key.room for change in plan.changes}, {SHOWN})
        self.assertIn(CellKey(SHOWN, "조식 포함", "2026-12-24", "A2", 1), {change.key for change in plan.changes})


if __name__ == "__main__":
    unittest.main()
