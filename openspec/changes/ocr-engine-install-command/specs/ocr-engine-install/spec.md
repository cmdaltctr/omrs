# Spec Delta

## Purpose

Lets an operator who installed OMRS as a package, with no git checkout, install and update the OCR engines from the command line or from the app.

## ADDED Requirements

### Requirement: The package ships the OCR worker folders

The OMRS package SHALL contain the OCR worker core and, for each engine, its manifest, lockfile, source and licence notes. It SHALL NOT contain model weights, engine environments, smoke evidence or test scripts.

#### Scenario: The package holds the worker files

- **WHEN** the operator unpacks the built OMRS package
- **THEN** it MUST hold the worker core and, for `dots-mocr` and `paddleocr-vl`, the manifest, the lockfile, the source and the licence notes

#### Scenario: The package holds no weights or evidence

- **WHEN** the operator lists the files under the shipped worker folders
- **THEN** none of them SHALL be a model file, a virtual environment, a smoke evidence file or a test script

### Requirement: One command installs one engine

`omrs ocr install <engine>` SHALL install one named engine into the OCR workers folder without a git checkout. It SHALL copy the shipped files, build the engine environment from the engine's lockfile, and run the engine's fetch step when it ships one. It SHALL NOT change the OMRS main environment.

#### Scenario: Install on a package install

- **GIVEN** OMRS runs from a package with `uv` on the path and no `OCR_WORKERS_DIR`
- **WHEN** the operator runs `omrs ocr install paddleocr-vl`
- **THEN** the folder `~/.omrs/ocr-workers/engines/paddleocr-vl` MUST hold a working engine environment
- **AND** the OMRS main environment MUST be unchanged

#### Scenario: Unknown engine

- **WHEN** the operator runs `omrs ocr install nonesuch`
- **THEN** the command MUST stop before it copies or installs anything
- **AND** it MUST name the engines the package ships

#### Scenario: uv is missing

- **GIVEN** `uv` is not on the path
- **WHEN** the operator runs `omrs ocr install dots-mocr --accept-model-licence`
- **THEN** the command MUST stop with the reason `uv-missing` before it copies anything

### Requirement: The command never writes the settings file

The command SHALL NOT write `omrs.jsonc`. When the folder it installed into differs from the `ocr_workers_dir` setting in force, it SHALL print the value to set.

#### Scenario: The command prints the setting

- **GIVEN** `ocr_workers_dir` is empty
- **WHEN** the install finishes
- **THEN** the command MUST print `ocr_workers_dir` with the installed folder
- **AND** `omrs.jsonc` MUST be unchanged

### Requirement: An engine with extra licence terms needs acceptance at every entry point

An engine whose manifest requires licence acceptance SHALL NOT install until the operator accepts, with `--accept-model-licence` on the command or the accept field in the request. A refusal SHALL name the licence file and SHALL happen before any file is copied.

#### Scenario: Command refused

- **WHEN** the operator runs `omrs ocr install dots-mocr` without the flag
- **THEN** the command MUST stop with the reason `licence-not-accepted`
- **AND** the message MUST name the licence file and the flag

#### Scenario: Request refused

- **WHEN** a request to install `dots-mocr` does not accept the licence
- **THEN** the server MUST refuse it with the reason `licence-not-accepted`
- **AND** no job MUST start

### Requirement: The engine is built in its final folder

The install target SHALL be the `--workers-dir` value, else the `ocr_workers_dir` setting in force, else `~/.omrs/ocr-workers`. The engine environment SHALL be built in that folder, because an environment holds absolute paths and cannot be moved.

#### Scenario: Default folder

- **GIVEN** no `--workers-dir` and an empty `ocr_workers_dir`
- **WHEN** the operator installs an engine
- **THEN** the target MUST be `~/.omrs/ocr-workers`

#### Scenario: Configured folder

- **GIVEN** `ocr_workers_dir` names an existing folder that holds `engines/`
- **WHEN** the operator installs an engine without `--workers-dir`
- **THEN** the target MUST be that folder

### Requirement: A source checkout is never overwritten

When the target is the `ocr-workers/` folder of an OMRS source checkout, the install SHALL build the engine environment in place and SHALL NOT copy shipped files over it.

#### Scenario: Developer checkout

- **GIVEN** `ocr_workers_dir` names the `ocr-workers/` folder of a checkout with local edits to an engine
- **WHEN** the operator installs that engine
- **THEN** the engine environment MUST be built in that folder
- **AND** every tracked file in it MUST be unchanged

### Requirement: Running the install again is safe

A second run SHALL refresh the shipped files and SHALL keep the engine environment and the model cache when the lockfile did not change. It SHALL NOT delete a file that it did not write.

#### Scenario: Unchanged lockfile

- **GIVEN** an engine is installed and its lockfile is unchanged
- **WHEN** the operator runs the install again
- **THEN** the engine environment MUST NOT be rebuilt
- **AND** the files in the model cache MUST be unchanged

#### Scenario: A folder built by hand

- **GIVEN** `~/.omrs/ocr-workers` was built by hand from the same files
- **WHEN** the operator installs an engine into it
- **THEN** the engine MUST keep working
- **AND** no file that the install did not write MUST be removed

### Requirement: The server runs the install as one guarded job

The server SHALL run the install as one background job, one at a time, behind the `manage` scope. The job SHALL start its commands as argument lists with no shell, SHALL give them no `*_API_KEY` variable, and SHALL redact their output. The request text SHALL NOT reach a command line.

#### Scenario: A second install while one runs

- **GIVEN** an install job is running
- **WHEN** another install request arrives
- **THEN** the server MUST refuse it with the reason `busy`

#### Scenario: Output is redacted

- **WHEN** a command in the job prints a line with an API key value
- **THEN** the status MUST show the line with the value removed

### Requirement: The job saves the workers folder when it succeeds

When the job finishes and the `ocr_workers_dir` setting differs from the installed folder, the job SHALL save the folder through the settings write route and SHALL report that the folder applies at the next launch. A failed job SHALL NOT change the setting.

#### Scenario: Success sets the folder

- **GIVEN** `ocr_workers_dir` is empty
- **WHEN** the job installs an engine into `~/.omrs/ocr-workers` and succeeds
- **THEN** `omrs.jsonc` MUST hold `ocr_workers_dir` with that folder
- **AND** the status MUST say that the folder applies at the next launch

#### Scenario: Failure leaves the setting alone

- **WHEN** the job fails in the fetch step
- **THEN** `omrs.jsonc` MUST be unchanged

### Requirement: Install progress and failure can be read

The status of the job SHALL name the current step (`copy`, `environment`, `fetch`) and the last redacted output lines. A failure SHALL carry a fixed reason: `unknown-engine`, `uv-missing`, `licence-not-accepted`, `busy`, `copy-failed`, `environment-failed`, `fetch-failed` or `timeout`.

#### Scenario: Reading the step

- **WHEN** the job is building the engine environment
- **THEN** a status read MUST show the step `environment`

#### Scenario: Fetch failure

- **WHEN** the fetch step fails
- **THEN** the status MUST show the reason `fetch-failed` and the last redacted output lines

### Requirement: A not-provisioned reason names the working command

When an engine is not provisioned, its reason SHALL name `omrs ocr install <engine>`. It SHALL NOT name a script path that exists only in a source checkout.

#### Scenario: Package install

- **GIVEN** OMRS runs from a package and `paddleocr-vl` is not installed
- **WHEN** the operator reads the engine status
- **THEN** the reason MUST name `omrs ocr install paddleocr-vl`
