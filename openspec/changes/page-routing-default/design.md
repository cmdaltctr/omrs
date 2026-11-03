# Design: page routing becomes the default and the document unit goes

## Context

Issue #161 showed the failure: a junk hidden text layer survives because document mode trusts it and the 10% gate rarely fires. Page mode reads every flagged page with the local tier and escalates what it cannot read; the `rf06` 10-page run (page 29 found at 0.99, worker pages Dice 1.0, blanks counted by `skip-blank-pages-before-worker`) is the evidence the operator accepted for flipping now (master flow D2, 2026-11-02). This change is ordered by `doc-reading-master-flow` group 2 and limited to its contents.

## Decisions

1. **The unit key stays, with one legal value.** `ocr_routing_unit` remains a setting with default `page`; `document` fails validation at start-up with a message naming `page` (the gotcha-11 pattern; `OCR_ROUTING_UNITS` becomes `("page",)`). Removing the key entirely was rejected because the master flow's task 2.2 expects "the default resolves to `page`", and a future unit can extend the tuple without a new key.
2. **The gate and its settings go together.** `ocr_required_by_gate` (now in `ocr_policy.py`), `ocr_fallback_page_fraction` and `ocr_fallback_min_confidence` are removed from Settings, the Settings-file write rule, the Settings page rows and the `read.document` options. Only the gate read `min_confidence`, so it goes with the function rather than staying as an unread setting. `ocr_fallback_enabled` stays: it switches OCR routing off. `OCR_UNCONDITIONAL_TYPES` loses its routing role and leaves the identity payload with the gate values.
3. **The document-unit code path is deleted.** The document branch of `OcrRoutedPdfInspector.load_data`, `_worker_document`, `maths_condition` (document-unit only) and the fast-path/degraded document stamping go. Maths page routing under the page unit (`split_page_routes`) is untouched. The ADR-066 rescue of last resort stays in the page path.
4. **A missing local runtime escalates instead of degrading.** Today a local-OCR exception makes flagged pages keep native text and count unresolved (the #161 trap). Instead, when the local tier cannot run, every flagged page joins the one page-listed worker request. With no worker either, the existing degradation applies (best available text, unresolved, one warning naming both tiers). Blank-page skipping still runs first, so blank sheets cost nothing either way.
5. **Identity: schema 7, one reindex.** The routing payload becomes `{enabled, routing_unit, blank_page_test, local_tier}`; `min_confidence`, `page_fraction` and `unconditional_types` go. `PAGE_ROUTING_ONLY_EMBED_KEYS` empties and `scoped_excluded_keys`'s subtraction dies with the document unit, exactly as `embed_exclusions.py` already anticipates ("If `page` ever becomes the default, empty this set and bump `_INDEX_IDENTITY_SCHEMA`"). `_INDEX_IDENTITY_SCHEMA` advances 6 to 7. Every source reindexes once.
6. **The stale-value refusals are start-up errors, not warnings.** `OCR_ROUTING_UNIT=document` and the two removed keys (`OCR_FALLBACK_PAGE_FRACTION`, `OCR_FALLBACK_MIN_CONFIDENCE`) follow the gotcha-11 shape: the start-up tripwire names the removal and the fix. A silent ignore would leave the operator believing a 10% rule still runs.

## What stays out

- No change to escalation rules, the 0.9 local cut, engine order, blank-page skipping, maths routing under the page unit, or the worker protocol.
- The operator's live-app step (master flow 2.4, `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` in the live environment) is the operator's; no live state is touched.
- The judge routers (proposals B and C) build on page mode afterwards, each from a fresh fork of the merged `v3`.

## Risks / Trade-offs

- [Stale configs fail at start-up] → Intentional and messaged. The refusal names `page` and the removed keys.
- [Every existing index reindexes once] → Accepted by the operator (master flow D2); current indexes are tests.
- [Flagged pages may cost worker time when the local runtime is missing] → Correct behaviour: reading the page beats keeping junk. The blank test and the local tier still shield the common cases.
- [The pdf-reader baseline loses its gate-calibration requirements] → The calibration history stays in the ADRs and experiment records; the spec describes the system as it will be.

## Open Questions

1. Remove `ocr_fallback_min_confidence` along with the gate? Recommendation: yes; nothing reads it once the gate goes. (The master flow named only the fraction; this follows the intent.)
2. Fold the ADR-069 page-routing amendment and this flip into one dated note on the ADR after merge? Recommendation: yes, as a short follow-up, matching the blank-pages follow-up pattern.
