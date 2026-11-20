"""옮겨 적다 틀린 쪽 하나가 호텔을 막지 않는다 — 앞선 읽기 폴더의 어긋난 것은 말없이 건너뛴다(R1).

    python3 -m unittest discover -s tests

장부와 기록 폴더는 `STAY_PRICE_LEDGER_DIR` 로 임시 폴더에 둔다. 값과 이름은 모두 지어낸 것이다.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
from browser_replies import reply  # noqa: E402

ERP = HERE / "fixtures" / "erp"
PRICE = (ERP / "price-runs-closed-absent-list.html").read_text(encoding="utf-8")
REJECTED = (ERP / "adjust-rejected.html").read_text(encoding="utf-8").replace("<td>스위트</td>", "<td>디럭스</td>")
ASKED = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-24",
         "to": "2026-12-31", "weekdays": list("월화수목금토일")}
PROBE = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "rooms": ["디럭스"], "ratePlans": ["조식 포함"], "from": "2026-12-24",
         "to": "2026-12-31", "weekdays": list("월화수목금토일"), "occupancy": "*", "nights": "all"}


def folder_state(folder: Path) -> dict:
    """폴더 안 파일마다 (바이트, 고친 시각) — 명령이 앞선 폴더를 건드리지 않았는지 견준다."""
    return {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in sorted(folder.iterdir())}


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.records = self.dir / "기록"
        self.env = {**os.environ, "STAY_PRICE_LEDGER_DIR": str(self.records)}

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def reading(self, job: str, name: str = "읽기-1") -> Path:
        folder = self.records / "작업" / job / name
        folder.mkdir(parents=True)
        (folder / "calls.json").write_text(json.dumps({"pairs": [ASKED], "reserved": [PROBE]}, ensure_ascii=False), encoding="utf-8")
        return folder

    @staticmethod
    def save(folder: Path, name: str, item) -> Path:
        path = folder / name
        if isinstance(item, bytes):
            path.write_bytes(item)
        else:
            path.write_text(item if isinstance(item, str) else json.dumps(item, ensure_ascii=False), encoding="utf-8")
        return path


class EarlierFolderTest(Cli):
    """R1 — 앞선 읽기 폴더에서는 다 받아 모든 검사를 지난 화면만 빌린다. 그 밖의 것(스스로 말하는 길이와 다른 쪽 · 빠진 쪽 ·
    검사값이 다른 머리 · JSON 이 아닌 파일 · 글자로 읽히지 않는 파일)은 말없이 건너뛰고, 이번 읽기는 그 폴더가 없는 것처럼
    `refetch` 로 받을 것을 댄다."""

    def test_r1_bad_pieces_in_an_earlier_folder_are_skipped_and_the_new_reading_asks_as_if_the_folder_were_not_there(self):
        old = self.reading("A")
        pair = reply("readPair", ASKED, {"fragment": PRICE}, pieces=4, body_id="p1")
        resv = reply("readReserved", PROBE, {"fragment": REJECTED}, pieces=3, body_id="r1")
        self.save(old, "pair-1.json", pair[0])
        self.save(old, "resv-1.json", resv[0])
        # 가격 조각: 둘째 쪽이 두 글자 모자란다(시운전) — 스스로 말하는 길이와 다르다. 셋째 쪽은 빠졌다
        short = dict(pair[2], text=pair[2]["text"][:-2])
        for index, item in ((1, pair[1]), (2, short), (4, pair[4])):
            self.save(old, f"take-p1-{item['at']}.json", item)
        # 예약 조각: 쪽은 다 있는데 한 쪽이 글자 수는 같고 글자가 다르다(이은 글자의 검사값이 머리와 다르다) · JSON 이 아닌 파일 ·
        # 글자로 읽히지 않는 파일 · 칸이 빠진 머리 · 검사값이 틀린 머리
        typo = dict(resv[2], text=resv[2]["text"].replace("<", ">", 1))
        self.assertEqual(len(typo["text"]), len(resv[2]["text"]))
        for item in (resv[1], typo, *resv[3:]):
            self.save(old, f"take-r1-{item['at']}.json", item)
        self.save(old, "resv-2.json", dict(resv[0], ask="00000000", body=dict(resv[0]["body"], crc32="00000000", id="r2")))
        self.save(old, "take-r1-x.json", '{"op": "take", "ok": true, "id": "r1", "at": 0, "text": "<div')
        self.save(old, "take-r1-y.json", b"\xff\xfe\x00 not text")
        self.save(old, "pair-2.json", {"op": "readPair", "ok": True, "ask": "00000000", "body": {"id": "p1"}})
        before = folder_state(old)

        new = self.reading("B")
        again_pair = reply("readPair", ASKED, {"fragment": PRICE}, pieces=4, body_id="p2")
        again_resv = reply("readReserved", PROBE, {"fragment": REJECTED}, pieces=3, body_id="r3")
        self.save(new, "pair-1.json", again_pair[0])
        self.save(new, "resv-1.json", again_resv[0])
        calls = new / "calls.json"
        asked = self.run_cli("reserved", "--calls", calls, "--answers", new, code=2)
        self.assertEqual([(item["id"], item["at"]) for item in asked["refetch"]], [("r3", 0)],
                         "예약 조각은 앞선 폴더에 쪽이 다 있어도 머리가 어긋난 곳의 것이라 이번 답의 쪽을 받는다")
        read = self.run_cli("read", "--calls", calls, "--answers", new, code=2)
        self.assertEqual(sorted((item["id"], item["at"]) for item in read["refetch"]), [("p2", 0), ("r3", 0)],
                         "앞선 폴더가 없는 것처럼 — 어긋난 쪽은 오류가 아니다")
        for item in again_pair[1:] + again_resv[1:]:
            self.save(new, f"take-{item['id']}-{item['at']}.json", item)
        self.assertTrue(self.run_cli("reserved", "--calls", calls, "--answers", new)["done"])
        snapshot = self.run_cli("read", "--calls", calls, "--answers", new)
        self.assertEqual((snapshot["offer"], len(snapshot["cells"])), ("샘플 오퍼", 16))
        self.assertEqual(folder_state(old), before, "앞선 폴더의 파일은 그대로다")

    def test_r1_a_whole_checked_screen_in_an_earlier_folder_is_still_borrowed_next_to_broken_ones(self):
        old = self.reading("A")
        pair = reply("readPair", ASKED, {"fragment": PRICE}, pieces=4, body_id="p1")
        for item in pair[1:]:
            self.save(old, f"take-p1-{item['at']}.json", item)
        self.save(old, "take-p1-broken.json", dict(pair[2], text=pair[2]["text"][:-2]))
        new = self.reading("B")
        self.save(new, "pair-1.json", reply("readPair", ASKED, {"fragment": PRICE}, pieces=4, body_id="p2")[0])
        resv = reply("readReserved", PROBE, {"fragment": REJECTED}, pieces=3, body_id="r3")
        for item in resv:
            self.save(new, f"resv-1-{item.get('at', 'answer')}.json", item)
        snapshot = self.run_cli("read", "--calls", new / "calls.json", "--answers", new)
        self.assertEqual(len(snapshot["cells"]), 16, "같은 글자의 다 받은 화면은 어긋난 쪽 곁에 있어도 빌린다")


if __name__ == "__main__":
    unittest.main()
