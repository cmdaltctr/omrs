# Design: pdf-inspector page provenance

## Context

See proposal.md for the reason. Current state, read on 27 October 2026:

- `PdfInspectorReader.load_data` calls `process_pdf(path)` and emits one `Document` with the whole Markdown and the evidence keys `pdf_reader`, `pdf_type`, `pdf_confidence`, `page_count`, `pages_needing_ocr`, `file_path`, `file_name`.
- `_complete_ocr_pages` calls `extract_pages_markdown(path)` only for `text_based` PDFs longer than 8 pages, and uses only its `pages_needing_ocr` count (TDR-026). The page text it returns is thrown away.
- The silent-empty guard (ADR-066) retries liteparse, then pypdf, and joins their page texts into one string.
- `OcrRoutedPdfInspector` reads `documents[0].metadata` as the evidence. The document unit stamps diagnostics on that one document. The page unit (`_page_unit_documents`) calls `page_evidence` (its own `extract_pages_markdown` call, already +1), routes pages, and `merge_pages` joins them into one document.
- `normalise_backend_read` normalises each document of a PDF read separately. It already loops over a list.
- `liteparse` and `pypdfium2` emit `page` (int, 1-based) and `page_label` (`str(page)`). The llama-index pypdf reader emits one document per page with `page_label` set to the PDF's own logical label (for example `"365"` or `"iii"`) and no `page`.
- `page` and `page_label` are already in `EXCLUDED_EMBED_METADATA_KEYS`. `header_path` is a retained key, so it is part of the embedded text.

pdf-inspector 1.17.0 API facts (checked on the installed wheel):

| Call | Page numbers |
| --- | --- |
| `extract_pages_markdown(path, pages=None)`: `PageMarkdown.page` | 0-based |
| `extract_pages_markdown(...)`: `PagesExtractionResult.pages_needing_ocr` | 1-based (94 of 94 files with flagged pages) |
| `process_pdf(path, pages=[n])` argument | 1-based |
| `classify_pdf(path).pages_needing_ocr` | documented 0-based |

The adapter uses only counts from the OCR lists, never indices. Page numbers come only from `PageMarkdown.page`.

## Goals / Non-Goals

**Goals:**

- Page documents from the default reader with the same `page` and `page_label` format as `liteparse` and `pypdfium2`.
- No change to classification, OCR evidence counts or the OCR gate decision for any file.
- Existing pdf_inspector indexes rebuild once on their next ingest. Other sources do not.

**Non-Goals:**

- Removal of running headers and footers that the whole-document call removes.
- Page numbers for documents the OCR worker reads as a whole PDF.
- A separate experiment. The pipeline sweep measures the effect.
- Removal of the third parse in the page routing unit (`page_evidence`).

## Decisions

### D1. Two calls: `process_pdf` for evidence, `extract_pages_markdown` for text

The adapter keeps `process_pdf(path)` and adds one `extract_pages_markdown(path)` call for every PDF. `process_pdf` supplies `pdf_type`, `pdf_confidence`, `page_count`, the sampled `pages_needing_ocr` and the silent-empty test (`markdown == ""`). `extract_pages_markdown` supplies the page texts and, for `text_based` PDFs longer than 8 pages, the full-scan OCR count. `_complete_ocr_pages` then reads the count from the result already in hand instead of calling the library again.

Measured on 194 local PDFs (Experiment 42 corpus and Experiment 3), one call each:

- `classify_pdf` gave the same `pdf_type`, `pdf_confidence` and `page_count` as `process_pdf` on 194 of 194 files.
- `classify_pdf` flagged fewer OCR pages than `process_pdf` on 71 of 194 files. It does not extract, so it misses pages that `process_pdf` flags after an empty extraction (the TDR-024 fonts).
- The full-scan count from `extract_pages_markdown` was never lower than the `process_pdf` count. On the 85 files where the `process_pdf` count is already complete (8 pages or fewer, or not `text_based`), it was equal on 80 and higher on 5 (4 `mixed`, 1 short `text_based`).
- Time: `process_pdf` 10.5 s, `extract_pages_markdown` 10.7 s, `classify_pdf` 0.7 s for the 194 files (2,384 pages).

Alternatives considered:

| Option | Rejected because |
| --- | --- |
| `classify_pdf` plus `extract_pages_markdown`, full-scan count for every file | Cheaper by about 10 s per 194 files. But the count rises on 5 of 85 short or mixed files, so the OCR gate (`OCR_FALLBACK_PAGE_FRACTION=0.10`) routes more files to OCR. That is a second behaviour change mixed into this one. It can be a later change with its own evidence. |
| `classify_pdf` plus `extract_pages_markdown`, sampled count from `classify_pdf` | Under-counts on 71 of 194 files and breaks the silent-empty rescue evidence. |
| `extract_pages_markdown` alone | It returns no `pdf_type` or confidence, so the OCR gate has no classification. |
| `process_pdf(path, pages=[n])` once per page | One parse per page, 1-based argument next to 0-based results, and it does not remove running headers on a single page either. |

The answer to "one call or two": two calls. The cheap classifier cannot replace `process_pdf` without changing the OCR evidence. The added cost is one parse (about 4 ms per page) for PDFs that did not already get the full scan. `text_based` PDFs longer than 8 pages already paid for both calls.

### D2. Page numbering

`page = PageMarkdown.page + 1` and `page_label = str(page)`. The `+ 1` lives in one small helper in the adapter, with a comment that names the 0-based source. `page_routing.page_evidence` already does the same conversion for its own call; it stays as it is.

Tests pin the conversion with a stubbed `pdf_inspector` whose pages are numbered 0, 1, 2, and with a real 2-page PDF compared against `pypdfium2`-style labels. Mutation checks: remove the `+ 1`, then change it to `+ 2`. Each mutant must fail a test.

### D3. Which documents the adapter emits

1. One document per page whose Markdown has non-whitespace text, in page order. Each carries the whole-PDF evidence keys plus `page` and `page_label`.
2. When `process_pdf` gives empty Markdown on a `text_based` PDF with pages, the rescue chain runs first (D4). This is the present trigger, unchanged.
3. When the per-page call raises, or gives no page text while `process_pdf` Markdown is not empty, emit the `process_pdf` Markdown as one document without page keys and log a warning. This keeps today's output as the safe floor.
4. When nothing has text, emit one document with empty text and no page keys, as today, so the OCR seam can read the classification.

`page_count` stays the `process_pdf` value. If the per-page result has a different length, the adapter logs a warning and still numbers pages from `PageMarkdown.page`.

### D4. Fallback chain keeps pages (ADR-066)

The liteparse and pypdf tiers keep one document per recovered page instead of one joined string. Each recovered document gets the pdf-inspector evidence keys, the fallback diagnostics (`extraction_fallback_backend`, `pages_needing_ocr=0`, `pages_needing_ocr_before_fallback`), and its page keys:

- liteparse: keep its own `page` and `page_label` (already physical, 1-based).
- pypdf: the llama-index reader returns one document per page in order, including empty pages. The adapter numbers them by position (`page = index + 1`) before it drops empty ones, and sets `page_label = str(page)`. pypdf's logical label is not kept, because one reader must give one label format, and Hit@page scores physical pages.

Tier order, the extraction-only liteparse construction and the error boundary stay as they are.

### D5. OCR routing (ADR-069)

- Document unit, gate not met or route missing: stamp the diagnostics and the maths count on every page document and return them all. The evidence is read from the first document, which carries the same whole-PDF values as the rest.
- Document unit, worker path: the worker parses the whole PDF and returns one Markdown text. The seam returns one document with that text, the whole-PDF evidence and no page keys. A future change can ask a protocol 1.1 route for `pages` = every page and use `pages_markdown`; it is out of scope here.
- Page unit: `_page_unit_documents` already knows each page's number, text and source (`PageResult`). It emits one document per page with text, with `page`, `page_label`, the four page-source counts and the diagnostics on each. `merge_pages` keeps computing the counts and the backend; its joined text is no longer the output. The last-resort rescue branch returns the wrapped reader's rescued page documents with all-native counts.

### D6. Normalisation (ADR-070)

`normalise_backend_read` already normalises each document, so it runs per page with no code change. `normalise_reader_text` is a pure function of its input text, and its rules do not change, so `NORMALISER_VERSION` stays 2. The identity change in D7 already reprocesses every affected source. A table or fenced block open at a page end is not protected across the break, but pdf-inspector already closes tables at page breaks (D8).

### D7. Index identity

Finding: `build_index_identity` hashes `parser.pdf_reader` (`"pdf_inspector"`) and `parser.text_format` (`"markdown"`). Neither changes. No reader or adapter version is in the payload. Without a change, a re-ingest of an unchanged PDF would report `skipped_unchanged` and keep the old whole-document chunks without pages. The benchmark's page check would then fail on reused indexes.

Decision: each registered PDF reader declares `output_revision` (integer, default 1). `pdf_inspector` declares 2. A pre-read resolver next to `resolve_declared_text_format` in `core/ingestion/backends/orchestrator.py` returns the revision of the resolved PDF reader when that reader reads the file (the same condition under which `_declared_text_format` asks the PDF reader), and `None` otherwise. `prepare_source` passes it to `build_index_identity`, which adds `parser.pdf_reader_output_revision` only when it is not `None`. The pipeline identify step already passes settings with the step's reader, so it gets the step reader's revision.

Effect: every PDF source read by any PDF reader gets a new digest and reprocesses once. `.md`, code and other sources keep their digest. `_INDEX_IDENTITY_SCHEMA` stays 6. The baseline test gains a PDF case with the new key.

Alternatives considered:

| Option | Rejected because |
| --- | --- |
| Bump `_INDEX_IDENTITY_SCHEMA` to 7 | Every source of every type reprocesses, for example a whole codebase collection, for a change that touches only PDFs. |
| Bump `NORMALISER_VERSION` | The normaliser did not change, and the version is hashed for every source, so it has the same blast radius as a schema bump. |
| Add the key only when the revision is above 1 | Saves the one-time rebuild of PDFs read by other readers, but adds a hidden rule. The simple rule ("every PDF source carries its reader revision") is easier to test and explain. |

### D8. Page breaks and chunking

The question was whether the whole-document Markdown joins elements across page breaks that per-page output would split. Measured on 198 local PDFs (2,384 pages; 1,420 breaks between two pages with text):

- At 1,174 breaks, the whole-document Markdown has the end of one page followed by a blank line and the next page. pdf-inspector concatenates pages; it does not stitch paragraphs.
- 15 breaks have a table row at the end of one page and at the start of the next. At all 13 that could be located, the whole-document output also had a blank line there, so the table was already two Markdown tables. No table was joined across pages.
- 82 breaks matched without a blank line, but the samples show repeated running text (journal names) matched at the wrong place. 164 could not be matched, because the whole-document call removes running headers and footers (see Risks).
- Per-page text summed to 4,825,455 characters against 4,778,166 for the whole document (+1.0%).

So per-page output splits nothing that was joined. What changes is chunking: the Markdown splitter works per document, so a chunk can no longer hold the end of page N and the start of page N+1, and chunk overlap does not cross a page break. A paragraph that runs over a break becomes two chunks, one per page, each with the correct page. The chunk count rises a little. `markdown_min_chunk_fraction` is 0 by default, so short page-end chunks are kept.

### D11. Heading context carries across page breaks (decided 2026-10-27)

The Markdown chunkers build `header_path` per document, from an empty heading stack. With one document per page, the first chunks of a page lose the section heading opened on an earlier page (67 of 72 page breaks on Experiment 3's 4 PDFs). `header_path` is part of the embedded text, so this would change retrieval.

Decision: when the chunker receives several documents from one source with page provenance, it processes them in page order and starts each page with the heading stack left open at the end of the previous page. A heading on the new page closes open headings of the same or a deeper level, as it does within one document. Chunks before the first heading on a page get the inherited `header_path`. The stack never crosses into another source.

Both chunking paths do this: the legacy Markdown path (LlamaIndex `MarkdownNodeParser`, `core/chunking/markdown.py`) and the model-token path (`core/chunking/model_token.py`). One shared helper computes the open stack at the end of a page, so the two paths cannot disagree.

Result to check: for a PDF whose page text joined in order equals the whole-document text, every chunk's `header_path` equals the path the whole-document chunking gives at that position.

Alternatives: prepend the open heading lines to each page text in the adapter. Rejected, because it changes the stored page text and the page character counts. Accept the loss. Rejected by the owner.



- `docs/guides/configuration.md`: the matrix row for `pdf_inspector` becomes `Yes: one document per page; the whole-document fallback and worker-read documents have no page` (the guard test reads only the leading `Yes`).
- `docs/guides/ingestion.md`: the reader table and the paragraph under it say that `pdf_inspector` emits one document per page, and name the fallbacks without pages.
- A new ADR, the next free number at build time (104 today), records D1, D4, D5 and D7. It amends ADR-050 (its "whole-document markdown" consequence), ADR-066 (one joined document) and ADR-069 decision 4 (one merged document per file). The ADR index and the amended ADRs get a status note.

### D10. Evidence plan

No separate experiment. The pipeline sweep, Part A (change `pipeline-sweep-llamacpp`), ingests Experiment 3's 6 documents and 5 FinanceBench PDFs with the default reader. Its baseline is Hit@1 17/17 for the Experiment 2 and Experiment 3 Ollama runs. This change merges before the sweep runs. The sweep's result shows whether per-page output keeps 17/17, and its step 1 checks that every PDF chunk has a page number. This change does not edit the sweep's files.

## Risks / Trade-offs

- [Heading carry-over is wrong for out-of-order or missing pages] → Pages are sorted by `page` before chunking. A missing page (for example a worker-read or failed page) ends the inherited stack for that source, so a wrong heading is never carried over a gap. Tests cover both cases.
- [Running headers stay in page text] The whole-document call removes repeated running headers and footers; the per-page call does not. Example: "S. Popat, L. Starkey *Computers & Education 128 (2019) 365–376*" now starts several pages of the Popat paper. Heading levels can also differ (the Van Der Weel paper has `# Methods` per page and `## Methods` whole). → Measure in the sweep. A later change can drop lines that repeat at the top or bottom of most pages.
- [Worker-read documents have no page] A PDF that the document unit sends to the worker loses page numbers. → FinanceBench 10-K filings are text PDFs and stay on the fast path. The benchmark's step 1 page check finds any exception.
- [One-time rebuild] Every PDF source reprocesses on its next ingest, in every collection, including the live `~/.omrs` app. Until then, old PDF chunks stay searchable without pages. → The release note and the ADR say so. Re-ingest the PDF folders after upgrade.
- [Extra parse] One more parse per PDF that did not already get the full scan. → About 4 ms per page; small against embedding time.
- [Page count mismatch] If `extract_pages_markdown` and `process_pdf` disagree on the page count, page numbers follow the per-page result. → Warn in the log. They agreed on 194 of 194 files.

## Migration Plan

1. Merge to `v3`. No settings change is needed.
2. Re-ingest each PDF folder. Each PDF reprocesses once through the failure-safe replacement path, so old rows stay searchable until the new rows are verified.
3. Rollback: revert the merge commit. The revision key leaves the payload, so PDF sources reprocess once more and return to whole-document chunks.
