"""change_core — 어딩 Stay 변경 도우미들이 같이 쓰는 부분: 장부, 규칙 표, 낡음 확인, 되돌리기 계산, 페이지 틀.

가격 칸(`price_cell`)이 이 패키지를 쓰는 첫 종류고, 부가옵션 가격 줄(`addon_price`)과 부과금(`charge`)이 뒤를 잇는다. 도우미마다 자기 항목 종류와
키·필드를 정해 같은 장부에 적고 같은 계산을 쓴다. 이 패키지는 가격 칸을 모른다 — 항목은 (종류, 키, 필드) → 값이고,
키는 `items.item_key` 로 굳힌 글자다. 다른 스킬에서는 플러그인 안의 상대 경로로 부른다:

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "stay-price-change" / "scripts"))
    from change_core.ledger import Ledger

    money     통화 자릿수와 반올림, 금액 글자 ↔ Decimal
    items     항목 값 모양(ItemState · Reading), 키 굳히기, 낡음 확인(stale_items)
    rules     판정 규칙 표(RuleTable)와 빨간 줄 고르기(decide)
    rollback  되돌리기 계산(plan_rollback) — 그대로인 항목만 돌리고 나머지는 까닭을 단다
    ledger    담당자 PC 의 SQLite 장부
    alive     장부의 저장된 값들을 차례로 따라 어느 기록의 값이 살아 있는지 · 되돌렸는지 · 다시 살렸는지 셈한다(ledger 가 쓴다)
    chrome    HTML 페이지 틀(색·글꼴·머리 숫자·저장 단계 목록·멈춤 선택지·그대로 두는 항목 표)
    window    편집 창을 통째로 다시 저장하는 화면의 저장 한 걸음(읽은 칸 그대로 + 짚은 금액 칸만 새 값)과 적용 뒤 견주기
    names     이름 · 설명에 적힌 바꾸기 전 값 — 도우미는 이름을 바꾸지 않으므로 미리보기와 결과가 알린다(우연히 같은 숫자는 빼고)
    files     기록 폴더의 파일 — 결과 파일 쓰기(기록 폴더 안의 없는 폴더는 만들며), 작업 폴더, 조각 빌리기, 장부 목록의 줄
              (세 도우미의 기록을 한 목록으로 — 줄은 저마다 그 기록을 쓴 도우미의 `described` 가 만든다, 목록을 만들 때만 부른다)
    cli       명령 한 번의 끝마무리 — 결과 쓰기와 종료 코드, 어떤 실패도 표준 오류의 JSON 한 줄(Traceback 없이)
"""
