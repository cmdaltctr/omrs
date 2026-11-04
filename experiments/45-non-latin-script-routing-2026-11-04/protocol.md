# Experiment 45: Non-Latin script routing on stored OCR evidence

- **Folder**: `45-non-latin-script-routing-2026-11-04`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Operator**: the OMRS maintainer, with a coding agent
- **Related**: OpenSpec change `non-latin-script-routing` (design D2 and D3, tasks 4.1 and 4.2), Experiments 33, 37 and 39, ADR-071, ADR-105
- **Number**: 45. Numbers 40 (page versus document routing, NiftyPM AIE-101) and 43 (image-based rescue gate) are in `reserved.json`. Number 44 exists in this worktree. Numbers 41 and 42 exist. Number 43 also exists as a folder in two sibling worktrees. The CLI gave 45 as the next free number.
- **Status of this file**: written before any analysis exists. No output file exists when the orchestrator commits it.

## 1. Question

On the stored Experiment 33 and 37 evidence, does the `detect` mode of `ocr_non_latin_routing` escalate any non-Latin page that the 0.9 confidence cut keeps, without a false positive on a Latin page?

The decision: propose `detect` as the default in its own change and ADR, or keep the default `off`.

## 2. Hypothesis

- **H1 (primary)**: at least 1 of the 129 non-Latin pages has a stored local OCR result that the 0.9 cut keeps and that the shipped detector marks non-Latin. Then `detect` escalates a page that the cut does not.
- **H0 for H1**: no such page exists.
- **H2 (primary)**: the shipped detector gives a non-Latin verdict on 0 Latin pages, at both check points.
- **H0 for H2**: it gives a non-Latin verdict on 1 or more Latin pages.
- **Decision rule (fixed)**: propose `detect` as the default only if H1 and H2 both hold, which means count (e) is at least 1 and count (c) is 0. Otherwise keep `off`. The other three counts (a, b, d) do not enter the rule.

The design note in `design.md` records a quick script that found local confidence below 0.9 on all 129 pages. That result predicts (e) = 0 and the outcome `keep off`. This plan does not use that script. The run counts the pages again with the shipped detector.

## 3. What changes, what is measured, what stays fixed

| Changes (one thing) | Primary metric | Guardrail metric | Fixed |
| --- | --- | --- | --- |
| `off` (the 0.9 cut and the other shipped reasons) vs `detect` (the same plus the script check) | (e) non-Latin pages kept by the cut that `detect` escalates | (c) Latin pages with a non-Latin verdict | Detector version 1, letter floor 40, non-Latin share floor 0.5, cut 0.9, stored local OCR rows and text, pdf-inspector 1.17.0 |

Nothing is re-run. No OCR engine, no model and no network call is used. The experiment applies a string rule to text that already exists.

## 4. Data

| Item | Value |
| --- | --- |
| Source | Experiment 33 (40 open-licence PDFs, frozen labels, stored local OCR rows and text) and Experiment 37 (dots.mocr page text for 14 documents). Hashes are in `plan.json` `frozen` |
| Unit | Page |
| Size | 464 stored local OCR rows. 129 pages in the non-Latin class. 40 PDFs for the page-flag scan. 257 dots.mocr page files |
| Groups | Pages in a document. Four documents hold the non-Latin class: `io01`, `io02`, `io03`, `io07` |
| Labels | Page class from the Experiment 37 `E-script` page list, the same 129 pages as the Experiment 39 plan. The class does not come from the detector under test |
| Already seen | Experiment 39 re-scored the same 464 rows for the confidence cut. A quick script in `design.md` counted non-Latin local output once, outside any protocol |

Page classes:

- **non_latin**: the 129 pages. `io01` 48, `io02` 16, `io03` 5, `io07` 60.
- **unclassified**: pages of those four documents outside the 129. They count in (a) only.
- **latin**: every page of the other 36 documents.

Inputs, all read only:

| Input | Found in |
| --- | --- |
| `experiments/33-.../labels.json` | this worktree, sibling checkout `omrs-v3` |
| `experiments/33-.../output/local_ocr/pages.json` (464 rows) | this worktree, sibling checkout |
| `experiments/33-.../output/.local_ocr_text/<doc>/p<NNN>.md` (464 files) | `~/Development/DATA/omrs/experiments/`, sibling checkout |
| `experiments/33-.../corpus/natural/<doc>.pdf` (40 files) | `~/Development/DATA/omrs/experiments/`, sibling checkout |
| `experiments/37-.../output/ocr_state_dots-mocr.json` | this worktree, sibling checkout |
| `experiments/37-.../output/dots-mocr/<doc>/p<NNN>.md` (257 files) | `~/Development/DATA/omrs/experiments/`, sibling checkout |

The runner reads the first root that has the file and checks its SHA-256 against `plan.json`. The sibling checkout is `omrs-v3/experiments/`. Nothing is written under `~/Development/DATA/` or in another worktree.

## 5. Steps

Run every command from the repository root. Use `uv run --no-sync python`.

1. Check the preconditions (P1 to P5 in `plan.json`): frozen hashes, the 129-page class, the shipped detector module and constants, pdf-inspector 1.17.0, no network. Stop on any failure.
2. Flag scan: for each of the 40 PDFs, read the page flags and the text items of the flagged pages. Apply the shipped detector. This is check point 1 of design D3.
3. Stored rows: for each of the 464 stored local OCR rows, read the stored text and apply the shipped detector and the shipped escalation reasons with the 0.9 cut. This is check point 2.
4. Engine text: apply the shipped detector to the 257 dots.mocr page files. This gives (c3) and a cross-check of the page class.
5. Summarise (a) to (e), G1, G2 and the rule outcome into `output/summary.json`.
6. Write `analysis.py` and `report.md` after the summary exists.

The detector comes from `omrs.integrations.pdf.script_routing`, imported from this worktree. The runner does not hold a copy of the letter test or the constants. It writes the git blob SHA-256 of the module file into the run record. The function names are read from the module and written into `plan.json` `detector.entry_points` before the first run. That edit is not an amendment, because it happens before any run.

## 6. Analysis

- **Stats level**: basic. Counts only. No p-values.
- **Test for H1**: none. The count (e) is read directly. The report lists every counted page with its confidence and its non-Latin share.
- **Interval**: none. Each count comes from a fixed set of pages, not a sample.
- **Quantities**:

| Name | What it counts |
| --- | --- |
| (a) | Flagged pages with a non-Latin verdict before OCR, per document, split by page class. Also flagged pages with a Latin verdict and with no verdict |
| (b) | Per document, stored local results with a non-Latin, Latin or no verdict (under 40 letters), split by page class |
| (c) | False positives on Latin pages. c1 = before OCR, c2 = on stored local text. c = c1 + c2. Beside it, the number of Latin pages that had a verdict. (c3) is the detector on dots.mocr text of Latin pages and is not gated |
| (d) | Local seconds saved by `always`: the sum of `doc_seconds_share` over the 129 pages. Beside it, the same sum without timed-out documents, and the sum for Latin stored rows |
| (e) | Non-Latin pages kept by the 0.9 cut that `detect` escalates. A row is kept when it has no `error_class`, has text, has a confidence of 0.9 or more, and is not `hosted_recommended` |

- **Gates**:

| Gate | Pass when | Why it matters |
| --- | --- | --- |
| G1 | (e) is at least 1 | `detect` only adds value if it escalates a page that the cut keeps |
| G2 | (c) is 0 | A false positive sends a Latin page to the slow engine and so costs time on every such page |

- **Stop rule**: the run is complete when `output/summary.json` holds all five quantities and both gates. Stop before any score if a precondition fails.
- **What each outcome means**:
  - G1 pass and G2 pass: PASS. Propose `detect` as the default in its own change and ADR.
  - G1 fail, G2 pass: FAIL for the default. Keep `off`. `always` stays the opt-in for known collections.
  - G2 fail: FAIL for the default. Keep `off`. List the Latin pages with a non-Latin verdict. A better detector is a separate change with a version bump.
  - Unclear: not applicable. Both gates are counts against a fixed number.

Nothing is tuned. The letter floor (40), the share floor (0.5) and the cut (0.9) stay as shipped. A sweep is exploratory and cannot change the answer.

### Known gap

The corpus holds no born-digital non-Latin PDF with flagged pages. All four non-Latin PDFs are pure scans. Their flagged pages have empty Markdown, no fonts and a few Latin text items. So check point 1 (the text layer of a flagged page) has no positive case here. Count (a) cannot show that `detect` works on a flagged page that has a text layer. The experiment measures check point 2 and the false-positive rate of both points. A born-digital non-Latin PDF with flagged pages is needed to test check point 1. That is future work and does not block the rule above.

### Other limits

- Four documents, 129 pages, one local model (pp-ocrv6-small). A different local model changes the confidences and so (e).
- (d) uses the seconds from the Experiment 33 run on that machine. Treat it as an order of magnitude.
- Latin stored rows are the pages that Experiment 33 labelled `needs_ocr`. Latin pages never sent to the local tier have no stored text. They count in (c1) only.
- `design.md` names `io01` as Bengali and `io07` as Devanagari. The Experiment 39 plan names them the other way round. This plan does not use script names. The report gives the scripts found by Unicode block count.

## 7. Runtime

- **Purpose**: optimisation
- **Runtime under test**: no
- **Local models**: none run. The stored rows come from pp-ocrv6-small (oar-ocr v0.7.0, onnxruntime 1.28.0), recorded in the Experiment 33 identity block. No llama.cpp model is used, so `verify_llamacpp_runtime` does not apply.

| Role | Repository | File | SHA-256 | llama.cpp build | Server arguments |
| --- | --- | --- | --- | --- | --- |
| none | not applicable | not applicable | not applicable | not applicable | not applicable |

- **Hosted references**: none
- **Tolerance**: counts must match exactly on a rerun. The run is deterministic.
- **Live check**: none. Precondition P4 checks the pdf-inspector version instead.
