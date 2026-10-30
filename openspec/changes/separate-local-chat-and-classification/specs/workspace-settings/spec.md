## ADDED Requirements

### Requirement: The llama.cpp card shows three blocks

The llama.cpp card SHALL group its values in three blocks, in this order: Embeddings (the embedding address and model, read-only), Classification (metadata) (the classification address, editable, and "Text model (classification)", read-only) and Chat (the Chat address, editable, the Chat model line and the Chat server choice). The card SHALL NOT label the classification model "Chat model". Other provider cards SHALL keep one block.

#### Scenario: Block titles

- **WHEN** the user opens Settings > Providers
- **THEN** the llama.cpp card MUST show the titles "Embeddings", "Classification (metadata)" and "Chat", in that order

#### Scenario: Text model label

- **WHEN** `llamacpp_chat_model` is `Qwen/Qwen3-0.6B-GGUF:Q8_0`
- **THEN** the Classification block MUST show "Text model (classification)" with that value
- **AND** no row outside the Chat block MUST be labelled "Chat model"

#### Scenario: Other cards

- **WHEN** the user opens the OpenRouter card
- **THEN** the card MUST show no block titles

### Requirement: The Chat block names the Chat model and links to Settings > Chat

The Chat block SHALL show the Chat model read-only, with a link to Settings > Chat, where it is set. When the Chat provider is `llamacpp`, the block SHALL show the row "Chat model" with `answer.model`. Otherwise the block SHALL show "Chat uses <provider name> (<model>)". The card SHALL NOT offer an edit control for the Chat model.

#### Scenario: Chat on OpenRouter

- **WHEN** the Chat provider is `openrouter` and the Chat model is `deepseek/deepseek-v4-flash-0731`
- **THEN** the Chat block MUST show "Chat uses OpenRouter (deepseek/deepseek-v4-flash-0731)" and a link to Settings > Chat

#### Scenario: Chat on llama.cpp

- **WHEN** the Chat provider is `llamacpp` and the Chat model is `Qwen/Qwen3-4B-GGUF:Q4_K_M`
- **THEN** the Chat block MUST show the read-only row "Chat model" with `Qwen/Qwen3-4B-GGUF:Q4_K_M`, a link to Settings > Chat, and no Edit action

### Requirement: The Chat block offers who runs the Chat server

The Chat block SHALL offer the choice "Who runs the Chat server" with two options: "The Llama app or another server you run" (`external`) and "OMRS's own llama-server" (`managed`). The choice SHALL show its source. A save SHALL write `llamacpp_chat_server` to `omrs.jsonc`. A locked choice, or a session without the `credentials` scope, SHALL make the choice read-only and SHALL state why.

#### Scenario: Choose OMRS's own server

- **WHEN** the user selects "OMRS's own llama-server"
- **THEN** `omrs.jsonc` MUST hold `"llamacpp_chat_server": "managed"` and the Chat block MUST show the Local server panel

#### Scenario: Locked choice

- **WHEN** `LLAMACPP_CHAT_SERVER` is in `.env`
- **THEN** the choice MUST be read-only and MUST name the variable and `.env`

#### Scenario: Switch refused while running

- **WHEN** the owned server runs and the user selects "The Llama app or another server you run"
- **THEN** the block MUST show one plain line that says to stop the server first, and the choice MUST stay `managed`

### Requirement: The Llama app choice warns about context size changes

While the choice is `external`, the Chat block SHALL show this callout: "Context size: set ctx-size for this model in the Llama app's models.user.ini, then relaunch the Llama app. The relaunch pauses embeddings and anything else on that port. OMRS does not edit this file or restart the app." The block SHALL offer no context window row for that server.

#### Scenario: Llama app callout

- **WHEN** the choice is `external`
- **THEN** the Chat block MUST show the callout that names `models.user.ini`, the relaunch of the Llama app, and the pause of embeddings and anything else on that port
- **AND** the block MUST NOT show a context window row

### Requirement: The OMRS server choice names the program it needs

While the choice is `managed`, the Chat block SHALL show this callout: "OMRS's own server needs a program named exactly llama-server. The Llama app's own llama program does not qualify. Install one with Homebrew: brew install llama.cpp. Then set the program path, for example /opt/homebrew/bin/llama-server." The panel SHALL show it again above the program path row while that path is not set or fails the program rule.

#### Scenario: OMRS server callout

- **WHEN** the user selects "OMRS's own llama-server"
- **THEN** the Chat block MUST show the callout that names `llama-server`, says that the Llama app's own `llama` program does not qualify, and gives `brew install llama.cpp`

#### Scenario: Program path not set

- **WHEN** the choice is `managed` and no program path is set
- **THEN** the Local server panel MUST show the same callout above the program path row

### Requirement: A classification address that follows the Chat address says so

While no source sets the classification address, the Classification block SHALL show the Chat address as the address in use, with the source `default` and the line "Uses the Chat address until you set one." Edit SHALL open with that address filled in.

#### Scenario: Follows the Chat address

- **WHEN** no source sets `llamacpp_classify_url` and the Chat address is `http://127.0.0.1:9931/v1`
- **THEN** the Classification block MUST show `http://127.0.0.1:9931/v1`, the source `default` and the line "Uses the Chat address until you set one."

### Requirement: A shared address on OMRS's server warns that the Text model is not used

When the choice is `managed` and the classification address in use equals the Chat address, the Classification block and the Local server panel SHALL show: "Classification goes to OMRS's own Chat server, which loads only the Chat model. The Text model is not used. Set a Classification address, for example the Llama app, to keep them apart."

#### Scenario: Shared address

- **WHEN** the choice is `managed` and no source sets `llamacpp_classify_url`
- **THEN** both places MUST show the warning that the Text model is not used

#### Scenario: Separate address

- **WHEN** the choice is `managed` and `llamacpp_classify_url` differs from `llamacpp_chat_url`
- **THEN** the card MUST NOT show the warning

### Requirement: The Chat form empties the model name when the provider changes

When the user changes the provider in the Chat form or the judge form, the model name field SHALL become empty. Save SHALL stay disabled until a model is typed or picked, and the field SHALL show the hint "Choose a model for this provider."

#### Scenario: Ollama name not carried to llama.cpp

- **WHEN** the Chat form opens with the provider Ollama and the model `qwen3:4b` and the user selects llama.cpp
- **THEN** the model name field MUST be empty and Save MUST be disabled

## MODIFIED Requirements

### Requirement: The llama.cpp card shows a Local server panel

When the Chat server choice is `managed`, the Chat block SHALL show a "Local server" panel with: the state as text and a badge (`stopped`, `starting`, `running` or `failed`); the fixed reason when the state is `failed`; setting rows for program path, context window and idle sleep, each with its value and source; the Chat model as a read-only row; and the buttons Start, Stop and Restart. The panel SHALL NOT show output of the server. With `external`, the card SHALL NOT show the panel.

#### Scenario: Failed with a reason

- **WHEN** a start ends with reason `port-in-use`
- **THEN** the panel MUST show the state `failed` and a friendly line for the reason, and MUST NOT show any process output

#### Scenario: External choice hides the panel

- **WHEN** the choice is `external`
- **THEN** the llama.cpp card MUST NOT show the Local server panel or its Start button

#### Scenario: No model row to edit

- **WHEN** the choice is `managed`
- **THEN** the panel MUST NOT offer a Model row with Edit, and its read-only Chat model row MUST link to Settings > Chat

### Requirement: The Local server panel buttons and rows follow the state and locks

Start SHALL be disabled while the state is `starting` or `running`. Stop SHALL be disabled while the state is `stopped`. A locked field SHALL be read-only and SHALL state its lock.

#### Scenario: Stopped

- **WHEN** no server is running
- **THEN** the panel MUST show the state `stopped`, Start enabled and Stop disabled

#### Scenario: Program and model need a credentials session

- **WHEN** the session lacks the `credentials` scope
- **THEN** the program path row and the Chat server choice MUST be read-only and MUST state that the scope is needed, and the Chat model row MUST stay read-only

#### Scenario: Locked field

- **WHEN** `LLAMACPP_SERVER_BINARY` is in the environment
- **THEN** the program path row MUST say where it is set and MUST NOT offer Edit

### Requirement: The Local server panel names what it does not manage and what is missing

The panel SHALL state that the embedding server is not managed. When Start fails because a value is not set, the panel SHALL name the missing value and where to set it.

#### Scenario: Not configured

- **WHEN** no program path is set and the user presses Start
- **THEN** the panel MUST show the state `failed` and the line "Set the program path first."

#### Scenario: No llama.cpp Chat model

- **WHEN** a program path is set, the Chat provider is not `llamacpp` and the user presses Start
- **THEN** the panel MUST show the state `failed` and the line "Choose llama.cpp and a Chat model in Settings > Chat first."
