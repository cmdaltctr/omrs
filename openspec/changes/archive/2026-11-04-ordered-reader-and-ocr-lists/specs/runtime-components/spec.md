## MODIFIED Requirements

### Requirement: OCR engine items follow the route rules

The OCR engine list SHALL hold every valid folder under `<ocr_workers_dir>/engines/`, the engines in force and the local OCR tier. An engine SHALL be `ready` only when the parsing route resolver finds its interpreter. Without a workers folder, a worker engine SHALL be `not-configured`. An engine folder without `.venv` SHALL be `missing`, with its provision command as the fix.

#### Scenario: Workers folder not set

- **WHEN** `ocr_workers_dir` is empty, `ocr_fallback_enabled` is true and `ocr_engines` starts with `dots-mocr`
- **THEN** the `dots-mocr` item MUST be `not-configured` and its `used_by` MUST hold `ocr_engines`

#### Scenario: Engine needs a licence

- **WHEN** the dots-mocr folder exists without `.venv`
- **THEN** the item MUST be `missing`
- **AND** its fix MUST be `python3 ocr-workers/provision.py dots-mocr --accept-model-licence`
- **AND** its reason MUST name `LICENCE-NOTES.md`

#### Scenario: Engine without a licence step

- **WHEN** the paddleocr-vl folder exists without `.venv`
- **THEN** the item MUST be `missing` with the fix `python3 ocr-workers/provision.py paddleocr-vl`

#### Scenario: Engine ready

- **WHEN** `<ocr_workers_dir>/engines/paddleocr-vl/.venv/bin/python` exists
- **THEN** the `paddleocr-vl` item MUST be `ready`

#### Scenario: Engine name without a folder

- **WHEN** `ocr_engines` names an engine that has no folder under `<ocr_workers_dir>/engines/`
- **THEN** the item MUST be `missing` with no fix command

#### Scenario: OCR fallback off

- **WHEN** `ocr_fallback_enabled` is false
- **THEN** every engine item MUST have an empty `used_by`
