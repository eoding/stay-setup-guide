"""명령 한 번의 끝마무리 — 세 도우미의 명령(`price_change.py` · `addon_change.py` · `charge_change.py`)이 같이 쓴다.

결과는 표준 출력에 JSON 으로, `--out` 을 주면 그 파일에도 쓴다(기록 폴더 안이면 없는 폴더를 만들며 — files.write_out). 파일에 쓰는
명령 가운데 짧은 답이 있는 것(`short`)은 표준 출력에 짧은 답만 낸다.

종료 코드는 셋이다. 0 됨 · 1 다른 값이 있음(답의 `same` 이 false) · 2 입력이나 순서가 맞지 않음. 2 는 언제나 표준 오류에 JSON 한
줄이다 — 파이썬의 Traceback 은 내지 않는다(failure):

- 명령이 거절한 것(ValueError · KeyError · TypeError 와 그 갈래 — 장부 · 계산 · 페이지 답의 오류)은 그 문장(받을 조각 `refetch` ·
  고를 줄 `choose` · 물을 것 `ask` 가 있으면 같이).
- 파일이나 장부를 읽거나 쓰지 못한 것(OSError · 장부가 잠김)은 어느 것인지와 까닭.
- 그 밖은 명령의 잘못(BUG) — 무슨 오류인지와 그 자리, 그리고 여기서 멈추고 그 글을 그대로 전하라는 문장.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import traceback
from pathlib import Path
from typing import Callable, Mapping

from . import files

EXTRAS = ("refetch", "choose", "ask")   # 거절에 딸려 가는 것 — 받을 조각 · 고를 줄(아동 밴드가 여럿) · 물을 것(아동이 든 값의 퍼센트)
BUG = ("여기서 멈추고, 이 글을 고치지 말고 그대로 담당자에게 전해 주세요(도우미를 만든 사람에게 보낼 글입니다). 다른 길로 돌아가 같은 "
       "일을 하지 않습니다.")
FILE_WHY = {FileNotFoundError: "없습니다", IsADirectoryError: "파일이 아니라 폴더입니다(파일 이름까지 줍니다)",
            NotADirectoryError: "경로 가운데 폴더가 아닌 파일이 있습니다", FileExistsError: "같은 이름의 파일이 있어 폴더를 만들지 못했습니다",
            PermissionError: "이 컴퓨터가 그 자리를 읽거나 쓰는 것을 막습니다(권한)"}


def run(args, short: Mapping[str, Callable[[dict], dict]]) -> int:
    """`args.handler(args)` 를 부르고 결과를 쓴다 — 종료 코드를 돌려준다. `--out` 의 자리는 셈하기 전에 본다(기록 폴더 밖의 없는
    폴더면 아무것도 셈하거나 장부에 적지 않고 거절한다)."""
    try:
        files.check_out(args.out)
        result = args.handler(args)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out and args.command != "render":
            path = files.write_out(args.out, text + "\n")
            if args.command in short:
                text = json.dumps(dict(out=str(path.resolve()), **short[args.command](result)), ensure_ascii=False, indent=2)
    except Exception as error:   # noqa: BLE001 — 어떤 실패도 JSON 한 줄로(Traceback 없이)
        print(json.dumps(failure(error), ensure_ascii=False), file=sys.stderr)
        return 2
    print(text)
    return 1 if result.get("same") is False else 0


def failure(error: Exception) -> dict:
    """실패 하나 → 표준 오류에 낼 JSON(`{"error": "…"}`)."""
    if isinstance(error, (ValueError, KeyError, TypeError)):
        payload = dict(error=str(error) if isinstance(error, ValueError) else f"입력 JSON 에 필요한 칸이 없습니다: {error}")
        payload.update({name: getattr(error, name) for name in EXTRAS if getattr(error, name, None)})
        return payload
    if isinstance(error, OSError):
        why = next((text for kind, text in FILE_WHY.items() if isinstance(error, kind)), error.strerror or str(error))
        where = error.filename or ""
        return dict(error=f"파일을 읽거나 쓰지 못했습니다{f': {where}' if where else ''} — {why}. 경로를 고쳐 같은 명령을 다시 합니다")
    if isinstance(error, sqlite3.OperationalError):
        return dict(error=f"장부를 열거나 적지 못했습니다 — {error}. 다른 창에서 도우미 명령이 돌고 있으면 끝난 뒤에 같은 명령을 다시 "
                          "합니다")
    frame = traceback.extract_tb(error.__traceback__)[-1] if error.__traceback__ else None
    place = f" — {Path(frame.filename).name} {frame.lineno}번 줄" if frame else ""
    return dict(error=f"명령에 잘못이 있습니다(예상하지 못한 오류 {type(error).__name__}: {error}{place}). {BUG}")
