# stay-setup-guide

Two agent skills for travel-agency staff. From a hotel contract (rate sheet) file alone, `stay-setup-guide`
produces a step-by-step **입력지시서** — an input guide as one HTML file, the deliverable a person follows on the
ERP Stay screens — plus a photo folder and a list of the values that need a human decision. `stay-setup-run` then
takes that same guide and fills the ERP Stay screens automatically, in the Chrome tab the user is already logged
into, one step at a time. **[판매 시작] (start selling) is always pressed by a person**, never by the skills. The
guides and the skill documents are Korean because the ERP screens are Korean.

## Install

**Claude Code plugin (recommended — it updates itself).** In Claude Code, the CLI or the desktop app's Code tab:

```
/plugin marketplace add eoding/stay-setup-guide
/plugin install stay-setup@eoding-stay
```

Then open `/plugin` → **Marketplaces** and turn on auto-update for `eoding-stay`. The skills are invoked as
`/stay-setup:stay-setup-guide` and `/stay-setup:stay-setup-run`.

**Copying the folders** also works and is the way to install into an agent that is not Claude Code: put
`skills/stay-setup-guide` and `skills/stay-setup-run` into the tool's skills directory (`~/.claude/skills/`,
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
- Other agents that read the standard `SKILL.md` format (Codex, Gemini CLI, Grok, Cursor, Hermes Agent) can produce
  the guide. **Automatic entry on Codex is not yet verified** — we do not claim it works. `skills/stay-setup-run`
  lists the three browser capabilities to confirm before trying it.
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

Per-hotel wall-clock time in production runs, photos included:

| Automatic entry, one hotel | 13–19 minutes |
|---|---|

At the end, read the validation banner. The pass mark is zero red and zero yellow items. Then press [판매 시작]
yourself.

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
- **The screen baseline is 운영 2026-09-04 배포판**, 27 screens. A new hotel starts empty: zero offers, zero rooms,
  zero sale links, and the room-link drawer stays blocked until the first offer exists. When the ERP screens change,
  both skills must be re-audited and the screen dictionary regenerated; the runner refuses steps written for older
  screens rather than clicking the wrong row.

## Repository layout

| Path | Contents |
|---|---|
| [`.claude-plugin/`](.claude-plugin) | Plugin and marketplace manifests (`plugin.json`, `marketplace.json`); bump both `version` fields when a skill version changes |
| [`skills/stay-setup-guide`](skills/stay-setup-guide) | The guide skill: procedure (`SKILL.md`), draft format rules, screen dictionary, facts guide, a worked example, converter/checker/renderer scripts |
| [`skills/stay-setup-run`](skills/stay-setup-run) | The runner skill: parser, in-page helper and boot scripts, screen mechanics, run-log format |
| [`docs/`](docs) | [`설치-사용-안내.md`](docs/설치-사용-안내.md) — the one-page install and use guide for non-developers |
| [`LICENSE`](LICENSE) | eoding Partner Use License |

## Disclaimer

**Photo copyright is the user's responsibility.** Any photos these skills locate or download (from the hotel's
official website or elsewhere) must be checked for copyright and usage permission by the user (the travel agency)
before use. The provider of these skills accepts no responsibility for the rights status of any photo. Obtain the
hotel's permission before publishing photos on a sales page.

The generated guide is a working aid. Verify every value against the contract before entering it. The runner copies
what the guide says onto the screen; it does not check that the guide matches the contract. The provider is not
liable for values entered into the ERP.

## License

**eoding Partner Use License** — see [`LICENSE`](LICENSE). In short: customers and partners with an eoding ERP
account may use, copy and modify this repository internally to configure eoding ERP; redistribution outside your
organization, resale, and use for other products are not permitted; no warranty. The bundled Pretendard font is
separately under the SIL Open Font License
([`skills/stay-setup-guide/scripts/fonts/LICENSE-Pretendard.txt`](skills/stay-setup-guide/scripts/fonts/LICENSE-Pretendard.txt)).

## Repository rules

- This repository is public. Never commit real contracts, real prices, contact details, internal hostnames, internal
  paths, hotel or customer ids, person names, or credentials. Run `gitleaks` on the staged diff before committing.
- The example under `skills/stay-setup-guide/examples/` uses a real hotel's public facts (name, address, rooms,
  facilities from its official site and booking sites) with **sample rates, seasons and cancellation terms that are
  not an actual contract**. No real contract values are in this repository.
- A skill folder holds only what is visible on screen (field names, options, buttons, order) and the document format
  rules. No internal code, database or API structure.
- Bump the `version` in both `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` whenever a skill's
  `SKILL.md` version changes.
