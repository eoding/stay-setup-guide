"""검토 3 의 모델 시험 — 바꾸기 · 되돌리기(아무 앞 기록이나, 되돌리기 · 저장 상태로 되돌리기까지, 모두 또는 일부, 그 사이 달라진
칸도 포함해서) · 지금 상태 저장 · 저장 상태로 되돌리기 · 도우미 밖의 손을 정해진 씨앗으로 섞은 차례 수백 개를, 메모리 속의 작은
ERP(모델)와 장부에 같이 한다. 걸음마다 — 장부가 말하는 살아 있는 값(칸마다 · 기록마다), 목록의 상태와 수, 기록마다 지금 되돌리자고
하면 되돌릴 것(되돌릴 것이 없다는 답까지)이 모델과 같은지 본다.

모델은 ERP 의 참값과, 장부가 알 수 있는 만큼의 「누구의 값인가」를 걸음마다 바로 고친다(장부는 저장된 값들을 저장한 차례로 다시
따라가 셈한다 — change_core.alive). 규칙은 같은 말이다:

- 칸에 넣은 기록이 그 칸의 값의 임자다. 되돌리기가 되돌리는 기록이 그 칸의 임자이면, 그 기록이 그 칸에 넣을 때 덮은 임자들이 다시
  임자가 되고 되돌리기도 임자다. 저장 상태로 되돌리기는 그 저장 때의 임자들을 다시 임자로 한다. 그 밖의 넣기는 그 기록만 임자다.
- 임자에서 빠진 기록은 — 되돌리기(되돌리는 기록이 임자였을 때)나 저장 상태로 되돌리기가 뺐으면 그것이 「되돌린」 것이고, 아니면
  덮였을 뿐이다. 되돌리는 기록이 임자가 아닌 칸을 되돌리기가 넣으면(그 사이 달라진 칸도 포함) 그 기록은 그 칸에서 「되돌린」 것이다.
- 되돌린 기록이 다시 임자가 되면 「되돌렸다가 다시 살림」이다.
- 도우미 밖의 손은 임자를 지운다 — 장부는 그 칸을 다시 넣을 때에야 안다(그때까지 장부의 셈은 옛 임자를 댄다). 밖의 손은 늘 처음
  보는 값을 넣는다(어느 기록의 값과 우연히 같지 않게).

되돌리기가 되돌리는 것은 그 기록이 저장했고 아직 되돌리지 않은 칸 가운데 ERP 가 지금도 그 기록이 넣은 값을 갖는 항목이다(기존 규칙).

    python3 -m unittest discover -s tests
"""

import random
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from change_core.files import record_progress  # noqa: E402
from change_core.items import ItemState, Refused  # noqa: E402
from change_core.ledger import DB_NAME, FieldWrite, Ledger, StepPlan, ValueRow  # noqa: E402
from change_core.rollback import plan_restore, plan_rollback  # noqa: E402

SEQUENCES = 300
STEPS = 12
KIND, HOTEL, HOTEL_ID, OFFER = "cell", "모델 호텔", "1", "모델 오퍼"
ITEMS = ("c1", "c2", "c3", "c4")
FIELDS = ("sell", "list")
POOL = tuple(Decimal(value) for value in range(100, 180, 10))    # 바꾸기가 넣는 값 — 좁게 골라 기록끼리 값이 자주 겹친다
START = datetime.fromisoformat("2026-11-21T10:00:00+09:00")


@dataclass
class Record:
    """모델의 기록 하나 — 무엇(change · rollback · restore · snapshot), 되돌리는 기록 · 저장 번호, 칸마다 (전 값, 넣은 값) 가운데
    저장된 것, 다 적용했는지(멈췄으면 False)."""
    kind: str
    undoes: int | None = None
    restores: int | None = None
    writes: dict = field(default_factory=dict)
    finished: bool = False


@dataclass(frozen=True)
class Now:
    """기록 하나가 넣은 칸 하나의 지금 — 임자인지 · 되돌린 기록 · 되돌렸다가 다시 살렸으면 (되돌린 기록, 다시 살린 기록)."""
    live: bool
    undone_by: int | None = None
    redone: tuple | None = None


class Model:
    """작은 ERP(칸 → 참값)와, 장부가 알 수 있는 만큼의 임자."""

    def __init__(self):
        self.value = {(item, name): Decimal(200 + 10 * index) for index, (item, name) in
                      enumerate((item, name) for item in ITEMS for name in FIELDS)}
        self.owners: dict = {}          # 칸 → 임자들(장부가 알 수 있는 만큼 — 밖의 손은 그 칸을 다시 넣을 때 안다)
        self.touched: set = set()       # 도우미 밖의 손이 탄 뒤 아직 도우미가 다시 넣지 않은 칸
        self.covered: dict = {}         # (기록, 칸) → 그 기록이 그 칸에 넣을 때 덮은 임자들
        self.now: dict = {}             # (기록, 칸) → Now
        self.saved_owners: dict = {}    # (저장 번호, 칸) → 그 저장 때의 임자들(밖의 손이 탄 칸이면 없음)
        self.saved_values: dict = {}    # (저장 번호, 칸) → 그 저장 때의 참값
        self.records: dict = {}
        self.fresh = 9000

    def put(self, number: int, cell, before: Decimal, after: Decimal) -> None:
        """기록 `number` 의 저장 하나가 칸에 값을 넣었다."""
        record = self.records[number]
        assert self.value[cell] == before
        owners = self.owners.get(cell, frozenset())
        if cell in self.touched:          # 밖의 손이 먼저 덮었다 — 옛 임자들은 그때 덮였다
            for old in owners:
                self.now[(old, cell)] = Now(False)
            owners = frozenset()
            self.touched.discard(cell)
        self.covered[(number, cell)] = owners
        undoing = True
        if record.kind == "rollback" and record.undoes in owners:
            new = {number} | self.covered[(record.undoes, cell)]
        elif record.kind == "restore":
            new = {number} | self.saved_owners.get((record.restores, cell), frozenset())
        else:
            new, undoing = {number}, False
            if record.kind == "rollback" and (record.undoes, cell) in self.now:
                self.now[(record.undoes, cell)] = Now(False, undone_by=number)
        for old in owners - new:
            self.now[(old, cell)] = Now(False, undone_by=number if undoing else None)
        for back in new - owners - {number}:
            was = self.now.get((back, cell))
            self.now[(back, cell)] = Now(True, redone=(was.undone_by, number) if was and was.undone_by else None)
        self.now[(number, cell)] = Now(True)
        self.owners[cell] = frozenset(new)
        self.value[cell] = after
        record.writes[cell] = (before, after)

    def snapshot(self, number: int) -> None:
        for cell in self.value:
            self.saved_values[(number, cell)] = self.value[cell]
            if cell in self.owners and cell not in self.touched:
                self.saved_owners[(number, cell)] = self.owners[cell]

    def outside(self, cell) -> None:
        self.fresh += 1
        self.value[cell] = Decimal(self.fresh)
        self.touched.add(cell)

    def items_of(self, number: int) -> dict:
        """기록이 저장한 항목마다 필드 → Now."""
        found: dict = {}
        for (item, name) in self.records[number].writes:
            found.setdefault(item, {})[name] = self.now[(number, (item, name))]
        return found

    def listed(self, number: int) -> dict:
        items = self.items_of(number)
        undone = {item for item, fields in items.items() if any(now.undone_by for now in fields.values())}
        redone = {item for item, fields in items.items() if item not in undone and any(now.redone for now in fields.values())}
        record = self.records[number]
        status = "applied" if record.finished else "stopped"
        if items and undone:
            status = "rolled_back" if len(undone) == len(items) else "partly_rolled_back"
        return dict(status=status, written=len(items), rolled_back=len(undone),
                    undone_by=sorted({now.undone_by for item in undone for now in items[item].values() if now.undone_by}),
                    redone=len(redone), redone_by=sorted({n for item in redone for now in items[item].values() if now.redone
                                                          for n in now.redone}),
                    live=sum(all(now.live for now in fields.values()) for fields in items.values()))

    def offer(self, number: int, chosen, include_kept: bool):
        """그 기록을 지금 되돌리자고 하면 — None(되돌릴 것이 없다는 답) 또는 (되돌릴 항목들, 그대로 둘 항목들)."""
        record = self.records[number]
        ours = {item: {name: record.writes[(item, name)] for name, now in fields.items() if now.undone_by is None}
                for item, fields in self.items_of(number).items()}
        ours = {item: fields for item, fields in ours.items() if fields}
        if not ours:
            return None
        picked = {item: fields for item, fields in ours.items() if item in chosen}
        if not picked:
            return "nothing chosen"
        restored, kept = set(), set()
        for item, fields in picked.items():
            if all(self.value[(item, name)] == after for name, (_before, after) in fields.items()):
                restored.add(item)
                continue
            kept.add(item)
            if include_kept and any(self.value[(item, name)] != before for name, (before, _after) in fields.items()):
                restored.add(item)
        return restored, kept


class AliveModelTest(unittest.TestCase):
    """씨앗마다 STEPS 걸음 — 걸음마다 장부와 모델을 견준다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    # ── 장부 쪽 ──
    def tick(self, seconds: int = 1) -> str:
        self.t += timedelta(seconds=seconds)
        return self.t.isoformat(timespec="seconds")

    def reading(self):
        return {(KIND, item): ItemState(item, "open", {name: self.model.value[(item, name)] for name in FIELDS}) for item in ITEMS}

    def apply(self, number: int, rows: list, request=None, reverses=None) -> None:
        """미리보기를 적고, 항목을 저장 한두 번에 나눠 begin · 저장한다 — 가끔 중간에 멈춘다(그 뒤 저장은 실패)."""
        read_at = self.tick()
        self.tick()
        recorded = self.ledger.record_preview(hotel=HOTEL, hotel_id=HOTEL_ID, offer=OFFER, currency="USD", sentence=f"걸음 {self.step}",
                                              read_at=read_at, rows=rows, request=request, reverses=reverses)
        assert recorded == number, (recorded, number)
        items = sorted({row.item_key for row in rows})
        cut = self.random.randint(1, len(items) - 1) if len(items) > 1 and self.random.random() < 0.5 else len(items)
        groups = [items[:cut], items[cut:]] if cut < len(items) else [items]
        steps = [StepPlan("save", f"{index}번째", {"items": group},
                          tuple(FieldWrite(KIND, row.item_key, row.field, row.after) for row in rows if row.item_key in group))
                 for index, group in enumerate(groups, 1)]
        self.ledger.begin(number, steps, read_at=self.tick())
        stop = len(steps) + 1 if self.random.random() < 0.85 else self.random.randint(1, len(steps))
        for index, step in enumerate(steps, 1):
            self.tick()
            if index == stop:
                self.ledger.record_step(number, index, saved=False, note="저장하지 못했습니다")
                self.log.append(f"  {number}번 {index}번째 저장에서 멈춤")
                return
            self.ledger.record_step(number, index, saved=True)
            for write in step.writes:
                self.model.put(number, (write.item_key, write.field), self.model.value[(write.item_key, write.field)], write.after)
        self.model.records[number].finished = True

    def next_number(self) -> int:
        return len(self.model.records) + 1

    # ── 걸음 ──
    def change(self) -> None:
        number = self.next_number()
        self.model.records[number] = Record("change")
        rows = []
        for item in self.random.sample(ITEMS, self.random.randint(1, 3)):
            for name in self.random.sample(FIELDS, self.random.randint(1, 2)):
                now = self.model.value[(item, name)]
                rows.append(ValueRow(KIND, item, item, name, "open", now, self.random.choice([v for v in POOL if v != now]),
                                     action="set"))
        self.log.append(f"{number}번 바꾸기 {[(row.item_key, row.field, str(row.after)) for row in rows]}")
        self.apply(number, rows)

    def rollback(self) -> None:
        targets = [number for number, record in self.model.records.items() if record.kind != "snapshot"]
        if not targets:
            return self.change()
        target = self.random.choice(targets)
        chosen = set(ITEMS) if self.random.random() < 0.6 else set(self.random.sample(ITEMS, self.random.randint(1, 3)))
        include_kept = self.random.random() < 0.2
        expected = self.model.offer(target, chosen, include_kept)
        self.log.append(f"{target}번 되돌리기 {sorted(chosen)}{' (달라진 칸도)' if include_kept else ''} → 모델 {expected}")
        plan = self.plan(target, chosen, include_kept)
        self.assertEqual(self.offered(plan), expected, self.story(f"{target}번 되돌리기의 계산"))
        if isinstance(plan, str) or not plan.restored:
            return
        kind = self.model.records[target].kind
        self.seen.add({"rollback": "rollback of a rollback", "restore": "rollback of a restore"}.get(kind, "rollback of a change"))
        if any(self.model.value[(item.key, name)] >= 9000 for item in plan.kept for name in item.written):
            self.seen.add("kept after an outside edit")
        number = self.next_number()
        self.model.records[number] = Record("rollback", undoes=target)
        rows = [ValueRow(KIND, item.key, item.label, name, "open", item.now.fields[name], value, action="set")
                for item in plan.restored for name, value in item.targets.items()]
        self.apply(number, rows, request=dict(kind="rollback", scope=sorted(chosen)) if chosen != set(ITEMS) else None,
                   reverses=target)

    def plan(self, target: int, chosen, include_kept: bool = False):
        """장부로 되돌리기 계산 — 되돌릴 것이 없다는 답이면 그 글자."""
        try:
            return plan_rollback(self.ledger.recorded_change(target), self.ledger.later_writes(target), self.reading(), self.t.isoformat(),
                                 include_kept, lambda kind, key: key in chosen)
        except Refused as refused:
            return str(refused)

    @staticmethod
    def offered(plan):
        if isinstance(plan, str):
            return None if "아직 되돌리지 않은 것이 없습니다" in plan else "nothing chosen"
        return {item.key for item in plan.restored}, {item.key for item in plan.kept}

    def snapshot(self) -> None:
        number = self.next_number()
        self.model.records[number] = Record("snapshot")
        self.tick()
        recorded = self.ledger.record_snapshot(
            hotel=HOTEL, hotel_id=HOTEL_ID, offer=OFFER, currency="USD", sentence="지금 상태", read_at=self.t.isoformat(),
            rows=[ValueRow(KIND, item, item, name, "open", self.model.value[(item, name)]) for item in ITEMS for name in FIELDS])
        assert recorded == number
        self.model.snapshot(number)
        self.model.records[number].finished = True
        self.log.append(f"{number}번 지금 상태 저장 {dict((f'{i}.{n}', str(v)) for (i, n), v in self.model.value.items())}")

    def restore(self) -> None:
        saved = [number for number, record in self.model.records.items() if record.kind == "snapshot"]
        if not saved:
            return self.snapshot()
        target = self.random.choice(saved)
        chosen = set(ITEMS) if self.random.random() < 0.6 else set(self.random.sample(ITEMS, self.random.randint(1, 3)))
        plan = plan_restore(self.ledger.recorded_snapshot(target), self.reading(), self.t.isoformat(), lambda kind, key: key in chosen)
        self.log.append(f"{target}번 저장 상태로 되돌리기 {sorted(chosen)} → {len(plan.restored)}항목")
        self.assertEqual({item.key for item in plan.restored},
                         {item for item in chosen if any(self.model.value[(item, name)] != self.model.saved_values[(target, (item, name))]
                                                         for name in FIELDS)}, self.story(f"{target}번 저장 상태로 되돌리기의 계산"))
        if not plan.restored:
            return
        number = self.next_number()
        self.model.records[number] = Record("restore", restores=target)
        rows = [ValueRow(KIND, item.key, item.label, name, "open", item.now.fields[name], value, action="set")
                for item in plan.restored for name, value in item.targets.items()]
        self.apply(number, rows, request=dict(kind="restore_snapshot", snapshot=target, scope=sorted(chosen)))

    def outside(self) -> None:
        cell = (self.random.choice(ITEMS), self.random.choice(FIELDS))
        self.model.outside(cell)
        self.log.append(f"도우미 밖에서 {cell} = {self.model.value[cell]}")

    # ── 견주기 ──
    def story(self, what: str) -> str:
        return f"씨앗 {self.seed} · 걸음 {self.step} · {what}\n" + "\n".join(self.log)

    def compare(self) -> None:
        listed = {entry["id"]: entry for entry in self.ledger.list_changes()}
        for number, record in self.model.records.items():
            if record.kind == "snapshot":
                continue
            entry, want = listed[number], self.model.listed(number)
            self.assertEqual({key: entry[key] for key in want}, want, self.story(f"목록의 {number}번"))
            self.assertEqual("되돌렸다가 다시 살림" in record_progress(entry, "칸"), bool(want["redone"]), self.story(f"{number}번 줄"))
            rows = {(row.item_key, row.field): (row.live, row.rolled_back_by, row.redone)
                    for row in self.ledger.change(number).rows if row.written}
            self.assertEqual(rows, {cell: (self.model.now[(number, cell)].live, self.model.now[(number, cell)].undone_by,
                                           self.model.now[(number, cell)].redone) for cell in record.writes},
                             self.story(f"장부가 말하는 {number}번의 칸마다 지금"))
            self.assertEqual(sorted(entry["change_id"] for entry in self.ledger.undone(number)), want["undone_by"],
                             self.story(f"{number}번을 되돌린 기록"))
            self.assertEqual(self.offered(self.plan(number, set(ITEMS))), self.model.offer(number, set(ITEMS), False),
                             self.story(f"지금 {number}번을 되돌리면"))

    def run_sequence(self, seed: int) -> None:
        self.seed, self.random, self.model, self.log = seed, random.Random(seed), Model(), []
        self.t = START
        path = Path(self.tmp.name) / f"{seed}" / DB_NAME
        path.parent.mkdir()
        self.ledger = Ledger(path, now=lambda: self.t)
        moves = (self.change, self.rollback, self.snapshot, self.restore, self.outside)
        for self.step in range(1, STEPS + 1):
            self.random.choices(moves, weights=(30, 40, 10, 10, 10))[0]()
            self.compare()

    def test_the_ledger_agrees_with_the_model_after_every_step(self):
        """씨앗마다 견주고, 끝에 그 씨앗들이 정말 그 길들을 지났는지 본다 — 되돌리기 · 저장 상태로 되돌리기를 되돌린 기록, 다시 살린 칸,
        일부만 되돌려진 기록, 멈춘 되돌리기, 밖의 손이 탄 칸을 되돌리기가 그대로 둔 경우."""
        self.seen = set()
        for seed in range(SEQUENCES):
            self.run_sequence(seed)
            for number, record in self.model.records.items():
                if record.kind == "snapshot":
                    continue
                if record.kind == "rollback" and not record.finished:
                    self.seen.add("stopped rollback")
                listed = self.model.listed(number)
                if listed["redone"]:
                    self.seen.add("redone")
                if listed["status"] == "partly_rolled_back":
                    self.seen.add("partly rolled back")
        self.assertEqual(self.seen, {"rollback of a change", "rollback of a rollback", "rollback of a restore", "stopped rollback",
                                     "redone", "partly rolled back", "kept after an outside edit"})


if __name__ == "__main__":
    unittest.main()
