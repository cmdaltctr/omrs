## ADDED Requirements

### Requirement: Local server items probe the router address

The local server list SHALL hold Ollama at `ollama_base_url` and one llama.cpp item at `llamacpp_router_url`. An item SHALL be `ready` when its health request succeeds, and `not-running` when it fails. An item that no setting in force uses SHALL still be listed, with an empty `used_by`. The llama.cpp item's `used_by` SHALL name every setting whose role runs on the router. The response SHALL NOT show a user name or password from an address.

#### Scenario: Ollama running and used

- **WHEN** `embed_provider` is `ollama` and Ollama answers at `http://localhost:11434`
- **THEN** the Ollama item MUST be `ready` and its `used_by` MUST hold `embed_provider`

#### Scenario: llama.cpp not running

- **WHEN** no process listens at `llamacpp_router_url`
- **THEN** the llama.cpp item MUST be `not-running` with the address in its reason

#### Scenario: One llama.cpp item for every role

- **WHEN** embeddings, classification and Chat all run on llama.cpp
- **THEN** the list MUST hold one llama.cpp item, and its `used_by` MUST hold `embed_provider`, `metadata_llm_provider` and `answer.provider`

#### Scenario: Ollama unused

- **WHEN** no setting in force uses Ollama
- **THEN** the Ollama item MUST still be listed with an empty `used_by`

## REMOVED Requirements

### Requirement: Local server items probe the configured address

**Reason**: The separate llama.cpp embedding, Chat and classification addresses are retired. One router address replaces them ("Local server items probe the router address").

**Migration**: None needed. The list shows one llama.cpp item at `llamacpp_router_url`.
