"""Z2 — 장부는 담당자의 문장 없이도 그 번호가 무엇을 덮는지 말한다.

시운전에서 새 세션이 읽어 준 문장은 "그 날짜들 … 12% 올려줘" — 날짜가 없었다. `list` 와 `check` 는 번호마다 장부가 가진 칸에서
범위 한 줄(`scope`)을 단다: 객실 · 요금제, 날짜 구간, 한 일(알면 "판매가 +12%"), 멈춘 변경이면 어디까지 갔는지.

    python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
import trial_scene  # noqa: E402
from change_core.ledger import DB_NAME, Ledger  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from price_change import listed  # noqa: E402
from price_model import CellKey, encode_request, encode_snapshot  # noqa: E402
from price_pages import cells_scope  # noqa: E402
from price_plan import plan_change, plan_steps, preview_rows, resolve, snapshot_rows, step_plans  # noqa: E402

REAL = datetime.now().astimezone()
TRIAL = "스탠다드(조식 포함), 스탠다드 바다 전망(조식 포함) · 12/7 월 ~ 12/8 화 · 12/10 목 · 12/14 월 (4일, 2026년)"


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
        self.assertEqual(self.scope(0, self.change), f"{TRIAL} · 판매가 +12%", "미리보기만 — 어디까지는 상태가 말한다")
        self.ledger(0).begin(self.change, step_plans(self.steps), read_at=self.snapshot.read_at)
        self.ledger(1).record_step(self.change, 1, saved=True)
        self.assertEqual(self.scope(2, self.change), f"{TRIAL} · 판매가 +12% · 저장 2번 중 1번 함 · 적용 중")
        self.assertEqual(self.scope(20, self.change), f"{TRIAL} · 판매가 +12% · 저장 2번 중 1번 하고 멈춤",
                         "세션이 끊겨 멈춘 변경 — 문장에 날짜가 없어도 범위와 어디까지 갔는지")
        self.assertNotIn("request", listed(self.ledger(20))[0], "요청 원문은 싣지 않는다")

    def test_a_saved_state_and_a_long_room_list_read_as_one_line(self):
        saved = self.ledger(0).record_snapshot(hotel=trial_scene.HOTEL, hotel_id=trial_scene.HOTEL_ID, offer=trial_scene.OFFER,
                                               currency="USD", sentence="응 저장해", read_at=self.snapshot.read_at,
                                               rows=snapshot_rows(self.snapshot), reading=encode_snapshot(self.snapshot))
        self.assertEqual(self.scope(0, saved), f"{TRIAL} · 지금 상태 저장")
        many = [CellKey(f"객실 {n}", "조식 포함", "2026-12-07", "A2", 1) for n in range(1, 6)]
        self.assertEqual(cells_scope(many), "객실 1(조식 포함), 객실 2(조식 포함), 객실 3(조식 포함) 외 2객실 · 12/7 월 (1일, 2026년)")

    def test_check_gives_the_same_line(self):
        env = {**os.environ, "STAY_PRICE_LEDGER_DIR": str(self.dir)}
        self.ledger(0).begin(self.change, step_plans(self.steps), read_at=self.snapshot.read_at)
        self.ledger(1).record_step(self.change, 1, saved=True)
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        reading = self.dir / "again.json"   # 첫 저장이 들어간 지금 값을 방금 읽었다
        reading.write_text(json.dumps(encode_snapshot(scene.applied(self.snapshot, self.steps[:1], now)), ensure_ascii=False),
                           encoding="utf-8")
        done = subprocess.run([sys.executable, str(SCRIPT), "check", "--change", str(self.change), "--snapshot", str(reading)],
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertEqual((report["can_continue"], report["scope"]), (True, f"{TRIAL} · 판매가 +12% · 저장 2번 중 1번 함 · 적용 중"))


if __name__ == "__main__":
    unittest.main()
