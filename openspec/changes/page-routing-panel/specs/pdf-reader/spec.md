## ADDED Requirements

### Requirement: The blank test SHALL have one on/off switch and no tuning

The setting `ocr_skip_blank_pages` (environment `OCR_SKIP_BLANK_PAGES`, `omrs.jsonc` key `ocr_skip_blank_pages`) SHALL switch the blank drop on or off. Its default SHALL be `true`. Off, the system SHALL NOT run the blank test and SHALL route every flagged page as a page that is not blank. The threshold SHALL stay a code constant with a version number, and no setting SHALL tune it.

#### Scenario: Default keeps the drop

- **GIVEN** no source sets `ocr_skip_blank_pages`
- **WHEN** a PDF with a blank flagged page is ingested
- **THEN** the page SHALL be dropped from the OCR route and counted in `ocr_pages_blank`

#### Scenario: Off sends blank pages to OCR

- **GIVEN** `OCR_SKIP_BLANK_PAGES=false`
- **WHEN** a PDF with a blank flagged page is ingested
- **THEN** the blank test SHALL NOT render any page
- **AND** the page SHALL go to the local tier and escalation path like any flagged page
- **AND** `ocr_pages_blank` SHALL be 0

#### Scenario: Environment text that is not a boolean

- **WHEN** `OCR_SKIP_BLANK_PAGES=sometimes` is set in the environment
- **THEN** start-up SHALL fail with a message that names `ocr_skip_blank_pages`

#### Scenario: Bad value in omrs.jsonc

- **GIVEN** `omrs.jsonc` holds `"ocr_skip_blank_pages": "sometimes"`
- **WHEN** the server starts
- **THEN** the key SHALL be listed as invalid and ignored, and the setting SHALL be `true`

#### Scenario: No tuning key

- **WHEN** an operator lists the OCR settings
- **THEN** `ocr_skip_blank_pages` SHALL be the only setting of the blank test
- **AND** no setting SHALL change its threshold

## MODIFIED Requirements

### Requirement: Blank flagged pages SHALL skip both OCR tiers

Under the `page` unit and while `ocr_skip_blank_pages` is `true`, the system SHALL test every flagged page for blankness after flagging and before the local tier. A blank page SHALL NOT be sent to the local tier or to any OCR route. It SHALL keep its native text, SHALL be counted in `ocr_pages_blank`, and SHALL emit a page document only when that native text is not empty. Unflagged pages SHALL NOT be tested.

#### Scenario: A blank sheet costs no OCR

- **GIVEN** the `page` routing unit and a flagged page that is an empty sheet of scanned paper
- **WHEN** the PDF is ingested
- **THEN** the local tier and the OCR routes SHALL NOT receive that page
- **AND** `ocr_pages_blank` SHALL count it
- **AND** `ocr_pages_unresolved` SHALL NOT count it

#### Scenario: A page with content is not blank

- **GIVEN** the `page` routing unit and a flagged page of faint handwriting, of non-Latin script, or with one printed dark 12 pt word
- **WHEN** the PDF is ingested
- **THEN** the page SHALL follow the local tier and escalation path as before

#### Scenario: Switch off

- **GIVEN** `ocr_skip_blank_pages` is `false` and a flagged page that is an empty sheet of scanned paper
- **WHEN** the PDF is ingested
- **THEN** the page SHALL follow the local tier and escalation path
- **AND** `ocr_pages_blank` SHALL NOT count it

### Requirement: The blank test SHALL participate in the index identity

The blank test version SHALL enter the source index identity for every source. While `ocr_skip_blank_pages` is `false`, the PDF `parser` block SHALL hold `skip_blank_pages: false`; while it is `true`, the block SHALL hold no such entry, so a default install keeps every digest. `ocr_pages_blank` SHALL be in the central embedding exclusion set.

#### Scenario: A blank test version change re-indexes

- **GIVEN** a source indexed under one blank test version
- **WHEN** it is ingested again under a different blank test version
- **THEN** the source SHALL be re-indexed

#### Scenario: Default adds nothing

- **GIVEN** a PDF source and a Markdown source indexed before this change
- **WHEN** they are ingested again with `ocr_skip_blank_pages` unset
- **THEN** neither digest SHALL change

#### Scenario: Switch off re-indexes PDF sources only

- **GIVEN** one PDF source and one Markdown source indexed with the switch on
- **WHEN** `ocr_skip_blank_pages` is set to `false` and the collection is ingested
- **THEN** the PDF source digest SHALL change and the PDF source SHALL be re-indexed
- **AND** the Markdown source digest SHALL NOT change

## REMOVED Requirements

### Requirement: The blank test has no setting

**Reason**: The operator decided on 2026-11-06 that the blank drop needs an off switch, settable in Settings and on a Read document step, for a collection where the blank test is wrong.

**Migration**: None needed. The default `ocr_skip_blank_pages=true` keeps today's behaviour and every digest. The threshold still has no setting (requirement "The blank test SHALL have one on/off switch and no tuning").
