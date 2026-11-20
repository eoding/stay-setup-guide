"""안내문(SKILL.md · references/commands.md · references/page.md)에 적힌 명령 · 플래그 · 페이지 호출이 코드에 그 이름으로 있고,
새 요금표 길의 예 · 문장 · 읽기 값이 코드와 같다.

글의 코드 조각(`…` 과 ``` 덩어리)에서 `price_change.py <명령>`, 명령 표의 첫 칸, 명령 뒤의 `--플래그`, `stayPrice.<호출>`,
`stayPriceLoader.<호출>` 을 모아 명령 파서와 페이지 모듈에 견준다. 글을 고쳐 없는 이름을 적으면 여기서 실패한다.

    python3 -m unittest discover -s tests
"""

import argparse
import json
import re
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

from change_core.ledger import CAUSES, IDLE  # noqa: E402
from price_browser import PAGE_KEEPS, READ_SPAN, read_calls, reserved_probes  # noqa: E402
from price_change import parser  # noqa: E402
from price_model import ERP_MAX_DAYS, GAP_KINDS  # noqa: E402
from price_pages import SEASON_REFILL_NOTE  # noqa: E402
from price_sheet import SheetCheck, decode_sheet  # noqa: E402

DOCS = [SKILL / "SKILL.md", SKILL / "references" / "commands.md", SKILL / "references" / "page.md"]


def required() -> dict[str, set[str]]:
    sub = next(action for action in parser()._actions if isinstance(action, argparse._SubParsersAction))
    return {name: {action.option_strings[0] for action in command._actions if action.required and action.option_strings}
            for name, command in sub.choices.items()}


def commands() -> dict[str, set[str]]:
    sub = next(action for action in parser()._actions if isinstance(action, argparse._SubParsersAction))
    return {name: {flag for action in command._actions for flag in action.option_strings} | {
        choice for action in command._actions if action.choices and not action.option_strings for choice in action.choices}
        for name, command in sub.choices.items()}


def exported(path: Path, name: str) -> set[str]:
    """`window.<name> = { … }` 의 맨 바깥 키 — 괄호 깊이 1 에서 `이름:` 으로 시작하는 것."""
    text = path.read_text(encoding="utf-8")
    at, depth, keys, start = text.index(f"window.{name} = {{") + len(f"window.{name} = "), 0, set(), None
    for index in range(at, len(text)):
        char = text[index]
        if char in "{([":
            depth += 1
            start = index + 1 if depth == 1 else start
        elif char in "})]":
            depth -= 1
            if depth == 0:
                break
        elif char == "," and depth == 1:
            start = index + 1
        if depth == 1 and start is not None:
            found = re.match(r"(?:\s|//[^\n]*\n)*(\w+)\s*:", text[start:start + 400])
            if found:
                keys.add(found.group(1))
            start = None
    return keys


def code_bits(text: str) -> list[str]:
    blocks = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return blocks + re.findall(r"`([^`\n]+)`", text)


class DocNamesTest(unittest.TestCase):
    def setUp(self):
        self.commands = commands()
        self.page = exported(SKILL / "scripts" / "page" / "stay_price.js", "stayPrice")
        self.loader = exported(SKILL / "scripts" / "page" / "stay_price_loader.js", "stayPriceLoader")

    def test_the_lever_sees_the_code(self):
        self.assertIn("--record", self.commands["read-calls"])
        self.assertIn("look", self.page)
        self.assertIn("again", self.loader)

    def test_every_command_and_flag_in_the_instructions_exists_with_that_name(self):
        for doc in DOCS:
            text = doc.read_text(encoding="utf-8")
            for name in re.findall(r"price_change\.py ([a-z][\w-]*)", text):
                self.assertIn(name, self.commands, f"{doc.name}: price_change.py {name}")
            # commands.md 「하위 명령」 표 — 첫 칸의 명령, 둘째 칸의 플래그
            if doc.name == "commands.md":
                table = text[text.index("## 하위 명령"):]
                table = table[:table.index("\n## ", 1)]
                rows = re.findall(r"^\| `([a-z][\w-]*)` \|([^|\n]*)\|", table, re.M)
                self.assertEqual({name for name, _flags in rows}, set(self.commands), "표가 모든 명령을 한 줄씩 적는다")
                for name, flags in rows:
                    for flag in re.findall(r"--[a-z][\w-]*", flags):
                        self.assertIn(flag, self.commands[name], f"{doc.name}: {name} {flag}")
            for bit in code_bits(text):
                for line in bit.splitlines():
                    current = None
                    for token in re.split(r"[\s`]+", line):
                        word = token.strip('"\'(),.;')
                        if word in self.commands and not (current and word in self.commands[current]):
                            current = word   # `render rollback` 의 rollback 은 render 의 고르는 값이다
                        elif word.startswith("--") and re.fullmatch(r"--[a-z][\w-]*", word):
                            owner = current or next((c for c, flags in self.commands.items() if word in flags), None)
                            self.assertIsNotNone(owner, f"{doc.name}: 없는 플래그 {word} ({line.strip()})")
                            self.assertIn(word, self.commands[owner], f"{doc.name}: {owner} {word} ({line.strip()})")

    def test_where_the_instructions_call_a_command_with_flags_they_give_every_required_flag(self):
        # begin 은 적용 직전에 읽은 값(--snapshot) 없이는 시작하지 않는다(T1) — 글이 그 플래그를 빠뜨리면 여기서 실패한다
        needed = required()
        self.assertIn("--snapshot", needed["begin"])
        for doc in DOCS:
            for bit in code_bits(doc.read_text(encoding="utf-8")):
                for line in bit.splitlines():
                    words = [token.strip('"\'(),.;') for token in re.split(r"[\s`]+", line)]
                    called = next((word for word in words if word in self.commands), None)
                    flags = {word for word in words if word.startswith("--")}
                    if called and flags & self.commands[called]:
                        self.assertLessEqual(needed[called], flags, f"{doc.name}: {line.strip()}")

    def test_the_instructions_say_the_idle_window_and_every_stop_cause_the_code_uses(self):
        minutes = f"{int(IDLE.total_seconds() // 60)}분"
        for doc in DOCS[:2]:
            text = doc.read_text(encoding="utf-8")
            self.assertIn(minutes, text, f"{doc.name}: 멈춤으로 보는 시간")
            for cause in CAUSES:
                self.assertIn(f"`{cause}`", text, f"{doc.name}: check 의 cause {cause}")

    def test_page_md_names_every_storage_key_the_page_and_loader_write_and_no_other(self):
        scripts = SKILL / "scripts" / "page"
        keys = {key for name in ("stay_price.js", "stay_price_loader.js")
                for key in re.findall(r"'(stayPrice[A-Z]\w*)'", (scripts / name).read_text(encoding="utf-8"))}
        self.assertEqual(len(keys), 4, keys)
        text = (SKILL / "references" / "page.md").read_text(encoding="utf-8")
        paragraph = text[text.index("**페이지에 남기는 것.**"):].split("\n\n", 1)[0]
        self.assertEqual(set(re.findall(r"`(stayPrice[A-Z]\w*)`", paragraph)), keys)

    def test_every_page_call_in_the_instructions_exists_with_that_name(self):
        for doc in DOCS:
            text = doc.read_text(encoding="utf-8")
            for name in re.findall(r"stayPrice\.(\w+)", text):
                self.assertIn(name, self.page, f"{doc.name}: stayPrice.{name}")
            for name in re.findall(r"stayPriceLoader\.(\w+)", text):
                self.assertIn(name, self.loader, f"{doc.name}: stayPriceLoader.{name}")


class SheetDocsTest(unittest.TestCase):
    """새 요금표 길(S7) — 안내문의 요금표 예, 덮기 한 문장, 넣지 않는 것의 종류, 읽기 값이 코드와 같다."""

    def setUp(self):
        self.skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.commands = (SKILL / "references" / "commands.md").read_text(encoding="utf-8")

    def test_the_sheet_example_in_commands_md_is_a_sheet_the_command_takes(self):
        section = self.commands[self.commands.index("### 요금표 (`kind: sheet`)"):]
        sheet = decode_sheet(json.loads(re.search(r"```json\n(.*?)```", section, re.S).group(1)))
        check = SheetCheck(sheet, tuple(dict.fromkeys((line.room, line.rate_plan) for line in sheet.lines)))
        self.assertTrue(check.cells)
        self.assertEqual({row.occupancy for line in sheet.lines for row in line.rows}, {"A2", "A3", "A2C1_CHD"})

    def test_the_instructions_say_the_season_refill_sentence_the_pages_say(self):
        self.assertGreaterEqual(self.skill.count(SEASON_REFILL_NOTE), 2, "두 길을 말할 때와 미리보기를 말할 때")
        self.assertIn("(가) 시즌 원판 바꾸기", self.skill)
        self.assertIn("아직 못 합니다", self.skill)
        self.assertNotIn("새 요금표로 통째 바꾸기는 아직 못 한다", self.skill)

    def test_commands_md_names_every_kind_of_gap(self):
        table = self.commands[self.commands.index("## 넣지 않는 것"):]
        table = table[:table.index("\n## ", 1)]
        self.assertEqual(set(re.findall(r"^\| `(\w+)` \|", table, re.M)) - {"kind"}, set(GAP_KINDS))   # 머리 줄은 `kind`

    def test_the_reading_cost_in_the_instructions_is_what_the_code_does(self):
        hotel, year = {"id": "1", "name": "호텔"}, [(date(2027, 1, 1) + timedelta(days=n)).isoformat() for n in range(365)]
        per_pair = len(read_calls(hotel, "오퍼", [("객실", "요금제")], year))
        probes = len(reserved_probes(hotel, "오퍼", [("객실", "요금제")], year))
        most = max(n for n in range(1, PAGE_KEEPS + 1) if n * per_pair + probes <= PAGE_KEEPS)
        self.assertEqual((per_pair, probes, most), (2, 1, 19))
        self.assertIn(f"가격 읽기(`readPair`) {per_pair}번({READ_SPAN}일에 한 번)", self.skill)
        self.assertIn(f"예약 있는 날 읽기(`readReserved`) {probes}번({ERP_MAX_DAYS}일에 한 번", self.skill)
        self.assertIn(f"합쳐 {PAGE_KEEPS}번까지", self.skill)
        self.assertIn(f"객실 · 요금제 {most}개까지", self.skill)
        for words in (f"{READ_SPAN}일에 한 번", f"{ERP_MAX_DAYS}일에 한 번", f"합쳐 {PAGE_KEEPS}번까지", "`KEEP_BODIES`"):
            self.assertIn(words, self.commands)


if __name__ == "__main__":
    unittest.main()
