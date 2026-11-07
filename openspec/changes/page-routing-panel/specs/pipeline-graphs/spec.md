## ADDED Requirements

### Requirement: A step skip-blank value enters the PDF identity only

A Read document step value of `ocr_skip_blank_pages` SHALL NOT enter the graph fingerprint or the `graph_shape` block. It SHALL reach the identify step with the other step options and SHALL enter the PDF `parser` block the same way the host value does. A saved graph without the option SHALL keep its fingerprint.

#### Scenario: Step off re-indexes PDF sources only

- **GIVEN** a user profile that has indexed one PDF source and one Markdown source
- **WHEN** its Read document step sets `ocr_skip_blank_pages` to `false` and the profile ingests again
- **THEN** the PDF source digest SHALL change and the PDF source SHALL be re-indexed
- **AND** the Markdown source digest SHALL NOT change
- **AND** the graph fingerprint SHALL NOT change

#### Scenario: Step repeats the host value

- **GIVEN** the host value is `true`
- **WHEN** a Read document step sets `ocr_skip_blank_pages` to `true`
- **THEN** every source digest SHALL equal the digest with the option unset

#### Scenario: Saved graph keeps its fingerprint

- **GIVEN** a graph saved before this change
- **WHEN** its fingerprint is computed after the change
- **THEN** the fingerprint SHALL equal the saved value

## MODIFIED Requirements

### Requirement: The Read document step sets its OCR options

The `read.document` operation SHALL accept these optional settings: `ocr_fallback_enabled`, `ocr_routing_unit`, `ocr_engines`, `ocr_skip_blank_pages`, `ocr_maths_routing_enabled`, `ocr_non_latin_routing`, and the older `ocr_engine_primary` and `ocr_engine_fallback`. `null` SHALL inherit the host value. Each set value SHALL pass the same rule as the matching key on Settings › Document reading. A graph-wide override of any of these keys SHALL remain a host-owned setting.

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

#### Scenario: Step turns the blank drop off

- **WHEN** a Read document node sets `ocr_skip_blank_pages` to `false`
- **THEN** that node SHALL send blank flagged pages along the local tier and escalation path
- **AND** other pipelines SHALL keep the host value

#### Scenario: Skip-blank value not a boolean

- **WHEN** a node sets `ocr_skip_blank_pages` to the text `"no"`
- **THEN** validation SHALL fail with issue code `invalid_parameter` before any node runs

#### Scenario: Graph-wide skip-blank override stays host-owned

- **WHEN** a graph sets `overrides.ocr_skip_blank_pages`
- **THEN** validation SHALL fail with issue code `host_owned_setting`

### Requirement: Studio shows a cut box beside each backend of the Read document step

The Read document step in Studio SHALL show, in panel step 4 (Local OCR backends), the `ocr_local_cuts` option as one "Confidence cut" number input beside each backend of the step's effective local OCR list (the step's own list, else the inherited host list). An empty input SHALL show the inherited cut: the host entry when there is one, else the backend's default. An empty input SHALL mean "inherit". A value outside 0 to 1 SHALL show the reason and SHALL NOT be saved.

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
