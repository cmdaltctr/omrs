## MODIFIED Requirements

### Requirement: Local OCR tier SHALL escalate pages below a default confidence of 0.9

When `OCR_ROUTING_UNIT=page`, a page the local OCR tier reads SHALL escalate to the worker when its reported confidence is below the effective cut. The effective cut SHALL be the value of `OCR_LOCAL_MIN_CONFIDENCE` when the operator sets it. Otherwise it SHALL be the calibrated cut of the selected local backend, which is 0.9 for the default backend `pp-ocrv6-small`. The tier SHALL keep a page whose confidence is at or above the effective cut, unless the page is empty, has no reported confidence, or carries the backend's hosted recommendation.

#### Scenario: Page below the default cut escalates

- **GIVEN** `page` routing unit, the default backend and no operator value for `OCR_LOCAL_MIN_CONFIDENCE`
- **WHEN** the local tier reads a page with text and confidence 0.85
- **THEN** the page SHALL escalate to the worker

#### Scenario: Page at the default cut stays local

- **GIVEN** `page` routing unit, the default backend and no operator value for `OCR_LOCAL_MIN_CONFIDENCE`
- **WHEN** the local tier reads a page with text, confidence 0.9 and no hosted recommendation
- **THEN** the page SHALL keep its local text

#### Scenario: Operator value replaces the default

- **GIVEN** `OCR_LOCAL_MIN_CONFIDENCE=0.7`
- **WHEN** the local tier reads a page with text and confidence 0.75
- **THEN** the page SHALL keep its local text
