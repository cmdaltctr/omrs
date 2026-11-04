## Purpose

Let the local OCR tier read pages with more than one backend, where each backend has its own confidence cut, and keep the default behaviour and the default index identity unchanged.

## ADDED Requirements

### Requirement: The local OCR backend SHALL be injected configuration

The system SHALL read `ocr_local_backend` (env `OCR_LOCAL_BACKEND`) from the injected settings. The default SHALL be `pp-ocrv6-small`. An unknown value SHALL stop start-up with a message that names the accepted values. The accepted values SHALL be the registered backends that hold a calibrated confidence cut.

#### Scenario: Default

- **WHEN** no source sets the key
- **THEN** the value SHALL be `pp-ocrv6-small`
- **AND** the local tier SHALL read pages with pdf-inspector as before this change

#### Scenario: Unknown value

- **WHEN** `OCR_LOCAL_BACKEND=indra` is set and no backend named `indra` is registered
- **THEN** start-up SHALL fail
- **AND** the message SHALL name `pp-ocrv6-small` as an accepted value

#### Scenario: Backend without a calibrated cut

- **GIVEN** a backend registered with no calibrated cut
- **WHEN** `OCR_LOCAL_BACKEND` names that backend
- **THEN** start-up SHALL fail
- **AND** the message SHALL say that the backend has no calibrated cut

### Requirement: A backend SHALL return one result per page it read

A backend SHALL take a PDF path, 1-based page numbers and the injected settings. For each page it read, it SHALL return the page number, the text, one page confidence and the model identity. The page confidence SHALL be a number from 0 to 1, or none when the backend reports none. A page the backend did not return SHALL count as missing. A backend SHALL NOT decide whether a page escalates.

#### Scenario: Backend returns text and confidence

- **WHEN** the local tier asks a backend for pages 2 and 5
- **THEN** the backend SHALL return a result for each page it read
- **AND** each result SHALL hold the text, the page confidence and the model identity

#### Scenario: Missing page

- **WHEN** a backend returns no result for a requested page
- **THEN** the shared rule SHALL escalate that page with the reason `missing_page`

### Requirement: A line-based backend SHALL reduce line confidences to one page confidence by a fixed rule

A backend that reports a confidence for each line SHALL give the page confidence as the mean of the line confidences, weighted by the number of characters in each line. A different rule SHALL be adopted only after a recorded experiment supports it.

#### Scenario: Weighted mean

- **GIVEN** a page with two lines: 90 characters at confidence 0.95 and 10 characters at confidence 0.45
- **WHEN** the backend reduces the confidences
- **THEN** the page confidence SHALL be 0.90

### Requirement: Every backend SHALL use the same escalation rule

The shared rule in the local tier SHALL decide escalation for every backend. A page SHALL escalate when it is missing, when its text is empty, when its confidence is missing or below the effective cut, when the backend recommends the hosted engine, or when the non-Latin post-check applies. The reasons SHALL keep their present names.

#### Scenario: Low confidence from a second backend

- **GIVEN** a registered backend with a calibrated cut of 0.7
- **WHEN** it returns a page with text and confidence 0.65
- **THEN** the page SHALL escalate with the reason `low_confidence`

#### Scenario: No reason fires

- **GIVEN** a registered backend with a calibrated cut of 0.7
- **WHEN** it returns a page with text, confidence 0.75 and no recommendation
- **THEN** the page SHALL keep its local text

### Requirement: The confidence cut SHALL belong to the backend

Each backend SHALL register a calibrated cut together with the name of the recorded experiment that fixed it, or no cut. Registration with a cut and no experiment name SHALL fail. `ocr_local_min_confidence` SHALL be optional. When it is unset, the effective cut SHALL be the cut of the selected backend. When it is set, the set value SHALL replace the backend's cut. The cut of `pp-ocrv6-small` SHALL be 0.9.

#### Scenario: Default cut

- **GIVEN** `ocr_local_backend` is `pp-ocrv6-small` and `ocr_local_min_confidence` is unset
- **WHEN** the effective cut is resolved
- **THEN** it SHALL be 0.9

#### Scenario: Operator value replaces the backend cut

- **GIVEN** `ocr_local_min_confidence` is set to 0.7
- **WHEN** the effective cut is resolved
- **THEN** it SHALL be 0.7 for any backend

#### Scenario: Cut without an experiment

- **WHEN** a backend is registered with a cut and no experiment name
- **THEN** registration SHALL fail

### Requirement: The backend SHALL participate in the source index identity

The `local_tier` block of the source index identity SHALL hold the resolved cut and, when it resolves, the model identity. When the backend is not the default, the block SHALL also hold the backend name. With the default backend, the block SHALL hold no backend name, so existing digests do not change.

#### Scenario: Default install keeps its digest

- **WHEN** an install with the default backend and an unset cut computes a source identity
- **THEN** the digest SHALL equal the digest before this change

#### Scenario: Another backend reindexes PDF sources

- **GIVEN** a page-unit collection indexed with `pp-ocrv6-small`
- **WHEN** the backend changes to another registered backend and an explicit ingest runs
- **THEN** PDF sources SHALL be processed again
- **AND** other sources SHALL keep their digest

#### Scenario: Cut change reindexes

- **GIVEN** a source indexed with the effective cut 0.9
- **WHEN** the effective cut becomes 0.85 and an explicit ingest runs
- **THEN** the source SHALL be processed again
