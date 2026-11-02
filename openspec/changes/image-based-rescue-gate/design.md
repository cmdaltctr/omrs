# Design

## Context

- **Fault.** `pdf_inspector` flags the pages. LiteParse (ADR-066) rescues text for them. TDR-024 then sets the flagged count to zero, so OCR stays off. Nothing checks the rescued text against the page. See proposal.md.
- **Data we have.** `experiments/33-ocr-routing-natural-positive-2026-09-17/` holds `labels.json` (40 documents, frozen), the PDFs, and the page images and reference transcriptions under `~/Development/DATA/omrs/experiments/33-*/`.
- **Model.** `ggml-org/Clef-Flash-GGUF` revision `a5a18a6e`: `Clef-Flash-Q8_0.gguf` (SHA-256 `25f801e2…`) and `mmproj-Clef-Flash-Q8_0.gguf` (SHA-256 `9dd8bc27…`), in `~/Development/DATA/omrs/ocr-models/clef-flash/`. Both hashes already match Hugging Face. Rule: decision models run at 8-bit or higher (ADR-074, ADR-103).

## Goals / Non-Goals

**Goals:** find out if an image-based check routes `rf06` and `rf07` to OCR and keeps good documents out.

**Non-Goals:** changing any default, choosing page or document routing (Experiment 40), new documents, new labels, other models.

## Decisions

### D1. One question, one stage

The model gets the page image and the first 2,000 characters of the rescued page text. Question: "Does the text match the text written or printed on the page image?" Request type `noul`, options `["no", "yes"]`, one probability out. The question asks about fidelity to the page, not about readability, because that mismatch caused the Experiment 42 failure.

### D2. Threshold

One threshold on `P(yes)`. Fit it on the healthy pages of the 38 documents that are not `rf06` or `rf07`, using the equal-cost rule of Experiment 38, then write it to `plan.json` before the junk pages are scored. This is an honest limit: the documents are not new. The result shows whether the idea works. It does not prove it generalises. The report says so.

### D3. Arms

| Arm | Flag rule |
| --- | --- |
| Production today | never flags |
| Word check (Experiment 38 code, unchanged) | below its committed threshold |
| Clef-Flash Q8_0 with image (treatment) | `P(yes)` below the D2 threshold |
| Hosted Jev with image (required control) | same question, pages and threshold rule |

### D4. What the report shows

Per arm: junk pages caught, healthy pages flagged, which documents would route at the current 10% rule, and the same at one flagged page. For each wrongly routed document, the OCR cost in pages. The pass rule is in the proposal.

### D5. Runtime

External `llama-server` b11941, `127.0.0.1`, one request at a time. Before scoring, check the build and both hashes, and send one right-text and one wrong-text request on one page. The two answers must differ in the expected direction. This proves the projector is loaded.

### D6. Page image size

PNG, 150 DPI, long side at most 1,568 px. One image serves the local and the hosted arm (the hosted limit is 1,568 px).

### D7. Required hosted Jev control

Model `jev-1.14.0`, header `TypeSafe-Danger-Zone-Images: true`, image as base64 PNG in the request `assets` map, key from the environment, never printed. Stop if the returned model id changes (pattern from `experiments/38-rescue-quality-signal-2026-09-30/jev_hosted.py`). The arm is required: the verdict compares the local arm with it. The operator records the approval in `plan.json` before the first image is sent, naming the documents. This sends page images to a third party, and the comparison needs `rf06` and `rf07`, which hold named-person records. If the operator refuses, the experiment does not run.

## Risks / Trade-offs

- **Image path fails on b11941.** The smoke test (D5) stops the run before scoring.
- **Speed.** Images add tokens. 1,123 pages may take an hour or more. Run in the background, with checkpoints.
- **Fit and test on the same documents.** See D2. A PASS leads to a follow-up change that confirms on new documents before any default moves.
- **Few junk documents.** Only `rf06` and `rf07`. The report gives counts, not only rates.

## Migration Plan

None. Experiment files only.
