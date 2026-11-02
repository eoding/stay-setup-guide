"""ERP 실제 렌더 픽스처(`tests/fixtures/erp/`)가 낡지 않았는가.

    python3 -m unittest test_erp_fixtures       (tests/ 에서)

사본은 `scripts/sync_erp_fixtures.py` 가 basecamp `stay/tests/fixtures/html/` 에서 옮긴다. ERP 화면이 바뀌어 원본이 다시
그려졌는데 사본을 안 옮기면 러너 시험이 **옛 화면**을 보고 통과한다 — 그래서 원본과 바이트로 견준다.
basecamp 를 못 찾으면(`BASECAMP_PATH` 도 없고 작업 공간의 옆 폴더도 없다) 대조만 건너뛴다.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import sync_erp_fixtures as sync  # noqa: E402

COPY = HERE / "fixtures" / "erp"


def basecamp_path():
    raw = os.environ.get("BASECAMP_PATH")
    candidates = [Path(raw).expanduser()] if raw else []
    candidates.append(HERE.parents[3] / "basecamp")  # 작업 공간: <ws>/stay-setup-guide 옆의 <ws>/basecamp
    for path in candidates:
        if (sync.source_dir(path) / sync.INDEX).is_file():
            return path
    return None


class TestErpFixtures(unittest.TestCase):
    def test_copy_matches_its_own_index(self):
        names = sync.listed(COPY)
        present = sorted(p.name for p in COPY.iterdir() if p.is_file())
        self.assertEqual(sorted(names), present)
        with open(COPY / sync.INDEX, encoding="utf-8") as handle:
            files = json.load(handle)["files"]
        self.assertTrue(all(item.get("screen") for item in files))

    def test_copy_is_not_stale(self):
        basecamp = basecamp_path()
        if basecamp is None:
            self.skipTest("basecamp 를 못 찾았습니다 — BASECAMP_PATH 를 주면 원본과 견줍니다")
        diff = sync.differences(sync.source_dir(basecamp), COPY)
        self.assertEqual(diff, [], "사본이 낡았습니다 — `python3 scripts/sync_erp_fixtures.py --basecamp <경로>` 로 옮기세요")


if __name__ == "__main__":
    unittest.main()
