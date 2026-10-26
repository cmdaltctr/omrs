# Browser check: install marimo from the Integrations page (task 8.3)

- **Date:** 2026-10-26
- **Branch:** `feat/install-marimo-from-integrations` at `7570a842`
- **Browser:** the Orca embedded browser, one tab, signed in with the scratch server's own link.
- **Server:** a scratch `omrs web` on port 8790. It never used the live app on port 8765 or `~/.omrs`.

```bash
UV_TOOL_DIR=<scratch>/uv-tools UV_TOOL_BIN_DIR=<scratch>/uv-bin OMRS_CONFIG_DIR=<scratch>/config \
  uv run --no-sync omrs web --workspace <scratch>/ws --port 8790 --experiment-root <scratch>/experiments
```

`<scratch>` is a folder in the session scratchpad. The install downloaded marimo into it. The real
`~/.local/share/uv/tools/marimo/uv-receipt.toml` and `~/.local/bin/marimo` kept their date
(13 October) for the whole check. The server's `PATH` did not hold `<scratch>/uv-bin`.

## Results

| Step | Width | Result |
|---|---|---|
| Open Integrations. The marimo card is under "External tools", below the extras. | 1280 | Pass. "Not installed", the purpose, Install and the copy command `uv tool install "marimo>=0.25.1,<0.26.0" --with jupytext`. |
| Install opens the confirm dialog. | 1280 | Pass. It names the command, says marimo goes into its own uv tool environment outside OMRS, says no restart is needed, and says the install does not register marimo. |
| Cancel the dialog. | 1280 | Pass. No request reached the install route, and focus returned to "Install marimo". |
| Confirm the install. | 1280 | Pass. The progress line "Installing marimo. This can take a few minutes." showed, then "Installed", version 0.25.2, the executable path in `<scratch>/uv-bin`, and "Register marimo in Experiments, Code editor." with a link. |
| The scratch receipt after the install. | n/a | Pass. `requirements = [{ name = "marimo", specifier = ">=0.25.1,<0.26.0" }, { name = "jupytext" }]`, which is the D7 card shape. The card offered Uninstall. |
| Follow the Code editor link. | 1280 | Pass. It opened `#/experiments/code-editor`. The form held the shipped manifest path and the found executable path. |
| Tick approval and press Register. | 1280 | Pass. Registration of the path off the server `PATH` succeeded (D5). The page called the recheck route once (one `recheck` line in the server log) and showed "Compatible, marimo 0.25.2". |
| Open an editor (scratch experiment, starter notebook), then try Install and Uninstall. | 1280 | Pass. Uninstall answered 409 `editor-running` and its button was disabled with the line "A marimo editor that OMRS started is running...". Install answered 409 `already-installed`, because the contract checks `ready` first. |
| Same, with jupytext hidden in the scratch tool environment for a moment (`needs-jupytext`). | 1280 | Pass. The card showed "Needs jupytext", the line about `analysis.py`, and the red caution naming 0.25.2. Install and Uninstall were disabled, and Install answered 409 `editor-running`. jupytext was put back. |
| `#/integrations/marimo` link. | 1280 | Pass. The card took focus. |
| Stop the editor, then Uninstall. | 1280 | Pass. The dialog says the whole marimo tool environment goes and that a registration then shows as unavailable. The card showed "Uninstalling marimo...", then "Not installed". |
| Install with `<scratch>/uv-bin` made read-only, so uv fails. | 390 | Pass. The dialog fitted (16 px to 374 px). The card showed "The install failed. The last output lines are below.", Retry, and the output lines in their own scroll box. Page width stayed 390 px. |
| Retry with the folder writable again. | 390 | Pass. The progress line fitted (right edge 357 px), then "Installed" with the long executable path wrapped. No element went past 390 px. |
| Open an editor while the marimo uninstall job runs. | 390 | Pass. 409 `tool_install_running` with "marimo is being installed or removed on the Integrations page. Wait until that job ends, then open again." No marimo process started, and no new credential was issued (the only listed one was the earlier, revoked editor credential). |
| "Not installed" badge colour (extras and marimo). | 1280, 390 | Pass. Every "Not installed" badge uses the error (red) variant, as "Installed" uses green. |

## Contrast of the status badges (WCAG 2.1, text against the badge background over the card)

| Theme | "Not installed" (error) | "Installed" (success) |
|---|---|---|
| Dark | 5.67:1 | 6.85:1 |
| Light | 5.96:1 | 4.94:1 |

Every value passes AA for normal text (4.5:1). The marimo card uses the same badge variant on the same card background.

## Notes on the test pane

- The Orca pane ran at about two frames a second while it was not in front. A dialog exit
  animation therefore took a few seconds, and the closed dialog stayed drawn until it ended.
  After it ended, the dialog unmounted and focus returned to the Install button. This is the
  pane, not the page.
- Orca `keypress Escape` and `click` on a snapshot ref did not reach the page in this pane.
  A key event sent inside the page closed the dialog, and DOM clicks drove the buttons.
- One light-theme screenshot caught the Install button in the middle of the theme colour
  transition, so it looked faded. A second screenshot after the transition showed the normal
  button, which is the same `Button` as the extras card.

## Defects found

None in the page. One stale line found while building the card was fixed before this check:
the page note for a server that cannot install extras said "This server cannot install from the
app", which was wrong for the marimo card. It now says "This server cannot install extras from the app".

## Clean-up

The tab was closed. Only the scratch server (its own PID) was stopped. Port 8765 was not touched.
The scratch marimo was uninstalled by the last Uninstall step.
