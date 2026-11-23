// 페이지 답의 본보기 — 진짜 `stay_promotion.js` 를 받침(promotion_harness.mjs)에서 돌려 얻은 답을 `fixtures/browser/` 에 둔다. 파이썬 쪽은
// 같은 입력(`inputs.json`)으로 같은 답을 받는다고 보고 이 파일들로 시험한다. 페이지를 고쳐 답이 바뀌면 다시 적는다:
//
//   NODE_PATH=<jsdom 이 있는 node_modules> node tests/page_goldens.mjs --write
//
// 파일마다 [답, take 쪽…] 목록이다(applyPromotion 는 쪽이 없어 [답]). 시각에 따라 바뀌는 칸은 정해 둔 값으로 적는다(NORMALIZED):
// 답의 `ms`(걸린 ms) · `doneAt`(끝난 시각) · `body.id`, 그리고 쪽의 `id`(페이지가 조각에 붙인 이름 — 시각으로 만든다)와 그 id 로 셈하는
// 쪽의 `sum`. 나머지 칸(`ask` · `body.chars/bytes/crc32/fnv` · 쪽의 `text/at/next/end` …)은 그대로다. tests/test_page_goldens.mjs 가
// 다시 만들어 견준다.
import { writeFileSync } from 'node:fs';
import { crc32 } from 'node:zlib';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { promotionPage, inPage, plain, takeAll, HOTEL, HERE } from './promotion_harness.mjs';

export const GOLDEN = join(HERE, 'fixtures', 'browser');
export const NORMALIZED = { ms: 0, doneAt: '2026-11-23T00:00:00.000Z', bodyId: { look: 'bgoldenlook', readPromotion: 'bgoldenread' } };
const PROMOTION = { offer: '601', promotion: '9005' };
const SET = [['tiers_value', 0, '16']];

function normal(op, answer, pieces = []) {
  const out = Object.assign({}, answer, { ms: NORMALIZED.ms, doneAt: NORMALIZED.doneAt });
  if (out.body) out.body = Object.assign({}, out.body, { id: NORMALIZED.bodyId[op] });
  // 쪽의 검사값(sum)은 조각 id 를 넣어 셈하므로 정해 둔 id 로 다시 셈한다(페이지와 같은 셈 — `id:at:end:글자` 의 CRC-32)
  const id = NORMALIZED.bodyId[op];
  const sum = (piece) => crc32(Buffer.from(`${id}:${piece.at}:${piece.end}:${piece.text}`, 'utf8')).toString(16).padStart(8, '0');
  return [out, ...pieces.map((piece) => Object.assign({}, piece, { id, sum: sum(piece) }))];
}

// 파일 이름 → 내용
export async function goldens() {
  const page = promotionPage();
  const sc = page.w.stayPromotion;
  const look = plain(await sc.look(inPage(page.w, {})));
  const read = plain(await sc.readPromotion(inPage(page.w, Object.assign({ hotel: HOTEL }, PROMOTION))));
  const readPieces = takeAll(page.w, read);
  const form = readPieces.body.window.form;
  const applyInput = Object.assign({ no: 1, hotel: HOTEL }, PROMOTION, { title: form.find(([name]) => name === 'title')[1], form, marks: readPieces.body.window.marks, set: SET });
  const apply = plain(await sc.applyPromotion(inPage(page.w, applyInput)));
  const posted = page.log.posts.map((post) => post.pairs);
  for (const [name, r] of [['look', look], ['readPromotion', read], ['applyPromotion', apply]]) if (!r.ok) throw new Error(`${name}: ${r.error}`);
  const files = {
    'look.json': normal('look', look, takeAll(page.w, look).takes),
    'readPromotion.json': normal('readPromotion', read, readPieces.takes),
    'applyPromotion.json': normal('applyPromotion', apply),
    'inputs.json': {
      _note: '손 조각(tests/fixtures/erp/promotions.json · promotions_erp.mjs)을 받침에 세우고 진짜 stay_promotion.js 를 돌려 얻은 답의 입력이다. '
        + '답 파일마다 [답, take 쪽…] 목록이고, 시각에 따라 바뀌는 칸은 normalized 의 값으로 적었다. posted 는 저장 요청이 실어 보낸 [이름, 값] 쌍이다.',
      normalized: { ms: NORMALIZED.ms, doneAt: NORMALIZED.doneAt, 'body.id 와 쪽의 id': NORMALIZED.bodyId },
      hotel: HOTEL,
      look: {},
      readPromotion: Object.assign({ hotel: HOTEL }, PROMOTION),
      applyPromotion: applyInput,
      posted
    }
  };
  page.w.close();
  return files;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (!process.argv.includes('--write')) {
    console.error('본보기를 다시 적으려면 --write 를 붙입니다');
    process.exit(2);
  }
  const files = await goldens();
  for (const [name, data] of Object.entries(files)) writeFileSync(join(GOLDEN, name), JSON.stringify(data, null, 2) + '\n');
  console.log(`다시 적음: ${Object.keys(files).join(', ')}`);
}
