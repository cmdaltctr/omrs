# ADR-104: pdf-inspector Emits Page Documents

- **Date:** 2026-10-27
- **Status:** Proposed
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Amends:** [ADR-050](050-configure-pdf-inspector-as-default-reader.md) (its "whole-document markdown" consequence), [ADR-066](066-tiered-reader-fallback-chain.md) (decision 2, one joined fallback document), [ADR-069](069-page-level-ocr-routing-and-the-pdfium-runtime.md) (decision 4, one merged document per file)
- **Related:** [ADR-070](070-normalise-reader-output-before-chunking.md) (normalisation runs per document, unchanged), [ADR-055](055-embedding-text-is-a-declared-contract.md) (embedding text contract), TDR-024 (silent-empty fonts), TDR-026 (full-scan OCR count)
- **Change:** `openspec/changes/pdf-inspector-page-provenance/` (design D1 to D11)

## Context

The default PDF reader, `pdf_inspector` (ADR-050), emits one document for the whole PDF. Its chunks carry no page number. Search results and answer citations therefore cannot name a page.

The first publication benchmark (Experiment 35) scores FinanceBench by gold page (Hit@page). It must use the production default reader for every dataset, so the reader is never a hidden variable. The default reader must record pages before the pipeline sweep runs.

pdf-inspector 1.17.0 already has a per-page call, `extract_pages_markdown`. The adapter called it only to count OCR pages on `text_based` PDFs longer than 8 pages (TDR-026), and threw the page text away. Its `PageMarkdown.page` index is 0-based.

`liteparse` and `pypdfium2` already emit `page` (integer, 1-based) and `page_label` (`str(page)`). Both keys are in `EXCLUDED_EMBED_METADATA_KEYS`. `header_path` is a retained key, so it is part of the embedded text.

The index identity hashes `parser.pdf_reader` and `parser.text_format`. Neither value changes with this decision. Without a new identity input, a re-ingest of an unchanged PDF reports `skipped_unchanged` and keeps the old whole-document chunks without pages.

## Decision

1. **Two library calls per PDF (design D1).** The adapter keeps `process_pdf(path)` for `pdf_type`, `pdf_confidence`, `page_count`, the sampled `pages_needing_ocr` and the silent-empty test. It adds one `extract_pages_markdown(path)` call for the page text. For `text_based` PDFs longer than 8 pages, the full-scan OCR count comes from that same result, so the separate evidence call goes. Measured on 194 local PDFs (2,384 pages), one call each:
   - `classify_pdf` gave the same `pdf_type`, `pdf_confidence` and `page_count` as `process_pdf` on 194 of 194 files.
   - `classify_pdf` flagged fewer OCR pages than `process_pdf` on 71 of 194 files. It does not extract, so it misses pages that `process_pdf` flags after an empty extraction (the TDR-024 fonts).
   - The full-scan count was never lower than the `process_pdf` count. On the 85 files where the `process_pdf` count is already complete (8 pages or fewer, or not `text_based`), it was equal on 80 and higher on 5.
   - Time for the 194 files: `process_pdf` 10.5 s, `extract_pages_markdown` 10.7 s, `classify_pdf` 0.7 s.

   The added cost is one parse, about 4 ms per page, for PDFs that did not already get the full scan.

2. **One document per page with text.** Each document carries `page = PageMarkdown.page + 1` and `page_label = str(page)`, plus the whole-PDF evidence keys. Pages with only whitespace emit no document. When the per-page call raises, or gives no text while the `process_pdf` Markdown has text, the adapter emits that Markdown as one document without page keys and logs a warning. `page_count` stays the `process_pdf` value.

3. **The fallback chain keeps pages (design D4, amends ADR-066).** The liteparse and pypdf tiers keep one document per recovered page instead of one joined string. LiteParse pages keep their own `page` and `page_label`. pypdf pages are numbered by position (`page = index + 1`) before empty pages are dropped, and get `page_label = str(page)`. The PDF's own logical label (for example `"iii"`) is not kept, because one reader must give one label format and Hit@page scores physical pages. Each recovered document carries the fallback diagnostics. Tier order and the error boundary do not change.

4. **OCR routing keeps pages (design D5, amends ADR-069 decision 4).**
   - Document unit, gate not met or route missing: the seam stamps the OCR diagnostics and the maths count on every page document and returns them all.
   - Document unit, worker path: the worker returns one text for the whole PDF. The seam returns one document with that text, the whole-PDF evidence and no page keys.
   - Page unit: the seam emits one document per page with text, with `page`, `page_label`, the four page-source counts and the diagnostics on each. `merge_pages` still computes the counts and the backend, but its joined text is no longer the output. The last-resort rescue returns the wrapped reader's page documents with all-native counts.

5. **Each PDF reader declares an output revision (design D7).** The registry gains `output_revision` (integer, default 1). `pdf_inspector` declares 2. When the resolved PDF reader reads the file, the index identity gains `parser.pdf_reader_output_revision`. Other sources carry no such key and keep their digest. `_INDEX_IDENTITY_SCHEMA` stays 6. Every PDF source therefore reprocesses once on its next ingest.

6. **A chunk never crosses a page break (design D8).** The Markdown splitter works per document. A chunk can no longer hold the end of page N and the start of page N+1, and chunk overlap stays inside one page. Measured on 198 local PDFs (2,384 pages, 1,420 breaks between two pages with text):
   - At 1,174 breaks, the whole-document Markdown already had a blank line between the pages. pdf-inspector concatenates pages and does not stitch paragraphs.
   - 15 breaks had a table row on both sides. At all 13 that could be located, the whole-document output also had a blank line there. No table was joined across pages.
   - 82 breaks matched without a blank line, but the samples show running text matched at the wrong place. 164 could not be matched, because the whole-document call removes running headers and footers.
   - Per-page text summed to 4,825,455 characters against 4,778,166 for the whole document (+1.0%).

   Per-page output therefore splits nothing that the whole-document output joined. A paragraph that runs over a break becomes two chunks, each with its correct page. The chunk count rises a little.

7. **Heading context carries across page breaks (design D11, decided 2026-10-27).** The Markdown chunkers build `header_path` from an empty heading stack for each document. With one document per page, the first chunks of a page would lose the heading opened on an earlier page (67 of 72 page breaks on Experiment 3's 4 PDFs). When the chunker receives several page documents from one source, it sorts them by `page` and starts each page with the heading stack left open at the end of the previous page. A heading on the new page closes open headings of the same or a deeper level. A gap in page numbers ends the inherited stack. The stack never crosses into another source. The legacy Markdown path and the model-token path use one shared helper, so the two paths cannot disagree.

Normalisation (ADR-070) already runs per document. Its rules do not change, so `NORMALISER_VERSION` stays 2.

## Consequences

### Positive

- Search results and answer citations from the default reader name a physical page.
- The page format is the same for `pdf_inspector`, `liteparse` and `pypdfium2`.
- Classification, OCR evidence counts and the OCR gate decision do not change for any file.
- Only PDF sources rebuild. Markdown, code and other sources keep their digest.
- Chunks keep the section heading of the whole-document output across page breaks.

### Negative

- **One-time rebuild.** Every PDF source in every collection reprocesses (re-chunk and re-embed) on its next ingest. This includes the live `~/.omrs` app. Until then, old PDF chunks stay searchable without a page. Re-ingest each PDF folder after the upgrade.
- **Running headers stay in page text.** The whole-document call removes repeated running headers and footers. The per-page call does not. For example, "S. Popat, L. Starkey *Computers & Education 128 (2019) 365–376*" now starts several pages of the Popat paper. Heading levels can also differ between the two calls: the Van Der Weel paper has `# Methods` per page and `## Methods` whole. The pipeline sweep measures the effect. A later change can drop lines that repeat at the top or bottom of most pages.
- **Worker-read documents have no page.** A PDF that the document unit sends to the OCR worker loses its page numbers. FinanceBench 10-K filings are text PDFs and stay on the fast path. The benchmark's page check finds any exception.
- **Extra parse.** One more pdf-inspector parse for each PDF that did not already get the full scan, about 4 ms per page.
- **Heading carry-over depends on page order.** Pages are sorted before chunking, and a gap ends the inherited stack, so a wrong heading is never carried over a missing page.

### Neutral

- If `extract_pages_markdown` and `process_pdf` disagree on the page count, page numbers follow the per-page result and the adapter logs a warning. They agreed on 194 of 194 files.
- The page routing unit still runs its own per-page scan (`page_evidence`). Removing that third parse is out of scope.
- pdf-inspector stays at 1.17.0. No dependency changes.
- Rollback: revert the merge commit. The revision key leaves the identity, so PDF sources reprocess once more and return to whole-document chunks.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **`classify_pdf` plus `extract_pages_markdown`, full-scan count for every file** | About 10 s faster per 194 files, but the OCR count rises on 5 of 85 short or mixed files. The OCR gate (`OCR_FALLBACK_PAGE_FRACTION=0.10`) would then route more files to OCR. That is a second behaviour change and needs its own evidence. |
| **`classify_pdf` plus `extract_pages_markdown`, sampled count from `classify_pdf`** | Under-counts OCR pages on 71 of 194 files and breaks the silent-empty rescue evidence. |
| **`extract_pages_markdown` alone** | It returns no `pdf_type` or confidence, so the OCR gate has no classification. |
| **`process_pdf(path, pages=[n])` once per page** | One parse per page, a 1-based argument next to 0-based results, and it does not remove running headers on a single page either. |
| **Bump `_INDEX_IDENTITY_SCHEMA` to 7** | Every source of every type reprocesses, for example a whole codebase collection, for a change that touches only PDFs. |
| **Bump `NORMALISER_VERSION`** | The normaliser did not change. The version is hashed for every source, so the blast radius equals a schema bump. |
| **Add the revision key only when the revision is above 1** | Saves the rebuild of PDFs read by other readers, but adds a hidden rule. "Every PDF source carries its reader revision" is easier to test and explain. |
| **Prepend the open heading lines to each page text in the adapter** | Changes the stored page text and the page character counts. |
| **Accept the heading loss at page breaks** | Rejected by the owner. `header_path` is embedded text, so the loss changes retrieval on 67 of 72 page breaks measured. |
| **Keep pypdf's logical page label** | One reader would give two label formats, and Hit@page scores physical pages. |

## References

- `openspec/changes/pdf-inspector-page-provenance/` (proposal, design D1 to D11, specs `pdf-reader` and `async-ingestion`)
- `src/omrs/integrations/pdf/pdf_inspector.py` (`PdfInspectorReader.load_data`, rescue chain)
- `src/omrs/integrations/pdf/registry.py` (`page_provenance`, `output_revision`)
- `src/omrs/integrations/pdf/ocr_routing.py` (`OcrRoutedPdfInspector`) and `page_routing.py` (`merge_pages`)
- `src/omrs/core/ingestion/backends/orchestrator.py` (pre-read revision resolver) and `source_state.py` (`build_index_identity`)
- `src/omrs/core/chunking/markdown.py` and `model_token.py` (heading carry-over)
- [Ingestion guide, PDF reader configuration](../guides/ingestion.md#pdf-reader-configuration)
- [Configuration guide, index identity](../guides/configuration.md#index-identity-and-re-ingestion)
- `docs/proposals/first-publication-benchmark.md` (Experiment 35, Hit@page)
