# Spec Delta

## MODIFIED Requirements

### Requirement: The page shows runtime components in three groups

The Integrations page SHALL show the runtime components in three sections: "OCR engines", "Model files" and "Local servers". Each row SHALL show the name, purpose, status text with a badge, and the settings that use it. A row SHALL show its reason and its copy command only when the server sends them (not `null`). A row that is not `ready` and that a setting in force uses SHALL show its status in red.

#### Scenario: Engine not provisioned

- **WHEN** dots-mocr is the primary engine and is not provisioned
- **THEN** the OCR engines group MUST show the dots-mocr row as missing, in red, with the reason that names its licence file and the copy command `omrs ocr install dots-mocr --accept-model-licence`

#### Scenario: Unused server not running

- **WHEN** no setting uses llama.cpp and the llama.cpp server is not running
- **THEN** the llama.cpp row MUST show "Not running" without red

#### Scenario: Phone width

- **WHEN** the page is 390 px wide
- **THEN** the section chips, each section, its reasons and its copy commands MUST fit without sideways page scroll

## ADDED Requirements

### Requirement: An OCR engine row offers Install

Each OCR engine row that is `missing` SHALL show an Install button. Pressing it SHALL call `POST /v1/integrations/ocr-engines/{engine}/install` and SHALL need the `manage` scope. The button SHALL be disabled while an install job runs.

#### Scenario: Engine not installed

- **WHEN** the `paddleocr-vl` row is `missing`
- **THEN** the row MUST show an Install button
- **AND** pressing it MUST call `POST /v1/integrations/ocr-engines/paddleocr-vl/install`

#### Scenario: Another install runs

- **WHEN** an install job runs for `dots-mocr`
- **THEN** the Install button of every OCR engine row MUST be disabled

#### Scenario: Engine ready

- **WHEN** the `paddleocr-vl` row is `ready`
- **THEN** the row MUST NOT show an Install button

### Requirement: Install asks for licence acceptance first

When the engine needs licence acceptance, pressing Install SHALL open a prompt that names the licence file and has an Accept and install button. The request SHALL carry the acceptance only after the user presses that button.

#### Scenario: Prompt for dots-mocr

- **WHEN** the user presses Install on the `dots-mocr` row
- **THEN** a prompt MUST name `LICENCE-NOTES.md` and show Accept and install
- **AND** no request MUST be sent until the user presses Accept and install

#### Scenario: No prompt without a licence step

- **WHEN** the user presses Install on the `paddleocr-vl` row
- **THEN** the request MUST be sent without a prompt

### Requirement: The row shows install progress, result and reason

While the job runs, the row SHALL show the step (copy, environment, fetch) and the last output line. On failure, it SHALL show the fixed reason in plain English. After a success that changed `ocr_workers_dir`, it SHALL say that the folder applies at the next launch and SHALL offer the restart action.

#### Scenario: Progress

- **WHEN** the job is in the `environment` step
- **THEN** the row MUST show that step and the last output line

#### Scenario: Failure

- **WHEN** the job fails with `fetch-failed`
- **THEN** the row MUST show a plain-English reason and MUST NOT show the raw reason code alone

#### Scenario: Success sets the folder

- **WHEN** the job succeeds and saved `ocr_workers_dir`
- **THEN** the row MUST say that the folder applies at the next launch and MUST offer the restart action

#### Scenario: Phone width

- **WHEN** the page is 390 px wide
- **THEN** the Install button, the prompt, the step line and the reason MUST fit without sideways page scroll
