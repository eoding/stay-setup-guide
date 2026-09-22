#!/usr/bin/env python3
"""sync_screen_dictionary.py — 화면 사전을 ERP 화면 마크업에서 다시 받아 온다.

`references/screen-dictionary.json` · `.md` 는 **손으로 고치는 파일이 아니다**. ERP(basecamp)
저장소의 관리 명령

    python manage.py stay_screen_dictionary --out <디렉터리>

이 Stay 화면 31개를 실제로 렌더해 `data-stay-*` 표식을 읽고, 화면에서 나오지 않는 산문
(화면 별칭 · 여는 길 · 거부 문구 보충)은 ERP 쪽 `stay/agent_markup_notes.json` 과 합쳐 두 파일을
찍는다. 이 스크립트는 그 명령을 대신 돌려 주고 결과를 이 스킬의 `references/` 에 덮어쓴다.
ERP 가 Stay 화면을 배포할 때마다 한 번 돌리면 된다.

사용법:
    python3 sync_screen_dictionary.py --basecamp ~/src/basecamp
    python3 sync_screen_dictionary.py --basecamp ~/src/basecamp --check     # 덮어쓰지 않고 낡았는지만
    python3 sync_screen_dictionary.py --basecamp ~/src/basecamp -o /tmp/미리보기

ERP 저장소 경로(`--basecamp`)는 사람마다 다르므로 반드시 준다. 그 저장소는 **로컬 개발 DB** 를
보는 설정이어야 한다 — 명령이 픽스처 호텔을 세웠다가 트랜잭션을 되감으므로 아무것도 남지
않지만, 운영·스테이지 DB 를 향해 돌릴 이유는 없다. 돌리기 전에 어느 DB 를 보는지 한 줄로
알려 준다.

사전을 새로 받았으면 직원용 화면 안내도 다시 만든다(저장소에 담긴 것은 폰트를 넣지 않은 판이다):

    python3 scripts/render_screen_guide.py --no-font

종료 코드: 0 성공(또는 `--check` 통과) / 1 실패·사전이 낡음 / 2 사용법 오류
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS_DIR.parent
REFERENCES_DIR = SKILL_DIR / "references"

#: 관리 명령이 찍는 두 파일 — 이름이 이 스킬의 `references/` 와 같다.
FILE_NAMES = ("screen-dictionary.json", "screen-dictionary.md")

#: 감싸는 설정 모듈이 딛고 서는 ERP 설정. 로컬 개발 DB 를 보고 테스트용 플래그가 켜져 있다.
DEFAULT_SETTINGS = "basecamp.settings.test"

#: 임시로 만들어 쓰는 설정 모듈 이름(ERP 저장소에는 파일을 남기지 않는다).
SHIM_MODULE = "stay_dict_settings"

#: 그 설정 모듈의 내용. 두 줄뿐이고 이유는 아래 주석 그대로다.
SHIM_SOURCE = '''\
"""sync_screen_dictionary.py 가 만든 임시 설정 — ERP 저장소에는 남지 않는다.

`stay_screen_dictionary` 는 장고 테스트 클라이언트로 화면을 열기 때문에 두 가지가 더 필요하다.
pytest 는 이 둘을 알아서 해 주지만 `manage.py` 로 그냥 돌리면 해 주는 사람이 없다.

- ALLOWED_HOSTS: 테스트 클라이언트는 호스트 이름이 `testserver` 다. 이것이 없으면 화면이
  400(DisallowedHost)으로 떨어져 사전이 한 줄도 나오지 않는다.
- TESTING: 로그인 신호가 `company_usersession` 행을 만들면서 접속 IP 를 넣는데, 테스트
  클라이언트의 가짜 로그인에는 IP 가 없어 `Column 'ip' cannot be null` 로 멈춘다.
"""

from {base} import *  # noqa: F401,F403

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
TESTING = True
'''

PROG = "sync_screen_dictionary"


# --------------------------------------------------------------------------
# 화면 출력 도우미 (convert_contract.py 와 같은 규칙)
# --------------------------------------------------------------------------

def _setup_streams() -> None:
    """한글이 깨지지 않도록 출력 인코딩을 UTF-8 로 맞춘다."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass


def _log(message: str) -> None:
    """진행 상황·경고를 표준오류로 알린다."""
    print(message, file=sys.stderr, flush=True)


def _fail(message: str) -> NoReturn:
    _log(f"{PROG}: {message}")
    sys.exit(1)


# --------------------------------------------------------------------------
# ERP 저장소 찾기
# --------------------------------------------------------------------------

def _resolve_basecamp(raw: str) -> Path:
    """`--basecamp` 가 정말 ERP 저장소인지 본다 — `manage.py` 와 Stay 관리 명령이 있어야 한다."""
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        _fail(f"ERP 저장소 폴더가 없습니다: {root}")
    if not (root / "manage.py").is_file():
        _fail(f"`manage.py` 가 없습니다 — ERP(basecamp) 저장소 최상위를 주세요: {root}")
    command = root / "stay" / "management" / "commands" / "stay_screen_dictionary.py"
    if not command.is_file():
        _fail(
            "이 저장소에는 `stay_screen_dictionary` 관리 명령이 없습니다 "
            f"(찾은 자리: {command}). ERP 를 최신으로 받아 주세요."
        )
    return root


def _resolve_python(raw: str | None, basecamp: Path) -> str:
    """돌릴 파이썬을 정한다 — 기본은 ERP 저장소의 가상환경이다."""
    if raw:
        python = Path(raw).expanduser()
        if not python.is_file():
            _fail(f"파이썬 실행 파일이 없습니다: {python}")
        return str(python)
    for venv in (basecamp / ".venv" / "bin" / "python",
                 basecamp / ".venv" / "Scripts" / "python.exe"):   # 윈도우 가상환경
        if venv.is_file():
            return str(venv)
    _log(
        f"{PROG}: 알림 — ERP 저장소에 `.venv` 가 없어 지금 파이썬으로 돌립니다. "
        "장고가 없다고 나오면 `--python <ERP 가상환경의 python>` 을 주세요."
    )
    return sys.executable


# --------------------------------------------------------------------------
# 관리 명령 돌리기
# --------------------------------------------------------------------------

def _write_shim(directory: Path, base_settings: str) -> Path:
    """임시 설정 모듈을 만들어 그 폴더를 돌려준다(PYTHONPATH 에 얹는다)."""
    path = directory / f"{SHIM_MODULE}.py"
    path.write_text(SHIM_SOURCE.format(base=base_settings), encoding="utf-8")
    return path


def _env_for(basecamp: Path, shim_dir: Path, settings_module: str) -> dict:
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = settings_module
    env["PYTHONPATH"] = os.pathsep.join(
        [str(shim_dir), str(basecamp), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])]
    )
    return env


def _run(cmd: list, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True)
    except OSError as exc:
        _fail(f"명령을 시작하지 못했습니다 ({exc.__class__.__name__}: {exc}).")


def _report_database(python: str, basecamp: Path, env: dict) -> None:
    """어느 DB 를 보고 도는지 한 줄로 알린다 — 운영·스테이지를 향해 돌리는 사고를 막는다."""
    probe = (
        "import django; django.setup();"
        "from django.conf import settings as s;"
        "d = s.DATABASES['default'];"
        "print(f\"{d.get('HOST') or 'localhost'}:{d.get('PORT') or ''}/{d.get('NAME')}\")"
    )
    done = _run([python, "-c", probe], cwd=basecamp, env=env)
    if done.returncode != 0:
        _log(f"{PROG}: 장고를 띄우지 못했습니다 — ERP 저장소의 `.env` 와 설정 모듈을 확인하세요.")
        _log(_tail(done.stderr))
        sys.exit(1)
    target = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else "(모름)"
    _log(f"{PROG}: 설정 {env['DJANGO_SETTINGS_MODULE']} · DB {target}")


def _tail(text: str, lines: int = 25) -> str:
    kept = [line for line in text.splitlines() if line.strip()][-lines:]
    return "\n".join(kept)


def _interesting(text: str) -> list:
    """관리 명령이 사람에게 한 말만 고른다 — 장고 요청 로그(JSON 한 줄)는 버린다."""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("{"):
            continue
        out.append(line.rstrip())
    return out


def _generate(python: str, basecamp: Path, env: dict, out_dir: Path, generated_on: str | None,
              check: bool) -> subprocess.CompletedProcess:
    cmd = [python, "manage.py", "stay_screen_dictionary", "--out", str(out_dir)]
    if generated_on:
        cmd += ["--generated-on", generated_on]
    if check:
        cmd.append("--check")
    _log(f"{PROG}: {' '.join(cmd[1:])} …")
    return _run(cmd, cwd=basecamp, env=env)


def _explain_failure(done: subprocess.CompletedProcess, log_dir: Path) -> NoReturn:
    """실패한 실행의 흔적을 파일로 남기고 끝을 보여 준다 — 로그가 길어 화면에 다 못 싣는다."""
    log_path = log_dir / "stay_screen_dictionary.log"
    try:
        log_path.write_text(
            (done.stdout or "") + "\n----- stderr -----\n" + (done.stderr or ""), encoding="utf-8"
        )
        where = f"전체 기록: {log_path}"
    except OSError:
        where = "(기록을 남기지 못했습니다)"
    _log(f"{PROG}: 관리 명령이 실패했습니다 (종료 코드 {done.returncode}).")
    _log(_tail(done.stderr or done.stdout or ""))
    _log(where)
    sys.exit(1)


# --------------------------------------------------------------------------
# 본체
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    _setup_streams()
    ap = argparse.ArgumentParser(
        prog=PROG,
        description="ERP 화면 마크업에서 화면 사전(screen-dictionary.json/.md)을 다시 받아 온다.",
    )
    ap.add_argument("--basecamp", required=True,
                    help="ERP(basecamp) 저장소 최상위 경로 (사람마다 다르므로 반드시 준다)")
    ap.add_argument("-o", "--out", default=None,
                    help=f"두 파일을 쓸 폴더 (기본: {REFERENCES_DIR})")
    ap.add_argument("--python", default=None,
                    help="ERP 를 돌릴 파이썬 (기본: <basecamp>/.venv/bin/python)")
    ap.add_argument("--settings", default=DEFAULT_SETTINGS,
                    help=f"딛고 설 장고 설정 모듈 (기본: {DEFAULT_SETTINGS} — 로컬 개발 DB)")
    ap.add_argument("--generated-on", default=None,
                    help="사전에 박을 날짜 (기본: 오늘). 두 번 돌려 같은 파일인지 볼 때만 준다")
    ap.add_argument("--check", action="store_true",
                    help="덮어쓰지 않고 지금 사전이 화면과 같은지만 본다 (다르면 종료 코드 1)")
    args = ap.parse_args(argv)

    basecamp = _resolve_basecamp(args.basecamp)
    python = _resolve_python(args.python, basecamp)
    target_dir = Path(args.out).expanduser().resolve() if args.out else REFERENCES_DIR

    with tempfile.TemporaryDirectory(prefix="stay-dict-") as tmp:
        tmp_dir = Path(tmp)
        _write_shim(tmp_dir, args.settings)
        env = _env_for(basecamp, tmp_dir, SHIM_MODULE)
        _report_database(python, basecamp, env)

        if args.check:
            done = _generate(python, basecamp, env, target_dir, args.generated_on, check=True)
            for line in _interesting(done.stdout) + _interesting(done.stderr):
                _log(f"  {line.strip()}")
            if done.returncode != 0:
                _log(f"{PROG}: 사전이 화면과 다릅니다 — `--check` 없이 다시 돌려 받으세요.")
                return 1
            _log(f"{PROG}: 사전이 화면과 같습니다.")
            return 0

        fresh_dir = tmp_dir / "out"
        done = _generate(python, basecamp, env, fresh_dir, args.generated_on, check=False)
        if done.returncode != 0:
            _explain_failure(done, Path(tempfile.gettempdir()))

        for line in _interesting(done.stderr) + _interesting(done.stdout):
            _log(f"  {line.strip()}")

        missing = [name for name in FILE_NAMES if not (fresh_dir / name).is_file()]
        if missing:
            _fail("관리 명령이 파일을 만들지 않았습니다: " + " · ".join(missing))

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _fail(f"쓸 폴더를 만들지 못했습니다 ({exc.__class__.__name__}).")

        changed = []
        for name in FILE_NAMES:
            source = fresh_dir / name
            target = target_dir / name
            before = target.read_bytes() if target.is_file() else None
            after = source.read_bytes()
            try:
                shutil.copyfile(source, target)
            except OSError as exc:
                _fail(f"{name} 을 쓰지 못했습니다 ({exc.__class__.__name__}).")
            state = "그대로" if before == after else ("새 파일" if before is None else "바뀜")
            if before != after:
                changed.append(name)
            _log(f"{PROG}: {target} — {state} ({len(after):,} 바이트)")

    if changed:
        _log(
            f"{PROG}: 사전이 바뀌었습니다 — 화면 안내도 다시 만드세요: "
            "python3 scripts/render_screen_guide.py --no-font"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        _log(f"{PROG}: 사용자가 중단했습니다.")
        raise SystemExit(1) from None
