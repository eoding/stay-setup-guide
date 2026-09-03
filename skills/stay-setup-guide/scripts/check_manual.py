#!/usr/bin/env python3
"""check_manual.py — 입력 지시서(manual.md) 형식 검사.

references/MANUAL-SPEC.md 의 규칙을 기계적으로 확인한다:
- 단계(## 제목) 수 = 저장/추가 버튼(→ [...]) 수
- 단계 번호가 1부터 끊기지 않고 연속
- 금지어 0 (내부 용어가 새어 들어갔는지)
- 원문자(①②...) 0
- 시트 좌표로 보이는 토큰(B46 같은) 0
- 절대 경로(/home/...) 0
- `폴더:` 줄이 `폴더: <공유 폴더명>/사진` 형식과 일치(--share-name 을 준 경우)
- 사진 단계에서 참조한 파일명이 실제 사진 폴더에 있는지(--photos 를 준 경우)
- 0단계(1·2·3 단계가 각각 환율 확인 · 거래처 확인 · 도시 확인)가 있는지
- 표의 칸 이름이 화면 사전(screen-dictionary.json)에 있는지
- 값에 나오는 금액이 계약서에 있는 숫자인지(--contract 를 준 경우, 경고만)

사용법:
    python3 check_manual.py <manual.md> [--photos DIR] [--share-name NAME]
                            [--dictionary screen-dictionary.json] [--contract contract.md]

--photos 를 생략하면 사진 존재 확인은 건너뛴다.
--share-name 을 생략하면 `폴더:` 줄 형식 확인은 건너뛴다(줄 목록만 보여준다).
--dictionary 를 생략하면 스크립트 옆의 ../references/screen-dictionary.json 을 쓴다(없으면 건너뛴다).
--contract 를 생략하면 금액 대조는 건너뛴다.
"""
import argparse
import decimal
import json
import os
import re
import sys

# 지시서에 나오면 안 되는 내부 작업 용어 (회사·사람 이름은 계약서에서 온 값이면 표 안에서는 허용되므로
# 여기 포함하지 않는다 — 값 자체의 정당성은 사람이 판단한다)
FORBIDDEN = [
    "QA", "담당자", "확인 필요", "임시값", "위와 같이", "근거", "기대값", "<!--", "/home/",
]

CIRCLED = re.compile(r"[①-⑳]")
# 시트 좌표(B46 같은) 의심 토큰. 통화·요금제 코드(USD, VND, KRW, HB, FB, BB, D-14 등)는 오탐이라 뺀다.
CELL = re.compile(r"(?<![A-Za-z0-9])[A-Z]{1,2}\d{1,3}(?![A-Za-z0-9])")
CELL_EXCLUDE = re.compile(r"^(D|HB|FB|BB|USD|VND|KRW)\d")
ROW = re.compile(r"^\| ([^|]+) \| ([^|]+) \|$")
STEP_RE = re.compile(r"^## (\d+)\.")
STEP_TITLE_RE = re.compile(r"^## (\d+)\.\s*(.*)$")
FILE_REF_RE = re.compile(r"\b((?:hotel|room|offer)_[A-Za-z0-9_\-]+\.(?:jpe?g|png))", re.IGNORECASE)
# 사진 목록 줄의 출처: `- hotel_01.jpg — 출처: https://...` (출처는 선택)
PHOTO_SRC_RE = re.compile(
    r"^\s*-\s*(?P<name>[\w][\w.\-]*\.(?:jpe?g|png))\s*[\u2014\u2013-]+\s*출처\s*:\s*(?P<url>\S+)\s*$",
    re.IGNORECASE,
)
HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# 0단계 — 호텔을 만들기 전에 반드시 먼저 보는 세 화면. 제목에 이 낱말이 들어 있으면 통과한다
# (`환율 등록 확인` 처럼 말이 붙어도 되게 부분 일치로 본다)
ZERO_STEPS = ["환율", "거래처", "도시"]

# 칸 이름 뒤에 붙는 통화 꼬리표는 화면 사전과 표기가 달라 떼고 비교한다
CURRENCY_SUFFIX_RE = re.compile(r"\s*\((?:[A-Z]{3}|공급 통화)\)")

# 금액이 아닌 숫자 칸(개수·연도·인원·전화·좌표·우선순위)
NOT_MONEY_FIELD_RE = re.compile(r"(객실 수|개수|연도|인원|전화|위도|경도|우선순위|층|번호|수량|박\)|D-N)")

# 반복 행 이름은 `<그룹> N · <열 이름>` 형식 — 사전과는 열 이름으로 대조한다
REPEAT_PREFIX_RE = re.compile(r"^.+? \d+ · ")

# 상품 공통 화면의 칸이라 화면 사전이 일부러 담지 않는 이름 — 대조에서 통과시킨다
DICT_EXEMPT = {"상품명"}

# 금액이 아닌 숫자(날짜·시각·좌표·면적)는 대조에서 뺀다
DATE_RE = re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")
TIME_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?")
COORD_RE = re.compile(r"\d+\.\d{6,}")
AREA_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*㎡")
# 전화번호 — `+` 로 시작하거나 하이픈으로 이어 붙인 숫자 묶음 (+84-297-0000000, 02-123-4567)
PHONE_RE = re.compile(r"\+?\d{1,4}(?:-\d{2,8}){2,5}")
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def norm_field(name):
    """칸 이름 비교용 정규화 — 통화 꼬리표 제거 + 공백 정리."""
    return re.sub(r"\s+", " ", CURRENCY_SUFFIX_RE.sub("", name)).strip()


def strip_repeat_prefix(name):
    """`구간 1 · 수수료 값` → `수수료 값`. 반복 행이 아니면 그대로."""
    return REPEAT_PREFIX_RE.sub("", name, count=1).strip()


def load_dictionary(path):
    """화면 사전에서 필드 label · screen_label 과 반복 행의 columns 를 모은다."""
    data = json.load(open(path, encoding="utf-8"))
    labels = set()
    for screen in data.get("screens") or []:
        for block in screen.get("blocks") or []:
            for field in block.get("fields") or []:
                for key in ("label", "screen_label"):
                    value = field.get(key)
                    if value:
                        labels.add(norm_field(value))
                # 체크박스 칸은 지시서에서 `<칸 이름> · <체크박스 문구>` 로도 쓴다
                checkbox_text = field.get("checkbox_text")
                if checkbox_text:
                    for key in ("label", "screen_label"):
                        value = field.get(key)
                        if value:
                            labels.add(norm_field(f"{value} · {checkbox_text}"))
                # 반복 행 필드가 열 이름 목록을 들고 있으면 그것도 허용한다(아직 없는 사전이면 무시)
                for column in field.get("columns") or []:
                    if isinstance(column, str):
                        labels.add(norm_field(column))
                    elif isinstance(column, dict):
                        for key in ("label", "screen_label"):
                            value = column.get(key)
                            if value:
                                labels.add(norm_field(value))
    return labels


def norm_num(token):
    """숫자 토큰을 비교용 표준형으로. 실패하면 None."""
    try:
        return format(decimal.Decimal(token.replace(",", "")).normalize(), "f")
    except (decimal.InvalidOperation, ValueError):
        return None


def amounts_in(text, min_digits=3):
    """금액으로 볼 만한 숫자만 뽑는다 — 날짜·시각·좌표·면적·전화번호 제외, 3자리 이상이거나 소수."""
    cleaned = text
    for pat in (DATE_RE, PHONE_RE, TIME_RE, COORD_RE, AREA_RE):
        cleaned = pat.sub(" ", cleaned)
    found = []
    for m in NUM_RE.finditer(cleaned):
        token = m.group(0)
        whole = token.split(".")[0].replace(",", "")
        if len(whole) < min_digits and "." not in token:
            continue
        key = norm_num(token)
        if key:
            found.append((key, token))
    return found


def check(md_path, photos_dir=None, share_name=None, dictionary_path=None, contract_path=None):
    lines = open(md_path, encoding="utf-8").read().splitlines()
    text = "\n".join(lines)

    steps = [l for l in lines if l.startswith("## ")]
    saves = [l for l in lines if l.startswith("→ [")]

    rows = [ROW.match(l) for l in lines if ROW.match(l)]
    rows = [(m.group(1).strip(), m.group(2).strip()) for m in rows if m.group(1).strip() not in ("칸", "---")]
    kinds = {"입력": 0, "선택": 0, "체크": 0, "해제": 0, "비움": 0, "자동": 0, "파일": 0, "괄호": 0}
    for _, v in rows:
        if v.startswith("선택:"):
            kinds["선택"] += 1
        elif v == "체크":
            kinds["체크"] += 1
        elif v == "해제":
            kinds["해제"] += 1
        elif v.startswith("비움"):
            kinds["비움"] += 1
        elif v.startswith("자동 입력됨"):
            kinds["자동"] += 1
        elif v.startswith("파일:"):
            kinds["파일"] += 1
        elif v.startswith("(") and v.endswith(")"):
            kinds["괄호"] += 1
        else:
            kinds["입력"] += 1

    forb = {w: text.count(w) for w in FORBIDDEN if text.count(w)}
    circled = len(CIRCLED.findall(text))
    cells = [
        m.group(0)
        for l in lines if not l.startswith("```")
        for m in CELL.finditer(l)
        if not CELL_EXCLUDE.match(m.group(0))
    ]

    folders = [l for l in lines if l.startswith("폴더:")]
    bad_folder = []
    if share_name:
        expected = f"폴더: {share_name}/사진"
        bad_folder = [l for l in folders if l.strip() != expected]

    have = set()
    if photos_dir:
        if os.path.isdir(photos_dir):
            have = {f for f in os.listdir(photos_dir) if re.search(r"\.(jpe?g|png)$", f, re.I)}
    # 출처 URL 안의 파일명이 참조로 잡히지 않게 URL 부분은 떼고 찾는다
    ref_text = "\n".join(PHOTO_SRC_RE.sub(lambda m: f"- {m.group('name')}", l) for l in lines)
    referenced = set(FILE_REF_RE.findall(ref_text))
    bad_sources = [
        f"{m.group('name')} — {m.group('url')}"
        for m in (PHOTO_SRC_RE.match(l) for l in lines)
        if m and not HTTP_URL_RE.match(m.group("url"))
    ]
    missing_files = sorted(referenced - have) if photos_dir else []
    unused_files = sorted(have - referenced) if photos_dir else []

    nums = [int(m.group(1)) for l in steps for m in [STEP_RE.match(l)] if m]
    seq_ok = nums == list(range(1, len(nums) + 1))

    titles = {}
    for l in lines:
        m = STEP_TITLE_RE.match(l)
        if m:
            titles.setdefault(int(m.group(1)), m.group(2))
    zero_missing = [
        want for i, want in enumerate(ZERO_STEPS, start=1) if want not in titles.get(i, "")
    ]

    dict_error = None
    unknown_fields = []
    if dictionary_path:
        try:
            labels = load_dictionary(dictionary_path)
        except (OSError, ValueError) as e:
            dict_error = str(e)
        else:
            seen = []
            for name, _ in rows:
                n = norm_field(name)
                if not n or n in labels or n in DICT_EXEMPT or n in seen:
                    continue
                if strip_repeat_prefix(n) in labels:  # 반복 행은 열 이름으로 한 번 더 본다
                    continue
                seen.append(n)
            unknown_fields = seen

    contract_error = None
    loose_amounts = []
    if contract_path:
        try:
            contract_text = open(contract_path, encoding="utf-8").read()
        except OSError as e:
            contract_error = str(e)
        else:
            known = {key for key, _ in amounts_in(contract_text, min_digits=1)}
            seen_amounts = {}
            for name, v in rows:
                if "㎡" in name:  # 면적 칸은 값에 단위가 없다 — 칸 이름으로 걸러낸다
                    continue
                if NOT_MONEY_FIELD_RE.search(name):  # 개수·연도·인원·전화·좌표 칸은 금액이 아니다
                    continue
                for key, token in amounts_in(v):
                    if key not in known and key not in seen_amounts:
                        seen_amounts[key] = token
            loose_amounts = [seen_amounts[k] for k in sorted(seen_amounts, key=lambda x: decimal.Decimal(x))]

    return {
        "steps": len(steps), "saves": len(saves), "seq_ok": seq_ok, "rows": len(rows), "kinds": kinds,
        "forbidden": forb, "circled": circled, "sheet_cells": cells[:5],
        "folder_lines": len(folders), "bad_folder": bad_folder,
        "photos_checked": bool(photos_dir), "photos_have": len(have),
        "photos_missing": missing_files, "photos_unused": unused_files,
        "bad_sources": bad_sources,
        "zero_missing": zero_missing,
        "dict_checked": bool(dictionary_path), "dict_error": dict_error, "unknown_fields": unknown_fields,
        "contract_checked": bool(contract_path), "contract_error": contract_error,
        "loose_amounts": loose_amounts,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="입력 지시서(manual.md) 형식 검사")
    ap.add_argument("manual", help="검사할 manual.md 경로")
    ap.add_argument("--photos", default=None, help="사진 폴더 (선택 — 주면 파일 존재까지 확인)")
    ap.add_argument("--share-name", default=None, help="공유 폴더명 (선택 — 주면 `폴더:` 줄 형식까지 확인, 예: 우에노_토우가네야)")
    ap.add_argument("--dictionary", default=None,
                    help="화면 사전 JSON (선택 — 생략하면 ../references/screen-dictionary.json 을 자동으로 씀)")
    ap.add_argument("--contract", default=None, help="계약서 md (선택 — 주면 금액이 계약서에 있는지 경고로 알림)")
    ap.add_argument("--strict", action="store_true",
                    help="경고(사전에 없는 칸 이름 · 계약서에 없는 금액)를 실패로 다룬다")
    args = ap.parse_args(argv)

    if not os.path.exists(args.manual):
        print(f"파일 없음: {args.manual}")
        return 1

    dictionary = args.dictionary
    if dictionary is None:
        default_dict = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), os.pardir, "references", "screen-dictionary.json"
        )
        if os.path.exists(default_dict):
            dictionary = os.path.normpath(default_dict)

    r = check(args.manual, args.photos, args.share_name, dictionary, args.contract)

    problems = []
    if r["steps"] != r["saves"]:
        problems.append(f"단계 {r['steps']} ≠ 저장 {r['saves']}")
    if not r["seq_ok"]:
        problems.append("단계 번호 불연속")
    if r["forbidden"]:
        problems.append(f"금지어 {r['forbidden']}")
    if r["circled"]:
        problems.append(f"원문자 {r['circled']}")
    if r["sheet_cells"]:
        problems.append(f"좌표 의심 {r['sheet_cells']}")
    if r["bad_folder"]:
        problems.append(f"폴더 줄 이상 {r['bad_folder'][:2]}")
    if r["photos_missing"]:
        problems.append(f"없는 사진 참조 {r['photos_missing']}")
    if r["zero_missing"]:
        problems.append("0단계(환율·거래처·도시 확인) 누락")
    if r["dict_error"]:
        problems.append(f"화면 사전 읽기 실패 {r['dict_error']}")
    if r["contract_error"]:
        problems.append(f"계약서 읽기 실패 {r['contract_error']}")

    warnings = []
    if r["unknown_fields"]:
        shown = r["unknown_fields"][:15]
        msg = f"사전에 없는 칸 이름 {len(r['unknown_fields'])}개: {shown}"
        (problems if args.strict else warnings).append(msg)
    if r["bad_sources"]:
        warnings.append(f"사진 출처 형식 {len(r['bad_sources'])}개 (http(s):// 아님): {r['bad_sources'][:5]}")
    if r["loose_amounts"]:
        shown = r["loose_amounts"][:15]
        msg = f"계약서에 없는 금액 {len(r['loose_amounts'])}개: {shown}"
        (problems if args.strict else warnings).append(msg)

    k = r["kinds"]
    print(
        f"단계 {r['steps']} · 값 {r['rows']} "
        f"(입력 {k['입력']} 선택 {k['선택']} 체크 {k['체크']} 해제 {k['해제']} 비움 {k['비움']} 자동 {k['자동']} 파일 {k['파일']}) "
        f"· 폴더줄 {r['folder_lines']}"
    )
    if r["photos_checked"]:
        print(f"사진 {r['photos_have']}장 확인 (미사용 {len(r['photos_unused'])})")
    else:
        print("사진 폴더 미지정 — 파일 존재 확인 건너뜀 (--photos 로 지정)")
    if not args.share_name:
        print("공유 폴더명 미지정 — `폴더:` 줄 형식 확인 건너뜀 (--share-name 으로 지정)")
    if not r["dict_checked"]:
        print("화면 사전 없음 — 칸 이름 확인 건너뜀 (--dictionary 로 지정)")
    if not r["contract_checked"]:
        print("계약서 미지정 — 금액 대조 건너뜀 (--contract 로 지정)")

    for w in warnings:
        print(f"   ⚠ {w}")

    if problems:
        for p in problems:
            print(f"   ✗ {p}")
        print("문제 있음")
        return 1

    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
