// A2 값은 그대로 돌아온다 — 설명에 주소가 든 줄, 36자 한 줄 · 점으로 이은 이름의 줄도 읽은 창의 칸이 명령에 그대로 돌아가고,
// 미리보기를 거쳐 그 칸 그대로 저장된다(전에는 거르기가 칸을 고쳐 「창의 값이 읽은 값과 다릅니다」 로 늘 거절됐다).
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'node:path';
import { addonPage, DB, HOTEL, SKILL } from './addon_harness.mjs';
import { windowFlow } from './window_flow.mjs';

const KIND = { script: join(SKILL, 'scripts', 'addon_change.py'), page: 'stayAddonPrice', read: 'readLine', calls: 'lines', prefix: 'line' };
const LINKED = '메뉴 안내: https://hotel.example/menu · see /menu/spa.pdf for details';
const LONG = 'Early-check-in-before-noon-surcharge';

test('A2 · 설명에 주소가 든 줄 · 36자 이름 · 점으로 이은 이름의 줄 — 읽고, 미리보기를 만들고, 읽은 칸 그대로 저장한다', async () => {
  const db = JSON.parse(JSON.stringify(DB));
  Object.assign(db.addons[0].lines[0], { name: LONG, description: LINKED });
  Object.assign(db.addons.find((a) => a.lines.some((l) => l.id === '304')).lines.find((l) => l.id === '304'), { name: 'v1.2.3' });
  const page = addonPage({ db });
  const flow = windowFlow(page, KIND);
  try {
    const request = { kind: 'addon_change', hotel: HOTEL, lines: [{ addon: '201', line: '301' }, { addon: '203', line: '304' }], field: 'sell', percent: '10', sentence: '시험' };
    const { short, steps } = await flow.change(request);
    assert.equal(short.saves, 2, JSON.stringify(short));
    assert.deepEqual(steps.map((s) => [s.answer.saved, s.recorded.saved]), [[true, true], [true, true]], JSON.stringify(steps.map((s) => s.answer.error)));
    const sent = page.log.posts.map((post) => Object.fromEntries(post.pairs));
    assert.deepEqual([sent[0].name, sent[0].description, sent[0].price], [LONG, LINKED, '22.00'], '이름 · 설명은 읽은 그대로, 판매가만 바뀌어 나갔다');
    assert.deepEqual([sent[1].name, sent[1].price], ['v1.2.3', '33.00']);
  } finally {
    flow.close();
    page.w.close();
  }
});
