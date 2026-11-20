"""기록 폴더의 파일 — 도우미 명령들이 같이 쓰는 파일 읽기 · 페이지 자리 · 답 폴더 · 앞선 읽기에서 조각 빌리기 · 계산 파일 지키기.

기록 폴더는 장부가 있는 곳이다(`ledger.ledger_dir`). 담당자가 시킨 일 하나에 `작업/<YYYY-MM-DD HHMMSS>/`, 그 안의 읽기마다
`읽기-1/` … 를 쓴다. 답 파일은 이름의 머리(`look-` · `pair-` · `line-` · `take-` …)로 알아본다 — 머리는 도우미마다 정한다.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .answers import named
from .ledger import ledger_dir

WORK = "작업"   # 기록 폴더 안의 작업 폴더들 — 일 하나에 `작업/<YYYY-MM-DD HHMMSS>/`, 그 안의 읽기마다 `읽기-1/` …


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
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = text
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


def fresh_record(out: str | None, replaces: int | None, record: bool, name: str) -> None:
    """계산 파일(plan · rollback · restore)은 기록이라 덮어쓰지 않는다 — 다시 계산하면 새 이름(`<name>-2.json` …)에 쓰고
    `--replaces` 로 앞 번호를 댄다. 무엇이든 셈하거나 장부에 적기 전에 본다."""
    if out and Path(out).exists():
        raise ValueError(f"이미 있는 파일입니다: {out} — 다시 계산한 미리보기는 새 이름({name}-2.json · {name}-3.json …)으로 씁니다")
    if replaces is not None and not record:
        raise ValueError("--replaces 는 장부에 적을 때(--record)만 줍니다")
