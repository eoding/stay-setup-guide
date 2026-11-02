#!/usr/bin/env python3
"""sync_erp_fixtures.py — ERP 가 실제 템플릿으로 그린 화면 조각을 러너 시험 픽스처로 옮긴다.

basecamp 저장소가 Stay 드로어·탭 패널을 실제로 렌더해 `stay/tests/fixtures/html/` 에 커밋한다(조각 42개 +
`index.json`, 바이트 고정 — pk 는 `{offer:1}` 같은 자리표시). 러너 시험(`tests/test_erp_fixtures.mjs`)은 그 사본
`tests/fixtures/erp/` 를 jsdom 에 올려 돈다. 이 스크립트가 그 사본을 맞춘다 — **손으로 고치는 파일이 아니다.**

사용법:
    python3 sync_erp_fixtures.py --basecamp ~/src/basecamp            # 사본을 갈아 끼운다
    python3 sync_erp_fixtures.py --basecamp ~/src/basecamp --check    # 낡았는지만 본다(다르면 종료 코드 1)

`index.json` 에 적힌 파일만 옮기고, 사본에만 있는 파일은 지운다. 종료 코드: 0 같음·갱신 / 1 낡음·실패 / 2 사용법 오류.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE.parent / "tests" / "fixtures" / "erp"
SOURCE_IN_BASECAMP = Path("stay") / "tests" / "fixtures" / "html"
INDEX = "index.json"


def source_dir(basecamp) -> Path:
    return Path(basecamp).expanduser().resolve() / SOURCE_IN_BASECAMP


def listed(directory: Path) -> list:
    """`index.json` 이 적은 파일 이름(그 자신 포함)."""
    with open(directory / INDEX, encoding="utf-8") as handle:
        index = json.load(handle)
    return [INDEX] + [item["file"] for item in index.get("files") or []]


def differences(source: Path, target: Path) -> list:
    """사본이 원본과 다른 자리 — `[(파일, 사유)]`. 비었으면 같다."""
    out = []
    names = listed(source)
    for name in names:
        src, dst = source / name, target / name
        if not src.is_file():
            out.append((name, "원본 index.json 에 있는데 원본 파일이 없다"))
        elif not dst.is_file():
            out.append((name, "사본에 없다"))
        elif src.read_bytes() != dst.read_bytes():
            out.append((name, "내용이 다르다"))
    if target.is_dir():
        for extra in sorted(p.name for p in target.iterdir() if p.is_file() and p.name not in names):
            out.append((extra, "원본에 없는 파일이 사본에 있다"))
    return out


def sync(source: Path, target: Path) -> list:
    target.mkdir(parents=True, exist_ok=True)
    names = listed(source)
    for name in names:
        (target / name).write_bytes((source / name).read_bytes())
    removed = [p.name for p in target.iterdir() if p.is_file() and p.name not in names]
    for name in removed:
        (target / name).unlink()
    return names


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="sync_erp_fixtures", description="ERP 실제 렌더 조각 → 러너 시험 픽스처")
    ap.add_argument("--basecamp", required=True, help="ERP(basecamp) 저장소 최상위 경로")
    ap.add_argument("--check", action="store_true", help="덮어쓰지 않고 사본이 낡았는지만 본다")
    args = ap.parse_args(argv)
    source = source_dir(args.basecamp)
    if not (source / INDEX).is_file():
        print(f"sync_erp_fixtures: 원본이 없습니다 — {source / INDEX}", file=sys.stderr)
        return 1
    if args.check:
        diff = differences(source, TARGET)
        for name, why in diff:
            print(f"  {name}: {why}", file=sys.stderr)
        print(f"sync_erp_fixtures: 사본이 {'낡았습니다' if diff else '원본과 같습니다'} ({TARGET})", file=sys.stderr)
        return 1 if diff else 0
    names = sync(source, TARGET)
    print(f"sync_erp_fixtures: {len(names)}개 파일 → {TARGET}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
