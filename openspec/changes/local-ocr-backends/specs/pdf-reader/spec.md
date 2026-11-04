## MODIFIED Requirements

### Requirement: Only unreadable local OCR pages escalate to the OCR routes

A page SHALL escalate to the OCR routes only when no listed local OCR backend keeps it. A backend SHALL NOT keep a page when it returns no text or only whitespace, reports no confidence or a confidence below its effective cut, recommends hosted OCR, gets a post-check reason from a page rule, or returns an output script it may not keep. Escalated pages SHALL go in one page-listed request to the first available engine in the OCR engine list. The OCR routes SHALL receive only escalated pages and direct pages.

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
- **WHEN** Indra's output script is Latin and PP-OCRv6 reads the page at confidence 0.95
- **THEN** the page SHALL NOT be sent to the OCR routes
- **AND** the metadata SHALL count it as a local-OCR page

### Requirement: Local OCR tier SHALL escalate pages below a default confidence of 0.9

When `OCR_ROUTING_UNIT=page`, a local OCR backend SHALL NOT keep a page whose reported confidence is below that backend's effective cut. The effective cut SHALL be the value of `OCR_LOCAL_MIN_CONFIDENCE` when the operator sets it, for every listed backend. Otherwise it SHALL be the backend's own calibrated cut, which is 0.9 for the default backend `pp-ocrv6-small`. A backend SHALL keep a page whose confidence is at or above its effective cut, unless the page is empty, has no reported confidence, carries the hosted recommendation, gets a post-check reason, or has an output script the backend may not keep.

#### Scenario: Page below the default cut escalates

- **GIVEN** `page` routing unit, the default backend list and no operator value for `OCR_LOCAL_MIN_CONFIDENCE`
- **WHEN** the local tier reads a page with text and confidence 0.85
- **THEN** the page SHALL escalate to the worker

#### Scenario: Page at the default cut stays local

- **GIVEN** `page` routing unit, the default backend list and no operator value for `OCR_LOCAL_MIN_CONFIDENCE`
- **WHEN** the local tier reads a page with text, confidence 0.9 and no hosted recommendation
- **THEN** the page SHALL keep its local text

#### Scenario: Operator value replaces the default

- **GIVEN** `OCR_LOCAL_MIN_CONFIDENCE=0.7`
- **WHEN** the local tier reads a page with text and confidence 0.75
- **THEN** the page SHALL keep its local text

#### Scenario: Each backend uses its own cut

- **GIVEN** `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small` and no operator value for `OCR_LOCAL_MIN_CONFIDENCE`
- **WHEN** Indra reads an Arabic page at confidence 0.91
- **THEN** Indra SHALL keep the page, because its cut is 0.90

### Requirement: A missing local OCR runtime sends flagged pages to the worker engine

When no listed local OCR backend can run (each one is not installed, has no model, or is switched off for the process), the page unit SHALL send every flagged page to the OCR routes in one page-listed request. Flagged pages SHALL NOT keep their native text as a fallback for a missing runtime, because a junk native text layer would then survive unseen (issue #161). When at least one listed backend can run, the pages SHALL go to the backends that can run, in list order. A worker failure after dispatch SHALL keep the existing per-file error boundary.

#### Scenario: No local runtime, worker available

- **GIVEN** the `page` routing unit, a PDF with flagged pages, and no usable local OCR backend
- **AND** the primary OCR route is available
- **WHEN** the PDF is ingested
- **THEN** the flagged pages SHALL be parsed by the OCR routes
- **AND** the flagged pages SHALL NOT keep native text

#### Scenario: No local runtime and no OCR route

- **GIVEN** the `page` routing unit, a PDF with flagged pages, no usable local OCR backend and no available OCR route
- **WHEN** the PDF is ingested
- **THEN** the flagged pages SHALL keep their best available text and count unresolved
- **AND** one warning SHALL name both missing tiers

#### Scenario: One backend switched off, the next one runs

- **GIVEN** `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small` and Indra switched off for the process
- **WHEN** a PDF with flagged pages is ingested
- **THEN** PP-OCRv6 SHALL read the flagged pages
