# llamacpp-server Specification

## Purpose
Lets `omrs web` start, stop and restart one `llama-server` for Chat. Covers ownership, settings, launch guardrails, lifecycle states with fixed reasons, routes and scopes, and the log file. The stdio MCP server and the CLI never manage it.

## Requirements

### Requirement: omrs owns only the server it starts

The managed router SHALL run on the shared runtime manager (capability `llamacpp-runtimes`) as the runtime `router`, with at most one `llama-server` router process and its model child processes. OMRS SHALL stop, restart and report only a server that the runtime state records and whose command line holds the recorded binary path. It SHALL NOT find a process by name or by port, and SHALL NOT signal a process it did not start.

#### Scenario: User's own server on the port

- **WHEN** another `llama-server` that the user started listens on the router port and the user presses Start
- **THEN** the state MUST be `failed` with the reason `port-in-use`, and no signal MUST go to the other process

#### Scenario: Stop with nothing owned

- **WHEN** the user presses Stop and no recorded server runs
- **THEN** the server MUST send no signal to any process and the state MUST stay `stopped`

#### Scenario: No process lookup

- **WHEN** the code of the runtime manager is scanned
- **THEN** it MUST NOT call any process listing, `pkill`, `killall`, `lsof` or port lookup, and MUST read only the command lines of the recorded pid and its direct children

#### Scenario: Other transports

- **WHEN** the user runs the CLI or the stdio MCP server
- **THEN** neither MUST expose a command or tool that starts or stops `llama-server`

#### Scenario: Every process is a client

- **WHEN** the router is `managed`
- **THEN** `omrs web`, the CLI, the stdio MCP server and the watcher MUST each be allowed to start or adopt it

#### Scenario: Embedding server

- **WHEN** `llamacpp_router_server` is `external`
- **THEN** OMRS MUST NOT manage any llama.cpp server for embeddings

#### Scenario: CLI answer starts the managed server

- **WHEN** the router is `managed`, no server runs and the CLI sends a Chat request
- **THEN** the CLI MUST start the router as a client and the request MUST succeed

### Requirement: Server settings and sources

The server SHALL have the settings `llamacpp_server_binary`, `llamacpp_router_server`, `llamacpp_router_url`, `llamacpp_router_models_max` and `llamacpp_router_memory_margin_mib`. Each SHALL have an upper-case env name (for example `LLAMACPP_ROUTER_SERVER`) and SHALL be settable in `omrs.jsonc` and in the Router panel. The model list `llamacpp_models` SHALL be settable in `omrs.jsonc` and in the Router panel only.

#### Scenario: Config file sets all three

- **WHEN** `omrs.jsonc` holds `llamacpp_server_binary`, `llamacpp_router_server` and `llamacpp_router_url`
- **THEN** `GET /v1/llamacpp/router` MUST report the source `config-file` and `locked` false for each

#### Scenario: Context window range

- **WHEN** the user saves a context size of 100 for a list entry
- **THEN** the server MUST return 400 with the range 512 to 262,144 and save nothing

#### Scenario: Program rule refused

- **WHEN** the user saves `~/.llama-app/llama` as the program
- **THEN** the server MUST return 400 with the program rule message, which starts "The program must be an absolute path to an executable file named llama-server", MUST NOT change the file, and the panel MUST show the message in place of a generic error

#### Scenario: Unknown choice refused

- **WHEN** the user saves `router_server` as `auto`
- **THEN** the server MUST return 400, name the accepted values `external` and `managed`, and MUST NOT change the file

#### Scenario: Embedding mode not written by the page

- **WHEN** a client sends `PUT /v1/settings/configuration` with the retired key `llamacpp_embed_server`
- **THEN** the server MUST refuse the key and MUST NOT change `omrs.jsonc`

### Requirement: Saved server settings follow the provider source order

A panel save SHALL write `omrs.jsonc`. The source order of provider settings SHALL apply: environment and `.env` (both lock), then `omrs.jsonc` (does not lock), then the default. A changed router argument SHALL apply at the next start of the owned router. A changed model entry SHALL apply by the reload rule of capability `llamacpp-router`. The port SHALL come from `llamacpp_router_url`.

#### Scenario: Saved from the GUI

- **WHEN** no environment value exists and the user saves the router mode, address and model limit
- **THEN** `omrs.jsonc` MUST hold them and their sources MUST be `config-file`

#### Scenario: Environment wins

- **WHEN** `LLAMACPP_ROUTER_URL=http://127.0.0.1:8090/v1` is in the environment and the user saves another value
- **THEN** the server MUST return 409 and name the variable

### Requirement: The program must be a file named llama-server

The program path SHALL be an absolute path to a regular file that is executable and whose file name is exactly `llama-server`. The server SHALL check this at save and before every launch. A path that fails SHALL be refused with 400 at save, or with state `failed` and reason `binary-invalid` at launch.

#### Scenario: Valid program

- **WHEN** the path is `/opt/llama/bin/llama-server`, a regular executable file
- **THEN** the server MUST accept it

#### Scenario: Relative path

- **WHEN** the path is `llama-server` or `./bin/llama-server`
- **THEN** the server MUST refuse it

#### Scenario: Other file name

- **WHEN** the path is `/bin/sh` or `/opt/llama/bin/llama-server-old`
- **THEN** the server MUST refuse it

#### Scenario: Not executable or not a file

- **WHEN** the path names a directory or a file without the execute permission
- **THEN** the server MUST refuse it

#### Scenario: Changed after save

- **WHEN** the saved file is replaced by a directory and the user presses Start
- **THEN** the state MUST be `failed` with reason `binary-invalid` and no process MUST start

### Requirement: The program check follows symlinks

The check SHALL follow a symlink to its target file. The file name SHALL be exactly `llama-server` both for the path as given and for the target after links are resolved (`llama-server.exe` on Windows).

#### Scenario: Symlink to a file with another name

- **WHEN** the path is a symlink named `llama-server` whose target file has another name
- **THEN** the server MUST refuse it

### Requirement: Port must be loopback

In managed mode the port SHALL come from `llamacpp_router_url`. The URL MUST use `http` and a loopback host (`127.0.0.1`, `localhost` or `::1`). Otherwise the launch SHALL fail with state `failed` and reason `not-loopback`, and no process SHALL start. The router SHALL bind `127.0.0.1`.

#### Scenario: Remote chat URL

- **WHEN** Chat runs on the `managed` router, `llamacpp_router_url` is `http://192.168.1.20:8080/v1` and the user presses Start
- **THEN** the state MUST be `failed` with the reason `not-loopback`

#### Scenario: Loopback chat URL

- **WHEN** Chat runs on the `managed` router and `llamacpp_router_url` is `http://localhost:8080/v1`
- **THEN** the router MUST start with `--host 127.0.0.1 --port 8080`

### Requirement: The argument list is fixed

The router SHALL be built from fixed flags only: `--models-preset <state root>/runtimes/router/models.ini`, `--models-max <n>`, `--models-memory-margin <n>`, `--host 127.0.0.1` and `--port <n>`. Model files and preset values SHALL reach it only through `models.ini` (capability `llamacpp-router`). It SHALL NOT pass `--sleep-idle-seconds`, `--api-key` or `--models-dir`.

#### Scenario: Exact arguments

- **WHEN** the router starts on port 8080 with model limit 4 and margin 8,192
- **THEN** the argument list MUST equal `[binary, "--models-preset", "<state root>/runtimes/router/models.ini", "--models-max", "4", "--models-memory-margin", "8192", "--host", "127.0.0.1", "--port", "8080"]`

### Requirement: The router starts without a shell or a free-text argument

The code SHALL start the process with no shell. No API or setting SHALL add a free-text argument.

#### Scenario: No shell

- **WHEN** an entry's file path holds a space or a `;`
- **THEN** the process call MUST use a list with no shell, and the path MUST reach `models.ini` as one value or be refused by the entry rule

#### Scenario: No extra argument

- **WHEN** a request body holds a field `args` or `extra_args`
- **THEN** the server MUST return 400 or ignore it, and MUST NOT pass it to the process

### Requirement: The router child gets a minimal environment

The child SHALL receive a minimal environment that holds no provider API key and no Hugging Face cache or token variable. It SHALL set `LLAMA_CACHE` to `<state root>/runtimes/router/empty-cache` and `XDG_CONFIG_HOME` to `<state root>/runtimes/router/empty-config`, two empty folders OMRS creates, so the router lists no cache model and reads no user `config.ini`.

#### Scenario: Minimal environment

- **WHEN** the environment of `omrs web` holds `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` and `OPENAI_COMPATIBLE_API_KEY`
- **THEN** the environment of the child MUST hold none of them

#### Scenario: Cache variables only for a Hugging Face model

- **WHEN** `HF_TOKEN`, `HF_HOME` and `LLAMA_CACHE=/data/cache` are set in the environment of `omrs web`, and every list entry loads by file path
- **THEN** the environment of the child MUST NOT hold `HF_TOKEN` or `HF_HOME`, and its `LLAMA_CACHE` MUST be `<state root>/runtimes/router/empty-cache`

#### Scenario: No user llama.cpp config file

- **WHEN** `XDG_CONFIG_HOME` is set in the environment of `omrs web`
- **THEN** the environment of the child MUST set `XDG_CONFIG_HOME` to `<state root>/runtimes/router/empty-config`, and that folder MUST be empty

### Requirement: Scopes for server control

Every router route SHALL need a browser session. Changing the program path, the router mode or an entry's `model`, `file` or `projector` SHALL need the `credentials` scope. Changing an entry's preset values, the address, the model limit or the margin, and Start, Stop and Restart, SHALL need `manage`. `GET /v1/llamacpp/router` SHALL need `read`. A bearer token SHALL NOT pass any route that writes or controls.

#### Scenario: Bearer token refused

- **WHEN** a client uses a bearer token with `manage` on `POST /v1/llamacpp/router/start`
- **THEN** the server MUST refuse the request

#### Scenario: Model change needs credentials

- **WHEN** a browser session with `manage` but not `credentials` changes an entry's `model` or `file`
- **THEN** the server MUST return 403 and save nothing

#### Scenario: The Configuration page cannot skip the scope

- **WHEN** a browser session with `manage` but not `credentials` sends `PUT /v1/settings/configuration` with `llamacpp_router_server`
- **THEN** the server MUST return 403 and save nothing

#### Scenario: The Configuration page cannot skip the program rule

- **WHEN** a browser session with `manage` but not `credentials` sends `PUT /v1/settings/configuration` with `llamacpp_server_binary`
- **THEN** the server MUST return 403 and save nothing
- **AND WHEN** a session with `credentials` sends a path that is not an executable file named `llama-server`
- **THEN** the server MUST return 400, name the rule and save nothing

#### Scenario: Chat server choice needs credentials

- **WHEN** a browser session with `manage` but not `credentials` sends `PUT /v1/llamacpp/router` with `router_server`
- **THEN** the server MUST refuse the request and save nothing

#### Scenario: External Chat save needs manage only

- **WHEN** a browser session with `manage` but not `credentials` saves the Chat provider `llamacpp` and a model that a list entry holds
- **THEN** the server MUST accept the request, in both router modes, because the save changes no model file

#### Scenario: Window change needs manage

- **WHEN** a browser session with `manage` changes only an entry's `ctx-size`
- **THEN** the server MUST accept the request

#### Scenario: Start needs manage

- **WHEN** a browser session with `manage` presses Start
- **THEN** the server MUST accept the request

### Requirement: Lifecycle states and fixed reasons

The router state SHALL be one of `stopped`, `starting`, `running` and `failed`. A `failed` state SHALL carry one reason from `binary-invalid`, `file-changed`, `not-loopback`, `port-in-use`, `bind-failed`, `exited`, `timeout`, `not-configured`, `not-downloaded`, `not-provisioned`, `not-supported`, `version-busy` and `wrong-build`.

#### Scenario: Reasons are fixed

- **WHEN** the process writes any text output
- **THEN** each reason in the status MUST be one of the fixed values and MUST NOT hold that text

### Requirement: Model states and fixed reasons

A model's state SHALL be one of `not-downloaded`, `unloaded`, `loading`, `loaded` and `failed`, and a failed model SHALL carry one reason from `model-invalid`, `file-changed`, `preset-invalid`, `model-load-failed`, `model-not-listed`, `role-mismatch` and `version-busy`. A request to a `not-downloaded` model SHALL be refused with the reason `not-downloaded` before any contact.

#### Scenario: Model not downloaded yet

- **WHEN** a request names a list entry whose file is missing
- **THEN** it MUST be refused with `not-downloaded` and the router MUST NOT be contacted

### Requirement: Start moves to running or to a failed state

Start SHALL move to `starting`, then poll `GET /health` on the owned port until it returns 200, then move to `running`. No model SHALL load at start. The wait SHALL end after 180 seconds with the reason `timeout`. An exit of the process while `starting` or `running` SHALL give `failed` with the reason `exited`.

#### Scenario: Healthy start

- **WHEN** the router starts and `GET /health` returns 200 after 2 seconds
- **THEN** the state MUST move from `starting` to `running` and every listed model MUST be `unloaded`

#### Scenario: Timeout

- **WHEN** `GET /health` does not return 200 within 180 seconds
- **THEN** the state MUST be `failed` with the reason `timeout` and the owned process MUST be stopped

#### Scenario: Exit while starting

- **WHEN** the process exits with a code before `/health` returns 200
- **THEN** the state MUST be `failed` with the reason `exited`

#### Scenario: Exit while running

- **WHEN** the running router is killed from outside
- **THEN** the next status read MUST show `failed` with the reason `exited`

#### Scenario: Graceful stop

- **WHEN** the router and its children end on SIGTERM within 10 seconds
- **THEN** OMRS MUST send no SIGKILL and the state MUST be `stopped`

#### Scenario: Forced stop

- **WHEN** the router ignores SIGTERM
- **THEN** OMRS MUST send SIGKILL to the process group after 10 seconds

#### Scenario: No child survives

- **WHEN** the router runs two loaded models and the user presses Stop
- **THEN** no model child process MUST run after the stop ends

#### Scenario: Restart uses saved values

- **WHEN** the user saves a new model limit and presses Restart
- **THEN** the new process MUST start with the new `--models-max` value

#### Scenario: Exit of omrs web

- **WHEN** `omrs web` shuts down while the router runs and no other OMRS process uses it
- **THEN** the router process group MUST be stopped before `omrs web` exits

#### Scenario: Exit of omrs web while the CLI uses it

- **WHEN** `omrs web` shuts down while a CLI process still sends embedding requests
- **THEN** the router MUST keep running

#### Scenario: Status shows both value sets

- **WHEN** the saved router arguments differ from those the running process started with
- **THEN** the status MUST report both sets, so the panel can show "Restart to apply"

#### Scenario: Save keeps it running

- **WHEN** the user saves a new context size for the Chat entry while the router runs
- **THEN** the router process MUST keep running and the Chat row MUST show `reload_pending` until the reload ends

### Requirement: Start refuses an unprovisioned or empty router

A blank program with no provisioned binary SHALL give `not-provisioned`, whose text names `omrs llamacpp install` and the Get llama.cpp action. A list with no entry SHALL give `not-configured`. A list in which no entry has a file SHALL give `not-downloaded` (see "A first start waits for its downloads").

#### Scenario: Nothing provisioned

- **WHEN** `llamacpp_server_binary` is blank and no pinned build is installed
- **THEN** the router MUST be `failed` with `not-provisioned`, and no process MUST start

#### Scenario: Not configured

- **WHEN** the model list has no entry and the user presses Start
- **THEN** the state MUST be `failed` with the reason `not-configured` and no process MUST start

### Requirement: Stop and restart

Stop SHALL send SIGTERM to the process group of the recorded server, wait up to 10 seconds, then send SIGKILL to the group, and SHALL record an operator stop. Restart SHALL stop the recorded server and then start it with the saved values. When `omrs web` exits, the server SHALL stop only when no other OMRS process uses it. A save SHALL NOT stop a running server.

#### Scenario: Graceful stop

- **WHEN** the server ends on SIGTERM within 10 seconds
- **THEN** OMRS MUST send no SIGKILL and the state MUST be `stopped`

#### Scenario: Forced stop

- **WHEN** the server ignores SIGTERM
- **THEN** OMRS MUST send SIGKILL to the process group after 10 seconds

#### Scenario: Restart uses saved values

- **WHEN** the user saves a new context window and presses Restart
- **THEN** the new process MUST start with the new `-c` value

#### Scenario: Exit of omrs web

- **WHEN** `omrs web` shuts down while the server runs and no other OMRS process uses it
- **THEN** the server process group MUST be stopped before `omrs web` exits

#### Scenario: Exit of omrs web while the CLI uses it

- **WHEN** `omrs web` shuts down while a CLI process still sends Chat requests
- **THEN** the server MUST keep running

#### Scenario: Status shows both value sets

- **WHEN** the saved values differ from the values the running process started with
- **THEN** the status MUST report both sets, so the page can show "Restart to apply"

#### Scenario: Save keeps it running

- **WHEN** the user saves a new Chat model while the server runs
- **THEN** the process MUST keep running and the status MUST show saved and running values that differ

### Requirement: The server log stays on disk

The output of the router and its model children SHALL go to `server.log` in the runtime folder `<state root>/runtimes/router/`. The file SHALL be emptied at start. OMRS SHALL empty it again when it passes 5 MiB, checked after a request. No route SHALL return the file or any output of the server. The page SHALL NOT show it.

#### Scenario: Output to file

- **WHEN** the router runs and writes text
- **THEN** the text MUST appear in `server.log` in the router runtime folder

#### Scenario: Size cap

- **WHEN** the log holds more than 5 MiB and a request ends
- **THEN** the file MUST hold less than 5 MiB after the request

#### Scenario: Not returned

- **WHEN** the user reads any `/v1/llamacpp/router` route, `GET /v1/runtimes` or `GET /v1/logs`
- **THEN** no response MUST hold text of the server process

### Requirement: Routes

The server SHALL expose `GET /v1/llamacpp/router`, `PUT /v1/llamacpp/router`, `PUT /v1/llamacpp/router/models/{id}`, `DELETE /v1/llamacpp/router/models/{id}`, `POST /v1/llamacpp/router/start`, `POST /v1/llamacpp/router/stop`, `POST /v1/llamacpp/router/restart`, `POST /v1/llamacpp/router/install` and `GET /v1/llamacpp/router/install`. The routes SHALL appear in `openapi.yaml`.

#### Scenario: Status shape

- **WHEN** the user reads `GET /v1/llamacpp/router`
- **THEN** the body MUST hold `state`, `reason`, `mode`, `address`, `running_with`, `saved` with `binary`, `router_server`, `router_url`, `models_max` and `memory_margin_mib` (each with `source` and `locked`), and `models` with `id`, `model`, `roles`, `file`, `ctx_size`, `state`, `reason` and `reload_pending`

#### Scenario: Contract

- **WHEN** the OpenAPI contract test runs
- **THEN** all nine routes MUST be present and match their responses

### Requirement: The PUT route and the removed routes

`PUT` SHALL return 400 for a rule failure and 409 for a locked field. The old `/v1/llamacpp/server` routes SHALL NOT exist.

#### Scenario: Locked field

- **WHEN** the program comes from the environment and the user sends `PUT` with a new program
- **THEN** the server MUST return 409 and name the variable

#### Scenario: Model key refused

- **WHEN** a `PUT /v1/llamacpp/router` body holds `model`
- **THEN** the server MUST return 400, save nothing, and the message MUST say that models are set in the model table

#### Scenario: Idle sleep key refused

- **WHEN** a `PUT /v1/llamacpp/router` body holds `idle_sleep`
- **THEN** the server MUST return 400, save nothing, and the message MUST say that OMRS stops an idle server after 10 minutes

#### Scenario: Old route gone

- **WHEN** a client sends `GET /v1/llamacpp/server`
- **THEN** the server MUST return 404

### Requirement: The old server model setting is retired

OMRS SHALL NOT read `llamacpp_server_model` or `LLAMACPP_SERVER_MODEL`. When the environment or `.env` sets `LLAMACPP_SERVER_MODEL`, start-up SHALL fail with a message that names it and its replacement. A `llamacpp_server_model` key in `omrs.jsonc` SHALL be ignored and listed in the problem list with the replacement `answer.model`. Its value SHALL NOT become the Chat model.

#### Scenario: Old name in .env

- **WHEN** `.env` sets `LLAMACPP_SERVER_MODEL`
- **THEN** start-up MUST fail, and the message MUST name `LLAMACPP_SERVER_MODEL`, `ANSWER__PROVIDER`, `ANSWER__MODEL` and `LLAMACPP_CHAT_SERVER`

#### Scenario: Old key in omrs.jsonc

- **WHEN** `omrs.jsonc` holds `"llamacpp_server_model": "Qwen/Qwen3-4B-GGUF:Q4_K_M"`
- **THEN** `omrs web` MUST start, the problem list MUST name `llamacpp_server_model` and `answer.model`, and the Chat model MUST stay as the other sources set it

### Requirement: The idle sleep setting is retired

OMRS SHALL NOT read `llamacpp_idle_sleep_seconds` or `LLAMACPP_IDLE_SLEEP_SECONDS`. When the environment or `.env` sets `LLAMACPP_IDLE_SLEEP_SECONDS`, start-up SHALL fail with a message that names it and the fixed 10-minute idle stop. A `llamacpp_idle_sleep_seconds` key in `omrs.jsonc` SHALL be ignored and listed in the problem list.

#### Scenario: Old name in .env

- **WHEN** `.env` sets `LLAMACPP_IDLE_SLEEP_SECONDS`
- **THEN** start-up MUST fail, and the message MUST name `LLAMACPP_IDLE_SLEEP_SECONDS` and say that OMRS stops an idle server after 10 minutes

#### Scenario: Old key in omrs.jsonc

- **WHEN** `omrs.jsonc` holds `"llamacpp_idle_sleep_seconds": 300`
- **THEN** `omrs web` MUST start and the problem list MUST name `llamacpp_idle_sleep_seconds`

### Requirement: The per-role server settings are retired

OMRS SHALL NOT read `llamacpp_embed_url`, `llamacpp_chat_url`, `llamacpp_classify_url`, `llamacpp_chat_server`, `llamacpp_embed_server` or `llamacpp_context_window`. An environment or `.env` value of one of them SHALL fail start-up with a message that names the variable and its replacement. An `omrs.jsonc` key SHALL be ignored and listed in the problem list as retired with its replacement.

#### Scenario: Old address in .env

- **WHEN** `.env` sets `LLAMACPP_EMBED_URL`
- **THEN** start-up MUST fail, and the message MUST name `LLAMACPP_EMBED_URL` and `LLAMACPP_ROUTER_URL`

#### Scenario: Old window in omrs.jsonc

- **WHEN** `omrs.jsonc` holds `"llamacpp_context_window": 16384`
- **THEN** `omrs web` MUST start, the problem list MUST name `llamacpp_context_window` and `llamacpp_models`, and no entry's `ctx_size` MUST change

#### Scenario: Old mode in the environment

- **WHEN** the environment sets `LLAMACPP_CHAT_SERVER=managed`
- **THEN** start-up MUST fail, and the message MUST name `LLAMACPP_CHAT_SERVER` and `LLAMACPP_ROUTER_SERVER`

### Requirement: A first start waits for its downloads

While an automatic download of a listed model is queued or runs, a Start SHALL give the state `starting` with the reason `not-downloaded` and the line "Models are still downloading.", and SHALL NOT give `failed`. When the last queued download ends, OMRS SHALL start the router and load the models that have files, unless the operator stopped the router or the mode became `external`. OMRS SHALL NOT store `not-downloaded` in the runtime record.

#### Scenario: First start waits then starts by itself

- **WHEN** no listed model has a file and the user confirms Start
- **THEN** the state MUST be `starting` with the line "Models are still downloading."
- **AND** when the last download ends the router MUST start without another press

#### Scenario: Stop during the download

- **WHEN** the user presses Stop while the downloads run
- **THEN** the router MUST stay stopped after the downloads end

#### Scenario: Every download fails

- **WHEN** every queued download fails or is cancelled
- **THEN** the state MUST be `failed` with `not-downloaded` and the line "No model is downloaded yet."
- **AND** OMRS MUST queue no download again until the user presses Start

#### Scenario: Server restart after a wait

- **WHEN** the web server restarts while a router that never started waited for downloads
- **THEN** the router MUST show `stopped`
