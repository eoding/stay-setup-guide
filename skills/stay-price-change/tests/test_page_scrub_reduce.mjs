// B3 주소 거르기 · B4 줄인 조각의 약속 — 파이썬 읽기가 원래 조각과 줄인 조각에서 같은 결과를 내는지까지 본다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { erpPage, inPage, plain, takeAll, charsOf, runFixture, loadJsdom, JSDOM_MISSING, OWN_FIXTURES, HERE, OFFER, HOTEL } from './page_harness.mjs';
import { crc32 } from 'node:zlib';

const CSRF = 'q8Zr3VbN0aWkT5yLmP2xC7dJ9eFh4gUs6iO1nRtYvBwXzAcQ'; // 지어낸 64자 꼴 토큰
const FIXTURES = [
  ['price', 'calendar-bulk--price-step2.html'],
  ['price', 'calendar-bulk--price-link-step2.html'],
  ['price', 'price-runs-closed-absent-list.html'],
  ['adjust', 'calendar-adjust--step2.html'],
  ['adjust', 'adjust-rejected.html']
];

// FNV-1a 32비트 — 파이썬 `change_core.answers.fnv1a` 와 같은 셈(시험이 따로 셈한다)
function fnv1a(bytes) {
  let h = 0x811c9dc5;
  for (const b of bytes) h = Math.imul(h ^ b, 0x01000193) >>> 0;
  return h.toString(16).padStart(8, '0');
}

function readPages(pairs) {
  const done = spawnSync('python3', ['-I', join(HERE, 'reduced_reader.py'), ...pairs.flat()], { encoding: 'utf8' });
  assert.equal(done.status, 0, done.stderr);
  return JSON.parse(done.stdout);
}

test('B8 · jsdom 이 없으면 NODE_PATH 를 말하며 실패한다(건너뛰지 않는다)', () => {
  assert.throws(() => loadJsdom(() => { throw new Error('Cannot find module'); }), (e) => e.message === JSDOM_MISSING && /NODE_PATH/.test(e.message) && /건너뛰지 않고/.test(e.message));
});

test('B3 · 주소 같은 키와 주소·쿼리 붙은 경로·토큰 같은 글자는 나가지 않는다', () => {
  const { w } = erpPage();
  const out = plain(w.stayPrice.scrub(inPage(w, {
    url: 'https://erp.example.test/stay/1/', href: 'x', hash: '#stay_tab_calendar', path: '/stay/1/', hxGet: 'y', csrf: 'z', requestUrl: 'u',
    note: '저장했습니다 · 디럭스 · 조식 포함 · 2026-07-01 ~ 2026-07-31 (31일)',
    amount: '1,234.50', ratio: '2/3', key: 'A2C1_CHD', blank: '',
    full: 'https://erp.example.test/stay/1/?month=2026-07', relative: '//erp.example.test/x', query: '/stay/1/calendar/bulk/?operation=price&month=2026-07',
    bare: '/stay/1/calendar/', token: CSRF, jwt: 'eyJhbGciOi.eyJzdWIiOi.c2ln', www: 'www.example.test/a',
    inside: '[다음] 을 눌렀더니 /stay/1/calendar/?month=2026-07 로 갔습니다',
    list: ['https://a.example.test/', '디럭스', { location: 'x', ok: true }], nested: { deep: { url: 'x', n: 3, bad: 'Infinity' } }
  })));
  assert.deepEqual(Object.keys(out).sort(), ['amount', 'blank', 'inside', 'key', 'list', 'nested', 'note', 'ratio']);
  assert.equal(out.note, '저장했습니다 · 디럭스 · 조식 포함 · 2026-07-01 ~ 2026-07-31 (31일)');
  assert.equal(out.amount, '1,234.50');
  assert.equal(out.ratio, '2/3');
  assert.equal(out.key, 'A2C1_CHD');
  assert.equal(out.inside, '[다음] 을 눌렀더니 [주소 지움] 로 갔습니다');
  assert.deepEqual(out.list, ['디럭스', { ok: true }]);
  assert.deepEqual(out.nested, { deep: { n: 3, bad: 'Infinity' } });
  assert.equal(w.stayPrice.scrub(w.eval('({ n: Infinity })')).n, null, '끝없는 수는 null 로');
  assert.equal(w.stayPrice.scrub(w.document.body), undefined, '화면 마디는 나가지 않는다');
  assert.deepEqual(plain(w.stayPrice.scrub(inPage(w, [w.location.href, 'ok']))), ['ok'], '페이지 주소는 나가지 않는다');
  w.close();
});

test('B4 · 줄인 조각에는 태그·글자·data-stay-*·data-calendar-*·colspan/rowspan 만 남는다', () => {
  const { w, doc } = erpPage();
  const box = doc.createElement('div');
  box.innerHTML = `<section class="stay-card" data-stay-summary id="s1" style="color:red" title="t" onclick="x()">
    <table class="t" data-stay-rows="prices" data-calendar-link-base hx-get="/stay/1/calendar/?a=1"><thead><tr><th colspan="4" scope="rowgroup">머리</th></tr></thead>
    <tbody data-stay-occupancy-key="A2" data-stay-los-nights="1" data-stay-href="/stay/1/x/?y=1" data-stay-token="${CSRF}"><tr data-stay-existing><td rowspan="2" class="n">1 &lt; 2 &amp; "3"</td></tr></tbody></table>
    <input type="hidden" name="csrfmiddlewaretoken" value="${CSRF}"><button data-stay-action="save">입력한 가격 적용</button><select name="s"><option>보이는 옵션</option></select>
    <textarea name="t">글</textarea><script>var leak = 1;</script><style>.x{}</style><template><b>틀</b></template><a href="/stay/1/?q=1" data-stay-action="goto">링크 글자</a><!-- 주석 --><br></section>`;
  assert.equal(w.stayPrice.reduce(box.firstElementChild),
    '<section data-stay-summary> <table data-stay-rows="prices" data-calendar-link-base><thead><tr><th colspan="4">머리</th></tr></thead>'
    + '<tbody data-stay-occupancy-key="A2" data-stay-los-nights="1"><tr data-stay-existing><td rowspan="2">1 &lt; 2 &amp; "3"</td></tr></tbody></table>'
    + ' <a data-stay-action="goto">링크 글자</a><br></section>', '표 뼈대 사이 빈칸은 지우고 다른 빈칸 줄은 한 칸으로');
  w.close();
});

test('B4 · 가격 수정·가감 조각 다섯 장 모두 줄여도 파이썬 읽기 결과가 같고, 숨은 칸 값·CSRF·주소는 남지 않는다', () => {
  const dir = mkdtempSync(join(tmpdir(), 'stay-price-reduce-'));
  try {
    const pairs = [], checks = [];
    for (const [kind, name] of FIXTURES) {
      const { w, doc } = erpPage();
      doc.body.innerHTML = readFileSync(join(OWN_FIXTURES, name), 'utf8');
      const root = doc.querySelector('[data-stay-screen]');
      root.insertAdjacentHTML('afterbegin', `<input type="hidden" name="csrfmiddlewaretoken" value="${CSRF}">`);
      const hidden = [...root.querySelectorAll('input[type="hidden"]')].map((i) => i.value);
      const clone = root.cloneNode(true);
      clone.querySelectorAll('input,select,textarea,button,script,style,template').forEach((el) => el.remove());
      const visible = clone.textContent;
      const reduced = w.stayPrice.reduce(root);
      assert.equal(w.stayPrice.scrub(reduced), reduced, `${name}: 줄인 조각은 거르기를 지나도 그대로다`);
      const file = join(dir, `reduced--${name}`);
      writeFileSync(file, reduced);
      pairs.push([kind, join(OWN_FIXTURES, name)], [kind, file]);
      checks.push({ name, reduced, hidden: hidden.filter((v) => v.length >= 4 && !visible.includes(v)) });
      w.close();
    }
    const pages = readPages(pairs);
    const { w, doc } = erpPage();
    for (let i = 0; i < checks.length; i++) {
      const [original, reduced] = [pages[2 * i], pages[2 * i + 1]];
      const { name, reduced: text, hidden } = checks[i];
      assert.ok(original.page, `${name}: 원래 조각을 읽는다 (${original.error})`);
      assert.deepEqual(reduced, { file: `reduced--${name}`, page: original.page }, `${name}: 줄인 조각도 같은 결과`);
      assert.ok(hidden.includes(CSRF), `${name}: 넣어 둔 CSRF 를 숨은 칸 목록이 잡았다`);
      const back = doc.createElement('div');
      back.innerHTML = text;
      const attrValues = [...back.querySelectorAll('*')].flatMap((el) => [...el.attributes].map((a) => a.value));
      for (const value of hidden) assert.ok(!back.textContent.includes(value) && !attrValues.includes(value), `${name}: 숨은 칸 값이 남았다 — ${value}`);
      for (const bad of ['<input', '<button', '<select', '<script', '<style', 'value=', 'href', 'hx-', '/stay/', '?operation', 'id=', 'class=']) {
        assert.ok(!text.includes(bad), `${name}: 줄인 조각에 ${bad} 가 남았다`);
      }
    }
    w.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('B9 · 줄인 조각에는 들여쓰기가 남지 않는다(파이썬 읽기는 위 다섯 장 시험에서 같은 결과)', () => {
  for (const [, name] of FIXTURES) {
    const { w, doc } = erpPage();
    doc.body.innerHTML = readFileSync(join(OWN_FIXTURES, name), 'utf8');
    const reduced = w.stayPrice.reduce(doc.querySelector('[data-stay-screen]'));
    assert.ok(!/\n/.test(reduced) && !/ {2,}/.test(reduced) && !/> </.test(reduced.replace(/<\/?(section|div|dl|h4|p|span|strong)[^>]*>/g, '')), `${name}: 줄바꿈·겹친 빈칸이 없다`);
    w.close();
  }
});

test('B9 · B16 · 큰 조각은 페이지에 남고 JSON 으로 800자 안의 쪽으로 나뉘며(따옴표 이스케이프 포함), 쪽마다 제 검사값(sum)이 있고, 이으면 바이트 수·CRC-32 가 답과 맞는다', async () => {
  const long = '아주 긴 "객실" 이름 칸 '.repeat(400);
  const page = erpPage({ bulkReview: runFixture('calendar-bulk--price-step2.html').replace('인원 무관 단일가 · 1박 이상', long) });
  const ALL_WEEK = ['월', '화', '수', '목', '금', '토', '일'];
  const r = plain(await page.w.stayPrice.readPair(inPage(page.w, { hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함', from: '2026-07-01', to: '2026-07-01', weekdays: ALL_WEEK })));
  assert.equal(r.ok, true, r.error);
  assert.ok(charsOf(r) <= 800, `읽기 답: ${charsOf(r)}자`);
  assert.equal(r.fragment, undefined, '답에는 조각을 싣지 않는다');
  const { takes, text, body } = takeAll(page.w, r);
  assert.deepEqual(Object.keys(r.body).sort(), ['bytes', 'chars', 'crc32', 'fnv', 'id'], '머리에는 쪽 수가 없다(take 는 글자 자리를 받는다) — 알아볼 값만');
  assert.ok(takes.length >= 15, `쪽 ${takes.length}개`);
  for (const t of takes) assert.ok(charsOf(t) <= 800 && t.end === r.body.chars, `쪽 ${t.at}: ${charsOf(t)}자`);
  for (const t of takes) {
    assert.equal(t.sum, crc32(Buffer.from(`${t.id}:${t.at}:${t.end}:${t.text}`, 'utf8')).toString(16).padStart(8, '0'), `쪽 ${t.at}: 쪽 하나의 검사값은 id:at:end:글자의 CRC-32`);
    assert.equal(t.bytes, undefined, '쪽에는 전체의 바이트 수 · CRC-32 가 없다(머리에 있다)');
  }
  assert.ok(takes.some((t) => t.text.includes('"')), '따옴표가 든 쪽이 있다(도구는 \\" 로 보인다)');
  assert.equal(text.length, r.body.chars);
  assert.equal(Buffer.byteLength(text), r.body.bytes);
  assert.equal(crc32(Buffer.from(text, 'utf8')).toString(16).padStart(8, '0'), r.body.crc32);
  assert.deepEqual(['foobar', '디럭스 · 조식 포함'].map((x) => fnv1a(Buffer.from(x, 'utf8'))), ['bf9cf968', '7da60b99'], '시험의 셈은 표준 FNV-1a(파이썬 시험과 같은 값)');
  assert.equal(fnv1a(Buffer.from(text, 'utf8')), r.body.fnv, '두 번째 알아볼 값 FNV-1a(32비트)도 이은 글자와 맞는다');
  assert.ok(body.fragment.includes(long.trim()), '이은 조각에 긴 글자가 그대로 있다');
  const small = takeAll(page.w, r, 300);
  assert.ok(small.takes.every((t) => charsOf(t) <= 300 && t.size === 300), '부르는 쪽이 더 작은 크기를 고를 수 있다');
  assert.equal(small.text, text, '어떤 크기로 받아도 이으면 같은 글자');
  assert.match(plain(page.w.stayPrice.take(r.body.id, 0, 100)).error, /크기\(size\)는 200 부터 800 까지/);
  assert.match(plain(page.w.stayPrice.take(r.body.id, 0, 900)).error, /크기\(size\)는 200 부터 800 까지/);
  assert.match(plain(page.w.stayPrice.take(r.body.id, r.body.chars)).error, /자리\(at\)는/);
  assert.match(plain(page.w.stayPrice.take('없는-id', 0)).error, /페이지에 없습니다/);
  const huge = plain(page.w.stayPrice.take('가'.repeat(2000), 0));
  assert.ok(charsOf(huge) <= 800 && huge.cut === true && /페이지에 없습니다/.test(huge.error), '어떤 값이 길게 들어와도 답은 줄여서 800자 안');
  page.w.close();
});

test('W2 · 페이지는 명령이 읽기 한 번에 허락하는 작업 수(PAGE_KEEPS)만큼 조각을 두어, 그만큼 부른 뒤에도 첫 조각을 받는다', async () => {
  const keeps = Number(/^PAGE_KEEPS = (\d+)$/m.exec(readFileSync(join(HERE, '..', 'scripts', 'price_browser.py'), 'utf8'))[1]);
  const page = erpPage();
  const read = async () => plain(await page.w.stayPrice.readPair(inPage(page.w, { hotel: HOTEL, offer: OFFER, room: '디럭스', ratePlan: '조식 포함',
    from: '2026-07-01', to: '2026-07-01', weekdays: ['월', '화', '수', '목', '금', '토', '일'] })));
  // 그 사이의 작업은 지어낸 조각으로 대신한다 — 작업 하나가 1초쯤이라 수백 번을 다 부르지 않는다. 앞뒤의 작업은 진짜다
  const between = (n) => {
    const store = page.w.__stayPriceBodies;
    for (let i = 0; i < n; i++) { const id = `between-${store.order.length}`; store.items[id] = { text: '{}', bytes: 2, crc32: '00000000' }; store.order.push(id); }
  };
  const first = await read();
  between(keeps - 2);
  const last = await read();
  assert.equal(plain(page.w.stayPrice.take(first.body.id, 0)).ok, true, `작업 ${keeps}번을 부른 뒤에도 첫 조각을 받는다`);
  between(1);
  await read();
  assert.match(plain(page.w.stayPrice.take(first.body.id, 0)).error, /페이지에 없습니다/, '하나 더 넘치면 가장 앞 조각부터 밀려난다');
  assert.equal(plain(page.w.stayPrice.take(last.body.id, 0)).ok, true);
  page.w.close();
});
