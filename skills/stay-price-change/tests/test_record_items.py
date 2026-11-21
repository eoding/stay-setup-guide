"""기록 한 줄도 항목이다(X6) — 공유 부분이 가격 칸이 아닌 「이름 붙은 칸이 있는 기록」(부가옵션 가격 줄 · 다음의 부과금 …)을
같은 장부 · 같은 낡음 확인 · 같은 되돌리기로 다룬다.

- 딸린 칸(이름 · 시즌 · 설명 …)이 미리보기 때와 다르면 그 항목은 낡은 것이다. 가격 칸의 모양(딸린 칸 없음)은 그대로다.
- 종류로 연 장부는 그 종류의 번호만 보이고, 다른 종류의 번호는 어느 도우미의 기록인지 대며 거절한다.
- 적용 직전 확인(begin_fresh)은 다른 항목이 하나라도 있으면 시작하지 않는다.
- 기록을 통째로 다시 저장하는 화면에서, 넣지 않은 필드가 저장 뒤 달라졌으면 untouched 가 짚는다.

    python3 -m unittest discover -s tests
"""

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from change_core.answers import answers, reading_time  # noqa: E402
from change_core.items import ItemState, decode_state, encode_state, item_key, stale_items  # noqa: E402
from change_core.ledger import FieldWrite, Ledger, LedgerError, StepPlan, ValueRow  # noqa: E402
from change_core.rules import moved_far  # noqa: E402

D = Decimal
LINE = "addon_price"
KEY = item_key({"addon": "11", "line": "101"})
OTHER_KEY = item_key({"addon": "11", "line": "102"})
CELL = "price_cell"
CELL_KEY = item_key({"room": "디럭스", "rate_plan": "조식", "date": "2026-12-24", "occupancy": "", "nights": 1})
START = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)


def line(sell="20.00", supply="18.00", name="소아 1인", season="7"):
    return ItemState(f"조식 · {name}", "present", {"sell": D(sell), "supply": None if supply is None else D(supply)},
                     {"name": name, "season": season, "description": ""})


class Clock:
    def __init__(self):
        self.at = START

    def __call__(self):
        return self.at


def rows(sell_after=None, supply_after=None):
    """줄 하나의 미리보기 — 판매가를 바꾸고 공급 원가는 그대로 둔다(넣지 않는 필드)."""
    return [ValueRow(LINE, KEY, "조식 · 소아 1인", "sell", "present", D("20.00"), sell_after, action="set" if sell_after else None),
            ValueRow(LINE, KEY, "조식 · 소아 1인", "supply", "present", D("18.00"), supply_after,
                     action="set" if supply_after else None)]


def preview(ledger, item_rows, reading=None):
    return ledger.record_preview(hotel="데모 호텔", hotel_id="1", offer="", currency="USD", sentence="조식 10% 올려줘",
                                 read_at=START.isoformat(), rows=item_rows, reading=reading or {})


STEP = [StepPlan("line", "조식 · 소아 1인", {"line": "101"}, (FieldWrite(LINE, KEY, "sell", D("22.00")),))]


class NamedFieldsTest(unittest.TestCase):
    def test_a_changed_named_field_makes_the_item_stale_even_when_every_amount_is_the_same(self):
        then = {(LINE, KEY): line()}
        self.assertEqual(stale_items(then, {(LINE, KEY): line()}), ())
        moved, = stale_items(then, {(LINE, KEY): line(season="8")})
        self.assertEqual((moved.key, moved.then.others["season"], moved.now.others["season"]), (KEY, "7", "8"))
        self.assertEqual(len(stale_items(then, {(LINE, KEY): line(name="소아 2인")})), 1, "줄 이름이 바뀌어도 낡은 것")

    def test_named_fields_survive_the_round_trip_and_a_cell_keeps_its_old_shape(self):
        state = line(supply=None)
        self.assertEqual(decode_state(encode_state(state)), state)
        cell = ItemState("디럭스 · 조식", "open", {"sell": D("100.00"), "list": None, "supply": None})
        self.assertNotIn("others", encode_state(cell), "딸린 칸이 없는 항목은 예전과 같은 모양으로 적힌다")
        self.assertEqual(decode_state(encode_state(cell)), cell)

    def test_the_thirty_percent_line_is_shared_and_moving_from_zero_crosses_it(self):
        self.assertFalse(moved_far(D("100"), D("130")))
        self.assertTrue(moved_far(D("100"), D("130.01")))
        self.assertTrue(moved_far(D("100"), D("69.99")))
        self.assertTrue(moved_far(D("0"), D("1")))
        self.assertFalse(moved_far(None, D("5")), "새로 넣는 값은 움직임으로 재지 않는다")


class KindLedgerTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "장부.sqlite3"
        self.clock = Clock()

    def tearDown(self):
        self.folder.cleanup()

    def ledger(self, kind=None):
        return Ledger(self.path, now=self.clock, kind=kind)

    def test_each_helper_sees_only_its_kind_and_refuses_the_other_kinds_numbers(self):
        line_id = preview(self.ledger(LINE), rows(D("22.00")))
        cell_id = self.ledger(CELL).record_preview(
            hotel="데모 호텔", hotel_id="1", offer="오퍼", currency="USD", sentence="디럭스 +10", read_at=START.isoformat(),
            rows=[ValueRow(CELL, CELL_KEY, "디럭스", "sell", "open", D("100"), D("110"), action="set")])
        self.assertEqual([entry["id"] for entry in self.ledger(LINE).list_changes()], [line_id])
        self.assertEqual([entry["id"] for entry in self.ledger(CELL).list_changes()], [cell_id])
        self.assertEqual({entry["id"] for entry in self.ledger().list_changes()}, {line_id, cell_id}, "종류 없이 열면 전부")
        with self.assertRaisesRegex(LedgerError, f"{line_id}번은 부가옵션 가격 도우미의 기록입니다"):
            self.ledger(CELL).change(line_id)
        with self.assertRaisesRegex(LedgerError, f"{cell_id}번은 가격 캘린더 도우미의 기록입니다"):
            self.ledger(LINE).recorded_change(cell_id)
        self.assertEqual(self.ledger(LINE).list_changes(cell_id), [])

    def test_a_record_without_item_rows_takes_its_kind_from_the_offer_or_the_change_it_reverses(self):
        """P1 — 목록은 번호마다 그 종류의 도우미가 줄을 만든다. 항목 줄이 없는 번호(넣을 것이 없던 미리보기 · 되돌리기)도 종류가
        있다: 오퍼 칸이 찼으면 가격 캘린더(그 칸은 가격 캘린더 도우미만 채운다), 되돌리기면 되돌리는 번호의 종류. 둘 다 아니면 종류가
        없고, 어느 도우미든 받으며 목록에는 담당자의 말과 함께 종류 없이 나온다."""
        from change_core import files
        line_id = preview(self.ledger(LINE), rows(D("22.00")))
        empty = dict(hotel="데모 호텔", hotel_id="1", currency="USD", read_at=START.isoformat(), rows=[], empty=True)
        back = self.ledger(LINE).record_preview(offer="", sentence="되돌려", reverses=line_id, **empty)
        cell = self.ledger(CELL).record_preview(offer="오퍼", sentence="1/2 디럭스 100 으로", **empty)
        bare = self.ledger(LINE).record_preview(offer="", sentence="조식 10% 올려줘", **empty)
        self.assertEqual({entry["id"]: entry["item_kind"] for entry in self.ledger().list_changes()},
                         {line_id: LINE, back: LINE, cell: CELL, bare: None})
        with self.assertRaisesRegex(LedgerError, f"{back}번은 부가옵션 가격 도우미의 기록입니다"):
            self.ledger(CELL).change(back)
        with self.assertRaisesRegex(LedgerError, f"{cell}번은 가격 캘린더 도우미의 기록입니다"):
            self.ledger(LINE).change(cell)
        self.assertEqual(self.ledger(CELL).change(bare).id, bare, "종류가 없는 번호는 어느 도우미든 받는다")
        self.assertEqual([entry["id"] for entry in self.ledger(CELL).list_changes()], [bare, cell])
        entry, = files.listed(self.ledger(CELL), CELL, lambda ledger, entry: dict(entry, scope="가격 칸 줄"), bare)
        self.assertEqual((entry["scope"], entry["helper"]), ("항목 없음 · 「조식 10% 올려줘」 · 저장할 것 없음", None))

    def test_begin_fresh_starts_nothing_when_a_named_field_moved_and_starts_when_everything_is_the_same(self):
        ledger = self.ledger(LINE)
        change = preview(ledger, rows(D("22.00")))
        then = {(LINE, KEY): line()}
        moved = ledger.begin_fresh(change, STEP, then, {(LINE, KEY): line(season="8")}, read_at=START.isoformat())
        self.assertEqual([item.key for item in moved], [KEY])
        self.assertEqual(ledger.change(change).status, "previewed", "아무것도 시작하지 않았다")
        self.assertEqual(ledger.begin_fresh(change, STEP, then, {(LINE, KEY): line()}, read_at=START.isoformat()), ())
        self.assertEqual(ledger.change(change).status, "applying")
        self.assertEqual(ledger.begin_fresh(change, STEP, then, {(LINE, KEY): line(season="9")}, read_at=START.isoformat()), (),
                         "이미 시작한 번호를 같은 단계로 다시 부르면 견주지 않고 그대로 둔다")

    def test_begin_fresh_refuses_a_reading_older_than_fifteen_minutes(self):
        ledger = self.ledger(LINE)
        change = preview(ledger, rows(D("22.00")))
        self.clock.at = START + timedelta(minutes=16)
        with self.assertRaisesRegex(LedgerError, "16분 전 것입니다"):
            ledger.begin_fresh(change, STEP, {(LINE, KEY): line()}, {(LINE, KEY): line()}, read_at=START.isoformat())

    def test_untouched_names_a_field_the_save_was_to_leave_alone_that_came_back_different(self):
        ledger = self.ledger(LINE)
        change = preview(ledger, rows(D("22.00")) + [
            ValueRow(LINE, OTHER_KEY, "조식 · 소아 2인", "sell", "present", D("30.00")),
            ValueRow(LINE, OTHER_KEY, "조식 · 소아 2인", "supply", "present", D("25.00"))])
        ledger.begin(change, STEP, read_at=START.isoformat())
        ledger.record_step(change, 1, True)
        kept = {(LINE, KEY): line(sell="22.00"), (LINE, OTHER_KEY): line(sell="30.00", supply="25.00", name="소아 2인")}
        self.assertEqual(ledger.verify(change, kept), [])
        self.assertEqual(ledger.untouched(change, kept), [])
        lost = {**kept, (LINE, KEY): line(sell="22.00", supply=None)}
        self.assertEqual(ledger.verify(change, lost), [], "넣은 판매가는 맞다 — verify 만으로는 원가가 사라진 것을 모른다")
        moved, = ledger.untouched(change, lost)
        self.assertEqual((moved.item_key, moved.field, moved.after, moved.seen), (KEY, "supply", D("18.00"), None))
        other = {**kept, (LINE, OTHER_KEY): line(sell="31.00", supply="25.00", name="소아 2인")}
        self.assertEqual(ledger.untouched(change, other), [], "저장하지 않은 줄은 보지 않는다(그 줄이 바뀐 것은 이 저장 탓이 아니다)")


class AnswersTest(unittest.TestCase):
    def test_a_reading_answer_is_one_without_a_step_number_and_the_latest_of_the_same_question_wins(self):
        early = {"op": "readLine", "ok": True, "ask": "a", "doneAt": "2026-11-21T01:00:00Z", "v": 1}
        late = dict(early, doneAt="2026-11-21T01:00:05Z", v=2)
        save = {"op": "applyLine", "no": 1, "ok": True, "ask": "a", "doneAt": "2026-11-21T01:00:09Z"}
        kept, _cut = answers([early, late, save, dict(save)], latest=True)
        self.assertEqual([result.get("v") for result in kept if result["op"] == "readLine"], [2])
        self.assertEqual(sum(result["op"] == "applyLine" for result in kept), 2, "저장 답은 묶지 않는다")

    def test_the_reading_time_is_the_earliest_finish_among_the_reads_the_helper_names(self):
        results = [{"op": "look", "ok": True, "ask": "l", "doneAt": "2026-11-21T00:59:00Z"},
                   {"op": "readLine", "ok": True, "ask": "a", "doneAt": "2026-11-21T01:00:05Z"},
                   {"op": "readLine", "ok": True, "ask": "b", "doneAt": "2026-11-21T01:00:02Z"}]
        self.assertEqual(datetime.fromisoformat(reading_time(results, ("readLine",))),
                         datetime(2026, 11, 21, 1, 0, 2, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
