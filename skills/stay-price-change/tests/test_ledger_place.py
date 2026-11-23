"""검토 10 — 장부가 있던 기록 폴더에서 장부 파일이 없어지면 빈 장부를 새로 만들지 않는다.

장부는 문서 폴더(Documents) 아래에 있다. iCloud 「데스크탑 및 문서」처럼 문서 폴더를 동기화하면 파일이 클라우드로만 옮겨지거나(그
자리에는 `.가격장부.sqlite3.icloud` 같은 자리표만 남는다) 사본으로 갈릴 수 있다. 그때 장부를 열던 명령이 빈 장부를 만들면 되돌리기가
"장부에 그 번호가 없습니다"가 된다. 기록 폴더에 작업 폴더나 페이지가 있으면 장부가 있던 자리다 — 명령은 그렇다고 말하고 멈춘다.
처음 쓰는 기록 폴더는 `work` 가 작업 폴더와 장부를 같이 만든다.

    python3 -m unittest discover -s tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
from change_core.ledger import DB_NAME, LEDGER_ENV, Ledger, LedgerError  # noqa: E402
from price_model import encode_request, encode_snapshot  # noqa: E402


class LedgerPlaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.records = Path(self.tmp.name) / "기록"
        self.env = scene.env(self.records)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, code=0):
        done = subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def write(self, name, data) -> Path:
        path = Path(self.tmp.name) / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_work_makes_the_ledger_with_the_first_work_folder_and_a_missing_ledger_is_never_made_again(self):
        work = Path(self.cli("work")["work"])
        ledger = self.records / DB_NAME
        self.assertTrue(work.is_dir() and ledger.is_file(), "처음 쓰는 기록 폴더 — work 가 작업 폴더와 장부를 같이 만든다")
        snapshot = self.write("snapshot.json", encode_snapshot(scene.snapshot()))
        request = self.write("request.json", encode_request(scene.request()))
        change = self.cli("plan", "--snapshot", snapshot, "--request", request, "--record")["change_id"]

        ledger.rename(self.records / f".{DB_NAME}.icloud")   # 클라우드로만 옮겨졌다 — 자리표만 남았다
        for args in (("list", "--all"), ("plan", "--snapshot", snapshot, "--request", request, "--record"),
                     ("rollback", "--change", change, "--snapshot", snapshot), ("work",)):
            said = self.cli(*args, code=2)["error"]
            self.assertIn("장부가 있던 자리라 빈 장부를 새로 만들지 않았습니다", said, args[0])
            self.assertIn(LEDGER_ENV, said, "동기화하지 않는 폴더로 옮기는 길을 말한다")
            self.assertFalse(ledger.exists(), f"{args[0]} 이 빈 장부를 만들지 않았다")
        self.assertEqual(len(list((self.records / "작업").iterdir())), 1, "work 도 새 작업 폴더를 만들지 않았다")

        (self.records / f".{DB_NAME}.icloud").rename(ledger)   # 내려받아 되찾았다
        self.assertEqual([entry["id"] for entry in self.cli("list", "--all")["changes"]], [change], "같은 장부가 그대로 열린다")

    def test_pages_alone_also_mark_a_folder_where_a_ledger_was(self):
        folder = Path(self.tmp.name) / "페이지만"
        folder.mkdir()
        (folder / "2026-11-21 10시00분 · 데모 호텔 · 미리보기.html").write_text("<html></html>", encoding="utf-8")
        with self.assertRaisesRegex(LedgerError, "장부가 있던 자리라"):
            Ledger(folder / DB_NAME)
        self.assertFalse((folder / DB_NAME).exists())
        empty = Path(self.tmp.name) / "처음"
        empty.mkdir()
        Ledger(empty / DB_NAME)
        self.assertTrue((empty / DB_NAME).is_file(), "작업 폴더도 페이지도 없는 폴더에서는 처음 쓰는 장부를 만든다")


if __name__ == "__main__":
    unittest.main()
