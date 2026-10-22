import json
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / 'scripts'))
import check_manual as cm
import render_screen_guide as screen
import sync_screen_dictionary as sync


def question(kind='객관식', choices='10:15\n12:15', card='샘플 오퍼 · 혜택 · 무료 픽업', required='체크'):
    return cm.parse_steps(f'''## 1. 정보 수집 질문 만들기
탭: 혜택
카드: {card}
| 칸 | 값 |
|---|---|
| 구분 | 선택: {kind} |
| 질문 | 이용 시간 |
| 필수 여부 | {required} |
| 선택지 표시 방식 | 선택: 칩 선택형 |
| 안내문 | 비움 |
선택지 (한 줄에 하나):
```
{choices}
```
→ [질문 추가]
'''.splitlines())


class CustomerOptionContract(unittest.TestCase):
    def test_question_contract_accepts_comma_inside_choice(self):
        self.assertEqual(cm.find_customer_option_gaps(question(choices='서울, 인천\n제주')), [])

    def test_rejects_ambiguous_owner_and_duplicate_choices(self):
        self.assertTrue(cm.find_customer_option_gaps(question(card='무료 픽업')))
        self.assertTrue(cm.find_customer_option_gaps(question(choices='10:15\n10:15')))

    def test_rejects_missing_choices_and_required_information(self):
        self.assertTrue(cm.find_customer_option_gaps(question(choices='')))
        self.assertTrue(cm.find_customer_option_gaps(question(kind='서술형', choices='')))
        self.assertFalse(cm.find_customer_option_gaps(question(kind='서술형', choices='', required='해제')))

    def test_question_title_and_choice_limits(self):
        self.assertTrue(cm.find_customer_option_gaps(question(choices='가' * 201)))
        self.assertTrue(cm.find_customer_option_gaps(question(choices='\n'.join(str(n) for n in range(101)))))
        steps = question()
        steps[0]['fields']['질문'] = '가' * 201
        self.assertTrue(cm.find_customer_option_gaps(steps))

    def test_currency_is_read_only_and_requires_explicit_boolean(self):
        steps = cm.parse_steps('''## 1. 원화 표시 설정 확인
화면: CCS 여행사 기본정보
| 칸 | 값 |
|---|---|
| Stay 온라인 요금은 원화만 표시 | 체크 |
→ [확인]
'''.splitlines())
        self.assertEqual(cm.find_customer_option_gaps(steps), [])
        steps[0]['saves'] = ['저장']
        self.assertTrue(cm.find_customer_option_gaps(steps))

    def test_question_description_limit(self):
        steps = question()
        steps[0].setdefault('longtexts', {})['안내문'] = '가' * 20001
        self.assertTrue(cm.find_customer_option_gaps(steps))

    def test_duplicate_block_is_not_silently_overwritten(self):
        steps = question()
        steps[0]['longtext_labels'] = ['안내문', '안내문']
        self.assertTrue(cm.find_customer_option_gaps(steps))

    def test_create_then_edit_in_one_guide_is_rejected_before_execution(self):
        first = question()[0]
        edit = question()[0]
        edit.update(num=2, title='정보 수집 질문 고치기', saves=['질문 저장'])
        edit['heads']['버튼'] = ['`이용 시간` 행의 [편집]']
        edit['fields']['질문'] = '희망 이용 시간'
        self.assertTrue(cm.find_customer_option_gaps([first, edit]))

    def test_question_limit_is_per_form_not_all_offers(self):
        many = []
        for i in range(201):
            st = question()[0]; st['fields']['질문'] = str(i); many.append(st)
        self.assertTrue(cm.find_customer_option_gaps(many))
        many[-1]['heads']['카드'] = ['다른 오퍼 · 혜택 · 무료 픽업']
        self.assertEqual(cm.find_customer_option_gaps(many), [])

    def test_onsite_requires_currency_zero_online_and_pax_age_rates(self):
        steps = cm.parse_steps('''## 1. 부과금 추가
| 칸 | 값 |
|---|---|
| 부과 방식 | 선택: 정액 |
| 부과 단위 | 선택: 인당 |
| 정액 금액 (USD) | 선택: 지정 (0 포함) |
| 정액 금액 (USD) 값 | 0 |
| 현장 결제 통화 | 선택: USD |
| 현장 결제 단가 | 0 |
| 현장 연령별 단가 · 소아 | 비움 |
→ [추가]
'''.splitlines())
        self.assertEqual(cm.find_customer_option_gaps(steps), [])
        for label, value in [('정액 금액 (USD) 값','3'),('현장 결제 통화','비움'),('현장 결제 단가','-1')]:
            old = steps[0]['fields'][label]; steps[0]['fields'][label] = value
            self.assertTrue(cm.find_customer_option_gaps(steps), label)
            steps[0]['fields'][label] = old
        steps[0]['fields']['현장 연령별 단가 · 소아'] = '0'
        steps[0]['fields']['부과 단위'] = '선택: 박당'
        self.assertTrue(cm.find_customer_option_gaps(steps))

    def test_supplement_fields_are_available_to_validation_and_renderer(self):
        path = SKILL / 'references/screen-dictionary.json'
        self.assertIn(cm.norm_field('선택지 (한 줄에 하나)'), cm.load_dictionary(path))
        data = json.loads(path.read_text())
        page, stats = screen.render_guide(data)
        self.assertIn('2026-10-22', page)
        self.assertIn('현장 결제 단가', page)
        self.assertGreater(stats.get('supplemental_screens', 0), 0)
        self.assertEqual(stats['screens'], data['meta']['screen_count'])

    def test_regeneration_preserves_separately_dated_supplement(self):
        original = json.dumps({'meta':{'screen_count':31}, 'supplement_meta':{'date':'2026-10-22'}, 'supplemental_screens':[{'id':'release-question'}]})
        fresh = '{"meta":{"screen_count":32}}'
        merged = json.loads(sync.preserve_supplement('screen-dictionary.json', fresh, original))
        self.assertEqual(merged['meta']['screen_count'],32)
        self.assertEqual(merged['supplemental_screens'][0]['id'],'release-question')
        md = 'base\n## 2026-10-22 배포 보충\nquestion'
        self.assertEqual(sync.preserve_supplement('screen-dictionary.md','new base',md), 'new base\n## 2026-10-22 배포 보충\nquestion')


if __name__ == '__main__':
    unittest.main()
