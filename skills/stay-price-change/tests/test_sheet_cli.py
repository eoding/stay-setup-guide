"""새 요금표 한 바퀴를 명령으로 — sheet → render sheet → read-calls → plan(넣지 않는 것) → 미리보기 → 적용 → 결과.

지어낸 요금표(sheet_scene): 객실 2 × 시즌 2 × 주중 · 주말 = 8줄, 성인 2 는 숫자, 성인 3 · 아동은 금액 차이, 3박 이상은 퍼센트.
읽은 값: 디럭스 비수기는 이미 같고 나머지는 다르다, 스위트에 요금표가 말하지 않는 성인 1 줄, 스위트 1/13 판매일 없음.

    python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import sheet_scene as S  # noqa: E402
from change_core.ledger import now_text  # noqa: E402
from price_browser import PAGE_KEEPS  # noqa: E402
from price_model import encode_snapshot  # noqa: E402
from price_pages import SEASON_REFILL_NOTE  # noqa: E402
from test_cli import answer  # noqa: E402
from test_pages import visible  # noqa: E402


class SheetCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = {**os.environ, "STAY_PRICE_LEDGER_DIR": str(self.dir / "기록")}
        self.look = self.write("look.json", S.look_data())
        self.sheet = self.write("sheet.json", S.sheet_data())

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.dir / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def run_cli(self, *args, code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def test_a_new_rate_sheet_end_to_end(self):
        check = self.run_cli("sheet", "--sheet", self.sheet, "--look", self.look, "--out", self.dir / "sheet-check.json")
        self.assertEqual((check["lines"], check["cells"]), (8, 112))
        self.assertNotIn("sheet", check, "Y6 — --out 의 짧은 답은 요금표를 다시 싣지 않는다")
        self.assertEqual(check["out"], str((self.dir / "sheet-check.json").resolve()))
        self.assertEqual(check["gaps"], [{"kind": "unnamed", "room": "패밀리", "rate_plan": S.PLAN, "occupancy": None, "nights": None,
                                          "dates": [], "lines": []}])
        self.assertEqual(check["reads"], {"readPair": 2, "readReserved": 1, "limit": PAGE_KEEPS, "fits": True})
        page = self.run_cli("render", "sheet", "--plan", self.dir / "sheet-check.json", "--out", self.dir / "sheet.html")["page"]
        self.assertIn("요금표를 이렇게 읽었습니다", visible(Path(page).read_text(encoding="utf-8")))

        calls = self.run_cli("read-calls", "--request", self.dir / "sheet-check.json")
        self.assertEqual([(c["room"], c["from"], c["to"]) for c in calls["pairs"]],
                         [("디럭스", "2027-01-04", "2027-01-17"), ("스위트", "2027-01-04", "2027-01-17")])
        self.assertEqual(len(calls["reserved"]), 1)

        snapshot = self.write("snapshot.json", encode_snapshot(S.reading(read_at=now_text())))
        planned = self.run_cli("plan", "--snapshot", snapshot, "--request", self.dir / "sheet-check.json", "--record",
                               "--out", self.dir / "plan.json")
        self.assertEqual((planned["counts"]["will_change"], planned["counts"]["red"], planned["counts"]["new"]), (80, 0, 0))
        self.assertEqual(planned["coverage"], {"untouched": 13, "unseen": 0, "no_sale": 1, "unknown": 0, "unnamed": 1})
        planned = dict(planned, **json.loads((self.dir / "plan.json").read_text(encoding="utf-8")))
        self.assertTrue(planned["plan"]["request"]["from_sheet"])
        changed = {(c["key"]["room"], c["key"]["date"], c["key"]["occupancy"], c["key"]["nights"]): (c["before"]["sell"], c["after"]["sell"])
                   for c in planned["plan"]["changes"]}
        self.assertEqual(changed[("디럭스", "2027-01-16", "A2", 3)], ("261.00", "270.00"))
        self.assertEqual(changed[("스위트", "2027-01-04", "A3", 1)], ("410.00", "440.00"))
        self.assertNotIn(("디럭스", "2027-01-08", "A3", 1), changed, "이미 같은 칸은 바뀌지 않는다")
        self.assertFalse([key for key in changed if key[2] == "A1" or key[1] == "2027-01-13" and key[0] == "스위트"])
        self.assertEqual([(s["room"], s["dates"][0], len(s["dates"]), len(s["rows"])) for s in planned["steps"]],
                         [("디럭스", "2027-01-11", 5, 4), ("디럭스", "2027-01-15", 2, 4), ("스위트", "2027-01-04", 5, 4),
                          ("스위트", "2027-01-08", 2, 4), ("스위트", "2027-01-11", 4, 4), ("스위트", "2027-01-15", 2, 4)])

        preview = visible(Path(self.run_cli("render", "preview", "--plan", self.dir / "plan.json")["page"]).read_text(encoding="utf-8"))
        self.assertIn(SEASON_REFILL_NOTE, preview)
        self.assertIn("스위트 · 조식 포함 성인 1 · 1박 이상 1/4 ~ 1/12, 1/14 ~ 1/17 (13일)", preview)

        change = planned["change_id"]
        self.assertEqual(self.run_cli("begin", "--change", change, "--plan", self.dir / "plan.json", "--snapshot", snapshot)["status"],
                         "applying")
        for call in self.run_cli("calls", "--change", change)["calls"]:
            last = self.run_cli("record-result", "--change", change, "--result", self.write(f"r{call['no']}.json", answer(call)))
        self.assertEqual(last["status"], "applied")
        result = visible(Path(self.run_cli("render", "result", "--change", change)["page"]).read_text(encoding="utf-8"))
        self.assertIn(SEASON_REFILL_NOTE, result)

    def test_one_room_at_a_time_and_a_sheet_too_big_for_one_reading(self):
        part = self.run_cli("sheet", "--sheet", self.sheet, "--look", self.look, "--room", "스위트", "--from", "2027-01-11",
                            "--out", self.dir / "part.json")
        self.assertEqual((part["cells"], part["range"]["pairs"], part["range"]["first"]), (7 * 4, 1, "2027-01-11"))
        self.assertEqual(json.loads((self.dir / "part.json").read_text(encoding="utf-8"))["range"]["pairs"],
                         [{"room": "스위트", "rate_plan": S.PLAN}])
        rooms = [f"객실 {n}" for n in range(1, PAGE_KEEPS // 2 + 1)]   # 1년은 객실마다 가격 읽기 2번 + 예약 읽기 1번 — 하나 넘친다
        big = dict(S.sheet_data(), lines=[{"room": room, "rate_plan": S.PLAN, "periods": [{"from": "2027-01-01", "to": "2027-12-31"}],
                                           "rows": S.rows("200")} for room in rooms])
        look = dict(S.look_data(), pairs=[{"room": room, "rate_plan": S.PLAN} for room in rooms])
        check = self.run_cli("sheet", "--sheet", self.write("big.json", big), "--look", self.write("big-look.json", look),
                             "--out", self.dir / "big-check.json")
        self.assertFalse(check["reads"]["fits"])
        error = self.run_cli("read-calls", "--request", self.dir / "big-check.json", code=2)["error"]
        self.assertIn("읽기 한 번에 들지 않습니다", error)
        self.assertIn("이 요금표(부분)는", error)
        self.assertIn(f"{PAGE_KEEPS}번까지", error)

    def test_the_wrong_file_or_hotel_is_refused(self):
        snapshot = self.write("snapshot.json", encode_snapshot(S.reading()))
        self.assertIn("sheet 명령", self.run_cli("plan", "--snapshot", snapshot, "--request", self.sheet, code=2)["error"])
        other = self.write("other-look.json", dict(S.look_data(), hotel={"id": "2", "name": S.HOTEL}))
        self.assertIn("look 의 답은 호텔 2", self.run_cli("sheet", "--sheet", self.sheet, "--look", other, code=2)["error"])
        long = self.write("long-look.json", {k: v for k, v in S.look_data().items() if k != "pairs"} | {"body": {"id": "x"}})
        self.assertIn("look --answers", self.run_cli("sheet", "--sheet", self.sheet, "--look", long, code=2)["error"])
        self.run_cli("sheet", "--sheet", self.sheet, "--look", self.look, "--out", self.dir / "c.json")
        krw = self.write("krw.json", encode_snapshot(replace(S.reading(), currency="KRW")))
        self.assertIn("통화", self.run_cli("plan", "--snapshot", krw, "--request", self.dir / "c.json", code=2)["error"])


if __name__ == "__main__":
    unittest.main()
