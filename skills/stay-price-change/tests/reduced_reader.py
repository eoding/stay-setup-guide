"""Node 시험(test_page_*.mjs)이 부르는 읽기 — 화면 조각 파일을 `erp_read.py` 로 읽어 JSON 으로 답한다.

    python3 tests/reduced_reader.py price|adjust <파일> [price|adjust <파일> …]

파일마다 {"file", "page"} 또는 {"file", "error"} 를 한 줄 목록으로 낸다. 금액(Decimal)은 글자로 낸다.
unittest 가 찾지 않도록 이름이 test_ 로 시작하지 않는다.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from erp_read import ParseError, parse_adjust_page, parse_price_page  # noqa: E402

READERS = {"price": parse_price_page, "adjust": parse_adjust_page}


def read(kind: str, path: str) -> dict:
    try:
        return dict(file=Path(path).name, page=asdict(READERS[kind](Path(path).read_text(encoding="utf-8"))))
    except ParseError as error:
        return dict(file=Path(path).name, error=str(error))


if __name__ == "__main__":
    args = sys.argv[1:]
    print(json.dumps([read(kind, path) for kind, path in zip(args[0::2], args[1::2])], ensure_ascii=False, default=str))
