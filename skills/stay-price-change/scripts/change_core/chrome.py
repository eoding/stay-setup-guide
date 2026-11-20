"""HTML 페이지 틀 — 파일 하나로 열리고 바깥 주소를 부르지 않는다. 밝은 화면·어두운 화면 둘 다 읽히게 색을 둔다.

종류마다 다른 표(가격 칸의 날짜 표 등)는 각 도우미가 그리고, 여기에는 모든 도우미가 같은 모양으로 쓰는 조각을 둔다:
머리 숫자, 저장 단계 목록, 적용 결과 띠, 멈췄을 때 선택지, 되돌리기 머리 띠, 그대로 두는 항목 표.
"""

from __future__ import annotations

import html
from datetime import datetime
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
td.none, td.same { color: var(--soft); text-align:center; }
small.more { display:block; color: var(--soft); font-size: 12px; }
.tag { display:inline-block; font-size: 11.5px; font-weight:700; padding: 0 7px; border-radius: 99px; margin-left: 4px;
       vertical-align: 1px; white-space: nowrap; }
.tag.res { background: var(--blue-bg); color: var(--blue); } .tag.closed { background: var(--cell); color: var(--soft); }
.tag.red { background: var(--red); color: var(--paper); } .tag.blocked { background: var(--amber); color: var(--paper); }
.tag.ok { background: var(--pick); color: var(--paper); } .tag.new { background: var(--blue); color: var(--paper); }
.tag.chosen { background: var(--paper); color: var(--pick); border: 1px solid var(--pick); }
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
        if tag in ("style", "script"):
            self.skip += 1
        elif tag in self.BREAKS:
            self.flush()
        elif tag in self.CELLS:
            if self.cells:
                self.line.append("|")
            self.cells += 1

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
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


def stats(items: Iterable[tuple[int, str]]) -> str:
    return '<div class="stat">' + "".join(f"<div><b>{number:,}</b><span>{esc(label)}</span></div>"
                                          for number, label in items) + "</div>"


def notes(lines: Iterable[str]) -> str:
    return '<ul class="notes">' + "".join(f"<li>{esc(line)}</li>" for line in lines) + "</ul>"


def steps_list(steps) -> str:
    """저장 단계 목록 — 장부의 StepRecord 들(번호 · 이름 · 상태)."""
    if not steps:
        return ""
    marks = {"saved": ('<span class="ok">✓</span>', '<span class="sub">저장함</span>'),
             "failed": ('<span class="fail">✕</span>', '<span class="fail">여기서 멈춤 · 바뀌지 않음</span>')}
    items = []
    for step in steps:
        mark, text = marks.get(step.status, ('<span class="wait">–</span>', '<span class="wait">아직 안 함</span>'))
        items.append(f"<li>{mark}<span>{step.index}. {esc(step.label)}</span>{text}</li>")
    return '<h2>저장 단계</h2><ul class="steps">' + "".join(items) + "</ul>"


def result_banner(record, written: int, mismatched: int, unit: str = "칸") -> str:
    """적용 결과 머리 띠 — 장부의 ChangeRecord 상태와 다시 읽어 맞았는지로 정한다."""
    failed = next((step for step in record.steps if step.status == "failed"), None)
    done = sum(step.status == "saved" for step in record.steps)
    if record.status == "stopped" and record.cause == "cut_off":
        waiting = next((step for step in record.steps if step.status != "saved"), None)
        if not done:
            return ('<div class="banner red"><b>첫 저장 전에 끊겼습니다.</b> 저장이 실패한 것은 아니고, 아무것도 바뀌지 않았습니다. '
                    '이어서 하려면 다시 읽어 확인합니다.</div>')
        return (f'<div class="banner red"><b>{waiting.index}번째 저장 앞에서 끊겼습니다.</b> 저장이 실패한 것은 아니고, '
                f'{done}번째 저장까지 됐습니다. 지금은 일부만 바뀐 상태입니다. 이어서 하려면 다시 읽어 확인합니다.</div>')
    if record.status == "stopped" and failed is not None:
        return (f'<div class="banner red"><b>{failed.index}번째 저장에서 멈췄습니다.</b> 지금은 일부만 바뀐 상태입니다.'
                f'{f" ({esc(failed.note)})" if failed.note else ""}</div>')
    if record.status == "applied" and record.verified_at and not mismatched:
        return (f'<div class="banner ok"><b>적용했고, 다시 읽어 확인했습니다.</b> {written:,}{unit} 모두 넣은 값과 같습니다.</div>')
    if record.status == "applied" and mismatched:
        return (f'<div class="banner red"><b>적용했지만, 다시 읽었더니 {mismatched:,}{unit}이 넣은 값과 다릅니다.</b> '
                "아래 표에서 빨간 곳을 확인해 주세요.</div>")
    if record.status == "applied":
        return '<div class="banner amber"><b>적용했습니다.</b> 아직 다시 읽어 확인하지 않았습니다.</div>'
    if record.status == "applying":
        return f'<div class="banner amber"><b>적용하는 중입니다.</b> {done}/{len(record.steps)}번 저장했습니다.</div>'
    return '<div class="banner blue"><b>아직 적용하지 않았습니다.</b></div>'


def stopped_choices(record) -> str:
    if record.status != "stopped":
        return ""
    done = sum(step.status == "saved" for step in record.steps)
    left = len(record.steps) - done
    back = (f'<div><b>된 것까지 되돌리기</b> — 이미 바뀐 {done}번을 원래 값으로 되돌립니다(미리보기를 먼저 보여 드립니다).</div>'
            if done else "")
    return ('<h2>어떻게 할까요?</h2><p>크롬에서 ERP 로그인을 확인한 뒤 대화창에서 골라 주세요.</p><div class="choices">'
            f'<div><b>이어서</b> — 남은 {left}번을 마저 적용합니다. 그 전에 남은 값을 다시 읽어 확인합니다.</div>{back}'
            '<div><b>이대로 두기</b> — 장부에 "중간에 멈춤"으로 적혀 있어 나중에 이어서 할 수 있습니다.</div>'
            "</div>")


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
    """그대로 두는 항목 — 적어 둔 값 · 도우미가 넣은 값 · 지금 값과 까닭."""
    if not plan.kept:
        return ""
    currency = plan.currency
    heading = ("그 사이 값이 달라졌지만 말씀대로 같이 되돌리는 것" if plan.include_kept
               else "그대로 두는 것 — 그 사이 값이 달라졌습니다")
    rows = []
    for item in plan.kept:
        if item.cause.outside:
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


def rollback_ask(plan: RollbackPlan, unit: str = "칸") -> str:
    ask = f'"되돌려"라고 하시면 {len(plan.restored):,}{unit}을 되돌립니다.'
    if plan.kept and not plan.include_kept:
        ask += (f' 그 사이 달라진 {len(plan.kept):,}{unit}도 되돌리려면 "{len(plan.kept):,}{unit}도 포함해서 되돌려"라고 '
                "해 주세요.")
    if plan.unremovable:
        ask += f" 지울 수 없는 {len(plan.unremovable):,}{unit}은 그대로 남습니다."
    return (f'<div class="banner blue">{esc(ask)}</div>'
            + notes(["이미 받은 예약의 금액은 되돌려도 바뀌지 않습니다.",
                     "판매 마감·판매 가능 상태는 되돌리지 않고 값만 되돌립니다.",
                     "이 되돌리기도 장부에 한 번의 변경으로 적혀서, 다시 되돌릴 수 있습니다."]))
