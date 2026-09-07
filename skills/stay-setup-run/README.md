# stay-setup-run — run the input guide in the browser

An agent skill that takes the **guide** produced by `stay-setup-guide`
(`<name>_입력지시서.html` — 지시서) and fills the ERP Stay screens step by step,
in the Chrome tab the user is already logged into. In coding terms: `stay-setup-guide` is the plan,
this skill is the execution. The guide and the screens are Korean, so the skill docs are Korean too.

`SKILL.md` is the authority on the procedure; the two files under `references/` are what it refers to.

**Three files, three roles.** The names are close; the roles are not.

| File | What it is | Who reads it | Where it lives |
|---|---|---|---|
| `<name>_입력지시서.html` | **지시서** — the guide, the one deliverable, carrying the check stamp | the person doing the setup, and this runner | `<name>/` (top level of the share folder) |
| `manual.md` | **원고** — the draft the guide is rendered from | `stay-setup-guide` only | `<name>/_원고/` |
| `steps.json` | **실행 계획** — the run plan extracted from the guide, generated, never hand-edited | this runner only | `<name>_실행/` |

> **Only a stamped, checker-passing guide runs.** `render_card.py` stamps the page it renders with
> `<meta name="stay-guide-stamp" content="v1;sha256=<sha256 of the draft>;check=ok|fail;rendered=<date>">`,
> where `check` is the verdict of `check_manual.py` on the same draft. `parse_guide.py` reads that stamp
> and exits **2** without opening a browser when the input is a `.md` draft, when the stamp is missing,
> when it says `check=fail`, or when the draft in the same share folder (`_원고/manual.md`, or `manual.md`
> in the old flat layout) no longer hashes to the stamp.
> Each refusal names the fix, and the fix is always on the guide side: fix the draft, re-render it with
> `render_card.py` and get the checker to pass. Editing the draft after the render therefore invalidates
> the guide by design.

> **Screens as of the production release of 2026-09-04.**
> A new hotel starts with **zero offers and zero rooms**: the first offer is created with [오퍼 추가]
> and the first room with [룸 추가], and every room is linked to an offer in the `판매 연결` card.
> Guides written for the older screens tell the runner to edit an existing offer or room row; the runner
> refuses those steps instead of clicking the wrong row, and asks for the guide to be regenerated. For
> those older screens use v0.2.x. Run `parse_guide.py --check` first: it makes the same judgement offline,
> before a browser is opened.
>
> The same release adds an **age-band panel** (`연령 구간`) to the offer tab and a conditional
> **per-age rate** card (`연령별 단가`) inside the charge drawer. Both are supported. Age ranges of one
> offer may not overlap, endpoints included, and `--check` blocks a guide where they do.
>
> The pass mark before a hotel goes on sale is **zero red and zero yellow** banner items. A step that
> dismisses a yellow item with a written reason is forbidden: the runner refuses it and `--check` blocks
> it before a browser is opened. A yellow item that remains is a defect in the guide and is fixed there.

Works with Claude Code, Codex, Gemini CLI, Grok, Hermes Agent, Cursor and any other agent that reads
the standard `SKILL.md` format **and can drive a browser**.

## Requirements

- Python 3.10+ for the parser. No Python packages to install.
- A tool that can drive the browser. The runner asks any browser agent for exactly three things, and the
  tool's name does not matter: **run JavaScript inside the logged-in ERP tab and get the value back**,
  **put a local file into a file input on that page**, and **take a screenshot**. Budget one JS call at
  45 seconds and one upload at 10MB.
  - **Claude Code (the Claude in Chrome extension) is the measured path** — seven hotels ran end to end on
    `javascript_tool`, `file_upload`, `computer` and the tab tools. The extension grants permission per site,
    so allow the ERP domain first.
  - **Codex (the Codex Chrome extension with developer mode / CDP) is untested.** We do not claim it works.
    Verify arbitrary JS evaluation with a returned value, per-site file-upload permission, and the per-call
    time limit before using it. A tool that cannot upload skips the photo steps; the log records them.
- Optional: Node.js, only to minify the two helper files with `esbuild` before injecting them, and to run
  the two browser tests. The originals work as they are.

## Install

**Claude Code plugin (recommended — it updates itself).** From the repository root README:
`/plugin marketplace add eoding/stay-setup-guide`, then `/plugin install stay-setup@eoding-stay`. The skill
is then invoked as `/stay-setup:stay-setup-run`.

**Copying the folder** also works and is the way to install into another agent:

```bash
git clone https://github.com/eoding/stay-setup-guide
cp -r stay-setup-guide/skills/stay-setup-run ~/.claude/skills/   # or ~/.codex/skills/, ~/.grok/skills/, .cursor/skills/
```

A copied skill does not update itself.

## Use

Open the ERP in Chrome, log in, and leave the tab on the hotel list (or on the edit screen of a hotel you
want to continue). Then give the agent the guide and the photo folder, with absolute paths.

```text
Use the stay-setup-run skill to run this guide in the browser.
Guide: /abs/path/<share_folder>/<share_folder>_입력지시서.html
Photos: /abs/path/<share_folder>/사진
Chrome tab: the hotel list page that is open now (already logged in)
Mode: 검토 (screenshot each step and ask before continuing)
```

The skill runs `parse_guide.py --check` before anything else. Exit 2 is the stamp gate above; exit 1 is an
unknown value, a missing photo file, a step the runner refuses, a step whose lines are in an order the screen
cannot render, or overlapping age ranges. Nothing opens a browser until `--check` is clean.

To continue an interrupted run, leave the hotel's edit screen open and say "continue this hotel" — the skill
reads `run-log.md` and resumes after the last `완료` step.

### Watching it go

The helper draws a small strip in the **top-right corner of the ERP page** and `runStep` keeps it current, so
anyone looking at the screen sees `12 / 77 · 지금: 룸 만들기 (2번째, 씨뷰 빌라) · 완료 11 · 건너뜀 1`. It is
green while running, red with the failing step's title when a step breaks, grey `끝` when done. It never
intercepts a click and re-attaches itself when the page swaps its body; the ✕ dismisses it.

Open the guide HTML in a second tab of the same browser and the ticks rise there too: the agent calls
`stayGuide.mark([{no, status, note}, …])` after each batch, which fills the sticky 진행 현황 header and the
per-step badge (대기 / 진행 중 / 완료 / 건너뜀 / 실패 / 확인 필요). Ticking a box by hand still works and is
recorded as `완료 (수동)`. `stayGuide.export()` returns the whole state as JSON for the run log. If the guide
tab is not open the agent skips this silently. Neither display changes the run.

Outputs land next to the share folder in `<share_folder>_실행/`: `steps.json` (the run plan — generated,
not hand-edited), `parse.txt` (the pre-flight summary), `run-log.md` (one line per step, plus a closing
section listing guide defects and any dangerous button a supervisor pressed) and `_inject/` (the minified
helper files uploaded into the page). Nothing in that folder is handed to anyone; the deliverable is the
guide in the share folder.

## Folder

| Path | Contents |
|---|---|
| `SKILL.md` | Entry point: inputs → parse → inject helper → step loop → failure handling → rules → report |
| `scripts/parse_guide.py` | Stamped guide HTML → `steps.json` (the run plan), checking the stamp, photo files, value kinds, line order and age-band overlap |
| `scripts/stay_helper.js` | In-page helper `stayRun`: find fields by label, set values by kind, add repeat rows, press a button and wait for the response, read values back, move uploaded files into the right file input, draw the progress strip |
| `scripts/stay_boot.js` | In-page runner built on the helper: `step`, `stepFields`, `titleHint`, `existsInList`, `checkGuide`, `runStep`, `runStepCore`, `runCellStep`, `runCheckStep`, `progressReset` |
| `references/screen-mechanics.md` | Step kind → screen map, how each screen opens and saves, traps |
| `references/run-log-spec.md` | `run-log.md` format, result words, resuming |
| `tests/test_parse_guide.py` | Parser tests — the stamp gate, refusals, photo and value checks |
| `tests/test_helper.mjs` · `tests/helper_fixture.html` | Helper tests on a fixture page — drawer forms, danger buttons |
| `tests/test_boot.mjs` · `tests/calendar_fixture.html` | Boot tests on a fixture page — price-calendar cells, openers, refusals, 0-step checks |

```bash
python3 -m unittest discover -s tests            # parser
node tests/test_helper.mjs                       # helper
node tests/test_boot.mjs                         # boot
```

The two browser tests skip themselves with exit code 0 when `jsdom` is not installed; nothing is installed
for you. To borrow a jsdom from elsewhere, set `NODE_PATH` to the `node_modules` that has it.

## Disclaimer

**A person must check the values before selling.** The skill copies what the guide says onto the screen. It does
not check that the guide matches the contract, or that what landed on screen is correct. The provider accepts no
responsibility for values entered into the ERP.

**The agent never presses [판매 시작] (start selling).** The helper refuses that button in every case, `force`
included. Reviewing the validation banner and starting the sale is the user's decision.

Dangerous buttons (delete, archive, close a month, make shared, delete a group, end sale) are refused by the runner,
as is any button carrying a confirmation dialog. If the guide asks for one, a supervising agent or person checks the
target row and presses it, and the run log records it.

**Photo copyright is the user's responsibility.**

## Limits

- If a screen changes, a field may not be found. The skill stops and reports what it could not find. It never invents a value.
- It does not log in, and it does not know the ERP address — the user supplies both. If the session expires it stops and asks.
- The runner never converts a currency or an amount. It enters what the guide says, and it stops before creating a
  hotel whose supply currency is not USD until the user confirms that currency.
- Photos must be in a folder the browser tool can read, and uploads are capped at 10MB per batch.
- Browser tools that cannot handle a file dialog skip the photo steps; the log records them.

## License

**eoding Partner Use License** — see `LICENSE` at the repository root. Customers and partners with an eoding ERP
account may use, copy and modify this repository internally to configure eoding ERP; redistribution outside your
organization, resale, and use for other products are not permitted; no warranty.
