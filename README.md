# stay-setup-guide

Two agent skills for travel-agency staff. From a hotel contract (rate sheet) file alone, `stay-setup-guide`
produces a step-by-step **입력지시서** — an input guide as one HTML file, the deliverable a person follows on the
ERP Stay screens — plus a photo folder and a list of the values that need a human decision. `stay-setup-run` then
takes that same guide and fills the ERP Stay screens automatically, in the Chrome tab the user is already logged
into, one step at a time. **[판매 시작] (start selling) is always pressed by a person**, never by the skills. The
guides and the skill documents are Korean because the ERP screens are Korean.

Current release: plugin `stay-setup` 1.6.1 (`stay-setup-guide` 1.6.1, `stay-setup-run` 0.13.1).

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
`/stay-setup:stay-setup-guide` and `/stay-setup:stay-setup-run`.

**Codex plugin.** In the Codex app or terminal Codex:

```
codex plugin marketplace add eoding/stay-setup-guide
codex plugin add stay-setup@eoding-stay
```

Pick up a new release with `codex plugin marketplace upgrade`. Codex covers guide creation and entering the values
by hand; automatic entry on Codex is 실측 전, not yet verified.

**Copying the folders** also works and is the way to install into an agent that is neither Claude Code nor Codex:
put `skills/stay-setup-guide` and `skills/stay-setup-run` into the tool's skills directory (`~/.claude/skills/`,
`~/.codex/skills/`, `.cursor/skills/`, and so on). A copied skill does not update itself.

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
banner. The pass mark is zero red and zero yellow items. Then press [판매 시작] yourself.

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
