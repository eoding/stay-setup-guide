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
        self.assertEqual(len(keys), 7, keys)
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


    def test_every_preparation_step_uses_only_what_an_earlier_step_set_up(self):
        """H4 — 일마다 새 작업 폴더(work)에서 시작하고, look 을 부르고 · 명령으로 묶고 · 명령이 말한 조각을 받은 뒤에 목록을 탭의
        호텔로 본다(그 차례가 명령이 바라는 차례다). --look 을 받는 명령을 한 곳에서 다 댄다."""
        prep = self.skill[self.skill.index("## 준비"):self.skill.index("## 읽기")]
        self.assertLess(prep.index("price_change.py work"), prep.index("<작업>/"), "작업 폴더를 만든 뒤에 그 안에 저장한다")
        self.assertLess(prep.index("stayPrice.look()"), prep.index("price_change.py look --answers"))
        self.assertLess(prep.index("price_change.py look --answers"), prep.index("`refetch`"), "명령이 받을 조각을 말한다")
        self.assertLess(prep.index("`refetch`"), prep.index("price_change.py list --look"), "목록은 탭의 호텔을 안 뒤에")
        self.assertIn("같은 대화의 두 번째 요청도", prep)
        said = prep[prep.index("`--look` 으로 받는 명령은"):].split("\n", 1)[0]
        for name, flags in commands().items():
            if "--look" in flags:
                self.assertIn(f"`{name}`", said, f"--look 을 받는 {name} 을 준비에서 댄다")

    def test_p5_the_price_view_says_that_it_leaves_a_ledger_entry(self):
        """P5 — 「지금 가격 보기」도 장부에 한 줄(지금 상태 저장)을 남긴다고 안내문이 말한다(도우미가 말하는 문장은 그 번호를 댄다)."""
        job = section(self.skill, "## 1. 지금 가격 보기")
        self.assertIn("보기도 장부에 「지금 상태 저장」 한 줄을 남긴다", job)
        self.assertIn("장부 S번에 적어 두었습니다", job)

    def test_a_person_asking_what_changed_since_a_saved_state_reaches_compare_from_skill_md(self):
        """H4 — 「아침에 저장해 둔 것과 뭐가 달라졌어?」는 요금표 참고 파일을 거치지 않고 SKILL.md 에서 compare 에 닿는다."""
        job = section(self.skill, "## 6. 저장해 둔 상태와 견주기")
        self.assertIn("6 저장해 둔 상태와 견주기", self.skill.split("## 반드시 지킬 것")[0], "하는 일 목록에 있다")
        for said in ("아침에 저장해 둔 것과 뭐가 달라졌어?", "`compare`", "](references/compare.md)"):
            self.assertIn(said, job)

    def test_the_spoken_compare_sentences_name_the_helper_s_own_changes_and_are_not_only_about_a_season_refill(self):
        """K1 — 견주기를 말하는 문장은 시즌 다시 채우기만의 것이 아니다: 저장한 뒤 도우미가 바꾼 칸은 그 기록을, 나머지는 장부에 없는
        변화를 말하고, 손입력 이야기는 장부에 없는 변화가 있을 때만 한다."""
        talk = (SKILL / "references" / "compare.md").read_text(encoding="utf-8")
        talk = talk[talk.index("4. **말하기.**"):talk.index("5. **되돌리기")]
        for said in ("`written_by`", "<`change_id`>번 <`what`>", "`counts.outside`", "장부에 없는 변화", "0 이면 이 말은 하지 않는다"):
            self.assertIn(said, talk)
        self.assertNotIn("시즌", talk.replace("시즌 채우기", ""), "시즌 다시 채우기를 전제로 말하지 않는다")

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

    def test_n5_compare_and_skill_md_give_one_folder_rule_and_one_one_word_question(self):
        """N5 — 견주기 뒤의 되돌리기: 준비의 폴더 규칙과 compare.md 5 가 같은 말을 하고, 변경 되돌리기와 저장 상태로 되돌리기 사이의
        고름은 한 낱말로 답하는 물음 하나다(SKILL.md 「4」, compare.md 5 가 그것을 묻는다)."""
        prep = self.skill[self.skill.index("## 준비"):self.skill.index("## 읽기")]
        self.assertIn("그 일의 폴더를 그대로 쓰는 때는 둘뿐이다 — 방금 멈춘 변경을 이어서 할 때, 견주기 바로 다음에 되돌릴 때(compare.md 5)", prep)
        compare = (SKILL / "references" / "compare.md").read_text(encoding="utf-8")
        step = compare[compare.index("5. **되돌리기(원할 때만).**"):]
        for said in ("이 작업 폴더에서 한다", "새 작업 폴더를 만들지 않는다", "「4. 되돌리기」의 한 낱말 물음"):
            self.assertIn(said, step)
        ask = section(self.skill, "## 4. 되돌리기")
        self.assertIn("'변경'이라고 하시면", ask)
        self.assertIn("'저장'이라고 하시면", ask)
        self.assertIn("어느 쪽으로 할까요?", ask)
        self.assertNotIn("이 변경만 되돌릴까요", self.skill + compare, "두 줄을 읽어 주는 긴 물음은 없앴다")

class TrialSevenDocsTest(unittest.TestCase):
    """T6 · T7 — 시운전 7 의 빈틈 하나에 답 하나, 도우미가 그때 읽는 자리에."""

    def setUp(self):
        self.skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.stopped = (SKILL / "references" / "stopped.md").read_text(encoding="utf-8")

    def test_the_saves_of_one_change_run_back_to_back_and_fifteen_idle_minutes_stop_it(self):
        apply = section(self.skill, "## 적용하기 — 바꾸기·되돌리기 공통")
        self.assertIn("사이에 다른 일 없이 잇달아 한다 — 15분 동안 아무 일이 없으면 변경이 멈추고 stopped.md 로 간다", apply)
        for skill, place in (("stay-addon-price-change", "SKILL.md"), ("stay-charge-change", "references/apply.md")):
            self.assertIn("사이에 다른 일 없이 잇달아", (SKILL.parent / skill / place).read_text(encoding="utf-8"), skill)

    def test_rolling_back_what_was_saved_after_a_stop_uses_a_new_work_folder_and_skips_the_stopped_notice(self):
        step = self.stopped[self.stopped.index("## 4. 된 것까지 되돌리기"):self.stopped.index("## 5.")]
        self.assertIn("새 작업 폴더에서 한다", step)
        self.assertIn("멈춘 변경 알림은 하지 않는다", step)
        self.assertIn("(된 것까지 되돌리기는 4 — 새 작업 폴더)", self.stopped)
        prep = self.skill[self.skill.index("5. **장부 보기.**"):self.skill.index("## 읽기")]
        self.assertIn("(지금 다루는 그 변경이면 하지 않는다)", prep)

    def test_a_view_request_that_points_back_is_filled_from_the_conversation_and_saved_with_the_read_range(self):
        job = section(self.skill, "## 1. 지금 가격 보기")
        self.assertIn("\"그 이틀 두 객실\"처럼 앞 대화를 가리키면 거기서 채우고 무엇으로 채웠는지 말한다", job)
        self.assertIn("\"응 저장해\" · \"그 이틀 두 객실\"처럼 무엇을 적었는지 알 수 없으면 읽은 범위를 쓴다", job)


class TrialEightDocsTest(unittest.TestCase):
    """U1 · U4 · U5 · U6 — 시운전 8 의 빈틈 하나에 답 하나, 도우미가 그때 읽는 자리에. 세 도우미가 같은 말을 한다."""

    def read(self, skill: str, place: str) -> str:
        return (SKILL.parent / skill / place).read_text(encoding="utf-8")

    def test_a_rollback_is_undone_like_a_change_in_every_document(self):
        """검토 3 — 되돌리기도 바꾸기처럼 되돌린다. 멈춘 되돌리기의 「된 것까지 되돌리기」는 된 저장을 되돌리기 전 값으로 되돌리고(페이지와
        같은 말), 되돌리기를 되돌려 달라는 말은 같은 길로 하며, 되돌리기를 되돌리면 먼저 `undoing` 을 그대로 말한다. 세 도우미의 어느
        문서도 되돌리기를 다시 되돌리지 않는다고 하지 않는다."""
        for skill in ("stay-price-change", "stay-addon-price-change", "stay-charge-change"):
            stopped = self.read(skill, "references/stopped.md")
            self.assertIn("멈춘 것이 되돌리기면", stopped, skill)
            self.assertIn("되돌리기 전 값", stopped, skill)
            self.assertIn("`undoing`", self.read(skill, "references/commands.md"), skill)
            for path in sorted((SKILL.parent / skill).rglob("*.md")):
                self.assertNotIn("다시 되돌리지 않", path.read_text(encoding="utf-8"), path)
        for skill in ("stay-price-change", "stay-charge-change"):
            rollback = self.read(skill, "references/rollback.md")
            self.assertIn("**되돌리기를 되돌려 달라면.** \"방금 되돌린 것 다시 되돌려줘\"처럼", rollback, skill)
            self.assertIn("짧은 답의 `undoing` 이 있으면", rollback, skill)
        self.assertIn("`undoing` 이 있으면 그 말부터.", self.read("stay-addon-price-change", "SKILL.md"))

    def test_u1_the_value_a_check_read_is_told_with_its_time_never_as_now(self):
        stopped = self.read("stay-price-change", "references/stopped.md")
        step = stopped[stopped.index("## 2."):stopped.index("## 3.")]
        self.assertIn("「미리보기 때 … · ○시 ○분에 다시 읽으니 … · 그 사이 ERP 에서 바뀜 · 넣지 않음」", step)
        self.assertIn("「지금」이라고 하지 않는다", step)
        self.assertNotIn("지금 …", stopped)

    def test_u4_the_cause_the_moved_sentence_said_is_not_said_again_from_why(self):
        step = self.read("stay-price-change", "references/stopped.md")
        step = step[step.index("**미리보기 뒤에 칸이 바뀌어 멈췄을 때**"):step.index("## 3.")]
        self.assertIn("`why` 의 「…미리보기 때 읽은 값과 다릅니다」는 다시 말하지 않는다", step)
        rule = next(line for line in step.splitlines() if line.startswith("- `can_continue` 가 false 면"))
        self.assertIn("다시 말하지 않고 남은 까닭만 전한다", rule, "까닭을 넘기라는 규칙이 그 예외를 말한다")

    def test_u5_the_rollback_preview_ends_with_the_number_of_saves_and_asks_for_the_word(self):
        for skill, place, start in (("stay-price-change", "references/rollback.md", "\n3. "),
                                    ("stay-charge-change", "references/rollback.md", "\n3. "),
                                    ("stay-addon-price-change", "SKILL.md", "\n3. `python3 scripts/addon_change.py render rollback")):
            text = self.read(skill, place)
            step = text[text.index(start):]
            step = step[:step.index("\n4. ")]
            self.assertIn("저장 횟수(`saves`)", step, skill)
            self.assertIn("\"맞으면 '되돌려'라고 해 주세요.\"", step, skill)

    def test_u6_the_add_on_and_charge_helpers_skip_the_stopped_notice_for_the_change_being_dealt_with(self):
        for skill in ("stay-addon-price-change", "stay-charge-change"):
            skill_md = self.read(skill, "SKILL.md")
            prep = skill_md[skill_md.index("5. **장부 보기.**"):skill_md.index("## 읽기")]
            self.assertIn("(지금 다루는 그 변경이면 하지 않는다)", prep, skill)
            self.assertIn("「준비」 5 의 멈춘 변경 알림은 하지 않는다(지금 다루는 그 변경이다)", self.read(skill, "references/stopped.md"), skill)


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
        steps = ["「2. 지금 상태만 저장」", "[compare.md](compare.md)", "restore --saved S"]
        self.assertEqual([step for step in steps if step in way], steps, "저장 → 다시 읽어 견주기(compare.md) → 되돌리기")
        self.assertLess(way.index(steps[0]), way.index(steps[1]))
        self.assertLess(way.index(steps[1]), way.index(steps[2]))
        compare = (SKILL / "references" / "compare.md").read_text(encoding="utf-8")
        steps = ["read-calls --record S", "compare --saved S", "render compare", "restore --saved S"]
        self.assertEqual([step for step in steps if step in compare], steps, "다시 읽기 → 견주기 → 페이지 → 되돌리기")
        self.assertEqual(sorted(steps, key=compare.index), steps)
        self.assertIn("시즌 창에는 다시 채운 입력값이 그대로 보이고, 캘린더의 날짜별 값만 저장해 둔 값으로 돌아갑니다", way)

    def test_the_child_percentage_question_reads_as_a_discount_and_names_every_guest_combination_it_covers(self):
        """K4 — 시운전의 물음 「'3박 이상 -10%'를 … 칸 전체에 하면」은 할인으로 읽히지 않았고, 한 답이 여러 인원 조합에 가는데 하나만 댔다."""
        bullet = self.sheet[self.sheet.index("**아동이 든 줄의 퍼센트는 묻는다.**"):].split("\n", 1)[0]
        for said in ("'3박 이상 10% 할인'", "칸 전체를 10% 깎으면", "성인 몫 <`adult`> 만 10% 깎고", "인원 조합을 모두 댄다",
                     "성인 2 + 아동 1 · 성인 1 + 아동 1 칸"):
            self.assertIn(said, bullet)

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
