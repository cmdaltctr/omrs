# Design: ordered lists for PDF readers and OCR engines

## Context

See proposal.md for the why. This section separates what the code does today (observed on branch `v3` at `12699bda`) from what this change proposes.

**Observed:**

- `config/__init__.py` holds one `pdf_reader: str = "pdf_inspector"`. `config/rules.py` holds `PDF_READER_NAMES = ("auto", "liteparse", "pdf_inspector", "pypdfium2", "pypdf")` and the nine `DOCUMENT_READING_KEYS`. An unknown value warns and falls back to `auto`.
- `integrations/pdf/registry.py` registers four readers with `register(name, import_path, probe_module, text_format=..., page_provenance=..., output_revision=...)`. `factory.py` resolves `auto` as LiteParse, then pypdfium2, then pypdf.
- `capabilities.resolve_pdf_reader` logs an error and uses pypdf when the configured reader is not importable. `capabilities.pdf_reader_options()` already probes every registered reader.
- The ADR-066 rescue chain lives inside `integrations/pdf/pdf_inspector.py` (`_rescue_pages`). It names `liteparse` and `pypdf` in code. A LiteParse failure hands over to pypdf; a pypdf exception propagates.
- `config/ocr_routes.py` holds `ocr_engine_primary = "dots-mocr"` and `ocr_engine_fallback = "paddleocr-vl"`. `integrations/ocr_worker/routes.py` builds `OcrRoutes(primary, fallback)`; `select()` returns the first available of the two. A fallback that resolves to the primary's command shares its client.
- `core/ingestion/source_state.py` hashes `parser.pdf_reader` (the single value), `pdf_reader_output_revision`, `ocr_worker_fingerprint` and `ocr_fallback_fingerprint`. `ocr_identity.route_fingerprints` returns a pair.
- The Studio Read document step (`core/ingestion/graph_adapters_catalogue.py`, `ReadParams`) has `pdf_reader`, `ocr_engine_primary` and `ocr_engine_fallback`. `transports/api/uninstall_profiles.py` walks saved profiles for `params.pdf_reader`. No operation-version upgrade path exists in `core/pipelines/`.
- Integrations has an Extras entry for `pdf-pypdfium2` and `pdf-inspector` (`transports/api/integrations_catalogue.py`), but no view of all readers. LiteParse and pypdf are base dependencies and have no row.
- `docs/guides/configuration.md` says the page cannot set "no fallback engine": a blank `ocr_engine_fallback` in `omrs.jsonc` reads as "not set".

**Proposed:** the decisions below.

## Goals / Non-Goals

**Goals:** visible reader installation state, ordered and editable reader and engine lists, no behaviour or identity change for existing configurations.

**Non-Goals:** per-page reader rescue (change C judges pages), changing the OCR gate or routing unit, a judge that moves a request to the next engine on a bad answer (change C), retiring the old keys.

## Decisions

### D1. The ADR-066 chain becomes the default list, not a hidden rule

`pdf_readers` defaults to `pdf_inspector, liteparse, pypdf`. The rescue tiers are the readers after the first. Alternative: keep the chain fixed in code and let the list hold only availability fallbacks. Rejected: two meanings in one setting, and the chain would stay invisible on the page. Writing the chain out makes the default inspectable and editable, and the identity rule (D5) keeps the digest stable.

### D2. One rule for "the next reader"

A later reader runs when (a) the reader before it is not installed (start-up, as `auto` does today), or (b) it returned no text for a PDF with pages. For pdf-inspector, (b) is the existing contradiction trigger (`text_based`, empty Markdown, pages above zero). A retry tier that raises hands over; the last tier's exception propagates. A primary reader's exception propagates, as today. This mirrors the OCR rule: availability and empty output move on, a crash after work started does not. Alternative: move on after any exception. Rejected: ADR-066 kept pypdf exceptions visible because they mean broken input.

### D3. A small chain module owns the tiers

A new `integrations/pdf/chain.py` takes the resolved list and the registry and runs tiers. `PdfInspectorReader` receives its tier names in its constructor. A bare `PdfInspectorReader()` keeps `("liteparse", "pypdf")`, so direct callers and the spec scenario "Bare direct adapter use stays on liteparse" hold. The adapter no longer names tiers. A new reader stays one adapter file plus one `register()` line (architecture invariant 11).

### D4. New list keys, old keys read for ever

- New: `pdf_readers` (`PDF_READERS`) and `ocr_engines` (`OCR_ENGINES`). Environment form: comma-separated, spaces trimmed. File form: JSON array of strings.
- Old: `pdf_reader`, `ocr_engine_primary`, `ocr_engine_fallback` stay valid in every source. They are not added to `config/legacy.py`, so gotcha 11's tripwire never fires.
- Resolution: the highest source that sets either form wins. Within one source, the list key wins and the old key is reported as ignored.
- Writing: the page writes only the list key and removes the matching old keys in the same atomic write (`settings_file_write.py`, comments kept).
- `omrs config init` builds its template from the model, so it shows the list keys. The old fields are marked so the template leaves them out.
- Alternative: retire the old keys with a tripwire. Rejected: no benefit to users, and the flat names would need a lifetime rule.

### D5. Index identity: hash what changes text, keep old digests

- Reader list: when the resolved list equals the expansion of a single value, `parser.pdf_reader` keeps that single value and nothing is added. Otherwise `parser.pdf_readers` (the full list) is added. Only PDF sources reindex.
- Engine list: entries 1 and 2 keep `ocr_worker_fingerprint` and `ocr_fallback_fingerprint`. A list of one gives the unavailable payload for entry 2, exactly as an empty fallback does today. Entries 3 and later add `ocr_more_fingerprints` only when present.
- No bump of `_INDEX_IDENTITY_SCHEMA`: every existing digest is unchanged.
- Cost for real users: none on upgrade. A user who edits a list reindexes PDF sources once on the next explicit ingest.

### D6. OcrRoutes holds a tuple

`OcrRoutes(routes: tuple)`. `select()` returns the first available client. `fingerprint` and `fallback_fingerprint` stay as properties for entries 1 and 2. Routes that resolve to the same command share one client, as today. The operator-stop retry (ADR-109) goes to the next available route once. The Integrations runtime items use `used_by = ("ocr_engines",)`.

### D7. Studio keeps old options valid

`ReadParams` adds `pdf_readers` and `ocr_engines`. The old fields stay accepted, expand by D4 rules, and a node that sets both forms fails validation with both names. No operation-version bump, because no upgrade path exists and none is needed. The graph fingerprint applies D5, so saved graphs keep their identities. `uninstall_profiles.py` walks both forms.

### D8. Integrations › PDF readers is built from the registry

`GET /v1/integrations` gains `pdf_readers`: one item per registered reader with `name`, `installed`, `extra` (or `null` for base), `fix_command`, `used_by`. The probe reuses `capabilities.pdf_reader_options()`. It only imports. The section goes in `web/src/integrations/` as `PdfReadersSection.tsx`, using `EntryList` and `CopyCommand`, with the attention count rule of `sections.ts`.

### D9. Front end

Load the `omrs-design` skill before UI work. A shared `OrderedListControl.tsx` serves both lists (up, down, remove, add from the known names). Each component stays under 200 lines. Check at 1280 px and 390 px.

## Risks / Trade-offs

- [A user builds a list with no text-capable retry, for example `pdf_inspector` alone] → rescue never runs and a silent-empty PDF indexes nothing. The row text says so, and Document reading warns when the list has one reader and that reader is pdf-inspector.
- [Comma-separated environment form cannot hold a name with a comma] → reader and engine names never hold commas (`ENGINE_NAME_PATTERN`, registry names).
- [Old and new keys in different sources confuse users] → `omrs config show` prints the winning key and its source, and the page lists the ignored old key.
- [More engines mean more memory if several start] → only the first available engine starts. Later engines start only when earlier ones are unavailable before dispatch, as today.

## Migration Plan

1. Ship with defaults equal to today's behaviour. No action needed.
2. On the first page save of a list, old keys leave `omrs.jsonc`.
3. Rollback: revert the change. A file that holds only the list keys then falls back to code defaults (pdf-inspector and the two engines), which equal the new defaults. A custom list is lost on rollback, and the guide says so.

## Open Questions

- Should the Integrations PDF readers section also offer Install for readers behind an allowed extra (ADR-094), or only the copy command? Recommendation: copy command only in this change; Install already exists on the Extras rows.
