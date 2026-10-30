## ADDED Requirements

### Requirement: The llama.cpp provider has a classification address

The llama.cpp provider SHALL have the address `llamacpp_classify_url` (env `LLAMACPP_CLASSIFY_URL`) for classification. When no source sets it, classification SHALL use `llamacpp_chat_url`. The sources SHALL follow the provider source order: the environment and `.env` (both lock), then `omrs.jsonc`, then the Chat address. The address SHALL follow the provider address rules. A saved change SHALL apply from the next request with no restart.

#### Scenario: Upgrade keeps classification where it was

- **WHEN** `omrs.jsonc` sets `llamacpp_chat_url` to `http://127.0.0.1:9931/v1` and no source sets `llamacpp_classify_url`
- **THEN** classification requests MUST go to `http://127.0.0.1:9931/v1`
- **AND** `GET /v1/connections` MUST report the classification address `http://127.0.0.1:9931/v1` with the source `default`

#### Scenario: Separate addresses

- **WHEN** `llamacpp_classify_url` is `http://127.0.0.1:9931/v1` and `llamacpp_chat_url` is `http://127.0.0.1:8081/v1`
- **THEN** classification requests MUST go to port 9931 and llama.cpp Chat answers MUST go to port 8081

#### Scenario: Environment locks the address

- **WHEN** `LLAMACPP_CLASSIFY_URL` is in the environment and the user saves another classification address
- **THEN** the server MUST return 409 and name the variable

#### Scenario: Wrong scheme

- **WHEN** the user saves the classification address `file:///etc/passwd`
- **THEN** the server MUST return 400, save nothing and send no request

### Requirement: A llama.cpp answer role needs its own model

When the Chat provider is `llamacpp` and the Chat model in force is empty, Chat SHALL refuse with a reason that says "Choose a Chat model" and SHALL send no request to any llama.cpp server. A llama.cpp answer role SHALL NOT use `llamacpp_chat_model`, which is the classification model. Classification SHALL keep `llamacpp_chat_model`.

#### Scenario: Empty Chat model refused

- **WHEN** the Chat provider is `llamacpp`, `ANSWER__MODEL` is empty and the user asks a question
- **THEN** the answer MUST fail with a message that says "Choose a Chat model", and no request MUST reach a llama.cpp server

#### Scenario: Classification keeps the Text model

- **WHEN** a document is classified with `METADATA_LLM_PROVIDER=local` and `LOCAL_BACKEND=llamacpp`
- **THEN** the request model MUST be `llamacpp_chat_model`

### Requirement: The llama.cpp Chat test checks the server's model list

When the Chat provider is `llamacpp` and the Chat server choice is `external`, a Chat model test SHALL first read the model list at the Chat address. When the list is readable and does not hold the model, the test SHALL return ok false with the reason `model-not-listed` and SHALL send no prompt. When the choice is `managed`, the test SHALL skip the list check.

#### Scenario: Name not listed

- **WHEN** the Llama app lists only `Qwen/Qwen3-0.6B-GGUF:Q8_0` and the user tests the llama.cpp model `qwen3:4b`
- **THEN** the test MUST return ok false with the reason `model-not-listed` and MUST send no prompt

#### Scenario: Name listed

- **WHEN** the server lists `Qwen/Qwen3-0.6B-GGUF:Q8_0` and the user tests that model
- **THEN** the test MUST send the short prompt and report its result

#### Scenario: Managed server skips the check

- **WHEN** the choice is `managed` and the user tests the llama.cpp Chat model
- **THEN** the test MUST NOT read the model list before the prompt

## MODIFIED Requirements

### Requirement: The Chat status says whether Chat is ready

`GET /v1/settings/chat` SHALL return the Chat provider, the model name, their source, whether the choice is locked, and whether Chat is ready. When Chat is not ready, it SHALL give a reason from a fixed set: `disabled`, `unknown-provider`, `not-installed`, `not-configured` (a required value, such as a key that the provider needs, is missing) and `no-model` (the Chat model in force is empty). The server SHALL NOT contact a provider for this route.

#### Scenario: Not ready without a key

- **WHEN** the Chat provider is `openrouter` and no OpenRouter key is set
- **THEN** `GET /v1/settings/chat` MUST report ready false with the reason `not-configured`

#### Scenario: Registry providers other than the first three

- **WHEN** the Chat provider is `anthropic` or `openai_compatible`
- **THEN** `GET /v1/settings/chat` MUST decide readiness from the descriptor of that provider, with no branch on the provider name

#### Scenario: Answering turned off

- **WHEN** `ANSWER__ENABLED` is false
- **THEN** `GET /v1/settings/chat` MUST report ready false with the reason `disabled`

#### Scenario: No provider request

- **WHEN** the Chat section or the Chat view reads `GET /v1/settings/chat`
- **THEN** the server MUST NOT send any request to a provider

#### Scenario: Empty Chat model

- **WHEN** the Chat provider is `llamacpp` and the Chat model in force is empty
- **THEN** `GET /v1/settings/chat` MUST report ready false with the reason `no-model`
