"""시즌 다시 채우기와 장부 — 새 표 없이 가격 칸의 장부를 그대로 쓴다. 다시 계산한 시즌 미리보기는 같은 시즌의 미리보기만 바꾸고, 목록의
한 줄은 「시즌 「이름」 다시 채우기(덮기|빈 칸만)[ · 날짜 일부] · 저장 N번」이다. 확인(verify)은 값 · ERP 가 말한 칸 수 · 새 칸의 판매
상태가 모두 맞을 때만 같다고 하고, 허용 인원 조합을 몰라 ERP 가 뺐을 수 있는 칸은 칸이 없어도 받아들인다.
"""

import os
import sys
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import scene  # noqa: E402
import season_scene  # noqa: E402
from change_core.ledger import LEDGER_ENV, Ledger, LedgerError  # noqa: E402
from price_model import CellKey, CellValue, encode_snapshot, snapshot_reading  # noqa: E402
from price_season import SeasonChoice, plan_season, recorded_request, season_steps, season_what  # noqa: E402
from price_season_cli import season_rows, verify_season  # noqa: E402

DELUXE = ("디럭스", "조식 포함")


class SeasonLedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ[LEDGER_ENV] = self.tmp.name
        self.ledger = Ledger(Path(self.tmp.name) / "장부.sqlite3", now=scene.clock, kind="price_cell")

    def tearDown(self):
        os.environ.pop(LEDGER_ENV, None)
        self.tmp.cleanup()

    def plan(self, window=None, before=None, choices=(), **save):
        fields = dict(pairs=[list(DELUXE)], price="180", occupancy_keys="A2", dates=["2026-12-01"])
        fields.update(save)
        snapshot = replace(season_scene.snapshot((), pairs=[DELUXE]), cells=before or {})
        plan = plan_season(snapshot, window or season_scene.window(), season_scene.fill_of(season_scene.save_of(fields)), choices)
        return snapshot, plan

    def record(self, snapshot, plan, replaces=None):
        return self.ledger.record_preview(hotel=snapshot.hotel, hotel_id=snapshot.hotel_id, offer=snapshot.offer, currency="USD",
                                          sentence="시즌 다시 채우기", read_at=snapshot.read_at, rows=season_rows(plan),
                                          request=recorded_request(plan), reading=encode_snapshot(snapshot), replaces=replaces)

    def apply(self, snapshot, plan, change_id, note):
        steps = season_steps(plan)
        self.ledger.begin(change_id, steps, recorded_request(plan), read_at=scene.read_after(snapshot.read_at))
        for step in self.ledger.change(change_id).steps:
            self.ledger.record_step(change_id, step.index, True, note)

    def test_a_season_preview_replaces_only_a_season_preview_of_the_same_season(self):
        snapshot, plan = self.plan(choices=[SeasonChoice(1, "NEW_ROW", "include", "응")])
        first = self.record(snapshot, plan)
        self.record(snapshot, plan, replaces=first)
        change = self.ledger.record_preview(hotel=snapshot.hotel, hotel_id=snapshot.hotel_id, offer=snapshot.offer, currency="USD",
                                            sentence="10% 올려", read_at=snapshot.read_at, rows=[], request={"kind": "change"})
        with self.assertRaises(LedgerError) as caught:
            self.record(snapshot, plan, replaces=change)
        self.assertIn("가격 바꾸기 미리보기이고 이 계산은 시즌 8801 다시 채우기", str(caught.exception))

    def test_the_list_line_names_the_season_overwrite_and_the_save_count(self):
        _snapshot, plan = self.plan(choices=[SeasonChoice(1, "NEW_ROW", "include", "응")])
        self.assertEqual(season_what(recorded_request(plan)), "시즌 「Peak」 다시 채우기(덮기) · 날짜 일부 · 저장 1번")
        _snapshot, plan = self.plan(choices=[SeasonChoice(1, "NEW_ROW", "include", "응")], overwrite=False, dates=None)
        self.assertEqual(season_what(recorded_request(plan)), "시즌 「Peak」 다시 채우기(빈 칸만) · 저장 1번")

    def test_verify_says_same_only_when_values_counts_and_new_cell_states_all_agree(self):
        before = {CellKey(*DELUXE, "2026-12-01", "A2", 1): CellValue(D("170"), None, None, "open")}
        snapshot, plan = self.plan(before=before)
        change = self.record(snapshot, plan)
        self.apply(snapshot, plan, change, "가격을 넣었습니다 — 새로 0칸 · 덮어쓴 1칸 (룸 1개 × 1일).")
        after = replace(snapshot, cells={**before, CellKey(*DELUXE, "2026-12-01", "A2", 1): CellValue(D("180"), None, None, "open")})
        mismatches = self.ledger.verify(change, snapshot_reading(after))
        self.assertTrue(verify_season(self.ledger, change, after, mismatches)["same"])
        other = self.record(snapshot, plan)
        self.apply(snapshot, plan, other, "가격을 넣었습니다 — 새로 1칸 · 덮어쓴 0칸 (룸 1개 × 1일).")
        told = verify_season(self.ledger, other, after, self.ledger.verify(other, snapshot_reading(after)))
        self.assertEqual((told["same"], told["mismatches"], told["counts"][0]["agree"]), (False, [], False),
                         "값이 모두 맞아도 ERP 가 말한 칸 수가 다르면 같다고 하지 않는다")

    def test_a_cell_that_differs_from_the_prediction_is_never_called_verified(self):
        snapshot, plan = self.plan(before={CellKey(*DELUXE, "2026-12-01", "A2", 1): CellValue(D("170"), None, None, "open")})
        change = self.record(snapshot, plan)
        self.apply(snapshot, plan, change, "가격을 넣었습니다 — 새로 0칸 · 덮어쓴 1칸 (룸 1개 × 1일).")
        wrong = replace(snapshot, cells={CellKey(*DELUXE, "2026-12-01", "A2", 1): CellValue(D("179"), None, None, "open")})
        told = verify_season(self.ledger, change, wrong, self.ledger.verify(change, snapshot_reading(wrong)))
        self.assertEqual((told["same"], [item["seen"] for item in told["mismatches"]]), (False, ["179"]))

    def test_left_out_combo_cells_are_accepted_and_a_state_only_difference_is_reported(self):
        window = season_scene.window(bands=[{"code": "CHD", "basis": "flat", "value": "20"}])
        window = replace(window, combos={**window.combos, "디럭스": None})
        snapshot, plan = self.plan(window=window, choices=[SeasonChoice(1, "NEW_ROW", "include", "응")])
        change = self.record(snapshot, plan)
        self.apply(snapshot, plan, change, "가격을 넣었습니다 — 새로 1칸 · 덮어쓴 0칸 (룸 1개 × 1일).")
        only_adult = replace(snapshot, cells={CellKey(*DELUXE, "2026-12-01", "A2", 1): CellValue(D("180"), None, None, "closed")})
        told = verify_season(self.ledger, change, only_adult, self.ledger.verify(change, snapshot_reading(only_adult)))
        self.assertEqual([item["key"]["occupancy"] for item in told["left_out"]], ["A2C1_CHD"], "ERP 가 조합으로 뺀 칸은 받아들인다")
        self.assertEqual(told["mismatches"], [])
        self.assertEqual([(item["want"], item["seen"]) for item in told["state_only"]], [("open", "closed")], "판매 상태만 다름")
        self.assertFalse(told["same"])


if __name__ == "__main__":
    unittest.main()
