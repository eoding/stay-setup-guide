/* stay_price_loader.js — 가격 변경 도우미를 로그인된 ERP 탭에 올리는 작은 실행 묶음 (stay-price-change).
 *
 * 쓰는 법(브라우저 도구 셋):
 *   1. JS 실행 도구로 이 파일 전체를 실행한다 → 파일 칸 `input#stay_price_bridge`(접근성 이름 `stay price file bridge`)가 생기고
 *      `window.stayPriceLoader` 가 선다. 칸은 1px · 거의 투명이라 보이지 않지만 접근성 트리에는 남아 도구가 이름으로 찾는다.
 *   2. 업로드 도구로 **그 이름의** 칸에 세 파일을 올린다(ERP 의 사진 올리기 칸과 헷갈리지 않게 — 한 번에 셋이든 하나씩이든):
 *      러너의 `stay_helper.js`·`stay_boot.js`, 그리고
 *      `stay_price.js`(`.min.js` 도 받는다).
 *   3. `await stayPriceLoader.load()` → 이름으로 골라 도우미 → 부트 → 가격 도우미 차례로 실행하고 작은 상태를 돌려준다.
 *   전체 페이지 이동 뒤에는 1 을 다시 하고 `stayPriceLoader.again()` — 적어 둔 원본을 같은 차례로 다시 실행한다.
 *
 * localStorage 에는 원본 셋만, `stayPrice` 로 시작하는 제 키에만 적는다(`stayPriceHelperSrc`·`stayPriceBootSrc`·`stayPriceSrc`).
 * 러너가 쓰는 키(`stayHelperSrc`·`stayBoot`·`staySteps`·`stayRunCursor`)는 읽지도 쓰지도 않는다 — 탭에 예전 러너 실행의
 * 원본(다른 판일 수 있다)과 계획·이어 하기 자리가 남아 있을 수 있고, 덮으면 그 실행이 깨진다.
 * 돌려주는 값에는 주소가 없다(파일 이름 · 바이트 수 · 판 번호뿐).
 */
(function () {
  'use strict';

  var BRIDGE = 'stay_price_bridge';
  var LABEL = 'stay price file bridge';   // 러너의 칸은 `stay file bridge` — 이름이 달라 서로 헷갈리지 않는다
  var FILES = [
    { name: 'stay_helper.js', key: 'stayPriceHelperSrc' },
    { name: 'stay_boot.js', key: 'stayPriceBootSrc' },
    { name: 'stay_price.js', key: 'stayPriceSrc' }
  ];
  var picked = {};                   // 파일 이름 → 읽은 글자(Promise). 업로드가 하나씩 와도 모인다

  function baseName(name) { return String(name || '').split(/[\\/]/).pop().replace(/\.min\.js$/, '.js'); }
  function readText(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(String(reader.result)); };
      reader.onerror = function () { reject(reader.error || new Error('읽지 못했습니다')); };
      reader.readAsText(file, 'utf-8');
    });
  }
  function collect(input) {
    [].slice.call(input.files || []).forEach(function (file) {
      var name = baseName(file.name);
      if (FILES.some(function (f) { return f.name === name; })) picked[name] = readText(file);
    });
  }
  function bridge() {
    var input = document.getElementById(BRIDGE);
    if (!input) {
      input = document.createElement('input');
      input.type = 'file';
      input.id = BRIDGE;
      input.multiple = true;
      input.accept = '.js';
      input.addEventListener('change', function () { collect(input); });
      (document.body || document.documentElement).appendChild(input);
    }
    // 숨기되 접근성 트리에서 빼지 않는다(hidden · display:none 은 빼 버린다) — 러너의 칸과 같은 방식
    input.hidden = false;
    input.setAttribute('aria-label', LABEL);
    input.style.cssText = 'position:fixed;left:0;bottom:0;width:1px;height:1px;opacity:0.01;z-index:2147483647;';
    return { ok: true, bridge: BRIDGE, label: LABEL, want: FILES.map(function (f) { return f.name; }) };
  }
  function clean(result) { return window.stayPrice && typeof window.stayPrice.scrub === 'function' ? window.stayPrice.scrub(result) : result; }
  function status() {
    return clean({
      ok: !!(window.stayRun && window.stayPrice),
      label: LABEL,
      helper: window.stayRun ? window.stayRun.version : null,
      price: window.stayPrice ? window.stayPrice.version : null,
      stored: FILES.filter(function (f) { return !!localStorage.getItem(f.key); }).map(function (f) { return f.key; })
    });
  }
  // 차례대로 실행한다. 하나라도 던지면 거기서 멈추고, store 일 때도 아무것도 적지 않는다
  function evaluate(texts, store) {
    for (var i = 0; i < FILES.length; i++) {
      try { (0, eval)(texts[i]); } catch (e) {
        return clean({ ok: false, error: FILES[i].name + ' 을 실행하다 멈췄습니다: ' + String(e && e.message || e).slice(0, 160) });
      }
    }
    if (store) FILES.forEach(function (f, i) { localStorage.setItem(f.key, texts[i]); });
    var out = status();
    out.loaded = FILES.map(function (f, i) { return { name: f.name, chars: texts[i].length }; });
    return out;
  }
  async function load() {
    var input = document.getElementById(BRIDGE);
    if (input) collect(input);       // change 사건 없이 올린 도구도 있다
    var missing = FILES.filter(function (f) { return !picked[f.name]; }).map(function (f) { return f.name; });
    if (missing.length) return clean({ ok: false, label: LABEL, error: '올라온 파일에 없는 것: ' + missing.join(', ') + ' — 세 파일을 「' + LABEL + '」 칸에 올린 뒤 다시 부릅니다', got: Object.keys(picked) });
    var texts;
    try { texts = await Promise.all(FILES.map(function (f) { return picked[f.name]; })); } catch (e) {
      return clean({ ok: false, error: '올라온 파일을 읽지 못했습니다: ' + String(e && e.message || e).slice(0, 160) });
    }
    if (input) input.value = '';
    picked = {};
    return evaluate(texts, true);
  }
  function again() {
    var texts = FILES.map(function (f) { return localStorage.getItem(f.key); });
    var missing = FILES.filter(function (f, i) { return !texts[i]; }).map(function (f) { return f.key; });
    if (missing.length) return clean({ ok: false, error: '적어 둔 원본이 없습니다: ' + missing.join(', ') + ' — 세 파일을 다시 올립니다(load)' });
    return evaluate(texts, false);
  }

  window.stayPriceLoader = { bridge: bridge, load: load, again: again, status: status };
  return bridge();
})();
