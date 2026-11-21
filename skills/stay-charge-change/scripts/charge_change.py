#!/usr/bin/env python3
"""charge_change.py — 부과금 도우미의 명령. JSON 파일을 받고 JSON 을 돌려준다(브라우저 쪽이 이 명령을 부른다).

장부 · 낡음 확인 · 15분 멈춤 · 다시 읽어 견주기 · 되돌리기 계산 · 저장 한 걸음 · 페이지 틀은 다른 두 도우미와 같은 것을 쓴다
(`../stay-price-change/scripts/change_core`). 장부는 같은 파일이고, 이 명령은 그 장부를 부과금(`charge`)의 장부로 연다 — 목록에는
부과금 번호만 나오고, 다른 도우미의 번호는 거절한다.

    work          새 작업 폴더 — 담당자가 시킨 일 하나에 하나(기록 폴더/작업/<YYYY-MM-DD HHMMSS>/)
    look          stayCharge.look() 의 답과 그 조각(take 답들) → 호텔의 오퍼마다 부과금 전부(목록이 보인 그대로). 기록 폴더의
                  다른 작업 폴더의 look/(같은 호텔)에서 다 받은 같은 조각을 스스로 찾아 빌린다
    read-calls    요청 파일(목록 확인은 --look), 또는 장부 번호 → readCharge 부를 값(calls.json)
    read          calls.json + readCharge 답과 조각(폴더째) → 지금 값(snapshot.json). 읽은 시각은 그 답들이 끝난 시각 가운데 가장
                  이른 것. 기록 폴더의 앞선 읽기 폴더(같은 호텔)에서 다 받은 같은 조각을 스스로 찾아 빌린다
    plan          지금 값 + 요청(+ 빨간 줄 고름) → 미리보기 계산과 저장 단계(plan-1.json). --record 면 장부에 적는다
    render        preview | result | rollback | prices 페이지(HTML). --text 면 파일을 만들지 않고 페이지의 글만 낸다(--out 과 같이 주지 않는다)
    begin         적용 시작 — 적용 직전에 읽은 값을 그 번호의 계산이 바탕으로 삼은 읽은 값과 견주어 한 칸이라도(딸린 칸까지)
                  다르면 아무것도 시작하지 않고 다른 것을 댄다(종료 1). 같으면 저장 단계를 장부에 적는다
    calls         아직 저장되지 않은 단계 → applyCharge 부를 값. 멈춘 변경은 다시 읽어 check 가 이어서 해도 된다고 한 뒤에만 낸다
    record-result applyCharge 답 하나 → 그 단계를 장부에 됨 · 멈춤으로 적는다
    check         장부 번호 + 방금 읽은 값 → 저장마다 됨 · 안 됨 · 섞임 · 그 사이 바뀜, 남은 저장을 해도 되는지
    verify        적용 뒤 다시 읽은 값과 견주기 — 넣은 값, 그리고 그 부과금의 다른 금액 · 칸이 그대로인지. 다르면 종료 1
    rollback      장부의 변경 하나(또는 --charge 로 고른 부과금)를 되돌리는 계산. --record 면 장부에 적는다
    list          장부에 적힌 부과금 변경 목록 — 탭의 호텔(--look) 것만, --all 이면 다른 호텔 것도 그 뒤에

결과는 표준 출력에 JSON 으로 쓰고, `--out` 을 주면 그 파일에도 쓴다. 파일에 쓰는 명령(look · read-calls · read · plan · rollback)은
`--out` 을 주면 표준 출력에는 짧은 답만 낸다. 종료 코드: 0 됨 · 1 다른 값이 있음(begin · verify) · 2 입력이나 순서가 맞지 않음
(표준 오류에 {"error": "…"}, 조각을 받아야 하면 "refetch").

예:
    python3 charge_change.py work
    python3 charge_change.py look --answers "<작업>/look" --out "<작업>/look.json"
    python3 charge_change.py list --look "<작업>/look.json"
    python3 charge_change.py read-calls --request "<작업>/request.json" --look "<작업>/look.json" --out "<R>/calls.json"
    python3 charge_change.py read --calls "<R>/calls.json" --answers "<R>" --out "<R>/snapshot.json"
    python3 charge_change.py plan --snapshot "<R>/snapshot.json" --request "<작업>/request.json" --record --out "<작업>/plan-1.json"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from charge_model import (
    ITEM_KIND, OFFERLESS, ModelError, Snapshot, charge_of, charge_of_key, decode_hotel, decode_listing, decode_request,
    decode_snapshot, encode_hotel, encode_listing, encode_request, encode_snapshot, field_label_of, hotel_label,
    known_charges, listing_of, part_of_key, refs_text, snapshot_items,
)
from charge_pages import (
    blocked_amounts, chosen_amounts, free_amounts, red_lines, render_preview, render_prices, render_result, render_rollback,
)
from charge_plan import (
    PlanError, charge_filter, counts, decode_plan, decode_step, encode_plan, encode_step, plan_change, plan_charge_rollback,
    plan_steps, preview_rows, resolve, rollback_rows, rollback_steps, step_call, step_plans,
)
from change_core import files
from change_core.answers import BrowserError, answers_for, attach_bodies, reading_time, step_outcome, unanswered
from change_core.chrome import page_text
from change_core.files import load, page_path
from change_core.items import encode_state, key_fields
from change_core.ledger import Ledger, LedgerError
from change_core.money import money_text
from change_core.rollback import decode_rollback, encode_rollback
from change_core.rules import Resolution, said_in
from change_core.window import moved_since as window_moved

PREFIXES = ("look-", "charge-", "take-")
PAGE_OBJECT = "stayCharge"          # 조각을 다시 받으라고 할 때 부르라고 말하는 페이지 모듈
READS = ("readCharge",)
PAGE_KEEPS = 200            # 페이지가 두는 조각 수(stay_price.js 의 KEEP_BODIES) — readCharge 하나가 조각 하나다
PAGE_NAMES = {"preview": "부과금 미리보기", "result": "부과금 적용 결과", "rollback": "부과금 되돌리기 미리보기",
              "prices": "지금 부과금"}


def open_ledger() -> Ledger:
    """부과금의 장부 — 다른 두 도우미와 같은 파일, 이 종류의 번호만."""
    return Ledger(kind=ITEM_KIND)


def load_results(paths) -> list:
    return files.load_results(paths, PREFIXES)


# ───────────── 읽기 ─────────────

def cmd_work(args):
    return dict(work=str(files.new_work()))


def cmd_look(args):
    results = load_results(args.answers)
    looks = [result for result in attach_bodies(answers_for(results, "look"), files.lent_looks(results, args.answers, PREFIXES),
                                                PAGE_OBJECT) if result.get("op") == "look"]
    if len(looks) != 1:
        raise BrowserError(f"stayCharge.look() 의 답이 하나여야 합니다(받은 것 {len(looks)}개)")
    look = looks[0]
    if look.get("login"):
        raise BrowserError("탭이 로그인 화면입니다 — 담당자가 직접 로그인한 뒤 다시 봅니다")
    if not look.get("ok"):
        raise BrowserError(f"stayCharge.look() 이 실패했습니다: {look.get('error')}")
    return encode_listing(listing_of(look, reading_time(results, ("look",))))


def load_calls(path: str) -> dict:
    calls = load(path)
    if not isinstance(calls, dict) or not isinstance(calls.get("charges"), list):
        raise ValueError(f"read-calls 가 낸 파일(charges)이 아닙니다: {path}")
    return calls


def recorded_snapshot(ledger: Ledger, change_id: int) -> Snapshot:
    return decode_snapshot(ledger.reading(change_id))


def read_calls(hotel: str, hotel_id: str, refs) -> dict:
    refs = list(dict.fromkeys(refs))
    if len(refs) > PAGE_KEEPS:
        raise PlanError(f"부과금 {len(refs)}개는 읽기 한 번에 들지 않습니다({PAGE_KEEPS}개까지) — 요청 파일을 둘 이상으로 나눕니다")
    return dict(charges=[dict(hotel=encode_hotel(hotel, hotel_id), offer=offer, charge=charge) for offer, charge in refs])


def cmd_read_calls(args):
    if args.record:
        then = recorded_snapshot(open_ledger(), args.record)
        return read_calls(then.hotel, then.hotel_id, then.asked)
    request = decode_request(load(args.request))
    listing = decode_listing(load(args.look)) if args.look else None
    return read_calls(request.hotel, request.hotel_id, known_charges(request, listing))


def cmd_read(args):
    calls, results = load_calls(args.calls), load_results(args.answers)
    missing = unanswered(calls["charges"], results, "readCharge")
    if missing:
        raise BrowserError(f"readCharge 답이 없는 부를 값이 {len(missing)}개 있습니다 — 처음 것: 오퍼 {missing[0]['offer']} · "
                           f"부과금 {missing[0]['charge']}. 그 값으로 readCharge 를 부릅니다(불렀는데 답이 끊겼거나 잘렸으면 "
                           "stayCharge.last() 의 답을 새 파일로 저장해도 됩니다)")
    read_at = reading_time(results, READS)
    joined = attach_bodies(answers_for(results, "readCharge"), files.lent_answers(args.calls, args.answers, calls, PREFIXES),
                           PAGE_OBJECT)
    asked = [(str(call["offer"]), str(call["charge"])) for call in calls["charges"]]
    hotel, hotel_id = decode_hotel(calls["charges"][0]["hotel"]) if calls["charges"] else ("", "")
    charges = {}
    for answer in joined:
        if answer.get("op") != "readCharge":
            continue
        charge = charge_of(answer)
        if charge is not None:
            charges[charge.id] = charge
        if answer.get("ok") and answer.get("hotel"):
            hotel = str(answer["hotel"].get("name") or hotel)
    return encode_snapshot(Snapshot(hotel, hotel_id, read_at, tuple(asked),
                                    {charge: charges[charge] for _offer, charge in asked if charge in charges}))


# ───────────── 미리보기 ─────────────

def fresh_record(args, name: str) -> None:
    files.fresh_record(args.out, args.replaces, args.record, name)


def cmd_plan(args):
    fresh_record(args, "plan")
    snapshot, request = decode_snapshot(load(args.snapshot)), decode_request(load(args.request))
    plan = plan_change(snapshot, request)
    resolutions = [Resolution(str(item["rule"]), str(item["choice"]), None if item.get("amounts") is None else
                              tuple(str(name) for name in item["amounts"]), said_in(item))
                   for item in load(args.resolutions)] if args.resolutions else []
    plan = resolve(plan, resolutions)
    steps = plan_steps(plan)
    change_id = open_ledger().record_preview(
        hotel=snapshot.hotel, hotel_id=snapshot.hotel_id, offer=OFFERLESS, currency=plan.currency, sentence=request.sentence,
        read_at=plan.read_at, rows=preview_rows(plan), request=encode_request(request), reading=encode_snapshot(snapshot),
        replaces=args.replaces, empty=steps is not None and not steps) if args.record else None
    return dict(change_id=change_id, replaces=args.replaces, counts=counts(plan), plan=encode_plan(plan, encode_request),
                red=red_lines(plan), chosen=chosen_amounts(plan), blocked=blocked_amounts(plan), free=free_amounts(plan),
                scope_card=any(name.startswith("scope_") for charge in plan.charges for name, _text in charge.form),
                steps=None if steps is None else [encode_step(step) for step in steps])


def moved_since(ledger: Ledger, change_id: int, now: Snapshot) -> list[dict]:
    """저장한 부과금 가운데 그대로여야 할 것이 달라진 것 — 그 부과금의 넣지 않은 금액(시간대 · 연령별 단가까지), 딸린 칸, 새로 생긴
    시간대 줄 · 연령별 단가(change_core.window.moved_since, 저장 단위는 부과금 하나)."""
    return window_moved(ledger, change_id, snapshot_items(recorded_snapshot(ledger, change_id)), snapshot_items(now),
                        unit=charge_of_key, label_of=field_label_of)


def cmd_render(args):
    if args.text and args.out:
        raise ValueError("--text 는 글만 내고 파일을 만들지 않습니다 — --out 과 같이 주지 않습니다")
    name = PAGE_NAMES[args.kind]
    if args.kind == "preview":
        data = load(args.plan)
        plan = decode_plan(data["plan"], decode_request)
        html, hotel = render_preview(plan, data.get("change_id"), data.get("steps")), plan.request.hotel
    elif args.kind == "rollback":
        data = load(args.plan)
        plan = decode_rollback(data["rollback"])
        html, hotel = render_rollback(plan, data.get("scope") or ""), plan.hotel
    elif args.kind == "prices":
        listing = decode_listing(load(args.look))
        html, hotel = render_prices(listing), listing.hotel
    else:
        ledger = open_ledger()
        record = ledger.change(args.change)
        moved = moved_since(ledger, args.change, decode_snapshot(load(args.snapshot))) if args.snapshot else ()
        html, hotel = render_result(record, moved, str(ledger.path)), record.hotel
        name = "부과금 되돌리기 결과" if record.kind == "rollback" else name
    if args.text:           # 글만 옮길 때 — 페이지 파일을 하나 더 만들지 않는다
        return dict(text=page_text(html))
    path = Path(args.out) if args.out else page_path(hotel, name)
    path.write_text(html, encoding="utf-8")
    return dict(page=str(path.resolve()))


# ───────────── 적용 ─────────────

def same_hotel_or_refuse(change_id: int, then: Snapshot, now: Snapshot) -> None:
    if then.hotel_id != now.hotel_id:
        raise PlanError(f"방금 읽은 값은 {hotel_label(now.hotel, now.hotel_id)} 것이고, {change_id}번은 "
                        f"{hotel_label(then.hotel, then.hotel_id)} 입니다")


def cmd_begin(args):
    """적용 직전에 읽은 값(`--snapshot`)이 미리보기 때 값과 한 칸이라도 다르면 아무것도 시작하지 않는다(종료 1)."""
    data = load(args.plan)
    if data.get("steps") is None:
        raise PlanError("빨간 줄을 먼저 골라 주세요 — 아직 저장 단계가 없습니다")
    if not data["steps"]:
        raise PlanError("저장할 것이 없는 미리보기입니다(바뀌는 칸이 없습니다) — 적용할 것이 없습니다")
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
        raise LedgerError(f"{args.change}번 변경은 멈춰 있습니다(저장이 실패했거나 15분 동안 아무 일이 없었습니다) — 같은 부과금을 다시 "
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
    report = ledger.check(args.change, snapshot_items(now), snapshot_items(then), now.read_at, unit=charge_of_key)
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
    return dict(change_id=args.change, same=not mismatches and not moved, moved=moved, mismatches=[
        dict(charge=charge_of_key(item.item_key), label=item.label, field=item.field,
             what=field_label_of(item.item_key, item.field), after=money_text(item.after), seen=money_text(item.seen),
             seen_state=item.seen_state) for item in mismatches])


# ───────────── 되돌리기 · 목록 ─────────────

def cmd_rollback(args):
    fresh_record(args, "rollback")
    ledger = open_ledger()
    now = decode_snapshot(load(args.snapshot))
    select, scope = charge_filter(args.charge or ())
    plan = plan_charge_rollback(ledger.recorded_change(args.change), ledger.later_writes(args.change), now, args.include_kept,
                                select)
    steps = rollback_steps(plan, now)
    change_id = ledger.record_preview(hotel=plan.hotel, hotel_id=plan.hotel_id, offer=OFFERLESS, currency=plan.currency,
                                      sentence=args.sentence, read_at=plan.read_at, rows=rollback_rows(plan, now),
                                      reverses=args.change, reading=encode_snapshot(now),
                                      replaces=args.replaces, empty=not steps) if args.record else None
    return dict(change_id=change_id, replaces=args.replaces, scope=scope or listed(ledger, args.change)[0]["scope"],
                rollback=encode_rollback(plan), steps=[encode_step(step) for step in steps])


def record_scope(entry: dict, labels: list[str]) -> str:
    """장부 한 줄의 범위 — 저장이 값을 넣는(넣을) 부과금 몇 개와 처음 부과금 이름(넣을 것이 없으면 짚은 부과금), 한 일, 멈췄으면 어디까지,
    저장할 것이 없는 미리보기면 그렇다고."""
    names = list(dict.fromkeys(labels))
    head = f"부과금 {len(names)}개" + (f" ({names[0]}{' 외' if len(names) > 1 else ''})" if names else "")
    request = entry.get("request") or {}
    did = ""
    if request.get("kind") == "charge_change":
        try:
            did = " · " + decode_request(request).describe()
        except (ModelError, KeyError, TypeError, ValueError):
            did = ""
    elif entry.get("reverses"):
        did = f" · {entry['reverses']}번 되돌리기"
    stopped = f" · {entry['saved_steps']}/{entry['steps']}번 저장하고 멈춤" if entry["status"] == "stopped" else ""
    return head + did + stopped + (" · 저장할 것 없음" if entry["status"] == "empty" else "")


def listed(ledger: Ledger, change_id: int | None = None) -> list[dict]:
    out = []
    for entry in ledger.list_changes(change_id):
        rows = ledger.change(entry["id"]).rows
        touched = {charge_of_key(row.item_key) for row in rows if row.action} or {charge_of_key(row.item_key) for row in rows}
        labels = [row.label for row in rows if part_of_key(row.item_key)[1] == "main" and row.field == "amount"
                  and charge_of_key(row.item_key) in touched]
        entry["scope"] = record_scope(entry, labels)
        del entry["request"]
        out.append(entry)
    return out


def cmd_list(args):
    ledger = open_ledger()
    return files.hotel_list(ledger.path, listed(ledger), args.look, args.all)


# ───────────── 짧은 답 · 파서 ─────────────

def short_look(result: dict) -> dict:
    return dict(hotel=result["hotel"], read_at=result["read_at"], offers=len(result["offers"]), charges=len(result["charges"]))


def short_read_calls(result: dict) -> dict:
    return dict(charges=result["charges"])


def short_read(result: dict) -> dict:
    snapshot = decode_snapshot(result)
    return dict(hotel=result["hotel"], currency=result["currency"], read_at=result["read_at"], asked=len(snapshot.asked),
                found=len(snapshot.charges), missing=[charge for _offer, charge in snapshot.missing()])


def short_plan(result: dict) -> dict:
    return dict(change_id=result["change_id"], replaces=result["replaces"], counts=result["counts"],
                saves=None if result["steps"] is None else len(result["steps"]), red=result["red"], chosen=result["chosen"],
                blocked=result["blocked"], free=result["free"], scope_card=result["scope_card"])


def short_rollback(result: dict) -> dict:
    plan = decode_rollback(result["rollback"])
    causes: dict[tuple, int] = {}
    for item in plan.kept:
        cause = (item.cause.change_id, item.cause.at, item.cause.sentence)
        causes[cause] = causes.get(cause, 0) + 1
    return dict(change_id=result["change_id"], replaces=result["replaces"], scope=result["scope"], restore_to=plan.restore_to,
                restored=len(plan.restored), kept=len(plan.kept),
                kept_why=[dict(change_id=change_id, at=at, sentence=sentence, outside=change_id is None, items=count)
                          for (change_id, at, sentence), count in causes.items()],
                saves=len(result["steps"]))


SHORT = {"look": short_look, "read-calls": short_read_calls, "read": short_read, "plan": short_plan, "rollback": short_rollback}


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="charge_change.py", description="부과금 도우미의 명령")
    commands = top.add_subparsers(dest="command", required=True)

    def command(name: str, handler, help_text: str):
        sub = commands.add_parser(name, help=help_text)
        sub.set_defaults(handler=handler)
        sub.add_argument("--out", help="결과(JSON, render 는 HTML)를 쓸 파일")
        return sub

    command("work", cmd_work, "새 작업 폴더")
    sub = command("look", cmd_look, "look 답 → 오퍼마다 부과금 전부")
    sub.add_argument("--answers", action="append", required=True, help="look 답과 take 답 파일, 또는 그것이 든 폴더 (여러 번)")
    sub = command("read-calls", cmd_read_calls, "읽을 부과금 → readCharge 부를 값")
    scope = sub.add_mutually_exclusive_group(required=True)
    scope.add_argument("--request", help="바꾸기 요청 파일(kind charge_change)")
    scope.add_argument("--record", type=int, help="장부 번호 — 그 번호의 계산이 바탕으로 삼은 부과금을 다시 읽는다")
    sub.add_argument("--look", help="look 명령이 낸 파일 — 요청의 오퍼 · 부과금 번호가 목록에 있는지 본다")
    sub = command("read", cmd_read, "readCharge 답 → 지금 값")
    sub.add_argument("--calls", required=True, help="read-calls 가 낸 파일")
    sub.add_argument("--answers", action="append", required=True, help="readCharge 답과 take 답 파일, 또는 그것이 든 폴더 (여러 번)")
    sub = command("plan", cmd_plan, "미리보기 계산")
    sub.add_argument("--snapshot", required=True)
    sub.add_argument("--request", required=True, help="바꾸기 요청 파일(kind charge_change)")
    sub.add_argument("--resolutions", help='빨간 줄 고름 JSON 목록 — [{"rule": "OVER_30", "choice": "include", "amounts": ["701 14:01-18:00 pct"], '
                     '"said": "<담당자 말>"}]')
    sub.add_argument("--record", action="store_true", help="장부에 미리보기로 적는다")
    sub.add_argument("--replaces", type=int, help="이 계산이 바꾸는 앞 미리보기의 장부 번호(빨간 줄을 고른 뒤 · 적용 직전에 값이 달라 다시 계산함)")
    sub = command("render", cmd_render, "페이지 만들기")
    sub.add_argument("kind", choices=sorted(PAGE_NAMES))
    sub.add_argument("--plan", help="preview 는 plan-<k>.json, rollback 은 rollback-<k>.json")
    sub.add_argument("--look", help="prices 의 look 파일")
    sub.add_argument("--change", type=int, help="result 의 장부 번호")
    sub.add_argument("--snapshot", help="result — 적용 뒤에 읽은 값(그대로여야 할 칸이 달라졌는지도 보인다)")
    sub.add_argument("--text", action="store_true", help="페이지를 만들지 않고 페이지에 보이는 글만 답의 text 로 낸다(--out 과 같이 주지 않는다)")
    sub = command("begin", cmd_begin, "적용 시작")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--plan", required=True, help="steps 가 든 plan-<k>.json 또는 rollback-<k>.json")
    sub.add_argument("--snapshot", required=True, help="적용 직전에 같은 부과금을 읽은 값(read-calls --record N 으로 읽는다, 15분 안)")
    sub = command("calls", cmd_calls, "남은 저장 → applyCharge 부를 값")
    sub.add_argument("--change", type=int, required=True)
    sub = command("record-result", cmd_record_result, "applyCharge 답 하나를 장부에")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--result", required=True, help="stayCharge.applyCharge 답 JSON")
    sub = command("check", cmd_check, "멈춘 변경을 방금 읽은 값으로 보기")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--snapshot", required=True, help="방금 같은 부과금을 읽은 값(read-calls --record N 으로 읽는다)")
    sub = command("verify", cmd_verify, "적용 뒤 견주기")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--snapshot", required=True)
    sub = command("rollback", cmd_rollback, "되돌리기 계산")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--snapshot", required=True, help="지금 읽은 값(read-calls --record <그 번호> 로 읽는다)")
    sub.add_argument("--include-kept", action="store_true", help="그 사이 달라진 칸도 되돌린다")
    sub.add_argument("--charge", action="append", help="이 부과금 번호만 (여러 번)")
    sub.add_argument("--record", action="store_true", help="장부에 되돌리기 미리보기로 적는다")
    sub.add_argument("--replaces", type=int, help="이 계산이 바꾸는 앞 되돌리기 미리보기(같은 변경을 되돌리는 것)의 장부 번호")
    sub.add_argument("--sentence", default="되돌리기", help="담당자가 한 말")
    sub = command("list", cmd_list, "장부 목록")
    sub.add_argument("--look", help="look 명령이 낸 파일 — 탭에 열린 호텔의 기록만 싣는다")
    sub.add_argument("--all", action="store_true", help="다른 호텔의 기록도 싣는다(탭의 호텔이 먼저)")
    return top


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.command == "render":
        needed = {"preview": "plan", "rollback": "plan", "prices": "look", "result": "change"}[args.kind]
        if getattr(args, needed) is None:
            parser().error(f"render {args.kind} 에는 --{needed} 가 필요합니다")
    try:
        result = args.handler(args)
    except (ModelError, LedgerError, BrowserError, ValueError, KeyError, TypeError) as error:
        message = str(error) if not isinstance(error, (KeyError, TypeError)) else f"입력 JSON 에 필요한 칸이 없습니다: {error}"
        payload = dict(error=message)
        if getattr(error, "refetch", None):
            payload["refetch"] = error.refetch
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 2
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out and args.command != "render":
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        if args.command in SHORT:
            text = json.dumps(dict(out=str(Path(args.out).resolve()), **SHORT[args.command](result)), ensure_ascii=False, indent=2)
    print(text)
    return 1 if result.get("same") is False else 0


if __name__ == "__main__":
    sys.exit(main())
