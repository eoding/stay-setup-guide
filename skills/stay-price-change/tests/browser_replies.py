"""시험용 — 페이지(`window.stayPrice`)가 돌려주는 답의 모양을 파이썬에서 만든다.

읽기 답은 작은 답 하나 + 조각을 글자 자리(at)로 나눠 담은 take 답들이다(`stay_price.js` 의 keep · take 와 같은 모양).
unittest 가 찾지 않도록 이름이 test_ 로 시작하지 않는다.
"""

import json
import zlib

from price_browser import ask_sum, fnv1a


def reply(op: str, asked: dict, keep: dict | None = None, pieces: int = 3, body_id: str | None = None, **fields) -> list[dict]:
    """작은 답 하나 + 조각을 `pieces` 쪽으로 나눈 take 답들. 페이지는 읽을 때마다 새 조각 id 를 붙인다 — 같은 글자를 다시 읽은
    답을 만들려면 `body_id` 를 달리 준다."""
    result = {"ok": True, "op": op, "ask": ask_sum(asked), **fields}
    if keep is None:
        return [result]
    # 페이지는 조각에 자기가 알아본 호텔을 싣는다 — 물은 호텔(없으면 시험 호텔)을 그대로, keep 의 hotel 이 있으면 그것으로
    body = {"op": op, "asked": {k: v for k, v in asked.items() if k != "no"}, "hotel": asked.get("hotel"), **keep}
    text = json.dumps(body, ensure_ascii=False)
    size = max(1, -(-len(text) // pieces))
    data = text.encode("utf-8")
    meta = {"id": body_id or f"b{zlib.crc32(data):08x}", "chars": len(text), "bytes": len(data),
            "crc32": f"{zlib.crc32(data):08x}", "fnv": fnv1a(data)}
    result["body"] = meta
    return [result] + [take(meta, text, at, size) for at in range(0, len(text), size)]


def take(meta: dict, text: str, at: int, size: int) -> dict:
    """`stayPrice.take(id, at, ...)` 의 답 — 글자 자리 at 부터 size 글자."""
    part = text[at:at + size]
    return {"op": "take", "ok": True, "id": meta["id"], "at": at, "size": 800, "next": at + len(part), "end": meta["chars"],
            "bytes": meta["bytes"], "crc32": meta["crc32"], "text": part}
