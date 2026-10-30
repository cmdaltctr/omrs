# Tasks

## 1. Plan

- [x] 1.1 Create the worktree `omrs-feat-experiment-41-ocr-runtimes` from `v3`. Verify: `git rev-parse --show-toplevel` and `git branch --show-current` match.
- [x] 1.2 Write `protocol.md` and `plan.json` in `experiments/41-ocr-runtimes-2026-10-30/`. Verify: page lists copied from Experiment 37 with SHA-256 `09f13055`; all four approvals `false`; gates set on 2026-10-06 and carried forward.
- [x] 1.3 Check the Hub facts behind the arms (every GGUF and MLX build for both models, base weights identity, file hashes). Verify: each fact is recorded in `protocol.md` section "Facts checked on 2026-10-30".
- [x] 1.4 Operator decides DR-4 (precision list). Verify: `open_decisions` records it with its date (2026-10-30).
- [ ] 1.4a Operator confirms DR-2 (licence scope). Verify: `open_decisions` records it with its date.

## 2. Approvals (operator, one by one)

- [ ] 2.1 Approve installing `mlx-vlm` and the llama.cpp conversion tools. Verify: `approvals.install_tooling` is `true`.
- [ ] 2.2 Approve the model downloads. Verify: `approvals.model_downloads` is `true`; target is `OMRS_OCR_MODEL_CACHE`.
- [ ] 2.3 Approve the licence scope (DR-2). Verify: `approvals.licence_check` is `true` and the decision is dated.
- [ ] 2.4 Approve the OCR run budget. Verify: `runtime_budget_h` filled and `approved` is `true`.

## 3. Conversions, pins and freeze

- [ ] 3.1 Convert dots.mocr to GGUF bf16 plus bf16 mmproj at llama.cpp build 11941 (kept as the D3 diagnostic). Verify: the file loads and the smoke pages give output (OI-2), or the failure is recorded as a finding (arm D4 stops).
- [ ] 3.1a Cross-check D4 against `lodrick-the-lafted/dots.mocr-gguf` Q8_0 with the same bf16 mmproj on the smoke pages (OI-9). Verify: outputs match, or the difference is recorded and resolved before the D4 run.
- [ ] 3.2 Quantise dots.mocr to Q8_0. Verify: SHA-256 recorded.
- [ ] 3.3 Download the official PaddleOCR-VL-1.6 GGUF (kept as the P3 diagnostic). Verify: 16-bit tensor type confirmed from the header (OI-3); SHA-256 recorded.
- [ ] 3.4 Quantise the official PaddleOCR-VL-1.6 GGUF to Q8_0 with `llama-quantize`. Verify: SHA-256 recorded.
- [ ] 3.5 Download the MLX 8-bit builds in `mlx_pins` (OI-4). Leave the 16-bit diagnostic builds until a diagnostic triggers. Verify: revision and SHA-256 match the pins; each build loads in `mlx-vlm`.
- [ ] 3.6 Add the `runtime` block to `plan.json` with the real SHA-256 values and the pinned server flags (`-c`, `--image-min-tokens`, `--image-max-tokens`, `--temp 0`, `--mmproj`; P arms use `max_new_tokens` 4096, D arms 8192). Record any changed mmproj as a pinned file with its own SHA-256. Verify: `omrs experiments check` passes the block.
- [ ] 3.7 Close OI-1, OI-2, OI-5, OI-6 and OI-7 (OI-11 is closed). Verify: each item answered in `plan.json`.
- [ ] 3.8 Run the parity check on the smoke pages (`eq01` p2 and p3) for each 8-bit arm: image token grids against the baseline (D arms: at most one patch row or column of difference; P arms: the same per layout block). Verify: grids match, or the arm stops and a finding is recorded; a build that ignores `--image-min-tokens` or `--image-max-tokens` stops that arm (OI-10); the tolerance is not loosened.
- [ ] 3.9 Freeze `plan.json` after the runtime block and pins (3.6), the closed items (3.7) and the parity check (3.8), before the first run. Verify: SHA-256 recorded in this file; a later setting change is a dated amendment.

## 4. Build the runners

- [ ] 4.1 Write `run_ocr.py` (`--backend {mlx,llamacpp}`, status inside it with `--status`), `summarise.py` and `analysis.py` (similarity scoring). Reuse `score_recall.py` and `check_katex.mjs` from Experiment 37 by path; do not copy them. Verify: 3 scripts at most (Standard limit); `uv run ruff check` and `ruff format --check` pass; a dry run lists 257 pages.
- [ ] 4.2 Call `verify_llamacpp_runtime` before the first score, and write run records. Verify: a wrong build or hash stops the run in a test.

## 5. Run

- [ ] 5.1 Run the two-page smoke test (`eq01` p2 and p3) for each new arm. Verify: non-empty output; compare with the scratch figures. Cover OI-10 (conversion at build 11941; mmproj speed on Metal).
- [ ] 5.2 Run each new arm alone through `E-maths`, `E-scan` and `E-script`. Verify: state file shows 257 pages; no other GPU job ran.
- [ ] 5.3 If a measured speed-up is at least 1.5 times and below 3 times, run `T-control` for that baseline. Verify: timings recorded apart from the Experiment 37 figures, or a note that no comparison fell in the band.

## 6. Score and review

- [ ] 6.1 Score KaTeX, recall and similarity for every arm. Verify: output files exist for each arm.
- [ ] 6.2 Build the review page for each arm (10 lowest-similarity pages, every screened page, 5 random pages, seed 41). Verify: the checks in `references/review-page-pattern.md` pass.
- [ ] 6.3 Operator reviews and records the verdicts. Verify: the SHA-256 of the verdict file is recorded.
- [ ] 6.4 For each 8-bit arm that fails C3, C4 or C5, run its 16-bit diagnostic on the failed gate's pages and score that gate only. Verify: `output/` holds a diagnostic result per triggered arm, or `summary.json` records that none triggered.

## 7. Close out

- [ ] 7.1 Write `output/summary.json` and `report.md`. Verify: every number in the report traces to `summary.json`.
- [ ] 7.2 Set `status` and `finding` in `experiment.json`. Verify: `omrs experiments check` passes.
- [ ] 7.3 If a llama.cpp arm passes for an engine, propose a follow-up OpenSpec change for that engine. Verify: next step named in the report; no engine, route or default changed here.
- [ ] 7.4 Run `openspec validate --all --strict`. Verify: all pass.
- [ ] 7.5 Archive this change after verification. Verify: the operator confirms before any push.
