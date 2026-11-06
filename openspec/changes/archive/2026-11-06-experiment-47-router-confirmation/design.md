# Design

## Context

- **What ships.** PR #169 added document routers (ADR-110). A router is the page rule `document_router` at order 40 (`integrations/pdf/page_rules/document_router.py`). It judges each page with text that the scan did not flag and that no earlier rule claimed. The judge is `compose_decision.PageJudge`. It sends the question, the first `max_chars` characters of the pdf-inspector page Markdown and the page image (`integrations/pdf/page_images.render_page`, 150 DPI, long side at most 1,568 px). A page whose P(yes) is below the threshold goes to OCR on its own.
- **Template.** `web/src/settings/routerWords.ts`: the Experiment 43 question, images on, 2,000 characters, threshold 0.172, note "Fitted on Experiment 33 documents, not confirmed".
- **Threshold source.** Experiment 43 `plan.json` `thresholds.clef_image`: 0.17220524482651753, fitted on 561 healthy fit pages (input SHA-256 `5721f983...`), amendment A1. The template rounds it to 0.172.
- **Stated cost.** About 2.7% of healthy pages (15 of 565) and about 3.6 s per judged page (Experiment 43, local arm, 3.64 s mean).
- **Known difference.** Experiment 43 judged LiteParse text of rescued documents with poppler renders. The shipped rule judges pdf-inspector Markdown of unflagged pages with the shipped renderer. The confirmation tests the shipped path as it is.
- **Issue #171.** Eleven deferred review points on the Experiment 43 harness.

## Goals / Non-Goals

**Goals:**

- Decide, on documents no earlier experiment used, whether the shipped router behaves as the app states.
- Call the shipped code, so the result is about the code users run.
- Close every issue #171 point in the new harness, each with a test that fails without the fix.

**Non-Goals:**

- Refitting the threshold, changing the question, the text head, the render or any default.
- Comparing other models, builds or questions.
- Choosing a default router. A PASS informs a separate decision.

## Decisions

### D1. Call the shipped path; record, do not re-implement

`score_router.py` builds an `EffectiveSettings` with one decision model entry (`llamacpp`, `external`, the harness's own `llama-server`) and one router entry with the template values. It calls `page_routing.page_evidence` (the scan), `page_rules.pipeline.run_rules` (blank, maths, non_latin and `document_router`, in order) and `compose_decision.build_page_judge`. `RecordingJudge` wraps the shipped judge: it passes each call through and records the answer, the text-head hash, the image hash and the time. It never changes an answer. Rejections come from the shipped rule's `RuleOutcome.add`.

Before any request the harness checks the plan recipe against `routerWords.ts` and `checks.SMOKE_QUESTION`. No change under `src/` is needed: `build_page_judge`, `run_rules` and `page_evidence` take injected settings and a transport.

Alternative: send System One requests from the harness, as Experiment 43 did. Rejected: it would test a copy of the prompt, text head and render, not the shipped code.

Alternative: a `managed` decision model entry, so OMRS starts `llama-server`. Rejected for this run: an `external` entry lets the harness run R1 to R6 on its own server with the pinned build. The rule, judge, adapter and renderer are the same in both cases.

### D2. Page range and populations

The manifest names a page range for each document. The scan runs on the whole file. The pipeline gets the evidence of the range pages only, so the router judges only those pages. A page the scan flagged goes to OCR without the router. A page an earlier rule claimed (for example a maths page) goes to OCR without the router. Both leave the router populations, and the summary reports them.

### D3. Corpus and overlap

`corpus_manifest.json` (format `omrs-exp47-corpus/1`) lists id, group, file, source address, licence, SHA-256 and page range. `prepare_inputs.py --validate` checks the schema and refuses any document whose SHA-256, file name or source address matches the committed source lists of Experiments 33 and 42. Experiments 38, 43 and 44 used the Experiment 33 documents, so these two lists cover all five. The lists are frozen by SHA-256 in `plan.json`.

### D4. Labels made on the machine, frozen before scoring

This reuses the Experiment 42 labelling plan (design D4 of `experiment-42-clef-flash-confirmation`). Experiment 42 itself switched to hosted Gemini references by amendment A7, so its labels cannot be reused here.

- Reference: dots-mocr through the shipped OCR routes (`capabilities.build_ocr_routes`), one page per request, offline. The Experiment 42 `references.py` pattern.
- Token rule: Experiment 33 `build_labels.tokens` and `recall`, imported by path, SHA-256 pinned. Not copied.
- Classes: `junk` below 0.50 with at least one text token, `healthy` at 0.80 or more, `grey` between, `excluded` for a failed or short reference or no text tokens (the Experiment 38 `classify_page` thresholds).
- Text under test: the pdf-inspector page Markdown, the text the router reads.
- Change from Experiment 33: the reference is the whole page. The Experiment 33 body-text split used a hosted model, and no page text leaves the machine here. The operator approves this change (OD3).
- Review: every junk and grey page and 15 seeded healthy pages, checked against the local page image. More than 3 disagreements stop the run.
- Freeze: scoring refuses until `labels.json`, `label_review.json` and `set_check.json` are committed, the review is complete and the set check passes. Both labelling steps refuse once a router score exists.

### D5. Gates (operator decision OD1: option B, 2026-11-05)

| Option | Gates | Effect |
| --- | --- | --- |
| A. Spec as written | junk recall >= 0.90 with lower 95% bound >= 0.80; healthy flag rate <= 0.02 with upper 95% bound <= 0.05 | Needs an interval function in `_lib/stats.py` and about 73 healthy pages with no false reject before the upper bound can reach 0.05. Experiment 43 (70% junk, 2.7% healthy) makes a FAIL likely |
| **B. Stated cost (chosen 2026-11-05)** | G1 junk recall >= 0.70; G2 healthy false-reject rate <= 0.05 (primary); G3 no JUNK document missed; G4 <= 5.0 s per judged page (secondary) | Checks the router against what the app tells users. Needs the MODIFIED pass-rule requirement in this change |

The operator chose option B on 2026-11-05 and approved the MODIFIED pass-rule requirement. G1 and G2 decide the verdict; G3 and G4 are reported only.

### D6. Fail-closed runner (issue #171)

| Point | Fix | Where |
| --- | --- | --- |
| 1 | Verdict withheld when a population is empty, a page has no score or a page failed | `_lib/run_safety.population_gaps`, `analysis.py` |
| 2 | `memory_pressure` output without a percentage stops the run | `_lib/run_safety.parse_free_memory_percent` |
| 3 | Cleanup procedure for private files | `protocol.md` section 8 |
| 4 | Page text and image hashes checked against `inputs.json` before the router reads them | `score_router.score_document` |
| 5 | `llama-server` stopped when startup fails before `/health` | `_lib/run_safety.start_until_ready` |
| 6 | Exclusive lock before the checkpoint is read | `_lib/run_safety.exclusive_lock` |
| 7 | Time, cost and failure stop rules in code | `exp47_io.StopRules` |
| 8 | No fit phase, so every scoring run checks the threshold and a committed `plan.json` | `exp47_io.check_threshold` |
| 9 | Run record appended before the first decision request | `score_router.run_arm`, `runtime_check` |
| 10 | Scoring refuses without a passing runtime check record (R4 and R5) for the same plan, inputs, labels, model and runner | `exp47_io.require_check` |
| 11 | Resume trusts a document only when its private files match the committed hashes; a re-read must give the same hashes; only committed files are read | `prepare_inputs.prepare` |

Generic fixes are new functions in `_lib/run_safety.py`. No existing `_lib` function changes, because earlier results depend on them.

### D7. Hosted reference

`jev_router` runs the same shipped path with a `typesafe` entry, threshold 0.21 (Experiment 43 amendment A3) and `send_off_machine` on. It runs only after a dated `decision_register` entry with scope `hosted_reference_arm`. The check happens before any request and before the run record. It never changes the verdict. The cost rule uses USD 0.00022 per page from Experiment 43, because the shipped judge reports no token count.

## Risks / Trade-offs

- [Small set: one page moves the healthy rate by about 2.5 points] → counts are reported with rates; the limit is stated in the report.
- [Whole-page references count figure text] → a review of every junk and grey page (by the coding agent, amendment A1); disagreements stop the run.
- [Renderer or scanner drift between steps] → `inputs.json` binds the scanner, renderer and their code hashes; scoring compares page text and image hashes.
- [0.172 and 0.17220524 differ] → the summary lists every page scored between the two values.
- [Option B lowers the bar of the existing spec] → the operator chooses; option A stays available.

## Migration Plan

None. Nothing ships. A PASS informs a separate decision about defaults.

## Operator decisions before the run

1. **OD1, gate option.** A or B (D5), then approve the hypotheses, gates, stop rules and set-check minimums.
2. **OD2, corpus manifest.** Approve the shortlist; fill `corpus_manifest.json`.
3. **OD3, labelling method.** Approve the local whole-page reference and the review rule (D4).
4. **OD4, hosted reference.** Run it or not (D7).
