# stay-setup-guide — 호텔 세팅 입력 지시서 스킬

호텔 계약서(요금표)만 있는 상태에서, ERP Stay 화면에 그대로 따라 칠 수 있는 "입력 지시서"(manual.md →
복사 버튼 달린 HTML 카드)를 만드는 Agent Skill이다. `SKILL.md` 가 절차의 정본이고, 이 폴더의 나머지는
그 절차가 참조하는 규칙·예시·도구다.

**ERP 2026-09-04(PR #9033) 이후 화면 기준**이다 — 호텔을 만들면 오퍼 0건·룸 0건·판매 연결 0건이고,
오퍼가 없는 동안에는 판매 연결의 [객실 추가] 가 막힌다. 그래서 지시서는 `오퍼 만들기` 를 룸·판매 연결보다 앞에 둔다.

## 설치

- **클로드 코드(Claude Code)**: 이 `stay-setup-guide` 폴더를 프로젝트의 `.claude/skills/` 아래
  (또는 사용자 전체에 적용하려면 `~/.claude/skills/`) 그대로 복사해 넣는다. 다음 실행부터 자동으로 인식한다.
- **헤르메스(Hermes Agent)**: 이 `stay-setup-guide` 폴더를 `~/.hermes/skills/` 아래 그대로 복사해 넣는다.
  `hermes skills list` 로 로드됐는지 확인할 수 있다.
- **계약서 변환**: `scripts/convert_contract.py` 가 xlsx·pdf·docx·hwp·hwpx 를 마크다운으로 바꾼다. 필요한 파이썬 패키지(firecrawl-anydoc, rhwp-python, openpyxl)는 처음 실행 때 **현재 파이썬 환경에 스스로 설치**한다(설치 전에 안내 한 줄을 출력). Node 는 필요 없다.

## 사용법

`SKILL.md` 를 읽고 그 절차(룰 정리 → 팩트 수집 → 지시서 작성 → 검사 → 렌더)를 그대로 따라간다. 자세한 값
표기 규칙은 `references/MANUAL-SPEC.md`, 완성된 결과물의 모양은 `examples/우에노_토우가네야/`를 본다.

지시서는 짝 스킬 `skills/stay-setup-run` 이 화면에서 그대로 실행한다 — 단계 제목·`카드:` 줄·마지막 `→ [버튼]` 표기가 그 러너가 알아보는 형식이다.

```
python3 scripts/check_manual.py <manual.md> --photos <사진 폴더> --share-name <공유 폴더명>
python3 scripts/render_card.py <manual.md> -o <이름>_입력지시서.html --font scripts/fonts/PretendardVariable.woff2 --title "<호텔> 입력 지시서"
```

## 폴더 구성

| 경로 | 내용 |
|---|---|
| `SKILL.md` | 이 스킬의 진입점. 입력 → 절차 → 하지 말 것 → 산출물 요약 |
| `references/MANUAL-SPEC.md` | 지시서(manual.md) 형식 규칙 정본 — 구조·표 표기·순서·금지어 |
| `references/screen-dictionary.md` / `.json` | ERP Stay 화면 26개의 칸 이름·선택지·버튼·거부 문구 정본(사람용 md, 기계용 json) |
| `references/facts-guide.md` | 호텔·룸 팩트(주소·시설·면적·전망·침대·좌표 등) 수집 절차와 출처 우선순위 |
| `examples/우에노_토우가네야/` | 예시 세트 — **호텔 정보는 실제(도쿄 우에노 토우가네야 호텔), 요금·시즌·취소 규정은 예시 값**(이 호텔과의 실제 계약이 아님): `contract.md`(변환된 계약서) → `rules.md` → `facts.json` → `manual.md`(정답지) → `changes.md` → 렌더된 HTML, `사진목록.txt`(파일명 · 출처) |
| `scripts/convert_contract.py` | 계약서 파일(xlsx·pdf·docx·hwp·hwpx 등) → 마크다운. 필요한 패키지는 첫 실행 때 스스로 설치 |
| `scripts/render_card.py` | `manual.md` → 표 셀마다 복사 버튼, 목차, 진행 체크가 달린 단일 HTML 파일 변환 |
| `scripts/check_manual.py` | `manual.md` 형식 검사(단계=저장 1:1, 번호 연속, 금지어·원문자·절대경로 0, 사진 참조 확인, 같은 오퍼의 시즌 날짜 겹침 0·오퍼의 `기본 취소 정책` 지정·`경고 넘어가기` 단계 0·`오퍼 고치기` 단계 0·`룸 만들기`·`판매 연결` 이 첫 `오퍼 만들기` 뒤·부가옵션 카드의 오퍼 한정·프로모션 카드·시즌 만들기의 `→ [추가]`) |
| `tests/` | 검사 스크립트 시험 — `python3 -m unittest discover -s skills/stay-setup-guide/tests` |
| `scripts/fonts/PretendardVariable.woff2` | HTML 카드에 임베드하는 한글 폰트(라이선스: 같은 폴더 `LICENSE-Pretendard.txt`, SIL OFL) |

## 면책

**사진 저작권은 사용자 책임입니다.** 이 스킬이 찾거나 내려받는 사진(호텔 공식 사이트 등)의 저작권·사용 허락 확인은 전적으로 사용자(여행사)의 책임이며, 이 스킬의 제공자는 사진의 권리 문제에 대해 어떠한 책임도 지지 않습니다. 판매 화면에 올리기 전에 호텔로부터 사용 허락을 받으십시오.

지시서는 작업 보조 자료입니다. 화면에 넣기 전에 값을 계약서와 대조하십시오. 입력된 값에 대한 책임은 제공자에게 없습니다.

## 한계

- 화면 사전은 코드에 적힌 문구 기준이라, 운영 화면의 번역 설정이 일부 칸 이름을 다르게 보여 줄 수 있다(사전의 마지막 절 참고). 사전에 없는 표현을 화면에서 보면 화면 문구를 따른다.
- 화면 사전(`references/screen-dictionary.md`·`.json`)은 이 스킬을 만든 시점의 화면 기준이다. 화면이 바뀌면 사전을 새로 받는다(`hermes skills update` 또는 저장소 최신본). 사전에 없는 칸·옵션·버튼을 지어내지 않는다.
- 가격·시즌·취소 규정은 계약서에 있는 값만 쓴다. 기존 판매 페이지나 여행 예약 사이트(OTA)에 있는 가격은
  쓰지 않는다.
- 사진은 이 스킬이 대신 구해주지 않는다. 사용자가 준비하거나, `references/facts-guide.md` §사진 의 절차대로
  직접 찾아 파일명 규칙에 맞게 저장해야 한다.
- `render_card.py` 로 만든 HTML 카드는 로그인 없이 브라우저에서 바로 열리는 정적 파일이다. 계약 조건이
  담기므로 이 파일을 누구와 어떻게 공유할지는 사용자가 판단한다.
