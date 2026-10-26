## MODIFIED Requirements

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
