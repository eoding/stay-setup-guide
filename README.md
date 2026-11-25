# stay-setup-guide

Six agent skills for travel-agency staff. Two set up a new hotel. From a hotel contract (rate sheet) file alone, `stay-setup-guide`
produces a step-by-step **입력지시서** — an input guide as one HTML file, the deliverable a person follows on the
ERP Stay screens — plus a photo folder and a list of the values that need a human decision. `stay-setup-run` then
takes that same guide and fills the ERP Stay screens automatically, in the Chrome tab the user is already logged
into, one step at a time. **[판매 시작] (start selling) is always pressed by a person**, never by the skills. Four
more change the prices of a hotel that already sells — price calendar cells, add-on price lines, charge amounts and
promotion discounts — with a preview, a save only after the person says "적용", a fresh reading to verify, and a rollback. The guides and the skill
documents are Korean because the ERP screens are Korean.

Release candidate: plugin `stay-setup` 1.10.3 (`stay-setup-guide` 1.8.5, `stay-setup-run` 0.16.0, `stay-price-change` 0.1.0, `stay-addon-price-change` 0.1.0, `stay-charge-change` 0.1.0, `stay-promotion-change` 0.1.1). Publishing follows the matched ERP release (the add-on stay-length condition, extra-person add-ons attached at quote time, the promotion drawer and the adjacent-offers warning, below). This release does not claim a production or browser installation rehearsal.

## 2026-11-25 add-on stay-length condition

For a contract requiring one dinner per adult on a guest-selected date, set the add-on to
`일자선택`, choose `전 숙박일 의무`, and enter a whole number from 2 to 99 in `숙박 N박 이상일 때만`.
For qualifying stays, the quantity equals the adult count. Guests choose one or more available dates.
Each selected date incurs the dinner charge for every adult. For shorter stays, guests can add dinner on available dates.
Set at least one sellable dinner date for each stay that the contract requires to include dinner. Check coverage for
the applicable rooms and rate plans. With no sellable dates, Stay hides the card and can issue a quote without dinner.
If you cannot cover a required stay, record the gap in `changes.md` and confirm whether to close those dates to sales
or arrange an agreed alternative before publishing. Keep the adult requirement on its own add-on. Set up a separate
optional children's dinner only when the contract makes it optional. Fixed-date mandatory dinners use surcharges.
If the settings cannot represent a required children's dinner, confirm how to provide and charge for it with the contract
owner. The checker enforces the same field combination and range as the ERP.

## 2026-11-24 extra-person add-ons are attached automatically

The ERP now attaches the two occupancy-rule add-ons, `기준 성인 초과 시 의무 (엑스트라베드)` and `총 인원 N명 이상일 때 의무`,
at quote time: one per adult above the room's `기준 성인` (one in total for the head-count rule), and the guest cannot
remove them. Record each contract charge once. If an extra adult's charge covers the required bed, put the charge in the
add-on. If the contract prices extra occupancy and the required bed separately, use the (base+1) room price cell for
occupancy and the add-on for the bed, following each charge's billing unit. A higher (base+1) room rate alongside a required
bed triggers a warning in the ERP and the checker so staff can verify both amounts against the contract. The extra-adult
rule requires a room's `기준 성인`. The total-headcount rule uses the total guests. A party whose automatic quantity exceeds
the add-on's `수량 상한` cannot book that room.

## 2026-11-24 promotion drawer fields and the adjacent-offers warning

The ERP promotion drawer lost two fields that had no effect on sales, `다른 프로모션과 중복 적용` and `배타 그룹`: the customer
room list and the staff quote sell one promotion per line. New promotions can no longer use the `발동 조건` option
「객실 수」, and when `혜택 방식` is `무료 숙박` the `적용 단위` row is hidden. Guides write none of the three and the checker
rejects them. A contract condition of the form "N rooms or more" is not carried over, because Stay sells one room per
booking; the guide records it in `changes.md` instead. A promotion opened from an offer card limits `요금제 한정` to that
offer's rate plans. The screen dictionary (279 fields), screen help and runner fixtures are re-synced, and the
promotion helper no longer shows the two removed settings and refuses values the ERP form now refuses (a flat discount
above 9,999,999,999.99, more than 2,147,483,647 free nights).

The validation banner has a new yellow item, the adjacent-offers warning (`두 오퍼가 맞닿아 있어 경계에 걸친 숙박은 판매되지
않습니다 …`). It appears whenever one offer's stay period ends the day before another's begins, as with contracts laid
out year by year, and a stay across that boundary cannot be booked in one go: guests are told to split it. It is not a
defect in the guide. The guide notes it in `changes.md`, the runner reports it apart from the other yellow items and
explains it without pressing [이건 넘어가기], and the person decides whether to dismiss it. Dismissing does not remove the
line, and the dismissal covers every later adjacent pair of that hotel. Every other yellow item still counts against the
pass mark. The runner now also counts yellow items in a collapsed list.

## 2026-11-23 promotion discount helper

A fourth helper, `stay-promotion-change`, changes the values of a promotion's tiers (a discount percentage, a flat discount
amount, a number of free nights) on one promotion of an offer or on one common to all offers, with the same preview, "적용",
re-reading, ledger and rollback as the other three. It saves only on an ERP whose promotion edit window carries the mark
that the server keeps the settings the window does not show (`data-stay-keeps-off-form-keys="1"`). That mark comes with an
ERP fix that is not deployed yet; on an ERP without it the helper reads and previews and says plainly that it will not save,
because a screen save there drops the cancellation settings stored on a tier. It never changes a promotion's conditions,
dates, booking period, thresholds or tiers. Built and tested in the suites against hand-built screens; it has not run on a
real ERP yet.

## 2026-11-21 price helpers for hotels that already sell

Three new skills change the prices of a hotel that is already selling, in the Chrome tab the person is logged into:
`stay-price-change` changes price calendar cells (sell, list and supply prices, by amount, percent or new value, and can
match a new rate sheet date by date), `stay-addon-price-change` changes add-on price lines (sell price and supply cost),
and `stay-charge-change` changes charge amounts (the flat amount or rate, one time band, one age rate, the pay-at-property
amount). Each one reads the current values from the ERP screens, shows a preview page, saves only after the person says
"적용", reads the screen again to check what was saved, and can roll back. All three record every preview, save and
rollback in one ledger on the person's computer. The setup skills are unchanged and point to the helpers for a hotel that
already sells. See "Changing the prices of a hotel that already sells" under [Use](#use).

## 2026-11-18 promotion target offers and screen-help names

The ERP promotion drawer opened from an offer card now starts with a `붙일 오퍼` checklist: every checked offer gets
its own copy of the promotion, and the opened card's offer is checked by default. If anything other than the
opened card's offer alone is ticked (two or more offers, or one different offer), `시즌 한정`, `요금제 한정` and the
room scope rows are hidden and saved empty. Guides stay as they are, one `프로모션 추가` step per offer card, which
keeps those fields usable for each offer. The checker rejects a `붙일 오퍼` row, and the runner leaves the checklist
untouched, so each step still saves one promotion for the opened offer. People entering by hand can use the
checklist to add one discount to several offers at once. The screen dictionary (281 fields), screen help and runner
fixtures are re-synced. The scope card's mode selects now render as plain selects, so they show on the styled screen.
Screen help also answers for the four names in the price-calendar edit window (`연동 방식` and the three `… 차액`
fields), and the price guide says that an empty `공급 원가` in the season price window keeps the stored cost.

## 2026-11-13 price calendar steps and age-band gaps

Two new step kinds follow the ERP price-calendar drawers: `선택 날짜 가격 수정` (set new prices for one room × one rate
plan over a date range ∩ weekdays — either "base combination only", where the other combinations keep their current
difference or take a new difference per row, or "every combination") and `선택 날짜 가격 가감` (move existing sell
prices by a signed amount or percentage, through the confirmation screen). Existing step kinds and guides are unchanged.
The checker now rejects age bands that leave an age uncovered or overlap inside one offer, because the ERP blocks
[판매 시작] for that offer. The runner reads prices as numbers (`218,100` = `218100`), clears the remembered values of
the season price drawer before filling it, stops before [판매 시작] with the banner's blockers in plain words, and still
runs on the pre-bundle production screens (the new steps hand over to a person where the old screen lacks the control).

## 2026-11-04 bed directinput

The guide and runner now carry assignment-dependent bed wording in the required same-row `직접입력 내용` field. Existing bed choices remain compatible.

## 2026-10-23 operations guide update

Rechecked the [upstream combined guide](https://mhj-stack.github.io/eoding-stay-guide/#start).
The partner guide now follows room STEP 04 / offer STEP 05 and includes sales-day, pricing, season and child-rate
FAQs. The skill-only [operations FAQ](skills/stay-setup-guide/references/operations-guide.md) covers the same decisions.
The automated guide keeps its existing offer-before-room creation order; both paths create offers and rooms before sale links.
Existing masked screenshots retain their 2026-10-15 capture date. Current price button names and the new-season
[추가] / edit [저장] distinction are retained where upstream still uses old wording.

The October customer options are **announced as upcoming** in the upstream guide checked on 2026-10-23.
Confirm availability against the deployment notice and current screens before using them. The update adds customer-form
completion/cancellation rules and post-booking answer guidance; it does not claim a new production-screen audit.

## 2026-10-22 customer options

The [customer-options guide](skills/stay-setup-guide/references/customer-options-guide.md) covers the agency-wide KRW display setting, generic questions on benefits/charges/addons, selection limits and onsite payment amounts. The screen dictionary retains its original extraction date and adds a separately dated release supplement; new instructions are not presented as new screenshots.

Question steps use the same input-guide contract as `stay-installer-mcp`. The browser runner verifies the exact offer/item, saves with the question-specific button, then reopens the question and checks the saved values. CCS settings require a human administrator and a fresh customer-page check. Customer answers and reservation history are reviewed after setup; installing questions does not perform a payment. Existing banner settings are reused, not automatically recreated.

## Install

**Claude Code plugin (recommended — it updates itself).** In Claude Code, the CLI or the desktop app's Code tab:

```
/plugin marketplace add eoding/stay-setup-guide
/plugin install stay-setup@eoding-stay
```

Then open `/plugin` → **Marketplaces** and turn on auto-update for `eoding-stay`. The skills are invoked as
`/stay-setup:stay-setup-guide` and `/stay-setup:stay-setup-run`, and the price helpers as `/stay-setup:stay-price-change`,
`/stay-setup:stay-addon-price-change`, `/stay-setup:stay-charge-change` and `/stay-setup:stay-promotion-change`.

**Codex plugin.** In the Codex app or terminal Codex:

```
codex plugin marketplace add eoding/stay-setup-guide
codex plugin add stay-setup@eoding-stay
```

Pick up a new release with `codex plugin marketplace upgrade`. Codex covers guide creation and entering the values
by hand; automatic entry on Codex is 실측 전, not yet verified, and the price helpers have run only with Claude in Chrome.

**Copying the folders** also works and is the way to install into an agent that is neither Claude Code nor Codex:
put `skills/stay-setup-guide` and `skills/stay-setup-run` into the tool's skills directory (`~/.claude/skills/`,
`~/.codex/skills/`, `.cursor/skills/`, and so on). The price helpers use code from `stay-price-change` and page files from
`stay-setup-run` by relative path, so copy all six folders side by side. A copied skill does not update itself.

Sales and operations staff who do not use a terminal should follow
[`docs/설치-사용-안내.md`](docs/설치-사용-안내.md) instead — one page, Windows and Mac, install to first hotel.

## Requirements

- **Python 3.10+** for the scripts. The contract converter installs its own packages on first run
  (`firecrawl-anydoc`, `rhwp-python`, `openpyxl`) and prints a notice first. Node.js is optional and only minifies
  the two browser helper files.
- **Claude Code** (CLI or the desktop app's Code tab) **with the Claude in Chrome extension** for automatic entry.
  That is the measured path: seven hotels ran end to end on it. The extension grants permission per site, so allow
  the ERP domain first.
- **Codex** covers guide creation and entering the values by hand. **Automatic entry on Codex is not yet verified**
  — we do not claim it works. `skills/stay-setup-run` lists the three browser capabilities to confirm before trying
  it. Other agents that read the standard `SKILL.md` format (Gemini CLI, Grok, Cursor) can produce the guide the same
  way.
- Contract formats the converter reads: xlsx, xlsm, xls, ods, csv, pdf, docx, pptx, odt, rtf, epub, hwp, hwpx.

## Use

Put the contract file and a photo folder in one folder, point the agent at it, and ask for the guide:

```text
/stay-setup:stay-setup-guide  Build the ERP Stay input guide from the contract in this folder.
Hotel <name>, city <city>, supply currency USD, contract party 자사, cancellation policy <name>.
Do not invent any rule, surcharge or value that is not in the contract.
```

**Three files, three roles.** Their names are close and the roles are not, so the layout keeps them apart.

| File | What it is | Who reads it | Where it lives |
|---|---|---|---|
| `<name>_입력지시서.html` | **지시서** — the guide, the one deliverable, carrying the check stamp | the person doing the setup, and the runner skill | `<name>/` |
| `manual.md` | **원고** — the draft the guide is rendered from, with `rules.md`, `facts.json`, `contract.md` | the guide skill only; never handed out | `<name>/_원고/` |
| `steps.json` | **실행 계획** — the run plan extracted from the guide, generated, never hand-edited | the runner skill only | `<name>_실행/` |

Alongside the guide you get `사진/` and `changes.md`, which lists every value decided differently from the contract
plus the fields left blank for a person to fill in. Open the guide in a browser and follow it by hand, or hand it to
the runner:

```text
/stay-setup:stay-setup-run  Run this guide in the ERP tab that is open and logged in.
Guide: /abs/path/<name>/<name>_입력지시서.html
Photos: /abs/path/<name>/사진
```

**Only a stamped, checker-passing guide runs.** The renderer stamps the HTML with the hash of the draft it came from
and the checker's verdict. The runner's parser refuses a draft file, a missing stamp, a failed check, or a draft that
has been edited since the render, and it exits before a browser is opened. The fix is always on the guide side: fix
the draft, re-render, get the checker to pass.

While the runner works, a small strip in the top-right corner of the ERP page shows where it is
(`12 / 77 · 지금: 룸 만들기 (2번째, 씨뷰 빌라) · 완료 11 · 건너뜀 1`). Leave the guide open in a second tab of the
same browser and its checkmarks and progress bar rise on their own. Neither display changes the run; if the guide tab
is not open the agent skips it silently.

Automatic entry took 13–19 minutes per hotel in production runs, photos included. At the end, read the validation
banner. The pass mark is zero red and zero yellow items, not counting the adjacent-offers warning. Then press [판매 시작] yourself.

**Changing the prices of a hotel that already sells.** Open the hotel's Stay edit screen in a logged-in Chrome tab and
ask in plain words. Each helper confirms what it understood, reads the current values, opens a preview page and saves
only after "적용". It reads the screen again afterwards, and "N번 되돌려" rolls a change back:

```text
/stay-setup:stay-price-change  12월 디럭스 판매가 10% 올려줘
/stay-setup:stay-addon-price-change  조식 추가 가격 5,000원 올려줘
/stay-setup:stay-charge-change  레이트 체크아웃 50% 를 60% 로
/stay-setup:stay-promotion-change  얼리버드 10% 를 12% 로
```

(Raise the December Deluxe sell price by 10%; add 5,000 to the breakfast add-on; change the late check-out rate from 50% to
60%; change the early-bird discount from 10% to 12%.) Changes over 30%, prices below cost and similar cases stop as red lines until the person chooses, in their own
words. The helpers change amounts only. They never delete anything and never create offers, rooms, add-ons, charges or
price cells. The promotion helper changes a promotion's tier values only, and only on an ERP whose promotion edit window
carries the mark that the server keeps settings the screen does not show; elsewhere a person changes promotions in the ERP.
Names and descriptions are not changed; when one still states the amount being replaced, the preview and the result say so.

**시즌 다시 채우기 (season refill).** The price helper can also refill a season through the season's [가격 입력] window
("시즌 [가격] 채우기"), which on its own has no preview and no undo. The helper reads the window, computes with the
ERP's own rules what every cell of the season will become, and shows every cell that will change before anything is
saved (changed cells, new cells, cells it had edited per date, reserved and closed days, days shared with another season,
old rows the refill leaves alone, days without a sale day). From a rate sheet the command derives the window inputs and
lists, under their own heading, every cell the window cannot make equal to the sheet; those can be fixed per date right
after. Choices are per save and per rule (fill as shown, leave those dates out, or change the request); one cell cannot
be kept on its own. After "적용" it types the window as shown and presses it once per save, reads the result back, and
compares cell by cell and with the ERP's own cell counts; "N번 되돌려" restores the values through the price calendar.
New cells cannot be removed, and the window's last inputs, the previous owner season of overwritten cells and the ERP's
hand-edit mark do not come back. It never ticks "이번에 고르지 않은 인원·요금제 가격 지우기". The helper reads each save's range
again just before that save; a change someone else makes in the seconds after that reading is overwritten, as on any ERP
screen. If the person refills
the season in the ERP by hand instead, the helper saves the state before, shows what changed and restores it on request.

Every preview, save and rollback goes into one SQLite ledger on that computer,
`~/Documents/어딩 Stay 가격 변경 기록/가격장부.sqlite3` (set `STAY_PRICE_LEDGER_DIR` to use another folder), with a work
folder per request and the preview pages next to it. Nothing is deleted from it, and a rollback undoes only what that
computer's ledger recorded.

**What has run on a real ERP.** On a local ERP, not on production: price calendar changes by amount and by percent with
reserved days, closed days, child rows and nights tiers; the three kinds of red line; a change cut off between saves and
picked up by a new session; partial and full rollback; matching a short rate sheet by per-date prices; add-on price lines;
charge amounts including a time band and a pay-at-property amount; a page answer miscopied on purpose and recovered with
one retake; the new piece form in a real browser tool; a rate sheet whose child rows were matched by the command and whose
percentage on child rows was asked; comparing a saved state with the present and restoring it; the note on a name that
states the old amount; two same-named add-ons told apart by their offer; the ledger list by hotel; a comparison that names
the helper's own ledger record; a restore to a saved state that settles the change it undid; a save refused at the
moment of pressing because a colleague's change, made through a second ledger, had landed on its cells, followed by the
check that forbids continuing, the stopped change's page and both rollbacks (run twice, before and after the page was
fixed); child cells held together with a kept adults-only cell; a person's click passing the idle wall while a script's
click is blocked. A read-only run on a real
tab after the final trial confirmed that a command makes its missing reading folder, that the loader asks only for the
file a tab is missing, and that `look` hands over the ids and names to choose from. Not yet run on a real ERP: creating
new cells, the failure paths (a save that fails or whose outcome is unknown), a year-long reading, a real rate-sheet file
from a hotel, and a comparison after an actual season refill in the ERP. Run in the test suites only: a failure ends in
one JSON line instead of a traceback; every helper's list line says "모두 되돌림" or "일부 되돌림" with the record that
did it; `look --find` and the newest look answer winning; add-on answers and previews naming the offer and the words
said for a chosen red line; the instructions for showing the ledger, for a change already rolled back, and for a restore
after a comparison. The last unit before handover has also run in the test suites only: every helper's list shows the
hotel's whole ledger with each record's kind in plain words, an empty list has its own sentence, the price list line
names the offer, `work` makes the `look/` folder and `calls --out` the folder for saved apply answers, and the wording of
the add-on and charge views and of the price view's ledger entry. Other follow-ups of the fifth trial (a work folder per
request, the edit-window view, room names taken from earlier readings, the one-line confirmations) are not counted above
as run on a real ERP. Of the fixes that followed the independent review, these have run in the test suites only: a
description that holds an address, a save window that closes mid-save, a drawer a person left open, the cost guard of an
add-on rollback, output on a console that is not UTF-8, and a ledger file that has gone missing. The wording fixes after
the second colleague trial (a re-read value shown with the time it was read, the list line giving the time applying
began, the choices of a rollback that stopped) were checked in the suites and by rendering that trial's ledger again,
not by a new run. The promotion helper (`stay-promotion-change`) has run in the test suites only, on hand-built screens drawn from
the ERP templates; it has not run on a real ERP. The season refill is built, in the test suites (with the season window's page
answers taken from the runner's captured ERP window and hand-built saved and refused renders), and its expansion is
parity-checked against the ERP's own functions on a test database; it has not yet run on a real screen. Nothing has run on
production, on Windows or macOS, or on Python 3.10.

## Optional room inventory

Inventory is optional. The guide skill adds inventory steps only when the contract or the user states room quantities
explicitly, per sale link and date. Without such quantities it adds no inventory step and asks no inventory question,
and guides without inventory steps run exactly as before. A quantity is never estimated from the hotel's total room
count or from what is left. The steps come after the sale links and sale days and before the price fill:

| Step | What it does |
|---|---|
| `재고 수량 판매 켜기` | Turns on 수량으로 판매 (sell by quantity) for one sale link; skipped if it is already on |
| `재고 한꺼번에 넣기` | Enters one total quantity for a date range (both ends included, at most 400 days), the listed weekdays and the listed sale links only; the drawer's default selection is never kept |
| `재고 수량 고치기` | Changes the total quantity of one sale link on one date |

The value is the total quantity for that sale link on that date, as stated in the contract or by the user, not the
number remaining; sold and in-payment counts are read-only and never entered. Dates are stay nights, so the check-out
day is not included. `0` means closed. An empty date means no quantity is set, and a link that sells by quantity does
not sell on that date. The skills never turn quantity selling off and never clear or delete inventory. The form rules
are in [`inventory-guide.md`](skills/stay-setup-guide/references/inventory-guide.md).

## Screen help

`skills/stay-setup-guide/scripts/explain_field.py` answers "what does this field do, and where do customers see it?"
without a contract and without touching the ERP. Give it a field name, optionally narrowed to one screen, or a screen
alone to list every field on it:

```
python3 skills/stay-setup-guide/scripts/explain_field.py '총 수량'
python3 skills/stay-setup-guide/scripts/explain_field.py '<field>' --screen '<screen name or id>'
python3 skills/stay-setup-guide/scripts/explain_field.py --screen '<screen name or id>'
```

It prints the baseline it was built from, then for each match the help text, the effect on sales, and where the field
appears on customer pages (or that it does not appear there directly). `--json` gives the same as JSON; the exit code is
1 when nothing matches. [`docs/파트너-가이드.html`](docs/파트너-가이드.html) shows each ERP input field next to where it appears on
customer pages. Both are point-in-time reference information (the guide uses screens captured on 2026-10-15), not a
check against live screens; when the real screen differs, the real screen wins.

[`docs/파트너-가이드-가격편.html`](docs/파트너-가이드-가격편.html) adds first-time pricing and eight maintenance
scenarios: season, room or rate-plan price changes, removing occupancy/rate-plan combinations, adding a rate plan,
date exceptions, pausing sales and extending a contract. It includes the two-checkbox comparison (overwrite prices
versus remove unselected combinations). Adapted from the [upstream price guide](https://mhj-stack.github.io/eoding-stay-guide/#price-start)
rechecked on 2026-10-23, with the 2026-10-20 button labels and the distinction between creating and editing a season.
Its amounts and dates are examples. This is a manual reference; the automated new-hotel workflow keeps overwrite off.
The guide skill uses [`price-guide.md`](skills/stay-setup-guide/references/price-guide.md) for pricing questions,
including when installed by copying only the skill folder.

## Rules the skills enforce

- **USD is the default supply currency.** Another currency is used only after the user confirms it, and the
  confirmation is recorded in `changes.md`. Amounts are never converted; the ERP handles currency.
- **No invented values.** Anything absent from the contract or the fact sources is left `비움` and listed in
  `changes.md` for a person to fill in. Prices, seasons and cancellation terms come from the contract only, never
  from an existing sales page or a booking site.
- **Seasons never overlap.** Two seasons of one offer cannot share a single day, containment included, and
  `이미 값이 있는 날도 덮기` stays off.
- **Every offer gets a 기본 취소 정책.** `지정 안 함` leaves a red banner item that blocks [판매 시작] outright.
- **A child policy becomes 연령 구간 (age bands) plus per-band prices**, not a child add-on. A child sleeping in the
  room is an occupancy band; an add-on is only something bought separately. Add-on and surcharge names start with
  what is being sold, so `하프보드 소아 (만6~11세)`, not `소아 (만6~11세)`.
- **Photo copyright is the user's responsibility**, stated in the final report and at the top of `changes.md`.
- **Scope lives in the 적용 범위 card** at the bottom of the promotion, add-on, add-on price and surcharge drawers
  (2026-09-21 release). One contract line such as "the breakfast rate plan on every room except the suite" is written
  as a mode plus include/exclude lists on the rate-plan and room axes; exclude wins, and an explicit scope with an
  empty include list sells nowhere and needs the confirmation row. A surcharge has no rate-plan axis.
- **The screen baseline is the production screens of 2026-09-21** (31 screens) **plus the inventory tab of
  2026-10-08**. A new hotel starts empty: zero offers, zero rooms, zero sale links, and the room-link drawer stays
  blocked until the first offer exists. When the ERP screens change, both skills must be re-audited and the screen
  dictionary regenerated; the runner refuses steps written for older screens rather than clicking the wrong row.

## Repository layout

| Path | Contents |
|---|---|
| [`.claude-plugin/`](.claude-plugin) · [`.codex-plugin/`](.codex-plugin) · [`.agents/plugins/`](.agents/plugins) | Plugin and marketplace manifests for Claude Code and Codex; bump every `version` field when a skill version changes |
| [`skills/stay-setup-guide`](skills/stay-setup-guide) | The guide skill: procedure (`SKILL.md`), draft format rules, screen dictionary, facts guide, a worked example, converter/checker/renderer scripts |
| [`skills/stay-setup-run`](skills/stay-setup-run) | The runner skill: parser, in-page helper and boot scripts, screen mechanics, run-log format |
| [`skills/stay-price-change`](skills/stay-price-change) | The price calendar helper, and the code the four price helpers share: `scripts/change_core` (ledger, red-line rules, rollback, pages), the page kit `stay_price.js` and the loader `stay_price_loader.js` |
| [`skills/stay-addon-price-change`](skills/stay-addon-price-change) · [`skills/stay-charge-change`](skills/stay-charge-change) · [`skills/stay-promotion-change`](skills/stay-promotion-change) | The add-on price, charge and promotion discount helpers: their commands, page modules and references, built on the shared code |
| [`scripts/run_price_helper_tests.py`](scripts/run_price_helper_tests.py) | Runs every suite of the four price helpers (see [Maintaining the price helpers](#maintaining-the-price-helpers)) |
| [`docs/`](docs) | [`설치-사용-안내.md`](docs/설치-사용-안내.md) — the one-page install and use guide for non-developers · [`파트너-가이드.html`](docs/파트너-가이드.html) — the partner guide: STEP 01–15 in ERP input order, real ERP and customer screenshots with numbered fields, captured 2026-10-15; a hand-made snapshot, so it does not regenerate when the screen dictionary is re-synced. In the public copy, staff names, product codes, other hotels, contact details, prices and hotel photos are masked · [`파트너-가이드-가격편.html`](docs/파트너-가이드-가격편.html) — pricing setup and maintenance, linked from the input guide · [`쉽게-보기/`](docs/쉽게-보기) — picture explainers for non-developers (open the HTML in a browser): [how the runner works](docs/쉽게-보기/레시피-요리사-손.html), [where child rates go](docs/쉽게-보기/아이-요금.html), [the first week](docs/쉽게-보기/일주일.html) |
| [`LICENSE`](LICENSE) | eoding Partner Use License v1.3 |

## Disclaimer

**Photo copyright is the user's responsibility.** Any photos these skills locate or download (from the hotel's
official website or elsewhere) must be checked for copyright and usage permission by the user (the travel agency)
before use. The provider of these skills accepts no responsibility for the rights status of any photo. Obtain the
hotel's permission before publishing photos on a sales page.

The generated guide is a working aid. Verify every value against the contract before entering it, and check room
inventory quantities against what was agreed with the hotel before selling. The runner copies what the guide says onto
the screen; it does not check that the guide matches the contract. To the extent permitted by law, the provider is not
liable for values, photos or inventory quantities entered into the ERP; the license states the exceptions.

## License

**eoding Partner Use License v1.3** — see [`LICENSE`](LICENSE); the Korean text governs. In short: customers and
partners with an eoding ERP account may use, copy and modify this repository internally to configure eoding ERP,
including having an AI agent enter values and upload photos with their own account; redistribution outside your
organization, resale, and use for other products are not permitted; no warranty. Values, photos and room inventory
quantities entered by an AI agent must be checked by the user before selling. Screen help is reference information and
does not guarantee how screens behave. Liability for eoding's wilful misconduct or gross negligence is not excluded.
The bundled Pretendard font is separately under the SIL Open Font License
([`skills/stay-setup-guide/scripts/fonts/LICENSE-Pretendard.txt`](skills/stay-setup-guide/scripts/fonts/LICENSE-Pretendard.txt)).

## Maintaining the price helpers

- One command runs every suite of the four helpers, Python and page tests:
  `NODE_PATH=<node_modules with jsdom> python3 scripts/run_price_helper_tests.py`. It runs on the Python that runs it
  (3.10+, so `python3.11 scripts/run_price_helper_tests.py` is a 3.11 run, the page tests' Python calls included), prints
  the Python, Node (18+) and jsdom it used, and fails when a suite fails, skips a test or cannot run. jsdom is not in this
  repository; the page tests were written against jsdom 22, and any folder where `npm install jsdom@22` ran will do.
- The page loader `skills/stay-price-change/scripts/page/stay_price_loader.js` runs only page files whose identity it
  knows: `stay_helper.js` and `stay_boot.js` of `stay-setup-run`, and `stay_price.js`, `stay_price_season.js`,
  `stay_addon_price.js`, `stay_charge.js` and `stay_promotion.js`. After changing any of the seven, a change to `stay-setup-run`'s two page files included, run
  `python3 skills/stay-price-change/scripts/loader_identity.py` and commit the loader in the same commit. The price
  calendar suite fails until you do, and a partner's tab refuses the files.
- Each helper's `SKILL.md` has a size budget in its `tests/test_docs.py`; detail goes to its `references/`.
- The ledger lives under `~/Documents`. When that folder is synced by a cloud service (for example iCloud "Desktop &
  Documents" on macOS, or OneDrive folder backup on Windows), set `STAY_PRICE_LEDGER_DIR` to a folder that is not synced
  and move the record folder there: a synced file can be evicted to the cloud or split into conflict copies. A command
  that finds work folders or pages in the record folder but no ledger file stops and says so instead of starting an empty
  ledger; `work` creates the ledger together with the first work folder.

## Repository rules

- This repository is public. Never commit real contracts, real prices, contact details, internal hostnames, internal
  paths, hotel or customer ids, person names, or credentials. Run `gitleaks` on the staged diff before committing.
- The example under `skills/stay-setup-guide/examples/` uses a real hotel's public facts (name, address, rooms,
  facilities from its official site and booking sites) with **sample rates, seasons and cancellation terms that are
  not an actual contract**. No real contract values are in this repository.
- A skill folder holds only what is visible on screen (field names, options, buttons, order) and the document format
  rules. No internal code, database or API structure.
- Bump every `version` field in the plugin manifests — `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json` and `.codex-plugin/plugin.json` — whenever a skill's `SKILL.md` version changes.
