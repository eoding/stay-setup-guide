"""판정 규칙 표와 빨간 줄 고르기.

규칙 한 줄 = 코드 · 담당자에게 보일 이름 · 무게(적용할 수 없음 blocked / 빨간 줄 red) · 고를 수 있는 것 · 판정 함수.
표의 위에서부터 처음 맞는 한 줄이 항목의 판정이다(항목마다 판정은 하나). 판정 함수가 받는 값은 종류마다 정한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Hashable, Iterable, Mapping

from .items import Refused

BLOCKED, RED = "blocked", "red"
RED_LINE_SHARE = Decimal("0.30")     # 「너무 큰 변화」 — 지금 값보다 30% 넘게 오르거나 내리면 빨간 줄(결정 10, 모든 종류에 같다)


def moved_far(old: Decimal | None, new: Decimal | None) -> bool:
    """한 필드가 `RED_LINE_SHARE` 넘게 움직였는지. 한쪽이 비었으면(새로 넣음 · 비움) 움직임으로 재지 않는다. 0 에서 움직이면 넘은 것이다."""
    return old is not None and new is not None and abs(new - old) > abs(old) * RED_LINE_SHARE


@dataclass(frozen=True)
class Rule:
    code: str
    label: str
    severity: str
    choices: tuple[str, ...]
    applies: Callable[..., bool]


class RuleTable:
    def __init__(self, *rules: Rule):
        self.rules = rules
        self.by_code = {rule.code: rule for rule in rules}

    def verdict(self, *facts) -> str | None:
        return next((rule.code for rule in self.rules if rule.applies(*facts)), None)

    def severity(self, code: str | None) -> str | None:
        rule = self.by_code.get(code)
        return None if rule is None else rule.severity


@dataclass(frozen=True)
class Resolution:
    """빨간 줄 규칙 하나에 대한 고름. `items` 가 None 이면 그 규칙의 모든 항목, 있으면 짚은 항목만. `said` 는 그렇게 고르며
    담당자가 한 말 그대로다 — 장부가 고른 것과 함께 적고, 결과 페이지가 고른 것 옆에 보인다."""
    rule: str
    choice: str
    items: tuple[Hashable, ...] | None = None
    said: str = ""


def said_in(entry: Mapping) -> str:
    """고름 파일의 고름 하나에 적힌 담당자의 말(`said`). 없으면 거절한다 — 빨간 줄의 고름은 담당자의 말에서만 나온다."""
    said = str(entry.get("said") or "").strip()
    if not said:
        raise Refused(f"고름마다 담당자가 그렇게 고르며 한 말을 그대로 적습니다(said): {entry.get('rule')} · {entry.get('choice')}")
    return said


def decide(table: RuleTable, flagged: Mapping[Hashable, str], resolutions: Iterable[Resolution],
           describe: Callable[[Hashable], str] = str) -> tuple[dict, tuple]:
    """빨간 줄 항목마다 고른 것 — `(항목 → 그 항목에 맞은 고름(Resolution), 아직 고르지 않은 항목)`. 항목을 짚은 고름이 규칙
    전체 고름보다 앞선다."""
    by_rule, by_item = {}, {}
    for resolution in resolutions:
        rule = table.by_code.get(resolution.rule)
        if rule is None or rule.severity != RED:
            raise Refused(f"고를 수 있는 것은 빨간 줄 규칙뿐입니다: {resolution.rule!r}")
        if resolution.choice not in rule.choices:
            raise Refused(f"{rule.label} — 고를 수 있는 것: {', '.join(rule.choices)} (받은 값 {resolution.choice!r})")
        if resolution.items is None:
            by_rule[rule.code] = resolution
            continue
        for item in resolution.items:
            if flagged.get(item) != rule.code:
                raise Refused(f"「{rule.label}」 항목이 아닙니다: {describe(item)}")
            by_item[item] = resolution
    chosen, waiting = {}, []
    for item, code in flagged.items():
        if table.severity(code) != RED:
            continue
        choice = by_item.get(item, by_rule.get(code))
        if choice is None:
            waiting.append(item)
        else:
            chosen[item] = choice
    return chosen, tuple(waiting)
