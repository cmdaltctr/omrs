## MODIFIED Requirements

### Requirement: Local server items probe the configured address

The local server list SHALL hold Ollama at `ollama_base_url` and llama.cpp at `llamacpp_embed_url` and `llamacpp_chat_url`, and at the classification address when it differs from `llamacpp_chat_url`. An item SHALL be `ready` when its health request succeeds, and `not-running` when it fails. An item that no setting in force uses SHALL still be listed, with an empty `used_by`. The response SHALL NOT show a user name or password from an address.

#### Scenario: Ollama running and used

- **WHEN** `embed_provider` is `ollama` and Ollama answers at `http://localhost:11434`
- **THEN** the Ollama item MUST be `ready` and its `used_by` MUST hold `embed_provider`

#### Scenario: llama.cpp not running

- **WHEN** no process listens at `llamacpp_chat_url`
- **THEN** the llama.cpp chat item MUST be `not-running` with the address in its reason

#### Scenario: Separate classification address

- **WHEN** `llamacpp_classify_url` is `http://127.0.0.1:9931/v1`, `llamacpp_chat_url` is `http://127.0.0.1:8081/v1` and metadata extraction uses llama.cpp
- **THEN** the list MUST hold a llama.cpp classification item at port 9931 whose `used_by` holds `metadata_llm_provider`
- **AND** the `used_by` of the llama.cpp chat item MUST NOT hold `metadata_llm_provider`

#### Scenario: Classification follows the Chat address

- **WHEN** no source sets `llamacpp_classify_url` and metadata extraction uses llama.cpp
- **THEN** the list MUST hold no classification item, and the `used_by` of the llama.cpp chat item MUST hold `metadata_llm_provider`
