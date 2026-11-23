#!/usr/bin/env python3
"""loader_identity.py — 올리개(`page/stay_price_loader.js`)의 `INSTALLED` 를 디스크의 일곱 파일로 다시 적는다.

올리개는 설치된 일곱 파일(러너의 `stay_helper.js` · `stay_boot.js`, 이 스킬의 `stay_price.js` · `stay_price_season.js`, 부가옵션 가격 스킬의
`stay_addon_price.js`, 부과금 스킬의 `stay_charge.js`, 프로모션 할인 스킬의 `stay_promotion.js`)의 알아볼 값을 안다. 그 값과 다른
파일은 올리지도(`load`) 다시 실행하지도(`again`) 않는다. 일곱 파일 가운데 하나라도 고치면 이 스킬 폴더에서 이 명령을 한 번 부른다:

    python3 scripts/loader_identity.py

알아볼 값은 줄 끝을 \\n 으로 맞춘 UTF-8 의 바이트 수 · CRC-32 · FNV-1a 다(올리개의 `identity` 와 같은 셈).
`tests/test_loader_identity.py` 가 올리개의 값과 이 셈을 견준다.
"""

from __future__ import annotations

import re
import sys
import zlib
from pathlib import Path

from change_core.answers import fnv1a

SCRIPTS = Path(__file__).resolve().parent
LOADER = SCRIPTS / "page" / "stay_price_loader.js"
RUNNER = SCRIPTS.parent.parent / "stay-setup-run" / "scripts"
ADDON = SCRIPTS.parent.parent / "stay-addon-price-change" / "scripts" / "page"
CHARGE = SCRIPTS.parent.parent / "stay-charge-change" / "scripts" / "page"
PROMOTION = SCRIPTS.parent.parent / "stay-promotion-change" / "scripts" / "page"
FILES = {"stay_helper.js": RUNNER / "stay_helper.js", "stay_boot.js": RUNNER / "stay_boot.js",
         "stay_price.js": SCRIPTS / "page" / "stay_price.js", "stay_addon_price.js": ADDON / "stay_addon_price.js",
         "stay_charge.js": CHARGE / "stay_charge.js", "stay_promotion.js": PROMOTION / "stay_promotion.js",
         "stay_price_season.js": SCRIPTS / "page" / "stay_price_season.js"}
BLOCK = re.compile(r"^  var INSTALLED = \{\n(.*?)\n  \};$", re.S | re.M)
ENTRY = re.compile(r"'([\w.]+)': \{ bytes: (\d+), crc32: '([0-9a-f]{8})', fnv: '([0-9a-f]{8})' \}")


def identity(data: bytes) -> dict:
    data = data.replace(b"\r\n", b"\n")
    return {"bytes": len(data), "crc32": f"{zlib.crc32(data):08x}", "fnv": fnv1a(data)}


def installed() -> dict[str, dict]:
    """디스크의 일곱 파일의 알아볼 값."""
    return {name: identity(path.read_bytes()) for name, path in FILES.items()}


def written(loader: Path = LOADER) -> dict[str, dict]:
    """올리개에 적힌 값."""
    found = BLOCK.search(loader.read_text(encoding="utf-8"))
    if not found:
        raise ValueError(f"{loader.name} 에서 `var INSTALLED = {{ … }};` 를 찾지 못했습니다")
    return {name: {"bytes": int(size), "crc32": crc, "fnv": fnv} for name, size, crc, fnv in ENTRY.findall(found.group(1))}


def rewrite(loader: Path = LOADER) -> list[str]:
    """올리개의 값을 디스크의 일곱 파일로 다시 적고, 값이 바뀐 파일 이름을 돌려준다(같으면 아무것도 쓰지 않는다)."""
    now, before = installed(), written(loader)
    lines = ",\n".join(f"    '{name}': {{ bytes: {item['bytes']}, crc32: '{item['crc32']}', fnv: '{item['fnv']}' }}"
                       for name, item in now.items())
    text = loader.read_bytes().decode("utf-8")
    loader.write_bytes(BLOCK.sub(lambda _: f"  var INSTALLED = {{\n{lines}\n  }};", text, count=1).encode("utf-8"))
    return [name for name in now if before.get(name) != now[name]]


if __name__ == "__main__":
    changed = rewrite()
    print(f"{LOADER.name}: " + (f"다시 적음 — {', '.join(changed)}" if changed else "일곱 파일 모두 이미 같습니다"))
    sys.exit(0)
