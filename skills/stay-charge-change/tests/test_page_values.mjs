// A2 값은 그대로 돌아온다 — 36자 한 줄의 이름 · 설명에 주소가 든 부과금도 읽은 창의 칸이 명령에 그대로 돌아가고, 미리보기를 거쳐
// 이름을 견준 뒤 그 칸 그대로 저장된다(전에는 거르기가 이름을 고쳐 「창의 부과금 이름이 고른 부과금이 아닙니다」 로 늘 거절됐다).
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'node:path';
import { chargePage, DB, HOTEL, SKILL } from './charge_harness.mjs';
import { windowFlow } from '../../stay-addon-price-change/tests/window_flow.mjs';

const KIND = { script: join(SKILL, 'scripts', 'charge_change.py'), page: 'stayCharge', read: 'readCharge', calls: 'charges', prefix: 'charge' };
const LONG = 'Early-check-in-before-noon-surcharge';
const LINKED = '안내: https://hotel.example/charges?id=1 · www.example.test';

test('A2 · 36자 이름 · 설명에 주소가 든 부과금 — 읽고, 미리보기를 만들고, 읽은 칸 그대로 저장한다', async () => {
  const db = JSON.parse(JSON.stringify(DB));
  Object.assign(db.offers[0].charges.find((c) => c.id === '703'), { name: LONG, description: LINKED });
  const page = chargePage({ db });
  const flow = windowFlow(page, KIND);
  try {
    const request = { kind: 'charge_change', hotel: HOTEL, amounts: [{ offer: '601', charge: '703', field: 'amount' }], value: '100', sentence: '시험' };
    const { short, steps } = await flow.change(request);
    assert.equal(short.saves, 1, JSON.stringify(short));
    assert.deepEqual(steps.map((s) => [s.answer.saved, s.recorded.saved]), [[true, true]], JSON.stringify(steps.map((s) => s.answer.error)));
    assert.equal(steps[0].call.payload.name, LONG, '명령이 낸 이름이 읽은 그대로');
    const sent = Object.fromEntries(page.log.posts[0].pairs);
    assert.deepEqual([sent.name, sent.description, sent.amount], [LONG, LINKED, '100.00']);
  } finally {
    flow.close();
    page.w.close();
  }
});
