## ADDED Requirements

### Requirement: List settings hold an array of names

`omrs.jsonc` SHALL accept `pdf_readers` and `ocr_engines` as JSON arrays of strings. The environment and `.env` SHALL accept `PDF_READERS` and `OCR_ENGINES` as comma-separated names, with spaces trimmed. A file value that is not an array of strings SHALL be ignored and listed as a problem. The environment SHALL lock a list field, as it locks other fields.

#### Scenario: File array

- **GIVEN** `omrs.jsonc` holds `"ocr_engines": ["dots-mocr", "paddleocr-vl"]`
- **WHEN** settings resolve
- **THEN** `ocr_engines` SHALL be that list with source `config-file`

#### Scenario: Wrong type in the file

- **GIVEN** `omrs.jsonc` holds `"pdf_readers": "pypdf"`
- **WHEN** settings resolve
- **THEN** the value SHALL be ignored and listed as a problem naming the key

### Requirement: Old single-value reading keys are read and replaced on save

The settings reader SHALL keep reading `pdf_reader`, `ocr_engine_primary` and `ocr_engine_fallback` from every source, with no retirement tripwire. When a source sets a list key and an old key, the list key SHALL win within that source and the old key SHALL be listed as ignored. A Settings page save of a list SHALL write the list key and remove the matching old keys from `omrs.jsonc` in the same atomic write, keeping comments.

#### Scenario: Old file key still applies

- **GIVEN** `omrs.jsonc` holds `"pdf_reader": "pypdf"` and no `pdf_readers`
- **WHEN** settings resolve
- **THEN** `pdf_readers` SHALL be `("pypdf",)`

#### Scenario: Save replaces the old keys

- **GIVEN** `omrs.jsonc` holds `"ocr_engine_primary": "dots-mocr"` and `"ocr_engine_fallback": "paddleocr-vl"`
- **WHEN** the user saves the engine list on the page
- **THEN** the file SHALL hold `ocr_engines` and neither old key

#### Scenario: Old environment name does not stop start-up

- **GIVEN** `PDF_READER=liteparse` in the environment
- **WHEN** the server starts
- **THEN** start-up SHALL succeed and `pdf_readers` SHALL be `("liteparse",)`
