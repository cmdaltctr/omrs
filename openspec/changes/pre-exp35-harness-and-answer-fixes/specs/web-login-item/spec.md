## ADDED Requirements

### Requirement: The login item keeps the local OCR variables

`install` SHALL carry `INDRA_OCR_MODEL_DIR`, `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` into the new plist. The value SHALL come from the installing process environment when set there, else from the plist being replaced. No other variable SHALL be carried. A variable set in neither place SHALL be left out. `install` SHALL print one line for each variable it carries, naming the variable and where the value came from, never a secret.

#### Scenario: Re-install keeps a hand-added variable

- **WHEN** the installed plist holds `INDRA_OCR_MODEL_DIR` and the installing shell does not set it
- **THEN** the new plist MUST hold the same `INDRA_OCR_MODEL_DIR` value, and `install` MUST say it kept the value from the old plist

#### Scenario: Shell value wins

- **WHEN** the installing shell sets `PDFIUM_LIB_PATH` to one path and the old plist holds another
- **THEN** the new plist MUST hold the shell's path

#### Scenario: Other variables are not carried

- **WHEN** the old plist holds `OPENROUTER_API_KEY`
- **THEN** the new plist MUST NOT hold it

#### Scenario: Nothing to carry

- **WHEN** neither the shell nor the old plist sets any of the three variables
- **THEN** the new plist MUST hold only `PATH` in its environment, as before
