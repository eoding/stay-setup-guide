"""검토 2 의 장부 쪽 — 「뒤에 넣은 값」은 번호가 아니라 차례로(5 · 6), 되돌리기는 장부가 셈한 임자를 읽는다(5), 저장됐는지의 뜻은
check 와 확인이 같다(1), 저장 안 됨으로 적힌 단계도 칸이 넣은 값이면 check 가 가린다(2).

장부를 시계와 함께 바로 부른다(명령을 거치지 않는다). 항목은 지어낸 칸 둘이다.

    python3 -m unittest discover -s tests
"""

import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from change_core.items import ItemState  # noqa: E402
from change_core.ledger import DB_NAME, FieldWrite, Ledger, StepPlan, ValueRow  # noqa: E402
from change_core.rollback import plan_rollback  # noqa: E402

D = Decimal
KIND, HOTEL, HOTEL_ID, OFFER = "cell", "검토 호텔", "1", "검토 오퍼"
START = datetime.fromisoformat("2026-11-21T10:00:00+09:00")


class Book:
    """장부 하나와 그 시계 · 작은 ERP(칸 → 판매가). 칸은 항목 키 하나에 필드 sell 하나다."""

    def __init__(self, folder: str):
        self.t = START
        self.ledger = Ledger(Path(folder) / DB_NAME, now=lambda: self.t)
        self.erp: dict[str, Decimal] = {}

    def tick(self, seconds: int = 1) -> str:
        self.t += timedelta(seconds=seconds)
        return self.t.isoformat(timespec="seconds")

    def reading(self) -> dict:
        return {(KIND, key): ItemState(key, "open", {"sell": value}) for key, value in self.erp.items()}

    def preview(self, after: dict, reverses=None) -> int:
        read_at = self.tick()
        self.tick()
        rows = [ValueRow(KIND, key, key, "sell", "open", self.erp[key], value, action="set") for key, value in after.items()]
        return self.ledger.record_preview(hotel=HOTEL, hotel_id=HOTEL_ID, offer=OFFER, currency="USD", sentence=f"{len(after)}칸",
                                          read_at=read_at, rows=rows, reverses=reverses)

    def apply(self, number: int, after: dict, saved: bool = True) -> None:
        step = StepPlan("save", "1번째", {"items": sorted(after)}, tuple(FieldWrite(KIND, key, "sell", value) for key, value in after.items()))
        self.ledger.begin(number, [step], read_at=self.tick())
        self.tick()
        self.ledger.record_step(number, 1, saved=saved)
        if saved:
            self.erp.update(after)

    def change(self, after: dict) -> int:
        number = self.preview(after)
        self.apply(number, after)
        return number

    def snapshot(self) -> int:
        return self.ledger.record_snapshot(hotel=HOTEL, hotel_id=HOTEL_ID, offer=OFFER, currency="USD", sentence="지금 상태",
                                           read_at=self.tick(), rows=[ValueRow(KIND, key, key, "sell", "open", value)
                                                                      for key, value in self.erp.items()])

    def rollback_plan(self, number: int):
        return plan_rollback(self.ledger.recorded_change(number), self.ledger.later_writes(number), self.reading(), self.tick())


class BookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.book = Book(self.tmp.name)
        self.book.erp = {"c1": D("100"), "c2": D("200")}

    def tearDown(self):
        self.tmp.cleanup()


class LaterByTimeTest(BookCase):
    """검토 2 의 6 — 미리보기와 그 적용 사이에 적은 지금 상태 저장 뒤의 그 적용은 그 저장 「뒤」에 넣은 값이다."""

    def test_an_apply_after_a_saved_state_taken_between_its_preview_and_its_apply_is_a_later_write(self):
        book = self.book
        first = book.change({"c1": D("150")})
        preview = book.preview({"c1": D("120")})                  # 2번 — 미리보기
        saved = book.snapshot()                                   # 3번 — 「적용」 전에 지금 상태 저장
        book.apply(preview, {"c1": D("120")})                     # 2번을 적용 — 3번 뒤의 일이다
        later = book.ledger.later_writes(saved)
        self.assertEqual([write.change_id for write in later[(KIND, "c1")]], [preview], "번호(2 < 3)가 아니라 차례로 뒤다")
        self.assertEqual(book.ledger.held_at(saved), {(KIND, "c1"): first}, "저장할 때 그 칸은 1번의 값이었다")

    def test_a_change_with_a_larger_number_applied_before_the_rolled_back_change_is_not_later(self):
        book = self.book
        older = book.preview({"c1": D("150")})                    # 1번 미리보기
        newer = book.change({"c1": D("130")})                     # 2번 — 먼저 적용
        book.apply(older, {"c1": D("150")})                       # 1번 — 나중에 적용(2번의 값을 덮음)
        self.assertEqual(book.ledger.later_writes(older), {}, "2번은 1번이 덮기 전에 넣은 값이다")
        self.assertEqual([write.change_id for write in book.ledger.later_writes(newer)[(KIND, "c1")]], [older])


class RollbackReadsTheHolderTest(BookCase):
    """검토 2 의 5 — 뒤 기록이 그 칸을 다시 넣었으면 값이 우연히 같아도 앞 기록을 되돌릴 때 그 칸을 그대로 두고 그 기록을 까닭으로 댄다."""

    def test_a_later_change_that_set_the_same_value_keeps_the_cell_and_is_named(self):
        book = self.book
        first = book.change({"c1": D("150"), "c2": D("250")})
        book.change({"c1": D("120")})
        third = book.change({"c1": D("150")})                     # 우연히 1번과 같은 값
        plan = book.rollback_plan(first)
        self.assertEqual([item.key for item in plan.restored], ["c2"])
        [kept] = plan.kept
        self.assertEqual((kept.key, kept.cause.change_id, kept.cause.sentence), ("c1", third, "1칸"),
                         "3번이 쥔 칸 — 3번이 까닭이다(값으로 보면 1번의 값이라 되돌리던 칸)")
        self.assertIsNotNone(kept.cause.at)

    def test_a_cell_whose_value_differs_still_names_the_later_change(self):
        book = self.book
        first = book.change({"c1": D("150")})
        second = book.change({"c1": D("151")})
        [kept] = book.rollback_plan(first).kept
        self.assertEqual(kept.cause.change_id, second)

    def test_an_undone_rollback_gives_the_cell_back_to_the_first_change(self):
        book = self.book
        first = book.change({"c1": D("150")})
        undo = book.preview({"c1": D("100")}, reverses=first)
        book.apply(undo, {"c1": D("100")})
        redo = book.preview({"c1": D("150")}, reverses=undo)      # 되돌리기를 되돌림 — 1번이 다시 임자
        book.apply(redo, {"c1": D("150")})
        plan = book.rollback_plan(first)
        self.assertEqual(([item.key for item in plan.restored], plan.kept), (["c1"], ()), "다시 산 1번의 칸은 되돌린다")


class CheckSettlesLostAnswersTest(BookCase):
    """검토 2 의 2 — 저장 안 됨으로 적힌 단계 · 아직 적지 않은 단계(누른 답을 잃었다)도 칸이 모두 넣은 값이면 check 가 저장됨으로 적는다."""

    def check(self, number: int):
        book = self.book
        then = {(KIND, key): ItemState(key, "open", {"sell": value}) for key, value in {"c1": D("100"), "c2": D("200")}.items()}
        return book.ledger.check(number, book.reading(), then, book.tick())

    def test_s3_a_step_recorded_as_not_saved_whose_cells_read_as_written_is_settled_as_saved(self):
        book = self.book
        number = book.preview({"c1": D("150")})
        book.apply(number, {"c1": D("150")}, saved=False)
        book.erp["c1"] = D("150")                                 # 장부에는 저장 안 됨, ERP 에는 들어갔다
        report = self.check(number)
        self.assertEqual((report.status, report.steps[0].ledger, report.steps[0].settled), ("applied", "failed", "saved"))
        self.assertEqual(book.rollback_plan(number).restored[0].key, "c1", "저장된 것으로 적혀 되돌릴 수 있다")

    def test_s3_a_step_never_recorded_whose_cells_read_as_written_is_settled_as_saved(self):
        book = self.book
        number = book.preview({"c1": D("150")})
        step = StepPlan("save", "1번째", {"items": ["c1"]}, (FieldWrite(KIND, "c1", "sell", D("150")),))
        book.ledger.begin(number, [step], read_at=book.tick())
        book.erp["c1"] = D("150")                                 # 눌렀고 저장됐는데 답을 적지 못했다
        report = self.check(number)
        self.assertEqual((report.status, report.steps[0].ledger, report.steps[0].settled), ("applied", "pending", "saved"))

    def test_a_not_saved_step_whose_cells_read_as_before_stays_not_saved(self):
        book = self.book
        number = book.preview({"c1": D("150")})
        book.apply(number, {"c1": D("150")}, saved=False)
        report = self.check(number)
        self.assertEqual((report.steps[0].settled, report.can_continue), (None, True))


if __name__ == "__main__":
    unittest.main()
