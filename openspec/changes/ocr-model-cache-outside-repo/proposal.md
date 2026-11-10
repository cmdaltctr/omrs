# Proposal

Parked 2026-11-10. Start only after Experiment 35 is done (operator, 2026-11-10). A working version exists on the local branch `parked/ocr-model-cache-outside-repo` (commits `8187b11f` and `843b3a4e`, never pushed). Use it as a reference, or re-implement from `tasks.md`. `adr-draft.md` in this folder is the ADR for the change.

## Why

Each OCR engine keeps its model weights in `<engine folder>/.model-cache`. Git ignores the folder, but it still sits inside the repository, so every checkout and every worktree gets its own copy. On 2026-11-10 the two caches of `omrs-v3` held 7.6 GB (dots-mocr PyTorch weights 5.7 GB, PaddleOCR-VL 1.9 GB). The project runs one worktree per change, so each new worktree that provisions an engine downloads the weights again.

A contributor who follows the README ends up with several GB of weights inside the checkout. Experiments copied the habit: Experiment 38 put 27 GB of model weights and model environments into its own `output/.models`. `OMRS_OCR_MODEL_CACHE` already moves the weights, but only for an operator who knows about it.

## What Changes

- The default weights root becomes `~/.omrs/ocr-models`. Engine `<name>` uses `~/.omrs/ocr-models/<name>/`. `OMRS_OCR_MODEL_CACHE`, when set and not blank, still replaces the root.
- The worker core and the host each resolve the folder. Both stop taking the engine folder. A parity test fails when the two rules disagree.
- **BREAKING**: OMRS no longer reads `<engine folder>/.model-cache`. An operator with weights there moves the folder once. The live app needs the same move and a refresh of its hand-built worker copy under `~/.omrs/ocr-workers`.
- Tests never use the real folder: an autouse fixture points `OMRS_OCR_MODEL_CACHE` at an empty temporary folder for every test.
- The two smoke scripts follow the same rule.
- `experiments/AGENTS.md` gets two rules: keep model weights and model environments outside the experiment folder, and never download weights into `output/`.
- Docs describe the new default and the one-time move. An ADR records the decision and amends ADR-062 decision 5.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ocr-worker-engines`: new requirements for where an engine keeps its model weights, and for the move from the old folder.

## Impact

- `ocr-workers/core/src/omrs_ocr_worker_core/engine.py` (`model_cache_dir`), `ocr-workers/engines/dots-mocr/src/omrs_ocr_dots_mocr/paths.py`, `ocr-workers/engines/paddleocr-vl/src/omrs_ocr_paddleocr_vl/engine.py`, and the two `smoke_test.py` scripts.
- `src/omrs/integrations/ocr_worker/routes.py` (`engine_cache_dir`) and `src/omrs/compose_runtimes.py` (one call).
- Tests: `tests/conftest.py`, a new `tests/fixtures/ocr_worker/model_cache.py`, two OCR fixtures, `clean_environ`, and about twelve OCR test files. The tripwire pin `_BASE_EXECUTED` rises by 4 (the branch counted +4 by test-ID diff; recount at apply).
- Docs: `ocr-workers/README.md`, `docs/guides/ingestion.md`, `docs/guides/configuration.md`, `docs/guides/architecture.md`, `experiments/AGENTS.md`, a new ADR and its index row.
- The engine fingerprint does not include the cache path, so no document is re-indexed.
- Experiment 35 never runs the OCR engines (`ocr_workers_dir` is empty on the pod), but do not merge this change into the Exp 35 branch after its freeze.
- `ocr-engine-install-command` (parked) builds on this change.
