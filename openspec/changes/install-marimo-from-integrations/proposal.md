# Proposal: Install marimo from the Integrations page

## Why

The Library opens an experiment in marimo, but the user must first install marimo in a terminal with `uv tool install "marimo>=0.25.1,<0.26" --with jupytext`. Without jupytext the Library refuses with `converter_missing`. Every other optional integration has a card with an Install button. The user asked for the same for marimo: "the install marimo needs to be in the card at integration with install button like all of them integrations."

marimo is not an OMRS extra. It is a separate `uv tool` with its own environment, on purpose (ADR-075, ADR-099). So the existing install job, which runs `uv pip install` into the server's own Python (ADR-094), cannot install it as it is. The notebooks guide and ADR-075 decision 4.3 also say that OMRS never runs `uv tool install`. This change reverses that rule for one fixed command, and ADR-101 records the reversal.

## What Changes

- The Integrations page gets a marimo card, in a new "External tools" group below the extras. The card shows the marimo state: not installed, installed and ready, installed without jupytext, installed outside the qualified range, or unknown. It shows the version and the executable path.
- The card has an Install button. Install runs one fixed argument list, `uv tool install "marimo>=0.25.1,<0.26.0" --with jupytext`, with no shell. The range comes from the shipped marimo manifest, so the install always matches the qualified versions. No request text reaches the command.
- The marimo install uses the one install job that the extras use. One job runs at a time, with the same 600 s limit, the same environment without `*_API_KEY` variables and the same 40 redacted output lines. After the command the job reads the marimo tool environment again. It reports success only when marimo is in range and jupytext is present. The server needs no restart.
- The card has an Uninstall button. It runs `uv tool uninstall marimo`. The card offers it only when the marimo tool environment holds exactly what the card installs, so the app never removes a marimo that the user installed in another way.
- Install and Uninstall are refused while a marimo editor that OMRS started is running. Opening a marimo editor (Code editor or Library) is refused while a marimo install or uninstall is running.
- Install does not register marimo. Registration stays a separate trust decision in Experiments, Code editor. After the install, the card links to the Code editor. The registration form fills in both the manifest path and the executable path that the install made. A successful registration then runs the compatibility check once.
- Registration accepts the exact executable path that the marimo card found, also when its folder is not on the server's `PATH`. This fixes the login item case: launchd gives the server a short `PATH` without `~/.local/bin`, where `uv tool` puts executables.
- The Code editor and the Library point to the marimo card instead of a terminal command. `converter_missing` now says to install marimo from the Integrations page.
- `docs/guides/notebooks.md`, `plugins/marimo/README.md`, the HTTP README and the folder guides describe the card. The text "OMRS never installs, upgrades or replaces marimo" is replaced.
- ADR-101 (Proposed) amends ADR-075 decision 4.3 and ADR-099 decision 4.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `workspace-integrations`: a marimo card that installs and uninstalls marimo as a separate `uv tool`, with its own states and refusals.
- `notebook-plugins`: the workspace may install marimo on an explicit user action; registration accepts the executable the card found; editor launches wait for a running marimo job; the Code editor links to the card.
- `workspace-experiment-library`: the `converter_missing` refusal points to the marimo card.

## Impact

- **Server:** a new module for marimo tool detection in `src/omrs/transports/api/` (it runs `uv tool dir` and `uv tool dir --bin` once per launch and reads the tool receipt and package metadata); `install_job.py` gains a tool action; a new route module for `POST /v1/integrations/tools/marimo/install` and `.../uninstall`; `GET /v1/integrations` gains a `tools` list; `GET /v1/plugins` gains the detected executable; `routes/plugins.py` and `routes/experiment_editor.py` gain the new refusals.
- **Contract:** `openapi.yaml` gains the `ExternalTool` schema, two operations, a `tool` field on `IntegrationInstall` and new `reason` values. The conformance families in `tests/unit/test_web_openapi_conformance_support.py` gain the two operations.
- **Web:** a marimo card and its controls in `web/src/integrations/`; new refusal lines; the Code editor hint, the registration form and the Library refusal lines in `web/src/experiments/`.
- **Core:** only message text in `core/plugins/registration.py` and `core/workspace/experiment_editor.py`. The plugin host still starts no process, and the manifest stays data with no install steps.
- **Dependencies:** none. marimo and jupytext stay out of the OMRS lock file and the OMRS environment.
- **Docs and records:** ADR-101; `docs/guides/notebooks.md`; `plugins/marimo/README.md`; `src/omrs/transports/api/README.md`; the `AGENTS.md` files of `src/omrs/transports/api/` and `web/src/integrations/`. The coordinator adds the ADR index row.
- **Tests:** the clean-base tripwire pins change and are re-pinned by test-ID diff.
