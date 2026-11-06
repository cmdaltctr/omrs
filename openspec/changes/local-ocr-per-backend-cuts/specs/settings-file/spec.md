## ADDED Requirements

### Requirement: The retired local OCR cut key is reported with its replacement

When `omrs.jsonc` holds `ocr_local_min_confidence`, the value SHALL be ignored and the key SHALL be listed as retired with the replacement `ocr_local_cuts`. The server SHALL start. No cut SHALL change because of the old key.

#### Scenario: Live file holds the old key

- **GIVEN** `omrs.jsonc` holds `"ocr_local_min_confidence": 0.7` and no other source sets a cut
- **WHEN** `omrs web` starts
- **THEN** the server MUST start
- **AND** the problem list MUST name `ocr_local_min_confidence` as retired with the replacement `ocr_local_cuts`
- **AND** the cut of `pp-ocrv6-small` MUST be 0.92

### Requirement: A bad cut map in omrs.jsonc is ignored and listed

When `omrs.jsonc` holds an `ocr_local_cuts` value that is not an object, names a backend that cannot be listed, or holds a value that is not a number from 0 to 1, the whole map SHALL be ignored and listed as invalid by key, never by value. The next source SHALL apply. The server SHALL start.

#### Scenario: Out-of-range cut in the file

- **WHEN** `omrs.jsonc` holds `"ocr_local_cuts": {"pp-ocrv6-small": 1.5}` and `omrs web` starts
- **THEN** the server MUST start with the default cuts
- **AND** the problem list MUST name `ocr_local_cuts` and its rule, and MUST NOT contain `1.5`
