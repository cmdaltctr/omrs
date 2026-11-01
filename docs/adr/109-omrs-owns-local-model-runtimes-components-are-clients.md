# ADR-109: OMRS Owns Local Model Runtimes; Components Are Clients

- **Date:** 2026-11-01
- **Status:** Proposed (2026-11-01; accepted when the change merges)
- **Deciders:** Maintainer
- **Amends:** [ADR-084](084-context-windows-and-an-owned-llama-server.md) (the owned `llama-server` moves from the web transport to a shared manager, and the idle sleep flag goes), [ADR-108](108-local-chat-and-classification-stay-apart.md) (decision 4: the managed Chat server runs for every OMRS process, not for `omrs web` only)
- **Related:** [ADR-087](087-settings-live-in-omrg-jsonc.md) (source order, `omrs.jsonc`), [ADR-105](105-pipeline-steps-own-their-ocr-settings.md) (OCR routes by engine folder), [ADR-106](106-app-searches-and-downloads-local-models.md), [ADR-103](103-experiments-run-local-models-through-llama-cpp-gguf.md) (llama.cpp for local models), root `AGENTS.md` Gotcha 17
- **Change:** `openspec/changes/managed-llamacpp-runtimes/`

## Context

Two OMRS processes, the web app and a CLI ingest, each start an OCR worker for `dots-mocr-llamacpp`. The worker owns a `llama-server`. Both workers share one cache folder and one pid file. The second worker reads the pid file of the first as stale and stops a server that is in use. The operator also has no way to stop an OCR server from the GUI.

The fault is in the design. An OCR engine owns a model server. OMRS reaches every other local model by URL (`llamacpp_chat_url`, `llamacpp_embed_url`, `llamacpp_classify_url`). OMRS has one `llama-server` manager, for Chat, and it lives in `transports/api/`. The CLI, the stdio MCP server and the watcher cannot use it.

Other tools solve this in four ways. All four share the same fault or need a daemon.

- **One daemon owns the models.** Ollama, LM Studio and llama-swap load models in one long-lived process and unload them after an idle time. OMRS has no such daemon and the change does not add one.
- **The operator runs the server.** docling, MinerU, dots.ocr and PaddleOCR-VL expect an external server and a URL. OMRS cannot check the build or the model files of such a server.
- **Attach or spawn.** surya takes a `FileLock`, attaches to a running server or spawns one, and only the spawner cleans up. That stops a server that another process still uses. This is our fault.
- **Pid files and health probes.** These fail in both directions. AMD GAIA issue #5314 read a slow `/health` answer as a dead server and restarted it. GAIA issue #5352 left orphaned servers running for 30 hours. unsloth issue #6425 notes that macOS has no `PR_SET_PDEATHSIG`, so a child cannot die with its parent. LM Studio issue #2481 reports the same class of fault.

No tool in this list counts clients with kernel locks, which free themselves when a process dies.

Facts about `llama-server` build b11941 that shape the design:

- `-np` is automatic. A request that finds no free slot waits in a deferred queue. It is not refused.
- `--timeout` defaults to 3,600 seconds.
- `/health` answers 503 while the model loads. It can answer 200 while a slot is stuck (llama.cpp issue #27388).
- A client disconnect cancels its task (issue #24496), so a timeout loses the work.
- `--sleep-idle-seconds` has an open race. A request that arrives as the server falls asleep is lost, or it crashes the server (issue #29689; the fix is in open PR #30012).

## Decision

1. **OMRS owns every local llama.cpp runtime. Chat, embeddings and OCR engines are clients.** One manager lives in `src/omrs/integrations/llamacpp_runtime/`. The web app, the CLI, the stdio MCP server and the watcher all use it. The code is synchronous with threads. `compose.py` builds one `RuntimeManager` per process and injects a lease into the clients in `core/`. `core/` does not import the package. Transports stay thin wrappers.

2. **Each role has two modes.** `external`: OMRS connects to a URL that the operator runs. `managed`: OMRS starts or adopts a `llama-server` with a fixed argument list.

   | Role | Runtime id | Mode setting | Default |
   | --- | --- | --- | --- |
   | Chat | `chat` | `llamacpp_chat_server` | `external` |
   | Embeddings | `embeddings` | `llamacpp_embed_server` | `external` |
   | OCR | `ocr-<engine folder>` | `ocr_runtime_url` | blank, which means managed |

   Chat keeps every guardrail it has today. Embeddings get a managed mode that the Settings page does not write. An OCR runtime is managed unless `ocr_runtime_url` is set. An external OCR server still gets the build check. The Integrations page says: "External server. Model files are not checked."

3. **State lives in a per-runtime folder, outside the workspace and `omrs.jsonc`.** The root is `OMRS_STATE_DIR`, else `$XDG_STATE_HOME/omrs`, else `~/.local/state/omrs`. Each runtime has `runtimes/<runtime id>/` with `start.lock`, `clients.lock`, `request.lock`, `server.json` and `server.log`. Every OMRS process writes these files. They hold no settings and no secrets, so Gotcha 17 (only `omrs web` writes the workspace and `omrs.jsonc`) stays true. The folder must be on a local disk, because `flock` is not reliable on NFS or SMB.

4. **A kernel-lock lease counts clients.** A process that uses a runtime holds a shared lock on `clients.lock`. To leave, it drops the lock and tries an exclusive, non-blocking lock. If that works, no other client exists, and it stops the server. The kernel frees a lock when its process dies, so a killed process never blocks the others. A process blocks on `clients.lock` only while it holds no other lock. While it holds `start.lock`, it makes only non-blocking attempts. No wait cycle can form.

5. **A server is stale only when its pid is gone or its command line is wrong.** A slow or failing `/health`, or a long request, never makes a server stale. `/health` is read during a start only. A new process adopts a live server with the same binary and arguments. If another process uses a server with different arguments, the new process gets `version-busy` and does not stop it. OMRS never signals a pid whose command line does not hold the recorded binary path.

6. **A server starts detached.** It runs in its own session with no pipe to the starter. The output goes to `server.log`. Ctrl-C in a CLI terminal does not reach it, and the starter can exit first. The lock descriptors are not inherited.

7. **A fixed 10-minute idle stop replaces `--sleep-idle-seconds`.** The constant is `IDLE_STOP_SECONDS = 600`. It is not a setting. The server stops when the last client leaves or when no request comes for 10 minutes, and the next request starts it again. `llamacpp_idle_sleep_seconds` (`LLAMACPP_IDLE_SLEEP_SECONDS`) is retired. The environment or `.env` value fails start-up with a message that names the 10-minute idle stop. An `omrs.jsonc` key is ignored and listed in the problem list.

8. **A one-slot runtime has a request lock.** OMRS serialises requests to a `-np 1` runtime across processes with `request.lock`. The request timeout starts when the lock is held. A longer timeout is wrong because OMRS cannot see the queue inside `llama-server`, and a timeout that disconnects the client cancels its work.

9. **The operator can stop a managed runtime.** `GET /v1/runtimes` lists the runtimes and `POST /v1/runtimes/{runtime_id}/stop` stops one. Stop needs a session with `manage`. A bearer credential is refused. An external runtime gives 409 `external-runtime`. A request that the stop interrupts goes once to the OCR fallback route. That is one narrow exception to "a worker failure after dispatch is not retried". The operator accepted it on 2026-11-01. The Integrations page shows each runtime with a Stop button.

10. **An OCR engine declares its runtime. The host never names an engine.** The engine's `pyproject.toml` holds a `[tool.omrs-ocr.runtime]` block with the program, the llama.cpp build, fixed flags, and model files with SHA-256. The host checks the build (`wrong-build`) and the hashes (`file-changed`) before a start, starts or adopts the runtime, and gives the worker its address in `OMRS_OCR_RUNTIME_URL`. An engine with no block does not change.

11. **Processes leave their runtimes when they exit.** Normal exit, `atexit` and SIGTERM leave each lease. After SIGKILL of the last client, an orphan server can stay up. The next OMRS process adopts it, and `omrs web` stops it at start-up when no process uses it.

## Consequences

### Positive

- Two OMRS processes share one OCR server. The second process no longer stops the server of the first.
- The CLI, the stdio MCP server and the watcher can use a managed Chat or embeddings server.
- The operator can see and stop every managed runtime from the GUI.
- No long-lived OMRS daemon is needed. Kernel locks and a state folder do the job.
- The host checks the llama.cpp build and the model files of a managed OCR runtime, so the output fingerprint stays honest.

### Negative

- **BREAKING:** the managed Chat server no longer stops when `omrs web` exits while another OMRS process uses it. It stops when the last OMRS process leaves.
- **BREAKING:** `LLAMACPP_IDLE_SLEEP_SECONDS` fails start-up, and `PUT /v1/llamacpp/server` with `idle_sleep` returns 400. The idle stop is fixed at 10 minutes.
- After SIGKILL of the last client, a server can run without a client until the next OMRS process starts. The Integrations page shows it as "Running, no OMRS process uses it", with Stop.
- `flock` gives no first-come order. One process could wait while others win the request lock again and again. OCR traffic is low, so this is accepted.
- `fcntl.flock` is POSIX. Managed mode reports `not-supported` on Windows. External mode works. CI runs on POSIX only.
- An external OCR server serves a model that OMRS cannot check. The row says so, and the guide advises one external llama.cpp engine at a time.

### Neutral

- PaddleOCR-VL declares no runtime and does not change.
- The OCR protocol version does not change.
- The live app's settings do not change. A read-only check on 2026-11-01 found no `LLAMACPP_IDLE_SLEEP_SECONDS` in its shell environment, `omrs.jsonc` or login item.
- Rollback is a revert of the merge commit. The state folder holds no settings, so it can be deleted.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Keep the manager in `transports/api/` | The CLI and the stdio MCP server cannot use it, and the OCR host would need a second manager. |
| A top-level `omrs/runtimes.py` | `integrations/` already holds process adapters (`process_launcher.py`, `ocr_worker/`), and its leaf contract fits. |
| A pid file where only the spawner cleans up (the surya pattern) | It stops a server that another process still uses. This is the fault we have. |
| A client count in a file | A killed process cannot decrement it. Kernel locks free themselves. |
| `/health` as the liveness test | Issue #27388 shows 200 while a slot is stuck. GAIA issue #5314 shows a slow answer read as dead. Both are wrong. |
| `--sleep-idle-seconds` | The race in issue #29689 loses a request or crashes the server, and the fix (PR #30012) is not merged. |
| A longer timeout for queued requests | OMRS cannot see a request's place in the deferred queue. A timeout that cancels the client also cancels its work (issue #24496). A long timeout hides a stuck slot. |
| Let `llama-server` queue one-slot requests | The second process's 300-second clock would run while it waits inside the server. |
| `--models-max` router mode (one server, many models) | It puts the OCR result outside the pinned build and ties Chat restarts to OCR. |
| An OMRS daemon that owns all runtimes (the Ollama pattern) | It adds a long-lived process to install, supervise and secure. The locks give the same sharing without one. |
| The worker keeps its own server and gets a lock | The host cannot check the build and files, the GUI cannot show or stop the server, and a killed worker orphans it. |
| Drop `ocr_runtime_url` and manage only | The operator chose to keep it as an opt-in on 2026-11-01. |

## Verification

Not built yet. The change `managed-llamacpp-runtimes` lists the checks in `tasks.md`:

1. Lease tests with a fake `llama-server` and separate client processes: two clients share one server, a killed client frees its lock, an orphan is adopted, five clients start at once, a reused pid is never signalled, and a 20-second lock-order stress test ends without deadlock.
2. Start, retry, idle stop, request lock, operator stop and exit tests.
3. A check against the real `llama-server` b11941 binary that `GET /props` reports the build (task 6.4).
4. OpenAPI conformance tests for both new routes, and Vitest tests for the Model runtimes section.
5. A browser check at 1,280 px and 390 px.

This section is updated with the results when the change merges.

## References

- `openspec/changes/managed-llamacpp-runtimes/` (proposal, design D1 to D12, specs `llamacpp-runtimes`, `llamacpp-server`, `ocr-worker-engines`, `workspace-integrations`)
- `src/omrs/integrations/llamacpp_runtime/`, `src/omrs/transports/api/llamacpp_server.py`, `src/omrs/transports/api/routes/runtimes.py`
- `docs/guides/configuration.md` (Local llama.cpp server, Upgrade notes), `docs/guides/architecture.md` (Local model runtimes), `ocr-workers/README.md` (Runtime block)
- Prior art: Ollama, LM Studio, llama-swap, docling, MinerU, dots.ocr, PaddleOCR-VL and surya (design.md, "What other tools do")
- Failure reports: AMD GAIA issues #5314 and #5352, unsloth issue #6425, LM Studio issue #2481
- llama.cpp issues #27388, #24496 and #29689, and PR #30012
- [ADR-084](084-context-windows-and-an-owned-llama-server.md), [ADR-108](108-local-chat-and-classification-stay-apart.md), [ADR-105](105-pipeline-steps-own-their-ocr-settings.md)
