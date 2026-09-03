#!/usr/bin/env python3
"""render_card.py — 호텔 세팅 카드 마크다운을 복사-친화적 단일 HTML로 변환.

md 는 표 안의 값을 복사하기 어렵다. 이 스크립트는 카드 md 파일을 읽어
표 셀·코드 스팬마다 [복사] 텍스트 버튼을 붙이고, 체크박스 진행 상태를 localStorage 에
저장하고, 문서 맨 위에 목차(## / ### 제목, 앵커 링크)를 붙이고, 사진 단계마다 저작권 고지를
붙이고, 사진 폴더가 있으면
"사진" 절 끝에 표 형태 갤러리(썸네일|파일명|내용|출처)를 붙인 단일 HTML 파일을 낸다.
화면은 LaTeX 로 뽑은 행정 문서처럼 희고 검은 단색 룩 하나로 고정한다(다크 테마 없음).

표준 라이브러리만으로 동작한다. Pillow(PIL) 가 있으면 사진 썸네일을 축소해
용량을 줄인다(없으면 300KB 이하 원본만 임베드, 넘으면 파일명만 표시).

사용법:
    python3 render_card.py <card.md> -o <out.html> [--photos <dir>] [--title "..."]
"""

import argparse
import base64
import hashlib
import html
import io
import mimetypes
import re
import sys
from collections import Counter
from pathlib import Path

try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except Exception:
    HAS_PIL = False


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)


def strip_html_comments(text):
    return _COMMENT_RE.sub('', text)


def to_plain_text(text):
    """인라인 마크다운 표시를 제거하고 순수 텍스트만 남긴다 (복사용 값·id·내비 라벨용)."""
    t = re.sub(r'`([^`]+)`', r'\1', text)
    t = re.sub(r'\*\*(.+?)\*\*', r'\1', t)
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)
    return t.strip()


_SLUG_STRIP_RE = re.compile(r'[^a-z0-9가-힣]+')


def slugify(text, existing):
    t = text.lower()
    t = _SLUG_STRIP_RE.sub('-', t).strip('-')
    if not t:
        t = 'sec'
    base = t
    n = 2
    while t in existing:
        t = f'{base}-{n}'
        n += 1
    existing.add(t)
    return t


_CIRCLED_NUM_RE = re.compile(r'[①-⑳]')  # U+2460~U+2473 (1~20)


def _circled_to_plain(m):
    n = ord(m.group()) - 0x2460 + 1
    return f'{n}.'


def normalize_circled_numbers(text):
    """폰트에서 깨져 보이는 원문자(①~⑳)를 '1.' 같은 일반 숫자로 치환한다.
    제목·본문·목차가 전부 같은 텍스트에서 파생되므로 파싱 전에 한 번만 치환하면 된다."""
    return _CIRCLED_NUM_RE.sub(_circled_to_plain, text)


_CURRENT_FILE = ''


def item_key(text):
    payload = (_CURRENT_FILE + '::' + to_plain_text(text)).encode('utf-8')
    return hashlib.sha1(payload).hexdigest()[:16]


def step_key(text):
    """## 단계 제목 -> "완료" 체크박스/목차 체크 동기화용 안정 키."""
    payload = (_CURRENT_FILE + '::step::' + to_plain_text(text)).encode('utf-8')
    return hashlib.sha1(payload).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 블록 파서 (마크다운 -> 블록 토큰 리스트)
# ---------------------------------------------------------------------------

HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
HR_RE = re.compile(r'^(-{3,}|\*{3,}|_{3,})\s*$')
FENCE_RE = re.compile(r'^(```|~~~)')
LIST_RE = re.compile(r'^(\s*)([-*]|\d+\.)\s+(.*)$')
TABLE_SEP_RE = re.compile(r'^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$')
CHECKBOX_ITEM_RE = re.compile(r'^\[( |x|X)\]\s+(.*)$')
_PIPE_SPLIT_RE = re.compile(r'(?<!\\)\|')

# manual.md 형식: "화면: 상세 페이지" 같은 굵은 라벨 줄, "→ [저장]" 같은 독립 액션 줄
LABEL_LINE_RE = re.compile(r'^(화면|탭|버튼|카드|블록|주의|설명|한줄설명|상세설명|폴더):\s*(.*)$')
ACTION_LINE_RE = re.compile(r'^→\s*\[(.+?)\]\s*$')
HEADING_NUM_RE = re.compile(r'^(\d+)\.\s*(.*)$')  # "## 1. 제목" -> 단계 번호/제목 분리


def split_table_row(line):
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|'):
        s = s[:-1]
    cells = _PIPE_SPLIT_RE.split(s)
    return [c.strip().replace('\\|', '|') for c in cells]


def parse_align(sep_line):
    aligns = []
    for c in split_table_row(sep_line):
        c = c.strip()
        left = c.startswith(':')
        right = c.endswith(':')
        if left and right:
            aligns.append('center')
        elif right:
            aligns.append('right')
        else:
            aligns.append(None)
    return aligns


def is_block_start(lines, i):
    """lines[i] 가 새 블록(문단/리스트 항목 이어쓰기를 끊는 것)의 시작인가."""
    if i >= len(lines):
        return True
    line = lines[i]
    stripped = line.strip()
    if stripped == '':
        return True
    if HEADING_RE.match(line):
        return True
    if HR_RE.match(stripped):
        return True
    if FENCE_RE.match(stripped):
        return True
    if LABEL_LINE_RE.match(line):
        return True
    if ACTION_LINE_RE.match(stripped):
        return True
    if line.lstrip().startswith('>'):
        return True
    if LIST_RE.match(line):
        return True
    if '|' in line and i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i + 1]):
        return True
    return False


def parse_blocks(lines):
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.strip() == '':
            i += 1
            continue

        m = re.match(r'^(```|~~~)(\w*)\s*$', line.strip())
        if m:
            fence, lang = m.group(1), m.group(2)
            i += 1
            code_lines = []
            while i < n and not lines[i].strip().startswith(fence):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 닫는 펜스 건너뛰기
            blocks.append(('code', lang, '\n'.join(code_lines)))
            continue

        m = HEADING_RE.match(line)
        if m:
            blocks.append(('heading', len(m.group(1)), m.group(2).strip()))
            i += 1
            continue

        if HR_RE.match(line.strip()):
            blocks.append(('hr',))
            i += 1
            continue

        m = LABEL_LINE_RE.match(line)
        if m:
            blocks.append(('label', m.group(1), m.group(2).strip()))
            i += 1
            continue

        m = ACTION_LINE_RE.match(line.strip())
        if m:
            blocks.append(('action', m.group(1).strip()))
            i += 1
            continue

        if '|' in line and i + 1 < n and TABLE_SEP_RE.match(lines[i + 1]):
            header_cells = split_table_row(line)
            align = parse_align(lines[i + 1])
            i += 2
            rows = []
            while i < n and lines[i].strip() != '' and '|' in lines[i] and not HEADING_RE.match(lines[i]):
                rows.append(split_table_row(lines[i]))
                i += 1
            blocks.append(('table', header_cells, align, rows))
            continue

        if line.lstrip().startswith('>'):
            bq_lines = []
            while i < n and lines[i].lstrip().startswith('>'):
                content = lines[i].lstrip()[1:]
                if content.startswith(' '):
                    content = content[1:]
                bq_lines.append(content)
                i += 1
            blocks.append(('blockquote', bq_lines))
            continue

        if LIST_RE.match(line):
            first_marker = LIST_RE.match(line).group(2)
            ordered = first_marker[0].isdigit()
            items = []
            while i < n:
                mi = LIST_RE.match(lines[i])
                if not mi:
                    break
                text = mi.group(3)
                i += 1
                cont = []
                while i < n and not is_block_start(lines, i):
                    cont.append(lines[i].strip())
                    i += 1
                full_text = text if not cont else text + ' ' + ' '.join(cont)
                items.append(full_text)
                if i < n and lines[i].strip() == '':
                    break
            blocks.append(('list', ordered, items))
            continue

        # 문단
        para_lines = [line.strip()]
        i += 1
        while i < n and not is_block_start(lines, i):
            para_lines.append(lines[i].strip())
            i += 1
        blocks.append(('para', ' '.join(para_lines)))

    return blocks


# ---------------------------------------------------------------------------
# 인라인 렌더링 (굵게·코드 스팬·링크) — 코드 스팬엔 복사 버튼을 붙인다
# ---------------------------------------------------------------------------

SPECIAL_RE = re.compile(r'`|\*\*|\[')
LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
BARE_BRACKET_RE = re.compile(r'\[([^\]]+)\]')


def render_code_span(code, stats, code_buttons):
    esc = html.escape(code)
    if not code_buttons:
        return f'<code>{esc}</code>'
    attr = html.escape(code, quote=True)
    stats['copy_code'] += 1
    return (
        f'<span class="code-copy"><code>{esc}</code>'
        f'<button type="button" class="copy-btn copy-code" data-copy="{attr}">[복사]</button></span>'
    )


def render_inline(text, stats, code_buttons=True, bracket_buttons=False):
    result = []
    pos = 0
    n = len(text)
    while pos < n:
        m = SPECIAL_RE.search(text, pos)
        if not m:
            result.append(html.escape(text[pos:]))
            break
        start = m.start()
        if start > pos:
            result.append(html.escape(text[pos:start]))
        tok = m.group()
        if tok == '`':
            end = text.find('`', start + 1)
            if end == -1:
                result.append(html.escape(text[start:start + 1]))
                pos = start + 1
                continue
            code = text[start + 1:end]
            result.append(render_code_span(code, stats, code_buttons))
            pos = end + 1
        elif tok == '**':
            end = text.find('**', start + 2)
            if end == -1:
                result.append(html.escape(text[start:start + 2]))
                pos = start + 2
                continue
            inner = text[start + 2:end]
            result.append('<strong>' + render_inline(inner, stats, code_buttons, bracket_buttons) + '</strong>')
            pos = end + 2
        elif tok == '[':
            m2 = LINK_RE.match(text, start)
            if m2:
                label, url = m2.group(1), m2.group(2)
                safe_url = html.escape(url, quote=True)
                inner = render_inline(label, stats, code_buttons, bracket_buttons)
                result.append(
                    f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">{inner}</a>'
                )
                pos = m2.end()
            elif bracket_buttons:
                m3 = BARE_BRACKET_RE.match(text, start)
                if m3:
                    inner_html = render_inline(m3.group(1), stats, code_buttons, bracket_buttons=False)
                    result.append(f'<span class="btn-look">{inner_html}</span>')
                    pos = m3.end()
                else:
                    result.append(html.escape('['))
                    pos = start + 1
            else:
                result.append(html.escape('['))
                pos = start + 1
    return ''.join(result)


# ---------------------------------------------------------------------------
# 블록 -> HTML
# ---------------------------------------------------------------------------

VALUE_COL_NAMES = {'값', '넣을 값'}

# 2열(칸|값) 표의 "값" 셀 종류 판별
SELECT_VALUE_RE = re.compile(r'^선택\s*:\s*(.*)$')
FILE_VALUE_RE = re.compile(r'^파일\s*:\s*(.*)$')
CHECK_WORDS = {'체크', '해제'}
MUTED_PREFIXES = ('비움', '자동 입력됨', '(없음)')


def render_value_cell(cell_raw, stats, kind_counts):
    """2열 표의 "값" 셀을 종류별로 렌더한다. (html, copy_text_or_None) 을 돌려준다.
    copy_text 가 None 이면 이 셀은 복사 버튼도 셀 클릭 복사도 없다."""
    raw = cell_raw.strip()
    plain = to_plain_text(raw)

    m = SELECT_VALUE_RE.match(raw)
    if m:
        kind_counts['select'] += 1
        rest_html = render_inline(m.group(1).strip(), stats, code_buttons=False)
        return f'<span class="v-select-mark">선택 ▸</span> <strong>{rest_html}</strong>', None

    if plain in CHECK_WORDS:
        kind_counts['check'] += 1
        return f'<strong>{html.escape(plain)}</strong>', None

    m = FILE_VALUE_RE.match(raw)
    if m:
        kind_counts['file'] += 1
        fname_raw = m.group(1).strip()
        fname_plain = to_plain_text(fname_raw).strip()
        fname_html = render_inline(fname_raw, stats, code_buttons=False)
        return f'파일 ▸ {fname_html}', fname_plain

    if any(plain.startswith(p) for p in MUTED_PREFIXES) or (plain.startswith('(') and plain.endswith(')')):
        kind_counts['muted'] += 1
        inner = render_inline(raw, stats, code_buttons=False)
        return f'<span class="v-muted">{inner}</span>', None

    kind_counts['typed'] += 1
    inner = render_inline(raw, stats, code_buttons=False)
    return inner, plain


def align_style(align, i):
    if not align or i >= len(align) or not align[i]:
        return ''
    a = align[i]
    if a == 'center':
        return ' style="text-align:center"'
    if a == 'right':
        return ' style="text-align:right"'
    return ''


def render_table(b, stats):
    _, header_cells, align, rows = b
    stats['tables'] += 1
    ncols = len(header_cells)
    value_cols = set()
    for i, h in enumerate(header_cells):
        if to_plain_text(h).strip() in VALUE_COL_NAMES:
            value_cols.add(i)

    # "칸 | 값" 같은 2열 표는 폭을 35%/65% 로 고정한다
    colgroup = '<colgroup><col style="width:35%"><col style="width:65%"></colgroup>' if ncols == 2 else ''

    th_html = []
    for i, h in enumerate(header_cells):
        style = align_style(align, i)
        th_html.append(f'<th{style}>{render_inline(h, stats, code_buttons=False)}</th>')

    rows_html = []
    for row in rows:
        if len(row) < ncols:
            cells = row + [''] * (ncols - len(row))
        else:
            cells = row[:ncols]
        tds = []
        for i, cell in enumerate(cells):
            style = align_style(align, i)
            plain = to_plain_text(cell)
            is_value_col = i in value_cols
            if plain == '':
                tds.append(f'<td{style}></td>')
                continue

            if ncols == 2 and is_value_col:
                # "값" 열은 종류별로 다르게 그린다 — 타이핑 값만 복사 버튼이 붙는다.
                val_html, copy_text = render_value_cell(cell, stats, stats['value_kinds'])
                if copy_text:
                    attr = html.escape(copy_text, quote=True)
                    stats['copy_cell'] += 1
                    btn = f'<button type="button" class="copy-btn copy-cell" data-copy="{attr}">[복사]</button>'
                    tds.append(
                        f'<td class="value-cell"{style} role="button" tabindex="0">'
                        f'<span class="cell-text">{val_html}</span> {btn}</td>'
                    )
                else:
                    tds.append(f'<td{style}><span class="cell-text">{val_html}</span></td>')
                continue

            inner = render_inline(cell, stats, code_buttons=False)
            # 2열이 아닌 구형 표는 기존대로 매 셀에 복사 버튼을 단다.
            show_button = is_value_col or ncols != 2
            if not show_button:
                tds.append(f'<td{style}>{inner}</td>')
                continue
            attr = html.escape(plain, quote=True)
            stats['copy_cell'] += 1
            btn = f'<button type="button" class="copy-btn copy-cell" data-copy="{attr}">[복사]</button>'
            cls = ' class="value-cell"' if is_value_col else ''
            role = ' role="button" tabindex="0"' if is_value_col else ''
            tds.append(
                f'<td{cls}{style}{role}><span class="cell-text">{inner}</span> {btn}</td>'
            )
        rows_html.append(f'<tr>{"".join(tds)}</tr>')

    return (
        f'<div class="table-wrap"><table>{colgroup}<thead><tr>{"".join(th_html)}</tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody></table></div>'
    )


FILENAME_TOKEN_RE = re.compile(r'^[\w][\w.\-]*\.(jpg|jpeg|png|gif|webp)$', re.IGNORECASE)

# 사진 단계의 파일 목록 줄: "hotel_01.jpg" 또는 "hotel_01.jpg — 출처: https://..."
PHOTO_SRC_LINE_RE = re.compile(
    r'^(?P<name>[\w][\w.\-]*\.(?:jpg|jpeg|png|gif|webp))\s*[\u2014\u2013-]+\s*출처\s*:\s*(?P<url>\S+)\s*$',
    re.IGNORECASE,
)
SAFE_URL_RE = re.compile(r'^https?://', re.IGNORECASE)

# 사진 단계마다 파일 목록 위에 자동으로 붙는 고지 (manual.md 에는 쓰지 않는다)
PHOTO_NOTICE_TEXT = (
    '사진의 저작권·사용 허락 확인은 사용자(여행사) 책임입니다. '
    '판매 화면에 올리기 전에 호텔의 허락을 받으세요.'
)
PHOTO_NOTICE_HTML = f'<p class="photo-notice">{html.escape(PHOTO_NOTICE_TEXT)}</p>'


def render_list(b, stats):
    _, ordered, items = b
    has_checkbox = any(CHECKBOX_ITEM_RE.match(it) for it in items)
    tag = 'ol' if (ordered and not has_checkbox) else 'ul'
    cls = ' class="checklist"' if has_checkbox else ''
    lis = []
    for it in items:
        m = CHECKBOX_ITEM_RE.match(it)
        if m:
            checked = m.group(1).lower() == 'x'
            text = m.group(2)
            stats['checkboxes'] += 1
            key = item_key(text)
            checked_attr = ' checked' if checked else ''
            inner = render_inline(text, stats, code_buttons=True)
            lis.append(
                f'<li><label class="chk"><input type="checkbox" data-key="{key}"{checked_attr}>'
                f'<span>{inner}</span></label></li>'
            )
        else:
            stripped_it = it.strip()
            # "파일명 — 출처: URL" 은 파일명(복사 버튼 유지) + 옆에 [출처] 링크로 나눈다
            m_src = PHOTO_SRC_LINE_RE.match(to_plain_text(stripped_it))
            if m_src:
                fname = m_src.group('name')
                url = m_src.group('url')
                stats['photo_sources'] += 1
                name_html = render_inline(f'`{fname}`', stats, code_buttons=True)
                if SAFE_URL_RE.match(url):
                    safe_url = html.escape(url, quote=True)
                    src_html = (
                        f'<a class="photo-src" href="{safe_url}" target="_blank" '
                        f'rel="noopener noreferrer" title="{safe_url}">출처</a>'
                    )
                else:
                    # http(s) 가 아니면 링크로 걸지 않고 글자만 보여준다
                    src_html = f'<span class="photo-src">출처: {html.escape(url)}</span>'
                lis.append(f'<li>{name_html} {src_html}</li>')
                continue
            # 백틱 없이 파일명만 달랑 있는 항목(사진 단계 목록)도 복사 버튼을 달아준다
            if '`' not in stripped_it and FILENAME_TOKEN_RE.match(stripped_it):
                it = f'`{stripped_it}`'
            inner = render_inline(it, stats, code_buttons=True)
            lis.append(f'<li>{inner}</li>')
    return f'<{tag}{cls}>{"".join(lis)}</{tag}>'


def _is_photo_file_list(b):
    """블록이 사진 파일 목록인가 — `- hotel_01.jpg` / `- hotel_01.jpg — 출처: URL` 항목."""
    if b[0] != 'list':
        return False
    for it in b[2]:
        plain = to_plain_text(it).strip()
        if PHOTO_SRC_LINE_RE.match(plain) or FILENAME_TOKEN_RE.match(plain):
            return True
    return False


def _is_photo_pick_para(b):
    """`파일 선택 → 아래 파일` 같은 안내 줄인가."""
    return b[0] == 'para' and '파일 선택' in b[1] and '아래 파일' in b[1]


def _step_ranges(blocks):
    """## 제목(단계)마다 [시작, 끝) 인덱스 구간으로 자른다. 앞머리(제목 전)도 한 구간."""
    starts = [i for i, b in enumerate(blocks) if b[0] == 'heading' and b[1] == 2]
    if not starts:
        return [(0, len(blocks))]
    ranges = [(0, starts[0])] if starts[0] > 0 else []
    for j, s in enumerate(starts):
        ranges.append((s, starts[j + 1] if j + 1 < len(starts) else len(blocks)))
    return ranges


def find_photo_notice_positions(blocks):
    """사진 단계마다 저작권 고지를 넣을 블록 인덱스 집합.
    파일 목록이 있으면 그 바로 위, 없으면 `파일 선택` 안내 줄 바로 뒤."""
    positions = set()
    for start, end in _step_ranges(blocks):
        seg = range(start, end)
        list_idx = next((i for i in seg if _is_photo_file_list(blocks[i])), None)
        if list_idx is not None:
            positions.add(list_idx)
            continue
        pick_idx = next((i for i in seg if _is_photo_pick_para(blocks[i])), None)
        if pick_idx is not None:
            positions.add(pick_idx + 1)
    return positions


def render_block(b, stats, existing_ids, nav_items):
    kind = b[0]

    if kind == 'heading':
        level = b[1]
        raw = b[2]
        plain = to_plain_text(raw)
        _id = slugify(plain, existing_ids)

        if level == 2:
            nav_items.append((_id, level, plain))
            skey = step_key(plain)
            stats['checkboxes'] += 1  # 단계마다 붙는 "완료" 진행 체크박스도 실제 산출물이다
            m = HEADING_NUM_RE.match(plain)
            m_raw = HEADING_NUM_RE.match(raw)
            if m and m_raw:
                num_html = html.escape(m.group(1))
                title_html = render_inline(m_raw.group(2), stats, code_buttons=False)
                num_span = f'<span class="step-num">{num_html}</span>'
            else:
                title_html = render_inline(raw, stats, code_buttons=False)
                num_span = ''
            done_html = (
                f'<label class="step-done-wrap"><input type="checkbox" class="step-done" '
                f'data-key="{skey}"><span>완료</span></label>'
            )
            return (
                f'<h2 id="{_id}"><span class="step-head">{num_span}'
                f'<span class="step-title">{title_html}</span></span>{done_html}</h2>'
            )

        inner = render_inline(raw, stats, code_buttons=False)
        return f'<h{level} id="{_id}">{inner}</h{level}>'

    if kind == 'hr':
        return '<hr class="sep">'

    if kind == 'label':
        label, content = b[1], b[2]
        esc_label = html.escape(label)
        if label == '폴더' and content.strip():
            # 경로는 파일 선택창에 붙여넣는 값이므로 코드처럼 보여주고 전체 경로 복사 버튼 하나만 단다.
            path = content.strip()
            esc_path = html.escape(path)
            attr = html.escape(path, quote=True)
            stats['copy_code'] += 1
            inner = (
                f'<span class="code-copy"><code>{esc_path}</code>'
                f'<button type="button" class="copy-btn copy-code" data-copy="{attr}">[복사]</button></span>'
            )
        else:
            inner = render_inline(content, stats, code_buttons=False, bracket_buttons=True) if content else ''
        label_cls = ' class="lbl-warn"' if label == '주의' else ''
        return f'<p class="mline"><strong{label_cls}>{esc_label}:</strong> {inner}</p>'

    if kind == 'action':
        inner = render_inline(b[1], stats, code_buttons=True)
        return f'<div class="action-box">{inner}</div>'

    if kind == 'code':
        lang, content = b[1], b[2]
        esc = html.escape(content)
        attr = html.escape(content, quote=True)
        stats['copy_block'] += 1
        lang_label = f' <span class="lang-tag">{html.escape(lang)}</span>' if lang else ''
        return (
            f'<div class="codeblock-wrap"><pre class="codeblock"><code>{esc}</code></pre>'
            f'<button type="button" class="copy-btn copy-block" data-copy="{attr}">[복사]</button>'
            f'{lang_label}</div>'
        )

    if kind == 'blockquote':
        paras = []
        for l in b[1]:
            s = l.strip()
            if s == '':
                continue
            paras.append(f'<p>{render_inline(s, stats, code_buttons=False)}</p>')
        return f'<blockquote>{"".join(paras)}</blockquote>'

    if kind == 'table':
        return render_table(b, stats)

    if kind == 'list':
        return render_list(b, stats)

    if kind == 'para':
        return f'<p>{render_inline(b[1], stats, code_buttons=False)}</p>'

    return ''


# ---------------------------------------------------------------------------
# 사진 갤러리
# ---------------------------------------------------------------------------

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
THUMB_MAX_W = 320
THUMB_JPEG_QUALITY = 78
FALLBACK_MAX_BYTES = 300 * 1024


def make_thumb(path):
    """(data_uri, note) 를 돌려준다. data_uri 가 None 이면 note 에 이유가 담긴다."""
    try:
        if HAS_PIL:
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im)
                if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):
                    bg = Image.new('RGB', im.size, (255, 255, 255))
                    rgba = im.convert('RGBA')
                    bg.paste(rgba, mask=rgba.split()[-1])
                    im = bg
                elif im.mode != 'RGB':
                    im = im.convert('RGB')
                w, h = im.size
                if w > THUMB_MAX_W:
                    ratio = THUMB_MAX_W / float(w)
                    im = im.resize((THUMB_MAX_W, max(1, int(h * ratio))))
                buf = io.BytesIO()
                im.save(buf, format='JPEG', quality=THUMB_JPEG_QUALITY)
                b64 = base64.b64encode(buf.getvalue()).decode('ascii')
                return f'data:image/jpeg;base64,{b64}', None
        size = path.stat().st_size
        if size <= FALLBACK_MAX_BYTES:
            mime = mimetypes.guess_type(str(path))[0] or 'image/jpeg'
            b64 = base64.b64encode(path.read_bytes()).decode('ascii')
            return f'data:{mime};base64,{b64}', None
        return None, f'{size // 1024}KB > {FALLBACK_MAX_BYTES // 1024}KB (PIL 미설치라 원본만 임베드 가능)'
    except Exception as e:
        return None, str(e)


README_FILE_HDRS = {'파일', '파일명', 'file', 'filename'}
README_CONTENT_HDRS = {'내용', '설명', 'content'}
README_SOURCE_HDRS = {'출처', 'source'}


def parse_readme_gallery_info(readme_path, stats):
    """README.md 의 (파일|내용|출처) 표를 filename -> (내용_html, 출처_html) 로,
    표 밖의 나머지 블록(주의사항 등)은 extra_html 로 돌려준다."""
    try:
        text = strip_html_comments(readme_path.read_text(encoding='utf-8'))
        text = normalize_circled_numbers(text)
    except Exception:
        return {}, ''
    blocks = parse_blocks(text.splitlines())
    lookup = {}
    extra_parts = []
    dummy_ids = set()
    dummy_nav = []
    table_consumed = False
    for b in blocks:
        if b[0] == 'table' and not table_consumed:
            table_consumed = True
            _, header_cells, _align, rows = b
            headers_plain = [to_plain_text(h).strip() for h in header_cells]

            def find_col(names):
                for i, h in enumerate(headers_plain):
                    if h in names:
                        return i
                return None

            fi = find_col(README_FILE_HDRS)
            ci = find_col(README_CONTENT_HDRS)
            si = find_col(README_SOURCE_HDRS)
            if fi is None:
                fi = 0
            if ci is None and len(headers_plain) > 1:
                ci = 1
            if si is None and len(headers_plain) > 2:
                si = 2
            for row in rows:
                if fi >= len(row):
                    continue
                fname = to_plain_text(row[fi]).strip()
                if not fname:
                    continue
                content_html = render_inline(row[ci], stats, code_buttons=False) if ci is not None and ci < len(row) else ''
                source_html = render_inline(row[si], stats, code_buttons=False) if si is not None and si < len(row) else ''
                lookup[fname] = (content_html, source_html)
            continue
        if b[0] == 'heading':
            continue
        piece = render_block(b, stats, dummy_ids, dummy_nav)
        if piece:
            extra_parts.append(piece)
    return lookup, '\n'.join(extra_parts)


def build_gallery(photos_dir, stats):
    if not photos_dir.is_dir():
        return f'<div class="gallery-wrap"><p>사진 폴더를 찾을 수 없다: <code>{html.escape(str(photos_dir))}</code></p></div>'

    files = sorted(
        p for p in photos_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    stats['photos'] = len(files)

    readme = photos_dir / 'README.md'
    lookup, extra_html = parse_readme_gallery_info(readme, stats) if readme.is_file() else ({}, '')

    rows = []
    for f in files:
        data_uri, note = make_thumb(f)
        name_attr = html.escape(f.name, quote=True)
        if data_uri:
            img_html = f'<img src="{data_uri}" alt="{name_attr}">'
        else:
            img_html = html.escape(f'(파일명만 표시: {note or ""})')
        stats['copy_photo'] += 1
        content_html, source_html = lookup.get(f.name, ('', ''))
        rows.append(
            '<tr>'
            f'<td class="photo-thumb-cell">{img_html}</td>'
            f'<td>{html.escape(f.name)} '
            f'<button type="button" class="copy-btn copy-photo" data-copy="{name_attr}">[복사]</button></td>'
            f'<td>{content_html}</td>'
            f'<td>{source_html}</td>'
            '</tr>'
        )

    meta = f'폴더: <code>{html.escape(str(photos_dir))}</code> · 이미지 {len(files)}장'
    if not HAS_PIL:
        meta += ' (PIL 미설치 — 300KB 이하 원본만 임베드)'

    if rows:
        table_html = (
            '<div class="table-wrap"><table><thead><tr>'
            '<th>썸네일</th><th>파일명</th><th>내용</th><th>출처</th>'
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
        )
    else:
        table_html = ''

    extra_block = f'<div class="gallery-note">{extra_html}</div>' if extra_html else ''
    return f'<div class="gallery-wrap"><p>{meta}</p>{table_html}{extra_block}</div>'


def group_toc_items(nav_items):
    """제목이 같은 접두(괄호 앞 부분)로 연속되는 단계를 하나로 묶는다.
    각 그룹: {'ids':[...], 'nums':[...], 'prefix':str, 'fulls':[...], 'first_full':str}.
    'fulls' 는 그룹에 속한 모든 단계의 전체 제목(완료 체크박스 키 계산용)."""
    groups = []
    for _id, _level, label in nav_items:
        m = HEADING_NUM_RE.match(label)
        num, title = (m.group(1), m.group(2)) if m else ('', label)
        prefix = title.split('(', 1)[0].strip() if '(' in title else title
        if groups and prefix and groups[-1]['prefix'] == prefix:
            groups[-1]['ids'].append(_id)
            groups[-1]['nums'].append(num)
            groups[-1]['fulls'].append(label)
        else:
            groups.append({'ids': [_id], 'nums': [num], 'prefix': prefix, 'fulls': [label], 'first_full': label})
    return groups


def build_toc(nav_items):
    """nav_items: [(id, level, label)] — 실제 입력 단계인 ## 제목만 담긴다(### 중첩 없음).
    같은 접두로 연속되는 단계는 "N~M. 접두 (count회)" 한 줄로 묶고 첫 단계로 링크한다.
    묶인 줄의 완료 표시는 그룹의 모든 단계가 다 체크됐을 때만 ☑, 일부만 됐으면 "k/N" 을
    회색으로 붙인다(JS 가 data-keys 목록을 보고 계산 — step_key 는 16자리 hex 라 콤마로 이어도 안전)."""
    if not nav_items:
        return ''
    groups = group_toc_items(nav_items)
    parts = ['<nav class="toc" aria-label="목차"><p class="toc-title">목차</p><ol class="toc-list">']
    for g in groups:
        first_id = g['ids'][0]
        keys_attr = html.escape(','.join(step_key(f) for f in g['fulls']), quote=True)
        if len(g['ids']) >= 2 and all(g['nums']):
            label = f"{g['nums'][0]}~{g['nums'][-1]}. {g['prefix']} ({len(g['ids'])}회)"
        else:
            label = g['first_full']
        esc_label = html.escape(label)
        parts.append(
            f'<li data-keys="{keys_attr}"><span class="toc-check">☐</span> '
            f'<a href="#{first_id}">{esc_label}</a><span class="toc-progress"></span></li>'
        )
    parts.append('</ol></nav>')
    return ''.join(parts)


# ---------------------------------------------------------------------------
# 페이지 조립 (아티팩트 규약: DOCTYPE/html/head/body 없음, title+style 최상단)
# ---------------------------------------------------------------------------

_STYLE_CSS_BODY = """
*{box-sizing:border-box;}
:root{
  --bg:#EEF3F8;
  --ink:#1B2A41;
  --muted:#5E6E82;
  --rule:#C9D5E2;
  --accent:#F2B233;
  --accent-ink:#1B2A41;
  --sky:#3E7CB1;
  --brick:#C8553D;
  --code-bg:#E1E9F2;
  --panel:#FFFFFF;
  color-scheme:light dark;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#111925;
    --ink:#E8EEF6;
    --muted:#9FB0C3;
    --rule:#2C3A4C;
    --accent:#F5C04A;
    --accent-ink:#111925;
    --sky:#7FB3E3;
    --brick:#E8846C;
    --code-bg:#1C2736;
    --panel:#182233;
  }
}
:root[data-theme="dark"]{
  --bg:#111925;
  --ink:#E8EEF6;
  --muted:#9FB0C3;
  --rule:#2C3A4C;
  --accent:#F5C04A;
  --accent-ink:#111925;
  --sky:#7FB3E3;
  --brick:#E8846C;
  --code-bg:#1C2736;
  --panel:#182233;
}
body{
  margin:0;
  background:var(--bg);
  color:var(--ink);
  font-family:"Pretendard","Apple SD Gothic Neo","Noto Sans KR",sans-serif;
  line-height:1.7;
  font-size:19px;
}
input[type=checkbox]{accent-color:var(--sky);}
main.card{max-width:60rem;margin:0 auto;padding:40px 24px 80px;}
h1{font-size:26px;font-weight:700;margin:0 0 22px;padding-bottom:12px;border-bottom:1px solid var(--rule);}
h2{
  display:flex;align-items:center;flex-wrap:wrap;gap:16px;
  margin:0 0 18px;font-weight:700;
}
h3{font-size:20px;font-weight:700;margin:22px 0 10px;}
h4{font-size:19px;font-weight:700;margin:16px 0 8px;}
p{margin:10px 0;}
p.mline{margin:10px 0;font-size:20px;}
p.mline strong{font-weight:700;}
.lbl-warn{color:var(--brick);}
.btn-look{
  display:inline-block;border:1px solid var(--rule);background:var(--code-bg);border-radius:4px;
  padding:2px 10px;font-weight:700;margin:0 2px;
}
blockquote{margin:12px 0;padding:2px 0 2px 16px;border-left:2px solid var(--rule);font-style:italic;}
blockquote p{margin:5px 0;}
hr.sep{border:none;border-top:1px solid var(--rule);margin:26px 0;}
ul,ol{padding-left:26px;margin:10px 0;}
li{margin:4px 0;}
ul.checklist{list-style:none;padding-left:0;}
ul.checklist li{margin:6px 0;}
label.chk{display:flex;align-items:flex-start;gap:8px;cursor:pointer;}
label.chk input[type=checkbox]{margin-top:5px;flex:0 0 auto;width:18px;height:18px;}
label.chk input[type=checkbox]:checked ~ span{text-decoration:line-through;}
code{font-family:"Courier New",ui-monospace,Consolas,monospace;font-size:.9em;background:var(--code-bg);padding:1px 5px;border-radius:4px;}
.code-copy{white-space:nowrap;}
.codeblock-wrap{position:relative;margin:12px 0;border:1px solid var(--rule);background:var(--code-bg);border-radius:8px;padding:12px 14px;}
.codeblock-wrap code{background:none;padding:0;}
pre.codeblock{margin:0;white-space:pre-wrap;word-break:break-word;font-size:16px;line-height:1.5;font-family:"Courier New",ui-monospace,Consolas,monospace;}
.copy-block{display:block;margin-top:8px;text-align:right;}
.lang-tag{font-size:.6em;color:var(--muted);}
.action-box{
  display:block;width:fit-content;
  background:var(--accent);color:var(--accent-ink);
  border:none;border-radius:8px;
  padding:12px 32px;
  margin:20px auto 0;
  font-weight:700;
  font-size:20px;
  text-align:center;
}
section.step{
  background:var(--panel);border:1px solid var(--rule);border-radius:10px;
  padding:28px 32px;margin-top:40px;
}
section.step.done, section.step.done *{color:var(--muted) !important;border-color:var(--rule) !important;}
.step-head{display:flex;align-items:baseline;gap:14px;flex:1 1 auto;min-width:0;}
.step-num{
  display:inline-flex;align-items:center;justify-content:center;
  min-width:28px;height:28px;padding:0 8px;
  background:var(--accent);color:var(--accent-ink);
  border-radius:999px;font-size:16px;font-weight:700;line-height:1;
}
.step-title{font-size:24px;font-weight:700;line-height:1.3;}
.step-done-wrap{
  display:flex;align-items:center;gap:6px;
  font-size:16px;font-weight:400;flex:0 0 auto;color:var(--muted);
  cursor:pointer;white-space:nowrap;margin-left:auto;
}
.step-done-wrap input[type=checkbox]{width:20px;height:20px;}
.table-wrap{overflow-x:auto;margin:12px 0;}
table{width:100%;border-collapse:collapse;font-size:17px;}
th,td{border:none;border-bottom:1px solid var(--rule);padding:14px 10px;text-align:left;vertical-align:top;word-wrap:break-word;}
thead th{border-top:1px solid var(--rule);}
th{font-weight:700;color:var(--muted);}
td .cell-text{display:inline;}
td.value-cell{
  cursor:pointer;background:none;
  display:flex;align-items:center;justify-content:space-between;gap:10px;
}
td.value-cell .cell-text{flex:1 1 auto;}
td.value-cell .copy-btn{flex:0 0 auto;white-space:nowrap;}
.v-select-mark{color:var(--sky);font-weight:600;}
.v-muted{color:var(--muted);font-style:italic;}
.copy-btn{
  border:none;background:none;color:var(--sky);
  font-family:inherit;font-size:14px;cursor:pointer;
  padding:0 1px;text-decoration:none;
}
.copy-btn:hover{text-decoration:underline;}
.copy-btn.copied{font-weight:700;}
.photo-notice{margin:12px 0 6px;font-size:14px;line-height:1.5;color:var(--muted);}
.photo-src{font-size:14px;color:var(--sky);margin-left:6px;white-space:nowrap;}
.gallery-wrap{margin:12px 0;}
.photo-thumb-cell{text-align:center;}
.photo-thumb-cell img{display:block;max-width:140px;max-height:110px;margin:0 auto;}
.gallery-note{margin-top:12px;font-size:.85em;color:var(--muted);}
.toc{
  background:var(--panel);border:1px solid var(--rule);border-radius:10px;
  padding:28px 32px;margin:0 0 40px;
}
.toc-title{font-weight:700;margin:0 0 10px;}
.toc-list{margin:0;padding-left:0;list-style:none;}
.toc li{margin:8px 0;}
.toc-check{display:inline-block;width:1.3em;color:var(--muted);}
.toc-progress{color:var(--muted);font-size:.8em;margin-left:6px;}
.toc a{color:var(--ink);text-decoration:none;}
.toc a:hover{text-decoration:underline;}
.foot{max-width:60rem;margin:0 auto;padding:18px 24px 60px;font-size:.65em;color:var(--muted);border-top:1px solid var(--rule);}
@page{size:A4;margin:2cm;}
@media print{
  body{background:#fff;color:#000;}
  section.step,.toc,.action-box,.codeblock-wrap,code{background:none !important;}
  .copy-btn{display:none !important;}
  a{color:#000;text-decoration:underline;}
  tr{page-break-inside:avoid;}
  h1,h2,h3,h4{page-break-after:avoid;}
  .toc{page-break-inside:avoid;}
}
"""


def build_style_css(font_b64):
    """Pretendard 가변 폰트를 base64 로 넣으면 @font-face 를 CSS 맨 앞에 붙인다."""
    if not font_b64:
        return _STYLE_CSS_BODY
    font_face = (
        '@font-face{'
        'font-family:"Pretendard";'
        f'src:local("Pretendard"),url(data:font/woff2;base64,{font_b64}) format("woff2");'
        'font-weight:45 920;'
        'font-display:swap;'
        '}\n'
    )
    return font_face + _STYLE_CSS_BODY

SCRIPT_JS = """
(function(){
  function fallbackCopy(text){
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '-1000px';
    ta.style.left = '-1000px';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    document.body.removeChild(ta);
    return ok;
  }

  function copyText(text){
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(function(){
        if (!fallbackCopy(text)) throw new Error('copy failed');
      });
    }
    return new Promise(function(resolve, reject){
      if (fallbackCopy(text)) resolve(); else reject(new Error('copy failed'));
    });
  }

  function flashButton(btn){
    if (!btn) return;
    btn.textContent = '[복사됨]';
    btn.classList.add('copied');
    window.clearTimeout(btn._copyTimer);
    btn._copyTimer = window.setTimeout(function(){
      btn.textContent = '[복사]';
      btn.classList.remove('copied');
    }, 1000);
  }

  function triggerCopy(btn){
    if (!btn) return;
    var text = btn.getAttribute('data-copy') || '';
    copyText(text).then(function(){ flashButton(btn); }).catch(function(){});
  }

  document.addEventListener('click', function(ev){
    var btn = ev.target.closest ? ev.target.closest('.copy-btn') : null;
    if (btn) {
      triggerCopy(btn);
      ev.stopPropagation();
      return;
    }
    var cell = ev.target.closest ? ev.target.closest('td.value-cell') : null;
    if (cell) {
      triggerCopy(cell.querySelector('.copy-btn'));
    }
  });

  document.addEventListener('keydown', function(ev){
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    var t = ev.target;
    if (!t || !t.classList || !t.classList.contains('value-cell')) return;
    ev.preventDefault();
    triggerCopy(t.querySelector('.copy-btn'));
  });

  try {
    var STORE_KEY = 'stay-card-progress-v1';
    var store = {};
    try { store = JSON.parse(window.localStorage.getItem(STORE_KEY) || '{}'); } catch (e) { store = {}; }

    // 목차 각 줄은 data-keys 에 그 줄에 속한 모든 단계의 완료 키를 콤마로 담고 있다.
    // 전부 체크면 ☑, 일부만 체크면 "k/N" 회색 표시, 0개면 아무 표시 없음(1개짜리 줄은 항상 ☑/☐ 만).
    var keyToLi = {};
    var tocLis = document.querySelectorAll('.toc li[data-keys]');
    for (var t = 0; t < tocLis.length; t++) {
      var li = tocLis[t];
      var keys = (li.getAttribute('data-keys') || '').split(',').filter(Boolean);
      for (var k2 = 0; k2 < keys.length; k2++) { keyToLi[keys[k2]] = li; }
    }

    function updateTocLi(li){
      var keys = (li.getAttribute('data-keys') || '').split(',').filter(Boolean);
      var total = keys.length;
      var done = 0;
      for (var i2 = 0; i2 < keys.length; i2++) { if (store[keys[i2]]) done++; }
      var checkSpan = li.querySelector('.toc-check');
      var badge = li.querySelector('.toc-progress');
      if (checkSpan) checkSpan.textContent = (total > 0 && done === total) ? '☑' : '☐';
      if (badge) badge.textContent = (total > 1 && done > 0 && done < total) ? (done + '/' + total) : '';
    }

    function syncStepDone(cb){
      var sec = cb.closest ? cb.closest('section.step') : null;
      if (sec) sec.classList.toggle('done', cb.checked);
      var li = keyToLi[cb.getAttribute('data-key')];
      if (li) updateTocLi(li);
    }

    for (var t3 = 0; t3 < tocLis.length; t3++) { updateTocLi(tocLis[t3]); }

    var boxes = document.querySelectorAll('input[type=checkbox][data-key]');
    for (var i = 0; i < boxes.length; i++) {
      (function(cb){
        var k = cb.getAttribute('data-key');
        var isStep = cb.classList.contains('step-done');
        if (store[k]) cb.checked = true;
        if (isStep) { var s0 = cb.closest ? cb.closest('section.step') : null; if (s0) s0.classList.toggle('done', cb.checked); }
        cb.addEventListener('change', function(){
          try {
            var s = JSON.parse(window.localStorage.getItem(STORE_KEY) || '{}');
            if (cb.checked) s[k] = true; else delete s[k];
            window.localStorage.setItem(STORE_KEY, JSON.stringify(s));
            store = s;
          } catch (e) {}
          if (isStep) syncStepDone(cb);
        });
      })(boxes[i]);
    }
  } catch (e) {}
})();
"""


def assemble_page(title, filename, body_html, font_b64=None):
    esc_title = html.escape(title)
    esc_filename = html.escape(filename)
    main = f'<main class="card">{body_html}</main>'
    footer = ''
    parts = [
        f'<title>{esc_title}</title>',
        '<style>', build_style_css(font_b64), '</style>',
        main,
        footer,
        '<script>', SCRIPT_JS, '</script>',
    ]
    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# 오케스트레이션
# ---------------------------------------------------------------------------

def render_card(md_text, filename, photos_dir, title_override, font_b64=None):
    global _CURRENT_FILE
    _CURRENT_FILE = filename

    stats = {
        'tables': 0, 'checkboxes': 0, 'copy_code': 0, 'copy_cell': 0,
        'copy_photo': 0, 'copy_block': 0, 'photos': 0, 'nav_items': 0,
        'photo_notices': 0, 'photo_sources': 0,
        'value_kinds': Counter(),  # typed/select/check/muted/file 셀 개수 (2열 표만)
    }

    text = strip_html_comments(md_text)
    text = normalize_circled_numbers(text)
    lines = text.splitlines()
    blocks = parse_blocks(lines)

    doc_title = None
    for b in blocks:
        if b[0] == 'heading' and b[1] == 1:
            doc_title = to_plain_text(b[2])
            break
    if not doc_title:
        doc_title = filename
    page_title = title_override or doc_title

    gallery_idx = None
    if photos_dir:
        last_idx = None
        last_level = None
        for idx, b in enumerate(blocks):
            if b[0] == 'heading' and '사진' in to_plain_text(b[2]):
                last_idx = idx
                last_level = b[1]
        if last_idx is not None:
            end = len(blocks)
            for idx in range(last_idx + 1, len(blocks)):
                b = blocks[idx]
                if b[0] == 'heading' and b[1] <= last_level:
                    end = idx
                    break
            gallery_idx = end
        else:
            gallery_idx = len(blocks)

    existing_ids = set()
    nav_items = []  # (id, level, label) — level 2 제목, 목차용
    notice_positions = find_photo_notice_positions(blocks)
    body_parts = []
    h1_pos = None
    step_open = False
    for idx, b in enumerate(blocks):
        if photos_dir and gallery_idx == idx:
            body_parts.append(build_gallery(photos_dir, stats))
        if idx in notice_positions:
            stats['photo_notices'] += 1
            body_parts.append(PHOTO_NOTICE_HTML)
        if b[0] == 'heading' and b[1] == 2:
            if step_open:
                body_parts.append('</section>')
            body_parts.append('<section class="step">')
            step_open = True
        body_parts.append(render_block(b, stats, existing_ids, nav_items))
        if b[0] == 'heading' and b[1] == 1 and h1_pos is None:
            h1_pos = len(body_parts) - 1
    if len(blocks) in notice_positions:
        stats['photo_notices'] += 1
        body_parts.append(PHOTO_NOTICE_HTML)
    if step_open:
        body_parts.append('</section>')
    if photos_dir and gallery_idx == len(blocks):
        body_parts.append(build_gallery(photos_dir, stats))

    stats['nav_items'] = len(nav_items)
    toc_html = build_toc(nav_items)
    if toc_html:
        insert_at = (h1_pos + 1) if h1_pos is not None else 0
        body_parts.insert(insert_at, toc_html)

    body_html = '\n'.join(p for p in body_parts if p)
    full_html = assemble_page(page_title, filename, body_html, font_b64)
    return full_html, stats


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='호텔 세팅 카드 md를 복사-친화적 단일 HTML로 변환한다.',
    )
    ap.add_argument('input', help='입력 마크다운 카드 파일')
    ap.add_argument('-o', '--output', required=True, help='출력 HTML 파일 경로')
    ap.add_argument('--photos', default=None, help='사진 폴더 (선택)')
    ap.add_argument('--title', default=None, help='HTML <title> (기본: 문서 첫 # 제목)')
    ap.add_argument('--font', default=None, help='Pretendard 가변 woff2 폰트 파일 경로 (base64 로 임베드)')
    args = ap.parse_args(argv)

    src_path = Path(args.input)
    if not src_path.is_file():
        print(f'입력 파일을 찾을 수 없다: {src_path}', file=sys.stderr)
        return 1
    md_text = src_path.read_text(encoding='utf-8')

    photos_dir = Path(args.photos) if args.photos else None

    font_b64 = None
    font_note = '임베드 안 함(시스템 Pretendard/고딕 폴백)'
    if args.font:
        font_path = Path(args.font)
        if font_path.is_file():
            font_bytes = font_path.read_bytes()
            font_b64 = base64.b64encode(font_bytes).decode('ascii')
            font_note = f'임베드 {len(font_bytes) / 1024 / 1024:.2f}MB ({font_path.name})'
        else:
            print(f'경고: 폰트 파일을 찾을 수 없다: {font_path} (시스템 폰트로 대체)', file=sys.stderr)

    html_out, stats = render_card(md_text, src_path.name, photos_dir, args.title, font_b64)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_out, encoding='utf-8')

    size = len(html_out.encode('utf-8'))
    total_copy_btns = stats['copy_code'] + stats['copy_cell'] + stats['copy_photo'] + stats['copy_block']

    print(f'OK: {out_path}')
    print(f'  크기: {size / 1024:.1f} KB ({size:,} bytes)' + (' ⚠ 16MB 초과' if size > 16 * 1024 * 1024 else ''))
    print(f'  표: {stats["tables"]}개')
    print(
        f'  복사 버튼: 총 {total_copy_btns}개'
        f' (표 셀 {stats["copy_cell"]} · 코드 스팬 {stats["copy_code"]}'
        f' · 코드블록 전체 {stats["copy_block"]} · 사진 파일명 {stats["copy_photo"]})'
    )
    print(f'  체크박스: {stats["checkboxes"]}개')
    print(f'  목차 항목: {stats["nav_items"]}개')
    print(f'  사진: {stats["photos"]}장 (썸네일: {"PIL 축소" if HAS_PIL else "폴백(300KB 이하 원본만)"})')
    if stats['photo_notices'] or stats['photo_sources']:
        print(f'  사진 저작권 고지: {stats["photo_notices"]}개 · 출처 링크: {stats["photo_sources"]}개')
    print(f'  폰트: {font_note}')
    vk = stats['value_kinds']
    if vk:
        print(
            f'  값 셀 종류(2열 표만): 타이핑 {vk.get("typed", 0)} · 선택 {vk.get("select", 0)}'
            f' · 체크/해제 {vk.get("check", 0)} · 회색(비움 등) {vk.get("muted", 0)} · 파일 {vk.get("file", 0)}'
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())
