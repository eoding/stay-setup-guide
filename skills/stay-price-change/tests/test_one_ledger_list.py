"""P1 — 「장부 보여줘」는 어느 도우미에 물어도 그 호텔의 장부 전부다.

읽기만 한 시운전에서 부가옵션 가격 도우미의 목록은 비어 있었는데, 같은 호텔에 몇 분 전의 가격 캘린더 기록이 있었다. 세 도우미가 한
장부 파일을 쓰므로 「장부에 아무것도 없습니다」는 틀린 말이다. 이제 세 도우미의 `list` 는 탭의 호텔의 기록을 종류와 상관없이 새것부터
싣고, 줄마다 그 기록을 쓴 도우미가 만든 범위 한 줄의 머리가 종류를 쉬운 말로 댄다(객실 가격 · 부가옵션 가격 · 부과금). 다른 호텔의
기록은 싣지 않는다(`--all` 일 때만).

세 기록은 저마다 그 도우미의 명령과 시험 장면(작은 ERP)으로 만든다 — 다른 두 도우미의 장면은 그 파일 자리로 올린다.

    python3 -m unittest discover -s tests
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import scene  # noqa: E402
from price_model import encode_request, encode_snapshot  # noqa: E402

PRICE = SKILLS / "stay-price-change" / "scripts" / "price_change.py"
ADDON = SKILLS / "stay-addon-price-change" / "scripts" / "addon_change.py"
CHARGE = SKILLS / "stay-charge-change" / "scripts" / "charge_change.py"
WORDS = ("부과금", "부가옵션 가격", "객실 가격")   # 새것부터 — 부과금 · 부가옵션 · 객실 가격의 차례로 적는다


def sibling_scene(skill: str, name: str):
    """다른 도우미의 시험 장면 — 그 파일 자리로 올린다(그 시험 폴더를 sys.path 에 넣으면 이름이 같은 시험 파일이 섞인다)."""
    spec = importlib.util.spec_from_file_location(name, SKILLS / skill / "tests" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OneLedgerListTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = scene.env(str(Path(self.tmp.name) / "기록"))
        self.dir = Path(self.tmp.name) / "기록" / "작업" / "시험"   # 기록 폴더 안 — 명령이 없는 읽기 폴더를 만든다
        self.cli(PRICE, "work")   # 일의 첫 명령(SKILL.md 「준비」 3) — 작업 폴더보다 장부가 먼저다

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, script: Path, *args):
        done = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, 0, f"{script.name} {args[0]}: {done.stderr or done.stdout}")
        return json.loads(done.stdout)

    def file(self, name: str, data) -> Path:
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def price_change(self) -> int:
        snapshot, request = self.file("p/snapshot.json", encode_snapshot(scene.snapshot())), self.file(
            "p/request.json", encode_request(scene.request()))
        return self.cli(PRICE, "plan", "--snapshot", snapshot, "--request", request, "--record", "--out", self.dir / "p" / "plan-1.json")[
            "change_id"]

    def read_then_plan(self, script: Path, folder: str, request: Path, calls_key: str, prefix: str, answer) -> int:
        """read-calls → 부를 값마다 작은 ERP 의 답 → read → plan --record. 장부 번호를 돌려준다."""
        reading = self.dir / folder / "읽기-1"
        self.cli(script, "read-calls", "--request", request, "--out", reading / "calls.json")
        calls = json.loads((reading / "calls.json").read_text(encoding="utf-8"))[calls_key]
        for index, call in enumerate(calls, 1):
            self.file(f"{folder}/읽기-1/{prefix}-{index}.json", answer(call))   # 작은 답과 조각(take) 답들의 목록 하나
        self.cli(script, "read", "--calls", reading / "calls.json", "--answers", reading, "--out", reading / "snapshot.json")
        return self.cli(script, "plan", "--snapshot", reading / "snapshot.json", "--request", request, "--record",
                        "--out", self.dir / folder / "plan-1.json")["change_id"]

    def addon_change(self) -> int:
        erp = sibling_scene("stay-addon-price-change", "addon_scene").Erp()
        request = self.file("a/request.json", dict(kind="addon_change", hotel=scene.HOTEL_REF, lines=[{"addon": "201", "line": "301"}],
                                                   field="sell", sentence="조식 10% 올려줘", percent="10"))
        return self.read_then_plan(ADDON, "a", request, "lines", "line", erp.read_line)

    def charge_change(self) -> int:
        erp = sibling_scene("stay-charge-change", "charge_scene").Erp()
        request = self.file("c/request.json", dict(kind="charge_change", hotel=scene.HOTEL_REF, sentence="레이트 체크아웃 60% 로",
                                                    amounts=[{"offer": "601", "charge": "701", "time": "14:01-18:00", "field": "pct"}],
                                                    value="60"))
        return self.read_then_plan(CHARGE, "c", request, "charges", "charge", erp.read_charge)

    def other_hotel_record(self) -> int:
        other = replace(scene.snapshot(), hotel="다른 데모 호텔", hotel_id="9")
        return self.cli(PRICE, "save-snapshot", "--snapshot", self.file("o/snapshot.json", encode_snapshot(other)))["change_id"]

    def test_every_helper_lists_the_same_three_lines_for_the_hotel_and_none_of_another_hotel(self):
        price, addon, charge = self.price_change(), self.addon_change(), self.charge_change()
        other = self.other_hotel_record()
        look = self.file("look.json", {"hotel": scene.HOTEL_REF})
        answers = {script.name: self.cli(script, "list", "--look", look) for script in (PRICE, ADDON, CHARGE)}
        lines = {name: [entry["line"] for entry in answer["changes"]] for name, answer in answers.items()}
        self.assertEqual(lines[ADDON.name], lines[PRICE.name], "부가옵션 가격 도우미의 목록 = 가격 캘린더 도우미의 목록")
        self.assertEqual(lines[CHARGE.name], lines[PRICE.name], "부과금 도우미의 목록 = 가격 캘린더 도우미의 목록")
        for name, answer in answers.items():
            self.assertEqual([entry["id"] for entry in answer["changes"]], [charge, addon, price], f"{name}: 새것부터 셋")
            self.assertEqual(answer["others"], 1, f"{name}: 다른 호텔의 기록은 싣지 않고 수만")
            self.assertNotIn(other, [entry["id"] for entry in answer["changes"]])
            self.assertEqual([entry["helper"] for entry in answer["changes"]], ["부과금 도우미", "부가옵션 가격 도우미", "가격 캘린더 도우미"])
        for line, number, word in zip(lines[PRICE.name], (charge, addon, price), WORDS):
            head, _when, scope = line.split(" · ", 2)
            self.assertEqual(head, f"장부 {number}번")
            self.assertTrue(scope.startswith(word), f"범위의 머리가 종류를 댄다({word}): {line}")
        self.assertIn(f" · 객실 가격 · {scene.OFFER} · ", lines[PRICE.name][2], "객실 가격 줄은 오퍼를 댄다(P3)")


class InstructionsTest(unittest.TestCase):
    """P1 · P2 — 도우미들의 안내문이 같은 말을 한다: 목록에는 네 도우미(프로모션 할인까지)의 기록이 모두 나오고, 다른 도우미의 기록은 읽어 주기만 하며
    그 이상(되돌리기 · 이어서)은 맡은 도우미를 댄다. 목록이 비었으면 무엇을 보았는지(이 컴퓨터의 장부 · 이 호텔) 말하는 문장 하나."""

    EMPTY = '`changes` 가 비었으면 "이 컴퓨터의 장부에 <`hotel.name`> 기록이 하나도 없습니다(객실 가격 · 부가옵션 가격 · 부과금 · 프로모션 모두)."'
    OTHER = ('다른 도우미의 줄(`helper`)은 읽어 주기만 하고, 그 번호를 되돌리거나 이어서 하라면 "장부 <`id`>번은 <`helper`>의 기록입니다"라고 '
             '하고 그 도우미로 한다.')

    def test_every_helper_reads_out_another_helper_s_record_names_its_owner_and_says_the_empty_ledger_sentence(self):
        for skill in ("stay-price-change", "stay-addon-price-change", "stay-charge-change"):
            text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
            prep = text[text.index("5. **장부 보기.**"):text.index("## 읽기")]
            self.assertIn("네 도우미", prep, skill)
            self.assertIn(self.OTHER, prep, skill)
            show = text[text.index("## 장부 보여줘"):]
            self.assertIn(self.EMPTY, show[:show.index("\n## ", 1)], skill)


if __name__ == "__main__":
    unittest.main()
