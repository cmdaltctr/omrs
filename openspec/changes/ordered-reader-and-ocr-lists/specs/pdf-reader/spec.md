## MODIFIED Requirements

### Requirement: PDF reader SHALL be selectable via environment variable

The system SHALL read the PDF reader setting at config-load time into a frozen ordered list of reader names, `Settings.pdf_readers`. The list SHALL come from `pdf_readers` (env `PDF_READERS`, comma-separated) or, when no source sets it, from the single value `pdf_reader` (env `PDF_READER`). Accepted single values SHALL stay `auto`, `pdf_inspector`, `liteparse`, `pypdfium2` and `pypdf`. An unknown single value SHALL log a warning naming it and fall back to `auto`. An unknown name in a list SHALL log a warning naming it and SHALL be dropped from the list.

#### Scenario: Explicit pdf-inspector selection via env var

- **WHEN** `PDF_READER=pdf_inspector` is set, `PDF_READERS` is not set and the package is importable
- **THEN** the injected `EffectiveSettings.pdf_readers` SHALL equal `("pdf_inspector", "liteparse", "pypdf")`
- **AND** pdf-inspector SHALL read every `.pdf` file

#### Scenario: Explicit override selection via env var

- **WHEN** `PDF_READER=liteparse` is set, `PDF_READERS` is not set and `liteparse` is importable
- **THEN** the injected `EffectiveSettings.pdf_readers` SHALL equal `("liteparse",)`
- **AND** the LiteParse adapter SHALL be used for all `.pdf` ingestion

#### Scenario: Unknown value falls back to auto with warning

- **WHEN** `PDF_READER=fastparser` is set
- **THEN** the system SHALL log a warning naming the offending value and the fallback
- **AND** it SHALL resolve as if `PDF_READER=auto` had been set

#### Scenario: Explicit list via the env var

- **WHEN** `PDF_READERS=pdf_inspector,pypdfium2` is set
- **THEN** the injected `EffectiveSettings.pdf_readers` SHALL equal `("pdf_inspector", "pypdfium2")`

### Requirement: pdf-inspector silent-empty extraction SHALL recover via a plain-text retry

When the pdf-inspector reader classifies a PDF as `text_based` while its own Markdown extraction is empty and its page count is greater than zero, the adapter SHALL retry the file with the readers that follow `pdf_inspector` in the injected reader list, in list order. Each retry SHALL run in extraction-only mode (OCR disabled regardless of operator settings) and SHALL keep one document per recovered page, so a readable text layer is not silently discarded. With the default list the tiers SHALL be `liteparse`, then `pypdf`.

#### Scenario: Normal extraction is untouched

- **GIVEN** pdf-inspector returns non-empty Markdown for a `text_based` PDF
- **WHEN** the adapter emits its documents
- **THEN** no retry SHALL occur
- **AND** the metadata SHALL carry no fallback diagnostics

#### Scenario: Scanned classifications are untouched

- **GIVEN** pdf-inspector classifies a PDF as `scanned`, `image_based` or another non-`text_based` type
- **WHEN** the adapter emits its documents
- **THEN** no retry SHALL occur regardless of extraction emptiness
- **AND** the OCR routing decision SHALL be unchanged

#### Scenario: Recovered pages keep their numbers

- **GIVEN** the first retry tier recovers text for pages 1 and 3 of a 3-page PDF
- **WHEN** the adapter emits its documents
- **THEN** it SHALL emit 2 documents with `page` 1 and 3 and `page_label` `"1"` and `"3"`
- **AND** each SHALL carry the pdf-inspector evidence and the fallback diagnostics

#### Scenario: A custom list sets the tiers

- **GIVEN** the reader list `pdf_inspector, pypdfium2`
- **WHEN** the contradiction triggers a retry
- **THEN** pypdfium2 SHALL be the only retry tier
- **AND** neither LiteParse nor pypdf SHALL run

#### Scenario: A list of one reader has no tiers

- **GIVEN** the reader list `pdf_inspector`
- **WHEN** the contradiction triggers
- **THEN** no retry SHALL run
- **AND** the original pdf-inspector result and flagged count SHALL be emitted unchanged

### Requirement: The rescue retry needs no default settings and falls back to pypdf

A retry tier SHALL receive concrete OCR and worker settings, so it does not need default effective settings. A tier that is not installed, raises, or yields no text SHALL hand over to the next tier. The last tier's exception SHALL propagate to the per-file error boundary. When the adapter is built directly without a reader list, its tiers SHALL be `liteparse`, then `pypdf`. Tier pages SHALL be numbered by position, from 1.

#### Scenario: Bare direct adapter use stays on liteparse

- **GIVEN** no default effective settings are installed and the adapter is built without a reader list
- **WHEN** the contradiction triggers and LiteParse can recover text
- **THEN** the LiteParse tier SHALL run with OCR disabled and automatic worker selection
- **AND** pypdf SHALL NOT be selected

#### Scenario: liteparse unavailable falls through to pypdf

- **GIVEN** the default list and the contradiction triggers
- **AND** LiteParse is not installed, raises, or yields no text
- **WHEN** the adapter emits its documents
- **THEN** the retry SHALL proceed with pypdf
- **AND** the diagnostic SHALL name pypdf as the fallback backend when it produces text

#### Scenario: pypdf pages are numbered by position

- **GIVEN** the pypdf tier returns one document per page, in page order
- **WHEN** the adapter emits the recovered documents
- **THEN** `page` SHALL be the 1-based position of the page in the file
- **AND** `page_label` SHALL be that number as a string, not the PDF's own page label

### Requirement: OCR dispatch uses the primary route before the fallback route

Every dispatch SHALL use the first engine of the injected OCR engine list (dots.mocr by default). A later engine SHALL serve the request only when every engine before it is unavailable before dispatch (PaddleOCR-VL is second by default).

#### Scenario: OCR required but the worker is unavailable

- **GIVEN** `pdf-inspector` reports that OCR is required
- **AND** every engine in the list is absent, unprovisioned, incompatible, or unusable before dispatch
- **WHEN** the PDF is ingested
- **THEN** the system SHALL retain the available `pdf-inspector` Markdown rather than fabricate missing content
- **AND** the document/file result SHALL report that OCR was required but unavailable
- **AND** ingestion SHALL remain within the existing per-file degradation boundary

## ADDED Requirements

### Requirement: The first installed reader in the list reads the file

The composition root SHALL pick the first installed reader of `pdf_readers` as the primary reader, once at start-up. When no listed reader is installed, it SHALL log an error and use `pypdf`, as a single uninstalled reader does today. `auto` SHALL be accepted only as a single value and SHALL keep its LiteParse, pypdfium2, pypdf probe with no retry tiers.

#### Scenario: A missing first reader is skipped

- **GIVEN** the list `pypdfium2, pypdf` and pypdfium2 is not installed
- **WHEN** the server starts
- **THEN** pypdf SHALL be the primary reader
- **AND** the start-up log SHALL name pypdfium2 as not installed

#### Scenario: auto in a list is refused

- **WHEN** a list holds `auto`
- **THEN** the warning SHALL say that `auto` is a single-value policy
- **AND** `auto` SHALL be dropped from the list

### Requirement: A single reader value expands to its documented list

A single `pdf_reader` value SHALL expand as follows: `pdf_inspector` to `pdf_inspector, liteparse, pypdf`; any other concrete reader to a list of that reader alone; `auto` to its probe. The packaged default list SHALL be `pdf_inspector, liteparse, pypdf`.

#### Scenario: Default configuration behaves as before

- **GIVEN** no source sets `pdf_readers` or `pdf_reader`
- **WHEN** a `text_based` PDF with an empty pdf-inspector extraction is ingested
- **THEN** the retry SHALL try LiteParse, then pypdf, exactly as ADR-066 describes

### Requirement: The reader list enters the index identity only when it differs from the expansion

The source index identity SHALL keep its current `parser.pdf_reader` value when the resolved list equals the expansion of a single value. Only a list that differs from every single-value expansion SHALL add the full list to the identity.

#### Scenario: Old key and equal list hash the same

- **GIVEN** one install with `pdf_reader=pdf_inspector` and one with `pdf_readers=pdf_inspector,liteparse,pypdf`
- **WHEN** both compute a PDF source identity
- **THEN** the two digests SHALL be equal to the digest before this change

#### Scenario: A different list reindexes PDF sources only

- **GIVEN** an indexed collection and the list changes to `pdf_inspector, pypdfium2`
- **WHEN** the next explicit ingest runs
- **THEN** PDF sources SHALL be processed again
- **AND** Markdown, code and other sources SHALL keep their digest
