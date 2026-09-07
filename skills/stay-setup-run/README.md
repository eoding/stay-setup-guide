# stay-setup-run — run the input guide in the browser

An agent skill that takes the **guide** produced by `stay-setup-guide`
(`<name>_입력지시서.html` — 지시서) and fills the ERP Stay screens step by step,
in the Chrome tab the user is already logged into. In coding terms: `stay-setup-guide` is the plan,
this skill is the execution. The guide and the screens are Korean, so the skill docs are Korean too.

**Three files, three roles.** The names are close; the roles are not.

| File | What it is | Who reads it | Where it lives |
|---|---|---|---|
| `<name>_입력지시서.html` | **지시서** — the guide, the one deliverable, carrying the check stamp | the person doing the setup, and this runner | `<name>/` (top level of the share folder) |
| `manual.md` | **원고** — the draft the guide is rendered from | `stay-setup-guide` only | `<name>/_원고/` |
| `steps.json` | **실행 계획** — the run plan extracted from the guide, generated, never hand-edited | this runner only | `<name>_실행/` |

Works with Claude Code, Codex, Gemini CLI, Grok, Hermes Agent, Cursor and any other agent that reads
the standard `SKILL.md` format **and can drive a browser**.

`SKILL.md` is the authority on the procedure; the two files under `references/` are what it refers to.

> **Screens as of the production release of 2026-09-04.**
> For older screens use v0.2.x.
> A new hotel now starts with **zero offers and zero rooms**: the first offer is created with [오퍼 추가]
> and the first room with [룸 추가], and every room including the first is linked to an offer in the
> `판매 연결` card. Guides written for the older screens tell the runner to edit a `기본 오퍼` offer or a
> `스탠다드` room row; the runner refuses those steps instead of clicking the wrong row, and asks for the
> guide to be regenerated. Run `parse_guide.py --check` first: it makes that same judgement offline,
> before a browser is opened.
>
> The 2026-09-04 release also adds an **age-band panel** (`연령 구간`) to the offer tab and a
> conditional **per-age rate** card (`연령별 단가`) inside the charge drawer. Both are supported.
>
> The pass mark before a hotel goes on sale is **zero red and zero yellow** banner items. The
> `경고 넘어가기` step, which used to dismiss a yellow item with a written reason, is forbidden: the
> runner refuses it and `parse_guide.py --check` blocks it before a browser is opened. A yellow item
> that remains is a defect in the guide and is fixed there.

> **Only a checked HTML guide runs.** `render_card.py` stamps the page it renders with
> `<meta name="stay-guide-stamp" content="v1;sha256=<sha256 of the draft>;check=ok|fail;rendered=<date>">`,
> where `check` is the verdict of `check_manual.py` on the same draft. `parse_guide.py` reads that stamp
> and exits **2** without opening a browser when the input is a `.md` file, when the stamp is missing,
> when it says `check=fail`, or when the draft in the same share folder (`_원고/manual.md`, or `manual.md`
> in the old flat layout) no longer hashes to the stamp.
> Each refusal names the fix, and the fix is always on the guide side: fix the draft, re-render it with
> `render_card.py` and get the checker to pass. Editing the draft after the render therefore invalidates
> the guide by design.

## Requirements

- Python 3.10+ for the parser. No Python packages to install.
- A tool that can drive the browser: Claude in Chrome, Playwright MCP, or an equivalent. It must be able to
  run JavaScript in the page, take screenshots, and upload a local file into a file input.
- Optional: Node.js, only to minify the two helper files with `esbuild` before injecting them. The originals work as they are.

## Install

### Universal (recommended)

```bash
npx skills add eoding/stay-setup-guide            # current project
npx skills add eoding/stay-setup-guide --global   # your user account
```

### Hermes Agent

```bash
hermes skills install eoding/stay-setup-guide/skills/stay-setup-run --yes
hermes skills list
```

### Claude Code, Codex, Grok, Cursor

Copy this folder into the tool's skills directory:

```bash
git clone https://github.com/eoding/stay-setup-guide
cp -r stay-setup-guide/skills/stay-setup-run ~/.claude/skills/   # or ~/.codex/skills/, ~/.grok/skills/, .cursor/skills/
```

Invoke it with `/stay-setup-run` or just describe the task.

## Use

Open the ERP in Chrome, log in, and leave the tab on the hotel list (or on the edit screen of a hotel you
want to continue). Then give the agent the guide folder and the photo folder, with absolute paths.

```text
Use the stay-setup-run skill to run this guide in the browser.
Guide: /abs/path/<share_folder>/<share_folder>_입력지시서.html
Photos: /abs/path/<share_folder>/사진
Chrome tab: the hotel list page that is open now (already logged in)
Mode: 검토 (screenshot each step and ask before continuing)
```

To continue an interrupted run, leave the hotel's edit screen open and say "continue this hotel" — the skill
reads `run-log.md` and resumes after the last `완료` step.

Outputs land next to the share folder in `<share_folder>_실행/`: `steps.json` (the run plan — generated,
not hand-edited), `parse.txt` (the pre-flight summary), `run-log.md` (one line per step, plus a closing
section listing guide defects and any dangerous button a supervisor pressed) and `_inject/` (the minified
helper files uploaded into the page). Nothing in that folder is handed to anyone; the deliverable is the
guide in the share folder.

## Folder

| Path | Contents |
|---|---|
| `SKILL.md` | Entry point: inputs → parse → inject helper → step loop → failure handling → rules → report |
| `scripts/parse_guide.py` | Stamped guide HTML → `steps.json` (the run plan), checking the stamp, photo files and value kinds |
| `scripts/stay_helper.js` | In-page helper `stayRun`: find fields by label, set values by kind, add repeat rows, press a button and wait for the response, read values back, move uploaded files into the right file input |
| `scripts/stay_boot.js` | In-page runner built on the helper: `step`, `stepFields`, `titleHint`, `existsInList`, `checkGuide`, `runStep`, `runCellStep`, `runCheckStep` |
| `references/screen-mechanics.md` | Step kind → screen map, how each screen opens and saves, traps |
| `references/run-log-spec.md` | `run-log.md` format, result words, resuming |
| `tests/` | Parser tests, and two fixture pages with browser tests (run only when jsdom is present) |

```bash
python3 -m unittest discover -s tests            # parser
node tests/test_helper.mjs                       # helper — drawer forms, danger buttons
node tests/test_boot.mjs                         # boot — price-calendar cells, openers, refusals, 0-step checks
```

The two browser tests skip themselves with exit code 0 when `jsdom` is not installed; nothing is installed
for you. To borrow a jsdom from elsewhere, set `NODE_PATH` to the `node_modules` that has it.

## Disclaimer

**A person must check the values before selling.** The skill copies what the guide says onto the screen. It does
not check that the guide matches the contract, or that what landed on screen is correct. The provider accepts no
responsibility for values entered into the ERP.

**The agent never presses [판매 시작] (start selling).** The helper refuses that button in every case, `force`
included. Reviewing the validation banner and starting the sale is the user's decision.

Dangerous buttons (delete, archive, close a month, make shared, delete a group, end sale) are refused by the runner.
If the guide asks for one, a supervising agent or person checks the target row and presses it, and the run log records it.

**Photo copyright is the user's responsibility.**

## Limits

- If a screen changes, a field may not be found. The skill stops and reports what it could not find. It never invents a value.
- It does not log in. If the session expires it stops and asks the user.
- Photos must be in a folder the browser tool can read, and uploads are capped at 10MB per batch.
- Browser tools that cannot handle a file dialog skip the photo steps; the log records them.

## License

**eoding Partner Use License** — see `LICENSE` at the repository root. Customers and partners with an eoding ERP
account may use, copy and modify this repository internally to configure eoding ERP; redistribution outside your
organization, resale, and use for other products are not permitted; no warranty.
