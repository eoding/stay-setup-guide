"""시즌 다시 채우기 한 바퀴 — 명령으로: 창 읽기 → 요청(말씀으로 · 요금표에서) → 읽기 범위 → 미리보기 → 고름(이대로 · 그 날은 빼고) →
적용 시작 → 저장마다 그 범위를 다시 읽고 → 저장 → 확인 → 되돌리기 → 확인. 그리고 저장이 호출보다 오래 걸려 「모름」이 된 것을 check 가
가리는 길, 120초보다 오래된 읽은 값 · 그 사이 바뀐 칸으로는 저장을 내지 않는 것.

페이지의 답은 `browser_replies` 와 `season_scene.answer_body` 로 만든다(페이지 모듈이 그 모양을 내는 것은 tests/test_page_season.mjs ·
test_page_season_contract.mjs 가 본다). 장부의 시계는 명령마다 STAY_PRICE_TEST_NOW 로 세운다.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
import season_scene  # noqa: E402
from browser_replies import done_at, reply  # noqa: E402
from change_core.answers import ask_sum  # noqa: E402
from change_core.ledger import CLOCK_ENV  # noqa: E402
from price_model import CellKey, CellValue, decode_snapshot, encode_snapshot  # noqa: E402
from price_season import decode_plan  # noqa: E402

T0 = datetime.fromisoformat("2026-11-21T10:00:00+09:00")
HOTEL = {"id": season_scene.HOTEL_ID, "name": season_scene.HOTEL}


def at(seconds: int) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat()


class FlowBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = scene.env(str(self.dir / "기록"))
        self.files = 0

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data) -> str:
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def cli(self, *args, code=0, now=0):
        env = dict(self.env, **{CLOCK_ENV: at(now)})
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def snap(self, snapshot, read_at) -> str:
        self.files += 1
        return self.write(f"snap-{self.files}.json", encode_snapshot(replace(snapshot, read_at=read_at)))

    def window_answers(self, window, folder: str, others=()) -> str:
        """readSeason 의 답(창 하나)과, 같은 오퍼의 다른 시즌마다 datesOnly 답 — 폴더에 둔다."""
        asked = {"hotel": HOTEL, "offer": window.offer, "season": {"id": window.season_id}}
        for index, item in enumerate(reply("readSeason", asked, keep=season_scene.answer_body(window), doneAt=done_at(T0))):
            self.write(f"{folder}/{'season-1' if index == 0 else f'take-w{index}'}.json", item)
        for number, other in enumerate(others, 2):
            asked = {"hotel": HOTEL, "offer": window.offer, "season": {"id": other.id, "name": other.name}, "datesOnly": True}
            body = {"offer": window.offer, "season": {"id": other.id, "name": other.name, "days": str(len(other.dates))}, "dates": list(other.dates)}
            for index, item in enumerate(reply("readSeason", asked, keep=body, body_id=f"d{number}", doneAt=done_at(T0))):
                self.write(f"{folder}/{f'season-{number}' if index == 0 else f'take-d{number}-{index}'}.json", item)
        return str(self.dir / folder)

    def saved_answer(self, call, plan_save, **over):
        counts = plan_save.counts
        banner = (f"가격을 넣었습니다 — 새로 {counts.created}칸 · 덮어쓴 {counts.updated}칸 (룸 {counts.rooms}개 × {counts.days}일)."
                  + (f" 판매일이 없어 건너뛴 칸 {counts.skipped}개 — 판매일 탭에서 날짜를 먼저 여세요." if counts.skipped else ""))
        answer = {"ok": True, "op": "applySeason", "no": call["no"], "ask": ask_sum(call["payload"]), "saved": True, "pressed": True,
                  "note": "저장했습니다", "banner": banner,
                  "counts": {"created": counts.created, "updated": counts.updated, "rooms": counts.rooms, "days": counts.days,
                             "skipped": counts.skipped}}
        answer.update(over)
        return answer


def applied(snapshot, plan, saves=None):
    """ERP 가 저장(들)을 받은 뒤의 칸 — 계산이 예상한 값 그대로."""
    cells = dict(snapshot.cells)
    for save in plan.live:
        if saves is None or save.index in saves:
            cells.update({change.key: change.after for change in save.changes})
    return replace(snapshot, cells=cells)


class OneDaySeasonTest(FlowBase):
    """하루짜리 시즌을 말씀으로 — 디럭스 두 요금제를 한 번에(요금제 조정 -8)."""

    def test_words_to_preview_apply_verify_rollback_and_list(self):
        window = season_scene.window(dates=["2026-12-31"], rooms=["디럭스"],
                                     others=[("590", "Normal", tuple(f"2026-12-{day:02d}" for day in range(1, 31)))])
        folder = self.window_answers(window, "작업/시즌", window.seasons)
        asked = self.cli("season", "--answers", f"{folder}/season-1.json", "--answers", f"{folder}/take-w1.json",
                         "--answers", f"{folder}/take-w2.json", "--answers", f"{folder}/take-w3.json", code=2)
        self.assertEqual(asked["ask"], [{"hotel": HOTEL, "offer": window.offer, "season": {"id": "590", "name": "Normal"}, "datesOnly": True}],
                         "S1 · 같은 오퍼의 다른 시즌 날을 읽으라고 묻는다")
        short = self.cli("season", "--answers", folder, "--out", self.dir / "season.json")
        self.assertEqual((short["dates"]["count"], short["other_seasons"]), (1, [{"name": "Normal", "days": 30}]))
        before = {CellKey("디럭스", "조식 포함", "2026-12-31", "A2", 1): CellValue(D("180"), None, None, "open"),
                  CellKey("디럭스", "룸온리", "2026-12-31", "A2", 1): CellValue(D("172"), None, None, "open")}
        snapshot = replace(season_scene.snapshot((), pairs=[("디럭스", "조식 포함"), ("디럭스", "룸온리")], dates=["2026-12-31"]), cells=before)
        request = self.write("request.json", {"kind": "season_fill", "hotel": HOTEL, "offer": window.offer,
                                              "season": {"id": window.season_id, "name": window.season_name}, "currency": "USD",
                                              "sentence": "Peak 시즌 디럭스 181 로 다시 채워줘, 룸온리는 8 싸게",
                                              "saves": [{"pairs": [{"room": "디럭스", "rate_plan": "조식 포함"}, {"room": "디럭스", "rate_plan": "룸온리"}],
                                                         "price": "181", "occupancy_keys": "A2", "plan_adjust": "-8", "overwrite": True,
                                                         "sources": {"price": "말씀", "plan_adjust": "말씀"}}]})
        calls = self.cli("read-calls", "--request", request, "--season", self.dir / "season.json")
        self.assertEqual({(call["room"], call["ratePlan"], call["from"], call["to"]) for call in calls["pairs"]},
                         {("디럭스", "조식 포함", "2026-12-31", "2026-12-31"), ("디럭스", "룸온리", "2026-12-31", "2026-12-31")})
        plan_short = self.cli("plan", "--snapshot", self.snap(snapshot, at(-60)), "--request", request, "--season", self.dir / "season.json",
                              "--record", "--out", self.dir / "plan-1.json")
        change = plan_short["change_id"]
        self.assertEqual((plan_short["saves"], plan_short["counts"]["changes"], plan_short["counts"]["new"]), (1, 2, 0))
        plan = decode_plan(json.loads((self.dir / "plan-1.json").read_text(encoding="utf-8"))["plan"])
        self.assertEqual(sorted(str(change.after.sell) for change in plan.changes), ["173.00", "181"])
        page = Path(self.cli("render", "preview", "--plan", self.dir / "plan-1.json")["page"]).read_text(encoding="utf-8")
        for words in ("시즌 「Peak」 다시 채우기", "「181」", "「-8」", "몇 초", "dry run", "지우기", "켜지 않음", "덮인 칸이 원래 어느 시즌"):
            self.assertIn(words, page)
        self.assertNotIn("지금 값", page, "A5 — 미리 읽은 값을 「지금」이라고 하지 않는다")

        self.assertEqual(self.cli("begin", "--change", change, "--plan", self.dir / "plan-1.json", "--snapshot", self.snap(snapshot, at(30)),
                                  now=40)["status"], "applying")
        step_range = self.cli("read-calls", "--record", change, "--step", 1)
        self.assertEqual(len(step_range["pairs"]), 2)
        stale = self.cli("calls", "--change", change, "--snapshot", self.snap(snapshot, at(30)), now=151, code=2)
        self.assertIn("121초 전 것입니다", stale["error"], "A2 — 120초보다 오래된 읽은 값으로는 저장을 내지 않는다")
        given = self.cli("calls", "--change", change, "--snapshot", self.snap(snapshot, at(50)), now=60)
        [call] = given["calls"]
        self.assertEqual((call["op"], call["no"], given["fresh"]["seconds"]), ("applySeason", 1, 10))
        self.assertIn(["overwrite", "on"], call["payload"]["want"])
        self.assertNotIn("stale_cleanup", [name for name, _value in call["payload"]["want"]])
        result = self.cli("record-result", "--change", change, "--result", self.write("r1.json", self.saved_answer(call, plan.saves[0])), now=70)
        self.assertEqual((result["saved"], result["status"]), (True, "applied"))
        after = applied(snapshot, plan)
        verified = self.cli("verify", "--change", change, "--snapshot", self.snap(after, at(80)), now=90)
        self.assertTrue(verified["same"], verified)
        self.assertEqual(verified["counts"][0]["told"], {"created": 0, "updated": 2, "skipped": 0})
        result_page = Path(self.cli("render", "result", "--change", change, now=95)["page"]).read_text(encoding="utf-8")
        self.assertIn("적용했고, 다시 읽어 확인했습니다.", result_page)
        self.assertIn("새로 0칸 · 덮어쓴 2칸", result_page)

        rollback = self.cli("rollback", "--change", change, "--snapshot", self.snap(after, at(100)), "--record", "--sentence", "방금 시즌 채운 거 되돌려",
                            "--out", self.dir / "rollback.json", now=110)
        self.assertEqual((rollback["restored"], rollback["unremovable"]), (2, 0))
        rollback_page = Path(self.cli("render", "rollback", "--plan", self.dir / "rollback.json", now=111)["page"]).read_text(encoding="utf-8")
        self.assertIn("채우기 전에 시즌 창에 있던 입력값", rollback_page)
        self.assertIn("되돌린 뒤 누가 이 시즌을", rollback_page)
        self.assertEqual(self.cli("begin", "--change", rollback["change_id"], "--plan", self.dir / "rollback.json",
                                  "--snapshot", self.snap(after, at(120)), now=125)["status"], "applying")
        for call in self.cli("calls", "--change", rollback["change_id"], now=126)["calls"]:
            answer = {"ok": True, "op": call["op"], "no": call["no"], "ask": ask_sum(call["payload"]), "saved": True, "pressed": True,
                      "note": "저장했습니다"}
            last = self.cli("record-result", "--change", rollback["change_id"], "--result", self.write(f"rb{call['no']}.json", answer), now=130)
        self.assertEqual(last["status"], "applied")
        self.assertTrue(self.cli("verify", "--change", rollback["change_id"], "--snapshot", self.snap(snapshot, at(140)), now=150)["same"])
        listed = self.cli("list", "--all", now=160)
        line = next(item["line"] for item in listed["changes"] if item["id"] == change)
        self.assertIn("시즌 「Peak」 다시 채우기(덮기) · 저장 1번", line)
        self.assertIn("모두 되돌림 2/2칸", line)


class SheetSeasonTest(FlowBase):
    """다섯 날 시즌을 요금표로 — 예약 있는 날 · 판매 마감 칸 · 판매일 없는 날 · 아동 칸 · 3박 층, 저장 둘. 둘째 저장은 답이 늦어 「모름」 →
    다시 읽어 check 가 저장됨으로 가린다."""

    DAYS = season_scene.CASES["hotel"]["season"]
    PAIRS = [("디럭스", "조식 포함"), ("디럭스", "룸온리"), ("스위트", "조식 포함")]

    def before(self):
        cells = {}
        prices = {("디럭스", "조식 포함"): D("190"), ("디럭스", "룸온리"): D("180"), ("스위트", "조식 포함"): D("290")}
        for (room, plan), base in prices.items():
            for day in self.DAYS:
                if room == "디럭스" and day == "2026-12-03":
                    continue
                state = "closed" if (room, plan, day) == ("디럭스", "조식 포함", "2026-12-04") else "open"
                for occupancy, nights, value in (("A2", 1, base), ("A3", 1, base + 50), ("A2C1_CHD", 1, base + 20), ("A2", 3, base - 20)):
                    cells[CellKey(room, plan, day, occupancy, nights)] = CellValue(value, None, None, state)
        return replace(season_scene.snapshot((), pairs=self.PAIRS, reserved={("디럭스", "2026-12-02")}), cells=cells)

    def sheet(self):
        line = lambda no, room, plan, base, special=None: {   # noqa: E731
            "room": room, "rate_plan": plan, "season": "Peak", "periods": [{"from": "2026-12-01", "to": "2026-12-05"}],
            "rows": [{"occupancy": "A2", "nights": 1, "sell": str(base)}, {"occupancy": "A3", "nights": 1, "sell": {"from": {"occupancy": "A2"}, "add": "60"}},
                     {"occupancy": "A2C1", "nights": 1, "sell": {"from": {"occupancy": "A2"}, "add": "25"}},
                     {"occupancy": "A2", "nights": 3, "sell": str(base - 20)}]}
        lines = [line(1, "디럭스", "조식 포함", 200), line(2, "디럭스", "룸온리", 190), line(3, "스위트", "조식 포함", 300)]
        special = {"room": "디럭스", "rate_plan": "조식 포함", "season": "연말 특가", "periods": [{"from": "2026-12-05", "to": "2026-12-05"}],
                   "rows": [{"occupancy": "A2", "nights": 1, "sell": "210"}, {"occupancy": "A3", "nights": 1, "sell": {"from": {"occupancy": "A2"}, "add": "60"}},
                            {"occupancy": "A2C1", "nights": 1, "sell": {"from": {"occupancy": "A2"}, "add": "25"}},
                            {"occupancy": "A2", "nights": 3, "sell": "180"}]}
        lines[0]["periods"] = [{"from": "2026-12-01", "to": "2026-12-04"}]
        return {"kind": "sheet", "hotel": HOTEL, "offer": season_scene.OFFER, "currency": "USD", "sentence": "새 요금표대로 Peak 다시 채워줘",
                "lines": lines + [special]}

    def test_sheet_to_two_saves_with_choices_unknown_settled_by_check_and_verify(self):
        window = season_scene.window(bands=[{"code": "CHD", "basis": "flat", "value": "20"}])
        folder = self.window_answers(window, "작업/시즌")
        self.cli("season", "--answers", folder, "--out", self.dir / "season.json")
        look = self.write("look.json", {"hotel": HOTEL, "offer": season_scene.OFFER,
                                        "pairs": [{"room": room, "rate_plan": plan} for room, plan in self.PAIRS]})
        sheet = self.write("sheet.json", self.sheet())
        self.cli("sheet", "--sheet", sheet, "--look", look, "--out", self.dir / "sheet-check.json")
        proposed = self.cli("season-request", "--sheet", self.dir / "sheet-check.json", "--season", self.dir / "season.json",
                            "--out", self.dir / "request.json")
        self.assertEqual([(len(save["pairs"]), save["inputs"]) for save in proposed["saves"]],
                         [(2, {"price": "200", "plan_adjust": "-10", "occupancy_keys": "A2,A3", "occupancy_adjust": "A3:+60", "los_prices": "3:180"}),
                          (1, {"price": "300", "occupancy_keys": "A2,A3", "occupancy_adjust": "A3:+60", "los_prices": "3:280"})],
                         "A1 — 명령이 요금표에서 창의 입력을 셈한다(금액 차이 · 요금제 조정 · 박수 층)")
        self.assertEqual([save["child_extra"] for save in proposed["saves"]], [{"CHD": "25"}, {"CHD": "25"}])
        request = json.loads((self.dir / "request.json").read_text(encoding="utf-8"))
        self.assertIn("요금표 1번째", request["saves"][0]["sources"]["price"], "A1 — 입력마다 어디서 왔는지 적는다")
        snapshot = self.before()
        first = self.cli("plan", "--snapshot", self.snap(snapshot, at(-60)), "--request", self.dir / "request.json",
                         "--season", self.dir / "season.json", "--record", "--out", self.dir / "plan-1.json")
        self.assertIsNone(first["saves"], "빨간 줄이 남아 저장 횟수를 말하지 않는다")
        rules = {save["save"]: {rule["rule"] for rule in save["rules"]} for save in first["per_save"]}
        self.assertIn("SHEET_DIFFERS", rules[1], "A1 — 12/5 특가는 시즌 창으로 만들 수 없어 다르게 채워지는 칸이다")
        self.assertIn("NEW_ROW", rules[1])
        self.assertGreater(first["misses"], 0)
        page = Path(self.cli("render", "preview", "--plan", self.dir / "plan-1.json")["page"]).read_text(encoding="utf-8")
        self.assertIn("요금표와 다르게 채워지는 칸", page)
        choices = self.write("choices.json", [
            {"save": 1, "rule": "SHEET_DIFFERS", "choice": "include", "said": "그대로 채우고 12/5 는 따로 맞춰"},
            {"save": 1, "rule": "NEW_ROW", "choice": "include", "said": "새 줄 생겨도 돼"},
            {"save": 1, "rule": "reserved", "choice": "exclude_dates", "said": "예약 있는 날은 빼"},
            {"save": 2, "rule": "NEW_ROW", "choice": "include", "said": "새 줄 생겨도 돼"}])
        second = self.cli("plan", "--snapshot", self.snap(snapshot, at(-60)), "--request", self.dir / "request.json",
                          "--season", self.dir / "season.json", "--resolutions", choices, "--record", "--replaces", first["change_id"],
                          "--out", self.dir / "plan-2.json")
        self.assertEqual(second["saves"], 2, second)
        change = second["change_id"]
        data = json.loads((self.dir / "plan-2.json").read_text(encoding="utf-8"))
        plan = decode_plan(data["plan"])
        self.assertEqual(plan.saves[0].excluded, ("2026-12-02",), "예약 있는 날을 빼고 다시 셈했다")
        self.assertFalse(any(change.key.date == "2026-12-02" for change in plan.saves[0].changes))
        self.assertTrue(any("closed" in change.marks and change.after.state == "closed" for change in plan.saves[0].changes),
                        "판매 마감인 칸은 값만 바뀐다")
        self.assertEqual(plan.saves[0].counts.skipped, 2 * 2 * 4,
                         "판매일 없는 12/3 은 요금제 2 × 박수 층 2 × 인원 4(A2 · A3 · 아동 둘)칸을 건너뛴다")
        self.assertEqual(data["followup"]["kind"], "targets", "A1 — 다르게 채워지는 칸을 날짜별로 맞출 목표 값 표가 계산 파일에 있다")
        self.assertEqual({item["key"]["date"] for item in data["followup"]["targets"]}, {"2026-12-05"},
                         "12/5 특가의 칸만 — 빼라고 한 예약 있는 날(12/2)의 칸은 내놓지 않는다")
        step2_form = data["steps"][1]["body"]["payload"]["form"]
        self.assertIn(["price", "200"], step2_form, "둘째 저장의 창은 첫 저장이 친 값으로 채워져 열린다")
        self.assertIn(["date_selection_0", "2026-12-01 ~ 2026-12-05"], step2_form)

        self.cli("begin", "--change", change, "--plan", self.dir / "plan-2.json", "--snapshot", self.snap(snapshot, at(20)), now=30)
        [call1] = self.cli("calls", "--change", change, "--snapshot", self.snap(snapshot, at(40)), now=50)["calls"]
        self.assertIn(["date_selection_0", "2026-12-01\n2026-12-03 ~ 2026-12-05"], call1["payload"]["want"], "뺀 날을 건너 구간을 친다")
        self.cli("record-result", "--change", change, "--result", self.write("r1.json", self.saved_answer(call1, plan.saves[0])), now=60)
        after1 = applied(snapshot, plan, saves={1})
        early = self.cli("calls", "--change", change, "--snapshot", self.snap(after1, at(55)), now=70, code=2)
        self.assertIn("앞에 읽은 것입니다", early["error"], "A2 — 앞 저장의 결과보다 먼저 읽은 값으로는 다음 저장을 내지 않는다")
        [call2] = self.cli("calls", "--change", change, "--snapshot", self.snap(after1, at(65)), now=75)["calls"]
        unknown = {"ok": False, "op": "applySeason", "no": call2["no"], "ask": ask_sum(call2["payload"]), "saved": "unknown", "pressed": True,
                   "error": "시간(40초) 안에 끝나지 않아 멈췄습니다 — 그 뒤로는 아무것도 누르지 않습니다 · 저장 단추는 눌렸습니다"}
        recorded = self.cli("record-result", "--change", change, "--result", self.write("r2.json", unknown), now=80)
        self.assertEqual((recorded["saved"], recorded["status"]), (False, "stopped"))
        self.assertIn(f"{change}번 변경은 멈춰 있습니다",
                      self.cli("calls", "--change", change, "--snapshot", self.snap(after1, at(85)), now=86, code=2)["error"],
                      "「모름」 뒤에는 다시 누르지 않는다 — 다시 읽어 check 가 가릴 때까지")
        after2 = applied(snapshot, plan)
        checked = self.cli("check", "--change", change, "--snapshot", self.snap(after2, at(90)), now=95)
        self.assertEqual((checked["status"], checked["steps"][1]["settled"]), ("applied", "saved"), checked)
        verified = self.cli("verify", "--change", change, "--snapshot", self.snap(after2, at(100)), now=110, code=1)
        self.assertFalse(verified["mismatches"], verified)
        self.assertEqual(verified["counts"][1]["told"], None, "「모름」이던 저장은 ERP 의 띠가 없다")
        self.assertFalse(verified["same"], "ERP 가 칸 수를 말하지 못한 저장이 있으면 「확인했습니다」라고 하지 않는다")
        page = Path(self.cli("render", "result", "--change", change, now=120)["page"]).read_text(encoding="utf-8")
        self.assertIn("ERP 가 말한 칸 수", page)
        self.assertNotIn("다시 읽어 확인했습니다.", page)
        follow = self.cli("plan", "--snapshot", self.snap(after2, at(130)), "--request", self.dir / "plan-2.json", "--record",
                          "--out", self.dir / "plan-3.json", now=140)
        self.assertGreater(follow["counts"]["will_change"], 0, "A1 — 채운 뒤 다르게 채워진 칸을 날짜별 변경으로 맞추는 미리보기")

    def test_a_cell_changed_since_the_preview_stops_the_change_before_its_save(self):
        window = season_scene.window()
        folder = self.window_answers(window, "작업/시즌")
        self.cli("season", "--answers", folder, "--out", self.dir / "season.json")
        snapshot = self.before()
        request = self.write("request.json", {"kind": "season_fill", "hotel": HOTEL, "offer": season_scene.OFFER,
                                              "season": {"id": window.season_id, "name": window.season_name}, "currency": "USD",
                                              "saves": [{"pairs": [{"room": "디럭스", "rate_plan": "조식 포함"}], "price": "190",
                                                         "occupancy_keys": "A2,A3", "occupancy_adjust": "A3:+50", "los_prices": "3:170"}]})
        planned = self.cli("plan", "--snapshot", self.snap(snapshot, at(-60)), "--request", request, "--season", self.dir / "season.json",
                           "--resolutions", self.write("c.json", [{"save": 1, "rule": "NEW_ROW", "choice": "include", "said": "응"}]),
                           "--record", "--out", self.dir / "plan-1.json")
        change = planned["change_id"]
        self.cli("begin", "--change", change, "--plan", self.dir / "plan-1.json", "--snapshot", self.snap(snapshot, at(10)), now=20)
        key = CellKey("디럭스", "조식 포함", "2026-12-05", "A2", 1)
        moved = replace(snapshot, cells={**snapshot.cells, key: CellValue(D("199"), None, None, "open")})
        stopped = self.cli("calls", "--change", change, "--snapshot", self.snap(moved, at(30)), now=40)
        self.assertEqual((stopped["calls"], stopped["status"], [item["key"]["date"] for item in stopped["differences"]]),
                         ([], "stopped", ["2026-12-05"]), "A2 — 그 저장의 칸이 미리보기 뒤에 바뀌었으면 아무것도 내지 않고 멈춘다")
        listed = self.cli("list", "--all", now=50)
        self.assertIn("적용하다 멈춤", next(item["line"] for item in listed["changes"] if item["id"] == change))
        checked = self.cli("check", "--change", change, "--snapshot", self.snap(moved, at(60)), now=70)
        self.assertFalse(checked["can_continue"])
        page = Path(self.cli("render", "result", "--change", change, now=80)["page"]).read_text(encoding="utf-8")
        self.assertTrue(any("미리보기 때 읽은 값과 다릅니다" in why for why in checked["why"]),
                        "같은 값으로 덮을 칸이 바뀐 것도 check 가 본다 — 저장 하나는 그 쌍의 칸을 모두 다시 쓴다")
        for words in ("적용하다 멈춤", "ERP 가 말한 칸 수", "1번째 저장에서 멈췄습니다", "칸 1개가 미리보기 때 읽은 값과 다릅니다"):
            self.assertIn(words, page, "멈춘 시즌 변경의 페이지는 마지막 check 대로 말하고 시즌 줄을 단다")


if __name__ == "__main__":
    unittest.main()
