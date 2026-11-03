# Spec Delta

## ADDED Requirements

### Requirement: The Read document step sets its OCR options

The `read.document` operation SHALL accept these optional settings: `ocr_fallback_enabled`, `ocr_routing_unit`, `ocr_engine_primary`, `ocr_engine_fallback` and `ocr_maths_routing_enabled`. `null` SHALL inherit the host value. Each set value SHALL pass the same rule as the matching key on Settings › Document reading. A graph-wide override of any of these keys SHALL remain a host-owned setting.

#### Scenario: Engine not provisioned

- **WHEN** a Read document node sets `ocr_engine_primary` to an engine that is not provisioned under the host workers folder
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

- **WHEN** a graph sets `overrides.ocr_engine_primary`
- **THEN** validation SHALL fail with issue code `host_owned_setting`
- **AND** the message SHALL tell the user to set the engine on the Read document step

#### Scenario: Studio lists the engines

- **WHEN** the user opens the Read document step of a user profile in Studio
- **THEN** the engine choices SHALL be the engines of the OCR engines group, each marked ready or not, and an "Inherit" choice

## REMOVED Requirements

### Requirement: Read document step sets OCR options

**Reason**: Replaced by "The Read document step sets its OCR options". The document unit and the three fraction and confidence keys are gone, so the fraction scenario no longer holds.
