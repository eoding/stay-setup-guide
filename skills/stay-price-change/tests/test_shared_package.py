"""공유 패키지(change_core) — 부과금·프로모션·부가옵션 도우미가 같이 쓸 부분은 가격 칸 코드를 모른다(R2).

    python3 -m unittest discover -s tests
"""

import ast
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
CORE = SCRIPTS / "change_core"
CELL_MODULES = {"price_model", "price_plan", "price_pages", "price_change", "erp_read"}
SHARED = {"ledger", "rules", "items", "rollback", "chrome", "money"}


class SharedPackageTest(unittest.TestCase):
    def test_the_package_holds_ledger_rules_stale_check_rollback_and_page_chrome(self):
        self.assertEqual({path.stem for path in CORE.glob("*.py")} - {"__init__"}, SHARED)

    def test_no_module_of_the_package_imports_cell_code(self):
        for path in CORE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
            names |= {node.module.split(".")[0] for node in ast.walk(tree)
                      if isinstance(node, ast.ImportFrom) and node.module and node.level == 0}
            self.assertEqual(names & CELL_MODULES, set(), path.name)

    def test_a_sibling_skill_can_import_it_by_path_without_loading_cell_code(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                "import change_core.ledger, change_core.rules, change_core.items, change_core.rollback, change_core.chrome; "
                "print(sorted(m for m in sys.modules if m.split('.')[0] in %r))" % sorted(CELL_MODULES))
        done = subprocess.run([sys.executable, "-c", code, str(SCRIPTS)], capture_output=True, text=True, cwd="/")
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "[]"), done.stderr)


if __name__ == "__main__":
    unittest.main()
