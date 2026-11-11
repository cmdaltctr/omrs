# Configuration

Where settings live, which one wins, and what every setting does.

---

## The short version

Settings come from six places. Each beats the one above it:

| # | Source | What belongs here |
|---|---|---|
| 1 | Model defaults, in the code | Last resort. You never edit these directly. |
| 2 | `src/omrs/config/defaults.yaml` | Project-wide defaults. Committed. Shared by everyone. |
| 3 | Profile YAML (`config/profiles/*.yaml`) | Per-collection behaviour |
| 4 | `omrs.jsonc` in the [user config folder](#user-config-folder) | Your settings. Edit it by hand or on the Settings page. |
| 5 | `.env` | Your machine: tokens, URLs, paths |
| 6 | Environment variables | Highest. Wins over everything. |

The Settings page shows the source of each value: `env`, `dotenv`, `config-file`, `yaml` or `default`. Only `env` and `dotenv` lock a field on the page. A value in `omrs.jsonc` does not lock it.

**Rule of thumb:**

- Sensible default for everyone → `defaults.yaml`
- Your own settings, kept in one file you can edit or the page can edit → `omrs.jsonc`
- Secret, or specific to your machine → `.env`
- Different for one collection → its profile
- Just for this one command → an environment variable

**Why the schema is Python while the values are YAML.** In short: YAML for
data, Python for the contract. Humans edit values, so the values live in YAML
(`defaults.yaml` and the profile bundles), while the contract (which keys
exist, their types, which source wins) is defined once in the typed Python
models in `config/__init__.py`. A misspelt key in YAML or an environment
variable therefore fails at startup and lists the valid fields, instead of
being silently ignored.

### The trap worth knowing

`.env` and environment variables sit **above** profiles. Put a profile lever
(`retrieval.top_k`, `retrieval.rerank_enabled`, `retrieval.hybrid_enabled`,
`chunking.strategy_fallback`, `metadata.taxonomy_mode`) in either and it
overrides every profile silently.

Real example: `RETRIEVAL__TOP_K=5` in `.env` meant the `documents` profile
(top_k 10) and the `codebase` profile (top_k 20) both returned 5 results.
Profiles looked broken. Nothing warned about it.

The same lever in `omrs.jsonc` does the opposite: each collection's profile
replaces it, so it changes nothing. `omrs config show` still lists it with
source `config-file`, so it looks in force (ADR-087 addendum).

**Keep the profile levers out of `.env` and `omrs.jsonc`. Keep `.env` for connection details and secrets only.**

---

## Variable naming

Settings that belong to one area are nested. The environment variable joins the
block and the field with a double underscore:

```
retrieval.top_k             →  RETRIEVAL__TOP_K
chunking.chunk_size         →  CHUNKING__CHUNK_SIZE
ingestion.embed_batch_size  →  INGESTION__EMBED_BATCH_SIZE
embedding.norm_tolerance    →  EMBEDDING__NORM_TOLERANCE
metadata.extraction_mode    →  METADATA__EXTRACTION_MODE
```

Cross-cutting settings stay flat: `EMBED_MODEL`, `CHROMA_PERSIST_DIR`,
`VECTOR_STORE`, `LANCEDB_URI`, `RAG_PROFILE`, `PDF_READERS`, and every
credential.

In YAML the same thing looks like this:

```yaml
retrieval:
  top_k: 10
  rerank_enabled: false

chunking:
  chunk_size: 512

# cross-cutting settings stay at the top level
COLLECTION_NAME: documents
```

### Upgrading from v1

Pre-v2 flat names (`TOP_K`, `CHUNK_SIZE`, `METADATA_EXTRACTION_MODE`, …) are no
longer read. The app **refuses to start** and names the replacement, rather
than silently falling back to a default.

Two guards catch mistakes:

- A wrong nested key (`RETRIEVAL__TOPK`) fails immediately, listing the valid
  fields.
- An old flat name (`TOP_K`) fails with the new name.

Full rename table: [ADR-037](../adr/037-architecture-v2-conformance.md).

---

## Profiles

A profile is a named bundle of retrieval behaviour, bound to a collection.

| Profile | For | top_k | Reranker | Hybrid search |
|---|---|---|---|---|
| `documents` | Papers, reports, prose | 10 | on | off |
| `codebase` | Source code | 20 | off | on |
| `hybrid` | Not a profile — a mode selector | — | — | — |

**Profiles only control five things:**

- `retrieval.top_k`
- `retrieval.rerank_enabled`
- `retrieval.hybrid_enabled`
- `chunking.strategy_fallback`
- `metadata.taxonomy_mode`

Everything else — chunk size, storage path, embedding model — is shared.

### Choosing a profile

Server-wide default:

```bash
RAG_PROFILE=documents
```

Per collection, which is the point of the feature:

```bash
omrs set-profile -c my_code -p codebase
```

Set `RAG_PROFILE=hybrid` to let each collection pick its own; untagged
collections fall back to `default_profile` in `hybrid.yaml`.

A collection cannot be tagged `hybrid` — it selects a mode, it is not one.

### User profiles

A user profile is a profile that you make in the web workspace. It has an id,
a title, a **base profile** (`documents` or `codebase`) and three pipelines:
**Ingest**, **Search** and **Answer**. The base profile gives the five profile
settings. The pipelines decide how the collection reads, searches and answers.

A collection follows a user profile when its `profile` tag holds the user
profile id, for example `my-notes`. `RAG_PROFILE` and `default_profile` in
`hybrid.yaml` accept `documents` and `codebase` only.

The web server owns the workspace. It reads and writes the database file
`workspace.db` in the folder of `omrs web --workspace` (default
`~/.omrs/workspace`). Other processes read user profiles from that default
folder, read-only, when the file exists:

| Process | Reads user profiles | Binds a user profile to a collection |
|---|---|---|
| `omrs web` and its MCP endpoint | Yes, from its own workspace | Yes |
| Stdio MCP server (`omrs`) | Yes, from the default workspace | No |
| CLI (`search`, `answer`, `ingest`, `watch`) | Yes, from the default workspace | No (`omrs set-profile` takes built-in names only) |

To bind a user profile, use Knowledge Base > Profile in the web app, or the
`change_collection_profile` tool on the MCP endpoint of `omrs web`.

If the default workspace file does not exist, a collection tagged with a user
profile fails with this error:

```text
Collection 'notes' uses the profile 'my-notes', which is not a built-in
profile. User profiles live in the web workspace, and no workspace database
was found at ~/.omrs/workspace/workspace.db. Start `omrs web` once with the
default workspace, or change the collection's profile to 'documents' or
'codebase'.
```

To fix it, do one of these:

1. Start `omrs web` once with the default workspace.
2. Run `omrs set-profile -c notes -p documents` (or `codebase`).

If you start `omrs web` with another `--workspace` folder, the other
processes do not find its profiles. The error names the path they read.

### Why the reranker differs

The `documents` profile turns the reranker on; `codebase` leaves it off. That
is not an oversight. Experiment 10 measured the reranker making code retrieval
**19–27% worse** and adding ~14s per query. On prose it helps. See
[ADR-019](../adr/019-reranker-disabled-for-technical-workloads.md) and
[ADR-030](../adr/030-prefer-int8-onnx-variant-for-modernbert-rerankers.md).

---

## What goes in `.env`

Only these:

```bash
# Where the vector database lives
VECTOR_STORE=lancedb
LANCEDB_URI=./lancedb
COLLECTION_NAME=documents
# Chroma only: install the `chroma` extra, set VECTOR_STORE=chroma,
# then keep CHROMA_PERSIST_DIR pointed at its existing directory.
CHROMA_PERSIST_DIR=./chroma_db

# Provider, model and address settings live in omrs.jsonc (run `omrs config init`)

# Secrets
HF_TOKEN=...
OPENROUTER_API_KEY=...
AZURE_DOC_INTELLIGENCE_KEY=...
CHROMA_CLOUD_API_KEY=...
```

If you find yourself putting `RETRIEVAL__*` or `CHUNKING__*` in here, it
probably belongs in `defaults.yaml` or a profile instead.

---

## All settings

Defaults below are what ships in `defaults.yaml`.

### Storage

| Variable | Default | What it does |
|---|---|---|
| `CHROMA_PERSIST_DIR` | `./chroma_db` | Where the database is written |
| `COLLECTION_NAME` | `documents` | Default collection |
| `CHROMA_SCAN_PAGE_SIZE` | `10000` | Rows per page when scanning metadata |
| `VECTOR_STORE` | `lancedb` | Store implementation: `lancedb` (base-install default) or `chroma` (optional extra). Unrecognised values fail startup listing the registered names |
| `LANCEDB_URI` | `./lancedb` | Parent directory for LanceDB tables (`VECTOR_STORE=lancedb` only). Embedded/local only in v1 |
| `CHROMA_MODE` | `local` | `local` or `cloud`. Explicit selection; unrecognised values fail startup |
| `CHROMA_CLOUD_API_KEY` | — | Required when `CHROMA_MODE=cloud`. `.env` only — never in YAML, logs, or results |
| `CHROMA_CLOUD_TENANT` | — | Optional tenant. Supplied with `CHROMA_CLOUD_DATABASE`, or both omitted |
| `CHROMA_CLOUD_DATABASE` | — | Optional database. Supplied with `CHROMA_CLOUD_TENANT`, or both omitted |

### Storage layout and concurrency

Three layers are often confused. Keep them separate.

**Layout.** LanceDB (the base-install default) stores each collection as its
own table directory, `{LANCEDB_URI}/{collection_name}.lance`. A collection
name must be a non-empty single path component. Separators, control
characters, `.`, `..`, and absolute paths are rejected. Validation runs
before any table access touches
disk (`core/vectordb/lancedb/table_name.py`). Chroma (the optional extra) keeps
collection names as logical identifiers inside one shared persist directory
(`CHROMA_PERSIST_DIR`). Per-collection Chroma persist directories, and Chroma
name validation, are deferred to a future change.

**Process mutation lock.** Ingestion mutations run inside one process-global
lock (`write_lock` in `core/ingestion/_state.py`, acquired by `_commit_sync`
in `core/ingestion/replacement.py`). The lock serialises mutations across all
collections within one process. It is not per-collection. Other processes
cannot see it.

**Cross-process writes.** Concurrent writes from separate processes (for
example, two stdio MCP clients) are unverified for both backends. No
two-process concurrent-write experiment has run. Do not assume isolation from
the `.lance` layout.

The deferred Chroma scope waits for demonstrated operator demand, and any
future contention claim needs a two-process, two-collection concurrent-write
experiment first.

### Chroma deployment mode

Chroma is an explicit optional backend. Install it with `uv sync --extra chroma`
in a source checkout, or `pip install "omrs[chroma]"` from a package. Set
`VECTOR_STORE=chroma` before using its local or cloud modes. CVE-2026-45829
(PYSEC-2026-311) is active for this optional dependency. Do not expose Chroma's
Python FastAPI server through this project.

`CHROMA_MODE` selects the Chroma deployment explicitly. The default mode is
`local`, the embedded `PersistentClient`. Selecting `cloud` connects to hosted
Chroma Cloud. API-key presence never switches storage: a missing shell
variable cannot silently redirect a process to an empty local database.
Unrecognised values fail settings validation.

Embedding compute and vector storage are independent axes. `EMBED_PROVIDER`
selects where embeddings run; `CHROMA_MODE` selects where vectors are stored.
No third selector named `hybrid` exists. All four combinations are valid:

| Mode | Embeddings | Vector store | Use |
| --- | --- | --- | --- |
| Full local | llama.cpp | local Chroma | Private/offline; strong local hardware |
| Cloud compute, local store | OpenRouter/Fireworks | local Chroma | Fast embeddings, local single-machine index |
| Full cloud | OpenRouter/Fireworks | Chroma Cloud | Shared indexes, parallel read cells, no SQLite lock |
| Local compute, cloud store | llama.cpp | Chroma Cloud | Local model with a shared remote index |

OpenRouter is the existing cloud-compute provider. Fireworks is a compatible
future option that needs a separate provider registration — it is not a
vector store.

Cloud mode validates credentials at `Settings` construction:
`CHROMA_MODE=cloud` without `CHROMA_CLOUD_API_KEY` fails startup. The
connection is checked with a heartbeat during runtime setup, so
authentication, network, and tenant/database mistakes surface before any
work begins. A cloud-mode failure is actionable and never silently falls
back to a local index. Select `CHROMA_MODE=local` deliberately if degraded
operation is acceptable.

`CHROMA_CLOUD_TENANT` and `CHROMA_CLOUD_DATABASE` are optional. Supply both
or neither; omitting both lets the cloud client resolve them from the API
key. The key stays in `.env` only — never in `defaults.yaml`, logs, or
results.

Collection metadata records the embedding provider, model, and index
identity. Changing the embedding provider or model, the corpus or parser,
the chunking configuration, or the vector dimension requires re-ingestion
into a fresh collection. Same-dimension model swaps are rejected rather than
silently mixing incompatible vector spaces.

#### Embedding model per profile

The `EMBED_*` settings choose the server default embedding model. A user
profile can choose another provider and model. Open the profile in Studio,
select its Embed step and use "Check model", then "Save model". The choice
belongs to the profile, so ingest, search, answer and graph runs on every
collection that follows the profile use the same model. A graph cannot set the
model. A built-in profile (`documents`, `codebase`) always uses the server
default. To use another model with a built-in profile, duplicate the profile
first.

A collection keeps vectors from one model only. The model of a profile is
locked while a collection that follows the profile holds rows or a model
stamp. A stamped collection stays locked after all its rows are deleted,
because the store keeps its vector size. A collection with rows but no stamp
is locked too, and the message says that the model is not recorded. To use
another model, create a new collection, bind it to the profile and ingest
again. You can always set the model back to the stamped model.

A collection cannot follow a profile whose model differs from the model that
made the collection's vectors. The refusal names both models.

A profile with no choice follows the server default. If you change `EMBED_*`
in `.env`, collections that follow the server default and hold vectors from
the old model fail with a mismatch message. To avoid this, choose an explicit
model in a user profile. Connection settings (URLs and keys) stay in `.env`
for every model.

Run the opt-in smoke check before using cloud storage:

```bash
uv run python scripts/chroma_cloud_smoke.py
```

The script ingests and queries a disposable collection, then deletes it. It
never runs in CI.

### LanceDB backend

LanceDB is the embedded, local-first base-install default. Each RAG collection
maps to one LanceDB table under `LANCEDB_URI`. Tables are created lazily on
first write, which locks the vector dimension. The store keeps collection
metadata, including profile tags and embedding identity, in durable schema
metadata.

LanceDB Cloud is out of scope. Unknown `VECTOR_STORE` values fail startup with
the registered names listed. The BM25 hybrid path is backend-agnostic: it reads
rows through `iter_documents` and invalidates off the store's durable data
version where one exists, else the process-local generation counter
([ADR-056](../adr/056-lineage-navigation-replaces-a-document-store.md)).
Native LanceDB full-text search is implemented as the `native` sparse backend
(see [Reranker](reranker.md#sparse-retrieval-backends-hybrid-search)).

### Legacy Chroma data and rollback

When the default would select LanceDB and recognised data exists in
`CHROMA_PERSIST_DIR`, startup stops. Choose one path: install the Chroma extra
and explicitly set `VECTOR_STORE=chroma` to keep the data, or explicitly set
`VECTOR_STORE=lancedb` and re-ingest source files. The server never migrates,
deletes, moves, or rewrites the Chroma directory.

Switching stores requires re-ingestion. Before reverting after LanceDB
ingestion, set and verify `VECTOR_STORE=lancedb`. Keep the pin while reverting
so an older release cannot select Chroma and make LanceDB data appear missing.

### Providers

Two Chat providers serve answering only. They are not valid for `EMBED_PROVIDER`, `LOCAL_BACKEND` or `CLOUD_BACKEND`. Set them with `ANSWER__PROVIDER=openai_compatible` or `ANSWER__PROVIDER=anthropic`, or choose them in Settings > Chat.

| Variable | Default | What it does |
|---|---|---|
| `OPENAI_COMPATIBLE_BASE_URL` | `https://api.openai.com/v1` | Address of any server that speaks the OpenAI chat API (OpenAI, Together, vLLM, LM Studio). It can be on this machine or remote |
| `OPENAI_COMPATIBLE_API_KEY` | unset | Optional. LM Studio and vLLM need none. The key goes only to the address above |
| `ANTHROPIC_API_KEY` | unset | Required for the `anthropic` provider. Address fixed at `https://api.anthropic.com`. Needs `uv sync --extra anthropic` |

| Variable | Default | What it does |
|---|---|---|
| `EMBED_PROVIDER` | `local` | `local`, `cloud`, `ollama`, `llamacpp`, or `openrouter` |
| `METADATA_LLM_PROVIDER` | `local` | `local` or `cloud`, independent of the above |
| `LOCAL_BACKEND` | `llamacpp` | `llamacpp` or `ollama` |
| `CLOUD_BACKEND` | `openrouter` | `openrouter` |
| `EMBED_MODEL` | — | Model name for embeddings |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_CONTEXT_WINDOW` | `16384` | Ollama context window in tokens, 2,048 to 262,144. See [Context windows](#context-windows) |
| `LLAMACPP_SERVER_BINARY` | blank | Absolute path of `llama-server`. Blank means the pinned build that `omrs llamacpp install` places. See [Local llama.cpp router](#local-llamacpp-router) |
| `LLAMACPP_ROUTER_SERVER` | `managed` | Who runs the llama.cpp router: `managed` (the `llama-server` that OMRS starts) or `external` (the Llama app or another server you run) |
| `LLAMACPP_ROUTER_URL` | `http://127.0.0.1:8080/v1` | Address of the llama.cpp router. A loopback `http` address when `managed` |
| `LLAMACPP_ROUTER_MODELS_MAX` | `4` | Models loaded at once, 1 to 16 |
| `LLAMACPP_ROUTER_MEMORY_MARGIN_MIB` | `8192` | Free memory margin in MiB, 0 to 262,144 |

An unrecognised value for any of the four provider selections above
(`EMBED_PROVIDER`, `METADATA_LLM_PROVIDER`, `LOCAL_BACKEND`,
`CLOUD_BACKEND`), plus `DOCUMENT_BACKEND`, fails startup with a clear
error naming the value and the accepted set.
`RETRIEVAL__HYBRID_SPARSE_BACKEND` fails startup the same way, but its
accepted names are registry-owned and validated at the composition
boundary (`capabilities.validate_sparse_backend`): an unknown concrete
name is rejected, listing `auto` plus the registered sparse backends.
Leading and trailing whitespace is stripped before validation, so
`EMBED_PROVIDER=" local "` resolves to `local`.
An empty or whitespace-only value (`SETTING=` in `.env`) is treated
as unset and resets to the default.

Optional dependencies:

```bash
uv sync --extra anthropic    # Anthropic Chat provider (about 40 MB of SDKs)
```

The LlamaIndex OpenAI-like packages are in the base install. The llama.cpp, OpenRouter and OpenAI-compatible providers need no extra. `uv sync --extra llamacpp` and `uv sync --extra openrouter` still work and install nothing more.

Connection details for each: [Providers](providers.md).

#### llama.cpp roles

One llama.cpp router serves embeddings, classification (metadata extraction), Chat, the claim-check judge and decision models ([ADR-115](../adr/115-one-llamacpp-router.md)). Every request goes to `llamacpp_router_url` and names its model. A setting gives a model its role.

| `omrs.jsonc` key | Env | Role | Default |
|---|---|---|---|
| `llamacpp_embed_model` | `LLAMACPP_EMBED_MODEL` | Embeddings | `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` |
| `llamacpp_chat_model` | `LLAMACPP_CHAT_MODEL` | Classification | `Qwen/Qwen3-4B-GGUF:Q8_0` |
| `answer.model`, with `answer.provider` set to `llamacpp` | `ANSWER__MODEL` | Chat | `""` (no Chat model chosen) |
| `answer.verify_model`, with the judge provider set to `llamacpp` | `ANSWER__VERIFY_MODEL` | Claim-check judge | `""` |
| `model` of a managed `llamacpp` decision entry | n/a | Decision | none |

Each value names an entry of `llamacpp_models` by its `model` value. The roles are not stored. The Router panel shows them for each entry.

Rules:

- Sources, highest first (ADR-087): process environment and `.env` (both lock the field), `omrs.jsonc` (does not lock), default.
- With the router in `managed` mode, a request for a model that is not in the list fails before any contact, with reason `model-not-listed`. With `external` mode, OMRS does not check the name.
- Chat on llama.cpp never uses `llamacpp_chat_model`. Classification never uses `answer.model`. An empty `answer.model` gives the setup message "Choose a Chat model in Settings > Chat." and OMRS sends nothing. An empty `answer.verify_model` skips the claim check with "Choose judge model in Settings > Chat."
- An entry with `embeddings = true` cannot hold the Chat, classification or judge role. A save that names one gets reason `role-mismatch`.
- When Chat and classification name the same entry, they share its slots, its context size and its reload. Settings > Chat and the Router panel show a warning. The warning does not block Save. It suggests another router model, your own llama.cpp server through the OpenAI-compatible provider, or a hosted provider such as OpenRouter.

#### Change provider values in the web workspace

In `omrs web`, Settings > Providers saves these values in `omrs.jsonc`: `OLLAMA_BASE_URL`, `OLLAMA_CONTEXT_WINDOW`, `LLAMACPP_ROUTER_SERVER`, `LLAMACPP_ROUTER_URL`, `LLAMACPP_ROUTER_MODELS_MAX`, `LLAMACPP_ROUTER_MEMORY_MARGIN_MIB`, `LLAMACPP_SERVER_BINARY`, `OPENROUTER_API_KEY`, `OPENAI_COMPATIBLE_BASE_URL`, `OPENAI_COMPATIBLE_API_KEY` and `ANTHROPIC_API_KEY`. The server uses the first source it finds, highest first:

| Rank | Source | Shown as | Locks the field |
|---|---|---|---|
| 1 | Process environment | `env` | yes |
| 2 | `.env` | `dotenv` | yes |
| 3 | `omrs.jsonc` in the [user config folder](#user-config-folder). A key field holds a reference: `env://` shows `config-file`, `file://` shows `key-file`, `keychain://` shows `keychain`. | `config-file`, `key-file`, `keychain` | no |
| 4 | A key file `secrets/<provider>.key` (keys only) | `key-file` | no |
| 5 | YAML defaults and the profile bundle | `yaml` | no |
| 6 | The code default | `default` | no |

A locked field shows the variable name and where it is set. Remove the variable from the environment or `.env` to edit the field here. A value in `omrs.jsonc`, a key file or a key reference does not lock. A save on the page replaces it.

The page writes `omrs.jsonc`. It changes only the key you save. Comments, key order and the other keys stay. A key saved on the page goes in the system keychain (service `omrs`, user name equal to the provider name), and the file gets `keychain://<provider>`. The app never writes a key to `.env`, to the workspace database or to a file. If no keychain exists, set the key variable (for example `OPENROUTER_API_KEY`) in the environment, or use a key file.

A saved or hand-edited value applies at once to new requests, with no restart. The Ollama address stays locked while embeddings use Ollama. Embedding providers and models are not editable on the page. The stdio MCP server and the CLI read `omrs.jsonc` when they start, so they see a page save at their next launch. See [Web workspace](web-workspace.md#provider-settings).

#### User config folder

The user config folder holds `omrs.jsonc`. You can edit the file by hand. The Settings page also writes it. The CLI, the stdio MCP server and `omrs web` all read it. This mirrors the OMMS layout (`~/.config/omms/omms.jsonc`).

The folder is the first of these:

1. `$OMRS_CONFIG_DIR`.
2. `$XDG_CONFIG_HOME/omrs`.
3. `~/.config/omrs`.

A missing folder or file gives no values and no warning. The folder can hold two things:

- `omrs.jsonc`: JSON with comments and trailing commas. It accepts every setting that the environment accepts.
- `secrets/<provider>.key`: one key for each provider. The file name is the provider name (`openrouter`, `openai_compatible`, `anthropic`). The page never writes it.

##### Key names

A file key is the environment name in lower case. A double underscore (`__`) nests one level. One rule covers every setting, so there is no mapping table:

```text
RETRIEVAL__TOP_K     →  { "retrieval": { "top_k": 7 } }
CHUNKING__CHUNK_SIZE →  { "chunking": { "chunk_size": 512 } }
EMBED_PROVIDER       →  { "embed_provider": "local" }
ANSWER__MODEL        →  { "answer": { "model": "qwen3:8b" } }
```

Three keys exist only in the file: `web_port`, `web_max_upload_mib` and `mcp_http_enabled`. `web_max_upload_mib` also has a launch twin, `WEB_MAX_UPLOAD_MIB`, which locks it.

Example `omrs.jsonc` (fake values):


```jsonc
{
  // Non-secret values
  "ollama_base_url": "http://gpu-box.local:11434",
  "openai_compatible_base_url": "https://api.together.xyz/v1",
  "answer": { "provider": "openrouter", "model": "openai/gpt-4o-mini" },
  "retrieval": { "top_k": 7 },
  "web_port": 9100,

  // Key fields hold references only
  "openrouter_api_key": "keychain://openrouter",
  "anthropic_api_key": "env://MY_ANTHROPIC_KEY",
}
```


A key field takes one of three references:

- `env://NAME`: the value of the environment variable `NAME`.
- `file://<path>`: a file inside `secrets/`. A leading `~` is the home folder.
- `keychain://<provider>`: the system keychain entry `omrs` / `<provider>`. Every process resolves it: the web server, the CLI and the stdio MCP server. The first read can make macOS ask you to allow access. Use `env://` or `file://` to avoid the prompt.

Example layout and permissions:


```text
~/.config/omrs/
  omrs.jsonc
  secrets/
    openrouter.key      one line: the key
    anthropic.key
```

```bash
chmod 700 ~/.config/omrs/secrets
chmod 600 ~/.config/omrs/secrets/*.key
```

Rules the server applies:
- A literal key in `omrs.jsonc` is ignored. The log names the field and never shows the value.
- A `file://` path must resolve inside `secrets/`. Any other path is refused.
- A key file holds at most 4 KiB. The server strips surrounding whitespace.
- The server refuses a symlink that leaves the folder, and a file that is not a regular file.
- A key file looser than 0600, or a `secrets/` folder looser than 0700, is still read. The log shows one warning with the path and mode, never the content. Windows skips the check.
- A new `omrs.jsonc` gets mode 0600 and a new folder gets mode 0700. A page save keeps the mode of an existing file.
- A page save goes to a temporary file that replaces the original, so a stop during a save never leaves half a file.
- The server notices a hand edit before the next request that reads settings. A save from the page that was open before your edit is refused (409), and your edit stays. Reload the page to see it.

##### What the Settings page writes

Settings > Configuration lists every setting. Each row shows the value in force and its source. A row with Edit opens a control for its kind: an on/off switch, a number field with its range, a choice list or a text field. Save sends `PUT /v1/settings/configuration`. The server checks every change, then writes all of them in one save or none.

The page can write every setting that holds one plain value: a boolean, a number, a text or a fixed choice. This includes the retrieval, reranker, hybrid, chunking, ingestion, metadata, answer, OCR and server settings, and the three file-only keys. The list comes from the `Settings` model, so a new plain setting is editable with no list change.

The server checks each value against the rule of its setting before the write: the type, the lower and upper bound, and the accepted choices. A value that breaks its rule gets 400 with the rule. The file does not change.

These keys stay read-only. The row shows the reason and no Edit:

| Keys | Reason on the row |
|---|---|
| `embed_provider`, `embed_model`, `local_backend`, `cloud_backend`, `llamacpp_embed_model`, `openrouter_embed_model`, every `embedding.*` key | The embedding model is part of every collection. Change it in omrs.jsonc and re-ingest. |
| `vector_store`, `lancedb_uri`, `chroma_persist_dir`, `chroma_mode`, `collection_name` | Existing collections stay where they are. Change it in omrs.jsonc and restart. |
| Every key field (`*_api_key`, `*_key`) | Keys are set on the provider cards as references. |
| `ingestion.ingest_extensions`, `metadata.keyword_rules` | Edit this in omrs.jsonc. |
| `ocr_runtime_url` | Set this in the environment, .env or omrs.jsonc. |

More rules:

- A key that the environment or `.env` sets is read-only. The row names the variable, for example "Remove RETRIEVAL__TOP_K from the environment or .env to edit it here." A save of that key gets 409.
- An optional setting saved in the file has Clear. Clear sends `null`, which removes the key from the file. The default then applies.
- A chunking key is part of the index identity. After a restart, the next ingest can read existing files again.
- A restart-only key shows "Restart to apply" after a save. The row keeps the launch value until the restart.
- The Providers cards still write key references (`keychain://`, `env://`, `file://`). The Configuration save refuses key fields.
- A save of `llamacpp_router_server` or `llamacpp_server_binary` needs the `credentials` scope (403 otherwise). A program path must be an executable file named `llama-server` (400 otherwise). A retired llama.cpp key, such as `llamacpp_embed_server`, is refused.

##### Problems in the file

A problem never stops the server. The server starts and lists each problem by key, never by value. `omrs config show` and `GET /v1/settings/configuration` show the list.

| Kind | When | What the server does |
|---|---|---|
| `broken` | The file is not valid JSON with comments. | Reads no value from the file. Logs one warning. A page save is refused (409) until you fix the file. |
| `invalid` | A value breaks its rule: the wrong type, out of range, a name that is not accepted, an address that is not `http` or `https`, or a literal key. | Ignores that value. The next source applies. The other values stay. |
| `unknown` | A key names no setting (a typo such as `retreival`). | Ignores the key. |
| `retired` | A key is an old flat name such as `top_k`. | Ignores the key. The message names the new key, here `retrieval.top_k`. |

An ignored value falls back to the next source. A typo in `embed_provider` therefore falls back to the default embedder. A collection that holds vectors from another model refuses to search until you restore the old model (ADR-051).

##### Settings that need a restart

`omrs web` applies these hand edits at once: provider addresses and keys, the Chat provider and model, the claim check judge provider and model (`answer.verify_provider`, `answer.verify_model`), reasoning levels (`answer.reasoning`, `answer.verify_reasoning`), context windows, llama.cpp server values, `web_max_upload_mib` and `mcp_http_enabled`. `web_port` and the engine settings (embedding, vector store, chunking, ingestion, retrieval, metadata, OCR and the other `answer` keys) apply at the next launch. `omrs web` keeps the values it started with and marks each changed key "Restart to apply".

**Limit.** These files are plaintext. File permissions do not stop another process of the same user, and an AI coding agent runs as that user. A `file://` or `env://` reference gives no security gain over `.env`. Use them on headless machines and in containers with a mounted folder. On a desktop, save keys in the keychain.

### Context windows

Ollama chat calls need an explicit context window. Without one, LlamaIndex read the model maximum (262,144 tokens for `qwen3:4b`) and sent it as `num_ctx`. Ollama then reserved about 43 GB, ran out of GPU memory and returned empty replies (TDR-036).

- `OLLAMA_CONTEXT_WINDOW` (or `ollama_context_window` in `omrs.jsonc`) sets the window. The default is 16,384 tokens. The range is 2,048 to 262,144.
- The first source wins, highest first: environment and `.env` (both lock), `omrs.jsonc`, the default. A page save writes `omrs.jsonc`.
- The Chat answer model and metadata extraction use it. A saved or hand-edited value applies to the next call. Ollama reloads the model at the new size.
- Embedding models are not covered. A different window can change how text is cut, and so the vectors.
- A llama.cpp model takes its context window from `ctx-size` in its entry of `llamacpp_models` (512 to 262,144). See [Local llama.cpp router](#local-llamacpp-router).

### Local llama.cpp router

OMRS can start, stop and adopt its own `llama-server` in router mode. One router serves every local llama.cpp model except OCR. One runtime manager serves every OMRS process: `omrs web`, the CLI, the stdio MCP server and the watcher. The router has two modes.

- `managed`: OMRS starts the router, or adopts one already running, with a fixed argument list. This is the default.
- `external`: OMRS starts, adopts and stops nothing. You run the server and give its address, for example the Llama app on `http://127.0.0.1:9931/v1`. OMRS does not check model files or presets on an external server.

| Setting | Env | `omrs.jsonc` key | Default | Range |
|---|---|---|---|---|
| Who runs the router | `LLAMACPP_ROUTER_SERVER` | `llamacpp_router_server` | `managed` | `managed` or `external` |
| Router address | `LLAMACPP_ROUTER_URL` | `llamacpp_router_url` | `http://127.0.0.1:8080/v1` | Loopback `http` address when `managed`. Any `http` or `https` address when `external` |
| Models loaded at once | `LLAMACPP_ROUTER_MODELS_MAX` | `llamacpp_router_models_max` | `4` | 1 to 16 |
| Free memory margin (MiB) | `LLAMACPP_ROUTER_MEMORY_MARGIN_MIB` | `llamacpp_router_memory_margin_mib` | `8192` | 0 to 262,144 |
| Program path | `LLAMACPP_SERVER_BINARY` | `llamacpp_server_binary` | blank | Absolute path of a file named `llama-server` |
| Model list | none | `llamacpp_models` | The shipped list below | File only |
| OCR | `OCR_RUNTIME_URL` | `ocr_runtime_url` | blank, which means managed | A free loopback port that OMRS picks |

A blank program path means the pinned llama.cpp build (b11941) that `omrs llamacpp install` places in the OMRS data folder. A path you set keeps the program rule and must be build b11941 or newer, else the router fails with `wrong-build`.

The model limit becomes `--models-max`. The memory margin becomes `--models-memory-margin`. The router unloads the least recently used model when a new one needs the room. A change to the model limit, the margin, the address or the program needs a router restart. The Router panel shows "Restart to apply".

With `external`, Start, Stop and Restart return 409 with reason `external-server`. Use the llama.cpp card in Settings > Providers, or set values in the environment or in `omrs.jsonc`.

#### The model list

`llamacpp_models` is a named map in `omrs.jsonc`. No environment variable sets it. Only `omrs web` writes it. A map you save replaces the shipped list as a whole. The first edit in the Router panel writes the shipped list plus your edit.

| Field | Rule |
|---|---|
| Key | 1 to 40 characters from `a-z`, `0-9` and `-` |
| `model` | A Hugging Face id with a quantisation tag, such as `org/name:Q8_0`. It is unique in the map and does not start with `-` |
| `file` | Managed only. An absolute path of an existing `.gguf` file. Its name does not hold `mmproj` |
| `projector` | Optional. An absolute path of a `.gguf` file, for an image model |
| `sha256`, `projector_sha256` | The SHA-256 that the page records when you add the entry |
| `preset` | An object of the allowed keys below |

The shipped list holds two entries with no file. The Router panel shows "Not downloaded" for an entry with no file. In `omrs web`, OMRS downloads the file with the Get a model job when the router first needs it. `omrs llamacpp install` also downloads it.

| Id | `model` | Preset | Role |
|---|---|---|---|
| `qwen3-embedding-4b` | `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` | `embeddings = true`, `pooling = last`, `embd-normalize = 2`, `ctx-size = 8192`, `batch-size = 8192`, `ubatch-size = 8192`, `parallel = 1`, `kv-unified = false` | Embeddings |
| `qwen3-4b` | `Qwen/Qwen3-4B-GGUF:Q8_0` | `ctx-size = 32768`, `parallel = 2` | Classification |

An entry for embeddings must set `embeddings`, `pooling`, `ctx-size`, `batch-size` and `ubatch-size`. `ubatch-size` must not be larger than `batch-size`. A save that breaks this gets reason `preset-invalid`. `ctx-size = 32768` with two slots gives 16,384 tokens for each slot.

Example entry in `omrs.jsonc`:

```jsonc
{
  "llamacpp_models": {
    "chat-8b": {
      "model": "Qwen/Qwen3-8B-GGUF:Q8_0",
      "file": "/models/Qwen3-8B-Q8_0.gguf",
      "sha256": "<64 hex characters>",
      "preset": { "ctx-size": 16384, "parallel": 1 },
    },
  },
  "answer": { "provider": "llamacpp", "model": "Qwen/Qwen3-8B-GGUF:Q8_0" },
}
```

#### Preset keys

OMRS writes `models.ini` from the `preset` object of each entry. It writes only these keys. Any other key gets 400 with reason `preset-key-unknown`. That includes `host`, `port`, `api-key`, `sleep-idle-seconds`, `hf-repo`, `connect` and `connect-code`.

| Key | Accepted value |
|---|---|
| `ctx-size` | Whole number, 512 to 262,144 |
| `batch-size`, `ubatch-size` | Whole number, 32 to 65,536 |
| `parallel` | Whole number, 1 to 16 |
| `embeddings` | `true` only. To turn it off, leave the key out |
| `pooling` | `none`, `mean`, `cls`, `last` or `rank` |
| `embd-normalize` | -1, 0, 1 or 2 |
| `kv-unified` | `true` or `false` |
| `flash-attn` | `on`, `off` or `auto` |
| `n-gpu-layers` | Whole number, 0 to 999, or `all` or `auto` |
| `fit` | `on` or `off` |
| `cache-type-k`, `cache-type-v` | `f32`, `f16`, `bf16`, `q8_0` or `q4_0` |
| `cache-prompt` | `true` or `false` |
| `cache-reuse` | Whole number, 0 to 65,536 |
| `image-min-tokens`, `image-max-tokens` | Whole number, 1 to 65,536 |

A boolean must be a JSON `true` or `false`. A string or a number gets 400. llama.cpp accepts any word for a boolean in `models.ini` without an error, so this check is the only one.

A preset edit reloads only the changed model. The other loaded models keep running. If another OMRS process uses the changed model, the change fails for that model with `version-busy`, and the Router panel shows "Reload pending".

#### Launch checks

1. The program is an absolute path of an executable regular file named exactly `llama-server`, both as given and after links resolve. OMRS checks it at save and before every launch.
2. Each model name follows the Hugging Face id rule with a tag. Each file is an absolute, readable `.gguf` path.
3. When a file has a recorded `sha256`, OMRS compares it before each router start and before each preset rewrite. A changed file leaves its entry out of `models.ini` with reason `file-changed`. Other entries keep working. An entry with no recorded value runs with the note "File not checked". A decision entry with no recorded value is refused.
4. In `managed` mode the address is an `http` address on a loopback host. The router binds `127.0.0.1`.
5. The arguments are fixed: `--models-preset`, `--models-max`, `--models-memory-margin`, `--host 127.0.0.1` and `--port`. No shell runs. You cannot add an argument. OMRS never passes `--sleep-idle-seconds`.
6. The router gets a minimal environment (`PATH`, `HOME`, `LANG`, `TMPDIR`) and no API key. It also gets `LLAMA_CACHE` and `XDG_CONFIG_HOME`, both set to empty folders in the router state folder. The router then lists no model from a Hugging Face cache and reads no `config.ini` of your user. The router also reads `/etc/llama.cpp/config.ini`. OMRS cannot redirect that file and does not check it.
7. OMRS starts and stops only the servers it records. It never touches a server you started. It never finds or stops a process by name or port.
8. The router output goes to `server.log` in the router folder (see [Runtime state folder](#runtime-state-folder)). OMRS empties the file at each start and again past 5 MiB. The page and the routes never show it.

The router state is `stopped`, `starting`, `running` or `failed`. A failed router has one reason: `binary-invalid`, `model-invalid`, `not-loopback`, `port-in-use`, `exited`, `timeout`, `not-configured`, `not-provisioned`, `not-supported`, `version-busy`, `wrong-build`, `file-changed`, `bind-failed` or `not-downloaded`. `not-provisioned` means no program path is set and no pinned build is placed. The line names `omrs llamacpp install` and Get llama.cpp. `not-downloaded` means no listed model has a file. The line reads "Models are still downloading." while a download runs, else "No model is downloaded yet." `not-configured` means the list holds no usable entry. `not-supported` means managed mode does not run on this platform (Windows). `bind-failed` means the router could not open a port after 4 tries. `version-busy` means another OMRS process uses the router with other arguments. `timeout` means `GET /health` did not answer 200 in 180 seconds. No model loads at start.

Each model has its own state: `not-downloaded`, `unloaded`, `loading`, `loaded` or `failed`. A failed model has one reason: `model-invalid`, `file-changed`, `preset-invalid`, `model-load-failed`, `model-not-listed`, `role-mismatch` or `version-busy`. A failed model does not stop the other models. Before its first request, OMRS asks the router to load the model and waits up to 300 seconds. The request timeout starts after the model is loaded.

A model with `parallel = 1` handles one request at a time across all OMRS processes. A request to another model does not wait for it.

#### Pinned build

OMRS can download llama.cpp build b11941 for macOS arm64, Linux x86-64 (CPU) and Linux x86-64 (CUDA 12.8). It checks the SHA-256 of each archive and places `llama-server` in `$XDG_DATA_HOME/omrs/llamacpp/b11941-<flavour>/`, else `~/.local/share/omrs/llamacpp/b11941-<flavour>/`. Other platforms get reason `not-supported`; set `llamacpp_server_binary` to your own build there.

Run the command once on each machine:

```bash
omrs llamacpp install                  # the flavour this machine needs
omrs llamacpp install --flavour cpu    # Linux x86-64: force the CPU build
```

On Linux the default flavour is CUDA when `/proc/driver/nvidia/version` exists, else CPU. Apple silicon has one build and refuses `--flavour`. The command runs `llama-server --version` on the placed file and, for CUDA, `--list-devices`. A failed check gives reason `binary-check-failed` or `cuda-device-missing`, and no binary stays in place. A build that is already placed and passes its checks is kept with no download. The command starts no server and asks no question, so a headless machine can run it. It records the flavour in `installed.json` in the data folder, and a blank `llamacpp_server_binary` resolves to that build. When `llamacpp_router_server` is `managed`, the command then downloads each model of the list that has no file, into the Hugging Face cache. See [CLI reference](cli-reference.md#llamacpp-install).

#### Runtime state folder

Every runtime keeps its state in `<state folder>/runtimes/<runtime id>/`. The runtime id is `router` or `ocr-<engine folder>`. The router folder also holds `models.ini`, `hashes.json`, the empty folders `empty-cache` and `empty-config`, and one `models/<model id>/` folder for each listed model with its own lock files. The state folder is the first of these that exists:

1. `$OMRS_STATE_DIR`.
2. `$XDG_STATE_HOME/omrs`.
3. `~/.local/state/omrs`.

The folder holds lock files, a record of the running server (`server.json`) and `server.log`. It holds no settings and no secrets. Every OMRS process writes to it. The CLI and the watcher cannot see the `--workspace` flag of `omrs web`, so only the environment sets this folder.

Put the state folder on a local disk. The locks use `flock`, which is not reliable on NFS or SMB. OMRS does not try to detect a network file system. Tests set `OMRS_STATE_DIR` to a temporary folder, so they never read your real folder.

#### Sharing, idle stop and exit

- Several OMRS processes share one server. A process that needs a runtime joins it. The first process starts the server. Later processes adopt it.
- The last process to leave stops the server. A server stays up while any other OMRS process uses it. So `omrs web` can exit while a CLI ingest still uses the router, and the router keeps running.
- A runtime with no request for 10 minutes stops. This idle stop is a fixed value. No setting changes it. The next request starts the server again.
- A server counts as stale only when its process is gone or runs another command. A slow `/health` answer never makes it stale.
- If a process dies without a clean exit (SIGKILL), the server can stay up with no client. The next OMRS process adopts it. `omrs web` also stops such a server at start-up. The Integrations page shows it as "Running, no OMRS process uses it", with a Stop button.
- Stop on the llama.cpp card, or on a row of the Model runtimes section, stops a managed server. It sends SIGTERM, waits 10 seconds, then sends SIGKILL. An external server has no Stop.
- On Windows, managed mode fails with `not-supported`. External mode works.

#### Retired: idle sleep

`LLAMACPP_IDLE_SLEEP_SECONDS` and `llamacpp_idle_sleep_seconds` no longer exist. OMRS does not pass `--sleep-idle-seconds` to `llama-server`, because that flag has an open race (llama.cpp issue #29689). If the environment or `.env` sets `LLAMACPP_IDLE_SLEEP_SECONDS`, start-up fails with a message that names it and the fixed 10-minute idle stop. Remove the variable. A `llamacpp_idle_sleep_seconds` key in `omrs.jsonc` is ignored and listed in the problem list. A body of `PUT /v1/llamacpp/router` with `idle_sleep` returns 400. The old `/v1/llamacpp/server` routes are gone and return 404.

#### OCR runtimes

An OCR engine can declare the `llama-server` it needs in its `pyproject.toml` (see [OCR engines](../../ocr-workers/README.md#runtime-block)). OMRS then starts or adopts that server, checks the build and the SHA-256 of each declared model file, and gives the address to the worker. This is the default. `ocr_runtime_url` is blank.

To use a server that you run yourself, set `OCR_RUNTIME_URL` (or `ocr_runtime_url`) to its address. OMRS then starts nothing and passes the address to every engine that declares a runtime. The build check still runs. OMRS cannot check model files on an external server. The Integrations page says so: "External server. Model files are not checked." One external address serves one llama.cpp engine at a time, so use it with one engine only.

Limits. The program path is editable in the GUI. The guardrails limit what can run to a file named `llama-server`. Anyone with a browser session and the `credentials` scope can still point the setting at any file with that name. Changing the router mode, the program path, or the `model`, `file` or `projector` of an entry needs the `credentials` scope. Changing preset values, the address, the model limit or the memory margin, and Start, Stop and Restart, need `manage`. A bearer token never passes a route that writes or controls. The CLI, the stdio MCP server and the watcher start and adopt the router as clients. They have no Stop.

### Get a model (search and download)

The llama.cpp and Ollama cards in Settings > Providers can search for a model and download it. These variables and rules apply. See [Web workspace](web-workspace.md).

| Variable | Use |
|---|---|
| `HF_TOKEN` | Needed to download from a gated Hugging Face repo. Set it in the environment of `omrs web` and restart the server. The server never saves, returns or logs it. Without it, a gated repo gives the reason `gated`. |
| `HF_HUB_CACHE` | Folder that receives the llama.cpp files. It wins over `HF_HOME`. |
| `HF_HOME` | Hugging Face home. The files go to `HF_HOME/hub` when `HF_HUB_CACHE` is not set. The default is `~/.cache/huggingface/hub`. |

1. The server contacts `huggingface.co` only when you search, open a file list or start a download. It sends no request at start-up.
2. Before a llama.cpp download the server checks the disk. It needs the size still to download plus 1 GiB spare. If the free space is smaller, the start gives the reason `no-space` and names both sizes. A file already in the cache counts as 0 bytes.
3. A managed router loads the file that the `file` field of the list entry names. Use this model records the path of the cached file there. The router never reads the Hugging Face cache by itself. An external server reads its own folder and does not see the file. Point that server at the folder the panel shows.
4. A download that gets no byte for 60 seconds ends with the reason `stalled`. A cancelled download leaves its partial file in the cache, and a later download of the same file continues from it.
5. An Ollama download is a pull request to the Ollama address in use. Ollama keeps its own files. The space check does not run for it.

### Chunking — `CHUNKING__*`

| Field | Default | What it does |
|---|---|---|
| `chunk_size` | `512` | Target chunk size for most files |
| `chunk_overlap` | `100` | Overlap between chunks. Calibrated ([ADR-018](../adr/018-balanced-retrieval-defaults.md)) — do not change casually |
| `markdown_chunk_size` | `1024` | Larger, because Markdown splits on headings |
| `markdown_heading_prepend` | `false` | Prepend the heading path to each chunk |
| `markdown_min_chunk_fraction` | `0.0` | Drop chunks below this fraction of the target |
| `strategy_fallback` | `markdown` | Strategy for file types we cannot identify. **Profile-owned**. Accepted values: inline `markdown`, or registered `code`, `config`, and `sentence` |

Known file types always use content-type dispatch — a `.py` file gets the code
splitter regardless of the fallback.

### Ingestion — `INGESTION__*`

| Field | Default | What it does |
|---|---|---|
| `embed_concurrency` | `4` | Parallel embedding requests. Machine-specific — lower it if the backend throttles |
| `embed_batch_size` | `100` | Documents per embedding call |
| `ingest_extensions` | the seven document extensions | File extensions ingestion collects. **Profile-owned** — the `codebase` profile adds source extensions. Env form is comma-separated (`.py,.ts`) or a JSON array string |
| `normalise_reader_output` (`INGESTION__NORMALISE_READER_OUTPUT`) | `true` | Remove reader markup (`<u>`, `<span>`, `<font>`, `<center>`, `<div>`, `<img>`, table styling) from PDF text before chunking, keeping every visible character. Part of the index identity: changing it reprocesses every source once. See [Ingestion guide](ingestion.md#reader-output-normalisation) |

### Embedding — `EMBEDDING__*`

**llama.cpp embeddings keep line breaks.** The llama.cpp embedder sends each chunk unchanged. Before this change it replaced every line break with a space, as the LlamaIndex OpenAI helpers do. Ollama always kept line breaks. With the same model file, the two forms give different vectors for a multi-line chunk.

- A collection built with Ollama works with llama.cpp with no rebuild.
- A one-line search question gives the same vector as before, so a search of a collection built by the older llama.cpp embedder gives the same results. Two cases differ: a question with line breaks, and any question when `EMBEDDING__QUERY_INSTRUCTION` is set, because the query then reads `Instruct: ...` and `Query: ...` on two lines. In those cases re-ingest the collection.
- New files added to such a collection use the new form, so the collection then holds both forms. Re-ingest the collection to keep one form.

Unit-norm guard for embedding vectors (see [ADR-053](../adr/053-embedding-norm-guard.md)). Dense
ranking treats L2 distance as cosine similarity; that is only rank-equivalent when vectors are
unit-normalised. The guard enforces the contract: fail-closed at ingest (a bad vector aborts the
file replacement before any write), warn-and-continue at query (results stay available, a
`norm_guard` diagnostic appears with diagnostics enabled).

The two `tokenizer_*` fields carry the Markdown chunking budget identity
([ADR-063](../adr/063-model-token-aware-markdown-chunking.md), promoted to packaged default
after experiment 25 passed all four frozen gates). The tokenizer is resolved from the local
Hugging Face cache only — it is independent of the embedding inference provider, and the
system never infers it from an Ollama, llama.cpp, or OpenRouter alias.

| Field | Default | What it does |
|---|---|---|
| `norm_guard_enabled` | `true` | Verify vector norms at both boundaries. Disabling is logged at startup |
| `norm_tolerance` | `0.001` | Maximum permitted `abs(norm − 1.0)`, inclusive. Must be positive |
| `tokenizer_model` | `Qwen/Qwen3-Embedding-4B` | Hugging Face identity used to budget Markdown chunks in real token units. Both fields empty → legacy character-budgeted path. Uncached revision → warning + the same legacy fallback |
| `tokenizer_revision` | `5cf2132abc99cad020ac570b19d031efec650f2b` | Pinned revision; must be present in the local cache for the model-token path to activate. Changing either field changes the source index identity, so Markdown sources re-chunk on the next ingest |
| `query_instruction` | empty | Instruction prefix applied to **queries only**. Empty preserves the raw query verbatim |

#### `EMBEDDING__QUERY_INSTRUCTION`

Some embedding models accept a task instruction that reshapes the query
vector. When this field is non-empty, the dense retrieval path embeds

```text
Instruct: <EMBEDDING__QUERY_INSTRUCTION>
Query: <the user's query>
```

instead of the raw query. Empty is the packaged default and preserves
today's behaviour exactly.

Four things to know before you set it:

1. **Queries only.** Document and chunk embeddings are never touched.
   You do not need to re-ingest anything to try an instruction, and you
   do not need to re-ingest anything to remove it.
2. **It changes query-vector semantics.** The same question maps to a
   different point in the embedding space, so results move. That is the
   point of the setting, and it is also its risk: an instruction that
   helps prose questions can dilute identifier tokens and hurt exact
   code lookups.
3. **Dense only.** The sparse (BM25) runner and the cross-encoder
   reranker receive the raw query, never the instructed one.
4. **The query-embedding cache keys on the prepared query.** Two
   identical raw queries under different instructions get separate cache
   entries and cannot collide.

Set it per model. A model that was not trained with instructions gains
nothing from one. Measure before you keep it: see the change record for
what the evaluated candidate instruction actually did on this workload.

### Retrieval — `RETRIEVAL__*`

| Field | Default | What it does |
|---|---|---|
| `top_k` | `10` | Results returned. **Profile-owned** |
| `similarity_threshold` | `0.0` | Minimum score to keep a result |
| `rerank_enabled` | `false` | Cross-encoder reranking. **Profile-owned** |
| `rerank_enabled_for_semantic` | `true` | Allow reranking on prose-like queries |
| `hard_technical_threshold` | `0.3` | Above this "technical" score, skip reranking |
| `rerank_fetch_multiplier` | `3` | Fetch `top_k × 3` candidates before reranking |
| `rerank_max_fetch` | `100` | Cap on that candidate pool |
| `rerank_model` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model |
| `rerank_backend` | `onnx` | Reranker inference backend (`onnx` or `torch`). `torch` requires `uv sync --extra torch`. See [ADR-038](../adr/038-pluggable-reranker-backend.md) |
| `hybrid_enabled` | `false` | Combine keyword and embedding search. **Profile-owned** |
| `hybrid_rrf_k` | `60` | Rank-fusion constant ([ADR-017](../adr/017-hybrid-retrieval-rrf.md)) |
| `hybrid_sparse_backend` | `bm25` | Sparse backend for hybrid search: `bm25`, `native`, or `auto`. Registry-owned validation at the composition boundary; unknown names fail startup listing `auto` plus the registered backends. See [Reranker](reranker.md#sparse-retrieval-backends-hybrid-search) |

### Answering — `ANSWER__*`

The grounded answering operation (`omrs answer`, the `answer_documents`
MCP tool, and the HTTP contract). It performs one or more completion calls at
query time. See [MCP tools](mcp-tools.md#answer_documents) and
[ADR-057](../adr/057-answering-is-additive-and-injected.md).

| Field | Default | What it does |
|---|---|---|
| `enabled` | `true` | Master switch. `false` makes the server model resolve to `None`; the answering tools then return an actionable error |
| `provider` | `llamacpp` | LLM provider, resolved through the same registry as metadata extraction. Unknown names fail startup. Besides `llamacpp`, `ollama` and `openrouter`, the registry holds `openai_compatible` and `anthropic` for answering only |
| `model` | `""` | Model name, passed to the provider builder as an `answer_model` override so answering never reuses the small metadata-classification model. Empty means no Chat model is chosen: Chat answers "Choose a Chat model in Settings > Chat." and sends nothing. With `llamacpp`, the name is the `model` of an entry in `llamacpp_models` |
| `timeout` | `120.0` | Seconds to wait for one completion round |
| `max_rounds` | `4` | Maximum COMPACT refinement rounds (1–8; the client-sampling path caps at 4). Later rounds widen the per-round budget up to a hard character ceiling (262,144); overflow evidence is dropped lowest-ranked first |
| `context_window` | `8192` | Per-round context budget in **characters** — a deterministic count, not a token estimate |
| `max_output_tokens` | `2048` | Reserved head-room for the model's reply inside one round's budget |
| `prefer_client_sampling` | `true` | Prefer the MCP client's model over the server model when the client advertises the sampling capability |
| `allow_legacy_sampling` | `true` | Allow the deprecated sampling back-channel only on a negotiated pre-2026-07-28 session. Never on a modern session |
| `verify_claims` | `false` | Opt-in claim-verification judge ([ADR-059](../adr/059-claim-verification-stage.md)). `true` adds one configured-judge call per cited prose sentence (~3.3 s P95 each on the tested GLM-5.3 cloud judge, experiment 20). An unavailable provider degrades to `verification_skipped`; the answer is never blocked |
| `verify_model` | `""` | Judge model. Empty derives it from the provider's default model (e.g. `OPENROUTER_LLM_MODEL`). The default cloud provider has no default model, so claim checks are skipped until you set one. A llama.cpp judge with an empty `verify_model` is not built and the status reason is `no-model`. Settings > Chat can set it; applies at once in `omrs web` |
| `verify_provider` | `cloud` | Judge provider. Aliases: `cloud` (or empty) resolves to the cloud backend, `local` to the local backend; anything else is a literal LLM-registry name. Unknown names fail startup. Settings > Chat can set it; applies at once in `omrs web` |
| `verify_judge` | `chat` | Claim-judge strategy (`ANSWER__VERIFY_JUDGE`): `chat`, `clef_flash` or `granite_guardian` (see "Claim-judge strategies" below). Unknown names fail startup, and the message names the registered strategies. Profile-overlaid like `verify_model`. Settings > Chat ("Judge type") can set it; the environment or `.env` locks it on its own |
| `reasoning` | `""` | Reasoning level for the Chat model, for example `low`, `high` or `none`. Empty sends no reasoning field, so the provider default applies. 1 to 32 letters, digits, `-` and `_`. Settings > Chat can set it; applies at once in `omrs web` |
| `verify_reasoning` | `""` | Reasoning level for the claim check judge. Same rules as `reasoning`, set apart so the judge can think less than the Chat model. Settings > Chat can set it; applies at once in `omrs web` |
| `temperature` | empty | Temperature for the Chat model, 0 to 2 (`ANSWER__TEMPERATURE`). Empty sends nothing, so the request keeps the library default: LlamaIndex sends `0.1` on `llamacpp`, `openrouter` and `openai_compatible`, and Ollama uses the model default. Settings > Chat can set it |
| `seed` | empty | Seed for the Chat model, a whole number from 0 to 2147483647 (`ANSWER__SEED`). Empty sends no seed. Settings > Chat can set it |
| `verify_temperature` | empty | Temperature for the claim check judge (`ANSWER__VERIFY_TEMPERATURE`). Same rules as `temperature`. Chat values never reach the judge |
| `verify_seed` | empty | Seed for the claim check judge (`ANSWER__VERIFY_SEED`). Same rules as `seed` |
| `allowed_hosts` | `""` | OpenRouter hosts the Chat model may use, separated by commas (`ANSWER__ALLOWED_HOSTS`), for example `fireworks` or `deepinfra/fp8`. Blank entries are dropped; at most 16. Only OpenRouter reads it. See "Temperature, seed and allowed hosts" below |
| `verify_allowed_hosts` | `""` | OpenRouter hosts the claim check judge may use (`ANSWER__VERIFY_ALLOWED_HOSTS`). Same rules as `allowed_hosts` |

The `verify_claims`, `verify_model`, `verify_provider` and `verify_judge`
fields are the one answer-block group a profile bundle may override per
collection — a `documents` collection can opt
into the configured judge while a `codebase` collection stays
speed-first. The default judge provider is the cloud backend (the only
tested path); a local judge can be selected but is unmeasured.

In `omrs web`, Settings > Chat can save `provider` and `model` for Chat and for MCP clients of that server that cannot supply their own model. `ANSWER__PROVIDER` or `ANSWER__MODEL` in the environment or `.env` wins and locks the choice. A saved choice goes in `omrs.jsonc` as `answer.provider` and `answer.model`, and applies at once, with no restart. Metadata extraction keeps its own model. The judge has its own choice. The stdio MCP server and the CLI read the choice from `omrs.jsonc` when they start.

Settings > Chat also has a "Claim check judge" block. It saves `verify_provider` and `verify_model` together in `omrs.jsonc` as `answer.verify_provider` and `answer.verify_model`. Both apply at once in `omrs web`, with no restart. A hand edit of either key also applies at once. `ANSWER__VERIFY_PROVIDER` or `ANSWER__VERIFY_MODEL` in the environment or `.env` wins and locks the block. The page saves a registry name only, never the alias `cloud` or `local`. It refuses an empty model. The block sets the judge only. `verify_claims` stays a profile lever ("Check claims" in Studio), so the judge runs only for collections whose profile turns it on. A profile that sets its own judge overrides the saved choice. A cloud judge sends each claim and its cited passages off this machine.

### Claim-judge strategies

`answer.verify_judge` picks how OMRS checks each cited claim (design D10 of `pre-exp35-harness-and-answer-fixes`). Each strategy is one file in `core/answer/judges/` and one line in its registry.

| Strategy | What it sends | Prompt-format version |
|---|---|---|
| `chat` (default) | The chat judge prompt to the judge LLM (`answer.verify_provider`, `answer.verify_model`). It reads a one-word reply; the last word wins. This is the judge of earlier releases. | `chat-oneword/1` |
| `clef_flash` | One yes/no (`noul`) question per claim to `/v1/systemone` on the llama.cpp router. The claim and its evidence go in the state. P(yes) of 0.5 or more is `supported`. | `clef-flash-claim/1` |
| `granite_guardian` | The Granite Guardian 3.3 groundedness prompt to the router's `/v1/completions`, with thinking off. The guardian answers `yes` when the claim is not grounded, so `yes` is `unsupported`. | `granite-guardian-3.3-groundedness/1` |

Measured accuracy (2026-11-10, full LLM-AggreFact test split, 29,320 rows, balanced accuracy, leaderboard rule; ADR-119):

| Strategy and model | Average | RAGTruth | Rows per second |
|---|---:|---:|---:|
| `chat` with GLM-5.3 (Z.AI, reasoning `low`) | 76.9 | 85.1 | about 2.8 (hosted) |
| `granite_guardian` with Granite Guardian 3.3 8B Q8_0 | 75.7 | 83.2 | 2.3 (RTX 4090) |
| `clef_flash` with Clef-Flash 9B Q8_0 | 67.8 | 71.9 | 7.5 (RTX 4090) |

`clef_flash` (`clef-flash-claim/1`) scores far below the model's published 76.6 and 83.2. Use `chat` when accuracy matters. `granite_guardian` scores well on the benchmark but rejected most claims on code and financial-table answers in Experiment 35 smoke runs (94% and 69%, against 26% and 22% for `chat`), so check it on your own documents first. Experiment 35 uses GLM-5.3 as its main checker.

For `clef_flash` and `granite_guardian`, set `answer.verify_provider` to `llamacpp` and `answer.verify_model` to the `model` of a `llamacpp_models` entry. Use the Q8_0 file: a model file below 8-bit is refused before any request (root gotcha 16). A judge that cannot start reports `verification_skipped` with a fixed reason, and the answer is still returned. An unreadable reply counts as `unparseable`, never as a pass.

A profile can pick its own judge in Studio: the Verify claims step has a "Claim judge" choice beside "Check claims". The choices come from the registry. A strategy whose model is not set up on this host shows as not ready, and a save that picks it is refused with a message that names the missing setting.

Each answer that ran the claim check carries `judge_calls`: one record per claim with the strategy, the model id, the host (hosted) or the SHA-256 of the GGUF file (local, read from the router's `hashes.json`), the prompt-format version, the call settings and P(yes). The record holds no claim text and no evidence text. See [MCP tools](mcp-tools.md).

Each provider sends the reasoning level in its own request field:

| Provider | Request field |
|---|---|
| `openrouter` | `reasoning: {"effort": <level>}` |
| `openai_compatible` | `reasoning_effort: <level>` |
| `ollama` | `think`: `low`, `medium` and `high` go as text, `none` sends `false`, any other level sends `true` |
| `llamacpp`, `anthropic` | Nothing. The level is saved, and Settings > Chat says the provider ignores it |

`ANSWER__REASONING` in the environment or `.env` wins and locks `answer.reasoning`. `ANSWER__VERIFY_REASONING` locks `answer.verify_reasoning`. Each level locks on its own; it does not lock the provider or model. A level is a server setting. A profile cannot change it.

#### Temperature, seed and allowed hosts

Each provider sends the temperature and the seed in its own request field:

| Provider | Temperature | Seed |
|---|---|---|
| `llamacpp`, `openrouter`, `openai_compatible` | `temperature` | `seed` |
| `ollama` | `options.temperature` | `options.seed` |
| `anthropic` | Nothing | Nothing |

Settings > Chat names each value a provider ignores. Anthropic ignores both, because current Claude models do not use sampling values and the Messages API has no seed. The seed is best effort on hosted APIs. On OpenRouter it reaches the model only when the serving host supports it.

`answer.allowed_hosts` fixes which OpenRouter hosts may serve the Chat model. When it is set, the request carries `provider: {"only": [...], "allow_fallbacks": false, "require_parameters": true}`. Before the first call, OMRS reads the model's endpoint list from OpenRouter once per process. When no listed host supports every value the request sets, OMRS makes no call. The answer is a generation error that names the model, the hosts and the missing values. For the judge, the same refusal gives `verification_skipped`. The library default temperature counts as a set value. Use the host slugs that the OpenRouter model page copies.

Each answer result records what was sent in `sampling` (see [MCP tools](mcp-tools.md#answer_documents)).

`ANSWER__TEMPERATURE`, `ANSWER__SEED`, `ANSWER__ALLOWED_HOSTS`, `ANSWER__VERIFY_TEMPERATURE`, `ANSWER__VERIFY_SEED` and `ANSWER__VERIFY_ALLOWED_HOSTS` each lock their own value in Settings > Chat. These values are server settings. A profile cannot change them.

With the defaults the judge cannot run. `verify_provider: cloud` resolves to OpenRouter, and `OPENROUTER_LLM_MODEL` is empty by default. An empty `verify_model` then leaves the judge with no model, and the answer reports `verification_skipped`. Set a judge model to turn claim checks on. Settings > Chat shows "Not set" and says that claim checks are skipped until you set one.
Environment variables still win over the profile:

```yaml
# config/profiles/documents.yaml — opt-in example (not enabled by default)
answer:
  verify_claims: true
  verify_model: ""          # empty = provider default model
  verify_provider: cloud
```

When verification runs, the result reports `verified: true` on success,
`unverified_claims` listing the failing claims on failure, or
`verification_skipped` with the reason when the judge could not run or had
no cited prose sentence to check. See
[MCP tools — claim verification](mcp-tools.md#claim-verification-optional).

### Metadata — `METADATA__*`

| Field | Default | What it does |
|---|---|---|
| `extraction_mode` | `llamaindex` | `disabled`, `keyword`, `local`, `llamaindex`, `ollama`, `llamacpp`, or `openrouter` |
| `keyword_rules` | — | JSON array of custom `{pattern, category}` rules |
| `taxonomy_mode` | `category` | `category` or `file_type`. **Profile-owned** |
| `ollama_classify_model` | `""` (none; choose one when the Ollama provider is picked) | Ollama model used for classification |
| `classify_max_attempts` | `3` | Maximum attempts **including** the initial request (all metadata LLM backends) |
| `classify_timeout` | `30.0` | Seconds per attempt (all metadata LLM backends) |
| `pipeline_timeout` | `180.0` | Seconds for the llamaindex pipeline (one attempt, three extractors per chunk) |
| `llamacpp_classify_timeout_override` | `None` | Per-provider override of `classify_timeout` for `llamacpp`. Falls back to the shared value when unset |
| `ollama_classify_timeout_override` | `None` | Per-provider override of `classify_timeout` for `ollama`. Falls back to the shared value when unset |
| `openrouter_classify_timeout_override` | `None` | Per-provider override of `classify_timeout` for `openrouter`. Falls back to the shared value when unset |
| `llamacpp_pipeline_timeout_override` | `None` | Per-provider override of `pipeline_timeout` for `llamacpp`. Falls back to the shared value when unset |
| `ollama_pipeline_timeout_override` | `None` | Per-provider override of `pipeline_timeout` for `ollama`. Falls back to the shared value when unset |
| `openrouter_pipeline_timeout_override` | `None` | Per-provider override of `pipeline_timeout` for `openrouter`. Falls back to the shared value when unset |

Set `extraction_mode=disabled` to skip classification entirely. This avoids
classification and category metadata. Details: [Metadata extraction](metadata-extraction.md),
including the six per-provider timeout overrides above and how
degradation from the configured mode is reported in the ingestion result.

### PDF reading

| Variable | Default | What it does |
|---|---|---|
| `PDF_READERS` | `pdf_inspector,liteparse,pypdf` | The reader list, in order. Names: `pdf_inspector`, `liteparse`, `pypdfium2`, `pypdf`. Comma-separated in the environment and `.env`; a JSON array in `omrs.jsonc` |
| `PDF_READER` | `pdf_inspector` | The single-value form of the same setting: `auto`, `pypdf`, `pypdfium2`, `liteparse`, or `pdf_inspector`. It expands to a list |
| `LITEPARSE_OCR_ENABLED` | `false` | OCR for scanned PDFs |
| `LITEPARSE_NUM_WORKERS` | — | Parallel workers |

The environment form is one line, and the file form is an array:

```text
PDF_READERS=pdf_inspector,liteparse,pypdf
```

```jsonc
"pdf_readers": ["pdf_inspector", "liteparse", "pypdf"]
```

The packaged default starts with `pdf_inspector`, a base dependency
([ADR-050](../adr/050-configure-pdf-inspector-as-default-reader.md)).
LiteParse and pypdf are base dependencies too. The default list is the
rescue chain of [ADR-066](../adr/066-tiered-reader-fallback-chain.md) written
out, so the page can show and edit it.

**How the list works.** One rule decides when a later reader runs. A later
reader runs when one of these is true:

1. The reader before it is not installed. This is checked at start-up. The
   first installed reader of the list reads every file. Each reader skipped
   on the way is named in an error. When no listed reader is installed, the
   error says so and pypdf reads the files.
2. The reader before it returned no text for a PDF that has pages. For
   `pdf_inspector` this is the case where it classifies a PDF as text-based
   and still extracts nothing. The readers after it then read the file again,
   in list order, with OCR switched off. A reader that is not installed,
   raises an error or returns no text hands over to the next one. The error of
   the last reader is not caught, because it means broken input.

An error from the first reader is never caught. A list of one reader runs no
retry.

`auto` is not allowed in a list. A list that holds `auto` or an unregistered
name drops that name and logs a warning. The page refuses an empty list, a
repeated name and `auto`.

**The single-value key still works.** `PDF_READER` is valid in every source.
OMRS expands it to a list:

| `PDF_READER` | Same as `PDF_READERS` |
|---|---|
| `pdf_inspector` | `pdf_inspector,liteparse,pypdf` |
| `liteparse`, `pypdfium2` or `pypdf` | That reader alone |
| `auto`, or an unknown name (logs a warning) | `liteparse,pypdfium2,pypdf`, so the first installed reader reads |

The highest source that sets either form wins, in the order of [the short
version](#the-short-version). Inside one source the list key wins, and OMRS
reports the single-value key as ignored: in the log for the environment and
`.env`, and in the problem list for `omrs.jsonc`. When the single-value key
wins, `PDF_READERS` shows its expansion, and the other way round. Code that
reads `pdf_reader` sees the first reader of the list.

The packaged default list is the expansion of the packaged default
`PDF_READER`, so both forms give the same behaviour and the same
[index identity](#index-identity-and-re-ingestion). Tests pin `pypdf` for
determinism.

`PDF_READERS` is the host default. A Read document step in a pipeline can
choose its own `pdf_readers` list for that step only. The step setting does
not change the environment or the other pipelines. A step that lists a reader
whose package is not installed fails validation with `option_unavailable`, and
no node runs. See
[Pipeline graphs](pipelines.md#pdf-readers-on-the-read-document-step).

Each reader declares the text format it emits and whether it provides
page-level provenance. Downstream consumers route on the declared format
instead of the file extension, and search results carry `page_label` only
when the reader can observe pages. The registry descriptor
(`registry.describe(name)`) exposes the same matrix — the table below and
the registry must stay in agreement (a guard test enforces this).

| Reader | Declared text format | Page provenance |
| --- | --- | --- |
| `pdf_inspector` | `markdown` | Yes: one document per page; the whole-document fallback has no page |
| `liteparse` | `plain` | Yes — string `page_label` alongside the integer `page` |
| `pypdf` | `plain` | Yes |
| `pypdfium2` | `plain` | Yes |

### OCR fallback and isolated engines

The OCR routing switch. OCR routing judges every page, so no document-level threshold exists:

| Variable | Default | What it does |
|---|---|---|
| `OCR_FALLBACK_ENABLED` | `true` | Switches OCR routing on and off. Off means no page reaches OCR |

Engine routes and operation:

| Variable | Default | What it does |
|---|---|---|
| `OCR_WORKERS_DIR` | empty | Absolute path to `ocr-workers`. Empty disables folder-based routes |
| `OCR_ENGINES` | `dots-mocr,paddleocr-vl` | The engine list, in order, of any length. The first available engine serves every worker request. Comma-separated in the environment and `.env`; a JSON array in `omrs.jsonc` |
| `OCR_ENGINE_PRIMARY` | `dots-mocr` | The single-value form of the first entry of `OCR_ENGINES` |
| `OCR_ENGINE_FALLBACK` | `paddleocr-vl` | The single-value form of the second entry. Empty means a list of one engine |
| `OCR_WORKER_REQUEST_TIMEOUT` | `300.0` | Minimum timeout in seconds for one parse response |
| `OCR_WORKER_SECONDS_PER_PAGE` | `120.0` | Per-page timeout allowance in seconds |
| `OCR_RUNTIME_URL` | empty | Address of a `llama-server` you run for OCR engines that declare a runtime. Empty means OMRS starts the server (managed). Set means external: OMRS starts nothing and does not check model files. See [OCR runtimes](#ocr-runtimes) |
| `OCR_MATHS_ROUTING_ENABLED` | `true` | Detect maths fonts on the pdf-inspector path and route affected pages |

These settings are flat, top-level fields beside `PDF_READERS`, resolved
once at the composition root and injected. The timeout is
`max(OCR_WORKER_REQUEST_TIMEOUT, requested_pages * OCR_WORKER_SECONDS_PER_PAGE)`.
A 14-page request gets 1,680 seconds with the defaults. On a managed runtime with one slot, the timeout starts when the request holds the runtime's request lock. Time spent waiting for another OMRS process does not count.

**How the engine list works.** The first available engine of the list
serves every request. A later engine serves only when every engine before it
is unavailable before dispatch. An engine is unavailable when it is unknown,
not provisioned or cannot start its runtime. If no engine is available,
flagged pages keep their available text. The answer never decides: an empty or
poor answer does not move a request to the next engine. A worker failure after
dispatch fails that file without retrying on another engine.

One exception exists. When an operator stops the runtime of the engine while
it serves a request (ADR-109), OMRS sends the request once to the next
available engine. It does not send a request twice to the same engine.

**The single-value keys still work.** `OCR_ENGINE_PRIMARY` and
`OCR_ENGINE_FALLBACK` are valid in every source. They expand to the list
primary first, then fallback. A blank name is left out, so an empty fallback
gives a list of one engine. The highest source that sets either form wins.
Inside one source `OCR_ENGINES` wins and the single-value keys are reported
as ignored. To run with no fallback engine, list one engine: set
`OCR_ENGINES=dots-mocr`, or remove the second engine on the Settings page.

Maths pages skip local OCR. Use `OCR_MATHS_ROUTING_ENABLED=false` to
disable maths routing. The master switch `OCR_FALLBACK_ENABLED=false`
disables all OCR routing.

OMRS removed three settings with the document routing unit:
`OCR_FALLBACK_MIN_CONFIDENCE`, `OCR_FALLBACK_PAGE_FRACTION` and
`OCR_MATHS_PAGE_FRACTION`. Each name in the environment fails start-up.
Each lower-case key in `omrs.jsonc` is listed as retired and ignored.

Each engine has its own environment under `ocr-workers/engines/<engine>`.
dots-mocr needs explicit model-licence acceptance. It runs on llama.cpp
([ADR-113](../adr/113-dots-mocr-runs-on-llama-cpp.md)):

- **Runtime.** The engine declares a pinned `llama-server`, build 11941, in
  its `pyproject.toml`. OMRS starts it, checks the build and the model file
  hashes, and stops it after 10 minutes with no request. See
  [Local llama.cpp router](#local-llamacpp-router).
- **Pins.** Provisioning downloads `dots-mocr-Q8_0.gguf`,
  `dots-mocr-mmproj-bf16.gguf` and the llama.cpp `b11941` release, and
  checks the SHA-256 of each. The values live in the engine's `pins.py`.
- **Token.** The model files are in a private Hugging Face repository. Run
  `hf auth login` or set `HF_TOKEN` before you provision. A parse needs no
  token.
- **Memory.** Experiment 41 measured a peak of 17.3 GiB (worker plus
  server) over 257 pages on Apple silicon. The earlier backend peaked at
  22.2 GiB. PaddleOCR-VL peaked at about 15 GiB on CPU (Experiment 37).
  Set `OCR_ENGINES=paddleocr-vl,dots-mocr` (PaddleOCR-VL first) on
  machines with limited memory.
- **Re-index.** The engine fingerprint changed at the move to llama.cpp.
  Provision `dots-mocr` again. The next ingest re-indexes each document
  once.

Paddle packages and the llama.cpp binary stay outside the OMRS environment.

**Set the workers folder in the web app.** Open Integrations › OCR
engines and edit "OCR workers folder". The server checks that the
folder is a full path and holds an `engines` folder before it writes
`ocr_workers_dir` to `omrs.jsonc`. The value applies at the next launch.
Use a checkout that stays, such as the integration worktree, not a
feature worktree that you remove later. When `OCR_WORKERS_DIR` comes from
the environment or `.env`, the field is read-only.

**OCR settings on a pipeline step.** A Read document step of a user
profile can set the OCR switch, the engine list, the routing unit and the
maths switch of this section (not the worker command, folder or timeouts). An empty value uses the server setting.
Built-in profiles always use the server settings. See
[ADR-105](../adr/105-pipeline-steps-own-their-ocr-settings.md).

**Memory with mixed engines.** One worker runs per engine, and only one
engine parses at a time. A pipeline whose steps use dots.mocr and
PaddleOCR-VL can still keep both engines loaded, about 32 GiB in the
worst case. A worker has no idle exit. The dots-mocr `llama-server` stops
after 10 minutes with no request. Use one
engine per pipeline on machines with less memory.

**Migration:** re-provision the required engines and set
`OCR_WORKERS_DIR`. `OCR_WORKER_COMMAND` and `OCR_WORKER_ENV_DIR` were
removed (ADR-105): start-up refuses either one and names the
replacement. See
[provisioning and migration](ingestion.md#provision-the-engines).

`OMRS_OCR_MODEL_CACHE` is a process-level variable read by the worker core.
When set, engine `<name>` uses `$OMRS_OCR_MODEL_CACHE/<name>/`; otherwise
it uses its own `.model-cache/` directory. Set it consistently for
provisioning and worker execution to preserve weights outside worktrees.

### OCR routing unit and the local OCR tier

The unit that OCR is decided on (always the page), and the local tier that runs first
under it (change `page-level-ocr-routing`,
[ADR-069](../adr/069-page-level-ocr-routing-and-the-pdfium-runtime.md)):

| Variable | Default | What it does |
|---|---|---|
| `OCR_ROUTING_UNIT` | `page` | `page` is the only legal value. `document` fails start-up with a message that names `page`. In `omrs.jsonc`, `"ocr_routing_unit": "document"` is listed as a settings-file problem and ignored, so `page` applies |
| `OCR_SKIP_BLANK_PAGES` | `true` | Skip blank pages. On, a flagged page with no ink keeps its native text and costs no OCR. Off, blank pages go to OCR like any flagged page. Accepts `true`/`false`, `1`/`0`, `yes`/`no` and `on`/`off`. Other text stops start-up and names `ocr_skip_blank_pages`. In `omrs.jsonc`, a value that is not a boolean is listed as invalid and ignored. Off re-indexes PDF sources only |
| `OCR_NON_LATIN_ROUTING` | `off` | `off`, `detect` or `always`. Sends non-Latin pages past the local tier to the OCR engines. See [Non-Latin page routing](#non-latin-page-routing). Any other value fails start-up and names the three |
| `OCR_LOCAL_BACKENDS` | `pp-ocrv6-small` | The local OCR backends, in the order they read. Comma-separated in the environment; a JSON array in `omrs.jsonc`. Accepted names: `pp-ocrv6-small`, `indra`. An unknown name fails start-up and lists the accepted names. See [Local OCR backends](#local-ocr-backends) |
| `OCR_LOCAL_CUTS` | `{}` | A JSON object that sets the confidence cut of a backend, one entry per backend name, for example `{"indra": 0.96}`. Each value is a number from 0 to 1. A backend with no entry uses its own default cut. A page below the cut goes to the next backend or to the worker. A page with no reported confidence goes on too. An unknown name, a value outside 0 to 1, or a value that is not a number fails start-up. In `omrs.jsonc` the key is `ocr_local_cuts`. See [Local OCR backends](#local-ocr-backends) |
| `OCR_LOCAL_OFFLINE` | `false` | `true` forbids the model download; a missing cached model then degrades |
| `OCR_LOCAL_MODEL_DIRECTORY` | empty | Artifact directory (`<name>/<revision>` leaf) to load the model from. Empty means the library's default cache |

Each backend registers its own default cut with the experiment that measured
it. The default cut of `pp-ocrv6-small` is 0.92 and the default cut of `indra`
is 0.94. Both come from [Experiment 46a](../../experiments/46a-local-ocr-per-backend-cuts-2026-11-06/report.md),
which re-read the saved results of Experiment 46 (229 pages from 9 documents).
Set `OCR_LOCAL_CUTS` only when you have measured a better cut for your
collection. The sample is small, so treat the defaults as settings chosen from
evidence and not as a publication result.

Set one cut in the environment or in `.env`. Write the value as a JSON object:

```bash
OCR_LOCAL_CUTS={"indra": 0.96}
```

Set the same cut in `omrs.jsonc`:

```jsonc
"ocr_local_cuts": {"indra": 0.96}
```

An empty map means that every backend uses its default cut.

These names are **flat on purpose**. `pydantic-settings` resolves
its `__` delimiter only into nested settings blocks, and the OCR
fields are top-level — a nested spelling such as
`OCR__ROUTING_UNIT` matches nothing and is discarded in silence. The
never-shipped nested spellings are trapped in `config/legacy.py` with
an error naming the flat replacement, so a typo cannot pass unnoticed.

An `OCR_ROUTING_UNIT` other than `page` raises at startup rather than
warning and falling back: the unit feeds the index identity, and a
fallback would index a corpus under a unit nobody chose.

The local tier needs two process-level libraries that pdf-inspector
loads by environment variable: `PDFIUM_LIB_PATH` (LiteParse ships
`libpdfium.dylib` in its package directory) and `ORT_DYLIB_PATH`
(ONNX Runtime ships its dylib in `capi/`). OMRS sets each variable itself,
from the library bundled in the running environment, when the variable is
unset or empty. This holds for the CLI, the MCP server, the watcher and
`omrs web`. A value you set stays: put your own path in the shell or in
`.env` (the composition root runs `load_dotenv()` before any read). When a
bundled library is missing, its variable stays unset. On
first use the model (`pp-ocrv6-small@oar-ocr-v0.7.0`, about 31 MB)
downloads unless `OCR_LOCAL_OFFLINE=true` and a cache is present. A
missing library or model never fails a file. Flagged pages go to the
worker engine in one page-listed request (issue #161). Only when no OCR
route exists either do they keep native text and count unresolved, with
one warning that names both missing tiers.

#### Local OCR backends

`OCR_LOCAL_BACKENDS` lists the backends of the local tier in reading order.
The default list holds `pp-ocrv6-small`. In the environment, write the names
separated by commas. In `omrs.jsonc`, write a JSON array. Settings > Document
reading edits the same list as the Local OCR backends row.

```bash
OCR_LOCAL_BACKENDS=pp-ocrv6-small,indra
```

| Backend | Installed by | Default confidence cut | `ocr_backend` value |
|---|---|---|---|
| `pp-ocrv6-small` | Base install | 0.92 | `pdf_inspector_ocr` |
| `indra` | Extra `local-ocr-indra` (`indra-ocr==1.1.2`, no PyTorch) | 0.94 | `indra_ocr` |

The first backend reads every flagged page that no page rule dropped or sent direct. The next
backend reads only the pages that the backends above did not keep. The OCR
engines read the pages that no listed backend kept. A backend keeps a page
when its text is not empty and its confidence reaches the cut of that backend.
Confidence is the only test. No backend filters by script. Each backend has its
own cut because each backend reports confidence on its own scale. The cut of a
backend is its `OCR_LOCAL_CUTS` entry, or its default cut when it has no entry.

A backend that cannot run is skipped for the call, with one warning per
process. When no listed backend can run, the missing-runtime rule of the local
tier applies: the flagged pages go to the OCR engines.

Indra needs its weights on disk. Set `INDRA_OCR_MODEL_DIR` to the folder of the
snapshot. When `OCR_LOCAL_OFFLINE=true`, Indra reads only that folder and never
downloads. Install the extra with `uv sync --extra local-ocr-indra`. The Indra
code is Apache-2.0. The weights use the modified OpenRAIL-M licence, which
limits commercial and competing use. Read it before you use the weights.

`OCR_NON_LATIN_ROUTING=always` and the `detect` text-layer check send pages
direct before any local backend reads them, Indra included. Under `detect`, the
output check also sends a mostly non-Latin result of any backend, Indra
included, to the OCR engines. When `indra` is in the list, set
`OCR_NON_LATIN_ROUTING` to `off`. Then the cut of Indra alone decides which
Arabic and Devanagari pages stay local. See
[Non-Latin page routing](#non-latin-page-routing).

Check the list: run `omrs config show` and read the `ocr_local_backends` and
`ocr_local_cuts` lines.
Each line ends with the source that set it. The Integrations page shows each
listed backend with its state and effective cut (see
[Reading parts on the Integrations page](web-workspace.md#reading-parts-on-the-integrations-page)).
To add a backend or a page rule, follow the procedures in
[Reading parts](reading-parts.md).

**Set a cut on the Settings page.** Open Settings > Document reading > Local
OCR. Each backend row has a "Confidence cut" input. An empty input shows the
default cut of the backend and means "use the default". Type a number from 0 to
1 to set a cut. The page saves the cuts with the backend list in one write to
`ocr_local_cuts`. A number outside 0 to 1 shows the message "The cut must be a
number from 0 to 1." and the page saves nothing.

**Set a cut on a pipeline step.** A Read document step of a user profile can
set `ocr_local_cuts` for its own pipeline. The step option follows these rules:

- A step entry replaces the cut of its own backend in that pipeline only.
- A backend with no step entry keeps the effective cut of the server. This
  differs from other read options, which replace the server value as a whole.
- An empty box in Studio means "inherit". Clear the last step cut to remove the
  key from the step.
- The graph-wide override `overrides.ocr_local_cuts` is refused with the reason
  `host_owned_setting`. The server owns the setting.
- Step cuts do not enter the graph fingerprint. They enter the identity of PDF
  sources, so a changed step cut re-reads PDF sources only.

Built-in profiles always use the server cuts. See
[Local OCR cuts on Read document step](pipelines.md#local-ocr-cuts-on-read-document-step).

#### Reading part options

`READING_PART_OPTIONS` holds the options of parts that have no flat key. The
value is a JSON object. Each key is a part name. Each value is an object of
option names. In `omrs.jsonc`, the key is `reading_part_options` and the value
is a JSON object.

```bash
READING_PART_OPTIONS='{"stamp-check": {"enabled": true}}'
```

The example names a page rule `stamp-check` from an installed package.
Start-up checks every entry against the descriptor of the part:

- The key must name a built-in part or a part that discovery accepted.
- Each option name must be an option that the descriptor declares.
- Each value must have the declared type and be in the accepted set.

Every page rule also takes `enabled`. A built-in rule ignores it. A rule from
another package runs only when its entry holds `"enabled": true`. A failed check
stops start-up and names the part and the option, never the value. For
example: `READING_PART_OPTIONS is not valid. Part 'maths' has no option
'colour'. Its options: enabled.`

An option that the descriptor marks as part of the identity enters the
identity of PDF sources. This holds only for a part in use: a listed reader
or backend, or a page rule from another package with `enabled` true. The
Settings page has no row for this key. Edit it in `omrs.jsonc`.

#### Non-Latin page routing

The default local backend has no recogniser for Arabic, Bengali or Devanagari
(Experiment 33: recall 0.000 on all 129 such pages). The `indra` backend reads
Arabic and Devanagari well and Bengali badly (Experiment 46). No backend filters
pages by script. The confidence cut of each backend decides which pages stay
local. `OCR_NON_LATIN_ROUTING` (change `non-latin-script-routing`) sends
non-Latin pages to the OCR engines without a wasted local pass. It has three
values:

| Value | What happens |
|---|---|
| `off` | Default. Routing is as before. |
| `detect` | A flagged page whose text layer is mostly non-Latin letters skips the local tier. A local OCR result that is mostly non-Latin letters escalates whatever its confidence, with the reason `non_latin_output`. This holds for the result of every local backend, Indra included. |
| `always` | Every flagged page skips the local tier. Use this only for a collection that you know is non-Latin. |

A page is non-Latin when it has at least 40 letters and at least half of them
are not Latin. Accented Latin letters count as Latin. Digits, punctuation and
space are not letters. A page with fewer than 40 letters gets no verdict. The
two numbers are fixed in the code with a version number. They are not settings.

What `detect` cannot see: a scanned page. A scan has no text layer, so the
detector has nothing to read before OCR. The four non-Latin PDFs of
Experiment 33 are all scans, and each page holds only a few Latin letters
of stamp text. For a scanned non-Latin collection, `detect` leaves the local
tier in place, and the confidence cut of each backend sends the pages on after
the local pass. Use `always` to skip the local pass. `detect` never renders a page, runs
OCR or calls a model.

How it combines with other settings:

- Only the page unit exists, so only the page unit has this setting.
- A page that is both a maths page and a non-Latin page goes to the OCR
  engines once, in the same page-listed request.
- `non_latin_output` is an extra reason to escalate. It does not replace the
  confidence cut. No backend is exempt from this check.
- When `indra` is in `OCR_LOCAL_BACKENDS`, set `OCR_NON_LATIN_ROUTING` to
  `off`. Under `detect`, every non-Latin result of Indra escalates, so Indra
  keeps no Arabic or Devanagari page.
- A blank flagged page leaves the route before this setting acts.
- If no OCR engine that speaks the page-listed protocol is available, the
  pages go through the local tier as if the setting were `off`. One warning
  per file names the configured engines.
- A PDF read this way carries `pages_non_latin`, the number of pages the setting
  sent direct or escalated. The key appears only when the setting is not `off`.
  It stays out of the embedded text.

Identity effect: with `detect` or `always`, the source identity of a PDF
holds `non_latin_routing: {mode, detector_version}`. Turning the setting on
reindexes PDF sources once on the next ingest. Other sources keep their
digest. With `off` the block is absent, so installs that do not use the
setting keep every digest. Settings > Document reading shows the setting
as a choice of the three values.

Example environment line:

```bash
OCR_NON_LATIN_ROUTING=always
```

Identity: the index identity schema is 8. The routing payload that every source
carries is `{enabled, routing_unit, blank_page_test}`, and the maths block is
`{enabled, detector_version}`. The page-source counts are excluded for every
source. The local OCR cuts and the local model identity are in the `parser`
block of PDF sources only. See
[Index identity and re-ingestion](#index-identity-and-re-ingestion). Reading an
index does not rebuild it.

The packaged default is `OCR_FALLBACK_ENABLED=true`
([ADR-065](../adr/065-ocr-fallback-gate-promoted-to-packaged-default.md),
page routing from [ADR-069](../adr/069-page-level-ocr-routing-and-the-pdfium-runtime.md)).
With no OCR route available, a flagged page keeps its native text and the
batch continues with an actionable warning. Set `OCR_FALLBACK_ENABLED=false`
to disable routing entirely.

Full behaviour, including provisioning and OCR metadata, is in
[the ingestion guide](ingestion.md#ocr-fallback-for-scanned-pdfs).

#### Decision models and document routers

A document router asks a decision model one yes-or-no question about a PDF page:
"is this text layer usable?". The router judges only pages that the scan did not
flag and that have native text. A low answer sends the page to OCR. This finds a
page whose hidden text layer is junk (ADR-110). No router is selected by default.
A router costs about 3.6 s per judged page and sent about 2.7% of healthy pages to
OCR in Experiment 43.

Three keys in `omrs.jsonc` set it up:

| Key | Env | What it holds |
|---|---|---|
| `decision_models` | none | Named decision models: where a request goes. |
| `document_routers` | none | Named routers: the question, the model and the threshold. |
| `document_router` | `DOCUMENT_ROUTER` | The host router: a router name. Blank means no router. |

The two maps are objects keyed by entry name. They live only in `omrs.jsonc`.
No environment variable sets a map, and `.env` does not either. An entry name
starts with a letter or digit, holds only letters, digits, hyphens and
underscores, and has at most 64 characters. No router can take the name `none`.

`document_router` follows the normal source order. Set in the environment or
`.env`, it wins and locks the choice on the Settings page.

Fields of a `decision_models` entry:

| Field | Required | What it holds |
|---|---|---|
| `kind` | yes | `llamacpp`, `typesafe`, `cloudflare` or `ollama`. |
| `address` | yes | The server address, `http` or `https`, with no user name, password, query or fragment. |
| `model` | yes | The model name that the request names. |
| `images` | no | `true` when the model takes a page image. Default `false`. |
| `key` | no | A key reference: `env://NAME`, `file://<path in secrets/>` or `keychain://<provider>`. Never the key itself. |
| `server` | no | `llamacpp` only: `external` or `managed`. A managed entry runs on the llama.cpp router, and its `model` names an entry of `llamacpp_models`. |

The model file, the projector and their SHA-256 values live in `llamacpp_models` as `file`, `projector`, `sha256` and `projector_sha256`, not in the decision entry. A decision entry that still holds `model_file`, `projector_file`, `model_sha256` or `projector_sha256` is listed in the problem list. See [The model list](#the-model-list).

Fields of a `document_routers` entry:

| Field | Required | What it holds |
|---|---|---|
| `model` | yes | The name of a `decision_models` entry. |
| `question` | yes | The question the model answers with yes or no. |
| `threshold` | yes | A number from 0 to 1. A page whose P(yes) is below it goes to OCR. |
| `images` | no | `true` sends the page image with the text. Default `false`. |
| `max_chars` | no | The page text is cut to this many characters. Default 2000. |
| `send_off_machine` | no | The opt-in for a hosted model. Default `false`: a hosted router sends nothing. |

Example `omrs.jsonc` (fake values; the threshold 0.172 comes from Experiment 43
and is not confirmed):

```jsonc
{
  // Where each yes-or-no request goes.
  "decision_models": {
    "clef-local": {
      "kind": "llamacpp",
      "address": "http://127.0.0.1:8090",
      "model": "clef-flash-q8_0",
      "images": true,
      "server": "external"
    },
    "jev": {
      "kind": "typesafe",
      "address": "https://api.typesafe.ai",
      "model": "jev",
      "images": true,
      "key": "env://TYPESAFE_API_KEY" // a reference, never the key
    }
  },
  // Named routers. A profile or the host setting picks one by name.
  "document_routers": {
    "handwriting": {
      "model": "clef-local",
      "question": "Is the text layer of this page a usable transcription of the page?",
      "threshold": 0.172,
      "images": true,
      "max_chars": 2000
    }
  },
  // The host router. Remove the key, or leave it blank, for no router.
  "document_router": "handwriting"
}
```

Rules:

- An entry with an unknown field or a wrong value is ignored. The problem list
  names the field, for example `document_routers.handwriting.threshold`. The
  other entries load.
- A literal key in an entry is ignored and listed. The entry loads without the
  key. The log and the problem list never show the key.
- Only `omrs web` writes the maps, through the Settings page. A save keeps the
  comments, checks the file revision and refuses a literal key. The page cannot
  delete a decision model that a router names, or a router that a saved
  profile names.
- The CLI, the stdio MCP server and the watcher read the maps when they start.
  They never write the file.

### Document backend

| Variable | Default | What it does |
|---|---|---|
| `DOCUMENT_BACKEND` | `local` | `local` or `azure`. Unrecognised values fail startup |
| `AZURE_DOC_INTELLIGENCE_ENDPOINT` | — | Azure endpoint URL |
| `AZURE_DOC_INTELLIGENCE_KEY` | — | Azure key |
| `AZURE_DOC_INTELLIGENCE_MODEL` | `prebuilt-layout` | Azure model |

Azure is opt-in ([ADR-024](../adr/024-dual-deployment-modes.md)) and
degrades to local parsing when credentials are missing or unreachable,
or when the optional SDK is absent. Each warning names the missing
piece: the `AZURE_DOC_INTELLIGENCE_ENDPOINT` /
`AZURE_DOC_INTELLIGENCE_KEY` variables, or the
`azure-ai-documentintelligence` package with `uv sync --extra azure`.
Azure reads `.pdf`, `.docx`, and `.doc` only; every other file type
goes through the local backend whatever `DOCUMENT_BACKEND` is set to.
An unrecognised `DOCUMENT_BACKEND` value (not `local` or `azure`) fails
startup rather than silently falling back. The accepted names come from
the document-backend registry instead of a fixed config-time list.

### Codebase map

| Variable | Default | What it does |
|---|---|---|
| `MAGIKA_BINARY` | `magika` | Availability probe for file-type detection. Detection runs in process through the Python API; the binary is the availability signal and the smoke tool's ground truth. A bare name is looked up on `PATH`, then next to the Python that runs omrs (where an install puts it). |
| `CODEBASE_MAP_CACHE_DIR` | `.opencode` | Cache location |
| `CODEBASE_MAP_MAX_FILES` | `5000` | File limit |
| `CODEBASE_MAP_MAX_DEPTH` | `10` | Directory depth limit |
| `DOC_SIMILARITY_THRESHOLD` | `0.85` | Similarity edge cutoff. Not yet calibrated |

The cache key is the git commit hash plus an owner context. The owner context
holds the map settings above (except the cache location), the community
settings, and the store's durable data version for `documents`. A cache with a
different or missing owner context is a miss, and the map rebuilds. If the
path is not a git repository, or the store has no durable data version, the
map rebuilds on every call.

### Community detection

Both graph subsystems, the codebase graph and the document similarity graph,
use the same configured strategy and seed.

| Variable | Default | What it does |
|---|---|---|
| `COMMUNITY_ALGORITHM` | `louvain` | `louvain` or `leiden`. Unknown names fail startup and list the available strategies |
| `COMMUNITY_SEED` | `0` | Seed for algorithm randomness. `0` keeps partitions deterministic |

`COMMUNITY_ALGORITHM` and `COMMUNITY_SEED` are cross-cutting, so their
environment variable names are flat. An empty value
(`COMMUNITY_ALGORITHM=`) resets to `louvain`.

There is no `auto`. Whether an optional package is installed must not change
graph output silently, so the algorithm is always explicit.

**Leiden.** `leiden` requires the optional `community-leiden` extra:

```bash
uv sync --extra community-leiden
```

Setting `COMMUNITY_ALGORITHM=leiden` without the extra fails startup with the
installation instruction above. There is no silent fallback to `louvain`: an
explicit algorithm selection is an operator contract. See
[ADR-044](../adr/044-pluggable-community-detection.md).

---

## Web workspace settings

`omrs web` has one setting of its own in `.env`, `WEB_MAX_UPLOAD_MIB`. It also reads the engine settings that other commands read. Its other options are command-line flags only: `--workspace`, `--port`, `--host`, `--root` and `--experiment-root`. The server builds its Engine from the same settings sources as the other commands. See [Web workspace](web-workspace.md).

| Variable | Default | Use |
|---|---|---|
| `WEB_MAX_UPLOAD_MIB` | unset | Per-file upload limit in whole MiB, 1 to 2048. Same as `--max-upload-mib`. |

The server uses the first upload limit it finds in this order:

1. `--max-upload-mib`.
2. `WEB_MAX_UPLOAD_MIB`, from the environment or `.env`.
3. `web_max_upload_mib` in `omrs.jsonc`, which the page writes from Settings > Workspace.
4. 50 MiB.

A launch value (step 1 or 2) locks the limit for that run. Settings then shows the limit and cannot change it. A hand edit of `web_max_upload_mib` in `omrs.jsonc` applies to the next upload. Any other value stops `omrs web` with exit code 2 before it binds a port. The name is flat, because `omrs web` options are not engine settings.

### Provider and Chat values

`omrs web` also lets you save LLM provider addresses, API keys, the Chat model and the claim check judge in Settings. The order is environment, `.env`, `omrs.jsonc`, the key file, then the default. Only the environment and `.env` lock the field (see [User config folder](#user-config-folder)). A saved key lives in the system keychain only, and `omrs.jsonc` holds a `keychain://` reference to it. A saved value applies at once with no restart. Details: [Providers](#providers), [Answering](#answering--answer__) and [Web workspace](web-workspace.md#provider-settings).

### Document reading values

The [Page routing guide](page-routing.md) shows where each key acts in the page flow.

Settings > Document reading edits ten keys in `omrs.jsonc`: `pdf_readers`, `ocr_fallback_enabled`, `ocr_routing_unit`, `ocr_engines`, `ocr_skip_blank_pages`, `ocr_maths_routing_enabled`, `ocr_non_latin_routing`, `document_router`, `ocr_local_backends` and `ocr_local_cuts`. The three list keys hold an array of names, and the page shows each as an ordered list with add, remove, move up and move down. The key `ocr_local_cuts` holds an object, and the page shows it as a "Confidence cut" input in each backend row. See [PDF reading](#pdf-reading), [OCR fallback and isolated engines](#ocr-fallback-and-isolated-engines) and [Local OCR backends](#local-ocr-backends).

- Each key applies after a restart only. Until then, the row shows the value in force and the saved value with "Restart to apply".
- Each key is part of the [index identity](#index-identity-and-re-ingestion). After the restart, the next ingest can read existing files again. A change to `ocr_local_cuts` or `ocr_local_backends` reads PDF sources only.
- A key in the environment or `.env` is locked. The row tells you which variable to remove.
- The page refuses a reader list that holds a name that is not a known reader. A reader that is not installed shows "Not installed". The page allows an OCR engine name that is valid but not provisioned yet, and marks it "Not provisioned".
- The page refuses a local OCR backend list that holds an unknown name. A backend that is not installed shows "Not installed" and you cannot add it. A backend that is already in the list stays.
- The page refuses an empty list, a repeated name, `auto` in the reader list, and blank text. "Use default" removes the key from the file.
- A save of a list writes the list key and removes the matching single-value keys (`pdf_reader`, `ocr_engine_primary`, `ocr_engine_fallback`) from `omrs.jsonc` in the same write. The page never writes a single-value key.
- The page refuses a cut that is not a number from 0 to 1, and a cut for a name that is not a local OCR backend. An empty input removes the entry, and the backend uses its default cut. Every save of `ocr_local_cuts` removes the retired single-cut key from the file in the same write. When the file holds that key, the Local OCR group shows a notice with a "Remove it" button. See [Per-backend local OCR cuts](#per-backend-local-ocr-cuts).
- A list of one engine turns the fallback engine off. Remove the second engine on the page and save.
- These checks run only when the page saves. At startup, an unknown `pdf_reader` from any source still logs a warning and falls back to `auto`.

---

## Upgrade notes

### Ordered reader and OCR engine lists

`PDF_READERS` and `OCR_ENGINES` replace the single-value reader and engine keys as the settings that the page edits. See [PDF reading](#pdf-reading) and [OCR fallback and isolated engines](#ocr-fallback-and-isolated-engines).

Nothing to do on upgrade. The default lists equal the behaviour before the change. The old keys `PDF_READER`, `OCR_ENGINE_PRIMARY` and `OCR_ENGINE_FALLBACK` still work in every source, and start-up does not refuse them. Every existing [index identity](#index-identity-and-re-ingestion) stays the same, so no source re-ingests.

| Before upgrade | After upgrade | What to do |
|---|---|---|
| `PDF_READER`, `OCR_ENGINE_PRIMARY` or `OCR_ENGINE_FALLBACK` set in the environment, `.env` or `omrs.jsonc` | The old key still applies and expands to a list. | Nothing. |
| An old key saved in `omrs.jsonc`, then you save a list on the Settings page | The page writes the list key and removes the old keys in the same write. | Nothing. |
| `PDF_READER=pdf_inspector` and pdf-inspector is not installed | Start-up uses LiteParse, the next reader of the list. Before, it used pypdf. PDF sources can then read with a different reader. | Install pdf-inspector, or set `PDF_READERS=pypdf` to keep the old reader. |
| `OCR_ENGINE_FALLBACK=` (empty) to turn the fallback engine off | Still turns it off. | Optional: set `OCR_ENGINES` to one engine. |

A reader list that no single value expands to adds `parser.pdf_readers` to the identity of PDF sources. An engine list with a third engine adds its fingerprint to every source. After you edit a list, the next explicit ingest reads the affected sources again once.

Rollback: revert the merge commit. A file that holds only the list keys then falls back to the code defaults. These equal the default lists. A custom list is lost on rollback, so keep a copy of it.

### Ordered local OCR backend list

`OCR_LOCAL_BACKENDS` makes the local tier an ordered list. See [Local OCR backends](#local-ocr-backends). For the cut of each backend, see [Per-backend local OCR cuts](#per-backend-local-ocr-cuts).

Nothing to do on upgrade. The default list holds `pp-ocrv6-small`, which gives the behaviour before the change.

| Before upgrade | After upgrade | What to do |
|---|---|---|
| You add `indra` to the list | PDF sources re-index once. Other sources keep their digest. | Install the extra and set `INDRA_OCR_MODEL_DIR`. Set `OCR_NON_LATIN_ROUTING` to `off`. |

### Per-backend local OCR cuts

`OCR_LOCAL_CUTS` sets the confidence cut of each local OCR backend. It replaces `OCR_LOCAL_MIN_CONFIDENCE`, which set one cut for every listed backend. See [Local OCR backends](#local-ocr-backends).

| Before upgrade | After upgrade | What to do |
|---|---|---|
| `OCR_LOCAL_MIN_CONFIDENCE` or `OCR__LOCAL_MIN_CONFIDENCE` set in the environment or in `.env` | Start-up stops. The message names `OCR_LOCAL_CUTS`. | Remove the variable. Set `OCR_LOCAL_CUTS` as a JSON object, for example `{"pp-ocrv6-small": 0.9}`, only if you need a cut other than the default. |
| `ocr_local_min_confidence` in `omrs.jsonc` | The server starts. OMRS ignores the key and lists it as retired. Settings > Document reading shows a notice with a "Remove it" button. | Press "Remove it", or save any cut on the page. Every save of `ocr_local_cuts` removes the old key. |
| No cut set | The default cuts change from 0.90 to 0.92 for `pp-ocrv6-small` and 0.94 for `indra`. | Set `OCR_LOCAL_CUTS` to keep the old value. |
| Every collection | Each source is read again once on its next explicit ingest. The index identity schema moves from 7 to 8. | Plan one re-ingest of each collection. A second ingest processes no source. |
| You change a cut later | PDF sources are read again. Markdown and code sources keep their digest. | Re-ingest PDF sources only. |
| `indra` is in `OCR_LOCAL_BACKENDS` and `OCR_NON_LATIN_ROUTING` is `detect` | Indra has no script filter now. Under `detect`, every non-Latin result of Indra escalates. | Set `OCR_NON_LATIN_ROUTING` to `off`. |

OMRS does not convert the old value. The old key meant "every backend", and that meaning no longer exists. Rollback: revert the merge commit. The old digests return, so each source is read again once more. The `ocr_local_cuts` key in `omrs.jsonc` is then listed as unknown and ignored.

### Local Chat and classification stay apart (ADR-108)

Classification and llama.cpp Chat each get their own address. The server that OMRS runs loads the Chat model, so the server model setting is retired. The router note below (ADR-115) replaces the addresses and the Chat server choice named here. See [llama.cpp roles](#llamacpp-roles).

| Before the upgrade | After the upgrade | What to do |
|---|---|---|
| `llamacpp_chat_url` set, no classification address | `llamacpp_chat_url` and `llamacpp_classify_url` are retired. Classification and Chat use `llamacpp_router_url`. | Follow the router note below. |
| `llamacpp_chat_model` set | The key stays. It names the classification model of the router list. The index identity is the same, so no re-ingest. | Nothing. |
| Chat on llama.cpp with a model, server run by you | `llamacpp_chat_server` is retired. The router note below applies. | Set `llamacpp_router_server` to `external` and `llamacpp_router_url` to the address of your server. |
| Chat on llama.cpp with a blank `answer.model` | Chat refuses with "Choose a Chat model". `GET /v1/settings/chat` gives the reason `no-model`. Before, the server answered with the model it had loaded. | Choose a Chat model in Settings > Chat. |
| llama.cpp claim check judge with a blank `answer.verify_model` | The claim check is skipped with "Choose a judge model in Settings > Chat." Before, the judge used the classification model. | Choose a judge model in Settings > Chat. |
| Ollama claim check judge with a blank `answer.verify_model` | The claim check is skipped with "Choose a judge model in Settings > Chat." Before, the judge used `metadata.ollama_classify_model`. | Choose a judge model in Settings > Chat. |
| Chat on Ollama with a blank `answer.model` | Chat refuses with "Choose a Chat model" and sends nothing. Before, Chat sent a request with no model name. | Choose a Chat model in Settings > Chat. |
| `llamacpp_server_model` in `omrs.jsonc` | Ignored and listed in the problem list, with the replacement `answer.model`. The old value never becomes the Chat model. | Follow the steps below. |
| `LLAMACPP_SERVER_MODEL` in the environment or `.env` | Start-up fails. The message names the replacement: `ANSWER__PROVIDER=llamacpp` with `ANSWER__MODEL`. | Remove the variable. Set the replacement, or follow the steps below. |

An install that used OMRS's own server:

1. On the llama.cpp card in Settings > Providers, set "Who runs llama.cpp" to "OMRS runs llama.cpp" (`managed`).
2. In the Router panel, check that the router list holds the old model. Add it with Get a model and Use this model if it is not there.
3. In Settings > Chat, choose the provider llama.cpp, paste the old `llamacpp_server_model` value as the Chat model, then save. When Chat already uses llama.cpp with no model, "Choose a Chat model" offers the same choice from the router list.

Then press Start in the Router panel. Step 1 and the Use this model button need a browser session with the `credentials` scope.

Rollback is a revert of the merge commit. The older build ignores `llamacpp_classify_url` and `llamacpp_chat_server` and lists them as unknown keys. It reads `llamacpp_server_model` again if you kept it.

### Managed llama.cpp runtimes (ADR-109)

One runtime manager now starts and stops every local `llama-server` for all OMRS processes. The router note below (ADR-115) replaces the `chat` and `embeddings` runtimes named here. See [Local llama.cpp router](#local-llamacpp-router).

| Before upgrade | After upgrade | What to do |
|---|---|---|
| `LLAMACPP_IDLE_SLEEP_SECONDS` in the environment or `.env` | Start-up fails. The message names the variable and the fixed 10-minute idle stop. | Remove the variable. |
| `llamacpp_idle_sleep_seconds` in `omrs.jsonc` | Ignored and listed in the problem list. | Remove the key. |
| `PUT /v1/llamacpp/router` with `idle_sleep` | Returns 400. The old `PUT /v1/llamacpp/server` route is gone (404). | Remove the field from the request. |
| The managed Chat server stopped when `omrs web` exited | It stops when the last OMRS process leaves. A CLI process that still uses it keeps it running. | Nothing. Press Stop in the Router panel to stop it at once. |
| The managed Chat server freed its model after 300 idle seconds and kept running | The server stops after 10 idle minutes and starts again on the next request. | Nothing. |
| `llamacpp-server.log` in the workspace folder | `server.log` in the runtime folder, under the state folder. | Nothing. |
| Embeddings on a server you run | `LLAMACPP_EMBED_SERVER` and `LLAMACPP_EMBED_URL` are retired. | Follow the router note below: set `llamacpp_router_server` to `external` and `llamacpp_router_url` to the address. |
| An OCR engine started its own `llama-server` | The engine declares a runtime and OMRS starts it. `OCR_RUNTIME_URL` stays blank. | Nothing. |

Rollback: revert the merge commit. The state folder holds no settings, so you can delete it.

### One llama.cpp router (ADR-115)

One router serves every local llama.cpp model except OCR. It has one address and one mode. Each model has an entry in `llamacpp_models` with its own context size. See [Local llama.cpp router](#local-llamacpp-router).

Six keys are retired. An environment or `.env` value stops start-up, and the message names the replacement. An `omrs.jsonc` key is ignored and listed in the problem list with its replacement.

| Retired | Replacement |
|---|---|
| `llamacpp_embed_url` (`LLAMACPP_EMBED_URL`), `llamacpp_chat_url` (`LLAMACPP_CHAT_URL`), `llamacpp_classify_url` (`LLAMACPP_CLASSIFY_URL`) | `llamacpp_router_url` (`LLAMACPP_ROUTER_URL`) |
| `llamacpp_chat_server` (`LLAMACPP_CHAT_SERVER`), `llamacpp_embed_server` (`LLAMACPP_EMBED_SERVER`) | `llamacpp_router_server` (`LLAMACPP_ROUTER_SERVER`) |
| `llamacpp_context_window` (`LLAMACPP_CONTEXT_WINDOW`) | `ctx-size` in the preset of the model's entry in `llamacpp_models` |
| Decision entry fields `model_file`, `projector_file`, `model_sha256`, `projector_sha256` | The entry in `llamacpp_models` that the decision entry names with `model` |

| Before upgrade | After upgrade | What to do |
|---|---|---|
| The Llama app on port 9931 serves embeddings and classification | Set `llamacpp_router_server` to `external` and `llamacpp_router_url` to `http://127.0.0.1:9931/v1`. | List the models that the app serves in `llamacpp_models`. OMRS does not check their files. |
| OMRS ran a managed Chat server | The router runs every model. | Add the Chat model to `llamacpp_models`, then choose it in Settings > Chat. |
| `answer.provider` was `ollama` by default | The default is `llamacpp` with no Chat model chosen. | Choose a Chat model in Settings > Chat, or set the provider you use. An install that saved its provider keeps it. |
| The default embedding model was `qwen3-embedding:0.6b` (1,024 dimensions) | The default is `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` (2,560 dimensions). | Plan one re-index of every collection (see One-time re-index in this section). |

**One-time re-index.** The embedding identity changes when a collection moves to Qwen3-Embedding-4B, because the vectors grow from 1,024 to 2,560 dimensions. A collection holds vectors of one size from one embedding model, so each collection re-indexes once. Re-ingest every collection after the router serves the new model. The change `local-ocr-per-backend-cuts` forces a re-index too, so one pass covers both. After the pass, run a known-answer search in each collection.

In `omrs web`, the first managed start downloads each listed model that has no file, through the Get a model job. A 4B model at Q8_0 is about 4.3 GB. The Router panel shows the note "Downloading" on the row. The CLI, the stdio MCP server and the watcher download nothing by themselves. `omrs llamacpp install` downloads each missing model into the Hugging Face cache (see [CLI reference](cli-reference.md#llamacpp-install)).

Rollback is a revert of the merge commit. The state folder holds no settings, so you can delete it. The older build reads the retired keys again. Rollback re-indexes once more, because the embedding identity changes back.

---

## Index identity and re-ingestion

OMRS skips a source it has already indexed when the file bytes and the
index identity both match. Change the identity and every affected source
re-ingests on the next run, even if not one byte of the file changed.

These settings are part of the index identity:

| What | Why it counts |
| --- | --- |
| `PDF_READERS`, as the **resolved** reader and list | It decides which reader produced the text. The resolved first reader is recorded, so `auto` counts as the reader it resolved to, and an uninstalled first reader counts as the next installed reader. A list that equals the expansion of one `PDF_READER` value adds nothing, so older identities stay the same. Any other list adds the full ordered list (PDF sources only) |
| The output revision of the resolved PDF reader (PDF sources only) | A reader declares a new revision when its output changes, so each PDF source reprocesses once. `pdf_inspector` declares 2 since it emits page documents; the other readers declare 1. Non-PDF sources do not carry it |
| `EMBEDDING__TOKENIZER_MODEL` and `EMBEDDING__TOKENIZER_REVISION` | They set the Markdown token budget, so chunk boundaries move |
| The **resolved** Markdown splitter | Model-token-aware or legacy fallback. The resolved value is recorded, not the configured one, so a corpus chunked under the fallback does not stay "matching" forever once the tokenizer becomes loadable |
| `OCR_FALLBACK_ENABLED` | It decides which reader produced the text |
| `OCR_ROUTING_UNIT` and the blank-page test | They decide which engine reads each page; recorded for every source |
| The resolved OCR route fingerprints (the first two engines; a third engine and later add their own) | Availability, protocol version, every package and exact version, pipeline identity and revision, model identity and revision, output-schema identity and version, and backend identifier |
| `OCR_SKIP_BLANK_PAGES` (only when `false`) | Off, no flagged page is dropped as blank, so PDF text can change. The PDF `parser` block gains `skip_blank_pages: false`. Turning it off re-indexes PDF sources only. The default (`true`) adds nothing, so no digest moves on upgrade |
| `OCR_MATHS_ROUTING_ENABLED` and the detector version | They decide whether maths pages reach OCR; recorded for every source |
| `OCR_NON_LATIN_ROUTING` (when not `off`) and its detector version | They decide which flagged pages skip the local tier; recorded for PDF sources only |
| `OCR_LOCAL_BACKENDS`, `OCR_LOCAL_CUTS` and the resolved local model | The `parser` block of PDF sources names each listed backend in list order with its effective cut and its resolved model identity. This holds for the default list too. Only effective cuts count, so an entry equal to the default cut gives the same digest as no entry. A cut change, from the environment, `omrs.jsonc`, the Settings page or a Read document step, reads PDF sources again. Markdown and code sources keep their digest |
| `READING_PART_OPTIONS` (identity options of parts in use) | Adds `parser.reading_part_options` for PDF sources. An empty map adds nothing |

Two consequences worth planning for:

1. **Provisioning either of the first two engines changes identity for previously indexed
   sources, including non-PDF sources.** Both route fingerprints belong
   to the shared identity payload. A list of one engine gives the same
   payload for the second engine as an empty fallback does. A previously unavailable route
   becoming available causes re-ingestion, including when it is the
   second route. Package, model, pipeline, protocol and output-schema
   changes have the same effect. Provision the required engines before
   building the corpus, or plan for re-ingestion.
2. **`EMBEDDING__QUERY_INSTRUCTION` deliberately does NOT count.** It
   changes query vectors only, never stored ones, so it is excluded from
   the identity on purpose. Set it, change it, or clear it freely: a
   byte-identical source still reports `skipped_unchanged`.

Transient process details — process ids, temporary paths, timings — are
excluded from the fingerprint. A missing, unusable, malformed, or
incompatible worker collapses to ONE stable unavailable fingerprint, so
"the worker is not installed" is a single identity rather than a
different one for every failure mode.

## How settings reach the code

Worth understanding if you are changing anything.

`config/` works out the values and produces a `Settings` object. It builds
nothing else.

`compose.py` takes those settings and constructs the real objects — embedder,
vector store, reranker. It is the only place that calls `get_settings()`.

Core operations receive a frozen `EffectiveSettings` as an argument. There is
no global to read and nothing to patch. Two searches running at once each hold
their own settings.

For tests, this means injecting rather than patching:

```python
def test_something(effective_settings):
    settings = effective_settings(top_k=20)
    results = search("query", effective_settings=settings)
```

More in [Architecture](architecture.md) and
[ADR-031](../adr/031-three-layer-config-compose-di.md).

---

## Adding a setting

**Belongs to one area** (chunking, ingestion, retrieval, metadata):

1. Add the field to that area's `settings.py`
2. Add it to `defaults.yaml` under the matching block

**Cross-cutting:**

1. Add the field to `Settings` in `config/__init__.py`
2. Add it to `defaults.yaml` at the top level

A test checks `defaults.yaml` agrees with the model defaults, so the two cannot
drift apart. If they disagree, that test tells you.
