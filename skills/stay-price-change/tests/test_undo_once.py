"""검토 3 — 되돌리기와 저장 상태로 되돌리기는 다시 되돌리지 않는다. 그래서 장부의 목록 · 되돌리기 · 「되돌릴 것이 없습니다」가 ERP 에
살아 있는 값과 늘 같다.

검토가 돌린 두 길: (A) 바꾸기 1 적용 → 그것을 되돌린 2 적용 → 2 를 되돌리자고 함. (B) 지금 상태 저장 1 → 바꾸기 2 적용 → 1 번
상태로 되돌리기 3 적용 → 3 을 되돌리자고 함. 예전에는 둘째 되돌리기가 적용되어 ERP 는 바꾼 값을 갖는데 목록은 바꾸기를 「모두 되돌림」,
되돌리기는 「되돌릴 것이 없습니다」라고 했다. 이제 그 계산부터 거절하고(아무것도 적지 않는다), 되돌린 값으로 다시 바꾸는 길(같은
요청의 새 변경)을 말한다.

    python3 -m unittest discover -s tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
from change_core.answers import ask_sum  # noqa: E402
from change_core.ledger import DB_NAME, Ledger, LedgerError  # noqa: E402
from price_model import decode_step, encode_request, encode_snapshot  # noqa: E402

RAISE = [{"rule": "ABOVE_LIST", "choice": "raise_list", "said": "정가도 같이 올려"}]


class UndoOnceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = scene.env(self.dir / "기록")
        self.files = 0
        self.minute = 0

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data) -> Path:
        self.files += 1
        path = self.dir / f"file-{self.files}.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def read(self, snapshot) -> Path:
        """그 값을 방금 다시 읽었다 — 읽을 때마다 1분 뒤(begin · check 는 장부가 적은 것 뒤에 읽은 값만 받는다)."""
        self.minute += 1
        return self.write(encode_snapshot(replace(snapshot, read_at=scene.read_again(self.minute))))

    def cli(self, *args, code=0):
        done = subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def apply(self, change: int, plan: Path, now):
        """begin(다시 읽은 값) → calls → 저장마다 「저장했다」 → 그 저장이 들어간 ERP 의 값."""
        self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(now))
        for call in self.cli("calls", "--change", change)["calls"]:
            answer = {"ok": True, "op": call["op"], "no": call["no"], "ask": ask_sum(call["payload"]), "saved": True, "pressed": True}
            self.cli("record-result", "--change", change, "--result", self.write(answer))
        return scene.applied(now, map(decode_step, json.loads(plan.read_text(encoding="utf-8"))["steps"]))

    def change(self, now):
        plan = self.dir / f"plan-{self.files}.json"
        change = self.cli("plan", "--snapshot", self.read(now), "--request", self.write(encode_request(scene.request())), "--record",
                          "--resolutions", self.write(RAISE), "--out", plan)["change_id"]
        return change, self.apply(change, plan, now)

    def listed(self) -> dict:
        return {entry["id"]: entry for entry in self.cli("list", "--all")["changes"]}

    def refused_again(self, number: int, what: str, now) -> None:
        """그 번호를 되돌리자고 하면 계산부터 거절하고 장부에 아무것도 적지 않는다 — 장부를 바로 불러도 같다."""
        out = self.dir / f"rollback-again-{number}.json"
        before = set(self.listed())
        refused = self.cli("rollback", "--change", number, "--snapshot", self.read(now), "--record", "--out", out, code=2)["error"]
        self.assertIn(f"{number}번은 {what}입니다 — 되돌리기는 다시 되돌리지 않습니다", refused)
        self.assertIn("같은 요청으로 새로 바꿉니다", refused, "되돌린 값으로 다시 바꾸는 길을 말한다")
        self.assertFalse(out.exists())
        self.assertEqual(set(self.listed()), before, "장부에 아무것도 적지 않았다")
        with self.assertRaisesRegex(LedgerError, "다시 되돌리지 않습니다"):
            Ledger(self.dir / "기록" / DB_NAME).record_preview(hotel=scene.HOTEL, hotel_id=scene.HOTEL_ID, offer=scene.OFFER,
                                                              currency="USD", sentence="되돌려", read_at=scene.NOW_TEXT, rows=[],
                                                              reverses=number, empty=True)

    def test_a_a_rollback_is_not_rolled_back_and_the_list_says_what_the_erp_holds(self):
        first = scene.snapshot()
        change, changed = self.change(first)
        back = self.dir / "rollback-1.json"
        rollback = self.cli("rollback", "--change", change, "--snapshot", self.read(changed), "--record", "--out", back)["change_id"]
        undone = self.apply(rollback, back, changed)
        self.assertEqual(undone.cells, first.cells, "ERP 는 바꾸기 전 값을 갖는다")

        self.refused_again(rollback, f"{change}번 되돌리기", undone)
        rows = self.listed()
        self.assertEqual((rows[change]["status"], rows[change]["undone_by"], rows[rollback]["status"]), ("rolled_back", [rollback], "applied"))
        self.assertIn(f"모두 되돌림 {rows[change]['written']}/{rows[change]['written']}칸 (장부 {rollback}번)", rows[change]["scope"])
        nothing = self.cli("rollback", "--change", change, "--snapshot", self.read(undone), code=2)["error"]
        self.assertIn("아직 되돌리지 않은 것이 없습니다", nothing, "ERP 에 바꾼 값이 없으니 참이다")

    def test_b_a_restore_is_not_rolled_back_and_the_change_it_covered_stays_rolled_back(self):
        first = scene.snapshot()
        saved = self.cli("save-snapshot", "--snapshot", self.read(first), "--sentence", "아침 상태 저장해 둬")["change_id"]
        change, changed = self.change(first)
        back = self.dir / "restore-1.json"
        restore = self.cli("restore", "--saved", saved, "--snapshot", self.read(changed), "--record", "--out", back)["change_id"]
        restored = self.apply(restore, back, changed)
        self.assertEqual(restored.cells, first.cells, "ERP 는 저장해 둔 값을 갖는다")

        self.refused_again(restore, f"{saved}번 저장 상태로 되돌리기", restored)
        rows = self.listed()
        self.assertEqual((rows[change]["status"], rows[change]["undone_by"], rows[restore]["status"]), ("rolled_back", [restore], "applied"))
        nothing = self.cli("rollback", "--change", change, "--snapshot", self.read(restored), code=2)["error"]
        self.assertIn("아직 되돌리지 않은 것이 없습니다", nothing)


if __name__ == "__main__":
    unittest.main()
