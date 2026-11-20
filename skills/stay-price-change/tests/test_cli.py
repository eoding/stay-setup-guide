"""명령 한 바퀴 — 화면 조각 읽기, 미리보기, 페이지, 낡음 확인, 적용 시작, 저장마다 적기, 확인, 되돌리기, 목록.

    python3 -m unittest discover -s tests

장부는 `STAY_PRICE_LEDGER_DIR` 로 임시 폴더에 둔다.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
from price_model import CellKey, Snapshot, decode_snapshot, decode_step, encode_request, encode_snapshot  # noqa: E402


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = {**os.environ, "STAY_PRICE_LEDGER_DIR": str(self.dir / "기록")}
        self.snapshot = self.write("snapshot.json", encode_snapshot(scene.snapshot()))
        self.request = self.write("request.json", encode_request(scene.request()))
        self.choice = self.write("resolutions.json", [{"rule": "ABOVE_LIST", "choice": "raise_list"}])

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.dir / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def write_text(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def run_cli(self, *args, code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def test_read_builds_a_snapshot_from_fragments(self):
        erp = HERE / "fixtures" / "erp"
        adjust = (erp / "adjust-rejected.html").read_text(encoding="utf-8").replace("<td>스위트</td>", "<td>디럭스</td>")
        result = self.run_cli("read", "--hotel", "데모 호텔", "--hotel-id", "1", "--price-page", f"디럭스={erp / 'price-runs-closed-absent-list.html'}",
                              "--adjust-page", self.write_text("adjust.html", adjust), "--read-at", "2026-11-20T14:02:00+09:00",
                              "--out", self.dir / "read.json")
        snapshot = decode_snapshot(json.loads((self.dir / "read.json").read_text(encoding="utf-8")))
        self.assertEqual((result["offer"], len(snapshot.cells), snapshot.currency), ("샘플 오퍼", 16, "USD"))
        self.assertIn(("디럭스", "2026-12-24"), snapshot.reserved)
        error = self.run_cli("read", "--hotel", "H", "--hotel-id", "9", "--price-page", f"디럭스={erp / 'calendar-adjust--step2.html'}", code=2)
        self.assertIn("가격 수정", error["error"])
        self.assertIn("캘린더의 객실 이름=파일", self.run_cli("read", "--hotel", "H", "--hotel-id", "9", "--price-page", erp / "calendar-adjust--step2.html", code=2)["error"])

    def test_preview_apply_verify_rollback_and_list(self):
        first = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--record",
                             "--out", self.dir / "plan1.json")
        change = first["change_id"]
        self.assertEqual((first["counts"]["cells"], len(first["unresolved"]), first["steps"]), (90, 2, None))
        self.assertIn("빨간 줄", self.run_cli("begin", "--change", change, "--plan", self.dir / "plan1.json", code=2)["error"])

        self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--resolutions", self.choice,
                     "--out", self.dir / "plan.json")
        plan = json.loads((self.dir / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(len(plan["steps"]), 8)
        page = Path(self.run_cli("render", "preview", "--plan", self.dir / "plan.json")["page"])
        self.assertEqual(page.parent, self.dir / "기록")
        self.assertTrue(page.name.endswith("· 데모 호텔 · 미리보기.html"))
        self.assertIn("ERP 에 8번 나눠 저장합니다", page.read_text(encoding="utf-8"))
        again = Path(self.run_cli("render", "preview", "--plan", self.dir / "plan.json")["page"])
        self.assertNotEqual(again, page)

        self.assertTrue(self.run_cli("stale", "--before", self.snapshot, "--after", self.snapshot)["same"])
        moved = scene.snapshot()
        key = CellKey("디럭스", "조식 포함", "2026-12-25", "A2", 1)
        moved = replace(moved, cells={**moved.cells, key: replace(moved.cells[key], sell=moved.cells[key].sell + 1)})
        stale = self.run_cli("stale", "--before", self.snapshot, "--after", self.write("moved.json", encode_snapshot(moved)),
                             code=1)
        self.assertEqual([item["key"]["date"] for item in stale["differences"]], ["2026-12-25"])

        self.assertEqual(self.run_cli("begin", "--change", change, "--plan", self.dir / "plan.json")["status"], "applying")
        for index in range(1, 6):
            self.run_cli("record-step", "--change", change, "--step", index, "--saved")
        self.assertEqual(self.run_cli("record-step", "--change", change, "--step", 6, "--failed", "--note", "로그인")["status"],
                         "stopped")
        for index in range(6, 9):
            last = self.run_cli("record-step", "--change", change, "--step", index, "--saved")
        self.assertEqual(last["status"], "applied")

        after = self.write("after.json", encode_snapshot(scene.applied(scene.snapshot(), map(decode_step, plan["steps"]))))
        self.assertTrue(self.run_cli("verify", "--change", change, "--snapshot", after)["same"])
        result = Path(self.run_cli("render", "result", "--change", change, "--out", self.dir / "result.html")["page"])
        self.assertIn("90칸 모두 넣은 값과 같습니다", result.read_text(encoding="utf-8"))

        rollback = self.run_cli("rollback", "--change", change, "--snapshot", after, "--record", "--sentence", "방금 것 되돌려",
                                "--out", self.dir / "rollback.json")
        self.assertEqual((len(rollback["rollback"]["restored"]), rollback["rollback"]["kept"], len(rollback["steps"])),
                         (90, [], 8))
        page = Path(self.run_cli("render", "rollback", "--plan", self.dir / "rollback.json")["page"])
        self.assertIn("에 적어 둔 값으로 되돌립니다", page.read_text(encoding="utf-8"))
        self.assertEqual(self.run_cli("begin", "--change", rollback["change_id"], "--plan", self.dir / "rollback.json")["steps"], 8)

        snapshot_id = self.run_cli("save-snapshot", "--snapshot", after)["change_id"]
        listed = self.run_cli("list")
        self.assertEqual([(row["id"], row["kind"], row["status"]) for row in listed["changes"]],
                         [(snapshot_id, "snapshot", "applied"), (rollback["change_id"], "rollback", "applying"),
                          (change, "change", "applied")])
        self.assertTrue(listed["ledger"].endswith("가격장부.sqlite3"))

    def test_a_request_on_another_value_and_a_clear_request_plan_through_the_command(self):
        clear = self.write("clear.json", encode_request(scene.request(operation="clear", value=None, field="list")))
        result = self.run_cli("plan", "--snapshot", self.snapshot, "--request", clear)
        self.assertEqual([(step["kind"], step["clear"]) for step in result["steps"]], [("cell_edit", ["list"])] * 2)
        self.assertEqual(result["counts"]["skipped"], 94)
        supply = self.write("supply.json", encode_request(scene.request(operation="percent", value=D("10"), field="supply")))
        self.assertEqual(self.run_cli("plan", "--snapshot", self.snapshot, "--request", supply)["counts"]["skipped"], 96)

    def test_mismatched_input_and_a_plan_for_another_request_are_refused(self):
        other = self.write("other.json", {**encode_request(scene.request()), "hotel": {"id": "2", "name": "데모 호텔"}})
        refused = self.run_cli("plan", "--snapshot", self.snapshot, "--request", other, code=2)["error"]
        self.assertIn("호텔 1 (데모 호텔)", refused, "G2 — 이름이 같아도 번호가 다르면 다른 호텔이다")
        self.assertIn("호텔 2 (데모 호텔)", refused)
        nameless = self.write("nameless.json", {**encode_request(scene.request()), "hotel": "데모 호텔"})
        self.assertIn("호텔 번호 없이", self.run_cli("plan", "--snapshot", self.snapshot, "--request", nameless, code=2)["error"])
        change = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--record")["change_id"]
        fifteen = self.write("request15.json", encode_request(scene.request("15")))
        self.run_cli("plan", "--snapshot", self.snapshot, "--request", fifteen, "--resolutions", self.choice,
                     "--out", self.dir / "plan15.json")
        self.assertIn("다른 계산", self.run_cli("begin", "--change", change, "--plan", self.dir / "plan15.json", code=2)["error"])
        self.assertIn("파일이 없습니다", self.run_cli("stale", "--before", "없는.json", "--after", self.snapshot, code=2)["error"])


if __name__ == "__main__":
    unittest.main()
