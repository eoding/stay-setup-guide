"""price_pages.py — 가격 칸 페이지. 틀(색·머리 숫자·저장 단계·되돌리기 띠)은 `change_core.chrome` 이 그리고,
여기서는 칸 표(객실·요금제마다 표 하나, 줄은 인원·박수, 열은 날짜 — 그림의 모양 가)와 가격 말을 그린다.

    render_preview(plan)       미리보기 — 칸 표, 빨간 줄·적용할 수 없음 띠, 머리 숫자, 따로 볼 칸
    render_result(record)      적용 결과 — 장부의 변경 하나: 저장 단계마다 된 것·멈춘 것, 다시 읽어 맞았는지
    render_rollback(plan)      되돌리기 미리보기 — 되돌리는 날짜, 그대로 두는 칸의 세 값과 까닭, 되돌리는 칸
    render_prices(snapshot)    지금 가격 보기 — 바꾸지 않고 표로만

글은 전부 쉬운 한국어이고, 도우미는 이 스킬을 부르는 이름이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Iterable, Mapping, Sequence

from change_core.chrome import (
    esc, fmt_money, fmt_time, kept_table, notes, page, result_banner, rollback_ask, rollback_head, stats, steps_list,
    stopped_choices,
)
from change_core.ledger import ChangeRecord
from change_core.money import scale_of
from change_core.rollback import RollbackPlan
from change_core.rules import BLOCKED, RED

from price_model import (
    CELL_RULES, CHOICE_LABELS, CLOSED, FIELD_LABELS, FIELDS, RESERVED, SKIP_LABELS, CellKey, CellValue, ChangeRequest, Plan,
    Snapshot, cell_name, day_label, key_of_item, nights_label, occupancy_label, occupancy_order, value_of,
)
from price_plan import counts, days_summary

MAKER = "어딩 Stay 가격 변경 도우미"


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


def operation_label(request: ChangeRequest, currency: str) -> str:
    """바꾸는 값과 방법 — "판매가 +10%" · "정가 -5,000 USD" · "공급 원가 지움" · "판매가 성인 2 1박 350.00 USD 으로"."""
    return f"{FIELD_LABELS[request.field]} {_how(request, currency)}"


def _how(request: ChangeRequest, currency: str) -> str:
    value = request.value
    if request.operation == "clear":
        return "지움"
    if request.operation == "percent":
        return f"{'+' if value >= 0 else '-'}{abs(value).normalize():f}%"
    if request.operation == "amount":
        return f"{'+' if value >= 0 else '-'}{fmt_money(abs(value), currency)} {currency}"
    return f"{occupancy_label(request.base_occupancy)} 1박 {fmt_money(value, currency)} {currency} 으로"


def _flag(verdict: str, after: CellValue, currency: str) -> str:
    if verdict == "ABOVE_LIST":
        return f"정가 {fmt_money(after.list, currency)} 넘음"
    if verdict == "BELOW_COST":
        return f"원가 {fmt_money(after.supply, currency)} 아래"
    if verdict == "OVER_30":
        return "30% 넘음"
    return "적용할 수 없음"


def _move(before: CellValue, after: CellValue, currency: str) -> str:
    """바뀐 필드마다 `전 → 후`. 판매가는 굵은 줄로, 정가·원가는 작은 줄로."""
    parts = []
    for name in FIELDS:
        old, new = getattr(before, name), getattr(after, name)
        if old == new:
            continue
        was = "새로" if old is None else fmt_money(old, currency)
        now = "비움" if new is None else fmt_money(new, currency)
        if name == "sell":
            parts.insert(0, f'<span class="was">{was}</span><span class="arrow">→</span><span class="now">{now}</span>')
        else:
            parts.append(f'<small class="more">{FIELD_LABELS[name]} {was} → {now}</small>')
    return "".join(parts)


def _rounding_note(currency: str) -> str:
    unit = "소수 둘째 자리(센트)" if scale_of(currency) == 2 else "1 단위"
    return f"계산하고 남는 끝자리는 {currency} {unit}까지 반올림합니다(ERP 와 같은 방식)."


def render_preview(plan: Plan, change_id: int | None = None, steps: Sequence | None = None) -> str:
    request, currency = plan.request, plan.currency
    tally = counts(plan.changes, len(plan.skipped))
    by_key = {change.key: change for change in plan.changes}
    closed = {change.key for change in plan.changes if CLOSED in change.marks}
    reserved = {(change.key.room, change.key.date) for change in plan.changes if RESERVED in change.marks}

    skipped = {item.key: item.reason for item in plan.skipped}

    def cell(key: CellKey) -> tuple[str, str]:
        change = by_key.get(key)
        if change is None:
            return "none", esc(SKIP_LABELS[skipped[key]])
        severity = CELL_RULES.severity(change.verdict)
        if severity == BLOCKED:
            return "blocked", (f'<span class="was">{fmt_money(change.before.sell, currency)}</span>'
                               '<span class="tag blocked">적용할 수 없음</span>')
        moved = _move(change.before, change.after, currency)
        if severity == RED:
            return "red", f'{moved}<span class="tag red">{esc(_flag(change.verdict, change.after, currency))}</span>'
        return "", moved

    title = f"미리보기 · {request.hotel} · {request.offer} · {operation_label(request, currency)}"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub"><b>아직 아무것도 바뀌지 않았습니다.</b> 지금 값은 {esc(fmt_time(plan.read_at))} 에 ERP 에서 읽은 것입니다'
            f'{f" (장부 {change_id}번에 적어 두었습니다)" if change_id else ""}. 통화 {esc(currency)}.</p>',
            _request_box(request, currency), _preview_banners(tally),
            stats([(tally["will_change"], "바뀌는 칸"), (tally["red"], "빨간 줄"),
                   (tally["blocked"], "적용할 수 없는 칸"), (tally["reserved"], "예약 있는 날의 칸 (바꿉니다)"),
                   (tally["closed"], "판매 마감인 칸 (값만 바뀌고 마감은 그대로)"),
                   (tally["skipped"], "건너뛰는 칸")]), _skip_line(plan)]
    if steps:
        edits = sum(step.kind == "cell_edit" for step in steps)
        body.append(f'<p class="sub">적용하면 ERP 에 {len(steps)}번 나눠 저장합니다(객실 · 요금제 · 값이 같은 이어진 날마다 한 번'
                    f'{f", 그중 정가·원가를 비우는 셀 창 저장 {edits}번" if edits else ""}).</p>')
    body += ["<h2>칸마다 바뀌는 값</h2>", grid(list(by_key) + list(skipped), cell, reserved, closed),
             _flagged_section(plan, currency)]
    others = [FIELD_LABELS[name] for name in FIELDS if name != request.field]
    lines = [_rounding_note(currency),
             "예약 있는 날도 똑같이 바꿉니다. 이미 받은 예약의 금액은 바뀌지 않습니다.",
             "판매 마감인 날은 값만 바뀌고 마감은 그대로입니다.",
             f"{others[0]}와 {others[1]}는 바꾸지 않습니다(정가를 넘는 칸에서 정가를 올리거나 지우라고 고르신 경우만 정가가 같이 바뀝니다)."]
    if request.operation == "percent":
        lines.insert(0, "아동이 있는 칸은 아동 추가분도 같은 비율로 곱했습니다." if request.scale_child_surcharge else
                     "아동이 있는 칸은 ERP 와 똑같이 성인 몫에만 곱하고 아동 추가분은 그대로 둡니다. "
                     "아동 추가분도 같이 바꾸려면 그렇게 말씀해 주세요.")
    body += [notes(lines),
             '<div class="banner blue">말씀이 없으면 아무것도 바뀌지 않습니다. 대화창에서 "적용"이라고 하시면 바꿉니다.</div>']
    return page(title, "\n".join(body), MAKER)


def _skip_line(plan: Plan) -> str:
    reasons: dict[str, int] = {}
    for item in plan.skipped:
        reasons[item.reason] = reasons.get(item.reason, 0) + 1
    if not reasons:
        return ""
    return ('<p class="sub">건너뛰는 칸의 까닭: '
            + esc(" · ".join(f"{SKIP_LABELS[reason]} {count:,}칸" for reason, count in reasons.items())) + "</p>")


def _request_box(request: ChangeRequest, currency: str) -> str:
    rows = [("호텔", request.hotel), ("오퍼", request.offer), ("객실", " · ".join(request.rooms)),
            ("요금제", " · ".join(request.rate_plans)), ("날짜", days_summary(request.dates)),
            ("바꾸는 값", operation_label(request, currency)),
            ("칸", "모든 인원 조합 · 모든 박수")]
    dl = "".join(f"<dt>{esc(name)}</dt><dd>{esc(value)}</dd>" for name, value in rows)
    sentence = f'<p class="sub">요청: “{esc(request.sentence)}”</p>' if request.sentence else ""
    return f'<div class="frame">{sentence}<dl class="kv">{dl}</dl></div>'


def _preview_banners(tally: Mapping) -> str:
    out = []
    blocked = [rule for rule in CELL_RULES.rules if rule.severity == BLOCKED and tally[rule.code]]
    if blocked:
        reasons = " · ".join(f"{rule.label} {tally[rule.code]}칸" for rule in blocked)
        out.append(f'<div class="banner amber"><b>적용할 수 없음 · {tally["blocked"]}칸</b> ERP 가 받지 않는 값이라 이 칸은 '
                   f'바꾸지 않습니다. ({esc(reasons)})</div>')
    messages = {
        "ABOVE_LIST": ("정가(줄 그은 값)를 넘습니다.", "ERP 는 판매가가 정가보다 비싼 것을 받지 않습니다. 이 칸은 골라 주세요: "
                       + " / ".join(CHOICE_LABELS[choice] for choice in CELL_RULES.by_code["ABOVE_LIST"].choices) + "."),
        "BELOW_COST": ("공급 원가보다 싸집니다.", "맞으면 그 칸을 짚어 다시 말씀해 주세요."),
        "OVER_30": ("지금 값보다 30% 넘게 바뀝니다.", "금액을 잘못 말씀하신 것은 아닌지 확인해 주세요. "
                    "맞으면 그 칸을 짚어 다시 말씀해 주세요."),
    }
    for rule in CELL_RULES.rules:
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
        rule = CELL_RULES.by_code[change.verdict]
        after = change.after or change.before
        moved = "—" if change.after is None else _move(change.before, change.after, currency)
        choices = " / ".join(CHOICE_LABELS[choice] for choice in rule.choices) if rule.choices else "바꾸지 않음"
        kind, word = ("blocked", "적용할 수 없음") if rule.severity == BLOCKED else ("red", "빨간 줄")
        rows.append(f'<tr><td class="text">{esc(cell_name(change.key))}</td><td>{fmt_money(change.before.sell, currency)}</td>'
                    f'<td>{moved}</td><td>{fmt_money(after.list, currency)}</td><td>{fmt_money(after.supply, currency)}</td>'
                    f'<td class="text"><span class="tag {kind}">{word}</span> {esc(rule.label)}</td>'
                    f'<td class="text">{esc(choices)}</td></tr>')
    return ('<h2>따로 확인할 칸</h2><div class="scroll"><table><tr><th>칸</th><th>지금 판매가</th><th>바뀌는 값</th>'
            '<th>정가(바뀐 뒤)</th><th>공급 원가(바뀐 뒤)</th><th>왜</th><th>고를 수 있는 것</th></tr>'
            + "".join(rows) + "</table></div>")


@dataclass
class CellView:
    """장부의 줄(필드마다 하나)을 칸 하나로 모은 것."""
    before: CellValue
    after: dict = field(default_factory=dict)
    written: bool = False
    verified: bool = True
    seen: dict = field(default_factory=dict)
    reserved: bool = False


def cell_views(record: ChangeRecord) -> dict[CellKey, CellView]:
    grouped: dict[str, list] = {}
    for row in record.rows:
        grouped.setdefault(row.item_key, []).append(row)
    views = {}
    for item_key, rows in grouped.items():
        before = {row.field: row.before for row in rows}
        view = CellView(CellValue(*(before.get(name) for name in FIELDS), rows[0].state),
                        reserved=RESERVED in rows[0].marks)
        for row in rows:
            if row.written:
                view.written = True
                view.after[row.field] = row.after
                view.verified = view.verified and row.verified
                view.seen[row.field] = row.seen
        views[key_of_item(item_key)] = view
    return views


def render_result(record: ChangeRecord, ledger_path: str | None = None) -> str:
    currency = record.currency
    views = cell_views(record)
    written = [view for view in views.values() if view.written]
    mismatched = [view for view in written if record.verified_at and not view.verified]
    kind = "되돌리기 결과" if record.kind == "rollback" else "적용 결과"
    title = f"{kind} · {record.hotel} · {record.offer}"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">장부 {record.id}번 · 요청 “{esc(record.sentence)}”'
            f'{f" · {record.reverses}번 변경을 되돌림" if record.reverses else ""} · 통화 {esc(currency)}</p>',
            result_banner(record, len(written), len(mismatched)), steps_list(record.steps), stopped_choices(record)]
    closed = {key for key, view in views.items() if view.before.state == "closed"}
    reserved = {(key.room, key.date) for key, view in views.items() if view.reserved}

    def cell(key: CellKey) -> tuple[str, str]:
        view = views[key]
        if not view.written:
            return "same", f'<span class="was">{fmt_money(view.before.sell, currency)}</span><small class="more">그대로</small>'
        moved = _move(view.before, _with(view.before, view.after), currency)
        if record.verified_at and not view.verified:
            seen = " · ".join(f"{FIELD_LABELS[name]} {'읽지 못함' if value is None else fmt_money(value, currency)}"
                              for name, value in view.seen.items())
            return "red", f'{moved}<small class="more">다시 읽은 값 {seen}</small>'
        return "", moved + ('<span class="tag ok">확인</span>' if view.verified and record.verified_at else "")

    body += ["<h2>칸마다 넣은 값</h2>", grid(views, cell, reserved, closed)]
    if record.status in ("applied", "stopped"):
        lines = ["손님 화면에는 길어야 5분 안에 새 가격이 보입니다. 결제 금액은 바로 새 가격입니다.",
                 "이미 받은 예약의 금액은 그대로입니다.",
                 "이 칸들은 ERP 에서 '손입력'으로 표시됩니다.",
                 f'되돌리려면 대화창에서 "{record.id}번 되돌려" 또는 "방금 것 되돌려"라고 하세요.']
        if ledger_path:
            lines.insert(3, f"기록: {ledger_path}")
        body.append(notes(lines))
    return page(title, "\n".join(body), MAKER)


def render_rollback(plan: RollbackPlan, reserved: Iterable[tuple[str, str]] = (), scope: str = "") -> str:
    currency = plan.currency
    title = f"되돌리기 미리보기 · {plan.hotel} · {plan.offer}"
    reserved = set(reserved)
    restored = {key_of_item(item.key): item for item in plan.restored}
    held = {key_of_item(item.key): item for item in plan.kept if item.cause.created or not plan.include_kept}
    befores = {key: value_of(item.now) for key, item in restored.items()}
    closed = {key for key, value in befores.items() if value.state == "closed"}
    closed |= {key for key, item in held.items() if item.now.state == "closed"}

    def cell(key: CellKey) -> tuple[str, str]:
        if key in held:
            sell = held[key].now.fields.get("sell")
            return "red", (f'<span class="now">{"가격 없음" if sell is None else fmt_money(sell, currency)}</span>'
                           '<small class="more">그대로 둠</small>')
        return "", _move(befores[key], _with(befores[key], restored[key].targets), currency)

    body = [f"<h1>{esc(title)}</h1>", rollback_head(plan, scope),
            stats([(len(restored), "되돌리는 칸"), (len(held), "그대로 두는 칸"),
                   (sum((key.room, key.date) in reserved for key in restored), "되돌리는 칸 중 예약 있는 날")]),
            kept_table(plan, FIELD_LABELS),
            '<h2>되돌리는 칸 <span class="sub">— 예약 있는 날도 포함합니다</span></h2>',
            grid([*restored, *held], cell, reserved, closed) if restored or held else
            '<p class="sub">되돌릴 칸이 없습니다.</p>',
            rollback_ask(plan)]
    return page(title, "\n".join(body), MAKER)


def _with(value: CellValue, fields: Mapping[str, Decimal | None]) -> CellValue:
    """`fields` 의 필드만 갈아 끼운 값. 없던 칸에 값을 넣으면 판매 가능한 칸이 된다."""
    merged = {name: fields[name] if name in fields else getattr(value, name) for name in FIELDS}
    return CellValue(merged["sell"], merged["list"], merged["supply"], "open" if value.state == "missing" else value.state)


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
                        for name, amount in (("정가", value.list), ("원가", value.supply)) if amount is not None)
        return "", f'<span class="now">{fmt_money(value.sell, currency)}</span>{extra}'

    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">{esc(fmt_time(snapshot.read_at))} 에 ERP 에서 읽은 값입니다. <b>아무것도 바꾸지 않았습니다.</b> '
            f"통화 {esc(currency)}.</p>",
            stats([(len(priced), "가격 있는 칸"), (len(closed), "판매 마감인 칸"), (len(cells) - len(priced), "가격 없는 칸"),
                   (len(snapshot.reserved), "예약 있는 날 (객실 · 날짜)")]),
            grid(sorted(cells, key=lambda k: (k.room, k.rate_plan, k.date)), cell, set(snapshot.reserved), closed),
            notes(["판매가는 굵게, 정가(손님 화면에 줄 그어 보이는 값)와 공급 원가는 작게 보입니다.",
                   '바꾸고 싶으면 대화창에서 "12월 디럭스 +10,000" 처럼 말씀해 주세요. 바꾸기 전에 미리보기를 먼저 보여 드립니다.'])]
    return page(title, "\n".join(body), MAKER)
