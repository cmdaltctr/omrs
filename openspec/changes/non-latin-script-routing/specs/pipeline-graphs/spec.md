## ADDED Requirements

### Requirement: Read document step sets non-Latin routing

The `read.document` operation SHALL accept an optional `ocr_non_latin_routing` with the values `off`, `detect` and `always`. `null` SHALL inherit the host value. A set value SHALL enter the step's ingestion identity under the same rule as the host value. A graph-wide override SHALL remain a host-owned setting.

#### Scenario: Step sets always

- **WHEN** a Read document node of an Arabic collection's profile sets `ocr_non_latin_routing` to `always`
- **THEN** that node SHALL send every flagged page past the local tier under the `page` unit
- **AND** other pipelines SHALL keep the host value

#### Scenario: Invalid value

- **WHEN** a node sets `ocr_non_latin_routing` to `arabic`
- **THEN** validation SHALL fail with issue code `invalid_parameter` before any node runs
