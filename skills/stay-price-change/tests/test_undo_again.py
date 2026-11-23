"""검토 3 — 되돌리기와 저장 상태로 되돌리기도 바꾸기처럼 되돌린다. 몇 번을 되돌려도 장부의 목록 · 되돌리기 · 「되돌릴 것이
없습니다」가 ERP 에 살아 있는 값과 같다.

검토가 돌린 두 길을 명령으로 그대로 한다: (A) 바꾸기 1 적용 → 그것을 되돌린 2 적용 → 2 를 되돌린 3 적용(→ 3 을 되돌린 4).
(B) 지금 상태 저장 1 → 바꾸기 2 적용 → 1 번 상태로 되돌리기 3 적용 → 3 을 되돌린 4 적용. 예전에는 둘째 되돌리기 뒤에 ERP 는 바꾼
값을 갖는데 목록은 바꾸기를 「모두 되돌림」, 그 바꾸기의 되돌리기는 「되돌릴 것이 없습니다」라고 했다.

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
from price_model import decode_step, encode_request, encode_snapshot  # noqa: E402

RAISE = [{"rule": "ABOVE_LIST", "choice": "raise_list", "said": "정가도 같이 올려"}]


class UndoAgainTest(unittest.TestCase):
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

    def undo(self, number: int, now):
        """그 번호를 되돌리는 계산(장부에 적음)과 적용 → (되돌리기 번호, 짧은 답, 적용 뒤 ERP 의 값)."""
        back = self.dir / f"rollback-{number}.json"
        short = self.cli("rollback", "--change", number, "--snapshot", self.read(now), "--record", "--out", back)
        return short["change_id"], short, self.apply(short["change_id"], back, now)

    def listed(self) -> dict:
        return {entry["id"]: entry for entry in self.cli("list", "--all")["changes"]}

    def offered(self, number: int, now) -> int:
        """그 번호를 지금 되돌리자고 하면 되돌릴 칸 수(장부에 적지 않는 계산) — 되돌릴 것이 없다고 하면 0."""
        out = self.dir / f"offer-{self.files}.json"
        done = subprocess.run([sys.executable, "-B", str(SCRIPT), "rollback", "--change", str(number), "--snapshot",
                               str(self.read(now)), "--out", str(out)], capture_output=True, text=True, env=self.env)
        if done.returncode == 2:
            self.assertIn("아직 되돌리지 않은 것이 없습니다", json.loads(done.stderr)["error"])
            return 0
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["restored"]

    def test_a_a_rollback_of_a_rollback_brings_the_change_back_and_the_list_and_rollback_say_so(self):
        first = scene.snapshot()
        change, changed = self.change(first)
        rollback, _short, undone = self.undo(change, changed)
        self.assertEqual(undone.cells, first.cells, "ERP 는 바꾸기 전 값을 갖는다")
        cells = self.listed()[change]["written"]

        again, short, redone = self.undo(rollback, undone)
        self.assertEqual(redone.cells, changed.cells, "되돌리기를 되돌리면 ERP 는 바꾼 값을 다시 갖는다")
        self.assertEqual(short["undoing"], f"장부 {rollback}번({change}번 되돌리기)을 되돌립니다 — {change}번이 넣었던 값으로 돌아갑니다.")
        self.assertEqual((short["restored"], short["kept"]), (cells, 0))
        rows = self.listed()
        self.assertEqual((rows[change]["status"], rows[change]["rolled_back"], rows[change]["redone"]), ("applied", 0, cells))
        self.assertTrue(rows[change]["scope"].endswith(f"되돌렸다가 다시 살림 (장부 {rollback}번 · {again}번)"), rows[change]["scope"])
        self.assertEqual((rows[rollback]["status"], rows[rollback]["undone_by"]), ("rolled_back", [again]))
        self.assertIn(f"모두 되돌림 {cells}/{cells}칸 (장부 {again}번)", rows[rollback]["scope"])
        self.assertEqual(rows[again]["status"], "applied")
        self.assertEqual(self.offered(change, redone), cells, "ERP 에 바꾼 값이 있으니 바꾸기를 다시 되돌릴 수 있다")
        self.assertEqual(self.offered(rollback, redone), 0, "되돌리기의 값은 ERP 에 없다")
        self.assertEqual(self.offered(again, redone), cells)

        third, _short, back = self.undo(again, redone)
        self.assertEqual(back.cells, first.cells, "셋째 되돌리기 — 다시 바꾸기 전 값")
        rows = self.listed()
        self.assertEqual((rows[change]["status"], rows[change]["undone_by"]), ("rolled_back", [third]))
        self.assertTrue(rows[rollback]["scope"].endswith(f"되돌렸다가 다시 살림 (장부 {again}번 · {third}번)"), rows[rollback]["scope"])
        self.assertEqual((rows[again]["status"], rows[again]["undone_by"]), ("rolled_back", [third]))
        self.assertEqual([self.offered(number, back) for number in (change, rollback, again, third)], [0, cells, 0, cells])

    def test_b_a_rollback_of_a_restore_brings_the_change_back(self):
        first = scene.snapshot()
        saved = self.cli("save-snapshot", "--snapshot", self.read(first), "--sentence", "아침 상태 저장해 둬")["change_id"]
        change, changed = self.change(first)
        out = self.dir / "restore-1.json"
        restore = self.cli("restore", "--saved", saved, "--snapshot", self.read(changed), "--record", "--out", out)["change_id"]
        restored = self.apply(restore, out, changed)
        self.assertEqual(restored.cells, first.cells, "ERP 는 저장해 둔 값을 갖는다")
        cells = self.listed()[change]["written"]
        self.assertEqual((self.listed()[change]["status"], self.offered(change, restored)), ("rolled_back", 0))

        again, short, redone = self.undo(restore, restored)
        self.assertEqual(redone.cells, changed.cells, "저장 상태로 되돌리기를 되돌리면 ERP 는 바꾼 값을 다시 갖는다")
        self.assertEqual(short["undoing"], f"장부 {restore}번({saved}번 저장 상태로 되돌리기)을 되돌립니다 — {restore}번이 바꾸기 전 값으로 "
                                           "돌아갑니다.")
        rows = self.listed()
        self.assertEqual((rows[change]["status"], rows[change]["redone_by"]), ("applied", [restore, again]))
        self.assertTrue(rows[change]["scope"].endswith(f"되돌렸다가 다시 살림 (장부 {restore}번 · {again}번)"), rows[change]["scope"])
        self.assertEqual((rows[restore]["status"], rows[restore]["undone_by"]), ("rolled_back", [again]))
        self.assertEqual([self.offered(number, redone) for number in (change, restore, again)], [cells, 0, cells])

    def test_d_compare_names_the_change_that_held_a_cell_when_saved_and_the_record_that_holds_it_now(self):
        """지금 상태 저장 뒤에 바꾸기를 되돌리고 · 다시 살리고 · 또 되돌려도, 견주기는 저장 때 칸을 가졌던 바꾸기(`edited_by`)와 지금
        칸을 가진 마지막 기록(`written_by`)을 댄다 — 되돌린 바꾸기도 저장 때는 그 칸을 가졌다."""
        change, changed = self.change(scene.snapshot())
        saved = self.cli("save-snapshot", "--snapshot", self.read(changed), "--sentence", "바꾼 뒤 상태 저장해 둬")["change_id"]
        rollback, _short, undone = self.undo(change, changed)
        again, _short, redone = self.undo(rollback, undone)
        third, _short, back = self.undo(again, redone)
        out = self.dir / "compare-1.json"
        self.cli("compare", "--saved", saved, "--snapshot", self.read(back), "--out", out)
        cells = [cell for cell in json.loads(out.read_text(encoding="utf-8"))["cells"] if cell["kind"] == "changed"]
        self.assertEqual(len(cells), self.listed()[change]["written"])
        self.assertEqual({(cell["edited_by"], cell["written_by"]) for cell in cells}, {(change, third)})

    def test_c_the_preview_page_of_a_rollback_of_a_rollback_says_what_it_does(self):
        change, changed = self.change(scene.snapshot())
        rollback, _short, undone = self.undo(change, changed)
        out = self.dir / "rollback-again.json"
        self.cli("rollback", "--change", rollback, "--snapshot", self.read(undone), "--out", out)
        page = Path(self.cli("render", "rollback", "--plan", out)["page"]).read_text(encoding="utf-8")
        self.assertIn(f"장부 {rollback}번({change}번 되돌리기)을 되돌립니다 — {change}번이 넣었던 값으로 돌아갑니다.", page)
        self.assertIn("이 되돌리기도 장부에 한 번의 변경으로 적혀서, 다시 되돌릴 수 있습니다", page)
        self.assertNotIn("다시 되돌리지 않습니다", page)


if __name__ == "__main__":
    unittest.main()
