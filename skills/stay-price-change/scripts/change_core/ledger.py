"""담당자 PC 의 변경 장부(SQLite 하나). 지우는 일은 없다.

자리는 어느 폴더에서 Claude 를 열어도 같은 한 곳이다: `~/Documents/어딩 Stay 가격 변경 기록/가격장부.sqlite3`.
환경 변수 `STAY_PRICE_LEDGER_DIR` 로 다른 폴더를 줄 수 있다(시험은 임시 폴더를 쓴다). 문서 폴더를 iCloud 같은 클라우드가 동기화하면
장부 파일이 클라우드로만 옮겨지거나 사본으로 갈릴 수 있어, 그때는 동기화하지 않는 폴더를 준다. 기록 폴더에 작업 폴더나 페이지가
있는데 장부 파일이 없으면 장부가 있던 자리다 — 빈 장부를 새로 만들지 않고 거절한다(`_missing`). 그래서 작업 폴더를 처음 만드는
`work` 가 장부도 같이 만든다(files.new_work). 가격·부과금·프로모션·부가옵션
도우미가 모두 이 장부 하나에 적는다. 시험은 `STAY_PRICE_TEST_NOW`(ISO 시각)로 장부의 시계를 그 시각에 세운다 — 명령을 부르는
시험이 이 컴퓨터의 시계에 기대지 않게(clock).

    meta         schema_version — 이 코드보다 새 판이 만든 장부는 열지 않는다
    changes      변경 한 번에 한 줄 — 종류(change / snapshot / rollback), 상태(previewed → applying → stopped / applied,
                 저장할 것이 없는 미리보기는 처음부터 empty, 다시 계산해 새 번호로 바뀐 미리보기는 replaced — 새 번호의
                 `replaces` 가 그 번호다, 지금 상태 저장은 saved),
                 호텔(페이지가 알아본 번호와 이름), 요청 문장, 읽은 시각, 되돌리기면 되돌리는 변경 번호, 요청 원문(JSON),
                 그 번호의 계산이 바탕으로 삼은 읽은 값(JSON — 읽은 범위가 들어 있다), 마지막으로 이어 가도 된다고 본
                 때(`active_at` — begin 이 받아들인 읽은 값의 시각, 저장 결과를 적은 때, 이어서 해도 된다고 한 check 의
                 읽은 값의 시각)
    item_values  항목 하나의 필드 하나에 한 줄 — 항목 종류(`price_cell` …), 굳은 키, 이름, 필드, 그때 상태, 전 값, 후 값,
                 넣는 방법(set / clear, 넣지 않으면 비어 있음 — 미리보기 때 정해지고 begin 은 저장 단계가 이것과 같은지 본다),
                 판정 · 표시 · 빨간 줄에 고른 것과 그렇게 고르며 담당자가 한 말, 몇 번째 저장인지, 다시 읽어 맞았는지와 읽은 값
    steps        저장 한 번에 한 줄 — 단계 종류와 내용(JSON), 끝날 때마다 바로 적는다. `unknown` 은 저장 단추는 눌렸고
                 저장됐는지 모르는 단계(다시 읽어 가릴 때까지 failed 로 둔다)
    checks       check 한 번에 한 줄 — 그 읽은 값의 시각, 이어서 해도 되는지와 안 되는 까닭, 멈춘 까닭, 남은 저장의 항목
                 가운데 그 계산의 읽은 값과 지금 값이 다른 것(지금 값). 결과 페이지가 멈춘 변경을 이것으로 말한다. 그 뒤에
                 저장 결과가 적히면 다 쓴 것(`spent`)이 된다 — 그 check 는 그 저장을 모른다
    begins       적용을 시작한 변경 하나에 한 줄 — begin 이 처음 받아들인 때. 목록의 「적용 중」 · 「적용하다 멈춤」이 이 시각이다
    unused_choices  미리보기 하나에 한 줄(있을 때만) — 담당자가 고른 빨간 줄 고름 가운데 어느 항목도 쓰지 않은 것(JSON, 고르며 한
                 말과 그 까닭). 항목 줄에는 남지 않아, 결과 페이지의 「고르신 빨간 줄」이 미리보기처럼 이것으로 댄다
    halts        저장은 됐는데 ERP 가 다음 저장을 하지 말라고 한 단계와 그 까닭(시즌 창의 「공급 통화 없음」 띠)
    issues       저장 하나의 부를 값을 낸 기록 — 어느 읽은 값으로(그 시각) 냈고 언제까지 누를 수 있는지(`until_ms`). 누를 때마다 그
                 범위를 다시 읽어야 하는 저장(시즌 창)이 쓴다: 같은 읽은 값으로 두 번 내지 않고, 저장 답은 낸 부를 값의 것만 받는다

어느 기록의 값이 ERP 에 살아 있는지(되돌렸는지 · 되돌렸다가 다시 살렸는지)는 장부에 적어 두지 않고 저장된 값들의 차례에서 그때마다
셈한다(`_chain` — change_core.alive). 그래서 되돌리기도 저장 상태로 되돌리기도 바꾸기처럼 되돌릴 수 있고, 몇 번을 되돌려도 목록 ·
되돌리기 · 결과 페이지 · 견주기가 같은 셈을 읽는다.

snapshot 은 읽어서 적어 두기만 하므로 적는 순간 상태가 saved 다(적용한 것이 아니다 — 목록에서 적용된 변경과 갈린다).
바뀌는 항목이 없거나 빨간 줄을 모두 안 바꾸기로 고른 미리보기는 적는 순간 상태가 empty 다 — 적용할 것이 없어 begin 이 받지 않고,
목록에서 적용을 기다리는 미리보기(previewed)처럼 읽히지 않는다. 담당자가 마음을 바꿔 다시 계산하면 replaced 가 된다.

도우미마다 자기 항목 종류로 장부를 연다(`Ledger(kind="price_cell")`). 그러면 `list_changes` 에는 그 종류의 번호만 나오고, 다른
종류의 번호를 주면 어느 도우미의 기록인지 대며 거절한다. 도우미의 `list` 명령은 종류 없이 열어 세 도우미의 기록을 모두 싣는다
(files.listed). 번호의 종류는 그 번호에 적힌 항목 줄의 종류다(표의 모양은 그대로다 — `_kind_of`).

적용을 시작하거나(begin) 멈춘 변경을 이어 가는(check) 읽은 값은 다시 읽은 값이어야 한다 — begin 은 그 번호를 계산한 뒤에 읽은
값만, check 는 장부가 그 번호에 마지막으로 적은 것(계산 · 저장 결과) 뒤에 읽은 값만 받는다(`_read_before`). 미리보기의 읽은 값
그대로나 그보다 앞선 읽은 값, 앞선 읽기 폴더의 답을 다시 쓴 읽기는 견줄 것이 없어 다시 읽은 것이 아니다.

적용 중인 변경이 `IDLE`(15분) 동안 아무 일이 없으면 멈춘 변경이다 — 목록 · calls · check · 결과 페이지 어디서나. 세션이
저장 사이에서 끊겨도 장부는 적용 중으로 남는데, 그 사이 ERP 값이 바뀌었을 수 있어 다시 읽지 않고는 남은 저장을 내지 않는다.
멈춘 뒤에 적힌 저장 결과는 적기만 하고 변경을 다시 살리지 않는다. 다시 살리는 것은 방금 읽은 값으로 이어서 해도 된다고 본
check 뿐이다.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable, Iterator, Mapping, Sequence

from .alive import Alive, Saved, Status, Write, walk
from .items import Difference, ItemState, Reading, decode_state, encode_state, stale_items
from .money import money, money_text
from .rollback import LaterWrite, RecordedChange, RecordedItem

LEDGER_ENV = "STAY_PRICE_LEDGER_DIR"
CLOCK_ENV = "STAY_PRICE_TEST_NOW"   # 시험용 — 주면 장부의 시계가 그 시각(ISO)에 서 있다
FOLDER_NAME = "어딩 Stay 가격 변경 기록"
DB_NAME = "가격장부.sqlite3"
WORK = "작업"                        # 기록 폴더 안의 작업 폴더들(files.new_work) — 있으면 장부가 있던 기록 폴더다
SCHEMA_VERSION = 4                   # 3 — 상태 empty(저장할 것이 없는 미리보기) · 4 — 부를 값을 낸 기록(issues)
IDLE = timedelta(minutes=15)         # 적용 중인 변경이 이만큼 아무 일이 없으면 멈춘 것이다(끊긴 세션). 받아들이는 읽은 값도 이만큼 안이다
CAUSES = ("failed", "unknown", "cut_off", "halted")   # 멈춘 까닭 — 저장이 실패함 · 저장됐는지 모름 · 실패 없이 끊김 · 저장은 됐는데 ERP 가
# 다음 저장을 하지 말라고 함(halts — 시즌 창의 「공급 통화 없음」 띠)
KIND_NAMES = {"price_cell": "가격 캘린더 도우미", "addon_price": "부가옵션 가격 도우미", "charge": "부과금 도우미",
              "promotion": "프로모션 할인 도우미"}   # 항목 종류 → 그 기록을 쓰는 도우미(거절 문장 · 목록)
OFFER_KIND = "price_cell"            # 장부의 오퍼 칸을 채우는 단 하나의 종류 — 부가옵션 · 부과금 도우미는 비운다(항목 줄이 없는 번호를 가른다)

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK (kind IN ('change', 'snapshot', 'rollback')),
  status TEXT NOT NULL CHECK (status IN ('previewed', 'empty', 'applying', 'stopped', 'applied', 'replaced', 'saved')),
  hotel TEXT NOT NULL,
  hotel_id TEXT NOT NULL DEFAULT '',
  offer TEXT NOT NULL,
  currency TEXT NOT NULL,
  sentence TEXT NOT NULL,
  read_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  applied_at TEXT,
  verified_at TEXT,
  reverses INTEGER REFERENCES changes(id),
  replaces INTEGER REFERENCES changes(id),
  request TEXT,
  reading TEXT,
  active_at TEXT
);
CREATE TABLE IF NOT EXISTS item_values (
  change_id INTEGER NOT NULL REFERENCES changes(id),
  item_kind TEXT NOT NULL,
  item_key TEXT NOT NULL,
  label TEXT NOT NULL,
  field TEXT NOT NULL,
  state TEXT NOT NULL,
  before TEXT,
  after TEXT,
  action TEXT CHECK (action IN ('set', 'clear')),
  step INTEGER,
  verified INTEGER NOT NULL DEFAULT 0,
  seen TEXT,
  seen_state TEXT,
  verdict TEXT,
  marks TEXT NOT NULL DEFAULT '',
  choice TEXT,
  said TEXT,
  PRIMARY KEY (change_id, item_kind, item_key, field)
);
CREATE TABLE IF NOT EXISTS steps (
  change_id INTEGER NOT NULL REFERENCES changes(id),
  idx INTEGER NOT NULL,
  kind TEXT NOT NULL,
  label TEXT NOT NULL,
  body TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'saved', 'failed')),
  finished_at TEXT,
  note TEXT,
  unknown INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (change_id, idx)
);
CREATE TABLE IF NOT EXISTS checks (
  change_id INTEGER NOT NULL REFERENCES changes(id),
  checked_at TEXT NOT NULL,
  read_at TEXT NOT NULL,
  can_continue INTEGER NOT NULL,
  cause TEXT,
  why TEXT NOT NULL,
  moved TEXT NOT NULL,
  spent INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS begins (
  change_id INTEGER PRIMARY KEY REFERENCES changes(id),
  begun_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS keep_checks BEFORE DELETE ON checks BEGIN SELECT RAISE(ABORT, '장부는 지우지 않습니다'); END;
CREATE TABLE IF NOT EXISTS unused_choices (
  change_id INTEGER PRIMARY KEY REFERENCES changes(id),
  choices TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS halts (
  change_id INTEGER NOT NULL REFERENCES changes(id),
  idx INTEGER NOT NULL,
  note TEXT NOT NULL,
  PRIMARY KEY (change_id, idx)
);
CREATE TABLE IF NOT EXISTS issues (
  change_id INTEGER NOT NULL REFERENCES changes(id),
  idx INTEGER NOT NULL,
  read_at TEXT NOT NULL,
  until_ms INTEGER NOT NULL,
  issued_at TEXT NOT NULL,
  PRIMARY KEY (change_id, idx, read_at)
);
CREATE TRIGGER IF NOT EXISTS keep_issues BEFORE DELETE ON issues BEGIN SELECT RAISE(ABORT, '장부는 지우지 않습니다'); END;
CREATE TRIGGER IF NOT EXISTS keep_begins BEFORE DELETE ON begins BEGIN SELECT RAISE(ABORT, '장부는 지우지 않습니다'); END;
CREATE TRIGGER IF NOT EXISTS keep_halts BEFORE DELETE ON halts BEGIN SELECT RAISE(ABORT, '장부는 지우지 않습니다'); END;
CREATE TRIGGER IF NOT EXISTS keep_unused BEFORE DELETE ON unused_choices BEGIN SELECT RAISE(ABORT, '장부는 지우지 않습니다'); END;
CREATE TRIGGER IF NOT EXISTS keep_meta BEFORE DELETE ON meta BEGIN SELECT RAISE(ABORT, '장부는 지우지 않습니다'); END;
CREATE TRIGGER IF NOT EXISTS keep_changes BEFORE DELETE ON changes BEGIN SELECT RAISE(ABORT, '장부는 지우지 않습니다'); END;
CREATE TRIGGER IF NOT EXISTS keep_values BEFORE DELETE ON item_values BEGIN SELECT RAISE(ABORT, '장부는 지우지 않습니다'); END;
CREATE TRIGGER IF NOT EXISTS keep_steps BEFORE DELETE ON steps BEGIN SELECT RAISE(ABORT, '장부는 지우지 않습니다'); END;
"""

ROW = "item_kind = ? AND item_key = ? AND field = ?"


class LedgerError(ValueError):
    """장부 순서에 맞지 않는 요청 — 문장은 담당자에게 그대로 보여 줄 수 있다."""


def ledger_dir() -> Path:
    override = os.environ.get(LEDGER_ENV)
    folder = Path(override).expanduser() if override else Path.home() / "Documents" / FOLDER_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _missing(path: Path) -> str | None:
    """장부 파일이 없는데 그 기록 폴더에 작업 폴더나 페이지가 있으면(장부가 있던 자리) 담당자에게 전할 문장, 아니면 None."""
    folder = path.parent
    if path.exists() or not (any((folder / WORK).glob("*")) or any(folder.glob("*.html"))):
        return None
    return (f"기록 폴더({folder})에 작업 폴더 · 페이지가 있는데 장부 파일({path.name})이 없습니다 — 장부가 있던 자리라 빈 장부를 새로 "
            "만들지 않았습니다. 문서 폴더(Documents)를 iCloud 같은 클라우드가 동기화하면 장부 파일이 클라우드로만 옮겨졌거나(내려받지 "
            "않음) 다른 이름의 사본이 됐을 수 있습니다. 여기서 멈추고 담당자에게 이 글을 그대로 전합니다 — 파일을 되찾은 뒤 같은 명령을 "
            f"다시 하거나, 동기화하지 않는 폴더를 환경 변수 {LEDGER_ENV} 로 정하고 기록 폴더를 그리로 옮깁니다")


def _moment(text: str) -> datetime:
    moment = datetime.fromisoformat(text)
    return moment if moment.tzinfo else moment.astimezone()


def clock():
    """지금 시각을 주는 함수 — 이 컴퓨터의 시계. `STAY_PRICE_TEST_NOW` 가 있으면 그 시각에 서 있는 시계다."""
    fixed = os.environ.get(CLOCK_ENV)
    if fixed:
        moment = _moment(fixed)
        return lambda: moment
    return lambda: datetime.now().astimezone()


def now_text() -> str:
    return clock()().isoformat(timespec="seconds")


def _minutes(span: timedelta) -> int:
    return int(span.total_seconds() // 60)


def _when(text: str) -> str:
    return _moment(text).strftime("%m/%d %H:%M:%S")


def _read_before(read_at: str, own: str, moments: Iterable[str | None]) -> str | None:
    """읽은 값이 다시 읽은 값이 아니면 장부의 그 시각, 맞으면 None. 그 번호가 바탕으로 삼은 읽은 값(`own` — 미리보기 · 되돌리기의
    읽은 시각)과 같거나 앞선 시각이면 그 읽은 값 자체이거나 더 오래된 것이고(앞선 읽기 폴더의 답을 다시 묶어도 시각은 그대로다),
    장부가 적은 때(`moments`) 가운데 가장 늦은 것보다 앞선 초에 읽었으면 그 기록을 모르는 값이다. 장부의 시각은 초까지라 같은 초에
    일어난 둘의 앞뒤는 가릴 수 없어, 같은 초는 앞서지 않은 것으로 본다(도우미는 장부에 적은 뒤에 다시 읽는다)."""
    if _moment(read_at) <= _moment(own):
        return own
    latest = max((moment for moment in moments if moment), key=_moment)
    return latest if _moment(read_at).replace(microsecond=0) < _moment(latest) else None


@dataclass(frozen=True)
class ValueRow:
    """미리보기 때 적는 한 줄 — 미리보기가 보인 그 항목의 그 필드. `after` 는 후 값(바뀌지 않는 필드는 None), `action` 은
    저장이 그 필드에 하는 일(`set` 넣음 · `clear` 비움 · None 넣지 않음), `choice` 는 그 항목의 빨간 줄에 고른 것, `said` 는
    그렇게 고르며 담당자가 한 말. `begin` 은 저장 단계가 쓰는 값이 이 줄들과 꼭 같을 때만 시작한다."""
    item_kind: str
    item_key: str
    label: str
    field: str
    state: str
    before: Decimal | None
    after: Decimal | None = None
    verdict: str | None = None
    marks: tuple[str, ...] = ()
    action: str | None = None
    choice: str | None = None
    said: str | None = None

    def __post_init__(self):
        if (self.action not in (None, "set", "clear") or (self.action == "set" and self.after is None)
                or (self.action == "clear" and self.after is not None)):
            raise LedgerError(f"넣는 값과 방법이 맞지 않습니다: {self.label} · {self.field} ({self.action}, {self.after})")


@dataclass(frozen=True)
class FieldWrite:
    """저장 단계가 쓰는 필드 하나. `after` 가 None 이면 그 필드를 비운다."""
    item_kind: str
    item_key: str
    field: str
    after: Decimal | None


@dataclass(frozen=True)
class StepPlan:
    kind: str
    label: str
    body: Mapping
    writes: tuple[FieldWrite, ...]


@dataclass(frozen=True)
class StepRecord:
    index: int
    kind: str
    label: str
    body: dict
    status: str
    finished_at: str | None
    note: str | None
    unknown: bool = False


@dataclass(frozen=True)
class RowRecord:
    """장부의 한 줄. 저장한 줄이면 장부의 차례에서 셈한 지금이 붙는다(change_core.alive) — `live` 그 값이 아직 이 번호의 것이다 ·
    `rolled_back_by` 그 값을 되돌린 기록(되돌려져 있지 않으면 None) · `redone` 되돌렸다가 다시 살렸으면 (되돌린 기록, 다시 살린 기록).
    살아 있지도 되돌려져 있지도 않으면 뒤 기록이나 도우미 밖이 덮었다."""
    item_kind: str
    item_key: str
    label: str
    field: str
    state: str
    before: Decimal | None
    after: Decimal | None
    action: str | None
    step: int | None
    written: bool
    verified: bool
    seen: Decimal | None
    seen_state: str | None
    rolled_back_by: int | None
    verdict: str | None
    marks: tuple[str, ...]
    choice: str | None = None
    said: str | None = None
    redone: tuple[int, int] | None = None
    live: bool = False


@dataclass(frozen=True)
class Checked:
    """멈춘 뒤 마지막 check 가 본 것 — 결과 페이지가 멈춘 변경을 말할 때 쓴다. `read_at` 은 그 check 의 읽은 값의 시각,
    `can_continue` · `why` 는 그 답, `cause` 는 그때의 멈춘 까닭(이어서 해도 된다고 해 적용 중으로 돌아간 변경도 왜 멈췄었는지
    말한다), `moved` 는 남은 저장의 항목 가운데 그 계산의 읽은 값과 지금 값이 다른 것 → 지금 값(없어졌으면 None)."""
    read_at: str
    can_continue: bool
    cause: str | None
    why: tuple[str, ...]
    moved: Mapping[tuple[str, str], ItemState | None]


@dataclass(frozen=True)
class ChangeRecord:
    """장부의 변경 하나. `status` · `cause` · `checked` 는 장부를 읽은 때(`as_of` — 장부의 시계) 기준이다(15분 멈춤). 결과 페이지는
    그때를 오늘로 삼는다 — 그날이 아닌 check 의 시각에는 날짜를 붙인다. `unused` 는 고른 빨간 줄 고름 가운데 어느 항목도 쓰지
    않은 것(`unused_choices`, 도우미가 준 모양 그대로)."""
    id: int
    kind: str
    status: str
    hotel: str
    hotel_id: str
    offer: str
    currency: str
    sentence: str
    read_at: str
    created_at: str
    applied_at: str | None
    verified_at: str | None
    reverses: int | None
    request: dict | None
    steps: tuple[StepRecord, ...]
    rows: tuple[RowRecord, ...]
    cause: str | None = None
    replaces: int | None = None
    checked: Checked | None = None
    as_of: str | None = None
    unused: tuple[dict, ...] = ()
    halt: str | None = None   # 저장 뒤 ERP 가 다음 저장을 하지 말라고 한 까닭(halts) — 멈춘 까닭이 halted 일 때


@dataclass(frozen=True)
class StepSeen:
    """저장 한 번을 방금 읽은 값으로 본 것. `ledger` 는 장부의 상태(saved · pending · failed · unknown), `seen` 은 읽은 값이
    말하는 것 — saved 넣은 값 그대로 · not_saved 전 값 그대로 · mixed 섞임(저장 한 번은 통째로 되거나 안 되니 다른 손이 탔다) ·
    changed 그 사이 다른 값이 됨. `settled` 는 이번에 가린 「모름」(saved · not_saved), `moved` 는 남은 저장의 칸 가운데
    그 계산이 바탕으로 삼은 읽은 값과 지금 값이 다른 칸 수."""
    index: int
    label: str
    ledger: str
    seen: str
    settled: str | None = None
    moved: int = 0


@dataclass(frozen=True)
class CheckReport:
    """`cause` 는 멈춘 까닭 — failed 저장이 실패함 · unknown 저장됐는지 모름 · cut_off 실패 없이 중간에 끊김 · halted 저장 뒤 ERP 가
    다음 저장을 하지 말라고 함(멈추지 않았으면 None). `last_saved` · `next` 는 마지막으로 저장된 단계와 다음에 할 단계(없으면 None), `note` 는 멈춘 저장의 메모."""
    change_id: int
    status: str
    steps: tuple[StepSeen, ...]
    remaining: tuple[int, ...]
    can_continue: bool
    why: tuple[str, ...]
    cause: str | None = None
    last_saved: StepSeen | None = None
    next: StepSeen | None = None
    note: str | None = None


def _kind_of(db, change_id: int | None) -> str | None:
    """번호의 종류 — 그 번호에 적힌 항목 줄의 종류. 항목 줄이 없는 번호(넣을 것이 없던 미리보기 · 되돌리기)는 오퍼 칸이 찼으면 가격
    캘린더의 것이고(오퍼 칸은 가격 캘린더 도우미만 채운다), 되돌리기면 되돌리는 번호의 종류다. 그래도 모르면 None — 어느 도우미든
    받고, 목록에는 종류 없이 나온다. 되돌리기는 앞선 번호만 가리키므로 따라가기는 끝난다."""
    while change_id is not None:
        row = db.execute("SELECT item_kind FROM item_values WHERE change_id = ? LIMIT 1", (change_id,)).fetchone()
        if row is not None:
            return row["item_kind"]
        header = db.execute("SELECT offer, reverses FROM changes WHERE id = ?", (change_id,)).fetchone()
        if header is None:
            return None
        if header["offer"]:
            return OFFER_KIND
        change_id = header["reverses"]
    return None


def _saved_state(change_id: int) -> str:
    return f"{change_id}번은 저장해 둔 상태입니다. 그 상태로 돌리려면 '저장해 둔 상태로 되돌리기'를 씁니다"


def _restored(kind: str, request: str | None) -> int | None:
    """저장 상태로 되돌리기면 그 저장 번호 — 장부의 종류는 change 라 요청(`restore_snapshot`)으로 가른다."""
    data = json.loads(request) if kind == "change" and request else None
    return int(data["snapshot"]) if data and data.get("kind") == "restore_snapshot" else None


def _tally(items: Mapping[tuple[str, str], Mapping[str, Status]]) -> dict:
    """기록 하나가 저장한 항목들(Alive.of)의 수 — `written` 저장한 항목, `rolled_back` 그 가운데 되돌린 필드가 있는 항목과 `undone_by`
    그 기록들, `redone` 되돌린 필드는 없고 되돌렸다가 다시 살린 필드가 있는 항목과 `redone_by` 그 기록들(되돌린 · 다시 살린),
    `live` 넣은 필드가 모두 살아 있는 항목."""
    undone, redone = [], []
    for fields in items.values():
        if any(status.undone_by for status in fields.values()):
            undone.append(fields)
        elif any(status.redone for status in fields.values()):
            redone.append(fields)
    return dict(written=len(items), rolled_back=len(undone),
                undone_by=sorted({status.undone_by for fields in undone for status in fields.values() if status.undone_by}),
                redone=len(redone),
                redone_by=sorted({number for fields in redone for status in fields.values() if status.redone
                                  for number in status.redone}),
                live=sum(all(status.live for status in fields.values()) for fields in items.values()))


def _absent(item) -> bool:
    return item is None or item.state == "missing"


def seen_kind(state: str, before: Decimal | None, after: Decimal | None, seen_state: str | None, seen: Decimal | None) -> str:
    """장부의 한 줄(넣은 필드 하나 — 그때 상태 · 전 값 · 넣은 값)을 다시 읽은 것(상태 · 값, 항목이 없으면 None)으로 — after 넣은 값 ·
    before 전 값(없던 항목이면 지금도 없음) · other 그 밖. check · 확인 · 결과 페이지가 모두 이것으로 가린다."""
    absent = seen_state in (None, "missing")
    if not absent and seen == after:
        return "after"
    if (state == "missing" and absent) or (state != "missing" and not absent and seen == before):
        return "before"
    return "other"


def _field_seen(row, item) -> str:
    return seen_kind(row["state"], money(row["before"]), money(row["after"]), None if item is None else item.state,
                     None if _absent(item) else item.fields.get(row["field"]))


def left_out(marks: Iterable[str], kind: str, skippable: Callable[[tuple[str, ...]], bool] | None) -> bool:
    """ERP 가 넣지 않을 수 있는 줄(`skippable(표시)` — 시즌 창이 객실의 허용 인원 조합 밖이면 그 칸을 만들지 않는다)이 전 값
    그대로인지 — 그 줄은 저장이 됐는지에 대해 아무것도 말하지 않는다. 「이 저장이 됐다」의 뜻은 하나다: check 는 그 줄을 빼고
    가리고(줄이 모두 그렇다면 저장 안 됨 — 다시 눌러도 그 칸은 그대로다), 확인은 그 줄을 다른 값으로 치지 않는다."""
    return kind == "before" and skippable is not None and skippable(tuple(marks))


def _marks(row) -> tuple[str, ...]:
    return tuple(mark for mark in (row["marks"] or "").split(",") if mark)


def _same_item(then, now) -> bool:
    return (_absent(then) and _absent(now)) or (not _absent(then) and then.same_as(now))


@dataclass(frozen=True)
class Mismatch:
    """확인에서 넣은 값이 아닌 줄. `left_out` 은 ERP 가 넣지 않을 수 있는 줄이 전 값 그대로인 것이다(left_out — 다른 값이 아니다)."""
    item_kind: str
    item_key: str
    label: str
    field: str
    after: Decimal | None
    seen: Decimal | None
    seen_state: str | None
    left_out: bool = False


def _body(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class Ledger:
    def __init__(self, path: Path | None = None, now=None, kind: str | None = None):
        """`now` 는 지금 시각을 주는 함수(시험이 시계를 옮겨 본다). 장부가 적는 시각과, 멈춤 · 읽은 값의 나이를 이것으로 셈한다.
        `kind` 를 주면 그 항목 종류의 장부로 연다 — 목록은 그 종류의 번호만, 다른 종류의 번호는 거절한다."""
        self.path = Path(path) if path else ledger_dir() / DB_NAME
        self._now = now or clock()
        self.kind = kind
        missing = _missing(self.path)
        if missing:
            raise LedgerError(missing)
        with self._db() as db:
            has_meta = db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'").fetchone()
            found = db.execute("SELECT value FROM meta WHERE name = 'schema_version'").fetchone() if has_meta else None
            if found and int(found["value"]) > SCHEMA_VERSION:
                raise LedgerError(f"이 장부는 더 새 판 도우미가 만든 것입니다(장부 판 {found['value']}, 이 도우미는 "
                                  f"{SCHEMA_VERSION}). 도우미를 새로 받아 주세요")
            if found and int(found["value"]) < SCHEMA_VERSION:   # 표의 모양(상태의 CHECK)은 판마다 다르고 SQLite 는 고쳐 쓰지 못한다
                raise LedgerError(f"이 장부는 시험 판 도우미가 만든 것입니다(장부 판 {found['value']}, 이 도우미는 "
                                  f"{SCHEMA_VERSION}). 장부 폴더를 새로 정해 주세요({LEDGER_ENV})")
            db.executescript(SCHEMA)
            db.execute("INSERT INTO meta (name, value) VALUES ('schema_version', ?)"
                       " ON CONFLICT(name) DO UPDATE SET value = excluded.value", (str(SCHEMA_VERSION),))

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _insert(self, db, kind, status, hotel, hotel_id, offer, currency, sentence, read_at, rows: Iterable[ValueRow],
                reverses=None, request=None, reading=None, replaces=None) -> int:
        stamp = self._stamp()
        change_id = db.execute(
            "INSERT INTO changes (kind, status, hotel, hotel_id, offer, currency, sentence, read_at, created_at, updated_at,"
            " applied_at, reverses, replaces, request, reading) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, status, hotel, hotel_id, offer, currency, sentence, read_at, stamp, stamp,
             stamp if status == "applied" else None, reverses, replaces, None if request is None else _body(request),
             None if reading is None else _body(reading))).lastrowid
        db.executemany(
            "INSERT INTO item_values (change_id, item_kind, item_key, label, field, state, before, after, action, verdict, marks,"
            " choice, said) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(change_id, row.item_kind, row.item_key, row.label, row.field, row.state, money_text(row.before),
              money_text(row.after), row.action, row.verdict, ",".join(row.marks), row.choice, row.said) for row in rows])
        return change_id

    def record_preview(self, *, hotel: str, offer: str, currency: str, sentence: str, read_at: str,
                       hotel_id: str, rows: Iterable[ValueRow], request: Mapping | None = None,
                       reverses: int | None = None, reading: Mapping | None = None, replaces: int | None = None,
                       empty: bool = False, unused: Sequence[Mapping] = ()) -> int:
        """미리보기를 적는다. `reverses` 를 주면 그 변경을 되돌리는 변경(rollback)이다. `reading` 은 그 계산이 바탕으로 삼은
        읽은 값 — 적용 직전 낡음 확인과 다시 읽을 범위가 이것으로 정해진다. `empty` 는 저장 단계가 하나도 없는 미리보기(바뀌는
        항목이 없거나 빨간 줄을 모두 안 바꾸기로 고름)다 — 상태 empty 로 적고, 넣는 값이 있는 줄이 있으면 거절한다.

        `replaces` 는 이 미리보기가 바꾸는 앞 미리보기 번호다(빨간 줄을 고른 뒤 · 그대로 둔 칸도 되돌릴 때 · 적용 직전에 값이 달라
        다시 계산함). 같은 것을 하는(`_acts` — 가격 바꾸기 · 같은 변경 되돌리기 · 같은 저장 상태로 되돌리기) 같은 호텔 · 오퍼의,
        아직 적용을 시작하지 않은 미리보기여야 하고, 그 번호는 `replaced` 가 되어 begin 이 받지 않는다.

        `unused` 는 고른 빨간 줄 고름 가운데 어느 항목도 쓰지 않은 것(도우미의 모양 그대로) — `unused_choices` 에 둔다."""
        kind = "rollback" if reverses is not None else "change"
        rows = list(rows)
        if empty and any(row.action for row in rows):
            raise LedgerError("저장할 것이 없다는 미리보기에 넣는 값이 있습니다 — 미리보기를 다시 계산합니다")
        with self._db() as db:
            if reverses is not None and self._header(db, reverses)["kind"] == "snapshot":
                raise LedgerError(_saved_state(reverses))
            if replaces is not None:
                self._replace(db, replaces, self._acts(kind, reverses, request), hotel_id, offer)
            change_id = self._insert(db, kind, "empty" if empty else "previewed", hotel, hotel_id, offer, currency, sentence,
                                     read_at, rows, reverses, request, reading, replaces)
            if unused:
                db.execute("INSERT INTO unused_choices (change_id, choices) VALUES (?, ?)", (change_id, _body(list(unused))))
            return change_id

    @staticmethod
    def _acts(kind: str, reverses: int | None, request: Mapping | None) -> str:
        """미리보기가 하는 일 — 다시 계산한 미리보기는 같은 일을 하는 앞 미리보기만 바꾼다. 저장 상태로 되돌리기 · 시즌 다시 채우기는
        장부의 종류가 change 라 요청(`restore_snapshot` · `season_fill` — 같은 시즌끼리)으로 가른다."""
        if kind == "rollback":
            return f"{reverses}번 되돌리기"
        if request and request.get("kind") == "restore_snapshot":
            return f"{request.get('snapshot')}번 저장 상태로 되돌리기"
        if request and request.get("kind") == "season_fill":
            return f"시즌 {(request.get('season') or {}).get('id')} 다시 채우기"
        return "가격 바꾸기"

    def _replace(self, db, change_id: int, acts: str, hotel_id: str, offer: str) -> None:
        old = self._header(db, change_id)
        if old["status"] == "replaced":
            raise LedgerError(f"{change_id}번 미리보기는 이미 {self._replacer(db, change_id)}번으로 바뀌었습니다 — 그 번호를 바꿉니다")
        if old["status"] not in ("previewed", "empty"):
            raise LedgerError(f"{change_id}번은 바꿀 수 있는 미리보기가 아닙니다(종류 {old['kind']} · 상태 {self._status(old)}) — "
                              "아직 적용을 시작하지 않은 미리보기만 바꿉니다")
        was = self._acts(old["kind"], old["reverses"], None if old["request"] is None else json.loads(old["request"]))
        if was != acts:
            raise LedgerError(f"{change_id}번은 {was} 미리보기이고 이 계산은 {acts} 입니다 — 같은 것을 다시 계산한 미리보기만 바꿉니다")
        if old["hotel_id"] != hotel_id or old["offer"] != offer:
            raise LedgerError(f"{change_id}번은 호텔 {old['hotel_id']} · {old['offer']} 의 미리보기입니다 — 같은 호텔 · 오퍼의 미리보기만 바꿉니다")
        db.execute("UPDATE changes SET status = 'replaced', updated_at = ? WHERE id = ?", (self._stamp(), change_id))

    @staticmethod
    def _replacer(db, change_id: int) -> int:
        return db.execute("SELECT id FROM changes WHERE replaces = ?", (change_id,)).fetchone()["id"]

    def record_snapshot(self, *, hotel: str, offer: str, currency: str, sentence: str, read_at: str,
                        hotel_id: str, rows: Iterable[ValueRow], reading: Mapping | None = None) -> int:
        with self._db() as db:
            return self._insert(db, "snapshot", "saved", hotel, hotel_id, offer, currency, sentence, read_at, rows,
                                reading=reading)

    def _header(self, db, change_id):
        row = db.execute("SELECT * FROM changes WHERE id = ?", (change_id,)).fetchone()
        if row is None:
            raise LedgerError(f"장부에 {change_id}번 변경이 없습니다")
        kind = _kind_of(db, change_id) if self.kind is not None else None
        if kind is not None and kind != self.kind:
            raise LedgerError(f"{change_id}번은 {KIND_NAMES.get(kind, kind)}의 기록입니다 — 이 도우미는 "
                              f"{KIND_NAMES.get(self.kind, self.kind)}의 기록만 다룹니다")
        return row

    def _stamp(self) -> str:
        return self._now().isoformat(timespec="seconds")

    def _age(self, moment: str) -> timedelta:
        return self._now() - _moment(moment)

    def _status(self, header) -> str:
        """적용 중인데 IDLE 동안 아무 일이 없었으면 멈춘 것이다."""
        if header["status"] == "applying" and (header["active_at"] is None or self._age(header["active_at"]) > IDLE):
            return "stopped"
        return header["status"]

    def _cause(self, header, steps, halted: bool = False) -> str | None:
        """멈춘 까닭. 장부가 적용 중인데 멈춘 것이면 끊긴 것이다(실패한 저장이 그 앞에 있었어도 그 뒤 이어서 했다). 저장 뒤 ERP 가 다음
        저장을 하지 말라고 해 멈췄으면(`halted` — halts) halted 다."""
        if self._status(header) != "stopped":
            return None
        if halted and header["status"] == "stopped":
            return "halted"
        failed = [step for step in steps if step["status"] == "failed"]
        missed, unknown, cut_off, _halted = CAUSES
        if header["status"] == "applying" or not failed:
            return cut_off
        return unknown if any(step["unknown"] for step in failed) else missed

    @staticmethod
    def _mark_saved(db, change_id: int, index: int, note: str | None, stamp: str) -> None:
        """단계 하나를 저장됨으로 적는다. 그 값이 누구의 것이 됐는지는 적지 않는다 — 장부의 차례에서 셈한다(_chain)."""
        db.execute("UPDATE steps SET status = 'saved', finished_at = ?, note = ?, unknown = 0 WHERE change_id = ? AND idx = ?",
                   (stamp, note, change_id, index))

    def begin(self, change_id: int, steps: Sequence[StepPlan], request: Mapping | None = None, *, read_at: str) -> None:
        """적용 시작 — 저장 단계를 적고 단계가 쓰는 필드마다 단계 번호를 단다.

        단계가 쓰는 값은 미리보기 때 적은 줄(넣는 필드 · 넣는 값 · 비움)과 꼭 같아야 한다. 미리보기에 없던 값, 다른 값, 두 번
        쓰는 값, 그리고 미리보기가 넣는다고 보였는데 어느 단계도 쓰지 않는 값이 하나라도 있으면 시작하지 않는다.
        `read_at` 은 적용 직전에 읽어 미리보기 때 값과 같다고 본 읽은 값의 시각이다. 그 번호를 계산한 뒤에 IDLE 안에 읽은 값으로만
        시작한다(_check_fresh). 그 시각이 첫 활동이다. 시작한 때(장부의 시계)는 `begins` 에 적는다. 같은 단계로 다시 부르면
        아무것도 바꾸지 않는다. `request` 를 주면 미리보기 때 적은 요청과 같은 계산인지 본다.
        """
        encoded = [(step.kind, _body(step.body)) for step in steps]
        with self._db() as db:
            header = self._header(db, change_id)
            if header["kind"] == "snapshot":
                raise LedgerError("지금 상태 저장은 적용할 것이 없습니다")
            if header["status"] == "replaced":
                raise LedgerError(f"{change_id}번 미리보기는 다시 계산해 {self._replacer(db, change_id)}번으로 바뀌었습니다 — "
                                  "그 번호와 그 계산 파일로 적용합니다")
            if header["status"] == "empty":
                raise LedgerError(f"{change_id}번은 저장할 것이 없는 미리보기입니다 — 적용할 것이 없습니다")
            if request is not None and header["request"] is not None and json.loads(header["request"]) != dict(request):
                raise LedgerError(f"{change_id}번 변경의 요청과 다른 계산입니다. 미리보기를 다시 만들어 주세요")
            if header["status"] != "previewed":
                stored = [(row["kind"], row["body"]) for row in
                          db.execute("SELECT kind, body FROM steps WHERE change_id = ? ORDER BY idx", (change_id,))]
                if stored == encoded:
                    return
                raise LedgerError(f"{change_id}번 변경은 이미 다른 저장 단계로 적용을 시작했습니다")
            self._check_fresh(header, read_at)
            for index, step in enumerate(steps, 1):
                for write in step.writes:
                    row = db.execute(f"SELECT label, after, action, step FROM item_values WHERE change_id = ? AND {ROW}",
                                     (change_id, write.item_kind, write.item_key, write.field)).fetchone()
                    if row is None or row["action"] is None:
                        raise LedgerError(f"미리보기가 넣는다고 보이지 않은 값입니다: {step.label} · {write.field}")
                    if row["action"] != ("clear" if write.after is None else "set") or money(row["after"]) != write.after:
                        raise LedgerError(f"미리보기와 다른 값입니다: {row['label']} · {write.field} — 미리보기 "
                                          f"{'비움' if row['action'] == 'clear' else row['after']}, 저장 {money_text(write.after) or '비움'}")
                    if row["step"] is not None:
                        raise LedgerError(f"같은 값을 두 번 씁니다: {step.label} · {write.field}")
                    db.execute(f"UPDATE item_values SET step = ? WHERE change_id = ? AND {ROW}",
                               (index, change_id, write.item_kind, write.item_key, write.field))
                db.execute("INSERT INTO steps (change_id, idx, kind, label, body, status) VALUES (?, ?, ?, ?, ?, 'pending')",
                           (change_id, index, step.kind, step.label, _body(step.body)))
            left = db.execute("SELECT label, field FROM item_values WHERE change_id = ? AND action IS NOT NULL AND step IS NULL"
                              " ORDER BY rowid", (change_id,)).fetchall()
            if left:
                raise LedgerError(f"미리보기가 넣는다고 보인 값 {len(left)}개를 어느 저장 단계도 넣지 않습니다 — 처음 것: "
                                  f"{left[0]['label']} · {left[0]['field']}")
            stamp = self._stamp()
            db.execute("INSERT INTO begins (change_id, begun_at) VALUES (?, ?)", (change_id, stamp))
            db.execute("UPDATE changes SET status = 'applying', updated_at = ?, active_at = ? WHERE id = ?",
                       (stamp, read_at, change_id))

    def _check_fresh(self, header, read_at: str) -> None:
        """적용 직전에 읽은 값이 그 번호를 계산한 뒤에(_read_before), IDLE 안에 읽은 것이 아니면 거절한다."""
        if _read_before(read_at, header["read_at"], (header["created_at"],)) is not None:
            raise LedgerError(f"이 읽은 값({_when(read_at)})은 {header['id']}번을 계산한 때({_when(header['created_at'])}) 뒤에 읽은 것이 아닙니다 — "
                              "적용 직전에 다시 읽은 값이 아닙니다(미리보기의 읽은 값이거나 그보다 앞선 것, 또는 앞선 읽기 폴더의 답을 "
                              "다시 쓴 읽기). 같은 범위를 새 읽기 폴더에 다시 읽고 begin 을 부릅니다")
        if self._age(read_at) > IDLE:
            raise LedgerError(f"적용 직전에 읽은 값이 {_minutes(self._age(read_at))}분 전 것입니다 — "
                              f"{_minutes(IDLE)}분 안에 읽은 값으로만 시작합니다. 다시 읽고 begin 을 부릅니다")

    def begin_fresh(self, change_id: int, steps: Sequence[StepPlan], then: Reading, now: Reading, *, read_at: str,
                    request: Mapping | None = None) -> tuple[Difference, ...]:
        """적용 직전에 다시 읽고 시작하기(결정 18) — 방금 읽은 값(`now`, 읽은 시각 `read_at`)이 그 번호를 계산한 뒤에 IDLE 안에 읽은
        것인지 먼저 보고(아니면 견주지 않고 거절한다), 그 번호의 계산이 바탕으로 삼은 읽은 값(`then`)과 견주어 한 항목이라도(딸린
        칸까지) 다르면 아무것도 시작하지 않고 다른 항목들을 돌려준다. 같으면 begin 하고 빈 것을 돌려준다. 이미 적용을 시작한 번호는
        견주지 않고 begin 에 넘긴다 — 같은 단계로 다시 부르면 아무것도 바꾸지 않는다."""
        with self._db() as db:
            header = self._header(db, change_id)
        if header["status"] == "previewed":
            self._check_fresh(header, read_at)
            differences = stale_items(then, now)
            if differences:
                return differences
        self.begin(change_id, steps, request, read_at=read_at)
        return ()

    def record_step(self, change_id: int, index: int, saved: bool, note: str | None = None, unknown: bool = False,
                    halt: str | None = None) -> str:
        """저장 한 번이 끝날 때마다 부른다. 새 상태를 돌려준다.

        `halt` 는 저장은 됐는데 ERP 가 다음 저장을 하지 말라고 한 까닭이다(시즌 창의 「공급 통화 없음」 띠) — 그 단계를 저장됨으로 적고
        `halts` 에 까닭을 적어, 남은 저장이 있으면 변경을 바로 멈춘다(적용 중으로 15분을 기다리지 않는다). 남은 저장이 없으면 다
        적용한 것이다. 그 밖의 저장(halt 없음)은 전과 같다.

        `unknown` 은 저장 단추는 눌렸고 저장됐는지 모르는 단계다 — failed 로 적고 표시를 단다(다시 읽어 가린다). 저장 결과는
        활동이다. 다만 이미 멈춘 변경(실패했거나 IDLE 동안 아무 일이 없던)에 적힌 저장은 적기만 하고 변경을 다시 살리지
        않는다 — 끊긴 뒤의 저장이 낡은 값으로 이어 간 것일 수 있어, 다시 읽어 check 를 거쳐야 남은 저장을 낸다."""
        with self._db() as db:
            header = self._header(db, change_id)
            step = db.execute("SELECT * FROM steps WHERE change_id = ? AND idx = ?", (change_id, index)).fetchone()
            if step is None:
                raise LedgerError(f"{change_id}번 변경에 {index}번째 저장이 없습니다")
            if step["status"] == "saved":
                return self._status(header)
            stamp, alive = self._stamp(), self._status(header) == "applying"
            db.execute("UPDATE checks SET spent = 1 WHERE change_id = ? AND spent = 0", (change_id,))   # 그 check 는 이 저장을 모른다
            if saved:
                self._mark_saved(db, change_id, index, note, stamp)
            else:
                db.execute("UPDATE steps SET status = 'failed', finished_at = ?, note = ?, unknown = ? WHERE change_id = ? AND idx = ?",
                           (stamp, note, int(unknown), change_id, index))
            left = db.execute("SELECT COUNT(*) FROM steps WHERE change_id = ? AND status != 'saved'",
                              (change_id,)).fetchone()[0]
            status = "stopped" if not saved else "applied" if left == 0 else header["status"]
            if saved and halt:
                db.execute("INSERT INTO halts (change_id, idx, note) VALUES (?, ?, ?) ON CONFLICT DO NOTHING", (change_id, index, halt))
                if left:
                    status = "stopped"
            db.execute("UPDATE changes SET status = ?, updated_at = ?, applied_at = COALESCE(applied_at, ?),"
                       " active_at = CASE WHEN ? THEN ? ELSE active_at END WHERE id = ?",
                       (status, stamp, stamp if status == "applied" else None, saved and alive, stamp, change_id))
            return self._status(self._header(db, change_id))

    def issue(self, change_id: int, index: int, read_at: str, until_ms: int) -> bool:
        """저장 하나의 부를 값을 그 읽은 값(`read_at`)으로 냈다고 적는다(`until_ms` — 누를 수 있는 마지막 때). 같은 읽은 값으로 이미
        냈으면 아무것도 적지 않고 False 다(한 읽은 값에 부를 값은 하나)."""
        with self._db() as db:
            self._header(db, change_id)
            found = db.execute("SELECT 1 FROM issues WHERE change_id = ? AND idx = ? AND read_at = ?", (change_id, index, read_at)).fetchone()
            if found:
                return False
            db.execute("INSERT INTO issues (change_id, idx, read_at, until_ms, issued_at) VALUES (?, ?, ?, ?, ?)",
                       (change_id, index, read_at, until_ms, self._stamp()))
            return True

    def issued(self, change_id: int, index: int | None = None) -> list[tuple[int, str, int, str]]:
        """낸 부를 값들 — (단계, 읽은 값의 시각, 누를 수 있는 마지막 때, 낸 때), 낸 차례대로."""
        with self._db() as db:
            rows = db.execute("SELECT idx, read_at, until_ms, issued_at FROM issues WHERE change_id = ?"
                              + ("" if index is None else " AND idx = ?") + " ORDER BY rowid",
                              (change_id,) if index is None else (change_id, index)).fetchall()
        return [(row["idx"], row["read_at"], row["until_ms"], row["issued_at"]) for row in rows]

    @staticmethod
    def _written(db, change_id):
        return db.execute(
            "SELECT item_values.* FROM item_values JOIN steps ON steps.change_id = item_values.change_id"
            " AND steps.idx = item_values.step WHERE item_values.change_id = ? AND steps.status = 'saved' ORDER BY item_values.rowid",
            (change_id,)).fetchall()

    def _ours(self, db, header) -> list:
        """이 번호가 저장한 줄 가운데 지금 되돌려져 있지 않은 것(장부의 차례에서 셈한다 — _chain). 뒤 기록이나 도우미 밖이 덮었을
        뿐인 줄은 남는다(되돌리기가 지금 값으로 가려 그대로 두는 칸과 그 까닭으로 보인다)."""
        statuses = self._chain(db, header["hotel_id"], header["offer"]).of(header["id"])
        return [row for row in self._written(db, header["id"])
                if statuses[(row["item_kind"], row["item_key"])][row["field"]].undone_by is None]

    def _chain(self, db, hotel_id: str | None = None, offer: str | None = None, saved: Iterable[int] = ()) -> Alive:
        """장부의 저장된 값들을 차례로 따라 셈한 살아 있는 값(change_core.alive.walk) — `hotel_id` · `offer` 를 주면 그 호텔 · 오퍼만.
        지금 상태 저장은 저장 상태로 되돌리기가 가리키는 것과 `saved` 로 준 것만 싣는다(그 밖의 저장은 셈을 바꾸지 않는다)."""
        where, params = ("", ()) if hotel_id is None else (" AND changes.hotel_id = ? AND changes.offer = ?", (hotel_id, offer))
        rows = db.execute(
            "SELECT item_values.change_id, item_values.item_kind, item_values.item_key, item_values.field, item_values.state,"
            " item_values.before, item_values.after, steps.idx, steps.finished_at, changes.kind, changes.reverses,"
            " changes.request, changes.hotel_id, changes.offer FROM item_values"
            " JOIN steps ON steps.change_id = item_values.change_id AND steps.idx = item_values.step AND steps.status = 'saved'"
            " JOIN changes ON changes.id = item_values.change_id WHERE item_values.action IS NOT NULL" + where
            + " ORDER BY item_values.rowid", params).fetchall()
        restores: dict[int, int | None] = {}
        writes = []
        for row in rows:
            if row["change_id"] not in restores:
                restores[row["change_id"]] = _restored(row["kind"], row["request"])
            writes.append(Write((_moment(row["finished_at"]), row["change_id"], row["idx"]), row["change_id"],
                                (row["hotel_id"], row["offer"], row["item_kind"], row["item_key"], row["field"]),
                                money(row["before"]), row["state"] == "missing", money(row["after"]),
                                row["reverses"] if row["kind"] == "rollback" else None, restores[row["change_id"]]))
        wanted = sorted({*saved, *(number for number in restores.values() if number is not None)})
        snapshots = db.execute(
            "SELECT item_values.change_id, item_values.item_kind, item_values.item_key, item_values.field, item_values.state,"
            " item_values.before, changes.created_at, changes.hotel_id, changes.offer FROM item_values"
            " JOIN changes ON changes.id = item_values.change_id WHERE changes.kind = 'snapshot'"
            f" AND changes.id IN ({', '.join('?' * len(wanted))})", wanted).fetchall() if wanted else []
        return walk(writes, [Saved((_moment(row["created_at"]), row["change_id"], 0), row["change_id"],
                                   (row["hotel_id"], row["offer"], row["item_kind"], row["item_key"], row["field"]),
                                   money(row["before"]), row["state"] == "missing") for row in snapshots])

    def verify(self, change_id: int, reading: Reading, skippable: Callable[[tuple[str, ...]], bool] | None = None) -> list[Mismatch]:
        """저장된 값을 방금 읽은 값과 견준다. 맞는 값은 확인됨으로 적고, 다른 값을 돌려준다. 되돌린 값은 보지 않는다. ERP 가 넣지 않을
        수 있는 줄(`skippable` — check 와 같은 뜻, left_out)이 전 값 그대로면 `left_out` 을 달아 돌려준다(다른 값이 아니다)."""
        mismatches = []
        with self._db() as db:
            for row in self._ours(db, self._header(db, change_id)):
                item = reading.get((row["item_kind"], row["item_key"]))
                seen = None if item is None else item.fields.get(row["field"])
                after = money(row["after"])
                held = item is not None and item.state != "missing" and seen == after
                if not held:
                    mismatches.append(Mismatch(row["item_kind"], row["item_key"], row["label"], row["field"], after, seen,
                                               None if item is None else item.state,
                                               left_out(_marks(row), _field_seen(row, item), skippable)))
                db.execute(f"UPDATE item_values SET verified = ?, seen = ?, seen_state = ? WHERE change_id = ? AND {ROW}",
                           (int(held), money_text(seen), None if item is None else item.state, change_id,
                            row["item_kind"], row["item_key"], row["field"]))
            stamp = self._stamp()
            db.execute("UPDATE changes SET verified_at = ?, updated_at = ? WHERE id = ?", (stamp, stamp, change_id))
        return mismatches

    def untouched(self, change_id: int, reading: Reading, unit: Callable[[str], str] | None = None) -> list[Mismatch]:
        """저장한 항목의 넣지 않은 필드 가운데 방금 읽은 값이 미리보기 때 값과 다른 것(`after` 는 그대로여야 할 값). 기록 하나를
        통째로 다시 저장하는 화면(부가옵션 가격 줄 · 부과금 …)에서 저장이 다른 필드를 건드리지 않았는지 본다. 장부에는 적지 않는다.
        `unit(항목 키)` 는 저장 한 번이 다시 쓰는 단위다(부과금은 시간대 · 연령별 단가까지 부과금 하나) — 주지 않으면 항목 하나다."""
        unit = unit or (lambda key: key)
        with self._db() as db:
            self._header(db, change_id)
            saved = {(row["item_kind"], unit(row["item_key"])) for row in self._written(db, change_id)}
            rows = db.execute("SELECT * FROM item_values WHERE change_id = ? AND action IS NULL AND state != 'missing'"
                              " ORDER BY rowid", (change_id,)).fetchall()
        moved = []
        for row in rows:
            if (row["item_kind"], unit(row["item_key"])) not in saved:
                continue
            item = reading.get((row["item_kind"], row["item_key"]))
            seen, before = None if item is None else item.fields.get(row["field"]), money(row["before"])
            if item is None or item.state == "missing" or seen != before:
                moved.append(Mismatch(row["item_kind"], row["item_key"], row["label"], row["field"], before, seen,
                                      None if item is None else item.state))
        return moved

    def check(self, change_id: int, now: Reading, then: Reading, read_at: str,
              unit: Callable[[str], str] | None = None, skippable: Callable[[tuple[str, ...]], bool] | None = None,
              warn: str | None = None) -> CheckReport:
        """이 변경에 무슨 일이 있었는지 — 저장마다 방금 읽은 값(`now`, 읽은 시각 `read_at`)이 말하는 것과, 남은 저장을 계획대로
        해도 되는지, 어디까지 됐고 왜 멈췄는지.

        읽은 값은 장부가 그 번호에 마지막으로 적은 것(계산 · 저장 결과) 뒤에 읽은 것이어야 한다(_read_before) — 아니면 아무것도
        가리거나 적지 않고 거절한다(적용 직전의 읽은 값은 그 뒤의 저장을 모른다).

        「모름」(눌렸고 저장됐는지 모르는 단계)은 읽은 값이 넣은 값 그대로면 저장됨으로, 전 값 그대로면 저장 안 됨으로 가려 적는다.
        저장 안 됨으로 적힌 단계 · 아직 적지 않은 단계도 칸이 모두 넣은 값이면 저장됨으로 적는다(누른 답을 잃었다). ERP 가 넣지 않을
        수 있는 줄(`skippable` — left_out)은 확인과 같은 뜻으로 가린다. 남은 저장을 해도 되는 것은 — 저장된 단계가 모두 그대로이고, 남은 단계가 모두 저장 안 됨이며, 남은 단계의 칸이 그 계산이
        바탕으로 삼은 읽은 값(`then`)과 모두 같고, 읽은 값이 IDLE 안의 것일 때뿐이다. 그러면 변경을 적용 중으로 두고 그 읽은
        값의 시각을 활동으로 적는다(IDLE 안이면 calls 가 남은 단계를 낸다). 아니면 멈춘 변경으로 둔다. `unit` 은 untouched 와 같다 —
        남은 저장의 칸은 그 저장이 다시 쓰는 단위 전부를 본다. `warn` 은 다시 읽어 안, ERP 가 다음 저장을 하지 말라고 하는 까닭이다(시즌
        목록의 「공급 통화 없음」 띠 — 「모름」이던 저장이 뒤에 그 띠와 함께 끝났다): 저장된 마지막 단계에 그 까닭을 적어(halts) 이어 가지
        않는다(record-result 가 저장 답의 경고로 멈추는 것과 같다).
        """
        unit = unit or (lambda key: key)
        with self._db() as db:
            header = self._header(db, change_id)
            steps = db.execute("SELECT * FROM steps WHERE change_id = ? ORDER BY idx", (change_id,)).fetchall()
            if not steps:
                raise LedgerError(f"{change_id}번 변경은 아직 적용을 시작하지 않았습니다(begin)")
            finished = [step["finished_at"] for step in steps if step["finished_at"]]
            since = _read_before(read_at, header["read_at"], (header["created_at"], *finished))
            if since is not None:
                what = "저장 결과" if since in finished else "계산"
                raise LedgerError(f"이 읽은 값({_when(read_at)})은 장부가 {change_id}번에 마지막으로 적은 {what}({_when(since)}) 뒤에 "
                                  "읽은 것이 아닙니다 — 그 뒤의 ERP 를 모르는 읽은 값이라 저장마다 됐는지 가리지 못합니다. 같은 범위를 새 "
                                  "읽기 폴더에 다시 읽고 check 를 부릅니다")
            rows = {step["idx"]: db.execute("SELECT * FROM item_values WHERE change_id = ? AND step = ? ORDER BY rowid",
                                            (change_id, step["idx"])).fetchall() for step in steps}
            halt = db.execute("SELECT idx, note FROM halts WHERE change_id = ? ORDER BY idx LIMIT 1", (change_id,)).fetchone()
        cause = self._cause(header, steps, halt is not None)
        note = next((step["note"] for step in steps if step["status"] == "failed"), None) if cause in ("failed", "unknown") else None
        if cause == "halted":
            note = halt["note"]
        seen_steps, settle, moved_items = [], [], {}
        for step in steps:
            found = [(row, _field_seen(row, now.get((row["item_kind"], row["item_key"])))) for row in rows[step["idx"]]]
            kinds = {kind for row, kind in found if not left_out(_marks(row), kind, skippable)} or {kind for _row, kind in found}
            seen = {frozenset({"after"}): "saved", frozenset({"before"}): "not_saved",
                    frozenset({"after", "before"}): "mixed"}.get(frozenset(kinds), "changed")
            state = "unknown" if step["status"] == "failed" and step["unknown"] else step["status"]
            if state == "saved" and seen != "saved":
                seen = "changed"
            # 「모름」은 읽은 값대로 가린다. 저장 안 됨 · 아직 적지 않은 저장도 칸이 모두 넣은 값이면 저장된 것이다(답을 잃은 누름)
            settled = (seen if state == "unknown" and seen in ("saved", "not_saved")
                       else "saved" if state in ("failed", "pending") and seen == "saved" else None)
            if settled:
                settle.append((step["idx"], settled))
            done = state == "saved" or settled == "saved"
            units = {(row["item_kind"], unit(row["item_key"])) for row in rows[step["idx"]]}
            items = {(kind, key) for kind, key in set(then) | set(now) if (kind, unit(key)) in units}
            items |= {(row["item_kind"], row["item_key"]) for row in rows[step["idx"]]}
            differ = [] if done else sorted(item for item in items if not _same_item(then.get(item), now.get(item)))
            moved_items.update((item, now.get(item)) for item in differ)
            seen_steps.append(StepSeen(step["idx"], step["label"], state, seen, settled, len(differ)))
        new_halt = None
        if warn and halt is None:   # 다시 읽어 안 「공급 통화 없음」 — 저장된 마지막 단계 뒤에 멈춘 것으로 적는다
            done_steps = [step for step in seen_steps if step.ledger == "saved" or step.settled == "saved"]
            if done_steps:
                new_halt = halt = {"idx": done_steps[-1].index, "note": warn}
                cause, note = "halted", warn
        why, remaining = [], []
        for step in seen_steps:
            name = f"{step.index}번째 저장({step.label})"
            if step.ledger == "saved" or step.settled == "saved":
                if step.seen != "saved":
                    why.append(f"{name}은 저장됐지만 그 뒤 칸이 다른 값이 됐습니다")
                continue
            remaining.append(step.index)
            if step.ledger == "unknown" and not step.settled:
                why.append(f"{name}은 저장됐는지 가리지 못했습니다 — 칸이 {'일부만 넣은 값' if step.seen == 'mixed' else '넣은 값도 전 값도 아닌 값'}입니다")
            elif step.seen == "mixed":
                why.append(f"{name}의 칸이 일부만 넣으려던 값입니다")
            elif step.seen == "changed" and not step.moved:
                why.append(f"{name}의 칸이 넣으려던 값도 그 전 값도 아닙니다")
            if step.moved:   # 넣으려던 값도 그 전 값도 아닌 칸은 미리보기 때 읽은 값과 다른 칸이다 — 한 번만 말한다
                why.append(f"{name}의 칸 {step.moved}개가 미리보기 때 읽은 값과 다릅니다")
        if halt is not None and remaining:   # ERP 가 다음 저장을 하지 말라고 했다 — 다시 읽어도 이어 가지 않는다
            why.append(f"{halt['idx']}번째 저장 뒤 ERP 가 다음 저장을 하지 말라고 했습니다({halt['note']}) — 이어서 하지 않습니다")
        elif warn and remaining:
            why.append(f"ERP 가 이 호텔에는 다음 저장을 하지 말라고 합니다({warn}) — 이어서 하지 않습니다")
        if remaining and self._age(read_at) > IDLE:
            why.append(f"읽은 값이 {_minutes(self._age(read_at))}분 전 것입니다 — {_minutes(IDLE)}분 안에 읽은 값으로만 이어 가니 "
                       "다시 읽습니다")
        can_continue = bool(remaining) and not why
        stamp = self._stamp()
        with self._db() as db:
            if new_halt is not None:
                db.execute("INSERT INTO halts (change_id, idx, note) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                           (change_id, new_halt["idx"], new_halt["note"]))
            for index, settled in settle:
                if settled == "saved":
                    self._mark_saved(db, change_id, index, "다시 읽어 저장된 것을 확인했습니다", stamp)
                else:
                    db.execute("UPDATE steps SET unknown = 0, note = ? WHERE change_id = ? AND idx = ?",
                               ("다시 읽어 저장되지 않은 것을 확인했습니다", change_id, index))
            status = "applied" if not remaining else "applying" if can_continue else "stopped"
            db.execute("UPDATE changes SET status = ?, updated_at = ?, applied_at = COALESCE(applied_at, ?),"
                       " active_at = CASE WHEN ? THEN ? ELSE active_at END WHERE id = ?",
                       (status, stamp, stamp if status == "applied" else None, can_continue, read_at, change_id))
            db.execute("INSERT INTO checks (change_id, checked_at, read_at, can_continue, cause, why, moved) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (change_id, stamp, read_at, int(can_continue), cause, _body(why),
                        _body([dict(kind=kind, key=key, now=encode_state(state)) for (kind, key), state in moved_items.items()])))
        saved = [step for step in seen_steps if step.ledger == "saved" or step.settled == "saved"]
        return CheckReport(header["id"], status, tuple(seen_steps), tuple(remaining), can_continue, tuple(why), cause,
                           saved[-1] if saved else None,
                           next((step for step in seen_steps if step.index == remaining[0]), None) if remaining else None, note)

    def recorded_change(self, change_id: int) -> RecordedChange:
        """되돌리기 계산 · 견주기의 재료 — 저장이 끝났고 아직 되돌리지 않은 값이 있는 항목만(장부의 차례에서 셈한다 — _chain).
        항목마다 그 기록의 값이 살아 있지 않은 필드는 지금 그 칸을 쥔 뒤 기록을 단다(`held` — 되돌리기는 그 칸을 그대로 둔다).
        되돌리기 · 저장 상태로 되돌리기도 바꾸기처럼 재료를 낸다(되돌린 기록 · 저장 번호를 함께)."""
        with self._db() as db:
            header = self._header(db, change_id)
            if header["kind"] == "snapshot":
                raise LedgerError(_saved_state(change_id))
            alive = self._chain(db, header["hotel_id"], header["offer"])
            statuses = alive.of(change_id)
            ours: dict[tuple[str, str], dict] = {}
            held: dict[tuple[str, str], dict] = {}
            for row in self._written(db, change_id):
                item, status = (row["item_kind"], row["item_key"]), statuses[(row["item_kind"], row["item_key"])][row["field"]]
                if status.undone_by is not None:
                    continue
                ours.setdefault(item, {})[row["field"]] = money(row["after"])
                holder = alive.holder.get((header["hotel_id"], header["offer"], *item, row["field"]))
                if not status.live and holder not in (None, change_id):
                    held.setdefault(item, {})[row["field"]] = holder
            items = []
            for (kind, key), written in ours.items():
                rows = db.execute("SELECT * FROM item_values WHERE change_id = ? AND item_kind = ? AND item_key = ?"
                                  " ORDER BY rowid", (change_id, kind, key)).fetchall()
                items.append(RecordedItem(kind, key, rows[0]["label"], rows[0]["state"],
                                          {row["field"]: money(row["before"]) for row in rows}, written, held.get((kind, key), {})))
        return RecordedChange(header["id"], header["kind"], header["hotel"], header["offer"], header["currency"],
                              header["sentence"], header["read_at"], header["applied_at"], tuple(items), header["hotel_id"],
                              header["reverses"], _restored(header["kind"], header["request"]))

    def recorded_snapshot(self, change_id: int) -> RecordedChange:
        """저장해 둔 상태로 돌리기의 재료 — snapshot 에 적은 항목 전부와 그때 값(넣은 값은 없다)."""
        with self._db() as db:
            header = self._header(db, change_id)
            if header["kind"] != "snapshot":
                raise LedgerError(f"{change_id}번은 저장해 둔 상태가 아닙니다(지금 상태 저장으로 적은 것만 됩니다)")
            grouped: dict[tuple[str, str], list] = {}
            for row in db.execute("SELECT * FROM item_values WHERE change_id = ? ORDER BY rowid", (change_id,)):
                grouped.setdefault((row["item_kind"], row["item_key"]), []).append(row)
        items = tuple(RecordedItem(kind, key, rows[0]["label"], rows[0]["state"],
                                   {row["field"]: money(row["before"]) for row in rows}, {})
                      for (kind, key), rows in grouped.items())
        return RecordedChange(header["id"], header["kind"], header["hotel"], header["offer"], header["currency"],
                              header["sentence"], header["read_at"], header["applied_at"], items, header["hotel_id"])

    def later_writes(self, change_id: int) -> dict[tuple[str, str], list[LaterWrite]]:
        """이 기록 뒤에 같은 호텔·오퍼에 이 장부가 저장한 값 — 항목마다, 변경마다 하나씩, 저장한 차례대로. 「뒤」는 번호가 아니라
        _chain 과 같은 차례다(저장한 시각, 같은 초면 번호, 단계): 지금 상태 저장은 적은 때 뒤, 변경은 그 항목을 저장한 단계 뒤(그
        항목을 저장하지 않았으면 계산한 때 뒤). 그래서 미리보기와 그 적용 사이에 적은 지금 상태 저장 뒤의 그 적용도 「뒤」다."""
        grouped: dict[tuple[str, str, int], dict] = {}
        with self._db() as db:
            header = self._header(db, change_id)
            rows = db.execute(
                "SELECT item_values.*, steps.finished_at, changes.sentence FROM item_values"
                " JOIN steps ON steps.change_id = item_values.change_id AND steps.idx = item_values.step"
                " JOIN changes ON changes.id = item_values.change_id"
                " WHERE steps.status = 'saved' AND changes.kind != 'snapshot'"
                " AND changes.hotel_id = ? AND changes.offer = ? ORDER BY item_values.rowid",
                (header["hotel_id"], header["offer"])).fetchall()
        order = (lambda row: (_moment(row["finished_at"]), row["change_id"], row["step"]))   # noqa: E731
        floor = (_moment(header["created_at"]), change_id, 0)
        own: dict[tuple[str, str], tuple] = {}
        for row in rows:
            if row["change_id"] == change_id:
                item = (row["item_kind"], row["item_key"])
                own[item] = max(own.get(item, floor), order(row))
        rows = [row for row in rows if row["change_id"] != change_id and order(row) > own.get((row["item_kind"], row["item_key"]), floor)]
        for row in sorted(rows, key=order):
            entry = grouped.setdefault((row["item_kind"], row["item_key"], row["change_id"]),
                                       dict(at=row["finished_at"], sentence=row["sentence"], written={}))
            entry["at"] = max(entry["at"], row["finished_at"])
            entry["written"][row["field"]] = money(row["after"])
        found: dict[tuple[str, str], list[LaterWrite]] = {}
        for (kind, key, later_id), entry in grouped.items():
            found.setdefault((kind, key), []).append(LaterWrite(later_id, entry["at"], entry["sentence"], entry["written"]))
        return found

    def change(self, change_id: int) -> ChangeRecord:
        with self._db() as db:
            header = self._header(db, change_id)
            steps = tuple(StepRecord(row["idx"], row["kind"], row["label"], json.loads(row["body"]), row["status"],
                                     row["finished_at"], row["note"], bool(row["unknown"]))
                          for row in db.execute("SELECT * FROM steps WHERE change_id = ? ORDER BY idx", (change_id,)))
            saved = {step.index for step in steps if step.status == "saved"}
            now = self._chain(db, header["hotel_id"], header["offer"]).of(change_id)
            rows = tuple(
                RowRecord(row["item_kind"], row["item_key"], row["label"], row["field"], row["state"], money(row["before"]),
                          money(row["after"]), row["action"], row["step"], row["step"] in saved, bool(row["verified"]),
                          money(row["seen"]), row["seen_state"], getattr(status, "undone_by", None), row["verdict"],
                          tuple(mark for mark in row["marks"].split(",") if mark), row["choice"], row["said"],
                          getattr(status, "redone", None), getattr(status, "live", False))
                for row in db.execute("SELECT * FROM item_values WHERE change_id = ? ORDER BY rowid", (change_id,))
                for status in [now.get((row["item_kind"], row["item_key"]), {}).get(row["field"])])
            last = db.execute("SELECT * FROM checks WHERE change_id = ? AND spent = 0 ORDER BY rowid DESC LIMIT 1",
                              (change_id,)).fetchone()
            unused = db.execute("SELECT choices FROM unused_choices WHERE change_id = ?", (change_id,)).fetchone()
            halt = db.execute("SELECT note FROM halts WHERE change_id = ? ORDER BY idx LIMIT 1", (change_id,)).fetchone()
        cause = self._cause(header, [dict(status=step.status, unknown=step.unknown) for step in steps], halt is not None)
        status = self._status(header)
        checked = None
        if last is not None and (status == "applying" if last["can_continue"] else status == "stopped"):
            checked = Checked(last["read_at"], bool(last["can_continue"]), last["cause"], tuple(json.loads(last["why"])),
                              {(item["kind"], item["key"]): decode_state(item["now"]) for item in json.loads(last["moved"])})
        return ChangeRecord(header["id"], header["kind"], status, header["hotel"], header["hotel_id"],
                            header["offer"], header["currency"], header["sentence"], header["read_at"], header["created_at"],
                            header["applied_at"], header["verified_at"], header["reverses"],
                            None if header["request"] is None else json.loads(header["request"]), steps, rows, cause,
                            header["replaces"], checked, self._stamp(), tuple(json.loads(unused["choices"])) if unused else (),
                            None if halt is None else halt["note"])

    def reading(self, change_id: int) -> dict:
        """그 번호의 계산이 바탕으로 삼은 읽은 값(적을 때 준 JSON 그대로). 적지 않은 번호면 거절한다."""
        with self._db() as db:
            header = self._header(db, change_id)
        if header["reading"] is None:
            raise LedgerError(f"{change_id}번에는 적어 둔 읽은 값이 없습니다 — 범위를 다시 정해 읽어야 합니다")
        return json.loads(header["reading"])

    def list_changes(self, change_id: int | None = None) -> list[dict]:
        """장부의 번호마다 한 줄(새것부터, `change_id` 를 주면 그 번호만, 종류로 열었으면 그 종류의 번호와 종류 없는 번호만).
        `item_kind` 는 그 번호의 종류(`_kind_of`). 저장한 항목이 뒤의 되돌리기로 모두 되돌아갔으면 상태는 `rolled_back`, 일부면
        `partly_rolled_back` 이다 — 되돌린 변경이 살아 있는 것처럼 보이지 않는다. 수는 장부의 차례에서 셈한다(_chain, _tally):
        `written` 저장한 항목 · `rolled_back` 그 가운데 되돌린 항목과 `undone_by` 되돌린 번호들 · `redone` 되돌렸다가 다시 살린 항목과
        `redone_by` 그 번호들(되돌린 · 다시 살린) · `live` 넣은 값이 모두 살아 있는 항목(나머지는 뒤 기록이 덮었다).
        `steps` · `saved_steps` 는 저장 단계 수와 그중 저장된 수, `request` 는 적어 둔 요청(없으면 None),
        `begun_at` 은 적용을 시작한 때(`begins` — 시작하지 않았거나 그 표를 두기 전에 시작한 번호는 None).
        `replaced_by` 는 이 미리보기를 다시 계산해 바꾼 번호(`replaces` 가 이 번호인 것 — 없으면 None).
        `planned` 는 적힌 항목 가운데 저장이 값을 넣는(넣을) 항목 수다 — 안 바꾸기로 고른 항목 · 적용할 수 없는 항목은 들지 않는다."""
        item = "item_values.item_kind || '|' || item_values.item_key"
        where, params = [], []
        if change_id is not None:
            where.append("changes.id = ?")
            params.append(change_id)
        with self._db() as db:
            rows = db.execute(
                f"SELECT changes.*, MIN(item_values.item_kind) AS item_kind, COUNT(DISTINCT {item}) AS items,"
                f" COUNT(DISTINCT CASE WHEN item_values.action IS NOT NULL THEN {item} END) AS planned,"
                " (SELECT COUNT(*) FROM steps AS s WHERE s.change_id = changes.id) AS step_count,"
                " (SELECT COUNT(*) FROM steps AS s WHERE s.change_id = changes.id AND s.status = 'saved') AS saved_steps,"
                " (SELECT begun_at FROM begins WHERE begins.change_id = changes.id) AS begun_at,"
                " (SELECT MIN(later.id) FROM changes AS later WHERE later.replaces = changes.id) AS replaced_by"
                " FROM changes LEFT JOIN item_values ON item_values.change_id = changes.id"
                + (" WHERE " + " AND ".join(where) if where else "") + " GROUP BY changes.id ORDER BY changes.id DESC",
                params).fetchall()
            kinds = {row["id"]: row["item_kind"] or _kind_of(db, row["id"]) for row in rows}
            header = rows[0] if change_id is not None and rows else None
            now = self._chain(db, *((header["hotel_id"], header["offer"]) if header is not None else ()))
        out = []
        for row in rows:
            if self.kind is not None and kinds[row["id"]] not in (self.kind, None):
                continue
            tally = _tally(now.of(row["id"]))
            out.append(dict(id=row["id"], kind=row["kind"], item_kind=kinds[row["id"]], status=self._listed_status(row, tally),
                            hotel=row["hotel"], hotel_id=row["hotel_id"], offer=row["offer"], currency=row["currency"],
                            sentence=row["sentence"], read_at=row["read_at"], created_at=row["created_at"],
                            begun_at=row["begun_at"], applied_at=row["applied_at"], verified_at=row["verified_at"],
                            reverses=row["reverses"], replaces=row["replaces"], replaced_by=row["replaced_by"],
                            items=row["items"], planned=row["planned"],
                            **tally, steps=row["step_count"], saved_steps=row["saved_steps"],
                            request=None if row["request"] is None else json.loads(row["request"])))
        return out

    def _listed_status(self, row, tally: Mapping) -> str:
        """목록의 상태 — 저장한 항목이 모두 되돌아갔으면 rolled_back, 일부면 partly_rolled_back, 아니면 장부의 상태."""
        if tally["written"] and tally["rolled_back"]:
            return "rolled_back" if tally["rolled_back"] >= tally["written"] else "partly_rolled_back"
        return self._status(row)

    def item_keys(self, item_kind: str, change_id: int | None = None) -> dict[int, list[str]]:
        """번호마다(`change_id` 를 주면 그 번호만) 그 번호에 적힌 그 종류의 항목 키들 — 목록 · check 가 무엇을 덮는 변경인지 말할 때 쓴다."""
        found: dict[int, list[str]] = {}
        with self._db() as db:
            for row in db.execute("SELECT DISTINCT change_id, item_key FROM item_values WHERE item_kind = ?"
                                  + ("" if change_id is None else " AND change_id = ?"),
                                  (item_kind,) if change_id is None else (item_kind, change_id)):
                found.setdefault(row["change_id"], []).append(row["item_key"])
        return found

    def undone(self, change_id: int) -> list[dict]:
        """이 변경의 저장한 값을 되돌린 기록마다(지금 되돌려져 있는 것만 — 장부의 차례에서 셈한다) — 번호 · 요청 문장 · 적용 시각 ·
        되돌린 항목들(종류, 키)."""
        grouped: dict[int, dict] = {}
        with self._db() as db:
            header = self._header(db, change_id)
            now = self._chain(db, header["hotel_id"], header["offer"]).of(change_id)
            for row in self._written(db, change_id):
                by = now[(row["item_kind"], row["item_key"])][row["field"]].undone_by
                if by is None:
                    continue
                if by not in grouped:
                    undoer = db.execute("SELECT sentence, applied_at FROM changes WHERE id = ?", (by,)).fetchone()
                    grouped[by] = dict(change_id=by, sentence=undoer["sentence"], applied_at=undoer["applied_at"], items={})
                grouped[by]["items"][(row["item_kind"], row["item_key"])] = None
        return [dict(entry, items=list(entry["items"])) for _by, entry in sorted(grouped.items())]

    def held_at(self, snapshot_id: int) -> dict[tuple[str, str], int]:
        """지금 상태 저장을 적을 때 그 항목에 이 장부가 넣은 값이 살아 있었으면 그 값을 넣은 기록(필드마다 마지막으로 넣은 기록 가운데
        가장 나중 번호) — 견주기의 「날짜별로 바꿔 둔 칸」. 저장 값이 장부가 아는 값과 다르면(도우미 밖에서 바뀜) 싣지 않는다."""
        with self._db() as db:
            header = self._header(db, snapshot_id)
            if header["kind"] != "snapshot":
                raise LedgerError(f"{snapshot_id}번은 저장해 둔 상태가 아닙니다(지금 상태 저장으로 적은 것만 됩니다)")
            now = self._chain(db, header["hotel_id"], header["offer"], saved=(snapshot_id,))
        found: dict[tuple[str, str], int] = {}
        for (record, cell), writer in now.held.items():
            if record == snapshot_id:
                found[(cell[2], cell[3])] = max(found.get((cell[2], cell[3]), writer), writer)
        return found
