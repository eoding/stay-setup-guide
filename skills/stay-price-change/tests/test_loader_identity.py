"""W1 — 올리개가 아는 설치 파일 넷(러너의 도우미 · 부트, 가격 도우미, 부가옵션 가격 도우미)의 알아볼 값은 늘 디스크의 네 파일
것이다. 네 파일 가운데 하나를 고치고 값을 다시 적지 않으면 여기서 실패하고, 고치는 명령을 말한다. 올리개가 그 값으로 예전 판을
거절하는 것은 tests/test_page_loader.mjs(와 부가옵션 스킬의 tests/test_page_loader.mjs)가 본다.

    python3 -m unittest discover -s tests
"""

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from loader_identity import FILES, LOADER, identity, installed, rewrite, written  # noqa: E402

AGAIN = "python3 scripts/loader_identity.py"


class LoaderIdentityTest(unittest.TestCase):
    def test_the_loader_knows_the_four_files_on_disk(self):
        self.assertEqual(set(FILES), {"stay_helper.js", "stay_boot.js", "stay_price.js", "stay_addon_price.js"})
        self.assertTrue(all(path.is_file() for path in FILES.values()), FILES)
        self.assertEqual(written(), installed(),
                         f"stay_price_loader.js 의 INSTALLED 가 디스크의 네 파일과 다릅니다 — 네 파일 가운데 하나를 고쳤으면 "
                         f"스킬 폴더에서 `{AGAIN}` 로 다시 적고 같이 커밋합니다")

    def test_the_one_command_writes_the_values_back_and_changes_nothing_else(self):
        with tempfile.TemporaryDirectory() as folder:
            stale = Path(folder) / LOADER.name
            text = LOADER.read_text(encoding="utf-8")
            price = installed()["stay_price.js"]
            stale.write_text(text.replace(f"bytes: {price['bytes']}, crc32: '{price['crc32']}'",
                                          f"bytes: {price['bytes'] - 1}, crc32: '{price['crc32']}'", 1), encoding="utf-8")
            self.assertNotEqual(written(stale), installed())
            self.assertEqual(rewrite(stale), ["stay_price.js"])
            self.assertEqual(stale.read_text(encoding="utf-8"), text, "값 한 줄만 고친다")
            self.assertEqual(rewrite(stale), [], "다시 부르면 아무것도 바꾸지 않는다")

    def test_a_checkout_with_windows_line_ends_has_the_same_values(self):
        data = FILES["stay_price.js"].read_bytes()
        self.assertNotIn(b"\r\n", data)
        self.assertEqual(identity(data.replace(b"\n", b"\r\n")), identity(data))


if __name__ == "__main__":
    unittest.main()
