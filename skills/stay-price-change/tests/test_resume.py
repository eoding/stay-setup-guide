"""T1 · T2 — 끊긴 변경은 다시 읽지 않고 이어 갈 수 없다.

begin 은 적용 직전에 읽은 값을 받아 미리보기 때 값과 견주고, 15분 안의 읽은 값으로만 시작한다. 적용 중인 변경이 15분 동안 아무
일이 없으면 목록 · calls · check · 결과 페이지 어디서나 멈춘 변경이다. 멈춘 뒤에 적힌 저장은 적기만 하고 변경을 살리지 않는다.
이어서 해도 된다고 본 check 의 읽은 값이 15분 안이면 calls 가 남은 저장을 낸다(같은 범위를 두 번 읽지 않는다).

    python3 -m unittest discover -s tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
from change_core.ledger import DB_NAME, IDLE, Ledger, LedgerError  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from change_core.answers import ask_sum  # noqa: E402
from price_model import encode_request, encode_snapshot, snapshot_reading  # noqa: E402
from price_pages import render_result  # noqa: E402
from price_plan import plan_change, plan_steps, preview_rows, resolve, step_plans  # noqa: E402
from test_pages import visible  # noqa: E402

REAL = scene.NOW


def at(minutes: float) -> str:
    return (REAL + timedelta(minutes=minutes)).isoformat(timespec="seconds")


class ResumeLedgerTest(unittest.TestCase):
    """장부를 바로 부른다 — 시계를 옮긴 장부(`Ledger(path, now=…)`)로 같은 장부를 나중에 본다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / DB_NAME
        self.before = scene.snapshot()
        plan = resolve(plan_change(self.before, scene.request()), [Resolution("ABOVE_LIST", "raise_list")])
        self.steps = plan_steps(plan)
        self.change = self.ledger(-20).record_preview(   # 미리보기는 20분 전에 적었다 — 이 시험의 읽은 값은 그 뒤에 읽은 것
            hotel=scene.HOTEL, hotel_id=scene.HOTEL_ID, offer=scene.OFFER, currency="USD", sentence=scene.SENTENCE,
            read_at=self.before.read_at, rows=preview_rows(plan), request=encode_request(plan.request),
            reading=encode_snapshot(self.before))
        self.then = snapshot_reading(self.before)

    def tearDown(self):
        self.tmp.cleanup()

    def ledger(self, minutes: float) -> Ledger:
        """`minutes` 분 뒤의 시계로 같은 장부를 본다."""
        return Ledger(self.path, now=lambda: REAL + timedelta(minutes=minutes))

    def reading(self, saved: int):
        return snapshot_reading(scene.applied(self.before, self.steps[:saved]))

    def test_begin_takes_only_a_reading_made_inside_the_window(self):
        with self.assertRaises(LedgerError) as caught:
            self.ledger(0).begin(self.change, step_plans(self.steps), read_at=at(-16))
        self.assertIn("16분 전", str(caught.exception))
        self.assertEqual(self.ledger(0).change(self.change).status, "previewed", "아무것도 시작하지 않았다")
        self.ledger(0).begin(self.change, step_plans(self.steps), read_at=at(-14))
        self.assertEqual(self.ledger(0).change(self.change).status, "applying")

    def test_an_applying_change_with_no_activity_for_15_minutes_is_stopped_everywhere(self):
        self.ledger(0).begin(self.change, step_plans(self.steps), read_at=at(0))
        self.ledger(1).record_step(self.change, 1, saved=True)
        for minutes, status in ((15.9, "applying"), (16.1, "stopped")):   # 마지막 활동은 1분에 적힌 저장
            later = self.ledger(minutes)
            record = later.change(self.change)
            self.assertEqual((record.status, record.cause), (status, None if status == "applying" else "cut_off"), minutes)
            self.assertEqual(later.list_changes()[0]["status"], status, f"목록 · {minutes}분")
        page = visible(render_result(self.ledger(16.1).change(self.change)))
        self.assertIn("2번째 저장 앞에서 끊겼습니다. 저장이 실패한 것은 아니고, 1번째 저장까지 됐습니다", page)
        self.assertIn("이어서 — 남은 7번을 마저 적용합니다", page)

    def test_a_save_recorded_after_the_change_went_quiet_is_kept_but_does_not_revive_it(self):
        self.ledger(0).begin(self.change, step_plans(self.steps), read_at=at(0))
        self.assertEqual(self.ledger(10).record_step(self.change, 1, saved=True), "applying", "15분 안의 저장은 활동이다")
        self.assertEqual(self.ledger(24).change(self.change).status, "applying", "10분의 저장에서 14분 지났다")
        self.assertEqual(self.ledger(26).record_step(self.change, 2, saved=True), "stopped", "16분 동안 조용하던 변경")
        record = self.ledger(26).change(self.change)
        self.assertEqual(([step.status for step in record.steps[:3]], record.status), (["saved", "saved", "pending"], "stopped"),
                         "저장은 적었고 변경은 멈춘 채로 둔다")

    def test_check_says_where_the_change_stands_and_a_fresh_check_lets_it_go_on_for_15_minutes(self):
        self.ledger(0).begin(self.change, step_plans(self.steps), read_at=at(0))
        self.ledger(1).record_step(self.change, 1, saved=True)
        report = self.ledger(30).check(self.change, self.reading(1), self.then, read_at=at(30))
        self.assertEqual((report.cause, report.last_saved.index, report.next.index, report.note), ("cut_off", 1, 2, None))
        self.assertEqual((report.can_continue, report.status), (True, "applying"))
        self.assertEqual(self.ledger(44).change(self.change).status, "applying", "check 의 읽은 값에서 14분 — 다시 읽지 않고 이어 간다")
        self.assertEqual(self.ledger(46).change(self.change).status, "stopped", "그 읽은 값에서 16분 — 다시 읽어야 한다")

        self.ledger(46).check(self.change, self.reading(1), self.then, read_at=at(46))
        self.ledger(47).record_step(self.change, 2, saved=False, note="허용 목록에 없는 클릭을 막았습니다")
        failed = self.ledger(48).check(self.change, self.reading(1), self.then, read_at=at(48))
        self.assertEqual((failed.cause, failed.note, failed.last_saved.index, failed.next.index),
                         ("failed", "허용 목록에 없는 클릭을 막았습니다", 1, 2))
        self.ledger(49).record_step(self.change, 2, saved=False, note="모름", unknown=True)
        unknown = self.ledger(50).check(self.change, self.reading(2), self.then, read_at=at(50))
        self.assertEqual((unknown.cause, unknown.steps[1].settled, unknown.last_saved.index, unknown.next.index),
                         ("unknown", "saved", 2, 3))

    def test_a_check_on_an_old_reading_or_one_that_cannot_go_on_leaves_the_change_stopped(self):
        self.ledger(0).begin(self.change, step_plans(self.steps), read_at=at(0))
        self.ledger(1).record_step(self.change, 1, saved=True)
        old = self.ledger(40).check(self.change, self.reading(1), self.then, read_at=at(20))
        self.assertFalse(old.can_continue)
        self.assertTrue(any("20분 전" in why and "다시 읽고" in why for why in old.why), old.why)
        self.assertEqual(self.ledger(40).change(self.change).status, "stopped")

        # 「모름」을 저장됨으로 가렸어도 남은 칸이 그 사이 바뀌었으면 이어 갈 수 없다 — 변경은 멈춘 채로 남는다
        self.ledger(41).check(self.change, self.reading(1), self.then, read_at=at(41))
        self.ledger(42).record_step(self.change, 2, saved=False, note="모름", unknown=True)
        moved = scene.applied(self.before, self.steps[:2])
        third = next(key for key in moved.cells if (key.room, key.rate_plan) == (self.steps[2].room, self.steps[2].rate_plan)
                     and key.date == self.steps[2].dates[0])
        moved = scene.with_cells(moved, {third: replace(moved.cells[third], sell=moved.cells[third].sell + 1)})
        report = self.ledger(43).check(self.change, snapshot_reading(moved), self.then, read_at=at(43))
        self.assertEqual((report.steps[1].settled, report.can_continue, report.status), ("saved", False, "stopped"))
        self.assertEqual(self.ledger(43).change(self.change).status, "stopped", "calls 가 남은 저장을 내지 않는다")


class ResumeCommandTest(unittest.TestCase):
    """명령으로 — begin 의 읽은 값, 그리고 시간이 지나 끊긴 변경(15분 끝자락에서 시작해 장부의 시계를 몇 초 옮긴다).
    명령의 장부 시계는 `self.clock` 에 서 있다(STAY_PRICE_TEST_NOW) — 이 컴퓨터의 시계 · 부하와 상관없다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.clock = scene.NOW
        self.write("snapshot.json", encode_snapshot(scene.snapshot()))
        self.write("request.json", encode_request(scene.request()))
        self.write("choice.json", [{"rule": "ABOVE_LIST", "choice": "raise_list", "said": "정가도 같이 올려"}])
        self.change = self.cli("plan", "--snapshot", self.dir / "snapshot.json", "--request", self.dir / "request.json",
                               "--resolutions", self.dir / "choice.json", "--record", "--out", self.dir / "plan.json")["change_id"]
        self.clock = scene.NOW + timedelta(minutes=25)   # 미리보기를 적고 25분 뒤 — 이 시험의 읽은 값은 그 뒤에 읽은 것

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.dir / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    @property
    def env(self) -> dict:
        return dict(scene.env(self.dir / "기록"), STAY_PRICE_TEST_NOW=self.clock.isoformat())

    def cli(self, *args, code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def reading(self, name, snapshot, read_at=None):
        """`read_at` 을 주지 않으면 방금(장부의 시계) 읽은 값."""
        return self.write(name, dict(encode_snapshot(snapshot), read_at=read_at or self.clock.isoformat(timespec="seconds")))

    def test_begin_needs_the_reading_made_just_before_and_starts_nothing_if_a_cell_differs(self):
        done = subprocess.run([sys.executable, str(SCRIPT), "begin", "--change", str(self.change), "--plan", str(self.dir / "plan.json")],
                              capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, 2)
        self.assertIn("--snapshot", done.stderr, "읽은 값 없이는 시작하지 않는다")
        moved = scene.snapshot()
        key = next(iter(sorted(moved.cells)))
        moved = scene.with_cells(moved, {key: replace(moved.cells[key], sell=moved.cells[key].sell + 1)})
        refused = self.cli("begin", "--change", self.change, "--plan", self.dir / "plan.json", "--snapshot", self.reading("moved.json", moved),
                           code=1)
        self.assertEqual((refused["same"], refused["status"], [item["key"]["date"] for item in refused["differences"]]),
                         (False, "previewed", [key.date]), "stale 과 같은 모양으로 다른 칸을 댄다")
        self.assertIn("begin", self.cli("calls", "--change", self.change, code=2)["error"], "아무것도 시작하지 않았다")
        old = self.reading("old.json", scene.snapshot(), (self.clock - timedelta(minutes=20)).isoformat(timespec="seconds"))
        self.assertIn("20분 전", self.cli("begin", "--change", self.change, "--plan", self.dir / "plan.json", "--snapshot", old, code=2)["error"])
        started = self.cli("begin", "--change", self.change, "--plan", self.dir / "plan.json", "--snapshot", self.reading("now.json", scene.snapshot()))
        self.assertEqual(started["status"], "applying")

    def test_a_run_cut_off_between_saves_is_stopped_until_a_fresh_check(self):
        edge = (self.clock - IDLE + timedelta(seconds=3)).isoformat(timespec="seconds")
        self.cli("begin", "--change", self.change, "--plan", self.dir / "plan.json", "--snapshot", self.reading("edge.json", scene.snapshot(), edge))
        self.assertEqual(len(self.cli("calls", "--change", self.change)["calls"]), 8, "15분 안 — 남은 저장을 낸다")
        self.clock += timedelta(seconds=4.5)              # 세션이 끊겼다 — 받아들인 읽은 값에서 15분이 지났다
        self.assertEqual(self.cli("list", "--all")["changes"][0]["status"], "stopped")
        self.assertIn("멈춰 있습니다", self.cli("calls", "--change", self.change, code=2)["error"])
        page = Path(self.cli("render", "result", "--change", self.change, "--out", self.dir / "result.html")["page"]).read_text(encoding="utf-8")
        self.assertIn("첫 저장 전에 끊겼습니다", page)
        report = self.cli("check", "--change", self.change, "--snapshot", self.reading("again.json", scene.snapshot()))
        self.assertEqual((report["cause"], report["last_saved"], report["next"]["no"], report["can_continue"], report["status"]),
                         ("cut_off", None, 1, True, "applying"))
        call = self.cli("calls", "--change", self.change)["calls"][0]
        result = self.write("r1.json", {"ok": True, "op": call["op"], "no": call["no"], "ask": ask_sum(call["payload"]), "saved": True, "pressed": True})
        self.assertEqual(self.cli("record-result", "--change", self.change, "--result", result)["status"], "applying")


if __name__ == "__main__":
    unittest.main()
