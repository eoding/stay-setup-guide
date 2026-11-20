// T4 — 브라우저 도구는 답이 객체일 때 점으로 이은 조각(글자·숫자·_·-) 셋 이상뿐인 글자를 토큰으로 보고 통째로 가린다
// (`"0.15.0"` → `"[BLOCKED: JWT token]"`). 페이지와 올리개의 어떤 답에도 그런 글자가 없다 — 작업마다 모든 답을 훑는다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { erpPage, inPage, plain, takeAll, HELPER, BOOT, PAGE, LOADER, OFFER } from './page_harness.mjs';

const DOTTED = /^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2,}$/;
const ALL_WEEK = ['월', '화', '수', '목', '금', '토', '일'];
// 호텔 이름도 그 모양이다 — look 의 hotel.name, 조각 안의 hotel 이 그 글자를 실어 나른다
const HOTEL = Object.freeze({ id: '1', name: 'demo.hotel.one' });

function blocked(value, at = '$', out = []) {
  if (typeof value === 'string') { if (DOTTED.test(value)) out.push(`${at} = ${value}`); }
  else if (Array.isArray(value)) value.forEach((item, i) => blocked(item, `${at}[${i}]`, out));
  else if (value && typeof value === 'object') Object.entries(value).forEach(([k, v]) => blocked(v, `${at}.${k}`, out));
  return out;
}
function upload(page, files) {
  const input = page.doc.getElementById('stay_price_bridge');
  Object.defineProperty(input, 'files', { configurable: true, value: files.map(([name, text]) => new page.w.File([text], name, { type: 'text/javascript' })) });
  input.dispatchEvent(new page.w.Event('change', { bubbles: true }));
}

test('T4 · 올리개의 답(칸 세우기 · load · status · again)에는 도구가 가리는 모양의 글자가 없다 — 판 번호 0.15.0 도', async () => {
  const page = erpPage({ bare: true, hotel: HOTEL });
  const answers = [plain(page.w.eval(LOADER))];
  upload(page, [['stay_helper.js', HELPER], ['stay_boot.js', BOOT]]);
  answers.push(plain(await page.w.stayPriceLoader.load()));                 // 가격 도우미가 아직 없을 때의 답
  upload(page, [['stay_price.js', PAGE]]);
  const loaded = plain(await page.w.stayPriceLoader.load());
  answers.push(loaded, plain(page.w.stayPriceLoader.status()), plain(page.w.stayPriceLoader.again()));
  assert.equal(loaded.ok, true, loaded.error);
  assert.ok(DOTTED.test(page.w.stayRun.version), `러너 판 번호가 그 모양이어야 이 시험이 뜻이 있다: ${page.w.stayRun.version}`);
  assert.equal(loaded.helper, page.w.stayRun.version.split('.').join('·'));
  assert.deepEqual(blocked(answers), []);
  page.w.close();
});

test('T4 · 페이지의 모든 작업 답과 쪽에는 도구가 가리는 모양의 글자가 없다', async () => {
  const page = erpPage({ hotel: HOTEL });
  const sp = page.w.stayPrice;
  const call = async (op, value) => plain(await sp[op](inPage(page.w, value)));
  const answers = [];
  const look = await call('look', {});
  answers.push(look, await call('look', { offer: OFFER }));
  assert.equal(look.hotel.name, 'demo·hotel·one', '이름은 점을 · 로 바꿔 읽을 수 있게 남는다');
  const pair = await call('readPair', { hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01', weekdays: ALL_WEEK });
  const resv = await call('readReserved', { hotel: HOTEL, offer: OFFER, rooms: ['디럭스'], ratePlans: ['조식 포함'], from: '2026-07-01', to: '2026-07-01', weekdays: ALL_WEEK, occupancy: '*', nights: 'all' });
  assert.equal(pair.ok, true, pair.error);
  assert.equal(resv.ok, true, resv.error);
  answers.push(pair, resv, ...takeAll(page.w, pair).takes, ...takeAll(page.w, resv).takes);
  assert.equal(takeAll(page.w, pair).body.hotel.name, 'demo·hotel·one', '조각 안의 이름도 같은 규칙');
  answers.push(await call('applyBulk', { no: 1, hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', dates: ['2026-07-01'], rows: [{ occupancy: '', nights: 1, sell: '125000.00', list: null, supply: null }] }));
  answers.push(await call('applyCell', { no: 2, hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', date: '2026-07-01', occupancy: '', nights: 1, clear: ['list'] }));
  answers.push(await call('readPair', { hotel: { id: '2', name: 'other.hotel.two' }, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01', weekdays: ALL_WEEK }));
  answers.push(plain(sp.take(pair.body.id, 0)), plain(sp.take('없는.조각.id', 0)), plain(sp.last()), plain(sp.idle()), plain(sp.config()),
    plain(sp.standDown()), plain(sp.standUp()));
  assert.deepEqual(blocked(answers), []);
  page.w.close();
});
