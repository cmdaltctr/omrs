# workspace-settings Specification

## Purpose
A Settings area that holds the workspace-wide controls and information that belong to no other view: appearance, provider connections, MCP access, the live server log, runtime capabilities and workspace details.

## Requirements

### Requirement: Settings is split into sections

The Settings view SHALL offer the sections Appearance, Providers, Chat, MCP, Server log, Runtime, Workspace, Document reading and Configuration, in that order, switched with chip buttons, with one section shown at a time. Each section SHALL have the address `#/settings/<section>` (`appearance`, `providers`, `chat`, `mcp`, `log`, `runtime`, `workspace`, `document-reading`, `configuration`). Selecting a chip SHALL rewrite the address. `#/settings` SHALL show Appearance.

#### Scenario: Switch section

- **WHEN** the user selects the Server log chip
- **THEN** only the Server log section MUST show, the Server log chip MUST be marked selected, and the address MUST read `#/settings/log`

#### Scenario: Open a section from a link

- **WHEN** the app opens at `#/settings/chat`
- **THEN** only the Chat section MUST show and the Chat chip MUST be marked selected

#### Scenario: Open Document reading from a link

- **WHEN** the app opens at `#/settings/document-reading`
- **THEN** only the Document reading section MUST show, its chip MUST be marked selected, and its chip MUST come directly before the Configuration chip

### Requirement: Connections show provider configuration without secrets

The Providers section SHALL show one card for each entry of `GET /v1/connections`. Each card SHALL show the provider name, a Local or Cloud badge with text, the roles that use it, each editable field as a setting row, the read-only values (embedding address and models) as read-only rows, and the install command when the provider is not installed.

#### Scenario: Roles follow the configuration

- **WHEN** `EMBED_PROVIDER` is `local`, `LOCAL_BACKEND` is `llamacpp` and the Chat provider is `ollama`
- **THEN** llama.cpp MUST list the embeddings role and Ollama MUST list the answers role

#### Scenario: Optional key

- **WHEN** the `openai_compatible` entry marks its key field as optional and no key is set
- **THEN** the card MUST show the key field as optional, MUST NOT show an error, and the Chat section MUST allow choosing `openai_compatible`

#### Scenario: Provider not installed

- **WHEN** the `anthropic` entry reports that its package is not installed
- **THEN** the card MUST show the install command `uv sync --extra anthropic`, and the Chat section MUST mark `anthropic` as not ready with the reason in text

### Requirement: Each provider field states where its value is set

A field from `env` SHALL show "Set in the environment. Change it there." with the variable name. A field from `dotenv` SHALL show "Set in .env. Change it there." with the variable name and the `.env` path. A field from `config-file` SHALL show "Saved in settings (omrs.jsonc)" and SHALL stay editable. The field source SHALL be one of `env`, `dotenv`, `config-file`, `keychain`, `key-file`, `default` and `none`.

#### Scenario: Address from the config file

- **WHEN** the Ollama entry reports the source `config-file`
- **THEN** the card MUST show the address with "Saved in settings (omrs.jsonc)" and MUST offer Edit

#### Scenario: Save an address

- **WHEN** the Ollama address is not locked and the user presses Edit, changes the address and presses Save
- **THEN** the card MUST show the address and the source `config-file` that the server returns after the save

### Requirement: A provider key shows only its state, last four characters and source

A key from `key-file` SHALL show "from key file" with the file path. A key from `keychain` SHALL show "in system keychain". A key field SHALL show at most "Key set" and the last four characters.

#### Scenario: Key is never exposed

- **WHEN** `OPENROUTER_API_KEY` is set in `.env`
- **THEN** the OpenRouter card MUST show "Set in .env. Change it there.", and no five consecutive characters of the key MUST appear in the response or the page

#### Scenario: Key from a key file

- **WHEN** the OpenRouter key field reports the source `key-file` for `secrets/openrouter.key`
- **THEN** the card MUST show "Key set · ending <last four> · from key file secrets/openrouter.key" and MUST offer Replace and no Remove

#### Scenario: Replace a key

- **WHEN** the user presses Replace, types a new OpenRouter key and presses Save key
- **THEN** the input MUST close, the card MUST show "Key set · ending <last four> · in system keychain", and the page MUST NOT show the key again

#### Scenario: No keychain

- **WHEN** the server reports that no keychain is available and no key is set
- **THEN** the key field MUST show one plain line that says so and names `secrets/<provider>.key` and the environment variable, and MUST offer no key input

### Requirement: The Providers section states where text and saves go

A Cloud card, and a card whose address is not on this machine, SHALL state that text leaves this machine. The section SHALL name the `omrs.jsonc` path and SHALL state that saves are written there.

#### Scenario: Cloud card and save location

- **WHEN** the Providers section shows a Cloud card
- **THEN** the card MUST state that text leaves this machine
- **AND** the section MUST name the `omrs.jsonc` path and MUST state that saves are written there

### Requirement: A connection test runs only on request

Each provider card SHALL offer a Test action that calls `POST /v1/connections/{provider}/test`. When a field holds an unsaved typed value, the request SHALL carry it and the server SHALL test it without saving it.

#### Scenario: Test a typed key before saving

- **WHEN** the user types an OpenRouter key, presses Test and the provider rejects the key
- **THEN** the card MUST show not reachable with the reason unauthorised, and the saved key state MUST NOT change

### Requirement: A connection test sends one bounded request and returns a fixed reason

The server SHALL send one model-list or key-check request for each address with a 5-second timeout, and return whether the provider was reachable and a reason from a fixed set (`refused`, `timeout`, `unauthorised`, `http-<status>`, `not-configured`). The server SHALL NOT return response bodies or exception text, SHALL NOT log a typed key, and SHALL NOT send a model-list or key-check request to any provider unless a test or a model list is requested.

#### Scenario: Local provider down

- **WHEN** the user tests Ollama and nothing listens on its URL
- **THEN** the entry MUST show not reachable with the reason refused, stated in text with a badge

#### Scenario: No background cloud call

- **WHEN** the user opens Providers or Chat and presses no Test or List models action
- **THEN** the server MUST NOT send any request to OpenRouter

### Requirement: The server log streams redacted lines

The Server log section SHALL show the server's recent log records in a monospace, terminal-style panel, loaded from `GET /v1/logs` and followed live through `GET /v1/logs/stream`, with a level filter, pause, copy, and auto-scroll while the panel is scrolled to the bottom. Both endpoints SHALL require the browser session.

#### Scenario: Live line

- **WHEN** the server logs a warning while the section is open
- **THEN** the warning MUST appear in the panel without a reload

#### Scenario: Bearer credential refused

- **WHEN** a request to either log endpoint carries a bearer credential instead of the browser session
- **THEN** the server MUST refuse it

### Requirement: Server log records are redacted and bounded in memory

Records SHALL be redacted before they are buffered, the buffer SHALL hold at most the last 1,000 records in memory, and the stream SHALL end when the server stops admitting requests.

#### Scenario: Secret removed

- **WHEN** a log message contains the configured OpenRouter key
- **THEN** the buffered record, the response and the panel MUST NOT contain the key

### Requirement: The MCP section shows how to connect a client

The MCP section SHALL show a copyable stdio client configuration that starts `omrs` with `uv run --directory <project>`, where `<project>` is `config_dir` from `GET /v1/connections`, so the client's process reads the same `.env`.

#### Scenario: Copy stdio configuration

- **WHEN** the user copies the stdio configuration
- **THEN** the clipboard MUST hold a client configuration that runs `uv run --directory <project> omrs` with `config_dir` as `<project>`

### Requirement: The MCP section shows the HTTP transport controls

The MCP section SHALL also show, through the endpoints of the `add-mcp-http-transport` change only: an on/off switch for MCP over HTTP, the HTTP client configuration with the server's `/mcp` URL, token create, rotate and revoke with a new token shown once, and the saved web port that applies on the next launch.

#### Scenario: Switch reflects the server

- **WHEN** the server reports MCP over HTTP as off and the user turns the switch on
- **THEN** the section MUST show the state the server returns after the change, not an assumed state

#### Scenario: Token shown once

- **WHEN** the user creates the MCP token and then leaves and reopens the MCP section
- **THEN** the token MUST show with a copy action after creation and MUST NOT show after reopening

### Requirement: The Chat section chooses the Chat model

The Chat section SHALL show the Chat provider and model from `GET /v1/settings/chat` as setting rows with their source.

#### Scenario: Locked choice

- **WHEN** `.env` sets `ANSWER__PROVIDER`
- **THEN** the section MUST show the choice as locked, name the variable and `.env`, and offer no Edit action

### Requirement: Editing the Chat choice offers a provider select, a model list and a test

When the choice is not locked, Edit SHALL open a provider select of the registered providers, each provider that is not ready marked with its reason in text, a model name field filled with the current model, a List models action that fills the field from the provider's list, a Test action for the typed choice, Save, Cancel and Clear. Save SHALL write `answer.provider` and `answer.model` to `omrs.jsonc`.

#### Scenario: Pick a model from the list

- **WHEN** the user presses Edit, selects Ollama, presses List models and picks `qwen3:4b`
- **THEN** the model name field MUST hold `qwen3:4b` and nothing MUST be saved until the user presses Save

#### Scenario: Type a model name

- **WHEN** the user selects OpenRouter, types `openai/gpt-4o-mini` and presses Save
- **THEN** the section MUST show the choice with the source `config-file` that the server returns

#### Scenario: Test result

- **WHEN** the user presses Test and the server reports ok false with the reason timeout
- **THEN** the section MUST show the failure as a badge with text and one plain sentence, and MUST NOT show provider text

### Requirement: The Chat section says where the choice applies

The Chat section SHALL state that the choice also answers MCP clients of this web server that cannot supply their own model, that metadata extraction keeps its own model, that the claim check judge has its own choice in the block below, and that `omrs` over stdio and the CLI read the same `omrs.jsonc` at their next launch. When the selected provider is cloud, the section SHALL state that questions and retrieved passages leave this machine.

#### Scenario: Cloud choice warns

- **WHEN** the user selects OpenRouter in the Chat section
- **THEN** the section MUST state that questions and retrieved passages are sent to openrouter.ai

#### Scenario: Local choice

- **WHEN** the user selects Ollama with an address on this machine
- **THEN** the section MUST NOT show the cloud statement

### Requirement: The Ollama card edits the context window

The Ollama card SHALL show "Context window (tokens)" as a setting row with its value and source. Edit SHALL open a number field filled with the current value, with the minimum 2,048 and the maximum 262,144. A locked field SHALL be read-only and SHALL state its lock. A saved value SHALL be written to `omrs.jsonc` and SHALL apply at once. The card SHALL state that the window does not apply to embedding models.

#### Scenario: Show default

- **WHEN** the user opens Settings > Providers with no value set
- **THEN** the Ollama card MUST show 16384 and the source "default"

#### Scenario: Save a value

- **WHEN** the user presses Edit, types 32768 and presses Save
- **THEN** the card MUST show 32768 and the source "Saved in settings (omrs.jsonc)"

#### Scenario: Out of range

- **WHEN** the user types 1000
- **THEN** the card MUST show the friendly error "Enter 2,048 to 262,144." and MUST NOT save

#### Scenario: Locked by environment

- **WHEN** the field reports source `env` or `dotenv`
- **THEN** the card MUST show where it is set and MUST NOT offer Edit

### Requirement: Every setting is shown as a value and source row

Each editable setting on the Settings page SHALL show one row with its label, the value in force and its source in plain words ("Saved in settings (omrs.jsonc)", "Set in .env", "Set in the environment", "default"). Edit SHALL open an input filled with the value in force, with Save and Cancel. The page SHALL NOT show an empty input for a field that has a value.

#### Scenario: Value from the file

- **WHEN** `omrs.jsonc` sets `llamacpp_server_binary` to `/opt/homebrew/bin/llama-server`
- **THEN** the row MUST show that path and "Saved in settings (omrs.jsonc)", and no input MUST be visible until the user presses Edit

#### Scenario: Edit opens filled

- **WHEN** the user presses Edit on that row
- **THEN** the input MUST hold `/opt/homebrew/bin/llama-server`

#### Scenario: Default value shown

- **WHEN** no source sets the Ollama address
- **THEN** the row MUST show `http://localhost:11434` and "default"

### Requirement: A set key shows a summary row

A key field with a key SHALL show one row "Key set · ending <last four> · <source>" and no input. It SHALL offer Replace, which opens an empty key input, unless the key comes from `env` or `dotenv`. It SHALL offer Remove only when the key is in the system keychain.

#### Scenario: Key in the keychain

- **WHEN** the OpenRouter key comes from `keychain://openrouter`
- **THEN** the row MUST read "Key set · ending <last four> · in system keychain" and MUST offer Replace and Remove

#### Scenario: Key in .env

- **WHEN** the OpenRouter key comes from `.env`
- **THEN** the row MUST read "Key set · ending <last four> · Set in .env. Change it there." and MUST offer no button

#### Scenario: No key

- **WHEN** no source sets the OpenRouter key and a keychain is available
- **THEN** the field MUST show a key input with the placeholder "Paste key (saved to the system keychain)" and the hint "Or put it in secrets/openrouter.key"

### Requirement: A refused save shows its reason

When the server refuses a Settings save with 400 or 409 and a message, the page SHALL show that message as one line with one action. Server messages for these answers SHALL name the rule or the source and SHALL NOT contain the refused value or any key.

#### Scenario: Program rule

- **WHEN** the user saves `~/.llama-app/llama` as the llama.cpp program
- **THEN** the card MUST show the program rule message and MUST NOT show "The local server could not complete that request."

#### Scenario: File changed on disk

- **WHEN** a save returns 409 because `omrs.jsonc` changed
- **THEN** the page MUST show "omrs.jsonc changed on disk. Reload to see the new values." with a Reload action

### Requirement: A restart-only change offers a restart

After the user saves a setting that applies only after a restart, the page SHALL open a dialog that names the setting and offers "Restart now" and "Later". "Restart now" SHALL use the power menu restart. When the app runs in a terminal, the dialog SHALL show the command to restart instead of "Restart now". "Later" SHALL leave the row marked "Restart to apply".

#### Scenario: Port saved

- **WHEN** the app runs as the login item and the user saves port 9100
- **THEN** a dialog MUST say that port 9100 applies after a restart and MUST offer "Restart now" and "Later"

#### Scenario: Restart now

- **WHEN** the user presses "Restart now"
- **THEN** the page MUST send the power menu restart request and MUST say that the page reloads by itself, and MUST name `omrs web open` for a restart that moves the app to a new port

#### Scenario: Reload when the app is back

- **WHEN** the restart was accepted and the server has stopped answering and then answers again
- **THEN** the page MUST reload once, so it shows what the new launch reads
- **AND** the page MUST NOT reload when the restart was refused, when the server never stopped answering, or after 90 seconds

#### Scenario: Foreground server

- **WHEN** the app runs in a terminal and the user saves port 9100
- **THEN** the dialog MUST show the restart command and MUST NOT offer "Restart now"

### Requirement: The Configuration section lists every setting

Settings SHALL have a Configuration section that lists every setting, grouped by block, with its value in force, its source, and "Restart to apply" when its file value differs from the value the server started with. Keys SHALL show at most the last four characters. The section SHALL show the `omrs.jsonc` path with a copy action, and the problems found in the file. It SHALL take its data from `GET /v1/settings/configuration` (read scope).

#### Scenario: Engine setting edited by hand

- **WHEN** the user changes `retrieval.top_k` in `omrs.jsonc` while the server runs
- **THEN** the section MUST show the launch value, the source `config-file` and "Restart to apply", and MUST offer the restart dialog

#### Scenario: Problems listed

- **WHEN** `omrs.jsonc` holds an unknown key and an invalid value
- **THEN** the section MUST list both by key with one plain line each and MUST NOT show the invalid value

#### Scenario: Database rows not moved

- **WHEN** the server could not move saved settings into `omrs.jsonc`
- **THEN** the section MUST show "Saved settings could not be moved to omrs.jsonc" with the folder path

### Requirement: Each settings block is a table of setting, value and source

Each block SHALL be a card that holds one table with the columns Setting, Value and Source, one row for each setting. A row waiting for a restart SHALL show "Next launch: <value>" under the value. At a phone width the Source SHALL show under the setting name, and the page SHALL NOT scroll sideways.

#### Scenario: Block shown as a table

- **WHEN** the section shows the Retrieval block
- **THEN** the block card MUST hold a table with the columns Setting, Value and Source, one row for each `retrieval.` setting, and no control MUST be visible until the user presses Edit

#### Scenario: Phone width

- **WHEN** the section is shown 390 px wide
- **THEN** each table MUST show the source under the setting name, Edit, Save and Cancel MUST stay at the top right of the card, and the page MUST NOT scroll sideways

### Requirement: A block table has an edit mode

A block card with at least one editable setting SHALL show Edit at its top right. Edit SHALL put the whole table in edit mode: each setting the server reports as editable SHALL show, in its Value cell, a control for its kind filled with the value the next launch uses. In edit mode, Save and Cancel SHALL take the place of Edit.

#### Scenario: Block with no editable setting

- **WHEN** every setting in a block is read-only
- **THEN** the block card MUST NOT show Edit

### Requirement: Each editable cell holds a control for its kind

The control SHALL be an on/off switch for a boolean, a number field with its range for a number, a choice list for a setting with fixed choices, and a text field for text. A Value cell SHALL hold only the control and its rule; a row SHALL have no button of its own.

#### Scenario: Turn a boolean off

- **WHEN** the user switches `answer.enabled` off in edit mode and saves
- **THEN** `omrs.jsonc` MUST hold `answer.enabled` false and the row MUST show "Off"

#### Scenario: Choose from fixed choices

- **WHEN** the user edits `metadata.extraction_mode`
- **THEN** the control MUST be a choice list of the accepted modes, and no free text MUST be possible

### Requirement: Save sends every changed cell of a table in one call

Save SHALL be disabled until a cell differs from its starting value, and while a cell breaks its rule. Save SHALL send every changed cell of that table in one `PUT /v1/settings/configuration` call with the revision the section read, so the server writes all of them or none. After a good save the table SHALL leave edit mode, and when a saved setting applies at restart the restart dialog SHALL open once for the whole save.

#### Scenario: Edit a restart-only number

- **WHEN** `retrieval.top_k` comes from the default, and the user presses Edit on the Retrieval table, types 20 and presses Save
- **THEN** the page MUST send `{"revision": <read revision>, "changes": {"retrieval.top_k": 20}}`, the table MUST leave edit mode, the row MUST show "Next launch: 20", "Saved in settings (omrs.jsonc)" and "Restart to apply", and the restart dialog MUST be offered

#### Scenario: Several cells saved together

- **WHEN** the user changes `retrieval.top_k` to 20 and `retrieval.hybrid_enabled` to on in one edit mode and presses Save
- **THEN** the page MUST send one request whose changes hold exactly those two keys, and the restart dialog MUST open once

#### Scenario: Nothing changed

- **WHEN** the user presses Edit and changes no cell
- **THEN** Save MUST be disabled and no request MUST be sent

#### Scenario: Out of range number refused before the request

- **WHEN** the server reports `answer.max_rounds` with the range 1 to 8 and the user types 12
- **THEN** the cell MUST show the range rule, Save MUST be disabled and no request MUST be sent

#### Scenario: File changed under the page

- **WHEN** someone edits `omrs.jsonc` by hand after the section loaded and the user then saves a table
- **THEN** the page MUST show "omrs.jsonc changed on disk. Reload to see the new values." and MUST NOT write

### Requirement: A refused save or Cancel keeps the table consistent

A refused save SHALL keep the table in edit mode with the typed values and SHALL show the server's message. Cancel SHALL drop every change in the table and leave edit mode. Only one table SHALL be in edit mode at a time; Edit on another table while the open table has changes SHALL ask whether to discard them.

#### Scenario: Cancel drops the changes

- **WHEN** the user types 20 for `retrieval.top_k` and presses Cancel
- **THEN** the table MUST leave edit mode, the row MUST show the value it showed before, and no request MUST be sent

#### Scenario: Second table while the first has changes

- **WHEN** the Retrieval table has a changed cell and the user presses Edit on the Answer table
- **THEN** the page MUST ask whether to discard the Retrieval changes, and MUST open the Answer table only after the user agrees

#### Scenario: Refused save keeps the typed values

- **WHEN** the server refuses a save with 400 and a message
- **THEN** the table MUST stay in edit mode with the typed values and MUST show the message

### Requirement: Read-only settings show a lock and a reason

A setting the server reports as read-only SHALL keep its value as text with a lock mark, also in edit mode, and in edit mode its reason SHALL show on a line under the row.

#### Scenario: Read-only identity setting

- **WHEN** the user presses Edit on the block that holds `embed_model`
- **THEN** the row MUST keep its value as text with a lock mark and MUST show its reason ("The embedding model is part of every collection. Change it in omrs.jsonc and re-ingest.") under the row

### Requirement: Environment locks, cleared values and chunking changes are explained

A setting set in the environment or `.env` SHALL be read-only with the reason "Remove <ENV_NAME> from the environment or .env to edit it here." An optional setting SHALL be cleared by emptying its field and saving, which removes the key so the default applies. A chunking block SHALL state that its settings are part of the index identity, so the next ingest after a restart can read existing files again.

#### Scenario: Clear an optional setting

- **WHEN** `omrs.jsonc` holds `metadata.ollama_classify_timeout_override` 30, and the user empties its field in edit mode and saves
- **THEN** the page MUST send `null` for that key, the key MUST be removed from the file and the row MUST show the default and the source "default"

### Requirement: Document reading shows the reading settings and their state

The Document reading section SHALL show one row for each of `pdf_readers`, `ocr_fallback_enabled`, `ocr_routing_unit`, `ocr_engines`, `ocr_maths_routing_enabled` and `ocr_non_latin_routing`. Each row SHALL show the value in force since launch, its source and the default. When the saved file value differs from the value in force, the row SHALL show the saved value and "Restart to apply".

#### Scenario: Value saved but not yet in force

- **WHEN** the server launched with `pdf_reader` `auto` and `omrs.jsonc` now holds `"pdf_reader": "liteparse"`
- **THEN** the PDF reader row MUST show `auto` in force, `liteparse` saved and "Restart to apply"

### Requirement: The host router row shows the value in force without a restart

The host router row (`document_router`) SHALL show the value in force now, read from `omrs.jsonc`, and SHALL NOT show "Restart to apply", because a saved router choice applies to the next request.

#### Scenario: Host router saved

- **WHEN** the user saves `handwriting` as the host router in a running `omrs web`
- **THEN** the host router row MUST show `handwriting` in force and MUST NOT show "Restart to apply"

### Requirement: Document reading states locks and when settings apply

A key set in the environment or `.env` SHALL be read-only and SHALL show "Remove <ENV_NAME> from the environment or .env to edit it here." The section SHALL state that the settings apply after a restart, and that they are part of the index identity, so the next ingest after a restart can read existing files again.

#### Scenario: Key locked by the environment

- **WHEN** `OCR_ROUTING_UNIT=page` is set in `.env`
- **THEN** the routing unit row MUST offer no Edit and MUST show "Remove OCR_ROUTING_UNIT from the environment or .env to edit it here."

### Requirement: Document reading routes

`GET /v1/settings/document-reading` SHALL need the read scope. It SHALL return the file `revision`, one entry for each of the six keys in a fixed order (with the value in force, the saved value, the source, whether it is locked, the lock reason, whether a restart is pending, and the default), every PDF reader with its availability, the reader in use, the OCR workers folder, and each known engine with its availability.

#### Scenario: Read the section

- **WHEN** a session with the read scope sends `GET /v1/settings/document-reading`
- **THEN** the answer MUST be 200 and MUST hold six `settings` entries, `pdf_readers` starting with `auto`, and `ocr.engines`
- **AND** `ocr` MUST NOT hold `worker_command_set`

### Requirement: The document reading save writes all values or none

`PUT /v1/settings/document-reading` SHALL need a browser session with the manage scope. It SHALL take `values` (one to six of the six keys, each a value or `null`) and a required `revision`. It SHALL write all values or none.

#### Scenario: One bad value stops the whole save

- **WHEN** a `PUT` sets `ocr_routing_unit` to `page` and `ocr_engine_primary` to `../x`
- **THEN** the server MUST answer 400 and the file MUST hold neither value

### Requirement: The document reading save answers with a status for each outcome

On success it SHALL return the same body as `GET`. It SHALL answer 400 for a key outside the six, for a value that breaks its rule, for a blank text value and for a PDF reader that is not installed. It SHALL answer 409 for a locked key, for a stale revision and for a file that cannot be parsed. No error message SHALL hold a submitted value. The scenario heading "Key outside the nine" keeps its baseline name for delta continuity; six keys are writable.

#### Scenario: Key outside the nine

- **WHEN** a `PUT` sets `embed_provider`
- **THEN** the server MUST answer 400 "embed_provider is not a document reading setting." and MUST NOT change the file

#### Scenario: Locked key

- **WHEN** `PDF_READER` is set in the environment and a `PUT` sets `pdf_reader`
- **THEN** the server MUST answer 409 "Remove PDF_READER from the environment or .env to edit it here." and MUST NOT change the file

#### Scenario: Value out of range

- **WHEN** a `PUT` sets `ocr_routing_unit` to `document`
- **THEN** the server MUST answer 400 with a message that names `page` as the only routing unit, and MUST NOT change the file

#### Scenario: Uninstalled reader

- **WHEN** `pypdfium2` is not installed and a `PUT` sets `pdf_reader` to `pypdfium2`
- **THEN** the server MUST answer 400 "pdf_reader: This PDF reader is not installed. Install its package, then save again." and MUST NOT change the file

#### Scenario: Unprovisioned engine is allowed

- **WHEN** a `PUT` sets `ocr_engine_primary` to a valid name that has no folder under the engines folder
- **THEN** the server MUST answer 200, the file MUST hold the name, and the engine entry MUST report `available` false with the reason

### Requirement: The Chat section sets the claim check judge

The Chat section SHALL show a "Claim check judge" block under the Chat choice. The block SHALL show the judge provider and the judge model from `GET /v1/settings/judge` as setting rows with their source. An alias SHALL show with the provider it resolves to, for example "cloud (OpenRouter)".

#### Scenario: Narrow screen

- **WHEN** the Chat section shows at 390 px wide
- **THEN** the judge rows and the form MUST fit with no horizontal page scroll

### Requirement: The judge block can be edited, removed or locked

An empty model SHALL show "Not set" and the sentence "Claim checks are skipped until you set a judge model." When the choice is not locked, the block SHALL offer Edit, and SHALL offer Remove when the source is `config-file`. When the choice is locked, the block SHALL name the variable and where it is set, and SHALL offer no Edit or Remove.

#### Scenario: Default judge shown

- **WHEN** no source sets the judge
- **THEN** the block MUST show "cloud (OpenRouter)" with "default", the model "Not set" with "default", the skipped-checks sentence, and Edit, and MUST NOT offer Remove

#### Scenario: Remove the judge

- **WHEN** the judge comes from `omrs.jsonc` and the user presses Remove
- **THEN** the page MUST send the clear request and MUST show the default judge with the source "default"

#### Scenario: Locked judge

- **WHEN** `.env` sets `ANSWER__VERIFY_PROVIDER`
- **THEN** the block MUST show the judge as locked, name the variable and `.env`, and offer no Edit or Remove

### Requirement: Editing the judge uses the same controls as the Chat choice

Edit SHALL open the same provider select, model name field, List models and Test actions as the Chat choice, filled with the current values, with Save and Cancel. Save SHALL be disabled while the model name is empty.

#### Scenario: Edit opens filled

- **WHEN** `omrs.jsonc` sets the judge to `openrouter` and `openai/gpt-5-mini` and the user presses Edit
- **THEN** the provider select MUST show OpenRouter and the model field MUST hold `openai/gpt-5-mini`

#### Scenario: Pick a judge model from the list

- **WHEN** the user presses Edit, selects Ollama, presses List models and picks `qwen3:4b`
- **THEN** the model name field MUST hold `qwen3:4b` and nothing MUST be saved until the user presses Save

### Requirement: The judge block states where the judge runs and what leaves this machine

The block SHALL state that the judge runs only for collections whose profile turns on "Check claims", and that a profile that sets its own judge overrides this choice. When the selected judge provider is cloud, the block SHALL state that claims and cited passages are sent off this machine.

#### Scenario: Judge scope and cloud statement

- **WHEN** the selected judge provider is cloud
- **THEN** the block MUST state that claims and cited passages are sent off this machine
- **AND** the block MUST state that the judge runs only for collections whose profile turns on "Check claims", and that a profile that sets its own judge overrides this choice

### Requirement: Document reading marks readers and engines that cannot run

The PDF reader choice SHALL mark each reader that is not installed and SHALL NOT let the user choose it. The engine choices SHALL list the engines the server reports and SHALL mark each engine that is not provisioned, with the reason.

#### Scenario: Reader not installed

- **WHEN** the server reports `pypdfium2` as not installed
- **THEN** the PDF reader choice MUST show `pypdfium2` as not available with the reason and MUST NOT allow it to be selected

#### Scenario: Engine not provisioned

- **WHEN** the server reports `dots-mocr` as not provisioned
- **THEN** the engine choices MUST mark `dots-mocr` as not available and MUST show the reason with its provision command

### Requirement: The Integrations page probes only local servers

The only provider request outside a test or a model list SHALL be the local server health probe of `GET /v1/integrations` (spec `runtime-components`). It SHALL send one request without a key to each configured Ollama and llama.cpp address, with a timeout of 1 second or less. The server SHALL NOT contact a cloud provider for it.

#### Scenario: Integrations page probes only local servers

- **WHEN** the user opens the Integrations page
- **THEN** the server MUST send one health request without a key to each configured Ollama and llama.cpp address
- **AND** the server MUST NOT send a model-list or key-check request to any provider

### Requirement: The Chat form empties the model name when the provider changes

When the user changes the provider in the Chat form or the judge form, the model name field SHALL become empty. Save SHALL stay disabled until a model is typed or picked, and the field SHALL show the hint "Choose a model for this provider."

#### Scenario: Ollama name not carried to llama.cpp

- **WHEN** the Chat form opens with the provider Ollama and the model `qwen3:4b` and the user selects llama.cpp
- **THEN** the model name field MUST be empty and Save MUST be disabled

### Requirement: A Document reading save goes to omrs.jsonc for the next launch

A save in the Document reading section SHALL write the changed keys into `omrs.jsonc` with the file revision the page last read. A save SHALL NOT change the value in force, except a save of `document_router`, which SHALL apply to the next request in `omrs web` and SHALL NOT offer the restart dialog. A refused save SHALL show the server message and SHALL leave the row unchanged.

#### Scenario: File edited while the page is open

- **WHEN** the user edits `omrs.jsonc` in an editor and then saves a row in Document reading
- **THEN** the page MUST show "omrs.jsonc changed on disk. Reload to see the new values." and MUST offer Reload

#### Scenario: Host router save applies at once

- **WHEN** the user saves a new host router and then ingests a file in the same running `omrs web`
- **THEN** the ingest MUST use the new router, and the restart dialog MUST NOT open

### Requirement: A save that leaves a key waiting offers a restart dialog

After a save that leaves a key waiting for a restart, the page SHALL offer the restart dialog and SHALL repeat the index identity note.

#### Scenario: Save a boolean

- **WHEN** the user turns maths routing off and presses Save
- **THEN** `omrs.jsonc` MUST hold `"ocr_maths_routing_enabled": false`, the row MUST show "Restart to apply", and the restart dialog MUST open

### Requirement: Use default removes a key from the file

"Use default" on a row SHALL remove the key from the file.

#### Scenario: Return to the default

- **WHEN** the file holds `"ocr_engine_fallback": "my-engine"` and the user presses "Use default" on that row
- **THEN** `omrs.jsonc` MUST no longer hold `ocr_engine_fallback`

### Requirement: Document reading edits the reader list in order

Settings › Document reading › PDF reading SHALL show the reader list as ordered rows. The user SHALL be able to add a registered reader, remove a reader, and move a reader up or down. Each row SHALL say what its position does: the first installed reader reads, a later reader retries when the readers before it returned no text. A reader that is not installed SHALL show "Not installed" and a link to Integrations › PDF readers. The page SHALL refuse to save an empty list.

#### Scenario: Move a reader up

- **GIVEN** the list `pdf_inspector, liteparse, pypdf`
- **WHEN** the user moves pypdf above LiteParse and saves
- **THEN** `omrs.jsonc` SHALL hold `"pdf_readers": ["pdf_inspector", "pypdf", "liteparse"]`
- **AND** the row SHALL show "Restart to apply"

#### Scenario: Empty list refused

- **WHEN** the user removes every reader and saves
- **THEN** the page SHALL show the reason and write nothing

### Requirement: Document reading edits the OCR engine list in order

The Engines block SHALL show the OCR engine list as ordered rows with add, remove, move up and move down. Each row SHALL say that a later engine runs only when the engines before it are unavailable before dispatch. An engine that is not provisioned SHALL show "Not provisioned". A list of one engine SHALL be allowed, so the user can turn the fallback off on the page.

#### Scenario: Remove the fallback engine

- **GIVEN** the list `dots-mocr, paddleocr-vl`
- **WHEN** the user removes PaddleOCR-VL and saves
- **THEN** `omrs.jsonc` SHALL hold `"ocr_engines": ["dots-mocr"]`
- **AND** no fallback engine SHALL run after the restart

#### Scenario: Locked by the environment

- **GIVEN** `OCR_ENGINES` or `OCR_ENGINE_PRIMARY` is set in the environment
- **WHEN** the Engines block renders
- **THEN** the list SHALL be read-only and SHALL name the variable to remove

### Requirement: Document reading lists render at desktop and phone widths

The two list controls SHALL fit a 1280 px window and a 390 px window with no horizontal page scroll. At 390 px the move and remove buttons SHALL stay reachable and labelled for screen readers.

#### Scenario: Phone width

- **WHEN** the page renders at 390 px
- **THEN** every list row and its buttons SHALL be visible without horizontal scrolling

### Requirement: Document reading shows non-Latin routing

Settings › Document reading SHALL show `ocr_non_latin_routing` in the "When to use OCR" block as a choice of `off`, `detect` and `always`. The row SHALL say that `detect` sees only text that already exists and does not catch scanned pages, and that `always` suits a collection known to be non-Latin. It SHALL follow the restart, lock and identity rules of the other Document reading rows.

#### Scenario: Row explains what detect cannot see

- **WHEN** the row renders
- **THEN** it SHALL say that `detect` does not catch scanned pages and SHALL name `always` for a known non-Latin collection

#### Scenario: Save always

- **WHEN** the user chooses `always` and saves
- **THEN** `omrs.jsonc` SHALL hold `"ocr_non_latin_routing": "always"`
- **AND** the row SHALL show "Restart to apply"

### Requirement: Providers shows a Decision models card

Settings › Providers SHALL show a Decision models card. It SHALL list each entry with its name, kind, model, image flag, local or hosted, and its key state (set, missing or not needed) without the key. The user SHALL be able to add, edit, test and remove an entry. A managed local entry SHALL show its model file, projector file and runtime state.

#### Scenario: Add a local entry

- **WHEN** the user adds a `llamacpp` entry with a Q8_0 model file and a projector file and saves
- **THEN** `omrs.jsonc` SHALL hold the entry under `decision_models`
- **AND** the card SHALL show "Not tested" until the user presses Test

#### Scenario: Remove an entry in use

- **GIVEN** router `handwriting` names entry `clef-local`
- **WHEN** the user removes `clef-local`
- **THEN** the removal SHALL be refused and the message SHALL name the router

### Requirement: Document reading has a Router section

Settings › Document reading SHALL have a Router section. It SHALL show the host router choice (a router name or "None"), and one row per router with its decision model, question, threshold, image flag. The user SHALL be able to create a router from blank or from the Experiment 43 template, edit, rename and delete it.

#### Scenario: Choose the host router

- **WHEN** the user picks `handwriting` as the host router and saves
- **THEN** `omrs.jsonc` SHALL hold `"document_router": "handwriting"`
- **AND** the row SHALL show "Restart to apply"

#### Scenario: Locked by the environment

- **GIVEN** `DOCUMENT_ROUTER` is set in the environment
- **WHEN** the section renders
- **THEN** the host choice SHALL be read-only and SHALL name the variable

### Requirement: Hosted routers carry a visible warning and an opt-in

A router on a hosted decision model SHALL show, on its row and in its form, that page text, and page images when the image flag is on, go to the named third party. Its form SHALL have a "send pages off this machine" checkbox that is off by default. The row SHALL say "Will not run" while the checkbox is off.

#### Scenario: Opt-in off

- **GIVEN** a new router on the hosted `jev` entry
- **WHEN** the user saves without ticking the checkbox
- **THEN** the row SHALL show the warning and "Will not run"

### Requirement: Router controls render at desktop and phone widths

The Decision models card and the Router section SHALL fit a 1280 px window and a 390 px window with no horizontal page scroll. The question text SHALL wrap.

#### Scenario: Phone width

- **WHEN** the Router section renders at 390 px
- **THEN** every row, warning and button SHALL be visible without horizontal scrolling

### Requirement: Document reading edits the confidence cut of each local OCR backend

Settings › Document reading › Local OCR › "Local OCR backends" SHALL give each listed backend row a "Confidence cut" number input from 0 to 1. An empty input SHALL show the backend's default cut and SHALL mean "use the default". A save SHALL write `ocr_local_cuts` with one entry for each filled input and SHALL keep the entries of backends that are not listed. A save with no entries SHALL remove the key.

#### Scenario: Default shown when unset

- **GIVEN** the list `pp-ocrv6-small` and no `ocr_local_cuts` in any source
- **WHEN** the Local OCR group renders
- **THEN** the PP-OCRv6 small row MUST show an empty "Confidence cut" input with the default 0.92 shown in it

#### Scenario: Set a cut and save

- **GIVEN** the list `pp-ocrv6-small, indra`
- **WHEN** the user types 0.95 in the Indra row and presses Save
- **THEN** `omrs.jsonc` MUST hold `"ocr_local_cuts": {"indra": 0.95}`
- **AND** the group MUST show "Restart to apply"

#### Scenario: Clear the last cut

- **GIVEN** `omrs.jsonc` holds `"ocr_local_cuts": {"indra": 0.95}` and the list `pp-ocrv6-small, indra`
- **WHEN** the user empties the Indra input and presses Save
- **THEN** `omrs.jsonc` MUST no longer hold `ocr_local_cuts`

#### Scenario: Value out of range

- **WHEN** the user types 1.5 in a cut input
- **THEN** the page MUST show "The cut must be a number from 0 to 1." beside the input
- **AND** Save MUST send nothing

#### Scenario: Locked by the environment

- **GIVEN** `OCR_LOCAL_CUTS` is set in the environment
- **WHEN** the Local OCR group renders
- **THEN** every cut input MUST be read-only and the group MUST show "Remove OCR_LOCAL_CUTS from the environment or .env to edit it here."

#### Scenario: Phone width

- **WHEN** the page renders at 390 px
- **THEN** every backend row, its cut input and its buttons MUST be visible without horizontal scrolling
- **AND** each cut input MUST have a label that names its backend

### Requirement: Document reading routes carry the local OCR cuts

`GET /v1/settings/document-reading` SHALL return an `ocr_local_cuts` entry with the value in force, the saved value, the source, the lock state and the default empty map. Each local OCR backend option SHALL carry its default cut. `PUT` SHALL accept `ocr_local_cuts` as an object or `null`. It SHALL answer 400 for a name that cannot be listed or a value that is not a number from 0 to 1, with no submitted value in the message.

#### Scenario: Read the cuts

- **WHEN** a session with the read scope sends `GET /v1/settings/document-reading`
- **THEN** the answer MUST hold an `ocr_local_cuts` entry
- **AND** the `pp-ocrv6-small` backend option MUST carry the default cut 0.92

#### Scenario: Refused value

- **WHEN** a `PUT` sets `ocr_local_cuts` to `{"pp-ocrv6-small": 2}`
- **THEN** the server MUST answer 400, the file MUST NOT change, and the message MUST NOT contain `2`

### Requirement: Document reading offers to remove the retired cut key

When `omrs.jsonc` holds `ocr_local_min_confidence`, the Local OCR group SHALL show "omrs.jsonc holds ocr_local_min_confidence. OMRS ignores it. Each backend now has its own cut." with a "Remove it" button. The button and every save of `ocr_local_cuts` SHALL remove the old key in the same write, with the revision check, the atomic replace and the comments kept.

#### Scenario: Remove the old key from the page

- **GIVEN** `omrs.jsonc` holds `"ocr_local_min_confidence": 0.9` and a comment above it
- **WHEN** the user presses "Remove it"
- **THEN** `omrs.jsonc` MUST no longer hold `ocr_local_min_confidence`
- **AND** every other key and comment in the file MUST stay
- **AND** the notice MUST go

#### Scenario: Saving a cut removes the old key

- **GIVEN** `omrs.jsonc` holds `"ocr_local_min_confidence": 0.9`
- **WHEN** the user sets the PP-OCRv6 small cut to 0.9 and presses Save
- **THEN** `omrs.jsonc` MUST hold `"ocr_local_cuts": {"pp-ocrv6-small": 0.9}` and MUST NOT hold `ocr_local_min_confidence`

### Requirement: The retired cut key notice respects the environment lock

When `omrs.jsonc` holds `ocr_local_min_confidence` and `OCR_LOCAL_CUTS` locks the cuts, the notice SHALL NOT show the "Remove it" button. It SHALL say that `OCR_LOCAL_CUTS` is set in the environment or `.env`, and that the operator removes `ocr_local_min_confidence` from `omrs.jsonc` by hand.

#### Scenario: Locked cuts

- **GIVEN** `omrs.jsonc` holds `ocr_local_min_confidence` and `OCR_LOCAL_CUTS` is set in the environment
- **WHEN** the Local OCR group renders
- **THEN** the notice MUST show without a "Remove it" button
- **AND** it MUST name `OCR_LOCAL_CUTS` and tell the operator to remove the key from `omrs.jsonc` by hand

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

#### Scenario: Mode and address rows

- **WHEN** the Router panel opens with no source set
- **THEN** it MUST show the mode row with "OMRS runs llama.cpp" selected and the address row with `http://127.0.0.1:8080/v1`

### Requirement: The Router panel shows and edits the model limit and the memory margin

The Router panel SHALL show two rows: "Models loaded at once" (`llamacpp_router_models_max`, 1 to 16) and "Free memory margin (MiB)" (`llamacpp_router_memory_margin_mib`, 0 to 262,144). Each row SHALL show the value in force, its source, its default and one plain help line, and SHALL offer Edit, Save and Use default. A saved value that differs from the running router's SHALL show "Restart to apply". A save SHALL need `manage`. A locked row SHALL show the variable name and offer no edit.

#### Scenario: Defaults shown

- **WHEN** no source sets either value
- **THEN** "Models loaded at once" MUST show 4 with source default, and "Free memory margin (MiB)" MUST show 8,192 with source default, each with its default and help line

#### Scenario: Edit and save the model limit

- **WHEN** the user edits "Models loaded at once" to 2 and saves
- **THEN** `omrs.jsonc` MUST hold `llamacpp_router_models_max` 2, the row MUST show source `omrs.jsonc`, and the panel MUST show "Restart to apply"

#### Scenario: Use default

- **WHEN** the user presses Use default on "Free memory margin (MiB)" that holds 16,384 from `omrs.jsonc`
- **THEN** the key MUST leave `omrs.jsonc` and the row MUST show 8,192 with source default

#### Scenario: Out of range refused

- **WHEN** the user saves 17 for "Models loaded at once" or 262,145 for "Free memory margin (MiB)"
- **THEN** the page MUST show the accepted range, the server MUST return 400 and nothing MUST be saved

#### Scenario: Locked by environment

- **WHEN** `LLAMACPP_ROUTER_MODELS_MAX` is set in the environment
- **THEN** the "Models loaded at once" row MUST show a lock and name the variable, and MUST offer no edit

### Requirement: The Chat section asks for a Chat model when none is chosen

When `answer.provider` is `llamacpp` and `answer.model` is empty, the Chat section SHALL show "Choose a Chat model" with a picker of the router list entries and "Get this model" for an entry that has no file. It SHALL NOT pick the classification model for the user. An entry that holds `embeddings` true SHALL NOT be offered.

#### Scenario: Fresh install Chat page

- **WHEN** OMRS starts with no `omrs.jsonc` and the user opens Settings > Chat
- **THEN** the page MUST show "Choose a Chat model" and a picker that lists the shipped entries without the embedding entry

#### Scenario: Pick a model

- **WHEN** the user picks `Qwen/Qwen3-4B-GGUF:Q8_0` and saves
- **THEN** `omrs.jsonc` MUST hold `answer.model` with that value and the entry MUST list the roles Chat and classification

### Requirement: The Chat section warns when Chat shares the classification model

When `answer.provider` is `llamacpp` and `answer.model` equals `llamacpp_chat_model`, the Chat section SHALL show a warning note that lists ways out, each linked to the control that sets it. The note SHALL NOT block Save. The Router panel row of the shared entry SHALL show a one-line warning.

#### Scenario: Chat picks the classification model

- **WHEN** the user saves `answer.model` equal to `llamacpp_chat_model` with provider `llamacpp`
- **THEN** the save MUST succeed and the Chat section MUST say "Chat and classification share this model. A long Chat answer can slow classification during an ingest. A context size change reloads the model for both."

#### Scenario: The note lists three ways out

- **WHEN** the shared-model warning shows
- **THEN** it MUST offer: choose another local model on the router; use your own llama.cpp server for Chat through the OpenAI-compatible provider (OMRS does not run it); or use a hosted provider such as OpenRouter

#### Scenario: Router panel row

- **WHEN** the shared-model warning shows
- **THEN** the Router panel row of that entry MUST show "Shared by Chat and classification"

#### Scenario: Chat uses another model

- **WHEN** `answer.model` differs from `llamacpp_chat_model`, or `answer.provider` is not `llamacpp`
- **THEN** the Chat section MUST NOT show the warning

### Requirement: The Router panel lists the models in a table

The panel SHALL show one table row per `llamacpp_models` entry with its roles, model name, file state, context size in tokens and model state. A row SHALL offer Edit (one control per allow-listed preset value), Get this model when it has no file, and Remove when it holds no role. A changed row of a running router SHALL show "Reload pending" until the reload ends. Each role SHALL link to the setting that gives it.

#### Scenario: Shipped list on a fresh install

- **WHEN** OMRS starts with no `omrs.jsonc`
- **THEN** the table MUST show `Qwen/Qwen3-Embedding-4B-GGUF:Q8_0` with the role Embeddings and `Qwen/Qwen3-4B-GGUF:Q8_0` with the role Classification only, both "Not downloaded"

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
