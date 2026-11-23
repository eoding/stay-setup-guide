"""F1 — 성인 · 아동 수만 적은 인원 조합("성인 2 + 아동 1" → `A2C1`)은 명령이 읽은 줄에 맞춘다. 줄이 하나면 그 줄, 아동 밴드가 여럿이면
고를 줄을 ERP 의 이름으로 대고 아무것도 적지 않는다. 요금표 · 목표 값 표 · 바꾸기 요청의 `occupancies` 가 모두 그렇다.

    python3 -m unittest discover -s tests
"""

import json
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
import sheet_scene as S  # noqa: E402
from price_model import CellKey, Target, TargetTable, encode_snapshot, guest_counts, matching_rows  # noqa: E402
from price_plan import ChooseRows, plan_change, plan_targets  # noqa: E402

TEEN = "A2C1_TEEN"
LABELS = {"A2C1_CHD": "A2C1_CHD · 소아 1", TEEN: "A2C1_TEEN · 청소년 1"}


def bandless_sheet() -> dict:
    """시험 요금표 그대로이되 아동 줄을 요금표의 말대로 — "성인 2 + 아동 1" 은 `A2C1`(밴드 코드를 모른다)."""
    data = S.sheet_data()
    for line in data["lines"]:
        for row in line["rows"]:
            if row["occupancy"] == "A2C1_CHD":
                row["occupancy"] = "A2C1"
    return data


def two_bands(reading):
    """같은 객실 · 요금제에 아동 밴드가 둘 — `A2C1_CHD` 마다 `A2C1_TEEN` 줄(값은 +10)."""
    cells = dict(reading.cells)
    for key, value in reading.cells.items():
        if key.occupancy == "A2C1_CHD":
            cells[replace(key, occupancy=TEEN)] = value if value.sell is None else replace(value, sell=value.sell + 10)
    return replace(reading, cells=cells, row_labels=LABELS)


class KeyTest(unittest.TestCase):
    def test_counts_and_rows_by_adults_and_children(self):
        self.assertEqual([guest_counts(key) for key in ("A2", "A2C1", "A2C1_CHD", "A2C1_CHD_C1_TEEN", "", "3")],
                         [(2, 0), (2, 1), (2, 1), (2, 2), None, None])
        rows = ("A2", "A3", "A2C1_CHD", TEEN, "A2C2_CHD")
        self.assertEqual(matching_rows("A2C1", rows), ("A2C1_CHD", TEEN))
        self.assertEqual(matching_rows("A2C1", ("A2", "A2C1_CHD")), ("A2C1_CHD",))
        self.assertEqual(matching_rows("A2C1_CHD", rows), ("A2C1_CHD",), "밴드 코드를 적은 키는 그 키만")
        self.assertEqual(matching_rows("A2C1_KID", rows), (), "없는 밴드는 다른 밴드로 옮기지 않는다")
        self.assertEqual(matching_rows("A3", ("A2",)), ())


class SheetCommandTest(unittest.TestCase):
    """시운전의 모양 — 요금표의 "성인 2 + 아동 1" 을 `A2C1` 로 적어도 계산은 한 번, 장부도 한 번, 「읽은 값에 없는 인원 조합」은 0."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = scene.env(str(self.dir / "기록"))

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

    def plan(self, reading, code=0):
        self.run_cli("sheet", "--sheet", self.write("sheet-1.json", bandless_sheet()), "--look", self.write("look.json", S.look_data()),
                     "--out", self.dir / "sheet-check-1.json")
        return self.run_cli("plan", "--snapshot", self.write("snapshot.json", encode_snapshot(reading)),
                            "--request", self.dir / "sheet-check-1.json", "--record", "--out", self.dir / "plan-1.json", code=code)

    def test_one_child_band_is_the_row_meant_and_nothing_is_unseen(self):
        planned = self.plan(S.reading(read_at=scene.NOW_TEXT))
        self.assertEqual(planned["coverage"]["unseen"], 0)
        self.assertEqual(planned["coverage"]["untouched"], 13, "요금표에 없는 칸은 스위트 성인 1 줄뿐 — 아동 줄은 같은 칸이다")
        self.assertEqual(len(self.run_cli("list", "--all")["changes"]), 1, "장부에는 한 번만 적힌다")
        targets = json.loads((self.dir / "plan-1.json").read_text(encoding="utf-8"))["plan"]["request"]["targets"]
        self.assertEqual({t["key"]["occupancy"] for t in targets}, {"A2", "A3", "A2C1_CHD"})
        changed = {(c["key"]["room"], c["key"]["date"], c["key"]["occupancy"]): c["after"]["sell"]
                   for c in json.loads((self.dir / "plan-1.json").read_text(encoding="utf-8"))["plan"]["changes"]}
        self.assertEqual(changed[("디럭스", "2027-01-15", "A2C1_CHD")], "330.00")

    def test_two_child_bands_are_listed_by_their_erp_names_and_nothing_is_recorded(self):
        refused = self.plan(two_bands(S.reading(read_at=scene.NOW_TEXT)), code=2)
        self.assertIn("A2C1_CHD · 소아 1 / A2C1_TEEN · 청소년 1", refused["error"])
        self.assertEqual({(item["room"], item["occupancy"]) for item in refused["choose"]}, {("디럭스", "A2C1"), ("스위트", "A2C1")})
        self.assertEqual(refused["choose"][0]["choices"], [{"occupancy": "A2C1_CHD", "label": "A2C1_CHD · 소아 1"},
                                                           {"occupancy": TEEN, "label": "A2C1_TEEN · 청소년 1"}])
        self.assertEqual(self.run_cli("list", "--all")["changes"], [], "고르기 전에는 장부에 아무것도 적지 않는다")
        self.assertFalse((self.dir / "plan-1.json").exists())


class RequestTest(unittest.TestCase):
    """목표 값 표 · 바꾸기 요청의 `occupancies` 도 같은 규칙이다."""

    def test_a_target_naming_adults_and_children_is_the_only_such_row(self):
        key = CellKey("디럭스", "조식 포함", "2026-12-25", "A2C1", 1)
        table = TargetTable(scene.HOTEL, scene.OFFER, (Target(key, (("sell", D("260")),)),), hotel_id=scene.HOTEL_ID)
        plan = plan_targets(scene.snapshot(), table)
        self.assertEqual([(c.key.occupancy, c.after.sell) for c in plan.changes], [("A2C1_CHD", D("260.00"))])
        self.assertEqual(plan.request.targets[0].key.occupancy, "A2C1_CHD", "미리보기의 요청은 맞춘 줄이다")
        with self.assertRaises(ChooseRows) as caught:
            plan_targets(two_bands(scene.snapshot()), table)
        self.assertEqual([choice["occupancy"] for choice in caught.exception.choose[0]["choices"]], ["A2C1_CHD", TEEN])

    def test_a_change_narrowed_to_adults_and_children_moves_that_row(self):
        plan = plan_change(scene.snapshot(), scene.request(occupancies=("A2C1",)))
        self.assertEqual({c.key.occupancy for c in plan.changes}, {"A2C1_CHD"})
        self.assertEqual(plan.request.occupancies, ("A2C1_CHD",))
        with self.assertRaises(ChooseRows):
            plan_change(two_bands(scene.snapshot()), scene.request(occupancies=("A2C1",)))


if __name__ == "__main__":
    unittest.main()
