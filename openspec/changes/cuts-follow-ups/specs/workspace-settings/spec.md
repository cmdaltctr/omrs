## ADDED Requirements

### Requirement: The retired cut key notice respects the environment lock

When `omrs.jsonc` holds `ocr_local_min_confidence` and `OCR_LOCAL_CUTS` locks the cuts, the notice SHALL NOT show the "Remove it" button. It SHALL say that `OCR_LOCAL_CUTS` is set in the environment or `.env`, and that the operator removes `ocr_local_min_confidence` from `omrs.jsonc` by hand.

#### Scenario: Locked cuts

- **GIVEN** `omrs.jsonc` holds `ocr_local_min_confidence` and `OCR_LOCAL_CUTS` is set in the environment
- **WHEN** the Local OCR group renders
- **THEN** the notice MUST show without a "Remove it" button
- **AND** it MUST name `OCR_LOCAL_CUTS` and tell the operator to remove the key from `omrs.jsonc` by hand
