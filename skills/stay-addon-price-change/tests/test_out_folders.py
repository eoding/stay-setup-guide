"""N1 — 명령은 없는 폴더에서 죽지 않고, 무슨 일이 있어도 파이썬 Traceback 으로 끝나지 않는다(가격 캘린더 도우미와 같은 끝마무리 —
change_core.cli).

결과 파일을 쓰는 명령은 모두 기록 폴더 안의 없는 폴더(`<작업>/읽기-2/` …)를 만들며 쓰고, 밖의 없는 폴더는 만들지 않고 거절한다.
예상하지 못한 오류는 표준 오류에 JSON 한 줄 · 종료 코드 2 이며, 명령의 잘못이면 멈추고 그 글을 그대로 전하라고 한다.

    python3 -m unittest discover -s tests
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

import addon_scene as scene
from test_flow import BOTH, SCRIPT, Flow

SCRIPTS = SCRIPT.parent


class Commands(Flow):
    def setUp(self):
        super().setUp()
        self.records = Path(self.env["STAY_PRICE_LEDGER_DIR"])
        self.written = []
        self.place = self.records / "작업" / "시험"

    def out(self, *args, name="out.json", code=0):
        """명령 하나를 아직 없는 폴더에 쓰게 부른다 — 쓴 파일의 자리와 답을 돌려준다."""
        folder = self.place / f"없는-{len(self.written) + 1}" / "그 안"
        self.assertFalse(folder.parent.exists())
        path = folder / name
        result = self.cli(*args, "--out", path, code=code)
        self.assertTrue(path.is_file(), f"{args[0]} 이 없는 폴더를 만들며 쓴다")
        self.written.append(args[0])
        return path, result

    def reading(self, *flags) -> Path:
        calls, _ = self.out("read-calls", *flags, name="calls.json")
        lines = json.loads(calls.read_text(encoding="utf-8"))["lines"]
        scene.write_answers(calls.parent, "line", [self.erp.read_line(call) for call in lines])
        return self.out("read", "--calls", calls, "--answers", calls.parent, name="snapshot.json")[0]


class MissingFolderTest(Commands):
    def test_every_command_that_writes_a_file_makes_the_missing_folder_inside_the_record_folder(self):
        path, _ = self.out("work")
        self.place = Path(json.loads(path.read_text(encoding="utf-8"))["work"])
        scene.write_answers(self.place / "look", "look", [scene.look_answer(self.erp)])
        look, _ = self.out("look", "--answers", self.place / "look")
        self.out("list", "--look", look)
        self.out("render", "prices", "--look", look, name="prices.html")

        request = self.request()
        snapshot = self.reading("--request", request, "--look", look)
        self.out("render", "window", "--snapshot", snapshot, name="window.html")
        plan, short = self.out("plan", "--snapshot", snapshot, "--request", request, "--record", name="plan-1.json")
        change = short["change_id"]
        self.out("render", "preview", "--plan", plan, name="preview.html")
        self.out("begin", "--change", change, "--plan", plan, "--snapshot", self.reading("--record", change))
        _, calls = self.out("calls", "--change", change)
        for call in calls["calls"]:
            self.out("record-result", "--change", change, "--result", self.file(f"r{call['no']}.json", self.erp.apply(call["payload"])))
        after = self.reading("--record", change)
        self.out("check", "--change", change, "--snapshot", after)
        self.out("verify", "--change", change, "--snapshot", after)
        self.out("render", "result", "--change", change, "--snapshot", after, name="result.html")
        rollback, _ = self.out("rollback", "--change", change, "--snapshot", after, "--record", name="rollback-1.json")
        self.out("render", "rollback", "--plan", rollback, name="rollback.html")

        from addon_change import parser
        commands = next(action for action in parser()._actions if hasattr(action, "choices") and action.choices).choices
        self.assertEqual(set(self.written), set(commands), "모든 명령이 결과 파일을 쓴다 — 하나도 빠짐없이 봤다")

    def test_a_missing_folder_outside_the_record_folder_is_refused_and_not_made(self):
        outside = Path(self.folder.name) / "밖" / "없는 폴더" / "calls.json"
        refused = self.cli("read-calls", "--request", self.request(lines=BOTH[:1]), "--out", outside, code=2)
        self.assertIn("기록 폴더", refused["error"])
        self.assertFalse(outside.parent.parent.exists(), "기록 폴더 밖에는 폴더를 만들지 않는다")


class UnexpectedErrorTest(Commands):
    def forced(self, setup: str, *argv) -> dict:
        code = (f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); import addon_change\n{setup}\n"
                f"sys.exit(addon_change.main({list(map(str, argv))!r}))")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assertEqual((len(done.stderr.strip().splitlines()), done.stdout), (1, ""), done.stderr)
        return json.loads(done.stderr)

    def test_a_bug_inside_a_command_is_one_json_line_that_says_to_stop_and_pass_the_text_on(self):
        said = self.forced("def boom(*_):\n    raise IndexError('보기 오류')\naddon_change.decode_request = boom",
                           "read-calls", "--request", self.request())
        self.assertTrue(said["error"].startswith("명령에 잘못이 있습니다(예상하지 못한 오류 IndexError: 보기 오류"), said)
        self.assertIn("여기서 멈추고, 이 글을 고치지 말고 그대로 담당자에게 전해 주세요", said["error"])

    def test_a_file_the_command_cannot_write_is_one_json_line_naming_the_file(self):
        said = self.forced("", "read-calls", "--request", self.request(), "--out", str(self.work))
        self.assertIn(f"파일을 읽거나 쓰지 못했습니다: {self.work}", said["error"])
        self.assertNotIn("멈추고", said["error"])


class ConsoleEncodingTest(Commands):
    """명령의 글은 콘솔의 코드 페이지와 상관없이 UTF-8 이다 — 윈도의 파이썬은 파이프로 나가는 글을 그 컴퓨터의 코드 페이지
    (cp949 · cp1252)로 쓰고 없는 글자에서 죽는다(가격 캘린더 도우미의 test_console_encoding). PYTHONIOENCODING 으로 같은 코드
    페이지를 세운다. 인자를 잘못 준 알림도 UTF-8 이다(명령의 첫 줄에서 바꾼다)."""

    def test_answers_are_utf8_on_a_korean_and_an_english_windows_code_page(self):
        for page in ("cp949", "cp1252"):
            with self.subTest(page):
                env = dict(self.env, STAY_PRICE_TEST_NOW=self.erp.clock.isoformat(), PYTHONIOENCODING=page)

                def run(*args, code=0):
                    done = subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)], capture_output=True, env=env)
                    self.assertEqual(done.returncode, code, done.stderr.decode("utf-8", "replace"))
                    self.assertNotIn(b"Traceback", done.stderr)
                    return done

                work = Path(json.loads(run("work").stdout.decode("utf-8"))["work"])
                scene.write_answers(work / "look", "look", [scene.look_answer(self.erp)])
                look = work / "look.json"
                run("look", "--answers", work / "look", "--out", look)
                listed = json.loads(run("list", "--look", look).stdout.decode("utf-8"))
                self.assertEqual(listed["hotel"]["name"], scene.HOTEL["name"])
                self.assertIn("render preview 에는 --plan 가 필요합니다", run("render", "preview", code=2).stderr.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
