## ADDED Requirements

### Requirement: Document reading shows non-Latin routing

Settings › Document reading SHALL show `ocr_non_latin_routing` in the "When to use OCR" block as a choice of `off`, `detect` and `always`. The row SHALL say that `detect` sees only text that already exists and does not catch scanned pages, that `always` suits a collection known to be non-Latin, and that the setting acts only under the `page` routing unit. It SHALL follow the restart, lock and identity rules of the other Document reading rows.

#### Scenario: Row under the document unit

- **GIVEN** the routing unit is `document`
- **WHEN** the row renders
- **THEN** it SHALL say the setting has no effect until the routing unit is `page`

#### Scenario: Save always

- **WHEN** the user chooses `always` and saves
- **THEN** `omrs.jsonc` SHALL hold `"ocr_non_latin_routing": "always"`
- **AND** the row SHALL show "Restart to apply"
