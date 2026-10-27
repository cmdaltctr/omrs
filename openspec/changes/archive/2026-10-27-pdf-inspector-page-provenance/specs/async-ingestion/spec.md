## ADDED Requirements

### Requirement: The PDF reader output revision SHALL participate in the identity of PDF sources

For a source that a PDF reader reads, the index-shaping identity SHALL include the declared output revision of that reader, inside the existing `source_index_identity` payload. Sources that no PDF reader reads SHALL NOT carry the value, so their identity stays unchanged. The identity schema number SHALL NOT change.

#### Scenario: A PDF indexed before the revision existed reprocesses once

- **GIVEN** a byte-identical PDF whose stored identity carries no reader output revision
- **WHEN** ingestion runs with `pdf_inspector` at output revision 2
- **THEN** the source SHALL NOT be reported as `skipped_unchanged`
- **AND** it SHALL be re-chunked, re-embedded and replaced through the existing failure-safe replacement path
- **AND** a second ingestion run with no other change SHALL report it as `skipped_unchanged`

#### Scenario: A reader output change reprocesses PDF sources

- **GIVEN** a byte-identical PDF indexed at one output revision of its reader
- **WHEN** the reader's declared output revision changes and ingestion runs again
- **THEN** the source SHALL NOT be reported as `skipped_unchanged`

#### Scenario: Non-PDF sources keep their identity

- **GIVEN** a previously indexed, byte-identical `.md` source
- **WHEN** ingestion runs again after the PDF reader output revision changes
- **THEN** the source SHALL be reported as `skipped_unchanged`

#### Scenario: Unchanged revision still skips

- **GIVEN** a PDF indexed at the current output revision
- **WHEN** ingestion runs again with no other change
- **THEN** the source SHALL be reported as `skipped_unchanged`

#### Scenario: A pipeline step reader supplies the revision

- **GIVEN** a Read document step that selects a PDF reader other than the host default
- **WHEN** the identify step computes the identity of a PDF source
- **THEN** the identity SHALL carry the output revision of the step's reader
