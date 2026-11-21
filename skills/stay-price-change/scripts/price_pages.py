"""price_pages.py — 가격 칸 페이지. 틀(색·머리 숫자·저장 단계·되돌리기 띠)은 `change_core.chrome` 이 그리고,
여기서는 칸 표(객실·요금제마다 표 하나, 줄은 인원·박수, 열은 날짜 — 그림의 모양 가)와 가격 말을 그린다.

    render_preview(plan)       미리보기 — 칸 표, 빨간 줄·적용할 수 없음 띠, 머리 숫자, 따로 볼 칸
    render_result(record)      적용 결과 — 장부의 변경 하나: 저장 단계마다 된 것·멈춘 것, 다시 읽어 맞았는지
    render_rollback(plan)      되돌리기 미리보기 — 되돌리는 날짜, 그대로 두는 칸의 세 값과 까닭, 되돌리는 칸
    render_prices(snapshot)    지금 가격 보기 — 바꾸지 않고 표로만
    render_compare(comparison) 저장해 둔 상태와 견주기 — 저장해 둔 값 → 지금 값을 칸마다, 바뀐 · 새로 생긴 · 없어진 칸의 수(시즌
                               [가격]을 다시 채운 뒤). 바꾸지 않는다
    render_sheet(check)        요금표를 이렇게 읽었습니다 — 요금표의 모양(객실이 줄, 기간이 열, 칸 안에 인원 · 박수)으로, 셈한 값은
                               셈과 함께. ERP 를 읽기 전에 담당자가 종이와 견준다

날짜 열은 ONE_COLUMN_PER_DATE_UP_TO(7)일까지 날짜마다 하나다(승인된 그림). 그보다 길면 표의 모든 줄이 똑같이 보이는 날끼리 —
떨어져 있어도 — 열 하나를 쓰고, 열 머리에 날 수와 날짜 구간을 모두 적는다. `by_date` 면 길이와 상관없이 날짜마다 열 하나다.

글은 전부 쉬운 한국어이고, 도우미는 이 스킬을 부르는 이름이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Iterable, Mapping, Sequence

from change_core.chrome import (
    MOVED_TAG, UNDO_ONCE, checked_when, chosen_groups, chosen_table, esc, fmt_money, fmt_time, kept_table, moved_sentence, nothing_left,
    notes, page, reread, result_banner, result_word, rollback_ask, rollback_head, stats, steps_list, stop_mode, stop_view,
    stopped_choices,
    unremovable_table,
)
from change_core.files import record_progress
from change_core.ledger import ChangeRecord
from change_core.money import example_step, scale_of
from change_core.rollback import RollbackPlan
from change_core.rules import BLOCKED, RED

from price_model import (
    CELL_RULES, CHOICE_LABELS, CLOSED, FIELD_LABELS, FIELDS, GAP_KINDS, HELD, NEW, RESERVED, SKIP_LABELS, TargetTable, CellChange, CellKey,
    CellValue, ChangeRequest, Gap, ITEM_KIND, Plan, Snapshot, cell_item_key, cell_name, day_label, decode_request, key_of_item, line_label, nights_label,
    occupancy_label, encode_key, occupancy_order, split_occupancy, value_of,
)
from price_compare import MOVED, Comparison, compare_counts
from price_plan import counts, day_runs, days_summary
from price_sheet import CHILD_READINGS, SheetCheck, SheetLine, coverage_counts, line_figures, periods_label, runs_label

MAKER = "어딩 Stay 가격 변경 도우미"
# 요금표로 날짜별 가격을 맞춘 미리보기 · 결과가 꼭 다는 한 문장(결정 32). SKILL.md 도 도우미가 이 문장 그대로 말하게 한다.
SEASON_REFILL_NOTE = ("여기서 날짜별로 바꾼 가격은 누가 ERP 시즌 화면에서 그 시즌의 [가격]을 '덮기'(이미 값이 있는 날도 덮기)로 "
                      "다시 채우면 옛 요금으로 돌아갑니다.")
ONE_COLUMN_PER_DATE_UP_TO = 7        # 날짜가 이만큼까지는 날짜마다 열 하나. 넘으면 칸이 모두 같은 날끼리 열 하나(결정 33A)
# 미리보기 안내 — 그런 칸이 있을 때만 단다
RESERVED_NOTE = "예약 있는 날도 똑같이 바꿉니다. 이미 받은 예약의 금액은 바뀌지 않습니다."
CLOSED_NOTE = "판매 마감인 날은 값만 바뀌고 마감은 그대로입니다."
# 되돌려도 그대로인 것 — 되돌리기 미리보기의 끝에 단다(chrome.rollback_ask)
ROLLBACK_KEEPS = ("이미 받은 예약의 금액은 되돌려도 바뀌지 않습니다.", "판매 마감·판매 가능 상태는 되돌리지 않고 값만 되돌립니다.",
                  "ERP 의 '손입력' 표시는 되돌리지 않습니다 — 도우미가 읽지도 되돌리지도 못합니다.")
# 결과 페이지의 값 출처 표시 — 도우미가 넣은 칸은 ERP 가 「손입력」으로 단다. 도우미는 그 표시를 읽지도 되돌리지도 못한다
MARK = "이 칸들은 ERP 에서 '손입력'으로 표시됩니다."
MARK_ON_ROLLBACK = "되돌린 칸도 ERP 에서 '손입력'으로 표시됩니다. 이 표시는 도우미가 읽지도 되돌리지도 못해, 넣기 전의 표시로 돌아가지 않습니다."
# 저장해 둔 상태로 되돌리기가 더 다는 것 — 시즌 [가격]을 다시 채운 뒤에 되돌릴 때 담당자가 알아야 할 것(sheet.md (가))
SEASON_SCREEN_NOTE = ("ERP 시즌 화면은 건드리지 않습니다. 그 사이 시즌의 [가격]을 다시 채웠다면 시즌 창에는 다시 채운 입력값이 그대로 "
                      "보이고, 캘린더의 날짜별 값만 저장해 둔 값으로 돌아갑니다.")
# 저장해 둔 상태와 견주기 — 읽은 값이 가려내지 못하는 것
HAND_EDITS = "ERP 의 '손입력' 표시는 도우미가 읽지 못해, ERP 화면에서 사람이 직접 고쳤던 칸이 덮였는지는 가려내지 못합니다."


def _short_day(day: str) -> str:
    return f"{int(day[5:7])}/{int(day[8:10])}"


def _ranges(days: Sequence[str], weekdays: bool) -> str:
    """날짜 → "12/4 금 ~ 12/5 토, 12/11 ~ 12/12" — 모든 날을 이어진 구간으로. 요일은 구간이 셋까지면 모두, 넘으면 첫 구간만."""
    runs = day_runs(days)
    parts = []
    for index, run in enumerate(runs):
        label = day_label if weekdays and (len(runs) <= 3 or index == 0) else _short_day
        parts.append(label(run[0]) if len(run) == 1 else f"{label(run[0])} ~ {label(run[-1])}")
    return ", ".join(parts)


def grid(keys: Iterable[CellKey], cell: Callable[[CellKey], tuple[str, str]], reserved: set, closed: set,
         by_date: bool = False) -> str:
    """객실·요금제마다 표 하나 — 줄은 인원·박수, 열은 날짜. `cell` 은 `(td 모양 이름, 안쪽 HTML)` 을 돌려준다.

    날짜가 ONE_COLUMN_PER_DATE_UP_TO 보다 많으면(그리고 `by_date` 가 아니면) 모든 줄의 칸이 똑같이 그려지는 날끼리 열 하나를
    쓴다(값 · 마감 · 빨간 줄 · 새 칸 같은 표시까지 같아야 한다). 열은 첫 날 차례이고, 머리에 날 수와 그 열의 날짜 구간을 모두
    적어 어느 날이든 꼭 한 열에서 찾힌다. 예약 있는 날은 열을 가르지 않는다 — 머리에 그 날들을 적는다. 마감은 그 열이 모두
    마감이면 머리에, 아니면 그 칸에 단다.
    """
    groups: dict[tuple[str, str], list[CellKey]] = {}
    for key in keys:
        groups.setdefault((key.room, key.rate_plan), []).append(key)
    out = []
    for (room, plan), members in groups.items():
        present = set(members)
        days = sorted({key.date for key in members})
        lines = sorted({(key.occupancy, key.nights) for key in members}, key=lambda line: (occupancy_order(line[0]), line[1]))
        full = {day for day in days if all(key in closed for key in members if key.date == day)}

        def td(key: CellKey) -> str:
            kind, inner = cell(key) if key in present else ("none", "—")
            if key in closed and key.date not in full:
                inner += '<span class="tag closed">마감</span>'
            return f'<td class="{kind}">{inner}</td>' if kind else f"<td>{inner}</td>"

        tds = {day: [td(CellKey(room, plan, day, occupancy, nights)) for occupancy, nights in lines] for day in days}
        grouped = not by_date and len(days) > ONE_COLUMN_PER_DATE_UP_TO
        columns: list[list[str]] = [[day] for day in days]
        if grouped:
            same: dict[tuple, list[str]] = {}
            for day in days:
                same.setdefault((day in full, tuple(tds[day])), []).append(day)
            columns = sorted(same.values(), key=lambda column: column[0])
        heads, opener = [], '<th class="days">' if grouped else "<th>"
        for column in columns:
            booked = [day for day in column if (room, day) in reserved]
            if grouped:
                label = f"{len(column)}일 · {_ranges(column, weekdays=True)}"
                tags = f'<span class="tag res">예약 있는 날 {esc(_ranges(booked, weekdays=False))}</span>' if booked else ""
            else:
                label, tags = day_label(column[0]), '<span class="tag res">예약 있는 날</span>' if booked else ""
            if column[0] in full:
                tags += '<span class="tag closed">판매 마감</span>'
            heads.append(f"{opener}{esc(label)}{tags}</th>")
        rows = [f"<tr><td>{esc(occupancy_label(occupancy))} · {esc(nights_label(nights))}</td>"
                f"{''.join(tds[column[0]][index] for column in columns)}</tr>" for index, (occupancy, nights) in enumerate(lines)]
        out.append(f'<h3>{esc(room)} · {esc(plan)}</h3>\n<div class="scroll"><table><tr><th>인원 · 박수</th>{"".join(heads)}</tr>'
                   f'{"".join(rows)}</table></div>')
    return "\n".join(out)


def operation_label(request: ChangeRequest, currency: str) -> str:
    """바꾸는 값과 방법 — "판매가 +10%" · "정가 -5,000 USD" · "공급 원가 지움" · "판매가 성인 2 · 1박 이상 350.00 USD 으로"."""
    return f"{FIELD_LABELS[request.field]} {_how(request, currency)}"


def _how(request: ChangeRequest, currency: str) -> str:
    value = request.value
    if request.operation == "clear":
        return "지움"
    if request.operation == "percent":
        return f"{'+' if value >= 0 else '-'}{abs(value).normalize():f}%"
    if request.operation == "amount":
        return f"{'+' if value >= 0 else '-'}{fmt_money(abs(value), currency)} {currency}"
    return f"{occupancy_label(request.base_occupancy)} · {nights_label(1)} {fmt_money(value, currency)} {currency} 으로"


def _flag(verdict: str, after: CellValue, currency: str, key: CellKey) -> str:
    if verdict == "ABOVE_LIST":
        return f"정가 {fmt_money(after.list, currency)} 넘음"
    if verdict == "ABOVE_ONE_NIGHT":
        return f"{nights_label(1)}보다 비쌈" if key.nights > 1 else "박수 층보다 쌈"
    if verdict == "BELOW_COST":
        return f"원가 {fmt_money(after.supply, currency)} 아래"
    if verdict == "OVER_30":
        return "30% 넘음"
    return "적용할 수 없음"


def _value_moves(before: CellValue, after: CellValue, currency: str, name: str) -> str:
    """정가 · 공급 원가 칸 — 바뀌면 `전 → 후`, 그대로면 그 값."""
    old, new = getattr(before, name), getattr(after, name)
    if old == new:
        return fmt_money(old, currency)
    return f"{'새로' if old is None else fmt_money(old, currency)} → {'비움' if new is None else fmt_money(new, currency)}"


def follows_erp(request: ChangeRequest | TargetTable) -> bool:
    """「정가도 같이 올림」에 ERP 의 짝(「정가도 같이 조정」)이 있는 요청인가 — 판매가를 금액이나 퍼센트로 옮길 때."""
    return isinstance(request, ChangeRequest) and request.field == "sell" and request.operation in ("amount", "percent")


def choice_words(request: ChangeRequest | TargetTable, choice: str, currency: str, keys: Iterable[CellKey] = ()) -> str:
    """고름의 이름. 「정가도 같이 올림」은 이 요청에서 정가가 어떻게 되는지까지 말한다 — 퍼센트면 "정가도 12% 올림", 금액이면
    "정가도 10.00 올림"(ERP 「정가도 같이 조정」과 같은 규칙), ERP 에 짝이 없는 새 값 · 목표 값이면 "정가도 판매가가 오른 만큼 올림".
    아동이 있는 칸(`keys`)을 퍼센트로 올리며 아동 추가분은 그대로 두면 그렇게 덧붙인다."""
    if choice != "raise_list":
        return CHOICE_LABELS[choice]
    if not follows_erp(request):
        return "정가도 판매가가 오른 만큼 올림"
    value = request.value
    way = "올림" if value > 0 else "내림"
    if request.operation == "amount":
        return f"정가도 {fmt_money(abs(value), currency)} {way}"
    children = not request.scale_child_surcharge and any(split_occupancy(key.occupancy)[1] for key in keys)
    return f"정가도 {abs(value).normalize():f}% {way}" + (" (아동이 있는 칸은 아동 추가분은 그대로)" if children else "")


def follow_move(change: CellChange, currency: str) -> str:
    """「정가도 같이 올림」이면 정가가 어떻게 되는지 — "61.18 → 68.52"."""
    return f"{fmt_money(change.before.list, currency)} → {fmt_money(change.list_follow, currency)}"


def _chosen_tag(change: CellChange, request: ChangeRequest | TargetTable, currency: str) -> str:
    """고른 빨간 줄 칸의 꼬리표 — 고른 것만. 그 결과는 칸의 값(「전 → 후」 · 「정가 … → …」)이 말하고, 고르기 전에 걸렸던 까닭
    (「정가보다 비싸집니다」)은 이제 일어나지 않는 일이라 쓰지 않는다."""
    return f'<span class="tag chosen">{esc(choice_words(request, change.choice, currency, [change.key]))}</span>'


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


def render_preview(plan: Plan, change_id: int | None = None, steps: Sequence | None = None, by_date: bool = False) -> str:
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
            was = "가격 없음" if change.before.sell is None else fmt_money(change.before.sell, currency)
            return "blocked", f'<span class="was">{was}</span><span class="tag blocked">적용할 수 없음</span>'
        if severity == HELD:
            return "none", (f'<span class="was">{fmt_money(change.before.sell, currency)}</span><small class="more">그대로</small>'
                            '<span class="tag chosen">성인 칸 따라 그대로</span>')
        if change.choice == "keep":
            was = "가격 없음" if change.before.sell is None else fmt_money(change.before.sell, currency)
            return "chosen", (f'<span class="was">{was}</span>'
                              f'<small class="more">그대로</small>{_chosen_tag(change, request, currency)}')

        moved = _move(change.before, change.after, currency)
        if change.choice:
            return "chosen", moved + _chosen_tag(change, request, currency)
        if severity == RED:
            return "red", f'{moved}<span class="tag red">{esc(_flag(change.verdict, change.after, currency, key))}</span>'
        if NEW in change.marks:
            return "new", f'{moved}<span class="tag new">새 칸</span>'
        return "", moved

    targets = isinstance(request, TargetTable)
    sheet = targets and request.from_sheet
    what = (f"{'새 요금표' if sheet else '목표 값'} {len(request.targets):,}칸" if targets else operation_label(request, currency))
    title = f"미리보기 · {request.hotel} · {request.offer} · {what}"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub"><b>아직 아무것도 바뀌지 않았습니다.</b> 지금 값은 {esc(fmt_time(plan.read_at))} 에 ERP 에서 읽은 것입니다'
            f'{f" (장부 {change_id}번에 적어 두었습니다)" if change_id else ""}. 통화 {esc(currency)}.</p>',
            _request_box(request, currency, plan.absent_pairs),
            f'<div class="banner amber">{esc(SEASON_REFILL_NOTE)}</div>' if sheet else "", _preview_banners(plan, tally),
            stats([(tally["will_change"], "바뀌는 칸"), (tally["red"], "빨간 줄 (고르기 전)")]
                  + ([(tally["chosen"], "고른 빨간 줄")] if tally["chosen"] else [])
                  + [(tally["blocked"], "적용할 수 없는 칸")] + ([(tally["held"], HELD_STAT)] if tally["held"] else [])
                  + ([(tally["reserved"], "예약 있는 날의 칸 (바꿉니다)")] if tally["reserved"] else [])
                  + ([(tally["closed"], "판매 마감인 칸 (값만 바뀌고 마감은 그대로)")] if tally["closed"] else [])
                  + [(tally["skipped"], "건너뛰는 칸")] + ([(tally["new"], "새로 생기는 칸")] if tally["new"] else [])),
            _skip_line(plan), _tiers_line(plan), _coverage_section(plan.coverage) if sheet else ""]
    if tally["red"]:
        body.append(f'<p class="sub">빨간 줄 {tally["red"]:,}칸을 어떻게 할지 고르시면 ERP 에 몇 번 나눠 저장하는지 정해집니다. '
                    "그때 미리보기를 다시 보여 드립니다.</p>")
    elif len(steps or ()) == 1:
        body.append('<p class="sub">적용하면 ERP 에 한 번에 저장합니다'
                    f'{"(정가·원가를 비우는 셀 창 저장)" if steps[0].kind == "cell_edit" else ""}.</p>')
    elif steps:
        edits = sum(step.kind == "cell_edit" for step in steps)
        body.append(f'<p class="sub">적용하면 ERP 에 {len(steps)}번 나눠 저장합니다(객실 · 요금제마다 값이 같은 날을 묶어 한 번 — 날이 떨어져 있어도 한 번'
                    f'{f", 그중 정가·원가를 비우는 셀 창 저장 {edits}번" if edits else ""}).</p>')
    body += ["<h2>칸마다 바뀌는 값</h2>", grid(list(by_key) + list(skipped), cell, reserved, closed, by_date),
             _flagged_section(plan, currency), _new_section(plan, currency)]
    marked = ([RESERVED_NOTE] if tally["reserved"] else []) + ([CLOSED_NOTE] if tally["closed"] else [])
    if targets:
        lines = [_rounding_note(currency), "목표 값이 지금 값과 같은 칸은 바꾸지 않습니다(표에 나오지 않습니다).", *marked]
        if tally["new"]:   # 있던 칸에 넣은 정가·공급 원가는 새 칸이 아니다 — 되돌리면 다시 비워진다
            lines.append("새로 생기는 칸은 나중에 되돌리기로 지울 수 없습니다. 꼭 필요한 칸인지 확인해 주세요.")
        body += [notes(lines), _ending(tally)]
        return page(title, "\n".join(body), MAKER)
    others = [FIELD_LABELS[name] for name in FIELDS if name != request.field]
    moved_list = sum(change.choice in ("raise_list", "clear_list") for change in plan.changes)
    lines = [_rounding_note(currency), *marked,
             f"{others[0]}와 {others[1]}는 바꾸지 않습니다" + (
                 f". 다만 고르신 대로 {moved_list:,}칸은 정가도 같이 바뀝니다(표의 「정가 … → …」 줄)." if moved_list else
                 "(정가를 넘는 칸에서 정가를 올리거나 지우라고 고르신 경우만 정가가 같이 바뀝니다).")]
    if request.operation == "percent":
        lines.insert(0, "아동이 있는 칸은 아동 추가분도 같은 비율로 곱했습니다." if request.scale_child_surcharge else
                     "아동이 있는 칸은 ERP 와 똑같이 성인 몫에만 곱하고 아동 추가분은 그대로 둡니다. "
                     "아동 추가분도 같이 바꾸려면 그렇게 말씀해 주세요.")
    body += [notes(lines), _ending(tally)]
    return page(title, "\n".join(body), MAKER)


APPLY_INVITE = '말씀이 없으면 아무것도 바뀌지 않습니다. 대화창에서 "적용"이라고 하시면 바꿉니다.'


def _ending(tally: Mapping) -> str:
    """미리보기의 끝 — 지금 담당자가 할 일. 고를 빨간 줄이 남았으면 그것이 먼저이고 "적용"을 청하지 않는다(Y3). 저장할 칸이 없으면
    적용할 것이 없다고 한다."""
    if tally["red"]:
        return (f'<div class="banner red"><b>아직 적용할 수 없습니다.</b> 먼저 빨간 줄 {tally["red"]:,}칸을 어떻게 할지 대화창에서 '
                "말씀해 주세요(고를 것은 위의 빨간 띠에 있습니다). 고르시면 미리보기를 다시 보여 드립니다.</div>")
    if not tally["will_change"]:
        return '<div class="banner blue">바꿀 칸이 없어 적용할 것이 없습니다. 아무것도 바뀌지 않았습니다.</div>'
    return f'<div class="banner blue">{APPLY_INVITE}</div>'


def _coverage_section(gaps: Sequence[Gap]) -> str:
    """요금표로 맞출 때 넣지 않는 것 — 종류마다 수와 목록(객실 · 요금제 · 인원 · 박수 · 날짜 구간 · 줄 번호)."""
    tally = coverage_counts(gaps)
    out = ['<h2>요금표가 넣지 않는 것 <span class="sub">— 적용 전에 꼭 보세요</span></h2>']
    if not gaps:
        return out[0] + '<div class="banner ok">읽은 범위의 칸을 요금표가 빠짐없이 덮습니다.</div>'
    units = {"untouched": "칸", "unseen": "칸", "no_sale": "일", "unknown": "개", "unnamed": "개"}
    for kind, title in GAP_KINDS.items():
        items = [gap for gap in gaps if gap.kind == kind]
        if not items:
            continue
        rows = []
        for gap in items:
            line = "" if gap.occupancy is None else line_label(gap.occupancy, gap.nights)
            days = f"{runs_label(gap.dates)} ({len(gap.dates):,}일)" if gap.dates else ""
            nos = ", ".join(f"{no}번째 줄" for no in gap.lines)
            rows.append("<tr>" + "".join(f'<td class="text">{esc(text)}</td>' for text in
                                         (f"{gap.room} · {gap.rate_plan}", line, days, nos)) + "</tr>")
        out.append(f"<h3>{esc(title)} · {tally[kind]:,}{units[kind]}</h3><div class=\"scroll\"><table>"
                   "<tr><th>객실 · 요금제</th><th>인원 · 박수</th><th>날짜</th><th>요금표 줄</th></tr>" + "".join(rows) + "</table></div>")
    return "\n".join(out)


def _tiers_line(plan: Plan) -> str:
    """읽은 값에서 바꾸기 전부터 1박 이상 층보다 비싼 박수 층 칸 — 이번에 바꾸지 않는 그 칸은 고치라고 하지 않고 수만 알린다."""
    if not plan.above_one_night_before:
        return ""
    return (f'<p class="sub">읽은 값에 바꾸기 전부터 같은 날 {nights_label(1)} 가격보다 비싼 박수 층 칸이 {plan.above_one_night_before:,}칸 '
            "있습니다. 이번에 바꾸지 않는 칸은 그대로 두고, 바꾸는 칸만 견줍니다.</p>")


def _skip_line(plan: Plan) -> str:
    reasons: dict[str, int] = {}
    for item in plan.skipped:
        reasons[item.reason] = reasons.get(item.reason, 0) + 1
    lines = []
    if reasons:
        lines.append('<p class="sub">건너뛰는 칸의 까닭: '
                     + esc(" · ".join(f"{SKIP_LABELS[reason]} {count:,}칸" for reason, count in reasons.items())) + "</p>")
    if plan.empty_pairs:
        lines.append('<p class="sub">읽었지만 가격이 하나도 없어 건너뛰는 객실·요금제: '
                     + esc(", ".join(f"{room} · {plan_name}" for room, plan_name in plan.empty_pairs)) + "</p>")
    if plan.no_sale:
        by_pair: dict[tuple[str, str], list[str]] = {}
        for room, plan_name, day in plan.no_sale:
            by_pair.setdefault((room, plan_name), []).append(day)
        lines.append('<p class="sub">판매일 없음(판매일이 열리지 않아 바꿀 수 없는 날, 「가격 없음」과 다릅니다): '
                     + esc(" / ".join(f"{room} · {plan_name} · {days_summary(days)}" for (room, plan_name), days in by_pair.items()))
                     + "</p>")
    return "".join(lines)


SCOPE_ROOMS = 3   # 장부 한 줄에 이름으로 적는 객실 수 — 넘으면 「외 N객실」


def cells_scope(keys: Iterable[CellKey]) -> str:
    """칸들이 덮는 것 — "스탠다드(조식 포함), 스탠다드 바다 전망(조식 포함) · 12/7 월 ~ 12/8 화 · 12/10 목 · 12/14 월 (4일, 2026년)".
    장부 목록 · check 가 요청 문장에 날짜가 없어도 무엇을 바꾼 번호인지 말할 수 있게."""
    keys = sorted(keys)
    if not keys:
        return "칸 없음"
    pairs = list(dict.fromkeys((key.room, key.rate_plan) for key in keys))
    rooms = list(dict.fromkeys(room for room, _plan in pairs))
    shown = pairs_label(pair for pair in pairs if pair[0] in rooms[:SCOPE_ROOMS])
    more = f" 외 {len(rooms) - SCOPE_ROOMS}객실" if len(rooms) > SCOPE_ROOMS else ""
    return f"{shown}{more} · {days_summary({key.date for key in keys})}"


def narrowed(occupancies: Iterable[str], nights: Iterable[int]) -> str:
    """좁힌 칸 — "1박 이상만" · "성인 2 · 성인 3만" · "성인 2 / 1박 이상만". 좁히지 않았으면 빈 글자."""
    parts = (" · ".join(occupancy_label(key) for key in occupancies), " · ".join(nights_label(n) for n in sorted(nights)))
    shown = " / ".join(part for part in parts if part)
    return f"{shown}만" if shown else ""


def record_what(kind: str, request: Mapping | None, reverses: int | None, currency: str, cells: int | None = None) -> str:
    """장부의 번호가 한 일 — "판매가 +12%" · "판매가 -10% (1박 이상만)" · "목표 값 6칸" · "새 요금표 120칸" · "3번 되돌리기" ·
    "3번 되돌리기 (성인 2만)" · "5번 저장 상태로 되돌리기" · "지금 상태 저장". 칸을 좁혔으면(인원 조합 · 박수 층, 되돌리기의 고른 칸)
    괄호로 그렇게 말한다 — 되돌리기 확인이 이 줄을 읽어 준다. 목표 값 · 새 요금표의 칸 수는 저장이 넣는(넣을) 칸이다(`cells`,
    장부의 `planned` — 빨간 줄에 안 바꾸기로 고른 칸은 세지 않는다)."""
    if kind == "snapshot":
        return "지금 상태 저장"
    picked = f" ({request['scope']}만)" if request and request.get("scope") else ""
    if kind == "rollback":
        return f"{reverses}번 되돌리기{picked}"
    if request is None:
        return "가격 바꾸기"
    if request.get("kind") == "restore_snapshot":
        return f"{request.get('snapshot')}번 저장 상태로 되돌리기{picked}"
    parsed = decode_request(request)
    if isinstance(parsed, TargetTable):
        return f"{'새 요금표' if parsed.from_sheet else '목표 값'} {len(parsed.targets) if cells is None else cells:,}칸"
    narrow = narrowed(parsed.occupancies, parsed.nights)
    return operation_label(parsed, currency) + (f" ({narrow})" if narrow else "")


def record_scope(entry: Mapping, keys: Iterable[CellKey]) -> str:
    """장부 목록의 한 줄 → 담당자에게 읽어 줄 수 있는 범위 — 「객실 가격」, 오퍼, 객실 · 요금제, 날짜 구간, 한 일, 어디까지
    갔는지(scope_text — 어디까지는 세 도우미가 같은 말, files.record_progress). 오퍼는 늘 댄다 — 같은 객실 · 요금제가 두 오퍼에 있으면 오퍼 없이는 두 번호가 같은 줄이 되고, 되돌리기
    확인이 이 줄을 읽어 준다."""
    return scope_text(entry["offer"], keys, record_what(entry["kind"], entry["request"], entry["reverses"], entry["currency"],
                                                        entry["planned"]), record_progress(entry, "칸"))


KIND_WORD = "객실 가격"   # 세 도우미의 기록이 한 목록에 나올 때 이 종류를 부르는 말(부가옵션 가격 줄 · 부과금은 범위의 머리가 말한다)


def scope_text(offer: str, keys: Iterable[CellKey], what: str, progress: str = "") -> str:
    """범위 한 줄의 차례 — 「객실 가격」 · 오퍼 · 칸들이 덮는 것 · 한 일 · 어디까지 갔는지. 장부에 적지 않은 되돌리기 계산도 같은
    차례다."""
    return " · ".join(part for part in (KIND_WORD, offer, cells_scope(keys), what, progress) if part)


def pairs_label(pairs: Iterable[tuple[str, str]]) -> str:
    """(객실, 요금제) 쌍 → "디럭스(조식 포함 · 룸온리), 스위트(조식 포함)"."""
    by_room: dict[str, list[str]] = {}
    for room, plan in pairs:
        by_room.setdefault(room, []).append(plan)
    return ", ".join(f"{room}({' · '.join(plans)})" for room, plans in by_room.items())


def cells_label(request: ChangeRequest) -> str:
    """확인 상자 · 미리보기의 「칸」 — 고른 인원 조합 · 박수 층, 고르지 않았으면 전부."""
    occupancies = " · ".join(occupancy_label(key) for key in request.occupancies) or "모든 인원 조합"
    nights = " · ".join(nights_label(n) for n in sorted(request.nights)) or "모든 박수"
    return f"{occupancies} / {nights}" if request.occupancies or request.nights else "모든 인원 조합 · 모든 박수"


def _request_box(request: ChangeRequest | TargetTable, currency: str, absent: Iterable[tuple[str, str]] = ()) -> str:
    if isinstance(request, TargetTable):
        keys = [target.key for target in request.targets]
        rows = [("호텔", request.hotel), ("오퍼", request.offer),
                ("객실 · 요금제", pairs_label(dict.fromkeys((key.room, key.rate_plan) for key in keys))),
                ("날짜", days_summary({key.date for key in keys})),
                ("칸", " / ".join(dict.fromkeys(line_label(key.occupancy, key.nights) for key in sorted(
                    keys, key=lambda k: (occupancy_order(k.occupancy), k.nights))))),
                ("목표 값", f"{len(keys):,}칸")]
    else:
        rows = [("호텔", request.hotel), ("오퍼", request.offer), ("객실 · 요금제", pairs_label(request.pairs)),
                ("날짜", days_summary(request.dates)), ("바꾸는 값", operation_label(request, currency)),
                ("칸", cells_label(request))]
    absent = list(absent)
    if absent:
        rows.append(("없는 요금제", ", ".join(f"{room}에는 {plan} 요금제가 없어 뺐습니다" for room, plan in absent)))
    dl = "".join(f"<dt>{esc(name)}</dt><dd>{esc(value)}</dd>" for name, value in rows)
    sentence = f'<p class="sub">요청: “{esc(request.sentence)}”</p>' if request.sentence else ""
    return f'<div class="frame">{sentence}<dl class="kv">{dl}</dl></div>'


CHOSEN_WORDS = {   # 고른 빨간 줄 띠 — 고른 것마다 저장이 그 칸에 하는 일
    "include": "계산한 값 그대로 바꿉니다.",
    "keep": "그 칸은 바꾸지 않습니다.",
    "raise_list": "정가도 그렇게 옮겨 저장합니다(ERP 「정가도 같이 조정」과 같은 계산).",
    "clear_list": "정가를 지워 저장합니다(손님 화면에 줄 그은 값이 없어집니다).",
}
CHOSEN_GROUPS = {   # 고른 빨간 줄 띠의 머리 — 고르기 전에 계산한 값이 어땠던 칸인지(지난 일로)
    "ABOVE_LIST": "계산한 값이 정가를 넘던 칸",
    "ABOVE_ONE_NIGHT": "1박 이상보다 비싸지던 박수 층",
    "BELOW_COST": "계산한 값이 공급 원가 아래이던 칸",
    "OVER_30": "30% 넘게 바뀌던 칸",
}
RAISE_WITHOUT_ERP = "ERP 에는 이런 바꾸기의 정가 규칙이 없어, 판매가가 오른 만큼 정가도 올려 저장합니다."
HELD_STAT = "성인 칸을 따라 그대로 두는 칸"
HELD_NOTE = ("아동이 든 칸은 같은 날 · 같은 박수 층의 성인만 있는 칸과 같이 움직여야 아동 추가분이 그대로 남습니다(ERP [선택 날짜 "
             "가격 가감]과 같습니다). 그 성인 칸을 바꾸면 이 칸도 바뀝니다.")


def red_lines(plan: Plan) -> list[dict]:
    """아직 고르지 않은 빨간 줄 — 규칙마다 칸 수, 고를 것(담당자에게 말하는 이름, 「정가도 같이 올림」은 첫 칸의 예와 함께), 칸의 예
    몇. 미리보기의 띠와 plan 의 답이 같은 말을 쓴다(도우미는 이 말을 그대로 전한다)."""
    out = []
    for rule in CELL_RULES.rules:
        waiting = [change for change in plan.changes if change.verdict == rule.code and change.waiting]
        if rule.severity != RED or not waiting:
            continue
        choices = []
        for choice in rule.choices:
            item = dict(choice=choice, words=choice_words(plan.request, choice, plan.currency, [c.key for c in waiting]))
            if choice == "raise_list":
                item["example"] = f"{cell_name(waiting[0].key)} — 정가 {follow_move(waiting[0], plan.currency)}"
            choices.append(item)
        out.append(dict(rule=rule.code, label=rule.label, cells=len(waiting), choices=choices,
                        examples=[encode_key(change.key) for change in waiting[:EXAMPLES]]))
    return out


def chosen_lines(plan: Plan) -> list[dict]:
    """고른 빨간 줄 — 규칙 · 고름마다 칸 수, 그 고름의 이름, 저장이 하는 일, 첫 칸의 예(바뀌는 값, 안 바꾸면 그대로인 값)."""
    out = []
    for rule in CELL_RULES.rules:
        for choice in rule.choices:
            picked = [change for change in plan.changes if change.verdict == rule.code and change.choice == choice]
            if not picked:
                continue
            example = picked[0]
            shown = "".join(f" {FIELD_LABELS[name]} {_value_moves(example.before, example.after, plan.currency, name)}"
                            for name in FIELDS if name in example.changed)
            does = RAISE_WITHOUT_ERP if choice == "raise_list" and not follows_erp(plan.request) else CHOSEN_WORDS[choice]
            out.append(dict(rule=rule.code, choice=choice, cells=len(picked), does=does,
                            words=choice_words(plan.request, choice, plan.currency, [c.key for c in picked]),
                            example=f"{cell_name(example.key)} —"
                                    + (shown or f" 판매가 {fmt_money(example.before.sell, plan.currency)} 그대로")))
    return out


def unused_lines(plan: Plan) -> list[dict]:
    """고르셨지만 이번 계산에서 어느 칸도 쓰지 않는 고름 — 고름 · 까닭마다 그 고름의 이름(`words`), 고르실 때 하신 말, 그 고름을
    말한 칸 수와 첫 칸, 까닭(`why` 코드 · `label` 담당자에게 하는 한 마디). 미리보기의 「고르신 빨간 줄」과 plan 의 답이 같은 말을
    쓴다 — 도우미는 red-lines.md 「쓰지 않는 고름」대로 한 문장을 덧붙인다."""
    return [dict(rule=item.rule, choice=item.choice, words=choice_words(plan.request, item.choice, plan.currency, item.cells),
                 said=item.said, cells=len(item.cells), why=item.why, label=item.words,
                 example=cell_name(item.cells[0]) if item.cells else None) for item in plan.unused]


EXAMPLES = 3   # 빨간 줄마다 plan 의 답에 싣는 칸의 예


def _preview_banners(plan: Plan, tally: Mapping) -> str:
    """머리 띠 — 적용할 수 없는 칸, 아직 고르지 않은 빨간 줄(규칙마다), 고른 빨간 줄(규칙마다, 고른 것과 그 칸의 예 하나)."""
    out = []
    blocked = [rule for rule in CELL_RULES.rules if rule.severity == BLOCKED and tally[rule.code]]
    if blocked:
        reasons = " · ".join(f"{rule.label} {tally[rule.code]}칸" for rule in blocked)
        out.append(f'<div class="banner amber"><b>적용할 수 없음 · {tally["blocked"]}칸</b> ERP 가 받지 않는 값이라 이 칸은 '
                   f'바꾸지 않습니다. ({esc(reasons)})</div>')
    if tally["held"]:
        out.append(f'<div class="banner amber"><b>같이 그대로 · {tally["held"]}칸</b> {esc(CELL_RULES.by_code["ADULT_HELD"].label)} '
                   f'— {esc(HELD_NOTE)}</div>')
    messages = {
        "ABOVE_LIST": ("정가(줄 그은 값)를 넘습니다.", "ERP 는 판매가가 정가보다 비싼 것을 받지 않습니다. 이 칸은 골라 주세요: "),
        "ABOVE_ONE_NIGHT": (f"같은 날 {nights_label(1)} 가격보다 비싼 박수 층이 됩니다.",
                            "긴 숙박이 1박 이상보다 비싸지는 칸입니다(2박 이상 층이 1박 이상보다 비싸지거나, 1박 이상을 내려 위 층보다 "
                            "싸짐). ERP [선택 날짜 가격 가감]은 이런 칸을 건너뜁니다. 이 칸은 골라 주세요: "),
        "BELOW_COST": ("공급 원가보다 싸집니다.", "맞으면 그 칸을 짚어 다시 말씀해 주세요. 고를 것: "),
        "OVER_30": ("지금 값보다 30% 넘게 바뀝니다.", "금액을 잘못 말씀하신 것은 아닌지 확인해 주세요. "
                    "맞으면 그 칸을 짚어 다시 말씀해 주세요. 고를 것: "),
    }
    for line in red_lines(plan):
        headline, detail = messages[line["rule"]]
        offered = " / ".join(item["words"] + (f" (예: {item['example']})" if "example" in item else "") for item in line["choices"])
        out.append(f'<div class="banner red"><b>빨간 줄 · {line["cells"]:,}칸이 {esc(headline)}</b> {esc(detail + offered)}.</div>')
    by_rule: dict[str, list[dict]] = {}
    for line in chosen_lines(plan):
        by_rule.setdefault(line["rule"], []).append(line)
    idle: dict[str, list[dict]] = {}
    for line in unused_lines(plan):
        idle.setdefault(line["rule"], []).append(line)
        by_rule.setdefault(line["rule"], [])
    for code, lines in by_rule.items():
        parts = [f"<li><b>{esc(line['words'])} · {line['cells']:,}칸</b> {esc(line['does'])}"
                 + (f' <span class="sub">예: {esc(line["example"])}</span>' if line["example"] else "") + "</li>" for line in lines]
        parts += [f"<li><b>{esc(line['words'])}</b> — 고르셨지만 이번 계산에서는 쓰지 않습니다"
                  + (f" ({line['cells']:,}칸)" if line["cells"] else "") + f": {esc(line['label'])}."
                  + (f' <span class="sub">예: {esc(line["example"])}</span>' if line["example"] else "") + "</li>" for line in idle.get(code, ())]
        counted = sum(line["cells"] for line in lines)
        out.append(f'<div class="banner amber"><b>고르신 빨간 줄{f" · {counted:,}칸" if lines else ""} '
                   f'({esc(CHOSEN_GROUPS[code])})</b><ul class="notes">{"".join(parts)}</ul></div>')
    if not tally["red"] and not tally["blocked"]:
        chosen = ("고르신 대로 저장합니다." if tally["will_change"] else "고르신 대로면 바꿀 칸이 없어 아무것도 저장하지 않습니다.")
        out.append('<div class="banner ok">' + (f"남은 빨간 줄이 없습니다. {chosen}" if tally["chosen"] else "빨간 줄이 없습니다.")
                   + "</div>")
    return "\n".join(out)


def _flagged_section(plan: Plan, currency: str) -> str:
    flagged = [change for change in plan.changes if change.verdict]
    if not flagged:
        return ""
    rows = []
    for change in flagged:
        rule = CELL_RULES.by_code[change.verdict]
        after = change.before if rule.severity == HELD else change.after or change.before
        if change.choice == "keep":
            moved = "그대로"
        else:
            moved = "—" if change.after is None else _move(change.before, change.after, currency)
        if change.choice:   # 고른 뒤에는 고른 것과 그 결과(앞 칸들의 값)만 — 걸렸던 까닭은 쓰지 않는다
            why = (f'<span class="tag chosen">고름</span> '
                   f'{esc(choice_words(plan.request, change.choice, currency, [change.key]))}')
            choices = "고르신 대로 그대로 둡니다(저장하지 않습니다)" if change.choice == "keep" else "고르신 대로 저장합니다"
        elif rule.severity == HELD:
            moved = "그대로"
            why = f'<span class="tag chosen">그대로</span> {esc(rule.label)}'
            choices = "성인만 있는 칸을 바꾸면 같이 바뀝니다(저장하지 않습니다)"
        else:
            kind, word = ("blocked", "적용할 수 없음") if rule.severity == BLOCKED else ("red", "빨간 줄")
            why = f'<span class="tag {kind}">{word}</span> {esc(rule.label)}'
            choices = " / ".join(choice_words(plan.request, choice, currency, [change.key])
                                 + (f": {follow_move(change, currency)}" if choice == "raise_list" else "")
                                 for choice in rule.choices) if rule.choices else "바꾸지 않음"
        rows.append(f'<tr><td class="text">{esc(cell_name(change.key))}</td><td>{fmt_money(change.before.sell, currency)}</td>'
                    f'<td>{moved}</td><td>{_value_moves(change.before, after, currency, "list")}</td>'
                    f'<td>{_value_moves(change.before, after, currency, "supply")}</td>'
                    f'<td class="text">{why}</td><td class="text">{esc(choices)}</td></tr>')
    return ('<h2>따로 확인할 칸</h2><div class="scroll"><table><tr><th>칸</th><th>지금 판매가</th><th>바뀌는 값</th>'
            '<th>정가 (지금 → 바뀐 뒤)</th><th>공급 원가 (지금 → 바뀐 뒤)</th><th>왜</th><th>고를 수 있는 것</th></tr>'
            + "".join(rows) + "</table></div>")


def _new_section(plan: Plan, currency: str) -> str:
    fresh = [change for change in plan.changes if NEW in change.marks]
    if not fresh:
        return ""
    rows = []
    for change in fresh:
        rule = CELL_RULES.by_code.get(change.verdict)
        status = "만듭니다" if rule is None else f"{'적용할 수 없음' if rule.severity == BLOCKED else '빨간 줄'} · {rule.label}"
        after = change.after or change.before
        rows.append(f'<tr><td class="text">{esc(cell_name(change.key))}</td><td>{fmt_money(after.sell, currency)}</td>'
                    f'<td>{fmt_money(after.list, currency)}</td><td>{fmt_money(after.supply, currency)}</td>'
                    f'<td class="text">{esc(status)}</td></tr>')
    return ('<h2>새로 생기는 칸 <span class="sub">— 지금은 가격이 없는 칸입니다</span></h2>'
            '<div class="banner amber">ERP 에는 칸을 지우는 길이 없어, 이 칸들은 나중에 되돌려도 지울 수 없습니다'
            '(되돌리기에서 「지울 수 없는 칸」으로 남습니다).</div><div class="scroll"><table>'
            '<tr><th>칸</th><th>판매가</th><th>정가</th><th>공급 원가</th><th>상태</th></tr>' + "".join(rows) + "</table></div>")


@dataclass
class CellView:
    """장부의 줄(필드마다 하나)을 칸 하나로 모은 것. `after` 는 저장이 끝난 단계가 넣은 값, `waiting` 은 아직 저장되지 않은 단계가
    넣을 값(이어서 하면 이 값이 된다 — 비움은 None), `steps` 는 그 단계 번호들(한 칸의 필드를 묶음 저장과 셀 창 저장이 나눠 쓸 수
    있다). 둘 다 비었으면 이 변경이 일부러 손대지 않는 칸이다."""
    before: CellValue
    after: dict = field(default_factory=dict)
    written: bool = False
    verified: bool = True
    seen: dict = field(default_factory=dict)
    reserved: bool = False
    rolled_back_by: int | None = None
    waiting: dict = field(default_factory=dict)
    steps: set = field(default_factory=set)


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
            if row.action is not None and not row.written:
                view.waiting[row.field] = row.after
                view.steps |= {row.step} - {None}
            if not row.written:
                continue
            view.written = True
            view.after[row.field] = row.after
            if row.rolled_back_by is not None:
                view.rolled_back_by = row.rolled_back_by
                continue
            view.verified = view.verified and row.verified
            view.seen[row.field] = row.seen
        views[key_of_item(item_key)] = view
    return views


def _waiting_tag(view: CellView, steps: Mapping) -> str:
    """아직 저장되지 않은 칸의 꼬리표 — 어느 저장의 칸인지("3 · 4번째 저장")와, 그 저장이 눌렸는데 됐는지 모르면 그렇게."""
    where = f" · {' · '.join(map(str, sorted(view.steps)))}번째 저장" if view.steps else ""
    unknown = any(steps[index].status == "failed" and steps[index].unknown for index in view.steps if index in steps)
    return f'<span class="tag wait">{"저장됐는지 모름" if unknown else "아직 저장 안 함"}{where}</span>'


def _undoes(record: ChangeRecord) -> bool:
    """되돌리기인가 — 변경 되돌리기 · 저장해 둔 상태로 되돌리기."""
    return record.kind == "rollback" or (record.request or {}).get("kind") == "restore_snapshot"


def result_name(record: ChangeRecord) -> str:
    """결과 페이지의 이름(제목과 파일 이름) — 「적용 결과」 · 「되돌리기 결과」, 멈춘 변경이면 「적용하다 멈춤」 · 「되돌리다 멈춤」
    (chrome.result_word)."""
    return result_word(record, _undoes(record))


def _moved_cell(before: CellValue, now, currency: str, seen_at: str) -> str:
    """멈춘 뒤 다시 읽어 보니 미리보기 때와 달라진 칸 — 미리보기 때 값과 그때 읽은 ERP 값(다른 필드만, `seen_at` 은 「19시 26분에
    다시 읽으니」), 그리고 넣지 않았다는 꼬리표. 그 값은 지금 값이라고 하지 않는다 — 그 뒤에 또 바뀌었을 수 있다."""
    if now is None or now.state == "missing":
        shown = f'<b class="now">{seen_at} 칸 없음</b>'
    else:
        fields = [name for name in FIELDS if getattr(before, name) != now.fields.get(name)] or ["sell"]

        def values(value_of) -> str:
            return " · ".join(f'{FIELD_LABELS[name] + " " if name != "sell" else ""}{fmt_money(value_of(name), currency)}' for name in fields)

        shown = (f'<span class="was">미리보기 때 {values(lambda name: getattr(before, name))}</span> · '
                 f'<b class="now">{seen_at} {values(now.fields.get)}</b>')
        if now.state != before.state and now.state == "closed":
            shown += '<span class="tag closed">판매 마감</span>'
    return shown + MOVED_TAG


def _waiting_intro(record: ChangeRecord, waiting: int, moved: int) -> str:
    """「아직 저장 안 함」 칸이 무엇을 보이는지 — 멈춘 뒤 마지막 check 가 본 것대로(stop_mode)."""
    mode = stop_mode(record)
    if mode == "forbids":
        text = f"「아직 저장 안 함」 {waiting:,}칸은 이 변경이 넣으려던 값입니다 — 이어서 할 수 없어 넣지 않습니다."
        if moved:
            text += " " + moved_sentence(record, moved)
    elif mode == "undone":
        text = f"「아직 저장 안 함」 {waiting:,}칸은 이 변경이 넣으려던 값입니다 — 넣지 않았고, 이어서 하지 않습니다."
        if moved:
            text += " " + moved_sentence(record, moved)
    elif mode == "allows":
        text = (f"「아직 저장 안 함」 {waiting:,}칸은 미리보기 때 값 → 이어서 하면 넣을 값입니다. {checked_when(record)}에 다시 읽었을 때 "
                "ERP 값이 미리보기 때와 같았습니다 — 그 뒤에 바뀌었을 수 있고, 바뀐 칸이 있으면 그 저장은 넣지 않고 멈춥니다.")
    elif mode == "unchecked":
        text = (f"「아직 저장 안 함」 {waiting:,}칸은 미리보기 때 값 → 이어서 하면 넣을 값입니다. 지금 ERP 값은 다시 읽어 봐야 "
                "압니다.")
    else:
        text = f"「아직 저장 안 함」 {waiting:,}칸은 미리보기 때 값 → 넣을 값입니다."
    return text + " 「그대로」인 칸은 이 변경이 바꾸지 않는 칸입니다."


def render_result(record: ChangeRecord, ledger_path: str | None = None, by_date: bool = False) -> str:
    """장부의 변경 하나의 결과. 칸마다 — 저장한 칸은 `전 → 넣은 값`, 아직 저장하지 않은 칸은 `미리보기 때 값 → 이어서 하면 넣을
    값`과 「아직 저장 안 함 · N번째 저장」, 이 변경이 일부러 손대지 않는 칸만 「그대로」. 멈춘 뒤 다시 읽어(check) 미리보기 때와 달라진
    칸은 미리보기 때 값과 그 check 가 읽은 값(그 시각과 함께), 「그 사이 ERP 에서 바뀜 · 넣지 않음」. 멈춘 변경을 이어서 할지 고르는 담당자가 보는 페이지다."""
    currency = record.currency
    views = cell_views(record)
    stop = stop_view(record)
    moved_now = {key: now for (kind, key), now in (stop[1].moved.items() if stop and stop[1] else ()) if kind == ITEM_KIND}
    moved_shown = sum(1 for key, view in views.items() if view.waiting and cell_item_key(key) in moved_now)
    steps = {step.index: step for step in record.steps}
    written = [view for view in views.values() if view.written and not view.rolled_back_by]
    waiting = [view for view in views.values() if view.waiting]
    undone = sorted({view.rolled_back_by for view in views.values() if view.rolled_back_by})
    undone_count = sum(1 for view in views.values() if view.rolled_back_by)
    mismatched = [view for view in written if record.verified_at and not view.verified]
    title = f"{result_name(record)} · {record.hotel} · {record.offer}"
    restored = (record.request or {}).get("snapshot") if (record.request or {}).get("kind") == "restore_snapshot" else None
    did = (f" · {record.reverses}번 변경을 되돌림" if record.reverses else
           f" · {restored}번에 저장해 둔 상태로 되돌림" if restored is not None else "")
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">장부 {record.id}번 · 요청 “{esc(record.sentence)}”{did} · 통화 {esc(currency)}</p>',
            result_banner(record, len(written), len(mismatched))]
    if undone:
        body.append(f'<p class="sub">이 변경의 {undone_count:,}칸은 뒤에 되돌렸습니다(장부 '
                    f'{", ".join(f"{number}번" for number in undone)}).</p>')
    if (record.request or {}).get("from_sheet"):
        body.append(f'<div class="banner amber">{esc(SEASON_REFILL_NOTE)}</div>')
    body += [steps_list(record.steps, _step_sizes(record)), stopped_choices(record, len(waiting)), _chosen_table(record)]
    closed = {key for key, view in views.items() if view.before.state == "closed"}
    reserved = {(key.room, key.date) for key, view in views.items() if view.reserved}

    def cell(key: CellKey) -> tuple[str, str]:
        view = views[key]
        if not view.written and not view.waiting:
            return "same", f'<span class="was">{fmt_money(view.before.sell, currency)}</span><small class="more">그대로</small>'
        now = moved_now.get(cell_item_key(key), False) if view.waiting else False
        if not view.written:
            if now is not False:
                return "red", _moved_cell(view.before, now, currency, reread(record))
            return "wait", _move(view.before, _with(view.before, view.waiting), currency) + _waiting_tag(view, steps)
        done = _with(view.before, view.after)
        moved = _move(view.before, done, currency)
        rest = ("" if not view.waiting else _moved_cell(done, now, currency, reread(record)) if now is not False
                else _move(done, _with(done, view.waiting), currency) + _waiting_tag(view, steps))
        if view.rolled_back_by:
            return "same", f'{moved}<span class="tag closed">되돌림 · 장부 {view.rolled_back_by}번</span>{rest}'
        if record.verified_at and not view.verified:
            seen = " · ".join(f"{FIELD_LABELS[name]} {'읽지 못함' if value is None else fmt_money(value, currency)}"
                              for name, value in view.seen.items())
            return "red", f'{moved}<small class="more">다시 읽은 값 {seen}</small>{rest}'
        if view.verified and record.verified_at:
            moved += '<span class="tag ok">확인</span>'
        elif waiting:   # 아직 저장하지 않은 칸이 있는 페이지에서는 저장한 칸도 저장했다고 단다
            moved += '<span class="tag ok">저장함</span>'
        return "wait" if rest else "", moved + rest

    if waiting:
        body += ["<h2>칸마다 넣은 값과 아직 넣지 않은 값</h2>",
                 f'<p class="sub">{esc(_waiting_intro(record, len(waiting) - moved_shown, moved_shown))}</p>']
    else:
        body.append("<h2>칸마다 넣은 값</h2>")
    body.append(grid(views, cell, reserved, closed, by_date))
    if nothing_left(record):   # ERP 에 이 변경의 값이 하나도 없다 — 손님 화면 · 되돌리는 법은 말하지 않는다
        body.append(notes([f"기록: {ledger_path}"]) if ledger_path else "")
    elif record.status in ("applied", "stopped"):
        undoes = _undoes(record)
        if stop is None:
            lines = ["손님 화면에는 길어야 5분 안에 새 가격이 보입니다. 결제 금액은 바로 새 가격입니다.",
                     "이미 받은 예약의 금액은 그대로입니다.", MARK_ON_ROLLBACK if undoes else MARK,
                     UNDO_ONCE if undoes else f'되돌리려면 대화창에서 "{record.id}번 되돌려" 또는 "방금 것 되돌려"라고 하세요.']
        else:   # 멈췄다 — 새 가격 · 출처 표시는 저장한 칸만이고, 되돌리는 법은 위의 「어떻게 할까요?」가 말한다
            saved = f"저장한 {len(written):,}칸은"
            lines = [f"{saved} 손님 화면에 길어야 5분 안에 새 가격으로 보입니다. 결제 금액은 바로 새 가격입니다.",
                     "이미 받은 예약의 금액은 그대로입니다.", f"{saved} ERP 에서 '손입력'으로 표시됩니다.", *([UNDO_ONCE] if undoes else [])]
        if ledger_path:
            lines.insert(3, f"기록: {ledger_path}")
        body.append(notes(lines))
    return page(title, "\n".join(body), MAKER)


def _chosen_table(record: ChangeRecord) -> str:
    """고르신 빨간 줄마다 — 빨간 줄 · 고르신 것 · 칸 수 · 고르실 때 하신 말(장부의 줄에서)."""
    request = decode_request(record.request) if record.request and record.request.get("kind") in ("change", "targets") else None
    entries = []
    for verdict, choice, said, keys in chosen_groups(record.rows):
        rule = CELL_RULES.by_code.get(verdict)
        words = (choice_words(request, choice, record.currency, [key_of_item(key) for key in keys]) if request
                 else CHOICE_LABELS[choice])
        entries.append((rule.label if rule else str(verdict), words, len(keys), said))
    return chosen_table(entries)


def _step_sizes(record: ChangeRecord) -> dict[int, int]:
    """저장 단계마다 그 저장이 쓰는 칸 수."""
    cells: dict[int, set[str]] = {}
    for row in record.rows:
        if row.action is not None and row.step is not None:
            cells.setdefault(row.step, set()).add(row.item_key)
    return {index: len(keys) for index, keys in cells.items()}


def _undone_banner(undone: Sequence[Mapping]) -> str:
    """「나머지 되돌리기」 — 이 변경에서 이미 되돌린 부분과 그 번호. 이번 되돌리기는 그 칸을 건드리지 않는다."""
    if not undone:
        return ""
    parts = []
    for item in undone:
        when = f" ({fmt_time(item['applied_at'])} 적용)" if item.get("applied_at") else ""
        parts.append(f"<li>장부 {item['change_id']}번 “{esc(item['sentence'])}”{esc(when)} — {item['cells']:,}칸 · "
                     f"{esc(item['scope'])}</li>")
    return (f'<div class="banner amber"><b>이 변경 가운데 {sum(item["cells"] for item in undone):,}칸은 이미 되돌렸습니다.</b> '
            f'이번 되돌리기는 그 칸을 건드리지 않고 나머지만 봅니다.<ul class="notes">{"".join(parts)}</ul></div>')


def render_rollback(plan: RollbackPlan, reserved: Iterable[tuple[str, str]] = (), scope: str = "", by_date: bool = False,
                    undone: Sequence[Mapping] = ()) -> str:
    currency = plan.currency
    what = "저장해 둔 상태로 되돌리기" if plan.mode == "restore" else "되돌리기"
    title = f"{what} 미리보기 · {plan.hotel} · {plan.offer}"
    reserved = set(reserved)
    restored = {key_of_item(item.key): item for item in plan.restored}
    kept = {} if plan.include_kept else {key_of_item(item.key): item for item in plan.kept}
    gone = {key_of_item(item.key): item for item in plan.unremovable}
    held = {**kept, **gone}
    befores = {key: value_of(item.now) for key, item in restored.items()}
    closed = {key for key, value in befores.items() if value.state == "closed"}
    closed |= {key for key, item in held.items() if item.now.state == "closed"}

    def cell(key: CellKey) -> tuple[str, str]:
        if key in held:
            sell = held[key].now.fields.get("sell")
            return "red", (f'<span class="now">{"가격 없음" if sell is None else fmt_money(sell, currency)}</span>'
                           f'<small class="more">{"지울 수 없음" if key in gone else "그대로 둠"}</small>')
        return "", _move(befores[key], _with(befores[key], restored[key].targets), currency)

    booked = sum((key.room, key.date) in reserved for key in restored)
    body = [f"<h1>{esc(title)}</h1>", rollback_head(plan, scope), _undone_banner(undone),
            stats([(len(restored), "되돌리는 칸"), (len(kept), "그대로 두는 칸"), (len(gone), "지울 수 없는 칸")]
                  + ([(booked, "되돌리는 칸 중 예약 있는 날")] if booked else [])),
            kept_table(plan, FIELD_LABELS), unremovable_table(plan, FIELD_LABELS),
            '<h2>되돌리는 칸' + (' <span class="sub">— 예약 있는 날도 포함합니다</span>' if booked else "") + "</h2>",
            grid([*restored, *held], cell, reserved, closed, by_date) if restored or held else
            '<p class="sub">되돌릴 칸이 없습니다.</p>',
            rollback_ask(plan, ROLLBACK_KEEPS + ((SEASON_SCREEN_NOTE,) if plan.mode == "restore" else ()))]
    return page(title, "\n".join(body), MAKER)


def _with(value: CellValue, fields: Mapping[str, Decimal | None]) -> CellValue:
    """`fields` 의 필드만 갈아 끼운 값. 없던 칸에 값을 넣으면 판매 가능한 칸이 된다."""
    merged = {name: fields[name] if name in fields else getattr(value, name) for name in FIELDS}
    return CellValue(merged["sell"], merged["list"], merged["supply"], "open" if value.state == "missing" else value.state)


def _example(snapshot: Snapshot) -> str:
    """페이지의 말 보기 — 읽은 첫 객실 · 첫 달과 그 오퍼의 통화에 맞는 금액(「12월 디럭스 +10」 · 원 오퍼면 「+10,000」)."""
    days = sorted({key.date for key in snapshot.cells} | set(snapshot.dates))
    room = min((room for room, _plan in snapshot.pairs), default="")
    month = f"{int(days[0][5:7])}월 " if days else ""
    return f"{month}{room} +{example_step(snapshot.currency)}".strip()


def render_prices(snapshot: Snapshot, by_date: bool = False) -> str:
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
                   (len(snapshot.reserved), "예약 있는 날 (객실 · 날짜)")]
                  + ([(len(snapshot.no_sale), "판매일 없는 날 (객실 · 날짜)")] if snapshot.no_sale else [])),
            grid(sorted(cells, key=lambda k: (k.room, k.rate_plan, k.date)), cell, set(snapshot.reserved), closed, by_date),
            *([f'<p class="sub">판매일 없음(판매일이 열리지 않은 날 — 칸이 없어 읽지 않았습니다): '
               + esc(" / ".join(f"{room} · {days_summary(day for r, day in snapshot.no_sale if r == room)}"
                                for room in sorted({r for r, _ in snapshot.no_sale}))) + "</p>"] if snapshot.no_sale else []),
            notes(["판매가는 굵게, 정가(손님 화면에 줄 그어 보이는 값)와 공급 원가는 작게 보입니다.",
                   f'바꾸고 싶으면 대화창에서 "{_example(snapshot)}" 처럼 말씀해 주세요. 바꾸기 전에 미리보기를 먼저 보여 드립니다.'])]
    return page(title, "\n".join(body), MAKER)


def render_compare(comparison: Comparison, scope: str = "", by_date: bool = False) -> str:
    """저장해 둔 상태와 견주기 — 칸마다 저장해 둔 값 → 지금 값(미리보기와 같은 칸 표)과 종류마다의 수. 아무것도 바꾸지 않았다."""
    currency, tally = comparison.currency, compare_counts(comparison)
    by_key = {item.key: item for item in comparison.cells}
    closed = {item.key for item in comparison.cells if item.now.state == "closed"}

    def cell(key: CellKey) -> tuple[str, str]:
        item = by_key[key]
        edited = f'<span class="tag chosen">날짜별로 바꿔 둔 값 · 장부 {item.edited_by}번</span>' if item.edited_by else ""
        if item.kind in MOVED:
            edited += (f'<span class="tag chosen">장부 {item.written_by}번이 넣은 값</span>' if item.written_by
                       else '<span class="tag wait">장부에 없는 변화</span>')
        if item.kind == "same":
            shown = "가격 없음" if item.now.sell is None else fmt_money(item.now.sell, currency)
            return "same", f'<span class="was">{shown}</span><small class="more">그대로</small>'
        if item.kind == "new":
            return "new", _move(item.then, item.now, currency) + '<span class="tag new">새로 생김</span>' + edited
        if item.kind == "gone":
            return "red", (f'<span class="was">{fmt_money(item.then.sell, currency)}</span><span class="tag red">없어짐</span>'
                           + edited)
        if item.kind == "closed":
            was, now = ("판매 가능", "판매 마감") if item.now.state == "closed" else ("판매 마감", "판매 가능")
            return "", f'<span class="now">{fmt_money(item.now.sell, currency)}</span><small class="more">{was} → {now}</small>'
        return "", _move(item.then, item.now, currency) + edited

    moved = tally["changed"] + tally["new"] + tally["gone"] + tally["closed"]
    title = f"저장해 둔 상태와 견주기 · {comparison.hotel} · {comparison.offer}"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub"><b>아무것도 바꾸지 않았습니다.</b> 장부 {comparison.saved}번에 저장해 둔 값({esc(fmt_time(comparison.saved_at))} 에 '
            f"ERP 에서 읽음)과 {esc(fmt_time(comparison.read_at))} 에 다시 읽은 값을 칸마다 견줍니다. 통화 {esc(currency)}.</p>",
            f'<div class="banner blue">저장할 때 하신 말: “{esc(comparison.sentence)}” (장부 {comparison.saved}번)'
            f'{f"<br>견주는 범위: {esc(scope)}" if scope else ""}</div>',
            stats([(tally["changed"], "바뀐 칸")]
                  + [(writer.cells, f"장부 {writer.change_id}번({writer.what})이 저장한 뒤 바꾼 칸") for writer in comparison.writers]
                  + ([(tally["outside"], "장부에 없는 변화")] if tally["outside"] else [])
                  + ([(tally["edited"], "날짜별로 바꿔 두었다가 바뀌거나 없어진 칸")] if tally["edited"] else [])
                  + ([(tally["reserved"], "바뀐 칸 중 예약 있는 날의 칸")] if tally["reserved"] else [])
                  + [(tally["new"], "새로 생긴 칸"), (tally["gone"], "없어진 칸")]
                  + ([(tally["closed"], "판매 마감 · 판매 가능만 바뀐 칸")] if tally["closed"] else [])
                  + [(tally["same"], "그대로인 칸")]),
            "<h2>칸마다 저장해 둔 값 → 지금 값</h2>",
            grid(list(by_key), cell, set(comparison.reserved), closed, by_date)]
    lines = [f"장부 {writer.change_id}번({writer.what} — “{writer.sentence}”, {fmt_time(writer.at)})이 저장한 뒤에 바꾼 칸 "
             f"{writer.cells:,}칸은 지금도 그 값입니다."
             + (f' 그 변경만 되돌리려면 "{writer.change_id}번 되돌려"라고 하세요.' if writer.what == "변경" else "")
             for writer in comparison.writers]
    if tally["outside"]:
        lines.append(f"장부에 없는 변화 {tally['outside']:,}칸은 도우미 밖(ERP 화면 · 시즌 채우기 · 다른 컴퓨터)에서 바뀌었습니다. "
                     + HAND_EDITS + (" 「날짜별로 바꿔 둔 값」은 이 컴퓨터의 장부에 적힌 도우미의 변경만입니다." if tally["edited"] else ""))
    if tally["reserved"]:
        lines.append("예약 있는 날의 칸도 바뀌었습니다. 이미 받은 예약의 금액은 바뀌지 않습니다.")
    if tally["new"]:
        lines.append("새로 생긴 칸은 저장해 둔 상태로 되돌려도 지울 수 없습니다. ERP 에 칸을 지우는 길이 없어서입니다.")
    if tally["closed"]:
        lines.append("판매 마감 · 판매 가능은 저장해 둔 상태로 되돌려도 돌아가지 않습니다.")
    body.append(notes(lines))
    body.append(f'<div class="banner blue">저장해 둔 값으로 되돌리려면 대화창에서 "{comparison.saved}번 상태로 되돌려"라고 하세요. 바로 '
                "바꾸지 않고, 무엇이 돌아가고 무엇이 돌아가지 않는지 미리보기로 먼저 보여 드립니다.</div>" if moved else
                '<div class="banner blue">저장해 둔 때와 모든 칸이 같습니다.</div>')
    return page(title, "\n".join(body), MAKER)


def _child_tag(figure) -> str:
    """아동이 든 값에 퍼센트를 곱한 값이면 어느 뜻으로 셈했는지 — 「아동 칸 %: 칸 전체에 곱함」 · 「… 성인 몫에만 …」."""
    return f'<span class="tag chosen">아동 칸 %: {esc(CHILD_READINGS[figure.child])}</span>' if figure.child else ""


def _sheet_cell(line: SheetLine, currency: str) -> str:
    """요금표 칸 하나 — 그 줄의 인원 · 박수마다 값(요금표에 적힌 차례). 셈한 값은 「계산」 꼬리표와 셈, 아동이 든 값에 퍼센트를
    곱한 값은 어느 뜻으로 셈했는지의 꼬리표(F2)."""
    parts = [f'<small class="more">{line.no}번째 줄</small>']
    for (occupancy, nights), values in line_figures(line, currency).items():
        sell = values["sell"]
        parts.append(f'<div>{esc(line_label(occupancy, nights))} <span class="now">{fmt_money(sell.value, currency)}</span>'
                     + ('<span class="tag new">계산</span>' if sell.formula else "") + _child_tag(sell) + "</div>")
        for name, figure in values.items():
            if name != "sell":
                parts.append(f'<small class="more">{FIELD_LABELS[name]} {fmt_money(figure.value, currency)}'
                             f'{" (계산)" if figure.formula else ""}</small>{_child_tag(figure)}')
        parts += [f'<small class="more">{FIELD_LABELS[name]} = {esc(figure.formula)}</small>'
                  for name, figure in values.items() if figure.formula]
    return "".join(parts)


def _child_percents(lines, currency: str) -> dict[str, int]:
    """아동이 든 값에 퍼센트를 곱한 값의 수 — 뜻마다(whole · adults)."""
    found: dict[str, int] = {}
    for line in lines:
        for values in line_figures(line, currency).values():
            for figure in values.values():
                if figure.child:
                    found[figure.child] = found.get(figure.child, 0) + 1
    return found


def render_sheet(check: SheetCheck) -> str:
    sheet, currency = check.sheet, check.sheet.currency
    title = f"요금표를 이렇게 읽었습니다 · {sheet.hotel} · {sheet.offer}"
    lines, known = check.selected, set(check.hotel_pairs)
    days = sorted({day for line in lines for day in line.days})
    columns: dict[tuple, list[SheetLine]] = {}
    for line in sorted(lines, key=lambda item: (item.days[0], item.no)):
        columns.setdefault((line.season, line.periods), []).append(line)
    pairs = list(dict.fromkeys((line.room, line.rate_plan) for line in lines))
    heads = "".join(f'<th class="days">{f"<b>{esc(season)}</b><br>" if season else ""}{esc(periods_label(periods))}</th>'
                    for season, periods in columns)
    rows = []
    for room, plan in pairs:
        tag = "" if (room, plan) in known else '<span class="tag blocked">호텔에 없음</span>'
        tds = []
        for members in columns.values():
            mine = [line for line in members if (line.room, line.rate_plan) == (room, plan)]
            tds.append(f'<td class="text">{"".join(_sheet_cell(line, currency) for line in mine)}</td>' if mine
                       else '<td class="none">—</td>')
        rows.append(f'<tr><td class="text">{esc(room)} · {esc(plan)}{tag}</td>{"".join(tds)}</tr>')
    facts = [("호텔", sheet.hotel), ("오퍼", sheet.offer), ("통화", currency), ("요금표 줄", f"{len(lines):,}줄"),
             ("날짜", f"{days[0]} ~ {days[-1]}"), ("칸", f"{len(check.cells):,}칸 (날짜마다 인원 · 박수 하나씩, 호텔에 있는 객실 · 요금제만)")]
    if not check.part.whole:
        window = f"{check.part.first or '처음'} ~ {check.part.last or '끝'}" if check.part.first or check.part.last else ""
        facts.append(("이번에 하는 부분", " / ".join(part for part in (" · ".join(check.part.rooms), window) if part)))
    sentence = f'<p class="sub">요청: “{esc(sheet.sentence)}”</p>' if sheet.sentence else ""
    body = [f"<h1>{esc(title)}</h1>",
            '<p class="sub"><b>아직 이 요금표의 범위로 ERP 의 가격을 읽지 않았고, 아무것도 바뀌지 않았습니다.</b> 종이 요금표와 한 줄씩 견주어 봐 주세요.</p>',
            f'<div class="frame">{sentence}<dl class="kv">'
            + "".join(f"<dt>{esc(name)}</dt><dd>{esc(value)}</dd>" for name, value in facts) + "</dl></div>"]
    for gap in check.gaps:
        nos = ", ".join(f"{no}번째 줄" for no in gap.lines)
        if gap.kind == "unknown":
            body.append(f'<div class="banner amber"><b>호텔(이 오퍼)에 없는 객실 · 요금제</b> {esc(gap.room)} · {esc(gap.rate_plan)} '
                        f'({esc(nos)}) — 이 줄은 넣지 않습니다. 이름을 잘못 옮겼으면 알려 주세요.</div>')
        else:
            body.append(f'<div class="banner blue"><b>요금표에 없는 객실 · 요금제</b> {esc(gap.room)} · {esc(gap.rate_plan)} '
                        "— 가격을 그대로 둡니다.</div>")
    children = _child_percents(lines, currency)
    if children:
        said = " · ".join(f"{CHILD_READINGS[reading]} {count}개" for reading, count in children.items())
        body.append(f'<div class="banner amber"><b>아동이 든 값의 퍼센트</b> {esc(said)} — 「아동 칸 %」 꼬리표가 붙은 값입니다. 퍼센트를 칸 '
                    "전체에 곱했는지, 성인 몫에만 곱하고 아동 추가분은 그대로 두었는지(ERP 의 퍼센트 가감은 이쪽) 꼬리표와 셈에 적었습니다. "
                    "말씀하신 뜻과 다르면 알려 주세요.</div>")
    body += ["<h2>요금표</h2>",
             f'<div class="scroll"><table><tr><th>객실 · 요금제</th>{heads}</tr>{"".join(rows)}</table></div>']
    reads, scope = check.reads, check.range
    if scope is not None:
        body.append("<h2>맞으면 ERP 에서 읽을 것</h2>"
                    f'<p class="sub">객실 · 요금제 {len(scope.pairs)}개 × {len(scope.dates):,}일({scope.dates[0]} ~ {scope.dates[-1]}, '
                    "요금표가 비운 날도 읽어 「요금표에 없는 칸」을 댑니다). 페이지 작업은 가격 읽기 "
                    f"{reads['readPair']}번, 예약 있는 날 읽기 {reads['readReserved']}번(숨은 줄이 있으면 더), 그리고 읽은 화면 조각마다 "
                    "받기(800자에 한 번)입니다.</p>")
        if not reads["fits"]:
            body.append(f'<div class="banner amber">읽기 한 번은 가격 읽기와 예약 있는 날 읽기를 합쳐 {reads["limit"]}번까지라, '
                        "이 요금표는 객실이나 기간을 나눠 한 부분씩 읽고 바꿉니다.</div>")
    body += [notes([f"「계산」 꼬리표가 붙은 값은 요금표가 차이(+금액 · %)로 적은 값을 도우미의 명령이 셈한 것입니다. 셈은 값 아래에 적었습니다. "
                    + _rounding_note(currency),
                    "나머지 숫자는 요금표에 적힌 그대로 옮겼습니다.",
                    "요금표와 다른 곳이 있으면 몇 번째 줄인지 말씀해 주세요."]),
             '<div class="banner blue">맞으면 대화창에서 "맞아"라고 해 주세요. 그때 ERP 에서 지금 가격을 읽어 미리보기를 만듭니다.</div>']
    return page(title, "\n".join(body), MAKER)
