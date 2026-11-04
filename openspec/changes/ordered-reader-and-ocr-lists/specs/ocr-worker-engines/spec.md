## MODIFIED Requirements

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

## ADDED Requirements

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
