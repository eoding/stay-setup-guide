"""기록 폴더의 파일 — 도우미 명령들이 같이 쓰는 파일 읽기 · 결과 파일 쓰기 · 페이지 자리 · 작업 폴더 · 답 폴더 · 앞선 읽기와
look 에서 조각 빌리기 · 계산 파일 지키기 · 세 도우미의 기록을 탭의 호텔로 좁힌 장부 목록.

기록 폴더는 장부가 있는 곳이다(`ledger.ledger_dir`). 담당자가 시킨 일 하나에 `작업/<YYYY-MM-DD HHMMSS>/`(new_work), 그 안의 look
답은 `look/`, 읽기마다 `읽기-1/` … 를 쓴다. 읽기 폴더는 아무도 미리 만들지 않는다 — 그 안에 쓰는 첫 명령(`read-calls --out`)이
만든다(write_out). 답 파일은 이름의 머리(`look-` · `pair-` · `line-` · `take-` …)로 알아본다 — 머리는 도우미마다 정한다.

장부 목록(listed)은 번호마다 그 번호를 쓴 도우미가 범위 한 줄을 만든다. 다른 도우미의 것은 같은 플러그인의 그 도우미 폴더에서
명령 모듈을 이름으로 불러(`described`) 만든다 — 목록을 만들 때만 부르므로, 이 패키지를 불러오는 것만으로는 도우미의 코드가 올라오지 않는다.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .answers import named
from .ledger import KIND_NAMES, Ledger, clock, ledger_dir

HELPERS = {"price_cell": ("stay-price-change", "price_change"), "addon_price": ("stay-addon-price-change", "addon_change"),
           "charge": ("stay-charge-change", "charge_change")}   # 항목 종류 → 그 기록을 쓰는 도우미의 스킬 폴더와 명령 모듈

WORK = "작업"   # 기록 폴더 안의 작업 폴더들 — 일 하나에 `작업/<YYYY-MM-DD HHMMSS>/`, 그 안의 읽기마다 `읽기-1/` …
LOOK = "look"   # 작업 폴더 안에서 look 답을 두는 폴더(SKILL.md 「준비」) — 다음 작업의 look 이 여기서 조각을 빌린다


def load(path: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"파일이 없습니다: {path}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON 을 읽지 못했습니다: {path} ({error})") from None


def page_path(hotel: str, name: str) -> Path:
    """기록 폴더의 새 페이지 자리 — `<날짜 시각> · <호텔> · <이름>.html`, 있으면 뒤에 (2) · (3) …"""
    safe = re.sub(r'[\\/:*?"<>|]', "_", hotel).strip() or "호텔"
    base = f"{datetime.now().strftime('%Y-%m-%d %H시%M분')} · {safe} · {name}"
    path, number = ledger_dir() / f"{base}.html", 2
    while path.exists():
        path, number = ledger_dir() / f"{base} ({number}).html", number + 1
    return path


def new_work() -> Path:
    """새 작업 폴더 `<기록 폴더>/작업/<YYYY-MM-DD HHMMSS>/` 를 그 안의 `look/` 과 함께 만들어 돌려준다 — 담당자가 시킨 일 하나(보기 ·
    바꾸기 · 되돌리기 · 이어서)에 하나. 같은 이름이 이미 있으면 뒤에 ` (2)` · ` (3)` …을 붙인다 — 앞선 일의 파일과 섞이지 않는다.
    `look/` 은 안내문의 첫 저장(look 답)이 가는 곳이다 — 도우미의 파일 도구가 없는 폴더를 만들지 못해도 막히지 않는다. 그 뒤의
    폴더(읽기 · 적용 답)는 그 안에 `--out` 으로 쓰는 명령(read-calls · calls)이 만든다."""
    base = ledger_dir() / WORK / clock()().strftime("%Y-%m-%d %H%M%S")
    number = 1
    while True:
        path = base if number == 1 else base.with_name(f"{base.name} ({number})")
        try:
            path.mkdir(parents=True)
        except FileExistsError:
            number += 1
            continue
        (path / LOOK).mkdir()
        return path


def answer_files(paths, prefixes: tuple[str, ...]) -> list[Path]:
    """답 파일 목록 — 파일은 그대로, 폴더는 그 안에서 이름이 `prefixes` 가운데 하나로 시작하는 .json·.txt 파일(이름순)."""
    files = []
    for path in map(Path, paths or ()):
        if path.is_dir():
            files += sorted(item for item in path.iterdir() if item.is_file() and item.name.startswith(prefixes)
                            and item.suffix in (".json", ".txt"))
        else:
            files.append(path)
    return files


def _first_value(text: str):
    """답 파일의 글 → 답. 온전한 JSON 이면 그것. JSON 하나가 온전히 닫힌 뒤에 도구가 붙인 글(탭 목록 같은 것)이 이어지면 그 JSON 만
    — 작업의 답은 그것이다. 닫히지 않은(잘린) 글은 그대로 글이다(change_core.answers 가 잘린 답으로 알아본다)."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    stripped = text.lstrip()
    try:
        value, end = json.JSONDecoder().raw_decode(stripped)
    except json.JSONDecodeError:
        return text
    return value if isinstance(value, (dict, list)) and stripped[end:].strip() else text


def load_results(paths, prefixes: tuple[str, ...]) -> list:
    """브라우저 답 파일들(폴더도 된다 — answer_files) — 파일 하나에 답 하나(객체) 또는 여럿(목록). 목록의 글자 항목, 그리고
    JSON 이 아닌 파일은 도구가 보인 그대로의 답이다(잘린 답일 수 있다 — change_core.answers.answers 가 알아본다). UTF-8 로 읽히지
    않는 바이트는 대체 글자로 읽는다 — 그런 파일은 답이 되지 못할 뿐 읽기를 막지 않는다. 답마다 그 파일 이름을 단다(answers.named —
    맞지 않는 쪽을 파일로 짚고, 다시 받은 쪽에 새 이름을 고른다)."""
    results = []
    for path in answer_files(paths, prefixes):
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            raise ValueError(f"파일이 없습니다: {path}") from None
        data = _first_value(text)
        results += [named(item, Path(path).name) for item in (data if isinstance(data, list) else [data])]
    return results


def calls_hotel(calls: dict) -> str:
    """읽기의 부를 값 파일(calls.json)이 부르는 호텔 번호 — 부를 값마다(파일 안의 목록마다의 항목) 같은 `hotel` 이 든다."""
    ids = {str((call.get("hotel") or {}).get("id")) for values in calls.values() if isinstance(values, list)
           for call in values if isinstance(call, dict)}
    if len(ids) != 1:
        raise ValueError(f"부를 값의 호텔이 하나가 아닙니다: {' · '.join(sorted(ids))}")
    return ids.pop()


def earlier_readings(hotel_id: str, own: Iterable[Path]) -> list[Path]:
    """기록 폴더의 읽기 폴더(`작업/<작업>/<읽기>/`) 가운데 같은 호텔을 읽은 것 — 그 폴더의 calls.json 이 그 호텔 번호를 부른다.
    이번 읽기의 폴더(`own` — 부를 값 파일과 답 파일 · 폴더가 있는 곳)는 뺀다. 읽지 못하는 calls.json 은 건너뛴다(빌려 줄 뿐이다).

    읽기 명령은 이 폴더들에서 다 받아 맞춰 본 조각만 빌린다. 이번 읽기의 답으로 치지 않는다(change_core.answers.attach_bodies)."""
    own_folders = {(path if path.is_dir() else path.parent).resolve() for path in own}
    found = []
    for calls in sorted((ledger_dir() / WORK).glob("*/*/calls.json")):
        if calls.parent.resolve() in own_folders:
            continue
        try:
            if calls_hotel(json.loads(calls.read_text(encoding="utf-8"))) == hotel_id:
                found.append(calls.parent)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return found


def lent_answers(calls_path: str, answer_paths, calls: dict, prefixes: tuple[str, ...]) -> list:
    """이번 읽기에 조각을 빌려 줄 답들 — 기록 폴더에서 같은 호텔을 읽은 앞선 읽기 폴더마다의 답 파일(earlier_readings)."""
    own = [Path(calls_path), *map(Path, answer_paths or ())]
    return load_results(earlier_readings(calls_hotel(calls), own), prefixes)


def lent_looks(results: list, answer_paths, prefixes: tuple[str, ...]) -> list:
    """이 look 에 조각을 빌려 줄 답들 — 기록 폴더의 다른 작업 폴더마다의 `look/` 가운데 같은 호텔을 본 것의 답 파일. 읽기가 앞선 읽기
    폴더에서 빌리는 것과 같다(lent_answers): 알아볼 값 넷이 같은 다 받은 조각만 쓰고, 이번 look 의 답으로 치지 않는다."""
    hotels = {str((result.get("hotel") or {}).get("id")) for result in results
              if isinstance(result, dict) and result.get("op") == "look"}
    own = {(path if path.is_dir() else path.parent).resolve() for path in map(Path, answer_paths or ())}
    lent = []
    for folder in sorted((ledger_dir() / WORK).glob(f"*/{LOOK}")):
        if not folder.is_dir() or folder.resolve() in own:
            continue
        answers = load_results([folder], prefixes)
        if any(isinstance(answer, dict) and answer.get("op") == "look" and str((answer.get("hotel") or {}).get("id")) in hotels
               for answer in answers):
            lent += answers
    return lent


def look_hotel(path: str) -> dict:
    """look 명령이 낸 파일의 호텔 `{id, name}` — 탭에 열린 호텔(페이지가 알아본 번호와 이름)."""
    data = load(path)
    hotel = data.get("hotel") if isinstance(data, dict) else None
    if not isinstance(hotel, dict) or not str(hotel.get("id") or "").strip():
        raise ValueError(f"look 명령이 낸 파일(hotel)이 아닙니다: {path}")
    return dict(id=str(hotel["id"]), name=str(hotel.get("name") or ""))


def _short_time(moment: str) -> str:
    """「11/21 10:05」 — 장부가 적은 시각 그대로(장부 · 읽은 시각은 이 컴퓨터의 시각대로 적혀 있다)."""
    when = datetime.fromisoformat(moment.replace("Z", "+00:00"))
    return f"{when.month}/{when.day} {when:%H:%M}"


def confirm_line(entry: dict) -> str:
    """장부 목록의 한 줄을 담당자에게 확인받을 때 읽어 주는 말 — 「장부 3번 · 11/21 10:05 적용 · <범위>」. 저장해 둔 상태는 그 값을
    ERP 에서 읽은 때와 「저장」, 적용을 시작하지 않은 미리보기는 만든 때와 「미리보기」, 적용 중이거나 멈춘 변경은 시작한 때와 그 말.
    세 도우미가 같은 말로 묻는다(되돌리기 · 견주기의 「이것 맞나요?」)."""
    if entry["kind"] == "snapshot":
        moment, word = entry["read_at"], "저장"
    elif entry.get("applied_at"):
        moment, word = entry["applied_at"], "적용"
    elif entry["status"] in ("applying", "stopped"):
        moment, word = entry["created_at"], "적용하다 멈춤" if entry["status"] == "stopped" else "적용 중"
    else:
        moment, word = entry["created_at"], "미리보기"
    return f"장부 {entry['id']}번 · {_short_time(moment)} {word} · {entry['scope']}"


def record_progress(entry: dict, unit: str) -> str:
    """장부 목록의 한 줄(`Ledger.list_changes`)이 어디까지 갔는지 — 세 도우미의 범위 한 줄(`scope`, 그래서 `line` 도)이 끝에 같은 말로
    단다(`unit` 은 그 도우미가 세는 것 — 칸 · 줄). 멈췄거나 적용 중이면 저장 몇 번 중 몇 번, 되돌렸으면 「모두 되돌림 a/b칸 (장부 N번)」
    · 「일부 되돌림 a/b칸 (장부 N번) · 나머지 c칸은 넣은 값 그대로」 — 읽어 주어도 넣은 값이 살아 있는 것처럼 들리지 않는다. 저장할
    것이 없는 미리보기면 그렇다고. 그 밖(미리보기 · 다 적용 · 저장해 둔 상태)은 상태(`status`)가 말한다 — 빈 글자."""
    status, steps, saved = entry["status"], entry["steps"], entry["saved_steps"]
    by = ", ".join(f"{number}번" for number in entry["undone_by"])
    done, back = entry["written"], entry["rolled_back"]
    if status == "stopped":
        return f"저장 {steps}번 중 {saved}번 하고 멈춤"
    if status == "applying":
        return f"저장 {steps}번 중 {saved}번 함 · 적용 중"
    if status == "rolled_back":
        return f"모두 되돌림 {back:,}/{done:,}{unit} (장부 {by})"
    if status == "partly_rolled_back":
        return f"일부 되돌림 {back:,}/{done:,}{unit} (장부 {by}) · 나머지 {done - back:,}{unit}은 넣은 값 그대로"
    if status == "empty":
        return "저장할 것 없음"
    return ""


Describe = Callable[[Ledger, dict], dict]   # 장부 목록의 한 줄(list_changes) → 범위 한 줄(`scope`)을 단 줄 — 도우미마다 하나


def describer(kind: str) -> Describe:
    """그 종류의 기록을 쓰는 도우미의 `described` — 같은 플러그인의 그 스킬 폴더(`HELPERS`)에서 명령 모듈을 이름으로 불러온다. 모듈
    이름은 도우미마다 달라 서로 가리지 않는다."""
    folder, module = HELPERS[kind]
    scripts = str(Path(__file__).resolve().parents[3] / folder / "scripts")
    if scripts not in sys.path:
        sys.path.append(scripts)
    return importlib.import_module(module).described


def _kindless(ledger: Ledger, entry: dict) -> dict:
    """항목 줄이 없어 종류를 모르는 번호(ledger._kind_of) — 담당자가 한 말과 어디까지 갔는지만."""
    return dict(entry, scope=" · ".join(part for part in ("항목 없음", f"「{entry['sentence']}」", record_progress(entry, "개")) if part))


def listed(ledger: Ledger, kind: str, own: Describe, change_id: int | None = None) -> list[dict]:
    """장부 목록의 줄마다(`change_id` 를 주면 그 번호만) 그 번호를 쓴 도우미가 만든 범위 한 줄(`scope`)과 그 도우미(`helper`)를 단다 —
    부르는 도우미(`kind`)의 줄은 `own` 이, 다른 두 도우미의 줄은 그 도우미의 `described` 가 만든다. 그래서 어느 도우미에 물어도 같은
    번호는 같은 줄이다. 종류로 연 장부면 그 종류의 번호만 나온다(check · rollback 의 범위). 요청 원문은 싣지 않는다."""
    out = []
    for entry in ledger.list_changes(change_id):
        found = entry["item_kind"]
        describe = own if found == kind else _kindless if found is None else describer(found)
        entry = describe(ledger, entry)
        entry["helper"] = KIND_NAMES.get(found)
        del entry["request"]
        out.append(entry)
    return out


def hotel_list(ledger_path: Path, entries: list[dict], look: str | None, every: bool) -> dict:
    """장부 목록의 답 — 탭에 열린 호텔(`look`, look 명령이 낸 파일)의 번호만. `every` 면 그 뒤에 다른 호텔의 번호도 싣는다(탭의
    호텔이 먼저, 저마다 새것부터). 둘 다 없으면 거절한다 — 다른 호텔의 기록은 담당자가 청할 때만 본다. `others` 는 싣지 않은
    다른 호텔의 번호 수다. 줄마다 확인받을 때 읽어 주는 말(`line` — confirm_line)을 단다."""
    if look is None and not every:
        raise ValueError("list 에는 --look(탭에 열린 호텔 — look 명령이 낸 파일)을 줍니다. 다른 호텔의 기록까지 보려면 --all 을 더합니다")
    hotel = look_hotel(look) if look else None
    entries = [dict(entry, line=confirm_line(entry)) for entry in entries]
    mine = [entry for entry in entries if hotel is not None and str(entry["hotel_id"]) == hotel["id"]]
    rest = [entry for entry in entries if hotel is None or str(entry["hotel_id"]) != hotel["id"]]
    return dict(ledger=str(ledger_path), hotel=hotel, changes=mine + rest if every else mine, others=0 if every else len(rest))


def _out_folder(out) -> Path | None:
    """`--out` 의 폴더가 없으면 그 폴더, 있으면 None. 기록 폴더 밖이면서 없으면 거절한다 — 밖에는 아무것도 몰래 만들지 않는다."""
    folder = Path(out).resolve().parent
    if folder.is_dir():
        return None
    records = ledger_dir().resolve()
    if not folder.is_relative_to(records):
        raise ValueError(f"쓸 파일의 폴더가 없습니다: {folder} — 기록 폴더({records}) 밖에는 폴더를 만들지 않습니다. 작업 폴더(`work` 의 "
                         "답) 안의 경로를 주거나, 이미 있는 폴더를 줍니다")
    return folder


def check_out(out: str | None) -> None:
    """무엇이든 셈하거나 장부에 적기 전에 — `--out` 이 쓸 수 없는 자리(기록 폴더 밖의 없는 폴더)면 거절한다. 만들지는 않는다."""
    if out:
        _out_folder(out)


def write_out(path, text: str) -> Path:
    """명령의 결과 파일(`--out` · 페이지)을 쓴다. 기록 폴더 안이면 없는 폴더(`<작업>/읽기-2/` …)를 만들며 쓰고, 밖의 없는 폴더는
    만들지 않고 거절한다(밖의 있는 폴더에는 쓴다)."""
    folder = _out_folder(path)
    if folder is not None:
        folder.mkdir(parents=True, exist_ok=True)
    path = Path(path)
    path.write_text(text, encoding="utf-8")
    return path


def fresh_record(out: str | None, replaces: int | None, record: bool, name: str) -> None:
    """계산 파일(plan · rollback · restore · sheet-check …)은 기록이라 덮어쓰지 않는다 — 다시 계산하면 새 이름(`<name>-2.json` …)에
    쓰고, 장부에 적는 계산이면 `--replaces` 로 앞 번호를 댄다. 무엇이든 셈하거나 장부에 적기 전에 본다."""
    if out and Path(out).exists():
        raise ValueError(f"이미 있는 파일입니다: {out} — 계산 파일은 기록이라 덮어쓰지 않습니다. 다시 계산한 것은 새 이름"
                         f"({name}-2.json · {name}-3.json …)으로 씁니다")
    if replaces is not None and not record:
        raise ValueError("--replaces 는 장부에 적을 때(--record)만 줍니다")
