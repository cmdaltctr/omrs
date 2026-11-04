# ocr-worker-engines Specification

## Purpose

Let OMRS run more than one isolated OCR engine through one shared worker core and one protocol. Adding an engine then needs one engine folder and one route setting, with no host code change.

## Requirements

### Requirement: OCR engines SHALL share one worker core and one protocol

Every OCR engine SHALL run as a separate local subprocess in its own environment, provisioned from its own lockfile. Every engine SHALL speak the same versioned JSON Lines protocol, served by one shared worker core. The core SHALL own request framing, validation, the capability command, page-subset selection and error mapping. An engine SHALL supply only its model-specific parsing and its identity declarations: packages, pipeline, and model with revisions.

#### Scenario: Two engines speak the same protocol

- **GIVEN** the `paddleocr-vl` and `dots-mocr` engines are both provisioned
- **WHEN** the host probes each engine
- **THEN** both SHALL report the same protocol version and output-schema identity
- **AND** each SHALL report its own package, pipeline and model identities

### Requirement: Each worker environment registers exactly one engine

Each environment SHALL contain exactly one registered engine. A worker environment that registers zero engines or more than one engine SHALL report itself unavailable through the capability probe and SHALL NOT accept parse requests.

#### Scenario: An environment with two engines is unavailable

- **GIVEN** a worker environment that registers two engines
- **WHEN** the host probes it
- **THEN** the probe SHALL return the stable unavailable fingerprint
- **AND** no parse request SHALL be dispatched to it

### Requirement: The host and worker protocol copies stay identical

The host's protocol copy and the worker core's protocol copy SHALL stay byte-identical.

#### Scenario: Protocol copies stay identical

- **WHEN** the test suite runs
- **THEN** a test SHALL fail if the host protocol module and the worker-core protocol module differ

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

### Requirement: Engine routes SHALL be injected configuration

The host SHALL read one ordered list of engine names from the injected effective settings, `ocr_engines`, and the workers directory. The default list SHALL be `dots-mocr, paddleocr-vl`. The list MAY hold any number of engines. When no source sets `ocr_engines`, the host SHALL build the list from `ocr_engine_primary` and `ocr_engine_fallback`, and an empty fallback name SHALL give a list of one engine. An empty workers directory SHALL make every route unavailable.

#### Scenario: Default routes

- **WHEN** the host reads the routes from the injected effective settings
- **THEN** the first engine SHALL be `dots-mocr`
- **AND** the second engine SHALL be `paddleocr-vl`

#### Scenario: Old keys build the list

- **GIVEN** `OCR_ENGINE_PRIMARY=paddleocr-vl` and `OCR_ENGINE_FALLBACK=` in the environment, and no `OCR_ENGINES`
- **WHEN** the host reads the routes
- **THEN** the list SHALL be `paddleocr-vl` alone

#### Scenario: Three engines

- **GIVEN** `OCR_ENGINES=dots-mocr,paddleocr-vl,glm-ocr`
- **WHEN** the host reads the routes
- **THEN** the host SHALL hold three routes in that order

### Requirement: The explicit worker command overrides the primary route only

The existing explicit worker command and environment directory SHALL stay valid and SHALL override the primary route only.

#### Scenario: The explicit command overrides the primary route

- **GIVEN** an explicit worker command is configured
- **WHEN** the primary route resolves
- **THEN** it SHALL use the explicit command
- **AND** the fallback route SHALL still resolve from the workers directory

### Requirement: Each route owns one lazy client

Each route SHALL own one lazy, long-lived client. A route's subprocess SHALL start only on that route's first dispatch. Routes that resolve to the same engine SHALL share one client.

#### Scenario: The fallback does not start while the primary serves

- **GIVEN** both routes are available
- **WHEN** a batch dispatches OCR requests
- **THEN** only the primary-route subprocess SHALL start

### Requirement: The request timeout grows with the page count

The request timeout SHALL grow with the number of pages in the request, and SHALL never be below the configured per-request timeout.

#### Scenario: A long request gets a longer timeout

- **GIVEN** the per-request timeout is 300 seconds and the per-page allowance is 120 seconds
- **WHEN** a 14-page request is dispatched
- **THEN** its timeout SHALL be 1,680 seconds

### Requirement: Every OCR dispatch SHALL use the primary route, then the fallback route

Every OCR dispatch SHALL go to the first engine of the list. This covers scanned and image-based PDFs, pages escalated from the local OCR tier, and maths pages. If that engine is unavailable before dispatch, the same request SHALL go to the next engine, and so on down the list. If every engine is unavailable, the existing degraded behaviour for an unavailable worker SHALL apply. A poor or empty answer SHALL NOT move a request to another engine.

#### Scenario: A scanned PDF goes to the primary engine

- **GIVEN** a scanned PDF and an available first engine
- **WHEN** the PDF is ingested
- **THEN** the whole PDF SHALL be parsed by the first engine
- **AND** no later engine SHALL be started

#### Scenario: A missing primary engine hands the request to the fallback

- **GIVEN** a scanned PDF, an unavailable first engine and an available second engine
- **WHEN** the PDF is ingested
- **THEN** the whole PDF SHALL be parsed by the second engine

#### Scenario: The third engine serves when the first two are missing

- **GIVEN** three engines and only the third is available before dispatch
- **WHEN** a request is dispatched
- **THEN** the third engine SHALL parse it

#### Scenario: An empty answer does not move the request

- **GIVEN** the first engine is available and returns empty Markdown for a page
- **WHEN** the result is merged
- **THEN** no request SHALL go to the second engine for that page

### Requirement: A worker failure after dispatch is not retried on the other route

A worker failure after dispatch SHALL remain a structured per-file error. It SHALL NOT trigger a retry on another engine. The one exception SHALL be a request that failed because the operator stopped the engine's runtime while it ran (accepted by the operator on 2026-11-01): the host SHALL send that request once to the next available engine in the list. The host SHALL NOT retry it again, whatever that result.

#### Scenario: Post-dispatch failure does not retry on the fallback

- **GIVEN** a request to the first engine has been written and flushed
- **WHEN** that worker crashes
- **THEN** the file SHALL receive a structured worker-crash error
- **AND** no request SHALL be sent to any other engine for that file

#### Scenario: Operator stop during a request

- **GIVEN** a request runs on the managed runtime of the first engine
- **WHEN** the operator stops that runtime
- **THEN** the host SHALL send the same request once to the next available engine
- **AND** later requests of that lease SHALL go to that engine without starting the stopped runtime

#### Scenario: The operator-stop retry happens once only

- **GIVEN** the host has sent a request once to the next engine after an operator stop
- **WHEN** that engine also fails or its runtime is also stopped by the operator
- **THEN** the file SHALL receive a structured error
- **AND** the host SHALL NOT send that request to any engine again

### Requirement: OCR diagnostics SHALL name the answering engine

`ocr_backend` SHALL name the engine that produced all of the document's text, using each engine's backend identifier: `dots_mocr` for dots-mocr and `paddleocr_vl` for PaddleOCR-VL. It SHALL be `mixed` when more than one backend produced text. A result produced by the fallback engine SHALL name the fallback engine.

#### Scenario: A document read by the fallback names it

- **GIVEN** an unavailable primary route and a scanned PDF parsed by the fallback route
- **WHEN** the adapter emits its document
- **THEN** `ocr_backend` SHALL be `paddleocr_vl`

#### Scenario: A document read by the primary names it

- **GIVEN** a scanned PDF parsed by the primary route
- **WHEN** the adapter emits its document
- **THEN** `ocr_backend` SHALL be `dots_mocr`

### Requirement: Engine provisioning SHALL be isolated and per engine

One provisioning command SHALL provision one named engine from that engine's lockfile only. It SHALL NOT change the OMRS main environment. An engine's packages, including PyTorch for `dots-mocr`, SHALL NOT enter the OMRS package metadata, the root lockfile, or any OMRS runtime import.

#### Scenario: Main environment stays free of engine packages

- **GIVEN** OMRS is installed from its main package metadata and root lockfile
- **WHEN** it starts and ingests a PDF
- **THEN** no Paddle or PyTorch package SHALL be required or imported by OMRS

### Requirement: An engine with extra model licence terms needs operator acceptance

An engine whose model licence adds terms beyond its code licence SHALL require explicit operator acceptance at provisioning. `dots-mocr` SHALL NOT provision without that acceptance. The engine folder SHALL record the terms that affect OMRS.

#### Scenario: dots-mocr refuses to provision without licence acceptance

- **WHEN** the operator provisions `dots-mocr` without the licence-acceptance flag
- **THEN** provisioning SHALL stop before installing anything
- **AND** it SHALL name the licence file and the flag

### Requirement: Model weights are fetched at provisioning

Model weights SHALL be fetched at provisioning, at a pinned model revision. A parse SHALL NOT download model files.

#### Scenario: Parse runs offline

- **GIVEN** a provisioned `dots-mocr` engine with its weights in the engine cache
- **WHEN** it parses a page with network access blocked
- **THEN** the parse SHALL succeed without a download attempt

### Requirement: The dots-mocr engine SHALL emit structured Markdown without page furniture

The `dots-mocr` engine SHALL convert the model's layout output to Markdown per page. Formulas SHALL be emitted as LaTeX display blocks with exactly one pair of `$$` delimiters. Tables SHALL be emitted as HTML tables. Title and section headers SHALL be emitted as Markdown headings. Page headers and page footers SHALL be omitted. Pictures SHALL carry no text.

#### Scenario: A display equation has one pair of delimiters

- **WHEN** the model returns a formula already wrapped in `$$`
- **THEN** the emitted Markdown SHALL contain that formula between exactly one opening and one closing `$$`

#### Scenario: Page furniture is dropped

- **WHEN** the model labels a region as a page header or page footer
- **THEN** that region's text SHALL NOT appear in the emitted Markdown

### Requirement: A truncated or unparsable page returns empty Markdown

A page whose output reaches the configured token limit, or whose layout output cannot be parsed, SHALL return empty Markdown for that page, and the engine SHALL log the reason on standard error. It SHALL NOT return truncated or unparsed output as Markdown. The protocol version SHALL NOT change for this.

#### Scenario: A truncated page is not usable text

- **WHEN** a page's generation reaches the token limit
- **THEN** that page's Markdown SHALL be empty
- **AND** the host SHALL apply the fallback chain for that page

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

### Requirement: Engines after the second enter the index identity only when present

The source index identity SHALL keep `ocr_worker_fingerprint` for the first engine and `ocr_fallback_fingerprint` for the second, as today. A list of one engine SHALL give the stable unavailable payload for the second. Fingerprints of the third and later engines SHALL be added under a new key only when the list holds three or more engines.

#### Scenario: Two-engine install keeps its digest

- **GIVEN** an install on the default two engines
- **WHEN** it computes a PDF source identity after this change
- **THEN** the digest SHALL equal the digest before this change

#### Scenario: Adding a third engine reindexes PDF sources

- **GIVEN** an indexed collection and a third engine is appended to the list
- **WHEN** the next explicit ingest runs
- **THEN** PDF sources SHALL be processed again
