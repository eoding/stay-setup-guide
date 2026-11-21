"""charge_pages.py — 부과금 도우미의 페이지(HTML): 지금 부과금 · 부과금 설정(편집 창 전부) · 미리보기 · 적용 결과 · 되돌리기 미리보기.

페이지 틀(색 · 머리 숫자 · 저장 단계 목록 · 결과 띠 · 멈춤 선택지 · 되돌리기 머리 · 그대로 두는 것 표)은 change_core.chrome 이다.
여기에는 부과금마다의 금액 칸 표와 이 종류만의 안내(저장하면 다시 만들어지는 줄 · 적용 범위 기록 · 무료가 되는 칸)를 둔다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from charge_model import AGE, FIELD_LABELS, ITEM_KIND, Charge, Listing, Place, Snapshot, part_of_key
from charge_plan import CHOICE_LABELS, RULES, AmountChange, Plan, counts, form_refusal, unused
from change_core.chrome import (
    MOVED_TAG, UNDO_ONCE, chosen_groups, chosen_table, esc, fmt_money, fmt_time, kept_table, moved_sentence, names_banner, nothing_left,
    notes, page, result_banner, rollback_ask, rollback_head, stats, steps_list, stop_view, stopped_choices, times_word, unremovable_table,
)
from change_core.ledger import ChangeRecord
from change_core.rollback import RollbackPlan
from change_core.rules import BLOCKED, RED

MAKER = "어딩 Stay 부과금 도우미"
UNIT = "칸"
REBUILT_NOTE = ("저장하면 ERP 가 그 부과금의 시간대 요율 줄과 연령별 단가를 모두 지우고 보낸 값으로 다시 만듭니다. 금액은 그대로지만 그 "
                "줄들의 ERP 번호가 새로 바뀌고, 되돌려도 번호는 돌아오지 않습니다(금액은 돌아옵니다).")
SCOPE_NOTE = ("편집 창에 「적용 범위」 칸이 있는 부과금은, 저장할 때 ERP 가 그 부과금의 적용 범위 기록이 없으면 하나 만듭니다(값은 지금과 "
              "같은 '기존 범위 그대로'라 손님이 내는 금액은 그대로). 화면에 보이지 않고 되돌려도 없어지지 않습니다.")
KEPT_NOTE = ("저장은 부과금마다 한 번이고, 편집 창의 다른 칸(종류 · 이름 · 부과 방식 · 단위 · 금액의 뜻(미정/지정) · 의무와 날짜 · 객실 · "
             "현장 결제 통화 · 시간대 줄의 시각과 방식 · 설명 · 적용 범위)은 창이 보인 그대로 보냅니다. 표의 다른 금액도 그대로 보냅니다.")
GUEST_NOTE = "손님 화면에는 저장하면 곧(길어야 몇 분) 새 금액이 보입니다. 이미 받은 예약의 금액은 바뀌지 않습니다."
KEEPS = ("이미 받은 예약의 금액은 되돌려도 바뀌지 않습니다.",
         "시간대 요율 줄 · 연령별 단가의 ERP 번호와 저장할 때 생긴 적용 범위 기록은 되돌리지 못합니다(금액만 되돌립니다).")
ROLLBACK_LABELS = {"amount": "금액", "pct": "정률(%)", "onsite": "현장 결제 금액"}


def _value(value: Decimal | None, place: Place, charge: Charge | None, currency: str) -> str:
    if value is None:
        return "비어 있음"
    if place.field == "pct":
        return f"{value:,.2f}%"
    unit = (charge.onsite_currency if charge and place.field == "onsite" and charge.onsite_currency else currency)
    return f"{fmt_money(value, unit)} {unit}".strip()


def _move(before, after, place: Place, charge: Charge | None, currency: str) -> str:
    if after is None or before == after:
        return f'<span class="was">{_value(before, place, charge, currency)}</span><small class="more">그대로</small>'
    free = '<small class="more"><b>무료가 됩니다</b></small>' if after == 0 else ""
    return (f'<span class="was">{_value(before, place, charge, currency)}</span><span class="arrow">→</span>'
            f'<span class="now">{_value(after, place, charge, currency)}</span>{free}')


def _shape(charge: Charge) -> str:
    """부과금의 모양 한 줄 — 종류 · 방식 · 단위 · 의무와 날짜 · 현장 결제 통화(창이 보인 글자)."""
    labels = charge.labels
    parts = [labels.get("kind", ""), labels.get("basis", ""), labels.get("per", "")]
    dates = charge.one("date_scope").strip()
    parts.append(("의무" + (f" · {dates}" if dates else " · 오퍼 전 기간")) if charge.one("date_mode") == "mandatory" else "선택")
    if charge.onsite_currency:
        parts.append(f"현장 결제 {charge.onsite_currency}")
    return " · ".join(part for part in parts if part)


def red_lines(plan: Plan) -> list[dict]:
    """고를 빨간 줄 — 규칙마다 칸 수와 고를 수 있는 것, 칸마다 무엇이 어떻게 되는지."""
    out = []
    for rule in RULES.rules:
        waiting = [change for change in plan.changes if change.verdict == rule.code and change.waiting]
        if rule.severity != RED or not waiting:
            continue
        out.append(dict(rule=rule.code, label=rule.label, amounts=len(waiting),
                        choices={choice: CHOICE_LABELS[choice] for choice in rule.choices},
                        examples=[dict(amount=change.id, name=change.label, moves=_moves(plan, change)) for change in waiting]))
    return out


def _moves(plan: Plan, change: AmountChange) -> str:
    charge = plan.charge(change.place.charge)
    return (f"{_value(change.before, change.place, charge, plan.currency)} → "
            f"{_value(change.after, change.place, charge, plan.currency)}")


def chosen_amounts(plan: Plan) -> list[dict]:
    """고른 칸마다 — 고른 것의 이름(`label`)과 그렇게 고르며 담당자가 한 말(`said`)."""
    return [dict(amount=change.id, name=change.label, rule=change.verdict, choice=change.choice,
                 label=CHOICE_LABELS[change.choice], said=change.said) for change in plan.changes if change.choice]


def blocked_amounts(plan: Plan) -> list[dict]:
    out = []
    for change in plan.changes:
        if RULES.severity(change.verdict) != BLOCKED:
            continue
        charge = plan.charge(change.place.charge)
        why = unused(charge, change.place) if change.verdict == "NOT_USED" else None
        if change.verdict == "FORM_REFUSES":
            why = form_refusal(charge, {change.place: change.after})
        out.append(dict(amount=change.id, name=change.label, rule=change.verdict, label=RULES.by_code[change.verdict].label,
                        why=why or ""))
    return out


def free_amounts(plan: Plan) -> list[dict]:
    return [dict(amount=change.id, name=change.label) for change in plan.changes if change.free]


def _verdict_cell(change: AmountChange | None, why: str) -> str:
    if change is None:
        return '<td class="text"><small>그대로 보냄</small></td>'
    rule = RULES.by_code.get(change.verdict)
    if rule is None:
        return f'<td class="text">{"바뀜" if change.writes else "그대로"}</td>'
    if change.choice:
        return f'<td class="text">{esc(rule.label)} <span class="tag chosen">{esc(CHOICE_LABELS[change.choice])}</span></td>'
    if rule.severity == RED:
        return f'<td class="text"><span class="tag red">빨간 줄</span> {esc(rule.label)}</td>'
    return (f'<td class="text"><span class="tag blocked">바꿀 수 없음</span> {esc(rule.label)}'
            f'{f"<small class=more>{esc(why)}</small>" if why else ""}</td>')


def render_preview(plan: Plan, change_id: int | None, steps: Sequence | None, names: Sequence[str] = ()) -> str:
    currency, request = plan.currency, plan.request
    found = counts(plan)
    title = f"미리보기 · {request.hotel} · 부과금"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub"><b>아직 아무것도 바뀌지 않았습니다.</b> 지금 값은 {esc(fmt_time(plan.read_at))} 에 ERP 에서 읽은 것입니다. '
            f"통화 {esc(currency)}. 요청 “{esc(request.sentence)}” → {esc(request.describe())}"
            f'{f" · 장부 {change_id}번" if change_id else ""}</p>']
    if found["red"]:
        body.append(f'<div class="banner red"><b>먼저 골라 주세요 — 빨간 줄 {found["red"]}칸.</b> 칸마다 "이대로 바꿈" 또는 '
                    "\"그 칸은 안 바꿈\"을 말씀해 주시면 다시 계산합니다.</div>")
    if found["blocked"]:
        body.append(f'<div class="banner amber"><b>바꿀 수 없는 칸 {found["blocked"]}칸</b>은 그대로 둡니다(아래 표의 까닭).</div>')
    free = [change.label for change in plan.changes if change.free]
    if free:
        body.append(f'<div class="banner amber"><b>무료가 됩니다 — {len(free)}칸.</b> {esc(" · ".join(free))} 은(는) 저장하면 '
                    "0 이 되어 손님이 내는 금액이 없어집니다.</div>")
    body.append(names_banner(names))
    sent = 0
    by_place = {change.place: change for change in plan.changes}
    tables = []
    for charge in plan.charges:
        rows = []
        for place in charge.places():
            change = by_place.get(place)
            before = charge.value(place)
            if change is None and before is None:
                continue
            name = (f'<td class="text">{esc(charge.part_label(place.part, place.at).removeprefix(charge.label).strip(" ·") or "부과금")}'
                    f' · {esc(place.field_label)}</td>')
            if change is None:
                sent += 1
                why = unused(charge, place)
                rows.append(f'<tr>{name}<td class="same"><span class="was">{_value(before, place, charge, currency)}</span></td>'
                            f'<td class="text"><small>{"쓰이지 않는 값 · " if why else ""}그대로 보냄</small></td></tr>')
                continue
            severity = RULES.severity(change.verdict)
            shown = change.after if change.writes or change.waiting or severity == BLOCKED else None
            cls = ("blocked" if severity == BLOCKED else "chosen" if change.choice else "red" if severity == RED
                   else "same" if shown is None or shown == before else "")
            why = unused(charge, place) if change.verdict == "NOT_USED" else ""
            if change.verdict == "FORM_REFUSES":
                why = form_refusal(charge, {place: change.after}) or ""
            rows.append(f'<tr>{name}<td class="{cls}">{_move(before, shown, place, charge, currency)}</td>'
                        f"{_verdict_cell(change, why)}</tr>")
        tables += [f"<h2>{esc(charge.label)} <small class=\"sub\">부과금 {esc(charge.id)}번</small></h2>",
                   f'<p class="sub">{esc(_shape(charge))}</p>',
                   '<div class="scroll"><table><tr><th>금액 칸</th><th>전 → 후</th><th>판정</th></tr>'
                   f'{"".join(rows)}</table></div>']
    body.append(stats([(found["will_change"], "바뀌는 칸"), (found["unchanged"], "그대로인 칸"), (found["blocked"], "바꿀 수 없는 칸"),
                       (found["red"], "고를 빨간 줄")] + ([(found["missing"], "목록에 없는 부과금")] if found["missing"] else [])
                      + [(sent, "짚지 않아 그대로 보내는 금액 칸")]))
    body += tables
    for offer, charge_id in plan.missing:
        body.append(f'<p class="sub">부과금 {esc(charge_id)}번(오퍼 {esc(offer)}) — 목록에 없습니다. 지워졌거나 번호가 바뀌었습니다. 바꾸지 않습니다.</p>')
    said = [KEPT_NOTE, REBUILT_NOTE, GUEST_NOTE]
    if any(name.startswith("scope_") for charge in plan.charges for name, _text in charge.form):
        said.insert(2, SCOPE_NOTE)
    body.append(notes(said))
    if steps is None:
        body.append('<div class="banner red">아직 적용할 수 없습니다. 먼저 빨간 줄을 골라 주세요.</div>')
    elif not steps:
        body.append('<div class="banner blue"><b>저장할 것이 없습니다.</b> 바뀌는 칸이 없어 적용할 것이 없습니다.</div>')
    else:
        body.append(f'<div class="banner blue">저장 {times_word(len(steps))}{"(부과금마다 한 번)" if len(steps) > 1 else ""}. 맞으면 "적용"이라고 해 주세요.</div>')
    return page(title, "\n".join(body), MAKER)


def render_result(record: ChangeRecord, moved: Sequence = (), ledger_path: str | None = None, names: Sequence[str] = ()) -> str:
    """장부의 변경 하나의 결과 — 칸마다 넣은 값과 다시 읽어 맞았는지. `moved` 는 그대로여야 할 칸이 달라진 것(verify 의 답)."""
    currency = record.currency
    rollback = record.kind == "rollback"
    name = "되돌리기 결과" if rollback else "적용 결과"
    title = f"{name} · {record.hotel} · 부과금"
    written = [row for row in record.rows if row.written and row.action and not row.rolled_back_by]
    mismatched = [row for row in written if record.verified_at and not row.verified]
    waiting = [row for row in record.rows if row.action and not row.written]
    stop = stop_view(record)   # 멈춘 뒤 다시 읽어 보니 남은 저장의 칸이 미리보기 때와 달라진 것 — 지금 값
    moved_now = {key: now for (kind, key), now in (stop[1].moved.items() if stop and stop[1] else ()) if kind == ITEM_KIND}
    changed_since = [row for row in waiting if row.item_key in moved_now]
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">장부 {record.id}번 · 요청 “{esc(record.sentence)}”'
            f'{f" · {record.reverses}번 변경을 되돌림" if record.reverses else ""} · 통화 {esc(currency)}</p>',
            result_banner(record, len(written), len(mismatched) + len(moved), UNIT), names_banner(names)]
    if moved:
        body.append('<div class="banner red"><b>그대로여야 할 칸이 달라졌습니다.</b> '
                    + esc(" · ".join(f"{item['label']} {item['what']}" for item in moved)) + "</div>")
    body += [steps_list(record.steps, None, UNIT), stopped_choices(record, len(waiting), UNIT),
             chosen_table([(RULES.by_code[verdict].label if verdict in RULES.by_code else str(verdict), CHOICE_LABELS[choice],
                            len(keys), said) for verdict, choice, said, keys in chosen_groups(record.rows)], UNIT)]
    rows = []
    for row in record.rows:
        charge, part, at = part_of_key(row.item_key)
        place = Place(charge, part, at, row.field)
        if not row.action:
            if row.before is None:
                continue
            cell = f'<td class="same">{_move(row.before, None, place, None, currency)}</td>'
        elif row.rolled_back_by:
            cell = f'<td class="same">{_move(row.before, row.after, place, None, currency)}<span class="tag closed">되돌림 · 장부 {row.rolled_back_by}번</span></td>'
        elif not row.written and row.item_key in moved_now:
            now = moved_now[row.item_key]
            shown = ("지금 칸 없음" if now is None or now.state == "missing"
                     else f"지금 {_value(now.fields.get(row.field), place, None, currency)}")
            cell = (f'<td class="red"><span class="was">미리보기 때 {_value(row.before, place, None, currency)}</span> '
                    f'<b class="now">{shown}</b>{MOVED_TAG}</td>')
        elif not row.written:
            cell = f'<td class="wait">{_move(row.before, row.after, place, None, currency)}<span class="tag wait">아직 저장 안 함</span></td>'
        elif record.verified_at and not row.verified:
            cell = (f'<td class="red">{_move(row.before, row.after, place, None, currency)}'
                    f'<small class="more">다시 읽은 값 {_value(row.seen, place, None, currency)}</small></td>')
        else:
            tag = '<span class="tag ok">확인</span>' if row.verified and record.verified_at else '<span class="tag ok">저장함</span>'
            cell = f"<td>{_move(row.before, row.after, place, None, currency)}{tag}</td>"
        rows.append(f'<tr><td class="text">{esc(row.label)} · {esc(FIELD_LABELS[(part, row.field)])}'
                    f'<small class="more">부과금 {esc(charge)}번</small></td>{cell}</tr>')
    body += ["<h2>칸마다 넣은 값</h2>",
             f'<p class="sub">{esc(moved_sentence(record, len(changed_since), UNIT))}</p>' if changed_since else "",
             f'<div class="scroll"><table><tr><th>금액 칸</th><th>전 → 후</th></tr>{"".join(rows)}</table></div>']
    if nothing_left(record):   # ERP 에 이 변경의 값이 하나도 없다 — 손님 화면 · 되돌리는 법은 말하지 않는다
        body.append(notes([f"기록: {ledger_path}"]) if ledger_path else "")
    elif record.status in ("applied", "stopped"):
        said = [GUEST_NOTE, UNDO_ONCE if record.kind == "rollback"
                else f'되돌리려면 대화창에서 "{record.id}번 되돌려" 또는 "방금 것 되돌려"라고 하세요.']
        if ledger_path:
            said.insert(1, f"기록: {ledger_path}")
        body.append(notes(said))
    return page(title, "\n".join(body), MAKER)


def render_rollback(plan: RollbackPlan, scope: str = "") -> str:
    currency = plan.currency
    title = f"되돌리기 미리보기 · {plan.hotel} · 부과금"
    rows = []
    for item in plan.restored:
        charge, part, at = part_of_key(item.key)
        for field_name, target in item.targets.items():
            place = Place(charge, part, at, field_name)
            rows.append(f'<tr><td class="text">{esc(item.label)} · {esc(FIELD_LABELS[(part, field_name)])}'
                        f'<small class="more">부과금 {esc(charge)}번</small></td>'
                        f"<td>{_move(item.now.fields.get(field_name), target, place, None, currency)}</td></tr>")
    body = [f"<h1>{esc(title)}</h1>", rollback_head(plan, scope),
            stats([(len(plan.restored), "되돌리는 칸"),
                   (0 if plan.include_kept else len(plan.kept), "그대로 두는 것")]),
            kept_table(plan, ROLLBACK_LABELS), unremovable_table(plan, ROLLBACK_LABELS, UNIT),
            "<h2>되돌리는 칸 — 지금 값 → 적어 둔 값</h2>",
            (f'<div class="scroll"><table><tr><th>금액 칸</th><th>지금 → 적어 둔 값</th></tr>{"".join(rows)}</table></div>'
             if rows else '<p class="sub">되돌릴 칸이 없습니다.</p>'),
            notes([REBUILT_NOTE]), rollback_ask(plan, KEEPS, UNIT)]
    return page(title, "\n".join(body), MAKER)


def _held(value: Decimal | None, place: Place, charge: Charge, currency: str) -> str:
    """편집 창의 금액 칸 하나를 창의 말로 — 빈 칸은 「미정」 · 「성인가와 같음」 · 「현장 금액 미정」."""
    if value is not None:
        return _value(value, place, charge, currency)
    if place.part == AGE:
        return "성인가와 같음" if place.field == "amount" else "현장 금액 미정"
    return "현장 금액 미정" if place.field == "onsite" else "미정"


def render_window(snapshot: Snapshot) -> str:
    """부과금 설정 — 읽은 부과금마다 편집 창의 칸 전부(창이 보인 그대로). 아무것도 바꾸지 않았다. 도우미가 바꾸는 것은 금액 칸뿐이다."""
    currency = snapshot.currency
    title = f"부과금 설정 · {snapshot.hotel}"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">{esc(fmt_time(snapshot.read_at))} 에 ERP 편집 창에서 읽었습니다. 아무것도 바꾸지 않았습니다. '
            "도우미가 바꿀 수 있는 것은 금액 칸뿐이고, 나머지 칸은 ERP 화면에서 사람이 바꿉니다.</p>"]
    for charge in snapshot.charges.values():
        labels = charge.labels
        dates = charge.one("date_scope").strip()
        settings = [("종류", labels.get("kind", "")), ("이름", charge.name), ("부과 방식", labels.get("basis", "")),
                    ("부과 단위", labels.get("per", "")),
                    ("의무 · 선택", ("의무 — " + (dates or "오퍼 전 기간")) if charge.one("date_mode") == "mandatory" else "선택"),
                    ("적용 룸 · 적용 범위", charge.listed.scope or "—"), ("현장 결제 통화", charge.onsite_currency or "없음"),
                    ("설명", "\n".join(text for _name, text in charge.form if _name == "description").strip() or "없음")]
        amounts = []
        for place in charge.places():
            why = unused(charge, place)
            amounts.append(f'<tr><td class="text">{esc(charge.part_label(place.part, place.at).removeprefix(charge.label).strip(" ·") or "부과금")}'
                           f' · {esc(place.field_label)}</td><td class="text">{esc(_held(charge.value(place), place, charge, currency))}</td>'
                           f'<td class="text">{esc(why) if why else "쓰임"}</td></tr>')
        body += [f"<h2>{esc(charge.label)} <small class=\"sub\">부과금 {esc(charge.id)}번</small></h2>",
                 '<div class="scroll"><table><tr><th>칸</th><th>지금 값</th></tr>'
                 + "".join(f'<tr><td class="text">{esc(name)}</td><td class="text">{esc(value)}</td></tr>' for name, value in settings)
                 + "</table></div>",
                 '<div class="scroll"><table><tr><th>금액 칸</th><th>지금 값</th><th>계산에</th></tr>' + "".join(amounts) + "</table></div>"]
    for offer, charge_id in snapshot.missing():
        body.append(f'<p class="sub">부과금 {esc(charge_id)}번(오퍼 {esc(offer)}) — 목록에 없습니다. 지워졌거나 번호가 바뀌었습니다.</p>')
    return page(title, "\n".join(body), MAKER)


def render_prices(listing: Listing) -> str:
    """지금 부과금 — 호텔의 오퍼마다 부과금 전부, 목록이 보인 그대로. 아무것도 바꾸지 않았다."""
    title = f"지금 부과금 · {listing.hotel}"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">{esc(fmt_time(listing.read_at))} 에 ERP 에서 읽었습니다. 아무것도 바꾸지 않았습니다.</p>',
            stats([(len(listing.offers), "오퍼"), (len(listing.charges), "부과금")])]
    for offer_id, offer_name in listing.offers:
        mine = [item for item in listing.charges if item.offer == offer_id]
        rows = "".join(f'<tr><td class="text">{esc(item.name)}<small class="more">부과금 {esc(item.id)}번</small></td>'
                       f'<td class="text">{esc(item.kind)}</td><td class="text">{esc(item.basis)}</td>'
                       f'<td class="text">{"<br>".join(esc(line) for line in item.amount)}</td>'
                       f'<td class="text">{esc(item.dates)}</td></tr>' for item in mine)
        body += [f"<h2>{esc(offer_name)} <small class=\"sub\">오퍼 {esc(offer_id)}번</small></h2>",
                 (f'<div class="scroll"><table><tr><th>부과금</th><th>종류</th><th>부과 방식</th><th>금액</th><th>적용 날짜</th></tr>'
                  f"{rows}</table></div>" if mine else '<p class="sub">부과금이 없습니다.</p>')]
    if listing.charges:      # 보기는 퍼센트로 — 부과금마다 통화가 다를 수 있다
        body.append(notes([f'바꾸고 싶으면 대화창에서 "{listing.charges[0].name} 10% 올려줘" 처럼 말씀해 주세요. 바꾸기 전에 미리보기를 먼저 보여 드립니다.']))
    return page(title, "\n".join(body), MAKER)
