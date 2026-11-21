"""Z1 — 멈춘 변경의 결과 페이지는 이어서 하면 무엇을 쓰는지 보인다.

담당자는 이 페이지를 보며 이어서 할지, 된 것까지 되돌릴지, 이대로 둘지 고른다. 그래서 칸마다 — 저장한 칸은 `전 → 넣은 값`,
아직 저장하지 않은 칸은 `미리보기 때 값 → 이어서 하면 넣을 값` 과 「아직 저장 안 함 · N번째 저장」, 이 변경이 일부러 손대지 않는 칸만
「그대로」. 미리보기와 같은 약속도 지킨다: 남은 저장이 넣을 값 하나하나가 페이지의 그 칸 옆에 같은 숫자로 있다.

두 번째 시운전의 모양(객실마다 저장 한 번, 둘)을 첫 저장 뒤에 끊고, 칸마다 고름을 섞은 모양(묶음 저장과 셀 창 저장이 한 칸의
필드를 나눠 쓴다)을 중간에 끊는다. 페이지의 칸 표는 사람이 읽듯 객실 · 요금제 머리, 날짜 열, 인원 · 박수 줄로 읽는다.

    python3 -m unittest discover -s tests
"""

import re
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import scene  # noqa: E402
import trial_scene  # noqa: E402
from change_core.chrome import page_text  # noqa: E402
from change_core.ledger import DB_NAME, Ledger  # noqa: E402
from change_core.rules import Resolution  # noqa: E402
from dataclasses import replace  # noqa: E402

from price_model import (  # noqa: E402
    CellKey, decode_resolution_items, encode_key, encode_request, encode_snapshot, encode_step, snapshot_reading,
)
from price_pages import render_result, result_name  # noqa: E402
from price_plan import (  # noqa: E402
    plan_cell_rollback, plan_change, plan_steps, preview_rows, resolve, rollback_rows, rollback_writes, save_steps, step_plans,
)
from test_preview_truth import above_list_cells, place, read_grid, shown_moves, step_writes  # noqa: E402

REAL = scene.NOW
SECTION = "칸마다 넣은 값과 아직 넣지 않은 값"


def tags(parts) -> list[str]:
    return [text for _tag, cls, text in parts if cls.startswith("tag")]


def waiting_steps(parts) -> set[int]:
    """칸의 「아직 저장 안 함 · 3 · 4번째 저장」(눌렸는데 됐는지 모르면 「저장됐는지 모름 · …」) 꼬리표가 말하는 단계 번호들."""
    found = [re.fullmatch(r"(?:아직 저장 안 함|저장됐는지 모름) · ([\d · ]+)번째 저장", text) for text in tags(parts)]
    return {int(n) for match in found if match for n in match.group(1).split(" · ")}


class StoppedResultPageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / DB_NAME

    def tearDown(self):
        self.tmp.cleanup()

    def ledger(self, minutes: float) -> Ledger:
        return Ledger(self.path, now=lambda: REAL + timedelta(minutes=minutes))

    @staticmethod
    def planned(choices):
        """시운전 모양을 고름대로 계산한 것 → (읽은 값, 계산, 저장 단계)."""
        snapshot = trial_scene.snapshot(read_at=REAL.isoformat(timespec="seconds"))
        resolutions = [Resolution(item["rule"], item["choice"], decode_resolution_items(item.get("cells"))) for item in choices]
        plan = resolve(plan_change(snapshot, trial_scene.request()), resolutions)
        return snapshot, plan, plan_steps(plan)

    def stopped(self, choices, saved):
        """고름대로 계산해 적용을 시작하고, 앞의 `saved` 번(저장 단계를 받아 번호를 주는 함수도 된다)만 저장한 뒤 세션이 끊긴(16분
        동안 아무 일이 없던) 변경 → (장부의 변경, 저장 단계(plan.json 모양))."""
        snapshot, plan, steps = self.planned(choices)
        saved = saved(steps) if callable(saved) else saved
        change = self.ledger(0).record_preview(
            hotel=snapshot.hotel, hotel_id=snapshot.hotel_id, offer=snapshot.offer, currency="USD", sentence=trial_scene.SENTENCE,
            read_at=snapshot.read_at, rows=preview_rows(plan), request=encode_request(plan.request), reading=encode_snapshot(snapshot))
        self.ledger(0).begin(change, step_plans(steps), read_at=scene.read_after(snapshot.read_at))
        for index in range(1, saved + 1):
            self.ledger(1).record_step(change, index, saved=True)
        record = self.ledger(20).change(change)
        self.assertEqual((record.status, record.cause), ("stopped", "cut_off"))
        return record, [encode_step(step) for step in steps]

    def assert_every_value_is_beside_its_cell(self, record, steps):
        """저장한 단계의 값과 남은 단계의 값이 모두 그 칸 옆에 같은 숫자로 있고, 남은 단계의 칸에는 「아직 저장 안 함 · N번째 저장」이
        붙고, 페이지에 보이는 바뀌는 값 하나하나는 꼭 한 저장 단계의 값이다 → 칸 표."""
        html = render_result(record)
        grid, classes = read_grid(html, SECTION, classes=True)
        saved = {step.index for step in record.steps if step.status == "saved"}
        by_cell = {}
        for index, step in enumerate(steps, 1):
            for key, field, value in step_writes([step]):
                spot = place(key)
                self.assertIn(spot, grid, f"저장하는 칸이 페이지에 없다 {key}")
                self.assertEqual(shown_moves(grid[spot]).get(field, "보이지 않음"), value,
                                 f"{index}번째 저장 · {key} · {field} — 저장은 {value}, 페이지는 {grid[spot]}")
                if index in saved:
                    self.assertIn("저장함", tags(grid[spot]), f"{key}: 저장한 칸")
                    self.assertNotIn(index, waiting_steps(grid[spot]))
                else:
                    self.assertIn(index, waiting_steps(grid[spot]), f"{key}: 이어서 하면 넣을 칸 — {grid[spot]}")
                    self.assertEqual(classes[spot], "wait")
                self.assertNotIn("그대로", [text for _tag, _cls, text in grid[spot]], f"{key}: 넣는 칸은 「그대로」가 아니다")
                by_cell.setdefault((spot, field), []).append(value)
        shown = [(spot, field, value) for spot, parts in grid.items() for field, value in shown_moves(parts).items()]
        self.assertTrue(shown)
        for spot, field, value in shown:
            self.assertEqual(by_cell.get((spot, field)), [value], f"페이지에서 바뀐다는 {spot} · {field} = {value} 는 꼭 한 저장 단계의 값")
        return grid, html

    def test_the_trial_cut_off_after_save_1_of_2_shows_what_continuing_would_write(self):
        record, steps = self.stopped([{"rule": "ABOVE_LIST", "choice": "raise_list"}], saved=1)
        self.assertEqual(len(steps), 2)
        grid, html = self.assert_every_value_is_beside_its_cell(record, steps)
        cell = grid[("스탠다드 바다 전망 · 조식 포함", "12/7 월", "성인 2 · 1박 이상")]
        self.assertEqual([text for _tag, _cls, text in cell],
                         ["120.00", "→", "134.40", "정가 132.00 → 147.84", "아직 저장 안 함 · 2번째 저장"],
                         "미리보기 때 값 → 이어서 하면 넣을 값 — 「120.00 그대로」가 아니다")
        text = page_text(html)
        self.assertIn("「아직 저장 안 함」 12칸은 미리보기 때 값 → 이어서 하면 넣을 값입니다. 지금 ERP 값은 다시 읽어 봐야 압니다.", text)
        self.assertIn("✓ 1. 스탠다드 · 조식 포함 · 12/7 월 ~ 12/8 화 · 12/10 목 · 12/14 월 (4일, 2026년) · 24칸 저장함", text)
        self.assertIn("– 2. 스탠다드 바다 전망 · 조식 포함 · 12/7 월 ~ 12/8 화 · 12/10 목 · 12/14 월 (4일, 2026년) · 12칸 아직 안 함", text)
        self.assertIn("이어서 — 남은 저장 한 번을 마저 적용합니다(아래 표의 「아직 저장 안 함」 12칸이 그 값으로 바뀝니다)", text)

        # 둘째 저장의 단추는 눌렸는데 됐는지 모른다 — 그 칸들은 「저장됐는지 모름」이고 값은 같은 자리에 있다
        self.ledger(21).record_step(record.id, 2, saved=False, note="모름", unknown=True)
        unsure = self.ledger(21).change(record.id)
        grid, html = self.assert_every_value_is_beside_its_cell(unsure, steps)
        self.assertEqual(tags(grid[("스탠다드 바다 전망 · 조식 포함", "12/7 월", "성인 2 · 1박 이상")]), ["저장됐는지 모름 · 2번째 저장"])
        self.assertIn("2. 스탠다드 바다 전망 · 조식 포함 · 12/7 월 ~ 12/8 화 · 12/10 목 · 12/14 월 (4일, 2026년) · 12칸 저장됐는지 모름", page_text(html))

    def test_cells_left_alone_on_purpose_stay_unchanged_and_a_cell_split_over_two_saves_shows_both_parts(self):
        over = above_list_cells(trial_scene.snapshot(), trial_scene.request())
        sea = [key for key in over if key.room == "스탠다드 바다 전망"]
        choices = [{"rule": "ABOVE_LIST", "choice": "raise_list"},
                   {"rule": "ABOVE_LIST", "choice": "clear_list", "cells": [encode_key(sea[0])]},
                   {"rule": "ABOVE_LIST", "choice": "keep", "cells": [encode_key(over[0]), encode_key(sea[-1])]},
                   {"rule": "ABOVE_ONE_NIGHT", "choice": "include"}]
        _snapshot, _plan, planned = self.planned(choices)
        clear = next(index for index, step in enumerate(planned, 1) if step.kind == "cell_edit")
        self.assertEqual((len(planned), planned[clear].kind), (6, "bulk"), "정가 지움(셀 창) 다음이 그 칸의 판매가(묶음)")
        for saved in range(len(planned)):   # 어느 저장 앞에서 끊겨도
            with self.subTest(saved=saved):
                record, steps = self.stopped(choices, saved=saved)
                grid, _html = self.assert_every_value_is_beside_its_cell(record, steps)
                for key in (over[0], sea[-1]):
                    parts = grid[place(key)]
                    self.assertEqual(([text for _tag, _cls, text in parts][1:], tags(parts)), (["그대로"], []),
                                     f"{key}: 안 바꾸기로 고른 칸은 「그대로」")
        # 셀 창 저장(정가 지움) 뒤에 끊겼다 — 한 칸에서 정가는 저장됐고 판매가는 이어서 하면 들어간다
        record, steps = self.stopped(choices, saved=clear)
        cleared = read_grid(render_result(record), SECTION)[place(sea[0])]
        self.assertEqual([text for _tag, _cls, text in cleared],
                         [f"정가 {sea_list(sea[0])} → 비움", "저장함", "120.00", "→", "134.40", f"아직 저장 안 함 · {clear + 1}번째 저장"])



SEA = "스탠다드 바다 전망"
MOVED_SENTENCE = ("「그 사이 ERP 에서 바뀜」 1칸은 미리보기 뒤에 ERP 에서 값이 바뀐 칸입니다. 칸에는 미리보기 때 값과 {when}에 다시 읽은 "
                  "값을 보입니다 — 다시 읽은 값은 그때 ERP 에 있던 값이고, 그 뒤에 또 바뀌었을 수 있습니다. 도우미는 이 칸에 아무것도 넣지 "
                  "않았습니다.")
MOVED_ERROR = ("ERP 화면의 값이 읽은 값과 다릅니다(1칸) — 2026-12-07 A2C1_CHD · 1박 이상 — 읽은 값 판매가 135.00 · 정가 147.00 · "
               "공급 원가 125.00 · 화면 판매가 136.00 · 정가 147.00 · 공급 원가 125.00. 아무것도 치지 않았고 누르지 않았습니다")


class StoppedAfterARefusedSaveTest(unittest.TestCase):
    """T1 — 시운전 7 의 모양(값은 지어냄): 첫 저장(스탠다드) 뒤 다른 사람이 둘째 저장의 칸(바다 전망 12/7 성인 2 + 아동 1 · 1박 이상)을
    바꿔, 둘째 저장이 누르기 전에 거절됐다. 결과 페이지는 멈춘 뒤 마지막 check 가 본 것대로 말한다: check 가 없으면 이어서 할 수
    있는지는 다시 읽어 봐야 안다고, check 가 안 된다고 했으면 이어서를 빼고 까닭과 그 칸을 그 check 가 읽은 값을(그 시각과 함께),
    된다고 했으면 이어서를. 시운전 8 F1 — check 가 읽은 값은 어느 상태의 페이지에서도 「지금」이 아니다. 그 뒤에 또 바뀌었을 수 있어
    칸마다 그 시각을 달고(다른 날 연 페이지면 날짜도), 설명 문장이 그렇게 한 번 말한다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / DB_NAME
        self.snapshot = trial_scene.snapshot(read_at=REAL.isoformat(timespec="seconds"))
        plan = resolve(plan_change(self.snapshot, trial_scene.request()), [Resolution("ABOVE_LIST", "raise_list", said="정가도 올려")])
        self.steps = plan_steps(plan)
        self.assertEqual([step.room for step in self.steps], ["스탠다드", SEA])
        self.change = self.ledger(0).record_preview(
            hotel=self.snapshot.hotel, hotel_id=self.snapshot.hotel_id, offer=self.snapshot.offer, currency="USD",
            sentence=trial_scene.SENTENCE, read_at=self.snapshot.read_at, rows=preview_rows(plan), request=encode_request(plan.request),
            reading=encode_snapshot(self.snapshot))
        self.ledger(0).begin(self.change, step_plans(self.steps), read_at=scene.read_after(self.snapshot.read_at))
        self.ledger(1).record_step(self.change, 1, saved=True)
        self.moved = CellKey(SEA, trial_scene.PLAN, "2026-12-07", "A2C1_CHD", 1)

    def tearDown(self):
        self.tmp.cleanup()

    def ledger(self, minutes: float) -> Ledger:
        return Ledger(self.path, now=lambda: REAL + timedelta(minutes=minutes))

    def refuse(self, note=MOVED_ERROR, unknown=False):
        self.ledger(5).record_step(self.change, 2, saved=False, note=note, unknown=unknown)

    def check(self, minutes=6, moved=True):
        """`minutes` 분에 다시 읽어 check — 첫 저장은 됐고, `moved` 면 둘째 저장의 그 칸이 다른 사람의 값(+1)이다."""
        now = scene.applied(self.snapshot, self.steps[:1], (REAL + timedelta(minutes=minutes)).isoformat(timespec="seconds"))
        if moved:
            now = replace(now, cells={**now.cells, self.moved: replace(now.cells[self.moved], sell=now.cells[self.moved].sell + 1)})
        return self.ledger(minutes).check(self.change, snapshot_reading(now), snapshot_reading(self.snapshot), now.read_at)

    def page(self, minutes=7):
        return page_text(render_result(self.ledger(minutes).change(self.change)))

    def assert_no_stored_now(self, text):
        """check 가 읽어 장부에 둔 값을 「지금」이라고 하지 않는다."""
        self.assertNotRegex(text, r"지금 [\d,.]+|지금 칸 없음", "장부에 둔 값을 지금 값이라고 하지 않는다")

    def moved_cell(self, minutes=7):
        grid = read_grid(render_result(self.ledger(minutes).change(self.change)), SECTION)
        return [part for _tag, _cls, part in grid[place(self.moved)]]

    def assert_plain(self, text):
        for raw in ("A2C1_CHD", "A2 ·", "읽은 값 판매가", "화면 판매가", "다시 읽고 미리보기를 새로 만듭니다"):
            self.assertNotIn(raw, text, "담당자가 읽는 글에 인원 조합 키 · 페이지 오류의 날글이 없다")

    def test_before_any_check_the_page_does_not_promise_that_continuing_is_possible(self):
        self.refuse()
        text = self.page()
        self.assertIn("2번째 저장에서 멈췄습니다 (미리보기 뒤에 ERP 에서 그 저장의 칸 1개가 바뀌어 아무것도 넣지 않았습니다). "
                      "지금은 일부만 바뀐 상태입니다.", text, "U3 — 첫 줄이 바뀐 칸 수를 댄다(도우미의 말과 같다)")
        self.assertIn("이어서 할 수 있는지는 ERP 를 다시 읽어 봐야 압니다 — 그 사이 바뀐 칸이 있으면 이어서 하지 않습니다.", text)
        self.assertIn("이어서 — 남은 저장 한 번을 마저 적용합니다(아래 표의 「아직 저장 안 함」 12칸이 그 값으로 바뀝니다). "
                      "다시 읽어 그 사이 바뀐 칸이 없을 때만 합니다.", text)
        self.assertIn('이대로 두기 — 장부에 "중간에 멈춤"으로 남습니다.', text)
        self.assertNotIn("나중에 이어서 할 수 있습니다", text)
        self.assertNotIn("로그인", text, "로그인과 상관없는 멈춤")
        self.assert_plain(text)

    def test_after_a_check_that_forbids_it_the_page_leaves_out_continuing_and_shows_what_the_erp_holds_now(self):
        self.refuse()
        report = self.check()
        self.assertFalse(report.can_continue)
        self.assertEqual(report.why, (f"2번째 저장({SEA} · 조식 포함 · 12/7 월 ~ 12/8 화 · 12/10 목 · 12/14 월 (4일, 2026년))"
                                      "의 칸 1개가 미리보기 때 읽은 값과 다릅니다",), "같은 까닭을 두 번 말하지 않는다")
        text = self.page()
        self.assertNotIn("이어서 —", text)
        self.assertNotIn("이어서 하면", text)
        self.assertIn("10시 6분에 ERP 를 다시 읽어 보니 이어서 할 수 없습니다.", text)
        self.assertIn(report.why[0], text, "check 의 까닭")
        self.assertIn("된 것까지 되돌리기 — 이미 된 저장 한 번을 원래 값으로 되돌립니다(미리보기를 먼저 보여 드립니다).", text)
        self.assertIn('이대로 두기 — 장부에 "중간에 멈춤"으로 남습니다. 남은 부분은 지금 값으로 새로 바꿔야 합니다(새 미리보기부터).', text)
        self.assertIn(MOVED_SENTENCE.format(when="10시 6분"), text)
        self.assertEqual(self.moved_cell(), ["미리보기 때 135.00", "·", "10시 6분에 다시 읽으니 136.00", "그 사이 ERP 에서 바뀜 · 넣지 않음"])
        self.assert_no_stored_now(text)
        grid = read_grid(render_result(self.ledger(7).change(self.change)), SECTION)
        other = grid[place(replace(self.moved, date="2026-12-08"))]
        self.assertIn("아직 저장 안 함 · 2번째 저장", tags(other), "바뀌지 않은 칸은 넣으려던 값 그대로 보인다")
        self.assertNotIn("로그인", text)
        self.assert_plain(text)
        self.assert_stopped_ends(text)

    def assert_stopped_ends(self, text):
        """시운전 8 F3 — 멈춘 변경의 페이지는 이름이 「적용하다 멈춤」이고, 손님 화면 · 손입력 줄은 저장한 칸을 그 수로 말하고, 되돌리는
        법은 위의 「어떻게 할까요?」 한 곳에서만 말한다."""
        self.assertEqual(text.splitlines()[0], "적용하다 멈춤 · 시운전 모양 호텔 · 기본 오퍼")
        self.assertEqual(result_name(self.ledger(7).change(self.change)), "적용하다 멈춤", "파일 이름도")
        self.assertIn("저장한 24칸은 손님 화면에 길어야 5분 안에 새 가격으로 보입니다. 결제 금액은 바로 새 가격입니다.", text)
        self.assertIn("저장한 24칸은 ERP 에서 '손입력'으로 표시됩니다.", text)
        self.assertNotIn("이 칸들은", text)
        self.assertNotIn("되돌리려면 대화창에서", text, "되돌리기는 고를 것에 있다 — 두 번 말하지 않는다")
        self.assertIn("된 것까지 되돌리기 —", text)

    def test_after_a_check_that_allows_it_the_page_offers_continuing(self):
        self.refuse(note="드로어 표에 없는 줄이나 칸이 있어 저장하지 않았습니다")
        self.assertTrue(self.check(moved=False).can_continue)
        text = self.page()
        self.assertEqual(text.splitlines()[0], "적용하다 멈춤 · 시운전 모양 호텔 · 기본 오퍼", "이어서 할 수 있어도 아직 멈춘 변경이다")
        self.assertIn("2번째 저장에서 멈췄습니다 (드로어 표에 없는 줄이나 칸이 있어 저장하지 않았습니다). 지금은 일부만 바뀐 상태입니다.", text)
        self.assertIn("10시 6분에 ERP 를 다시 읽어 보니 남은 저장의 칸이 미리보기 때와 같았습니다 — 이어서 할 수 있습니다.", text)
        self.assertIn("이어서 — 남은 저장 한 번을 마저 적용합니다(아래 표의 「아직 저장 안 함」 12칸이 그 값으로 바뀝니다).", text)
        self.assertIn("「아직 저장 안 함」 12칸은 미리보기 때 값 → 이어서 하면 넣을 값입니다. 10시 6분에 다시 읽었을 때 ERP 값이 미리보기 "
                      "때와 같았습니다 — 그 뒤에 바뀌었을 수 있고, 바뀐 칸이 있으면 그 저장은 넣지 않고 멈춥니다.", text)
        self.assert_no_stored_now(text)
        self.assertNotIn("로그인", text)
        # 그 check 는 15분이 지나면, 또는 그 뒤 저장 결과가 적히면 더는 이어서를 말하지 않는다
        self.assertIn("이어서 할 수 있는지는 ERP 를 다시 읽어 봐야 압니다", self.page(minutes=22))
        self.ledger(8).record_step(self.change, 2, saved=False, note="드로어 표에 없는 줄이나 칸이 있어 저장하지 않았습니다")
        self.assertIn("이어서 할 수 있는지는 ERP 를 다시 읽어 봐야 압니다", self.page(minutes=9))

    def test_the_value_the_check_read_carries_its_time_in_every_state_and_the_date_on_a_later_day(self):
        """시운전 8 F1 — 다른 사람이 그 칸을 되돌린 뒤에도, 저장한 칸을 되돌린 뒤에도, 다음 날 다시 연 페이지에서도 그 값은 10시 6분에
        읽은 값으로 보인다. 설명 문장은 어느 상태에서나 한 번 있다."""
        self.refuse()
        self.check()
        later = 24 * 60 + 7   # 다음 날 10시 7분
        text = self.page(minutes=later)
        self.assertIn("11월 21일 10시 6분에 ERP 를 다시 읽어 보니 이어서 할 수 없습니다.", text)
        self.assertIn(MOVED_SENTENCE.format(when="11월 21일 10시 6분"), text)
        self.assertEqual(self.moved_cell(later)[2], "11월 21일 10시 6분에 다시 읽으니 136.00", "다음 날에는 날짜까지")
        self.assert_no_stored_now(text)
        # 저장한 첫 저장을 뒤에 되돌렸다 — 이어서도 되돌릴 것도 없지만, 그 칸은 여전히 그때 읽은 값과 그 시각이다(설명 문장도 남는다)
        undo = self.rollback_saved(minutes=10)
        text = self.page(minutes=11)
        self.assertIn("이 변경이 저장한 칸은 뒤에 모두 되돌렸습니다.", text)
        self.assertIn(f"이 변경의 24칸은 뒤에 되돌렸습니다(장부 {undo}번).", text)
        self.assertEqual(text.count(MOVED_SENTENCE.format(when="10시 6분")), 1, "설명 문장은 한 번")
        self.assertEqual(self.moved_cell(11), ["미리보기 때 135.00", "·", "10시 6분에 다시 읽으니 136.00", "그 사이 ERP 에서 바뀜 · 넣지 않음"])
        self.assert_no_stored_now(text)

    def rollback_saved(self, minutes):
        """첫 저장의 칸을 모두 되돌리는 되돌리기를 `minutes` 분에 적용한다 → 그 번호."""
        read_at = (REAL + timedelta(minutes=minutes - 1)).isoformat(timespec="seconds")
        now = scene.applied(self.snapshot, self.steps[:1], read_at)
        ledger = self.ledger(minutes)
        rollback = plan_cell_rollback(ledger.recorded_change(self.change), ledger.later_writes(self.change), now)
        rid = ledger.record_preview(hotel=rollback.hotel, hotel_id=rollback.hotel_id, offer=rollback.offer, currency=rollback.currency,
                                    sentence="되돌려", read_at=rollback.read_at, rows=rollback_rows(rollback), reverses=self.change)
        steps = save_steps(rollback_writes(rollback))
        self.ledger(minutes + 0.5).begin(rid, step_plans(steps), read_at=(REAL + timedelta(minutes=minutes + 0.2)).isoformat())
        for index in range(1, len(steps) + 1):
            self.ledger(minutes + 0.5).record_step(rid, index, saved=True)
        return rid

    def test_a_rollback_that_stopped_does_not_offer_to_undo_what_it_undid(self):
        """되돌리기가 중간에 멈췄다(둘 가운데 첫 저장만 됨). 되돌리기는 다시 되돌리지 않으므로(`rollback` 이 거절한다) 페이지는
        「된 것까지 되돌리기」를 권하지 않고, 남은 것은 되돌리던 변경을 새로 되돌리면 된다고 말한다 — 그때 나머지만 되돌린다."""
        self.ledger(2).record_step(self.change, 2, saved=True)

        def at(minutes):
            return (REAL + timedelta(minutes=minutes)).isoformat(timespec="seconds")

        ledger = self.ledger(10)
        rollback = plan_cell_rollback(ledger.recorded_change(self.change), ledger.later_writes(self.change),
                                      scene.applied(self.snapshot, self.steps, at(9)))
        rid = ledger.record_preview(hotel=rollback.hotel, hotel_id=rollback.hotel_id, offer=rollback.offer, currency=rollback.currency,
                                    sentence="되돌려", read_at=rollback.read_at, rows=rollback_rows(rollback), reverses=self.change)
        steps = save_steps(rollback_writes(rollback))
        self.assertEqual(len(steps), 2)
        self.ledger(10.5).begin(rid, step_plans(steps), read_at=at(10.2))
        self.ledger(11).record_step(rid, 1, saved=True)
        self.ledger(12).record_step(rid, 2, saved=False, note="드로어 표에 없는 줄이나 칸이 있어 저장하지 않았습니다")
        record = self.ledger(13).change(rid)
        text = page_text(render_result(record))
        self.assertEqual((record.status, result_name(record)), ("stopped", "되돌리다 멈춤"))
        self.assertNotIn("된 것까지 되돌리기", text)
        self.assertIn("이어서 — 남은 저장 한 번을 마저 적용합니다", text)
        self.assertIn("남은 것을 되돌리려면 되돌리던 것을 새로 되돌려 달라고 하세요 — 이미 되돌린 것은 빼고 나머지만 되돌립니다.", text)
        with self.assertRaisesRegex(Exception, "다시 되돌리지 않습니다"):
            self.ledger(14).undoable(rid)
        # 되돌리던 변경을 새로 되돌리면 — 첫 저장이 되돌린 객실은 빼고, 아직 그 변경의 값인 객실만 되돌린다
        still = [step for step in self.steps if step.room != steps[0].room]
        again = plan_cell_rollback(self.ledger(15).recorded_change(self.change), self.ledger(15).later_writes(self.change),
                                   scene.applied(self.snapshot, still, at(15)))
        self.assertEqual([step.room for step in save_steps(rollback_writes(again))], [step.room for step in still])
        self.assertEqual(0 < len(again.restored) < len(rollback.restored), True)

    def test_a_change_that_finished_keeps_its_name_its_footer_and_the_undo_hint(self):
        self.ledger(2).record_step(self.change, 2, saved=True)
        record = self.ledger(3).change(self.change)
        text = page_text(render_result(record))
        self.assertEqual((record.status, result_name(record)), ("applied", "적용 결과"))
        self.assertEqual(text.splitlines()[0], "적용 결과 · 시운전 모양 호텔 · 기본 오퍼")
        self.assertIn("손님 화면에는 길어야 5분 안에 새 가격이 보입니다. 결제 금액은 바로 새 가격입니다.", text)
        self.assertIn("이 칸들은 ERP 에서 '손입력'으로 표시됩니다.", text)
        self.assertIn('되돌리려면 대화창에서 "1번 되돌려" 또는 "방금 것 되돌려"라고 하세요.', text)

    def test_the_login_sentence_comes_only_when_the_cause_can_be_a_lost_login(self):
        self.refuse(note="모름", unknown=True)
        self.assertIn("크롬에서 ERP 로그인을 확인한 뒤 대화창에서 골라 주세요.", self.page())
        self.tearDown()
        self.setUp()
        self.refuse(note="탭이 로그인 화면입니다 — 담당자가 직접 로그인한 뒤 다시 부릅니다")
        self.assertIn("크롬에서 ERP 로그인을 확인한 뒤 대화창에서 골라 주세요.", self.page())
        self.tearDown()
        self.setUp()
        self.refuse()
        self.check()
        self.assertIn("대화창에서 골라 주세요.", self.page())
        self.assertNotIn("로그인", self.page(), "누르는 순간의 확인이 거절한 것은 로그인과 상관없다")


def sea_list(key: CellKey) -> str:
    return f"{trial_scene.snapshot().cells[key].list:.2f}"


if __name__ == "__main__":
    unittest.main()
