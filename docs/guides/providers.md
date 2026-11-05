# Providers

OMRS supports multiple embedding and metadata LLM providers. Providers are selected independently via a two-tier system: category (`local`|`cloud`) + sub-provider — you can mix and match (e.g., cloud embeddings with a local LLM).

> **Scope:** This guide covers embedding and metadata LLM providers, and the two Chat-only providers (OpenAI-compatible and Anthropic). Document parsing (`DOCUMENT_BACKEND=azure`, Azure Document Intelligence) is a separate orthogonal axis — see [ADR-024](../adr/024-dual-deployment-modes.md).

## Overview

| Category | Sub-provider         | Embeddings        | Metadata LLM           | Extra deps                   |
| -------- | -------------------- | ----------------- | ---------------------- | ---------------------------- |
| `local`  | `llamacpp` (default) | `OpenAIEmbedding` | `OpenAILike` / `httpx` | None (base install)          |
| `local`  | `ollama`             | `OllamaEmbedding` | `Ollama` / `httpx`     | None (core)                  |
| `cloud`  | `openrouter`         | `OpenAIEmbedding` | `OpenAILike` / `httpx` | None (base install)          |

The LlamaIndex OpenAI-like packages are in the base install. The `llamacpp` and `openrouter` extras stay as empty extras, so `uv sync --extra llamacpp` and `uv sync --extra openrouter` still work.

`llamacpp` and `openrouter` both use the OpenAI-compatible API (`OpenAIEmbedding`, `OpenAILike`) — only `api_base` and `api_key` differ. The same pattern supports any OpenAI-compatible endpoint (vLLM, TGI, LocalAI, Azure OpenAI). See [ADR-026](../adr/026-provider-registry-and-openrouter.md) for the full rationale.

## Environment variables

### Provider selection

| Env var                 | Controls                | Default      | Valid values          |
| ----------------------- | ----------------------- | ------------ | --------------------- |
| `EMBED_PROVIDER`        | Embedding model         | `local`      | `local` / `cloud`     |
| `METADATA_LLM_PROVIDER` | Metadata extraction LLM | `local`      | `local` / `cloud`     |
| `LOCAL_BACKEND`         | Local sub-provider      | `llamacpp`   | `llamacpp` / `ollama` |
| `CLOUD_BACKEND`         | Cloud sub-provider      | `openrouter` | `openrouter`          |

> **Why `METADATA_LLM_PROVIDER` defaults to `local` regardless of `EMBED_PROVIDER`:** to prevent surprising cloud API costs. If you set `EMBED_PROVIDER=cloud`, metadata extraction still uses a local LLM unless you explicitly set `METADATA_LLM_PROVIDER=cloud`.

### llama.cpp (default local backend)

| Env var                 | Default                              | Purpose                         |
| ----------------------- | ------------------------------------ | ------------------------------- |
| `LLAMACPP_EMBED_MODEL`  | _(required)_                         | GGUF filename for embeddings    |
| `LLAMACPP_EMBED_URL`    | `http://localhost:8080/v1`           | llama-server embedding endpoint |
| `LLAMACPP_CHAT_MODEL`   | _(required for local metadata mode)_ | Text model (classification): the model for metadata extraction. Chat never uses it |
| `LLAMACPP_CLASSIFY_URL` | unset: uses `LLAMACPP_CHAT_URL`      | llama-server address for classification |
| `LLAMACPP_CHAT_URL`     | `http://localhost:8081/v1`           | llama-server address for Chat, and for classification while `LLAMACPP_CLASSIFY_URL` is unset |
| `LLAMACPP_CHAT_SERVER`  | `external`                           | Who runs the Chat server: `external` (the Llama app or another server you run) or `managed` (the `llama-server` that OMRS starts) |

Chat on llama.cpp uses the Chat model, `ANSWER__MODEL` with `ANSWER__PROVIDER=llamacpp` (Settings > Chat in `omrs web`). It never falls back to `LLAMACPP_CHAT_MODEL`. An empty Chat model is refused with "Choose a Chat model". See [llama.cpp Chat and classification](configuration.md#llamacpp-chat-and-classification).

```bash
# No extra needed: the OpenAI-like packages are in the base install

# Start two llama-server processes
llama-server -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --port 8080 --embeddings
llama-server -hf Qwen/Qwen3-0.6B-GGUF:Q8_0 --port 8081
```

**Managed server or your own.** You can start `llama-server` yourself, as above. This is the default, `LLAMACPP_CHAT_SERVER=external`. With `LLAMACPP_CHAT_SERVER=managed` (or "OMRS's own llama-server" on the llama.cpp card), OMRS can start, stop and restart one chat server for you (Settings > Providers > llama.cpp > Local server). The CLI and the MCP server start and share it too, and it stops when the last OMRS process leaves. That server loads the Chat model from Settings > Chat. It has no model setting of its own. omrs manages only the server it started. It never touches a server you started yourself. The embedding server is `external` by default. OMRS can manage it with `LLAMACPP_EMBED_SERVER=managed`. A managed server stops after 10 idle minutes and starts again on the next request. See [Local llama.cpp server](configuration.md#local-llamacpp-server) for the settings and guardrails.

```bash
# .env
EMBED_PROVIDER=local
METADATA_LLM_PROVIDER=local
LOCAL_BACKEND=llamacpp
LLAMACPP_EMBED_MODEL=Qwen3-Embedding-0.6B-Q8_0.gguf
LLAMACPP_CHAT_MODEL=Qwen3-0.6B-Q8_0.gguf
```

See [ADR-025](../adr/025-pluggable-inference-backend.md) for the full rationale.

### Chat-only providers (OpenAI-compatible and Anthropic)

These two providers serve the answers role only (`ANSWER__PROVIDER`, or Settings > Chat in `omrs web`). They are not valid for `EMBED_PROVIDER`, `LOCAL_BACKEND` or `CLOUD_BACKEND`.

| Provider | Env var | Default | Purpose |
|---|---|---|---|
| `openai_compatible` | `OPENAI_COMPATIBLE_BASE_URL` | `https://api.openai.com/v1` | Address of any server that speaks the OpenAI chat API (OpenAI, Together, vLLM, LM Studio) |
| `openai_compatible` | `OPENAI_COMPATIBLE_API_KEY` | unset | Optional. LM Studio and vLLM need none. Sent only to the address above |
| `anthropic` | `ANTHROPIC_API_KEY` | unset | Required. The address is fixed at `https://api.anthropic.com` |

`openai_compatible` uses `OpenAILike` from the base install. The address can be on this machine or remote. `anthropic` needs an extra, because it pulls boto3 and Google SDKs (about 40 MB):

```bash
uv sync --extra anthropic
```

The connection test sends `GET {base_url}/models` for `openai_compatible`, with a bearer header only when a key is set. For `anthropic` it sends `GET /v1/models` with the headers `x-api-key` and `anthropic-version: 2023-06-01`, and sends nothing when no key is set.

### Where provider values come from

For each address and key, the server uses the first source it finds, highest first: process environment, `.env`, `omrs.jsonc` in the user config folder (the Settings page writes this file), a key file `secrets/<provider>.key` (keys only), the default. `GET /v1/connections` reports the source as `env`, `dotenv`, `config-file`, `keychain`, `key-file`, `default` or `none`, and the top-level `user_config_dir` (with `~` for home).

- The environment, `.env` and `omrs.jsonc` lock the field in Settings. The card shows "Set from environment (read-only here)" or "Set from config file (read-only here)".
- A key file does not lock. The card shows "Set from key file (read-only here). Saving a key in the keychain overrides it."
- The CLI and the stdio MCP server read the environment, `.env` and the user config folder. They do not see values saved in the web page.
- The files in the user config folder are plaintext. The keychain stays the advice on a desktop. See [Configuration](configuration.md#user-config-folder).

### Ollama (alternative local backend)

| Env var                           | Default                  | Purpose                                  |
| --------------------------------- | ------------------------ | ---------------------------------------- |
| `EMBED_MODEL`                     | _(required)_             | Ollama embedding model name              |
| `OLLAMA_BASE_URL`                 | `http://localhost:11434` | Ollama server URL                        |
| `OLLAMA_CONTEXT_WINDOW`           | `16384`                  | Context window in tokens (2,048 to 262,144) for Chat and metadata extraction |
| `METADATA__OLLAMA_CLASSIFY_MODEL` | `qwen3:0.6b`             | Ollama model for metadata classification |
| `INGESTION__EMBED_BATCH_SIZE`     | `100`                    | Ollama `/api/embed` batch size           |

Context window. omrs sends `OLLAMA_CONTEXT_WINDOW` on every Chat and metadata call, so Ollama never reserves memory for the model maximum (TDR-036). Embedding models are not covered. See [Context windows](configuration.md#context-windows).

### OpenRouter (cloud backend)

OpenRouter is a cloud provider that implements the OpenAI-compatible API at `https://openrouter.ai/api/v1`. It uses the same LlamaIndex classes as llama.cpp (`OpenAIEmbedding`, `OpenAILike`) — only `api_base` and `api_key` differ.

| Env var                  | Default                       | Purpose                                                          |
| ------------------------ | ----------------------------- | ---------------------------------------------------------------- |
| `OPENROUTER_API_KEY`     | _(required)_                  | OpenRouter API key                                               |
| `OPENROUTER_EMBED_MODEL` | _(required for embeddings)_   | OpenRouter embedding model (e.g., `text-embedding-3-small`)      |
| `OPENROUTER_LLM_MODEL`   | _(required for metadata LLM)_ | OpenRouter chat model (e.g., `meta-llama/llama-3.1-8b-instruct`) |

```bash
# No extra needed: the OpenAI-like packages are in the base install
```

```bash
# .env — cloud embeddings with local LLM (cost-efficient)
EMBED_PROVIDER=cloud
METADATA_LLM_PROVIDER=local
LOCAL_BACKEND=ollama
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_EMBED_MODEL=text-embedding-3-small
```

```bash
# .env — fully cloud
EMBED_PROVIDER=cloud
METADATA_LLM_PROVIDER=cloud
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_EMBED_MODEL=text-embedding-3-small
OPENROUTER_LLM_MODEL=meta-llama/llama-3.1-8b-instruct
```

> **Adding other OpenAI-compatible providers:** The registry pattern supports any endpoint that implements the OpenAI API (vLLM, TGI, LocalAI, Azure OpenAI, actual OpenAI). Adding one requires a new `core/providers/<kind>/<name>.py` exposing `build(settings)` with a different `api_base`, plus one `register()` line — see [Adding a new provider](#adding-a-new-provider) below.

See [ADR-026](../adr/026-provider-registry-and-openrouter.md) for the full rationale.

> **Shared classification knobs, with per-provider timeout overrides:**
> `METADATA__CLASSIFY_MAX_ATTEMPTS` governs the retry budget for **all
> three** metadata LLM backends (Ollama, llama.cpp, OpenRouter) — it has
> no per-provider override. `METADATA__CLASSIFY_TIMEOUT` (per-attempt,
> direct-chat classification) and `METADATA__PIPELINE_TIMEOUT` (the
> `llamaindex` mode's multi-extractor pipeline) are shared defaults that
> each backend can override independently:
>
> | Backend      | Classify timeout override                        | Pipeline timeout override                        |
> | ------------ | ------------------------------------------------ | ------------------------------------------------ |
> | `llamacpp`   | `METADATA__LLAMACPP_CLASSIFY_TIMEOUT_OVERRIDE`  | `METADATA__LLAMACPP_PIPELINE_TIMEOUT_OVERRIDE`  |
> | `ollama`     | `METADATA__OLLAMA_CLASSIFY_TIMEOUT_OVERRIDE`    | `METADATA__OLLAMA_PIPELINE_TIMEOUT_OVERRIDE`    |
> | `openrouter` | `METADATA__OPENROUTER_CLASSIFY_TIMEOUT_OVERRIDE`| `METADATA__OPENROUTER_PIPELINE_TIMEOUT_OVERRIDE`|
>
> Each is unset (`None`) by default and falls back to the shared
> `METADATA__CLASSIFY_TIMEOUT` / `METADATA__PIPELINE_TIMEOUT` — set one
> only on the machine that needs different tuning (e.g. a slower local
> box wants a longer `llamacpp` pipeline budget without loosening the
> fast-fail classify budget elsewhere). The model field stays per-provider
> too (`METADATA__OLLAMA_CLASSIFY_MODEL`, `LLAMACPP_CHAT_MODEL`,
> `OPENROUTER_LLM_MODEL`). See [Metadata extraction](metadata-extraction.md#timeouts).

## Registry pattern

Providers are resolved through flat, per-domain lazy registries. Each registry maps a name to a `"module:attr"` import string, resolved and cached on first `get()`. Importing a registry never imports a provider module, so a missing optional dependency degrades gracefully.

| Registry | Location |
| --- | --- |
| Embedding providers | `core/providers/embeddings/registry.py` |
| LLM providers | `core/providers/llm/registry.py` |
| Metadata extraction backends | `core/metadata/registry.py` |
| Decision model kinds | `core/providers/decision/registry.py` |

Provider construction (instantiating the LlamaIndex client) lives in `compose.py` (`build_embed_model`), enforced by `import-linter`. The registries only resolve names to callables; they do not construct. Metadata extraction resolves LLMs through its own dispatch in `core/metadata/extractor.py`, not through the composition root.

Each LLM provider module also declares a `CONNECTION` descriptor (`ConnectionDescriptor` in `core/providers/llm/connection.py`) for its Providers card. The optional field `model_source` says whether the app can search for and download a model for that provider. The default is `None`: the card shows no Get a model panel and the download routes refuse the provider with 400.

| `model_source` | Provider | What the app does |
| --- | --- | --- |
| `huggingface-gguf` | `llamacpp` | Searches Hugging Face for GGUF repos, lists the files by quantisation label, and downloads them into the Hugging Face cache. |
| `ollama-pull` | `ollama` | Lists built-in Ollama names and Hugging Face GGUF repos, and runs an Ollama pull. |

The pure rules (name checks, label parser, built-in Ollama names) live in `core/providers/model_sources.py`. The download job picks its adapter from a table keyed by the source kind, not by provider name.

Two more descriptor flags say how an answer role uses the provider (ADR-108). The routes and the composition root read the flags. They never test the provider name.

| Flag | Default | llama.cpp and Ollama | What it does |
| --- | --- | --- | --- |
| `default_answer_model` | `True` | `False` | Whether the provider has a model setting of its own that an empty judge model may use. With `False`, an empty judge model or Chat model is refused, never filled with a classification model (the llama.cpp Text model or `metadata.ollama_classify_model`). The claim check is skipped with "Choose a judge model in Settings > Chat." Chat refuses with "Choose a Chat model in Settings > Chat.", and `GET /v1/settings/chat` gives the reason `no-model`. OpenRouter keeps `True` and its documented default. |
| `test_checks_model_list` | `False` | `True` (llama.cpp only) | With `True` and the Chat server choice `external`, the Chat test reads the provider's model list (`{LLAMACPP_CHAT_URL}/models`) first. A model that the list does not hold gives the reason `model-not-listed`, and no prompt is sent. A list that cannot be read gives the usual reasons (`refused`, `timeout`, `http-NNN`). With `managed`, the test skips the list, because OMRS's own server loads the Chat model. |

The card layout comes from the descriptor too. `ConnectionField` and `ReadOnlyValue` have an optional `group`: `embeddings` (title "Embeddings"), `metadata` ("Classification (metadata)") or `answers` ("Chat"). The card shows the fields without a group first, then each group under its title, in that order. Only llama.cpp sets a group, so the other cards show one block with no titles. `ConnectionField` also has an optional `follows`: the id of the field whose value applies while this field is not set. The llama.cpp Classification address (`classify_url`) follows the Chat address (`chat_url`). `GET /v1/connections` then reports the Chat address as its value, with the source `default`.

<!-- registry-names:embeddings -->
Registered embedding providers: `ollama`, `llamacpp`, `openrouter`.
<!-- /registry-names:embeddings -->

<!-- registry-names:llm -->
Registered LLM providers: `ollama`, `llamacpp`, `openrouter`, `openai_compatible`, `anthropic`.
<!-- /registry-names:llm -->

### Adding a new provider

1. Add `core/providers/<kind>/<name>.py` exposing `build(settings)` (match the signature of `ollama.py` or `llamacpp.py`).
2. Add one `register("<name>", "omrs.core.providers.<kind>.<name>:build")` line at the bottom of that registry.
3. Add the optional-dependency extra in `pyproject.toml` and, if it is an extra, an entry in `_PROVIDER_EXTRAS` (`core/providers/llm/registry.py`).
4. Add env vars to `.env.example`.
5. Add the name to the `<!-- registry-names -->` block above.
6. Add tests in `tests/test_registry_contract.py` and `tests/unit/test_provider_config.py`.
7. If the provider can download models, set `model_source` on its `CONNECTION` descriptor to `huggingface-gguf` or `ollama-pull`. Leave it unset for any other provider. A third source kind needs a new adapter and a registry for the job, not a name check. See ADR-106.

No changes to `core/ingestion/`, `core/retrieval/`, or `transports/` are needed — they consume providers through the registries and the composition root.

## Decision models

A decision model answers one yes/no question about a document page. A document router uses it to find pages whose native text is junk (ADR-110). Decision models are named entries in the `decision_models` map of `omrs.jsonc`. The map format is in [Configuration](configuration.md).

### Kinds

Each entry has a kind. The kind comes from `core/providers/decision/registry.py`. All kinds send the same System One request: one `noul` question (options `no` and `yes`), the page text in `state.text` and, for an image router, one page image. The reply gives P(yes) between 0 and 1.

| Kind | Request | Image | Status |
| --- | --- | --- | --- |
| `llamacpp` | `POST <address>/v1/systemone` | `images` list, data URL | Tested (Experiment 43) |
| `typesafe` | `POST https://api.typesafe.ai/v1/systemone` | `assets` map | Tested (Experiment 43) |
| `cloudflare` | `POST <address>/ai/run/@cf/cloudflare/<model>` | `images` list, base64 | Not yet tested |
| `ollama` | `POST <address>/v1/systemone` | `images` list, base64 | Not yet tested |

"Not yet tested" means no live request of that kind has passed the smoke test. The entry still works. Each adapter module holds the label as `NOT_YET_TESTED`, and `registry.not_yet_tested()` lists those kinds. Remove the label only after one live request passes the smoke test and the result is recorded.

A reply without a P(yes), or with a value that is not a finite number in [0, 1], counts as a failed request. The log gives the fixed reason `malformed-reply` and never the reply.

### Local and hosted

An entry whose address is not a loopback address (`127.0.0.1`, `::1` or `localhost`) is hosted. A router that uses a hosted entry sends nothing until the router itself sets `send_off_machine: true`. Without it, the router status is `needs-opt-in`.

Only a hosted request with an image carries the header `TypeSafe-Danger-Zone-Images: true`. A local request never carries it.

### Key references

The `key` field holds a reference, never the key:

- `env://NAME` reads the environment variable `NAME`.
- `file://~/.config/omrs/secrets/<name>.key` reads a file inside the `secrets/` folder.
- `keychain://<provider>` reads the system keychain.

A literal key is ignored. `compose_decision.py` resolves the reference with the same rules as the provider keys (ADR-083, gotcha 18). A reference that does not resolve gives the status `request-failed`, and no request goes out.

### The 8-bit rule

A decision model on this machine must run at 8-bit or higher: Q8_0, F16, BF16 or F32 (AGENTS.md gotcha 16). A 4-bit build gave different answers in Experiment 38.

- A managed `llamacpp` entry: OMRS reads `general.file_type` from the GGUF header of `model_file`. It reads only the header bytes. Any other type, such as Q4_K_M, gives `quantisation-refused` with the rule text.
- An external `llamacpp` or `ollama` entry: OMRS reads the quantisation marker in the model name that the server reports, for example `Clef-Flash-Q8_0.gguf`.
- When no type can be read, the entry shows "Quantisation not checked".

Hosted kinds have no quantisation check.

### Vision projector

An image router needs an entry with `images: true`. A managed image entry must also declare `projector_file` (the `--mmproj` flag). A llama.cpp server without a projector answers an image request with HTTP 501.

Before an image router uses an entry, OMRS runs a smoke test. It sends one bundled page image (`core/providers/decision/smoke_page.png`) twice: with its right text and with wrong text. The test passes when P(yes) for the right text is higher by at least the margin 0.2 (`SMOKE_MARGIN`, version `exp43-r4-2026-11-02`). Experiment 43 recorded that margin: Clef-Flash Q8_0 gave 0.903 against 0.069, hosted Jev 0.39 against 0.01. A failed smoke test gives `projector-not-loaded`.

### Managed runtime

A `llamacpp` entry sets `server` to `external` or `managed`. OMRS starts nothing for an external entry and sends requests to its address.

A managed entry runs as the runtime `decision-<entry name>`, role `decision`. It follows the same lease, adoption, idle-stop and stop rules as the other managed runtimes, and `GET /v1/runtimes` lists it. To start it, OMRS needs:

- `LLAMACPP_SERVER_BINARY`, the `llama-server` program.
- A loopback `http` address with a port. The server binds `127.0.0.1` on that port.
- `model_file` and `model_sha256`. An image entry also needs `projector_file` and `projector_sha256`.

The server serves one request at a time (`--parallel 1`). It gets `--mmproj` for an image entry. A changed file gives `file-changed`, and the server does not start. If a field is missing, the router status is `unreachable`.

The server starts on the first request of a router or of Test, not at start-up.

### Build floor

Image requests to llama.cpp need build b11941 or later, the build of Experiment 43 (`BUILD_FLOOR` in `core/providers/decision/checks.py`). Before OMRS starts a managed decision runtime, it reads the build from `llama-server --version`. A lower build, or no build number, gives `wrong-build`. The server does not start, and the reason names the build found and the floor. The router status is `wrong-build`. OMRS does not check the build of an external server.

### When the checks run

Building the judge sends nothing. The checks run on the first page that the router judges: the quantisation check, one text request with no page content, and the smoke test for an image router. For a managed entry, the text request starts the runtime, so the build check runs then. They run once per process for each entry. Fixed reasons: `unknown-model`, `unreachable`, `quantisation-refused`, `projector-not-loaded`, `wrong-build`, `needs-opt-in`, `request-failed`. Logs give the reason and counts only, never page text, images, keys or reply bodies.

Test on the Providers card runs the checks again for one entry (`compose_decision.test_decision_model`). It also updates the result that the routers use. The text request holds no page content, so Test also sends it to a hosted entry without the router opt-in. Test shows the quantisation line, the projector line of an image entry and, for a managed entry, the build line.

## ChromaDB dimension lock

ChromaDB locks the vector dimension at collection creation time. Switching from `local` + `ollama` (1024-dim for `qwen3-embedding:0.6b`) to `cloud` + `openrouter` (1536-dim for `text-embedding-3-small`) requires re-ingestion:

```bash
rm -rf chroma_db
omrs ingest /path/to/docs/
```
