"""담당자 PC 의 변경 장부(SQLite 하나). 지우는 일은 없다.

자리는 어느 폴더에서 Claude 를 열어도 같은 한 곳이다: `~/Documents/어딩 Stay 가격 변경 기록/가격장부.sqlite3`.
환경 변수 `STAY_PRICE_LEDGER_DIR` 로 다른 폴더를 줄 수 있다(시험은 임시 폴더를 쓴다). 가격·부과금·프로모션·부가옵션
도우미가 모두 이 장부 하나에 적는다.

    meta         schema_version — 이 코드보다 새 판이 만든 장부는 열지 않는다
    changes      변경 한 번에 한 줄 — 종류(change / snapshot / rollback), 상태(previewed → applying → stopped / applied,
                 다시 계산해 새 번호로 바뀐 미리보기는 replaced — 새 번호의 `replaces` 가 그 번호다, 지금 상태 저장은 saved),
                 호텔(페이지가 알아본 번호와 이름), 요청 문장, 읽은 시각, 되돌리기면 되돌리는 변경 번호, 요청 원문(JSON),
                 그 번호의 계산이 바탕으로 삼은 읽은 값(JSON — 읽은 범위가 들어 있다), 마지막으로 이어 가도 된다고 본
                 때(`active_at` — begin 이 받아들인 읽은 값의 시각, 저장 결과를 적은 때, 이어서 해도 된다고 한 check 의
                 읽은 값의 시각)
    item_values  항목 하나의 필드 하나에 한 줄 — 항목 종류(`price_cell` …), 굳은 키, 이름, 필드, 그때 상태, 전 값, 후 값,
                 넣는 방법(set / clear, 넣지 않으면 비어 있음 — 미리보기 때 정해지고 begin 은 저장 단계가 이것과 같은지 본다),
                 판정 · 표시 · 빨간 줄에 고른 것, 몇 번째 저장인지, 다시 읽어 맞았는지와 읽은 값, 되돌린 되돌리기 번호
    steps        저장 한 번에 한 줄 — 단계 종류와 내용(JSON), 끝날 때마다 바로 적는다. `unknown` 은 저장 단추는 눌렸고
                 저장됐는지 모르는 단계(다시 읽어 가릴 때까지 failed 로 둔다)

snapshot 은 읽어서 적어 두기만 하므로 적는 순간 상태가 saved 다(적용한 것이 아니다 — 목록에서 적용된 변경과 갈린다).

도우미마다 자기 항목 종류로 장부를 연다(`Ledger(kind="price_cell")`). 그러면 목록에는 그 종류의 번호만 나오고, 다른 종류의 번호를
주면 어느 도우미의 기록인지 대며 거절한다. 번호의 종류는 그 번호에 적힌 항목 줄의 종류다(표의 모양은 그대로다).

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
from typing import Iterable, Iterator, Mapping, Sequence

from .items import Difference, Reading, stale_items
from .money import money, money_text
from .rollback import LaterWrite, RecordedChange, RecordedItem

LEDGER_ENV = "STAY_PRICE_LEDGER_DIR"
FOLDER_NAME = "어딩 Stay 가격 변경 기록"
DB_NAME = "가격장부.sqlite3"
SCHEMA_VERSION = 2
IDLE = timedelta(minutes=15)         # 적용 중인 변경이 이만큼 아무 일이 없으면 멈춘 것이다(끊긴 세션). 받아들이는 읽은 값도 이만큼 안이다
CAUSES = ("failed", "unknown", "cut_off")   # 멈춘 까닭 — 저장이 실패함 · 저장됐는지 모름 · 실패 없이 끊김
KIND_NAMES = {"price_cell": "가격 캘린더 도우미", "addon_price": "부가옵션 가격 도우미"}   # 항목 종류 → 그 기록을 쓰는 도우미(거절 문장)

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK (kind IN ('change', 'snapshot', 'rollback')),
  status TEXT NOT NULL CHECK (status IN ('previewed', 'applying', 'stopped', 'applied', 'replaced', 'saved')),
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
  rolled_back_by INTEGER REFERENCES changes(id),
  verdict TEXT,
  marks TEXT NOT NULL DEFAULT '',
  choice TEXT,
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


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _moment(text: str) -> datetime:
    moment = datetime.fromisoformat(text)
    return moment if moment.tzinfo else moment.astimezone()


def _minutes(span: timedelta) -> int:
    return int(span.total_seconds() // 60)


@dataclass(frozen=True)
class ValueRow:
    """미리보기 때 적는 한 줄 — 미리보기가 보인 그 항목의 그 필드. `after` 는 후 값(바뀌지 않는 필드는 None), `action` 은
    저장이 그 필드에 하는 일(`set` 넣음 · `clear` 비움 · None 넣지 않음), `choice` 는 그 항목의 빨간 줄에 고른 것.
    `begin` 은 저장 단계가 쓰는 값이 이 줄들과 꼭 같을 때만 시작한다."""
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


@dataclass(frozen=True)
class ChangeRecord:
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
    """`cause` 는 멈춘 까닭 — failed 저장이 실패함 · unknown 저장됐는지 모름 · cut_off 실패 없이 중간에 끊김(멈추지 않았으면
    None). `last_saved` · `next` 는 마지막으로 저장된 단계와 다음에 할 단계(없으면 None), `note` 는 멈춘 저장의 메모."""
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


def _absent(item) -> bool:
    return item is None or item.state == "missing"


def _field_seen(row, item) -> str:
    """장부의 한 줄(넣은 필드 하나)을 방금 읽은 항목으로 — after 넣은 값 · before 전 값 · other 그 밖."""
    seen = None if _absent(item) else item.fields.get(row["field"])
    if not _absent(item) and seen == money(row["after"]):
        return "after"
    if (row["state"] == "missing" and _absent(item)) or (row["state"] != "missing" and not _absent(item) and seen == money(row["before"])):
        return "before"
    return "other"


def _same_item(then, now) -> bool:
    return (_absent(then) and _absent(now)) or (not _absent(then) and then.same_as(now))


@dataclass(frozen=True)
class Mismatch:
    item_kind: str
    item_key: str
    label: str
    field: str
    after: Decimal | None
    seen: Decimal | None
    seen_state: str | None


def _body(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class Ledger:
    def __init__(self, path: Path | None = None, now=None, kind: str | None = None):
        """`now` 는 지금 시각을 주는 함수(시험이 시계를 옮겨 본다). 장부가 적는 시각과, 멈춤 · 읽은 값의 나이를 이것으로 셈한다.
        `kind` 를 주면 그 항목 종류의 장부로 연다 — 목록은 그 종류의 번호만, 다른 종류의 번호는 거절한다."""
        self.path = Path(path) if path else ledger_dir() / DB_NAME
        self._now = now or (lambda: datetime.now().astimezone())
        self.kind = kind
        with self._db() as db:
            has_meta = db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'").fetchone()
            found = db.execute("SELECT value FROM meta WHERE name = 'schema_version'").fetchone() if has_meta else None
            if found and int(found["value"]) > SCHEMA_VERSION:
                raise LedgerError(f"이 장부는 더 새 판 도우미가 만든 것입니다(장부 판 {found['value']}, 이 도우미는 "
                                  f"{SCHEMA_VERSION}). 도우미를 새로 받아 주세요")
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
            " choice) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(change_id, row.item_kind, row.item_key, row.label, row.field, row.state, money_text(row.before),
              money_text(row.after), row.action, row.verdict, ",".join(row.marks), row.choice) for row in rows])
        return change_id

    def record_preview(self, *, hotel: str, offer: str, currency: str, sentence: str, read_at: str,
                       hotel_id: str, rows: Iterable[ValueRow], request: Mapping | None = None,
                       reverses: int | None = None, reading: Mapping | None = None, replaces: int | None = None) -> int:
        """미리보기를 적는다. `reverses` 를 주면 그 변경을 되돌리는 변경(rollback)이다. `reading` 은 그 계산이 바탕으로 삼은
        읽은 값 — 적용 직전 낡음 확인과 다시 읽을 범위가 이것으로 정해진다.

        `replaces` 는 이 미리보기가 바꾸는 앞 미리보기 번호다(빨간 줄을 고른 뒤 · 그대로 둔 칸도 되돌릴 때 · 적용 직전에 값이 달라
        다시 계산함). 같은 것을 하는(`_acts` — 가격 바꾸기 · 같은 변경 되돌리기 · 같은 저장 상태로 되돌리기) 같은 호텔 · 오퍼의,
        아직 적용을 시작하지 않은 미리보기여야 하고, 그 번호는 `replaced` 가 되어 begin 이 받지 않는다."""
        kind = "rollback" if reverses is not None else "change"
        with self._db() as db:
            if reverses is not None:
                self._header(db, reverses)
            if replaces is not None:
                self._replace(db, replaces, self._acts(kind, reverses, request), hotel_id, offer)
            return self._insert(db, kind, "previewed", hotel, hotel_id, offer, currency, sentence, read_at, rows, reverses,
                                request, reading, replaces)

    @staticmethod
    def _acts(kind: str, reverses: int | None, request: Mapping | None) -> str:
        """미리보기가 하는 일 — 다시 계산한 미리보기는 같은 일을 하는 앞 미리보기만 바꾼다. 저장 상태로 되돌리기는 장부의 종류가
        change 라 요청(`restore_snapshot`)으로 가른다."""
        if kind == "rollback":
            return f"{reverses}번 되돌리기"
        if request and request.get("kind") == "restore_snapshot":
            return f"{request.get('snapshot')}번 저장 상태로 되돌리기"
        return "가격 바꾸기"

    def _replace(self, db, change_id: int, acts: str, hotel_id: str, offer: str) -> None:
        old = self._header(db, change_id)
        if old["status"] == "replaced":
            raise LedgerError(f"{change_id}번 미리보기는 이미 {self._replacer(db, change_id)}번으로 바뀌었습니다 — 그 번호를 바꿉니다")
        if old["status"] != "previewed":
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
        if self.kind is not None:
            other = db.execute("SELECT item_kind FROM item_values WHERE change_id = ? AND item_kind != ? LIMIT 1",
                               (change_id, self.kind)).fetchone()
            if other is not None:
                owner = KIND_NAMES.get(other["item_kind"], other["item_kind"])
                raise LedgerError(f"{change_id}번은 {owner}의 기록입니다 — 이 도우미는 {KIND_NAMES.get(self.kind, self.kind)}의 "
                                  "기록만 다룹니다")
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

    def _cause(self, header, steps) -> str | None:
        """멈춘 까닭. 장부가 적용 중인데 멈춘 것이면 끊긴 것이다(실패한 저장이 그 앞에 있었어도 그 뒤 이어서 했다)."""
        if self._status(header) != "stopped":
            return None
        failed = [step for step in steps if step["status"] == "failed"]
        missed, unknown, cut_off = CAUSES
        if header["status"] == "applying" or not failed:
            return cut_off
        return unknown if any(step["unknown"] for step in failed) else missed

    @staticmethod
    def _mark_saved(db, header, index: int, note: str | None, stamp: str) -> None:
        """단계 하나를 저장됨으로 적는다. 되돌리기의 저장이면 되돌린 변경의 그 값들에 이 번호를 단다."""
        db.execute("UPDATE steps SET status = 'saved', finished_at = ?, note = ?, unknown = 0 WHERE change_id = ? AND idx = ?",
                   (stamp, note, header["id"], index))
        if header["kind"] == "rollback":
            for row in db.execute("SELECT item_kind, item_key, field FROM item_values WHERE change_id = ? AND step = ?",
                                  (header["id"], index)).fetchall():
                db.execute(f"UPDATE item_values SET rolled_back_by = ? WHERE change_id = ? AND {ROW}"
                           " AND action IS NOT NULL AND rolled_back_by IS NULL",
                           (header["id"], header["reverses"], row["item_kind"], row["item_key"], row["field"]))

    def begin(self, change_id: int, steps: Sequence[StepPlan], request: Mapping | None = None, *, read_at: str) -> None:
        """적용 시작 — 저장 단계를 적고 단계가 쓰는 필드마다 단계 번호를 단다.

        단계가 쓰는 값은 미리보기 때 적은 줄(넣는 필드 · 넣는 값 · 비움)과 꼭 같아야 한다. 미리보기에 없던 값, 다른 값, 두 번
        쓰는 값, 그리고 미리보기가 넣는다고 보였는데 어느 단계도 쓰지 않는 값이 하나라도 있으면 시작하지 않는다.
        `read_at` 은 적용 직전에 읽어 미리보기 때 값과 같다고 본 읽은 값의 시각이다. IDLE 보다 오래된 읽은 값으로는 시작하지
        않는다. 그 시각이 첫 활동이다. 같은 단계로 다시 부르면 아무것도 바꾸지 않는다. `request` 를 주면 미리보기 때 적은
        요청과 같은 계산인지 본다.
        """
        encoded = [(step.kind, _body(step.body)) for step in steps]
        with self._db() as db:
            header = self._header(db, change_id)
            if header["kind"] == "snapshot":
                raise LedgerError("지금 상태 저장은 적용할 것이 없습니다")
            if header["status"] == "replaced":
                raise LedgerError(f"{change_id}번 미리보기는 다시 계산해 {self._replacer(db, change_id)}번으로 바뀌었습니다 — "
                                  "그 번호와 그 계산 파일로 적용합니다")
            if request is not None and header["request"] is not None and json.loads(header["request"]) != dict(request):
                raise LedgerError(f"{change_id}번 변경의 요청과 다른 계산입니다. 미리보기를 다시 만들어 주세요")
            if header["status"] != "previewed":
                stored = [(row["kind"], row["body"]) for row in
                          db.execute("SELECT kind, body FROM steps WHERE change_id = ? ORDER BY idx", (change_id,))]
                if stored == encoded:
                    return
                raise LedgerError(f"{change_id}번 변경은 이미 다른 저장 단계로 적용을 시작했습니다")
            if self._age(read_at) > IDLE:
                raise LedgerError(f"적용 직전에 읽은 값이 {_minutes(self._age(read_at))}분 전 것입니다 — "
                                  f"{_minutes(IDLE)}분 안에 읽은 값으로만 시작합니다. 다시 읽고 begin 을 부릅니다")
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
            db.execute("UPDATE changes SET status = 'applying', updated_at = ?, active_at = ? WHERE id = ?",
                       (self._stamp(), read_at, change_id))

    def begin_fresh(self, change_id: int, steps: Sequence[StepPlan], then: Reading, now: Reading, *, read_at: str,
                    request: Mapping | None = None) -> tuple[Difference, ...]:
        """적용 직전에 다시 읽고 시작하기(결정 18) — 방금 읽은 값(`now`, 읽은 시각 `read_at`)을 그 번호의 계산이 바탕으로 삼은 읽은
        값(`then`)과 견주어, 한 항목이라도(딸린 칸까지) 다르면 아무것도 시작하지 않고 다른 항목들을 돌려준다. 같으면 begin 하고 빈
        것을 돌려준다(읽은 값이 IDLE 보다 오래됐으면 begin 이 거절한다). 이미 적용을 시작한 번호는 견주지 않고 begin 에 넘긴다 — 같은
        단계로 다시 부르면 아무것도 바꾸지 않는다."""
        if self.change(change_id).status == "previewed":
            differences = stale_items(then, now)
            if differences:
                return differences
        self.begin(change_id, steps, request, read_at=read_at)
        return ()

    def record_step(self, change_id: int, index: int, saved: bool, note: str | None = None, unknown: bool = False) -> str:
        """저장 한 번이 끝날 때마다 부른다. 새 상태를 돌려준다.

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
            if saved:
                self._mark_saved(db, header, index, note, stamp)
            else:
                db.execute("UPDATE steps SET status = 'failed', finished_at = ?, note = ?, unknown = ? WHERE change_id = ? AND idx = ?",
                           (stamp, note, int(unknown), change_id, index))
            left = db.execute("SELECT COUNT(*) FROM steps WHERE change_id = ? AND status != 'saved'",
                              (change_id,)).fetchone()[0]
            status = "stopped" if not saved else "applied" if left == 0 else header["status"]
            db.execute("UPDATE changes SET status = ?, updated_at = ?, applied_at = COALESCE(applied_at, ?),"
                       " active_at = CASE WHEN ? THEN ? ELSE active_at END WHERE id = ?",
                       (status, stamp, stamp if status == "applied" else None, saved and alive, stamp, change_id))
            return self._status(self._header(db, change_id))

    @staticmethod
    def _written(db, change_id, still_ours=False):
        return db.execute(
            "SELECT item_values.* FROM item_values JOIN steps ON steps.change_id = item_values.change_id"
            " AND steps.idx = item_values.step WHERE item_values.change_id = ? AND steps.status = 'saved'"
            + (" AND item_values.rolled_back_by IS NULL" if still_ours else "") + " ORDER BY item_values.rowid",
            (change_id,)).fetchall()

    def verify(self, change_id: int, reading: Reading) -> list[Mismatch]:
        """저장된 값을 방금 읽은 값과 견준다. 맞는 값은 확인됨으로 적고, 다른 값을 돌려준다. 되돌린 값은 보지 않는다."""
        mismatches = []
        with self._db() as db:
            self._header(db, change_id)
            for row in self._written(db, change_id, still_ours=True):
                item = reading.get((row["item_kind"], row["item_key"]))
                seen = None if item is None else item.fields.get(row["field"])
                after = money(row["after"])
                held = item is not None and item.state != "missing" and seen == after
                if not held:
                    mismatches.append(Mismatch(row["item_kind"], row["item_key"], row["label"], row["field"], after, seen,
                                               None if item is None else item.state))
                db.execute(f"UPDATE item_values SET verified = ?, seen = ?, seen_state = ? WHERE change_id = ? AND {ROW}",
                           (int(held), money_text(seen), None if item is None else item.state, change_id,
                            row["item_kind"], row["item_key"], row["field"]))
            stamp = self._stamp()
            db.execute("UPDATE changes SET verified_at = ?, updated_at = ? WHERE id = ?", (stamp, stamp, change_id))
        return mismatches

    def untouched(self, change_id: int, reading: Reading) -> list[Mismatch]:
        """저장한 항목의 넣지 않은 필드 가운데 방금 읽은 값이 미리보기 때 값과 다른 것(`after` 는 그대로여야 할 값). 기록 하나를
        통째로 다시 저장하는 화면(부가옵션 가격 줄 · 부과금 …)에서 저장이 다른 필드를 건드리지 않았는지 본다. 장부에는 적지 않는다."""
        with self._db() as db:
            self._header(db, change_id)
            saved = {(row["item_kind"], row["item_key"]) for row in self._written(db, change_id)}
            rows = db.execute("SELECT * FROM item_values WHERE change_id = ? AND action IS NULL AND state != 'missing'"
                              " ORDER BY rowid", (change_id,)).fetchall()
        moved = []
        for row in rows:
            if (row["item_kind"], row["item_key"]) not in saved:
                continue
            item = reading.get((row["item_kind"], row["item_key"]))
            seen, before = None if item is None else item.fields.get(row["field"]), money(row["before"])
            if item is None or item.state == "missing" or seen != before:
                moved.append(Mismatch(row["item_kind"], row["item_key"], row["label"], row["field"], before, seen,
                                      None if item is None else item.state))
        return moved

    def check(self, change_id: int, now: Reading, then: Reading, read_at: str) -> CheckReport:
        """이 변경에 무슨 일이 있었는지 — 저장마다 방금 읽은 값(`now`, 읽은 시각 `read_at`)이 말하는 것과, 남은 저장을 계획대로
        해도 되는지, 어디까지 됐고 왜 멈췄는지.

        「모름」(눌렸고 저장됐는지 모르는 단계)은 읽은 값이 넣은 값 그대로면 저장됨으로, 전 값 그대로면 저장 안 됨으로 가려 적는다.
        남은 저장을 해도 되는 것은 — 저장된 단계가 모두 그대로이고, 남은 단계가 모두 저장 안 됨이며, 남은 단계의 칸이 그 계산이
        바탕으로 삼은 읽은 값(`then`)과 모두 같고, 읽은 값이 IDLE 안의 것일 때뿐이다. 그러면 변경을 적용 중으로 두고 그 읽은
        값의 시각을 활동으로 적는다(IDLE 안이면 calls 가 남은 단계를 낸다). 아니면 멈춘 변경으로 둔다.
        """
        with self._db() as db:
            header = self._header(db, change_id)
            steps = db.execute("SELECT * FROM steps WHERE change_id = ? ORDER BY idx", (change_id,)).fetchall()
            if not steps:
                raise LedgerError(f"{change_id}번 변경은 아직 적용을 시작하지 않았습니다(begin)")
            rows = {step["idx"]: db.execute("SELECT * FROM item_values WHERE change_id = ? AND step = ? ORDER BY rowid",
                                            (change_id, step["idx"])).fetchall() for step in steps}
        cause = self._cause(header, steps)
        note = next((step["note"] for step in steps if step["status"] == "failed"), None) if cause in ("failed", "unknown") else None
        seen_steps, settle = [], []
        for step in steps:
            kinds = {_field_seen(row, now.get((row["item_kind"], row["item_key"]))) for row in rows[step["idx"]]}
            seen = {frozenset({"after"}): "saved", frozenset({"before"}): "not_saved",
                    frozenset({"after", "before"}): "mixed"}.get(frozenset(kinds), "changed")
            state = "unknown" if step["status"] == "failed" and step["unknown"] else step["status"]
            if state == "saved" and seen != "saved":
                seen = "changed"
            settled = seen if state == "unknown" and seen in ("saved", "not_saved") else None
            if settled:
                settle.append((step["idx"], settled))
            done = state == "saved" or settled == "saved"
            items = {(row["item_kind"], row["item_key"]) for row in rows[step["idx"]]}
            moved = 0 if done else sum(not _same_item(then.get(item), now.get(item)) for item in items)
            seen_steps.append(StepSeen(step["idx"], step["label"], state, seen, settled, moved))
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
            elif step.seen == "saved":
                why.append(f"{name}은 장부에 저장 안 됨인데 칸은 이미 넣으려던 값입니다")
            elif step.seen == "mixed":
                why.append(f"{name}의 칸이 일부만 넣으려던 값입니다")
            elif step.seen == "changed":
                why.append(f"{name}의 칸이 넣으려던 값도 그 전 값도 아닙니다")
            if step.moved:
                why.append(f"{name}의 칸 {step.moved}개가 미리보기 때 읽은 값과 다릅니다")
        if remaining and self._age(read_at) > IDLE:
            why.append(f"읽은 값이 {_minutes(self._age(read_at))}분 전 것입니다 — {_minutes(IDLE)}분 안에 읽은 값으로만 이어 갑니다. "
                       "다시 읽고 check 를 부릅니다")
        can_continue = bool(remaining) and not why
        stamp = self._stamp()
        with self._db() as db:
            for index, settled in settle:
                if settled == "saved":
                    self._mark_saved(db, header, index, "다시 읽어 저장된 것을 확인했습니다", stamp)
                else:
                    db.execute("UPDATE steps SET unknown = 0, note = ? WHERE change_id = ? AND idx = ?",
                               ("다시 읽어 저장되지 않은 것을 확인했습니다", change_id, index))
            status = "applied" if not remaining else "applying" if can_continue else "stopped"
            db.execute("UPDATE changes SET status = ?, updated_at = ?, applied_at = COALESCE(applied_at, ?),"
                       " active_at = CASE WHEN ? THEN ? ELSE active_at END WHERE id = ?",
                       (status, stamp, stamp if status == "applied" else None, can_continue, read_at, change_id))
        saved = [step for step in seen_steps if step.ledger == "saved" or step.settled == "saved"]
        return CheckReport(header["id"], status, tuple(seen_steps), tuple(remaining), can_continue, tuple(why), cause,
                           saved[-1] if saved else None,
                           next((step for step in seen_steps if step.index == remaining[0]), None) if remaining else None, note)

    def recorded_change(self, change_id: int) -> RecordedChange:
        """되돌리기 계산의 재료 — 실제로 저장이 끝났고 아직 되돌리지 않은 값이 있는 항목만."""
        with self._db() as db:
            header = self._header(db, change_id)
            if header["kind"] == "snapshot":
                raise LedgerError(f"{change_id}번은 저장해 둔 상태입니다. 그 상태로 돌리려면 '저장해 둔 상태로 되돌리기'를 씁니다")
            ours: dict[tuple[str, str], dict] = {}
            for row in self._written(db, change_id, still_ours=True):
                ours.setdefault((row["item_kind"], row["item_key"]), {})[row["field"]] = money(row["after"])
            items = []
            for (kind, key), written in ours.items():
                rows = db.execute("SELECT * FROM item_values WHERE change_id = ? AND item_kind = ? AND item_key = ?"
                                  " ORDER BY rowid", (change_id, kind, key)).fetchall()
                items.append(RecordedItem(kind, key, rows[0]["label"], rows[0]["state"],
                                          {row["field"]: money(row["before"]) for row in rows}, written))
        return RecordedChange(header["id"], header["kind"], header["hotel"], header["offer"], header["currency"],
                              header["sentence"], header["read_at"], header["applied_at"], tuple(items), header["hotel_id"])

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
        """이 변경 뒤에 같은 호텔·오퍼에 이 장부가 저장한 값 — 항목마다, 변경마다 하나씩, 오래된 것부터."""
        grouped: dict[tuple[str, str, int], dict] = {}
        with self._db() as db:
            header = self._header(db, change_id)
            rows = db.execute(
                "SELECT item_values.*, steps.finished_at, changes.sentence FROM item_values"
                " JOIN steps ON steps.change_id = item_values.change_id AND steps.idx = item_values.step"
                " JOIN changes ON changes.id = item_values.change_id"
                " WHERE item_values.change_id > ? AND steps.status = 'saved' AND changes.kind != 'snapshot'"
                " AND changes.hotel_id = ? AND changes.offer = ? ORDER BY item_values.change_id, steps.idx",
                (change_id, header["hotel_id"], header["offer"])).fetchall()
        for row in rows:
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
            rows = tuple(
                RowRecord(row["item_kind"], row["item_key"], row["label"], row["field"], row["state"], money(row["before"]),
                          money(row["after"]), row["action"], row["step"], row["step"] in saved, bool(row["verified"]),
                          money(row["seen"]), row["seen_state"], row["rolled_back_by"], row["verdict"],
                          tuple(mark for mark in row["marks"].split(",") if mark), row["choice"])
                for row in db.execute("SELECT * FROM item_values WHERE change_id = ? ORDER BY rowid", (change_id,)))
        cause = self._cause(header, [dict(status=step.status, unknown=step.unknown) for step in steps])
        return ChangeRecord(header["id"], header["kind"], self._status(header), header["hotel"], header["hotel_id"],
                            header["offer"], header["currency"], header["sentence"], header["read_at"], header["created_at"],
                            header["applied_at"], header["verified_at"], header["reverses"],
                            None if header["request"] is None else json.loads(header["request"]), steps, rows, cause,
                            header["replaces"])

    def reading(self, change_id: int) -> dict:
        """그 번호의 계산이 바탕으로 삼은 읽은 값(적을 때 준 JSON 그대로). 적지 않은 번호면 거절한다."""
        with self._db() as db:
            header = self._header(db, change_id)
        if header["reading"] is None:
            raise LedgerError(f"{change_id}번에는 적어 둔 읽은 값이 없습니다 — 범위를 다시 정해 읽어야 합니다")
        return json.loads(header["reading"])

    def list_changes(self, change_id: int | None = None) -> list[dict]:
        """장부의 번호마다 한 줄(새것부터, `change_id` 를 주면 그 번호만, 종류로 열었으면 그 종류의 번호만). 저장한 항목이 뒤의 되돌리기로 모두 되돌아갔으면 상태는 `rolled_back`, 일부면
        `partly_rolled_back` 이다(`written` · `rolled_back` 이 그 수, `undone_by` 가 되돌린 번호들) — 되돌린 변경이 살아 있는
        것처럼 보이지 않는다. `steps` · `saved_steps` 는 저장 단계 수와 그중 저장된 수, `request` 는 적어 둔 요청(없으면 None)."""
        item = "item_values.item_kind || '|' || item_values.item_key"
        where, params = [], []
        if change_id is not None:
            where.append("changes.id = ?")
            params.append(change_id)
        if self.kind is not None:
            where.append("NOT EXISTS (SELECT 1 FROM item_values AS other WHERE other.change_id = changes.id AND other.item_kind != ?)")
            params.append(self.kind)
        with self._db() as db:
            rows = db.execute(
                f"SELECT changes.*, COUNT(DISTINCT {item}) AS items,"
                f" COUNT(DISTINCT CASE WHEN steps.status = 'saved' THEN {item} END) AS written,"
                f" COUNT(DISTINCT CASE WHEN item_values.rolled_back_by IS NOT NULL THEN {item} END) AS rolled_back,"
                " GROUP_CONCAT(DISTINCT item_values.rolled_back_by) AS undone_by,"
                " (SELECT COUNT(*) FROM steps AS s WHERE s.change_id = changes.id) AS step_count,"
                " (SELECT COUNT(*) FROM steps AS s WHERE s.change_id = changes.id AND s.status = 'saved') AS saved_steps"
                " FROM changes LEFT JOIN item_values ON item_values.change_id = changes.id"
                " LEFT JOIN steps ON steps.change_id = item_values.change_id AND steps.idx = item_values.step"
                + (" WHERE " + " AND ".join(where) if where else "") + " GROUP BY changes.id ORDER BY changes.id DESC",
                params).fetchall()
        return [dict(id=row["id"], kind=row["kind"], status=self._listed_status(row), hotel=row["hotel"], hotel_id=row["hotel_id"],
                     offer=row["offer"], currency=row["currency"],
                     sentence=row["sentence"], read_at=row["read_at"], created_at=row["created_at"],
                     applied_at=row["applied_at"], verified_at=row["verified_at"], reverses=row["reverses"],
                     replaces=row["replaces"], items=row["items"], written=row["written"], rolled_back=row["rolled_back"],
                     undone_by=sorted(int(number) for number in (row["undone_by"] or "").split(",") if number),
                     steps=row["step_count"], saved_steps=row["saved_steps"],
                     request=None if row["request"] is None else json.loads(row["request"])) for row in rows]

    def _listed_status(self, row) -> str:
        """목록의 상태 — 저장한 항목이 모두 되돌아갔으면 rolled_back, 일부면 partly_rolled_back, 아니면 장부의 상태."""
        if row["written"] and row["rolled_back"]:
            return "rolled_back" if row["rolled_back"] >= row["written"] else "partly_rolled_back"
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
        """이 변경의 저장한 값을 이미 되돌린 되돌리기마다 — 번호 · 요청 문장 · 적용 시각 · 되돌린 항목들(종류, 키)."""
        grouped: dict[int, dict] = {}
        with self._db() as db:
            self._header(db, change_id)
            for row in db.execute(
                    "SELECT item_values.rolled_back_by AS by, item_values.item_kind, item_values.item_key, changes.sentence,"
                    " changes.applied_at FROM item_values JOIN changes ON changes.id = item_values.rolled_back_by"
                    " WHERE item_values.change_id = ? ORDER BY item_values.rolled_back_by, item_values.rowid", (change_id,)):
                entry = grouped.setdefault(row["by"], dict(change_id=row["by"], sentence=row["sentence"], applied_at=row["applied_at"],
                                                           items={}))
                entry["items"][(row["item_kind"], row["item_key"])] = None
        return [dict(entry, items=list(entry["items"])) for entry in grouped.values()]
