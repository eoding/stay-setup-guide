"""검토 2 의 시즌 다시 채우기 쪽 — 명령으로 한 바퀴씩. 페이지의 답은 `browser_replies` 와 `season_scene` 으로 만들고, 장부의 시계는
명령마다 STAY_PRICE_TEST_NOW 로 세운다(test_season_flow 의 FlowBase).

    python3 -m unittest discover -s tests
"""

import json
import sys
import unittest
from dataclasses import replace
from datetime import datetime
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import season_scene  # noqa: E402
from change_core.answers import ask_sum  # noqa: E402
from price_model import CellKey, CellValue  # noqa: E402
from price_season import SeasonError, counts_agree, decode_plan, encode_window, plan_season, window_of  # noqa: E402
from test_season_flow import HOTEL, FlowBase, applied, at  # noqa: E402

DAY = "2026-12-01"
BB = ("디럭스", "조식 포함")


def key(occupancy: str, nights: int = 1, day: str = DAY, pair=BB) -> CellKey:
    return CellKey(pair[0], pair[1], day, occupancy, nights)


class SeasonCase(FlowBase):
    """시즌 창(season.json)과 요청을 쓰고 미리보기를 적는다 — 경우마다 창 · 읽은 값 · 요청만 다르다."""

    def plan(self, window, snapshot, saves, choices=None, sentence="Peak 다시 채워줘"):
        self.write("season.json", encode_window(window))
        request = self.write("request.json", {"kind": "season_fill", "hotel": HOTEL, "offer": window.offer,
                                              "season": {"id": window.season_id, "name": window.season_name}, "currency": "USD",
                                              "sentence": sentence, "saves": saves})
        args = ["plan", "--snapshot", self.snap(snapshot, at(-60)), "--request", request, "--season", self.dir / "season.json",
                "--record", "--out", self.dir / f"plan-{self.files}.json"]
        if choices:
            args[-2:-2] = ["--resolutions", self.write(f"choices-{self.files}.json", choices)]
        out = args[-1]
        short = self.cli(*args)
        data = json.loads(Path(out).read_text(encoding="utf-8"))
        return short, decode_plan(data["plan"]), out

    def season_after(self, window, seconds: int, supply_warn=None) -> str:
        """그 저장 뒤에 readSeason 으로 다시 읽은 창(season 이 낸 season.json) — 읽은 때 · 「공급 통화 없음」 띠."""
        return self.write(f"season-after-{seconds}.json", encode_window(replace(window, read_at=at(seconds), supply_warn=supply_warn)))

    def answer(self, call, **fields) -> str:
        body = {"op": call["op"], "no": call["no"], "ask": ask_sum(call["payload"]), "pressed": True, **fields}
        return self.write(f"answer-{call['no']}-{self.files}.json", body)


class LandedOneWayTest(SeasonCase):
    """검토 2 의 1 — 「이 저장이 됐다」의 뜻은 check 와 확인이 같다. 허용 인원 조합을 몰라 ERP 가 뺄 수 있다고 표시한 칸을 ERP 가 뺀
    「모름」 저장은 check 가 저장됨으로 가리고, 되돌릴 수 있다."""

    def test_s2_an_unknown_save_that_landed_without_a_cell_the_erp_may_leave_out_settles_as_saved_and_rolls_back(self):
        window = replace(season_scene.window(bands=[{"code": "CHD", "basis": "flat", "value": "20"}], dates=[DAY], rooms=["디럭스"]),
                         combos={"디럭스": None})
        before = {key("A2"): CellValue(D("180"), None, None, "open"), key("A2C1_CHD"): CellValue(D("195"), None, None, "open")}
        snapshot = replace(season_scene.snapshot((), pairs=[BB], dates=[DAY]), cells=before)
        short, plan, plan_file = self.plan(window, snapshot, [{"pairs": [{"room": BB[0], "rate_plan": BB[1]}], "price": "190",
                                                               "occupancy_keys": "A2", "child_extra": {"CHD": ""}, "overwrite": True}])
        self.assertEqual(short["counts"]["combo_unknown"], 1, "A2C1_CHD 는 ERP 가 뺄 수 있는 칸이다")
        change = short["change_id"]
        self.cli("begin", "--change", change, "--plan", plan_file, "--snapshot", self.snap(snapshot, at(20)), now=30)
        [call] = self.cli("calls", "--change", change, "--snapshot", self.snap(snapshot, at(40)), now=50)["calls"]
        recorded = self.cli("record-result", "--change", change, "--result", self.answer(call, ok=False, saved="unknown",
                                                                                        error="시간(40초) 안에 끝나지 않아 멈췄습니다"), now=60)
        self.assertEqual(recorded["status"], "stopped")
        landed = replace(snapshot, cells={**before, key("A2"): CellValue(D("190"), None, None, "open")})   # ERP 가 A2C1_CHD 는 뺐다
        checked = self.cli("check", "--change", change, "--snapshot", self.snap(landed, at(70)), "--season", self.season_after(window, 65),
                           now=75)
        self.assertEqual((checked["status"], checked["steps"][0]["settled"], checked["why"]), ("applied", "saved", []), checked)
        verified = self.cli("verify", "--change", change, "--snapshot", self.snap(landed, at(80)), now=85, code=1)
        self.assertEqual((verified["mismatches"], [item["key"]["occupancy"] for item in verified["left_out"]]), ([], ["A2C1_CHD"]),
                         "확인도 같은 칸을 같은 뜻으로 받아들인다(띠가 없어 「확인했습니다」는 아니다)")
        rollback = self.cli("rollback", "--change", change, "--snapshot", self.snap(landed, at(90)), "--record",
                            "--out", self.dir / "rollback-1.json", now=95)
        self.assertEqual(rollback["restored"], 1, "저장된 A2 190 을 되돌릴 수 있다")

    def test_s2_a_step_whose_every_cell_may_be_left_out_and_reads_as_before_is_not_saved(self):
        window = replace(season_scene.window(bands=[{"code": "CHD", "basis": "flat", "value": "20"}], dates=[DAY], rooms=["디럭스"]),
                         combos={"디럭스": None})
        before = {key("A2"): CellValue(D("190"), None, None, "open"), key("A2C1_CHD"): CellValue(D("195"), None, None, "open")}
        snapshot = replace(season_scene.snapshot((), pairs=[BB], dates=[DAY]), cells=before)
        short, plan, plan_file = self.plan(window, snapshot, [{"pairs": [{"room": BB[0], "rate_plan": BB[1]}], "price": "190",
                                                               "occupancy_keys": "A2", "child_extra": {"CHD": ""}, "overwrite": True}])
        change = short["change_id"]
        self.cli("begin", "--change", change, "--plan", plan_file, "--snapshot", self.snap(snapshot, at(20)), now=30)
        [call] = self.cli("calls", "--change", change, "--snapshot", self.snap(snapshot, at(40)), now=50)["calls"]
        self.cli("record-result", "--change", change, "--result", self.answer(call, ok=False, saved="unknown", error="모름"), now=60)
        checked = self.cli("check", "--change", change, "--snapshot", self.snap(snapshot, at(70)), "--season", self.season_after(window, 65),
                           now=75)
        self.assertEqual((checked["steps"][0]["settled"], checked["can_continue"]), ("not_saved", True),
                         "칸이 모두 ERP 가 뺄 수 있는 칸이고 전 값 그대로면 저장 안 됨 — 다시 눌러도 그 칸은 그대로다")


class NoChangeSaveTest(SeasonCase):
    """검토 2 의 8 — 바뀌는 칸이 없는 저장은 장부의 단계가 아니다(누르지 않는다). 앞 저장이 거절돼도 check 가 거짓 까닭으로 막지 않는다."""

    def test_s8_a_save_that_changes_no_cell_is_not_pressed_and_check_reads_the_change_truthfully(self):
        window = season_scene.window(dates=[DAY], rooms=["디럭스"])
        ro = ("디럭스", "룸온리")
        before = {key("A2"): CellValue(D("180"), None, None, "open"), key("A2", pair=ro): CellValue(D("172"), None, None, "open")}
        snapshot = replace(season_scene.snapshot((), pairs=[BB, ro], dates=[DAY]), cells=before)
        saves = [{"pairs": [{"room": BB[0], "rate_plan": BB[1]}], "price": "190", "occupancy_keys": "A2", "overwrite": True},
                 {"pairs": [{"room": ro[0], "rate_plan": ro[1]}], "price": "172", "occupancy_keys": "A2", "overwrite": True}]
        short, plan, plan_file = self.plan(window, snapshot, saves)
        self.assertEqual((short["saves"], [save["pressed"] for save in short["per_save"]]), (1, [True, False]),
                         "룸온리는 이미 172 라 그 저장은 누르지 않는다")
        self.assertIn("2번째 저장은 누르지 않습니다", self.cli("render", "preview", "--plan", plan_file, "--text")["text"])
        change = short["change_id"]
        self.cli("begin", "--change", change, "--plan", plan_file, "--snapshot", self.snap(snapshot, at(20)), now=30)
        [call] = self.cli("calls", "--change", change, "--snapshot", self.snap(snapshot, at(40)), now=50)["calls"]
        refused = self.answer(call, ok=False, saved=False, pressed=False, refused=True, differ=["price"],
                              error="시즌 창이 미리보기 때와 다릅니다(price) — 아무것도 치지 않았고 누르지 않았습니다")
        self.cli("record-result", "--change", change, "--result", refused, now=60)
        checked = self.cli("check", "--change", change, "--snapshot", self.snap(snapshot, at(70)), now=75)
        self.assertEqual(([step["seen"] for step in checked["steps"]], checked["why"], checked["can_continue"]),
                         (["not_saved"], [], True), "누르지 않는 저장이 없어 「넣으려던 값도 그 전 값도 아닙니다」라는 거짓 까닭이 없다")
        listed = next(item for item in self.cli("list", "--all", now=80)["changes"] if item["id"] == change)
        self.assertIn("저장 1번", listed["line"], "장부의 한 일도 누르는 저장만 센다")


class DayFactsTest(SeasonCase):
    """검토 2 의 7 — 미리보기 뒤에 판매일이 열리거나 예약이 든 날은 적용 직전(begin)과 저장 직전(calls)의 다시 읽기가 알아챈다."""

    DAYS = season_scene.CASES["hotel"]["season"]

    def setup_change(self):
        window = season_scene.window(rooms=["디럭스"])
        cells = {key("A2", day=day): CellValue(D("180"), None, None, "open") for day in self.DAYS if day != "2026-12-03"}
        snapshot = replace(season_scene.snapshot((), pairs=[BB]), cells=cells)
        self.assertIn(("디럭스", "2026-12-03"), snapshot.no_sale)
        short, plan, plan_file = self.plan(window, snapshot, [{"pairs": [{"room": BB[0], "rate_plan": BB[1]}], "price": "190",
                                                               "occupancy_keys": "A2", "overwrite": True}])
        self.assertEqual((plan.saves[0].counts.created, plan.saves[0].counts.skipped), (0, 1), "12/3 은 판매일이 없어 건너뛴다")
        return short["change_id"], snapshot, plan_file

    def test_s7_a_sale_day_opened_since_the_preview_stops_begin(self):
        change, snapshot, plan_file = self.setup_change()
        opened = replace(snapshot, no_sale=frozenset())                    # 누가 12/3 판매일을 열었다(칸은 아직 없다)
        stale = self.cli("begin", "--change", change, "--plan", plan_file, "--snapshot", self.snap(opened, at(20)), now=30, code=1)
        self.assertEqual([(item["key"], item["then"]["state"], item["now"]) for item in stale["differences"]],
                         [({"room": "디럭스", "date": "2026-12-03", "what": "no_sale"}, "no_sale", None)])

    def test_s7_a_booking_since_the_preview_stops_the_save_before_its_press(self):
        change, snapshot, plan_file = self.setup_change()
        self.cli("begin", "--change", change, "--plan", plan_file, "--snapshot", self.snap(snapshot, at(20)), now=30)
        booked = replace(snapshot, reserved=frozenset({("디럭스", "2026-12-02")}))
        stopped = self.cli("calls", "--change", change, "--snapshot", self.snap(booked, at(40)), now=50)
        self.assertEqual((stopped["calls"], stopped["status"], [item["key"] for item in stopped["differences"]]),
                         ([], "stopped", [{"room": "디럭스", "date": "2026-12-02", "what": "reserved"}]))


class SmallParityTest(unittest.TestCase):
    """검토 2 의 9 — 아동 금액은 창의 금액 규칙대로(어긋나면 그 저장이 막힌다), 박수별 단가는 ERP 가 칸에 넣는 자릿수로, 허용 조합을 몰라
    빠질 수 있는 줄의 건너뛴 칸은 짐작으로, 「허용 인원 조합」 칸이 없으면 모름, 소문자 예전 키는 거절."""

    def plan(self, window=None, cells=None, **save):
        fields = dict(pairs=[list(BB)], price="180", occupancy_keys="A2", overwrite=True, dates=[DAY])
        fields.update(save)
        snapshot = replace(season_scene.snapshot((), pairs=[BB], dates=[DAY]), cells=cells or {key("A2"): CellValue(D("170"), None, None, "open")})
        return plan_season(snapshot, window or season_scene.window(dates=[DAY], rooms=["디럭스"]),
                           season_scene.fill_of(season_scene.save_of(fields)))

    def test_s9_a_child_amount_the_window_refuses_blocks_the_save_with_a_sentence(self):
        window = season_scene.window(bands=[{"code": "CHD", "basis": "flat", "value": "20"}], dates=[DAY], rooms=["디럭스"])
        for typed in ("1,000", "23.185", "-5"):
            save = self.plan(window, child_extra={"CHD": typed}).saves[0]
            self.assertEqual((save.refused, save.changes, save.waiting()),
                             (f"아동 추가 금액 CHD는 0 이상 숫자로, 쉼표 없이 소수 둘째 자리까지 적습니다(예: 180 · 23.18): {typed!r}", (),
                              ["ERP_REFUSES"]), typed)
        self.assertIsNone(self.plan(window, child_extra={"CHD": "23.18"}).saves[0].refused)

    def test_s9_a_nights_tier_price_is_predicted_as_the_erp_stores_it(self):
        save = self.plan(los_prices="3:160.545").saves[0]
        three = next(change.after for change in save.changes if change.key.nights == 3)
        self.assertEqual(str(three.sell), "160.55", "가격 칸은 소수 둘째 자리 — 넣을 때 반올림된다")
        self.assertEqual(str(next(change.after for change in save.changes if change.key.nights == 1).sell), "180", "짧은 값은 그대로")
        self.assertIn("정수 부분 10자리까지", self.plan(los_prices="3:12345678901").saves[0].refused)

    def test_s9_skipped_cells_of_rows_the_erp_may_leave_out_are_a_guess_in_the_count_comparison(self):
        window = replace(season_scene.window(bands=[{"code": "CHD", "basis": "flat", "value": "20"}], rooms=["디럭스"]),
                         combos={"디럭스": None})
        days = season_scene.CASES["hotel"]["season"]
        cells = {key("A2", day=day): CellValue(D("170"), None, None, "open") for day in days if day != "2026-12-03"}
        snapshot = replace(season_scene.snapshot((), pairs=[BB]), cells=cells)
        fill = season_scene.fill_of(season_scene.save_of(dict(pairs=[list(BB)], price="180", occupancy_keys="A2", child_extra={"CHD": ""})))
        counted = plan_season(snapshot, window, fill).saves[0].counts
        self.assertEqual((counted.skipped, counted.maybe_skipped), (2, 1), "12/3 의 A2 와 A2C1_CHD — 아동 줄은 ERP 가 뺄 수 있다")
        told = replace(counted, created=counted.created - counted.maybe_created, skipped=1, maybe_created=0, maybe_updated=0, maybe_skipped=0)
        self.assertTrue(counts_agree(counted, told), "ERP 가 아동 줄을 빼고 건너뛴 칸도 1개로 말해도 예상과 맞다")

    def test_s9_a_room_type_table_without_the_allowed_combinations_column_means_unknown(self):
        window = season_scene.window(rooms=["디럭스"])
        body = dict(season_scene.answer_body(window, room_types=[{"name": "디럭스", "combos": None}]), hotel=HOTEL)
        self.assertEqual(window_of(body, {}).combos, {"디럭스": None}, "칸이 없으면 모른다 — 제한 없음이 아니다")

    def test_s9_a_legacy_lowercase_key_the_save_would_overwrite_is_refused_with_a_sentence(self):
        with self.assertRaises(SeasonError) as refused:
            self.plan(cells={key("a2"): CellValue(D("170"), None, None, "open")})
        self.assertIn("인원 조합 키가 소문자인 예전 칸(`a2`)", str(refused.exception))
        self.assertIn("대문자로 고친 뒤 다시 읽습니다", str(refused.exception))


class SaleStateTest(SeasonCase):
    """검토 2 의 0 — 미리보기는 ERP 가 쓸 판매 상태를 말한다. ERP 시즌 창은 새 칸을 판매 가능으로 만들고 지속 마감(요금제 마감 · 객실
    전체 마감)이 덮는 날에만 마감으로 둔다. 셀 창에서 칸마다 마감한 날에 판매 가능한 새 칸이 생기면 빨간 줄이고, 그 뒤 그날은
    「인원·박수별 상태 다름」으로 읽혀 확인 · 되돌리기가 된다."""

    WINDOW = dict(bands=[{"code": "CHD", "basis": "flat", "value": "30"}], dates=[DAY], rooms=["디럭스"])
    SAVE = [{"pairs": [{"room": BB[0], "rate_plan": BB[1]}], "price": "180", "occupancy_keys": "A2", "child_extra": {"CHD": ""},
             "overwrite": True}]

    def test_s1_new_cells_on_a_day_closed_cell_by_cell_go_on_sale_and_that_is_a_red_line(self):
        window = season_scene.window(**self.WINDOW)
        before = {key("A2"): CellValue(D("170"), None, None, "closed")}            # 셀 창에서 마감(「기존 가격 마감」 — 지속 마감 아님)
        snapshot = replace(season_scene.snapshot((), pairs=[BB], dates=[DAY]), cells=before)
        short, plan, first_file = self.plan(window, snapshot, self.SAVE)
        new = next(change for change in plan.saves[0].changes if change.before.state == "missing")
        self.assertEqual((new.key.occupancy, str(new.after.sell), new.after.state), ("A2C1_CHD", "210.00", "open"),
                         "ERP 는 새 칸을 판매 가능으로 만든다 — 그날 다른 칸이 셀 창에서 마감이어도")
        [rule] = [rule for rule in short["per_save"][0]["rules"] if rule["rule"] == "OPENS_ON_CLOSED_DAY"]
        self.assertEqual((rule["cells"], rule["choices"], short["saves"]), (1, ["include", "exclude_dates"], None))
        self.assertIn("손님이 그 칸으로 예약할 수 있습니다", rule["said"])
        page = self.cli("render", "preview", "--plan", first_file, "--text")["text"]
        self.assertIn(rule["said"], page, "미리보기의 빨간 띠가 도우미의 말과 같다")

        chosen, plan, plan_file = self.plan(window, snapshot, self.SAVE, choices=[
            {"save": 1, "rule": "OPENS_ON_CLOSED_DAY", "choice": "include", "said": "그래도 채워"},
            {"save": 1, "rule": "NEW_ROW", "choice": "include", "said": "그래도 채워"}])
        self.assertEqual(chosen["saves"], 1, chosen)
        change = chosen["change_id"]
        self.cli("begin", "--change", change, "--plan", plan_file, "--snapshot", self.snap(snapshot, at(20)), now=30)
        [call] = self.cli("calls", "--change", change, "--snapshot", self.snap(snapshot, at(40)), now=50)["calls"]
        self.cli("record-result", "--change", change, "--result", self.write("r1.json", self.saved_answer(call, plan.saves[0])), now=60)
        # 저장 뒤 그날은 마감 칸(A2)과 판매 가능 칸(A2C1_CHD)이 섞여 화면이 「인원·박수별 상태 다름」 — 읽은 값은 그날 칸을 모두 mixed 로
        after = replace(snapshot, cells={key("A2"): CellValue(D("180"), None, None, "mixed"),
                                         key("A2C1_CHD"): CellValue(D("210"), None, None, "mixed")})
        verified = self.cli("verify", "--change", change, "--snapshot", self.snap(after, at(70)), now=75)
        self.assertEqual((verified["same"], verified["state_only"]), (True, []), verified)
        rollback = self.cli("rollback", "--change", change, "--snapshot", self.snap(after, at(80)), "--record",
                            "--out", self.dir / "rollback-1.json", now=85)
        self.assertEqual((rollback["restored"], rollback["unremovable"]), (1, 1), "A2 는 되돌리고 새 A2C1_CHD 는 지울 수 없다")

    def test_s1_a_new_cell_on_a_sales_closure_day_is_closed_even_where_the_pair_had_no_cell(self):
        window = season_scene.window(**self.WINDOW)
        snapshot = replace(season_scene.snapshot((), pairs=[BB], dates=[DAY], closures=[(BB[0], BB[1], DAY)]), cells={})
        short, plan, plan_file = self.plan(window, snapshot, self.SAVE, choices=[
            {"save": 1, "rule": "NEW_ROW", "choice": "include", "said": "그래도 채워"}])
        self.assertEqual({change.key.occupancy: change.after.state for change in plan.saves[0].changes},
                         {"A2": "closed", "A2C1_CHD": "closed"}, "요금제 마감인 날 — ERP 가 새 칸을 마감으로 만든다")
        self.assertEqual((short["counts"]["closed_new"], short["saves"]), (2, 1))
        self.assertNotIn("OPENS_ON_CLOSED_DAY", {rule["rule"] for rule in short["per_save"][0]["rules"]})
        self.assertIn("판매 마감 날에 새로 생기는 칸", self.cli("render", "preview", "--plan", plan_file, "--text")["text"])
        change = short["change_id"]
        self.cli("begin", "--change", change, "--plan", plan_file, "--snapshot", self.snap(snapshot, at(20)), now=30)
        [call] = self.cli("calls", "--change", change, "--snapshot", self.snap(snapshot, at(40)), now=50)["calls"]
        self.cli("record-result", "--change", change, "--result", self.write("r1.json", self.saved_answer(call, plan.saves[0])), now=60)
        closed = applied(snapshot, plan)
        self.assertTrue(self.cli("verify", "--change", change, "--snapshot", self.snap(closed, at(70)), now=75)["same"])
        opened = replace(closed, cells={cell: replace(value, state="open") for cell, value in closed.cells.items()})
        told = self.cli("verify", "--change", change, "--snapshot", self.snap(opened, at(80)), now=85, code=1)
        self.assertEqual([(item["want"], item["seen"]) for item in told["state_only"]], [("closed", "open")] * 2)


class PressOnFreshReadingTest(SeasonCase):
    """검토 2 의 2 · 3 — 시즌 창 저장은 calls 가 그 범위를 방금 읽은 값으로 낸 부를 값으로만, 그 기한 안에만 누른다. 같은 읽은 값으로
    부를 값을 두 번 내지 않고, 누른 답을 잃은 뒤의 calls 는 「이미 된 것으로 보입니다」라고 답하며 장부에 거짓을 적지 않는다. 된
    누름은 언제 적어도 받는다."""

    def setup_change(self):
        window = season_scene.window(dates=[DAY], rooms=["디럭스"])
        ro = ("디럭스", "룸온리")
        before = {key("A2"): CellValue(D("180"), None, None, "open"), key("A2", pair=ro): CellValue(D("172"), None, None, "open")}
        snapshot = replace(season_scene.snapshot((), pairs=[BB, ro], dates=[DAY]), cells=before)
        short, plan, plan_file = self.plan(window, snapshot, [{"pairs": [{"room": BB[0], "rate_plan": BB[1]}, {"room": ro[0], "rate_plan": ro[1]}],
                                                               "price": "181", "occupancy_keys": "A2", "plan_adjust": "-8", "overwrite": True}])
        change = short["change_id"]
        self.cli("begin", "--change", change, "--plan", plan_file, "--snapshot", self.snap(snapshot, at(20)), now=30)
        return change, snapshot, plan, plan_file

    def test_s4_the_payload_carries_the_deadline_of_its_reading_and_one_reading_gives_one_payload(self):
        change, snapshot, _plan, _plan_file = self.setup_change()
        reading = self.snap(snapshot, at(40))
        given = self.cli("calls", "--change", change, "--snapshot", reading, now=50)
        [call] = given["calls"]
        deadline = int((datetime.fromisoformat(at(40)).timestamp() + 120) * 1000)
        self.assertEqual((call["payload"]["freshUntil"], given["fresh"]["seconds"]), (deadline, 10), "읽은 때부터 120초 — 페이지가 이 기한을 본다")
        again = self.cli("calls", "--change", change, "--snapshot", reading, now=55, code=2)
        self.assertIn("이 읽은 값", again["error"])
        self.assertIn("이미 냈습니다", again["error"])

    def test_s4_a_payload_not_issued_by_calls_is_refused_and_an_issued_press_is_recorded_whatever_its_age(self):
        change, snapshot, plan, plan_file = self.setup_change()
        stored = json.loads(Path(plan_file).read_text(encoding="utf-8"))["steps"][0]["body"]["payload"]
        self.assertNotIn("freshUntil", stored, "계산 파일의 페이로드에는 기한이 없다 — 페이지가 누르지 않는다")
        fake = self.write("fake.json", {"op": "applySeason", "no": 1, "ask": ask_sum(dict(stored, no=1)), "saved": True, "pressed": True,
                                        "ok": True})
        self.assertIn("calls 가 낸 부를 값의 답이 아닙니다", self.cli("record-result", "--change", change, "--result", fake, now=40, code=2)["error"])
        [call] = self.cli("calls", "--change", change, "--snapshot", self.snap(snapshot, at(40)), now=50)["calls"]
        expired = self.cli("record-result", "--change", change, "--result", self.answer(call, ok=False, saved=False, pressed=False, expired=True,
                                                                                       error="이 부를 값의 기한이 지났습니다"), now=200)
        self.assertEqual((expired["started"], expired["expired"], expired["status"]), (False, True, "applying"), "기한이 지난 거절은 적지 않는다")
        late = self.cli("record-result", "--change", change, "--result", self.write("late.json", self.saved_answer(call, plan.saves[0])), now=700)
        self.assertEqual((late["saved"], late["status"]), (True, "applied"), "누른 저장은 10분 뒤에 적어도 받는다")

    def test_s3_a_second_calls_after_a_press_whose_answer_was_lost_says_already_saved_and_writes_nothing(self):
        change, snapshot, plan, _plan_file = self.setup_change()
        self.cli("calls", "--change", change, "--snapshot", self.snap(snapshot, at(40)), now=50)   # 눌렀고 저장됐는데 답을 잃었다
        landed = applied(snapshot, plan)
        answer = self.cli("calls", "--change", change, "--snapshot", self.snap(landed, at(80)), now=90)
        self.assertEqual((answer["calls"], answer["saved_already"], answer["status"]), ([], 1, "applying"), answer)
        self.assertIn("이미 된 것으로 보입니다", answer["said"])
        listed = next(item for item in self.cli("list", "--all", now=95)["changes"] if item["id"] == change)
        self.assertEqual((listed["status"], listed["saved_steps"]), ("applying", 0), "장부에 「그 사이 바뀜」을 적지 않았다")
        checked = self.cli("check", "--change", change, "--snapshot", self.snap(landed, at(100)), now=105)
        self.assertEqual((checked["status"], checked["steps"][0]["ledger"], checked["steps"][0]["settled"]), ("applied", "pending", "saved"))
        self.assertEqual(self.cli("rollback", "--change", change, "--snapshot", self.snap(landed, at(110)), "--record",
                                  "--out", self.dir / "rollback-1.json", now=115)["restored"], 2, "저장된 것으로 적혀 되돌릴 수 있다")


class UnknownSaveTest(SeasonCase):
    """검토 2 의 page 2 · 4 · 7 — 「모름」으로 끝난 시즌 저장 뒤: 그 저장이 「공급 통화 없음」 띠와 함께 끝났으면 다시 읽은 시즌 창(check
    --season)으로 변경이 멈춘다, ERP 가 늦게 거절한 그 창은 그 저장의 답(lateSave)으로 적힌다, 시즌 목록의 띠는 그 뒤에 누른 저장이
    있으면 누구의 띠인지 말하지 않는다."""

    def two_saves(self):
        window = season_scene.window(dates=[DAY], rooms=["디럭스"])
        ro = ("디럭스", "룸온리")
        before = {key("A2"): CellValue(D("180"), None, None, "open"), key("A2", pair=ro): CellValue(D("172"), None, None, "open")}
        snapshot = replace(season_scene.snapshot((), pairs=[BB, ro], dates=[DAY]), cells=before)
        saves = [{"pairs": [{"room": pair[0], "rate_plan": pair[1]}], "price": price, "occupancy_keys": "A2", "overwrite": True}
                 for pair, price in ((BB, "190"), (ro, "175"))]
        short, plan, plan_file = self.plan(window, snapshot, saves)
        change = short["change_id"]
        self.cli("begin", "--change", change, "--plan", plan_file, "--snapshot", self.snap(snapshot, at(20)), now=30)
        [call] = self.cli("calls", "--change", change, "--snapshot", self.snap(snapshot, at(40)), now=50)["calls"]
        self.cli("record-result", "--change", change, "--result", self.answer(call, ok=False, saved="unknown", error="모름"), now=60)
        return window, snapshot, plan, change, call

    def test_page2_an_unknown_save_that_ended_with_the_no_supply_banner_stops_the_change_at_check(self):
        window, snapshot, plan, change, _call = self.two_saves()
        landed = applied(snapshot, plan, saves={1})
        warn = "공급 통화가 없어 가격 원장을 기록하지 못했습니다. 이대로는 팔리지 않으니 기본정보에서 통화를 지정한 뒤 다시 적용해주세요."
        early = self.cli("check", "--change", change, "--snapshot", self.snap(landed, at(70)), "--season", self.season_after(window, 55, warn),
                         now=75, code=2)
        self.assertIn("앞에 읽은 것", early["error"], "「모름」 앞에 읽은 시즌 창은 그 저장의 띠를 모른다")
        checked = self.cli("check", "--change", change, "--snapshot", self.snap(landed, at(70)), "--season", self.season_after(window, 65, warn),
                           now=75)
        self.assertEqual((checked["status"], checked["cause"], checked["can_continue"], checked["note"]), ("stopped", "halted", False, warn))
        self.assertEqual(checked["steps"][0]["settled"], "saved")
        self.assertIn(f"{change}번 변경은 멈춰 있습니다",
                      self.cli("calls", "--change", change, "--snapshot", self.snap(landed, at(80)), now=85, code=2)["error"])

    def test_page4_a_late_refusal_of_an_unknown_save_is_recorded_as_that_save_with_the_erp_text(self):
        _window, _snapshot, _plan, change, call = self.two_saves()
        late = self.answer(call, ok=False, saved=False, refused=True, late=True, error="시즌 창이 저장을 거절했습니다 — 조정 값은 부호를 붙여 주세요",
                           errors=["조정 값은 부호를 붙여 주세요"])
        recorded = self.cli("record-result", "--change", change, "--result", late, now=70)
        self.assertEqual((recorded["saved"], recorded["status"]), (False, "stopped"))
        line = next(item for item in self.cli("list", "--all", now=71)["changes"] if item["id"] == change)
        self.assertEqual(line["status"], "stopped")
        step = self.cli("check", "--change", change, "--snapshot", self.snap(_snapshot, at(80)), now=85)
        self.assertEqual((step["cause"], step["note"]), ("failed", "시즌 창이 저장을 거절했습니다 — 조정 값은 부호를 붙여 주세요"),
                         "「모름」이 아니라 ERP 의 거절 문장으로 멈춘 저장이다(그래서 --season 없이 가린다)")

    def test_page7_the_season_list_banner_is_not_named_as_a_save_when_a_later_press_did_not_settle(self):
        window = season_scene.window(dates=[DAY], rooms=["디럭스"])
        ro = ("디럭스", "룸온리")
        before = {key("A2"): CellValue(D("180"), None, None, "open"), key("A2", pair=ro): CellValue(D("172"), None, None, "open")}
        snapshot = replace(season_scene.snapshot((), pairs=[BB, ro], dates=[DAY]), cells=before)
        saves = [{"pairs": [{"room": pair[0], "rate_plan": pair[1]}], "price": price, "occupancy_keys": "A2", "overwrite": True}
                 for pair, price in ((BB, "190"), (ro, "175"))]
        short, plan, plan_file = self.plan(window, snapshot, saves)
        change = short["change_id"]
        self.cli("begin", "--change", change, "--plan", plan_file, "--snapshot", self.snap(snapshot, at(20)), now=30)
        [call1] = self.cli("calls", "--change", change, "--snapshot", self.snap(snapshot, at(40)), now=50)["calls"]
        first = self.saved_answer(call1, plan.saves[0])
        self.cli("record-result", "--change", change, "--result", self.write("r1.json", first), now=60)
        folder = self.window_answers(window, "작업/띠-1", banner=first["banner"], done=62)
        self.assertEqual(self.cli("season", "--answers", folder, "--out", self.dir / "s-1.json", now=63)["banner"],
                         f"장부 {change}번 1번째 저장의 띠: {first['banner']}", "가장 늦게 누른 저장의 띠 — 그 저장의 수다")
        [call2] = self.cli("calls", "--change", change, "--snapshot", self.snap(applied(snapshot, plan, saves={1}), at(70)), now=75)["calls"]
        folder = self.window_answers(window, "작업/띠-2", banner=first["banner"], done=80)
        self.assertIsNone(self.cli("season", "--answers", folder, "--out", self.dir / "s-2.json", now=81)["banner"],
                          "2번째 저장의 부를 값을 낸 뒤라 띠가 그 저장의 것일 수 있다 — 누구의 띠인지 말하지 않는다")
        self.cli("record-result", "--change", change, "--result", self.answer(call2, ok=False, saved="unknown", error="모름"), now=85)
        folder = self.window_answers(window, "작업/띠-3", banner=first["banner"], done=90)
        self.assertIsNone(self.cli("season", "--answers", folder, "--out", self.dir / "s-3.json", now=91)["banner"],
                          "「모름」인 2번째 저장 뒤의 띠는 1번째 저장의 수로 읽어 주지 않는다")


class StoppedPageWordsTest(SeasonCase):
    """W 보고 5 의 남은 것 — 멈춘 시즌 변경의 결과 페이지 「고르신 빨간 줄」은 규칙 코드가 아니라 쉬운 말이다."""

    def test_s13_the_stopped_season_result_page_names_chosen_rules_in_plain_words(self):
        window = season_scene.window(dates=[DAY], rooms=["디럭스"])
        snapshot = replace(season_scene.snapshot((), pairs=[BB], dates=[DAY]), cells={key("A2"): CellValue(D("180"), None, None, "open")})
        short, _plan, plan_file = self.plan(window, snapshot, [{"pairs": [{"room": BB[0], "rate_plan": BB[1]}], "price": "190",
                                                                "occupancy_keys": "A2", "los_prices": "3:170", "overwrite": True}],
                                            choices=[{"save": 1, "rule": "NEW_ROW", "choice": "include", "said": "3박 줄 생겨도 돼"}])
        change = short["change_id"]
        self.cli("begin", "--change", change, "--plan", plan_file, "--snapshot", self.snap(snapshot, at(20)), now=30)
        [call] = self.cli("calls", "--change", change, "--snapshot", self.snap(snapshot, at(40)), now=50)["calls"]
        self.cli("record-result", "--change", change, "--result", self.answer(call, ok=False, saved=False, refused=True,
                                                                             error="시즌 창이 저장을 거절했습니다 — 조정 값은 부호를 붙여 주세요"), now=60)
        page = self.cli("render", "result", "--change", change, "--text", now=70)["text"]
        self.assertIn("고르신 빨간 줄", page)
        self.assertIn("이 객실 · 요금제에 없던 인원 조합 · 박수 줄이 생깁니다 | 이대로 채움", page)
        self.assertNotIn("NEW_ROW", page)


if __name__ == "__main__":
    unittest.main()
