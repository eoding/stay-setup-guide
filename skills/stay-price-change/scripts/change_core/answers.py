"""페이지 답 — 어딩 Stay 도우미의 페이지 모듈(`stayPrice` · `stayAddonPrice`)과 주고받는 답의 공통 부분.

브라우저 도구는 답을 1,000자쯤에서 자른다(`[TRUNCATED]`). 그래서 페이지는 작업의 답(JSON 으로 800자 안)에 `ask`(물은 값의
지문)와 `body`(id 와 그 글자를 알아볼 값 — 글자 수 · 바이트 수 · CRC-32 · FNV-1a)만 싣고, 조각은 `take(id, at, size)` 로 한 쪽씩
내준다. 이 모듈은 쪽을 자리로 이어 바이트 수 · CRC-32 · FNV-1a 가 모두 맞을 때만 쓴다 — 잘리거나 잘못 옮겨 적은 쪽이 틀린 값이
되지 않는다. 잘린 답(글자 그대로 넣는다)은 알아보고, 어느 쪽을 어떤 크기로 다시 받을지 말한다(CutAnswer.refetch).

한 변경은 세 번 읽는다(미리보기 · 적용 직전 · 적용 뒤). 적용 직전의 조각은 거의 늘 미리보기 때와 같은 글자다. 그래서 알아볼 값
넷이 앞선 읽기에서 다 받은 조각과 같으면 그 글자를 쓰고, 어디에도 없는 조각만 다시 받으라고 한다. 앞선 읽기의 답은 조각을 빌려
줄 뿐 이번 읽기의 답으로 치지 않는다 — 이번 읽기에서 부르지 않은 작업을 예전 답으로 메우면 낡은 값이 지금 값이 된다.

읽는 작업의 답과 저장 작업의 답은 저장 번호 `no` 로 가른다 — 저장 작업의 답에만 있다. 답을 잃은 읽는 작업은 `last()` 로 받아도,
같은 값으로 다시 불러도 된다(같은 물음의 답이 여럿이면 가장 늦게 끝난 것을 쓴다).

    ask_sum(value)                        물은 값의 지문(페이지와 같은 셈)
    answers(results, latest)              답 목록 → 온전한 답과 잘린 쪽의 단서
    attach_bodies(results, earlier)       읽기 답에 페이지에 남겨 둔 조각을 붙인다
    answers_for(results, op) · unanswered(calls, results, op)   한 작업의 답 · 답이 없는 부를 값
    reading_time(results, reads)          읽기 한 번이 ERP 를 읽은 시각
    step_outcome(call, result)            저장 작업 답 → Outcome(저장됨 · 안 됨 · 모름 · 시작 안 함)
"""

from __future__ import annotations

import json
import re
import zlib
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping


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


def _asked(result: Mapping) -> bool:
    """읽는 작업의 답 — 조각(take)의 답이 아니고 저장 번호(`no`)가 없다."""
    return result.get("op") != "take" and "no" not in result


def _finished(result: Mapping) -> tuple:
    """답의 끝난 시각(`doneAt`)으로 견줄 값 — 시각이 없거나 읽지 못하면 가장 이른 것으로 친다."""
    try:
        return 1, datetime.fromisoformat(str(result["doneAt"]).replace("Z", "+00:00")).timestamp()
    except (KeyError, TypeError, ValueError):
        return (0,)


def _latest(whole: list[dict]) -> list[dict]:
    """같은 읽는 작업 · 같은 물음(지문 `ask`)의 온전한 답이 둘 이상이면 끝난 시각이 가장 늦은 것 하나만(같으면 뒤의 것) — 답을 잃어
    stayPrice.last() 로 받은 답과 다시 불러 받은 답이 함께 저장돼도 읽기는 한 번의 답으로 묶인다."""
    chosen: dict[tuple, int] = {}
    for index, result in enumerate(whole):
        if _asked(result):
            key = (result.get("op"), result.get("ask"))
            if key not in chosen or _finished(result) >= _finished(whole[chosen[key]]):
                chosen[key] = index
    return [result for index, result in enumerate(whole)
            if not _asked(result) or chosen[(result.get("op"), result.get("ask"))] == index]


def answers(results: Iterable, latest: bool = False) -> tuple[list[dict], list[dict]]:
    """답 목록 → (온전한 답, 잘린 쪽의 단서). 글자로 들어온 답은 도구가 보인 그대로다 — `[TRUNCATED]` 가 붙었거나
    JSON 이 닫히지 않았으면 잘린 것이다. 답이 아닌 것은 뺀다: 시작하지 않은 답(`started: false` — 아무것도 하지 않았다),
    작업이 도는 중에 받은 stayPrice.last()(`{running}`), 그리고 잘린 읽는 작업의 답(어느 물음의 답인지 모른다 — 그 물음은 답이
    없는 것으로 남아 last() 로 받거나 다시 부르라는 말이 나온다). 잘린 take 답은 다시 받을 쪽의 단서가 된다. `latest` 면 같은
    물음의 답이 여럿일 때 가장 늦게 끝난 것만 남긴다(_latest — 이번 읽기의 답. 앞선 읽기의 답은 조각만 빌려 주므로 모두 둔다)."""
    whole, cut = [], []
    for item in results:
        if isinstance(item, Mapping):
            data, text = dict(item), None
        else:
            text = str(item)
            try:
                data = json.loads(text)
            except ValueError:
                data = None
        if isinstance(data, dict) and (text is None or "[TRUNCATED]" not in text):
            if data.get("started") is not False and not ("running" in data and "op" not in data):
                whole.append(data)
            continue
        clue = _clue(text)
        if clue["op"] == "take" or (clue["op"] is None and clue["id"] is not None):
            cut.append(clue)
    return (_latest(whole) if latest else whole), cut


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
    whole, cuts = answers(results, latest=True)
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


def reading_time(results: Iterable, reads: Iterable[str]) -> str:
    """읽기 한 번이 ERP 를 읽은 시각(지금 시각대의 ISO, 초까지) — 그 읽기에서 부른 읽는 작업(`reads`)의 온전한 답마다 페이지가
    적은 끝난 시각(`doneAt`) 가운데 가장 이른 것. 명령을 부른 때가 아니다(읽기가 끝나고 몇 분 뒤에 부를 수 있다). 15분 창도 이
    시각에서 잰다. 끝난 시각이 없는 답(예전 판 페이지의 답)이 하나라도 있으면 언제 읽었는지 모르므로 거절한다."""
    moments, reads = [], tuple(reads)
    for result in answers(results, latest=True)[0]:
        if result.get("op") not in reads or not result.get("ok"):
            continue
        if not result.get("doneAt"):
            raise BrowserError(f"{result['op']} 의 답에 끝난 시각(doneAt)이 없어 언제 읽었는지 모릅니다 — 예전 판 페이지의 답입니다. "
                               "도우미를 다시 올리고 새 읽기 폴더로 처음부터 읽습니다")
        try:
            moment = datetime.fromisoformat(str(result["doneAt"]).replace("Z", "+00:00"))
        except ValueError:
            raise BrowserError(f"{result['op']} 의 끝난 시각을 읽지 못했습니다: {result['doneAt']}") from None
        if moment.tzinfo is None:
            raise BrowserError(f"{result['op']} 의 끝난 시각에 시간대가 없습니다: {result['doneAt']}")
        moments.append(moment)
    if not moments:
        raise BrowserError("읽기 답이 하나도 없어 언제 읽었는지 모릅니다")
    return min(moments).astimezone().isoformat(timespec="seconds")


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
