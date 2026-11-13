## ADDED Requirements

### Requirement: A llama.cpp reranker backend scores through the local router

The system SHALL accept `llamacpp` for `retrieval.rerank_backend`. That backend SHALL send each query and its candidates to the router's `/v1/rerank` endpoint for the model in `retrieval.rerank_model`, and SHALL keep the reranker contract (sorted, truncated to `top_k`, scores in (0, 1], provenance flag). It SHALL be one registry entry, resolved without a branch on strategy names.

#### Scenario: Router reranks the candidates

- **GIVEN** `RETRIEVAL__RERANK_BACKEND=llamacpp` and a router model whose preset sets `pooling: rank`
- **WHEN** a search runs with `rerank=True`
- **THEN** the router's `/v1/rerank` endpoint SHALL score the candidates
- **AND** the results SHALL be sorted by its scores, truncated to `top_k`, and carry `"reranked": true`

#### Scenario: Router unavailable

- **GIVEN** `RETRIEVAL__RERANK_BACKEND=llamacpp` and a router that does not answer
- **WHEN** a search runs with `rerank=True`
- **THEN** the system SHALL return un-reranked results truncated to `top_k` with `"reranked": false` and a failure reason
- **AND** the system SHALL NOT raise

#### Scenario: Both construction paths

- **WHEN** the reranker is built by the composition root and by the lazy pipeline path with `rerank_backend` `llamacpp`
- **THEN** both SHALL construct the llama.cpp backend with the router address and the model name from the settings

#### Scenario: Unknown backend still refused

- **GIVEN** `RETRIEVAL__RERANK_BACKEND=vllm`
- **WHEN** settings are resolved
- **THEN** the system SHALL fail with an error naming `onnx`, `torch` and `llamacpp`
