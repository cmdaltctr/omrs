# Design: One llama.cpp router for every local model

## Context

See proposal.md for the motivation. The facts below come from the code on branch `v3` at `79194bf2` and from the llama.cpp b11941 source.

Runtime manager (ADR-109, `src/omrs/integrations/llamacpp_runtime/`):

- One server per runtime id. `spec.py` `RUNTIME_ID_RE` accepts `chat`, `embeddings`, `ocr-*` and `decision-*`.
- Ports come from the role addresses (`compose_runtimes.py` `_managed`, `rules.loopback_port`). Code defaults: embeddings `http://localhost:8080/v1`, Chat `http://localhost:8081/v1` (`config/__init__.py`).
- The gated transport (`core/runtime_gate.py`) sends each request to the client's own address.
- Argument lists: Chat `-c <window>`; embeddings `--embedding` only (no `-c`, `-ub`, `--pooling` or `-np`); decision `--mmproj`, `--parallel 1`, SHA-256 per file and a build floor (`spec.py`). `--sleep-idle-seconds` is refused.
- The digest is SHA-256 of binary path and argument list. A different digest while another process uses the server gives `version-busy` (`lease.py`). `request.lock` is taken only when the whole server is one-slot.
- `manager.py`: `IDLE_STOP_SECONDS = 600`, status reads `rss_bytes` of the recorded pid only. `process.py`: detached session, group stop (SIGTERM, 10 s, SIGKILL), `owns()` checks the binary path, `/health` wait 180 s.
- Decision runtime lease in `compose_decision.py`, `REQUEST_TIMEOUT = 120.0`, `POST /v1/systemone` with `model` (`core/providers/decision/llamacpp.py`).

Clients already send a model name with each request: embeddings, classification, Chat (`is_chat_model=True`) and decision. A router can route all of them.

Settings: `llamacpp_chat_server` and `llamacpp_embed_server` (`external` or `managed`); `llamacpp_server_binary` (absolute, named `llama-server`); `llamacpp_context_window` (16,384, Chat only); `llamacpp_classify_url` (blank follows Chat). Three settings named "context window" exist with two units: `ollama_context_window` (tokens), `llamacpp_context_window` (tokens) and `answer.context_window` (characters). Retirement lives in `config/legacy.py` (`_REMOVED_ENV_VARS`, `NOTHING_REPLACES`) and `KIND_RETIRED` in the `omrs.jsonc` problem list. The open change `tripwire-retirement-and-provider-symmetry` rewrites that policy (flat names persist while an upgrade path exists).

Downloads (ADR-106): `hf_hub_download` at a pinned revision into the Hugging Face cache, value `org/name:LABEL`, loaded with `-hf`. No SHA-256 is recorded. Projector files are left out of the file list (`model_sources.py`).

Experiments: `experiments/_lib/llamacpp_runtime.py` `verify_llamacpp_runtime` needs one loopback address. It reads `/props` `build_info` and, in router mode, the `-m <path>` (or `--model`) token of each model's `status.args` from `GET /v1/models`. So a router preset must load each model by file path, not by Hugging Face id.

llama.cpp b11941 router (`tools/server/server.cpp`, `tools/server/server-models.cpp`, read for this design):

- In router mode every model route, `POST /v1/systemone` included, maps to `proxy_post`, which routes by the `model` field.
- `GET /models?reload=1` re-reads the preset sources. It unloads only models whose preset changed or that left the file. Unchanged models keep running.
- `POST /models/load` and `POST /models/unload` exist. `GET /v1/models` reports each model's `status` and, when memory scheduling is on, its `memory`.
- Each loaded model runs as a child `llama-server` that the router watches. The router also lists every model in its Hugging Face cache (`load_from_cache`), unless `LLAMA_CACHE` points elsewhere (D4).
- The router strips reserved keys from a preset (`api-key`, `models-*`, `host`, `port`, `alias`, `hf-repo` and others).
- Release b11941 publishes `macos-arm64`, `ubuntu-x64` (CPU only), `ubuntu-cuda-12.8-x64`, `ubuntu-cuda-13.4-x64` and matching `cudart-*` archives.

Live app (2026-11-06): it uses the Llama app router on 9931 for embeddings and classification, with context sizes set in the Llama app's own `models.ini`. Chat answers go to OpenRouter.

## Goals / Non-Goals

**Goals:**

- One router process, one address and one Settings panel for every local llama.cpp model except OCR.
- Per-model behaviour where the old design was per-server: request lock, digest, readiness, memory and failure.
- The same managed setup on macOS arm64 and Linux x86-64 (CPU and CUDA), with a pinned build.
- Shipped defaults, tests and CI that need no Ollama.

**Non-Goals:**

- Moving dots.mocr OCR onto the router (ADR-113 keeps its own pinned server).
- Removing the Ollama provider, its decision kind, its download source or Ollama-built collections.
- A router for remote hosts. The router binds `127.0.0.1` only.
- Windows managed mode (stays `not-supported`).
- Per-model idle unload by OMRS. The router's own LRU (`--models-max`, `--models-memory-margin`) decides.

## Architecture

```
 omrs web / CLI / stdio MCP / watcher            (every process is a client)
   |  embeddings   classification   Chat   decision (Clef-Flash + mmproj)
   |      \             |            |        /
   |       +-- RuntimeGate per model (lease, load, one-slot lock) --+
   v                                                                 v
 runtimes/router/  start.lock clients.lock server.json models.ini   models/<id>/clients.lock request.lock
   |
   v
 llama-server --models-preset models.ini --models-max N --models-memory-margin M --host 127.0.0.1 --port P
   |-- child llama-server: Qwen/Qwen3-Embedding-4B-GGUF:Q8_0  (embeddings, pooling last)
   |-- child llama-server: Qwen/Qwen3-4B-GGUF:Q8_0            (classification; Chat only if picked)
   '-- child llama-server: <Clef-Flash entry>                 (decision, --mmproj, parallel 1)

 runtimes/ocr-dots-mocr-llamacpp/   separate pinned llama-server (ADR-113), unchanged
```

## Decisions

### D1. One router for every local model; OCR stays apart

OMRS runs one upstream `llama-server` in router mode under runtime id `router`. It serves embeddings, classification, Chat (when `answer.provider` is `llamacpp`), the claim-check judge when it is local llama.cpp, and decision models. The `chat`, `embeddings` and `decision-<name>` runtime ids retire. `ocr-*` runtimes do not change.

ADR-109 rejected router mode because "it puts the OCR result outside the pinned build and ties Chat restarts to OCR". This design answers both points. OCR keeps its own pinned server, so its parity evidence (ADR-113) stays valid. A preset edit reloads only the changed model (D7), so a Chat change does not restart other models, and never OCR.

Alternatives:

- Keep one server per role. Rejected: three addresses, three mode settings, three Settings blocks, and context sizes still live outside OMRS for external users.
- llama-swap or another proxy. Rejected: a second program to pin and supervise. llama.cpp's own router is in the pinned release.
- Put OCR on the router too. Rejected by ADR-113 parity evidence and ADR-109's concern.

### D2. Settings: one mode, one address, retired role keys

New keys (flat, env name in upper case, settable in `.env` and `omrs.jsonc`; the page writes them):

| Key | Values | Default |
| --- | --- | --- |
| `llamacpp_router_server` | `managed` (OMRS runs llama.cpp) or `external` (use this address) | `managed` |
| `llamacpp_router_url` | loopback `http` URL for `managed`; any http(s) URL for `external` | `http://127.0.0.1:8080/v1` |
| `llamacpp_server_binary` | kept. Blank means the provisioned pinned binary (D12) | `""` |
| `llamacpp_router_models_max` | 1 to 16 | 4 |
| `llamacpp_router_memory_margin_mib` | 0 to 262,144 | 8,192 |
| `llamacpp_models` | file-only named map (D3) | the shipped list (D11) |

Role keys stay and keep their meaning: `llamacpp_embed_model` (embedding identity, `org/repo:QUANT`), `llamacpp_chat_model` (classification Text model), `answer.model` with `answer.provider = llamacpp` (Chat), and the judge model. Each names an entry of `llamacpp_models` by its `model` value.

Retired keys, with replacement:

| Retired | Replacement |
| --- | --- |
| `llamacpp_embed_url`, `llamacpp_chat_url`, `llamacpp_classify_url` | `llamacpp_router_url` |
| `llamacpp_chat_server`, `llamacpp_embed_server` | `llamacpp_router_server` |
| `llamacpp_context_window` | `ctx_size` of the model's entry in `llamacpp_models` |

Retirement follows the existing mechanism: an environment or `.env` value fails start-up with a message that names the replacement (`_REMOVED_ENV_VARS`), and an `omrs.jsonc` key is ignored and listed as `retired` with its replacement. These are flat names, so under the policy of `tripwire-retirement-and-provider-symmetry` (design D1 there) their entries persist while an upgrade path exists. Whichever change merges second rebases its `legacy.py` edits onto the other.

Naming: the per-model value is `ctx_size`, shown as "Context size (tokens)". The page never shows it beside `answer.context_window` without the unit "characters". `ollama_context_window` keeps its label "Ollama context window (tokens)".

Default mode `managed`: with no Ollama, a fresh install needs a local server, and the router can be provisioned by OMRS (D12). Decided by the operator on 2026-11-06 (Q1, see "Operator decisions"). The Router panel shows the mode row ("OMRS runs llama.cpp" or "Use this address") and the router address, so the operator sees and edits both in the web GUI.

Alternative: keep the three URLs pointing at one port. Rejected: three settings that must agree, and a mismatch silently splits roles across two servers.

### D3. The model list

`llamacpp_models` is a named map in `omrs.jsonc`, like `decision_models` (file only, no environment variable, only `omrs web` writes it, revision check, atomic replace). The map key is a short id (`[a-z0-9-]{1,40}`). Each entry:

| Field | Rule |
| --- | --- |
| `model` | Request name and preset section name, `org/repo:QUANT`, unique in the map, never starts with `-` |
| `file` | Absolute path of an existing regular `.gguf` file whose name holds no `mmproj` (managed only) |
| `projector` | Optional absolute `.gguf` path (image models) |
| `sha256`, `projector_sha256` | Recorded when the entry is added through the page (D5) |
| `preset` | Object with allow-listed keys only (D4) |

Roles are derived, never stored: an entry has the role of every role key that names its `model`. The Router panel shows them. One entry can serve several roles (the shipped Qwen3-4B serves classification; it serves Chat too only when the operator picks it).

A user map replaces the shipped list as a whole. The first page edit writes the shipped list plus the edit.

Managed decision entries change shape: a `decision_models` entry with `kind: llamacpp` and `server: managed` names a list entry by `model`. Its `model_file`, `projector_file`, `model_sha256` and `projector_sha256` fields retire and are reported as moved to `llamacpp_models` (outcome A of D10).

In `external` mode the map still names models, and `file`, `projector` and `preset` are not used. The panel says "External server: OMRS does not check model files or presets."

### D4. Preset writer and allow-list

OMRS writes `<state>/runtimes/router/models.ini` from the list. It writes no `[*]` section. Each entry becomes one section named by `model`, with `model = <file>` and `mmproj = <projector>`, so `GET /v1/models` shows `-m <path>` and `verify_llamacpp_runtime` keeps working.

Allowed preset keys (anything else is refused with 400 `preset-key-unknown`; values are typed and range-checked, never free text):

| Key | Type |
| --- | --- |
| `ctx-size` | integer 512 to 262,144 |
| `batch-size`, `ubatch-size` | integer 32 to 65,536; `ubatch-size` at most `batch-size` |
| `parallel` | integer 1 to 16 |
| `embeddings` | `true` only. To turn it off, leave the key out: b11941 has no `--no-embeddings` (spike 1.5) |
| `pooling` | `none`, `mean`, `cls`, `last`, `rank` |
| `embd-normalize` | -1, 0, 1, 2 |
| `kv-unified` | boolean |
| `flash-attn` | `on`, `off`, `auto` |
| `n-gpu-layers` | integer 0 to 999, or `all` or `auto` |
| `fit` | `on`, `off` |
| `cache-type-k`, `cache-type-v` | `f32`, `f16`, `bf16`, `q8_0`, `q4_0` |
| `cache-prompt` | boolean |
| `cache-reuse` | integer 0 to 65,536 |
| `image-min-tokens`, `image-max-tokens` | integer 1 to 65,536 |

A boolean comes from a JSON boolean only, and the writer writes exactly `true` or `false`. It never writes a negated key such as `no-kv-unified`. Reason: b11941 accepts any word for a boolean key in `models.ini` without an error (`kv-unified = bogus` loads), so OMRS is the only check (spike 1.5).

The `cache-type-k` and `cache-type-v` list is a deliberate subset: b11941 also accepts `q4_1`, `iq4_nl`, `q5_0` and `q5_1`. Adding one needs a code change and a test, like any key.

Never written, whatever the source: `host`, `port`, `api-key`, `api-key-file`, `models-*`, `sleep-idle-seconds`, `hf-repo`, `alias`, `log-file`, `ssl-*`, `model-url`, `connect`, `connect-code`. The allow-list already blocks each of them; the list names them for the reserved-key test. The router argument list is fixed (spec `llamacpp-server`):

```
[binary, "--models-preset", <state>/runtimes/router/models.ini,
 "--models-max", N, "--models-memory-margin", M,
 "--host", "127.0.0.1", "--port", P]
```

Adding a key needs a code change and a test. The pipeline sweep presets (`pipeline-sweep-llamacpp` design D6a) use `spec-type` and `chat-template-kwargs`. They are not in the list. Spike 1.5 confirmed the `spec-type` values on b11941 (a comma list of `none`, `draft-simple`, `draft-eagle3`, `draft-mtp`, `draft-dflash`, `draft-dspark`, `ngram-simple`, `ngram-map-k`, `ngram-map-k4v`, `ngram-mod`, `ngram-cache`; default `none`). The sweep needs only `none`, which is the default, so the key stays out until a run needs another value. `chat-template-kwargs` is free text. The sweep sends the thinking setting per request.

This keeps ADR-084's fixed-flag rule: no free-text argument, no shell, a minimal child environment.

Router environment: the router child gets the minimal environment of ADR-084 plus two fixed values, `LLAMA_CACHE=<state>/runtimes/router/empty-cache` and `XDG_CONFIG_HOME=<state>/runtimes/router/empty-config` (both empty folders OMRS creates). It never gets the Hugging Face cache or token variables. Reasons, from spikes 1.2 and 1.5: b11941 lists every model in its Hugging Face cache and autoloads one on request, and `LLAMA_CACHE` pointing at an empty folder removes them all from the list (`evidence/spike-1.2-cache.md`); and b11941 reads `${XDG_CONFIG_HOME:-~/.config}/llama.cpp/config.ini` before its flags, so a user file could change every model without OMRS knowing. Known limit: `/etc/llama.cpp/config.ini` is read too and cannot be redirected; OMRS does not check it.

### D5. Model rules and file checks

- Name rule: the existing Hugging Face id rule (`rules.model_kind`), with a required `:QUANT` tag.
- File rule: absolute, regular, readable, `.gguf`. The decision quantisation check (ADR-110 decision 2) reads the GGUF header of a decision entry's file.
- SHA-256: the page records it when an entry is added or its file changes (Use this model hashes the file after the download job). Before each router start, and before each preset rewrite, OMRS compares each listed file with its recorded value. A hash cache in `<state>/runtimes/router/hashes.json`, keyed by path, size and `mtime_ns`, avoids hashing 4 GiB files on every start. A changed file leaves its entry out of the preset with reason `file-changed`. Other entries keep working. An entry without a recorded value runs with the note "File not checked". A decision entry without one is refused, as today.

Why per-entry: one changed file must not stop embeddings for every collection.

### D6. Routing by name

Every client sends the entry's `model`. A `RuntimeGate` per model takes the router lease, the model's shared client lock, makes the model ready (D8), takes the model's request lock when it is one-slot, and sends to `llamacpp_router_url`. A managed request that names a model outside the list is refused before any contact with reason `model-not-listed`. In external mode OMRS does not check the name.

With the router environment of D4, the router lists only the preset entries. The `model-not-listed` refusal stays for external mode and as the check before any contact.

### D7. Restart rule: reload one model, restart only for router arguments

- Preset change of one entry (file, projector, preset values): under `start.lock`, OMRS rewrites only that entry's section of `models.ini` (temporary file and rename) and calls `GET /models?reload=1`. b11941 unloads only the changed model. The next request loads it with the new preset.
- A process that wants a different preset for model X than the running one checks model X's `clients.lock`. If another process uses model X, it gets `version-busy` for model X only. Other models are not affected.
- Router argument change (`models_max`, memory margin, port, binary): the whole router restarts, with the existing `version-busy` rule.
- The Router panel shows "Reload pending" per model and "Restart to apply" for router arguments.

Spike 1.2 checked this on b11941 (2026-11-06, `evidence/spike-1.2.md`): an edit of one section unloaded only that model, the other model kept its child pid, and the next load showed the new value in `status.args`. A byte-identical rewrite, or a reorder with a comment, unloaded nothing. A removed section unloaded and dropped only that model; an added section listed as `unloaded`. The stop condition did not fire, so this rule stands.

Alternative: restart on every edit. Rejected: it drops every loaded model, so a context size edit for Chat would stall ingestion.

### D8. Per-model locks, digests and readiness

State folder:

```
<state>/runtimes/router/
  start.lock  clients.lock  server.json  server.log  models.ini  hashes.json
  empty-cache/  empty-config/        (router environment, D4)
  models/<model id>/clients.lock  request.lock
```

`<model id>` is the first 16 hex characters of SHA-256 of `model`, the same in every process.

- Router digest: SHA-256 of binary path and router argument list. Preset sections are not in it.
- Model digest: SHA-256 of the model's section text. `server.json` records a `models` map of digests.
- Request lock: only for an entry with `parallel = 1`. Requests to other models do not wait. The Clef-Flash entry serialises across processes without blocking embeddings.
- Readiness: router start waits up to 180 s for `GET /health` 200 (no model loads at start). Before the first request to model X in a lease, OMRS reads `GET /v1/models`. When X is not `loaded`, OMRS sends `POST /models/load` and polls until `loaded` or `failed`, up to `MODEL_LOAD_TIMEOUT_SECONDS = 300` (fixed constant, not a setting). A request timeout (decision 120 s, classification, embeddings) starts after the model is loaded. A failed load gives reason `model-load-failed` for X only.

Spike 1.2 results on b11941 (`evidence/spike-1.2.md`):

- `/health` answers 200 with no model loaded (0.12 s after start).
- `status.value` is `unloaded`, `loading` or `loaded`; `status.args` and `status.preset` are present. A `memory` object (`status`, then `min`, `max` and `effective` per device, in bytes) appears only when the memory margin is above 0.
- Load took 4.5 s to 5.2 s for a 4B Q8_0 model; unload 0.1 s. With a margin above 0 the router first measures each model in a short-lived `--offline` child, so the first load call can wait several seconds. `MODEL_LOAD_TIMEOUT_SECONDS = 300` covers it.
- Autoload is on by default: a request to an unloaded model loads it. OMRS still makes the model ready with `POST /models/load` first, so the request timeout never includes a load.
- An unknown name gives 404 on `POST /models/load` and 400 on unload and proxied requests. OMRS refuses unlisted names before any contact (D6), so it never relies on either code.

### D9. Child processes: stop and memory

Each loaded model is a child `llama-server`. Stop still signals the router's process group (SIGTERM, 10 s, SIGKILL). Memory is the sum of the router's RSS and its direct children's RSS. OMRS reads the direct children of the recorded pid only (Linux: every `/proc/<pid>/task/*/children` file, because each child hangs under the router thread that spawned it, so the main thread's file alone finds none; macOS `proc_listchildpids`) and counts a child only when its command line holds the recorded binary path. It still lists no other process. The short-lived `--offline` measuring children (about 1 MB each) pass that test and are counted; their size does not matter. The per-model row shows the router's own `memory` figure when the router reports it.

Spike 1.3 results on b11941 (`evidence/spike-1.3-macos.md`, `evidence/spike-1.3-linux.md`): children share the router's process group and session on both systems. A group SIGTERM ended every process within 0.14 s. After SIGKILL of the router pid alone, every child exited within 0.03 s: each child exits when its stdin pipe from the router closes (`server-common.cpp`). A kill during a model load left nothing behind. The stop condition did not fire, so no per-child stop is added. The Linux run used an arm64 container; process-group and pipe behaviour is the same on x86-64.

### D10. Decision models on the router

The b11941 source forwards `POST /v1/systemone` in router mode. Spike 1.1 confirms it live with Clef-Flash Q8_0 and its projector, and runs the projector smoke test (ADR-110 decision 3) through the router.

- Outcome A (expected): a managed decision entry names a list entry with `projector` and `parallel = 1`. The router checks the build floor b11941 when any decision entry is listed (`wrong-build`). `GET /v1/runtimes` shows the decision model as a model of the `router` item.
- Outcome B (spike fails): decision models keep their own `decision-<name>` runtimes as today. Only their Settings rows move into the Router panel as "Own server". The change is updated before group 5 to restore the removed requirement.

Spike 1.1 result (`evidence/spike-1.1.md`): outcome A. The Clef-Flash Q8_0 entry with its projector and `parallel = 1` loaded in 3.5 s; `status.args` showed `--model`, `--mmproj` and `--parallel 1`. A `POST /v1/systemone` built by OMRS `build_request` returned 200 in 0.67 s. OMRS `run_smoke_test` passed through the router: right text 0.9387, wrong text 0.0195, margin 0.919 against the 0.2 limit.

### D11. Embeddings preset and shipped defaults

The shipped list (code default) holds two entries with no file. The panel shows "Not downloaded" and Get this model.

| Id | `model` | Preset | Roles |
| --- | --- | --- | --- |
| `qwen3-embedding-4b` | `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` | `embeddings=true pooling=last embd-normalize=2 ctx-size=8192 batch-size=8192 ubatch-size=8192 parallel=1 kv-unified=false` | embeddings |
| `qwen3-4b` | `Qwen/Qwen3-4B-GGUF:Q8_0` | `ctx-size=32768 parallel=2` | classification |

- Embeddings write `pooling`, `ctx-size`, `batch-size` and `ubatch-size` explicitly. `ubatch-size` must hold the longest chunk, or one input splits across batches. `parallel=1` and `kv-unified=false` keep each vector independent of what shares its batch (llama.cpp issue #6950). The request lock serialises embedding calls across processes.
- `embd-normalize=2` gives unit vectors, which the norm guard expects.
- An entry with `embeddings=true` cannot hold a Chat, classification or judge role (refused with `role-mismatch`), because the child runs embedding-only.
- Qwen3-4B: the shipped `qwen3-4b` entry serves classification only. `ctx-size=32768` with two slots gives 16,384 tokens per slot, so two classification calls run at once. The operator can pick this entry for Chat too, or add another entry (D14).
- Default role values: `llamacpp_embed_model = Qwen/Qwen3-Embedding-4B-GGUF:Q8_0`, `llamacpp_chat_model = Qwen/Qwen3-4B-GGUF:Q8_0`, `answer.provider = llamacpp`, `answer.model = ""` (no Chat model chosen, D14). `metadata.ollama_classify_model` default becomes `""`, and the Ollama provider asks for a model when the user picks it.
- The embedding identity string keeps the `org/repo:QUANT` form from now on, so a later file move does not re-index.

### D12. Pinned binaries on macOS and Linux

OMRS provisions llama.cpp b11941, the build that ADR-110 and ADR-113 already pin:

| Platform | Archive |
| --- | --- |
| macOS arm64 | `llama-b11941-bin-macos-arm64.tar.gz` |
| Linux x86-64, CPU | `llama-b11941-bin-ubuntu-x64.tar.gz` (CPU only) |
| Linux x86-64, CUDA | `llama-b11941-bin-ubuntu-cuda-12.8-x64.tar.gz` plus `cudart-llama-b11941-bin-ubuntu-cuda-12.8-x64.tar.gz` |

- The pins (names and SHA-256) live in `integrations/llamacpp_runtime/pins.py`. A test checks that the tag equals the dots-mocr engine's `LLAMA_TAG`.
- A provisioning job (Integrations card "llama.cpp", `manage` scope, on request only) and a CLI command `omrs llamacpp install [--flavour cpu|cuda]` download, check SHA-256, unpack and place the binary in `$XDG_DATA_HOME/omrs/llamacpp/b11941-<flavour>/` (else `~/.local/share/omrs/...`). The CLI covers headless RunPod pods. Neither starts a server.
- Each flavour unpacks into its own folder: every archive unpacks to a `llama-b11941/` folder, so two flavours in one parent would overwrite each other (spike 1.4).
- CUDA layout: the `cudart` files go beside `llama-server`. Every llama.cpp library uses RUNPATH `$ORIGIN`, so they resolve with no `LD_LIBRARY_PATH` (spike 1.4).
- After unpacking, the job runs `llama-server --version` and checks that it reports build 11941. Any failure is refused with reason `binary-check-failed` and the loader's message. This one check covers a host that is too old (the CUDA build needs glibc 2.38, so Ubuntu 24.04 or newer; the CPU build needs glibc 2.34) and a missing `libgomp1`.
- For the CUDA flavour the job also runs `llama-server --list-devices` and needs at least one CUDA device in its output, else reason `cuda-device-missing`. The exit code cannot tell: the CUDA build exits 0 and lists no device when the driver is missing (spike 1.4).
- `llamacpp_server_binary` set means a user path. The program rule still applies, and the router refuses a build below b11941 (`wrong-build`). Homebrew b11960 passes.
- Flavour default on Linux: CUDA when `/proc/driver/nvidia/version` exists, else CPU. CUDA 12.8 is chosen over 13.4 because it needs an older driver. Decided by the operator on 2026-11-06 (Q4).
- The flavour is visible and editable in the web GUI. The Integrations llama.cpp card shows the detected flavour as the default and lets the operator choose CPU or CUDA before install (Linux x86-64 only). The install request (`POST /v1/llamacpp/router/install`) carries the chosen flavour, and `GET /v1/llamacpp/router/install` reports the detected one. The CLI keeps `--flavour cpu|cuda` and uses the same detection when the flag is absent. macOS arm64 has one build and shows no choice.

Alternative: user path only. Rejected: RunPod pods have no Homebrew, and ADR-103 asks for a pinned build.

### D13. Ollama out of defaults, tests, CI and first-choice docs

- Code: the Ollama provider, decision kind and download source stay. Only defaults change (D11).
- `tests/conftest.py`: environment defaults equal the shipped llama.cpp defaults. The embedding mock patches the llama.cpp embedding builder, not `OllamaEmbedding`. Ollama tests opt in with their own fixture. The stale comment about the empty `llamacpp` group goes.
- A new fast test checks that every provider, model and URL value conftest sets equals the shipped default (`Settings` field defaults and `defaults.yaml`). Mutation check: changing one conftest value makes it fail.
- `ci.yml` and `local_ci.sh` drop the Ollama environment blocks. The slow suite runs only when `GET <router>/health` answers 200 and `/v1/models` lists the default embedding model; it prints "Slow tests skipped: no llama.cpp router at 127.0.0.1:8080" otherwise.
- Tier 2 nightly job: installs the pinned b11941 CPU build and serves `Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0` (the Ollama gate's model family, small for a CPU runner). Its thresholds are re-measured once. The job comment states why its model differs from the shipped default.
- `.env.example` and repo `.env` hold no provider, model or URL keys. They hold secret notes, commented developer overrides, and a pointer to `omrs config init` and `omrs.jsonc`.

### D14. Chat default

`answer.provider = llamacpp` and `answer.model = ""`: no Chat model is chosen on a fresh install. Classification keeps `Qwen/Qwen3-4B-GGUF:Q8_0`, and the shipped `qwen3-4b` list entry serves classification only. Decided by the operator on 2026-11-06 (Q2).

- The Chat page shows "Choose a Chat model" with a picker of router list entries and a "Get this model" action for an entry that has no file. The operator can pick any local model for Chat, including the classification model, as a deliberate choice.
- A Chat request with no model returns a plain setup message that names the setting (`answer.model`). It never crashes and never falls back to the classification model.
- The claim-check judge follows the same rule. With `answer.verify_provider` on llama.cpp and `answer.verify_model` empty, the judge is not built and the judge status gives the reason `no-model` (existing guard `Choose a judge model in Settings > Chat.` in `compose_answer.py`, which holds because the llama.cpp provider has no default answer model). The llama.cpp client builds the Chat and judge roles only from an explicit model name. An empty name never selects `llamacpp_chat_model`.
- Role mismatch (D11) still applies: an embedding entry cannot be picked for Chat.

Alternative rejected: Chat shares the classification model (`Qwen/Qwen3-4B-GGUF:Q8_0`) by default. The operator's reason: Chat and classification would clash on one model. This was the first draft of this design.

### D15. Memory limits

`--models-max 4` and `--models-memory-margin 8192` (MiB). On a 64 GB Mac during ingest: embeddings 4B Q8_0 (about 4.3 GB plus a small cache), Qwen3-4B Q8_0 (about 4.3 GB plus about 4.8 GB of f16 cache at 32,768 tokens), Clef-Flash when routing runs, and dots.mocr OCR outside the router. That stays well under 64 GB and leaves 8 GiB free for the OS and the app. On a GPU pod the margin applies per device. Values accepted by the operator on 2026-11-06 (Q3).

Both values are visible and editable in the web GUI, in Settings > llama.cpp Router panel, as two rows:

| Row | Key | Range |
| --- | --- | --- |
| Models loaded at once | `llamacpp_router_models_max` | 1 to 16 |
| Free memory margin (MiB) | `llamacpp_router_memory_margin_mib` | 0 to 262,144 |

Each row shows the value in force, its source (default, `omrs.jsonc`, or locked by environment), the default, and one plain help line. Each row offers Edit, Save and Use default. A save of either value changes a router argument, so the panel shows "Restart to apply" beside Restart (D7) until the router restarts. A locked row shows a lock and the variable name, and offers no edit.

### D16. Fake llama server router mode

`tests/fixtures/llamacpp/fake_llama_server.py` gains `--models-preset`: it parses the INI file, serves `GET /v1/models` with `status` and `args`, `POST /models/load`, `POST /models/unload` and `GET /models?reload=1` with b11941's unload rule, routes POSTs by `model`, and starts one real child process per loaded model in its own process group. Tests of stop, memory and reload use it. No test starts a real `llama-server`.

### D17. Pipeline sweep alignment

This change lands before `pipeline-sweep-llamacpp`. That design plans `llama serve` (the Llama app binary, refused by the program rule), its own preset file, and a non-goal that keeps live, CI and defaults on Ollama. A task amends the sweep's design to run on the OMRS router (scratch `OMRS_CONFIG_DIR` and `OMRS_STATE_DIR`, entries with its D6a presets) and to drop the contradicting non-goal. This change edits no file of that change.

## Risks / Trade-offs

- [The router reads every Hugging Face cache model and may autoload one on a stray request] → The router environment points `LLAMA_CACHE` at an empty folder (D4), and OMRS refuses unlisted names (D6). The router binds loopback only.
- [`/etc/llama.cpp/config.ini` changes every model] → Known limit (D4). Likelihood 1 (no OMRS step writes it), impact 3.
- [LRU eviction between the readiness check and the request makes one request carry a load] → Load takes seconds on local disk; the decision timeout is 120 s. Rare (likelihood 2, impact 2).
- [Two processes with different settings fight over one model's preset] → Per-model `version-busy` (D7). A process rewrites only its own model's section.
- [One-slot embeddings slow a large ingest] → Batches of 100 inputs per request; measured in the live rollout. Raising `parallel` is one preset edit, at the cost of batch-dependent vectors.
- [Re-index cost: every collection re-ingests once] → Timed with the `local-ocr-per-backend-cuts` re-index. Release notes say so.
- [CUDA driver on a pod is older than CUDA 12.8 needs, or the pod image is older than Ubuntu 24.04] → The job refuses with `binary-check-failed` or `cuda-device-missing` (D12). The user path override stays.
- [Router-mode bug in b11941 (for example #30323, slower Qwen3 embedding mode)] → Spikes measure it. The pin moves only with a new ADR-103 check.
- [Retirement collides with the tripwire change] → Rebase rule in D2.

## Migration Plan

1. Merge after `local-ocr-per-backend-cuts`.
2. Upgrade start-up names every retired key in the environment or `.env`. The operator moves values per the table in D2.
3. Provision the router, download the models, switch live `omrs.jsonc` to one router address, remove stale keys.
4. Re-ingest every collection once. Check categories and search.
5. Rollback: revert the merge commit. The state folder holds no settings and can be deleted. A rollback re-indexes once more (identity changes back).

## Operator decisions (2026-11-06, gate G0)

- **Q1, router mode default (D2):** `managed` accepted. The Router panel shows the mode row (managed or external) and the router URL.
- **Q2, Chat default (D14):** changed. Chat does not share the classification model by default. `answer.provider = llamacpp` and `answer.model = ""`. Classification keeps `Qwen/Qwen3-4B-GGUF:Q8_0`, and the shipped `qwen3-4b` entry serves classification only. A fresh install shows "Choose a Chat model". A Chat or claim-check judge request with no model returns a plain setup message that names `answer.model`, never a crash and never a silent fallback to the classification model. If the user picks the classification model for Chat, Settings > Chat and the Router panel row show a warning (shared slots, shared context size, one reload for both). It suggests another router model, the user's own llama.cpp server through the OpenAI-compatible provider, or a hosted provider such as OpenRouter. It does not block Save (operator, 2026-11-06).
- **Q3, memory limits (D15):** `--models-max 4` and `--models-memory-margin 8192` MiB accepted. Added: both are visible and editable in Settings > llama.cpp Router panel as "Models loaded at once" (1 to 16) and "Free memory margin (MiB)" (0 to 262,144).
- **Q4, Linux flavour (D12):** CUDA 12.8 when an NVIDIA driver is present, else CPU, accepted. Added: the Integrations llama.cpp card shows the detected flavour as the default and lets the operator choose CPU or CUDA before install.

- **G2, design path (D10):** outcome A confirmed by the operator on 2026-11-06. Decision models run on the router in both modes; the `decision-<name>` runtime path goes (task 5.1).

## Spike results (2026-11-06, gate G2)

Evidence in `evidence/`. Build b11941, archives checked against the release SHA-256 values.

- 1.1 decision forwarding: outcome A (D10).
- 1.2 load, unload and reload: D7 and D8 hold; cache listing fixed by the router environment (D4).
- 1.3 child processes: no child survives on macOS or Linux; no per-child stop (D9).
- 1.4 Linux builds: SHA-256 match, layout and checks in D12. GPU part on a RunPod RTX A6000 (driver 595.91.07): CUDA device listed, model loaded (`evidence/spike-1.4-gpu.md`).
- 1.5 preset keys: D4 corrected (booleans, `embeddings`, reserved keys, `spec-type`, router environment).

## Open Questions

None left. Answered by the spikes: the `memory` field names (D8), the `cudart` layout (D12) and the CUDA 12.8 build on a RunPod driver (spike 1.4).
