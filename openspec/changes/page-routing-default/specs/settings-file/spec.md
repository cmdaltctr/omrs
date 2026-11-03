# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: A page write checks boolean, fraction, unit and blank values`
- TO: `### Requirement: A page write checks boolean, unit and blank values`

## MODIFIED Requirements

### Requirement: The page may write the document-reading keys

The keys the Settings page may write SHALL include `pdf_reader`, `ocr_fallback_enabled`, `ocr_routing_unit`, `ocr_engine_primary`, `ocr_engine_fallback` and `ocr_maths_routing_enabled`. `null` SHALL remove the key. The removed keys `ocr_fallback_min_confidence`, `ocr_fallback_page_fraction` and `ocr_maths_page_fraction` SHALL NOT be writable; a write of any of them SHALL be refused naming its removal.

#### Scenario: Valid reader written

- **WHEN** the page writes `pdf_reader` `liteparse`
- **THEN** `omrs.jsonc` MUST hold `"pdf_reader": "liteparse"` and every other byte of the file MUST stay as it was

#### Scenario: Removed gate key refused

- **WHEN** the page writes `ocr_fallback_page_fraction` `0.2`
- **THEN** the write MUST be refused naming the removed key and the file MUST NOT change

### Requirement: A page write checks boolean, unit and blank values

A page write of a document-reading key SHALL also check the value before it writes: a boolean key SHALL take only `true` or `false`; `ocr_routing_unit` SHALL be `page`; and a blank text value SHALL be refused.

#### Scenario: Blank engine name refused

- **WHEN** the page writes `ocr_engine_fallback` as an empty string
- **THEN** the write MUST be refused with "ocr_engine_fallback: The value must not be blank. Send null to use the default." and the file MUST NOT change

#### Scenario: Text where a boolean is expected

- **WHEN** the page writes `ocr_fallback_enabled` as the text `"true"`
- **THEN** the write MUST be refused with "ocr_fallback_enabled: The value must be true or false." and the file MUST NOT change

#### Scenario: Document unit refused

- **WHEN** the page writes `ocr_routing_unit` `document`
- **THEN** the write MUST be refused with a message naming `page` as the only routing unit and the file MUST NOT change
