"""K2 — 저장해 둔 상태로 되돌리면, 그 저장 뒤에 이 장부가 넣었다가 그 되돌리기가 덮은 값은 되돌린 것으로 적힌다(되돌리기와 같이).

다섯 번째 시운전의 차례 그대로: 지금 상태 저장(1) → 바꾸기(2) 적용 → 1번 상태로 되돌리기(3) 적용. 그 뒤 목록에서 2번이 「적용」
으로 남아 "방금 바꾼 거 되돌려"가 2번을 다시 내밀고, 그 되돌리기는 모든 칸을 「그 사이 바뀜」으로 보였다. 이제 2번은 모두 되돌린
변경이고(되돌린 번호 3), 2번을 되돌리자고 하면 되돌릴 것이 없다. 일부만 덮었으면 일부 되돌림이고 나머지만 되돌린다.

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


class RestoreSettlesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = scene.env(self.dir / "기록")
        self.files = 0

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data) -> Path:
        self.files += 1
        path = self.dir / f"file-{self.files}.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def cli(self, *args, code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def apply(self, change: int, plan: Path, now):
        """begin → calls → 저장마다 「저장했다」는 답 → 그 저장이 들어간 지금 값."""
        again = replace(scene.fresh(now), read_at=scene.read_again(2))   # 계산(1분 뒤에 읽은 값) 뒤에 다시 읽은 값
        self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.write(encode_snapshot(again)))
        for call in self.cli("calls", "--change", change)["calls"]:
            answer = {"ok": True, "op": call["op"], "no": call["no"], "ask": ask_sum(call["payload"]), "saved": True, "pressed": True}
            self.cli("record-result", "--change", change, "--result", self.write(answer))
        steps = json.loads(plan.read_text(encoding="utf-8"))["steps"]
        return scene.applied(scene.fresh(now), map(decode_step, steps), scene.NOW_TEXT)

    def save_change_restore(self, *flags):
        """저장(1) → 연말 10% 바꾸기(2) 적용 → 1번 상태로 되돌리기(3, 고르기 플래그) 적용. 세 번호와 마지막 지금 값."""
        before = scene.fresh(scene.snapshot())
        saved = self.cli("save-snapshot", "--snapshot", self.write(encode_snapshot(before)),
                         "--sentence", "아침 상태 저장해 둬")["change_id"]
        plan = self.dir / "plan-1.json"
        change = self.cli("plan", "--snapshot", self.write(encode_snapshot(before)), "--request",
                          self.write(encode_request(scene.request())), "--record", "--resolutions",
                          self.write([{"rule": "ABOVE_LIST", "choice": "raise_list", "said": "정가도 같이 올려"}]),
                          "--out", plan)["change_id"]
        changed = self.apply(change, plan, before)
        back = self.dir / "rollback-1.json"
        restore = self.cli("restore", "--saved", saved, "--snapshot", self.write(encode_snapshot(changed)), "--record",
                           "--sentence", f"{saved}번 상태로 되돌려", *flags, "--out", back)
        restored = self.apply(restore["change_id"], back, changed)
        return saved, change, restore["change_id"], restored

    def listed(self) -> dict:
        return {entry["id"]: entry for entry in self.cli("list", "--all")["changes"]}

    def test_the_trial_sequence_save_change_restore_then_list_and_a_rollback_of_the_change(self):
        saved, change, restore, restored = self.save_change_restore()
        rows = self.listed()
        self.assertEqual((rows[saved]["status"], rows[change]["status"], rows[restore]["status"]),
                         ("saved", "rolled_back", "applied"), "되돌린 변경은 「적용」으로 남지 않는다")
        self.assertEqual((rows[change]["rolled_back"], rows[change]["written"], rows[change]["undone_by"]),
                         (rows[change]["written"], rows[change]["written"], [restore]))
        self.assertIn(f"모두 되돌림 {rows[change]['written']}/{rows[change]['written']}칸 (장부 {restore}번)", rows[change]["scope"])
        self.assertEqual([rows[number]["line"].split(" · ")[:2] for number in (saved, change, restore)],
                         [[f"장부 {saved}번", "11/21 10:01 저장"], [f"장부 {change}번", "11/21 10:00 적용"],
                          [f"장부 {restore}번", "11/21 10:00 적용"]],
                         "K4 — 저장해 둔 상태는 값을 읽은 때와 「저장」으로 확인받는다(적용이 아니다)")
        refused = self.cli("rollback", "--change", change, "--snapshot", self.write(encode_snapshot(restored)), "--record",
                           "--sentence", "방금 바꾼 거 되돌려", "--out", self.dir / "rollback-2.json", code=2)
        self.assertIn("아직 되돌리지 않은 것이 없습니다", refused["error"], "다시 내밀지 않는다")

    def test_a_restore_of_one_room_leaves_the_change_partly_rolled_back_and_its_rollback_takes_only_the_rest(self):
        saved, change, restore, restored = self.save_change_restore("--room", "디럭스")
        rows = self.listed()
        self.assertEqual((rows[change]["status"], rows[change]["undone_by"]), ("partly_rolled_back", [restore]))
        self.assertLess(rows[change]["rolled_back"], rows[change]["written"])
        rest = self.cli("rollback", "--change", change, "--snapshot", self.write(encode_snapshot(restored)), "--record",
                        "--sentence", "나머지도 되돌려", "--out", self.dir / "rollback-2.json")
        self.assertEqual((rest["restored"], rest["kept"]), (rows[change]["written"] - rows[change]["rolled_back"], 0),
                         "그 사이 바뀐 칸으로 보이지 않고, 남은 칸만 되돌린다")
        plan = json.loads((self.dir / "rollback-2.json").read_text(encoding="utf-8"))["rollback"]
        self.assertTrue(all("디럭스" not in item["key"] for item in plan["restored"]), "1번 상태로 돌린 디럭스는 다시 돌리지 않는다")

    def test_a_value_already_overwritten_outside_the_helper_is_not_counted_as_undone_by_the_restore(self):
        before = scene.fresh(scene.snapshot())
        saved = self.cli("save-snapshot", "--snapshot", self.write(encode_snapshot(before)))["change_id"]
        plan = self.dir / "plan-1.json"
        change = self.cli("plan", "--snapshot", self.write(encode_snapshot(before)), "--request",
                          self.write(encode_request(scene.request())), "--record", "--resolutions",
                          self.write([{"rule": "ABOVE_LIST", "choice": "raise_list", "said": "정가도 같이 올려"}]),
                          "--out", plan)["change_id"]
        changed = self.apply(change, plan, before)
        key = sorted(key for key in changed.cells if changed.cells[key] != before.cells.get(key))[0]
        touched = scene.with_cells(changed, {key: replace(changed.cells[key], sell=changed.cells[key].sell + 1)})   # ERP 화면에서 고침
        back = self.dir / "rollback-1.json"
        restore = self.cli("restore", "--saved", saved, "--snapshot", self.write(encode_snapshot(touched)), "--record",
                           "--out", back)["change_id"]
        self.apply(restore, back, touched)
        row = self.listed()[change]
        self.assertEqual((row["status"], row["rolled_back"]), ("partly_rolled_back", row["written"] - 1),
                         "ERP 화면에서 먼저 덮인 칸은 그 변경이 되돌려진 것이 아니다")


if __name__ == "__main__":
    unittest.main()
