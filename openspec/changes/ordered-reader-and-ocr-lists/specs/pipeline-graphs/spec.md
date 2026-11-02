## MODIFIED Requirements

### Requirement: Read document step sets OCR options

The `read.document` operation SHALL accept these optional settings: `ocr_fallback_enabled`, `ocr_fallback_min_confidence`, `ocr_fallback_page_fraction`, `ocr_routing_unit`, `ocr_engines` (or the older `ocr_engine_primary` and `ocr_engine_fallback`), `ocr_maths_routing_enabled` and `ocr_maths_page_fraction`. `null` SHALL inherit the host value. Each set value SHALL pass the same rule as the matching key on Settings › Document reading. A graph-wide override of any of these keys SHALL remain a host-owned setting.

#### Scenario: Engine not provisioned

- **WHEN** a Read document node lists an engine in `ocr_engines` that is not provisioned under the host workers folder
- **THEN** validation SHALL fail with issue code `option_unavailable`
- **AND** the issue SHALL name the node, the engine and the provision command
- **AND** no node SHALL run

#### Scenario: Invalid fraction

- **WHEN** a Read document node sets `ocr_fallback_page_fraction` to `1.5`
- **THEN** validation SHALL fail with issue code `invalid_parameter` before any node runs

#### Scenario: Graph-wide OCR override stays host-owned

- **WHEN** a graph sets `overrides.ocr_engine_primary`
- **THEN** validation SHALL fail with issue code `host_owned_setting`
- **AND** the message SHALL tell the user to set the engine on the Read document step

#### Scenario: Studio lists the engines

- **WHEN** the user opens the Read document step of a user profile in Studio
- **THEN** the engine choices SHALL be the engines of the OCR engines group, each marked ready or not, and an "Inherit" choice

## ADDED Requirements

### Requirement: Read document step accepts a reader list

The `read.document` operation SHALL accept an optional `pdf_readers` list of registered concrete readers. `null` SHALL inherit the host list. The list SHALL follow the host list rules: the first installed reader reads, later readers are retry tiers, and `auto` is refused. Every listed reader SHALL be installed, or validation SHALL fail with `option_unavailable`.

#### Scenario: Step list reads PDF sources

- **WHEN** a Read document node sets `pdf_readers` to `pdf_inspector, pypdfium2`
- **THEN** that node SHALL read PDF sources with pdf-inspector and retry with pypdfium2 only
- **AND** other pipelines and the standard ingest path SHALL keep the host list

#### Scenario: Uninstalled reader in a step list

- **WHEN** a node lists a reader that is not installed
- **THEN** validation SHALL fail with issue code `option_unavailable` naming the node and the reader
- **AND** no node SHALL run

### Requirement: Old Read document options keep working

A saved graph whose Read document node sets `pdf_reader`, `ocr_engine_primary` or `ocr_engine_fallback` SHALL still validate and run. The single values SHALL expand to lists by the host expansion rules. A node that sets both an old option and its list SHALL fail validation with a message that names both keys.

#### Scenario: Saved graph with the old reader option

- **GIVEN** a saved graph whose Read document node sets `pdf_reader` to `pypdf`
- **WHEN** the graph runs
- **THEN** the node SHALL read with the list `pypdf`
- **AND** each source identity SHALL equal its identity before this change

#### Scenario: Old and new options together

- **WHEN** a node sets `ocr_engine_primary` and `ocr_engines`
- **THEN** validation SHALL fail and the message SHALL name both keys
