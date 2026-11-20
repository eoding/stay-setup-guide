#!/usr/bin/env python3
"""price_change.py — 가격 변경 도우미의 명령. JSON 파일을 받고 JSON 을 돌려준다(브라우저 쪽이 이 명령을 부른다).

    look          stayPrice.look() 의 답과 그 조각(take 답들) → 호텔 · 오퍼 · 객실 × 요금제(답이 길 때)
    read-calls    읽을 범위(요청 파일, 또는 장부 번호) → 브라우저에 부를 값: readPair 목록과 readReserved 첫 물음(calls.json)
    reserved      calls.json + readReserved 답들 → 남은 물음(숨긴 줄이 있던 물음은 좁혀서). 다 끝나면 done
    read          calls.json + 브라우저 답들(readPair · readReserved 와 그 조각의 take 답, 폴더째) → 지금 값(snapshot.json).
                  읽은 시각(read_at)은 그 작업들이 끝난 시각 가운데 가장 이른 것이다. 시험용으로 ERP 화면 조각(HTML) 파일도 받는다
                  reserved · read 는 기록 폴더의 앞선 읽기 폴더(같은 호텔)에서 다 받은 같은 조각을 스스로 찾아 빌린다
    sheet         요금표 파일(kind sheet) + look 의 답 → 셈한 값 · 호텔에 없는 / 요금표에 없는 객실 · 요금제 · 읽을 범위와
                  페이지 작업 수(sheet-check.json). read-calls · plan · render sheet 가 이 파일을 받는다
    plan          지금 값 + 요청(+ 빨간 줄 고름) → 미리보기 계산과 저장 단계(plan-1.json). --record 면 장부에 적는다.
                  다시 계산하면 새 파일(plan-2.json)에 쓰고 --replaces 로 앞 번호를 댄다(있는 파일은 덮어쓰지 않는다).
                  요청이 sheet-check.json 이면 요금표를 칸마다 펼쳐 계산하고 넣지 않는 것(coverage)을 단다
    render        preview | result | rollback | prices | sheet 페이지(HTML) 만들기
    begin         적용 시작 — 적용 직전에 읽은 값을 그 번호의 계산이 바탕으로 삼은 읽은 값과 견주어, 한 칸이라도 다르면
                  아무것도 시작하지 않고 다른 칸을 댄다(종료 1). 같으면 저장 단계를 장부에 적는다
    calls         장부의 변경에서 아직 저장되지 않은 단계 → 브라우저에 부를 값(applyBulk · applyCell). 멈춘 변경(저장이 실패했거나
                  15분 동안 아무 일이 없던)은 다시 읽어 check 가 이어서 해도 된다고 한 뒤에만 낸다
    check         장부 번호 + 방금 읽은 값 → 저장마다 됨 · 안 됨 · 섞임 · 그 사이 바뀜, 남은 저장을 계획대로 해도 되는지와 까닭,
                  어디까지 됐고 왜 멈췄는지. 「모름」인 저장은 읽은 값으로 가려 장부에 적는다
    record-result 브라우저 답(applyBulk · applyCell JSON) 하나 → 그 단계를 장부에 됨·멈춤으로 적는다
    verify        적용 뒤 다시 읽은 값과 견주기
    stale         장부 번호의 계산이 바탕으로 삼은 읽은 값과 방금 읽은 값 견주기 — 다르면 종료 코드 1
    rollback      장부의 변경 하나(또는 객실·요금제·날짜·인원으로 고른 일부)를 되돌리는 계산. --record 면 장부에 적는다.
                  다시 계산하면 새 파일(rollback-2.json)에 쓰고 --replaces 로 앞 번호를 댄다(plan 과 같다)
    restore       지금 상태 저장으로 적어 둔 상태로 되돌리는 계산(rollback 과 같은 모양 · 같은 두 규칙). --record 면 변경으로 적는다
    save-snapshot 지금 값을 장부에만 적어 두기
    list          장부에 적힌 변경 목록

결과는 표준 출력에 JSON 으로 쓰고, `--out` 을 주면 그 파일에도 쓴다. 파일에 쓰는 명령 여섯(read-calls · read · sheet · plan ·
rollback · restore)은 `--out` 을 주면 표준 출력에는 짧은 답만 낸다 — 다음에 무엇을 할지 정하는 데 필요한 번호 · 수 · 빨간 줄 · 파일
자리이고, 칸 목록은 싣지 않는다(SHORT). 종료 코드: 0 됨 · 1 다른 값이 있음(stale·verify) ·
2 입력이나 순서가 맞지 않음(표준 오류에 {"error": "…"}). 장부 자리는 `STAY_PRICE_LEDGER_DIR` 로 바꿀 수 있다.

장부 번호마다(미리보기 · 지금 상태 저장 · 되돌리기) 그 계산이 바탕으로 삼은 읽은 값을 적어 둔다. 그래서 같은 범위를 다시 읽을 때는
`read-calls --record N`, 적용 직전 확인은 `begin --change N --snapshot <방금 읽은 값>` 처럼 번호만 준다.

예:
    python3 price_change.py read-calls --request range.json --out R/calls.json
    python3 price_change.py read --calls R/calls.json --answers R --out R/snapshot.json
    python3 price_change.py plan --snapshot R/snapshot.json --request request.json --record --out plan-1.json
    python3 price_change.py render preview --plan plan-1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from change_core import files
from change_core.answers import BrowserError, answers_for, attach_bodies, step_outcome, unanswered
from change_core.chrome import page_text
from change_core.files import load, page_path
from change_core.items import encode_state, key_fields
from change_core.ledger import Ledger, LedgerError, now_text
from change_core.money import money_text
from change_core.rollback import decode_rollback, encode_rollback
from change_core.rules import Resolution
from erp_read import PairRead, ParseError, build_snapshot, parse_adjust_page, parse_price_page
from price_browser import (
    page_hotel, pair_reads, read_calls, reading_size, reading_time, reserved_probes, reserved_round, step_call, too_big,
)
from change_core.rules import BLOCKED
from price_model import (
    CELL_RULES, ITEM_KIND, ReadRange, TargetTable, decode_hotel, decode_plan, decode_request, decode_resolution_items, decode_snapshot, decode_step,
    encode_change, encode_hotel, encode_key, encode_plan, encode_request, encode_snapshot, encode_step, hotel_label, iso_day,
    key_of_item, line_label, request_range, same_hotel, snapshot_reading,
)
from price_pages import (
    EXAMPLES, cells_scope, chosen_lines, record_scope, record_what, red_lines, render_prices, render_preview, render_result,
    render_rollback, render_sheet, result_name,
)
from price_sheet import Part, SheetCheck, coverage_counts, decode_check, decode_sheet, encode_check, plan_sheet
from price_plan import (
    PlanError, cell_filter, counts, plan_cell_restore, plan_cell_rollback, plan_change, plan_steps, plan_targets, preview_rows,
    resolve, rollback_rows, rollback_writes, save_steps, snapshot_rows, stale_cells, step_plans, unresolved,
)

def open_ledger() -> Ledger:
    """가격 칸의 장부 — 목록에는 가격 칸 번호만 나오고, 다른 도우미(부가옵션 가격 …)의 번호는 거절한다."""
    return Ledger(kind=ITEM_KIND)


PAGE_NAMES = {"preview": "미리보기", "result": "적용 결과", "rollback": "되돌리기 미리보기", "prices": "지금 가격",
              "sheet": "요금표 읽은 것"}   # result 는 되돌리기의 결과면 「되돌리기 결과」(price_pages.result_name)


ANSWER_PREFIXES = ("look-", "pair-", "resv-", "take-")


def load_results(paths) -> list:
    return files.load_results(paths, ANSWER_PREFIXES)


def lent_answers(args, calls: dict) -> list:
    """이번 읽기에 조각을 빌려 줄 답들 — 기록 폴더에서 같은 호텔을 읽은 앞선 읽기 폴더마다의 답 파일."""
    return files.lent_answers(args.calls, args.answers, calls, ANSWER_PREFIXES)


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
        if args.hotel or args.hotel_id or args.price_page or args.adjust_page or args.read_at:
            raise ValueError("브라우저 답으로 읽을 때 호텔은 페이지가 알아본 것을, 읽은 시각은 답의 끝난 시각을 씁니다 — --hotel · "
                             "--hotel-id · --read-at · 화면 조각 파일을 같이 주지 않습니다")
        calls, results = load_calls(args.calls), load_results(args.answers)
        missing = unanswered(calls["pairs"], results, "readPair")
        if missing:
            raise BrowserError(f"readPair 답이 없는 부를 값이 {len(missing)}개 있습니다 — 처음 것: {missing[0]['room']} · "
                               f"{missing[0]['ratePlan']} · {missing[0]['from']} ~ {missing[0]['to']}. 그 값으로 readPair 를 부릅니다"
                               " (불렀는데 답이 끊겼거나 잘렸으면 stayPrice.last() 의 답을 새 파일로 저장해도 됩니다)")
        read_at = reading_time(results)
        results = attach_bodies(results, lent_answers(args, calls))
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
        read_at = args.read_at or now_text()
    return encode_snapshot(build_snapshot(hotel["name"], read_at, pages, adjusts, hotel["id"]))


def recorded_reading(ledger: Ledger, change_id: int):
    """장부 번호의 계산이 바탕으로 삼은 읽은 값(Snapshot) — 읽은 범위와 그때 값이 들어 있다."""
    return decode_snapshot(ledger.reading(change_id))


def request_scope(data: dict) -> ReadRange:
    """요청 파일의 읽을 범위 — sheet 가 낸 파일이면 요금표의 범위(읽기 한 번에 들지 않으면 거절), 아니면 request_range."""
    return decode_check(data).fitting_range() if data.get("kind") == "sheet_check" else request_range(data)


def cmd_read_calls(args):
    """페이지가 조각을 다 두지 못하는 읽기는 아무것도 부르기 전에 거절한다 — 받으려 할 때는 앞 조각이 이미 밀려나 있다."""
    scope: ReadRange = recorded_reading(open_ledger(), args.record).range if args.record else request_scope(load(args.request))
    hotel = encode_hotel(scope.hotel, scope.hotel_id)
    calls = dict(pairs=read_calls(hotel, scope.offer, scope.pairs, scope.dates),
                 reserved=reserved_probes(hotel, scope.offer, scope.pairs, scope.dates))
    size = reading_size(calls)
    if not size["fits"]:
        raise PlanError(f"이 범위는 읽기 한 번에 들지 않습니다 — {too_big(size)}. 객실 · 요금제나 날짜로 나눠 범위 파일을 둘 이상 쓰고 "
                        "하나씩 읽습니다")
    return calls


def cmd_reserved(args):
    calls = load_calls(args.calls)
    asked = answers_for(load_results(args.answers), "readReserved")
    done = reserved_round(calls["reserved"], attach_bodies(asked, lent_answers(args, calls)))
    return dict(done=done.done, ask=done.ask, answered=len(done.pages), failed=done.failed)


def cmd_sheet(args):
    """요금표를 읽기 전에 확인한다 — `--look` 은 look 명령의 답(짧으면 stayPrice.look() 의 답 파일 그대로도 된다)."""
    look = load(args.look)
    if not isinstance(look, dict) or not isinstance(look.get("hotel"), dict) or not isinstance(look.get("pairs"), list):
        raise ValueError("--look 은 hotel · offer · pairs 가 든 look 의 답입니다 — 목록이 길어 body 로 왔으면 look --answers 로 먼저 묶습니다")
    sheet = decode_sheet(load(args.sheet))
    name, hotel_id = decode_hotel(look["hotel"])
    if not same_hotel(sheet.hotel, sheet.hotel_id, name, hotel_id) or look.get("offer") != sheet.offer:
        raise PlanError(f"요금표 파일은 {hotel_label(sheet.hotel, sheet.hotel_id)} · {sheet.offer} 인데 look 의 답은 "
                        f"{hotel_label(name, hotel_id)} · {look.get('offer')} 입니다 — stayPrice.look({{offer}}) 로 그 오퍼를 봅니다")
    part = Part(tuple(args.room or ()), iso_day(args.date_from) if args.date_from else None,
                iso_day(args.date_to) if args.date_to else None)
    return encode_check(SheetCheck(sheet, tuple((str(item["room"]), str(item["rate_plan"])) for item in look["pairs"]), part))


def fresh_record(args, name: str) -> None:
    files.fresh_record(args.out, args.replaces, args.record, name)


def cmd_plan(args):
    fresh_record(args, "plan")
    snapshot, data = decode_snapshot(load(args.snapshot)), load(args.request)
    if data.get("kind") == "sheet_check":
        plan = plan_sheet(snapshot, decode_check(data))
    else:
        request = decode_request(data)
        plan = plan_targets(snapshot, request) if isinstance(request, TargetTable) else plan_change(snapshot, request)
    request = plan.request
    resolutions = [Resolution(str(item["rule"]), str(item["choice"]), decode_resolution_items(item.get("cells")))
                   for item in load(args.resolutions)] if args.resolutions else []
    plan = resolve(plan, resolutions)
    steps = plan_steps(plan)
    change_id = open_ledger().record_preview(hotel=snapshot.hotel, hotel_id=snapshot.hotel_id, offer=request.offer,
                                        currency=plan.currency,
                                        sentence=request.sentence, read_at=plan.read_at, rows=preview_rows(plan),
                                        request=encode_request(plan.request), reading=encode_snapshot(snapshot),
                                        replaces=args.replaces) if args.record else None
    result = dict(change_id=change_id, replaces=args.replaces, counts=counts(plan.changes, len(plan.skipped)), plan=encode_plan(plan),
                  red=red_lines(plan), chosen=chosen_lines(plan), above_one_night_before=plan.above_one_night_before,
                  unresolved=[encode_change(change) for change in unresolved(plan)],
                  steps=None if steps is None else [encode_step(step) for step in steps])
    if isinstance(request, TargetTable) and request.from_sheet:
        result["coverage"] = coverage_counts(plan.coverage)
    return result


def cmd_render(args):
    name = PAGE_NAMES[args.kind]
    if args.kind == "preview":
        data = load(args.plan)
        plan = decode_plan(data["plan"])
        html = render_preview(plan, data.get("change_id"), [decode_step(step) for step in data.get("steps") or ()], args.by_date)
        hotel = plan.request.hotel
    elif args.kind == "rollback":
        data = load(args.plan)
        plan = decode_rollback(data["rollback"])
        html = render_rollback(plan, [(item["room"], item["date"]) for item in data.get("reserved") or ()],
                               data.get("scope") or "", args.by_date, data.get("undone") or ())
        hotel = plan.hotel
    elif args.kind == "prices":
        snapshot = decode_snapshot(load(args.snapshot))
        html, hotel = render_prices(snapshot, args.by_date), snapshot.hotel
    elif args.kind == "sheet":
        check = decode_check(load(args.plan))
        html, hotel = render_sheet(check), check.sheet.hotel
    else:
        ledger = open_ledger()
        record = ledger.change(args.change)
        html, hotel, name = render_result(record, str(ledger.path), args.by_date), record.hotel, result_name(record)
    path = Path(args.out) if args.out else page_path(hotel, name)
    path.write_text(html, encoding="utf-8")
    return dict(page=str(path.resolve()), **({"text": page_text(html)} if args.text else {}))


def reading_since(ledger: Ledger, change_id: int, now):
    """그 번호의 계산이 바탕으로 삼은 읽은 값 — 방금 읽은 값(`now`)이 다른 호텔·오퍼면 거절."""
    then = recorded_reading(ledger, change_id)
    if not same_hotel(then.hotel, then.hotel_id, now.hotel, now.hotel_id) or then.offer != now.offer:
        raise PlanError(f"방금 읽은 값은 {hotel_label(now.hotel, now.hotel_id)} · {now.offer} 것이고, {change_id}번은 "
                        f"{hotel_label(then.hotel, then.hotel_id)} · {then.offer} 입니다")
    return then


def encode_differences(differences) -> list[dict]:
    return [dict(key=key_fields(item.key), then=encode_state(item.then), now=encode_state(item.now)) for item in differences]


def differences_since(ledger: Ledger, change_id: int, now) -> list[dict]:
    """그 번호의 계산이 바탕으로 삼은 읽은 값과 방금 읽은 값(`now`)이 다른 칸 — 한쪽에만 있는 칸도. 다른 호텔·오퍼면 거절."""
    return encode_differences(stale_cells(reading_since(ledger, change_id, now), now))


def cmd_begin(args):
    """적용 직전에 읽은 값(`--snapshot`)이 미리보기 때 값과 한 칸이라도 다르면 아무것도 시작하지 않는다(종료 1, stale 과 같은 답)."""
    data = load(args.plan)
    if data.get("steps") is None:
        raise PlanError("저장 단계가 없습니다. 빨간 줄 칸을 먼저 골라 주세요")
    if not data["steps"]:
        raise PlanError(f"{args.change}번 미리보기는 바꿀 칸이 없어 적용할 것이 없습니다 — 아무것도 시작하지 않았습니다")
    ledger, now = open_ledger(), decode_snapshot(load(args.snapshot))
    then = reading_since(ledger, args.change, now) if ledger.change(args.change).status == "previewed" else now
    differences = ledger.begin_fresh(args.change, step_plans(decode_step(step) for step in data["steps"]), snapshot_reading(then),
                                     snapshot_reading(now), read_at=now.read_at,
                                     request=data["plan"]["request"] if "plan" in data else None)
    if differences:
        return dict(change_id=args.change, status="previewed", same=False, differences=encode_differences(differences))
    record = ledger.change(args.change)
    return dict(change_id=record.id, status=record.status, steps=len(record.steps))


def record_hotel(record) -> dict:
    """장부가 적어 둔 호텔 — 페이지가 알아본 번호 · 이름. 부를 값마다 실려 다른 호텔의 탭에서는 페이지가 누르지 않는다."""
    return encode_hotel(record.hotel, record.hotel_id)


def cmd_calls(args):
    record = open_ledger().change(args.change)
    if not record.steps:
        raise LedgerError(f"{args.change}번 변경은 아직 적용을 시작하지 않았습니다(begin)")
    if record.status == "stopped":
        raise LedgerError(f"{args.change}번 변경은 멈춰 있습니다(저장이 실패했거나 15분 동안 아무 일이 없었습니다) — 같은 범위를 "
                          f"다시 읽고(read-calls --record {args.change}) check 가 이어서 해도 된다고 하면 calls 를 다시 부릅니다")
    return dict(change_id=record.id, status=record.status,
                calls=[step_call(step.index, record_hotel(record), record.offer, step.kind, step.body)
                       for step in record.steps if step.status != "saved"])


def cmd_record_result(args):
    result = load(args.result)
    ledger = open_ledger()
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
    ledger = open_ledger()
    record, now = ledger.change(args.change), decode_snapshot(load(args.snapshot))
    if not same_hotel(record.hotel, record.hotel_id, now.hotel, now.hotel_id) or record.offer != now.offer:
        raise PlanError(f"방금 읽은 값은 {hotel_label(now.hotel, now.hotel_id)} · {now.offer} 것이고, {args.change}번은 "
                        f"{hotel_label(record.hotel, record.hotel_id)} · {record.offer} 입니다")
    report = ledger.check(args.change, snapshot_reading(now), snapshot_reading(recorded_reading(ledger, args.change)), now.read_at)
    step_ref = (lambda step: None if step is None else dict(no=step.index, label=step.label))
    return dict(change_id=report.change_id, scope=listed(ledger, args.change)[0]["scope"], status=report.status, cause=report.cause,
                note=report.note,
                last_saved=step_ref(report.last_saved), next=step_ref(report.next), remaining=list(report.remaining),
                can_continue=report.can_continue, why=list(report.why),
                steps=[dict(no=step.index, label=step.label, ledger=step.ledger, seen=step.seen, settled=step.settled,
                            moved=step.moved) for step in report.steps])


def cmd_verify(args):
    mismatches = open_ledger().verify(args.change, snapshot_reading(decode_snapshot(load(args.snapshot))))
    return dict(change_id=args.change, same=not mismatches, mismatches=[
        dict(key=key_fields(item.item_key), label=item.label, field=item.field, after=money_text(item.after),
             seen=money_text(item.seen), seen_state=item.seen_state) for item in mismatches])


def cmd_stale(args):
    differences = differences_since(open_ledger(), args.change, decode_snapshot(load(args.snapshot)))
    return dict(same=not differences, differences=differences)


def rollback_answer(change_id, args, scope, plan, snapshot, undone=()) -> dict:
    return dict(change_id=change_id, replaces=args.replaces, scope=scope, rollback=encode_rollback(plan),
                steps=[encode_step(step) for step in save_steps(rollback_writes(plan))],
                reserved=[dict(room=room, date=day) for room, day in sorted(snapshot.reserved)], undone=list(undone))


def undone_before(ledger: Ledger, change_id: int) -> list[dict]:
    """이 변경에서 이미 되돌린 부분 — 되돌린 번호마다 요청 문장 · 시각 · 칸 수 · 범위(cells_scope). 「나머지 되돌리기」 미리보기가 말한다."""
    return [dict(change_id=entry["change_id"], sentence=entry["sentence"], applied_at=entry["applied_at"],
                 cells=len(entry["items"]), scope=cells_scope(key_of_item(key) for kind, key in entry["items"] if kind == ITEM_KIND))
            for entry in ledger.undone(change_id)]


def rollback_scope(ledger: Ledger, change_id: int | None, kind: str, request: dict | None, reverses: int | None, plan) -> str:
    """되돌리기 계산이 덮는 범위 한 줄 — 장부에 적었으면 `list` 의 그 번호 줄, 아니면 같은 셈(되돌리는 칸 · 한 일 · 고른 칸)."""
    if change_id is not None:
        return listed(ledger, change_id)[0]["scope"]
    keys = {key_of_item(row.item_key) for row in rollback_rows(plan)}
    return " · ".join((cells_scope(keys), record_what(kind, request, reverses, plan.currency)))


def cmd_rollback(args):
    fresh_record(args, "rollback")
    ledger = open_ledger()
    snapshot = decode_snapshot(load(args.snapshot))
    select, picked = cell_filter(args.room or (), args.rate_plan or (), args.date_from, args.date_to, args.occupancy or ())
    plan = plan_cell_rollback(ledger.recorded_change(args.change), ledger.later_writes(args.change), snapshot,
                              args.include_kept, select)
    undone = undone_before(ledger, args.change)
    request = dict(kind="rollback", scope=picked) if picked else None   # 고른 칸 — 장부 목록의 범위 한 줄이 말한다
    change_id = ledger.record_preview(hotel=plan.hotel, hotel_id=plan.hotel_id, offer=plan.offer, currency=plan.currency,
                                      sentence=args.sentence, read_at=plan.read_at, rows=rollback_rows(plan),
                                      reverses=args.change, reading=encode_snapshot(snapshot), request=request,
                                      replaces=args.replaces) if args.record else None
    scope = rollback_scope(ledger, change_id, "rollback", request, args.change, plan)
    return rollback_answer(change_id, args, scope, plan, snapshot, undone)


def cmd_restore(args):
    fresh_record(args, "rollback")
    ledger = open_ledger()
    snapshot = decode_snapshot(load(args.snapshot))
    select, picked = cell_filter(args.room or (), args.rate_plan or (), args.date_from, args.date_to, args.occupancy or ())
    plan = plan_cell_restore(ledger.recorded_snapshot(args.saved), snapshot, select)
    request = dict(kind="restore_snapshot", snapshot=args.saved, scope=picked)
    change_id = ledger.record_preview(
        hotel=plan.hotel, hotel_id=plan.hotel_id, offer=plan.offer, currency=plan.currency, sentence=args.sentence,
        read_at=plan.read_at, rows=rollback_rows(plan), reading=encode_snapshot(snapshot),
        request=request, replaces=args.replaces) if args.record else None
    return rollback_answer(change_id, args, rollback_scope(ledger, change_id, "change", request, None, plan), plan, snapshot)


def cmd_save_snapshot(args):
    snapshot = decode_snapshot(load(args.snapshot))
    return dict(change_id=open_ledger().record_snapshot(hotel=snapshot.hotel, hotel_id=snapshot.hotel_id, offer=snapshot.offer,
                                                   currency=snapshot.currency,
                                                   sentence=args.sentence, read_at=snapshot.read_at,
                                                   rows=snapshot_rows(snapshot), reading=encode_snapshot(snapshot)))


def listed(ledger: Ledger, change_id: int | None = None) -> list[dict]:
    """장부 목록의 줄마다(`change_id` 를 주면 그 번호만) 범위 한 줄(`scope`)을 단다 — 장부가 가진 칸에서 객실 · 요금제, 날짜 구간,
    한 일(알면 "판매가 +12%" 처럼), 멈췄으면 어디까지 갔는지, 되돌렸으면 몇 칸을. 요청 원문은 싣지 않는다."""
    keys = ledger.item_keys(ITEM_KIND, change_id)
    out = []
    for entry in ledger.list_changes(change_id):
        entry["scope"] = record_scope(entry, map(key_of_item, keys.get(entry["id"], ())))
        del entry["request"]
        out.append(entry)
    return out


def cmd_list(args):
    ledger = open_ledger()
    return dict(ledger=str(ledger.path), changes=listed(ledger))


def short_read_calls(result: dict) -> dict:
    """readPair 를 부를 값은 도우미가 그대로 넣어야 하므로 싣는다. 예약 있는 날 물음은 reserved 명령이 파일에서 읽는다."""
    return dict(pairs=result["pairs"], reads=reading_size(result))


def short_read(result: dict) -> dict:
    cells = result["cells"]
    dates = result["dates"]
    return dict(hotel=result["hotel"], offer=result["offer"], currency=result["currency"], read_at=result["read_at"],
                cells=len(cells), priced=sum(cell["state"] != "missing" for cell in cells),
                closed=sum(cell["state"] == "closed" for cell in cells), missing=sum(cell["state"] == "missing" for cell in cells),
                reserved=len(result["reserved"]), no_sale=len(result["no_sale"]), pairs=len(result["pairs"]),
                dates=dict(first=dates[0] if dates else None, last=dates[-1] if dates else None, count=len(dates)))


def short_sheet(result: dict) -> dict:
    scope = result["range"]
    return dict(hotel=result["sheet"]["hotel"], offer=result["sheet"]["offer"], currency=result["currency"],
                lines=result["lines"], cells=result["cells"], part=result["part"], gaps=result["gaps"],
                range=None if scope is None else dict(pairs=len(scope["pairs"]), first=scope["first"], last=scope["last"],
                                                     days=scope["days"]),
                reads=result["reads"])


def short_plan(result: dict) -> dict:
    """미리보기를 말하고 고를 것을 묻는 데 필요한 것 — 수, 저장 횟수(`saves`, 빨간 줄이 남았으면 null), 고를 빨간 줄과 고른 것의 말,
    적용할 수 없는 칸의 까닭. 칸마다의 값은 계산 파일과 미리보기 페이지에 있다."""
    plan = decode_plan(result["plan"])
    blocked = [dict(rule=rule.code, label=rule.label, cells=result["counts"][rule.code],
                    examples=[encode_key(change.key) for change in plan.changes if change.verdict == rule.code][:EXAMPLES])
               for rule in CELL_RULES.rules if rule.severity == BLOCKED and result["counts"][rule.code]]
    short = dict(change_id=result["change_id"], replaces=result["replaces"], counts=result["counts"],
                 saves=None if result["steps"] is None else len(result["steps"]), red=result["red"], chosen=result["chosen"],
                 blocked=blocked, above_one_night_before=result["above_one_night_before"])
    if isinstance(plan.request, TargetTable):   # 표에 인원 · 박수가 없던 목표는 명령이 고른 줄 — 담당자에게 어느 줄인지 말한다
        short["lines"] = list(dict.fromkeys(line_label(target.key.occupancy, target.key.nights) for target in plan.request.targets))
    if "coverage" in result:
        short["coverage"] = result["coverage"]
    return short


def short_rollback(result: dict) -> dict:
    """되돌리기를 말하는 데 필요한 것 — 적어 둔 시각, 되돌리는 · 그대로 두는 · 지울 수 없는 칸 수, 그대로 두는 까닭마다의 수,
    저장 횟수, 되돌리는 칸 가운데 예약 있는 날의 칸 수."""
    plan, reserved = decode_rollback(result["rollback"]), {(item["room"], item["date"]) for item in result["reserved"]}
    causes: dict[tuple, int] = {}
    for item in plan.kept:
        cause = (item.cause.change_id, item.cause.at, item.cause.sentence)
        causes[cause] = causes.get(cause, 0) + 1
    restored = [key_of_item(item.key) for item in plan.restored]
    return dict(change_id=result["change_id"], replaces=result["replaces"], scope=result["scope"], mode=plan.mode,
                restore_to=plan.restore_to, restored=len(restored), kept=len(plan.kept), unremovable=len(plan.unremovable),
                kept_why=[dict(change_id=change_id, at=at, sentence=sentence, outside=change_id is None, cells=count)
                          for (change_id, at, sentence), count in causes.items()],
                saves=len(result["steps"]), reserved=sum((key.room, key.date) in reserved for key in restored),
                undone=result["undone"])


SHORT = {"read-calls": short_read_calls, "read": short_read, "sheet": short_sheet, "plan": short_plan,
         "rollback": short_rollback, "restore": short_rollback}


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
    scope.add_argument("--request", help="요청 파일 — 읽을 범위(kind range) · 바꾸기 요청 · 목표 값 표 · sheet 가 낸 파일")
    scope.add_argument("--record", type=int, help="장부 번호 — 그 번호의 계산이 바탕으로 삼은 범위를 다시 읽는다")

    sub = command("reserved", cmd_reserved, "readReserved 물음과 답 → 남은 물음")
    sub.add_argument("--calls", required=True, help="read-calls 가 낸 파일")
    sub.add_argument("--answers", action="append", help="readReserved 답과 take 답 파일, 또는 그것이 든 폴더 (여러 번)")

    sub = command("read", cmd_read, "브라우저 답 → 지금 값")
    sub.add_argument("--calls", help="read-calls 가 낸 파일")
    sub.add_argument("--answers", action="append", help="readPair · readReserved 답과 take 답 파일, 또는 그것이 든 폴더 (여러 번)")
    sub.add_argument("--read-at", help="시험용: 화면 조각 파일로 읽을 때의 읽은 시각(ISO), 없으면 지금 — 브라우저 답은 작업들의 끝난 "
                     "시각(doneAt) 가운데 가장 이른 것이 읽은 시각이다")
    sub.add_argument("--hotel", help="시험용: 화면 조각 파일로 읽을 때의 호텔 이름 — 브라우저 답은 페이지가 알아본 호텔을 쓴다")
    sub.add_argument("--hotel-id", help="시험용: 화면 조각 파일로 읽을 때의 호텔 번호")
    sub.add_argument("--price-page", action="append", help="시험용: '캘린더의 객실 이름=[선택 날짜 가격 수정] 확인 단계 HTML' (여러 번)")
    sub.add_argument("--adjust-page", action="append", help="시험용: [선택 날짜 가격 가감] 확인 단계 HTML (여러 번)")

    sub = command("sheet", cmd_sheet, "요금표 확인 — 셈한 값 · 호텔에 없는 / 요금표에 없는 객실 · 요금제 · 읽을 범위")
    sub.add_argument("--sheet", required=True, help="요금표 파일(kind sheet) — 도우미가 요금표에서 숫자만 옮겨 적은 것")
    sub.add_argument("--look", required=True, help="look 의 답(hotel · offer · pairs) — 호텔의 객실 · 요금제")
    sub.add_argument("--room", action="append", help="이 객실의 줄만 (여러 번) — 요금표를 객실마다 나눠 할 때")
    sub.add_argument("--from", dest="date_from", help="이 날짜부터(ISO) — 요금표를 시즌(날짜 창)마다 나눠 할 때")
    sub.add_argument("--to", dest="date_to", help="이 날짜까지(ISO)")

    sub = command("plan", cmd_plan, "미리보기 계산")
    sub.add_argument("--snapshot", required=True)
    sub.add_argument("--request", required=True,
                     help="요청 JSON — 바꾸는 방법(kind change) · 목표 값 표(kind targets) · sheet 가 낸 파일(kind sheet_check)")
    sub.add_argument("--resolutions", help='빨간 줄 고름 JSON 목록 — [{"rule": "ABOVE_LIST", "choice": "raise_list"}]')
    sub.add_argument("--record", action="store_true", help="장부에 미리보기로 적는다")
    sub.add_argument("--replaces", type=int, help="이 계산이 바꾸는 앞 미리보기의 장부 번호(빨간 줄을 고른 뒤 · 적용 직전에 값이 "
                     "달라 다시 계산할 때). 그 번호는 replaced 가 되고 begin 이 받지 않는다")

    sub = command("render", cmd_render, "페이지 만들기")
    sub.add_argument("kind", choices=sorted(PAGE_NAMES))
    sub.add_argument("--plan", help="preview 는 plan-<k>.json, rollback 은 rollback-<k>.json, sheet 는 sheet 가 낸 파일")
    sub.add_argument("--snapshot", help="prices 의 지금 값")
    sub.add_argument("--change", type=int, help="result 의 장부 번호")
    sub.add_argument("--by-date", action="store_true",
                     help="날짜마다 열 하나 — 기본은 8일 넘는 표에서 칸이 모두 같은 날끼리 열 하나(\"날짜별로 펼쳐 줘\")")
    sub.add_argument("--text", action="store_true",
                     help="답에 페이지에 보이는 글(text)도 싣는다 — 도우미는 자기 페이지를 브라우저 도구로 열지 못하니, 페이지의 글을 "
                          "그대로 옮겨야 할 때 이것으로 읽는다")

    sub = command("begin", cmd_begin, "적용 시작 — 적용 직전에 읽은 값이 미리보기 때와 같을 때만")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--plan", required=True, help="steps 가 든 plan-<k>.json 또는 rollback-<k>.json")
    sub.add_argument("--snapshot", required=True, help="적용 직전에 같은 범위로 읽은 값(read-calls --record N 으로 읽는다, 15분 안)")

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
    sub.add_argument("--replaces", type=int, help="이 계산이 바꾸는 앞 되돌리기 미리보기(같은 변경을 되돌리는 것)의 장부 번호"
                     "(--include-kept 로 · 적용 직전에 값이 달라 다시 계산할 때). 그 번호는 replaced 가 되고 begin 이 받지 않는다")
    sub.add_argument("--sentence", default="되돌리기", help="담당자가 한 말")

    sub = command("restore", cmd_restore, "저장해 둔 상태로 되돌리는 계산")
    sub.add_argument("--saved", type=int, required=True, help="지금 상태 저장(save-snapshot)으로 적은 장부 번호")
    sub.add_argument("--snapshot", required=True, help="지금 읽은 값")
    sub.add_argument("--record", action="store_true", help="장부에 변경 미리보기로 적는다(적용하면 이것도 되돌릴 수 있다)")
    sub.add_argument("--replaces", type=int, help="이 계산이 바꾸는 앞 미리보기(같은 저장 상태로 되돌리는 것)의 장부 번호"
                     "(적용 직전에 값이 달라 다시 계산할 때). 그 번호는 replaced 가 되고 begin 이 받지 않는다")
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
        needed = {"preview": "plan", "rollback": "plan", "prices": "snapshot", "result": "change", "sheet": "plan"}[args.kind]
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
        if args.command in SHORT:
            text = json.dumps(dict(out=str(Path(args.out).resolve()), **SHORT[args.command](result)), ensure_ascii=False, indent=2)
    print(text)
    return 1 if result.get("same") is False else 0


if __name__ == "__main__":
    sys.exit(main())
