## MODIFIED Requirements

### Requirement: omrs owns only the server it starts

The managed Chat server SHALL run on the shared runtime manager (capability `llamacpp-runtimes`) as the runtime `chat`, with at most one `llama-server`. OMRS SHALL stop, restart and report only a server that its runtime state records and whose command line holds the recorded binary path. It SHALL NOT find a process by name or by port, and SHALL NOT signal a process it did not start.

#### Scenario: User's own server on the port

- **WHEN** another `llama-server` that the user started listens on the chat port and the user presses Start
- **THEN** the state MUST be `failed` with reason `port-in-use`, and no signal MUST go to the other process

#### Scenario: Stop with nothing owned

- **WHEN** the user presses Stop and no recorded server runs
- **THEN** the server MUST send no signal to any process and the state MUST stay `stopped`

#### Scenario: No process lookup

- **WHEN** the code of the runtime manager is scanned
- **THEN** it MUST NOT call any process listing, `pkill`, `killall`, `lsof` or port lookup, and MUST read the command line of a recorded pid only

#### Scenario: Other transports

- **WHEN** the user runs the CLI or the stdio MCP server
- **THEN** neither MUST expose a command or tool that starts or stops `llama-server`

#### Scenario: Every process is a client

- **WHEN** the Chat choice is `managed`
- **THEN** `omrs web`, the CLI, the stdio MCP server and the watcher MUST each be allowed to start or adopt the server as a client

#### Scenario: Embedding server

- **WHEN** `llamacpp_embed_server` is not `managed`
- **THEN** OMRS MUST NOT manage a llama.cpp embedding server

#### Scenario: CLI answer starts the managed server

- **WHEN** the Chat choice is `managed`, no server runs and the CLI sends a Chat request
- **THEN** the CLI MUST start the server as a client and the request MUST succeed

### Requirement: Server settings and sources

The server SHALL have the settings `llamacpp_server_binary`, `llamacpp_chat_server` (`external` or `managed`, default `external`) and `llamacpp_context_window` (default 16,384, range 2,048 to 262,144). Each SHALL have an upper-case env name (for example `LLAMACPP_CHAT_SERVER`) and SHALL be settable in `omrs.jsonc` and in the llama.cpp card. `llamacpp_embed_server` SHALL be settable in the environment, `.env` and `omrs.jsonc`, and SHALL NOT be written by the Settings page.

#### Scenario: Config file sets all three

- **WHEN** `omrs.jsonc` holds `llamacpp_server_binary`, `llamacpp_chat_server` and `llamacpp_context_window`
- **THEN** `GET /v1/llamacpp/server` MUST report each with source `config-file` and `locked` false

#### Scenario: Context window range

- **WHEN** the user saves 1,000
- **THEN** the server MUST return 400 with the range and save nothing

#### Scenario: Program rule refused

- **WHEN** the user saves `~/.llama-app/llama` as the program
- **THEN** the server MUST return 400 with the program rule message, which starts "The program must be the absolute path of an executable file named llama-server", MUST NOT change the file, and the card MUST show that message in place of a generic error

#### Scenario: Unknown choice refused

- **WHEN** the user saves `chat_server` as `router`
- **THEN** the server MUST return 400, name the accepted values `external` and `managed`, and MUST NOT change the file

#### Scenario: Embedding mode not written by the page

- **WHEN** a client sends `PUT /v1/settings/configuration` with `llamacpp_embed_server`
- **THEN** the server MUST refuse the key and MUST NOT change `omrs.jsonc`

### Requirement: The argument list is fixed

The server SHALL build the argument list as a list from fixed flags only: `-m <path>` or `-hf <id>`, `--host 127.0.0.1`, `--port <n>` and `-c <n>`. It SHALL NOT pass `--sleep-idle-seconds`. The code SHALL start the process with no shell. The API and the settings SHALL NOT accept any other argument. The child SHALL receive a minimal environment that holds no provider API key.

#### Scenario: Exact arguments

- **WHEN** the server starts with the model `/m/q.gguf`, port 8081 and window 16,384
- **THEN** the argument list MUST equal `[binary, "-m", "/m/q.gguf", "--host", "127.0.0.1", "--port", "8081", "-c", "16384"]`

#### Scenario: No shell

- **WHEN** the model path holds a space or a `;`
- **THEN** the process call MUST use a list with no shell, and the text MUST reach the program as one argument or be refused by the model rule

#### Scenario: No extra argument

- **WHEN** a request body holds a field `args` or `extra_args`
- **THEN** the server MUST return 400 or ignore it, and MUST NOT pass it to the process

#### Scenario: Minimal environment

- **WHEN** the environment of `omrs web` holds `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` and `OPENAI_COMPATIBLE_API_KEY`
- **THEN** the environment of the child MUST hold none of them

#### Scenario: Cache variables only for a Hugging Face model

- **WHEN** `HF_TOKEN` and `LLAMA_CACHE` are set and the model is a local `.gguf` file
- **THEN** the environment of the child MUST hold neither of them

### Requirement: Scopes for server control

Every server route SHALL need the browser session. Changing the program path or the Chat server choice SHALL need the `credentials` scope on every route that can write it. While the choice is `managed`, every route that writes a llama.cpp Chat choice SHALL need the `credentials` scope. The context window, start, stop and restart SHALL need `manage`. `GET /v1/llamacpp/server` SHALL need `read`. A bearer token SHALL NOT pass any route that writes or controls.

#### Scenario: Bearer token refused

- **WHEN** a client uses a bearer token with `manage` on `POST /v1/llamacpp/server/start`
- **THEN** the server MUST refuse the request

#### Scenario: Model change needs credentials

- **WHEN** the choice is `managed` and a browser session with `manage` but not `credentials` sends `PUT /v1/settings/chat` with the provider `llamacpp` and a new model
- **THEN** the server MUST return 403 and save nothing

#### Scenario: The Configuration page cannot skip the scope

- **WHEN** the choice is `managed` and a browser session with `manage` but not `credentials` sends `PUT /v1/settings/configuration` with `answer.model` while the Chat provider is `llamacpp`
- **THEN** the server MUST return 403 and save nothing

#### Scenario: The Configuration page cannot skip the program rule

- **WHEN** a browser session with `manage` but not `credentials` sends `PUT /v1/settings/configuration` with `llamacpp_server_binary`
- **THEN** the server MUST return 403 and save nothing
- **AND WHEN** a session with `credentials` sends a path that is not an executable file named `llama-server`
- **THEN** the server MUST return 400, name the rule and save nothing

#### Scenario: Chat server choice needs credentials

- **WHEN** a browser session with `manage` but not `credentials` sends `PUT /v1/llamacpp/server` with `chat_server`
- **THEN** the server MUST refuse the request and save nothing

#### Scenario: External Chat save needs manage only

- **WHEN** the choice is `external` and a browser session with `manage` but not `credentials` saves the Chat provider `llamacpp` and a model
- **THEN** the server MUST accept the request

#### Scenario: Window change needs manage

- **WHEN** a browser session with `manage` sends `PUT /v1/llamacpp/server` with only a new context window
- **THEN** the server MUST accept the request

#### Scenario: Start needs manage

- **WHEN** a browser session with `manage` presses Start
- **THEN** the server MUST accept the request

### Requirement: Lifecycle states and fixed reasons

The server state SHALL be one of `stopped`, `starting`, `running` and `failed`. A `failed` state SHALL carry one reason from `binary-invalid`, `model-invalid`, `not-loopback`, `port-in-use`, `exited`, `timeout`, `not-configured`, `not-supported` and `version-busy`.

#### Scenario: Reasons are fixed

- **WHEN** the process writes any text to its output
- **THEN** the reason in the status MUST be one of the nine fixed values and MUST NOT hold that text

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

The output of the server SHALL go to `server.log` in the runtime folder `<state root>/runtimes/chat/`. The file SHALL be emptied at each start. OMRS SHALL empty it again when it passes 5 MiB, checked after each request. No route SHALL return the file or any output of the server. The page SHALL NOT show it.

#### Scenario: Output to file

- **WHEN** the server runs and writes text
- **THEN** the text MUST appear in `server.log` in the Chat runtime folder

#### Scenario: Size cap

- **WHEN** the log holds more than 5 MiB and a Chat request ends
- **THEN** the file MUST hold less than 5 MiB after that request

#### Scenario: Not returned

- **WHEN** the user reads any `/v1/llamacpp/server` route, `GET /v1/runtimes` or `GET /v1/logs`
- **THEN** no response MUST hold text from the server process

### Requirement: Routes

The server SHALL expose `GET /v1/llamacpp/server`, `PUT /v1/llamacpp/server`, `POST /v1/llamacpp/server/start`, `POST /v1/llamacpp/server/stop` and `POST /v1/llamacpp/server/restart`. `GET` SHALL return the state, the reason, the values the running process started with, the saved values with their sources and locks, and the Chat model in force. `PUT` SHALL save the server settings, with 400 for a rule failure and 409 for a locked field. The routes SHALL appear in `openapi.yaml`.

#### Scenario: Status shape

- **WHEN** the user reads `GET /v1/llamacpp/server`
- **THEN** the body MUST hold `state`, `reason`, `running_with`, `shared_with_classification`, `chat_model` with `provider`, `model` and `usable`, and `saved` with `binary`, `chat_server` and `context_window`, each with `source` and `locked`

#### Scenario: Locked field

- **WHEN** the program comes from the environment and the user sends `PUT` with a new program
- **THEN** the server MUST return 409 and name the variable

#### Scenario: Model key refused

- **WHEN** a `PUT /v1/llamacpp/server` body holds `model`
- **THEN** the server MUST return 400, save nothing, and the message MUST say that the Chat model is set in Settings > Chat

#### Scenario: Idle sleep key refused

- **WHEN** a `PUT /v1/llamacpp/server` body holds `idle_sleep`
- **THEN** the server MUST return 400, save nothing, and the message MUST say that OMRS stops an idle server after 10 minutes

#### Scenario: Contract

- **WHEN** the OpenAPI contract test runs
- **THEN** all five routes MUST be present and match the responses

## REMOVED Requirements

### Requirement: Idle sleep frees the model of the managed server

**Reason**: llama-server's `--sleep-idle-seconds` has an open race that loses a request or crashes the server (llama.cpp issue #29689). The runtime manager stops an idle runtime after a fixed 10 minutes instead.

**Migration**: Remove `LLAMACPP_IDLE_SLEEP_SECONDS` from the environment and `.env`, and `llamacpp_idle_sleep_seconds` from `omrs.jsonc`. No replacement setting exists.

## ADDED Requirements

### Requirement: The idle sleep setting is retired

OMRS SHALL NOT read `llamacpp_idle_sleep_seconds` or `LLAMACPP_IDLE_SLEEP_SECONDS`. When the environment or `.env` sets `LLAMACPP_IDLE_SLEEP_SECONDS`, start-up SHALL fail with a message that names it and the fixed 10-minute idle stop. A `llamacpp_idle_sleep_seconds` key in `omrs.jsonc` SHALL be ignored and listed in the problem list.

#### Scenario: Old name in .env

- **WHEN** `.env` sets `LLAMACPP_IDLE_SLEEP_SECONDS`
- **THEN** start-up MUST fail, and the message MUST name `LLAMACPP_IDLE_SLEEP_SECONDS` and say that OMRS stops an idle server after 10 minutes

#### Scenario: Old key in omrs.jsonc

- **WHEN** `omrs.jsonc` holds `"llamacpp_idle_sleep_seconds": 300`
- **THEN** `omrs web` MUST start and the problem list MUST name `llamacpp_idle_sleep_seconds`
