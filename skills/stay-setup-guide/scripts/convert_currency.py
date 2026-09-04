#!/usr/bin/env python3
"""convert_currency.py — 입력 지시서(manual.md)의 공급 통화와 금액을 다른 통화로 바꾼다.

계약서 시트가 두 통화를 나란히 적어 두고(예: `Net(VND)` 와 `Net(USD)`) 한쪽이 다른 쪽을
고정 환율로 나눈 값일 때, 이미 만든 지시서를 다시 쓰지 않고 통화만 갈아끼운다.

바꾸는 것
1. `호텔 만들기` 단계의 `공급 통화 | 선택: <FROM>` → `선택: <TO>`
2. 금액 칸의 값 — `<FROM> 값 ÷ 환율`, 소수 <decimals> 자리에서 반올림(사사오입, ROUND_HALF_UP),
   천 단위 구분 없이 · 뒤따르는 0 없이 적는다 (137.176… → `137.18`, 5.00 → `5`)
   금액 칸:
     판매 단가(공급 통화) · 정가(취소선, 선택) · 공급 원가(net, 선택) · 판매가 · 정가 ·
     공급 원가 · 판매가(공급 통화) · 공급 원가(선택) · 정액 금액 (…) 값 · 금액 가치 (…) ·
     기준 요금제 대비 조정(선택) · 인원 조합별 조정(선택) · `단 N · 할인액` 같은 정액 프로모션 칸
   `기준 요금제 대비 조정(선택)`·`인원 조합별 조정(선택)` 은 `+1390000` 처럼 **절대 금액일 때만**
   바꾼다. `+24.5%` 같은 정률은 손대지 않는다.
3. 칸 이름 안의 통화 꼬리표 — `정액 금액 (VND) 값` → `정액 금액 (USD) 값`
4. 표가 아닌 줄의 `공급 통화 VND` → `공급 통화 USD`

손대지 않는 것
- 정률(%)·할인율·우선순위·인원·수량·날짜·시각·코드·좌표
- `선택:` · `체크` · `해제` · `비움` · `자동 입력됨 …` · `파일:` 로 시작하는 값
  (금액 칸이라도 값이 순수한 숫자가 아니면 건드리지 않는다)

사용법:
    python3 convert_currency.py <manual.md> --from VND --to USD --rate 25500 [--decimals 2]
                                [-o OUT.md] [--field "칸 이름"] [--dry-run]

`-o` 를 생략하면 입력 파일을 그 자리에서 고쳐 쓴다.
"""
import argparse
import decimal
import os
import re
import sys

# 표 한 줄: `| 칸 | 값 |`
ROW_RE = re.compile(r"^\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<value>[^|]*?)\s*\|\s*$")
# 칸 이름 꼬리의 통화 표기 — `(VND)` · `(공급 통화)`
CURRENCY_TAG_RE = re.compile(r"\(\s*(?:[A-Z]{3}|공급 통화)\s*\)")
# `단 1 · 할인액` 처럼 반복 행 번호가 앞에 붙은 칸 이름
REPEAT_PREFIX_RE = re.compile(r"^.+? \d+ · ")
# 순수한 금액 값 — 부호(선택) + 숫자(천 단위 구분 허용) + 소수(선택)
NUMBER_RE = re.compile(r"^(?P<sign>[+-]?)(?P<int>\d[\d,]*)(?P<frac>\.\d+)?$")

CURRENCY_FIELD = "공급 통화"

# 값이 금액인 칸 (칸 이름은 통화 꼬리표를 `(공급 통화)` 로 맞춘 뒤 비교한다)
MONEY_FIELDS = {
    "판매 단가(공급 통화)",
    "정가(취소선, 선택)",
    "공급 원가(net, 선택)",
    "판매가",
    "정가",
    "공급 원가",
    "판매가(공급 통화)",
    "공급 원가(선택)",
    "정액 금액 (공급 통화) 값",
    "금액 가치 (공급 통화)",
    "기준 요금제 대비 조정(선택)",
    "인원 조합별 조정(선택)",
}
# 위 목록에 없어도 이름만으로 금액이라고 볼 수 있는 칸 (프로모션 정액 단 등)
MONEY_LABEL_RE = re.compile(r"(정액 금액|금액 가치|할인액|할증액|추가 금액|금액 값)")

# 표가 아닌 줄에서 바꾸는 자리 — `공급 통화 VND`
FREE_TEXT_RE_TMPL = r"(공급 통화\s*)({cur})(?![A-Za-z])"


def canon_label(label):
    """칸 이름 비교용 — 통화 꼬리표를 `(공급 통화)` 로 맞추고 공백을 정리한다."""
    return re.sub(r"\s+", " ", CURRENCY_TAG_RE.sub("(공급 통화)", label)).strip()


def is_money_field(label, extra=()):
    """이 칸의 값이 금액인가."""
    canon = canon_label(label)
    if canon in MONEY_FIELDS or canon in extra:
        return True
    stripped = REPEAT_PREFIX_RE.sub("", canon, count=1).strip()
    if stripped in MONEY_FIELDS or stripped in extra:
        return True
    return bool(MONEY_LABEL_RE.search(canon))


def convert_amount(value, rate, decimals):
    """`+1390000` → `+54.51`. 순수한 숫자가 아니면 None(= 그대로 둔다)."""
    m = NUMBER_RE.match(value)
    if not m:
        return None
    raw = m.group("int").replace(",", "") + (m.group("frac") or "")
    try:
        amount = decimal.Decimal(raw)
    except decimal.InvalidOperation:
        return None
    with decimal.localcontext() as ctx:
        ctx.prec = 40
        quantum = decimal.Decimal(1).scaleb(-decimals)
        converted = (amount / decimal.Decimal(rate)).quantize(
            quantum, rounding=decimal.ROUND_HALF_UP
        )
    return m.group("sign") + format_amount(converted)


def format_amount(number):
    """천 단위 구분 없이, 뒤따르는 0 없이 — 137.18 · 5 · 0."""
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def rename_label(label, from_currency, to_currency):
    """`정액 금액 (VND) 값` → `정액 금액 (USD) 값`. 바뀐 게 없으면 원래 이름."""
    return re.sub(rf"\(\s*{re.escape(from_currency)}\s*\)", f"({to_currency})", label)


def convert_text(text, from_currency, to_currency, rate, decimals, extra_fields=()):
    """지시서 본문을 바꾸고 (새 본문, 요약) 을 돌려준다."""
    out = []
    per_field = {}          # 칸 이름 → 바꾼 값 개수
    renamed = {}            # 원래 칸 이름 → 새 칸 이름
    currency_rows = 0       # `공급 통화` 칸을 바꾼 횟수
    free_text = 0           # 표 밖 `공급 통화 VND` 를 바꾼 횟수
    samples = []            # (칸, 이전 값, 새 값) 앞 몇 개
    free_pat = re.compile(FREE_TEXT_RE_TMPL.format(cur=re.escape(from_currency)))

    for line in text.splitlines():
        m = ROW_RE.match(line)
        if not m:
            new_line, n = free_pat.subn(rf"\1{to_currency}", line)
            free_text += n
            out.append(new_line)
            continue

        label, value = m.group("label"), m.group("value")
        if label in ("칸",) or set(label) <= set("- :"):
            out.append(line)
            continue

        new_label = rename_label(label, from_currency, to_currency)
        if new_label != label:
            renamed[label] = new_label

        new_value = value
        if canon_label(label) == CURRENCY_FIELD:
            if value.strip() == f"선택: {from_currency}":
                new_value = f"선택: {to_currency}"
                currency_rows += 1
        elif is_money_field(label, extra_fields):
            converted = convert_amount(value, rate, decimals)
            if converted is not None and converted != value:
                new_value = converted
                per_field[label] = per_field.get(label, 0) + 1
                if len(samples) < 5:
                    samples.append((label, value, converted))

        if new_label == label and new_value == value:
            out.append(line)
        else:
            out.append(f"| {new_label} | {new_value} |")

    new_text = "\n".join(out)
    if text.endswith("\n"):
        new_text += "\n"
    summary = {
        "per_field": per_field,
        "renamed": renamed,
        "currency_rows": currency_rows,
        "free_text": free_text,
        "samples": samples,
        "total": sum(per_field.values()),
    }
    return new_text, summary


def print_summary(summary, from_currency, to_currency, rate, decimals, path):
    print(f"{path}: {from_currency} → {to_currency} (÷ {rate}, 소수 {decimals}자리 반올림)")
    if summary["currency_rows"]:
        print(f"  공급 통화 칸 {summary['currency_rows']}곳: 선택: {from_currency} → 선택: {to_currency}")
    else:
        print(f"  ⚠ `공급 통화 | 선택: {from_currency}` 줄을 찾지 못했다")
    for label in sorted(summary["per_field"], key=lambda x: (-summary["per_field"][x], x)):
        print(f"  {label}: {summary['per_field'][label]}개")
    print(f"  값 합계 {summary['total']}개")
    for old, new in sorted(summary["renamed"].items()):
        print(f"  칸 이름: `{old}` → `{new}`")
    if summary["free_text"]:
        print(f"  표 밖 `공급 통화 {from_currency}` {summary['free_text']}곳")
    for label, old, new in summary["samples"]:
        print(f"  예: {label} {old} → {new}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="입력 지시서의 공급 통화·금액을 다른 통화로 환산")
    ap.add_argument("manual", help="입력 지시서 manual.md 경로")
    ap.add_argument("--from", dest="from_currency", required=True, help="지금 통화 (예: VND)")
    ap.add_argument("--to", dest="to_currency", required=True, help="바꿀 통화 (예: USD)")
    ap.add_argument("--rate", required=True,
                    help="1 <to> 당 <from> 값 (예: 25500 — 값을 이 수로 나눈다)")
    ap.add_argument("--decimals", type=int, default=2, help="반올림할 소수 자리 (기본 2)")
    ap.add_argument("-o", "--output", default=None, help="출력 경로 (기본: 입력 파일을 그 자리에서 고침)")
    ap.add_argument("--field", action="append", default=[],
                    help="금액 칸을 더 알려준다 (여러 번 쓸 수 있다)")
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 요약만 보여준다")
    args = ap.parse_args(argv)

    if not os.path.exists(args.manual):
        print(f"파일 없음: {args.manual}")
        return 1
    try:
        rate = decimal.Decimal(str(args.rate).replace(",", ""))
    except decimal.InvalidOperation:
        print(f"환율을 읽을 수 없다: {args.rate}")
        return 1
    if rate <= 0:
        print("환율은 0보다 커야 한다")
        return 1
    if args.decimals < 0:
        print("소수 자리는 0 이상이어야 한다")
        return 1

    with open(args.manual, encoding="utf-8") as handle:
        text = handle.read()

    extra = {canon_label(f) for f in args.field}
    new_text, summary = convert_text(
        text, args.from_currency, args.to_currency, rate, args.decimals, extra
    )
    print_summary(summary, args.from_currency, args.to_currency, rate, args.decimals, args.manual)

    if args.dry_run:
        print("  (--dry-run — 파일을 쓰지 않았다)")
        return 0

    out_path = args.output or args.manual
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(new_text)
    print(f"  썼다: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
