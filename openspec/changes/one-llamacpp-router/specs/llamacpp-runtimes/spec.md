## MODIFIED Requirements

### Requirement: Each role has an external and a managed mode

OMRS SHALL know two runtime roles: the router (runtime id `router`, capability `llamacpp-router`), which serves every local llama.cpp model by name, and OCR (`ocr-<engine folder name>`, one per engine that declares a runtime). In `external` mode OMRS SHALL connect to the configured URL and SHALL NOT start, adopt or stop any process. In `managed` mode OMRS SHALL start or adopt a `llama-server` with a fixed argument list. The runtime ids `chat`, `embeddings` and `decision-<name>` SHALL NOT exist.

#### Scenario: External embeddings start nothing

- **WHEN** `llamacpp_router_server` is `external` and a client embeds text
- **THEN** OMRS MUST send the request to `llamacpp_router_url` and MUST NOT start any process

#### Scenario: Not supported on Windows

- **WHEN** a role is `managed` on Windows
- **THEN** the runtime MUST be `failed` with the reason `not-supported` and no process MUST start

#### Scenario: Old runtime ids gone

- **WHEN** a client reads `GET /v1/runtimes`
- **THEN** no item MUST have the id `chat`, `embeddings` or one that starts with `decision-`

### Requirement: Mode settings

The mode settings SHALL be `llamacpp_router_server` (env `LLAMACPP_ROUTER_SERVER`, `external` or `managed`, default `managed`) and `ocr_runtime_url` (env `OCR_RUNTIME_URL`, blank means managed, default blank). The managed router SHALL use the program in force (`llamacpp_server_binary`, else the provisioned pinned binary), the port of `llamacpp_router_url` and the model list `llamacpp_models`.

#### Scenario: Default modes

- **WHEN** no source sets a mode
- **THEN** the router MUST be `managed`, and every declared OCR runtime MUST be `managed`

#### Scenario: Managed embeddings argument list

- **WHEN** embeddings run on the `managed` router, `llamacpp_router_url` is `http://127.0.0.1:8080/v1`, the model limit is 4 and the margin is 8,192
- **THEN** no embeddings-only server MUST start, and the router argument list MUST equal `[binary, "--models-preset", "<state root>/runtimes/router/models.ini", "--models-max", "4", "--models-memory-margin", "8192", "--host", "127.0.0.1", "--port", "8080"]`

### Requirement: Runtime state lives in a per-runtime folder

Each runtime SHALL have a folder `<state root>/runtimes/<runtime id>/` that holds `start.lock`, `clients.lock`, `request.lock`, `server.json` and `server.log`. The router folder SHALL also hold `models.ini`, `hashes.json` and one folder `models/<model id>/` per listed model with its own `clients.lock` and `request.lock`, where `<model id>` is the first 16 hex characters of the SHA-256 of the model name. The state root SHALL be `OMRS_STATE_DIR`, else `$XDG_STATE_HOME/omrs`, else `~/.local/state/omrs`. Every OMRS process SHALL be allowed to write these files. They SHALL hold no secrets, SHALL be rebuilt from settings, and SHALL NOT be in the workspace database or `omrs.jsonc`. `server.json` and `models.ini` SHALL be written to a temporary file and renamed.

#### Scenario: CLI writes runtime state

- **WHEN** the CLI starts a managed runtime
- **THEN** `server.json` MUST appear under the state root, and `workspace.db` and `omrs.jsonc` MUST NOT change

#### Scenario: State root from the environment

- **WHEN** `OMRS_STATE_DIR` is `/tmp/s`
- **THEN** the router runtime folder MUST be `/tmp/s/runtimes/router/`

#### Scenario: Same model folder in every process

- **WHEN** the web app and the CLI both use `Qwen/Qwen3-4B-GGUF:Q8_0`
- **THEN** both MUST use the same `models/<model id>/` folder

### Requirement: A running server is adopted, and stale only by pid or command line

A process SHALL adopt a recorded server when its pid is alive, its command line holds the recorded binary path and its argument digest equals the wanted one. The router digest SHALL cover the binary path and the router argument list, and SHALL NOT cover the preset sections. A record SHALL be stale only when the pid is gone or the command line does not hold the recorded binary path. A stale pid SHALL NOT be signalled. A slow `/health`, a 503 answer or a long request in progress SHALL NOT make a server stale. OMRS SHALL read only the command lines of the recorded pid and of its direct children, and SHALL NOT list other processes.

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

#### Scenario: Preset edit is not a new router version

- **WHEN** a process wants a different `ctx-size` for one model while another process uses the router
- **THEN** the router MUST be adopted, not replaced, and only that model's rule in capability `llamacpp-router` MUST apply

### Requirement: A start checks the build and the declared files

Before a start, OMRS SHALL apply the program rule. For an OCR runtime it SHALL refuse with `wrong-build` when `<binary> --version` reports another build than the declared one. For the router it SHALL refuse with `wrong-build` when the build is below b11941. It SHALL refuse with `file-changed` when a declared OCR file does not match its SHA-256, and the reason line SHALL name the file. Router model files SHALL be checked per entry by capability `llamacpp-router`. A start SHALL wait up to 180 seconds for `GET /health` to return 200.

#### Scenario: Wrong build refused

- **WHEN** an OCR engine declares build 11941 and the binary reports build 11960
- **THEN** the runtime MUST be `failed` with `wrong-build` and no server MUST start

#### Scenario: Changed model file refused

- **WHEN** a declared OCR model file no longer matches its SHA-256
- **THEN** the runtime MUST be `failed` with `file-changed`, the reason line MUST name the file name, and no server MUST start

#### Scenario: Newer router build accepted

- **WHEN** the router binary reports build 11960
- **THEN** the router MUST start

### Requirement: Requests to a one-slot runtime wait for a request lock

A runtime whose argument list holds `-np 1` SHALL be a one-slot runtime. Each OMRS request to it SHALL hold `request.lock` exclusive while it runs. On the router, the lock SHALL be per model (capability `llamacpp-router`), and the router's own `request.lock` SHALL NOT be taken. The request timeout SHALL start when the lock is held. The wait for the lock SHALL have no timeout of its own.

#### Scenario: Second client waits without losing its timeout

- **WHEN** process A holds a 250-second OCR request on a one-slot runtime with a 300-second timeout and process B sends a request at the same time
- **THEN** process B's request MUST start after A's ends and MUST NOT time out because of the wait

#### Scenario: Router lock is per model

- **WHEN** a one-slot model on the router is busy and another process sends a request to a different model
- **THEN** the second request MUST NOT wait

### Requirement: A route lists the runtimes

`GET /v1/runtimes` SHALL need `read` and SHALL return one item per runtime in force with `id`, `role` (`router` or `ocr`), `mode`, `state` (`running`, `starting`, `stopped` or `failed`), `reason` from a fixed set, `reason_text`, `memory_bytes`, `clients` (`some` or `none`), `used_by`, `address`, `files_checked` and `models`. `models` SHALL be a list for the router (each with `model`, `roles`, `state`, `reason` and `memory_bytes`) and empty for OCR. It SHALL NOT start, stop or write anything. The route SHALL be in `openapi.yaml`. No response SHALL hold server output.

#### Scenario: List shape

- **WHEN** a client reads `GET /v1/runtimes`
- **THEN** each item MUST hold the listed fields and no other field

#### Scenario: Reading starts nothing

- **WHEN** a client reads `GET /v1/runtimes` while every runtime is stopped
- **THEN** no process MUST start and no runtime file MUST change

#### Scenario: Router models listed

- **WHEN** the router serves the embedding and Chat models
- **THEN** the router item's `models` MUST hold both, each with its roles

### Requirement: A route stops a managed runtime

`POST /v1/runtimes/{runtime_id}/stop` SHALL need a browser session with `manage` and SHALL refuse a bearer token. It SHALL return 404 for an unknown id and 409 with the reason `external-runtime` for an external runtime. The route SHALL be in `openapi.yaml`.

#### Scenario: Stop refused for a bearer token

- **WHEN** a bearer token with `manage` sends `POST /v1/runtimes/router/stop`
- **THEN** the server MUST refuse the request and MUST send no signal

#### Scenario: External runtime

- **WHEN** a session stops the `router` runtime while it is `external`
- **THEN** the server MUST return 409 with the reason `external-runtime` and MUST send no signal

#### Scenario: Old id unknown

- **WHEN** a session sends `POST /v1/runtimes/chat/stop`
- **THEN** the server MUST return 404

### Requirement: A managed decision runtime checks its build

Before the router serves a listed decision model, OMRS SHALL read the `llama-server` build number and refuse a build below the floor that serves decision requests with images (b11941). The refusal SHALL name the build found and the floor.

#### Scenario: Old build

- **GIVEN** a `llama-server` build below the floor and a listed decision model
- **WHEN** the router would start
- **THEN** it SHALL NOT start and the reason SHALL be `wrong-build`

## REMOVED Requirements

### Requirement: A local decision model can run as a managed runtime

**Reason**: A managed `llamacpp` decision model now runs as a model on the one router (capability `llamacpp-router`, "Decision models run on the router"). The runtime id `decision-<entry name>` retires.

**Migration**: Move each managed decision entry's model and projector files into a `llamacpp_models` entry, and set the decision entry's `model` to that entry's name. The `omrs.jsonc` problem list names each old field.
