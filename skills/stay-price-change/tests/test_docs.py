"""안내문(SKILL.md · references/commands.md · references/page.md)에 적힌 명령 · 플래그 · 페이지 호출이 코드에 그 이름으로 있다.

글의 코드 조각(`…` 과 ``` 덩어리)에서 `price_change.py <명령>`, 명령 표의 첫 칸, 명령 뒤의 `--플래그`, `stayPrice.<호출>`,
`stayPriceLoader.<호출>` 을 모아 명령 파서와 페이지 모듈에 견준다. 글을 고쳐 없는 이름을 적으면 여기서 실패한다.

    python3 -m unittest discover -s tests
"""

import argparse
import re
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

from price_change import parser  # noqa: E402

DOCS = [SKILL / "SKILL.md", SKILL / "references" / "commands.md", SKILL / "references" / "page.md"]


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

    def test_every_page_call_in_the_instructions_exists_with_that_name(self):
        for doc in DOCS:
            text = doc.read_text(encoding="utf-8")
            for name in re.findall(r"stayPrice\.(\w+)", text):
                self.assertIn(name, self.page, f"{doc.name}: stayPrice.{name}")
            for name in re.findall(r"stayPriceLoader\.(\w+)", text):
                self.assertIn(name, self.loader, f"{doc.name}: stayPriceLoader.{name}")


if __name__ == "__main__":
    unittest.main()
