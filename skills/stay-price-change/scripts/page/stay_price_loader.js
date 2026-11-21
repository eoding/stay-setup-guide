/* stay_price_loader.js — 가격 변경 도우미를 로그인된 ERP 탭에 올리는 작은 실행 묶음 (stay-price-change · stay-addon-price-change ·
 * stay-charge-change).
 *
 * 쓰는 법(브라우저 도구 셋):
 *   1. JS 실행 도구로 이 파일 전체를 실행한다 → 파일 칸 `input#stay_price_bridge`(접근성 이름 `stay price file bridge`)가 생기고
 *      `window.stayPriceLoader` 가 선다. 칸은 1px · 거의 투명이라 보이지 않지만 접근성 트리에는 남아 도구가 이름으로 찾는다.
 *      이 첫 답(`sets`)은 묶음 셋의 파일을 모두 댄다 — 어느 도우미가 붙여 넣어도 제 묶음의 파일 수를 잘못 듣지 않는다. 도우미는 보통
 *      이 파일 뒤에 `stayPriceLoader.again('<묶음>')` 한 줄을 붙여 한 번에 실행하므로, 실제로 보는 답은 제 묶음의 것이다.
 *   2. 업로드 도구로 **그 이름의** 칸에 파일을 올린다(ERP 의 사진 올리기 칸과 헷갈리지 않게 — 한 번에 모두든 하나씩이든):
 *      가격 캘린더는 러너의 `stay_helper.js`·`stay_boot.js`, 그리고 `stay_price.js` 셋. 부가옵션 가격은 그 셋에
 *      `stay_addon_price.js` 를 더한 넷.
 *   3. `await stayPriceLoader.load()`(부가옵션은 `load('addon')`) → 이름으로 골라 도우미 → 부트 → 가격 도우미(→ 부가옵션 가격
 *      도우미) 차례로 실행하고 작은 상태를 돌려준다.
 *   전체 페이지 이동 뒤에는 1 을 다시 하고 `stayPriceLoader.again()`(부가옵션은 `again('addon')`) — 적어 둔 원본을 같은 차례로 다시 실행한다.
 *   `again` 이 거절하면 원본이 없거나 예전 판인 파일만(`want`) 대어, 무엇을 올릴지 그 답 하나로 안다. 그 파일만 올리고 `load` 를 부르면
 *   나머지는 이 탭에 적어 둔 원본(설치된 것과 같은 것)을 쓴다 — 다른 묶음을 쓰던 탭에서 제 묶음의 파일 하나만 없을 때.
 *
 * 묶음은 셋이다 — 인자 없이(가격 캘린더) 세 파일, `'addon'`(부가옵션 가격) 네 파일, `'charge'`(부과금) 네 파일. `bridge` · `load` ·
 * `again` · `status` 가 같은 인자를 받는다. 파일 칸은 하나라 다섯 이름을 모두 모은다.
 *
 * 이 파일은 설치된 다섯 파일의 알아볼 값(`INSTALLED`)을 안다. 도우미는 이 파일을 설치된 스킬에서 늘 새로 붙여 넣으므로, 그 값과 다른
 * 글자는 예전 판이다 — `load()` 는 올라온 파일이, `again()` 은 적어 둔 원본이 그 값과 다르면 아무것도 실행하지 않고 어느 파일인지
 * 말한다. 플러그인을 새로 깐 뒤 예전 탭이 예전 코드를 되살리지 않는다.
 *
 * localStorage 에는 `stayPrice` 로 시작하는 키 여섯만 생긴다. 이 올리개는 원본만 적는다(`stayPriceHelperSrc`·`stayPriceBootSrc`·
 * `stayPriceSrc`, 부가옵션 묶음은 `stayPriceAddonSrc`, 부과금 묶음은 `stayPriceChargeSrc` 까지). 올린 가격 도우미는 마지막 작업의 답을
 * `stayPriceLast` 에 적는다(부가옵션 · 부과금 도우미의 작업도 같은 작업 틀을 지나 같은 키에). 러너가 쓰는 키(`stayHelperSrc`·`stayBoot`·`staySteps`·`stayRunCursor`)는 읽지도 쓰지도 않는다 —
 * 탭에 예전 러너 실행의 원본(다른 판일 수 있다)과 계획·이어 하기 자리가 남아 있을 수 있고, 덮으면 그 실행이 깨진다.
 * 돌려주는 값에는 주소가 없다(파일 이름 · 바이트 수 · 판 번호뿐). 판 번호는 점을 `·` 로 바꿔 보낸다(`0·15·0`).
 */
(function () {
  'use strict';

  var BRIDGE = 'stay_price_bridge';
  var LABEL = 'stay price file bridge';   // 러너의 칸은 `stay file bridge` — 이름이 달라 서로 헷갈리지 않는다
  var HELPER = { name: 'stay_helper.js', key: 'stayPriceHelperSrc' };
  var BOOT = { name: 'stay_boot.js', key: 'stayPriceBootSrc' };
  var PRICE = { name: 'stay_price.js', key: 'stayPriceSrc' };
  // 묶음의 마지막 파일은 제 도우미를 세운다 — 상태(status)는 그 도우미의 판을 `report` 이름으로 알린다(전역 `global`)
  var ADDON = { name: 'stay_addon_price.js', key: 'stayPriceAddonSrc', report: 'addon', global: 'stayAddonPrice' };
  var CHARGE = { name: 'stay_charge.js', key: 'stayPriceChargeSrc', report: 'charge', global: 'stayCharge' };
  // 묶음 → 실행 차례. 인자 없이 부르면 가격 캘린더 묶음이다
  var SETS = { price: [HELPER, BOOT, PRICE], addon: [HELPER, BOOT, PRICE, ADDON], charge: [HELPER, BOOT, PRICE, CHARGE] };
  var KNOWN = [HELPER, BOOT, PRICE, ADDON, CHARGE];
  // 설치된 다섯 파일의 알아볼 값 — 줄 끝을 \n 으로 맞춘 글자의 UTF-8 바이트 수 · CRC-32 · FNV-1a(페이지가 조각을 알아보는 셈과 같다).
  // 다섯 파일 가운데 하나라도 고치면 `python3 scripts/loader_identity.py` 로 다시 적는다 — tests/test_loader_identity.py 가 견준다.
  var INSTALLED = {
    'stay_helper.js': { bytes: 203280, crc32: '2469cc98', fnv: '8fc462df' },
    'stay_boot.js': { bytes: 176868, crc32: 'fca0450a', fnv: 'fb095b48' },
    'stay_price.js': { bytes: 103649, crc32: '348e9dd2', fnv: '32409fe4' },
    'stay_addon_price.js': { bytes: 16645, crc32: '8503dfcd', fnv: '9083ec41' },
    'stay_charge.js': { bytes: 19858, crc32: 'b1e9a054', fnv: 'a806ff00' }
  };
  var picked = {};                   // 파일 이름 → 읽은 글자(Promise). 업로드가 하나씩 와도 모인다

  function baseName(name) { return String(name || '').split(/[\\/]/).pop(); }
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
      if (KNOWN.some(function (f) { return f.name === name; })) picked[name] = readText(file);
    });
  }

  var CRC_TABLE = (function () {
    var table = [];
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c >>> 0;
    }
    return table;
  })();
  // 글자의 알아볼 값. 줄 끝을 \n 으로 맞춘다 — 윈도에서 받은 플러그인은 파일 줄 끝이 \r\n 일 수 있다
  function identity(text) {
    text = String(text).replace(/\r\n/g, '\n');
    var crc = 0xffffffff, fnv = 0x811c9dc5, bytes = 0;
    var add = function (b) { crc = CRC_TABLE[(crc ^ b) & 0xff] ^ (crc >>> 8); fnv = Math.imul(fnv ^ b, 0x01000193) >>> 0; bytes++; };
    for (var i = 0; i < text.length; i++) {
      var c = text.codePointAt(i);
      if (c > 0xffff) i++;
      if (c < 0x80) add(c);
      else if (c < 0x800) { add(0xc0 | c >> 6); add(0x80 | c & 63); }
      else if (c < 0x10000) { add(0xe0 | c >> 12); add(0x80 | c >> 6 & 63); add(0x80 | c & 63); }
      else { add(0xf0 | c >> 18); add(0x80 | c >> 12 & 63); add(0x80 | c >> 6 & 63); add(0x80 | c & 63); }
    }
    var hex = function (n) { return ('0000000' + (n >>> 0).toString(16)).slice(-8); };
    return { bytes: bytes, crc32: hex(crc ^ 0xffffffff), fnv: hex(fnv) };
  }
  // 설치된 것과 다른 파일의 이름들 — texts 는 files 차례
  function notInstalled(files, texts) {
    return files.filter(function (f, i) {
      var seen = identity(texts[i]), want = INSTALLED[f.name];
      return seen.bytes !== want.bytes || seen.crc32 !== want.crc32 || seen.fnv !== want.fnv;
    }).map(function (f) { return f.name; });
  }
  // 묶음 이름 → 실행할 파일들. 인자 없이는 가격 캘린더, 모르는 이름이면 null
  function filesOf(set) {
    if (set === undefined || set === null) return SETS.price;
    return Object.prototype.hasOwnProperty.call(SETS, set) ? SETS[set] : null;
  }
  function unknownSet(set) {
    return clean({ ok: false, label: LABEL, error: '모르는 묶음입니다: ' + String(set).slice(0, 40) + ' — 비우면 가격 캘린더, "addon" 이면 부가옵션 가격, "charge" 면 부과금입니다' });
  }

  // 칸을 세운다. 묶음을 대면 그 묶음의 파일 이름(`want`), 대지 않으면 묶음마다의 파일 이름(`sets`)을 댄다
  function bridge(set) {
    var files = filesOf(set);
    if (!files) return unknownSet(set);
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
    var names = function (list) { return list.map(function (f) { return f.name; }); };
    if (set === undefined || set === null) {
      var sets = {};
      Object.keys(SETS).forEach(function (name) { sets[name] = names(SETS[name]); });
      return clean({ ok: true, bridge: BRIDGE, label: LABEL, sets: sets });
    }
    return clean({ ok: true, bridge: BRIDGE, label: LABEL, want: names(files) });
  }
  // 브라우저 도구는 점으로 이은 조각 셋 이상뿐인 글자(판 번호 `0.15.0`)를 토큰으로 보고 가린다 — 점을 `·` 로 바꾼다.
  // 가격 도우미가 올라오기 전의 답도 지나므로 `stayPrice.scrub` 과 따로 둔다(그 scrub 도 같은 규칙이다)
  var DOTTED = /^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2,}$/;
  function dotless(value) {
    if (typeof value === 'string') return DOTTED.test(value) ? value.split('.').join('·') : value;
    if (Array.isArray(value)) return value.map(dotless);
    if (value && typeof value === 'object') {
      var out = {};
      Object.keys(value).forEach(function (k) { out[k] = dotless(value[k]); });
      return out;
    }
    return value;
  }
  function clean(result) { return dotless(window.stayPrice && typeof window.stayPrice.scrub === 'function' ? window.stayPrice.scrub(result) : result); }
  function status(set) {
    var files = filesOf(set);
    if (!files) return unknownSet(set);
    var extra = files.filter(function (f) { return f.report; });
    var out = {
      ok: !!(window.stayRun && window.stayPrice && extra.every(function (f) { return window[f.global]; })),
      label: LABEL,
      helper: window.stayRun ? window.stayRun.version : null,
      price: window.stayPrice ? window.stayPrice.version : null
    };
    extra.forEach(function (f) { out[f.report] = window[f.global] ? window[f.global].version : null; });
    out.stored = files.filter(function (f) { return !!localStorage.getItem(f.key); }).map(function (f) { return f.key; });
    return clean(out);
  }
  // 차례대로 실행한다. 하나라도 던지면 거기서 멈추고, store 일 때도 아무것도 적지 않는다
  function evaluate(set, files, texts, store) {
    for (var i = 0; i < files.length; i++) {
      try { (0, eval)(texts[i]); } catch (e) {
        return clean({ ok: false, error: files[i].name + ' 을 실행하다 멈췄습니다: ' + String(e && e.message || e).slice(0, 160) });
      }
    }
    if (store) files.forEach(function (f, i) { localStorage.setItem(f.key, texts[i]); });
    var out = status(set);
    out.loaded = files.map(function (f, i) { return { name: f.name, chars: texts[i].length }; });
    return out;
  }
  // 이 탭에 적어 둔 원본 가운데 설치된 것과 같은 것 — 파일 이름 → 글자. 없거나 예전 판인 파일은 들지 않는다
  function storedCurrent(files) {
    var out = {};
    files.forEach(function (f) {
      var text = localStorage.getItem(f.key);
      if (text && !notInstalled([f], [text]).length) out[f.name] = text;
    });
    return out;
  }
  // 올라온 파일을 쓰고, 올라오지 않은 파일은 이 탭에 적어 둔 원본이 설치된 것과 같으면 그것을 쓴다 — 그래서 again 이 댄 파일(`want`)만
  // 올려도 된다. 올라온 파일이 설치된 것과 다르면 아무것도 실행하지 않는다
  async function load(set) {
    var files = filesOf(set);
    if (!files) return unknownSet(set);
    var input = document.getElementById(BRIDGE);
    if (input) collect(input);       // change 사건 없이 올린 도구도 있다
    var kept = storedCurrent(files);
    var missing = files.filter(function (f) { return !picked[f.name] && !kept[f.name]; }).map(function (f) { return f.name; });
    if (missing.length) return clean({ ok: false, label: LABEL, want: missing, error: '올라온 파일에 없는 것: ' + missing.join(', ') + ' — 그 파일을 「' + LABEL + '」 칸에 올린 뒤 다시 부릅니다', got: Object.keys(picked) });
    var uploaded = files.filter(function (f) { return picked[f.name]; });
    var texts;
    try {
      var read = await Promise.all(uploaded.map(function (f) { return picked[f.name]; }));
      var byName = {};
      uploaded.forEach(function (f, i) { byName[f.name] = read[i]; });
      texts = files.map(function (f) { return Object.prototype.hasOwnProperty.call(byName, f.name) ? byName[f.name] : kept[f.name]; });
    } catch (e) {
      return clean({ ok: false, error: '올라온 파일을 읽지 못했습니다: ' + String(e && e.message || e).slice(0, 160) });
    }
    var wrong = notInstalled(files, texts);
    if (wrong.length) {
      return clean({ ok: false, label: LABEL, wrong: wrong, error: '올라온 파일이 설치된 도우미의 것과 다릅니다: ' + wrong.join(', ') +
        ' — 올린 폴더에 남은 예전 복사본일 수 있습니다. 설치된 스킬 폴더의 그 파일을 「' + LABEL + '」 칸에 다시 올린 뒤 다시 부릅니다' });
    }
    if (input) input.value = '';
    picked = {};
    return evaluate(set, files, texts, true);
  }
  // 적어 둔 원본을 다시 실행한다. 없거나 예전 판인 파일이 있으면 아무것도 실행하지 않고 그 파일만 `want` 에 댄다 — 그 파일을 올리고
  // load 를 부르면 나머지는 적어 둔 원본을 쓴다
  function again(set) {
    var files = filesOf(set);
    if (!files) return unknownSet(set);
    var texts = files.map(function (f) { return localStorage.getItem(f.key); });
    var missing = files.filter(function (f, i) { return !texts[i]; }).map(function (f) { return f.name; });
    var wrong = files.filter(function (f, i) { return texts[i] && notInstalled([f], [texts[i]]).length; }).map(function (f) { return f.name; });
    if (missing.length || wrong.length) {
      var want = files.filter(function (f) { return missing.indexOf(f.name) >= 0 || wrong.indexOf(f.name) >= 0; }).map(function (f) { return f.name; });
      var said = [];
      if (missing.length) said.push('적어 둔 원본이 없습니다: ' + missing.join(', '));
      if (wrong.length) said.push('적어 둔 원본이 설치된 도우미와 다릅니다: ' + wrong.join(', ') + ' — 도우미를 새로 깔기 전에 이 탭에 적어 둔 예전 판입니다');
      var out = { ok: false, want: want, error: said.join(' · ') + '. 이 파일을 「' + LABEL + '」 칸에 다시 올립니다(load)' +
        (want.length < files.length ? ' — 나머지는 이 탭에 적어 둔 원본을 씁니다' : '') };
      if (wrong.length) out.wrong = wrong;
      return clean(out);
    }
    return evaluate(set, files, texts, false);
  }

  window.stayPriceLoader = { bridge: bridge, load: load, again: again, status: status };
  return bridge();
})();
