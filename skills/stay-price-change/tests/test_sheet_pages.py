"""새 요금표의 페이지 — 「요금표를 이렇게 읽었습니다」(S5)와, 요금표 미리보기의 넣지 않는 것(S4) · 시즌 [가격] 덮기 한 문장(S7).

    python3 -m unittest discover -s tests
"""

import copy
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import scene  # noqa: E402
import sheet_scene as S  # noqa: E402
from price_pages import SEASON_REFILL_NOTE, render_preview, render_sheet  # noqa: E402
from price_plan import plan_change  # noqa: E402
from price_sheet import Part, SheetCheck, decode_sheet, plan_sheet  # noqa: E402
from test_pages import SelfContainedMixin, visible  # noqa: E402

PAIRS = (("디럭스", S.PLAN), ("스위트", S.PLAN), ("패밀리", S.PLAN))


class SheetPageTest(SelfContainedMixin, unittest.TestCase):
    """S5 — 요금표의 모양: 객실이 줄, 기간이 열, 칸 안에 인원 · 박수. 셈한 값은 「계산」과 그 셈. ERP 를 읽기 전에 보인다."""

    def setUp(self):
        data = S.sheet_data()
        data["lines"].append(dict(copy.deepcopy(data["lines"][0]), room="펜트하우스"))
        self.page = render_sheet(SheetCheck(decode_sheet(data), PAIRS))
        self.text = visible(self.page)

    def test_rooms_go_down_and_periods_go_across(self):
        self.assert_self_contained(self.page)
        heads = re.findall(r'<th class="days">(.*?)</th>', self.page)
        self.assertEqual([visible(head) for head in heads],
                         ["비수기 1/4 ~ 1/10 월·화·수·목·일", "비수기 1/4 ~ 1/10 금·토", "성수기 1/11 ~ 1/17 월·화·수·목·일",
                          "성수기 1/11 ~ 1/17 금·토"])
        rooms = [visible(cell) for cell in re.findall(r"<tr><td class=\"text\">(.*?)</td>", self.page)]
        self.assertEqual(rooms, ["디럭스 · 조식 포함", "스위트 · 조식 포함", "펜트하우스 · 조식 포함 호텔에 없음"])

    def test_each_cell_shows_its_line_and_every_row_with_calculated_values_marked(self):
        first = visible(re.search(r"<tr><td class=\"text\">디럭스.*?</tr>", self.page).group(0))
        self.assertIn("1번째 줄 성인 2 · 1박 이상 200.00 성인 3 · 1박 이상 260.00 계산 판매가 = 성인 2 · 1박 이상 200.00 + 60 "
                      "성인 2 + 아동 1 · 1박 이상 230.00 계산 판매가 = 성인 2 · 1박 이상 200.00 + 30 "
                      "성인 2 · 3박 이상 180.00 계산 판매가 = 성인 2 · 1박 이상 200.00 - 10%", first)
        self.assertIn("2번째 줄 성인 2 · 1박 이상 240.00", first)

    def test_it_says_nothing_was_read_and_what_will_be_read_after_yes(self):
        self.assertIn("요금표를 이렇게 읽었습니다 · 데모 호텔 · 기본 오퍼", self.text)
        self.assertIn("아직 이 요금표의 범위로 ERP 의 가격을 읽지 않았고, 아무것도 바뀌지 않았습니다.", self.text)
        self.assertIn("호텔(이 오퍼)에 없는 객실 · 요금제 펜트하우스 · 조식 포함 (9번째 줄) — 이 줄은 넣지 않습니다", self.text)
        self.assertIn("요금표에 없는 객실 · 요금제 패밀리 · 조식 포함 — 가격을 그대로 둡니다", self.text)
        self.assertIn("객실 · 요금제 2개 × 14일(2027-01-04 ~ 2027-01-17", self.text)
        self.assertIn("가격 읽기 2번, 예약 있는 날 읽기 1번", self.text)
        self.assertIn('맞으면 대화창에서 "맞아"라고 해 주세요.', self.text)

    def test_a_part_says_which_part(self):
        text = visible(render_sheet(SheetCheck(decode_sheet(S.sheet_data()), PAIRS, Part(("스위트",), "2027-01-11", None))))
        self.assertIn("이번에 하는 부분 스위트 / 2027-01-11 ~ 끝", text)
        self.assertIn("객실 · 요금제 1개 × 7일(2027-01-11 ~ 2027-01-17", text)
        self.assertNotIn("디럭스 · 조식 포함", text)


class SheetPreviewTest(unittest.TestCase):
    """S4 · S7 — 요금표 미리보기는 넣지 않는 것을 종류마다 보이고, 시즌 [가격] 덮기 한 문장을 단다. 다른 미리보기는 그 문장이 없다."""

    def test_the_preview_lists_what_the_sheet_leaves_out_and_the_season_refill_sentence(self):
        plan = plan_sheet(S.reading(), SheetCheck(decode_sheet(S.sheet_data()), PAIRS))
        text = visible(render_preview(plan))
        self.assertIn("미리보기 · 데모 호텔 · 기본 오퍼 · 새 요금표 108칸", text)
        self.assertIn(SEASON_REFILL_NOTE, text)
        self.assertIn("요금표가 넣지 않는 것", text)
        self.assertIn("요금표에 없는 칸 — 그대로 둡니다 · 13칸 객실 · 요금제 인원 · 박수 날짜 요금표 줄 "
                      "스위트 · 조식 포함 성인 1 · 1박 이상 1/4 ~ 1/12, 1/14 ~ 1/17 (13일)", text)
        self.assertIn("판매일 없는 날 — 이 길로는 넣을 수 없습니다 · 1일", text)
        self.assertIn("요금표에 없는 객실 · 요금제 — 그대로 둡니다 · 1개", text)
        self.assertNotIn("이 객실 · 요금제에 없는 인원 조합", text)
        self.assertNotIn(SEASON_REFILL_NOTE, visible(render_preview(plan_change(scene.snapshot(), scene.request()))))


if __name__ == "__main__":
    unittest.main()
