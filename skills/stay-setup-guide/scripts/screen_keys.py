"""화면 사전으로 지시서의 칸 이름을 **화면 칸 key**(`data-stay-field` = POST 이름)로 푼다 — 화면마다.

지시서는 사람이 보는 글자를 적는다(`| 룸 이름 | Single |`). 도구가 화면에서 그 칸을 찾는 계약은 글자가 아니라
표식이다(ERP `docs/development/erp-ui-foundations.md` §8, 2026-10-28). 그 사이를 잇는 것이 이 모듈이다.

  · 단계 갈래 → 화면: `references/step-kinds.json`. `이름`·`설명`·`정렬` 같은 글자는 화면마다 다른 칸이라
    화면을 모르고는 key 를 못 고른다.
  · 칸 이름 → key: 그 화면의 사전 칸에서 지금 글자(`label`·`screen_label`) → 옛 글자(`former_labels`) → 별칭(`aliases`)
    순으로 찾는다. 옛 글자로 찾았으면 `how="former_label"` — 검사기가 이름 바뀜 경고로 알린다.
  · 반복 행 `<묶음> <N> · <열>` 과 이름 붙은 칸 `<칸> · <이름>`(오퍼별 표시명 · Single) 도 푼다.

`check_manual.py`(검사) · `render_card.py`(지시서에 `data-stay-*` 를 싣는다)가 함께 쓴다. 표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

REFERENCES = Path(__file__).resolve().parent.parent / "references"
DICTIONARY_PATH = REFERENCES / "screen-dictionary.json"
STEP_KINDS_PATH = REFERENCES / "step-kinds.json"

#: 돈 칸 라벨의 통화 꼬리표 — `정액 금액 (USD)` · `정액 금액 (공급 통화)` (check_manual `CURRENCY_SUFFIX_RE` 와 같다)
_CURRENCY = re.compile(r"\s*\((?:[A-Z]{3}|공급 통화)\)")
_PAREN = re.compile(r"\s*[(（][^)）]*[)）]")
#: 반복 행 정본 꼴 — `구간 1 · 수수료 값` (check_manual `REPEAT_PREFIX_RE` 와 같은 빈칸 규칙)
_REPEAT = re.compile(r"^(?P<group>.+?) (?P<n>\d+) · (?P<col>.+)$")
#: 이름 붙은 칸 — 사전에는 `연령별 단가 · 〈연령 구간 노출명〉` 처럼 자리표시로 있다
_PLACEHOLDER = re.compile(r"\s*(?P<sep>[·—–])\s*〈[^〉]*〉\s*$")
_NAMED_SEPARATORS = (" · ", " — ", " – ", " - ")

#: 화면에는 그 이름의 칸이 없지만 도구가 그 칸으로 **옮기는** 원고 줄(2026-10-28 날짜 선택 칸).
#: 시즌의 `날짜 나열:` · `추가 날짜:` 는 블록이라 표 줄 검사를 받지 않는다.
CONVERTED_LINES = {
    "season": {"기간 시작": "date_selection_0", "기간 종료": "date_selection_0"},
    # 셀 상태(배포 전 운영 화면) — 지금 사전에는 그 화면이 없어 쓰이지 않는다
    "season-status-fill": {"시작 날짜": "date_selection_0", "종료 날짜": "date_selection_0"},
}


_BACKTICK_KEY = re.compile(r"^`([A-Za-z0-9_]+)`$")


def norm(label: str) -> str:
    return re.sub(r"\s+", " ", _CURRENCY.sub("", str(label or ""))).strip()


def _loose(label: str) -> str:
    """괄호·빈칸을 뗀 비교용 — `단(tier)` ↔ `단`, `공급 원가(선택)` ↔ `공급 원가 (선택)`."""
    return re.sub(r"\s+", "", _PAREN.sub("", norm(label)))


@dataclass(frozen=True)
class Resolved:
    screen: str
    key: str
    label: str  # 그 칸의 지금 화면 글자
    how: str  # key | label | alias | former_label | checkbox | converted | named | row | loose
    row: int | None = None  # 반복 행 번호
    column: str = ""  # 반복 행의 열 이름
    name: str = ""  # 이름 붙은 칸의 이름(`Single`)

    @property
    def renamed(self) -> bool:
        return self.how == "former_label"


class ScreenKeys:
    """사전 한 벌 + 갈래 표 한 벌. `resolve(갈래, 칸 이름)` 이 일이다."""

    #: 화면 → 그 화면이 고치는 대상(`data-stay-entity`). 탭 패널의 [편집] 처럼 글자가 같은 버튼이 대상마다 있을 때
    #: 이 단계가 어느 대상의 버튼을 여는지 가른다(`opener`).
    SCREEN_ENTITY = {
        "room-type": "room_type", "room-images": "room_type", "room-link-edit": "room", "room-link-bulk": "room",
        "offer": "offer", "offer-age-band": "age_band", "season": "season", "season-price-fill": "season",
        "rate-plan-catalog": "rate_plan_catalog", "rate-plan-row": "rate_plan", "rate-plan-deploy": "room",
        "charge": "charge", "addon": "addon", "addon-price": "addon_price", "promotion": "promotion",
        "benefit": "benefit", "benefit-group": "benefit_group", "cancellation-policy": "policy",
        "item-questions": "charge", "benefit-questions": "benefit",
    }

    def __init__(self, dictionary: dict, step_kinds: dict):
        self.kinds = {k: v for k, v in (step_kinds.get("kinds") or {}).items()}
        self.panel_actions = dict(dictionary.get("panel_actions") or {})
        self.validation = dict(dictionary.get("validation") or {})
        self.screens: dict = {}
        screens = list(dictionary.get("screens") or []) + list(dictionary.get("supplemental_screens") or [])
        for screen in screens:
            blocks = screen.get("blocks") or []
            if screen.get("ref") and isinstance(dictionary.get(screen["ref"]), dict):
                blocks = dictionary[screen["ref"]].get("blocks") or []
            fields = [f for b in blocks for f in b.get("fields") or []]
            self.screens[screen["id"]] = {"screen": screen, "fields": fields}

    @classmethod
    def load(cls, dictionary_path=DICTIONARY_PATH, step_kinds_path=STEP_KINDS_PATH) -> "ScreenKeys":
        with open(dictionary_path, encoding="utf-8") as handle:
            dictionary = json.load(handle)
        with open(step_kinds_path, encoding="utf-8") as handle:
            kinds = json.load(handle)
        return cls(dictionary, kinds)

    # ------------------------------------------------------------------ 화면

    def step(self, kind: str) -> dict:
        """갈래 → `{screens: [...], tab, submit_action}`. 모르는 갈래면 빈 dict."""
        return dict(self.kinds.get(kind) or {})

    def screen_ids(self, kind: str) -> list:
        return [s for s in self.step(kind).get("screens") or [] if s in self.screens]

    def tab_key(self, kind: str) -> str:
        got = self.step(kind)
        if got.get("tab"):
            return got["tab"]
        ids = self.screen_ids(kind)
        return (self.screens[ids[0]]["screen"].get("tab") or "") if ids else ""

    def actions(self, screen_id: str) -> list:
        return list((self.screens.get(screen_id) or {}).get("screen", {}).get("actions") or [])

    def action_for(self, kind: str, button: str) -> str:
        """버튼 글자 → 동사. 그 갈래의 화면들의 `actions` 에서 글자로 찾는다. 못 찾으면 빈 문자열."""
        want = _loose(button.strip("[]"))
        hits = {a["action"] for sid in self.screen_ids(kind) for a in self.actions(sid) if _loose(a.get("label", "")) == want}
        return hits.pop() if len(hits) == 1 else ""

    #: 단계 마지막 줄(`→ [ … ]`)이 누르는 버튼으로 볼 수 있는 동사 — 그 화면의 "저장" 자리
    SUBMIT_VERBS = ("save", "deploy", "save_cell", "add_cell", "next")

    def submit_action(self, kind: str, button: str) -> str:
        """마지막 줄 버튼 → 동사. 글자로 못 찾으면 그 화면의 저장 자리 동사가 **하나뿐일 때만** 그것.

        사전은 동사마다 글자 하나만 든다(`save` = `저장`) — 새로 만들 때 [추가], 고칠 때 [저장] 처럼
        같은 버튼의 글자가 갈리므로 글자만으로는 못 맞춘다.
        """
        verb = self.action_for(kind, button)
        if verb:
            return verb
        verbs = {a["action"] for sid in self.screen_ids(kind) for a in self.actions(sid)
                 if a.get("action") in self.SUBMIT_VERBS}
        return verbs.pop() if len(verbs) == 1 else ""

    #: 이름이 바뀐 여는 버튼 — 옛 원고의 글자도 그 버튼이다(2026-10-28 혜택 탭: 「혜택 추가」 두 개가 갈렸다)
    OPENER_ALIASES = {
        "혜택 추가": ("항상 포함 혜택 추가",),
        "이 그룹에 혜택 추가": ("후보 혜택 추가",),
    }

    def opener(self, kind: str, button: str, row: str | None = None):
        """`버튼:` 줄의 여는 버튼 → `{action, entity, card}`(탭 패널 `panel_actions`). 하나로 못 가르면 None.

        같은 글자의 버튼이 대상마다 있으면(객실 탭의 [편집] — 룸 타입 · 판매 연결) 이 단계 화면의 대상
        (`SCREEN_ENTITY`)이나 그 버튼이 여는 화면(`target`)으로 가른다. 그래도 둘 이상이면 고르지 않는다 —
        동사만 실으면 러너가 그 패널의 아무 버튼이나 누를 수 있다. 저장 자리·위험·절대 금지 동사는 싣지 않는다.
        """
        tab = self.tab_key(kind)
        raw = str(button or "").strip("[]").strip()
        wants = {_loose(raw)} | {_loose(n) for n in self.OPENER_ALIASES.get(norm(raw), ())}
        if not tab or not raw:
            return None
        cands = [a for a in self.panel_actions.get(tab) or []
                 if _loose(a.get("label", "")) in wants and a.get("action") not in self.SUBMIT_VERBS
                 and not a.get("danger") and not a.get("never_press")]
        cands = self._distinct(cands)
        if len(cands) > 1:
            entities = {self.SCREEN_ENTITY.get(s) for s in self.screen_ids(kind)} - {None}
            screens = {s.replace("-", "_") for s in self.screen_ids(kind)}
            narrowed = [a for a in cands if (a.get("target") and a["target"] in screens)]
            if not narrowed and row:
                narrowed = [a for a in cands if a.get("entity") in entities]
            cands = self._distinct(narrowed)  # 그래도 못 가르면(프로모션 [추가] — 전 오퍼 공통 · 오퍼별) 고르지 않는다
        if len(cands) != 1:
            return None
        got = cands[0]
        return {"action": got.get("action"), "entity": got.get("entity") or "", "card": got.get("card") or ""}

    @staticmethod
    def _distinct(actions: list) -> list:
        seen, out = set(), []
        for a in actions:
            key = (a.get("action"), a.get("entity"), a.get("card"), a.get("target"))
            if key not in seen:
                seen.add(key)
                out.append(a)
        return out

    def flagged_actions(self) -> dict:
        """사전이 표시한 동사 — `{danger: [...], never_press: [...]}`(화면 `actions` · 탭 `panel_actions` · 검증 배너)."""
        found = [a for sid in self.screens for a in self.actions(sid)]
        found += [a for acts in self.panel_actions.values() for a in acts or []]
        found += list(self.validation.get("actions") or [])
        danger = sorted({a["action"] for a in found if a.get("danger") and a.get("action")})
        never = sorted({a["action"] for a in found if a.get("never_press") and a.get("action")})
        return {"danger": danger, "never_press": never}

    # ------------------------------------------------------------------ 칸

    def resolve(self, kind: str, label: str):
        """갈래·칸 이름 → `Resolved` 또는 None(그 화면에 없는 칸이거나 갈래를 모른다)."""
        for screen_id in self.screen_ids(kind):
            hit = self.resolve_on(screen_id, label)
            if hit is not None:
                return hit
        return None

    def resolve_on(self, screen_id: str, label: str):
        fields = (self.screens.get(screen_id) or {}).get("fields") or []
        want = norm(label)
        if not want:
            return None
        # ⓪ 칸 셀이 백틱 key(`` `min_nights` ``) — 그 화면에 그 key 의 칸이 있으면 그대로(설치 도구와 같은 규칙)
        m = _BACKTICK_KEY.match(want)
        if m:
            field = next((f for f in fields if f.get("key") == m.group(1)), None)
            return Resolved(screen_id, field["key"], field.get("label", ""), "key") if field else None
        # ① 칸 하나를 통째로 — 지금 글자 → 옛 글자 → 별칭 → 체크박스 문구 꼴. 옛 글자가 별칭보다 먼저다 —
        #    ERP 노트는 옛 글자를 별칭에도 함께 싣는데(2026-10-28) 그 줄은 이름 바뀜으로 알려야 한다.
        for how, names_of in (
            ("label", lambda f: [f.get("label"), f.get("screen_label")]),
            ("former_label", lambda f: f.get("former_labels") or []),
            ("alias", lambda f: f.get("aliases") or []),
            ("checkbox", lambda f: [f"{f.get('label')} · {f['checkbox_text']}"] if f.get("checkbox_text") else []),
        ):
            for field in fields:
                if any(norm(n) == want for n in names_of(field) if n):
                    return Resolved(screen_id, field.get("key", ""), field.get("label", ""), how)
        converted = CONVERTED_LINES.get(screen_id, {}).get(want)
        if converted and any(f.get("key") == converted for f in fields):
            field = next(f for f in fields if f.get("key") == converted)
            return Resolved(screen_id, converted, field.get("label", ""), "converted")
        # ② 반복 행 `<묶음> <N> · <열>`
        m = _REPEAT.match(want)
        if m:
            group = self._row_field(fields, m.group("group"))
            if group is not None:
                return Resolved(screen_id, group.get("key", ""), group.get("label", ""), "row",
                                row=int(m.group("n")), column=m.group("col").strip())
        # ③ 이름 붙은 칸 `<칸> · <이름>` — 사전에는 자리표시 꼴(`… · 〈룸 카테고리명〉`)로 한 줄
        for field in fields:
            base = _PLACEHOLDER.sub("", field.get("label") or "")
            if base == field.get("label"):
                continue
            for sep in _NAMED_SEPARATORS:
                if want.startswith(norm(base) + sep):
                    return Resolved(screen_id, field.get("key", ""), field.get("label", ""), "named",
                                    name=want[len(norm(base) + sep):].strip())
        # ④ 괄호·빈칸만 다른 글자 — `공급 원가(선택)` ↔ `공급 원가 (선택)`
        loose = _loose(want)
        hits = [f for f in fields if loose and any(_loose(n) == loose for n in
                [f.get("label"), *(f.get("aliases") or []), *(f.get("former_labels") or [])] if n)]
        if len({f.get("key") for f in hits}) == 1:
            return Resolved(screen_id, hits[0].get("key", ""), hits[0].get("label", ""), "loose")
        return None

    @staticmethod
    def _row_field(fields: list, group: str):
        """반복 행 묶음 이름 → 그 칸. 지시서 접두는 사전 글자의 꼬리이기도 하다(`구간` ↔ `취소 수수료 구간`)."""
        rows = [f for f in fields if f.get("columns")]
        g = _loose(group)
        for field in rows:
            names = [field.get("label"), *(field.get("aliases") or []), *(field.get("former_labels") or [])]
            if any(n and _loose(n) == g for n in names):
                return field
        tails = [f for f in rows if g and _loose(f.get("label")).endswith(g)]
        return tails[0] if len(tails) == 1 else None
