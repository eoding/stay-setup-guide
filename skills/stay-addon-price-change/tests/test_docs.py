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
        # 이 도우미의 묶음(`SETS.addon`)이 적는 원본 키와 가격 도우미가 적는 키 — 다른 묶음의 키는 이 도우미의 글에 없다
        files = re.search(r"\baddon: \[([\w, ]+)\]", loader).group(1).split(", ")
        self.assertEqual(len(files), 4, files)
        keys = {re.search(rf"var {name} = \{{ name: '[\w.]+', key: '(stayPrice\w+)'", loader).group(1) for name in files}
        keys |= set(re.findall(r"'(stayPrice[A-Z]\w*)'", page))
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

    def test_a_whole_edit_window_can_be_shown_without_a_change_request(self):
        """H4 — 「이 가격 줄 설정 다 보여줘」: 바꾸기 요청 없이 번호로 읽고 편집 창의 칸 전부를 보이는 길이 SKILL.md 에 있다."""
        job = self.skill[self.skill.index("## 1. "):self.skill.index("## 2. ")]
        for said in ("이 가격 줄 설정 다 보여줘", "read-calls --line ", "render window --snapshot"):
            self.assertIn(said, job)

    def test_p5_the_prices_view_narrows_to_what_the_person_named(self):
        """P5 — 「조식 가격 보여줘」처럼 부가옵션 · 줄을 말하면 look 을 그 낱말로 좁혀 그 줄만 오퍼부터 말한다(페이지는 호텔 전부)."""
        job = self.skill[self.skill.index("## 1. "):self.skill.index("## 2. ")]
        for said in ('`--find "<그 낱말>"`', "`items` 만 「오퍼 · 부가옵션 · 줄」과 판매가로 말한다", "페이지는 호텔 전부다"):
            self.assertIn(said, job)

    def test_the_pointer_to_the_stopped_page_repeats_the_rule_that_must_not_be_missed(self):
        pointing = [line for line in self.skill.splitlines() if "](references/stopped.md)" in line]
        self.assertTrue(any("다시 읽어 `check` 가 이어서 해도 된다고 하기 전에는 이어서 하지 않는다" in line for line in pointing))

    def test_every_preparation_step_uses_only_what_an_earlier_step_set_up(self):
        """H4 — 일마다 새 작업 폴더(work)에서 시작하고, look 을 부르고 · 명령으로 묶고 · 명령이 말한 조각을 받은 뒤에 목록을 탭의
        호텔로 본다(그 차례가 명령이 바라는 차례다). --look 을 받는 명령을 한 곳에서 다 댄다."""
        prep = self.skill[self.skill.index("## 준비"):self.skill.index("## 읽기")]
        self.assertLess(prep.index("addon_change.py work"), prep.index("<작업>/"), "작업 폴더를 만든 뒤에 그 안에 저장한다")
        self.assertLess(prep.index("stayAddonPrice.look()"), prep.index("addon_change.py look --answers"))
        self.assertLess(prep.index("addon_change.py look --answers"), prep.index("`refetch`"), "명령이 받을 조각을 말한다")
        self.assertLess(prep.index("`refetch`"), prep.index("addon_change.py list --look"), "목록은 탭의 호텔을 안 뒤에")
        self.assertIn("같은 대화의 두 번째 요청도", prep)
        takes = {name for name, command in subcommands().items() if "--look" in {flag for action in command._actions for flag in action.option_strings}}
        said = prep[prep.index("`--look` 으로 받는 명령은"):].split("\n", 1)[0]
        for name in takes:
            self.assertIn(f"`{name}", said, f"--look 을 받는 {name} 을 준비에서 댄다")

    def test_it_says_what_it_refuses(self):
        rules = self.skill[self.skill.index("## 반드시 지킬 것"):self.skill.index("## 담당자에게 말할 때")]
        for refused in ("[삭제]", "만들기", "의무 규칙", "다른 탭", "두 번 누르지 않는다", "적용"):
            self.assertIn(refused, rules)


    def test_n3_the_two_everyday_requests_have_their_own_short_section(self):
        """N3 — 「장부 보여줘」는 준비 1~5 와 `line` 을 새것부터 그대로, 되돌린 것을 또 되돌리라면 목록으로만(그 문장 그대로) 답한다."""
        ledger = self.skill[self.skill.index("## 장부 보여줘"):]
        ledger = ledger[:ledger.index("\n## ", 1)]
        for said in ("「준비」 1~5 만", "새것부터", "`line` 그대로", "덧붙이지 않고", "읽지도 장부에 적지도 않는다"):
            self.assertIn(said, ledger)
        none = self.skill[self.skill.index("## 되돌릴 것이 없을 때"):]
        none = none[:none.index("\n## ", 1)]
        for said in ("`rolled_back`", "읽지도 장부에 적지도 않고", "\"장부 <`id`>번은 장부 <`undone_by`>번이 이미 모두 되돌렸습니다. 되돌릴 것이 없어 아무것도 하지 않았습니다.\"",
                     "`previewed` · `empty` · `replaced`"):
            self.assertIn(said, none)

class RoutingTest(unittest.TestCase):
    """H7 — 담당자가 「가격 바꿔줘」라고 하면 세 도우미 가운데 어느 것이 열려도 된다. 그래서 설명(description)과 「하지 않는 일」이
    다른 두 종류를 이름으로 그 도우미에 보내고, 프로모션 할인 값은 프로모션 할인 도우미로 보낸다(세 도우미가 같은 문장)."""

    HELPERS = ("stay-price-change", "stay-addon-price-change", "stay-charge-change")
    PROMO = "프로모션 할인 값은 프로모션 할인 도우미(stay-promotion-change)가 합니다 — 화면에 안 보이는 설정을 지키는 표식이 있는 ERP 에서만 저장합니다."

    def test_the_description_and_the_not_done_page_route_the_other_kinds_and_promotions(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        description = re.search(r'^description: "(.*)"$', text, re.M).group(1)
        not_done = (SKILL / "references" / "not-done.md").read_text(encoding="utf-8")
        for other in self.HELPERS:
            if other != SKILL.name:
                self.assertIn(other, description, f"설명이 {other} 로 보낸다")
                self.assertIn(other, not_done, f"「하지 않는 일」이 {other} 로 보낸다")
        for setup in ("stay-setup-guide", "stay-setup-run"):
            self.assertIn(setup, description)
            self.assertIn(setup, not_done)
        self.assertIn("프로모션 할인 값은 stay-promotion-change 가 맡는다.", description)
        self.assertIn("stay-promotion-change", not_done)
        self.assertNotIn("프로모션 할인은 다루지 않는다", description)
        for helper in self.HELPERS:
            page = (SKILL.parent / helper / "references" / "not-done.md").read_text(encoding="utf-8")
            self.assertIn(self.PROMO, page, f"{helper} 의 「하지 않는 일」이 같은 한 문장으로 답한다")


if __name__ == "__main__":
    unittest.main()
