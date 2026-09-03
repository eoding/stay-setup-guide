# stay-setup-guide

An agent skill for travel-agency staff: from a hotel contract (rate sheet) file alone, it produces a step-by-step **input guide (HTML)** for the ERP Stay screens plus a photo folder. The guide is written in Korean because the ERP screens are Korean.

Works with Claude Code, Codex, Gemini CLI, Grok, Hermes Agent, Cursor and any other agent that reads the standard `SKILL.md` skill format.

| Path | Contents |
|---|---|
| [`skills/stay-setup-guide`](skills/stay-setup-guide) | The skill: procedure (`SKILL.md`), format rules, screen dictionary, facts guide, a fictional example, converter/checker/renderer scripts |

## Requirements

- Python 3.10+ (the skill's scripts are pure Python; converter packages install themselves on first run)
- An agent that can read/write files, run a terminal command, and fetch web pages (for hotel facts and photos)

The skill's scripts do not need Node.js (the optional `npx skills` installer below is a separate tool). Contract formats: xlsx, xlsm, xls, ods, csv, pdf, docx, pptx, odt, rtf, epub, hwp, hwpx.

## Install

### Universal (recommended)

Uses the [`skills`](https://github.com/vercel-labs/skills) CLI, which installs into every agent it finds on your machine (Claude Code, Codex, Gemini CLI, Grok, Cursor, Cline, Amp and more).

```bash
npx skills add eoding/stay-setup-guide            # current project
npx skills add eoding/stay-setup-guide --global   # your user account
```

Update later with `npx skills update`.

### Hermes Agent

```bash
hermes skills install eoding/stay-setup-guide/skills/stay-setup-guide --yes
hermes skills list
```

Update with `hermes skills update stay-setup-guide`.

### Claude Code

Either the universal command above, or copy the folder:

```bash
git clone https://github.com/eoding/stay-setup-guide
cp -r stay-setup-guide/skills/stay-setup-guide ~/.claude/skills/     # personal
# or into a project:  .claude/skills/stay-setup-guide
```

Invoke it with `/stay-setup-guide` or just describe the task.

### Codex

Codex reads `~/.codex/skills/<name>/SKILL.md` (user) and `.codex/skills/` or `.agents/skills/` (project).

```bash
git clone https://github.com/eoding/stay-setup-guide
cp -r stay-setup-guide/skills/stay-setup-guide ~/.codex/skills/
```

### Gemini CLI

```bash
gemini skills install https://github.com/eoding/stay-setup-guide --path skills/stay-setup-guide
gemini skills list
```

The default scope is your user account. Add `--scope workspace` to install into the current workspace only.

### Grok

Grok reads `~/.grok/skills/<name>/SKILL.md`. The universal command above places it there; or copy the folder:

```bash
git clone https://github.com/eoding/stay-setup-guide
cp -r stay-setup-guide/skills/stay-setup-guide ~/.grok/skills/
```

### Cursor and others

Copy `skills/stay-setup-guide` into the tool's skills directory (for Cursor: `.cursor/skills/`), or use the universal command.

## Use

Put the contract file in a folder and ask the agent. Use absolute paths.

```text
Use the stay-setup-guide skill to build the full ERP Stay input guide for this hotel.
Contract: /abs/path/input/rates.xlsx. Hotel name <name>, city <city>, supply currency USD,
contract party 자사, share folder name <share_folder>. Write outputs to /abs/path/output/<share_folder>/.
Do not invent any rule, surcharge or value that is not in the contract.
```

Hermes one-shot form:

```bash
hermes -z "<the prompt above>" --skills stay-setup-guide
```

Outputs: `<share_folder>_입력지시서.html` (the guide, with copy buttons), `사진/` (photos), `manual.md`, `rules.md`, `facts.json`, and `changes.md` (every value the agent decided differently from the contract, for review).

On first run, `scripts/convert_contract.py` installs three Python packages into the current Python environment (`firecrawl-anydoc`, `rhwp-python`, `openpyxl`) and prints a notice before doing so.

## Disclaimer

**Photo copyright is the user's responsibility.** Any photos this skill locates or downloads (from the hotel's official website or elsewhere) must be checked for copyright and usage permission by the user (the travel agency) before use. The provider of this skill accepts no responsibility for the rights status of any photo. Obtain the hotel's permission before publishing photos on a sales page.

The generated guide is a working aid. Verify every value against the contract before entering it; the provider is not liable for values entered into the ERP.

## License

MIT. See `LICENSE`. The bundled Pretendard font is under the SIL Open Font License (`skills/stay-setup-guide/scripts/fonts/LICENSE-Pretendard.txt`).

## Repository rules

- This repository is meant to be public. Never commit real contracts, real prices, contact details or company names. The example under `examples/` uses a real hotel's public facts (name, address, rooms, facilities from its official site and booking sites) with **sample rates, seasons and cancellation terms that are not an actual contract**. No real contract values are in this repository.
- A skill folder holds only what is visible on screen (field names, options, buttons, order) and the document format rules. No internal code, database or API structure.
- Later phases of this project (verification tools, MCP server) will live in this repository next to the skill.
