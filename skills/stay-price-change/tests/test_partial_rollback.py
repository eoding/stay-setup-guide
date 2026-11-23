"""변경의 일부만 되돌리기 — 객실·요금제·날짜 범위·인원 조합으로 고르고, 장부는 값마다 어느 되돌리기가 되돌렸는지 적는다.
나중에 "나머지" 를 되돌리면 아직 도우미 것인 칸만 건드린다. 변경 전체 되돌리기는 고르지 않은 같은 길이다.

    python3 -m unittest discover -s tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import scene  # noqa: E402
from change_core.items import Refused  # noqa: E402
from change_core.ledger import DB_NAME, Ledger  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from price_change import listed  # noqa: E402
from price_model import encode_request, encode_snapshot, key_of_item, snapshot_reading  # noqa: E402
from price_pages import render_result, render_rollback  # noqa: E402
from price_plan import (  # noqa: E402
    cell_filter, plan_cell_rollback, plan_change, plan_steps, preview_rows, resolve, rollback_rows, rollback_writes, save_steps,
    step_plans,
)
from test_pages import visible  # noqa: E402


class PartialRollbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / DB_NAME, now=scene.clock)
        plan = resolve(plan_change(scene.snapshot(), scene.request()), [Resolution("ABOVE_LIST", "raise_list")])
        steps = plan_steps(plan)
        self.change = self.ledger.record_preview(hotel=scene.HOTEL, hotel_id=scene.HOTEL_ID, offer=scene.OFFER, currency="USD",
                                                 sentence=scene.SENTENCE, read_at=plan.read_at, rows=preview_rows(plan),
                                                 request=encode_request(plan.request))
        self.ledger.begin(self.change, step_plans(steps), read_at=scene.READ_AGAIN)
        for index in range(1, len(steps) + 1):
            self.ledger.record_step(self.change, index, saved=True)
        self.now = scene.applied(scene.snapshot(), steps, "2026-11-25T09:00:00+09:00")

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, **choose):
        select, scope = cell_filter(**choose)
        return plan_cell_rollback(self.ledger.recorded_change(self.change), self.ledger.later_writes(self.change),
                                  self.now, select=select), scope

    def apply(self, rollback, saved=None):
        rid = self.ledger.record_preview(hotel=rollback.hotel, hotel_id=rollback.hotel_id, offer=rollback.offer, currency=rollback.currency,
                                         sentence="일부 되돌려", read_at=rollback.read_at, rows=rollback_rows(rollback),
                                         reverses=self.change)
        steps = save_steps(rollback_writes(rollback))
        self.ledger.begin(rid, step_plans(steps), read_at=scene.read_after(rollback.read_at))
        for index in range(1, (len(steps) if saved is None else saved) + 1):
            self.ledger.record_step(rid, index, saved=True)
        self.now = scene.applied(self.now, steps[:saved] if saved is not None else steps)
        return rid, steps

    def test_choosing_by_room_rate_plan_date_range_or_occupancy(self):
        by_room, scope = self.plan(rooms=["디럭스"])
        self.assertEqual((len(by_room.restored), scope), (48, "디럭스"))
        by_plan, _ = self.plan(rate_plans=["룸온리"])
        self.assertEqual(len(by_plan.restored), 42)
        by_dates, scope = self.plan(date_from="2027-01-01", date_to="2027-01-31")
        self.assertEqual((len(by_dates.restored), scope), (42, "1/1 금 ~ 1/31 일"))
        by_occupancy, _ = self.plan(rooms=["스위트"], occupancies=["A2C1_CHD"])
        self.assertEqual({key_of_item(item.key).occupancy for item in by_occupancy.restored}, {"A2C1_CHD"})
        self.assertEqual(len(by_occupancy.restored), 14)
        with self.assertRaises(Refused):
            self.plan(rooms=["없는 객실"])

    def test_the_ledger_marks_what_was_rolled_back_and_the_rest_touches_only_what_is_still_ours(self):
        first, _ = self.plan(rooms=["디럭스"])
        rid, _ = self.apply(first)
        record = self.ledger.change(self.change)
        undone = {row.item_key for row in record.rows if row.rolled_back_by == rid}
        self.assertEqual(len(undone), 48)
        self.assertEqual({key_of_item(key).room for key in undone}, {"디럭스"})
        self.assertEqual(len(self.ledger.recorded_change(self.change).items), 42)
        rest, scope = self.plan()
        self.assertEqual(scope, "")
        self.assertEqual({key_of_item(item.key).room for item in rest.restored}, {"스위트"})
        self.assertEqual((len(rest.restored), len(rest.kept)), (42, 0))
        second, _ = self.apply(rest)
        self.assertEqual({row.rolled_back_by for row in self.ledger.change(self.change).rows if row.action},
                         {rid, second})
        listed = {row["id"]: row for row in self.ledger.list_changes()}
        self.assertEqual(listed[self.change]["rolled_back"], 90)
        with self.assertRaises(Refused):
            self.plan()
        self.assertEqual(self.now.cells, scene.snapshot().cells)

    def test_z7_a_rolled_back_change_does_not_look_live_and_the_rest_says_what_was_rolled_back_by_which_record(self):
        def entry(number):
            return next(item for item in listed(self.ledger) if item["id"] == number)

        self.assertEqual(entry(self.change)["status"], "applied")
        first, _ = self.plan(rooms=["디럭스"])
        rid, _ = self.apply(first)
        partly = entry(self.change)
        self.assertEqual((partly["status"], partly["written"], partly["rolled_back"], partly["undone_by"]),
                         ("partly_rolled_back", 90, 48, [rid]))
        self.assertTrue(partly["scope"].endswith(f"판매가 +10% · 일부 되돌림 48/90칸 (장부 {rid}번) · 나머지 42칸은 넣은 값 그대로"),
                        partly["scope"])
        self.assertEqual(entry(rid)["status"], "applied", "되돌리기 자체는 적용된 변경이다")
        self.assertIn(f"{self.change}번 되돌리기", entry(rid)["scope"])

        # 나머지 되돌리기의 미리보기 — 이미 되돌린 부분과 그 번호를 말한다(명령으로)
        folder = Path(self.tmp.name)
        (folder / "now.json").write_text(json.dumps(encode_snapshot(self.now), ensure_ascii=False), encoding="utf-8")
        env = scene.env(str(folder))
        script = str(HERE.parent / "scripts" / "price_change.py")
        done = subprocess.run([sys.executable, script, "rollback", "--change", str(self.change), "--snapshot", str(folder / "now.json"),
                               "--out", str(folder / "rollback-1.json")], capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        short = json.loads(done.stdout)
        self.assertEqual([(item["change_id"], item["sentence"], item["cells"]) for item in short["undone"]], [(rid, "일부 되돌려", 48)])
        self.assertEqual(short["undone"][0]["scope"], "디럭스(룸온리 · 조식 포함) · 12/25 금 ~ 12/26 토 · 1/1 금 ~ 1/2 토 (4일, 2026·2027년)")
        page = subprocess.run([sys.executable, script, "render", "rollback", "--plan", str(folder / "rollback-1.json"), "--out",
                               str(folder / "rollback.html")], capture_output=True, text=True, env=env)
        self.assertEqual(page.returncode, 0, page.stderr)
        text = visible((folder / "rollback.html").read_text(encoding="utf-8"))
        self.assertIn("이 변경 가운데 48칸은 이미 되돌렸습니다. 이번 되돌리기는 그 칸을 건드리지 않고 나머지만 봅니다.", text)
        self.assertIn(f"장부 {rid}번 “일부 되돌려”", text)
        self.assertIn("42 되돌리는 칸", text)

        # 되돌리기의 결과 페이지는 이름도 제목도 「되돌리기 결과」다(Z8)
        made = subprocess.run([sys.executable, script, "render", "result", "--change", str(rid)], capture_output=True, text=True, env=env)
        self.assertEqual(made.returncode, 0, made.stderr)
        result = Path(json.loads(made.stdout)["page"])
        self.assertTrue(result.name.endswith(f" · {scene.HOTEL} · 되돌리기 결과.html"), result.name)
        self.assertIn(f"되돌리기 결과 · {scene.HOTEL} · {scene.OFFER} 장부 {rid}번 · 요청 “일부 되돌려” · {self.change}번 변경을 되돌림",
                      visible(result.read_text(encoding="utf-8")))
        self.assertIn(MARK_ON_ROLLBACK, visible(result.read_text(encoding="utf-8")),
                      "R6 — ERP 의 '손입력' 표시는 도우미가 읽지도 되돌리지도 못한다고 말한다")
        self.assertIn("'손입력' 표시는 되돌리지 않습니다", text, "되돌리기 미리보기도 되돌려도 그대로인 것으로 말한다")
        self.assertIn("읽지도 되돌리지도 못한다", (HERE.parent / "references" / "commands.md").read_text(encoding="utf-8"))

        rest, _ = self.plan()
        second, _ = self.apply(rest)
        whole = entry(self.change)
        self.assertEqual((whole["status"], whole["rolled_back"], whole["undone_by"]), ("rolled_back", 90, [rid, second]))
        self.assertTrue(whole["scope"].endswith(f"모두 되돌림 90/90칸 (장부 {rid}번, {second}번)"), whole["scope"])

    def test_z7_the_reserved_days_heading_appears_only_when_a_rolled_back_cell_is_on_one(self):
        booked, _ = self.plan(rooms=["디럭스"], date_from="2026-12-25", date_to="2026-12-26")
        free, _ = self.plan(rooms=["디럭스"], date_from="2027-01-01")
        self.assertIn("되돌리는 칸 — 예약 있는 날도 포함합니다", visible(render_rollback(booked, self.now.reserved)))
        text = visible(render_rollback(free, self.now.reserved))
        self.assertIn("되돌리는 칸", text)
        self.assertNotIn("예약 있는 날", text)

    def test_a_rollback_stopped_half_way_leaves_the_unsaved_cells_ours(self):
        whole, _ = self.plan()
        rid, steps = self.apply(whole, saved=3)
        still = self.ledger.recorded_change(self.change).items
        self.assertEqual(len(still), 90 - sum(len(s.dates) * len(s.rows) for s in steps[:3]))
        self.assertEqual(self.ledger.change(rid).status, "applying")

    def test_pages_show_the_range_and_the_rolled_back_cells(self):
        first, scope = self.plan(rooms=["디럭스"], date_from="2026-12-25", date_to="2026-12-26")
        text = visible(render_rollback(first, self.now.reserved, scope))
        self.assertIn("되돌리는 범위: 디럭스 / 12/25 금 ~ 12/26 토", text)
        self.assertIn("24 되돌리는 칸", text)
        rid, _ = self.apply(first)
        self.ledger.verify(self.change, snapshot_reading(self.now))
        text = visible(render_result(self.ledger.change(self.change)))
        self.assertIn(f"200.00 → 220.00 되돌림 · 장부 {rid}번", text)
        self.assertIn("적용했고, 다시 읽어 확인했습니다. 66칸 모두 넣은 값과 같습니다.", text)
        self.assertIn(f"이 변경의 24칸은 뒤에 되돌렸습니다(장부 {rid}번).", text)
        self.assertIn("300.00 → 330.00 확인", text)

    def test_the_command_takes_the_same_choices(self):
        folder = Path(self.tmp.name)
        (folder / "now.json").write_text(json.dumps(encode_snapshot(self.now), ensure_ascii=False), encoding="utf-8")
        done = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "price_change.py"), "rollback",
                               "--change", str(self.change), "--snapshot", str(folder / "now.json"), "--room", "스위트",
                               "--rate-plan", "룸온리", "--from", "2027-01-01"],
                              capture_output=True, text=True, env=scene.env(str(folder)))
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual((result["scope"], len(result["rollback"]["restored"]), len(result["steps"])),
                         (f"객실 가격 · {scene.OFFER} · 스위트(룸온리) · 1/1 금 (1일, 2027년) · {self.change}번 되돌리기 (스위트 / 룸온리 / 1/1 금 ~ 끝만)", 6, 1),
                         "범위는 종류 · 오퍼 · 되돌리는 칸 · 한 일 · 고른 칸 — 장부 목록의 줄과 같은 셈")


MARK_ON_ROLLBACK = "되돌린 칸도 ERP 에서 '손입력'으로 표시됩니다. 이 표시는 도우미가 읽지도 되돌리지도 못해, 넣기 전의 표시로 돌아가지 않습니다."


if __name__ == "__main__":
    unittest.main()
