"""price_browser.py — 브라우저 쪽 `window.stayPrice`(`scripts/page/stay_price.js`)와 주고받는 모양.

    read_calls(hotel, offer, pairs, dates)       readPair 부를 값 — 객실 × 요금제마다, 고른 날만 덮는 기간·요일로(186일씩)
    reserved_probes(hotel, offer, pairs, dates)  readReserved 첫 물음 — 같은 기간마다 객실·요금제 전부
    page_hotel(results)                   읽기 답의 조각이 말하는 호텔(페이지가 알아본 번호·이름) — 하나여야 한다
    attach_bodies(results, earlier)       읽기 답에 페이지에 남겨 둔 조각을 붙인다 — 쪽(take 답)을 잇고 바이트 수·CRC-32·FNV-1a 를
                                          맞춰 본다. 앞선 읽기(earlier)에서 다 받은 같은 조각이면 그것을 쓴다
    reserved_round(probes, results)       물음과 답 → 남은 물음, 다 끝났으면 쓸 가감 확인 단계(숨긴 줄 0)
    pair_reads(results)                   readPair 답 → PairRead — 객실은 물은(캘린더 칩의) 이름, 화면의 오퍼·요금제가 다르면 거절
    step_call(no, hotel, offer, kind, body)  장부의 저장 단계 하나 → applyBulk / applyCell 부를 값

부를 값에는 언제나 `hotel`({id, name} — stayPrice.look() 의 hotel)이 든다. 페이지는 무엇이든 누르기 전에 탭이 그 번호의 호텔인지
보고, 아니면 두 호텔을 대며 거절한다.
    step_outcome(call, result)            브라우저 답 → Outcome(저장됨 · 안 됨 · 모름 · 시작 안 함). 그 단계를 물은 답이 아니면 거절

가감 확인 단계는 건너뛰는 칸을 300줄까지만 보이고 나머지는 숨긴 줄 수로 말한다. 숨긴 줄이 있는 답은 쓰지 않고,
그 물음을 객실 → 요금제 → 날짜 반쪽 순으로 쪼개 다시 묻는다. 쪼갠 물음들은 원래 물음의 칸을 나눠 가지므로, 숨긴 줄이
없는 답들을 합치면 원래 물음이 다 보였을 때와 같다. 계산은 답 목록만 보고 매번 처음부터 다시 한다(답을 덧붙여 다시 부르면 된다).

브라우저 도구는 답을 1,000자쯤에서 자른다(`[TRUNCATED]`). 그래서 페이지는 작업의 답(JSON 으로 800자 안)에 `ask`(물은 값의
지문)와 `body`(id 와 그 글자를 알아볼 값 — 글자 수 · 바이트 수 · CRC-32 · FNV-1a)만 싣고, 조각은 `stayPrice.take(id, at, size)` 로
한 쪽씩 내준다. 이 모듈은 쪽을 자리로 이어 바이트 수 · CRC-32 · FNV-1a 가 모두 맞을 때만 쓴다 — 잘리거나 잘못 옮겨 적은 쪽이
틀린 가격이 되지 않는다. 잘린 답(글자 그대로 넣는다)은 알아보고, 어느 쪽을 어떤 크기로 다시 받을지 말한다(CutAnswer.refetch).

한 변경은 세 번 읽는다(미리보기 · 적용 직전 · 적용 뒤). 적용 직전의 조각은 거의 늘 미리보기 때와 같은 글자다. 그래서 알아볼 값
넷이 앞선 읽기에서 다 받은 조각과 같으면 그 글자를 쓰고, 어디에도 없는 조각만 다시 받으라고 한다. 앞선 읽기의 답은 조각을 빌려
줄 뿐 이번 읽기의 답으로 치지 않는다 — 이번 읽기에서 부르지 않은 작업을 예전 답으로 메우면 낡은 값이 지금 값이 된다.
"""

from __future__ import annotations

import json
import re
import zlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Mapping

from change_core.money import money_text
from erp_read import AdjustPage, PairRead, parse_adjust_page, parse_price_page
from price_model import ERP_MAX_DAYS, FIELDS, WEEKDAYS, day_windows, decode_step, iso_day

READ_SPAN = 186                      # readPair 한 번의 기간 — 달마다 달력 칸을 보므로(판매일 확인) 여섯 달 남짓으로 끊어 45초 안에
# 페이지가 두는 조각 수(stay_price.js 의 KEEP_BODIES). 읽기는 readPair · readReserved 를 다 부른 뒤에 조각을 받으므로(take),
# 한 번의 읽기가 이보다 많은 조각을 만들면 앞 조각이 밀려나 받을 수 없다 — 그것이 읽기 한 번이 덮을 수 있는 크기다.
PAGE_KEEPS = 40
PROBE_FIELDS = ("hotel", "offer", "rooms", "ratePlans", "from", "to", "weekdays", "occupancy", "nights")
OPS = {"bulk": "applyBulk", "cell_edit": "applyCell"}


class BrowserError(ValueError):
    """브라우저의 답이 물은 것과 맞지 않거나, 더 물어도 답을 얻을 수 없다."""


def ask_sum(value: Mapping) -> str:
    """물은 값의 지문 — `no` 를 뺀 값을 키 정렬 JSON 으로 적은 것의 CRC-32(페이지의 `askedOf`·`canon`·`crc32` 와 같다)."""
    text = json.dumps({name: item for name, item in value.items() if name != "no"}, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    return f"{zlib.crc32(text.encode('utf-8')):08x}"


DEFAULT_SIZE = 800                   # stayPrice.take 의 기본 쪽 크기(도구가 보이는 글자 수) — 도구는 1,000자쯤에서 자른다
MIN_SIZE = 200


class CutAnswer(BrowserError):
    """도구가 잘라 버린 답이 있다. `refetch` 는 다시 받을 쪽 — `stayPrice.take(id, at, size)` 에 그대로 넣는다."""

    def __init__(self, message: str, refetch: list[dict]):
        super().__init__(message)
        self.refetch = refetch


def _clue(text: str) -> dict:
    """잘린 답의 앞부분에서 무엇의 답이었는지(op · id · at · size)를 줍는다 — 페이지는 이 칸들을 답의 앞에 둔다."""
    def grab(name: str, pattern: str):
        found = re.search(r'"%s"\s*:\s*%s' % (name, pattern), text)
        return found.group(1) if found else None
    at, size = grab("at", r"(\d+)"), grab("size", r"(\d+)")
    return {"op": grab("op", r'"([^"]*)"'), "id": grab("id", r'"([^"]*)"'), "at": None if at is None else int(at),
            "size": None if size is None else int(size)}


def answers(results: Iterable) -> tuple[list[dict], list[dict]]:
    """답 목록 → (온전한 답, 잘린 답의 단서). 글자로 들어온 답은 도구가 보인 그대로다 — `[TRUNCATED]` 가 붙었거나
    JSON 이 닫히지 않았으면 잘린 것이다. 시작하지 않은 답(`started: false` — 아무것도 하지 않았다)은 없는 답으로 친다."""
    whole, cut = [], []
    for item in results:
        if isinstance(item, Mapping):
            if item.get("started") is not False:
                whole.append(dict(item))
            continue
        text = str(item)
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict) and "[TRUNCATED]" not in text:
            if data.get("started") is not False:
                whole.append(data)
        else:
            cut.append(_clue(text))
    return whole, cut


def _smaller(size: int | None) -> int:
    return max(MIN_SIZE, (size or DEFAULT_SIZE) * 3 // 4)


def fnv1a(data: bytes) -> str:
    """조각을 알아보는 두 번째 값 — FNV-1a 32비트(페이지의 `fnv1a` 와 같다). 셈법이 CRC-32 와 달라 둘이 함께 맞으면 같은 글자다."""
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return f"{value:08x}"


def _identity(meta: Mapping) -> tuple:
    """조각의 알아볼 값 — 글자 수 · 바이트 수 · CRC-32 · FNV-1a. 넷이 같으면 같은 글자로 친다."""
    return int(meta["chars"]), int(meta["bytes"]), str(meta["crc32"]), str(meta.get("fnv"))


def _body_meta(result: Mapping) -> Mapping | None:
    return result.get("body") if result.get("op") != "take" and result.get("ok") else None


def _pieces(whole: Iterable[Mapping]) -> dict[str, dict[int, Mapping]]:
    """take 답 → 조각 id 마다 자리 → 쪽. 같은 자리의 쪽이 두 번이면 앞이 같아야 하고 긴 쪽을 쓴다."""
    pieces: dict[str, dict[int, Mapping]] = {}
    for result in whole:
        if result.get("op") != "take":
            continue
        if not result.get("ok"):
            raise BrowserError(f"조각 한 쪽을 받지 못했습니다: {result.get('error')}")
        at, text = int(result["at"]), str(result["text"])
        if int(result["next"]) != at + len(text):
            raise BrowserError(f"조각 {result['id']} 의 {at}번째 자리 쪽이 스스로 말하는 길이와 다릅니다")
        seen = pieces.setdefault(str(result["id"]), {}).get(at)
        if seen is not None:
            short, long_ = sorted((str(seen["text"]), text), key=len)
            if not long_.startswith(short):
                raise BrowserError(f"조각 {result['id']} 의 {at}번째 자리 쪽이 두 번 왔는데 서로 다릅니다")
            if len(text) <= len(str(seen["text"])):
                continue
        pieces[str(result["id"])][at] = result
    return pieces


def _join(meta: Mapping, got: Mapping[int, Mapping]) -> tuple[str | None, int]:
    """쪽을 0 부터 next 를 따라 end 까지 잇는다 → `(글자, 끝 자리)`. 빈 자리가 있으면 `(None, 그 자리)`. 이은 글자의 알아볼
    값이 답과 다르면 BrowserError — 다른 조각의 쪽이 섞였거나 잘못 옮겨 적었다."""
    parts, pos, end = [], 0, int(meta["chars"])
    while pos < end:
        piece = got.get(pos)
        if piece is None:
            return None, pos
        if (piece.get("end"), piece.get("bytes"), piece.get("crc32")) != (end, meta["bytes"], meta["crc32"]):
            raise BrowserError(f"조각 {meta['id']} 의 쪽들이 말하는 크기·검사값이 답과 다릅니다")
        parts.append(str(piece["text"]))
        pos = int(piece["next"])
    text = "".join(parts)
    data = text.encode("utf-8")
    if len(data) != meta["bytes"] or f"{zlib.crc32(data):08x}" != meta["crc32"] or fnv1a(data) != meta.get("fnv"):
        raise BrowserError(f"조각 {meta['id']} 을 이어 보니 바이트 수나 CRC-32 · FNV-1a 가 맞지 않습니다 — 쪽을 다시 받아야 합니다")
    return text, pos


def attach_bodies(results: Iterable, earlier: Iterable = ()) -> list[dict]:
    """답 목록(읽기 답과 take 답, 잘린 답의 글자가 섞여 있다) → 읽기 답마다 조각을 푼 답. take 답은 빠진다. 푼 답에는 `body`
    가 남지 않아 한 번 더 지나도 그대로다.

    조각의 글자는 (1) 그 조각의 쪽을 이은 것, 아니면 (2) 알아볼 값 넷이 같은 다 받은 조각 — 이번 답들이나 앞선 읽기의 답들
    (`earlier`)에서 — 이다. 어디에도 없으면 CutAnswer 로 그 조각의 빈 자리와 크기를 댄다(그 자리의 쪽이 잘려 왔으면 더 작은
    크기). 이번 조각의 쪽이 서로 어긋나거나 이은 글자가 알아볼 값과 다르면 BrowserError. 앞선 읽기에서 그렇게 어긋난 조각은
    빌리지 않을 뿐이다. 풀린 body 의 물음(`asked`)은 답의 지문(`ask`)과 맞아야 한다.
    """
    whole, cuts = answers(results)
    for clue in cuts:
        if clue["op"] not in ("take", None) or (clue["op"] is None and clue["id"] is None):
            raise BrowserError(f"{clue['op'] or '어떤 작업'} 의 답이 잘렸습니다(도구는 1,000자쯤에서 자릅니다) — "
                               f"stayPrice.last() 로 다시 받거나 같은 작업을 다시 부릅니다")
    before = answers(earlier)[0]
    pieces = _pieces(whole + before)
    held: dict[tuple, str] = {}
    for result in before:
        meta = _body_meta(result)
        if meta is not None:
            try:
                text, _end = _join(meta, pieces.get(str(meta["id"]), {}))
            except BrowserError:
                continue
            if text is not None:
                held[_identity(meta)] = text
    joined: dict[int, tuple[str | None, int]] = {}
    for index, result in enumerate(whole):
        meta = _body_meta(result)
        if meta is not None:
            joined[index] = _join(meta, pieces.get(str(meta["id"]), {}))
            if joined[index][0] is not None:
                held[_identity(meta)] = joined[index][0]
    out, refetch = [], []
    for index, result in enumerate(whole):
        if result.get("op") == "take":
            continue
        meta = _body_meta(result)
        if meta is None:
            out.append(result)
            continue
        text, pos = joined[index]
        text = text if text is not None else held.get(_identity(meta))
        if text is None:
            cut = next((clue for clue in cuts if clue["id"] == str(meta["id"]) and clue["at"] == pos), None)
            refetch.append({"id": str(meta["id"]), "at": pos, "size": _smaller(cut["size"]) if cut else DEFAULT_SIZE})
            continue
        body = json.loads(text)
        if body.get("op") != result.get("op") or ask_sum(body.get("asked") or {}) != result.get("ask"):
            raise BrowserError(f"조각 {meta['id']} 은 이 답의 물음에서 나온 것이 아닙니다")
        merged = {**result, **body}
        merged.pop("body", None)
        out.append(merged)
    if refetch:
        raise CutAnswer("받지 못했거나 잘린 쪽이 있습니다 — " + " · ".join(
            f"stayPrice.take('{item['id']}', {item['at']}, {item['size']})" for item in refetch) + " 로 받아 덧붙입니다", refetch)
    return out


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


def answers_for(results: Iterable, op: str) -> list:
    """답 목록에서 그 작업(`readPair` · `readReserved` · `look`)의 답과 조각(take) 답만 — 한 폴더에 섞여 있어도 나눈다.
    잘린 글자 답은 앞부분의 op 로 가른다."""
    out = []
    for item in results:
        if isinstance(item, Mapping):
            kind = item.get("op")
        else:
            try:
                data = json.loads(str(item))
            except ValueError:
                data = None
            kind = data.get("op") if isinstance(data, dict) else _clue(str(item))["op"]
        if kind in (op, "take", None):
            out.append(item)
    return out


def unanswered(calls: Iterable[Mapping], results: Iterable, op: str) -> list[dict]:
    """부를 값 가운데 그 작업의 답이 하나도 없는 것(지문 `ask` 로 짝짓는다)."""
    asked = {str(result.get("ask")) for result in answers(answers_for(results, op))[0] if result.get("op") == op}
    return [call for call in calls if ask_sum(call) not in asked]


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


@dataclass(frozen=True)
class Outcome:
    """저장 작업 답 하나의 뜻. `saved` 는 True 저장됨 · False 저장 안 됨 · "unknown" 단추는 눌렸고 저장됐는지 모름 ·
    None 시작하지 않음(지나가는 까닭으로 아무것도 누르기 전에 멈췄다 — `wait` 초 뒤 같은 값으로 다시 부른다)."""
    saved: bool | str | None
    note: str
    wait: int | None = None

    @property
    def started(self) -> bool:
        return self.saved is not None


def step_outcome(call: Mapping, result: Mapping) -> Outcome:
    """다른 작업·다른 번호·다른 값을 물은 답이면 BrowserError — 엉뚱한 단계에 적지 않는다."""
    if result.get("op") != call["op"] or result.get("no") != call["no"]:
        raise BrowserError(f"{call['no']}번 저장({call['op']})의 답이 아닙니다: {result.get('op')} {result.get('no')}번")
    if result.get("ask") != ask_sum(call["payload"]):
        raise BrowserError(f"{call['no']}번 저장의 답이 장부의 그 단계와 다른 값을 물었습니다")
    reason = result.get("error") or "저장하지 못했습니다"
    if result.get("started") is False and not result.get("pressed") and result.get("saved") in (None, False):
        return Outcome(None, reason, int(result.get("wait") or 5))
    if result.get("saved") is True:
        note = result.get("note") or "저장했습니다"
        return Outcome(True, note if result.get("ok") else f"{note} · {result.get('error')}")
    if result.get("saved") == "unknown":
        return Outcome("unknown", f"저장됐는지 알 수 없습니다 — 다시 읽어 값을 확인해야 합니다: {reason}")
    return Outcome(False, reason)
