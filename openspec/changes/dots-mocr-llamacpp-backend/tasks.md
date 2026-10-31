# Tasks

## 1. Pins and the private model copy

- [ ] 1.1 Upload `dots-mocr-Q8_0.gguf` and `dots-mocr-mmproj-bf16.gguf` to the private Hugging Face repository `cmdaltctr/omrs-ocr-gguf-converted`. Add a model card that names the source (`rednote-hilab/dots.mocr` at `e539fbb5`), the converter (llama.cpp build 11941), both SHA-256 values and the licence terms. The card must not use the dots.mocr name as a product name (clause 4.4), and must contain no personal paths.
  - Needs the operator's `hf auth login` first.
  - Deferred by the operator on 2026-10-31: the upload happens later, so this task stays unticked. Until it is done, the engine's pinned model revision is a placeholder that makes the fetch step refuse to run (task 2.3).
  - Verify: the Hub API reports the repository as private; a fresh download of each file matches `6017b184…` and `63f415f9…`; `grep -E "/Users/|aizat"` on the card finds nothing.
- [x] 1.2 Record the SHA-256 values of `llama-b11941-bin-macos-arm64.tar.gz` and `llama-b11941-bin-ubuntu-x64.tar.gz` from the `ggml-org/llama.cpp` release `b11941`.
  - Recorded on 2026-10-31 (the GitHub release digests; a downloaded copy of each archive gave the same value):
    - `llama-b11941-bin-macos-arm64.tar.gz`: `fb5c491b35c75731019caa85d704fb839532c15dbb9bd3f6b3f75a667e7ac49a` (16,378,354 bytes).
    - `llama-b11941-bin-ubuntu-x64.tar.gz`: `e8a1ee13aa19c6c78f5651457758160da27410301b179d6ef3505c81c8ea31f1` (22,566,911 bytes). This is the CPU build, which settles the design's open question.
  - The unpacked macOS `llama-server --version` printed `version: 0.7.0-dev (build 11941, commit 19ff817fb)`. The archive holds one folder, `llama-b11941/`, with `llama-server` and its `.dylib` files side by side.
  - Verify: hashing a downloaded copy of each archive gives the recorded value; the unpacked `llama-server --version` reports build 11941.

## 2. The new engine (`ocr-workers/engines/dots-mocr-llamacpp`)

- [ ] 2.1 Write a failing test: the `dots-mocr-llamacpp` lockfile holds no `torch`, `torchvision`, `transformers` or `accelerate`. Then create the folder with:
  - `pyproject.toml` (worker core, `pypdfium2`, `pillow`, `huggingface-hub`) and the `dots-mocr-llamacpp` entry point;
  - `requires-acceptance`;
  - a `LICENCE-NOTES.md` copied from the PyTorch engine, plus the provenance of the GGUF files;
  - `uv.lock`.
  - Verify: the test fails before the folder exists and passes after.
- [ ] 2.2 Copy the prompt, the render settings and `layout.py` into the new package (design D6). Add a test that the copies match the PyTorch engine byte for byte.
  - Verify: the test passes, and fails when one character of either copy changes.
- [ ] 2.3 Write the fetch step (design D3, D4). It downloads the model, the projector and the llama.cpp archive at their pins, checks each SHA-256, writes through a `.tmp` file and a rename, and unpacks the archive into `<engine cache>/llama.cpp/`.
  - Verify with tests written first:
    - a hash mismatch stops with the file name and leaves no partial file;
    - a missing token gives an error that names `hf auth login` and `HF_TOKEN`.
- [ ] 2.4 Write the server lifecycle (design D8): a free loopback port, a start timeout with `/health` polling, the build check, a capped log, stop on SIGTERM and exit, and the pid-file clean-up.
  - Verify with tests against a fake server script:
    - the first parse starts it, and a later parse reuses it;
    - closing the worker stops it;
    - a stale server from a killed worker is stopped, and an unrelated pid is left alone;
    - a health timeout returns a parse error that names the log;
    - a wrong build is refused.
- [ ] 2.5 Write the engine:
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
- [ ] 2.6 Write `smoke_test.py` for the engine, on the pattern of the PyTorch engine's: plan only by default, `--provision` to run, an offline parse of `eq01` p2 and p3 with the network blocked, and capability JSON, timings and peak memory written to `smoke_evidence/`.
  - Verify: a plan-only run lists the steps and touches nothing.
- [ ] 2.7 Update the tripwire pin by test ID for the new tests. Run the new engine tests and the OCR route tests.
  - Verify: `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q` passes, then the tripwire passes on that report.

## 3. Provision and the real-document check (design D9)

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
  - Verify: `pgrep -fl llama-server` lists no process whose path is inside the engine folder.
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
