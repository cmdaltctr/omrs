## ADDED Requirements

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

## MODIFIED Requirements

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

### Requirement: Scopes for server control

Every server route SHALL need the browser session. Changing the program path or the Chat server choice SHALL need the `credentials` scope. While the choice is `managed`, every route that writes a llama.cpp Chat choice SHALL need the `credentials` scope. The context window, the idle sleep, start, stop and restart SHALL need `manage`. `GET /v1/llamacpp/server` SHALL need `read`. A bearer token SHALL NOT pass any route that writes or controls.

#### Scenario: Bearer token refused

- **WHEN** a client uses a bearer token with `manage` on `POST /v1/llamacpp/server/start`
- **THEN** the server MUST refuse the request

#### Scenario: Model change needs credentials

- **WHEN** the choice is `managed` and a browser session with `manage` but not `credentials` sends `PUT /v1/settings/chat` with the provider `llamacpp` and a new model
- **THEN** the server MUST return 403 and save nothing

#### Scenario: The Configuration page cannot skip the scope

- **WHEN** the choice is `managed` and a browser session with `manage` but not `credentials` sends `PUT /v1/settings/configuration` with `answer.model` while the Chat provider is `llamacpp`
- **THEN** the server MUST return 403 and save nothing

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
