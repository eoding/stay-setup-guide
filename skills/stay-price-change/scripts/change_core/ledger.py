"""담당자 PC 의 변경 장부(SQLite 하나). 지우는 일은 없다.

자리는 어느 폴더에서 Claude 를 열어도 같은 한 곳이다: `~/Documents/어딩 Stay 가격 변경 기록/가격장부.sqlite3`.
환경 변수 `STAY_PRICE_LEDGER_DIR` 로 다른 폴더를 줄 수 있다(시험은 임시 폴더를 쓴다). 가격·부과금·프로모션·부가옵션
도우미가 모두 이 장부 하나에 적는다.

    meta         schema_version — 이 코드보다 새 판이 만든 장부는 열지 않는다
    changes      변경 한 번에 한 줄 — 종류(change / snapshot / rollback), 상태(previewed → applying → stopped / applied),
                 요청 문장, 읽은 시각, 되돌리기면 되돌리는 변경 번호, 요청 원문(JSON)
    item_values  항목 하나의 필드 하나에 한 줄 — 항목 종류(`price_cell` …), 굳은 키, 이름, 필드, 그때 상태, 전 값, 넣을 값,
                 넣는 방법(set / clear, 넣지 않으면 비어 있음), 몇 번째 저장인지, 다시 읽어 맞았는지와 읽은 값,
                 되돌린 되돌리기 번호
    steps        저장 한 번에 한 줄 — 단계 종류와 내용(JSON), 끝날 때마다 바로 적는다

snapshot 은 읽어서 적어 두기만 하므로 적는 순간 상태가 applied 다.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

from .items import Reading
from .money import money, money_text
from .rollback import LaterWrite, RecordedChange, RecordedItem

LEDGER_ENV = "STAY_PRICE_LEDGER_DIR"
FOLDER_NAME = "어딩 Stay 가격 변경 기록"
DB_NAME = "가격장부.sqlite3"
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK (kind IN ('change', 'snapshot', 'rollback')),
  status TEXT NOT NULL CHECK (status IN ('previewed', 'applying', 'stopped', 'applied')),
  hotel TEXT NOT NULL,
  offer TEXT NOT NULL,
  currency TEXT NOT NULL,
  sentence TEXT NOT NULL,
  read_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  applied_at TEXT,
  verified_at TEXT,
  reverses INTEGER REFERENCES changes(id),
  request TEXT
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


@dataclass(frozen=True)
class ValueRow:
    """미리보기 때 적는 한 줄 — `after` 는 계산한 새 값(바뀌지 않는 필드는 None)."""
    item_kind: str
    item_key: str
    label: str
    field: str
    state: str
    before: Decimal | None
    after: Decimal | None = None
    verdict: str | None = None
    marks: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class ChangeRecord:
    id: int
    kind: str
    status: str
    hotel: str
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
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else ledger_dir() / DB_NAME
        with self._db() as db:
            has_meta = db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'").fetchone()
            found = db.execute("SELECT value FROM meta WHERE name = 'schema_version'").fetchone() if has_meta else None
            if found and int(found["value"]) > SCHEMA_VERSION:
                raise LedgerError(f"이 장부는 더 새 판 도우미가 만든 것입니다(장부 판 {found['value']}, 이 도우미는 "
                                  f"{SCHEMA_VERSION}). 도우미를 새로 받아 주세요")
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO meta (name, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

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

    def _insert(self, db, kind, status, hotel, offer, currency, sentence, read_at, rows: Iterable[ValueRow],
                reverses=None, request=None) -> int:
        stamp = now_text()
        change_id = db.execute(
            "INSERT INTO changes (kind, status, hotel, offer, currency, sentence, read_at, created_at, updated_at,"
            " applied_at, reverses, request) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, status, hotel, offer, currency, sentence, read_at, stamp, stamp, stamp if status == "applied" else None,
             reverses, None if request is None else _body(request))).lastrowid
        db.executemany(
            "INSERT INTO item_values (change_id, item_kind, item_key, label, field, state, before, after, verdict, marks)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(change_id, row.item_kind, row.item_key, row.label, row.field, row.state, money_text(row.before),
              money_text(row.after), row.verdict, ",".join(row.marks)) for row in rows])
        return change_id

    def record_preview(self, *, hotel: str, offer: str, currency: str, sentence: str, read_at: str,
                       rows: Iterable[ValueRow], request: Mapping | None = None, reverses: int | None = None) -> int:
        """미리보기를 적는다. `reverses` 를 주면 그 변경을 되돌리는 변경(rollback)이다."""
        with self._db() as db:
            if reverses is not None:
                self._header(db, reverses)
            return self._insert(db, "rollback" if reverses is not None else "change", "previewed", hotel, offer, currency,
                                sentence, read_at, rows, reverses, request)

    def record_snapshot(self, *, hotel: str, offer: str, currency: str, sentence: str, read_at: str,
                        rows: Iterable[ValueRow]) -> int:
        with self._db() as db:
            return self._insert(db, "snapshot", "applied", hotel, offer, currency, sentence, read_at, rows)

    def _header(self, db, change_id):
        row = db.execute("SELECT * FROM changes WHERE id = ?", (change_id,)).fetchone()
        if row is None:
            raise LedgerError(f"장부에 {change_id}번 변경이 없습니다")
        return row

    def begin(self, change_id: int, steps: Sequence[StepPlan], request: Mapping | None = None) -> None:
        """적용 시작 — 저장 단계를 적고 단계가 쓰는 필드마다 넣을 값·방법·단계 번호를 단다.

        같은 단계로 다시 부르면 아무것도 바꾸지 않는다. `request` 를 주면 미리보기 때 적은 요청과 같은 계산인지 본다.
        """
        encoded = [(step.kind, _body(step.body)) for step in steps]
        with self._db() as db:
            header = self._header(db, change_id)
            if header["kind"] == "snapshot":
                raise LedgerError("지금 상태 저장은 적용할 것이 없습니다")
            if request is not None and header["request"] is not None and json.loads(header["request"]) != dict(request):
                raise LedgerError(f"{change_id}번 변경의 요청과 다른 계산입니다. 미리보기를 다시 만들어 주세요")
            if header["status"] != "previewed":
                stored = [(row["kind"], row["body"]) for row in
                          db.execute("SELECT kind, body FROM steps WHERE change_id = ? ORDER BY idx", (change_id,))]
                if stored == encoded:
                    return
                raise LedgerError(f"{change_id}번 변경은 이미 다른 저장 단계로 적용을 시작했습니다")
            for index, step in enumerate(steps, 1):
                for write in step.writes:
                    row = db.execute(f"SELECT step FROM item_values WHERE change_id = ? AND {ROW}",
                                     (change_id, write.item_kind, write.item_key, write.field)).fetchone()
                    if row is None:
                        raise LedgerError(f"미리보기에 없던 값입니다: {step.label} · {write.field}")
                    if row["step"] is not None:
                        raise LedgerError(f"같은 값을 두 번 씁니다: {step.label} · {write.field}")
                    db.execute(f"UPDATE item_values SET after = ?, action = ?, step = ? WHERE change_id = ? AND {ROW}",
                               (money_text(write.after), "clear" if write.after is None else "set", index, change_id,
                                write.item_kind, write.item_key, write.field))
                db.execute("INSERT INTO steps (change_id, idx, kind, label, body, status) VALUES (?, ?, ?, ?, ?, 'pending')",
                           (change_id, index, step.kind, step.label, _body(step.body)))
            db.execute("UPDATE changes SET status = 'applying', updated_at = ? WHERE id = ?", (now_text(), change_id))

    def record_step(self, change_id: int, index: int, saved: bool, note: str | None = None) -> str:
        """저장 한 번이 끝날 때마다 부른다. 되돌리기의 저장이 끝나면 되돌린 변경의 그 값들에 이 번호를 단다. 새 상태를 돌려준다."""
        with self._db() as db:
            header = self._header(db, change_id)
            step = db.execute("SELECT * FROM steps WHERE change_id = ? AND idx = ?", (change_id, index)).fetchone()
            if step is None:
                raise LedgerError(f"{change_id}번 변경에 {index}번째 저장이 없습니다")
            if step["status"] == "saved":
                return header["status"]
            stamp = now_text()
            db.execute("UPDATE steps SET status = ?, finished_at = ?, note = ? WHERE change_id = ? AND idx = ?",
                       ("saved" if saved else "failed", stamp, note, change_id, index))
            if saved and header["kind"] == "rollback":
                for row in db.execute("SELECT item_kind, item_key, field FROM item_values WHERE change_id = ? AND step = ?",
                                      (change_id, index)).fetchall():
                    db.execute(f"UPDATE item_values SET rolled_back_by = ? WHERE change_id = ? AND {ROW}"
                               " AND action IS NOT NULL AND rolled_back_by IS NULL",
                               (change_id, header["reverses"], row["item_kind"], row["item_key"], row["field"]))
            left = db.execute("SELECT COUNT(*) FROM steps WHERE change_id = ? AND status != 'saved'",
                              (change_id,)).fetchone()[0]
            status = "stopped" if not saved else "applied" if left == 0 else "applying"
            db.execute("UPDATE changes SET status = ?, updated_at = ?, applied_at = COALESCE(applied_at, ?) WHERE id = ?",
                       (status, stamp, stamp if status == "applied" else None, change_id))
        return status

    @staticmethod
    def _written(db, change_id, still_ours=False):
        return db.execute(
            "SELECT item_values.* FROM item_values JOIN steps ON steps.change_id = item_values.change_id"
            " AND steps.idx = item_values.step WHERE item_values.change_id = ? AND steps.status = 'saved'"
            + (" AND item_values.rolled_back_by IS NULL" if still_ours else "") + " ORDER BY item_values.rowid",
            (change_id,)).fetchall()

    def verify(self, change_id: int, reading: Reading) -> list[Mismatch]:
        """저장된 값을 방금 읽은 값과 견준다. 맞는 값은 확인됨으로 적고, 다른 값을 돌려준다."""
        mismatches = []
        with self._db() as db:
            self._header(db, change_id)
            for row in self._written(db, change_id):
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
            stamp = now_text()
            db.execute("UPDATE changes SET verified_at = ?, updated_at = ? WHERE id = ?", (stamp, stamp, change_id))
        return mismatches

    def recorded_change(self, change_id: int) -> RecordedChange:
        """되돌리기 계산의 재료 — 실제로 저장이 끝났고 아직 되돌리지 않은 값이 있는 항목만."""
        with self._db() as db:
            header = self._header(db, change_id)
            if header["kind"] == "snapshot":
                raise LedgerError("지금 상태 저장으로 되돌리기는 이 판에 아직 없습니다")
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
                              header["sentence"], header["read_at"], header["applied_at"], tuple(items))

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
                " AND changes.hotel = ? AND changes.offer = ? ORDER BY item_values.change_id, steps.idx",
                (change_id, header["hotel"], header["offer"])).fetchall()
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
                                     row["finished_at"], row["note"])
                          for row in db.execute("SELECT * FROM steps WHERE change_id = ? ORDER BY idx", (change_id,)))
            saved = {step.index for step in steps if step.status == "saved"}
            rows = tuple(
                RowRecord(row["item_kind"], row["item_key"], row["label"], row["field"], row["state"], money(row["before"]),
                          money(row["after"]), row["action"], row["step"], row["step"] in saved, bool(row["verified"]),
                          money(row["seen"]), row["seen_state"], row["rolled_back_by"], row["verdict"],
                          tuple(mark for mark in row["marks"].split(",") if mark))
                for row in db.execute("SELECT * FROM item_values WHERE change_id = ? ORDER BY rowid", (change_id,)))
        return ChangeRecord(header["id"], header["kind"], header["status"], header["hotel"], header["offer"],
                            header["currency"], header["sentence"], header["read_at"], header["created_at"],
                            header["applied_at"], header["verified_at"], header["reverses"],
                            None if header["request"] is None else json.loads(header["request"]), steps, rows)

    def list_changes(self) -> list[dict]:
        item = "item_values.item_kind || '|' || item_values.item_key"
        with self._db() as db:
            rows = db.execute(
                f"SELECT changes.*, COUNT(DISTINCT {item}) AS items,"
                f" COUNT(DISTINCT CASE WHEN steps.status = 'saved' THEN {item} END) AS written,"
                f" COUNT(DISTINCT CASE WHEN item_values.rolled_back_by IS NOT NULL THEN {item} END) AS rolled_back"
                " FROM changes LEFT JOIN item_values ON item_values.change_id = changes.id"
                " LEFT JOIN steps ON steps.change_id = item_values.change_id AND steps.idx = item_values.step"
                " GROUP BY changes.id ORDER BY changes.id DESC").fetchall()
        return [dict(id=row["id"], kind=row["kind"], status=row["status"], hotel=row["hotel"], offer=row["offer"],
                     sentence=row["sentence"], read_at=row["read_at"], created_at=row["created_at"],
                     applied_at=row["applied_at"], verified_at=row["verified_at"], reverses=row["reverses"],
                     items=row["items"], written=row["written"], rolled_back=row["rolled_back"]) for row in rows]
