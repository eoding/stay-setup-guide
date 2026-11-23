"""K4 · K5 — 말과 페이지: 확인받는 한 줄(`line`), 답 파일 뒤에 도구가 붙인 글, `render --text` 의 제목, 통화에 맞는 말 보기.
세 도우미가 같은 코드(change_core)를 쓴다.

    python3 -m unittest discover -s tests
"""

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import scene  # noqa: E402
from change_core.chrome import page_text  # noqa: E402
from change_core.files import confirm_line, load_results  # noqa: E402
from change_core.money import example_step  # noqa: E402
from change_core.ledger import DB_NAME, Ledger  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from price_change import listed  # noqa: E402
from price_model import encode_request  # noqa: E402
from price_pages import render_prices  # noqa: E402
from price_plan import (  # noqa: E402
    cell_filter, plan_cell_rollback, plan_change, plan_steps, preview_rows, resolve, rollback_rows, rollback_writes, save_steps,
    step_plans,
)


class ConfirmLineTest(unittest.TestCase):
    def entry(self, **over):
        return dict(dict(id=7, kind="change", status="applied", read_at="2026-11-21T09:30:00+09:00",
                         created_at="2026-11-21T09:40:00+09:00", applied_at="2026-11-21T09:45:00+09:00", scope="디럭스 · 판매가 +10%"),
                    **over)

    def test_a_change_says_when_it_was_applied_and_a_saved_state_when_its_values_were_read(self):
        self.assertEqual(confirm_line(self.entry()), "장부 7번 · 11/21 09:45 적용 · 디럭스 · 판매가 +10%")
        self.assertEqual(confirm_line(self.entry(kind="snapshot", status="saved", applied_at=None)),
                         "장부 7번 · 11/21 09:30 저장 · 디럭스 · 판매가 +10%")
        self.assertEqual(confirm_line(self.entry(status="previewed", applied_at=None)), "장부 7번 · 11/21 09:40 미리보기 · 디럭스 · 판매가 +10%")
        self.assertEqual(confirm_line(self.entry(status="stopped", applied_at=None, begun_at="2026-11-21T09:43:00+09:00")),
                         "장부 7번 · 11/21 09:43 적용하다 멈춤 · 디럭스 · 판매가 +10%", "멈춘 변경은 적용을 시작한 때")
        self.assertEqual(confirm_line(self.entry(status="applying", applied_at=None, begun_at="2026-11-21T09:43:00+09:00")),
                         "장부 7번 · 11/21 09:43 적용 중 · 디럭스 · 판매가 +10%")
        self.assertEqual(confirm_line(self.entry(status="stopped", applied_at=None, begun_at=None)),
                         "장부 7번 · 11/21 09:40 적용하다 멈춤 · 디럭스 · 판매가 +10%", "시작한 때를 적기 전의 장부")



class StoppedThenUndoneLineTest(unittest.TestCase):
    """F4 — 저장 하나를 넣고 멈춘 변경을 뒤에 되돌려도 목록의 줄은 「미리보기」가 아니다. ERP 에 칸을 넣었던 변경이라 되돌리기 전의
    말과 시각(「적용하다 멈춤」, 시작한 때) 그대로이고, 끝에 되돌린 만큼이 붙는다. 다 적용한 뒤 되돌린 변경은 「적용」 그대로다.
    시운전 8 F2 — 그 시각은 적용을 시작한 때(begin)다. 미리보기는 10:00, 적용 시작은 10:03, 첫 저장은 10:04 에 한다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.at = scene.NOW
        self.ledger = Ledger(Path(self.tmp.name) / DB_NAME, now=lambda: self.at)
        self.before = scene.snapshot()
        plan = resolve(plan_change(self.before, scene.request()), [Resolution("ABOVE_LIST", "raise_list")])
        self.steps = plan_steps(plan)
        self.change = self.ledger.record_preview(hotel=scene.HOTEL, hotel_id=scene.HOTEL_ID, offer=scene.OFFER, currency="USD",
                                                 sentence=scene.SENTENCE, read_at=plan.read_at, rows=preview_rows(plan),
                                                 request=encode_request(plan.request))
        self.at = scene.NOW + timedelta(minutes=3)
        self.ledger.begin(self.change, step_plans(self.steps), read_at=scene.READ_AGAIN)
        self.at = scene.NOW + timedelta(minutes=4)

    def tearDown(self):
        self.tmp.cleanup()

    def line(self, change_id):
        return confirm_line(listed(self.ledger, change_id)[0])

    def undo(self, saved, **choose):
        """저장된 단계(`saved` 번까지)의 칸 가운데 고른 칸을 되돌리는 되돌리기를 적용한다."""
        select, _scope = cell_filter(**choose)
        now = scene.applied(self.before, self.steps[:saved], "2026-11-25T09:00:00+09:00")
        rollback = plan_cell_rollback(self.ledger.recorded_change(self.change), self.ledger.later_writes(self.change), now,
                                      select=select)
        rid = self.ledger.record_preview(hotel=rollback.hotel, hotel_id=rollback.hotel_id, offer=rollback.offer,
                                         currency=rollback.currency, sentence="되돌려", read_at=rollback.read_at,
                                         rows=rollback_rows(rollback), reverses=self.change)
        steps = save_steps(rollback_writes(rollback))
        self.ledger.begin(rid, step_plans(steps), read_at=scene.read_after(rollback.read_at))
        for index in range(1, len(steps) + 1):
            self.ledger.record_step(rid, index, saved=True)
        return rid

    def test_a_stopped_change_keeps_its_word_and_time_after_a_partial_and_then_a_full_rollback(self):
        self.ledger.record_step(self.change, 1, saved=True)
        self.ledger.record_step(self.change, 2, saved=False, note="드로어 표에 없는 줄")
        stopped = self.line(self.change)
        head = stopped.split(" · 객실 가격 · ")[0]
        self.assertEqual(head, f"장부 {self.change}번 · 11/21 10:03 적용하다 멈춤", "미리보기(10:00)가 아니라 적용을 시작한 때")
        self.assertTrue(stopped.endswith("저장 8번 중 1번 하고 멈춤"), stopped)
        first = self.undo(1, occupancies=["A2"])
        partly = self.line(self.change)
        self.assertEqual(partly.split(" · 객실 가격 · ")[0], head, "일부 되돌린 뒤에도 같은 말과 시각")
        self.assertIn(f"일부 되돌림 4/12칸 (장부 {first}번)", partly)
        second = self.undo(1)
        undone = self.line(self.change)
        self.assertEqual(undone.split(" · 객실 가격 · ")[0], head, "모두 되돌린 뒤에도 「미리보기」가 아니다")
        self.assertIn(f"모두 되돌림 12/12칸 (장부 {first}번, {second}번)", undone)
        self.assertEqual(listed(self.ledger, self.change)[0]["status"], "rolled_back")

    def test_an_applied_then_rolled_back_change_keeps_applied(self):
        for index in range(1, len(self.steps) + 1):
            self.ledger.record_step(self.change, index, saved=True)
        applied = self.line(self.change).split(" · 객실 가격 · ")[0]
        self.undo(len(self.steps))
        self.assertEqual(self.line(self.change).split(" · 객실 가격 · ")[0], applied)
        self.assertTrue(applied.endswith(" 적용"), applied)

class AnswerFileTest(unittest.TestCase):
    def test_only_the_operation_s_answer_is_read_from_a_file_the_tool_added_text_to(self):
        answer = {"ok": True, "op": "look", "hotel": {"id": "1", "name": "데모 호텔"}}
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "look-1.json").write_text(json.dumps(answer, ensure_ascii=False) + "\n\nTabs:\n- 데모 호텔 · ERP (현재 탭)\n",
                                                      encoding="utf-8")
            (Path(folder) / "look-2.json").write_text('{"ok": true, "op": "look", "body": {"id": "b1", "cha[TRUNCATED]',
                                                      encoding="utf-8")
            whole, cut = load_results([folder], ("look-",))
        self.assertEqual(dict(whole), answer, "닫힌 JSON 뒤의 탭 목록은 답이 아니다")
        self.assertIsInstance(cut, str, "닫히지 않은 답은 잘린 답 그대로 남는다")


class PageWordsTest(unittest.TestCase):
    def test_render_text_prints_the_title_once_and_the_example_fits_the_currency(self):
        usd = page_text(render_prices(scene.snapshot()))
        lines = usd.splitlines()
        self.assertEqual(lines.count(lines[0]), 1, "제목은 한 번")
        self.assertIn('"12월 디럭스 +10"', usd)
        self.assertNotIn("+10,000", usd, "달러 호텔에 +10,000 을 보기로 들지 않는다")
        krw = page_text(render_prices(replace(scene.snapshot(), currency="KRW")))
        self.assertIn('"12월 디럭스 +10,000"', krw)
        self.assertEqual([example_step(code) for code in ("USD", "EUR", "KRW", "VND", "JPY", "THB")],
                         ["10", "10", "10,000", "100,000", "1,000", "10"])


if __name__ == "__main__":
    unittest.main()
