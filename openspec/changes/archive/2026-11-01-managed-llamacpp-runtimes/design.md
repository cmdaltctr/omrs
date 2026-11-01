# Design

## Context

See proposal.md, "Why". The current state that shapes the approach:

- **Chat server manager.** `src/omrs/transports/api/llamacpp_server.py` (388 lines) starts one `llama-server` with `start_new_session=True`. It keeps the handle, pumps output through a pipe into a 5 MiB log, polls `/health` for 180 s, and stops with SIGTERM, 10 s, SIGKILL on the process group. It is asyncio code in the web transport. The CLI and the stdio MCP server cannot use it. Its launch rules live in `src/omrs/core/providers/llm/llamacpp_rules.py`. `compose_llamacpp.py` builds the settings view. `config/provider_sources.py` holds `llamacpp_server_binary`, `llamacpp_chat_server`, `llamacpp_context_window` and `llamacpp_idle_sleep_seconds`.
- **The managed Chat port is fixed.** It comes from `llamacpp_chat_url`, so the Chat client, and classification when `llamacpp_classify_url` is blank, reach it with no change.
- **OCR host.** `routes.py` resolves `<workers>/engines/<name>/.venv/bin/python -m omrs_ocr_worker_core` and never branches on a name. `pool.py` keeps one `ManagedOcrClient` per route command, with one dispatch lock per process, until the pool closes. `client.py` closes a worker with stdin close, 5 s, SIGTERM, 5 s, SIGKILL. `manifest.py` is standard-library only, because `ocr-workers/provision.py` loads it by file path with the system `python3`.
- **The dots.mocr branch.** `dots-mocr-llamacpp-backend` has a worker that starts its own server (`server.py`, a pid file in the engine cache). Two OMRS processes start two workers that share one cache folder. The second worker reads the first one's pid file as stale and stops a server that is in use.
- **Gotcha 17.** Only `omrs web` writes the workspace and `omrs.jsonc`. The state files of this change are neither, so every process may write them (D3).
- **Import contracts.** `integrations` must not import `core` (except `core.settings`), `transports` or `daemon`. `core` must not import `transports`.

### What other tools do

- **One daemon that owns models:** Ollama, LM Studio and llama-swap load models in one long-lived process and unload them after an idle time.
- **External server only:** docling, MinerU, dots.ocr and PaddleOCR-VL expect the operator to run the server and give a URL.
- **Attach or spawn:** surya takes a `FileLock`, attaches to a running server or spawns one. Only the spawner cleans up, so it can kill a server that another process still uses. This is the same fault as ours.
- **Orphans are a known failure:** AMD GAIA #5314 read a slow `/health` as a dead server and restarted it. GAIA #5352 had orphaned servers that ran for 30 hours. unsloth #6425: macOS has no `PR_SET_PDEATHSIG`, so a child cannot die with its parent. LM Studio #2481 reports the same class of problem.
- **Nobody counts clients with lease files.** D4 does this with kernel locks, which free themselves when a process dies.

### llama-server b11941 facts used here

- `-np` is automatic by default. Continuous batching is on. A request that finds no free slot waits in a deferred queue. It is not refused.
- `--timeout` defaults to 3,600 s.
- `/health` answers 503 while the model loads. It can answer 200 while a slot is stuck (#27388).
- A client disconnect cancels its task (#24496).
- `--sleep-idle-seconds` has an open race: a request that arrives as the server falls asleep is lost or crashes the server (#29689; the fix is in open PR #30012).

## Goals / Non-Goals

**Goals:**

- Every OMRS process can use a managed runtime. Two processes share one server.
- A server that a process still uses is never stopped by another process's start, idle stop or exit.
- No server outlives the last OMRS process for longer than the next OMRS start (D9).

**Non-Goals:**

- A daemon of our own. The kernel locks and a state folder do the job without a long-lived OMRS process.
- Windows. `fcntl.flock` is POSIX. On Windows, managed mode fails with the reason `not-supported`. External mode works.
- Any change to PaddleOCR-VL (it declares no runtime).
- Any change to the live app's settings in `~/.omrs`.
- llama-server's own idle sleep (#29689).
- Counting clients. The design needs only "some client" or "no client".

## Decisions

### D1. One manager in `integrations/llamacpp_runtime/` (D-a)

The package `src/omrs/integrations/llamacpp_runtime/` holds:

| Module | Job |
| --- | --- |
| `rules.py` | Launch rules moved from `core/providers/llm/llamacpp_rules.py`: program check, model kind, loopback port, argument lists per role, minimal child environment, fixed reasons. |
| `spec.py` | `RuntimeSpec`: runtime id, role, mode, binary, argument list, declared files with SHA-256, required build, port policy, slot count. |
| `state.py` | State folder paths and the atomic read and write of `server.json`. |
| `locks.py` | `flock` helpers for the three lock files. |
| `process.py` | Detached start, build check, file hash check, command-line check, stop. |
| `manager.py` | `RuntimeManager` (one per process) and `RuntimeLease` (one per runtime per process): acquire, request, idle timer, leave, status, operator stop. |

The code is synchronous with threads, so the CLI and the watcher need no event loop. The web routes call it through `run_in_threadpool`. `compose.py` builds one `RuntimeManager` per process and injects leases. The llama.cpp Chat, classification and embedding clients in `core/` receive an optional lease object by injection; `core/` does not import the package. The card field list (`LLAMACPP_SERVER_FIELDS`) stays in `core/providers/llm/llamacpp_rules.py` because it is settings data. `transports/api/llamacpp_server.py` keeps the web lifespan hook and maps the manager's status to the existing route body.

- **Rejected: keep the manager in `transports/api/`.** The CLI and MCP stdio could not use it, and the OCR host would need a second manager.
- **Rejected: a top-level `omrs/runtimes.py`.** `integrations/` already holds process adapters (`process_launcher.py`, `ocr_worker/`), and its leaf contract fits.

### D2. Roles and modes (D-b)

| Role | Runtime id | `external` | `managed` |
| --- | --- | --- | --- |
| Chat | `chat` | `llamacpp_chat_url` (today's default) | Port from `llamacpp_chat_url`. Argument list `[binary, -m/-hf, model, --host, 127.0.0.1, --port, n, -c, window]`. |
| Embeddings | `embeddings` | `llamacpp_embed_url` (live app setting, unchanged) | Port from `llamacpp_embed_url`. Argument list `[binary, -m/-hf, model, --host, 127.0.0.1, --port, n, --embedding]`. |
| OCR | `ocr-<engine folder>` | `ocr_runtime_url` when not blank | Default. Free loopback port. Argument list from the engine's runtime block (D7). |

- The mode keys are `llamacpp_chat_server` (exists), `llamacpp_embed_server` (new, env `LLAMACPP_EMBED_SERVER`, `external` or `managed`, default `external`) and `ocr_runtime_url` (new, env `OCR_RUNTIME_URL`, blank means managed).
- `llamacpp_embed_server` is read from the environment, `.env` and `omrs.jsonc`. The Settings page does not write it in this change. The operator switches it later.
- Chat keeps every guardrail: the program is an absolute path to an executable file named `llama-server` (links resolved), the argument list is a list with no shell, the flags are fixed, the host is `127.0.0.1`, a change of program or Chat server choice needs the `credentials` scope, and so does a llama.cpp Chat model write while Chat is managed. The same program check and model rule apply to managed embeddings (`llamacpp_embed_model` names the `.gguf` file or Hugging Face id). Embeddings reuse `llamacpp_server_binary`.
- Chat and embeddings keep the fixed port from their URL. Their clients and the readiness probes need no change. A port held by a process that is not the recorded server gives `port-in-use`, as today. They get no bind retry, because a fixed port cannot move.
- OCR in external mode (operator decision, 2026-11-01: `ocr_runtime_url` stays, opt-in only). A blank value, the default, means managed. When the value is set, the host starts nothing and passes `ocr_runtime_url` to every engine that declares a runtime. The build check still runs: the host reads `GET /props` and refuses the runtime with `wrong-build` when the build is not the declared one, so the fingerprint stays honest about the build. The host cannot check model files. The runtimes list never hides this: the row for an external OCR runtime says plainly "External server. Model files are not checked." (the item reports `mode` `external` and `files_checked` false).
- **Rejected: `--models-max` router mode (one server, many models).** It puts the OCR result outside the pinned build and ties Chat restarts to OCR.

### D3. State folder and files (D-c)

- **Root:** `OMRS_STATE_DIR`, else `$XDG_STATE_HOME/omrs`, else `~/.local/state/omrs`. Each runtime has `<root>/runtimes/<runtime id>/`.
- **Files in each runtime folder:**
  - `start.lock`: exclusive while one process decides to adopt, start or stop.
  - `clients.lock`: shared by every process that uses the runtime now.
  - `request.lock`: exclusive while one request runs on a one-slot runtime (D6).
  - `server.json`: pid, port, binary path, argument digest, build, state (`starting`, `running`, `stopped`), `stopped_by` (`operator`, `idle`, `last-client` or none), generation number, last failure reason. Written to `server.json.tmp`, then renamed.
  - `server.log`: the child's output (D5).
- **Why not the workspace:** `workspace.db` and `omrs.jsonc` are written by `omrs web` only (Gotcha 17). The CLI, MCP stdio and the watcher must also start runtimes, so the state is outside both. Every OMRS process may write these files. They hold no settings and no secrets. Gotcha 17 in `AGENTS.md` gets one sentence that says so.
- **Why not the engine cache:** an OCR runtime is the host's, not the worker's. The engine cache holds only the files the engine declares.
- **Why not `--workspace`:** the CLI cannot see the web app's `--workspace` flag, so the folder must come from the environment alone.
- **Local disk only.** `flock` is not reliable on NFS or SMB. The default root is in the home folder. The configuration guide says that `OMRS_STATE_DIR` must be on a local disk. OMRS does not try to detect a network file system.
- **Tests** set `OMRS_STATE_DIR` to a tmp folder in an autouse fixture, beside `OMRS_CONFIG_DIR`.

### D4. The lease lifecycle (D-c)

**Join** (first request of a process):

1. Open `clients.lock` and take a **shared** lock. Block if needed.
2. Take `start.lock` **exclusive**. Block if needed.
3. Read `server.json`. Decide:
   - **Adopt** when the pid is alive, its command line holds the recorded binary path, and the argument digest equals the one this process wants. If the state is `starting` (its starter died), poll `/health` up to the start timeout.
   - **Stale record** when the pid is gone, or its command line does not hold the recorded binary path (pid reuse). Never signal that pid. Start a new server.
   - **Other version** when the pid is ours but the digest differs (for example a changed pinned binary path). Drop this process's shared lock. Try an exclusive lock on a new descriptor, **non-blocking**. Success means no other client: stop the old server and start the new one. Failure means another process uses the old server: refuse with `version-busy`, release `start.lock`, then take the shared lock again. The old server keeps running.
4. Start when needed (D5). Hold `start.lock` until `/health` answers 200 or the start fails.
5. Release `start.lock`. Keep the shared lock.

**Leave** (idle stop, close or exit of the process):

1. Close the descriptor that holds the shared lock.
2. Open a new descriptor and try `clients.lock` **exclusive, non-blocking**. Failure: another client exists; do nothing more.
3. Success: take `start.lock` exclusive, stop the server (SIGTERM to its process group, 10 s, SIGKILL), write `stopped_by: last-client` or `idle`, release both locks.

**Lock order rule.** A process blocks on `clients.lock` only while it holds no other lock. Under `start.lock`, only non-blocking attempts on `clients.lock` happen. So no wait cycle can form.

**Stale rule.** A server is stale only when its pid is gone or its command line is wrong. A slow `/health`, a 503, or a 60 s request in progress never makes a server stale. `/health` is read only during a start. This avoids GAIA #5314.

**Detach.** The server starts with `start_new_session=True`, `stdin` from `/dev/null`, `stdout` and `stderr` to `server.log`, and `close_fds=True`. It has no pipe to the starter, so it survives the starter's exit with no SIGPIPE. A Ctrl-C in a CLI terminal goes to the CLI's process group only. Python opens descriptors as non-inheritable (PEP 446), so the server never holds a lock descriptor. A test checks this.

**Command-line check.** `ps -o command= -p <pid>` on one recorded pid. It is not a process listing, so the existing "no process lookup" rule holds.

- **Rejected: pid file plus "only the spawner cleans up" (surya).** It stops a server that another process still uses.
- **Rejected: a client count in a file.** A killed process cannot decrement it. Kernel locks free themselves.
- **Rejected: `/health` as liveness.** #27388 (200 while stuck) and GAIA #5314 (slow means dead) show it is wrong both ways.

### D5. Start, bind retries, log and crash restart

- **Checks before start**, in this order: program rule; for an OCR runtime, the build from `<binary> --version` must equal the declared build (`wrong-build`), and the SHA-256 of each declared file must match (`file-changed`, the reason line names the file name). The hashes run at each start, not at adoption. For 4.4 GB that is a few seconds, small beside a model load.
- **Port:** Chat and embeddings use the port of their URL. An OCR runtime binds a socket to port 0 on `127.0.0.1`, reads the port, closes the socket and passes the port. When the server exits before it is healthy and its log ends with llama-server's bind error, the manager retries on a new port, at most 3 times, then fails with `bind-failed`. Any other early exit is `exited`, with no retry.
- **Health:** poll `GET /health` every 0.5 s up to 180 s. 503 means loading. Timeout stops the process and gives `timeout`.
- **Log:** `server.log` is emptied at each start. The child writes to it directly. A client checks its size after each request and empties it in place when it passes 5 MiB (the child opened it with `O_APPEND`, so later lines go to the new end). No route returns it.
- **Crash restart:** when a request fails because the connection is refused or reset, the lease takes `start.lock` and reads `server.json`. If the recorded pid is gone and `stopped_by` is empty, it starts the server once and sends the request once more. A second failure ends the request with `exited`. If `stopped_by` is `operator`, it does not restart (D8).

### D6. Queued requests on one-slot runtimes (D-e)

**Decision:** a per-runtime request lock. A runtime whose argument list holds `-np 1` is a one-slot runtime. Each OMRS request to it takes `request.lock` exclusive before it is sent and releases it after the answer. The request timeout starts when the lock is held, not when the caller asks. For OCR, the host takes the lock around one worker parse request, so `request_timeout(settings, pages)` (floor 300 s) times only the parse. The worker's own HTTP timeout is engine code and must not be shorter.

The wait for the lock has no timeout of its own. It is bounded because each holder's request is bounded by its own timeout, and the kernel frees the lock of a process that dies. A CLI user can still press Ctrl-C.

Chat and embeddings have no `-np 1`. llama-server gives them several slots and continuous batching, and their client timeouts stay as they are.

- **Why not a longer timeout for queued requests:** OMRS cannot see a request's place in llama-server's deferred queue. Any fixed extra time is wrong for some queue length. A wait of N requests needs N times the timeout, and an unbounded timeout hides a stuck slot (#27388).
- **Why not let llama-server queue:** with one slot, a second process's request would wait inside the server while its 300 s clock runs, and would time out for a reason that is not its own. A timeout also disconnects the client, which cancels its task (#24496), so the work is lost.
- **Trade-off:** `flock` gives no first-come order. In theory one process could wait while others win the lock again and again. OCR traffic is a few processes, so this is accepted.

### D7. Idle stop (D-d)

- `IDLE_STOP_SECONDS = 600` in `manager.py`, a constant. It is not a setting.
- Each lease records the time its last request ended. A daemon timer thread checks once a minute. When no request runs in this process and 600 s have passed, the lease leaves (D4). For an OCR lease, the host closes that route's worker first, then leaves.
- The server stops only when the leave finds no other client. So the server stops at most 10 minutes after the last request of the last active process.
- The next request joins again and starts the server.
- **Rejected: `--sleep-idle-seconds`.** The race in #29689 loses a request or crashes the server, and the fix (PR #30012) is not merged. The existing Chat server passes the flag today (default 300 s). This change stops passing it and retires the setting.

### D8. Operator stop (D-g)

- `POST /v1/runtimes/{runtime_id}/stop` and the Chat card's Stop both call `RuntimeManager.stop(runtime_id)`.
- It takes `start.lock`, checks the recorded pid as in D4, sends SIGTERM to the process group, waits 10 s, sends SIGKILL, and writes `stopped_by: operator` with the current generation.
- A request in progress fails. For OCR, the host sends that request to the fallback route once. This is a narrow exception to "a worker failure after dispatch is not retried". The operator accepted it on 2026-11-01 (operator decision), because the operator's own Stop caused the failure and not a fault of the engine. The retry is one only: if the fallback also fails or is also stopped, the file gets a structured error and the host does not send it again, to this route or to any other.
- A lease that joined that generation does not restart the server. Its route is then unavailable before dispatch, so OCR uses the fallback route for the rest of that lease. A process that joins later, or the same process after its lease left and joins again, starts the server again.
- An external runtime has no Stop. The route returns 409 with the reason `external-runtime`.
- Scope: the session with `manage`, the same as `POST /v1/llamacpp/server/stop`. A bearer credential is refused.

### D9. Exit of OMRS processes (D-h)

- The worker no longer starts a server, so the host's close timing (stdin close, 5 s, SIGTERM, 5 s, SIGKILL in `client.py`) cannot orphan an OCR server. A killed worker leaves only itself.
- **Normal exit:** `OcrClientPool.close()`, `Engine.close()`, the web lifespan shutdown and an `atexit` hook in `RuntimeManager` all call leave for each lease. The OCR order is: close the worker, then leave the runtime.
- **SIGTERM:** the CLI, MCP stdio and watcher entry points turn SIGTERM into `SystemExit`, so the `atexit` hooks run. `omrs web` already shuts down through its lifespan.
- **SIGKILL:** no code runs. The kernel frees the shared lock. If other clients exist, nothing changes. If none exist, the server is an orphan. The next OMRS process that joins adopts it (no second server). `omrs web` at start-up also sweeps the state folder: a runtime with a live, owned server and no client (exclusive `clients.lock` succeeds, non-blocking) is stopped. The Integrations page shows such a runtime as "Running, no OMRS process uses it", with Stop.
- So the managed Chat server no longer stops when `omrs web` exits while a CLI still uses it. This is the BREAKING item in the proposal.

### D10. Engines declare a runtime (D-f)

An OCR engine's `pyproject.toml` may hold:

```toml
[tool.omrs-ocr.runtime]
program = "llama.cpp/llama-b11941/llama-server"
build = 11941
flags = ["--temp", "0", "-c", "24576", "-np", "1", "--image-min-tokens", "4", "--image-max-tokens", "14400"]

[[tool.omrs-ocr.runtime.files]]
flag = "-m"
path = "models/dots-mocr-Q8_0.gguf"
sha256 = "6017b1844a77837010649939fe2e934af17728fc89243f88b10bde4afa04d6be"

[[tool.omrs-ocr.runtime.files]]
flag = "--mmproj"
path = "models/dots-mocr-mmproj-bf16.gguf"
sha256 = "63f415f961da981d0ee101cfdbf7a7bcc81ace4c4aa780a6e2823c0cd780761f"
```

- **Paths** are relative to the engine cache: `$OMRS_OCR_MODEL_CACHE/<engine>` when set, else `<engine folder>/.model-cache` (the worker core's `model_cache_dir` rule; the host repeats it). An absolute path, `..`, or a link that resolves outside the cache is refused.
- **Rules:** the program file name is `llama-server`. `flag` is `-m` or `--mmproj`. `flags` are strings and must not hold `--host`, `--port`, `-m`, `--model`, `--mmproj`, `-hf`, `--hf-repo`, `--api-key`, `--sleep-idle-seconds`, `--log-file` or anything starting with `--model-url`. The host adds `--host 127.0.0.1 --port <n>`.
- **Reader:** `manifest.py` gains `declared_runtime(folder, cache_dir)`. It stays standard-library only and uses `tomllib`, which exists in every Python that runs the host (OMRS needs 3.11). `provision.py` does not call it, so its older `python3` support is untouched.
- **Host path:** `routes.py` puts the declared runtime on `RouteCommand`. The pool builds a `RuntimeSpec` with runtime id `ocr-<engine folder name>` and gives the route's `ManagedOcrClient` a lease. Before a parse, the client joins (D4), takes the request lock (D6), and starts the worker with `OMRS_OCR_RUNTIME_URL=http://127.0.0.1:<port>` in its environment. If the URL changes (a restart on a new port), the client closes the worker and starts it with the new URL.
- **Failures before dispatch** (`wrong-build`, `file-changed`, `bind-failed`, `timeout`, `version-busy`, `not-supported`, operator stop) make the route unavailable for that request, so the existing fallback rule applies.
- **No block:** the route works as today. PaddleOCR-VL is unchanged.
- **Engine-agnostic:** the host uses the folder name only as data, as `routes.py` does now. No host module names an engine.
- **Probe:** `--capabilities` needs no runtime and starts none.

### D11. GUI and routes (D-g)

- `GET /v1/runtimes` (`read`) returns one item per runtime in force: `id`, `role`, `mode`, `state` (`running`, `starting`, `stopped`, `failed`), `reason` (fixed set) and a plain `reason_text`, `memory_bytes` (from `ps -o rss=` of the recorded pid, `null` when not running), `clients` (`some` or `none`, from a non-blocking exclusive attempt that is released at once), `used_by` (settings in force, for example `ocr_engine_primary`), `address` (loopback host and port, no user name), `files_checked` (false for external OCR). The route starts nothing and writes nothing.
- `POST /v1/runtimes/{runtime_id}/stop` (D8). The id must match `^(chat|embeddings|ocr-[A-Za-z0-9._-]+)$` and be in the list, else 404.
- Both go in `openapi.yaml` first, with a family in `FAMILIES` and `additionalProperties: false`. The 409 reason `external-runtime` gets a plain line in the route's message map and in `web/src/integrations/InstallRefusal.tsx` if that file renders it.
- The Integrations page gets a "Model runtimes" section: one row per runtime with role, mode, a status badge, the reason line, memory, used by, and a Stop button for a managed runtime that runs. Stop asks for confirmation when `clients` is `some`.

### D12. Retire the idle sleep setting

- `llamacpp_idle_sleep_seconds` leaves `config/provider_sources.py`, `user_config.py`, the card and `GET /v1/llamacpp/server`.
- `config/legacy.py`: `LLAMACPP_IDLE_SLEEP_SECONDS` in the environment or `.env` fails start-up with a message that names it and the fixed 10-minute idle stop. The `omrs.jsonc` key is ignored and listed in the problem list. This follows the `llamacpp_server_model` retirement.
- `PUT /v1/llamacpp/server` with `idle_sleep` returns 400 with that message.
- Live-app check (read only, 2026-11-01, names counted and values not read): the live app does not set `LLAMACPP_IDLE_SLEEP_SECONDS` in the shell environment, in `~/.config/omrs/omrs.jsonc` or in the `com.omrs.web` login item plist. No `~/.omrs/.env` exists. The retirement goes ahead as planned, and start-up will not fail on the live app.

## Risks / Trade-offs

- [An orphan holds memory after a SIGKILL of the last client] → D9 sweep at `omrs web` start, adoption by the next client, and a "no OMRS process uses it" row with Stop.
- [The operator stops a runtime that a CLI ingest uses] → Stop asks for confirmation when `clients` is `some`. OCR requests go to the fallback route.
- [`flock` on a network file system] → the default root is local. The guide says so.
- [The live app sets `LLAMACPP_IDLE_SLEEP_SECONDS`] → start-up would fail. Checked on 2026-11-01 (task 9.4): the live app does not set it, so the risk is closed for the live app.
- [Windows users of managed Chat lose it] → reason `not-supported`, and external mode stays. CI is POSIX only, so Windows was never tested.
- [External OCR serves a model OMRS cannot check] → the build check stays, the row says "External server. Model files are not checked.", and the guide says external OCR suits one llama.cpp engine at a time.
- [A one-slot runtime serialises pages across processes] → this is the server's real capacity. D6 makes the wait visible as lock wait, not as timeouts.
- [`ps` output differs between macOS and Linux] → only the `command=` and `rss=` columns are used. Tests run the fake server on both CI platforms.

## Migration Plan

1. Land the manager with Chat on it. Chat behaviour stays the same for one process. The live app's settings do not change.
2. The idle sleep key retires. The live app does not set it (checked 2026-11-01), so nothing changes for the live app. Any other `omrs.jsonc` key is ignored with a problem-list line.
3. `dots-mocr-llamacpp-backend` rebases and declares a runtime.
4. Rollback: revert the merge commit. The state folder can be deleted. It holds no settings.

## Open Questions

- **External OCR (decided 2026-11-01):** `ocr_runtime_url` stays, opt-in only. It cannot check model files, so the build check still runs and the Integrations row says so plainly (D2). Nothing is open.
- **`GET /props` build field on b11941:** the design assumes `/props` reports the build. Task 6.4 checks the real binary. If it does not, external OCR refuses with `wrong-build` until another check is chosen.
