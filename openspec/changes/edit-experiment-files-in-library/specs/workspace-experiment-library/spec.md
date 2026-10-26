## ADDED Requirements

### Requirement: The protocol and the report can be edited from the experiment page

The experiment page SHALL let a browser session with the `manage` scope edit `protocol.md`, `report.md`, and `results.md` when the folder has no `report.md`. The server SHALL refuse every other name before any file access. It SHALL save only a file that exists as a regular file directly in a listed experiment folder of an added project, is at most 1 MiB, is valid UTF-8 and holds no NUL character. The Plan tab SHALL offer no edit. A bearer credential SHALL NOT save.

#### Scenario: Edit a protocol

- **WHEN** the user selects Edit on the Protocol tab, changes the text and selects Save
- **THEN** `protocol.md` on disk holds the new text
- **AND** the tab shows the rendered Markdown again

#### Scenario: Report kept in results.md

- **WHEN** an experiment has `results.md` and no `report.md`
- **THEN** the Report tab offers Edit, and a save changes `results.md`

#### Scenario: results.md next to report.md

- **WHEN** a client saves `results.md` in a folder that also has `report.md`
- **THEN** the server refuses the request and writes nothing

#### Scenario: Plan file

- **WHEN** a client saves `plan.json`
- **THEN** the server refuses the request and writes nothing

#### Scenario: Missing protocol

- **WHEN** a client saves `protocol.md` in a folder without `protocol.md`
- **THEN** the server refuses the request and creates no file

#### Scenario: Link swapped in

- **WHEN** `report.md` is a link to a file elsewhere
- **THEN** the read says the file is not editable
- **AND** a save is refused and no file outside the folder changes

#### Scenario: Notebook credential

- **WHEN** a bearer credential sends a save
- **THEN** the server answers 403 and writes nothing

### Requirement: A save carries the revision it was based on

The file read SHALL return the SHA-256 revision of the file, whether the app can edit it, and its last logged edit. A save SHALL carry the revision that the editor loaded. When the file on disk has another revision, the server SHALL answer 409 with the reason `changed_on_disk` and SHALL write nothing. A save whose text equals the file SHALL write nothing and SHALL say that nothing changed.

#### Scenario: File changed in a terminal

- **WHEN** the user opens the editor, the file then changes on disk, and the user selects Save
- **THEN** the server answers 409 with the reason `changed_on_disk`
- **AND** the file keeps the terminal change
- **AND** the editor keeps the user's text and offers Reload

#### Scenario: Unchanged text

- **WHEN** the user saves text equal to the file
- **THEN** the answer says nothing changed
- **AND** no file and no edit log changes

#### Scenario: Cut file

- **WHEN** a file is larger than 1 MiB
- **THEN** the read returns no revision and says the file is not editable

### Requirement: A save replaces the file in one step

The server SHALL write the new text to a temporary file in the same folder and then rename it over the file, so a reader sees the old or the new text and never part of it. It SHALL keep CRLF line endings when the old file uses CRLF for every line break, and SHALL keep a leading UTF-8 byte order mark. It SHALL refuse text over 1 MiB or with a NUL character. The app SHALL NOT run git, stage or commit.

#### Scenario: CRLF file

- **WHEN** the old file uses CRLF line endings and the editor sends LF text
- **THEN** the saved file uses CRLF line endings

#### Scenario: Write fails

- **WHEN** the rename fails
- **THEN** the file keeps its old text and no temporary file is left

#### Scenario: Too large

- **WHEN** a save sends more than 1 MiB of text
- **THEN** the server answers 400 and writes nothing

### Requirement: Each save from the app is logged and shown

Each save that changes a file SHALL append one edit record to `edits.jsonl` in the experiment folder after the file is replaced. When the append fails, the server SHALL restore the old text and answer with an error that says the file was not saved. When the restore also fails, the server SHALL answer with an error that says the file was saved but the edit was not recorded. The tab SHALL show "Last edited" with the date and time of the last logged edit of its file. `experiment.json` SHALL NOT change.

#### Scenario: Last edited line

- **WHEN** the user saves `report.md`
- **THEN** `edits.jsonl` gains one line for `report.md`
- **AND** the Report tab shows "Last edited" with the time of that save

#### Scenario: Log cannot be written

- **WHEN** the edit log append fails after the file was replaced
- **THEN** the file holds its old text again
- **AND** the page says the file was not saved

#### Scenario: Log and restore both fail

- **WHEN** the edit log append fails after the file was replaced
- **AND** the old text cannot be put back
- **THEN** the file keeps the new text and `edits.jsonl` has no line for the save
- **AND** the page says the file was saved but the edit was not recorded in `edits.jsonl`

#### Scenario: Log is a link

- **WHEN** `edits.jsonl` is a link
- **THEN** the server answers 409 with the reason `edit_log_unusable` and writes nothing

### Requirement: The editor warns on a finished or converted experiment and guards unsaved text

In edit mode, the page SHALL show a warning when the experiment status is `PASS`, `FAIL`, `INCONCLUSIVE`, `MEASURED` or `SUPERSEDED`, or when the record is converted. The warning SHALL name the status, and SHALL say that git keeps the old text and that the app records the save. While the text has unsaved changes, Cancel, a tab switch and in-app navigation SHALL ask before they discard it, and a browser reload SHALL show the browser prompt.

#### Scenario: Finished experiment

- **WHEN** the user selects Edit on the Report tab of a `PASS` experiment
- **THEN** a warning names `PASS` and says that git keeps the old text and the app records the save

#### Scenario: Planned experiment

- **WHEN** the user selects Edit on a `PLANNED` experiment with no migration note
- **THEN** no warning is shown

#### Scenario: Switch tab with changes

- **WHEN** the user has unsaved changes and selects the Plan tab
- **THEN** a dialog asks whether to discard the changes
- **AND** Keep editing returns to the editor with the text kept
