## RENAMED Requirements

- FROM: `### Requirement: Local OCR tier SHALL escalate pages below a default confidence of 0.9`
- TO: `### Requirement: Local OCR tier SHALL escalate pages below the backend's effective cut`

## MODIFIED Requirements

### Requirement: Only unreadable local OCR pages escalate to the OCR routes

A page SHALL escalate to the OCR routes only when no listed local OCR backend keeps it. A backend SHALL NOT keep a page with no text, no confidence or a confidence below its cut, a hosted recommendation, or a post-check reason. Escalated pages SHALL go in one page-listed request to the first available engine in the OCR engine list. The OCR routes SHALL receive only escalated pages and direct pages.

#### Scenario: A page the local tier cannot read escalates

- **GIVEN** the `page` routing unit and a flagged page the local tier returns no text for
- **AND** the worker returns usable, non-empty Markdown for that page
- **WHEN** the PDF is ingested
- **THEN** that page SHALL be sent to the worker
- **AND** the metadata SHALL count it as a worker page

#### Scenario: Unreadable local OCR pages escalate alone

- **GIVEN** the local OCR tier returns no text for 1 of 3 flagged pages
- **AND** an OCR route is available
- **AND** the worker returns usable, non-empty Markdown for the escalated page
- **WHEN** the PDF is ingested
- **THEN** exactly that page SHALL be sent to the worker
- **AND** the metadata SHALL count 1 worker page and 2 local-OCR pages

#### Scenario: Missing worker keeps local OCR text

- **GIVEN** a page escalates and no OCR route is available
- **WHEN** the PDF is ingested
- **THEN** the page SHALL keep the text of the first listed backend that returned non-empty text for it, or native text when no backend did
- **AND** the page SHALL be counted as unresolved without failing the file

#### Scenario: A page the first backend passes on is kept by the second

- **GIVEN** `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small` and a flagged Latin page
- **WHEN** Indra reads the page at confidence 0.80 and PP-OCRv6 reads it at confidence 0.95
- **THEN** the page SHALL NOT be sent to the OCR routes
- **AND** the metadata SHALL count it as a local-OCR page

### Requirement: Local OCR tier SHALL escalate pages below the backend's effective cut

When `OCR_ROUTING_UNIT=page`, a local OCR backend SHALL NOT keep a page whose reported confidence is below that backend's effective cut. The effective cut SHALL be the backend's entry in `ocr_local_cuts` when there is one, else the backend's default cut, which is 0.92 for the default backend `pp-ocrv6-small`. A backend SHALL keep a page at or above its effective cut unless another escalation reason applies.

#### Scenario: Page below the default cut escalates

- **GIVEN** `page` routing unit, the default backend list and an empty `ocr_local_cuts`
- **WHEN** the local tier reads a page with text and confidence 0.91
- **THEN** the page SHALL escalate to the worker

#### Scenario: Page at the default cut stays local

- **GIVEN** `page` routing unit, the default backend list and an empty `ocr_local_cuts`
- **WHEN** the local tier reads a page with text, confidence 0.92 and no hosted recommendation
- **THEN** the page SHALL keep its local text

#### Scenario: Operator value replaces the default

- **GIVEN** `OCR_LOCAL_CUTS={"pp-ocrv6-small": 0.7}`
- **WHEN** the local tier reads a page with text and confidence 0.75
- **THEN** the page SHALL keep its local text

#### Scenario: Each backend uses its own cut

- **GIVEN** `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small` and an empty `ocr_local_cuts`
- **WHEN** Indra reads an Arabic page at confidence 0.95
- **THEN** Indra SHALL keep the page, because its cut is 0.94
