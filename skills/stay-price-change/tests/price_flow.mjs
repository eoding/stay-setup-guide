// 시험의 받침 — 진짜 명령(`price_change.py`)과 jsdom 의 페이지로 한 바퀴를 돈다: look → 읽기 → 미리보기 → 적용 직전 다시 읽기 →
// begin → calls 의 저장을 페이지에서 하고 record-result. 도우미가 SKILL.md 대로 하는 차례 그대로다.
// node --test 가 시험으로 집지 않도록 이름이 test_ 로 시작하지 않는다.
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { inPage, plain, takeAll, SKILL } from './page_harness.mjs';

const SCRIPT = join(SKILL, 'scripts', 'price_change.py');

// 답 하나와 (조각이 있으면) 그 쪽들 — 도우미가 저장하는 그대로
function withPieces(w, answer) { return answer && answer.body ? [answer, ...takeAll(w, answer).takes] : [answer]; }

export function priceFlow(page) {
  const dir = mkdtempSync(join(tmpdir(), 'stay-price-flow-'));
  const env = Object.assign({}, process.env, { STAY_PRICE_LEDGER_DIR: join(dir, 'ledger') });
  let files = 0;
  const file = (name, data) => { const path = join(dir, `${++files}-${name}`); writeFileSync(path, JSON.stringify(data)); return path; };
  const folder = (name) => { const path = join(dir, name); mkdirSync(path, { recursive: true }); return path; };
  // 명령 하나 — 종료 0 · 1 은 표준 출력, 2 는 표준 오류의 JSON
  const cli = (...args) => {
    const done = spawnSync('python3', [SCRIPT, ...args.map(String)], { encoding: 'utf8', env });
    if (![0, 1, 2].includes(done.status)) throw new Error(`${args[0]}: ${done.stderr}`);
    return Object.assign(JSON.parse(done.status === 2 ? done.stderr : done.stdout), { code: done.status });
  };
  const must = (...args) => {
    const out = cli(...args);
    if (out.code !== 0) throw new Error(`${args[0]} 이 종료 ${out.code}: ${out.error || JSON.stringify(out)}`);
    return out;
  };
  const sp = page.w.stayPrice;
  let reads = 0;
  return {
    dir, cli, must, file,
    async look(input) {
      const look = folder('look');
      const answer = plain(await sp.look(inPage(page.w, input || {})));
      writeFileSync(join(look, 'look-1.json'), JSON.stringify(withPieces(page.w, answer)));
      return Object.assign(must('look', '--answers', look), { answer });
    },
    // 읽기 한 번 — read-calls(범위 파일 또는 장부 번호) → readPair 마다 → reserved 가 끝날 때까지 readReserved → read
    async read(scope) {
      const at = folder(`읽기-${++reads}`);
      const flags = typeof scope === 'number' ? ['--record', scope] : ['--request', file('request.json', scope)];
      must('read-calls', ...flags, '--out', join(at, 'calls.json'));
      const calls = join(at, 'calls.json');
      const asked = JSON.parse(readFileSync(calls, 'utf8'));
      for (let i = 0; i < asked.pairs.length; i++) {
        const answer = plain(await sp.readPair(inPage(page.w, asked.pairs[i])));
        if (!answer.ok) throw new Error(`readPair: ${answer.error}`);
        writeFileSync(join(at, `pair-${i + 1}.json`), JSON.stringify(withPieces(page.w, answer)));
      }
      for (let n = 1, round = must('reserved', '--calls', calls, '--answers', at); !round.done; round = must('reserved', '--calls', calls, '--answers', at)) {
        for (const probe of round.ask) {
          const answer = plain(await sp.readReserved(inPage(page.w, probe)));
          if (!answer.ok) throw new Error(`readReserved: ${answer.error}`);
          writeFileSync(join(at, `resv-${n++}.json`), JSON.stringify(withPieces(page.w, answer)));
        }
      }
      must('read', '--calls', calls, '--answers', at, '--out', join(at, 'snapshot.json'));
      return join(at, 'snapshot.json');
    },
    // 미리보기 → 적용 직전 다시 읽기 → begin. 장부 번호와 계산 파일
    async preview(request) {
      const plan = join(dir, `plan-${reads}.json`);
      const short = must('plan', '--snapshot', await this.read(request), '--request', file('request.json', request), '--record', '--out', plan);
      return { change: short.change_id, plan, short };
    },
    async begin(change, plan) { return must('begin', '--change', change, '--plan', plan, '--snapshot', await this.read(change)); },
    // calls 의 저장을 차례로 페이지에서 하고 record-result — 저장되지 않은 단계에서 멈춘다(SKILL.md 「적용하기」 2). `before(call)` 은
    // 저장마다 그 앞에 부른다(그 사이 다른 사람이 ERP 에서 저장하는 것을 흉내 낸다)
    async apply(change, before) {
      const calls = must('calls', '--change', change).calls;
      const steps = [];
      for (const call of calls) {
        if (before) await before(call);
        const answer = plain(await sp[call.op](inPage(page.w, call.payload)));
        const recorded = must('record-result', '--change', change, '--result', file(`step-${call.no}.json`, answer));
        steps.push({ call, answer, recorded });
        if (!recorded.saved) break;
      }
      return steps;
    },
    close() { rmSync(dir, { recursive: true, force: true }); }
  };
}
