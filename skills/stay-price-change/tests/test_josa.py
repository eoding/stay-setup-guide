"""W4 (시운전 10) — 담당자에게 읽어 주는 줄의 조사는 앞 낱말의 끝소리로 하나를 고른다. 「취소 조건이(가)」 · 「할인 값 14 으로」를
그대로 읽어 주었다. 네 도우미가 한 함수(change_core.words.josa)를 쓴다.

    python3 -m unittest discover -s tests
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from change_core.words import josa  # noqa: E402


class JosaTest(unittest.TestCase):
    def test_a_number_takes_ro_or_euro_by_how_its_last_digit_sounds(self):
        said = {number: josa(number, "으로") for number in ("14", "16", "10", "13", "17", "55", "15.0", "100", "2", "0.5")}
        self.assertEqual(said, {"14": "14로", "16": "16으로", "10": "10으로", "13": "13으로", "17": "17로", "55": "55로",
                                "15.0": "15.0으로", "100": "100으로", "2": "2로", "0.5": "0.5로"})

    def test_words_and_codes_take_the_particle_their_last_sound_needs(self):
        self.assertEqual([josa("취소 조건", "이가"), josa("환불 규정", "이가"), josa("16%", "으로"), josa("350.00 USD", "으로"),
                          josa("갈라 디너", "은는"), josa("「갈라 디너」", "은는"), josa("메일", "으로"), josa("CHD", "이가")],
                         ["취소 조건이", "환불 규정이", "16%로", "350.00 USD로", "갈라 디너는", "「갈라 디너」는", "메일로", "CHD가"])

    def test_an_ending_it_cannot_read_keeps_both(self):
        self.assertEqual((josa("…", "이가"), josa("…", "으로")), ("…이(가)", "…(으)로"))

    def test_every_helper_says_a_new_value_with_one_particle(self):
        """도우미마다 「새 값으로」 한 일 — 장부 한 줄 · 확인 상자가 쓴다."""
        for folder in ("stay-addon-price-change", "stay-charge-change", "stay-promotion-change"):
            sys.path.insert(0, str(SKILLS / folder / "scripts"))
        import addon_model
        import charge_model
        import promotion_model
        self.assertEqual(promotion_model.ChangeRequest("H", "1", (), "value", Decimal("14"), "").describe(), "할인 값 14로")
        self.assertEqual(addon_model.ChangeRequest("H", "1", "sell", "value", Decimal("16"), "").describe()[-5:], " 16으로")
        charge = charge_model.ChangeRequest("H", "1", (charge_model.Target("601", charge_model.Place("701", "main", "", "pct")),),
                                            "value", Decimal("60"), "")
        self.assertEqual(charge.describe(), "정률(%) 60으로")


if __name__ == "__main__":
    unittest.main()
