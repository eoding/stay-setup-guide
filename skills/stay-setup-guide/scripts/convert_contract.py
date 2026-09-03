#!/usr/bin/env python3
"""계약서 파일(엑셀·PDF·워드·한글)을 마크다운으로 바꾼다.

사용법:
    python3 convert_contract.py <입력파일> [-o 출력.md] [--sheet 시트이름]

-o 를 주지 않으면 결과를 화면(표준출력)으로 내보낸다.
필요한 변환 패키지는 처음 한 번 자동으로 설치한다.

종료 코드: 0 성공 / 1 변환 실패 / 2 사용법 오류
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

# 표·문서 계열 -> firecrawl-anydoc
ANYDOC_EXTS = {
    ".xlsx", ".xlsm", ".xls", ".ods", ".csv",
    ".pdf", ".docx", ".doc", ".pptx", ".odt", ".rtf", ".epub",
}
# 한글 문서 -> rhwp-python
HWP_EXTS = {".hwp", ".hwpx"}
# anydoc 이 안 될 때 openpyxl 로 대신 읽을 수 있는 형식
OPENPYXL_EXTS = {".xlsx", ".xlsm"}

ANYDOC_SPEC = "firecrawl-anydoc==0.2.4"
RHWP_SPEC = "rhwp-python==0.8.1"
OPENPYXL_SPEC = "openpyxl"

PROG = "convert_contract"


# --------------------------------------------------------------------------
# 화면 출력 도우미
# --------------------------------------------------------------------------

def _setup_streams() -> None:
    """한글이 깨지지 않도록 출력 인코딩을 UTF-8 로 맞춘다."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass


def _log(message: str) -> None:
    """진행 상황·경고를 표준오류로 알린다(결과물에는 섞이지 않는다)."""
    print(message, file=sys.stderr, flush=True)


def _fail(message: str) -> NoReturn:
    _log(f"{PROG}: {message}")
    sys.exit(1)


# --------------------------------------------------------------------------
# 패키지 자동 설치
# --------------------------------------------------------------------------

def _run(cmd: list) -> bool:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True)
    except Exception:
        return False
    return done.returncode == 0


def _install_attempts(spec: str) -> list:
    """설치 명령 후보를 순서대로 만든다.

    표준 pip 이 우선이고, pip 이 없는 환경(uv 로 만든 가상환경 등)을 위해
    uv 와 ensurepip 경로를 뒤에 둔다.
    """
    pip_base = [sys.executable, "-m", "pip", "install",
                "--quiet", "--disable-pip-version-check"]
    attempts = [
        pip_base + [spec],
        pip_base + ["--user", spec],
    ]
    uv = shutil.which("uv")
    if uv:
        attempts.append([uv, "pip", "install", "--python", sys.executable, spec])
    return attempts


def _ensure(module_name: str, spec: str, *, label: str):
    """모듈을 불러오고, 없으면 한 번 설치한 뒤 다시 불러온다.

    성공하면 모듈 객체를, 끝내 실패하면 None 을 돌려준다.
    """
    module = _try_import(module_name)
    if module is not None:
        return module

    _log(f"처음 한 번 {label} 설치 중…")

    for cmd in _install_attempts(spec):
        if _run(cmd):
            break
    else:
        # pip 자체가 없는 환경이면 pip 을 깔고 한 번 더 시도한다.
        if _run([sys.executable, "-m", "ensurepip", "--default-pip"]):
            _run([sys.executable, "-m", "pip", "install",
                  "--quiet", "--disable-pip-version-check", spec])

    _refresh_import_paths()
    return _try_import(module_name)


def _try_import(module_name: str):
    import importlib

    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        if module_name == "rhwp" and _repair_hwp_runtime(exc):
            try:
                return importlib.import_module(module_name)
            except Exception:
                return None
        return None
    except Exception:
        return None


def _refresh_import_paths() -> None:
    """방금 설치한 패키지를 같은 실행 안에서 바로 불러올 수 있게 한다."""
    import importlib
    import site

    try:
        user_site = site.getusersitepackages()
    except Exception:
        user_site = None
    if isinstance(user_site, str) and user_site not in sys.path:
        sys.path.append(user_site)
    importlib.invalidate_caches()


def _repair_hwp_runtime(exc: ImportError) -> bool:
    """한글 문서 패키지가 딸려 온 글꼴 라이브러리 때문에 안 열릴 때 손본다.

    리눅스 배포본에 따라 패키지에 동봉된 글꼴 라이브러리가 오래되어
    글자를 그리는 기능 하나가 빠져 있다. 시스템에 깔린 최신 글꼴
    라이브러리를 먼저 올려 두면 그대로 열린다.
    """
    text = str(exc)
    if "undefined symbol" not in text or "FT_" not in text:
        return False
    if not sys.platform.startswith("linux"):
        return False

    import ctypes

    for name in ("libfreetype.so.6", "libfreetype.so"):
        try:
            ctypes.CDLL(name, mode=ctypes.RTLD_GLOBAL)
            return True
        except OSError:
            continue
    return False


def _install_hint(label: str, spec: str) -> NoReturn:
    _log(f"{PROG}: {label} 를 설치하지 못했습니다. 인터넷 연결을 확인한 뒤 "
         "아래 명령을 직접 실행해 주세요.")
    _log(f'  "{sys.executable}" -m pip install {spec}')
    if shutil.which("uv"):
        _log(f'  uv pip install --python "{sys.executable}" {spec}')
    sys.exit(1)


# --------------------------------------------------------------------------
# 변환 경로 1 — anydoc (엑셀·PDF·워드 등)
# --------------------------------------------------------------------------

def _anydoc_error_message(exc: Exception, module) -> str:
    """anydoc 예외를 사람이 읽는 한 줄로 바꾼다."""
    pairs = [
        ("EncryptedError",
         "암호가 걸린 파일입니다. 암호를 풀고 다시 저장한 뒤 시도해 주세요."),
        ("NeedsOcrError",
         "글자가 없는 이미지 문서입니다. 글자가 들어간 파일로 다시 받아 주세요."),
        ("MissingPartError",
         "파일이 일부 손상되었습니다. 원본을 다시 받아 주세요."),
        ("MalformedError", "파일 내용을 읽을 수 없습니다. 원본을 다시 받아 주세요."),
        ("ResourceLimitError", "파일이 너무 커서 변환하지 못했습니다."),
        ("UnsupportedError", "이 파일 형식은 변환할 수 없습니다."),
    ]
    for attr, message in pairs:
        cls = getattr(module, attr, None)
        if isinstance(cls, type) and isinstance(exc, cls):
            return message
    return f"변환에 실패했습니다 ({exc.__class__.__name__})."


class _InstallFailed(Exception):
    """필요한 패키지를 깔지 못했다."""


class _ConvertFailed(Exception):
    """패키지는 있는데 이 파일을 변환하지 못했다."""


def _convert_with_anydoc(path: Path) -> str:
    module = _ensure("anydoc", ANYDOC_SPEC, label="문서 변환 패키지")
    if module is None:
        raise _InstallFailed("문서 변환 패키지를 설치하지 못했습니다.")
    try:
        return module.to_markdown(str(path))
    except Exception as exc:
        raise _ConvertFailed(_anydoc_error_message(exc, module)) from exc


# --------------------------------------------------------------------------
# 변환 경로 2 — openpyxl (엑셀 예비 경로)
# --------------------------------------------------------------------------

def _cell_text(value) -> str:
    """셀 값을 사람이 읽는 표기로 바꾼다(반올림하지 않는다)."""
    import datetime as dt

    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return ""
        if value.is_integer() and abs(value) < 1e16:
            return str(int(value))
        text = repr(value)
        if "e" in text or "E" in text:
            text = f"{value:f}".rstrip("0").rstrip(".")
        return text
    if isinstance(value, dt.datetime):
        if value.hour or value.minute or value.second:
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return value.strftime("%Y-%m-%d")
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, dt.time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, dt.timedelta):
        return str(value)
    return str(value)


def _escape(text: str) -> str:
    """표 안에서 줄바꿈·세로줄·물결표가 표를 깨지 않게 손본다."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join(part.strip() for part in text.split("\n") if part.strip())
    text = text.replace("|", "\\|").replace("~", "\\~")
    return text.strip()


def _hidden_rows(worksheet) -> set:
    """숨긴 행 번호. 만료된 옛 요금 구간이 여기 숨어 있는 경우가 많다."""
    hidden = set()
    for number, dimension in getattr(worksheet, "row_dimensions", {}).items():
        if getattr(dimension, "hidden", False):
            hidden.add(number)
    return hidden


def _hidden_columns(worksheet) -> set:
    """숨긴 열의 번호(1부터). 한 묶음이 여러 열에 걸칠 수 있다."""
    hidden = set()
    for dimension in getattr(worksheet, "column_dimensions", {}).values():
        if not getattr(dimension, "hidden", False):
            continue
        first = getattr(dimension, "min", None)
        last = getattr(dimension, "max", None)
        if first and last:
            hidden.update(range(int(first), int(last) + 1))
    return hidden


def _sheet_to_rows(worksheet) -> list:
    """시트를 문자열 표로 만들고 숨긴 줄과 빈 행·빈 열을 걷어낸다."""
    skip_rows = _hidden_rows(worksheet)
    skip_cols = _hidden_columns(worksheet)

    rows = []
    for number, raw in enumerate(worksheet.iter_rows(values_only=True), start=1):
        if number in skip_rows:
            continue
        rows.append([
            _escape(_cell_text(value))
            for index, value in enumerate(raw, start=1)
            if index not in skip_cols
        ])
    if not rows:
        return []

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    rows = [r for r in rows if any(cell for cell in r)]
    if not rows:
        return []

    keep = [i for i in range(width) if any(r[i] for r in rows)]
    return [[r[i] for i in keep] for r in rows]


def _rows_to_table(rows: list) -> str:
    header, *body = rows
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _convert_with_openpyxl(path: Path) -> str:
    module = _ensure("openpyxl", OPENPYXL_SPEC, label="엑셀 읽기 패키지")
    if module is None:
        _install_hint("엑셀 읽기 패키지", OPENPYXL_SPEC)

    try:
        book = module.load_workbook(str(path), data_only=True)
    except Exception as exc:
        _fail(f"엑셀 파일을 열지 못했습니다 ({exc.__class__.__name__}).")

    sections = []
    for worksheet in book.worksheets:
        if getattr(worksheet, "sheet_state", "visible") != "visible":
            continue
        rows = _sheet_to_rows(worksheet)
        if not rows:
            continue
        title = str(worksheet.title).strip() or "시트"
        sections.append(f"## {title}\n\n{_rows_to_table(rows)}")

    if not sections:
        _fail("엑셀 파일에서 읽을 내용을 찾지 못했습니다. "
              "값이 비어 있는지 확인해 주세요.")
    return "\n\n".join(sections)


# --------------------------------------------------------------------------
# 변환 경로 3 — rhwp (한글 문서)
# --------------------------------------------------------------------------

def _convert_with_rhwp(path: Path) -> str:
    module = _ensure("rhwp", RHWP_SPEC, label="한글 문서 패키지")
    if module is None:
        _install_hint("한글 문서 패키지", RHWP_SPEC)

    try:
        document = module.parse(str(path))
    except FileNotFoundError:
        _fail("파일을 찾을 수 없습니다.")
    except PermissionError:
        _fail("파일을 열 권한이 없습니다.")
    except Exception as exc:
        _fail(f"한글 문서를 열지 못했습니다 ({exc.__class__.__name__}).")

    try:
        return document.to_ir().to_markdown()
    except Exception:
        _log(f"{PROG}: 경고 — 표를 표 모양으로 옮기지 못해 글자만 뽑았습니다.")

    try:
        text = document.extract_text()
    except Exception as exc:
        _fail(f"한글 문서 내용을 읽지 못했습니다 ({exc.__class__.__name__}).")

    if not text.strip():
        _fail("한글 문서에서 읽을 내용을 찾지 못했습니다.")
    return text


# --------------------------------------------------------------------------
# 시트 하나만 남기기
# --------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return "".join(text.split()).lower()


def _select_sheet(markdown: str, wanted: str) -> str:
    lines = markdown.splitlines()
    heads = [i for i, line in enumerate(lines) if line.startswith("## ")]
    if not heads:
        _log(f"{PROG}: 경고 — 시트가 하나뿐이라 --sheet 를 건너뛰고 전체를 내보냅니다.")
        return markdown

    titles = [lines[i][3:].strip() for i in heads]
    picked = None
    for index, title in enumerate(titles):
        if title == wanted:
            picked = index
            break
    if picked is None:
        for index, title in enumerate(titles):
            if _normalize(title) == _normalize(wanted):
                picked = index
                break
    if picked is None:
        loose = [i for i, t in enumerate(titles) if _normalize(wanted) in _normalize(t)]
        if len(loose) == 1:
            picked = loose[0]
    if picked is None:
        _fail(f"'{wanted}' 시트를 찾지 못했습니다. 들어 있는 시트: "
              + ", ".join(titles))

    start = heads[picked]
    end = heads[picked + 1] if picked + 1 < len(heads) else len(lines)
    return "\n".join(lines[start:end]).rstrip()


# --------------------------------------------------------------------------
# 본체
# --------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"{PROG}.py",
        description="계약서 파일(엑셀·PDF·워드·한글)을 마크다운으로 바꿉니다.",
    )
    parser.add_argument("input", help="바꿀 계약서 파일")
    parser.add_argument("-o", "--output",
                        help="저장할 마크다운 파일 (없으면 화면에 출력)")
    parser.add_argument("--sheet", help="엑셀에서 이 시트 하나만 남깁니다")
    parser.add_argument("--force-openpyxl", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list) -> int:
    _setup_streams()
    args = _build_parser().parse_args(argv)

    source = Path(args.input).expanduser()
    if not source.exists():
        _fail("파일을 찾을 수 없습니다. 경로를 다시 확인해 주세요.")
    if not source.is_file():
        _fail("폴더가 아니라 파일을 지정해 주세요.")

    suffix = source.suffix.lower()
    if suffix in HWP_EXTS:
        markdown = _convert_with_rhwp(source)
        route = "rhwp"
    elif suffix in ANYDOC_EXTS:
        if args.force_openpyxl:
            if suffix not in OPENPYXL_EXTS:
                _fail("예비 경로는 .xlsx / .xlsm 파일에만 쓸 수 있습니다.")
            markdown = _convert_with_openpyxl(source)
            route = "openpyxl"
        else:
            try:
                markdown = _convert_with_anydoc(source)
                route = "anydoc"
            except (_InstallFailed, _ConvertFailed) as exc:
                if suffix not in OPENPYXL_EXTS:
                    if isinstance(exc, _InstallFailed):
                        _install_hint("문서 변환 패키지", ANYDOC_SPEC)
                    _fail(str(exc))
                _log(f"{PROG}: 알림 — 기본 변환이 안 되어 예비 경로로 다시 시도합니다.")
                markdown = _convert_with_openpyxl(source)
                route = "openpyxl"
    else:
        _fail(f"지원하지 않는 형식입니다 ({suffix or '확장자 없음'}).")

    if args.sheet:
        markdown = _select_sheet(markdown, args.sheet)

    if not markdown.strip():
        _fail("변환 결과가 비어 있습니다. 파일에 내용이 있는지 확인해 주세요.")

    header = f"<!-- converted by convert_contract.py: {source.name} ({route}) -->"
    result = f"{header}\n\n{markdown.strip()}\n"

    if args.output:
        target = Path(args.output).expanduser()
        try:
            if target.parent and not target.parent.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(result, encoding="utf-8", newline="\n")
        except OSError as exc:
            _fail(f"결과를 저장하지 못했습니다 ({exc.__class__.__name__}).")
    else:
        sys.stdout.write(result)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        _log(f"{PROG}: 사용자가 중단했습니다.")
        raise SystemExit(1) from None
