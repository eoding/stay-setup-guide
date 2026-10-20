#!/usr/bin/env python3
"""Find field help and customer effects from the supplied screen guide, without ERP writes."""
import argparse
import json
from pathlib import Path
import re

MAP = Path(__file__).resolve().parents[1] / 'references' / 'screen-effects.json'


def norm(value):
    return re.sub(r'\s+', '', value or '').replace('`', '').casefold()


def search(data, query, screen=''):
    matches = []
    for item in data['screens'] + data.get('supplemental_screens', []):
        if screen and not any(norm(screen) in norm(item[key]) for key in ('id', 'name')):
            continue
        for field in item['fields']:
            # 바뀌기 전 글자(`aliases`)로 물어도 같은 칸을 찾는다 — ERP CO-32105 처럼 화면 글자가 바뀐 칸
            if query and not any(norm(query) in norm(t) for t in [field['label'], *field.get('aliases', [])]):
                continue
            matches.append({'screen':item['name'], 'screen_id':item['id'],
                            'summary':item['summary'], **field})
    return matches


def main(argv=None):
    ap = argparse.ArgumentParser(description='Stay 칸 도움말 · 고객 화면 영향 찾기 (읽기 전용)')
    ap.add_argument('field', nargs='?', default='', help='칸 이름. --screen만 주면 그 화면의 모든 칸')
    ap.add_argument('--screen', default='', help='화면 이름 또는 화면 사전 ID')
    ap.add_argument('--json', action='store_true', help='기계용 JSON 출력')
    args = ap.parse_args(argv)
    if not args.field and not args.screen:
        ap.error('칸 이름이나 --screen을 주세요')
    data = json.loads(MAP.read_text(encoding='utf-8'))
    rows = search(data, args.field, args.screen)
    if args.json:
        print(json.dumps({'baseline':data['meta'], 'matches':rows}, ensure_ascii=False, indent=2))
    else:
        print('기준: ' + data['meta']['verification'])
        if not rows:
            print('해당 칸을 찾지 못했습니다. 실제 화면의 칸 이름을 확인하세요.')
        for row in rows:
            print(f"\n{row['screen']} / {row['label']}")
            if row.get('help'):
                print('도움말: ' + row['help'])
            print('영향: ' + row['effect'])
            if not row.get('web'):
                print('고객 화면의 표시 자리: 직접 표시 없음 (' + row.get('downstream','') + ')')
            for place in row.get('web', []):
                print('표시: ' + ' › '.join(place.get(k,'') for k in ('page','section','element')))
    return 0 if rows else 1


if __name__ == '__main__':
    raise SystemExit(main())
