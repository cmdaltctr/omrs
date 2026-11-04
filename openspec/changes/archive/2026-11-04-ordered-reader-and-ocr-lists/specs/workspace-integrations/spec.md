## ADDED Requirements

### Requirement: Integrations page lists PDF readers

The Integrations page SHALL have a PDF readers section. It SHALL show one row for every reader in the PDF reader registry, in registry order, so a newly registered reader appears with no page change. Each row SHALL show the reader name, "Installed" or "Not installed", and where the reader is used: its position in the host list, and each saved profile whose Read document step lists it.

#### Scenario: All four readers listed

- **GIVEN** pdf-inspector, LiteParse and pypdf are installed and pypdfium2 is not
- **WHEN** the user opens Integrations › PDF readers
- **THEN** four rows SHALL show
- **AND** pypdfium2 SHALL show "Not installed"

#### Scenario: Reader in use

- **GIVEN** the host list is `pdf_inspector, liteparse, pypdf`
- **WHEN** the section loads
- **THEN** the pdf-inspector row SHALL say it is first in Settings › Document reading
- **AND** the LiteParse row SHALL say it is second

### Requirement: A missing reader shows a copy-fix command

A row for a reader that is not installed SHALL show the command that installs it, with a copy button, in the style of the other Integrations rows. A reader behind an extra SHALL show that extra's command. A reader in the base install SHALL show the base sync command. The probe SHALL only import-check the reader. It SHALL NOT install, download or start anything.

#### Scenario: pypdfium2 fix command

- **GIVEN** pypdfium2 is not installed
- **WHEN** the row renders
- **THEN** it SHALL show `uv sync --extra pdf-pypdfium2` with a copy button

#### Scenario: Reader in use but missing

- **GIVEN** a reader is in the host list and is not installed
- **WHEN** the section loads
- **THEN** the row SHALL show in the attention colour
- **AND** the section chip SHALL count it
