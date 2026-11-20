// B1 페이지 모듈 하나 — 러너의 도우미·부트 위에 올리고, 작업 하나는 호출 하나, 결과는 평범한 객체, localStorage 는 stayPrice 키만.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { erpPage, inPage, plain, charsOf, OFFER, RUNNER_STEPS, RUNNER_CURSOR, HOTEL } from './page_harness.mjs';

const ALL_WEEK = ['월', '화', '수', '목', '금', '토', '일'];
const PAIR = { hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01', weekdays: ALL_WEEK };
const RESERVED = { hotel: HOTEL, offer: OFFER, rooms: ['디럭스'], ratePlans: ['조식 포함'], from: '2026-12-24', to: '2026-12-31', weekdays: ALL_WEEK, occupancy: '*', nights: 'all' };
const BULK = { no: 1, hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', dates: ['2026-07-01'], rows: [{ occupancy: '', nights: 1, sell: '125000.00' }] };
const CELL = { no: 2, hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', date: '2026-07-01', occupancy: '', nights: 1, clear: ['list'] };

test('B1 · 러너의 도우미·부트 없이 올리면 작업마다 무엇이 없는지 말하고 아무것도 누르지 않는다', async () => {
  const page = erpPage({ withScripts: false });
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, PAIR)));
  assert.equal(r.ok, false);
  assert.match(r.error, /stay_helper\.js.*stay_boot\.js.*없는 것: stayRun, calDayRanges/);
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});

test('B1 · window.stayPrice 의 작업 넷은 호출 하나로 끝나고, 결과는 JSON 그대로인 작은 객체다', async () => {
  const page = erpPage();
  const sp = page.w.stayPrice;
  assert.equal(typeof sp.version, 'string');
  for (const [name, input] of [['readPair', PAIR], ['readReserved', RESERVED], ['applyBulk', BULK], ['applyCell', CELL]]) {
    const r = await sp[name](inPage(page.w, input));
    assert.equal(r.ok, true, `${name}: ${r.error}`);
    assert.equal(r.op, name);
    assert.equal(page.w.JSON.stringify(r), JSON.stringify(plain(r)), `${name}: JSON 으로 그대로 오간다`);
    assert.ok(charsOf(plain(r)) <= 800, `${name}: 답이 JSON 으로 800자 안 (${charsOf(plain(r))})`);
    assert.ok(r.ms < 45000, `${name}: 45초 안`);
  }
  page.w.close();
});

test('B1 · localStorage 는 stayPrice 로 시작하는 키만 쓰고 러너의 staySteps·stayRunCursor 는 그대로 둔다', async () => {
  const page = erpPage();
  const before = Object.keys(page.w.localStorage);
  const r1 = plain(await page.w.stayPrice.readPair(inPage(page.w, PAIR)));
  plain(await page.w.stayPrice.readReserved(inPage(page.w, RESERVED)));
  plain(await page.w.stayPrice.applyCell(inPage(page.w, CELL)));
  const r4 = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
  assert.ok(r1.ok && r4.ok);
  const added = Object.keys(page.w.localStorage).filter((k) => !before.includes(k));
  assert.deepEqual(added, ['stayPriceLast']);
  assert.equal(page.w.localStorage.getItem('staySteps'), RUNNER_STEPS);
  assert.equal(page.w.localStorage.getItem('stayRunCursor'), RUNNER_CURSOR);
  assert.deepEqual(plain(page.w.stayPrice.last()), r4, '마지막 결과를 다시 읽을 수 있다(45초에 잘린 호출 뒤)');
  page.w.close();
});

test('B1 · 작업이 도는 동안에는 다음 작업을 받지 않고, 도는 중이라는 표시를 남긴다', async () => {
  const page = erpPage();
  const first = page.w.stayPrice.readPair(inPage(page.w, PAIR));
  assert.equal(plain(page.w.stayPrice.last()).running.op, 'readPair');
  const second = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
  assert.equal(second.ok, false);
  assert.match(second.error, /앞 작업\(readPair\)이 아직 끝나지 않았습니다/);
  // G7 — 시작하지 않은 작업은 실패가 아니다: started false · 기다릴 초 · 그 단계의 번호와 지문을 싣는다
  assert.deepEqual([second.started, second.wait, second.no, typeof second.ask], [false, 10, 1, 'string']);
  assert.equal((plain(await first)).ok, true);
  assert.deepEqual(page.log.posts, [], '두 번째 작업은 아무것도 누르지 않았다');
  const third = plain(await page.w.stayPrice.applyBulk(inPage(page.w, BULK)));
  assert.equal(third.ok, true, third.error);
  page.w.close();
});

test('B16 · 길게 늘어진 오류·막힌 클릭·줄 목록이 있어도 답은 JSON 으로 800자 안이다', async () => {
  const page = erpPage();
  const long = '아주 긴 "이름" '.repeat(60);
  const cases = [
    ['readPair', Object.assign({}, PAIR, { room: long })],
    ['readReserved', Object.assign({}, RESERVED, { rooms: [long, long + '2', long + '3'] })],
    ['applyBulk', Object.assign({}, BULK, { rows: Array.from({ length: 30 }, (_, i) => ({ occupancy: 'A' + (i + 2) + 'C1_' + long.slice(0, 20), nights: i + 1, sell: '1000', list: '2000', supply: '500' })) })],
    ['applyCell', Object.assign({}, CELL, { occupancy: long })]
  ];
  for (const [name, input] of cases) {
    const r = plain(await page.w.stayPrice[name](inPage(page.w, input)));
    assert.equal(r.ok, false, name);
    assert.ok(charsOf(r) <= 800, `${name}: ${charsOf(r)}자`);
    assert.ok(r.error, `${name}: 오류 문장은 남는다`);
  }
  page.w.close();
});
