"""명령의 글은 콘솔의 코드 페이지와 상관없이 UTF-8 이다.

윈도의 파이썬은 파이프로 나가는 글을 그 컴퓨터의 코드 페이지(한국어 윈도 cp949 · 영어 윈도 cp1252)로, 없는 글자에서 멈추는
strict 로 쓴다. 명령이 장부를 적은 뒤에 결과를 쓰다 죽으면 장부는 적혔는데 답은 Traceback 이다. `PYTHONIOENCODING` 으로 같은
코드 페이지 · 같은 strict 를 세우고, 이 길을 지난다: 빨간 줄이 있는 미리보기(— 가 든 예), 저장됐는지 모르는 저장 적기, 베트남
글자가 든 호텔 이름의 calls · list, 그리고 work. 답은 모두 UTF-8 JSON 이고 종료 코드는 0 이다.

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
from browser_replies import NOW  # noqa: E402
from change_core.answers import ask_sum  # noqa: E402
from price_model import encode_request, encode_snapshot  # noqa: E402

CODE_PAGES = ("cp949", "cp1252")
HOTEL = "Khách sạn Hà Nội"      # 지어낸 이름 — cp949 에도 cp1252 에도 없는 글자(ạ · ộ)가 든다


class ConsoleEncodingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.dir / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def run_cli(self, page, *args, code=0):
        env = dict(scene.env(str(self.dir / f"기록-{page}")), PYTHONIOENCODING=page)
        done = subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)], capture_output=True, env=env)
        said = done.stderr.decode("utf-8", "replace")
        self.assertEqual(done.returncode, code, f"{page} · {args[0]}: {said}")
        self.assertNotIn("Traceback", said)
        return json.loads(done.stdout.decode("utf-8")) if code == 0 else done.stderr.decode("utf-8")

    def test_every_answer_is_utf8_json_on_a_korean_and_an_english_windows_code_page(self):
        snapshot = replace(scene.snapshot(), hotel=HOTEL)
        request = replace(scene.request(), hotel=HOTEL)
        snap = self.write("snapshot.json", encode_snapshot(snapshot))
        ask = self.write("request.json", encode_request(request))
        choice = self.write("choice.json", [{"rule": "ABOVE_LIST", "choice": "raise_list", "said": "정가도 같이 올려"}])
        later = replace(snapshot, read_at=NOW.replace(minute=1).isoformat())   # 미리보기를 적은 뒤에 다시 읽은 값
        fresh = self.write("fresh.json", encode_snapshot(later))
        for page in CODE_PAGES:
            with self.subTest(page):
                self.assertIn("작업", self.run_cli(page, "work")["work"])
                red = self.run_cli(page, "plan", "--snapshot", snap, "--request", ask, "--record")
                self.assertEqual(red["red"][0]["choices"][0]["example"],
                                 "1/1 금 · 스위트 · 조식 포함 · 성인 2 · 1박 이상 — 정가 500.00 → 550.00")
                planned = self.run_cli(page, "plan", "--snapshot", snap, "--request", ask, "--resolutions", choice, "--record",
                                       "--replaces", red["change_id"])
                plan = self.write(f"plan-{page}.json", planned)
                change = planned["change_id"]
                self.assertEqual(self.run_cli(page, "begin", "--change", change, "--plan", plan, "--snapshot", fresh)["status"],
                                 "applying")
                calls = self.run_cli(page, "calls", "--change", change)["calls"]
                self.assertEqual(calls[0]["payload"]["hotel"]["name"], HOTEL)
                first = calls[0]
                unknown = {"ok": False, "op": first["op"], "no": first["no"], "ask": ask_sum(first["payload"]), "pressed": True,
                           "saved": "unknown", "error": "저장 뒤 화면이 답하지 않았습니다 — 저장됐는지 모릅니다"}
                recorded = self.run_cli(page, "record-result", "--change", change, "--result", self.write(f"unknown-{page}.json", unknown))
                self.assertEqual((recorded["saved"], recorded["status"]), (False, "stopped"))
                listed = self.run_cli(page, "list", "--all")
                self.assertEqual({entry["hotel"] for entry in listed["changes"]}, {HOTEL})
                self.assertIn("저장 ", next(entry for entry in listed["changes"] if entry["id"] == change)["scope"])
                self.assertIn("render preview 에는 --plan 가 필요합니다", self.run_cli(page, "render", "preview", code=2),
                              "인자를 잘못 준 알림도 UTF-8 이다 — 명령의 첫 줄에서 바꾼다")


if __name__ == "__main__":
    unittest.main()
