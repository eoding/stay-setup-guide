"""검토 2 · 5 — 아동이 든 칸은 성인만 있는 칸을 따라 그대로 두고, 나중 차례에 걸린 박수 층 칸도 칸마다 고른다.

검토 2: 금액 · 퍼센트(그리고 같은 셈인 새 값 지정)로 바꿀 때 같은 객실 · 요금제 · 날짜 · 박수 층의 성인만 있는 칸이 새 판매가를 받지
않으면(빨간 줄에 안 바꿈 · 적용할 수 없음 · 박수 층 규칙) 그 성인 수의 아동 칸도 움직이지 않는다 — ERP
`bulk_price_adjust._skip_followers_of_skipped_adult_cells`(2026-11-13 QA 고침)와 같고, 박수 층 규칙과 더 바뀌지 않을 때까지 같이 돈다.
그런 칸은 미리보기에 「성인만 있는 칸을 바꾸지 않아 같이 그대로 둡니다」로 보이고, 세어지고, 저장하지 않는다.

ERP 와 견줄 때의 고름: ERP 는 정가보다 비싸지는 칸(「정가도 같이 조정」을 끈 때)과 박수 층 규칙의 칸을 건너뛰고, 공급 원가 · 30%
확인은 없다 — 그래서 정가 넘음은 안 바꿈, 박수 층도 안 바꿈, 공급 원가 · 30% 는 이대로 바꿈으로 고른 계산이 ERP 의 결과다.
아래 표의 기대값은 ERP 의 `build_preview`(정액 · 정률 · 성인 칸 · 건너뜀 차례 · 고리)를 손으로 따라 셈한 것이다.

검토 5: 다른 박수 층 칸을 「이대로 바꿈」으로 고른 뒤에야 걸리는 칸이 있다. 그 칸을 짚은 고름도 받는다.

    python3 -m unittest discover -s tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from price_model import (  # noqa: E402
    CellKey, CellValue, ChangeRequest, Snapshot, Target, TargetTable, cell_item_key, encode_key, encode_request, encode_snapshot,
)
from price_pages import render_preview, unused_lines  # noqa: E402
from price_plan import counts, plan_change, plan_steps, plan_targets, preview_rows, resolve  # noqa: E402
from test_pages import visible  # noqa: E402

DAY = "2026-12-24"
LIKE_ERP = (Resolution("ABOVE_LIST", "keep"), Resolution("ABOVE_ONE_NIGHT", "keep"), Resolution("BELOW_COST", "include"),
            Resolution("OVER_30", "include"))
CHILD = "A2C1_CHD"


def snap(cells) -> Snapshot:
    """`{(인원, 박수): 판매가 또는 (판매가, 정가)}` → 객실 R · 요금제 P · 하루."""
    def value(item):
        sell, listed = item if isinstance(item, tuple) else (item, None)
        return CellValue(D(sell), None if listed is None else D(listed), None, "open")
    return Snapshot("H", "O", "USD", "2026-11-20T10:00:00+09:00",
                    {CellKey("R", "P", DAY, occupancy, nights): value(item) for (occupancy, nights), item in cells.items()},
                    frozenset(), frozenset({("R", "P")}), hotel_id="9")


def ask(operation, value, **over) -> ChangeRequest:
    return ChangeRequest(hotel="H", hotel_id="9", offer="O", rooms=("R",), rate_plans=("P",), dates=(DAY,), operation=operation,
                         value=D(value), **over)


# (이름, 칸들, 요청, ERP 의 결과 {(인원, 박수): ("moves", 새 판매가) | ("stays", 그 칸의 판정)}, build_preview 를 손으로 따라 셈한 것)
# 판정의 짝: ERP ABOVE_ORIGINAL = ABOVE_LIST(안 바꿈) · ADULT_CELL_SKIPPED = ADULT_HELD · ABOVE_ONE_NIGHT · NOT_POSITIVE 는 같은 이름.
CASES = (
    ("검토의 장면 — 성인 1박 이상이 정가를 넘어 그대로",
     {("A2", 1): ("480.00", "500.00"), ("A2", 3): "432.00", (CHILD, 1): "510.00", (CHILD, 3): "459.00"},
     ask("percent", "10"),
     {("A2", 1): ("stays", "ABOVE_LIST"), ("A2", 3): ("moves", "475.20"), (CHILD, 1): ("stays", "ADULT_HELD"),
      (CHILD, 3): ("moves", "502.20")},
     "성인 1박 scaled(480)=528 > 정가 500 → 정가 초과 · 아동 1박 528+30=558 이지만 성인 칸을 건너뛰어 따라 건너뜀(510 그대로) · "
     "성인 3박 475.20 · 아동 3박 475.20+27=502.20 · 박수 층: 475.20 < 480, 502.20 < 510"),
    ("금액 — 성인 칸이 0 이하",
     {("A2", 1): "90.00", (CHILD, 1): "120.00"}, ask("amount", "-100"),
     {("A2", 1): ("stays", "NOT_POSITIVE"), (CHILD, 1): ("stays", "ADULT_HELD")},
     "성인 90−100=−10 ≤ 0 → 0 이하 · 아동 120−100=20 이지만 성인 칸을 건너뛰어 따라 건너뜀"),
    ("박수 층 — 성인 3박 이상이 1박 이상보다 비싸져 그대로",
     {("A2", 1): "100.00", ("A2", 3): "90.00", (CHILD, 1): "160.00", (CHILD, 3): "117.00"}, ask("amount", "20", nights=(3,)),
     {("A2", 3): ("stays", "ABOVE_ONE_NIGHT"), (CHILD, 3): ("stays", "ADULT_HELD")},
     "3박만 고름 · 성인 3박 110 > 성인 1박 100(고르지 않은 층) → 박수 층 · 아동 3박 137 < 160 이지만 둘째 고리에서 성인 3박을 따라 건너뜀"),
    ("고리 — 따라 그대로 둔 아동 1박 이상 때문에 아동 3박 이상이 박수 층에 걸린다",
     {("A2", 1): ("480.00", "500.00"), ("A2", 3): "430.00", (CHILD, 1): "500.00", (CHILD, 3): "480.00"}, ask("percent", "10"),
     {("A2", 1): ("stays", "ABOVE_LIST"), ("A2", 3): ("moves", "473.00"), (CHILD, 1): ("stays", "ADULT_HELD"),
      (CHILD, 3): ("stays", "ABOVE_ONE_NIGHT")},
     "성인 1박 528 > 500 → 정가 초과 · 아동 1박 528+20=548 → 따라 건너뜀(500 그대로) · 성인 3박 473 < 480 · "
     "아동 3박 473+50=523 > 아동 1박 지금 값 500 → 박수 층(따르기 전이면 548 과 견줘 지나갔다)"),
    ("성인 칸을 고르지 않으면 아동 칸만 옮긴다",
     {("A2", 1): ("480.00", "500.00"), (CHILD, 1): "510.00"}, ask("percent", "10", occupancies=(CHILD,)),
     {(CHILD, 1): ("moves", "558.00")},
     "대상은 아동 칸뿐 — 성인 칸(정가를 넘을 칸)은 고른 칸이 아니라 따르지 않는다 · 아동 scaled(480)+30=558"),
    ("제 까닭이 먼저 — 아동 칸도 0 이하",
     {("A2", 1): "90.00", (CHILD, 1): "120.00"}, ask("amount", "-500"),
     {("A2", 1): ("stays", "NOT_POSITIVE"), (CHILD, 1): ("stays", "NOT_POSITIVE")},
     "성인 −410 · 아동 −380 — 아동 칸은 제 까닭(0 이하)으로 먼저 건너뛴다"),
    ("아동 추가분도 같이 바꿔도 따른다",
     {("A2", 1): ("480.00", "500.00"), (CHILD, 1): "510.00"}, ask("percent", "10", scale_child_surcharge=True),
     {("A2", 1): ("stays", "ABOVE_LIST"), (CHILD, 1): ("stays", "ADULT_HELD")},
     "아동 scaled(510)=561 이지만 성인 칸을 건너뛰어 따라 건너뜀 — ERP 의 _adult_key 는 「추가 인원 요금도 같이」와 상관없다"),
)


def outcome(plan, key) -> tuple[str, str]:
    change = next(change for change in plan.changes if change.key == key)
    if change.writes:
        return "moves", str(change.writes["sell"])
    return "stays", change.verdict


class AdultFollowTest(unittest.TestCase):
    def test_a_case_table_worked_by_hand_from_the_erp_function(self):
        for name, cells, request, expected, worked in CASES:
            with self.subTest(name, worked=worked):
                plan = resolve(plan_change(snap(cells), request), LIKE_ERP)
                got = {(key.occupancy, key.nights): outcome(plan, key) for key in (c.key for c in plan.changes)}
                self.assertEqual(got, expected)
                written = {(row.occupancy, row.nights): str(row.sell) for step in plan_steps(plan) for row in step.rows}
                self.assertEqual(written, {cell: value for cell, (what, value) in expected.items() if what == "moves"},
                                 "저장 단계는 움직이는 칸만 쓴다")

    def test_the_reviewers_scene_case_keeps_the_child_cell_at_510_and_says_why(self):
        plan = resolve(plan_change(scene.snapshot(), scene.request()), [Resolution("ABOVE_LIST", "keep", said="그 칸은 그냥 둬")])
        for day in ("2027-01-01", "2027-01-02"):
            adult, child = (CellKey("스위트", "조식 포함", day, occupancy, 1) for occupancy in ("A2", CHILD))
            self.assertEqual((outcome(plan, adult), outcome(plan, child)), (("stays", "ABOVE_LIST"), ("stays", "ADULT_HELD")), day)
            self.assertEqual(next(c for c in plan.changes if c.key == child).before.sell, D("510.00"))
            self.assertFalse([row for step in plan_steps(plan) for row in step.rows
                              if step.room == "스위트" and step.rate_plan == "조식 포함" and day in step.dates
                              and (row.occupancy, row.nights) == (CHILD, 1)], "아동 1박 이상은 저장하지 않는다")
            rows = [row for row in preview_rows(plan) if row.item_key == cell_item_key(child)]
            self.assertTrue(rows and all(row.action is None and row.verdict == "ADULT_HELD" for row in rows), "장부에도 넣지 않는 칸")
        tally = counts(plan.changes, len(plan.skipped))
        self.assertEqual((tally["held"], tally["ADULT_HELD"], tally["will_change"], len(plan_steps(plan))), (2, 2, 86, 8))
        text = visible(render_preview(plan, 1, plan_steps(plan)))
        self.assertIn("같이 그대로 · 2칸 성인만 있는 칸을 바꾸지 않아 같이 그대로 둡니다", text)
        self.assertIn("510.00 그대로 성인 칸 따라 그대로", text)

    def test_amount_set_and_a_kept_adult_tier_cell_also_hold_the_child_cell(self):
        cells = {("A2", 1): ("100.00", "105.00"), (CHILD, 1): "130.00"}
        for request in (ask("amount", "10"), ask("set", "110", base_occupancy="A2")):
            with self.subTest(request.operation):
                plan = resolve(plan_change(snap(cells), request), [Resolution("ABOVE_LIST", "keep")])
                self.assertEqual(outcome(plan, CellKey("R", "P", DAY, CHILD, 1)), ("stays", "ADULT_HELD"))
                raised = resolve(plan_change(snap(cells), request), [Resolution("ABOVE_LIST", "raise_list")])
                self.assertEqual(outcome(raised, CellKey("R", "P", DAY, CHILD, 1)), ("moves", "140.00"), "성인 칸이 움직이면 같이 움직인다")
        tiers = {("A2", 1): "100.00", ("A2", 3): "90.00", (CHILD, 1): "160.00", (CHILD, 3): "117.00"}
        included = resolve(plan_change(snap(tiers), ask("amount", "20", nights=(3,))), [Resolution("ABOVE_ONE_NIGHT", "include")])
        self.assertEqual({(c.key.occupancy, c.key.nights): outcome(included, c.key) for c in included.changes},
                         {("A2", 3): ("moves", "110.00"), (CHILD, 3): ("moves", "137.00")},
                         "박수 층 칸을 「이대로 바꿈」으로 고르면 성인 칸이 움직여 아동 칸도 움직인다(ERP 에는 없는 고름)")
        waiting = resolve(plan_change(snap(tiers), ask("amount", "20", nights=(3,))), ())
        self.assertEqual([c.verdict for c in waiting.changes], ["ABOVE_ONE_NIGHT", "ADULT_HELD"],
                         "고르기 전에는 성인 칸만 고를 칸이다 — 아동 칸은 그 고름을 따른다")
        self.assertEqual(counts(waiting.changes)["red"], 1)

    def test_a_target_table_names_every_cell_and_does_not_follow(self):
        table = TargetTable("H", "O", (Target(CellKey("R", "P", DAY, "A2", 1), (("sell", D("520.00")),)),
                                       Target(CellKey("R", "P", DAY, CHILD, 1), (("sell", D("540.00")),))), hotel_id="9")
        plan = resolve(plan_targets(snap({("A2", 1): ("480.00", "500.00"), (CHILD, 1): "510.00"}), table), [Resolution("ABOVE_LIST", "keep")])
        self.assertEqual(outcome(plan, CellKey("R", "P", DAY, CHILD, 1)), ("moves", "540.00"), "목표 값은 칸마다 담당자가 적은 값이다")



class ChildTierCellTest(unittest.TestCase):
    """T5 — 박수 층 빨간 줄과 아동 칸. 시운전 7 의 모양(값은 지어냄): 판매가 +12%, 1박 이상 칸은 모두 정가를 넘고, 성인 1박 이상을
    안 바꾸고 나머지는 정가도 올리기로 고르면 아동 1박 이상은 성인 칸을 따라 그대로다. 그러면 3박 이상 칸이 모두 그날 1박 이상보다
    비싸진다. 성인 3박 이상이 아직 고르지 않은 빨간 줄이면 아동 3박 이상은 그 성인 칸을 따라 같이 그대로다 — 성인 칸이 그대로면 아동
    칸의 답은 결과를 바꾸지 못하니 묻지 않는다(red-lines.md 「같이 그대로 두는 아동 칸」과 같은 말)."""

    CELLS = {("A2", 1): ("100.00", "110.00"), ("A2", 3): "90.00", ("A2C1_CHD", 1): ("115.00", "125.00"), ("A2C1_CHD", 3): "105.00",
             ("A2C2_CHD", 1): ("130.00", "140.00"), ("A2C2_CHD", 3): "120.00"}
    SAID = "성인 2 · 1박 이상 칸은 안 바꿔. 나머지는 정가도 같이 올려줘."

    def cell(self, occupancy, nights):
        return CellKey("R", "P", DAY, occupancy, nights)

    def plan(self, *tier_choices):
        first = (Resolution("ABOVE_LIST", "keep", (self.cell("A2", 1),), self.SAID), Resolution("ABOVE_LIST", "raise_list", said=self.SAID))
        return resolve(plan_change(snap(self.CELLS), ask("percent", "12")), first + tier_choices)

    def verdicts(self, plan):
        return {(c.key.occupancy, c.key.nights): (c.verdict, c.choice) for c in plan.changes}

    def test_while_the_adult_tier_cell_is_unchosen_the_child_tier_cells_follow_it_and_only_the_adult_cell_is_asked(self):
        plan = self.plan()
        self.assertEqual(self.verdicts(plan), {
            ("A2", 1): ("ABOVE_LIST", "keep"), ("A2", 3): ("ABOVE_ONE_NIGHT", None),
            ("A2C1_CHD", 1): ("ADULT_HELD", None), ("A2C1_CHD", 3): ("ADULT_HELD", None),
            ("A2C2_CHD", 1): ("ADULT_HELD", None), ("A2C2_CHD", 3): ("ADULT_HELD", None)})
        tally = counts(plan.changes)
        self.assertEqual((tally["red"], tally["held"], tally["ABOVE_ONE_NIGHT"]), (1, 4, 1), "red-lines.md 와 같은 수 — 빨간 줄 1칸, 같이 그대로 4칸")

    def test_kept_adult_tier_cell_with_child_tier_cells_chosen_to_change_holds_them_and_saves_nothing(self):
        include = Resolution("ABOVE_ONE_NIGHT", "include", (self.cell("A2C1_CHD", 3), self.cell("A2C2_CHD", 3)), "아동 칸은 이대로 바꿔")
        plan = self.plan(Resolution("ABOVE_ONE_NIGHT", "keep", (self.cell("A2", 3),), "성인 3박은 안 바꿔"), include)
        self.assertEqual({key: verdict for key, verdict in self.verdicts(plan).items() if key[0] != "A2"},
                         {(child, nights): ("ADULT_HELD", None) for child in ("A2C1_CHD", "A2C2_CHD") for nights in (1, 3)},
                         "아동 칸은 성인 칸을 따라 그대로 — 「이대로 바꿈」이 아동 추가분을 바꾸지 못한다")
        self.assertEqual(plan_steps(plan), (), "저장 단계가 하나도 없다")
        self.assertEqual(counts(plan.changes)["will_change"], 0)

    def test_included_adult_tier_cell_with_one_child_tier_cell_kept_saves_the_adult_and_the_other_child_only(self):
        plan = self.plan(Resolution("ABOVE_ONE_NIGHT", "include", (self.cell("A2", 3), self.cell("A2C2_CHD", 3)), "3박은 그대로 올려"),
                         Resolution("ABOVE_ONE_NIGHT", "keep", (self.cell("A2C1_CHD", 3),), "아동 1명 3박은 두고"))
        self.assertEqual(self.verdicts(plan)[("A2C1_CHD", 3)], ("ABOVE_ONE_NIGHT", "keep"), "성인 칸이 움직이면 아동 칸은 제 빨간 줄이다")
        written = {(row.occupancy, row.nights): str(row.sell) for step in plan_steps(plan) for row in step.rows}
        self.assertEqual(written, {("A2", 3): "100.80", ("A2C2_CHD", 3): "130.80"},
                         "성인 3박과 고른 아동 3박만 저장한다 — 안 바꾸기로 고른 아동 칸 · 성인 1박을 따라 그대로인 아동 1박은 쓰지 않는다")



class UnusedChoiceTest(unittest.TestCase):
    """T4 — 고른 것이 어느 칸에도 쓰이지 않으면 말한다. 시운전 7: "나머지는 정가도 같이 올려줘" 의 「정가도 같이 올림」은 남은 빨간
    칸(아동 1박 이상 둘)에 고른 것인데, 성인 1박 이상을 안 바꾸기로 해 그 칸들이 같이 그대로가 되면서 고른 것과 미리보기 · 도우미의
    말에서 사라졌다. plan 의 답 · 미리보기 · 장부가 그 고름과 까닭을 남긴다."""

    def setUp(self):
        self.scene = ChildTierCellTest()

    def test_the_raise_said_for_child_cells_held_with_their_kept_adult_cell_is_reported_with_why(self):
        plan = self.scene.plan()
        self.assertEqual([(line["rule"], line["choice"], line["cells"], line["why"], line["label"], line["said"]) for line in unused_lines(plan)],
                         [("ABOVE_LIST", "raise_list", 2, "held_kept", "성인만 있는 칸을 그대로 두셔서 같이 그대로 둡니다", ChildTierCellTest.SAID)])
        text = visible(render_preview(plan, 5, plan_steps(plan)))
        self.assertIn("정가도 12% 올림 (아동이 있는 칸은 아동 추가분은 그대로) — 고르셨지만 이번 계산에서는 쓰지 않습니다 (2칸): "
                      "성인만 있는 칸을 그대로 두셔서 같이 그대로 둡니다.", text, "미리보기의 「고르신 빨간 줄」")
        held = {row.item_key: row.said for row in preview_rows(plan) if row.verdict == "ADULT_HELD" and row.field == "sell"}
        self.assertEqual(held[cell_item_key(self.scene.cell("A2C1_CHD", 1))], ChildTierCellTest.SAID, "담당자의 말은 장부에 남는다")

    def test_a_choice_every_cell_takes_is_not_reported_and_one_with_no_cell_of_its_rule_says_so(self):
        plan = self.scene.plan(Resolution("ABOVE_ONE_NIGHT", "keep", said="그 칸도 안 바꿔"),
                               Resolution("BELOW_COST", "include", said="원가 아래도 그대로"))
        self.assertEqual([(line["rule"], line["why"], line["cells"]) for line in unused_lines(plan)],
                         [("ABOVE_LIST", "held_kept", 2), ("BELOW_COST", "none", 0)],
                         "성인 3박의 「안 바꿈」은 쓰인다 · 공급 원가 빨간 줄은 이 계산에 없다")

    def test_a_rule_wide_choice_covered_by_pinned_cells_or_by_a_later_rule_wide_choice_says_which(self):
        cell = self.scene.cell
        plan = resolve(plan_change(snap(ChildTierCellTest.CELLS), ask("percent", "12")), (
            Resolution("ABOVE_LIST", "clear_list", said="정가 지워"),                      # 뒤의 규칙 전체 고름이 앞선다
            Resolution("ABOVE_LIST", "raise_list", said="아니 정가 올려"),                # 칸마다 고른 것이 모두 앞선다
            Resolution("ABOVE_LIST", "keep", (cell("A2", 1), cell("A2C1_CHD", 1), cell("A2C2_CHD", 1)), "1박은 다 그대로")))
        self.assertEqual([(line["choice"], line["why"], line["cells"]) for line in unused_lines(plan)],
                         [("clear_list", "replaced", 0), ("raise_list", "pinned", 0)])
        self.assertEqual(unused_lines(plan)[1]["label"], "그 빨간 줄의 칸을 모두 칸마다 따로 고르셨습니다")

    def test_the_command_s_short_answer_carries_unused(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)

            def write(name, data):
                (folder / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return folder / name

            choices = [{"rule": "ABOVE_LIST", "choice": "keep", "said": ChildTierCellTest.SAID, "cells": [encode_key(self.scene.cell("A2", 1))]},
                       {"rule": "ABOVE_LIST", "choice": "raise_list", "said": ChildTierCellTest.SAID}]
            done = subprocess.run([sys.executable, "-B", str(SCRIPT), "plan", "--snapshot", write("s.json", encode_snapshot(snap(ChildTierCellTest.CELLS))),
                                   "--request", write("r.json", encode_request(ask("percent", "12"))), "--resolutions", write("c.json", choices),
                                   "--out", folder / "plan-2.json"],
                                  capture_output=True, text=True, env=scene.env(folder / "기록"))
            self.assertEqual(done.returncode, 0, done.stderr)
            short = json.loads(done.stdout)
            self.assertEqual([(line["choice"], line["cells"], line["why"]) for line in short["unused"]], [("raise_list", 2, "held_kept")])
            self.assertEqual([line["choice"] for line in short["chosen"]], ["keep"])


class TierChoiceTest(unittest.TestCase):
    """검토 5 — 디럭스 · 조식 포함 · 12/25: 성인 2 · 3박 이상 180 → 195, 성인 2 · 1박 이상 200 → 190. 첫 계산은 3박 이상만 걸고, 그
    칸을 「이대로 바꿈」으로 고르면 1박 이상이 걸린다. 그 칸을 짚은 「안 바꿈」을 받는다."""

    def setUp(self):
        self.three, self.one = (CellKey("디럭스", "조식 포함", "2026-12-25", "A2", nights) for nights in (3, 1))
        self.table = TargetTable(scene.HOTEL, scene.OFFER, (Target(self.three, (("sell", D("195")),)), Target(self.one, (("sell", D("190")),))),
                                 hotel_id=scene.HOTEL_ID)

    def test_a_tier_cell_flagged_only_in_a_later_round_can_be_chosen_by_name(self):
        plan = plan_targets(scene.snapshot(), self.table)
        self.assertEqual([(c.key.nights, c.verdict) for c in plan.changes], [(1, None), (3, "ABOVE_ONE_NIGHT")], "첫 계산은 3박 이상만")
        chosen = resolve(plan, [Resolution("ABOVE_ONE_NIGHT", "include", (self.three,), "3박은 그대로 바꿔"),
                                Resolution("ABOVE_ONE_NIGHT", "keep", (self.one,), "1박은 두고")])
        self.assertEqual({c.key.nights: (c.verdict, c.choice, c.writes) for c in chosen.changes},
                         {3: ("ABOVE_ONE_NIGHT", "include", {"sell": D("195.00")}), 1: ("ABOVE_ONE_NIGHT", "keep", {})})
        with self.assertRaisesRegex(ValueError, "항목이 아닙니다"):
            resolve(plan, [Resolution("ABOVE_ONE_NIGHT", "keep", (replace(self.one, occupancy="A3"),))])

    def test_the_command_takes_the_choice_file_naming_the_later_cell(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)

            def write(name, data):
                (folder / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return folder / name

            choices = [{"rule": "ABOVE_ONE_NIGHT", "choice": "include", "said": "3박은 그대로 바꿔", "cells": [encode_key(self.three)]},
                       {"rule": "ABOVE_ONE_NIGHT", "choice": "keep", "said": "1박은 두고", "cells": [encode_key(self.one)]}]
            done = subprocess.run([sys.executable, "-B", str(SCRIPT), "plan", "--snapshot", write("s.json", encode_snapshot(scene.snapshot())),
                                   "--request", write("t.json", encode_request(self.table)), "--resolutions", write("c.json", choices)],
                                  capture_output=True, text=True, env=scene.env(folder / "기록"))
            self.assertEqual(done.returncode, 0, done.stderr)
            answer = json.loads(done.stdout)
            self.assertEqual((answer["counts"]["red"], answer["counts"]["include"], answer["counts"]["keep"], len(answer["steps"])), (0, 1, 1, 1))


if __name__ == "__main__":
    unittest.main()
