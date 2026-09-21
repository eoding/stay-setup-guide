#!/usr/bin/env python3
"""render_screen_guide.py — 화면 사전(screen-dictionary.json) → 직원용 화면 안내 HTML 한 장.

호텔을 **손으로** 까는 담당자가 읽는 문서다. 호텔마다 받는 입력 지시서
(`<이름>_입력지시서.html`)가 "무엇을 넣는지" 를 말하고, 이 문서는 "화면이 어떻게 움직이는지"
를 말한다. 스크린샷은 쓰지 않는다 — 화면 사전에서 통째로 만들어 내므로 사전이 새 배포판으로
바뀌면 이 문서도 같이 새로 나온다.

사전의 `meta.screen_count` · `meta.field_count` 와 실제로 그린 화면 수 · 칸 수가 다르면
끝에서 경고를 내고 종료 코드 1 을 돌려준다 — 사전을 고치고 이 문서를 다시 만들지 않은 상태다.

같은 사전으로 두 번 돌리면 **바이트까지 같은 파일**이 나온다(오늘 날짜를 찍지 않고 사전의
`generated_on` 만 쓴다).

사용법:
    python3 render_screen_guide.py                      # 사전 → docs/화면-안내.html
    python3 render_screen_guide.py -o /tmp/미리보기.html
    python3 render_screen_guide.py --dictionary <다른 사전.json> --no-font
"""

import argparse
import base64
import html
import json
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS_DIR.parent
REPO_ROOT = SKILL_DIR.parent.parent

DEFAULT_DICTIONARY = SKILL_DIR / 'references' / 'screen-dictionary.json'
DEFAULT_OUTPUT = REPO_ROOT / 'docs' / '화면-안내.html'
DEFAULT_FONT = SCRIPTS_DIR / 'fonts' / 'PretendardVariable.woff2'
SKILL_MD = SKILL_DIR / 'SKILL.md'

PAGE_TITLE = 'ERP Stay 화면 안내'
STAMP_META_NAME = 'stay-screen-guide'
STAMP_VERSION = 'v1'

#: 이 문서를 다시 만드는 명령 (푸터에 그대로 적는다).
REGEN_COMMAND = 'python3 skills/stay-setup-guide/scripts/render_screen_guide.py'

#: 탭 글자를 여는 길에서 뽑는다 — `편집 화면 탭 \`객실\`` 꼴.
_TAB_RE = re.compile(r'편집 화면 탭 `([^`]+)`')

#: 탭이 없는 화면을 모으는 묶음 이름 (사전의 `tabs` 에는 없다).
OUTSIDE_TABS = '탭 밖 화면'


# ---------------------------------------------------------------------------
# 「화면 읽는 법」 — 손으로 쓴 상수다.
# 근거는 `stay-setup-run/references/screen-mechanics.md` 와 `references/MANUAL-SPEC.md` 뿐이고,
# 거기 없는 말은 적지 않는다.
# ---------------------------------------------------------------------------

HOWTO_ITEMS = [
    (
        '드로어(서랍)에서 입력한다',
        'Stay 탭의 입력은 거의 전부 오른쪽에서 밀려 나오는 서랍에서 한다. '
        '칸 이름은 왼쪽, 입력은 그 오른쪽, 도움말은 그 아래다. '
        '**저장 버튼은 그 서랍 안에 있다** — [저장]·[추가]·[만들기]·[이 단가로 깔기]처럼 화면마다 글자가 다르다. '
        '닫기는 Esc 이고, 서랍을 연 채로 페이지를 새로 고치지 않는다.',
    ),
    (
        '탭을 옮기는 것은 저장이 아니다',
        '위쪽 탭 글자를 눌러도 값은 저장되지 않는다. 탭마다 자기 저장 버튼이 있다. '
        '오른쪽 위의 [저장]은 「기본정보」·「참조정보」·「추가수집정보」·「환율 설정」·「SEO」 같은 상품 공통 탭에만 보이고, '
        'Stay 탭(호텔 정보·객실·오퍼·시즌·요금제·판매일·가격 캘린더·부과금·부가옵션·프로모션·취소정책·혜택)에는 없다.',
    ),
    (
        '맨 위 검증 배너의 🔴 와 🟡',
        '편집 화면 맨 위에 두 묶음이 선다 — 「🔴 이대로면 못 팝니다」와 「🟡 채우면 좋음」이다. '
        '**🔴 가 하나라도 있으면 [판매 시작]이 눌리지 않는다.** '
        '같은 문제가 여러 건이면 「같은 문제 N건 ▼」로 접히니 남은 건수는 펼쳐서 센다. '
        '합격선은 판매 시작 전 🔴 0 · 🟡 0 이다.',
    ),
    (
        '판매 연결은 오퍼가 먼저다',
        '새로 만든 호텔은 오퍼 0건 · 룸 0건 · 판매 연결 0건이다. '
        '오퍼가 하나도 없으면 `객실` 탭 `판매 연결` 카드의 [객실 추가]가 그려지지 않고 「오퍼를 먼저 만드세요」 안내만 뜬다. '
        '그래서 순서는 **오퍼 → 룸 → 판매 연결**이다. [룸 추가]는 룸 타입만 만들 뿐 판매 연결을 만들지 않는다.',
    ),
    (
        '가격 캘린더의 날짜 칸은 작은 창을 연다',
        '순서는 오퍼 줄 고르기 → 목표 달로 이동 → 룸 줄 고르기([룸별 입력]) → 날짜 칸 누르기다. '
        '**판매일이 열린 날만 눌린다** — 닫힌 날은 글자라 눌리지 않는다. '
        '날짜 칸을 누르면 작은 창이 열리고, 그 안에서 인원 조합 행을 채워 **그 행의** [저장](없던 행이면 [추가])을 누른다.',
    ),
    (
        '카드와 행을 보고 누른다',
        '화면은 오퍼별·룸별 카드가 겹겹이다. 같은 이름이 여러 카드에 있을 수 있으니 '
        '누르려는 버튼이 **있는** 카드 안에서 행을 찾는다. '
        '행 하나 없는 빈 카드도 제 상자를 가진다.',
    ),
    (
        '되돌리기 어려운 버튼은 확인창을 연다',
        '[삭제]·[보관]·[판매 종료]·[판매 재개]·[공용으로]·[전용으로 분리]·[빈 판매일 정리]·[세후가로 확정] 같은 버튼은 '
        '누르면 곧바로 실행되지 않고 화면 가운데에 작은 창이 뜬다. '
        '브라우저가 띄우던 알림창이 아니라 이 화면 안의 창이고, 버튼은 [취소]·[확인] 둘이다.',
    ),
    (
        '[판매 시작]은 맨 마지막이고 사람이 누른다',
        '세팅이 끝나면 배너가 🔴 0 · 🟡 0 인지 보고, 가격 캘린더·요금제·부과금을 한 번 훑은 뒤 '
        '**사람이 직접** [판매 시작]을 누른다. 도구는 이 버튼을 누르지 않는다.',
    ),
]


# ---------------------------------------------------------------------------
# 인라인 표기 (사전 글자에 섞여 있는 `코드` 와 **굵게**)
# ---------------------------------------------------------------------------

_CODE_RE = re.compile(r'`([^`]+)`')
_BOLD_RE = re.compile(r'\*\*(.+?)\*\*')


def inline(text):
    """사전 글자를 HTML 로 — 먼저 통째로 이스케이프한 뒤 `코드`·**굵게** 만 되살린다."""
    if not text:
        return ''
    out = html.escape(str(text))
    out = _CODE_RE.sub(lambda m: f'<code>{m.group(1)}</code>', out)
    out = _BOLD_RE.sub(lambda m: f'<strong>{m.group(1)}</strong>', out)
    return out


def attr(text):
    return html.escape(str(text or ''), quote=True)


# ---------------------------------------------------------------------------
# 사전 읽기
# ---------------------------------------------------------------------------

def load_dictionary(path):
    with open(path, encoding='utf-8') as fp:
        return json.load(fp)


def resolve_screen(screen, data):
    """`ref` 만 있는 참조 줄(검증 배너)을 최상위 키의 정본으로 펼친다.

    참조 줄이 달고 있는 메모는 **싣지 않는다** — 화면 이야기가 아니라 사전 파일을 어떻게
    짜 두었는지의 메모라서(정본이 어느 키에 있는지) 화면을 읽는 사람에게는 군더더기다.
    """
    ref = screen.get('ref')
    if not ref:
        return screen
    target = data.get(ref) or {}
    merged = dict(target)
    merged.update({k: v for k, v in screen.items() if k not in ('ref', 'notes')})
    merged['notes'] = list(target.get('notes') or [])
    merged['blocks'] = target.get('blocks') or []
    merged['buttons'] = target.get('buttons') or []
    merged['cards'] = target.get('cards') or screen.get('cards')
    merged['rules'] = target.get('rules') or []
    return merged


def screen_tab(screen):
    """이 화면이 사는 탭 이름 (편집 화면 탭이 아니면 None)."""
    for line in screen.get('opens') or []:
        found = _TAB_RE.search(line)
        if found:
            return found.group(1)
    return None


def field_rows(screen):
    for block in screen.get('blocks') or []:
        for field in block.get('fields') or []:
            yield block, field


def count_fields(screens):
    return sum(1 for s in screens for _ in field_rows(s))


def skill_version(skill_md=SKILL_MD):
    """SKILL.md 앞머리의 `version:` 한 줄. 없으면 빈 문자열."""
    try:
        text = skill_md.read_text(encoding='utf-8')
    except OSError:
        return ''
    found = re.search(r'^version:\s*([^\s#]+)\s*$', text, re.MULTILINE)
    return found.group(1) if found else ''


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_STYLE_CSS_BODY = """
:root{
  --bg:#ffffff;
  --ink:#16181d;
  --muted:#5d6570;
  --rule:#d8dde4;
  --rule-soft:#eceff3;
  --panel:#f6f8fa;
  --accent:#1f4f8b;
  --code-bg:#f0f2f5;
  --warn:#8a5a00;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#111925;
    --ink:#e8eef6;
    --muted:#9fb0c3;
    --rule:#2c3a4c;
    --rule-soft:#1e2938;
    --panel:#182233;
    --accent:#7fb3e3;
    --code-bg:#1c2736;
    --warn:#f2c868;
  }
}
:root[data-theme="dark"]{
  --bg:#111925;
  --ink:#e8eef6;
  --muted:#9fb0c3;
  --rule:#2c3a4c;
  --rule-soft:#1e2938;
  --panel:#182233;
  --accent:#7fb3e3;
  --code-bg:#1c2736;
  --warn:#f2c868;
}
*{box-sizing:border-box;}
body{
  margin:0;
  background:var(--bg);
  color:var(--ink);
  font-family:"Pretendard","Apple SD Gothic Neo","Noto Sans KR",sans-serif;
  line-height:1.7;
  font-size:17px;
  word-break:keep-all;
  overflow-wrap:anywhere;
}
main{max-width:64rem;margin:0 auto;padding:36px 16px 72px;}
h1{font-size:28px;font-weight:700;margin:0 0 12px;line-height:1.3;}
h2{font-size:22px;font-weight:700;margin:0 0 10px;line-height:1.35;}
h3{font-size:18px;font-weight:700;margin:22px 0 8px;}
h4{font-size:16px;font-weight:700;margin:18px 0 6px;color:var(--muted);}
p{margin:8px 0;}
a{color:var(--accent);}
code{font-family:ui-monospace,"Courier New",Consolas,monospace;font-size:.92em;background:var(--code-bg);padding:1px 5px;border-radius:4px;}
.lede{font-size:18px;margin:0 0 14px;}
.page-head{border-bottom:2px solid var(--rule);padding-bottom:18px;margin-bottom:26px;}
.baseline{margin:0;padding:12px 14px;background:var(--panel);border:1px solid var(--rule);border-radius:8px;}
.baseline dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:2px 12px;font-size:15px;}
.baseline dt{color:var(--muted);white-space:nowrap;}
.baseline dd{margin:0;}
.howto{margin:0 0 30px;}
.howto ol{margin:0;padding:0;list-style:none;counter-reset:howto;}
.howto li{
  counter-increment:howto;
  position:relative;
  margin:0 0 10px;
  padding:10px 14px 10px 44px;
  background:var(--panel);
  border:1px solid var(--rule-soft);
  border-radius:8px;
}
.howto li::before{
  content:counter(howto);
  position:absolute;left:12px;top:10px;
  width:22px;height:22px;line-height:22px;text-align:center;
  border-radius:999px;background:var(--accent);color:var(--bg);
  font-size:13px;font-weight:700;
}
.howto .h-title{font-weight:700;display:block;}
.howto .h-body{display:block;font-size:15px;color:var(--ink);}
.toc{margin:0 0 34px;padding:16px 16px 6px;border:1px solid var(--rule);border-radius:8px;}
.toc h2{font-size:18px;margin:0 0 10px;}
.toc-tab{margin:0 0 10px;}
.toc-tab-name{font-weight:700;font-size:15px;}
.toc-tab ul{margin:2px 0 0;padding:0 0 0 2px;list-style:none;}
.toc-tab li{display:inline;font-size:15px;}
.toc-tab li::after{content:" · ";color:var(--muted);}
.toc-tab li:last-child::after{content:"";}
.toc-empty{color:var(--muted);font-size:14px;}
section.screen{
  margin:0 0 34px;
  padding:18px 0 0;
  border-top:1px solid var(--rule);
}
.screen-no{color:var(--muted);font-weight:400;font-size:16px;}
.tab-badge{
  display:inline-block;margin-left:8px;padding:1px 9px;
  border:1px solid var(--rule);border-radius:999px;
  font-size:13px;font-weight:400;color:var(--muted);vertical-align:middle;
}
.opens{margin:6px 0 10px;font-size:15px;}
.opens .path ~ .path::before{content:" → ";color:var(--muted);}
.opens .k{color:var(--muted);margin-right:4px;}
.cards{font-size:15px;margin:0 0 10px;}
.cards .k{color:var(--muted);margin-right:4px;}
.buttons{font-size:15px;margin:12px 0 0;}
.buttons .k{color:var(--muted);margin-right:4px;}
.btn{display:inline-block;border:1px solid var(--rule);border-radius:5px;padding:0 7px;margin:2px 3px 2px 0;font-size:14px;white-space:nowrap;}
table{width:100%;border-collapse:collapse;font-size:15px;margin:8px 0 4px;}
th,td{border:1px solid var(--rule-soft);padding:7px 9px;vertical-align:top;text-align:left;}
th{background:var(--panel);color:var(--muted);font-weight:700;white-space:nowrap;}
td.c-name{width:20%;}
td.c-kind{width:11%;white-space:nowrap;}
td.c-req{width:6%;text-align:center;}
td.c-opt{width:33%;}
td.c-help{width:30%;}
.fname{font-weight:700;}
.req-yes{font-weight:700;}
.sub{display:block;margin:3px 0 0;font-size:14px;color:var(--muted);}
.opt-list{margin:0;}
.notes{margin:12px 0 0;padding:10px 14px;background:var(--panel);border-left:3px solid var(--rule);border-radius:0 6px 6px 0;}
.notes ul{margin:0;padding-left:18px;font-size:15px;}
.notes li{margin:0 0 5px;}
.notes li:last-child{margin-bottom:0;}
.notes .k{display:block;font-size:13px;color:var(--muted);margin-bottom:5px;}
.rules td.c-sev{white-space:nowrap;width:12%;}
.rules td.c-skip{white-space:nowrap;width:14%;}
.not-covered{margin:34px 0 0;padding:18px 0 0;border-top:2px solid var(--rule);}
.not-covered ul{padding-left:18px;font-size:15px;}
.not-covered li{margin:0 0 5px;}
footer{
  margin:34px 0 0;padding:16px 0 0;border-top:1px solid var(--rule);
  font-size:14px;color:var(--muted);
}
footer code{font-size:13px;}
@media (max-width: 640px){
  body{font-size:16px;}
  main{padding:24px 16px 56px;}
  h1{font-size:24px;}
  h2{font-size:20px;}
  table,thead,tbody,tr,td{display:block;width:auto;}
  table{border:0;margin-bottom:14px;}
  thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;}
  tr{border:1px solid var(--rule);border-radius:8px;padding:6px 2px;margin:0 0 10px;}
  td{border:0;border-bottom:1px solid var(--rule-soft);padding:6px 10px;width:auto !important;text-align:left !important;}
  tr td:last-child{border-bottom:0;}
  td:empty{display:none;}
  td::before{
    content:attr(data-label);
    display:block;font-size:13px;color:var(--muted);margin-bottom:2px;
  }
  .toc-tab li{display:list-item;margin-left:16px;}
  .toc-tab li::after{content:"";}
}
@media print{
  :root{
    --bg:#ffffff; --ink:#000000; --muted:#444444;
    --rule:#999999; --rule-soft:#cccccc; --panel:#ffffff;
    --accent:#000000; --code-bg:#f2f2f2;
  }
  body{font-size:11pt;}
  main{max-width:none;padding:0;}
  a{color:#000;text-decoration:none;}
  section.screen{page-break-before:always;break-before:page;}
  section.screen:first-of-type{page-break-before:auto;break-before:auto;}
  .toc{page-break-after:always;break-after:page;}
  tr,li{page-break-inside:avoid;break-inside:avoid;}
  h1,h2,h3,h4{page-break-after:avoid;break-after:avoid;}
  thead{display:table-header-group;}
  .howto li{break-inside:avoid;}
}
"""


def build_style_css(font_b64):
    """Pretendard 가변 폰트를 base64 로 넣으면 @font-face 를 CSS 맨 앞에 붙인다.
    (`render_card.py` 와 같은 방식 — 바깥으로 나가는 요청이 없는 단일 파일을 만든다.)"""
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


# ---------------------------------------------------------------------------
# 조각 그리기
# ---------------------------------------------------------------------------

def anchor_of(screen):
    return 'screen-' + re.sub(r'[^a-z0-9-]+', '-', str(screen.get('id', '')).lower()).strip('-')


def render_options_cell(field):
    """선택지 / 형식 칸 — 선택지를 콤마로 늘어놓고 그 아래에 형식·열 구성을 붙인다."""
    parts = []
    options = field.get('options') or []
    if options:
        parts.append('<span class="opt-list">' + ', '.join(inline(o) for o in options) + '</span>')

    columns = field.get('columns') or []
    if columns:
        parts.append('<span class="sub">열 — ' + ', '.join(inline(c) for c in columns) + '</span>')
    for group in field.get('column_options') or []:
        parts.append('<span class="sub">열 선택지 — ' + ', '.join(inline(o) for o in group) + '</span>')
    if field.get('columns_note'):
        parts.append(f'<span class="sub">{inline(field["columns_note"])}</span>')

    for group in field.get('checkbox_groups') or []:
        name = inline(group.get('group', ''))
        items = ', '.join(inline(i) for i in group.get('items') or [])
        parts.append(f'<span class="sub"><strong>{name}</strong> — {items}</span>')

    if field.get('options_note'):
        parts.append(f'<span class="sub">{inline(field["options_note"])}</span>')
    if field.get('format'):
        parts.append(f'<span class="sub">{inline(field["format"])}</span>')
    return ''.join(parts)


def render_name_cell(field):
    parts = [f'<span class="fname">{inline(field.get("label", ""))}</span>']
    if field.get('screen_label') and field['screen_label'] != field.get('label'):
        parts.append(f'<span class="sub">화면 글자 — {inline(field["screen_label"])}</span>')
    if field.get('checkbox_text'):
        parts.append(f'<span class="sub">확인란 글자 — {inline(field["checkbox_text"])}</span>')
    if field.get('same_row_as'):
        parts.append(f'<span class="sub">같은 줄 — {inline(field["same_row_as"])}</span>')
    return ''.join(parts)


def render_help_cell(field):
    parts = []
    if field.get('help'):
        parts.append(inline(field['help']))
    if field.get('visible_when'):
        parts.append(f'<span class="sub">보일 때 — {inline(field["visible_when"])}</span>')
    return ''.join(parts)


def render_block(block):
    out = []
    if block.get('name'):
        out.append(f'<h4>블록 <code>{inline(block["name"])}</code></h4>')
    out.append('<table class="fields">')
    out.append(
        '<thead><tr><th>칸</th><th>종류</th><th>필수</th>'
        '<th>선택지 / 형식</th><th>도움말</th></tr></thead>'
    )
    out.append('<tbody>')
    for field in block.get('fields') or []:
        required = '<span class="req-yes">예</span>' if field.get('required') else ''
        out.append('<tr class="field">')
        out.append(f'<td class="c-name" data-label="칸">{render_name_cell(field)}</td>')
        out.append(f'<td class="c-kind" data-label="종류">{inline(field.get("kind", ""))}</td>')
        out.append(f'<td class="c-req" data-label="필수">{required}</td>')
        out.append(f'<td class="c-opt" data-label="선택지 / 형식">{render_options_cell(field)}</td>')
        out.append(f'<td class="c-help" data-label="도움말">{render_help_cell(field)}</td>')
        out.append('</tr>')
    out.append('</tbody></table>')
    return '\n'.join(out)


def render_rules(rules):
    """검증 배너의 규칙 목록 — 표 모양이 다른 유일한 덩어리라 제 표로 그린다."""
    out = ['<h4>배너에 뜨는 문구</h4>', '<table class="rules">']
    out.append('<thead><tr><th>문구</th><th>묶음</th><th>넘어가기</th></tr></thead><tbody>')
    for rule in rules:
        skip = '가능' if rule.get('dismissible') else '불가'
        out.append('<tr>')
        out.append(f'<td data-label="문구">{inline(rule.get("message", ""))}</td>')
        out.append(f'<td class="c-sev" data-label="묶음">{inline(rule.get("severity", ""))}</td>')
        out.append(f'<td class="c-skip" data-label="넘어가기">{skip}</td>')
        out.append('</tr>')
    out.append('</tbody></table>')
    return '\n'.join(out)


def render_screen(no, screen, tab):
    out = [f'<section class="screen" id="{attr(anchor_of(screen))}">']
    badge = f'<span class="tab-badge">{inline(tab)}</span>' if tab else ''
    out.append(
        f'<h2><span class="screen-no">{no}.</span> {inline(screen.get("name", ""))}{badge}</h2>'
    )

    opens = screen.get('opens') or []
    if opens:
        items = ''.join(f'<span class="path">{inline(o)}</span>' for o in opens)
        out.append(f'<p class="opens"><span class="k">여는 길</span>{items}</p>')

    cards = screen.get('cards') or []
    if cards:
        names = ' · '.join(f'<code>{inline(c)}</code>' for c in cards)
        out.append(f'<p class="cards"><span class="k">화면 안 카드</span>{names}</p>')

    for block in screen.get('blocks') or []:
        out.append(render_block(block))

    if screen.get('rules'):
        out.append(render_rules(screen['rules']))

    buttons = screen.get('buttons') or []
    if buttons:
        chips = ''.join(f'<span class="btn">{inline(b)}</span>' for b in buttons)
        out.append(f'<p class="buttons"><span class="k">버튼</span>{chips}</p>')

    notes = screen.get('notes') or []
    if notes:
        items = ''.join(f'<li>{inline(n)}</li>' for n in notes)
        out.append(f'<div class="notes"><span class="k">이 화면의 메모</span><ul>{items}</ul></div>')

    out.append('</section>')
    return '\n'.join(out)


def render_toc(tabs, by_tab, numbers):
    out = ['<nav class="toc">', '<h2>탭별 차례</h2>']
    for tab in list(tabs) + [OUTSIDE_TABS]:
        screens = by_tab.get(tab) or []
        out.append('<div class="toc-tab">')
        out.append(f'<span class="toc-tab-name">{inline(tab)}</span>')
        if screens:
            items = ''.join(
                f'<li><a href="#{attr(anchor_of(s))}">{numbers[s["id"]]}. {inline(s.get("name", ""))}</a></li>'
                for s in screens
            )
            out.append(f'<ul>{items}</ul>')
        else:
            out.append(
                '<p class="toc-empty">이 안내에 담은 칸이 없는 탭이다 — 상품 공통 화면이라 '
                '「이 안내에 없는 것」을 본다.</p>'
            )
        out.append('</div>')
    out.append('</nav>')
    return '\n'.join(out)


def render_howto():
    out = ['<section class="howto">', '<h2>화면 읽는 법</h2>', '<ol>']
    for title, body in HOWTO_ITEMS:
        out.append(
            f'<li><span class="h-title">{inline(title)}</span>'
            f'<span class="h-body">{inline(body)}</span></li>'
        )
    out.append('</ol></section>')
    return '\n'.join(out)


def render_head_block(meta, screen_count, field_count):
    rows = [
        ('화면 기준', meta.get('erp_baseline', '')),
        ('사전 뽑은 날', meta.get('generated_on', '')),
        ('담은 것', f'화면 {screen_count}개 · 입력 칸 {field_count}개'),
    ]
    dl = ''.join(
        f'<dt>{inline(k)}</dt><dd>{inline(v)}</dd>' for k, v in rows if v
    )
    return (
        '<header class="page-head">'
        f'<h1>{inline(PAGE_TITLE)}</h1>'
        '<p class="lede">이 페이지는 화면 사전에서 그대로 만들어진다 — 여기 적힌 ERP 배포판의 화면과 같다.</p>'
        '<p>호텔마다 받는 <strong>입력 지시서</strong>가 어느 칸에 <strong>무엇을</strong> 넣을지를 말하고, '
        '이 페이지는 <strong>화면이 어떻게 움직이는지</strong>를 말한다.</p>'
        f'<div class="baseline"><dl>{dl}</dl></div>'
        '</header>'
    )


def render_not_covered(items):
    if not items:
        return ''
    lis = ''.join(f'<li>{inline(i)}</li>' for i in items)
    return (
        '<section class="not-covered" id="not-covered">'
        '<h2>이 안내에 없는 것</h2>'
        f'<ul>{lis}</ul>'
        '</section>'
    )


def render_footer(version):
    ver = f'<p>스킬 판: <code>stay-setup-guide {inline(version)}</code></p>' if version else ''
    return (
        '<footer>'
        f'{ver}'
        '<p>다시 만드는 명령 (저장소 맨 위에서):</p>'
        f'<p><code>{inline(REGEN_COMMAND)}</code></p>'
        '<p>화면 사전이 바뀌면 이 명령을 다시 돌린다 — 손으로 고치지 않는다.</p>'
        '</footer>'
    )


def stamp_meta(meta, screen_count, field_count):
    value = (
        f'{STAMP_VERSION};screens={screen_count};fields={field_count};'
        f'generated={meta.get("generated_on", "")}'
    )
    return f'<meta name="{STAMP_META_NAME}" content="{attr(value)}">'


# ---------------------------------------------------------------------------
# 한 장으로 조립
# ---------------------------------------------------------------------------

def render_guide(data, font_b64=None, version=''):
    meta = data.get('meta') or {}
    tabs = data.get('tabs') or []
    screens = [resolve_screen(s, data) for s in data.get('screens') or []]

    numbers = {}
    tab_of = {}
    by_tab = {}
    for idx, screen in enumerate(screens, 1):
        numbers[screen['id']] = idx
        tab = screen_tab(screen)
        tab_of[screen['id']] = tab
        by_tab.setdefault(tab or OUTSIDE_TABS, []).append(screen)

    screen_count = len(screens)
    field_count = count_fields(screens)

    body = [
        render_head_block(meta, screen_count, field_count),
        render_howto(),
        render_toc(tabs, by_tab, numbers),
    ]
    for idx, screen in enumerate(screens, 1):
        body.append(render_screen(idx, screen, tab_of[screen['id']]))
    body.append(render_not_covered(data.get('not_covered') or []))
    body.append(render_footer(version))

    page = '\n'.join([
        '<!DOCTYPE html>',
        '<html lang="ko">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{inline(PAGE_TITLE)}</title>',
        stamp_meta(meta, screen_count, field_count),
        '<style>',
        build_style_css(font_b64),
        '</style>',
        '</head>',
        '<body>',
        '<main>',
        '\n'.join(body),
        '</main>',
        '</body>',
        '</html>',
        '',
    ])
    stats = {
        'screens': screen_count,
        'fields': field_count,
        'tabs': len(tabs),
        'meta_screens': meta.get('screen_count'),
        'meta_fields': meta.get('field_count'),
    }
    return page, stats


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='화면 사전(JSON) → 직원용 화면 안내 HTML 한 장.',
    )
    ap.add_argument('--dictionary', default=str(DEFAULT_DICTIONARY),
                    help=f'화면 사전 JSON (기본: {DEFAULT_DICTIONARY.name})')
    ap.add_argument('-o', '--output', default=str(DEFAULT_OUTPUT),
                    help='출력 HTML 경로 (기본: docs/화면-안내.html)')
    ap.add_argument('--font', default=str(DEFAULT_FONT),
                    help='임베드할 Pretendard 가변 woff2 (기본: scripts/fonts/PretendardVariable.woff2)')
    ap.add_argument('--no-font', action='store_true',
                    help='폰트를 넣지 않는다 (시스템 고딕 폴백 · 파일이 작아진다)')
    args = ap.parse_args(argv)

    dict_path = Path(args.dictionary)
    if not dict_path.is_file():
        print(f'화면 사전을 찾을 수 없다: {dict_path}', file=sys.stderr)
        return 1
    data = load_dictionary(dict_path)

    font_b64 = None
    font_note = '넣지 않음 (시스템 고딕 폴백)'
    if not args.no_font:
        font_path = Path(args.font)
        if font_path.is_file():
            font_bytes = font_path.read_bytes()
            font_b64 = base64.b64encode(font_bytes).decode('ascii')
            font_note = f'{font_path.name} {len(font_bytes) / 1024 / 1024:.2f}MB 임베드'
        else:
            print(f'경고: 폰트 파일을 찾을 수 없다: {font_path} (시스템 폰트로 대체)', file=sys.stderr)

    page, stats = render_guide(data, font_b64, skill_version())

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding='utf-8')

    size = len(page.encode('utf-8'))
    print(f'OK: {out_path}')
    print(f'  화면: {stats["screens"]}개 · 입력 칸: {stats["fields"]}개 · 탭: {stats["tabs"]}개')
    print(f'  크기: {size / 1024:.1f} KB ({size:,} bytes)')
    print(f'  폰트: {font_note}')

    mismatch = []
    if stats['meta_screens'] is not None and stats['meta_screens'] != stats['screens']:
        mismatch.append(f'화면 {stats["screens"]} ≠ meta.screen_count {stats["meta_screens"]}')
    if stats['meta_fields'] is not None and stats['meta_fields'] != stats['fields']:
        mismatch.append(f'입력 칸 {stats["fields"]} ≠ meta.field_count {stats["meta_fields"]}')
    if mismatch:
        for line in mismatch:
            print(f'  ⚠ 사전의 머리 숫자와 다르다: {line}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
