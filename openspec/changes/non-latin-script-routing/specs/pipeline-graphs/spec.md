## MODIFIED Requirements

### Requirement: The Read document step sets its OCR options

The `read.document` operation SHALL accept these optional settings: `ocr_fallback_enabled`, `ocr_routing_unit`, `ocr_engines`, `ocr_maths_routing_enabled`, `ocr_non_latin_routing`, and the older `ocr_engine_primary` and `ocr_engine_fallback`. `null` SHALL inherit the host value. Each set value SHALL pass the same rule as the matching key on Settings › Document reading. A graph-wide override of any of these keys SHALL remain a host-owned setting.

#### Scenario: Engine not provisioned

- **WHEN** a Read document node lists, in `ocr_engines`, an engine that is not provisioned under the host workers folder
- **THEN** validation SHALL fail with issue code `option_unavailable`
- **AND** the issue SHALL name the node, the engine and the provision command
- **AND** no node SHALL run

#### Scenario: Removed key refused

- **WHEN** a Read document node sets `ocr_maths_page_fraction`, `ocr_fallback_page_fraction` or `ocr_fallback_min_confidence`
- **THEN** validation SHALL fail with issue code `invalid_parameter` before any node runs

#### Scenario: Document unit refused

- **WHEN** a Read document node sets `ocr_routing_unit` to `document`
- **THEN** validation SHALL fail with issue code `invalid_parameter` before any node runs

#### Scenario: Graph-wide OCR override stays host-owned

- **WHEN** a graph sets `overrides.ocr_engine_primary` or `overrides.ocr_engines`
- **THEN** validation SHALL fail with issue code `host_owned_setting`
- **AND** the message SHALL tell the user to set the engine on the Read document step

#### Scenario: Studio lists the engines

- **WHEN** the user opens the Read document step of a user profile in Studio
- **THEN** the engine choices SHALL be the engines of the OCR engines group, each marked ready or not, and an "Inherit" choice

#### Scenario: Step sets always

- **WHEN** a Read document node of an Arabic collection's profile sets `ocr_non_latin_routing` to `always`
- **THEN** that node SHALL send every flagged page past the local tier
- **AND** other pipelines SHALL keep the host value

#### Scenario: Invalid non-Latin routing value

- **WHEN** a node sets `ocr_non_latin_routing` to `arabic`
- **THEN** validation SHALL fail with issue code `invalid_parameter` before any node runs

### Requirement: Ingestion identity records the step OCR settings

Graph ingestion SHALL compute each source's index identity with the effective OCR settings of the Read document node in the commit node's ancestor slice, in the same way as the step reader. This SHALL include `ocr_non_latin_routing`. A node that inherits every OCR setting SHALL keep the identity of the standard ingest path.

#### Scenario: Engine change forces reprocessing

- **WHEN** a source was indexed through a graph whose Read document node inherits `dots-mocr`, and the node then sets `ocr_engine_primary` to `paddleocr-vl`
- **THEN** the next explicit ingest SHALL process the source again

#### Scenario: Inheriting keeps the standard identity

- **WHEN** the canonical ingestion template runs with every OCR setting empty
- **THEN** its sources SHALL keep the same identity as the standard ingest path

#### Scenario: Step non-Latin routing forces reprocessing of PDF sources

- **WHEN** a PDF source was indexed through a graph whose Read document node inherits `off`, and the node then sets `ocr_non_latin_routing` to `always`
- **THEN** the next explicit ingest SHALL process the PDF source again
