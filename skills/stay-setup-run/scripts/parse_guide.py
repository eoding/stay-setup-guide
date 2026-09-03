#!/usr/bin/env python3
"""parse_guide.py — 입력 지시서(manual.md 또는 렌더된 HTML) → steps.json.

한 단계(`## N. 제목`) = 저장 버튼 한 번. 단계 안에는:

    화면:/탭:/카드:/블록:/버튼:/폴더:/주의:   머리 줄 (버튼은 여러 줄)
    | 칸 | 값 |                              2열 고정 표
    <라벨>:  +  펜스 블록                     긴 글 (상세설명·설명·날짜 나열 …)
    파일 선택 → 아래 파일  +  `- a.jpg`       사진 목록
    → [저장]                                  저장 버튼

manual.md 와 render_card.py 가 만든 HTML 은 같은 steps 를 낸다.

사용법:
    python3 parse_guide.py <guide.html | manual.md | 폴더>
        [--photos DIR] [--title-prefix STR] [-o steps.json] [--check]
"""

import argparse
import json
import re
import sys
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
ROW_LABEL_RE = re.compile(r"^(.+?)\s+(\d+)\s*·\s*(.+)$")
AUTO_MARKERS = ("자동 입력됨", "자동입력됨")


# ---------------------------------------------------------------------------
# 값·라벨·버튼 해석 (manual.md 와 HTML 이 함께 쓴다)
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
# manual.md 읽기
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
    """`값` 칸 마크업을 manual.md 의 값 표기로 되돌린다."""
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


def resolve_input(path):
    """입력 경로 → (읽을 파일, 'manual.md'|'html'). 같은 폴더의 manual.md 를 먼저 쓴다."""
    p = Path(path)
    if p.is_dir():
        md = p / "manual.md"
        if md.exists():
            return md, "manual.md"
        htmls = sorted(p.glob("*_입력지시서.html")) or sorted(p.glob("*.html"))
        if htmls:
            return htmls[0], "html"
        raise SystemExit("입력 지시서를 찾지 못했습니다: %s" % p)
    if not p.exists():
        raise SystemExit("파일이 없습니다: %s" % p)
    if p.suffix.lower() in (".html", ".htm"):
        md = p.parent / "manual.md"
        if md.exists():
            print("manual.md 가 옆에 있어 그것을 읽습니다: %s" % md, file=sys.stderr)
            return md, "manual.md"
        return p, "html"
    return p, "manual.md"


def summarize(doc):
    steps = doc["steps"]
    kinds = Counter(s["kind"] for s in steps)
    unknown = [(s["no"], f["label"], f["raw_value"])
               for s in steps for f in s["fields"] if f.get("unknown")]
    missing = doc["guide"].get("photo_missing", [])
    lines = ["단계 %d개 · 값 %d행 · 사진 %d장"
             % (len(steps), sum(len(s["fields"]) for s in steps),
                sum(len(s["photos"]) for s in steps)),
             "종류별 단계 수:"]
    lines += ["  %-24s %d" % (k, v) for k, v in kinds.most_common()]
    lines.append("알 수 없는 값 칸: %d" % len(unknown))
    lines += ["  %d단계 · %s · %s" % u for u in unknown[:20]]
    lines.append("없는 사진 파일: %d" % len(missing))
    lines += ["  %s" % m for m in missing[:20]]
    return "\n".join(lines), len(unknown), len(missing)


def main(argv=None):
    ap = argparse.ArgumentParser(description="입력 지시서를 steps.json 으로 바꾼다")
    ap.add_argument("input", help="manual.md · <이름>_입력지시서.html · 공유 폴더")
    ap.add_argument("--photos", default=None, help="사진 폴더 (기본: 지시서 폴더의 `사진`)")
    ap.add_argument("--title-prefix", default=None, help="호텔명·상품명 앞에 붙일 접두")
    ap.add_argument("-o", "--output", default=None, help="steps.json 경로")
    ap.add_argument("--check", action="store_true",
                    help="요약만 내고, 알 수 없는 값이나 없는 사진이 있으면 1 로 끝낸다")
    args = ap.parse_args(argv)

    src, source = resolve_input(args.input)
    text = src.read_text(encoding="utf-8")
    title, raws = (parse_markdown(text) if source == "manual.md" else parse_html(text))
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

    doc = {"guide": {"title": title, "source": source, "share_folder": guide_dir.name,
                     "photos_dir": str(photos_dir), "title_prefix": args.title_prefix,
                     "photo_missing": missing},
           "steps": steps}

    text_summary, n_unknown, n_missing = summarize(doc)
    if args.check:
        print(text_summary)
        return 1 if (n_unknown or n_missing) else 0

    out = Path(args.output) if args.output else guide_dir / "steps.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(text_summary, file=sys.stderr)
    print("steps.json: %s" % out, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
