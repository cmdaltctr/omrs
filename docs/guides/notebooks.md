# Notebooks

OMRS can open a marimo notebook editor next to the web workspace. The editor is an optional external tool. You install and update it outside OMRS. This guide tells you how to trust, install, register, open, stop and update it, and how to use the starter notebook.

The web workspace works without a notebook plugin. Home, Chat, Knowledge Base, Studio, Integrations and Settings do not need marimo.

Related guides:

- [Web workspace](web-workspace.md): start the server, sign in, credentials and scopes.
- [Pipeline graphs](pipelines.md): the graph documents that notebooks submit.
- `plugins/marimo/README.md`: the marimo manifest, its launch arguments and its limits.

## What is in the plugin

The plugin has these files:

| File | Contents |
|---|---|
| `src/omrs/core/plugins/shipped/marimo/manifest.json` | Plugin identity, tested marimo versions, capabilities, and the fixed probe, launch and conversion arguments. |
| `plugins/marimo/README.md` | Install, register, recheck, launch, stop and update steps for marimo. |
| `plugins/marimo/starter_notebook.py` | A starter notebook that runs graphs through the OMRS API. |

The manifest is package data in the OMRS wheel, so an installed application finds it. `GET /v1/plugins` gives its absolute path in `shipped_manifests`. The README and the starter notebook stay in the folder `plugins/marimo/`. That folder is not in the OMRS wheel. OMRS does not depend on marimo, and marimo is not in the OMRS lock file. The manifest is data. It contains no shell commands, no Python hooks, no credentials and no install steps.

## Trust model

Read this section before you register the plugin or open a notebook.

- **Notebook Python runs with your permissions.** It can read and write your files and use your network, like any program that you start. A separate tool environment for marimo is not an operating-system sandbox.
- **Registration is an explicit trust decision.** OMRS registers a manifest and an executable only when you approve them (`approved: true`). OMRS stores the SHA-256 of the manifest and the identity of the executable. A changed manifest disables the plugin until you register it again. A changed executable disables it until a recheck passes.
- **Each launch needs your consent.** Every open request must carry `consent: true`. Before each launch, OMRS runs the compatibility check again.
- **Experiment credentials cannot touch the live library.** A notebook uses a bearer credential that is bound to one experiment context. That credential runs graphs only in its experiment. It cannot read, search, ingest into or delete from the ordinary library. The server refuses such a request before any work starts.
- **Experiment writes stay in the experiment workspace.** An experiment has its own index below `output/` in its workspace. The default store is LanceDB.
- **OMRS does not pass its secrets to the editor.** The editor gets only a small set of environment variables, for example `PATH`, `HOME` and `LANG`, plus `OMRS_CONNECTION_FILE`. Provider keys from `.env` do not reach it.

The workspace shows a trust notice when you register a plugin, list plugins, register an experiment or open an editor.

## Install marimo outside OMRS

OMRS never installs, upgrades or replaces marimo. It never runs `uvx`, `uv tool install` or `pip`.

1. Install marimo in its own tool environment:

   ```bash
   uv tool install marimo
   ```

2. Find the path of the executable:

   ```bash
   command -v marimo
   ```

3. Keep this path. You give it to OMRS when you register the plugin.

## Prepare an experiment workspace

A notebook runs in an approved experiment workspace.

1. Start the server with an experiment root:

   ```bash
   omrs web --experiment-root ~/omrs-experiments
   ```

2. In the browser session, register an experiment workspace below that root with `POST /v1/experiments`, for example `{"workspace": "<absolute path of the root>/chunking-test", "name": "chunking test"}`. The response gives the context id (`exp_...`) and its backend and index identity.
3. Copy `plugins/marimo/starter_notebook.py` into the experiment workspace.

To end an experiment, revoke it with `DELETE /v1/experiments/{context_id}`. A run that already started finishes. A new run in that context is refused.

## Register and check the plugin

Plugin routes are session only. A bearer credential cannot use them.

1. Read `GET /v1/plugins`. The field `shipped_manifests` gives the path of the shipped manifest. Read that file.
2. Register it with `POST /v1/plugins`. The registration form in **Code editor** fills in the manifest path for you.

   ```json
   {"manifest_path": "<path from shipped_manifests>", "executable_path": "<path from command -v marimo>", "approved": true}
   ```

   The manifest must be the shipped file or a file below `<workspace>/plugins/`. The executable must be in a `PATH` directory or below `<workspace>/plugins/`.

3. Run a compatibility check with `POST /v1/plugins/{name}/recheck`. The check runs only `marimo --version` and `marimo edit --help`, without a shell.
4. Read the state with `GET /v1/plugins`. The plugin stays disabled when the version is outside the tested range, or when the help text does not list a required launch option. The message names the problem.

Before you register a plugin, `GET /v1/plugins` returns an empty list and an install hint. A recheck of an unknown plugin returns 404. Nothing else in the workspace changes.

**Register again after an upgrade.** Manifest version 0.3.0 moved the manifest into the package. The old file was plugins/marimo/manifest.json in the checkout. A registration made with the old file shows that its manifest is missing or changed, and the plugin stays disabled. Do steps 1 to 3 again with the shipped manifest. Each OMRS version that changes the manifest also needs a new registration.

## Open a notebook

Send `POST /v1/plugins/{name}/editors` with the notebook path relative to the experiment workspace, the experiment context id, and your consent:

```json
{"notebook": "starter_notebook.py", "experiment_context": "exp_...", "consent": true}
```

OMRS then:

1. runs the compatibility check again,
2. picks a free port from 2719, 2720 and 2721 (it never stops or adopts a program on a busy port),
3. writes a new access token to a private file (mode 600) in a private launch directory,
4. issues a new API credential that is bound to the experiment context, with the scopes `graph`, `read` and `run`,
5. writes the connection file `omrs_connection.json` and a separate API token file (both mode 600) in the same launch directory,
6. starts marimo on `127.0.0.1` with startup cell execution, automatic package install and update checks turned off, and sets `OMRS_CONNECTION_FILE` to the path of the connection file,
7. returns the editor address (`url_without_token`) and the editor access token once, in the response body.

The editor opens in a separate browser tab. The workspace never embeds the editor in its own page. The URL never contains the token, and no log contains it.

The connection file holds the API address, the experiment context id and the path of the API token file. It does not hold the token. The launch directory is below `<workspace>/run/editors/`, not in the experiment workspace. The response never contains the API credential. `GET /v1/credentials` lists it with the label `notebook editor`.

OMRS owns only the editor processes that it starts. Your notebook files stay where they are.

## Stop, update, recheck, start

Use this procedure to update marimo. OMRS has no update button.

1. **Stop.** Stop the editor in the workspace (`DELETE /v1/plugin-editors/{launch_id}`), or stop `omrs web`. OMRS sends SIGTERM to the editor process group, waits for a limited time, then sends SIGKILL. It removes only the private launch directory, with the connection file and the API token file. It revokes the API credential of that editor.
2. **Update.** Update marimo outside OMRS:

   ```bash
   uv tool upgrade marimo
   ```

   If you installed an exact version, use `uv tool install marimo@latest` instead.

3. **Recheck.** Run `POST /v1/plugins/{name}/recheck`. OMRS shows `unchecked` until you do. It probes the updated executable. It does not change the OMRS lock file.
4. **Start.** If the recheck passes, open the notebook again.

If the new version is outside the tested range, the plugin stays disabled. Keep the earlier marimo version, or qualify the new version and update the manifest. Then register the edited manifest again.

## Use the starter notebook

`plugins/marimo/starter_notebook.py` runs graphs through the same protected graph API as the Studio canvas. It uses the Python standard library only.

### In an editor that OMRS opens

The notebook reads `OMRS_CONNECTION_FILE` and connects without more steps. It refuses a connection file or a token file whose mode is wider than 600.

### In an editor that you start yourself

If `OMRS_CONNECTION_FILE` is not set, the notebook reads three environment variables.

1. In the browser session, issue a credential that is bound to the experiment:

   ```json
   {"scopes": ["read", "graph", "run"], "label": "notebook", "experiment_context": "exp_..."}
   ```

   Send it to `POST /v1/credentials`. The response shows the token once.

2. Save the token in a file. Run `chmod 600` on the file. The notebook refuses a token file that other users can read.
3. Set these environment variables:

   | Variable | Value |
   |---|---|
   | `OMRS_API_URL` | The loopback address that `omrs web` printed, for example `http://127.0.0.1:8765`. |
   | `OMRS_TOKEN_FILE` | The path of the token file. `OMRS_TOKEN` also works, but a file keeps the token out of the process list. |
   | `OMRS_EXPERIMENT_CONTEXT` | The experiment context id (`exp_...`). |

4. Start marimo from that shell.

`OMRS_CONNECTION_FILE` takes precedence over these variables.

### Run a graph

1. Open the notebook. Nothing runs when it opens.
2. Choose a template and change the parameters. A parameter change does not start a run.
3. Press **Run graph**. The notebook submits one graph run and follows it.

Each run records the graph revision, the effective settings, the backend and index identity, the inputs and the outputs. The notebook writes a checkpoint below `output/runs/` in the notebook directory. It writes a temporary file first, then renames it, so a failed write keeps the earlier checkpoint.

The notebook never stores or prints the token.

## Full access from the Library

The experiment page in **Library** has the button **Open in marimo**. It opens the analysis of that experiment in marimo, with the packages of the project. This launch has full access. It does not use an experiment workspace or an experiment credential. The route is `POST /v1/experiment-projects/{project_id}/experiments/{folder}/editor`. It needs a browser session with the `manage` scope and the body `{"consent": true}`.

### What full access means

The notebook kernel runs as you, with the Python packages of the project. Code in a cell can:

- read and write any file that you can read and write,
- use the network,
- read the project `.env` file if the code opens it,
- change the project `.venv` if you install a package from the marimo package panel.

OMRS does not sandbox the kernel. An `Engine` that a cell builds on the live library writes to the same store as the running app. Use stores that are local to the experiment folder.

The dialog shows this text. You must tick the box before the editor opens:

> This opens `analysis.marimo.py` in marimo in a new tab. The notebook runs in this project's Python environment with your full file and network access, like any program you start. OMRS does not sandbox it. Cells do not run until you run them. OMRS adds `analysis.marimo.py` and marimo adds `__marimo__/` in the experiment folder. Add both to your `.gitignore`.

### The project environment

- **Only `<project root>/.venv`.** The kernel runs in that folder. It must hold `pyvenv.cfg` and `bin/python` (the POSIX layout). The folder can be a link. Conda, Poetry environments outside the project and `UV_PROJECT_ENVIRONMENT` are not supported. Without a usable `.venv`, OMRS refuses with `no_project_environment`. Run `uv sync` (or `python -m venv .venv`) in the project folder, then open again.
- **Same Python version.** When the project `.venv` has no marimo, its Python major.minor must be the same as the marimo tool environment. OMRS reads both versions from `pyvenv.cfg` files. It finds the marimo tool environment from the `#!` line of the registered executable. A difference gives the refusal `python_mismatch`, with both versions named. When OMRS cannot read a file, it skips the check and marimo reports the problem in the editor.
- **No automatic install.** OMRS writes `writable = false` for the environment in the private `.marimo.toml`. marimo then installs nothing by itself. A package install from the package panel is your own action.

### Shadowed packages

When the project `.venv` has no marimo, marimo puts its own tool packages on the `PYTHONPATH` of the kernel. These copies come first. If a package is in both environments with different versions, the kernel imports the marimo copy. OMRS lists the names of these packages (at most 20) as a warning on the page. To prevent this, add marimo to the dev dependencies of the project, if your project policy permits it. marimo then uses the copy in the project `.venv`.

### The `.env` file and startup execution

- **`.env` is not loaded.** The private `.marimo.toml` sets `runtime.dotenv` to one empty private file in the launch folder. So provider keys in the project `.env` do not go into the kernel environment. An empty list (`dotenv = []`) does not work: marimo 0.25.1 ignores it and loads the project `.env`. If the project sets its own `runtime.dotenv` in its `pyproject.toml`, the project setting wins.
- **No cell runs when the notebook opens.** The private `.marimo.toml` sets `auto_instantiate = false`. A `pyproject.toml` can turn startup execution back on with `[tool.marimo.runtime]`. Before the launch, OMRS reads the nearest `pyproject.toml` above the experiment folder. If it sets `auto_instantiate = true`, or if it is not valid TOML, OMRS refuses with `project_config_runs_on_open`.

### Derived files and git

OMRS writes the notebook as `analysis.marimo.py` in the experiment folder, beside `analysis.py`. marimo writes its session cache below `__marimo__/` in the same folder. Both are derived files. `analysis.py` stays the source of truth. OMRS does not change a tracked file and does not edit the `.gitignore` of a project.

Add these two patterns to the `.gitignore` of the project:

```text
experiments/**/analysis.marimo.py
experiments/**/__marimo__/
```

This repository already has them.

### Conversion and jupytext

When `analysis.marimo.py` does not exist, OMRS converts `analysis.py` with `marimo convert`. When `analysis.py` does not exist, OMRS writes an empty starter notebook. OMRS never overwrites an existing `analysis.marimo.py`.

marimo needs jupytext to convert the percent format of `analysis.py`. Without it, OMRS refuses with `converter_missing`. Install marimo with jupytext in its tool environment:

```bash
uv tool install "marimo>=0.25.1,<0.26" --with jupytext
```

Then run a recheck. If the install changed the executable, OMRS shows `unchecked` until you do. OMRS never installs jupytext.

### Get a fresh conversion

When `analysis.py` is newer than `analysis.marimo.py`, the page shows: "analysis.py changed after this notebook was made. Delete analysis.marimo.py to make a new copy."

1. Stop the editor.
2. Delete `analysis.marimo.py` in the experiment folder.
3. Select **Open in marimo** again. OMRS converts `analysis.py` again.

Your edits in the old notebook are lost when you delete it. Copy the cells that you need into `analysis.py` first.

## What task 8.4 confirmed

Task 8.4 qualified marimo 0.25.1 on macOS. marimo was installed with `uv tool install marimo` (uv 0.12.18), outside the OMRS environment.
The manifest range is `>=0.25.1,<0.26.0`. The full record is `openspec/changes/add-local-web-pipeline-workspace/evidence/marimo-qualification.md`.

Confirmed with the real editor:

- `marimo --version` prints only the version (`0.25.1`). The recheck reads it and reports `compatible`.
- `marimo edit --help` lists every launch option in the manifest. No flag changed.
- The editor listens on `127.0.0.1` only. Without the token, it redirects to its login page. A wrong token also goes to the login page.
  The right token in `?access_token=` sets a session cookie and redirects to `/`. The API answers 401 without a session.
- The `.marimo.toml` file in the launch directory wins over `~/.marimo.toml`. With `auto_instantiate = true` in `~/.marimo.toml`, no cell ran when the browser opened the notebook.
- A notebook header cannot turn startup execution on. marimo ignores `runtime.auto_instantiate` there and logs a warning.
- The notebook kernel receives `OMRS_CONNECTION_FILE`. The starter notebook connected with it and ran one graph after **Run graph**, and not before.
- `--skip-update-check` turns off the update check. `--no-sandbox` turns off the sandbox that installs dependencies. The editor made no outbound connection.
- On a busy port, marimo exits with "address already in use". It does not pick another port. OMRS checks the port first.
- Stop and `omrs web` shutdown removed the editor process group, the launch directory, the connection file and the token files. The editor credential was revoked.
- An update outside OMRS changed the executable. OMRS showed `unchecked`, and the recheck found the new version. No OMRS file or environment changed.

Limits that stay:

- A `pyproject.toml` with `[tool.marimo.runtime]` in the notebook directory or a parent directory overrides the launch directory file. It can turn startup execution back on.
  Do not keep an experiment workspace below a project that sets `auto_instantiate` there.
- A notebook header can change `runtime.on_cell_change`. Check a notebook before you trust it.
- marimo writes a session cache below `__marimo__/session/` beside the notebook. It holds cell outputs. It did not hold a token.
- After `uv tool install marimo==<version>`, `uv tool upgrade marimo` keeps that version. Use `uv tool install marimo@latest` to move on.
- If the editor process ends by itself, OMRS does not notice it. The connection file stays and the credential stays valid until you stop the editor in the workspace or stop `omrs web`.

The automated plugin tests use fake executables. Only task 8.4 started a real marimo.
