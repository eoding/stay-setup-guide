"""charge_plan.py — 부과금 금액 계산: 미리보기, 빨간 줄 고르기, 저장 단계, 장부 줄, 되돌리기.

    plan_change(snapshot, request)   → Plan            짚은 금액 칸마다 전 → 후, 판정. 셈은 여기서만 한다(도우미는 셈하지 않는다)
    resolve(plan, resolutions)       → Plan            빨간 줄 고름(이대로 바꿈 · 그 칸은 안 바꿈)을 칸에 단다
    plan_steps(plan)                 → 저장 단계들      부과금마다 한 번 — 창이 보인 칸 전부 + 바꾸는 금액 칸만 새 값. 빨간 줄이 남았으면 None
    preview_rows · rollback_rows     → 장부 줄         고른 부과금의 금액 칸 전부(바꾸지 않는 칸도 — 적용 뒤 견주기가 본다)
    plan_charge_rollback(…)          → RollbackPlan    (change_core.rollback.plan_rollback) — 지금 값을 읽은 부과금인지 본다
    rollback_steps(plan, snapshot)   → 저장 단계들      되돌릴 부과금마다 지금 창의 칸 + 적어 둔 값

도우미는 금액만 바꾼다. 빈 칸(「미정」 · 성인가와 같음)은 채우지 않고 찬 칸은 비우지 않는다 — 칸을 채우거나 비우는 것은 부과금의
모양을 바꾸는 일이다. 저장 단계는 그 사실을 스스로 지킨다(`ChargeStep` 이 만들어질 때 거절한다).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Iterable, Mapping, Sequence

from charge_model import (
    AGE, AMOUNT_NAME, FLAT, ITEM_KIND, MAIN, PCT, PER_PERSON, PRESENT, TIME, TYPED, Charge, ChargeRef, ChangeRequest, ModelError,
    Place, Snapshot, charge_of_key, decode_charge, encode_charge, encode_hotel, hotel_label, part_of_key, snapshot_items,
)
from change_core.ledger import FieldWrite, StepPlan, ValueRow
from change_core.money import money, money_text, round_money
from change_core.rollback import LaterWrite, RecordedChange, RollbackPlan, plan_rollback
from change_core.rules import BLOCKED, RED, Resolution, Rule, RuleTable, decide, moved_far
from change_core.window import Form, form_values, with_values

LIMIT = Decimal(10) ** 10                # ERP 의 금액 칸은 정수 10자리까지(max_digits 12 · 소수 2)
PCT_TOP = Decimal(100)

# 판정 함수는 Facts 하나를 받는다. 위에서부터 처음 맞는 한 줄이 그 칸의 판정이다.
RULES = RuleTable(
    Rule("NOT_USED", "이 부과금에서 계산에 쓰이지 않는 칸입니다", BLOCKED, (), lambda f: f.unused is not None),
    Rule("UNDECIDED", "비어 있는 칸(미정 · 성인가와 같음)은 채우지 않습니다", BLOCKED, (), lambda f: f.before is None),
    Rule("NEGATIVE", "0 아래가 됩니다", BLOCKED, (), lambda f: f.after is not None and f.after < 0),
    Rule("PCT_RANGE", "정률이 0~100% 밖이 됩니다", BLOCKED, (), lambda f: f.percent and f.after is not None and f.after > PCT_TOP),
    Rule("FORM_REFUSES", "ERP 가 그 값으로는 저장하지 않습니다", BLOCKED, (), lambda f: f.refused is not None),
    Rule("OVER_30", "30% 넘게 바뀝니다", RED, ("include", "keep"), lambda f: moved_far(f.before, f.after)),
)
CHOICE_LABELS = {"include": "이대로 바꿈", "keep": "그 칸은 안 바꿈"}


class PlanError(ModelError):
    """요청과 읽은 값이 맞지 않아 계산할 수 없다."""


@dataclass(frozen=True)
class Facts:
    before: Decimal | None
    after: Decimal | None
    unused: str | None
    refused: str | None
    percent: bool


def place_id(place: Place) -> str:
    """금액 칸을 짚는 짧은 글자 — 빨간 줄 고름 · 짧은 답에 쓴다. 「701 14:01-18:00 pct」 · 「705 CHD amount」 · 「703 amount」."""
    return " ".join(part for part in (place.charge, place.at, place.field) if part)


def unused(charge: Charge, place: Place) -> str | None:
    """그 칸이 이 부과금의 모양에서 계산에 쓰이지 않는 까닭(쓰이면 None) — 바꿔도 손님이 내는 돈이 바뀌지 않는 칸이다."""
    tiers = charge.times()
    if place.part == MAIN:
        if place.field in ("amount", "pct") and tiers:
            return "시간대별 요율이 있어 이 칸은 계산에 쓰이지 않습니다 — 시간대 줄의 금액을 바꿉니다"
        if place.field == "amount" and charge.basis == PCT:
            return "정률(1박 요금의 %) 부과금이라 정액 금액은 계산에 쓰이지 않습니다"
        if place.field == "pct" and charge.basis == FLAT:
            return "정액 부과금이라 정률은 계산에 쓰이지 않습니다"
        if place.field == "onsite" and not charge.onsite_currency:
            return "현장 결제 통화가 없는 부과금이라 현장 결제 금액이 없습니다"
        return None
    if place.part == TIME:
        band = next(band for band in tiers if band.at == place.at)
        if place.field == "amount" and band.basis == PCT:
            return "이 시간대 줄은 정률이라 정액 금액은 쓰이지 않습니다"
        if place.field == "pct" and band.basis == FLAT:
            return "이 시간대 줄은 정액이라 정률은 쓰이지 않습니다"
        return None
    if place.field == "amount" and not (charge.per == PER_PERSON and charge.basis == FLAT and not tiers):
        return "연령별 단가는 인당 · 정액 · 시간대 요율 없음일 때만 계산에 쓰입니다"
    if place.field == "onsite" and not charge.onsite_currency:
        return "현장 결제 통화가 없어 현장 단가가 쓰이지 않습니다"
    return None


def form_refusal(charge: Charge, changes: Mapping[Place, Decimal]) -> str | None:
    """바꾼 뒤의 부과금을 ERP 폼(ChargeEditForm.clean)이 받지 않는 까닭 — 받으면 None. 화면이 거절할 값은 저장하지 않는다."""
    def after(place: Place) -> Decimal | None:
        return changes[place] if place in changes else charge.value(place)

    for value in changes.values():
        if value >= LIMIT:
            return "금액이 너무 큽니다(ERP 의 금액 칸은 정수 10자리까지입니다)"
    places = charge.places()
    ages = [after(place) for place in places if place.part == AGE and place.field == "amount"]
    onsite_ages = [after(place) for place in places if place.part == AGE and place.field == "onsite"]
    online_ages = [value for value in ages if value is not None]
    onsite_rates = [value for value in onsite_ages if value is not None]
    tiers = charge.times()
    amount = after(Place(charge.id, MAIN, "", "amount")) if charge.basis == FLAT else None
    currency = charge.one("onsite_currency").strip()
    if online_ages and (charge.per != PER_PERSON or charge.basis != FLAT or tiers):
        return "연령별 단가가 있으면 부과 단위가 인당 · 방식이 정액 · 시간대 요율 없음이어야 ERP 가 저장합니다"
    if (after(Place(charge.id, MAIN, "", "onsite")) is not None or onsite_rates) and not currency:
        return "현장 결제 통화가 없는데 현장 금액이 있어 ERP 가 저장하지 않습니다"
    if currency and (charge.basis != FLAT or amount != 0 or tiers or any(value != 0 for value in online_ages)):
        return "현장 결제 부과금은 온라인 정액 금액과 연령별 단가가 0 이고 시간대 요율이 없어야 ERP 가 저장합니다"
    if onsite_rates and charge.per != PER_PERSON:
        return "현장 연령별 단가는 인당 부과금에서만 ERP 가 저장합니다"
    return None


def rounder(charge: Charge, place: Place, currency: str) -> Callable[[Decimal], Decimal]:
    """그 칸의 반올림 — 정률은 소수 둘, 현장 결제는 현장 통화의 자릿수, 나머지는 호텔 통화의 자릿수(ERP 와 같은 반올림)."""
    if place.field == "pct":
        return lambda value: value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    unit = (charge.onsite_currency or currency) if place.field == "onsite" else currency
    return lambda value: round_money(value, unit)


@dataclass(frozen=True)
class AmountChange:
    """짚은 금액 칸 하나의 계산. `after` 는 셈한 후 값(셈하지 못했으면 None), `choice` 는 빨간 줄에 고른 것."""
    offer: str
    place: Place
    label: str
    before: Decimal | None
    after: Decimal | None
    verdict: str | None
    choice: str | None = None

    @property
    def id(self) -> str:
        return place_id(self.place)

    @property
    def changed(self) -> bool:
        return self.after is not None and self.after != self.before

    @property
    def waiting(self) -> bool:
        return RULES.severity(self.verdict) == RED and self.choice is None

    @property
    def blocked(self) -> bool:
        return RULES.severity(self.verdict) == BLOCKED

    @property
    def writes(self) -> bool:
        """저장이 이 칸에 새 값을 넣는지 — 적용할 수 없는 칸 · 아직 고르지 않은 빨간 줄은 넣지 않는다(안 바꾸기로 고른 칸은 고를 때
        후 값이 전 값이 된다)."""
        return self.changed and not self.blocked and not self.waiting

    @property
    def free(self) -> bool:
        """이 저장으로 무료(0)가 된다 — 미리보기가 소리 내어 말한다."""
        return self.writes and self.after == 0


@dataclass(frozen=True)
class Plan:
    request: ChangeRequest
    read_at: str
    currency: str
    changes: tuple[AmountChange, ...]
    charges: tuple[Charge, ...]
    missing: tuple[ChargeRef, ...] = ()

    @property
    def unchanged(self) -> tuple[AmountChange, ...]:
        """그대로인 칸 — 바뀌지 않거나 안 바꾸기로 고른 칸. 바뀌는 · 그대로 · 바꿀 수 없는 · 고를 칸이 짚은 칸을 빠짐없이 나눈다."""
        return tuple(change for change in self.changes if not change.writes and not change.blocked and not change.waiting)

    def charge(self, charge_id: str) -> Charge:
        return next(charge for charge in self.charges if charge.id == charge_id)


def _after(before: Decimal | None, request: ChangeRequest, rounding: Callable[[Decimal], Decimal]) -> Decimal | None:
    if request.how == "value":
        return rounding(request.figure)
    if before is None:
        return None
    if request.how == "amount":
        return rounding(before + request.figure)
    return rounding(before * (Decimal(100) + request.figure) / Decimal(100))


def _verdict(charge: Charge, place: Place, before: Decimal | None, after: Decimal | None) -> str | None:
    why = unused(charge, place)
    if after is not None and after == before:
        return "NOT_USED" if why else None
    refused = form_refusal(charge, {place: after}) if after is not None else None
    return RULES.verdict(Facts(before, after, why, refused, place.field == "pct"))


def plan_change(snapshot: Snapshot, request: ChangeRequest) -> Plan:
    """짚은 금액 칸마다 전 → 후와 판정. 짚은 부과금 가운데 읽은 값에 없는 것(지워졌거나 번호가 바뀐 것)은 `missing` 이다."""
    if snapshot.hotel_id != request.hotel_id:
        raise PlanError(f"지금 값은 {hotel_label(snapshot.hotel, snapshot.hotel_id)} 것이고 요청은 "
                        f"{hotel_label(request.hotel, request.hotel_id)} 입니다")
    unread = [f"{offer} · {charge}" for offer, charge in request.charges() if not snapshot.covers(charge)]
    if unread:
        raise PlanError(f"요청한 부과금 가운데 읽지 않은 것이 있습니다({', '.join(unread)}) — 이 요청 파일로 읽기를 다시 합니다")
    currency = snapshot.currency
    changes, charges, missing = [], {}, []
    for target in request.targets:
        charge = snapshot.charges.get(target.place.charge)
        if charge is None:
            missing.append((target.offer, target.place.charge))
            continue
        if charge.offer != target.offer:
            raise PlanError(f"부과금 {charge.id}번은 오퍼 {charge.offer} 의 것입니다(요청은 오퍼 {target.offer}) — look 의 번호를 씁니다")
        place = charge.normal(target.place)
        charge.where(place)                   # 그 시간대 줄 · 연령 구간이 창에 있는지(없으면 ModelError)
        if any(change.place == place for change in changes):
            raise PlanError(f"같은 금액 칸을 두 번 적었습니다: {charge.place_label(place)}")
        before = charge.value(place)
        after = _after(before, request, rounder(charge, place, charge.currency or currency))
        changes.append(AmountChange(target.offer, place, charge.place_label(place), before, after,
                                    _verdict(charge, place, before, after)))
        charges[charge.id] = charge
    if not changes and not missing:
        raise PlanError("읽은 값에 요청이 짚은 부과금이 없습니다")
    return Plan(request, snapshot.read_at, currency, tuple(changes), tuple(charges.values()), tuple(dict.fromkeys(missing)))


def resolve(plan: Plan, resolutions: Iterable[Resolution]) -> Plan:
    """빨간 줄 고름을 칸에 단다. 고름의 `items` 는 금액 칸의 짧은 글자(place_id)다 — 그 규칙의 칸이 아니면 거절한다."""
    by_id = {change.id: change.place for change in plan.changes}
    keyed = [Resolution(item.rule, item.choice, None if item.items is None else tuple(by_id.get(str(name), str(name))
                                                                                    for name in item.items))
             for item in resolutions]
    flagged = {change.place: change.verdict for change in plan.changes if change.verdict}
    chosen, _waiting = decide(RULES, flagged, keyed, lambda place: f"금액 칸 {place_id(place) if isinstance(place, Place) else place}")
    return replace(plan, changes=tuple(_choose(change, chosen.get(change.place)) for change in plan.changes))


def _choose(change: AmountChange, choice: str | None) -> AmountChange:
    """고른 것을 단다 — 「그 칸은 안 바꿈」이면 후 값이 전 값이 된다(다른 두 도우미와 같다)."""
    if choice is None:
        return change
    return replace(change, choice=choice, after=change.before if choice == "keep" else change.after)


def unresolved(plan: Plan) -> tuple[AmountChange, ...]:
    return tuple(change for change in plan.changes if change.waiting)


def counts(plan: Plan) -> dict:
    """칸 수 — 짚은 칸 · 바뀌는 칸 · 그대로인 칸 · 바꿀 수 없는 칸 · 고를 칸, 무료가 되는 칸, 그리고 판정마다."""
    found = dict(amounts=len(plan.changes), charges=len(plan.charges), will_change=sum(c.writes for c in plan.changes),
                 unchanged=len(plan.unchanged), blocked=sum(c.blocked for c in plan.changes),
                 red=sum(c.waiting for c in plan.changes), chosen=sum(c.choice is not None for c in plan.changes),
                 free=sum(c.free for c in plan.changes), missing=len(plan.missing))
    for rule in RULES.rules:
        found[rule.code] = sum(change.verdict == rule.code for change in plan.changes)
    return found


# ───────────── 저장 단계 ─────────────

@dataclass(frozen=True)
class Edit:
    """저장이 넣는 금액 칸 하나 — 장부의 항목 키 · 필드와, 창의 칸 이름 · 몇 번째 · 넣는 글자."""
    key: str
    field: str
    name: str
    nth: int
    value: str


@dataclass(frozen=True)
class ChargeStep:
    """저장 한 번 = 부과금 하나의 편집 창 [저장] 한 번. `form` 은 창이 보일 칸 전부(읽은 그대로), `edits` 는 그 가운데 바꾸는 금액
    칸. 만들 때 지킨다: 금액 칸만 · 숫자 글자만(비우지 않는다) · 창에 있고 지금 빈 칸이 아닌 칸만(채우지 않는다) · 한 칸에 한 번."""
    offer: str
    charge: str
    name: str
    label: str
    form: Form
    edits: tuple[Edit, ...]

    kind = "charge"

    def __post_init__(self):
        if not self.edits:
            raise PlanError(f"바꾸는 칸이 없는 저장입니다: {self.label}")
        seen = set()
        for edit in self.edits:
            if not AMOUNT_NAME.match(edit.name):
                raise PlanError(f"저장은 금액 칸만 바꿉니다({edit.name} 는 금액 칸이 아닙니다): {self.label}")
            if not TYPED.match(edit.value):
                raise PlanError(f"금액 칸에는 0 이상의 숫자만 넣습니다({edit.name} ← {edit.value!r}): {self.label}")
            if charge_of_key(edit.key) != self.charge:
                raise PlanError(f"다른 부과금의 칸입니다: {self.label}")
            if (edit.name, edit.nth) in seen:
                raise PlanError(f"같은 칸을 두 번 바꿉니다({edit.name} {edit.nth + 1}번째): {self.label}")
            seen.add((edit.name, edit.nth))
            values = form_values(self.form, edit.name)
            if not 0 <= edit.nth < len(values):
                raise PlanError(f"창에 없는 칸입니다({edit.name} {edit.nth + 1}번째): {self.label}")
            if not values[edit.nth].strip():
                raise PlanError(f"빈 칸은 채우지 않습니다({edit.name} {edit.nth + 1}번째): {self.label}")
        self.sent()

    def sent(self) -> Form:
        """저장 단추가 보낼 칸 전부 — 읽은 칸에 바꾸는 칸만 새 값(change_core.window — 부가옵션 도우미와 같은 걸음)."""
        return with_values(self.form, {(edit.name, edit.nth): edit.value for edit in self.edits})

    def writes(self) -> tuple[FieldWrite, ...]:
        return tuple(FieldWrite(ITEM_KIND, edit.key, edit.field, money(edit.value)) for edit in self.edits)


def encode_step(step: ChargeStep) -> dict:
    return dict(kind=step.kind, offer=step.offer, charge=step.charge, name=step.name, label=step.label,
                form=[list(pair) for pair in step.form],
                edits=[dict(key=e.key, field=e.field, name=e.name, nth=e.nth, value=e.value) for e in step.edits])


def decode_step(data: Mapping) -> ChargeStep:
    if data.get("kind") != "charge":
        raise ModelError(f"부과금의 저장 단계가 아닙니다: {data.get('kind')}")
    return ChargeStep(str(data["offer"]), str(data["charge"]), str(data["name"]), str(data["label"]),
                      tuple((str(name), str(value)) for name, value in data["form"]),
                      tuple(Edit(str(e["key"]), str(e["field"]), str(e["name"]), int(e["nth"]), str(e["value"]))
                            for e in data["edits"]))


def _step(charge: Charge, targets: Mapping[Place, Decimal]) -> ChargeStep:
    edits = []
    for place, value in targets.items():
        if value is None:
            raise PlanError(f"비우는 저장은 하지 않습니다: {charge.place_label(place)}")
        name, nth = charge.where(place)
        edits.append(Edit(place.key, place.field, name, nth, money_text(value)))
    return ChargeStep(charge.offer, charge.id, charge.name, charge.label, charge.form, tuple(edits))


def plan_steps(plan: Plan) -> tuple[ChargeStep, ...] | None:
    """바뀌는 칸이 있는 부과금마다 저장 한 번(짚은 차례). 아직 고르지 않은 빨간 줄이 있으면 None."""
    if unresolved(plan):
        return None
    grouped: dict[str, dict[Place, Decimal]] = {}
    for change in plan.changes:
        if change.writes:
            grouped.setdefault(change.place.charge, {})[change.place] = change.after
    return tuple(_step(plan.charge(charge_id), targets) for charge_id, targets in grouped.items())


def step_plans(steps: Iterable[ChargeStep]) -> list[StepPlan]:
    return [StepPlan(step.kind, step.label, encode_step(step), step.writes()) for step in steps]


def step_call(no: int, hotel: str, hotel_id: str, step: ChargeStep) -> dict:
    """장부의 저장 단계 하나 → stayCharge.applyCharge 에 그대로 넣을 값."""
    return {"no": no, "op": "applyCharge", "payload": {
        "no": no, "hotel": encode_hotel(hotel, hotel_id), "offer": step.offer, "charge": step.charge, "name": step.name,
        "form": [list(pair) for pair in step.form], "set": [[edit.name, edit.nth, edit.value] for edit in step.edits]}}


# ───────────── 장부 줄 ─────────────

def _rows(charge: Charge, changes: Mapping[Place, AmountChange] | None = None,
          targets: Mapping[Place, Decimal] | None = None) -> list[ValueRow]:
    """부과금 하나의 금액 칸 전부 — 칸마다 전 값 · 후 값 · 넣는지 · 판정 · 고른 것(미리보기) 또는 되돌릴 값(되돌리기)."""
    rows = []
    for place in charge.places():
        before = charge.value(place)
        change = (changes or {}).get(place)
        if change is not None:
            after, write, verdict, choice = change.after, change.writes, change.verdict, change.choice
        else:
            after = (targets or {}).get(place)
            write, verdict, choice = after is not None and after != before, None, None
        rows.append(ValueRow(ITEM_KIND, place.key, charge.part_label(place.part, place.at), place.field, PRESENT, before,
                             None if after is None or after == before else after, verdict, (),
                             "set" if write else None, choice))
    return rows


def preview_rows(plan: Plan) -> list[ValueRow]:
    """짚은 부과금의 금액 칸 전부(바뀌지 않는 칸도) — 적용 뒤 견주기가 그 칸들이 그대로인지 본다."""
    by_place = {change.place: change for change in plan.changes}
    return [row for charge in plan.charges for row in _rows(charge, changes=by_place)]


# ───────────── 되돌리기 ─────────────

def charge_filter(charges: Iterable[str] = ()) -> tuple[Callable[[str, str], bool] | None, str]:
    """일부만 되돌릴 때 부과금을 고르는 조건(부과금 번호)과 그 범위의 글. 아무것도 주지 않으면 `(None, "")` — 변경 전체다."""
    chosen = {str(charge) for charge in charges}
    if not chosen:
        return None, ""
    return (lambda kind, key: kind == ITEM_KIND and charge_of_key(key) in chosen), "부과금 " + " · ".join(sorted(chosen)) + "번"


def plan_charge_rollback(recorded: RecordedChange, later: Mapping[tuple[str, str], Sequence[LaterWrite]], now: Snapshot,
                         include_kept: bool = False, select: Callable[[str, str], bool] | None = None) -> RollbackPlan:
    """부과금 되돌리기 — 지금 값을 그 부과금들만큼 읽었는지 보고 공통 되돌리기 계산에 넘긴다. 그 사이 지워진 부과금 · 시간대 줄 ·
    연령별 단가, 그리고 그 사이 빈 칸이 된 금액은 되살릴 길이 없어 그대로 두는 것(까닭: 도우미 밖)으로 남는다."""
    if now.hotel_id != recorded.hotel_id:
        raise PlanError(f"지금 읽은 값은 {hotel_label(now.hotel, now.hotel_id)} 것이고, 되돌릴 변경은 "
                        f"{hotel_label(recorded.hotel, recorded.hotel_id)} 입니다")
    gaps = sorted({charge_of_key(item.key) for item in recorded.items
                   if item.kind == ITEM_KIND and (select is None or select(item.kind, item.key))
                   and not now.covers(charge_of_key(item.key))})
    if gaps:
        raise PlanError(f"지금 값을 읽지 않은 부과금: {', '.join(gaps)}")
    plan = plan_rollback(recorded, later, snapshot_items(now), now.read_at, include_kept, select)
    return replace(plan, restored=tuple(item for item in plan.restored if item.now.state == PRESENT
                                        and all(item.now.fields.get(name) is not None for name in item.targets)))


def _targets(plan: RollbackPlan) -> dict[str, dict[Place, Decimal]]:
    grouped: dict[str, dict[Place, Decimal]] = {}
    for item in plan.restored:
        charge, part, at = part_of_key(item.key)
        for name, value in item.targets.items():
            grouped.setdefault(charge, {})[Place(charge, part, at, name)] = value
    return grouped


def rollback_steps(plan: RollbackPlan, now: Snapshot) -> tuple[ChargeStep, ...]:
    """되돌릴 부과금마다 저장 한 번 — 지금 편집 창의 칸 전부 + 적어 둔 값."""
    return tuple(_step(now.charges[charge_id], targets) for charge_id, targets in _targets(plan).items())


def rollback_rows(plan: RollbackPlan, now: Snapshot) -> list[ValueRow]:
    return [row for charge_id, targets in _targets(plan).items() for row in _rows(now.charges[charge_id], targets=targets)]


# ───────────── 계산 파일 ─────────────

def encode_change(change: AmountChange) -> dict:
    return dict(offer=change.offer, charge=change.place.charge, part=change.place.part, at=change.place.at,
                field=change.place.field, label=change.label, before=money_text(change.before), after=money_text(change.after),
                verdict=change.verdict, choice=change.choice)


def decode_change(data: Mapping) -> AmountChange:
    return AmountChange(str(data["offer"]), Place(str(data["charge"]), str(data["part"]), str(data["at"]), str(data["field"])),
                        str(data["label"]), money(data["before"]), money(data["after"]), data["verdict"], data["choice"])


def encode_plan(plan: Plan, encode_request) -> dict:
    return dict(request=encode_request(plan.request), read_at=plan.read_at, currency=plan.currency,
                changes=[encode_change(change) for change in plan.changes],
                charges=[encode_charge(charge) for charge in plan.charges],
                missing=[dict(offer=offer, charge=charge) for offer, charge in plan.missing])


def decode_plan(data: Mapping, decode_request) -> Plan:
    return Plan(decode_request(data["request"]), str(data["read_at"]), str(data["currency"]),
                tuple(decode_change(change) for change in data["changes"]),
                tuple(decode_charge(charge) for charge in data["charges"]),
                tuple((str(item["offer"]), str(item["charge"])) for item in data["missing"]))

