# Getting Started

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — Python package manager:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- A Linux x86-64 machine or an Apple silicon Mac. OMRS places its own pinned llama.cpp build, so you install no model server.

## Install

1. Copy the example config. It holds storage settings and secret notes only.

   ```bash
   cp .env.example .env
   ```

2. Install the Python dependencies. The llama.cpp backend needs no extra.

   ```bash
   uv sync
   ```

3. Place the pinned llama.cpp build. The command downloads it once, checks it and prints the path.

   ```bash
   uv run omrs llamacpp install
   ```

   The command starts no server. On Linux, add `--flavour cpu` or `--flavour cuda` to choose the build. See [CLI reference](cli-reference.md#llamacpp-install).

4. Run the first command that needs a model, for example the verify step below. OMRS starts the router and downloads the two shipped models: `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` for embeddings and `Qwen/Qwen3-4B-GGUF:Q8_0` for classification. The first run waits for the download. Chat has no model until you choose one in Settings > Chat.

## Verify it works

```bash
uv run omrs
```

No output means it's working — it's waiting silently for MCP messages on stdin. Press Ctrl-C to stop.

To inspect the tools interactively:

```bash
npx @modelcontextprotocol/inspector uv run omrs
```

## Reranker and hybrid search

The reranker is **off by default**. Experiment 10 measured a 19–27% degradation on technical/code workloads, so it is opt-in. The `documents` profile turns it on for semantic workloads; the `codebase` profile leaves it off for speed (ADR-018). It's a ~23 MB ONNX model that downloads once from HuggingFace and runs entirely locally.

1. Edit `.env` and set:
   ```
   RETRIEVAL__RERANK_ENABLED=true
   ```
2. Trigger the first download by running any search with `rerank=True`. The model caches in `~/.cache/huggingface/` — no repeat downloads.

See [Reranker](reranker.md) for details.

## Alternative providers

The llama.cpp router is the default. Ollama and OpenRouter are opt-in providers: [Ollama](https://ollama.com) for a local server you run yourself, [OpenRouter](https://openrouter.ai) for cloud embeddings. See [Providers](providers.md) for setup instructions.

### Ollama (opt-in)

Ollama is an opt-in local backend. Install and start Ollama yourself, pull an embedding model, then set `local_backend` to `ollama` and `embed_model` to that model in `omrs.jsonc`. See [Ollama](providers.md#ollama-opt-in-local-backend) for every setting.

### Hybrid search

For rare terms, citations, error codes, and exact identifiers, try opt-in hybrid retrieval:

```bash
uv run omrs search "What fixes MCP-1138?" --hybrid
```

MCP clients can pass `hybrid: true` to `search_documents`.

## Register in your AI client

See [MCP Client Setup](mcp-client-setup.md) to connect the server to OpenChamber, Claude Desktop, or any other MCP-compatible client.

## Verification checklist

- [ ] `uv run omrs llamacpp install` reports that the pinned build is ready
- [ ] After your first ingest, `curl http://127.0.0.1:8080/v1/models` lists `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0`
- [ ] `uv run omrs` starts without errors and waits on stdin
- [ ] MCP Inspector can discover and call all five tools
- [ ] Your MCP client shows `rag-docs` as connected (green)
- [ ] "What documents do you have access to?" calls `list_indexed_documents`
- [ ] "What collections are available?" calls `list_collections`
- [ ] "Index /path/to/file.pdf into the research collection" calls `ingest_documents` with `collection`
- [ ] A question about document content calls `search_documents` and cites the source
- [ ] "Delete the chunks for /path/to/file.pdf" calls `delete_documents` with `path`
- [ ] "Drop the collection research" calls `delete_documents` with `collection`
