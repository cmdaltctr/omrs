# Proposal: skip blank pages before the OCR engine, and count them

## Why

Under `OCR_ROUTING_UNIT=page`, blank sheets (covers, empty backs) go through local OCR and then to the OCR engine. On a 10-page extract of `rf06`, 4 blank pages used about 167 s of engine time and came back empty. They are then counted `ocr_pages_unresolved`, which tells the operator that something failed when nothing did (handoff 2026-11-02, "rf06 unresolved pages").

## What Changes

- **New fifth page-source count `ocr_pages_blank`.** The page unit counts a flagged page as blank when the page image has no marks. The five counts (`native`, `local`, `worker`, `blank`, `unresolved`) sum to `page_count`. `unresolved` keeps its meaning: a flagged, non-blank page no tier produced text for, whether the local tier never ran or an escalation came back empty.
- **Blank pages skip both OCR tiers.** After pdf-inspector flags a page and before local OCR runs, the page unit renders the page and measures stroke ink. A page below the fixed threshold is blank. It keeps its native text (empty on every measured blank page) and emits no page document, as today. It never reaches local OCR or the OCR engine.
- **The blank test reads the page image, never OCR text.** Local OCR returns empty text on real content too (Experiment 33: recall 0.000 on Arabic and Devanagari pages, 0.310 on handwriting). Design.md records the measured signal on all 1,123 Experiment 33 pages and the margin between blank pages and pages with content.
- **Safe failure.** A page that cannot be rendered or measured is treated as not blank. It follows today's path.
- **No new setting.** The threshold is a code constant with a version number. The version joins the page-unit index identity so a later threshold change reindexes page-unit sources only.
- **Document unit unchanged.** The `document` unit emits no page-source counts and runs no blank test.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `pdf-reader`: the page-routed document gains the blank count; blank flagged pages skip local OCR and the OCR routes; page-routing-only keys include the new count.

## Impact

- Code: a new module under `src/omrs/integrations/pdf/` holds the blank test (`ocr_routing.py` is at its 500-line ceiling). `page_routing.py` gains the blank source and count key. `ocr_routing.py` calls the test once, between flagging and local OCR. `core/ingestion/embed_exclusions.py` adds `ocr_pages_blank` to the exclusion set and to the page-routing-only keys. `core/ingestion/ocr_identity.py` adds the blank-test version to the page-unit payload.
- Index identity: page-unit sources reindex once (new excluded key and new version key). Document-unit sources keep their identity. `_INDEX_IDENTITY_SCHEMA` does not change.
- HTTP API: no contract change. Chunk metadata is a free-form mapping (`additionalProperties: true`) in `openapi.yaml`, so the new key appears there with no schema edit.
- Docs: the `docs/guides/ingestion.md` count table notes the fifth count. An ADR-069 amendment is a workflow follow-up.
- Dependencies: none new. LiteParse (render) is a base dependency. Pillow and NumPy come with `llama-index-core`, as NumPy already does for the reranker.
- Related planned changes: `ordered-reader-and-ocr-lists`, `non-latin-script-routing` and `document-reading-routers` all route pages after flagging. A blank page leaves the route before any of them, so none needs an edit.
