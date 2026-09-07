#!/usr/bin/env python3
"""render_card.py 의 검사 도장(stay-guide-stamp) 시험.

렌더된 HTML 의 `<head>` 에는 도장이 하나 박힌다:

    <meta name="stay-guide-stamp" content="v1;sha256=<manual.md 바이트의 sha256>;check=<ok|fail>;rendered=<날짜>">

`stay-setup-run` 의 `parse_guide.py` 가 이 도장을 보고 실행 여부를 정하므로, 도장이 없거나
해시가 틀리거나 `check` 가 잘못 찍히면 검사를 건너뛴 지시서가 그대로 실행된다.

실행:
    python3 -m unittest discover -s skills/stay-setup-guide/tests -v
"""
import datetime
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.normpath(os.path.join(HERE, os.pardir))
SCRIPTS = os.path.join(SKILL, "scripts")
RENDER = os.path.join(SCRIPTS, "render_card.py")
sys.path.insert(0, SCRIPTS)

import render_card as rc  # noqa: E402

STAMP_RE = re.compile(r'<meta name="stay-guide-stamp" content="([^"]+)">')

#: 검사기를 그대로 통과하는 가장 작은 지시서 — 0단계(환율·거래처·도시) 세 줄.
ZERO_OK = """# 시험 호텔 — 입력 지시서

## 1. 환율 확인
화면: 왼쪽 메뉴 `자유여행` → `상품관리` → 목록 위 [호텔 만들기]
주의: 목록에 뜨는지만 보고 [목록] 으로 나온다

| 칸 | 값 |
|---|---|
| 공급 통화 | 선택: USD |

→ [목록]

## 2. 거래처 확인
화면: 왼쪽 메뉴 `자유여행` → `상품관리` → 목록 위 [호텔 만들기]
블록: `거래처정보`

| 칸 | 값 |
|---|---|
| 거래처 | 선택: 자사 |

→ [목록]

## 3. 도시 확인
화면: 왼쪽 메뉴 `자유여행` → `상품관리` → 목록 위 [호텔 만들기]

| 칸 | 값 |
|---|---|
| 도시 | 선택: 도쿄(TYO) |

→ [목록]
"""

#: 검사기가 막는 지시서 — `오퍼 고치기` 는 2026-09-04 화면에 없는 옛 갈래다(0단계도 없다).
STALE = """# 시험 호텔 — 입력 지시서

## 1. 오퍼 고치기 (기본 오퍼)
탭: `오퍼`
버튼: `기본 오퍼` 행의 [편집]

| 칸 | 값 |
|---|---|
| 오퍼명 | 2026 계약 |

→ [저장]
"""

#: `폴더:` 줄이 공유 폴더명과 어긋난 지시서 — `--share-name` 을 줄 때만 걸린다.
WRONG_FOLDER = ZERO_OK + """
## 4. 대표이미지 올리기 (1장)
탭: `기본정보`
폴더: 다른이름/사진

파일 선택 → 아래 파일
- hotel_01.jpg

→ [저장]
"""


def parse_stamp(text):
    m = STAMP_RE.search(text)
    if not m:
        return None
    out = {}
    for i, part in enumerate(p.strip() for p in m.group(1).split(";")):
        if i == 0 and "=" not in part:
            out["version"] = part
            continue
        key, _, value = part.partition("=")
        out[key] = value
    return out


class TestStampFormat(unittest.TestCase):
    def test_no_stamp_when_not_asked(self):
        """도장을 주지 않으면 예전과 똑같은 글이 나온다 — 렌더 자체는 달라지지 않는다."""
        html_text, _ = rc.render_card(ZERO_OK, "manual.md", None, None)
        self.assertNotIn("stay-guide-stamp", html_text)

    def test_stamp_sits_right_after_title(self):
        stamp = rc.build_stamp("a" * 64, True, rendered="2026-09-07")
        html_text, _ = rc.render_card(ZERO_OK, "manual.md", None, None, None, stamp)
        head = html_text.splitlines()[:2]
        self.assertTrue(head[0].startswith("<title>"), head[0])
        self.assertEqual(
            head[1],
            '<meta name="stay-guide-stamp" '
            'content="v1;sha256=%s;check=ok;rendered=2026-09-07">' % ("a" * 64))

    def test_build_stamp_fields(self):
        got = parse_stamp('<meta name="stay-guide-stamp" content="%s">'
                          % rc.build_stamp("b" * 64, False, rendered="2026-01-02"))
        self.assertEqual(got, {"version": "v1", "sha256": "b" * 64,
                               "check": "fail", "rendered": "2026-01-02"})

    def test_manual_sha256_is_of_bytes(self):
        text = "본문 한 줄\n"
        self.assertEqual(rc.manual_sha256(text.encode("utf-8")),
                         hashlib.sha256(text.encode("utf-8")).hexdigest())


class TestCheckerRun(unittest.TestCase):
    """도장의 `check` 는 옆의 `check_manual.py` 를 같은 프로세스에서 돌린 결과다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text, name="manual.md"):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_clean_manual_passes(self):
        ok, _out = rc.run_checker(self.write(ZERO_OK))
        self.assertTrue(ok)

    def test_stale_manual_fails(self):
        ok, out = rc.run_checker(self.write(STALE))
        self.assertFalse(ok)
        self.assertIn("✗", out)

    def test_share_name_reaches_the_checker(self):
        """`--share-name` 을 줄 때만 `폴더:` 줄 형식이 걸린다 — 옵션이 검사기까지 간다는 증거."""
        path = self.write(WRONG_FOLDER)
        self.assertTrue(rc.run_checker(path)[0])
        self.assertFalse(rc.run_checker(path, share_name="시험")[0])

    def test_photos_reach_the_checker(self):
        """`--photos` 를 주면 없는 사진 참조가 오류가 된다."""
        path = self.write(WRONG_FOLDER)
        photos = os.path.join(self.dir, "사진")
        os.mkdir(photos)
        ok, out = rc.run_checker(path, photos_dir=photos)
        self.assertFalse(ok)
        self.assertIn("hotel_01.jpg", out)


class TestCliStamp(unittest.TestCase):
    """CLI 로 렌더한 HTML 의 도장 — 해시·판정·날짜가 다 맞아야 한다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def render(self, md_text, *extra):
        md = os.path.join(self.dir, "manual.md")
        with open(md, "w", encoding="utf-8") as handle:
            handle.write(md_text)
        out = os.path.join(self.dir, "시험_입력지시서.html")
        proc = subprocess.run([sys.executable, RENDER, md, "-o", out, *extra],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        with open(out, encoding="utf-8") as handle:
            return parse_stamp(handle.read()), proc

    def test_stamp_is_present_and_hash_matches(self):
        stamp, proc = self.render(ZERO_OK)
        self.assertIsNotNone(stamp, proc.stdout)
        self.assertEqual(stamp["version"], "v1")
        self.assertEqual(stamp["sha256"],
                         hashlib.sha256(ZERO_OK.encode("utf-8")).hexdigest())
        self.assertEqual(stamp["rendered"], datetime.date.today().isoformat())
        self.assertIn("검사 도장:", proc.stdout)

    def test_check_ok_for_clean_manual(self):
        stamp, _ = self.render(ZERO_OK)
        self.assertEqual(stamp["check"], "ok")

    def test_check_fail_for_failing_manual(self):
        """검사기가 막는 지시서는 `check=fail` 로 찍히고, 렌더는 그 사실을 말한다."""
        stamp, proc = self.render(STALE)
        self.assertEqual(stamp["check"], "fail")
        self.assertEqual(stamp["sha256"],
                         hashlib.sha256(STALE.encode("utf-8")).hexdigest())
        self.assertIn("검사기를 통과하지 못했다", proc.stderr)

    def test_share_name_option_changes_the_verdict(self):
        self.assertEqual(self.render(WRONG_FOLDER)[0]["check"], "ok")
        self.assertEqual(self.render(WRONG_FOLDER, "--share-name", "시험")[0]["check"], "fail")


class TestShareLayoutDefaults(unittest.TestCase):
    """`<이름>/_원고/manual.md` 자리면 출력 경로와 공유 폴더명을 경로에서 알아낸다.

    담당자에게 가는 것은 `<이름>/<이름>_입력지시서.html` 하나이므로, 그 자리가 기본값이다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.share = os.path.join(self.tmp.name, "우에노_토우가네야")
        self.draft = os.path.join(self.share, "_원고")
        os.makedirs(self.draft)
        self.md = os.path.join(self.draft, "manual.md")
        with open(self.md, "w", encoding="utf-8") as handle:
            handle.write(ZERO_OK)

    def tearDown(self):
        self.tmp.cleanup()

    def test_derive_share_name(self):
        self.assertEqual(rc.derive_share_name(self.md), "우에노_토우가네야")

    def test_derive_share_name_is_none_outside_the_layout(self):
        flat = os.path.join(self.share, "manual.md")
        with open(flat, "w", encoding="utf-8") as handle:
            handle.write(ZERO_OK)
        self.assertIsNone(rc.derive_share_name(flat))
        self.assertIsNone(rc.default_output(flat))

    def test_default_output_is_the_share_folder_guide(self):
        self.assertEqual(str(rc.default_output(self.md)),
                         os.path.join(self.share, "우에노_토우가네야_입력지시서.html"))

    def test_cli_without_o_writes_the_guide_next_to_the_draft_folder(self):
        proc = subprocess.run([sys.executable, RENDER, self.md],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = os.path.join(self.share, "우에노_토우가네야_입력지시서.html")
        self.assertTrue(os.path.isfile(out), proc.stdout)
        self.assertIn("공유 폴더명: 우에노_토우가네야", proc.stdout)

    def test_cli_without_o_outside_the_layout_asks_for_o(self):
        flat = os.path.join(self.tmp.name, "manual.md")
        with open(flat, "w", encoding="utf-8") as handle:
            handle.write(ZERO_OK)
        proc = subprocess.run([sys.executable, RENDER, flat], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("출력 경로를 정할 수 없다", proc.stderr)

    def test_derived_share_name_reaches_the_checker(self):
        """`--share-name` 없이도 `폴더:` 줄 형식이 걸린다 — 경로에서 알아낸 이름이 검사기까지 간다."""
        with open(self.md, "w", encoding="utf-8") as handle:
            handle.write(WRONG_FOLDER)
        proc = subprocess.run([sys.executable, RENDER, self.md], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = os.path.join(self.share, "우에노_토우가네야_입력지시서.html")
        with open(out, encoding="utf-8") as handle:
            self.assertEqual(parse_stamp(handle.read())["check"], "fail")


#: 번호 없는 `##` 절이 섞인 지시서 — 번호 붙은 단계만 진행 현황에 센다.
WITH_PLAIN_SECTION = ZERO_OK + """
## 참고
이 절은 번호가 없으니 단계가 아니다.
"""


class TestStepMarkup(unittest.TestCase):
    """단계마다 붙는 `data-step` — 자동 실행기(window.stayGuide)와 주고받는 약속이다.

    번호는 문서에서 몇 번째로 나왔는지가 아니라 `## N. 제목` 의 N 에서만 나오므로,
    같은 원고를 몇 번을 렌더해도 같은 번호가 나와야 한다.
    """

    def render(self, md_text=ZERO_OK):
        html_text, _stats = rc.render_card(md_text, "manual.md", None, None)
        return html_text

    def test_section_and_badge_carry_the_step_number(self):
        html_text = self.render()
        for no in (1, 2, 3):
            self.assertIn('<section class="step" data-step="%d">' % no, html_text)
            self.assertIn('<span class="step-status" data-step="%d" data-status="대기">대기</span>' % no,
                          html_text)

    def test_note_line_follows_each_step_heading(self):
        html_text = self.render()
        for no in (1, 2, 3):
            # 빈 줄은 `hidden` 으로 감춰 두고, 자리는 제목 바로 다음이다
            self.assertIn('</h2>\n<p class="step-note" data-step="%d" hidden></p>' % no, html_text)

    def test_badge_sits_before_the_done_checkbox(self):
        html_text = self.render()
        badge = html_text.index('<span class="step-status" data-step="1"')
        done = html_text.index('<label class="step-done-wrap">')
        self.assertLess(badge, done)

    def test_step_numbers_are_stable_across_renders(self):
        first = re.findall(r'data-step="(\d+)"', self.render())
        second = re.findall(r'data-step="(\d+)"', self.render())
        self.assertEqual(first, second)
        self.assertTrue(first)

    def test_unnumbered_section_has_no_step_number(self):
        html_text = self.render(WITH_PLAIN_SECTION)
        self.assertIn('<section class="step">', html_text)          # 번호 없는 절
        self.assertEqual(sorted(set(re.findall(r'<section class="step" data-step="(\d+)">', html_text))),
                         ["1", "2", "3"])

    def test_heading_step_no_reads_only_the_heading_number(self):
        self.assertEqual(rc.heading_step_no("7. 오퍼 만들기"), 7)
        self.assertEqual(rc.heading_step_no("**12.** 사진 올리기"), 12)
        self.assertIsNone(rc.heading_step_no("참고"))


class TestProgressPanel(unittest.TestCase):
    """h1 바로 밑에 붙는 "진행 현황" 머리말 — 전체 개수는 렌더가 세서 넘긴다."""

    def render(self, md_text=ZERO_OK):
        html_text, stats = rc.render_card(md_text, "manual.md", None, None)
        return html_text, stats

    def test_panel_markup_and_total(self):
        html_text, stats = self.render()
        self.assertIn('<section class="progress-panel" data-total="3">', html_text)
        self.assertIn('<p class="progress-title">진행 현황</p>', html_text)
        self.assertIn('<div class="progress-bar"><div class="progress-fill" style="width:0%"></div></div>',
                      html_text)
        self.assertIn('<span class="progress-done">완료 0</span>', html_text)
        self.assertIn('<span class="progress-total">전체 3</span>', html_text)
        self.assertIn('<p class="progress-current">아직 시작하지 않았습니다</p>', html_text)
        self.assertIn('<p class="progress-times"></p>', html_text)
        self.assertEqual(stats["steps"], 3)

    def test_total_counts_only_numbered_steps(self):
        html_text, stats = self.render(WITH_PLAIN_SECTION)
        self.assertIn('data-total="3"', html_text)
        self.assertEqual(stats["steps"], 3)

    def test_order_is_h1_then_panel_then_toc(self):
        html_text, _ = self.render()
        self.assertLess(html_text.index("<h1 "), html_text.index('class="progress-panel"'))
        self.assertLess(html_text.index('class="progress-panel"'), html_text.index('<nav class="toc"'))

    def test_panel_is_sticky_and_flattened_for_print(self):
        html_text, _ = self.render()
        self.assertIn("position:sticky", html_text)
        self.assertIn(".progress-panel{position:static !important", html_text)


class TestStayGuideApi(unittest.TestCase):
    """자동 실행기가 부르는 `window.stayGuide` — 이름 네 개가 다 나와야 한다."""

    def setUp(self):
        self.html, _ = rc.render_card(ZERO_OK, "manual.md", None, None)

    def test_api_object_is_exposed(self):
        self.assertIn("window.stayGuide", self.html)
        for name in ("mark:", "current:", "reset:", "'export':"):
            self.assertIn(name, self.html)

    def test_storage_key_is_tied_to_the_stamp(self):
        self.assertIn("'stayGuide:'", self.html)
        self.assertIn("stayGuide:nostamp", self.html)

    def test_all_canonical_statuses_are_known(self):
        for status in ("대기", "진행 중", "완료", "건너뜀", "실패", "확인 필요"):
            self.assertIn(status, self.html)
        self.assertIn("완료 (수동)", self.html)  # 사람이 직접 켠 것은 따로 남긴다

    def test_english_aliases_are_accepted(self):
        for alias in ("pending", "waiting", "running", "current", "active", "done", "ok",
                      "success", "skipped", "skip", "failed", "fail", "error",
                      "check", "review", "warn"):
            self.assertIn("'%s'" % alias, self.html)


class TestRenderRegression(unittest.TestCase):
    """진행 현황을 붙이면서 기존 것(단계별 완료 체크박스·목차)이 사라지지 않았는지 본다."""

    def setUp(self):
        self.html, self.stats = rc.render_card(ZERO_OK, "manual.md", None, None)

    def test_step_done_checkbox_still_there(self):
        self.assertEqual(self.html.count('<input type="checkbox" class="step-done"'), 3)
        self.assertEqual(self.html.count("<span>완료</span></label>"), 3)

    def test_toc_still_there(self):
        self.assertIn('<nav class="toc" aria-label="목차">', self.html)
        self.assertIn('<span class="toc-check">☐</span>', self.html)
        self.assertEqual(self.stats["nav_items"], 3)

    def test_copy_path_is_untouched(self):
        """복사 버튼을 그리는 길과 그 클릭 처리기는 그대로다."""
        self.assertIn(".copy-btn{", self.html)
        self.assertIn("closest('.copy-btn')", self.html)

    def test_cli_output_reports_the_step_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = os.path.join(tmp, "manual.md")
            with open(md, "w", encoding="utf-8") as handle:
                handle.write(ZERO_OK)
            out = os.path.join(tmp, "시험_입력지시서.html")
            proc = subprocess.run([sys.executable, RENDER, md, "-o", out],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("번호 붙은 단계 3개", proc.stdout)
            with open(out, encoding="utf-8") as handle:
                rendered = handle.read()
            self.assertIn('data-step="1"', rendered)
            self.assertIn("window.stayGuide", rendered)
            self.assertIn("진행 현황", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
