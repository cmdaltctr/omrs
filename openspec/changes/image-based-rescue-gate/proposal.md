# Proposal: Experiment 43, test an image-based check on rescued PDF text

## Why

GitHub issue #161: a scanned handwritten PDF can keep a junk text layer and never reach OCR. `rf06` page 29 shows it. dots.mocr reads "Antonía Cruz González, Sevilla 17 de Agosto de 1911". The embedded text layer reads "INT , L/ NUI a ¡NS SRA". pdf-inspector flags the pages, finds no text, and the rescue chain (ADR-066) takes the junk layer from LiteParse. The flags then drop to zero, so OCR stays off and 61 junk chunks are indexed. The issue scores 6 x 8 = 48.

Experiments 38 and 42 tried to catch this with a text-only check and both failed. Experiment 42 found the main cause: Clef-flash was asked "is this readable writing?", but the label asks "does this text match what is on the page?". It flagged faithful copies of non-prose pages (chart numbers, grammar formulas, verse) and missed thin junk. Clef-Flash is a multimodal model, and the model card lists image input. Neither experiment gave it an image. The GGUF files for the image path exist (`ggml-org/Clef-Flash-GGUF` Q8_0 plus `mmproj-Clef-Flash-Q8_0.gguf`) and the llama.cpp build pinned by OMRS (b11941) is newer than the vision PR.

The repository rule is: no gate changes without an experiment on unseen documents. This change runs that experiment.

## What Changes

- Add Experiment 43 (`experiments/43-image-rescue-gate-2026-11-02/`), with `protocol.md` and `plan.json` committed before any page is scored. Number 40 stays reserved for the page versus document routing test.
- Ask a different question. The model receives the page image and the rescued page text, and answers one yes/no question: does this text match the text on the page? It is not asked whether the text is readable.
- Run Clef-Flash Q8_0 with its `mmproj` file on llama.cpp b11941, local only, bound to `127.0.0.1`, one request at a time. Check both file hashes and the build before scoring.
- Use two document stages. Stage 1 (development) uses the 40 Experiment 38 documents and the 68 Experiment 42 documents. These are now seen, so they fit the threshold and settle the page render settings. Stage 2 (confirmation) uses new documents, with the threshold frozen in `plan.json` before any of them is scored.
- Label handwritten and `ambiguous` pages with two references that must agree, because Experiment 42 excluded most handwriting as `ambiguous`: the Experiment 33 Gemini transcription rule, plus a second local transcription by dots.mocr (the engine from change `dots-mocr-llamacpp-backend`). Agreement gives a label. Disagreement gives `ambiguous`. Other pages keep the Experiment 33 label. The operator checks a stratified sample of pages by eye this time (Experiment 42 waived it).
- Score these arms on the same pages: production today (control, never flags), the Experiment 38 word check (cheap comparator), the Experiment 42 text-only Clef-Flash scores (reference row, not rerun), and the image-plus-text Clef-Flash check (treatment).
- Add hosted TypeSafe Jev (`jev-1.14.0`) with image input as a control arm. It gets the same page render, the same text head and the same wording as the treatment. It runs only on documents the operator approves by name, records the returned model id for every page, and stops if the id changes. It is reported in its own table and does not change the verdict.
- Keep gates G1 to G3 and the 0.10 margin over the word check from Experiment 42. Report every result at page level and at document level, so Experiment 40 can choose the routing unit.
- No production code changes. A PASS opens a separate change (a rescue check inside the reader chain, behind a setting that defaults to off) and an ADR. A FAIL is recorded and the work stops.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `rescue-quality-evaluation`: adds rules for an image-based candidate (the question must test fidelity to the page, a model that reads images runs with its projector file, development and confirmation stages, handwritten and ambiguous pages need two agreeing references, the operator checks a sample of labels). The existing rules on junk labels, margin, false-positive cost, local-first models and unchanged production stay.

## Impact

- **Code:** experiment scripts only, under `experiments/43-image-rescue-gate-2026-11-02/`. No change under `src/`, `pyproject.toml` or `uv.lock`.
- **Dependencies:** none added to OMRS. `llama-server` b11941 and the Clef-Flash files run as external processes (ADR-074 decision 7, ADR-103). `wordfreq` stays an experiment-only tool.
- **Downloads:** Clef-Flash Q8_0 (9.66 GB) and its `mmproj` file (0.62 GB) are already in `~/Development/DATA/omrs/ocr-models/clef-flash/` (download in progress at the time of writing; pinned to revision `a5a18a6e`). New open-licence PDFs for Stage 2 need operator approval before download.
- **Cloud:** hosted Jev images only, and only for documents the operator approves by name in a dated `plan.json` amendment. The default is open-licence documents. `rf06` and `rf07` hold named-person records and stay excluded unless the operator names them. The key is read from the `TYPESAFE_API_KEY` environment variable and is never written to a file. Hosted Clef-Flash stays out of scope. Input tokens cost \$0.042 per million, with no separate image charge.
- **Data:** page renders and scores go to gitignored `output/`. Frozen Experiment 33, 38 and 42 files are read only.
- **Related records:** issue #161, TDR-024, ADR-066, ADR-069, ADR-071, ADR-074, ADR-103, ADR-109, Experiment 38 and 42 reports, `openspec/specs/rescue-quality-evaluation`.
