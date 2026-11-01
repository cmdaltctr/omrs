## ADDED Requirements

### Requirement: The Integrations page lists model runtimes

The Integrations page SHALL have a "Model runtimes" section with one row per runtime from `GET /v1/runtimes`. Each row SHALL show the role, the mode, a status badge, one plain reason line when a reason is sent, the memory when it is sent, the address and what uses it. An external OCR row SHALL say "External server. Model files are not checked." and SHALL NOT hide it when the build check passes. A running managed runtime with no client SHALL say "Running, no OMRS process uses it".

#### Scenario: Failed OCR runtime

- **WHEN** the `ocr-dots-mocr-llamacpp` runtime is `failed` with `file-changed`
- **THEN** its row MUST show Failed and one reason line that names the changed file

#### Scenario: External Chat runtime

- **WHEN** the Chat runtime is `external`
- **THEN** its row MUST show the mode External and MUST NOT show a Stop button

#### Scenario: External OCR runtime

- **GIVEN** `ocr_runtime_url` is set and the build check passes
- **WHEN** the page shows the OCR runtime row
- **THEN** the row MUST show the mode External and MUST say "External server. Model files are not checked."
- **AND** the row MUST NOT show a Stop button

#### Scenario: Phone width

- **WHEN** the page is 390 px wide
- **THEN** every runtime row, its reason line and its Stop button MUST fit without sideways page scroll

### Requirement: A managed runtime can be stopped from the page

A row of a managed runtime that is `running` or `starting` SHALL show a Stop button. Stop SHALL send `POST /v1/runtimes/{runtime_id}/stop`. When the row reports that another OMRS process uses the runtime, the page SHALL ask for confirmation first and SHALL say that requests in progress fail and OCR uses the fallback engine. After the stop, the row SHALL show Stopped.

#### Scenario: Stop with no other client

- **WHEN** the user presses Stop on a running managed runtime that no other process uses
- **THEN** the page MUST send the stop request and the row MUST show Stopped

#### Scenario: Stop while in use asks first

- **WHEN** the row reports that another OMRS process uses the runtime and the user presses Stop
- **THEN** the page MUST ask for confirmation and MUST send no request until the user confirms

#### Scenario: Session without manage

- **WHEN** the session has `read` only
- **THEN** the page MUST NOT show a Stop button
