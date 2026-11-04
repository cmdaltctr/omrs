# Design: route non-Latin pages straight to the OCR engine

## Context

See proposal.md for the why.

**Observed in the code (branch `v3`, `12699bda`):**

- Page routing (`integrations/pdf/ocr_routing.py`, `_page_unit_documents`) takes per-page evidence from `page_routing.page_evidence` (pdf-inspector `extract_pages_markdown`): page number, Markdown, `needs_ocr` and `ocr_reason`. The pdf-inspector 1.17.0 type stub says a page's Markdown is empty when `needs_ocr` is true. So a flagged page carries no text in the evidence that routing reads today.
- `maths_routing.split_page_routes(flagged, maths_pages)` returns `(direct, local)`. Direct pages skip the local tier and join one page-listed request (`_escalated_worker_text`). This is the seam the new setting uses.
- `page_routing.local_ocr` escalates on `missing_page`, `empty_text`, `low_confidence` (below `ocr_local_min_confidence`, default 0.9) and `hosted_recommended`.
- Other per-page evidence available without OCR: `pdf_inspector.extract_text_with_positions(path, pages)` gives text items with font names; pypdf gives font resources (used by `maths_pages.py`) and the catalogue `/Lang`.
- `ocr_identity.maths_routing_payload` shows the identity pattern: flag plus detector version.

**Observed in the data (read-only probe, 2026-11-02, pdf-inspector 1.17.0):**

| PDF | Script | Type | Pages flagged | Flagged Markdown | Fonts | Text items, pages 1 to 3 | `/Lang` |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| `io01` | Bengali | scanned | 49 of 49 | 0 chars | none | 20 items, 402 Latin letters | none |
| `io02` | Arabic | scanned | 16 of 16 | 0 chars | none | 3 items, 21 Latin letters | none |
| `io03` | Arabic | scanned | 5 of 5 | 0 chars | none | 3 items, 21 Latin letters | none |
| `io07` | Devanagari | scanned | 66 of 66 | 0 chars | none | 3 items, 21 Latin letters | none |

The text items look like a library stamp, watermark or catalogue text, not page text. They are all Latin, so on `io01` the detector would give a Latin verdict and keep the page on the local tier, which is the safe outcome. Stored Experiment 33 local OCR outputs (task 6.7) give a preliminary view of a post-local check: pages whose local output is mostly non-Latin letters: `io07` 59 of 60, `io01` 16 of 48, `io02` 1 of 14, `io03` 0 of 5. Local confidence was below 0.9 on all 129 pages, so the current cut already escalates every one. These counts come from a quick script, not a protocol. The experiment in task group 4 repeats them properly.

**Conclusion that shaped the scope:** no cheap pre-OCR signal exists for scanned non-Latin pages in the measured set. A Unicode-share detector works only on text that exists: a text layer on a flagged page (not seen in this corpus) or the local OCR output. The change therefore offers `always` for known collections and keeps `detect` honest about its reach.

## Goals / Non-Goals

**Goals:** skip the wasted local pass for known non-Latin collections; add a confidence-independent escalation for clearly non-Latin local output; measure before any default changes.

**Non-Goals:** an image-based script classifier; using a decision model to ask "is this page Latin?" (possible later with change C's routers); language identification; any change under the `document` unit.

## Decisions

### D1. One setting with three values

`ocr_non_latin_routing`: `off`, `detect`, `always` (the `always` mode for scanned non-Latin collections was confirmed by the operator on 2026-11-02). Alternative: a boolean plus a per-profile "collection script" field. Rejected: two settings for one decision. Alternative: auto-detect only. Rejected: it would detect nothing on the measured scans, and the setting would look broken.

### D2. Detector is fixed and versioned, not tuned by settings

Letters are characters where `str.isalpha()` is true. Latin letters are those whose Unicode name starts with `LATIN`. A verdict needs at least 40 letters (watermarks give about 7 per page) and a non-Latin share of at least 0.5. Both numbers live in `script_routing.py` with `SCRIPT_DETECTOR_VERSION = 1`, which joins the identity, like `MATHS_DETECTOR_VERSION`. Alternative: settings for both. Rejected: unmeasured knobs. The experiment can change the constants and bump the version.

### D3. Detect mode checks two points

1. Before the local tier: run the detector on the flagged page's text items (`extract_text_with_positions` for the flagged pages, one call per file). Non-Latin pages join the direct set.
2. After the local tier: run it on each local result. A non-Latin result adds the reason `non_latin_output` and escalates.

Point 1 costs one text extraction per file with flagged pages. Point 2 costs a character count.

### D4. Always mode uses the maths seam

`always` puts every flagged page in the direct set: `direct = flagged ∪ maths`. The local tier gets an empty list. Unflagged pages keep native text. This reuses `split_page_routes` and the one page-listed request, so no new dispatch path exists.

### D5. Degrade to today when no engine is available

Before building the direct set, check `OcrRoutes.select()`. If it is `None`, use today's split (maths only) and log one warning. Alternative: keep pages unresolved with empty text. Rejected: local text, even poor, beats empty text, and `off` behaviour is the safe floor.

### D6. Interactions

- **Page unit only.** Rebase note (2026-11-04): change `page-routing-default` removed the `document` unit (`OCR_ROUTING_UNITS = ("page",)`), and start-up refuses any other value. The earlier document-unit note and identity rule were dropped, because that state cannot occur.
- **Maths.** Union of direct sets, one request, one entry per page.
- **`ocr_local_min_confidence`.** Unchanged for pages the local tier reads. `non_latin_output` is an extra reason, not a new cut.
- **Change C routers.** A router acts on rescued or native text pages. This setting acts on flagged pages. They do not touch the same pages. If both apply to one page in future, the router runs first, and its "no" pages enter the flagged set.
- **Change A engine list.** Direct pages go to the engine list. Nothing here depends on its length.

### D7. Identity and diagnostics

Block `script_routing: {mode, detector_version}` only with a mode other than `off`. Existing digests stay the same. Cost for real users: turning the setting on reindexes PDF sources in page-unit collections once. `pages_non_latin` is a scalar count, added to `EXCLUDED_EMBED_METADATA_KEYS`.

### D8. Studio

`read.document` gets `ocr_non_latin_routing` (ADR-105: steps own their OCR settings). Validation uses the Document reading rule. Graph-wide override stays host-owned.

## Risks / Trade-offs

- [Operator expects `detect` to find scanned Arabic pages] → the Settings row and the guide say it does not, and name `always`.
- [`always` on a mixed Latin collection sends Latin flagged pages to the engine] → slower (engine 7 to 56 s per page against 0.75 s local), not wrong. The row says to use it only for a known collection, and Studio lets one profile carry it.
- [The 40-letter floor misses short non-Latin pages] → such pages go through the local tier and the confidence cut as today.
- [Post-local check fires on Latin pages with many symbols] → letters only are counted, and Latin accented letters count as Latin. The experiment measures false positives on all Latin pages of Experiment 33.

## Migration Plan

Default `off`. No action on upgrade. Rollback: revert; a file key `ocr_non_latin_routing` is then reported as unknown and ignored.

## Open Questions

- Should a later change let a router (change C) answer "is this page in a Latin script?" for scans, so `detect` can see images? Recommendation: decide after the experiment and after change C's confirmation experiment.
