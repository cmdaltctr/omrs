## MODIFIED Requirements

### Requirement: Several routers can exist and are picked by name

The operator SHALL be able to create, rename and delete routers. The host default `document_router` (env `DOCUMENT_ROUTER`) SHALL name one router or be empty. Empty SHALL mean no router, and SHALL be the default. A Read document step SHALL be able to pick a router by name or turn routing off for that step. A router or host default saved through `omrs web` SHALL apply to the next request in that process, as `decision_models` and `llamacpp_models` do. A value set by `env` or `dotenv` SHALL stay locked. Other OMRS processes (CLI, stdio MCP server, watcher) SHALL read the file at launch.

#### Scenario: No router by default

- **WHEN** no source sets `document_router`
- **THEN** no page SHALL be judged
- **AND** reading SHALL behave exactly as before this change

#### Scenario: Delete a router in use

- **GIVEN** a saved profile's Read document step names router `handwriting`
- **WHEN** the user deletes `handwriting`
- **THEN** the delete SHALL be refused and the message SHALL name the profile

#### Scenario: Saved router applies to the next request

- **GIVEN** `omrs web` runs and `DOCUMENT_ROUTER` is not set in the environment
- **WHEN** the user saves a change to router `handwriting` and then ingests a file
- **THEN** the ingest SHALL use the saved router without a restart
