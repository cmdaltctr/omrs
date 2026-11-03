# Spec Delta

## ADDED Requirements

### Requirement: The routing unit is `page`

The `page` routing unit SHALL be the default and the only routing unit. A configuration or environment value of `document` for `ocr_routing_unit` SHALL fail at start-up with a message that names `page` as the routing unit in force. No other value SHALL be accepted.

#### Scenario: A stale document value is refused

- **GIVEN** `OCR_ROUTING_UNIT=document` or `"ocr_routing_unit": "document"` in the settings file
- **WHEN** settings are resolved at start-up
- **THEN** the start-up SHALL fail with a message naming `page` as the only routing unit

#### Scenario: No value resolves to page

- **GIVEN** no `ocr_routing_unit` value is configured
- **WHEN** a PDF is ingested
- **THEN** routing SHALL follow the page-level OCR routing requirement

### Requirement: A missing local OCR runtime sends flagged pages to the worker engine

When the local OCR model or runtime is unavailable, the page unit SHALL send every flagged page to the OCR routes in one page-listed request. Flagged pages SHALL NOT keep their native text as a fallback for a missing runtime, because a junk native text layer would then survive unseen (issue #161). A worker failure after dispatch SHALL keep the existing per-file error boundary.

#### Scenario: No local runtime, worker available

- **GIVEN** the `page` routing unit, a PDF with flagged pages, and no usable local OCR runtime
- **AND** the primary OCR route is available
- **WHEN** the PDF is ingested
- **THEN** the flagged pages SHALL be parsed by the OCR routes
- **AND** the flagged pages SHALL NOT keep native text

#### Scenario: No local runtime and no OCR route

- **GIVEN** the `page` routing unit, a PDF with flagged pages, no usable local OCR runtime and no available OCR route
- **WHEN** the PDF is ingested
- **THEN** the flagged pages SHALL keep their best available text and count unresolved
- **AND** one warning SHALL name both missing tiers

### Requirement: Adopting page routing re-indexes every source once

The OCR routing payload SHALL drop the gate values (`min_confidence`, `page_fraction`) and the unconditional routing types, the unit-scoped key subtraction SHALL be removed, and the identity schema SHALL advance from 6 to 7. Every source indexed before this change SHALL be re-indexed on its next ingest.

#### Scenario: A source indexed before the change reprocesses

- **GIVEN** a source indexed before this change, under any settings
- **WHEN** it is ingested again after this change
- **THEN** the source SHALL be re-indexed

### Requirement: Page-level OCR routing SHALL OCR only flagged pages

When OCR is enabled, the pdf-inspector path SHALL decide OCR need per page from a scan of every page. Pages that do not need OCR SHALL keep native pdf-inspector Markdown. Pages that need OCR SHALL be processed by the local OCR tier. A missing local runtime SHALL follow the missing-runtime requirement instead of keeping native text.

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

### Requirement: Every PDF document counts the source of every page

The PDF reader SHALL emit one document for each page that has text, in page order, each carrying its `page` and `page_label`. Every emitted document SHALL carry the same scalar counts of native, local-OCR, worker, blank and unresolved pages, which SHALL sum to the page count.

#### Scenario: Page-source counts sum to the page count

- **GIVEN** any ingested PDF
- **WHEN** the adapter emits its documents
- **THEN** the native, local-OCR, worker, blank and unresolved page counts SHALL sum to `page_count` on every document

#### Scenario: OCR pages keep their page numbers

- **GIVEN** a 5-page PDF whose page 3 is read by the local tier and page 4 by the worker
- **WHEN** the adapter emits its documents
- **THEN** the document for page 3 SHALL carry `page` 3 and the local OCR text
- **AND** the document for page 4 SHALL carry `page` 4 and the worker text

#### Scenario: No configured unit still counts every page

- **GIVEN** no routing unit is configured
- **WHEN** a PDF is ingested
- **THEN** the emitted metadata SHALL carry the native, local-OCR, worker, blank and unresolved page counts

### Requirement: The blank test SHALL participate in the index identity

The blank test version SHALL enter the source index identity for every source. `ocr_pages_blank` SHALL be in the central embedding exclusion set.

#### Scenario: A blank test version change re-indexes

- **GIVEN** a source indexed under one blank test version
- **WHEN** it is ingested again under a different blank test version
- **THEN** the source SHALL be re-indexed

### Requirement: Metadata keys enter the index identity for every source

A metadata key in the centrally owned exclusion set SHALL contribute to `embedding_text.excluded_keys` in the source index identity for every source, with no subtraction by routing unit, because the page unit is the only unit and every install can emit its keys.

#### Scenario: Every install includes the page-source counts

- **GIVEN** any install
- **WHEN** a source index identity is computed
- **THEN** the page-source counts SHALL contribute to `embedding_text.excluded_keys`

### Requirement: Changing the local cut re-indexes sources

The index identity SHALL change when the effective local cut changes, so that sources read under a different cut are re-indexed.

#### Scenario: Sources re-index when the default changes

- **GIVEN** a source indexed with the previous default cut of 0.8
- **WHEN** the source is ingested again under the default cut of 0.9
- **THEN** the source SHALL be re-indexed

## RENAMED Requirements

- FROM: `### Requirement: The scalar OCR diagnostics keep their document-unit meaning`
- TO: `### Requirement: The scalar OCR diagnostics keep their meaning`

## MODIFIED Requirements

### Requirement: The scalar OCR diagnostics keep their meaning

The four existing OCR diagnostics SHALL remain scalars and SHALL keep their meaning. `ocr_required` SHALL be true when at least one page was flagged or goes direct to the worker. `ocr_used` SHALL be true when OCR produced the text of at least one page, by either tier. `pages_needing_ocr` SHALL remain the count of flagged pages.

#### Scenario: Page routing keeps the scalar OCR diagnostics

- **GIVEN** a PDF with at least one flagged page
- **WHEN** OCR produces the text of at least one page
- **THEN** `ocr_required` and `ocr_used` SHALL be true
- **AND** `pages_needing_ocr` SHALL be the count of flagged pages

### Requirement: pdf-inspector SHALL route OCR-required PDFs to an isolated document-understanding worker

When the configured PDF path uses `pdf_inspector`, the system SHALL use the `pdf-inspector` result as both the fast extraction result and the evidence for which pages need OCR. Pages that need OCR SHALL go to the local tier and the OCR routes under the page-level routing requirements. Text-based PDFs with no flagged pages and no maths pages SHALL dispatch no OCR request.

#### Scenario: Clean text-based PDF stays on pdf-inspector without starting the parsing worker

- **GIVEN** `pdf_inspector` is the configured PDF path and the OCR worker is available
- **AND** `pdf-inspector` classifies the PDF as text-based and flags no page
- **AND** the PDF has no maths pages
- **WHEN** the PDF is ingested
- **THEN** the `pdf-inspector` Markdown SHALL be used
- **AND** no OCR parse request SHALL be dispatched
- **AND** the long-lived worker and its model SHALL NOT be started

### Requirement: OCR dispatch uses the primary route before the fallback route

Every dispatch SHALL use the primary OCR route (dots.mocr by default), and the fallback route (PaddleOCR-VL by default) when the primary is unavailable before dispatch.

#### Scenario: OCR required but the worker is unavailable

- **GIVEN** flagged or escalated pages exist
- **AND** both OCR routes are absent, unprovisioned, incompatible, or unusable before dispatch
- **WHEN** the PDF is ingested
- **THEN** the system SHALL retain the best available text rather than fabricate missing content
- **AND** the document/file result SHALL report that OCR was required but unavailable
- **AND** ingestion SHALL remain within the existing per-file degradation boundary

### Requirement: Layout complexity alone does not route a PDF to OCR

Layout complexity alone SHALL NOT flag a page for OCR. A text-based multi-column or table-heavy page that `pdf-inspector` extracts acceptably SHALL remain native, unless it is a maths page.

#### Scenario: Complex text layout does not imply OCR

- **GIVEN** a text-based PDF containing multiple columns or tables and no maths pages
- **AND** `pdf-inspector` extracts the layout with acceptable quality
- **WHEN** the PDF is ingested
- **THEN** every page SHALL remain on the `pdf-inspector` path
- **AND** layout complexity alone SHALL NOT start or invoke the OCR worker

### Requirement: The page-source counts stay in the central exclusion set

The page-source counts SHALL remain in the one centrally owned exclusion set for every source; a second list held by the PDF reader would exclude them from embedding text while moving no identity at all.

#### Scenario: The PDF reader holds no second exclusion list

- **WHEN** embedding text is built
- **THEN** the page-source counts SHALL be excluded through the centrally owned exclusion set
- **AND** the PDF reader SHALL hold no second list of them

## REMOVED Requirements

### Requirement: Scanned PDFs always route to OCR and other PDFs route by threshold

**Reason**: The document-unit gate; every page is now judged by the page scan.

### Requirement: The document routing unit sends the whole PDF to the worker

**Reason**: The document unit is removed.

### Requirement: The OCR routing gate SHALL be calibrated evidence expressed as injected configuration

**Reason**: The gate is deleted; its calibration record stays in the ADRs and experiments.

### Requirement: The routing gate is calibrated on fixtures disjoint from evaluation

**Reason**: The gate is deleted; its calibration record stays in the ADRs and experiments.

### Requirement: Packaged routing defaults ship the promoted gate

**Reason**: There is no gate to ship defaults for.

### Requirement: The document unit stamps OCR diagnostics on every page document

**Reason**: The document unit is removed.

### Requirement: A worker-read document carries no page provenance

**Reason**: The whole-PDF worker document is removed with the document unit; page-routed worker text keeps its page number.

### Requirement: The page-source counts are keys only the page unit emits

**Reason**: The page unit is the only unit; the central-exclusion requirement covers the keys.

### Requirement: Page-level OCR routing SHALL OCR only pages that need it

**Reason**: Replaced by "Page-level OCR routing SHALL OCR only flagged pages"; its document-unit and native-text fallback scenarios no longer hold.

### Requirement: A page-routed document counts the source of every page

**Reason**: Replaced by "Every PDF document counts the source of every page"; the document-unit scenario no longer holds.

### Requirement: The blank test SHALL participate in the page-unit index identity

**Reason**: Replaced by "The blank test SHALL participate in the index identity".

### Requirement: Unit-scoped metadata keys SHALL enter the index identity only under their unit

**Reason**: Replaced by "Metadata keys enter the index identity for every source".

### Requirement: Changing the local cut re-indexes page-unit sources only

**Reason**: Replaced by "Changing the local cut re-indexes sources".
