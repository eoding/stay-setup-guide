// M7 페이지 답의 본보기 — `fixtures/browser/` 의 답 파일은 지금의 stay_promotion.js 가 같은 입력에 내는 답과 같다. 페이지를 고쳐 답이
// 바뀌면 여기서 실패하고, 다시 적는 명령을 말한다(파이썬 쪽 시험이 낡은 답으로 돌지 않게). 시각에 따라 바뀌는 칸 — 답의 `ms` ·
// `doneAt` · `body.id`, 쪽의 `id` — 은 page_goldens.mjs 의 NORMALIZED 값으로 맞춘 뒤 견준다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { goldens, GOLDEN } from './page_goldens.mjs';
import { charsOf } from './promotion_harness.mjs';

const AGAIN = 'NODE_PATH=<jsdom 이 있는 node_modules> node tests/page_goldens.mjs --write';

test('M7 · 본보기 답 파일은 지금 페이지가 같은 입력에 내는 답과 같다', async () => {
  const files = await goldens();
  assert.deepEqual(readdirSync(GOLDEN).filter((name) => name.endsWith('.json')).sort(), Object.keys(files).sort());
  for (const [name, data] of Object.entries(files)) {
    const committed = JSON.parse(readFileSync(join(GOLDEN, name), 'utf8'));
    assert.deepEqual(committed, JSON.parse(JSON.stringify(data)), `${name} 이 지금 페이지의 답과 다릅니다 — 스킬 폴더에서 \`${AGAIN}\` 로 다시 적고 같이 커밋합니다`);
  }
});

test('M7 · 본보기의 답과 쪽은 800자 안이고, 저장 답은 saved true 이며, 저장 요청은 읽은 form 에서 첫 단의 값만 바꾼 것이다', () => {
  const read = (name) => JSON.parse(readFileSync(join(GOLDEN, name), 'utf8'));
  for (const name of ['look.json', 'readPromotion.json', 'applyPromotion.json']) for (const item of read(name)) assert.ok(charsOf(item) <= 800, name);
  const [apply] = read('applyPromotion.json');
  assert.deepEqual([apply.op, apply.saved, apply.pressed], ['applyPromotion', true, true]);
  const inputs = read('inputs.json');
  const { form, set, marks } = inputs.applyPromotion;
  assert.deepEqual(set, [['tiers_value', 0, '16']]);
  assert.deepEqual(marks, [['cancellation'], ['cancellation']]);
  assert.deepEqual(form.filter(([name]) => name === 'tiers_origin').map(([, v]) => v), ['46', '31']);
  let seen = -1;
  assert.deepEqual(inputs.posted, [form.map(([name, value]) => [name, name === 'tiers_value' && ++seen === 0 ? '16' : value])]);
});
