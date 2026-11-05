## ADDED Requirements

### Requirement: omrs.jsonc holds decision models and routers as named maps

`omrs.jsonc` SHALL accept `decision_models` and `document_routers` as objects keyed by entry name. They SHALL be file-only: no environment variable SHALL set a map. `document_router`, the host router name, SHALL follow the normal source order and MAY come from the environment. An entry with an unknown field or a wrong type SHALL be ignored and listed as a problem, and the other entries SHALL still load.

#### Scenario: Hand-written router

- **GIVEN** `omrs.jsonc` holds one decision model `clef-local` and one router `handwriting` that names it
- **WHEN** settings resolve
- **THEN** both SHALL be available by name with source `config-file`

#### Scenario: Broken entry

- **GIVEN** a router whose threshold is `"high"`
- **WHEN** settings resolve
- **THEN** that router SHALL be ignored and listed as a problem naming the field
- **AND** the other routers SHALL load

### Requirement: Only the web server writes the maps

Only `omrs web` SHALL write `decision_models` and `document_routers`, through the Settings page, with the revision check, the atomic replace and comments kept. The CLI, the stdio MCP server and the watcher SHALL read them only. A key field inside an entry SHALL hold a reference only.

#### Scenario: CLI reads a router

- **GIVEN** `DOCUMENT_ROUTER=handwriting` and the router in `omrs.jsonc`
- **WHEN** `omrs ingest` runs
- **THEN** it SHALL use the router and SHALL NOT write the file
