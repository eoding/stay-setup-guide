import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'explain_field.py'


class TestExplainField(unittest.TestCase):
    def call(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)

    def test_hotel_name_help_reports_customer_location(self):
        result = self.call('호텔명', '--screen', '호텔 만들기', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)['matches']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['label'], '호텔명')
        self.assertIn('히어로', str(rows[0]['web']))

    def test_inventory_help_distinguishes_total_from_remaining(self):
        result = self.call('총 수량', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)['matches']
        self.assertEqual(len(rows), 2)
        self.assertTrue(all('남음' in row['effect'] for row in rows))

    def test_unknown_field_does_not_invent_help(self):
        result = self.call('계약서에 없는 가상 칸', '--json')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['matches'], [])

    def test_effect_map_matches_current_dictionary_for_rendering(self):
        sys.path.insert(0, str(SCRIPT.parent))
        import render_screen_guide as rsg
        root = SCRIPT.parent.parent / 'references'
        data = rsg.load_dictionary(root / 'screen-dictionary.json')
        impact = rsg.load_impact(root / 'screen-effects.json')
        page, stats = rsg.render_guide(data, version='1.5.0', impact=impact)
        self.assertEqual(stats['fields'], 243)
        self.assertIn('허용 인원 조합', page)


if __name__ == '__main__':
    unittest.main()
