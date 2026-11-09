## ADDED Requirements

### Requirement: The login item keeps the local OCR model folder

`install` SHALL carry `INDRA_OCR_MODEL_DIR` into the new plist. The value SHALL come from the installing process environment when set there, else from the plist being replaced. No other variable SHALL be carried, including `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH`. A variable set in neither place SHALL be left out. `install` SHALL print one line when it carries the variable, naming where the value came from.

#### Scenario: Re-install keeps a hand-added variable

- **WHEN** the installed plist holds `INDRA_OCR_MODEL_DIR` and the installing shell does not set it
- **THEN** the new plist MUST hold the same `INDRA_OCR_MODEL_DIR` value, and `install` MUST say it kept the value from the old plist

#### Scenario: Shell value wins

- **WHEN** the installing shell sets `INDRA_OCR_MODEL_DIR` to one path and the old plist holds another
- **THEN** the new plist MUST hold the shell's path

#### Scenario: Other variables are not carried

- **WHEN** the old plist holds `OPENROUTER_API_KEY`, `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH`
- **THEN** the new plist MUST hold none of them

#### Scenario: Nothing to carry

- **WHEN** neither the shell nor the old plist sets `INDRA_OCR_MODEL_DIR`
- **THEN** the new plist MUST hold only `PATH` in its environment, as before

### Requirement: The login item command files stay under the size ceiling

No file of the login item commands SHALL exceed 500 lines after the carried-variable lines are added.

#### Scenario: Split file

- **WHEN** the size-ceiling test runs
- **THEN** `web_login_item.py` and the file that takes its status helpers MUST each hold fewer than 500 lines
