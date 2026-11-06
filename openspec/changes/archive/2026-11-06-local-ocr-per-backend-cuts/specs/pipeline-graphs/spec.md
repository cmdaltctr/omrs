## ADDED Requirements

### Requirement: The Read document step sets local OCR cuts

The `read.document` operation SHALL accept an optional `ocr_local_cuts` map from backend name to cut. `null` SHALL inherit the host map. Each set value SHALL pass the same rule as `ocr_local_cuts` on Settings › Document reading. A step entry SHALL replace the host cut of its own backend for that pipeline only. A backend with no step entry SHALL keep the host's effective cut. A graph-wide override of `ocr_local_cuts` SHALL be a host-owned setting.

#### Scenario: Step cut replaces one host cut

- **GIVEN** the host map `{"indra": 0.96}` and a Read document node that sets `ocr_local_backends` to `["pp-ocrv6-small", "indra"]` and `ocr_local_cuts` to `{"pp-ocrv6-small": 0.88}`
- **WHEN** the node reads a PDF
- **THEN** PP-OCRv6 small SHALL use 0.88 and Indra SHALL use 0.96
- **AND** other pipelines and the standard ingest path SHALL keep the host cuts

#### Scenario: Out-of-range step cut refused

- **WHEN** a Read document node sets `ocr_local_cuts` to `{"pp-ocrv6-small": 1.4}`
- **THEN** validation SHALL fail with issue code `invalid_parameter` before any node runs
- **AND** the message SHALL NOT contain `1.4`

#### Scenario: Unknown backend in a step cut refused

- **WHEN** a Read document node sets `ocr_local_cuts` to `{"nope": 0.9}`
- **THEN** validation SHALL fail with issue code `invalid_parameter` before any node runs

#### Scenario: Graph-wide cut override stays host-owned

- **WHEN** a graph sets `overrides.ocr_local_cuts`
- **THEN** validation SHALL fail with issue code `host_owned_setting`
- **AND** the message SHALL tell the user to set the cuts on the Read document step

### Requirement: Step cuts enter the PDF identity only

Graph ingestion SHALL compute each source's index identity with the effective cuts of the Read document node in the commit node's ancestor slice. A step cut SHALL enter the PDF `parser` block only, as the host cuts do, and SHALL NOT enter the graph fingerprint. A node that leaves `ocr_local_cuts` empty, or sets only the host's effective values, SHALL keep the identity of the standard ingest path. A saved graph without the key SHALL keep its fingerprint.

#### Scenario: A step cut change re-indexes PDF sources only

- **GIVEN** a collection with one PDF source and one Markdown source, indexed through a graph whose Read document node leaves `ocr_local_cuts` empty
- **WHEN** the node sets `ocr_local_cuts` to `{"pp-ocrv6-small": 0.95}` and an explicit ingest runs
- **THEN** the PDF source SHALL be processed again
- **AND** the Markdown source SHALL keep its digest and SHALL NOT be processed

#### Scenario: Saved graph keeps its fingerprint

- **GIVEN** a graph saved before this change
- **WHEN** its fingerprint is computed after this change
- **THEN** the fingerprint SHALL be unchanged

#### Scenario: Host value set on the step keeps the identity

- **GIVEN** the host map is empty
- **WHEN** a Read document node sets `ocr_local_cuts` to `{"pp-ocrv6-small": 0.92}`
- **THEN** every source SHALL keep the identity of the standard ingest path

### Requirement: Studio shows a cut box beside each backend of the Read document step

The Read document step in Studio SHALL show the `ocr_local_cuts` option as one "Confidence cut" number input beside each backend of the step's effective local OCR list (the step's own list, else the inherited host list). An empty input SHALL show the inherited cut: the host entry when there is one, else the backend's default. An empty input SHALL mean "inherit". A value outside 0 to 1 SHALL show the reason and SHALL NOT be saved.

#### Scenario: Inherited cuts shown

- **GIVEN** the host map `{"indra": 0.96}` and a Read document step whose list inherits `pp-ocrv6-small, indra`
- **WHEN** the user opens the step in Studio
- **THEN** the PP-OCRv6 small input SHALL be empty and show 0.92
- **AND** the Indra input SHALL be empty and show 0.96

#### Scenario: Set a step cut

- **WHEN** the user types 0.88 in the PP-OCRv6 small input of the step and saves the pipeline
- **THEN** the saved step SHALL hold `"ocr_local_cuts": {"pp-ocrv6-small": 0.88}`

#### Scenario: Clear every step cut

- **GIVEN** a step that holds `"ocr_local_cuts": {"pp-ocrv6-small": 0.88}`
- **WHEN** the user empties the input and saves the pipeline
- **THEN** the saved step SHALL NOT hold `ocr_local_cuts`, so it inherits the host map like every other cleared step option

#### Scenario: Value out of range

- **WHEN** the user types 1.4 in a step cut input
- **THEN** the step SHALL show "The cut must be a number from 0 to 1." beside the input
- **AND** the pipeline save SHALL NOT send the value

#### Scenario: Built-in profile is read-only

- **WHEN** the user opens the Read document step of a built-in profile
- **THEN** every cut input SHALL be read-only
