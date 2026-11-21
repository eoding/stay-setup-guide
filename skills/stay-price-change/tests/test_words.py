"""K4 · K5 — 말과 페이지: 확인받는 한 줄(`line`), 답 파일 뒤에 도구가 붙인 글, `render --text` 의 제목, 통화에 맞는 말 보기.
세 도우미가 같은 코드(change_core)를 쓴다.

    python3 -m unittest discover -s tests
"""

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import scene  # noqa: E402
from change_core.chrome import page_text  # noqa: E402
from change_core.files import confirm_line, load_results  # noqa: E402
from change_core.money import example_step  # noqa: E402
from price_pages import render_prices  # noqa: E402


class ConfirmLineTest(unittest.TestCase):
    def entry(self, **over):
        return dict(dict(id=7, kind="change", status="applied", read_at="2026-11-21T09:30:00+09:00",
                         created_at="2026-11-21T09:40:00+09:00", applied_at="2026-11-21T09:45:00+09:00", scope="디럭스 · 판매가 +10%"),
                    **over)

    def test_a_change_says_when_it_was_applied_and_a_saved_state_when_its_values_were_read(self):
        self.assertEqual(confirm_line(self.entry()), "장부 7번 · 11/21 09:45 적용 · 디럭스 · 판매가 +10%")
        self.assertEqual(confirm_line(self.entry(kind="snapshot", status="saved", applied_at=None)),
                         "장부 7번 · 11/21 09:30 저장 · 디럭스 · 판매가 +10%")
        self.assertEqual(confirm_line(self.entry(status="previewed", applied_at=None)), "장부 7번 · 11/21 09:40 미리보기 · 디럭스 · 판매가 +10%")
        self.assertEqual(confirm_line(self.entry(status="stopped", applied_at=None)),
                         "장부 7번 · 11/21 09:40 적용하다 멈춤 · 디럭스 · 판매가 +10%")


class AnswerFileTest(unittest.TestCase):
    def test_only_the_operation_s_answer_is_read_from_a_file_the_tool_added_text_to(self):
        answer = {"ok": True, "op": "look", "hotel": {"id": "1", "name": "데모 호텔"}}
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "look-1.json").write_text(json.dumps(answer, ensure_ascii=False) + "\n\nTabs:\n- 데모 호텔 · ERP (현재 탭)\n",
                                                      encoding="utf-8")
            (Path(folder) / "look-2.json").write_text('{"ok": true, "op": "look", "body": {"id": "b1", "cha[TRUNCATED]',
                                                      encoding="utf-8")
            whole, cut = load_results([folder], ("look-",))
        self.assertEqual(dict(whole), answer, "닫힌 JSON 뒤의 탭 목록은 답이 아니다")
        self.assertIsInstance(cut, str, "닫히지 않은 답은 잘린 답 그대로 남는다")


class PageWordsTest(unittest.TestCase):
    def test_render_text_prints_the_title_once_and_the_example_fits_the_currency(self):
        usd = page_text(render_prices(scene.snapshot()))
        lines = usd.splitlines()
        self.assertEqual(lines.count(lines[0]), 1, "제목은 한 번")
        self.assertIn('"12월 디럭스 +10"', usd)
        self.assertNotIn("+10,000", usd, "달러 호텔에 +10,000 을 보기로 들지 않는다")
        krw = page_text(render_prices(replace(scene.snapshot(), currency="KRW")))
        self.assertIn('"12월 디럭스 +10,000"', krw)
        self.assertEqual([example_step(code) for code in ("USD", "EUR", "KRW", "VND", "JPY", "THB")],
                         ["10", "10", "10,000", "100,000", "1,000", "10"])


if __name__ == "__main__":
    unittest.main()
