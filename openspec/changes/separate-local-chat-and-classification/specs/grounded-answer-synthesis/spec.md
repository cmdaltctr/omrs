## ADDED Requirements

### Requirement: A judge never falls back to the classification model

When the judge provider resolves to `llamacpp` or `ollama` and the judge model in force is empty, the claim check SHALL be skipped with a `verification_skipped` reason that names the missing judge model. The pipeline SHALL send no judge request. The answer SHALL keep its status, citations and evidence. A classification model SHALL NOT judge claims. A provider that has its own answer model setting SHALL keep its documented default for an empty judge model.

#### Scenario: Empty llama.cpp judge model

- **GIVEN** claim checks are on, the judge provider is `llamacpp` and `answer.verify_model` is empty
- **WHEN** the answer pipeline runs
- **THEN** the result SHALL have `status="ok"` with `verification_skipped` naming the missing judge model
- **AND** no request SHALL reach the classification address or use `llamacpp_chat_model`

#### Scenario: Empty Ollama judge model

- **GIVEN** claim checks are on, the judge provider is `ollama` and `answer.verify_model` is empty
- **WHEN** the answer pipeline runs
- **THEN** the result SHALL have `status="ok"` with `verification_skipped` naming the missing judge model
- **AND** no judge request SHALL use `metadata.ollama_classify_model`

#### Scenario: OpenRouter keeps its default

- **GIVEN** claim checks are on, the judge provider is `openrouter`, `answer.verify_model` is empty and an OpenRouter key is set
- **WHEN** the answer pipeline runs
- **THEN** the judge SHALL use `openrouter_llm_model`, as before
