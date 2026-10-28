## ADDED Requirements

### Requirement: The page shows runtime components in three groups

Below the integration cards, the Integrations page SHALL show the groups "OCR engines", "Model files" and "Local servers". Each row SHALL show the name, purpose, status text with a badge, reason, the settings that use it and its copy command. A row that is not `ready` and that a setting in force uses SHALL show its status in red.

#### Scenario: Engine not provisioned

- **WHEN** dots-mocr is the primary engine and is not provisioned
- **THEN** the OCR engines group MUST show the dots-mocr row as missing, in red, with the reason that names its licence file and the copy command `python3 ocr-workers/provision.py dots-mocr --accept-model-licence`

#### Scenario: Unused server not running

- **WHEN** no setting uses llama.cpp and the llama.cpp server is not running
- **THEN** the llama.cpp row MUST show "Not running" without red

#### Scenario: Phone width

- **WHEN** the page is 390 px wide
- **THEN** the three groups, their reasons and their copy commands MUST fit without sideways page scroll

### Requirement: The OCR engines group sets the workers folder

The OCR engines group SHALL show the OCR workers folder in force and a field to change it. Save SHALL send the folder to the settings write route. When the server refuses the folder, the field SHALL show the reason. After a save, the group SHALL say that the folder applies at the next launch and SHALL offer the restart action. When `env` or `.env` sets the folder, the field SHALL be read-only and SHALL say which variable to remove.

#### Scenario: Set the folder

- **WHEN** the user enters a folder that holds `engines/` and presses Save
- **THEN** `omrs.jsonc` MUST hold `ocr_workers_dir` with that folder
- **AND** the group MUST say that the folder applies at the next launch

#### Scenario: Folder refused

- **WHEN** the user enters a folder without `engines/`
- **THEN** the field MUST show the reason and the file MUST NOT change

### Requirement: Provider cards report readiness

The llama.cpp and OpenRouter cards SHALL keep the "Base default" badge. Each SHALL also show one readiness line. For llama.cpp, the line SHALL be "Ready" when the configured llama.cpp addresses that settings use answer, and "Not running at <address>" otherwise. For OpenRouter, the line SHALL be "Ready" when a key reference for OpenRouter is set, and "No key set" otherwise. A card SHALL NOT show "Ready" from a module check alone.

#### Scenario: llama.cpp not running

- **WHEN** the llama.cpp packages are present and no server answers at `llamacpp_chat_url`
- **THEN** the llama.cpp card MUST show "Base default" and "Not running at http://localhost:8081/v1"
- **AND** it MUST NOT show "Ready"

#### Scenario: OpenRouter without a key

- **WHEN** no OpenRouter key reference is set
- **THEN** the OpenRouter card MUST show "No key set"
