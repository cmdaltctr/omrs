# Spec Delta

## ADDED Requirements

### Requirement: The maths routing flag SHALL be injected configuration

The maths routing enable flag SHALL be a top-level effective-settings field, resolved once at the composition root and enabled by default. Maths routing SHALL have no page fraction: every flagged maths page goes to the OCR routes. A stale `ocr_maths_page_fraction` SHALL be refused as the scenarios state.

#### Scenario: The flag is read from injected settings

- **WHEN** the page unit decides whether flagged maths pages skip the local OCR tier
- **THEN** it SHALL read the enable flag from the injected effective settings

#### Scenario: A stale maths page fraction is refused

- **GIVEN** `OCR_MATHS_PAGE_FRACTION` in the environment
- **WHEN** settings are resolved at start-up
- **THEN** the start-up SHALL fail with a message naming the removed key

#### Scenario: A stale maths page fraction in the settings file is not read

- **GIVEN** `"ocr_maths_page_fraction": 0.2` in the settings file
- **WHEN** settings are resolved at start-up
- **THEN** the settings-file problem list SHALL name the key as retired
- **AND** no settings field SHALL hold the value

## MODIFIED Requirements

### Requirement: Maths routing SHALL participate in the source index identity

The existing source index identity SHALL include a maths-routing block: the resolved enable flag and the detector version. The block SHALL be present for every source.

#### Scenario: A detector change triggers re-ingestion

- **GIVEN** a previously indexed, byte-identical PDF
- **WHEN** the detector version changes
- **THEN** the source SHALL NOT be reported as `skipped_unchanged`

#### Scenario: Toggling maths routing triggers re-ingestion

- **GIVEN** a previously indexed, byte-identical PDF
- **WHEN** maths routing is turned off
- **THEN** the source SHALL NOT be reported as `skipped_unchanged`

#### Scenario: Unchanged maths routing inputs still skip

- **GIVEN** a previously indexed, byte-identical source
- **WHEN** it is ingested again with every source index identity input unchanged, maths-routing inputs included
- **THEN** it SHALL be reported as `skipped_unchanged`

## REMOVED Requirements

### Requirement: The document unit sends a maths-heavy PDF whole to the OCR routes

**Reason**: The document unit is removed (change page-routing-default). Under the page unit, each flagged maths page goes to the OCR routes on its own.

### Requirement: Maths routing SHALL be injected configuration

**Reason**: Replaced by "The maths routing flag SHALL be injected configuration". The document-unit maths page fraction is removed, so the fraction scenario no longer holds.
