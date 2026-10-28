# Tasks

## 0. Set up

- [x] 0.1 Create the worktree `../omrs-v3-feat-integrations-show-runtime-components` on branch `feat/integrations-show-runtime-components` from `v3`. Run `uv sync --frozen --extra web` in it. Verify: `git rev-parse --show-toplevel` and `git branch --show-current` name the new worktree and branch.
- [x] 0.2 Save the fast-suite test IDs before the change, outside git (one redaction test ID holds a fake key). Verify: `evidence/test-ids-summary.txt` records the count and the diff files list each change.

## 1. Runtime probes (design D1)

- [x] 1.1 Move the `[tool.omrs-ocr]` manifest read into a standard-library helper in `integrations/ocr_worker/`. Make `provision.py` and the probe use it. Write the test first: a manifest with `requires-acceptance = true` gives the licence file. Verify: the test fails before the helper exists; the existing `provision.py` tests still pass.
- [x] 1.2 Write failing tests for the OCR engine items: no workers folder gives `not-configured`; a folder without `.venv` gives `missing` with the right fix, with and without the licence flag; a folder with `.venv/bin/python` gives `ready`; `used_by` names `ocr_engine_primary`. Then write the probe with `resolve_engine_command`. Verify: the tests fail first, then pass.
- [x] 1.3 Write failing tests for the model file items with a patched `try_to_load_from_cache`: cached gives `ready`, not cached gives `missing` with the `uvx --from huggingface_hub hf download …` fix at the pinned revision, and no network call happens (a network guard fixture fails the test on a request). Then write the probe. Verify: the tests fail first, then pass.
- [x] 1.4 Write failing tests for the local server items against a stub server: answering gives `ready`, a closed port gives `not-running`, a 3 s delay gives `not-running` within 2 s in total, and a credential in the address is removed. Then write the probes with `httpx` and `asyncio.gather`. Verify: the tests fail first, then pass.
- [x] 1.5 Write a failing test that a probe that raises gives `unknown`, a 200 response, and no error text. Add the `runtime` block to `GET /v1/integrations` and to `openapi.yaml`. Verify: the test passes, and the OpenAPI contract test passes.

## 2. Provider readiness (design D2)

- [x] 2.1 Write failing tests: the llama.cpp entry has `readiness.ready` false and the address in its line when the stub server is down; the OpenRouter entry gives "No key set" without a key reference; the status field and "Base default" do not change. Then add `readiness`. Verify: the tests fail first, then pass; the existing catalogue tests still pass.

## 3. Writable workers folder (design D3)

- [x] 3.1 Write failing tests for the folder rule: a relative path, a missing folder and a folder without `engines/` give 400 and leave the file unchanged; a valid folder under home is stored with `~`; an empty value removes the key; a value set by `env` stays locked. Then remove the key from `READ_ONLY_KEYS` and add the rule. Verify: the tests fail first, then pass; `tests/` for `settings_file_write` still pass.

## 4. Read document step OCR options (design D4)

- [x] 4.1 Write failing tests for `ReadParams`: each of the eight keys accepts `None` and a valid value; `ocr_fallback_page_fraction` 1.5 and `ocr_routing_unit` `"pages"` give `invalid_parameter`; an engine that is not provisioned gives `option_unavailable`, with the node, the engine and the provision command. Then add the fields and the admission check. Verify: the tests fail first, then pass.
- [x] 4.2 Write failing tests: `overrides.ocr_engine_primary` gives `host_owned_setting` with the step hint. Then extend `_HOST_OWNED_EXACT` and `_HOST_OWNED_HINTS`. Verify: the tests fail first, then pass.
- [x] 4.3 Write failing tests for `with_read_options`: a node that sets `ocr_fallback_enabled` false reads a flagged PDF without OCR; a node that sets `paddleocr-vl` sends the request to a fake `paddleocr-vl` client; a node that inherits uses the host engine. Then replace `with_pdf_reader`. Verify: the tests fail first, then pass; the existing `pdf_reader` step tests still pass.
- [x] 4.4 Write failing tests for the identity: an engine change makes the next ingest process the source again; an all-inherit template keeps the standard-path identity (compare with the stored identity of an existing test fixture). Then add `read_options` to `IngestionShape`. Verify: the tests fail first, then pass. Mutation check: stop the identify step from receiving the step OCR options (`IngestionShape.step_options`), and confirm the identity test fails. Removing them from `identity_block` alone is not caught, because the graph fingerprint already hashes every node parameter (`evidence/mutation-read-options.txt`).

## 5. OCR client pool (design D5)

- [x] 5.1 Write failing tests with fake route commands: two nodes with one engine share one client; the host route and an inheriting node share one client; two engines never dispatch at the same time (a fake parse that records overlap). Then write `OcrClientPool` and wire it in composition and `plan_run`. Verify: the tests fail first, then pass; `lint-imports` passes with no new `ignore_imports`.
- [x] 5.2 Write failing tests for the start-up line `OCR routes: primary=<engine> [provisioned|not provisioned], fallback=…`, built from the engine folders alone, so no worker starts. Call it from `build_engine`. Verify: the tests fail first, then pass; removing the call makes `test_build_engine_logs_the_line` fail.

## 6. Web (load `omrs-design` before UI work)

- [x] 6.1 Write failing Vitest tests for the three groups: red status for a used, missing item; plain status for an unused one; the copy command; the empty-state text. Then build the groups in `web/src/integrations/`. Verify: the tests fail first, then pass.
- [x] 6.2 Write failing tests for the workers-folder field: Save sends the key; a refusal shows the reason; a locked key is read-only and names the variable; a saved value shows "applies at the next launch" and the restart action. Then build the field. Verify: the tests fail first, then pass.
- [x] 6.3 Write failing tests for the readiness line on the llama.cpp and OpenRouter cards. Then add it. Verify: the tests fail first, then pass.
- [x] 6.4 Add Studio labels for the eight step settings, and show engine readiness in the engine choice. Verify: a Studio test shows "Inherit", `dots-mocr` and `paddleocr-vl` with their state.
- [x] 6.5 Run the browser check on a scratch server (scratch `OMRS_CONFIG_DIR`, fixed port) at 1280 px and 390 px, after telling the user. Verify: `evidence/browser-check.json` records each row and no sideways page scroll at 390 px. Screenshots stay out of the repository, because they can show local paths.

## 7. Docs and decision

- [x] 7.1 Write ADR-105, "Pipeline steps own their OCR settings". It amends design D5 of `add-pdf-reader-step-setting`. Verify: `docs/adr/ADR_README.md` lists it.
- [x] 7.2 Update `docs/guides/configuration.md` (workers folder on the Integrations page, step OCR options, memory note for mixed engines) and `docs/guides/ingestion.md`. Grep `docs/guides/` for "read-only" next to `ocr_workers_dir`. Verify: no stale statement remains.

## 8. Integration checks

- [x] 8.1 Re-pin the tripwire from the test-ID diff against the saved before-list (`evidence/test-ids-summary.txt`), with a dated comment under 100 characters. Verify: `uv run --no-sync pytest tests/test_clean_base_tripwire.py -q` passes.
- [x] 8.2 Run `./scripts/local_ci.sh`. Verify: every step passes, and no step prints `SKIPPED` unless the PR body names it.
- [x] 8.3 Run `openspec validate integrations-show-runtime-components --strict` and `openspec validate --all --strict`. Verify: both pass.

## 9. Remove the OCR worker command (design D7)

- [x] 9.1 Write failing tests: `OCR_WORKER_COMMAND` or `OCR_WORKER_ENV_DIR` in the environment fails `check_legacy_env_vars` with a message that names `OCR_WORKERS_DIR` and `OCR_ENGINE_PRIMARY`; `Settings` and `EffectiveSettings` have neither field; a node engine always resolves from the workers folder. Then remove the fields, the override branch and the start-up label. Verify: tests fail first, then pass; `tests/test_ocr_routes.py` passes with the explicit-command cases removed.
- [x] 9.2 Write failing tests that `GET /v1/settings/document-reading` has no `worker_command_set` and the page shows no worker-command note. Remove them from the route, `openapi.yaml`, the web client and the section. Verify: tests fail first, then pass; `npm run typecheck` passes.
- [x] 9.3 Remove the old command from `.env.example`, `docs/guides/` and `ocr-workers/README.md`. Leave ADRs and experiment folders as records. Verify: `grep -rn OCR_WORKER_COMMAND src web/src docs/guides .env.example ocr-workers/README.md` finds only the `config/legacy.py` entry and its guide note.
- [x] 9.4 Re-pin the tripwire, run `./scripts/local_ci.sh` and `openspec validate --all --strict`. Verify: every step passes.
