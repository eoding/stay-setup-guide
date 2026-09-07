#!/usr/bin/env python3
"""parse_guide.py — 지시서(`<이름>_입력지시서.html`) → 실행 계획(`steps.json`).

지시서는 담당자가 읽고 따라 치는 산출물이고, 실행 계획은 그 지시서에서 뽑아낸 **러너 내부 파일**이다
(자동 생성 · 사람이 손대지 않는다 · `<이름>_실행/` 에 산다). 러너는 지시서 HTML 만 읽는다 —
원고(`_원고/manual.md`)는 실행 입력이 아니다.

한 단계(`## N. 제목`) = 저장 버튼 한 번. 단계 안에는:

    화면:/탭:/카드:/블록:/버튼:/폴더:/주의:   머리 줄 (버튼은 여러 줄)
    | 칸 | 값 |                              2열 고정 표
    <라벨>:  +  펜스 블록                     긴 글 (상세설명·설명·날짜 나열 …)
    파일 선택 → 아래 파일  +  `- a.jpg`       사진 목록
    → [저장]                                  저장 버튼

원고(manual.md)와 render_card.py 가 만든 지시서 HTML 은 같은 steps 를 낸다. 그래도 **실행 입력은
지시서 HTML 하나뿐**이다: `render_card.py` 가 `<head>` 에 박은 검사 도장

    <meta name="stay-guide-stamp" content="v1;sha256=<원고 바이트의 sha256>;check=<ok|fail>;rendered=<날짜>">

이 없거나, `check=fail` 이거나, 같은 공유 폴더의 원고(`_원고/manual.md`, 옛 자리면 `manual.md`)의
sha256 이 도장과 다르면 **거부하고 2 로 끝낸다**. 사람이 검토한 지시서만 실행에 들어가게 하려는
것이다 — 원고를 직접 주면 검사기를 건너뛸 수 있다.

사용법:
    python3 parse_guide.py <<이름>_입력지시서.html | 공유 폴더>
        [--photos DIR] [--title-prefix STR] [-o <이름>_실행/steps.json] [--check]
"""

import argparse
import hashlib
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

HEAD_KEYS = ("화면", "탭", "카드", "블록", "버튼", "폴더", "주의")
HEAD_FIELD = {"화면": "screen", "탭": "tab", "카드": "card", "블록": "block",
              "폴더": "folder", "주의": "notice"}
BACKTICK_FREE = {"탭", "카드", "블록", "폴더"}

STEP_RE = re.compile(r"^##\s+(\d+)\.\s*(.+?)\s*$")
HEAD_RE = re.compile(r"^(%s)\s*:\s*(.*)$" % "|".join(HEAD_KEYS))
SUBMIT_RE = re.compile(r"^→\s*\[(.+)\]\s*$")
LABEL_RE = re.compile(r"^([^|`#\-→\s].*?)\s*:\s*$")
LIST_ITEM_RE = re.compile(r"^-\s+(.*\S)\s*$")
FENCE_RE = re.compile(r"^(```|~~~)")
FILENAME_RE = re.compile(r"^[\w][\w.\-]*\.(?:jpg|jpeg|png|gif|webp)$", re.IGNORECASE)
PHOTO_ITEM_RE = re.compile(
    r"^(?P<name>[\w][\w.\-]*\.(?:jpg|jpeg|png|gif|webp))"
    r"(?:\s*[—–-]+\s*출처\s*:\s*(?P<url>\S+))?\s*$", re.IGNORECASE)
SELECT_RE = re.compile(r"^선택\s*:\s*(.*)$")
FILE_RE = re.compile(r"^파일\s*:\s*(.*)$")
#: 반복 행 칸 이름의 **정본 꼴**은 `<칸 이름> <N> · <하위 칸>` 이다 — 빈칸은 하나씩이고
#: 가운뎃점은 앞뒤에 빈칸이 있는 U+00B7 이다. 지시서 검사기·`stay_helper.js` `splitRepeat` 와
#: **한 글자도 다르면 안 된다** — 한쪽만 반복 행으로 읽으면 N번째 행이 아니라 첫 행에 값이 들어간다.
ROW_LABEL_RE = re.compile(r"^(\S(?:.*?\S)?) (\d+) · (.+)$")
AUTO_MARKERS = ("자동 입력됨", "자동입력됨")


# ---------------------------------------------------------------------------
# 값·라벨·버튼 해석 (원고 manual.md 와 지시서 HTML 이 함께 쓴다)
# ---------------------------------------------------------------------------

def split_options(body):
    """다중 선택 값을 나눈다 — 괄호 밖의 `, ` 에서만 자른다."""
    parts, buf, depth = [], [], 0
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0 and i + 1 < n and body[i + 1] == " " \
                and i + 2 < n and not body[i + 2].isspace():
            parts.append("".join(buf).strip())
            buf = []
            i += 2
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf).strip())
    parts = [p for p in parts if p]
    return parts


NEAR_MISS = {"선택", "파일", "체크됨", "체크함", "해제됨", "해제함",
             "비우기", "빈칸", "자동", "자동입력", "자동 입력"}
LOOSE_MARK_RE = re.compile(r"^(선택|파일)\s*[:：]\s*")


def looks_unknown(raw):
    """어휘 낱말을 흉내 냈지만 정해진 표기가 아닌 값 — 사람이 봐야 한다."""
    if raw in NEAR_MISS:
        return True
    return bool(LOOSE_MARK_RE.match(raw)) and not (SELECT_RE.match(raw) or FILE_RE.match(raw))


def classify_value(raw):
    """값 셀 하나를 {kind, …} 로. MANUAL-SPEC 의 표기 그대로."""
    raw = (raw or "").strip()
    m = SELECT_RE.match(raw)
    if m:
        body = m.group(1).strip()
        opts = split_options(body)
        if len(opts) > 1:
            return {"kind": "multi", "values": opts}
        return {"kind": "select", "value": body}
    if raw in ("체크", "해제"):
        return {"kind": "check" if raw == "체크" else "uncheck"}
    m = FILE_RE.match(raw)
    if m:
        return {"kind": "file", "file": m.group(1).strip()}
    if raw in ("", "비움"):
        return {"kind": "empty"}
    if any(raw.startswith(a) for a in AUTO_MARKERS):
        return {"kind": "auto"}
    out = {"kind": "typed", "value": raw}
    if looks_unknown(raw):
        out["unknown"] = True
    return out


def parse_button(raw):
    """`버튼:` 한 줄에서 눌러야 할 것을 뽑는다."""
    def grab(pattern):
        m = re.search(pattern, raw)
        return m.group(1).strip() if m else None

    times = grab(r"(\d+)\s*번\s*$")
    return {"raw": raw,
            "text": grab(r"\[([^\]]+)\]"),          # [편집]
            "row": grab(r"`([^`]+)`\s*(?:행|줄)의"),  # `스탠다드` 행의
            "card": grab(r"`([^`]+)`\s*묶음의"),      # `오퍼명` 묶음의
            "group": grab(r"`([^`]+)`\s*의\s*\["),   # `침대 구성` 의 [침대 행 추가]
            "drawer": "드로어" in raw,
            "times": int(times) if times else 1}


def title_kind(title):
    """제목 끝의 ` (…)` 를 떼어낸 앞부분 — 괄호가 겹쳐도 짝을 맞춘다."""
    t = title.strip()
    if not t.endswith(")"):
        return t
    depth = 0
    for i in range(len(t) - 1, -1, -1):
        if t[i] == ")":
            depth += 1
        elif t[i] == "(":
            depth -= 1
            if depth == 0:
                return t[:i].strip()
    return t


# ---------------------------------------------------------------------------
# 원고(manual.md) 읽기 — 시험용. 실행 입력은 지시서 HTML 이다
# ---------------------------------------------------------------------------

def new_raw(no, title):
    return {"no": no, "title": title, "heads": [], "rows": [],
            "longtexts": [], "files": [], "submit": None, "lines": []}


def split_row(line):
    s = line.strip().strip("|")
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", s)]


def parse_markdown(text):
    lines = text.splitlines()
    title, steps, cur, pending = "", [], None, None
    i, n = 0, len(lines)
    while i < n:
        line, s = lines[i], lines[i].strip()
        i += 1
        if not title and s.startswith("# ") and not s.startswith("## "):
            title = s[2:].strip()
            continue
        m = STEP_RE.match(s)
        if m:
            cur = new_raw(int(m.group(1)), m.group(2))
            cur["lines"].append(line)
            steps.append(cur)
            pending = None
            continue
        if cur is None:
            continue
        cur["lines"].append(line)
        if not s:
            pending = None
            continue
        m = HEAD_RE.match(s)
        if m:
            cur["heads"].append((m.group(1), m.group(2).strip()))
            pending = None
            continue
        m = SUBMIT_RE.match(s)
        if m:
            cur["submit"] = m.group(1).strip()
            continue
        if s.startswith("|"):
            cells = split_row(s)
            if len(cells) >= 2 and cells[0] != "칸" and not set(cells[0]) <= set("-: "):
                cur["rows"].append((cells[0], cells[1]))
            continue
        m = FENCE_RE.match(s)
        if m:
            fence, body = m.group(1), []
            while i < n and not lines[i].strip().startswith(fence):
                body.append(lines[i])
                cur["lines"].append(lines[i])
                i += 1
            if i < n:
                cur["lines"].append(lines[i])
                i += 1
            cur["longtexts"].append((pending or "본문", "\n".join(body).strip("\n")))
            pending = None
            continue
        m = LIST_ITEM_RE.match(s)
        if m:
            pm = PHOTO_ITEM_RE.match(m.group(1).replace("`", "").strip())
            if pm:
                cur["files"].append((pm.group("name"), pm.group("url")))
            continue
        m = LABEL_RE.match(s)
        if m:
            pending = m.group(1).strip()
    for st in steps:
        st["raw"] = "\n".join(st.pop("lines")).strip("\n")
    return title, steps


# ---------------------------------------------------------------------------
# 렌더된 HTML 읽기 (render_card.py 의 마크업을 되짚는다)
# ---------------------------------------------------------------------------

VOID_TAGS = {"br", "img", "input", "hr", "meta", "link", "col", "source", "area"}


class DomBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "#root", "attrs": {}, "kids": []}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "kids": []}
        self.stack[-1]["kids"].append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1]["kids"].append({"tag": tag, "attrs": dict(attrs), "kids": []})

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1]["kids"].append(data)


def classes(node):
    return tuple(node["attrs"].get("class", "").split()) if isinstance(node, dict) else ()


def elements(node):
    return [k for k in node["kids"] if isinstance(k, dict)]


def find_all(node, pred, out=None):
    out = [] if out is None else out
    for k in elements(node):
        if pred(k):
            out.append(k)
        find_all(k, pred, out)
    return out


def find(node, pred):
    return next(iter(find_all(node, pred)), None)


def by_class(name):
    return lambda n: name in classes(n)


def by_tag(name):
    return lambda n: n["tag"] == name


def text_of(node):
    if not isinstance(node, dict):
        return node or ""
    return "".join(text_of(k) for k in node["kids"])


def md_of(node, skip=()):
    """인라인 마크업을 원래 마크다운으로 되돌린다 (복사 버튼은 버린다)."""
    if node is None or node in skip:
        return ""
    if isinstance(node, str):
        return node
    if node["tag"] == "button" or "copy-btn" in classes(node):
        return ""
    inner = "".join(md_of(k, skip) for k in node["kids"])
    if node["tag"] == "code":
        return "`%s`" % inner
    if "btn-look" in classes(node):
        return "[%s]" % inner
    return inner


def html_value_cell(td):
    """`값` 칸 마크업을 원고(manual.md)의 값 표기로 되돌린다."""
    cell = find(td, by_class("cell-text")) or td
    if find(cell, by_class("v-select-mark")):
        strong = find(cell, by_tag("strong"))
        return "선택: " + md_of(strong).strip()
    muted = find(cell, by_class("v-muted"))
    if muted is not None:
        return md_of(muted).strip()
    t = md_of(cell).strip()
    if t.startswith("파일 ▸"):
        return "파일: " + t[len("파일 ▸"):].strip()
    return t


def html_photo_items(ul):
    items = []
    for li in elements(ul):
        code = find(li, by_tag("code"))
        name = text_of(code if code is not None else li).strip()
        if li["tag"] != "li" or not FILENAME_RE.match(name):
            continue
        src = find(li, by_class("photo-src"))  # <a href> 또는 http 가 아닌 글자
        items.append((name, src and (src["attrs"].get("href")
                                     or text_of(src).split(":", 1)[-1].strip() or None)))
    return items


def parse_html_section(sec):
    h2 = find(sec, by_tag("h2"))
    num = text_of(find(h2, by_class("step-num"))).strip() if h2 is not None else ""
    title = md_of(find(h2, by_class("step-title"))).strip() if h2 is not None else ""
    cur = new_raw(int(num) if num.isdigit() else 0, title)
    pending = None
    for node in elements(sec):
        tag, cls = node["tag"], classes(node)
        if tag == "h2" or "photo-notice" in cls:
            continue
        if tag == "p" and "mline" in cls:
            strong = find(node, by_tag("strong"))
            label = text_of(strong).strip().rstrip(":").strip()
            rest = md_of(node, skip=(strong,)).strip()
            if label in HEAD_KEYS:
                cur["heads"].append((label, rest))
                pending = None
            else:
                pending = label
            continue
        if tag == "p":
            t = text_of(node).strip()
            pending = t[:-1].strip() if t.endswith(":") else None
            continue
        if tag == "div" and "table-wrap" in cls:
            for tr in find_all(node, by_tag("tr")):
                tds = find_all(tr, by_tag("td"))
                if len(tds) < 2:
                    continue
                label = md_of(tds[0]).strip()
                if not label:
                    continue
                cur["rows"].append((label, html_value_cell(tds[1])))
            continue
        if tag == "div" and "codeblock-wrap" in cls:
            code = find(node, by_tag("code"))
            cur["longtexts"].append((pending or "본문", text_of(code).strip("\n")))
            pending = None
            continue
        if tag == "div" and "action-box" in cls:
            cur["submit"] = md_of(node).strip()
            continue
        if tag in ("ul", "ol"):
            cur["files"].extend(html_photo_items(node))
            continue
    lines = ["## %d. %s" % (cur["no"], cur["title"])]
    lines += ["%s: %s" % (k, v) for k, v in cur["heads"]]
    lines += ["| %s | %s |" % (a, b) for a, b in cur["rows"]]
    for label, body in cur["longtexts"]:
        lines += ["%s:" % label, "```", body, "```"]
    lines += ["- %s%s" % (f, " — 출처: %s" % s if s else "") for f, s in cur["files"]]
    if cur["submit"]:
        lines.append("→ [%s]" % cur["submit"])
    cur["raw"] = "\n".join(lines)
    cur.pop("lines")
    return cur


def parse_html(text):
    dom = DomBuilder()
    dom.feed(text)
    h1 = find(dom.root, by_tag("h1"))
    title = md_of(h1).strip() if h1 is not None else ""
    sections = find_all(dom.root, lambda n: n["tag"] == "section" and "step" in classes(n))
    return title, [parse_html_section(s) for s in sections]


# ---------------------------------------------------------------------------
# steps.json 만들기
# ---------------------------------------------------------------------------

def build_step(raw):
    head = {"screen": None, "tab": None, "card": None, "block": None,
            "buttons": [], "buttons_parsed": [], "folder": None, "notice": None}
    for key, val in raw["heads"]:
        if key == "버튼":
            head["buttons"].append(val)
            head["buttons_parsed"].append(parse_button(val))
        else:
            head[HEAD_FIELD[key]] = val.replace("`", "").strip() if key in BACKTICK_FREE else val

    fields, seen = [], Counter()
    for label, value_raw in raw["rows"]:
        seen[label] += 1
        name = label if seen[label] == 1 else "%s #%d" % (label, seen[label])
        f = {"label": name, "raw_value": value_raw}
        if name != label:
            f["label_base"] = label
        f.update(classify_value(value_raw))
        m = ROW_LABEL_RE.match(label)
        if m:
            f["row_group"] = m.group(1).strip()
            f["row_index"] = int(m.group(2))
            f["row_field"] = m.group(3).strip()
        fields.append(f)

    photos = [{"file": f, "source": s} for f, s in raw["files"]]
    for f in fields:
        if f["kind"] == "file" and f.get("file"):
            photos.append({"file": f["file"], "source": None, "from_field": f["label"]})

    title = raw["title"]
    return {"no": raw["no"], "title": title, "kind": title_kind(title), "head": head,
            "fields": fields,
            "longtexts": [{"label": l, "text": t} for l, t in raw["longtexts"]],
            "photos": photos, "submit": raw["submit"], "raw": raw.get("raw", "")}


PREFIX_TARGETS = {"호텔 만들기": "호텔명", "기본정보 글 입력": "상품명"}

# ---------------------------------------------------------------------------
# 실행 전 훑기 — 브라우저를 열기 전에 걸리는 것을 잡는다
#
# `stay_boot.js` 의 `staleStep` / `checkGuide` 와 **같은 판정**을 파일 단계에서 한 번 더 한다.
# 그쪽은 페이지 안에서만 돌 수 있어서, 지시서가 옛 화면 기준이라는 사실을 알려면 로그인한 탭과
# 파일 다리와 부트가 다 필요하다. 여기서 걸러 내면 그 전부를 건너뛴다.
# ---------------------------------------------------------------------------

#: 러너가 다루는 단계 갈래. 여기 없는 갈래는 **막지 않고 알리기만** 한다 — 지시서 쪽이 새 화면을
#: 먼저 낼 수 있고, 그때 러너가 못 하는 것은 사람이 판단할 일이지 파서가 정할 일이 아니다.
KNOWN_KINDS = {
    "환율 확인", "거래처 확인", "도시 확인", "호텔 만들기",
    "기본정보 글 입력", "대표이미지 올리기", "상품상세 이미지 올리기", "호텔 정보 입력",
    "취소정책 만들기",
    "룸 만들기", "룸 사진 올리기",
    "오퍼 만들기",
    "연령 구간 만들기",                       # 2026-09-04 신설 (오퍼 탭 `연령 구간` 패널)
    "판매 연결 한 번에 만들기", "판매 연결 표시명 넣기", "판매 연결 표시명 고치기",
    "시즌 만들기", "시즌 가격 채우기", "셀 상태 바꾸기",
    "가격 셀 손으로 고치기", "가격 셀 만들기",
    # 요금제는 지시서 쪽이 `요금제 고치기` 로도 적는다(정본을 고치는 것이 늘 같은 화면이라서다) —
    # 두 표기를 다 받는다. 여기서 표기를 하나로 고르는 것은 사전(`stay-setup-guide`)의 몫이다.
    "요금제 고치기", "요금제 만들기",
    "요금제 정본 고치기", "요금제 정본 만들기", "요금제 배포", "요금제 전체 적용",
    "기준 요금제 바꾸기", "요금제 삭제",
    "판매일 열기",
    "부과금 추가", "부가옵션 만들기", "부가옵션 가격 넣기",
    "프로모션 추가", "혜택 추가", "택1 그룹 만들기", "그룹에 혜택 추가",
    # `택1 그룹 후보 추가` 는 `그룹에 혜택 추가` 와 같은 화면(그룹 카드 [이 그룹에 혜택 추가])의
    # 다른 표기다 — A-seasense 지시서가 이렇게 적었고, 사전 스크린 §23 이 맞는 화면임을
    # 확인했다(2026-09-07). 러너는 드로어 일반 처리로 실행하므로 두 표기를 다 받는다.
    "택1 그룹 후보 추가",
    "판매 시작",
}

#: 러너가 **금지**하는 갈래 — 합격선이 판매 시작 전 🟡 0 이라 사유를 적어 넘기는 길이 없다.
#: `stay_boot.js` 의 `refusedStep` 과 같은 판정이다.
FORBIDDEN_KIND_RE = re.compile(r"^경고 넘어가기")
FORBIDDEN_WARN_WHY = ("`경고 넘어가기` 는 금지된 단계입니다 — 합격선은 판매 시작 전 🟡 0 입니다. "
                      "사유를 적어 넘기지 말고 지시서에서 원인을 고쳐 다시 까세요.")

#: 러너가 실행을 거부하는 갈래·표시 — `stay_boot.js` `staleStep` 과 한 글자도 다르면 안 된다.
STALE_KIND_RE = re.compile(r"^오퍼 고치기")
STALE_HEAD_MARKS = ("기본 오퍼", "스탠다드")

#: 연령별 단가 칸 — 부과금 드로어의 카드이고, **[부과 단위]가 `인당`** 이고 **[부과 방식]이 `정액`**
#: 이며 시간대별 요율 행이 하나도 없을 때만 화면에 선다(세 조건이 다 맞아야 그 카드가 선다).
#: 그래서 지시서의 줄 차례가 곧 결과다.
AGE_RATE_LABEL_RE = re.compile(r"^연령별\s*단가(\s*[·・]\s*.+)?$")
#: 카드를 세우는 두 셀렉트. 연령별 단가 줄은 **둘 다보다 뒤**여야 한다.
CHARGE_GATE_LABELS = ("부과 단위", "부과단위", "부과 방식", "부과방식")
#: 인당을 고르는 칸 — 이 줄이 아예 없으면 카드가 설 일이 없다.
CHARGE_UNIT_LABELS = ("부과 단위", "부과단위")
#: 화면 차례는 … → 적용 날짜 → 적용 룸 scope → 연령별 단가 → 시간대별 요율 → 설명 이다.
#: 지시서도 그 차례를 따라야 사람이 화면과 나란히 읽는다(dict-audit 2026-09-04 합의).
CHARGE_ROOM_SCOPE_LABELS = ("적용 룸 scope", "적용 룸", "적용룸 scope")
TIER_ROW_LABEL_RE = re.compile(r"^(시간대별\s*요율|요율)\s+\d+\s*[·・]")


def stale_reason(step):
    """러너가 실행을 거부하는 단계인가 — 이유 한 줄, 아니면 None.

    옛 화면(ERP 2026-09-04 이전) 기준 단계와 금지된 단계(`경고 넘어가기`)를 함께 본다.
    """
    kind, title = step.get("kind") or "", step.get("title") or ""
    head = json.dumps(step.get("head") or {}, ensure_ascii=False)
    if FORBIDDEN_KIND_RE.match(kind) or FORBIDDEN_KIND_RE.match(title):
        return FORBIDDEN_WARN_WHY
    if STALE_KIND_RE.match(kind) or STALE_KIND_RE.match(title):
        return "`오퍼 고치기` 단계 — 고쳐 쓸 `기본 오퍼` 가 없습니다"
    if "룸 만들기" in kind and "스탠다드" in head:
        return "`룸 만들기` 단계가 `스탠다드` 행의 [편집] 을 가리킵니다"
    if "기본 오퍼" in head:
        return "`기본 오퍼` 를 가리키는 단계입니다"
    return None


def charge_order_problem(step):
    """부과금 단계의 [연령별 단가] 줄이 화면에 설 수 없는 차례인가 — 이유 한 줄, 아니면 None."""
    labels = [f.get("label_base") or f["label"] for f in step["fields"]]
    age_at = [i for i, l in enumerate(labels) if AGE_RATE_LABEL_RE.match(l)]
    if not age_at:
        return None
    if not any(l in CHARGE_UNIT_LABELS for l in labels):
        return "[연령별 단가] 줄이 있는데 [부과 단위] 줄이 없습니다 — 그 칸은 부과 단위가 `인당` 일 때만 화면에 섭니다"
    gate_at = [i for i, l in enumerate(labels) if l in CHARGE_GATE_LABELS]
    if min(age_at) < max(gate_at):
        return "[연령별 단가] 줄이 [부과 단위]·[부과 방식] 줄보다 앞에 있습니다 — 둘을 먼저 골라야 그 칸이 섭니다"
    scope_at = [i for i, l in enumerate(labels) if l in CHARGE_ROOM_SCOPE_LABELS]
    if scope_at and min(age_at) < max(scope_at):
        return "[연령별 단가] 줄이 [적용 룸 scope] 줄보다 앞에 있습니다 — 화면 차례는 적용 룸 scope 다음입니다"
    tier_at = [i for i, l in enumerate(labels) if TIER_ROW_LABEL_RE.match(l)]
    if tier_at and min(tier_at) < max(age_at):
        return "[시간대별 요율] 줄이 [연령별 단가] 줄보다 앞에 있습니다 — 요율 행이 하나라도 생기면 연령별 단가 카드가 사라집니다"
    return None


#: 연령 구간 단계에서 나이를 읽는 칸.
AGE_MIN_LABELS = ("최소 연령", "최소연령")
AGE_MAX_LABELS = ("최대 연령", "최대연령")


def _age_of(step, labels):
    for f in step["fields"]:
        if (f.get("label_base") or f["label"]) in labels and f.get("kind") == "typed":
            try:
                return Decimal(str(f.get("value") or "").strip())
            except (InvalidOperation, ValueError):
                return None
    return None


def _ranges_overlap(min_a, max_a, min_b, max_b) -> bool:
    """서버와 **같은 판정**이다 — 경계는 양끝 포함이다(`stay.services.age_band.ranges_overlap`).

    `0~5.99` 와 `6~11.99` 는 안 겹치고, `0~6` 과 `6~11.99` 는 만 6세에서 겹쳐 거부된다.
    """
    return min_a <= max_b and min_b <= max_a


def age_band_overlaps(steps):
    """같은 오퍼 안에서 나이 범위가 겹치는 연령 구간 단계 — 서버가 저장을 거부한다.

    러너가 이것을 따로 보는 이유는 `staleStep` 을 파일 단계에서 한 번 더 보는 이유와 같다.
    겹치는 구간은 **그 단계에서 저장이 막힐 뿐**이라, 그때는 이미 앞 단계들이 화면에 만들어져
    있다. 브라우저를 열기 전에 걸러 내면 그 되돌리기가 통째로 없어진다.
    카드(오퍼)별로 나눠 견준다 — 다른 오퍼의 구간끼리는 겹쳐도 된다.
    """
    seen, out = {}, []
    for s in steps:
        if s.get("kind") != "연령 구간 만들기":
            continue
        lo, hi = _age_of(s, AGE_MIN_LABELS), _age_of(s, AGE_MAX_LABELS)
        if lo is None or hi is None:
            continue
        card = (s["head"].get("card") or "").strip()
        for prev_no, prev_lo, prev_hi in seen.get(card, []):
            if _ranges_overlap(lo, hi, prev_lo, prev_hi):
                out.append({
                    "no": s["no"], "title": s["title"],
                    "why": "%d단계와 나이 범위가 겹칩니다 — 만 %s~%s세 와 만 %s~%s세 "
                           "(양끝이 포함이라 경계가 맞닿기만 해도 겹칩니다)"
                           % (prev_no, lo, hi, prev_lo, prev_hi),
                })
                break
        seen.setdefault(card, []).append((s["no"], lo, hi))
    return out


def preflight(steps):
    """실행 전 훑기 결과 — {stale, unknown_kinds, charge_order, age_overlap}.

    `stale` 은 러너가 **거부하는** 단계다(옛 화면 기준 · 금지된 갈래).
    """
    stale = [{"no": s["no"], "title": s["title"], "why": w}
             for s in steps for w in [stale_reason(s)] if w]
    refused_nos = {x["no"] for x in stale}
    # 거부하는 갈래는 위에서 이미 한 줄로 알린다 — `모르는 갈래` 로 두 번 세지 않는다
    unknown = [{"no": s["no"], "kind": s["kind"]}
               for s in steps
               if s["kind"] and s["kind"] not in KNOWN_KINDS and s["no"] not in refused_nos]
    order = [{"no": s["no"], "title": s["title"], "why": w}
             for s in steps for w in [charge_order_problem(s)] if w]
    return {"stale": stale, "unknown_kinds": unknown, "charge_order": order,
            "age_overlap": age_band_overlaps(steps)}


def apply_title_prefix(steps, prefix):
    joined = prefix  # 접두를 그대로 붙인다 (예: __skills__호텔명)
    for st in steps:
        want = PREFIX_TARGETS.get(st["kind"])
        if not want:
            continue
        for f in st["fields"]:
            if f["label"] == want and f["kind"] == "typed":
                f["value"] = joined + f["value"]
                f["prefixed"] = True


# ---------------------------------------------------------------------------
# 실행 입력 문지기 — 검사를 통과한 HTML 지시서만 받는다
# ---------------------------------------------------------------------------

#: `render_card.py` 가 `<head>` 에 박는 도장. 값은
#: `v1;sha256=<원고 manual.md 바이트의 sha256>;check=<ok|fail>;rendered=<YYYY-MM-DD>` 다.
STAMP_META_NAME = "stay-guide-stamp"
STAMP_RE = re.compile(
    r"""<meta[^>]*\bname\s*=\s*["']%s["'][^>]*>""" % STAMP_META_NAME, re.IGNORECASE)
STAMP_CONTENT_RE = re.compile(r"""\bcontent\s*=\s*["']([^"']*)["']""", re.IGNORECASE)

#: 거부 문구 — 사람이 다음에 무엇을 할지가 문장 안에 들어 있어야 한다.
MSG_MD_INPUT = ("manual.md 는 원고다 — 실행 입력이 아니다. render_card.py 로 지시서 HTML 을 만들고 "
                "검사를 통과시킨 뒤 그 지시서를 준다")
MSG_NO_STAMP = "지시서에 검사 도장이 없다 — render_card.py 로 다시 만든다"
MSG_CHECK_FAIL = "검사기를 통과하지 못한 지시서다 — check_manual.py 의 오류를 고치고 다시 렌더한다"
MSG_STALE_MD = "원고(manual.md)가 지시서보다 새롭다 — 다시 렌더한다"

#: 원고 폴더 이름 — 공유 폴더 안에서 원고와 그 부속(rules.md·facts.json·contract.md)이 사는 곳.
DRAFT_DIR = "_원고"


class GuideRefused(Exception):
    """실행 입력으로 받을 수 없는 지시서. main 이 2 로 끝낸다."""


def parse_stamp(text):
    """HTML 글에서 도장을 읽어 {raw, version, sha256, check, rendered} 로. 없으면 None."""
    m = STAMP_RE.search(text)
    if not m:
        return None
    mc = STAMP_CONTENT_RE.search(m.group(0))
    if not mc:
        return None
    raw = mc.group(1).strip()
    stamp = {"raw": raw, "version": None, "sha256": None, "check": None, "rendered": None}
    for i, part in enumerate(piece.strip() for piece in raw.split(";")):
        if not part:
            continue
        if i == 0 and "=" not in part:
            stamp["version"] = part
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        if key in stamp:
            stamp[key] = value.strip()
    return stamp


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_input(path):
    """입력 경로 → (읽을 지시서 HTML 파일, "html").

    **지시서 HTML 만 받는다.** 원고(manual.md)를 주면 거부한다 — 검사를 건너뛴 채로 실행되는 길을
    막는다. 공유 폴더를 주면 그 **맨 위**의 `*_입력지시서.html` 이 하나일 때만 그것을 쓴다
    (`_원고/` 안은 보지 않는다).
    """
    p = Path(path)
    if p.is_dir():
        htmls = sorted(p.glob("*_입력지시서.html"))
        if not htmls:
            raise GuideRefused("폴더에 `*_입력지시서.html` 이 없다: %s — %s" % (p, MSG_MD_INPUT))
        if len(htmls) > 1:
            raise GuideRefused(
                "폴더에 `*_입력지시서.html` 이 %d개다: %s — 실행할 하나를 파일로 지정한다"
                % (len(htmls), ", ".join(h.name for h in htmls)))
        return htmls[0], "html"
    if not p.exists():
        raise GuideRefused("파일이 없습니다: %s" % p)
    if p.suffix.lower() == ".md":
        raise GuideRefused(MSG_MD_INPUT)
    if p.suffix.lower() not in (".html", ".htm"):
        raise GuideRefused("HTML 지시서가 아니다: %s — %s" % (p, MSG_MD_INPUT))
    return p, "html"


def verify_stamp(html_path, text):
    """도장을 확인한다. 통과하면 도장 dict, 아니면 GuideRefused.

    셋을 본다: 도장이 있는가 · `check=ok` 인가 · 같은 공유 폴더의 원고가 그 뒤로 바뀌지 않았는가.
    원고는 `_원고/manual.md` 를 먼저 보고, 없으면 옛 자리인 `manual.md` 를 본다.
    """
    stamp = parse_stamp(text)
    if not stamp or not stamp.get("sha256"):
        raise GuideRefused(MSG_NO_STAMP)
    if stamp.get("check") != "ok":
        raise GuideRefused(MSG_CHECK_FAIL)
    md = find_manual(Path(html_path).parent)
    if md and file_sha256(md) != stamp["sha256"]:
        raise GuideRefused(MSG_STALE_MD)
    return stamp


def find_manual(share_dir):
    """공유 폴더에서 원고를 찾는다 — `_원고/manual.md` 먼저, 없으면 옛 자리 `manual.md`. 없으면 None."""
    for cand in (Path(share_dir) / DRAFT_DIR / "manual.md", Path(share_dir) / "manual.md"):
        if cand.exists():
            return cand
    return None


def stamp_line(stamp):
    return "검사 도장: %s · sha256 %s… · 렌더 %s" % (
        stamp.get("check") or "?", (stamp.get("sha256") or "")[:12], stamp.get("rendered") or "?")


def summarize(doc):
    steps = doc["steps"]
    kinds = Counter(s["kind"] for s in steps)
    unknown = [(s["no"], f["label"], f["raw_value"])
               for s in steps for f in s["fields"] if f.get("unknown")]
    missing = doc["guide"].get("photo_missing", [])
    pre = doc["guide"].get("preflight") or {"stale": [], "unknown_kinds": [], "charge_order": [], "age_overlap": []}
    pre.setdefault("age_overlap", [])
    lines = ["단계 %d개 · 값 %d행 · 사진 %d장"
             % (len(steps), sum(len(s["fields"]) for s in steps),
                sum(len(s["photos"]) for s in steps)),
             "종류별 단계 수:"]
    lines += ["  %-24s %d" % (k, v) for k, v in kinds.most_common()]
    lines.append("알 수 없는 값 칸: %d" % len(unknown))
    lines += ["  %d단계 · %s · %s" % u for u in unknown[:20]]
    lines.append("없는 사진 파일: %d" % len(missing))
    lines += ["  %s" % m for m in missing[:20]]
    lines.append("러너가 거부하는 단계: %d" % len(pre["stale"]))
    lines += ["  %d단계 · %s · %s" % (x["no"], x["title"], x["why"]) for x in pre["stale"][:20]]
    lines.append("줄 차례가 어긋난 단계: %d" % len(pre["charge_order"]))
    lines += ["  %d단계 · %s · %s" % (x["no"], x["title"], x["why"]) for x in pre["charge_order"][:20]]
    lines.append("나이 범위가 겹치는 단계: %d" % len(pre["age_overlap"]))
    lines += ["  %d단계 · %s · %s" % (x["no"], x["title"], x["why"]) for x in pre["age_overlap"][:20]]
    if pre["unknown_kinds"]:
        # 막지 않는다 — 알리기만 한다(`KNOWN_KINDS` 주석)
        lines.append("러너가 모르는 단계 갈래: %d" % len(pre["unknown_kinds"]))
        lines += ["  %d단계 · %s" % (x["no"], x["kind"]) for x in pre["unknown_kinds"][:20]]
    blocking = (len(unknown) + len(missing) + len(pre["stale"])
                + len(pre["charge_order"]) + len(pre["age_overlap"]))
    return "\n".join(lines), len(unknown), len(missing), blocking


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="검사를 통과한 지시서(<이름>_입력지시서.html)를 실행 계획(steps.json)으로 바꾼다 "
                    "(원고 manual.md 는 받지 않는다 — render_card.py 로 렌더한 지시서를 준다)")
    ap.add_argument("input", help="<이름>_입력지시서.html · 그 지시서 하나가 든 공유 폴더")
    ap.add_argument("--photos", default=None, help="사진 폴더 (기본: 공유 폴더의 `사진`)")
    ap.add_argument("--title-prefix", default=None, help="호텔명·상품명 앞에 붙일 접두")
    ap.add_argument("-o", "--output", default=None,
                    help="실행 계획 경로 (기본: 공유 폴더의 steps.json — 보통 `<이름>_실행/steps.json` 을 준다)")
    ap.add_argument("--check", action="store_true",
                    help="도장과 요약만 내고, 알 수 없는 값이나 없는 사진이 있으면 1 로 끝낸다")
    args = ap.parse_args(argv)

    try:
        src, source = resolve_input(args.input)
        text = src.read_text(encoding="utf-8")
        stamp = verify_stamp(src, text)
    except GuideRefused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    title, raws = parse_html(text)
    steps = [build_step(r) for r in raws]
    if args.title_prefix:
        apply_title_prefix(steps, args.title_prefix)

    guide_dir = src.parent
    photos_dir = Path(args.photos).expanduser().resolve() if args.photos \
        else (guide_dir / "사진").resolve()
    missing = []
    for ph in (p for st in steps for p in st["photos"]):
        if not (photos_dir / ph["file"]).exists():
            ph["missing"] = True
            if ph["file"] not in missing:
                missing.append(ph["file"])

    doc = {"guide": {"title": title, "source": source, "guide_file": str(src),
                     "share_folder": guide_dir.name,
                     "photos_dir": str(photos_dir), "title_prefix": args.title_prefix,
                     "stamp": stamp, "photo_missing": missing, "preflight": preflight(steps)},
           "steps": steps}

    text_summary, _n_unknown, _n_missing, blocking = summarize(doc)
    if args.check:
        print(stamp_line(stamp))
        print(text_summary)
        return 1 if blocking else 0

    out = Path(args.output) if args.output else guide_dir / "steps.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(text_summary, file=sys.stderr)
    print("실행 계획(steps.json): %s" % out, file=sys.stderr)
    if doc["guide"]["preflight"]["stale"]:
        # 러너도 이 단계를 거부한다(`stay_boot.js` `staleStep`) — 여기서 먼저 말해 준다
        print("⚠ 옛 화면 기준 단계가 있습니다 — 실행하지 말고 지시서를 다시 만드세요.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
