# Design: master execution order for the document-reading and dots-mocr flow

## Context

See proposal.md. Facts below were checked on 2026-11-02 against the repos, code and packages; the source of each is named. The operator's rules live in the repo `AGENTS.md` and the handoff `~/Development/DATA/omrs/handoffs/2026-11-02-doc-reading-and-dots-mocr-handoff.md` (facts, results, commit IDs).

Worktrees (siblings under `~/Development/PROJECTS/om-systems/omrs/`, all clean, nothing pushed, 2026-11-02):

| Worktree | Branch | State |
| --- | --- | --- |
| `omrs-v3` | `v3` | Proposals A, B, C, `skip-blank-pages-before-worker` committed. Last commit `7823fc88`. |
| `omrs-feat-dots-mocr-llamacpp-backend` | `feat/dots-mocr-llamacpp-backend` | Last commit `d552a92d`. Tasks 2b.1 to 2b.7, 3.1 to 3.3, 3.5, 3.6 ticked; 3.4 and 3.7 open. Tripwire pin `_BASE_EXECUTED = 9859`. |
| `omrs-feat-image-based-rescue-gate` | `feat/image-based-rescue-gate` | Experiment 43. Last commit `4c7a8bf4`. |

## Goals / Non-Goals

**Goals:**

- One recorded order an agent can follow group by group, stopping at every gate.
- Correctness before optimisation: the #161 fix is verified before blank-page skipping is built.
- Evidence before defaults: the `document` unit and the 10% rule are removed only after the pre-registered re-test.

**Non-Goals:**

- No new code, settings or concepts in this change.
- No re-planning of the changes it orders; each keeps its own tasks and design.
- No decision made here that belongs to the operator.

## D1. Why blank pages moved after the dots-mocr merge

Task 4.1 of `skip-blank-pages-before-worker` re-runs the 10-page `rf06` extract with `dots-mocr-llamacpp` and checks the `llama-server` log. That engine folder exists only on `feat/dots-mocr-llamacpp-backend`; `v3` has `dots-mocr` (PyTorch) and `paddleocr-vl` only (checked). Running the blank-page change first either stalls on its own verification or forces a workaround. After the dots-mocr change merges (group 2), the engine sits on `v3` and task 4.1 runs cleanly. If group 4's rename already applied, the engine is named `dots-mocr` with `backend_id` `dots_mocr_llamacpp`; update the engine name in the task 4.1 verification note, not the measured rule.

## D2. Why the default flip waits for the re-test

Evidence for page routing today: one scratch run on a 10-page `rf06` extract (page 29 found, 5 worker pages, 1 local page, 4 blank sheets) and the parity results. Experiment 43 also showed thresholds fitted and judged on the same documents are optimistic. The handoff records the operator's rule: re-test on new documents, pre-registered, before any default change. Group 4 (the re-test) therefore gates group 5 (the flip). The re-test needs no judge model and no proposal; it is an experiment with a protocol committed before any run.

## D3. The local-OCR library trap

`pdf_inspector` 1.17.0 requires compatible PDFium and ONNX Runtime shared libraries for routed OCR; set `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` when they are not on the platform library search path (package METADATA). Without them the local OCR tier raises, `ocr_routing.py` catches it, and flagged pages keep their native junk text with one warning ("Local OCR tier unavailable"). Every page-mode run, scratch or live, must set both variables and then grep the log for that warning. Copies in a project venv: `.venv/lib/python3.14/site-packages/liteparse/libpdfium.dylib` and `.venv/lib/python3.14/site-packages/onnxruntime/capi/libonnxruntime.1.28.0.dylib`.

## D4. The 10-page `rf06` extract

The scratch extract from the 2026-11-02 page-mode test may not exist any more. Its original `rf06` pages: 20, 29, 33, 40, 46, 50, 60, 70, 80, 86. Of these, 20, 40, 70 and 80 are blank sheets; 29, 33, 46, 50 and 86 went to the worker engine; 60 resolved locally (confidence 0.91). Recreate the extract from the `rf06` PDF when needed.

## D5. Gates

| Gate | After | Question |
| --- | --- | --- |
| G0 | Group 0 | Operator reports the live page-mode result; if the log shows the local-OCR warning, fix the library paths first. |
| G1 | Group 1 GPU run | Operator approves the 1 to 1.5 hour GPU run. |
| G2 | Group 1 | Operator gives "3.7 confirmed" with a date. |
| G3 | Group 2 task 4.5 | Operator approves touching the live workers folder and restart. |
| G4 | Group 2 PR | Operator says merge. |
| G5 | Group 3 PR | Operator says merge. |
| G6 | Group 4 | Operator supplies or approves the new-document set. |
| G7 | Group 5 | Operator answers the default-flip question with the re-test evidence on the table. |
| G8 | Group 6 | Operator says whether to post the drafted #161 comment; later, whether to run the judge follow-up. |

## D6. What stays parked

Proposals `ordered-reader-and-ocr-lists`, `non-latin-script-routing` and `document-reading-routers` stay unstarted until the operator names one; all three modify `pdf-reader` specs together with `skip-blank-pages-before-worker`, so each apply must fork fresh from the merged `v3` and rebase its deltas. Experiment 44 (image fidelity pilot), Experiments 35 and 35a (RunPod CUDA) and the Ollama/MLX `model`-field parity runs stay parked.
