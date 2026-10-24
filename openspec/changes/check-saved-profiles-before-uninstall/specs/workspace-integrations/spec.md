## ADDED Requirements

### Requirement: The card names the profile that uses an extra

When the server refuses an uninstall because a saved user profile uses the extra, the card SHALL name the profile and the setting inside it, SHALL link to that profile in Studio, and SHALL show no Uninstall button and no lasting command.

#### Scenario: A profile uses pypdfium2

- **WHEN** the entry reports `in-use` with the setting `pdf_reader` and the profile "Scans"
- **THEN** the PDF reader: pypdfium2 card MUST say that the profile "Scans" uses this extra through `pdf_reader`, MUST link to `#/studio/<profile id>`, and MUST NOT show Uninstall or the lasting command

#### Scenario: A refused uninstall names the profile

- **WHEN** the uninstall request answers 409 `in-use` with a `profile`
- **THEN** the card MUST show a line that names that profile
