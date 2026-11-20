"""price_ledger.py — 담당자 PC 의 가격 변경 장부(SQLite 하나). 지우는 일은 없다.

자리는 어느 폴더에서 Claude 를 열어도 같은 한 곳이다: `~/Documents/어딩 Stay 가격 변경 기록/가격장부.sqlite3`.
환경 변수 `STAY_PRICE_LEDGER_DIR` 로 다른 폴더를 줄 수 있다(시험은 임시 폴더를 쓴다).

    changes  변경 한 번에 한 줄 — 종류(change / snapshot / rollback), 상태(previewed → applying → stopped / applied),
             요청 문장, 읽은 시각, 되돌리기면 되돌리는 변경 번호
    cells    칸마다 한 줄 — 적어 둔 전 값, 넣을 값, 판정, 몇 번째 저장에 들어가는지, 다시 읽어 맞았는지
    steps    저장 한 번에 한 줄 — 끝날 때마다 바로 적는다

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
from typing import Iterable, Iterator

from price_model import (
    CellKey, CellValue, CellWrite, LaterWrite, Plan, RecordedCell, RecordedChange, RollbackPlan, SaveStep, Snapshot,
    decode_step, encode_request, encode_step, money, money_text,
)

LEDGER_ENV = "STAY_PRICE_LEDGER_DIR"
FOLDER_NAME = "어딩 Stay 가격 변경 기록"
DB_NAME = "가격장부.sqlite3"

SCHEMA = """
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
CREATE TABLE IF NOT EXISTS cells (
  change_id INTEGER NOT NULL REFERENCES changes(id),
  room TEXT NOT NULL,
  rate_plan TEXT NOT NULL,
  date TEXT NOT NULL,
  occupancy TEXT NOT NULL,
  nights INTEGER NOT NULL,
  before_sell TEXT,
  before_list TEXT,
  before_supply TEXT,
  before_state TEXT NOT NULL,
  reserved INTEGER NOT NULL DEFAULT 0,
  after_sell TEXT,
  after_list TEXT,
  verdict TEXT,
  step INTEGER,
  verified INTEGER NOT NULL DEFAULT 0,
  seen_sell TEXT,
  seen_list TEXT,
  seen_state TEXT,
  PRIMARY KEY (change_id, room, rate_plan, date, occupancy, nights)
);
CREATE TABLE IF NOT EXISTS steps (
  change_id INTEGER NOT NULL REFERENCES changes(id),
  idx INTEGER NOT NULL,
  room TEXT NOT NULL,
  rate_plan TEXT NOT NULL,
  dates TEXT NOT NULL,
  rows TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'saved', 'failed')),
  finished_at TEXT,
  note TEXT,
  PRIMARY KEY (change_id, idx)
);
CREATE TRIGGER IF NOT EXISTS keep_changes BEFORE DELETE ON changes BEGIN SELECT RAISE(ABORT, '장부는 지우지 않습니다'); END;
CREATE TRIGGER IF NOT EXISTS keep_cells BEFORE DELETE ON cells BEGIN SELECT RAISE(ABORT, '장부는 지우지 않습니다'); END;
CREATE TRIGGER IF NOT EXISTS keep_steps BEFORE DELETE ON steps BEGIN SELECT RAISE(ABORT, '장부는 지우지 않습니다'); END;
"""

KEY_COLUMNS = ("room", "rate_plan", "date", "occupancy", "nights")


class LedgerError(ValueError):
    """장부 순서에 맞지 않는 요청 — 문장은 담당자에게 그대로 보여 줄 수 있다."""


def ledger_dir() -> Path:
    override = os.environ.get(LEDGER_ENV)
    folder = Path(override).expanduser() if override else Path.home() / "Documents" / FOLDER_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _key(row) -> CellKey:
    return CellKey(row["room"], row["rate_plan"], row["date"], row["occupancy"], row["nights"])


def _before(row) -> CellValue:
    return CellValue(money(row["before_sell"]), money(row["before_list"]), money(row["before_supply"]), row["before_state"])


@dataclass(frozen=True)
class StepRecord:
    index: int
    step: SaveStep
    status: str
    finished_at: str | None
    note: str | None


@dataclass(frozen=True)
class CellRecord:
    key: CellKey
    before: CellValue
    after_sell: Decimal | None
    after_list: Decimal | None
    verdict: str | None
    reserved: bool
    step: int | None
    written: bool
    verified: bool
    seen: CellValue | None


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
    steps: tuple[StepRecord, ...]
    cells: tuple[CellRecord, ...]


class Ledger:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else ledger_dir() / DB_NAME
        with self._db() as db:
            db.executescript(SCHEMA)

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

    def _insert_change(self, db, kind, status, hotel, offer, currency, sentence, read_at, reverses=None, request=None):
        stamp = now_text()
        cursor = db.execute(
            "INSERT INTO changes (kind, status, hotel, offer, currency, sentence, read_at, created_at, updated_at,"
            " applied_at, reverses, request) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, status, hotel, offer, currency, sentence, read_at, stamp, stamp,
             stamp if status == "applied" else None, reverses, request))
        return cursor.lastrowid

    @staticmethod
    def _insert_cells(db, change_id, rows: Iterable[tuple]):
        db.executemany(
            "INSERT INTO cells (change_id, room, rate_plan, date, occupancy, nights, before_sell, before_list,"
            " before_supply, before_state, reserved, after_sell, after_list, verdict)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(change_id, key.room, key.rate_plan, key.date, key.occupancy, key.nights, money_text(before.sell),
              money_text(before.list_price), money_text(before.supply_cost), before.state, int(reserved),
              money_text(after_sell), money_text(after_list), verdict)
             for key, before, reserved, after_sell, after_list, verdict in rows])

    def record_preview(self, plan: Plan) -> int:
        request = plan.request
        with self._db() as db:
            change_id = self._insert_change(db, "change", "previewed", request.hotel, request.offer, plan.currency,
                                            request.sentence, plan.read_at,
                                            request=json.dumps(encode_request(request), ensure_ascii=False))
            self._insert_cells(db, change_id, ((c.key, c.before, "reserved" in c.marks,
                                                c.after.sell if c.after else None, None, c.verdict)
                                               for c in plan.changes))
        return change_id

    def record_rollback_preview(self, plan: RollbackPlan, sentence: str) -> int:
        with self._db() as db:
            original = db.execute("SELECT id FROM changes WHERE id = ?", (plan.reverses,)).fetchone()
            if original is None:
                raise LedgerError(f"장부에 {plan.reverses}번 변경이 없습니다")
            change_id = self._insert_change(db, "rollback", "previewed", plan.hotel, plan.offer, plan.currency,
                                            sentence, plan.read_at, reverses=plan.reverses)
            self._insert_cells(db, change_id, ((c.key, c.before, "reserved" in c.marks, c.after.sell, None, None)
                                               for c in plan.restored))
        return change_id

    def record_snapshot(self, snapshot: Snapshot, sentence: str) -> int:
        with self._db() as db:
            change_id = self._insert_change(db, "snapshot", "applied", snapshot.hotel, snapshot.offer,
                                            snapshot.currency, sentence, snapshot.read_at)
            self._insert_cells(db, change_id, ((key, value, (key.room, key.date) in snapshot.reserved, None, None, None)
                                               for key, value in sorted(snapshot.cells.items())))
        return change_id

    def _header(self, db, change_id):
        row = db.execute("SELECT * FROM changes WHERE id = ?", (change_id,)).fetchone()
        if row is None:
            raise LedgerError(f"장부에 {change_id}번 변경이 없습니다")
        return row

    def begin(self, change_id: int, steps: Iterable[SaveStep]) -> None:
        """적용 시작 — 저장 단계를 적고 칸마다 넣을 값과 단계 번호를 단다. 같은 단계로 다시 부르면 아무것도 바꾸지 않는다."""
        steps = tuple(steps)
        encoded = [json.dumps(encode_step(step), ensure_ascii=False, sort_keys=True) for step in steps]
        with self._db() as db:
            header = self._header(db, change_id)
            if header["kind"] == "snapshot":
                raise LedgerError("지금 상태 저장은 적용할 것이 없습니다")
            if header["status"] != "previewed":
                stored = [json.dumps(encode_step(self._step(row)), ensure_ascii=False, sort_keys=True)
                          for row in db.execute("SELECT * FROM steps WHERE change_id = ? ORDER BY idx", (change_id,))]
                if stored == encoded:
                    return
                raise LedgerError(f"{change_id}번 변경은 이미 다른 저장 단계로 적용을 시작했습니다")
            recorded = {_key(row) for row in db.execute("SELECT * FROM cells WHERE change_id = ?", (change_id,))}
            for index, step in enumerate(steps, 1):
                for day in step.dates:
                    for row in step.rows:
                        key = CellKey(step.room, step.rate_plan, day, row.occupancy, row.nights)
                        if key not in recorded:
                            raise LedgerError(f"미리보기에 없던 칸입니다: {step.room} · {step.rate_plan} · {day}")
                        db.execute(
                            "UPDATE cells SET after_sell = ?, after_list = ?, step = ? WHERE change_id = ? AND room = ?"
                            " AND rate_plan = ? AND date = ? AND occupancy = ? AND nights = ?",
                            (str(row.sell), money_text(row.list_price), index, change_id, *(
                                getattr(key, column) for column in KEY_COLUMNS)))
                db.execute("INSERT INTO steps (change_id, idx, room, rate_plan, dates, rows, status) VALUES"
                           " (?, ?, ?, ?, ?, ?, 'pending')", (change_id, index, step.room, step.rate_plan,
                                                              json.dumps(list(step.dates)),
                                                              json.dumps(encode_step(step)["rows"], ensure_ascii=False)))
            db.execute("UPDATE changes SET status = 'applying', updated_at = ? WHERE id = ?", (now_text(), change_id))

    def record_step(self, change_id: int, index: int, saved: bool, note: str | None = None) -> str:
        """저장 한 번이 끝날 때마다 부른다. 돌려주는 값은 변경의 새 상태다."""
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
            left = db.execute("SELECT COUNT(*) FROM steps WHERE change_id = ? AND status != 'saved'",
                              (change_id,)).fetchone()[0]
            status = "stopped" if not saved else "applied" if left == 0 else "applying"
            db.execute("UPDATE changes SET status = ?, updated_at = ?, applied_at = COALESCE(applied_at, ?) WHERE id = ?",
                       (status, stamp, stamp if status == "applied" else None, change_id))
        return status

    def verify(self, change_id: int, snapshot: Snapshot) -> list[tuple[CellKey, CellWrite, CellValue | None]]:
        """저장된 칸을 방금 읽은 값과 견준다. 맞는 칸은 확인됨으로 적고, 다른 칸 `(자리, 넣은 값, 읽은 값)` 을 돌려준다."""
        mismatches = []
        with self._db() as db:
            self._header(db, change_id)
            for row in self._written_rows(db, change_id):
                key = _key(row)
                write = CellWrite(key, money(row["after_sell"]), money(row["after_list"]))
                seen = snapshot.cells.get(key)
                held = seen is not None and seen.sell == write.sell and (
                    write.list_price is None or seen.list_price == write.list_price)
                if not held:
                    mismatches.append((key, write, seen))
                db.execute(
                    "UPDATE cells SET verified = ?, seen_sell = ?, seen_list = ?, seen_state = ? WHERE change_id = ?"
                    " AND room = ? AND rate_plan = ? AND date = ? AND occupancy = ? AND nights = ?",
                    (int(held), money_text(seen.sell) if seen else None, money_text(seen.list_price) if seen else None,
                     seen.state if seen else None, change_id, *(getattr(key, column) for column in KEY_COLUMNS)))
            db.execute("UPDATE changes SET verified_at = ?, updated_at = ? WHERE id = ?", (now_text(), now_text(), change_id))
        return mismatches

    @staticmethod
    def _written_rows(db, change_id):
        return db.execute(
            "SELECT cells.* FROM cells JOIN steps ON steps.change_id = cells.change_id AND steps.idx = cells.step"
            " WHERE cells.change_id = ? AND steps.status = 'saved' ORDER BY cells.rowid", (change_id,)).fetchall()

    @staticmethod
    def _step(row) -> SaveStep:
        return decode_step(dict(room=row["room"], rate_plan=row["rate_plan"], dates=json.loads(row["dates"]),
                                rows=json.loads(row["rows"])))

    def recorded_change(self, change_id: int) -> RecordedChange:
        """되돌리기 계산의 재료 — 실제로 저장이 끝난 칸만."""
        with self._db() as db:
            header = self._header(db, change_id)
            if header["kind"] == "snapshot":
                raise LedgerError("지금 상태 저장으로 되돌리기는 이 판에 아직 없습니다")
            cells = tuple(RecordedCell(_key(row), _before(row),
                                       CellWrite(_key(row), money(row["after_sell"]), money(row["after_list"])))
                          for row in self._written_rows(db, change_id))
        return RecordedChange(header["id"], header["kind"], header["hotel"], header["offer"], header["currency"],
                              header["sentence"], header["read_at"], header["applied_at"], cells)

    def later_writes(self, change_id: int) -> dict[CellKey, list[LaterWrite]]:
        """이 변경 뒤에 같은 호텔·오퍼에 이 장부가 저장한 칸 — 칸마다 오래된 것부터."""
        found: dict[CellKey, list[LaterWrite]] = {}
        with self._db() as db:
            header = self._header(db, change_id)
            rows = db.execute(
                "SELECT cells.*, steps.finished_at, changes.sentence FROM cells"
                " JOIN steps ON steps.change_id = cells.change_id AND steps.idx = cells.step"
                " JOIN changes ON changes.id = cells.change_id"
                " WHERE cells.change_id > ? AND steps.status = 'saved' AND changes.kind != 'snapshot'"
                " AND changes.hotel = ? AND changes.offer = ? ORDER BY cells.change_id, steps.idx",
                (change_id, header["hotel"], header["offer"])).fetchall()
        for row in rows:
            key = _key(row)
            found.setdefault(key, []).append(LaterWrite(row["change_id"], row["finished_at"], row["sentence"],
                                                        CellWrite(key, money(row["after_sell"]), money(row["after_list"]))))
        return found

    def change(self, change_id: int) -> ChangeRecord:
        with self._db() as db:
            header = self._header(db, change_id)
            steps = tuple(StepRecord(row["idx"], self._step(row), row["status"], row["finished_at"], row["note"])
                          for row in db.execute("SELECT * FROM steps WHERE change_id = ? ORDER BY idx", (change_id,)))
            saved = {step.index for step in steps if step.status == "saved"}
            cells = tuple(
                CellRecord(_key(row), _before(row), money(row["after_sell"]), money(row["after_list"]), row["verdict"],
                           bool(row["reserved"]), row["step"], row["step"] in saved, bool(row["verified"]),
                           None if row["seen_state"] is None else CellValue(
                               money(row["seen_sell"]), money(row["seen_list"]), None, row["seen_state"]))
                for row in db.execute("SELECT * FROM cells WHERE change_id = ? ORDER BY rowid", (change_id,)))
        return ChangeRecord(header["id"], header["kind"], header["status"], header["hotel"], header["offer"],
                            header["currency"], header["sentence"], header["read_at"], header["created_at"],
                            header["applied_at"], header["verified_at"], header["reverses"], steps, cells)

    def list_changes(self) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT changes.*, COUNT(cells.room) AS cells,"
                " SUM(CASE WHEN steps.status = 'saved' THEN 1 ELSE 0 END) AS written,"
                " SUM(CASE WHEN steps.status = 'saved' AND cells.verified = 1 THEN 1 ELSE 0 END) AS verified"
                " FROM changes LEFT JOIN cells ON cells.change_id = changes.id"
                " LEFT JOIN steps ON steps.change_id = cells.change_id AND steps.idx = cells.step"
                " GROUP BY changes.id ORDER BY changes.id DESC").fetchall()
        return [dict(id=row["id"], kind=row["kind"], status=row["status"], hotel=row["hotel"], offer=row["offer"],
                     sentence=row["sentence"], read_at=row["read_at"], created_at=row["created_at"],
                     applied_at=row["applied_at"], verified_at=row["verified_at"], reverses=row["reverses"],
                     cells=row["cells"], written=row["written"] or 0, verified=row["verified"] or 0) for row in rows]
