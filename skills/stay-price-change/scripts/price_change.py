#!/usr/bin/env python3
"""price_change.py — 가격 변경 도우미의 명령. JSON 파일을 받고 JSON 을 돌려준다(브라우저 쪽이 이 명령을 부른다).

    read          ERP 화면 조각(HTML) → 지금 값(snapshot.json)
    plan          지금 값 + 요청(+ 빨간 줄 고름) → 미리보기 계산과 저장 단계(plan.json). --record 면 장부에 적는다
    render        preview | result | rollback | prices 페이지(HTML) 만들기
    begin         적용 시작 — 저장 단계를 장부에 적는다
    record-step   저장 한 번이 끝날 때마다 — 됨(--saved) 또는 멈춤(--failed)
    verify        적용 뒤 다시 읽은 값과 견주기
    stale         미리보기 때 값과 방금 읽은 값 견주기 — 다르면 종료 코드 1
    rollback      장부의 변경 하나를 되돌리는 계산(rollback.json). --record 면 장부에 적는다
    save-snapshot 지금 값을 장부에만 적어 두기
    list          장부에 적힌 변경 목록

결과는 표준 출력에 JSON 으로 쓰고, `--out` 을 주면 그 파일에도 쓴다. 종료 코드: 0 됨 · 1 다른 칸이 있음(stale·verify) ·
2 입력이나 순서가 맞지 않음(표준 오류에 {"error": "…"}). 장부 자리는 `STAY_PRICE_LEDGER_DIR` 로 바꿀 수 있다.

예:
    python3 price_change.py read --hotel "데모 호텔" --price-page p1.html --adjust-page a.html --out snapshot.json
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

from erp_read import ParseError, build_snapshot, parse_adjust_page, parse_price_page
from price_ledger import Ledger, LedgerError, ledger_dir, now_text
from price_model import (
    decode_plan, decode_request, decode_resolution, decode_rollback, decode_snapshot, decode_step, encode_change,
    encode_key, encode_plan, encode_rollback, encode_snapshot, encode_step, encode_value, money_text,
)
from price_pages import render_prices, render_preview, render_result, render_rollback
from price_plan import PlanError, counts, plan_change, plan_rollback, resolve, rollback_writes, save_steps, stale_cells

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


def cmd_read(args):
    pages = [parse_price_page(Path(path).read_text(encoding="utf-8")) for path in args.price_page]
    adjusts = [parse_adjust_page(Path(path).read_text(encoding="utf-8")) for path in args.adjust_page or ()]
    return encode_snapshot(build_snapshot(args.hotel, args.read_at or now_text(), pages, adjusts))


def cmd_plan(args):
    snapshot, request = decode_snapshot(load(args.snapshot)), decode_request(load(args.request))
    plan = plan_change(snapshot, request)
    resolutions = [decode_resolution(item) for item in load(args.resolutions)] if args.resolutions else []
    writes, unresolved = resolve(plan, resolutions)
    steps = save_steps(writes) if not unresolved else None
    change_id = Ledger().record_preview(plan) if args.record else None
    return dict(change_id=change_id, counts=counts(plan.changes, len(plan.skipped)), plan=encode_plan(plan),
                unresolved=[encode_change(change) for change in unresolved],
                steps=None if steps is None else [encode_step(step) for step in steps])


def cmd_render(args):
    if args.kind == "preview":
        data = load(args.plan)
        plan = decode_plan(data["plan"])
        html, hotel = render_preview(plan, data.get("change_id"), len(data["steps"]) if data.get("steps") else None), \
            plan.request.hotel
    elif args.kind == "rollback":
        plan = decode_rollback(load(args.plan)["rollback"])
        html, hotel = render_rollback(plan), plan.hotel
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
    request = decode_request(data["plan"]["request"]) if "plan" in data else None
    ledger = Ledger()
    ledger.begin(args.change, [decode_step(step) for step in data["steps"]], request)
    record = ledger.change(args.change)
    return dict(change_id=record.id, status=record.status, steps=len(record.steps))


def cmd_record_step(args):
    return dict(change_id=args.change, step=args.step,
                status=Ledger().record_step(args.change, args.step, args.saved, args.note))


def cmd_verify(args):
    mismatches = Ledger().verify(args.change, decode_snapshot(load(args.snapshot)))
    return dict(change_id=args.change, same=not mismatches, mismatches=[
        dict(key=encode_key(key), sell=str(write.sell), list=money_text(write.list_price), seen=encode_value(seen))
        for key, write, seen in mismatches])


def cmd_stale(args):
    differences = stale_cells(decode_snapshot(load(args.before)), decode_snapshot(load(args.after)))
    return dict(same=not differences, differences=[
        dict(key=encode_key(item.key), then=encode_value(item.then), now=encode_value(item.now)) for item in differences])


def cmd_rollback(args):
    ledger = Ledger()
    plan = plan_rollback(ledger.recorded_change(args.change), ledger.later_writes(args.change),
                         decode_snapshot(load(args.snapshot)), args.include_kept)
    change_id = ledger.record_rollback_preview(plan, args.sentence) if args.record else None
    return dict(change_id=change_id, rollback=encode_rollback(plan),
                steps=[encode_step(step) for step in save_steps(rollback_writes(plan))])


def cmd_save_snapshot(args):
    return dict(change_id=Ledger().record_snapshot(decode_snapshot(load(args.snapshot)), args.sentence))


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

    sub = command("read", cmd_read, "ERP 화면 조각 → 지금 값")
    sub.add_argument("--hotel", required=True)
    sub.add_argument("--price-page", action="append", required=True, help="[선택 날짜 가격 수정] 확인 단계 HTML (여러 번)")
    sub.add_argument("--adjust-page", action="append", help="[선택 날짜 가격 가감] 확인 단계 HTML (여러 번)")
    sub.add_argument("--read-at", help="읽은 시각(ISO). 없으면 지금")

    sub = command("plan", cmd_plan, "미리보기 계산")
    sub.add_argument("--snapshot", required=True)
    sub.add_argument("--request", required=True)
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
    sub.add_argument("--record", action="store_true", help="장부에 되돌리기 미리보기로 적는다")
    sub.add_argument("--sentence", default="되돌리기", help="담당자가 한 말")

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
    except (ParseError, PlanError, LedgerError, ValueError, KeyError, TypeError) as error:
        message = str(error) if not isinstance(error, (KeyError, TypeError)) else f"입력 JSON 에 필요한 칸이 없습니다: {error}"
        print(json.dumps(dict(error=message), ensure_ascii=False), file=sys.stderr)
        return 2
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out and args.command != "render":
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if result.get("same") is False else 0


if __name__ == "__main__":
    sys.exit(main())
