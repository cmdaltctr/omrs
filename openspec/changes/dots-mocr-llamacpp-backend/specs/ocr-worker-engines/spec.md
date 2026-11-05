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

An engine that ships the `omrs-ocr-fetch` step (the `dots-mocr` engine) SHALL fetch its model files and any runtime binary it needs at provisioning, each at a pinned revision or release, and SHALL check each against a pinned SHA-256. A parse by such an engine SHALL NOT download files. The `paddleocr-vl` engine ships no fetch step: Paddle downloads its model files into the engine cache on the first parse. A model file that an engine declares with a SHA-256 and that no longer matches SHALL stop that engine's route before dispatch, with a reason that names the file.

#### Scenario: Parse runs offline

- **GIVEN** a provisioned `dots-mocr` engine with its files in the engine cache
- **WHEN** it parses a page with network access blocked
- **THEN** the parse SHALL succeed without a download attempt

#### Scenario: A changed model file stops the engine

- **GIVEN** a provisioned `dots-mocr` engine whose declared model file no longer matches its pinned SHA-256
- **WHEN** a PDF needs the `dots-mocr` route
- **THEN** the route SHALL be unavailable with a reason that names the file
- **AND** no llama.cpp server SHALL start for it

#### Scenario: Provisioning rejects a download that does not match

- **WHEN** a downloaded model file or runtime archive does not match its pinned SHA-256
- **THEN** provisioning SHALL stop with an error that names the file
- **AND** it SHALL leave no partial file in the engine cache

## ADDED Requirements

### Requirement: The dots-mocr engine SHALL declare a pinned llama.cpp runtime

The `dots-mocr` engine SHALL declare its llama.cpp runtime in its manifest: the pinned `llama-server` program in its cache, build 11941, the fixed server flags, and the model file and projector with their SHA-256. The worker SHALL NOT start, adopt or stop a model server. The prompt, page rendering, token limit and Markdown conversion SHALL stay as the PyTorch backend had them.

#### Scenario: The declared runtime matches the pins

- **WHEN** the host reads the `dots-mocr` manifest
- **THEN** the declared program, build, flags, file paths and SHA-256 values SHALL equal the engine's pins
- **AND** the flags SHALL be `--temp 0 -c 24576 -np 1 --image-min-tokens 4 --image-max-tokens 14400`

#### Scenario: The worker starts no server

- **GIVEN** a provisioned `dots-mocr` worker
- **WHEN** it parses a page
- **THEN** it SHALL start no process

### Requirement: The dots-mocr engine SHALL use the runtime URL the host passes

The `dots-mocr` worker SHALL send each page to the server at `OMRS_OCR_RUNTIME_URL`. When the variable is missing or is not a loopback `http` URL, a parse SHALL return a parse error that names the variable.

#### Scenario: Pages go to the passed URL

- **GIVEN** `OMRS_OCR_RUNTIME_URL` names a running server
- **WHEN** the worker parses a page
- **THEN** it SHALL send one chat request for that page to `<url>/v1/chat/completions`

#### Scenario: Missing URL

- **GIVEN** `OMRS_OCR_RUNTIME_URL` is not set
- **WHEN** the worker receives a parse request
- **THEN** it SHALL return a parse error that names `OMRS_OCR_RUNTIME_URL`

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
