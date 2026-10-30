## MODIFIED Requirements

### Requirement: Local llama.cpp classification uses the chat completions endpoint

When `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=llamacpp`, the system SHALL use the OpenAI-compatible `/v1/chat/completions` endpoint at the classification address with the model specified by `LLAMACPP_CHAT_MODEL`. The classification address SHALL be `LLAMACPP_CLASSIFY_URL`, or `LLAMACPP_CHAT_URL` when no source sets it.

#### Scenario: llama.cpp backend uses the chat completions endpoint

- **WHEN** `METADATA__EXTRACTION_MODE` is `"local"`
- **AND** `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=llamacpp`
- **AND** no source sets `LLAMACPP_CLASSIFY_URL`
- **THEN** the system SHALL use the OpenAI-compatible `/v1/chat/completions` endpoint at `LLAMACPP_CHAT_URL` with the model specified by `LLAMACPP_CHAT_MODEL`

#### Scenario: Classification address set

- **WHEN** `METADATA__EXTRACTION_MODE` is `"local"`
- **AND** `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=llamacpp`
- **AND** `LLAMACPP_CLASSIFY_URL=http://127.0.0.1:9931/v1` and `LLAMACPP_CHAT_URL=http://127.0.0.1:8081/v1`
- **THEN** the system SHALL send each classification request to `http://127.0.0.1:9931/v1/chat/completions` and none to port 8081
- **AND** the request model SHALL be `LLAMACPP_CHAT_MODEL`, never `ANSWER__MODEL`

### Requirement: The llamaindex extraction LLM follows METADATA_LLM_PROVIDER

The LLM SHALL be selected by `METADATA_LLM_PROVIDER`: when `ollama`, the system SHALL use `Ollama` from `llama-index-llms-ollama` with `METADATA__OLLAMA_CLASSIFY_MODEL`; when `llamacpp`, the system SHALL use `OpenAILike` from `llama-index-llms-openai-like` with the classification address and `LLAMACPP_CHAT_MODEL`; when `openrouter`, the system SHALL use `OpenAILike` with `api_base=https://openrouter.ai/api/v1`, `api_key=OPENROUTER_API_KEY`, and `model=OPENROUTER_LLM_MODEL`.

#### Scenario: Successful LlamaIndex extraction with ollama provider

- **WHEN** `METADATA__EXTRACTION_MODE=llamaindex`
- **AND** `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=ollama`
- **AND** `llama-index-llms-ollama` is installed and Ollama is reachable
- **THEN** `extract_metadata()` SHALL return a dict containing `category`, `keywords`, `summary`, and optionally `document_title`
- **THEN** the system SHALL use `IngestionPipeline` with at least `TitleExtractor` and `KeywordExtractor`

#### Scenario: Successful LlamaIndex extraction with llamacpp provider

- **WHEN** `METADATA__EXTRACTION_MODE=llamaindex`
- **AND** `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=llamacpp`
- **AND** `llama-index-llms-openai-like` is installed and llama-server is reachable
- **THEN** `extract_metadata()` SHALL return a dict containing `category`, `keywords`, `summary`, and optionally `document_title`
- **THEN** the LLM SHALL be `OpenAILike` configured with the classification address and `LLAMACPP_CHAT_MODEL`

#### Scenario: Successful LlamaIndex extraction with openrouter provider

- **WHEN** `METADATA__EXTRACTION_MODE=llamaindex`
- **AND** `METADATA_LLM_PROVIDER=cloud` with `CLOUD_BACKEND=openrouter`
- **AND** `llama-index-llms-openai-like` is installed and `OPENROUTER_API_KEY` is set
- **THEN** `extract_metadata()` SHALL return a dict containing `category`, `keywords`, `summary`, and optionally `document_title`
- **THEN** the LLM SHALL be `OpenAILike` configured with `api_base=https://openrouter.ai/api/v1` and `model=OPENROUTER_LLM_MODEL`

#### Scenario: LlamaIndex extraction uses the classification address

- **WHEN** `METADATA__EXTRACTION_MODE=llamaindex`
- **AND** `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=llamacpp`
- **AND** `LLAMACPP_CLASSIFY_URL=http://127.0.0.1:9931/v1` and `LLAMACPP_CHAT_URL=http://127.0.0.1:8081/v1`
- **THEN** the `OpenAILike` LLM SHALL use `api_base=http://127.0.0.1:9931/v1` and `model=LLAMACPP_CHAT_MODEL`
