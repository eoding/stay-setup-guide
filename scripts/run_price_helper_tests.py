#!/usr/bin/env python3
"""run_price_helper_tests.py — 가격 변경 도우미 넷(stay-price-change · stay-addon-price-change · stay-charge-change ·
stay-promotion-change)의 시험을 모두 돈다.

이 저장소에는 CI 가 없다. 도우미마다 시험이 둘이다 — 파이썬 시험(`tests/test_*.py`, unittest)과 페이지 시험(`tests/test_page_*.mjs`,
node --test 와 jsdom). 여덟을 차례로 돌려 무엇을 돌렸는지 찍고, 하나라도 실패하거나 건너뛴 시험이 있거나 돌지 못하면 0 이 아닌 종료
코드로 끝난다.

    NODE_PATH=<jsdom 이 든 node_modules> python3 scripts/run_price_helper_tests.py
    NODE_PATH=<jsdom 이 든 node_modules> python3.11 scripts/run_price_helper_tests.py     # 다른 파이썬으로

- 파이썬: 이 스크립트를 부른 파이썬(3.10 이상)으로 돈다. 페이지 시험이 안에서 부르는 `python3` 도 같은 파이썬이 되도록 그 파이썬을
  `-B` 와 함께 부르는 작은 `python3` 를 PATH 맨 앞에 잠시 둔다(임시 폴더, 끝나면 지운다 — 윈도에서는 두지 않고 PATH 의 것을 댄다).
- Node: PATH 의 `node`(18 이상 — node --test).
- jsdom: 페이지 시험은 `require('jsdom')` 으로 jsdom 을 찾는다. 이 저장소는 jsdom 을 담지 않는다 — jsdom 이 든 node_modules 를
  `NODE_PATH` 로 준다(시험은 jsdom 22 로 맞췄고, 사람의 클릭을 흉내 내려고 jsdom 안쪽 파일 `living/generated/utils.js` 를 쓴다).
  못 찾으면 페이지 시험을 돌리지 않고 그렇게 말한 뒤 실패로 끝난다(건너뛰어 통과로 치지 않는다).
- __pycache__ 를 만들지 않는다(-B · PYTHONDONTWRITEBYTECODE — 페이지 시험은 `python3 -I` 로 불러 환경 변수가 듣지 않으므로 위의
  `python3` 가 -B 를 붙인다).

여섯 페이지 파일(러너의 stay_helper.js · stay_boot.js, stay_price.js · stay_addon_price.js · stay_charge.js · stay_promotion.js)을
고치면 먼저
`python3 skills/stay-price-change/scripts/loader_identity.py` 로 올리개의 알아볼 값을 다시 적는다 — 가격 캘린더 도우미의 파이썬 시험
(test_loader_identity)이 견준다.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = (("stay-price-change", "가격 캘린더 도우미"), ("stay-addon-price-change", "부가옵션 가격 도우미"),
          ("stay-charge-change", "부과금 도우미"), ("stay-promotion-change", "프로모션 할인 도우미"))
NODE_MIN = 18
JSDOM_HINT = ("jsdom 을 찾지 못했습니다 — 페이지 시험을 돌리지 않았습니다. 이 저장소는 jsdom 을 담지 않습니다. jsdom(22 로 맞춤)이 든 "
              "node_modules 를 NODE_PATH 로 주고 다시 부릅니다: NODE_PATH=/path/to/node_modules python3 scripts/run_price_helper_tests.py "
              "(없으면 아무 빈 폴더에서 `npm install jsdom@22` 를 하고 그 폴더의 node_modules 를 줍니다)")


def say(text: str = "") -> None:
    print(text, flush=True)


def python_suite(folder: Path, env: dict) -> tuple[bool, str]:
    """파이썬 시험 하나 — 통과했는지와 한 줄 요약. 건너뛴 시험(skipped)이 있으면 실패다."""
    done = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"], cwd=folder, env=env,
                          capture_output=True, text=True)
    ran = re.search(r"^Ran (\d+) tests? in ([\d.]+)s$", done.stderr, re.M)
    last = done.stderr.strip().splitlines()[-1] if done.stderr.strip() else ""
    if done.returncode != 0 or not ran or not last.startswith("OK") or "skipped" in last:
        tail = "\n".join(done.stderr.strip().splitlines()[-25:])
        return False, f"실패 — {last or '답 없음'}\n{tail}"
    return True, f"{ran.group(1)}개 통과 ({float(ran.group(2)):.0f}초)"


def page_suite(folder: Path, env: dict) -> tuple[bool, str]:
    """페이지 시험 하나 — node --test 의 수(tests · pass · fail · skipped · todo · cancelled)를 읽는다. 건너뛴 시험이 있으면 실패다."""
    files = sorted(str(path.relative_to(folder)) for path in (folder / "tests").glob("test_page_*.mjs"))
    if not files:
        return False, "페이지 시험 파일이 없습니다"
    started = time.monotonic()
    done = subprocess.run(["node", "--test", *files], cwd=folder, env=env, capture_output=True, text=True)
    counts = {name: int(value) for name, value in re.findall(r"^ℹ (tests|pass|fail|skipped|todo|cancelled) (\d+)$", done.stdout, re.M)}
    left = {name: counts.get(name, 0) for name in ("fail", "skipped", "todo", "cancelled") if counts.get(name, 0)}
    if done.returncode != 0 or not counts.get("tests") or counts.get("pass") != counts.get("tests") or left:
        failing = [line for line in done.stdout.splitlines() if line.startswith(("✖", "not ok"))][:10]
        said = " · ".join(f"{name} {value}" for name, value in left.items()) or f"종료 코드 {done.returncode}"
        return False, f"실패 — {said}\n" + "\n".join(failing + done.stderr.strip().splitlines()[-10:])
    return True, f"{counts['tests']}개 통과 ({time.monotonic() - started:.0f}초)"


def node_version() -> tuple[str | None, int]:
    if not shutil.which("node"):
        return None, 0
    text = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip()
    major = re.match(r"v(\d+)", text)
    return text, int(major.group(1)) if major else 0


def jsdom_found(env: dict) -> tuple[str | None, str | None]:
    """페이지 시험이 찾는 자리에서 jsdom 을 찾는다 — (판, 자리) 또는 (None, None)."""
    script = "const p=require.resolve('jsdom/package.json');console.log(require(p).version+'\\t'+require('path').dirname(p))"
    done = subprocess.run(["node", "-e", script], cwd=ROOT / "skills" / "stay-price-change" / "tests", env=env,
                          capture_output=True, text=True)
    if done.returncode != 0 or "\t" not in done.stdout:
        return None, None
    version, place = done.stdout.strip().split("\t", 1)
    return version, place


def shim(folder: Path) -> bool:
    """페이지 시험이 부르는 `python3` 를 이 파이썬으로 — 임시 폴더에 `-B` 를 붙여 이 파이썬을 부르는 `python3` 를 둔다. 페이지 시험은
    `python3 -I` 로 부르는데 -I 는 PYTHONDONTWRITEBYTECODE 를 듣지 않아 -B 가 따로 있어야 __pycache__ 가 생기지 않는다. 윈도는 False."""
    if os.name == "nt":
        return False
    target = folder / "python3"
    target.write_text(f'#!/bin/sh\nexec "{sys.executable}" -B "$@"\n', encoding="utf-8")
    target.chmod(0o755)
    return True


def main() -> int:
    if sys.version_info < (3, 10):
        say(f"파이썬 3.10 이상이 필요합니다(지금 {sys.version.split()[0]})")
        return 2
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    node, major = node_version()
    say(f"파이썬  {sys.version.split()[0]}  {sys.executable}")
    say(f"Node    {node or '없음'}  {shutil.which('node') or ''}")
    jsdom, place = jsdom_found(env) if node else (None, None)
    say(f"jsdom   {jsdom or '없음'}  {place or ''}  (NODE_PATH={os.environ.get('NODE_PATH') or '비어 있음'})")
    say()
    results = []
    with tempfile.TemporaryDirectory(prefix="price-helper-tests-") as temp:
        bin_dir = Path(temp)
        if shim(bin_dir):
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            say(f"페이지 시험이 부르는 python3 도 {sys.executable} 입니다")
        else:
            say(f"페이지 시험이 부르는 python3 는 PATH 의 것입니다: {shutil.which('python3') or '없음'}")
        say()
        for name, label in SKILLS:
            folder = ROOT / "skills" / name
            ok, line = python_suite(folder, env)
            results.append(ok)
            say(f"{'통과' if ok else '실패'}  {label} · 파이썬 시험  ({name}: python -B -m unittest discover -s tests) — {line}")
            if node is None or major < NODE_MIN:
                results.append(False)
                say(f"실패  {label} · 페이지 시험 — Node {NODE_MIN} 이상이 없어 돌리지 못했습니다(지금 {node or '없음'})")
            elif jsdom is None:
                results.append(False)
                say(f"실패  {label} · 페이지 시험 — {JSDOM_HINT}")
            else:
                ok, line = page_suite(folder, env)
                results.append(ok)
                say(f"{'통과' if ok else '실패'}  {label} · 페이지 시험  ({name}: node --test tests/test_page_*.mjs) — {line}")
    say()
    passed = sum(results)
    say(f"{passed}/{len(results)} 통과" + ("" if passed == len(results) else " — 실패하거나 돌지 못한 시험이 있습니다"))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
