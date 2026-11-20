#!/usr/bin/env python3
"""price_change.py — 가격 변경 도우미의 명령. JSON 파일을 받고 JSON 을 돌려준다(브라우저 쪽이 이 명령을 부른다).

    look          stayPrice.look() 의 답과 그 조각(take 답들) → 호텔 · 오퍼 · 객실 × 요금제(답이 길 때)
    read          ERP 화면 조각(HTML) 또는 브라우저 답(readPair · readReserved 와 그 조각의 take 답들) → 지금 값(snapshot.json)
    read-calls    요청 → 브라우저에 부를 값: readPair 목록과 readReserved 첫 물음
    reserved      readReserved 물음과 답 → 남은 물음(숨긴 줄이 있던 물음은 좁혀서). 다 끝나면 done
    plan          지금 값 + 요청(+ 빨간 줄 고름) → 미리보기 계산과 저장 단계(plan.json). --record 면 장부에 적는다
    render        preview | result | rollback | prices 페이지(HTML) 만들기
    begin         적용 시작 — 저장 단계를 장부에 적는다
    record-step   저장 한 번이 끝날 때마다 — 됨(--saved) 또는 멈춤(--failed)
    calls         장부의 변경에서 아직 저장되지 않은 단계 → 브라우저에 부를 값(applyBulk · applyCell)
    record-result 브라우저 답(applyBulk · applyCell JSON) 하나 → 그 단계를 장부에 됨·멈춤으로 적는다
    verify        적용 뒤 다시 읽은 값과 견주기
    stale         미리보기 때 값과 방금 읽은 값 견주기 — 다르면 종료 코드 1
    rollback      장부의 변경 하나(또는 객실·요금제·날짜·인원으로 고른 일부)를 되돌리는 계산. --record 면 장부에 적는다
    restore       지금 상태 저장으로 적어 둔 상태로 되돌리는 계산(rollback.json 과 같은 모양). --record 면 변경으로 적는다
    save-snapshot 지금 값을 장부에만 적어 두기
    list          장부에 적힌 변경 목록

결과는 표준 출력에 JSON 으로 쓰고, `--out` 을 주면 그 파일에도 쓴다. 종료 코드: 0 됨 · 1 다른 값이 있음(stale·verify) ·
2 입력이나 순서가 맞지 않음(표준 오류에 {"error": "…"}). 장부 자리는 `STAY_PRICE_LEDGER_DIR` 로 바꿀 수 있다.

예:
    python3 price_change.py read --hotel "데모 호텔" --price-page "디럭스=p1.html" --adjust-page a.html --out snapshot.json
    python3 price_change.py plan --snapshot snapshot.json --request request.json --record --out plan.json
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
    BrowserError, attach_bodies, pair_reads, read_calls, reserved_probes, reserved_round, step_call, step_outcome,
)
from price_model import (
    decode_plan, decode_request, decode_resolution_items, decode_snapshot, decode_step, encode_change, encode_plan,
    TargetTable, encode_request, encode_snapshot, encode_step, snapshot_reading,
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


def cmd_read(args):
    pages = [price_page_arg(text) for text in args.price_page or ()]
    pages += pair_reads(load_results(args.pair_result))
    adjusts = [parse_adjust_page(Path(path).read_text(encoding="utf-8")) for path in args.adjust_page or ()]
    if args.reserved_probes:
        done = reserved_round(load(args.reserved_probes), load_results(args.reserved_result))
        if not done.done:
            raise BrowserError(f"예약 있는 날 물음이 {len(done.ask)}개 남았습니다 — reserved 명령으로 남은 물음을 보세요")
        adjusts += done.pages
    return encode_snapshot(build_snapshot(args.hotel, args.read_at or now_text(), pages, adjusts))


def request_scope(request) -> tuple[str, list[tuple[str, str]], list[str]]:
    if isinstance(request, TargetTable):
        keys = [target.key for target in request.targets]
        return request.offer, [(key.room, key.rate_plan) for key in keys], [key.date for key in keys]
    pairs = list(request.pairs) or [(room, plan) for room in request.rooms for plan in request.rate_plans]
    return request.offer, pairs, list(request.dates)


def cmd_read_calls(args):
    offer, pairs, dates = request_scope(decode_request(load(args.request)))
    return dict(pairs=read_calls(offer, pairs, dates), reserved=reserved_probes(offer, pairs, dates))


def cmd_reserved(args):
    done = reserved_round(load(args.probes), load_results(args.result))
    return dict(done=done.done, ask=done.ask, answered=len(done.pages), failed=done.failed)


def cmd_plan(args):
    snapshot, request = decode_snapshot(load(args.snapshot)), decode_request(load(args.request))
    plan = plan_targets(snapshot, request) if isinstance(request, TargetTable) else plan_change(snapshot, request)
    resolutions = [Resolution(str(item["rule"]), str(item["choice"]), decode_resolution_items(item.get("cells")))
                   for item in load(args.resolutions)] if args.resolutions else []
    writes, unresolved = resolve(plan, resolutions)
    steps = save_steps(writes) if not unresolved else None
    change_id = Ledger().record_preview(hotel=request.hotel, offer=request.offer, currency=plan.currency,
                                        sentence=request.sentence, read_at=plan.read_at, rows=preview_rows(plan),
                                        request=encode_request(plan.request)) if args.record else None
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


def cmd_record_step(args):
    return dict(change_id=args.change, step=args.step,
                status=Ledger().record_step(args.change, args.step, args.saved, args.note))


def cmd_calls(args):
    record = Ledger().change(args.change)
    if not record.steps:
        raise LedgerError(f"{args.change}번 변경은 아직 적용을 시작하지 않았습니다(begin)")
    return dict(change_id=record.id, status=record.status,
                calls=[step_call(step.index, record.offer, step.kind, step.body) for step in record.steps if step.status != "saved"])


def cmd_record_result(args):
    result = load(args.result)
    ledger = Ledger()
    record = ledger.change(args.change)
    step = next((step for step in record.steps if step.index == result.get("no")), None)
    if step is None:
        raise LedgerError(f"{args.change}번 변경에 {result.get('no')}번째 저장이 없습니다")
    outcome = step_outcome(step_call(step.index, record.offer, step.kind, step.body), result)
    if not outcome.started:
        return dict(change_id=record.id, step=step.index, started=False, wait=outcome.wait, note=outcome.note,
                    status=record.status)
    return dict(change_id=record.id, step=step.index, started=True, saved=outcome.saved is True, note=outcome.note,
                status=ledger.record_step(record.id, step.index, outcome.saved is True, outcome.note,
                                          unknown=outcome.saved == "unknown"))


def cmd_verify(args):
    mismatches = Ledger().verify(args.change, snapshot_reading(decode_snapshot(load(args.snapshot))))
    return dict(change_id=args.change, same=not mismatches, mismatches=[
        dict(key=key_fields(item.item_key), label=item.label, field=item.field, after=money_text(item.after),
             seen=money_text(item.seen), seen_state=item.seen_state) for item in mismatches])


def cmd_stale(args):
    differences = stale_cells(decode_snapshot(load(args.before)), decode_snapshot(load(args.after)))
    return dict(same=not differences, differences=[
        dict(key=key_fields(item.key), then=encode_state(item.then), now=encode_state(item.now)) for item in differences])


def cmd_rollback(args):
    ledger = Ledger()
    snapshot = decode_snapshot(load(args.snapshot))
    select, scope = cell_filter(args.room or (), args.rate_plan or (), args.date_from, args.date_to, args.occupancy or ())
    plan = plan_cell_rollback(ledger.recorded_change(args.change), ledger.later_writes(args.change), snapshot,
                              args.include_kept, select)
    change_id = ledger.record_preview(hotel=plan.hotel, offer=plan.offer, currency=plan.currency, sentence=args.sentence,
                                      read_at=plan.read_at, rows=rollback_rows(plan),
                                      reverses=args.change) if args.record else None
    return dict(change_id=change_id, scope=scope, rollback=encode_rollback(plan),
                steps=[encode_step(step) for step in save_steps(rollback_writes(plan))],
                reserved=[dict(room=room, date=day) for room, day in sorted(snapshot.reserved)])


def cmd_restore(args):
    ledger = Ledger()
    snapshot = decode_snapshot(load(args.snapshot))
    select, scope = cell_filter(args.room or (), args.rate_plan or (), args.date_from, args.date_to, args.occupancy or ())
    plan = plan_cell_restore(ledger.recorded_snapshot(args.saved), snapshot, select)
    change_id = ledger.record_preview(
        hotel=plan.hotel, offer=plan.offer, currency=plan.currency, sentence=args.sentence, read_at=plan.read_at,
        rows=rollback_rows(plan),
        request=dict(kind="restore_snapshot", snapshot=args.saved, scope=scope)) if args.record else None
    return dict(change_id=change_id, scope=scope, rollback=encode_rollback(plan),
                steps=[encode_step(step) for step in save_steps(rollback_writes(plan))],
                reserved=[dict(room=room, date=day) for room, day in sorted(snapshot.reserved)])


def cmd_save_snapshot(args):
    snapshot = decode_snapshot(load(args.snapshot))
    return dict(change_id=Ledger().record_snapshot(hotel=snapshot.hotel, offer=snapshot.offer, currency=snapshot.currency,
                                                   sentence=args.sentence, read_at=snapshot.read_at,
                                                   rows=snapshot_rows(snapshot)))


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

    sub = command("read", cmd_read, "ERP 화면 조각 → 지금 값")
    sub.add_argument("--hotel", required=True)
    sub.add_argument("--price-page", action="append", help="'캘린더의 객실 이름=[선택 날짜 가격 수정] 확인 단계 HTML' (여러 번)")
    sub.add_argument("--pair-result", action="append", help="stayPrice.readPair 답과 그 조각의 take 답들 JSON — 목록 (여러 번)")
    sub.add_argument("--adjust-page", action="append", help="[선택 날짜 가격 가감] 확인 단계 HTML (여러 번)")
    sub.add_argument("--reserved-probes", help="read-calls 가 낸 readReserved 첫 물음(reserved 목록) JSON")
    sub.add_argument("--reserved-result", action="append", help="stayPrice.readReserved 답과 take 답들 JSON — 목록 (여러 번)")
    sub.add_argument("--read-at", help="읽은 시각(ISO). 없으면 지금")

    sub = command("read-calls", cmd_read_calls, "요청 → readPair · readReserved 부를 값")
    sub.add_argument("--request", required=True)

    sub = command("reserved", cmd_reserved, "readReserved 물음과 답 → 남은 물음")
    sub.add_argument("--probes", required=True, help="read-calls 가 낸 reserved 목록 JSON")
    sub.add_argument("--result", action="append", help="stayPrice.readReserved 답과 take 답들 JSON — 목록 (여러 번)")

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

    sub = command("record-step", cmd_record_step, "저장 한 번의 결과")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--step", type=int, required=True, help="1부터 센 저장 번호")
    done = sub.add_mutually_exclusive_group(required=True)
    done.add_argument("--saved", action="store_true", dest="saved")
    done.add_argument("--failed", action="store_false", dest="saved")
    sub.add_argument("--note", help="멈춘 까닭 등")

    sub = command("calls", cmd_calls, "아직 저장되지 않은 단계 → applyBulk · applyCell 부를 값")
    sub.add_argument("--change", type=int, required=True)

    sub = command("record-result", cmd_record_result, "브라우저 답 하나를 장부에 적기")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--result", required=True, help="stayPrice.applyBulk · applyCell 답 JSON")

    sub = command("verify", cmd_verify, "적용 뒤 다시 읽은 값과 견주기")
    sub.add_argument("--change", type=int, required=True)
    sub.add_argument("--snapshot", required=True)

    sub = command("stale", cmd_stale, "미리보기 때 값과 방금 읽은 값 견주기")
    sub.add_argument("--before", required=True)
    sub.add_argument("--after", required=True)

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
