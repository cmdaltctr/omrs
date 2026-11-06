## MODIFIED Requirements

### Requirement: Inference backend selection

The system SHALL select the embedding provider via the `EMBED_PROVIDER` environment variable. The accepted values SHALL be `local` (the default), `cloud`, `ollama`, `llamacpp`, and `openrouter`. The default `LOCAL_BACKEND` SHALL be `llamacpp`.

#### Scenario: Default provider is local

- **WHEN** `EMBED_PROVIDER` is not set and `INFERENCE_BACKEND` is not set
- **THEN** the system SHALL use `local` as the embedding provider
- **THEN** the concrete backend SHALL be resolved from `LOCAL_BACKEND`, which defaults to `llamacpp`

#### Scenario: Explicit ollama provider

- **WHEN** `EMBED_PROVIDER=ollama`
- **THEN** the system SHALL use `OllamaEmbedding` with `OLLAMA_BASE_URL` and `EMBED_MODEL`

#### Scenario: llamacpp provider selected

- **WHEN** `EMBED_PROVIDER=llamacpp`
- **THEN** the system SHALL use `OpenAILikeEmbedding` with `LLAMACPP_ROUTER_URL` and `LLAMACPP_EMBED_MODEL`

#### Scenario: openrouter provider selected

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `OPENROUTER_API_KEY` and `OPENROUTER_EMBED_MODEL` are set
- **THEN** the system SHALL use `OpenAILikeEmbedding` with `api_base=https://openrouter.ai/api/v1`

#### Scenario: llamacpp provider but optional deps not installed

- **WHEN** `EMBED_PROVIDER=llamacpp`
- **AND** `llama-index-embeddings-openai-like` is not installed
- **THEN** the system SHALL raise an `ImportError` instructing the user to run `uv sync --extra llamacpp`

### Requirement: llamacpp embedding configuration

When the effective embedding provider is `llamacpp`, the system SHALL send embedding requests to `llamacpp_router_url` (default `http://127.0.0.1:8080/v1`) with the model name `llamacpp_embed_model` (default `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0`), and reuse `INGESTION__EMBED_BATCH_SIZE` for batch size. The `OpenAILikeEmbedding` instance SHALL be configured with `api_key="no-key"` since `llama-server` does not require authentication.

#### Scenario: Embedding server reachable

- **WHEN** the effective embedding provider is `llamacpp`
- **AND** `LLAMACPP_ROUTER_URL=http://127.0.0.1:8080/v1`
- **AND** `LLAMACPP_EMBED_MODEL=Qwen/Qwen3-Embedding-4B-GGUF:Q8_0`
- **THEN** embedding requests SHALL be sent to `http://127.0.0.1:8080/v1/embeddings` with the model `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0`

#### Scenario: Custom embed URL

- **WHEN** `llamacpp_router_server` is `external` and `llamacpp_router_url` is `http://127.0.0.1:9931/v1`
- **THEN** embedding requests SHALL target `http://127.0.0.1:9931/v1/embeddings`

### Requirement: llamacpp chat configuration for metadata extraction

When the metadata language model resolves to llama.cpp and `METADATA__EXTRACTION_MODE` is `ollama` or `llamaindex`, the system SHALL send language model calls to `llamacpp_router_url` with the model name `llamacpp_chat_model`. The `ollama` metadata mode SHALL use `httpx` to call `/v1/chat/completions` with the OpenAI chat format. The `llamaindex` metadata mode SHALL use `OpenAILike` LLM from `llama-index-llms-openai-like`.

#### Scenario: ollama metadata mode with llamacpp backend

- **WHEN** the metadata language model resolves to llama.cpp
- **AND** `METADATA__EXTRACTION_MODE=ollama`
- **THEN** the system SHALL POST to `{LLAMACPP_ROUTER_URL}/chat/completions`
- **THEN** the request body SHALL follow OpenAI chat format with `model`, `messages`, and `stream: false`
- **THEN** the response SHALL be parsed from `choices[0].message.content`

#### Scenario: llamaindex metadata mode with llamacpp backend

- **WHEN** the metadata language model resolves to llama.cpp
- **AND** `METADATA__EXTRACTION_MODE=llamaindex`
- **THEN** the LLM SHALL be `OpenAILike` with `api_base=LLAMACPP_ROUTER_URL` and `model=LLAMACPP_CHAT_MODEL`
- **THEN** the extraction pipeline SHALL use this LLM for `TitleExtractor`, `KeywordExtractor`, and `SummaryExtractor`

#### Scenario: llamaindex mode with llamacpp but openai-like not installed

- **WHEN** the metadata language model resolves to llama.cpp
- **AND** `METADATA__EXTRACTION_MODE=llamaindex`
- **AND** `llama-index-llms-openai-like` is not installed
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL fall back to the `ollama` metadata mode (which uses raw `httpx`) against `LLAMACPP_ROUTER_URL`
