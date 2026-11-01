## Purpose

One manager for every local llama.cpp model runtime (Chat, embeddings and OCR), shared by every OMRS process. It covers roles and modes, state files, the cross-process lease, adoption, idle stop, the request lock, operator stop and the runtime routes.

## ADDED Requirements

### Requirement: Each role has an external and a managed mode

OMRS SHALL know three runtime roles: Chat (runtime id `chat`), embeddings (`embeddings`) and OCR (`ocr-<engine folder name>`, one per engine that declares a runtime). In `external` mode OMRS SHALL connect to the configured URL and SHALL NOT start, adopt or stop any process. In `managed` mode OMRS SHALL start or adopt a `llama-server` with a fixed argument list.

#### Scenario: External embeddings start nothing

- **WHEN** `llamacpp_embed_server` is `external` and a client embeds text
- **THEN** OMRS MUST send the request to `llamacpp_embed_url` and MUST NOT start any process

#### Scenario: Not supported on Windows

- **WHEN** a role is `managed` on Windows
- **THEN** the runtime MUST be `failed` with the reason `not-supported` and no process MUST start

### Requirement: Mode settings

The mode settings SHALL be `llamacpp_chat_server` (default `external`), `llamacpp_embed_server` (env `LLAMACPP_EMBED_SERVER`, `external` or `managed`, default `external`) and `ocr_runtime_url` (env `OCR_RUNTIME_URL`, blank means managed, default blank). Managed embeddings SHALL use `llamacpp_server_binary`, the port of `llamacpp_embed_url` and `llamacpp_embed_model` as the model, with the same program and model rules as Chat.

#### Scenario: Default modes

- **WHEN** no source sets a mode
- **THEN** Chat and embeddings MUST be `external`, and every declared OCR runtime MUST be `managed`

#### Scenario: Managed embeddings argument list

- **WHEN** `llamacpp_embed_server` is `managed`, `llamacpp_embed_url` is `http://127.0.0.1:8080/v1` and `llamacpp_embed_model` is `/m/e.gguf`
- **THEN** the argument list MUST equal `[binary, "-m", "/m/e.gguf", "--host", "127.0.0.1", "--port", "8080", "--embedding"]`

### Requirement: Runtime state lives in a per-runtime folder

Each runtime SHALL have a folder `<state root>/runtimes/<runtime id>/` that holds `start.lock`, `clients.lock`, `request.lock`, `server.json` and `server.log`. The state root SHALL be `OMRS_STATE_DIR`, else `$XDG_STATE_HOME/omrs`, else `~/.local/state/omrs`. Every OMRS process SHALL be allowed to write these files. They SHALL hold no settings and no secrets, and SHALL NOT be in the workspace database or `omrs.jsonc`. `server.json` SHALL be written to a temporary file and renamed.

#### Scenario: CLI writes runtime state

- **WHEN** the CLI starts a managed runtime
- **THEN** `server.json` MUST appear under the state root, and `workspace.db` and `omrs.jsonc` MUST NOT change

#### Scenario: State root from the environment

- **WHEN** `OMRS_STATE_DIR` is `/tmp/s`
- **THEN** the Chat runtime folder MUST be `/tmp/s/runtimes/chat/`

### Requirement: Every process that uses a runtime holds a shared lease

A process SHALL hold a shared lock on `clients.lock` while it uses a managed runtime. It SHALL adopt, start or stop only while it holds `start.lock` exclusive. To leave, it SHALL drop its shared lock and try an exclusive lock on a new descriptor without blocking. Success SHALL mean no other client, and the process SHALL stop the server. Failure SHALL leave the server running. A process SHALL NOT block on `clients.lock` while it holds another runtime lock.

#### Scenario: Two clients share one server

- **WHEN** the web app and a CLI ingest both use the `ocr-dots-mocr-llamacpp` runtime
- **THEN** exactly one `llama-server` process MUST run for that runtime

#### Scenario: First client leaves

- **WHEN** two processes use one runtime and the first one exits
- **THEN** the server MUST keep running and the second process's requests MUST succeed

#### Scenario: Last client leaves

- **WHEN** the only process that uses a runtime exits normally
- **THEN** the server process group MUST be stopped and `server.json` MUST record `stopped_by` `last-client`

#### Scenario: Five clients start at once

- **WHEN** five processes send their first request to a stopped runtime at the same time
- **THEN** exactly one server MUST start, and all five requests MUST be answered by it

### Requirement: A running server is adopted, and stale only by pid or command line

A process SHALL adopt a recorded server when its pid is alive, its command line holds the recorded binary path and its argument digest equals the wanted one. A record SHALL be stale only when the pid is gone or its command line does not hold the recorded binary path. A stale pid SHALL NOT be signalled. A slow `/health`, a 503 answer or a long request in progress SHALL NOT make a server stale. OMRS SHALL read only the command line of the one recorded pid and SHALL NOT list processes.

#### Scenario: Orphan adopted after a SIGKILL

- **WHEN** the only client of a runtime is killed with SIGKILL and a new process sends a request
- **THEN** the new process MUST adopt the running server and no second server MUST start

#### Scenario: Busy server is not dead

- **WHEN** a server answers `/health` after 5 seconds, or is busy with a 60-second request, and a second process joins
- **THEN** the second process MUST adopt it and MUST NOT stop or replace it

#### Scenario: Reused pid left alone

- **WHEN** the recorded pid now runs another command
- **THEN** OMRS MUST NOT signal that pid and MUST start a new server

#### Scenario: Other version while in use

- **WHEN** a process wants a runtime with a changed pinned binary path while another process uses the old server
- **THEN** the request MUST fail with the reason `version-busy`, and the old server MUST keep running

#### Scenario: Other version with no other client

- **WHEN** a process wants a runtime with a changed pinned binary path and no other process uses the old server
- **THEN** OMRS MUST stop the old server and start the new one

### Requirement: A managed server starts detached

A managed server SHALL start with no shell, in a new session, with standard input from `/dev/null`, its output written straight to `server.log` and no inherited descriptor. It SHALL survive the exit of the process that started it. A SIGINT to the starter's process group SHALL NOT reach it.

#### Scenario: Ctrl-C in the CLI

- **WHEN** a CLI ingest started a runtime that the web app also uses and the user presses Ctrl-C in the CLI terminal
- **THEN** the server MUST keep running and the web app's next request MUST succeed

#### Scenario: Lock descriptor not inherited

- **WHEN** the starter of a runtime exits and no other process uses it, while the server process still runs
- **THEN** an exclusive non-blocking lock on `clients.lock` MUST succeed

### Requirement: A start checks the build and the declared files

Before a start, OMRS SHALL apply the program rule. For an OCR runtime it SHALL refuse with `wrong-build` when `<binary> --version` reports another build than the declared one. It SHALL refuse with `file-changed` when a declared file does not match its SHA-256, and the reason line SHALL name the file. A start SHALL wait up to 180 seconds for `GET /health` to return 200.

#### Scenario: Wrong build refused

- **WHEN** an OCR engine declares build 11941 and the binary reports build 11960
- **THEN** the runtime MUST be `failed` with `wrong-build` and no server MUST start

#### Scenario: Changed model file refused

- **WHEN** a declared model file no longer matches its SHA-256
- **THEN** the runtime MUST be `failed` with `file-changed`, the reason line MUST name the file name, and no server MUST start

### Requirement: Bind failures and crashes are retried a fixed number of times

A runtime on a free port SHALL retry a bind failure on a new port at most 3 times, then fail with `bind-failed`. When a request finds the recorded server gone and no stop was recorded, OMRS SHALL start the server once under `start.lock` and resend the request once.

#### Scenario: Bind error retried

- **WHEN** an OCR runtime's server fails to bind on each try
- **THEN** OMRS MUST try at most 4 ports in total and then report `bind-failed`

#### Scenario: Crash mid-session

- **WHEN** the server crashes between two requests of one process
- **THEN** the next request MUST start exactly one new server and succeed

### Requirement: An idle runtime stops after 10 minutes

A process SHALL leave a managed runtime when 600 seconds have passed since its last request ended and no request of it runs. The 600 seconds SHALL be a fixed constant and SHALL NOT be a setting. The next request SHALL start or adopt the runtime again. OMRS SHALL NOT pass `--sleep-idle-seconds` to any server.

#### Scenario: Idle stop

- **WHEN** the only client of a runtime sends no request for 600 seconds
- **THEN** the server MUST stop and `server.json` MUST record `stopped_by` `idle`

#### Scenario: Next request after idle stop

- **WHEN** a request arrives after an idle stop
- **THEN** the runtime MUST start again and the request MUST succeed

#### Scenario: No sleep flag

- **WHEN** any managed server starts
- **THEN** its argument list MUST NOT hold `--sleep-idle-seconds`

### Requirement: Requests to a one-slot runtime wait for a request lock

A runtime whose argument list holds `-np 1` SHALL be a one-slot runtime. Each OMRS request to it SHALL hold `request.lock` exclusive while it runs. The request timeout SHALL start when the lock is held. The wait for the lock SHALL have no timeout of its own.

#### Scenario: Second client waits without losing its timeout

- **WHEN** process A holds a 250-second OCR request on a one-slot runtime with a 300-second timeout and process B sends a request at the same time
- **THEN** process B's request MUST start after A's ends and MUST NOT time out because of the wait

### Requirement: The operator can stop a managed runtime

A stop by the operator SHALL send SIGTERM to the server's process group, wait 10 seconds, then send SIGKILL, and SHALL record `stopped_by` `operator`. A request in progress SHALL fail. A process whose lease joined before the stop SHALL NOT start that runtime again for the rest of that lease. A process that joins later SHALL start it again. An external runtime SHALL NOT be stopped.

#### Scenario: Stop while a CLI uses it

- **WHEN** a CLI ingest uses an OCR runtime and the operator stops it
- **THEN** the server MUST stop, and the CLI MUST NOT start it again during that lease

#### Scenario: New process after an operator stop

- **WHEN** a new process sends a request after an operator stop
- **THEN** the runtime MUST start again

### Requirement: OMRS processes leave their runtimes when they exit

On a normal exit, a SIGTERM, an engine close, an OCR pool close or the shutdown of `omrs web`, a process SHALL leave each runtime it holds. The CLI, the stdio MCP server and the watcher SHALL turn SIGTERM into a normal exit. At start-up, `omrs web` SHALL stop every recorded managed server that is alive, owned, and used by no process.

#### Scenario: SIGTERM to the only client

- **WHEN** the only client of a runtime receives SIGTERM
- **THEN** the server MUST stop before the client process exits

#### Scenario: Orphan swept at web start

- **WHEN** an owned server runs with no client and `omrs web` starts
- **THEN** `omrs web` MUST stop that server

### Requirement: A route lists the runtimes

`GET /v1/runtimes` SHALL need `read` and SHALL return one item per runtime in force with `id`, `role`, `mode`, `state` (`running`, `starting`, `stopped` or `failed`), `reason` from a fixed set, `reason_text`, `memory_bytes`, `clients` (`some` or `none`), `used_by`, `address` and `files_checked`. It SHALL NOT start, stop or write anything. The route SHALL be in `openapi.yaml`. No response SHALL hold server output.

#### Scenario: List shape

- **WHEN** a client reads `GET /v1/runtimes`
- **THEN** every item MUST hold the listed fields and no other field

#### Scenario: Reading starts nothing

- **WHEN** a client reads `GET /v1/runtimes` while every runtime is stopped
- **THEN** no process MUST start and no runtime file MUST change

### Requirement: A route stops a managed runtime

`POST /v1/runtimes/{runtime_id}/stop` SHALL need a browser session with `manage` and SHALL refuse a bearer token. It SHALL return 404 for an unknown id and 409 with the reason `external-runtime` for an external runtime. The route SHALL be in `openapi.yaml`.

#### Scenario: Stop refused for a bearer token

- **WHEN** a bearer token with `manage` sends `POST /v1/runtimes/chat/stop`
- **THEN** the server MUST refuse the request and MUST send no signal

#### Scenario: External runtime

- **WHEN** a session stops the `embeddings` runtime while it is `external`
- **THEN** the server MUST return 409 with the reason `external-runtime` and MUST send no signal

### Requirement: An external OCR runtime is checked for its build

External OCR SHALL be opt-in only: a blank `ocr_runtime_url` SHALL mean managed. When it is set, OMRS SHALL pass it to every OCR engine that declares a runtime, SHALL start nothing, and SHALL refuse the runtime with `wrong-build` when the server's reported build differs from the declared build. The runtime item SHALL report `mode` `external` and `files_checked` false.

#### Scenario: External OCR server with another build

- **WHEN** `ocr_runtime_url` names a server that reports build 11960 and the engine declares 11941
- **THEN** the OCR route MUST be unavailable with `wrong-build` and the fallback route MUST serve the file

#### Scenario: External OCR server with the declared build

- **WHEN** `ocr_runtime_url` names a server that reports build 11941 and the engine declares 11941
- **THEN** OMRS MUST start no process and MUST pass the URL to the worker
- **AND** the runtime item MUST report `mode` `external` and `files_checked` false
