"""시즌 [가격 입력] 창의 셈 — `fixtures/season_fill_cases.json` 의 경우표 A~R. 기대값은 손으로 셈한 것이다(ERP 코드는 없다).

ERP 규칙의 근거(우리말로 옮김): basecamp `stay/services/season.py` — 조정은 부호 필수 · 0.01 반올림 · 요금제 조정 먼저 그 위에 인원 조합
조정, 아동 조합은 성인 칸 + 구간 금액(비율 구간은 성인 1인 추가분 × 비율), 박수 층은 1박 판매가만 갈리고 정가 · 공급 원가는 1박 것,
`fill_season_price` — 판매일 없는 날은 칸마다 건너뜀, 있는 칸은 덮기일 때만 판매가 · (준) 정가 · (준) 원가, 상태는 그대로, 없는 칸은
판매 가능(지속 마감이 덮으면 마감)으로 생김, 고르지 않은 좌표는 그대로. `stay/services/pricing/money.py` — 공급 원가는 통화 단위로
반 올림(원화 0자리). `stay/services/occupancy_combo.py` — 허용 조합 밖 좌표는 그 객실에 깔지 않는다.

.plans 의 parity/test_season_parity.py 가 같은 표를 ERP 의 함수에 넣어 같은 값이 나오는지 본다(이 저장소 밖에서 돈다).
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import season_scene as scene  # noqa: E402
from change_core.money import round_money  # noqa: E402
from price_model import CellKey  # noqa: E402
from price_season import child_rates, plan_season, want_form  # noqa: E402
from season_expand import SeasonRefused, key_allowed, los_matrix, parse_combos, parse_inputs, parse_keys  # noqa: E402

PURE = {item["id"]: item for item in scene.CASES["pure"]}


def triple(values):
    return tuple(None if value is None else Decimal(value) for value in values)


def inputs_of(case):
    save = scene.save_of(dict(case["inputs"], pairs=[["디럭스", "조식 포함"]]))
    return parse_inputs({name: save.text(name) for name in ("price", "original_price", "net_price", "plan_adjust", "occupancy_keys",
                                                             "occupancy_adjust", "los_prices")},
                        child_rates(scene.window(bands=case.get("bands")), save))


class PureCasesTest(unittest.TestCase):
    """A~I — 금액표 · 입력 문법 · 허용 조합. 표의 키 차례(성인 키 바로 뒤에 그 아동 키)도 본다 — ERP 가 그 차례로 칸을 만든다."""

    def assert_matrix(self, case_id):
        case = PURE[case_id]
        matrices = los_matrix(inputs_of(case))
        for nights, tables in case["expect"].items():
            base, plan = matrices[int(nights)]
            for name, table in (("base", base), ("plan", plan)):
                if name not in tables:
                    continue
                want = {key: triple(values) for key, values in tables[name].items()}
                self.assertEqual({key: table[key] for key in want}, want, f"{case_id} · {nights}박 · {name}")
                self.assertEqual([key for key in table if key in want], list(want), f"{case_id} 키 차례")

    def test_a_plan_adjustment_first_then_occupancy_then_children_and_the_tier_keeps_one_night_net(self):
        self.assert_matrix("A")

    def test_b_a_percent_band_takes_its_share_of_the_next_adult_or_the_average_and_free_or_unusable_bands_make_no_cells(self):
        self.assertEqual([rate.code for rate in child_rates(scene.window(bands=PURE["B"]["bands"]),
                                                            scene.save_of({"pairs": [["디럭스", "조식 포함"]], "price": "1"}))],
                         PURE["B"]["rates"])
        self.assert_matrix("B")

    def test_c_a_percent_adjustment_rounds_half_up_to_the_cent(self):
        self.assert_matrix("C")

    def test_d_won_net_is_stored_rounded_to_the_won(self):
        self.assert_matrix("D")
        self.assertEqual(round_money(Decimal("76000.95"), "KRW"), Decimal(PURE["D"]["net_stored"]))

    def test_e_bare_numbers_become_adult_keys_and_trailing_commas_fold(self):
        self.assertEqual(parse_keys(PURE["E"]["inputs"]["occupancy_keys"]), PURE["E"]["keys"])

    def test_f_room_combos_decide_which_keys_the_room_takes(self):
        combos = parse_combos(PURE["F"]["combos"])
        self.assertEqual({key: key_allowed(combos, key) for key in PURE["F"]["allowed"]}, PURE["F"]["allowed"])

    def test_g_h_a_negative_result_or_a_missing_sign_refuses_the_whole_save(self):
        for case_id in ("G", "H"):
            with self.assertRaises(SeasonRefused) as caught:
                inputs_of(PURE[case_id])
            self.assertIn(PURE[case_id]["refused"], str(caught.exception))

    def test_i_a_typed_child_key_with_its_own_adjustment_keeps_that_value(self):
        self.assert_matrix("I")


class FillCasesTest(unittest.TestCase):
    """J~R — 칸마다 무엇이 되는지와 ERP 가 말할 칸 수(새로 · 덮어쓴 · 판매일 없어 건너뜀)."""

    def planned(self, case_id):
        case = scene.case(case_id)
        window = scene.window(bands=case.get("bands"), combos=case.get("combos"))
        plan = plan_season(scene.snapshot(case["before"], pairs=case["fill"]["pairs"]), window, scene.fill_of(scene.save_of(case["fill"])))
        return case, window, plan.saves[0]

    def test_j_to_r_every_expected_cell_and_count(self):
        for case_id in "JKLMNOPQR":
            with self.subTest(case=case_id):
                case, _window, save = self.planned(case_id)
                self.assertIsNone(save.refused)
                final = dict(scene.snapshot(case["before"], pairs=case["fill"]["pairs"]).cells)
                final.update({change.key: change.after for change in save.changes})
                for item in case["expect"]:
                    key = CellKey(item["room"], item["plan"], item["date"], item["key"], item["nights"])
                    value = final.get(key)
                    if item["cell"] is None:
                        self.assertTrue(value is None or value.state == "missing", f"{case_id} {key} 는 칸이 없어야 합니다")
                        continue
                    sell, listed, net, state = item["cell"]
                    self.assertEqual((value.sell, value.list, value.supply, value.state),
                                     (Decimal(sell), scene.money(listed), scene.money(net), state), f"{case_id} {key}")
                self.assertEqual((save.counts.created, save.counts.updated, save.counts.skipped),
                                 (case["counts"]["created"], case["counts"]["updated"], case["counts"]["skipped"]), case_id)

    def test_o_cells_outside_this_fill_are_left_old(self):
        _case, _window, save = self.planned("O")
        self.assertEqual({(key.occupancy, key.nights) for key in save.left_old}, {("A3", 1), ("A2", 3)})

    def test_p_dates_are_typed_as_runs_that_never_cross_an_unchosen_day(self):
        case, window, save = self.planned("P")
        self.assertIn(["date_selection_0", case["date_selection"]], want_form(window, save.save))
        self.assertIn(["date_selection_1", ""], want_form(window, save.save))

    def test_q_the_combo_skip_is_named_as_the_erp_banner_lists_it(self):
        case, _window, save = self.planned("Q")
        self.assertEqual([list(item) for item in save.combo_skipped], case["combo_skipped"])


if __name__ == "__main__":
    unittest.main()
