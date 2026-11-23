"""목표 값 표 — 지금 값과 다른 칸만, 필드 여럿, 비우기, 새로 생기는 칸(판매가 필요 · 보인 적 있는 인원·박수만), 같은 규칙.

    python3 -m unittest discover -s tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import scene  # noqa: E402
from change_core.items import Refused  # noqa: E402
from price_model import (  # noqa: E402
    CellKey, CellValue, Target, TargetTable, decode_request, encode_key, encode_request, encode_snapshot,
)
from price_pages import red_lines, render_preview  # noqa: E402
from price_plan import counts, plan_steps, plan_targets, unresolved  # noqa: E402
from test_pages import visible  # noqa: E402

D = Decimal
ROOM, PLAN = "디럭스", "조식 포함"


def key(day, occupancy="A2", nights=1, room=ROOM, plan=PLAN):
    return CellKey(room, plan, day, occupancy, nights)


def table(*targets, sentence="새 요금표"):
    return TargetTable(scene.HOTEL, scene.OFFER, tuple(Target(k, tuple((name, None if v is None else D(v))
                                                                       for name, v in values.items()))
                                                       for k, values in targets), sentence, scene.HOTEL_ID)


class TargetPlanTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = scene.snapshot()

    def test_only_cells_that_differ_are_kept_and_several_fields_move_at_once(self):
        plan = plan_targets(self.snapshot, table(
            (key("2026-12-25"), {"sell": "200.00"}),
            (key("2026-12-26"), {"sell": "210.00", "list": "260.00", "supply": "150.00"}),
            (key("2027-01-01", room="스위트"), {"list": None})))
        self.assertEqual([(c.key.date, c.changed) for c in plan.changes],
                         [("2026-12-26", ("sell", "list", "supply")), ("2027-01-01", ("list",))])
        self.assertEqual(unresolved(plan), ())
        steps = plan_steps(plan)
        self.assertEqual([s.kind for s in steps], ["bulk", "cell_edit"])
        self.assertEqual([(r.sell, r.list, r.supply) for r in steps[0].rows], [(D("210.00"), D("260.00"), D("150.00"))])

    def test_a_target_on_a_day_without_price_is_a_new_cell_written_in_the_bulk_save(self):
        new = key("2027-01-02", room="스위트", plan="룸온리")
        plan = plan_targets(self.snapshot, table((new, {"sell": "450.00", "supply": "300.00"})))
        change = plan.changes[0]
        self.assertEqual((change.marks, change.verdict, change.after.state), (("new",), None, "open"))
        self.assertEqual(counts(plan.changes)["new"], 1)
        steps = plan_steps(plan)
        self.assertEqual([(s.dates, [(r.occupancy, r.sell, r.supply) for r in s.rows]) for s in steps],
                         [(("2027-01-02",), [("A2", D("450.00"), D("300.00"))])])

    def test_a_new_cell_on_a_sales_closure_day_is_predicted_closed_as_the_erp_writes_it(self):
        """날짜별 변경도 ERP 가 새 칸을 판매 가능으로 만들고 지속 마감(요금제 마감 · 객실 전체 마감)인 날에만 마감으로 둔다 — 미리보기가
        그 상태를 말하고, 시즌 다시 채우기의 미리보기와 같은 말을 쓴다. 셀 창 마감은 지속 마감이 아니다(그날 새 칸은 판매 가능)."""
        new = key("2027-01-02", room="스위트", plan="룸온리")
        closure = replace(self.snapshot, closures=frozenset({("스위트", "룸온리", "2027-01-02")}))
        plan = plan_targets(closure, table((new, {"sell": "450.00"})))
        self.assertEqual((plan.changes[0].marks, plan.changes[0].after.state), (("new",), "closed"))
        self.assertEqual([(s.dates, [(r.occupancy, r.sell) for r in s.rows]) for s in plan_steps(plan)],
                         [(("2027-01-02",), [("A2", D("450.00"))])], "저장은 그대로다 — 판매 상태는 ERP 가 정한다")
        page = visible(render_preview(plan))
        self.assertIn("만듭니다 · 판매 마감으로(판매 마감 날에 새로 생기는 칸)", page)
        self.assertIn("판매 마감 날에 새로 생기는 칸 · 1칸. 요금제 마감 · 객실 전체 마감인 날의 새 칸은 ERP 가 마감으로 만듭니다(팔리지 않습니다 — "
                      "마감을 풀면 이 값으로 팔립니다).", page)
        self.assertIn("마감", page.split("새로 생기는 칸 — 지금은 가격이 없는 칸입니다")[0].split("칸마다 바뀌는 값")[1], "칸 표도 마감을 단다")
        opened = plan_targets(self.snapshot, table((new, {"sell": "450.00"})))
        self.assertEqual(opened.changes[0].after.state, "open", "지속 마감이 아닌 날의 새 칸은 판매 가능이다")
        self.assertNotIn("판매 마감 날에 새로 생기는 칸", visible(render_preview(opened)))

    def test_a_new_cell_needs_a_sell_price_and_an_occupancy_the_room_already_shows(self):
        plan = plan_targets(self.snapshot, table(
            (key("2027-01-02", room="스위트", plan="룸온리"), {"list": "500.00"}),
            (key("2026-12-25", occupancy="A4"), {"sell": "400.00"}),
            (key("2026-12-25", nights=7), {"sell": "150.00"})))
        self.assertEqual(sorted((c.key.occupancy, c.key.nights, c.verdict) for c in plan.changes),
                         [("A2", 1, "NEW_WITHOUT_SELL"), ("A2", 7, "NEW_NOT_SHOWN"), ("A4", 1, "NEW_NOT_SHOWN")])
        self.assertEqual(plan_steps(plan), ())

    def test_the_same_rules_apply_to_the_resulting_cell(self):
        plan = plan_targets(self.snapshot, table(
            (key("2026-12-25"), {"sell": "270.00"}),     # +35% — 1박 이상을 올리니 박수 층 규칙에는 걸리지 않는다
            (key("2026-12-26"), {"sell": "210.00", "supply": "250.00"}),
            (key("2027-01-01", room="스위트"), {"sell": "520.00"}),
            (key("2027-01-02", room="스위트"), {"sell": "0"})))
        self.assertEqual([c.verdict for c in plan.changes], ["OVER_30", "BELOW_COST", "ABOVE_LIST", "NOT_POSITIVE"])

    def test_targets_outside_what_was_read_and_bad_tables_are_refused(self):
        with self.assertRaises(Refused):
            plan_targets(self.snapshot, table((key("2026-12-31"), {"sell": "200.00"})))
        with self.assertRaises(Refused) as caught:
            plan_targets(self.snapshot, table((key("2026-12-25", room="패밀리"), {"sell": "200.00"})))
        self.assertIn("패밀리 · 조식 포함", str(caught.exception))
        with self.assertRaises(ValueError):
            table((key("2026-12-25"), {"sell": "1"}), (key("2026-12-25"), {"sell": "2"}))
        with self.assertRaises(ValueError):
            table((key("2026-12-25"), {"sell": None}))
        with self.assertRaises(ValueError):
            table((key("2026-12-25"), {"tax": "1"}))

    def test_json_round_trip(self):
        request = table((key("2026-12-25"), {"sell": "200.00", "list": None}))
        self.assertEqual(decode_request(encode_request(request)), request)


class TargetLinesTest(unittest.TestCase):
    """T6 — 담당자의 표는 객실 · 요금제 · 날짜 · 값만 적는다. 그 객실 · 요금제에 읽힌 줄이 하나뿐이면 그 줄이다."""

    def setUp(self):
        whole = scene.snapshot()
        # 디럭스 조식 포함은 성인 2 · 1박 이상 줄 하나만 읽힌 호텔처럼
        self.snapshot = replace(whole, cells={k: v for k, v in whole.cells.items()
                                              if (k.room, k.rate_plan) != (ROOM, PLAN) or (k.occupancy, k.nights) == ("A2", 1)})

    def test_a_target_without_occupancy_or_nights_means_the_only_line(self):
        request = table((key("2026-12-25", occupancy=None, nights=None), {"sell": "210.00"}))
        plan = plan_targets(self.snapshot, request)
        self.assertEqual([(c.key.occupancy, c.key.nights, c.after.sell) for c in plan.changes], [("A2", 1, D("210.00"))])
        self.assertEqual(plan.request.targets[0].key, key("2026-12-25"), "미리보기 · 장부의 요청은 채운 줄이다")
        text = visible(render_preview(plan))
        self.assertIn("칸 성인 2 · 1박 이상", text, "미리보기 머리가 어느 줄인지 말한다")

    def test_several_lines_are_refused_with_the_lines_to_choose_from(self):
        with self.assertRaises(Refused) as caught:
            plan_targets(scene.snapshot(), table((key("2026-12-25", occupancy=None, nights=None), {"sell": "210.00"})))
        message = str(caught.exception)
        for line in ("성인 2 · 1박 이상(A2 · 1)", "성인 2 · 3박 이상(A2 · 3)", "성인 2 + 아동 1 · 3박 이상(A2C1_CHD · 3)"):
            self.assertIn(line, message)
        self.assertIn("인원 조합(occupancy)과 박수(nights)를 적습니다", message)
        # 인원 조합만 적고 박수가 없으면 그 인원 조합의 박수 층이 하나일 때만
        with self.assertRaises(Refused) as caught:
            plan_targets(scene.snapshot(), table((key("2026-12-25", nights=None), {"sell": "210.00"})))
        self.assertIn("성인 2 · 1박 이상(A2 · 1) / 성인 2 · 3박 이상(A2 · 3)", str(caught.exception))
        one_tier = replace(scene.snapshot(), cells={k: v for k, v in scene.snapshot().cells.items() if k.nights == 1})
        plan = plan_targets(one_tier, table((key("2026-12-25", occupancy="A3", nights=None), {"sell": "300.00"})))
        self.assertEqual([(c.key.occupancy, c.key.nights) for c in plan.changes], [("A3", 1)])

    def test_a_table_file_may_leave_the_line_out_and_an_empty_occupancy_still_means_no_occupancy(self):
        data = encode_request(table((key("2026-12-25"), {"sell": "210.00"})))
        data["targets"][0]["key"] = {"room": ROOM, "rate_plan": PLAN, "date": "2026-12-25"}
        self.assertEqual(decode_request(data).targets[0].key, key("2026-12-25", occupancy=None, nights=None))
        data["targets"][0]["key"].update(occupancy="", nights=1)
        self.assertEqual(decode_request(data).targets[0].key, key("2026-12-25", occupancy="", nights=1), "빈 키는 인원 무관 줄이다")
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            data["targets"][0]["key"] = {"room": ROOM, "rate_plan": PLAN, "date": "2026-12-25"}
            (folder / "s.json").write_text(json.dumps(encode_snapshot(self.snapshot), ensure_ascii=False), encoding="utf-8")
            (folder / "t.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            done = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "price_change.py"), "plan", "--record",
                                   "--snapshot", str(folder / "s.json"), "--request", str(folder / "t.json")],
                                  capture_output=True, text=True, env=scene.env(str(folder)))
            self.assertEqual(done.returncode, 0, done.stderr)
            result = json.loads(done.stdout)
            self.assertEqual(result["plan"]["request"]["targets"][0]["key"], encode_key(key("2026-12-25")))
            self.assertEqual(len(result["steps"]), 1)


class TargetPageAndCommandTest(unittest.TestCase):
    def test_preview_lists_new_cells_and_the_command_plans_a_target_table(self):
        request = table((key("2027-01-02", room="스위트", plan="룸온리"), {"sell": "450.00"}),
                        (key("2026-12-25"), {"sell": "205.00"}))
        text = visible(render_preview(plan_targets(scene.snapshot(), request)))
        self.assertIn("미리보기 · 데모 호텔 · 기본 오퍼 · 목표 값 2칸", text)
        self.assertIn("1 새로 생기는 칸", text)
        self.assertIn("새로 → 450.00 새 칸", text)
        self.assertIn("새로 생기는 칸 — 지금은 가격이 없는 칸입니다", text)
        self.assertIn("새로 생기는 칸은 나중에 되돌리기로 지울 수 없습니다", text)
        # T5 — 있던 칸에 정가 · 공급 원가를 넣는 것은 새 칸이 아니다(되돌리면 비워진다). 그 말은 새 칸이 있을 때만 나온다
        onto = visible(render_preview(plan_targets(scene.snapshot(), table((key("2026-12-25"), {"list": "260.00", "supply": "150.00"})))))
        self.assertIn("1 바뀌는 칸", onto)
        self.assertNotIn("새로 생기는 칸", onto)
        self.assertNotIn("지울 수 없습니다", onto)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "s.json").write_text(json.dumps(encode_snapshot(scene.snapshot()), ensure_ascii=False), encoding="utf-8")
            (folder / "t.json").write_text(json.dumps(encode_request(request), ensure_ascii=False), encoding="utf-8")
            done = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "price_change.py"), "plan",
                                   "--snapshot", str(folder / "s.json"), "--request", str(folder / "t.json")],
                                  capture_output=True, text=True, env=scene.env(str(folder)))
            self.assertEqual(done.returncode, 0, done.stderr)
            result = json.loads(done.stdout)
            self.assertEqual((result["counts"]["new"], len(result["steps"])), (1, 2))
            self.assertEqual(result["plan"]["changes"][0]["key"], encode_key(key("2027-01-02", room="스위트", plan="룸온리")))


class RowNotThereTest(unittest.TestCase):
    """W1 (시운전 11) — 이 객실 · 요금제에 없는 줄(「성인 2 · 5박 이상」)의 값을 넣으라면 막는다(`NEW_NOT_SHOWN`). 그 칸은 생기지 않으니
    「새로 생기는 칸」으로 세지도 · 늘어놓지도 · 되돌려도 지울 수 없다고 하지도 않는다(예약 있는 날이어도 「바꿉니다」로 세지 않는다).
    까닭은 줄이 없다는 것이고 금액을 바꾸라고 하지 않으며, 대신 할 수 있는 것(ERP 에서 사람이 만듦 · 시즌 다시 채우기)을 댄다.
    아무것도 고르지 않았으니 「고르신 대로면」이라고 하지 않는다. 미리보기 머리의 칸 수와 장부 한 줄의 칸 수가 같다."""

    def test_a_row_the_room_does_not_have_is_refused_in_true_words_and_never_counted_as_created(self):
        missing = key("2026-12-25", nights=5)   # 디럭스 · 조식 포함 · 12/25 는 예약 있는 날이다
        plan = plan_targets(scene.snapshot(), table((missing, {"sell": "45.00"})))
        tally = counts(plan.changes)
        self.assertEqual({name: tally[name] for name in ("blocked", "NEW_NOT_SHOWN", "new", "reserved", "will_change")},
                         {"blocked": 1, "NEW_NOT_SHOWN": 1, "new": 0, "reserved": 0, "will_change": 0})
        text = visible(render_preview(plan))
        for wrong in ("새로 생기는 칸", "지울 수 없", "ERP 가 받지 않는 값", "금액을 바꿔 다시", "고르신 대로면", "예약 있는 날의 칸"):
            self.assertNotIn(wrong, text)
        for said in ("미리보기 · 데모 호텔 · 기본 오퍼 · 목표 값 0칸", "금액을 바꿔도 같습니다", "「추가할 인원 조합」",
                     "바꿀 수 있는 칸이 없어 저장할 것이 없습니다. 아무것도 바뀌지 않았습니다."):
            self.assertIn(said, text)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "s.json").write_text(json.dumps(encode_snapshot(scene.snapshot()), ensure_ascii=False), encoding="utf-8")
            (folder / "t.json").write_text(json.dumps(encode_request(table((missing, {"sell": "45.00"}))), ensure_ascii=False),
                                           encoding="utf-8")
            cli = [sys.executable, str(HERE.parent / "scripts" / "price_change.py")]
            done = subprocess.run([*cli, "plan", "--record", "--snapshot", str(folder / "s.json"), "--request", str(folder / "t.json"),
                                   "--out", str(folder / "plan-1.json")], capture_output=True, text=True, env=scene.env(str(folder)))
            self.assertEqual(done.returncode, 0, done.stderr)
            short = json.loads(done.stdout)
            self.assertEqual((short["saves"], short["counts"]["new"], [line["rule"] for line in short["blocked"]]), (0, 0, ["NEW_NOT_SHOWN"]))
            self.assertEqual(short["blocked"][0]["said"],
                             "적용할 수 없는 1칸(12/25 금 · 디럭스 · 조식 포함 · 성인 2 · 5박 이상)은 이 객실 · 요금제에는 그 인원 조합 · 박수 "
                             "줄이 없어 넣을 수 없습니다 — 금액을 바꿔도 같습니다. 그 줄은 ERP 에서 사람이 만듭니다 — 그날 가격 수정 창의 "
                             "「추가할 인원 조합」이나 시즌의 [가격 입력] 창에서요. 박수 층이면 그 시즌을 다시 채우라고 하실 때 도우미가 만들 수 "
                             "있습니다.")
            self.assertEqual(short["nothing"], "바꿀 수 있는 칸이 없어 저장할 것이 없습니다. 아무것도 바뀌지 않았습니다.")
            listed = subprocess.run([*cli, "list", "--all"], capture_output=True, text=True, env=scene.env(str(folder)))
            line, = [entry["line"] for entry in json.loads(listed.stdout)["changes"]]
            self.assertTrue(line.endswith("· 목표 값 0칸 · 저장할 것 없음"), line)


class AlreadyBelowCostTest(unittest.TestCase):
    """W7 (시운전 9) — 바꾸기 전부터 공급 원가보다 쌌던 칸의 빨간 줄은 「싸집니다」가 아니라 「이미 공급 원가보다 쌉니다 — 이번에도
    그대로」다(날짜별 길 — 시즌 다시 채우기와 같은 이름). 섞였으면 그 수를 댄다."""

    def test_the_red_line_names_cells_that_were_below_cost_before_the_change(self):
        days = ("2026-12-25", "2026-12-26")
        now = {(1, "50.00"), (3, "45.00")}            # 1박 이상 · 3박 이상 모두 공급 원가 52.00 아래
        wanted = {1: "51.00", 3: "46.00"}             # 3박 이상이 1박 이상보다 싸게 남아 박수 층 규칙에 걸리지 않는다
        below = scene.with_cells(scene.snapshot(), {key(day, nights=n, room="스위트"): CellValue(D(sell), None, D("52.00"), "open")
                                                   for day in days for n, sell in now})
        targets = [(key(day, nights=n, room="스위트"), {"sell": wanted[n]}) for day in days for n in wanted]
        plan = plan_targets(below, table(*targets))
        line, = red_lines(plan)
        self.assertEqual((line["rule"], line["label"], line["cells"]), ("BELOW_COST", "이미 공급 원가보다 쌉니다 — 이번에도 그대로", 4))
        self.assertIn("빨간 줄 · 4칸이 이미 공급 원가보다 쌉니다 — 이번에도 그대로.", visible(render_preview(plan)))
        mixed = scene.with_cells(below, {key(days[1], room="스위트"): CellValue(D("60.00"), None, D("52.00"), "open")})
        line, = red_lines(plan_targets(mixed, table(*targets)))
        self.assertEqual(line["label"], "공급 원가보다 싸집니다(그 가운데 3칸은 이미 공급 원가보다 쌉니다 — 이번에도 그대로)")

if __name__ == "__main__":
    unittest.main()
