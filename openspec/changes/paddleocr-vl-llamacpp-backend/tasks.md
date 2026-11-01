# Tasks

Parked. Start only after `managed-llamacpp-runtimes` and `dots-mocr-llamacpp-backend` are merged into `v3`. Create a new worktree `omrs-feat-paddleocr-vl-llamacpp-backend` from `v3` then.

## 1. Settle the open questions

- [ ] 1.1 Read the value that arm P4 passed as `vl_rec_api_model_name` from the Experiment 41 run log or command record.
  - Verify: the value and its source file are recorded under this task.
- [ ] 1.2 Ask the operator where `PaddleOCR-VL-1.6-Q8_0.gguf` is hosted (for example the private `cmdaltctr/omrs-ocr-gguf-converted`), and check the Apache-2.0 terms (licence notice, attribution, statement of changes) before any upload.
  - Verify: the operator's decision, the repository, the pinned commit and a fresh-download SHA-256 match are recorded under this task.

## 2. Engine (tests first)

- [ ] 2.1 Rewrite the `managed-llamacpp-runtimes` scenario "PaddleOCR-VL unchanged" so it names a test engine without a runtime block. Then add the `[tool.omrs-ocr.runtime]` block to `ocr-workers/engines/paddleocr-vl/pyproject.toml` with the design D1 pins.
  - Verify tests first: the host reads the block with no rule failure; every value equals the engine's pins; `openspec validate --all --strict` passes.
- [ ] 2.2 Wire `OMRS_OCR_RUNTIME_URL` into the pipeline as `vl_rec_backend="llama-cpp-server"` and `vl_rec_server_url=<url>/v1` (design D2). A missing or non-loopback URL gives a parse error that names the variable.
  - Verify tests first, with PaddleX mocked: the pipeline gets the URL; the missing URL gives the named error; the layout settings equal P0's.
- [ ] 2.3 Add the fetch step for the two GGUF files and the `b11941` archive, with SHA-256 checks and `.tmp` then rename.
  - Verify tests first: a hash mismatch stops with the file name and leaves no partial file.
- [ ] 2.4 Update the fingerprint (design D3) and re-pin the tripwire by test-ID diff.
  - Verify: the fingerprint test fails before the change; the parallel fast suite and the tripwire pass.

## 3. Ship checks

- [ ] 3.1 The operator reviews the 25 C5 pages for P4 and P0 and records a decision.
  - Verify: the decision and date are recorded under this task. A "no" stops the change here.
- [ ] 3.2 Provision the engine in the worktree (operator approval for the download), then run a real-document check through `build_ocr_routes` with dots.mocr unavailable, so the fallback serves. The operator writes the pass rules before the run.
  - Verify: results and seconds per page are in the engine's `SMOKE_RESULTS.md`.
- [ ] 3.3 Check the default routes: dots.mocr primary, PaddleOCR-VL fallback.
  - Verify: the default-routes test passes unchanged.

## 4. Close

- [ ] 4.1 Update `ocr-workers/README.md`, `docs/guides/ingestion.md` and the engine's licence notes.
  - Verify: the docs name the declared runtime and the one-time re-index.
- [ ] 4.2 Run the parallel fast suite and the tripwire, `openspec validate --all --strict`, and `./scripts/local_ci.sh` with operator approval. Open a pull request into `v3`.
  - Verify: every check is green. Merge only when the operator says so.
