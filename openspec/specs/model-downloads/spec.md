# model-downloads Specification

## Purpose
Lets a user of `omrs web` find a local model, see its downloadable files, and download one into the llama.cpp cache or into Ollama, with progress, cancel and fixed guardrails on names, sizes, scopes and network use.

## Requirements

### Requirement: A provider declares its model source

A provider SHALL offer model search and download only when its registry entry declares a model source. The llama.cpp provider SHALL declare the Hugging Face GGUF source. The Ollama provider SHALL declare the Ollama pull source. A provider with no source SHALL show no Get a model panel, and the download routes SHALL refuse it with 400.

#### Scenario: Cards with a source

- **WHEN** the user opens Settings > Providers
- **THEN** the llama.cpp card and the Ollama card MUST each show a Get a model panel

#### Scenario: Card without a source

- **WHEN** the user opens the OpenRouter card
- **THEN** the card MUST NOT show a Get a model panel

#### Scenario: Route refuses a provider without a source

- **WHEN** a client sends `POST /v1/model-downloads` with the provider `openrouter`
- **THEN** the server MUST return 400 and start no job

### Requirement: The server contacts the model host only on request

The server SHALL contact `huggingface.co`, or the Ollama address for a pull, only to answer a search, a file list or a download that the user asked for. The server SHALL NOT contact these hosts at start-up, on a page load or in the background. The stdio MCP server and the CLI SHALL NOT expose search or download.

#### Scenario: Start-up makes no request

- **WHEN** `omrs web` starts and the user opens Settings > Providers without typing a search
- **THEN** the server MUST send no request to `huggingface.co`

#### Scenario: Search sends one request

- **WHEN** the user searches for `qwen3`
- **THEN** the server MUST send one search request to the Hugging Face API

### Requirement: Search returns GGUF repos sorted by downloads

`GET /v1/model-downloads/search` SHALL take a provider and a query of 1 to 100 characters with no control characters. For llama.cpp it SHALL return at most 20 Hugging Face repos that hold GGUF files, sorted by downloads, each with its id, downloads, likes, gated flag and last change date. A query that breaks the rule SHALL give 400.

#### Scenario: Matching repos

- **WHEN** the user searches `qwen3` for llama.cpp
- **THEN** every result MUST be a repo tagged GGUF, and the results MUST be in order of downloads, highest first

#### Scenario: Empty query

- **WHEN** the query is empty or longer than 100 characters
- **THEN** the server MUST return 400 and send no request to Hugging Face

#### Scenario: Host not reachable

- **WHEN** Hugging Face does not answer within 10 seconds
- **THEN** the server MUST return the reason `network` and an empty list

### Requirement: Ollama search adds the built-in names

For Ollama the search SHALL return the built-in Ollama library names that contain the query, first, followed by the Hugging Face GGUF results written as `hf.co/{org}/{repo}`. The built-in list SHALL be fixed data in the code. The server SHALL NOT read ollama.com pages.

#### Scenario: Built-in name first

- **WHEN** the user searches `qwen3` for Ollama
- **THEN** the first results MUST include the built-in names that contain `qwen3`, and the Hugging Face results MUST start with `hf.co/`

#### Scenario: No scraping

- **WHEN** the user searches for Ollama
- **THEN** the server MUST send no request to `ollama.com`

### Requirement: The file list groups GGUF files by quantisation

`GET /v1/model-downloads/files` SHALL return the GGUF files of one repo at one fixed revision. Each entry SHALL give a quantisation label, the file names and the total size in bytes. Parts of one split model SHALL form one entry. Projector files (`mmproj`) SHALL be left out. The response SHALL name the revision so that the download gets the same files.

#### Scenario: Sizes and labels

- **WHEN** the user opens `unsloth/Qwen3-4B-GGUF`
- **THEN** the list MUST hold an entry `Q4_K_M` with its file name and size in bytes, and MUST hold no `mmproj` file

#### Scenario: Split model

- **WHEN** a repo holds `model-Q8_0-00001-of-00002.gguf` and `model-Q8_0-00002-of-00002.gguf`
- **THEN** the list MUST hold one `Q8_0` entry with both file names and the sum of their sizes

#### Scenario: Unknown repo

- **WHEN** the repo does not exist or holds no GGUF file
- **THEN** the server MUST return 404 with the reason `not-found`

### Requirement: Names follow fixed rules

The server SHALL accept a repo id only in the form `org/name` with letters, digits, `.`, `_` and `-`, a quantisation label only from letters, digits, `_` and `-`, and an Ollama name only in the form `name`, `name:tag`, `namespace/name:tag` or `hf.co/org/name:tag`. No value SHALL start with `-`. A value that breaks a rule SHALL give 400 and SHALL NOT reach a request or a file path.

#### Scenario: Bad repo id

- **WHEN** the repo is `../x`, `org/`, `a b` or `--help`
- **THEN** the server MUST return 400

#### Scenario: Bad Ollama name

- **WHEN** the Ollama name holds a space, a `;` or starts with `-`
- **THEN** the server MUST return 400

### Requirement: One download runs at a time

The web server SHALL run at most one model download at a time. `POST /v1/model-downloads` SHALL start a job and return 202. A start while a job runs SHALL return 409 with the reason `busy`. The job state SHALL live in memory, so a server restart shows `idle`.

#### Scenario: Second start refused

- **WHEN** a download runs and the user starts another one
- **THEN** the server MUST return 409 with the reason `busy` and keep the first job running

### Requirement: The job reports byte progress

`GET /v1/model-downloads/current` SHALL return the state (`idle`, `running`, `succeeded`, `failed` or `cancelled`), the provider, the model, the bytes done, the bytes in total when known, and on failure one reason from a fixed set. The reasons SHALL be `busy`, `no-space`, `gated`, `not-found`, `network`, `stalled`, `ollama-unreachable` and `failed`. No route SHALL return raw output, a stack trace or a token.

#### Scenario: Progress grows

- **WHEN** a llama.cpp download of 2,497,280,000 bytes runs
- **THEN** successive status reads MUST show bytes done that grow toward 2,497,280,000

#### Scenario: Stalled download

- **WHEN** no byte arrives for 60 seconds
- **THEN** the job MUST stop with the state `failed` and the reason `stalled`

### Requirement: The user can cancel a download

`DELETE /v1/model-downloads/current` SHALL stop a running job and set the state `cancelled`. A cancelled llama.cpp download SHALL leave no partial file in the cache, so a later download of the same file starts again. A cancelled Ollama pull SHALL leave its partial layers to Ollama, so a later pull of the same name continues from them. A cancel with no running job SHALL return 409.

#### Scenario: Cancel

- **WHEN** the user presses Cancel during a download
- **THEN** the job MUST stop within 5 seconds and the state MUST be `cancelled`

#### Scenario: Shutdown stops the job

- **WHEN** `omrs web` shuts down during a download
- **THEN** the server MUST stop the download before it exits

### Requirement: Free space is checked first

Before a llama.cpp download the server SHALL compare the size still to download with the free space of the cache disk. When the free space is smaller than that size plus 1 GiB, the server SHALL refuse the start with 409 and the reason `no-space`, and SHALL state both sizes.

#### Scenario: Disk too small

- **WHEN** the file set needs 9.7 GB and the cache disk has 5 GB free
- **THEN** the server MUST return 409 with the reason `no-space` and start no job

#### Scenario: Already cached

- **WHEN** every file of the set is already in the cache
- **THEN** the job MUST succeed with no new bytes and no space refusal

### Requirement: A gated repo needs a token

The search and the file list SHALL show whether a repo is gated. A download from a gated repo SHALL need `HF_TOKEN` in the environment of `omrs web`. Without it the start SHALL return 409 with the reason `gated`. The server SHALL NOT store, return or log the token.

#### Scenario: Gated without token

- **WHEN** the repo is gated and `HF_TOKEN` is not set
- **THEN** the server MUST return 409 with the reason `gated`

#### Scenario: Token never returned

- **WHEN** `HF_TOKEN` is set and the user reads any download route
- **THEN** no response body and no log line MUST hold the token

### Requirement: A llama.cpp download lands where the managed server reads

A llama.cpp download SHALL put the files in the cache that the managed `llama-server` reads for a Hugging Face id. On success the status SHALL give the model value `org/name:LABEL`, and the server SHALL start the managed server with that value without a new download.

#### Scenario: Start after download

- **WHEN** the download of `unsloth/Qwen3-4B-GGUF:Q4_K_M` succeeds and the user saves that model as the Chat model and restarts OMRS's own server
- **THEN** the managed server MUST reach `running` without a new download

### Requirement: Use this model keeps the model rules

After a llama.cpp download, when the Chat server choice is `managed`, Use this model SHALL save the model value as the Chat model, with the provider `llamacpp`, through the Chat save route, with its model rule and the `credentials` scope. It SHALL then offer Restart. The download routes SHALL NOT change any setting.

#### Scenario: Saves the Chat model

- **WHEN** the choice is `managed` and the user presses Use this model after a download of `unsloth/Qwen3-4B-GGUF:Q4_K_M`
- **THEN** `omrs.jsonc` MUST hold `answer.provider` `llamacpp` and `answer.model` `unsloth/Qwen3-4B-GGUF:Q4_K_M`, and MUST NOT hold `llamacpp_server_model`

#### Scenario: No credentials

- **WHEN** a session with `manage` but not `credentials` presses Use this model
- **THEN** the server MUST refuse the save and keep the old Chat model

#### Scenario: Download changes no setting

- **WHEN** a download succeeds
- **THEN** `omrs.jsonc` MUST be unchanged until the user presses Use this model

### Requirement: An external llama.cpp server is told, not controlled

When the Chat server choice is `external`, the panel SHALL NOT offer Use this model. It SHALL show the cache folder of the file and a Refresh models action that re-reads the existing model list. OMRS SHALL NOT edit the files of the user's server or send a signal to it. The saved choice, not the server state, SHALL decide what the panel offers.

#### Scenario: Llama app after a download

- **WHEN** a llama.cpp download succeeds and the choice is `external`
- **THEN** the panel MUST show the cache folder and Refresh models, and no Use this model

#### Scenario: New model shows after the server lists it

- **WHEN** the user's server lists `Qwen/Qwen3-1.7B-GGUF:Q8_0` and the user presses Refresh models
- **THEN** the llama.cpp model list MUST include `Qwen/Qwen3-1.7B-GGUF:Q8_0`

#### Scenario: Managed choice with a stopped server

- **WHEN** a llama.cpp download succeeds, the choice is `managed` and the owned server is `stopped`
- **THEN** the panel MUST offer Use this model, and its Restart MUST stay disabled until the server runs

### Requirement: An Ollama pull goes to the configured Ollama

An Ollama download SHALL send one pull request to the Ollama address in use and relay its progress. On success the model SHALL appear in the existing Ollama model list. When Ollama does not answer, the job SHALL fail with the reason `ollama-unreachable`.

#### Scenario: Pull succeeds

- **WHEN** the user downloads `qwen3:4b` for Ollama
- **THEN** the job MUST succeed and the next Ollama model list MUST hold `qwen3:4b`

#### Scenario: Ollama down

- **WHEN** nothing listens at the Ollama address
- **THEN** the job MUST fail with the reason `ollama-unreachable`

### Requirement: Scopes for search and download

Every model download route SHALL need the browser session with the `manage` scope. A bearer token SHALL NOT pass any of them. The routes SHALL appear in `openapi.yaml`.

#### Scenario: Bearer token refused

- **WHEN** a client uses a bearer token on `POST /v1/model-downloads`
- **THEN** the server MUST refuse the request and start no job

#### Scenario: Contract

- **WHEN** the OpenAPI contract test runs
- **THEN** the search, file list, start, status and cancel routes MUST be present and match the responses
