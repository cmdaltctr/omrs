# Browser check (task 10.3)

Date: 2026-10-26. Branch `feat/open-experiment-in-marimo`. Browser: the Orca built-in browser, driven with `orca` commands.

## Set-up

The check used a scratch server. It did not use the live app on port 8765 or `~/.omrs`.

```sh
# <scratch> is a folder in the session scratchpad; <worktree> is this worktree.
grep -v -i openrouter_api_key ~/.config/omrs/omrs.jsonc > <scratch>/config/omrs.jsonc
(cd web && npm run build)
env -u OPENROUTER_API_KEY OMRS_CONFIG_DIR=<scratch>/config LANCEDB_URI=<scratch>/lance \
  uv run --no-sync omrs web --workspace <scratch>/ws --port 8842
orca tab create --worktree "path:<worktree>" --url about:blank --json
orca goto --page <id> --url "http://127.0.0.1:8842/#bootstrap=<token from the log>"
orca exec --page <id> --command "set viewport 1280 900 1"   # later "set viewport 390 844 1"
```

- The tab origin was `http://127.0.0.1:8842`, so the server needed no `--allow-origin`.
- The Library project was this worktree, added through the Add project form (50 experiments).
- marimo was the installed `uv tool` marimo 0.25.1 (`~/.local/bin/marimo`). It was registered through the Code editor form.
- The second Library project was a scratch project for the `.env` check (see `live-launch.md`).
- The server was stopped by its own workspace path (`pkill -f "omrs web --workspace <scratch>/ws"`). Port 8765 was not touched.

## Results

| # | Check | Width | Result |
| --- | --- | --- | --- |
| 1 | marimo not registered: "Open in marimo" is disabled, and the hint "Register marimo in Experiments, Code editor, to open notebooks." links to `#/experiments/code-editor` | 1280 | Pass |
| 2 | The hint link opens the Code editor section. The manifest path field holds `<worktree>/src/omrs/core/plugins/shipped/marimo/manifest.json` (from `shipped_manifests[0]`) | 1280 | Pass |
| 3 | Register real marimo 0.25.1 through the form, then Recheck: "marimo 0.25.1 is compatible", launchable | 1280 | Pass |
| 4 | Consent dialog: the text of design D3, a cleared checkbox, and "Open in marimo" disabled until the box is ticked | 1280, 390 | Pass |
| 5 | Consent is not remembered: the checkbox is cleared each time the dialog opens again | 1280, 390 | Pass |
| 6 | Experiment 34 (has `analysis.py`; marimo's tool environment has no jupytext): one alert line "marimo needs jupytext to convert analysis.py. Run `uv tool install "marimo>=0.25.1,<0.26" --with jupytext`, then open again." with "Try again". No file left in the folder, and the private convert folder is empty | 1280 | Pass |
| 7 | Experiment 14 (no `analysis.py`): the open makes a new tab at marimo's sign-in page. The card shows "marimo is open in a new tab", the address `http://127.0.0.1:2719/`, the one-time token with "Paste it into the marimo sign-in page.", "Open the editor tab again", "Created an empty notebook.", the shadowed packages (anyio, click, idna, jedi, pygments, starlette, uvicorn) and Stop | 1280 | Pass |
| 8 | Reload while the editor runs: the card "marimo is running for this experiment" with the address, "Open the editor tab", the token note and Stop. The token is not on the page | 390 | Pass |
| 9 | A second open while the editor runs: "marimo is already open for this experiment." and the running card | 390, 1280 | Pass |
| 10 | Stop through Confirm stop: the editor process, its kernel and the launch folder are gone, and the card goes away | 390, 1280 | Pass |
| 11 | After Stop, the "already open" line goes away too | 1280 | Pass after a fix (see below) |
| 12 | Second open of experiment 14: "Opened the existing notebook." | 1280 | Pass |
| 13 | Code editor running list: "marimo, project Dotenv check, experiment 14-liteparse-qasper-promotion-2026-06-29, http://127.0.0.1:2719/" with Stop. Stop from the list ends that launch | 1280 | Pass |
| 14 | No sideways scroll at 390 px: `scrollWidth` = `clientWidth` = 390 on the page, with the dialog open, and with the running card | 390 | Pass |
| 15 | At 390 px "Open in marimo" is full width in its row (358 px of 358 px). The dialog sits at x = 16 with width 358 | 390 | Pass |
| 16 | Focus returns to "Open in marimo" after the dialog closes (Escape, the X button and Cancel) | 1280 | Pass |

## Fix made during the check

Check 11 failed first. After an `editor_running` refusal and then Stop, the line "marimo is already open for this experiment." stayed on the page. A vitest test reproduced it (`clears the editor_running line when that editor is stopped` in `web/src/experiments/library/OpenInMarimo.test.tsx`) and failed. Stop on either card now also clears the refusal line. The test passed, and failed again when the fix was removed. The live re-check passed after a reload onto the new bundle.

## Harness notes (not product faults)

- The Orca tab draws a frame only when a screenshot is taken. A Radix dialog that closes keeps `data-state="closed"` and its exit animation until the next frame. So after Cancel, the dialog looked open until a screenshot. After the frame it was gone and focus was on "Open in marimo".
- A screenshot can reset the page scale. After that, `orca click` lands at twice the coordinates (on `<html>`). Running `set viewport <w> <h> 1` after each screenshot fixed this.
- A navigation that changes only the URL hash does not load a new bundle. Reload the tab after `npm run build`.
- marimo's sign-in form needed `form.requestSubmit()`; the Login click did not submit it.

Screenshots stay in the session scratchpad. They are not committed, because one of them shows a one-time editor token and others show home-folder paths.
