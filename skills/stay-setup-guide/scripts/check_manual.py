#!/usr/bin/env python3
"""check_manual.py — 지시서 원고(manual.md) 형식 검사.

원고(`_원고/manual.md`)를 검사하고, 통과한 원고만 `render_card.py` 가 지시서
(`<이름>_입력지시서.html`)로 렌더한다. 담당자에게 건네는 것은 그 지시서 하나다.

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
- 오퍼 `투숙 시작`·`판매일 열기` 시작일이 오늘보다 앞인지(오류 — 판매 구간은 지시서를 만드는 날부터다)
- 오퍼의 `예약 시작`·`예약 종료` 가 `비움` 인지(경고 — 예약 기간 제한이 없어진다)
- `시즌 만들기` 의 `기간 종료` 가 오늘보다 앞인지(오류 — 판매 구간 밖 시즌은 만들지 않는다)
- 같은 오퍼의 시즌끼리 날짜가 하루라도 겹치는지(겹침·포함 모두 오류 — 배너에 🟡 가 남는다)
- `시즌 가격 채우기` 에 `이미 값이 있는 날도 덮기 | 체크` 가 남아 있는지(겹치지 않으면 필요 없다 — 경고)
- 오퍼마다 `기본 취소 정책` 이 있는지(`지정 안 함`·빈 값이면 오류 — 배너가 🔴 로 막는다)
- `오퍼 고치기` 단계가 있는지(있으면 오류 — 호텔은 빈 상태로 만들어져 고칠 기본 오퍼가 없다)
- `룸 만들기`·`판매 연결` 단계가 첫 `오퍼 만들기` 보다 앞에 있는지(있으면 오류 — 오퍼가 없으면 객실 추가가 막힌다)
- `경고 넘어가기` 단계가 있는지(있으면 오류 — 원인을 지시서에서 고친다)
- `캠페인 만들기` 단계가 있는지(있으면 오류) · 어느 단계든 `캠페인` 칸이 있는지(있으면 오류 — 화면에서 없어졌다)
- 갈라디너·컴펄서리 디너를 부가옵션으로 넣었는지(오류 — 의무 부과금 하나로 넣는다)
- 갈라디너 부과금이 `인당` 인지 · 연령 구간이 있는데 `연령별 단가` 줄이 없는지(오류)
- 유료 연령 구간마다 `시즌 가격 채우기` 에 `아동 추가 금액 — <노출명>` 줄이 있는지(오류 — 아이 1박 요금의 자리는 그 칸 하나다)
- `아동 추가 금액` 을 적었는데 `인원 조합(선택)` 이 비었는지(오류 — 아동 금액은 성인 좌표 위에 얹혀 화면이 저장을 막는다)
- `연령 구간 만들기` 가 그 오퍼의 첫 `시즌 가격 채우기` 보다 앞인지(오류 — 유료 구간이 없으면 그 드로어에 아동 금액 칸이 서지 않는다)
- 부가옵션이 아이의 잠자리(쉐어베드·소파베드·아동 1박)를 파는지(오류 — 식사·픽업·엑스트라베드는 따로 사는 것이라 부가옵션이 맞다)
- `밴드 코드` 가 영대문자·숫자 2~8자인지(오류 — 그 코드가 가격 셀 좌표에 그대로 실린다)
- `인원 조합(선택)`·`인원 조합별 조정(선택)` 의 키가 A-형(`A2`·`A2C1_CHD`)인지(오류 — 옛 숫자 키 `2,3`·`3:+14`)
- `박수별 단가(선택)` 가 `박수:1박 단가` 목록인지(오류 — 부호 없음 · 박수 2 이상 · 같은 박수 한 번)
- 부과금 이름이 `(성인)` 으로 끝나는지(경고 — 성인·소아를 하나로 합친다)
- `룸 만들기` 의 `룸 이름` 에 한글이 있는지(경고 — 룸 이름은 계약서 원어, 한글은 `오퍼별 표시명`)
- 엑스트라베드 부가옵션의 `의무 규칙` 이 `의무 아님` 인지(경고 — 계약서가 필수라고 하면 `기준 성인 초과 시 의무`)
- 같은 이름의 부가옵션이 오퍼 여럿에 있으면 가격 넣기 카드 줄이 오퍼를 한정하는지
- `시즌 만들기` 단계가 `→ [추가]` 로 끝나는지
- `취소정책 만들기` 단계가 `→ [추가]` 로 끝나는지(새 정책은 [추가], [저장] 은 이미 있는 정책을 고칠 때다)
- 반복 행 이름이 정본 형식(`<칸 이름> <N> · <하위 칸>`)인지 — 홑 빈칸, 가운뎃점은 빈칸으로 감싼 ` · `
- `체크`/`해제` 를 체크박스가 아닌 칸(다중 체크·선택·라디오)에 썼는지(고른 것은 `선택: …`, 안 고르면 `비움`)
- `호텔 만들기` 단계의 `공급 통화` 가 USD 인지(아니면 경고만 — 막지 않는다)
- 혜택의 `수량` 이 비었는데 `제공 주기` 를 체크했는지(오류 — 그 칸은 수량이 있어야 화면에 선다)

사용법:
    python3 check_manual.py <_원고/manual.md> [--photos DIR] [--share-name NAME]
                            [--dictionary screen-dictionary.json] [--contract contract.md]

--photos 를 생략하면 사진 존재 확인은 건너뛴다.
--share-name 을 생략해도 원고가 `<이름>/_원고/manual.md` 자리에 있으면 공유 폴더명 `<이름>` 을
경로에서 알아낸다. 그 자리가 아니면 `폴더:` 줄 형식 확인은 건너뛴다(줄 목록만 보여준다).
--dictionary 를 생략하면 스크립트 옆의 ../references/screen-dictionary.json 을 쓴다(없으면 건너뛴다).
--contract 를 생략하면 금액 대조는 건너뛴다.
날짜 검사의 "오늘" 은 원고 맨 앞의 `작성일: YYYY-MM-DD` 줄이고, 그 줄이 없으면 검사하는 날이다.
"""
import argparse
import datetime
import decimal
import json
import os
import re
import sys

#: 원고 폴더 이름 — 공유 폴더 `<이름>/` 안에서 원고·부속 파일이 사는 곳.
#: 담당자에게 건네는 것은 `<이름>/<이름>_입력지시서.html` 하나이고, 원고는 여기 남는다.
DRAFT_DIR = "_원고"


def derive_share_name(manual_path):
    """원고 경로가 `<이름>/_원고/manual.md` 꼴이면 공유 폴더명 `<이름>` 을 돌려준다.

    옛 자리(`<이름>/manual.md`)나 그 밖의 경로면 None — 그때는 `--share-name` 으로 준다.
    """
    draft = os.path.dirname(os.path.abspath(os.path.expanduser(manual_path)))
    if os.path.basename(draft) != DRAFT_DIR:
        return None
    share = os.path.dirname(draft)
    name = os.path.basename(share)
    return name or None


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
# 사진 목록의 한 줄 — `- hotel_01.jpg` 또는 `- hotel_01.jpg — 출처: https://…`
PHOTO_LINE_RE = re.compile(
    r"^\s*-\s*(?P<name>[\w][\w.\-]*\.(?:jpe?g|png))"
    r"(?:\s*[\u2014\u2013-]+\s*출처\s*:\s*\S+)?\s*$",
    re.IGNORECASE,
)
# 표 칸의 파일 값 — `| 오퍼 이미지 | 파일: offer_hero.jpg |`
PHOTO_FIELD_RE = re.compile(
    r"^파일\s*:\s*(?P<name>[\w][\w.\-]*\.(?:jpe?g|png))\s*$", re.IGNORECASE
)

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
# 새 취소정책을 만드는 드로어의 저장 버튼은 [추가] 다 — [저장] 은 이미 있는 정책을 고칠 때다
# (`references/screen-dictionary.md` §취소정책: "새로 만들 때의 저장 버튼은 [추가]").
CANCEL_POLICY_CREATE_TITLE = "취소정책 만들기"
CANCEL_POLICY_CREATE_BUTTON = "추가"
CANCEL_POLICY_EMPTY = {"지정 안 함", "", "비움", "—", "-", "— 없음 —", "- 없음 -", "(지정 안 함)"}

# 캠페인은 2026-09-04 ERP 화면에서 제거됐다(모델·컬럼만 휴면 보존) — 오퍼가 `오퍼 이미지` 로
# 겉면을 직접 가진다. 단계로도 만들지 않고, 어느 단계 표에도 `캠페인` 줄을 두지 않는다.
CAMPAIGN_TITLE = "캠페인 만들기"
CAMPAIGN_FIELD = "캠페인"

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

# `오퍼별 표시명 · <룸 카테고리명>` 처럼 뒤에 행 이름이 붙는 칸 — 사전과는 앞부분으로 대조한다.
# `연령별 단가 · <노출명>` 도 같다: 부과금 드로어의 그 표는 이 오퍼의 연령 구간마다 칸이 하나씩 늘어난다.
# `아동 추가 금액 — <노출명>` 은 시즌 가격 채우기 드로어에서 **유료** 연령 구간마다 늘어난다 —
# 구분자가 가운뎃점이 아니라 EM DASH 라 붙는 말을 뗄 때 그 구분자도 함께 본다.
ROW_SUFFIX_FIELDS = ("오퍼별 표시명", "연령별 단가", "아동 추가 금액")
#: 뒤에 붙는 행 이름을 가르는 구분자 — 정본은 ` · ` 와 ` — ` 다(원고 오타로 EN DASH·하이픈도 받는다).
ROW_SUFFIX_SEPARATORS = (" \u00b7 ", " \u2014 ", " \u2013 ", " - ")

# 룸 이름은 계약서·요금표가 부르는 **원어 그대로**다 — ERP 객실 목록과 계약서 요금표를 이름으로
# 맞춰야 어느 줄이 어느 룸인지 대조된다. 고객이 보는 한글 이름은 판매 연결 일괄 드로어의
# `오퍼별 표시명` 이 따로 가진다. 실제 사례(2026-09-07): 같은 계약서로 만든 두 지시서가
# `Superior Ocean View` 와 `슈페리어 오션뷰` 로 갈렸다.
ROOM_CREATE_TITLE = "룸 만들기"
ROOM_NAME_FIELD = "룸 이름"
HANGUL_RE = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")

# 엑스트라베드 부가옵션의 `의무 규칙` — 계약서가 "기준 인원 외 성인 추가 시 엑스트라베드 필수"
# 라고 하면 `기준 성인 초과 시 의무 (엑스트라베드)` 다. `의무 아님` 으로 두면 고객이 세 번째 성인을
# 침대 없이 넣을 수 있다. 계약서가 정말 선택이라고 하는 경우도 있어 경고로만 알린다.
EXTRA_BED_NAME_RE = re.compile(r"엑스트라\s*베드")
ADDON_RULE_FIELD = "의무 규칙"
ADDON_RULE_OPTIONAL = "의무 아님"
ADDON_RULE_OVER_ADULT = "기준 성인 초과 시 의무"

# 연령 구간 — 계약서에 아동 정책이 있을 때만 넣는 선택 단계.
# 구간은 오퍼에 매달리므로 그 오퍼를 만든 뒤에 오고, 부과금 드로어의 `연령별 단가` 표와
# 시즌 가격 채우기 드로어의 `아동 추가 금액` 칸은 **이미 만들어 둔 구간만** 보여 주므로
# 둘보다 앞이다 — 2026-09-08 부로 자리가 `가격 셀 손입력` 뒤에서 `객실(룸)` 앞으로 올라왔다.
AGE_BAND_TITLE = "연령 구간 만들기"
AGE_RATE_FIELD = "연령별 단가"

# 연령 구간의 `요금 기준 유형` — `무료` · `정액` · `성인 요금의 %` · `타 밴드 요금과 동일`.
# `무료` 가 **아닌** 구간(= 유료)마다 `시즌 가격 채우기` 드로어에 `아동 추가 금액 — <노출명>`
# 칸이 하나씩 선다(2026-09-08 ERP 실측). 그 칸이 성인 좌표 옆에 아동 좌표를 함께 깔므로
# (`A2` → `A2C1_CHD` = A2 + 그 금액), 아이가 방에서 자는 1박 요금은 **그 칸 한 곳**에만 둔다.
AGE_BAND_TYPE_FIELD = "요금 기준 유형"
AGE_BAND_FREE_TYPE = "무료"
AGE_BAND_NAME_FIELD = "노출명"
AGE_BAND_CODE_FIELD = "밴드 코드"
SEASON_FILL_TITLE = "시즌 가격 채우기"
CHILD_EXTRA_FIELD = "아동 추가 금액"
#: `아동 추가 금액 — 소아` — 구분자는 EM DASH(U+2014)를 빈칸으로 감싼 것이 정본이다.
#: 원고 오타 하나로 검사가 헛돌면 안 되므로 EN DASH·하이픈·가운뎃점도 같은 칸으로 읽는다.
CHILD_EXTRA_LABEL_RE = re.compile(
    r"^아동\s*추가\s*금액(?:\s*[\u2014\u2013\-\u00b7\u30fb]\s*(?P<name>.+))?$"
)

# 밴드 코드 — 정본은 `occupancy_key.BAND_CODE_RE`(`^[A-Z0-9]{2,8}$`)다. 소문자로 쳐도 서버가
# 대문자로 굳히므로 검사기는 소문자를 받아 주고, 밑줄·한글·공백·기호·1자·9자 이상만 막는다
# (밑줄은 좌표 조각 구분자다 — `A2C1_CHD`). 정본 표기는 `CHD`·`INF`·`TEEN`.
BAND_CODE_RE = re.compile(r"^[A-Za-z0-9]{2,8}$")

# 인원 조합 좌표 — `stay.services.occupancy_key` 의 A-형 정규형이다: 성인 수 `A2` 뒤에 아동
# 조각이 붙고(첫 조각은 붙여 `A2C1_CHD`, 둘째부터 `_C1_TEEN` 이 더 붙는다). 옛 숫자 키
# (`2,3` · `3:+14`)도 서버가 받아 A-형으로 저장하지만, 같은 좌표가 화면·요금표·엔진 로그에서
# A-형으로 다시 나오므로 지시서는 A-형만 쓴다.
OCCUPANCY_KEYS_FIELDS = ("인원 조합(선택)", "인원 조합")
OCCUPANCY_ADJUST_FIELDS = ("인원 조합별 조정(선택)", "인원 조합별 조정")
OCCUPANCY_KEY_RE = re.compile(r"^A\d+(?:C\d+_[A-Z0-9]{2,8})?(?:_C\d+_[A-Z0-9]{2,8})*$")
BARE_NUMBER_RE = re.compile(r"^\d+$")

# 박수별 단가 — `박수:1박 단가` 를 쉼표로 잇는다(`3:100,5:90` = 3박부터 1박 100, 5박부터 90).
# 차액이 아니라 **단가**라 부호를 붙이지 않고, 1박 단가는 위 `판매 단가(공급 통화)` 칸이라
# 박수는 2 이상이다. 층 하나가 셀 수를 통째로 곱하므로 같은 박수를 두 번 적지 않는다.
LOS_PRICES_FIELDS = ("박수별 단가(선택)", "박수별 단가")
LOS_ENTRY_RE = re.compile(r"^(?P<nights>\d+)\s*:\s*(?P<price>[\d,]+(?:\.\d+)?)$")

# 계약서가 아동을 말하면(나이대·정원 내 무료 투숙·성인 요금의 %·쉐어베드) 그것은 **인원**이다 —
# 방에서 자는 아이는 `연령 구간` 으로 넣어야 고객 화면 인원 선택기에 소아·유아가 선다.
# 부가옵션으로 만들면 "아이를 추가로 산다" 로 읽히고 인원 선택기에는 성인만 남는다.
# 실제 사례(2026-09-07): 정원 내 소아·유아 무료 투숙 계약이 연령 구간 0개로 깔렸다.
# 그 아이의 **1박 요금**은 2026-09-08 부로 자리가 하나다 — `시즌 가격 채우기` 의
# `아동 추가 금액 — <노출명>` 칸(§B-4). 부가옵션은 **따로 사는 것**(식사 업그레이드·픽업·
# 엑스트라베드)만 판다.
ADDON_STEP_TITLES = ("부가옵션 만들기", "부과금 추가")
CHILD_AUDIENCE_RE = re.compile(r"(소아|유아|아동|어린이)")
# 이름이 **대상만** 말하는 꼴 — `소아` · `소아 (만6~11세)`. 무엇을 파는지가 없다.
AUDIENCE_ONLY_NAME_RE = re.compile(r"^(소아|유아|아동|어린이|성인)\s*(\(.*\))?$")
# 아동이 방에서 잔다는 표시 — 이 말이 보이면 연령 구간이 있어야 한다.
CHILD_STAY_RE = re.compile(r"(무료\s*투숙|무료\s*숙박|쉐어\s*베드|쉐어베드|share\s*bed|엑스트라베드\s*무료)", re.I)
CHILD_POLICY_STEP_TITLES = ("부가옵션", "혜택")

# 부가옵션이 팔면 안 되는 것 — **아이가 방에서 자는 1박**이다(§D-1, 2026-09-08).
# 이름의 아동 대상어 + 숙박 성격 낱말로 잡는다.
CHILD_ADDON_AUDIENCE_RE = re.compile(r"(소아|아동|유아|초등학생|미취학|어린이|child|infant)", re.I)
# 잠자리 **자체**를 파는 말 — 조식이 묶여 있어도(`쉐어베드 소아 (조식 포함)`) 그 값은 아이의
# 1박 요금이라 `아동 추가 금액` 으로 간다.
CHILD_LODGING_RE = re.compile(
    r"(쉐어\s*베드|쉐어베드|share\s*bed|sharebed|베드\s*셰어|베드셰어|bed\s*share|"
    r"소파\s*베드|소파베드|sofa\s*bed|보트\s*베드|보트베드|"
    r"무료\s*투숙|동반\s*투숙|무료\s*숙박|추가\s*침대\s*없이)", re.I
)
# 잠자리로도, 물건 값의 **단위**로도 읽히는 약한 말 — `조식 소아 (만 6~11세) 1박 1인` 처럼
# 따로 사는 것의 단위면 부가옵션이 맞다. 그래서 이 말만 걸렸을 때는 아래 예외를 먼저 본다.
CHILD_STAY_UNIT_RE = re.compile(r"(1\s*박|숙박)", re.I)
# 따로 사는 것 — 식사 업그레이드·픽업·엑스트라베드는 이름에 아이가 들어가도 부가옵션이다.
ADDON_SEPARATE_GOODS_RE = re.compile(
    r"(조식|중식|석식|점심|저녁|식사|breakfast|meal|"
    r"하프\s*보드|하프보드|half\s*board|풀\s*보드|풀보드|full\s*board|디너|dinner|"
    r"픽업|pick\s*-?\s*up|셔틀|shuttle|엑스트라\s*베드|엑스트라베드|extra\s*bed)", re.I
)

# 갈라디너·컴펄서리 디너·행사 요금 — **특정 날짜에 인당으로 붙는 의무 요금**이다.
# 계약이 "반드시 낸다" 고 하는 돈은 고객이 뺄 수 있는 부가옵션이 아니라 **의무 부과금 하나**다:
# `부과 방식` 정액(성인 단가) · `부과 단위` 인당 · `부과 유형` 의무 · `적용 날짜 (선택)` 그 날짜 ·
# `연령별 단가 · <노출명>` 로 소아·유아 단가. 실제 사례(2026-09-07): 12/24·12/31 컴펄서리 디너가
# 부가옵션으로 깔려 고객이 빼면 호텔이 물리는 돈이 한 푼도 청구되지 않았다. 성인만 부과금으로 두고
# 소아를 부가옵션으로 나눈 것도 같은 구멍이다 — 소아분이 선택 항목이 되어 빠진다.
GALA_NAME_RE = re.compile(r"(갈라\s*디너|갈라디너|gala|컴펄서리|compulsory)", re.I)
# 계약서가 `선택`·`optional` 이라고 못 박은 디너만 부가옵션이다 — 그때는 이름 끝에 이 표시를 붙인다.
GALA_OPTIONAL_MARK = "(선택)"
ADDON_CREATE_TITLE = "부가옵션 만들기"
SURCHARGE_TITLE = "부과금 추가"
# `부과 단위` 가 이것이어야 사람 수만큼 곱해지고 `연령별 단가` 표가 화면에 선다.
PER_PERSON_UNIT = "인당"
# 성인·소아를 부과금 둘로 쪼갠 흔적 — 이름 끝의 `(성인)`.
ADULT_ONLY_SUFFIX_RE = re.compile(r"\(\s*성인\s*\)\s*$")

# 혜택 드로어(화면 사전 §24) — `제공 주기` 체크박스는 `수량` 에 값이 있어야만 화면에 그려진다.
# 실제 사례(2026-09-04): `수량` 을 비운 채 `제공 주기 | 체크` 만 남긴 원고를 러너가 실행하다
# "화면에 없는 칸" 으로 막혔다. 택1 그룹 안에 넣는 후보(`[이 그룹에 혜택 추가]`)도 같은 드로어다.
BENEFIT_CREATE_TITLE = "혜택 추가"
BENEFIT_CANDIDATE_TITLE = "택1 그룹 후보 추가"
QUANTITY_FIELD = "수량"
PROVISION_FREQUENCY_FIELD = "제공 주기"

# 만들기 드로어에만 있는 칸 — `{칸 이름: 그 드로어의 저장 버튼}`.
# 요금제 정본은 만들 때와 고칠 때가 **다른 드로어**다(운영 화면 실측 — 만들기 드로어에만 그려지는 칸이 있다):
# `지금 모든 객실에 배포` 체크박스와 그 묶음 머리 `배포` 는 [정본 만들기] 쪽에만 그려지고,
# 기존 정본을 [편집] 로 열면 그 줄이 아예 없다 — 지시서가 그 줄을 쓰면 담당자가 없는 칸을 찾는다.
# 두 드로어는 저장 버튼으로 갈리므로(만들기 [만들기] · 편집 [저장]) 그 버튼으로 판정한다.
CREATE_ONLY_FIELDS = {"지금 모든 객실에 배포": "만들기"}

# 그 칸을 쓰면 안 되는 **고치기 단계**의 제목. 버튼으로도 갈리지만(위 표), 제목이 이미
# "고치기" 라고 말하는 단계에서는 사람 말로 그대로 돌려주는 편이 고칠 자리를 바로 가리킨다.
CREATE_ONLY_EDIT_TITLES = ("요금제 고치기", "요금제 정본 고치기")

# 룸 사진 카드에는 **저장 버튼이 없다** — 파일 input 이 `hx-trigger="change"` 라 고르는 순간 올라간다
# (운영 화면 실측). 드로어 아래 [저장] 은 룸 폼의 저장이라 사진과 무관하고, 올리는
# 도중에 누르면 드로어가 먼저 닫힐 수 있다. 그래서 이 단계만 마지막 줄이 [사진 추가] 다.
ROOM_PHOTO_TITLE = "룸 사진 올리기"
ROOM_PHOTO_BUTTON = "사진 추가"

# 사진 단계의 제목이 `(N장)` 으로 장수를 약속하면 파일 줄도 그만큼 있어야 한다.
# 제목만 고치고 파일 줄을 안 늘린(또는 그 반대) 지시서가 실제로 나왔다 — 담당자는 제목을 세고
# 올리므로, 어긋나면 몇 장을 올려야 하는지 화면 밖에서 알 길이 없다.
PHOTO_STEP_TITLES = ("대표이미지", "상품상세 이미지", "룸 사진", "오퍼 이미지")
PHOTO_COUNT_RE = re.compile(r"\((\d+)장\)")

# 판매 구간은 **지시서를 만드는 날(오늘)부터**다. 계약(요금표)이 지난 날부터 유효해도 지난 날은
# 팔 수 없으므로, 오퍼 `투숙 시작` 과 `판매일 열기` 의 시작일은 max(계약 시작일, 오늘) 이다.
# 실제 사례(2026-09-07): 2026-01-05~2026-12-31 요금표를 그대로 옮겨 여덟 달 전 날짜를 열었다.
SALE_START_FIELDS = ((OFFER_CREATE_TITLE, "투숙 시작"), ("판매일 열기", "시작일"))
# 오퍼의 예약 창 — `비움` 으로 두면 예약 기간 제한이 없어져 지난 날짜·닫아야 할 날짜까지 열린다.
BOOKING_WINDOW_FIELDS = ("예약 시작", "예약 종료")
SEASON_CREATE_TITLE = "시즌 만들기"
SEASON_END_FIELD = "기간 종료"
# 원고가 맨 앞(첫 단계 앞)에 지닐 수 있는 작성일 — 있으면 이 날이 "오늘" 이다.
GUIDE_DATE_RE = re.compile(r"^\s*(?:작성일|rendered)\s*[:：]\s*(\d{4}-\d{1,2}-\d{1,2})\s*$")
#: 값이 비었다고 보는 표기
BLANK_VALUES = {"", "—", "-", "없음"}


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
                   "heads": {}, "rows": [], "fields": {}, "saves": [], "files": []}
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
            pf = PHOTO_FIELD_RE.match(value)
            if pf:
                cur["files"].append(pf.group("name"))
            continue
        pl = PHOTO_LINE_RE.match(line)
        if pl:
            cur["files"].append(pl.group("name"))
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


def guide_date(lines, today=None):
    """지시서를 만드는 날 — 원고 맨 앞의 `작성일: YYYY-MM-DD` 가 있으면 그 날, 없으면 검사하는 날."""
    for line in lines:
        if line.startswith("## "):
            break
        m = GUIDE_DATE_RE.match(line)
        if m:
            day = _date(m.group(1))
            if day:
                return day
    return today or datetime.date.today()


def find_past_sale_starts(steps, today):
    """오퍼 `투숙 시작` 과 `판매일 열기` 시작일이 오늘보다 앞이면 오류.

    계약(요금표)이 지난 날부터 유효해도 **지난 날은 팔 수 없다** — 시작일은
    max(계약 시작일, 오늘) 이고, 종료일만 계약이 값을 주는 마지막 날이다.
    """
    problems = []
    for step in steps:
        for title, field in SALE_START_FIELDS:
            if not step["title"].startswith(title):
                continue
            start = _date_field(step["fields"], field)
            if start and start < today:
                problems.append(
                    f"{step['num']}단계: {field} {start.isoformat()} 이 "
                    f"오늘({today.isoformat()})보다 앞이다 — 판매 구간은 오늘부터"
                )
    return problems


def find_blank_booking_window(steps):
    """오퍼의 `예약 시작`·`예약 종료` 를 `비움` 으로 두면 경고.

    비우면 예약 기간 제한이 없어진다(화면 안내 그대로) — 예약 시작은 오늘 00:00,
    예약 종료는 계약서의 예약 마감(없으면 판매 종료일 23:59)을 적는다.
    """
    problems = []
    for step in steps:
        if not step["title"].startswith(OFFER_CREATE_TITLE):
            continue
        for field in BOOKING_WINDOW_FIELDS:
            raw = step["fields"].get(field)
            if raw is None:
                continue  # 줄 자체가 없는 것은 사전 검사가 본다
            value = strip_select(raw).strip()
            if value.startswith("비움") or value in BLANK_VALUES:
                problems.append(
                    f"{step['num']}단계: `{field}` 가 비었다 — 예약 시작은 오늘 00:00, "
                    "예약 종료는 계약서의 예약 마감(없으면 판매 종료일 23:59)"
                )
    return problems


def find_past_seasons(steps, today):
    """`시즌 만들기` 의 기간 종료가 오늘보다 앞이면 오류 — 판매 구간 밖 시즌은 만들지 않는다."""
    problems = []
    for step in steps:
        if not step["title"].startswith(SEASON_CREATE_TITLE):
            continue
        end = _date_field(step["fields"], SEASON_END_FIELD)
        if end is None:
            days = season_dates(step)
            end = max(days) if days else None
        if end and end < today:
            name = step_subject(step["title"]) or step["fields"].get("시즌명") or ""
            problems.append(
                f"{step['num']}단계: 시즌 `{name}` 의 {SEASON_END_FIELD} {end.isoformat()} 가 "
                f"오늘({today.isoformat()})보다 앞이다 — 판매 구간 밖 시즌은 만들지 않는다"
            )
    return problems


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


def find_hangul_room_names(steps):
    """`룸 만들기` 의 `룸 이름` 에 한글이 있으면 경고 — 룸 이름은 계약서 원어 그대로다.

    ERP 객실 목록과 계약서 요금표는 이름으로 맞춘다. 한글로 옮겨 적으면 요금표의 어느 줄이
    어느 룸인지 대조가 끊긴다. 고객이 보는 한글 이름은 판매 연결 일괄 드로어의
    `오퍼별 표시명` 이 따로 가진다. 계약서 자체가 한글이면 그 원어가 한글이니 그대로 두고
    `changes.md` 에 적는다 — 그래서 오류가 아니라 경고다.
    """
    problems = []
    for step in steps:
        if not step["title"].startswith(ROOM_CREATE_TITLE):
            continue
        name = (step["fields"].get(ROOM_NAME_FIELD) or "").strip()
        if name and HANGUL_RE.search(name):
            problems.append(
                f"{step['num']}단계: 룸 이름 {name} 에 한글이 있다 — "
                "룸 이름은 계약서 원어, 한글은 오퍼별 표시명에"
            )
    return problems


#: 나이 칸의 이름은 2026-09-08 에 `최소 연령` → `최소 연령 (만 나이)` 로 바뀌었다
#: (`OfferAgeBandForm.__init__` — 세는 나이로 받아 적으면 한 밴드 위로 저장되고 그 한 칸이
#: 소아가와 성인가를 가른다). **두 표기를 다 읽는다** — 옛 원고를 이사시키지 않으면서 새 원고를
#: 받으려면 여기가 유일한 문이다. 이름 하나만 보던 동안에는 새 라벨을 쓴 원고에서 나이 겹침
#: 검사가 **조용히 건너뛰었다**(검출 0건). 화면이 거부하는 원고가 검사를 통과하는 것이라,
#: 담당자는 그 단계에 가서야 막힌다.
AGE_MIN_LABELS = ("최소 연령 (만 나이)", "최소 연령", "최소연령")
AGE_MAX_LABELS = ("최대 연령 (만 나이)", "최대 연령", "최대연령")


def _age_value(step, names):
    """`최소 연령 (만 나이)` · `최대 연령 (만 나이)` 칸의 숫자. 비었거나 숫자가 아니면 None."""
    for name in names:
        raw = (step["fields"].get(name) or "").strip()
        if not raw:
            continue
        try:
            return decimal.Decimal(raw.replace(",", ""))
        except (decimal.InvalidOperation, ValueError):
            return None
    return None


def find_age_band_overlaps(steps):
    """같은 오퍼(카드)의 연령 구간이 한 살이라도 겹치면 오류 — **양끝 포함**이다.

    화면이 거부하는 조합이라(`age_band.ranges_overlap`) 지시서에 남으면 담당자가 그 단계에서
    막힌다. 흔한 실수가 "만 12세 미만" 을 `0~11.99` 로 적으면서 그 아래 유아 구간(`0~5.99`)을
    함께 두는 것이다 — 아래 구간 위에서 시작해야 한다(`6~11.99`).
    """
    problems = []
    by_card = {}
    for step in steps:
        if not step["title"].startswith(AGE_BAND_TITLE):
            continue
        low, high = _age_value(step, AGE_MIN_LABELS), _age_value(step, AGE_MAX_LABELS)
        if low is None or high is None:
            continue
        by_card.setdefault(card_name(step) or "", []).append((step, low, high))
    for rows in by_card.values():
        for index, (step, low, high) in enumerate(rows):
            for other, other_low, other_high in rows[:index]:
                if low <= other_high and other_low <= high:
                    problems.append(
                        f"{step['num']}단계: 연령 구간이 {other['num']}단계와 겹친다 — "
                        f"만 {low}~{high}세 와 만 {other_low}~{other_high}세 "
                        "(양끝이 포함이라 경계가 맞닿기만 해도 겹친다 — 아래 구간 위에서 시작한다)"
                    )
                    break
    return problems


def find_age_band_order(steps):
    """`연령 구간 만들기` 는 첫 `오퍼 만들기` 뒤 · `연령별 단가` 와 `시즌 가격 채우기` 보다 앞이다.

    구간은 오퍼의 자식이라(오퍼 카드에서 [연령 구간 추가]) 오퍼가 없으면 만들 자리가 없고,
    부과금 드로어의 `연령별 단가` 표는 **이미 만들어 둔 구간만** 칸으로 보여 준다 — 순서가
    뒤집히면 담당자가 그 칸을 찾지 못한다.

    2026-09-08 부로 `시즌 가격 채우기` 보다도 앞이다 — 유료 구간이 하나도 없으면 그 드로어에
    `아동 추가 금액 — <노출명>` 칸이 아예 서지 않아, 아이 1박 요금을 적을 자리가 사라진다(§D-2).
    """
    problems = []
    first_offer = next(
        (step["num"] for step in steps if step["title"].startswith(OFFER_CREATE_TITLE)), None
    )
    band_steps = [step for step in steps if step["title"].startswith(AGE_BAND_TITLE)]
    for step in band_steps:
        if first_offer is None or step["num"] < first_offer:
            problems.append(
                f"{step['num']}단계: `{step['title']}` 가 `{OFFER_CREATE_TITLE}` 보다 앞이다 — "
                "연령 구간은 오퍼 카드에서 만든다(오퍼를 먼저 만든다)"
            )
    first_band = band_steps[0]["num"] if band_steps else None
    for step in steps:
        uses_rate = any(
            name == AGE_RATE_FIELD or name.startswith(f"{AGE_RATE_FIELD} · ") for name in step["fields"]
        )
        if not uses_rate:
            continue
        if first_band is None:
            problems.append(
                f"{step['num']}단계: `{AGE_RATE_FIELD}` 줄이 있는데 `{AGE_BAND_TITLE}` 단계가 없다 — "
                "연령 구간을 먼저 만들어야 그 칸이 화면에 생긴다"
            )
        elif step["num"] < first_band:
            problems.append(
                f"{step['num']}단계: `{AGE_RATE_FIELD}` 줄이 `{AGE_BAND_TITLE}` 단계보다 앞이다 — "
                "연령 구간을 먼저 만들어야 그 칸이 화면에 생긴다"
            )
    fills = _season_fill_steps(steps)
    for step in band_steps:
        earlier = [
            fill for fill in _fills_of_offer(fills, card_name(step) or "")
            if fill["num"] < step["num"]
        ]
        if not earlier:
            continue
        problems.append(
            f"{step['num']}단계: `{AGE_BAND_TITLE}` 가 {earlier[0]['num']}단계 "
            f"`{SEASON_FILL_TITLE}` 보다 뒤다 — 연령 구간을 먼저 만들어야 그 드로어에 "
            f"`{CHILD_EXTRA_FIELD}` 칸이 선다"
        )
    return problems


def _fold(text):
    """칸 이름·노출명 비교용 꼴 — 빈칸을 접고 대소문자를 무시한다."""
    return re.sub(r"\s+", "", text or "").casefold()


def _blank(value):
    """`비움` · `—` · 빈 칸처럼 값이 없다고 보는 표기인가."""
    text = (value or "").strip()
    return not text or text in BLANK_VALUES or text.startswith("비움")


def _labeled_value(step, names):
    """`인원 조합(선택)` 처럼 `(선택)` 이 붙거나 안 붙거나 하는 칸의 값(없으면 None)."""
    for name in names:
        if name in step["fields"]:
            return step["fields"][name]
    return None


def _season_fill_steps(steps):
    """`시즌 가격 채우기` 단계를 `(단계, 오퍼 카드 or None)` 로 모은다.

    가격 채우기 단계의 `카드:` 는 **시즌 이름**이라(`카드: Regular`) 오퍼는 `시즌 만들기`
    단계를 거쳐 찾는다. 시즌 이름이 겹치거나 그 단계가 없으면 오퍼를 알 수 없어 None 이다.
    """
    seasons = season_index(steps)
    fills = []
    for step in steps:
        if not step["title"].startswith(SEASON_FILL_TITLE):
            continue
        key = fill_season(step, seasons)
        fills.append((step, key[0] if key else None))
    return fills


def _fills_of_offer(fills, offer):
    """그 오퍼의 가격 채우기 단계 — 오퍼를 못 읽은 단계도 함께 본다(어느 오퍼인지 모른다)."""
    return [step for step, own in fills if own is None or own == offer]


def _child_extra_names(step):
    """그 단계의 `아동 추가 금액 — <노출명>` 줄에서 노출명(비교용 꼴)을 모은다."""
    names = set()
    for name, _ in step["rows"]:
        m = CHILD_EXTRA_LABEL_RE.match(name.strip())
        if m and m.group("name"):
            names.add(_fold(m.group("name")))
    return names


def find_child_extra_missing(steps):
    """유료 연령 구간마다 `시즌 가격 채우기` 에 `아동 추가 금액 — <노출명>` 줄이 있어야 한다.

    `요금 기준 유형` 이 `무료` 가 **아닌** 구간(정액 · 성인 요금의 % · 타 밴드 요금과 동일)은
    시즌 채우기 드로어에 아동 금액 칸을 하나 세우고, 그 칸이 성인 좌표 옆에 아동 좌표를 함께
    깐다(`A2` → `A2C1_CHD`). 줄이 빠지면 아이 1박 요금이 어디에도 실리지 않는다 — 그 돈을
    부가옵션으로 옮겨 적는 길은 2026-09-08 부로 막혔다(§D-1).

    가격을 셀로 손입력하는 원고(=`시즌 가격 채우기` 단계가 아예 없다)와 `요금 기준 유형` 줄이
    없어 유료인지 알 수 없는 구간은 건너뛴다.
    """
    fills = _season_fill_steps(steps)
    if not fills:
        return []
    problems = []
    for step in steps:
        if not step["title"].startswith(AGE_BAND_TITLE):
            continue
        kind = strip_select(step["fields"].get(AGE_BAND_TYPE_FIELD) or "")
        if _blank(kind) or kind.startswith(AGE_BAND_FREE_TYPE):
            continue
        label = (step["fields"].get(AGE_BAND_NAME_FIELD)
                 or step["fields"].get(AGE_BAND_CODE_FIELD) or "")
        if _blank(label):
            continue
        label = label.strip()
        mine = _fills_of_offer(fills, card_name(step) or "")
        if not mine:
            continue
        if any(_fold(label) in _child_extra_names(fill) for fill in mine):
            continue
        problems.append(
            f"{step['num']}단계: 유료 연령 구간 `{label}` 의 "
            f"`{CHILD_EXTRA_FIELD} \u2014 {label}` 줄이 `{SEASON_FILL_TITLE}` 에 없다 — "
            "아이 1박 요금은 그 칸 한 곳에만 둔다"
        )
    return problems


def find_child_extra_without_occupancy(steps):
    """`아동 추가 금액` 에 값을 적었는데 `인원 조합(선택)` 이 비었으면 오류 — 화면이 저장을 막는다.

    아동 금액은 **성인 좌표 위에 얹히는** 값이라(`A2` → `A2C1_CHD` = A2 + 그 금액) 좌표가
    인원 무관 단일가 한 곳(`""`)이면 얹힐 데가 없다. `SeasonPriceFillForm.clean` 이 그 조합을
    거부한다(ERP 실측): "아동 추가 금액은 성인 좌표를 적은 전개에서만 쓰입니다 — A2 처럼 성인
    수를 적거나 금액을 비워주세요". `인원 조합별 조정` · `기준 요금제 대비 조정` 이 막히는 것과
    같은 판단이다.

    `성인 요금의 %` 구간의 `자동 입력됨 · 그대로 둠` 줄도 그 목록에 실리므로 예외가 아니다 —
    그 줄만 있어도 인원 조합을 적어야 저장된다. 값을 `비움` 으로 둔 아동 줄은 그 구간의 셀을
    아예 만들지 않으므로(§B-4) 걸리지 않는다.
    """
    problems = []
    for step in steps:
        if not step["title"].startswith(SEASON_FILL_TITLE):
            continue
        filled = any(
            CHILD_EXTRA_LABEL_RE.match(name.strip()) and not _blank(value)
            for name, value in step["rows"]
        )
        if not filled or not _blank(_labeled_value(step, OCCUPANCY_KEYS_FIELDS)):
            continue
        problems.append(
            f"{step['num']}단계: {CHILD_EXTRA_FIELD}을 적었는데 인원 조합이 비어 있다 — "
            "아동 금액은 성인 좌표 위에 얹히므로 A2 처럼 성인 수를 적어야 저장된다"
        )
    return problems


def find_child_lodging_addon(steps):
    """`부가옵션 만들기` 이름이 아이의 **잠자리**를 팔면 오류(§D-1, 2026-09-08).

    아이가 방에서 자는 1박 요금은 `시즌 가격 채우기` 의 `아동 추가 금액 — <노출명>` 한 곳에만
    둔다 — 부가옵션으로 만들면 고객이 빼 버릴 수 있고, 인원 선택기에도 그 아이가 서지 않는다.
    식사 업그레이드·픽업·엑스트라베드는 **따로 사는 것**이라 이름에 아이가 들어가도 부가옵션이
    맞다(`하프보드 소아` · `조식 소아 (만 6~11세) 1박 1인`) — 그 예외를 먼저 본다. 다만
    쉐어베드·소파베드처럼 **잠자리 자체**를 파는 이름은 조식이 묶여 있어도(`쉐어베드 소아
    (조식 포함)`) 파는 것이 아이의 1박이라 예외가 아니다.
    """
    problems = []
    for step in steps:
        if not step["title"].startswith(ADDON_CREATE_TITLE):
            continue
        name = (step["fields"].get("이름") or "").strip()
        if not name or not CHILD_ADDON_AUDIENCE_RE.search(name):
            continue
        lodging = bool(CHILD_LODGING_RE.search(name))
        unit_only = bool(CHILD_STAY_UNIT_RE.search(name)) and not ADDON_SEPARATE_GOODS_RE.search(name)
        if not (lodging or unit_only):
            continue
        problems.append(
            f"{step['num']}단계: 부가옵션 `{name}` 은 아이의 1박 요금이다 — "
            f"부가옵션이 아니라 `{SEASON_FILL_TITLE}` 의 `{CHILD_EXTRA_FIELD}` 칸이다"
        )
    return problems


def find_band_code_format(steps):
    """`밴드 코드` 가 영대문자·숫자 2~8자가 아니면 오류 — 그 코드가 좌표에 그대로 실린다.

    소문자로 쳐도 서버가 대문자로 굳히므로 소문자는 받아 준다. 밑줄은 좌표 조각 구분자라
    (`A2C1_CHD`) 코드 안에 들어가면 좌표가 갈라지고, 한글·공백·기호·1자·9자 이상도 막힌다.
    """
    problems = []
    for step in steps:
        if not step["title"].startswith(AGE_BAND_TITLE):
            continue
        code = (step["fields"].get(AGE_BAND_CODE_FIELD) or "").strip()
        if _blank(code) or BAND_CODE_RE.match(code):
            continue
        problems.append(
            f"{step['num']}단계: 밴드 코드 `{code}` 는 쓸 수 없다 — "
            "영대문자·숫자 2~8자다(CHD·INF·TEEN · 밑줄은 좌표 조각 구분자라 못 쓴다)"
        )
    return problems


def find_occupancy_key_legacy(steps):
    """`인원 조합(선택)`·`인원 조합별 조정(선택)` 의 좌표가 A-형이 아니면 오류.

    옛 숫자 키(`2,3` · `3:+14`)도 서버가 받아 `A2,A3` 로 저장하지만, 같은 좌표가 화면·요금표·
    엔진 로그에서 A-형으로 다시 나온다 — 지시서와 화면이 다른 글자를 쓰면 대조가 끊긴다.
    아동을 더한 좌표는 밴드 코드까지 적는다(`A2C1_CHD` · 둘째 구간부터 `_C1_TEEN`). `비움` 은 통과.
    """
    problems = []
    for step in steps:
        for names, what, example, with_amount in (
            (OCCUPANCY_KEYS_FIELDS, "인원 조합", "A2,A3", False),
            (OCCUPANCY_ADJUST_FIELDS, "인원 조합별 조정", "A3:+14,A4:+26", True),
        ):
            value = _labeled_value(step, names)
            if value is None or _blank(value):
                continue
            text = str(value).strip()
            numeric, unread = [], []
            for part in text.split(","):
                part = part.strip()
                if not part:
                    continue
                key = part.split(":", 1)[0].strip() if with_amount else part
                if BARE_NUMBER_RE.match(key):
                    numeric.append(key)
                elif not OCCUPANCY_KEY_RE.match(key):
                    unread.append(key)
            if numeric:
                problems.append(
                    f"{step['num']}단계: {what} `{text}` 은 옛 숫자 표기다 — "
                    f"{example} 처럼 A-형 좌표로 적는다(아이를 더하면 A2C1_CHD)"
                )
            elif unread:
                problems.append(
                    f"{step['num']}단계: {what} 의 좌표 `{', '.join(unread)}` 를 읽지 못한다 — "
                    f"{example} 처럼 A-형으로 적는다(성인 수 A2 뒤에 아동 조각 C1_CHD)"
                )
    return problems


def find_los_prices_format(steps):
    """`박수별 단가(선택)` 는 `박수:1박 단가` 쉼표 목록이다 — 부호·1박 이하·중복은 오류.

    차액이 아니라 **단가**라 부호를 붙이지 않고(`3:+100` 은 화면이 거부한다), 1박 단가는 위
    `판매 단가(공급 통화)` 칸이라 박수는 2 이상이다. 층 하나가 셀 수를 통째로 곱하므로 같은
    박수를 두 번 적지 않는다. `비움` 은 통과.
    """
    problems = []
    for step in steps:
        value = _labeled_value(step, LOS_PRICES_FIELDS)
        if value is None or _blank(value):
            continue
        text = str(value).strip()
        seen, message = set(), None
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            m = LOS_ENTRY_RE.match(part)
            if not m:
                message = (
                    f"{step['num']}단계: 박수별 단가 `{text}` 를 읽지 못한다 — "
                    "3:100,5:90 처럼 `박수:1박 단가` 로 적는다"
                    "(차액이 아니라 단가라 부호를 붙이지 않는다)"
                )
                break
            nights = int(m.group("nights"))
            if nights <= 1:
                message = (
                    f"{step['num']}단계: 박수별 단가 `{text}` 의 박수가 {nights} 다 — "
                    "박수는 2 이상이다(1박 단가는 위 `판매 단가(공급 통화)` 칸이다)"
                )
                break
            if nights in seen:
                message = (
                    f"{step['num']}단계: 박수별 단가 `{text}` 에 {nights}박이 두 번 있다 — "
                    "박수마다 한 번만 적는다"
                )
                break
            seen.add(nights)
        if message:
            problems.append(message)
    return problems


def find_audience_only_names(steps):
    """`부가옵션 만들기` · `부과금 추가` 의 `이름` 이 **대상만** 적혀 있으면 오류.

    `소아 (만6~11세)` 처럼 파는 물건이 빠진 이름은 고객 화면에서 "아이를 따로 산다" 로 읽힌다.
    하프보드 소아 식사면 `하프보드 소아 (만6~11세)` 처럼 **무엇을 파는지**를 앞에 적는다.
    (방에서 자는 아이 자체는 부가옵션이 아니라 `연령 구간` 이고, 그 아이의 1박 요금은
    `시즌 가격 채우기` 의 `아동 추가 금액 — <노출명>` 이다 — `find_child_lodging_addon`.)
    """
    problems = []
    for step in steps:
        if not any(step["title"].startswith(t) for t in ADDON_STEP_TITLES):
            continue
        name = (step["fields"].get("이름") or "").strip()
        if name and AUDIENCE_ONLY_NAME_RE.match(name):
            problems.append(
                f"{step['num']}단계: 부가옵션 이름이 대상만 적혀 있다({name}) — "
                "무엇을 파는지 앞에 적는다(예: 하프보드 소아)"
            )
    return problems


def find_extra_bed_optional_rules(steps):
    """엑스트라베드 부가옵션의 `의무 규칙` 이 `의무 아님` 이면 경고.

    계약서가 "기준 인원 외 성인 추가 시 엑스트라베드 추가 필수" 라고 하면 그 침대는 고객이
    뺄 수 없다 — `기준 성인 초과 시 의무 (엑스트라베드)` 로 둬야 세 번째 성인이 침대 없이
    들어가지 않는다. 계약서가 정말 선택으로 파는 침대도 있으므로 경고로만 알린다.
    """
    problems = []
    for step in steps:
        if not step["title"].startswith(ADDON_CREATE_TITLE):
            continue
        name = (step["fields"].get("이름") or "").strip()
        if not EXTRA_BED_NAME_RE.search(name):
            continue
        rule = strip_select(step["fields"].get(ADDON_RULE_FIELD) or "")
        if rule.startswith(ADDON_RULE_OPTIONAL):
            problems.append(
                f"{step['num']}단계: 엑스트라베드 의무 규칙이 `{ADDON_RULE_OPTIONAL}` — "
                f'계약서에 "추가 시 필수" 문장이 있으면 `{ADDON_RULE_OVER_ADULT}`'
            )
    return problems


def find_child_policy_without_age_band(steps):
    """아이가 보이는데 `연령 구간 만들기` 단계가 하나도 없으면 경고. 두 가지를 함께 본다.

    - 부가옵션·혜택 글에 "정원 내 소아·유아 무료 투숙(쉐어베드)" 처럼 **방에서 잔다**는 말이 있다
    - 부가옵션 `이름` 이 아이를 대상으로 한다(`하프보드 소아`) — 파는 것이 식사라도 그 아이를
      인원으로 고를 수 없으면 아무도 그 부가옵션을 살 수 없다

    아이는 `연령 구간` 으로 넣어야 고객 화면 인원 선택기에 소아·유아가 서고, 방에서 자는 아이의
    1박 요금은 그 다음 `시즌 가격 채우기` 의 `아동 추가 금액 — <노출명>` 이 정한다(§D-1).
    한 단계에서 둘 다 걸려도 한 번만 알린다.
    """
    if any(step["title"].startswith(AGE_BAND_TITLE) for step in steps):
        return []
    problems = []
    for step in steps:
        if not any(kind in step["title"] for kind in CHILD_POLICY_STEP_TITLES):
            continue
        text = " ".join([step["title"]] + [str(v) for v in step["fields"].values()])
        name = (step["fields"].get("이름") or "").strip()
        sleeps = bool(CHILD_AUDIENCE_RE.search(text) and CHILD_STAY_RE.search(text))
        child_named = bool(
            step["title"].startswith(ADDON_CREATE_TITLE) and CHILD_AUDIENCE_RE.search(name)
        )
        if not (sleeps or child_named):
            continue
        problems.append(
            f"{step['num']}단계: 아동 정책이 보이는데 연령 구간 단계가 없다 — "
            "계약서의 아동 정책은 연령 구간으로 넣는다"
        )
    return problems


def _is_gala(step):
    """단계 제목·`이름` 칸에 갈라디너·컴펄서리 디너로 읽히는 말이 있는가."""
    name = (step["fields"].get("이름") or "").strip()
    return bool(GALA_NAME_RE.search(f"{step['title']} {name}"))


def find_gala_addons(steps):
    """갈라디너를 `부가옵션 만들기` 로 넣으면 오류 — 고객이 빼 버릴 수 있다.

    계약이 물리는 컴펄서리 디너는 **의무 부과금 하나**다(인당·정액·적용 날짜·연령별 단가).
    부가옵션은 고객이 고를 때만 붙으므로 그 돈이 청구되지 않는다. 계약서가 `선택`·`optional`
    이라고 못 박은 디너만 부가옵션이고, 그때는 이름 끝에 `(선택)` 을 붙여 그 사실을 남긴다.
    """
    problems = []
    for step in steps:
        if not step["title"].startswith(ADDON_CREATE_TITLE) or not _is_gala(step):
            continue
        name = (step["fields"].get("이름") or "").strip()
        if GALA_OPTIONAL_MARK in name or GALA_OPTIONAL_MARK in step["title"]:
            continue
        problems.append(
            f"{step['num']}단계: 갈라디너는 의무 부과금(인당·정액·적용 날짜·연령별 단가)로 넣는다 — "
            "계약서가 선택이라고 명시한 경우만 부가옵션이며 그때는 이름에 (선택) 을 붙인다"
        )
    return problems


def find_gala_surcharge_gaps(steps):
    """갈라디너 부과금이 `인당` 이 아니거나 `연령별 단가` 줄이 없으면 오류.

    행사비는 사람 수만큼 붙는 돈이라 `부과 단위` 가 `인당` 이어야 하고, 그 오퍼에 연령 구간이
    있으면 소아·유아 단가는 **그 부과금 안의** `연령별 단가 · <노출명>` 줄로 적는다. 소아분을
    부가옵션으로 따로 만들면 그쪽만 빠진다(성인만 내는 행사면 유아·소아 줄에 `0`).
    """
    problems = []
    bands = {}
    for step in steps:
        if step["title"].startswith(AGE_BAND_TITLE):
            bands[card_name(step) or ""] = bands.get(card_name(step) or "", 0) + 1
    for step in steps:
        if not step["title"].startswith(SURCHARGE_TITLE) or not _is_gala(step):
            continue
        unit = strip_select(step["fields"].get("부과 단위") or "")
        if unit != PER_PERSON_UNIT:
            problems.append(
                f"{step['num']}단계: 갈라디너 부과금의 `부과 단위` 가 `{PER_PERSON_UNIT}` 이 아니다"
                f"({unit or '비움'}) — 인당·정액·적용 날짜로 넣어야 사람 수만큼 붙고 "
                "`연령별 단가` 칸이 화면에 선다"
            )
            continue
        has_rate = any(
            name == AGE_RATE_FIELD or name.startswith(f"{AGE_RATE_FIELD} · ") for name in step["fields"]
        )
        card = card_name(step) or ""
        count = bands.get(card, 0) if card else sum(bands.values())
        if not has_rate and count:
            problems.append(
                f"{step['num']}단계: 갈라디너 부과금에 연령별 단가 줄이 없다 — "
                "소아·유아 단가를 연령별 단가로 넣는다(성인만이면 유아·소아 0)"
            )
    return problems


def find_adult_only_charge_names(steps):
    """부과금 이름이 `(성인)` 으로 끝나면 경고 — 성인·소아를 둘로 쪼갠 흔적이다.

    한 부과금의 `정액 금액` 이 성인가이고 `연령별 단가 · <노출명>` 이 아이 단가다. 이름으로
    성인을 한정하면 아이 몫이 다른 곳(대개 부가옵션)에 남아 고객이 뺄 수 있게 된다.
    """
    problems = []
    for step in steps:
        if not step["title"].startswith(SURCHARGE_TITLE):
            continue
        name = (step["fields"].get("이름") or "").strip()
        if name and ADULT_ONLY_SUFFIX_RE.search(name):
            problems.append(
                f"{step['num']}단계: 부과금 이름이 `(성인)` 으로 끝난다({name}) — "
                "성인·소아를 부과금 하나의 연령별 단가로 합친다"
            )
    return problems


def _field_value(step, base):
    """`<base>` 또는 `<base> · <체크박스 문구>` 로 적힌 값을 하나 찾는다(없으면 None).

    체크박스 칸은 지시서에서 `제공 주기 · 1박당 제공 (비우면 체류당)` 처럼 사전의
    `checkbox_text` 를 붙여 쓸 수 있다(§load_dictionary) — 둘 다 같은 칸으로 본다.
    """
    for name, value in step["fields"].items():
        if name == base or name.startswith(f"{base} · "):
            return value
    return None


def find_benefit_frequency_without_quantity(steps):
    """혜택의 `수량` 이 비었는데 `제공 주기` 를 체크했으면 오류.

    화면 사전 §24 대로 `제공 주기` 체크박스는 `수량` 에 값이 있어야만 화면에 그려진다 —
    수량을 비운 채 체크만 원고에 남기면 담당자(또는 러너)가 화면에서 그 칸을 찾지 못한다.
    """
    problems = []
    for step in steps:
        if not (step["title"].startswith(BENEFIT_CREATE_TITLE)
                or step["title"].startswith(BENEFIT_CANDIDATE_TITLE)):
            continue
        frequency = _field_value(step, PROVISION_FREQUENCY_FIELD)
        if (frequency or "").strip() != "체크":
            continue
        quantity = (_field_value(step, QUANTITY_FIELD) or "").strip()
        if quantity and quantity != "비움":
            continue
        problems.append(
            f"{step['num']}단계: 수량이 비어 있는데 `제공 주기` 를 체크했다 — "
            "수량을 채우거나 제공 주기를 해제한다"
        )
    return problems


def find_photo_count_gaps(steps):
    """사진 단계 제목의 `(N장)` 과 그 단계의 파일 줄 수가 다르면 오류.

    파일 줄은 두 모양을 함께 센다 — 목록 줄(`- hotel_02.jpg`, 출처가 붙은 것 포함)과
    표 칸의 파일 값(`| 오퍼 이미지 | 파일: offer_hero.jpg |`).
    제목에 장수가 없는 단계(`룸 사진 올리기 (1번째, Single)`)는 약속한 것이 없으므로 보지 않는다.
    """
    problems = []
    for step in steps:
        title = step["title"]
        if not any(kind in title for kind in PHOTO_STEP_TITLES):
            continue
        m = PHOTO_COUNT_RE.search(title)
        if not m:
            continue
        want, have = int(m.group(1)), len(step["files"])
        if want != have:
            problems.append(f"{step['num']}단계: 제목은 {want}장인데 파일 줄은 {have}개다")
    return problems


def find_room_photo_saves(steps):
    """`룸 사진 올리기` 단계가 [저장] 으로 끝나면 오류 — 그 카드에는 저장 버튼이 없다.

    「대표이미지」·「상품상세 이미지」는 대상이 아니다. 그쪽은 「기본정보」 탭(상품 공통 화면)이라
    탭 오른쪽 위 [저장] 이 진짜 저장이다.
    """
    problems = []
    for step in steps:
        if not step["title"].startswith(ROOM_PHOTO_TITLE):
            continue
        saves = step["saves"]
        last = saves[-1] if saves else ""
        if last == ROOM_PHOTO_BUTTON:
            continue
        problems.append(
            f"{step['num']}단계: `{ROOM_PHOTO_TITLE}` 는 `→ [{ROOM_PHOTO_BUTTON}]` 로 끝낸다 — "
            f"룸 사진 카드에는 저장 버튼이 없고 파일을 고르면 바로 올라간다"
            f"(지금은 [{last or '?'}])"
        )
    return problems


def find_create_only_fields(steps):
    """만들기 드로어에만 있는 칸이 편집 단계에 적혀 있으면 오류.

    `지금 모든 객실에 배포` 가 그 첫 사례다 — [정본 만들기] 드로어에만 있는 체크박스라,
    `요금제 고치기` 처럼 [저장] 으로 끝나는 단계에 적으면 화면에 없는 칸이 된다.
    """
    problems = []
    for step in steps:
        saves = step["saves"]
        last = saves[-1] if saves else ""
        is_edit_step = step["title"].startswith(CREATE_ONLY_EDIT_TITLES)
        for name in step["fields"]:
            want = CREATE_ONLY_FIELDS.get(norm_field(name))
            if want is None:
                continue
            if is_edit_step:
                problems.append(
                    f"{step['num']}단계: `{name}` 는 새로 만들 때만 있는 칸이다 — 고치기 표에서 뺀다"
                )
                continue
            if last == want:
                continue
            problems.append(
                f"{step['num']}단계: `{name}` 칸은 [{want}] 로 끝나는 만들기 드로어에만 있다 — "
                f"이 단계는 [{last or '?'}] 로 끝난다(그 줄을 뺀다)"
            )
    return problems


def find_campaign_uses(steps):
    """캠페인은 화면에서 없어졌다 — 단계도, 어느 표의 `캠페인` 줄도 두지 않는다."""
    problems = []
    for step in steps:
        if step["title"].startswith(CAMPAIGN_TITLE):
            problems.append(
                f"{step['num']}단계: 캠페인 단계는 만들지 않는다(오퍼 이미지로 대신)"
            )
            continue
        if CAMPAIGN_FIELD in step["fields"]:
            problems.append(
                f"{step['num']}단계: `{CAMPAIGN_FIELD}` 칸은 화면에서 없어졌다 — 줄을 뺀다"
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


def find_cancel_policy_save_gaps(steps):
    """`취소정책 만들기` 단계는 `→ [추가]` 로 끝나야 한다.

    새 정책을 만드는 드로어의 버튼 문구가 [추가] 다(`references/screen-dictionary.md` §취소정책).
    [저장] 은 **이미 있는 정책을 고칠 때**의 버튼이라, 만들기 단계에 적으면 담당자가 없는 버튼을 찾는다.
    """
    problems = []
    for step in steps:
        if not step["title"].startswith(CANCEL_POLICY_CREATE_TITLE):
            continue
        saves = step["saves"]
        if saves and saves[-1] != CANCEL_POLICY_CREATE_BUTTON:
            problems.append(
                f"{step['num']}단계: `{CANCEL_POLICY_CREATE_TITLE}` 의 마지막 줄은 "
                f"`→ [{CANCEL_POLICY_CREATE_BUTTON}]` 다 — [저장] 은 이미 있는 정책을 고칠 때의 버튼이다"
                f" (지금 [{saves[-1]}])"
            )
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

# 반복 행 이름의 **정본 형식**은 `<칸 이름> <N> · <하위 칸>` 이다 — 낱말 사이는 홑 빈칸 하나,
# 가운뎃점은 U+00B7 을 빈칸으로 감싼 ` · ` 다. 지시서를 화면에서 실행하는 도우미가 이 형태로
# 행을 찾으므로(빈칸 없는 `1·`, 전각 가운뎃점 `・`, 홑화살괄호 변종은 못 찾는다) 검사기도
# 이 형태만 받는다. 사전과는 `<하위 칸>`(열 이름)으로 대조한다.
REPEAT_PREFIX_RE = re.compile(r"^.+? \d+ \u00b7 ")
# 정본에서 벗어난 반복 행을 잡는 그물 — 가운뎃점 변종·빈칸 빠짐·겹빈칸을 모두 받아 본 뒤
# 위 정본과 견줘 어긋난 것만 오류로 돌려준다.
REPEAT_LOOSE_RE = re.compile(r"^.+?\s*\d+\s*[\u00b7\u30fb\u2027\u2219]\s*.+$")

# 사전은 행마다 늘어나는 칸을 자리표시 라벨 한 줄로 담는다(`연령별 단가 · 〈연령 구간 노출명〉`).
# 지시서는 그 자리에 실제 이름을 넣어 쓰므로(`연령별 단가 · 소아`) 허용 집합에는 자리표시를
# 뗀 bare 이름(`연령별 단가`)도 함께 넣어 둔다 — `strip_row_suffix()` 가 줄인 형태와 만난다.
PLACEHOLDER_SUFFIX_RE = re.compile(r"\s*[\u00b7\u2014\u2013]\s*\u3008[^\u3009]*\u3009\s*$")

# 상품 공통 화면의 칸이라 화면 사전이 일부러 담지 않는 이름 — 대조에서 통과시킨다
DICT_EXEMPT = {"상품명"}

# `체크` / `해제` 는 **체크박스 한 칸**의 값이다. `다중 체크`·`선택`·`라디오` 처럼 목록에서 고르는
# 칸은 고른 것을 `선택: …` 으로 적고, 아무것도 안 고르면 `비움` 이다 — 그 칸에는 끌 스위치가 없다.
CHECKBOX_KIND = "체크박스"
CHECK_VALUES = {"체크", "해제"}

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
    """`오퍼별 표시명 · Single` → `오퍼별 표시명` · `아동 추가 금액 — 소아` → `아동 추가 금액`.

    판매 연결 일괄 드로어의 표시명은 체크한 룸마다 칸이 하나씩 늘어난다 — 사전에는 한 줄
    (`오퍼별 표시명 · 〈룸 카테고리명〉`)로 있고 지시서는 룸 이름을 넣어 쓴다.
    """
    for base in ROW_SUFFIX_FIELDS:
        for sep in ROW_SUFFIX_SEPARATORS:
            if name.startswith(f"{base}{sep}"):
                return base
    return name


def strip_placeholder_suffix(label):
    """`연령별 단가 · 〈연령 구간 노출명〉` → `연령별 단가`. 자리표시가 없으면 그대로."""
    return PLACEHOLDER_SUFFIX_RE.sub("", label).strip()


def find_repeat_row_format_gaps(steps):
    """반복 행 이름이 정본 형식(`<칸 이름> <N> · <하위 칸>`)에서 벗어나면 오류.

    화면에서 지시서를 실행하는 도우미는 이 형태로 행을 찾는다 — 빈칸 없는 `구간 1· 수수료 값`,
    전각 가운뎃점 `구간 1 ・ 수수료 값` 은 같은 줄로 읽히지 않는다.
    """
    problems = []
    seen = set()
    for step in steps:
        for name, _ in step["rows"]:
            if not REPEAT_LOOSE_RE.match(name) or REPEAT_PREFIX_RE.match(name):
                continue
            if (step["num"], name) in seen:
                continue
            seen.add((step["num"], name))
            problems.append(
                f"{step['num']}단계: 반복 행 이름 `{name}` 이 정본 형식이 아니다 — "
                "`<칸 이름> <N> · <하위 칸>` 으로 적는다(홑 빈칸 · 가운뎃점은 빈칸으로 감싼 ` · `)"
            )
    return problems


def find_check_value_class_gaps(steps, kinds):
    """`체크`/`해제` 를 체크박스가 아닌 칸에 쓰면 오류 — 그 칸에는 끌 스위치가 없다.

    `다중 체크`·`선택`·`라디오` 는 고른 것을 `선택: …` 으로 적고, 아무것도 안 고르면 `비움` 이다.
    사전에 없는 이름은 건드리지 않는다(그쪽은 `사전에 없는 칸 이름` 이 따로 알린다).
    """
    problems = []
    for step in steps:
        for name, value in step["rows"]:
            if value.strip() not in CHECK_VALUES:
                continue
            n = norm_field(name)
            for key in (n, strip_repeat_prefix(n), strip_row_suffix(n)):
                found = kinds.get(key)
                if found:
                    break
            if not found or CHECKBOX_KIND in found:
                continue
            kind = " · ".join(sorted(found))
            problems.append(
                f"{step['num']}단계: `{name}` 은 체크박스가 아니라 `{kind}` 다 — "
                f"고른 것은 `선택: …`, 아무것도 안 고르면 `비움` 으로 적는다(지금 `{value}`)"
            )
    return problems


def load_dictionary(path):
    """화면 사전에서 필드 label · screen_label 과 반복 행의 columns 를 모은다."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    labels = set()

    def add(value):
        """칸 이름 하나를 허용 집합에 넣는다 — 자리표시 라벨이면 bare 이름도 함께."""
        norm = norm_field(value)
        if not norm:
            return
        labels.add(norm)
        bare = strip_placeholder_suffix(norm)
        if bare and bare != norm:
            labels.add(bare)

    # `screens` 의 검증 배너 줄은 최상위 `validation` 키를 가리키는 참조(`ref`)라 칸이 없다 —
    # 정본 한 벌을 함께 읽어 그 화면의 칸도 사전에 들어오게 한다.
    screens = list(data.get("screens") or [])
    validation = data.get("validation")
    if isinstance(validation, dict):
        screens.append(validation)
    for screen in screens:
        for block in screen.get("blocks") or []:
            for field in block.get("fields") or []:
                for key in ("label", "screen_label"):
                    value = field.get(key)
                    if value:
                        add(value)
                # 체크박스 칸은 지시서에서 `<칸 이름> · <체크박스 문구>` 로도 쓴다
                checkbox_text = field.get("checkbox_text")
                if checkbox_text:
                    for key in ("label", "screen_label"):
                        value = field.get(key)
                        if value:
                            add(f"{value} · {checkbox_text}")
                # 반복 행 필드가 열 이름 목록을 들고 있으면 그것도 허용한다(아직 없는 사전이면 무시)
                for column in field.get("columns") or []:
                    if isinstance(column, str):
                        add(column)
                    elif isinstance(column, dict):
                        for key in ("label", "screen_label"):
                            value = column.get(key)
                            if value:
                                add(value)
    return labels


def load_dictionary_kinds(path):
    """화면 사전에서 `{칸 이름: {종류, …}}` 를 모은다 — 같은 이름이 화면마다 다른 종류일 수 있다."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    screens = list(data.get("screens") or [])
    validation = data.get("validation")
    if isinstance(validation, dict):
        screens.append(validation)
    kinds = {}
    for screen in screens:
        for block in screen.get("blocks") or []:
            for field in block.get("fields") or []:
                kind = field.get("kind")
                if not kind:
                    continue
                for key in ("label", "screen_label"):
                    value = field.get(key)
                    if value:
                        kinds.setdefault(norm_field(value), set()).add(kind)
    return kinds


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


def check(md_path, photos_dir=None, share_name=None, dictionary_path=None, contract_path=None,
          today=None):
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

    #: 인원 조합의 값은 **A-형 좌표**다(`A2,A3` · `A3:+14` · `A2C1_CHD`) — 시트 좌표가 아니라
    #: 화면이 요구하는 정본 표기다(2026-09-08 `services/occupancy_key`). 표 행뿐 아니라
    #: `카드: … 의 인원 조합 \`A2\` 행` · `주의: 이 룸만 인원 조합이 \`A2\` 하나다` 처럼
    #: 머리 줄에도 나온다.
    #:
    #: 거르는 축이 **둘**인 이유 — 어느 한쪽만으로는 구멍이 난다:
    #:  ① 자리(줄): `인원 조합` 이 적힌 줄에서만 눈감는다. 전역으로 `^A\d{1,2}$` 를
    #:     `CELL_EXCLUDE` 에 더하면 `A2` 는 통과하지만 **진짜 시트 A열 좌표 `A70` 까지
    #:     함께 눈감아**, 오탐을 없애려다 미탐을 만든다.
    #:  ② 모양(토큰): 그 줄에서도 A-형(`A2`)만 빼고 `B47` 은 그대로 잡는다. 줄만 보고
    #:     통째로 건너뛰면 `주의: 인원 조합은 요금표 B47 참고` 같은 줄이 통과한다.
    #: `_address_row`(주소 칸의 `Lot TT13`)와 같은 결이되 축이 하나 더 있다.
    A_FORM = re.compile(r"^A\d+$")

    def _occupancy_line(l):
        return "인원 조합" in l

    cells = [
        m.group(0)
        for l in lines
        if not l.startswith("```") and not _address_row(l)
        for m in CELL.finditer(l)
        if not CELL_EXCLUDE.match(m.group(0))
        and not (_occupancy_line(l) and A_FORM.match(m.group(0)))
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
    guide_day = guide_date(lines, today)
    past_sale_starts = find_past_sale_starts(parsed, guide_day)
    blank_booking_window = find_blank_booking_window(parsed)
    past_seasons = find_past_seasons(parsed, guide_day)
    season_overlaps = find_season_overlaps(parsed)
    needless_overwrite = find_needless_overwrite(parsed)
    cancel_policy_gaps = find_missing_cancel_policy(parsed)
    legacy_offer_steps = find_legacy_offer_edit_steps(parsed)
    rooms_before_offer = find_rooms_before_offer(parsed)
    skip_warning_steps = find_skip_warning_steps(parsed)
    campaign_uses = find_campaign_uses(parsed)
    age_band_order = find_age_band_order(parsed)
    age_band_overlaps = find_age_band_overlaps(parsed)
    band_code_formats = find_band_code_format(parsed)
    child_extra_missing = find_child_extra_missing(parsed)
    child_extra_no_occupancy = find_child_extra_without_occupancy(parsed)
    child_lodging_addons = find_child_lodging_addon(parsed)
    occupancy_key_legacy = find_occupancy_key_legacy(parsed)
    los_prices_formats = find_los_prices_format(parsed)
    audience_only_names = find_audience_only_names(parsed)
    hangul_room_names = find_hangul_room_names(parsed)
    extra_bed_rules = find_extra_bed_optional_rules(parsed)
    child_policy_gaps = find_child_policy_without_age_band(parsed)
    gala_addons = find_gala_addons(parsed)
    gala_surcharge_gaps = find_gala_surcharge_gaps(parsed)
    adult_only_names = find_adult_only_charge_names(parsed)
    benefit_frequency_gaps = find_benefit_frequency_without_quantity(parsed)
    create_only_fields = find_create_only_fields(parsed)
    room_photo_saves = find_room_photo_saves(parsed)
    photo_count_gaps = find_photo_count_gaps(parsed)
    addon_card_gaps = find_addon_card_gaps(parsed)
    promo_common = find_promo_common_cards(parsed)
    season_saves = find_season_save_gaps(parsed)
    cancel_policy_saves = find_cancel_policy_save_gaps(parsed)
    repeat_row_formats = find_repeat_row_format_gaps(parsed)
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
    check_value_classes = []
    if dictionary_path:
        try:
            labels = load_dictionary(dictionary_path)
            field_kinds = load_dictionary_kinds(dictionary_path)
        except (OSError, ValueError) as e:
            dict_error = str(e)
        else:
            check_value_classes = find_check_value_class_gaps(parsed, field_kinds)
            seen = []
            for name, _ in rows:
                n = norm_field(name)
                if not n or n in labels or n in DICT_EXEMPT or n in seen:
                    continue
                if strip_repeat_prefix(n) in labels:  # 반복 행은 열 이름으로 한 번 더 본다
                    continue
                if strip_row_suffix(n) in labels:  # `오퍼별 표시명 · <룸 이름>` 은 앞부분으로 본다
                    continue
                if n == CAMPAIGN_FIELD:  # 걷힌 칸 — `find_campaign_uses` 가 오류로 잡는다(두 번 알리지 않는다)
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
        "guide_date": guide_day,
        "past_sale_starts": past_sale_starts,
        "blank_booking_window": blank_booking_window,
        "past_seasons": past_seasons,
        "season_overlaps": season_overlaps, "needless_overwrite": needless_overwrite,
        "cancel_policy_gaps": cancel_policy_gaps, "skip_warning_steps": skip_warning_steps,
        "legacy_offer_steps": legacy_offer_steps, "rooms_before_offer": rooms_before_offer,
        "campaign_uses": campaign_uses,
        "age_band_order": age_band_order,
        "age_band_overlaps": age_band_overlaps,
        "band_code_formats": band_code_formats,
        "child_extra_missing": child_extra_missing,
        "child_extra_no_occupancy": child_extra_no_occupancy,
        "child_lodging_addons": child_lodging_addons,
        "occupancy_key_legacy": occupancy_key_legacy,
        "los_prices_formats": los_prices_formats,
        "audience_only_names": audience_only_names,
        "hangul_room_names": hangul_room_names,
        "extra_bed_rules": extra_bed_rules,
        "child_policy_gaps": child_policy_gaps,
        "gala_addons": gala_addons,
        "gala_surcharge_gaps": gala_surcharge_gaps,
        "adult_only_names": adult_only_names,
        "benefit_frequency_gaps": benefit_frequency_gaps,
        "create_only_fields": create_only_fields,
        "room_photo_saves": room_photo_saves,
        "photo_count_gaps": photo_count_gaps,
        "addon_card_gaps": addon_card_gaps,
        "promo_common": promo_common, "season_saves": season_saves,
        "cancel_policy_saves": cancel_policy_saves,
        "repeat_row_formats": repeat_row_formats,
        "check_value_classes": check_value_classes,
        "currency": currency,
        "dict_checked": bool(dictionary_path), "dict_error": dict_error, "unknown_fields": unknown_fields,
        "contract_checked": bool(contract_path), "contract_error": contract_error,
        "loose_amounts": loose_amounts,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="입력 지시서(manual.md) 형식 검사")
    ap.add_argument("manual", help="검사할 manual.md 경로")
    ap.add_argument("--photos", default=None, help="사진 폴더 (선택 — 주면 파일 존재까지 확인)")
    ap.add_argument("--share-name", default=None,
                    help="공유 폴더명 (선택 — 주면 `폴더:` 줄 형식까지 확인, 예: 우에노_토우가네야. "
                         "생략해도 원고가 `<이름>/_원고/manual.md` 자리면 경로에서 알아낸다)")
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

    share_name = args.share_name
    derived_share = None
    if not share_name:
        derived_share = derive_share_name(args.manual)
        share_name = derived_share

    r = check(args.manual, args.photos, share_name, dictionary, args.contract)

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
    for p in (r["past_sale_starts"] + r["past_seasons"]
              + r["season_overlaps"] + r["cancel_policy_gaps"] + r["skip_warning_steps"]
              + r["legacy_offer_steps"] + r["rooms_before_offer"]
              + r["campaign_uses"] + r["age_band_order"] + r["age_band_overlaps"]
              + r["band_code_formats"] + r["child_extra_missing"]
              + r["child_extra_no_occupancy"]
              + r["child_lodging_addons"] + r["occupancy_key_legacy"]
              + r["los_prices_formats"]
              + r["audience_only_names"] + r["gala_addons"]
              + r["gala_surcharge_gaps"] + r["create_only_fields"]
              + r["room_photo_saves"] + r["photo_count_gaps"] + r["addon_card_gaps"]
              + r["promo_common"] + r["season_saves"] + r["cancel_policy_saves"]
              + r["repeat_row_formats"] + r["check_value_classes"]
              + r["benefit_frequency_gaps"]):
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
    for w in r["blank_booking_window"]:
        warnings.append(w)
    for w in r["needless_overwrite"]:
        warnings.append(w)
    for w in r["child_policy_gaps"]:
        warnings.append(w)
    for w in r["adult_only_names"]:
        warnings.append(w)
    for w in r["hangul_room_names"]:
        warnings.append(w)
    for w in r["extra_bed_rules"]:
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
    if derived_share:
        print(f"공유 폴더명 `{derived_share}` — 원고 경로(`<이름>/{DRAFT_DIR}/manual.md`)에서 알아냄")
    elif not share_name:
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
