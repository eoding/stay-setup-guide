"""안내문(SKILL.md 와 references/ 의 파일 전부)에 적힌 명령 · 플래그 · 페이지 호출 · 올리개 호출 · 판정 코드가 코드에 그 이름으로 있다(X8).

글의 코드 조각(`…` 과 ``` 덩어리)에서 `addon_change.py <명령>`, 명령 표의 첫 칸과 둘째 칸의 플래그, 명령 뒤의 `--플래그`,
`stayAddonPrice.<호출>`, `stayPriceLoader.<호출>` 을 모아 명령 파서 · 페이지 모듈 · 올리개에 견준다. 글을 고쳐 없는 이름을 적으면
여기서 실패한다. SKILL.md 는 담당자의 Claude 가 쓸 때마다 통째로 읽으므로 크기를 지키고, 참고 파일을 모두 가리킨다.

    python3 -m unittest discover -s tests
"""

import argparse
import re
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

from addon_change import PAGE_KEEPS, parser  # noqa: E402
from addon_plan import CHOICE_LABELS, LINE_RULES  # noqa: E402
from change_core.ledger import CAUSES, IDLE  # noqa: E402

PRICE = SKILL.parent / "stay-price-change"
REFERENCES = sorted((SKILL / "references").glob("*.md"))
DOCS = [SKILL / "SKILL.md", *REFERENCES]
SKILL_BUDGET = 20_000          # SKILL.md 의 바이트 수 상한(UTF-8)


def subcommands() -> dict:
    return next(action for action in parser()._actions if isinstance(action, argparse._SubParsersAction)).choices


def commands() -> dict[str, set[str]]:
    return {name: {flag for action in command._actions for flag in action.option_strings} | {
        choice for action in command._actions if action.choices and not action.option_strings for choice in action.choices}
        for name, command in subcommands().items()}


def required() -> dict[str, set[str]]:
    return {name: {action.option_strings[0] for action in command._actions if action.required and action.option_strings}
            for name, command in subcommands().items()}


def exported(path: Path, name: str) -> set[str]:
    """`window.<name> = { … }` 의 맨 바깥 키."""
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
        self.page = exported(SKILL / "scripts" / "page" / "stay_addon_price.js", "stayAddonPrice")
        self.loader = exported(PRICE / "scripts" / "page" / "stay_price_loader.js", "stayPriceLoader")

    def test_the_lever_sees_the_code(self):
        self.assertIn("--record", self.commands["read-calls"])
        self.assertEqual({"look", "readLine", "applyLine", "take", "last", "idle"} - self.page, set())
        self.assertIn("again", self.loader)

    def test_every_command_and_flag_in_the_instructions_exists_with_that_name(self):
        for doc in DOCS:
            text = doc.read_text(encoding="utf-8")
            for name in re.findall(r"addon_change\.py ([a-z][\w-]*)", text):
                self.assertIn(name, self.commands, f"{doc.name}: addon_change.py {name}")
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
                            current = word
                        elif word.startswith("--") and re.fullmatch(r"--[a-z][\w-]*", word):
                            owner = current or next((c for c, flags in self.commands.items() if word in flags), None)
                            self.assertIsNotNone(owner, f"{doc.name}: 없는 플래그 {word} ({line.strip()})")
                            self.assertIn(word, self.commands[owner], f"{doc.name}: {owner} {word} ({line.strip()})")

    def test_where_the_instructions_call_a_command_with_flags_they_give_every_required_flag(self):
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

    def test_paths_handed_to_a_command_in_the_instructions_are_quoted(self):
        flags = r"--(?:out|snapshot|request|plan|calls|answers|resolutions|result|look)"
        for doc in DOCS:
            for bit in code_bits(doc.read_text(encoding="utf-8")):
                for found in re.finditer(rf"({flags}) (\S+)", bit):
                    if "<" in found.group(2):
                        self.assertTrue(found.group(2).startswith('"'), f"{doc.name}: {found.group(0)}")

    def test_every_page_and_loader_call_in_the_instructions_exists_with_that_name(self):
        for doc in DOCS:
            text = doc.read_text(encoding="utf-8")
            for name in re.findall(r"stayAddonPrice\.(\w+)", text):
                self.assertIn(name, self.page, f"{doc.name}: stayAddonPrice.{name}")
            for name in re.findall(r"stayPriceLoader\.(\w+)", text):
                self.assertIn(name, self.loader, f"{doc.name}: stayPriceLoader.{name}")
            self.assertNotRegex(text, r"stayPrice\.(?!js)\w+\(", f"{doc.name}: 가격 캘린더 도우미의 작업을 부르라고 하지 않는다")

    def test_the_rules_table_names_every_rule_and_choice_the_code_uses(self):
        text = (SKILL / "references" / "commands.md").read_text(encoding="utf-8")
        table = text[text.index("## 판정"):]
        table = table[:table.index("\n## ", 1)]
        self.assertEqual(set(re.findall(r"^\| `([A-Z_0-9]+)` \|", table, re.M)), {rule.code for rule in LINE_RULES.rules})
        for choice in CHOICE_LABELS:
            self.assertIn(f"`{choice}`", table)

    def test_the_stopped_page_says_the_idle_window_and_every_stop_cause(self):
        text = (SKILL / "references" / "stopped.md").read_text(encoding="utf-8")
        self.assertIn(f"{int(IDLE.total_seconds() // 60)}분", text)
        for cause in CAUSES:
            self.assertIn(f"`{cause}`", text)

    def test_page_md_names_every_storage_key_the_loader_writes_for_this_helper(self):
        loader = (PRICE / "scripts" / "page" / "stay_price_loader.js").read_text(encoding="utf-8")
        page = (PRICE / "scripts" / "page" / "stay_price.js").read_text(encoding="utf-8")
        keys = set(re.findall(r"'(stayPrice[A-Z]\w*)'", loader + page))
        text = (SKILL / "references" / "page.md").read_text(encoding="utf-8")
        paragraph = text[text.index("**페이지에 남기는 것.**"):].split("\n\n", 1)[0]
        self.assertEqual(set(re.findall(r"`(stayPrice[A-Z]\w*)`", paragraph)), keys)


class LimitTest(unittest.TestCase):
    def test_one_reading_holds_as_many_lines_as_the_page_keeps_pieces_and_the_docs_say_that_number(self):
        page = (PRICE / "scripts" / "page" / "stay_price.js").read_text(encoding="utf-8")
        self.assertEqual(int(re.search(r"var KEEP_BODIES = (\d+);", page).group(1)), PAGE_KEEPS,
                         "readLine 하나가 조각 하나 — 읽기 한 번의 줄 수는 페이지가 두는 조각 수까지다")
        self.assertIn(f"한 번에 {PAGE_KEEPS}줄까지", (SKILL / "references" / "commands.md").read_text(encoding="utf-8"))


class SkillShapeTest(unittest.TestCase):
    def setUp(self):
        self.skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    def test_skill_md_fits_the_budget_and_points_to_every_reference(self):
        size = len(self.skill.encode("utf-8"))
        self.assertLessEqual(size, SKILL_BUDGET, f"SKILL.md 가 {size:,}바이트 — 가끔만 필요한 갈래는 references/ 로 옮긴다")
        for path in REFERENCES:
            self.assertIn(f"](references/{path.name})", self.skill, f"SKILL.md 가 {path.name} 를 가리키지 않는다")

    def test_the_pointer_to_the_stopped_page_repeats_the_rule_that_must_not_be_missed(self):
        pointing = [line for line in self.skill.splitlines() if "](references/stopped.md)" in line]
        self.assertTrue(any("다시 읽어 `check` 가 이어서 해도 된다고 하기 전에는 이어서 하지 않는다" in line for line in pointing))

    def test_it_says_what_it_refuses(self):
        rules = self.skill[self.skill.index("## 반드시 지킬 것"):self.skill.index("## 담당자에게 말할 때")]
        for refused in ("[삭제]", "만들기", "의무 규칙", "다른 탭", "두 번 누르지 않는다", "적용"):
            self.assertIn(refused, rules)


if __name__ == "__main__":
    unittest.main()
