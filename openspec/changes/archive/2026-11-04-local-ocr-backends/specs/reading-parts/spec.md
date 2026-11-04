## Purpose

Make each part of page reading (PDF readers, local OCR backends and page rules) replaceable and diagnosable on its own, through one pure-data descriptor per part, one shared registry helper, and discovery of parts from installed packages.

## ADDED Requirements

### Requirement: Each reading part SHALL have one pure-data descriptor

Every built-in PDF reader, local OCR backend and page rule SHALL have a descriptor in `core/reading_parts.py`. A descriptor SHALL hold the name, kind, import path, extra and probe module, the settings and options the part reads with their defaults, its index-identity contribution, its health facts, its UI label and help key, and its version. The module SHALL import nothing from `omrs`. Names SHALL be unique within a kind, and page rule orders SHALL be unique.

#### Scenario: Descriptor module stays pure

- **WHEN** the import check reads `core/reading_parts.py`
- **THEN** it SHALL find no import of an `omrs` module

#### Scenario: Duplicate name

- **WHEN** two descriptors of one kind share a name
- **THEN** loading the table SHALL fail with a message naming the duplicate

### Requirement: Descriptors and integration registrations SHALL agree

Integration code SHALL register each built-in part with one lazy `register()` line that names the part, its import path and the facts integration code reads at call time. A test SHALL fail when a descriptor has no registration, a registration has no descriptor, or a shared fact differs between the two.

#### Scenario: Missing registration

- **GIVEN** a descriptor for backend `fake` and no `register()` line for it
- **WHEN** the pin test runs
- **THEN** it SHALL fail and name `fake`

#### Scenario: Different cut

- **GIVEN** a descriptor cut of 0.9 and a registered cut of 0.8 for one backend
- **WHEN** the pin test runs
- **THEN** it SHALL fail and name the backend and the field

### Requirement: Page-reading registries SHALL share one registry helper

The PDF reader, local OCR backend and page rule registries SHALL use one helper that offers registration, description, names, lazy loading with a cache, an installed check that imports nothing, and a per-process switch-off with a reason. The helper SHALL import no part at module level. The public functions of the PDF reader registry SHALL keep their names and behaviour.

#### Scenario: Installed check imports nothing

- **WHEN** the installed check runs for a registered part
- **THEN** the part's module SHALL NOT be in `sys.modules` afterwards

#### Scenario: Switched off

- **GIVEN** a part switched off with the reason `PanicException: lock poisoned`
- **WHEN** health is read
- **THEN** the part SHALL show as switched off with that reason

### Requirement: Installed packages SHALL be able to add reading parts through entry points

The system SHALL discover reading parts from the entry-point groups `omrs.pdf_readers`, `omrs.local_ocr_backends` and `omrs.page_rules` with `importlib.metadata.entry_points`. An entry point SHALL name a descriptor. Discovery SHALL run once per process, in the composition root, before settings are resolved, and SHALL NOT run when `omrs.config` is imported. Discovery SHALL load the descriptor only; the part's implementation SHALL load on first use.

#### Scenario: Discovered backend can be listed

- **GIVEN** an installed distribution that declares backend `fake-ocr` in `omrs.local_ocr_backends`
- **WHEN** `OCR_LOCAL_BACKENDS=fake-ocr,pp-ocrv6-small` is set and the engine starts
- **THEN** start-up SHALL succeed and the local tier SHALL try `fake-ocr` first

#### Scenario: Importing config discovers nothing

- **WHEN** `omrs.config` is imported and settings are read without the composition root
- **THEN** no entry-point group SHALL be read

#### Scenario: Nothing discovered

- **GIVEN** no distribution declares a reading part
- **WHEN** the engine starts
- **THEN** the accepted names and every start-up message SHALL equal those before this change

### Requirement: A bad external part SHALL never stop start-up

A discovered descriptor whose name clashes with a built-in part, or whose type does not match its group, SHALL be refused with one warning. A discovered part that fails to load SHALL be skipped with one warning and shown as broken with the reason. A discovered page rule that raises while reading a file SHALL be skipped for that file with one warning and marked broken.

#### Scenario: Name clash

- **GIVEN** a distribution that declares a PDF reader named `pypdf`
- **WHEN** the engine starts
- **THEN** start-up SHALL succeed, the built-in `pypdf` SHALL stay in use
- **AND** one warning SHALL name the distribution and the clash

#### Scenario: Import failure

- **GIVEN** a distribution whose entry point module raises `ImportError`
- **WHEN** the engine starts
- **THEN** start-up SHALL succeed
- **AND** health SHALL list the part as broken with the error

### Requirement: A discovered part SHALL act only when the operator names it

A discovered PDF reader or local OCR backend SHALL be used only when a list setting names it. A discovered page rule SHALL be off until its `enabled` option is `true`.

#### Scenario: Discovered rule is off by default

- **GIVEN** a discovered page rule `stamp-check` and no options for it
- **WHEN** a PDF is ingested
- **THEN** the rule SHALL NOT run
- **AND** the source digest SHALL equal the digest without the distribution

### Requirement: Parts without flat settings SHALL read their options from one map

Built-in parts SHALL keep their flat setting keys. A part with no flat key SHALL read its options from `reading_part_options`, a map keyed by part name. The system SHALL validate each entry against the part's descriptor and SHALL refuse an unknown part or key at start-up. Options the descriptor marks as identity options SHALL enter the source index identity. An empty map SHALL add nothing to the identity.

#### Scenario: Unknown option

- **WHEN** `reading_part_options` holds `{"stamp-check": {"colour": "red"}}` and the descriptor declares no `colour`
- **THEN** start-up SHALL fail and the message SHALL name the part and the key

#### Scenario: Empty map keeps the digest

- **WHEN** `reading_part_options` is empty
- **THEN** every source digest SHALL equal the digest before this change

### Requirement: Health SHALL show each reading part on its own

The health report and the Integrations page SHALL show, from descriptors and registries: each listed local OCR backend in order with installed, model present, switched off and why, and its effective cut; each page rule with on or off, version and source; and each discovered part with its distribution and version, or broken with the reason.

#### Scenario: Backend switched off at run time

- **GIVEN** the default list and a pdf-inspector panic during ingest
- **WHEN** health is read
- **THEN** the `pp-ocrv6-small` entry SHALL show switched off with the panic message

#### Scenario: Rule status

- **GIVEN** maths routing on and non-Latin routing `off`
- **WHEN** health is read
- **THEN** `maths` SHALL show on with its detector version and `non_latin` SHALL show off

### Requirement: Hand-typed key lists SHALL derive from descriptors or be pinned to them

Python key lists that name reading parts or their settings SHALL be derived from descriptors where import contracts allow. Each copy that cannot import them (the HTTP contract enums and the web key lists) SHALL have a test that fails when it differs from the descriptors. A derived list SHALL equal the literal list it replaces.

#### Scenario: Web list drifts

- **WHEN** a key is removed from `web/src/api/settingsDocumentReading.ts`
- **THEN** the drift test SHALL fail and name the key

### Requirement: OCR runtimes SHALL follow the OCR engine list

The runtimes list SHALL include a runtime for every engine in `ocr_engines` that declares one, and `used_by` SHALL come from `ocr_engines`. `ocr_engine_primary` and `ocr_engine_fallback` SHALL stay readable as input aliases.

#### Scenario: Third engine runtime

- **GIVEN** three engines in `ocr_engines` and a `llama-server` runtime on the third
- **WHEN** `GET /v1/runtimes` is called
- **THEN** the response SHALL include the third engine's runtime

#### Scenario: Alias still read

- **WHEN** only `OCR_ENGINE_PRIMARY=paddleocr-vl` is set
- **THEN** `ocr_engines` SHALL resolve as before this change
