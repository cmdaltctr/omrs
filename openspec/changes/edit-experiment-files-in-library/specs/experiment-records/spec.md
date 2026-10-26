## ADDED Requirements

### Requirement: Edits from the app are logged in an edit log

The edit log `edits.jsonl` in an experiment folder SHALL be an append-only file that git tracks. Each line SHALL declare `omrs-edit-record/1` and hold the file name, the UTC time of the save, the SHA-256 and size of the file before and after, the record status at the time, whether the record is converted, and the tool. A line SHALL reject keys that the format does not define, and SHALL hold no user name, login or folder path. Writers SHALL only append. Readers SHALL refuse a line with an unknown format version and name the version.

#### Scenario: First edit

- **WHEN** the app saves `protocol.md` in a folder without `edits.jsonl`
- **THEN** `edits.jsonl` exists with one line for `protocol.md`
- **AND** its `after_sha256` equals the SHA-256 of the saved file

#### Scenario: Second edit

- **WHEN** the app saves a file in a folder whose `edits.jsonl` has one line
- **THEN** the file has two lines and the first line is unchanged

#### Scenario: Unknown key

- **WHEN** a line in `edits.jsonl` holds a key that format version 1 does not define
- **THEN** reading that line fails with a message that names the key

#### Scenario: Record file unchanged

- **WHEN** the app logs an edit
- **THEN** `experiment.json` in that folder is byte-identical to before

## MODIFIED Requirements

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
- a reserved number that now has a folder (information);
- an `edits.jsonl` line that does not load, or an `edits.jsonl` that is a link or not a regular file (warning).

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

#### Scenario: Broken edit log line

- **WHEN** line 3 of an experiment's `edits.jsonl` is not valid JSON
- **THEN** the checker reports the warning `edit-log-invalid` that names line 3

### Requirement: The experiments folder guide stands alone

`experiments/AGENTS.md` SHALL state the rules for experiment folders in the repository, including the record file, the seven status values, naming, reserved numbers, run records, the edit log and the commands to check and index. It SHALL state that a finished or converted experiment changes only `experiment.json`, `protocol.md` and its report file (`report.md`, or `results.md` in a folder without `report.md`), that the web app appends a line to `edits.jsonl` for each save and no tool changes an earlier line, and that a tool may add only the git-ignored derived files `analysis.ipynb`, `analysis.marimo.py` and `__marimo__/` to it. It SHALL NOT link to files outside the repository. `experiments/CLAUDE.md` SHALL be a link to it.

#### Scenario: Guide links stay inside the repository

- **WHEN** the links in `experiments/AGENTS.md` are resolved
- **THEN** each one points to a path inside the repository

#### Scenario: Derived notebook files are ignored by git

- **WHEN** `git check-ignore` runs in this repository for `analysis.marimo.py` and `__marimo__/session/x.json` inside an experiment folder
- **THEN** git reports both paths as ignored

#### Scenario: Edit log is tracked by git

- **WHEN** `git check-ignore` runs in this repository for `edits.jsonl` inside an experiment folder
- **THEN** git reports the path as not ignored
