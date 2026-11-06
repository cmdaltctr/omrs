## ADDED Requirements

### Requirement: The shipped Chat default is local llama.cpp

With no source set, `answer.provider` SHALL be `llamacpp` and `answer.model` SHALL be `Qwen/Qwen3-4B-GGUF:Q8_0`, served by the router (capability `llamacpp-router`). No shipped default SHALL name Ollama as a provider or an Ollama model tag. `metadata.ollama_classify_model` SHALL default to an empty value. The Ollama provider SHALL stay registered and usable when a user chooses it.

#### Scenario: Fresh install Chat choice

- **WHEN** OMRS starts with no `omrs.jsonc`, no `.env` and no environment value
- **THEN** `GET /v1/settings/chat` MUST report provider `llamacpp` and model `Qwen/Qwen3-4B-GGUF:Q8_0`

#### Scenario: No Ollama default

- **WHEN** a test reads every shipped default of `Settings` and `defaults.yaml`
- **THEN** no provider default MUST be `ollama` and no model default MUST be an Ollama tag such as `qwen3:4b`

#### Scenario: Ollama still opt-in

- **WHEN** the user saves Chat provider `ollama` with model `qwen3:4b`
- **THEN** the save MUST succeed and the next answer MUST go to `ollama_base_url`

## REMOVED Requirements

### Requirement: The llama.cpp provider has a classification address

**Reason**: Classification, Chat and embeddings share the one router address `llamacpp_router_url`. A separate classification address no longer exists.

**Migration**: Remove `LLAMACPP_CLASSIFY_URL` and `llamacpp_classify_url`. Start-up names the retired variable. Make `llamacpp_chat_model` name a router list entry.
