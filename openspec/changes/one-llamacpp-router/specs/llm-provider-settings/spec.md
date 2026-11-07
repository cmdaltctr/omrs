## ADDED Requirements

### Requirement: The shipped Chat default is local llama.cpp with no model chosen

With no source set, `answer.provider` SHALL be `llamacpp` and `answer.model` SHALL be empty. Classification SHALL keep `llamacpp_chat_model` `Qwen/Qwen3-4B-GGUF:Q8_0`. Chat SHALL NOT share the classification model unless the user picks it. No shipped default SHALL name Ollama as a provider or an Ollama model tag. `metadata.ollama_classify_model` SHALL default to an empty value. The Ollama provider SHALL stay registered and usable when a user chooses it.

#### Scenario: Fresh install Chat choice

- **WHEN** OMRS starts with no `omrs.jsonc`, no `.env` and no environment value
- **THEN** `GET /v1/settings/chat` MUST report provider `llamacpp` and model `""`
- **AND** the classification model MUST be `Qwen/Qwen3-4B-GGUF:Q8_0`

#### Scenario: Chat with no model

- **WHEN** a user asks a question while `answer.provider` is `llamacpp` and `answer.model` is empty
- **THEN** the answer MUST be a plain setup message that names the setting `answer.model`
- **AND** no request MUST go to the router, and the classification model MUST NOT answer

### Requirement: A llama.cpp judge with no model is not built

When the claim-check judge provider resolves to llama.cpp and `answer.verify_model` is empty, the judge SHALL NOT be built. `GET /v1/settings/judge` SHALL report ready false with reason `no-model`. The judge SHALL NOT use `llamacpp_chat_model` as a fallback.

#### Scenario: Judge on llama.cpp with no model

- **WHEN** `answer.verify_provider` is `llamacpp` and `answer.verify_model` is empty
- **THEN** `GET /v1/settings/judge` MUST report ready false with reason `no-model`
- **AND** a claim check MUST report a setup message that names `answer.verify_model` and MUST NOT send a request to `Qwen/Qwen3-4B-GGUF:Q8_0`

#### Scenario: No Ollama default

- **WHEN** a test reads every shipped default of `Settings` and `defaults.yaml`
- **THEN** no provider default MUST be `ollama` and no model default MUST be an Ollama tag such as `qwen3:4b`
- **AND** the `answer.model` default MUST be empty

#### Scenario: Ollama still opt-in

- **WHEN** the user saves Chat provider `ollama` with model `qwen3:4b`
- **THEN** the save MUST succeed and the next answer MUST go to `ollama_base_url`

## REMOVED Requirements

### Requirement: The llama.cpp provider has a classification address

**Reason**: Classification, Chat and embeddings share the one router address `llamacpp_router_url`. A separate classification address no longer exists.

**Migration**: Remove `LLAMACPP_CLASSIFY_URL` and `llamacpp_classify_url`. Start-up names the retired variable. Make `llamacpp_chat_model` name a router list entry.
