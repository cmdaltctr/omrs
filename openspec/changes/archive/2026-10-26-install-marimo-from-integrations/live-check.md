# Live check: install marimo from the card on the real uv folders (task 8.4)

- **Date:** 2026-10-26
- **Code:** `v3` at `759f63da` (merge of PR #132).
- **Server:** a scratch `omrs web` on port 8790, started from the `v3` checkout with
  `--workspace <scratch>/ws`, `OMRS_CONFIG_DIR=<scratch>/config` and
  `--experiment-root <v3 checkout>`. No `UV_TOOL_DIR` or `UV_TOOL_BIN_DIR`, so uv used the real
  tool folders. The server `PATH` held no `~/.local/bin` entry. The live app on port 8765 and
  `~/.omrs` were not touched.
- **Client:** the HTTP API with the server's own one-time sign-in link (the same session and
  routes the page uses). The page itself was checked in the browser at task 8.3.

## Results

| Step | Result |
|---|---|
| Card state before the install. The real marimo was 0.25.1 with no jupytext, installed in a terminal on 13 October. | Pass. `needs-jupytext`, version 0.25.1, Install offered, caution "Install replaces your marimo 0.25.1 tool environment with marimo >=0.25.1,<0.26.0 and jupytext." Uninstall refused with `not-installed-by-app`. |
| Install from the card. | Pass. 202, then the job ended `succeeded` (tool `marimo`, action `install`). The card showed `ready`, jupytext true, executable `~/.local/bin/marimo`, Install refused with `already-installed`, Uninstall offered. |
| `uv tool list --show-version-specifiers --show-with` | Pass. `marimo v0.25.1 [required: >=0.25.1, <0.26.0] [with: jupytext]`. uv kept 0.25.1 because it is inside the range. |
| Receipt text (home folder as `~`) | Pass. `requirements = [{ name = "marimo", specifier = ">=0.25.1,<0.26.0" }, { name = "jupytext" }]` with the `~/.local/bin/marimo` entrypoint. This is the D7 card shape, and the card offered Uninstall. |
| Register `~/.local/bin/marimo` with a server `PATH` that lacks `~/.local/bin` (D5). | Pass. Register answered 201. The recheck answered "marimo 0.25.1 is compatible". |
| Open in marimo on experiment 34 (`34-worker-sample-review-2026-09-19`). | Pass. 201, `notebook_state` `converted`, notebook `analysis.marimo.py`, `source_newer` false. No `converter_missing` in the response or the server log. |
| `git status --short` in the `v3` checkout after the open. | Pass. Empty. `analysis.marimo.py` is ignored by git. |
| Uninstall on the real tool. | Not run, by design. |

## Clean-up

The editor was stopped (200) and the scratch project was removed (200). Only the scratch server
(its own PID) was stopped. The converted `analysis.marimo.py` stays in experiment 34; git ignores it.
The real marimo tool now holds the card install: marimo 0.25.1 with jupytext and the tested range.
