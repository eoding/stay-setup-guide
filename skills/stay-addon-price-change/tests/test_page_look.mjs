// A1 보기 — stayAddonPrice.look() 하나로 로그인 화면인지, 어느 호텔인지, 부가옵션과 가격 줄 전부(목록 그대로의 글자)를 안다.
// 누르는 것은 목록이 안 보일 때의 [부가옵션] 탭 하나뿐이다. 목록은 늘 페이지에 두고(body) take 로 받는다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { addonPage, plain, charsOf, takeAll, HOTEL, DB, LISTED } from './addon_harness.mjs';


test('A1 · 부가옵션 탭이면 아무것도 누르지 않고, 부가옵션 넷과 가격 줄 다섯을 목록의 글자 그대로 조각으로 돌려준다', async () => {
  const page = addonPage();
  const r = plain(await page.w.stayAddonPrice.look());
  assert.equal(r.ok, true, r.error);
  assert.deepEqual([r.op, r.login, r.hotel, r.count], ['look', false, HOTEL, { addons: 4, lines: 5 }]);
  assert.deepEqual(r.clicks, {});
  assert.deepEqual(page.log.reached, [], '목록이 보이면 누르지 않는다');
  assert.ok(charsOf(r) <= 800, String(charsOf(r)));
  const { takes, body } = takeAll(page.w, r);
  assert.ok(takes.length >= 2, '목록은 800자를 넘어 조각 여럿으로 온다');
  for (const piece of takes) assert.ok(charsOf(piece) <= 800, `쪽 하나도 800자 안: ${charsOf(piece)}`);
  assert.deepEqual(body.hotel, HOTEL);
  assert.deepEqual(body.addons, LISTED);
  page.w.close();
});

test('A1 · 다른 탭에서 부르면 [부가옵션] 탭 하나만 누르고, 목록이 아직 스텁이어도 목록이 온 뒤에 읽는다', async () => {
  const page = addonPage({ tab: 'calendar', addons: 'stub' });
  const r = plain(await page.w.stayAddonPrice.look());
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.clicks, { tab: 1 });
  assert.deepEqual(page.log.reached, ['stay-tab=addons']);
  assert.deepEqual(takeAll(page.w, r).body.addons, LISTED);
  page.w.close();
});

test('A1 · 부가옵션 탭이 이미 켜졌는데 목록이 아직 스텁이면 탭을 누르지 않고 목록이 올 때까지 기다린다', async () => {
  const page = addonPage({ addons: 'stub', stubMs: 300 });
  const r = plain(await page.w.stayAddonPrice.look());
  assert.equal(r.ok, true, r.error);
  assert.deepEqual([r.clicks, page.log.reached], [{}, []]);
  assert.deepEqual(takeAll(page.w, r).body.addons, LISTED);
  page.w.close();
});

test('A1 · 로그인 화면이면 그렇게만 말하고 아무것도 누르지 않는다(러너가 없어도)', async () => {
  const page = addonPage({ login: true, withScripts: false });
  const r = plain(await page.w.stayAddonPrice.look());
  assert.deepEqual([r.ok, r.login, r.hotel, r.body], [true, true, undefined, undefined]);
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});

test('A1 · 호텔 번호가 없는 화면이면 거절한다', async () => {
  const page = addonPage({ hotel: null });
  const r = plain(await page.w.stayAddonPrice.look());
  assert.equal(r.ok, false);
  assert.match(r.error, /호텔 번호를 찾지 못했습니다/);
  assert.deepEqual(page.log.reached, []);
  page.w.close();
});

test('A1 · 가격 표의 머리가 그 일곱 칸이 아니면(ERP 가 칸을 바꿨으면) 다른 칸을 값으로 읽지 않고 멈춘다', async () => {
  const page = addonPage();
  const th = [...page.doc.querySelectorAll('[data-stay-entity-id="201"] thead th')].find((el) => el.textContent.trim() === '판매가');
  th.textContent = '정가';
  const r = plain(await page.w.stayAddonPrice.look());
  assert.equal(r.ok, false);
  assert.match(r.error, /가격 표의 머리가 「가격행 이름 \/ 판매가 \/ 통화별 금액 \/ 적용 대상 \/ 적용 범위 \/ 인원 밴드 \/ 액션」 가 아닙니다/);
  assert.equal(r.body, undefined);
  page.w.close();
});

test('A1 · 부가옵션이 많아도 답과 쪽은 800자 안이고(쪽 크기 200 도), 이은 목록에 줄이 모두 있다', async () => {
  const db = JSON.parse(JSON.stringify(DB));
  const base = db.addons[0];
  for (let i = 0; i < 20; i++) {
    db.addons.push(Object.assign({}, base, { id: String(400 + i), name: `늘린 부가옵션 ${i + 1}`,
      lines: base.lines.map((line, j) => Object.assign({}, line, { id: String(500 + i * 2 + j), name: `${line.name} ${i + 1}` })) }));
  }
  const page = addonPage({ db });
  const r = plain(await page.w.stayAddonPrice.look());
  assert.equal(r.ok, true, r.error);
  assert.deepEqual(r.count, { addons: 24, lines: 45 });
  for (const size of [undefined, 200]) {
    const { takes, body } = takeAll(page.w, r, size);
    for (const piece of takes) assert.ok(charsOf(piece) <= 800, `${size}: ${charsOf(piece)}`);
    assert.equal(body.addons.flatMap((a) => a.lines).length, 45, String(size));
    assert.deepEqual(body.addons.at(-1).lines.map((l) => l.id), ['538', '539']);
  }
  page.w.close();
});
