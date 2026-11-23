"""promotion_plan.py — 프로모션 할인 계산: 미리보기, 빨간 줄 고르기, 저장 단계, 장부 줄, 되돌리기.

    plan_change(snapshot, request)   → Plan            짚은 단마다 전 → 후, 판정. 셈은 여기서만 한다(도우미는 셈하지 않는다)
    resolve(plan, resolutions)       → Plan            빨간 줄 고름(이대로 바꿈 · 그 단은 안 바꿈)을 단에 달고, 고른 뒤 저장될 단 사다리를
                                                       다시 본다(새로 뒤집히는 단은 새 빨간 줄 — 더 생기지 않을 때까지)
    plan_steps(plan)                 → 저장 단계들      프로모션마다 한 번 — 창이 보인 칸 전부 + 바꾸는 단의 값만 새 값. 빨간 줄이 남았으면 None
    preview_rows · rollback_rows     → 장부 줄         고른 프로모션의 단 전부(바꾸지 않는 단도 — 적용 뒤 견주기가 본다)
    plan_promotion_rollback(…)       → RollbackPlan    (change_core.rollback.plan_rollback) — 지금 값을 읽은 프로모션인지 본다
    rollback_steps(plan, snapshot)   → 저장 단계들      되돌릴 프로모션마다 지금 창의 칸 + 적어 둔 값

도우미는 단의 값만 바꾼다. 제목 · 코드 · 발동 조건 · 혜택 방식 · 단위 · 기준값 · 날짜 · 진행기간 · 시즌 · 요금제 · 중복 · 배타 그룹 · 취소
정책 · 적용 범위는 창이 보인 그대로 보내고, 단을 더하거나 지우지 않는다. 저장 단계는 그 사실과 「표식 있는 ERP 에서만 저장」을 스스로
지킨다(`PromotionStep` 이 만들어질 때 거절한다).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Iterable, Mapping, Sequence

from promotion_model import (
    BASES, GATE, ITEM_KIND, ORIGIN_UNKNOWN, PRESENT, TRIGGERS, TYPED, UNSURE_ORIGIN, VALUE, ChangeRequest, ModelError, Promotion,
    PromotionRef, Snapshot,
    decode_promotion, encode_hotel, encode_promotion, hotel_label, part_of_key, promotion_of_key, snapshot_items, threshold_key,
    tier_key,
)
from change_core.items import Refused
from change_core.ledger import FieldWrite, StepPlan, ValueRow
from change_core.money import money, money_text, round_money
from change_core.rollback import LaterWrite, RecordedChange, RollbackPlan, plan_rollback
from change_core.rules import BLOCKED, RED, Resolution, Rule, RuleTable, decide, moved_far
from change_core.window import Form, form_values, with_values

HUNDRED = Decimal(100)
DATE = r"\d{4}-\d{2}-\d{2}"


@dataclass(frozen=True)
class Facts:
    before: Decimal | None
    after: Decimal | None
    keeps: bool
    basis: str
    refused: str | None
    origin_known: bool
    free_stay: bool
    inverts: bool


def _whole(value: Decimal | None) -> bool:
    return value is not None and value == value.to_integral_value()


# 판정 함수는 Facts 하나를 받는다. 위에서부터 처음 맞는 한 줄이 그 단의 판정이다.
RULES = RuleTable(
    Rule("NO_MARK", GATE, BLOCKED, (), lambda f: not f.keeps),
    Rule("ORIGIN_UNKNOWN", ORIGIN_UNKNOWN, BLOCKED, (), lambda f: not f.origin_known),
    Rule("EMPTY", "값이 비어 있는 단은 채우지 않습니다", BLOCKED, (), lambda f: f.before is None),
    Rule("NEGATIVE", "0 아래가 됩니다", BLOCKED, (), lambda f: f.after is not None and f.after < 0),
    Rule("PCT_RANGE", "할인율이 100% 를 넘습니다", BLOCKED, (), lambda f: f.basis == "PCT" and f.after is not None and f.after > HUNDRED),
    Rule("NOT_WHOLE", "무료 숙박은 박 단위 정수여야 합니다", BLOCKED, (), lambda f: f.basis == "FREE_NIGHT" and f.after is not None
         and not _whole(f.after)),
    Rule("FORM_REFUSES", "ERP 가 이 프로모션을 그 값으로 저장하지 않습니다", BLOCKED, (), lambda f: f.refused is not None),
    Rule("ZERO", "할인이 없어집니다", RED, ("include", "keep"), lambda f: f.after == 0),
    Rule("ROOM_FREE", "객실 요금이 무료가 됩니다", RED, ("include", "keep"), lambda f: f.free_stay),
    Rule("INVERTS", "기준값이 더 큰 단보다 할인이 커집니다(작으면 작아집니다)", RED, ("include", "keep"), lambda f: f.inverts),
    Rule("OVER_30", "30% 넘게 바뀝니다", RED, ("include", "keep"), lambda f: moved_far(f.before, f.after)),
)
CHOICE_LABELS = {"include": "이대로 바꿈", "keep": "그 단은 안 바꿈"}
INVERTS = "INVERTS"     # 고른 뒤 저장될 사다리로 다시 보는 규칙(resolve)


class PlanError(ModelError):
    """요청과 읽은 값이 맞지 않아 계산할 수 없다."""


def typed(value: Decimal) -> str:
    """창의 값 칸에 치는 글자 — 그 값의 십진 글자 그대로(지수 꼴 없이). ERP 는 친 글자를 그대로 적으므로, 되돌리기는 읽어 둔 표기
    (「15.0」)를 그대로 친다. 도우미가 셈한 값은 셈할 때 끝의 0 을 뺀다(`plain`)."""
    return f"{value:f}"


def plain(value: Decimal) -> Decimal:
    """셈한 값의 표기 — 끝의 0 을 뺀다(12.50 → 12.5, 25.00 → 25, 100 → 100). 목록이 「12.5%」 · 「25 USD」로 보인다."""
    return Decimal(f"{value.normalize():f}") if value else Decimal(0)


def rounder(promotion: Promotion, currency: str) -> Callable[[Decimal], Decimal]:
    """단의 값의 반올림 — 할인율은 소수 둘, 할인 금액은 호텔 통화의 자릿수, 무료 숙박은 반올림하지 않는다(정수가 아니면 바꿀 수
    없는 단으로 남긴다 — 도우미가 박수를 지어내지 않는다)."""
    basis = promotion.basis
    if basis == "PCT":
        return lambda value: value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if basis == "FLAT":
        return lambda value: round_money(value, promotion.currency or currency)
    return lambda value: value


def _threshold(text: str) -> int | None:
    try:
        number = Decimal(str(text).strip())
    except ArithmeticError:
        return None
    return int(number) if number.is_finite() and _whole(number) and number >= 0 else None


def form_refusal(promotion: Promotion, changes: Mapping[str, Decimal]) -> str | None:
    """바꾼 뒤의 프로모션을 ERP 폼(PromotionEditForm.clean)이 받지 않는 까닭 — 받으면 None. `changes` 는 기준값 → 새 값. 화면이 거절할
    값은 저장하지 않는다 — 바꾸지 않는 칸이 이미 폼에 맞지 않아도(시딩 · SQL 로 들어온 프로모션) 그 프로모션은 저장하지 않는다."""
    tiers = promotion.tiers()
    trigger, basis = promotion.trigger, promotion.basis
    if not promotion.one("title").strip():
        return "프로모션명이 비어 있어 ERP 가 저장하지 않습니다"
    if trigger not in TRIGGERS or basis not in BASES:
        return "발동 조건이나 혜택 방식이 비어 있어 ERP 가 저장하지 않습니다"
    if not tiers:
        return "할인 단이 하나도 없어 ERP 가 저장하지 않습니다"
    numbers = [_threshold(tier.threshold) for tier in tiers]
    if None in numbers:
        return "기준값이 0 이상의 정수가 아닌 단이 있어 ERP 가 저장하지 않습니다"
    if trigger == "ALWAYS" and any(number != 0 for number in numbers):
        return "‘상시’ 프로모션의 기준값이 0 이 아니라 ERP 가 저장하지 않습니다"
    for tier in tiers:
        value = changes.get(tier.at, promotion.value(tier))
        words = promotion.threshold_words(tier)
        if value is None:
            return f"{words} 단의 값이 비어 있어 ERP 가 저장하지 않습니다"
        if value < 0 or (basis == "PCT" and value > HUNDRED) or (basis == "FREE_NIGHT" and not _whole(value)):
            return f"{words} 단의 값({money_text(value)})을 ERP 가 받지 않습니다"
    if promotion.one("tiers_submitted") != "1":
        return "할인 단 표식(tiers_submitted)이 없어 ERP 가 단을 읽지 않습니다"
    get = (lambda name: (form_values(promotion.form, name) or [""])[0].strip())
    if form_values(promotion.form, "promotion_apply_flag"):
        start, end = get("promotion_apply_start_date"), get("promotion_apply_end_date")
        if not start or not end:
            return "진행기간 제한이 켜져 있는데 기간이 비어 있어 ERP 가 저장하지 않습니다"
        if start > end:
            return "진행기간의 종료일이 시작일보다 빨라 ERP 가 저장하지 않습니다"
    start, end = get("start_date"), get("end_date")
    if start and end and start > end:
        return "적용 숙박일의 종료일이 시작일보다 빨라 ERP 가 저장하지 않습니다"
    return None


def free_stay(promotion: Promotion, at: str, after: Decimal | None) -> bool:
    """그 값이면 객실 요금이 통째로 무료가 되는지 — 할인율 100%, 또는 연박 무료 숙박이 그 단의 박수 이상."""
    if after is None:
        return False
    if promotion.basis == "PCT":
        return after == HUNDRED
    threshold = _threshold(at)
    return promotion.basis == "FREE_NIGHT" and promotion.trigger == "LOS" and bool(threshold) and after >= threshold


def _inverted(promotion: Promotion, at: str, values: Mapping[str, Decimal | None]) -> bool:
    mine, value = _threshold(at), values.get(at)
    if promotion.trigger == "ALWAYS" or mine is None or value is None:
        return False
    for other, theirs in values.items():
        number = _threshold(other)
        if other == at or number is None or theirs is None:
            continue
        if (number > mine and theirs < value) or (number < mine and theirs > value):
            return True
    return False


@dataclass(frozen=True)
class TierChange:
    """짚은 단 하나의 계산. `after` 는 셈한 후 값(셈하지 못했으면 None), `choice` 는 빨간 줄에 고른 것, `said` 는 그렇게 고르며 담당자가
    한 말."""
    offer: str
    promotion: str
    tier: str
    label: str
    before: Decimal | None
    after: Decimal | None
    verdict: str | None
    choice: str | None = None
    said: str | None = None

    @property
    def id(self) -> str:
        """단을 짚는 짧은 글자 — 빨간 줄 고름 · 짧은 답에 쓴다. 「9001 21」(프로모션 번호와 기준값)."""
        return f"{self.promotion} {self.tier}"

    @property
    def key(self) -> str:
        return tier_key(self.promotion, self.tier)

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
        """저장이 이 단에 새 값을 넣는지 — 바꿀 수 없는 단 · 아직 고르지 않은 빨간 줄은 넣지 않는다(안 바꾸기로 고른 단은 고를 때
        후 값이 전 값이 된다)."""
        return self.changed and not self.blocked and not self.waiting

    @property
    def larger(self) -> bool | None:
        """할인이 커지는지(True) · 작아지는지(False) — 넣지 않으면 None."""
        return None if not self.writes else self.after > self.before


@dataclass(frozen=True)
class Plan:
    request: ChangeRequest
    read_at: str
    currency: str
    changes: tuple[TierChange, ...]
    promotions: tuple[Promotion, ...]
    missing: tuple[PromotionRef, ...] = ()

    @property
    def unchanged(self) -> tuple[TierChange, ...]:
        """그대로인 단 — 바뀌지 않거나 안 바꾸기로 고른 단. 바뀌는 · 그대로 · 바꿀 수 없는 · 고를 단이 짚은 단을 빠짐없이 나눈다."""
        return tuple(change for change in self.changes if not change.writes and not change.blocked and not change.waiting)

    def promotion(self, promotion_id: str) -> Promotion:
        return next(promotion for promotion in self.promotions if promotion.id == promotion_id)

    @property
    def unmarked(self) -> tuple[Promotion, ...]:
        """편집 창에 화면 밖 설정을 지키는 표식이 없는 프로모션 — 이 ERP 에서는 저장하지 않는다."""
        return tuple(promotion for promotion in self.promotions if not promotion.keeps)

    @property
    def unsure(self) -> tuple[Promotion, ...]:
        """표식은 있는데 편집 창의 단 줄 가운데 ERP 가 어느 저장된 단에서 왔는지 모르는 줄(`?`)이 있는 프로모션 — 저장하지 않는다."""
        return tuple(promotion for promotion in self.promotions if promotion.keeps and not promotion.origin_known)


def _after(before: Decimal | None, request: ChangeRequest, rounding: Callable[[Decimal], Decimal]) -> Decimal | None:
    if request.how == "value":
        return plain(rounding(request.figure))
    if before is None:
        return None
    if request.how == "amount":
        return plain(rounding(before + request.figure))
    return plain(rounding(before * (HUNDRED + request.figure) / HUNDRED))


def plan_change(snapshot: Snapshot, request: ChangeRequest) -> Plan:
    """짚은 단마다 전 → 후와 판정. 짚은 프로모션 가운데 읽은 값에 없는 것(지워졌거나 번호가 바뀐 것)은 `missing` 이다."""
    if snapshot.hotel_id != request.hotel_id:
        raise PlanError(f"지금 값은 {hotel_label(snapshot.hotel, snapshot.hotel_id)} 것이고 요청은 "
                        f"{hotel_label(request.hotel, request.hotel_id)} 입니다")
    unread = [f"{offer} · {promotion}" for offer, promotion in request.promotions() if not snapshot.covers(promotion)]
    if unread:
        raise PlanError(f"요청한 프로모션 가운데 읽지 않은 것이 있습니다({', '.join(unread)}) — 이 요청 파일로 읽기를 다시 합니다")
    currency = snapshot.currency
    found, promotions, missing = [], {}, []
    for target in request.targets:
        promotion = snapshot.promotions.get(target.promotion)
        if promotion is None:
            missing.append((target.offer, target.promotion))
            continue
        if promotion.offer != target.offer:
            raise PlanError(f"프로모션 {promotion.id}번은 {promotion.listed.offer_name}(오퍼 {promotion.offer}) 카드의 것입니다(요청은 오퍼 "
                            f"{target.offer}) — look 의 번호를 씁니다")
        tier = promotion.tier(target.tier)
        before = promotion.value(tier)
        found.append((target, promotion, tier, before, _after(before, request, rounder(promotion, currency))))
        promotions[promotion.id] = promotion
    if not found and not missing:
        raise PlanError("읽은 값에 요청이 짚은 프로모션이 없습니다")
    changes = []
    for target, promotion, tier, before, after in found:
        planned = {other.at: promotion.value(other) for other in promotion.tiers()}
        then = dict(planned)
        planned.update({t.at: a for t_, p, t, _b, a in found if p.id == promotion.id and a is not None})
        changes.append(TierChange(target.offer, promotion.id, tier.at, promotion.tier_label(tier), before, after,
                                  _verdict(promotion, tier.at, before, after, then, planned)))
    return Plan(request, snapshot.read_at, currency, tuple(changes), tuple(promotions.values()), tuple(dict.fromkeys(missing)))


def _verdict(promotion: Promotion, at: str, before, after, then: Mapping, planned: Mapping) -> str | None:
    if after is not None and after == before:
        return None
    refused = form_refusal(promotion, {at: after}) if after is not None else None
    inverts = _inverted(promotion, at, planned) and not _inverted(promotion, at, then)
    return RULES.verdict(Facts(before, after, promotion.keeps, promotion.basis, refused, promotion.origin_known,
                               free_stay(promotion, at, after), inverts))


def resolve(plan: Plan, resolutions: Iterable[Resolution]) -> Plan:
    """빨간 줄 고름을 단에 단다. 고름의 `items` 는 단의 짧은 글자(「9001 21」)다 — 그 규칙의 단이 아니면 거절한다. 받는 것은 계산이 막 낸
    미리보기(plan_change — 아직 고른 것이 없다)다.

    빨간 줄은 저장될 값으로 판정한다. 처음 판정(plan_change)은 짚은 단을 모두 셈한 값으로 본다. 고른 뒤에는 저장될 사다리 — 「그 단은 안
    바꿈」 · 바꿀 수 없는 단은 지금 값, 넣는 단과 아직 고르기를 기다리는 단은 셈한 값 — 로 다시 본다(saved_ladder). 넣는(또는 기다리는)
    단이 그 사다리에서 다른 단과 뒤집히는데(기준값이 큰 단보다 할인이 크거나 작은 단보다 작음) 처음 판정의 사다리와 지금 값으로는 뒤집히지
    않으면, 그 단은 새 빨간 줄 INVERTS 다 — 앞서 다른 빨간 줄(30% · 0 · 무료)에 「이대로 바꿈」을 골랐어도 그 고름은 뒤집힘을 고른 것이
    아니라 다시 고를 때까지 저장하지 않는다(INVERTS 를 짚은 고름이 있으면 그것을 단다). 「안 바꿈」 고름이 사다리를 바꿔 또 다른 단을
    뒤집을 수 있으니 새 빨간 줄이 더 생기지 않을 때까지 되풀이한다. 빨간 줄은 더해지기만 한다 — 처음 판정의 빨간 줄은 그대로다. 단을 짚은
    고름은 어느 차례에서든 그 규칙에 걸린 단이면 받는다(다른 단을 「안 바꿈」으로 고른 뒤에야 뒤집히는 단이 있다).
    """
    by_id = {change.id: change.key for change in plan.changes}
    keyed = [Resolution(item.rule, item.choice, None if item.items is None else tuple(by_id.get(str(name), str(name))
                                                                                    for name in item.items), item.said)
             for item in resolutions]
    shown = {change.key: change.id for change in plan.changes}
    describe = (lambda key: f"단 {shown.get(key, key)}")
    decide(RULES, {}, [replace(item, items=None) for item in keyed], describe)    # 규칙과 고를 것이 맞는지 — 짚은 단은 아래에서 본다
    verdicts = {change.key: change.verdict for change in plan.changes}
    seen = {key: {code} for key, code in verdicts.items() if code}                # 어느 차례에서든 단이 걸린 규칙
    for _round in range(len(plan.changes) + 1):
        flagged = {key: code for key, code in verdicts.items() if code}
        usable = [replace(item, items=tuple(key for key in item.items if flagged.get(key) == item.rule)) if item.items is not None else item
                  for item in keyed]
        chosen, _waiting = decide(RULES, flagged, [item for item in usable if item.items is None or item.items], describe)
        changes = tuple(_choose(replace(change, verdict=verdicts[change.key]), chosen.get(change.key)) for change in plan.changes)
        turned = _turned(plan, changes)
        if not turned:
            break
        for key in turned:
            verdicts[key] = INVERTS
            seen.setdefault(key, set()).add(INVERTS)
    else:
        raise PlanError("빨간 줄을 다시 보는 차례가 끝나지 않았습니다 — 계산의 결함입니다")
    for item in keyed:
        for key in item.items or ():
            if item.rule not in seen.get(key, ()):
                raise Refused(f"「{RULES.by_code[item.rule].label}」 항목이 아닙니다: {describe(key)}")
    return replace(plan, changes=changes)


def saved_ladder(plan: Plan, promotion: Promotion, changes: Iterable[TierChange] | None = None) -> dict[str, Decimal | None]:
    """저장되면 그 프로모션의 단마다 값 — 넣는 단과 아직 고르기를 기다리는 단은 셈한 값, 그 밖(바꿀 수 없는 단 · 「안 바꿈」 · 짚지 않은
    단)은 지금 값."""
    ladder = {tier.at: promotion.value(tier) for tier in promotion.tiers()}
    ladder.update({change.tier: change.after for change in (plan.changes if changes is None else changes)
                   if change.promotion == promotion.id and (change.writes or change.waiting)})
    return ladder


def _turned(plan: Plan, changes: Sequence[TierChange]) -> set[str]:
    """고른 뒤 저장될 사다리에서 새로 뒤집히는 단의 키 — 넣는(또는 기다리는) 단 가운데 판정이 아직 INVERTS 가 아니고, 저장될 사다리로는
    뒤집히는데 처음 판정의 사다리(짚은 단 모두 셈한 값 — plan_change 의 그것)와 지금 값으로는 뒤집히지 않는 단."""
    turned = set()
    for promotion in plan.promotions:
        now = {tier.at: promotion.value(tier) for tier in promotion.tiers()}
        first = dict(now)
        first.update({change.tier: change.after for change in plan.changes if change.promotion == promotion.id and change.after is not None})
        saved = saved_ladder(plan, promotion, changes)
        turned |= {change.key for change in changes if change.promotion == promotion.id and (change.writes or change.waiting)
                   and change.verdict != INVERTS and _inverted(promotion, change.tier, saved)
                   and not _inverted(promotion, change.tier, first) and not _inverted(promotion, change.tier, now)}
    return turned


def _choose(change: TierChange, resolution: Resolution | None) -> TierChange:
    """고른 것과 그렇게 고르며 한 말을 단다 — 「그 단은 안 바꿈」이면 후 값이 전 값이 된다(다른 도우미와 같다)."""
    if resolution is None:
        return change
    keep = resolution.choice == "keep"
    return replace(change, choice=resolution.choice, said=resolution.said or None, after=change.before if keep else change.after)


def unresolved(plan: Plan) -> tuple[TierChange, ...]:
    return tuple(change for change in plan.changes if change.waiting)


def counts(plan: Plan) -> dict:
    """단 수 — 짚은 단 · 바뀌는 단 · 그대로인 단 · 바꿀 수 없는 단 · 고를 단, 그리고 판정마다. `sent` 는 짚지 않아 창이 보인 그대로
    보내는 단(짚은 프로모션의 다른 단 — 시운전 10 에서 도우미가 페이지를 읽어야만 「그대로인 단」을 말할 수 있었다)."""
    targeted = {(change.promotion, change.tier) for change in plan.changes}
    found = dict(tiers=len(plan.changes), promotions=len(plan.promotions), will_change=sum(c.writes for c in plan.changes),
                 unchanged=len(plan.unchanged),
                 sent=sum((promotion.id, tier.at) not in targeted for promotion in plan.promotions for tier in promotion.tiers()),
                 blocked=sum(c.blocked for c in plan.changes),
                 red=sum(c.waiting for c in plan.changes), chosen=sum(c.choice is not None for c in plan.changes),
                 missing=len(plan.missing))
    for rule in RULES.rules:
        found[rule.code] = sum(change.verdict == rule.code for change in plan.changes)
    return found


# ───────────── 저장 단계 ─────────────

@dataclass(frozen=True)
class Edit:
    """저장이 넣는 단의 값 하나 — 장부의 항목 키와, 창의 몇 번째 값 칸(`tiers_value` 가운데 0 부터) · 넣는 글자."""
    key: str
    nth: int
    value: str


@dataclass(frozen=True)
class PromotionStep:
    """저장 한 번 = 프로모션 하나의 편집 창 [저장] 한 번. `form` 은 창이 보일 칸 전부(읽은 그대로), `marks` 는 단 줄마다 화면 밖 설정의
    이름(읽은 그대로 — 페이지가 누르기 전에 견준다), `edits` 는 바꾸는 단의 값. 만들 때 지킨다: 표식 있는 창만 · 단의 값 칸만 ·
    숫자 글자만(비우지 않는다) · 창에 있고 지금 빈 칸이 아닌 칸만(채우지 않는다) · 한 칸에 한 번."""
    offer: str
    promotion: str
    title: str
    label: str
    form: Form
    marks: tuple[tuple[str, ...], ...]
    keeps: bool
    edits: tuple[Edit, ...]

    kind = "promotion"

    def __post_init__(self):
        if not self.keeps:
            raise PlanError(f"{GATE}: {self.label}")
        if any(value.strip() == UNSURE_ORIGIN for value in form_values(self.form, "tiers_origin")):
            raise PlanError(f"{ORIGIN_UNKNOWN}: {self.label}")
        if not self.edits:
            raise PlanError(f"바꾸는 단이 없는 저장입니다: {self.label}")
        values = form_values(self.form, VALUE)
        if len(self.marks) != len(values):
            raise PlanError(f"단 줄의 표식 수({len(self.marks)})가 값 칸 수({len(values)})와 다릅니다: {self.label}")
        seen = set()
        for edit in self.edits:
            if not TYPED.match(edit.value):
                raise PlanError(f"단의 값 칸에는 0 이상의 숫자만 넣습니다({edit.value!r}): {self.label}")
            if promotion_of_key(edit.key) != self.promotion or part_of_key(edit.key)[1] is None:
                raise PlanError(f"다른 프로모션의 단이거나 단이 아닌 칸입니다: {self.label}")
            if edit.nth in seen:
                raise PlanError(f"같은 단을 두 번 바꿉니다({edit.nth + 1}번째 단): {self.label}")
            seen.add(edit.nth)
            if not 0 <= edit.nth < len(values):
                raise PlanError(f"창에 없는 단입니다({edit.nth + 1}번째 단): {self.label}")
            if not values[edit.nth].strip():
                raise PlanError(f"빈 값은 채우지 않습니다({edit.nth + 1}번째 단): {self.label}")
            threshold = form_values(self.form, "tiers_threshold")[edit.nth]
            if threshold_key(threshold) != part_of_key(edit.key)[1]:
                raise PlanError(f"{edit.nth + 1}번째 단의 기준값({threshold})이 그 단의 키와 다릅니다: {self.label}")
        self.sent()

    def sent(self) -> Form:
        """저장 단추가 보낼 칸 전부 — 읽은 칸에 바꾸는 단의 값만 새 값(change_core.window — 다른 도우미와 같은 걸음)."""
        return with_values(self.form, {(VALUE, edit.nth): edit.value for edit in self.edits})

    def writes(self) -> tuple[FieldWrite, ...]:
        return tuple(FieldWrite(ITEM_KIND, edit.key, "value", money(edit.value)) for edit in self.edits)


def encode_step(step: PromotionStep) -> dict:
    return dict(kind=step.kind, offer=step.offer, promotion=step.promotion, title=step.title, label=step.label,
                form=[list(pair) for pair in step.form], marks=[list(names) for names in step.marks], keeps=step.keeps,
                edits=[dict(key=e.key, nth=e.nth, value=e.value) for e in step.edits])


def decode_step(data: Mapping) -> PromotionStep:
    if data.get("kind") != "promotion":
        raise ModelError(f"프로모션의 저장 단계가 아닙니다: {data.get('kind')}")
    return PromotionStep(str(data["offer"]), str(data["promotion"]), str(data["title"]), str(data["label"]),
                         tuple((str(name), str(value)) for name, value in data["form"]),
                         tuple(tuple(str(name) for name in names) for names in data["marks"]), data.get("keeps") is True,
                         tuple(Edit(str(e["key"]), int(e["nth"]), str(e["value"])) for e in data["edits"]))


def _step(promotion: Promotion, targets: Mapping[str, Decimal]) -> PromotionStep:
    edits = []
    for at, value in targets.items():
        if value is None:
            raise PlanError(f"비우는 저장은 하지 않습니다: {promotion.label} · 기준값 {at} 단")
        edits.append(Edit(tier_key(promotion.id, at), promotion.tier(at).index, typed(value)))
    return PromotionStep(promotion.offer, promotion.id, promotion.name, promotion.label, promotion.form, promotion.marks,
                         promotion.keeps, tuple(edits))


def plan_steps(plan: Plan) -> tuple[PromotionStep, ...] | None:
    """바뀌는 단이 있는 프로모션마다 저장 한 번(짚은 차례). 아직 고르지 않은 빨간 줄이 있으면 None."""
    if unresolved(plan):
        return None
    grouped: dict[str, dict[str, Decimal]] = {}
    for change in plan.changes:
        if change.writes:
            grouped.setdefault(change.promotion, {})[change.tier] = change.after
    return tuple(_step(plan.promotion(promotion_id), targets) for promotion_id, targets in grouped.items())


def step_plans(steps: Iterable[PromotionStep]) -> list[StepPlan]:
    return [StepPlan(step.kind, step.label, encode_step(step), step.writes()) for step in steps]


def step_call(no: int, hotel: str, hotel_id: str, step: PromotionStep) -> dict:
    """장부의 저장 단계 하나 → stayPromotion.applyPromotion 에 그대로 넣을 값."""
    return {"no": no, "op": "applyPromotion", "payload": {
        "no": no, "hotel": encode_hotel(hotel, hotel_id), "offer": step.offer, "promotion": step.promotion, "title": step.title,
        "form": [list(pair) for pair in step.form], "marks": [list(names) for names in step.marks],
        "set": [[VALUE, edit.nth, edit.value] for edit in step.edits]}}


# ───────────── 장부 줄 ─────────────

def _rows(promotion: Promotion, changes: Mapping[str, TierChange] | None = None,
          targets: Mapping[str, Decimal] | None = None) -> list[ValueRow]:
    """프로모션 하나의 단 전부 — 단마다 전 값 · 후 값 · 넣는지 · 판정 · 고른 것과 그 말(미리보기) 또는 되돌릴 값(되돌리기)."""
    rows = []
    for tier in promotion.tiers():
        before = promotion.value(tier)
        change = (changes or {}).get(tier.at)
        if change is not None:
            after, write, verdict, choice, said = change.after, change.writes, change.verdict, change.choice, change.said
        else:
            after = (targets or {}).get(tier.at)
            write, verdict, choice, said = after is not None and after != before, None, None, None
        rows.append(ValueRow(ITEM_KIND, tier_key(promotion.id, tier.at), promotion.tier_label(tier), "value", PRESENT, before,
                             None if after is None or after == before else after, verdict, (),
                             "set" if write else None, choice, said))
    return rows


def preview_rows(plan: Plan) -> list[ValueRow]:
    """짚은 프로모션의 단 전부(바뀌지 않는 단도) — 적용 뒤 견주기가 그 단들이 그대로인지 본다."""
    return [row for promotion in plan.promotions
            for row in _rows(promotion, changes={c.tier: c for c in plan.changes if c.promotion == promotion.id})]


# ───────────── 되돌리기 ─────────────

def promotion_filter(promotions: Iterable[str] = ()) -> tuple[Callable[[str, str], bool] | None, str]:
    """일부만 되돌릴 때 프로모션을 고르는 조건(프로모션 번호)과 그 범위의 글. 아무것도 주지 않으면 `(None, "")` — 변경 전체다."""
    chosen = {str(promotion) for promotion in promotions}
    if not chosen:
        return None, ""
    return (lambda kind, key: kind == ITEM_KIND and promotion_of_key(key) in chosen), "프로모션 " + " · ".join(sorted(chosen)) + "번"


def plan_promotion_rollback(recorded: RecordedChange, later: Mapping[tuple[str, str], Sequence[LaterWrite]], now: Snapshot,
                            include_kept: bool = False, select: Callable[[str, str], bool] | None = None) -> RollbackPlan:
    """프로모션 되돌리기 — 지금 값을 그 프로모션들만큼 읽었는지 보고 공통 되돌리기 계산에 넘긴다. 그 사이 지워진 프로모션 · 단(기준값을
    바꾼 단도), 그리고 그 사이 빈 값이 된 단은 되살릴 길이 없어 그대로 두는 것(까닭: 도우미 밖)으로 남는다."""
    if now.hotel_id != recorded.hotel_id:
        raise PlanError(f"지금 읽은 값은 {hotel_label(now.hotel, now.hotel_id)} 것이고, 되돌릴 변경은 "
                        f"{hotel_label(recorded.hotel, recorded.hotel_id)} 입니다")
    gaps = sorted({promotion_of_key(item.key) for item in recorded.items
                   if item.kind == ITEM_KIND and (select is None or select(item.kind, item.key))
                   and not now.covers(promotion_of_key(item.key))})
    if gaps:
        raise PlanError(f"지금 값을 읽지 않은 프로모션: {', '.join(gaps)}")
    plan = plan_rollback(recorded, later, snapshot_items(now), now.read_at, include_kept, select)
    return replace(plan, restored=tuple(item for item in plan.restored if item.now.state == PRESENT
                                        and all(item.now.fields.get(name) is not None for name in item.targets)))


def _targets(plan: RollbackPlan) -> dict[str, dict[str, Decimal]]:
    grouped: dict[str, dict[str, Decimal]] = {}
    for item in plan.restored:
        promotion, tier = part_of_key(item.key)
        grouped.setdefault(promotion, {})[tier] = item.targets["value"]
    return grouped


def rollback_steps(plan: RollbackPlan, now: Snapshot) -> tuple[PromotionStep, ...]:
    """되돌릴 프로모션마다 저장 한 번 — 지금 편집 창의 칸 전부 + 적어 둔 값. 지금 창에 표식이 없으면 거절한다(PromotionStep)."""
    return tuple(_step(now.promotions[promotion_id], targets) for promotion_id, targets in _targets(plan).items())


def rollback_rows(plan: RollbackPlan, now: Snapshot) -> list[ValueRow]:
    return [row for promotion_id, targets in _targets(plan).items()
            for row in _rows(now.promotions[promotion_id], targets=targets)]


# ───────────── 계산 파일 ─────────────

def encode_change(change: TierChange) -> dict:
    return dict(offer=change.offer, promotion=change.promotion, tier=change.tier, label=change.label,
                before=money_text(change.before), after=money_text(change.after), verdict=change.verdict, choice=change.choice,
                said=change.said)


def decode_change(data: Mapping) -> TierChange:
    return TierChange(str(data["offer"]), str(data["promotion"]), str(data["tier"]), str(data["label"]), money(data["before"]),
                      money(data["after"]), data["verdict"], data["choice"], data.get("said"))


def encode_plan(plan: Plan, encode_request) -> dict:
    return dict(request=encode_request(plan.request), read_at=plan.read_at, currency=plan.currency,
                changes=[encode_change(change) for change in plan.changes],
                promotions=[encode_promotion(promotion) for promotion in plan.promotions],
                missing=[dict(offer=offer, promotion=promotion) for offer, promotion in plan.missing])


def decode_plan(data: Mapping, decode_request) -> Plan:
    return Plan(decode_request(data["request"]), str(data["read_at"]), str(data["currency"]),
                tuple(decode_change(change) for change in data["changes"]),
                tuple(decode_promotion(promotion) for promotion in data["promotions"]),
                tuple((str(item["offer"]), str(item["promotion"])) for item in data["missing"]))
