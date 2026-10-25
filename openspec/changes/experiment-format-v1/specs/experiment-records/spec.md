# Spec Delta

## ADDED Requirements

### Requirement: Every experiment has a versioned record file

Each experiment folder SHALL contain an `experiment.json` record that declares the format `omrs-experiment/1`. The record SHALL hold the experiment number, title, date, category, size, status, the folder that supersedes it, a one-line finding, optional references to decision records, changes and tasks, and an optional migration note. The record SHALL reject keys that format version 1 does not define. The `omrs` package SHALL ship a JSON Schema for the record that matches the validation rules exactly.

The number SHALL be one or more digits, optionally followed by one lower-case letter or by a dot and digits (`22`, `5b`, `10.1`), or empty for an unnumbered experiment. The category SHALL be one of `retrieval`, `ingestion`, `runtime`, `generation`, `graph`, `review`. The size SHALL be one of `Quick`, `Standard`, `Confirmatory`. The finding SHALL be one line.

#### Scenario: Valid record

- **WHEN** an `experiment.json` declares `omrs-experiment/1` and has every required field with an allowed value
- **THEN** the record loads without error

#### Scenario: Unknown key

- **WHEN** an `experiment.json` contains a key that format version 1 does not define
- **THEN** loading fails with a message that names the key

#### Scenario: Newer format version

- **WHEN** an `experiment.json` declares a format version that this release does not know
- **THEN** loading fails with a message that names the version and says a newer `omrs` is needed

#### Scenario: Shipped schema matches the validator

- **WHEN** the shipped JSON Schema is compared with the schema generated from the record rules
- **THEN** the two are identical

### Requirement: Status has seven defined values

An experiment status SHALL be one of `PLANNED`, `ACTIVE`, `PASS`, `FAIL`, `INCONCLUSIVE`, `MEASURED`, `SUPERSEDED`. `MEASURED` SHALL mean a measurement with no pass or fail gate. A record with status `SUPERSEDED` SHALL name the superseding experiment folder. A record with any other status SHALL NOT name one.

#### Scenario: Superseded without a pointer

- **WHEN** a record has status `SUPERSEDED` and no superseding folder
- **THEN** loading fails with a message that asks for the superseding folder

#### Scenario: Pointer on a live experiment

- **WHEN** a record has status `PASS` and names a superseding folder
- **THEN** loading fails

### Requirement: Category and size may be empty only on converted records

A record SHALL have a category and a size, unless it carries a migration note. A migration note SHALL keep the original status text, the file it came from and the date of conversion. Together with the move report in the change folder, it lets each conversion be checked.

#### Scenario: New record without a category

- **WHEN** a record without a migration note has no category
- **THEN** loading fails

#### Scenario: Converted record without a size

- **WHEN** a record with a migration note has no size
- **THEN** the record loads
- **AND** the checker reports the missing size as information, not as an error

### Requirement: Experiment folders are detected by record or by name

Inside an experiments directory, a direct subfolder SHALL be an experiment folder when it contains `experiment.json`, or when its name matches `<number>-<slug>-<YYYY-MM-DD>`. Other subfolders SHALL be ignored. The folder name SHALL be the experiment identity. Detection SHALL list only the top level of each experiment's `output/` folder and SHALL NOT read the files inside it.

#### Scenario: Shared folders are ignored

- **WHEN** the experiments directory holds `_lib/`, `ARCHIVED/` and `example/`
- **THEN** none of them is reported as an experiment

#### Scenario: Two folders share a number

- **WHEN** two converted folders both use the number `19`
- **THEN** both are listed as separate experiments with their own folder names
- **AND** the checker reports the shared number as a warning

#### Scenario: Large output folder

- **WHEN** an experiment's `output/` folder holds many gigabytes in nested folders
- **THEN** a check reads only the names at the top level of `output/`

### Requirement: The checker reports problems without changing files

The checker SHALL read an experiments directory and report findings with a severity (`error`, `warning`, `info`), a stable code, the experiment folder and a plain message. It SHALL NOT write any file. It SHALL report at least these problems:

- a detected experiment folder without a valid `experiment.json` (error);
- a record number or date that differs from the folder name (error);
- a superseding folder that does not exist (error);
- a number used by more than one folder (error for records without a migration note, warning otherwise);
- a status line in `report.md` that differs from the record status (warning, or information for converted records);
- a run record whose plan SHA-256 differs from the current `plan.json` (warning);
- files missing for the declared size: `report.md` for Quick; `protocol.md`, `plan.json` and `report.md` for Standard and Confirmatory (warning, or information for converted records);
- an index table that differs from the generated table (error);
- a reserved number that now has a folder (information).

The CLI check SHALL exit with a non-zero code when any error is found, and also on warnings when strict mode is requested.

#### Scenario: Plan changed after a run

- **WHEN** `output/run-records.jsonl` records a plan SHA-256 and `plan.json` now has a different SHA-256
- **THEN** the checker reports a warning for that experiment

#### Scenario: Status in report disagrees

- **WHEN** a new record says `PASS` and the status line in its `report.md` says `FAIL`
- **THEN** the checker reports a warning that names both values

#### Scenario: Check leaves files unchanged

- **WHEN** the checker runs on an experiments directory
- **THEN** no file in that directory is created, changed or deleted

### Requirement: The index table is generated from the records

The index table in `EXP_README.md` SHALL be generated from the `experiment.json` files and placed between the lines `<!-- omrs:experiment-index:start -->` and `<!-- omrs:experiment-index:end -->`. Generation SHALL change only the lines between the markers. The table SHALL list every experiment with its number, a link to its folder, its date, its status and its finding, ordered by number and then by folder name, with unnumbered experiments last. After the experiment table, the block SHALL list the reserved numbers with their reason and reference, so that a planned experiment without a folder stays visible. Generation SHALL be deterministic. Writing SHALL refuse a file without both markers.

#### Scenario: Reserved number in the index

- **WHEN** `reserved.json` reserves number 35
- **THEN** the generated block lists 35 with its reason and reference below the experiment table

#### Scenario: Text outside the markers is kept

- **WHEN** the index is written to an `EXP_README.md` that has text before and after the markers
- **THEN** that text is byte-identical after the write

#### Scenario: File without markers

- **WHEN** the index is written to an `EXP_README.md` without the markers
- **THEN** the write is refused with a message that names the missing marker
- **AND** the file is unchanged

#### Scenario: A finding contains a pipe character

- **WHEN** a finding contains `|`
- **THEN** the generated row escapes it so the table keeps five columns

### Requirement: Reserved numbers are honoured

`experiments/reserved.json` SHALL list numbers that are reserved without a folder, each with a reason and a reference. The folder creator SHALL NOT use a reserved number.

#### Scenario: Next number skips a reservation

- **WHEN** the highest folder number is 42 and `43` is reserved
- **THEN** the next new experiment gets number `44`

### Requirement: New experiment folders are created from templates

The folder creator SHALL make a new folder named `<number>-<slug>-<YYYY-MM-DD>` with an `experiment.json` record at status `PLANNED` and the template files for the chosen size. The slug SHALL be lower-case letters, digits and single hyphens. The number SHALL be the lowest whole number above the highest folder number that is not reserved, unless a follow-up of an existing number is requested, which SHALL take the next free letter (`38a`, then `38b`). The creator SHALL NOT overwrite or change any existing file or folder, and SHALL refuse a folder name that already exists.

#### Scenario: Standard experiment

- **WHEN** a Standard experiment named `ocr-text-quality` in category `ingestion` is created on 2026-10-26 and the next free number is 43
- **THEN** the folder `43-ocr-text-quality-2026-10-26` exists
- **AND** it holds `experiment.json` with status `PLANNED`, `protocol.md`, `plan.json` and `report.md`

#### Scenario: Quick experiment

- **WHEN** a Quick experiment is created
- **THEN** the folder holds `experiment.json` and `report.md`
- **AND** its `experiment.json` is the only machine-readable plan it needs

#### Scenario: Follow-up experiment

- **WHEN** a follow-up of experiment 38 is created and `38a` does not exist
- **THEN** the new folder uses number `38a`

#### Scenario: Folder already exists

- **WHEN** the computed folder name already exists
- **THEN** creation is refused and nothing is written

### Requirement: Runs append a run record

An experiment run SHALL append one JSON line to `output/run-records.jsonl` when it starts. The line SHALL declare `omrs-run-record/1` and hold the start time in UTC, the git commit, whether the working tree had uncommitted changes, the SHA-256 of `plan.json` (empty when there is no plan) and the command. Earlier lines SHALL NOT be changed.

#### Scenario: Second run of the same experiment

- **WHEN** an experiment that already has one run record starts again
- **THEN** the file has two lines and the first line is unchanged

### Requirement: The experiments folder guide stands alone

`experiments/AGENTS.md` SHALL state the rules for experiment folders in the repository, including the record file, the seven status values, naming, reserved numbers, run records and the commands to check and index. It SHALL NOT link to files outside the repository. `experiments/CLAUDE.md` SHALL be a link to it.

#### Scenario: Guide links stay inside the repository

- **WHEN** the links in `experiments/AGENTS.md` are resolved
- **THEN** each one points to a path inside the repository

### Requirement: The repository skill templates match the package templates

The repository copy of the experiment skill SHALL carry template files that are byte-identical to the templates shipped in the `omrs` package. A test SHALL fail when they differ. The repository copy SHALL contain no personal names, home-folder paths or email addresses.

#### Scenario: Template drift

- **WHEN** the package protocol template changes and the skill copy does not
- **THEN** the drift test fails and names the file

#### Scenario: Personal path in the skill

- **WHEN** a file in the repository skill copy contains a home-folder path
- **THEN** a test fails and names the file
