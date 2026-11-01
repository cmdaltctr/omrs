## MODIFIED Requirements

### Requirement: Adding an OCR engine SHALL NOT require host code changes

The host SHALL resolve an engine from its name and the configured workers directory alone. An operator SHALL be able to route to a new engine by adding its engine folder, provisioning it, and naming it in a route setting. An engine that needs a llama.cpp runtime SHALL declare it in its manifest, and the host SHALL start it from that declaration. The host SHALL NOT branch on engine names.

#### Scenario: A new engine is routed by configuration only

- **GIVEN** a new engine folder is added under the workers directory and provisioned
- **WHEN** the operator sets a route to that engine name
- **THEN** the host SHALL probe and dispatch to that engine
- **AND** no host module SHALL need a code change

#### Scenario: An unknown engine name degrades

- **GIVEN** a route names an engine that has no folder or no provisioned environment
- **WHEN** a PDF needs that route
- **THEN** the route SHALL resolve to the stable unavailable fingerprint
- **AND** the route's fallback behaviour SHALL apply without failing the file

#### Scenario: A new engine with a declared runtime needs no host change

- **GIVEN** a new engine folder declares a llama.cpp runtime in `[tool.omrs-ocr.runtime]`
- **WHEN** the operator routes to it
- **THEN** the host SHALL start that runtime from the declaration
- **AND** no host module SHALL name the engine

### Requirement: A worker failure after dispatch is not retried on the other route

A worker failure after dispatch SHALL remain a structured per-file error. It SHALL NOT trigger a retry on the other route. The one exception SHALL be a request that failed because the operator stopped the route's runtime while it ran (accepted by the operator on 2026-11-01): the host SHALL send that request once to the fallback route. The host SHALL NOT retry it again, whatever the fallback result.

#### Scenario: Post-dispatch failure does not retry on the fallback

- **GIVEN** a primary-route request has been written and flushed
- **WHEN** the primary worker crashes
- **THEN** the file SHALL receive a structured worker-crash error
- **AND** no request SHALL be sent to the fallback route for that file

#### Scenario: Operator stop during a request

- **GIVEN** a primary-route request runs on a managed runtime
- **WHEN** the operator stops that runtime
- **THEN** the host SHALL send the same request once to the fallback route
- **AND** later requests of that lease SHALL go to the fallback route without starting the runtime

#### Scenario: The operator-stop retry happens once only

- **GIVEN** the host has sent a request once to the fallback route after an operator stop
- **WHEN** the fallback route also fails or its runtime is also stopped by the operator
- **THEN** the file SHALL receive a structured error
- **AND** the host SHALL NOT send that request to any route again

## ADDED Requirements

### Requirement: An engine may declare a llama.cpp runtime

An engine's `pyproject.toml` MAY hold a `[tool.omrs-ocr.runtime]` block with `program`, `build`, `flags` and a list of `files`, each with `flag` (`-m` or `--mmproj`), `path` and `sha256`. The host SHALL read the block with the standard library only.

#### Scenario: Declared runtime read

- **GIVEN** an engine declares `program`, `build` 11941, its flags and two files
- **WHEN** the host resolves the route
- **THEN** the route SHALL carry a runtime with that program, build, flags and files

### Requirement: A declared runtime follows fixed rules

Every declared path SHALL be relative to the engine cache and SHALL resolve inside it. The program file name SHALL be `llama-server`. `flags` SHALL NOT hold a host, port, model, projector, Hugging Face, API key, log file or idle sleep flag. A block that breaks a rule SHALL make the route unavailable with a reason that names the rule.

#### Scenario: Path outside the cache refused

- **GIVEN** a declared file path holds `..` or is absolute
- **WHEN** the host resolves the route
- **THEN** the route SHALL be unavailable with a reason that names the path rule

#### Scenario: Reserved flag refused

- **GIVEN** the declared `flags` hold `--port`
- **WHEN** the host resolves the route
- **THEN** the route SHALL be unavailable with a reason that names the flag rule

### Requirement: The host starts the declared runtime and passes its URL

For a route whose engine declares a runtime, the host SHALL start or adopt that runtime before it dispatches a parse, and SHALL start the worker with `OMRS_OCR_RUNTIME_URL` set to the runtime's base URL. When the runtime restarts on another URL, the host SHALL start the worker again with the new URL. The capability probe SHALL NOT start the runtime. A runtime that cannot start SHALL make the route unavailable before dispatch, so the fallback route serves the request.

#### Scenario: Worker receives the URL

- **GIVEN** a provisioned engine that declares a runtime
- **WHEN** the host dispatches the first parse
- **THEN** the worker environment SHALL hold `OMRS_OCR_RUNTIME_URL` with a loopback `http` URL of the running server

#### Scenario: Probe starts nothing

- **WHEN** the host probes an engine that declares a runtime
- **THEN** no `llama-server` process SHALL start

#### Scenario: Runtime start fails

- **GIVEN** a declared model file does not match its SHA-256
- **WHEN** a scanned PDF needs the primary route
- **THEN** the primary route SHALL be unavailable before dispatch
- **AND** the fallback route SHALL parse the PDF

### Requirement: An engine without a runtime block is unchanged

An engine whose manifest has no `[tool.omrs-ocr.runtime]` block SHALL run as before: the host SHALL start no runtime for it and SHALL NOT set `OMRS_OCR_RUNTIME_URL`.

#### Scenario: PaddleOCR-VL unchanged

- **GIVEN** the `paddleocr-vl` engine declares no runtime
- **WHEN** the host dispatches a parse to it
- **THEN** no `llama-server` process SHALL start
- **AND** the worker environment SHALL NOT hold `OMRS_OCR_RUNTIME_URL`

### Requirement: A killed worker leaves no model server

Closing or killing an OCR worker SHALL NOT leave a model server that no OMRS process uses. The worker SHALL NOT start a model server. An idle OCR route SHALL close its worker before its process leaves the runtime.

#### Scenario: Worker killed during a parse

- **GIVEN** a worker that uses a managed runtime
- **WHEN** the host kills the worker with SIGKILL
- **THEN** the runtime SHALL keep running while the host process holds its lease
- **AND** no other model server SHALL exist for that engine
