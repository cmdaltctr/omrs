## MODIFIED Requirements

### Requirement: The page may write the document-reading keys

The keys the Settings page may write SHALL include `pdf_readers`, `ocr_engines`, `ocr_fallback_enabled`, `ocr_routing_unit` and `ocr_maths_routing_enabled`. `null` SHALL remove the key. The removed keys `ocr_fallback_min_confidence`, `ocr_fallback_page_fraction` and `ocr_maths_page_fraction` SHALL NOT be writable; a write of any of them SHALL be refused naming its removal.

#### Scenario: Valid reader written

- **WHEN** the page writes `pdf_readers` `["liteparse"]`
- **THEN** `omrs.jsonc` MUST hold `"pdf_readers": ["liteparse"]` and every other byte of the file MUST stay as it was

#### Scenario: Removed gate key refused

- **WHEN** the page writes `ocr_fallback_page_fraction` `0.2`
- **THEN** the write MUST be refused naming the removed key and the file MUST NOT change

### Requirement: A page write checks reader and engine names

A page write of a document-reading key SHALL check the value before it writes: each `pdf_readers` entry SHALL be one of `liteparse`, `pdf_inspector`, `pypdfium2` and `pypdf`; each `ocr_engines` name SHALL start with a letter or digit, SHALL hold only letters, digits, dots, hyphens and underscores, and SHALL be at most 64 characters. A list SHALL NOT be empty, hold a duplicate, or hold `auto`.

#### Scenario: Unknown reader refused on write

- **WHEN** the page writes `pdf_readers` `["pdfminer"]`
- **THEN** the write MUST be refused with "pdf_readers: The value must be one of: liteparse, pdf_inspector, pypdfium2, pypdf." and the file MUST NOT change

#### Scenario: Engine name with a path

- **WHEN** the page writes `ocr_engines` `["../other"]`
- **THEN** the write MUST be refused with the engine name rule and the file MUST NOT change

#### Scenario: Empty, duplicate and auto lists refused

- **WHEN** the page writes `pdf_readers` as `[]`, as `["pypdf", "pypdf"]` or as `["auto"]`
- **THEN** each write MUST be refused and the file MUST NOT change

### Requirement: A page write checks boolean, unit and blank values

A page write of a document-reading key SHALL also check the value before it writes: a boolean key SHALL take only `true` or `false`; `ocr_routing_unit` SHALL be `page`; and a blank text value or a blank list entry SHALL be refused.

#### Scenario: Blank engine name refused

- **WHEN** the page writes `ocr_engines` as `["dots-mocr", ""]`
- **THEN** the write MUST be refused naming `ocr_engines` and the blank rule, and the file MUST NOT change

#### Scenario: Text where a boolean is expected

- **WHEN** the page writes `ocr_fallback_enabled` as the text `"true"`
- **THEN** the write MUST be refused with "ocr_fallback_enabled: The value must be true or false." and the file MUST NOT change

#### Scenario: Document unit refused

- **WHEN** the page writes `ocr_routing_unit` `document`
- **THEN** the write MUST be refused with a message naming `page` as the only routing unit and the file MUST NOT change

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

### Requirement: The page does not write the old reading keys

A write of `pdf_reader`, `ocr_engine_primary` or `ocr_engine_fallback` SHALL be refused, naming the list key that replaces it. The page SHALL remove these keys from `omrs.jsonc` only as part of a list save.

#### Scenario: Old engine key refused

- **WHEN** the page writes `ocr_engine_fallback` `paddleocr-vl`
- **THEN** the write MUST be refused naming `ocr_engines` and the file MUST NOT change
