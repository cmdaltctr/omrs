# llamacpp-server Specification

## Purpose
Lets `omrs web` start, stop and restart one `llama-server` for Chat. Covers ownership, settings, launch guardrails, lifecycle states with fixed reasons, routes and scopes, and the log file. The stdio MCP server and the CLI never manage it.

## Requirements

### Requirement: omrs owns only the server it starts

`omrs web` SHALL start at most one `llama-server` for Chat and SHALL keep the handle of that process. It SHALL stop, restart and report only that process. It SHALL NOT find a process by name or by port. It SHALL NOT signal a process it did not start. The stdio MCP server and the CLI SHALL NOT start or stop the server. The llama.cpp embedding server SHALL NOT be managed.

#### Scenario: User's own server on the port

- **WHEN** another `llama-server` that the user started listens on the chat port and the user presses Start
- **THEN** the state MUST be `failed` with reason `port-in-use`, and no signal MUST go to the other process

#### Scenario: Stop with nothing owned

- **WHEN** the user presses Stop and omrs owns no process
- **THEN** the server MUST send no signal to any process and the state MUST stay `stopped`

#### Scenario: No process lookup

- **WHEN** the code of the lifecycle module is scanned
- **THEN** it MUST NOT call any process listing, `pkill`, `killall`, `lsof` or port lookup

#### Scenario: Other transports

- **WHEN** the user runs the CLI or the stdio MCP server
- **THEN** neither MUST expose a command or tool that starts or stops `llama-server`

### Requirement: Server settings and sources

The server SHALL have the settings `llamacpp_server_binary` (env `LLAMACPP_SERVER_BINARY`), `llamacpp_chat_server` (env `LLAMACPP_CHAT_SERVER`, `external` or `managed`, default `external`), `llamacpp_context_window` (env `LLAMACPP_CONTEXT_WINDOW`, default 16,384, range 2,048 to 262,144) and `llamacpp_idle_sleep_seconds` (env `LLAMACPP_IDLE_SLEEP_SECONDS`, default 300, range 0 to 86,400, 0 turns sleep off). Each SHALL be settable in `omrs.jsonc` and in the llama.cpp card.

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

### Requirement: Saved server settings follow the provider source order

A card save SHALL write `omrs.jsonc`. The source order of the provider settings SHALL apply: the environment and `.env` (both lock), then `omrs.jsonc` (does not lock), then the default. A changed value SHALL apply at the next start of the owned server. The port SHALL come from `llamacpp_chat_url`.

#### Scenario: Saved from the GUI

- **WHEN** no environment value exists and the user saves the three values
- **THEN** `omrs.jsonc` MUST hold them and the sources MUST be `config-file`

#### Scenario: Environment wins

- **WHEN** `LLAMACPP_CONTEXT_WINDOW=8192` is in the environment and the user saves another value
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

### Requirement: The model must be a gguf file or a Hugging Face id

When the Chat server choice is `managed`, the Chat model SHALL be one of: an absolute path to an existing file with the extension `.gguf`, or a well-formed Hugging Face id `org/name` with an optional `:tag`. The model SHALL NOT start with `-`. The server SHALL check this at a Chat save and before every launch. A failure SHALL give 400 at save, or state `failed` and reason `model-invalid` at launch.

#### Scenario: Gguf path

- **WHEN** the Chat model is `/models/qwen3-4b-q8_0.gguf` and the file exists
- **THEN** the server MUST accept it and pass it with `-m`

#### Scenario: Hugging Face id

- **WHEN** the Chat model is `Qwen/Qwen3-0.6B-GGUF:Q8_0`
- **THEN** the server MUST accept it and pass it with `-hf`

#### Scenario: Leading dash

- **WHEN** the Chat model is `--api-key` or `-m`
- **THEN** the server MUST refuse it

#### Scenario: Missing file

- **WHEN** the Chat model is an absolute `.gguf` path that does not exist
- **THEN** the server MUST refuse it

#### Scenario: Malformed id

- **WHEN** the Chat model is `a b`, `org/`, `../x`, `qwen3:4b` or an id with a space or a shell character
- **THEN** the server MUST refuse it

#### Scenario: Ollama-style name at save

- **WHEN** the choice is `managed` and the user saves the Chat provider `llamacpp` with the model `qwen3:4b`
- **THEN** `PUT /v1/settings/chat` MUST return 400 with the model rule message and MUST NOT change `omrs.jsonc`

#### Scenario: External server keeps any name

- **WHEN** the choice is `external` and the user saves the Chat provider `llamacpp` with the model `my-model`
- **THEN** the save MUST succeed

### Requirement: Port must be loopback

The port SHALL come from `llamacpp_chat_url`. The URL MUST use `http` and a loopback host (`127.0.0.1`, `localhost` or `::1`). Otherwise the launch SHALL fail with state `failed` and reason `not-loopback`, and no process SHALL start. The server SHALL bind to `127.0.0.1`.

#### Scenario: Remote chat URL

- **WHEN** `llamacpp_chat_url` is `http://192.168.1.20:8081/v1` and the user presses Start
- **THEN** the state MUST be `failed` with reason `not-loopback`

#### Scenario: Loopback chat URL

- **WHEN** `llamacpp_chat_url` is `http://localhost:8081/v1`
- **THEN** the server MUST start with `--host 127.0.0.1 --port 8081`

### Requirement: The argument list is fixed

The server SHALL build the argument list as a list from fixed flags only: `-m <path>` or `-hf <id>`, `--host 127.0.0.1`, `--port <n>`, `--sleep-idle-seconds <n>` only when the idle sleep is above 0, and `-c <n>`. The code SHALL start the process with no shell. The API and the settings SHALL NOT accept any other argument. The child SHALL receive a minimal environment that holds no provider API key.

#### Scenario: Exact arguments

- **WHEN** the server starts with the model `/m/q.gguf`, port 8081 and window 16,384
- **THEN** the argument list MUST equal `[binary, "-m", "/m/q.gguf", "--host", "127.0.0.1", "--port", "8081", "-c", "16384"]` when the idle sleep is 0

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

Every server route SHALL need the browser session. Changing the program path or the Chat server choice SHALL need the `credentials` scope on every route that can write it. While the choice is `managed`, every route that writes a llama.cpp Chat choice SHALL need the `credentials` scope. The context window, the idle sleep, start, stop and restart SHALL need `manage`. `GET /v1/llamacpp/server` SHALL need `read`. A bearer token SHALL NOT pass any route that writes or controls.

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

The server state SHALL be one of `stopped`, `starting`, `running` and `failed`. A `failed` state SHALL carry one reason from `binary-invalid`, `model-invalid`, `not-loopback`, `port-in-use`, `exited`, `timeout` and `not-configured`.

#### Scenario: Reasons are fixed

- **WHEN** the process writes any text to its output
- **THEN** the reason in the status MUST be one of the seven fixed values and MUST NOT hold that text

### Requirement: Start moves to running or to a failed state

Start SHALL move to `starting`, then poll `GET /health` on the owned port until it returns 200, then move to `running`. The wait SHALL end after 180 seconds with reason `timeout`. An exit of the process while `starting` or `running` SHALL give `failed` with reason `exited`. A missing program, or a Chat choice that is not llama.cpp with a model, SHALL give `not-configured`.

#### Scenario: Healthy start

- **WHEN** the process starts and `GET /health` returns 200 after 20 seconds
- **THEN** the state MUST move from `starting` to `running`

#### Scenario: Timeout

- **WHEN** `GET /health` does not return 200 within 180 seconds
- **THEN** the state MUST be `failed` with reason `timeout` and the owned process MUST be stopped

#### Scenario: Exit while starting

- **WHEN** the process exits with a code before `/health` returns 200
- **THEN** the state MUST be `failed` with reason `exited`

#### Scenario: Exit while running

- **WHEN** the running process is killed from outside
- **THEN** the next status read MUST show `failed` with reason `exited`

#### Scenario: Not configured

- **WHEN** no program is set, or the Chat provider is not `llamacpp`, or the Chat model is empty, and the user presses Start
- **THEN** the state MUST be `failed` with reason `not-configured` and no process MUST start

### Requirement: Stop and restart

Stop SHALL send SIGTERM to the process group of the owned process, wait up to 10 seconds, then send SIGKILL to the group. Restart SHALL stop the owned process and then start it with the saved values. The owned server SHALL stop when `omrs web` exits. A save SHALL NOT stop a running server. The status SHALL report the values the running process started with and the saved values, so the page can show "Restart to apply" when they differ.

#### Scenario: Graceful stop

- **WHEN** the owned process ends on SIGTERM within 10 seconds
- **THEN** the server MUST send no SIGKILL and the state MUST be `stopped`

#### Scenario: Forced stop

- **WHEN** the owned process ignores SIGTERM
- **THEN** the server MUST send SIGKILL to the process group after 10 seconds

#### Scenario: Restart uses saved values

- **WHEN** the user saves a new context window and presses Restart
- **THEN** the new process MUST start with the new `-c` value

#### Scenario: Exit of omrs web

- **WHEN** `omrs web` shuts down while the owned server runs
- **THEN** the owned process group MUST be stopped before the process exits

#### Scenario: Save keeps it running

- **WHEN** the user saves a new Chat model while the server runs
- **THEN** the process MUST keep running and the status MUST show saved and running values that differ

### Requirement: The server log stays on disk

The output of the child process SHALL go to the file `llamacpp-server.log` in the workspace folder. The file SHALL be emptied at each start and SHALL NOT grow past 5 MiB. No route SHALL return the file or any output of the child. The page SHALL NOT show it.

#### Scenario: Output to file

- **WHEN** the server runs and writes text
- **THEN** the text MUST appear in `llamacpp-server.log` in the workspace folder

#### Scenario: Size cap

- **WHEN** the child writes more than 5 MiB of output
- **THEN** the file MUST stay at or below 5 MiB

#### Scenario: Not returned

- **WHEN** the user reads any `/v1/llamacpp/server` route or `GET /v1/logs`
- **THEN** no response MUST hold text from the child process

### Requirement: Routes

The server SHALL expose `GET /v1/llamacpp/server`, `PUT /v1/llamacpp/server`, `POST /v1/llamacpp/server/start`, `POST /v1/llamacpp/server/stop` and `POST /v1/llamacpp/server/restart`. `GET` SHALL return the state, the reason, the values the running process started with, the saved values with their sources and locks, and the Chat model in force. `PUT` SHALL save the server settings, with 400 for a rule failure and 409 for a locked field. The routes SHALL appear in `openapi.yaml`.

#### Scenario: Status shape

- **WHEN** the user reads `GET /v1/llamacpp/server`
- **THEN** the body MUST hold `state`, `reason`, `running_with`, `shared_with_classification`, `chat_model` with `provider`, `model` and `usable`, and `saved` with `binary`, `chat_server`, `context_window` and `idle_sleep`, each with `source` and `locked`

#### Scenario: Locked field

- **WHEN** the program comes from the environment and the user sends `PUT` with a new program
- **THEN** the server MUST return 409 and name the variable

#### Scenario: Model key refused

- **WHEN** a `PUT /v1/llamacpp/server` body holds `model`
- **THEN** the server MUST return 400, save nothing, and the message MUST say that the Chat model is set in Settings > Chat

#### Scenario: Contract

- **WHEN** the OpenAPI contract test runs
- **THEN** all five routes MUST be present and match the responses

### Requirement: Idle sleep frees the model of the managed server

The managed server SHALL receive `--sleep-idle-seconds <n>` when the idle sleep setting is above 0, and SHALL NOT receive the flag when it is 0. A value outside 0 to 86,400 SHALL be refused with 400 at save and SHALL fail startup when it comes from the environment. A change while the server runs SHALL NOT stop the server and SHALL set "Restart to apply". The card SHALL say that the server frees the model after the idle seconds and reloads it on the next request, and that 0 turns sleep off.

#### Scenario: Default idle sleep

- **WHEN** no source sets the idle sleep and the user starts the server
- **THEN** the argument list MUST hold `--sleep-idle-seconds 300`

#### Scenario: Sleep turned off

- **WHEN** the idle sleep is 0 and the user starts the server
- **THEN** the argument list MUST NOT hold `--sleep-idle-seconds`

#### Scenario: Change while running

- **WHEN** the server runs with idle sleep 0 and the user saves 120
- **THEN** the server MUST keep running and `pending_restart` MUST be true
- **AND** after Restart the argument list MUST hold `--sleep-idle-seconds 120`

#### Scenario: Out of range

- **WHEN** the user saves -1 or 86,401
- **THEN** the route MUST return 400 and nothing is saved

### Requirement: Who runs the Chat server is a saved choice

`llamacpp_chat_server` SHALL say who runs the llama.cpp Chat server: `external` (a server that the user runs, such as the Llama app) or `managed` (the `llama-server` that OMRS starts). The sources SHALL follow the provider source order: the environment and `.env` (both lock), then `omrs.jsonc`, then the default `external`. A saved change SHALL apply at once. The server state SHALL NOT change the choice.

#### Scenario: Default choice

- **WHEN** no source sets `llamacpp_chat_server`
- **THEN** `GET /v1/llamacpp/server` MUST report `chat_server` as `external` with the source `default`

#### Scenario: The choice survives a launch

- **WHEN** `omrs.jsonc` holds `"llamacpp_chat_server": "managed"` and `omrs web` starts
- **THEN** `GET /v1/llamacpp/server` MUST report `chat_server` as `managed` and the state `stopped`

#### Scenario: Environment wins

- **WHEN** `LLAMACPP_CHAT_SERVER=external` is in the environment and the user saves `managed`
- **THEN** the server MUST return 409, name the variable and save nothing

### Requirement: OMRS's own server loads the Chat model

When the choice is `managed`, Start and Restart SHALL launch the server with the Chat model in force: `answer.model` while `answer.provider` is `llamacpp`. The server SHALL have no model setting of its own. When the Chat model in force differs from the model of the running process, the status SHALL report `pending_restart` as true.

#### Scenario: Start uses the Chat model

- **WHEN** the choice is `managed`, the Chat provider is `llamacpp`, the Chat model is `Qwen/Qwen3-4B-GGUF:Q4_K_M` and the user presses Start
- **THEN** the argument list MUST hold `-hf` and `Qwen/Qwen3-4B-GGUF:Q4_K_M`

#### Scenario: Chat save while the server runs

- **WHEN** the owned server runs and the user saves a new llama.cpp Chat model in Settings > Chat
- **THEN** the process MUST keep running and `pending_restart` MUST be true
- **AND** after Restart the argument list MUST hold the new model

#### Scenario: Chat uses another provider

- **WHEN** the choice is `managed`, the Chat provider is `openrouter` and the user presses Start
- **THEN** the state MUST be `failed` with the reason `not-configured` and no process MUST start

### Requirement: The external choice leaves the Chat server to its owner

When the choice is `external`, OMRS SHALL NOT start a server. Start and Restart SHALL return 409 with the reason `external-server` and SHALL start no process. A change to `external` while the owned server is `starting` or `running` SHALL return 409 with the reason `server-running` and SHALL save nothing.

#### Scenario: Start refused

- **WHEN** the choice is `external` and a client sends `POST /v1/llamacpp/server/start`
- **THEN** the server MUST return 409 with the reason `external-server` and MUST start no process

#### Scenario: Switch refused while running

- **WHEN** the owned server runs and the user saves `chat_server` as `external`
- **THEN** the server MUST return 409 with the reason `server-running`, keep the server running and leave `omrs.jsonc` unchanged

#### Scenario: Switch after a stop

- **WHEN** the owned server is `stopped` and the user saves `chat_server` as `external`
- **THEN** `omrs.jsonc` MUST hold `"llamacpp_chat_server": "external"`

### Requirement: The old server model setting is retired

OMRS SHALL NOT read `llamacpp_server_model` or `LLAMACPP_SERVER_MODEL`. When the environment or `.env` sets `LLAMACPP_SERVER_MODEL`, start-up SHALL fail with a message that names it and its replacement. A `llamacpp_server_model` key in `omrs.jsonc` SHALL be ignored and listed in the problem list with the replacement `answer.model`. Its value SHALL NOT become the Chat model.

#### Scenario: Old name in .env

- **WHEN** `.env` sets `LLAMACPP_SERVER_MODEL`
- **THEN** start-up MUST fail, and the message MUST name `LLAMACPP_SERVER_MODEL`, `ANSWER__PROVIDER`, `ANSWER__MODEL` and `LLAMACPP_CHAT_SERVER`

#### Scenario: Old key in omrs.jsonc

- **WHEN** `omrs.jsonc` holds `"llamacpp_server_model": "Qwen/Qwen3-4B-GGUF:Q4_K_M"`
- **THEN** `omrs web` MUST start, the problem list MUST name `llamacpp_server_model` and `answer.model`, and the Chat model MUST stay as the other sources set it
