"""HTML 페이지 — 담당자가 읽는 글과 숫자가 맞는지, 파일 하나로 열리는지, 이름 속 꺾쇠가 글자로만 보이는지.

    python3 -m unittest discover -s tests
"""

import html
import re
import sys
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import scene  # noqa: E402
from change_core.ledger import DB_NAME, Ledger  # noqa: E402
from change_core.rollback import LaterWrite, RecordedChange, RecordedItem  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from price_model import (  # noqa: E402
    ITEM_KIND, CellKey, CellValue, ChangeRequest, Snapshot, cell_item_key, cell_name, encode_request, snapshot_reading,
)
from price_pages import render_prices, render_preview, render_result, render_rollback  # noqa: E402
from price_plan import plan_cell_rollback, plan_change, preview_rows, resolve, save_steps, step_plans  # noqa: E402

D = Decimal


def visible(page: str) -> str:
    page = re.sub(r"<style>.*?</style>", " ", page, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


class SelfContainedMixin:
    def assert_self_contained(self, page):
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn("prefers-color-scheme: dark", page)
        self.assertNotRegex(page, r"(src|href)=|https?://|@import")


class PreviewPageTest(SelfContainedMixin, unittest.TestCase):
    def test_scene_preview_shows_counts_banners_marks_and_cells(self):
        plan = plan_change(scene.snapshot(), scene.request())
        page = render_preview(plan, change_id=3, steps=8)
        text = visible(page)
        self.assert_self_contained(page)
        self.assertIn("미리보기 · 데모 호텔 · 기본 오퍼 · 판매가 +10%", text)
        self.assertIn("아직 아무것도 바뀌지 않았습니다. 지금 값은 2026-11-20 14:02 에 ERP 에서 읽은 것입니다 (장부 3번에 적어 두었습니다)",
                      text)
        for number, label in ((90, "바뀌는 칸"), (2, "빨간 줄"), (0, "적용할 수 없는 칸"), (24, "예약 있는 날의 칸"),
                              (6, "판매 마감인 칸"), (6, "가격이 없어 건너뛰는 칸")):
            self.assertIn(f"{number} {label}", text)
        self.assertIn("빨간 줄 · 2칸이 정가(줄 그은 값)를 넘습니다.", text)
        self.assertIn("정가도 같은 만큼 올림 / 이 칸은 안 바꿈", text)
        self.assertIn("ERP 에 8번 나눠 저장합니다", text)
        for heading in ("디럭스 · 조식 포함", "디럭스 · 룸온리", "스위트 · 조식 포함", "스위트 · 룸온리"):
            self.assertIn(heading, text)
        self.assertIn("12/26 토 판매 마감", text)
        self.assertIn("12/25 금 예약 있는 날", text)
        self.assertIn("339.95 → 373.95", text)
        self.assertIn("230.00 → 250.00", text)
        self.assertIn("480.00 → 528.00 정가 500.00 넘음", text)
        self.assertIn("따로 확인할 칸", text)
        self.assertIn("1/1 금 · 스위트 · 조식 포함 · 성인 2 · 1박", text)
        self.assertIn("성인 몫에만 곱하고 아동 추가분은 그대로", text)
        self.assertIn("성인 2 + 아동 1 · 3박 이상", text)

    def test_a_hundred_percent_puts_red_banners_up_without_double_counting(self):
        text = visible(render_preview(plan_change(scene.snapshot(), scene.request("100"))))
        self.assertIn("빨간 줄 · 88칸이 지금 값보다 30% 넘게 바뀝니다.", text)
        self.assertIn("빨간 줄 · 2칸이 정가(줄 그은 값)를 넘습니다.", text)
        self.assertIn("90 빨간 줄", text)

    def test_blocked_cells_are_set_apart(self):
        snapshot = Snapshot("H", "O", "KRW", "2026-11-20T10:00:00+09:00",
                            {CellKey("R", "P", "2026-12-25", "A2", 1): CellValue(D("50000"), None, None, "open"),
                             CellKey("R", "P", "2026-12-25", "A3", 1): CellValue(D("90000"), None, None, "open")},
                            frozenset())
        plan = plan_change(snapshot, ChangeRequest("H", "O", ("R",), ("P",), ("2026-12-25",), "amount", D("-60000")))
        text = visible(render_preview(plan))
        self.assertIn("적용할 수 없음 · 1칸 ERP 가 받지 않는 값이라 이 칸은 바꾸지 않습니다. (0 이하가 됩니다 1칸)", text)
        self.assertIn("50,000 적용할 수 없음", text)
        self.assertIn("90,000 → 30,000 30% 넘음", text)
        self.assertIn("판매가 -60,000 KRW", text)

    def test_names_are_shown_as_text_not_markup(self):
        snapshot = scene.snapshot()
        snapshot = Snapshot("<b>호텔</b>", snapshot.offer, snapshot.currency, snapshot.read_at, snapshot.cells,
                            snapshot.reserved)
        page = render_preview(plan_change(snapshot, scene.request(hotel="<b>호텔</b>")))
        self.assertNotIn("<b>호텔</b>", page)
        self.assertIn("&lt;b&gt;호텔&lt;/b&gt;", page)


class ResultPageTest(SelfContainedMixin, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / DB_NAME)
        self.before = scene.snapshot()
        plan = plan_change(self.before, scene.request())
        self.steps = save_steps(resolve(plan, [Resolution("ABOVE_LIST", "raise_list")])[0])
        self.id = self.ledger.record_preview(hotel=scene.HOTEL, offer=scene.OFFER, currency="USD", sentence=scene.SENTENCE,
                                             read_at=plan.read_at, rows=preview_rows(plan),
                                             request=encode_request(plan.request))
        self.ledger.begin(self.id, step_plans(self.steps))

    def tearDown(self):
        self.tmp.cleanup()

    def test_stopped_change_shows_where_it_stopped_and_the_three_choices(self):
        for index in range(1, 6):
            self.ledger.record_step(self.id, index, saved=True)
        self.ledger.record_step(self.id, 6, saved=False, note="ERP 로그인이 풀린 것으로 보입니다")
        page = render_result(self.ledger.change(self.id))
        text = visible(page)
        self.assert_self_contained(page)
        self.assertIn("6번째 저장에서 멈췄습니다. 지금은 일부만 바뀐 상태입니다. (ERP 로그인이 풀린 것으로 보입니다)", text)
        self.assertIn("1. 디럭스 · 조식 포함 · 12/25 금 ~ 12/26 토 (2일, 2026년) 저장함", text)
        self.assertIn("6. 스위트 · 조식 포함 · 1/1 금 ~ 1/2 토 (2일, 2027년) 여기서 멈춤 · 바뀌지 않음", text)
        self.assertIn("8. 스위트 · 룸온리 · 1/1 금 (1일, 2027년) 아직 안 함", text)
        self.assertIn("이어서 — 남은 3번을", text)
        self.assertIn("된 것까지 되돌리기 — 이미 바뀐 5번을", text)
        self.assertIn("이대로 두기", text)

    def test_applied_and_verified_and_a_mismatch(self):
        for index in range(1, 9):
            self.ledger.record_step(self.id, index, saved=True)
        after = scene.applied(self.before, self.steps)
        self.ledger.verify(self.id, snapshot_reading(after))
        text = visible(render_result(self.ledger.change(self.id), ledger_path="/기록/가격장부.sqlite3"))
        self.assertIn("적용했고, 다시 읽어 확인했습니다. 90칸 모두 넣은 값과 같습니다.", text)
        self.assertIn("기록: /기록/가격장부.sqlite3", text)
        self.assertIn("480.00 → 528.00 정가 500.00 → 548.00 확인", text)
        odd = CellKey("디럭스", "조식 포함", "2026-12-25", "A2", 1)
        self.ledger.verify(self.id, snapshot_reading(scene.with_cells(after, {odd: replace(after.cells[odd], sell=D("1.00"))})))
        text = visible(render_result(self.ledger.change(self.id)))
        self.assertIn("적용했지만, 다시 읽었더니 1칸이 넣은 값과 다릅니다.", text)
        self.assertIn("200.00 → 220.00 다시 읽은 값 판매가 1.00", text)


class RollbackPageTest(SelfContainedMixin, unittest.TestCase):
    def test_restore_date_kept_cells_with_three_values_and_cause_and_restored_cells(self):
        a, b, c = (CellKey("디럭스", "룸온리", day, "A2", 1) for day in ("2027-01-01", "2027-01-02", "2026-12-25"))

        def item(key, before, after):
            return RecordedItem(ITEM_KIND, cell_item_key(key), cell_name(key), "open",
                                dict(sell=D(before), list=None, supply=None), dict(sell=D(after)))

        recorded = RecordedChange(4, "change", "데모 호텔", "기본 오퍼", "USD", scene.SENTENCE, "2026-11-20T14:02:00+09:00",
                                  "2026-11-20T14:05:00+09:00",
                                  (item(a, "480.00", "528.00"), item(b, "270.00", "297.00"), item(c, "170.00", "187.00")))
        later = {(ITEM_KIND, cell_item_key(b)): [LaterWrite(6, "2026-11-24T10:30:00+09:00", "1/2 디럭스 룸온리 310 으로",
                                                            dict(sell=D("310.00")))]}
        now = Snapshot("데모 호텔", "기본 오퍼", "USD", "2026-11-27T09:00:00+09:00", {
            a: CellValue(D("550.00"), None, None, "open"), b: CellValue(D("310.00"), None, None, "open"),
            c: CellValue(D("187.00"), None, None, "open")}, frozenset({("디럭스", "2026-12-25")}))
        page = render_rollback(plan_cell_rollback(recorded, later, now), now.reserved)
        text = visible(page)
        self.assert_self_contained(page)
        self.assertIn("2026-11-20 14:02 에 적어 둔 값으로 되돌립니다.", text)
        self.assertIn(f"그때 한 일: “{scene.SENTENCE}” (2026-11-20 14:05 적용, 장부 4번)", text)
        self.assertIn("1 되돌리는 칸 2 그대로 두는 칸 1 되돌리는 칸 중 예약 있는 날", text)
        self.assertIn("1/1 금 · 디럭스 · 룸온리 · 성인 2 · 1박 판매가 480.00 판매가 528.00 판매가 550.00 도우미 밖에서 바뀜",
                      text)
        self.assertIn("1/2 토 · 디럭스 · 룸온리 · 성인 2 · 1박 판매가 270.00 판매가 297.00 판매가 310.00 이 컴퓨터의 다른 변경 "
                      "(2026-11-24 10:30 “1/2 디럭스 룸온리 310 으로”, 장부 6번)", text)
        self.assertIn("12/25 금 예약 있는 날", text)
        self.assertIn("187.00 → 170.00", text)
        self.assertIn("550.00 그대로 둠", text)
        self.assertIn('그 사이 달라진 2칸도 되돌리려면 "2칸도 포함해서 되돌려"', text)


class PricesPageTest(SelfContainedMixin, unittest.TestCase):
    def test_plain_view_changes_nothing_and_shows_list_and_missing(self):
        page = render_prices(scene.snapshot())
        text = visible(page)
        self.assert_self_contained(page)
        self.assertIn("지금 가격 · 데모 호텔 · 기본 오퍼", text)
        self.assertIn("아무것도 바꾸지 않았습니다.", text)
        self.assertIn("90 가격 있는 칸 6 판매 마감인 칸 6 가격 없는 칸 2 예약 있는 날", text)
        self.assertIn("480.00 정가 500.00", text)
        self.assertIn("가격 없음", text)


if __name__ == "__main__":
    unittest.main()
