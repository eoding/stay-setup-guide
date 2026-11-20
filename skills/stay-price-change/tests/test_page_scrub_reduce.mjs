// B3 주소 거르기 · B4 줄인 조각의 약속 — 파이썬 읽기가 원래 조각과 줄인 조각에서 같은 결과를 내는지까지 본다.
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node --test tests/test_page_*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { erpPage, inPage, plain, loadJsdom, JSDOM_MISSING, OWN_FIXTURES, HERE } from './page_harness.mjs';

const CSRF = 'q8Zr3VbN0aWkT5yLmP2xC7dJ9eFh4gUs6iO1nRtYvBwXzAcQ'; // 지어낸 64자 꼴 토큰
const FIXTURES = [
  ['price', 'calendar-bulk--price-step2.html'],
  ['price', 'calendar-bulk--price-link-step2.html'],
  ['price', 'price-runs-closed-absent-list.html'],
  ['adjust', 'calendar-adjust--step2.html'],
  ['adjust', 'adjust-rejected.html']
];

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
    '<section data-stay-summary>\n    <table data-stay-rows="prices" data-calendar-link-base><thead><tr><th colspan="4">머리</th></tr></thead>\n    '
    + '<tbody data-stay-occupancy-key="A2" data-stay-los-nights="1"><tr data-stay-existing><td rowspan="2">1 &lt; 2 &amp; "3"</td></tr></tbody></table>\n    '
    + '\n    <a data-stay-action="goto">링크 글자</a><br></section>');
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
