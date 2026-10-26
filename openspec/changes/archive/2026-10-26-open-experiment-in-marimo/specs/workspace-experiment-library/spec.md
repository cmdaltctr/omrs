## ADDED Requirements

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
- **THEN** the server refuses with 409 reason `converter_missing` and a message that names the install command to run outside OMRS
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
