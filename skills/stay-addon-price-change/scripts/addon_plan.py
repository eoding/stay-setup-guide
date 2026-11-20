"""addon_plan.py — 부가옵션 가격 줄 계산: 미리보기, 빨간 줄 고르기, 저장 단계, 장부 줄, 되돌리기.

    plan_change(snapshot, request)   → Plan            고른 줄마다 전 → 후, 판정. 셈은 여기서만 한다(도우미는 셈하지 않는다)
    resolve(plan, resolutions)       → Plan            빨간 줄 고름(이대로 바꿈 · 그 줄은 안 바꿈)을 줄에 단다
    plan_steps(plan)                 → 저장 단계들      줄마다 한 번 — 편집 창이 보인 칸 전부 + 바꾸는 칸만 새 값. 빨간 줄이 남았으면 None
    preview_rows · rollback_rows     → 장부 줄         (change_core.ledger 의 ValueRow)
    plan_line_rollback(recorded, …)  → RollbackPlan    (change_core.rollback.plan_rollback) — 지금 값을 읽은 줄인지 본다
    rollback_steps(plan, snapshot)   → 저장 단계들      되돌릴 줄마다 지금 편집 창의 칸 + 적어 둔 값

공급 원가 칸은 바꾸라는 말이 없으면 편집 창이 보인 값 그대로 보낸다 — 비우는 것은 담당자가 비우라고 했을 때와, 되돌리기가 원가가
없던 때로 돌릴 때뿐이다. 저장 단계는 그 사실을 스스로 지킨다(`LineStep` 이 만들어질 때 거절한다).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Callable, Iterable, Mapping, Sequence

from addon_model import (
    DIFFER, DOUBT_LABELS, FIELD_LABELS, FIELDS, FORM_NAMES, HIDDEN, ITEM_KIND, PRESENT, ChangeRequest, Form, Line, LineKey,
    ModelError, Snapshot, encode_hotel, form_value, hotel_label, key_of_item, line_item_key, snapshot_items, with_values,
)
from change_core.ledger import FieldWrite, StepPlan, ValueRow
from change_core.money import money, money_text, round_money
from change_core.rollback import LaterWrite, RecordedChange, RollbackPlan, plan_rollback
from change_core.rules import BLOCKED, RED, Resolution, Rule, RuleTable, decide, moved_far

Values = Mapping[str, Decimal | None]

# 판정 함수는 (전 값, 후 값 또는 None, 셈하지 못한 까닭 또는 None, 의심스러운 까닭 또는 None, 넣는 필드들) 을 받는다.
# 위에서부터 처음 맞는 한 줄이 그 줄의 판정이다. 판매가 0 이하는 판매가를 바꿀 때만 본다 — 무료(0)인 줄의 원가만 바꾸는 것은 된다.
LINE_RULES = RuleTable(
    Rule(HIDDEN.upper(), "금액 기록이 ERP 화면에 보이지 않는 줄입니다", BLOCKED, (),
         lambda before, after, lacking, doubt, changed: doubt == HIDDEN),
    Rule(DIFFER.upper(), "목록과 편집 창이 금액을 다르게 보입니다", BLOCKED, (),
         lambda before, after, lacking, doubt, changed: doubt == DIFFER),
    Rule("NO_SUPPLY", "공급 원가가 없어 금액 · 퍼센트로 셈할 수 없습니다", BLOCKED, (),
         lambda before, after, lacking, doubt, changed: lacking == "supply"),
    Rule("NOT_POSITIVE", "판매가가 0 이하가 됩니다", BLOCKED, (),
         lambda before, after, lacking, doubt, changed: after is not None and "sell" in changed and after["sell"] <= 0),
    Rule("NEGATIVE_SUPPLY", "공급 원가가 0 아래가 됩니다", BLOCKED, (),
         lambda before, after, lacking, doubt, changed: after is not None and after["supply"] is not None and after["supply"] < 0),
    Rule("BELOW_COST", "공급 원가보다 싸집니다", RED, ("include", "keep"),
         lambda before, after, lacking, doubt, changed: after is not None and after["supply"] is not None
         and after["sell"] < after["supply"]),
    Rule("OVER_30", "30% 넘게 바뀝니다", RED, ("include", "keep"),
         lambda before, after, lacking, doubt, changed: after is not None and any(moved_far(before[name], after[name]) for name in changed)),
)
CHOICE_LABELS = {"include": "이대로 바꿈", "keep": "그 줄은 안 바꿈"}


class PlanError(ModelError):
    """요청과 읽은 값이 맞지 않아 계산할 수 없다."""


@dataclass(frozen=True)
class LineChange:
    """고른 줄 하나의 계산. `after` 는 셈한 후 값(셈하지 못했으면 None), `choice` 는 빨간 줄에 고른 것."""
    line: Line
    after: Values | None
    verdict: str | None
    choice: str | None = None

    @property
    def key(self) -> LineKey:
        return self.line.key

    @property
    def before(self) -> dict[str, Decimal | None]:
        return self.line.fields()

    @property
    def changed(self) -> tuple[str, ...]:
        return () if self.after is None else tuple(name for name in FIELDS if self.after[name] != self.before[name])

    @property
    def waiting(self) -> bool:
        return LINE_RULES.severity(self.verdict) == RED and self.choice is None

    @property
    def writes(self) -> dict[str, Decimal | None]:
        """저장이 이 줄에 넣는 필드 → 값(비우면 None). 적용할 수 없는 줄 · 아직 고르지 않은 · 안 바꾸기로 고른 빨간 줄은 넣지 않는다."""
        if LINE_RULES.severity(self.verdict) == BLOCKED or self.waiting or self.choice == "keep":
            return {}
        return {name: self.after[name] for name in self.changed}


@dataclass(frozen=True)
class Plan:
    request: ChangeRequest
    read_at: str
    currency: str
    changes: tuple[LineChange, ...]
    missing: tuple[LineKey, ...] = ()

    @property
    def unchanged(self) -> tuple[LineChange, ...]:
        return tuple(change for change in self.changes if not change.changed and change.verdict is None)


def _after(line: Line, request: ChangeRequest, currency: str) -> tuple[dict | None, str | None]:
    before = line.fields()
    old = before[request.field]
    if request.how == "clear":
        new = None
    elif request.how == "value":
        new = round_money(request.figure, currency)
    elif old is None:
        return None, request.field
    elif request.how == "amount":
        new = round_money(old + request.figure, currency)
    else:
        new = round_money(old * (Decimal(100) + request.figure) / Decimal(100), currency)
    return dict(before, **{request.field: new}), None


def plan_change(snapshot: Snapshot, request: ChangeRequest) -> Plan:
    """고른 줄마다 전 → 후와 판정. 고른 줄 가운데 읽은 값에 없는 줄(지워졌거나 읽지 않은 줄)은 `missing` 이다."""
    if snapshot.hotel_id != request.hotel_id:
        raise PlanError(f"지금 값은 {hotel_label(snapshot.hotel, snapshot.hotel_id)} 것이고 요청은 "
                        f"{hotel_label(request.hotel, request.hotel_id)} 입니다")
    chosen = [key for key in snapshot.asked if request.selects(key)]
    if request.lines and set(request.lines) - set(snapshot.asked):
        raise PlanError("요청한 줄 가운데 읽지 않은 줄이 있습니다 — 이 요청 파일로 읽기를 다시 합니다")
    if not chosen:
        raise PlanError("읽은 값에 요청이 고른 가격 줄이 없습니다")
    currency = snapshot.currency
    changes = []
    for key in chosen:
        line = snapshot.lines.get(key)
        if line is None:
            continue
        after, lacking = _after(line, request, currency)
        changed = () if after is None else tuple(name for name in FIELDS if after[name] != line.fields()[name])
        verdict = (LINE_RULES.verdict(line.fields(), after, lacking, line.doubt, changed)
                   if changed or lacking or line.doubt else None)
        changes.append(LineChange(line, after, verdict))
    return Plan(request, snapshot.read_at, currency, tuple(changes), tuple(key for key in chosen if key not in snapshot.lines))


def resolve(plan: Plan, resolutions: Iterable[Resolution]) -> Plan:
    """빨간 줄 고름을 줄에 단다. 고름의 `items` 는 가격 줄 번호(글자)다 — 그 규칙의 줄이 아니면 거절한다."""
    by_line = {change.key.line: change.key for change in plan.changes}
    keyed = [Resolution(item.rule, item.choice, None if item.items is None else tuple(by_line.get(str(line), str(line))
                                                                                    for line in item.items))
             for item in resolutions]
    flagged = {change.key: change.verdict for change in plan.changes if change.verdict}
    chosen, _waiting = decide(LINE_RULES, flagged, keyed, lambda key: f"가격 줄 {getattr(key, 'line', key)}번")
    return replace(plan, changes=tuple(replace(change, choice=chosen.get(change.key)) for change in plan.changes))


def unresolved(plan: Plan) -> tuple[LineChange, ...]:
    return tuple(change for change in plan.changes if change.waiting)


def counts(plan: Plan) -> dict:
    """줄 수 — 고른 줄 · 바뀌는 줄 · 그대로인 줄 · 없는 줄, 그리고 판정마다."""
    found = dict(lines=len(plan.changes) + len(plan.missing), will_change=sum(bool(change.writes) for change in plan.changes),
                 unchanged=len(plan.unchanged), missing=len(plan.missing),
                 blocked=sum(LINE_RULES.severity(change.verdict) == BLOCKED for change in plan.changes),
                 red=sum(change.waiting for change in plan.changes))
    for rule in LINE_RULES.rules:
        found[rule.code] = sum(change.verdict == rule.code for change in plan.changes)
    return found


# ───────────── 저장 단계 ─────────────

@dataclass(frozen=True)
class LineStep:
    """저장 한 번 = 가격 줄 하나의 편집 창 [저장] 한 번. `form` 은 창이 보일 칸 전부(읽은 그대로), `set` 은 그 가운데 바꾸는 칸의
    새 글자(공급 원가를 비우면 ""). 공급 원가는 바꾸지 않으면 `form` 의 값 그대로 간다 — 만들 때 그것을 지킨다."""
    addon: str
    line: str
    label: str
    form: Form
    set: Mapping[str, str]

    kind = "line"

    def __post_init__(self):
        unknown = set(self.set) - set(FORM_NAMES.values())
        if unknown or not self.set:
            raise PlanError(f"저장은 판매가(price) · 공급 원가(net_amount)만 바꿉니다: {self.label}")
        final = self.sent()
        supply = FORM_NAMES["supply"]
        if not form_value(final, supply, self.label).strip() and form_value(self.form, supply, self.label).strip() \
                and self.set.get(supply) != "":
            raise PlanError(f"공급 원가가 빈 채로 저장될 뻔했습니다: {self.label}")
        if not form_value(final, FORM_NAMES["sell"], self.label).strip():
            raise PlanError(f"판매가가 빈 채로 저장될 뻔했습니다: {self.label}")

    @property
    def key(self) -> LineKey:
        return LineKey(self.addon, self.line)

    def sent(self) -> Form:
        """저장 단추가 보낼 칸 전부 — 읽은 칸에 바꾸는 칸만 새 값."""
        return with_values(self.form, self.set)

    def writes(self) -> tuple[FieldWrite, ...]:
        names = {form_name: name for name, form_name in FORM_NAMES.items()}
        return tuple(FieldWrite(ITEM_KIND, line_item_key(self.key), names[form_name], money(text) if text.strip() else None)
                     for form_name, text in self.set.items())


def encode_step(step: LineStep) -> dict:
    return dict(kind=step.kind, addon=step.addon, line=step.line, label=step.label, form=[list(pair) for pair in step.form],
                set=dict(step.set))


def decode_step(data: Mapping) -> LineStep:
    if data.get("kind") != "line":
        raise ModelError(f"부가옵션 가격 줄의 저장 단계가 아닙니다: {data.get('kind')}")
    return LineStep(str(data["addon"]), str(data["line"]), str(data["label"]),
                    tuple((str(name), str(value)) for name, value in data["form"]), {str(k): str(v) for k, v in data["set"].items()})


def _step(line: Line, writes: Values) -> LineStep:
    return LineStep(line.key.addon, line.key.line, line.label, line.form,
                    {FORM_NAMES[name]: "" if value is None else money_text(value) for name, value in writes.items()})


def plan_steps(plan: Plan) -> tuple[LineStep, ...] | None:
    """바뀌는 줄마다 저장 한 번. 아직 고르지 않은 빨간 줄이 있으면 None."""
    if unresolved(plan):
        return None
    return tuple(_step(change.line, change.writes) for change in plan.changes if change.writes)


def step_plans(steps: Iterable[LineStep]) -> list[StepPlan]:
    return [StepPlan(step.kind, step.label, encode_step(step), step.writes()) for step in steps]


def step_call(no: int, hotel: str, hotel_id: str, step: LineStep) -> dict:
    """장부의 저장 단계 하나 → stayAddonPrice.applyLine 에 그대로 넣을 값."""
    return {"no": no, "op": "applyLine", "payload": {"no": no, "hotel": encode_hotel(hotel, hotel_id), "addon": step.addon,
                                                     "line": step.line, "form": [list(pair) for pair in step.form],
                                                     "set": dict(step.set)}}


# ───────────── 장부 줄 ─────────────

def _rows(line: Line, after: Values | None, writes: Values, verdict=None, choice=None) -> list[ValueRow]:
    rows = []
    for name in FIELDS:
        old = line.fields()[name]
        new = None if after is None else after[name]
        action = None if name not in writes else "clear" if writes[name] is None else "set"
        rows.append(ValueRow(ITEM_KIND, line_item_key(line.key), line.label, name, PRESENT, old,
                             None if new == old else new, verdict, (), action, choice))
    return rows


def preview_rows(plan: Plan) -> list[ValueRow]:
    """고른 줄 전부(바뀌지 않는 줄도) — 필드마다 전 값 · 후 값 · 넣는지 · 판정 · 고른 것."""
    return [row for change in plan.changes
            for row in _rows(change.line, change.after, change.writes, change.verdict, change.choice)]


# ───────────── 되돌리기 ─────────────

def line_filter(lines: Iterable[str] = ()) -> tuple[Callable[[str, str], bool] | None, str]:
    """일부만 되돌릴 때 줄을 고르는 조건(가격 줄 번호)과 그 범위의 글. 아무것도 주지 않으면 `(None, "")` — 변경 전체다."""
    chosen = {str(line) for line in lines}
    if not chosen:
        return None, ""
    return (lambda kind, key: kind == ITEM_KIND and key_of_item(key).line in chosen), "가격 줄 " + " · ".join(sorted(chosen)) + "번"


def plan_line_rollback(recorded: RecordedChange, later: Mapping[tuple[str, str], Sequence[LaterWrite]], now: Snapshot,
                       include_kept: bool = False, select: Callable[[str, str], bool] | None = None) -> RollbackPlan:
    """부가옵션 가격 줄 되돌리기 — 지금 값을 그 줄들만큼 읽었는지 보고 공통 되돌리기 계산에 넘긴다. 그 사이 지워진 줄은 되살릴 길이
    없어 그대로 두는 줄(까닭: 도우미 밖)로 남고, 같이 되돌리라고 해도 넣지 않는다."""
    if now.hotel_id != recorded.hotel_id:
        raise PlanError(f"지금 읽은 값은 {hotel_label(now.hotel, now.hotel_id)} 것이고, 되돌릴 변경은 "
                        f"{hotel_label(recorded.hotel, recorded.hotel_id)} 입니다")
    gaps = sorted(key_of_item(item.key).line for item in recorded.items
                  if item.kind == ITEM_KIND and (select is None or select(item.kind, item.key))
                  and not now.covers(key_of_item(item.key)))
    if gaps:
        raise PlanError(f"지금 값을 읽지 않은 가격 줄: {', '.join(gaps)}")
    plan = plan_rollback(recorded, later, snapshot_items(now), now.read_at, include_kept, select)
    return replace(plan, restored=tuple(item for item in plan.restored if item.now.state == PRESENT))


def rollback_steps(plan: RollbackPlan, now: Snapshot) -> tuple[LineStep, ...]:
    """되돌릴 줄마다 저장 한 번 — 지금 편집 창의 칸 전부 + 적어 둔 값(적어 둔 원가가 없으면 원가를 비운다)."""
    return tuple(_step(now.lines[key_of_item(item.key)], item.targets) for item in plan.restored)


def rollback_rows(plan: RollbackPlan, now: Snapshot) -> list[ValueRow]:
    rows = []
    for item in plan.restored:
        line = now.lines[key_of_item(item.key)]
        after = dict(line.fields(), **item.targets)
        rows += _rows(line, after, item.targets)
    return rows


def doubt_label(code: str | None) -> str:
    return DOUBT_LABELS.get((code or "").lower(), "")
