# How this project is put together

This is the map. If you are trying to work out where something lives, or why a
change you made had no effect, start here.

For _why_ a particular technology was chosen, see [Technology choices](#technology-choices)
at the end. For the full reasoning behind any of it, see [`docs/adr/`](../adr/).

The principle that shapes everything: **it runs on your machine**. Cloud
providers are opt-in, never required, and everything degrades back to local if
they are missing.

---

## The one-paragraph version

There is a **core** that does the actual work — reading files, chunking,
embedding, searching. There are **transports** that expose that work to the
outside world: an MCP server and a CLI. There is a **composition root** that
builds all the objects and hands them to the core. And there is **config**,
which works out what the settings are.

The rule that makes it hold together: **core never reaches out**. It does not
read global settings, does not build its own database connection, does not know
a CLI exists. Everything it needs arrives as a function argument.

---

## The four layers

```
transports/          MCP server, CLI. Thin. No business logic.
    │                Calls into core, formats the answer.
    ▼
compose.py           Builds everything: embedder, vector store, reranker,
    │                profile resolver. The ONLY place objects are constructed.
    ▼
core/                The actual work. Receives what it needs as arguments.
    │                Never imports transports. Never reads a global.
    ▼
config/              Works out what the settings are. Reads nothing else.
                     Builds nothing.
```

Two supporting folders sit off to the side:

- `integrations/` — wrappers around outside tools: Azure Document
  Intelligence, Magika, the PDF readers. Leaf modules.
- `daemon/` — the file watcher, a long-running process rather than a
  request/response transport.

These boundaries are not a convention you have to remember. `uv run lint-imports`
checks them, and the build fails if you cross one.

---

## Settings: the part that confuses everyone

Settings can come from five places. Each beats the one above it:

```
1. Model defaults          in the code, last resort
2. defaults.yaml           project-wide, committed, shared by everyone
3. profile YAML            per collection (documents / codebase)
4. .env                    your machine, your secrets
5. environment variables   highest priority, wins over everything
```

### Which one should you use?

| You want to change                     | Put it in               |
| -------------------------------------- | ----------------------- |
| A sensible default for everyone        | `defaults.yaml`         |
| A token, a URL, a path on your machine | `.env`                  |
| How _one collection_ behaves           | its profile YAML        |
| Something for a single command         | an environment variable |

**The trap.** `.env` beats profiles. Put `RETRIEVAL__TOP_K=5` in `.env` and
every profile returns 5 results regardless of what its YAML says. Profiles stop
working and nothing warns you. Keep tuning out of `.env`.

### The five levers profiles own

Profiles do not set everything. They set five things and inherit the rest:

- `retrieval.top_k`
- `retrieval.rerank_enabled`
- `retrieval.hybrid_enabled`
- `chunking.strategy_fallback`
- `metadata.taxonomy_mode`

Anything else — chunk size, storage path, which embedding model — is shared
across all profiles.

### Variable names

Settings that belong to one area are nested. The environment variable uses a
double underscore:

```
retrieval.top_k             →  RETRIEVAL__TOP_K
chunking.chunk_size         →  CHUNKING__CHUNK_SIZE
ingestion.embed_batch_size  →  INGESTION__EMBED_BATCH_SIZE
metadata.extraction_mode    →  METADATA__EXTRACTION_MODE
```

Cross-cutting settings stay flat: `EMBED_MODEL`, `CHROMA_PERSIST_DIR`,
`VECTOR_STORE`, `LANCEDB_URI`, `RAG_PROFILE`, `PDF_READERS`, and all
credentials.

Use a pre-v2 name like `TOP_K` and the app refuses to start, telling you the
replacement. It does not quietly ignore you. Full table in
[ADR-037](../adr/037-architecture-v2-conformance.md).

---

## What each piece actually does

### `config/` — works out the settings

Reads the five sources above and produces one `Settings` object holding the
final answers.

That is all it does. It builds no objects, opens no connections, calls no
models. It is a leaf: it must not import business logic from `core/`.

This matters more than it sounds. "Is LiteParse installed?" is not a setting —
it is a question about the world. Those checks live in `compose.py`. Keeping
them in config is what made config depend on retrieval, which inverted the
whole dependency direction.

- `config/__init__.py` — the `Settings` model and the resolver
- `config/sources.py` — reads `defaults.yaml` and the profile bundles
- `config/legacy.py` — catches pre-v2 names and explains the rename

### `compose.py` — builds the objects

Takes the settings and constructs the real things: the embedding model, the
vector store, the reranker, the profile resolver.

It is the only place allowed to do this, and the only place that calls
`get_settings()`. Everything else is handed what it needs.

Why one place: before the v2 work, objects were built in a dozen scattered
spots, all reading one shared global. That is how you end up unable to run two
configurations at once.

The composition root is split by concern. `compose.py` is the entry point.
`compose_settings.py`, `compose_engine.py` and `compose_answer.py` build the
settings, the Engine and the answer models. `compose_pipelines.py` builds the
operation catalogue and plans graph runs for one Engine.
`pipeline_templates.py` publishes the canonical graphs. These modules sit at
the top level because they import more than one domain.

**Answer reasoning and usage** (ADR-093). The core answer seam stays "prompt
in, whole reply text out". `engine_answer.py` keeps one `CompletionLedger` for
each answer request beside the seam:

1. `server_seam()` calls the model and returns the reply text.
2. It passes the raw provider reply to the provider's `read_reply`, found
   through `core/providers/llm/registry.reply_reader()`.
3. It adds the result (`ReplyFacts`) to the ledger. The judge seam adds to the
   same ledger, for usage only.
4. `Engine.answer` adds `usage` and `reasoning` to the result after synthesis.

A user-profile answer runs a pipeline graph. Core cannot take a ledger there,
so `engine_profiles.answer` sets the ledger as the active ledger of the task
(`collecting()`). `graph_host` wraps the `answer_llm` and `verify_llm`
resources so each call records into it. A raw `Engine.run_pipeline` call sets
no ledger and records nothing. A client-sampled answer has no ledger, because
OMRS cannot see the client's model.

### `core/` — does the work

| Folder             | Job                                                                                        |
| ------------------ | ------------------------------------------------------------------------------------------ |
| `core/ingestion/`  | Read files, chunk them, write to the store                                                 |
| `core/retrieval/`  | Search, rerank, fuse results                                                               |
| `core/chunking/`   | The chunking strategies: code, markdown, sentence, config                                  |
| `core/metadata/`   | Work out a category and keywords for a document                                            |
| `core/vectordb/`   | The database interface, LanceDB default implementation, and optional Chroma implementation |
| `core/profiles/`   | Resolve which profile a collection uses                                                    |
| `core/providers/`  | Build embedding and LLM clients                                                            |
| `core/codebase/`   | Codebase map and code graph                                                                |
| `core/documents/`  | Document similarity graph                                                                  |
| `core/community/`  | Community-detection strategies for both graphs (Louvain default, Leiden optional)          |
| `core/answer/`     | Answer from retrieved evidence: synthesis, citations and optional claim checks             |
| `core/pipelines/`  | Graph contracts, operation catalogue, validation, admission and the graph runner           |
| `core/workspace/`  | Workspace records, the repository contract and the local run service                       |
| `core/settings.py` | `EffectiveSettings` — the frozen settings object passed around                             |

`core/ingestion/` and `core/retrieval/` do not import each other. They share
only settings.

`core/codebase/` receives its context explicitly. `build_codebase_map` and
`get_codebase_map_text` take `settings=` and `store=` keywords. The map passes
the settings to detection, community detection, both document-graph builds,
and the cache. `store=None` gives a map with no document communities; it never
reads a default store. `get_codebase_map_text` is the documented boundary that
resolves default settings when a caller omits them. The MCP tool supplies both
values. `FileInventory` and `CodebaseMap` live in `core/codebase/models.py`, so
`cache.py` and `codebase_map.py` import in any order.

### Pipeline graphs: who owns what

A pipeline graph connects registered operations. The graph code is split so
that the runner knows no domain, and each domain owns its own operations.

| Module | Owns |
| --- | --- |
| `core/pipelines/` | Graph documents, port types, the operation catalogue, preflight, admission, the scheduler, cancellation, events and results. It imports no domain package. |
| `core/ingestion/graph_adapters*.py` | Sources, Read, Prepare text and Embed / commit operations. `graph_adapters_catalogue.py` holds the canonical ingestion graph. |
| `core/ingestion/graph_fingerprint.py` | Index-shaping identity of an ingestion graph. |
| `core/ingestion/sources.py`, `core/ingestion/commit.py` | Per-source seams and the protected commit that `ingest_path_async` and the adapters share. |
| `core/retrieval/graph_adapters*.py` | Retrieve, Combine, Select and Context operations. |
| `core/retrieval/operations.py` | Sizing, rerank policy, filtering and fallback rules that `search()` and the adapters share. |
| `core/answer/graph_adapters.py` | Answer and Verify operations. |
| `core/answer/stages.py`, `core/answer/results.py` | Evidence, synthesis, citation and verification stages, and the result shapes, that `answer()` and the adapters share. |
| `core/workspace/` | Workspace records, the repository contract and the local run service. It imports no web framework and no SQLite. |
| `compose_pipelines.py` | Builds the catalogue from the three domain registrars, describes the Engine to preflight, plans runs and leases Engine resources. |
| `pipeline_templates.py` | The canonical `ingestion`, `search` and `answer` graphs. |

Each adapter calls the same function as the standard operation. There is no
second copy of ranking, the ÷30 threshold transform, chunking or source
replacement. The standard `ingest`, `search` and `answer` paths keep their
signatures, defaults and return shapes. The canonical templates reproduce
them on recorded fixtures. See [Pipeline graphs](pipelines.md).

### Stable source and chunk lineage

`core/ingestion/source_state.py` is the single identity seam
([ADR-052](../adr/052-stable-source-chunk-lineage.md)). For every production
source it derives and stamps:

- `source_id` = `"src_" + SHA-256("file\0" + canonical absolute path)`.
  Stable while the file is edited in place, new after a move or copy, and
  identical across collections.
- `source_content_hash` = SHA-256 of the original file bytes. There is no
  `document_hash` alias.
- `source_version` = SHA-256 over `source_content_hash` + NUL +
  `source_index_identity`.
- `chunk_id` = `"chk_" + SHA-256(source_id + NUL + source_version + NUL +
  decimal index + NUL + text hash)` over the text-only chunk content.
- the vector row ID = SHA-256 over `source_id` + NUL + `source_attempt` + NUL
  + `chunk_id`. It stays attempt-specific so candidate and durable attempts
    coexist until replacement is verified (ADR-048). A stable `chunk_id` is
    never a store primary key.

`pipeline.py` builds `source_id` once per source and runs a compatibility
guard before any mutation: rows for a canonical path that lack or disagree on
`source_id` fail ingestion with a rebuild instruction. No migration, alias,
or dual write exists. Listing, deletion preview, and path deletion derive the
same `source_id` through one shared path rule. Retrieval reads lineage as
plain metadata keys (`LINEAGE_METADATA_KEYS` in
`src/omrs/core/retrieval/dense.py`) and never imports the ingestion layer.

### `core/vectordb/` — the store boundary

Two stores sit behind the `VectorStore` ABC (ADR-034): `lancedb`, the
base-install default, and `chroma`, an explicit optional extra selected with
`VECTOR_STORE` (ADR-049).

`core/vectordb/chroma/store.py` is the single module that imports `chromadb` and
the single construction site for both deployments. Local mode builds a
`PersistentClient` over the resolved persist directory; cloud mode builds
and validates a `CloudClient`, with a heartbeat round trip so
authentication, network, and tenant/database mistakes surface at startup.
Following upstream LlamaIndex's client-construction/VectorStore split, the
constructed client is injected into `ChromaVectorStore`, which stays
deployment-agnostic.

`core/vectordb/lancedb/store.py` is the LanceDB implementation (ADR-046): one
`lancedb.connect(uri)` connection backs the store, and each RAG collection
maps to one LanceDB table. Table creation is lazy — the vector dimension
locks on first write — and the LlamaIndex adapter is constructed with
`mode="create"` so it can never overwrite a populated table (the adapter's
default mode is `"overwrite"`). The adapter prints to stdout when it
creates a table, so writes run with stdout redirected: stdout is the MCP
protocol channel.

Collection metadata records the embedding configuration that owns the
vector space: `rag_embed_provider`, `rag_embed_model`, and
`rag_index_identity`. Vector dimensions alone cannot prove compatibility,
so a model swap, of the same or a different dimension, is rejected before any
embedding, write or query (`check_embedding_identity` is the read-only check).
Stamping is read-merge-write: Chroma's `modify(metadata=...)` replaces the
complete map, so existing profile tags are read and merged first. The
LanceDB store keeps the same triple in each table's durable Arrow schema
metadata, merged through pylance's `update_schema_metadata`.

Each backend has its own folder: `core/vectordb/lancedb/` and
`core/vectordb/chroma/`. The modules shared by every backend stay at the
`core/vectordb/` root, and `tests/unit/test_folder_layout.py` fails when
backend code lands there. Supporting modules keep each store under the
500-line ceiling:

- `core/vectordb/identity.py` — the `EmbeddingIdentity` type and the
  `IdentityGuardMixin` (stamping plus write/query-path mismatch rejection)
- `core/vectordb/chroma/paged.py` — the `PagedReadMixin` (bounded and bulk
  collection reads, formerly `chroma_utils.py`)
- `core/vectordb/naming.py` — deterministic experiment collection names
  (e.g. `exp14-qasper-openrouter-qwen3-8b-liteparse-cs512-co100`)
- `core/vectordb/lancedb/meta.py` — the LanceDB table-metadata seam and its
  identity guard, reusing `identity.py`'s pure helpers, plus the metadata
  struct evolution that grows a table's Arrow struct when later writes
  introduce new metadata keys
- `core/vectordb/lancedb/filter.py` — ChromaDB `where` dict → LanceDB filter
  translation through the `lancedb.expr` value serialiser; operators are
  null-aware and schema-absent fields fold to constants, preserving
  ChromaDB missing-field semantics across backends
- `core/vectordb/lancedb/paged.py` — the LanceDB paged-read mixin (scanner
  pages plus `strip_internal_metadata`)
- `core/vectordb/lancedb/fts.py` — the native full-text-search seam: additive
  FTS index lifecycle, native sparse queries, coverage diagnostics, and the
  capability probe
- `core/vectordb/validation.py` — the fail-closed embedding write contract
  (`validate_embedding_batch` and
  `materialise_and_validate_node_embeddings`), shared by every backend
- `core/vectordb/registry.py` — lazy vector-store registry mapping
  `VECTOR_STORE` names to factories (`chroma`, `lancedb`)

Every store write is fail-closed
([ADR-051](../adr/051-fail-closed-embedding-write-contract.md)). Each
adapter validates the complete embedding batch immediately before its
backend mutation: `write_nodes` embeds missing nodes and validates the
whole batch first, and `upsert_precomputed` validates caller-computed
vectors first. A rejected batch never reaches the SDK, never persists a
subset, and never advances the generation counter. Every failure names the
collection, the embedding provider/model, and each affected identifier —
direct `upsert_precomputed` callers must pass `embedding_identity` so the
diagnostic is always available. `get_collection_dimension` discovers an
existing collection's vector width without creating backend state (one
stored embedding on ChromaDB; the Arrow schema width on LanceDB), so
dimension conflicts are rejected before any write. The validator never
normalises, truncates, or repairs vectors; norm policy is enforced
separately by the embedding norm guard ([ADR-053](../adr/053-embedding-norm-guard.md)).

`compose.build_vector_store` resolves the configured name through the
registry instead of branching over it. Each factory receives the resolved
settings; the Chroma factory consumes mode, persist directory, API key,
tenant, and database, and the LanceDB factory consumes the `LANCEDB_URI`
parent directory. Each registry entry declares its availability metadata:
required packages, optional extra, installation guidance, sparse capability,
and storage-summary resolver. An unregistered `VECTOR_STORE` name fails
startup listing the registered names. Credentials never enter
`EffectiveSettings`, profiles, YAML defaults, or operation-level objects.

`get_default_store()` returns only the instance installed by
`compose.ensure_runtime_setup`. Before composition it raises a controlled
error. It never imports settings or constructs a fallback store.

One writer per collection is an explicit boundary. BM25 cache validity uses
the store's durable data version where one exists
([ADR-056](../adr/056-lineage-navigation-replaces-a-document-store.md)), so
a mutation by another process — the watch daemon writing while the MCP
server serves — invalidates the cache without inter-process signalling.
Where no durable version exists, the process-local generation counter
applies and same-process mutations are the only ones the cache sees;
evaluation workers reuse completed immutable indexes read-only either way.
Cross-process write safety of the underlying stores remains unverified.

**Layout and concurrency contract.** Each LanceDB collection is one table
directory, `{LANCEDB_URI}/{collection_name}.lance`. A regression test pins
this layout against a real temporary store (`TestNativeLayoutPin`); it
asserts layout only and says nothing about concurrency. Collection names are
validated as non-empty single path components at the adapter's table-access
boundary (`core/vectordb/lancedb/table_name.py`); Chroma name validation stays
deferred with the per-directory scope. Three layers stay distinct: the
process-global ingestion mutation lock (`write_lock` in
`core/ingestion/_state.py`) serialises mutations across all collections
within one process; the physical `.lance` layout; and cross-process write
safety, which is unverified for both backends. No registration in
`core/vectordb/registry.py` sets `cross_process_writes_safe`. Operator
detail: [Configuration](configuration.md#storage-layout-and-concurrency);
specification: `openspec/changes/add-per-collection-persist-dirs/`.

### `transports/` — exposes it

- `transports/mcp/` — the MCP server, nine tools, over stdio (split by tool)
- `transports/cli/` — the `omrs` command, one file per command group
- `transports/api/`: the optional local web runtime (`omrs web`). It is a
  FastAPI application with the `web` extra. Its routes call the Engine and
  the workspace run service. It holds no ranking, chunking or graph logic.
  The base install does not import it.

Transports hold no business logic. They resolve a profile, call core, format
the answer.

---

## How a search actually flows

```
MCP client asks for a search
      │
      ▼
transports/mcp/          works out which profile this collection uses
      │                  → EffectiveSettings (frozen)
      ▼
core/retrieval/pipeline  resolves settings ONCE here, at the boundary.
      │                  Everything below gets them as an argument.
      ├─→ dense.py       embedding search
      ├─→ sparse_dispatch.py sparse backend: bm25 (sparse.py) or
      │                      native (native_sparse.py); if hybrid is on
      ├─→ fusion.py      merge the two rankings
      ├─→ policy.py      decide whether to rerank
      └─→ reranker.py    re-score with the cross-encoder
      │
      ▼
results back to the client
```

The settings object is frozen. Two searches running at once each hold their own
copy; neither can affect the other. That is the whole point of passing it as an
argument instead of reading a global.

---

## Adding things

### A new chunking strategy

1. Write `core/chunking/<name>.py`
2. Add one line to `core/chunking/registry.py`:

```python
register("mystrategy", "omrs.core.chunking.mystrategy:chunk_my_file_async")
```

That is the whole job. No other file changes. Same pattern for metadata
backends and retrieval stages.

This is enforced, not just encouraged. One test fails if a dispatch module
imports a strategy directly; another fails if it branches on strategy names.

### Community strategies

Community detection follows the same pattern, with one addition: the
strategies live in `core/community/`, and both graph consumers (the codebase
code graph and the document similarity graph) dispatch through
`partition_graph` with an injected seed.

The shared contract is flat: `list[set[Hashable]]`, every node in exactly one
non-empty community. Algorithm-specific objects (igraph partitions, leidenalg
results) never cross the boundary. Graphs with fewer than five nodes bypass
partitioning entirely. No LLM is called anywhere in the pipeline, and the
default seed of `0` keeps partitions deterministic run to run.

### A new vector database

Implement `VectorStore` from `core/vectordb/base.py`, add one `register()`
line to `core/vectordb/registry.py`, and let `compose.build_vector_store`
resolve it by name — never a branch over the name (invariant #10).
Put the backend in its own folder (`core/vectordb/<name>/`). ChromaDB is
confined to `core/vectordb/chroma/store.py` and `core/vectordb/chroma/cloud.py`;
LanceDB is confined to `core/vectordb/lancedb/store.py`,
`core/vectordb/lancedb/literal.py` and `core/vectordb/lancedb/fts.py`.
Contracts fail the build if either library is imported anywhere else.

### OCR engines and maths routing

OCR engines live outside the OMRS environment:

```text
ocr-workers/
  core/                  shared protocol, validation, framing and engine contract
  engines/dots-mocr/     default first engine, isolated PyTorch environment
  engines/paddleocr-vl/  default second engine, isolated Paddle environment
  provision.py           provisions one named engine from its lockfile
```

Each engine registers exactly one `omrs.ocr_engine` entry point in its
own environment. The shared core reports unavailable when it finds zero
or multiple engines. The host resolves engine folders by name without
branching on engine names. See the
[add-an-engine checklist](../../ocr-workers/README.md#add-an-engine).

`capabilities.build_ocr_routes` constructs an `OcrRoutes` tuple from
injected settings, one route for each engine in `OCR_ENGINES`. The default
list is `dots-mocr, paddleocr-vl`. `OCR_WORKERS_DIR`
locates the engine projects. Each route resolves from the folder and the
engine name only; the explicit `OCR_WORKER_COMMAND` override was removed
(ADR-105). See [migration](ingestion.md#provision-the-engines).

Before each worker dispatch, `OcrRoutes.select()` chooses the first
available engine of the list. If none is available, flagged pages
keep native text and count unresolved. A post-dispatch failure remains a
per-file error without a cross-route retry. Each client starts its parsing
subprocess lazily. Identical commands and working directories share a
client; owner shutdown closes each distinct client. The timeout grows
with requested page count, with `OCR_WORKER_REQUEST_TIMEOUT` as its floor.

`integrations/pdf/maths_pages.py` reads font resources using `pypdf`.
Its closed, versioned font list includes maths fonts with Unicode maps.
`maths_routing.py` keeps the routing decisions outside the reader wrapper:

- Maths pages skip local OCR and join locally escalated pages in one
  worker request. Unresolved maths pages keep native text.

`OCR_MATHS_ROUTING_ENABLED=false` disables maths routing, and the master
`OCR_FALLBACK_ENABLED=false` disables all OCR routing. The answering
fingerprint supplies `ocr_backend`; documents with several text producers
report `mixed`. The scalar `pages_maths_font` stays out of embedding and
language-model metadata text.

Source identity includes the routing payload `{enabled, routing_unit,
blank_page_test, local_tier}`, both route fingerprints and the maths block
`{enabled, detector_version}` for every source. The page-source counts are
excluded. Identity schema 7 reindexes every existing source once on its
next ingest.

The dots-mocr engine needs explicit model-licence acceptance. It checks
model-code hashes before loading and parses offline. Experiment 37 measured
a peak of about 22 GiB of Apple Silicon GPU memory through Metal
Performance Shaders (MPS) over 257 pages; one-page smoke tests showed
only 7–9.5 GiB. CPU execution is slower. Operators with limited memory
can put `paddleocr-vl` first in `OCR_ENGINES`. Neither runtime enters the
OMRS base environment. `OMRS_OCR_MODEL_CACHE` can keep per-engine weights
outside worktrees.

### Local model runtimes

OMRS owns the local `llama-server` processes. Chat, embeddings and OCR
engines are clients of a runtime. They do not start or stop one
([ADR-109](../adr/109-omrs-owns-local-model-runtimes-components-are-clients.md)).

One manager does this for every OMRS process: `omrs web`, the CLI, the stdio
MCP server and the watcher. It lives in `integrations/llamacpp_runtime/`:

| Module       | Job                                                                                   |
| ------------ | ------------------------------------------------------------------------------------- |
| `rules.py`   | Launch checks: program, model, loopback port, argument lists, child environment, fixed reasons |
| `spec.py`    | `RuntimeSpec`: id, role, mode, binary, arguments, declared files, build, port policy, slots |
| `state.py`   | The state folder and the atomic read and write of `server.json`                       |
| `locks.py`   | `flock` helpers for the lock files                                                    |
| `process.py` | Detached start, build and file checks, command-line check, stop                       |
| `manager.py` | `RuntimeManager` (one per process) and `RuntimeLease` (one per runtime per process)   |

The code is synchronous and uses threads, so the CLI and the watcher need no
event loop. The web routes call it through `run_in_threadpool`.

**Roles and modes.** The runtime ids are `chat`, `embeddings` and
`ocr-<engine folder>`. Each role is `external` (you run the server and give
a URL) or `managed` (OMRS starts or adopts it). Chat and embeddings default
to `external`. An OCR runtime is managed unless `ocr_runtime_url` is set.

**Where it sits in the import contracts.** The manager is an integration, so
`integrations-are-leaves` applies: it does not import `core`, `transports` or
`daemon`. `compose.py` builds one `RuntimeManager` per process. It hands a
lease to the llama.cpp Chat, classification and embedding clients in `core/`
by injection. `core/` never imports the package. The field list for the
llama.cpp card (`LLAMACPP_SERVER_FIELDS`) stays in
`core/providers/llm/llamacpp_rules.py` because it is settings data.
`transports/api/llamacpp_server.py` is a thin adapter: it keeps the web
lifespan hook and maps the manager's status to the route body.

**State folder.** Each runtime has `<state root>/runtimes/<runtime id>/`. The
state root is `OMRS_STATE_DIR`, else `$XDG_STATE_HOME/omrs`, else
`~/.local/state/omrs`. It must be on a local disk. Every OMRS process writes
there. It holds no settings and no secrets. The folder holds:

- `start.lock`: held exclusive while one process decides to adopt, start or
  stop the server.
- `clients.lock`: held shared by every process that uses the runtime.
- `request.lock`: held exclusive for one request on a one-slot runtime.
- `server.json`: pid, port, binary path, argument digest, build, state,
  `stopped_by`, generation and the last failure reason.
- `server.log`: the server output.

**The lease.** A process joins a runtime on its first request. It takes a
shared lock on `clients.lock`, then `start.lock`, then reads `server.json`.
It adopts a live server that has the same binary and arguments. Otherwise it
starts one. When a process leaves (idle stop, close or exit), it drops its
shared lock and tries an exclusive, non-blocking lock on `clients.lock`. If
that works, no other client exists, and it stops the server. The kernel frees
a lock when its process dies, so a killed process never blocks the others.

**Lock order rule.** A process blocks on `clients.lock` only while it holds no
other lock. While it holds `start.lock`, it makes only non-blocking attempts
on `clients.lock`. No wait cycle can form.

**Stale rule.** A server is stale only when its pid is gone or its command
line does not hold the recorded binary path. A slow `/health` answer, a 503
or a long request never makes a server stale. `/health` is read during a
start only.

**Idle stop and exit.** A runtime with no request for 10 minutes stops. This
is a fixed constant (`IDLE_STOP_SECONDS = 600`), not a setting. OMRS does not
pass `--sleep-idle-seconds` to `llama-server`. After SIGKILL of the last
client, an orphan server can stay up. The next OMRS process adopts it, and
`omrs web` stops it at start-up when no process uses it.

**OCR engines.** An engine declares its server in `[tool.omrs-ocr.runtime]`
in its `pyproject.toml`. The host reads the block through
`integrations/ocr_worker/manifest.py` (standard library only), starts or
adopts the runtime, and gives the worker its address in
`OMRS_OCR_RUNTIME_URL`. The host never names an engine. See the
[runtime block](../../ocr-workers/README.md#runtime-block). A one-slot
runtime serialises requests across processes with `request.lock`.

Operator detail, including the failure reasons:
[Configuration](configuration.md#local-llamacpp-server).

### A new setting

- Belongs to one area? Add it to that area's `settings.py`
  (`core/retrieval/settings.py`, and so on), then to `defaults.yaml` under the
  matching block.
- Cross-cutting? Add it to `Settings` in `config/__init__.py` and to
  `defaults.yaml` at the top level.

A test checks the two agree, so they cannot drift apart.

---

## Registry eligibility and audit inventory

A module goes into a registry when configuration selects by name among two or
more interchangeable implementations that share one contract. That is the
whole rule. A single capability adapter does not need a registry just because
it lives under `integrations/`. An ordered fallback factory does not either.

Native versus optional is an availability property, independent of registry
eligibility. A base-install implementation still registers when it belongs to
a configured strategy family (Louvain registers next to Leiden; pypdf
registers next to liteparse and pypdfium2). An optional adapter with no named
peers stays an integration.

### Integration inventory

Every Python module under `src/omrs/integrations/`, classified. A contract
test fails when a module is missing from this table.

<!-- integration-inventory:start count=66 -->

| Module                                   | Availability                                                   | Selector                                                            | Shared contract                               | Fallback owner                                                                    | Disposition                                                         |
| ---------------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `omrs.integrations`                   | Native                                                         | None                                                                | Package facade                                | None                                                                              | Facade; exports stable integration APIs only                        |
| `omrs.integrations.azure`             | Optional `azure` extra                                         | `DOCUMENT_BACKEND=azure`, via `core/ingestion/backends/registry.py` | Async document read into LlamaIndex Documents | `core/ingestion/backends/orchestrator.py` (retry budget, then one local fallback) | Registered strategy behind the document-backend registry            |
| `omrs.integrations.leidenalg`         | Optional `community-leiden` extra                              | `COMMUNITY_ALGORITHM=leiden`, via `core/community/registry.py`      | Flat partition callable                       | None; explicit selection fails startup                                            | External adapter behind the community registry                      |
| `omrs.integrations.magika`            | Optional executable                                            | `MAGIKA_BINARY` selects the binary path, not an implementation      | `FileEntry` detection results                 | `core/codebase/codebase_map.py` suffix detection                                  | Capability integration; remains unregistered                        |
| `omrs.integrations.ocr_worker`        | Native                                                         | None                                                                | `OcrWorkerClient` and protocol types          | None                                                                              | Facade; exports the worker client and protocol types                |
| `omrs.integrations.ocr_worker.client` | Native                                                         | `OCR_FALLBACK_ENABLED` and resolved route command                  | JSON Lines request/response client            | `integrations/pdf/ocr_routing.py` before dispatch                                 | Subprocess capability adapter; injected into core                   |
| `omrs.integrations.ocr_worker.dispatch` | Native | Resolved routes in list order | `RoutedClient`: sends a parse to the first available route and, after an operator stop of its runtime, once to the next available route | Unavailable before dispatch goes to the next route; no retry after dispatch | Never sends one request twice to the same route |
| `omrs.integrations.ocr_worker.fingerprint` | Native                                                      | Resolved route command with `--capabilities`                       | Frozen `OcrWorkerFingerprint`                 | Stable unavailable fingerprint                                                     | Capability probe; invalid probes have one stable identity           |
| `omrs.integrations.ocr_worker.managed` | Native                                                         | `OCR_FALLBACK_ENABLED` and resolved route command                  | Owner-scoped `ManagedOcrClient` lifecycle     | `capabilities.build_ocr_routes` unavailable path                                   | Composition-boundary wrapper; injected into core                    |
| `omrs.integrations.ocr_worker.manifest` | Native | Engine `pyproject.toml` `[tool.omrs-ocr]` | Parsed manifest, licence gate and not-provisioned reason | Minimal TOML reader before Python 3.11 | Standard-library helper; `ocr-workers/provision.py` loads it by file path |
| `omrs.integrations.ocr_worker.pool` | Native | Resolved route commands of each node and of the host | `OcrClientPool`: one lazy `ManagedOcrClient` per command, `routes(settings)` | Unavailable route when a command does not resolve | Engine-owned; one pool-wide lock serialises parsing (ADR-105) |
| `omrs.integrations.ocr_worker.protocol` | Native                                                       | None                                                                | Versioned JSON Lines envelopes                 | None                                                                              | Wire-protocol twin (1.1: optional request `pages`, response `pages_markdown`); tests keep its independent copy compatible      |
| `omrs.integrations.ocr_worker.routes` | Native | `OCR_WORKERS_DIR`, `OCR_ENGINES` | `OcrRoutes` (one route per listed engine) and `select()` | Unknown or unprovisioned engine → stable unavailable fingerprint | Resolves engines by folder name; a later engine only before dispatch; per-page timeout scaling |
| `omrs.integrations.ocr_worker.runtime` | Native | Engine `[tool.omrs-ocr.runtime]` block, `OCR_RUNTIME_URL` | Runtime spec per engine (`ocr-<engine folder>`) and lease use around one worker parse with `OMRS_OCR_RUNTIME_URL` | Runtime unavailable makes the route unavailable before dispatch | Host never names an engine; ADR-109 |
| `omrs.integrations.ocr_worker.validation` | Native                                                    | None                                                                | Protocol violation codes and payload checks    | None                                                                              | Split from `protocol.py` at the 500-line ceiling; byte-identical twin in `ocr-workers/core/` |
| `omrs.integrations.llamacpp_runtime` | Native | `LLAMACPP_CHAT_SERVER`, `LLAMACPP_EMBED_SERVER`, `OCR_RUNTIME_URL` | Facade; exports the manager, lease, spec, state and lock surface of the shared runtime manager | None | One manager for every local llama.cpp runtime; components are clients |
| `omrs.integrations.llamacpp_runtime.lease` | Native | None | `RuntimeLease` (one per runtime per process): join, `request`/`arequest`/`session`, crash restart, leave; `RuntimeUnavailable` and `RuntimeRequestFailed` | Crash restart once; none after an operator stop | Split from `manager.py` at the 500-line ceiling; holds the D4 lock order |
| `omrs.integrations.llamacpp_runtime.locks` | Native | None | `LockFile`: shared and exclusive `flock` on one descriptor each | None | Kernel locks free themselves when a process dies; `not-supported` on Windows |
| `omrs.integrations.llamacpp_runtime.manager` | Native | `LLAMACPP_CHAT_SERVER`, `LLAMACPP_EMBED_SERVER`, `OCR_RUNTIME_URL` | `RuntimeManager` (one per process): `lease`, `stop` (operator), `sweep`, `status`, `close`; `install_sigterm_exit` | None; an external runtime is never started or stopped | Injected by `compose.py`; `IDLE_STOP_SECONDS = 600`; `atexit` leave |
| `omrs.integrations.llamacpp_runtime.process` | Native | None | Detached start, build check (`--version`), SHA-256 file check, `ps` command-line check, SIGTERM/SIGKILL stop | None; a failed check gives a fixed reason | Only module that starts or stops a runtime process; no shell |
| `omrs.integrations.llamacpp_runtime.rules` | Native | None | Launch checks: program rule, model kind, loopback port, argument lists, child environment, fixed reasons | None | Moved from `core/providers/llm/llamacpp_rules.py`; standard-library only |
| `omrs.integrations.llamacpp_runtime.spec` | Native | None | Frozen `RuntimeSpec` (id, role, mode, argv, files, build, port policy, slots) | None | Chat and embeddings builders; free-port OCR runtime; no `--sleep-idle-seconds` |
| `omrs.integrations.llamacpp_runtime.state` | Native | `OMRS_STATE_DIR`, `$XDG_STATE_HOME` | `server.json` atomic read/write and the state root | Missing or broken file reads as no record | Local-disk runtime state shared by every OMRS process |
| `omrs.integrations.part_registry` | Native | None | `PartRegistry`: register, describe, names, lazy cached `get`, `probe`, import-free `installed`, per-process `switch_off` and `off_reason` | None | Shared helper for the page-reading registries (change `local-ocr-backends`, ADR-112); imports no part at module level |
| `omrs.integrations.pdf`               | Native                                                         | None                                                                | `get_pdf_reader(reader)`                      | None                                                                              | Public facade exposing the factory                                  |
| `omrs.integrations.pdf.blank_pages` | Base, via `liteparse` renders | `OCR_FALLBACK_ENABLED`, flagged pages only | `find_blank_pages` frozenset and `BLANK_PAGE_TEST_VERSION` | Render or score failure → no page blank; every page keeps its normal route | Edge-free stroke-ink blank test with a versioned threshold (change `skip-blank-pages-before-worker`) |
| `omrs.integrations.pdf.chain` | Native | `PDF_READERS` | `clean_reader_list`, `first_installed`, `tiers_after`, `rescue_pages`, `construct` | A tier that is not installed, raises or returns no text hands over to the next tier; the last tier's exception propagates; no installed reader gives pypdf | Runs the reader list: start-up choice and pdf-inspector rescue tiers; names no reader, so tiers come from the list through the registry |
| `omrs.integrations.pdf.factory`       | Native                                                         | `PDF_READER=auto`                                                   | Reader instance with `load_data`              | Factory itself (LiteParse → pypdfium2 → pypdf probe, for direct `auto` callers)   | Registry-backed factory; `auto` stays ordered capability resolution |
| `omrs.integrations.pdf.liteparse`     | Base dependency (despite the stale docstring naming an extra)  | `PDF_READER=liteparse`                                              | `load_data`                                   | `compose.resolve_pdf_reader` `auto` probe                                         | Registered reader strategy                                          |
| `omrs.integrations.pdf.local_ocr` | Native | None | Package marker for the local OCR backends | None | Imports no backend module (change `local-ocr-backends`, design D7) |
| `omrs.integrations.pdf.local_ocr.base` | Native | None | `BackendPage`, the `LocalOcrBackend` protocol, `LocalOcrPage` and `page_confidence` (character-weighted mean of line confidences) | None | Contract of a local OCR backend; a backend never decides escalation |
| `omrs.integrations.pdf.local_ocr.chain` | Native | `OCR_LOCAL_BACKENDS` in list order | `read_local_pages`: shared escalation rule with each backend's effective cut, `script_not_kept`, pass-on, first-listed text for an unresolved page | A backend that raises is skipped with one warning per process; a panic switches it off; every backend failing raises the first failure | Design D8; called by `page_routing.local_ocr` |
| `omrs.integrations.pdf.local_ocr.pp_ocrv6_small` | Base dependency (`pdf-inspector`) | `OCR_LOCAL_BACKENDS` lists `pp-ocrv6-small` (the default) | `BACKEND`: `read_pages` (`force` mode on the 1-based page list) and `identity` (one-page blank probe) | `pdf_inspector` missing → `ImportError`; engine failure raises | Built-in backend; imports `pdf_inspector` inside each method |
| `omrs.integrations.pdf.local_ocr.registry` | Native | `OCR_LOCAL_BACKENDS`, `OCR_LOCAL_MIN_CONFIDENCE` (optional override) | `PartRegistry("local OCR backend")`: `register` with cut, `calibrated_by`, `keeps_scripts` and `producer`; `effective_cut`, `listed`, `switch_off`, `off_reason` | A cut without `calibrated_by` raises `ValueError`; unknown names raise | Lazy `register()` line per built-in backend, pinned to `LOCAL_OCR_BACKENDS` descriptors |
| `omrs.integrations.pdf.maths_pages` | Base, via `pypdf` | `OCR_MATHS_ROUTING_ENABLED` | `maths_font_pages` frozenset of 1-based pages | Unreadable font resources → no pages flagged | Closed, versioned maths-font list (`MATHS_DETECTOR_VERSION`) |
| `omrs.integrations.pdf.maths_routing` | Native | `OCR_MATHS_ROUTING_ENABLED` | Maths-page detection and page split | Disabled → routing unchanged | Maths-page decisions the pdf-inspector seam calls |
| `omrs.integrations.pdf.ocr_routing`   | Native                                                         | `PDF_READER=pdf_inspector` and `OCR_FALLBACK_ENABLED`               | `OcrRoutedPdfInspector` and OCR diagnostics  | No OCR route before dispatch: flagged pages keep native text and count unresolved | Page-level routing seam around the pdf-inspector strategy           |
| `omrs.integrations.pdf.page_routing` | Base dependency (`pdf-inspector`) | `OCR_ROUTING_UNIT=page` (the default and only legal value) | `page_evidence`, `local_ocr` (delegates to `local_ocr.chain`), `resolve_local_model_identity(settings, backend)`, `local_tier_off_reason`, `merge_pages` | Full page scan raises — the page unit has no sampled evidence to fall back to | Page-unit OCR routing: per-page evidence, the local tier with its post-check, and the page-source counts; the seam emits one document per page |
| `omrs.integrations.pdf.page_rules` | Native | None | Package marker for the page rules | None | Imports no rule module (change `local-ocr-backends`, design D5) |
| `omrs.integrations.pdf.page_rules.base` | Native | None | `RuleContext`, `RuleOutcome`, the `PageRule` protocol and the `PostCheck` callable | None | Interface of a page rule; optional `post_check`, `degrade` and `stamp` hooks |
| `omrs.integrations.pdf.page_rules.blank` | Base, via `liteparse` renders | Always on, flagged pages only | `RULE`, order 10: drops the pages `blank_pages.find_blank_pages` finds | Render or score failure → no page dropped | Built-in page rule; calls the blank test through its module at call time |
| `omrs.integrations.pdf.page_rules.maths` | Base, via `pypdf` | `OCR_MATHS_ROUTING_ENABLED` | `RULE`, order 20: maths pages go direct; stamps `pages_maths_font` | Disabled → no page direct, no stamp | Built-in page rule; calls `maths_routing.detect_maths_pages` at call time |
| `omrs.integrations.pdf.page_rules.non_latin` | Native | `OCR_NON_LATIN_ROUTING` | `RULE`, order 30: direct set, `non_latin_output` post-check, degrade to the local tier, `pages_non_latin` stamp | No engine available → today's routing and one warning | Built-in page rule; calls `script_routing` at call time |
| `omrs.integrations.pdf.page_rules.pipeline` | Native | Registered page rules in ascending order | `run_rules` → `RoutingPlan` (drops, direct, local split, post-checks, degrade, stamps) | External rule that fails → skipped for the file, one warning, switched off | Four fixed semantics of design D5; a built-in rule's exception reaches the caller |
| `omrs.integrations.pdf.page_rules.registry` | Native | None | `PartRegistry("page rule")`: `register` with order and hook flags, `describe`, `available`, `ordered` | None; unknown names raise | Lazy `register()` line per built-in rule, pinned to `PAGE_RULES` descriptors |
| `omrs.integrations.pdf.pdf_inspector` | Base dependency (compatibility `pdf-inspector` extra retained) | `PDF_READER=pdf_inspector` (packaged default, ADR-050)              | `load_data`                                   | `compose.resolve_pdf_reader` missing-backend error → pypdf                        | Registered reader strategy; configuration-owned default             |
| `omrs.integrations.pdf.pypdf`         | Base, via `llama-index-readers-file`                           | `PDF_READER=pypdf`                                                  | `load_data`                                   | Terminal `auto` tier                                                              | Registered reader strategy                                          |
| `omrs.integrations.pdf.pypdfium`      | Optional `pdf-pypdfium2` extra                                 | `PDF_READER=pypdfium2`                                              | `load_data`                                   | None                                                                              | Registered reader strategy                                          |
| `omrs.integrations.pdf.registry`      | Native                                                         | `PDF_READER` concrete values                                        | Reader class with `load_data`                 | None; unknown names raise                                                         | Lazy registry for concrete PDF readers                              |
| `omrs.integrations.pdf.script_routing` | Native | `OCR_NON_LATIN_ROUTING` (`off` default, `detect`, `always`) | `is_non_latin`, `non_latin_direct_pages`, `post_check_enabled`, `non_latin_output_reason`, `output_script`; versioned detector (`SCRIPT_DETECTOR_VERSION`) and output-script rule (`OUTPUT_SCRIPT_VERSION`) | `detect` reads only existing text and finds no scanned page; no engine available → today's routing and one warning | Non-Latin page routing for the page unit; no rendering, OCR or model call |
| `omrs.integrations.tokenizer`         | Base `tokenizers` and `huggingface-hub` dependencies           | `EMBEDDING__TOKENIZER_MODEL` and `EMBEDDING__TOKENIZER_REVISION`    | `load_tokenizer(model, revision)`             | `core/chunking/model_token.py` legacy splitter                                    | Offline cache adapter; never downloads                              |
| `omrs.integrations.process_launcher`  | Native (standard library; no shell)                            | A registered and enabled external-tool plugin                       | Owned process group, private directory, loopback port | None; a used port or failed launch is refused                             | Only plugin module that starts processes; imports no `omrs.core` module |
| `omrs.integrations.keychain` | `keyring` (optional, `web` extra; imported inside functions) | System keychain for provider API keys | Provider name to key under service `omrs` | None; no keychain means unavailable and a save raises | Never falls back to a plaintext store; each call runs in a worker thread with a time limit |
| `omrs.integrations.huggingface_models` | Base (`httpx`, `huggingface-hub`; the library is imported inside functions) | None; the web model panel calls it on request | `search_models`, `list_repo_files`, `bytes_to_download`, `has_room`; `ModelHostError` with a fixed reason | None; a failed read gives `network`, `not-found` or `gated` | Reads send no token, no redirect to another host and a body limit; the download goes through `huggingface_hub` |
| `omrs.integrations.ollama_pull` | Base (`httpx`) | None; the web model panel calls it on request | `pull_model` with progress summed over layer digests; `OllamaPullError` and `PullCancelled` | None; a failed pull gives `failed` or `ollama-unreachable` | Streamed `POST /api/pull`; runs in a worker thread; no server text reaches an error |
| `omrs.integrations.workspace_sqlite`  | Native (standard-library `sqlite3`)                            | None; the web runtime composes it                                   | `core/workspace/repository.py` contract       | None                                                                              | Facade; exports `SqliteWorkspaceRepository` and schema errors       |
| `omrs.integrations.workspace_sqlite.chats` | Native (standard-library `sqlite3`) | None | Stored chats, turns and chat folders as plain dictionaries | None; a failed transaction rolls back | Chat store for the web server; imports no `omrs.core` module |
| `omrs.integrations.workspace_sqlite.experiment_library` | Native (standard-library `sqlite3`) | None | Experiment projects, user notebooks and notebook entries as plain dictionaries | None; a failed transaction rolls back | Store for the web server's experiment library; imports no `omrs.core` module |
| `omrs.integrations.workspace_sqlite.deletion` | Native (standard-library `sqlite3`)                    | Previewed workspace cleanup                                         | Finished runs and their events                | None; runs inside the caller's transaction                                        | Deletes run rows only; pipelines and revisions stay                 |
| `omrs.integrations.workspace_sqlite.pipeline_sql` | Native (standard-library `sqlite3`)                    | None                                                                | Shared pipeline and revision inserts, read and write transactions | None; a failed transaction rolls back                                 | Used by the repository and the profile store; imports no `omrs.core` module |
| `omrs.integrations.workspace_sqlite.profiles` | Native (standard-library `sqlite3`)                        | None                                                                | User profiles and the pipelines they own; a read-only catalogue | None; the catalogue opens the file read-only and never migrates it    | Profile store for the web server; catalogue for every other process |
| `omrs.integrations.workspace_sqlite.repository` | Native (standard-library `sqlite3`)                  | None                                                                | Workspace records as plain dictionaries       | None; a failed transaction rolls back                                             | Repository adapter; imports no `omrs.core` module                   |
| `omrs.integrations.workspace_sqlite.rows` | Native                                                     | None                                                                | JSON encoding and row-to-record conversion    | None                                                                              | Helper for the repository adapter                                   |
| `omrs.integrations.workspace_sqlite.schema` | Native (standard-library `sqlite3`)                      | None                                                                | Versioned migrations, backups, owner-only files | Migration rollback to the last version                                          | Application records only; never opens a vector store                |
| `omrs.integrations.workspace_sqlite.settings` | Native (standard-library `sqlite3`)                        | None                                                                | Typed web-server settings (`mcp_http_enabled`, `web_port`) | None; an invalid stored value reads as unset                  | Refuses unknown keys; imports no `omrs.core` module                 |
| `omrs.integrations.workspace_sqlite.tokens` | Native (standard-library `sqlite3`)                        | None                                                                | The one durable MCP token, stored as a SHA-256 hash | None; a failed rotation keeps the old token                    | Shows the token value once; constant-time verify                    |

<!-- integration-inventory:end -->

### Strategy-family audit

The same rule applied to every name-dispatched family, inside and outside
`integrations/`:

| Family              | Selector                                                                                                 | Live registry / factory                                             | Conclusion                                                                                                                                                       | Follow-up |
| ------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| Community detection | `COMMUNITY_ALGORITHM`                                                                                    | `core/community/registry.py`                                        | Registered in this change: `louvain` native, `leiden` optional via `integrations/leidenalg.py`                                                                   | None      |
| PDF readers         | `PDF_READERS`                                                                                            | `integrations/pdf/registry.py` behind `integrations/pdf/factory.py` | Concrete readers registered behind the unchanged `auto` factory                                                                                                  | None      |
| Chunking            | Content-type dispatch in `core/ingestion/chunker.py`; `CHUNKING__STRATEGY_FALLBACK` (default `markdown`) | `core/chunking/registry.py`                                         | Already a registry                                                                                                                                               | None      |
| Metadata extraction | `METADATA__EXTRACTION_MODE` and provider backends                                                        | `core/metadata/registry.py`                                         | Already a registry                                                                                                                                               | None      |
| Embedding providers | `EMBED_PROVIDER`                                                                                         | `core/providers/embeddings/registry.py`                             | Already a registry                                                                                                                                               | None      |
| LLM providers       | `LOCAL_BACKEND` / `CLOUD_BACKEND`                                                                        | `core/providers/llm/registry.py`                                    | Already a registry                                                                                                                                               | None      |
| Sparse retrieval    | `RETRIEVAL__HYBRID_SPARSE_BACKEND`                                                                       | `core/retrieval/sparse_registry.py` (`bm25`, `native`)              | Both concrete backends registered; `auto` stays an unregistered policy resolved at the composition boundary                                                      | None      |
| Reranking           | `RETRIEVAL__RERANK_BACKEND`, resolved by `core/retrieval/backend.py`                                     | `core/retrieval/registry.py` (`reranker_onnx`, `reranker_torch`)    | Already registered strategies                                                                                                                                    | None      |
| Vector store        | `VECTOR_STORE`                                                                                           | `core/vectordb/registry.py`                                         | `chroma` and `lancedb` registered                                                                                                                                | None      |
| Document backends   | `DOCUMENT_BACKEND`                                                                                       | `core/ingestion/backends/registry.py`                               | Registered by `register-document-backend-strategies`: `local` native, `azure` optional via `integrations/azure.py`; retry and fallback owned by the orchestrator | None      |

Live registry contents, kept in step with the code by contract tests:

<!-- registry-names:community -->

`leiden` `louvain`

<!-- /registry-names:community -->

<!-- registry-names:pdf -->

`liteparse` `pdf_inspector` `pypdf` `pypdfium2`

<!-- /registry-names:pdf -->

<!-- registry-names:chunking -->

`code` `config` `sentence`

<!-- /registry-names:chunking -->

<!-- registry-names:metadata -->

`keyword` `llamacpp` `llamaindex` `ollama` `openrouter`

<!-- /registry-names:metadata -->

<!-- registry-names:embeddings -->

`llamacpp` `ollama` `openrouter`

<!-- /registry-names:embeddings -->

<!-- registry-names:llm -->

`anthropic` `llamacpp` `ollama` `openai_compatible` `openrouter`

<!-- /registry-names:llm -->

<!-- registry-names:retrieval -->

`bm25` `dense` `fusion` `reranker_onnx` `reranker_torch`

<!-- /registry-names:retrieval -->

<!-- registry-names:sparse-backend -->

`bm25` `native`

<!-- /registry-names:sparse-backend -->

<!-- registry-names:vectordb -->

`chroma` `lancedb`

<!-- /registry-names:vectordb -->

<!-- registry-names:document-backend -->

`azure` `local`

<!-- /registry-names:document-backend -->

### Audit conclusions

- The concrete PDF readers were the one behaviour-preserving missing registry
  family. They are now registered behind the unchanged `auto` factory.
- Magika remains a capability adapter, not a strategy family: one configured
  capability, no interchangeable named peers.
- Azure and local document backends were deferred to the strict-valid follow-up
  `openspec/changes/register-document-backend-strategies/` because fallback
  ownership changes with registration. That change has now delivered the
  document-backend registry: accepted `DOCUMENT_BACKEND` names are registry-
  owned, validated at startup at the composition boundary, and the orchestrator
  owns the retry budget plus exactly one local fallback.
- Native sparse retrieval is implemented: `bm25` and `native` are registered
  in `core/retrieval/sparse_registry.py`, the LanceDB FTS lifecycle lives in
  `core/vectordb/lancedb/fts.py`, and `auto` resolves at the composition
  boundary through the store capability probe.
- Every other current family already uses a registry or a documented policy
  alias or sentinel. No migration was required for this change.

---

## The rules that are actually enforced

These are not documentation. They fail the build.

| Rule                                                               | Enforced by                                      |
| ------------------------------------------------------------------ | ------------------------------------------------ |
| ChromaDB only in `core/vectordb/chroma/`                           | `chromadb-confined-to-vectordb`                  |
| LanceDB only in `core/vectordb/lancedb/`                           | `lancedb-confined-to-vectordb`                   |
| `config/` never imports business logic                             | `config-is-leaf`                                 |
| `integrations/` never imports core or transports                   | `integrations-are-leaves`                        |
| `core/` never imports transports or providers                      | `core-business-avoids-providers-transports`      |
| `core/community/` never imports either graph consumer              | `community-strategies-independent-of-consumers`  |
| `core/pipelines/` never imports a domain package                   | `pipeline-runner-independent-of-domains`         |
| Graph adapters stay in their domain package                        | `retrieval-graph-adapters-stay-in-domain`, `ingestion-graph-adapters-stay-in-domain`, `answer-graph-adapters-stay-in-domain` |
| `core/workspace/` never imports a domain or the web runtime        | `workspace-services-independent-of-domains-and-web` |
| `core/` never imports FastAPI, Starlette, Uvicorn, marimo or SQLite | `core-free-of-web-notebook-and-sqlite-runtimes`  |
| Settings models stay pure data                                     | `settings-models-are-pure-data`                  |
| Every package covered by some contract                             | `tests/test_contract_coverage.py`                |
| No global settings reads in core                                   | `tests/test_no_global_settings_reads.py`         |
| No file over 500 lines                                             | `tests/test_file_size_ceiling.py`                |
| Dispatch goes through registries                                   | `tests/test_no_module_level_strategy_imports.py` |

Run them with `uv run lint-imports` and `uv run pytest -m "not slow"`.

One detail worth knowing: the contracts fail when a _suppression_ becomes
unnecessary. Fix a violation, forget to delete its exception, and the build
tells you. That is deliberate — see [ADR-037](../adr/037-architecture-v2-conformance.md).

---

## Technology choices

Short version. Each links to the full reasoning.

**LlamaIndex** ([ADR-002](../adr/002-adopt-llamaindex-for-rag-pipeline.md)) —
document loaders, chunkers and vector store adapters already exist, so we write
pipeline logic instead of plumbing.

**LanceDB** ([ADR-046](../adr/046-lancedb-vector-store-backend.md),
[ADR-049](../adr/0049-lancedb-default-and-chroma-isolation.md)) — the embedded
base-install default. Each collection gets its own table and files rather than
sharing one SQLite file, as Chroma does. That is a layout fact, not a write
safety claim: cross-process write safety is unverified (see the layout and
concurrency contract in the `core/vectordb/` section).

**ChromaDB** ([ADR-003](../adr/003-use-chromadb-as-vector-store.md),
[ADR-049](../adr/0049-lancedb-default-and-chroma-isolation.md)) — an explicit
optional backend. Install the `chroma` extra before setting `VECTOR_STORE=chroma`.

Vector-store selection is runtime-swappable at the deployment boundary, but
embedding-provider selection is **process/deployment scoped**, not
per-collection. The composition root assigns one LlamaIndex
`Settings.embed_model` for the process. Concurrent collections may use
different retrieval profiles and stores, but they cannot safely select
different embedding providers in the same server process. Run separate
processes for different providers until an explicit per-operation embedding
context replaces the LlamaIndex global.

**MCP** ([ADR-004](../adr/004-adopt-mcp-protocol-for-server-interface.md)) —
one server works with any MCP client, rather than a bespoke integration each
time.

**uv** ([ADR-001](../adr/001-use-uv-as-package-manager.md)) — fast, one
lockfile, no virtualenv juggling.

**ONNX Runtime for the default reranker path**
([ADR-005](../adr/005-cross-encoder-reranker-with-onnx-runtime.md),
[ADR-038](../adr/038-pluggable-reranker-backend.md)) — the default install
stays torch-free; a torch-backed reranker is available behind the `torch`
optional extra.

**qwen3-embedding:0.6b**
([ADR-009](../adr/009-switch-to-qwen3-embedding-0-6b.md)) — better retrieval
quality than nomic-embed-text, at a size that still runs locally.

**Cross-encoder reranker, off by default**
([ADR-005](../adr/005-cross-encoder-reranker-with-onnx-runtime.md),
[ADR-019](../adr/019-reranker-disabled-for-technical-workloads.md)) —
Experiment 10 found it _hurt_ results on code-heavy content by 19–27%. The
`documents` profile turns it back on, because it does help on prose.

**Deterministic graphs, no LLM**
([ADR-022](../adr/022-code-graph-via-tree-sitter-ast.md),
[ADR-023](../adr/023-document-graph-via-embedding-similarity.md)) — the code
graph comes from tree-sitter parsing, the document graph from embedding
similarity. Same input, same output, every time.

---

## Where to go next

| You want to                  | Read                                    |
| ---------------------------- | --------------------------------------- |
| Get it running               | [Getting started](getting-started.md)   |
| Change a setting             | [Configuration](configuration.md)       |
| Use the CLI                  | [CLI reference](cli-reference.md)       |
| Connect an MCP client        | [MCP client setup](mcp-client-setup.md) |
| Understand ingestion         | [Ingestion](ingestion.md)               |
| Understand reranking         | [Reranker](reranker.md)                 |
| Write tests                  | [Testing](testing.md)                   |
| Know why a decision was made | [`docs/adr/`](../adr/)                  |
