## MODIFIED Requirements

### Requirement: OCR routing follows the step reader under host OCR settings

A Read document node SHALL apply the OCR routing that its effective reader supports. Each OCR setting SHALL come from the node when the node sets it, and from the host settings otherwise. A node SHALL use only OCR engines provisioned under the host's `ocr_workers_dir`. A node SHALL NOT change the host settings, the workers folder or an engine command. Built-in profiles run no saved pipeline and SHALL keep the host OCR settings.

#### Scenario: Step selects a reader without OCR routing

- **WHEN** the host reader is `pdf_inspector` with OCR fallback enabled and a Read document node selects `pypdf`
- **THEN** the node SHALL read PDF sources without OCR routing

#### Scenario: Step selects pdf-inspector on a host with another default

- **WHEN** the host reader is `pypdf`, the host enables OCR fallback, and a Read document node selects `pdf_inspector`
- **THEN** OCR-required PDF sources SHALL route through the OCR routes of the node's effective engines
- **AND** when no route is available, the node SHALL keep the partial text and report the degradation, as the standard path does

#### Scenario: Step selects another primary engine

- **WHEN** the host primary engine is `dots-mocr` and a Read document node sets `ocr_engine_primary` to `paddleocr-vl`
- **THEN** OCR-required PDF sources of that node SHALL go to the `paddleocr-vl` worker
- **AND** a node that leaves the engine empty SHALL still use `dots-mocr`

#### Scenario: Step turns OCR off

- **WHEN** the host enables OCR fallback and a Read document node sets `ocr_fallback_enabled` to `false`
- **THEN** that node SHALL read PDF sources without OCR routing

## ADDED Requirements

### Requirement: Read document step sets OCR options

The `read.document` operation SHALL accept these optional settings: `ocr_fallback_enabled`, `ocr_fallback_min_confidence`, `ocr_fallback_page_fraction`, `ocr_routing_unit`, `ocr_engine_primary`, `ocr_engine_fallback`, `ocr_maths_routing_enabled` and `ocr_maths_page_fraction`. `null` SHALL inherit the host value. Each set value SHALL pass the same rule as the matching key on Settings › Document reading. A graph-wide override of any of these keys SHALL remain a host-owned setting.

#### Scenario: Engine not provisioned

- **WHEN** a Read document node sets `ocr_engine_primary` to an engine that is not provisioned under the host workers folder
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

### Requirement: Ingestion identity records the step OCR settings

Graph ingestion SHALL compute each source's index identity with the effective OCR settings of the Read document node in the commit node's ancestor slice, in the same way as the step reader. A node that inherits every OCR setting SHALL keep the identity of the standard ingest path.

#### Scenario: Engine change forces reprocessing

- **WHEN** a source was indexed through a graph whose Read document node inherits `dots-mocr`, and the node then sets `ocr_engine_primary` to `paddleocr-vl`
- **THEN** the next explicit ingest SHALL process the source again

#### Scenario: Inheriting keeps the standard identity

- **WHEN** the canonical ingestion template runs with every OCR setting empty
- **THEN** its sources SHALL keep the same identity as the standard ingest path

### Requirement: Step OCR workers share one pool

The host SHALL keep one lazy worker client per engine name, shared by every node and by the host routes. A worker SHALL start only on its first dispatch. At most one OCR worker SHALL parse at a time per Engine, so that two engines do not hold peak memory together.

#### Scenario: Two nodes, one engine

- **WHEN** two Read document nodes both use `paddleocr-vl`
- **THEN** one `paddleocr-vl` worker process SHALL serve both

#### Scenario: Two engines in one run

- **WHEN** one node uses `dots-mocr` and another uses `paddleocr-vl`
- **THEN** the two workers SHALL NOT parse at the same time
