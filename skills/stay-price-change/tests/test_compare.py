"""G1 — 시즌 [가격]을 다시 채우는 길((가))의 안전망: 채우기 전에 지금 상태를 저장하고, 채운 뒤 다시 읽어 저장해 둔 상태와 칸마다
견주고(compare), 원하면 같은 저장 상태로 되돌린다(restore). 도우미는 시즌 화면을 만지지 않는다.

명령으로 한 바퀴 — 날짜별로 바꾼 변경 하나를 적용하고, 지금 상태를 저장하고, 시즌을 다시 채운 것처럼 몇 칸이 바뀌고 한 칸이 새로
생기고 한 날에 예약이 든 값을 읽어 견준 뒤, 같은 저장 상태로 되돌리는 계산을 한다.

    python3 -m unittest discover -s tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
from change_core.answers import ask_sum  # noqa: E402
from price_model import CellKey, CellValue, cell_item_key, decode_step, encode_request, encode_snapshot  # noqa: E402
from price_pages import SEASON_SCREEN_NOTE  # noqa: E402

D = Decimal
REFILLED = [CellKey("디럭스", "조식 포함", day, occupancy, nights)
            for day in ("2026-12-25", "2026-12-26") for occupancy, _extra in scene.OCCUPANCIES for nights in scene.NIGHTS]
CREATED = CellKey("스위트", "룸온리", "2027-01-02", "A2", 1)       # 저장할 때 가격 없음 — 시즌을 다시 채워 생겼다
BOOKED = ("디럭스", "2026-12-26")                                 # 다시 읽은 값에서 예약이 있는 날 — 바뀐 칸 가운데 하루


class SeasonRefillSafetyNetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = scene.env(self.dir / "기록")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data) -> Path:
        path = self.dir / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def cli(self, *args, code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def apply_change(self):
        """날짜별로 바꾼 변경 하나(연말 10%)를 적용한다 → (장부 번호, 적용한 뒤 읽은 값)."""
        snapshot = scene.fresh(scene.snapshot())
        change = self.cli("plan", "--snapshot", self.write("snapshot.json", encode_snapshot(snapshot)),
                          "--request", self.write("request.json", encode_request(scene.request())), "--record",
                          "--resolutions", self.write("choices.json", [{"rule": "ABOVE_LIST", "choice": "raise_list",
                                                                        "said": "정가도 같이 올려"}]),
                          "--out", self.dir / "plan-1.json")["change_id"]
        steps = json.loads((self.dir / "plan-1.json").read_text(encoding="utf-8"))["steps"]
        self.cli("begin", "--change", change, "--plan", self.dir / "plan-1.json", "--snapshot", self.dir / "snapshot.json")
        for call in self.cli("calls", "--change", change)["calls"]:
            answer = {"ok": True, "op": call["op"], "no": call["no"], "ask": ask_sum(call["payload"]), "saved": True, "pressed": True}
            self.cli("record-result", "--change", change, "--result", self.write(f"r{call['no']}.json", answer))
        return change, scene.applied(snapshot, map(decode_step, steps), scene.NOW_TEXT)

    def test_g1_save_refill_compare_and_restore_through_the_commands(self):
        change, before = self.apply_change()
        saved = self.cli("save-snapshot", "--snapshot", self.write("saved.json", encode_snapshot(before)),
                         "--sentence", "시즌 다시 채우기 전에 저장해 둬")["change_id"]

        # 담당자가 ERP 에서 시즌 [가격]을 다시 채웠다 — 디럭스 · 조식 포함 연말 두 날의 12칸이 시즌 값으로, 가격 없던 한 칸이 생기고,
        # 다시 읽으니 바뀐 칸 가운데 12/26 디럭스에 예약이 있다
        cells = {key: replace(before.cells[key], sell=before.cells[key].sell + D("5.00")) for key in REFILLED}
        cells[CREATED] = CellValue(D("450.00"), None, None, "open")
        refilled = replace(scene.with_cells(before, cells, scene.NOW_TEXT), reserved=frozenset({BOOKED}))
        now = self.write("now.json", encode_snapshot(refilled))

        short = self.cli("compare", "--saved", saved, "--snapshot", now, "--out", self.dir / "compare-1.json")
        self.assertEqual({name: short["counts"][name] for name in ("changed", "edited", "reserved", "new", "gone", "closed")},
                         dict(changed=12, edited=12, reserved=6, new=1, gone=0, closed=0))
        self.assertEqual(short["counts"]["same"] + 13, short["counts"]["cells"])
        self.assertEqual((short["saved"], short["edited_by"]), (saved, [change]), "날짜별로 바꿔 둔 값은 그 변경 번호와 함께")
        self.assertEqual(short["example"], dict(key=dict(room="디럭스", rate_plan="조식 포함", date="2026-12-25", occupancy="A2",
                                                         nights=1), field="sell", then="220.00", now="225.00"))
        self.assertTrue(short["scope"].endswith("지금 상태 저장"), short["scope"])
        self.assertNotIn("cells", short, "짧은 답에 칸 목록은 없다")

        text = self.cli("render", "compare", "--plan", self.dir / "compare-1.json", "--text")["text"].splitlines()
        self.assertEqual(text[0], "저장해 둔 상태와 견주기 · 데모 호텔 · 기본 오퍼")
        for line in ("12 바뀐 칸", "12 날짜별로 바꿔 두었다가 바뀌거나 없어진 칸", "6 바뀐 칸 중 예약 있는 날의 칸", "1 새로 생긴 칸",
                     "0 없어진 칸"):
            self.assertIn(line, text)
        self.assertIn(f"성인 2 · 1박 이상 | 220.00 → 225.00 날짜별로 바꿔 둔 값 · 장부 {change}번 | "
                      f"220.00 → 225.00 날짜별로 바꿔 둔 값 · 장부 {change}번 | 330.00 그대로 | 330.00 그대로", text)
        self.assertIn("성인 2 · 1박 이상 | 373.95 그대로 | 373.95 그대로 | 484.00 그대로 | 새로 → 450.00 새로 생김", text)
        self.assertTrue(any("아무것도 바꾸지 않았습니다" in line for line in text))
        self.assertFalse(any("되돌립니다" in line for line in text), "견주기 페이지는 되돌린다고 말하지 않는다")
        self.assertTrue(any(f'"{saved}번 상태로 되돌려"' in line for line in text))

        restore = self.cli("restore", "--saved", saved, "--snapshot", now, "--record", "--sentence", f"{saved}번 상태로 되돌려",
                           "--out", self.dir / "rollback-1.json")
        self.assertEqual((restore["mode"], restore["restored"], restore["unremovable"], restore["kept"]), ("restore", 12, 1, 0))
        plan = json.loads((self.dir / "rollback-1.json").read_text(encoding="utf-8"))["rollback"]
        self.assertEqual({item["key"] for item in plan["restored"]}, {cell_item_key(key) for key in REFILLED},
                         "되돌리는 칸은 바뀐 칸 그대로")
        self.assertEqual([item["key"] for item in plan["unremovable"]], [cell_item_key(CREATED)], "새로 생긴 칸은 지울 수 없다")
        page = self.cli("render", "rollback", "--plan", self.dir / "rollback-1.json", "--text")["text"]
        self.assertIn(SEASON_SCREEN_NOTE, page, "시즌 창은 다시 채운 입력값 그대로라는 것을 되돌리기 전에 말한다")

    def test_compare_takes_only_a_saved_state_and_a_reading_of_its_whole_range(self):
        before = scene.fresh(scene.snapshot())
        saved = self.cli("save-snapshot", "--snapshot", self.write("saved.json", encode_snapshot(before)))["change_id"]
        same = self.cli("compare", "--saved", saved, "--snapshot", self.dir / "saved.json")
        self.assertEqual((same["counts"]["changed"], same["counts"]["new"], same["counts"]["same"]), (0, 0, same["counts"]["cells"]))
        text = self.cli("render", "compare", "--plan", self.write("same.json", same), "--text")["text"]
        self.assertIn("저장해 둔 때와 모든 칸이 같습니다.", text)

        part = replace(before, cells={key: value for key, value in before.cells.items() if key.room == "디럭스"},
                       pairs=frozenset(pair for pair in before.pairs if pair[0] == "디럭스"))
        refused = self.cli("compare", "--saved", saved, "--snapshot", self.write("part.json", encode_snapshot(part)), code=2)
        self.assertIn(f"read-calls --record {saved}", refused["error"])
        plan = self.cli("plan", "--snapshot", self.dir / "saved.json", "--request",
                        self.write("request.json", encode_request(scene.request())), "--record")["change_id"]
        self.assertIn("저장해 둔 상태가 아닙니다", self.cli("compare", "--saved", plan, "--snapshot", self.dir / "saved.json",
                                                         code=2)["error"])

    def test_a_cell_the_saved_state_never_had_is_new_and_cannot_be_removed_by_a_restore(self):
        before = scene.fresh(scene.snapshot())
        saved = self.cli("save-snapshot", "--snapshot", self.write("saved.json", encode_snapshot(before)))["change_id"]
        tier = CellKey("디럭스", "조식 포함", "2026-12-25", "A2", 5)   # 시즌을 다시 채우며 생긴 5박 이상 층 — 저장할 때는 없던 줄
        now = self.write("now.json", encode_snapshot(scene.with_cells(before, {tier: CellValue(D("170.00"), None, None, "open")})))
        short = self.cli("compare", "--saved", saved, "--snapshot", now, "--out", self.dir / "compare-1.json")
        self.assertEqual((short["counts"]["new"], short["counts"]["changed"]), (1, 0))
        self.assertIn("성인 2 · 5박 이상 | 새로 → 170.00 새로 생김 | — | — | —",
                      self.cli("render", "compare", "--plan", self.dir / "compare-1.json", "--text")["text"].splitlines())
        restore = self.cli("restore", "--saved", saved, "--snapshot", now, "--out", self.dir / "rollback-1.json")
        self.assertEqual((restore["restored"], restore["unremovable"]), (0, 1), "되돌려도 지울 수 없는 칸으로 댄다")

    def test_a_cell_gone_since_the_save_is_counted_and_restored(self):
        before = scene.fresh(scene.snapshot())
        saved = self.cli("save-snapshot", "--snapshot", self.write("saved.json", encode_snapshot(before)))["change_id"]
        gone = CellKey("디럭스", "룸온리", "2027-01-01", "A3", 3)
        cells = {key: value for key, value in before.cells.items() if key != gone}
        now = self.write("now.json", encode_snapshot(replace(before, cells=cells)))
        short = self.cli("compare", "--saved", saved, "--snapshot", now, "--out", self.dir / "compare-1.json")
        self.assertEqual((short["counts"]["gone"], short["counts"]["changed"], short["counts"]["edited"]), (1, 0, 0))
        text = self.cli("render", "compare", "--plan", self.dir / "compare-1.json", "--text")["text"]
        self.assertIn("297.00 없어짐", text)
        restore = self.cli("restore", "--saved", saved, "--snapshot", now, "--out", self.dir / "rollback-1.json")
        self.assertEqual((restore["restored"], restore["unremovable"]), (1, 0), "없어진 칸은 저장해 둔 값으로 다시 넣는다")


if __name__ == "__main__":
    unittest.main()
