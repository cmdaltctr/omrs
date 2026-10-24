## ADDED Requirements

### Requirement: A saved user profile that selects an extra blocks its uninstall

The uninstall in-use check SHALL also read every user profile that is not deleted. A profile uses an extra when an enabled `read.document` step in the current revision of its ingest pipeline names a PDF reader that the in-use map ties to the extra, or when its `embed_provider` names a provider whose registry entry declares the extra. The server SHALL then refuse the uninstall with 409 and the reason `in-use`, SHALL name the profile (`id` and `title`) and the setting inside it, and SHALL start no process. A global setting that uses the extra SHALL be reported before a profile. When the server cannot read the profiles, it SHALL log a warning and apply the global check only.

#### Scenario: A profile reads PDF files with pypdfium2

- **WHEN** the user profile "Scans" has a Read document step with `pdf_reader` set to `pypdfium2`, and the user uninstalls `pdf-pypdfium2`
- **THEN** the server MUST return 409 with the reason `in-use`, the setting `pdf_reader` and the profile "Scans", and MUST start no process

#### Scenario: A disabled step does not block

- **WHEN** the only Read document step that names `pypdfium2` is disabled
- **THEN** the entry MUST NOT report `in-use` because of that profile

#### Scenario: A deleted profile does not block

- **WHEN** the profile that names `pypdfium2` is deleted
- **THEN** the entry MUST NOT report `in-use` because of that profile

#### Scenario: A profile embedding provider with an extra blocks it

- **WHEN** a user profile's `embed_provider` names a provider whose embedding registry entry declares an extra
- **THEN** that extra's entry MUST report `in-use` with the setting `embed_provider` and that profile

#### Scenario: A global setting is named first

- **WHEN** `pdf_reader` is `pypdfium2` in `omrs.jsonc` and a profile also names `pypdfium2`
- **THEN** the entry MUST report the setting `pdf_reader` with no profile

#### Scenario: Profiles cannot be read

- **WHEN** the web server has no profile catalogue
- **THEN** the catalogue MUST still answer, and only the global settings MUST decide `in-use`
