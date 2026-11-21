// 시험의 받침 — 편집 창 하나를 저장하는 도우미(부가옵션 가격 · 부과금)의 진짜 명령과 jsdom 의 페이지로 한 바퀴를 돈다: 읽기 →
// 미리보기 → 적용 직전 다시 읽기 → begin → calls 의 저장을 페이지에서 하고 record-result. 도우미가 SKILL.md 대로 하는 차례다.
// 부과금 도우미의 시험도 이 파일을 쓴다. node --test 가 시험으로 집지 않도록 이름이 test_ 로 시작하지 않는다.
//
//   kind  {script: 명령 파일, page: 'stayAddonPrice' | 'stayCharge', read: 'readLine' | 'readCharge', calls: 'lines' | 'charges',
//          prefix: 'line' | 'charge'}
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { inPage, plain } from '../../stay-price-change/tests/page_harness.mjs';

function pieces(w, page, answer) {
  if (!answer || !answer.body) return [answer];
  const out = [answer];
  for (let at = 0; at < answer.body.chars;) {
    const piece = plain(w[page].take(answer.body.id, at));
    if (!piece.ok) throw new Error(piece.error);
    out.push(piece);
    at = piece.next;
  }
  return out;
}

export function windowFlow(page, kind) {
  const dir = mkdtempSync(join(tmpdir(), 'stay-window-flow-'));
  const env = Object.assign({}, process.env, { STAY_PRICE_LEDGER_DIR: join(dir, 'ledger') });
  let files = 0, reads = 0;
  const file = (name, data) => { const path = join(dir, `${++files}-${name}`); writeFileSync(path, JSON.stringify(data)); return path; };
  const must = (...args) => {
    const done = spawnSync('python3', [kind.script, ...args.map(String)], { encoding: 'utf8', env });
    if (done.status !== 0) throw new Error(`${args[0]} 이 종료 ${done.status}: ${done.stderr || done.stdout}`);
    return JSON.parse(done.stdout);
  };
  const ui = page.w[kind.page];
  return {
    dir, must,
    async read(scope) {
      const at = join(dir, `읽기-${++reads}`);
      mkdirSync(at);
      must('read-calls', ...(typeof scope === 'number' ? ['--record', scope] : ['--request', file('request.json', scope)]), '--out', join(at, 'calls.json'));
      const calls = JSON.parse(readFileSync(join(at, 'calls.json'), 'utf8'))[kind.calls];
      for (let i = 0; i < calls.length; i++) {
        const answer = plain(await ui[kind.read](inPage(page.w, calls[i])));
        if (!answer.ok) throw new Error(`${kind.read}: ${answer.error}`);
        writeFileSync(join(at, `${kind.prefix}-${i + 1}.json`), JSON.stringify(pieces(page.w, kind.page, answer)));
      }
      must('read', '--calls', join(at, 'calls.json'), '--answers', at, '--out', join(at, 'snapshot.json'));
      return join(at, 'snapshot.json');
    },
    // 미리보기 → 적용 직전 다시 읽기 → begin → 저장마다 페이지 · record-result. 단계마다 {call, answer, recorded}
    async change(request) {
      const plan = join(dir, 'plan.json');
      const short = must('plan', '--snapshot', await this.read(request), '--request', file('request.json', request), '--record', '--out', plan);
      const begun = must('begin', '--change', short.change_id, '--plan', plan, '--snapshot', await this.read(short.change_id));
      const steps = [];
      for (const call of must('calls', '--change', short.change_id).calls) {
        const answer = plain(await ui[call.op](inPage(page.w, call.payload)));
        steps.push({ call, answer, recorded: must('record-result', '--change', short.change_id, '--result', file(`step-${call.no}.json`, answer)) });
      }
      return { short, begun, steps };
    },
    close() { rmSync(dir, { recursive: true, force: true }); }
  };
}
