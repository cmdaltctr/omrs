## MODIFIED Requirements

### Requirement: The page may write the document-reading keys

The keys the Settings page may write SHALL include `pdf_readers`, `ocr_engines`, `ocr_fallback_enabled`, `ocr_routing_unit`, `ocr_maths_routing_enabled` and `ocr_non_latin_routing`. `null` SHALL remove the key. The removed keys `ocr_fallback_min_confidence`, `ocr_fallback_page_fraction` and `ocr_maths_page_fraction` SHALL NOT be writable; a write of any of them SHALL be refused naming its removal.

#### Scenario: Valid reader written

- **WHEN** the page writes `pdf_readers` `["liteparse"]`
- **THEN** `omrs.jsonc` MUST hold `"pdf_readers": ["liteparse"]` and every other byte of the file MUST stay as it was

#### Scenario: Removed gate key refused

- **WHEN** the page writes `ocr_fallback_page_fraction` `0.2`
- **THEN** the write MUST be refused naming the removed key and the file MUST NOT change

#### Scenario: Unknown non-Latin routing value refused on write

- **WHEN** the page writes `ocr_non_latin_routing` `"arabic"`
- **THEN** the write MUST be refused with "ocr_non_latin_routing: The value must be one of: off, detect, always." and the file MUST NOT change
