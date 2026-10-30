## Why

Local classification and local Chat share one llama.cpp address (`llamacpp_chat_url`). So classification cannot stay on the Llama app (port 9931) while Chat moves to the `llama-server` that OMRS runs (ADR-084). The llama.cpp card labels the classification model "Chat model", which makes users think it answers Chat. A single-model `llama-server` ignores the model name in a request, so the server model and the Chat model can disagree with no sign. A llama.cpp claim-check judge with no model of its own uses the classification model with no sign.

## What Changes

Already in place, so this change does not add it: Settings > Chat saves `answer.provider` and `answer.model`, and `compose_answer.build_answer_llm` always passes `answer.model` to the provider. Chat on llama.cpp already has its own model setting. This change adds no second Chat model setting.

- **Three blocks on the llama.cpp card.** Embeddings (address and model, read-only as today), Classification (metadata) and Chat. The read-only row "Chat model" becomes "Text model (classification)". The key stays `llamacpp_chat_model`.
- **A classification address.** New setting `llamacpp_classify_url` (env `LLAMACPP_CLASSIFY_URL`). When no source sets it, classification uses the Chat address, so an existing install keeps working. Both classification paths (direct chat completions and the LlamaIndex extractors) use it. Sources follow ADR-087.
- **The Chat block shows the Chat model.** It is read-only on the card, with a link to Settings > Chat, which stays its only home. When Chat uses another provider, the block says so, for example "Chat uses OpenRouter (deepseek/deepseek-v4-flash-0731)".
- **Who runs the Chat server is a saved choice.** New setting `llamacpp_chat_server`: `external` (the Llama app or another server you run, the default) or `managed` (OMRS's own `llama-server`). Each choice shows a callout:
  - Llama app: the context size is `ctx-size` in the app's `models.user.ini`. A change needs a Llama app relaunch, which pauses embeddings and anything else on that port.
  - OMRS's own server: it needs a program named exactly `llama-server`. The Llama app's own `llama` program does not qualify. The callout suggests `brew install llama.cpp`.
- **One Chat model, no drift.** When the choice is `managed`, OMRS's server loads the Chat model (`answer.model`, provider `llamacpp`). **BREAKING:** the separate server model setting `llamacpp_server_model` (env `LLAMACPP_SERVER_MODEL`) is retired. The env name stops start-up with its replacement named. The `omrs.jsonc` key is ignored and reported. While the choice is `managed`, a Chat save for llama.cpp keeps the ADR-084 model rule and the `credentials` scope, on every route that can write it.
- **Use this model saves the Chat model.** After a llama.cpp download, with the choice `managed`, the button saves the Chat model and offers Restart. With `external`, the panel stays as ADR-106 decision 4 says.
- **No silent fallback to the classification model.**
  - A llama.cpp claim-check judge with an empty `answer.verify_model` is skipped with the reason "Choose a judge model". It no longer uses `llamacpp_chat_model`.
  - A llama.cpp Chat with an empty model refuses with "Choose a Chat model". The Chat status gives the reason `no-model`.
  - The Chat test for llama.cpp checks the server's model list first. A name that the server does not list fails with `model-not-listed`. This finds the `qwen3:4b` default that the Chat form keeps when the user changes the provider.
  - The Chat form empties the model name when the provider changes.
  - Classification still passes no model override and keeps `llamacpp_chat_model`.
- **A shared address warns.** When classification follows the Chat address and OMRS runs the Chat server, the card says that classification uses the Chat model, because the server loads one model.
- The integrations runtime list shows the classification address as its own llama.cpp item when it differs from the Chat address.
- Add ADR-108, which amends ADR-084 decision 4 (the server model) and ADR-106 decision 4 (who runs the Chat server, and Use this model). Update the provider, configuration, web workspace and metadata extraction guides, `.env.example` and the upgrade notes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `llamacpp-server`: the server settings lose the model and gain the Chat server choice. OMRS's server loads the Chat model. The `external` choice refuses Start. The old model setting is retired. The scopes cover a Chat save while the choice is `managed`.
- `llm-provider-settings`: the classification address setting. The Chat status reason `no-model`. A llama.cpp Chat answer needs a Chat model. The llama.cpp Chat test checks the model list.
- `metadata-extraction`: llama.cpp classification, direct and through LlamaIndex, uses the classification address.
- `grounded-answer-synthesis`: a llama.cpp judge never falls back to the classification model.
- `workspace-settings`: three blocks on the llama.cpp card, the Chat model line, the Chat server choice with its two callouts, the follow and shared-address notes, the Local server panel without a model row, and the Chat form that empties the model on a provider change.
- `model-downloads`: Use this model saves the Chat model and depends on the saved choice, not on the server state.
- `runtime-components`: the local server list includes the classification address.

## Impact

- **Settings:** `llamacpp_classify_url` and `llamacpp_chat_server` in `config/provider_sources.py`. `llamacpp_classify_url` in `PROVIDER_ADDRESS_FIELDS` (`core/settings.py`), `config/rules.py` `ADDRESS_FIELDS` and `ACCEPTED`. `llamacpp_server_model` removed. `LLAMACPP_SERVER_MODEL` in `_REMOVED_ENV_VARS` (`config/legacy.py`). `llamacpp_chat_server` is read-only on the Configuration page.
- **Backend:** `core/providers/llm/llamacpp.py` (roles, classification address, card groups), `core/metadata/llamacpp.py`, `core/metadata/llamaindex.py` (no change expected: it already passes no override), `compose_answer.py` (judge without a default model), `core/providers/llm/registry.py` and `connection.py` (descriptor fields `group`, `follows`, `default_answer_model`, `test_checks_model_list`), `core/providers/llm/llamacpp_rules.py`, `compose_llamacpp.py`, `transports/api/routes/llamacpp_server.py`, `routes/chat_settings.py`, `routes/configuration.py`, `transports/api/runtime_servers.py`, `settings_handover.py`.
- **HTTP contract:** `openapi.yaml` changes to `ProviderField`, `ProviderReadOnlyValue`, `ChatSettings`, the Chat test reason, `LlamacppServerStatus`, `SaveLlamacppServerRequest` and the start and restart 409 reasons. No new operation, so `FAMILIES` keeps its ids. The conformance tests must pass.
- **Front end:** `ProviderCard.tsx` groups, a new `LlamacppChatBlock.tsx` and `ChatServerChoice.tsx`, `LlamacppServerPanel.tsx` and `LlamacppServerFields.tsx` without the model row, `LlamacppUseModel.tsx`, `ModelDownloadDone.tsx`, `ChatModelForm.tsx`, `connectionWords.ts`, `llamacppServerWords.ts`, and the `api/` types. Each component stays under 200 lines.
- **Index identity:** no change. The address is not part of the identity, and `llamacpp_chat_model` keeps its key.
- **Docs:** ADR-108, `docs/adr/ADR_README.md`, notes on ADR-084 and ADR-106, `docs/guides/providers.md`, `docs/guides/configuration.md`, `docs/guides/web-workspace.md`, `docs/guides/metadata-extraction.md`, `.env.example`, `src/omrs/transports/api/README.md`.
- **Tests:** new unit, route and front-end tests, and new pins in `tests/test_clean_base_tripwire.py`.
- **Not changed:** embeddings, Ollama, OpenRouter, the ADR-084 program rule, and the files of the Llama app.
