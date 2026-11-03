# Spec Delta

## MODIFIED Requirements

### Requirement: A page-routed document counts the source of every page

The `page` routing unit SHALL emit one document for each page that has text, in page order, each carrying its `page` and `page_label`. Every emitted document SHALL carry the same scalar counts of native, local-OCR, worker, blank and unresolved pages, which SHALL sum to the page count.

#### Scenario: Page-source counts sum to the page count

- **GIVEN** the `page` routing unit and any ingested PDF
- **WHEN** the adapter emits its documents
- **THEN** the native, local-OCR, worker, blank and unresolved page counts SHALL sum to `page_count` on every document

#### Scenario: OCR pages keep their page numbers

- **GIVEN** the `page` routing unit and a 5-page PDF whose page 3 is read by the local tier and page 4 by the worker
- **WHEN** the adapter emits its documents
- **THEN** the document for page 3 SHALL carry `page` 3 and the local OCR text
- **AND** the document for page 4 SHALL carry `page` 4 and the worker text

#### Scenario: The document unit emits no page-source counts

- **GIVEN** no routing unit is configured
- **WHEN** a PDF is ingested
- **THEN** the emitted metadata SHALL NOT carry the native, local-OCR, worker, blank or unresolved page counts

## ADDED Requirements

### Requirement: Blank flagged pages SHALL skip both OCR tiers

Under the `page` unit, the system SHALL test every flagged page for blankness after flagging and before the local tier. A blank page SHALL NOT be sent to the local tier or to any OCR route. It SHALL keep its native text, SHALL be counted in `ocr_pages_blank`, and SHALL emit a page document only when that native text is not empty. Unflagged pages SHALL NOT be tested.

#### Scenario: A blank sheet costs no OCR

- **GIVEN** the `page` routing unit and a flagged page that is an empty sheet of scanned paper
- **WHEN** the PDF is ingested
- **THEN** the local tier and the OCR routes SHALL NOT receive that page
- **AND** `ocr_pages_blank` SHALL count it
- **AND** `ocr_pages_unresolved` SHALL NOT count it

#### Scenario: A page with content is not blank

- **GIVEN** the `page` routing unit and a flagged page of faint handwriting, of non-Latin script, or with one printed dark 12 pt word
- **WHEN** the PDF is ingested
- **THEN** the page SHALL follow the local tier and escalation path as before

### Requirement: The blank test SHALL read the page image only

The blank test SHALL decide from the rendered page image. It SHALL NOT use OCR output, the local tier's confidence, or the length of native text as its verdict. A mark connected to the edge of the rendered image, such as a scanner frame or the edge of a smaller sheet, SHALL NOT count as content.

#### Scenario: Empty local OCR text is not a blank verdict

- **GIVEN** a flagged page with Devanagari script that the local tier cannot read
- **WHEN** the blank test runs
- **THEN** the page SHALL NOT be blank

#### Scenario: A small sheet on a dark scanner background

- **GIVEN** a flagged page that shows an empty sheet on a dark scanner background
- **WHEN** the blank test runs
- **THEN** the page SHALL be blank

### Requirement: A page the blank test cannot measure SHALL NOT be blank

When the page cannot be rendered or measured, the system SHALL treat it as not blank and route it as before. It SHALL log one warning for each file and SHALL NOT fail the file.

#### Scenario: Render failure keeps today's route

- **GIVEN** the `page` routing unit and a flagged page whose render raises an error
- **WHEN** the PDF is ingested
- **THEN** the page SHALL go to the local tier as before
- **AND** the file SHALL NOT fail

### Requirement: The blank test has no setting

The blank test SHALL have no setting or option. Its threshold SHALL be a code constant with a version number.

#### Scenario: No configuration key

- **WHEN** an operator lists the OCR settings
- **THEN** no setting SHALL enable, disable or tune the blank test

### Requirement: The blank test SHALL participate in the page-unit index identity

The blank test version SHALL enter the source index identity under the `page` unit only. `ocr_pages_blank` SHALL join the central embedding exclusion set and the page-routing-only keys. A `document`-unit source SHALL keep the identity it has.

#### Scenario: Page-unit sources reindex once

- **GIVEN** a source indexed under the `page` unit before this change
- **WHEN** it is ingested again after this change
- **THEN** the source SHALL be re-indexed

#### Scenario: Document-unit sources keep their identity

- **GIVEN** a source indexed under the default `document` unit before this change
- **WHEN** it is ingested again after this change
- **THEN** the source SHALL NOT be reprocessed
