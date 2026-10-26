# ADR-101: The App Installs marimo as a Separate uv Tool

- **Date:** 2026-10-26
- **Status:** Proposed
- **Deciders:** Maintainer
- **Amends:** [ADR-075](075-omrg-owned-pipeline-runner-local-web-packaging-and-external-tool-plugins.md) decision 4.3 (OMRS never installs or upgrades the tool), [ADR-099](099-library-experiments-open-in-marimo-with-the-project-environment.md) decision 4 (jupytext installed outside OMRS)
- **Related:** [ADR-094](094-app-installs-allowed-extras-into-itself.md) (the install job), [ADR-096](096-app-uninstalls-extras-it-can-install.md) (uninstall), [ADR-085](085-web-login-item.md) (login item)
- **Change:** `openspec/changes/install-marimo-from-integrations/` (design D1 to D11)

## Context

The Library opens an experiment in marimo (ADR-099). Before that works, the user must run `uv tool install "marimo>=0.25.1,<0.26" --with jupytext` in a terminal. Without jupytext the Library refuses with `converter_missing`. Every optional extra on the Integrations page has an Install button. The user asked for the same for marimo.

Four facts shape the decision:

- marimo is a separate `uv tool` with its own environment, on purpose. It is not an OMRS dependency and not in the lock file (ADR-075 decision 4.4). The extras job runs `uv pip install` into the server's own Python (ADR-094), so it cannot install marimo as it is.
- ADR-075 decision 4.3 says that OMRS never runs `uvx`, installs packages or upgrades tools. ADR-099 decision 4 says that missing jupytext is reported with a command to run outside OMRS.
- The shipped manifest holds the qualified range, `minimum` 0.25.1 and `below` 0.26.0. The manifest parser refuses installer tokens, so the install command cannot live in the manifest.
- The login item gives the server a short `PATH` without `~/.local/bin`, where `uv tool` puts executables by default. Registration accepts only executables from `PATH` folders or `<workspace>/plugins/`. So the login-item server cannot register the marimo that `uv tool` installed.

## Decision

1. **One fixed command.** On a user's Install click, the server runs `uv tool install "marimo>=<minimum>,<<below>" --with jupytext` as an argument list with no shell. The range comes from the shipped manifest. No request text reaches the command. There is no `--force`. Uninstall runs `uv tool uninstall marimo`. marimo stays in its own tool environment, outside OMRS.
2. **The same job and guards as the extras.** The one `InstallJob` runs it: one job at a time, 600 s, no `*_API_KEY` variable, 40 redacted lines, `manage` session scope. After exit code 0 the server reads the tool environment again. Success needs marimo inside the range and jupytext present. There is no `uv pip check` and no restart, because the server's environment does not change. Any server install type may install marimo when `uv` is found.
3. **Detection reads uv's own files.** The server asks `uv tool dir` and `uv tool dir --bin` once per launch, then reads the marimo receipt (`uv-receipt.toml`) and the package metadata of the tool environment. It does not parse `uv tool list` text. The card states are `ready`, `needs-jupytext`, `outside-range`, `not-installed` and `unknown`.
4. **Install does not register.** Registration stays the explicit trust decision of ADR-075 decision 4.5. The card links to Experiments, Code editor. The registration form fills in the shipped manifest and the found executable. After a successful registration the page runs the compatibility check once.
5. **Registration accepts the found executable.** The exact path that the server found for the marimo tool is approved, also outside `PATH`. No other file in that folder is.
6. **Uninstall only what the card installed.** The card offers Uninstall only when the receipt holds exactly the marimo range and jupytext. Any other receipt shows the copy command only. Install replaces a marimo outside the range or without jupytext, after a caution that names the installed version.
7. **Jobs and editors exclude each other.** Install and uninstall are refused while a marimo editor that OMRS started is running. Opening a marimo editor is refused while a marimo job runs.

This ADR does not change the rest of ADR-075 decision 4 or ADR-099. marimo is still not a dependency, the manifest is still data with no install action, and the notebook, kernel and launch rules of ADR-099 stand.

## Consequences

### Positive

- The user gets a working marimo with jupytext from the app in one action, in the qualified range.
- `uv tool upgrade marimo` keeps the range, because uv keeps the install constraints.
- The login-item server can register the marimo that `uv tool` installed.
- The page states why the Library cannot convert (`needs-jupytext`) or why the plugin is incompatible (`outside-range`).

### Negative

- The server can now start a process that downloads marimo from the package index. The guards limit it to the qualified marimo and jupytext.
- Install replaces a marimo tool environment that the user may have set up for other work. The caution names the version first.
- Registration is still a second step after Install.
- uv picks the tool's Python. It can differ from a project `.venv`, and the Library then refuses with `python_mismatch`, as with the manual command.
- The uninstall check depends on uv's receipt format. A format change makes the card refuse Uninstall, which is the safe side.

### Neutral

- No new dependency. marimo and jupytext stay out of the OMRS environment and lock file.
- The extras catalogue, its states and its routes do not change. marimo is listed apart, under "External tools".
- There is no upgrade button.
- Windows stays unsupported, as for `omrs web`.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Keep the terminal command only** | The user asked for an Install button. The login item also cannot register the result today. |
| **A `marimo` extra in OMRS** | Rejected before by ADR-075 alternative 4: it couples marimo's resolution and update cadence to the OMRS lock file. |
| **`uvx --with jupytext marimo`** | It runs marimo in a temporary environment and gives no fixed executable to register and hash. |
| **Install command in the manifest** | The manifest must stay data with no install steps. The parser refuses installer tokens. |
| **Register on Install** | Install and trust are different questions. A user may install marimo without wanting OMRS to start it. A failed write after a good install leaves a partial result. |
| **Parse `uv tool list --show-paths`** | Its output is text for people with no stated format. |
| **Add `~/.local/bin` to the login item `PATH`** | The folder can differ (`UV_TOOL_BIN_DIR`, `XDG_BIN_HOME`), and every program in it would become registrable. |
| **Uninstall any marimo tool** | It could remove a marimo the user installed for other work. |
| **`--force` on the install** | It would replace an executable that another installer (pipx, Homebrew) put in the same folder. |
| **Supersede ADR-075 and ADR-099** | Only one rule of each changes. The rest still holds. |

## References

- `openspec/changes/install-marimo-from-integrations/design.md` (evidence for uv and marimo behaviour, checked with Context7 and `uv 0.12.18 --help`)
- `src/omrs/transports/api/install_job.py`, `install_environment.py`, `routes/integrations.py`, `routes/plugins.py`, `routes/experiment_editor.py`, `lifespan.py`
- `src/omrs/core/plugins/shipped/marimo/manifest.json` and `src/omrs/core/plugins/versions.py`
- `src/omrs/transports/cli/_web_login_item.py` (`LAUNCH_PATH`)
- [Notebooks guide](../guides/notebooks.md)
- uv CLI reference, `uv tool install`, `uv tool uninstall`, `uv tool dir`, `uv tool list`: <https://docs.astral.sh/uv/reference/cli>
- uv tools concepts (`--with`, upgrades keep constraints): <https://docs.astral.sh/uv/concepts/tools>
- marimo, "Coming from Jupytext" (`marimo convert` requires jupytext): <https://docs.marimo.io/guides/coming_from/jupytext>

Accept this ADR only after the change's browser check and live check pass (tasks 8.3 and 8.4), and the PR merges (task 8.6).
