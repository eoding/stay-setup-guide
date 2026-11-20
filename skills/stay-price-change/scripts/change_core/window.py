"""편집 창 하나를 통째로 다시 저장하는 화면(부가옵션 가격 줄 · 부과금)이 같이 쓰는 저장 한 걸음과 적용 뒤 견주기.

ERP 의 편집 창은 [저장] 할 때 창의 칸을 전부 보내고 서버는 받은 대로 덮어쓴다(빠진 칸은 비운다). 그래서 도우미는 창이 보낼 칸
전부(`Form` — [이름, 값] 쌍, 창의 차례 그대로)를 읽어 두고, 저장할 때 그 가운데 미리보기가 보인 금액 칸만 새 값으로 바꿔 보낸다
(`with_values`). 같은 이름의 칸이 여럿이면(부과금의 시간대 요율 줄) 몇 번째 칸인지(0 부터)로 짚는다. 페이지 쪽의 같은 걸음은
`stay_price.js` 의 `stayPageKit.fill` 이다 — 치기 전에 창이 읽은 칸과 같은지, 친 뒤에 짚은 칸만 바뀌었는지 본다.

    form_values(form, name) · form_value(form, name, what)   이름의 값들 · 하나뿐인 값
    with_values(form, edits)                                   짚은 칸만 바꾼 쌍(차례 그대로). 없는 칸을 짚으면 거절
    moved_since(ledger, change_id, then, now, unit, label_of)  적용 뒤 다시 읽은 값에서 그대로여야 할 것이 달라진 것
"""

from __future__ import annotations

from typing import Callable, Mapping

from .answers import BrowserError
from .items import MISSING_STATE, Reading, Refused
from .money import money_text

Form = tuple[tuple[str, str], ...]
Place = tuple[str, int]          # (칸 이름, 같은 이름 가운데 몇 번째 — 0 부터)


def form_values(form: Form, name: str) -> list[str]:
    return [value for key, value in form if key == name]


def form_value(form: Form, name: str, what: str) -> str:
    """하나뿐이어야 하는 칸의 값. 없거나 여럿이면 BrowserError — 창이 생각한 모양이 아니다."""
    values = form_values(form, name)
    if len(values) != 1:
        raise BrowserError(f"{what} 편집 창이 {name} 칸을 {len(values)}개 보냅니다 — 하나여야 합니다")
    return values[0]


def with_values(form: Form, edits: Mapping[Place, str]) -> Form:
    """편집 창이 보내는 쌍 가운데 `edits` 가 짚은 칸(이름, 몇 번째)만 그 값으로 바꾼 것 — 나머지는 그대로, 차례도 그대로.
    창에 없는 칸을 짚으면 거절한다(보내지 않을 값을 바꿨다고 적지 않게)."""
    seen: dict[str, int] = {}
    out = []
    for name, value in form:
        nth = seen.get(name, 0)
        seen[name] = nth + 1
        out.append((name, edits.get((name, nth), value)))
    missing = [f"{name} {nth + 1}번째" for name, nth in edits if nth >= seen.get(name, 0)]
    if missing:
        raise Refused(f"창에 없는 칸을 바꾸려 했습니다: {', '.join(missing)}")
    return tuple(out)


def _shown(value) -> str:
    return money_text(value) or "없음"


def moved_since(ledger, change_id: int, then: Reading, now: Reading, unit: Callable[[str], str] | None = None,
                label_of: Callable[[str, str], str] | None = None) -> list[dict]:
    """저장한 것 가운데 그대로여야 할 것이 달라진 것 — 저장 단위(`unit(항목 키)`, 주지 않으면 항목 하나)마다:
    넣지 않은 금액이 미리보기 때 값과 다른 것(장부 `untouched`), 창이 보내는 딸린 칸(`form.` 으로 시작)이 그 번호의 읽은 값(`then`)과
    다른 것, 그 단위에 미리보기 때 없던 항목이 생긴 것. 저장 한 번이 기록 하나를 통째로 다시 쓰는 화면에서, 저장이 바꾸라고 하지
    않은 곳을 건드리지 않았는지 본다. `label_of(키, 필드)` 는 금액 칸의 이름(주지 않으면 필드 이름)."""
    unit = unit or (lambda key: key)
    label_of = label_of or (lambda key, field: field)
    record = ledger.change(change_id)
    saved = {unit(row.item_key) for row in record.rows if row.written}
    moved = [dict(key=item.item_key, label=item.label,
                  what=f"{label_of(item.item_key, item.field)} {_shown(item.after)} → {_shown(item.seen)}")
             for item in ledger.untouched(change_id, now, unit)]
    for kind, key in sorted(set(then) | set(now)):
        if unit(key) not in saved:
            continue
        before, after = then.get((kind, key)), now.get((kind, key))
        if before is None and after is not None and after.state != MISSING_STATE:
            moved.append(dict(key=key, label=after.label, what="미리보기 때 없던 것이 생겼습니다"))
            continue
        if before is None or after is None or after.state == MISSING_STATE:
            continue
        for name in sorted(set(before.others) | set(after.others)):
            if name.startswith("form.") and before.others.get(name) != after.others.get(name):
                moved.append(dict(key=key, label=before.label,
                                  what=f"{name[5:]} 칸 {before.others.get(name, '없음')!r} → {after.others.get(name, '없음')!r}"))
    return moved
