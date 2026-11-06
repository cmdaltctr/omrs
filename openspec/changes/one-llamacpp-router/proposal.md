# Proposal: One llama.cpp router for every local model

## Why

OMRS runs one `llama-server` per role today: Chat, embeddings and one per decision model (ADR-109). Each role has its own address, mode setting and Settings block, and the live app still depends on the Llama app's own `models.ini` for context sizes. Ollama is the shipped Chat default, the test default and the CI gate, although ADR-103 makes llama.cpp the only runtime for local model evidence. The pipeline sweep must run on Linux (RunPod) with a pinned build, and the next forced re-index (change `local-ocr-per-backend-cuts`) is the one cheap moment to move embeddings to Qwen3-Embedding-4B.

## What Changes

- **One OMRS-run router.** OMRS runs one upstream `llama-server` in router mode (`--models-preset`, `--models-max`, `--models-memory-margin`). It serves every local llama.cpp model by name: embeddings, classification, Chat when its provider is `llamacpp`, and decision models (with projector). The dots.mocr OCR server stays separate on its own pinned server (ADR-113).
- **BREAKING:** the per-role runtimes `chat`, `embeddings` and `decision-<name>` are replaced by the one runtime `router`. ADR-108's chat-only managed mode goes.
- **One address.** Setting `llamacpp_router_server` (`managed` or `external`) and `llamacpp_router_url`. External mode points at a server the user runs, for example the Llama app on port 9931.
- **BREAKING:** `llamacpp_embed_url`, `llamacpp_chat_url`, `llamacpp_classify_url`, `llamacpp_chat_server`, `llamacpp_embed_server` and `llamacpp_context_window` are retired. An environment or `.env` value fails start-up and names the replacement. An `omrs.jsonc` key is reported in the problem list.
- **Model list in OMRS Settings.** A file-only map `llamacpp_models` holds each model: name (`org/repo:QUANT`), absolute GGUF path, optional projector, and preset values from a fixed allow-list (context size, batch sizes, pooling, slots, and others). OMRS writes the preset file from it. No dependency on the Llama app's `models.ini`.
- **One Router panel** in Settings: Start, Stop, Restart and a table of models with their roles, file and context size, editable. Get a model and Use this model add or replace a list entry. They no longer overwrite the Chat model.
- **Per-model behaviour:** a request lock for one-slot models only, a per-model preset digest, per-model readiness through the router's load endpoint, and a preset edit that reloads only the changed model.
- **Pinned binaries.** OMRS provisions the pinned llama.cpp build b11941 with SHA-256 for macOS arm64, Linux x86-64 CPU and Linux x86-64 CUDA. A user path stays allowed as an override.
- **BREAKING:** new shipped defaults with no Ollama: Chat provider `llamacpp` with no Chat model chosen (`answer.model = ""`), classification `Qwen/Qwen3-4B-GGUF:Q8_0`, embeddings `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` (2,560 dimensions). Chat and classification do not share a model by default. A fresh install shows "Choose a Chat model" on the Chat page, and a Chat or claim-check request with no model returns a plain setup message. Every collection re-indexes once, timed with the re-index that `local-ocr-per-backend-cuts` forces.
- **Router settings are visible and editable in the web GUI.** The Router panel shows the mode, the address, "Models loaded at once" and "Free memory margin (MiB)". The Integrations llama.cpp card shows the detected Linux flavour (CPU or CUDA) and lets the operator choose it before install.
- **Ollama becomes opt-in only.** The provider code stays (decision kind, download source, Ollama-built collections). Defaults, tests, CI and the first-choice docs use llama.cpp.
- **Single source of settings.** Repo `.env` and `.env.example` hold no provider, model or URL keys. Tests, `ci.yml` and `local_ci.sh` use mocked llama.cpp values equal to the shipped defaults, and a test pins that equality. The CI slow suite runs only when a llama.cpp router answers.
- New ADR-115 supersedes ADR-109's rejection of router mode and its per-role table. It amends ADR-084, ADR-108 and ADR-110, and relates to ADR-103, ADR-106 and ADR-113.

## Capabilities

### New Capabilities

- `llamacpp-router`: the one router OMRS runs or connects to. Model list, preset writer and allow-list, model rules, name routing, per-model locks and readiness, reload rule, decision models on the router, memory limits, pinned binaries and shipped defaults.

### Modified Capabilities

- `llamacpp-runtimes`: roles become `router` and `ocr-*`. Mode settings, state folder (preset file), adoption digest, start checks, request lock per model, runtime list and stop route change. The decision runtime moves to the router.
- `llamacpp-server`: process control now applies to the router. Settings, argument list, routes, lifecycle and scopes change. The Chat server choice and the Chat model rule are removed. The Chat-era settings are retired.
- `llm-provider-settings`: the classification address is removed. Shipped Chat defaults move from Ollama to llama.cpp, with no Chat model chosen.
- `inference-backend`: llama.cpp embedding and classification requests go to the router address.
- `runtime-components`: the local server list probes the router address.
- `settings-file`: the source-order example and the read-only key list name the router keys.
- `model-downloads`: a download is used through a router list entry. Use this model adds or replaces an entry.
- `workspace-integrations`: provider readiness and the Model runtimes rows follow the router. The llama.cpp card shows and sets the install flavour.
- `workspace-settings`: the llama.cpp card shows one Router panel with the mode, address, "Models loaded at once" and "Free memory margin (MiB)" rows. The Chat-server blocks and the classification-address warnings go.

## Impact

- Code: `src/omrs/integrations/llamacpp_runtime/` (router spec, preset writer, per-model locks), `compose_runtimes.py`, `compose_decision.py`, `core/runtime_gate.py`, `config/` (new keys, retirement in `legacy.py`, defaults), `core/answer/settings.py`, `core/providers/` (embedding, classification and Chat clients address), `transports/api/` (router routes, `openapi.yaml`), `web/src/settings/` and `web/src/integrations/`.
- Tests: `tests/conftest.py`, the fake llama server gains a router mode, tripwire re-pin, `ci.yml`, `scripts/local_ci.sh`.
- Docs: README, getting-started, providers, configuration, web-workspace, architecture guides, `.env.example`, new ADR-115.
- Data: every collection re-indexes once (1,024 to 2,560 dimensions).
- Related changes: lands after `local-ocr-per-backend-cuts` (shares its re-index) and before `pipeline-sweep-llamacpp` (whose design must then use the OMRS router). Overlaps `tripwire-retirement-and-provider-symmetry` on the retirement policy.
- Platforms: macOS arm64 and Linux x86-64 (CPU and CUDA). Windows stays `not-supported` for managed mode.
