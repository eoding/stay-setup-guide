"""시험용 — 지어낸 호텔 하나의 부가옵션 가격 줄과, 페이지(`window.stayAddonPrice`)가 돌려줄 답을 파이썬에서 만든다.

`Erp` 는 줄마다 판매가 · 공급 원가 · 편집 창의 다른 칸을 들고 있는 작은 ERP 다. `answers_for_reading` 은 그 상태로 readLine 답(작은 답 +
조각 take 답)을 만들고, `apply` 는 applyLine 이 보낼 칸을 받아 상태를 바꾸고 답을 만든다(편집 창이 읽은 값과 다르면 페이지처럼
거절한다). 답의 모양은 진짜 페이지 모듈이 낸 답(tests/fixtures/browser/)과 같다 — tests/test_golden.py 가 견준다.
조각을 나누는 일은 가격 캘린더 도우미의 시험 받침(`browser_replies.reply`)을 그대로 쓴다.

unittest 가 찾지 않도록 이름이 test_ 로 시작하지 않는다. 이름 · 번호 · 금액은 모두 지어낸 것이다(공개 저장소).
"""

import copy
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
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

HOTEL = {"id": "1", "name": "데모 호텔"}
SCOPE_TEXT = "요금제: 기존 범위 그대로 · 객실: 기존 범위 그대로 · 부가옵션 범위와 모두 일치하는 대상에만 적용"
START = datetime(2026, 11, 21, 1, 0, tzinfo=timezone.utc)


def line(addon, addon_name, line_id, name, sell, supply, target="전체", season="", date="", description="", hidden=False,
         currency="USD", listed=None, offer="데모 오퍼 2027", scope=True):
    """줄 하나 — 목록과 편집 창이 같은 값을 보이는 보통 줄. `hidden` 이면 목록의 통화별 금액이 「별도 금액 없음」(값 줄이 안 보임),
    `listed` 를 주면 목록의 통화별 금액이 그 글자들이다(편집 창과 다르게 보이는 줄). `scope` 가 False 면 편집 창에 적용 범위 카드가 없다."""
    return dict(addon=addon, addon_name=addon_name, line=line_id, name=name, sell=sell, supply=supply, target=target,
                season=season, date=date, description=description, hidden=hidden, currency=currency, listed=listed, offer=offer,
                scope=scope)


def demo_lines():
    return [
        line("201", "조식 추가 (성인)", "301", "비수기 조식", "20.00", "15.00", target="비수기", season="41"),
        line("201", "조식 추가 (성인)", "302", "연말 조식", "35.50", "28.00", target="2026-12-31", date="2026-12-31"),
        line("202", "공항 픽업", "303", "편도 픽업", "40.00", "", hidden=True),
        line("203", "엑스트라베드", "304", "엑스트라베드 1개", "30.00", "25.00"),
    ]


def form_of(item):
    return [["name", item["name"]], ["price", item["sell"]], ["net_amount", item["supply"]], ["season", item["season"]],
            ["date", item["date"]], ["rate_plan", ""], ["description", item["description"]]] + (
        [["scope_rate_plan_mode", "0"], ["scope_room_mode", "0"]] if item["scope"] else [])


def row_of(item):
    cur = item.get("currency", "USD")
    values = ([] if item["hidden"] else
              [f"판매가: {item['sell']} {cur}"] + ([f"공급 원가: {item['supply']} {cur}"] if item["supply"] else []))
    if item.get("listed") is not None:
        values = list(item["listed"])
    return {"id": item["line"], "name": item["name"], "sell": f"{item['sell']} {cur}", "values": values, "target": item["target"],
            "scope": SCOPE_TEXT, "band": "전체"}


def window_of(item):
    labels = {"season": "비수기" if item["season"] else "---------", "rate_plan": "---------",
              **({"scope_rate_plan_mode": "기존 범위 그대로", "scope_room_mode": "기존 범위 그대로"} if item["scope"] else {})}
    return {"title": f"가격 편집 — {item['name']}", "addon": item["addon_name"], "form": form_of(item), "labels": labels,
            "errors": []}


class Erp:
    """줄들의 지금 상태와 시계. 읽기 · 저장마다 답의 끝난 시각이 10초씩 간다."""

    def __init__(self, lines=None):
        self.lines = {item["line"]: dict(item) for item in (lines or demo_lines())}
        self.clock = START
        self.posts = []
        self.reads = 0

    def tick(self) -> str:
        self.clock += timedelta(seconds=10)
        return done_at(self.clock)

    def read_line(self, call):
        """readLine 하나의 답(작은 답 + take 답들). 목록에 없는 줄이면 missing."""
        asked = {key: call[key] for key in ("hotel", "addon", "line")}
        item = self.lines.get(call["line"])
        self.reads += 1
        if item is None or item["addon"] != call["addon"]:
            return reply("readLine", asked, None, missing=True, doneAt=self.tick(),
                         note="목록에 그 부가옵션의 그 가격 줄이 없습니다 — 아무것도 열지 않았습니다")
        keep = {"hotel": HOTEL, "addon": {"id": item["addon"], "name": item["addon_name"], "offer": item["offer"]}, "line": row_of(item),
                "window": window_of(item)}
        return reply("readLine", asked, keep, pieces=3, body_id=f"b{self.reads}",
                     what=f"{item['offer']} · {item['addon_name']} · {item['name']}",
                     doneAt=self.tick())

    def apply(self, payload, outcome=True):
        """applyLine 하나 — 편집 창의 칸이 payload 의 form 과 같을 때만 form + set 을 보내고(공급 원가가 빌 뻔하면 거절) 상태를 바꾼다.
        `outcome` 이 False 면 서버가 거절, "unknown" 이면 눌렀지만 알 수 없음(상태는 바뀐다)."""
        item = self.lines[payload["line"]]
        base = {"op": "applyLine", "no": payload["no"], "ask": ask(payload), "doneAt": self.tick()}
        if form_of(item) != payload["form"]:
            return dict(base, ok=False, saved=False, pressed=False, refused=True,
                        error="창의 값이 읽은 값과 다릅니다 — 아무것도 치지 않았고 누르지 않았습니다")
        sent = [[name, payload["set"].get(name, value)] for name, value in payload["form"]]
        values = dict(sent)
        if not values["net_amount"] and dict(payload["form"])["net_amount"] and payload["set"].get("net_amount") != "":
            return dict(base, ok=False, saved=False, pressed=False, refused=True, error="공급 원가가 빈 채로 저장될 뻔했습니다")
        self.posts.append(sent)
        if outcome is False:
            return dict(base, ok=False, saved=False, pressed=True, error="가격 편집 창이 저장을 거절했습니다")
        item["sell"], item["supply"] = values["price"], values["net_amount"]
        if outcome == "unknown":
            return dict(base, ok=False, saved="unknown", pressed=True, error="저장 단추는 눌렸고 저장됐는지 알 수 없습니다")
        return dict(base, ok=True, saved=True, pressed=True, note="저장했습니다", what=f"{item['offer']} · {item['addon_name']} · {item['name']}")


def write_answers(folder: Path, prefix: str, answers) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for index, answer in enumerate(answers, 1):
        (folder / f"{prefix}-{index}.json").write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")


def look_answer(erp: Erp, body_id: str = "blook"):
    """look 의 답(작은 답 + take 답들) — 지금 상태의 부가옵션과 줄 전부. 페이지는 볼 때마다 새 조각 id 를 붙인다(`body_id`)."""
    addons = {}
    for item in erp.lines.values():
        entry = addons.setdefault(item["addon"], {"id": item["addon"], "name": item["addon_name"], "offer": item["offer"],
                                                  "lines": []})
        entry["lines"].append(row_of(item))
    keep = {"hotel": HOTEL, "addons": list(addons.values())}
    return reply("look", {}, keep, pieces=4, body_id=body_id, login=False, hotel=HOTEL,
                 count={"addons": len(addons), "lines": len(erp.lines)}, doneAt=erp.tick())


def snapshot_copy(erp: Erp) -> dict:
    return copy.deepcopy(erp.lines)
