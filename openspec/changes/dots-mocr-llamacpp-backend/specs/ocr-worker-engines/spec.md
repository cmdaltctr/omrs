# Spec Delta

## MODIFIED Requirements

### Requirement: Engine provisioning SHALL be isolated and per engine

One provisioning command SHALL provision one named engine from that engine's lockfile and pinned file list only. It SHALL NOT change the OMRS main environment. An engine's packages, model files and runtime binaries SHALL NOT enter the OMRS package metadata, the root lockfile, or any OMRS runtime import.

#### Scenario: Main environment stays free of engine packages

- **GIVEN** OMRS is installed from its main package metadata and root lockfile
- **WHEN** it starts and ingests a PDF
- **THEN** no Paddle or PyTorch package SHALL be required or imported by OMRS

#### Scenario: The llama.cpp runtime stays inside the engine folder

- **GIVEN** the `dots-mocr` engine is provisioned
- **WHEN** the operator inspects the OMRS main environment and the system `PATH`
- **THEN** the engine's llama.cpp binary SHALL exist only inside the engine folder
- **AND** provisioning SHALL NOT install or change any llama.cpp binary outside it

### Requirement: Model weights are fetched at provisioning

Model files and any runtime binary an engine needs SHALL be fetched at provisioning, each at a pinned revision or release, and each SHALL be checked against a pinned SHA-256. A parse SHALL NOT download files. An engine whose files do not match their pinned SHA-256 SHALL refuse to parse and SHALL name the file that differs.

#### Scenario: Parse runs offline

- **GIVEN** a provisioned `dots-mocr` engine with its files in the engine cache
- **WHEN** it parses a page with network access blocked
- **THEN** the parse SHALL succeed without a download attempt

#### Scenario: A changed model file stops the engine

- **GIVEN** a provisioned `dots-mocr` engine whose model file no longer matches its pinned SHA-256
- **WHEN** the host sends a parse request
- **THEN** the worker SHALL return a parse error that names the file
- **AND** it SHALL NOT start the llama.cpp server

#### Scenario: Provisioning rejects a download that does not match

- **WHEN** a downloaded model file or runtime archive does not match its pinned SHA-256
- **THEN** provisioning SHALL stop with an error that names the file
- **AND** it SHALL leave no partial file in the engine cache

## ADDED Requirements

### Requirement: The dots-mocr engine SHALL run on a llama.cpp server it owns

The `dots-mocr` engine SHALL run the model through a llama.cpp server that its worker starts, uses and stops. The server SHALL listen on a loopback address only. The engine SHALL use only the llama.cpp release pinned for it, and SHALL refuse to parse when the server reports another build. The prompt, page rendering, token limit and Markdown conversion SHALL stay as the PyTorch backend had them.

#### Scenario: The first parse starts the server

- **GIVEN** a provisioned `dots-mocr` worker with no server running
- **WHEN** the worker receives its first parse request
- **THEN** it SHALL start the pinned llama.cpp server on a free loopback port
- **AND** it SHALL wait until the server reports healthy before it sends the page
- **AND** later requests to the same worker SHALL reuse that server

#### Scenario: The server stops with the worker

- **GIVEN** a `dots-mocr` worker with a running server
- **WHEN** the host closes the worker
- **THEN** the server process SHALL stop
- **AND** no llama.cpp process started by that worker SHALL remain

#### Scenario: A server left by a killed worker is cleaned up

- **GIVEN** a `dots-mocr` worker was killed and left its server running
- **WHEN** a new `dots-mocr` worker starts its server
- **THEN** it SHALL stop the server that the earlier worker started
- **AND** it SHALL NOT stop any llama.cpp process that the engine did not start

#### Scenario: The server does not become healthy

- **WHEN** the server does not report healthy within the start timeout
- **THEN** the worker SHALL return a parse error that names the server log
- **AND** the host SHALL apply the fallback chain for that file

#### Scenario: The fingerprint names the runtime

- **WHEN** the host probes the `dots-mocr` engine
- **THEN** its fingerprint SHALL name the llama.cpp backend, the pinned llama.cpp build and the model file revision
- **AND** documents indexed with the PyTorch backend SHALL be re-indexed on their next ingest

### Requirement: The dots-mocr engine SHALL NOT depend on PyTorch

The `dots-mocr` engine environment SHALL NOT install or import PyTorch, torchvision, transformers or accelerate. No OCR engine shipped with OMRS SHALL require PyTorch.

#### Scenario: The provisioned environment has no PyTorch

- **GIVEN** the `dots-mocr` engine is provisioned from its lockfile
- **WHEN** the operator lists the packages in its environment
- **THEN** no PyTorch, torchvision, transformers or accelerate package SHALL be present
