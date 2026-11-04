## Purpose

Send pages written in a non-Latin script past the local OCR tier to the OCR engine list under page routing, using only evidence that is cheap and observable, and say plainly what the detector cannot see.

## ADDED Requirements

### Requirement: Non-Latin routing SHALL be injected configuration

The system SHALL read `ocr_non_latin_routing` (env `OCR_NON_LATIN_ROUTING`) from the injected settings. Accepted values SHALL be `off`, `detect` and `always`. The default SHALL be `off`. An unknown value SHALL stop start-up with a message naming the accepted values, because the value feeds the index identity.

#### Scenario: Default

- **WHEN** no source sets the key
- **THEN** the value SHALL be `off`
- **AND** page routing SHALL behave exactly as before this change

#### Scenario: Unknown value

- **WHEN** `OCR_NON_LATIN_ROUTING=arabic` is set
- **THEN** start-up SHALL fail and the message SHALL name `off`, `detect` and `always`

### Requirement: A page is non-Latin only when it has enough letters

The detector SHALL count alphabetic characters in a page text. A page SHALL count as non-Latin only when it holds at least the detector's minimum letter count and at least half of those letters are outside the Latin script. A page with fewer letters SHALL get no verdict. The minimum count and the share SHALL be fixed in the detector with a version number. They SHALL NOT be settings.

#### Scenario: Watermark text gives no verdict

- **GIVEN** a flagged scanned page whose only text items are 7 Latin letters
- **WHEN** the detector runs
- **THEN** it SHALL give no verdict

#### Scenario: Arabic text layer

- **GIVEN** a flagged page whose text items hold 300 letters, 280 of them Arabic
- **WHEN** the detector runs
- **THEN** it SHALL mark the page non-Latin

### Requirement: Detect mode reads only text that already exists

Under `detect` and the `page` unit, the system SHALL run the detector on each flagged page's text items before the local tier. A non-Latin page SHALL skip the local tier and join the one page-listed request to the OCR engine list. The detector SHALL NOT render a page, run OCR or call a model for this check.

#### Scenario: Scanned non-Latin page is not detected before OCR

- **GIVEN** `detect`, the `page` unit and a scanned Arabic page with no text layer
- **WHEN** the PDF is ingested
- **THEN** the page SHALL go to the local tier as before

#### Scenario: Flagged page with an Arabic text layer goes direct

- **GIVEN** `detect`, the `page` unit and a flagged page whose text items are mostly Arabic
- **WHEN** the PDF is ingested
- **THEN** the page SHALL skip the local tier and go to the OCR engine list

### Requirement: Detect mode escalates a non-Latin local OCR result

Under `detect`, a local OCR page result that the detector marks non-Latin SHALL escalate to the OCR engine list with the reason `non_latin_output`, whatever its confidence. The confidence cut SHALL still apply to every other local result.

#### Scenario: Confident non-Latin output escalates

- **GIVEN** `detect` and a local result of 400 Devanagari letters with confidence 0.95
- **WHEN** the post-check runs
- **THEN** the page SHALL escalate with the reason `non_latin_output`

#### Scenario: Latin output follows the cut

- **GIVEN** `detect` and a Latin local result with confidence 0.95
- **WHEN** the post-check runs
- **THEN** the page SHALL keep its local text

### Requirement: Always mode sends every flagged page to the engine

Under `always` and the `page` unit, every flagged page SHALL skip the local tier and join the one page-listed request to the OCR engine list. Unflagged pages SHALL keep native text.

#### Scenario: Known Arabic collection

- **GIVEN** `always`, the `page` unit and a 16-page scan with every page flagged
- **WHEN** the PDF is ingested
- **THEN** all 16 pages SHALL go to the OCR engine list in one request
- **AND** the local tier SHALL NOT run

### Requirement: Non-Latin routing degrades to the local tier

When no engine in the OCR engine list is available before dispatch, pages chosen by non-Latin routing SHALL go through the local tier and its post-check as if the setting were `off`. The system SHALL log one warning per file.

#### Scenario: No engine available

- **GIVEN** `always` and no available OCR engine
- **WHEN** a flagged page is read
- **THEN** the local tier SHALL read it
- **AND** one warning SHALL name the missing engine

### Requirement: Maths and non-Latin pages go direct once

A page that is both a maths page and a non-Latin page SHALL be sent to the OCR engine list once, in the same request.

#### Scenario: Both conditions

- **GIVEN** maths routing on, `always`, and a flagged page with a maths font
- **WHEN** the PDF is ingested
- **THEN** the page SHALL appear once in the page-listed request

### Requirement: Non-Latin routing SHALL participate in the source index identity

With a value other than `off`, the identity SHALL hold a block with the mode and the detector version. With `off`, the block SHALL be absent, so existing digests do not change.

#### Scenario: Turning the setting on reindexes PDF sources

- **GIVEN** a page-unit collection indexed with `off`
- **WHEN** the setting changes to `detect` and an explicit ingest runs
- **THEN** PDF sources SHALL be processed again
- **AND** other sources SHALL keep their digest

#### Scenario: Default install keeps its digest

- **WHEN** an install with `off` computes a source identity
- **THEN** the digest SHALL equal the digest before this change

### Requirement: Non-Latin routing diagnostics SHALL be honest

A PDF document read by page routing SHALL carry `pages_non_latin`, the number of pages sent direct or escalated by this setting, only when the setting is not `off`. The key SHALL be in the central embedding exclusion set. Diagnostics SHALL NOT claim a script for a page that got no verdict.

#### Scenario: Count stamped

- **GIVEN** `detect` and 3 pages escalated with `non_latin_output`
- **WHEN** the document is emitted
- **THEN** `pages_non_latin` SHALL be 3
- **AND** it SHALL NOT appear in the embedded text
