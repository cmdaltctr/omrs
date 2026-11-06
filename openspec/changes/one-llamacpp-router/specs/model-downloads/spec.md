## MODIFIED Requirements

### Requirement: A llama.cpp download lands where the managed server reads

A llama.cpp download SHALL put the files in the Hugging Face cache. On success the status SHALL give the model value `org/name:LABEL`, the absolute path of the downloaded `.gguf` file in the cache, and its SHA-256. The managed router SHALL load that file by path through a list entry, without a new download.

#### Scenario: Start after download

- **WHEN** the download of `Qwen/Qwen3-4B-GGUF:Q8_0` succeeds and the user adds it to the router list
- **THEN** the router MUST load the model from the cache path without a new download

#### Scenario: Status gives path and hash

- **WHEN** a llama.cpp download succeeds
- **THEN** the status MUST hold the model value, an absolute `.gguf` path inside the cache and a 64-character SHA-256

### Requirement: An external llama.cpp server is told, not controlled

When `llamacpp_router_server` is `external`, the panel SHALL NOT offer Use this model. It SHALL show the cache folder of the file and a Refresh models action that re-reads the server's model list. OMRS SHALL NOT edit the files of the user's server or send a signal to it. The saved mode, not the server state, SHALL decide what the panel offers.

#### Scenario: Llama app after a download

- **WHEN** a llama.cpp download succeeds and the router mode is `external`
- **THEN** the panel MUST show the cache folder and Refresh models, and no Use this model

#### Scenario: New model shows after the server lists it

- **WHEN** the user's server lists `Qwen/Qwen3-1.7B-GGUF:Q8_0` and the user presses Refresh models
- **THEN** the llama.cpp model list MUST include `Qwen/Qwen3-1.7B-GGUF:Q8_0`

#### Scenario: Managed choice with a stopped server

- **WHEN** a llama.cpp download succeeds, the mode is `managed` and the router is `stopped`
- **THEN** the panel MUST offer Use this model, and the entry MUST load on the next request

## ADDED Requirements

### Requirement: Use this model adds or replaces a router list entry

After a llama.cpp download, when the router is `managed`, Use this model SHALL add a router list entry, or replace the file of the entry the user picks, through the router model route with its entry rules and the `credentials` scope. It SHALL record the file's SHA-256. It SHALL NOT change `answer.model` or any other role setting. The download routes SHALL NOT change any setting.

#### Scenario: Adds a list entry

- **WHEN** the router is `managed` and the user presses Use this model after a download of `Qwen/Qwen3-1.7B-GGUF:Q8_0` and picks Add as a new model
- **THEN** `omrs.jsonc` MUST hold a `llamacpp_models` entry with that model, its cache path and its SHA-256, and `answer.model` MUST be unchanged

#### Scenario: Replaces an entry's file

- **WHEN** the user picks the existing entry `qwen3-4b` as the target
- **THEN** that entry's `model`, `file` and `sha256` MUST change, and its preset MUST stay

#### Scenario: No credentials

- **WHEN** a session with `manage` but not `credentials` presses Use this model
- **THEN** the server MUST refuse the save and keep the old list

#### Scenario: Download changes no setting

- **WHEN** a download succeeds
- **THEN** `omrs.jsonc` MUST be unchanged until the user presses Use this model

## REMOVED Requirements

### Requirement: Use this model keeps the model rules

**Reason**: Use this model no longer saves the Chat model. It adds or replaces a router list entry ("Use this model adds or replaces a router list entry").

**Migration**: After Use this model, pick the Chat model in Settings > Chat if the new entry should answer.
