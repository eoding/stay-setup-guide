"""price_browser.py — 브라우저 쪽 `window.stayPrice`(`scripts/page/stay_price.js`)와 주고받는 가격 칸의 모양.

답의 공통 부분(지문 · 잘린 답 · 조각 잇기 · 읽은 시각 · 저장 답의 뜻)은 `change_core.answers` 에 있다. 여기에는 가격 칸만의 것을 둔다.

    read_calls(hotel, offer, pairs, dates)       readPair 부를 값 — 객실 × 요금제마다, 고른 날만 덮는 기간·요일로(186일씩)
    reserved_probes(hotel, offer, pairs, dates)  readReserved 첫 물음 — 같은 기간마다 객실·요금제 전부
    page_hotel(results)                   읽기 답의 조각이 말하는 호텔(페이지가 알아본 번호·이름) — 하나여야 한다
    reserved_round(probes, results)       물음과 답 → 남은 물음, 다 끝났으면 쓸 가감 확인 단계(숨긴 줄 0)
    reading_time(results)                 읽기 한 번이 ERP 를 읽은 시각 — readPair · readReserved 답의 끝난 시각 가운데 가장 이른 것
    pair_reads(results)                   readPair 답 → PairRead — 객실은 물은(캘린더 칩의) 이름, 화면의 오퍼·요금제가 다르면 거절
    step_call(no, hotel, offer, kind, body)  장부의 저장 단계 하나 → applyBulk / applyCell 부를 값(쓰는 값만)
    step_calls(hotel, offer, steps, reading)  장부의 저장 단계들 → 부를 값들 — 칸마다 누르기 전에 화면에 있어야 할 값(`was`)을 싣는다

부를 값에는 언제나 `hotel`({id, name} — stayPrice.look() 의 hotel)이 든다. 페이지는 무엇이든 누르기 전에 탭이 그 번호의 호텔인지
보고, 아니면 두 호텔을 대며 거절한다.

가감 확인 단계는 건너뛰는 칸을 300줄까지만 보이고 나머지는 숨긴 줄 수로 말한다. 숨긴 줄이 있는 답은 쓰지 않고,
그 물음을 객실 → 요금제 → 날짜 반쪽 순으로 쪼개 다시 묻는다. 쪼갠 물음들은 원래 물음의 칸을 나눠 가지므로, 숨긴 줄이
없는 답들을 합치면 원래 물음이 다 보였을 때와 같다. 계산은 답 목록만 보고 매번 처음부터 다시 한다(답을 덧붙여 다시 부르면 된다).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Iterable, Mapping

from change_core import answers as shared
from change_core.answers import BrowserError, ask_sum, attach_bodies
from change_core.money import money_text
from change_core.words import josa
from price_plan import days_summary
from erp_read import AdjustPage, PairRead, parse_adjust_page, parse_price_page
from price_model import (ERP_MAX_DAYS, FIELDS, MISSING, WEEKDAYS, CellKey, CellValue, RowWrite, Snapshot, day_windows, decode_step,
                         iso_day)

READ_SPAN = 186                      # readPair 한 번의 기간 — 달마다 달력 칸을 보므로(판매일 확인) 여섯 달 남짓으로 끊어 45초 안에
# 페이지가 두는 조각 수(stay_price.js 의 KEEP_BODIES). 읽기는 readPair · readReserved 를 다 부른 뒤에 조각을 받으므로(take),
# 한 번의 읽기가 이보다 많은 조각을 만들면 앞 조각이 밀려나 받을 수 없다 — 그것이 읽기 한 번이 덮을 수 있는 크기이고, read-calls 는
# 이보다 큰 읽기를 거절한다(`reading_size`). 1년이면 객실 · 요금제 99개, 550일(ERP_MAX_DAYS)이면 66개까지 한 번에 읽는다.
PAGE_KEEPS = 200
PROBE_FIELDS = ("hotel", "offer", "rooms", "ratePlans", "from", "to", "weekdays", "occupancy", "nights")
OPS = {"bulk": "applyBulk", "cell_edit": "applyCell"}
READS = ("readPair", "readReserved")   # 읽기 한 번의 읽는 작업 — 읽은 시각은 이 답들의 끝난 시각에서 잰다(look 은 뺀다)


def reading_time(results: Iterable) -> str:
    return shared.reading_time(results, READS)


def selected(first: str, last: str, weekdays: Iterable[str]) -> list[str]:
    """first ~ last 가운데 고른 요일의 날 — 화면의 「기간 ∩ 요일」 과 같다."""
    wanted = {WEEKDAYS.index(day) for day in weekdays}
    start, end = date.fromisoformat(first), date.fromisoformat(last)
    return [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)
            if (start + timedelta(days=offset)).weekday() in wanted]


def periods(dates: Iterable[str], span: int = ERP_MAX_DAYS) -> list[tuple[str, str, list[str]]]:
    """고른 날만 덮는 (시작일, 종료일, 요일) 목록. 「기간 ∩ 요일」 하나로 꼭 그 날들이 되면 하나, 아니면 이어진 날마다 하나.

    가격 수정 창은 판매일이 없는 날이 하루라도 끼면 기간을 통째로 거절하므로, 고르지 않은 날을 덮지 않는다.
    """
    days = sorted({iso_day(day) for day in dates})
    if not days:
        raise ValueError("날짜가 없습니다")
    out = []
    for window in day_windows(days, span):
        weekdays = [WEEKDAYS[index] for index in sorted({date.fromisoformat(day).weekday() for day in window})]
        if selected(window[0], window[-1], weekdays) == window:
            out.append((window[0], window[-1], weekdays))
            continue
        runs: list[list[str]] = []
        for day in window:
            if runs and (date.fromisoformat(day) - date.fromisoformat(runs[-1][-1])).days == 1:
                runs[-1].append(day)
            else:
                runs.append([day])
        out += [(run[0], run[-1], list(WEEKDAYS)) for run in runs]
    return out


def _hotel(hotel: Mapping) -> dict:
    if not str(hotel.get("id") or "").strip():
        raise BrowserError("부를 값에 호텔 번호가 없습니다 — stayPrice.look() 의 hotel 을 그대로 씁니다")
    return {"id": str(hotel["id"]).strip(), "name": str(hotel.get("name") or "")}


def read_calls(hotel: Mapping, offer: str, pairs: Iterable[tuple[str, str]], dates: Iterable[str]) -> list[dict]:
    spans, hotel = periods(dates, READ_SPAN), _hotel(hotel)
    return [{"hotel": hotel, "offer": offer, "room": room, "ratePlan": plan, "from": first, "to": last, "weekdays": weekdays}
            for room, plan in dict.fromkeys(pairs) for first, last, weekdays in spans]


def reading_size(calls: Mapping) -> dict:
    """읽기 한 번(read-calls 가 낸 `{pairs, reserved}`)의 페이지 작업 수 — 숨은 줄로 예약 읽기가 쪼개지기 전의 수다. 합쳐
    PAGE_KEEPS 를 넘으면 한 번에 읽지 못한다(앞 조각이 밀려난다)."""
    pairs, probes = len(calls["pairs"]), len(calls["reserved"])
    return dict(readPair=pairs, readReserved=probes, limit=PAGE_KEEPS, fits=pairs + probes <= PAGE_KEEPS)


def too_big(size: Mapping) -> str:
    """읽기 한 번에 들지 않는 까닭 — 거절 문장의 가운데."""
    return (f"페이지 작업이 가격 읽기 {size['readPair']}번 + 예약 있는 날 읽기 {size['readReserved']}번인데, 읽기 한 번은 "
            f"{PAGE_KEEPS}번까지입니다(페이지가 읽은 화면 조각을 {PAGE_KEEPS}개까지만 두고 — stay_price.js KEEP_BODIES — 조각은 다 읽은 "
            f"뒤에 받으므로 넘으면 앞 조각이 밀려납니다. 가격 읽기는 객실 · 요금제마다 {READ_SPAN}일에 한 번, 예약 읽기는 "
            f"{ERP_MAX_DAYS}일에 한 번)")


def reserved_probes(hotel: Mapping, offer: str, pairs: Iterable[tuple[str, str]], dates: Iterable[str]) -> list[dict]:
    """객실 · 요금제는 이름순이다 — 요청 파일로 읽든 장부 번호로 읽든 같은 범위면 같은 물음(같은 지문)이 되어, 앞선 읽기의
    조각을 그대로 빌릴 수 있다."""
    pairs, hotel = list(pairs), _hotel(hotel)
    rooms, plans = sorted({room for room, _ in pairs}), sorted({plan for _, plan in pairs})
    return [{"hotel": hotel, "offer": offer, "rooms": rooms, "ratePlans": plans, "from": first, "to": last,
             "weekdays": weekdays, "occupancy": "*", "nights": "all"} for first, last, weekdays in periods(dates)]


def _same_hotel_as_asked(result: Mapping) -> None:
    """페이지는 물은 호텔이 아니면 읽지 않는다. 조각이 말하는 호텔이 물은 번호와 다르면 쓰지 않는다(덧붙인 파일이 섞였을 때)."""
    seen, asked = result.get("hotel"), (result.get("asked") or {}).get("hotel")
    if not isinstance(seen, Mapping) or not isinstance(asked, Mapping) or str(seen.get("id")) != str(asked.get("id")):
        raise BrowserError(f"{result.get('op')} 의 답이 물은 호텔({(asked or {}).get('id')})이 아닌 "
                           f"{(seen or {}).get('id') if isinstance(seen, Mapping) else '모르는'} 호텔에서 읽은 것입니다")


def page_hotel(results: Iterable) -> dict:
    """읽기 답들이 말하는 호텔 {id, name} — 페이지가 알아본 그대로. 둘 이상이거나 없으면 거절한다."""
    seen = {(str(result["hotel"].get("id")), str(result["hotel"].get("name") or "")) for result in attach_bodies(results)
            if result.get("op") in ("readPair", "readReserved") and result.get("ok") and isinstance(result.get("hotel"), Mapping)}
    if len(seen) != 1:
        raise BrowserError("읽기 답에서 호텔을 하나로 정하지 못했습니다: " + (" · ".join(f"{i} ({n})" for i, n in sorted(seen)) or "없음"))
    hotel_id, name = seen.pop()
    return {"id": hotel_id, "name": name}


def probe_key(probe: Mapping) -> str:
    missing = [name for name in PROBE_FIELDS if name not in probe]
    if missing:
        raise BrowserError(f"readReserved 물음에 칸이 없습니다: {', '.join(missing)}")
    return ask_sum({name: probe[name] for name in PROBE_FIELDS})


def split(probe: Mapping) -> list[dict]:
    """숨긴 줄이 있던 물음을 둘 이상으로 — 객실 하나씩, 그다음 요금제 하나씩, 그다음 고른 날의 반쪽씩."""
    if len(probe["rooms"]) > 1:
        return [dict(probe, rooms=[room]) for room in probe["rooms"]]
    if len(probe["ratePlans"]) > 1:
        return [dict(probe, ratePlans=[plan]) for plan in probe["ratePlans"]]
    days = selected(probe["from"], probe["to"], probe["weekdays"])
    if len(days) > 1:
        half = len(days) // 2
        return [dict(probe, **{"from": days[0], "to": days[half - 1]}), dict(probe, **{"from": days[half], "to": days[-1]})]
    raise BrowserError(f"{probe['rooms'][0]} · {probe['ratePlans'][0]} · {probe['from']} 하루로 좁혀도 가감 확인 단계가 줄을 숨깁니다")


@dataclass
class Round:
    """`ask` 는 아직 답이 없는 물음(그대로 readReserved 에 넘긴다), `pages` 는 쓸 답, `failed` 는 실패한 답의 까닭."""
    ask: list[dict]
    pages: list[AdjustPage]
    failed: list[dict] = field(default_factory=list)

    @property
    def done(self) -> bool:
        return not self.ask


def reserved_round(probes: Iterable[Mapping], results: Iterable[Mapping]) -> Round:
    """`results` 는 readReserved 답과 그 조각의 take 답들(순서 무관). 답은 지문(`ask`)으로 물음에 붙는다."""
    answers: dict[str, AdjustPage] = {}
    failures: dict[str, str] = {}
    for result in attach_bodies(results):
        if result.get("op") != "readReserved":
            raise BrowserError(f"readReserved 의 답이 아닙니다: {result.get('op')}")
        key = str(result.get("ask"))
        if result.get("ok"):
            _same_hotel_as_asked(result)
            answers[key] = parse_adjust_page(result["fragment"])
            failures.pop(key, None)
        elif key not in answers:
            failures[key] = result.get("error") or "실패"
    ask, pages, queue = [], [], [dict(probe) for probe in probes]
    while queue:
        probe = queue.pop(0)
        page = answers.get(probe_key(probe))
        if page is None:
            ask.append(probe)
        elif page.hidden:
            queue[0:0] = split(probe)
        else:
            pages.append(page)
    return Round(ask, pages, [{"asked": probe, "error": failures[probe_key(probe)]} for probe in ask if probe_key(probe) in failures])


class NoSaleDays(BrowserError):
    """고른 날이 모두 판매일 없음 — 더 읽지 않는다. `say` 는 도우미가 담당자에게 그대로 하는 말이다(거절과 함께 나간다 — change_core.cli)."""

    def __init__(self, message: str, say: str):
        super().__init__(message)
        self.say = say


def refuse_no_sale_days(pairs: list[Mapping], results: Iterable) -> None:
    """readPair 부를 값마다 답이 와 있고 어느 답에도 판매일 있는 날이 없으면(`days.withCell` 이 모두 0) 거절한다 — 판매일이 없는
    날에는 넣을 칸도 읽을 가격도 없다. readPair 의 첫 답이 이미 그렇게 말하므로 예약 있는 날 · 조각을 더 읽지 않는다(시운전 9 —
    readPair 가 「고른 날이 모두 판매일 없음」이라 했는데 읽기 셋을 더 하고서야 멈췄다). 하나라도 답이 없거나 판매일 있는 날이
    있으면 아무것도 하지 않는다(판매일 없는 날만 미리보기가 따로 댄다)."""
    results = list(results)
    if not pairs or shared.unanswered(pairs, results, "readPair"):
        return
    small = {str(result.get("ask")): result for result in shared.answers(shared.answers_for(results, "readPair"))[0]
             if result.get("op") == "readPair"}
    found = [small.get(ask_sum(call)) for call in pairs]
    if any(answer is None or not answer.get("ok") or (answer.get("days") or {}).get("withCell", 1) != 0 for answer in found):
        return
    days = sorted({day for call in pairs for day in selected(call["from"], call["to"], call["weekdays"])})
    rooms = ", ".join(dict.fromkeys(f"{call['room']}({call['ratePlan']})" for call in pairs))
    say = (f"{josa(days_summary(days), '은는')} {pairs[0]['offer']} 오퍼의 {rooms}에 판매일이 열려 있지 않습니다 — 그날은 가격을 읽을 "
           "수도 넣을 수도 없습니다. 판매일은 ERP 의 판매일 탭에서 사람이 엽니다. 아무것도 바꾸지 않았고 장부에도 적지 않았습니다.")
    raise NoSaleDays("고른 날이 모두 판매일 없음입니다(readPair 의 답 `days.withCell` 이 모두 0) — 더 읽지 않습니다. 거절의 `say` 를 "
                     "담당자에게 그대로 말하고 멈춥니다(미리보기 · 장부 없음)", say)


def pair_reads(results: Iterable[Mapping]) -> list[PairRead]:
    """`results` 는 readPair 답과 그 조각의 take 답들. 객실은 물은 이름(캘린더 칩의 이름)으로 적는다.

    읽은 날과 「판매일 없음」인 날을 합치면 물은 날(기간 ∩ 요일)과 꼭 같아야 한다 — 하루라도 빠지거나 남으면 거절한다.
    """
    reads = []
    for result in attach_bodies(results):
        if result.get("op") != "readPair":
            raise BrowserError(f"readPair 의 답이 아닙니다: {result.get('op')}")
        if not result.get("ok"):
            raise BrowserError(f"{result.get('what') or '객실 · 요금제'} 를 읽지 못했습니다: {result.get('error')}")
        asked = result["asked"]
        _same_hotel_as_asked(result)
        page = parse_price_page(result["fragment"]) if result.get("fragment") else None
        no_sale = tuple(sorted(iso_day(day) for day in result.get("noSale") or ()))
        wanted = set(selected(asked["from"], asked["to"], asked["weekdays"]))
        if set(page.days if page else ()) | set(no_sale) != wanted or (page and set(page.days) & set(no_sale)):
            raise BrowserError(f"{asked['room']} · {asked['ratePlan']}: 읽은 날과 판매일 없는 날을 합쳐도 물은 날과 맞지 않습니다")
        reads.append(PairRead(asked["offer"], asked["room"], asked["ratePlan"], page, no_sale))
    return reads


def step_call(no: int, hotel: Mapping, offer: str, kind: str, body: Mapping) -> dict:
    """장부의 저장 단계(번호 · 종류 · `encode_step` 모양) → `{no, op, payload}`. payload 는 stayPrice 의 그 작업에 그대로 넘긴다.
    `hotel` 은 장부가 적어 둔 호텔(페이지가 알아본 번호 · 이름) — 다른 호텔의 탭이면 페이지가 누르지 않는다."""
    step, hotel = decode_step(dict(body, kind=kind)), _hotel(hotel)
    if step.kind == "cell_edit":
        key = step.key
        payload = {"no": no, "hotel": hotel, "offer": offer, "room": key.room, "ratePlan": key.rate_plan, "date": key.date,
                   "occupancy": key.occupancy, "nights": key.nights, "clear": list(step.clear)}
    else:
        payload = {"no": no, "hotel": hotel, "offer": offer, "room": step.room, "ratePlan": step.rate_plan,
                   "dates": list(step.dates),
                   "rows": [{"occupancy": row.occupancy, "nights": row.nights,
                             **{name: money_text(getattr(row, name)) for name in FIELDS}} for row in step.rows]}
    return {"no": no, "op": OPS[step.kind], "payload": payload}


def _shown(value: CellValue) -> list:
    """칸 하나가 화면에 보일 값 — [판매가, 정가, 공급 원가] 금액 글자(없으면 null). 판매가가 null 이면 칸이 없다(가격 없음)."""
    return [money_text(getattr(value, name)) for name in FIELDS]


def _runs(dates, values) -> list[list]:
    """단계의 날짜(차례대로)와 날마다 있어야 할 값 → `[첫 날, 끝 날, 판매가, 정가, 공급 원가]` 목록. 단계의 날짜 목록에서 잇달아 같은
    값인 날들을 한 줄로 묶는다(끝 날까지의 단계 날짜가 그 줄의 날이다 — 사이의 고르지 않은 날은 들지 않는다)."""
    runs: list[list] = []
    for day, value in zip(dates, values):
        shown = _shown(value)
        if runs and runs[-1][2:] == shown:
            runs[-1][1] = day
        else:
            runs.append([day, day, *shown])
    return runs


def _after(value: CellValue, row: RowWrite) -> CellValue:
    """묶음 저장 한 줄이 칸 하나에 넣은 뒤의 값 — 넣은 필드만 바뀐다. 없던 칸은 판매가를 넣으면 생긴다."""
    written = {name: getattr(row, name) for name in FIELDS if getattr(row, name) is not None}
    if value.state == "missing":
        return CellValue(written["sell"], written.get("list"), written.get("supply"), "open") if "sell" in written else value
    return replace(value, **written)


def step_calls(hotel: Mapping, offer: str, steps: Iterable[tuple[int, str, Mapping]], reading: Snapshot) -> list[dict]:
    """장부의 저장 단계들(번호 · 종류 · `encode_step` 모양, 차례대로) → 부를 값들. 단계가 쓰는 칸마다 누르는 순간 화면에 있어야 할
    값을 `was` 로 싣는다 — 그 계산이 바탕으로 삼은 읽은 값(`reading`, 장부에 적힌 것) 위에 앞 단계들이 넣은 값을 얹은 것이다(같은
    칸을 셀 창이 먼저 비우고 묶음 저장이 판매가를 넣는 때가 있다). 묶음 저장은 줄마다 `was: [[첫 날, 끝 날, 판매가, 정가, 공급
    원가], …]`(`_runs`), 셀 창은 `was: [판매가, 정가, 공급 원가]`. 페이지는 무엇이든 치기 전에 화면의 값(가격 수정 ② 의 「기존」 줄 ·
    셀 창의 줄)과 견주고, 다르면 치지도 누르지도 않고 거절한다 — 그 사이 다른 손이 바꾼 값을 낡은 계산으로 덮지 않는다. 그래서
    저장된 칸의 장부 「전 값」은 누른 순간 화면에 있던 값이다."""
    seen = dict(reading.cells)
    calls = []
    for no, kind, body in steps:
        call, step = step_call(no, hotel, offer, kind, body), decode_step(dict(body, kind=kind))
        if step.kind == "cell_edit":
            value = seen.get(step.key, MISSING)
            call["payload"]["was"] = _shown(value)
            if value.state != "missing":
                seen[step.key] = replace(value, **{name: None for name in step.clear})
        else:
            for row, sent in zip(step.rows, call["payload"]["rows"]):
                keys = [CellKey(step.room, step.rate_plan, day, row.occupancy, row.nights) for day in step.dates]
                sent["was"] = _runs(step.dates, [seen.get(key, MISSING) for key in keys])
                seen.update({key: _after(seen.get(key, MISSING), row) for key in keys})
        calls.append(call)
    return calls
