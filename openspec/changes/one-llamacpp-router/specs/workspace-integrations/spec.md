## MODIFIED Requirements

### Requirement: Provider cards report readiness

The llama.cpp and OpenRouter cards SHALL keep the "Base default" badge. Each SHALL also show one readiness line. For llama.cpp, the line SHALL be "Ready" when the router at `llamacpp_router_url` answers, and "Not running at <address>" otherwise. For OpenRouter, the line SHALL be "Ready" when an OpenRouter key is set from any source, and "No key set" otherwise. A card SHALL NOT show "Ready" from a module check alone.

#### Scenario: llama.cpp not running

- **WHEN** the llama.cpp packages are present and no server answers at `llamacpp_router_url`
- **THEN** the llama.cpp card MUST show "Base default" and "Not running at http://127.0.0.1:8080/v1"
- **AND** it MUST NOT show "Ready"

#### Scenario: OpenRouter without a key

- **WHEN** no OpenRouter key is set from any source
- **THEN** the OpenRouter card MUST show "No key set"

### Requirement: The Integrations page lists model runtimes

The Integrations page SHALL have a "Model runtimes" section with one row per runtime from `GET /v1/runtimes`. Each row SHALL show the role, the mode, a status badge, one plain reason line when a reason is sent, the memory when it is sent, the address and what uses it. The router row SHALL list its models below it, each with its roles, state and memory. An external OCR row SHALL say "External server. Model files are not checked." and SHALL NOT hide it when the build check passes. A running managed runtime with no client SHALL say "Running, no OMRS process uses it".

#### Scenario: Failed OCR runtime

- **WHEN** the `ocr-dots-mocr-llamacpp` runtime is `failed` with `file-changed`
- **THEN** its row MUST show Failed and one reason line that names the changed file

#### Scenario: External Chat runtime

- **WHEN** Chat runs on the router and the router runtime is `external`
- **THEN** the router row MUST show the mode External and MUST NOT show a Stop button

#### Scenario: Router models under the row

- **WHEN** the router serves the embedding model (loaded) and the Chat model (unloaded)
- **THEN** the router row MUST list both models with their roles and states

#### Scenario: External OCR runtime

- **GIVEN** `ocr_runtime_url` is set and the build check passes
- **WHEN** the page shows the OCR runtime row
- **THEN** the row MUST show the mode External and MUST say "External server. Model files are not checked."
- **AND** the row MUST NOT show a Stop button

#### Scenario: Phone width

- **WHEN** the page is 390 px wide
- **THEN** every runtime row, its model lines, its reason line and its Stop button MUST fit without sideways page scroll

## ADDED Requirements

### Requirement: The Integrations page provisions the pinned llama.cpp build

The page SHALL have a llama.cpp card with the pinned build, the platform archive and the install state. A Get llama.cpp button SHALL start the provisioning job of capability `llamacpp-router` and SHALL need `manage`. On Linux x86-64 the card SHALL show the detected flavour as the default and let the user choose CPU or CUDA before install. On macOS arm64 it SHALL show no choice. The card SHALL show progress and a fixed reason on failure.

#### Scenario: Not provisioned

- **WHEN** no pinned binary is provisioned and `llamacpp_server_binary` is blank
- **THEN** the card MUST show "Not installed" and the Get llama.cpp button

#### Scenario: Detected flavour shown

- **WHEN** the host is Linux x86-64 with an NVIDIA driver and the user opens the llama.cpp card
- **THEN** the card MUST show CUDA 12.8 as the default flavour and offer CPU as the other choice

#### Scenario: Flavour chosen before install

- **WHEN** the user picks CPU and presses Get llama.cpp
- **THEN** the install request MUST name the flavour `cpu` and the job MUST fetch the CPU archive

#### Scenario: No choice on macOS

- **WHEN** the host is macOS arm64
- **THEN** the card MUST NOT show a flavour choice

#### Scenario: Hash failure shown

- **WHEN** the provisioning job fails with `file-changed`
- **THEN** the card MUST show Failed with one reason line and MUST NOT show the binary as provisioned

#### Scenario: Read-only session

- **WHEN** the session has `read` only
- **THEN** the card MUST NOT show the Get llama.cpp button
