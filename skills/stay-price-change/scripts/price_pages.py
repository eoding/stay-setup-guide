"""price_pages.py — 담당자가 브라우저로 여는 HTML 한 장씩. 파일 하나로 열리고 바깥 주소를 부르지 않는다.

    render_preview(plan)       미리보기 — 객실·요금제별 표(날짜가 열), 빨간 줄·적용할 수 없음 띠, 머리 숫자, 따로 볼 칸
    render_result(record)      적용 결과 — 저장 단계마다 된 것·멈춘 것, 다시 읽어 맞았는지
    render_rollback(plan)      되돌리기 미리보기 — 되돌리는 날짜, 그대로 두는 칸의 세 값과 까닭, 되돌리는 칸
    render_prices(snapshot)    지금 가격 보기 — 바꾸지 않고 표로만

글은 전부 쉬운 한국어이고, 도우미는 이 스킬을 부르는 이름이다. 밝은 화면·어두운 화면 둘 다 읽히게 색을 둔다.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta
from typing import Callable, Iterable, Mapping

from price_model import (
    BLOCKED, CHOICE_LABELS, CLOSED, RED, RESERVED, RULE_BY_CODE, RULES, CellKey, CellValue, ChangeRequest, Plan,
    RollbackPlan, Snapshot, occupancy_order, scale_of, split_occupancy,
)
from price_plan import counts

WEEKDAYS = "월화수목금토일"

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
td:first-child, th:first-child, td.text { text-align:left; }
td.text { white-space: normal; }
.was { color: var(--soft); } .now { font-weight: 700; } .arrow { color: var(--soft); padding: 0 3px; }
td.red { background: var(--red-bg); } td.blocked { background: var(--amber-bg); }
td.none, td.same { color: var(--soft); text-align:center; }
small.more { display:block; color: var(--soft); font-size: 12px; }
.tag { display:inline-block; font-size: 11.5px; font-weight:700; padding: 0 7px; border-radius: 99px; margin-left: 4px;
       vertical-align: 1px; white-space: nowrap; }
.tag.res { background: var(--blue-bg); color: var(--blue); } .tag.closed { background: var(--cell); color: var(--soft); }
.tag.red { background: var(--red); color: var(--paper); } .tag.blocked { background: var(--amber); color: var(--paper); }
.tag.ok { background: var(--pick); color: var(--paper); }
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


def day_label(day: str) -> str:
    value = date.fromisoformat(day)
    return f"{value.month}/{value.day} {WEEKDAYS[value.weekday()]}"


def days_summary(days: Iterable[str]) -> str:
    days = sorted(days)
    runs: list[list[str]] = []
    for day in days:
        if runs and (date.fromisoformat(runs[-1][-1]) + timedelta(days=1)).isoformat() == day:
            runs[-1].append(day)
        else:
            runs.append([day])
    parts = [day_label(run[0]) if len(run) == 1 else f"{day_label(run[0])} ~ {day_label(run[-1])}" for run in runs]
    if len(parts) > 8:
        parts = parts[:8] + ["…"]
    years = sorted({day[:4] for day in days})
    return f"{' · '.join(parts)} ({len(days)}일{', ' + '·'.join(years) + '년' if years else ''})"


def occupancy_label(key: str) -> str:
    if not key:
        return "인원 무관"
    if key.isdigit():
        return f"{key}명"
    adult_key, has_children = split_occupancy(key)
    if adult_key is None:
        return key
    adults = f"성인 {adult_key[1:]}"
    if not has_children:
        return adults
    children = sum(int(count) for count in re.findall(r"C(\d+)", key.upper()))
    return f"{adults} + 아동 {children}"


def nights_label(nights: int) -> str:
    return "1박" if nights == 1 else f"{nights}박 이상"


def cell_name(key: CellKey) -> str:
    return f"{day_label(key.date)} · {key.room} · {key.rate_plan} · {occupancy_label(key.occupancy)} · {nights_label(key.nights)}"


def operation_label(request: ChangeRequest, currency: str) -> str:
    value = request.value
    if request.operation == "percent":
        return f"{'+' if value >= 0 else '-'}{abs(value).normalize():f}%"
    if request.operation == "amount":
        return f"{'+' if value >= 0 else '-'}{fmt_money(abs(value), currency)} {currency}"
    return f"{occupancy_label(request.base_occupancy)} {fmt_money(value, currency)} {currency} 으로"


def stats(items: Iterable[tuple[int, str]]) -> str:
    return '<div class="stat">' + "".join(f"<div><b>{number:,}</b><span>{esc(label)}</span></div>"
                                          for number, label in items) + "</div>"


def page(title: str, body: str) -> str:
    return (f'<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<meta name="color-scheme" content="light dark">\n<title>{esc(title)}</title>\n<style>{CSS}</style>\n'
            f'</head>\n<body>\n<main>\n{body}\n<footer>어딩 Stay 가격 변경 도우미가 만든 페이지입니다.</footer>\n'
            f'</main>\n</body>\n</html>\n')


def grid(keys: Iterable[CellKey], cell: Callable[[CellKey], tuple[str, str]], reserved: set, closed: set) -> str:
    """객실·요금제마다 표 하나 — 줄은 인원·박수, 열은 날짜. `cell` 은 `(td 모양 이름, 안쪽 HTML)` 을 돌려준다.

    예약 있는 날은 날짜 머리에 단다. 마감은 그 열이 모두 마감이면 날짜 머리에, 아니면 그 칸에 단다.
    """
    groups: dict[tuple[str, str], list[CellKey]] = {}
    for key in keys:
        groups.setdefault((key.room, key.rate_plan), []).append(key)
    out = []
    for (room, plan), members in groups.items():
        present = set(members)
        days = sorted({key.date for key in members})
        lines = sorted({(key.occupancy, key.nights) for key in members}, key=lambda line: (occupancy_order(line[0]), line[1]))
        heads, full = [], set()
        for day in days:
            tags = '<span class="tag res">예약 있는 날</span>' if (room, day) in reserved else ""
            if all(key in closed for key in members if key.date == day):
                full.add(day)
                tags += '<span class="tag closed">판매 마감</span>'
            heads.append(f"<th>{esc(day_label(day))}{tags}</th>")
        rows = []
        for occupancy, nights in lines:
            tds = []
            for day in days:
                key = CellKey(room, plan, day, occupancy, nights)
                kind, inner = cell(key) if key in present else ("none", "—")
                if key in closed and day not in full:
                    inner += '<span class="tag closed">마감</span>'
                tds.append(f'<td class="{kind}">{inner}</td>' if kind else f"<td>{inner}</td>")
            rows.append(f"<tr><td>{esc(occupancy_label(occupancy))} · {esc(nights_label(nights))}</td>{''.join(tds)}</tr>")
        out.append(f'<h3>{esc(room)} · {esc(plan)}</h3>\n<div class="scroll"><table><tr><th>인원 · 박수</th>{"".join(heads)}</tr>'
                   f'{"".join(rows)}</table></div>')
    return "\n".join(out)


def _flag(verdict: str, before: CellValue, currency: str) -> str:
    if verdict == "ABOVE_LIST":
        return f"정가 {fmt_money(before.list_price, currency)} 넘음"
    if verdict == "BELOW_COST":
        return f"원가 {fmt_money(before.supply_cost, currency)} 아래"
    if verdict == "OVER_30":
        return "30% 넘음"
    return "적용할 수 없음"


def _rounding_note(currency: str) -> str:
    unit = "소수 둘째 자리(센트)" if scale_of(currency) == 2 else "1 단위"
    return f"계산하고 남는 끝자리는 {currency} {unit}까지 반올림합니다(ERP 와 같은 방식)."


def render_preview(plan: Plan, change_id: int | None = None, steps: int | None = None) -> str:
    request, currency = plan.request, plan.currency
    tally = counts(plan.changes, len(plan.skipped))
    by_key = {change.key: change for change in plan.changes}
    closed = {change.key for change in plan.changes if CLOSED in change.marks}
    reserved = {(change.key.room, change.key.date) for change in plan.changes if RESERVED in change.marks}

    def cell(key: CellKey) -> tuple[str, str]:
        change = by_key.get(key)
        if change is None:
            return "none", "가격 없음"
        rule = RULE_BY_CODE.get(change.verdict)
        was = f'<span class="was">{fmt_money(change.before.sell, currency)}</span>'
        if rule is not None and rule.severity == BLOCKED:
            return "blocked", f'{was}<span class="tag blocked">적용할 수 없음</span>'
        now = f'<span class="arrow">→</span><span class="now">{fmt_money(change.after.sell, currency)}</span>'
        if rule is not None:
            return "red", f'{was}{now}<span class="tag red">{esc(_flag(rule.code, change.before, currency))}</span>'
        return "", f"{was}{now}"

    title = f"미리보기 · {request.hotel} · {request.offer} · 판매가 {operation_label(request, currency)}"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub"><b>아직 아무것도 바뀌지 않았습니다.</b> 지금 값은 {esc(fmt_time(plan.read_at))} 에 ERP 에서 읽은 것입니다'
            f'{f" (장부 {change_id}번에 적어 두었습니다)" if change_id else ""}. 통화 {esc(currency)}.</p>']
    body.append(_request_box(request, currency))
    body.append(_preview_banners(tally))
    body.append(stats([(tally["will_change"], "바뀌는 칸"), (tally["red"], "빨간 줄"),
                       (tally["blocked"], "적용할 수 없는 칸"), (tally["reserved"], "예약 있는 날의 칸 (바꿉니다)"),
                       (tally["closed"], "판매 마감인 칸 (값만 바뀌고 마감은 그대로)"),
                       (tally["skipped"], "가격이 없어 건너뛰는 칸")]))
    if steps:
        body.append(f'<p class="sub">적용하면 ERP 에 {steps}번 나눠 저장합니다(객실 · 요금제 · 값이 같은 이어진 날마다 한 번).</p>')
    body.append("<h2>칸마다 바뀌는 값</h2>")
    body.append(grid(list(by_key) + list(plan.skipped), cell, reserved, closed))
    body.append(_flagged_section(plan, currency))
    notes = [_rounding_note(currency),
             "예약 있는 날도 똑같이 바꿉니다. 이미 받은 예약의 금액은 바뀌지 않습니다.",
             "판매 마감인 날은 값만 바뀌고 마감은 그대로입니다.",
             "정가와 공급 원가는 바꾸지 않습니다(정가를 넘는 칸에서 정가도 올리라고 고르신 경우만 정가가 같이 오릅니다)."]
    if request.operation == "percent":
        notes.insert(0, "아동이 있는 칸은 아동 추가분도 같은 비율로 곱했습니다." if request.scale_child_surcharge else
                     "아동이 있는 칸은 ERP 와 똑같이 성인 몫에만 곱하고 아동 추가분은 그대로 둡니다. "
                     "아동 추가분도 같이 바꾸려면 그렇게 말씀해 주세요.")
    body.append('<ul class="notes">' + "".join(f"<li>{esc(note)}</li>" for note in notes) + "</ul>")
    body.append('<div class="banner blue">말씀이 없으면 아무것도 바뀌지 않습니다. 대화창에서 "적용"이라고 하시면 바꿉니다.</div>')
    return page(title, "\n".join(body))


def _request_box(request: ChangeRequest, currency: str) -> str:
    rows = [("호텔", request.hotel), ("오퍼", request.offer), ("객실", " · ".join(request.rooms)),
            ("요금제", " · ".join(request.rate_plans)), ("날짜", days_summary(request.dates)),
            ("바꾸는 값", f"판매가 {operation_label(request, currency)}"),
            ("칸", "모든 인원 조합 · 모든 박수")]
    dl = "".join(f"<dt>{esc(name)}</dt><dd>{esc(value)}</dd>" for name, value in rows)
    sentence = f'<p class="sub">요청: “{esc(request.sentence)}”</p>' if request.sentence else ""
    return f'<div class="frame">{sentence}<dl class="kv">{dl}</dl></div>'


def _preview_banners(tally: Mapping) -> str:
    out = []
    blocked = [rule for rule in RULES if rule.severity == BLOCKED and tally[rule.code]]
    if blocked:
        reasons = " · ".join(f"{rule.label} {tally[rule.code]}칸" for rule in blocked)
        out.append(f'<div class="banner amber"><b>적용할 수 없음 · {tally["blocked"]}칸</b> ERP 가 받지 않는 값이라 이 칸은 '
                   f'바꾸지 않습니다. ({esc(reasons)})</div>')
    messages = {
        "ABOVE_LIST": ("정가(줄 그은 값)를 넘습니다.", "ERP 는 판매가가 정가보다 비싼 것을 받지 않습니다. 이 칸은 골라 주세요: "
                       + " / ".join(CHOICE_LABELS[choice] for choice in RULE_BY_CODE["ABOVE_LIST"].choices) + "."),
        "BELOW_COST": ("공급 원가보다 싸집니다.", "맞으면 그 칸을 짚어 다시 말씀해 주세요."),
        "OVER_30": ("지금 값보다 30% 넘게 바뀝니다.", "금액을 잘못 말씀하신 것은 아닌지 확인해 주세요. "
                    "맞으면 그 칸을 짚어 다시 말씀해 주세요."),
    }
    for rule in RULES:
        if rule.severity == RED and tally[rule.code]:
            headline, detail = messages[rule.code]
            out.append(f'<div class="banner red"><b>빨간 줄 · {tally[rule.code]:,}칸이 {esc(headline)}</b> {esc(detail)}</div>')
    if not tally["red"] and not tally["blocked"]:
        out.append('<div class="banner ok">빨간 줄이 없습니다.</div>')
    return "\n".join(out)


def _flagged_section(plan: Plan, currency: str) -> str:
    flagged = [change for change in plan.changes if change.verdict]
    if not flagged:
        return ""
    rows = []
    for change in flagged:
        rule = RULE_BY_CODE[change.verdict]
        after = "—" if change.after is None else fmt_money(change.after.sell, currency)
        choices = " / ".join(CHOICE_LABELS[choice] for choice in rule.choices) if rule.choices else "바꾸지 않음"
        kind = "적용할 수 없음" if rule.severity == BLOCKED else "빨간 줄"
        rows.append(f'<tr><td class="text">{esc(cell_name(change.key))}</td><td>{fmt_money(change.before.sell, currency)}</td>'
                    f'<td>{after}</td><td>{fmt_money(change.before.list_price, currency)}</td>'
                    f'<td>{fmt_money(change.before.supply_cost, currency)}</td>'
                    f'<td class="text"><span class="tag {"blocked" if rule.severity == BLOCKED else "red"}">{kind}</span> '
                    f'{esc(rule.label)}</td><td class="text">{esc(choices)}</td></tr>')
    return ('<h2>따로 확인할 칸</h2><div class="scroll"><table><tr><th>칸</th><th>지금</th><th>바뀔 값</th><th>정가</th>'
            '<th>공급 원가</th><th>왜</th><th>고를 수 있는 것</th></tr>' + "".join(rows) + "</table></div>")


def _step_label(step) -> str:
    return f"{step.room} · {step.rate_plan} · {days_summary(step.dates)}"


def render_result(record, ledger_path: str | None = None) -> str:
    currency = record.currency
    written = [cell for cell in record.cells if cell.written]
    mismatched = [cell for cell in written if record.verified_at and not cell.verified]
    failed = next((step for step in record.steps if step.status == "failed"), None)
    done = sum(step.status == "saved" for step in record.steps)
    kind = "되돌리기 결과" if record.kind == "rollback" else "적용 결과"
    title = f"{kind} · {record.hotel} · {record.offer}"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">장부 {record.id}번 · 요청 “{esc(record.sentence)}”'
            f'{f" · {record.reverses}번 변경을 되돌림" if record.reverses else ""} · 통화 {esc(currency)}</p>']
    if record.status == "stopped" and failed is not None:
        body.append(f'<div class="banner red"><b>{failed.index}번째 저장에서 멈췄습니다.</b> 지금은 일부만 바뀐 상태입니다.'
                    f'{f" ({esc(failed.note)})" if failed.note else ""}</div>')
    elif record.status == "applied" and record.verified_at and not mismatched:
        body.append(f'<div class="banner ok"><b>적용했고, 다시 읽어 확인했습니다.</b> {len(written):,}칸 모두 넣은 값과 같습니다.</div>')
    elif record.status == "applied" and mismatched:
        body.append(f'<div class="banner red"><b>적용했지만, 다시 읽었더니 {len(mismatched):,}칸이 넣은 값과 다릅니다.</b> '
                    "아래 표에서 빨간 칸을 확인해 주세요.</div>")
    elif record.status == "applied":
        body.append('<div class="banner amber"><b>적용했습니다.</b> 아직 다시 읽어 확인하지 않았습니다.</div>')
    elif record.status == "applying":
        body.append(f'<div class="banner amber"><b>적용하는 중입니다.</b> {done}/{len(record.steps)}번 저장했습니다.</div>')
    else:
        body.append('<div class="banner blue"><b>아직 적용하지 않았습니다.</b></div>')
    if record.steps:
        items = []
        for step in record.steps:
            mark, text = {"saved": ('<span class="ok">✓</span>', '<span class="sub">저장함</span>'),
                          "failed": ('<span class="fail">✕</span>', '<span class="fail">여기서 멈춤 · 바뀌지 않음</span>'),
                          }.get(step.status, ('<span class="wait">–</span>', '<span class="wait">아직 안 함</span>'))
            items.append(f"<li>{mark}<span>{step.index}. {esc(_step_label(step.step))}</span>{text}</li>")
        body.append('<h2>저장 단계</h2><ul class="steps">' + "".join(items) + "</ul>")
    if record.status == "stopped":
        left = len(record.steps) - done
        body.append('<h2>어떻게 할까요?</h2><p>크롬에서 ERP 로그인을 확인한 뒤 대화창에서 골라 주세요.</p><div class="choices">'
                    f'<div><b>이어서</b> — 남은 {left}번을 마저 적용합니다. 그 전에 남은 칸을 다시 읽어 확인합니다.</div>'
                    f'<div><b>된 것까지 되돌리기</b> — 이미 바뀐 {done}번을 원래 값으로 되돌립니다(미리보기를 먼저 보여 드립니다).</div>'
                    '<div><b>이대로 두기</b> — 일부만 바뀐 채로 둡니다. 장부에 "중간에 멈춤"으로 적혀 있어 나중에 이어서 할 수 있습니다.</div>'
                    "</div>")
    by_key = {cell.key: cell for cell in record.cells}
    closed = {cell.key for cell in record.cells if cell.before.state == "closed"}
    reserved = {(cell.key.room, cell.key.date) for cell in record.cells if cell.reserved}

    def cell_html(key: CellKey) -> tuple[str, str]:
        cell = by_key[key]
        was = f'<span class="was">{fmt_money(cell.before.sell, currency)}</span>'
        if not cell.written:
            return "same", f'{was}<small class="more">그대로</small>'
        now = f'<span class="arrow">→</span><span class="now">{fmt_money(cell.after_sell, currency)}</span>'
        listed = f'<small class="more">정가 {fmt_money(cell.after_list, currency)}</small>' if cell.after_list is not None else ""
        if record.verified_at and not cell.verified:
            seen = "읽지 못함" if cell.seen is None else fmt_money(cell.seen.sell, currency)
            return "red", f'{was}{now}{listed}<small class="more">다시 읽은 값 {seen}</small>'
        check = '<span class="tag ok">확인</span>' if cell.verified else ""
        return "", f"{was}{now}{check}{listed}"

    body.append("<h2>칸마다 넣은 값</h2>")
    body.append(grid(by_key, cell_html, reserved, closed))
    if record.status in ("applied", "stopped"):
        notes = ["손님 화면에는 길어야 5분 안에 새 가격이 보입니다. 결제 금액은 바로 새 가격입니다.",
                 "이미 받은 예약의 금액은 그대로입니다.",
                 "이 칸들은 ERP 에서 '손입력'으로 표시됩니다.",
                 f'되돌리려면 대화창에서 "{record.id}번 되돌려" 또는 "방금 것 되돌려"라고 하세요.']
        if ledger_path:
            notes.insert(3, f"기록: {ledger_path}")
        body.append('<ul class="notes">' + "".join(f"<li>{esc(note)}</li>" for note in notes) + "</ul>")
    return page(title, "\n".join(body))


def render_rollback(plan: RollbackPlan) -> str:
    currency = plan.currency
    title = f"되돌리기 미리보기 · {plan.hotel} · {plan.offer}"
    applied = f"{fmt_time(plan.original_applied_at)} 적용" if plan.original_applied_at else "중간에 멈춘 변경"
    reserved_back = sum(RESERVED in change.marks for change in plan.restored)
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub"><b>아직 아무것도 바뀌지 않았습니다.</b> 지금 값은 {esc(fmt_time(plan.read_at))} 에 ERP 에서 읽은 것입니다. '
            f"통화 {esc(currency)}.</p>",
            f'<div class="banner blue"><b>{esc(fmt_time(plan.restore_to))} 에 적어 둔 값으로 되돌립니다.</b><br>'
            f"그때 한 일: “{esc(plan.original_sentence)}” ({esc(applied)}, 장부 {plan.reverses}번)</div>",
            stats([(len(plan.restored), "되돌리는 칸"),
                   (0 if plan.include_kept else len(plan.kept), "그대로 두는 칸"),
                   (reserved_back, "되돌리는 칸 중 예약 있는 날")])]
    if plan.kept:
        heading = ("그 사이 값이 달라졌지만 말씀대로 같이 되돌리는 칸" if plan.include_kept
                   else "그대로 두는 칸 — 그 사이 값이 달라졌습니다")
        rows = []
        for cell in plan.kept:
            if cell.cause.outside:
                why = '도우미 밖에서 바뀜 <span class="sub">(ERP 에서 직접 고친 것으로 보임)</span>'
            else:
                why = (f'이 컴퓨터의 다른 변경 <span class="sub">({esc(fmt_time(cell.cause.at))} '
                       f'“{esc(cell.cause.sentence)}”, 장부 {cell.cause.change_id}번)</span>')
            now = "가격 없음" if cell.now.sell is None else fmt_money(cell.now.sell, currency)
            rows.append(f'<tr><td class="text">{esc(cell_name(cell.key))}</td><td>{fmt_money(cell.recorded.sell, currency)}</td>'
                        f'<td>{fmt_money(cell.written.sell, currency)}</td><td class="red"><b>{now}</b></td>'
                        f'<td class="text">{why}</td></tr>')
        body.append(f'<h2>{esc(heading)}</h2><div class="scroll"><table><tr><th>칸</th>'
                    f'<th>적어 둔 값<br><span class="sub">{esc(fmt_time(plan.restore_to))}</span></th>'
                    f'<th>도우미가 넣은 값<br><span class="sub">{esc(fmt_time(plan.original_applied_at))}</span></th>'
                    f'<th>지금 값</th><th>왜</th></tr>{"".join(rows)}</table></div>')
    by_key = {change.key: change for change in plan.restored}
    held = {} if plan.include_kept else {cell.key: cell for cell in plan.kept}
    closed = {key for key, change in by_key.items() if CLOSED in change.marks}
    closed |= {key for key, cell in held.items() if cell.now.state == "closed"}
    reserved = {(key.room, key.date) for key, change in by_key.items() if RESERVED in change.marks}

    def cell(key: CellKey) -> tuple[str, str]:
        if key in held:
            now = held[key].now
            return "red", (f'<span class="now">{"가격 없음" if now.sell is None else fmt_money(now.sell, currency)}</span>'
                           '<small class="more">그대로 둠</small>')
        change = by_key[key]
        was = "가격 없음" if change.before.sell is None else fmt_money(change.before.sell, currency)
        listed = (f'<small class="more">정가 {fmt_money(change.after.list_price, currency)}</small>'
                  if change.after.list_price != change.before.list_price else "")
        return "", (f'<span class="was">{was}</span><span class="arrow">→</span>'
                    f'<span class="now">{fmt_money(change.after.sell, currency)}</span>{listed}')

    body.append('<h2>되돌리는 칸 <span class="sub">— 예약 있는 날도 포함합니다</span></h2>')
    body.append(grid([*by_key, *held], cell, reserved, closed) if by_key or held else
                '<p class="sub">되돌릴 칸이 없습니다.</p>')
    ask = f'"되돌려"라고 하시면 {len(plan.restored):,}칸을 되돌립니다.'
    if plan.kept and not plan.include_kept:
        ask += f' 그대로 두는 {len(plan.kept):,}칸도 되돌리려면 "{len(plan.kept):,}칸도 포함해서 되돌려"라고 해 주세요.'
    body.append(f'<div class="banner blue">{esc(ask)}</div>')
    body.append('<ul class="notes"><li>이미 받은 예약의 금액은 되돌려도 바뀌지 않습니다.</li>'
                "<li>이 되돌리기도 장부에 한 번의 변경으로 적혀서, 다시 되돌릴 수 있습니다.</li></ul>")
    return page(title, "\n".join(body))


def render_prices(snapshot: Snapshot) -> str:
    currency = snapshot.currency
    title = f"지금 가격 · {snapshot.hotel} · {snapshot.offer}"
    cells = snapshot.cells
    priced = [key for key, value in cells.items() if value.state != "missing"]
    closed = {key for key, value in cells.items() if value.state == "closed"}

    def cell(key: CellKey) -> tuple[str, str]:
        value = cells[key]
        if value.state == "missing":
            return "none", "가격 없음"
        extra = "".join(f'<small class="more">{name} {fmt_money(amount, currency)}</small>'
                        for name, amount in (("정가", value.list_price), ("원가", value.supply_cost)) if amount is not None)
        return "", f'<span class="now">{fmt_money(value.sell, currency)}</span>{extra}'

    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">{esc(fmt_time(snapshot.read_at))} 에 ERP 에서 읽은 값입니다. <b>아무것도 바꾸지 않았습니다.</b> '
            f"통화 {esc(currency)}.</p>",
            stats([(len(priced), "가격 있는 칸"), (len(closed), "판매 마감인 칸"), (len(cells) - len(priced), "가격 없는 칸"),
                   (len(snapshot.reserved), "예약 있는 날 (객실 · 날짜)")]),
            grid(sorted(cells, key=lambda k: (k.room, k.rate_plan, k.date)), cell, set(snapshot.reserved), closed),
            '<ul class="notes"><li>판매가는 굵게, 정가(손님 화면에 줄 그어 보이는 값)와 공급 원가는 작게 보입니다.</li>'
            '<li>바꾸고 싶으면 대화창에서 "12월 디럭스 +10,000" 처럼 말씀해 주세요. 바꾸기 전에 미리보기를 먼저 보여 드립니다.</li></ul>']
    return page(title, "\n".join(body))
