"""한 장부 · 한 벌의 장치(C6) — 이 도우미는 다른 두 도우미의 장부 · 미리보기 판정 틀 · 적용 직전 다시 읽기 · 15분 멈춤 · check ·
verify · 되돌리기 계산 · 페이지 틀 · 조각 · 「읽은 그대로 보내고 짚은 칸만 바꾸기」를 베끼지 않고 같은 것(change_core · stayPageKit)을
쓴다. 같은 이름의 함수를 이 스킬에 다시 만들면 여기서 실패한다.

    python3 -m unittest discover -s tests
"""

import ast
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
CORE = SKILL.parent / "stay-price-change" / "scripts" / "change_core"
PAGE = SKILL / "scripts" / "page" / "stay_charge.js"
ADDON_PAGE = SKILL.parent / "stay-addon-price-change" / "scripts" / "page" / "stay_addon_price.js"


def defined(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.ClassDef))}


def imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {f"{node.module}.{alias.name}" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
            for alias in node.names}


class SharedMachineryTest(unittest.TestCase):
    def test_the_command_uses_the_shared_ledger_stale_check_rollback_chrome_pieces_and_window_step(self):
        used = set().union(*(imported(path) for path in SCRIPTS.glob("*.py")))
        for name in ("change_core.ledger.Ledger", "change_core.ledger.ValueRow", "change_core.rollback.plan_rollback",
                     "change_core.rules.RuleTable", "change_core.rules.decide", "change_core.rules.moved_far",
                     "change_core.answers.attach_bodies", "change_core.answers.step_outcome", "change_core.chrome.page",
                     "change_core.chrome.result_banner", "change_core.chrome.kept_table", "change_core.window.with_values",
                     "change_core.window.moved_since"):
            self.assertIn(name, used, name)

    def test_no_shared_function_is_copied_into_this_skill(self):
        shared = set().union(*(defined(path) for path in CORE.glob("*.py")))
        mine = set().union(*(defined(path) for path in SCRIPTS.glob("*.py")))
        # 이름이 같아도 되는 것: 공유 함수를 이 종류의 키 · 접두로 부르는 명령의 얇은 덧뿐(아래에서 그 덧이 공유 함수를 부르는지 본다)
        wrappers = {"moved_since": "window_moved(", "fresh_record": "files.fresh_record(", "load_results": "files.load_results(",
                    "recorded_snapshot": "ledger.reading(", "listed": "files.listed("}
        self.assertEqual((shared & mine) - set(wrappers) - {"__post_init__"}, set())
        command = (SCRIPTS / "charge_change.py").read_text(encoding="utf-8")
        for name, call in wrappers.items():
            self.assertIn(call, command, f"{name} 는 공유 함수를 부른다")

    def test_the_page_modules_hold_no_copy_of_the_kit(self):
        for path in (PAGE, ADDON_PAGE):
            code = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                             if not re.match(r"^\s*(//|/\*|\*)", line))
            for copy in ("function sent(", "function differs(", "function pairs(", "function fill(", "function saveOnce(",
                         "function Wall(", "function run(", "function scrub(", "function take(", "saveSigns",
                         "addEventListener"):
                self.assertNotIn(copy, code, f"{path.name}: {copy}")
            for use in ("K.run(", "K.press(", "K.settle("):
                self.assertIn(use, code, f"{path.name}: {use}")
        charge = PAGE.read_text(encoding="utf-8")
        self.assertIn("K.fill(", charge)
        self.assertIn("K.saveOnce(", charge)

    def test_one_ledger_file_and_schema_for_all_three_helpers(self):
        with tempfile.TemporaryDirectory() as folder:
            os.environ["STAY_PRICE_LEDGER_DIR"] = folder
            try:
                from charge_change import open_ledger
                from change_core.ledger import DB_NAME, KIND_NAMES, SCHEMA_VERSION, Ledger
                ledger = open_ledger()
                self.assertEqual((ledger.path, ledger.kind), (Path(folder) / DB_NAME, "charge"))
                self.assertEqual(Ledger().path, ledger.path)
                self.assertEqual(KIND_NAMES["charge"], "부과금 도우미")
                self.assertEqual(SCHEMA_VERSION, 4, "항목 종류는 표의 모양을 바꾸지 않는다 — 4 는 세 도우미가 같이 쓰는 장부에 부를 값을 낸 기록(issues)을 더한 판")
            finally:
                del os.environ["STAY_PRICE_LEDGER_DIR"]


if __name__ == "__main__":
    unittest.main()
