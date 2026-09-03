#!/usr/bin/env python3
"""parse_guide.py 검증 — 예시(우에노 토우가네야) manual.md · HTML 을 함께 본다.

    python3 -m pytest skills/stay-setup-run/tests/test_parse_guide.py
    python3 skills/stay-setup-run/tests/test_parse_guide.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "parse_guide.py"
REPO = HERE.parents[2]
EXAMPLE = REPO / "skills" / "stay-setup-guide" / "examples" / "우에노_토우가네야"
MANUAL = EXAMPLE / "manual.md"
GUIDE_HTML = EXAMPLE / "우에노_토우가네야_입력지시서.html"

sys.path.insert(0, str(SCRIPT.parent))
import parse_guide  # noqa: E402


def parse(path, **kw):
    src, source = parse_guide.resolve_input(str(path))
    title, raws = (parse_guide.parse_markdown(src.read_text(encoding="utf-8"))
                   if source == "manual.md"
                   else parse_guide.parse_html(src.read_text(encoding="utf-8")))
    steps = [parse_guide.build_step(r) for r in raws]
    if kw.get("prefix"):
        parse_guide.apply_title_prefix(steps, kw["prefix"])
    return title, steps


def step_by_no(steps, no):
    for s in steps:
        if s["no"] == no:
            return s
    raise AssertionError("%d단계가 없습니다" % no)


def field_by_label(step, label):
    for f in step["fields"]:
        if f["label"] == label:
            return f
    raise AssertionError("`%s` 칸이 없습니다 (%s)" % (label, step["title"]))


def comparable(step):
    """manual.md 와 HTML 이 반드시 같아야 하는 부분 (raw 는 뺀다)."""
    return {
        "no": step["no"],
        "title": step["title"],
        "kind": step["kind"],
        "head": {k: step["head"][k] for k in ("tab", "card", "block", "folder")},
        "buttons": step["head"]["buttons"],
        "fields": [{k: v for k, v in f.items()
                    if k in ("label", "kind", "value", "values", "file")}
                   for f in step["fields"]],
        "longtexts": step["longtexts"],
        "photos": [p["file"] for p in step["photos"]],
        "submit": step["submit"],
    }


class TestManual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.title, cls.steps = parse(MANUAL)

    def test_step_count(self):
        self.assertEqual(len(self.steps), 60)
        self.assertEqual([s["no"] for s in self.steps], list(range(1, 61)))

    def test_room_name_is_typed(self):
        f = field_by_label(step_by_no(self.steps, 10), "룸 이름")
        self.assertEqual(f["kind"], "typed")
        self.assertEqual(f["value"], "Single")

    def test_last_step_kind(self):
        last = step_by_no(self.steps, 60)
        self.assertEqual(last["kind"], "판매 시작")
        self.assertEqual(last["submit"], "판매 시작")
        self.assertEqual(last["fields"], [])

    def test_target_room_is_select(self):
        f = field_by_label(step_by_no(self.steps, 36), "대상 룸")
        self.assertEqual(f["kind"], "select")
        self.assertEqual(f["value"], "2026~2027 시즌 요금 · Single")

    def test_photo_with_source(self):
        photos = step_by_no(self.steps, 6)["photos"]
        self.assertEqual([p["file"] for p in photos], ["hotel_01.jpg"])
        self.assertTrue(photos[0]["source"].startswith("http"))

    def test_multi_select_is_split(self):
        f = field_by_label(step_by_no(self.steps, 35), "대상 룸")
        self.assertEqual(f["kind"], "multi")
        self.assertEqual(len(f["values"]), 6)
        self.assertEqual(f["values"][0], "2026~2027 시즌 요금 · Single")

    def test_repeated_row_label(self):
        f = field_by_label(step_by_no(self.steps, 10), "침대 구성 1 · 침대 종류")
        self.assertEqual((f["row_group"], f["row_index"], f["row_field"]),
                         ("침대 구성", 1, "침대 종류"))

    def test_head_and_buttons(self):
        head = step_by_no(self.steps, 10)["head"]
        self.assertEqual(head["tab"], "객실")
        self.assertEqual(head["card"], "객실 (룸 타입)")
        self.assertEqual(len(head["buttons"]), 2)
        first, second = head["buttons_parsed"]
        self.assertEqual((first["text"], first["row"], first["drawer"], first["times"]),
                         ("편집", "스탠다드", False, 1))
        self.assertEqual((second["text"], second["group"], second["drawer"], second["times"]),
                         ("침대 행 추가", "침대 구성", True, 1))

    def test_longtexts(self):
        lt = step_by_no(self.steps, 5)["longtexts"]
        self.assertEqual([x["label"] for x in lt], ["한줄설명", "상세설명"])
        self.assertIn("55실 규모의 비즈니스 호텔", lt[0]["text"])

    def test_file_field_becomes_photo(self):
        for s in self.steps:
            for f in s["fields"]:
                if f["kind"] == "file":
                    self.assertIn(f["file"], [p["file"] for p in s["photos"]])
                    return
        self.fail("`파일:` 칸이 있는 단계를 찾지 못했습니다")


class TestHtmlMatchesManual(unittest.TestCase):
    def test_same_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            # manual.md 가 옆에 있으면 파서가 그것을 먼저 읽으므로 HTML 만 따로 둔다
            copy = Path(tmp) / GUIDE_HTML.name
            shutil.copy(GUIDE_HTML, copy)
            _, from_html = parse(copy)
        _, from_md = parse(MANUAL)
        self.assertEqual(len(from_html), len(from_md))
        for a, b in zip(from_md, from_html):
            self.assertEqual(comparable(a), comparable(b), "%d단계가 다릅니다" % a["no"])

    def test_html_next_to_manual_prefers_manual(self):
        src, source = parse_guide.resolve_input(str(GUIDE_HTML))
        self.assertEqual(source, "manual.md")
        self.assertEqual(src, MANUAL)

    def test_directory_input(self):
        src, source = parse_guide.resolve_input(str(EXAMPLE))
        self.assertEqual((src, source), (MANUAL, "manual.md"))


class TestTitlePrefix(unittest.TestCase):
    def test_only_two_fields_change(self):
        _, plain = parse(MANUAL)
        _, fixed = parse(MANUAL, prefix="__skills__")
        changed = []
        for a, b in zip(plain, fixed):
            for fa, fb in zip(a["fields"], b["fields"]):
                if fa.get("value") != fb.get("value"):
                    changed.append((a["no"], a["kind"], fb["label"], fb["value"]))
        self.assertEqual(changed, [
            (4, "호텔 만들기", "호텔명", "__skills__우에노 토우가네야 호텔"),
            (5, "기본정보 글 입력", "상품명", "__skills__우에노 토우가네야 호텔"),
        ])

    def test_prefix_recorded_in_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "steps.json"
            run(str(MANUAL), "--title-prefix", "__skills__", "-o", str(out))
            doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(doc["guide"]["title_prefix"], "__skills__")
        self.assertEqual(doc["guide"]["source"], "manual.md")
        self.assertEqual(doc["guide"]["share_folder"], "우에노_토우가네야")
        self.assertTrue(Path(doc["guide"]["photos_dir"]).is_absolute())


MINI = """# 시험 호텔 — 입력 지시서

## 1. 대표이미지 올리기 (1장)
탭: `기본정보`
폴더: 시험/사진

파일 선택 → 아래 파일
- hotel_01.jpg — 출처: https://example.com/a.jpg

→ [저장]
"""


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True)


class TestCheckMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = Path(self.tmp) / "시험"
        (self.dir / "사진").mkdir(parents=True)
        (self.dir / "manual.md").write_text(MINI, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_check_fails_on_missing_photo(self):
        r = run(str(self.dir), "--check")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("hotel_01.jpg", r.stdout)
        self.assertIn("없는 사진 파일: 1", r.stdout)

    def test_check_passes_when_photo_exists(self):
        (self.dir / "사진" / "hotel_01.jpg").write_bytes(b"jpeg")
        r = run(str(self.dir), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("없는 사진 파일: 0", r.stdout)

    def test_missing_marked_in_json(self):
        out = Path(self.tmp) / "steps.json"
        r = run(str(self.dir), "-o", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(doc["guide"]["photo_missing"], ["hotel_01.jpg"])
        self.assertTrue(doc["steps"][0]["photos"][0]["missing"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
