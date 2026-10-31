# Tasks

## 1. Plan

- [x] 1.1 Create the worktree `omrs-feat-experiment-41-ocr-runtimes` from `v3`. Verify: `git rev-parse --show-toplevel` and `git branch --show-current` match.
- [x] 1.2 Write `protocol.md` and `plan.json` in `experiments/41-ocr-runtimes-2026-10-30/`. Verify: page lists copied from Experiment 37 with SHA-256 `09f13055`; all four approvals `false`; gates set on 2026-10-06 and carried forward.
- [x] 1.3 Check the Hub facts behind the arms (every GGUF and MLX build for both models, base weights identity, file hashes). Verify: each fact is recorded in `protocol.md` section "Facts checked on 2026-10-30".
- [x] 1.4 Operator decides DR-4 (precision list). Verify: `open_decisions` records it with its date (2026-10-30).
- [x] 1.4a Operator confirms DR-2 (licence scope). Verify: `open_decisions` records it with its date.

## 2. Approvals (operator, one by one)

- [x] 2.1 Approve installing `mlx-vlm` and the llama.cpp conversion tools. Verify: `approvals.install_tooling` is `true`.
- [x] 2.2 Approve the model downloads. Verify: `approvals.model_downloads` is `true`; target is `OMRS_OCR_MODEL_CACHE`.
- [x] 2.3 Approve the licence scope (DR-2). Verify: `approvals.licence_check` is `true` and the decision is dated.
- [x] 2.4 Approve the OCR run budget. Verify: `runtime_budget_h` filled and `approved` is `true`.

## 3. Conversions, pins and freeze

- [x] 3.1 Convert dots.mocr to GGUF bf16 plus bf16 mmproj at llama.cpp build 11941 (kept as the D3 diagnostic). Verify: the file loads and the smoke pages give output (OI-2), or the failure is recorded as a finding (arm D4 stops).
- [x] 3.1a Cross-check D4 against `lodrick-the-lafted/dots.mocr-gguf` Q8_0 with the same bf16 mmproj on the smoke pages (OI-9). Verify: outputs match, or the difference is recorded and resolved before the D4 run.
- [x] 3.2 Quantise dots.mocr to Q8_0. Verify: SHA-256 recorded.
- [x] 3.3 Download the official PaddleOCR-VL-1.6 GGUF (kept as the P3 diagnostic). Verify: 16-bit tensor type confirmed from the header (OI-3); SHA-256 recorded.
- [x] 3.4 Quantise the official PaddleOCR-VL-1.6 GGUF to Q8_0 with `llama-quantize`. Verify: SHA-256 recorded.
- [x] 3.5 Download the MLX 8-bit builds in `mlx_pins` (OI-4). Leave the 16-bit diagnostic builds until a diagnostic triggers. Verify: revision and SHA-256 match the pins; each build loads in `mlx-vlm`.
- [x] 3.6 Add the `runtime` block to `plan.json` with the real SHA-256 values and the pinned server flags (`-c`, `--image-min-tokens`, `--image-max-tokens`, `--temp 0`, `--mmproj`; P arms use `max_new_tokens` 4096, D arms 8192). Record any changed mmproj as a pinned file with its own SHA-256. Verify: `omrs experiments check` passes the block.
- [x] 3.7 Close OI-1, OI-2, OI-5, OI-6 and OI-7 (OI-11 is closed). Verify: each item answered in `plan.json`.
- [x] 3.8 Run the parity check on the smoke pages (`eq01` p2 and p3) for each 8-bit arm: image token grids against the baseline (D arms: at most one patch row or column of difference; P arms: the same per layout block). Verify: grids match, or the arm stops and a finding is recorded; a build that ignores `--image-min-tokens` or `--image-max-tokens` stops that arm (OI-10); the tolerance is not loosened.
- [x] 3.9 Freeze `plan.json` after the runtime block and pins (3.6), the closed items (3.7) and the parity check (3.8), before the first run. Verify: SHA-256 recorded in this file; a later setting change is a dated amendment.
  Frozen 2026-10-30. SHA-256 `8bef273844c21bb182ca32cbc3376f0a317175898abd5b65019702d3302ccd66` (rule in `plan.json` `freeze.sha256_of`).

## 4. Build the runners

- [x] 4.1 Write `run_ocr.py` (`--backend {mlx,llamacpp}`, status inside it with `--status`), `summarise.py` and `analysis.py` (similarity scoring). Reuse `score_recall.py` and `check_katex.mjs` from Experiment 37 by path; do not copy them. Verify: 3 scripts at most (Standard limit); `uv run ruff check` and `ruff format --check` pass; a dry run lists 257 pages.
- [x] 4.2 Call `verify_llamacpp_runtime` before the first score, and write run records. Verify: a wrong build or hash stops the run in a test.

## 5. Run

- [x] 5.1 Run the two-page smoke test (`eq01` p2 and p3) for each new arm. Verify: non-empty output; compare with the scratch figures. Cover OI-10 (conversion at build 11941; mmproj speed on Metal).
- [x] 5.2 Run each new arm alone through `E-maths`, `E-scan` and `E-script`. Verify: state file shows 257 pages; no other GPU job ran.
  Run 2026-10-31, one arm at a time (D4, D2, P4, P2), 257 pages each, 0 timeouts. Only the idle live app (port 9931, embedding model loaded) ran beside them.
- [x] 5.3 If a measured speed-up is at least 1.5 times and below 3 times, run `T-control` for that baseline. Verify: timings recorded apart from the Experiment 37 figures, or a note that no comparison fell in the band.
  Not run, by operator-approved recommendation (2026-10-31). Only D2 (2.5 times) fell in the band. D2 is a comparison arm, and D4 fails C1 whatever the D0 re-timing says (it would need a D0 median of 88 s or more). Recorded in `report.md`.

## 6. Score and review

- [x] 6.1 Score KaTeX, recall and similarity for every arm. Verify: output files exist for each arm.
- [x] 6.2 Build the review page for each arm (10 lowest-similarity pages, every screened page, 5 random pages, seed 41). Verify: the checks in `references/review-page-pattern.md` pass.
- [x] 6.3 Operator reviews and records the verdicts. Verify: the SHA-256 of the verdict file is recorded.
  Done 2026-10-31 by Claude (four parallel Sonnet reviewers, cross-checked by a foreign-script and repeated-phrase count), on the operator's instruction and acceptance ("just accept AI spot check"). The plan names the operator as the C5 reviewer, so `report.md` states that this is an AI review. `plan.json` is not amended. `review_verdicts.json` SHA-256 `7e68db96dedaf78dbc916309b38a2b039f3368e7da8a83fa2cda0f764dbae3b0`.
- [x] 6.4 For each 8-bit arm that fails C3, C4 or C5, run its 16-bit diagnostic on the failed gate's pages and score that gate only. Verify: `output/` holds a diagnostic result per triggered arm, or `summary.json` records that none triggered.
  Triggered by C5 for D4, P4 and P2. D3, P3 and P1 ran on the review lists of D4, P4 and P2 (2026-10-31). `summary.json` `diagnostics` holds the result: D3 1 of 17 pages invented, P3 12 of 25, P1 15 of 26. None passes, so none changes a verdict. D0 and P0 were also reviewed on the same pages as a control (0 of 17 and 15 of 25). Verdicts: `review_verdicts_diagnostic.json` SHA-256 `f75e9457f616e610fd169786328271ad656e1cd98341f93009e9b21a035e7ead`. Reviewer: Claude, as for 6.3.

## 7. Close out

- [x] 7.1 Write `output/summary.json` and `report.md`. Verify: every number in the report traces to `summary.json`.
- [x] 7.2 Set `status` and `finding` in `experiment.json`. Verify: `omrs experiments check` passes.
- [x] 7.3 If a llama.cpp arm passes for an engine, propose a follow-up OpenSpec change for that engine. Verify: next step named in the report; no engine, route or default changed here.
  No llama.cpp arm passed (D4 fails C1 and C5, P4 fails C5), so no follow-up change is proposed. The report names a separate experiment on PaddleOCR-VL's wrong-script text as the next step.
- [x] 7.4 Run `openspec validate --all --strict`. Verify: all pass.
- [x] 7.5 Archive this change after verification. Verify: the operator confirms before any push.
  Verified 2026-10-31: `openspec validate --all --strict` (90 of 90), `omrs experiments check` (0 errors), `report.md` numbers checked against `output/summary.json`. The operator asked for the remaining steps to run on the recommendation. Nothing is pushed.
