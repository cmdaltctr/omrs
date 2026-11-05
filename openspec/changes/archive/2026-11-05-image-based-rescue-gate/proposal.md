# Proposal: Experiment 43, does an image-based check route the bad PDFs to OCR?

## Why

GitHub issue #161: `rf06` and `rf07` (handwritten scans) keep a junk text layer, so they never reach OCR. On `rf06` page 29 the text layer reads "INT , L/ NUI a ¡NS SRA" and dots.mocr reads "Antonía Cruz González, Sevilla 17 de Agosto de 1911". Text-only checks failed in Experiments 38 and 42. Clef-Flash also reads page images, and nobody has tried that. We want one answer: does an image-based check route these PDFs to OCR without sending good PDFs there?

## What Changes

- Add Experiment 43. It uses only data we already have: the 40 documents of Experiment 33 with their frozen labels, page images and reference transcriptions. No download. No new labels. No second stage.
- For each page, give Clef-Flash Q8_0 (with its `mmproj` file, llama.cpp b11941, local) the page image and the rescued text layer. Ask one question: does this text match the page?
- Compare with two arms on the same pages: production today (never flags) and the Experiment 38 word check.
- Required control: the same question, pages and threshold rule go to hosted TypeSafe Jev with images. The report cannot give a verdict without this arm. The operator records the approval to send the page images in `plan.json` before the first image leaves the machine.
- Pass rule, fixed before the run: (1) `rf06` and `rf07` route to OCR; (2) no document labelled `usable` routes to OCR. The report also gives page-level numbers.
- No production code changes. A PASS opens a separate change and an ADR. A FAIL is recorded and #161 stays open.
- Experiment 44 stays as an optional 30-page smoke test before the full run.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `rescue-quality-evaluation`: adds rules for an image-based candidate (the question tests fidelity to the page, the model runs with its projector file, hosted image sending needs approval).

## Impact

- **Code:** experiment scripts only, under `experiments/43-image-rescue-gate-2026-11-02/`. Nothing under `src/`.
- **Dependencies:** none. `llama-server` b11941 and the Clef-Flash files (already downloaded, hash-checked) run outside the project environment.
- **Cloud:** the required Jev image control sends page images to TypeSafe, including `rf06` and `rf07` (named-person records). The key comes from the `TYPESAFE_API_KEY` environment variable.
- **Data:** page renders and scores go to gitignored `output/`. Experiment 33 files are read only.
- **Related:** issue #161, TDR-024, ADR-066, ADR-074, ADR-103, Experiments 33, 38, 42 and 44.

## Archive note (2026-11-05)

Superseded design. Page routing became the default (change `page-routing-default`, no 10% rule), and change `document-reading-routers` (ADR-110, PR #169) turned the image check into a per-page router. The Experiment 43 record (PR #170) stays as the evidence for the router's question, thresholds and cost figures. Issue #161 stays open until a confirmation run on new documents.
