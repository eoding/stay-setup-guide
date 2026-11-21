"""시험용 — 지어낸 호텔 하나의 부과금(tests/fixtures/erp/charges.json)과, 페이지(`window.stayCharge`)가 돌려줄 답을 파이썬에서 만든다.

`Erp` 는 부과금마다 저장된 값을 들고 있는 작은 ERP 다. 편집 창은 ChargeEditForm 처럼 그리고(`form_of`), 저장은 서버처럼 한다
(`apply` — 창이 읽은 값과 다르면 페이지처럼 거절하고, 받은 칸을 폼처럼 검사해 시간대 요율 줄과 연령별 단가를 받은 대로 다시 만든다).
목록 줄은 `_charges_panel.html` 처럼 그린다(`row_of`). 답의 모양은 진짜 페이지 모듈이 낸 답(tests/fixtures/browser/)과 같다 —
tests/test_golden.py 가 견준다. 조각을 나누는 일은 가격 캘린더 도우미의 시험 받침(`browser_replies.reply`)을 그대로 쓴다.

unittest 가 찾지 않도록 이름이 test_ 로 시작하지 않는다. 이름 · 번호 · 금액은 모두 지어낸 것이다(공개 저장소).
"""

import copy
import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL.parent / "stay-price-change" / "scripts"))

from change_core.answers import ask_sum as ask  # noqa: E402


def _price_test_helper(name: str):
    """가격 캘린더 도우미의 시험 받침 하나를 그 파일 자리로 올린다 — 그 시험 폴더를 sys.path 에 넣으면 이름이 같은 시험 파일이 섞인다."""
    spec = importlib.util.spec_from_file_location(f"price_{name}", SKILL.parent / "stay-price-change" / "tests" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_replies = _price_test_helper("browser_replies")
done_at, reply = _replies.done_at, _replies.reply

DATA = json.loads((HERE / "fixtures" / "erp" / "charges.json").read_text(encoding="utf-8"))
HOTEL = DATA["hotel"]
START = datetime(2026, 11, 21, 1, 0, tzinfo=timezone.utc)
KINDS = {0: "얼리 체크인", 1: "레이트 체크아웃", 9: "기타"}
BASES = {0: "정액", 1: "1박 요금의 %"}
PERS = {0: "체류당 1회", 1: "박당", 2: "인당"}
MODES = {"blank": "미정 (비움)", "set": "지정 (0 포함)"}
DATE_MODES = {"optional": "선택 — 고객이 고를 때만 붙습니다", "mandatory": "의무 — 고객 선택 없이 자동으로 붙습니다"}
TWO = Decimal("0.01")


def text(value) -> str:
    return "" if value is None else str(value)


def two(value: str) -> str:
    """DecimalField(소수 둘)에 저장된 값이 창에 다시 그려지는 글자."""
    return str(Decimal(value).quantize(TWO))


def form_of(offer: dict, charge: dict) -> list[list[str]]:
    """편집 창이 보낼 칸 — ChargeEditForm 이 저장된 부과금으로 그린 창의 [이름, 값] 쌍, 창의 차례 그대로."""
    form = [["kind", str(charge["kind"])], ["name", charge["name"]], ["basis", str(charge["basis"])], ["per", str(charge["per"])],
            ["amount_mode", "set" if charge["amount"] is not None else "blank"], ["amount", text(charge["amount"])],
            ["pct_mode", "set" if charge["pct"] is not None else "blank"], ["pct", text(charge["pct"])],
            ["date_mode", "mandatory" if charge["mandatory"] else "optional"], ["date_scope", ", ".join(charge["dates"])]]
    form += [["room_scope", room["id"]] for room in offer["rooms"] if room["id"] in charge["rooms"]]
    form += [["onsite_currency", text(charge["onsite_currency"])], ["onsite_amount", text(charge["onsite_amount"])]]
    form += [[f"onsite_age_rate_{band['id']}", text(charge["onsite_ages"].get(band["id"]))] for band in offer["bands"]]
    form += [[f"age_rate_{band['id']}", text(charge["ages"].get(band["id"]))] for band in offer["bands"]]
    form += [["tiers_submitted", "1"]]
    for tier in charge["tiers"]:
        form += [["tiers_time_from", tier["from"]], ["tiers_time_to", tier["to"]], ["tiers_basis", str(tier["basis"])],
                 ["tiers_amount", text(tier["amount"])], ["tiers_pct", text(tier["pct"])]]
    return form + [["description", charge["description"]], ["scope_room_mode", "0"]]


def labels_of(charge: dict) -> dict:
    currency = next((c["code"] for c in DATA["currencies"] if c["id"] == charge["onsite_currency"]), "---------")
    labels = {"kind": KINDS[charge["kind"]], "basis": BASES[charge["basis"]], "per": PERS[charge["per"]],
              "amount_mode": MODES["set" if charge["amount"] is not None else "blank"],
              "pct_mode": MODES["set" if charge["pct"] is not None else "blank"],
              "date_mode": DATE_MODES["mandatory" if charge["mandatory"] else "optional"], "onsite_currency": currency}
    if charge["tiers"]:
        labels["tiers_basis"] = "\n".join(BASES[tier["basis"]] for tier in charge["tiers"])
    labels["scope_room_mode"] = "기존 범위 그대로"
    return labels


def bands_of(offer: dict) -> list[dict]:
    return ([{"field": f"onsite_age_rate_{band['id']}", "code": band["code"], "label": band["name"]} for band in offer["bands"]]
            + [{"field": f"age_rate_{band['id']}", "code": band["code"], "label": band["name"]} for band in offer["bands"]])


def money(value: str) -> str:
    return f"{Decimal(value):,.2f}"


def amount_lines(offer: dict, charge: dict) -> list[str]:
    """목록의 「금액」 칸이 보이는 줄들(_charges_panel.html · ChargeRow.amount_text)."""
    cur = DATA["currency"]
    tiers = charge["tiers"]
    has = charge["amount"] is not None or charge["pct"] is not None or any(
        t["amount"] is not None or t["pct"] is not None for t in tiers)
    if not has:
        lines = ["미정 판매 차단" if charge["mandatory"] else "미정"]
    elif tiers:
        lines = [f"{t['from']} ~ {t['to']} · {BASES[t['basis']]}: "
                 + (f"{money(t['amount'])} {cur}" if t["basis"] == 0 else f"{money(t['pct'])}%") for t in tiers]
    else:
        parts = ([money(charge["amount"])] if charge["amount"] is not None else []) + (
            [f"{money(charge['pct'])}%"] if charge["pct"] is not None else [])
        lines = [" · ".join(parts) + (f" {cur}" if charge["basis"] == 0 else "")]
    lines.append(PERS[charge["per"]])
    rated = [band for band in offer["bands"] if band["id"] in charge["ages"]]
    if rated:
        lines.append("연령별 단가: " + " · ".join(band["name"] for band in rated))
        lines += [f"{band['name']}: {money(charge['ages'][band['id']])} {cur}" for band in rated]
    if charge["onsite_currency"]:
        code = next(c["code"] for c in DATA["currencies"] if c["id"] == charge["onsite_currency"])
        lines.append(f"현장 결제: {charge['onsite_amount'] if charge['onsite_amount'] is not None else '미설정'} {code}")
        lines += [f"{band['name']} 현장 결제: {charge['onsite_ages'][band['id']]} {code}" for band in rated
                  if charge["onsite_ages"].get(band["id"]) is not None]
    return lines


def row_of(offer: dict, charge: dict) -> dict:
    rooms = [room["name"] for room in offer["rooms"] if room["id"] in charge["rooms"]]
    if charge["mandatory"]:
        dates = "의무 " + (f"지정 {len(charge['dates'])}일 {', '.join(charge['dates'])}" if charge["dates"] else "오퍼 전 기간")
    else:
        dates = "선택 항목 (고객이 고를 때만)"
    return {"id": charge["id"], "name": charge["name"], "kind": KINDS[charge["kind"]], "basis": BASES[charge["basis"]],
            "amount": amount_lines(offer, charge), "scope": f"{', '.join(rooms) if rooms else '이 오퍼의 모든 객실'} · 객실: 기존 범위 그대로",
            "dates": dates}


def window_of(offer: dict, charge: dict) -> dict:
    return {"title": f"부과금 편집 — {charge['name']}", "currency": DATA["currency"], "form": form_of(offer, charge),
            "labels": labels_of(charge), "bands": bands_of(offer), "errors": []}


def _decimal(value: str) -> Decimal | None:
    value = (value or "").strip()
    if not value:
        return None
    if not re.fullmatch(r"-?\d+(\.\d+)?", value):
        raise ValueError(value)
    return Decimal(value)


class Erp:
    """부과금들의 지금 상태와 시계. 읽기 · 저장마다 답의 끝난 시각이 10초씩 간다. `posts` 는 저장 요청이 실어 보낸 쌍들이다."""

    def __init__(self, data=None):
        self.data = copy.deepcopy(data or DATA)
        self.clock = START
        self.posts = []
        self.reads = 0

    def tick(self) -> str:
        self.clock += timedelta(seconds=10)
        return done_at(self.clock)

    def offers(self):
        """목록의 차례 — 오퍼는 번호가 큰 것부터, 부과금은 종류 · 번호 차례(build_charge_groups)."""
        for offer in sorted(self.data["offers"], key=lambda o: -int(o["id"])):
            yield offer, sorted(offer["charges"], key=lambda c: (c["kind"], int(c["id"])))

    def find(self, offer_id: str, charge_id: str):
        for offer, charges in self.offers():
            for charge in charges:
                if offer["id"] == offer_id and charge["id"] == charge_id:
                    return offer, charge
        return None, None

    def charge(self, charge_id: str) -> dict:
        return next(c for o in self.data["offers"] for c in o["charges"] if c["id"] == charge_id)

    def read_charge(self, call):
        """readCharge 하나의 답(작은 답 + take 답들). 목록에 없는 부과금이면 missing."""
        asked = {key: call[key] for key in ("hotel", "offer", "charge")}
        offer, charge = self.find(call["offer"], call["charge"])
        self.reads += 1
        if charge is None:
            return reply("readCharge", asked, None, missing=True, doneAt=self.tick(),
                         note="목록에 그 오퍼의 그 부과금이 없습니다 — 아무것도 열지 않았습니다")
        keep = {"hotel": HOTEL, "offer": {"id": offer["id"], "name": offer["name"]}, "charge": row_of(offer, charge),
                "window": window_of(offer, charge)}
        return reply("readCharge", asked, keep, pieces=3, body_id=f"b{self.reads}", what=f"{offer['name']} · {charge['name']}",
                     doneAt=self.tick())

    def apply(self, payload, outcome=True):
        """applyCharge 하나 — 창의 칸이 payload 의 form 과 같을 때만 form + set 을 보내고, 폼처럼 검사해 저장한다.
        `outcome` 이 False 면 서버가 거절, "unknown" 이면 눌렀지만 알 수 없음(상태는 바뀐다)."""
        offer, charge = self.find(payload["offer"], payload["charge"])
        base = {"op": "applyCharge", "no": payload["no"], "ask": ask(payload), "doneAt": self.tick()}
        if form_of(offer, charge) != payload["form"]:
            return dict(base, ok=False, saved=False, pressed=False, refused=True,
                        error="창의 값이 읽은 값과 다릅니다 — 아무것도 치지 않았고 누르지 않았습니다")
        edits = {(name, nth): value for name, nth, value in payload["set"]}
        seen, sent = {}, []
        for name, value in payload["form"]:
            nth = seen.get(name, 0)
            seen[name] = nth + 1
            sent.append([name, edits.get((name, nth), value)])
        self.posts.append(sent)
        errors = self.check(offer, sent)
        if outcome is False or errors:
            return dict(base, ok=False, saved=False, pressed=True,
                        error="부과금 편집 창이 저장을 거절했습니다 — " + (" / ".join(errors) or "적용 범위 오류"))
        self.save(offer, charge, sent)
        if outcome == "unknown":
            return dict(base, ok=False, saved="unknown", pressed=True, error="[저장] 은 눌렸고 저장됐는지 알 수 없습니다")
        return dict(base, ok=True, saved=True, pressed=True, note="저장했습니다", what=f"{offer['name']} · {charge['name']}")

    @staticmethod
    def check(offer: dict, sent) -> list[str]:
        """ChargeEditForm.clean 가운데 이 시험에 닿는 것."""
        get = lambda name: next((v for k, v in sent if k == name), "")  # noqa: E731
        every = lambda name: [v for k, v in sent if k == name]  # noqa: E731
        errors = []
        try:
            numbers = {name: _decimal(value) for name, value in sent
                       if re.match(r"^(amount|pct|onsite_amount|age_rate_\d+|onsite_age_rate_\d+)$", name)}
            tiers = list(zip(every("tiers_time_from"), every("tiers_basis"), map(_decimal, every("tiers_amount")),
                             map(_decimal, every("tiers_pct"))))
        except ValueError as bad:
            return [f"숫자를 입력하세요: {bad}"]
        if any(value is not None and value < 0 for value in numbers.values()):
            errors.append("0 이상이어야 합니다")
        basis, per = get("basis"), get("per")
        if get("amount_mode") == "set" and basis == "0" and numbers.get("amount") is None:
            errors.append("정액 금액 값을 입력하세요 — 0 도 유효한 값입니다")
        if get("pct_mode") == "set" and basis == "1" and numbers.get("pct") is None:
            errors.append("정률(%) 값을 입력하세요 — 0 도 유효한 값입니다")
        for index, (_start, tier_basis, amount, pct) in enumerate(tiers, 1):
            if (tier_basis == "0" and amount is None) or (tier_basis == "1" and pct is None):
                errors.append(f"{index}번째 티어의 금액이 필요합니다")
        ages = [numbers[f"age_rate_{b['id']}"] for b in offer["bands"] if numbers.get(f"age_rate_{b['id']}") is not None]
        onsite_ages = [numbers[f"onsite_age_rate_{b['id']}"] for b in offer["bands"]
                       if numbers.get(f"onsite_age_rate_{b['id']}") is not None]
        if ages and (per != "2" or basis != "0" or tiers):
            errors.append("연령별 단가를 넣으려면 인당 · 정액 · 시간 요율 없음이어야 합니다")
        amount = numbers.get("amount") if basis == "0" and get("amount_mode") == "set" else None
        if get("onsite_currency") and (basis != "0" or amount != 0 or tiers or any(a != 0 for a in ages)):
            errors.append("현장 결제 항목의 온라인 정액·연령별 금액은 0으로 두고 시간 티어를 비우세요.")
        if (numbers.get("onsite_amount") is not None or onsite_ages) and not get("onsite_currency"):
            errors.append("현장 결제 통화를 선택하세요.")
        return errors

    @staticmethod
    def save(offer: dict, charge: dict, sent) -> None:
        """서버의 저장 — 받은 칸으로 덮어쓰고, 시간대 요율 줄과 연령별 단가는 받은 대로 다시 만든다(charge.save_charge)."""
        get = lambda name: next((v for k, v in sent if k == name), "")  # noqa: E731
        every = lambda name: [v for k, v in sent if k == name]  # noqa: E731
        basis = int(get("basis"))
        value = lambda name: two(get(name)) if get(name).strip() else None  # noqa: E731
        charge.update(kind=int(get("kind")), name=get("name"), basis=basis, per=int(get("per")),
                      amount=value("amount") if basis == 0 and get("amount_mode") == "set" else None,
                      pct=value("pct") if basis == 1 and get("pct_mode") == "set" else None,
                      mandatory=get("date_mode") == "mandatory",
                      dates=[d for d in re.split(r"[,\s]+", get("date_scope")) if d] if get("date_mode") == "mandatory" else [],
                      rooms=every("room_scope"), onsite_currency=get("onsite_currency") or None,
                      onsite_amount=value("onsite_amount"), description=get("description"))
        charge["tiers"] = [dict(**{"from": start, "to": end}, basis=int(b), amount=two(a) if b == "0" else None,
                                pct=two(p) if b == "1" else None)
                           for start, end, b, a, p in zip(every("tiers_time_from"), every("tiers_time_to"), every("tiers_basis"),
                                                          every("tiers_amount"), every("tiers_pct"))]
        online = {b["id"]: two(get(f"age_rate_{b['id']}")) for b in offer["bands"] if get(f"age_rate_{b['id']}").strip()}
        onsite = {b["id"]: two(get(f"onsite_age_rate_{b['id']}")) for b in offer["bands"]
                  if get(f"onsite_age_rate_{b['id']}").strip()}
        charge["ages"] = {band: online.get(band, "0.00") for band in [b["id"] for b in offer["bands"]] if band in online or band in onsite}
        charge["onsite_ages"] = onsite


def write_answers(folder: Path, prefix: str, answers) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for index, answer in enumerate(answers, 1):
        (folder / f"{prefix}-{index}.json").write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")


def look_answer(erp: Erp, body_id: str = "blook"):
    """look 의 답(작은 답 + take 답들) — 지금 상태의 오퍼와 부과금 전부. `body_id` 는 페이지가 조각에 붙이는 이름(부를 때마다 다르다)."""
    offers = [{"id": offer["id"], "name": offer["name"], "charges": [row_of(offer, charge) for charge in charges]}
              for offer, charges in erp.offers()]
    keep = {"hotel": HOTEL, "offers": offers}
    return reply("look", {}, keep, pieces=4, body_id=body_id, login=False, hotel=HOTEL,
                 count={"offers": len(offers), "charges": sum(len(o["charges"]) for o in offers)}, doneAt=erp.tick())
