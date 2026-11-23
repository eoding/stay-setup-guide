"""K3 — 객실 이름은 한 번만 배운다. 요금표의 'Deluxe' 를 맞추려고 오퍼의 모든 객실을 다시 읽었다(가격 읽기 4번 · 조각 20개 · 3분
반) — 몇 분 전 같은 기록 폴더의 읽기가 이미 그 객실의 `rooms: [{room, drawer}]` 를 갖고 있었는데. `rooms` 는 기록 폴더의 읽기
가운데 같은 호텔 · 오퍼를 읽은 것에서 이름을 모으고, 어느 읽기도 읽지 않은 객실만 읽을 범위로 낸다.

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
from price_model import encode_snapshot  # noqa: E402


class RoomNamesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.records = Path(self.tmp.name) / "기록"
        self.env = scene.env(self.records)
        base = scene.snapshot()
        self.hotel = {"id": base.hotel_id, "name": base.hotel}
        self.offer = base.offer
        self.look = Path(self.tmp.name) / "look.json"
        self.look.write_text(json.dumps({"login": False, "hotel": self.hotel, "offer": self.offer, "offers": [self.offer],
                                         "pairs": [{"room": "디럭스", "rate_plan": "조식 포함"}, {"room": "디럭스", "rate_plan": "룸온리"},
                                                   {"room": "스위트", "rate_plan": "룸온리"}, {"room": "패밀리", "rate_plan": "조식 포함"}]},
                                        ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def reading(self, folder: str, read_at: str, names: dict, rooms=("디럭스", "스위트"), **over):
        """기록 폴더의 앞선 읽기 하나 — `작업/<folder>/snapshot.json`(read --out 이 쓰는 자리)."""
        base = scene.snapshot(read_at=read_at)
        pairs = {pair for pair in base.pairs if pair[0] in rooms} | ({("패밀리", "조식 포함")} if "패밀리" in rooms else set())
        snapshot = replace(base, room_names=names, pairs=frozenset(pairs),
                           cells={key: value for key, value in base.cells.items() if key.room in rooms},
                           reserved=frozenset(item for item in base.reserved if item[0] in rooms), **over)
        path = self.records / "작업" / folder / "snapshot.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(encode_snapshot(snapshot), ensure_ascii=False), encoding="utf-8")

    def cli(self, *args, code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code == 0 else json.loads(done.stderr)

    def test_names_an_earlier_reading_holds_are_not_read_again_and_only_an_unread_room_is_asked_for(self):
        self.reading("2026-11-21 100000/읽기-1", "2026-11-21T10:00:00+09:00", {"디럭스": "Deluxe"})
        self.reading("2026-11-21 100500/읽기-1", "2026-11-21T10:05:00+09:00", {"디럭스": "Deluxe Room"}, rooms=("디럭스",))
        self.reading("2026-11-21 101000/읽기-1", "2026-11-21T10:10:00+09:00", {"패밀리": "남의 객실"}, rooms=("패밀리",),
                     hotel_id="9")                                         # 다른 호텔의 읽기는 빌리지 않는다
        out = Path(self.tmp.name) / "rooms-1.json"
        self.assertIn("패밀리", self.cli("rooms", "--look", self.look, "--out", out, code=2)["error"], "읽을 날이 없으면 묻는다")
        short = self.cli("rooms", "--look", self.look, "--date", "2026-12-25", "--out", out)
        self.assertEqual(short["rooms"], [{"room": "디럭스", "drawer": "Deluxe Room"}, {"room": "스위트", "drawer": None},
                                          {"room": "패밀리", "drawer": None}], "새 읽기가 앞서고, 읽었지만 이름이 없는 객실은 null")
        self.assertEqual((short["unread"], short["read"]), (["패밀리"], True), "다시 읽을 것은 어느 읽기도 읽지 않은 객실뿐")
        calls = self.cli("read-calls", "--request", out, "--out", Path(self.tmp.name) / "calls.json")
        self.assertEqual([(pair["room"], pair["ratePlan"], pair["from"], pair["to"]) for pair in calls["pairs"]],
                         [("패밀리", "조식 포함", "2026-12-25", "2026-12-25")], "낸 파일이 그 객실 하루만 읽는 범위다")

        self.reading("2026-11-21 102000/읽기-1", "2026-11-21T10:20:00+09:00", {"패밀리": "Family Suite"}, rooms=("패밀리",))
        again = self.cli("rooms", "--look", self.look, "--out", Path(self.tmp.name) / "rooms-2.json")
        self.assertEqual((again["unread"], again["read"], again["rooms"][2]), ([], False, {"room": "패밀리", "drawer": "Family Suite"}))
        data = json.loads((Path(self.tmp.name) / "rooms-2.json").read_text(encoding="utf-8"))
        self.assertEqual(data["kind"], "room_names", "읽을 것이 없으면 읽을 범위가 아니다")
        self.cli("rooms", "--look", self.look, "--out", Path(self.tmp.name) / "rooms-2.json", code=2)   # 덮어쓰지 않는다

    def test_the_sheet_reference_settles_an_exact_match_without_a_question(self):
        sheet = (HERE.parent / "references" / "sheet.md").read_text(encoding="utf-8")
        pairing = sheet[sheet.index("**객실 짝.**"):].split("\n", 1)[0]
        for said in ("rooms --look", "글자 그대로 같으면 그 객실이다 — 묻지 않는다", "두 객실이 똑같이 맞으면", "다시 읽지 않는다"):
            self.assertIn(said, pairing)


if __name__ == "__main__":
    unittest.main()
