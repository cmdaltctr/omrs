# ADR-115: One llama.cpp Router Serves Every Local Model

- **Date:** 2026-11-06
- **Status:** Proposed (2026-11-06; accepted when the change merges and the live rollout passes)
- **Deciders:** Maintainer
- **Supersedes in part:** [ADR-109](109-omrs-owns-local-model-runtimes-components-are-clients.md) (the rejection of router mode in its Alternatives table, and the per-role table of decision 2: the `chat` and `embeddings` rows)
- **Amends:** [ADR-084](084-context-windows-and-an-owned-llama-server.md) (decisions 3 to 5: the owned server, its settings and its argument list move from one Chat server to the router), [ADR-108](108-local-chat-and-classification-stay-apart.md) (decisions 1 to 5 and 7: the classification address, the Chat address and the Chat server choice are retired, and the managed Chat-only server goes), [ADR-110](110-decision-models-and-named-document-routers.md) (decision 4: a managed decision model runs on the router, not on its own `decision-<name>` runtime)
- **Related:** [ADR-103](103-experiments-run-local-models-through-llama-cpp-gguf.md) (llama.cpp is the runtime for local model evidence), [ADR-106](106-app-searches-and-downloads-local-models.md) (Get a model download), [ADR-113](113-dots-mocr-runs-on-llama-cpp.md) (the OCR server stays apart), [ADR-087](087-settings-live-in-omrg-jsonc.md) (source order)
- **Change:** `openspec/changes/one-llamacpp-router/` (design D1 to D17, specs `llamacpp-router`, `llamacpp-runtimes`, `llamacpp-server`, `llm-provider-settings`, `inference-backend`, `runtime-components`, `settings-file`, `model-downloads`, `workspace-integrations`, `workspace-settings`)
- **Evidence:** `openspec/changes/one-llamacpp-router/evidence/` (spikes 1.1 to 1.5, build b11941)

## Context

ADR-109 gave OMRS one `llama-server` per role. Chat, embeddings and each decision model run their own server. Each role has its own address, its own mode setting and its own Settings block. The live app still reads context sizes from the Llama app's own `models.ini`.

Four facts made this a poor fit.

- **Too many addresses.** Embeddings, classification and Chat use three address settings (`llamacpp_embed_url`, `llamacpp_classify_url`, `llamacpp_chat_url`) and two mode settings (`llamacpp_chat_server`, `llamacpp_embed_server`). A user must set five values to run three models.
- **Ollama is still the default.** The shipped Chat default, the test default and the CI gate use Ollama. ADR-103 makes llama.cpp the only runtime for local model evidence.
- **The sweep needs Linux.** The pipeline sweep must run on RunPod with a pinned build. No managed path provisions a build there.
- **A cheap moment to change embeddings.** The change `local-ocr-per-backend-cuts` forces one re-index. Moving embeddings to Qwen3-Embedding-4B costs no extra re-index if it lands with it.

ADR-109 rejected router mode for one reason: "It puts the OCR result outside the pinned build and ties Chat restarts to OCR." This ADR answers both points. OCR keeps its own pinned server. A preset edit reloads only the changed model (decision 6), so a Chat change restarts nothing else.

Facts about `llama-server` build b11941 that shape the decision. The spikes below checked each one.

- In router mode, `POST /v1/systemone` is forwarded by the `model` field.
- `GET /models?reload=1` re-reads the preset file. It unloads only the models whose section changed or went away.
- `GET /v1/models` reports each model's `status` (`unloaded`, `loading`, `loaded`) and its `args`.
- The router lists every model in its Hugging Face cache and loads one on a request, unless `LLAMA_CACHE` points elsewhere.
- The router reads `${XDG_CONFIG_HOME:-~/.config}/llama.cpp/config.ini` before its flags.
- A boolean key in `models.ini` takes any word without an error (`kv-unified = bogus` loads).

## Decision

1. **OMRS runs one router for every local llama.cpp model except OCR.** OMRS starts or adopts one upstream `llama-server` in router mode under runtime id `router`. It serves embeddings, classification, Chat (when the provider is `llamacpp`), the claim-check judge and `llamacpp` decision models. Each request names its model in the `model` field. The runtime ids `chat`, `embeddings` and `decision-<name>` retire. The `ocr-*` runtimes do not change (ADR-113).

2. **One mode, one address, two limits.** These settings follow the normal source order of ADR-087: environment and `.env` lock a field, `omrs.jsonc` does not.

   | Setting | Values | Default |
   | --- | --- | --- |
   | `llamacpp_router_server` | `managed` (OMRS runs it) or `external` (a server you run, for example the Llama app on port 9931) | `managed` |
   | `llamacpp_router_url` | loopback `http` URL when `managed`; any `http` or `https` URL when `external` | `http://127.0.0.1:8080/v1` |
   | `llamacpp_router_models_max` | 1 to 16 (`--models-max`) | 4 |
   | `llamacpp_router_memory_margin_mib` | 0 to 262,144 (`--models-memory-margin`) | 8,192 |

   In `external` mode OMRS starts, adopts and stops nothing. The router settings show in the Settings Router panel, with the value in force, its source and its default.

3. **The per-role server settings retire.** An environment or `.env` value fails start-up and the message names the replacement. An `omrs.jsonc` key is ignored and listed in the problem list. These are flat names, so they stay while an upgrade path exists.

   | Retired | Replacement |
   | --- | --- |
   | `llamacpp_embed_url`, `llamacpp_chat_url`, `llamacpp_classify_url` | `llamacpp_router_url` |
   | `llamacpp_chat_server`, `llamacpp_embed_server` | `llamacpp_router_server` |
   | `llamacpp_context_window` | `ctx-size` in the preset of the model's entry in `llamacpp_models` |
   | Decision entry fields `model_file`, `projector_file`, `model_sha256`, `projector_sha256` | The entry in `llamacpp_models` that the decision entry names |

4. **The model list is `llamacpp_models` in `omrs.jsonc`.** It is a named map. The key is an id of 1 to 40 characters from `a-z`, `0-9` and `-`. Each entry holds `model` (a Hugging Face id with a quantisation tag, such as `org/name:Q8_0`), `file` (an absolute path of a `.gguf` file), an optional `projector`, the recorded `sha256` values and a `preset` object. No environment variable sets the map. Only `omrs web` writes it. A user map replaces the shipped list as a whole. In `external` mode the map names models, and OMRS does not check files or presets.

   Roles are never stored. An entry has the role of each setting that names its `model`: `llamacpp_embed_model` (embeddings), `llamacpp_chat_model` (classification), `answer.model` (Chat), the judge model and each managed decision entry. A role setting that names no entry gives the reason `model-not-listed`. An entry with `embeddings = true` cannot hold a text role (`role-mismatch`).

5. **The preset file holds allow-listed keys only, and the argument list is fixed.** OMRS writes `<state>/runtimes/router/models.ini`: one section per entry, named by `model`, with `model = <file>` and `mmproj = <projector>`. Section names are model names, and the file path goes in the `model` key, so `GET /v1/models` shows `-m <path>`. The accepted preset keys are `ctx-size`, `batch-size`, `ubatch-size`, `parallel`, `embeddings`, `pooling`, `embd-normalize`, `kv-unified`, `flash-attn`, `n-gpu-layers`, `fit`, `cache-type-k`, `cache-type-v`, `cache-prompt`, `cache-reuse`, `image-min-tokens` and `image-max-tokens`. Each key is typed and range-checked. Any other key is refused with `preset-key-unknown`.

   A boolean takes a JSON boolean and is written as exactly `true` or `false`, never as a negated key. `embeddings` takes `true` only, because b11941 has no `--no-embeddings`. This is the only check, because llama.cpp accepts any word.

   The router argument list is `--models-preset`, `--models-max`, `--models-memory-margin`, `--host 127.0.0.1` and `--port`. `--sleep-idle-seconds` stays refused. This keeps the fixed-flag rule of ADR-084: no free-text argument and no shell.

6. **A preset edit reloads only the changed model.** Under `start.lock`, OMRS rewrites only the changed section and calls `GET /models?reload=1`. A change of the router's own arguments (model limit, margin, port, binary) restarts the router. When another OMRS process uses the changed model, the change fails for that model only with `version-busy`. Other models keep running.

7. **Each model has its own locks, digest and readiness.**
   - The router digest covers the binary path and the argument list. A preset edit is not a new router version.
   - Each model has `models/<model id>/clients.lock`. A model with `parallel = 1` also has `request.lock`. A request to a one-slot model does not block a request to another model.
   - Before the first request to a model in a lease, OMRS reads `GET /v1/models`. When the model is not `loaded`, it calls `POST /models/load` and polls up to `MODEL_LOAD_TIMEOUT_SECONDS = 300`. The request timeout starts after the model is loaded. A failed load gives `model-load-failed` for that model only.
   - The router start waits up to 180 seconds for `GET /health`. No model loads at start.
   - A managed request that names a model outside the list is refused before any contact (`model-not-listed`).

8. **A model file is checked against its recorded SHA-256.** OMRS compares the file before each router start and before each preset rewrite. A cache in `hashes.json`, keyed by path, size and `mtime_ns`, avoids hashing a 4 GiB file at every start. A changed file leaves its entry out of `models.ini` with reason `file-changed`. Other entries keep working. An entry with no recorded value runs with the note "File not checked". A decision entry with no recorded value is refused.

9. **The router child gets an empty cache and an empty config folder.** The child gets the minimal environment of ADR-084 plus two values: `LLAMA_CACHE=<state>/runtimes/router/empty-cache` and `XDG_CONFIG_HOME=<state>/runtimes/router/empty-config`. OMRS empties both folders at every start. The child never gets a Hugging Face cache or token variable. This stops the router from listing and autoloading cached models, and stops a user `config.ini` from changing a model without OMRS knowing. **Known limit:** the router also reads `/etc/llama.cpp/config.ini` and OMRS cannot redirect it. OMRS does not check that file.

10. **Stop and memory reach the children.** Each loaded model runs as a child `llama-server`. The group stop (SIGTERM, 10 seconds, SIGKILL) ends every child. The router item's memory is the router's resident size plus that of its direct children whose command line holds the recorded binary path. On Linux, OMRS reads every `/proc/<pid>/task/*/children` file, because each child hangs under the router thread that started it. On macOS it uses `proc_listchildpids`. OMRS lists no other process.

11. **Decision models run on the router (outcome A).** A managed `llamacpp` decision entry names a list entry by `model`. That list entry holds the `projector` for an image model and `parallel = 1`. When any decision entry is listed, a router build below b11941 is refused with `wrong-build`. The quantisation check of ADR-110 decision 2 reads the list entry's file. The projector smoke test of ADR-110 decision 3 runs through the router.

12. **OMRS provisions a pinned llama.cpp build on request.** The pins live in `integrations/llamacpp_runtime/pins.py`: build b11941 for macOS arm64, Linux x86-64 CPU and Linux x86-64 CUDA 12.8 (with its `cudart` archive). A provisioning job and the CLI command `omrs llamacpp install [--flavour cpu|cuda]` download the archives, check their SHA-256, unpack each flavour into its own `b11941-<flavour>/` folder and put the CUDA runtime files beside `llama-server`. The job then runs `llama-server --version` and fails with `binary-check-failed` unless it reports build 11941. For CUDA it also runs `--list-devices` and fails with `cuda-device-missing` when no CUDA device shows. A blank `llamacpp_server_binary` means the provisioned binary. A user path keeps the program rule and is refused below b11941 (`wrong-build`). On Linux the default flavour is CUDA when `/proc/driver/nvidia/version` exists, else CPU. Other platforms, such as macOS x86-64, give `not-supported` and keep the user path.

13. **The shipped defaults use llama.cpp and no Ollama.**

    | Role | Default |
    | --- | --- |
    | Embeddings | `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` (2,560 dimensions), preset `embeddings=true pooling=last embd-normalize=2 ctx-size=8192 batch-size=8192 ubatch-size=8192 parallel=1 kv-unified=false` |
    | Classification | `Qwen/Qwen3-4B-GGUF:Q8_0`, preset `ctx-size=32768 parallel=2` |
    | Chat | Provider `llamacpp`, `answer.model` empty: no Chat model is chosen |

    The shipped list has no file paths. An entry with no file shows "Not downloaded" and downloads through the Get a model job (ADR-106) when the router first needs it. A Chat or claim-check judge request with no model returns a plain setup message that names `answer.model`. It never falls back to the classification model. The Ollama provider, decision kind and download source stay as an opt-in. Defaults, tests, CI and first-choice docs use llama.cpp. Every collection re-indexes once, because the embedding identity changes. The re-index of `local-ocr-per-backend-cuts` forces that moment.

14. **Memory limits are `--models-max 4` and `--models-memory-margin 8192`.** On a 64 GB Mac during ingestion, embeddings 4B Q8_0 (about 4.3 GB plus a small cache), Qwen3-4B Q8_0 (about 4.3 GB plus about 4.8 GB of f16 cache at 32,768 tokens) and the Clef-Flash routing model stay well below 64 GB and leave 8 GiB free. dots.mocr OCR runs outside the router. On a GPU pod the margin applies per device.

## Spike evidence (build b11941, 2026-11-06)

Each spike ran on a scratch port and a scratch state folder, never on the live app. The files are in the change folder under `evidence/`.

| Spike | Result |
| --- | --- |
| 1.1 Decision forwarding | **Outcome A.** The router forwarded `POST /v1/systemone` for Clef-Flash Q8_0 with its projector (status 200 in 0.67 s). `status.args` showed `--model`, `--mmproj` and `--parallel 1`. The OMRS projector smoke test passed through the router: right text 0.9387, wrong text 0.0195, margin 0.919 against the 0.2 limit. |
| 1.2 Load, unload and reload | **The reload rule holds.** Editing one section unloaded only that model. The other model kept its child pid. The next load showed the new value in `status.args`. A byte-identical rewrite and a comment reorder unloaded nothing. A removed section unloaded and dropped only its model. `/health` answered 200 with no model loaded. A 4B Q8_0 model loaded in 4.5 to 5.2 s and unloaded in 0.1 s. With the margin above 0, `GET /v1/models` adds a `memory` object. The router listed models from the Hugging Face cache. Setting `LLAMA_CACHE` to an empty folder removed that list. |
| 1.3 Child processes | **No child survives.** On macOS and on Linux, children share the router's process group and session. A group SIGTERM ended every process within 0.14 s. After SIGKILL of the router pid alone, every child exited within 0.03 s, because each child exits when its stdin pipe from the router closes. A kill during a model load left nothing behind. The Linux run used an arm64 container; process-group and pipe behaviour are the same on x86-64. So no per-child stop is needed. |
| 1.4 Linux builds | **SHA-256 values match the release.** The `cudart` files sit beside `llama-server` (RUNPATH `$ORIGIN`, no `LD_LIBRARY_PATH`). The CPU build lists no CUDA device. The CUDA build needs glibc 2.38 (Ubuntu 24.04 or newer); the CPU build needs glibc 2.34. A CUDA build with no driver exits 0 and lists no device, so the exit code cannot tell. On a RunPod RTX A6000 (driver 595.91.07, CUDA 13.2), `llama-server --list-devices` listed `CUDA0` and a 0.6B model loaded and answered (prompt 658.6 tokens/s, generation 350.6 tokens/s). CUDA 12.8 works on that driver. |
| 1.5 Preset keys | **The allow-list was corrected.** Booleans take any word without an error. `embeddings` has no negated form. Some keys are reserved by the router. `spec-type` takes a list and defaults to `none`. The router environment of decision 9 came from this spike and spike 1.2. |

## Operator decisions (2026-11-06)

- **Q1, mode default:** `managed`. The Router panel shows the mode row and the router address.
- **Q2, Chat default:** Chat does not share the classification model by default. `answer.provider` is `llamacpp` and `answer.model` is empty. The shipped `qwen3-4b` entry serves classification only. A fresh install shows "Choose a Chat model". If the user picks the classification model for Chat, Settings > Chat and the Router panel show a warning (shared slots, shared context size, one reload for both). The warning suggests another router model, the user's own llama.cpp server through the OpenAI-compatible provider, or a hosted provider such as OpenRouter. It does not block Save.
- **Q3, memory limits:** `--models-max 4` and `--models-memory-margin 8192` MiB. Both show in the Router panel as "Models loaded at once" (1 to 16) and "Free memory margin (MiB)" (0 to 262,144).
- **Q4, Linux flavour:** CUDA 12.8 when an NVIDIA driver exists, else CPU. The Integrations llama.cpp card shows the detected flavour and lets the operator choose CPU or CUDA before install.
- **G2, design path:** outcome A of spike 1.1. Decision models run on the router in both modes. The `decision-<name>` runtime path goes.

## Consequences

### Positive

- One address, one mode and one Settings panel serve every local llama.cpp model except OCR.
- Context sizes and other model options live in OMRS settings. The live app no longer depends on the Llama app's `models.ini`.
- The same managed setup works on macOS arm64 and Linux x86-64 (CPU and CUDA) with a pinned build. RunPod pods can run the pipeline sweep.
- A one-slot model, a changed file or a failed load affects that model only.
- Defaults, tests and CI use llama.cpp. ADR-103 and the shipped defaults agree.

### Negative

- **BREAKING:** six keys retire. A start-up that finds one in the environment or `.env` fails with the replacement named.
- **BREAKING:** the managed Chat-only mode of ADR-108 goes. A user who ran Chat on a separate managed server moves Chat to a router entry.
- **BREAKING:** the default Chat provider changes from Ollama to llama.cpp, with no model chosen. Chat shows "Choose a Chat model" until the user picks one.
- Every collection re-indexes once, because the embedding model changes from 1,024 to 2,560 dimensions. The re-index of `local-ocr-per-backend-cuts` forces that moment.
- A model download of several GiB starts when the router first needs a missing model. The entry shows "Downloading" with progress.
- The router reads `/etc/llama.cpp/config.ini` and OMRS cannot redirect it. Likelihood 1 (no OMRS step writes it), impact 3.
- The CUDA build needs glibc 2.38 or newer. An older host gets `binary-check-failed`.
- The router can evict a model (least-recently-used rule) between the readiness check and the request, so one request carries a load. A load takes seconds on a local disk and the decision timeout is 120 s. Likelihood 2, impact 2.

### Neutral

- dots.mocr OCR keeps its own server and its parity evidence (ADR-113).
- The Ollama provider code stays, so Ollama-built collections keep working.
- The state folder holds no settings, so rollback is a revert of the merge commit and a delete of the state folder. Rollback re-indexes once more, because the identity changes back.
- The pipeline sweep change `pipeline-sweep-llamacpp` is amended to run on the OMRS router (task 10.3 of this change).

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Keep one server per role (ADR-109 as built) | Three addresses, three mode settings and three Settings blocks stay. OMRS still needs the Llama app for context sizes. |
| A router that OMRS does not run (the Llama app only) | The pinned build, the preset and the file checks sit outside OMRS. RunPod pods have no Llama app. |
| llama-swap or another process manager | It adds a new dependency and a second config format. llama.cpp's router already unloads by least-recently-used and reloads one model on a preset change (spike 1.2). |
| Put OCR on the router too | It puts the OCR result outside the pinned build of ADR-113 and ties OCR restarts to the other models. |
| Restart the router on every preset edit | It drops every loaded model, so a context size edit for Chat would stall ingestion. |
| Chat shares the classification model by default | The operator chose against it (Q2): Chat and classification would clash on one model. |
| Write free-text router flags or a `[*]` section | It breaks the fixed-flag rule of ADR-084 and lets one setting change every model. |
| Use a Homebrew build on every host | RunPod pods have no Homebrew, and ADR-103 asks for a pinned build. The user path stays as an override. |
| Leave the Hugging Face cache visible to the router | The router lists and may autoload any cached model on a stray request (spike 1.2). |

## Verification

Not built yet. The change `one-llamacpp-router` lists the checks in `tasks.md`:

1. Fake-router tests (`tests/fixtures/llamacpp/fake_llama_server.py` in router mode): argument list, preset writer golden files, per-model locks, readiness with a slow load, reload of one model, stop reaching children and memory summing.
2. Settings tests: defaults, source order, range refusal, retirement of the six keys and the four decision fields, and the "No Ollama default" scenarios.
3. Provisioning tests with a local archive server: hash mismatch, unpinned platform, headless CLI, `binary-check-failed` and `cuda-device-missing`.
4. OpenAPI conformance tests, Vitest tests for the Router panel and the Integrations card, and a browser check at 1,280 px and 390 px.
5. A live rollout (tasks 13.1 to 13.5): provision the router, download the models, switch `omrs.jsonc`, re-ingest every collection and check a known-answer search per collection.

This section is updated with the results when the change merges.

## References

- `openspec/changes/one-llamacpp-router/` (proposal, design D1 to D17, specs, `evidence/`)
- `src/omrs/integrations/llamacpp_runtime/` (`router_spec.py`, `preset_writer.py`, `hashes.py`, `children.py`, `model_locks.py`, `readiness.py`, `reload.py`, `router_lease.py`, `pins.py`)
- `src/omrs/config/llamacpp_models.py`, `llamacpp_preset.py`, `llamacpp_roles.py`, `llamacpp_router_rules.py`, `src/omrs/core/llamacpp_router.py`
- `docs/guides/configuration.md` (Local llama.cpp router, Upgrade notes), `docs/guides/architecture.md` (Local model runtimes)
- [ADR-084](084-context-windows-and-an-owned-llama-server.md), [ADR-108](108-local-chat-and-classification-stay-apart.md), [ADR-109](109-omrs-owns-local-model-runtimes-components-are-clients.md), [ADR-110](110-decision-models-and-named-document-routers.md)
- [ADR-103](103-experiments-run-local-models-through-llama-cpp-gguf.md), [ADR-106](106-app-searches-and-downloads-local-models.md), [ADR-113](113-dots-mocr-runs-on-llama-cpp.md)
