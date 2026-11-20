"""안내문(SKILL.md 와 references/ 의 파일 전부)에 적힌 명령 · 플래그 · 페이지 호출이 코드에 그 이름으로 있고, 새 요금표 길의
예 · 문장 · 읽기 값이 코드와 같다. 새 요금표 길은 sheet.md 에 있고 SKILL.md 는 그곳을 가리키며 놓치면 안 되는 두 규칙만 둔다.

SKILL.md 는 담당자의 Claude 가 쓸 때마다 통째로 읽는다(Z9). 그래서 크기를 지키고, 가끔만 필요한 갈래(멈춘 변경 · 빨간 줄 ·
요금표 · 막힐 때 · 하지 않는 일)는 references/ 에 두고 SKILL.md 의 가리킴이 여는 때와 그때 놓치면 안 되는 규칙을 말한다.
「반드시 지킬 것」의 규칙 문장은 하나도 빠지지 않는다(시작한 판의 목록 — tests/fixtures/must-keep-rules.txt).

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

REFERENCES = sorted((SKILL / "references").glob("*.md"))
DOCS = [SKILL / "SKILL.md", *REFERENCES]
SKILL_BUDGET = 25_000          # SKILL.md 의 바이트 수 상한(UTF-8)
MUST_KEEP = SKILL / "tests" / "fixtures" / "must-keep-rules.txt"
# 가리킴이 그 자리에서 다시 말해야 하는 규칙 — 그 파일을 가리키는 줄 가운데 하나에 이 말이 있다
REMINDERS = {
    "stopped.md": "다시 읽어 `check` 가 이어서 해도 된다고 하기 전에는 이어서 하지 않는다",
    "failures.md": "같은 저장을 두 번 누르지 않는다",
    "red-lines.md": "\"적용\"이라고만 하면 저장하지 않는다",
}


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

    def test_paths_handed_to_a_command_in_the_instructions_are_quoted(self):
        # 기록 폴더 · 작업 폴더 · 페이지 이름에는 빈칸과 「·」가 있다 — 따옴표 없이 넘긴 경로는 셸이 쪼갠다(Y7)
        flags = r"--(?:out|snapshot|request|plan|calls|answers|resolutions|result|sheet|look|earlier)"
        for doc in DOCS:
            for bit in code_bits(doc.read_text(encoding="utf-8")):
                for found in re.finditer(rf"({flags}) (\S+)", bit):
                    if "<" in found.group(2):
                        self.assertTrue(found.group(2).startswith('"'), f"{doc.name}: {found.group(0)}")

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
        for doc in (SKILL / "references" / "stopped.md", SKILL / "references" / "commands.md"):
            text = doc.read_text(encoding="utf-8")
            self.assertIn(minutes, text, f"{doc.name}: 멈춤으로 보는 시간")
            for cause in CAUSES:
                self.assertIn(f"`{cause}`", text, f"{doc.name}: check 의 cause {cause}")

    def test_page_md_names_every_storage_key_the_page_and_loader_write_and_no_other(self):
        scripts = SKILL / "scripts" / "page"
        keys = {key for name in ("stay_price.js", "stay_price_loader.js")
                for key in re.findall(r"'(stayPrice[A-Z]\w*)'", (scripts / name).read_text(encoding="utf-8"))}
        self.assertEqual(len(keys), 5, keys)
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


def section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start:] if end < 0 else text[start:end]


def sentences(line: str) -> list[str]:
    """규칙 한 줄 → 문장들(「…다.」 로 끝나는 곳에서 자른다)."""
    return [part for part in re.split(r"(?<=다\.)\s+", line.strip()) if part]


class SkillBudgetTest(unittest.TestCase):
    """Z9 — SKILL.md 는 크기 안이고, 모든 참고 파일을 가리키며, 「반드시 지킬 것」의 규칙 문장을 하나도 잃지 않는다."""

    def setUp(self):
        self.skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    def test_skill_md_fits_the_budget(self):
        size = len(self.skill.encode("utf-8"))
        self.assertLessEqual(size, SKILL_BUDGET, f"SKILL.md 가 {size:,}바이트 — 가끔만 필요한 갈래는 references/ 로 옮긴다")

    def test_every_reference_file_is_pointed_to_from_skill_md(self):
        self.assertGreaterEqual(len(REFERENCES), 7)
        for path in REFERENCES:
            self.assertIn(f"](references/{path.name})", self.skill, f"SKILL.md 가 {path.name} 를 가리키지 않는다")

    def test_the_pointers_repeat_the_rule_that_must_not_be_missed_there(self):
        lines = self.skill.splitlines()
        for name, rule in REMINDERS.items():
            pointing = [line for line in lines if f"](references/{name})" in line]
            self.assertTrue(pointing, name)
            self.assertTrue(any(rule in line for line in pointing), f"{name} 를 가리키는 줄이 「{rule}」을 말하지 않는다")

    def test_no_rule_sentence_of_the_must_keep_list_disappeared(self):
        kept = section(self.skill, "## 반드시 지킬 것")
        rules = [line for line in MUST_KEEP.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(rules), 14, "시작한 판의 「반드시 지킬 것」은 14줄")
        for rule in rules:
            for sentence in sentences(rule):
                self.assertIn(sentence, kept, f"「반드시 지킬 것」에서 빠진 문장: {sentence}")


class SheetDocsTest(unittest.TestCase):
    """새 요금표 길(S7 · V6) — 안내문의 요금표 예, 덮기 한 문장, 넣지 않는 것의 종류, 읽기 값이 코드와 같다."""

    def setUp(self):
        self.skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.commands = (SKILL / "references" / "commands.md").read_text(encoding="utf-8")
        self.sheet = (SKILL / "references" / "sheet.md").read_text(encoding="utf-8")

    def test_v6_the_sheet_flow_lives_in_sheet_md_and_skill_md_keeps_a_pointer_and_the_two_rules(self):
        section = self.skill[self.skill.index("## 5. 새 요금표로 맞추기"):]
        section = section[:section.index("\n## ", 1)]
        self.assertIn("[references/sheet.md](references/sheet.md)", section)
        self.assertIn("셈은 명령이 한다", section, "도우미는 셈하지 않는다")
        self.assertIn(SEASON_REFILL_NOTE, section, "시즌 [가격] 덮기 한 문장")
        self.assertLess(len(section), 1500, "SKILL.md 에는 언제 여는지와 두 규칙만")
        for step in ("**요금표 파일 쓰기.**", "**읽을 범위 · 나누기.**", "sheet --sheet"):
            self.assertNotIn(step, self.skill)
            self.assertIn(step, self.sheet)

    def test_the_sheet_example_in_commands_md_is_a_sheet_the_command_takes(self):
        section = self.commands[self.commands.index("### 요금표 (`kind: sheet`)"):]
        sheet = decode_sheet(json.loads(re.search(r"```json\n(.*?)```", section, re.S).group(1)))
        check = SheetCheck(sheet, tuple(dict.fromkeys((line.room, line.rate_plan) for line in sheet.lines)))
        self.assertTrue(check.cells)
        self.assertEqual({row.occupancy for line in sheet.lines for row in line.rows}, {"A2", "A3", "A2C1"},
                         "아동이 든 줄은 요금표의 말대로 성인 · 아동 수만 적는다(F1 — 밴드 코드는 명령이 맞춘다)")

    def test_the_instructions_say_the_season_refill_sentence_the_pages_say(self):
        self.assertGreaterEqual(self.sheet.count(SEASON_REFILL_NOTE), 2, "두 길을 말할 때와 미리보기를 말할 때")
        self.assertNotIn("아직 못 합니다", self.sheet + (SKILL / "references" / "not-done.md").read_text(encoding="utf-8"),
                         "(가)는 「아직 못 함」이 아니라 저장 · 견주기 · 되돌리기의 안전망이다(G1)")
        self.assertNotIn("새 요금표로 통째 바꾸기는 아직 못 한다", self.skill + self.sheet)

    def test_g1_the_season_refill_way_saves_compares_and_restores_and_says_why_the_helper_does_not_fill(self):
        way = section(self.sheet, "## (가) 시즌 원판 바꾸기")
        why = re.search(r"도우미는 시즌을 직접 채우지 않습니다 — [^\"]+때문입니다\.", way)
        self.assertIsNotNone(why, "시즌을 채우지 않는다는 것과 그 까닭을 한 문장으로")
        self.assertIn(why.group(0), (SKILL / "references" / "not-done.md").read_text(encoding="utf-8"), "「하지 않는 것」도 같은 문장")
        steps = ["「2. 지금 상태만 저장」", "read-calls --record S", "compare --saved S", "render compare", "restore --saved S"]
        self.assertEqual([step for step in steps if step in way], steps, "저장 → 다시 읽기 → 견주기 → 되돌리기")
        self.assertLess(way.index(steps[0]), way.index(steps[2]))
        self.assertLess(way.index(steps[2]), way.index(steps[4]))
        self.assertIn("시즌 창에는 다시 채운 입력값이 그대로 보이고, 캘린더의 날짜별 값만 저장해 둔 값으로 돌아갑니다", way)

    def test_commands_md_names_every_kind_of_gap(self):
        table = self.commands[self.commands.index("## 넣지 않는 것"):]
        table = table[:table.index("\n## ", 1)]
        self.assertEqual(set(re.findall(r"^\| `(\w+)` \|", table, re.M)) - {"kind"}, set(GAP_KINDS))   # 머리 줄은 `kind`

    def test_the_reading_cost_in_the_instructions_is_what_the_code_does(self):
        hotel, year = {"id": "1", "name": "호텔"}, [(date(2027, 1, 1) + timedelta(days=n)).isoformat() for n in range(365)]
        per_pair = len(read_calls(hotel, "오퍼", [("객실", "요금제")], year))
        probes = len(reserved_probes(hotel, "오퍼", [("객실", "요금제")], year))
        most = max(n for n in range(1, PAGE_KEEPS + 1) if n * per_pair + probes <= PAGE_KEEPS)
        self.assertEqual((per_pair, probes, most), (2, 1, 99), "1년이면 객실 · 요금제 99개까지 한 번에 읽는다")
        self.assertIn(f"가격 읽기(`readPair`) {per_pair}번({READ_SPAN}일에 한 번)", self.sheet)
        self.assertIn(f"예약 있는 날 읽기(`readReserved`) {probes}번({ERP_MAX_DAYS}일에 한 번", self.sheet)
        self.assertIn(f"합쳐 {PAGE_KEEPS}번까지", self.sheet)
        self.assertIn(f"객실 · 요금제 {most}개까지", self.sheet)
        for words in (f"{READ_SPAN}일에 한 번", f"{ERP_MAX_DAYS}일에 한 번", f"합쳐 {PAGE_KEEPS}번까지", "`KEEP_BODIES`"):
            self.assertIn(words, self.commands)

    def test_every_count_of_kept_screens_in_the_instructions_is_what_the_page_keeps(self):
        said = {doc.name: [int(n) for n in re.findall(r"조각[을이]? (\d+)개|(\d+)개 조각|(?<=합쳐 )(\d+)(?=번까지)", doc.read_text(encoding="utf-8"))
                           for n in n if n] for doc in DOCS}
        for name in ("commands.md", "page.md", "sheet.md"):
            self.assertTrue(said[name], f"{name} 가 페이지가 두는 조각 수를 말한다")
        self.assertEqual({n for numbers in said.values() for n in numbers}, {PAGE_KEEPS}, said)


if __name__ == "__main__":
    unittest.main()
