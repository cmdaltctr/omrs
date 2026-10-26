# ADR-099: Library Experiments Open in marimo with the Project Environment

- **Date:** 2026-10-25
- **Status:** Accepted (2026-10-26; built and merged to v3 at PR #131; evidence: `openspec/changes/archive/2026-10-26-open-experiment-in-marimo/browser-check.md` and `live-launch.md`)
- **Deciders:** Maintainer
- **Related:** [ADR-075](075-omrg-owned-pipeline-runner-local-web-packaging-and-external-tool-plugins.md) (external-tool plugins; this ADR amends decision 4.2 for the manifest only), [ADR-097](097-experiment-records-versioned-format.md) (experiment records)
- **Change:** `openspec/changes/archive/2026-10-26-open-experiment-in-marimo/` (design D1 to D10)

## Context

The Library shows an experiment's record and files, but the user cannot work with its analysis from there. The marimo plugin opens only sandbox experiment contexts, which give the notebook a limited API credential and no project packages.

Four facts shape the decision:

- All 24 experiment folders with an `analysis.py` (Jupytext percent format) are finished, converted records. Each script finds its data through `Path(__file__)`, and marimo sets `__file__` to the notebook file. A notebook outside the experiment folder cannot find the data.
- The experiment rule says that a finished or converted experiment changes only `experiment.json`. The same folders already hold a derived, git-ignored `analysis.ipynb`.
- The plugin host may start only the approved, hashed marimo executable with manifest arguments. The manifest parser refuses `uv`, `uvx`, `pip` and installer tokens, and ADR-075 says OMRS installs nothing.
- The installed app cannot find the shipped manifest. `SHIPPED_PLUGIN_MANIFESTS` points at `plugins/marimo/manifest.json` beside the source tree, which is not in the wheel.

The user chose full access: the kernel runs in the project's own environment, behind consent on every launch, with run-on-open off.

## Decision

1. **The notebook is a derived file in the experiment folder.** It is `analysis.marimo.py`, directly beside `analysis.py`, for every status. It is git-ignored and never tracked. `analysis.py` stays the source of truth. OMRS writes the notebook only with an exclusive create, never overwrites it, and never changes a tracked file. The experiment rule now names the derived files a tool may add: `analysis.ipynb`, `analysis.marimo.py` and `__marimo__/`.
   - *Amended by [ADR-102](102-library-edits-protocol-and-report-with-an-edit-log.md) (2026-10-26):* the rule now also lets a finished or converted experiment change `protocol.md` and the report file. A folder can gain `edits.jsonl`, the edit log the app writes.
2. **The kernel runs in `<project root>/.venv` through marimo's own `[venv]` setting.** OMRS keeps the approved marimo executable as the server. It writes `[venv] path = "<absolute .venv path>"`, `writable = false` and a `runtime.dotenv` list that names one empty private file into the private launch configuration. (marimo 0.25.1 ignores an empty `dotenv = []` in this layer and then loads the project `.env`; the live launch check found this.) The argv stays the manifest recipe. marimo installs nothing in this mode.
3. **The existing editor supervisor launches it.** Consent per launch, loopback ports 2719 to 2721, a fresh token returned once, a separate tab, and stop and shutdown clean-up stay as they are. The new route needs the session `manage` scope. The project must be an added Library project, the folder a listed experiment folder, and the notebook path is fixed by the server.
4. **Conversion runs through a manifest recipe.** `marimo convert` runs with the registered executable into a private folder, then OMRS copies the result with an exclusive create. A folder without `analysis.py` gets a packaged empty notebook. Missing jupytext is reported with the command to run outside OMRS.
   - *Amended by [ADR-101](101-app-installs-marimo-as-a-separate-uv-tool.md) (2026-10-26):* the marimo card on the Integrations page can now install jupytext with marimo. The terminal command stays as the alternative.
5. **Run-on-open stays off.** OMRS refuses to launch when the nearest `pyproject.toml` turns on `auto_instantiate`.
6. **The manifest ships in the wheel.** It moves to `src/omrs/core/plugins/shipped/marimo/manifest.json` and is found through `importlib.resources`. It stays data only. The README and the starter notebook stay outside the wheel.

## Consequences

### Positive

- One action opens any experiment's analysis with the project's packages importable.
- Frozen records stay byte-identical. The notebook can be made again from the tracked `analysis.py`.
- No new process type, no new dependency and no install by OMRS. The trust checks of the plugin host still apply.
- The installed app can register the shipped manifest, and the form fills in its path.

### Negative

- marimo puts its own tool packages first on the kernel's `PYTHONPATH` when the project has no marimo. Shared packages with other versions are shadowed (7 of 14 shared distributions differ on the maintainer's machine). The page lists them.
- Each project must ignore `analysis.marimo.py` and `__marimo__/` itself. OMRS does not edit other projects' `.gitignore`.
- The manifest changes path and hash, so every operator registers marimo again once.
- Conversion needs jupytext in marimo's tool environment, an extra step outside OMRS.
- The kernel has the user's full file and network access. OMRS discloses this but does not contain it.

### Neutral

- Windows stays unsupported, as for `omrs web`.
- Sandbox experiment launches are unchanged.
- A project that sets `[tool.marimo.venv]` or `runtime.dotenv` in its own `pyproject.toml` keeps its own choice.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Notebook in a workspace folder (`<workspace>/notebooks/...`)** | `Path(__file__)` points at the workspace, so every analysis loses its data. |
| **Notebook in `output/`** | Same `__file__` break, and `output/` is regenerated by scripts only. |
| **Notebook only for `PLANNED` and `ACTIVE` experiments** | Every existing `analysis.py` is in a finished, converted folder. |
| **`uv run --project <root> --with marimo marimo edit`** | It runs `uv`, not the approved executable, downloads marimo, and can sync the project `.venv` without `--no-sync`. The manifest parser refuses `uv`. |
| **`marimo edit --sandbox` with PEP 723 metadata** | It builds an isolated environment, not the project one, and installs packages. |
| **`[tool.marimo.venv]` written into the project `pyproject.toml` or the notebook header** | OMRS would edit tracked or user files. |
| **`writable = true`** | marimo would install itself into the user's project environment. |
| **A second launcher for Library editors** | It would duplicate the consent, port, token and clean-up rules. Research found no reason the supervisor is unsafe for this use. |
| **`force-include` of `plugins/marimo/manifest.json`, or a byte copy with a drift test** | Two locations for one data file, with no extra reader. |

## References

- `openspec/changes/archive/2026-10-26-open-experiment-in-marimo/design.md` (evidence with file and line references for marimo 0.25.1)
- `src/omrs/core/plugins/` (`manifest.py`, `editor.py`, `kernel_config.py`, `conversion.py`, `shipped.py`)
- `src/omrs/core/plugins/shipped/marimo/manifest.json` and `empty_notebook.py.template`
- `src/omrs/core/workspace/experiment_editor.py` and `src/omrs/transports/api/routes/experiment_editor.py`
- `experiments/AGENTS.md` and `src/omrs/core/experiment_records/templates/experiments-agents.md`
- [Notebooks guide](../guides/notebooks.md), section "Full access from the Library"
- `tests/unit/test_web_experiment_editor.py`, `tests/unit/test_workspace_experiment_editor.py` and `tests/unit/test_plugin_editor.py`
- marimo documentation, "Using custom virtual environments": <https://docs.marimo.io/guides/editor_features/home>
- uv CLI reference, `uv run --with` and `--no-sync`: <https://docs.astral.sh/uv/reference/cli>
