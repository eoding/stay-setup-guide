"""시험용 — 지어낸 호텔 하나의 프로모션(tests/fixtures/erp/promotions.json)과, 페이지(`window.stayPromotion`)가 돌려줄 답을 파이썬에서 만든다.

`Erp` 는 프로모션마다 저장된 값을 들고 있는 작은 ERP 다. 편집 창은 PromotionEditForm 처럼 그리고(`form_of`), 저장은 서버처럼 한다
(`apply` — 창이 읽은 값 · 표식과 다르거나 표식이 없으면 페이지처럼 거절하고, 받은 칸을 폼처럼 검사해 할인 규칙을 다시 만든다). 화면 밖
설정을 지키는 ERP(`keeps` — 데이터의 `keeps`)는 행이 불러온 저장 단(`tiers_origin`)의 화면 밖 설정과 저장된 표기를 잇고, 지키지 않는
ERP 는 폼 값으로 새로 써 그 설정을 지운다(services/promotion.keep_off_form_keys · build_trigger). 목록 줄은 `_promotions_panel.html`
처럼 그린다(`row_of`). 답의 모양은 진짜 페이지 모듈이 낸 답(tests/fixtures/browser/)과 같다 — tests/test_golden.py 가 견준다. 조각을
나누는 일은 가격 캘린더 도우미의 시험 받침(`browser_replies.reply`)을 그대로 쓴다.

unittest 가 찾지 않도록 이름이 test_ 로 시작하지 않는다. 이름 · 번호 · 값은 모두 지어낸 것이다(공개 저장소).
"""

import copy
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL.parent / "stay-price-change" / "scripts"))

from change_core.answers import ask_sum as ask  # noqa: E402


def _price_test_helper(name: str):
    spec = importlib.util.spec_from_file_location(f"price_{name}", SKILL.parent / "stay-price-change" / "tests" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_replies = _price_test_helper("browser_replies")
done_at, reply = _replies.done_at, _replies.reply

DATA = json.loads((HERE / "fixtures" / "erp" / "promotions.json").read_text(encoding="utf-8"))
HOTEL = DATA["hotel"]
START = datetime(2026, 11, 23, 1, 0, tzinfo=timezone.utc)
TRIGGERS = {"ALWAYS": "상시 — 조건 없이 항상", "LOS": "연박 — N박 이상 묵으면", "LEAD_TIME": "얼리버드 — 체크인 D-N일 전에 예약하면",
            "ROOM_COUNT": "객실 수 — N개 이상 잡으면"}
BASES = {"PCT": "정률 — 요금의 %", "FLAT": "정액 — 금액을 뺀다", "FREE_NIGHT": "무료 숙박 — N박을 공짜로 (STAY5PAY4형)"}
UNITS = {0: "박당", 1: "체류당 1회"}
UNIT_NAMES = {0: "PER_NIGHT", 1: "PER_STAY"}
VALUE_KEYS = {"PCT": "pct", "FLAT": "amount", "FREE_NIGHT": "free_nights"}
THRESHOLD_LABELS = {"LOS": "최소 숙박(박)", "LEAD_TIME": "체크인 D-N일 전", "ROOM_COUNT": "최소 객실 수", "ALWAYS": "기준 없음"}
LIST_TRIGGERS = {"ALWAYS": "상시 · 조건 없이 항상", "LOS": "연박", "LEAD_TIME": "얼리버드", "ROOM_COUNT": "객실 수"}
COMMON = {"id": "0", "name": "전 오퍼 공통"}


def text(value) -> str:
    return "" if value is None else str(value)


def offer_of(card: dict) -> dict:
    return card["offer"] or COMMON


def off_keys(promotion: dict, tier: dict) -> list[str]:
    """그 단의 화면 밖 설정의 이름 — 기준값과 저장된 혜택 방식의 값 키를 뺀 나머지(services/promotion._off_form)."""
    value_key = VALUE_KEYS.get(promotion["trigger"]["basis"])
    return [key for key in tier if key not in ("threshold", value_key)]


def form_of(card: dict, promotion: dict, keeps: bool) -> list[list[str]]:
    """편집 창이 보낼 칸 — PromotionEditForm 이 저장된 프로모션으로 그린 창의 [이름, 값] 쌍, 창(hx-include)의 차례 그대로."""
    trigger = promotion["trigger"]
    value_key = VALUE_KEYS[trigger["basis"]]
    form = [["title", promotion["title"]], ["code", promotion["code"]], ["trigger_type", trigger["type"]], ["basis", trigger["basis"]],
            ["unit", str(promotion["unit"])], ["tiers_submitted", "1"]]
    for tier in trigger["tiers"]:
        form += ([["tiers_origin", str(tier["threshold"])]] if keeps else []) + [
            ["tiers_threshold", str(tier["threshold"])], ["tiers_value", text(tier.get(value_key))]]
    form += [["start_date", promotion["start"]], ["end_date", promotion["end"]]]
    form += [["promotion_apply_flag", "on"]] if promotion["apply_flag"] else []
    form += [["promotion_apply_start_date", promotion["apply_start"]], ["promotion_apply_end_date", promotion["apply_end"]],
             ["season", text(promotion["season"])], ["rate_plan", text(promotion["rate_plan"])]]
    form += [["combinability", "on"]] if promotion["combinability"] else []
    return form + [["exclusivity_group", promotion["group"]], ["cancellation_policy", text(promotion["policy"])],
                   ["scope_rate_plan_mode", "0"], ["scope_room_mode", "0"]]


def labels_of(card: dict, promotion: dict) -> dict:
    season = next((s for s in card["seasons"] if s["id"] == promotion["season"]), None)
    plan = next((p for p in DATA["rate_plans"] if p["id"] == promotion["rate_plan"]), None)
    policy = next((p for p in DATA["policies"] if p["id"] == promotion["policy"]), None)
    return {"trigger_type": TRIGGERS[promotion["trigger"]["type"]], "basis": BASES[promotion["trigger"]["basis"]],
            "unit": UNITS[promotion["unit"]], "season": f"{offer_of(card)['name']} · {season['name']}" if season else "(전 시즌)",
            "rate_plan": plan["name"] if plan else "(전 요금제)",
            "cancellation_policy": policy["name"] if policy else "(요금제·오퍼 정책을 따름)",
            "scope_rate_plan_mode": "기존 범위 그대로", "scope_room_mode": "기존 범위 그대로"}


def marks_of(promotion: dict, keeps: bool) -> list[list[str]]:
    return [off_keys(promotion, tier) if keeps else [] for tier in promotion["trigger"]["tiers"]]


def benefit_lines(promotion: dict) -> list[str]:
    """목록의 「혜택」 칸이 보이는 줄들 — 단마다 「기준 라벨 기준값 → 값」(상시는 값만), 단이 여럿이면 안내 한 줄."""
    trigger = promotion["trigger"]
    lines = []
    for tier in trigger["tiers"]:
        value = tier.get(VALUE_KEYS[trigger["basis"]])
        shown = {"PCT": f"{value}%", "FLAT": f"{value} {DATA['currency']}", "FREE_NIGHT": f"{value}박 무료"}[trigger["basis"]]
        lines.append(shown if trigger["type"] == "ALWAYS" else f"{THRESHOLD_LABELS[trigger['type']]} {tier['threshold']} → {shown}")
    return lines + (["※ 만족하는 단 중 가장 높은 하나만 적용"] if len(trigger["tiers"]) > 1 else [])


def row_of(card: dict, promotion: dict) -> dict:
    season = next((s for s in card["seasons"] if s["id"] == promotion["season"]), None)
    plan = next((p for p in DATA["rate_plans"] if p["id"] == promotion["rate_plan"]), None)
    limits = ([f"시즌 {season['name']}"] if season else []) + ["요금제: 기존 범위 그대로", "객실: 기존 범위 그대로"]
    limits += [f"요금제 {plan['name']}"] if plan else []
    limits.append(f"숙박일 {promotion['start'] or '…'} ~ {promotion['end'] or '…'}" if promotion["start"] or promotion["end"]
                  else "숙박일 제한 없음")
    if promotion["apply_flag"]:
        limits.append(f"예약일 {promotion['apply_start'] or '…'} ~ {promotion['apply_end'] or '…'}")
    warnings = (["진행기간이 비어 있습니다. 후보에서 빠져 고객이 고르면 예약이 거부됩니다."]
                if promotion["apply_flag"] and not (promotion["apply_start"] and promotion["apply_end"]) else [])
    return {"id": promotion["id"], "title": promotion["title"], "code": promotion["code"],
            "trigger": LIST_TRIGGERS[promotion["trigger"]["type"]], "benefit": benefit_lines(promotion),
            "combo": ["중복 가능" if promotion["combinability"] else "택일"] + ([f"배타 그룹 {promotion['group']}"] if promotion["group"] else []),
            "limits": limits, "warnings": warnings}


def window_of(card: dict, promotion: dict, keeps: bool) -> dict:
    return {"title": f"프로모션 편집 — {promotion['title']}", "form": form_of(card, promotion, keeps), "labels": labels_of(card, promotion),
            "keeps": keeps, "marks": marks_of(promotion, keeps), "errors": []}


def _number(value: str):
    try:
        number = Decimal(value.strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


class Erp:
    """프로모션들의 지금 상태와 시계. 읽기 · 저장마다 답의 끝난 시각이 10초씩 간다. `posts` 는 저장 요청이 실어 보낸 쌍들이다.
    `keeps` 가 False 면 화면 밖 설정을 지키지 않는 ERP(표식 없음 · 저장이 그 설정을 지운다)다."""

    def __init__(self, data=None, keeps=None):
        self.data = copy.deepcopy(data or DATA)
        if keeps is not None:
            self.data["keeps"] = keeps
        self.clock = START
        self.posts = []
        self.reads = 0

    @property
    def keeps(self) -> bool:
        return bool(self.data["keeps"])

    def tick(self) -> str:
        self.clock += timedelta(seconds=10)
        return done_at(self.clock)

    def cards(self):
        """목록의 차례 — 데이터의 카드 차례, 카드 안은 데이터의 차례."""
        for card in self.data["cards"]:
            yield card, card["promotions"]

    def find(self, offer_id: str, promotion_id: str):
        for card, promotions in self.cards():
            for promotion in promotions:
                if offer_of(card)["id"] == offer_id and promotion["id"] == promotion_id:
                    return card, promotion
        return None, None

    def promotion(self, promotion_id: str) -> dict:
        return next(p for c in self.data["cards"] for p in c["promotions"] if p["id"] == promotion_id)

    def read_promotion(self, call):
        """readPromotion 하나의 답(작은 답 + take 답들). 목록에 없는 프로모션이면 missing."""
        asked = {key: call[key] for key in ("hotel", "offer", "promotion")}
        card, promotion = self.find(call["offer"], call["promotion"])
        self.reads += 1
        if promotion is None:
            return reply("readPromotion", asked, None, missing=True, doneAt=self.tick(),
                         note="목록에 그 카드의 그 프로모션이 없습니다 — 아무것도 열지 않았습니다")
        keep = {"hotel": HOTEL, "offer": offer_of(card), "promotion": row_of(card, promotion),
                "window": window_of(card, promotion, self.keeps)}
        return reply("readPromotion", asked, keep, pieces=3, body_id=f"b{self.reads}",
                     what=f"{offer_of(card)['name']} · {promotion['title']}", doneAt=self.tick())

    def apply(self, payload, outcome=True):
        """applyPromotion 하나 — 창에 표식이 있고, 창의 칸 · 단의 표식이 payload 의 form · marks 와 같을 때만 form + set 을 보내고, 폼처럼
        검사해 저장한다. `outcome` 이 False 면 서버가 거절, "unknown" 이면 눌렀지만 알 수 없음(상태는 바뀐다)."""
        card, promotion = self.find(payload["offer"], payload["promotion"])
        base = {"op": "applyPromotion", "no": payload["no"], "ask": ask(payload), "doneAt": self.tick()}
        refused = dict(base, ok=False, saved=False, pressed=False, refused=True)
        if not self.keeps:
            return dict(refused, error="이 ERP 는 아직 프로모션을 화면으로 저장하면 화면에 안 보이는 설정이 지워질 수 있어, 도우미가 저장하지 "
                                       "않습니다 — 아무것도 치지 않았고 누르지 않았습니다")
        if marks_of(promotion, True) != payload["marks"]:
            return dict(refused, error="창의 단 표식(화면에 없는 설정)이 읽은 것과 다릅니다 — 아무것도 치지 않았고 누르지 않았습니다")
        if form_of(card, promotion, True) != payload["form"]:
            return dict(refused, error="창의 값이 읽은 값과 다릅니다 — 아무것도 치지 않았고 누르지 않았습니다")
        edits = {(name, nth): value for name, nth, value in payload["set"]}
        seen, sent = {}, []
        for name, value in payload["form"]:
            nth = seen.get(name, 0)
            seen[name] = nth + 1
            sent.append([name, edits.get((name, nth), value)])
        return self.post(card, promotion, sent, base, outcome)

    def post(self, card, promotion, sent, base, outcome=True):
        """저장 요청 하나 — 보낸 칸을 폼처럼 검사하고 서버처럼 저장한다."""
        self.posts.append(sent)
        errors = self.check(sent)
        if outcome is False or errors:
            return dict(base, ok=False, saved=False, pressed=True,
                        error="프로모션 편집 창이 저장을 거절했습니다 — " + (" / ".join(errors) or "적용 범위 오류"))
        self.save(promotion, sent)
        if outcome == "unknown":
            return dict(base, ok=False, saved="unknown", pressed=True, error="[저장] 은 눌렸고 저장됐는지 알 수 없습니다")
        return dict(base, ok=True, saved=True, pressed=True, note="저장했습니다", what=f"{offer_of(card)['name']} · {promotion['title']}")

    @staticmethod
    def check(sent) -> list[str]:
        """PromotionEditForm.clean 가운데 이 시험에 닿는 것."""
        get = lambda name: next((v for k, v in sent if k == name), "")  # noqa: E731
        every = lambda name: [v for k, v in sent if k == name]  # noqa: E731
        errors = []
        if not get("title").strip():
            errors.append("필수 항목입니다.")
        basis, trigger = get("basis"), get("trigger_type")
        rows = [(t, v) for t, v in zip(every("tiers_threshold"), every("tiers_value")) if t.strip() or v.strip()]
        if not rows:
            return errors + ["최소 한 단은 있어야 합니다"]
        thresholds = []
        for index, (raw_threshold, raw_value) in enumerate(rows, 1):
            threshold, value = _number(raw_threshold), _number(raw_value)
            if threshold is None or threshold != int(threshold) or threshold < 0:
                return errors + [f"{index}번째 단의 기준값은 정수여야 합니다"]
            if value is None or value < 0:
                return errors + [f"{index}번째 단의 값은 0 이상이어야 합니다"]
            if basis == "PCT" and value > 100:
                return errors + [f"{index}번째 단의 할인율은 0~100 사이여야 합니다"]
            if basis == "FREE_NIGHT" and value != value.to_integral_value():
                return errors + [f"{index}번째 단의 무료 숙박은 박 단위 정수여야 합니다"]
            thresholds.append(int(threshold))
        if trigger == "ALWAYS" and any(thresholds):
            errors.append("‘상시’ 는 기준값을 보지 않습니다")
        if len(set(thresholds)) != len(thresholds):
            errors.append("기준값이 같은 단이 둘 이상입니다")
        if get("promotion_apply_flag") and not (get("promotion_apply_start_date") and get("promotion_apply_end_date")):
            errors.append("진행기간 제한을 켜면 시작일과 종료일이 필요합니다")
        return errors

    def save(self, promotion: dict, sent) -> None:
        """서버의 저장 — 받은 칸으로 덮어쓰고 할인 규칙을 다시 만든다. 지키는 ERP 는 행이 불러온 저장 단의 화면 밖 설정과, 숫자가 같으면
        저장된 표기를 잇는다(services/promotion.keep_off_form_keys · _merged_tier)."""
        get = lambda name: next((v for k, v in sent if k == name), "")  # noqa: E731
        every = lambda name: [v for k, v in sent if k == name]  # noqa: E731
        stored = promotion["trigger"]
        old_key = VALUE_KEYS.get(stored["basis"])
        basis = get("basis")
        value_key = VALUE_KEYS[basis]
        origins = every("tiers_origin") if self.keeps else [None] * len(every("tiers_threshold"))
        tiers = []
        for threshold, value, origin in zip(every("tiers_threshold"), every("tiers_value"), origins):
            number = Decimal(value)
            row = {"threshold": int(threshold), value_key: int(number) if basis == "FREE_NIGHT" else str(number)}
            source = next((tier for tier in stored["tiers"] if origin and str(tier["threshold"]) == origin), None)
            if source is not None:
                if value_key == old_key and Decimal(str(source[value_key])) == number:
                    row[value_key] = source[value_key]
                for key in off_keys(promotion, source):
                    row.setdefault(key, source[key])
            tiers.append(row)
        promotion["trigger"] = {"type": get("trigger_type"), "basis": basis, "unit": UNIT_NAMES[int(get("unit"))], "tiers": tiers}
        promotion.update(title=get("title"), code=get("code"), unit=int(get("unit")), combinability=bool(get("combinability")),
                         group=get("exclusivity_group"), season=get("season") or None, rate_plan=get("rate_plan") or None,
                         start=get("start_date"), end=get("end_date"), apply_flag=bool(get("promotion_apply_flag")),
                         apply_start=get("promotion_apply_start_date"), apply_end=get("promotion_apply_end_date"),
                         policy=get("cancellation_policy") or None)


def write_answers(folder: Path, prefix: str, answers) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for index, answer in enumerate(answers, 1):
        (folder / f"{prefix}-{index}.json").write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")


def look_answer(erp: Erp, body_id: str = "blook"):
    """look 의 답(작은 답 + take 답들) — 지금 상태의 카드와 프로모션 전부."""
    offers = [dict(offer_of(card), promotions=[row_of(card, promotion) for promotion in promotions])
              for card, promotions in erp.cards()]
    keep = {"hotel": HOTEL, "offers": offers}
    return reply("look", {}, keep, pieces=4, body_id=body_id, login=False, hotel=HOTEL,
                 count={"offers": len(offers), "promotions": sum(len(o["promotions"]) for o in offers)}, doneAt=erp.tick())
