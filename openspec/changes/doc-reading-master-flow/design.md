# Design: master execution order for the document-reading and dots-mocr flow

## Context

See proposal.md. Facts below were checked on 2026-11-02 against the repos, code and packages; the source of each is named. The operator's rules live in the repo `AGENTS.md` and the handoff `~/Development/DATA/omrs/handoffs/2026-11-02-doc-reading-and-dots-mocr-handoff.md` (facts, results, commit IDs).

Worktrees (siblings under `~/Development/PROJECTS/om-systems/omrs/`, all clean, nothing pushed, 2026-11-02):

| Worktree | Branch | State |
| --- | --- | --- |
| `omrs-v3` | `v3` | Proposals A, B, C, `skip-blank-pages-before-worker`, this master flow. |
| `omrs-feat-dots-mocr-llamacpp-backend` | `feat/dots-mocr-llamacpp-backend` | Last commit `d552a92d`. Tasks 2b.1 to 2b.7, 3.1 to 3.3, 3.5, 3.6 ticked; 3.4 and 3.7 open. Tripwire pin `_BASE_EXECUTED = 9859`. |
| `omrs-feat-image-based-rescue-gate` | `feat/image-based-rescue-gate` | Experiment 43, verdict FAIL under the 10% document rule. Last commit `4c7a8bf4`. |

## Goals / Non-Goals

**Goals:**

- One recorded order an agent can follow group by group, stopping at every gate.
- The operator's confirmed order (2026-11-02), six steps, small changes only.

**Non-Goals:**

- No new code, settings or concepts in this change.
- No re-planning of the changes it orders; each keeps its own tasks and design.
- No decision made here that belongs to the operator.

## D1. Blank pages first, verified on the PyTorch engine

`skip-blank-pages-before-worker` runs first because it is the smallest change and the operator ordered it so. Its task 4.1 was written against `dots-mocr-llamacpp`, which reaches `v3` only when group 6 merges; `v3` today holds `dots-mocr` (PyTorch) and `paddleocr-vl` only (checked). Task 4.1 therefore verifies on the PyTorch engine with a same-engine baseline: record the 10-page extract's page texts and engine calls before the change, then confirm blank pages make zero engine calls and the other pages stay identical. This keeps the measurement honest without waiting for group 6.

## D2. The default flip decision (operator, 2026-11-02)

The 2026-11-02 handoff recorded the rule "re-test on new documents before any default change". On 2026-11-02, in session, the operator confirmed a different order: remove the `document` unit and make `page` the default in group 2, before any new-document re-test, on the strength of the `rf06` 10-page page-mode run (page 29 found at 0.99, worker pages Dice 1.0 against parity references, one local page, four blank sheets explained). The pre-registered re-test stops being a gate. If the operator later wants a light check on new documents, he asks for it; the flow does not plan it.

## D3. The local-OCR library trap

`pdf_inspector` 1.17.0 requires compatible PDFium and ONNX Runtime shared libraries for routed OCR; set `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` when they are not on the platform library search path (package METADATA). Without them the local OCR tier raises, `ocr_routing.py` catches it, and flagged pages keep their native junk text with one warning ("Local OCR tier unavailable"). Every page-mode run, scratch or live, must set both variables and then grep the log for that warning. Copies in a project venv: `.venv/lib/python3.14/site-packages/liteparse/libpdfium.dylib` and `.venv/lib/python3.14/site-packages/onnxruntime/capi/libonnxruntime.1.28.0.dylib`.

## D4. The 10-page `rf06` extract

The scratch extract from the 2026-11-02 page-mode test may not exist any more. Its original `rf06` pages: 20, 29, 33, 40, 46, 50, 60, 70, 80, 86. Of these, 20, 40, 70 and 80 are blank sheets; 29, 33, 46, 50 and 86 went to the worker engine; 60 resolved locally (confidence 0.91). Recreate the extract from the `rf06` PDF when needed.

## D5. Gates

| Gate | After | Question |
| --- | --- | --- |
| G1 | Group 1 PR | Operator says merge the blank-pages PR. |
| G2 | Group 2 PR | Operator says merge the `page-routing-default` PR. |
| G3 | Group 3 GPU run | Operator approves the 1 to 1.5 hour GPU run. |
| G4 | Group 4 A PR | Operator says merge. |
| G5 | Group 4 B PR | Operator says merge. |
| G6 | Group 4 C PR | Operator says merge. |
| G7 | After G6 | Operator says whether to run the judge confirmation experiment on new documents. |
| G8 | Group 5 PR | Operator says merge the Experiment 43 branch PR. |
| G9 | Group 5 | Operator says whether to post the drafted #161 comment. |
| G10 | Group 6 start | Operator gives "3.7 confirmed" with a date. |
| G11 | Group 6 task 4.5 | Operator approves touching the live workers folder and restart. |
| G12 | Group 6 PR | Operator says merge. |

## D6. What stays parked

`paddleocr-vl-llamacpp-backend` waits for group 6 to merge (its own tasks say so). Experiment 44 (image fidelity pilot), Experiments 35 and 35a (RunPod CUDA) and the Ollama/MLX `model`-field parity runs stay parked. The `cloudflare` and `ollama` decision-model kinds inside `document-reading-routers` are built to fake-server tests only; live checks are that change's own follow-up, outside this flow.
