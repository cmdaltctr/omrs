## MODIFIED Requirements

### Requirement: Document reading shows the reading settings and their state

The Document reading section SHALL show one row for each of `pdf_readers`, `ocr_fallback_enabled`, `ocr_routing_unit`, `ocr_engines`, `ocr_maths_routing_enabled` and `ocr_non_latin_routing`. Each row SHALL show the value in force since launch, its source and the default. When the saved file value differs from the value in force, the row SHALL show the saved value and "Restart to apply".

#### Scenario: Value saved but not yet in force

- **WHEN** the server launched with `pdf_reader` `auto` and `omrs.jsonc` now holds `"pdf_reader": "liteparse"`
- **THEN** the PDF reader row MUST show `auto` in force, `liteparse` saved and "Restart to apply"

## ADDED Requirements

### Requirement: Document reading shows non-Latin routing

Settings › Document reading SHALL show `ocr_non_latin_routing` in the "When to use OCR" block as a choice of `off`, `detect` and `always`. The row SHALL say that `detect` sees only text that already exists and does not catch scanned pages, and that `always` suits a collection known to be non-Latin. It SHALL follow the restart, lock and identity rules of the other Document reading rows.

#### Scenario: Row explains what detect cannot see

- **WHEN** the row renders
- **THEN** it SHALL say that `detect` does not catch scanned pages and SHALL name `always` for a known non-Latin collection

#### Scenario: Save always

- **WHEN** the user chooses `always` and saves
- **THEN** `omrs.jsonc` SHALL hold `"ocr_non_latin_routing": "always"`
- **AND** the row SHALL show "Restart to apply"
