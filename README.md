<p align="center">
  <img src="web/public/omrs-logo.svg" alt="OMRS logo" width="96" height="96" />
</p>

# OMRS: Opinionated Modular RAG System

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Requires llama.cpp, Ollama, or OpenRouter](https://img.shields.io/badge/requires-llama.cpp_or_Ollama_or_OpenRouter-000000)](https://github.com/ggml-org/llama.cpp)

OMRS is a standalone, local-first retrieval framework. Point it at your files — PDFs,
Word docs, notes, papers, source code — and search them by meaning rather
than keywords.

It exposes an `Engine` API as the core product, and ships three transports
that wrap it: an [MCP](https://modelcontextprotocol.io) server, a CLI, and a
file watcher. MCP is one transport, not the product identity.

Everything runs on your machine by default. No cloud, no API keys, no
recurring costs. Cloud providers are available if you want them, never
required.

**What it is:** a retrieval framework that exposes an `Engine` API and ships
MCP, CLI, and watcher transports. Your AI assistant, your terminal, or your
own code calls the same engine.

**What it isn't:** a chatbot, a cloud service, or a replacement for your
file system. It is a search layer. Something asks it questions; it finds the
relevant passages.

---

## Library usage

```python
from omrs import Engine

engine = Engine.from_environment()
engine.ingest("./docs", collection_name="docs")
results = engine.search("query", collection_name="docs")
engine.close()
```

`Engine.from_environment()` reads `.env` and `defaults.yaml` exactly as the
transports do, so a script and the MCP server share one configuration
surface.

---

## Two jobs, one engine

The same engine handles two quite different tasks, and they want opposite
settings. You pick per collection.

|                  | Document grounding                    | Codebase context                      |
| ---------------- | ------------------------------------- | ------------------------------------- |
| For              | Papers, reports, financial statements | Source code                           |
| Profile          | `documents`                           | `codebase`                            |
| Results returned | 10                                    | 20                                    |
| Reranker         | on — improves prose                   | off — measured 19–27% _worse_ on code |
| Search           | embeddings only                       | embeddings + keyword (BM25)           |

```bash
omrs set-profile -c my_papers -p documents
omrs set-profile -c my_code   -p codebase
```

Both collections then behave correctly in the same running engine. See
[Configuration](docs/guides/configuration.md#profiles).

---

## Install

You need [uv](https://docs.astral.sh/uv/). OMRS runs one local
[llama.cpp](https://github.com/ggml-org/llama.cpp) router for every local
model, so it needs no other model server. `omrs llamacpp install` places the
pinned llama.cpp build. [Ollama](#ollama-opt-in) and
[OpenRouter](#openrouter-opt-in) are opt-in providers. `omrs web` can also set
the router and the Ollama context window (see
[Configuration](docs/guides/configuration.md#local-llamacpp-router)).

```bash
cp .env.example .env              # optional: storage and secrets only
uv sync                           # the llama.cpp backend needs no extra
uv run omrs llamacpp install      # places the pinned llama.cpp build, once
uv run omrs                       # Ctrl-C to stop
```

OMRS starts the router when a command first needs a model. It downloads the
two shipped models then: `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` for embeddings
and `Qwen/Qwen3-4B-GGUF:Q8_0` for classification. Chat has no model until you
choose one in Settings > Chat.

No output means it is working — it waits silently for MCP messages on stdin.

Then register it with your AI client: [MCP client setup](docs/guides/mcp-client-setup.md).

### What goes in `.env`

Vector-store selection and secrets.

```bash
VECTOR_STORE=lancedb
LANCEDB_URI=./lancedb
COLLECTION_NAME=documents
# plus any API keys
```

Provider, model and address settings live in `omrs.jsonc`, not in `.env`.
Run `uv run omrs config init` to write a commented starter file.

Tuning belongs in `src/omrs/config/defaults.yaml`; per-collection behaviour
belongs in a profile. Putting tuning in `.env` silently overrides your
profiles — see [Configuration](docs/guides/configuration.md) for the
precedence rules.

### Vector store and legacy data

LanceDB is the base-install default. It stores each collection under
`LANCEDB_URI`. To use Chroma, install the optional extra in a source
checkout:

```bash
uv sync --extra chroma
```

For an installed package, use `pip install "omrs[chroma]"`. Then set
`VECTOR_STORE=chroma`. CVE-2026-45829 (PYSEC-2026-311) remains active for
this optional dependency. Do not expose Chroma's Python FastAPI server
through this project.

Recognised legacy Chroma data stops default-derived LanceDB startup. Keep
it by installing the extra and explicitly setting `VECTOR_STORE=chroma`, or
explicitly set `VECTOR_STORE=lancedb` and re-ingest source files. The engine
never moves, deletes, or migrates the Chroma directory.

A store change requires re-ingestion. Before reverting after LanceDB
ingestion, set and verify `VECTOR_STORE=lancedb`. Keep that pin during the
revert. An older release can otherwise select Chroma and make LanceDB data
appear missing.

---

## Transports

### MCP server

The MCP transport exposes seven tools your AI can call:

| Tool                        | What it does                                                                           |
| --------------------------- | -------------------------------------------------------------------------------------- |
| `ingest_documents`          | Index a file or directory                                                              |
| `search_documents`          | Search by meaning, with optional reranking, hybrid search and metadata filters         |
| `list_indexed_documents`    | See what is indexed                                                                    |
| `list_collections`          | See all collections and their sizes                                                    |
| `delete_documents`          | Remove documents, or drop a collection                                                 |
| `get_codebase_map`          | Generate a compact map of a codebase: file types, code communities, architectural hubs |
| `change_collection_profile` | Switch a collection between `documents` and `codebase`                                 |

Details: [MCP tools reference](docs/guides/mcp-tools.md).

### CLI

The same `omrs` command is both the MCP server and a terminal tool.

| Command                    | What it does                          |
| -------------------------- | ------------------------------------- |
| `omrs`                  | Start the MCP server                  |
| `omrs ingest <path>`    | Index a file or directory             |
| `omrs search <query>`   | Search from the terminal              |
| `omrs list`             | List indexed documents                |
| `omrs list-collections` | List all collections                  |
| `omrs watch <dir>`      | Auto-ingest new and changed files     |
| `omrs install-login-watcher` | Install a macOS login watcher for a folder |
| `omrs delete`           | Delete documents or drop a collection |
| `omrs set-profile`      | Bind a collection to a profile        |
| `omrs benchmark`        | Benchmark embedding throughput        |
| `omrs web`              | Start the local web workspace (`web` extra) |

Every flag and example: [CLI reference](docs/guides/cli-reference.md).

### Watcher

`omrs watch` monitors a directory and auto-ingests new and changed files.
`omrs install-login-watcher` installs a macOS launch agent so the watcher
starts at login. Both delegate to the same `Engine` as the other transports.

---

## Supported files

`.pdf` `.docx` `.pptx` `.txt` `.md` `.html` `.csv`

Source code is handled too — the codebase map and code graph use tree-sitter
parsing across around 16 languages.

---

## Optional extras

**Hybrid search** — combines keyword matching with embedding search. Worth
it for exact identifiers, error codes, product names, citations. On by
default in the `codebase` profile.

```bash
uv run omrs search "What fixes MCP-1138?" --hybrid
```

### Ollama (opt-in)

Ollama is an opt-in local backend. Install it from [ollama.com](https://ollama.com),
start it, then pull one embedding model and one classification model.

```bash
ollama pull qwen3-embedding:0.6b
ollama pull qwen3:0.6b
```

Choose it in `omrs.jsonc`:

```jsonc
{
  "local_backend": "ollama",
  "embed_model": "qwen3-embedding:0.6b",
  "metadata": { "ollama_classify_model": "qwen3:0.6b" }
}
```

### OpenRouter (opt-in)

OpenRouter gives cloud embeddings or LLM calls with no local model server. It needs no extra.

```bash
uv sync
```

Chat answers can also use any OpenAI-compatible server (OpenAI, Together, vLLM, LM Studio) with no extra, or Anthropic with `uv sync --extra anthropic`. Set them in `omrs web` under Settings > Providers, or in the read-only user config folder (`~/.config/omrs/omrs.jsonc` and `secrets/<provider>.key`, also read by the CLI and the stdio server; see [Configuration](docs/guides/configuration.md#user-config-folder)). See also [Providers](docs/guides/providers.md).

```jsonc
// omrs.jsonc
{
  "embed_provider": "cloud",
  "cloud_backend": "openrouter",
  "openrouter_api_key": "env://OPENROUTER_API_KEY",
  "openrouter_embed_model": "text-embedding-3-small"
}
```

Switching embedding provider can change the vector dimension. Both supported
stores lock their collection dimension on first write. Re-ingest source
files into a fresh collection after a dimension change.

### Azure Document Intelligence (opt-in)

Azure Document Intelligence reads complex PDFs (`uv sync --extra azure`).
It is opt-in, and falls back to local parsing if unreachable.

Full setup for each: [Providers](docs/guides/providers.md).

---

## Documentation

| Guide                                                     | What is in it                                    |
| --------------------------------------------------------- | ------------------------------------------------ |
| [Getting started](docs/guides/getting-started.md)         | Install, verify, first ingest                    |
| [Configuration](docs/guides/configuration.md)             | Every setting, where it goes, and which one wins |
| [Architecture](docs/guides/architecture.md)               | How the pieces fit together                      |
| [CLI reference](docs/guides/cli-reference.md)             | Every command and flag                           |
| [MCP tools](docs/guides/mcp-tools.md)                     | Tool parameters in detail                        |
| [MCP client setup](docs/guides/mcp-client-setup.md)       | Claude Desktop, OpenChamber, multi-project       |
| [Providers](docs/guides/providers.md)                     | llama.cpp, Ollama, OpenRouter                    |
| [Ingestion](docs/guides/ingestion.md)                     | How chunking and embedding work                  |
| [Reading parts](docs/guides/reading-parts.md)             | PDF readers, local OCR backends, page rules      |
| [Metadata extraction](docs/guides/metadata-extraction.md) | Auto-categorisation and filtering                |
| [Reranker](docs/guides/reranker.md)                       | When reranking helps, and when it does not       |
| [Testing](docs/guides/testing.md)                         | Running the suite, writing tests                 |
| [Web workspace](docs/guides/web-workspace.md)             | `omrs web`: launch, sign-in, file grants, jobs   |
| [Notebooks](docs/guides/notebooks.md)                     | Optional marimo plugin, trust, starter notebook  |
| [Decision records](docs/adr/)                             | Why things are the way they are                  |
| [Contributing](CONTRIBUTING.md)                           | Workflow and conventions                         |

---

## Version 2.0.0

v2 restructured the codebase into a modular framework and, in doing so,
broke three things. If you are coming from v1:

- **Settings are renamed.** `TOP_K` is now `RETRIEVAL__TOP_K`, `CHUNK_SIZE`
  is `CHUNKING__CHUNK_SIZE`, and so on. The engine refuses to start on an
  old name and tells you the replacement rather than silently ignoring it.
- **Old import paths are gone.** `omrs.server`, `omrs.cli`,
  `omrs.ingestion` and the rest now live under `omrs.core.*`,
  `omrs.transports.*` and `omrs.integrations.*`.
- **Custom profile YAML needs converting** to nested blocks.

Your ChromaDB collections, CLI commands and MCP tool signatures are
unchanged, and rolling back is code-only — no data migration either way.

The migration table and the full reasoning are in
[ADR-037](docs/adr/037-architecture-v2-conformance.md).

---

## Licence

[MIT](./LICENSE)
