# Experiment 45: Non-Latin script routing on stored OCR evidence

- **Folder**: `45-non-latin-script-routing-2026-11-04`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Date run**: 2026-11-04
- **Operator**: build agent under the OMRS orchestrator, change `non-latin-script-routing`
- **Plan**: [protocol.md](protocol.md) · [plan.json](plan.json)
- **Source of every number**: `output/summary.json`, `output/verdicts.json` and `output/report_tables.md`

## Answer

- **Question**: On stored Experiment 33 and 37 evidence, does `detect` escalate any non-Latin page that the 0.9 cut keeps, without a false positive on a Latin page?
- **Answer**: No. (e) is 0, because the 0.9 cut already escalates all 129 non-Latin pages. (c) is 0.
- **Decision**: Keep the default `off`. `always` stays an opt-in for collections known to be non-Latin scans.
- **How sure**: High for this corpus. The highest stored confidence on a non-Latin page is 0.805, which is 0.095 below the cut. Low for other corpora: 4 documents, 3 scripts, one local model, and no born-digital non-Latin PDF.
- **Next step**: Test check point 1 on a born-digital non-Latin PDF with flagged pages when one is available.

## What we tested

The shipped detector (`omrs.integrations.pdf.script_routing`, version 1, 40-letter floor, 0.5 share) at its two check points, against the current 0.9 confidence cut. The result decides whether `detect` becomes the default. The data is 701 flagged pages over 40 PDFs (Experiment 33), 464 stored local OCR rows (Experiment 33) and the dots.mocr text of the 129 non-Latin pages (Experiment 37).

## Results

G1 fails and G2 passes, so the fixed rule keeps the default `off`.

| Gate | Pass when | Value | Result |
| --- | --- | ---: | :---: |
| G1 | (e) at least 1 | 0 | fail |
| G2 | (c) equal to 0 | 0 | pass |

| Measure | Value |
| --- | --- |
| (a) Flagged pages with a non-Latin verdict before OCR | 0 of 701 |
| (b) Stored local rows of the 129 non-Latin pages with a non-Latin verdict | 61 (`io01` 9, `io02` 0, `io03` 0, `io07` 52) |
| (c) Non-Latin verdicts on Latin pages | 0 (c1 0 of 565 flagged, none with a verdict; c2 0 of 309 with a verdict; c3 0 of 119, not gated) |
| (d) Local seconds `always` saves on the 129 pages | 89.937 s (`io01` 20.064, `io02` 22.528, `io03` 15.485, `io07` 31.860) |
| (e) Non-Latin pages the 0.9 cut keeps and `detect` escalates | 0 (e0, kept by the cut whatever the verdict: 0) |

Per-document tables are in `output/report_tables.md`.

- Before OCR, `io01` gives a Latin verdict on all 48 non-Latin pages, because its stamp text holds more than 40 Latin letters. The other three documents have fewer than 40 letters per page, so they give no verdict.
- All 129 non-Latin pages have local confidence from 0.454 to 0.805. Every one escalates on `low_confidence`, and 5 also on `hosted_recommended`.

### Hypotheses

| Hypothesis | Null | Result | Plain meaning |
| --- | --- | --- | --- |
| H1 (primary) | `detect` escalates no non-Latin page the cut keeps | Not supported: (e) = 0 | The cut already sends every measured non-Latin page to the engine. |
| H2 (guardrail) | The detector marks Latin pages non-Latin | Supported as zero: (c) = 0 | No false positive. At check point 1 the zero rests on no verdicts at all. |

### Amendments and deviations

1. `plan.json` `detector.entry_points` was filled from the shipped module before the first run, as the plan allows.
2. The plan said to stop and ask if the shipped module returns only a verdict. `is_non_latin` returns only a verdict. The run went on and recorded verdicts only, with no recomputed share. The orchestrator accepted this after the run: both gates use verdicts only, so no result changes.
3. `output/run-records.jsonl` has 4 lines. Lines 1 and 2 are crashed starts from a key-name bug in the runner, before any page was scored. Line 3 is the first complete run. Line 4 is a rerun after the runner was changed to write `~` and relative paths. Its rows match line 3 exactly.
4. Check point 1 used the shipped `page_evidence`, then `pdf_inspector.extract_text_with_positions`, then `is_non_latin`. It matches the shipped `_text_layer_verdicts` on all 40 PDFs.
5. The shipped `local_ocr` needs a live OCR run, so (e) applies the plan's definition to the stored rows. Like the plan, it leaves out the blank-page and maths-page steps.

### Exploratory findings

- Exploratory: the local model reads these scripts as other scripts. `io01` local text is mostly Latin and CJK letters (1,421 and 764). Check point 2 alone would catch 61 of the 129 pages.
- Exploratory: the engine text gives `io01` Devanagari, `io02` and `io03` Arabic, and `io07` Bengali. `design.md` and the Experiment 39 plan disagree on `io01` and `io07`; the engine text settles it. These names enter no gate.

## Why it happened

1. The local model is unsure on these scripts, so its confidence falls below 0.9 on every page. The cut escalates them before the detector can add anything.
2. Scanned pages and stamps hold fewer than 40 letters, or only Latin stamp text, so check point 1 has nothing to read.

## Limits

1. The corpus has 4 non-Latin documents in 3 scripts and no born-digital non-Latin PDF with flagged pages. Check point 1 therefore has no positive case.
2. Experiment 33 stored local text only for pages labelled `needs_ocr`. Latin pages never sent to the local tier count in (c1) only.
3. The result holds for PP-OCRv6 Small and the 0.9 cut. A more confident local model or a lower cut can change (e).

## What it means for you

The default stays `off`. Use `always` on a collection you know is non-Latin; on these 129 pages it saves about 90 s of local OCR. `detect` adds nothing on this corpus.

## Artefacts

| File | Contents |
| --- | --- |
| `output/summary.json` | Aggregated counts and gates |
| `output/verdicts.json` | Per-page verdicts at both check points |
| `output/report_tables.md` | Per-document tables for (a) to (e) |
| `output/script_letters_engine_text.json` | Letters per script in the engine text |
| `output/run-records.jsonl` | One line per run start: time, git commit, plan SHA-256 |
| `run_script_routing.py` | The run: verdicts from the shipped detector |
| `summarise.py` | Counts and gates from the run output |
| `analysis.py` | Tables from the JSON |
