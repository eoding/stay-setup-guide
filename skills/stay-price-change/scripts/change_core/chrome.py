"""HTML 페이지 틀 — 파일 하나로 열리고 바깥 주소를 부르지 않는다. 밝은 화면·어두운 화면 둘 다 읽히게 색을 둔다.

종류마다 다른 표(가격 칸의 날짜 표 등)는 각 도우미가 그리고, 여기에는 모든 도우미가 같은 모양으로 쓰는 조각을 둔다:
머리 숫자, 저장 단계 목록, 적용 결과 띠, 멈췄을 때 선택지, 되돌리기 머리 띠, 그대로 두는 항목 표.

멈춘 변경의 결과 페이지는 멈춘 뒤 마지막 check(장부의 `checks` — ChangeRecord.checked)가 본 것대로 말한다(stop_mode): check 가
없으면 이어서 할 수 있는지는 다시 읽어 봐야 안다고, 이어서 해도 된다고 했으면 그렇다고, 안 된다고 했으면 까닭(`why`)과 함께 이어서를
빼고. 저장한 칸을 뒤에 되돌린 변경은 이어서 하지 않는다.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Iterable, Mapping

from .money import scale_of
from .rollback import RollbackPlan

CSS = """
:root { --bg:#f6f4ef; --paper:#fffdf8; --ink:#22201c; --soft:#6b655b; --line:#e2dccf; --pick:#1f6f5c; --pick-bg:#e6f3ee;
        --red:#b3261e; --red-bg:#fbe9e7; --amber:#8a5a00; --amber-bg:#fdf1d6; --blue:#1d4f91; --blue-bg:#e5eefa; --cell:#f0ece2; }
@media (prefers-color-scheme: dark) { :root { --bg:#191815; --paper:#23211d; --ink:#efeade; --soft:#a79f90; --line:#3a362f;
        --pick:#6fcdb3; --pick-bg:#1d3a33; --red:#ff9a8f; --red-bg:#46211e; --amber:#f2c264; --amber-bg:#3d2f12;
        --blue:#9cc0f5; --blue-bg:#1c2c44; --cell:#2e2b26; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font:16px/1.65 "Pretendard","Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif; }
main { max-width: 1180px; margin: 0 auto; padding: 28px 22px 80px; }
h1 { font-size: 24px; margin: 0 0 6px; letter-spacing:-0.02em; }
h2 { font-size: 19px; margin: 26px 0 8px; }
h3 { font-size: 16px; margin: 18px 0 6px; }
.sub { color: var(--soft); font-size: 14px; margin: 2px 0; }
.frame { background: var(--paper); border:1px solid var(--line); border-radius: 14px; padding: 16px 20px; margin: 12px 0; }
dl.kv { display:grid; grid-template-columns: 110px 1fr; gap: 4px 14px; margin: 8px 0; }
dl.kv dt { color: var(--soft); } dl.kv dd { margin:0; font-weight:600; }
.banner { border-radius: 10px; padding: 12px 16px; margin: 10px 0; border-left: 5px solid; }
.banner.red { background: var(--red-bg); border-color: var(--red); }
.banner.amber { background: var(--amber-bg); border-color: var(--amber); }
.banner.ok { background: var(--pick-bg); border-color: var(--pick); }
.banner.blue { background: var(--blue-bg); border-color: var(--blue); }
.stat { display:flex; flex-wrap:wrap; gap:10px; margin: 12px 0; }
.stat div { border:1px solid var(--line); border-radius: 10px; padding: 8px 14px; background: var(--paper); }
.stat b { display:block; font-size: 22px; line-height:1.2; }
.stat span { font-size: 13px; color: var(--soft); }
.scroll { overflow-x:auto; }
table { border-collapse: collapse; width:100%; font-size: 14px; margin: 6px 0 14px; }
th, td { border:1px solid var(--line); padding: 5px 8px; text-align: right; white-space: nowrap; vertical-align: top; }
th { background: var(--cell); font-weight:600; text-align:center; }
th.days { white-space: normal; min-width: 8em; max-width: 18em; }
td:first-child, th:first-child, td.text { text-align:left; }
td.text { white-space: normal; }
.was { color: var(--soft); } .now { font-weight: 700; } .arrow { color: var(--soft); padding: 0 3px; }
td.red { background: var(--red-bg); } td.blocked { background: var(--amber-bg); } td.new { background: var(--blue-bg); }
td.chosen { background: var(--pick-bg); }
td.wait { outline: 2px dashed var(--amber); outline-offset: -3px; }
td.none, td.same { color: var(--soft); text-align:center; }
small.more { display:block; color: var(--soft); font-size: 12px; }
.tag { display:inline-block; font-size: 11.5px; font-weight:700; padding: 0 7px; border-radius: 99px; margin-left: 4px;
       vertical-align: 1px; white-space: nowrap; }
.tag.res { background: var(--blue-bg); color: var(--blue); } .tag.closed { background: var(--cell); color: var(--soft); }
.tag.red { background: var(--red); color: var(--paper); } .tag.blocked { background: var(--amber); color: var(--paper); }
.tag.ok { background: var(--pick); color: var(--paper); } .tag.new { background: var(--blue); color: var(--paper); }
.tag.chosen { background: var(--paper); color: var(--pick); border: 1px solid var(--pick); }
.tag.wait { background: var(--amber-bg); color: var(--amber); border: 1px solid var(--amber); }
.steps { list-style:none; padding:0; margin: 8px 0; }
.steps li { display:grid; grid-template-columns: 26px 1fr auto; gap: 8px; padding: 7px 10px; border-bottom:1px solid var(--line); }
.steps .ok { color: var(--pick); font-weight:700; } .steps .fail { color: var(--red); font-weight:700; }
.steps .wait { color: var(--soft); }
.choices { display:grid; gap: 8px; margin: 10px 0; }
.choices div { border:1px solid var(--line); border-radius: 10px; padding: 9px 14px; background: var(--paper); }
ul.notes { padding-left: 20px; } ul.notes li { margin: 3px 0; }
code { background: var(--cell); padding: 1px 6px; border-radius: 5px; font-size: .92em; word-break: break-all; }
footer { margin-top: 30px; color: var(--soft); font-size: 13px; }
"""


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def fmt_clock(text: str, today: date | None = None) -> str:
    """「17시 26분」 — 담당자에게 시각을 말하는 꼴(SKILL.md 의 「○시 ○분」). `today` 를 주었는데 그 시각이 그날이 아니면 날짜를
    앞에 붙인다 — 「11월 21일 17시 26분」(해가 다르면 「2026년 11월 21일 17시 26분」)."""
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    clock = f"{moment.hour}시 {moment.minute}분"
    if today is None or moment.date() == today:
        return clock
    day = f"{moment.month}월 {moment.day}일"
    return f"{day} {clock}" if moment.year == today.year else f"{moment.year}년 {day} {clock}"


def fmt_money(value, currency: str) -> str:
    if value is None:
        return "없음"
    return f"{value:,.{scale_of(currency)}f}"


def fmt_time(text: str | None) -> str:
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text


def page(title: str, body: str, maker: str = "어딩 Stay 도우미") -> str:
    return (f'<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<meta name="color-scheme" content="light dark">\n<title>{esc(title)}</title>\n<style>{CSS}</style>\n'
            f'</head>\n<body>\n<main>\n{body}\n<footer>{esc(maker)}가 만든 페이지입니다.</footer>\n'
            f'</main>\n</body>\n</html>\n')


class _Text(HTMLParser):
    """페이지에 보이는 글 — 머리 · 문단 · 띠 · 표의 줄마다 한 줄, 표의 칸은 ` | ` 로 잇는다. 스타일 · 스크립트는 뺀다."""
    BREAKS = {"h1", "h2", "h3", "p", "div", "tr", "li", "dt", "dd", "br", "table", "ul"}
    CELLS = {"td", "th"}

    def __init__(self):
        super().__init__()
        self.lines, self.line, self.skip, self.cells = [], [], 0, 0

    def flush(self):
        text = " ".join(" ".join(self.line).split())
        if text:
            self.lines.append(text)
        self.line, self.cells = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "title"):          # 제목은 머리(h1)가 다시 말한다 — 한 번만
            self.skip += 1
        elif tag in self.BREAKS:
            self.flush()
        elif tag in self.CELLS:
            if self.cells:
                self.line.append("|")
            self.cells += 1

    def handle_endtag(self, tag):
        if tag in ("style", "script", "title"):
            self.skip -= 1
        elif tag in self.BREAKS:
            self.flush()

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.line.append(data.strip())


def page_text(page_html: str) -> str:
    """페이지 HTML → 담당자가 화면에서 읽는 글(줄마다). 도우미가 페이지의 글을 그대로 옮겨야 할 때 쓴다(render --text)."""
    reader = _Text()
    reader.feed(page_html)
    reader.flush()
    return "\n".join(reader.lines)


def times_word(count: int) -> str:
    """저장 횟수를 말하는 글 — 하나면 「한 번」(「1번」은 장부 번호처럼 읽히고, 「1번 나눠」는 말이 되지 않는다), 아니면 「N번」."""
    return "한 번" if count == 1 else f"{count:,}번"


def stats(items: Iterable[tuple[int, str]]) -> str:
    return '<div class="stat">' + "".join(f"<div><b>{number:,}</b><span>{esc(label)}</span></div>"
                                          for number, label in items) + "</div>"


def notes(lines: Iterable[str]) -> str:
    return '<ul class="notes">' + "".join(f"<li>{esc(line)}</li>" for line in lines) + "</ul>"


def steps_list(steps, sizes: Mapping[int, int] | None = None, unit: str = "칸") -> str:
    """저장 단계 목록 — 장부의 StepRecord 들(번호 · 이름 · 됐는지). `sizes` 는 단계마다 그 저장이 쓰는 항목 수."""
    if not steps:
        return ""
    marks = {"saved": ('<span class="ok">✓</span>', '<span class="sub">저장함</span>'),
             "unknown": ('<span class="fail">?</span>', '<span class="fail">저장됐는지 모름 · 다시 읽어 가립니다</span>'),
             "failed": ('<span class="fail">✕</span>', '<span class="fail">여기서 멈춤 · 바뀌지 않음</span>')}
    items = []
    for step in steps:
        state = "unknown" if step.status == "failed" and step.unknown else step.status
        mark, text = marks.get(state, ('<span class="wait">–</span>', '<span class="wait">아직 안 함</span>'))
        size = f" · {sizes[step.index]:,}{unit}" if sizes and step.index in sizes else ""
        items.append(f"<li>{mark}<span>{step.index}. {esc(step.label)}{size}</span>{text}</li>")
    return '<h2>저장 단계</h2><ul class="steps">' + "".join(items) + "</ul>"


MOVED_ERRORS = ("ERP 화면의 값이 읽은 값과 다릅니다", "창의 값이 읽은 값과 다릅니다")   # 페이지가 누르기 전에 화면이 읽은 값과 달라 거절한 답의 머리(stay_price.js)
MOVED_NOTE = "미리보기 뒤에 ERP 에서 그 저장의 {what} 바뀌어 아무것도 넣지 않았습니다"
MOVED_COUNT = re.compile(re.escape(MOVED_ERRORS[0]) + r"\((\d+)칸\)")   # 묶음 저장의 거절은 칸 수를 댄다 — 창 하나의 거절은 그 하나다


def plain_note(note: str | None) -> str | None:
    """저장 메모를 담당자가 읽을 말로 — 그 사이 화면이 바뀌어 페이지가 거절한 답(인원 조합 키 · 「읽은 값 … 화면 …」이 든 글)은 쉬운 한
    문장으로 바꾼다(묶음 저장이면 바뀐 칸 수와 함께 — 도우미가 하는 말과 같다, stopped.md 2). 장부에는 페이지의 글 그대로 남는다(기록)."""
    if not (note and note.startswith(MOVED_ERRORS)):
        return note
    count = MOVED_COUNT.match(note)
    return MOVED_NOTE.format(what=f"칸 {count.group(1)}개가" if count else "값이")


def stop_view(record):
    """멈춘 변경을 보일 때의 `(멈춘 까닭, 멈춘 뒤의 check 또는 None)`. 멈췄거나, 멈췄다가 다시 읽은 check 가 이어서 해도 된다고 해
    적용 중인 변경이다(장부는 그 check 를 적용 중으로 돌려놓지만 담당자는 아직 고르지 않았다). 아니면 None."""
    if record.status == "stopped":
        return record.cause, getattr(record, "checked", None)
    checked = getattr(record, "checked", None)
    if record.status == "applying" and checked is not None and checked.cause:
        return checked.cause, checked
    return None


def _alive(record) -> bool:
    """이 변경이 넣고 아직 되돌리지 않은 값이 ERP 에 있는가."""
    return any(row.written and row.action and row.rolled_back_by is None for row in record.rows)


def stop_mode(record) -> str | None:
    """멈춘 변경의 결과 페이지가 어느 말을 하는지 — `undone` 저장한 칸을 뒤에 되돌렸다(이어서 하지 않는다) · `unchecked` 멈춘 뒤에
    check 가 없다(이어서 할 수 있는지는 다시 읽어 봐야 안다) · `allows` check 가 이어서 해도 된다고 했다 · `forbids` 안 된다고 했다.
    멈춘 변경이 아니면 None."""
    stop = stop_view(record)
    if stop is None:
        return None
    if any(row.rolled_back_by for row in record.rows):
        return "undone"
    checked = stop[1]
    return "unchecked" if checked is None else "allows" if checked.can_continue else "forbids"


def nothing_left(record) -> bool:
    """멈춘 변경인데 ERP 에 이 변경의 값이 하나도 남아 있지 않다 — 하나도 저장하지 않았거나 저장한 것을 모두 되돌렸다. 결과
    페이지는 손님 화면 · 되돌리는 법을 말하지 않는다."""
    return stop_view(record) is not None and not _alive(record)


def checked_when(record) -> str:
    """멈춘 뒤 마지막 check 가 ERP 를 다시 읽은 때 — 「19시 26분」. 장부를 읽은 날(`record.as_of` — 이 페이지를 만든 때)이 그날이
    아니면 날짜까지 붙인다 — 뒷날 다시 연 페이지가 그때 읽은 값을 오늘 읽은 것처럼 말하지 않는다."""
    today = datetime.fromisoformat(record.as_of).date() if record.as_of else None
    return fmt_clock(stop_view(record)[1].read_at, today)


def reread(record) -> str:
    """check 가 다시 읽은 값 앞에 붙이는 말 — 「19시 26분에 다시 읽으니」. 그 값은 그때 ERP 에 있던 값이라 「지금」이라고 하지 않는다
    (그 뒤에 또 바뀌었을 수 있다 — 시운전 8 에서 그 사이 값이 되돌려졌다)."""
    return f"{checked_when(record)}에 다시 읽으니"


def moved_sentence(record, count: int, unit: str = "칸") -> str:
    """멈춘 뒤 다시 읽어 보니 남은 저장의 항목이 미리보기 때와 달라진 것 — 그 수를 대고, 그 사이 ERP 에서 바뀌었고, 표의 다시 읽은
    값은 그때 ERP 에 있던 값이라 그 뒤에 또 바뀌었을 수 있고, 도우미는 아무것도 넣지 않았다는 문장. 표에서는 그 항목이 「미리보기 때
    … · ○시 ○분에 다시 읽으니 …」와 「그 사이 ERP 에서 바뀜 · 넣지 않음」이다."""
    return (f"「그 사이 ERP 에서 바뀜」 {count:,}{unit}은 미리보기 뒤에 ERP 에서 값이 바뀐 {unit}입니다. {unit}에는 미리보기 때 값과 "
            f"{checked_when(record)}에 다시 읽은 값을 보입니다 — 다시 읽은 값은 그때 ERP 에 있던 값이고, 그 뒤에 또 바뀌었을 수 "
            f"있습니다. 도우미는 이 {unit}에 아무것도 넣지 않았습니다.")


MOVED_TAG = '<span class="tag red">그 사이 ERP 에서 바뀜 · 넣지 않음</span>'


def _stop_banner(record, cause: str | None) -> str:
    """멈춘 변경의 머리 띠 — 어디서 왜 멈췄고 지금 ERP 에 이 변경이 얼마나 남았는지."""
    done = sum(step.status == "saved" for step in record.steps)
    waiting = next((step for step in record.steps if step.status != "saved"), None)
    at = waiting.index if waiting else len(record.steps)
    now = ("지금은 일부만 바뀐 상태입니다." if _alive(record) else "저장한 것은 뒤에 모두 되돌렸습니다." if done
           else "아무것도 바뀌지 않았습니다.")
    if cause == "cut_off":
        if not done:
            return '<div class="banner red"><b>첫 저장 전에 끊겼습니다.</b> 저장이 실패한 것은 아니고, 아무것도 바뀌지 않았습니다.</div>'
        return (f'<div class="banner red"><b>{at}번째 저장 앞에서 끊겼습니다.</b> 저장이 실패한 것은 아니고, '
                f'{done}번째 저장까지 됐습니다. {now}</div>')
    failed = next((step for step in record.steps if step.status == "failed"), None)
    if failed is None:   # 「모름」이던 저장을 다시 읽어 저장된 것으로 가렸다
        return (f'<div class="banner red"><b>{at}번째 저장 앞에서 멈췄습니다.</b> 저장됐는지 모르던 저장은 다시 읽어 저장된 것을 '
                f'확인했습니다. {now}</div>')
    note = plain_note(failed.note)
    why = f"({esc(note.rstrip('.'))})" if note else ""
    return f'<div class="banner red"><b>{failed.index}번째 저장에서 멈췄습니다</b>{why}. {now}</div>'


def result_word(record, undoes: bool) -> str:
    """결과 페이지의 이름(제목과 파일 이름) — 「적용 결과」 · 되돌리기(`undoes`)면 「되돌리기 결과」. 멈춘 변경(stop_view)이면
    「적용하다 멈춤」 · 「되돌리다 멈춤」이다 — 기록 폴더의 파일 목록이 다 적용한 것처럼 읽히지 않게."""
    if stop_view(record) is not None:
        return "되돌리다 멈춤" if undoes else "적용하다 멈춤"
    return "되돌리기 결과" if undoes else "적용 결과"


def result_banner(record, written: int, mismatched: int, unit: str = "칸") -> str:
    """적용 결과 머리 띠 — 장부의 ChangeRecord 상태와 다시 읽어 맞았는지로 정한다."""
    done = sum(step.status == "saved" for step in record.steps)
    stop = stop_view(record)
    if stop is not None:
        return _stop_banner(record, stop[0])
    if record.status == "applied" and record.verified_at and not mismatched:
        return (f'<div class="banner ok"><b>적용했고, 다시 읽어 확인했습니다.</b> {written:,}{unit} 모두 넣은 값과 같습니다.</div>')
    if record.status == "applied" and mismatched:
        return (f'<div class="banner red"><b>적용했지만, 다시 읽었더니 {mismatched:,}{unit}이 넣은 값과 다릅니다.</b> '
                "아래 표에서 빨간 곳을 확인해 주세요.</div>")
    if record.status == "applied":
        return '<div class="banner amber"><b>적용했습니다.</b> 아직 다시 읽어 확인하지 않았습니다.</div>'
    if record.status == "applying":
        return f'<div class="banner amber"><b>적용하는 중입니다.</b> {done}/{len(record.steps)}번 저장했습니다.</div>'
    if record.status == "empty":
        return '<div class="banner blue"><b>저장할 것이 없는 미리보기였습니다.</b> 아무것도 바뀌지 않았습니다.</div>'
    return '<div class="banner blue"><b>아직 적용하지 않았습니다.</b></div>'


def names_banner(names: Iterable[str]) -> str:
    """이름 · 설명에 바꾸기 전 값이 적힌 항목(change_core.names 의 문장들) — 알림이다(고를 것이 아니다). 없으면 빈 글자."""
    names = list(names)
    if not names:
        return ""
    return ('<div class="banner blue"><b>이름 · 설명에 바꾸기 전 값이 적혀 있습니다.</b>'
            + "".join(f"<br>{esc(sentence)}" for sentence in names) + "</div>")


def stopped_choices(record, waiting: int | None = None, unit: str = "칸") -> str:
    """멈춘 변경의 선택지 — stopped.md 2 · 3 과 같은 것만(stop_mode). `waiting` 은 남은 저장이 쓰는 항목 수(표에 「아직 저장 안 함」으로
    보이는 것). 「크롬에서 ERP 로그인을 확인한 뒤」는 로그인이 풀린 것일 수 있을 때만 — 저장됐는지 몰랐거나 페이지가 로그인을 말했을 때."""
    mode = stop_mode(record)
    if mode is None:
        return ""
    cause, checked = stop_view(record)
    done = sum(step.status == "saved" for step in record.steps)
    left = len(record.steps) - done
    failed = next((step for step in record.steps if step.status == "failed"), None)
    login = cause == "unknown" or (failed is not None and "로그인" in (failed.note or ""))
    alive = _alive(record)
    if mode == "undone" and not alive:
        return (f'<div class="banner blue">이 변경이 저장한 {unit}은 뒤에 모두 되돌렸습니다. 이어서 할 것도 되돌릴 것도 없습니다. '
                "남은 부분을 바꾸려면 새로 말씀해 주세요.</div>")
    back = ""
    if alive:
        what = "이미 된 저장 가운데 아직 되돌리지 않은 것" if mode == "undone" else f"이미 된 저장 {times_word(done)}"
        back = f'<div><b>된 것까지 되돌리기</b> — {what}을 원래 값으로 되돌립니다(미리보기를 먼저 보여 드립니다).</div>'
    shown = f"(아래 표의 「아직 저장 안 함」 {waiting:,}{unit}이 그 값으로 바뀝니다)" if waiting else ""
    stay = '<div><b>이대로 두기</b> — 장부에 "중간에 멈춤"으로 남습니다.'
    why = ""
    if mode == "undone":
        lead = "이 변경은 저장한 것 가운데 일부를 뒤에 되돌렸습니다 — 이어서 하지 않습니다."
        offered = back + stay + " 남은 부분을 바꾸려면 새로 말씀해 주세요.</div>"
    elif mode == "unchecked":
        lead = "이어서 할 수 있는지는 ERP 를 다시 읽어 봐야 압니다 — 그 사이 바뀐 칸이 있으면 이어서 하지 않습니다."
        offered = (f"<div><b>이어서</b> — 남은 저장 {times_word(left)}을 마저 적용합니다{shown}. 다시 읽어 그 사이 바뀐 칸이 없을 때만 "
                   f"합니다.</div>{back}{stay}</div>")
    elif mode == "allows":
        lead = (f"{checked_when(record)}에 ERP 를 다시 읽어 보니 남은 저장의 {unit}이 미리보기 때와 같았습니다 — 이어서 할 수 "
                "있습니다.")
        offered = (f"<div><b>이어서</b> — 남은 저장 {times_word(left)}을 마저 적용합니다{shown}.</div>{back}{stay} 나중에 이어서 하려면 "
                   "다시 읽어 확인합니다.</div>")
    else:
        lead = f"{checked_when(record)}에 ERP 를 다시 읽어 보니 이어서 할 수 없습니다."
        why = notes(checked.why)
        offered = back + stay + " 남은 부분은 지금 값으로 새로 바꿔야 합니다(새 미리보기부터).</div>"
    ask = "크롬에서 ERP 로그인을 확인한 뒤 대화창에서 골라 주세요." if login else "대화창에서 골라 주세요."
    return (f'<h2>어떻게 할까요?</h2><p>{esc(lead)}</p>{why}<p>{ask}</p><div class="choices">{offered}</div>')


def rollback_head(plan: RollbackPlan, scope: str = "") -> str:
    if plan.mode == "restore":
        head = (f"<b>{esc(fmt_time(plan.restore_to))} 에 저장해 둔 상태로 되돌립니다.</b><br>"
                f"저장할 때 하신 말: “{esc(plan.original_sentence)}” (장부 {plan.reverses}번)")
    else:
        applied = f"{fmt_time(plan.original_applied_at)} 적용" if plan.original_applied_at else "중간에 멈춘 변경"
        head = (f"<b>{esc(fmt_time(plan.restore_to))} 에 적어 둔 값으로 되돌립니다.</b><br>"
                f"그때 한 일: “{esc(plan.original_sentence)}” ({esc(applied)}, 장부 {plan.reverses}번)")
    return (f'<p class="sub"><b>아직 아무것도 바뀌지 않았습니다.</b> 지금 값은 {esc(fmt_time(plan.read_at))} 에 ERP 에서 읽은 '
            f"것입니다. 통화 {esc(plan.currency)}.</p>"
            f'<div class="banner blue">{head}{f"<br>되돌리는 범위: {esc(scope)}" if scope else ""}</div>')


def _values(values: Mapping, field_labels: Mapping[str, str], currency: str, empty: str) -> str:
    parts = [f"{esc(field_labels.get(name, name))} {empty if value is None else fmt_money(value, currency)}"
             for name, value in values.items()]
    return "<br>".join(parts)


def kept_table(plan: RollbackPlan, field_labels: Mapping[str, str]) -> str:
    """그대로 두는 항목 — 적어 둔 값 · 도우미가 넣은 값 · 지금 값과 까닭. 지금 저장하면 안 되는 항목(`cause.why`)은 같이 되돌리라고 해도
    넣지 않으므로 따로 표 하나다."""
    stays = [item for item in plan.kept if item.cause.why]
    changed = [item for item in plan.kept if not item.cause.why]
    heading = ("그 사이 값이 달라졌지만 말씀대로 같이 되돌리는 것" if plan.include_kept
               else "그대로 두는 것 — 그 사이 값이 달라졌습니다")
    return (_kept_rows(plan, changed, field_labels, heading)
            + _kept_rows(plan, stays, field_labels, "그대로 두는 것 — 지금 저장하면 안 됩니다(같이 되돌리라고 하셔도 넣지 않습니다)"))


def _kept_rows(plan: RollbackPlan, items, field_labels: Mapping[str, str], heading: str) -> str:
    if not items:
        return ""
    currency = plan.currency
    rows = []
    for item in items:
        if item.cause.why:
            why = esc(item.cause.why)
        elif item.cause.outside:
            why = '도우미 밖에서 바뀜 <span class="sub">(ERP 에서 직접 고친 것으로 보임)</span>'
        else:
            why = (f'이 컴퓨터의 다른 변경 <span class="sub">({esc(fmt_time(item.cause.at))} '
                   f'“{esc(item.cause.sentence)}”, 장부 {item.cause.change_id}번)</span>')
        now = {name: item.now.fields.get(name) for name in item.written}
        now_html = "없음" if item.now.state == "missing" else _values(now, field_labels, currency, "비어 있음")
        rows.append(f'<tr><td class="text">{esc(item.label)}</td>'
                    f'<td>{_values(item.recorded, field_labels, currency, "없음")}</td>'
                    f'<td>{_values(item.written, field_labels, currency, "비움")}</td>'
                    f'<td class="red"><b>{now_html}</b></td><td class="text">{why}</td></tr>')
    return (f'<h2>{esc(heading)}</h2><div class="scroll"><table><tr><th>무엇</th>'
            f'<th>적어 둔 값<br><span class="sub">{esc(fmt_time(plan.restore_to))}</span></th>'
            f'<th>도우미가 넣은 값<br><span class="sub">{esc(fmt_time(plan.original_applied_at))}</span></th>'
            f'<th>지금 값</th><th>왜</th></tr>{"".join(rows)}</table></div>')


def unremovable_table(plan: RollbackPlan, field_labels: Mapping[str, str], unit: str = "칸") -> str:
    """지울 수 없는 것 — 되돌리면 없어야 하지만 ERP 에 지우는 길이 없어 지금 값 그대로 남는 것."""
    if not plan.unremovable:
        return ""
    why = ("저장해 둔 때에는 없었고 그 뒤에 생겼습니다" if plan.mode == "restore"
           else "이 변경으로 새로 생겼습니다")
    rows = "".join(f'<tr><td class="text">{esc(item.label)}</td>'
                   f'<td>{_values(item.now.fields, field_labels, plan.currency, "없음")}</td>'
                   f'<td class="text">{esc(why)}</td></tr>' for item in plan.unremovable)
    return (f'<h2>지울 수 없는 {esc(unit)} — ERP 에 지우는 길이 없어 지금 값 그대로 남습니다</h2>'
            f'<div class="scroll"><table><tr><th>무엇</th><th>지금 값</th><th>왜</th></tr>{rows}</table></div>')


def chosen_groups(rows) -> list[tuple[str, str, str | None, tuple[str, ...]]]:
    """장부의 줄(필드마다 하나 — RowRecord)에서 고른 빨간 줄마다 `(판정, 고른 것, 고르며 한 말, 그 항목 키들)`. 같은 판정 · 고름 ·
    말이면 한 묶음이다(처음 나온 차례)."""
    groups: dict[tuple, dict[str, None]] = {}
    for row in rows:
        if row.choice:
            groups.setdefault((row.verdict, row.choice, row.said), {})[row.item_key] = None
    return [(verdict, choice, said, tuple(keys)) for (verdict, choice, said), keys in groups.items()]


def chosen_table(entries: Iterable[tuple[str, str, int, str | None]], unit: str = "칸") -> str:
    """고르신 빨간 줄 — 줄마다 `(빨간 줄 이름, 고르신 것, 그 수, 고르실 때 하신 말)`. 고른 것이 없으면 빈 글자."""
    rows = "".join(f'<tr><td class="text">{esc(rule)}</td><td class="text">{esc(choice)}</td><td>{count:,}</td>'
                   f'<td class="text">{f"“{esc(said)}”" if said else "—"}</td></tr>' for rule, choice, count, said in entries)
    if not rows:
        return ""
    return (f'<h2>고르신 빨간 줄</h2><div class="scroll"><table><tr><th>빨간 줄</th><th>고르신 것</th><th>{esc(unit)} 수</th>'
            f'<th>고르실 때 하신 말</th></tr>{rows}</table></div>')


ROLLBACK_NOTE = ("이 되돌리기도 장부에 적힙니다. 되돌리기는 다시 되돌리지 않습니다 — 되돌린 값으로 다시 바꾸려면 같은 내용으로 새로 "
                 "바꿔 달라고 하세요.")
UNDO_ONCE = ("이 되돌리기는 다시 되돌리지 않습니다. 되돌린 값으로 다시 바꾸려면 같은 내용으로 새로 바꿔 달라고 하세요.")   # 되돌리기 · 저장 상태로 되돌리기의 결과 페이지 끝(세 도우미)


def rollback_ask(plan: RollbackPlan, kind_notes: Iterable[str], unit: str = "칸") -> str:
    """되돌리기 미리보기의 끝 — 무엇을 말하면 되돌리는지와 알릴 것. `kind_notes` 는 종류마다 되돌려도 그대로인 것(예약 금액 ·
    판매 마감 · 값의 출처 표시 …), 그 뒤에 모든 종류에 같은 한 줄(ROLLBACK_NOTE)이 붙는다."""
    ask = (f'"되돌려"라고 하시면 {len(plan.restored):,}{unit}을 되돌립니다.' if plan.restored else
           f"되돌릴 {unit}이 없어 되돌릴 것이 없습니다. 아무것도 바뀌지 않았습니다.")   # 0{unit}을 되돌리자고 청하지 않는다
    changed = [item for item in plan.kept if not item.cause.why]
    stays = len(plan.kept) - len(changed)
    if changed and not plan.include_kept:
        ask += (f' 그 사이 달라진 {len(changed):,}{unit}도 되돌리려면 "{len(changed):,}{unit}도 포함해서 되돌려"라고 '
                "해 주세요.")
    if stays:
        ask += f" 지금 저장하면 안 되는 {stays:,}{unit}은 그대로 둡니다(까닭은 위 표)."
    if plan.unremovable:
        ask += f" 지울 수 없는 {len(plan.unremovable):,}{unit}은 그대로 남습니다."
    return f'<div class="banner blue">{esc(ask)}</div>' + notes([*kind_notes, ROLLBACK_NOTE])
