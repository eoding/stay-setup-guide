#!/usr/bin/env python3
"""render_screen_guide.py 시험 — 화면 사전 → 직원용 「화면 안내」 HTML 한 장.

이 문서는 사람이 손대지 않고 사전에서만 만들어진다. 그래서 지켜야 할 것은 넷이다.

1. 사전의 머리 숫자(`meta.screen_count` · `meta.field_count`)와 그린 수가 같다 —
   다르면 사전이 바뀐 뒤 문서를 다시 만들지 않은 것이다.
2. 사전의 탭·화면·여는 길·카드가 하나도 빠지지 않는다.
3. 같은 사전이면 몇 번을 돌려도 **바이트까지 같은** 파일이 나온다(날짜를 찍지 않는다).
4. 바깥으로 나가는 요청이 하나도 없다 — 인터넷 없이 여는 단일 파일이다.
5. `--impact` 를 주면 칸마다 「웹에 나오는 곳」·「효과」 가 붙고, 안 주면 예전과 같은 바이트다.
   사전과 지도의 칸이 한 줄이라도 어긋나면 문서를 만들지 않는다.

실행:
    python3 -m pytest -q skills/stay-setup-guide/tests/test_render_screen_guide.py
    python3 -m unittest discover -s skills/stay-setup-guide/tests -v
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.normpath(os.path.join(HERE, os.pardir))
SCRIPTS = os.path.join(SKILL, "scripts")
RENDER = os.path.join(SCRIPTS, "render_screen_guide.py")
DICTIONARY = os.path.join(SKILL, "references", "screen-dictionary.json")
sys.path.insert(0, SCRIPTS)

import render_screen_guide as rsg  # noqa: E402


def load_dict():
    with open(DICTIONARY, encoding="utf-8") as fp:
        return json.load(fp)


def render_once(data=None, font_b64=None):
    return rsg.render_guide(data or load_dict(), font_b64, rsg.skill_version())


def section_of(page, screen_id):
    """그 화면의 `<section>` 덩어리만 잘라 돌려준다."""
    found = re.search(
        r'<section class="screen" id="screen-%s">.*?</section>' % re.escape(screen_id),
        page,
        re.S,
    )
    return found.group(0) if found else ""


def tag_balance(page):
    """여닫는 태그가 맞는지 — (어긋난 자리, 안 닫힌 태그)."""
    from html.parser import HTMLParser

    void = {
        "meta", "br", "hr", "img", "link", "input", "area",
        "base", "col", "embed", "source", "track", "wbr",
    }

    class Balance(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = []
            self.errors = []

        def handle_starttag(self, tag, attrs):
            if tag not in void:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            if tag in void:
                return
            if not self.stack:
                self.errors.append("여는 태그 없이 </%s>" % tag)
            elif self.stack[-1] != tag:
                self.errors.append("</%s> 자리에 <%s>" % (tag, self.stack[-1]))
            else:
                self.stack.pop()

    parser = Balance()
    parser.feed(page)
    return parser.errors, parser.stack


#: 작은 가짜 사전 — 사전 구조가 바뀌어도 렌더러가 최소 한 벌은 그려 내는지 본다.
SYNTHETIC = {
    "meta": {
        "generated_on": "2026-01-02",
        "screen_count": 2,
        "field_count": 3,
        "erp_baseline": "시험용 배포판 화면 기준",
    },
    "tabs": ["시험탭", "빈탭"],
    "screens": [
        {
            "id": "synth-one",
            "name": "시험 화면 하나",
            "opens": ["편집 화면 탭 `시험탭`", "[시험 버튼]"],
            "cards": ["시험 카드"],
            "blocks": [
                {
                    "name": "",
                    "fields": [
                        {
                            "label": "이름",
                            "kind": "텍스트",
                            "required": True,
                            "options": None,
                            "options_note": None,
                            "format": "100자까지",
                            "help": "그대로 적습니다.",
                            "checkbox_text": None,
                            "visible_when": "",
                            "same_row_as": None,
                        },
                        {
                            "label": "고르기",
                            "kind": "선택",
                            "required": False,
                            "options": ["하나", "둘"],
                            "options_note": "이 호텔에 만든 것만",
                            "format": "",
                            "help": "",
                            "checkbox_text": None,
                            "visible_when": "「이름」을 채운 뒤",
                            "same_row_as": None,
                        },
                    ],
                },
                {
                    "name": "반복 블록",
                    "fields": [
                        {
                            "label": "줄 넣기",
                            "kind": "반복 행",
                            "required": False,
                            "options": None,
                            "options_note": None,
                            "format": "",
                            "help": "",
                            "columns": ["왼쪽", "오른쪽"],
                            "column_options": [["가", "나"]],
                            "columns_note": "첫 열 이름은 위 칸이 정한다.",
                            "checkbox_groups": [{"group": "묶음", "items": ["가", "나"]}],
                            "checkbox_text": None,
                            "visible_when": "",
                            "same_row_as": None,
                        }
                    ],
                },
            ],
            "buttons": ["추가", "삭제"],
            "notes": ["메모 한 줄 — `코드` 와 **굵게** 가 섞여 있다."],
        },
        {
            "id": "synth-two",
            "name": "탭 밖 화면 하나",
            "opens": ["왼쪽 메뉴 `자유여행` → `상품관리`"],
            "cards": [],
            "blocks": [],
            "buttons": [],
            "notes": [],
        },
    ],
    "not_covered": ["가짜 사전이라 담지 않은 것."],
}


class ScreenGuideCountsTest(unittest.TestCase):
    """사전의 머리 숫자와 그린 수가 같아야 한다."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_dict()
        cls.page, cls.stats = render_once(cls.data)

    def test_screen_count_matches_meta(self):
        meta = self.data["meta"]["screen_count"]
        self.assertEqual(self.stats["screens"], meta)
        self.assertEqual(len(re.findall(r'<section class="screen"', self.page)), meta + self.stats.get('supplemental_screens', 0))

    def test_field_count_matches_meta(self):
        meta = self.data["meta"]["field_count"]
        self.assertEqual(self.stats["fields"], meta)
        self.assertEqual(len(re.findall(r'<tr class="field">', self.page)), meta + self.stats.get('supplemental_fields', 0))

    def test_counts_are_printed_on_the_page(self):
        meta = self.data["meta"]
        self.assertIn(
            "화면 %d개 · 입력 칸 %d개" % (meta["screen_count"], meta["field_count"]),
            self.page,
        )

    def test_stamp_carries_the_counts(self):
        meta = self.data["meta"]
        stamp = re.search(r'<meta name="stay-screen-guide" content="([^"]+)">', self.page)
        self.assertIsNotNone(stamp, "도장(<meta name=stay-screen-guide>)이 없다")
        self.assertEqual(
            stamp.group(1),
            "v1;screens=%d;fields=%d;generated=%s"
            % (meta["screen_count"], meta["field_count"], meta["generated_on"]),
        )

    def test_baseline_and_generated_on_are_shown(self):
        meta = self.data["meta"]
        self.assertIn(rsg.inline(meta["erp_baseline"]), self.page)
        self.assertIn(meta["generated_on"], self.page)


class ScreenGuideContentTest(unittest.TestCase):
    """사전의 탭·화면·여는 길·카드·메모가 빠짐없이 실려야 한다."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_dict()
        cls.page, _ = render_once(cls.data)
        cls.toc = re.search(r'<nav class="toc">.*?</nav>', cls.page, re.S).group(0)

    def test_every_tab_appears_in_toc(self):
        for tab in self.data["tabs"]:
            self.assertIn(rsg.inline(tab), self.toc, f"차례에 탭 `{tab}` 이 없다")

    def test_toc_keeps_dictionary_tab_order(self):
        positions = [self.toc.index(rsg.inline(t)) for t in self.data["tabs"]]
        self.assertEqual(positions, sorted(positions), "차례의 탭 순서가 사전과 다르다")

    def test_toc_links_reach_every_screen(self):
        anchors = set(re.findall(r'<section class="screen" id="([^"]+)">', self.page))
        links = set(re.findall(r'<a href="#(screen-[^"]+)">', self.toc))
        self.assertEqual(links, anchors)
        self.assertEqual(len(anchors), self.data["meta"]["screen_count"] + len(self.data.get('supplemental_screens', [])))

    def test_every_screen_has_name_opens_and_cards(self):
        for screen in self.data["screens"]:
            resolved = rsg.resolve_screen(screen, self.data)
            block = section_of(self.page, screen["id"])
            self.assertTrue(block, f'화면 `{screen["id"]}` 의 절이 없다')
            self.assertIn(rsg.inline(resolved["name"]), block)
            for opens in resolved.get("opens") or []:
                self.assertIn(rsg.inline(opens), block, f'{screen["id"]}: 여는 길이 빠졌다')
            for card in resolved.get("cards") or []:
                self.assertIn(rsg.inline(card), block, f'{screen["id"]}: 카드가 빠졌다')

    def test_every_field_label_appears_in_its_screen(self):
        for screen in self.data["screens"]:
            resolved = rsg.resolve_screen(screen, self.data)
            block = section_of(self.page, screen["id"])
            for _, field in rsg.field_rows(resolved):
                self.assertIn(
                    rsg.inline(field["label"]),
                    block,
                    f'{screen["id"]}: 칸 `{field["label"]}` 이 빠졌다',
                )

    def test_screen_notes_are_carried(self):
        for screen in self.data["screens"]:
            resolved = rsg.resolve_screen(screen, self.data)
            block = section_of(self.page, screen["id"])
            for note in resolved.get("notes") or []:
                self.assertIn(rsg.inline(note), block, f'{screen["id"]}: 메모가 빠졌다')

    def test_validation_reference_row_is_resolved_to_the_canonical_screen(self):
        block = section_of(self.page, "validation")
        self.assertIn(rsg.inline("사유"), block)
        for rule in self.data["validation"]["rules"]:
            self.assertIn(rsg.inline(rule["message"]), block)
        # 참조 줄의 사전 구조 메모는 싣지 않는다.
        self.assertNotIn("최상위 <code>validation</code> 키다", block)

    def test_howto_items_are_present(self):
        howto = re.search(r'<section class="howto">.*?</section>', self.page, re.S)
        self.assertIsNotNone(howto, "「화면 읽는 법」 절이 없다")
        body = howto.group(0)
        self.assertIn("화면 읽는 법", body)
        self.assertLessEqual(len(rsg.HOWTO_ITEMS), 8)
        for title, text in rsg.HOWTO_ITEMS:
            self.assertIn(rsg.inline(title), body)
            self.assertIn(rsg.inline(text), body)

    def test_not_covered_list_is_at_the_end(self):
        section = re.search(r'<section class="not-covered".*?</section>', self.page, re.S)
        self.assertIsNotNone(section, "「이 안내에 없는 것」 절이 없다")
        for item in self.data["not_covered"]:
            self.assertIn(rsg.inline(item), section.group(0))
        self.assertLess(self.page.index('class="not-covered"'), self.page.index("<footer>"))

    def test_footer_carries_skill_version_and_regen_command(self):
        footer = re.search(r"<footer>.*?</footer>", self.page, re.S).group(0)
        version = rsg.skill_version()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertIn(version, footer)
        self.assertIn(rsg.inline(rsg.REGEN_COMMAND), footer)

    def test_field_tables_have_the_five_columns(self):
        head = (
            "<thead><tr><th>칸</th><th>종류</th><th>필수</th>"
            "<th>선택지 / 형식</th><th>도움말</th></tr></thead>"
        )
        self.assertIn(head, self.page)


class ScreenGuideSelfContainedTest(unittest.TestCase):
    """바깥으로 나가는 요청이 없어야 한다 — 인터넷 없이 여는 단일 파일이다."""

    @classmethod
    def setUpClass(cls):
        cls.page, _ = render_once()

    def test_no_external_script_or_stylesheet(self):
        self.assertNotIn("<script", self.page)
        self.assertNotIn("<link", self.page)

    def test_no_http_references_at_all(self):
        self.assertEqual(re.findall(r"https?://", self.page), [])

    def test_html_shell_is_complete(self):
        self.assertTrue(self.page.startswith("<!DOCTYPE html>"))
        self.assertIn('<html lang="ko">', self.page)
        self.assertIn('<meta charset="utf-8">', self.page)
        self.assertIn('<meta name="viewport"', self.page)
        self.assertIn("<title>ERP Stay 화면 안내</title>", self.page)
        self.assertTrue(self.page.rstrip().endswith("</html>"))

    def test_tags_are_balanced(self):
        errors, left_open = tag_balance(self.page)
        self.assertEqual(errors, [])
        self.assertEqual(left_open, [])

    def test_font_is_embedded_as_data_url_when_given(self):
        page, _ = render_once(font_b64="QUJD")
        self.assertIn("@font-face{", page)
        self.assertIn("url(data:font/woff2;base64,QUJD) format(\"woff2\")", page)
        self.assertEqual(re.findall(r"https?://", page), [])

    def test_print_rules_break_pages_before_each_screen(self):
        self.assertIn("@media print{", self.page)
        self.assertIn("section.screen{page-break-before:always", self.page)

    def test_phone_width_rules_exist(self):
        self.assertIn("@media (max-width: 640px){", self.page)
        self.assertIn('content:attr(data-label)', self.page)
        for label in ("칸", "종류", "필수", "선택지 / 형식", "도움말"):
            self.assertIn('data-label="%s"' % label, self.page)


class ScreenGuideEscapingTest(unittest.TestCase):
    def test_inline_escapes_html_then_restores_markup(self):
        self.assertEqual(rsg.inline("a < b & c"), "a &lt; b &amp; c")
        self.assertEqual(rsg.inline("`코드`"), "<code>코드</code>")
        self.assertEqual(rsg.inline("**굵게**"), "<strong>굵게</strong>")
        self.assertEqual(rsg.inline("<script>x</script>"), "&lt;script&gt;x&lt;/script&gt;")
        self.assertEqual(rsg.inline(""), "")
        self.assertEqual(rsg.inline(None), "")

    def test_a_dictionary_value_with_angle_brackets_is_escaped(self):
        data = json.loads(json.dumps(SYNTHETIC))
        data["screens"][0]["notes"] = ['<img src=x onerror="boom">']
        page, _ = rsg.render_guide(data)
        self.assertNotIn("<img", page)
        self.assertIn("&lt;img src=x onerror=&quot;boom&quot;&gt;", page)


class ScreenGuideDeterminismTest(unittest.TestCase):
    def test_two_renders_are_byte_identical(self):
        first, _ = render_once()
        second, _ = render_once()
        self.assertEqual(first, second)

    def test_cli_writes_the_same_bytes_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            one = os.path.join(tmp, "one.html")
            two = os.path.join(tmp, "two.html")
            for out in (one, two):
                done = subprocess.run(
                    [sys.executable, RENDER, "--dictionary", DICTIONARY, "-o", out, "--no-font"],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(done.returncode, 0, done.stderr)
            with open(one, "rb") as fp:
                a = fp.read()
            with open(two, "rb") as fp:
                b = fp.read()
            self.assertEqual(a, b)
            self.assertEqual(a.decode("utf-8"), open(one, encoding="utf-8").read())

    def test_cli_reports_counts_and_defaults_to_the_bundled_dictionary(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "guide.html")
            done = subprocess.run(
                [sys.executable, RENDER, "-o", out, "--no-font"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            meta = load_dict()["meta"]
            self.assertIn(
                "화면: %d개 · 입력 칸: %d개" % (meta["screen_count"], meta["field_count"]),
                done.stdout,
            )


class ScreenGuideMismatchTest(unittest.TestCase):
    """머리 숫자가 어긋난 사전은 CLI 가 종료 코드 1 로 알린다."""

    def test_cli_fails_when_meta_counts_disagree(self):
        data = json.loads(json.dumps(SYNTHETIC))
        data["meta"]["field_count"] = 999
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.json")
            out = os.path.join(tmp, "bad.html")
            with open(bad, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False)
            done = subprocess.run(
                [sys.executable, RENDER, "--dictionary", bad, "-o", out, "--no-font"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(done.returncode, 1)
            self.assertIn("meta.field_count", done.stderr)


class SyntheticDictionaryTest(unittest.TestCase):
    """작은 가짜 사전도 그대로 그려져야 한다 (사전이 커지기 전의 최소 계약)."""

    @classmethod
    def setUpClass(cls):
        cls.page, cls.stats = rsg.render_guide(SYNTHETIC, None, "9.9.9")

    def test_counts(self):
        self.assertEqual(self.stats["screens"], SYNTHETIC["meta"]["screen_count"])
        self.assertEqual(self.stats["fields"], SYNTHETIC["meta"]["field_count"])

    def test_tabs_with_and_without_screens(self):
        toc = re.search(r'<nav class="toc">.*?</nav>', self.page, re.S).group(0)
        self.assertIn("시험탭", toc)
        self.assertIn("빈탭", toc)
        self.assertIn(rsg.OUTSIDE_TABS, toc)
        self.assertIn("시험 화면 하나", toc)
        self.assertIn("탭 밖 화면 하나", toc)

    def test_block_name_and_repeat_row_columns(self):
        block = section_of(self.page, "synth-one")
        self.assertIn("<code>반복 블록</code>", block)
        self.assertIn("열 — 왼쪽, 오른쪽", block)
        self.assertIn("열 선택지 — 가, 나", block)
        self.assertIn("첫 열 이름은 위 칸이 정한다.", block)
        self.assertIn("<strong>묶음</strong> — 가, 나", block)

    def test_options_are_a_comma_list_and_notes_sit_under_them(self):
        block = section_of(self.page, "synth-one")
        self.assertIn("하나, 둘", block)
        self.assertIn("이 호텔에 만든 것만", block)
        self.assertIn("보일 때 — 「이름」을 채운 뒤", block)

    def test_required_mark_and_buttons_and_notes(self):
        block = section_of(self.page, "synth-one")
        self.assertIn('<span class="req-yes">예</span>', block)
        self.assertIn('<span class="btn">추가</span>', block)
        self.assertIn("<code>코드</code>", block)
        self.assertIn("<strong>굵게</strong>", block)

    def test_screen_without_blocks_still_renders(self):
        block = section_of(self.page, "synth-two")
        self.assertTrue(block)
        self.assertIn("탭 밖 화면 하나", block)
        self.assertNotIn('<tr class="field">', block)

    def test_version_and_not_covered(self):
        self.assertIn("9.9.9", self.page)
        self.assertIn("가짜 사전이라 담지 않은 것.", self.page)


#: 작은 가짜 영향 지도 — 위 가짜 사전과 칸이 **정확히 같아야** 한다(화면 2·칸 3).
SYNTHETIC_IMPACT = {
    "meta": {
        "generated_on": "2026-01-02",
        "erp_baseline": "시험용 배포판 화면 기준",
        "screen_count": 2,
        "field_count": 3,
    },
    "screens": [
        {
            "id": "synth-one",
            "name": "시험 화면 하나",
            "summary": "이 화면을 안 채우면 고객 화면의 제목 줄이 빈다.",
            "fields": [
                {
                    "label": "이름",
                    "block": "",
                    "erp_column": "fake.Model.name",
                    "engine": "FakeDto.name",
                    "web": [
                        {
                            "page": "호텔 상세 /stay/<id>",
                            "section": "히어로 상단",
                            "element": "h1 제목",
                            "how": "두 줄까지 흘리고 자른다",
                        },
                        {
                            "page": "예약 /stay/<id>/reserve",
                            "section": "우측 요약 카드",
                            "element": "이름 줄",
                            "how": "그대로",
                        },
                    ],
                    "web_not_shown": None,
                    "erp_reservation": None,
                    "downstream": "표시",
                    "effect": "고객 웹 호텔 상세의 히어로에 제목으로 나온다.",
                    "confidence": "확인",
                    "evidence": ["fake:one.py:1"],
                },
                {
                    "label": "고르기",
                    "block": "",
                    "erp_column": "fake.Model.pick",
                    "engine": None,
                    "web": [],
                    "web_not_shown": ["고객 화면에 안 나온다 — 그 카드 줄이 지금 꺼져 있다. 켜지면 카드 하단에 나온다"],
                    "erp_reservation": None,
                    "downstream": "미사용",
                    "effect": "ERP 안에서만 쓰인다 — 엔진이 이 컬럼을 아예 읽지 않아 고객 웹 어디에도 영향이 없다. 뒷문장은 목록에서 잘린다.",
                    "confidence": "미사용",
                    "evidence": ["fake:two.py:2"],
                },
                {
                    "label": "줄 넣기",
                    "block": "반복 블록",
                    "erp_column": "fake.Model.rows",
                    "engine": "FakeRow",
                    "web": [],
                    "web_not_shown": None,
                    "erp_reservation": "2. 객실·요금제 — 요금 행에서 확인",
                    "downstream": "게이트",
                    "effect": "웹에 글자로는 안 나온다 — 조건에 안 맞는 줄을 응답에서 지운다.",
                    "confidence": "부분",
                    "evidence": ["fake:three.py:3"],
                },
            ],
        },
        {
            "id": "synth-two",
            "name": "탭 밖 화면 하나",
            "summary": "값을 넣는 칸이 없는 화면이다.",
            "fields": [],
        },
    ],
}


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False)


class ImpactMapTest(unittest.TestCase):
    """`--impact` 를 주면 칸마다 「웹에 나오는 곳」·「효과」 가 붙는다."""

    @classmethod
    def setUpClass(cls):
        cls.plain, cls.plain_stats = rsg.render_guide(SYNTHETIC, None, "9.9.9")
        cls.page, cls.stats = rsg.render_guide(SYNTHETIC, None, "9.9.9", SYNTHETIC_IMPACT)

    def test_page_without_impact_is_unchanged(self):
        again, _ = rsg.render_guide(SYNTHETIC, None, "9.9.9", None)
        self.assertEqual(self.plain, again)
        self.assertNotIn("웹에 나오는 곳", self.plain)
        self.assertNotIn("impact-overview", self.plain)
        self.assertNotIn("screen-summary", self.plain)
        self.assertNotEqual(self.plain, self.page)
        self.assertIsNone(self.plain_stats["impact"])

    def test_field_table_has_seven_columns(self):
        self.assertIn(
            "<thead><tr><th>칸</th><th>종류</th><th>필수</th>"
            "<th>선택지 / 형식</th><th>도움말</th>"
            "<th>웹에 나오는 곳</th><th>효과</th></tr></thead>",
            self.page,
        )
        self.assertIn('<table class="fields with-impact">', self.page)
        self.assertIn(
            "<thead><tr><th>칸</th><th>종류</th><th>필수</th>"
            "<th>선택지 / 형식</th><th>도움말</th></tr></thead>",
            self.plain,
        )
        self.assertNotIn("with-impact", self.plain)

    def test_counts_still_match_the_dictionary_head(self):
        self.assertEqual(self.stats["screens"], SYNTHETIC["meta"]["screen_count"])
        self.assertEqual(self.stats["fields"], SYNTHETIC["meta"]["field_count"])
        self.assertEqual(len(re.findall(r'<tr class="field">', self.page)), 3)

    def test_web_places_are_one_line_each(self):
        block = section_of(self.page, "synth-one")
        self.assertIn(
            '<span class="web-line">호텔 상세 /stay/&lt;id&gt; › 히어로 상단 › h1 제목 — '
            '<span class="w-how">두 줄까지 흘리고 자른다</span></span>',
            block,
        )
        self.assertIn("예약 /stay/&lt;id&gt;/reserve › 우측 요약 카드 › 이름 줄", block)
        self.assertEqual(block.count('class="web-line"'), 2)

    def test_field_with_no_web_place_says_so(self):
        block = section_of(self.page, "synth-one")
        self.assertEqual(block.count('<span class="web-none">고객 화면에 안 나옴</span>'), 2)

    def test_unused_field_gets_the_muted_tag(self):
        block = section_of(self.page, "synth-one")
        self.assertIn('<span class="tag tag-muted">웹 미사용</span>', block)
        self.assertEqual(block.count("웹 미사용"), 1)

    def test_gate_and_partial_tags(self):
        block = section_of(self.page, "synth-one")
        self.assertIn('<span class="tag tag-gate">게이트</span>', block)
        self.assertIn('<span class="tag tag-partial">일부 확인</span>', block)

    def test_shown_field_has_no_tag_but_keeps_its_effect(self):
        row = re.search(
            r'<tr class="field">(?:(?!</tr>).)*?이름(?:(?!</tr>).)*?</tr>',
            section_of(self.page, "synth-one"),
            re.S,
        )
        self.assertIsNotNone(row, "「이름」 줄을 못 찾았다")
        self.assertNotIn('class="tag', row.group(0))
        self.assertIn("고객 웹 호텔 상세의 히어로에 제목으로 나온다.", row.group(0))

    def test_erp_reservation_and_not_shown_lines(self):
        block = section_of(self.page, "synth-one")
        self.assertIn(
            '<span class="sub">ERP 직원 예약: 2. 객실·요금제 — 요금 행에서 확인</span>', block
        )
        self.assertIn(
            '<span class="sub">고객 화면에 안 나온다 — 그 카드 줄이 지금 꺼져 있다. 켜지면 카드 하단에 나온다</span>',
            block,
        )
        # 머리말은 영향 지도의 줄이 갖는다 — 렌더러가 따로 덧붙이지 않는다.
        self.assertNotIn("코드에 자리는 있으나", self.page)

    def test_internal_columns_are_not_printed(self):
        self.assertNotIn("fake.Model.name", self.page)
        self.assertNotIn("FakeDto.name", self.page)
        self.assertNotIn("fake:one.py:1", self.page)

    def test_each_screen_carries_its_summary(self):
        for screen_id, summary in (
            ("synth-one", "이 화면을 안 채우면 고객 화면의 제목 줄이 빈다."),
            ("synth-two", "값을 넣는 칸이 없는 화면이다."),
        ):
            block = section_of(self.page, screen_id)
            self.assertIn('<p class="screen-summary">%s</p>' % summary, block)

    def test_overview_section_sits_right_after_the_howto(self):
        overview = re.search(
            r'<section class="impact-overview".*?</section>', self.page, re.S
        )
        self.assertIsNotNone(overview, "「한눈에」 절이 없다")
        self.assertIn(rsg.IMPACT_OVERVIEW_TITLE, overview.group(0))
        howto_end = self.page.index("</section>", self.page.index('<section class="howto">'))
        self.assertLess(howto_end, self.page.index('<section class="impact-overview"'))
        self.assertLess(
            self.page.index('<section class="impact-overview"'),
            self.page.index('<nav class="toc">'),
        )

    def test_overview_counts_and_lists_the_unused_fields(self):
        overview = re.search(
            r'<section class="impact-overview".*?</section>', self.page, re.S
        ).group(0)
        self.assertIn(
            '<h3>%s <span class="ov-count">1개</span></h3>' % rsg.IMPACT_UNUSED_TITLE, overview
        )
        self.assertIn('<a href="#screen-synth-one">시험 화면 하나</a>', overview)
        self.assertIn('<span class="fname">고르기</span>', overview)
        # 목록의 이유는 `effect` 의 첫 문장만이다.
        self.assertIn("엔진이 이 컬럼을 아예 읽지 않아 고객 웹 어디에도 영향이 없다.", overview)
        self.assertNotIn("뒷문장은 목록에서 잘린다.", overview)

    def test_overview_gate_table(self):
        overview = re.search(
            r'<section class="impact-overview".*?</section>', self.page, re.S
        ).group(0)
        self.assertIn(
            '<h3>%s <span class="ov-count">1개</span></h3>' % rsg.IMPACT_GATE_TITLE, overview
        )
        self.assertIn(
            "<thead><tr><th>화면</th><th>칸</th><th>틀리면 생기는 일</th></tr></thead>", overview
        )
        self.assertIn("조건에 안 맞는 줄을 응답에서 지운다.", overview)

    def test_overview_summary_table_has_every_screen(self):
        overview = re.search(
            r'<section class="impact-overview".*?</section>', self.page, re.S
        ).group(0)
        self.assertIn(
            "<thead><tr><th>화면</th><th>이 화면을 안 채우면</th></tr></thead>", overview
        )
        table = overview[overview.index('<table class="summaries">'):]
        for summary in ("이 화면을 안 채우면 고객 화면의 제목 줄이 빈다.", "값을 넣는 칸이 없는 화면이다."):
            self.assertIn(summary, table)
        self.assertEqual(table.count('<td class="c-screen"'), 2)

    def test_header_states_the_impact_basis_without_commit_refs(self):
        head = re.search(r'<header class="page-head">.*?</header>', self.page, re.S).group(0)
        self.assertIn("<dt>고객 웹 영향</dt>", head)
        self.assertIn("<dd>%s</dd>" % rsg.IMPACT_BASELINE_TEXT, head)
        self.assertNotIn("고객 웹 영향", self.plain)

    def test_commit_refs_in_impact_meta_are_never_printed(self):
        impact = json.loads(json.dumps(SYNTHETIC_IMPACT))
        impact["meta"].update(erp_ref="aaaa1111", engine_ref="bbbb2222", web_ref="cccc3333")
        page, _ = rsg.render_guide(SYNTHETIC, None, "9.9.9", impact)
        for ref in ("aaaa1111", "bbbb2222", "cccc3333"):
            self.assertNotIn(ref, page)
        self.assertIn("<dd>%s</dd>" % rsg.IMPACT_BASELINE_TEXT, page)

    def test_impact_counts_are_reported(self):
        self.assertEqual(
            self.stats["impact"], {"shown": 1, "none": 2, "unused": 1, "gate": 1}
        )

    def test_phone_width_stacks_the_seven_columns(self):
        self.assertIn("@media (max-width: 700px){", self.page)
        for label in ("웹에 나오는 곳", "효과", "틀리면 생기는 일", "이 화면을 안 채우면"):
            self.assertIn('data-label="%s"' % label, self.page)
        self.assertNotIn("@media (max-width: 700px){", self.plain)

    def test_impact_page_tags_are_balanced(self):
        errors, left_open = tag_balance(self.page)
        self.assertEqual(errors, [])
        self.assertEqual(left_open, [])

    def test_impact_page_stays_offline_and_deterministic(self):
        self.assertEqual(re.findall(r"https?://", self.page), [])
        self.assertNotIn("<script", self.page)
        again, _ = rsg.render_guide(SYNTHETIC, None, "9.9.9", SYNTHETIC_IMPACT)
        self.assertEqual(self.page, again)

    def test_a_truncated_quote_in_the_map_does_not_reach_the_page(self):
        data = json.loads(json.dumps(SYNTHETIC_IMPACT))
        data["screens"][0]["fields"][0]["effect"] = "푸터에 `{checkIn} ~ {checkOut} · {…"
        page, _ = rsg.render_guide(SYNTHETIC, None, "9.9.9", data)
        self.assertNotIn("`", page)
        self.assertIn("{checkIn} ~ {checkOut}", page)

    def test_escaping_survives_the_new_columns(self):
        data = json.loads(json.dumps(SYNTHETIC_IMPACT))
        data["screens"][0]["fields"][0]["web"][0]["how"] = '<img src=x onerror="boom">'
        page, _ = rsg.render_guide(SYNTHETIC, None, "9.9.9", data)
        self.assertNotIn("<img", page)
        self.assertIn("&lt;img src=x onerror=&quot;boom&quot;&gt;", page)


class ImpactOneLineTest(unittest.TestCase):
    def test_first_sentence_only(self):
        self.assertEqual(rsg.one_line("앞 문장이다. 뒷 문장이다."), "앞 문장이다.")

    def test_short_text_is_kept_whole(self):
        self.assertEqual(rsg.one_line("짧은 글"), "짧은 글")
        self.assertEqual(rsg.one_line(""), "")
        self.assertEqual(rsg.one_line(None), "")

    def test_long_text_without_a_sentence_end_is_cut(self):
        text = "가 " * 200
        cut = rsg.one_line(text, limit=40)
        self.assertTrue(cut.endswith("…"))
        self.assertLessEqual(len(cut), 41)

    def test_a_half_open_code_quote_loses_only_the_quote(self):
        cut = rsg.one_line("여기는 길게 이어지는 설명이고 `열린코드", limit=200)
        self.assertNotIn("`", cut)
        self.assertIn("열린코드", cut)

    def test_impact_inline_drops_a_dangling_quote(self):
        self.assertEqual(rsg.impact_inline("앞 `코드` 와 잘린 `조각"), "앞 <code>코드</code> 와 잘린 조각")
        self.assertEqual(rsg.impact_inline("`짝이` 맞으면 그대로"), "<code>짝이</code> 맞으면 그대로")


class ImpactMismatchTest(unittest.TestCase):
    """사전과 지도가 한 줄이라도 어긋나면 문서를 만들지 않는다."""

    def render_with(self, mutate):
        impact = json.loads(json.dumps(SYNTHETIC_IMPACT))
        mutate(impact)
        with self.assertRaises(rsg.ImpactMismatch) as caught:
            rsg.render_guide(SYNTHETIC, None, "9.9.9", impact)
        return str(caught.exception)

    def test_a_renamed_label_is_caught(self):
        def rename(impact):
            impact["screens"][0]["fields"][1]["label"] = "고르기(바뀜)"

        message = self.render_with(rename)
        self.assertIn("어긋난다", message)
        self.assertIn("영향 지도에 칸이 없다: synth-one / (블록 없음) / 고르기", message)
        self.assertIn("사전에 없는 칸이 영향 지도에 있다", message)

    def test_a_moved_block_is_caught(self):
        def move(impact):
            impact["screens"][0]["fields"][2]["block"] = "다른 블록"

        self.assertIn("줄 넣기", self.render_with(move))

    def test_a_missing_screen_is_caught(self):
        def drop(impact):
            impact["screens"] = impact["screens"][:1]
            impact["meta"]["screen_count"] = 1

        message = self.render_with(drop)
        self.assertIn("영향 지도에 화면이 없다: synth-two", message)

    def test_impact_head_counts_must_agree(self):
        def bend(impact):
            impact["meta"]["field_count"] = 99

        self.assertIn("meta.field_count", self.render_with(bend))


class ImpactCliTest(unittest.TestCase):
    def render(self, tmp, dictionary, impact=None, out="out.html"):
        dict_path = os.path.join(tmp, "dict.json")
        write_json(dict_path, dictionary)
        out_path = os.path.join(tmp, out)
        argv = [sys.executable, RENDER, "--dictionary", dict_path, "-o", out_path, "--no-font"]
        if impact is not None:
            impact_path = os.path.join(tmp, "impact.json")
            write_json(impact_path, impact)
            argv += ["--impact", impact_path]
        done = subprocess.run(argv, capture_output=True, text=True)
        return done, out_path

    def test_cli_renders_the_impact_columns_and_reports_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            done, out_path = self.render(tmp, SYNTHETIC, SYNTHETIC_IMPACT)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("고객 웹 영향: 나오는 칸 1개 · 안 나오는 칸 2개", done.stdout)
            self.assertIn("웹 미사용 1개 · 게이트 1개", done.stdout)
            with open(out_path, encoding="utf-8") as fp:
                page = fp.read()
            self.assertIn("<th>웹에 나오는 곳</th><th>효과</th>", page)
            self.assertIn(rsg.IMPACT_OVERVIEW_TITLE, page)

    def test_cli_writes_the_same_bytes_twice_with_impact(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, one = self.render(tmp, SYNTHETIC, SYNTHETIC_IMPACT, out="one.html")
            second, two = self.render(tmp, SYNTHETIC, SYNTHETIC_IMPACT, out="two.html")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            with open(one, "rb") as fp:
                a = fp.read()
            with open(two, "rb") as fp:
                b = fp.read()
            self.assertEqual(a, b)

    def test_cli_fails_when_a_label_disagrees(self):
        impact = json.loads(json.dumps(SYNTHETIC_IMPACT))
        impact["screens"][0]["fields"][0]["label"] = "이름(바뀜)"
        with tempfile.TemporaryDirectory() as tmp:
            done, out_path = self.render(tmp, SYNTHETIC, impact)
            self.assertEqual(done.returncode, 1)
            self.assertIn("영향 지도가 화면 사전과 어긋난다", done.stderr)
            self.assertIn("이름", done.stderr)
            self.assertFalse(os.path.exists(out_path), "어긋났는데 파일을 썼다")

    def test_cli_fails_when_the_impact_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            dict_path = os.path.join(tmp, "dict.json")
            write_json(dict_path, SYNTHETIC)
            done = subprocess.run(
                [
                    sys.executable, RENDER,
                    "--dictionary", dict_path,
                    "-o", os.path.join(tmp, "out.html"),
                    "--no-font",
                    "--impact", os.path.join(tmp, "없는지도.json"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(done.returncode, 1)
            self.assertIn("영향 지도를 찾을 수 없다", done.stderr)

    def test_cli_without_impact_writes_the_same_bytes_as_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain, plain_path = self.render(tmp, SYNTHETIC, None, out="plain.html")
            self.assertEqual(plain.returncode, 0, plain.stderr)
            with open(plain_path, encoding="utf-8") as fp:
                page = fp.read()
            self.assertNotIn("웹에 나오는 곳", page)
            self.assertNotIn("impact-overview", page)
            self.assertNotIn("고객 웹 영향", plain.stdout)


if __name__ == "__main__":
    unittest.main()
