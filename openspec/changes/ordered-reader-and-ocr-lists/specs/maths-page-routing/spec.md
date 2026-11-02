## MODIFIED Requirements

### Requirement: Maths pages fall back when the primary route is missing

If the first engine of the OCR engine list is unavailable before dispatch, the flagged pages SHALL go in one request to the next available engine in the list. If every engine is unavailable, the pages SHALL keep native text and SHALL count as unresolved. A page for which the engine returns empty Markdown SHALL keep native text and SHALL count as unresolved.

#### Scenario: A missing primary engine falls back

- **GIVEN** the `page` routing unit, 4 flagged maths pages, an unavailable first engine and an available second engine
- **WHEN** the PDF is ingested
- **THEN** the 4 pages SHALL go to the second engine in one request

#### Scenario: No engine keeps native text

- **GIVEN** the `page` routing unit, 4 flagged maths pages and no available engine
- **WHEN** the PDF is ingested
- **THEN** the 4 pages SHALL keep native text
- **AND** they SHALL count as unresolved
