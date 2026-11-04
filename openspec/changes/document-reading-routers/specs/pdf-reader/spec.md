## MODIFIED Requirements

### Requirement: Page-level OCR routing SHALL OCR only flagged pages

When OCR is enabled, the pdf-inspector path SHALL decide OCR need per page from a scan of every page. Pages that do not need OCR SHALL keep native pdf-inspector Markdown, except a page that a page rule adds to the route (for example a page that a selected router rejects). Pages that need OCR, and added pages, SHALL be processed by the local OCR tier. A missing local runtime SHALL follow the missing-runtime requirement instead of keeping native text.

#### Scenario: Only flagged pages are OCRed

- **GIVEN** a 20-page PDF with 3 pages needing OCR
- **WHEN** the PDF is ingested
- **THEN** the 17 other pages SHALL keep native Markdown
- **AND** only the 3 flagged pages SHALL be processed by the local OCR tier

#### Scenario: Missing local OCR runtime sends flagged pages to the OCR routes

- **GIVEN** no usable local OCR runtime and a PDF with flagged pages
- **WHEN** the PDF is ingested
- **THEN** the flagged pages SHALL be parsed by the OCR routes under the missing-runtime requirement
- **AND** the flagged pages SHALL NOT keep native text while any OCR route is available

#### Scenario: A rejected unflagged page is OCRed

- **GIVEN** a 20-page PDF with no flagged page and a selected router that rejects page 7
- **WHEN** the PDF is ingested
- **THEN** page 7 SHALL be processed by the local OCR tier
- **AND** the 19 other pages SHALL keep native Markdown

### Requirement: The scalar OCR diagnostics keep their meaning

The four existing OCR diagnostics SHALL remain scalars and SHALL keep their meaning. `ocr_required` SHALL be true when at least one page was flagged, goes direct to the worker or was added to the route by a page rule. `ocr_used` SHALL be true when OCR produced the text of at least one page, by either tier. `pages_needing_ocr` SHALL remain the count of flagged pages, which does not include pages that a page rule added.

#### Scenario: Page routing keeps the scalar OCR diagnostics

- **GIVEN** a PDF with at least one flagged page
- **WHEN** OCR produces the text of at least one page
- **THEN** `ocr_required` and `ocr_used` SHALL be true
- **AND** `pages_needing_ocr` SHALL be the count of flagged pages

#### Scenario: An added page does not change the flagged count

- **GIVEN** a PDF with 2 flagged pages and 1 page that a router rejects
- **WHEN** OCR reads all 3 pages
- **THEN** `pages_needing_ocr` SHALL be 2
- **AND** `ocr_required` SHALL be true
