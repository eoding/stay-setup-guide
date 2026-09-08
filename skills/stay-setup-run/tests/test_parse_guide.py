#!/usr/bin/env python3
"""parse_guide.py 검증 — 예시(우에노 토우가네야)의 원고(`_원고/manual.md`)와 지시서 HTML 을 함께 본다.

실행 입력은 **검사 도장이 찍힌 지시서 HTML 하나뿐**이다(문지기: `TestGuideGate`). 원고는 CLI 가
받지 않으므로, 원고와 지시서가 같은 steps 를 내는지 보는 시험은 내부 파서를 직접 부른다.

    python3 -m pytest skills/stay-setup-run/tests/test_parse_guide.py
    python3 skills/stay-setup-run/tests/test_parse_guide.py
"""

import hashlib
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
GUIDE_SKILL = REPO / "skills" / "stay-setup-guide"
RENDER = GUIDE_SKILL / "scripts" / "render_card.py"
EXAMPLE = GUIDE_SKILL / "examples" / "우에노_토우가네야"
MANUAL = EXAMPLE / "_원고" / "manual.md"
GUIDE_HTML = EXAMPLE / "우에노_토우가네야_입력지시서.html"

sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(RENDER.parent))
import parse_guide  # noqa: E402
import render_card  # noqa: E402


def parse(path, **kw):
    """파일 하나를 읽어 (제목, steps) — 확장자로 파서를 고른다.

    CLI 는 HTML 만 받지만, 여기서는 md 와 HTML 이 같은 steps 를 내는지 봐야 하므로 둘 다 읽는다.
    """
    src = Path(path)
    text = src.read_text(encoding="utf-8")
    title, raws = (parse_guide.parse_markdown(text) if src.suffix.lower() == ".md"
                   else parse_guide.parse_html(text))
    steps = [parse_guide.build_step(r) for r in raws]
    if kw.get("prefix"):
        parse_guide.apply_title_prefix(steps, kw["prefix"])
    return title, steps


def render_guide(dirpath, md_text, name="시험_입력지시서.html", check="ok", sha=None, stamp=True):
    """작은 manual 본문을 HTML 지시서로 렌더해 `dirpath` 에 둔다. 만든 경로를 돌려준다.

    도장은 **여기서 손으로 박는다** — 검사기(`check_manual.py`)를 돌리지 않는다. 이 시험들이
    보는 것은 문지기 뒤의 파서·훑기이고, 문지기 자체는 `TestGuideGate` 가 진짜 렌더로 본다.
    `check="fail"`, `stamp=False`, `sha=...` 로 거부되는 지시서도 만들 수 있다.
    """
    digest = sha or hashlib.sha256(md_text.encode("utf-8")).hexdigest()
    mark = render_card.build_stamp(digest, check == "ok") if stamp else None
    html_text, _ = render_card.render_card(md_text, "manual.md", None, None, None, mark)  # 원고 파일 이름
    out = Path(dirpath) / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")
    return out


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

    def test_row_label_takes_only_canonical_form(self):
        """반복 행 칸 이름의 정본 꼴은 `<칸 이름> <N> · <하위 칸>` 하나뿐이다.

        `stay_helper.js` 의 `splitRepeat` 과 같은 판정이어야 한다 — 한쪽만 반복 행으로 읽으면
        N번째 행이 아니라 첫 행에 값이 들어간다.
        """
        from parse_guide import ROW_LABEL_RE
        # 눈으로 가릴 수 없는 글자(가운뎃점 종류·붙임 빈칸)는 **코드포인트로 적는다** —
        # 글자 그대로 적으면 편집·복사 과정에서 정본 꼴로 바뀌어 시험이 조용히 무력해진다.
        SP, DOT = "\u0020", "\u00b7"          # 보통 빈칸 · 가운뎃점(U+00B7)
        NBSP, FULL_DOT = "\u00a0", "\u30fb"   # 붙임 빈칸 · 전각 가운뎃점(U+30FB)
        canonical = "침대 구성" + SP + "1" + SP + DOT + SP + "침대 종류"
        m = ROW_LABEL_RE.match(canonical)
        self.assertIsNotNone(m, canonical)
        self.assertEqual((m.group(1), m.group(2), m.group(3)), ("침대 구성", "1", "침대 종류"))
        bad = {
            "가운뎃점 뒤 빈칸 없음": "침대 구성" + SP + "1" + SP + DOT + "침대 종류",
            "가운뎃점 앞 빈칸 없음": "침대 구성" + SP + "1" + DOT + SP + "침대 종류",
            "빈칸 둘": "침대 구성" + SP + SP + "1" + SP + DOT + SP + "침대 종류",
            "전각 가운뎃점(U+30FB)": "침대 구성" + SP + "1" + SP + FULL_DOT + SP + "침대 종류",
            "숫자 앞 빈칸 없음": "침대 구성" + "1" + SP + DOT + SP + "침대 종류",
            "숫자 앞 붙임 빈칸(NBSP)": "침대 구성" + NBSP + "1" + SP + DOT + SP + "침대 종류",
            "가운뎃점 둘레가 붙임 빈칸(NBSP)": "침대 구성" + SP + "1" + NBSP + DOT + NBSP + "침대 종류",
            "숫자 없음 — 반복 행이 아니다": "연령별 단가" + SP + DOT + SP + "초등학생",
        }
        for why, sample in bad.items():
            self.assertIsNone(ROW_LABEL_RE.match(sample), "%s: %r" % (why, sample))

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
            # 원고가 같은 폴더에 있으면 파서가 그것을 먼저 읽으므로 지시서만 따로 둔다
            copy = Path(tmp) / GUIDE_HTML.name
            shutil.copy(GUIDE_HTML, copy)
            _, from_html = parse(copy)
        _, from_md = parse(MANUAL)
        self.assertEqual(len(from_html), len(from_md))
        for a, b in zip(from_md, from_html):
            self.assertEqual(comparable(a), comparable(b), "%d단계가 다릅니다" % a["no"])

    def test_html_input_stays_html(self):
        """`_원고/manual.md` 가 있어도 읽는 것은 지시서 HTML 이다 — 검사를 통과한 쪽이 실행 입력이다."""
        src, source = parse_guide.resolve_input(str(GUIDE_HTML))
        self.assertEqual((src, source), (GUIDE_HTML, "html"))

    def test_directory_input(self):
        src, source = parse_guide.resolve_input(str(EXAMPLE))
        self.assertEqual((src, source), (GUIDE_HTML, "html"))

    def test_example_stamp_matches_manual(self):
        """예시 지시서의 도장은 `_원고/manual.md` 와 맞고 검사도 통과한 것이다(다시 렌더하면 갱신된다)."""
        stamp = parse_guide.verify_stamp(GUIDE_HTML, GUIDE_HTML.read_text(encoding="utf-8"))
        self.assertEqual(stamp["check"], "ok")
        self.assertEqual(stamp["sha256"], parse_guide.file_sha256(MANUAL))


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
            r = run(str(GUIDE_HTML), "--title-prefix", "__skills__", "-o", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(doc["guide"]["title_prefix"], "__skills__")
        self.assertEqual(doc["guide"]["source"], "html")
        self.assertEqual(doc["guide"]["share_folder"], "우에노_토우가네야")
        self.assertEqual(doc["guide"]["stamp"]["check"], "ok")
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
        render_guide(self.dir, MINI)

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


# dict-audit 과 합의한 머리 줄 키를 그대로 쓴다 — `탭:` · `카드:` · `버튼:` 이고
# 저장 버튼은 마지막 `→ [ … ]` 줄이다(이 갈래에 `화면:` 은 쓰지 않는다).
# 부과금 단계의 줄 차례도 화면 차례 그대로다:
#   종류 → 이름 → 부과 방식 → 부과 단위 → 정액 금액 → 적용 룸 scope → 연령별 단가 → 시간대별 요율 → 설명
# 카드를 세우는 것은 **[부과 단위]=인당 + [부과 방식]=정액** 이다(화면이 그때만 그 칸을 세운다).
AGE_BAND = """# 시험 호텔 — 입력 지시서

## 1. 연령 구간 만들기 (1번째, 초등학생)
탭: `오퍼`
카드: `2026 계약`
버튼: [연령 구간 추가]

| 칸 | 값 |
|---|---|
| 밴드 코드 | CHILD |
| 노출명 | 초등학생 |
| 최소 연령 | 0 |
| 최대 연령 | 11.99 |
| 방 인원수에 포함 | 체크 |
| 요금 기준 유형 | 선택: 성인 요금의 % |
| 요금 기준 값 | 50 |
| 상세(자유텍스트) | 비움 |

→ [추가]

## 2. 부과금 추가 (1번째, 갈라디너)
탭: `부과금`
카드: `2026 계약`
버튼: [부과금 추가]

| 칸 | 값 |
|---|---|
| 종류 | 선택: 기타 |
| 이름 | 갈라디너 |
| 부과 방식 | 선택: 정액 |
| 부과 단위 | 선택: 인당 |
| 정액 금액 | 100 |
| 적용 룸 scope | 비움 |
| 연령별 단가 · 초등학생 | 50 |
| 연령별 단가 · 유아 | 0 |
| 설명 | 비움 |

→ [추가]
"""

BAD_ORDER = AGE_BAND.replace(
    "| 적용 룸 scope | 비움 |\n| 연령별 단가 · 초등학생 | 50 |",
    "| 연령별 단가 · 초등학생 | 50 |\n| 적용 룸 scope | 비움 |")

#: [부과 단위] 줄이 아예 없으면 그 카드는 화면에 설 일이 없다
NO_UNIT = AGE_BAND.replace("| 부과 단위 | 선택: 인당 |\n", "")

STALE = """# 시험 호텔 — 입력 지시서

## 1. 오퍼 고치기 (기본 오퍼)
탭: `오퍼`
버튼: `기본 오퍼` 행의 [편집]

| 칸 | 값 |
|---|---|
| 오퍼명 | 2026 계약 |

→ [저장]
"""

#: 금지된 갈래 — 합격선이 판매 시작 전 🟡 0 이라 사유를 적어 넘기는 길이 없다
WARN_SKIP = """# 시험 호텔 — 입력 지시서

## 1. 경고 넘어가기 (오퍼에 취소정책이 없습니다)
화면: 편집 화면 맨 위 점검 배너
버튼: 노란 목록에서 `오퍼에 취소정책이 없습니다` 가 들어간 줄의 [이건 넘어가기]

| 칸 | 값 |
|---|---|
| 사유 | 계약서에 없음 |

→ [넘어가기]
"""


class TestNewStepKinds(unittest.TestCase):
    """2026-09-04 신설 화면 — 연령 구간 · 부과금의 연령별 단가.

    예시 지시서가 아니라 여기 붙인 작은 본문을 쓴다. 예시는 `stay-setup-guide` 쪽이 다시 그리는
    파일이라, 거기에 기대면 그쪽이 손댈 때마다 이 시험이 깨진다.
    """

    @classmethod
    def setUpClass(cls):
        _, cls.steps = parse_guide.parse_markdown(AGE_BAND)
        cls.steps = [parse_guide.build_step(r) for r in cls.steps]

    def test_age_band_kind_and_fields(self):
        band = only_step(self.steps, "연령 구간 만들기")
        self.assertEqual(band["head"]["tab"], "오퍼")
        self.assertEqual(band["head"]["card"], "2026 계약")
        self.assertEqual(band["submit"], "추가")
        # 여는 버튼은 `버튼:` 줄에서 읽는다 — 러너의 `runStep` 이 쓰는 것이 이 값이다
        self.assertEqual([b["text"] for b in band["head"]["buttons_parsed"]], ["연령 구간 추가"])
        self.assertEqual(field_by_label(band, "밴드 코드")["value"], "CHILD")
        self.assertEqual(field_by_label(band, "노출명")["value"], "초등학생")
        self.assertEqual(field_by_label(band, "방 인원수에 포함")["kind"], "check")
        basis = field_by_label(band, "요금 기준 유형")
        self.assertEqual((basis["kind"], basis["value"]), ("select", "성인 요금의 %"))
        self.assertEqual(field_by_label(band, "상세(자유텍스트)")["kind"], "empty")

    def test_age_band_kind_is_known(self):
        self.assertIn("연령 구간 만들기", parse_guide.KNOWN_KINDS)

    def test_age_rate_rows_are_plain_fields(self):
        """`연령별 단가 · <노출명>` 은 반복 행이 아니다 — 숫자가 없으니 `row_group` 이 붙으면 안 된다."""
        charge = only_step(self.steps, "부과금 추가")
        f = field_by_label(charge, "연령별 단가 · 초등학생")
        self.assertEqual((f["kind"], f["value"]), ("typed", "50"))
        self.assertNotIn("row_group", f)
        # 0 은 "무료" 라는 뜻이고 비움과 다르다 — 파서가 비움으로 접으면 안 된다
        self.assertEqual(field_by_label(charge, "연령별 단가 · 유아")["value"], "0")

    def test_preflight_is_clean(self):
        pre = parse_guide.preflight(self.steps)
        self.assertEqual(pre["stale"], [])
        self.assertEqual(pre["charge_order"], [])
        self.assertEqual(pre["unknown_kinds"], [])


class TestPreflight(unittest.TestCase):
    def _steps(self, text):
        _, raws = parse_guide.parse_markdown(text)
        return [parse_guide.build_step(r) for r in raws]

    def test_stale_guide_is_flagged(self):
        pre = parse_guide.preflight(self._steps(STALE))
        self.assertEqual([x["no"] for x in pre["stale"]], [1])
        self.assertIn("기본 오퍼", pre["stale"][0]["why"])

    def test_age_rate_before_room_scope_is_flagged(self):
        pre = parse_guide.preflight(self._steps(BAD_ORDER))
        self.assertEqual([x["no"] for x in pre["charge_order"]], [2])
        self.assertIn("적용 룸 scope", pre["charge_order"][0]["why"])

    def test_age_rate_without_charge_unit_is_flagged(self):
        """카드를 세우는 것은 [부과 단위]=인당 이다 — [부과 방식] 은 정액/정률 축이라 다른 칸이다."""
        pre = parse_guide.preflight(self._steps(NO_UNIT))
        self.assertEqual([x["no"] for x in pre["charge_order"]], [2])
        self.assertIn("부과 단위", pre["charge_order"][0]["why"])

    def test_unknown_kind_is_reported_not_blocking(self):
        steps = self._steps(AGE_BAND)
        steps[0]["kind"] = "우주선 만들기"
        pre = parse_guide.preflight(steps)
        self.assertEqual([x["kind"] for x in pre["unknown_kinds"]], ["우주선 만들기"])
        self.assertEqual(pre["stale"], [])


#: A-seasense 지시서(2026-09-07)가 `그룹에 혜택 추가` 대신 쓴 표기 — 같은 화면(그룹 카드
#: [이 그룹에 혜택 추가])의 다른 제목이다. 러너는 드로어 일반 처리로 이미 실행했지만
#: `--check` 가 "모르는 단계 갈래" 로 알렸다 — `KNOWN_KINDS` 에 이 표기를 더한다.
GROUP_CANDIDATE = """# 시험 호텔 — 입력 지시서

## 1. 택1 그룹 후보 추가 (1번째, 편도 픽업)
탭: `혜택`
카드: `공항 이동 서비스 (숙박일수 조건)`
버튼: [이 그룹에 혜택 추가]

| 칸 | 값 |
|---|---|
| 소속 택1 그룹 | 선택: 공항 이동 서비스 (숙박일수 조건) |
| 혜택 이름 | 공항 → 리조트 편도 픽업 무료 (4박 이상 예약 시) |

→ [추가]
"""


class TestGroupCandidateKind(unittest.TestCase):
    """A-seasense 지시서의 `택1 그룹 후보 추가` — `그룹에 혜택 추가` 의 동의 표기."""

    @classmethod
    def setUpClass(cls):
        _, raws = parse_guide.parse_markdown(GROUP_CANDIDATE)
        cls.steps = [parse_guide.build_step(r) for r in raws]

    def test_title_parses_to_group_candidate_kind(self):
        step = only_step(self.steps, "택1 그룹 후보 추가")
        self.assertEqual(step["head"]["tab"], "혜택")
        self.assertEqual(step["head"]["card"], "공항 이동 서비스 (숙박일수 조건)")
        self.assertEqual(step["submit"], "추가")

    def test_group_candidate_kind_is_known(self):
        self.assertIn("택1 그룹 후보 추가", parse_guide.KNOWN_KINDS)

    def test_preflight_reports_no_unknown_kind(self):
        pre = parse_guide.preflight(self.steps)
        self.assertEqual(pre["unknown_kinds"], [])


def age_band_step(no, name, lo, hi, card="2026 계약"):
    """연령 구간 단계 한 개 — 겹침 시험용."""
    return ("## %d. 연령 구간 만들기 (%d번째, %s)\n"
            "탭: `오퍼`\n카드: `%s`\n버튼: [연령 구간 추가]\n\n"
            "| 칸 | 값 |\n|---|---|\n"
            "| 밴드 코드 | BAND%d |\n| 노출명 | %s |\n"
            "| 최소 연령 | %s |\n| 최대 연령 | %s |\n\n→ [추가]\n"
            % (no, no, name, card, no, name, lo, hi))


def bands_manual(*specs):
    return "# 시험 호텔 — 입력 지시서\n\n" + "\n".join(
        age_band_step(i + 1, *spec) for i, spec in enumerate(specs))


class TestAgeBandOverlap(unittest.TestCase):
    """나이 경계는 **양끝 포함**이다 — 서버(`stay.services.age_band.ranges_overlap`)와 같은 판정.

    러너가 이것을 파일 단계에서 보는 이유는 `staleStep` 과 같다: 겹치는 구간은 그 단계에서
    저장이 막힐 뿐이라, 그때는 앞 단계들이 이미 화면에 만들어져 있다.
    """

    def _overlap(self, md):
        _, raws = parse_guide.parse_markdown(md)
        return parse_guide.preflight([parse_guide.build_step(r) for r in raws])["age_overlap"]

    def test_adjacent_bands_pass(self):
        self.assertEqual(self._overlap(bands_manual(("유아", "0", "5.99"), ("초등학생", "6", "11.99"))), [])

    def test_both_starting_at_zero_fails(self):
        hits = self._overlap(bands_manual(("유아", "0", "5.99"), ("초등학생", "0", "11.99")))
        self.assertEqual([x["no"] for x in hits], [2])
        self.assertIn("1단계", hits[0]["why"])

    def test_touching_boundary_fails(self):
        """`0~6` 과 `6~11.99` 는 만 6세에서 겹친다 — 계약서가 11.99 를 쓰는 이유다."""
        hits = self._overlap(bands_manual(("유아", "0", "6"), ("초등학생", "6", "11.99")))
        self.assertEqual([x["no"] for x in hits], [2])

    def test_different_offers_do_not_collide(self):
        md = bands_manual(("유아", "0", "11.99"), ("초등학생", "0", "11.99", "2027 계약"))
        self.assertEqual(self._overlap(md), [])

    def test_three_bands_report_each_clash_once(self):
        md = bands_manual(("유아", "0", "5.99"), ("초등학생", "0", "11.99"), ("청소년", "6", "11.99"))
        self.assertEqual([x["no"] for x in self._overlap(md)], [2, 3])

    def test_example_guide_has_no_overlap(self):
        _, steps = parse(MANUAL)
        self.assertEqual(parse_guide.preflight(steps)["age_overlap"], [])


# ---------------------------------------------------------------------------
# 2026-09-08 신설 칸 — `박수별 단가(선택)` · `아동 추가 금액 — <노출명>`
#
# 넷 다 **막는** 판정이다: 그대로 실행하면 그 단계에서 반드시 실패하고, 그때는 앞 단계들이
# 이미 화면에 만들어져 있다. 파일 단계에서 걸러 내면 그 되돌리기가 통째로 없어진다.
# 아래 본문은 넷을 다 통과하는 정본이고, 실패 짝은 한 줄만 바꿔 만든다.
# ---------------------------------------------------------------------------
SEASON_CHILD = """# 시험 호텔 — 입력 지시서

## 1. 연령 구간 만들기 (1번째, 소아)
탭: `오퍼`
카드: `2026 계약`
버튼: [연령 구간 추가]

| 칸 | 값 |
|---|---|
| 밴드 코드 | CHD |
| 노출명 | 소아 |
| 최소 연령 (만 나이) | 5 |
| 최대 연령 (만 나이) | 11.99 |
| 방 인원수에 포함 | 체크 |
| 요금 기준 유형 | 선택: 정액 |
| 요금 기준 값 | 23.18 |

→ [추가]

## 2. 시즌 가격 채우기 (1회차, Low × Deluxe Garden)
탭: `시즌`
카드: `Low`
버튼: [가격]

| 칸 | 값 |
|---|---|
| 판매 단가(공급 통화) | 92.00 |
| 대상 룸 | 선택: 2026 계약 · Deluxe Garden |
| 인원 조합(선택) | A2,A3 |
| 인원 조합별 조정(선택) | A3:+30 |
| 박수별 단가(선택) | 3:100,5:90 |
| 아동 추가 금액 — 소아 | 23.18 |
| 이미 값이 있는 날도 덮기 | 해제 |

→ [이 단가로 깔기]
"""


def swap(old, new, text=None):
    """정본 본문에서 한 줄만 바꾼다 — 실패 짝은 늘 한 군데만 다르다."""
    text = SEASON_CHILD if text is None else text
    assert old in text, old
    return text.replace(old, new)


class TestNewFieldPreflight(unittest.TestCase):
    """신설 칸 넷의 판정. 통과/실패를 짝으로 본다."""

    def _pre(self, text):
        _, raws = parse_guide.parse_markdown(text)
        return parse_guide.preflight([parse_guide.build_step(r) for r in raws])

    def _why(self, text, bucket="value_format"):
        hits = self._pre(text)[bucket]
        self.assertEqual(len(hits), 1, hits)
        return hits[0]["why"]

    # --- 통과 짝 ---------------------------------------------------------
    def test_clean_guide_passes(self):
        pre = self._pre(SEASON_CHILD)
        self.assertEqual(pre["value_format"], [])
        self.assertEqual(pre["step_order"], [])
        self.assertEqual(pre["unknown_kinds"], [])
        self.assertEqual(pre["stale"], [])

    def test_new_fields_land_in_steps(self):
        """새 칸은 화이트리스트 없이 그대로 실린다 — 러너는 라벨로 찾는다."""
        _, raws = parse_guide.parse_markdown(SEASON_CHILD)
        fill = [parse_guide.build_step(r) for r in raws][1]
        self.assertEqual(field_by_label(fill, "박수별 단가(선택)")["value"], "3:100,5:90")
        child = field_by_label(fill, "아동 추가 금액 — 소아")
        self.assertEqual((child["kind"], child["value"]), ("typed", "23.18"))

    def test_child_extra_label_re_reads_the_display_name(self):
        """구분자는 EM DASH 가 정본이지만 EN DASH·하이픈·가운뎃점도 받는다(원고 오타로 안 멈춘다)."""
        for label, name in (("아동 추가 금액 — 소아", "소아"), ("아동 추가 금액 – 소아", "소아"),
                            ("아동 추가 금액 - 소아", "소아"), ("아동 추가 금액 · 소아", "소아")):
            m = parse_guide.CHILD_EXTRA_LABEL_RE.match(label)
            self.assertIsNotNone(m, label)
            self.assertEqual(m.group("name"), name, label)
        self.assertIsNone(parse_guide.CHILD_EXTRA_LABEL_RE.match("아동 정책 표기"))

    def test_auto_child_extra_row_still_passes(self):
        """`성인 요금의 %` 구간의 칸은 `자동 입력됨 · 그대로 둠` 이다 — 값 판정에 걸리지 않는다."""
        md = swap("| 아동 추가 금액 — 소아 | 23.18 |",
                  "| 아동 추가 금액 — 소아 | 자동 입력됨 · 그대로 둠 |")
        _, raws = parse_guide.parse_markdown(md)
        steps = [parse_guide.build_step(r) for r in raws]
        self.assertEqual(field_by_label(steps[1], "아동 추가 금액 — 소아")["kind"], "auto")
        self.assertEqual(parse_guide.preflight(steps)["value_format"], [])

    # --- 1. 박수별 단가 꼴 -------------------------------------------------
    def test_los_prices_with_sign_is_flagged(self):
        why = self._why(swap("| 박수별 단가(선택) | 3:100,5:90 |",
                             "| 박수별 단가(선택) | 3:+100,5:90 |"))
        self.assertIn("박수별 단가", why)
        self.assertIn("부호", why)

    def test_los_prices_one_night_is_flagged(self):
        why = self._why(swap("| 박수별 단가(선택) | 3:100,5:90 |",
                             "| 박수별 단가(선택) | 1:100,5:90 |"))
        self.assertIn("2 이상", why)

    def test_los_prices_duplicate_nights_is_flagged(self):
        why = self._why(swap("| 박수별 단가(선택) | 3:100,5:90 |",
                             "| 박수별 단가(선택) | 3:100,3:90 |"))
        self.assertIn("두 번", why)

    def test_los_prices_without_colon_is_flagged(self):
        why = self._why(swap("| 박수별 단가(선택) | 3:100,5:90 |",
                             "| 박수별 단가(선택) | 100,90 |"))
        self.assertIn("박수:1박 단가", why)

    def test_empty_los_prices_passes(self):
        self.assertEqual(
            self._pre(swap("| 박수별 단가(선택) | 3:100,5:90 |", "| 박수별 단가(선택) | 비움 |"))["value_format"], [])

    # --- 2. 인원 조합의 옛 숫자 키 ----------------------------------------
    def test_bare_number_occupancy_keys_is_flagged(self):
        why = self._why(swap("| 인원 조합(선택) | A2,A3 |", "| 인원 조합(선택) | 2,3 |"))
        self.assertIn("인원 조합", why)
        self.assertIn("A2,A3", why)

    def test_bare_number_adjust_key_is_flagged(self):
        why = self._why(swap("| 인원 조합별 조정(선택) | A3:+30 |", "| 인원 조합별 조정(선택) | 3:+14 |"))
        self.assertIn("인원 조합별 조정", why)

    def test_child_occupancy_key_passes(self):
        """아동 조합(`A2C2_CHD`)은 자동 전개로 안 나와 직접 적는다 — 막으면 안 된다."""
        self.assertEqual(
            self._pre(swap("| 인원 조합(선택) | A2,A3 |", "| 인원 조합(선택) | A2,A2C2_CHD |"))["value_format"], [])

    # --- 3. 밴드 코드 꼴 ---------------------------------------------------
    def test_band_code_with_underscore_is_flagged(self):
        why = self._why(swap("| 밴드 코드 | CHD |", "| 밴드 코드 | CHILD_1 |"))
        self.assertIn("밴드 코드", why)
        self.assertIn("2~8자", why)

    def test_band_code_too_long_or_short_is_flagged(self):
        for bad in ("C", "CHILDBAND9"):
            with self.subTest(code=bad):
                self.assertIn("밴드 코드", self._why(swap("| 밴드 코드 | CHD |", "| 밴드 코드 | %s |" % bad)))

    def test_band_code_in_hangul_is_flagged(self):
        self.assertIn("밴드 코드", self._why(swap("| 밴드 코드 | CHD |", "| 밴드 코드 | 소아 |")))

    def test_lowercase_band_code_passes(self):
        """서버가 대문자로 굳힌다 — 소문자로 적었다고 막지 않는다."""
        self.assertEqual(self._pre(swap("| 밴드 코드 | CHD |", "| 밴드 코드 | chd |"))["value_format"], [])

    # --- 4. `아동 추가 금액` 줄과 `연령 구간 만들기` 의 차례 ----------------
    def test_age_band_after_season_fill_is_flagged(self):
        """단계 차례를 뒤집으면 그 칸이 화면에 서지 않는다(유료 구간이 아직 없다)."""
        _, raws = parse_guide.parse_markdown(SEASON_CHILD)
        steps = [parse_guide.build_step(r) for r in raws]
        steps[0]["no"], steps[1]["no"] = 2, 1          # 연령 구간이 뒤로 밀렸다
        hits = parse_guide.preflight(steps)["step_order"]
        self.assertEqual([x["no"] for x in hits], [1])
        self.assertIn("연령 구간 만들기", hits[0]["why"])
        self.assertIn("소아", hits[0]["why"])

    def test_child_extra_without_any_age_band_is_flagged(self):
        md = swap("## 1. 연령 구간 만들기 (1번째, 소아)", "## 1. 룸 만들기 (1번째, Deluxe Garden)")
        why = self._why(md, "step_order")
        self.assertIn("`연령 구간 만들기` 단계가 없습니다", why)

    def test_season_fill_without_child_row_passes(self):
        """아동 정책이 없는 계약 — 그 줄이 없으면 연령 구간 단계도 있을 이유가 없다."""
        md = swap("| 아동 추가 금액 — 소아 | 23.18 |\n", "")
        md = swap("## 1. 연령 구간 만들기 (1번째, 소아)", "## 1. 룸 만들기 (1번째, Deluxe Garden)", md)
        self.assertEqual(self._pre(md)["step_order"], [])


class TestCheckModeStale(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = Path(self.tmp) / "시험"
        (self.dir / "사진").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_check_fails_on_stale_guide(self):
        render_guide(self.dir, STALE)
        r = run(str(self.dir), "--check")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("러너가 거부하는 단계: 1", r.stdout)

    def test_check_passes_on_new_screen_guide(self):
        render_guide(self.dir, AGE_BAND)
        r = run(str(self.dir), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("러너가 거부하는 단계: 0", r.stdout)
        self.assertIn("줄 차례가 어긋난 단계: 0", r.stdout)
        self.assertIn("나이 범위가 겹치는 단계: 0", r.stdout)

    def test_check_fails_on_warn_skip_step(self):
        """`경고 넘어가기` 는 금지된 갈래다 — 브라우저를 열기 전에 막는다(🟡 0 이 합격선)."""
        render_guide(self.dir, WARN_SKIP)
        r = run(str(self.dir), "--check")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("러너가 거부하는 단계: 1", r.stdout)
        self.assertIn("금지된 단계", r.stdout)
        self.assertNotIn("러너가 모르는 단계 갈래", r.stdout)

    def test_check_fails_on_overlapping_bands(self):
        render_guide(self.dir, bands_manual(("유아", "0", "5.99"), ("초등학생", "0", "11.99")))
        r = run(str(self.dir), "--check")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("나이 범위가 겹치는 단계: 1", r.stdout)

    def test_check_passes_on_new_child_fields(self):
        render_guide(self.dir, SEASON_CHILD)
        r = run(str(self.dir), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("값 형식이 어긋난 단계: 0", r.stdout)
        self.assertIn("단계 차례가 어긋난 단계: 0", r.stdout)

    def test_check_fails_on_bad_los_prices(self):
        render_guide(self.dir, swap("| 박수별 단가(선택) | 3:100,5:90 |",
                                    "| 박수별 단가(선택) | 3:+100 |"))
        r = run(str(self.dir), "--check")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("값 형식이 어긋난 단계: 1", r.stdout)

    def test_preflight_lands_in_json(self):
        render_guide(self.dir, AGE_BAND)
        out = Path(self.tmp) / "steps.json"
        r = run(str(self.dir), "-o", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(doc["guide"]["preflight"]["stale"], [])


#: 검사기(`check_manual.py`)를 그대로 통과하는 가장 작은 지시서 — 0단계 세 줄만 있다.
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


class TestGuideGate(unittest.TestCase):
    """실행 입력은 **검사를 통과한 HTML 지시서** 하나뿐이다.

    원고를 직접 받으면 사람이 검토한 지시서를 건너뛸 수 있으므로, CLI 는 원고를 받지 않고
    지시서의 도장(`stay-guide-stamp`)을 본다. 여기서는 `render_card.py` 를 진짜로 돌려
    도장이 찍힌 지시서를 만든다.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = Path(self.tmp) / "시험"
        (self.dir / "사진").mkdir(parents=True)
        self.md = self.dir / "manual.md"
        self.md.write_text(ZERO_OK, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def render(self, *extra):
        """render_card.py 를 그대로 돌려 도장 찍힌 HTML 을 만든다 (검사기도 함께 돈다)."""
        out = self.dir / "시험_입력지시서.html"
        r = subprocess.run([sys.executable, str(RENDER), str(self.md), "-o", str(out), *extra],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return out, r

    def test_markdown_input_is_refused(self):
        r = run(str(self.md), "--check")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("manual.md 는 원고다 — 실행 입력이 아니다", r.stderr)

    def test_missing_stamp_is_refused(self):
        out = render_guide(self.dir, ZERO_OK, stamp=False)
        r = run(str(out), "--check")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("지시서에 검사 도장이 없다", r.stderr)

    def test_failed_check_stamp_is_refused(self):
        """검사기를 통과하지 못한 지시서(`check=fail`)는 브라우저를 열기 전에 막는다."""
        self.md.write_text(STALE, encoding="utf-8")
        out, r = self.render()
        self.assertIn("check=fail", out.read_text(encoding="utf-8")[:2000])
        self.assertIn("검사기를 통과하지 못했다", r.stderr)
        got = run(str(out), "--check")
        self.assertEqual(got.returncode, 2, got.stdout + got.stderr)
        self.assertIn("검사기를 통과하지 못한 지시서다", got.stderr)

    def test_stale_manual_is_refused(self):
        """지시서를 만든 뒤 원고를 고쳤으면 그 지시서는 옛 계획이다 — 다시 렌더해야 한다."""
        out, _ = self.render()
        self.md.write_text(ZERO_OK + "\n<!-- 나중에 고친 자국 -->\n", encoding="utf-8")
        r = run(str(out), "--check")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("원고(manual.md)가 지시서보다 새롭다", r.stderr)

    def test_good_html_is_accepted(self):
        out, _ = self.render()
        r = run(str(out), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("검사 도장: ok", r.stdout)
        self.assertIn("단계 3개", r.stdout)

    def test_folder_input_picks_the_one_html(self):
        self.render()
        r = run(str(self.dir), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("검사 도장: ok", r.stdout)

    def test_folder_with_two_guides_is_refused(self):
        self.render()
        shutil.copy(self.dir / "시험_입력지시서.html", self.dir / "다른_입력지시서.html")
        r = run(str(self.dir), "--check")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("2개", r.stderr)

    def test_stamp_lands_in_json(self):
        out, _ = self.render()
        target = Path(self.tmp) / "steps.json"
        r = run(str(out), "-o", str(target))
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = json.loads(target.read_text(encoding="utf-8"))
        stamp = doc["guide"]["stamp"]
        self.assertEqual(stamp["check"], "ok")
        self.assertEqual(stamp["version"], "v1")
        self.assertEqual(stamp["sha256"], parse_guide.file_sha256(self.md))


class TestDraftLayoutGate(unittest.TestCase):
    """새 공유 폴더 배치 — 원고는 `_원고/manual.md`, 지시서는 맨 위 `<이름>_입력지시서.html`.

    도장의 신선도 검사는 `_원고/manual.md` 를 먼저 보고, 없으면 옛 자리 `manual.md` 를 본다.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = Path(self.tmp) / "시험"
        (self.dir / "사진").mkdir(parents=True)
        (self.dir / "_원고").mkdir()
        self.md = self.dir / "_원고" / "manual.md"
        self.md.write_text(ZERO_OK, encoding="utf-8")
        self.guide = self.dir / "시험_입력지시서.html"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def render(self):
        """`-o` 없이 렌더하면 지시서가 공유 폴더 맨 위에 놓인다."""
        r = subprocess.run([sys.executable, str(RENDER), str(self.md)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.guide.is_file(), r.stdout)
        return r

    def test_find_manual_prefers_the_draft_folder(self):
        (self.dir / "manual.md").write_text("옛 자리", encoding="utf-8")
        self.assertEqual(parse_guide.find_manual(self.dir), self.md)

    def test_find_manual_falls_back_to_the_old_flat_place(self):
        self.md.unlink()
        legacy = self.dir / "manual.md"
        legacy.write_text(ZERO_OK, encoding="utf-8")
        self.assertEqual(parse_guide.find_manual(self.dir), legacy)

    def test_good_guide_is_accepted(self):
        self.render()
        r = run(str(self.dir), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("검사 도장: ok", r.stdout)

    def test_stale_draft_is_refused(self):
        """지시서를 만든 뒤 `_원고/manual.md` 를 고치면 그 지시서는 옛 계획이다."""
        self.render()
        self.md.write_text(ZERO_OK + "\n<!-- 나중에 고친 자국 -->\n", encoding="utf-8")
        r = run(str(self.guide), "--check")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("원고(manual.md)가 지시서보다 새롭다", r.stderr)

    def test_draft_folder_is_not_mistaken_for_a_guide(self):
        """폴더 입력은 맨 위의 `*_입력지시서.html` 만 본다 — `_원고/` 안은 보지 않는다."""
        self.render()
        shutil.copy(self.guide, self.dir / "_원고" / "옛_입력지시서.html")
        r = run(str(self.dir), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
