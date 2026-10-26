# Design: Install marimo from the Integrations page

## Context

See `proposal.md` for the reason. This section gives only the facts that shape the design.

1. **The extras job installs into the server.** `InstallJob.start` builds `[uv, "pip", action, "--python", sys.executable, *packages]`, then runs `uv pip check`, then marks the extra `restart_needed` (`src/omrs/transports/api/install_job.py`). marimo must not go into the server's Python (ADR-075 decision 4.4).
2. **marimo is a separate `uv tool`.** On the maintainer's machine `uv tool list --show-paths` gives `marimo v0.25.1 (~/.local/share/uv/tools/marimo)` and `- marimo (~/.local/bin/marimo)`. `~/.local/bin/marimo` is a link to `~/.local/share/uv/tools/marimo/bin/marimo`, whose `#!` line names the tool environment's Python.
3. **The tool receipt records what was asked for.** `~/.local/share/uv/tools/marimo/uv-receipt.toml` holds `requirements = [{ name = "marimo" }]` and `entrypoints = [{ name = "marimo", install-path = "~/.local/bin/marimo", from = "marimo" }]`. A tool installed with a range records `specifier` (the semgrep receipt: `{ name = "semgrep", specifier = "==1.174.0" }`). A tool installed with `--with` lists each extra package as another requirement (the graphifyy receipt lists `graphifyy`, `mcp` and `openai`).
4. **The qualified range lives in the shipped manifest.** `tool.tested_versions` is `{"minimum": "0.25.1", "below": "0.26.0"}` in `src/omrs/core/plugins/shipped/marimo/manifest.json`. `VersionRange.describe()` gives `>=0.25.1,<0.26.0` (`core/plugins/versions.py`). A guide test already pins that text (`tests/unit/test_notebooks_guide.py`).
5. **The login item has a short `PATH`.** `LAUNCH_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"` (`src/omrs/transports/cli/_web_login_item.py`). Registration accepts an executable only from a `PATH` folder or `<workspace>/plugins/` (`_executable_problem` in `routes/plugins.py`). So the login-item server refuses today to register `~/.local/bin/marimo`. The live check of ADR-099 used a scratch server started from a shell, which had the full `PATH`.
6. **jupytext is needed for conversion.** marimo's docs say that converting a py:percent script "requires jupytext" and show `uvx --with=jupytext marimo convert ...`. The Library refuses with `converter_missing` when it is missing (`core/workspace/experiment_editor.py`).
7. **Rules that this change reverses.** ADR-075 decision 4.3: "OMRG probes the registered executable. It never runs `uvx`, installs packages, or upgrades tools." ADR-099 decision 4: "Missing jupytext is reported with the command to run outside OMRS." `docs/guides/notebooks.md` line 40: "OMRS never installs, upgrades or replaces marimo. It never runs `uvx`, `uv tool install` or `pip`."

### uv and marimo behaviour checked for this design

| Source | What it says |
|---|---|
| Context7 `/websites/astral_sh_uv`, `uv tool install` (docs.astral.sh/uv/reference/cli) | "Packages are installed into an isolated virtual environment in the uv tools directory." "If the tool was previously installed, the existing tool will generally be replaced." |
| Context7 `/websites/astral_sh_uv`, concepts/tools | `--with` adds a package and may be given more than once. "If the requested version conflicts with the requirements of the tool package, package resolution will fail." uv does not overwrite an executable that uv did not install; `--force` changes this. |
| Context7 `/websites/astral_sh_uv`, `uv tool upgrade` | "Tool upgrades will respect the version constraints provided when installing the tool." So `uv tool upgrade marimo` after this install stays inside `<0.26.0`. |
| Context7 `/websites/astral_sh_uv`, `uv tool dir` and storage | The tools folder is `$UV_TOOL_DIR`, else `$XDG_DATA_HOME/uv/tools`, else `~/.local/share/uv/tools`. `uv tool dir --bin` gives the executable folder: `$UV_TOOL_BIN_DIR`, `$XDG_BIN_HOME`, `$XDG_DATA_HOME/../bin`, then `~/.local/bin`. |
| Context7 `/websites/astral_sh_uv`, `uv tool list` | `--show-paths`, `--show-version-specifiers` and `--show-with` add the paths, the specifiers and the `--with` requirements. The output is text for people. |
| Local `uv 0.12.18 --help` (2026-10-26) | `uv tool install` has `-w, --with <WITH>`, `--force`, `--reinstall` and `-p, --python`. `uv tool uninstall <NAME>...` and `--all`. `uv tool dir --bin`. `uv tool list --show-paths --show-version-specifiers --show-with --show-extras --show-python`. |
| Context7 `/websites/marimo_io`, "Coming from Jupytext" and quickstart | `marimo convert percent_notebook.py -o marimo_notebook.py` "(requires jupytext)". |

## Goals / Non-Goals

**Goals:**

- One Install action on a marimo card puts a qualified marimo with jupytext in place, with the guards of the extras job.
- The card says what is there, so the user sees why the Library cannot convert or open.
- The step from install to a working Code editor is short, and the trust decision stays where it is.

**Non-Goals:**

- No upgrade button. `uv tool upgrade marimo` stays a terminal step, and it keeps the range (Context7 evidence above).
- No other external tool. The card code is for marimo only. A second tool would justify a general shape later.
- No change to the extras install, its states or its routes.
- No Windows support, as for `omrs web`.
- No choice of Python for the tool environment (see Risks).

## Decisions

### D1. One fixed command, built from the shipped manifest

The install argument list is `[uv, "tool", "install", "marimo>=<minimum>,<<below>", "--with", "jupytext"]`. The range is the shipped manifest's `tested_versions`, read through `parse_manifest`, so a later manifest change moves the install with it. There is no shell, no stdin, no `--force` and no request text. The uninstall argument list is `[uv, "tool", "uninstall", "marimo"]`.

- *Why not `--force`:* uv then replaces an executable that another installer (pipx, Homebrew) put in the same folder. uv's own refusal, shown in the output lines, is the safer result.
- *Why not `uvx`:* it runs marimo in a temporary environment and gives no fixed executable to register.
- *Why not a pinned `marimo==0.25.1`:* the manifest qualifies a range. A range lets `uv tool upgrade marimo` take a patch release that stays inside it.
- *Why not let the manifest hold the command:* the manifest parser refuses installer tokens (`notebook-plugins` spec: manifests SHALL NOT supply installation commands). The command is code in OMRS, and the manifest stays data.

### D2. Detection reads uv's own files, after asking uv where they are

A new module `transports/api/tool_environment.py` finds the marimo tool:

1. Find `uv` with the existing `find_uv` (PATH, then `~/.local/bin`, then `~/.cargo/bin`). No `uv` gives `unknown` with `uv-not-found`.
2. Run `uv tool dir` and `uv tool dir --bin` once per launch, with a 10 s limit, through the existing `SubprocessProbeRunner`. Cache both answers. The folders depend only on the environment, which does not change in a launch. A failure gives `unknown`.
3. Read `<tools>/marimo/uv-receipt.toml`. No file gives `not-installed`. The `marimo` requirement's `specifier` and the other requirement names give the "installed by the card" test (D7). The marimo entrypoint's `install-path` gives the executable.
4. Read the installed versions from the tool environment's package metadata (`importlib.metadata.distributions(path=[<site-packages>])` over `<tools>/marimo/lib/python*/site-packages`). This gives the marimo version and whether jupytext is present. It runs no process.
5. Compare the version with `VersionRange.contains` from the manifest. The result is `ready`, `needs-jupytext`, `outside-range` or `not-installed`.

- *Why not parse `uv tool list`:* its output is text for people, with no stated format.
- *Why not compute the folders from the variables:* uv's rule has four steps and may change. One `uv tool dir` call per launch costs little and is always right.
- *Why not run `marimo --version`:* package metadata gives the same version with no process, and the plugin recheck already runs the probe when the user asks.

The child processes get the server environment without `*_API_KEY` variables, so `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR` reach both detection and the job. A test or browser check can then point uv at a scratch folder.

### D3. The same install job, with a tool action

`InstallJob` keeps one state, so one job runs per server across extras and the tool. A new start method takes the target (`tool="marimo"`), the action, the argument list and a check function. It reuses `_child_environment`, `_exec`, `_stop`, the 600 s limit and the 40 redacted lines. After exit code 0 it runs the check function in a thread: detection again, success only on `ready` (install) or `not-installed` (uninstall), else `check-failed`. It does not run `uv pip check` and does not set `restart_needed`, because the server's environment did not change. The snapshot gains `tool` (`marimo` or `null`); `extra` is `null` for a tool job.

- *Why not a second job object:* two jobs could run `uv` at the same time against one cache, and the page rule "one job at a time" (ADR-094 decision 4) would break.
- *Why not `uv pip check --python <tool Python>`:* uv resolves the tool environment as a whole, and detection already checks the two packages that OMRS needs.

### D4. Install does not register marimo

Registration is the trust decision about running an executable (ADR-075 decision 4.5). Two readings were weighed.

- *Register on Install.* The user pressed Install on a fixed, pinned requirement, the manifest ships inside OMRS, and uv wrote the executable seconds ago. A second step adds a click and no new fact about the file.
- *Keep them apart (chosen).* Install answers "may OMRS run uv for me". Registration answers "may OMRS start this program with my permissions, with full file and network access for Library kernels". The second question has its own text and checkbox, and the Code editor already shows it. A user can install marimo for jupytext or for use in a terminal, without wanting OMRS to launch it. Coupling the install job to the plugin registry also makes a partial result possible: installed but not registered after a write failure. And a reinstall over an existing registration changes the executable's identity, which the registry treats as "recheck before launch" on purpose.

So the cost of the second step is made small instead. After success the card shows "Installed" and the line "Register marimo in Experiments, Code editor", with a link to `#/experiments/code-editor`. `GET /v1/plugins` gains `detected_executables` (`{"marimo": "<absolute path>"}` or `{}`), and the registration form fills in the manifest and the executable until the user types. The user ticks approval and presses Register. On success the page calls the recheck route once, so the plugin goes from `unchecked` to its checked state without a third click. When marimo is already registered, the card says "Recheck marimo in Code editor" instead.

### D5. Registration accepts the found executable path

`PluginHost` gains a callable that returns the detected marimo executable. `_executable_problem` accepts that exact absolute path, in addition to `PATH` folders and `<workspace>/plugins/`. The file-name check against the manifest stays. No other file in that folder passes. This closes the login-item gap of Context item 5 for the path that uv itself reported.

- *Why not add `~/.local/bin` to `LAUNCH_PATH`:* the folder can differ (`UV_TOOL_BIN_DIR`, `XDG_BIN_HOME`), and every program in it would become registrable.
- *Why not add the whole `uv tool dir --bin` folder:* the same objection for every tool there.

### D6. Refusals between the job and the editors

- Install and uninstall refuse with `editor-running` while any editor of the `marimo` plugin that this server started is running (`host.editors.sessions()`). Replacing the tool environment under a running kernel can break it, and an uninstall would delete the files it runs from.
- Opening a marimo editor refuses with `tool_install_running` while the job runs with `tool="marimo"`. Both the Code editor route (`openPluginEditor`) and the Library route (`openExperimentEditor`) check it before they issue a credential.
- An extras job does not block an editor open. It does not touch marimo.

### D7. Uninstall is in scope, for the card's own install only

Every installable card on the page has Uninstall (ADR-096), and the user asked for marimo "like all of them". `uv tool uninstall marimo` removes the whole tool environment, including a marimo that the user installed before for another use. So the card offers Uninstall only when the receipt holds exactly what D1 installs: a `marimo` requirement whose specifier set equals the manifest range (compared as a sorted set of clauses, so `<0.26.0,>=0.25.1` matches), and `jupytext`, and nothing else. Any other receipt gives `not-installed-by-app` and the copy command `uv tool uninstall marimo`. A marimo registration is not a reason to refuse. After the uninstall, the registry reports it `unavailable` with its own message. The dialog says so.

- *Why not refuse while registered:* nothing breaks at the next start, as it does for an extra in use (ADR-096 decision 3). The registration stays and works again after a new install and a recheck.

### D8. An existing marimo outside the range or without jupytext

`uv tool install` with a new requirement replaces the tool environment (Context7 evidence). The card offers Install in the states `not-installed`, `needs-jupytext` and `outside-range`. For the last two it shows a caution with the installed version, for example: "Install replaces your marimo 0.27.0 tool environment with marimo >=0.25.1,<0.26.0 and jupytext." The confirm dialog repeats it. This is the same pattern as `install_caution` on the extras cards (ADR-094 decision 9), computed per launch instead of fixed text.

### D9. Contract and page shape

- `GET /v1/integrations` keeps `integrations` and adds `tools: ExternalTool[]`. `ExternalTool` holds `id`, `name`, `purpose`, `availability`, `version`, `jupytext`, `executable`, `requirement`, `install_command`, `uninstall_command`, `installable`, `install_reason`, `install_caution`, `uninstallable`, `uninstall_reason` and `plugin_status` (the marimo registration state, or `null`). `additionalProperties: false`, as for `Integration`.
- New operations `installTool` and `uninstallTool`: `POST /v1/integrations/tools/{tool}/install` and `.../uninstall`, `tool` limited to `marimo`. An unknown tool gets 404 and starts nothing. Both need `require_session("manage")`. The status stays on `GET /v1/integrations/install`.
- `IntegrationInstall` gains `tool`. New `reason` values: `editor-running`, `not-installed-by-app`, and `tool_install_running` on the editor routes.
- The route code goes in a new `routes/integration_tools.py`, so `routes/integrations.py` stays small.
- On the page, a `ToolCard` reuses the card frame, the badges, `CopyCommand` and the confirm dialog. `installPhase` and `uninstallPhase` match a job by `tool` as well as `extra`. `busy` covers both kinds, so all buttons are disabled during any job.
- The extras catalogue (`CATALOGUE`) is not changed. marimo is not an extra, and putting it there would make it look like a base entry (`is_base_extra(None)` is true).

### D10. ADR-101 amends ADR-075 and ADR-099; it does not supersede them

Only one sentence of each record is reversed: ADR-075 decision 4.3 (OMRS never installs or upgrades the tool) and the end of ADR-099 decision 4 (jupytext installed outside OMRS). ADR-075's other points stand: marimo is not a dependency, the manifest has no install action, registration is explicit trust. ADR-099's notebook, kernel and launch rules stand. The project records this as "Amended by" with a short italic note under the changed decision (as ADR-075 decision 4.2 carries for ADR-099, and ADR-087 carries for ADR-095). The notes go in when ADR-101 is accepted, after merge, as for ADR-099.

### D11. Any server install type may install marimo

The extras job needs a `uv tool` server install, because it changes the server's environment (ADR-094 decision 2). This job does not, so a checkout or a pip install of OMRS may install marimo too. `uv` must still be found.

## Risks / Trade-offs

- [The server can now start a process that downloads marimo from the package index.] → Same guard as the extras: `manage` session scope only, a fixed requirement, and no request text. A stolen session can install the qualified marimo and nothing else.
- [Install replaces a marimo that the user set up for other work.] → The caution names the version before the click. Uninstall never removes a marimo the card did not install.
- [uv picks the tool's Python. It can differ from a project `.venv`, which gives `python_mismatch` in the Library.] → Unchanged from today's manual command. The refusal already names both versions. Passing `--python` would need a choice per project, which a single tool environment cannot meet.
- [A future uv changes the receipt format.] → Detection then reads no specifier and reports `not-installed-by-app`, which is the safe side. The live check (task 7.4) reads the real receipt after an install from the card.
- [`uv tool dir` hangs or fails.] → 10 s limit; the card shows `unknown` and the copy command.
- [The install succeeds but marimo still fails the plugin recheck (for example a missing launch option).] → The recheck message names the problem as today. The card is about the install only.

## Migration Plan

No data migration. A user with a marimo from the old manual command sees `needs-jupytext` (the maintainer's machine today) or `ready`. A registration made before stays valid until an install from the card changes the executable, and then needs one recheck. Rollback is a revert of the merge; the tool environment that the card made stays and works as a manual install.

## Open Questions

None that change the specs or tasks. The user may still prefer one click for install and registration (D4). That would be a follow-up change.
