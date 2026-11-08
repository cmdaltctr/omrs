# Design: old-print junk-text gate experiment

## Context

- The page scan (`page-routing-default`) judges a page by its text layer alone. A garbled old-print layer has plausible length and character mix, so it passes.
- The document router (ADR-112 page rule, off by default) shows Clef-Flash each unflagged page image and text, and sends the page to OCR when P(yes) is under the threshold. Experiment 43 fitted 0.172 on a mixed junk set; Experiment 47 showed it does not transfer to old prints.
- Experiment 47 labels: old-print junk pages have text-layer token recall 0.0 to 0.42 against the local reference (junk below 0.50); healthy false-reject 2 of 54 at 0.172.

## Goals / Non-Goals

**Goals:** decide, with a held-out set, whether either signal reaches junk recall at least 0.70 on old prints while healthy false-rejects stay at most 0.05.

**Non-Goals:** no default change in this change; no fix for reversed-order Arabic (G7) or table loss (G8); no new OCR engine; no hosted model as a production path.

## Decisions

### D1. Two sets, fit then confirm

Fit set: Experiment 47's old prints (J6, J11 to J18) plus new old prints. Held-out set: at least 6 old-print documents and 8 healthy documents never seen in Experiments 43, 47 or the fit step, frozen with SHA-256 before any score is read. Thresholds and word lists are fixed on the fit set and written into `plan.json` before the held-out run.

### D2. Arms

| Arm | Signal | Role |
| --- | --- | --- |
| control | shipped default, no router | baseline |
| clef_refit | Clef-Flash Q8_0 router, threshold fitted on the fit set | treatment |
| text_score | deterministic old-print text score, cut fitted on the fit set | treatment |
| jev_reference | hosted Jev router | reference only, open-licence pages only |

### D3. Labels

Each page is labelled from the image by the operator (junk text layer or healthy) before any arm runs, following the `ocr-routing-evaluation` labelling rules (OCR need labelled apart from unrecoverable content). Pages the page scan already sends to OCR are out of the denominators, as in Experiment 47.

### D4. Gates (held-out set)

- G1 primary: junk-page recall at least 0.70.
- G2 primary: healthy-page false-reject rate at most 0.05.
- G3 secondary: no old-print document with all junk pages missed.
- G4 secondary: added time at most 5.0 s per routed page on the Mac.

Report Wilson intervals. A treatment passes only if G1 and G2 pass.

### D5. What a pass leads to

A pass opens a separate production change. Likely shape: a new page rule (one file, one descriptor entry, one `register()` line, ADR-112), or a refitted router threshold, each visible in the Page routing panel. A fail on both arms closes the router line of work for old prints; #161 then gets a documented limit and a user-facing note.

## Risks / Trade-offs

- [Few public old prints with a garbled layer] → search archive.org and national library collections; keep the held-out minimum and report INCONCLUSIVE rather than lower it.
- [Word-list signal depends on language detection] → record the detected language per page; report recall per language.
- [Fit and held-out documents from one digitiser share artefacts] → spread the held-out set across at least three sources.
