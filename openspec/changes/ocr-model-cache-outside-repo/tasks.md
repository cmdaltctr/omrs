# Tasks

Start only after Experiment 35 is done. Create a worktree `omrs-v3-feat-ocr-model-cache-outside-repo` from `v3`, run `uv sync --frozen --extra web`, and check `git rev-parse --show-toplevel` and `git branch --show-current` before any command that changes state. Write each group's tests first and see them fail. A working version is on the local branch `parked/ocr-model-cache-outside-repo`; read its diff, then re-implement. Do not run the full suite without the operator's approval.

## 1. The rule and its tests

- [ ] 1.1 Replace the "defaults to the engine folder" test in `tests/test_ocr_worker_core.py` with `test_model_cache_defaults_to_the_user_folder` (variable unset, empty, spaces; `HOME` set to a temporary folder), and add `test_host_and_worker_agree_on_the_model_cache` (unset, blank, spaces, set).
  - Verify: both fail on the current code.
- [ ] 1.2 Change `model_cache_dir` in the worker core and `engine_cache_dir` in `routes.py` (design D1, D2). Drop the engine-folder argument. Update `compose_runtimes.py` (one call), `paths.py` of dots-mocr and `engine.py` of paddleocr-vl.
  - Verify: the 1.1 tests pass; make the host default differ for a moment and see the parity test fail, then restore.
- [ ] 1.3 Update the two `smoke_test.py` scripts to the same rule.
  - Verify: `tests/test_ocr_dots_llamacpp_smoke.py` and `tests/test_ocr_worker_smoke_runner.py` pass.

## 2. Test isolation

- [ ] 2.1 Add the autouse fixture `_isolated_ocr_model_cache` to `tests/conftest.py` and the helper `tests/fixtures/ocr_worker/model_cache.py` (design D4).
  - Verify: a test that prints `OMRS_OCR_MODEL_CACHE` sees a temporary folder.
- [ ] 2.2 Point `stand_in_engine` and `make_engine` at the helper. Change `clean_environ` to drop only the runtime URL. Stop clearing the cache variable in the seven test files that did. Fix the tests that pinned `.model-cache` (`test_ocr_worker_client.py`, `test_ocr_dots_llamacpp_host.py`, `test_ocr_dots_llamacpp_smoke.py`).
  - Verify: `uv run --no-sync pytest -n auto -q -m "not slow" tests/test_ocr_*.py tests/test_llamacpp_runtime_ocr_compose.py tests/unit/test_runtimes_follow_engine_list.py tests/unit/test_ocr_routing_runtime_unavailable.py` passes (622 tests on the branch).

## 3. Docs, ADR and experiments rule

- [ ] 3.1 Update `ocr-workers/README.md` (Model cache section, the runtime block rule, and the one-time `mv`), `docs/guides/ingestion.md`, `docs/guides/configuration.md` and `docs/guides/architecture.md`.
  - Verify: `uv run --no-sync pytest -q tests/test_docs_*.py` passes.
- [ ] 3.2 Add the two rules to `experiments/AGENTS.md` (Local models).
  - Verify: `uv run --no-sync omrs experiments check` reports 0 errors and the experiment record tests pass.
- [ ] 3.3 Move `adr-draft.md` from this folder to `docs/adr/` under the next free number (119 when drafted), fix the number inside it, and add the index row to `ADR_README.md`. Update the commit references in its last section.
  - Verify: the docs tests pass.

## 4. Gates

- [ ] 4.1 Re-pin `_BASE_EXECUTED` in `tests/test_clean_base_tripwire.py` by test-ID diff, with a dated comment. Run `ruff check`, `ruff format --check` and `uv run --no-sync lint-imports`.
  - Verify: `./scripts/local_ci.sh` passes, with the operator's approval to run it.
- [ ] 4.2 Run `openspec validate ocr-model-cache-outside-repo --strict`.
  - Verify: it reports the change as valid.
- [ ] 4.3 Operator step, live app: do the Migration Plan step 4.
  - Verify: the Integrations page shows both engines ready and one small PDF ingest through each works.

## Workflow follow-up

- Open the PR into `v3`, watch CI and handle review comments. Do not merge without the operator.
- Archive the change after review and verification.
- Delete the branch `parked/ocr-model-cache-outside-repo` once the change is merged.
