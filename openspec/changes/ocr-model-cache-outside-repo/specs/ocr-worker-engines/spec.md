# Spec Delta

## ADDED Requirements

### Requirement: Model weights live outside the repository by default

An OCR engine SHALL keep its model weights in `~/.omrs/ocr-models/<engine>` unless `OMRS_OCR_MODEL_CACHE` is set and not blank. When it is set, the engine SHALL use `$OMRS_OCR_MODEL_CACHE/<engine>`. The default SHALL NOT depend on the engine folder or on the checkout.

#### Scenario: Default location

- **GIVEN** `OMRS_OCR_MODEL_CACHE` is unset and `HOME` is `/home/u`
- **WHEN** the engine `dots-mocr` resolves its model cache
- **THEN** the folder MUST be `/home/u/.omrs/ocr-models/dots-mocr`

#### Scenario: Variable set

- **GIVEN** `OMRS_OCR_MODEL_CACHE` is `/data/weights`
- **WHEN** the engine `paddleocr-vl` resolves its model cache
- **THEN** the folder MUST be `/data/weights/paddleocr-vl`

#### Scenario: Blank variable

- **GIVEN** `OMRS_OCR_MODEL_CACHE` holds only spaces
- **WHEN** an engine resolves its model cache
- **THEN** the default location MUST be used

### Requirement: The host and the worker resolve the same cache folder

The host, which checks the declared model files before it starts an engine, and the worker, which reads them, SHALL resolve the same folder for the same engine and the same environment.

#### Scenario: Both agree

- **WHEN** the host and the worker resolve the cache of engine `x`, with the variable unset, blank or set
- **THEN** both MUST return the same folder

### Requirement: The old in-folder cache is not read

OMRS SHALL NOT read model weights from `<engine folder>/.model-cache`. It SHALL look for them only in the folder that the previous requirements define.

#### Scenario: Weights left in the old folder

- **GIVEN** an engine has weights in `<engine folder>/.model-cache` and none in `~/.omrs/ocr-models/<engine>`
- **WHEN** the host checks the declared model files of the engine
- **THEN** it MUST look in `~/.omrs/ocr-models/<engine>`
- **AND** it MUST NOT use the files in `<engine folder>/.model-cache`

### Requirement: Tests never read the operator's weights

A test run SHALL NOT read, hash or write `~/.omrs/ocr-models`. Every test SHALL run with `OMRS_OCR_MODEL_CACHE` pointing at an empty temporary folder, except a test of the default itself, which sets `HOME` to a temporary folder.

#### Scenario: Isolation by default

- **WHEN** any test starts
- **THEN** `OMRS_OCR_MODEL_CACHE` MUST name an empty temporary folder
