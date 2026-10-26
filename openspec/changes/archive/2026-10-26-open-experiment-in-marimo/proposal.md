# Proposal: open a Library experiment in marimo

## Why

The Library shows an experiment's record, files and findings, but the user cannot work with its analysis from there. To explore results interactively today, the user must convert `analysis.py` by hand, start marimo in a terminal and find the right Python environment. The marimo plugin exists, but it opens only sandbox experiment contexts, and the installed app cannot find the shipped marimo manifest at all (`SHIPPED_PLUGIN_MANIFESTS` points at `parents[4]/plugins/marimo/manifest.json`, which is not in the wheel).

## What Changes

- Add an **Open in marimo** action to the experiment page at `#/experiments/library/<project-id>/<folder>`.
- Add `POST /v1/experiment-projects/{project_id}/experiments/{folder}/editor`. It needs the browser session with the `manage` scope and `consent: true` on every call. A bearer credential cannot launch.
- The notebook is `analysis.marimo.py`, written directly in the experiment folder. It is a derived, git-ignored file, like the existing `analysis.ipynb`. OMRS never edits, renames or replaces a tracked file in the folder.
- On the first open, OMRS converts `analysis.py` with the registered marimo executable (`marimo convert`). When the folder has no `analysis.py`, OMRS copies a packaged empty notebook. A notebook that exists is opened as it is and is never overwritten.
- **Full access:** the notebook kernel runs in the project's own `.venv`, so experiment code can import the project's packages. OMRS keeps the approved marimo executable as the server and passes the project environment to marimo through the private launch configuration (`[venv] path`, `writable = false`). OMRS installs nothing into the project environment.
- Startup cell execution stays off. OMRS refuses to launch when the project's `pyproject.toml` turns it back on.
- Reuse the existing editor supervisor: consent, loopback ports 2719 to 2721, a fresh token per launch, a separate browser tab, stop and shutdown clean-up.
- **Bug fix:** ship the marimo manifest in the `omrs` package and find it with `importlib.resources`. The manifest stays data only. `GET /v1/plugins` names the shipped manifest path, so the register form can fill it in.
- The manifest gains one optional capability (`project_environment`) and one optional recipe (`convert_script`). Its version goes from 0.2.0 to 0.3.0. **BREAKING (operator step):** a registration made with the old manifest is disabled until the operator registers the packaged manifest again.
- Amend the experiment rule "in a finished or converted experiment, change only `experiment.json`" so that it names the git-ignored derived files a tool may add.
- Document what full access means in `docs/guides/notebooks.md`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `workspace-experiment-library`: add the Open in marimo action, the notebook location and conversion rules, the launch checks and the experiment-page states.
- `workspace-experiments`: the Code editor section lists editors that the Library opened, and stops them the same way.
- `notebook-plugins`: the shipped manifest is found in an installed app; an editor launch can run its kernel in a project environment; conversion runs through a structured manifest recipe.
- `experiment-records`: the experiments folder guide names the git-ignored derived files that a tool may add to a finished or converted experiment.

## Impact

- **API:** one new route, new 409 reasons, two new nullable fields on `EditorInfo`, one new field on `PluginList`. `openapi.yaml`, the conformance families and `src/omrs/transports/api/README.md` change.
- **Code:** `core/plugins/` (manifest parser, launch plan, supervisor), a new core module for the Library launch checks, `transports/api/lifespan.py`, a new route module beside `routes/experiment_library.py`, and the packaged data folder `src/omrs/core/plugins/shipped/`.
- **Web:** the experiment page, a consent dialog, the API client, the register form default and the refusal lines.
- **Docs:** `docs/guides/notebooks.md`, `docs/guides/experiment-records.md`, `plugins/marimo/README.md`, `experiments/AGENTS.md` and its two template copies, `.gitignore`.
- **ADR:** new ADR-099. It amends ADR-075 decision 4.2 for the manifest only.
- **Dependencies:** none. marimo and jupytext stay outside the OMRS lock file. Conversion needs jupytext in marimo's own tool environment.
- **Platforms:** macOS and Linux. Windows is not supported, the same as `omrs web` today.
