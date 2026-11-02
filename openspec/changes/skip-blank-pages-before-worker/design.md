# Design: skip blank pages before the OCR engine, and count them

## Context

See proposal.md for the problem. The page unit lives in `src/omrs/integrations/pdf/ocr_routing.py` (the page-unit read method, now at the 500-line ceiling) and `page_routing.py`. Today the method builds `flagged` from pdf-inspector's full scan, splits maths pages off with `split_page_routes`, runs `local_ocr` on the rest, sends escalated and maths pages to `_escalated_worker_text` in one request, and merges with `merge_pages`. Four counts come from `_COUNT_KEYS` in `page_routing.py`; `merge_pages` adds any page no tier reported to `ocr_pages_unresolved`, so the four always sum to `page_count`.

The four counts reach three other places:

- `core/ingestion/embed_exclusions.py`: `EXCLUDED_EMBED_METADATA_KEYS` and `PAGE_ROUTING_ONLY_EMBED_KEYS`. Under the `page` unit the exclusion list enters the index identity (`embedding_text.excluded_keys`); under `document` the page-only keys are subtracted.
- `core/ingestion/ocr_identity.py`: `ocr_routing_payload` adds `routing_unit` and `local_tier` only off the `document` default.
- `src/omrs/transports/api/openapi.yaml`: chunk `metadata` is `type: object, additionalProperties: true`. No count is named in the contract. The web front end reads none of the four keys.

## Goals / Non-Goals

**Goals:**

- Blank flagged pages cost no local OCR and no OCR engine time.
- A fifth count, `ocr_pages_blank`, so `unresolved` means only "an escalation produced no text".
- Never skip a page with readable content. Errors must fall on the cheap side: a doubtful page goes to OCR as today.

**Non-Goals:**

- No setting, no option, no per-profile switch.
- No change to the `document` unit.
- No change to escalation rules, the 0.9 local cut, or the engine order.
- No attempt to detect pictures without text. A photograph has ink and goes to OCR as today.

## Measurements

All numbers below were measured on 2026-11-02 with read-only scripts. Render: LiteParse 2.11.1 `screenshot` (the base dependency, PDFium inside). Corpus: all 1,123 pages of the 40 Experiment 33 documents. Reference: the frozen Experiment 33 transcriptions (`output/.transcripts/<doc>/pNNN.json`, `transcription` and `legibility`). No OCR model ran. No page text was printed.

### Candidates that fail

1. **LiteParse `is_solid_fill`.** True on 6 pages only (the pure white pages `io07` 1, 3, 5, 64, 65, 66). False on all 4 `rf06` blanks, because scanned paper has grain. Too narrow.
2. **Global ink ratio** (pixels darker than the page median by 40 grey levels). `rf06` page 40 scores 0.47 and page 70 scores 0.21: both are a small empty sheet on a dark scanner lid. A clean digital page (`io05` p1, 91 characters) scores 0.0. No threshold works.
3. **Stroke ink with a margin crop instead of edge removal.** Removes the scanner frame but also removes headers near the edge: `rf07` p12 (11 characters) drops to 4.6e-5, below the `rf06` blanks.
4. **pdf-inspector `ocr_reason`.** All 4 blanks say `scanned`, but so do 380 of 701 flagged pages, including every non-Latin page. Not a blank signal.
5. **Local OCR returned no text.** Rejected without measurement because Experiment 33 already shows recall 0.000 on Arabic and Devanagari pages and 0.310 on handwriting.

### The chosen signal: edge-free stroke ink

1. Render the page. Convert to grey. Downscale with a box filter so the long side is 1000 px.
2. Morphological closing with a 9 x 9 square (maximum filter, then minimum filter). It removes dark marks thinner than 9 px and keeps large dark areas and straight edges.
3. Stroke ink: pixels where the closing is brighter than the image by more than 40 grey levels.
4. Remove specks: keep an ink pixel only when at least 3 of its 8 neighbours are ink.
5. Remove every ink mark connected to the image border (geodesic reconstruction from the border). This drops scanner frames and the edge of a small sheet.
6. Score: the fraction of remaining ink pixels. A page is blank when the score is below **1.5e-4** (0.015 % of pixels).

NumPy and Pillow only. Measured cost: 0.28 s per page for render plus score on this machine (89 `rf06` pages in 24.5 s). The OCR engine took 33 to 51 s for each blank page.

### Measured values (score, threshold 1.5e-4)

| Document | Page | Reference | Score | Verdict |
|---|---|---|---|---|
| rf06 | 20 | empty, no_text | 0.000000 | blank |
| rf06 | 40 | empty, no_text (sheet on dark lid) | 0.000074 | blank |
| rf06 | 70 | empty, no_text (sheet on dark lid) | 0.000092 | blank |
| rf06 | 80 | empty, no_text | 0.000043 | blank |
| rf06 | 9 | 1 character (page number) | 0.000011 | blank |
| rf06 | 13 | 2 characters (page number) | 0.000022 | blank |
| io07 | 1 | empty, no_text (solid white) | 0.000000 | blank |
| io06 | 78 | 19 characters | 0.000801 | not blank (lowest content page) |
| rf07 | 28 | illegible | 0.000987 | not blank |
| rf07 | 30 | illegible | 0.001631 | not blank |
| rf06 | 34 | 23 characters, dark page | 0.001673 | not blank |
| rf07 | 12 | 11 characters | 0.002013 | not blank |
| io05 | 2 | illegible | 0.002784 | not blank |
| rf07 | 49 | 185 characters | 0.009403 | not blank |
| rf06 | 46 | 597 characters | 0.010501 | not blank |
| rf06 | 50 | 1,062 characters | 0.015947 | not blank |
| rf06 | 29 | 318 characters | 0.023442 | not blank |
| rf07 | 6 | 861 characters | 0.025115 | not blank |
| rf07 | 47 | 970 characters | 0.027923 | not blank |
| rf06 | 60 | 1,225 characters | 0.044235 | not blank |
| rf06 | 86 | 2,171 characters | 0.061587 | not blank |
| rf06 | 33 | 885 characters | 0.065206 | not blank |
| io01 | 13 | 591 characters, Bengali | 0.072404 | not blank |
| io07 | 28 | 715 characters, Devanagari | 0.089589 | not blank |
| io02 | 2 | 3,357 characters, Arabic | 0.167798 | not blank |

Whole corpus, flagged pages only (701):

| Group | Pages | Below 1.5e-4 (skipped) |
|---|---|---|
| Content: 3 or more reference characters, or illegible | 633 | 0 |
| Page number only: 1 or 2 reference characters | 16 | 8 |
| Empty reference, `no_text` | 52 | 29 |
| Of which, the 4 `rf06` blanks from the handoff (subset of the row above) | 4 | 4 |

The three groups total 701. Recounted 2026-11-02 from the frozen
references during the PR review: 633 + 16 + 52; the table first published
632 for the content group, one short.

None of the 422 unflagged pages scores below the threshold either. The 23 empty pages that stay above it (mostly `rf07` sheets with show-through and specks) go to OCR as today.

**Margin.** The highest `rf06` blank scores 9.2e-5. The threshold is 1.6 times that. The lowest content page scores 8.0e-4, 5.3 times the threshold. The margin is deliberately wider on the content side, because a wrong "blank" loses text and a wrong "not blank" only costs engine time.

### Synthetic sparse-ink check

The corpus has no page with 3 to 18 characters, so words were drawn on the real `rf06` p20 blank scan (render at 176 dpi, page median grey 222):

| Mark | Score | Verdict |
|---|---|---|
| "7", 10 pt, dark | 0.000027 | blank |
| "12", 10 pt, dark | 0.000074 | blank |
| "Index", 12 pt, dark | 0.000303 | not blank |
| "Notes", 12 pt, grey 150 (faint) | 0.000093 | blank |
| "Chapter 3", 14 pt, dark | 0.000618 | not blank |
| "RECEIVED" stamp, 18 pt | 0.000998 | not blank |
| one 40-character line, 11 pt | 0.001597 | not blank |

**Verdict: a safe blank test exists for real pages.** On the measured corpus no page with content is skipped, with a 5.3 times margin. Three known limits remain. A page whose only mark is a page number counts blank (8 of 16 measured), which loses only the number; `page_label` already carries it. A page whose only mark is one faint short word also counts blank. A page whose only mark is a lone one-pixel stroke also counts blank: the speck guard drops isolated single-pixel strokes before the score, and a hairline carries less ink than the faint word above. A test pins each limit. Open question 1 asks the operator to accept these limits.

## Decisions

1. **Where the test runs.** After `flagged` is built and before `split_page_routes`, on flagged pages only. A blank page leaves the route before the maths split, before local OCR, and before any OCR route. It produces a `PageResult` with its native text and a new source `blank`. Its native text was empty on all 37 pages the test would skip, so it emits no page document, as today.
   - Alternative: test only pages the local tier escalated. Fewer pages tested, but blank maths pages would still need a test before dispatch, and blank pages would still pay local OCR. Rejected for one placement with one rule.
2. **New module.** `src/omrs/integrations/pdf/blank_pages.py` holds the render and the score, with `BLANK_PAGE_TEST_VERSION = 1` and the threshold constant. `ocr_routing.py` gains one call and loses lines elsewhere if needed to stay at 500. Renders go in batches of 16 pages, because a PNG is up to 1.5 MB and a scan can flag hundreds of pages. Pillow and NumPy are imported inside the function (integrations rule 1).
3. **Fifth count.** `PAGE_SOURCE_BLANK = "blank"` and `ocr_pages_blank` join `_COUNT_KEYS`. `merge_pages` still puts unreported pages in `unresolved`, so the five counts sum to `page_count`. A blank page has no producer, so it never changes `ocr_backend`. `ocr_used` stays false for it. `pages_needing_ocr` and `ocr_required` keep their meaning and still include blank pages, because pdf-inspector flagged them.
4. **Safe failure.** Any exception from the render or the score marks the page "not blank" and logs one warning for each file. The page follows today's route. The file never fails because of the test.
5. **Index identity.** Under the `page` unit, `ocr_routing_payload` adds `blank_page_test: 1` (the version constant). `ocr_pages_blank` joins `EXCLUDED_EMBED_METADATA_KEYS` and `PAGE_ROUTING_ONLY_EMBED_KEYS`. Page-unit sources reindex once. This is needed and not only tidy: a page-number page the engine used to read (for example "13") now emits no document, and stored counts move from `unresolved` to `blank`. Document-unit sources hash exactly what they hash today. `_INDEX_IDENTITY_SCHEMA` stays 6, as with the earlier page-unit payload keys (ADR-069 point 5).
6. **Contract.** No `openapi.yaml` edit. The key appears in the free-form chunk metadata mapping. Stored chunks written before the change keep four counts until they reindex, which the identity change forces for page-unit sources.

## Interaction with other routing

- **Maths pages.** The test runs before the maths split. A maths page has font glyphs and therefore ink, so it is not blank in practice. If it were blank, nothing would be lost by skipping it.
- **The 0.9 local cut.** Unchanged. It applies to pages the local tier reads; blank pages never reach it.
- **Change A, `ordered-reader-and-ocr-lists`.** A blank page is never in the page-listed request, so the engine order never sees it.
- **`non-latin-script-routing`.** The blank test runs first. Non-Latin pages scored 0.07 to 0.17, far above the threshold, so they reach that change's detector as before.
- **`document-reading-routers`.** Router-rejected pages carry rescued text and are not blank. No interaction.
- **Missing local OCR runtime.** The test uses LiteParse, not the local runtime, so blank pages still count blank when the local tier is missing.

## Risks / Trade-offs

- [A page whose only content is one faint short word counts blank] → Accepted limit, stated in docs. The mutation test pins that a single dark 12 pt word and an 11-character header are not blank.
- [The 40-document corpus is small; a new kind of scan could score near the threshold] → The post-build check (tasks) reruns the whole corpus through the real code. The version constant lets a later threshold change reindex page-unit sources only.
- [LiteParse changes its render resolution] → The score downsizes to 1000 px first, so resolution matters little. A unit test pins the score of a fixture page.
- [About 0.3 s added per flagged page] → Small next to local OCR and 33 to 51 s per engine page. Pages that are not flagged are never rendered.
- [Pillow is a transitive dependency (via `llama-index-core`), not declared by OMRS] → Same position as NumPy in `core/retrieval/reranker.py`. Open question 2.

## Migration Plan

No operator action. Page-unit sources reindex once on the next ingest. Rollback: revert the change; page-unit sources reindex once more.

## Open Questions

1. Accept that a page whose only mark is a page number, or one faint short word, counts blank? Recommendation: yes. The measured content margin is 5.3 times and the loss is at most one word.
2. Declare Pillow and NumPy as direct dependencies? Recommendation: no, follow the NumPy precedent; both come with `llama-index-core`.
