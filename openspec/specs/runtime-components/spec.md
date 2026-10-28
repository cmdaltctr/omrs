# runtime-components Specification

## Purpose
Report the parts that settings depend on but that no pip extra installs: OCR engines, model files and local servers. Each item states whether it is ready, why not, and the command that fixes it. The probes only read, so opening the Integrations page never downloads, installs, starts or writes anything.

## Requirements

### Requirement: The server reports runtime components in three groups

`GET /v1/integrations` SHALL return a `runtime` object with three lists: `ocr_engines`, `model_files` and `local_servers`. Each item SHALL have a `name`, a one-line `purpose`, a `status`, a `reason` (or `null`), a `fix` copy command (or `null`) and `used_by`, the settings in force at launch that need the item. A status SHALL be one of `ready`, `missing`, `not-configured`, `not-running` or `unknown`.

#### Scenario: Three groups returned

- **WHEN** a client calls `GET /v1/integrations`
- **THEN** the response MUST hold `runtime.ocr_engines`, `runtime.model_files` and `runtime.local_servers`
- **AND** every item MUST have the fields `name`, `purpose`, `status`, `reason`, `fix` and `used_by`

#### Scenario: A probe fails

- **WHEN** a probe raises an error
- **THEN** that item MUST have the status `unknown`
- **AND** the response MUST be 200 and MUST NOT hold the error text

### Requirement: Probes only read

A runtime probe SHALL NOT download a file, install a package, start a process or write a file. A server probe SHALL send one request with a timeout of 1 second or less. All server probes of one request SHALL run at the same time.

#### Scenario: Tokenizer not cached

- **WHEN** the tokenizer of token-aware chunking is not in the local cache
- **THEN** the probe MUST report `missing` without a network request to the model host

#### Scenario: Server does not answer

- **WHEN** the llama.cpp address does not answer within 1 second
- **THEN** the probe MUST report `not-running`, and the whole response MUST arrive within 2 seconds

### Requirement: OCR engine items follow the route rules

The OCR engine list SHALL hold every valid folder under `<ocr_workers_dir>/engines/`, the engines in force and the local OCR tier. An engine SHALL be `ready` only when the parsing route resolver finds its interpreter. Without a workers folder, a worker engine SHALL be `not-configured`. An engine folder without `.venv` SHALL be `missing`, with its provision command as the fix.

#### Scenario: Workers folder not set

- **WHEN** `ocr_workers_dir` is empty, `ocr_fallback_enabled` is true and `ocr_engine_primary` is `dots-mocr`
- **THEN** the `dots-mocr` item MUST be `not-configured` and its `used_by` MUST hold `ocr_engine_primary`

#### Scenario: Engine needs a licence

- **WHEN** the dots-mocr folder exists without `.venv`
- **THEN** the item MUST be `missing`
- **AND** its fix MUST be `python3 ocr-workers/provision.py dots-mocr --accept-model-licence`
- **AND** its reason MUST name `LICENCE-NOTES.md`

#### Scenario: Engine without a licence step

- **WHEN** the paddleocr-vl folder exists without `.venv`
- **THEN** the item MUST be `missing` with the fix `python3 ocr-workers/provision.py paddleocr-vl`

#### Scenario: Engine ready

- **WHEN** `<ocr_workers_dir>/engines/paddleocr-vl/.venv/bin/python` exists
- **THEN** the `paddleocr-vl` item MUST be `ready`

#### Scenario: Engine name without a folder

- **WHEN** `ocr_engine_primary` names an engine that has no folder under `<ocr_workers_dir>/engines/`
- **THEN** the item MUST be `missing` with no fix command

#### Scenario: OCR fallback off

- **WHEN** `ocr_fallback_enabled` is false
- **THEN** every engine item MUST have an empty `used_by`

### Requirement: Model file items check the local cache only

The model file list SHALL hold the chunking tokenizer at its pinned revision, the reranker model and the local OCR tier model. An item SHALL be `ready` when it loads from the local cache without the network, and `missing` otherwise. A `missing` item SHALL give a fix command that fetches the file at the pinned revision. When the tokenizer model or revision is blank, the tokenizer item SHALL be `not-configured`, because Markdown chunking then uses the legacy splitter on purpose.

#### Scenario: Tokenizer missing

- **WHEN** `tokenizer.json` of `Qwen/Qwen3-Embedding-4B` at revision `5cf2132a…` is not cached
- **THEN** the tokenizer item MUST be `missing`
- **AND** its reason MUST say that Markdown chunking falls back to the legacy splitter

### Requirement: Local server items probe the configured address

The local server list SHALL hold Ollama at `ollama_base_url` and llama.cpp at `llamacpp_embed_url` and `llamacpp_chat_url`. An item SHALL be `ready` when its health request succeeds, and `not-running` when it fails. An item that no setting in force uses SHALL still be listed, with an empty `used_by`. The response SHALL NOT show a user name or password from an address.

#### Scenario: Ollama running and used

- **WHEN** `embed_provider` is `ollama` and Ollama answers at `http://localhost:11434`
- **THEN** the Ollama item MUST be `ready` and its `used_by` MUST hold `embed_provider`

#### Scenario: llama.cpp not running

- **WHEN** no process listens at `llamacpp_chat_url`
- **THEN** the llama.cpp chat item MUST be `not-running` with the address in its reason
