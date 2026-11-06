# llamacpp-router Specification

## Purpose

One llama.cpp router that OMRS runs or connects to. It serves every local llama.cpp model by name (embeddings, classification, Chat, judge and decision models) from a model list in OMRS settings. OCR runtimes stay apart.

## ADDED Requirements

### Requirement: One router serves every local llama.cpp model by name

OMRS SHALL send every llama.cpp request for embeddings, classification, Chat, the claim-check judge and `llamacpp` decision models to `llamacpp_router_url`. Each request SHALL name the model of a list entry in its `model` field. OCR engine runtimes SHALL NOT use the router.

#### Scenario: Embeddings and Chat share one address

- **WHEN** embeddings use `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` and Chat uses `Qwen/Qwen3-4B-GGUF:Q8_0`
- **THEN** both requests MUST go to `llamacpp_router_url`, each with its own model name

#### Scenario: OCR keeps its own server

- **WHEN** the dots.mocr engine runs a page
- **THEN** its request MUST go to its own `ocr-*` runtime and not to the router

### Requirement: Router mode and address settings

The settings SHALL be `llamacpp_router_server` (`managed` or `external`, default `managed`), `llamacpp_router_url` (default `http://127.0.0.1:8080/v1`), `llamacpp_router_models_max` (1 to 16, default 4) and `llamacpp_router_memory_margin_mib` (0 to 262,144, default 8,192). Each SHALL follow the provider source order: environment and `.env` (both lock), `omrs.jsonc` (no lock), default. In `external` mode OMRS SHALL start, adopt and stop nothing.

#### Scenario: Defaults

- **WHEN** no source sets a router setting
- **THEN** the mode MUST be `managed`, the address `http://127.0.0.1:8080/v1`, the model limit 4 and the margin 8,192 MiB

#### Scenario: External Llama app

- **WHEN** `llamacpp_router_server` is `external` and `llamacpp_router_url` is `http://127.0.0.1:9931/v1`
- **THEN** every llama.cpp role MUST send to port 9931 and no process MUST start

#### Scenario: Out of range

- **WHEN** a save sets `llamacpp_router_models_max` to 0
- **THEN** the server MUST return 400 and save nothing

### Requirement: The model list lives in omrs.jsonc

`llamacpp_models` SHALL be a named map in `omrs.jsonc`, keyed by an id of 1 to 40 characters from `a-z`, `0-9` and `-`. Each entry SHALL hold `model`, and in managed mode `file`, with optional `projector`, `sha256`, `projector_sha256` and `preset`. No environment variable SHALL set it. Only `omrs web` SHALL write it. A user map SHALL replace the shipped list as a whole.

#### Scenario: Environment cannot set the list

- **WHEN** the environment holds `LLAMACPP_MODELS`
- **THEN** OMRS MUST ignore it and the list MUST come from `omrs.jsonc` or the shipped list

#### Scenario: CLI reads the list

- **WHEN** the CLI starts the router
- **THEN** it MUST read `llamacpp_models` from `omrs.jsonc` and MUST NOT write `omrs.jsonc`

#### Scenario: User map replaces shipped list

- **WHEN** `omrs.jsonc` holds a `llamacpp_models` map with one entry
- **THEN** the router MUST serve that one entry only

### Requirement: Roles are derived from the role settings

An entry SHALL have the role of each setting that names its `model`: `llamacpp_embed_model` (embeddings), `llamacpp_chat_model` (classification), `answer.model` while `answer.provider` is `llamacpp` (Chat), the judge model while the judge runs on llama.cpp (judge), and each managed `llamacpp` decision entry (decision). A role setting that names no entry SHALL give the reason `model-not-listed` for that role.

#### Scenario: One entry, two roles

- **WHEN** `llamacpp_chat_model` and `answer.model` both name `Qwen/Qwen3-4B-GGUF:Q8_0` and Chat runs on llama.cpp
- **THEN** that entry MUST list the roles Chat and classification

#### Scenario: Unlisted model refused before contact

- **WHEN** the router is managed and `answer.model` names a model that no entry holds
- **THEN** the Chat request MUST fail with reason `model-not-listed` and MUST NOT reach the router

#### Scenario: Embedding entry cannot chat

- **WHEN** a save makes `answer.model` name an entry whose preset has `embeddings` true
- **THEN** the server MUST return 400 with reason `role-mismatch` and save nothing

### Requirement: Entry files follow fixed rules

`model` SHALL be a Hugging Face id `org/name:QUANT` that does not start with `-`. In managed mode `file` SHALL be an absolute path of an existing regular `.gguf` file whose name holds no `mmproj`, and `projector`, when set, an absolute path of an existing `.gguf` file. A save that breaks a rule SHALL return 400 and save nothing. A launch-time failure SHALL fail that entry only.

#### Scenario: Relative file refused

- **WHEN** a save sets `file` to `models/q.gguf`
- **THEN** the server MUST return 400 and save nothing

#### Scenario: Name without tag refused

- **WHEN** a save sets `model` to `Qwen/Qwen3-4B-GGUF`
- **THEN** the server MUST return 400 and save nothing

#### Scenario: Missing file at start

- **WHEN** the router starts and one entry's file no longer exists
- **THEN** that entry MUST be `failed` with reason `model-invalid` and every other entry MUST stay usable

### Requirement: The preset file holds allow-listed keys only

OMRS SHALL write `models.ini` in the router state folder from the list, one section per entry named by `model`, with `model = <file>` and `mmproj = <projector>`. It SHALL write only the allow-listed preset keys, each typed and range-checked. Any other key SHALL be refused with 400 `preset-key-unknown`.

#### Scenario: Allowed keys

- **WHEN** a save sets any of `ctx-size`, `batch-size`, `ubatch-size`, `parallel`, `embeddings`, `pooling`, `embd-normalize`, `kv-unified`, `flash-attn`, `n-gpu-layers`, `fit`, `cache-type-k`, `cache-type-v`, `cache-prompt`, `cache-reuse`, `image-min-tokens` or `image-max-tokens` with a value in its range
- **THEN** the server MUST accept it and `models.ini` MUST hold it in the entry's section

#### Scenario: Section loads by file path

- **WHEN** the entry `Qwen/Qwen3-4B-GGUF:Q8_0` has file `/m/Qwen3-4B-Q8_0.gguf`
- **THEN** `models.ini` MUST hold a section `[Qwen/Qwen3-4B-GGUF:Q8_0]` with `model = /m/Qwen3-4B-Q8_0.gguf`

#### Scenario: Reserved key refused

- **WHEN** a save sets the preset key `sleep-idle-seconds`, `api-key`, `host` or `port`
- **THEN** the server MUST return 400 `preset-key-unknown` and MUST NOT change `omrs.jsonc` or `models.ini`

#### Scenario: Free text refused

- **WHEN** a save sets `pooling` to `last --api-key x`
- **THEN** the server MUST return 400 and save nothing

#### Scenario: Live-server check reads the path

- **WHEN** `verify_llamacpp_runtime` reads `GET /v1/models` from the managed router
- **THEN** each loaded entry's `status.args` MUST hold `-m` or `--model` followed by the entry's `file`

### Requirement: Embedding entries set their pooling and sizes explicitly

An entry used for embeddings SHALL have `embeddings` true and SHALL set `pooling`, `ctx-size`, `batch-size` and `ubatch-size` in its preset. `ubatch-size` SHALL NOT exceed `batch-size`. A save or launch that breaks this SHALL fail with reason `preset-invalid`.

#### Scenario: Missing pooling

- **WHEN** a save makes `llamacpp_embed_model` name an entry with no `pooling`
- **THEN** the server MUST return 400 with reason `preset-invalid`

#### Scenario: Shipped embedding preset

- **WHEN** the shipped list is in force
- **THEN** the embedding section MUST hold `embeddings = true`, `pooling = last`, `ctx-size = 8192`, `batch-size = 8192` and `ubatch-size = 8192`

### Requirement: Listed files are checked against their recorded SHA-256

When an entry records `sha256` or `projector_sha256`, OMRS SHALL compare the file with it before each router start and before each preset rewrite. A mismatch SHALL leave that entry out of `models.ini` with reason `file-changed` and a reason line that names the file. Other entries SHALL keep working. An entry with no recorded value SHALL run with the note "File not checked", except a decision entry, which SHALL be refused.

#### Scenario: Changed file isolated

- **WHEN** the Chat entry's file no longer matches its recorded SHA-256
- **THEN** the Chat entry MUST be `failed` `file-changed` and embedding requests MUST still succeed

#### Scenario: Use this model records the hash

- **WHEN** the user adds an entry through Use this model
- **THEN** `omrs.jsonc` MUST hold the entry's `sha256`

### Requirement: A preset edit reloads only the changed model

When an entry's file, projector or preset changes while the router runs, OMRS SHALL rewrite only that entry's section and ask the router to reload its presets, so that only the changed model unloads. When another OMRS process uses the changed model, the change SHALL fail for that model with reason `version-busy` and other models SHALL keep running. A change of the router's own arguments SHALL restart the router.

#### Scenario: Context size edit

- **WHEN** the router serves the embedding and Chat models and the user changes the Chat entry's `ctx-size`
- **THEN** the embedding model MUST stay loaded and the next Chat request MUST load the Chat model with the new value

#### Scenario: Model in use elsewhere

- **WHEN** the CLI uses the Chat model and the web app wants a different preset for it
- **THEN** the web app's Chat request MUST fail with `version-busy` and embedding requests MUST succeed

#### Scenario: Model limit edit

- **WHEN** the user changes `llamacpp_router_models_max` and presses Restart
- **THEN** the router MUST restart with the new `--models-max` value

### Requirement: A model is made ready before its request is timed

Before the first request to a model in a lease, OMRS SHALL read the model's status and, when it is not loaded, ask the router to load it and wait up to 300 seconds for `loaded`. 300 seconds SHALL be a fixed constant. The request's own timeout SHALL start after the model is loaded. A failed load SHALL give reason `model-load-failed` for that model only.

#### Scenario: Slow load does not eat the decision timeout

- **WHEN** Clef-Flash takes 40 seconds to load and its decision request has a 120-second timeout
- **THEN** the request MUST succeed and its timeout MUST start after the load ends

#### Scenario: Load failure isolated

- **WHEN** the decision model fails to load
- **THEN** its requests MUST fail with `model-load-failed` and embedding requests MUST succeed

### Requirement: One-slot models wait for their own request lock

An entry with `parallel` 1 SHALL be a one-slot model. Each OMRS request to it SHALL hold that model's `request.lock` exclusive while it runs. Requests to other models SHALL NOT wait for it. The request timeout SHALL start when the lock is held.

#### Scenario: Decision requests do not block embeddings

- **WHEN** process A holds a decision request on the one-slot Clef-Flash entry and process B sends an embedding request
- **THEN** process B's request MUST start without waiting for A

#### Scenario: Second decision request waits

- **WHEN** two processes send requests to the one-slot Clef-Flash entry at once
- **THEN** the second MUST start after the first ends and MUST NOT time out because of the wait

### Requirement: Decision models run on the router

A `decision_models` entry with kind `llamacpp` and `server` `managed` SHALL name a list entry by `model`. That list entry SHALL hold `projector` for an image model and `parallel` 1. The router SHALL forward `POST /v1/systemone` by model. When any decision entry is listed, a router build below b11941 SHALL be refused with `wrong-build`. The decision fields `model_file`, `projector_file`, `model_sha256` and `projector_sha256` SHALL be reported as moved to `llamacpp_models`.

#### Scenario: Clef-Flash on the router

- **GIVEN** a managed decision entry that names a list entry with a Q8_0 file and a projector
- **WHEN** the document router asks it a page question
- **THEN** the request MUST go to `llamacpp_router_url` `/v1/systemone` with that model name
- **AND** the projector smoke test MUST pass through the router

#### Scenario: Old decision file field

- **WHEN** `omrs.jsonc` holds `decision_models.clef-local.model_file`
- **THEN** the problem list MUST name the field and `llamacpp_models` as its new place

### Requirement: Memory limits bound the loaded models

The router SHALL start with `--models-max` from `llamacpp_router_models_max` and `--models-memory-margin` from `llamacpp_router_memory_margin_mib`. The router item's memory SHALL be the sum of the router's resident memory and that of its direct child processes whose command line holds the recorded binary path.

#### Scenario: Memory sums children

- **WHEN** the router runs two loaded models as child processes
- **THEN** the router item's `memory_bytes` MUST be the sum of the three resident sizes

### Requirement: OMRS provisions a pinned llama.cpp build on request

On request only, OMRS SHALL download llama.cpp build b11941 for the host platform, check its SHA-256 and place `llama-server` in the OMRS data folder. Pinned archives SHALL exist for macOS arm64, Linux x86-64 CPU and Linux x86-64 CUDA 12.8. A blank `llamacpp_server_binary` SHALL mean the provisioned binary. A set path SHALL keep the program rule and SHALL be refused below build b11941 with `wrong-build`. The CLI SHALL offer `omrs llamacpp install [--flavour cpu|cuda]`.

#### Scenario: Hash mismatch

- **WHEN** the downloaded archive does not match its pinned SHA-256
- **THEN** the job MUST fail with reason `file-changed` and MUST NOT place any binary

#### Scenario: Headless pod

- **WHEN** a user runs `omrs llamacpp install --flavour cuda` on Linux x86-64
- **THEN** the CUDA 12.8 archive and its runtime archive MUST be checked and placed, and no server MUST start

#### Scenario: Unpinned platform

- **WHEN** the host is macOS x86-64
- **THEN** the job MUST fail with reason `not-supported` and the user path MUST stay allowed

#### Scenario: Old user build

- **WHEN** `llamacpp_server_binary` names a build 11510 binary
- **THEN** the router MUST be `failed` with `wrong-build` and no process MUST start

### Requirement: Shipped local defaults use llama.cpp

With no source set, the shipped list SHALL hold `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` (embeddings preset of this spec) and `Qwen/Qwen3-4B-GGUF:Q8_0` (`ctx-size` 32,768, `parallel` 2), both with no file. `llamacpp_embed_model` and `llamacpp_chat_model` SHALL name them. An entry with no file SHALL show the state "Not downloaded", SHALL NOT be written to `models.ini`, and SHALL download automatically when the router first needs it.

#### Scenario: Fresh install

- **WHEN** OMRS starts with no `omrs.jsonc`
- **THEN** the Router panel MUST list both entries as "Not downloaded" until the router first needs them, then download them automatically

#### Scenario: Embedding identity string

- **WHEN** a collection is ingested with the shipped defaults
- **THEN** its stamped embedding identity MUST be provider `llamacpp` and model `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0`

### Requirement: A listed model with no file downloads automatically

When the managed router starts, or a listed entry is first needed, and the entry has no downloaded file, OMRS SHALL download it automatically through the Get a model download job (ADR-106): pinned revision, progress shown, cancellable. When the download completes, OMRS SHALL record the file path and its SHA-256, write the entry to `models.ini` by absolute file path and load it. A download in progress SHALL NOT count against the router start wait or the model load wait.

#### Scenario: First start downloads missing models

- **WHEN** the managed router starts and `Qwen/Qwen3-4B-GGUF:Q8_0` has no file in the cache
- **THEN** OMRS MUST start its download job, show progress on the Router panel, and load the model by file path once the download completes

#### Scenario: A slow download does not time out the router

- **WHEN** a listed model is still downloading after the router start wait has passed
- **THEN** the router MUST NOT be reported as `timeout`, and the entry MUST show "Downloading" with progress

#### Scenario: Headless install downloads too

- **WHEN** `omrs llamacpp install` runs on a machine with listed models missing
- **THEN** it MUST download each missing model after the binary and print progress to the log
