"""B12 판매일 없는 날 — 가격 수정 창은 그런 날이 끼면 기간을 통째로 거절하므로 읽지 않고, 「판매일 없음」(「가격 없음」과
다르다)으로 알리고, 계산은 그 날을 그 까닭으로 건너뛴다.

    python3 -m unittest discover -s tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(HERE.parent / "scripts"))

import scene  # noqa: E402
from browser_replies import reply  # noqa: E402
from erp_read import PairRead, ParseError, build_snapshot, parse_price_page  # noqa: E402
from change_core.answers import BrowserError  # noqa: E402
from price_browser import pair_reads  # noqa: E402
from price_model import (  # noqa: E402
    CellKey, ChangeRequest, Target, TargetTable, decode_plan, decode_snapshot, encode_plan, encode_snapshot,
)
from price_pages import render_preview, render_prices  # noqa: E402
from price_plan import plan_change, plan_targets  # noqa: E402

PRICE = (HERE / "fixtures" / "erp" / "price-runs-closed-absent-list.html").read_text(encoding="utf-8")   # 12/24 ~ 12/31
PAGE = parse_price_page(PRICE)
CLOSED_DAYS = ("2027-01-01", "2027-01-02")
ASKED = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-24", "to": "2027-01-02",
         "weekdays": list("월화수목금토일")}


def snapshot():
    return build_snapshot("데모 호텔", "2026-11-20T19:00:00+09:00", [PairRead("샘플 오퍼", "디럭스", "조식 포함", PAGE, CLOSED_DAYS)],
                          hotel_id="1")


class NoSaleTest(unittest.TestCase):
    def test_the_page_answer_carries_days_with_no_sale_day_and_must_cover_the_question(self):
        read, = pair_reads(reply("readPair", ASKED, {"fragment": PRICE, "noSale": list(CLOSED_DAYS)}))
        self.assertEqual((read.no_sale, sorted(read.page.days)[0]), (CLOSED_DAYS, "2026-12-24"))
        with self.assertRaisesRegex(BrowserError, "물은 날과 맞지 않습니다"):
            pair_reads(reply("readPair", ASKED, {"fragment": PRICE, "noSale": ["2027-01-01"]}))
        with self.assertRaisesRegex(BrowserError, "물은 날과 맞지 않습니다"):
            pair_reads(reply("readPair", ASKED, {"fragment": PRICE, "noSale": [*CLOSED_DAYS, "2026-12-24"]}))
        closed = dict(ASKED, **{"from": "2027-01-01", "to": "2027-01-02"})
        nothing, = pair_reads(reply("readPair", closed, {"fragment": None, "noSale": list(CLOSED_DAYS)}))
        self.assertIsNone(nothing.page)

    def test_the_snapshot_keeps_them_apart_from_days_without_a_price(self):
        snap = decode_snapshot(encode_snapshot(snapshot()))
        self.assertEqual(snap.no_sale, {("디럭스", day) for day in CLOSED_DAYS})
        self.assertEqual(snap.cells[CellKey("디럭스", "조식 포함", "2026-12-28", "A2", 1)].state, "missing", "가격 없음은 칸이 있다")
        self.assertFalse(any(key.date in CLOSED_DAYS for key in snap.cells), "판매일 없음은 칸이 없다")
        page = render_prices(snap)
        self.assertIn("판매일 없는 날 (객실 · 날짜)", page)
        self.assertIn("판매일 없음(판매일이 열리지 않은 날", page)

    def test_a_read_with_no_open_day_counts_as_read_but_not_alone(self):
        only = PairRead("샘플 오퍼", "스위트", "조식 포함", None, CLOSED_DAYS)
        snap = build_snapshot("H", "t", [PairRead.of("디럭스", PAGE), only])
        self.assertIn(("스위트", "조식 포함"), snap.pairs)
        self.assertIn(("스위트", "2027-01-01"), snap.no_sale)
        with self.assertRaisesRegex(ParseError, "모두 판매일 없음"):
            build_snapshot("H", "t", [only])
        with self.assertRaisesRegex(ParseError, "판매일 없음이면서 읽은 화면에도"):
            PairRead("샘플 오퍼", "디럭스", "조식 포함", PAGE, ("2026-12-24",))

    def test_planning_lists_them_as_skipped_with_that_reason_and_changes_the_open_days(self):
        request = ChangeRequest(hotel="데모 호텔", hotel_id="1", offer="샘플 오퍼", rooms=("디럭스",), rate_plans=("조식 포함",),
                                dates=("2026-12-24", "2027-01-01", "2027-01-02"), operation="amount", value=D("5"))
        plan = plan_change(snapshot(), request)
        self.assertEqual(plan.no_sale, tuple(("디럭스", "조식 포함", day) for day in CLOSED_DAYS))
        self.assertEqual({change.key.date for change in plan.changes}, {"2026-12-24"})
        self.assertEqual(decode_plan(encode_plan(plan)).no_sale, plan.no_sale)
        self.assertIn("판매일 없음(판매일이 열리지 않아 바꿀 수 없는 날", render_preview(plan, None, []))
        self.assertIn("1/1 금 ~ 1/2 토", render_preview(plan, None, []))

    def test_target_tables_skip_them_too(self):
        targets = TargetTable("데모 호텔", "샘플 오퍼", (
            Target(CellKey("디럭스", "조식 포함", "2026-12-24", "A2", 1), (("sell", D("150.00")),)),
            Target(CellKey("디럭스", "조식 포함", "2027-01-01", "A2", 1), (("sell", D("150.00")),))), hotel_id="1")
        plan = plan_targets(snapshot(), targets)
        self.assertEqual(plan.no_sale, (("디럭스", "조식 포함", "2027-01-01"),))
        self.assertEqual([change.key.date for change in plan.changes], ["2026-12-24"])


class NoSaleOnlyTest(unittest.TestCase):
    """W2 (시운전 9) — 고른 날이 모두 판매일 없음이면 readPair 의 첫 답(`days.withCell` 0)에서 멈춘다: 다음 명령(`reserved`, 건너뛰었으면
    `read`)이 예약 있는 날 · 조각을 더 읽으라고 하지 않고 거절하며, 거절의 `say` 가 담당자에게 그대로 하는 말이다. 판매일 있는
    날이 하루라도 있으면 그대로 읽는다(판매일 없는 날은 미리보기가 따로 댄다)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = scene.env(str(self.dir / "기록"))

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def answer(self, folder: Path, name: str, asked: dict, days: dict, keep: dict):
        for index, item in enumerate(reply("readPair", asked, keep, days=days)):
            (folder / f"{name}{'' if index == 0 else '-' + str(index)}.json").write_text(json.dumps(item, ensure_ascii=False),
                                                                                       encoding="utf-8")

    def test_every_chosen_day_without_a_sale_day_stops_at_the_first_answer_with_a_sentence_to_say(self):
        closed = dict(ASKED, **{"from": "2027-01-01", "to": "2027-01-02"})
        probe = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "rooms": ["디럭스"], "ratePlans": ["조식 포함"], "from": "2027-01-01",
                 "to": "2027-01-02", "weekdays": list("월화수목금토일"), "occupancy": "*", "nights": "all"}
        folder = self.dir / "읽기-1"
        folder.mkdir()
        calls = folder / "calls.json"
        calls.write_text(json.dumps({"pairs": [closed], "reserved": [probe]}, ensure_ascii=False), encoding="utf-8")
        self.answer(folder, "pair-1", closed, {"asked": 2, "noSale": 2, "withCell": 0}, {"fragment": None, "noSale": list(CLOSED_DAYS)})
        said = ("1/1 금 ~ 1/2 토 (2일, 2027년)은 샘플 오퍼 오퍼의 디럭스(조식 포함)에 판매일이 열려 있지 않습니다 — 그날은 가격을 "
                "읽을 수도 넣을 수도 없습니다. 판매일은 ERP 의 판매일 탭에서 사람이 엽니다. 아무것도 바꾸지 않았고 장부에도 적지 않았습니다.")
        for command in (("reserved", "--calls", calls, "--answers", folder),
                        ("read", "--calls", calls, "--answers", folder, "--out", folder / "snapshot.json")):
            refused = self.run_cli(*command, code=2)
            self.assertEqual(refused["say"], said)
            self.assertIn("더 읽지 않습니다", refused["error"])
            self.assertNotIn("refetch", refused, "조각을 받으라고 하지 않는다")
        self.assertFalse((folder / "snapshot.json").exists())

        open_day = dict(ASKED, **{"from": "2026-12-24", "to": "2026-12-24"})
        calls.write_text(json.dumps({"pairs": [closed, open_day], "reserved": [probe]}, ensure_ascii=False), encoding="utf-8")
        self.answer(folder, "pair-2", open_day, {"asked": 1, "noSale": 0, "withCell": 1}, {"fragment": PRICE})
        self.assertFalse(self.run_cli("reserved", "--calls", calls, "--answers", folder)["done"], "판매일 있는 날이 있으면 그대로 읽는다")


if __name__ == "__main__":
    unittest.main()
