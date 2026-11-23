"""price_season_cli.py — 시즌 다시 채우기(시즌 원판 바꾸기)의 명령 쪽. `price_change.py` 가 요청 · 계산 파일 · 장부 단계의 종류를 보고
여기로 넘긴다. 셈은 `price_season`, 페이지는 `season_pages` 가 한다.

    window_command(args)          season — readSeason 답들 → season.json(창). 다른 시즌의 날을 아직 읽지 않았으면 ask
    request_range(data, window)   read-calls — 요청의 범위(저장들의 쌍 × 날)
    plan_command(args, …)         plan — 미리보기 계산 · 장부에 적기
    begin_steps(data)             begin — 계산 파일의 저장 단계(StepPlan)와 장부에 적을 요청
    next_call(ledger, record, …)  calls — 다음 저장 하나의 부를 값. 그 저장의 범위를 120초 안에 다시 읽은 값이 미리보기 때(앞 저장이 넣은
                                  값을 얹은 것)와 같을 때만. 다르면 그 저장을 「그 사이 바뀜」으로 적고 변경을 멈춘다
    verify_season(…)              verify — 장부의 확인 + 허용 조합을 몰라 ERP 가 뺐을 수 있는 칸 · 새 칸의 판매 상태 · ERP 가 말한 칸 수
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from change_core.answers import attach_bodies
from change_core.chrome import MOVED_ERRORS
from change_core.items import key_fields
from change_core.ledger import Ledger, clock
from change_core.money import money_text
from change_core.rollback import holds
from price_model import (
    FIELDS, MISSING, CellKey, CellValue, Snapshot, cell_state, encode_key, encode_snapshot, encode_value, key_of_item, same_hotel,
)
from price_season import (
    KEEPS, KIND, NO_SUPPLY, RULES, AskSeasons, SeasonError, banner_counts, counts as plan_counts, counts_agree, covers, decode_choices, decode_counts, decode_fill,
    decode_plan, decode_window, encode_plan, encode_window, expected_cells, fresh_problem, followup_targets, has_writes, missing_seasons,
    plan_season, preview_rows, range_differences, recorded_request, rule_choices, season_range, season_steps, step_call, step_range,
    window_of, window_remembers,
)
from price_sheet import decode_check
from season_sheet import targets_of

SEASON_PREFIXES = ("season-", "take-")
OPENS_CLOSED = "opens_closed"   # 새 칸을 판매 마감으로 만든다고 짐작한 칸의 표시(장부의 marks) — 확인이 판매 상태를 견준다


# ─── season ───


def window_command(results: list, earlier: list) -> dict:
    """readSeason 답들(조각 포함) → 창. 답 가운데 datesOnly 가 아닌 가장 늦은 것이 창, datesOnly 답들은 다른 시즌의 날이다."""
    answers = [result for result in attach_bodies(results, earlier, page="stayPriceSeason") if result.get("op") == "readSeason"]
    failed = [result for result in answers if not result.get("ok")]
    if failed and not any(result.get("ok") for result in answers):
        raise SeasonError(f"stayPriceSeason.readSeason 이 실패했습니다: {failed[-1].get('error')}")
    whole = [result for result in answers if result.get("ok") and not (result.get("asked") or {}).get("datesOnly")]
    if not whole:
        raise SeasonError("stayPriceSeason.readSeason 의 답(datesOnly 없이 부른 것)이 없습니다 — 답을 <작업>/시즌/season-1.json 에 저장하고 "
                          "다시 묶습니다")
    main = max(whole, key=lambda result: str(result.get("doneAt") or ""))
    dated = {str(result["season"]["id"]): tuple(result.get("dates") or ()) for result in answers
             if result.get("ok") and (result.get("asked") or {}).get("datesOnly")}
    ask = missing_seasons(main, dated)
    if ask:
        raise AskSeasons(f"같은 오퍼의 다른 시즌 {len(ask)}개의 날을 아직 읽지 않았습니다 — ask 의 값마다 stayPriceSeason.readSeason(<값 그대로>) "
                         "의 답을 season-<n>.json 으로 저장하고 season 을 다시 합니다(다른 시즌 날에도 드는 칸을 미리보기가 말하려고)", ask)
    return encode_window(window_of(main, dated))


# ─── read-calls · plan ───


def load_window(path: str | None, load) -> object:
    if not path:
        raise SeasonError("시즌 다시 채우기 요청에는 --season(season 명령이 낸 season.json)을 함께 줍니다")
    return decode_window(load(path))


def request_range(data: Mapping, window) -> tuple:
    fill = decode_fill(data)
    pairs, days = season_range(window, fill)
    return fill, pairs, days


def sheet_targets(fill, window) -> dict:
    """요금표에서 끌어낸 요청이면 그 요금표의 칸(시즌 날 · 창의 쌍, 인원 조합은 ERP 키) → (필드 값 — 통화 단위로 반올림, 줄 번호).
    아니면 빈 것."""
    return targets_of(decode_check(fill.sheet), window) if fill.sheet else {}


def helper_edits(ledger: Ledger, snapshot: Snapshot) -> dict[CellKey, int]:
    """읽은 칸 가운데 이 장부의 날짜별 변경(시즌 다시 채우기가 아닌 것, 같은 호텔 · 오퍼)이 넣은 값을 그대로 갖고 있는 칸 → 그 값을 넣은
    장부 번호(가장 나중 것). 되돌린 값은 넣은 값으로 치지 않는다(그 되돌리기가 넣은 값이 된다)."""
    found: dict[CellKey, int] = {}
    for entry in sorted(ledger.list_changes(), key=lambda item: item["id"]):
        if (entry["kind"] == "snapshot" or not entry["written"] or entry["offer"] != snapshot.offer
                or (entry.get("request") or {}).get("kind") == KIND
                or not same_hotel(entry["hotel"], entry["hotel_id"], snapshot.hotel, snapshot.hotel_id)):
            continue
        for item in ledger.recorded_change(entry["id"]).items:
            key = key_of_item(item.key)
            value = snapshot.cells.get(key)
            if value is not None and value.state != "missing" and holds(cell_state(key, value), item.written):
                found[key] = entry["id"]
    return found


def season_rows(plan):
    """장부 줄 — 새 칸을 마감으로 만든다고 짐작한 칸에는 표시를 하나 더 단다(확인이 판매 상태를 견준다)."""
    closed = {change.key for change in plan.changes if change.before.state == "missing" and change.after.state == "closed"}
    rows = []
    for row in preview_rows(plan):
        if key_of_item(row.item_key) in closed and OPENS_CLOSED not in row.marks:
            row = type(row)(**{**row.__dict__, "marks": row.marks + (OPENS_CLOSED,)})
        rows.append(row)
    return rows


def plan_command(snapshot: Snapshot, data: Mapping, window, resolutions, ledger: Ledger | None, replaces: int | None,
                 record: bool) -> dict:
    fill = decode_fill(data)
    choices = decode_choices(resolutions)
    plan = plan_season(snapshot, window, fill, choices, helper_edits(ledger, snapshot) if ledger else {},
                       sheet_targets(fill, window))
    steps = season_steps(plan)
    change_id = None
    if record:
        change_id = ledger.record_preview(
            hotel=snapshot.hotel, hotel_id=snapshot.hotel_id, offer=window.offer, currency=snapshot.currency, sentence=fill.sentence,
            read_at=snapshot.read_at, rows=season_rows(plan), request=recorded_request(plan), reading=encode_snapshot(snapshot),
            replaces=replaces, empty=steps is not None and not has_writes(plan),
            unused=[dict(rule=choice.rule, choice=choice.choice, said=choice.said, why="none", words="이번 계산에는 그 빨간 줄에 걸린 칸이 "
                         "없습니다", cells=[]) for choice in plan.unused])
    return dict(kind="season_plan", change_id=change_id, replaces=replaces, plan=encode_plan(plan), counts=plan_counts(plan),
                steps=None if steps is None else [dict(kind=step.kind, label=step.label, body=step.body) for step in steps],
                waiting=[dict(save=save.index, rules=save.waiting()) for save in plan.live if save.waiting()],
                followup=followup_request(plan))


def followup_request(plan) -> dict | None:
    """요금표와 다르게 채워지는 칸을 채운 뒤 날짜별로 맞출 목표 값 표(kind targets) — 그런 칸이 없으면 None. `plan` · `read-calls` 에
    이 계산 파일을 요청으로 주면 이 표로 한다(그때 다시 읽은 값과 견주니 채운 뒤의 값에서 다른 칸만 바뀐다)."""
    targets = followup_targets(plan)
    if not targets:
        return None
    return dict(kind="targets", hotel=dict(id=plan.window.hotel_id, name=plan.window.hotel), offer=plan.window.offer, from_sheet=True,
                sentence=f"{plan.fill.sentence or '새 요금표'} — 시즌 창으로 맞추지 못한 칸 날짜별로 맞추기", targets=targets)


def short_plan(result: Mapping) -> dict:
    """미리보기를 말하고 고를 것을 묻는 데 필요한 것 — 바구니마다의 수, 저장 횟수(고를 것이 남았으면 null), 저장마다 고를 규칙(규칙마다
    걸린 날 · 고를 수 있는 것), 거절한 저장의 ERP 문장, 요금표와 다른 칸 수."""
    plan = decode_plan(result["plan"])
    saves = []
    for save in plan.saves:
        rules = [dict(rule=code, label=RULES[code][0] if code in RULES else KEEPS[code], cells=len(keys), dates=len(save.hit_dates(code)),
                      choices=list(rule_choices(code)), chosen=None if code not in save.choices else save.choices[code].choice)
                 for code, keys in save.hits.items()]
        saves.append(dict(save=save.index, dropped=save.dropped, excluded=list(save.excluded), refused=save.refused,
                          waiting=save.waiting(), rules=rules, predicted=dict(created=save.counts.created, updated=save.counts.updated,
                                                                                skipped=save.counts.skipped)))
    short = dict(kind="season_plan", change_id=result["change_id"], replaces=result["replaces"], counts=result["counts"],
                 saves=None if result["steps"] is None else len(result["steps"]), per_save=saves,
                 misses=len(plan.misses), followup=len((result.get("followup") or {}).get("targets") or ()),
                 unused=[dict(save=choice.save, rule=choice.rule, said=choice.said) for choice in plan.unused])
    remembers = window_remembers(recorded_request(plan))
    if remembers:   # 날짜 일부만 채우는 저장 — "적용"을 청하기 전에 그대로 말한다(season-fill.md 3)
        short["remembers"] = remembers
    return short


def begin_steps(data: Mapping) -> tuple[list, dict]:
    plan = decode_plan(data["plan"])
    steps = season_steps(plan)
    if steps is None:
        raise SeasonError("고를 것이 남은 저장이 있습니다 — 빨간 줄 · 막힘을 먼저 고르고 미리보기를 다시 만듭니다")
    return steps, recorded_request(plan)


# ─── calls ───


def saved_values(record) -> dict[CellKey, CellValue]:
    """장부가 저장됐다고 적은 단계들이 넣은 칸의 값(예상) — 전 값 위에 넣은 필드를 얹고, 없던 칸은 판매 가능(마감 짐작이면 마감)."""
    cells: dict[CellKey, dict] = {}
    for row in record.rows:
        if not row.written or row.rolled_back_by:
            continue
        key = key_of_item(row.item_key)
        entry = cells.setdefault(key, dict(state=row.state, marks=row.marks, values={}))
        entry["values"][row.field] = (row.before, row.after if row.action else row.before)
    out = {}
    for key, entry in cells.items():
        values = {name: entry["values"].get(name, (None, None))[1] for name in FIELDS}
        if entry["state"] == "missing":
            state = "closed" if OPENS_CLOSED in entry["marks"] else "open"
        else:
            state = entry["state"]
        if values["sell"] is not None:
            out[key] = CellValue(values["sell"], values["list"], values["supply"], state)
    return out


def next_call(ledger: Ledger, record, now: Snapshot | None, then: Snapshot) -> dict:
    """다음 저장 하나의 부를 값 — A2. 그 저장의 범위(쌍 × 날)를 덮고, 앞 단계가 끝난 뒤(첫 단계는 그 번호를 계산한 뒤) FRESH_SECONDS
    안에 읽은 값이어야 한다(아니면 아무것도 내지 않고 다시 읽으라고 거절). 그 범위의 칸이 있어야 할 값과 하나라도 다르면 아무것도 내지
    않고, 그 저장을 「그 사이 바뀜」(페이지가 누르기 전에 거절한 것과 같은 메모)으로 적어 변경을 멈추고 다른 칸을 댄다."""
    left = [step for step in record.steps if step.status != "saved"]
    if not left:
        return dict(change_id=record.id, status=record.status, calls=[])
    step = left[0]
    warned = next((other for other in record.steps if other.status == "saved" and NO_SUPPLY in (other.note or "")), None)
    if warned is not None:
        raise SeasonError(f"{warned.index}번째 저장 뒤 ERP 가 공급 통화가 없어 가격 원장을 기록하지 못했다고 했습니다 — 칸은 써졌지만 팔리지 "
                          "않습니다. 다음 저장을 내지 않습니다. 담당자에게 그 띠의 글을 그대로 전하고, 기본정보에서 통화를 지정한 뒤 다시 합니다")
    window = decode_window(record.request["window"])
    pairs, days = step_range(window, step.body)
    if now is None:
        raise SeasonError(f"시즌 창 저장은 그 저장의 범위를 {120}초 안에 다시 읽은 값으로만 냅니다 — read-calls --record {record.id} --step "
                          f"{step.index} 로 읽고 calls 에 --snapshot 을 줍니다")
    if not same_hotel(now.hotel, now.hotel_id, record.hotel, record.hotel_id) or now.offer != record.offer:
        raise SeasonError(f"방금 읽은 값은 호텔 {now.hotel_id} · {now.offer} 것이고, {record.id}번은 호텔 {record.hotel_id} · {record.offer} 입니다")
    gaps = covers(now, pairs, days)
    if gaps:
        raise SeasonError(f"방금 읽은 값이 {step.index}번째 저장의 범위를 덮지 않습니다({', '.join(gaps[:5])}) — read-calls --record {record.id} "
                          f"--step {step.index} 로 읽습니다")
    finished = [other.finished_at for other in record.steps if other.finished_at]
    problem = fresh_problem(now.read_at, max(finished) if finished else record.created_at, clock()())
    if problem:
        raise SeasonError(problem)
    expected = expected_cells(then, saved_values(record), pairs, days)
    differences = range_differences(expected, now, pairs, days)
    if differences:
        status = ledger.record_step(record.id, step.index, False,
                                    f"{MOVED_ERRORS[0]}({len(differences)}칸) — 시즌 창 저장 직전에 그 범위를 다시 읽으니 미리보기 때와 다릅니다")
        return dict(change_id=record.id, status=status, calls=[], stopped=True,
                    differences=[dict(key=encode_key(key), then=encode_value(was), now=encode_value(seen))
                                 for key, was, seen in differences])
    age = int((clock()() - datetime.fromisoformat(now.read_at.replace("Z", "+00:00"))).total_seconds())
    return dict(change_id=record.id, status=record.status, calls=[step_call(step.index, step.body)],
                fresh=dict(read_at=now.read_at, seconds=age))


def pair_unit(item_key: str) -> str:
    """시즌 창 저장 하나가 다시 쓰는 단위 — 객실 · 요금제(그 저장은 그 쌍의 칸을 같은 값으로도 덮는다). check 가 남은 저장을 볼 때 장부의
    줄(값이 바뀌는 칸)만이 아니라 그 쌍의 칸을 모두 미리보기 때와 견주게 한다."""
    fields = key_fields(item_key)
    return f"{fields['room']}\u0000{fields['rate_plan']}"


def step_calls(record) -> list[dict]:
    """장부의 시즌 단계 전부의 부를 값(record-result 가 답을 그 단계에 맞춘다)."""
    return [step_call(step.index, step.body) for step in record.steps]


def is_season(record) -> bool:
    return any(step.kind == KIND for step in record.steps) or (record.request or {}).get("kind") == KIND


# ─── verify ───


def verify_season(ledger: Ledger, change_id: int, now: Snapshot, mismatches) -> dict:
    """장부의 확인(그 변경이 넣은 칸마다 읽은 값이 넣은 값인지) 위에 — 허용 인원 조합을 몰라 ERP 가 뺐을 수 있는 칸은 칸이 없거나 전
    값이면 받아들이고, 새 칸의 판매 상태가 짐작과 다르면 「판매 상태만 다름」, ERP 가 띠로 말한 칸 수를 예상과 견준다. 「확인했습니다」는
    셋 다 맞을 때만이다."""
    record = ledger.change(change_id)
    combo = {row.item_key for row in record.rows if "combo_unknown" in row.marks}
    befores = {(row.item_key, row.field): row.before for row in record.rows}
    accepted, remaining = [], []
    for item in mismatches:
        before = befores.get((item.item_key, item.field))
        if item.item_key in combo and (item.seen_state in (None, "missing") or item.seen == before):
            accepted.append(item)
        else:
            remaining.append(item)
    state_only = []
    for row in record.rows:
        if not row.written or row.field != "sell" or row.state != "missing" or row.rolled_back_by:
            continue
        key = key_of_item(row.item_key)
        value = now.cells.get(key, MISSING)
        want = "closed" if OPENS_CLOSED in row.marks else "open"
        if value.state not in ("missing", want) and value.sell == row.after:
            state_only.append(dict(key=encode_key(key), want=want, seen=value.state))
    counted = []
    for step in record.steps:
        if step.status != "saved":
            continue
        told = banner_counts(step.note)
        predicted = decode_counts(step.body.get("predicted") or {})
        counted.append(dict(no=step.index, predicted=dict(created=predicted.created, updated=predicted.updated, skipped=predicted.skipped),
                            told=None if told is None else dict(created=told.created, updated=told.updated, skipped=told.skipped),
                            agree=told is not None and counts_agree(predicted, told)))
    same = not remaining and not state_only and all(item["agree"] for item in counted)
    return dict(change_id=change_id, same=same,
                mismatches=[dict(key=key_fields(item.item_key), label=item.label, field=item.field, after=money_text(item.after),
                                 seen=money_text(item.seen), seen_state=item.seen_state) for item in remaining],
                left_out=[dict(key=key_fields(item.item_key), label=item.label) for item in accepted if item.field == "sell"],
                state_only=state_only, counts=counted)


def rollback_inputs(ledger: Ledger, change_id: int) -> dict | None:
    """되돌리는 변경이 시즌 다시 채우기면 그 시즌 이름과 창의 이전 입력값(미리보기 때 읽은 창 — 사람이 손으로 다시 칠 수 있게)."""
    request = ledger.change(change_id).request or {}
    if request.get("kind") != KIND:
        return None
    window = request.get("window") or {}
    return dict(season=(request.get("season") or {}).get("name") or "", form=[list(pair) for pair in window.get("form") or ()],
                remembers=window_remembers(request))


def short_window(result: Mapping) -> dict:
    """창을 말하는 데 필요한 것 — 시즌 날, 마지막 입력값이 채워져 열렸는지, 객실 · 요금제(캘린더 이름), 아동 칸, 다른 시즌, 허용 조합을
    모르는 객실. 칸 목록(form)은 싣지 않는다."""
    window = decode_window(result)
    return dict(hotel=result["hotel"], offer=window.offer, season=dict(id=window.season_id, name=window.season_name),
                dates=dict(first=window.dates[0] if window.dates else None, last=window.dates[-1] if window.dates else None,
                           count=len(window.dates)),
                last_fill_note=window.last_fill_note or None,
                pairs=[dict(room=plan.room, rate_plan=plan.rate_plan, base=plan.base) for plan in window.plans],
                child=[dict(code=item.code, kind=item.kind, percent=None if item.percent is None else str(item.percent),
                            default=item.blank or None) for item in window.child],
                other_seasons=[dict(name=item.name, days=len(item.dates)) for item in window.seasons],
                combos_unknown=[room for room, text in window.combos.items() if text is None], banner=window.banner)


def short_request(result: Mapping) -> dict:
    """요금표에서 끌어낸 요청 — 저장마다 쌍 · 창에 칠 입력 · 날 수. 요금표 파일은 싣지 않는다."""
    fill = decode_fill(result)
    return dict(season=dict(id=fill.season_id, name=fill.season_name), saves=[
        dict(pairs=[dict(room=room, rate_plan=plan) for room, plan in save.pairs],
             inputs={name: save.text(name) for name in ("price", "original_price", "net_price", "plan_adjust", "occupancy_keys",
                                                        "occupancy_adjust", "los_prices") if save.text(name)},
             child_extra=dict(save.child_extra), dates=None if save.dates is None else len(save.dates)) for save in fill.saves])
