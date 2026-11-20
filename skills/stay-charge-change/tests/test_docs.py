"""안내문(SKILL.md 와 references/ 의 파일 전부)에 적힌 명령 · 플래그 · 페이지 호출 · 올리개 호출 · 판정 코드 · 오류 글이 코드에 그 이름으로
있다(C8).

글의 코드 조각(`…` 과 ``` 덩어리)에서 `charge_change.py <명령>`, 명령 표의 첫 칸과 둘째 칸의 플래그, 명령 뒤의 `--플래그`,
`stayCharge.<호출>`, `stayPriceLoader.<호출>` 을 모아 명령 파서 · 페이지 모듈 · 올리개에 견주고, 오류 표의 글을 코드에서 찾는다. 글을
고쳐 없는 이름을 적으면 여기서 실패한다. SKILL.md 는 담당자의 Claude 가 쓸 때마다 통째로 읽으므로 크기를 지키고, 참고 파일을 모두
가리킨다.

    python3 -m unittest discover -s tests
"""

import argparse
import re
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

from charge_change import PAGE_KEEPS, parser  # noqa: E402
from charge_model import FIELD_LABELS, PART_FIELDS  # noqa: E402
from charge_plan import CHOICE_LABELS, RULES  # noqa: E402
from change_core.ledger import CAUSES, IDLE  # noqa: E402

PRICE = SKILL.parent / "stay-price-change"
REFERENCES = sorted((SKILL / "references").glob("*.md"))
DOCS = [SKILL / "SKILL.md", *REFERENCES]
SKILL_BUDGET = 16_384          # SKILL.md 의 바이트 수 상한(UTF-8) — 16 KB
PAGE = SKILL / "scripts" / "page" / "stay_charge.js"
KIT = PRICE / "scripts" / "page" / "stay_price.js"
LOADER = PRICE / "scripts" / "page" / "stay_price_loader.js"


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


def section(text: str, head: str) -> str:
    part = text[text.index(head):]
    return part[:part.index("\n## ", 1)] if "\n## " in part[1:] else part


def error_heads(table: str) -> list[str]:
    """오류 표의 첫 칸에 적힌 글들(`…` 로 감싼 것) — 「…」 로 줄인 곳에서 끊은 조각들."""
    out = []
    for row in re.findall(r"^\| (.+?) \| ", table, re.M):
        for bit in re.findall(r"``? ?(.+?) ?``?(?: ·|$)", row):
            out += [piece.strip() for piece in bit.split("…") if len(piece.strip()) >= 4]
    return out


class DocNamesTest(unittest.TestCase):
    def setUp(self):
        self.commands = commands()
        self.page = exported(PAGE, "stayCharge")
        self.loader = exported(LOADER, "stayPriceLoader")

    def test_the_lever_sees_the_code(self):
        self.assertIn("--record", self.commands["read-calls"])
        self.assertEqual({"look", "readCharge", "applyCharge", "take", "last", "idle"} - self.page, set())
        self.assertIn("again", self.loader)

    def test_every_command_and_flag_in_the_instructions_exists_with_that_name(self):
        for doc in DOCS:
            text = doc.read_text(encoding="utf-8")
            for name in re.findall(r"charge_change\.py ([a-z][\w-]*)", text):
                self.assertIn(name, self.commands, f"{doc.name}: charge_change.py {name}")
            if doc.name == "commands.md":
                rows = re.findall(r"^\| `([a-z][\w-]*)` \|([^|\n]*)\|", section(text, "## 하위 명령"), re.M)
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
            for name in re.findall(r"stayCharge\.(\w+)", text):
                self.assertIn(name, self.page, f"{doc.name}: stayCharge.{name}")
            for name in re.findall(r"stayPriceLoader\.(\w+)", text):
                self.assertIn(name, self.loader, f"{doc.name}: stayPriceLoader.{name}")
            self.assertNotRegex(text, r"stay(?:Price|AddonPrice)\.(?!js)\w+\(", f"{doc.name}: 다른 도우미의 작업을 부르라고 하지 않는다")
            for name in re.findall(r"stayPriceLoader\.\w+\('(\w+)'\)", text):
                self.assertEqual(name, "charge", f"{doc.name}: 올리개 묶음은 'charge'")

    def test_the_rules_table_names_every_rule_and_choice_the_code_uses(self):
        table = section((SKILL / "references" / "commands.md").read_text(encoding="utf-8"), "## 판정")
        self.assertEqual(set(re.findall(r"^\| `([A-Z_0-9]+)` \|", table, re.M)), {rule.code for rule in RULES.rules})
        for choice in CHOICE_LABELS:
            self.assertIn(f"`{choice}`", table)

    def test_the_amounts_table_names_every_place_the_model_knows(self):
        table = section((SKILL / "references" / "commands.md").read_text(encoding="utf-8"), "## 금액 칸")
        for part, fields in PART_FIELDS.items():
            for name in fields:
                self.assertIn(f'"{name}"', table, f"{part} · {name}")
        for word in ('"time"', '"age"'):
            self.assertIn(word, table)
        self.assertEqual(len(FIELD_LABELS), sum(len(fields) for fields in PART_FIELDS.values()))

    def test_every_error_the_tables_quote_is_said_by_the_code(self):
        python = "\n".join(path.read_text(encoding="utf-8") for path in [*(SKILL / "scripts").glob("*.py"),
                                                                            *(PRICE / "scripts" / "change_core").glob("*.py")])
        # 창 이름은 모듈이 kit 에 넘긴다(「부과금 편집 창」 + 「이 저장을 거절했습니다」) — 붙인 글로 찾는다
        pages = "\n".join(path.read_text(encoding="utf-8") for path in (PAGE, KIT, LOADER)).replace("opts.window + '", "부과금 편집 창")
        for doc, source in (("commands.md", python), ("page.md", pages)):
            table = section((SKILL / "references" / doc).read_text(encoding="utf-8"), "## 오류")
            heads = [head for head in error_heads(table) if head != "stayCharge is not defined"]
            self.assertGreater(len(heads), 10, doc)
            missing = [head for head in heads if head not in source]
            self.assertEqual(missing, [], f"{doc}: 코드에 없는 오류 글")

    def test_the_stopped_page_says_the_idle_window_and_every_stop_cause(self):
        text = (SKILL / "references" / "stopped.md").read_text(encoding="utf-8")
        self.assertIn(f"{int(IDLE.total_seconds() // 60)}분", text)
        for cause in CAUSES:
            self.assertIn(f"`{cause}`", text)

    def test_page_md_names_every_storage_key_the_loader_writes_for_this_helper(self):
        loader = LOADER.read_text(encoding="utf-8")
        names = re.search(r"charge: \[([^\]]+)\]", loader).group(1).split(",")
        keys = {re.search(rf"var {name.strip()} = \{{[^}}]*key: '(\w+)'", loader).group(1) for name in names}
        keys |= set(re.findall(r"'(stayPrice[A-Z]\w*)'", KIT.read_text(encoding="utf-8")))
        text = (SKILL / "references" / "page.md").read_text(encoding="utf-8")
        paragraph = text[text.index("**페이지에 남기는 것.**"):].split("\n\n", 1)[0]
        self.assertEqual(set(re.findall(r"`(stayPrice[A-Z]\w*)`", paragraph)), keys)


class LimitTest(unittest.TestCase):
    def test_one_reading_holds_as_many_charges_as_the_page_keeps_pieces_and_the_docs_say_that_number(self):
        page = KIT.read_text(encoding="utf-8")
        self.assertEqual(int(re.search(r"var KEEP_BODIES = (\d+);", page).group(1)), PAGE_KEEPS,
                         "readCharge 하나가 조각 하나 — 읽기 한 번의 부과금 수는 페이지가 두는 조각 수까지다")
        self.assertIn(f"한 번에 {PAGE_KEEPS}개까지", (SKILL / "references" / "commands.md").read_text(encoding="utf-8"))


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

    def test_it_says_what_it_refuses_and_that_it_changes_amounts_only(self):
        rules = self.skill[self.skill.index("## 반드시 지킬 것"):self.skill.index("## 담당자에게 말할 때")]
        for refused in ("[삭제]", "[부과금 추가]", "[정보 수집 폼]", "[요율 행 추가]", "금액만 바꾼다", "채우지 않고",
                        "비우지 않는다", "다른 탭", "두 번 누르지 않는다", "적용"):
            self.assertIn(refused, rules)

    def test_the_other_two_helpers_point_here_where_they_used_to_say_charges_are_not_handled(self):
        for other in ("stay-price-change", "stay-addon-price-change"):
            skill = (SKILL.parent / other / "SKILL.md").read_text(encoding="utf-8")
            not_done = (SKILL.parent / other / "references" / "not-done.md").read_text(encoding="utf-8")
            self.assertTrue("stay-charge-change" in skill and "stay-charge-change" in not_done, f"{other} 가 이 도우미를 가리킨다")
            self.assertFalse(re.search(r"부과금 ?· ?프로모션 할인은 다루지 않는다", skill), f"{other} 가 아직 부과금을 다루지 않는다고 한다")


if __name__ == "__main__":
    unittest.main()
