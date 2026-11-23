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

from change_core.answers import BrowserError, ask_sum, attach_bodies
from change_core.chrome import MOVED_ERRORS
from change_core.items import encode_state, key_fields, stale_items
from change_core.ledger import Ledger, clock
from change_core.money import money_text
from change_core.rollback import holds
from price_model import (
    FIELDS, MISSING, CellKey, CellValue, Snapshot, as_read, cell_state, decode_hotel, encode_key, encode_snapshot, encode_value,
    key_of_item, same_hotel,
)
from price_season import (
    KIND, NO_SUPPLY, RULES, AskSeasons, SeasonError, banner_counts, counts as plan_counts, counts_agree, covers, day_items, decode_choices,
    decode_counts, decode_fill,
    decode_plan, decode_window, encode_plan, encode_window, expected_cells, fresh_problem, followup_targets, has_writes, missing_seasons,
    FRESH_SECONDS, fresh_until, plan_season, preview_rows, range_differences, recorded_request, rule_choices, rule_label, rule_said, season_range,
    season_steps, step_call, step_range,
    window_of, window_remembers,
)
from price_sheet import decode_check
from season_sheet import targets_of

SEASON_PREFIXES = ("season-", "take-")
OPENS_CLOSED = "opens_closed"   # 새 칸을 ERP 가 마감으로 만드는 칸(지속 마감인 날)의 표시(장부의 marks) — 확인이 판매 상태를 견준다
READS_MIXED = "reads_mixed"     # 새 칸이 생긴 뒤 그날 그 요금제의 칸 상태가 섞여 화면이 「인원·박수별 상태 다름」으로 보일 칸의 표시


def expected_state(marks, before_state: str) -> str:
    """장부의 줄(그 칸의 표시 · 전 상태)로 — 저장 뒤 다시 읽으면 그 칸이 보일 판매 상태. 있던 칸은 그대로(ERP 의 덮기는 상태를 쓰지
    않는다), 새 칸은 지속 마감인 날만 마감 · 그 밖은 판매 가능, 그날 상태가 섞이면 mixed(price_model.as_read)."""
    if READS_MIXED in marks:
        return "mixed"
    if before_state != "missing":
        return before_state
    return "closed" if OPENS_CLOSED in marks else "open"


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


def season_rows(plan, snapshot: Snapshot):
    """장부 줄 — 새 칸 가운데 ERP 가 마감으로 만드는 칸(지속 마감인 날)과, 저장 뒤 그날 칸 상태가 섞여 화면이 「인원·박수별 상태
    다름」으로 보일 칸(새 칸이 생겨 섞이는 날의 바뀌는 칸)에 표시를 단다(확인이 판매 상태를 그 표시대로 견준다 — expected_state)."""
    after = as_read({**snapshot.cells, **{change.key: change.after for change in plan.changes}})
    marked: dict[CellKey, tuple[str, ...]] = {}
    for change in plan.changes:
        opens_closed = change.before.state == "missing" and change.after.state == "closed"
        mixed = after[change.key].state == "mixed" and change.before.state != "mixed"
        marked[change.key] = ((OPENS_CLOSED,) if opens_closed else ()) + ((READS_MIXED,) if mixed else ())
    rows = []
    for row in preview_rows(plan):
        extra = tuple(mark for mark in marked.get(key_of_item(row.item_key), ()) if mark not in row.marks)
        rows.append(type(row)(**{**row.__dict__, "marks": row.marks + extra}) if extra else row)
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
            read_at=snapshot.read_at, rows=season_rows(plan, snapshot), request=recorded_request(plan), reading=encode_snapshot(snapshot),
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
        rules = []
        for code, keys in save.hits.items():
            rule = dict(rule=code, label=rule_label(save, code), cells=len(keys), dates=len(save.hit_dates(code)),
                        choices=list(rule_choices(code)), chosen=None if code not in save.choices else save.choices[code].choice)
            if code in RULES and code not in save.choices:   # 고를 것이 남은 빨간 줄 · 막힘 — 도우미가 그대로 하는 말
                rule["said"] = rule_said(save, code, plan.currency)
            rules.append(rule)
        saves.append(dict(save=save.index, dropped=save.dropped, pressed=not save.dropped and bool(save.changes), excluded=list(save.excluded),
                          refused=save.refused, waiting=save.waiting(), rules=rules,
                          predicted=dict(created=save.counts.created, updated=save.counts.updated, skipped=save.counts.skipped)))
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


def written_values(record, steps) -> dict[CellKey, CellValue]:
    """그 단계들이 넣은(넣을) 칸의 값(예상) — 칸마다 넣는 필드는 넣는 값, 나머지 필드는 전 값, 판매 상태는 다시 읽으면 보일 것
    (expected_state)."""
    keys = {row.item_key for row in record.rows if row.action is not None and row.step in steps and not row.rolled_back_by}
    cells: dict[str, dict] = {}
    for row in record.rows:
        if row.item_key in keys:
            entry = cells.setdefault(row.item_key, dict(state=row.state, marks=row.marks, values={}))
            entry["values"][row.field] = row.after if row.action is not None else row.before
    out = {}
    for item_key, entry in cells.items():
        values = [entry["values"].get(name) for name in FIELDS]
        if values[0] is not None:
            out[key_of_item(item_key)] = CellValue(*values, expected_state(entry["marks"], entry["state"]))
    return out


def saved_values(record) -> dict[CellKey, CellValue]:
    """장부가 저장됐다고 적은 단계들이 넣은 칸의 값(예상)."""
    return written_values(record, {step.index for step in record.steps if step.status == "saved"})


def next_call(ledger: Ledger, record, now: Snapshot | None, then: Snapshot) -> dict:
    """다음 저장 하나의 부를 값 — A2. 그 저장의 범위(쌍 × 날)를 덮고, 앞 단계가 끝난 뒤(첫 단계는 그 번호를 계산한 뒤) FRESH_SECONDS
    안에 읽은 값이어야 한다(아니면 아무것도 내지 않고 다시 읽으라고 거절). 그 범위가 있어야 할 값(미리보기 때 + 앞 저장들이 넣은 값)
    그대로면 부를 값을 낸다 — 그 읽은 값의 기한(`freshUntil`)을 얹고 장부에 냈다고 적는다(같은 읽은 값으로는 두 번 내지 않는다).
    그 범위가 있어야 할 값에 이 저장이 넣는 값까지 얹은 것과 같으면 이 저장은 이미 된 것으로 보인다(누른 답을 잃었다) — 아무것도
    적지 않고 그렇게 답한다(record-result 나 check 로 가린다). 그 밖에 하나라도 다르면(판매일 없는 날 · 예약 있는 날도) 아무것도
    내지 않고, 그 저장을 「그 사이 바뀜」(페이지가 누르기 전에 거절한 것과 같은 메모)으로 적어 변경을 멈추고 다른 칸을 댄다."""
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
        raise SeasonError(f"시즌 창 저장은 그 저장의 범위를 {FRESH_SECONDS}초 안에 다시 읽은 값으로만 냅니다 — read-calls --record {record.id} "
                          f"--step {step.index} 로 읽고 calls 에 --snapshot 을 줍니다")
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
    earlier = saved_values(record)
    expected = expected_cells(then, earlier, pairs, days)
    differences = range_differences(expected, now, pairs, days)
    moved_days = stale_items(day_items(then, pairs, days), day_items(now, pairs, days))   # 판매일이 열림 · 예약이 듦(검토 2 의 7)
    if not differences and not moved_days:
        until = fresh_until(now.read_at)
        if not ledger.issue(record.id, step.index, now.read_at, until):
            raise SeasonError(f"이 읽은 값({_clock_text(now.read_at)})으로 {step.index}번째 저장의 부를 값을 이미 냈습니다 — 같은 읽은 값으로 두 번 "
                              "내지 않습니다. 그 부를 값으로 누른 답이 있으면 record-result 에 줍니다. 누르지 않았거나 눌렀는지 모르면 그 저장의 "
                              "범위를 새 읽기 폴더에 다시 읽고 calls 를 부릅니다(눌러서 저장됐으면 calls 가 「이미 된 것으로 보입니다」라고 답합니다)")
        age = int((clock()() - datetime.fromisoformat(now.read_at.replace("Z", "+00:00"))).total_seconds())
        return dict(change_id=record.id, status=record.status, calls=[step_call(step.index, step.body, until)],
                    fresh=dict(read_at=now.read_at, seconds=age, until=_clock_text(until)))
    landed = as_read(expected_cells(then, {**earlier, **written_values(record, {step.index})}, pairs, days))
    if differences and not range_differences(landed, now, pairs, days):
        return dict(change_id=record.id, status=record.status, calls=[], saved_already=step.index,
                    said=(f"{step.index}번째 저장은 이미 된 것으로 보입니다 — 그 범위의 칸이 모두 이 저장이 넣는 값입니다(누른 뒤 답을 적지 "
                          "못했을 수 있습니다). 다시 누르지 않았고 장부에도 아무것도 적지 않았습니다. 그 누름의 답 파일이 있으면 "
                          "record-result 에 주고, 없으면 같은 범위를 다시 읽어 check 로 가립니다(칸이 모두 넣은 값이면 저장됨으로 적습니다)"))
    count = len(differences) + len(moved_days)
    status = ledger.record_step(record.id, step.index, False,
                                f"{MOVED_ERRORS[0]}({count}칸) — 시즌 창 저장 직전에 그 범위를 다시 읽으니 미리보기 때와 다릅니다")
    return dict(change_id=record.id, status=status, calls=[], stopped=True,
                differences=[dict(key=encode_key(key), then=encode_value(was), now=encode_value(seen))
                             for key, was, seen in differences]
                + [dict(key=key_fields(item.key), then=encode_state(item.then), now=encode_state(item.now)) for item in moved_days])


def _clock_text(moment) -> str:
    """읽은 시각(ISO) · 기한(ms) → 이 컴퓨터 시각대의 「HH:MM:SS」."""
    if isinstance(moment, int):
        return datetime.fromtimestamp(moment / 1000).astimezone().strftime("%H:%M:%S")
    return datetime.fromisoformat(str(moment).replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")


def pair_unit(item_key: str) -> str:
    """시즌 창 저장 하나가 다시 쓰는 단위 — 객실 · 요금제(그 저장은 그 쌍의 칸을 같은 값으로도 덮는다). check 가 남은 저장을 볼 때 장부의
    줄(값이 바뀌는 칸)만이 아니라 그 쌍의 칸을 모두 미리보기 때와 견주게 한다."""
    fields = key_fields(item_key)
    return f"{fields['room']}\u0000{fields['rate_plan']}"


def answer_call(ledger: Ledger, record, step, result: Mapping) -> dict:
    """저장 답 하나가 그 단계의 어느 부를 값의 것인지 — calls 가 그 단계에 낸 부를 값(기한을 얹은 것) 가운데 답의 지문(`ask`)이 같은
    것. 누른 답은 언제 적어도 받는다(기한은 누르기를 막을 뿐, 된 저장을 잃게 하지 않는다). calls 가 낸 부를 값의 답이 아니면 거절한다."""
    calls = [step_call(step.index, step.body, until) for _index, _read_at, until in ledger.issued(record.id, step.index)]
    found = next((call for call in calls if ask_sum(call["payload"]) == result.get("ask")), None)
    if found is None:
        raise BrowserError(f"{step.index}번째 저장의 답이 calls 가 낸 부를 값의 답이 아닙니다 — 시즌 창 저장은 calls 가 그 범위를 다시 읽은 "
                           "값으로 낸 부를 값(기한 freshUntil 이 든 것)으로만 누릅니다. 계산 파일 · 장부의 페이로드로는 누르지 않습니다")
    return found


def is_season(record) -> bool:
    return any(step.kind == KIND for step in record.steps) or (record.request or {}).get("kind") == KIND


# ─── verify ───


def may_skip(marks) -> bool:
    """ERP 가 넣지 않을 수 있는 칸 — 허용 인원 조합을 몰라 객실 조합으로 빠질 수 있다고 표시한 칸. check 와 확인이 이 한 뜻으로
    「이 저장이 됐다」를 가린다(change_core.ledger.left_out)."""
    return "combo_unknown" in marks


def verify_season(ledger: Ledger, change_id: int, now: Snapshot, mismatches) -> dict:
    """장부의 확인(그 변경이 넣은 칸마다 읽은 값이 넣은 값인지 — `may_skip` 으로 부른 것) 위에 — ERP 가 넣지 않을 수 있는 칸이 전 값
    그대로면(left_out) 받아들이고, 새 칸의 판매 상태가 짐작과 다르면 「판매 상태만 다름」, ERP 가 띠로 말한 칸 수를 예상과 견준다.
    「확인했습니다」는 셋 다 맞을 때만이다."""
    record = ledger.change(change_id)
    accepted = [item for item in mismatches if item.left_out]
    remaining = [item for item in mismatches if not item.left_out]
    state_only = []
    for row in record.rows:
        if not row.written or row.field != "sell" or row.state != "missing" or row.rolled_back_by:
            continue
        key = key_of_item(row.item_key)
        value = now.cells.get(key, MISSING)
        want = expected_state(row.marks, row.state)
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


BANNER_HEAD = 30   # 띠 글이 장부의 저장 메모와 이만큼 앞이 같아야 그 저장의 띠로 친다(둘 다 「…」로 잘릴 수 있다)


def banner_owner(ledger: Ledger, window: Mapping) -> dict | None:
    """창의 답에 실린 시즌 목록의 띠(마지막 저장의 띠 — 다른 시즌의 저장일 수 있다)가 이 장부의 어느 시즌 채우기 저장의 것인지 —
    `{change_id, step, season_id, season}`, 모르면 None. 같은 호텔 · 오퍼의 시즌 채우기 가운데 저장된 단계의 메모(ERP 의 띠 글)와 앞이
    같은 것, 새것부터."""
    banner = str(window.get("banner") or "").split("…")[0].strip()
    if len(banner) < BANNER_HEAD:
        return None
    _name, hotel_id = decode_hotel(window["hotel"])
    for entry in ledger.list_changes():
        request = entry.get("request") or {}
        if request.get("kind") != KIND or str(entry["hotel_id"]) != str(hotel_id) or entry["offer"] != window.get("offer"):
            continue
        for step in ledger.change(entry["id"]).steps:
            note = str(step.note or "").split("…")[0].strip()
            size = min(len(note), len(banner))
            if step.status == "saved" and size >= BANNER_HEAD and note[:size] == banner[:size]:
                season = request.get("season") or {}
                return dict(change_id=entry["id"], step=step.index, season_id=str(season.get("id")), season=season.get("name"))
    return None


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
                combos_unknown=[room for room, text in window.combos.items() if text is None],
                banner=_own_banner(window, result.get("banner_owner")))


def _own_banner(window, owner: Mapping | None) -> str | None:
    """짧은 답의 `banner` — 시즌 목록의 띠가 이 시즌의 저장의 것일 때만, 어느 저장인지 붙여서(시운전 12 — Normal 을 읽었는데 Peak
    저장의 띠가 실렸다). 다른 시즌의 것이거나 어느 저장의 것인지 모르면 싣지 않는다(None)."""
    if not window.banner or not owner or owner.get("season_id") != window.season_id:
        return None
    return f"장부 {owner['change_id']}번 {owner['step']}번째 저장의 띠: {window.banner}"


def short_request(result: Mapping) -> dict:
    """요금표에서 끌어낸 요청 — 저장마다 쌍 · 창에 칠 입력 · 날 수. 요금표 파일은 싣지 않는다."""
    fill = decode_fill(result)
    return dict(season=dict(id=fill.season_id, name=fill.season_name), saves=[
        dict(pairs=[dict(room=room, rate_plan=plan) for room, plan in save.pairs],
             inputs={name: save.text(name) for name in ("price", "original_price", "net_price", "plan_adjust", "occupancy_keys",
                                                        "occupancy_adjust", "los_prices") if save.text(name)},
             child_extra=dict(save.child_extra), dates=None if save.dates is None else len(save.dates)) for save in fill.saves])
