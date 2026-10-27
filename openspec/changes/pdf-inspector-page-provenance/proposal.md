# Proposal: pdf-inspector page provenance

## Why

The default PDF reader, `pdf_inspector`, emits one document for the whole PDF. Its chunks carry no page number, so search results and answer citations cannot name a page.

The first publication benchmark (`docs/proposals/first-publication-benchmark.md`, Experiment 35) scores FinanceBench by gold page (Hit@page). It must use the production default reader for every dataset, so the reader is never a hidden variable. A per-dataset reader is not allowed. The default reader must therefore record pages before the pipeline sweep runs.

pdf-inspector 1.17.0 already has a per-page call, `extract_pages_markdown`. The adapter calls it today, but only to count OCR pages on long text PDFs.

## What Changes

- The `pdf_inspector` adapter emits one document per page that has text, in page order. Each document carries `page` (int, 1-based) and `page_label` (the same number as a string), the format `liteparse` and `pypdfium2` already use.
- The adapter keeps `process_pdf` for classification, the sampled OCR evidence and the silent-empty test. It takes the page text from one `extract_pages_markdown` call. That call also gives the full-scan OCR count, so the separate evidence call goes.
- Every page document carries the whole-PDF evidence keys (`pdf_type`, `pdf_confidence`, `page_count`, `pages_needing_ocr` and the others). These keys are already excluded from embedding text.
- When the per-page call fails, or gives no text while the whole-document Markdown has text, the adapter emits the whole-document Markdown as one document without `page` or `page_label`.
- The fallback chain (ADR-066) keeps one document per recovered page. LiteParse pages keep their numbers. pypdf pages get their physical number from their position.
- OCR routing: under the `document` unit, every page document gets the OCR diagnostics. A worker-read document has no page keys, because the worker returns one text for the whole PDF. Under the `page` unit, the seam emits one document per page with its page number, also for pages that local OCR or the worker read.
- The registry declares `page_provenance=True` for `pdf_inspector`, and a new per-reader `output_revision` (2 for `pdf_inspector`, 1 for the others).
- The index identity of every PDF source gains the reader output revision. Each PDF source therefore reprocesses once on its next ingest. Non-PDF sources keep their identity. **BREAKING** for stored indexes: PDF chunks built by the old reader are replaced on the next ingest, with new chunk boundaries at page breaks.
- Docs: the page-provenance matrix in `docs/guides/configuration.md`, the PDF reader section of `docs/guides/ingestion.md`, and a new ADR that amends ADR-050, ADR-066 and ADR-069.

Out of scope: a separate experiment, cross-page heading context, removal of repeated running headers, page numbers for worker-read documents, and any edit to the `pipeline-sweep-llamacpp` or `experiment-35-full-document-rag-benchmark` changes. The retrieval effect is measured inside the pipeline sweep (Part A), which runs after this change merges.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `pdf-reader`: `pdf_inspector` emits page documents with `page` and `page_label`, and declares page provenance. The rescue chain, the OCR evidence rule and the page routing unit keep one document per page. A worker-read document reports no page.
- `async-ingestion`: the index identity of a PDF source includes the declared output revision of the PDF reader, so a reader output change reprocesses PDF sources only.

## Impact

- Code: `src/omrs/integrations/pdf/pdf_inspector.py`, `registry.py`, `factory.py`, `ocr_routing.py`, `page_routing.py`; `src/omrs/core/ingestion/source_state.py`, `sources.py` and `backends/orchestrator.py` (pre-read revision resolver).
- Tests: `tests/test_page_provenance.py`, `tests/test_reader_text_format.py`, `tests/unit/test_pdf_inspector_reader.py`, `tests/unit/test_pdf_inspector_full_scan.py`, `tests/unit/test_page_unit_seam.py`, `tests/unit/test_index_identity_baseline.py`, `tests/unit/test_pdf_baseline_fixtures.py`, the OCR seam tests and the tripwire pin.
- Stored data: every PDF source in every collection reprocesses once (re-chunk and re-embed). This includes the live `~/.omrs` app.
- Chunks: no chunk crosses a page break. Chunk count rises a little.
- Runtime: one more pdf-inspector parse per file for PDFs that did not already get the full scan (about 4 ms per page on the 194 local test PDFs).
- Dependencies: none. pdf-inspector stays at 1.17.0.
