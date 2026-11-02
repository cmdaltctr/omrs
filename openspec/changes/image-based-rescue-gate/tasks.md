# Tasks: Experiment 43, image-based check on the bad PDFs

Run in a sibling worktree `omrs-feat-image-based-rescue-gate` from `v3`. Large files stay outside git.

## 1. Plan

- [x] 1.1 Scaffold `experiments/43-image-rescue-gate-2026-11-02/` with `protocol.md`, `plan.json` (PLANNED) and `experiment.json`. Verify: `omrs experiments check` passes, and the commit precedes any `output/` file.
- [x] 1.2 Write the question, text head (2,000 characters), image settings (150 DPI, 1,568 px), pass rule and D2 threshold rule into `plan.json`. Verify: the commit precedes task 3.1.
- [x] 1.3 Operator records the approval to send page images to TypeSafe, naming the documents (it includes `rf06` and `rf07`). Verify: a dated entry exists in `plan.json` before task 3.5 starts.

## 2. Runtime and inputs

- [x] 2.1 Check the build (b11941) and both Clef-Flash file hashes against `plan.json`, then run the smoke test (right text, wrong text, one page). Verify: the answers differ in the expected direction; without the projector file the run stops before scoring.
- [x] 2.2 Check the Experiment 33 inputs: run its `freeze.py --check`, list PDFs, page images and labels for the 40 documents. Verify: prints `freeze verified`, and a missing file stops the run with its path.
- [x] 2.3 Extract the rescued text per page with the shipped LiteParse and pypdf adapters. Verify: one text per page, tool versions recorded, and the junk layer of `rf06` page 29 reads as in issue #161.

## 3. Score and decide

- [x] 3.1 Fit the threshold on the healthy pages (D2) and commit it. Verify: the value is in `plan.json` before any junk page is scored.
- [x] 3.2 Write the scoring script (image plus text head, one request at a time, checkpoints, atomic writes) and a test with a fake server. Verify: the test checks that the request holds the image and the text head, and fails when either is missing.
- [x] 3.3 Score all pages with the treatment, and the word check on the same pages. Verify: every page has a score, failed requests are counted, and a resumed run does not rescore.
- [x] 3.4 Write `analysis.py`: junk caught, healthy flagged, routed documents at the 10% and one-page rules, OCR cost. Verify: a small fixed table gives known values, and a broken rule fails a test.
- [x] 3.5 Score the same pages with hosted Jev (D7), after the operator has recorded the approval in `plan.json`. Write a scoring script with a fake-server test for the request shape, key handling and model-id stop. Verify: the returned model id is recorded for every page, the run stops if it changes, and the key never appears in any output.

## 4. Report

- [x] 4.1 Write `report.md` with the verdict against the pass rule, the local arm beside the hosted Jev arm, tables, speed and memory, and the limits from D2. Verify: every number comes from `output/summary.json`.
- [ ] 4.2 Record the result in `experiment.json` and the index, and comment on issue #161. Verify: `omrs experiments check` passes and the comment exists. A PASS opens a follow-up change and ADR. A FAIL leaves #161 open.
- [x] 4.3 Run `openspec validate --all --strict` and the fast tests. Verify: all pass, and nothing under `src/` changed.

## Workflow follow-up

- Open the pull request into `v3`. Do not merge until told.
- Copy `output/` to `~/Development/DATA/omrs/experiments/43-image-rescue-gate-2026-11-02/` before removing the worktree, and record the SHA-256 values.
