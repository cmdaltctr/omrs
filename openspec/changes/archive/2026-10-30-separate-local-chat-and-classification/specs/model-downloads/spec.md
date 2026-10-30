## MODIFIED Requirements

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
