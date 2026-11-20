"""price_pages.py — 가격 칸 페이지. 틀(색·머리 숫자·저장 단계·되돌리기 띠)은 `change_core.chrome` 이 그리고,
여기서는 칸 표(객실·요금제마다 표 하나, 줄은 인원·박수, 열은 날짜 — 그림의 모양 가)와 가격 말을 그린다.

    render_preview(plan)       미리보기 — 칸 표, 빨간 줄·적용할 수 없음 띠, 머리 숫자, 따로 볼 칸
    render_result(record)      적용 결과 — 장부의 변경 하나: 저장 단계마다 된 것·멈춘 것, 다시 읽어 맞았는지
    render_rollback(plan)      되돌리기 미리보기 — 되돌리는 날짜, 그대로 두는 칸의 세 값과 까닭, 되돌리는 칸
    render_prices(snapshot)    지금 가격 보기 — 바꾸지 않고 표로만
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
    esc, fmt_money, fmt_time, kept_table, notes, page, result_banner, rollback_ask, rollback_head, stats, steps_list,
    stopped_choices, unremovable_table,
)
from change_core.ledger import ChangeRecord
from change_core.money import scale_of
from change_core.rollback import RollbackPlan
from change_core.rules import BLOCKED, RED

from price_model import (
    CELL_RULES, CHOICE_LABELS, CLOSED, FIELD_LABELS, FIELDS, GAP_KINDS, NEW, RESERVED, SKIP_LABELS, TargetTable, CellChange, CellKey,
    CellValue, ChangeRequest, Gap, Plan, Snapshot, cell_name, day_label, key_of_item, line_label, nights_label, occupancy_label,
    encode_key, occupancy_order, split_occupancy, value_of,
)
from price_plan import counts, day_runs, days_summary
from price_sheet import SheetCheck, SheetLine, coverage_counts, line_figures, periods_label, runs_label

MAKER = "어딩 Stay 가격 변경 도우미"
# 요금표로 날짜별 가격을 맞춘 미리보기 · 결과가 꼭 다는 한 문장(결정 32). SKILL.md 도 도우미가 이 문장 그대로 말하게 한다.
SEASON_REFILL_NOTE = ("여기서 날짜별로 바꾼 가격은 누가 ERP 시즌 화면에서 그 시즌의 [가격]을 '덮기'(이미 값이 있는 날도 덮기)로 "
                      "다시 채우면 옛 요금으로 돌아갑니다.")
ONE_COLUMN_PER_DATE_UP_TO = 7        # 날짜가 이만큼까지는 날짜마다 열 하나. 넘으면 칸이 모두 같은 날끼리 열 하나(결정 33A)
# 미리보기 안내 — 그런 칸이 있을 때만 단다
RESERVED_NOTE = "예약 있는 날도 똑같이 바꿉니다. 이미 받은 예약의 금액은 바뀌지 않습니다."
CLOSED_NOTE = "판매 마감인 날은 값만 바뀌고 마감은 그대로입니다."


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
                  + [(tally["blocked"], "적용할 수 없는 칸")]
                  + ([(tally["reserved"], "예약 있는 날의 칸 (바꿉니다)")] if tally["reserved"] else [])
                  + ([(tally["closed"], "판매 마감인 칸 (값만 바뀌고 마감은 그대로)")] if tally["closed"] else [])
                  + [(tally["skipped"], "건너뛰는 칸")] + ([(tally["new"], "새로 생기는 칸")] if tally["new"] else [])),
            _skip_line(plan), _tiers_line(plan), _coverage_section(plan.coverage) if sheet else ""]
    if tally["red"]:
        body.append(f'<p class="sub">빨간 줄 {tally["red"]:,}칸을 어떻게 할지 고르시면 ERP 에 몇 번 나눠 저장하는지 정해집니다. '
                    "그때 미리보기를 다시 보여 드립니다.</p>")
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
        body += [notes(lines),
                 '<div class="banner blue">말씀이 없으면 아무것도 바뀌지 않습니다. 대화창에서 "적용"이라고 하시면 바꿉니다.</div>']
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
    body += [notes(lines),
             '<div class="banner blue">말씀이 없으면 아무것도 바뀌지 않습니다. 대화창에서 "적용"이라고 하시면 바꿉니다.</div>']
    return page(title, "\n".join(body), MAKER)


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
    """고른 빨간 줄 — 규칙 · 고름마다 칸 수, 그 고름의 이름, 저장이 하는 일, 첫 칸의 예(바뀌는 값)."""
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
                            example=f"{cell_name(example.key)} —{shown}" if shown else ""))
    return out


EXAMPLES = 3   # 빨간 줄마다 plan 의 답에 싣는 칸의 예


def _preview_banners(plan: Plan, tally: Mapping) -> str:
    """머리 띠 — 적용할 수 없는 칸, 아직 고르지 않은 빨간 줄(규칙마다), 고른 빨간 줄(규칙마다, 고른 것과 그 칸의 예 하나)."""
    out = []
    blocked = [rule for rule in CELL_RULES.rules if rule.severity == BLOCKED and tally[rule.code]]
    if blocked:
        reasons = " · ".join(f"{rule.label} {tally[rule.code]}칸" for rule in blocked)
        out.append(f'<div class="banner amber"><b>적용할 수 없음 · {tally["blocked"]}칸</b> ERP 가 받지 않는 값이라 이 칸은 '
                   f'바꾸지 않습니다. ({esc(reasons)})</div>')
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
    for code, lines in by_rule.items():
        parts = [f"<li><b>{esc(line['words'])} · {line['cells']:,}칸</b> {esc(line['does'])}"
                 + (f' <span class="sub">예: {esc(line["example"])}</span>' if line["example"] else "") + "</li>" for line in lines]
        out.append(f'<div class="banner amber"><b>고르신 빨간 줄 · {sum(line["cells"] for line in lines):,}칸 '
                   f'({esc(CHOSEN_GROUPS[code])})</b><ul class="notes">{"".join(parts)}</ul></div>')
    if not tally["red"] and not tally["blocked"]:
        out.append('<div class="banner ok">' + ("남은 빨간 줄이 없습니다. 고르신 대로 저장합니다." if tally["chosen"] else
                                               "빨간 줄이 없습니다.") + "</div>")
    return "\n".join(out)


def _flagged_section(plan: Plan, currency: str) -> str:
    flagged = [change for change in plan.changes if change.verdict]
    if not flagged:
        return ""
    rows = []
    for change in flagged:
        rule = CELL_RULES.by_code[change.verdict]
        after = change.after or change.before
        if change.choice == "keep":
            moved = "그대로"
        else:
            moved = "—" if change.after is None else _move(change.before, change.after, currency)
        if change.choice:   # 고른 뒤에는 고른 것과 그 결과(앞 칸들의 값)만 — 걸렸던 까닭은 쓰지 않는다
            why = (f'<span class="tag chosen">고름</span> '
                   f'{esc(choice_words(plan.request, change.choice, currency, [change.key]))}')
            choices = "고르신 대로 저장합니다"
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
    """장부의 줄(필드마다 하나)을 칸 하나로 모은 것."""
    before: CellValue
    after: dict = field(default_factory=dict)
    written: bool = False
    verified: bool = True
    seen: dict = field(default_factory=dict)
    reserved: bool = False
    rolled_back_by: int | None = None


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


def render_result(record: ChangeRecord, ledger_path: str | None = None, by_date: bool = False) -> str:
    currency = record.currency
    views = cell_views(record)
    written = [view for view in views.values() if view.written and not view.rolled_back_by]
    undone = sorted({view.rolled_back_by for view in views.values() if view.rolled_back_by})
    undone_count = sum(1 for view in views.values() if view.rolled_back_by)
    mismatched = [view for view in written if record.verified_at and not view.verified]
    kind = "되돌리기 결과" if record.kind == "rollback" else "적용 결과"
    title = f"{kind} · {record.hotel} · {record.offer}"
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub">장부 {record.id}번 · 요청 “{esc(record.sentence)}”'
            f'{f" · {record.reverses}번 변경을 되돌림" if record.reverses else ""} · 통화 {esc(currency)}</p>',
            result_banner(record, len(written), len(mismatched))]
    if undone:
        body.append(f'<p class="sub">이 변경의 {undone_count:,}칸은 뒤에 되돌렸습니다(장부 '
                    f'{", ".join(f"{number}번" for number in undone)}).</p>')
    if (record.request or {}).get("from_sheet"):
        body.append(f'<div class="banner amber">{esc(SEASON_REFILL_NOTE)}</div>')
    body += [steps_list(record.steps), stopped_choices(record)]
    closed = {key for key, view in views.items() if view.before.state == "closed"}
    reserved = {(key.room, key.date) for key, view in views.items() if view.reserved}

    def cell(key: CellKey) -> tuple[str, str]:
        view = views[key]
        if not view.written:
            return "same", f'<span class="was">{fmt_money(view.before.sell, currency)}</span><small class="more">그대로</small>'
        moved = _move(view.before, _with(view.before, view.after), currency)
        if view.rolled_back_by:
            return "same", f'{moved}<span class="tag closed">되돌림 · 장부 {view.rolled_back_by}번</span>'
        if record.verified_at and not view.verified:
            seen = " · ".join(f"{FIELD_LABELS[name]} {'읽지 못함' if value is None else fmt_money(value, currency)}"
                              for name, value in view.seen.items())
            return "red", f'{moved}<small class="more">다시 읽은 값 {seen}</small>'
        return "", moved + ('<span class="tag ok">확인</span>' if view.verified and record.verified_at else "")

    body += ["<h2>칸마다 넣은 값</h2>", grid(views, cell, reserved, closed, by_date)]
    if record.status in ("applied", "stopped"):
        lines = ["손님 화면에는 길어야 5분 안에 새 가격이 보입니다. 결제 금액은 바로 새 가격입니다.",
                 "이미 받은 예약의 금액은 그대로입니다.",
                 "이 칸들은 ERP 에서 '손입력'으로 표시됩니다.",
                 f'되돌리려면 대화창에서 "{record.id}번 되돌려" 또는 "방금 것 되돌려"라고 하세요.']
        if ledger_path:
            lines.insert(3, f"기록: {ledger_path}")
        body.append(notes(lines))
    return page(title, "\n".join(body), MAKER)


def render_rollback(plan: RollbackPlan, reserved: Iterable[tuple[str, str]] = (), scope: str = "", by_date: bool = False) -> str:
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

    body = [f"<h1>{esc(title)}</h1>", rollback_head(plan, scope),
            stats([(len(restored), "되돌리는 칸"), (len(kept), "그대로 두는 칸"), (len(gone), "지울 수 없는 칸"),
                   (sum((key.room, key.date) in reserved for key in restored), "되돌리는 칸 중 예약 있는 날")]),
            kept_table(plan, FIELD_LABELS), unremovable_table(plan, FIELD_LABELS),
            '<h2>되돌리는 칸 <span class="sub">— 예약 있는 날도 포함합니다</span></h2>',
            grid([*restored, *held], cell, reserved, closed, by_date) if restored or held else
            '<p class="sub">되돌릴 칸이 없습니다.</p>',
            rollback_ask(plan)]
    return page(title, "\n".join(body), MAKER)


def _with(value: CellValue, fields: Mapping[str, Decimal | None]) -> CellValue:
    """`fields` 의 필드만 갈아 끼운 값. 없던 칸에 값을 넣으면 판매 가능한 칸이 된다."""
    merged = {name: fields[name] if name in fields else getattr(value, name) for name in FIELDS}
    return CellValue(merged["sell"], merged["list"], merged["supply"], "open" if value.state == "missing" else value.state)


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
                   '바꾸고 싶으면 대화창에서 "12월 디럭스 +10,000" 처럼 말씀해 주세요. 바꾸기 전에 미리보기를 먼저 보여 드립니다.'])]
    return page(title, "\n".join(body), MAKER)


def _sheet_cell(line: SheetLine, currency: str) -> str:
    """요금표 칸 하나 — 그 줄의 인원 · 박수마다 값(요금표에 적힌 차례). 셈한 값은 「계산」 꼬리표와 셈."""
    parts = [f'<small class="more">{line.no}번째 줄</small>']
    for (occupancy, nights), values in line_figures(line, currency).items():
        sell = values["sell"]
        parts.append(f'<div>{esc(line_label(occupancy, nights))} <span class="now">{fmt_money(sell.value, currency)}</span>'
                     + ('<span class="tag new">계산</span>' if sell.formula else "") + "</div>")
        for name, figure in values.items():
            if name != "sell":
                parts.append(f'<small class="more">{FIELD_LABELS[name]} {fmt_money(figure.value, currency)}'
                             f'{" (계산)" if figure.formula else ""}</small>')
        parts += [f'<small class="more">{FIELD_LABELS[name]} = {esc(figure.formula)}</small>'
                  for name, figure in values.items() if figure.formula]
    return "".join(parts)


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
            '<p class="sub"><b>아직 ERP 에서 아무것도 읽지 않았고, 아무것도 바뀌지 않았습니다.</b> 종이 요금표와 한 줄씩 견주어 봐 주세요.</p>',
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
