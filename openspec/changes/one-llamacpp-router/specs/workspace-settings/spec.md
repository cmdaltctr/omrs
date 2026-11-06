## ADDED Requirements

### Requirement: The llama.cpp card shows one Router panel

The llama.cpp card SHALL show one Router panel. It SHALL show the choice "OMRS runs llama.cpp" (`managed`) or "Use this address" (`external`), the router address, the program in force (provisioned build or user path), the router state with one plain reason line, and Start, Stop and Restart. Start, Stop and Restart SHALL show only in managed mode, follow the state, and need `manage`. Locked fields SHALL show a lock and the variable name.

#### Scenario: Managed and stopped

- **WHEN** the mode is `managed` and the router is `stopped`
- **THEN** the panel MUST show Start enabled and Stop and Restart disabled

#### Scenario: External mode

- **WHEN** the mode is `external` with address `http://127.0.0.1:9931/v1`
- **THEN** the panel MUST show the address, the note "External server: OMRS does not check model files or presets", and no Start, Stop or Restart

#### Scenario: Restart to apply

- **WHEN** the saved model limit differs from the running router's
- **THEN** the panel MUST show "Restart to apply" beside Restart

#### Scenario: Locked address

- **WHEN** `LLAMACPP_ROUTER_URL` is set in the environment
- **THEN** the address row MUST show a lock and name the variable, and MUST offer no edit

### Requirement: The Router panel lists the models in a table

The panel SHALL show one table row per `llamacpp_models` entry with its roles, model name, file state, context size in tokens and model state. A row SHALL offer Edit (one control per allow-listed preset value), Get this model when it has no file, and Remove when it holds no role. A changed row of a running router SHALL show "Reload pending" until the reload ends. Each role SHALL link to the setting that gives it.

#### Scenario: Shipped list on a fresh install

- **WHEN** OMRS starts with no `omrs.jsonc`
- **THEN** the table MUST show `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` with the role Embeddings and `Qwen/Qwen3-4B-GGUF:Q8_0` with the roles Chat and Classification, both "Not downloaded"

#### Scenario: Edit context size

- **WHEN** the user edits the Chat row's context size to 16,384 and saves
- **THEN** `omrs.jsonc` MUST hold `ctx-size` 16384 in that entry's preset and the row MUST show 16,384

#### Scenario: Remove refused for a used entry

- **WHEN** an entry holds the role Chat
- **THEN** its row MUST NOT offer Remove

#### Scenario: Unit is stated

- **WHEN** the table shows the context size column
- **THEN** the column heading MUST say "Context size (tokens)"

### Requirement: Router panel controls render at desktop and phone widths

The Router panel and its model table SHALL fit at 1,280 px and 390 px without sideways page scroll. At 390 px each table row SHALL stack its fields, and every button SHALL stay reachable.

#### Scenario: Phone width

- **WHEN** the page is 390 px wide and the table holds three entries
- **THEN** every row, its Edit button and the Start, Stop and Restart buttons MUST fit without sideways page scroll

## REMOVED Requirements

### Requirement: The llama.cpp card shows a Local server panel

**Reason**: The Router panel replaces the Chat-only Local server panel.

**Migration**: Use the Router panel in the llama.cpp card.

### Requirement: The Local server panel states ownership and pending restarts

**Reason**: The Router panel states the mode, the program in force and "Restart to apply" for the whole router, and "Reload pending" per model.

**Migration**: Read the router state and the per-row states in the Router panel.

### Requirement: The Local server panel buttons and rows follow the state and locks

**Reason**: Replaced by "The llama.cpp card shows one Router panel".

**Migration**: Start, Stop and Restart sit in the Router panel.

### Requirement: The Local server panel names what it does not manage and what is missing

**Reason**: The router manages every local llama.cpp model except OCR. The panel's external note and the "Not downloaded" rows say what is missing.

**Migration**: None needed.

### Requirement: The llama.cpp card shows three blocks

**Reason**: Embeddings, classification and Chat share one router address. The model table shows each entry's roles.

**Migration**: Read roles in the Router panel table.

### Requirement: The Chat block names the Chat model and links to Settings > Chat

**Reason**: The Chat block goes. The table row of the Chat model shows the role Chat with a link to Settings > Chat.

**Migration**: Follow the Chat role link in the Router panel table.

### Requirement: The Chat block offers who runs the Chat server

**Reason**: One router mode replaces the Chat server choice.

**Migration**: Use the Router panel choice "OMRS runs llama.cpp" or "Use this address".

### Requirement: The Llama app choice warns about context size changes

**Reason**: Context sizes now live in OMRS settings for managed mode. In external mode the panel note says OMRS does not check presets.

**Migration**: Set the context size in the Router panel table.

### Requirement: The OMRS server choice names the program it needs

**Reason**: The Router panel shows the program in force, and the Integrations page provisions the pinned build.

**Migration**: Use Get llama.cpp on the Integrations page, or set the program path in the Router panel.

### Requirement: A classification address that follows the Chat address says so

**Reason**: The classification address is retired. Every role uses the router address.

**Migration**: None needed.

### Requirement: A shared address on OMRS's server warns that the Text model is not used

**Reason**: The router serves the classification Text model by name, so it is always used.

**Migration**: None needed.
