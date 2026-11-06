## ADDED Requirements

### Requirement: Per-backend cuts SHALL be read from one map

The system SHALL read `ocr_local_cuts` (env `OCR_LOCAL_CUTS`) from the injected settings as a map from backend name to cut. The environment form SHALL be a JSON object. The `omrs.jsonc` form SHALL be an object. Each value SHALL be a number from 0 to 1. Each name SHALL be a backend that `ocr_local_backends` can list. The default SHALL be an empty map. An entry SHALL change the cut of its own backend only.

#### Scenario: Environment map sets one cut

- **GIVEN** `OCR_LOCAL_BACKENDS=pp-ocrv6-small,indra` and `OCR_LOCAL_CUTS={"indra": 0.96}`
- **WHEN** the effective cuts are resolved
- **THEN** the cut of `indra` SHALL be 0.96
- **AND** the cut of `pp-ocrv6-small` SHALL be its default, 0.92

#### Scenario: File map sets one cut

- **GIVEN** no environment value and `omrs.jsonc` holding `"ocr_local_cuts": {"pp-ocrv6-small": 0.88}`
- **WHEN** the effective cuts are resolved
- **THEN** the cut of `pp-ocrv6-small` SHALL be 0.88

#### Scenario: Entry for a backend that is not listed

- **GIVEN** the default list and `OCR_LOCAL_CUTS={"indra": 0.96}`
- **WHEN** the engine starts
- **THEN** start-up SHALL succeed
- **AND** the local tier SHALL read with `pp-ocrv6-small` at 0.92 only

### Requirement: A bad cut map from the environment SHALL stop start-up

When `OCR_LOCAL_CUTS` in the environment or `.env` names a backend that cannot be listed, holds a value that is not a number, or holds a number outside 0 to 1, start-up SHALL fail. The message SHALL name the key, the rule and the accepted backend names. It SHALL NOT hold a submitted value.

#### Scenario: Unknown backend name

- **WHEN** `OCR_LOCAL_CUTS={"tesseract": 0.9}` is set and no backend named `tesseract` is registered or discovered
- **THEN** start-up SHALL fail
- **AND** the message SHALL name every accepted backend

#### Scenario: Value out of range

- **WHEN** `OCR_LOCAL_CUTS={"pp-ocrv6-small": 1.2}` is set
- **THEN** start-up SHALL fail
- **AND** the message SHALL NOT contain `1.2`

### Requirement: The single cut override SHALL be retired

`ocr_local_min_confidence` SHALL NOT be a setting. When `OCR_LOCAL_MIN_CONFIDENCE` or `OCR__LOCAL_MIN_CONFIDENCE` is in the environment or `.env`, start-up SHALL fail with a message that names `OCR_LOCAL_CUTS` as the replacement.

#### Scenario: Old variable in the environment

- **WHEN** `OCR_LOCAL_MIN_CONFIDENCE=0.9` is set and the engine starts
- **THEN** start-up SHALL fail
- **AND** the message SHALL name `OCR_LOCAL_MIN_CONFIDENCE` and `OCR_LOCAL_CUTS`

#### Scenario: Nested spelling in .env

- **WHEN** `.env` holds `OCR__LOCAL_MIN_CONFIDENCE=0.9` and the engine starts
- **THEN** start-up SHALL fail
- **AND** the message SHALL name `OCR_LOCAL_CUTS`

## MODIFIED Requirements

### Requirement: The confidence cut SHALL belong to the backend

A backend SHALL register a default cut together with the name of the recorded experiment that fixed it, or no cut. A registration with a cut and no experiment name SHALL fail. The effective cut of a backend SHALL be its entry in `ocr_local_cuts` when there is one, else its default cut. No other setting SHALL change a cut. The default cut of `pp-ocrv6-small` SHALL be 0.92, from experiment `46a-local-ocr-per-backend-cuts-2026-11-06`.

#### Scenario: Default cut

- **GIVEN** the default list and an empty `ocr_local_cuts`
- **WHEN** the effective cut is resolved
- **THEN** it SHALL be 0.92

#### Scenario: Each backend keeps its own cut

- **GIVEN** `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small` and `OCR_LOCAL_CUTS={"pp-ocrv6-small": 0.7}`
- **WHEN** the effective cuts are resolved
- **THEN** the cut of `pp-ocrv6-small` SHALL be 0.7
- **AND** the cut of `indra` SHALL be 0.94

#### Scenario: Override replaces every cut

- **GIVEN** `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small` and `OCR_LOCAL_CUTS={"indra": 0.7, "pp-ocrv6-small": 0.7}`
- **WHEN** the effective cuts are resolved
- **THEN** both cuts SHALL be 0.7, because each backend has its own entry

#### Scenario: Cut without an experiment

- **WHEN** a backend is registered with a cut and no experiment name
- **THEN** the registration SHALL fail

#### Scenario: Unset value prints as unset

- **WHEN** `omrs config show` runs with no value for `ocr_local_cuts`
- **THEN** the output SHALL show an empty map and SHALL NOT print `null`

### Requirement: The local tier SHALL try the listed backends in order

The first listed backend SHALL read every page the local tier must read, in one call. A page with no escalation reason SHALL be kept. Every other page SHALL pass to the next backend in one call. A page that the last backend does not keep SHALL escalate to the OCR engine list with the last backend's reasons. No backend SHALL refuse a page because of its script.

#### Scenario: Second backend keeps a Latin page

- **GIVEN** `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small` and a scanned Latin page
- **WHEN** Indra returns Latin text at confidence 0.80 and PP-OCRv6 returns text at confidence 0.95
- **THEN** PP-OCRv6 SHALL keep the page
- **AND** the page producer SHALL be `pdf_inspector_ocr`

#### Scenario: Both backends escalate

- **GIVEN** `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small` and a scanned Bengali page
- **WHEN** Indra returns Bengali text at confidence 0.80 and PP-OCRv6 returns text at confidence 0.6
- **THEN** the page SHALL escalate to the OCR engine list with the reason `low_confidence`

#### Scenario: Default list behaves as before

- **GIVEN** the default list and an explicit cut of 0.9 for `pp-ocrv6-small`
- **WHEN** the golden fixture PDF is ingested under each rule combination
- **THEN** every page text and every metadata value SHALL equal the snapshot taken before this change

### Requirement: The local backend list SHALL participate in the source index identity

For every list, the default list included, the PDF `parser` block SHALL name each listed backend in order with its effective cut and its model identity once resolved. The OCR routing block that every source carries SHALL hold no local OCR cut and no local model identity. No block SHALL hold kept scripts or an output-script version. The identity SHALL depend on effective cuts only, so a cut change SHALL re-index PDF sources only.

#### Scenario: The upgrade re-indexes once

- **GIVEN** a collection indexed before this change
- **WHEN** an explicit ingest runs after the upgrade
- **THEN** every source SHALL be processed again once
- **AND** a second explicit ingest with no setting change SHALL process no source

#### Scenario: Default install keeps its digest

- **GIVEN** an install with the default list and no cut entries, after the upgrade
- **WHEN** two processes compute the identity of one source
- **THEN** the two digests SHALL be equal

#### Scenario: A new list re-indexes PDF sources

- **GIVEN** a collection indexed with the default list
- **WHEN** the list changes to `indra,pp-ocrv6-small` and an explicit ingest runs
- **THEN** PDF sources SHALL be processed again
- **AND** other sources SHALL keep their digest

#### Scenario: A cut change re-indexes PDF sources

- **GIVEN** a collection indexed with `OCR_LOCAL_BACKENDS=pp-ocrv6-small,indra` and no cut entries
- **WHEN** `OCR_LOCAL_CUTS={"indra": 0.96}` is set and an explicit ingest runs
- **THEN** PDF sources SHALL be processed again
- **AND** other sources SHALL keep their digest

#### Scenario: A default backend cut change leaves a Markdown source unchanged

- **GIVEN** a collection with one PDF source and one Markdown source, indexed with the default list and no cut entries
- **WHEN** `OCR_LOCAL_CUTS={"pp-ocrv6-small": 0.95}` is set and an explicit ingest runs
- **THEN** the PDF source SHALL be processed again
- **AND** the Markdown source SHALL keep its digest and SHALL NOT be processed

#### Scenario: A resolved local model enters the PDF identity only

- **GIVEN** OCR routing on and the default list
- **WHEN** the model identity of `pp-ocrv6-small` resolves
- **THEN** the PDF `parser` block SHALL hold it
- **AND** the digest of a Markdown source SHALL equal its digest with the model unresolved

#### Scenario: An explicit default cut keeps the digest

- **WHEN** `OCR_LOCAL_CUTS={"pp-ocrv6-small": 0.92}` is set with the default list
- **THEN** the digest SHALL equal the digest with an empty map

### Requirement: Indra OCR SHALL be an optional backend outside the default list

The system SHALL offer Indra OCR as the backend `indra` behind the optional extra `local-ocr-indra`. Its default cut SHALL be 0.94, from experiment `46a-local-ocr-per-backend-cuts-2026-11-06`. It SHALL use producer `indra_ocr` and name the model `datalab-to/indra-ocr@bd02167fdf2005a19962cc15188f8496a2c87d3b`. It SHALL read weights from `INDRA_OCR_MODEL_DIR` when that is set. It SHALL NOT be in the default list.

#### Scenario: Not in the default list

- **WHEN** no source sets `ocr_local_backends`
- **THEN** the list SHALL NOT contain `indra`

#### Scenario: Indra keeps a Latin page above its cut

- **GIVEN** `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small` and a scanned Latin page
- **WHEN** Indra returns 300 Latin letters at confidence 0.95
- **THEN** Indra SHALL keep the page
- **AND** the page producer SHALL be `indra_ocr`

#### Scenario: Indra passes on a page below its cut

- **GIVEN** `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small` and a scanned Arabic page
- **WHEN** Indra returns Arabic text at confidence 0.93
- **THEN** the page SHALL get the reason `low_confidence` from Indra
- **AND** the page SHALL pass to `pp-ocrv6-small`

## REMOVED Requirements

### Requirement: A backend SHALL declare the output scripts it may keep

**Reason**: The operator decided on 2026-11-06 that confidence alone decides for every backend. Indra was the only backend with a script filter. The re-analysis in `46a-local-ocr-per-backend-cuts-2026-11-06` shows that Indra at cut 0.94 keeps no bad page without the filter.

**Migration**: Remove `keeps_scripts` from any external backend descriptor. Set the backend's cut in `ocr_local_cuts` instead. The reason `script_not_kept` no longer appears in page diagnostics.

### Requirement: The output script SHALL be classified by a fixed, versioned rule

**Reason**: The output-script verdict served only the script filter, which this change removes. Nothing else reads it.

**Migration**: None for operators. The non-Latin detector and its version do not change. The identity loses the output-script version, and every source re-indexes once with the upgrade.
