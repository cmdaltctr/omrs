# Proposal: page routing becomes the default and the document unit goes

## Why

Issue #161 is the failure this closes: a scan with a junk hidden text layer keeps that junk, because document mode trusts the layer and the 10% gate rarely fires. Page mode fixes it, and the operator confirmed the order on 2026-11-02 (master flow design D2): flip the default now, on the strength of the `rf06` 10-page page-mode run (page 29 found at 0.99, worker pages Dice 1.0 against parity references, the four blank sheets now counted by `skip-blank-pages-before-worker`). A new-document re-test is not a gate for this flip. With page mode the only unit, the document gate, its 10% rule and its thresholds are dead code that can silently keep junk alive; they go.

## What Changes

- **`ocr_routing_unit` defaults to `page` and `document` is refused.** A config or environment value of `document` fails at start-up with a message naming `page` (the gotcha-11 pattern). The key stays, with `page` as its only legal value.
- **The document routing gate is deleted.** `ocr_required_by_gate` and `ocr_fallback_page_fraction` go. `ocr_fallback_min_confidence` has no reader once the gate goes, so it goes with them (open question 1). `ocr_fallback_enabled` stays: it still switches OCR routing on and off.
- **A missing local OCR runtime never returns junk text.** When the local OCR model or runtime is unavailable, flagged pages go straight to the worker engine. The current page-unit fallback (keep native text, count unresolved) is exactly the #161 failure mode and is removed.
- **One re-index, accepted.** The routing payload loses the gate values and the unconditional types; the page-only key scoping dies with the document unit; the identity schema advances from 6 to 7. Every existing source reindexes once.
- **No other settings.** No new keys. The Settings page, the Settings-file write rule and the `read.document` graph node drop the two removed keys.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `pdf-reader`: the gate, the document unit and its calibration requirements are removed; the page unit is the routing behaviour for every PDF; a missing local tier escalates to the worker instead of keeping native text; the unit-scoped identity rules become unconditional.
- `settings-file`: the writable key list drops `ocr_fallback_min_confidence` and `ocr_fallback_page_fraction`; `ocr_routing_unit` accepts `page` only.
- `workspace-settings`: the Document reading rows drop the two removed keys.
- `pipeline-graphs`: the `read.document` optional settings drop the two removed keys.

## Impact

- Code: `ocr_policy.py` (the gate function and both threshold constants), the document-unit branch and `_worker_document` in `ocr_routing.py`, `maths_condition` (document-unit only), the local-OCR failure branch in the page unit, the settings fields and their validation in `config/`, the identity payload in `core/ingestion/ocr_identity.py`, the page-only key scoping in `core/ingestion/embed_exclusions.py` (emptied; `_INDEX_IDENTITY_SCHEMA` 6 to 7), the pipeline lever lists in `core/pipelines/levers.py` and `core/ingestion/graph_adapters_catalogue.py`, and the Settings page rows in `web/`.
- Operators: `OCR_ROUTING_UNIT=document` or the removed keys in `omrs.jsonc`/environment fail at start-up with a message naming the fix. Every existing index reindexes once on the next ingest.
- The operator's live-app step (master flow 2.4: add `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` to the live environment) stays the operator's; this change touches no live state.
- Evidence: the `rf06` page-mode run (master flow D2), issue #161, and the Experiment 33 corpus measurements already recorded.
