# Design: open a Library experiment in marimo

## Context

See `proposal.md` for the motivation. This section names only the current state that the decisions depend on.

- **Editor supervisor.** `NotebookEditorSupervisor` (`src/omrs/core/plugins/editor.py:179-311`) rechecks the registration, picks a free loopback port from 2719 to 2721, makes a fresh token per launch, writes it to a private file and starts the registered executable through the injected `OwnedProcessLauncher` (`src/omrs/integrations/process_launcher.py`). The argv is always `(registered executable, *manifest args)` (`editor.py:173`). The launch directory gets a `.marimo.toml` rendered from the manifest (`runtime.auto_instantiate = false`, `runtime.on_cell_change = "lazy"`). The child process gets only `ENV_ALLOWLIST` plus `OMRS_CONNECTION_FILE` (`process_launcher.py:39-44`).
- **Plugin routes.** `routes/plugins.py` opens an editor only for a sandbox experiment context and gives the notebook an experiment-bound bearer credential. The Library has no experiment context.
- **Library routes.** `routes/experiment_library.py` resolves a project from the workspace database, checks it again with `check_project_path` (`core/workspace/experiment_library.py:40`) and finds a listed folder with `experiment_pages._folder` (`core/workspace/experiment_pages.py:205`). Writes need `require_session("manage")` (`experiment_library.py:43`).
- **Manifest bug.** `SHIPPED_PLUGIN_MANIFESTS` (`transports/api/lifespan.py:54-56`) is `parents[4]/plugins/marimo/manifest.json`. In an installed wheel that path does not exist, so `default_plugins_factory` filters it out (`lifespan.py:273`) and the register route refuses the manifest as not approved (`routes/plugins.py:121-133`). Two tests pin the old behaviour: `tests/unit/test_plugin_marimo_manifest.py:62-91` asserts the wheel has no plugin files.
- **Analysis scripts.** 24 experiment folders hold `analysis.py` in Jupytext percent format. All 24 are converted, finished records (11 `PASS`, 9 `FAIL`, 4 `INCONCLUSIVE`, each with a `migration` note). Every one finds its data relative to its own file: `_ROOT = Path(__file__).parent` (for example `experiments/1-reranker-threshold-calibration-2026-05-12/analysis.py:22`) or `EXP = Path(__file__).resolve().parent` (`experiments/19-native-fts-vs-bm25-sparse-2026-08-29/analysis.py:25`).
- **Frozen records.** `experiments/AGENTS.md:87` (and its two template copies) says: "In a finished or converted experiment, change only `experiment.json`. Never edit its other files." The same folders already hold a derived, git-ignored notebook: `.gitignore:48-49` ignores `experiments/**/analysis.ipynb`, and `experiments/EXP_README.md` (section "Experiment Analysis Workflow") calls it derived and not tracked.
- **marimo 0.25.1** (the qualified version, manifest range `>=0.25.1,<0.26.0`) is installed as a uv tool on Python 3.14. Its tool environment has no jupytext.

## Goals / Non-Goals

**Goals:**

- One action on the experiment page opens the experiment's analysis in marimo, with the project's packages importable.
- No tracked file in an experiment folder changes. A frozen record stays byte-identical.
- No cell runs when the notebook opens.
- The installed app finds the shipped manifest.

**Non-Goals:**

- Windows. `omrs web` already needs POSIX (`lifespan.py:24` imports `fcntl`), and the project-environment check reads the POSIX venv layout (`.venv/bin/python`).
- Environments other than `<project root>/.venv`: conda, Poetry's external environments, `UV_PROJECT_ENVIRONMENT`.
- Writing notebook edits back to `analysis.py`. `analysis.py` stays the source of truth.
- A "make a fresh copy" button. The user deletes `analysis.marimo.py` to get a new conversion (D4).
- An OMRS API credential for Library launches. Full-access code imports the project directly.
- Detecting that an editor process ended by itself. The existing limit stays (`docs/guides/notebooks.md`, "Limits stay").

## Decisions

### D1. The notebook is `analysis.marimo.py`, a git-ignored derived file in the experiment folder

The notebook lives directly in the experiment folder, beside `analysis.py`, for every status. It is never tracked in git. `analysis.py` stays the tracked source of truth. marimo also writes its session cache to `__marimo__/` beside the notebook (`docs/guides/notebooks.md`, "Limits stay"); that folder is derived and git-ignored too.

Evidence:

1. The notebook must sit in the experiment folder for the analysis code to work. All 24 scripts resolve data through `Path(__file__)`. marimo sets `__file__` to the notebook file (`marimo/_runtime/runner/by_refs.py:131`, `marimo/_runtime/patches.py:213`). A copy in any other folder makes every data path wrong, and the `except NameError: Path.cwd()` fallback never runs because `__file__` is defined.
2. A derived, git-ignored notebook in a frozen folder already has a precedent (`analysis.ipynb`, `.gitignore:48-49`). The frozen-record rule protects the record files. Adding an ignored file changes no record file, no checker result and no hash in `output/run-records.jsonl`.
3. Reproducibility comes from the tracked `analysis.py` and the recorded marimo version: `marimo convert` writes `__generated_with = "<version>"` into the notebook. Deleting the notebook and opening again gives the same conversion with the same marimo version.

The experiment rule is amended in `experiments/AGENTS.md`, `src/omrs/core/experiment_records/templates/experiments-agents.md` and `.agents/skills/s-experiment/references/template-experiments-agents.md` (kept byte-identical by `tests/unit/test_experiment_skill_drift.py`), and in rule 6 of `.agents/skills/s-experiment/SKILL.md`:

> In a finished or converted experiment, change only `experiment.json`. Never edit its other files. A tool may add the git-ignored derived files `analysis.ipynb`, `analysis.marimo.py` and `__marimo__/`. Never commit them.

This repository's `.gitignore` adds `experiments/**/analysis.marimo.py` and `experiments/**/__marimo__/`. OMRS does not edit another project's `.gitignore`; the consent dialog and the guide tell the user to add the two patterns.

Alternatives:

| Option | Rejected because |
| --- | --- |
| Write the notebook only for `PLANNED` and `ACTIVE` experiments that are not converted | Every existing `analysis.py` is in a converted, finished folder, so the feature would open none of them. |
| `<workspace>/notebooks/<project_id>/<folder>/notebook.py` | `Path(__file__)` points at the workspace folder, so every data path breaks (evidence 1). |
| `<folder>/output/marimo/notebook.py` | Same `__file__` break. `output/` is regenerated by scripts only and is copied to the data store before worktree removal (`experiments/AGENTS.md`, "While it runs"). |
| Track `notebook.py` in git for new experiments | Two tracked sources of one analysis drift. marimo's format is not Jupytext percent, so it cannot replace `analysis.py` under the current rule. |

### D2. The kernel runs in `<project root>/.venv` through marimo's `[venv]` configuration

OMRS keeps the approved marimo executable as the server. For a Library launch the supervisor adds two tables to the private `.marimo.toml` in the launch directory:

```toml
[venv]
path = "<project root>/.venv"   # absolute, resolved by OMRS
writable = false

[runtime]
dotenv = ["<launch folder>/omrs-no-dotenv.env"]  # one empty private file; merged with the manifest's runtime table
```

The argv does not change. It is the manifest recipe, which already has `--no-sandbox`.

Evidence from marimo 0.25.1 (installed package, read without running it; docs at <https://docs.marimo.io/guides/editor_features/home> "Using custom virtual environments"):

1. `VenvConfig` has `path` and `writable` (`marimo/_config/config.py:103-118`), and the user configuration type carries it (`config.py:707`).
2. The user layer is the first `.marimo.toml` found walking up from the working directory (`marimo/_config/utils.py:68-118`). The launch directory is the working directory (`process_launcher.py:250`), so the OMRS file wins over `~/.marimo.toml`. Task 8.4 of the earlier change confirmed this for `runtime` keys. The cwd file loses only `signing`, `cache.verification` and `cache.store` (`marimo/_config/reader.py:136-152`), not `venv`.
3. In edit mode a configured `venv.path` makes marimo start the kernel as `<venv python> -m marimo._ipc.launch_kernel` (`marimo/_session/session.py:128-161`, `marimo/_session/managers/ipc.py:332-410`). A relative path resolves against the notebook file (`marimo/_session/_venv.py:57-91`), so OMRS writes an absolute path.
4. With `writable = false` marimo installs nothing. When the venv has no marimo, marimo puts its own tool site-packages on the kernel's `PYTHONPATH`, and refuses to start when the venv's Python major.minor differs from marimo's (`ipc.py:376-398`, `_venv.py:160-183`).
5. `--sandbox` ignores `[venv]` (`ipc.py:333-337`), so the existing `--no-sandbox` argument stays required.
6. marimo loads the project's `.env` by default when no layer sets `runtime.dotenv` (`marimo/_config/manager.py:255-289`). A `dotenv` list in the user layer stops that, so provider keys from the project's `.env` do not enter the kernel's environment without the notebook asking for them. A project that sets `runtime.dotenv` in its own `pyproject.toml` keeps its choice. **Correction from the live launch check (task 10.4):** marimo 0.25.1 drops an empty user-layer list (`_drop_hollow_dotenv`, `marimo/_config/manager.py:670-679`, because marimo 0.18 and earlier saved masked empty lists to disk), so `dotenv = []` still loaded the project `.env`. OMRS therefore names one empty private file, `omrs-no-dotenv.env`, in the launch folder. A non-empty list survives that filter and outranks the project default.

The manifest declares the support as an optional capability, so a future manifest for a marimo without `[venv]` can leave it out:

```json
"project_environment": {"config": "venv.path"}
```

The parser accepts a `config` capability without a `value` only for names in a new `HOST_CONFIG_CAPABILITIES = {"project_environment"}` set; the host supplies the value at launch. A Library launch is refused with reason `editor_unsupported` when the registered manifest does not declare the capability.

Pre-launch checks, all by reading files, with no process:

- `<root>/.venv/pyvenv.cfg` and `<root>/.venv/bin/python` exist (`.venv` can be a link; the resolved folder must hold both). Else 409 `no_project_environment`: "This project has no .venv folder. Run `uv sync` (or `python -m venv .venv`) in the project folder, then open again."
- When the project venv has no `marimo-*.dist-info`, compare Python major.minor from the project's `pyvenv.cfg` (`version_info` or `version`) with marimo's tool environment. OMRS finds that environment from the `#!` line of the registered executable and its `pyvenv.cfg`. A mismatch is 409 `python_mismatch` with both versions named. When either file cannot be read, OMRS skips the check, and marimo reports the problem in the editor.
- Shadowed packages: list distributions that exist in both site-packages folders with different versions (names only, at most 20). They go into the response as a warning. On this machine the marimo tool environment and the OMRS `.venv` share 14 distributions and 7 differ, for example `starlette` 1.8.0 against 1.6.0 and `uvicorn` 0.54.0 against 0.52.1. The kernel imports the marimo copies first.

Alternatives:

| Option | Rejected because |
| --- | --- |
| `uv run --project <root> --no-sync --with "marimo>=0.25.1,<0.26" marimo edit ...` | The process is `uv`, not the approved and hashed marimo executable. The manifest parser refuses `uv` as an executable and as a token (`manifest.py:52-63`, `:278`, `:405`). `--with` downloads marimo into an ephemeral environment (uv CLI reference, `--with`: "layered on top of the project environment in a separate, ephemeral environment"), which breaks ADR-075 decision 4.3 (OMRS installs nothing). Without `--no-sync`, `uv run` syncs and can change the project `.venv`. It also needs uv on the server's `PATH`. |
| `marimo edit --sandbox` with PEP 723 metadata | It builds an isolated environment from the notebook's inline dependencies, not the project environment, and ignores `[venv]` (evidence 5). It installs packages. |
| `[tool.marimo.venv]` in the project's `pyproject.toml` | OMRS would edit a tracked project file. It still works when the user sets it: the project layer overrides the OMRS user layer, and the kernel uses the user's chosen venv. |
| A PEP 723 `[tool.marimo.venv]` header in the converted notebook | It works only for notebooks OMRS writes, puts an absolute home path in the file, and edits a file the user may already have changed. |
| `writable = true` | marimo would install itself into the project `.venv`, which changes the user's environment. |
| Add marimo to the project's dev dependencies | ADR-075 decision 4.4 keeps marimo out of the OMRS lock file. Other projects may do this; marimo then uses the venv copy and skips the `PYTHONPATH` step (evidence 4). |

### D3. Security and trust

Full access is the user's choice. These guards stay:

1. **Scope.** The route uses `require_session("manage")`, like adding a project. A bearer credential never has `manage` (`security.py:46-49`). Stop stays on `DELETE /v1/plugin-editors/{launch_id}` with the session-only `plugins` scope.
2. **Consent on every call.** The body is `{"consent": true}` with `extra="forbid"`. `consent: false` is 403, and nothing is read or written.
3. **Allowed locations.** The project comes from the Library record and is checked again with `check_project_path`. The folder must be a listed experiment folder that resolves directly inside `<root>/experiments` (`experiment_pages._folder`). The notebook path is fixed: `<folder>/analysis.marimo.py`. No request text names a path, a flag or an argument. An existing notebook that is a link, or not a regular file, is refused with 409 `notebook_not_regular`.
4. **No shell, no user flags.** argv is the manifest recipe with host substitutions only. The conversion argv is the manifest `convert_script` recipe with `{source_path}` and `{output_path}` set by OMRS.
5. **Loopback and token.** Unchanged: `127.0.0.1` only, a fresh token in a 0600 file, the token returned once in the response body, never in a URL or a log.
6. **Run on open stays off.** The manifest `.marimo.toml` sets `runtime.auto_instantiate = false`. marimo strips `auto_instantiate` from a notebook's PEP 723 header (`marimo/_config/manager.py:538-545`) but honours a project `pyproject.toml` (`manager.py:306-309`). Before launch OMRS finds the nearest `pyproject.toml` the same way marimo does (from the notebook folder upwards) and refuses with 409 `project_config_runs_on_open` when `[tool.marimo.runtime] auto_instantiate` is true, or when the file is not valid TOML.
7. **One editor per notebook.** A second open of a notebook with a running editor is 409 `editor_running`, with the launch id, so the page can show it and offer Stop.

`docs/guides/notebooks.md` gets a section "Full access from the Library". It says that the kernel runs as the user with the project's packages, can read and write any file the user can, can use the network, can read `.env` if the code opens it, and can change the project `.venv` if the user installs a package from marimo's package panel. Code that builds an OMRS `Engine` on the live library writes to the same store as the running app; use experiment-local stores.

Consent text (dialog body):

> This opens `analysis.marimo.py` in marimo in a new tab. The notebook runs in this project's Python environment with your full file and network access, like any program you start. OMRS does not sandbox it. Cells do not run until you run them. OMRS adds `analysis.marimo.py` and marimo adds `__marimo__/` in the experiment folder. Add both to your `.gitignore`.

### D4. Conversion

- **When.** Only when `analysis.marimo.py` does not exist. An existing notebook is opened as it is (`notebook_state: "existing"`). OMRS never overwrites it.
- **How.** OMRS runs the manifest recipe `convert_script` (`["convert", "{source_path}", "-o", "{output_path}"]`) with the registered executable through the existing probe runner (no shell, allow-listed environment, 120 s limit). `{output_path}` is inside a new private (0700) folder below `<workspace>/run/convert/`. OMRS then copies the result to `<folder>/analysis.marimo.py` with `O_CREAT | O_EXCL` and removes the private folder. Reason: `marimo convert -o` overwrites an existing file without asking when stdout is not a terminal (`marimo/_cli/utils.py:18-33`, `marimo/_cli/convert/commands.py:136`). Converting into an empty private folder and an exclusive create keep that from touching the experiment folder.
- **No `analysis.py`.** OMRS copies the packaged `empty_notebook.py.template` with an exclusive create (`notebook_state: "created"`). The template is a valid marimo 0.25.1 notebook with one Markdown cell and one cell that sets `EXP = Path(__file__).resolve().parent` and reads `experiment.json`. It has no experiment text substituted into it, so no record value becomes code.
- **jupytext.** Conversion of percent format needs jupytext in marimo's tool environment (`marimo/_convert/non_marimo_python_script.py:22-30`). When marimo exits with its missing-dependency error naming jupytext, the route returns 409 `converter_missing`: "marimo needs jupytext to convert analysis.py. Run `uv tool install \"marimo>=0.25.1,<0.26\" --with jupytext`, then open again." OMRS never installs it.
- **Other failures.** 409 `conversion_failed` with "marimo could not convert analysis.py." The redacted last 40 lines of output go to the server log at warning level. No file is left in the experiment folder.
- **Stale notebook.** `source_newer: true` when `analysis.py` is newer than `analysis.marimo.py`. The page says: "analysis.py changed after this notebook was made. Delete analysis.marimo.py to make a new copy."

### D5. API

`POST /v1/experiment-projects/{project_id}/experiments/{folder}/editor`, operationId `openExperimentEditor`, family `experiment_library`.

Request (`ExperimentEditorRequest`, `additionalProperties: false`):

```json
{"consent": true}
```

Response 201 (`ExperimentEditorOpened`):

```json
{
  "status": "ok",
  "launch_id": "...",
  "plugin": "marimo",
  "project_id": "...",
  "folder": "34-worker-sample-review-2026-09-19",
  "notebook": "analysis.marimo.py",
  "notebook_state": "converted",
  "source_newer": false,
  "environment": {"kind": "project", "python": "3.14", "marimo_in_project": false, "shadowed": ["starlette"]},
  "url_without_token": "http://127.0.0.1:2719/",
  "token_delivery": {"method": "response_body_once", "token": "..."},
  "trust_notice": "..."
}
```

Errors use the existing envelope. Each 409 carries a `reason` from a contract enum and a plain line from `EDITOR_REASONS` in the route module (rule 4 of `src/omrs/transports/api/AGENTS.md`):

| Status | Reason | When |
| --- | --- | --- |
| 400 | (validation) | Folder name refused by `check_name`; body not `{"consent": bool}` |
| 403 | | Bearer credential; `consent` is not true |
| 404 | | Unknown or unavailable project; folder not listed |
| 409 | `editor_unavailable` | marimo not registered, or recheck says not launchable (message from the plugin state) |
| 409 | `editor_unsupported` | Manifest lacks `project_environment`, or lacks `convert_script` when a conversion is needed |
| 409 | `no_project_environment` | No usable `<root>/.venv` |
| 409 | `python_mismatch` | Python major.minor differs and the venv has no marimo |
| 409 | `project_config_runs_on_open` | Nearest `pyproject.toml` turns on startup execution, or cannot be parsed |
| 409 | `notebook_not_regular` | `analysis.marimo.py` is a link or not a regular file |
| 409 | `editor_running` | An editor for this notebook runs; body adds `launch_id` |
| 409 | `converter_missing` | jupytext missing |
| 409 | `conversion_failed` | Other conversion failure |
| 409 | `no_free_port` | Ports 2719 to 2721 are busy |
| 409 | `launch_failed` | The editor did not start |
| 503 | | No experiment library in this server |

`EditorInfo` gains `project_id` and `folder` (nullable strings, required), so `GET /v1/plugins` shows which editors the Library opened. `PluginList` gains `shipped_manifests` (array of absolute paths). The `Error` schema gains the new reasons in its `reason` description and an optional `launch_id`.

Checks run in the order of the table, cheapest first. The notebook is written only after every check passes, just before the launch.

### D6. Ship the manifest with `importlib.resources`

Move `plugins/marimo/manifest.json` to `src/omrs/core/plugins/shipped/marimo/manifest.json` with `git mv`. Hatch already ships every file under `src/omrs` (`pyproject.toml:161-162`, `packages = ["src/omrs"]`), as it does for `core/experiment_records/templates/`. Add `empty_notebook.py.template` beside it. The `.template` suffix keeps the file out of ruff, coverage and import discovery.

`core/plugins/shipped.py` exposes `shipped_manifests() -> tuple[Path, ...]` with `importlib.resources.files("omrs.core.plugins") / "shipped" / "marimo" / "manifest.json"`. A registration stores a file path and reads it again later, so the function returns the resource only when it is a real `pathlib.Path` on disk (the normal wheel and editable installs); a zip import returns nothing and logs one warning. `lifespan.SHIPPED_PLUGIN_MANIFESTS` becomes a call to this function. The manifest stays data: the parser rules in `manifest.py` do not loosen, except the two optional additions in D2 and D4.

`plugins/marimo/README.md` and `starter_notebook.py` stay outside the wheel, so ADR-075 decision 4.2 changes for the manifest only. Tests change: `test_built_wheel_excludes_plugins` becomes "the wheel holds `omrs/core/plugins/shipped/marimo/manifest.json` and nothing under `plugins/`". It stays a slow test, plus a fast test that reads the manifest through `importlib.resources` and parses it.

Alternatives: hatch `force-include` of `plugins/marimo/manifest.json` (two locations of one file, and a source checkout and a wheel resolve different paths); keep a byte copy in `plugins/marimo/` with a drift test (a second copy for no reader; existing registrations must re-register anyway because the manifest hash changes in this change).

### D7. Supervisor reuse

The supervisor stays the one launcher. Changes:

- `build_launch_plan(..., kernel_environment: KernelEnvironment | None = None)`. With a value, the rendered `.marimo.toml` gains the `[venv]` table and `runtime.dotenv` naming one empty private file in the launch folder (see D2 evidence 6). Paths are written as TOML basic strings with escaping; a path with a control character is refused before rendering.
- `NotebookEditorSupervisor.open(..., kernel_environment=...)` passes it through, and refuses the launch with `PluginLaunchError` when the manifest lacks `project_environment`.
- `NotebookEditorSupervisor.convert(name, source, output_dir, timeout)` runs the `convert_script` recipe through the registry's probe runner. `core/plugins` still starts no process itself (import-linter contract `plugin-host-starts-no-processes`).
- `PluginHost` gains `editor_experiments: dict[str, tuple[str, str]]` (launch id to project id and folder). Stop and shutdown clear it with `editor_contexts`.

The Library launch logic (folder checks, venv checks, pyproject check, notebook preparation) goes into a new module `src/omrs/core/workspace/experiment_editor.py`, which reads files only. The route module `src/omrs/transports/api/routes/experiment_editor.py` wires it to the supervisor, so `experiment_library.py` stays under 500 lines.

Research found no reason that reuse is unsafe. The supervisor already binds loopback only, owns only its processes, and keeps tokens out of argv and logs.

### D8. Web

- **Placement.** The experiment page header actions, before "Add to notebook": a default button "Open in marimo" with the `SquareArrowOutUpRight` icon, the same as `OpenEditorForm`. At 390 px the header actions wrap, and the button stays full width in its row.
- **Disabled state.** When `GET /v1/plugins` has no launchable `marimo`, the button is disabled and a hint below the record card says: "Register marimo in Experiments, Code editor, to open notebooks." with a link to that section.
- **Consent.** The button opens a dialog (`components/ui/dialog.tsx`) with the D3 text, a checkbox "I understand this notebook runs with my full access", and "Open in marimo" (enabled only when ticked) and "Cancel". Consent is never remembered.
- **Launching.** The confirm button shows "Opening marimo" with `aria-busy`, and a polite live region says the same. Conversion and start take a few seconds.
- **Opened.** The page calls `window.open(url, "_blank", "noopener,noreferrer")`, then shows a card: "marimo is open in a new tab", the editor address, `OneTimeSecret` for the token with "Paste it into the marimo sign-in page", a link "Open the editor tab again", the notebook state ("Converted from analysis.py", "Created an empty notebook" or "Opened the existing notebook"), the stale note from D4, the shadowed packages as a short warning, and Stop through `ConfirmAction` with the existing stop warning.
- **Running.** On reload, the page finds its editor in `GET /v1/plugins` by `project_id` and `folder`, and shows the running card without the token, plus Stop.
- **Refusals.** One plain line per reason from `refusal.ts`, through `describeError`; the raw message goes to the console.
- **Register form.** `PluginRegisterForm` fills the manifest path from `shipped_manifests[0]`.
- **Check.** Browser check at 1280 px and 390 px on a scratch server, recorded in `browser-check.md` in this change folder.

### D9. Manifest changes

`plugin_version` 0.2.0 to 0.3.0. Add the capability `project_environment` (D2) and the optional recipe `recipes.convert_script.args` with the new substitutions `{source_path}` and `{output_path}`, which only that recipe may use. `schema_version` stays 1: the shipped manifest and its parser ship together now, and the parser keeps refusing unknown keys. The README's "update" steps say that a new OMRS version can need a new registration.

### D10. Decisions made during the build

These follow best practice where the design was silent. They do not change D1 to D9.

1. **Unknown plugin.** `NotebookEditorSupervisor.open` still raises `KeyError` for an unknown plugin, so `POST /v1/plugins/{name}/editors` keeps its 404. The Library route maps `KeyError` to 409 `editor_unavailable`.
2. **Sibling modules.** `core/plugins/kernel_config.py` renders the `[venv]` and `dotenv` tables, `conversion.py` holds `ConvertResult`, and `versions.py` holds the version helpers. This keeps `editor.py` and `manifest.py` under the 400-line target and the 500-line ceiling.
3. **Two editors for one experiment.** A second open while an editor for the same project and folder runs is refused with 409 `editor_running` and the running `launch_id`. One lock serialises Library opens, so two requests cannot convert one notebook twice.
4. **Conversion log.** The tail of a failed conversion is logged once at warning level, after the provider-key and token redaction. The response holds only the plain line.
5. **`analysis.py` as a link.** It counts as absent, so the server writes the packaged empty notebook (`created`) and never converts the link target.
6. **Unreadable `pyproject.toml`.** A file that cannot be read is refused like one that is not TOML (`project_config_runs_on_open`).
7. **Code editor link.** The web app adds the route `#/experiments/code-editor`, so the disabled-state hint can link to that section.
8. **Server text in refusals.** The page shows a fixed line per reason. For `python_mismatch` and `converter_missing` it shows the server line, because that line names the versions or the install command.
9. **No `.env` through an empty file, not `[]`.** The live check found that marimo 0.25.1 ignores `dotenv = []` in the user layer (D2 evidence 6, correction). A launch with a kernel environment writes an empty private file `omrs-no-dotenv.env` in the launch folder, and `runtime.dotenv` names only that file. The live check confirms the project `.env` is not loaded (`live-launch.md`).
10. **Stop clears a stale refusal.** After an `editor_running` refusal, Stop on either card also clears that line, so the page does not say "already open" for an editor that has stopped (`browser-check.md`, check 11).
11. **Live check without jupytext.** marimo's tool environment on the build machine has no jupytext, and OMRS installs nothing. The live check (task 10.4) records the `converter_missing` refusal and opens a folder without `analysis.py`. Conversion itself is checked with the fake executable only.

## Risks / Trade-offs

- [The kernel imports marimo's copies of shared packages first (`PYTHONPATH` injection), so experiment code can see a different `starlette` or `anyio` than the project pins.] → The response and the page list the shadowed names. The guide explains it and says how a project can avoid it (marimo in the project's dev dependencies, where its policy allows).
- [A project `pyproject.toml` can change other marimo runtime settings, for example `on_cell_change = "autorun"`.] → Only startup execution is refused (the user's fixed decision). Autorun reacts to cell edits, not to opening. The guide names it.
- [The derived notebook can be committed by mistake in a project without the ignore patterns.] → The dialog and the guide say to add the patterns. This repository's `.gitignore` adds them, and a test checks that `git check-ignore` matches both in this repository.
- [Re-registration is needed after upgrade, because the manifest path and hash change.] → The plugin state message already says to register again. The register form now fills in the path. The release note says so.
- [An editor that exits by itself stays listed until Stop or shutdown.] → Existing limit; unchanged.
- [A user installs a package from marimo's package panel into the project `.venv`.] → That is an explicit user action under full access. The guide names it. `writable = false` stops automatic installs.
- [`.env` content can still reach the notebook if the code reads it, or if the project sets `runtime.dotenv`.] → Full access; disclosed in the dialog and the guide.

## Migration Plan

1. Ship the change. Existing marimo registrations show "manifest missing" or "manifest changed".
2. The operator opens Experiments, Code editor, and registers again. The form fills in the packaged manifest path.
3. The operator runs `uv tool install "marimo>=0.25.1,<0.26" --with jupytext` once to allow conversion.
4. Rollback: revert the merge. Registrations made with the 0.3.0 manifest then point at a missing path and need a new registration with the 0.2.0 file. Derived notebooks stay in the experiment folders and are ignored by git.
