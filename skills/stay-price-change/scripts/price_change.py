#!/usr/bin/env python3
"""price_change.py — 가격 변경 도우미의 명령. JSON 파일을 받고 JSON 을 돌려준다(브라우저 쪽이 이 명령을 부른다).

    look          stayPrice.look() 의 답과 그 조각(take 답들) → 호텔 · 오퍼 · 객실 × 요금제(답이 길 때)
    read-calls    읽을 범위(요청 파일, 또는 장부 번호) → 브라우저에 부를 값: readPair 목록과 readReserved 첫 물음(calls.json)
    reserved      calls.json + readReserved 답들 → 남은 물음(숨긴 줄이 있던 물음은 좁혀서). 다 끝나면 done
    read          calls.json + 브라우저 답들(readPair · readReserved 와 그 조각의 take 답, 폴더째) → 지금 값(snapshot.json).
                  시험용으로 ERP 화면 조각(HTML) 파일도 받는다
    plan          지금 값 + 요청(+ 빨간 줄 고름) → 미리보기 계산과 저장 단계(plan.json). --record 면 장부에 적는다
    render        preview | result | rollback | prices 페이지(HTML) 만들기
    begin         적용 시작 — 저장 단계를 장부에 적는다
    calls         장부의 변경에서 아직 저장되지 않은 단계 → 브라우저에 부를 값(applyBulk · applyCell). 멈춘 변경은 check 가
                  이어서 해도 된다고 한 뒤에만 낸다
    check         장부 번호 + 방금 읽은 값 → 저장마다 됨 · 안 됨 · 섞임 · 그 사이 바뀜, 남은 저장을 계획대로 해도 되는지와 까닭.
                  「모름」인 저장은 읽은 값으로 가려 장부에 적는다
    record-result 브라우저 답(applyBulk · applyCell JSON) 하나 → 그 단계를 장부에 됨·멈춤으로 적는다
    verify        적용 뒤 다시 읽은 값과 견주기
    stale         장부 번호의 계산이 바탕으로 삼은 읽은 값과 방금 읽은 값 견주기 — 다르면 종료 코드 1
    rollback      장부의 변경 하나(또는 객실·요금제·날짜·인원으로 고른 일부)를 되돌리는 계산. --record 면 장부에 적는다
    restore       지금 상태 저장으로 적어 둔 상태로 되돌리는 계산(rollback.json 과 같은 모양). --record 면 변경으로 적는다
    save-snapshot 지금 값을 장부에만 적어 두기
    list          장부에 적힌 변경 목록

결과는 표준 출력에 JSON 으로 쓰고, `--out` 을 주면 그 파일에도 쓴다. 종료 코드: 0 됨 · 1 다른 값이 있음(stale·verify) ·
2 입력이나 순서가 맞지 않음(표준 오류에 {"error": "…"}). 장부 자리는 `STAY_PRICE_LEDGER_DIR` 로 바꿀 수 있다.

장부 번호마다(미리보기 · 지금 상태 저장 · 되돌리기) 그 계산이 바탕으로 삼은 읽은 값을 적어 둔다. 그래서 같은 범위를 다시 읽을 때는
`read-calls --record N`, 적용 직전 낡음 확인은 `stale --change N` 처럼 번호만 준다.

예:
    python3 price_change.py read-calls --request range.json --out R/calls.json
    python3 price_change.py read --calls R/calls.json --answers R --out R/snapshot.json
    python3 price_change.py plan --snapshot R/snapshot.json --request request.json --record --out plan.json
    python3 price_change.py render preview --plan plan.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from change_core.items import encode_state, key_fields
from change_core.ledger import Ledger, LedgerError, ledger_dir, now_text
from change_core.money import money_text
from change_core.rollback import decode_rollback, encode_rollback
from change_core.rules import Resolution
from erp_read import PairRead, ParseError, build_snapshot, parse_adjust_page, parse_price_page
from price_browser import (
    BrowserError, answers_for, attach_bodies, page_hotel, pair_reads, read_calls, reserved_probes, reserved_round, step_call,
    step_outcome, unanswered,
)
from price_model import (
    ReadRange, TargetTable, decode_plan, decode_request, decode_resolution_items, decode_snapshot, decode_step, encode_change,
    encode_hotel, encode_plan, encode_request, encode_snapshot, encode_step, hotel_label, request_range, same_hotel,
    snapshot_reading,
)
from price_pages import render_prices, render_preview, render_result, render_rollback
from price_plan import (
    PlanError, cell_filter, counts, plan_cell_restore, plan_cell_rollback, plan_change, plan_targets, preview_rows, resolve, rollback_rows, rollback_writes, save_steps,
    snapshot_rows, stale_cells, step_plans,
)

PAGE_NAMES = {"preview": "미리보기", "result": "적용 결과", "rollback": "되돌리기 미리보기", "prices": "지금 가격"}


def load(path: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"파일이 없습니다: {path}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON 을 읽지 못했습니다: {path} ({error})") from None


def page_path(hotel: str, kind: str) -> Path:
    safe = re.sub(r'[\\/:*?"<>|]', "_", hotel).strip() or "호텔"
    base = f"{datetime.now().strftime('%Y-%m-%d %H시%M분')} · {safe} · {PAGE_NAMES[kind]}"
    path, number = ledger_dir() / f"{base}.html", 2
    while path.exists():
        path, number = ledger_dir() / f"{base} ({number}).html", number + 1
    return path


ANSWER_PREFIXES = ("look-", "pair-", "resv-", "take-")
EARLIER_HELP = ("같은 일의 앞선 읽기 폴더 (여러 번) — 그 안의 다 받은 조각만 빌린다. 이번 읽기의 답으로 치지 않는다. "
                "알아볼 값(글자 수 · 바이트 수 · CRC-32 · FNV-1a)이 같은 조각은 다시 받지 않아도 된다")


def answer_files(paths) -> list[Path]:
    """답 파일 목록 — 파일은 그대로, 폴더는 그 안에서 이름이 look-·pair-·resv-·take- 로 시작하는 .json·.txt 파일(이름순)."""
    files = []
    for path in map(Path, paths or ()):
        if path.is_dir():
            files += sorted(item for item in path.iterdir() if item.is_file() and item.name.startswith(ANSWER_PREFIXES)
                            and item.suffix in (".json", ".txt"))
        else:
            files.append(path)
    return files


def load_results(paths) -> list:
    """브라우저 답 파일들(폴더도 된다 — answer_files) — 파일 하나에 답 하나(객체) 또는 여럿(목록). 목록의 글자 항목, 그리고
    JSON 이 아닌 파일은 도구가 보인 그대로의 답이다(잘린 답일 수 있다 — price_browser.answers 가 알아본다)."""
    results = []
    for path in answer_files(paths):
        try:
            text = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ValueError(f"파일이 없습니다: {path}") from None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = text
        results += data if isinstance(data, list) else [data]
    return results


def price_page_arg(text: str) -> PairRead:
    """`--price-page 캘린더의 객실 이름=파일` — 화면 조각에는 드로어의 객실 이름만 있어 칩의 이름을 따로 받는다."""
    room, sep, path = text.partition("=")
    if not sep or not room.strip() or not path:
        raise ValueError(f"--price-page 는 '캘린더의 객실 이름=파일' 로 적습니다: {text}")
    return PairRead.of(room.strip(), parse_price_page(Path(path).read_text(encoding="utf-8")))


def cmd_look(args):
    looks = [result for result in attach_bodies(load_results(args.answers)) if result.get("op") == "look"]
    if len(looks) != 1:
        raise BrowserError(f"stayPrice.look() 의 답이 하나여야 합니다(받은 것 {len(looks)}개)")
    look = looks[0]
    if not look.get("ok"):
        raise BrowserError(f"stayPrice.look() 이 실패했습니다: {look.get('error')}")
    return {name: look.get(name) for name in ("login", "hotel", "offer", "offers", "pairs")}


def load_calls(path: str) -> dict:
    calls = load(path)
    if not isinstance(calls, dict) or not isinstance(calls.get("pairs"), list) or not isinstance(calls.get("reserved"), list):
        raise ValueError(f"read-calls 가 낸 파일(pairs · reserved)이 아닙니다: {path}")
    return calls


def cmd_read(args):
    if args.calls or args.answers:
        if not (args.calls and args.answers):
            raise ValueError("브라우저 답으로 읽을 때는 --calls(read-calls 가 낸 파일)와 --answers(답 파일·폴더)를 함께 줍니다")
        if args.hotel or args.hotel_id or args.price_page or args.adjust_page:
            raise ValueError("브라우저 답으로 읽을 때 호텔은 페이지가 알아본 것을 씁니다 — --hotel · --hotel-id · 화면 조각 파일을 같이 주지 않습니다")
        calls, results = load_calls(args.calls), load_results(args.answers)
        missing = unanswered(calls["pairs"], results, "readPair")
        if missing:
            raise BrowserError(f"readPair 답이 없는 부를 값이 {len(missing)}개 있습니다 — 처음 것: {missing[0]['room']} · "
                               f"{missing[0]['ratePlan']} · {missing[0]['from']} ~ {missing[0]['to']}. 그 값으로 readPair 를 부릅니다")
        results = attach_bodies(results, load_results(args.earlier))
        pair_answers, reserved_answers = answers_for(results, "readPair"), answers_for(results, "readReserved")
        done = reserved_round(calls["reserved"], reserved_answers)
        if not done.done:
            raise BrowserError(f"예약 있는 날 물음이 {len(done.ask)}개 남았습니다 — reserved 명령으로 남은 물음을 보세요")
        hotel = page_hotel(pair_answers + reserved_answers)
        pages, adjusts = pair_reads(pair_answers), done.pages
    else:
        if not (args.hotel and args.hotel_id):
            raise ValueError("화면 조각 파일로 읽을 때는 --hotel 과 --hotel-id 를 함께 줍니다")
        hotel = {"id": args.hotel_id, "name": args.hotel}
        pages = [price_page_arg(text) for text in args.price_page or ()]
        adjusts = [parse_adjust_page(Path(path).read_text(encoding="utf-8")) for path in args.adjust_page or ()]
    return encode_snapshot(build_snapshot(hotel["name"], args.read_at or now_text(), pages, adjusts, hotel["id"]))


def recorded_reading(ledger: Ledger, change_id: int):
    """장부 번호의 계산이 바탕으로 삼은 읽은 값(Snapshot) — 읽은 범위와 그때 값이 들어 있다."""
    return decode_snapshot(ledger.reading(change_id))


def cmd_read_calls(args):
    scope: ReadRange = recorded_reading(Ledger(), args.record).range if args.record else request_range(load(args.request))
    hotel = encode_hotel(scope.hotel, scope.hotel_id)
    return dict(pairs=read_calls(hotel, scope.offer, scope.pairs, scope.dates),
                reserved=reserved_probes(hotel, scope.offer, scope.pairs, scope.dates))


def cmd_reserved(args):
    asked = answers_for(load_results(args.answers), "readReserved")
    done = reserved_round(load_calls(args.calls)["reserved"], attach_bodies(asked, load_results(args.earlier)))
    return dict(done=done.done, ask=done.ask, answered=len(done.pages), failed=done.failed)


def cmd_plan(args):
    snapshot, request = decode_snapshot(load(args.snapshot)), decode_request(load(args.request))
    plan = plan_targets(snapshot, request) if isinstance(request, TargetTable) else plan_change(snapshot, request)
    resolutions = [Resolution(str(item["rule"]), str(item["choice"]), decode_resolution_items(item.get("cells")))
                   for item in load(args.resolutions)] if args.resolutions else []
    writes, unresolved = resolve(plan, resolutions)
    steps = save_steps(writes) if not unresolved else None
    change_id = Ledger().record_preview(hotel=snapshot.hotel, hotel_id=snapshot.hotel_id, offer=request.offer,
                                        currency=plan.currency,
                                        sentence=request.sentence, read_at=plan.read_at, rows=preview_rows(plan),
                                        request=encode_request(plan.request),
                                        reading=encode_snapshot(snapshot)) if args.record else None
    return dict(change_id=change_id, counts=counts(plan.changes, len(plan.skipped)), plan=encode_plan(plan),
                unresolved=[encode_change(change) for change in unresolved],
                steps=None if steps is None else [encode_step(step) for step in steps])


def cmd_render(args):
    if args.kind == "preview":
        data = load(args.plan)
        plan = decode_plan(data["plan"])
        html = render_preview(plan, data.get("change_id"), [decode_step(step) for step in data.get("steps") or ()])
        hotel = plan.request.hotel
    elif args.kind == "rollback":
        data = load(args.plan)
        plan = decode_rollback(data["rollback"])
        html = render_rollback(plan, [(item["room"], item["date"]) for item in data.get("reserved") or ()],
                               data.get("scope") or "")
        hotel = plan.hotel
    elif args.kind == "prices":
        snapshot = decode_snapshot(load(args.snapshot))
        html, hotel = render_prices(snapshot), snapshot.hotel
    else:
        ledger = Ledger()
        record = ledger.change(args.change)
        html, hotel = render_result(record, str(ledger.path)), record.hotel
    path = Path(args.out) if args.out else page_path(hotel, args.kind)
    path.write_text(html, encoding="utf-8")
    return dict(page=str(path.resolve()))


def cmd_begin(args):
    data = load(args.plan)
    if not data.get("steps"):
        raise PlanError("저장 단계가 없습니다. 빨간 줄 칸을 먼저 골라 주세요")
    ledger = Ledger()
    ledger.begin(args.change, step_plans(decode_step(step) for step in data["steps"]),
                 data["plan"]["request"] if "plan" in data else None)
    record = ledger.change(args.change)
    return dict(change_id=record.id, status=record.status, steps=len(record.steps))


def record_hotel(record) -> dict:
    """장부가 적어 둔 호텔 — 페이지가 알아본 번호 · 이름. 부를 값마다 실려 다른 호텔의 탭에서는 페이지가 누르지 않는다."""
    return encode_hotel(record.hotel, record.hotel_id)


def cmd_calls(args):
    record = Ledger().change(args.change)
    if not record.steps:
        raise LedgerError(f"{args.change}번 변경은 아직 적용을 시작하지 않았습니다(begin)")
    if record.status == "stopped":
        raise LedgerError(f"{args.change}번 변경은 멈춰 있습니다 — 같은 범위를 다시 읽고(read-calls --record {args.change}) "
                          f"check 가 이어서 해도 된다고 하면 calls 를 다시 부릅니다")
    return dict(change_id=record.id, status=record.status,
                calls=[step_call(step.index, record_hotel(record), record.offer, step.kind, step.body)
                       for step in record.steps if step.status != "saved"])


def cmd_record_result(args):
    result = load(args.result)
    ledger = Ledger()
    record = ledger.change(args.change)
    step = next((step for step in record.steps if step.index == result.get("no")), None)
    if step is None:
        raise LedgerError(f"{args.change}번 변경에 {result.get('no')}번째 저장이 없습니다")
    outcome = step_outcome(step_call(step.index, record_hotel(record), record.offer, step.kind, step.body), result)
    if not outcome.started:
        return dict(change_id=record.id, step=step.index, started=False, wait=outcome.wait, note=outcome.note,
                    status=record.status)
    return dict(change_id=record.id, step=step.index, started=True, saved=outcome.saved is True, note=outcome.note,
                status=ledger.record_step(record.id, step.index, outcome.saved is True, outcome.note,
                                          unknown=outcome.saved == "unknown"))


def cmd_check(args):
    ledger = Ledger()
    record, now = ledger.change(args.change), decode_snapshot(load(args.snapshot))
    if not same_hotel(record.hotel, record.hotel_id, now.hotel, now.hotel_id) or record.offer != now.offer:
        raise PlanError(f"방금 읽은 값은 {hotel_label(now.hotel, now.hotel_id)} · {now.offer} 것이고, {args.change}번은 "
                        f"{hotel_label(record.hotel, record.hotel_id)} · {record.offer} 입니다")
    report = ledger.check(args.change, snapshot_reading(now), snapshot_reading(recorded_reading(ledger, args.change)))
    return dict(change_id=report.change_id, status=report.status, remaining=list(report.remaining),
                can_continue=report.can_continue, why=list(report.why),
                steps=[dict(no=step.index, label=step.label, ledger=step.ledger, seen=step.seen, settled=step.settled,
                            moved=step.moved) for step in report.steps])


def cmd_verify(args):
    mismatches = Ledger().verify(args.change, snapshot_reading(decode_snapshot(load(args.snapshot))))
    return dict(change_id=args.change, same=not mismatches, mismatches=[
        dict(key=key_fields(item.item_key), label=item.label, field=item.field, after=money_text(item.after),
             seen=money_text(item.seen), seen_state=item.seen_state) for item in mismatches])


def cmd_stale(args):
    then, now = recorded_reading(Ledger(), args.change), decode_snapshot(load(args.snapshot))
    if not same_hotel(then.hotel, then.hotel_id, now.hotel, now.hotel_id) or then.offer != now.offer:
        raise PlanError(f"방금 읽은 값은 {hotel_label(now.hotel, now.hotel_id)} · {now.offer} 것이고, {args.change}번은 "
                        f"{hotel_label(then.hotel, then.hotel_id)} · {then.offer} 입니다")
    differences = stale_cells(then, now)
    return dict(same=not differences, differences=[
        dict(key=key_fields(item.key), then=encode_state(item.then), now=encode_state(item.now)) for item in differences])


def cmd_rollback(args):
    ledger = Ledger()
    snapshot = decode_snapshot(load(args.snapshot))
    select, scope = cell_filter(args.room or (), args.rate_plan or (), args.date_from, args.date_to, args.occupancy or ())
    plan = plan_cell_rollback(ledger.recorded_change(args.change), ledger.later_writes(args.change), snapshot,
                              args.include_kept, select)
    change_id = ledger.record_preview(hotel=plan.hotel, hotel_id=plan.hotel_id, offer=plan.offer, currency=plan.currency,
                                      sentence=args.sentence, read_at=plan.read_at, rows=rollback_rows(plan),
                                      reverses=args.change, reading=encode_snapshot(snapshot)) if args.record else None
    return dict(change_id=change_id, scope=scope, rollback=encode_rollback(plan),
                steps=[encode_step(step) for step in save_steps(rollback_writes(plan))],
                reserved=[dict(room=room, date=day) for room, day in sorted(snapshot.reserved)])


def cmd_restore(args):
    ledger = Ledger()
    snapshot = decode_snapshot(load(args.snapshot))
    select, scope = cell_filter(args.room or (), args.rate_plan or (), args.date_from, args.date_to, args.occupancy or ())
    plan = plan_cell_restore(ledger.recorded_snapshot(args.saved), snapshot, select)
    change_id = ledger.record_preview(
        hotel=plan.hotel, hotel_id=plan.hotel_id, offer=plan.offer, currency=plan.currency, sentence=args.sentence,
        read_at=plan.read_at, rows=rollback_rows(plan), reading=encode_snapshot(snapshot),
        request=dict(kind="restore_snapshot", snapshot=args.saved, scope=scope)) if args.record else None
    return dict(change_id=change_id, scope=scope, rollback=encode_rollback(plan),
                steps=[encode_step(step) for step in save_steps(rollback_writes(plan))],
                reserved=[dict(room=room, date=day) for room, day in sorted(snapshot.reserved)])


def cmd_save_snapshot(args):
    snapshot = decode_snapshot(load(args.snapshot))
    return dict(change_id=Ledger().record_snapshot(hotel=snapshot.hotel, hotel_id=snapshot.hotel_id, offer=snapshot.offer,
                                                   currency=snapshot.currency,
                                                   sentence=args.sentence, read_at=snapshot.read_at,
                                                   rows=snapshot_rows(snapshot), reading=encode_snapshot(snapshot)))


def cmd_list(args):
    ledger = Ledger()
    return dict(ledger=str(ledger.path), changes=ledger.list_changes())


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="price_change.py", description=__doc__.split("\n\n")[0],
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = root.add_subparsers(dest="command", required=True)

    def command(name, handler, help_text):
        sub = commands.add_parser(name, help=help_text)
        sub.set_defaults(handler=handler)
        sub.add_argument("--out", help="결과(JSON, render 는 HTML)를 쓸 파일")
        return sub

    sub = command("look", cmd_look, "stayPrice.look() 의 답(과 그 조각) → 호텔 · 오퍼 · 객실 × 요금제")
    sub.add_argument("--answers", action="append", required=True, help="look 답과 take 답 파일, 또는 그것이 든 폴더 (여러 번)")

    sub = command("read-calls", cmd_read_calls, "읽을 범위 → readPair · readReserved 부를 값")
    scope = sub.add_mutually_exclusive_group(required=True)
    scope.add_argument("--request", help="요청 파일 — 읽을 범위(kind range) · 바꾸기 요청 · 목표 값 표")
    scope.add_argument("--record", type=int, help="장부 번호 — 그 번호의 계산이 바탕으로 삼은 범위를 다시 읽는다")

    sub = command("reserved", cmd_reserved, "readReserved 물음과 답 → 남은 물음")
    sub.add_argument("--calls", required=True, help="read-calls 가 낸 파일")
    sub.add_argument("--answers", action="append", help="readReserved 답과 take 답 파일, 또는 그것이 든 폴더 (여러 번)")
    sub.add_argument("--earlier", action="append", help=EARLIER_HELP)

    sub = command("read", cmd_read, "브라우저 답 → 지금 값")
    sub.add_argument("--calls", help="read-calls 가 낸 파일")
    sub.add_argument("--answers", action="append", help="readPair · readReserved 답과 take 답 파일, 또는 그것이 든 폴더 (여러 번)")
    sub.add_argument("--earlier", action="append", help=EARLIER_HELP)
    sub.add_argument("--read-at", help="읽은 시각(ISO). 없으면 지금")
    sub.add_argument("--hotel", help="시험용: 화면 조각 파일로 읽을 때의 호텔 이름 — 브라우저 답은 페이지가 알아본 호텔을 쓴다")
    sub.add_argument("--hotel-id", help="시험용: 화면 조각 파일로 읽을 때의 호텔 번호")
    sub.add_argument("--price-page", action="append", help="시험용: '캘린더의 객실 이름=[선택 날짜 가격 수정] 확인 단계 HTML' (여러 번)")
    sub.add_argument("--adjust-page", action="append", help="시험용: [선택 날짜 가격 가감] 확인 단계 HTML (여러 번)")

    sub = command("plan", cmd_plan, "미리보기 계산")
    sub.add_argument("--snapshot", required=True)
    sub.add_argument("--request", required=True, help="요청 JSON — 바꾸는 방법(kind change) 또는 목표 값 표(kind targets)")
    sub.add_argument("--resolutions", help='빨간 줄 고름 JSON 목록 — [{"rule": "ABOVE_LIST", "choice": "raise_list"}]')
    sub.add_argument("--record", action="store_true", help="장부에 미리보기로 적는다")

    sub = command("render", cmd_render, "페이지 만들기")
    sub.add_argument("kind", choices=sorted(PAGE_NAMES))
    sub.add_argument("--plan", help="preview 는 plan.json, rollback 은 rollback.json")
    sub.add_argument("--snapshot", help="prices 의 지금 값")
    sub.add_argument("--change", type=int, help="result 의 장부 번호")

    sub = command("begin", cmd_begin, "적용 시작")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--plan", required=True, help="steps 가 든 plan.json 또는 rollback.json")

    sub = command("calls", cmd_calls, "아직 저장되지 않은 단계 → applyBulk · applyCell 부를 값")
    sub.add_argument("--change", type=int, required=True)

    sub = command("record-result", cmd_record_result, "브라우저 답 하나를 장부에 적기")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--result", required=True, help="stayPrice.applyBulk · applyCell 답 JSON")

    sub = command("check", cmd_check, "변경에 무슨 일이 있었는지 — 저장마다, 그리고 남은 저장을 해도 되는지")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--snapshot", required=True, help="방금 같은 범위로 읽은 값(read-calls --record N 으로 읽는다)")

    sub = command("verify", cmd_verify, "적용 뒤 다시 읽은 값과 견주기")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--snapshot", required=True)

    sub = command("stale", cmd_stale, "장부 번호의 읽은 값과 방금 읽은 값 견주기")
    sub.add_argument("--change", type=int, required=True, help="미리보기 · 되돌리기의 장부 번호")
    sub.add_argument("--snapshot", required=True, help="방금 같은 범위로 읽은 값")

    sub = command("rollback", cmd_rollback, "되돌리기 계산")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--snapshot", required=True, help="지금 읽은 값")
    sub.add_argument("--include-kept", action="store_true", help="그 사이 달라진 칸도 되돌린다")
    sub.add_argument("--room", action="append", help="이 객실의 칸만 (여러 번)")
    sub.add_argument("--rate-plan", action="append", help="이 요금제의 칸만 (여러 번)")
    sub.add_argument("--from", dest="date_from", help="이 날짜부터(ISO)")
    sub.add_argument("--to", dest="date_to", help="이 날짜까지(ISO)")
    sub.add_argument("--occupancy", action="append", help="이 인원 조합 키의 칸만 (여러 번, 인원 무관은 빈 글자)")
    sub.add_argument("--record", action="store_true", help="장부에 되돌리기 미리보기로 적는다")
    sub.add_argument("--sentence", default="되돌리기", help="담당자가 한 말")

    sub = command("restore", cmd_restore, "저장해 둔 상태로 되돌리는 계산")
    sub.add_argument("--saved", type=int, required=True, help="지금 상태 저장(save-snapshot)으로 적은 장부 번호")
    sub.add_argument("--snapshot", required=True, help="지금 읽은 값")
    sub.add_argument("--record", action="store_true", help="장부에 변경 미리보기로 적는다(적용하면 이것도 되돌릴 수 있다)")
    sub.add_argument("--sentence", default="저장해 둔 상태로 되돌리기", help="담당자가 한 말")
    sub.add_argument("--room", action="append", help="이 객실의 칸만 (여러 번)")
    sub.add_argument("--rate-plan", action="append", help="이 요금제의 칸만 (여러 번)")
    sub.add_argument("--from", dest="date_from", help="이 날짜부터(ISO)")
    sub.add_argument("--to", dest="date_to", help="이 날짜까지(ISO)")
    sub.add_argument("--occupancy", action="append", help="이 인원 조합 키의 칸만 (여러 번)")

    sub = command("save-snapshot", cmd_save_snapshot, "지금 값을 장부에만 적기")
    sub.add_argument("--snapshot", required=True)
    sub.add_argument("--sentence", default="지금 상태 저장")

    command("list", cmd_list, "장부 목록")
    return root


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.command == "render":
        needed = {"preview": "plan", "rollback": "plan", "prices": "snapshot", "result": "change"}[args.kind]
        if getattr(args, needed) is None:
            parser().error(f"render {args.kind} 에는 --{needed} 가 필요합니다")
    try:
        result = args.handler(args)
    except (ParseError, PlanError, LedgerError, BrowserError, ValueError, KeyError, TypeError) as error:
        message = str(error) if not isinstance(error, (KeyError, TypeError)) else f"입력 JSON 에 필요한 칸이 없습니다: {error}"
        payload = dict(error=message)
        if getattr(error, "refetch", None):
            payload["refetch"] = error.refetch
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 2
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out and args.command != "render":
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if result.get("same") is False else 0


if __name__ == "__main__":
    sys.exit(main())
