# Spec Delta

## ADDED Requirements

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
