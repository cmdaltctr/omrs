# Spec Delta

## ADDED Requirements

### Requirement: A Document reading save goes to omrs.jsonc for the next launch

A save in the Document reading section SHALL write the changed keys into `omrs.jsonc` with the file revision the page last read. A save SHALL NOT change the value in force. After a save that leaves a key waiting for a restart, the page SHALL offer the restart dialog and SHALL repeat the index identity note. "Use default" on a row SHALL remove the key from the file. A refused save SHALL show the server message and SHALL leave the row unchanged.

#### Scenario: Save a boolean

- **WHEN** the user turns maths routing off and presses Save
- **THEN** `omrs.jsonc` MUST hold `"ocr_maths_routing_enabled": false`, the row MUST show "Restart to apply", and the restart dialog MUST open

#### Scenario: Return to the default

- **WHEN** the file holds `"ocr_engine_fallback": "my-engine"` and the user presses "Use default" on that row
- **THEN** `omrs.jsonc` MUST no longer hold `ocr_engine_fallback`

#### Scenario: File edited while the page is open

- **WHEN** the user edits `omrs.jsonc` in an editor and then saves a row in Document reading
- **THEN** the page MUST show "omrs.jsonc changed on disk. Reload to see the new values." and MUST offer Reload

## MODIFIED Requirements

### Requirement: Document reading shows the reading settings and their state

The Document reading section SHALL show one row for each of `pdf_reader`, `ocr_fallback_enabled`, `ocr_routing_unit`, `ocr_engine_primary`, `ocr_engine_fallback` and `ocr_maths_routing_enabled`. Each row SHALL show the value in force since launch, its source and the default. When the saved file value differs from the value in force, the row SHALL show the saved value and "Restart to apply".

#### Scenario: Value saved but not yet in force

- **WHEN** the server launched with `pdf_reader` `auto` and `omrs.jsonc` now holds `"pdf_reader": "liteparse"`
- **THEN** the PDF reader row MUST show `auto` in force, `liteparse` saved and "Restart to apply"

### Requirement: Document reading routes

`GET /v1/settings/document-reading` SHALL need the read scope. It SHALL return the file `revision`, one entry for each of the six keys in a fixed order (with the value in force, the saved value, the source, whether it is locked, the lock reason, whether a restart is pending, and the default), every PDF reader with its availability, the reader in use, the OCR workers folder, and each known engine with its availability.

#### Scenario: Read the section

- **WHEN** a session with the read scope sends `GET /v1/settings/document-reading`
- **THEN** the answer MUST be 200 and MUST hold six `settings` entries, `pdf_readers` starting with `auto`, and `ocr.engines`
- **AND** `ocr` MUST NOT hold `worker_command_set`

### Requirement: The document reading save writes all values or none

`PUT /v1/settings/document-reading` SHALL need a browser session with the manage scope. It SHALL take `values` (one to six of the six keys, each a value or `null`) and a required `revision`. It SHALL write all values or none.

#### Scenario: One bad value stops the whole save

- **WHEN** a `PUT` sets `ocr_routing_unit` to `page` and `ocr_engine_primary` to `../x`
- **THEN** the server MUST answer 400 and the file MUST hold neither value

### Requirement: The document reading save answers with a status for each outcome

On success it SHALL return the same body as `GET`. It SHALL answer 400 for a key outside the six, for a value that breaks its rule, for a blank text value and for a PDF reader that is not installed. It SHALL answer 409 for a locked key, for a stale revision and for a file that cannot be parsed. No error message SHALL hold a submitted value.

#### Scenario: Key outside the nine

- **WHEN** a `PUT` sets `embed_provider`
- **THEN** the server MUST answer 400 "embed_provider is not a document reading setting." and MUST NOT change the file

#### Scenario: Locked key

- **WHEN** `PDF_READER` is set in the environment and a `PUT` sets `pdf_reader`
- **THEN** the server MUST answer 409 "Remove PDF_READER from the environment or .env to edit it here." and MUST NOT change the file

#### Scenario: Value out of range

- **WHEN** a `PUT` sets `ocr_routing_unit` to `document`
- **THEN** the server MUST answer 400 with a message that names `page` as the only routing unit, and MUST NOT change the file

#### Scenario: Uninstalled reader

- **WHEN** `pypdfium2` is not installed and a `PUT` sets `pdf_reader` to `pypdfium2`
- **THEN** the server MUST answer 400 "pdf_reader: This PDF reader is not installed. Install its package, then save again." and MUST NOT change the file

#### Scenario: Unprovisioned engine is allowed

- **WHEN** a `PUT` sets `ocr_engine_primary` to a valid name that has no folder under the engines folder
- **THEN** the server MUST answer 200, the file MUST hold the name, and the engine entry MUST report `available` false with the reason

## REMOVED Requirements

### Requirement: Document reading saves to omrs.jsonc for the next launch

**Reason**: Replaced by "A Document reading save goes to omrs.jsonc for the next launch". The maths page fraction is removed, so the fraction save scenario no longer holds.
