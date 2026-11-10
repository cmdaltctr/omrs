# Tasks

Parked until Experiment 35 is done. Start only after `ocr-model-cache-outside-repo` (weights in `~/.omrs/ocr-models/<engine>`) is merged into `v3`. Create a worktree `omrs-v3-feat-ocr-engine-install-command` from `v3`, then run `uv sync --frozen --extra web` in it. Check `git rev-parse --show-toplevel` and `git branch --show-current` before any command that changes state. Write each group's tests before its code and show each new test failing first. Do not run the full suite or start a server without the operator's approval.

## 1. The shared install module

- [ ] 1.1 Write tests for the install module (design D3, D4, D5, D9) with a fake `uv` on `PATH`: the licence gate refuses before any copy; an unknown engine names the shipped engines; a missing `uv` gives `uv-missing`; the target order is `--workers-dir`, the setting in force, then `~/.omrs/ocr-workers`; a source checkout target gets no copy; a second run keeps `.venv` and the cache and deletes no foreign file; each step prints a `step:` line.
  - Verify: the new tests fail against an empty module, with `pytest -m "not slow" <file>`.
- [ ] 1.2 Create `src/omrs/integrations/ocr_worker/provision.py` (standard library only) with the steps from `ocr-workers/provision.py`: licence gate, Python range, copy, `uv sync --locked --python 3.12`, fetch. Add the shipped-files lookup that falls back to `<checkout>/ocr-workers` in a checkout.
  - Verify: the 1.1 tests pass; `uv run --no-sync lint-imports` keeps `integrations-are-leaves`.
- [ ] 1.3 Reduce `ocr-workers/provision.py` to a shim that loads the package module by file path and calls its `main`.
  - Verify: `tests/test_ocr_worker_provision.py` passes with no edit to its assertions.
- [ ] 1.4 Change `python3 ocr-workers/provision.py <engine>` to `omrs ocr install <engine>` in `manifest.py`, `runtime_components.py` and `routes.py`, and in the web fixtures and tests that pin the string (`DocumentReadingSection.test.tsx`, `settings/test/fixtures.ts`, `ListParam.test.tsx`, `RuntimeSection.test.tsx`).
  - Verify: change the Python tests first and see them fail; then `uv run --no-sync pytest -n auto -q -m "not slow" tests/test_ocr_*.py tests/unit` passes and `npm test` in `web/` passes for those four files.
- [ ] 1.5 Update `ocr-workers/README.md` (provisioning section: the supported command, the shim, the folder rules) and `docs/guides/ingestion.md`.
  - Verify: `uv run --no-sync pytest -q tests/test_docs_*.py` passes and the commands in the text run as written (with `--dry-run`).

## 2. The `omrs ocr install` command

- [ ] 2.1 Write CLI tests with `CliRunner`: the flags `--workers-dir` and `--accept-model-licence`; all output on stderr; the `ocr_workers_dir` line printed when the folder differs from the setting in force; `omrs.jsonc` unchanged in every case.
  - Verify: the tests fail before the command exists.
- [ ] 2.2 Add the `ocr` group and `install` command in `src/omrs/transports/cli/` as a thin wrapper over the module. Add `--progress` for the machine-readable `step:` lines the job reads.
  - Verify: the 2.1 tests pass; `uv run --no-sync omrs ocr install --help` lists the options.
- [ ] 2.3 Document the command in `docs/guides/cli-reference.md` and add it to the checkout and package sections of `docs/guides/configuration.md`.
  - Verify: the CLI reference test or drift check passes; the documented flags match `--help`.

## 3. Ship the worker folders in the wheel

- [ ] 3.1 Write tests for a release check script `scripts/check_wheel_ocr_workers.py` on small fake wheels: it passes with the worker core and both engines' manifest, lockfile, source and licence notes; it fails when a file is missing; it fails when the wheel holds a weights file, a virtual environment, smoke evidence or a test script.
  - Verify: the tests fail before the script exists.
- [ ] 3.2 Add the hatch `force-include` entries and exclusions (design D1). Build a wheel into the scratch folder with `uv build --wheel` and run the script on it.
  - Verify: the script passes on the real wheel; `unzip -l` shows no file under `smoke_evidence`, no `.venv`, no `.gguf` or `.safetensors`.
- [ ] 3.3 Call the script where `scripts/check_web_wheel.py` is called (release preparation and `scripts/local_ci.sh` if it builds a wheel).
  - Verify: `grep -rn check_wheel_ocr_workers` shows the same call sites as `check_web_wheel`.

## 4. The install job and routes

- [ ] 4.1 Write job tests with a fake CLI subprocess: a second request while one runs gives `busy`; the child environment has no `*_API_KEY`; output is redacted and capped at 40 lines; the step is read from `step:` lines; a timeout gives `timeout`; each fixed reason maps from the exit; success saves `ocr_workers_dir` only when it differs; failure leaves the setting alone.
  - Verify: the tests fail before the job exists.
- [ ] 4.2 Add `OcrEngineInstallJob` in a new module under `src/omrs/transports/api/`, reusing the redaction and scrub helpers from `install_job.py`. Add it to `WebRuntime` and stop it at web shutdown. Keep every file under 500 lines.
  - Verify: the 4.1 tests pass; `tests/test_file_size_ceiling.py` passes.
- [ ] 4.3 Add `POST /v1/integrations/ocr-engines/{engine}/install` and `GET /v1/integrations/ocr-engines/install` behind `require_session("manage")`. Check `{engine}` against the shipped engine names. Add the refusal reasons to the OpenAPI contract and to the route's message map.
  - Verify: contract tests fail first, then pass; a request with an unknown engine gets 409 `unknown-engine` and starts no process.
- [ ] 4.4 Add a rule for the job to `src/omrs/transports/api/AGENTS.md` and update `docs/guides/architecture.md` (job list).
  - Verify: `tests/test_docs_*.py` and `tests/test_strategy_registration_inventory.py` pass.

## 5. The Integrations page

- [ ] 5.1 Write component tests (vitest): the Install button shows only on a `missing` engine row; every button is disabled while a job runs; the licence prompt names `LICENCE-NOTES.md` and sends no request until Accept and install; no prompt for `paddleocr-vl`; the step line and last output line show; a failure shows plain English, not the raw code; a success that saved the folder offers the restart action.
  - Verify: the tests fail before the component change.
- [ ] 5.2 Implement the Install action, the licence prompt and the progress line in `web/src/integrations/` with a `useOcrEngineInstall` hook. Follow the `omrs-design` skill tokens and keep each file under the size ceiling.
  - Verify: the 5.1 tests pass; `npm run build` and the web type check pass.
- [ ] 5.3 Check the page at 1280 px and 390 px in a browser, using a scratch config, a fixed free port and the Orca preview steps. Warn the operator before starting the server.
  - Verify: screenshots at both widths show the button, the prompt, the progress line and the reason with no sideways scroll.

## 6. Integration checks

- [ ] 6.1 Re-pin `_BASE_EXECUTED` in `tests/test_clean_base_tripwire.py` by test-ID diff, with a dated comment.
  - Verify: `./scripts/local_ci.sh` passes, with the operator's approval to run it.
- [ ] 6.2 Run `openspec validate ocr-engine-install-command --strict`.
  - Verify: the command prints that the change is valid.
- [ ] 6.3 With the operator's approval for a download of about 2 GB, install the built wheel into a scratch tool folder and a scratch `HOME`, then run `omrs ocr install paddleocr-vl`.
  - Verify: the engine folder holds a working `.venv`; the Integrations row shows `ready`; `omrs.jsonc` in the scratch config is unchanged by the CLI.
- [ ] 6.4 With the operator's approval for a download of several GB, repeat 6.3 for `dots-mocr` from the app's Install button, including the licence prompt.
  - Verify: the job ends `succeeded`; `ocr_workers_dir` is saved; the row says the folder applies at the next launch.

## Workflow follow-up

- Operator step: after the next live reinstall, run `omrs ocr install dots-mocr --accept-model-licence --workers-dir ~/.omrs/ocr-workers` to refresh the live folder in place.
- Archive the change after review and verification.
