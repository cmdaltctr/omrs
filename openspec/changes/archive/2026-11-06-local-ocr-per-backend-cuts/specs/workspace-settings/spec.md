## ADDED Requirements

### Requirement: Document reading edits the confidence cut of each local OCR backend

Settings › Document reading › Local OCR › "Local OCR backends" SHALL give each listed backend row a "Confidence cut" number input from 0 to 1. An empty input SHALL show the backend's default cut and SHALL mean "use the default". A save SHALL write `ocr_local_cuts` with one entry for each filled input and SHALL keep the entries of backends that are not listed. A save with no entries SHALL remove the key.

#### Scenario: Default shown when unset

- **GIVEN** the list `pp-ocrv6-small` and no `ocr_local_cuts` in any source
- **WHEN** the Local OCR group renders
- **THEN** the PP-OCRv6 small row MUST show an empty "Confidence cut" input with the default 0.92 shown in it

#### Scenario: Set a cut and save

- **GIVEN** the list `pp-ocrv6-small, indra`
- **WHEN** the user types 0.95 in the Indra row and presses Save
- **THEN** `omrs.jsonc` MUST hold `"ocr_local_cuts": {"indra": 0.95}`
- **AND** the group MUST show "Restart to apply"

#### Scenario: Clear the last cut

- **GIVEN** `omrs.jsonc` holds `"ocr_local_cuts": {"indra": 0.95}` and the list `pp-ocrv6-small, indra`
- **WHEN** the user empties the Indra input and presses Save
- **THEN** `omrs.jsonc` MUST no longer hold `ocr_local_cuts`

#### Scenario: Value out of range

- **WHEN** the user types 1.5 in a cut input
- **THEN** the page MUST show "The cut must be a number from 0 to 1." beside the input
- **AND** Save MUST send nothing

#### Scenario: Locked by the environment

- **GIVEN** `OCR_LOCAL_CUTS` is set in the environment
- **WHEN** the Local OCR group renders
- **THEN** every cut input MUST be read-only and the group MUST show "Remove OCR_LOCAL_CUTS from the environment or .env to edit it here."

#### Scenario: Phone width

- **WHEN** the page renders at 390 px
- **THEN** every backend row, its cut input and its buttons MUST be visible without horizontal scrolling
- **AND** each cut input MUST have a label that names its backend

### Requirement: Document reading routes carry the local OCR cuts

`GET /v1/settings/document-reading` SHALL return an `ocr_local_cuts` entry with the value in force, the saved value, the source, the lock state and the default empty map. Each local OCR backend option SHALL carry its default cut. `PUT` SHALL accept `ocr_local_cuts` as an object or `null`. It SHALL answer 400 for a name that cannot be listed or a value that is not a number from 0 to 1, with no submitted value in the message.

#### Scenario: Read the cuts

- **WHEN** a session with the read scope sends `GET /v1/settings/document-reading`
- **THEN** the answer MUST hold an `ocr_local_cuts` entry
- **AND** the `pp-ocrv6-small` backend option MUST carry the default cut 0.92

#### Scenario: Refused value

- **WHEN** a `PUT` sets `ocr_local_cuts` to `{"pp-ocrv6-small": 2}`
- **THEN** the server MUST answer 400, the file MUST NOT change, and the message MUST NOT contain `2`

### Requirement: Document reading offers to remove the retired cut key

When `omrs.jsonc` holds `ocr_local_min_confidence`, the Local OCR group SHALL show "omrs.jsonc holds ocr_local_min_confidence. OMRS ignores it. Each backend now has its own cut." with a "Remove it" button. The button and every save of `ocr_local_cuts` SHALL remove the old key in the same write, with the revision check, the atomic replace and the comments kept.

#### Scenario: Remove the old key from the page

- **GIVEN** `omrs.jsonc` holds `"ocr_local_min_confidence": 0.9` and a comment above it
- **WHEN** the user presses "Remove it"
- **THEN** `omrs.jsonc` MUST no longer hold `ocr_local_min_confidence`
- **AND** every other key and comment in the file MUST stay
- **AND** the notice MUST go

#### Scenario: Saving a cut removes the old key

- **GIVEN** `omrs.jsonc` holds `"ocr_local_min_confidence": 0.9`
- **WHEN** the user sets the PP-OCRv6 small cut to 0.9 and presses Save
- **THEN** `omrs.jsonc` MUST hold `"ocr_local_cuts": {"pp-ocrv6-small": 0.9}` and MUST NOT hold `ocr_local_min_confidence`
