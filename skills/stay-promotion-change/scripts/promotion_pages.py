"""promotion_pages.py — 프로모션 할인 도우미의 페이지(HTML): 지금 프로모션 · 프로모션 설정(편집 창 전부) · 미리보기 · 적용 결과 · 되돌리기
미리보기.

페이지 틀(색 · 머리 숫자 · 저장 단계 목록 · 결과 띠 · 멈춤 선택지 · 되돌리기 머리 · 그대로 두는 것 표)은 change_core.chrome 이다.
여기에는 프로모션마다의 단 표와 이 종류만의 안내(표식 없는 ERP · 화면 밖 설정 · 손님에게 닿는 것 · 적용 범위 기록)를 둔다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from promotion_model import (
    BASES, COMMON, GATE, ITEM_KIND, TRIGGERS, UNITS, Listing, Promotion, Snapshot, off_words, part_of_key, promotion_of_key,
)
from promotion_plan import CHOICE_LABELS, RULES, Plan, TierChange, counts, form_refusal, typed
from change_core.chrome import (
    MOVED_TAG, chosen_groups, chosen_table, esc, fmt_money, fmt_time, kept_table, moved_sentence, names_banner,
    nothing_left, notes, page, reread, result_banner, result_word, rollback_ask, rollback_head, stats, steps_list, stop_view,
    stopped_choices, times_word, undo_hint, unremovable_table,
)
from change_core.ledger import ChangeRecord
from change_core.rollback import RollbackPlan
from change_core.rules import BLOCKED, RED
from change_core.window import form_values
from change_core.words import josa

MAKER = "어딩 Stay 프로모션 할인 도우미"
UNIT = "단"
KEPT_NOTE = ("저장은 프로모션마다 한 번이고, 편집 창의 다른 칸(제목 · 코드 · 발동 조건 · 혜택 방식 · 적용 단위 · 단의 기준값 · 적용 숙박일 · "
             "진행기간 제한과 그 기간 · 시즌 · 요금제 · 중복 · 배타 그룹 · 취소 정책 · 적용 범위)은 창이 보인 그대로 보냅니다. 표의 다른 단도 "
             "그대로 보내고, 단을 더하거나 지우지 않습니다.")
SIDE_NOTE = ("저장하면 ERP 가 화면에 보이지 않는 분류 칸(할인 단위 · 프로모션 종류)을 화면의 값으로 다시 맞춥니다. 화면으로 만든 프로모션은 "
             "이미 같아 바뀌는 것이 없고, 되돌려도 그 칸은 그대로 둡니다.")
SCOPE_NOTE = ("편집 창에 「적용 범위」 칸이 있는 프로모션은, 저장할 때 ERP 가 그 프로모션의 적용 범위 기록이 없으면 하나 만듭니다(값은 지금과 "
              "같은 '기존 범위 그대로'라 손님이 내는 금액은 그대로). 화면에 보이지 않고 되돌려도 없어지지 않습니다.")
OFF_NOTE = "이 단에는 화면에 안 보이는 {what} 붙어 있습니다 — 그대로 둡니다."   # {what} 은 조사까지(josa)
GUEST_TAIL = ("할인은 손님이 이 프로모션을 고를 때만, 객실 요금에만 붙습니다(부과금 · 부가옵션은 그대로). 저장 뒤 새 견적부터 바뀌고 이미 받은 "
              "예약의 금액은 그대로입니다.")
KEEPS = ("이미 받은 예약의 금액은 되돌려도 바뀌지 않습니다.",
         "저장할 때 ERP 가 다시 맞춘 분류 칸과 생긴 적용 범위 기록은 되돌리지 못합니다(할인 값만 되돌립니다).")
ROLLBACK_LABELS = {"value": "할인 값"}


def shown(value: Decimal | None, basis: str, currency: str) -> str:
    """단의 값을 화면의 말로 — 「12.5%」 · 「20.00 USD」 · 「2박」."""
    if value is None:
        return "비어 있음"
    if basis == "PCT":
        return f"{typed(value)}%"
    if basis == "FREE_NIGHT":
        return f"{typed(value)}박"
    return f"{fmt_money(value, currency)} {currency}".strip()


def _move(before, after, basis: str, currency: str) -> str:
    if after is None or before == after:
        return f'<span class="was">{shown(before, basis, currency)}</span><small class="more">그대로</small>'
    zero = '<small class="more"><b>할인이 없어집니다</b></small>' if after == 0 else ""
    return (f'<span class="was">{shown(before, basis, currency)}</span><span class="arrow">→</span>'
            f'<span class="now">{shown(after, basis, currency)}</span>{zero}')


def settings(promotion: Promotion) -> list[tuple[str, str]]:
    """프로모션의 설정 — 도우미가 바꾸지 않고 창이 보인 그대로 보내는 칸을 화면의 말로."""
    get = (lambda name: (form_values(promotion.form, name) or [""])[0].strip())
    labels = promotion.labels
    booking = ((f"켜짐 — {get('promotion_apply_start_date') or '…'} ~ {get('promotion_apply_end_date') or '…'} 에 예약한 건만")
               if form_values(promotion.form, "promotion_apply_flag") else "꺼짐(상시 진행)")
    stay = (f"{get('start_date') or '…'} ~ {get('end_date') or '…'}" if get("start_date") or get("end_date") else "제한 없음")
    return [("카드", promotion.listed.offer_name + (" (모든 오퍼에 붙음)" if promotion.offer == COMMON else "")),
            ("프로모션명", promotion.name), ("코드", promotion.listed.code or "없음"),
            ("발동 조건", labels.get("trigger_type") or TRIGGERS.get(promotion.trigger, promotion.trigger)),
            ("혜택 방식", labels.get("basis") or BASES.get(promotion.basis, promotion.basis)),
            ("적용 단위", labels.get("unit") or UNITS.get(get("unit"), get("unit"))),
            ("적용 숙박일", stay), ("진행기간 제한", booking),
            ("시즌 한정", labels.get("season") or "(전 시즌)"), ("요금제 한정", labels.get("rate_plan") or "(전 요금제)"),
            ("다른 프로모션과 중복", "허용" if form_values(promotion.form, "combinability") else "택일"),
            ("배타 그룹", get("exclusivity_group") or "없음"),
            ("취소 정책", labels.get("cancellation_policy") or "(요금제·오퍼 정책을 따름)")]


def _settings_table(promotion: Promotion) -> str:
    return ('<div class="scroll"><table><tr><th>그대로 보내는 설정</th><th>창의 값</th></tr>'
            + "".join(f'<tr><td class="text">{esc(name)}</td><td class="text">{esc(value)}</td></tr>'
                      for name, value in settings(promotion)) + "</table></div>")


def _shape(promotion: Promotion) -> str:
    return " · ".join(part for part in (TRIGGERS.get(promotion.trigger, ""), BASES.get(promotion.basis, ""),
                                        UNITS.get((form_values(promotion.form, "unit") or [""])[0], "")) if part)


def off_notes(promotion: Promotion) -> list[str]:
    """화면 밖 설정이 붙은 단마다 한 문장 — 「이 단에는 화면에 안 보이는 취소 조건이 붙어 있습니다 — 그대로 둡니다」."""
    return [f"{promotion.threshold_words(tier)} 단: " + OFF_NOTE.format(what=josa(off_words(tier.off), "이가"))
            for tier in promotion.tiers() if tier.off]


def kept_off(then: Snapshot, now: Snapshot, saved: Sequence[str], moved: Sequence[dict]) -> list[str]:
    """저장한 프로모션 가운데 그대로여야 할 것이 달라지지 않은 것(verify 의 `moved` 에 없음)의, 화면 밖 설정이 붙은 단마다 한 문장 —
    「…단: 화면에 안 보이는 취소 조건은 저장 뒤에도 그대로입니다」. verify 가 견준 것(표식 — 화면 밖 설정의 이름 — 은 `moved` 가 본다)
    에서 말한다. 그 번호의 읽은 값(`then`)과 방금 읽은 값(`now`) 둘 다에 그 단의 설정이 있을 때만."""
    touched = {promotion_of_key(item["key"]) for item in moved}
    out = []
    for promotion_id in sorted(set(saved)):
        before, after = then.promotions.get(promotion_id), now.promotions.get(promotion_id)
        if before is None or after is None or promotion_id in touched:
            continue
        was = {tier.at: tier.off for tier in before.tiers() if tier.off}
        out += [f"{after.threshold_words(tier)} 단: 화면에 안 보이는 {josa(off_words(tier.off), '은는')} 저장 뒤에도 그대로입니다."
                for tier in after.tiers() if tier.off and was.get(tier.at) == tier.off]
    return out


def guest_effect(plan: Plan) -> str:
    """손님에게 닿는 것 한 문장 — 할인이 커지면 손님이 내는 객실 요금이 줄고, 작아지면 는다. 새 견적부터, 기존 예약은 그대로."""
    moves = {change.larger for change in plan.changes if change.larger is not None}
    if moves == {True}:
        head = "할인이 커져, 이 프로모션을 고른 손님이 내는 객실 요금이 줄어듭니다."
    elif moves == {False}:
        head = "할인이 줄어, 이 프로모션을 고른 손님이 내는 객실 요금이 늘어납니다."
    elif moves:
        head = "할인이 커지는 단은 손님이 내는 객실 요금이 줄고, 줄어드는 단은 늘어납니다."
    else:
        return ""
    return f"{head} {GUEST_TAIL}"


def red_lines(plan: Plan) -> list[dict]:
    """고를 빨간 줄 — 규칙마다 단 수와 고를 수 있는 것, 단마다 무엇이 어떻게 되는지."""
    out = []
    for rule in RULES.rules:
        waiting = [change for change in plan.changes if change.verdict == rule.code and change.waiting]
        if rule.severity != RED or not waiting:
            continue
        out.append(dict(rule=rule.code, label=rule.label, tiers=len(waiting),
                        choices={choice: CHOICE_LABELS[choice] for choice in rule.choices},
                        examples=[dict(tier=change.id, name=change.label, moves=_moves(plan, change)) for change in waiting]))
    return out


def _moves(plan: Plan, change: TierChange) -> str:
    promotion = plan.promotion(change.promotion)
    currency = promotion.currency or plan.currency
    return f"{shown(change.before, promotion.basis, currency)} → {shown(change.after, promotion.basis, currency)}"


def chosen_tiers(plan: Plan) -> list[dict]:
    """고른 단마다 — 고른 것의 이름(`label`)과 그렇게 고르며 담당자가 한 말(`said`)."""
    return [dict(tier=change.id, name=change.label, rule=change.verdict, choice=change.choice,
                 label=CHOICE_LABELS[change.choice], said=change.said) for change in plan.changes if change.choice]


def _why(plan: Plan, change: TierChange) -> str:
    if change.verdict == "FORM_REFUSES":
        return form_refusal(plan.promotion(change.promotion), {change.tier: change.after}) or ""
    return ""


def blocked_tiers(plan: Plan) -> list[dict]:
    return [dict(tier=change.id, name=change.label, rule=change.verdict, label=RULES.by_code[change.verdict].label,
                 why=_why(plan, change)) for change in plan.changes if RULES.severity(change.verdict) == BLOCKED]


def _verdict_cell(change: TierChange | None, why: str) -> str:
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


def _tier_table(plan: Plan, promotion: Promotion) -> str:
    """프로모션 하나의 단 표 — 짚지 않은 단은 「그대로 보냄」(그 수는 counts 의 `sent`)."""
    currency = promotion.currency or plan.currency
    mine = {change.tier: change for change in plan.changes if change.promotion == promotion.id}
    rows = []
    for tier in promotion.tiers():
        change, before = mine.get(tier.at), promotion.value(tier)
        off = f'<small class="more">화면 밖 설정: {esc(off_words(tier.off))} — 그대로 둠</small>' if tier.off else ""
        name = f'<td class="text">{esc(promotion.threshold_words(tier))} 단 · {esc(promotion.field_label)}{off}</td>'
        if change is None:
            rows.append(f'<tr>{name}<td class="same"><span class="was">{shown(before, promotion.basis, currency)}</span></td>'
                        '<td class="text"><small>그대로 보냄</small></td></tr>')
            continue
        severity = RULES.severity(change.verdict)
        after = change.after if change.writes or change.waiting or severity == BLOCKED else None
        cls = ("blocked" if severity == BLOCKED else "chosen" if change.choice else "red" if severity == RED
               else "same" if after is None or after == before else "")
        rows.append(f'<tr>{name}<td class="{cls}">{_move(before, after, promotion.basis, currency)}</td>'
                    f"{_verdict_cell(change, _why(plan, change))}</tr>")
    return '<div class="scroll"><table><tr><th>단</th><th>전 → 후</th><th>판정</th></tr>' + "".join(rows) + "</table></div>"


def render_preview(plan: Plan, change_id: int | None, steps: Sequence | None, names: Sequence[str] = ()) -> str:
    request = plan.request
    found = counts(plan)
    title = f"미리보기 · {request.hotel} · 프로모션 할인"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub"><b>아직 아무것도 바뀌지 않았습니다.</b> 지금 값은 {esc(fmt_time(plan.read_at))} 에 ERP 에서 읽은 것입니다. '
            f"요청 “{esc(request.sentence)}” → {esc(request.describe())}{f' · 장부 {change_id}번' if change_id else ''}</p>"]
    if plan.unmarked:
        body.append(f'<div class="banner red"><b>{esc(GATE)}.</b> 계산은 보여 드리지만 저장하지 않습니다: '
                    f'{esc(" · ".join(promotion.label for promotion in plan.unmarked))}</div>')
    if found["red"]:
        body.append(f'<div class="banner red"><b>먼저 골라 주세요 — 빨간 줄 {found["red"]}단.</b> 단마다 "이대로 바꿈" 또는 '
                    "\"그 단은 안 바꿈\"을 말씀해 주시면 다시 계산합니다.</div>")
    if found["blocked"] - found["NO_MARK"]:
        body.append(f'<div class="banner amber"><b>바꿀 수 없는 단 {found["blocked"] - found["NO_MARK"]}단</b>은 그대로 둡니다(아래 표의 까닭).</div>')
    zero = [change.label for change in plan.changes if change.writes and change.after == 0]
    if zero:
        body.append(f'<div class="banner amber"><b>할인이 없어집니다 — {len(zero)}단.</b> {esc(" · ".join(zero))}</div>')
    body.append(names_banner(names))
    tables = []
    for promotion in plan.promotions:
        table = _tier_table(plan, promotion)
        offs = off_notes(promotion)
        tables += [f"<h2>{esc(promotion.label)} <small class=\"sub\">프로모션 {esc(promotion.id)}번</small></h2>",
                   f'<p class="sub">{esc(_shape(promotion))}</p>', table,
                   (f'<div class="banner amber">{"<br>".join(esc(line) for line in offs)}</div>' if offs else ""),
                   _settings_table(promotion)]
    body.append(stats([(found["will_change"], "바뀌는 단"), (found["unchanged"], "그대로인 단"), (found["blocked"], "바꿀 수 없는 단"),
                       (found["red"], "고를 빨간 줄")] + ([(found["missing"], "목록에 없는 프로모션")] if found["missing"] else [])
                      + [(found["sent"], "짚지 않아 그대로 보내는 단")]))
    body += tables
    for offer, promotion_id in plan.missing:
        body.append(f'<p class="sub">프로모션 {esc(promotion_id)}번(오퍼 {esc(offer)}) — 목록에 없습니다. 지워졌거나 번호가 바뀌었습니다. 바꾸지 않습니다.</p>')
    said = [KEPT_NOTE, SIDE_NOTE] + ([guest_effect(plan)] if guest_effect(plan) else [])
    if any(name.startswith("scope_") for promotion in plan.promotions for name, _text in promotion.form):
        said.insert(2, SCOPE_NOTE)
    if steps is None or steps:   # 저장할 것이 없으면(표식 없는 ERP · 고른 대로면 바뀌는 단이 없음) 저장이 하는 일을 말하지 않는다
        body.append(notes(said))
    if steps is None:
        body.append('<div class="banner red">아직 적용할 수 없습니다. 먼저 빨간 줄을 골라 주세요.</div>')
    elif not steps and plan.unmarked:
        body.append(f'<div class="banner red"><b>저장하지 않습니다.</b> {esc(GATE)}.</div>')
    elif not steps:
        body.append('<div class="banner blue"><b>저장할 것이 없습니다.</b> 바뀌는 단이 없어 적용할 것이 없습니다.</div>')
    else:
        body.append(f'<div class="banner blue">저장 {times_word(len(steps))}{"(프로모션마다 한 번)" if len(steps) > 1 else ""}. 맞으면 "적용"이라고 해 주세요.</div>')
    return page(title, "\n".join(body), MAKER)


def result_name(record: ChangeRecord) -> str:
    """결과 페이지의 이름(제목과 파일 이름) — 「적용 결과」 · 「되돌리기 결과」, 멈췄으면 「…하다 멈춤」(chrome.result_word)."""
    return result_word(record, record.kind == "rollback")


def _row_value(value, record: ChangeRecord) -> str:
    return "비어 있음" if value is None else typed(value)


def render_result(record: ChangeRecord, moved: Sequence = (), ledger_path: str | None = None, names: Sequence[str] = (),
                  kept: Sequence[str] = ()) -> str:
    """장부의 변경 하나의 결과 — 단마다 넣은 값과 다시 읽어 맞았는지. `moved` 는 그대로여야 할 것이 달라진 것, `kept` 는 화면 밖 설정이
    저장 뒤에도 그대로인 단의 문장(verify 의 답 — kept_off)."""
    title = f"{result_name(record)} · {record.hotel} · 프로모션 할인"
    written = [row for row in record.rows if row.written and row.action and not row.rolled_back_by]
    mismatched = [row for row in written if record.verified_at and not row.verified]
    waiting = [row for row in record.rows if row.action and not row.written]
    stop = stop_view(record)
    moved_now = {key: now for (kind, key), now in (stop[1].moved.items() if stop and stop[1] else ()) if kind == ITEM_KIND}
    changed_since = [row for row in waiting if row.item_key in moved_now]
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">장부 {record.id}번 · 요청 “{esc(record.sentence)}”'
            f'{f" · {record.reverses}번 변경을 되돌림" if record.reverses else ""}</p>',
            result_banner(record, len(written), len(mismatched) + len(moved), UNIT), names_banner(names)]
    if moved:
        body.append('<div class="banner red"><b>그대로여야 할 것이 달라졌습니다.</b> '
                    + esc(" · ".join(f"{item['label']} {item['what']}" for item in moved)) + "</div>")
    body += [steps_list(record.steps, None, UNIT), stopped_choices(record, len(waiting), UNIT),
             chosen_table([(RULES.by_code[verdict].label if verdict in RULES.by_code else str(verdict), CHOICE_LABELS[choice],
                            len(keys), said) for verdict, choice, said, keys in chosen_groups(record.rows)], UNIT)]
    rows = []
    for row in record.rows:
        promotion, _tier = part_of_key(row.item_key)
        move = (lambda before, after: f'<span class="was">{_row_value(before, record)}</span>'
                + ("" if after is None or after == before else f'<span class="arrow">→</span><span class="now">{_row_value(after, record)}</span>'))
        if not row.action:
            if row.before is None:
                continue
            cell = f'<td class="same">{move(row.before, None)}<small class="more">그대로</small></td>'
        elif row.rolled_back_by:
            cell = f'<td class="same">{move(row.before, row.after)}<span class="tag closed">되돌림 · 장부 {row.rolled_back_by}번</span></td>'
        elif not row.written and row.item_key in moved_now:   # 그때 읽은 값 — 지금 값이라고 하지 않는다(chrome.reread)
            now = moved_now[row.item_key]
            if now is None or now.state == "missing":
                said = f'<b class="now">{reread(record)} 단 없음</b>'
            else:
                said = (f'<span class="was">미리보기 때 {_row_value(row.before, record)}</span> · '
                        f'<b class="now">{reread(record)} {_row_value(now.fields.get(row.field), record)}</b>')
            cell = f'<td class="red">{said}{MOVED_TAG}</td>'
        elif not row.written:
            cell = f'<td class="wait">{move(row.before, row.after)}<span class="tag wait">아직 저장 안 함</span></td>'
        elif record.verified_at and not row.verified:
            cell = f'<td class="red">{move(row.before, row.after)}<small class="more">다시 읽은 값 {_row_value(row.seen, record)}</small></td>'
        else:
            tag = '<span class="tag ok">확인</span>' if row.verified and record.verified_at else '<span class="tag ok">저장함</span>'
            cell = f"<td>{move(row.before, row.after)}{tag}</td>"
        rows.append(f'<tr><td class="text">{esc(row.label)}<small class="more">프로모션 {esc(promotion)}번</small></td>{cell}</tr>')
    body += ["<h2>단마다 넣은 값</h2>",
             f'<p class="sub">{esc(moved_sentence(record, len(changed_since), UNIT))}</p>' if changed_since else "",
             f'<div class="scroll"><table><tr><th>단</th><th>전 → 후</th></tr>{"".join(rows)}</table></div>']
    if nothing_left(record):
        body.append(notes([f"기록: {ledger_path}"]) if ledger_path else "")
    elif record.status in ("applied", "stopped"):
        tail = (("되돌린 할인 값은 저장 뒤 새 견적부터 붙습니다" if record.kind == "rollback" else "저장 뒤 새 견적부터 새 할인으로 바뀝니다")
                + "(손님이 이 프로모션을 고를 때만, 객실 요금에만). 이미 받은 예약의 금액은 바뀌지 않습니다.")
        if stop is None:
            said = [*kept, tail, undo_hint(record)]
        else:   # 멈췄다 — 되돌리는 법은 위의 「어떻게 할까요?」가 말한다
            said = [f"저장한 {len(written):,}단만 새 할인입니다. {tail}"]
        if ledger_path:   # 되돌리는 법 앞에
            said.insert(len(said) - 1 if stop is None else len(said), f"기록: {ledger_path}")
        body.append(notes(said))
    return page(title, "\n".join(body), MAKER)


def render_rollback(plan: RollbackPlan, now: Snapshot, scope: str = "") -> str:
    title = f"되돌리기 미리보기 · {plan.hotel} · 프로모션 할인"
    rows = []
    for item in plan.restored:
        promotion_id, _tier = part_of_key(item.key)
        promotion = now.promotions.get(promotion_id)
        basis, currency = (promotion.basis, promotion.currency or plan.currency) if promotion else ("", plan.currency)
        rows.append(f'<tr><td class="text">{esc(item.label)}<small class="more">프로모션 {esc(promotion_id)}번</small></td>'
                    f"<td>{_move(item.now.fields.get('value'), item.targets['value'], basis, currency)}</td></tr>")
    body = [f"<h1>{esc(title)}</h1>", rollback_head(plan, scope),
            stats([(len(plan.restored), "되돌리는 단"), (0 if plan.include_kept else len(plan.kept), "그대로 두는 것")]),
            kept_table(plan, ROLLBACK_LABELS), unremovable_table(plan, ROLLBACK_LABELS, UNIT),
            "<h2>되돌리는 단 — 지금 값 → 적어 둔 값</h2>",
            (f'<div class="scroll"><table><tr><th>단</th><th>지금 → 적어 둔 값</th></tr>{"".join(rows)}</table></div>'
             if rows else '<p class="sub">되돌릴 단이 없습니다.</p>'),
            rollback_ask(plan, KEEPS, UNIT)]
    return page(title, "\n".join(body), MAKER)


def render_window(snapshot: Snapshot) -> str:
    """프로모션 설정 — 읽은 프로모션마다 편집 창의 칸 전부(창이 보인 그대로)와 단, 화면 밖 설정의 이름. 아무것도 바꾸지 않았다."""
    title = f"프로모션 설정 · {snapshot.hotel}"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">{esc(fmt_time(snapshot.read_at))} 에 ERP 편집 창에서 읽었습니다. 아무것도 바꾸지 않았습니다. '
            "도우미가 바꿀 수 있는 것은 단의 할인 값뿐이고, 나머지 칸은 ERP 화면에서 사람이 바꿉니다.</p>"]
    for promotion in snapshot.promotions.values():
        currency = promotion.currency or snapshot.currency
        tiers = "".join(f'<tr><td class="text">{esc(promotion.threshold_words(tier))} 단</td>'
                        f'<td class="text">{esc(shown(promotion.value(tier), promotion.basis, currency))}</td>'
                        f'<td class="text">{esc(off_words(tier.off)) or "없음"}</td></tr>' for tier in promotion.tiers())
        mark = ("이 ERP 는 화면에 없는 설정을 저장 때 지킵니다 — 도우미가 저장할 수 있습니다." if promotion.keeps else f"{GATE}.")
        body += [f"<h2>{esc(promotion.label)} <small class=\"sub\">프로모션 {esc(promotion.id)}번</small></h2>",
                 f'<p class="sub">{esc(mark)}</p>', _settings_table(promotion),
                 f'<div class="scroll"><table><tr><th>단</th><th>{esc(promotion.field_label)}</th><th>화면 밖 설정</th></tr>{tiers}</table></div>']
    for offer, promotion_id in snapshot.missing():
        body.append(f'<p class="sub">프로모션 {esc(promotion_id)}번(오퍼 {esc(offer)}) — 목록에 없습니다. 지워졌거나 번호가 바뀌었습니다.</p>')
    return page(title, "\n".join(body), MAKER)


def render_prices(listing: Listing) -> str:
    """지금 프로모션 — 호텔의 카드마다(오퍼 · 전 오퍼 공통) 프로모션 전부, 목록이 보인 그대로. 아무것도 바꾸지 않았다."""
    title = f"지금 프로모션 · {listing.hotel}"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">{esc(fmt_time(listing.read_at))} 에 ERP 에서 읽었습니다. 아무것도 바꾸지 않았습니다. 할인은 손님이 그 '
            "프로모션을 고를 때만, 객실 요금에만 붙습니다.</p>",
            stats([(len(listing.offers), "카드"), (len(listing.promotions), "프로모션")])]
    lines = (lambda items: "<br>".join(esc(line) for line in items))
    for offer_id, offer_name in listing.offers:
        mine = [item for item in listing.promotions if item.offer == offer_id]
        rows = "".join(f'<tr><td class="text">{esc(item.title)}{f"<br><small>{esc(item.code)}</small>" if item.code else ""}'
                       f'<small class="more">프로모션 {esc(item.id)}번</small></td><td class="text">{esc(item.trigger)}</td>'
                       f'<td class="text">{lines(item.benefit)}</td><td class="text">{lines(item.combo)}</td>'
                       f'<td class="text">{lines(item.limits)}</td></tr>' for item in mine)
        head = f"오퍼 {esc(offer_id)}번" if offer_id != COMMON else "모든 오퍼에 붙음"
        body += [f"<h2>{esc(offer_name)} <small class=\"sub\">{head}</small></h2>",
                 (f'<div class="scroll"><table><tr><th>프로모션</th><th>발동 조건</th><th>혜택</th><th>중복</th><th>한정</th></tr>'
                  f"{rows}</table></div>" if mine else '<p class="sub">프로모션이 없습니다.</p>')]
    if listing.promotions:
        first = listing.promotions[0]
        body.append(notes([f'바꾸고 싶으면 대화창에서 "{first.label} 할인 2% 포인트 올려줘" 처럼 말씀해 주세요. 바꾸기 전에 미리보기를 '
                           "먼저 보여 드립니다."]))
    return page(title, "\n".join(body), MAKER)
