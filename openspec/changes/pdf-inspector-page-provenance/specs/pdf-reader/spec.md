## ADDED Requirements

### Requirement: pdf_inspector emits one document per page

The `pdf_inspector` reader SHALL emit one document for each page that has non-whitespace text, in page order. Pages without text SHALL emit no document. The declared text format SHALL stay `markdown`.

#### Scenario: Three-page PDF gives three page documents

- **GIVEN** a text-based PDF with 3 pages that each have text
- **WHEN** the PDF is parsed by `pdf_inspector`
- **THEN** the reader SHALL emit 3 documents in page order
- **AND** each document text SHALL be the Markdown of its own page only

#### Scenario: A page without text emits no document

- **GIVEN** a 3-page PDF whose second page has no text
- **WHEN** the PDF is parsed by `pdf_inspector`
- **THEN** the reader SHALL emit 2 documents, for pages 1 and 3

#### Scenario: No page has text

- **GIVEN** a PDF on which no page has text and no fallback tier recovers text
- **WHEN** the PDF is parsed by `pdf_inspector`
- **THEN** the reader SHALL emit one document with empty text and no `page` or `page_label`
- **AND** that document SHALL carry the classification so OCR routing can read it

### Requirement: pdf_inspector page numbers are physical and 1-based

Each page document SHALL carry `page`, the physical page number counted from 1, as an integer, and `page_label`, the same number as a string. pdf-inspector numbers pages from 0 in its per-page result, so the reader SHALL add 1.

#### Scenario: The first page is page 1

- **GIVEN** pdf-inspector reports a per-page result whose page index is 0
- **WHEN** the reader emits the document for that page
- **THEN** `page` SHALL be the integer 1
- **AND** `page_label` SHALL be the string `"1"`

#### Scenario: Labels match the other page readers

- **GIVEN** the same 2-page PDF parsed by `pdf_inspector` and by `pypdfium2`
- **WHEN** both readers emit their page documents
- **THEN** both SHALL give `page` values 1 and 2 and `page_label` values `"1"` and `"2"`

#### Scenario: A chunk keeps its page

- **GIVEN** a multi-page PDF ingested with `pdf_inspector`
- **WHEN** a chunk from page 2 is retrieved
- **THEN** the result SHALL carry `page_label` `"2"`

### Requirement: Every pdf_inspector page document carries the whole-PDF evidence

Each page document SHALL carry the same whole-PDF metadata: `pdf_reader`, `pdf_type`, `pdf_confidence`, `page_count`, `pages_needing_ocr`, `file_path` and `file_name`, plus any fallback diagnostics. These keys SHALL keep their present meaning and SHALL stay excluded from embedding text.

#### Scenario: Page documents agree on the evidence

- **GIVEN** a 12-page text-based PDF
- **WHEN** the PDF is parsed by `pdf_inspector`
- **THEN** every page document SHALL carry `page_count` 12
- **AND** every page document SHALL carry the same `pdf_type`, `pdf_confidence` and `pages_needing_ocr`

### Requirement: pdf_inspector falls back to the whole-document Markdown

When the per-page extraction raises, or gives no page text while the whole-document Markdown has text, the reader SHALL emit the whole-document Markdown as one document without `page` or `page_label`, and SHALL log a warning. The read SHALL NOT fail for this reason.

#### Scenario: Per-page extraction raises

- **GIVEN** a PDF whose per-page extraction raises and whose whole-document Markdown is not empty
- **WHEN** the PDF is parsed by `pdf_inspector`
- **THEN** the reader SHALL emit one document with the whole-document Markdown
- **AND** that document SHALL NOT carry `page` or `page_label`
- **AND** a warning SHALL name the file

### Requirement: Readers declare an output revision

Each registered PDF reader SHALL declare an integer output revision in its registry metadata. The revision SHALL increase when a change to the reader changes the documents it emits for the same file. The descriptor SHALL report it.

#### Scenario: Declared revisions

- **WHEN** the PDF reader registry is inspected
- **THEN** `pdf_inspector` SHALL declare output revision 2
- **AND** `liteparse`, `pypdf` and `pypdfium2` SHALL declare output revision 1

### Requirement: The document unit stamps OCR diagnostics on every page document

Under the `document` routing unit, the OCR routing seam SHALL read the evidence from the page documents and SHALL stamp `ocr_required`, `ocr_used`, `ocr_backend` and any maths count on every page document it returns. The fast and degraded paths SHALL keep the page documents and their page numbers.

#### Scenario: Fast path keeps the pages

- **GIVEN** the `document` unit and a clean 3-page text-based PDF
- **WHEN** the PDF is ingested
- **THEN** 3 page documents SHALL be returned with `page` 1, 2 and 3
- **AND** each SHALL carry `ocr_required` false and `ocr_backend` `pdf_inspector`

#### Scenario: Degraded path keeps the pages

- **GIVEN** the `document` unit, a PDF the gate routes to OCR, and no available OCR route
- **WHEN** the PDF is ingested
- **THEN** the native page documents SHALL be returned with their page numbers
- **AND** each SHALL carry `ocr_required` true and `ocr_used` false

### Requirement: A worker-read document carries no page provenance

Under the `document` routing unit, a document built from the worker's whole-PDF Markdown SHALL NOT carry `page` or `page_label`, because the response does not attribute text to pages. It SHALL keep `page_count` and the other whole-PDF evidence.

#### Scenario: Worker path emits one document without a page

- **GIVEN** the `document` unit and a scanned PDF that an available OCR route parses
- **WHEN** the PDF is ingested
- **THEN** the seam SHALL return one document with the worker Markdown
- **AND** that document SHALL NOT carry `page` or `page_label`

## MODIFIED Requirements

### Requirement: Page provenance is honest per reader

Readers that can observe page boundaries SHALL emit `page_label`, the key
retrieval reads. Readers that cannot SHALL emit nothing rather than a
placeholder, and the system SHALL NOT promise the field where it cannot be
produced.

#### Scenario: liteparse emits page_label

- **WHEN** a PDF is parsed by `liteparse`
- **THEN** each emitted document MUST carry `page_label` as a string
  alongside the existing integer `page`
- **AND** a chunk retrieved from that document MUST return a non-null
  `page_label`

#### Scenario: pypdfium2 emits page_label

- **WHEN** a PDF is parsed by `pypdfium2`
- **THEN** each emitted page document MUST carry `page_label` as a string
  alongside the existing integer `page`
- **AND** a chunk retrieved through the `auto` chain MUST preserve it

#### Scenario: pdf_inspector emits page_label

- **WHEN** a PDF is parsed by `pdf_inspector` and its per-page extraction succeeds
- **THEN** each emitted page document MUST carry `page_label` as a string
  alongside the existing integer `page`
- **AND** the reader MUST continue to report `page_count` in metadata so an
  operator can see the document's true length

#### Scenario: pdf_inspector reports no page

- **WHEN** `pdf_inspector` emits the whole-document Markdown as one document,
  because its per-page extraction failed or gave no text
- **THEN** `page_label` MUST be absent rather than fabricated
- **AND** the reader MUST continue to report `page_count` in metadata so an
  operator can see the document's true length

#### Scenario: Page support is discoverable

- **WHEN** an operator or caller inspects the configured reader through the
  registry descriptor
- **THEN** the descriptor MUST report whether page-level provenance is
  available under that configuration
- **AND** `pdf_inspector` MUST report that it is available

### Requirement: pdf-inspector silent-empty extraction SHALL recover via a plain-text retry

When the pdf-inspector reader classifies a PDF as `text_based` while its own Markdown extraction is empty and the page count is greater than zero, the adapter SHALL retry the file with the registered `liteparse` reader in extraction-only mode (OCR disabled regardless of operator settings), keeping one document for each recovered page, so a readable text layer is not silently discarded.

#### Scenario: Normal extraction is untouched

- **GIVEN** pdf-inspector returns non-empty Markdown for a `text_based` PDF
- **WHEN** the adapter emits its documents
- **THEN** no retry SHALL occur
- **AND** the metadata SHALL carry no fallback diagnostics

#### Scenario: Scanned classifications are untouched

- **GIVEN** pdf-inspector classifies a PDF as `scanned`, `image_based`, or another non-`text_based` type
- **WHEN** the adapter emits its documents
- **THEN** no retry SHALL occur regardless of extraction emptiness
- **AND** the OCR routing decision SHALL be unchanged

#### Scenario: Recovered pages keep their numbers

- **GIVEN** the liteparse tier recovers text from pages 1 and 3 of a 3-page PDF
- **WHEN** the adapter emits its documents
- **THEN** it SHALL emit 2 documents with `page` 1 and 3 and `page_label` `"1"` and `"3"`
- **AND** each SHALL carry the pdf-inspector evidence and the fallback diagnostics

### Requirement: The rescue retry needs no default settings and falls back to pypdf

The rescue tier SHALL receive concrete OCR and worker settings so it does not require default effective settings. When liteparse is unavailable or its retry yields no text, the adapter SHALL retry with the registered `pypdf` reader, preserving the same page-document contract.

#### Scenario: Bare direct adapter use stays on liteparse

- **GIVEN** no default effective settings were installed
- **WHEN** the contradiction triggers and liteparse can recover text
- **THEN** the liteparse tier SHALL run with OCR disabled and automatic worker selection
- **AND** pypdf SHALL NOT be selected

#### Scenario: liteparse unavailable falls through to pypdf

- **GIVEN** the contradiction triggers and the liteparse package is not installed, or its retry raises or yields no text
- **WHEN** the adapter emits its documents
- **THEN** the retry SHALL proceed with the registered pypdf reader
- **AND** the diagnostic SHALL name pypdf as the fallback backend when it produces the text

#### Scenario: pypdf pages are numbered by position

- **GIVEN** the pypdf tier returns one document per page, in page order
- **WHEN** the adapter emits the recovered documents
- **THEN** `page` SHALL be the 1-based position of the page in the file
- **AND** `page_label` SHALL be that number as a string, not the PDF's own page label

### Requirement: Rescue diagnostics name the tier that produced the text

Diagnostics SHALL be additive, and `extraction_fallback_backend` SHALL name the tier that produced the text (`liteparse` or `pypdf`); diagnostics SHALL NOT claim the OCR worker or any other backend produced it.

#### Scenario: Contradiction triggers the retry

- **GIVEN** pdf-inspector returns `pdf_type=text_based`, non-zero `page_count`, and empty Markdown
- **WHEN** the adapter emits its documents
- **THEN** the document texts SHALL be the liteparse per-page extraction, one document per recovered page
- **AND** each document SHALL carry an additive diagnostic naming liteparse as the fallback backend

### Requirement: pdf-inspector OCR evidence SHALL cover every page of text_based PDFs longer than the detection sample

pdf-inspector detects OCR need from a bounded page sample (8 pages). When `process_pdf` classifies a PDF as `text_based` and its page count is greater than 8, the adapter SHALL compute `pages_needing_ocr` from a scan of every page (`extract_pages_markdown`), so image-only pages outside the sample reach the OCR routing gate. The adapter SHALL NOT change `pdf_type` or `pdf_confidence`, and SHALL NOT add a metadata key.

#### Scenario: Image-only page outside the sample is counted

- **GIVEN** a 20-page PDF that pdf-inspector classifies as `text_based` with no sampled page needing OCR
- **AND** a full page scan finds 3 pages needing OCR
- **WHEN** the adapter emits its documents
- **THEN** `pages_needing_ocr` SHALL be 3

#### Scenario: Short or already complete results get no extra scan

- **GIVEN** a `text_based` PDF with 8 pages or fewer, or a PDF classified `scanned`, `image_based` or `mixed`
- **WHEN** the adapter emits its documents
- **THEN** no page scan SHALL run beyond the one per-page extraction that gives the page text
- **AND** `pages_needing_ocr` SHALL be the count from `process_pdf`, even when the per-page extraction flags a different number

#### Scenario: Full scan failure keeps the sampled evidence

- **GIVEN** a `text_based` PDF longer than 8 pages whose full page scan raises
- **WHEN** the adapter emits its documents
- **THEN** `pages_needing_ocr` SHALL be the sampled count
- **AND** the read SHALL succeed with a logged warning

#### Scenario: Silent-empty rescue records the full-scan count

- **GIVEN** a `text_based` PDF longer than 8 pages with empty Markdown whose fallback tier recovers text
- **WHEN** the adapter emits its documents
- **THEN** `pages_needing_ocr` SHALL be zero
- **AND** `pages_needing_ocr_before_fallback` SHALL be the full-scan count

### Requirement: A page-routed document counts the source of every page

The `page` routing unit SHALL emit one document for each page that has text, in page order, each carrying its `page` and `page_label`. Every emitted document SHALL carry the same scalar counts of native, local-OCR, worker and unresolved pages, which SHALL sum to the page count.

#### Scenario: Page-source counts sum to the page count

- **GIVEN** the `page` routing unit and any ingested PDF
- **WHEN** the adapter emits its documents
- **THEN** the native, local-OCR, worker and unresolved page counts SHALL sum to `page_count` on every document

#### Scenario: OCR pages keep their page numbers

- **GIVEN** the `page` routing unit and a 5-page PDF whose page 3 is read by the local tier and page 4 by the worker
- **WHEN** the adapter emits its documents
- **THEN** the document for page 3 SHALL carry `page` 3 and the local OCR text
- **AND** the document for page 4 SHALL carry `page` 4 and the worker text

#### Scenario: The document unit emits no page-source counts

- **GIVEN** no routing unit is configured
- **WHEN** a PDF is ingested
- **THEN** the emitted metadata SHALL NOT carry the native, local-OCR, worker or unresolved page counts
