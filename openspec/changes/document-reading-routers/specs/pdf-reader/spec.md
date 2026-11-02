## MODIFIED Requirements

### Requirement: A rescue corrects the routing evidence only when it recovers text

A successful retry SHALL correct the routing evidence it emits: the scalar `pages_needing_ocr` SHALL be set to zero, because the pages were flagged only by the failed extraction, and the pre-fallback flagged count SHALL be preserved under an additive diagnostic key. A retry chain that yields no text from either tier SHALL leave the original pdf-inspector result unchanged so the OCR routing gate still sees the flagged evidence.

When a document router is selected, the zero SHALL be replaced by the router's verdicts: the scalar `pages_needing_ocr` SHALL equal the number of rescued pages the router rejects, and only those pages SHALL go to OCR, page by page. Without a router, the rule above SHALL apply unchanged.

#### Scenario: Recovered text corrects the routing evidence

- **GIVEN** a fallback tier recovers text from a file pdf-inspector flagged page-by-page
- **WHEN** the OCR routing seam reads the emitted metadata
- **THEN** `pages_needing_ocr` SHALL be zero
- **AND** the original flagged count SHALL be preserved under a separate diagnostic key

#### Scenario: Failed retry keeps the original evidence

- **GIVEN** both fallback tiers yield no text
- **WHEN** the adapter emits its document
- **THEN** the emitted result SHALL be the unchanged pdf-inspector result with its original flagged count
- **AND** the OCR routing decision SHALL be unchanged from a run without the guard

#### Scenario: A selected router replaces the zero

- **GIVEN** a selected router and a rescue that recovers text for 44 flagged pages
- **WHEN** the router rejects 40 of them
- **THEN** `pages_needing_ocr` SHALL be 40
- **AND** the original flagged count SHALL be preserved under its diagnostic key
