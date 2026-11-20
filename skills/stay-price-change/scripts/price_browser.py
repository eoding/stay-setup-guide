"""price_browser.py — 브라우저 쪽 `window.stayPrice`(`scripts/page/stay_price.js`)와 주고받는 모양.

    read_calls(offer, pairs, dates)       readPair 부를 값 — 객실 × 요금제마다, 고른 날만 덮는 기간·요일로(186일씩)
    reserved_probes(offer, pairs, dates)  readReserved 첫 물음 — 같은 기간마다 객실·요금제 전부
    attach_bodies(results)                읽기 답에 페이지에 남겨 둔 조각을 붙인다 — 쪽(take 답)을 잇고 바이트 수·CRC-32 를 맞춰 본다
    reserved_round(probes, results)       물음과 답 → 남은 물음, 다 끝났으면 쓸 가감 확인 단계(숨긴 줄 0)
    pair_reads(results)                   readPair 답 → PairRead — 객실은 물은(캘린더 칩의) 이름, 화면의 오퍼·요금제가 다르면 거절
    step_call(no, offer, kind, body)      장부의 저장 단계 하나 → applyBulk / applyCell 부를 값
    step_outcome(call, result)            브라우저 답 → (저장됨, 메모). 그 단계를 물은 답이 아니면 거절. 「알 수 없음」은 저장됨이 아니다

가감 확인 단계는 건너뛰는 칸을 300줄까지만 보이고 나머지는 숨긴 줄 수로 말한다. 숨긴 줄이 있는 답은 쓰지 않고,
그 물음을 객실 → 요금제 → 날짜 반쪽 순으로 쪼개 다시 묻는다. 쪼갠 물음들은 원래 물음의 칸을 나눠 가지므로, 숨긴 줄이
없는 답들을 합치면 원래 물음이 다 보였을 때와 같다. 계산은 답 목록만 보고 매번 처음부터 다시 한다(답을 덧붙여 다시 부르면 된다).

브라우저 도구는 답을 2,000바이트쯤에서 자른다. 그래서 페이지는 작업의 답(1,500바이트 안)에 `ask`(물은 값의 지문)와
`body`(id · 바이트 수 · CRC-32 · 쪽 수)만 싣고, 조각은 `stayPrice.take(id, index)` 로 한 쪽씩 내준다. 이 모듈은 쪽을 이어
바이트 수와 CRC-32 가 둘 다 맞을 때만 쓴다 — 잘리거나 잘못 옮겨 적은 쪽이 틀린 가격이 되지 않는다.
"""

from __future__ import annotations

import json
import zlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Mapping

from change_core.money import money_text
from erp_read import AdjustPage, PairRead, parse_adjust_page, parse_price_page
from price_model import FIELDS, WEEKDAYS, decode_step, iso_day

MAX_SPAN = 550                       # ERP 가 한 번에 받는 기간(일)
READ_SPAN = 186                      # readPair 한 번의 기간 — 달마다 달력 칸을 보므로(판매일 확인) 여섯 달 남짓으로 끊어 45초 안에
PROBE_FIELDS = ("offer", "rooms", "ratePlans", "from", "to", "weekdays", "occupancy", "nights")
OPS = {"bulk": "applyBulk", "cell_edit": "applyCell"}


class BrowserError(ValueError):
    """브라우저의 답이 물은 것과 맞지 않거나, 더 물어도 답을 얻을 수 없다."""


def ask_sum(value: Mapping) -> str:
    """물은 값의 지문 — `no` 를 뺀 값을 키 정렬 JSON 으로 적은 것의 CRC-32(페이지의 `askedOf`·`canon`·`crc32` 와 같다)."""
    text = json.dumps({name: item for name, item in value.items() if name != "no"}, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    return f"{zlib.crc32(text.encode('utf-8')):08x}"


def attach_bodies(results: Iterable[Mapping]) -> list[dict]:
    """답 목록(읽기 답과 take 답이 섞여 있다) → 읽기 답마다 조각을 푼 답. take 답은 빠진다.

    쪽이 하나라도 없거나, 같은 쪽이 서로 다르거나, 이은 글자의 바이트 수·CRC-32 가 답의 body 와 다르면 BrowserError.
    풀린 body 의 물음(`asked`)은 답의 지문(`ask`)과 맞아야 한다.
    """
    results = [dict(result) for result in results]
    pieces: dict[str, dict[int, Mapping]] = {}
    for result in results:
        if result.get("op") != "take":
            continue
        if not result.get("ok"):
            raise BrowserError(f"조각 한 쪽을 받지 못했습니다: {result.get('error')}")
        seen = pieces.setdefault(str(result["id"]), {}).setdefault(int(result["index"]), result)
        if seen.get("text") != result.get("text"):
            raise BrowserError(f"조각 {result['id']} 의 {result['index']}번째 쪽이 두 번 왔는데 서로 다릅니다")
    out = []
    for result in results:
        if result.get("op") == "take":
            continue
        meta = result.get("body")
        if not result.get("ok") or meta is None:
            out.append(result)
            continue
        got = pieces.get(str(meta["id"]), {})
        missing = [index for index in range(int(meta["pieces"])) if index not in got]
        if missing:
            raise BrowserError(f"조각 {meta['id']} 의 쪽 {len(missing)}개를 받지 않았습니다(번호 {', '.join(map(str, missing[:5]))})")
        if any((piece.get("count"), piece.get("bytes"), piece.get("crc32")) != (meta["pieces"], meta["bytes"], meta["crc32"])
               for piece in got.values()):
            raise BrowserError(f"조각 {meta['id']} 의 쪽들이 말하는 크기·검사값이 답과 다릅니다")
        text = "".join(got[index]["text"] for index in range(int(meta["pieces"])))
        data = text.encode("utf-8")
        if len(data) != meta["bytes"] or f"{zlib.crc32(data):08x}" != meta["crc32"]:
            raise BrowserError(f"조각 {meta['id']} 을 이어 보니 바이트 수나 CRC-32 가 맞지 않습니다 — 쪽을 다시 받아야 합니다")
        body = json.loads(text)
        if body.get("op") != result.get("op") or ask_sum(body.get("asked") or {}) != result.get("ask"):
            raise BrowserError(f"조각 {meta['id']} 은 이 답의 물음에서 나온 것이 아닙니다")
        out.append({**result, **body})
    return out


def selected(first: str, last: str, weekdays: Iterable[str]) -> list[str]:
    """first ~ last 가운데 고른 요일의 날 — 화면의 「기간 ∩ 요일」 과 같다."""
    wanted = {WEEKDAYS.index(day) for day in weekdays}
    start, end = date.fromisoformat(first), date.fromisoformat(last)
    return [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)
            if (start + timedelta(days=offset)).weekday() in wanted]


def periods(dates: Iterable[str], span: int = MAX_SPAN) -> list[tuple[str, str, list[str]]]:
    """고른 날만 덮는 (시작일, 종료일, 요일) 목록. 「기간 ∩ 요일」 하나로 꼭 그 날들이 되면 하나, 아니면 이어진 날마다 하나.

    가격 수정 창은 판매일이 없는 날이 하루라도 끼면 기간을 통째로 거절하므로, 고르지 않은 날을 덮지 않는다.
    """
    days = sorted({iso_day(day) for day in dates})
    if not days:
        raise ValueError("날짜가 없습니다")
    windows: list[list[str]] = []
    for day in days:
        if windows and (date.fromisoformat(day) - date.fromisoformat(windows[-1][0])).days < span:
            windows[-1].append(day)
        else:
            windows.append([day])
    out = []
    for window in windows:
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


def read_calls(offer: str, pairs: Iterable[tuple[str, str]], dates: Iterable[str]) -> list[dict]:
    spans = periods(dates, READ_SPAN)
    return [{"offer": offer, "room": room, "ratePlan": plan, "from": first, "to": last, "weekdays": weekdays}
            for room, plan in dict.fromkeys(pairs) for first, last, weekdays in spans]


def reserved_probes(offer: str, pairs: Iterable[tuple[str, str]], dates: Iterable[str]) -> list[dict]:
    pairs = list(dict.fromkeys(pairs))
    rooms, plans = list(dict.fromkeys(room for room, _ in pairs)), list(dict.fromkeys(plan for _, plan in pairs))
    return [{"offer": offer, "rooms": rooms, "ratePlans": plans, "from": first, "to": last, "weekdays": weekdays,
             "occupancy": "*", "nights": "all"} for first, last, weekdays in periods(dates)]


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
        page = parse_price_page(result["fragment"]) if result.get("fragment") else None
        no_sale = tuple(sorted(iso_day(day) for day in result.get("noSale") or ()))
        wanted = set(selected(asked["from"], asked["to"], asked["weekdays"]))
        if set(page.days if page else ()) | set(no_sale) != wanted or (page and set(page.days) & set(no_sale)):
            raise BrowserError(f"{asked['room']} · {asked['ratePlan']}: 읽은 날과 판매일 없는 날을 합쳐도 물은 날과 맞지 않습니다")
        reads.append(PairRead(asked["offer"], asked["room"], asked["ratePlan"], page, no_sale))
    return reads


def step_call(no: int, offer: str, kind: str, body: Mapping) -> dict:
    """장부의 저장 단계(번호 · 종류 · `encode_step` 모양) → `{no, op, payload}`. payload 는 stayPrice 의 그 작업에 그대로 넘긴다."""
    step = decode_step(dict(body, kind=kind))
    if step.kind == "cell_edit":
        key = step.key
        payload = {"no": no, "offer": offer, "room": key.room, "ratePlan": key.rate_plan, "date": key.date,
                   "occupancy": key.occupancy, "nights": key.nights, "clear": list(step.clear)}
    else:
        payload = {"no": no, "offer": offer, "room": step.room, "ratePlan": step.rate_plan, "dates": list(step.dates),
                   "rows": [{"occupancy": row.occupancy, "nights": row.nights,
                             **{name: money_text(getattr(row, name)) for name in FIELDS}} for row in step.rows]}
    return {"no": no, "op": OPS[step.kind], "payload": payload}


def step_outcome(call: Mapping, result: Mapping) -> tuple[bool, str]:
    """(저장됨, 장부 메모). 다른 작업·다른 번호·다른 값을 물은 답이면 BrowserError — 엉뚱한 단계에 적지 않는다."""
    if result.get("op") != call["op"] or result.get("no") != call["no"]:
        raise BrowserError(f"{call['no']}번 저장({call['op']})의 답이 아닙니다: {result.get('op')} {result.get('no')}번")
    if result.get("ask") != ask_sum(call["payload"]):
        raise BrowserError(f"{call['no']}번 저장의 답이 장부의 그 단계와 다른 값을 물었습니다")
    if result.get("saved") is True:
        note = result.get("note") or "저장했습니다"
        return True, note if result.get("ok") else f"{note} · {result.get('error')}"
    reason = result.get("error") or "저장하지 못했습니다"
    if result.get("saved") == "unknown":
        return False, f"저장됐는지 알 수 없습니다 — 다시 읽어 값을 확인해야 합니다: {reason}"
    return False, reason
