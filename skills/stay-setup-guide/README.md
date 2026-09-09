# stay-setup-guide — 호텔 세팅 입력 지시서 스킬

호텔 계약서(요금표)만 있는 상태에서, ERP Stay 화면에 그대로 따라 칠 수 있는 **지시서**
(`<이름>_입력지시서.html` — 복사 버튼과 진행 체크가 달린 단일 HTML)를 만드는 Agent Skill이다.
`SKILL.md` 가 절차의 정본이고, 이 폴더의 나머지는 그 절차가 참조하는 규칙·예시·도구다.
짝 스킬 `stay-setup-run` 이 이 지시서를 브라우저에서 그대로 실행한다.

> **세 파일의 구분** — 이름이 비슷해도 셋은 다른 물건이다.
> - **지시서** `<이름>/<이름>_입력지시서.html` — **담당자에게 건네는 유일한 산출물**. 검사 도장을 지고, 러너도 이것만 읽는다.
> - **원고** `<이름>/_원고/manual.md` (곁에 `rules.md`·`facts.json`·`contract.md`) — 지시서를 만드는 작업 파일. 건네지 않는다.
> - **실행 계획** `<이름>_실행/steps.json` — 러너 스킬이 지시서에서 뽑는 내부 파일. 이 스킬은 만들지 않는다.

**운영 2026-09-04 배포판 화면 기준**이다 — 호텔을 만들면 오퍼 0건·룸 0건·판매 연결 0건이고,
오퍼가 없는 동안에는 판매 연결의 [객실 추가] 가 막힌다. 그래서 지시서는 `오퍼 만들기` 를 룸·판매 연결보다 앞에 둔다.
같은 날 배포로 **연령 구간**(`오퍼` 탭)과 부과금 드로어의 **연령별 단가** 표가 생겼다 — 계약서에 아동 정책이 있으면
소아를 부가옵션으로 따로 만들지 않고 부과금 한 건에 나이대별 단가로 적는다.

## 설치

- **클로드 코드(Claude Code) — 플러그인**: 저장소 최상위 안내대로 `/plugin marketplace add eoding/stay-setup-guide`
  → `/plugin install stay-setup@eoding-stay` 로 깔고 자동 업데이트를 켠다. 그러면 `/stay-setup:stay-setup-guide` 로 부른다.
- **코덱스(Codex) — 플러그인**: `codex plugin marketplace add eoding/stay-setup-guide` →
  `codex plugin add stay-setup@eoding-stay`. 새 판은 `codex plugin marketplace upgrade` 로 받는다. 지시서 만들기와
  손 입력까지가 Codex 로 되는 범위다(브라우저 자동 입력은 실측 전).
- **폴더 복사**: 이 `stay-setup-guide` 폴더를 그대로 `~/.claude/skills/`(또는 프로젝트의 `.claude/skills/`,
  `~/.codex/skills/`, `.cursor/skills/`, `~/.hermes/skills/`) 아래에 넣는다. 복사본은 스스로 업데이트되지 않는다.
- **계약서 변환**: `scripts/convert_contract.py` 가 xlsx·pdf·docx·hwp·hwpx 등을 마크다운으로 바꾼다. 필요한
  파이썬 패키지(firecrawl-anydoc, rhwp-python, openpyxl)는 처음 실행 때 **현재 파이썬 환경에 스스로 설치**한다
  (설치 전에 안내 한 줄을 출력). Node 는 필요 없다.

## 사용법

`SKILL.md` 를 읽고 그 절차(룰 정리 → 팩트 수집 → 원고 작성 → 🟡 0건 만들기 → 검사 → 렌더)를 그대로 따라간다.
값 표기 규칙의 정본은 `references/MANUAL-SPEC.md`, 완성된 결과물의 모양은 `examples/우에노_토우가네야/`를 본다.

원고를 다 쓰면 검사하고 렌더한다. 원고가 `<이름>/_원고/manual.md` 자리에 있으면 공유 폴더명과 출력 경로를
경로에서 알아낸다 — 렌더 결과는 `<이름>/<이름>_입력지시서.html` 이다.

```
python3 scripts/check_manual.py <이름>/_원고/manual.md --photos <이름>/사진
python3 scripts/render_card.py  <이름>/_원고/manual.md --font scripts/fonts/PretendardVariable.woff2 --title "<호텔> 입력 지시서"
```

원고를 다른 자리에 두었으면 `--share-name <공유 폴더명>` 과 `-o <출력 HTML>` 을 준다. 두 스크립트 모두
`--help` 로 쓸 수 있는 옵션을 보여 준다.

**원고를 한 글자라도 고쳤으면 다시 렌더한다.** `render_card.py` 는 렌더한 HTML 에 검사 도장
(`<meta name="stay-guide-stamp" content="v1;sha256=<원고 해시>;check=ok|fail;rendered=<날짜>">`)을 박는다.
러너는 도장이 없거나 `check=fail` 이거나 원고 해시가 어긋난 지시서를 브라우저를 열기도 전에 거부한다.

**예시 세트에는 사진 파일이 없다** — 저작권 때문에 `examples/우에노_토우가네야/` 에는 파일명과 출처 목록
(`사진목록.txt`)만 두고 이미지 자체는 담지 않는다. 그래서 예시를 검사할 때는 `--photos` 를 빼고 돌린다
(붙이면 지시서가 부르는 사진 파일이 없다고 나온다). 이 스킬 폴더에서 그대로 실행되는 명령은 이렇다.

```
python3 scripts/check_manual.py examples/우에노_토우가네야/_원고/manual.md
```

실제 호텔을 세팅할 때는 사진을 준비한 폴더를 `--photos` 로 함께 주어 파일이 다 있는지까지 확인한다.

## 폴더 구성

| 경로 | 내용 |
|---|---|
| `SKILL.md` | 이 스킬의 진입점. 입력 → 절차 → 반드시 지킬 것 → 하지 말 것 → 산출물 |
| `references/MANUAL-SPEC.md` | 지시서 원고(`_원고/manual.md`) 형식 규칙 정본 — 구조·표 표기·단계 갈래별 마지막 줄·순서·금지어 |
| `references/screen-dictionary.md` · `references/screen-dictionary.json` | ERP Stay 화면 31개의 칸 이름·선택지·버튼·거부 문구 정본(사람용 md, 검사기용 json — 함께 고친다) |
| `references/facts-guide.md` | 호텔·룸 팩트(주소·시설·면적·전망·침대·좌표·도시 코드) 수집 절차와 출처 우선순위 |
| `examples/우에노_토우가네야/` | 예시 세트 — **호텔 정보는 실제(도쿄 우에노 토우가네야 호텔), 요금·시즌·취소 규정은 예시 값**(이 호텔과의 실제 계약이 아님). 공유 폴더 배치 그대로다: 맨 위에 지시서 `우에노_토우가네야_입력지시서.html` · `changes.md` · `사진목록.txt`(파일명 · 출처 — **사진 파일 자체는 저작권 때문에 담지 않는다**), 작업 파일은 `_원고/` 안에 `contract.md`(변환된 계약서) → `rules.md` → `facts.json` → `manual.md`(원고 정답지) |
| `scripts/convert_contract.py` | 계약서 파일(xlsx·pdf·docx·hwp·hwpx 등) → 마크다운. 필요한 패키지는 첫 실행 때 스스로 설치 |
| `scripts/check_manual.py` | 원고 형식 검사 — 단계=저장 1:1, 번호 연속, 금지어·원문자·좌표·절대경로 0, 사진 파일 존재, 같은 오퍼의 시즌 날짜 겹침 0, 오퍼의 `기본 취소 정책` 지정, 금지 단계(`경고 넘어가기`·`오퍼 고치기`·`캠페인 만들기`) 0, `룸 만들기`·`판매 연결` 이 첫 `오퍼 만들기` 뒤, 연령 구간 나이 범위 겹침 0, 부가옵션·부과금 이름이 대상만 적히지 않았는지, 단계 갈래별 마지막 줄, 판매 구간이 지시서 만든 날부터인지(과거 투숙 시작·과거 시즌 오류, 예약 시작·종료 비움 ⚠), 룸 이름에 한글(⚠), 엑스트라베드 의무 규칙(⚠), 공급 통화 USD 여부(⚠) |
| `scripts/render_card.py` | 원고 → 지시서 HTML(표 셀마다 복사 버튼, 목차, `진행 현황` 띠와 단계별 상태 표, 검사 도장, 폰트 임베드). 러너가 옆 탭에서 `stayGuide.mark(...)` 로 체크를 올릴 수 있다 |
| `scripts/fonts/PretendardVariable.woff2` | HTML 지시서에 임베드하는 한글 폰트(라이선스: 같은 폴더 `LICENSE-Pretendard.txt`, SIL OFL) |
| `tests/test_check_manual.py` · `tests/test_render_card.py` | 검사기 시험(화면 사전 JSON 을 그대로 읽어 칸 이름·값 종류를 대조하고 예시 원고가 ALL OK 인지 본다)과 렌더러의 검사 도장 시험 |

```
python3 -m unittest discover -s tests
```

## 면책

**사진 저작권은 사용자 책임입니다.** 이 스킬이 찾거나 내려받는 사진(호텔 공식 사이트 등)의 저작권·사용 허락 확인은 전적으로 사용자(여행사)의 책임이며, 이 스킬의 제공자는 사진의 권리 문제에 대해 어떠한 책임도 지지 않습니다. 판매 화면에 올리기 전에 호텔로부터 사용 허락을 받으십시오.

지시서는 작업 보조 자료입니다. 화면에 넣기 전에 값을 계약서와 대조하십시오. 입력된 값에 대한 책임은 제공자에게 없습니다.

## 한계

- 화면 사전(`references/screen-dictionary.md`·`.json`)은 **운영 2026-09-04 배포판** 기준이다. 화면이 바뀌면 사전을
  새로 받고 스킬을 다시 점검한다. 사전에 없는 칸·옵션·버튼을 지어내지 않는다.
- 사전은 코드에 적힌 문구 기준이라, 운영 화면의 번역 설정이 일부 칸 이름을 다르게 보여 줄 수 있다(사전의 마지막 절 참고).
  사전에 없는 표현을 화면에서 보면 화면 문구를 따른다.
- 가격·시즌·취소 규정은 계약서에 있는 값만 쓴다. 기존 판매 페이지나 여행 예약 사이트(OTA)의 가격은 쓰지 않는다.
  금액은 계약서 숫자 그대로 적고 다른 통화로 환산하지 않는다.
- 사진은 이 스킬이 대신 구해주지 않는다. 사용자가 준비하거나, `references/facts-guide.md` §사진 의 절차대로
  직접 찾아 파일명 규칙에 맞게 저장해야 한다.
- 지시서 HTML 은 로그인 없이 브라우저에서 바로 열리는 정적 파일이다. 계약 조건이 담기므로 이 파일을 누구와
  어떻게 공유할지는 사용자가 판단한다.
