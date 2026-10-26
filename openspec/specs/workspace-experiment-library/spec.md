# workspace-experiment-library Specification

## Purpose
The experiment library in the web workspace: projects added from the browser, a library of experiment cards with their checker findings, an experiment page that shows only top-level text files with a size limit, notebooks that group experiments from one or more projects, and creation of a new experiment folder from the library.

## Requirements

### Requirement: Experiment projects are added from the web workspace

The web workspace SHALL let a browser session with the `manage` scope add an experiment project by giving an absolute folder path and a name. The server SHALL accept the path only when it is an existing directory that contains an `experiments` directory inside it, and when no stored project has the same resolved path. The project list SHALL persist in the workspace database across restarts. Removing a project SHALL remove it from the list and from user notebooks, and SHALL NOT change any file on disk. A bearer credential SHALL NOT add or remove a project.

#### Scenario: Add a valid project

- **WHEN** the session adds `/work/omrs` and `/work/omrs/experiments` is a directory
- **THEN** the project is listed with its name, its path and its experiment count
- **AND** it is still listed after the server restarts

#### Scenario: Folder without experiments

- **WHEN** the session adds a folder that has no `experiments` directory
- **THEN** the request fails with a message that names the missing directory
- **AND** nothing is stored

#### Scenario: Experiments link that leaves the project

- **WHEN** the `experiments` entry is a link to a directory outside the project folder
- **THEN** the request fails and nothing is stored

#### Scenario: Project folder removed from disk

- **WHEN** a stored project's folder no longer exists
- **THEN** the project is listed as unavailable and its experiments are not listed

### Requirement: The library lists experiments with their checks

For a project, the workspace SHALL list every detected experiment with its folder name, number, title, date, category, size, status, superseded-by folder, finding and checker findings, and SHALL list the project's reserved numbers and project-level findings. The listing SHALL come from the experiment folders on each request. The library view SHALL filter by status and category, search number, title and finding, and offer "All projects".

#### Scenario: Converted experiments are listed

- **WHEN** the library opens a project whose experiments folder holds 50 records
- **THEN** 50 cards are shown with their status badges
- **AND** a card with checker warnings shows the warning count

#### Scenario: Filter by status

- **WHEN** the user selects the status `FAIL`
- **THEN** only experiments with status `FAIL` are shown

### Requirement: The experiment page shows its files safely

The experiment page SHALL show the record, the checker findings for that experiment, the top-level files of the folder and the top-level names in `output/`. It SHALL show the text of a top-level file whose suffix is `.md`, `.json`, `.jsonl`, `.txt`, `.csv`, `.yaml`, `.yml` or `.py`, and SHALL render Markdown without raw HTML. The server SHALL refuse a file name with a path separator, `..` or a leading dot, a file outside the experiment folder after links are resolved, and any other suffix. A file over 1 MiB SHALL return its first 1 MiB and say that it was cut. Other files, such as HTML review pages, SHALL be listed with their size as not viewable.

#### Scenario: Read a protocol

- **WHEN** the user opens the Protocol tab of an experiment that has `protocol.md`
- **THEN** the Markdown is rendered as text, headings and tables

#### Scenario: HTML review page

- **WHEN** the folder holds `review.html`
- **THEN** the file list shows `review.html` as not viewable
- **AND** the server refuses a request for its text

#### Scenario: Path escape

- **WHEN** a client asks for the file `../../secret.txt`
- **THEN** the server refuses the request and reads no file

#### Scenario: Older folder without a report

- **WHEN** an experiment has `results.md` and no `report.md`
- **THEN** the Report tab shows `results.md`

### Requirement: Notebooks group experiments

The workspace SHALL present every project as a notebook of its experiments. The user SHALL create, rename and delete user notebooks, and add and remove experiments from any project in a user notebook. User notebooks and their entries SHALL persist in the workspace database. An entry whose folder is no longer detected SHALL be shown as missing with a remove action and SHALL NOT be removed on its own. Deleting a notebook SHALL NOT change any experiment file.

#### Scenario: Cross-project notebook

- **WHEN** the user creates the notebook `Paper 1` and adds one experiment from each of two projects
- **THEN** the notebook lists both experiments with their project names

#### Scenario: Missing entry

- **WHEN** an experiment folder in a user notebook is renamed on disk
- **THEN** the notebook shows that entry as missing
- **AND** the entry stays until the user removes it

#### Scenario: Duplicate notebook name

- **WHEN** the user creates a notebook with the name of an existing user notebook
- **THEN** the request fails and no notebook is created

### Requirement: A new experiment is created from the library

A browser session with the `manage` scope SHALL create an experiment in a project from a slug, a title, a category, a size and an optional follow-up number. The folder SHALL be created by the experiment record folder creator with today's date. When the project's `EXP_README.md` has both index markers, the index SHALL then be rewritten. The response SHALL name the new folder and say whether the index was written, the file had no markers, or there was no file. When the folder was created but `EXP_README.md` could not be read or written, or is not valid UTF-8, the request SHALL still succeed. The response SHALL then report the index as `failed` with a plain message that names `omrs experiments index --write`. A refusal SHALL write nothing.

#### Scenario: Create a Standard experiment

- **WHEN** the user creates a Standard experiment `ocr-text-quality` in category `ingestion`
- **THEN** a new folder with status `PLANNED` appears in the library
- **AND** the project's index lists it

#### Scenario: The index cannot be updated

- **WHEN** the user creates an experiment and the project's `EXP_README.md` is not valid UTF-8 or cannot be read or replaced
- **THEN** the request succeeds and the new folder exists
- **AND** the response reports the index as `failed` with a message that names `omrs experiments index --write`

#### Scenario: Folder exists

- **WHEN** the computed folder already exists
- **THEN** the request fails with the creator's message and no file changes

### Requirement: An experiment opens in marimo from its page

The experiment page SHALL offer an "Open in marimo" action. The server SHALL launch the editor only for a browser session with the `manage` scope and only when the request carries `consent: true`. A bearer credential SHALL NOT launch an editor. The project SHALL be an added Library project that is still available, and the folder SHALL be a listed experiment folder of that project. The request SHALL NOT name a file path, a flag or an argument. The editor SHALL bind to the loopback address, SHALL open in a separate browser tab, and SHALL return its access token once in the response body and never in a URL or a log.

#### Scenario: Open a converted experiment

- **WHEN** a session with the `manage` scope sends consent for a listed experiment and marimo is registered and launchable
- **THEN** an editor starts on a loopback port from 2719 to 2721
- **AND** the response holds the editor address without the token and the token once

#### Scenario: Consent is missing

- **WHEN** the request carries `consent: false`
- **THEN** the server refuses it with 403
- **AND** no file is read or written and no process starts

#### Scenario: Bearer credential

- **WHEN** a bearer credential sends the request
- **THEN** the server refuses it and no process starts

#### Scenario: Folder name with a path escape

- **WHEN** the folder in the address is `..` or holds a path separator
- **THEN** the server refuses it with a validation error and reads no file

#### Scenario: Unknown folder

- **WHEN** the folder is not a listed experiment of the project
- **THEN** the server returns 404 and no process starts

### Requirement: The Library notebook is a derived file in the experiment folder

The notebook SHALL be `analysis.marimo.py` directly inside the experiment folder, for every status. When it does not exist, the server SHALL make it from `analysis.py` through the registered editor's conversion recipe, or from a packaged empty notebook when the folder has no `analysis.py`. The server SHALL write the notebook with an exclusive create and SHALL NOT overwrite, rename or edit any existing file in the folder. An existing notebook SHALL be opened as it is. The response SHALL say whether the notebook was converted, created or already existed, and whether `analysis.py` is newer than the notebook.

#### Scenario: First open converts analysis.py

- **WHEN** a finished, converted experiment has `analysis.py` and no `analysis.marimo.py`
- **THEN** `analysis.marimo.py` exists after the open and the response says `converted`
- **AND** every file that existed in the folder before the open is byte-identical after it

#### Scenario: Second open keeps the user's edits

- **WHEN** `analysis.marimo.py` already exists
- **THEN** the server opens it without changing it and the response says `existing`

#### Scenario: No analysis script

- **WHEN** the folder has no `analysis.py`
- **THEN** the server creates `analysis.marimo.py` from the packaged empty notebook and the response says `created`

#### Scenario: Conversion tool is missing

- **WHEN** the editor's conversion fails because jupytext is not in marimo's tool environment
- **THEN** the server refuses with 409 reason `converter_missing` and a message that says to install marimo with jupytext from the marimo card on the Integrations page, and names the copy command for a terminal
- **AND** the page shows a link to the marimo card
- **AND** no file is left in the experiment folder

#### Scenario: The notebook is a link

- **WHEN** `analysis.marimo.py` is a symbolic link or not a regular file
- **THEN** the server refuses with 409 reason `notebook_not_regular` and starts no process

### Requirement: The Library notebook kernel runs in the project environment

The notebook kernel SHALL run in the project's `<project root>/.venv` with the user's full file and network access, so that experiment code can import the project's packages. The server SHALL keep the registered editor executable as the editor server and SHALL install nothing into the project environment. It SHALL NOT load the project's `.env` into the kernel on its own. When the project has no usable `.venv`, or when the project environment has no marimo and its Python major and minor version differs from the editor's, the server SHALL refuse with a message that says what to do. The response SHALL list packages that the editor's environment shadows with a different version.

#### Scenario: Experiment code imports a project package

- **WHEN** the kernel of a Library notebook runs `import omrs` in this repository
- **THEN** the import succeeds from the project environment

#### Scenario: Project without a virtual environment

- **WHEN** the project folder has no `.venv`
- **THEN** the server refuses with 409 reason `no_project_environment` and a message that names `uv sync`

#### Scenario: Python versions differ

- **WHEN** the project `.venv` uses Python 3.12, has no marimo, and marimo runs on Python 3.14
- **THEN** the server refuses with 409 reason `python_mismatch` and names both versions

#### Scenario: Project environment unchanged

- **WHEN** a Library notebook opens and is stopped
- **THEN** the set of installed distributions in the project `.venv` is the same as before

### Requirement: Opening a Library notebook runs no cell

No cell SHALL run when a Library notebook opens. The server SHALL refuse to launch when the nearest `pyproject.toml` above the notebook turns startup execution on, or cannot be parsed.

#### Scenario: Project turns on startup execution

- **WHEN** the project's `pyproject.toml` sets `[tool.marimo.runtime] auto_instantiate = true`
- **THEN** the server refuses with 409 reason `project_config_runs_on_open` and starts no process

#### Scenario: Normal open

- **WHEN** a converted notebook opens in the editor
- **THEN** no cell has run until the user runs one

### Requirement: The experiment page shows the editor state

The experiment page SHALL disable "Open in marimo" with a hint that links to the Code editor section when no launchable marimo is registered. Before each launch it SHALL show a consent dialog that says the notebook runs in the project's environment with the user's full file and network access, and that names the files the open adds to the folder. While the launch runs it SHALL show a busy state. After a launch it SHALL show the editor address, the one-time token, a link to open the tab again, the notebook state and a Stop action. After a reload it SHALL show a running editor for the experiment with Stop and without the token. A refused launch SHALL show one plain line and one action. The page SHALL work at 1280 px and 390 px wide.

#### Scenario: marimo not registered

- **WHEN** the plugin list has no launchable marimo
- **THEN** the button is disabled and the hint links to the Code editor section

#### Scenario: Consent is not remembered

- **WHEN** the user opens marimo, stops it, and opens it again
- **THEN** the consent dialog shows again with its checkbox cleared

#### Scenario: Editor already running

- **WHEN** an editor for this experiment runs and the user reloads the page
- **THEN** the page shows the running editor with Stop and no token

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
