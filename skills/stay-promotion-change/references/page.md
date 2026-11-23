# 페이지 쪽 — 올리기 · 벽 · 작업 · 답 · 오류

차례: 올리기 · 벽 · 보기와 작업 · 답의 모양 · 오류와 할 일

## 올리기

이 도우미의 페이지 모듈 `scripts/page/stay_promotion.js` 는 가격 캘린더 도우미의 페이지 파일(`stay_price.js`) 위에 선다 — 벽 · 작업 틀 · 누르기 · 답 거르기 · 조각, 그리고 편집 창을 읽고(`sent`) 읽은 그대로 보내며 짚은 칸만 바꾸고(`fill`) 저장을 한 번 누르는(`saveOnce`) 부품은 그 파일의 것을 그대로 쓴다(베끼지 않는다 — 부가옵션 · 부과금 도우미와 같은 부품이다). 그래서 올리개도 가격 캘린더 도우미의 것을 쓰고, 묶음 이름 `'promotion'` 을 준다.

| 부르는 것 | 답 |
|---|---|
| `../stay-price-change/scripts/page/stay_price_loader.js` 전체 + 끝에 한 줄 `stayPriceLoader.again('promotion')` 을 한 번에 실행 | 올리개가 서고 그 실행의 답은 `again('promotion')` 의 답이다. 올리개만 실행한 답은 묶음마다의 파일 이름(`sets` — 이 도우미는 `promotion` 의 네 파일)이다 |
| (파일 올리기 도구) 그 칸에 네 파일 | 러너의 `stay_helper.js` · `stay_boot.js`, 가격 캘린더 도우미의 `stay_price.js`, 이 스킬의 `stay_promotion.js`. 접근성 이름이 `stay price file bridge` 인 칸이다(ERP 의 사진 칸과 헷갈리지 않게) |
| `await stayPriceLoader.load('promotion')` | 네 파일을 그 차례로 실행하고 `{ok, helper, price, promotion, stored, loaded}`. 올라온 파일이 설치된 도우미의 것과 다르면 실행하지 않고 `wrong` 에 그 이름을 댄다 — 설치된 스킬 폴더의 그 파일을 다시 올린다 |
| `stayPriceLoader.again('promotion')` | 이 탭에 적어 둔 원본을 다시 실행한다. 없거나 예전 판인 파일만 `want` 에 댄다 — 그 파일만 올리고 `load('promotion')` |
| `stayPriceLoader.status('promotion')` | `{ok, helper, price, promotion, stored}` — 올라 있는 판들 |

**올릴 파일의 자리.** 모두 이 스킬 폴더(SKILL.md 가 있는 폴더)에서 본 자리다: `../stay-setup-run/scripts/stay_helper.js` · `../stay-setup-run/scripts/stay_boot.js` · `../stay-price-change/scripts/page/stay_price.js` · `scripts/page/stay_promotion.js`. 파일 올리기 도구에는 이 스킬 폴더의 절대 경로를 앞에 붙인 온전한 경로로 준다. 같은 이름의 파일을 다른 곳(예전 복사본 · 내려받은 폴더)에서 찾아 올리지 않는다 — 예전 판이면 올리개가 `wrong` 으로 거절한다.

**`stored` 의 키 이름이 가려져도.** `load` · `again` 의 답에서 `stored` 의 키 이름 하나가 브라우저 도구에 가려 `[BLOCKED: Base64 encoded data]` 처럼 보일 수 있다(도구가 긴 글을 숨긴다). 올랐는지는 `ok: true` 와 판 번호로 정한다 — 가려진 이름 때문에 다시 올리지 않는다.

**페이지에 남기는 것.** 이 탭의 출처(ERP 주소)의 localStorage 에 `stayPrice` 로 시작하는 키만 쓴다. 올리개가 원본 넷 `stayPriceHelperSrc` · `stayPriceBootSrc` · `stayPriceSrc` · `stayPricePromotionSrc` 를 적어 두고 `again('promotion')` 이 다시 실행한다. 작업 틀이 마지막 작업의 답을 `stayPriceLast` 에 적고 `last()` 가 읽는다. 러너의 키는 읽지도 쓰지도 않는다.

## 벽

작업이 도는 동안 페이지 맨 바깥에서 모든 클릭과 폼 제출을 먼저 보고, 그 작업의 허용 목록에 없는 것은 막고 적는다(답의 `blocked`). 작업 밖에서도 스크립트가 만든 클릭은 막는다(사람의 클릭은 지난다).

| 작업 | 지나는 것 |
|---|---|
| `look` | [프로모션] 탭(목록이 안 보일 때만) |
| `readPromotion` | 탭 · 고른 카드(오퍼 번호, 전 오퍼 공통은 0)의 고른 줄(프로모션 번호)의 [편집] |
| `applyPromotion` | 위 둘 · 그 호텔 · 그 프로모션의 편집 주소로 저장하는 [저장] 한 번 — 그 창에 표식(`data-stay-keeps-off-form-keys="1"`)이 있고, 누르는 순간 창이 친 뒤의 칸 그대로일 때만 |

어느 작업에서도 막는 것: [삭제] · [프로모션 추가] · [단 추가] · 단 [삭제] · 편집 창의 모든 고르기(발동 조건 · 혜택 방식 · 적용 단위 · 시즌 · 요금제 · 취소 정책 · 적용 범위) · 모든 체크(진행기간 제한 · 중복 허용 · 적용 범위 · 붙일 오퍼) · 적용 범위 카드 · 보관 · 판매 시작/종료 · 다른 탭.

## 보기와 작업

| 부르는 것 | 하는 일 |
|---|---|
| `await stayPromotion.look()` | 이 탭이 어디인지 — 로그인 화면이면 `login: true`. 아니면 호텔(`{id, name}`)과 카드마다 프로모션 줄 전부(조각 `body`). 표의 머리가 「프로모션 / 발동 조건 / 혜택 / 중복 / 한정 / 액션」이 아니면 읽지 않는다 |
| `await stayPromotion.readPromotion({hotel, offer, promotion})` | 그 줄의 [편집] 을 눌러 창을 열고, 창이 그 프로모션의 것인지(저장 주소) · 단 줄이 다 그려졌는지 본 뒤 저장 단추가 보낼 칸(`form`) · 고르기의 글자(`labels`) · 뿌리의 표식(`keeps`) · 단 줄마다 화면 밖 설정의 이름(`marks`) · 오류를 읽고 닫는다. 목록에 없으면 `missing: true` |
| `await stayPromotion.applyPromotion({no, hotel, offer, promotion, title, form, marks, set})` | 명령의 `calls` 가 준 `payload` 그대로. 창을 열고 이름 · 표식 · 단 줄의 숨은 칸 `tiers_origin`(`?` 가 없어야 한다) · 단 표식이 읽은 것과 같은지 본 뒤, 창이 보낼 칸이 `form` 과 꼭 같을 때만 `set`(단의 값 칸 `tiers_value` 만)을 치고 저장을 한 번 누른다. `tiers_origin` 은 `form` 에 읽은 그대로 있고 치지 않는다(commands.md 「단」) |
| `stayPromotion.take(id, at, size)` · `last()` · `idle()` | 조각의 한 쪽 · 마지막 작업의 답 · 쉬는 벽 — 읽기만 한다 |

## 답의 모양

모든 답은 JSON 으로 800자 안이다. `op` · `ok` · `ask`(물은 값의 지문) · `clicks`(지난 클릭) · `blocked` · `ms` · `doneAt`(끝난 시각). `what`(읽거나 저장한 프로모션) · `note`(저장했으면 「저장했습니다」 같은 한 마디) · `rest`(답할 때 화면 — 드로어 · 요청 — 이 정리됐는지. 아니면 다음 작업이 `started: false` 로 기다린다)도 온다. 읽기는 조각 `body`(id · 글자 수 · 바이트 수 · CRC-32 · FNV-1a)를 싣고 `take` 로 받는다. `readPromotion` 은 `keeps` 도 싣고, 결과를 못 본 저장(`saved: "unknown"`)에 ERP 가 늦게 거절로 답했으면 한 번 `late`(그 저장의 결과 한 문장 — "앞서 저장됐는지 알 수 없던 k번째 저장은 ERP 가 거절했습니다 — <ERP 의 글>". 그대로 말한다, stopped.md 1)도 싣는다. 저장 작업의 답에는 언제나 `saved`(true · false · "unknown") 와 `pressed` 가 있다 — 누르기 전에 멈추면 `refused: true`, 표식이 없어 멈추면 `gate: true` 도. 시작하지 않은 작업은 `started: false` 와 `wait`(초)다.

## 오류와 할 일

| 오류 (앞부분) | 뜻 · 할 일 |
|---|---|
| `이 프로모션의 편집 창은 ERP 가 할인 단 줄이 어느 저장된 단에서 왔는지 모르는 상태라…` (`refused: true`) | 그 창의 단 줄 가운데 숨은 칸 `tiers_origin` 이 `?` 인 줄이 있다. 아무것도 치지 않았고 누르지 않았다. 그 문장을 그대로 말하고 끝낸다 |
| `이 ERP 는 아직 프로모션을 화면으로 저장하면 …` (`gate: true`) | 그 창에 표식이 없다. 아무것도 치지 않았고 누르지 않았다. 그 문장을 그대로 말하고 끝낸다 |
| `창의 단 표식(화면에 없는 설정)이 읽은 것과 다릅니다` · `창의 값이 읽은 값과 다릅니다` | 미리보기 뒤에 ERP 에서 그 프로모션이 바뀌었다. 아무것도 넣지 않았다 — 기록하고(`record-result`) stopped.md |
| `친 뒤에 창이 바뀌었습니다(…) — 저장을 누르지 않았습니다` (`refused: true`) | 값을 친 뒤 [저장] 을 누르기 전(앞 요청이 끝나기를 기다리는 사이)에 창의 칸이 바뀌어 벽이 그 클릭을 막았다. 저장 요청은 나가지 않았다(`saved: false`). 다시 부르지 않는다 — 장부에 적고 stopped.md |
| `단 줄 …의 화면 밖 설정 표식이 창에 실린 단 목록과 다릅니다` | 화면이 다 그려지지 않았다. 몇 초 뒤 같은 값으로 다시 부른다 |
| `열린 창이 고른 프로모션(…)의 편집 창이 아닙니다` · `프로모션 편집 창의 할인 단 줄이 다 그려지지 않았습니다` | 아무것도 치지 않았다. 탭을 새로 고쳐 달라고 하고 「준비」 2 부터 |
| `프로모션 표의 머리가 …` · `프로모션 줄의 칸이 …개입니다` | ERP 화면이 바뀌었을 수 있다. 멈추고 담당자에게 그대로 알린다 |
| `프로모션 편집 창이 저장을 거절했습니다 — …` | 저장 안 됨(`saved: false`). 다시 누르지 않는다 — stopped.md. 뒤의 글이 단을 짚으면(「기준값 46 단에 저장된 화면에 없는 설정 …」 — 화면 밖 설정을 어느 단에 이을지 ERP 가 정할 수 없을 때) 도우미로는 풀 수 없다. 그 글을 그대로 담당자에게 알린다 |
| `[저장] 은 눌렸고 저장됐는지 알 수 없습니다` | `saved: "unknown"`. 다시 누르지 않는다 — 다시 읽어 `check`(stopped.md) |
| `허용 목록에 없는 클릭을 막았습니다` | 벽이 막았다. 돌아가는 길을 찾지 않고 그대로 알리고 멈춘다 |
| `앞 작업(…)이 아직 끝나지 않았습니다` · `앞 화면(드로어·요청)이 아직 정리되지 않았습니다` (`started: false`) | `wait` 초 뒤 같은 값으로 다시 부른다 |
| `드로어가 열려 있습니다 — 이 도우미가 연 것이 아니라 닫지 않았습니다` | 사람이 하던 일이다. 사람이 닫은 뒤 다시 부른다 |
| `이 탭은 호텔 … 입니다 — 요청은 호텔 …` | 다른 호텔의 탭이다. 그 호텔의 Stay 화면을 열어 달라고 한다 |
