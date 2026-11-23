"""season_sheet.py — 요금표로 시즌을 다시 채울 때, 확인한 요금표(`sheet` → sheet-check)와 시즌 창에서 창에 칠 입력을 끌어낸다(A1).
도우미는 셈하지 않는다 — 금액 차이 · 요금제 조정 · 박수 층 · 아동 금액은 여기서 셈하고, 그 입력이 요금표를 그대로 만드는지는 `plan` 이
칸마다 견준다(그대로 만들지 못하는 칸은 「요금표와 다르게 채워지는 칸」).

    propose(check, window, sentence)   → SeasonFill(요금표 파일을 품은 요청 — 칸마다 어디서 온 입력인지 sources 에)
    sheet_key(name, window)            요금표의 인원 조합 이름 → ERP 키(`2` → `A2`, 코드 없는 `A2C1` → 쓸 수 있는 아동 구간이 하나면 그 코드)

끌어내는 길(요약): 시즌 날 · 창의 객실 · 요금제에 든 요금표 칸만 본다. 쌍마다 인원 · 박수 줄의 값은 시즌 날 가운데 가장 많은 날의 값이다
(날마다 다르면 그 날들은 「다르게 채워지는 칸」이 된다). 객실마다 기준 요금제(✓)의 줄에서 판매 단가(첫 성인 키 · 1박) · 정가 · 공급 원가
(모든 칸에 있을 때만) · 인원 조합(성인 키) · 인원 조합별 조정(금액 차이) · 박수별 단가 · 아동 금액(고칠 수 있는 구간, 아니면 그 아동 키를
직접 치고 차이로)을 만들고, 다른 요금제는 한 금액이나 한 퍼센트가 모든 줄에 맞으면 요금제 조정으로 같은 저장에 넣고, 아니면 제 저장을
따로 둔다. 입력이 같은 객실들은 한 저장으로 묶는다. 요금표가 시즌의 모든 날을 덮지 않으면 덮는 날만 고른다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from decimal import Decimal
from typing import Mapping

from change_core.money import round_money
from price_model import CellKey, occupancy_order
from price_season import SeasonError, SeasonFill, SeasonSave, SeasonWindow, child_rates
from price_sheet import SheetCheck, encode_check
from season_expand import Inputs, SeasonRefused, build_key, los_matrix, normalize_key, parse_inputs, parse_key


def _usable_codes(window: SeasonWindow) -> list[str]:
    probe = SeasonSave(pairs=(), price="0")
    return [rate.code for rate in child_rates(window, probe)]


def sheet_key(name: str, window: SeasonWindow) -> str:
    try:
        key = normalize_key(name)
    except ValueError as error:
        raise SeasonError(f"요금표의 인원 조합 {name!r} 을 읽지 못했습니다 — {error}") from None
    parsed = parse_key(key)
    if parsed.adults is not None and any(code is None for _count, code in parsed.children):
        codes = _usable_codes(window)
        if len(codes) != 1:
            raise SeasonError(f"요금표의 {name} 에 아동 구간 코드가 없고, 창에서 쓸 수 있는 아동 구간이 {len(codes)}개입니다"
                              f"({', '.join(codes) or '없음'}) — 요금표 파일의 그 인원 조합에 코드를 적습니다(예: A2C1_CHD)")
        return build_key(parsed.adults, [(parsed.children[0][0], codes[0])])
    return key


def targets_of(check: SheetCheck, window: SeasonWindow) -> dict[CellKey, tuple[tuple[tuple[str, Decimal | None], ...], int]]:
    """요금표 칸 가운데 시즌 날 · 창의 쌍에 든 것 → (필드 값 — 통화 단위로 반올림, 줄 번호). 인원 조합은 ERP 키로."""
    pairs = {(plan.room, plan.rate_plan) for plan in window.plans}
    days = set(window.dates)
    out = {}
    for key, cell in check.cells.items():
        if (key.room, key.rate_plan) not in pairs or key.date not in days:
            continue
        target = replace(key, occupancy=sheet_key(key.occupancy, window))
        out[target] = (tuple((name, None if value is None else round_money(value, check.sheet.currency)) for name, value in cell.values),
                       cell.line)
    return out


def _text(value: Decimal) -> str:
    """금액 글자 — 창의 금액 칸 문법(쉼표 · 지수 없이, 끝의 0 없이, 소수 둘째 자리까지)."""
    return format(value.quantize(Decimal("0.01")).normalize(), "f")


def _signed(value: Decimal) -> str:
    return ("+" if value >= 0 else "-") + _text(abs(value))


def _lines(targets) -> dict[tuple[str, str], dict[tuple[str, int], dict]]:
    """쌍 → (인원, 박수) → 가장 많은 날의 값(필드 → 금액)과 그 줄 번호들."""
    grouped: dict[tuple[str, str], dict[tuple[str, int], Counter]] = {}
    lines: dict[tuple[str, str], set[int]] = {}
    for key, (values, line) in targets.items():
        grouped.setdefault((key.room, key.rate_plan), {}).setdefault((key.occupancy, key.nights), Counter())[values] += 1
        lines.setdefault((key.room, key.rate_plan), set()).add(line)
    out = {}
    for pair, rows in grouped.items():
        out[pair] = {}
        for at, counted in rows.items():
            best = sorted(counted.items(), key=lambda item: (-item[1], str(item[0])))[0][0]
            out[pair][at] = dict(best)
    return out


def _base_inputs(rows: Mapping[tuple[str, int], dict], window: SeasonWindow) -> dict[str, object] | None:
    """기준이 될 요금제 하나의 줄 → 창 입력(글자). 성인 키가 없으면(인원 무관 "" 뿐) 키 없이."""
    adults = sorted({occ for occ, nights in rows if nights == 1 and occ and not parse_key(occ).children}, key=occupancy_order)
    first = adults[0] if adults else ""
    if (first, 1) not in rows:
        return None
    base = rows[(first, 1)]
    price = base["sell"]
    every = lambda name: all(name in values and values[name] is not None for values in rows.values())   # noqa: E731
    texts = {"price": _text(price), "original_price": _text(base["list"]) if every("list") else "",
             "net_price": _text(base["supply"]) if every("supply") else ""}
    keys, adjusts, child = list(adults), [], {}
    for occ in adults[1:]:
        if (occ, 1) in rows and rows[(occ, 1)]["sell"] != price:
            adjusts.append(f"{occ}:{_signed(rows[(occ, 1)]['sell'] - price)}")
    editable = {item.code for item in window.child if item.kind == "amount"}
    auto = set(_usable_codes(window))
    for occ, nights in sorted(rows, key=lambda at: (occupancy_order(at[0]), at[1])):
        parsed = parse_key(occ) if occ else None
        if nights != 1 or not parsed or not parsed.children:
            continue
        adult_key = f"A{parsed.adults}"
        single = len(parsed.children) == 1 and parsed.children[0][0] == 1 and parsed.children[0][1] in auto
        if single and parsed.children[0][1] in editable and (adult_key, 1) in rows and parsed.children[0][1] not in child:
            child[parsed.children[0][1]] = _text(rows[(occ, 1)]["sell"] - rows[(adult_key, 1)]["sell"])
            continue
        if single:
            continue   # 비율 구간 — ERP 가 셈한다(요금표와 다르면 다르게 채워지는 칸)
        keys.append(occ)
        adjusts.append(f"{occ}:{_signed(rows[(occ, 1)]['sell'] - price)}")
    tiers = sorted(nights for occ, nights in rows if occ == first and nights > 1)
    texts.update(occupancy_keys=",".join(keys), occupancy_adjust=",".join(adjusts),
                 los_prices=",".join(f"{nights}:{_text(rows[(first, nights)]['sell'])}" for nights in tiers), plan_adjust="")
    if texts["original_price"] and any(rows[(first, nights)]["sell"] > Decimal(texts["original_price"]) for nights in tiers):
        texts["original_price"] = ""   # 박수 층 판매가가 정가보다 비싸면 창이 거절한다 — 정가는 비우고 다르게 채워지는 칸으로
    return dict(texts=texts, child=child)


def _reproduces(texts: Mapping[str, str], child: Mapping[str, str], window: SeasonWindow, rows, adjusted: bool) -> bool:
    """그 입력의 금액표가 그 요금제의 줄(가장 많은 날의 값)을 모두 그대로 만드는지 — 요금제 조정을 건 표(adjusted)나 기준 표로."""
    save = SeasonSave(pairs=(), **{name: texts.get(name, "") for name in ("price", "original_price", "net_price", "plan_adjust",
                                                                          "occupancy_keys", "occupancy_adjust", "los_prices")},
                      child_extra=tuple(child.items()))
    try:
        inputs: Inputs = parse_inputs({name: save.text(name) for name in ("price", "original_price", "net_price", "plan_adjust",
                                                                          "occupancy_keys", "occupancy_adjust", "los_prices")},
                                      child_rates(window, save))
        matrices = los_matrix(inputs)
    except SeasonRefused:
        return False
    for (occ, nights), values in rows.items():
        table = matrices.get(nights, ({}, {}))[1 if adjusted else 0]
        if occ not in table:
            return False
        sell, listed, net = table[occ]
        if values.get("sell") != sell:
            return False
        if "list" in values and values["list"] is not None and values["list"] != listed:
            return False
    return True


def _plan_adjust(base_texts, child, window, rows_other, base_price: Decimal, other_price: Decimal) -> str | None:
    """다른 요금제 하나가 기준 요금제의 입력 위에 한 금액이나 한 퍼센트의 조정으로 그대로 만들어지면 그 조정 글자(금액이 먼저)."""
    candidates = [_signed(other_price - base_price)]
    if base_price:
        percent = ((other_price / base_price) - 1) * 100
        if percent == percent.quantize(Decimal("0.0001")):
            candidates.append(("+" if percent >= 0 else "-") + format(abs(percent).normalize(), "f") + "%")
    for text in candidates:
        if _reproduces(dict(base_texts, plan_adjust=text), child, window, rows_other, adjusted=True):
            return text
    return None


def propose(check: SheetCheck, window: SeasonWindow, sentence: str = "") -> SeasonFill:
    """확인한 요금표 + 시즌 창 → 요금표를 품은 시즌 다시 채우기 요청. 요금표의 칸이 하나도 시즌 · 창에 들지 않으면 거절."""
    targets = targets_of(check, window)
    if not targets:
        raise SeasonError(f"요금표의 칸 가운데 시즌 「{window.season_name}」의 날 · 시즌 창의 객실 · 요금제에 드는 칸이 없습니다 — 요금표의 "
                          "기간과 시즌 날을 다시 봅니다")
    lines = _lines(targets)
    used = {}
    for key, (_values, line) in targets.items():
        used.setdefault((key.room, key.rate_plan), set()).add(line)
    saves: list[tuple[dict, dict, list[tuple[str, str]], set[str]]] = []

    def add(inputs: dict, pairs: list[tuple[str, str]]):
        days = {key.date for key in targets if (key.room, key.rate_plan) in pairs}
        saves.append((inputs["texts"], inputs["child"], pairs, days))

    for room in window.rooms:
        plans = [plan for plan in window.plans if plan.room_id == room.id and (plan.room, plan.rate_plan) in lines]
        if not plans:
            continue
        base = window.base_plan(room.id)
        lead = base if base is not None and base in plans else None
        rest = [plan for plan in plans if plan is not lead]
        if lead is not None:
            inputs = _base_inputs(lines[(lead.room, lead.rate_plan)], window)
            if inputs is None:
                rest = plans
                lead = None
            else:
                together = [(lead.room, lead.rate_plan)]
                adjust = None
                for plan in list(rest):
                    rows = lines[(plan.room, plan.rate_plan)]
                    other = next((values["sell"] for (occ, nights), values in rows.items() if nights == 1
                                  and occ == (inputs["texts"]["occupancy_keys"].split(",")[0] if inputs["texts"]["occupancy_keys"] else "")), None)
                    text = None if other is None else _plan_adjust(inputs["texts"], inputs["child"], window, rows,
                                                                   Decimal(inputs["texts"]["price"]), other)
                    if text is not None and (adjust is None or adjust == text):
                        adjust = text
                        together.append((plan.room, plan.rate_plan))
                        rest.remove(plan)
                if adjust is not None:
                    inputs["texts"]["plan_adjust"] = adjust
                add(inputs, together)
        for plan in rest:
            inputs = _base_inputs(lines[(plan.room, plan.rate_plan)], window)
            if inputs is not None:
                add(inputs, [(plan.room, plan.rate_plan)])
    merged: list[tuple[dict, dict, list, set]] = []
    for texts, child, pairs, days in saves:
        twin = next((item for item in merged if item[0] == texts and item[1] == child and item[3] == days), None)
        if twin is None:
            merged.append((texts, child, list(pairs), set(days)))
        else:
            twin[2].extend(pairs)
    out = []
    for texts, child, pairs, days in merged:
        lines_used = sorted({line for pair in pairs for line in used.get(pair, ())})
        source = f"요금표 {', '.join(f'{line}번째' for line in lines_used)} 줄에서 셈함"
        out.append(SeasonSave(tuple(pairs), texts["price"], texts["original_price"], texts["net_price"], texts["plan_adjust"],
                              texts["occupancy_keys"], texts["occupancy_adjust"], texts["los_prices"], tuple(sorted(child.items())), True,
                              None if days >= set(window.dates) else tuple(sorted(days)),
                              tuple((name, source) for name in ("price", "original_price", "net_price", "plan_adjust", "occupancy_keys",
                                                                "occupancy_adjust", "los_prices") if texts[name])
                              + tuple((f"child_extra_{code}", source) for code in sorted(child))))
    return SeasonFill(window.hotel, window.hotel_id, window.offer, window.season_id, window.season_name, check.sheet.currency,
                      sentence or check.sheet.sentence, tuple(out), encode_check(check))
