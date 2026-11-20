"""시험용 — 페이지(`window.stayPrice`)가 돌려주는 답의 모양을 파이썬에서 만든다.

읽기 답은 작은 답 하나 + 조각을 글자 자리(at)로 나눠 담은 take 답들이다(`stay_price.js` 의 keep · take 와 같은 모양).
unittest 가 찾지 않도록 이름이 test_ 로 시작하지 않는다.
"""

import json
import zlib

from price_browser import ask_sum


def reply(op: str, asked: dict, keep: dict | None = None, pieces: int = 3, **fields) -> list[dict]:
    result = {"ok": True, "op": op, "ask": ask_sum(asked), **fields}
    if keep is None:
        return [result]
    text = json.dumps({"op": op, "asked": {k: v for k, v in asked.items() if k != "no"}, **keep}, ensure_ascii=False)
    size = max(1, -(-len(text) // pieces))
    data = text.encode("utf-8")
    meta = {"id": f"b{zlib.crc32(data):08x}", "chars": len(text), "bytes": len(data), "crc32": f"{zlib.crc32(data):08x}", "pieces": pieces}
    result["body"] = meta
    return [result] + [take(meta, text, at, size) for at in range(0, len(text), size)]


def take(meta: dict, text: str, at: int, size: int) -> dict:
    """`stayPrice.take(id, at, ...)` 의 답 — 글자 자리 at 부터 size 글자."""
    part = text[at:at + size]
    return {"op": "take", "ok": True, "id": meta["id"], "at": at, "size": 800, "next": at + len(part), "end": meta["chars"],
            "bytes": meta["bytes"], "crc32": meta["crc32"], "text": part}
