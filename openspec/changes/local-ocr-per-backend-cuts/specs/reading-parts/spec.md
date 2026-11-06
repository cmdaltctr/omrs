## MODIFIED Requirements

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

#### Scenario: Descriptor with a removed field

- **GIVEN** a distribution whose local OCR backend descriptor passes `keeps_scripts`
- **WHEN** the engine starts
- **THEN** start-up SHALL succeed
- **AND** health SHALL list the backend as broken with the error

### Requirement: Health SHALL show each reading part on its own

The health report and the Integrations page SHALL show, from descriptors, registries and the injected settings: each listed local OCR backend in order with installed, model present, switched off and why, and its effective cut; each page rule with on or off, version and source; and each discovered part with its distribution and version, or broken with the reason. The effective cut SHALL be the backend's `ocr_local_cuts` entry, else its default cut.

#### Scenario: Backend switched off at run time

- **GIVEN** the default list and a pdf-inspector panic during ingest
- **WHEN** health is read
- **THEN** the `pp-ocrv6-small` entry SHALL show switched off with the panic message

#### Scenario: Rule status

- **GIVEN** maths routing on and non-Latin routing `off`
- **WHEN** health is read
- **THEN** `maths` SHALL show on with its detector version and `non_latin` SHALL show off

#### Scenario: Effective cuts of two backends

- **GIVEN** `OCR_LOCAL_BACKENDS=pp-ocrv6-small,indra` and `OCR_LOCAL_CUTS={"indra": 0.96}`
- **WHEN** health is read
- **THEN** the `pp-ocrv6-small` entry SHALL show cut 0.92
- **AND** the `indra` entry SHALL show cut 0.96
