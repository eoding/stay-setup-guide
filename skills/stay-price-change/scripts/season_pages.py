"""season_pages.py — 시즌 다시 채우기의 페이지. 틀은 `change_core.chrome`, 칸 표는 `price_pages.grid` 를 쓴다.

    render_preview(plan, change_id, steps, by_date)   미리보기 — 저장마다 창에 칠 값 · 칸 표, 바구니(바뀌는 · 새로 생기는 · 날짜별로 바꿔
                                                      둔 · 예약 · 다른 시즌 날 · 마감 · 예전 칸 · 판매일 없는 날 · 같은 값 · 조합으로 빠질
                                                      수 있는), 빨간 줄과 고를 것, 요금표와 다른 칸, 되돌려도 돌아오지 않는 것
    render_result(record, ledger_path, by_date)       적용 결과 — 칸마다 넣은 값 · 다시 읽은 값, ERP 가 말한 칸 수와 예상, 「확인했습니다」는
                                                      값 · 칸 수 · 새 칸의 판매 상태가 모두 맞을 때만. 멈춘 변경은 가격 칸의 결과 페이지가
                                                      말하고(마지막 check 대로) 이 페이지의 시즌 줄이 붙는다
    rollback_notes(season)                            되돌리기 미리보기에 붙는 것 — 되돌려도 돌아오지 않는 것 · 창의 이전 입력값

글은 쉬운 우리말이다. 미리 읽은 값을 「지금」이라고 하지 않는다(A5).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from change_core.chrome import esc, fmt_money, fmt_time, notes, page, result_word, stats, stop_view, stopped_choices, steps_list, times_word
from change_core.ledger import ChangeRecord
from change_core.money import scale_of
from price_model import CLOSED, FIELD_LABELS, FIELDS, RESERVED, CellKey, CellValue, cell_name, key_of_item
from price_pages import MAKER, cell_views, grid, render_result as render_cells_result
from price_season import (
    CHOICE_WORDS, FRACTION_SENTENCE, INPUT_LABELS, KEEPS, RULES, SeasonPlan, banner_counts, counts, counts_agree, date_runs,
    decode_counts, rule_choices, verdict,
)
from price_season_cli import OPENS_CLOSED

# 되돌려도 돌아오지 않는 것(설계 5) — 미리보기 · 되돌리기 미리보기가 그대로 말한다
UNDO_CREATED = "새로 생기는 칸 {n}칸은 되돌려도 지울 수 없습니다(ERP 에 칸을 지우는 길이 없습니다)."
UNDO_WHAT = ("되돌리기는 가격 캘린더에서 날짜별로 전 값을 다시 넣는 것입니다. 시즌 창의 마지막 입력값은 이번에 친 값으로 남고, 덮인 칸이 "
             "원래 어느 시즌 것이었는지와 ERP 의 '손입력' 표시는 되돌아가지 않습니다.")
UNDO_EMPTY = "정가·공급 원가가 비어 있던 칸 {n}칸에 값을 넣습니다. 되돌릴 때는 그 칸마다 한 번씩 {n}번 저장해야 해서 오래 걸립니다."
UNDO_REFILL = "되돌린 뒤 누가 이 시즌을 '덮기'로 다시 채우면 이번 값이 다시 들어갑니다."
NO_DELETE = "도우미는 시즌 창의 '이번에 고르지 않은 인원·요금제 가격 지우기'를 켜지 않습니다 — 이번 채우기에 없는 예전 칸은 예전 값으로 남습니다."
GUESS = "「날짜별로 따로 넣은 것으로 보이는 칸」 · 객실 조합으로 빠질 수 있는 칸 · 새 칸의 판매 마감은 도우미의 짐작입니다(ERP 가 그 표시를 보이지 않습니다)."
BUCKETS = (   # 미리보기 바구니 — (코드, 머리, 덧말). 차례가 보이는 차례다
    ("helper_edited", "장부가 날짜별로 바꿔 둔 칸", "이 장부의 날짜별 변경이 넣은 값을 시즌 값으로 덮습니다."),
    ("looks_edited", "날짜별로 따로 넣은 것으로 보이는 칸", "같은 줄의 다른 날과 값이 달라 따로 넣은 것으로 보입니다(짐작) — 시즌 값으로 덮습니다."),
    ("reserved", "예약 있는 날의 칸", "다른 칸처럼 바뀝니다. 이미 받은 예약의 금액은 그대로입니다."),
    ("other_season", "다른 시즌 날짜에도 드는 날의 칸", "덮으면 이 시즌의 칸이 됩니다."),
    ("closed", "판매 마감인 칸", "값만 바뀌고 마감은 그대로입니다."),
)


def _money(value: Decimal | None, currency: str, empty: str = "비어 있음") -> str:
    return empty if value is None else fmt_money(value, currency)


def _move(before: CellValue, after: CellValue, currency: str) -> str:
    parts = []
    for name in FIELDS:
        old, new = getattr(before, name), getattr(after, name)
        if old == new:
            continue
        was, now = ("새로" if old is None else fmt_money(old, currency)), ("비움" if new is None else fmt_money(new, currency))
        if name == "sell":
            parts.insert(0, f'<span class="was">{was}</span><span class="arrow">→</span><span class="now">{now}</span>')
        else:
            parts.append(f'<small class="more">{FIELD_LABELS[name]} {was} → {now}</small>')
    return "".join(parts)


def _days(days: Sequence[str]) -> str:
    runs = date_runs(days)
    shown = ", ".join(runs[:6]) + (" …" if len(runs) > 6 else "")
    return f"{shown} ({len(days):,}일)"


def _inputs(plan: SeasonPlan, save) -> str:
    """저장 하나가 창에 칠 값 — 칸 이름 · 글자 그대로(빈 칸은 「비움」), 아동 칸, 덮기, 날짜, 어디서 온 값인지."""
    rows = [("객실 · 요금제", ", ".join(f"{room} · {rate_plan}" for room, rate_plan in save.save.pairs))]
    sources = dict(save.save.sources)
    for name, label in INPUT_LABELS.items():
        text = save.save.text(name)
        source = f" — {sources[name]}" if sources.get(name) else ""
        rows.append((label, (f"「{text}」" if text else "비움") + source))
    typed = save.save.child()
    for item in plan.window.child:
        if item.kind == "amount":
            text = typed.get(item.code, "")
            rows.append((f"아동 추가 금액 {item.code}", f"「{text}」" if text else f"비움(구간 기본값 {item.blank or '없음'})"))
        elif item.kind == "percent":
            rows.append((f"아동 {item.code}", item.text))
    rows.append(("이미 값이 있는 날도 덮기", "켬" if save.save.overwrite else "끔 — 값이 없는 칸에만 넣습니다"))
    rows.append(("날짜", "시즌 전체 " + _days(plan.window.dates) if save.save.dates is None else "고른 날 " + _days(save.dates)))
    if save.excluded:
        rows.append(("빼는 날", _days(save.excluded) + " — 고르신 대로 이 날은 채우지 않습니다"))
    rows.append(("지우기", "켜지 않음"))
    return '<dl class="kv">' + "".join(f"<dt>{esc(name)}</dt><dd>{esc(value)}</dd>" for name, value in rows) + "</dl>"


def _rule_label(code: str) -> str:
    return RULES[code][0] if code in RULES else KEEPS[code]


def _rule_banner(plan: SeasonPlan, save) -> str:
    """저장 하나의 막힘 · 빨간 줄 — 무엇이 몇 칸 · 며칠에 걸렸고, 고를 수 있는 것. 칸 하나만 그대로 두는 것은 없다."""
    out = []
    if save.refused:
        out.append(f'<div class="banner red"><b>{save.index}번째 저장은 ERP 창이 거절할 입력입니다.</b> “{esc(save.refused)}” — 요청을 고쳐 '
                   "미리보기를 다시 만듭니다.</div>")
    for code in RULES:
        keys = save.hits.get(code)
        if not keys or code == "ERP_REFUSES":
            continue
        days = save.hit_dates(code)
        chosen = save.choices.get(code)
        choices = " · ".join(f"「{CHOICE_WORDS[choice]}」" for choice in rule_choices(code))
        offered = choices if len(days) < len(save.dates) or "include" in rule_choices(code) else "「요청을 고침」"
        if chosen:
            text = f"고르신 것: {CHOICE_WORDS[chosen.choice]} (“{esc(chosen.said)}”)"
            color = "amber"
        else:
            color = "red"
            text = (f"고를 것: {offered} · 「요청을 고침」. 창은 칸 하나를 뺄 수 없어 칸마다 고르지 않습니다."
                    + (" 그 날을 빼면 남는 날이 없어 「그 날은 빼고 채움」은 이 저장을 통째로 빼는 것입니다." if len(days) >= len(save.dates) else ""))
        extra = f" {FRACTION_SENTENCE}" if code == "WHOLE_UNIT_FRACTION" else ""
        out.append(f'<div class="banner {color}"><b>{save.index}번째 저장 · {esc(_rule_label(code))} — {len(keys):,}칸 · {len(days):,}일</b>'
                   f"{esc(extra)}<br>{text}</div>")
    return "".join(out)


def _cell_table(keys: Iterable[CellKey], show) -> str:
    rows = "".join(f'<tr><td class="text">{esc(cell_name(key))}</td>{show(key)}</tr>' for key in keys)
    return f'<div class="scroll"><table>{rows}</table></div>' if rows else ""


def _bucket_sections(plan: SeasonPlan, save) -> str:
    currency = plan.currency
    by_key = {change.key: change for change in save.changes}
    out = []
    for code, title, words in BUCKETS:
        keys = [change.key for change in save.changes if CLOSED in change.marks] if code == "closed" else list(save.hits.get(code, ()))
        if not keys:
            continue
        def show(key, change=None):
            change = by_key[key]
            owner = next((mark.split(":", 1)[1] for mark in change.marks if mark.startswith(("helper_edited:", "other_season:"))), "")
            tag = f" (장부 {owner}번)" if code == "helper_edited" else ""
            if code == "other_season":
                season = next((item.name for item in plan.window.seasons if item.id == owner), owner)
                tag = f" (시즌 「{season}」)"
            return f"<td>{_move(change.before, change.after, currency)}{esc(tag)}</td>"
        out.append(f"<h3>{esc(title)} · {len(keys):,}칸</h3><p class=\"sub\">{esc(words)}</p>{_cell_table(keys, show)}")
    if save.left_old:
        out.append(f"<h3>이번 채우기에 없는 예전 칸 · {len(save.left_old):,}칸</h3><p class=\"sub\">{esc(NO_DELETE)}</p>")
    if save.no_sale:
        days: dict[str, list[str]] = {}
        for room, day in save.no_sale:
            days.setdefault(room, []).append(day)
        out.append(f"<h3>판매일 없는 날 · {save.counts.skipped:,}칸</h3><p class=\"sub\">아무것도 넣지 않습니다(판매일 탭에서 먼저 열어야 "
                   "합니다): " + esc(" / ".join(f"{room} {_days(sorted(set(items)))}" for room, items in days.items())) + "</p>")
    if save.same:
        out.append(f'<p class="sub">값은 같고 이 시즌 칸이 되는 칸 {save.same:,}칸 — 표에 없습니다.</p>')
    if save.untouched:
        out.append(f'<p class="sub">덮기를 꺼서 그대로 두는 칸(이미 값이 있음) {save.untouched:,}칸.</p>')
    maybe = [change.key for change in save.changes if "combo_unknown" in change.marks]
    if maybe:
        out.append(f"<h3>ERP 가 객실 조합으로 뺄 수 있는 칸 · {len(maybe):,}칸</h3><p class=\"sub\">ERP 가 객실의 허용 인원 조합 밖이면 "
                   "넣지 않습니다. 객실 이름이 객실 타입 이름과 달라 도우미가 그 조합을 읽지 못했습니다(짐작) — 적용 뒤에 다시 읽어 넣었는지 "
                   "봅니다.</p>")
    if save.combo_skipped:
        out.append('<p class="sub">객실의 허용 인원 조합 밖이라 ERP 가 넣지 않는 줄: '
                   + esc(" · ".join(f"{room} {key}" for room, key in save.combo_skipped)) + "</p>")
    return "".join(out)


def _misses_section(plan: SeasonPlan) -> str:
    if not plan.misses:
        return ""
    currency = plan.currency
    rows = []
    for miss in plan.misses[:200]:
        sheet = " · ".join(f"{FIELD_LABELS[name]} {_money(value, currency)}" for name, value in miss.sheet.items())
        filled = "칸 없음" if miss.fill is None else " · ".join(f"{FIELD_LABELS[name]} {_money(miss.fill.get(name), currency)}"
                                                              for name in miss.sheet)
        rows.append(f'<tr><td class="text">{esc(cell_name(miss.key))}</td><td>{esc(sheet)}</td><td class="red">{esc(filled)}</td>'
                    f"<td>{miss.line}번째 줄</td></tr>")
    more = f'<p class="sub">… 모두 {len(plan.misses):,}칸(처음 200칸만 보입니다)</p>' if len(plan.misses) > 200 else ""
    return (f'<h2>요금표와 다르게 채워지는 칸 · {len(plan.misses):,}칸</h2><div class="banner red">시즌 창은 시즌의 모든 날에 같은 값을 넣어 '
            "이 칸들을 요금표 값으로 만들지 못합니다. 고를 것: 「이대로 채움」(채운 뒤 이 칸들을 날짜별 변경으로 맞추는 것을 바로 내놓습니다) · "
            "「그 날은 빼고 채움」 · 채우지 않음.</div><div class=\"scroll\"><table><tr><th>칸</th><th>요금표</th><th>채운 뒤</th><th>요금표 줄"
            f"</th></tr>{''.join(rows)}</table></div>{more}")


def undo_lines(plan: SeasonPlan) -> list[str]:
    created = sum(change.before.state == "missing" for change in plan.changes)
    emptied = sum(1 for change in plan.changes if change.before.state != "missing"
                  and any(getattr(change.before, name) is None and getattr(change.after, name) is not None for name in ("list", "supply")))
    lines = [UNDO_CREATED.format(n=f"{created:,}")] if created else []
    lines.append(UNDO_WHAT)
    if emptied:
        lines.append(UNDO_EMPTY.format(n=f"{emptied:,}"))
    lines.append(UNDO_REFILL)
    return lines


def render_preview(plan: SeasonPlan, change_id: int | None = None, steps: Sequence | None = None, by_date: bool = False) -> str:
    window, currency, tally = plan.window, plan.currency, counts(plan)
    title = f"미리보기 · {window.hotel} · {window.offer} · 시즌 「{window.season_name}」 다시 채우기"
    sentence = f'<p class="sub">요청: “{esc(plan.fill.sentence)}”</p>' if plan.fill.sentence else ""
    body = [f"<h1>{esc(title)}</h1>",
            f'<p class="sub"><b>아직 아무것도 바뀌지 않았습니다.</b> 칸 값은 {esc(fmt_time(plan.read_at))} 에 ERP 에서 읽은 것입니다'
            f'{f" (장부 {change_id}번에 적어 두었습니다)" if change_id else ""}. 통화 {esc(currency)}.</p>',
            f'<div class="frame">{sentence}<dl class="kv"><dt>시즌</dt><dd>{esc(window.season_name)} · {_days(window.dates)}</dd>'
            f'<dt>창</dt><dd>{esc(window.title)}{" — " + esc(window.last_fill_note) if window.last_fill_note else ""}</dd></dl></div>']
    for save in plan.saves:
        body.append(_rule_banner(plan, save))
    body.append(stats([(tally["changes"], "바뀌는 칸"), (tally["new"], "새로 생기는 칸"), (tally["red"], "고를 빨간 줄"),
                       (tally["blocked"], "막힌 것")]
                      + [(tally[code], title) for code, title, _words in BUCKETS if code != "closed" and tally.get(code)]
                      + ([(tally["left_old"], "이번 채우기에 없는 예전 칸")] if tally["left_old"] else [])
                      + ([(tally["no_sale"], "판매일 없는 날의 칸")] if tally["no_sale"] else [])
                      + ([(tally["same"], "값은 같고 시즌 칸이 되는 칸")] if tally["same"] else [])
                      + ([(tally["combo_unknown"], "조합으로 빠질 수 있는 칸")] if tally["combo_unknown"] else [])
                      + ([(tally["misses"], "요금표와 다르게 채워지는 칸")] if tally["misses"] else [])))
    body.append(_misses_section(plan))
    for save in plan.saves:
        if save.dropped:
            body.append(f"<h2>{save.index}번째 저장 — 빠짐</h2><p class=\"sub\">고르신 대로 모든 날을 빼서 이 저장은 누르지 않습니다.</p>")
            continue
        by_key = {change.key: change for change in save.changes}
        closed = {key for key, change in by_key.items() if CLOSED in change.marks or change.after.state == "closed"}
        reserved = {(key.room, key.date) for key, change in by_key.items() if RESERVED in change.marks}

        def cell(key: CellKey, by_key=by_key, save=save) -> tuple[str, str]:
            change = by_key[key]
            code = verdict(save, key)
            moved = _move(change.before, change.after, currency)
            if code and RULES[code][1] == "blocked":
                return "blocked", moved + f'<span class="tag blocked">{esc(_rule_label(code))}</span>'
            if code and code not in save.choices:
                return "red", moved + f'<span class="tag red">{esc(_rule_label(code))}</span>'
            if change.before.state == "missing":
                return "new", moved + '<span class="tag new">새 칸</span>'
            return "", moved
        body += [f"<h2>{save.index}번째 저장 — 창에 칠 값</h2>", _inputs(plan, save),
                 f'<p class="sub">ERP 가 저장 뒤 말할 수(예상): 새로 {save.counts.created:,}칸 · 덮어쓴 {save.counts.updated:,}칸 '
                 f'(룸 {save.counts.rooms}개 × {save.counts.days}일){f" · 판매일이 없어 건너뛴 칸 {save.counts.skipped:,}개" if save.counts.skipped else ""}.</p>',
                 grid(list(by_key), cell, reserved, closed, by_date) if by_key else '<p class="sub">값이 바뀌는 칸이 없습니다.</p>',
                 _bucket_sections(plan, save)]
    live = plan.live
    if steps:
        body.append(f'<p class="sub">적용하면 시즌 [가격 입력] 창을 {times_word(len(steps))} 누릅니다(저장마다 한 번). 저장마다 그 범위를 '
                    "다시 읽어 미리보기 때와 같을 때만 누릅니다.</p>")
    body.append("<h2>알아 두실 것</h2>" + notes([NO_DELETE, GUESS, *undo_lines(plan),
                                                 "계산은 ERP 시즌 창과 같은 셈입니다(조정은 소수 둘째 자리 반올림, 공급 원가는 "
                                                 f"{'1 단위' if scale_of(currency) == 0 else '소수 둘째 자리'}로 반올림)."]))
    if not plan.ready:
        body.append('<div class="banner red"><b>아직 적용할 수 없습니다.</b> 위의 빨간 띠 · 막힌 것을 저장마다 어떻게 할지 대화창에서 '
                    "말씀해 주세요. 고르시면 미리보기를 다시 보여 드립니다.</div>")
    elif not live or not any(save.changes for save in live):
        body.append('<div class="banner blue">채워도 바뀌는 칸이 없어 적용할 것이 없습니다. 아무것도 바뀌지 않았습니다.</div>')
    else:
        body.append('<div class="banner blue">말씀이 없으면 아무것도 바뀌지 않습니다. 대화창에서 "적용"이라고 하시면 시즌 창에 그대로 '
                    "쳐서 저장합니다.</div>")
    return page(title, "\n".join(part for part in body if part), MAKER)


# ─── 적용 결과 ───


def season_check(record: ChangeRecord) -> dict:
    """장부만으로 — 넣은 칸 가운데 다시 읽은 값이 넣은 값이 아닌 칸(허용 조합을 몰라 ERP 가 뺐을 수 있는 칸이 칸 없음 · 전 값이면 받아들임),
    새 칸의 판매 상태가 짐작과 다른 칸, 저장마다 ERP 가 띠로 말한 수와 예상."""
    views = cell_views(record)
    combo = {key_of_item(row.item_key) for row in record.rows if "combo_unknown" in row.marks}
    opens_closed = {key_of_item(row.item_key) for row in record.rows if OPENS_CLOSED in row.marks}
    seen_state = {key_of_item(row.item_key): row.seen_state for row in record.rows if row.field == "sell"}
    wrong, left_out, state_only = [], [], []
    for key, view in views.items():
        if not view.written or view.rolled_back_by is not None or not record.verified_at:
            continue
        if not view.verified:
            if key in combo and (seen_state.get(key) in (None, "missing") or view.seen.get("sell") == view.before.sell):
                left_out.append(key)
            else:
                wrong.append(key)
        elif view.before.state == "missing" and seen_state.get(key) not in (None, "closed" if key in opens_closed else "open"):
            state_only.append(key)
    steps = []
    for step in record.steps:
        predicted = decode_counts(step.body.get("predicted") or {})
        told = banner_counts(step.note) if step.status == "saved" else None
        steps.append(dict(no=step.index, label=step.label, predicted=predicted, told=told,
                          agree=told is not None and counts_agree(predicted, told)))
    return dict(views=views, wrong=wrong, left_out=left_out, state_only=state_only, steps=steps)


def _counts_text(counts) -> str:
    return f"새로 {counts.created:,}칸 · 덮어쓴 {counts.updated:,}칸" + (f" · 건너뛴 {counts.skipped:,}칸" if counts.skipped else "")


def season_section(record: ChangeRecord, check: Mapping) -> str:
    """저장마다 ERP 가 말한 수와 예상 — 결과 페이지(멈춘 변경도)에 붙는다."""
    rows = []
    for item in check["steps"]:
        told = "아직 저장 안 함" if item["told"] is None else _counts_text(item["told"])
        mark = "맞음" if item["agree"] else ("—" if item["told"] is None else "다름")
        shade = ' class="red"' if mark == "다름" else ""
        rows.append(f'<tr><td class="text">{item["no"]}. {esc(item["label"])}</td><td>{esc(_counts_text(item["predicted"]))}</td>'
                    f'<td{shade}>{esc(told)}</td><td>{mark}</td></tr>')
    request = record.request or {}
    return ("<h2>ERP 가 말한 칸 수</h2><div class=\"scroll\"><table><tr><th>저장</th><th>미리보기의 예상</th><th>ERP 의 저장 띠</th><th></th></tr>"
            + "".join(rows) + "</table></div>"
            + f'<p class="sub">시즌 「{esc((request.get("season") or {}).get("name") or "")}」 · 시즌 창을 누른 저장만 ERP 가 칸 수를 말합니다.</p>')


def render_result(record: ChangeRecord, ledger_path: str | None = None, by_date: bool = False) -> str:
    check = season_check(record)
    if stop_view(record) is not None:   # 멈춘 변경은 가격 칸의 결과 페이지가 마지막 check 대로 말한다 — 시즌 줄을 붙인다
        cells = render_cells_result(record, ledger_path, by_date)
        return cells.replace("<h2>저장 단계</h2>", season_section(record, check) + "<h2>저장 단계</h2>", 1)
    currency = record.currency
    views = check["views"]
    title = f"{result_word(record, False)} · {record.hotel} · {record.offer} · 시즌 「{(record.request.get('season') or {}).get('name')}」 다시 채우기"
    written = [key for key, view in views.items() if view.written]
    wrong, left_out, state_only = check["wrong"], check["left_out"], check["state_only"]
    agree = all(item["agree"] for item in check["steps"])
    told = [item["told"] for item in check["steps"] if item["told"] is not None]
    if record.status == "applied" and record.verified_at:
        if wrong:
            banner = (f'<div class="banner red"><b>저장은 됐지만 다시 읽었더니 {len(wrong):,}칸이 미리보기와 다릅니다.</b> 아래 표의 빨간 칸을 '
                      f"확인해 주세요. 원하시면 '{record.id}번 되돌려'로 저장 전 값으로 돌립니다.</div>")
        elif not agree:
            banner = ('<div class="banner amber"><b>적용했고 다시 읽은 값은 모두 맞습니다.</b> 다만 ERP 가 말한 칸 수가 미리보기와 달라 도우미 '
                      "계산을 점검해야 합니다(아래 「ERP 가 말한 칸 수」).</div>")
        elif state_only:
            banner = (f'<div class="banner amber"><b>적용했고 다시 읽은 값은 모두 맞습니다.</b> 다만 새로 생긴 칸 {len(state_only):,}칸의 판매 '
                      "상태가 미리보기와 다릅니다(판매 상태만 다름 — 아래 표).</div>")
        else:
            said = " · ".join(_counts_text(item) for item in told)
            banner = (f'<div class="banner ok"><b>적용했고, 다시 읽어 확인했습니다.</b> ERP 도 \'{esc(said)}\'이라고 답했습니다.'
                      f"{f' 객실 조합으로 빠진 {len(left_out):,}칸은 ERP 가 넣지 않았습니다.' if left_out else ''}</div>")
    elif record.status == "applied":
        banner = '<div class="banner amber"><b>적용했습니다.</b> 아직 다시 읽어 확인하지 않았습니다.</div>'
    elif record.status == "applying":
        done = sum(step.status == "saved" for step in record.steps)
        banner = f'<div class="banner amber"><b>적용하는 중입니다.</b> 시즌 창을 {done}/{len(record.steps)}번 눌렀습니다.</div>'
    else:
        banner = '<div class="banner blue"><b>아직 적용하지 않았습니다.</b></div>'

    def cell(key: CellKey) -> tuple[str, str]:
        view = views[key]
        after = CellValue(*(view.after.get(name, getattr(view.before, name)) for name in FIELDS),
                          "open" if view.before.state == "missing" else view.before.state)
        moved = _move(view.before, after, currency)
        if key in wrong:
            seen = view.seen.get("sell")
            return "red", moved + f'<span class="tag red">다시 읽으니 {esc(_money(seen, currency, "칸 없음"))}</span>'
        if key in left_out:
            return "chosen", moved + '<span class="tag chosen">객실 조합으로 ERP 가 넣지 않음</span>'
        if key in state_only:
            return "red", moved + '<span class="tag red">판매 상태만 다름</span>'
        return ("new" if view.before.state == "missing" else ""), moved

    reserved = {(key.room, key.date) for key, view in views.items() if view.reserved}
    closed = {key for key, view in views.items() if view.before.state == "closed"}
    body = [f"<h1>{esc(title)}</h1>", banner,
            stats([(len(written), "넣은 칸"), (len(wrong), "다시 읽으니 다른 칸")]
                  + ([(len(state_only), "판매 상태만 다른 칸")] if state_only else [])
                  + ([(len(left_out), "객실 조합으로 빠진 칸")] if left_out else [])),
            season_section(record, check), steps_list(record.steps),
            "<h2>칸마다 넣은 값</h2>", grid(written, cell, reserved, closed, by_date) if written else '<p class="sub">넣은 칸이 없습니다.</p>',
            stopped_choices(record)]
    if record.status == "applied":
        body.append(notes(["손님 화면에는 5분 안에 새 가격이 보입니다. 이미 받은 예약의 금액은 그대로입니다.", UNDO_WHAT, UNDO_REFILL,
                           f"되돌리려면 '{record.id}번 되돌려'라고 하세요."]))
    if ledger_path:
        body.append(f'<p class="sub">장부: {esc(ledger_path)}</p>')
    return page(title, "\n".join(part for part in body if part), MAKER)


def rollback_notes(season: Mapping) -> str:
    """시즌 다시 채우기를 되돌릴 때 — 되돌려도 돌아오지 않는 것과, 채우기 전에 창에 있던 입력값(손으로 다시 칠 수 있게. 도우미는 다시 치지
    않는다 — 그것도 시즌 창 저장이라 칸을 또 쓴다)."""
    shown = [(name, value) for name, value in season.get("form") or () if name in INPUT_LABELS or name.startswith("child_extra_")]
    rows = "".join(f"<dt>{esc(INPUT_LABELS.get(name, name))}</dt><dd>{esc(value) if value else '비움'}</dd>" for name, value in shown)
    return (f'<div class="banner amber"><b>시즌 「{esc(season.get("season") or "")}」 다시 채우기를 되돌립니다.</b> {esc(UNDO_WHAT)} '
            f"{esc(UNDO_REFILL)}</div><h2>채우기 전에 시즌 창에 있던 입력값</h2><p class=\"sub\">도우미는 이 값을 다시 치지 않습니다(그것도 "
            f"시즌 창 저장이라 칸을 또 씁니다). 창의 기억을 되돌리고 싶으시면 직접 쳐 주세요.</p><dl class=\"kv\">{rows}</dl>")

