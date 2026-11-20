// G2 작업마다 호텔에 묶인다 — readPair · readReserved · applyBulk · applyCell 은 무엇이든 누르기 전에 탭이 요청의 호텔(번호)인지
// 보고, 아니면 두 호텔을 대며 거절한다. 읽은 조각에는 페이지가 알아본 호텔이 실린다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { erpPage, inPage, plain, takeAll, OFFER, HOTEL, HERE, SKILL } from './page_harness.mjs';

const ALL_WEEK = ['월', '화', '수', '목', '금', '토', '일'];
const [BULK, CELL] = JSON.parse(readFileSync(join(HERE, 'fixtures', 'browser', 'calls.json'), 'utf8')).map((call) => call.payload);
const OPS = {
  readPair: { hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01', weekdays: ALL_WEEK },
  readReserved: { hotel: HOTEL, offer: OFFER, rooms: ['디럭스'], ratePlans: ['조식 포함'], from: '2026-12-24', to: '2026-12-31', weekdays: ALL_WEEK, occupancy: '*', nights: 'all' },
  applyBulk: BULK,
  applyCell: CELL
};

test('G2 · 다른 호텔의 탭이면 작업 넷 모두 아무것도 누르지 않고 두 호텔을 대며 거절한다(이름이 같아도 번호가 다르면 다른 호텔)', async () => {
  for (const [op, input] of Object.entries(OPS)) {
    const page = erpPage({ hotel: { id: '2', name: HOTEL.name } });
    const r = plain(await page.w.stayPrice[op](inPage(page.w, input)));
    assert.equal(r.ok, false, op);
    assert.match(r.error, /이 탭은 호텔 2 \(데모 호텔\) 입니다 — 요청은 호텔 1 \(데모 호텔\) 입니다/, `${op}: ${r.error}`);
    assert.deepEqual([page.log.reached, page.log.posts, r.clicks], [[], [], {}], `${op}: 아무것도 누르지 않았다`);
    assert.equal(r.saved, undefined, `${op}: 저장 단추와 상관없는 거절이다`);
    page.w.close();
  }
});

test('G2 · 호텔을 짚지 않은 요청이나 호텔 번호가 없는 화면에서는 작업을 시작하지 않는다', async () => {
  const page = erpPage();
  const { hotel, ...nameless } = OPS.applyBulk;
  const r = plain(await page.w.stayPrice.applyBulk(inPage(page.w, nameless)));
  assert.equal(r.ok, false);
  assert.match(r.error, /`hotel` 이 없습니다/);
  const name = plain(await page.w.stayPrice.readPair(inPage(page.w, { ...OPS.readPair, hotel: { name: HOTEL.name } })));
  assert.match(name.error, /`hotel` 이 없습니다/, '이름만으로는 호텔을 정하지 않는다');
  assert.deepEqual(page.log.reached, []);
  page.w.close();
  const bare = erpPage({ hotel: null });
  const b = plain(await bare.w.stayPrice.readPair(inPage(bare.w, OPS.readPair)));
  assert.match(b.error, /호텔 번호를 찾지 못했습니다/);
  assert.deepEqual(bare.log.reached, []);
  bare.w.close();
});

test('G2 · 읽은 조각에는 페이지가 알아본 호텔이 실리고, 파이썬은 그 호텔로 지금 값을 적는다', async () => {
  const page = erpPage({ hotel: { id: HOTEL.id, name: '페이지가 부르는 이름' } });
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, OPS.readPair)));
  assert.equal(r.ok, true, r.error);
  const { body } = takeAll(page.w, r);
  assert.deepEqual(body.hotel, { id: HOTEL.id, name: '페이지가 부르는 이름' });
  const code = `import json, sys; sys.path.insert(0, ${JSON.stringify(join(SKILL, 'scripts'))})\nimport price_browser as b\n`
    + 'print(json.dumps(b.page_hotel(json.load(sys.stdin)), ensure_ascii=False))';
  const done = spawnSync('python3', ['-I', '-c', code], { input: JSON.stringify([r, ...takeAll(page.w, r).takes]), encoding: 'utf8' });
  assert.equal(done.status, 0, done.stderr);
  assert.deepEqual(JSON.parse(done.stdout), { id: HOTEL.id, name: '페이지가 부르는 이름' });
  page.w.close();
});
