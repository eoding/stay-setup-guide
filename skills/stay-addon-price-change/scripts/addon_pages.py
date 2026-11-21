"""addon_pages.py — 부가옵션 가격 도우미의 페이지(HTML): 지금 가격 · 가격 줄 설정(편집 창 전부) · 미리보기 · 적용 결과 · 되돌리기 미리보기.

페이지 틀(색 · 머리 숫자 · 저장 단계 목록 · 결과 띠 · 멈춤 선택지 · 되돌리기 머리 · 그대로 두는 것 표)은 change_core.chrome 이다.
여기에는 가격 줄 표와 이 종류만의 안내(값의 출처 표시 · 적용 범위 기록 · 금액 기록이 안 보이는 줄)를 둔다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Sequence

from addon_model import (
    DOUBT_LABELS, FIELD_LABELS, FIELDS, FORM_NAMES, NET_POINT, SELL_POINT, Line, Listing, Snapshot, key_of_item,
)
from addon_plan import CHOICE_LABELS, LINE_RULES, Plan, counts
from change_core.chrome import (
    chosen_groups, chosen_table, esc, fmt_money, fmt_time, kept_table, names_banner, notes, page, result_banner, rollback_ask,
    rollback_head, stats, steps_list, stopped_choices, unremovable_table,
)
from change_core.ledger import ChangeRecord
from change_core.money import example_step
from change_core.rollback import RollbackPlan
from change_core.rules import BLOCKED, RED

MAKER = "어딩 Stay 부가옵션 가격 도우미"
UNIT = "줄"
# 저장하면 ERP 가 하는 일 가운데 화면에 안 보이고 되돌려도 돌아오지 않는 것 — 미리보기가 적용 전에 말한다(X4)
SOURCE_NOTE = ("저장하면 ERP 가 이 줄들의 금액 출처를 'ERP 손입력'으로 적습니다. 되돌려도 금액만 돌아오고 이 표시는 돌아오지 "
               "않습니다(지금 모든 줄이 이미 'ERP 손입력'이면 달라지는 것이 없습니다).")
SCOPE_NOTE = ("편집 창에 「적용 범위」 칸이 있는 줄은, 저장할 때 ERP 가 그 줄의 적용 범위 기록이 없으면 하나 만듭니다(값은 지금과 같은 "
              "'기존 범위 그대로'라 손님이 내는 금액은 그대로). 화면에 보이지 않고 되돌려도 없어지지 않습니다.")
HIDDEN_NOTE = ("목록과 편집 창이 모두 공급 원가를 '없음'으로 보이는데 ERP 에는 원가가 저장된 줄은 도우미도 알 수 없습니다. 그런 줄은 "
               "통화별 금액이 「별도 금액 없음」으로 보여 도우미가 바꾸지 않습니다.")
KEEPS = ("이미 받은 예약의 금액은 되돌려도 바뀌지 않습니다.", "금액의 출처 표시('ERP 손입력')는 되돌리지 않습니다.")
SENT_LABELS = {"name": "이름", "season": "시즌", "date": "날짜", "rate_plan": "요금제", "description": "설명"}
SCOPE_AXES = {"rate_plan": "요금제", "room": "객실"}            # 적용 범위 카드의 축 — `scope_<축>_mode` · `_include` · `_exclude`
SCOPE_PICKS = {"include": "포함", "exclude": "제외"}


def _money(value: Decimal | None, currency: str) -> str:
    return "없음" if value is None else fmt_money(value, currency)


def _move(before: Decimal | None, after: Decimal | None, currency: str) -> str:
    if before == after:
        return f'<span class="was">{_money(before, currency)}</span><small class="more">그대로</small>'
    return (f'<span class="was">{_money(before, currency)}</span><span class="arrow">→</span>'
            f'<span class="now">{"비움" if after is None else fmt_money(after, currency)}</span>')


def _scope_sent(line: Line) -> str:
    """적용 범위 카드가 보내는 것 — 축마다 모드(화면의 글자)와 고른 대상 수, 「범위를 비운 채 저장」이 켜졌는지. 카드가 없으면 빈 글자."""
    names = [name for name, _value in line.form]
    parts = []
    for axis, word in SCOPE_AXES.items():
        mode = f"scope_{axis}_mode"
        if mode in names:
            picked = [f"{said} {names.count(f'scope_{axis}_{kind}')}개" for kind, said in SCOPE_PICKS.items()
                      if f"scope_{axis}_{kind}" in names]
            shown = line.labels.get(mode) or dict(line.form)[mode]
            parts.append(f"{word} {shown}" + (f"({' · '.join(picked)})" if picked else ""))
    if "scope_confirm_deny_all" in names:
        parts.append("범위를 비운 채 저장 켜짐")
    if not parts:
        return "적용 범위 칸 그대로" if any(name.startswith("scope_") for name in names) else ""
    return "적용 범위 " + " · ".join(parts)


def _kept_fields(line: Line) -> str:
    """저장할 때 편집 창이 보인 그대로 다시 보내는 칸 — 고르는 칸은 화면의 글자로, 적용 범위는 축마다 그 값으로."""
    parts = []
    for name, value in line.form:
        if name in FORM_NAMES.values():
            continue
        if name in SENT_LABELS:
            parts.append(f"{SENT_LABELS[name]} {line.labels.get(name, value) if value else '비어 있음'}")
    return " · ".join(part for part in (*parts, _scope_sent(line)) if part)


def scope_card(plan: Plan) -> bool:
    """저장할 수 있는 줄(바뀌는 줄 · 아직 고르지 않은 빨간 줄) 가운데 편집 창에 적용 범위 카드가 있는 줄이 있는지 — 있으면 저장할 때
    ERP 가 그 줄의 적용 범위 기록을 만들 수 있다(SCOPE_NOTE). 짧은 답의 `scope_card` 가 이것이라 도우미가 그 말을 할 때를 안다."""
    return any(name.startswith("scope_") for change in plan.changes if change.writes or change.waiting
               for name, _value in change.line.form)


def red_lines(plan: Plan) -> list[dict]:
    """고를 빨간 줄 — 규칙마다 줄 수와 고를 수 있는 것, 줄마다 무엇이 어떻게 되는지."""
    out = []
    for rule in LINE_RULES.rules:
        waiting = [change for change in plan.changes if change.verdict == rule.code and change.waiting]
        if rule.severity != RED or not waiting:
            continue
        out.append(dict(rule=rule.code, label=rule.label, lines=len(waiting),
                        choices={choice: CHOICE_LABELS[choice] for choice in rule.choices},
                        examples=[dict(line=change.key.line, name=change.line.label,
                                       moves=[f"{FIELD_LABELS[name]} {_money(change.before[name], plan.currency)} → "
                                              f"{_money(change.after[name], plan.currency)}" for name in change.changed])
                                  for change in waiting]))
    return out


def chosen_lines(plan: Plan) -> list[dict]:
    """고른 줄마다 — 고른 것의 이름(`label`)과 그렇게 고르며 담당자가 한 말(`said`)."""
    return [dict(line=change.key.line, name=change.line.label, rule=change.verdict, choice=change.choice,
                 label=CHOICE_LABELS[change.choice], said=change.said) for change in plan.changes if change.choice]


def blocked_lines(plan: Plan) -> list[dict]:
    out = []
    for change in plan.changes:
        if LINE_RULES.severity(change.verdict) == BLOCKED:
            rule = LINE_RULES.by_code[change.verdict]
            out.append(dict(line=change.key.line, name=change.line.label, rule=rule.code, label=rule.label,
                            why=DOUBT_LABELS.get(change.verdict.lower(), "")))
    return out


def render_preview(plan: Plan, change_id: int | None, steps: Sequence | None, names: Sequence[str] = ()) -> str:
    currency, request = plan.currency, plan.request
    found = counts(plan)
    title = f"미리보기 · {request.hotel} · 부가옵션 가격"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub"><b>아직 아무것도 바뀌지 않았습니다.</b> 지금 값은 {esc(fmt_time(plan.read_at))} 에 ERP 에서 읽은 것입니다. '
            f"통화 {esc(currency)}. 요청 “{esc(request.sentence)}” → {esc(request.describe())}"
            f'{f" · 장부 {change_id}번" if change_id else ""}</p>']
    if found["red"]:
        body.append(f'<div class="banner red"><b>먼저 골라 주세요 — 빨간 줄 {found["red"]}줄.</b> 줄마다 "이대로 바꿈" 또는 '
                    "\"그 줄은 안 바꿈\"을 말씀해 주시면 다시 계산합니다.</div>")
    if found["blocked"]:
        body.append(f'<div class="banner amber"><b>바꿀 수 없는 줄 {found["blocked"]}줄</b>은 그대로 둡니다(아래 표의 까닭).</div>')
    body.append(names_banner(names))
    body.append(stats([(found["will_change"], "바뀌는 줄"), (found["unchanged"], "그대로인 줄"), (found["blocked"], "바꿀 수 없는 줄"),
                       (found["red"], "고를 빨간 줄")] + ([(found["missing"], "목록에 없는 줄")] if found["missing"] else [])))
    rows = []
    for change in plan.changes:
        severity = LINE_RULES.severity(change.verdict)
        rule = LINE_RULES.by_code.get(change.verdict)
        after = change.after if change.writes or change.waiting or severity == BLOCKED else None
        cells = []
        for name in FIELDS:
            new = change.before[name] if after is None else after[name]
            cls = ("blocked" if severity == BLOCKED else "chosen" if change.choice else "red" if severity == RED
                   else "" if new != change.before[name] else "same")
            cells.append(f'<td class="{cls}">{_move(change.before[name], new, currency)}</td>')
        if rule is None:
            verdict = "바뀜" if change.writes else "그대로"
        elif change.choice:
            verdict = (f'{esc(rule.label)} <span class="tag chosen">{esc(CHOICE_LABELS[change.choice])}</span>'
                       + ('<small class="more">고르신 대로 그대로 둡니다(저장하지 않습니다)</small>' if change.choice == "keep" else ""))
        elif severity == RED:
            verdict = f'<span class="tag red">빨간 줄</span> {esc(rule.label)}'
        else:
            why = DOUBT_LABELS.get(change.verdict.lower(), "")
            verdict = f'<span class="tag blocked">바꿀 수 없음</span> {esc(rule.label)}{f"<small class=more>{esc(why)}</small>" if why else ""}'
        rows.append(f'<tr><td class="text">{esc(change.line.label)}<small class="more">가격 줄 {esc(change.key.line)}번</small></td>'
                    f'{"".join(cells)}<td class="text">{verdict}</td>'
                    f'<td class="text"><small>{esc(_kept_fields(change.line))}</small></td></tr>')
    for key in plan.missing:
        rows.append(f'<tr><td class="text">가격 줄 {esc(key.line)}번</td><td class="none" colspan="2">목록에 없음</td>'
                    '<td class="text">지워졌거나 번호가 바뀌었습니다 — 바꾸지 않습니다</td><td></td></tr>')
    body += ["<h2>줄마다 전 → 후</h2>",
             '<div class="scroll"><table><tr><th>가격 줄</th><th>판매가</th><th>공급 원가</th><th>판정</th>'
             f'<th>그대로 다시 보내는 칸</th></tr>{"".join(rows)}</table></div>']
    # 고르신 빨간 줄과 그때 하신 말 — 결과 페이지와 같은 표. 모두 「안 바꿈」이라 저장할 것이 없는 미리보기에서도 그 말이 보인다
    chosen: dict[tuple, int] = {}
    for change in plan.changes:
        if change.choice:
            key = (change.verdict, change.choice, change.said)
            chosen[key] = chosen.get(key, 0) + 1
    body.append(chosen_table([(LINE_RULES.by_code[verdict].label if verdict in LINE_RULES.by_code else str(verdict), CHOICE_LABELS[choice],
                               count, said) for (verdict, choice, said), count in chosen.items()], UNIT))
    said = [SOURCE_NOTE, "저장은 줄마다 한 번이고, 편집 창의 다른 칸(이름 · 시즌 · 날짜 · 요금제 · 설명 · 적용 범위)은 창이 보인 그대로 "
            "보냅니다. 공급 원가는 바꾸라고 하지 않으면 지금 값 그대로 보냅니다.",
            "손님 화면에는 저장하면 곧(길어야 몇 분) 새 금액이 보입니다. 이미 받은 예약의 금액은 바뀌지 않습니다.", HIDDEN_NOTE]
    if scope_card(plan):
        said.insert(1, SCOPE_NOTE)
    if steps is None:
        body += [notes(said), '<div class="banner red">아직 적용할 수 없습니다. 먼저 빨간 줄을 골라 주세요.</div>']
    elif not steps:     # 고른 대로면 바꿀 줄이 없다 — 저장이 하는 일도, "적용"도 말하지 않는다
        body.append('<div class="banner blue">바꿀 줄이 없어 적용할 것이 없습니다. 아무것도 바뀌지 않았습니다.</div>')
    else:
        body += [notes(said), f'<div class="banner blue">저장 {len(steps)}번(줄마다 한 번). 맞으면 "적용"이라고 해 주세요.</div>']
    return page(title, "\n".join(body), MAKER)


def _record_lines(record: ChangeRecord) -> dict[str, dict]:
    """장부의 줄마다 — 이름, 필드마다 전 값 · 넣은 값 · 넣는지 · 저장됐는지 · 다시 읽어 맞았는지 · 읽은 값."""
    lines: dict[str, dict] = {}
    for row in record.rows:
        entry = lines.setdefault(row.item_key, dict(label=row.label, fields={}))
        entry["fields"][row.field] = row
    return lines


def render_result(record: ChangeRecord, moved: Sequence = (), ledger_path: str | None = None, names: Sequence[str] = ()) -> str:
    """장부의 변경 하나의 결과 — 줄마다 넣은 값과 다시 읽어 맞았는지. `moved` 는 그대로여야 할 필드 · 칸이 달라진 것(verify 의 답)."""
    currency = record.currency
    lines = _record_lines(record)
    rollback = record.kind == "rollback"
    name = "되돌리기 결과" if rollback else "적용 결과"
    title = f"{name} · {record.hotel} · 부가옵션 가격"
    written = [key for key, entry in lines.items() if any(row.written and not row.rolled_back_by for row in entry["fields"].values())]
    mismatched = [key for key in written if record.verified_at and not all(
        row.verified for row in lines[key]["fields"].values() if row.written and row.action)]
    waiting = [key for key, entry in lines.items() if any(row.action and not row.written for row in entry["fields"].values())]
    moved_keys = {item["key"] for item in moved}
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">장부 {record.id}번 · 요청 “{esc(record.sentence)}”'
            f'{f" · {record.reverses}번 변경을 되돌림" if record.reverses else ""} · 통화 {esc(currency)}</p>',
            result_banner(record, len(written), len(mismatched) + len(moved_keys - set(mismatched)), UNIT), names_banner(names)]
    if moved:
        body.append('<div class="banner red"><b>그대로여야 할 칸이 달라졌습니다.</b> '
                    + esc(" · ".join(f"{item['label']} {item['what']}" for item in moved)) + "</div>")
    body += [steps_list(record.steps, {step.index: 1 for step in record.steps}, UNIT), stopped_choices(record, len(waiting), UNIT),
             chosen_table([(LINE_RULES.by_code[verdict].label if verdict in LINE_RULES.by_code else str(verdict), CHOICE_LABELS[choice],
                            len(keys), said) for verdict, choice, said, keys in chosen_groups(record.rows)], UNIT)]
    rows = []
    for key, entry in lines.items():
        cells = []
        for field_name in FIELDS:
            row = entry["fields"].get(field_name)
            if row is None:
                cells.append('<td class="none">—</td>')
                continue
            if not row.action:
                cells.append(f'<td class="same">{_move(row.before, row.before, currency)}</td>')
                continue
            moved_html = _move(row.before, row.after, currency)
            if row.rolled_back_by:
                cells.append(f'<td class="same">{moved_html}<span class="tag closed">되돌림 · 장부 {row.rolled_back_by}번</span></td>')
            elif not row.written:
                cells.append(f'<td class="wait">{moved_html}<span class="tag wait">아직 저장 안 함</span></td>')
            elif record.verified_at and not row.verified:
                cells.append(f'<td class="red">{moved_html}<small class="more">다시 읽은 값 {_money(row.seen, currency)}</small></td>')
            else:
                tag = '<span class="tag ok">확인</span>' if row.verified and record.verified_at else '<span class="tag ok">저장함</span>'
                cells.append(f"<td>{moved_html}{tag}</td>")
        rows.append(f'<tr><td class="text">{esc(entry["label"])}<small class="more">가격 줄 {esc(key_of_item(key).line)}번</small></td>'
                    f'{"".join(cells)}</tr>')
    body += ["<h2>줄마다 넣은 값</h2>",
             f'<div class="scroll"><table><tr><th>가격 줄</th><th>판매가</th><th>공급 원가</th></tr>{"".join(rows)}</table></div>']
    if record.status in ("applied", "stopped"):
        said = ["손님 화면에는 곧(길어야 몇 분) 새 금액이 보입니다. 이미 받은 예약의 금액은 그대로입니다.",
                "이 줄들의 금액 출처는 ERP 에서 'ERP 손입력'으로 표시됩니다.",
                f'되돌리려면 대화창에서 "{record.id}번 되돌려" 또는 "방금 것 되돌려"라고 하세요.']
        if ledger_path:
            said.insert(2, f"기록: {ledger_path}")
        body.append(notes(said))
    return page(title, "\n".join(body), MAKER)


def render_rollback(plan: RollbackPlan, scope: str = "") -> str:
    currency = plan.currency
    title = f"되돌리기 미리보기 · {plan.hotel} · 부가옵션 가격"
    rows = []
    for item in plan.restored:
        cells = "".join(f"<td>{_move(item.now.fields.get(name), item.targets.get(name, item.now.fields.get(name)), currency)}</td>"
                        for name in FIELDS)
        rows.append(f'<tr><td class="text">{esc(item.label)}<small class="more">가격 줄 {esc(key_of_item(item.key).line)}번</small></td>'
                    f"{cells}</tr>")
    body = [f"<h1>{esc(title)}</h1>", rollback_head(plan, scope),
            stats([(len(plan.restored), "되돌리는 줄"), (0 if plan.include_kept else len(plan.kept), "그대로 두는 줄")]),
            kept_table(plan, FIELD_LABELS), unremovable_table(plan, FIELD_LABELS, UNIT),
            "<h2>되돌리는 줄 — 지금 값 → 적어 둔 값</h2>",
            (f'<div class="scroll"><table><tr><th>가격 줄</th><th>판매가</th><th>공급 원가</th></tr>{"".join(rows)}</table></div>'
             if rows else '<p class="sub">되돌릴 줄이 없습니다.</p>'),
            notes([SOURCE_NOTE]), rollback_ask(plan, KEEPS, UNIT)]
    return page(title, "\n".join(body), MAKER)


def render_window(snapshot: Snapshot) -> str:
    """가격 줄 설정 — 읽은 줄마다 편집 창의 칸 전부(창이 보인 그대로). 아무것도 바꾸지 않았다. 도우미가 바꾸는 것은 판매가 · 공급 원가뿐이다."""
    currency = snapshot.currency
    title = f"가격 줄 설정 · {snapshot.hotel}"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">{esc(fmt_time(snapshot.read_at))} 에 ERP 편집 창에서 읽었습니다. 아무것도 바꾸지 않았습니다. 통화 {esc(currency)}. '
            "도우미가 바꿀 수 있는 것은 판매가와 공급 원가뿐이고, 나머지 칸은 ERP 화면에서 사람이 바꿉니다.</p>"]
    for line in snapshot.lines.values():
        names = [name for name, _value in line.form]
        rows = [("판매가", fmt_money(line.sell, currency)), ("공급 원가", _money(line.supply, currency))]
        rows += [(word, line.labels.get(name) or "\n".join(value for key, value in line.form if key == name).strip() or "—")
                 for name, word in SENT_LABELS.items() if name in names]
        rows += [("적용 대상", line.listed.target or "—"), ("적용 범위", _scope_sent(line) or line.listed.scope or "—")]
        if line.doubt:
            rows.append(("확인할 것", DOUBT_LABELS[line.doubt]))
        body += [f"<h2>{esc(line.label)} <small class=\"sub\">가격 줄 {esc(line.key.line)}번</small></h2>",
                 '<div class="scroll"><table><tr><th>칸</th><th>지금 값</th></tr>'
                 + "".join(f'<tr><td class="text">{esc(name)}</td><td class="text">{esc(value)}</td></tr>' for name, value in rows)
                 + "</table></div>"]
    for key in snapshot.missing():
        body.append(f'<p class="sub">가격 줄 {esc(key.line)}번(부가옵션 {esc(key.addon)}) — 목록에 없습니다. 지워졌거나 번호가 바뀌었습니다.</p>')
    return page(title, "\n".join(body), MAKER)


def render_prices(listing: Listing) -> str:
    """지금 가격 — 호텔의 부가옵션과 가격 줄 전부, 목록이 보인 그대로. 아무것도 바꾸지 않았다."""
    currency = listing.currency
    title = f"지금 부가옵션 가격 · {listing.hotel}"
    rows = []
    for line in listing.lines:
        points = line.points()
        hidden = SELL_POINT not in points
        rows.append(f'<tr><td class="text">{esc(line.addon)}<small class="more">부가옵션 {esc(line.key.addon)}번'
                    f'{f" · {esc(line.offer)}" if line.offer else ""}</small></td>'
                    f'<td class="text">{esc(line.name)}<small class="more">가격 줄 {esc(line.key.line)}번</small></td>'
                    f'<td class="text">{esc(line.target)}</td><td>{fmt_money(line.sell, currency)}</td>'
                    f'<td class="{"blocked" if hidden else ""}">'
                    f'{"알 수 없음" if hidden else _money(points.get(NET_POINT), currency)}'
                    f'{"<small class=more>금액 기록이 화면에 안 보임 — 도우미가 바꾸지 않는 줄</small>" if hidden else ""}</td></tr>')
    addon_count = len(listing.addons)
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">{esc(fmt_time(listing.read_at))} 에 ERP 에서 읽었습니다. 아무것도 바꾸지 않았습니다. 통화 {esc(currency)}.</p>',
            stats([(addon_count, "부가옵션"), (len(listing.lines), "가격 줄")]),
            (f'<div class="scroll"><table><tr><th>부가옵션</th><th>가격 줄</th><th>적용 대상</th><th>판매가</th><th>공급 원가</th></tr>'
             f'{"".join(rows)}</table></div>' if rows else '<p class="sub">가격 줄이 없습니다.</p>')]
    if listing.lines:
        body.append(notes([f'바꾸고 싶으면 대화창에서 "{listing.lines[0].addon} +{example_step(currency)}" 처럼 말씀해 주세요. 바꾸기 전에 미리보기를 먼저 보여 드립니다.']))
    return page(title, "\n".join(body), MAKER)
