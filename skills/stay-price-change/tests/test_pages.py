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
import trial_scene  # noqa: E402
from change_core.ledger import DB_NAME, Ledger  # noqa: E402
from change_core.rollback import LaterWrite, RecordedChange, RecordedItem  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from price_model import (  # noqa: E402
    ITEM_KIND, CellKey, CellValue, ChangeRequest, Snapshot, cell_item_key, cell_name, encode_request, snapshot_reading,
)
from price_pages import render_prices, render_preview, render_result, render_rollback  # noqa: E402
from price_plan import plan_cell_rollback, plan_change, plan_steps, preview_rows, resolve, step_plans, unresolved  # noqa: E402

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
        page = render_preview(plan, change_id=3)
        text = visible(page)
        self.assert_self_contained(page)
        self.assertIn("미리보기 · 데모 호텔 · 기본 오퍼 · 판매가 +10%", text)
        self.assertIn("아직 아무것도 바뀌지 않았습니다. 지금 값은 2026-11-20 14:02 에 ERP 에서 읽은 것입니다 (장부 3번에 적어 두었습니다)",
                      text)
        for number, label in ((90, "바뀌는 칸"), (2, "빨간 줄 (고르기 전)"), (0, "적용할 수 없는 칸"), (24, "예약 있는 날의 칸"),
                              (6, "판매 마감인 칸"), (6, "건너뛰는 칸")):
            self.assertIn(f"{number} {label}", text)
        self.assertNotIn("고른 빨간 줄", text)
        self.assertIn("빨간 줄 · 2칸이 정가(줄 그은 값)를 넘습니다.", text)
        self.assertIn("이 칸은 골라 주세요: 정가도 10% 올림 (예: 1/1 금 · 스위트 · 조식 포함 · 성인 2 · 1박 이상 — 정가 500.00 → 550.00) / "
                      "정가 지움 / 그 칸은 안 바꿈.", text, "Y1 — 고를 것이 정가가 어떻게 되는지 숫자로 말한다")
        self.assertIn("정가도 10% 올림: 500.00 → 550.00 / 정가 지움 / 그 칸은 안 바꿈", text, "칸마다 그 칸의 숫자")
        self.assertIn("빨간 줄 2칸을 어떻게 할지 고르시면 ERP 에 몇 번 나눠 저장하는지 정해집니다", text, "V4 — 고르기 전에는 저장 횟수가 없다")
        self.assertNotIn("나눠 저장합니다", text)
        self.assertIn("건너뛰는 칸의 까닭: 가격 없음 6칸", text)
        for heading in ("디럭스 · 조식 포함", "디럭스 · 룸온리", "스위트 · 조식 포함", "스위트 · 룸온리"):
            self.assertIn(heading, text)
        self.assertIn("12/26 토 판매 마감", text)
        self.assertIn("12/25 금 예약 있는 날", text)
        self.assertIn("339.95 → 373.95", text)
        self.assertIn("230.00 → 250.00", text)
        self.assertIn("480.00 → 528.00 정가 500.00 넘음", text)
        self.assertIn("따로 확인할 칸", text)
        self.assertIn("1/1 금 · 스위트 · 조식 포함 · 성인 2 · 1박 이상", text)
        self.assertIn("성인 몫에만 곱하고 아동 추가분은 그대로", text)
        self.assertIn("성인 2 + 아동 1 · 3박 이상", text)

    def test_v1_after_choosing_the_preview_shows_the_choice_and_the_list_price_it_will_write(self):
        plan = resolve(plan_change(scene.snapshot(), scene.request()), [Resolution("ABOVE_LIST", "raise_list")])
        text = visible(render_preview(plan, change_id=4, steps=plan_steps(plan)))
        for number, label in ((90, "바뀌는 칸"), (0, "빨간 줄 (고르기 전)"), (2, "고른 빨간 줄")):
            self.assertIn(f"{number} {label}", text)
        self.assertNotIn("골라 주세요", text)
        self.assertNotIn("넘음", text, "고른 칸은 「정가 넘음」이 아니라 고른 것으로 보인다")
        self.assertIn("고르신 빨간 줄 · 2칸 (계산한 값이 정가를 넘던 칸) 정가도 10% 올림 · 2칸 정가도 그렇게 옮겨 저장합니다(ERP 「정가도 같이 조정」과 같은 계산). "
                      "예: 1/1 금 · 스위트 · 조식 포함 · 성인 2 · 1박 이상 — 판매가 480.00 → 528.00 정가 500.00 → 550.00", text)
        self.assertIn("480.00 → 528.00 정가 500.00 → 550.00 정가도 10% 올림 ", text, "Y4 — 칸은 고른 것과 그 결과만")
        self.assertIn("500.00 → 550.00 없음 고름 정가도 10% 올림 고르신 대로 저장합니다", text)
        self.assertNotIn("정가보다 비싸집니다", text, "Y4 — 고른 뒤에는 일어나지 않을 일을 쓰지 않는다")
        self.assertIn("남은 빨간 줄이 없습니다. 고르신 대로 저장합니다.", text)
        self.assertIn("ERP 에 8번 나눠 저장합니다", text)
        self.assertIn("객실 · 요금제마다 값이 같은 날을 묶어 한 번 — 날이 떨어져 있어도 한 번", text, "T7 — 저장 묶음을 말하는 글")
        self.assertIn("다만 고르신 대로 2칸은 정가도 같이 바뀝니다", text)

        kept = resolve(plan_change(scene.snapshot(), scene.request()), [Resolution("ABOVE_LIST", "keep")])
        text = visible(render_preview(kept, steps=plan_steps(kept)))
        self.assertIn("88 바뀌는 칸", text, "안 바꾸기로 고른 칸은 바뀌는 칸에서 빠진다")
        self.assertIn("480.00 그대로 그 칸은 안 바꿈", text)
        self.assertNotIn("480.00 → 528.00", text)

    def test_y3_the_preview_ends_with_what_is_needed_first_and_never_invites_apply_while_a_choice_is_open(self):
        def ending(plan):
            return visible(render_preview(plan, steps=plan_steps(plan))).rsplit("아동이 있는 칸", 1)[-1]

        fresh = plan_change(scene.snapshot(), scene.request())
        self.assertTrue(unresolved(fresh))
        text = visible(render_preview(fresh))
        self.assertNotIn("이라고 하시면 바꿉니다", text, "고를 빨간 줄이 남은 미리보기는 적용을 청하지 않는다")
        self.assertTrue(text.endswith("아직 적용할 수 없습니다. 먼저 빨간 줄 2칸을 어떻게 할지 대화창에서 말씀해 주세요"
                                      "(고를 것은 위의 빨간 띠에 있습니다). 고르시면 미리보기를 다시 보여 드립니다. "
                                      "어딩 Stay 가격 변경 도우미가 만든 페이지입니다."), text[-200:])
        chosen = resolve(fresh, [Resolution("ABOVE_LIST", "raise_list")])
        self.assertIn('대화창에서 "적용"이라고 하시면 바꿉니다.', ending(chosen), "다 고르면 그때 적용을 청한다")
        nothing = resolve(plan_change(scene.snapshot(), scene.request(rooms=("스위트",), rate_plans=("조식 포함",),
                                                                      dates=("2027-01-01",), occupancies=("A2",), nights=(1,))),
                          [Resolution("ABOVE_LIST", "keep")])
        self.assertIn("바꿀 칸이 없어 적용할 것이 없습니다.", ending(nothing))
        self.assertNotIn("이라고 하시면 바꿉니다", ending(nothing))

    def test_v5_notes_about_reserved_and_closed_days_only_when_the_plan_has_such_cells(self):
        whole = visible(render_preview(plan_change(scene.snapshot(), scene.request())))
        for words in ("예약 있는 날도 똑같이 바꿉니다", "판매 마감인 날은 값만 바뀌고", "예약 있는 날의 칸", "판매 마감인 칸"):
            self.assertIn(words, whole)
        plain = visible(render_preview(plan_change(scene.snapshot(), scene.request(rooms=("스위트",), rate_plans=("룸온리",),
                                                                                    dates=("2026-12-25",)))))
        for words in ("예약 있는 날도 똑같이 바꿉니다", "판매 마감인 날은 값만 바뀌고", "예약 있는 날의 칸", "판매 마감인 칸"):
            self.assertNotIn(words, plain)
        trial = visible(render_preview(plan_change(trial_scene.snapshot(), trial_scene.request())))
        self.assertIn("예약 있는 날도 똑같이 바꿉니다", trial)
        self.assertNotIn("판매 마감", trial, "시운전의 모양에는 마감 칸이 없다")

    def test_a_hundred_percent_puts_red_banners_up_without_double_counting(self):
        text = visible(render_preview(plan_change(scene.snapshot(), scene.request("100"))))
        self.assertIn("빨간 줄 · 88칸이 지금 값보다 30% 넘게 바뀝니다.", text)
        self.assertIn("빨간 줄 · 2칸이 정가(줄 그은 값)를 넘습니다.", text)
        self.assertIn("90 빨간 줄", text)

    def test_blocked_cells_are_set_apart(self):
        snapshot = Snapshot("H", "O", "KRW", "2026-11-20T10:00:00+09:00",
                            {CellKey("R", "P", "2026-12-25", "A2", 1): CellValue(D("50000"), None, None, "open"),
                             CellKey("R", "P", "2026-12-25", "A3", 1): CellValue(D("90000"), None, None, "open")},
                            frozenset(), frozenset({("R", "P")}))
        plan = plan_change(snapshot, ChangeRequest("H", "O", ("R",), ("P",), ("2026-12-25",), "amount", D("-60000")))
        text = visible(render_preview(plan))
        self.assertIn("적용할 수 없음 · 1칸 ERP 가 받지 않는 값이라 이 칸은 바꾸지 않습니다. (0 이하가 됩니다 1칸)", text)
        self.assertIn("50,000 적용할 수 없음", text)
        self.assertIn("90,000 → 30,000 30% 넘음", text)
        self.assertIn("판매가 -60,000 KRW", text)

    def test_a_pair_read_without_prices_is_named(self):
        snapshot = scene.snapshot()
        snapshot = replace(snapshot, pairs=snapshot.pairs | {("디럭스", "반값 요금"), ("스위트", "반값 요금")})
        plan = plan_change(snapshot, scene.request(rate_plans=("조식 포함", "룸온리", "반값 요금")))
        self.assertIn("읽었지만 가격이 하나도 없어 건너뛰는 객실·요금제: 디럭스 · 반값 요금, 스위트 · 반값 요금",
                      visible(render_preview(plan)))

    def test_list_and_supply_changes_are_shown_when_they_change(self):
        listed = plan_change(scene.snapshot(), scene.request(operation="amount", value=D("20"), field="list",
                                                             rooms=("스위트",), rate_plans=("조식 포함",)))
        text = visible(render_preview(listed))
        self.assertIn("미리보기 · 데모 호텔 · 기본 오퍼 · 정가 +20.00 USD", text)
        self.assertIn("정가 500.00 → 520.00", text)
        self.assertIn("판매가와 공급 원가는 바꾸지 않습니다", text)
        cleared = plan_change(scene.snapshot(), scene.request(operation="clear", value=None, field="list",
                                                              rooms=("스위트",), rate_plans=("조식 포함",)))
        text = visible(render_preview(cleared, steps=plan_steps(cleared)))
        self.assertIn("정가 500.00 → 비움", text)
        self.assertIn("그중 정가·원가를 비우는 셀 창 저장 2번", text)

    def test_names_are_shown_as_text_not_markup(self):
        snapshot = scene.snapshot()
        snapshot = replace(snapshot, hotel="<b>호텔</b>")
        page = render_preview(plan_change(snapshot, scene.request(hotel="<b>호텔</b>")))
        self.assertNotIn("<b>호텔</b>", page)
        self.assertIn("&lt;b&gt;호텔&lt;/b&gt;", page)


class ResultPageTest(SelfContainedMixin, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / DB_NAME, now=scene.clock)
        self.before = scene.snapshot()
        plan = resolve(plan_change(self.before, scene.request()), [Resolution("ABOVE_LIST", "raise_list")])
        self.steps = plan_steps(plan)
        self.id = self.ledger.record_preview(hotel=scene.HOTEL, hotel_id=scene.HOTEL_ID, offer=scene.OFFER, currency="USD", sentence=scene.SENTENCE,
                                             read_at=plan.read_at, rows=preview_rows(plan),
                                             request=encode_request(plan.request))
        self.ledger.begin(self.id, step_plans(self.steps), read_at=scene.NOW_TEXT)

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
        self.assertIn("1. 디럭스 · 조식 포함 · 12/25 금 ~ 12/26 토 (2일, 2026년) · 12칸 저장함", text)
        self.assertIn("6. 스위트 · 조식 포함 · 1/1 금 ~ 1/2 토 (2일, 2027년) · 12칸 여기서 멈춤 · 바뀌지 않음", text)
        self.assertIn("8. 스위트 · 룸온리 · 1/1 금 (1일, 2027년) · 6칸 아직 안 함", text)
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
        self.assertIn("480.00 → 528.00 정가 500.00 → 550.00 확인", text)
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
            c: CellValue(D("187.00"), None, None, "open")}, frozenset({("디럭스", "2026-12-25")}),
            frozenset({("디럭스", "룸온리")}))
        page = render_rollback(plan_cell_rollback(recorded, later, now), now.reserved)
        text = visible(page)
        self.assert_self_contained(page)
        self.assertIn("2026-11-20 14:02 에 적어 둔 값으로 되돌립니다.", text)
        self.assertIn(f"그때 한 일: “{scene.SENTENCE}” (2026-11-20 14:05 적용, 장부 4번)", text)
        self.assertIn("1 되돌리는 칸 2 그대로 두는 칸 0 지울 수 없는 칸 1 되돌리는 칸 중 예약 있는 날", text)
        self.assertIn("1/1 금 · 디럭스 · 룸온리 · 성인 2 · 1박 이상 판매가 480.00 판매가 528.00 판매가 550.00 도우미 밖에서 바뀜",
                      text)
        self.assertIn("1/2 토 · 디럭스 · 룸온리 · 성인 2 · 1박 이상 판매가 270.00 판매가 297.00 판매가 310.00 이 컴퓨터의 다른 변경 "
                      "(2026-11-24 10:30 “1/2 디럭스 룸온리 310 으로”, 장부 6번)", text)
        self.assertIn("12/25 금 예약 있는 날", text)
        self.assertIn("187.00 → 170.00", text)
        self.assertIn("550.00 그대로 둠", text)
        self.assertIn('그 사이 달라진 2칸도 되돌리려면 "2칸도 포함해서 되돌려"', text)
        self.assertIn('"되돌려"라고 하시면 1칸을 되돌립니다.', text)

        moved = replace(now, cells={**now.cells, c: CellValue(D("190.00"), None, None, "open")})
        nothing = visible(render_rollback(plan_cell_rollback(recorded, later, moved), moved.reserved))
        self.assertIn("되돌릴 칸이 없어 되돌릴 것이 없습니다. 아무것도 바뀌지 않았습니다.", nothing)
        self.assertNotIn('"되돌려"라고 하시면', nothing, "되돌릴 칸이 없으면 0칸을 되돌리자고 청하지 않는다")
        self.assertIn('그 사이 달라진 3칸도 되돌리려면 "3칸도 포함해서 되돌려"', nothing)


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
