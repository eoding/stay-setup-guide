"""N1 — 명령은 없는 폴더에서 죽지 않고, 무슨 일이 있어도 파이썬 Traceback 으로 끝나지 않는다.

마지막 시운전에서 `read-calls --out "<작업>/읽기-2/calls.json"` 이 읽기 폴더가 없어 FileNotFoundError 와 Traceback, 종료 코드 1(「다른 값이
있음」의 자리)로 죽었다. 이제 결과 파일을 쓰는 명령은 모두 기록 폴더 안의 없는 폴더를 만들며 쓰고(밖의 없는 폴더는 만들지 않고
거절한다), 예상하지 못한 오류는 표준 오류에 JSON 한 줄 · 종료 코드 2 이며 명령의 잘못이면 멈추고 그 글을 그대로 전하라고 한다.

    python3 -m unittest discover -s tests
"""

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
SCRIPT = SCRIPTS / "price_change.py"
sys.path.insert(0, str(SCRIPTS))

import scene  # noqa: E402
from price_model import decode_step, encode_request, encode_snapshot  # noqa: E402

ERP = HERE / "fixtures" / "erp"


def answer(call):
    from change_core.answers import ask_sum
    return {"ok": True, "op": call["op"], "no": call["no"], "ask": ask_sum(call["payload"]), "saved": True, "pressed": True,
            "note": "저장했습니다"}


def sheet_example() -> dict:
    text = (HERE.parent / "references" / "commands.md").read_text(encoding="utf-8")
    section = text[text.index("### 요금표 (`kind: sheet`)"):]
    return json.loads(re.search(r"```json\n(.*?)```", section, re.S).group(1))


class Commands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.records = self.dir / "기록"
        self.env = scene.env(str(self.records))
        self.written = []

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, f"{args[0]}: {done.stderr or done.stdout}")
        self.assertNotIn("Traceback", done.stderr)
        return json.loads(done.stdout) if code in (0, 1) else json.loads(done.stderr)

    def out(self, *args, name="out.json", code=0):
        """명령 하나를 아직 없는 폴더(작업 폴더 안의 새 이름)에 쓰게 부른다 — 쓴 파일의 자리와 답을 돌려준다."""
        folder = self.work / f"없는-{len(self.written) + 1}" / "그 안"
        self.assertFalse(folder.parent.exists())
        path = folder / name
        result = self.cli(*args, "--out", path, code=code)
        self.assertTrue(path.is_file(), f"{args[0]} 이 없는 폴더를 만들며 쓴다")
        self.written.append(args[0] if args[0] != "render" else f"render {args[1]}")
        return path, result

    def file(self, name, data) -> Path:
        path = self.dir / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path


class MissingFolderTest(Commands):
    def test_every_command_that_writes_a_file_makes_the_missing_folder_inside_the_record_folder(self):
        self.work = self.records / "작업" / "시험"
        path, _ = self.out("work")
        self.work = Path(json.loads(path.read_text(encoding="utf-8"))["work"])

        looks = self.work / "look"
        looks.mkdir()
        (looks / "look-1.json").write_text(json.dumps({
            "op": "look", "ok": True, "login": False, "hotel": scene.HOTEL_REF, "offer": scene.OFFER, "offers": [scene.OFFER],
            "pairs": [{"room": room, "rate_plan": plan} for room, plan, _ in scene.GROUPS],
            "doneAt": "2026-11-20T05:00:00.000Z"}, ensure_ascii=False), encoding="utf-8")
        look, _ = self.out("look", "--answers", looks)
        self.out("list", "--look", look)
        self.out("rooms", "--look", look, "--date", "2026-12-25")
        sheet, _ = self.out("sheet", "--sheet", self.file("sheet.json", sheet_example()), "--look", look)
        self.out("render", "sheet", "--plan", sheet, name="sheet.html")

        request = self.file("request.json", encode_request(scene.request()))
        calls, _ = self.out("read-calls", "--request", request, name="calls.json")
        self.out("reserved", "--calls", calls, "--answers", calls.parent)
        self.out("read", "--hotel", scene.HOTEL, "--hotel-id", scene.HOTEL_ID, "--price-page",
                 f"디럭스={ERP / 'price-runs-closed-absent-list.html'}", "--read-at", scene.NOW_TEXT, name="snapshot.json")

        snapshot = self.file("snapshot.json", encode_snapshot(scene.snapshot()))
        _, saved = self.out("save-snapshot", "--snapshot", snapshot)
        self.out("render", "prices", "--snapshot", snapshot, name="prices.html")
        said = self.file("고름.json", [{"rule": "ABOVE_LIST", "choice": "raise_list", "said": "정가도 같이 올려"}])
        plan, short = self.out("plan", "--snapshot", snapshot, "--request", request, "--resolutions", said, "--record",
                               name="plan-1.json")
        change = short["change_id"]
        self.out("render", "preview", "--plan", plan, name="preview.html")
        fresh = self.file("fresh.json", encode_snapshot(scene.fresh(scene.snapshot())))
        self.out("stale", "--change", change, "--snapshot", fresh)
        self.out("begin", "--change", change, "--plan", plan, "--snapshot", fresh)
        _, calls = self.out("calls", "--change", change)
        self.out("check", "--change", change, "--snapshot", fresh)
        for call in calls["calls"]:
            self.out("record-result", "--change", change, "--result", self.file(f"r{call['no']}.json", answer(call)))
        steps = [decode_step(step) for step in json.loads(plan.read_text(encoding="utf-8"))["steps"]]
        after = self.file("after.json", encode_snapshot(scene.applied(scene.fresh(scene.snapshot()), steps, scene.NOW_TEXT)))
        self.out("verify", "--change", change, "--snapshot", after)
        self.out("render", "result", "--change", change, name="result.html")
        rollback, _ = self.out("rollback", "--change", change, "--snapshot", after, "--record", name="rollback-1.json")
        self.out("render", "rollback", "--plan", rollback, name="rollback.html")
        self.out("restore", "--saved", saved["change_id"], "--snapshot", after, "--record", name="rollback-2.json")
        compare, _ = self.out("compare", "--saved", saved["change_id"], "--snapshot", after, name="compare-1.json")
        self.out("render", "compare", "--plan", compare, name="compare.html")

        from price_change import parser
        commands = next(action for action in parser()._actions if hasattr(action, "choices") and action.choices).choices
        self.assertEqual({name.split()[0] for name in self.written}, set(commands), "모든 명령이 결과 파일을 쓴다 — 하나도 빠짐없이 봤다")

    def test_a_missing_folder_outside_the_record_folder_is_refused_before_anything_is_recorded_and_not_made(self):
        snapshot = self.file("snapshot.json", encode_snapshot(scene.snapshot()))
        outside = self.dir / "밖" / "없는 폴더" / "s.json"
        refused = self.cli("save-snapshot", "--snapshot", snapshot, "--out", outside, code=2)
        self.assertIn("기록 폴더", refused["error"])
        self.assertFalse(outside.parent.parent.exists(), "기록 폴더 밖에는 폴더를 만들지 않는다")
        self.assertEqual(self.cli("list", "--all")["changes"], [], "거절하기 전에 장부에 적지 않았다")
        there = self.dir / "s.json"
        self.cli("save-snapshot", "--snapshot", snapshot, "--out", there)
        self.assertTrue(there.is_file(), "밖이라도 있는 폴더에는 쓴다")


class UnexpectedErrorTest(Commands):
    """명령 안에서 예상하지 못한 오류가 나도 Traceback 이 아니라 JSON 한 줄 · 종료 코드 2 다. 명령의 잘못이면 멈추고 그대로 전하라고 한다."""

    def forced(self, setup: str, *argv) -> subprocess.CompletedProcess:
        code = (f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); import price_change\n{setup}\n"
                f"sys.exit(price_change.main({list(map(str, argv))!r}))")
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=self.env)

    def one_line(self, done) -> dict:
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assertEqual(len(done.stderr.strip().splitlines()), 1, done.stderr)
        self.assertEqual(done.stdout, "")
        return json.loads(done.stderr)

    def test_a_bug_inside_a_command_is_one_json_line_that_says_to_stop_and_pass_the_text_on(self):
        said = self.one_line(self.forced("def boom(*_):\n    raise AttributeError('보기 오류')\nprice_change.files.new_work = boom", "work"))
        self.assertTrue(said["error"].startswith("명령에 잘못이 있습니다(예상하지 못한 오류 AttributeError: 보기 오류"), said)
        self.assertIn("여기서 멈추고, 이 글을 고치지 말고 그대로 담당자에게 전해 주세요", said["error"])

    def test_a_file_the_command_cannot_write_is_one_json_line_naming_the_file(self):
        self.records.mkdir()
        said = self.one_line(self.forced("", "list", "--all", "--out", str(self.records)))
        self.assertIn(f"파일을 읽거나 쓰지 못했습니다: {self.records}", said["error"])
        self.assertIn("폴더입니다", said["error"])
        self.assertNotIn("멈추고", said["error"], "명령의 잘못이 아니다 — 경로를 고치면 된다")


if __name__ == "__main__":
    unittest.main()
