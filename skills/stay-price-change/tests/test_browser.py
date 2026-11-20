"""브라우저 쪽과 주고받는 모양 — 읽기 부를 값(B5), 예약 있는 날 물음을 숨긴 줄이 없을 때까지 좁히기(B6), 저장 단계 → 부를 값과
답 → 장부 메모(B7).

    python3 -m unittest discover -s tests
"""

import json
import sys
import unittest
from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import scene  # noqa: E402
from price_browser import (  # noqa: E402
    BrowserError, periods, price_pages, read_calls, reserved_probes, reserved_round, step_call, step_outcome,
)
from price_model import BulkStep, CellEditStep, CellKey, RowWrite, encode_step  # noqa: E402

ERP = HERE / "fixtures" / "erp"
REJECTED = (ERP / "adjust-rejected.html").read_text(encoding="utf-8")
PRICE = (ERP / "price-runs-closed-absent-list.html").read_text(encoding="utf-8")
OFFER = "〈오퍼 관리용 이름〉"
CONTRACT = HERE / "fixtures" / "browser" / "calls.json"


def answer(probe, hidden=0, ok=True):
    """readReserved 의 답 — 조각은 손 조각 adjust-rejected 에 숨긴 줄 문장을 붙인 것."""
    note = f'<p class="stay-description">목록이 길어 {hidden:,}줄은 줄였습니다. 적용한 뒤 적용 기록에서 모두 볼 수 있습니다.</p>'
    title = '<h4 class="stay-section-title">건너뛰는 칸'
    head, tail = REJECTED.split(title, 1)
    fragment = REJECTED if not hidden else head + title + tail.replace("    </div>\n", "    </div>\n    " + note + "\n", 1)
    assert not hidden or note in fragment
    return {"ok": ok, "op": "readReserved", "asked": dict(probe), "fragment": fragment, "error": None if ok else "드로어가 열리지 않았습니다"}


class ReadCallsTest(unittest.TestCase):
    def test_one_period_covers_exactly_the_chosen_days(self):
        days = ["2026-12-25", "2026-12-26", "2027-01-01", "2027-01-02"]
        self.assertEqual(periods(days), [("2026-12-25", "2027-01-02", ["금", "토"])])
        calls = read_calls("데모 오퍼", [("디럭스", "조식 포함"), ("스위트", "룸온리"), ("디럭스", "조식 포함")], days)
        self.assertEqual(calls, [
            {"offer": "데모 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-25", "to": "2027-01-02", "weekdays": ["금", "토"]},
            {"offer": "데모 오퍼", "room": "스위트", "ratePlan": "룸온리", "from": "2026-12-25", "to": "2027-01-02", "weekdays": ["금", "토"]}])

    def test_days_one_period_cannot_cover_are_read_in_runs_never_reading_an_unchosen_day(self):
        # 수·목을 고른 기간이면 7/8(수)이 끼므로 이어진 날마다 따로 — 판매일 없는 날이 끼면 ERP 가 기간을 통째로 거절한다
        self.assertEqual(periods(["2026-07-01", "2026-07-02", "2026-07-09"]),
                         [("2026-07-01", "2026-07-02", list("월화수목금토일")), ("2026-07-09", "2026-07-09", list("월화수목금토일"))])

    def test_a_span_longer_than_550_days_is_split(self):
        thursdays = [(date(2026, 1, 1) + timedelta(weeks=week)).isoformat() for week in range(79)]
        self.assertEqual(periods(thursdays), [("2026-01-01", "2027-07-01", ["목"])], "546일 — 한 번에 읽는다")
        self.assertEqual(periods(thursdays + ["2027-07-08"]), [("2026-01-01", "2027-07-01", ["목"]), ("2027-07-08", "2027-07-08", ["목"])])

    def test_the_scene_request_reads_four_pairs_and_asks_one_reserved_probe(self):
        request = scene.request()
        pairs = [(room, plan) for room in request.rooms for plan in request.rate_plans]
        self.assertEqual(len(read_calls(request.offer, pairs, request.dates)), 4)
        self.assertEqual(reserved_probes(request.offer, pairs, request.dates), [
            {"offer": request.offer, "rooms": ["디럭스", "스위트"], "ratePlans": ["조식 포함", "룸온리"],
             "from": "2026-12-25", "to": "2027-01-02", "weekdays": ["금", "토"], "occupancy": "*", "nights": "all"}])

    def test_read_answers_must_be_what_was_asked(self):
        asked = {"offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함"}
        page, = price_pages([{"ok": True, "op": "readPair", "asked": asked, "fragment": PRICE}])
        self.assertEqual((page.offer, page.rate_plan, page.currency), ("샘플 오퍼", "조식 포함", "USD"))
        with self.assertRaisesRegex(BrowserError, "물은 것"):
            price_pages([{"ok": True, "op": "readPair", "asked": dict(asked, ratePlan="룸온리"), "fragment": PRICE}])
        with self.assertRaisesRegex(BrowserError, "읽지 못했습니다: 칩이 없습니다"):
            price_pages([{"ok": False, "op": "readPair", "asked": asked, "error": "칩이 없습니다"}])
        with self.assertRaisesRegex(BrowserError, "readPair 의 답이 아닙니다"):
            price_pages([{"ok": True, "op": "applyBulk", "asked": asked, "fragment": PRICE}])


class ReservedRoundTest(unittest.TestCase):
    def setUp(self):
        self.start = reserved_probes(OFFER, [("디럭스", "조식 포함"), ("스위트", "룸온리")],
                                     ["2026-12-24", "2026-12-25", "2026-12-26", "2026-12-27"])

    def test_no_answer_asks_the_first_probe(self):
        done = reserved_round(self.start, [])
        self.assertEqual((done.done, done.ask, done.pages), (False, self.start, []))

    def test_an_answer_without_hidden_rows_is_used_as_it_is(self):
        done = reserved_round(self.start, [answer(self.start[0])])
        self.assertTrue(done.done)
        self.assertEqual(len(done.pages), 1)
        self.assertIn("예약이 있는 날", {row.reason for row in done.pages[0].rejected})

    def test_hidden_rows_narrow_by_room_then_rate_plan_then_half_the_days_until_nothing_is_hidden(self):
        probe = self.start[0]
        rooms = reserved_round([probe], [answer(probe, hidden=120)])
        self.assertEqual([item["rooms"] for item in rooms.ask], [["디럭스"], ["스위트"]])
        deluxe, suite = rooms.ask
        plans = reserved_round([probe], [answer(probe, hidden=120), answer(deluxe), answer(suite, hidden=8)])
        self.assertEqual([(item["rooms"], item["ratePlans"]) for item in plans.ask], [(["스위트"], ["조식 포함"]), (["스위트"], ["룸온리"])])
        suite_bb, suite_ro = plans.ask
        halves = reserved_round([probe], [answer(probe, hidden=120), answer(deluxe), answer(suite, hidden=8),
                                          answer(suite_bb), answer(suite_ro, hidden=1)])
        self.assertEqual([(item["from"], item["to"]) for item in halves.ask], [("2026-12-24", "2026-12-25"), ("2026-12-26", "2026-12-27")])
        results = [answer(probe, hidden=120), answer(deluxe), answer(suite, hidden=8), answer(suite_bb), answer(suite_ro, hidden=1)]
        results += [answer(item) for item in halves.ask]
        done = reserved_round([probe], results)
        self.assertTrue(done.done)
        self.assertEqual(len(done.pages), 4, "디럭스 · 스위트 조식 포함 · 스위트 룸온리 반쪽 둘")
        self.assertTrue(all(page.hidden == 0 for page in done.pages))
        self.assertEqual(reserved_round([probe], list(reversed(results))).ask, [], "답의 차례와 상관없다")

    def test_a_failed_answer_keeps_the_probe_asked_and_says_why_until_it_is_answered(self):
        probe = self.start[0]
        failed = reserved_round([probe], [answer(probe, ok=False)])
        self.assertEqual(failed.ask, [probe])
        self.assertEqual(failed.failed, [{"asked": probe, "error": "드로어가 열리지 않았습니다"}])
        self.assertTrue(reserved_round([probe], [answer(probe, ok=False), answer(probe)]).done)

    def test_a_single_day_that_still_hides_rows_cannot_be_narrowed(self):
        probe = dict(self.start[0], rooms=["디럭스"], ratePlans=["조식 포함"], **{"from": "2026-12-24", "to": "2026-12-24"})
        with self.assertRaisesRegex(BrowserError, "하루로 좁혀도"):
            reserved_round([probe], [answer(probe, hidden=3)])

    def test_answers_to_other_operations_or_without_the_probe_are_refused(self):
        with self.assertRaisesRegex(BrowserError, "readReserved 의 답이 아닙니다"):
            reserved_round(self.start, [dict(answer(self.start[0]), op="readPair")])
        with self.assertRaisesRegex(BrowserError, "칸이 없습니다: occupancy"):
            reserved_round(self.start, [dict(answer(self.start[0]), asked={k: v for k, v in self.start[0].items() if k != "occupancy"})])


BULK = BulkStep("디럭스", "조식 포함", ("2026-07-01",), (RowWrite("", 1, D("125000.00")),))
CELL = CellEditStep(CellKey("디럭스", "조식 포함", "2026-07-01", "", 1), ("list",))


class StepCallTest(unittest.TestCase):
    def test_ledger_steps_become_the_page_payloads_pinned_for_the_node_test(self):
        calls = [step_call(1, OFFER, BULK.kind, encode_step(BULK)), step_call(2, OFFER, CELL.kind, encode_step(CELL))]
        self.assertEqual(calls, json.loads(CONTRACT.read_text(encoding="utf-8")))
        self.assertEqual(calls[0]["payload"]["rows"], [{"occupancy": "", "nights": 1, "sell": "125000.00", "list": None, "supply": None}])

    def test_an_unknown_step_kind_or_a_bad_body_is_refused(self):
        with self.assertRaises(ValueError):
            step_call(1, OFFER, "cell_edit", dict(encode_step(CELL), clear=["sell"]))

    def test_a_result_is_recorded_only_for_the_step_it_asked_about(self):
        call = step_call(1, OFFER, BULK.kind, encode_step(BULK))
        asked = {name: value for name, value in call["payload"].items() if name != "no"}
        saved = {"ok": True, "op": "applyBulk", "no": 1, "asked": asked, "saved": True, "pressed": True, "note": "저장했습니다 · 디럭스"}
        self.assertEqual(step_outcome(call, saved), (True, "저장했습니다 · 디럭스"))
        blocked = dict(saved, ok=False, error="허용 목록에 없는 클릭을 막았습니다: a")
        self.assertEqual(step_outcome(call, blocked), (True, "저장했습니다 · 디럭스 · 허용 목록에 없는 클릭을 막았습니다: a"))
        unsure = dict(saved, ok=False, saved=False, error="결과를 확인하지 못했습니다")
        self.assertEqual(step_outcome(call, unsure), (False, "저장 단추는 눌렸습니다 — 다시 읽어 값을 확인해야 합니다: 결과를 확인하지 못했습니다"))
        refused = dict(unsure, pressed=False, refused=True, error="드로어 표에 없는 줄")
        self.assertEqual(step_outcome(call, refused), (False, "드로어 표에 없는 줄"))
        for wrong in (dict(saved, no=2), dict(saved, op="applyCell"), dict(saved, asked=dict(asked, dates=["2026-07-02"]))):
            with self.assertRaises(BrowserError):
                step_outcome(call, wrong)


if __name__ == "__main__":
    unittest.main()
