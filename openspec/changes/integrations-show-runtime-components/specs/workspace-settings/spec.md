## MODIFIED Requirements

### Requirement: A connection test sends one bounded request and returns a fixed reason

The server SHALL send one model-list or key-check request for each address with a 5-second timeout, and return whether the provider was reachable and a reason from a fixed set (`refused`, `timeout`, `unauthorised`, `http-<status>`, `not-configured`). The server SHALL NOT return response bodies or exception text, SHALL NOT log a typed key, and SHALL NOT send a model-list or key-check request to any provider unless a test or a model list is requested. The only other provider request is the local server health probe of `GET /v1/integrations` (spec `runtime-components`): one request without a key to the configured Ollama and llama.cpp addresses, with a timeout of 1 second or less. The server SHALL NOT contact a cloud provider for it.

#### Scenario: Local provider down

- **WHEN** the user tests Ollama and nothing listens on its URL
- **THEN** the entry MUST show not reachable with the reason refused, stated in text with a badge

#### Scenario: No background cloud call

- **WHEN** the user opens Providers or Chat and presses no Test or List models action
- **THEN** the server MUST NOT send any request to OpenRouter

#### Scenario: Integrations page probes only local servers

- **WHEN** the user opens the Integrations page
- **THEN** the server MAY send one health request without a key to each configured Ollama and llama.cpp address
- **AND** the server MUST NOT send a model-list or key-check request to any provider

### Requirement: Document reading routes

`GET /v1/settings/document-reading` SHALL need the read scope. It SHALL return the file `revision`, one entry for each of the nine keys in a fixed order (with the value in force, the saved value, the source, whether it is locked, the lock reason, whether a restart is pending, and the default), every PDF reader with its availability, the reader in use, the OCR workers folder, and each known engine with its availability.

#### Scenario: Read the section

- **WHEN** a session with the read scope sends `GET /v1/settings/document-reading`
- **THEN** the answer MUST be 200 and MUST hold nine `settings` entries, `pdf_readers` starting with `auto`, and `ocr.engines`
- **AND** `ocr` MUST NOT hold `worker_command_set`

## REMOVED Requirements

### Requirement: Document reading marks readers and engines that are not ready

**Reason**: Its scenario "Worker command overrides the primary engine" described `OCR_WORKER_COMMAND`, which this change removes. The rest of the rule moves unchanged to "Document reading marks readers and engines that cannot run".

**Migration**: None. Remove `OCR_WORKER_COMMAND` and `OCR_WORKER_ENV_DIR` from the environment or `.env`, and set `OCR_WORKERS_DIR` with `OCR_ENGINE_PRIMARY`.

## ADDED Requirements

### Requirement: Document reading marks readers and engines that cannot run

The PDF reader choice SHALL mark each reader that is not installed and SHALL NOT let the user choose it. The engine choices SHALL list the engines the server reports and SHALL mark each engine that is not provisioned, with the reason.

#### Scenario: Reader not installed

- **WHEN** the server reports `pypdfium2` as not installed
- **THEN** the PDF reader choice MUST show `pypdfium2` as not available with the reason and MUST NOT allow it to be selected

#### Scenario: Engine not provisioned

- **WHEN** the server reports `dots-mocr` as not provisioned
- **THEN** the engine choices MUST mark `dots-mocr` as not available and MUST show the reason with its provision command
