"""Z2 — 장부는 담당자의 문장 없이도 그 번호가 무엇을 덮는지 말한다.

시운전에서 새 세션이 읽어 준 문장은 "그 날짜들 … 12% 올려줘" — 날짜가 없었다. `list` 와 `check` 는 번호마다 장부가 가진 칸에서
범위 한 줄(`scope`)을 단다: 객실 · 요금제, 날짜 구간, 한 일(알면 "판매가 +12%"), 멈춘 변경이면 어디까지 갔는지.

    python3 -m unittest discover -s tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
import trial_scene  # noqa: E402
from change_core.ledger import DB_NAME, Ledger  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from price_change import listed  # noqa: E402
from price_model import CellKey, Target, TargetTable, encode_request, encode_snapshot  # noqa: E402
from price_pages import cells_scope  # noqa: E402
from price_plan import plan_change, plan_steps, plan_targets, preview_rows, resolve, snapshot_rows, step_plans  # noqa: E402

REAL = scene.NOW
TRIAL = "스탠다드(조식 포함), 스탠다드 바다 전망(조식 포함) · 12/7 월 ~ 12/8 화 · 12/10 목 · 12/14 월 (4일, 2026년)"
HEAD = f"객실 가격 · {trial_scene.OFFER} · {TRIAL}"   # 범위 한 줄의 머리 — 종류(P1) · 오퍼(P3)부터


class ListScopeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = self.dir / DB_NAME
        self.snapshot = trial_scene.snapshot(read_at=REAL.isoformat(timespec="seconds"))
        plan = resolve(plan_change(self.snapshot, trial_scene.request()), [Resolution("ABOVE_LIST", "raise_list")])
        self.steps = plan_steps(plan)
        self.change = self.ledger(0).record_preview(
            hotel=trial_scene.HOTEL, hotel_id=trial_scene.HOTEL_ID, offer=trial_scene.OFFER, currency="USD",
            sentence=trial_scene.SENTENCE, read_at=self.snapshot.read_at, rows=preview_rows(plan),
            request=encode_request(plan.request), reading=encode_snapshot(self.snapshot))

    def tearDown(self):
        self.tmp.cleanup()

    def ledger(self, minutes: float) -> Ledger:
        return Ledger(self.path, now=lambda: REAL + timedelta(minutes=minutes))

    def scope(self, minutes: float, number: int) -> str:
        return next(item for item in listed(self.ledger(minutes)) if item["id"] == number)["scope"]

    def test_a_stopped_change_says_rooms_dates_what_and_how_far_without_the_sentence(self):
        self.assertEqual(self.scope(0, self.change), f"{HEAD} · 판매가 +12%", "미리보기만 — 어디까지는 상태가 말한다")
        self.ledger(0).begin(self.change, step_plans(self.steps), read_at=self.snapshot.read_at)
        self.ledger(1).record_step(self.change, 1, saved=True)
        self.assertEqual(self.scope(2, self.change), f"{HEAD} · 판매가 +12% · 저장 2번 중 1번 함 · 적용 중")
        self.assertEqual(self.scope(20, self.change), f"{HEAD} · 판매가 +12% · 저장 2번 중 1번 하고 멈춤",
                         "세션이 끊겨 멈춘 변경 — 문장에 날짜가 없어도 범위와 어디까지 갔는지")
        self.assertNotIn("request", listed(self.ledger(20))[0], "요청 원문은 싣지 않는다")

    def test_a_saved_state_and_a_long_room_list_read_as_one_line(self):
        saved = self.ledger(0).record_snapshot(hotel=trial_scene.HOTEL, hotel_id=trial_scene.HOTEL_ID, offer=trial_scene.OFFER,
                                               currency="USD", sentence="응 저장해", read_at=self.snapshot.read_at,
                                               rows=snapshot_rows(self.snapshot), reading=encode_snapshot(self.snapshot))
        self.assertEqual(self.scope(0, saved), f"{HEAD} · 지금 상태 저장")
        many = [CellKey(f"객실 {n}", "조식 포함", "2026-12-07", "A2", 1) for n in range(1, 6)]
        self.assertEqual(cells_scope(many), "객실 1(조식 포함), 객실 2(조식 포함), 객실 3(조식 포함) 외 2객실 · 12/7 월 (1일, 2026년)")

    def test_two_offers_with_the_same_room_and_rate_plan_read_as_two_lines_each_naming_its_offer(self):
        """P3 — 읽기만 한 시운전: 「장부 1번 · 11/21 13:16 저장 · 디럭스(조식 포함) · 12/7 월 ~ 12/8 화 …」는 그 객실 · 요금제가 있는
        두 오퍼를 가르지 못했다. 되돌리기 전에 담당자가 확인하는 줄이 이것이라 오퍼를 늘 댄다."""
        other = replace(self.snapshot, offer="연말 오퍼")
        numbers = [self.ledger(0).record_snapshot(hotel=trial_scene.HOTEL, hotel_id=trial_scene.HOTEL_ID, offer=snapshot.offer,
                                                  currency="USD", sentence="지금 가격 보여줘", read_at=snapshot.read_at,
                                                  rows=snapshot_rows(snapshot), reading=encode_snapshot(snapshot))
                   for snapshot in (self.snapshot, other)]
        lines = [self.scope(0, number) for number in numbers]
        self.assertEqual(lines, [f"객실 가격 · {trial_scene.OFFER} · {TRIAL} · 지금 상태 저장", f"객실 가격 · 연말 오퍼 · {TRIAL} · 지금 상태 저장"])

    def test_a_target_table_counts_the_cells_it_writes_not_the_ones_kept_on_a_red_line(self):
        """F5 — 요금표 시운전: 8칸을 넣고 4칸을 빨간 줄에 그대로 둔 변경을 「새 요금표 12칸」이라고 읽어 주었다."""
        reading = scene.snapshot(read_at=REAL.isoformat(timespec="seconds"))
        sells = dict(zip(scene.DATES, ("420", "420", "600", "600")))   # 1/1 · 1/2 는 정가 500 — 600 이면 정가를 넘는 빨간 줄
        table = TargetTable(scene.HOTEL, scene.OFFER, tuple(Target(CellKey("스위트", "조식 포함", day, "A2", 1), (("sell", Decimal(sell)),))
                                                           for day, sell in sells.items()), hotel_id=scene.HOTEL_ID, from_sheet=True)
        plan = resolve(plan_targets(reading, table), [Resolution("ABOVE_LIST", "keep")])
        self.assertEqual(sum(change.choice == "keep" for change in plan.changes), 2)
        number = self.ledger(0).record_preview(
            hotel=scene.HOTEL, hotel_id=scene.HOTEL_ID, offer=scene.OFFER, currency="USD", sentence="새 요금표대로",
            read_at=reading.read_at, rows=preview_rows(plan), request=encode_request(plan.request), reading=encode_snapshot(reading))
        self.assertTrue(self.scope(0, number).endswith("· 새 요금표 2칸"), self.scope(0, number))
        self.ledger(0).begin(number, step_plans(plan_steps(plan)), read_at=reading.read_at)
        for step in range(1, len(plan_steps(plan)) + 1):
            self.ledger(1).record_step(number, step, saved=True)
        self.assertTrue(self.scope(2, number).endswith("· 새 요금표 2칸"), "적용한 뒤에도 넣은 칸 수 — 되돌리기 확인이 읽어 준다")

    def test_check_gives_the_same_line(self):
        env = scene.env(str(self.dir))
        self.ledger(0).begin(self.change, step_plans(self.steps), read_at=self.snapshot.read_at)
        self.ledger(1).record_step(self.change, 1, saved=True)
        now = scene.NOW_TEXT
        reading = self.dir / "again.json"   # 첫 저장이 들어간 지금 값을 방금 읽었다
        reading.write_text(json.dumps(encode_snapshot(scene.applied(self.snapshot, self.steps[:1], now)), ensure_ascii=False),
                           encoding="utf-8")
        done = subprocess.run([sys.executable, str(SCRIPT), "check", "--change", str(self.change), "--snapshot", str(reading)],
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertEqual((report["can_continue"], report["scope"]), (True, f"{HEAD} · 판매가 +12% · 저장 2번 중 1번 함 · 적용 중"))


class NarrowedScopeTest(unittest.TestCase):
    """R5 — 칸을 좁힌 변경(인원 조합 · 박수 층)은 범위 한 줄이 그렇게 말한다. 되돌리기 확인은 그 줄을 읽어 주므로 "1박 이상만 −5%"
    가 "판매가 -5%" 로만 들리면 안 된다. rollback · restore 의 짧은 답도 범위를 싣는다(장부 목록의 그 번호 줄과 같다)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = scene.env(str(self.dir))
        self.snapshot = trial_scene.snapshot(read_at=scene.NOW_TEXT)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def write(self, name, data) -> Path:
        path = self.dir / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def applied_change(self, name: str, **narrow) -> tuple[int, Path]:
        request = replace(trial_scene.request(), value=Decimal("-5"), sentence="1박 이상만 5% 내려줘", **narrow)
        short = self.cli("plan", "--snapshot", self.write(f"{name}-snapshot.json", encode_snapshot(self.snapshot)),
                         "--request", self.write(f"{name}-request.json", encode_request(request)), "--record",
                         "--out", self.dir / f"{name}-plan.json")
        self.assertEqual(short["counts"]["red"], 0)
        steps = plan_steps(plan_change(self.snapshot, request))
        ledger = Ledger(self.dir / DB_NAME, now=scene.clock)
        ledger.begin(short["change_id"], step_plans(steps), read_at=self.snapshot.read_at)
        for index in range(1, len(steps) + 1):
            ledger.record_step(short["change_id"], index, saved=True)
        now = scene.NOW_TEXT
        return short["change_id"], self.write(f"{name}-after.json", encode_snapshot(scene.applied(self.snapshot, steps, now)))

    def line(self, number: int) -> str:
        return next(item for item in self.cli("list", "--all")["changes"] if item["id"] == number)["scope"]

    def test_r5_a_narrowed_change_says_which_cells_and_its_rollback_and_restore_answers_carry_the_scope(self):
        nights, after = self.applied_change("nights", nights=(1,))
        self.assertEqual(self.line(nights), f"{HEAD} · 판매가 -5% (1박 이상만)")
        both, _after = self.applied_change("both", nights=(1,), occupancies=("A2",))
        self.assertEqual(self.line(both), f"{HEAD} · 판매가 -5% (성인 2 / 1박 이상만)")

        back = self.cli("rollback", "--change", nights, "--snapshot", after, "--record", "--out", self.dir / "rollback-1.json")
        self.assertEqual(back["scope"], self.line(back["change_id"]), "짧은 답의 범위 = 장부 목록의 그 번호 줄")
        self.assertTrue(back["scope"].endswith(f"· {nights}번 되돌리기"), back["scope"])
        part = self.cli("rollback", "--change", nights, "--snapshot", after, "--occupancy", "A2", "--record", "--replaces",
                        back["change_id"], "--out", self.dir / "rollback-2.json")
        self.assertEqual(part["scope"], self.line(part["change_id"]))
        self.assertTrue(part["scope"].endswith(f"· {nights}번 되돌리기 (성인 2만)"), part["scope"])
        unrecorded = self.cli("rollback", "--change", nights, "--snapshot", after, "--out", self.dir / "rollback-3.json")
        self.assertEqual(unrecorded["scope"], back["scope"], "장부에 적지 않은 계산도 같은 줄")

        saved = self.cli("save-snapshot", "--snapshot", self.write("saved.json", encode_snapshot(self.snapshot)))["change_id"]
        restore = self.cli("restore", "--saved", saved, "--snapshot", after, "--record", "--out", self.dir / "restore-1.json")
        self.assertEqual(restore["scope"], self.line(restore["change_id"]))
        self.assertTrue(restore["scope"].endswith(f"· {saved}번 저장 상태로 되돌리기"), restore["scope"])


if __name__ == "__main__":
    unittest.main()


class TabHotelListTest(unittest.TestCase):
    """H3 — 목록은 탭에 열린 호텔(look 명령이 낸 파일)의 번호만 싣고, 다른 호텔의 번호는 --all 로 청할 때만 그 뒤에 싣는다.
    작업 폴더는 work 가 일마다 새로 만든다(세 도우미가 같은 것을 쓴다)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "기록").mkdir()
        self.env = scene.env(str(self.dir / "기록"))

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, script=SCRIPT, code=0):
        done = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout if code == 0 else done.stderr)

    def preview(self, hotel: str, hotel_id: str) -> int:
        snapshot = replace(trial_scene.snapshot(read_at=scene.NOW_TEXT), hotel=hotel, hotel_id=hotel_id)
        plan = resolve(plan_change(snapshot, replace(trial_scene.request(), hotel=hotel, hotel_id=hotel_id)),
                       [Resolution("ABOVE_LIST", "raise_list")])
        return Ledger(self.dir / "기록" / DB_NAME, now=scene.clock).record_preview(
            hotel=hotel, hotel_id=hotel_id, offer=trial_scene.OFFER, currency="USD", sentence="12% 올려줘",
            read_at=snapshot.read_at, rows=preview_rows(plan), request=encode_request(plan.request), reading=encode_snapshot(snapshot))

    def look(self) -> Path:
        folder = self.dir / "look"
        folder.mkdir()
        (folder / "look-1.json").write_text(json.dumps({
            "op": "look", "ok": True, "login": False, "hotel": trial_scene.HOTEL_REF, "offer": trial_scene.OFFER,
            "offers": [trial_scene.OFFER], "pairs": [], "doneAt": "2026-11-21T01:00:00.000Z"}, ensure_ascii=False), encoding="utf-8")
        self.cli("look", "--answers", folder, "--out", self.dir / "look.json")
        return self.dir / "look.json"

    def test_the_tab_hotel_first_and_other_hotels_only_when_asked(self):
        older = self.preview(trial_scene.HOTEL, trial_scene.HOTEL_ID)
        other = self.preview("다른 데모 호텔", "9")
        newer = self.preview(trial_scene.HOTEL, trial_scene.HOTEL_ID)
        look = self.look()
        tab = self.cli("list", "--look", look)
        self.assertEqual(([entry["id"] for entry in tab["changes"]], tab["others"], tab["hotel"]),
                         ([newer, older], 1, trial_scene.HOTEL_REF))
        every = self.cli("list", "--look", look, "--all")
        self.assertEqual([entry["id"] for entry in every["changes"]], [newer, older, other], "탭의 호텔이 먼저, 저마다 새것부터")
        self.assertIn("--look", self.cli("list", code=2)["error"], "어느 호텔인지 말하지 않으면 싣지 않는다")
        self.assertEqual([entry["id"] for entry in self.cli("list", "--all")["changes"]], [newer, other, older])

    def test_each_helper_makes_a_new_work_folder_every_time(self):
        made = [Path(self.cli("work", script=script)["work"]) for script in (
            SCRIPT, HERE.parent.parent / "stay-addon-price-change" / "scripts" / "addon_change.py",
            HERE.parent.parent / "stay-charge-change" / "scripts" / "charge_change.py", SCRIPT)]
        self.assertEqual(len(set(made)), 4, "같은 초에 불러도 앞선 일의 폴더를 다시 주지 않는다")
        for path in made:
            self.assertTrue(path.is_dir())
            self.assertEqual(path.parent, self.dir / "기록" / "작업")
            self.assertEqual([item.name for item in path.iterdir()], ["look"], "look 답을 둘 폴더까지(P4)")


class LookReuseTest(unittest.TestCase):
    """H4 — 가격 캘린더 도우미의 look 도 앞선 작업 폴더의 look/ 에서 다 받은 같은 조각을 빌린다(다른 두 도우미 · 읽기와 같다)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.records = Path(self.tmp.name) / "기록"
        self.env = scene.env(str(self.records))

    def tearDown(self):
        self.tmp.cleanup()

    def look(self, folder: Path, body_id: str, pieces: bool, pairs=(("디럭스", "조식 포함"), ("스위트", "조식 포함"))) -> subprocess.CompletedProcess:
        from browser_replies import reply
        keep = {"hotel": trial_scene.HOTEL_REF, "offer": trial_scene.OFFER, "offers": [trial_scene.OFFER],
                "pairs": [{"room": room, "rate_plan": plan} for room, plan in pairs]}
        answers = reply("look", {}, keep, pieces=3, body_id=body_id, login=False, hotel=trial_scene.HOTEL_REF,
                        offer=trial_scene.OFFER, count={"offers": 1, "pairs": len(pairs)})
        folder.mkdir(parents=True)
        for index, answer in enumerate(answers if pieces else answers[:1], 1):
            (folder / f"look-{index}.json").write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPT), "look", "--answers", str(folder), "--out", str(folder.parent / "look.json")],
                              capture_output=True, text=True, env=self.env)

    def test_a_later_look_of_the_same_screen_borrows_the_pieces_an_earlier_look_folder_took(self):
        work = self.records / "작업"
        first = self.look(work / "2026-11-21 100000" / "look", "blook", pieces=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.look(work / "2026-11-21 103000" / "look", "blook2", pieces=False)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(len(json.loads((work / "2026-11-21 103000" / "look.json").read_text(encoding="utf-8"))["pairs"]), 2)
        third = self.look(work / "2026-11-21 110000" / "look", "blook3", pieces=False, pairs=(("디럭스", "룸온리"),))
        self.assertEqual(third.returncode, 2, "화면이 바뀌면 빌릴 것이 없어 받으라고 한다")
        self.assertEqual([item["id"] for item in json.loads(third.stderr)["refetch"]], ["blook3"])


class NewestLookTest(unittest.TestCase):
    """N4 — 담당자가 말한 오퍼가 탭이 연 오퍼가 아니면 도우미는 `look()` 뒤에 `look({offer})` 를 부르고 그 답을 다음 번호
    (`look-2.json`)로 저장한다(기록 폴더의 파일은 고치지 않는다). 명령은 가장 늦게 끝난 답 — 그 오퍼 — 을 쓴다."""

    def test_two_look_answers_bind_the_one_the_page_finished_last(self):
        from browser_replies import done_at, reply
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        records = Path(tmp.name) / "기록"
        folder = records / "작업" / "2026-11-21 100000" / "look"
        answers = []
        for offer, pairs, minute in ((trial_scene.OFFER, [("디럭스", "조식 포함")], 1), ("다른 오퍼", [("스위트", "룸온리")], 2)):
            asked = {} if minute == 1 else {"offer": offer}
            keep = {"hotel": trial_scene.HOTEL_REF, "offer": offer, "offers": [trial_scene.OFFER, "다른 오퍼"],
                    "pairs": [{"room": room, "rate_plan": plan} for room, plan in pairs]}
            answers += reply("look", asked, keep, pieces=2, body_id=f"blook{minute}", login=False, hotel=trial_scene.HOTEL_REF,
                             offer=offer, count={"offers": 2, "pairs": 1}, doneAt=done_at(scene.NOW + timedelta(minutes=minute)))
        folder.mkdir(parents=True)
        for index, answer in enumerate(answers, 1):
            (folder / f"look-{index}.json").write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
        done = subprocess.run([sys.executable, str(SCRIPT), "look", "--answers", str(folder), "--out", str(folder.parent / "look.json")],
                              capture_output=True, text=True, env=scene.env(str(records)))
        self.assertEqual(done.returncode, 0, done.stderr)
        look = json.loads(done.stdout)
        self.assertEqual((look["offer"], look["pairs"]), ("다른 오퍼", [{"room": "스위트", "rate_plan": "룸온리"}]))
