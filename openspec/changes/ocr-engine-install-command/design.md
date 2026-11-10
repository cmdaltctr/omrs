## Context

See `proposal.md` for the problem. The facts that shape the design:

- The wheel packages only `src/omrs`. The `ocr-workers/` folder holds 29 tracked files, 0.67 MB, once smoke evidence and test scripts are left out.
- `ocr-workers/provision.py` runs with the operator's system `python3`. It loads `src/omrs/integrations/ocr_worker/manifest.py` by file path, which only works in a checkout. Its steps are: licence gate, Python range check (`>=3.11,<3.14`, default 3.12), `uv sync --locked` in the engine folder, then the engine's `omrs-ocr-fetch` script.
- An engine environment holds absolute paths. It must be built where it will run.
- Each engine depends on the worker core through `[tool.uv.sources] omrs-ocr-worker-core = { path = "../../core" }`. The layout `core/` beside `engines/` must survive.
- The app already runs guarded background jobs on `WebRuntime`: `InstallJob` (extras, `uv pip`) and `ModelDownloadJob`. Web shutdown stops the model download job.
- Only `omrs web` writes `omrs.jsonc` (root gotchas 17 and 18). The CLI and other processes read it.
- The change `ocr-model-cache-outside-repo` (parked, not yet applied) moves the model cache default to `~/.omrs/ocr-models/<engine>`. This design assumes it and does not touch it.

## Goals / Non-Goals

**Goals:**

- One implementation of the install steps, used by the CLI, the job and the tests.
- A package install reaches a working engine with `omrs ocr install <engine>`, or one button in the app.
- An existing checkout or hand-built folder keeps working and can be refreshed in place.

**Non-Goals:**

- Windows. The project tests on POSIX only. The install code makes no Windows claim.
- An uninstall action. Removing an engine means deleting its folder.
- A cancel button and byte-level progress for the fetch step (see Open Questions).
- Detecting an engine folder from an older release. The protocol has a version handshake, so a protocol break shows as a protocol error. Add a version stamp when a release plans a protocol change.
- Any change to the model cache default (that is `ocr-model-cache-outside-repo`), the engine list, routing, or the engines' own code.

## Decisions

### D1. Ship the worker folders in the wheel (recommended)

Use hatch `force-include` for `ocr-workers/core` and, per engine, `pyproject.toml`, `uv.lock`, `src/` and the licence notes. Leave out `smoke_evidence/`, `smoke_test.py`, `parity_check.py`, `SMOKE_RESULTS.md` and `DATA_LOCATIONS.md`. A release check (beside `scripts/check_web_wheel.py`) fails when the wheel lacks the worker files or holds a weights or evidence file.

- Why: the host and the worker keep byte-identical protocol copies, and one release guarantees that at runtime. The cost is 0.67 MB. It needs no new hosting.
- Rejected: download a pinned archive at install time. It adds hosting, hash pinning and a version-skew case, and it fails offline for the code part.

### D2. `uv` supplies the Python interpreter (recommended)

Run `uv sync --locked --python 3.12` in the engine folder, as `provision.py` does today. `--python` accepts 3.11 to 3.13. `uv` downloads the interpreter when it is absent. Find `uv` with `shutil.which`, as `install_environment.py` does. With no `uv`, stop with `uv-missing` and the one-line `uv` install hint.

- Why: the server's own Python can be 3.14, outside the engines' `>=3.11,<3.14` range.
- Rejected: use `sys.executable`. It fails on 3.14 and ties the engine to the server's Python.

### D3. Where the folder goes

Order: `--workers-dir`, then the `ocr_workers_dir` setting in force, then `~/.omrs/ocr-workers`. The environment is built in that folder. When the target is the `ocr-workers/` folder of a source checkout (an ancestor holds `pyproject.toml` and `src/omrs`), the copy step is skipped and only the environment is built. This keeps the old `provision.py` behaviour for developers.

### D4. Copy and rerun rules

Copy file by file. Never delete a file the install did not write. Never touch `.venv` or the model cache. A second run refreshes the shipped files and runs `uv sync --locked`, which does nothing when the lockfile is unchanged. A folder built by hand from the same files is adopted without a rebuild.

### D5. One implementation: a package module, run by the CLI, and the job runs the CLI

Put the install steps in `src/omrs/integrations/ocr_worker/provision.py` (standard library only). `integrations` is a leaf layer, so it may not import `core` or `transports`; this module needs neither. The CLI group `omrs ocr install` is a thin wrapper in `transports/cli/`. It writes progress lines to stderr (stdout stays free, root gotcha 5), one `step: copy|environment|fetch` line at each step.

The server job runs `python -m omrs ocr install ... --progress` as an argument list and reads the `step:` lines. This gives the job a real process to time out and kill, and it keeps one code path.

- Rejected: call the function in a worker thread. A thread cannot stop its `uv` child cleanly or stream its output.
- Rejected: extend `InstallJob`. It runs `uv pip install` into the server's own environment, with a 600 s limit, and it sets `restart_needed`. None of that fits.

### D6. A separate job object and two routes

Add `OcrEngineInstallJob` on `WebRuntime`, beside `installs` and `model_downloads`. Reuse the redaction and environment-scrub helpers from `install_job.py` (no `*_API_KEY`, last 40 redacted lines). One job at a time. Total limit 45 minutes, a module constant (weights are several GB). Stop it at shutdown like `model_downloads`.

- `POST /v1/integrations/ocr-engines/{engine}/install`, body `{"accept_model_licence": bool}`, `manage` scope. It answers 409 with a `reason` from the fixed list in the spec.
- `GET /v1/integrations/ocr-engines/install` reads the job (step, last lines, reason, result).

The request text never reaches the command line: `{engine}` is checked against the folder names the package ships, and the folder comes from settings.

### D7. The job saves `ocr_workers_dir` itself

The server owns `omrs.jsonc`, so on success the job calls the settings write path in-process when the setting differs from the installed folder. The existing restart-pending flow tells the user that the folder applies at the next launch. The CLI only prints the line to apply.

### D8. One command name everywhere, and a shim for `provision.py`

Change the three places that print `python3 ocr-workers/provision.py <engine>` to `omrs ocr install <engine>`: `manifest.py`, `runtime_components.py` and `routes.py`. Update the web fixtures and tests that pin the old string. In a checkout the command is `uv run --no-sync omrs ocr install <engine>`.

`ocr-workers/provision.py` stays as a short shim that loads the package module by file path, so existing checkout habits and `tests/test_ocr_worker_provision.py` keep working. The docs call the shim checkout-only and name `omrs ocr install` as the supported command.

### D9. The licence gate lives in the shared module

The gate reads `requires-acceptance` from the engine manifest (`manifest.licence_gate`, already shared). The CLI flag and the request field both feed it, so the two entry points cannot differ. The refusal happens before the copy step.

## Risks / Trade-offs

- [The wheel grows by about 0.7 MB] → Accepted. The release check keeps weights and evidence out.
- [A package upgrade leaves an older engine folder] → A protocol break shows as a protocol version error. Re-running `omrs ocr install` refreshes the files. A version stamp is deferred (Non-Goals).
- [`uv sync` or the fetch step fails halfway] → The folder is left as it was found, apart from files the install wrote. The job reports the failing step and the last redacted lines. Re-running is safe (D4). The fetch step already refuses a download whose SHA-256 differs and leaves no partial file in the cache.
- [The 45-minute limit is too short on a slow link] → The failure is `timeout` and a re-run resumes cheaply, because `uv` and the cache keep finished work. The constant is easy to change.
- [Two entry points drift] → The job runs the CLI, so there is one flow.
- [A checkout is overwritten by mistake] → D3 skips the copy for a source checkout. A scenario in the spec tests it.

## Migration Plan

1. Merge `ocr-model-cache-outside-repo` first.
2. Land this change. Nothing breaks for a checkout or for a hand-built folder.
3. The live app: run `omrs ocr install dots-mocr --accept-model-licence --workers-dir ~/.omrs/ocr-workers` after the next live reinstall. The files match, so it is a refresh. The operator's own step, not part of the code change.
4. Rollback: revert the commit. The `~/.omrs/ocr-workers` folders it wrote stay valid, because they hold the same files that a checkout holds.

## Open Questions

- Progress during the fetch (up to several GB): the first version shows the step and the last output line. Add byte progress later if the wait feels long.
- A cancel button: the first version has none. A killed job leaves a safe state (D4).
- A default for `ocr_workers_dir`: it stays empty here. A later change could default it to `~/.omrs/ocr-workers` when `engines/` exists there, which would remove the Save step.
- A disk-space check before the install: engines need roughly 9 GB (environments about 2 GB, weights up to 6 GB). The first version reports a full disk as `environment-failed` or `fetch-failed` with the output lines.
- When to delete the `ocr-workers/provision.py` shim.
