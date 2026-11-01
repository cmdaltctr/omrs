# Tasks

## 1. Pins and the private model copy

- [x] 1.1 Upload `dots-mocr-Q8_0.gguf` and `dots-mocr-mmproj-bf16.gguf` to the private Hugging Face repository `cmdaltctr/omrs-ocr-gguf-converted`. Add a model card that names the source (`rednote-hilab/dots.mocr` at `e539fbb5`), the converter (llama.cpp build 11941), both SHA-256 values and the licence terms. The card must not use the dots.mocr name as a product name (clause 4.4), and must contain no personal paths.
  - Needs the operator's `hf auth login` first.
  - Done 2026-10-31. Repository private; commit `64803a1fa579b1e95be9c352ada2b808d5e708ff`, pinned in `pins.py`. A fresh download of each file at that commit matched `6017b184…` and `63f415f9…`, and the card holds no personal paths.
  - Verify: the Hub API reports the repository as private; a fresh download of each file matches `6017b184…` and `63f415f9…`; `grep -E "/Users/|aizat"` on the card finds nothing.
- [x] 1.2 Record the SHA-256 values of `llama-b11941-bin-macos-arm64.tar.gz` and `llama-b11941-bin-ubuntu-x64.tar.gz` from the `ggml-org/llama.cpp` release `b11941`.
  - Recorded on 2026-10-31 (the GitHub release digests; a downloaded copy of each archive gave the same value):
    - `llama-b11941-bin-macos-arm64.tar.gz`: `fb5c491b35c75731019caa85d704fb839532c15dbb9bd3f6b3f75a667e7ac49a` (16,378,354 bytes).
    - `llama-b11941-bin-ubuntu-x64.tar.gz`: `e8a1ee13aa19c6c78f5651457758160da27410301b179d6ef3505c81c8ea31f1` (22,566,911 bytes). This is the CPU build, which settles the design's open question.
  - The unpacked macOS `llama-server --version` printed `version: 0.7.0-dev (build 11941, commit 19ff817fb)`. The archive holds one folder, `llama-b11941/`, with `llama-server` and its `.dylib` files side by side.
  - Verify: hashing a downloaded copy of each archive gives the recorded value; the unpacked `llama-server --version` reports build 11941.

## 2. The new engine (`ocr-workers/engines/dots-mocr-llamacpp`)

- [x] 2.1 Write a failing test: the `dots-mocr-llamacpp` lockfile holds no `torch`, `torchvision`, `transformers` or `accelerate`. Then create the folder with:
  - `pyproject.toml` (worker core, `pypdfium2`, `pillow`, `huggingface-hub`) and the `dots-mocr-llamacpp` entry point;
  - `requires-acceptance`;
  - a `LICENCE-NOTES.md` copied from the PyTorch engine, plus the provenance of the GGUF files;
  - `uv.lock`.
  - Verify: the test fails before the folder exists and passes after.
- [x] 2.2 Copy the prompt, the render settings and `layout.py` into the new package (design D6). Add a test that the copies match the PyTorch engine byte for byte.
  - Verify: the test passes, and fails when one character of either copy changes.
- [x] 2.3 Write the fetch step (design D3, D4). It downloads the model, the projector and the llama.cpp archive at their pins, checks each SHA-256, writes through a `.tmp` file and a rename, and unpacks the archive into `<engine cache>/llama.cpp/`.
  - Verify with tests written first:
    - a hash mismatch stops with the file name and leaves no partial file;
    - a missing token gives an error that names `hf auth login` and `HF_TOKEN`.
- [x] 2.4 Write the server lifecycle (design D8): a free loopback port, a start timeout with `/health` polling, the build check, a capped log, stop on SIGTERM and exit, and the pid-file clean-up.
  - Verify with tests against a fake server script:
    - the first parse starts it, and a later parse reuses it;
    - closing the worker stops it;
    - a stale server from a killed worker is stopped, and an unrelated pid is left alone;
    - a health timeout returns a parse error that names the log;
    - a wrong build is refused.
  - Note 2026-11-01: superseded. Two OMRS processes started two workers that shared one cache folder, and the second stopped the first one's server. The server lifecycle moves to the host (`managed-llamacpp-runtimes`). Task 2b.2 removes `server.py` and its tests. This task stays ticked as a record of the work done.
- [x] 2.5 Write the engine:
  - `parse` with the D5 request;
  - empty Markdown for a capped or unparsable page;
  - the SHA-256 check of the model files before the server starts;
  - the D7 fingerprint.
  - Verify with tests against the fake server:
    - the request body matches D5;
    - a capped page is empty and the reason is logged;
    - a changed model file returns a parse error that names the file;
    - the fingerprint fields match D7;
    - no module imports `torch`.
- [x] 2.6 Write `smoke_test.py` for the engine, on the pattern of the PyTorch engine's: plan only by default, `--provision` to run, an offline parse of `eq01` p2 and p3 with the network blocked, and capability JSON, timings and peak memory written to `smoke_evidence/`.
  - Verify: a plan-only run lists the steps and touches nothing.
- [x] 2.7 Update the tripwire pin by test ID for the new tests. Run the new engine tests and the OCR route tests.
  - Verify: `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q` passes, then the tripwire passes on that report.

## 2b. Move the engine onto the runtime manager (design D2)

Start this group only after `managed-llamacpp-runtimes` is merged into `v3` and this branch is rebased on `v3`. Write each test first and see it fail.

- [x] 2b.1 Rebase `feat/dots-mocr-llamacpp-backend` on `v3` with `managed-llamacpp-runtimes` merged. Resolve the tripwire pin conflict by test-ID diff, not by hand-edited counts.
  - Verify: `git merge-base --is-ancestor <managed-llamacpp-runtimes merge commit> HEAD` succeeds; the fast suite passes before any further edit.
- [x] 2b.2 Remove `src/omrs_ocr_dots_mocr_llamacpp/server.py`, `tests/test_ocr_dots_llamacpp_server.py`, the `server_log` and `server_pid_file` helpers in `paths.py`, and `tests/fixtures/ocr_worker/fake_llama_server.py`. Point the engine tests at the shared fake in `tests/fixtures/llamacpp/`.
  - Verify: `grep -rn "server_pid_file\|LlamaServer\|install_shutdown_hooks" ocr-workers/engines/dots-mocr-llamacpp tests` finds nothing; no engine module imports `subprocess`.
- [x] 2b.3 Add the `[tool.omrs-ocr.runtime]` block to the engine's `pyproject.toml` (design D2): program, build 11941, the D5 flags, and both files with their SHA-256.
  - Verify tests first: the host's `declared_runtime` reads the block with no rule failure; a test asserts that every value equals `pins.py`, and fails when one character of a hash changes.
- [x] 2b.4 Make the engine read `OMRS_OCR_RUNTIME_URL` and send each page to `<url>/v1/chat/completions`. A missing or non-loopback value gives a parse error that names the variable.
  - Verify tests first, against the shared fake: the request body still matches D5; a missing variable gives the named error; the worker starts no process (a test patches `subprocess.Popen` to fail).
- [x] 2b.5 Move the model-file hash check to the host (design D2). Remove `_verify_model_files` from the engine. Keep the hash checks in `fetch.py`.
  - Verify: a host-path test (`build_ocr_routes` with a test workers folder) shows that a changed model file makes the route unavailable with a reason that names the file, and that the fallback route parses the PDF; the engine test for the old parse-time check is removed with a note in the commit message.
- [x] 2b.6 Update `smoke_test.py`: it starts the runtime through the host's manager with a scratch `OMRS_STATE_DIR`, passes the URL to the worker, and leaves the runtime at the end.
  - Verify: a plan-only run lists the steps and touches nothing; the smoke tests pass against the shared fake.
- [ ] 2b.7 Update the tripwire pin by test-ID diff (removed server tests, new manifest and URL tests). Run the parallel fast suite with a JUnit report, then the tripwire on that report.
  - Verify: both pass; the diff of test IDs is in the commit message.

## 3. Provision and the real-document check (design D9)

Start this group only after group 2b is done.

- [ ] 3.1 Provision `dots-mocr-llamacpp` in this worktree with `--accept-model-licence`. This is a download of about 4.4 GB, plus the binary.
  - Needs operator approval for the download and the licence acceptance.
  - Verify: `--capabilities` prints the D7 fingerprint, and the model files match their hashes.
- [ ] 3.2 Run the smoke test offline (`eq01` p2 and p3).
  - Verify: both pages give non-empty Markdown with the network blocked; the result is in `SMOKE_RESULTS.md`.
- [ ] 3.3 Run the parity check: the 20 T-control pages plus `eq01` p2 and p3, through `build_ocr_routes` with primary `dots-mocr-llamacpp`. Compare with Experiment 41 arm D4 and with the T-control text.
  - Verify:
    - every page Dice is 0.99 or more against D4;
    - at least 18 of 22 pages are identical to D4;
    - the median Dice against T-control is 0.99 or more;
    - the JSON is in `smoke_evidence/`.
- [ ] 3.4 Ingest `eq01`, `io06` and `rf06` into a scratch collection with the CLI, using scratch `LANCEDB_URI` and `OMRS_CONFIG_DIR` and never `~/.omrs`.
  - Verify: search finds a known phrase from an OCR page of each PDF, and KaTeX 0.16.22 renders every formula on the `eq01` pages.
- [ ] 3.5 Start a scratch web preview with `ocr_engine_primary = "dots-mocr-llamacpp"` and open the Integrations page in Orca.
  - Verify: the engine row shows ready at 1,280 px and at 390 px, with screenshots in `smoke_evidence/`.
- [ ] 3.6 Check for a clean exit: stop the CLI run and then the preview server.
  - Verify: `pgrep -fl llama-server` lists no process whose path is inside the engine folder, and the runtime's `server.json` in the scratch `OMRS_STATE_DIR` records `stopped_by` `last-client`.
- [ ] 3.7 Write the results to `SMOKE_RESULTS.md`: pass or fail per rule, seconds per page, peak memory and the llama.cpp build. **Stop here** and ask the operator to confirm cut-over.
  - Verify: the operator's confirmation and its date are recorded under this task.

## 4. Cut-over (only after 3.7 is confirmed)

- [ ] 4.1 Remove `ocr-workers/engines/dots-mocr` (the PyTorch engine). Move `dots-mocr-llamacpp` to `engines/dots-mocr`, and rename the package to `omrs_ocr_dots_mocr` and the entry point to `dots-mocr`. Keep `backend_id` `dots_mocr_llamacpp`.
  - Verify: re-provisioning `dots-mocr` succeeds, and `--capabilities` shows the llama.cpp fingerprint.
- [ ] 4.2 Update the tests. `tests/test_ocr_worker_import_boundary.py` must now assert that no engine lock holds PyTorch. `tests/test_ocr_engine_dots_mocr.py` moves to the llama.cpp engine, the patch and code-hash tests go, and the D6 copy test goes. Re-pin the tripwire by test ID.
  - Verify: each changed assertion fails on the old tree first; the parallel fast suite and the tripwire pass.
- [ ] 4.3 Update `docs/guides/ingestion.md`, `docs/guides/configuration.md`, `docs/guides/architecture.md`, `ocr-workers/README.md` and the engine's `LICENCE-NOTES.md`. Cover the llama.cpp runtime, the pins, the token needed for a private repository, peak memory, and the one-time re-index.
  - Verify: `grep -rn "PyTorch\|torch" docs/guides ocr-workers/README.md` names no OCR engine.
- [ ] 4.4 Write the ADR "dots.mocr runs on llama.cpp", and append a dated note to ADR-072 (no edits to its old text). The ADR states that Experiment 41 failed the speed gate, records the operator's reasons for moving anyway, and cites the D9 results. Add it to the ADR index.
  - Verify: the index lists the new ADR, and ADR-072 links to it.
- [ ] 4.5 Provision the new `dots-mocr` engine in the live workers folder `~/.omrs/ocr-workers`, then restart the live web app.
  - Needs operator approval before touching the live app. The next ingest re-indexes the live collections.
  - Verify: the live Integrations page shows `dots-mocr` ready, and one live ingest of a scanned PDF returns OCR text.

## 5. Close

- [ ] 5.1 Run `./scripts/local_ci.sh` (ask the operator before the full run).
  - Verify: every step passes, and no step reports `SKIPPED` without a stated reason.
- [ ] 5.2 Run `openspec validate --all --strict`.
  - Verify: everything passes.
- [ ] 5.3 Open the pull request into `v3`, wait for CI, and work through the review comments.
  - Verify: every CI check is green, and every review thread is answered and resolved. Merge only when the operator says so.

## Workflow follow-up

- Archive this change after the merge, then sync `ocr-worker-engines`.
- Before `git worktree remove`, copy `smoke_evidence/` and any scratch results to `~/Development/DATA/omrs/` with their SHA-256 values. Never copy `.env`.
- Keep the PyTorch model cache copy in `~/Development/DATA/omrs` for rollback.
