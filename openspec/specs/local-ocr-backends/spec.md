# local-ocr-backends Specification

## Purpose
Let the local OCR tier read pages with an ordered list of local OCR backends. Each backend has its own calibrated default cut, which the operator can replace per backend with `ocr_local_cuts`. Confidence alone decides whether a backend keeps a page.

## Requirements

### Requirement: The local OCR backend list SHALL be injected configuration

The system SHALL read `ocr_local_backends` (env `OCR_LOCAL_BACKENDS`) from the injected settings as an ordered list of backend names, in the same forms as `ocr_engines`: a comma-separated environment value or a JSON array in `omrs.jsonc`. The default SHALL be `["pp-ocrv6-small"]`. An unknown name, or a backend without a calibrated cut, SHALL stop start-up with a message that names the accepted values.

#### Scenario: Default list

- **WHEN** no source sets the key
- **THEN** the list SHALL be `["pp-ocrv6-small"]`
- **AND** the local tier SHALL read pages with pdf-inspector exactly as before this change

#### Scenario: Unknown backend

- **WHEN** `OCR_LOCAL_BACKENDS=tesseract` is set and no backend named `tesseract` is registered or discovered
- **THEN** start-up SHALL fail
- **AND** the message SHALL name every accepted backend

#### Scenario: Backend without a calibrated cut

- **GIVEN** a backend registered with no cut
- **WHEN** `OCR_LOCAL_BACKENDS` names it
- **THEN** start-up SHALL fail and the message SHALL say that the backend has no calibrated cut

### Requirement: A local OCR backend SHALL return text and one confidence per page

A backend SHALL take a PDF path, 1-based page numbers and the injected settings. For each page it reads, it SHALL return the page number, the text, one page confidence from 0 to 1 or none, the model identity, and whether it recommends a hosted engine. A page the backend does not return SHALL count as missing. A backend SHALL NOT decide whether a page escalates.

#### Scenario: Backend returns two pages

- **WHEN** the local tier asks a backend for pages 2 and 5
- **THEN** the backend SHALL return one result for each page it read
- **AND** each result SHALL hold the text, the page confidence and the model identity

#### Scenario: Missing page

- **WHEN** a backend returns no result for a requested page
- **THEN** the shared rule SHALL give that page the reason `missing_page`

### Requirement: A line-based backend SHALL reduce line confidences to one page confidence by a fixed rule

A backend that reports confidence per line SHALL give the page confidence as the mean of its line confidences, weighted by the number of characters in each line. A different rule SHALL be adopted only after a recorded experiment supports it.

#### Scenario: Weighted mean

- **GIVEN** a page with two lines: 90 characters at confidence 0.95 and 10 characters at confidence 0.45
- **WHEN** the backend reduces the confidences
- **THEN** the page confidence SHALL be 0.90

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

### Requirement: A backend that cannot run SHALL be skipped

A listed backend that is not installed SHALL be skipped with one warning per process. A backend that raises a non-`Exception` panic SHALL be switched off for the rest of the process, and later files SHALL skip it. The local tier SHALL count as unavailable only when every listed backend is skipped or switched off.

#### Scenario: Backend not installed

- **GIVEN** `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small` and no Indra extra installed
- **WHEN** a PDF with flagged pages is ingested
- **THEN** PP-OCRv6 SHALL read the pages
- **AND** one warning SHALL name the missing backend

#### Scenario: Panic switches one backend off

- **GIVEN** `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small` and a pdf-inspector panic on the first file
- **WHEN** a second file is ingested
- **THEN** Indra SHALL still read the second file's pages
- **AND** PP-OCRv6 SHALL NOT be called

### Requirement: An unresolved page SHALL keep the text of the first backend that read it

When an escalated page is not resolved by the OCR engine list, it SHALL keep the text of the first listed backend that returned non-empty text for it, and that backend SHALL be named as its producer.

#### Scenario: No engine available

- **GIVEN** `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small`, no available OCR engine, and an Arabic page that Indra reads at confidence 0.80
- **WHEN** the PDF is ingested
- **THEN** the page SHALL keep Indra's text and count as unresolved
- **AND** its producer SHALL be `indra_ocr`

### Requirement: A kept page SHALL name the backend that kept it

Each backend SHALL declare a producer name. A page kept by a backend SHALL carry that producer. `ocr_backend` SHALL be `mixed` when more than one backend produced text. The producer of `pp-ocrv6-small` SHALL be `pdf_inspector_ocr`, as before this change.

#### Scenario: Two local backends in one document

- **GIVEN** a PDF where Indra keeps page 1 and PP-OCRv6 keeps page 2, and every other page is native
- **WHEN** the document is emitted
- **THEN** page 1 SHALL name `indra_ocr`, page 2 SHALL name `pdf_inspector_ocr`
- **AND** `ocr_backend` SHALL be `mixed`

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

### Requirement: Settings and the Read document step SHALL edit the backend list

Settings › Document reading SHALL show `ocr_local_backends` as an ordered list, edited like the PDF reader list. The Read document step SHALL accept `ocr_local_backends`. A saved graph without the key SHALL keep its fingerprint.

#### Scenario: Saved graph keeps its fingerprint

- **GIVEN** a graph saved before this change
- **WHEN** its fingerprint is computed after this change
- **THEN** the fingerprint SHALL be unchanged

#### Scenario: Unknown name in a step

- **WHEN** a Read document step sets `ocr_local_backends` to `["nope"]`
- **THEN** the step SHALL be refused with `invalid_parameter`

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

### Requirement: Adding Indra SHALL touch only its own part

Adding the Indra backend SHALL change no file under `src/omrs/` other than its own file, its `register()` line and its descriptor entry. A test SHALL enforce this.

#### Scenario: Indra is one part

- **WHEN** the one-file check runs
- **THEN** the word `indra` SHALL appear under `src/omrs/` only in the Indra backend file, its `register()` line and its descriptor entry

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
