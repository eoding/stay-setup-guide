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


def steps_by_kind(steps, kind):
    """그 갈래의 단계들 — 번호 대신 갈래로 찾는다.

    예시 지시서가 다시 그려지면 단계 번호가 통째로 밀린다(2026-09-04 ERP 변경: 호텔이
    오퍼 0 · 룸 0 으로 생겨 `오퍼 고치기` 가 `오퍼 만들기` 로 바뀌고 룸 단계가 늘었다).
    번호를 박아 두면 그때마다 시험이 깨지므로, 갈래로 찾아 그 안에서 몇 번째를 고른다.
    """
    return [s for s in steps if s["kind"] == kind]


def only_step(steps, kind, index=0):
    hits = steps_by_kind(steps, kind)
    if len(hits) <= index:
        raise AssertionError("`%s` 단계가 %d개뿐입니다" % (kind, len(hits)))
    return hits[index]


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

    def test_step_numbering_is_contiguous(self):
        # 개수를 박아 두지 않는다 — 예시 지시서가 다시 그려질 때마다 바뀐다(`steps_by_kind` 주석).
        # 대신 1부터 빠짐없이 이어지는지를 본다. 그것이 파서가 지켜야 할 성질이다.
        self.assertEqual([s["no"] for s in self.steps], list(range(1, len(self.steps) + 1)))
        self.assertGreater(len(self.steps), 30)

    def test_room_name_is_typed(self):
        room = only_step(self.steps, "룸 만들기")
        f = field_by_label(room, "룸 이름")
        self.assertEqual(f["kind"], "typed")
        # 제목 `룸 만들기 (1번째, Single)` 의 이름과 칸 값이 같아야 한다
        self.assertTrue(room["title"].rstrip(")").endswith(f["value"]), room["title"])

    def test_last_step_kind(self):
        last = self.steps[-1]
        self.assertEqual(last["kind"], "판매 시작")
        self.assertEqual(last["submit"], "판매 시작")
        self.assertEqual(last["fields"], [])

    def test_target_room_is_select(self):
        f = field_by_label(only_step(self.steps, "시즌 가격 채우기"), "대상 룸")
        self.assertEqual(f["kind"], "select")
        self.assertIn(" · ", f["value"])  # `오퍼 · 룸` 꼴

    def test_photo_with_source(self):
        withsrc = [(s, p) for s in self.steps for p in s["photos"] if p.get("source")]
        self.assertTrue(withsrc, "출처가 적힌 사진이 한 장도 없습니다")
        self.assertTrue(withsrc[0][1]["source"].startswith("http"))

    def test_multi_select_is_split(self):
        f = field_by_label(only_step(self.steps, "판매일 열기"), "대상 룸")
        self.assertEqual(f["kind"], "multi")
        self.assertGreater(len(f["values"]), 1)
        for v in f["values"]:
            self.assertIn(" · ", v)

    def test_repeated_row_label(self):
        f = field_by_label(only_step(self.steps, "룸 만들기"), "침대 구성 1 · 침대 종류")
        self.assertEqual((f["row_group"], f["row_index"], f["row_field"]),
                         ("침대 구성", 1, "침대 종류"))

    def test_head_and_buttons(self):
        head = only_step(self.steps, "룸 만들기")["head"]
        self.assertEqual(head["tab"], "객실")
        self.assertEqual(head["card"], "객실 (룸 타입)")
        self.assertEqual(len(head["buttons"]), 2)
        first, second = head["buttons_parsed"]
        # ERP 2026-09-04 뒤로는 1번째 룸도 [룸 추가] 다. 옛 지시서(`스탠다드` 행의 [편집])도
        # 파서는 읽을 수 있어야 하므로 두 꼴을 다 받는다 — 실행을 거부하는 것은 러너의 몫이다
        # (stay_boot.js `staleStep`).
        self.assertIn((first["text"], first["row"]), [("룸 추가", None), ("편집", "스탠다드")])
        self.assertEqual((first["drawer"], first["times"]), (False, 1))
        self.assertEqual((second["text"], second["group"], second["drawer"], second["times"]),
                         ("침대 행 추가", "침대 구성", True, 1))

    def test_guide_vintage_is_consistent(self):
        """예시 지시서가 옛 화면 기준이면 통째로, 새 화면 기준이면 통째로여야 한다.

        섞이면 러너가 반만 실행하고 멈춘다 — ERP 2026-09-04 뒤 화면에는 고쳐 쓸
        `기본 오퍼`·`스탠다드` 가 없으므로 그 단계는 stay_boot.js `staleStep` 이 거부한다.
        예시가 아직 옛 것이어도 이 시험은 통과한다(옛 표시가 **모두** 있으면 옛 지시서다).
        """
        heads = json.dumps([s["head"] for s in self.steps], ensure_ascii=False)
        kinds = [s["kind"] for s in self.steps]
        old_marks = ["오퍼 고치기" in kinds, "기본 오퍼" in heads, "스탠다드" in heads]
        self.assertIn(sum(old_marks), (0, len(old_marks)),
                      "옛 화면 표시와 새 화면 표시가 섞였습니다: 오퍼 고치기=%s · 기본 오퍼=%s · 스탠다드=%s"
                      % tuple(old_marks))
        if not any(old_marks):
            # 새 화면 기준이면 첫 오퍼도 [오퍼 추가] 로 만든다
            self.assertIn("오퍼 만들기", kinds)

    def test_longtexts(self):
        lt = only_step(self.steps, "기본정보 글 입력")["longtexts"]
        self.assertEqual([x["label"] for x in lt], ["한줄설명", "상세설명"])
        self.assertGreater(len(lt[0]["text"]), 10)

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
                    # 단계 번호는 빼고 본다 — 예시가 다시 그려지면 번호가 밀린다
                    changed.append((a["kind"], fb["label"], fb["value"]))
        self.assertEqual(changed, [
            ("호텔 만들기", "호텔명", "__skills__우에노 토우가네야 호텔"),
            ("기본정보 글 입력", "상품명", "__skills__우에노 토우가네야 호텔"),
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
