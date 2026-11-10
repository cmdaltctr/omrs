# Proposal

## Why

A person who installs OMRS as a package (`uv tool install omrs`) cannot use the OCR engines. The wheel ships only `src/omrs`, so the `ocr-workers/` folder is not in it. The only provisioning script, `ocr-workers/provision.py`, runs only inside a git checkout, because it loads a helper from `../src/omrs/...`. `OCR_WORKERS_DIR` is empty by default, so every engine is unavailable until someone sets it.

Today the only working setups are a checkout, or a folder built by hand. The live app's `~/.omrs/ocr-workers` was built by hand: `git archive`, cloned model caches, `uv sync --locked`. Every engine environment holds absolute paths, so a folder cannot be copied after it is built.

The change `ocr-model-cache-outside-repo` (parked) moves the weights out of the repository, to `~/.omrs/ocr-models/<engine>`. This change moves the rest: engine code and environments install into `~/.omrs/ocr-workers` from the package, with no checkout. It matches the project goal that the web app drives the whole system.

## What Changes

- Ship the worker folders inside the wheel: `ocr-workers/core` and, for each engine, `pyproject.toml`, `uv.lock`, `src/` and the licence notes. These files total 0.67 MB. The host and the worker keep byte-identical protocol copies, so they must come from one release.
- Add `omrs ocr install <engine>`. It copies the shipped worker folders to `~/.omrs/ocr-workers`, builds the engine environment there with `uv sync --locked`, runs the engine's `omrs-ocr-fetch` step when it has one, and prints the `ocr_workers_dir` line to apply. It refuses an engine that needs licence acceptance until the operator passes `--accept-model-licence`. It never writes `omrs.jsonc`, because only `omrs web` writes that file (root gotcha 18).
- Add one API route and one server-side job that run the same install. On success, the job saves `ocr_workers_dir` through the settings write route. The job sits beside `InstallJob` and `ModelDownloadJob` and keeps their guards (one job at a time, no shell, no `*_API_KEY` in the child environment, redacted output).
- Add an Install action to each OCR engine row on the Integrations page, with a licence prompt and a progress line.
- Move the provisioning logic into package code so the CLI, the job and the tests share it. What happens to `ocr-workers/provision.py` is an open question in `design.md`.
- Not **BREAKING**: a checkout or a hand-built `ocr_workers_dir` keeps working unchanged.

## Capabilities

### New Capabilities

- `ocr-engine-install`: how the OCR engines reach a machine without a checkout: what the package ships, the install command and job, the licence gate, the build location, progress and failure reporting, and the upgrade rule for an existing folder.

### Modified Capabilities

- `workspace-integrations`: new requirements for the Install action on an OCR engine row, its licence prompt, its progress line and the refusal reasons. The existing requirement "The OCR engines group sets the workers folder" does not change.
- `runtime-components`: the fix command of a missing OCR engine becomes `omrs ocr install <engine>` instead of `python3 ocr-workers/provision.py <engine>`. The same command string changes in one `workspace-integrations` scenario.

## Impact

- `pyproject.toml`: wheel `force-include` for the worker folders; a release check that the wheel holds them (like `scripts/check_web_wheel.py`).
- `src/omrs/integrations/ocr_worker/`: provisioning logic as package code; the manifest helper it already uses.
- `src/omrs/transports/cli/`: a new `ocr` command group.
- `src/omrs/transports/api/`: one route group, one job on `WebRuntime`, contract entries and refusal reasons.
- `web/src/integrations/`: the Install action, licence prompt and progress line.
- Docs: `ocr-workers/README.md`, `docs/guides/ingestion.md`, `docs/guides/configuration.md`, `docs/guides/cli-reference.md`, `docs/guides/architecture.md`.
- Needs `uv` on the machine and network access to Hugging Face and GitHub. Adds no Python dependency to the base install.
- Depends on `ocr-model-cache-outside-repo` (weights in `~/.omrs/ocr-models/<engine>`). Merge that first. Both are parked until Experiment 35 is done.
- The parked change `paddleocr-vl-llamacpp-backend` adds a runtime block and a fetch step to the `paddleocr-vl` engine. The install command reads each engine's manifest, so it does not need to change when that lands.
