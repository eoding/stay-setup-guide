"""안내문(SKILL.md 와 references/ 의 파일 전부)에 적힌 명령 · 플래그 · 페이지 호출 · 올리개 호출 · 판정 코드 · 오류 글이 코드에 그 이름으로
있다(M8).

글의 코드 조각(`…` 과 ``` 덩어리)에서 `promotion_change.py <명령>`, 명령 표의 첫 칸과 둘째 칸의 플래그, 명령 뒤의 `--플래그`,
`stayPromotion.<호출>`, `stayPriceLoader.<호출>` 을 모아 명령 파서 · 페이지 모듈 · 올리개에 견주고, 오류 표의 글을 코드에서 찾는다. 글을
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

from promotion_change import PAGE_KEEPS, parser  # noqa: E402
from promotion_model import BASES, GATE  # noqa: E402
from promotion_plan import CHOICE_LABELS, RULES  # noqa: E402
from change_core.ledger import CAUSES, IDLE  # noqa: E402

PRICE = SKILL.parent / "stay-price-change"
REFERENCES = sorted((SKILL / "references").glob("*.md"))
DOCS = [SKILL / "SKILL.md", *REFERENCES]
SKILL_BUDGET = 16_384          # SKILL.md 의 바이트 수 상한(UTF-8) — 16 KB
PAGE = SKILL / "scripts" / "page" / "stay_promotion.js"
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
        self.page = exported(PAGE, "stayPromotion")
        self.loader = exported(LOADER, "stayPriceLoader")

    def test_the_lever_sees_the_code(self):
        self.assertIn("--record", self.commands["read-calls"])
        self.assertEqual({"look", "readPromotion", "applyPromotion", "take", "last", "idle"} - self.page, set())
        self.assertIn("again", self.loader)

    def test_every_command_and_flag_in_the_instructions_exists_with_that_name(self):
        for doc in DOCS:
            text = doc.read_text(encoding="utf-8")
            for name in re.findall(r"promotion_change\.py ([a-z][\w-]*)", text):
                self.assertIn(name, self.commands, f"{doc.name}: promotion_change.py {name}")
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
            for name in re.findall(r"stayPromotion\.(\w+)", text):
                self.assertIn(name, self.page, f"{doc.name}: stayPromotion.{name}")
            for name in re.findall(r"stayPriceLoader\.(\w+)", text):
                self.assertIn(name, self.loader, f"{doc.name}: stayPriceLoader.{name}")
            self.assertNotRegex(text, r"stay(?:Price|AddonPrice|Charge)\.(?!js)\w+\(", f"{doc.name}: 다른 도우미의 작업을 부르라고 하지 않는다")
            for name in re.findall(r"stayPriceLoader\.\w+\('(\w+)'\)", text):
                self.assertEqual(name, "promotion", f"{doc.name}: 올리개 묶음은 'promotion'")

    def test_the_rules_table_names_every_rule_and_choice_the_code_uses(self):
        table = section((SKILL / "references" / "commands.md").read_text(encoding="utf-8"), "## 판정")
        self.assertEqual(set(re.findall(r"^\| `([A-Z_0-9]+)` \|", table, re.M)), {rule.code for rule in RULES.rules})
        for choice in CHOICE_LABELS:
            self.assertIn(f"`{choice}`", table)

    def test_the_tiers_table_names_every_basis_and_the_request_names_every_way(self):
        tiers = section((SKILL / "references" / "commands.md").read_text(encoding="utf-8"), "## 단")
        for name in ("정률", "정액", "무료 숙박"):
            self.assertIn(name, tiers)
        self.assertEqual(set(BASES), {"PCT", "FLAT", "FREE_NIGHT"})
        request = section((SKILL / "references" / "commands.md").read_text(encoding="utf-8"), "## 요청 파일")
        for word in ("`value`", "`amount`", "`percent`", '"tier"', '"offer": "0"'):
            self.assertIn(word, request)

    def test_every_error_the_tables_quote_is_said_by_the_code(self):
        python = "\n".join(path.read_text(encoding="utf-8") for path in [*(SKILL / "scripts").glob("*.py"),
                                                                            *(PRICE / "scripts" / "change_core").glob("*.py")])
        # 창 이름은 모듈이 kit 에 넘긴다(「부과금 편집 창」 + 「이 저장을 거절했습니다」) — 붙인 글로 찾는다
        pages = "\n".join(path.read_text(encoding="utf-8") for path in (PAGE, KIT, LOADER)).replace("opts.window + '", "프로모션 편집 창")
        for doc, source in (("commands.md", python), ("page.md", pages)):
            table = section((SKILL / "references" / doc).read_text(encoding="utf-8"), "## 오류")
            heads = [head for head in error_heads(table) if head != "stayPromotion is not defined"]
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
        names = re.search(r"promotion: \[([^\]]+)\]", loader).group(1).split(",")
        keys = {re.search(rf"var {name.strip()} = \{{[^}}]*key: '(\w+)'", loader).group(1) for name in names}
        keys |= set(re.findall(r"'(stayPrice[A-Z]\w*)'", KIT.read_text(encoding="utf-8")))
        text = (SKILL / "references" / "page.md").read_text(encoding="utf-8")
        paragraph = text[text.index("**페이지에 남기는 것.**"):].split("\n\n", 1)[0]
        self.assertEqual(set(re.findall(r"`(stayPrice[A-Z]\w*)`", paragraph)), keys)


class GateWordsTest(unittest.TestCase):
    def test_the_plain_gate_sentence_is_one_sentence_everywhere(self):
        page = PAGE.read_text(encoding="utf-8")
        self.assertIn(GATE, page, "페이지와 명령이 같은 문장을 쓴다")
        for doc in (SKILL / "SKILL.md", SKILL / "references" / "not-done.md", SKILL / "references" / "commands.md"):
            text = doc.read_text(encoding="utf-8")
            self.assertTrue(GATE in text or "`gate`" in text, doc.name)
        self.assertIn(GATE, (SKILL / "references" / "commands.md").read_text(encoding="utf-8"))
        self.assertIn(GATE, (SKILL / "references" / "not-done.md").read_text(encoding="utf-8"))

    def test_skill_md_says_it_never_saves_without_the_mark_and_changes_tier_values_only(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("표식 없는 ERP 에서는 저장하지 않는다", skill)
        self.assertIn("단의 값만 바꾼다", skill)
        self.assertIn("표식이 있는 ERP 에서만 저장한다", skill.split("---")[1], "설명(description)도 말한다")


class LimitTest(unittest.TestCase):
    def test_one_reading_holds_as_many_promotions_as_the_page_keeps_pieces_and_the_docs_say_that_number(self):
        page = KIT.read_text(encoding="utf-8")
        self.assertEqual(int(re.search(r"var KEEP_BODIES = (\d+);", page).group(1)), PAGE_KEEPS,
                         "readPromotion 하나가 조각 하나 — 읽기 한 번의 프로모션 수는 페이지가 두는 조각 수까지다")
        self.assertIn(f"한 번에 {PAGE_KEEPS}개까지", (SKILL / "references" / "commands.md").read_text(encoding="utf-8"))


class SkillShapeTest(unittest.TestCase):
    def setUp(self):
        self.skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    def test_skill_md_fits_the_budget_and_points_to_every_reference(self):
        size = len(self.skill.encode("utf-8"))
        self.assertLessEqual(size, SKILL_BUDGET, f"SKILL.md 가 {size:,}바이트 — 가끔만 필요한 갈래는 references/ 로 옮긴다")
        for path in REFERENCES:
            self.assertIn(f"](references/{path.name})", self.skill, f"SKILL.md 가 {path.name} 를 가리키지 않는다")

    def test_every_preparation_step_uses_only_what_an_earlier_step_set_up(self):
        """H4 — 일마다 새 작업 폴더(work)에서 시작하고, look 을 부르고 · 명령으로 묶고 · 명령이 말한 조각을 받은 뒤에 목록을 탭의
        호텔로 본다(그 차례가 명령이 바라는 차례다). --look 을 받는 명령을 한 곳에서 다 댄다."""
        prep = self.skill[self.skill.index("## 준비"):self.skill.index("## 읽기")]
        self.assertLess(prep.index("promotion_change.py work"), prep.index("<작업>/"), "작업 폴더를 만든 뒤에 그 안에 저장한다")
        self.assertLess(prep.index("stayPromotion.look()"), prep.index("promotion_change.py look --answers"))
        self.assertLess(prep.index("promotion_change.py look --answers"), prep.index("`refetch`"), "명령이 받을 조각을 말한다")
        self.assertLess(prep.index("`refetch`"), prep.index("promotion_change.py list --look"), "목록은 탭의 호텔을 안 뒤에")
        self.assertIn("같은 대화의 두 번째 요청도", prep)
        takes = {name for name, command in subcommands().items() if "--look" in {flag for action in command._actions for flag in action.option_strings}}
        said = prep[prep.index("`--look` 으로 받는 명령은"):].split("\n", 1)[0]
        for name in takes:
            self.assertIn(f"`{name}", said, f"--look 을 받는 {name} 을 준비에서 댄다")



if __name__ == "__main__":
    unittest.main()
