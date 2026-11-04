# Proposal: ordered lists for PDF readers and OCR engines

## Why

The operator cannot see which PDF readers are installed, and cannot choose the order in which readers and OCR engines are tried. Today the PDF reader is one value, the rescue tiers after pdf-inspector are fixed in code (ADR-066), and OCR has exactly one primary and one fallback engine. Changes B and C (issue #161) need these lists to be visible and editable first.

## What Changes

- **Integrations › PDF readers.** A new section lists every registered PDF reader (today pdf-inspector, LiteParse, pypdfium2 and pypdf). Each row shows "Installed" or "Not installed", where the reader is used, and a copy command that fixes a missing reader. A reader registered later shows up with no page change.
- **Settings › Document reading › PDF reading becomes an ordered list.** New key `pdf_readers` (env `PDF_READERS`, comma-separated). The first installed reader reads the file. A later reader runs only when the reader before it is not installed, or when it returned no text for a PDF that has pages. The default list is `pdf_inspector, liteparse, pypdf`, which is the ADR-066 rescue chain written out.
- **OCR engines become an ordered list.** New key `ocr_engines` (env `OCR_ENGINES`, comma-separated), default `dots-mocr, paddleocr-vl`, any length. A later engine runs only when every engine before it is unavailable before dispatch. A bad answer never moves a request to the next engine. A failure after dispatch stays a per-file error (the operator-stop exception of ADR-109 sends the request once to the next engine).
- **Old single-value keys keep working.** `pdf_reader`, `ocr_engine_primary` and `ocr_engine_fallback` (and `PDF_READER`, `OCR_ENGINE_PRIMARY`, `OCR_ENGINE_FALLBACK`) are still read and expand to the equivalent list. They are not retired, so no start-up tripwire fires. The Settings page writes only the new keys and removes the old keys from `omrs.jsonc` in the same save.
- **Studio follows the lists.** The Read document step gets `pdf_readers` and `ocr_engines` options. Saved graphs with the old options still load and run.
- **Index identity stays the same for existing configurations.** A list equal to the expansion of today's single values hashes exactly as today. Only a list that differs adds identity keys, and only those sources reindex.
- **Registry rule kept.** A new reader is one adapter file plus one `register()` line. A new OCR engine is one folder plus one list entry. The pdf-inspector adapter stops naming its rescue tiers in code.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `pdf-reader`: the reader setting becomes an ordered list, and the rescue tiers come from that list.
- `ocr-worker-engines`: the two engine routes become an ordered list of any length, with the same "unavailable before dispatch" rule.
- `maths-page-routing`: maths pages fall back down the engine list, not to one fallback.
- `pipeline-graphs`: the Read document step accepts the two lists and keeps accepting the old options.
- `runtime-components`: OCR engine items name `ocr_engines` in `used_by`.
- `workspace-integrations`: a PDF readers section.
- `workspace-settings`: Document reading edits the two lists.
- `settings-file`: old single-value keys are read and replaced by the list keys on the next page save.

## Impact

- **Settings:** `config/__init__.py`, `config/ocr_routes.py`, `config/rules.py` (`DOCUMENT_READING_KEYS`, list rules), `config/setting_shapes.py` (a list kind), `config/settings_file.py` and `settings_file_write.py` (list values, old-key removal), `core/settings.py` (`EffectiveSettings` fields).
- **Readers:** `integrations/pdf/factory.py`, `pdf_inspector.py` (rescue tiers injected), a new chain module beside them, `capabilities.py`, `compose_settings.py`, `core/ingestion/backends/local.py`.
- **OCR routes:** `integrations/ocr_worker/routes.py` (`OcrRoutes` holds a tuple), `core/ingestion/ocr_identity.py` and `source_state.py` (extra fingerprints only for a third engine or later).
- **Studio:** `core/ingestion/graph_adapters_catalogue.py`, `graph_adapters_values.py`, `graph_fingerprint.py`, `core/pipelines/levers.py`, `transports/api/uninstall_profiles.py`.
- **HTTP contract:** `openapi.yaml` (`IntegrationList.pdf_readers`, document-reading key enum and array values). The conformance tests must pass.
- **Front end:** `web/src/integrations/` (new section), `web/src/settings/DocumentReadingSection.tsx` and a list control, `web/src/studio/` engine and reader controls.
- **Docs:** `docs/guides/configuration.md` (PDF reading, OCR fallback, Document reading values, an upgrade note), `docs/guides/pipelines.md`, `docs/guides/architecture.md` (integration inventory row), `.env.example`.
- **Not changed:** the page routing unit (the only unit), the local OCR tier, and the default behaviour of any existing install.
