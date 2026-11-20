"""페이지 답 — 어딩 Stay 도우미의 페이지 모듈(`stayPrice` · `stayAddonPrice`)과 주고받는 답의 공통 부분.

브라우저 도구는 답을 1,000자쯤에서 자른다(`[TRUNCATED]`). 그래서 페이지는 작업의 답(JSON 으로 800자 안)에 `ask`(물은 값의
지문)와 `body`(id 와 그 글자를 알아볼 값 — 글자 수 · 바이트 수 · CRC-32 · FNV-1a)만 싣고, 조각은 `take(id, at, size)` 로 한 쪽씩
내준다. 쪽마다 제 검사값(`sum`)이 있어 이 모듈은 쪽을 하나씩 맞춰 보고, 맞는 쪽만 자리로 이어 바이트 수 · CRC-32 · FNV-1a 가
모두 맞을 때만 쓴다 — 잘리거나 잘못 옮겨 적은 쪽이 틀린 값이 되지 않고, 그 쪽 하나만 다시 받으면 된다. 잘린 답(글자 그대로
넣는다)과 틀린 쪽은 파일로 짚고, 어느 쪽을 어떤 크기로 어디까지 받아 어느 새 이름에 둘지 말한다(CutAnswer.refetch).

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


class Answer(dict):
    """답 하나(JSON 객체). `file` 은 그 답이 든 파일의 이름이다(모르면 빈 글자) — 다시 받을 쪽을 말할 때 파일로 짚는다."""
    file = ""


class Shown(str):
    """도구가 보인 그대로의 답 글자(JSON 이 아니거나 잘렸을 수 있다). `file` 은 Answer 와 같다."""
    file = ""


def named(item, file: str):
    """답 하나에 파일 이름을 단다 — 객체는 Answer, 글자는 Shown 으로. 그 밖의 값은 그대로다."""
    if isinstance(item, Mapping):
        out = Answer(item)
    elif isinstance(item, str):
        out = Shown(item)
    else:
        return item
    out.file = file
    return out


def answers(results: Iterable, latest: bool = False) -> tuple[list[dict], list[dict]]:
    """답 목록 → (온전한 답, 잘린 쪽의 단서). 글자로 들어온 답은 도구가 보인 그대로다 — `[TRUNCATED]` 가 붙었거나
    JSON 이 닫히지 않았으면 잘린 것이다. 답이 아닌 것은 뺀다: 시작하지 않은 답(`started: false` — 아무것도 하지 않았다),
    작업이 도는 중에 받은 stayPrice.last()(`{running}`), 그리고 잘린 읽는 작업의 답(어느 물음의 답인지 모른다 — 그 물음은 답이
    없는 것으로 남아 last() 로 받거나 다시 부르라는 말이 나온다). 잘린 take 답은 다시 받을 쪽의 단서가 된다(`file` · 도구가
    잘랐는지 `truncated`). `latest` 면 같은 물음의 답이 여럿일 때 가장 늦게 끝난 것만 남긴다(_latest — 이번 읽기의 답. 앞선
    읽기의 답은 조각만 빌려 주므로 모두 둔다)."""
    whole, cut = [], []
    for item in results:
        file = getattr(item, "file", "")
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
                whole.append(named(data, file))
            continue
        clue = _clue(text)
        if clue["op"] == "take" or (clue["op"] is None and clue["id"] is not None):
            cut.append(dict(clue, file=file, truncated="[TRUNCATED]" in text))
    return (_latest(whole) if latest else whole), cut


def _smaller(size: int | None) -> int:
    return max(MIN_SIZE, (size or DEFAULT_SIZE) * 3 // 4)


def fnv1a(data: bytes) -> str:
    """조각을 알아보는 두 번째 값 — FNV-1a 32비트(페이지의 `fnv1a` 와 같다). 셈법이 CRC-32 와 달라 둘이 함께 맞으면 같은 글자다."""
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return f"{value:08x}"


def page_sum(body_id: str, at: int, end: int, text: str) -> str:
    """쪽 하나의 검사값 — `조각 id:자리:전체 길이:글자` 의 CRC-32(페이지 take 의 `sum` 과 같은 셈). 쪽마다 따로 맞춰 보므로
    잘못 옮겨 적은 쪽 하나를 그 쪽으로 짚는다."""
    return f"{zlib.crc32(f'{body_id}:{at}:{end}:{text}'.encode('utf-8')):08x}"


def _identity(meta: Mapping) -> tuple:
    """조각의 알아볼 값 — 글자 수 · 바이트 수 · CRC-32 · FNV-1a. 넷이 같으면 같은 글자로 친다."""
    return int(meta["chars"]), int(meta["bytes"]), str(meta["crc32"]), str(meta.get("fnv"))


def _units(text: str) -> int:
    """페이지(JS)가 세는 글자 수 — UTF-16 단위. 자리(at · next · end)와 머리의 chars 가 이 수다."""
    return len(text.encode("utf-16-le")) // 2


def _identity_of(text: str) -> tuple:
    """이은 글자 자체의 알아볼 값 — 머리(`_identity`)와 같은 모양."""
    data = text.encode("utf-8")
    return _units(text), len(data), f"{zlib.crc32(data):08x}", fnv1a(data)


RETAKE = "그 쪽을 다시 받아 새 파일로 저장합니다"
RECALL = "같은 값으로 그 작업을 다시 불러 답을 새 파일로 저장합니다(받아 둔 쪽은 그대로 씁니다)"


@dataclass(frozen=True)
class _Page:
    """맞춰 본 쪽 하나."""
    id: str
    at: int
    next: int
    end: int
    text: str


@dataclass(frozen=True)
class _Bad:
    """맞지 않는 쪽 하나 — 어느 조각 · 자리 · 파일 · 왜. `smaller` 면 도구가 잘랐으니 더 작은 크기(`size` 의 3/4)로 다시 받는다."""
    id: str
    at: int | None
    file: str
    why: str
    smaller: bool = False
    size: int | None = None


def _whole_number(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _check(result: Mapping) -> _Page | _Bad:
    """take 답 하나를 그 쪽만으로 맞춰 본다 — 칸이 있고, 다음 자리가 자리 + 글자 수이고, 검사값(sum)이 글자와 맞는다."""
    body_id, at = str(result.get("id")), _whole_number(result.get("at"))

    def bad(why: str, smaller: bool = False) -> _Bad:
        return _Bad(body_id, at, getattr(result, "file", ""), why, smaller, _whole_number(result.get("size")))

    if not result.get("ok"):
        error = str(result.get("error") or "실패")
        return bad(f"페이지가 이 쪽을 주지 못했습니다({error})", smaller="다른 size" in error)
    text, next_, end = result.get("text"), _whole_number(result.get("next")), _whole_number(result.get("end"))
    if not isinstance(text, str) or at is None or next_ is None or end is None:
        return bad("쪽의 칸(at · next · end · text)이 빠졌거나 숫자가 아닙니다")
    if "[TRUNCATED]" in text:
        return bad("도구가 이 쪽을 잘랐습니다", smaller=True)
    if "sum" not in result:
        return bad("쪽에 검사값(sum)이 없습니다 — 예전 판 페이지의 쪽입니다")
    if next_ != at + _units(text) or not 0 <= at < next_ <= end:
        return bad("옮겨 적은 글의 길이가 쪽이 말하는 길이와 다릅니다")
    if str(result["sum"]) != page_sum(body_id, at, end, text):
        return bad("옮겨 적은 글이 페이지가 준 것과 다릅니다")
    return _Page(body_id, at, next_, end, text)


@dataclass(frozen=True)
class _Joined:
    """한 조각의 맞는 쪽들을 이은 것. `text` 는 처음부터 끝(`end`)까지 이어지면 그 글자, 아니면 None. 이어지지 않으면 `gap` 은
    처음부터 따라갈 수 있는 가장 먼 자리(빈 곳), `until` 은 그 뒤로 끝까지 맞는 쪽이 이어지는 첫 자리(없으면 end)다."""
    text: str | None
    end: int
    gap: int
    until: int


def _join(pages: Iterable[_Page], end: int) -> _Joined:
    """맞는 쪽들을 0 부터 next 를 따라 end 까지 잇는다. 맞는 쪽은 어느 것이든 그 자리의 참 글자라 같은 자리에 여럿이면 아무거나 쓴다."""
    starts: dict[int, list[_Page]] = {}
    for page in pages:
        if page.end == end:
            starts.setdefault(page.at, []).append(page)
    came: dict[int, _Page | None] = {0: None}
    todo = [0]
    while todo:
        for page in starts.get(todo.pop(), ()):
            if page.next not in came:
                came[page.next] = page
                todo.append(page.next)
    if end in came:
        parts, pos = [], end
        while pos:
            page = came[pos]
            parts.append(page.text)
            pos = page.at
        return _Joined("".join(reversed(parts)), end, end, end)
    whole, grew = {end}, True
    while grew:
        grew = False
        for start, group in starts.items():
            if start not in whole and any(page.next in whole for page in group):
                whole.add(start)
                grew = True
    gap = max(came)
    return _Joined(None, end, gap, min(pos for pos in whole if pos > gap))


def _sorted_pages(results: Iterable[Mapping]) -> tuple[dict[str, list[_Page]], dict[str, list[_Bad]]]:
    """take 답 → 조각 id 마다 맞는 쪽 · 맞지 않는 쪽."""
    good: dict[str, list[_Page]] = {}
    bad: dict[str, list[_Bad]] = {}
    for result in results:
        if result.get("op") == "take":
            checked = _check(result)
            (good if isinstance(checked, _Page) else bad).setdefault(checked.id, []).append(checked)
    return good, bad


def _joined(good: Mapping[str, list[_Page]]) -> dict[str, _Joined]:
    """조각 id 마다 맞는 쪽을 이은 것 — 끝 자리는 쪽들이 말하는 것(맞는 쪽은 모두 같은 끝을 말한다)."""
    return {body_id: _join(pages, pages[0].end) for body_id, pages in good.items()}


def _lent(earlier: Iterable) -> dict[tuple, str]:
    """앞선 읽기의 맞는 쪽들로 처음부터 끝까지 이어지는 조각 — 이은 글자의 알아볼 값 → 글자. 앞선 읽기의 머리는 보지 않는다:
    이번 답의 머리와 알아볼 값 넷이 같은 글자만 빌리므로 그것이 검사다. 맞지 않는 쪽 · 빈 자리 · 읽지 못한 파일은 말없이
    건너뛴다 — 앞선 읽기는 빌려 줄 뿐, 그 안의 어긋난 것이 이번 읽기를 막지 않는다."""
    good, _bad = _sorted_pages(answers(earlier)[0])
    return {_identity_of(joined.text): joined.text for joined in _joined(good).values() if joined.text is not None}


def _body_meta(result: Mapping) -> Mapping | None:
    return result.get("body") if result.get("op") != "take" and result.get("ok") else None


def _which(result: Mapping) -> str:
    return getattr(result, "file", "") or f"{result.get('op')} 의 답"


def _save_prefix(body_id: str, names: set[str]) -> str:
    """다시 받는 쪽을 저장할 파일 이름의 앞 — 처음이면 `take-<id>-`, 그 조각의 파일이 이미 있으면 `take-<id>-<k>-`(k 는 2 부터
    아직 없는 수). 기록 폴더의 파일은 덮어쓰지 않으므로 다시 받은 쪽은 언제나 새 이름에 간다."""
    base = f"take-{body_id}-"
    if not any(name.startswith(base) for name in names):
        return base
    round_ = 2
    while any(name.startswith(f"{base}{round_}-") for name in names):
        round_ += 1
    return f"{base}{round_}-"


def _retake(meta: Mapping, joined: _Joined | None, bad: Mapping[str, list[_Bad]], names: set[str]) -> dict:
    """받을 쪽 하나 — `{id, at, size, until, save, bad}`. at 부터 받아 `<save><at>.json` 에 두고, 답의 next 가 until 보다 작으면
    next 로 이어 받는다. `bad` 는 그 사이 자리의 맞지 않는 쪽마다 `{file, at, why}`(다시 받는 까닭)."""
    body_id = str(meta["id"])
    joined = joined or _Joined(None, int(meta["chars"]), 0, int(meta["chars"]))
    named_ = [item for item in bad.get(body_id, ()) if item.at is not None and joined.gap <= item.at < joined.until]
    size = next((_smaller(item.size) for item in named_ if item.at == joined.gap and item.smaller), DEFAULT_SIZE)
    return {"id": body_id, "at": joined.gap, "size": size, "until": joined.until, "save": _save_prefix(body_id, names),
            "bad": [{"file": item.file, "at": item.at, "why": f"{item.why} — {RETAKE}"} for item in named_]}


def _say(item: Mapping) -> str:
    """받을 쪽 하나를 말로 — 부를 것 · 저장할 파일 · 이어 받을 데까지 · 다시 받는 까닭."""
    words = (f"stayPrice.take('{item['id']}', {item['at']}, {item['size']}) 의 답을 {item['save']}{item['at']}.json 에"
             f"(답의 next 가 {item['until']} 보다 작으면 take('{item['id']}', next) 를 {item['save']}<next>.json 에 이어서)")
    return words + "".join(f" [{bad['file'] or str(bad['at']) + '번째 자리 쪽'}: {bad['why']}]" for bad in item["bad"])


def _body_text(result: Mapping, meta: Mapping, joined: Mapping[str, _Joined], held: Mapping[tuple, str],
               bad: Mapping[str, list[_Bad]]) -> str | None:
    """읽기 답 하나의 조각 글자 — 그 조각의 맞는 쪽을 이은 것, 아니면 알아볼 값이 같은 다른 조각. 없으면 None(받을 쪽이 있다).
    답의 머리를 옮겨 적다 틀렸으면(쪽들이 말하는 것과 다르면) 그 답을 다시 받으라고 거절한다."""
    try:
        identity, body_id = _identity(meta), str(meta["id"])
    except (KeyError, TypeError, ValueError):
        raise BrowserError(f"{_which(result)} 의 조각 머리(body)를 읽지 못했습니다 — 옮겨 적다 틀렸습니다. {RECALL}") from None
    own = joined.get(body_id)
    if own is not None and (own.end != identity[0] or (own.text is not None and _identity_of(own.text) != identity)):
        raise BrowserError(f"{_which(result)} 의 조각 머리(body)가 페이지가 준 쪽들과 맞지 않습니다 — 그 답을 옮겨 적다 틀렸습니다. "
                           f"{RECALL}")
    text = own.text if own is not None and own.text is not None else held.get(identity)
    if text is None and any("페이지에 없습니다" in item.why for item in bad.get(body_id, ())):
        raise BrowserError(f"조각 {body_id} 이 페이지에 없습니다(페이지가 바뀌었거나 조각이 밀려났습니다) — 새 폴더로 읽기를 처음부터 "
                           "다시 합니다")
    return text


def attach_bodies(results: Iterable, earlier: Iterable = ()) -> list[dict]:
    """답 목록(읽기 답과 take 답, 잘린 답의 글자가 섞여 있다) → 읽기 답마다 조각을 푼 답. take 답은 빠진다. 푼 답에는 `body`
    가 남지 않아 한 번 더 지나도 그대로다.

    쪽은 하나씩 맞춰 본다(칸 · 길이 · 검사값 sum — _check). 같은 자리에는 맞는 쪽을 쓰고 맞지 않는 쪽은 무시한다. 조각의 글자는
    (1) 그 조각의 맞는 쪽을 처음부터 끝까지 이은 것, 아니면 (2) 알아볼 값 넷이 같은 다 받은 조각 — 이번 답들이나 앞선 읽기의
    답들(`earlier`, _lent)에서 — 이다. 어디에도 없으면 CutAnswer 로 받을 쪽(_retake)을 댄다: 빈 곳의 자리 · 크기 · 어디까지 이어
    받을지 · 새 파일 이름 · 그 사이의 맞지 않는 쪽과 까닭. 그래서 어떤 쪽을 몇 번 잘못 옮겨 적어도 그 쪽을 다시 받으면 읽기가
    끝난다. 답의 머리(body)가 맞는 쪽들과 다르면 BrowserError(그 답을 다시 받는다). 풀린 body 가 다른 물음(`asked` 의 지문이
    답의 `ask` 와 다름)의 것이면 그 답은 옮겨 적다 지문이 틀린 것이라 쓰지 않는다 — 그 물음은 답이 없는 것으로 남는다.
    """
    results = list(results)
    whole, cuts = answers(results, latest=True)
    good, bad = _sorted_pages(whole)
    for clue in cuts:
        if clue["id"] is not None:
            bad.setdefault(clue["id"], []).append(_Bad(clue["id"], clue["at"], clue["file"], "답이 잘렸거나 JSON 으로 닫히지 않았습니다",
                                                       clue["truncated"], clue["size"]))
    joined = _joined(good)
    held = {**_lent(earlier), **{_identity_of(item.text): item.text for item in joined.values() if item.text is not None}}
    names = {getattr(item, "file", "") for item in results}
    out, refetch = [], []
    for result in whole:
        if result.get("op") == "take":
            continue
        meta = _body_meta(result)
        if meta is None:
            out.append(result)
            continue
        text = _body_text(result, meta, joined, held, bad)
        if text is None:
            refetch.append(_retake(meta, joined.get(str(meta["id"])), bad, names))
            continue
        body = json.loads(text)
        if body.get("op") != result.get("op") or ask_sum(body.get("asked") or {}) != result.get("ask"):
            continue
        merged = {**result, **body}
        merged.pop("body", None)
        out.append(merged)
    if refetch:
        raise CutAnswer("받지 못했거나 잘렸거나 잘못 옮겨 적은 쪽이 있습니다 — " + " · ".join(map(_say, refetch)), refetch)
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
