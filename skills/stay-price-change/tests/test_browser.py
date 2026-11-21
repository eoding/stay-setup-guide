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
from browser_replies import reply, take as browser_take  # noqa: E402
from erp_read import ParseError  # noqa: E402
from change_core.answers import (  # noqa: E402
    BrowserError, CutAnswer, Outcome, ask_sum, attach_bodies, fnv1a, step_outcome, unanswered,
)
from price_browser import (  # noqa: E402
    page_hotel, pair_reads, periods, read_calls, reserved_probes, reserved_round, step_call, step_calls,
)
from price_model import MISSING, BulkStep, CellEditStep, CellKey, CellValue, RowWrite, Snapshot, encode_step  # noqa: E402

ERP = HERE / "fixtures" / "erp"
REJECTED = (ERP / "adjust-rejected.html").read_text(encoding="utf-8")
PRICE = (ERP / "price-runs-closed-absent-list.html").read_text(encoding="utf-8")
OFFER = "〈오퍼 관리용 이름〉"
HOTEL = scene.HOTEL_REF
CONTRACT = HERE / "fixtures" / "browser" / "calls.json"


def answer(probe, hidden=0, ok=True):
    """readReserved 의 답과 조각 쪽들 — 조각은 손 조각 adjust-rejected 에 숨긴 줄 문장을 붙인 것."""
    note = f'<p class="stay-description">목록이 길어 {hidden:,}줄은 줄였습니다. 적용한 뒤 적용 기록에서 모두 볼 수 있습니다.</p>'
    title = '<h4 class="stay-section-title">건너뛰는 칸'
    head, tail = REJECTED.split(title, 1)
    fragment = REJECTED if not hidden else head + title + tail.replace("    </div>\n", "    </div>\n    " + note + "\n", 1)
    assert not hidden or note in fragment
    if not ok:
        return reply("readReserved", dict(probe), ok=False, error="드로어가 열리지 않았습니다")
    return reply("readReserved", dict(probe), {"fragment": fragment})


def spots(refetch):
    """받을 쪽마다 (조각 id, 자리, 크기)."""
    return [(item["id"], item["at"], item["size"]) for item in refetch]


def flat(*answers):
    return [item for group in answers for item in group]


class ReadCallsTest(unittest.TestCase):
    def test_one_period_covers_exactly_the_chosen_days(self):
        days = ["2026-12-25", "2026-12-26", "2027-01-01", "2027-01-02"]
        self.assertEqual(periods(days), [("2026-12-25", "2027-01-02", ["금", "토"])])
        calls = read_calls(HOTEL, "데모 오퍼", [("디럭스", "조식 포함"), ("스위트", "룸온리"), ("디럭스", "조식 포함")], days)
        self.assertEqual(calls, [
            {"hotel": HOTEL, "offer": "데모 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-25", "to": "2027-01-02", "weekdays": ["금", "토"]},
            {"hotel": HOTEL, "offer": "데모 오퍼", "room": "스위트", "ratePlan": "룸온리", "from": "2026-12-25", "to": "2027-01-02", "weekdays": ["금", "토"]}])

    def test_days_one_period_cannot_cover_are_read_in_runs_never_reading_an_unchosen_day(self):
        # 수·목을 고른 기간이면 7/8(수)이 끼므로 이어진 날마다 따로 — 판매일 없는 날이 끼면 ERP 가 기간을 통째로 거절한다
        self.assertEqual(periods(["2026-07-01", "2026-07-02", "2026-07-09"]),
                         [("2026-07-01", "2026-07-02", list("월화수목금토일")), ("2026-07-09", "2026-07-09", list("월화수목금토일"))])

    def test_reads_are_cut_at_186_days_so_one_call_walks_few_calendar_months(self):
        year = [(date(2027, 1, 1) + timedelta(days=offset)).isoformat() for offset in range(365)]
        calls = read_calls(HOTEL, "O", [("R", "P")], year)
        self.assertEqual([(call["from"], call["to"]) for call in calls], [("2027-01-01", "2027-07-05"), ("2027-07-06", "2027-12-31")])
        self.assertEqual(len(reserved_probes(HOTEL, "O", [("R", "P")], year)), 1, "가감 물음은 550일까지 한 번에")

    def test_a_span_longer_than_550_days_is_split(self):
        thursdays = [(date(2026, 1, 1) + timedelta(weeks=week)).isoformat() for week in range(79)]
        self.assertEqual(periods(thursdays), [("2026-01-01", "2027-07-01", ["목"])], "546일 — 한 번에 읽는다")
        self.assertEqual(periods(thursdays + ["2027-07-08"]), [("2026-01-01", "2027-07-01", ["목"]), ("2027-07-08", "2027-07-08", ["목"])])

    def test_the_scene_request_reads_four_pairs_and_asks_one_reserved_probe(self):
        request = scene.request()
        pairs = [(room, plan) for room in request.rooms for plan in request.rate_plans]
        self.assertEqual(len(read_calls(HOTEL, request.offer, pairs, request.dates)), 4)
        self.assertEqual(reserved_probes(HOTEL, request.offer, pairs, request.dates), [
            {"hotel": HOTEL, "offer": request.offer, "rooms": ["디럭스", "스위트"], "ratePlans": ["룸온리", "조식 포함"],
             "from": "2026-12-25", "to": "2027-01-02", "weekdays": ["금", "토"], "occupancy": "*", "nights": "all"}])

    def test_read_answers_must_be_what_was_asked(self):
        asked = {"hotel": HOTEL, "offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-24", "to": "2026-12-31", "weekdays": list("월화수목금토일")}
        read, = pair_reads(reply("readPair", asked, {"fragment": PRICE}))
        self.assertEqual((read.offer, read.room, read.rate_plan, read.page.room, read.page.currency),
                         ("샘플 오퍼", "디럭스", "조식 포함", "샘플 오퍼 · 디럭스", "USD"))
        with self.assertRaisesRegex(ParseError, "룸온리 를 물었는데 화면은 샘플 오퍼 · 조식 포함"):
            pair_reads(reply("readPair", dict(asked, ratePlan="룸온리"), {"fragment": PRICE}))
        with self.assertRaisesRegex(BrowserError, "읽지 못했습니다: 칩이 없습니다"):
            pair_reads(reply("readPair", asked, ok=False, error="칩이 없습니다"))
        with self.assertRaisesRegex(BrowserError, "readPair 의 답이 아닙니다"):
            pair_reads(reply("applyBulk", asked, {"fragment": PRICE}))

    def test_g2_a_reading_from_another_hotel_than_asked_is_refused_and_the_page_names_the_hotel(self):
        asked = {"hotel": HOTEL, "offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-24",
                 "to": "2026-12-31", "weekdays": list("월화수목금토일")}
        other = {"id": "2", "name": HOTEL["name"]}
        with self.assertRaisesRegex(BrowserError, "물은 호텔\\(1\\)이 아닌 2 호텔"):
            pair_reads(reply("readPair", asked, {"fragment": PRICE, "hotel": other}))
        with self.assertRaisesRegex(BrowserError, "물은 호텔"):
            pair_reads(reply("readPair", dict(asked, hotel=None), {"fragment": PRICE}))
        self.assertEqual(page_hotel(reply("readPair", asked, {"fragment": PRICE, "hotel": dict(HOTEL, name="페이지 이름")})),
                         {"id": "1", "name": "페이지 이름"})
        with self.assertRaisesRegex(BrowserError, "하나로 정하지 못했습니다"):
            page_hotel(reply("readPair", asked, {"fragment": PRICE}) + reply("readPair", dict(asked, hotel=other), {"fragment": PRICE}))
        with self.assertRaisesRegex(BrowserError, "호텔 번호가 없습니다"):
            read_calls({"name": "데모 호텔"}, "O", [("R", "P")], ["2026-12-25"])


class ReservedRoundTest(unittest.TestCase):
    def setUp(self):
        self.start = reserved_probes(HOTEL, OFFER, [("디럭스", "조식 포함"), ("스위트", "룸온리")],
                                     ["2026-12-24", "2026-12-25", "2026-12-26", "2026-12-27"])

    def test_no_answer_asks_the_first_probe(self):
        done = reserved_round(self.start, [])
        self.assertEqual((done.done, done.ask, done.pages), (False, self.start, []))

    def test_an_answer_without_hidden_rows_is_used_as_it_is(self):
        done = reserved_round(self.start, answer(self.start[0]))
        self.assertTrue(done.done)
        self.assertEqual(len(done.pages), 1)
        self.assertIn("예약이 있는 날", {row.reason for row in done.pages[0].rejected})

    def test_hidden_rows_narrow_by_room_then_rate_plan_then_half_the_days_until_nothing_is_hidden(self):
        probe = self.start[0]
        rooms = reserved_round([probe], answer(probe, hidden=120))
        self.assertEqual([item["rooms"] for item in rooms.ask], [["디럭스"], ["스위트"]])
        deluxe, suite = rooms.ask
        plans = reserved_round([probe], flat(answer(probe, hidden=120), answer(deluxe), answer(suite, hidden=8)))
        self.assertEqual([(item["rooms"], item["ratePlans"]) for item in plans.ask], [(["스위트"], ["룸온리"]), (["스위트"], ["조식 포함"])])
        suite_ro, suite_bb = plans.ask
        halves = reserved_round([probe], flat(answer(probe, hidden=120), answer(deluxe), answer(suite, hidden=8),
                                              answer(suite_bb), answer(suite_ro, hidden=1)))
        self.assertEqual([(item["from"], item["to"]) for item in halves.ask], [("2026-12-24", "2026-12-25"), ("2026-12-26", "2026-12-27")])
        results = flat(answer(probe, hidden=120), answer(deluxe), answer(suite, hidden=8), answer(suite_bb), answer(suite_ro, hidden=1),
                       *[answer(item) for item in halves.ask])
        done = reserved_round([probe], results)
        self.assertTrue(done.done)
        self.assertEqual(len(done.pages), 4, "디럭스 · 스위트 조식 포함 · 스위트 룸온리 반쪽 둘")
        self.assertTrue(all(page.hidden == 0 for page in done.pages))
        self.assertEqual(reserved_round([probe], list(reversed(results))).ask, [], "답의 차례와 상관없다")

    def test_a_failed_answer_keeps_the_probe_asked_and_says_why_until_it_is_answered(self):
        probe = self.start[0]
        failed = reserved_round([probe], answer(probe, ok=False))
        self.assertEqual(failed.ask, [probe])
        self.assertEqual(failed.failed, [{"asked": probe, "error": "드로어가 열리지 않았습니다"}])
        self.assertTrue(reserved_round([probe], flat(answer(probe, ok=False), answer(probe))).done)

    def test_a_single_day_that_still_hides_rows_cannot_be_narrowed(self):
        probe = dict(self.start[0], rooms=["디럭스"], ratePlans=["조식 포함"], **{"from": "2026-12-24", "to": "2026-12-24"})
        with self.assertRaisesRegex(BrowserError, "하루로 좁혀도"):
            reserved_round([probe], answer(probe, hidden=3))

    def test_answers_to_other_operations_or_for_another_probe_are_refused_or_left_unused(self):
        with self.assertRaisesRegex(BrowserError, "readReserved 의 답이 아닙니다"):
            reserved_round(self.start, reply("readPair", self.start[0], {"fragment": REJECTED}))
        with self.assertRaisesRegex(BrowserError, "칸이 없습니다: occupancy"):
            reserved_round([{k: v for k, v in self.start[0].items() if k != "occupancy"}], [])
        other = dict(self.start[0], nights="one")
        self.assertEqual(reserved_round(self.start, answer(other)).ask, self.start, "다른 물음의 답은 이 물음의 답이 아니다")


BULK = BulkStep("디럭스", "조식 포함", ("2026-07-01",), (RowWrite("", 1, D("125000.00")),))
CELL = CellEditStep(CellKey("디럭스", "조식 포함", "2026-07-01", "", 1), ("list",))


def reading(cells) -> Snapshot:
    return Snapshot("데모 호텔", OFFER, "USD", "2026-11-21T10:00:00+09:00", cells, frozenset(), frozenset({("디럭스", "조식 포함")}),
                    hotel_id=HOTEL["id"])


def key(day, occupancy=""):
    return CellKey("디럭스", "조식 포함", day, occupancy, 1)


class StepCallTest(unittest.TestCase):
    def test_ledger_steps_become_the_page_payloads_pinned_for_the_node_test(self):
        # 페이지 시험의 화면과 같은 값 — 가격 수정 ② 의 7/1 인원 무관 줄(정가 · 원가 없음)과 셀 창의 7/1 A2 줄(page_harness ROWS)
        cell = CellEditStep(key("2026-07-01", "A2"), ("supply",))
        seen = reading({key("2026-07-01"): CellValue(D("120000.00"), None, None, "open"),
                        key("2026-07-01", "A2"): CellValue(D("150000.00"), None, D("110000.00"), "open")})
        calls = step_calls(HOTEL, OFFER, [(1, BULK.kind, encode_step(BULK)), (2, cell.kind, encode_step(cell))], seen)
        self.assertEqual(calls, json.loads(CONTRACT.read_text(encoding="utf-8")))
        self.assertEqual(calls[0]["payload"]["rows"], [{"occupancy": "", "nights": 1, "sell": "125000.00", "list": None, "supply": None,
                                                        "was": [["2026-07-01", "2026-07-01", "120000.00", None, None]]}])
        self.assertEqual(calls[1]["payload"]["was"], ["150000.00", None, "110000.00"])

    def test_a1_each_step_carries_what_the_screen_must_show_with_the_earlier_steps_laid_over_the_reading(self):
        seen = reading({key("2026-07-01"): CellValue(D("120.00"), D("150.00"), None, "open"),
                        key("2026-07-02"): CellValue(D("120.00"), D("150.00"), None, "closed"),
                        key("2026-07-03"): CellValue(D("125.00"), D("150.00"), None, "open"),
                        key("2026-07-04"): MISSING})
        clear = CellEditStep(key("2026-07-01"), ("list",))
        bulk = BulkStep("디럭스", "조식 포함", ("2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04", "2026-07-06"),
                        (RowWrite("", 1, D("130.00")), RowWrite("A2", 1, D("160.00"))))
        again = BulkStep("디럭스", "조식 포함", ("2026-07-04",), (RowWrite("", 1, None, D("140.00")),))
        calls = step_calls(HOTEL, OFFER, [(1, clear.kind, encode_step(clear)), (2, bulk.kind, encode_step(bulk)),
                                          (3, again.kind, encode_step(again))], seen)
        self.assertEqual(calls[0]["payload"]["was"], ["120.00", "150.00", None], "셀 창은 읽은 값 그대로")
        self.assertEqual(calls[1]["payload"]["rows"][0]["was"], [
            ["2026-07-01", "2026-07-01", "120.00", None, None],       # 앞 단계(셀 창)가 정가를 비웠다
            ["2026-07-02", "2026-07-02", "120.00", "150.00", None],   # 마감인 칸도 값으로 본다
            ["2026-07-03", "2026-07-03", "125.00", "150.00", None],
            ["2026-07-04", "2026-07-06", None, None, None],           # 가격 없음 · 읽은 값에 없는 칸은 칸이 없는 것 — 잇달면 한 줄
        ])
        self.assertEqual(calls[1]["payload"]["rows"][1]["was"], [["2026-07-01", "2026-07-06", None, None, None]],
                         "읽은 값에 없는 줄은 날마다 칸이 없다")
        self.assertEqual(calls[2]["payload"]["rows"][0]["was"], [["2026-07-04", "2026-07-04", "130.00", None, None]],
                         "앞 묶음 저장이 판매가를 넣어 만든 칸")
        self.assertEqual([call["payload"]["no"] for call in calls], [1, 2, 3])
        self.assertEqual(calls[1]["payload"]["rows"][0]["sell"], "130.00", "넣는 값은 step_call 그대로")

    def test_an_unknown_step_kind_or_a_bad_body_is_refused(self):
        with self.assertRaises(ValueError):
            step_call(1, HOTEL, OFFER, "cell_edit", dict(encode_step(CELL), clear=["sell"]))

    def test_a_result_is_recorded_only_for_the_step_it_asked_about(self):
        call = step_call(1, HOTEL, OFFER, BULK.kind, encode_step(BULK))
        saved = {"ok": True, "op": "applyBulk", "no": 1, "ask": ask_sum(call["payload"]), "saved": True, "pressed": True, "note": "저장했습니다 · 디럭스"}
        self.assertEqual(step_outcome(call, saved), Outcome(True, "저장했습니다 · 디럭스"))
        blocked = dict(saved, ok=False, error="허용 목록에 없는 클릭을 막았습니다: a")
        self.assertEqual(step_outcome(call, blocked), Outcome(True, "저장했습니다 · 디럭스 · 허용 목록에 없는 클릭을 막았습니다: a"))
        unsure = dict(saved, ok=False, saved="unknown", error="결과를 확인하지 못했습니다")
        self.assertEqual(step_outcome(call, unsure), Outcome("unknown", "저장됐는지 알 수 없습니다 — 다시 읽어 값을 확인해야 합니다: 결과를 확인하지 못했습니다"))
        rejected = dict(saved, ok=False, saved=False, error="셀 창이 저장을 거절했습니다")
        self.assertEqual(step_outcome(call, rejected), Outcome(False, "셀 창이 저장을 거절했습니다"))
        refused = dict(unsure, saved=False, pressed=False, refused=True, error="드로어 표에 없는 줄")
        self.assertEqual(step_outcome(call, refused), Outcome(False, "드로어 표에 없는 줄"))
        later = dict(refused, refused=None, started=False, wait=10, error="앞 작업(readPair)이 아직 끝나지 않았습니다")
        self.assertEqual(step_outcome(call, later), Outcome(None, "앞 작업(readPair)이 아직 끝나지 않았습니다", 10))
        self.assertFalse(step_outcome(call, later).started, "G7 — 시작하지 않은 저장")
        self.assertEqual(step_outcome(call, dict(later, pressed=True, saved="unknown")).saved, "unknown",
                         "눌린 저장은 시작하지 않은 것으로 보지 않는다")
        other = dict(call["payload"], dates=["2026-07-02"])
        for wrong in (dict(saved, no=2), dict(saved, op="applyCell"), dict(saved, ask=ask_sum(other))):
            with self.assertRaises(BrowserError):
                step_outcome(call, wrong)



class BodyTest(unittest.TestCase):
    """B9 · B16 — 조각은 자리(at)로 이어지는 쪽으로 오고, 바이트 수와 CRC-32 가 둘 다 맞을 때만 쓴다. 잘린 답은 알아보고
    어느 쪽을 어떤 크기로 다시 받을지 말한다."""

    ASKED = {"offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-24", "to": "2026-12-31",
             "weekdays": list("월화수목금토일")}

    def test_pieces_in_any_order_join_into_the_fragment(self):
        result, *takes = reply("readPair", self.ASKED, {"fragment": PRICE}, pieces=4)
        joined, = attach_bodies([takes[2], result, takes[0], takes[3], takes[1], takes[1]])
        self.assertEqual((joined["fragment"], joined["asked"]), (PRICE, self.ASKED))

    def test_a_missing_cut_or_mistyped_page_is_named_with_its_reason_and_never_read(self):
        result, *takes = reply("readPair", self.ASKED, {"fragment": PRICE}, pieces=4)
        body_id, chars = result["body"]["id"], result["body"]["chars"]
        with self.assertRaises(CutAnswer) as missing:
            attach_bodies([result, *takes[:3]])
        self.assertEqual(missing.exception.refetch, [{"id": body_id, "at": takes[3]["at"], "size": 800, "until": chars,
                                                       "save": f"take-{body_id}-", "bad": []}])
        at = next(index for index, take in enumerate(takes) if "140.00" in take["text"])
        typo = dict(takes[at], text=takes[at]["text"].replace("140.00", "146.00", 1))
        self.assertEqual(len(typo["text"]), len(takes[at]["text"]), "글자 수가 같은 잘못 옮겨 적기")
        with self.assertRaises(CutAnswer) as mistyped:
            attach_bodies([result, *takes[:at], typo, *takes[at + 1:]])
        self.assertEqual([(item["at"], item["until"], [bad["why"] for bad in item["bad"]]) for item in mistyped.exception.refetch],
                         [(takes[at]["at"], takes[at]["next"], ["옮겨 적은 글이 페이지가 준 것과 다릅니다 — 그 쪽을 다시 받아 새 파일로 저장합니다"])],
                         "그 쪽 하나만 다시 받는다")
        joined, = attach_bodies([result, *takes, typo])
        self.assertEqual(joined["fragment"], PRICE, "같은 자리에 맞는 쪽이 있으면 맞지 않는 쪽은 무시한다")
        short = dict(takes[1], text=takes[1]["text"][:-5])
        with self.assertRaises(CutAnswer) as cut_short:
            attach_bodies([result, takes[0], short, *takes[2:]])
        self.assertEqual([bad["why"] for bad in cut_short.exception.refetch[0]["bad"]],
                         ["옮겨 적은 글의 길이가 쪽이 말하는 길이와 다릅니다 — 그 쪽을 다시 받아 새 파일로 저장합니다"])
        with self.assertRaisesRegex(BrowserError, "조각 머리\\(body\\)가 페이지가 준 쪽들과 맞지 않습니다"):
            attach_bodies([dict(result, body=dict(result["body"], crc32="00000000")), *takes])
        with self.assertRaises(CutAnswer):
            attach_bodies([result, {"ok": False, "op": "take", "id": "x", "error": "그 조각이 페이지에 없습니다"}])
        with self.assertRaisesRegex(BrowserError, "페이지에 없습니다.*새 폴더"):
            attach_bodies([result, {"ok": False, "op": "take", "id": body_id, "error": "그 조각이 페이지에 없습니다"}])

    def test_u1_a_header_whose_second_check_differs_is_refused_here_and_never_lent_by_an_earlier_reading(self):
        # 글자 수 · 바이트 수 · CRC-32 는 이은 글자와 맞고 FNV-1a 만 다른 머리 — 이 읽기의 답이면 그 답을 다시 받으라고 거절한다
        result, *takes = reply("readPair", self.ASKED, {"fragment": PRICE}, pieces=3, body_id="b1")
        odd = dict(result["body"], fnv="00000000")
        self.assertNotEqual(odd["fnv"], result["body"]["fnv"])
        with self.assertRaisesRegex(BrowserError, "조각 머리\\(body\\)가 페이지가 준 쪽들과 맞지 않습니다"):
            attach_bodies([dict(result, body=odd), *takes])
        # 앞선 읽기의 그런 머리는 빌려 주는 것과 상관없다 — 같은 틀린 머리를 단 이번 답은 쪽을 받아야 한다
        again = dict(result, body=dict(odd, id="b2"))
        with self.assertRaises(CutAnswer) as caught:
            attach_bodies([again], earlier=[dict(result, body=odd), *takes])
        self.assertEqual([(item["id"], item["at"]) for item in caught.exception.refetch], [("b2", 0)])
        lent, = attach_bodies([dict(result, body=dict(result["body"], id="b2"))], earlier=[result, *takes])
        self.assertEqual(lent["fragment"], PRICE, "머리가 맞는 조각은 빌려 쓴다")

    def test_a_cut_answer_names_the_piece_to_fetch_again_and_a_smaller_size(self):
        result, *takes = reply("readPair", self.ASKED, {"fragment": PRICE}, pieces=3)
        shown = json.dumps(takes[1], ensure_ascii=False)
        cut = shown[:1000] + "[TRUNCATED]"
        with self.assertRaises(CutAnswer) as caught:
            attach_bodies([result, takes[0], cut, takes[2]])
        self.assertEqual(spots(caught.exception.refetch), [(result["body"]["id"], takes[1]["at"], 600)])
        self.assertIn(f"stayPrice.take('{result['body']['id']}', {takes[1]['at']}, 600)", str(caught.exception))
        unclosed = shown[:700]
        with self.assertRaises(CutAnswer):
            attach_bodies([result, takes[0], unclosed, takes[2]])
        # 붙여 넣은 사람이 JSON 을 닫아 버린 잘린 답 — `[TRUNCATED]` 표시만이 잘렸다고 말해 준다(B19)
        for closed in (shown[:990] + '[TRUNCATED]"}', json.dumps(dict(takes[1], text=takes[1]["text"][:300] + "[TRUNCATED]"), ensure_ascii=False)):
            self.assertIsInstance(json.loads(closed), dict, "닫힌 JSON 이다")
            with self.assertRaises(CutAnswer) as marked:
                attach_bodies([result, takes[0], closed, takes[2]])
            self.assertEqual(spots(marked.exception.refetch), [(result["body"]["id"], takes[1]["at"], 600)])
        # 같은 자리에서 더 작게 다시 받은 쪽 둘이 빈 곳을 메우면 잘린 답은 그냥 지나간다
        text = "".join(take["text"] for take in takes)
        meta, mid = result["body"], takes[1]
        half = (mid["next"] - mid["at"]) // 2
        again = [browser_take(meta, text, mid["at"], half), browser_take(meta, text, mid["at"] + half, mid["next"] - mid["at"] - half)]
        joined, = attach_bodies([result, takes[0], cut, *again, takes[2]])
        self.assertEqual(joined["fragment"], PRICE)

    def test_z4_a_cut_reading_answer_is_no_answer_and_the_whole_one_from_last_or_a_new_call_is_used(self):
        result, *takes = reply("readPair", self.ASKED, {"fragment": PRICE})
        cut = json.dumps(result, ensure_ascii=False)[:60] + "[TRUNCATED]"
        self.assertEqual(attach_bodies([cut]), [], "어느 물음의 답인지 모르는 잘린 답은 답이 아니다")
        self.assertEqual(unanswered([self.ASKED], [cut], "readPair"), [self.ASKED], "그 물음은 답이 없는 것으로 남는다")
        running = {"running": {"op": "readPair", "at": "2026-11-21T01:00:00.000Z"}}
        self.assertEqual(unanswered([self.ASKED], [cut, running], "readPair"), [self.ASKED], "돌던 중에 받은 last() 도 답이 아니다")
        joined, = attach_bodies([cut, running, result, *takes])
        self.assertEqual(joined["fragment"], PRICE)

    def test_an_answer_whose_body_is_from_another_question_is_not_used_and_that_question_stays_unanswered(self):
        # 옮겨 적다 지문(ask)이 틀린 답 — 검사값이 맞는 조각이 진짜 물음을 말한다. 그 답은 쓰지 않고(막지도 않고), 진짜 물음은
        # 답이 없는 것으로 남아 다시 부르게 된다
        result, *takes = reply("readPair", self.ASKED, {"fragment": PRICE})
        wrong = dict(result, ask=ask_sum(dict(self.ASKED, room="스위트")))
        self.assertEqual(attach_bodies([wrong, *takes]), [])
        self.assertEqual(unanswered([self.ASKED], [wrong, *takes], "readPair"), [self.ASKED])
        joined, = attach_bodies([wrong, result, *takes])
        self.assertEqual(joined["fragment"], PRICE)

    def test_the_digest_matches_the_page_rule_for_korean_and_key_order(self):
        self.assertEqual(ask_sum({"no": 3, "b": [1, None], "a": "디럭스 \"킹\""}), ask_sum({"a": "디럭스 \"킹\"", "b": [1, None]}))

    def test_the_second_body_check_is_standard_fnv1a_over_utf8(self):
        # 표준 FNV-1a 32비트 시험값 — 페이지(stay_price.js)도 같은 셈이다(화면 시험이 이은 글자로 맞춰 본다)
        self.assertEqual([fnv1a(b""), fnv1a(b"a"), fnv1a(b"foobar")], ["811c9dc5", "e40c292c", "bf9cf968"])
        self.assertEqual(fnv1a("디럭스 · 조식 포함".encode("utf-8")), "7da60b99")


if __name__ == "__main__":
    unittest.main()