# Stay Setup Guide

Set up hotels and update prices in eoding ERP Stay. Start with a hotel contract and a folder of photos. The setup guide turns them into an HTML guide you can follow yourself or hand to the setup runner.

See [GitHub Releases](https://github.com/eoding/stay-setup-guide/releases) for published release notes.

## Install

Install Python 3.10 or later for the guide scripts. The contract converter prints a notice before installing missing packages on first use. See the [staff installation guide](docs/%EC%84%A4%EC%B9%98-%EC%82%AC%EC%9A%A9-%EC%95%88%EB%82%B4.md) for help setting up your computer.

### Claude Code

In a Claude Code session, run these commands.

```text
/plugin marketplace add eoding/stay-setup-guide
/plugin install stay-setup@eoding-stay
```

Choose an installation scope when prompted. If Claude Code asks you to reload, run `/reload-plugins`. Manage updates in `/plugin`. See [Claude Code plugin setup](https://code.claude.com/docs/en/plugins/install).

### Codex

Run these commands in a terminal. Use `stay-setup-guide` to prepare your guide, then enter the values by hand in ERP. Browser automation in Codex remains unverified.

```sh
codex plugin marketplace add eoding/stay-setup-guide
codex plugin add stay-setup@eoding-stay
```

To refresh this marketplace, run `codex plugin marketplace upgrade eoding-stay`.

### Other agents

If your agent supports `SKILL.md` files, copy all six folders from [`skills/`](skills) into its skills directory. Keep them side by side. The price helpers share files across folders. Update copied folders yourself when you adopt a new release.

## Use

| Skill | Use it to |
| --- | --- |
| [`stay-setup-guide`](skills/stay-setup-guide) | Build and check an HTML input guide from a hotel contract. |
| [`stay-setup-run`](skills/stay-setup-run) | Enter the checked guide in ERP through a signed-in browser tab. |
| [`stay-price-change`](skills/stay-price-change) | Change room prices or match a rate sheet in the price calendar. |
| [`stay-addon-price-change`](skills/stay-addon-price-change) | Change an add-on's selling price or supply cost. |
| [`stay-charge-change`](skills/stay-charge-change) | Change a charge amount or rate, including time bands, age bands, and amounts paid at the hotel. |
| [`stay-promotion-change`](skills/stay-promotion-change) | Update a promotion's discount amount, percentage, or free-night count. |

### Set up a hotel

1. Put the contract or rate sheet and the photos in one folder. Ask the agent to create a guide. The converter accepts spreadsheets, PDFs, Word files, and HWP files.
2. Open the HTML guide and its photo folder. Read `changes.md` for values you need to confirm and departures from the contract. Verify prices, dates, cancellation terms, and room inventory against the contract or the hotel's confirmation.
3. Follow the HTML guide in ERP by hand, or use the setup runner in Claude Code with the [Claude in Chrome extension](https://code.claude.com/docs/en/chrome). This is the browser setup used for verified hotel installations. Open the hotel list in a signed-in Chrome tab and grant the extension access to the ERP site. The runner accepts a checked HTML guide with its verification stamp. If the guide changes or fails its check, correct the draft and render a new HTML guide.
4. Check the saved setup and the ERP validation banner. Clear all red and yellow items except the advisory warning for adjacent offers. A staff member selects **Start selling**. The runner stops before that action.

The checker validates the guide's format and supported ERP field rules. It can flag amounts missing from the contract when given the extracted contract text. You are responsible for comparing the guide with the contract and getting permission to use the photos.

```text
/stay-setup:stay-setup-guide Create a setup guide from the rate sheet and photos in this folder.
/stay-setup:stay-setup-run Enter the checked HTML guide in the ERP tab I have open.
```

### Changing the prices of a hotel that already sells

Open the hotel's edit page in a signed-in Chrome tab. Name the price, the change you want, and its scope. If two items have the same name, specify the room, rate plan, or offer.

```text
/stay-setup:stay-price-change Raise the January room-only selling price by 10% for the standard room.
/stay-setup:stay-addon-price-change Increase the breakfast add-on selling price by 5,000 KRW.
/stay-setup:stay-charge-change Change the late checkout rate from 50% to 60%.
/stay-setup:stay-promotion-change Change the early booking discount from 10% to 12%.
```

Review the preview and resolve flagged changes before confirming. The helper saves only after you send the requested confirmation. It rereads the saved prices and keeps a local record of the change. To restore recorded values, ask the helper to roll back the change by its ledger record number. To store the ledger outside a synced Documents folder, set `STAY_PRICE_LEDGER_DIR`.

Promotion changes require an ERP that preserves settings outside the edit form. The promotion helper has been tested on fixtures. Read its [instructions](skills/stay-promotion-change/SKILL.md) before applying a change.

#### Refill a season

The price helper previews what the ERP will change or create for every date in a season. Review the affected dates before confirming. The helper rereads each save range immediately before saving. The save can overwrite edits made after that read. Coordinate with anyone editing the same prices.

Rollback restores recorded calendar values. Newly created cells remain. Season refill has been tested against ERP rules and fixtures. See the [season refill instructions](skills/stay-price-change/references/season-fill.md) for the workflow and its limits.

## Optional room inventory

Add inventory only when the contract or the hotel gives an agreed total for each sale link and stay night. Use that total. ERP calculates the remaining inventory. A total of zero closes the night. For a link that sells by quantity, a blank night is unavailable. See the [inventory guide](skills/stay-setup-guide/references/inventory-guide.md) for setup and checks.

## Screen help

Use the [partner screenshot guide](docs/%ED%8C%8C%ED%8A%B8%EB%84%88-%EA%B0%80%EC%9D%B4%EB%93%9C.html) to find fields and see how they appear to guests. The [partner pricing guide](docs/%ED%8C%8C%ED%8A%B8%EB%84%88-%EA%B0%80%EC%9D%B4%EB%93%9C-%EA%B0%80%EA%B2%A9%ED%8E%B8.html) covers first setup and price maintenance. Compare the screenshots with the ERP screen you are using.

For a field or screen lookup, use `explain_field.py`. Enter the field or screen name as it appears in ERP.

```sh
python3 skills/stay-setup-guide/scripts/explain_field.py '<field name>' --screen '<screen name or ID>'
```

Read the [operations FAQ](skills/stay-setup-guide/references/operations-guide.md), [pricing rules](skills/stay-setup-guide/references/price-guide.md), and [customer options guide](skills/stay-setup-guide/references/customer-options-guide.md) for contract details and screen behavior. The [illustrated guides](docs/%EC%89%BD%EA%B2%8C-%EB%B3%B4%EA%B8%B0) explain setup, child rates, and the runner.

## Maintaining the price helpers

Run the four helper suites with Python 3.11, Node.js 18 or later, and a local copy of jsdom. Point `NODE_PATH` at its `node_modules` directory.

```sh
NODE_PATH=/path/to/node_modules python3.11 scripts/run_price_helper_tests.py
```

After changing a browser script used by the price loader, run `python3 skills/stay-price-change/scripts/loader_identity.py` and commit the regenerated loader with the script. The [setup guide maintenance instructions](skills/stay-setup-guide/README.md) explain how to refresh the screen dictionary from ERP. Use [the runner's fixture sync script](skills/stay-setup-run/scripts/sync_erp_fixtures.py) to update the captured views.

## Repository rules

Keep contracts, real prices, hotel and customer identifiers, contact information, internal paths, and credentials out of this public repository. Scan staged changes with `gitleaks`. Keep the [Claude Code](.claude-plugin) and [Codex](.codex-plugin) manifests in sync when releasing a skill. The [Codex marketplace manifest](.agents/plugins/marketplace.json) points to the same plugin.

## License

The [eoding Partner Use License v1.3](LICENSE) permits internal use by eoding ERP customers and partners and sets the terms for copying, modification, and redistribution. The Korean text governs. The bundled [Pretendard font](skills/stay-setup-guide/scripts/fonts/LICENSE-Pretendard.txt) has a separate license.
