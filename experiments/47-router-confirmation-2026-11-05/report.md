# Experiment 47: Document router confirmation on new documents

- **Folder**: `47-router-confirmation-2026-11-05`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Date run**: 2026-11-05
- **Operator**: coding agent, with operator decisions in `plan.json` `decision_register`
- **Plan**: [protocol.md](protocol.md) · [plan.json](plan.json)
- **Source of every number**: `output/summary.json`, `output/labels.json`, `output/set_check.json`, `output/inputs.json`, `output/scores_clef_router.json`, `output/scores_jev_router.json` and `output/reference_state.json`

## Answer

- **Question**: On documents it has not seen, does the shipped document router send at least 70% of junk-text pages to OCR, and wrongly reject no more than 5% of healthy pages?
- **Answer**: No. The local router (Clef-Flash, threshold 0.172) caught 28 of 54 junk pages (0.52). It wrongly rejected 2 of 54 healthy pages (0.037).
- **Decision**: Keep the document router off by default. Do not use the Experiment 43 recall as the expected recall on new documents.
- **How sure**: Medium. There are 54 junk pages in 11 documents. The recall is far below the gate, but most junk pages come from one kind of document: old prints with a garbled text layer.
- **Next step**: Decide whether to refit the threshold on old printed documents in a new experiment, or to stop the router work here.

## What we tested

The router is a page rule. It shows a decision model each page that the page scan did not already send to OCR, with the page text and the page image. The model gives the probability (P(yes)) that the text matches the page. A page under the threshold goes to OCR. The baseline is the shipped default: no router. The result informs whether the router can be on by default (gate G7 of the master flow). The data is 186 pages from 32 public-domain or CC BY PDFs (18 JUNK, 14 GOOD). Of these, 111 pages reach the router.

## Results

The table shows the treatment arm, which decides the verdict, and the hosted reference arm, which does not.

| Arm | Junk pages | Junk caught (recall) | Healthy pages | Healthy rejected (rate) | Documents with junk missed | Seconds per page |
| --- | ---: | --- | ---: | --- | ---: | ---: |
| Control (no router) | 54 | 0 (0.00) | 54 | 0 (0.00) | 11 | 0 |
| clef_router (local, threshold 0.172) | 54 | 28 (0.52) | 54 | 2 (0.037) | 2 (G7, G8) | 2.65 |
| jev_router (hosted, threshold 0.21) | 54 | 18 (0.33) | 54 | 4 (0.074) | 3 (G7, G8, J6) | 0.86 |

| Gate | Role | Rule | Observed (clef_router) | Result |
| --- | --- | --- | --- | :---: |
| G1 | primary | junk recall at least 0.70 | 0.52 (28 of 54) | Fail |
| G2 | primary | healthy false-reject rate at most 0.05 | 0.037 (2 of 54) | Pass |
| G3 | secondary | documents with junk missed = 0 | 2 (G7, G8) | Fail |
| G4 | secondary | seconds per page at most 5.0 | 2.65 | Pass |

The verdict is FAIL, because primary gate G1 fails (`output/summary.json`). No page scored between the shipped threshold 0.172 and the exact Experiment 43 value 0.1722.

### Hypotheses

| Hypothesis | Null | Result | Plain meaning |
| --- | --- | --- | --- |
| H1 (primary): the router catches at least 70% of unflagged junk pages and rejects at most 5% of healthy pages | Recall under 0.70 or false-reject rate over 0.05 | Not supported. Recall 0.52, false-reject rate 0.037 | The router is cheap on healthy pages, but it misses about half of the junk pages it exists for. |

### Amendments and deviations

1. **A1** (before any score): the coding agent did the label review, not the operator.
2. **A2** (before any label or score): the page scan sent every page of 9 of the 10 approved JUNK documents to OCR. The set check could not pass (7 unflagged junk pages in 1 document). The operator chose to add documents. We added 8 JUNK prints (J11 to J18) and 5 GOOD articles (G10 to G14). All 19 approved documents stayed, and their scan rows were identical to the committed rows.
3. **Reference failures.** 7 of 186 local reference pages timed out after 300 s (J4 pages 9 to 12, J8 pages 1 and 4, J9 page 11). All 7 are manuscript pages that the scan already sends to OCR. The label rule marks them "excluded", so they change no population (`output/reference_state.json`).
4. **Run records.** 5 of the 6 run records show `git_dirty: true`. The cause is untracked output files (`runtime_check_*.json`, `scores_*.json`). `plan.json` and the labels were committed and clean before each score.

### Labels and set check

The labels compare the page text the router reads with a local dots-mocr transcription of the page (Experiment 33 token rule). A page is junk below 0.50 recall and healthy at 0.80 or more. The labels gave 58 junk, 56 healthy, 3 grey and 69 excluded pages (`output/labels.json`). The excluded pages are the flagged pages, which have no text.

The set check passed: 58 unflagged junk pages in 12 documents and 56 unflagged healthy pages in 10 documents. The minimums are 20 in 5 and 40 in 8 (`output/set_check.json`). Earlier page rules claimed 4 junk pages (G3 page 5, G7 pages 4 to 6) and 2 healthy pages (G3 pages 3 and 4). Those pages go to OCR without the router, so 54 junk and 54 healthy pages remain.

The agent review covered all 58 junk pages, 3 grey pages and 15 seeded healthy pages. It agreed with all 76 classes (`output/label_review.json`). Three GOOD documents have junk pages, and the review agreed with each:

- **G7** (born-digital Arabic): the scan text holds most words in reversed letter order. All 5 pages are junk.
- **G3 page 5** and **G8 page 11**: born-digital table pages. The scan text lost most of the table.

### What the scan does alone

The page scan (pdf-inspector) decides before the router.

- It sent all 55 pages of the 9 manuscript JUNK documents to OCR (`output/inputs.json`). It finds no text on these image pages, so it sends them to OCR whatever their text layer holds.
- It sent no page of the 9 garbled old prints (J6, J11 to J18) to OCR. On these pages it reads the garbled text layer and treats it as good text.
- It sent all 14 pages of 3 GOOD documents to OCR: G4 and G5 (clean scans, no text found) and G9 (Japanese born-digital, flagged as `suspected_garbled_text`). This costs OCR time on pages with a usable text layer.

So the work left for the router is old print with a garbled text layer, plus born-digital pages with broken extraction (G7, G8).

### Local and hosted arms compared

The two arms scored the same 111 pages and agreed on 93 (0.84): both rejected 17, neither rejected 76. Only Clef-Flash rejected 13 pages, all junk. Only Jev rejected 5 pages: 2 healthy pages of G1 (USGS fact sheet, P(yes) 0.16 and 0.13) and 3 junk pages (`output/summary.json`, `comparison`).

- Jev scores sit in a narrow band. Healthy pages mostly score 0.3 to 0.7, junk pages 0.08 to 0.38. 25 of its 36 missed junk pages are less than 0.1 above its threshold 0.21.
- Clef-Flash separates the groups better. Healthy born-digital pages score about 0.85 to 0.94, printed junk pages about 0.04 to 0.4. 10 of its 26 missed junk pages are less than 0.1 above 0.172.
- Both arms rejected G6 pages 10 and 12 (a clean 1897 Spanish scan). These are the 2 Clef-Flash false rejects.

### Exploratory findings

These are not part of the plan and cannot change the answer.

1. Most missed junk pages are old prints with P(yes) just above the threshold, for example J6 (0.13 to 0.28) and J15 (0.16 to 0.37). The threshold came from Experiment 43, whose junk was a different mix.
2. Three missed pages score high: G7 pages 2 and 3 (0.72 and 0.76) and G8 page 11 (0.87). There the text is a reversed or partial copy of a clean page. The model seems to accept text that uses the right words, even when their order or coverage is wrong.

## Why it happened

1. **Different junk.** Here, unflagged junk is mainly old print where few words are right (label recall 0.0 to 0.42). The model scores these pages near the threshold, so a fixed threshold catches about half of them.
2. **Broken but plausible text passes.** Reversed Arabic, and table pages that lost their cells, still contain real words from the page. The model scores them as a match.
3. **The scan removes the easy cases.** Image-only manuscripts never reach the router, so the router sees only the harder garbled prints.

## Limits

1. The junk population is 54 pages in 11 documents. The 8 added prints come from one source (Google Books via archive.org), so the result leans on that kind of document.
2. Amendment A2 chose the added documents with the scan, before any label or score. They were chosen to reach the router, not at random.
3. The labels use a local OCR reference, not a human transcription. One reviewer (the coding agent) checked the review pages.
4. Each arm used one threshold, frozen from Experiment 43. This does not show what a refitted threshold would do.

## What it means for you

The router stays off by default. It is cheap on healthy pages (2 of 54 rejected), but it misses about half of the garbled old prints it is meant to catch. A refit on old prints needs a new experiment with its own held-out documents.

## Artefacts

| File | Contents |
| --- | --- |
| `output/summary.json` | Metrics, gates, verdict and arm comparison |
| `output/scores_clef_router.json` | Per-page P(yes) and rejection, local arm |
| `output/scores_jev_router.json` | Per-page P(yes) and rejection, hosted arm |
| `output/labels.json` | Per-page labels and recall |
| `output/label_review.json` | Agent review verdicts |
| `output/set_check.json` | Set-check counts |
| `output/inputs.json` | Scan result and hashes per page |
| `output/reference_state.json` | Local reference status and time per page |
| `output/runtime_check_*.json` | Runtime checks R1 to R6 |
| `output/run-records.jsonl` | One line per run start: time, git commit, plan SHA-256 |
| `analysis.py` | Builds `summary.json` from the JSON files |

**Time and cost.** The local references took 4.1 hours of OCR time (`output/reference_state.json`). The local arm scored 111 pages in about 6 minutes. The hosted arm took about 2.5 minutes, at an estimated USD 0.02 (111 pages at USD 0.00022 per page, under the USD 1.00 cap).
