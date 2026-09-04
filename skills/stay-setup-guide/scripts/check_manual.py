#!/usr/bin/env python3
"""check_manual.py — 입력 지시서(manual.md) 형식 검사.

references/MANUAL-SPEC.md 의 규칙을 기계적으로 확인한다:
- 단계(## 제목) 수 = 저장/추가 버튼(→ [...]) 수
- 단계 번호가 1부터 끊기지 않고 연속
- 금지어 0 (내부 용어가 새어 들어갔는지)
- 원문자(①②...) 0
- 시트 좌표로 보이는 토큰(B46 같은) 0
- 절대 경로(/home/...) 0
- `폴더:` 줄이 `폴더: <공유 폴더명>/사진` 형식과 일치(--share-name 을 준 경우)
- 사진 단계에서 참조한 파일명이 실제 사진 폴더에 있는지(--photos 를 준 경우)
- 0단계(1·2·3 단계가 각각 환율 확인 · 거래처 확인 · 도시 확인)가 있는지
- 표의 칸 이름이 화면 사전(screen-dictionary.json)에 있는지
- 값에 나오는 금액이 계약서에 있는 숫자인지(--contract 를 준 경우, 경고만)
- 같은 오퍼의 시즌끼리 날짜가 하루라도 겹치는지(겹침·포함 모두 오류 — 배너에 🟡 가 남는다)
- `시즌 가격 채우기` 에 `이미 값이 있는 날도 덮기 | 체크` 가 남아 있는지(겹치지 않으면 필요 없다 — 경고)
- 오퍼마다 `기본 취소 정책` 이 있는지(`지정 안 함`·빈 값이면 오류 — 배너가 🔴 로 막는다)
- `오퍼 고치기` 단계가 있는지(있으면 오류 — 호텔은 빈 상태로 만들어져 고칠 기본 오퍼가 없다)
- `룸 만들기`·`판매 연결` 단계가 첫 `오퍼 만들기` 보다 앞에 있는지(있으면 오류 — 오퍼가 없으면 객실 추가가 막힌다)
- `경고 넘어가기` 단계가 있는지(있으면 오류 — 원인을 지시서에서 고친다)
- `캠페인 만들기` 단계가 있는지(있으면 오류 — 캠페인은 걷혔다) · 오퍼의 `캠페인` 이 `선택: — 없음 —` 인지
- 같은 이름의 부가옵션이 오퍼 여럿에 있으면 가격 넣기 카드 줄이 오퍼를 한정하는지
- `시즌 만들기` 단계가 `→ [추가]` 로 끝나는지
- `호텔 만들기` 단계의 `공급 통화` 가 USD 인지(아니면 경고만 — 막지 않는다)

사용법:
    python3 check_manual.py <manual.md> [--photos DIR] [--share-name NAME]
                            [--dictionary screen-dictionary.json] [--contract contract.md]

--photos 를 생략하면 사진 존재 확인은 건너뛴다.
--share-name 을 생략하면 `폴더:` 줄 형식 확인은 건너뛴다(줄 목록만 보여준다).
--dictionary 를 생략하면 스크립트 옆의 ../references/screen-dictionary.json 을 쓴다(없으면 건너뛴다).
--contract 를 생략하면 금액 대조는 건너뛴다.
"""
import argparse
import datetime
import decimal
import json
import os
import re
import sys

# 지시서에 나오면 안 되는 내부 작업 용어 (회사·사람 이름은 계약서에서 온 값이면 표 안에서는 허용되므로
# 여기 포함하지 않는다 — 값 자체의 정당성은 사람이 판단한다)
FORBIDDEN = [
    "QA", "담당자", "확인 필요", "임시값", "위와 같이", "근거", "기대값", "<!--", "/home/",
]

CIRCLED = re.compile(r"[①-⑳]")
# 시트 좌표(B46 같은) 의심 토큰. 통화·요금제 코드(USD, VND, KRW, HB, FB, BB, D-14 등)는 오탐이라 뺀다.
CELL = re.compile(r"(?<![A-Za-z0-9])[A-Z]{1,2}\d{1,3}(?![A-Za-z0-9])")
CELL_EXCLUDE = re.compile(r"^(D|HB|FB|BB|USD|VND|KRW)\d")
ROW = re.compile(r"^\| ([^|]+) \| ([^|]+) \|$")
STEP_RE = re.compile(r"^## (\d+)\.")
STEP_TITLE_RE = re.compile(r"^## (\d+)\.\s*(.*)$")
FILE_REF_RE = re.compile(r"\b((?:hotel|room|offer)_[A-Za-z0-9_\-]+\.(?:jpe?g|png))", re.IGNORECASE)
# 사진 목록 줄의 출처: `- hotel_01.jpg — 출처: https://...` (출처는 선택)
PHOTO_SRC_RE = re.compile(
    r"^\s*-\s*(?P<name>[\w][\w.\-]*\.(?:jpe?g|png))\s*[\u2014\u2013-]+\s*출처\s*:\s*(?P<url>\S+)\s*$",
    re.IGNORECASE,
)
HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# 단계 첫 줄들(`화면:` `탭:` `카드:` …)과 마지막 저장 줄
HEAD_RE = re.compile(r"^(화면|탭|카드|블록|버튼|폴더|주의):\s*(.*)$")
# 표 대신 라벨 줄 + 펜스 코드블록으로 적는 긴 값(`날짜 나열:` `상세설명:`)
LABEL_RE = re.compile(r"^([^|`#\-→\s][^|]*?)\s*:\s*$")
FENCE_RE = re.compile(r"^(```|~~~)")
SAVE_RE = re.compile(r"^→\s*\[([^\]]+)\]")
BACKTICK_RE = re.compile(r"`([^`]+)`")
# 부가옵션 가격 넣기 카드 줄의 오퍼 한정 형식: `<이름>` — 오퍼 칸이 `<오퍼>` 인 카드
ADDON_CARD_OFFER_RE = re.compile(
    r"^`(?P<name>[^`]+)`\s*[\u2014\u2013-]+\s*오퍼 칸이\s*`(?P<offer>[^`]+)`\s*인 카드\s*$"
)
# 시즌 날짜 값 안의 날짜·기간
DATE_TOKEN_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
DATE_SPAN_RE = re.compile(r"(\d{4}-\d{1,2}-\d{1,2})\s*~\s*(\d{4}-\d{1,2}-\d{1,2})")
MONTH_RE = re.compile(r"(\d{1,2})월")
# 시즌 하나가 담을 수 있는 날짜 수 상한 — 이보다 길면 값을 못 읽은 것으로 보고 대조에서 뺀다
MAX_SEASON_DAYS = 4000

OVERWRITE_FIELD = "이미 값이 있는 날도 덮기"
PROMO_COMMON_CARD = "전 오퍼 공통"

# 요일 규칙 시즌 — `적용 요일` 의 요일 글자를 파이썬 weekday(월=0)로 옮긴다
WEEKDAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
WEEKDAY_TOKEN_RE = re.compile(r"[월화수목금토일](?:요일)?")

# 오퍼의 기본 취소 정책 — 이 값이면 판매 시작 배너에 🟡 가 남는다
CANCEL_POLICY_FIELD = "기본 취소 정책"
CANCEL_POLICY_EMPTY = {"지정 안 함", "", "비움", "—", "-", "— 없음 —", "- 없음 -", "(지정 안 함)"}

# 캠페인은 걷혔다(오퍼가 `오퍼 이미지` 로 겉면을 직접 가진다) — 단계로 만들지 않고 오퍼 값은 언제나 「— 없음 —」
CAMPAIGN_TITLE = "캠페인 만들기"
CAMPAIGN_FIELD = "캠페인"
CAMPAIGN_NONE = {"— 없음 —", "- 없음 -"}

# 배너 경고를 사유로 넘기는 단계는 더 이상 쓰지 않는다 — 원인을 지시서에서 고친다
SKIP_WARNING_TITLE = "경고 넘어가기"
SKIP_WARNING_BUTTON = "넘어가기"

# 오퍼 단계 — 호텔이 빈 상태로 만들어지므로(2026-09-04) 오퍼는 언제나 **만드는** 단계다.
OFFER_CREATE_TITLE = "오퍼 만들기"
# 종전 지시서의 흔적 — `기본 오퍼` 가 저절로 생기던 시절의 단계 제목이다.
OFFER_EDIT_TITLE = "오퍼 고치기"

# 오퍼가 없으면 판매 연결 카드의 [객실 추가] 가 아예 그려지지 않는다 —
# 이 제목들은 첫 `오퍼 만들기` 뒤에 와야 한다.
AFTER_OFFER_TITLES = ("룸 만들기", "판매 연결")

# `오퍼별 표시명 · <룸 카테고리명>` 처럼 뒤에 행 이름이 붙는 칸 — 사전과는 앞부분으로 대조한다
ROW_SUFFIX_FIELDS = ("오퍼별 표시명",)


def strip_select(value):
    """`선택: A, B` → `A, B`. 아니면 그대로."""
    return value[len("선택:"):].strip() if value.startswith("선택:") else value.strip()


def parse_steps(lines):
    """manual.md 를 단계 단위로 쪼갠다 — 번호·제목·첫 줄들·표·긴 값 블록·저장 줄."""
    steps = []
    cur = None
    label = None      # 방금 지나온 `<칸 이름>:` 라벨 줄
    fence = None      # 펜스 블록을 모으는 중이면 (칸 이름, 줄 목록)
    for line in lines:
        if fence is not None:
            if FENCE_RE.match(line):
                name, buf = fence
                fence = None
                if cur is not None and name:
                    cur["fields"].setdefault(name, " / ".join(x.strip() for x in buf if x.strip()))
            else:
                fence[1].append(line)
            continue
        if FENCE_RE.match(line):
            fence = (label, [])
            label = None
            continue
        m = STEP_TITLE_RE.match(line)
        if m:
            label = None
            cur = {"num": int(m.group(1)), "title": m.group(2).strip(),
                   "heads": {}, "rows": [], "fields": {}, "saves": []}
            steps.append(cur)
            continue
        if cur is None:
            continue
        h = HEAD_RE.match(line)
        if h:
            cur["heads"].setdefault(h.group(1), []).append(h.group(2).strip())
            continue
        s = SAVE_RE.match(line)
        if s:
            cur["saves"].append(s.group(1).strip())
            continue
        r = ROW.match(line)
        if r:
            key, value = r.group(1).strip(), r.group(2).strip()
            if key in ("칸", "---"):
                continue
            cur["rows"].append((key, value))
            cur["fields"].setdefault(key, value)
            continue
        lb = LABEL_RE.match(line)
        label = lb.group(1).strip() if lb else (label if not line.strip() else None)
    return steps


def head(step, name):
    """단계의 `<name>:` 첫 줄 하나(없으면 None)."""
    values = step["heads"].get(name)
    return values[0] if values else None


def card_name(step):
    """`카드:` 줄에서 백틱 안 이름(첫 번째)만."""
    line = head(step, "카드")
    if not line:
        return None
    m = BACKTICK_RE.search(line)
    return m.group(1).strip() if m else line.strip()


def step_subject(title):
    """`시즌 만들기 (1번째, Regular)` → `Regular`. 괄호가 없으면 None."""
    m = re.match(r"^.*?\((.*)\)\s*$", title)
    if not m:
        return None
    inner = m.group(1)
    return inner.split(",", 1)[1].strip() if "," in inner else inner.strip()


def _date(token):
    y, mo, d = (int(x) for x in token.replace("/", "-").split("-"))
    try:
        return datetime.date(y, mo, d)
    except ValueError:
        return None


def _span(start, end):
    """두 날짜 사이의 날짜 집합. 뒤집혔거나 너무 길면 None(모름)."""
    if not start or not end or end < start or (end - start).days + 1 > MAX_SEASON_DAYS:
        return None
    return {start + datetime.timedelta(days=i) for i in range((end - start).days + 1)}


def season_dates(step):
    """시즌 만들기 단계의 표에서 날짜 집합을 읽는다. 읽을 수 없으면 None."""
    fields = step["fields"]
    kind = strip_select(fields.get("날짜 규칙 유형", ""))
    if kind == "기간 범위":
        return _span(_date_field(fields, "기간 시작"), _date_field(fields, "기간 종료"))
    if kind == "월 목록":
        whole = _span(_date_field(fields, "기간 시작"), _date_field(fields, "기간 종료"))
        months = {int(m) for m in MONTH_RE.findall(strip_select(fields.get("적용 월", "")))}
        if whole is None or not months:
            return None
        return {d for d in whole if d.month in months}
    if kind == "비연속 날짜 나열":
        return _listed_dates(fields.get("날짜 나열", ""))
    if kind == "요일 규칙":
        return _weekday_dates(fields)
    return None  # 유형을 못 읽었으면 대조에서 뺀다


def _weekday_dates(fields):
    """요일 규칙 시즌 → 기간 안에서 그 요일에 해당하는 날짜 집합(못 읽으면 None).

    기간은 `기간 시작`·`기간 종료` 두 칸에서 읽고, 한 칸에 `2026-06-01 ~ 2026-08-31 중 토`
    처럼 몰아 적은 표기도 받는다.
    """
    weekday_value = strip_select(fields.get("적용 요일", ""))
    days = _weekday_set(weekday_value)
    if not days:
        return None
    whole = _span(_date_field(fields, "기간 시작"), _date_field(fields, "기간 종료"))
    if whole is None:
        m = DATE_SPAN_RE.search(weekday_value)
        whole = _span(_date(m.group(1)), _date(m.group(2))) if m else None
    if whole is None:
        return None
    picked = {d for d in whole if d.weekday() in days}
    return picked or None


def _weekday_set(value):
    """`일, 월, 화` 또는 `2026-06-01 ~ 2026-08-31 중 토` → {0, 6, ...}. 못 읽으면 빈 집합."""
    text = value.split("중", 1)[1] if "중" in value else value
    text = DATE_SPAN_RE.sub(" ", text)
    return {WEEKDAYS[m.group(0)[0]] for m in WEEKDAY_TOKEN_RE.finditer(text)}


def _date_field(fields, name):
    value = (fields.get(name) or "").strip()
    m = DATE_TOKEN_RE.search(value)
    return _date(m.group(0)) if m else None


def _listed_dates(value):
    """`2026-07-01 ~ 2026-07-10 / 2026-12-24` 같은 나열 → 날짜 집합(못 읽으면 None)."""
    rest = value
    days = set()
    for m in DATE_SPAN_RE.finditer(value):
        part = _span(_date(m.group(1)), _date(m.group(2)))
        if part is None:
            return None
        days |= part
        rest = rest.replace(m.group(0), " ")
    for m in DATE_TOKEN_RE.finditer(rest):
        one = _date(m.group(0))
        if one is None:
            return None
        days.add(one)
    return days or None


def season_index(steps):
    """`시즌 만들기` 단계들 → {(오퍼 카드, 시즌명): 날짜 집합 or None}."""
    seasons = {}
    for step in steps:
        if not step["title"].startswith("시즌 만들기"):
            continue
        name = step_subject(step["title"]) or step["fields"].get("시즌명")
        if not name:
            continue
        seasons[(card_name(step) or "", name)] = season_dates(step)
    return seasons


def target_rooms(step):
    """`대상 룸` 값 → 룸 이름 집합(못 읽으면 빈 집합 = 모든 룸과 겹치는 것으로 본다)."""
    value = strip_select(step["fields"].get("대상 룸", ""))
    return {part.strip() for part in value.split(",") if part.strip()}


def fill_season(step, seasons):
    """가격 채우기 단계 → (오퍼, 시즌명). 이름이 겹치거나 없으면 None."""
    card = card_name(step)
    if not card:
        return None
    matches = [key for key in seasons if key[1] == card]
    return matches[0] if len(matches) == 1 else None


def find_season_overlaps(steps):
    """같은 오퍼의 시즌끼리 날짜가 하루라도 겹치면 오류.

    판매 시작 배너에 🟡 를 남기지 않는 것이 합격선이라, 겹침(포함도 겹침이다)은 사유로
    넘기는 것이 아니라 시즌 날짜 자체를 갈라 없앤다. 날짜를 못 읽는 시즌(유형이 없거나
    값이 비었거나)은 대조에서 뺀다.
    """
    problems = []
    seen = []  # 앞 단계에서 만든 (오퍼 카드, 시즌명, 날짜 집합)
    for step in steps:
        if not step["title"].startswith("시즌 만들기"):
            continue
        name = step_subject(step["title"]) or step["fields"].get("시즌명")
        if not name:
            continue
        name = name.strip()
        offer = card_name(step) or ""
        mine = season_dates(step)
        if not mine:
            seen.append((offer, name, None))
            continue
        for prev_offer, prev_name, prev_dates in seen:
            if prev_offer != offer or prev_name == name or not prev_dates:
                continue
            hit = mine & prev_dates
            if not hit:
                continue
            how = "통째로 들어 있다" if mine <= prev_dates or prev_dates <= mine else f"{len(hit)}일 겹친다"
            problems.append(
                f"{step['num']}단계: 시즌 `{name}` 날짜가 같은 오퍼의 시즌 `{prev_name}` 와 {how} — "
                "같은 오퍼의 시즌은 하루도 겹칠 수 없다(넓은 시즌 날짜에서 빼거나 요일로 가른다)"
            )
        seen.append((offer, name, mine))
    return problems


def find_needless_overwrite(steps):
    """`시즌 가격 채우기` 의 `이미 값이 있는 날도 덮기` 체크는 이제 쓸 일이 없다(경고).

    시즌이 겹치지 않으면 덮을 값이 없다 — 체크가 남아 있으면 시즌을 아직 안 가른 흔적이다.
    """
    return [
        f"{step['num']}단계: `{OVERWRITE_FIELD}` 가 체크다 — 시즌이 겹치지 않으면 덮기가 필요 없다"
        for step in steps
        if step["title"].startswith("시즌 가격 채우기") and step["fields"].get(OVERWRITE_FIELD) == "체크"
    ]


def find_missing_cancel_policy(steps):
    """오퍼마다 `기본 취소 정책` 이 있어야 한다 — 빠지면 배너가 🔴 로 막는다(2026-09-04)."""
    problems = []
    for step in steps:
        title = step["title"]
        if not title.startswith(OFFER_CREATE_TITLE):
            continue
        raw = step["fields"].get(CANCEL_POLICY_FIELD)
        if raw is None:
            problems.append(
                f"{step['num']}단계: `{CANCEL_POLICY_FIELD}` 줄이 없다 — 오퍼마다 취소 정책을 고른다"
            )
            continue
        value = strip_select(raw).strip()
        if value in CANCEL_POLICY_EMPTY:
            problems.append(
                f"{step['num']}단계: `{CANCEL_POLICY_FIELD}` 가 `{value or '빈 값'}` 이다 — "
                "판매 시작 배너가 🔴 로 막는다(계약서에 없으면 사용자가 정한 공용 정책을 고른다)"
            )
    return problems


def find_legacy_offer_edit_steps(steps):
    """`오퍼 고치기` 단계는 쓰지 않는다 — 고칠 `기본 오퍼` 가 더 이상 생기지 않는다."""
    return [
        f"{step['num']}단계: `{OFFER_EDIT_TITLE}` 단계는 쓰지 않는다 — "
        f"호텔은 오퍼 0건으로 만들어진다, `{OFFER_CREATE_TITLE}` 로 [오퍼 추가] 한다"
        for step in steps
        if step["title"].startswith(OFFER_EDIT_TITLE)
    ]


def find_rooms_before_offer(steps):
    """`룸 만들기`·`판매 연결` 이 첫 `오퍼 만들기` 보다 앞에 오면 오류.

    오퍼가 하나도 없으면 판매 연결 카드의 [객실 추가] 버튼이 그려지지 않고, 드로어를 열어도
    폼 대신 "오퍼를 먼저 만드세요" 만 뜬다 — 지시서가 그 순서로 가면 담당자가 막힌다.
    """
    first_offer = next(
        (step["num"] for step in steps if step["title"].startswith(OFFER_CREATE_TITLE)), None
    )
    early = [
        step
        for step in steps
        if step["title"].startswith(AFTER_OFFER_TITLES)
        and (first_offer is None or step["num"] < first_offer)
    ]
    return [
        f"{step['num']}단계: `{step['title']}` 가 `{OFFER_CREATE_TITLE}` 보다 앞이다 — "
        "오퍼가 없으면 객실 추가가 막힌다(오퍼를 먼저 만든다)"
        for step in early
    ]


def find_campaign_uses(steps):
    """캠페인은 걷혔다 — `캠페인 만들기` 단계도, 오퍼의 캠페인 이름표도 두지 않는다."""
    problems = []
    for step in steps:
        title = step["title"]
        if title.startswith(CAMPAIGN_TITLE):
            problems.append(
                f"{step['num']}단계: 캠페인 단계는 만들지 않는다(오퍼 이미지로 대신)"
            )
            continue
        if not title.startswith(OFFER_CREATE_TITLE):
            continue
        raw = step["fields"].get(CAMPAIGN_FIELD)
        if raw is None:
            continue
        value = strip_select(raw).strip()
        if value not in CAMPAIGN_NONE:
            problems.append(
                f"{step['num']}단계: `{CAMPAIGN_FIELD}` 이 `{value or '빈 값'}` 이다 — "
                "캠페인은 걷혔다, 언제나 `선택: — 없음 —`(오퍼의 겉면은 `오퍼 이미지`)"
            )
    return problems


def find_skip_warning_steps(steps):
    """`경고 넘어가기` 단계는 쓰지 않는다 — 배너에 🟡 가 남으면 지시서를 고친다."""
    problems = []
    for step in steps:
        saves = step["saves"]
        is_skip = SKIP_WARNING_TITLE in step["title"] or (saves and saves[-1] == SKIP_WARNING_BUTTON)
        if is_skip:
            problems.append(
                f"{step['num']}단계: `{SKIP_WARNING_TITLE}` 단계는 쓰지 않는다 — "
                "판매 시작 전 배너에 🟡 가 남으면 지시서가 틀린 것이니 원인을 지시서에서 고친다"
            )
    return problems


def find_addon_card_gaps(steps):
    """같은 이름의 부가옵션이 오퍼 여럿에 있는데 가격 넣기 카드가 오퍼를 한정하지 않은 곳."""
    offers_by_name = {}
    for step in steps:
        title = step["title"]
        if "부가옵션" not in title or "가격" in title:
            continue
        name = step["fields"].get("이름")
        offer = strip_select(step["fields"].get("오퍼", ""))
        if name and offer:
            offers_by_name.setdefault(name.strip(), set()).add(offer)
    problems = []
    for step in steps:
        title = step["title"]
        if "부가옵션" not in title or "가격" not in title:
            continue
        line = head(step, "카드")
        if not line:
            continue
        if ADDON_CARD_OFFER_RE.match(line):
            continue
        name = card_name(step)
        if name and len(offers_by_name.get(name, ())) > 1:
            problems.append(
                f"{step['num']}단계: 부가옵션 `{name}` 이 오퍼 "
                f"{len(offers_by_name[name])}곳에 있다 — 카드 줄에 "
                "`<이름>` — 오퍼 칸이 `<오퍼>` 인 카드 형식으로 오퍼를 적어야 한다"
            )
    return problems


def find_promo_common_cards(steps):
    """(비활성) `전 오퍼 공통` 카드는 실재한다 — 오퍼 없는 공통 프로모션이며 모든 오퍼에 붙는다.
    공통 프로모션이 0건이면 화면이 카드를 감출 뿐이라(러너가 오퍼 0 요청으로 연다) 검사하지 않는다."""
    return []

def supply_currency(steps):
    """`호텔 만들기` 단계의 `공급 통화` 값. 단계나 칸이 없으면 None."""
    for step in steps:
        if step["title"].startswith(CURRENCY_STEP_TITLE):
            value = step["fields"].get("공급 통화")
            if value is None:
                return None
            return strip_select(value) or None
    return None


def find_season_save_gaps(steps):
    """`시즌 만들기` 단계는 `→ [추가]` 로 끝나야 한다(드로어 버튼 문구)."""
    problems = []
    for step in steps:
        if not step["title"].startswith("시즌 만들기"):
            continue
        saves = step["saves"]
        if saves and saves[-1] != "추가":
            problems.append(f"{step['num']}단계: 시즌 만들기의 마지막 줄은 `→ [추가]` 다 (지금 [{saves[-1]}])")
    return problems


# 0단계 — 호텔을 만들기 전에 반드시 먼저 보는 세 화면. 제목에 이 낱말이 들어 있으면 통과한다
# (`환율 등록 확인` 처럼 말이 붙어도 되게 부분 일치로 본다)
ZERO_STEPS = ["환율", "거래처", "도시"]

# 공급 통화는 USD 가 원칙이다 — 다른 통화면 경고만 한다(막지는 않는다)
DEFAULT_CURRENCY = "USD"
CURRENCY_STEP_TITLE = "호텔 만들기"

# 칸 이름 뒤에 붙는 통화 꼬리표는 화면 사전과 표기가 달라 떼고 비교한다
CURRENCY_SUFFIX_RE = re.compile(r"\s*\((?:[A-Z]{3}|공급 통화)\)")

# 금액이 아닌 숫자 칸(개수·연도·인원·전화·좌표·우선순위)
NOT_MONEY_FIELD_RE = re.compile(r"(객실 수|개수|연도|인원|전화|위도|경도|우선순위|층|번호|수량|박\)|D-N)")

# 반복 행 이름은 `<그룹> N · <열 이름>` 형식 — 사전과는 열 이름으로 대조한다
REPEAT_PREFIX_RE = re.compile(r"^.+? \d+ · ")

# 상품 공통 화면의 칸이라 화면 사전이 일부러 담지 않는 이름 — 대조에서 통과시킨다
DICT_EXEMPT = {"상품명"}

# 금액이 아닌 숫자(날짜·시각·좌표·면적)는 대조에서 뺀다
DATE_RE = re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")
TIME_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?")
COORD_RE = re.compile(r"\d+\.\d{6,}")
AREA_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*㎡")
# 전화번호 — `+` 로 시작하거나 하이픈으로 이어 붙인 숫자 묶음 (+84-297-0000000, 02-123-4567)
PHONE_RE = re.compile(r"\+?\d{1,4}(?:-\d{2,8}){2,5}")
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def norm_field(name):
    """칸 이름 비교용 정규화 — 통화 꼬리표 제거 + 공백 정리."""
    return re.sub(r"\s+", " ", CURRENCY_SUFFIX_RE.sub("", name)).strip()


def strip_repeat_prefix(name):
    """`구간 1 · 수수료 값` → `수수료 값`. 반복 행이 아니면 그대로."""
    return REPEAT_PREFIX_RE.sub("", name, count=1).strip()


def strip_row_suffix(name):
    """`오퍼별 표시명 · Single` → `오퍼별 표시명`. 그 칸 이름이 아니면 그대로.

    판매 연결 일괄 드로어의 표시명은 체크한 룸마다 칸이 하나씩 늘어난다 — 사전에는 한 줄
    (`오퍼별 표시명 · 〈룸 카테고리명〉`)로 있고 지시서는 룸 이름을 넣어 쓴다.
    """
    for base in ROW_SUFFIX_FIELDS:
        if name.startswith(f"{base} · "):
            return base
    return name


def load_dictionary(path):
    """화면 사전에서 필드 label · screen_label 과 반복 행의 columns 를 모은다."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    labels = set()
    for screen in data.get("screens") or []:
        for block in screen.get("blocks") or []:
            for field in block.get("fields") or []:
                for key in ("label", "screen_label"):
                    value = field.get(key)
                    if value:
                        labels.add(norm_field(value))
                # 체크박스 칸은 지시서에서 `<칸 이름> · <체크박스 문구>` 로도 쓴다
                checkbox_text = field.get("checkbox_text")
                if checkbox_text:
                    for key in ("label", "screen_label"):
                        value = field.get(key)
                        if value:
                            labels.add(norm_field(f"{value} · {checkbox_text}"))
                # 반복 행 필드가 열 이름 목록을 들고 있으면 그것도 허용한다(아직 없는 사전이면 무시)
                for column in field.get("columns") or []:
                    if isinstance(column, str):
                        labels.add(norm_field(column))
                    elif isinstance(column, dict):
                        for key in ("label", "screen_label"):
                            value = column.get(key)
                            if value:
                                labels.add(norm_field(value))
    return labels


def norm_num(token):
    """숫자 토큰을 비교용 표준형으로. 실패하면 None."""
    try:
        return format(decimal.Decimal(token.replace(",", "")).normalize(), "f")
    except (decimal.InvalidOperation, ValueError):
        return None


def amounts_in(text, min_digits=3):
    """금액으로 볼 만한 숫자만 뽑는다 — 날짜·시각·좌표·면적·전화번호 제외, 3자리 이상이거나 소수."""
    cleaned = text
    for pat in (DATE_RE, PHONE_RE, TIME_RE, COORD_RE, AREA_RE):
        cleaned = pat.sub(" ", cleaned)
    found = []
    for m in NUM_RE.finditer(cleaned):
        token = m.group(0)
        whole = token.split(".")[0].replace(",", "")
        if len(whole) < min_digits and "." not in token:
            continue
        key = norm_num(token)
        if key:
            found.append((key, token))
    return found


def check(md_path, photos_dir=None, share_name=None, dictionary_path=None, contract_path=None):
    with open(md_path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    text = "\n".join(lines)

    steps = [l for l in lines if l.startswith("## ")]
    saves = [l for l in lines if l.startswith("→ [")]

    rows = [ROW.match(l) for l in lines if ROW.match(l)]
    rows = [(m.group(1).strip(), m.group(2).strip()) for m in rows if m.group(1).strip() not in ("칸", "---")]
    kinds = {"입력": 0, "선택": 0, "체크": 0, "해제": 0, "비움": 0, "자동": 0, "파일": 0, "괄호": 0}
    for _, v in rows:
        if v.startswith("선택:"):
            kinds["선택"] += 1
        elif v == "체크":
            kinds["체크"] += 1
        elif v == "해제":
            kinds["해제"] += 1
        elif v.startswith("비움"):
            kinds["비움"] += 1
        elif v.startswith("자동 입력됨"):
            kinds["자동"] += 1
        elif v.startswith("파일:"):
            kinds["파일"] += 1
        elif v.startswith("(") and v.endswith(")"):
            kinds["괄호"] += 1
        else:
            kinds["입력"] += 1

    forb = {w: text.count(w) for w in FORBIDDEN if text.count(w)}
    circled = len(CIRCLED.findall(text))
    # 주소 칸(`Lot TT13` 같은 필지 번호)은 시트 좌표가 아니다 — 그 행은 검사하지 않는다
    def _address_row(l):
        m = ROW.match(l)
        return bool(m and "주소" in m.group(1))
    cells = [
        m.group(0)
        for l in lines if not l.startswith("```") and not _address_row(l)
        for m in CELL.finditer(l)
        if not CELL_EXCLUDE.match(m.group(0))
    ]

    folders = [l for l in lines if l.startswith("폴더:")]
    bad_folder = []
    if share_name:
        expected = f"폴더: {share_name}/사진"
        bad_folder = [l for l in folders if l.strip() != expected]

    have = set()
    if photos_dir:
        if os.path.isdir(photos_dir):
            have = {f for f in os.listdir(photos_dir) if re.search(r"\.(jpe?g|png)$", f, re.I)}
    # 출처 URL 안의 파일명이 참조로 잡히지 않게 URL 부분은 떼고 찾는다
    ref_text = "\n".join(PHOTO_SRC_RE.sub(lambda m: f"- {m.group('name')}", l) for l in lines)
    referenced = set(FILE_REF_RE.findall(ref_text))
    bad_sources = [
        f"{m.group('name')} — {m.group('url')}"
        for m in (PHOTO_SRC_RE.match(l) for l in lines)
        if m and not HTTP_URL_RE.match(m.group("url"))
    ]
    missing_files = sorted(referenced - have) if photos_dir else []
    unused_files = sorted(have - referenced) if photos_dir else []

    parsed = parse_steps(lines)
    season_overlaps = find_season_overlaps(parsed)
    needless_overwrite = find_needless_overwrite(parsed)
    cancel_policy_gaps = find_missing_cancel_policy(parsed)
    legacy_offer_steps = find_legacy_offer_edit_steps(parsed)
    rooms_before_offer = find_rooms_before_offer(parsed)
    skip_warning_steps = find_skip_warning_steps(parsed)
    campaign_uses = find_campaign_uses(parsed)
    addon_card_gaps = find_addon_card_gaps(parsed)
    promo_common = find_promo_common_cards(parsed)
    season_saves = find_season_save_gaps(parsed)
    currency = supply_currency(parsed)

    nums = [int(m.group(1)) for l in steps for m in [STEP_RE.match(l)] if m]
    seq_ok = nums == list(range(1, len(nums) + 1))

    titles = {}
    for l in lines:
        m = STEP_TITLE_RE.match(l)
        if m:
            titles.setdefault(int(m.group(1)), m.group(2))
    zero_missing = [
        want for i, want in enumerate(ZERO_STEPS, start=1) if want not in titles.get(i, "")
    ]

    dict_error = None
    unknown_fields = []
    if dictionary_path:
        try:
            labels = load_dictionary(dictionary_path)
        except (OSError, ValueError) as e:
            dict_error = str(e)
        else:
            seen = []
            for name, _ in rows:
                n = norm_field(name)
                if not n or n in labels or n in DICT_EXEMPT or n in seen:
                    continue
                if strip_repeat_prefix(n) in labels:  # 반복 행은 열 이름으로 한 번 더 본다
                    continue
                if strip_row_suffix(n) in labels:  # `오퍼별 표시명 · <룸 이름>` 은 앞부분으로 본다
                    continue
                seen.append(n)
            unknown_fields = seen

    contract_error = None
    loose_amounts = []
    if contract_path:
        try:
            with open(contract_path, encoding="utf-8") as handle:
                contract_text = handle.read()
        except OSError as e:
            contract_error = str(e)
        else:
            known = {key for key, _ in amounts_in(contract_text, min_digits=1)}
            seen_amounts = {}
            for name, v in rows:
                if "㎡" in name:  # 면적 칸은 값에 단위가 없다 — 칸 이름으로 걸러낸다
                    continue
                if NOT_MONEY_FIELD_RE.search(name):  # 개수·연도·인원·전화·좌표 칸은 금액이 아니다
                    continue
                for key, token in amounts_in(v):
                    if key not in known and key not in seen_amounts:
                        seen_amounts[key] = token
            loose_amounts = [seen_amounts[k] for k in sorted(seen_amounts, key=lambda x: decimal.Decimal(x))]

    return {
        "steps": len(steps), "saves": len(saves), "seq_ok": seq_ok, "rows": len(rows), "kinds": kinds,
        "forbidden": forb, "circled": circled, "sheet_cells": cells[:5],
        "folder_lines": len(folders), "bad_folder": bad_folder,
        "photos_checked": bool(photos_dir), "photos_have": len(have),
        "photos_missing": missing_files, "photos_unused": unused_files,
        "bad_sources": bad_sources,
        "zero_missing": zero_missing,
        "season_overlaps": season_overlaps, "needless_overwrite": needless_overwrite,
        "cancel_policy_gaps": cancel_policy_gaps, "skip_warning_steps": skip_warning_steps,
        "legacy_offer_steps": legacy_offer_steps, "rooms_before_offer": rooms_before_offer,
        "campaign_uses": campaign_uses,
        "addon_card_gaps": addon_card_gaps,
        "promo_common": promo_common, "season_saves": season_saves,
        "currency": currency,
        "dict_checked": bool(dictionary_path), "dict_error": dict_error, "unknown_fields": unknown_fields,
        "contract_checked": bool(contract_path), "contract_error": contract_error,
        "loose_amounts": loose_amounts,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="입력 지시서(manual.md) 형식 검사")
    ap.add_argument("manual", help="검사할 manual.md 경로")
    ap.add_argument("--photos", default=None, help="사진 폴더 (선택 — 주면 파일 존재까지 확인)")
    ap.add_argument("--share-name", default=None, help="공유 폴더명 (선택 — 주면 `폴더:` 줄 형식까지 확인, 예: 우에노_토우가네야)")
    ap.add_argument("--dictionary", default=None,
                    help="화면 사전 JSON (선택 — 생략하면 ../references/screen-dictionary.json 을 자동으로 씀)")
    ap.add_argument("--contract", default=None, help="계약서 md (선택 — 주면 금액이 계약서에 있는지 경고로 알림)")
    ap.add_argument("--strict", action="store_true",
                    help="경고(사전에 없는 칸 이름 · 계약서에 없는 금액)를 실패로 다룬다")
    args = ap.parse_args(argv)

    if not os.path.exists(args.manual):
        print(f"파일 없음: {args.manual}")
        return 1

    dictionary = args.dictionary
    if dictionary is None:
        default_dict = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), os.pardir, "references", "screen-dictionary.json"
        )
        if os.path.exists(default_dict):
            dictionary = os.path.normpath(default_dict)

    r = check(args.manual, args.photos, args.share_name, dictionary, args.contract)

    problems = []
    if r["steps"] != r["saves"]:
        problems.append(f"단계 {r['steps']} ≠ 저장 {r['saves']}")
    if not r["seq_ok"]:
        problems.append("단계 번호 불연속")
    if r["forbidden"]:
        problems.append(f"금지어 {r['forbidden']}")
    if r["circled"]:
        problems.append(f"원문자 {r['circled']}")
    if r["sheet_cells"]:
        problems.append(f"좌표 의심 {r['sheet_cells']}")
    if r["bad_folder"]:
        problems.append(f"폴더 줄 이상 {r['bad_folder'][:2]}")
    if r["photos_missing"]:
        problems.append(f"없는 사진 참조 {r['photos_missing']}")
    if r["zero_missing"]:
        problems.append("0단계(환율·거래처·도시 확인) 누락")
    for p in (r["season_overlaps"] + r["cancel_policy_gaps"] + r["skip_warning_steps"]
              + r["legacy_offer_steps"] + r["rooms_before_offer"]
              + r["campaign_uses"] + r["addon_card_gaps"] + r["promo_common"] + r["season_saves"]):
        problems.append(p)
    if r["dict_error"]:
        problems.append(f"화면 사전 읽기 실패 {r['dict_error']}")
    if r["contract_error"]:
        problems.append(f"계약서 읽기 실패 {r['contract_error']}")

    warnings = []
    if r["currency"] and r["currency"] != DEFAULT_CURRENCY:
        warnings.append(
            f"공급 통화가 {DEFAULT_CURRENCY} 가 아니다({r['currency']}) — "
            "사용자에게 확인받은 기록이 changes.md 에 있어야 한다"
        )
    for w in r["needless_overwrite"]:
        warnings.append(w)
    if r["unknown_fields"]:
        shown = r["unknown_fields"][:15]
        msg = f"사전에 없는 칸 이름 {len(r['unknown_fields'])}개: {shown}"
        (problems if args.strict else warnings).append(msg)
    if r["bad_sources"]:
        warnings.append(f"사진 출처 형식 {len(r['bad_sources'])}개 (http(s):// 아님): {r['bad_sources'][:5]}")
    if r["loose_amounts"]:
        shown = r["loose_amounts"][:15]
        msg = f"계약서에 없는 금액 {len(r['loose_amounts'])}개: {shown}"
        (problems if args.strict else warnings).append(msg)

    k = r["kinds"]
    print(
        f"단계 {r['steps']} · 값 {r['rows']} "
        f"(입력 {k['입력']} 선택 {k['선택']} 체크 {k['체크']} 해제 {k['해제']} 비움 {k['비움']} 자동 {k['자동']} 파일 {k['파일']}) "
        f"· 폴더줄 {r['folder_lines']}"
    )
    if r["photos_checked"]:
        print(f"사진 {r['photos_have']}장 확인 (미사용 {len(r['photos_unused'])})")
    else:
        print("사진 폴더 미지정 — 파일 존재 확인 건너뜀 (--photos 로 지정)")
    if not args.share_name:
        print("공유 폴더명 미지정 — `폴더:` 줄 형식 확인 건너뜀 (--share-name 으로 지정)")
    if not r["dict_checked"]:
        print("화면 사전 없음 — 칸 이름 확인 건너뜀 (--dictionary 로 지정)")
    if not r["contract_checked"]:
        print("계약서 미지정 — 금액 대조 건너뜀 (--contract 로 지정)")

    for w in warnings:
        print(f"   ⚠ {w}")

    if problems:
        for p in problems:
            print(f"   ✗ {p}")
        print("문제 있음")
        return 1

    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
