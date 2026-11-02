## ADDED Requirements

### Requirement: Read document step picks a router by name

The `read.document` operation SHALL accept an optional `document_router`: a router name, the value `none`, or `null`. `null` SHALL inherit the host router. `none` SHALL turn routing off for the step. A name that no router holds SHALL fail validation with `option_unavailable` before any node runs. The step's router SHALL enter its ingestion identity under the same rule as the host router.

#### Scenario: Step picks a router

- **WHEN** a Read document node sets `document_router` to `handwriting`
- **THEN** that node SHALL judge pages with `handwriting`
- **AND** other pipelines SHALL keep the host router

#### Scenario: Unknown router name

- **WHEN** a node sets `document_router` to `missing`
- **THEN** validation SHALL fail with issue code `option_unavailable` naming the node and the router
- **AND** no node SHALL run
