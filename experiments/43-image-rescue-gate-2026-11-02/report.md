# Experiment 43: Image-based check on rescued PDF text

- **Folder**: `43-image-rescue-gate-2026-11-02`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Date run**: 2026-11-02
- **Operator**: the project operator, with a Claude Code agent
- **Plan**: [protocol.md](protocol.md) · [plan.json](plan.json)
- **Source of every number**: `output/summary.json`, `output/scores_clef_image.json`, `output/scores_jev_image.json`, `output/run-records.jsonl`

## Answer

- **Question**: Does a check that shows a model the page image and the rescued text, and asks "does the text match the page?", send `rf06` and `rf07` to OCR without sending any usable document to OCR?
- **Answer**: No. Both arms send `rf06` and `rf07` to OCR, and both also send usable documents to OCR under the 10% rule.
- **Decision**: Do not change any default. Issue #161 stays open. The image check catches the bad PDFs, so the idea stays alive, but the 10% routing rule makes it unusable as it stands.
- **How sure**: Low. Only two documents (`rf06`, `rf07`) have a junk text layer, and the threshold was fitted on the same documents it was tested on.
- **Next step**: Look at the flagged `rf05` pages by eye, then decide between a stricter routing rule tested on new documents and dropping the image route.

## What we tested

We gave each page of the 40 Experiment 33 documents (1,123 pages, 799 with a text layer) to a model as an image together with the first 2,000 characters of its rescued text, and asked one question: "Does the text match the text written or printed on the page image?". Two models answered: local Clef-Flash Q8_0 with its projector file on llama.cpp b11941, and hosted TypeSafe `jev-1.14.0`. The result decides whether an image-based check can fix issue #161 (`rf06` and `rf07` never reach OCR). The data are the frozen Experiment 33 labels: 89 junk pages and 565 healthy pages among the pages with rescued text.

## Results

The table shows what each arm does at page level and at document level. Part 1 of the pass rule asks that `rf06` and `rf07` route to OCR. Part 2 asks that no usable document is newly routed. A document routes at 10% flagged pages.

| Arm | Junk caught of 89 (`rf06`+`rf07` of 54) | Healthy flagged of 565 | `rf06` / `rf07` routed | Usable documents newly routed (OCR pages) | Pass rule |
| --- | --- | --- | --- | --- | :---: |
| Control (today) | 0 (0) | 0 | no / no | none | FAIL |
| Word check (Experiment 38 scores) | 37 (32) | 11 | yes / yes | `rf05` (25) | FAIL |
| Local Clef-Flash image, threshold 0.1722 | 62 (54) | 15 | yes / yes | `rf05` (25) | FAIL |
| Hosted Jev image, threshold 0.21 | 61 (53) | 15 | yes / yes | `rf08`, `tl04`, `tl06` (43) | FAIL |

The word check row uses the classified pages only, from the committed Experiment 38 scores, so it is a reference row and not a rerun. The one-page rule (a document routes at one flagged page) also fails every arm. It routes `rf05` and `rf08` for the local arm (53 pages of OCR) and a longer list for Jev (68 pages).

- **Local arm.** It catches all 54 junk pages of `rf06` and `rf07` and 62 of 89 junk pages in total, against 37 for the word check. On `rf05` it flags 10 of 25 pages (5 healthy, 4 grey, 1 excluded). Even the 5 healthy pages alone pass the 10% line.
- **Hosted arm.** It is about equal at catching junk (61 of 89, 53 of 54 in `rf06` and `rf07`). It routes more usable documents than the local arm, and short documents decide it: one or two false flags reach 10%.

### Hypotheses

| Hypothesis | Null | Result | Plain meaning |
| --- | --- | --- | --- |
| H1 (primary): the image check passes both parts of the pass rule | The check fails part 1 or part 2 | Not supported. Part 1 passes, part 2 fails for both image arms. | The check finds the bad PDFs and also flags good documents. |

### Amendments and deviations

- **A1.** The local threshold (0.1722) was fixed on the 561 fit-phase scores before any junk page was scored by this arm. The hosted threshold (0.21) was fixed the same way.
- **A2.** TypeSafe returned short-lived HTTP 503 ("Image processing is unavailable") and 529 ("overloaded") answers on about 3% of requests. The stop rule now counts only pages still without a score after retries, and a resume retries failed pages. No page was left without a score. The question, the scores, the threshold rule and the pass rule did not change.
- **Images on b11941.** They must go as data URLs. The smoke test passed (right text 0.903, wrong text 0.069). Without the projector the server answers HTTP 501 and the runner stops.
- **Score files** are committed, as in Experiments 38 and 42. The design said they would be gitignored. Page images and page text stay gitignored.
- **Approval.** The operator approved sending the page images of all 40 documents, including `rf06` and `rf07`, to TypeSafe on 2026-11-02, before any image was sent.

### Exploratory findings

- **Exploratory.** `rf06` page 29: pypdf gives the exact junk quoted in issue #161. LiteParse gives the same junk tokens in a different order. Both match Experiment 38 byte for byte.
- **Exploratory.** Hosted scores for the same page vary by up to 0.03 between calls, more than the planned 0.02 tolerance.

## Why it happened

1. **The image check separates faithful text from junk well.** It catches 54 of 54 junk pages in `rf06` and `rf07` (local arm), where the word check catches 32. This is the gain over the text-only checks of Experiments 38 and 42.
2. **The 10% rule punishes short documents.** In `rf05` (25 pages) 10 flagged pages are 40%. In a document of 4 to 12 pages one or two false flags are enough to cross 10%. This is the Experiment 42 lesson again.
3. **The cause of the `rf05` flags is unexplained.** They may be real mismatches (the document is hard), a label problem, or an image render problem. We did not look at the pages.

## Limits

1. The threshold was fitted on the same 40 documents it was tested on, so the result is, if anything, optimistic.
2. Only two documents (`rf06`, `rf07`) have a junk text layer, and only 13 documents reach the check, so one document changes the verdict.
3. Hosted scores are noisy (up to 0.03 between calls), and the hosted model id was the same on every page (`jev-1.14.0`) but TypeSafe states that image input is not yet ready for production.
4. The local arm was run once. The result does not show how it behaves on new documents.

## Speed and cost

| | Local Clef-Flash | Hosted Jev |
| --- | --- | --- |
| Pages scored | 799 | 799 |
| Seconds per page | 3.64 mean | 1.38 mean (median 0.81, maximum 7.8) |
| Total request time | 48.5 minutes | 18.4 minutes (about 30 minutes of wall clock with retries) |
| Input tokens | 1.75 million | 4.08 million |
| Cost | none (9.66 GB model plus 0.62 GB projector, free memory stayed between 65% and 83%) | about USD 0.17 |
| Failed requests | 0 | 21 error events, 0 pages left without a score |

## What it means for you

The image idea works for the handwritten PDFs, and the hosted model gives no gain over the local one. The routing rule, not the model, is what fails. Nothing changes in production, and issue #161 stays open.

## Artefacts

| File | Contents |
| --- | --- |
| `output/summary.json` | Aggregated metrics, routing tables and the pass rule per arm |
| `output/scores_clef_image.json` | Raw per-page local scores |
| `output/scores_jev_image.json` | Raw per-page hosted scores, with the returned model id |
| `output/runtime_check_clef_image.json` | Build, hash, projector and smoke-test checks |
| `output/run-records.jsonl` | One line per run start: time, git commit, plan SHA-256 |
| `analysis.py`, `score_pages.py`, `prepare_inputs.py` | Analysis, scoring and input preparation |
