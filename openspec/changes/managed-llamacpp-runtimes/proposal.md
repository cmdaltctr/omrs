# Proposal

## Why

Two OMRS processes (the web app and a CLI ingest) each start an OCR worker for `dots-mocr-llamacpp`. Both workers use one cache folder, and the second worker stops the server of the first. The operator also has no way to stop an OCR server from the GUI.

The cause is a design fault: an OCR engine owns a model server. OMRS reaches every other local model by URL (`llamacpp_chat_url`, `llamacpp_embed_url`, `llamacpp_classify_url`). It has one `llama-server` manager, for Chat, and that manager lives in the web transport only. This change gives OMRS one runtime manager for every local llama.cpp model. Components (Chat, embeddings, OCR engines) become clients of a runtime. They do not own it.

## What Changes

- **One runtime manager in `integrations/`.** Move the Chat server manager out of `transports/api/` into `src/omrs/integrations/llamacpp_runtime/`. The web app, the CLI, the stdio MCP server and the watcher all use it. Transports stay thin wrappers.
- **Two modes per role.** Roles: Chat, embeddings and OCR. `external` connects to a URL that the operator runs (today's embeddings on the Llama app). `managed` lets OMRS start or adopt a `llama-server` with fixed arguments.
  - Chat moves onto the manager and keeps every guardrail it has today.
  - Embeddings get a managed mode, built and tested. The live app stays on `external`.
  - OCR runtimes are managed by default. An operator can point them at an external server with `ocr_runtime_url`.
- **Cross-process lifecycle with file locks.** Each OMRS process that uses a runtime holds a shared lock for as long as it uses it. The last process to leave stops the server. A new process adopts a server that is still running. A server is stale only when its process is gone or runs another command line, never because `/health` is slow.
- **Idle stop after 10 minutes.** A fixed constant, not a setting. The next request starts the runtime again. OMRS does not use llama-server's own idle sleep (llama.cpp issue #29689).
- **BREAKING:** `llamacpp_idle_sleep_seconds` (`LLAMACPP_IDLE_SLEEP_SECONDS`) is retired. The environment or `.env` value fails start-up with a message that names the 10-minute idle stop. An `omrs.jsonc` key is ignored and listed in the problem list.
- **BREAKING:** the managed Chat server no longer stops when `omrs web` exits while another OMRS process still uses it. It stops when the last OMRS process leaves.
- **Queued requests on one-slot runtimes.** A per-runtime request lock serialises OMRS requests across processes. The request timeout starts only when the lock is held.
- **Engines declare a runtime.** An OCR engine's `[tool.omrs-ocr.runtime]` block names the binary, the model files with SHA-256, the llama.cpp build and the fixed flags. The host checks them, starts or adopts the runtime, and passes the base URL to the worker in `OMRS_OCR_RUNTIME_URL`. The host never names an engine. An engine with no block (PaddleOCR-VL) does not change.
- **GUI.** The Integrations page lists each runtime: role, mode, state with one reason line, memory, and who uses it. Managed runtimes have a Stop button. New routes `GET /v1/runtimes` and `POST /v1/runtimes/{runtime_id}/stop`, in the OpenAPI contract.
- **OCR fallback on an operator stop.** A request that fails because the operator stopped its runtime goes to the fallback engine.

## Capabilities

### New Capabilities

- `llamacpp-runtimes`: the shared manager for local llama.cpp runtimes. Covers roles and modes, state files, the cross-process lease, adoption and the stale rule, start and bind retries, crash restart, idle stop, the request lock, operator stop, process exit and the runtime routes.

### Modified Capabilities

- `llamacpp-server`: the Chat server runs on the shared manager. Every OMRS process can start it as a client, and it stops when the last client leaves. The embedding server can be managed. The idle sleep setting and flag are retired. The log moves to the runtime folder. New failure reasons are added.
- `ocr-worker-engines`: an engine may declare a llama.cpp runtime that the host starts. A request that the operator's stop interrupts goes to the fallback route.
- `workspace-integrations`: the Integrations page lists model runtimes with a Stop button.

## Impact

- **New code:** `src/omrs/integrations/llamacpp_runtime/` (manager, leases, state files, process start and stop, launch rules, OCR runtime specs) and `src/omrs/transports/api/routes/runtimes.py`.
- **Moved code:** the launch rules in `src/omrs/core/providers/llm/llamacpp_rules.py` move to the new package. The card field list stays in `core/`. `src/omrs/transports/api/llamacpp_server.py` becomes a thin adapter over the manager.
- **Changed code:** `src/omrs/integrations/ocr_worker/{manifest.py,routes.py,managed.py,pool.py}`, `src/omrs/compose_llamacpp.py`, `src/omrs/config/provider_sources.py`, `src/omrs/config/legacy.py`, the llama.cpp Chat, classification and embedding clients (lease by injection), the CLI, MCP stdio and watcher entry points (SIGTERM ends the process through normal exit).
- **API:** two new routes. `PUT /v1/llamacpp/server` refuses `idle_sleep`. The status `saved` block drops `idle_sleep`. The reason enum grows.
- **Web:** a "Model runtimes" section on the Integrations page. The llama.cpp card loses the idle sleep field.
- **Settings:** new `llamacpp_embed_server` (default `external`) and `ocr_runtime_url` (default blank). `llamacpp_idle_sleep_seconds` retired. New state folder `OMRS_STATE_DIR`, else `$XDG_STATE_HOME/omrs`, else `~/.local/state/omrs`.
- **Tests:** a fake `llama-server` shared by the manager tests, moved from the `dots-mocr-llamacpp-backend` branch. The tripwire is re-pinned by test-ID diff.
- **Docs and ADR:** ADR-109 "OMRS owns local model runtimes; components are clients". Updates to `docs/guides/configuration.md`, `docs/guides/architecture.md`, `docs/guides/web-workspace.md`, `ocr-workers/README.md`, the root `AGENTS.md` (Gotcha 17) and `src/omrs/transports/api/AGENTS.md`.
- **Depends on this change:** `dots-mocr-llamacpp-backend` (reworked to declare a runtime) and `paddleocr-vl-llamacpp-backend` (parked).
- **Not changed:** PaddleOCR-VL, the OCR protocol version, the live app's settings in `~/.omrs`, Windows support (managed mode reports `not-supported` there).
