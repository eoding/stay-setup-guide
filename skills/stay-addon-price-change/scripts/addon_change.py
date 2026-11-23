#!/usr/bin/env python3
"""addon_change.py — 부가옵션 가격 도우미의 명령. JSON 파일을 받고 JSON 을 돌려준다(브라우저 쪽이 이 명령을 부른다).

장부 · 낡음 확인 · 15분 멈춤 · 다시 읽어 견주기 · 되돌리기 계산 · 페이지 틀은 가격 캘린더 도우미와 같은 것을 쓴다
(`../stay-price-change/scripts/change_core`). 장부는 같은 파일이고, 이 명령은 그 장부를 부가옵션 가격 줄(`addon_price`)의 장부로
연다 — 다른 도우미의 번호는 거절한다. `list` 만은 세 도우미의 기록을 모두 싣는다(줄은 저마다 그 도우미가 만든다).

    work          새 작업 폴더 — 담당자가 시킨 일 하나에 하나(기록 폴더/작업/<YYYY-MM-DD HHMMSS>/)
    look          stayAddonPrice.look() 의 답과 그 조각(take 답들) → 호텔의 부가옵션 · 가격 줄 전부(목록이 보인 그대로). 기록 폴더의
                  다른 작업 폴더의 look/(같은 호텔)에서 다 받은 같은 조각을 스스로 찾아 빌린다
    read-calls    요청 파일(필요하면 --look), 장부 번호, 또는 가격 줄 번호(--line, 바꾸지 않고 설정만 볼 때 · --look 과 같이)
                  → readLine 부를 값(calls.json)
    read          calls.json + readLine 답과 조각(폴더째) → 지금 값(snapshot.json). 읽은 시각은 그 답들이 끝난 시각 가운데 가장
                  이른 것. 기록 폴더의 앞선 읽기 폴더(같은 호텔)에서 다 받은 같은 조각을 스스로 찾아 빌린다
    plan          지금 값 + 요청(+ 빨간 줄 고름) → 미리보기 계산과 저장 단계(plan-1.json). --record 면 장부에 적는다
    render        preview | result | rollback | prices | window 페이지(HTML) — window 는 읽은 가격 줄의 편집 창 칸 전부
    begin         적용 시작 — 적용 직전에 읽은 값을 그 번호의 계산이 바탕으로 삼은 읽은 값과 견주어 한 줄이라도(딸린 칸까지)
                  다르면 아무것도 시작하지 않고 다른 줄을 댄다(종료 1). 같으면 저장 단계를 장부에 적는다
    calls         아직 저장되지 않은 단계 → applyLine 부를 값. 멈춘 변경은 다시 읽어 check 가 이어서 해도 된다고 한 뒤에만 낸다
    record-result applyLine 답 하나 → 그 단계를 장부에 됨 · 멈춤으로 적는다
    check         장부 번호 + 방금 읽은 값 → 저장마다 됨 · 안 됨 · 섞임 · 그 사이 바뀜, 남은 저장을 해도 되는지
    verify        적용 뒤 다시 읽은 값과 견주기 — 넣은 값, 그리고 그대로여야 할 필드 · 칸까지. 다르면 종료 1
    rollback      장부의 변경 하나(또는 --line 으로 고른 줄)를 되돌리는 계산. --record 면 장부에 적는다
    list          장부에 적힌 기록 목록 — 세 도우미(객실 가격 · 부가옵션 가격 · 부과금)의 것 모두, 탭의 호텔(--look) 것만,
                  --all 이면 다른 호텔 것도 그 뒤에

결과는 표준 출력에 JSON 으로 쓰고, `--out` 을 주면 그 파일에도 쓴다(기록 폴더 안이면 없는 폴더를 만들며). 파일에 쓰는 명령(look ·
read-calls · read · plan · rollback)은 `--out` 을 주면 표준 출력에는 짧은 답만 낸다. 종료 코드: 0 됨 · 1 다른 값이 있음(begin · verify) ·
2 입력이나 순서가 맞지 않음(표준 오류에 {"error": "…"} 한 줄, 조각을 받아야 하면 "refetch" — 예상하지 못한 오류도 이 한 줄이다,
change_core.cli).

예:
    python3 addon_change.py work
    python3 addon_change.py look --answers "<작업>/look" --out "<작업>/look.json"
    python3 addon_change.py list --look "<작업>/look.json"
    python3 addon_change.py read-calls --request "<작업>/request.json" --look "<작업>/look.json" --out "<R>/calls.json"
    python3 addon_change.py read --calls "<R>/calls.json" --answers "<R>" --out "<R>/snapshot.json"
    python3 addon_change.py plan --snapshot "<R>/snapshot.json" --request "<작업>/request.json" --record --out "<작업>/plan-1.json"
"""

from __future__ import annotations

import argparse
import sys

from addon_model import (
    FIELD_LABELS, FIELDS, ITEM_KIND, OFFERLESS, LineKey, ModelError, Snapshot, chosen_lines, decode_hotel, decode_line,
    decode_listing, decode_request, decode_snapshot, encode_hotel, encode_line, encode_listing, encode_request,
    encode_snapshot, hotel_label, key_of_item, keys_text, line_item_key, line_of, listing_of, name_notes_of, snapshot_items,
)
from addon_pages import (
    UNIT, blocked_lines, chosen_lines as chosen_said, red_lines, render_preview, render_prices, render_result, render_rollback,
    render_window, result_name, scope_card,
)
from addon_plan import (
    LineChange, Plan, PlanError, counts, decode_step, encode_step, line_filter, plan_change, plan_line_rollback, plan_steps,
    preview_rows, resolve, rollback_rows, rollback_steps, step_call, step_plans,
)
from change_core import cli, files
from change_core.answers import BrowserError, answers_for, attach_bodies, reading_time, step_outcome, unanswered
from change_core.chrome import nothing_to_save, page_text
from change_core.files import load, page_path
from change_core.items import encode_state, key_fields
from change_core.ledger import Ledger, LedgerError
from change_core.money import money, money_text
from change_core.rollback import decode_rollback, encode_rollback
from change_core.rules import Resolution, said_in
from change_core.window import moved_since as window_moved

PAGE_OBJECT = "stayAddonPrice"      # 이 도우미의 페이지 모듈 — 조각을 다시 받으라는 글이 이 이름의 take 를 부르라고 한다
PREFIXES = ("look-", "line-", "take-")
READS = ("readLine",)
PAGE_KEEPS = 200            # 페이지가 두는 조각 수(stay_price.js 의 KEEP_BODIES) — readLine 하나가 조각 하나다
LOOK_SHOWN = 40             # look 의 짧은 답이 싣는 고를 줄 수 — 넘으면 `more` 에 남은 수, --find 로 좁힌다
PAGE_NAMES = {"preview": "부가옵션 미리보기", "result": "부가옵션 적용 결과", "rollback": "부가옵션 되돌리기 미리보기",
              "prices": "지금 부가옵션 가격", "window": "가격 줄 설정"}


def open_ledger() -> Ledger:
    """부가옵션 가격 줄의 장부 — 가격 캘린더 도우미와 같은 파일, 이 종류의 번호만(`list` 는 종류 없이 연다)."""
    return Ledger(kind=ITEM_KIND)


def load_results(paths) -> list:
    return files.load_results(paths, PREFIXES)


# ───────────── 읽기 ─────────────

def cmd_work(args):
    return dict(work=str(files.new_work()))


def cmd_look(args):
    results = load_results(args.answers)
    looks = [result for result in attach_bodies(answers_for(results, "look"), files.lent_looks(results, args.answers, PREFIXES), PAGE_OBJECT)
             if result.get("op") == "look"]
    if len(looks) != 1:
        raise BrowserError(f"stayAddonPrice.look() 의 답이 하나여야 합니다(받은 것 {len(looks)}개)")
    look = looks[0]
    if look.get("login"):
        raise BrowserError("탭이 로그인 화면입니다 — 담당자가 직접 로그인한 뒤 다시 봅니다")
    if not look.get("ok"):
        raise BrowserError(f"stayAddonPrice.look() 이 실패했습니다: {look.get('error')}")
    return encode_listing(listing_of(look, reading_time(results, ("look",))))


def load_calls(path: str) -> dict:
    calls = load(path)
    if not isinstance(calls, dict) or not isinstance(calls.get("lines"), list):
        raise ValueError(f"read-calls 가 낸 파일(lines)이 아닙니다: {path}")
    return calls


def recorded_snapshot(ledger: Ledger, change_id: int) -> Snapshot:
    return decode_snapshot(ledger.reading(change_id))


def read_calls(hotel: str, hotel_id: str, keys) -> dict:
    keys = list(dict.fromkeys(keys))
    if len(keys) > PAGE_KEEPS:
        raise PlanError(f"가격 줄 {len(keys)}개는 읽기 한 번에 들지 않습니다({PAGE_KEEPS}줄까지) — 부가옵션으로 나눠 요청 파일을 둘 이상 씁니다")
    return dict(lines=[dict(hotel=encode_hotel(hotel, hotel_id), addon=key.addon, line=key.line) for key in keys])


def listed_keys(listing, lines) -> list:
    """가격 줄 번호들 → 줄 키 — 목록(look)에서 찾는다. 바꾸지 않고 설정만 볼 때(render window) 쓴다."""
    found = {line.key.line: line.key for line in listing.lines}
    unknown = [str(line) for line in lines if str(line) not in found]
    if unknown:
        raise ModelError(f"목록에 없는 가격 줄 번호입니다: {', '.join(unknown)} — look 의 번호를 씁니다")
    return [found[str(line)] for line in lines]


def cmd_read_calls(args):
    if args.line:
        if not args.look:
            raise ValueError("--line 으로 고를 때는 --look(이 일의 look.json)을 같이 줍니다 — 가격 줄의 부가옵션을 목록에서 찾습니다")
        listing = decode_listing(load(args.look))
        return read_calls(listing.hotel, listing.hotel_id, listed_keys(listing, args.line))
    if args.record:
        then = recorded_snapshot(open_ledger(), args.record)
        return read_calls(then.hotel, then.hotel_id, then.asked)
    request = decode_request(load(args.request))
    listing = decode_listing(load(args.look)) if args.look else None
    return read_calls(request.hotel, request.hotel_id, chosen_lines(request, listing))


def cmd_read(args):
    calls, results = load_calls(args.calls), load_results(args.answers)
    missing = unanswered(calls["lines"], results, "readLine")
    if missing:
        raise BrowserError(f"readLine 답이 없는 부를 값이 {len(missing)}개 있습니다 — 처음 것: 부가옵션 {missing[0]['addon']} · "
                           f"가격 줄 {missing[0]['line']}. 그 값으로 readLine 을 부릅니다(불렀는데 답이 끊겼거나 잘렸으면 "
                           "stayAddonPrice.last() 의 답을 새 파일로 저장해도 됩니다)")
    read_at = reading_time(results, READS)
    joined = attach_bodies(answers_for(results, "readLine"), files.lent_answers(args.calls, args.answers, calls, PREFIXES),
                           PAGE_OBJECT)
    asked = [LineKey(str(call["addon"]), str(call["line"])) for call in calls["lines"]]
    hotel, hotel_id = decode_hotel(calls["lines"][0]["hotel"]) if calls["lines"] else ("", "")
    lines = {}
    for answer in joined:
        if answer.get("op") != "readLine":
            continue
        line = line_of(answer)
        if line is not None:
            lines[line.key] = line
        if answer.get("ok") and answer.get("hotel"):
            hotel = str(answer["hotel"].get("name") or hotel)
    return encode_snapshot(Snapshot(hotel, hotel_id, read_at, tuple(asked), {key: lines[key] for key in asked if key in lines}))


# ───────────── 미리보기 ─────────────

def encode_change(change: LineChange) -> dict:
    return dict(line=encode_line(change.line), after=None if change.after is None else
                {name: money_text(value) for name, value in change.after.items()},
                verdict=change.verdict, choice=change.choice, said=change.said)


def decode_change(data) -> LineChange:
    return LineChange(decode_line(data["line"]), None if data["after"] is None else
                      {name: money(value) for name, value in data["after"].items()}, data["verdict"], data["choice"],
                      data.get("said"))


def encode_plan(plan: Plan) -> dict:
    return dict(request=encode_request(plan.request), read_at=plan.read_at, currency=plan.currency,
                changes=[encode_change(change) for change in plan.changes], missing=keys_text(plan.missing))


def decode_plan(data) -> Plan:
    return Plan(decode_request(data["request"]), str(data["read_at"]), str(data["currency"]),
                tuple(decode_change(change) for change in data["changes"]),
                tuple(LineKey(str(key["addon"]), str(key["line"])) for key in data["missing"]))


def fresh_record(args, name: str) -> None:
    files.fresh_record(args.out, args.replaces, args.record, name)


def cmd_plan(args):
    fresh_record(args, "plan")
    snapshot, request = decode_snapshot(load(args.snapshot)), decode_request(load(args.request))
    plan = plan_change(snapshot, request)
    resolutions = [Resolution(str(item["rule"]), str(item["choice"]), None if item.get("lines") is None else
                              tuple(str(line) for line in item["lines"]), said_in(item))
                   for item in load(args.resolutions)] if args.resolutions else []
    plan = resolve(plan, resolutions)
    steps = plan_steps(plan)
    change_id = open_ledger().record_preview(
        hotel=snapshot.hotel, hotel_id=snapshot.hotel_id, offer=OFFERLESS, currency=plan.currency, sentence=request.sentence,
        read_at=plan.read_at, rows=preview_rows(plan), request=encode_request(request), reading=encode_snapshot(snapshot),
        replaces=args.replaces, empty=steps is not None and not steps) if args.record else None
    names = name_notes_of(snapshot, ((line_item_key(change.key), name, change.before[name]) for change in plan.changes
                                     for name in change.writes))
    return dict(change_id=change_id, replaces=args.replaces, counts=counts(plan), plan=encode_plan(plan), red=red_lines(plan),
                chosen=chosen_said(plan), blocked=blocked_lines(plan), scope_card=scope_card(plan),
                names=[note.sentence for note in names],
                steps=None if steps is None else [encode_step(step) for step in steps])


def written_names(ledger: Ledger, record) -> list[str]:
    """저장한 필드의 바꾸기 전 값이 그 줄 · 부가옵션의 이름이나 줄의 설명에 적혀 있으면 그 알림 문장들(미리보기와 같은 셈)."""
    return [note.sentence for note in name_notes_of(recorded_snapshot(ledger, record.id), (
        (row.item_key, row.field, row.before) for row in record.rows if row.written and row.action))]


def moved_since(ledger: Ledger, change_id: int, now: Snapshot) -> list[dict]:
    """저장한 줄 가운데 그대로여야 할 것이 달라진 것 — 넣지 않은 금액과 딸린 칸(change_core.window.moved_since, 저장 단위는 줄 하나)."""
    return window_moved(ledger, change_id, snapshot_items(recorded_snapshot(ledger, change_id)), snapshot_items(now),
                        label_of=lambda key, field: FIELD_LABELS[field])


def cmd_render(args):
    if args.text and args.out:
        raise ValueError("--text 는 글만 내고 파일을 만들지 않습니다 — --out 과 같이 주지 않습니다")
    name = PAGE_NAMES[args.kind]
    if args.kind == "preview":
        data = load(args.plan)
        plan = decode_plan(data["plan"])
        html, hotel = render_preview(plan, data.get("change_id"), data.get("steps"), data.get("names") or ()), plan.request.hotel
    elif args.kind == "rollback":
        data = load(args.plan)
        plan = decode_rollback(data["rollback"])
        html, hotel = render_rollback(plan, data.get("scope") or ""), plan.hotel
    elif args.kind == "prices":
        listing = decode_listing(load(args.look))
        html, hotel = render_prices(listing), listing.hotel
    elif args.kind == "window":
        snapshot = decode_snapshot(load(args.snapshot))
        html, hotel = render_window(snapshot), snapshot.hotel
    else:
        ledger = open_ledger()
        record = ledger.change(args.change)
        moved = moved_since(ledger, args.change, decode_snapshot(load(args.snapshot))) if args.snapshot else ()
        html, hotel = render_result(record, moved, str(ledger.path), written_names(ledger, record)), record.hotel
        name = f"부가옵션 {result_name(record)}"
    if args.text:           # 글만 옮길 때 — 페이지 파일을 하나 더 만들지 않는다
        return dict(text=page_text(html))
    path = files.write_out(args.out or page_path(hotel, name), html)
    return dict(page=str(path.resolve()))


# ───────────── 적용 ─────────────

def same_hotel_or_refuse(change_id: int, then: Snapshot, now: Snapshot) -> None:
    if then.hotel_id != now.hotel_id:
        raise PlanError(f"방금 읽은 값은 {hotel_label(now.hotel, now.hotel_id)} 것이고, {change_id}번은 "
                        f"{hotel_label(then.hotel, then.hotel_id)} 입니다")


def cmd_begin(args):
    """적용 직전에 읽은 값(`--snapshot`)이 미리보기 때 값과 한 줄이라도 다르면 아무것도 시작하지 않는다(종료 1)."""
    data = load(args.plan)
    if data.get("steps") is None:
        raise PlanError("저장 단계가 없습니다. 빨간 줄을 먼저 골라 주세요")
    if not data["steps"]:
        raise PlanError(f"{args.change}번 미리보기는 바꿀 줄이 없어 적용할 것이 없습니다 — 아무것도 시작하지 않았습니다")
    ledger, now = open_ledger(), decode_snapshot(load(args.snapshot))
    then = recorded_snapshot(ledger, args.change)
    same_hotel_or_refuse(args.change, then, now)
    differences = ledger.begin_fresh(args.change, step_plans(decode_step(step) for step in data["steps"]), snapshot_items(then),
                                     snapshot_items(now), read_at=now.read_at,
                                     request=data["plan"]["request"] if "plan" in data else None)
    if differences:
        return dict(change_id=args.change, status="previewed", same=False, differences=[
            dict(key=key_fields(item.key), then=encode_state(item.then), now=encode_state(item.now)) for item in differences])
    record = ledger.change(args.change)
    return dict(change_id=record.id, status=record.status, steps=len(record.steps))


def step_payload(record, step) -> dict:
    return step_call(step.index, record.hotel, record.hotel_id, decode_step(dict(step.body, kind=step.kind)))


def cmd_calls(args):
    record = open_ledger().change(args.change)
    if not record.steps:
        raise LedgerError(f"{args.change}번 변경은 아직 적용을 시작하지 않았습니다(begin)")
    if record.status == "stopped":
        raise LedgerError(f"{args.change}번 변경은 멈춰 있습니다(저장이 실패했거나 15분 동안 아무 일이 없었습니다) — 같은 줄을 다시 "
                          f"읽고(read-calls --record {args.change}) check 가 이어서 해도 된다고 하면 calls 를 다시 부릅니다")
    return dict(change_id=record.id, status=record.status,
                calls=[step_payload(record, step) for step in record.steps if step.status != "saved"])


def cmd_record_result(args):
    result = load(args.result)
    ledger = open_ledger()
    record = ledger.change(args.change)
    step = next((step for step in record.steps if step.index == result.get("no")), None)
    if step is None:
        raise LedgerError(f"{args.change}번 변경에 {result.get('no')}번째 저장이 없습니다")
    outcome = step_outcome(step_payload(record, step), result)
    if not outcome.started:
        return dict(change_id=record.id, step=step.index, started=False, wait=outcome.wait, note=outcome.note, status=record.status)
    return dict(change_id=record.id, step=step.index, started=True, saved=outcome.saved is True, note=outcome.note,
                status=ledger.record_step(record.id, step.index, outcome.saved is True, outcome.note,
                                          unknown=outcome.saved == "unknown"))


def cmd_check(args):
    ledger = open_ledger()
    now = decode_snapshot(load(args.snapshot))
    then = recorded_snapshot(ledger, args.change)
    same_hotel_or_refuse(args.change, then, now)
    report = ledger.check(args.change, snapshot_items(now), snapshot_items(then), now.read_at)
    step_ref = (lambda step: None if step is None else dict(no=step.index, label=step.label))
    return dict(change_id=report.change_id, scope=listed(ledger, args.change)[0]["scope"], status=report.status,
                cause=report.cause, note=report.note, last_saved=step_ref(report.last_saved), next=step_ref(report.next),
                remaining=list(report.remaining), can_continue=report.can_continue, why=list(report.why),
                steps=[dict(no=step.index, label=step.label, ledger=step.ledger, seen=step.seen, settled=step.settled,
                            moved=step.moved) for step in report.steps])


def cmd_verify(args):
    ledger, now = open_ledger(), decode_snapshot(load(args.snapshot))
    same_hotel_or_refuse(args.change, recorded_snapshot(ledger, args.change), now)
    mismatches = ledger.verify(args.change, snapshot_items(now))
    moved = moved_since(ledger, args.change, now)
    return dict(change_id=args.change, same=not mismatches and not moved, moved=moved,
                names=written_names(ledger, ledger.change(args.change)), mismatches=[
        dict(line=key_of_item(item.item_key).line, label=item.label, field=item.field, after=money_text(item.after),
             seen=money_text(item.seen), seen_state=item.seen_state) for item in mismatches])


# ───────────── 되돌리기 · 목록 ─────────────

def cmd_rollback(args):
    fresh_record(args, "rollback")
    ledger = open_ledger()
    now = decode_snapshot(load(args.snapshot))
    select, picked = line_filter(args.line or ())
    plan = plan_line_rollback(ledger.recorded_change(args.change), ledger.later_writes(args.change), now, args.include_kept, select)
    steps, rows = rollback_steps(plan, now), rollback_rows(plan, now)
    request = dict(kind="rollback", scope=picked) if picked else None      # 고른 줄 — 장부 목록의 범위 한 줄이 말한다
    change_id = ledger.record_preview(hotel=plan.hotel, hotel_id=plan.hotel_id, offer=OFFERLESS, currency=plan.currency,
                                      sentence=args.sentence, read_at=plan.read_at, rows=rows, reverses=args.change,
                                      request=request, reading=encode_snapshot(now), replaces=args.replaces,
                                      empty=not steps) if args.record else None
    # 되돌리기 확인이 읽는 범위 한 줄 — 장부에 적었으면 `list` 의 그 번호 줄, 아니면 같은 셈
    scope = listed(ledger, change_id)[0]["scope"] if change_id is not None else scope_line(rows, record_what(request, args.change))
    return dict(change_id=change_id, replaces=args.replaces, scope=scope, rollback=encode_rollback(plan),
                steps=[encode_step(step) for step in steps])


def record_what(request: dict | None, reverses: int | None) -> str:
    """장부의 번호가 한 일 — "판매가 +10%" · "3번 되돌리기" · "3번 되돌리기 (가격 줄 301번만)"."""
    if reverses:
        return f"{reverses}번 되돌리기" + (f" ({request['scope']}만)" if request and request.get("scope") else "")
    if request and request.get("kind") == "addon_change":
        try:
            return decode_request(request).describe()
        except (ModelError, KeyError, TypeError, ValueError):
            return ""
    return ""


def scope_line(rows, did: str, progress: str = "") -> str:
    """범위 한 줄 — 저장이 값을 넣는(넣을) 줄이 몇 줄인지와 처음 줄 이름, 한 일, 어디까지 갔는지(`progress`). 안 바꾸기로 고른 줄 ·
    아직 고르지 않은 빨간 줄 · 적용할 수 없는 줄은 세지 않는다(가격 도우미의 「N칸」과 같은 셈 — 되돌리기 확인이 이 줄을 읽어 준다).
    넣는 줄이 없으면 이름은 고른 줄의 것이다."""
    written = {row.item_key for row in rows if row.action}
    labels = [(row.label, row.item_key in written) for row in rows if row.field == FIELDS[0]]
    names = list(dict.fromkeys(label for label, writes in labels if writes))
    shown = names or list(dict.fromkeys(label for label, _writes in labels))
    head = f"부가옵션 가격 줄 {len(names)}개" + (f" ({shown[0]}{' 외' if len(shown) > 1 else ''})" if shown else "")
    return " · ".join(part for part in (head, did, progress) if part)


def record_scope(entry: dict, rows) -> str:
    """장부 한 줄의 범위(scope_line) — 어디까지 갔는지는 세 도우미가 같은 말이다(멈춤 · 적용 중 · 모두 · 일부 되돌림 · 저장할 것
    없음 — files.record_progress)."""
    return scope_line(rows, record_what(entry.get("request"), entry.get("reverses")), files.record_progress(entry, UNIT))


def described(ledger: Ledger, entry: dict) -> dict:
    """부가옵션 가격 줄 기록 한 줄에 범위 한 줄(`scope`)과 그 변경의 줄이 든 오퍼(`offer` — 둘 이상이면 ` · ` 로 잇는다. 부가옵션
    변경은 오퍼 하나에 묶이지 않아 장부의 오퍼 칸이 비어 있으므로, 그 번호의 읽은 값에서 줄마다의 오퍼를 모은다)를 단다. 다른 두
    도우미의 `list` 도 이것으로 이 종류의 줄을 만든다."""
    rows = ledger.change(entry["id"]).rows
    lines = recorded_snapshot(ledger, entry["id"]).lines
    offers = dict.fromkeys(lines[key].listed.offer for key in map(key_of_item, (row.item_key for row in rows)) if key in lines)
    return dict(entry, scope=record_scope(entry, rows), offer=" · ".join(offer for offer in offers if offer))


def listed(ledger: Ledger, change_id: int | None = None) -> list[dict]:
    """장부 목록의 줄마다(`change_id` 를 주면 그 번호만) 범위 한 줄 — 종류로 연 장부면 부가옵션 가격 줄 기록만(files.listed)."""
    return files.listed(ledger, ITEM_KIND, described, change_id)


def cmd_list(args):
    """탭의 호텔의 기록 전부 — 세 도우미의 것을 모두, 저마다 그 도우미가 만든 줄로."""
    ledger = Ledger()
    return files.hotel_list(ledger.path, listed(ledger), args.look, args.all)


# ───────────── 짧은 답 · 파서 ─────────────

def look_item(line: dict) -> dict:
    """고를 줄 하나 — 요청 파일에 옮길 번호(`addon` · `line`)와 담당자에게 말할 이름(오퍼부터 — 오퍼마다 이름이 같은 부가옵션이 있다)."""
    return dict(offer=line["offer"], addon=line["addon"], addon_name=line["addon_name"], line=line["line"], name=line["name"],
                target=line["target"], sell=line["sell"])


def short_look(result: dict, find: str | None = None) -> dict:
    """호텔과 수, 그리고 고를 줄(`items`, LOOK_SHOWN 줄까지 — 넘으면 `more` 에 남은 수). `find` 를 주면 오퍼 · 부가옵션 · 줄 이름 ·
    적용 대상에 그 낱말이 든 줄만(`found` 는 그 수) — 도우미는 이 목록에서 고르고 파일을 통째로 읽지 않는다."""
    items = [look_item(line) for line in result["lines"]
             if not find or find.casefold() in " ".join((line["offer"], line["addon_name"], line["name"], line["target"])).casefold()]
    short = dict(hotel=result["hotel"], currency=result["currency"], read_at=result["read_at"], addons=len(result["addons"]),
                 lines=len(result["lines"]))
    if find:
        short.update(find=find, found=len(items))
    short["items"] = items[:LOOK_SHOWN]
    if len(items) > LOOK_SHOWN:
        short["more"] = len(items) - LOOK_SHOWN
    return short


def short_read_calls(result: dict) -> dict:
    return dict(lines=result["lines"])


def short_read(result: dict) -> dict:
    snapshot = decode_snapshot(result)
    doubt = [line.key.line for line in snapshot.lines.values() if line.doubt]
    return dict(hotel=result["hotel"], currency=result["currency"], read_at=result["read_at"], asked=len(snapshot.asked),
                found=len(snapshot.lines), missing=[key.line for key in snapshot.missing()], doubt=doubt)


def short_plan(result: dict) -> dict:
    """`nothing` 은 저장할 것이 없을 때(`saves` 0)만 — 도우미가 그대로 하는 말(빨간 줄을 고른 것이 있을 때만 「고르신 대로면」)."""
    saves = None if result["steps"] is None else len(result["steps"])
    short = dict(change_id=result["change_id"], replaces=result["replaces"], counts=result["counts"], saves=saves,
                 red=result["red"], chosen=result["chosen"], blocked=result["blocked"], names=result["names"],
                 scope_card=result["scope_card"])
    if saves == 0:
        short["nothing"] = nothing_to_save(bool(result["counts"]["chosen"]), UNIT)
    return short


def short_rollback(result: dict) -> dict:
    plan = decode_rollback(result["rollback"])
    causes: dict[tuple, int] = {}
    for item in plan.kept:
        cause = (item.cause.change_id, item.cause.at, item.cause.sentence, item.cause.why)
        causes[cause] = causes.get(cause, 0) + 1
    return dict(change_id=result["change_id"], replaces=result["replaces"], scope=result["scope"], restore_to=plan.restore_to,
                restored=len(plan.restored), kept=len(plan.kept),
                kept_why=[dict(change_id=change_id, at=at, sentence=sentence, why=why, outside=change_id is None and why is None,
                               lines=count)
                          for (change_id, at, sentence, why), count in causes.items()],
                saves=len(result["steps"]), undoing=plan.undoing or None)


SHORT = {"look": short_look, "read-calls": short_read_calls, "read": short_read, "plan": short_plan, "rollback": short_rollback}


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="addon_change.py", description="부가옵션 가격 도우미의 명령")
    commands = top.add_subparsers(dest="command", required=True)

    def command(name: str, handler, help_text: str):
        sub = commands.add_parser(name, help=help_text)
        sub.set_defaults(handler=handler)
        sub.add_argument("--out", help="결과(JSON, render 는 HTML)를 쓸 파일")
        return sub

    command("work", cmd_work, "새 작업 폴더")
    sub = command("look", cmd_look, "look 답 → 부가옵션 · 가격 줄 전부")
    sub.add_argument("--answers", action="append", required=True, help="look 답과 take 답 파일, 또는 그것이 든 폴더 (여러 번)")
    sub.add_argument("--find", help="짧은 답의 고를 줄을 이 낱말(오퍼 · 부가옵션 · 줄 이름 · 적용 대상)로 좁힌다 — 파일은 전부")
    sub = command("read-calls", cmd_read_calls, "읽을 줄 → readLine 부를 값")
    scope = sub.add_mutually_exclusive_group(required=True)
    scope.add_argument("--request", help="바꾸기 요청 파일(kind addon_change)")
    scope.add_argument("--record", type=int, help="장부 번호 — 그 번호의 계산이 바탕으로 삼은 줄을 다시 읽는다")
    scope.add_argument("--line", action="append", help="가격 줄 번호(여러 번) — 바꾸지 않고 설정만 볼 때. --look 과 같이 준다")
    sub.add_argument("--look", help="look 명령이 낸 파일 — 요청이 부가옵션 · 전부로 고를 때")
    sub = command("read", cmd_read, "readLine 답 → 지금 값")
    sub.add_argument("--calls", required=True, help="read-calls 가 낸 파일")
    sub.add_argument("--answers", action="append", required=True, help="readLine 답과 take 답 파일, 또는 그것이 든 폴더 (여러 번)")
    sub = command("plan", cmd_plan, "미리보기 계산")
    sub.add_argument("--snapshot", required=True)
    sub.add_argument("--request", required=True, help="바꾸기 요청 파일(kind addon_change)")
    sub.add_argument("--resolutions", help='빨간 줄 고름 JSON 목록 — [{"rule": "OVER_30", "choice": "include", "lines": ["301"], '
                     '"said": "<담당자 말>"}]')
    sub.add_argument("--record", action="store_true", help="장부에 미리보기로 적는다")
    sub.add_argument("--replaces", type=int, help="이 계산이 바꾸는 앞 미리보기의 장부 번호(빨간 줄을 고른 뒤 · 적용 직전에 값이 달라 다시 계산함)")
    sub = command("render", cmd_render, "페이지 만들기")
    sub.add_argument("kind", choices=sorted(PAGE_NAMES))
    sub.add_argument("--plan", help="preview 는 plan-<k>.json, rollback 은 rollback-<k>.json")
    sub.add_argument("--look", help="prices 의 look 파일")
    sub.add_argument("--change", type=int, help="result 의 장부 번호")
    sub.add_argument("--snapshot", help="result — 적용 뒤에 읽은 값(그대로여야 할 칸이 달라졌는지도 보인다), window — 읽은 값")
    sub.add_argument("--text", action="store_true", help="페이지에 보이는 글만 답의 text 로 낸다 — 파일을 만들지 않는다")
    sub = command("begin", cmd_begin, "적용 시작")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--plan", required=True, help="steps 가 든 plan-<k>.json 또는 rollback-<k>.json")
    sub.add_argument("--snapshot", required=True, help="적용 직전에 같은 줄을 읽은 값(read-calls --record N 으로 읽는다, 15분 안)")
    sub = command("calls", cmd_calls, "남은 저장 → applyLine 부를 값")
    sub.add_argument("--change", type=int, required=True)
    sub = command("record-result", cmd_record_result, "applyLine 답 하나를 장부에")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--result", required=True, help="stayAddonPrice.applyLine 답 JSON")
    sub = command("check", cmd_check, "멈춘 변경을 방금 읽은 값으로 보기")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--snapshot", required=True, help="방금 같은 줄을 읽은 값(read-calls --record N 으로 읽는다)")
    sub = command("verify", cmd_verify, "적용 뒤 견주기")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--snapshot", required=True)
    sub = command("rollback", cmd_rollback, "되돌리기 계산")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--snapshot", required=True, help="지금 읽은 값(read-calls --record <그 번호> 로 읽는다)")
    sub.add_argument("--include-kept", action="store_true", help="그 사이 달라진 줄도 되돌린다")
    sub.add_argument("--line", action="append", help="이 가격 줄 번호만 (여러 번)")
    sub.add_argument("--record", action="store_true", help="장부에 되돌리기 미리보기로 적는다")
    sub.add_argument("--replaces", type=int, help="이 계산이 바꾸는 앞 되돌리기 미리보기(같은 변경을 되돌리는 것)의 장부 번호")
    sub.add_argument("--sentence", default="되돌리기", help="담당자가 한 말")
    sub = command("list", cmd_list, "장부 목록")
    sub.add_argument("--look", help="look 명령이 낸 파일 — 탭에 열린 호텔의 기록만 싣는다")
    sub.add_argument("--all", action="store_true", help="다른 호텔의 기록도 싣는다(탭의 호텔이 먼저)")
    return top


def main(argv=None) -> int:
    cli.utf8_streams()
    args = parser().parse_args(argv)
    if args.command == "render":
        needed = {"preview": "plan", "rollback": "plan", "prices": "look", "result": "change", "window": "snapshot"}[args.kind]
        if getattr(args, needed) is None:
            parser().error(f"render {args.kind} 에는 --{needed} 가 필요합니다")
    return cli.run(args, dict(SHORT, look=lambda result: short_look(result, getattr(args, "find", None))))


if __name__ == "__main__":
    sys.exit(main())
