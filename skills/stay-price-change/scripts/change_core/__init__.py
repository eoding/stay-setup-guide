"""change_core — 어딩 Stay 변경 도우미들이 같이 쓰는 부분: 장부, 규칙 표, 낡음 확인, 되돌리기 계산, 페이지 틀.

가격 칸(`price_cell`)이 이 패키지를 쓰는 첫 종류다. 부과금·프로모션 할인·부가옵션 금액 도우미는 자기 항목 종류와
키·필드를 정해 같은 장부에 적고 같은 계산을 쓴다. 이 패키지는 가격 칸을 모른다 — 항목은 (종류, 키, 필드) → 값이고,
키는 `items.item_key` 로 굳힌 글자다. 다른 스킬에서는 플러그인 안의 상대 경로로 부른다:

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "stay-price-change" / "scripts"))
    from change_core.ledger import Ledger

    money     통화 자릿수와 반올림, 금액 글자 ↔ Decimal
    items     항목 값 모양(ItemState · Reading), 키 굳히기, 낡음 확인(stale_items)
    rules     판정 규칙 표(RuleTable)와 빨간 줄 고르기(decide)
    rollback  되돌리기 계산(plan_rollback) — 그대로인 항목만 돌리고 나머지는 까닭을 단다
    ledger    담당자 PC 의 SQLite 장부
    chrome    HTML 페이지 틀(색·글꼴·머리 숫자·저장 단계 목록·멈춤 선택지·그대로 두는 항목 표)
"""
