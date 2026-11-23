"""검토 2 의 시즌 다시 채우기 쪽 — 명령으로 한 바퀴씩. 페이지의 답은 `browser_replies` 와 `season_scene` 으로 만들고, 장부의 시계는
명령마다 STAY_PRICE_TEST_NOW 로 세운다(test_season_flow 의 FlowBase).

    python3 -m unittest discover -s tests
"""

import json
import sys
import unittest
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import season_scene  # noqa: E402
from change_core.answers import ask_sum  # noqa: E402
from price_model import CellKey, CellValue  # noqa: E402
from price_season import decode_plan, encode_window  # noqa: E402
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
        checked = self.cli("check", "--change", change, "--snapshot", self.snap(landed, at(70)), now=75)
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
        checked = self.cli("check", "--change", change, "--snapshot", self.snap(snapshot, at(70)), now=75)
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


if __name__ == "__main__":
    unittest.main()
