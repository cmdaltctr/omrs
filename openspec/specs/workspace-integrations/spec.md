# workspace-integrations Specification

## Purpose
An Integrations page listing the installable integration extras with live availability and copy-ready install commands, so the optional capabilities of the engine are visible and reachable from the workspace.

## Requirements

### Requirement: The Integrations page lists every installable integration

The Integrations view SHALL list one entry for each installable pip extra the project declares (chroma, hybrid, pdf-pypdfium2, pdf-inspector, community-leiden, azure, llamacpp, openrouter, torch, web) and for the always-on magika integration. Each entry SHALL show its name, a one-line purpose, its availability status as text with a badge, and its install command.

#### Scenario: Full catalogue

- **WHEN** the user opens Integrations
- **THEN** every declared extra and magika MUST be listed with a name, purpose, status and install command

An entry that every install includes SHALL show a second badge "Base default" next to its status and SHALL offer no Install and no install command, so a user does not install it again. Such an entry has no extra (magika), or an extra whose requirements are all base requirements, kept so an old `--extra` command still works (pdf-inspector, llamacpp, openrouter).

#### Scenario: Base install entry

- **WHEN** the user opens Integrations
- **THEN** the magika, pdf-inspector, llamacpp and openrouter cards MUST show "Base default" next to their status with no Install and no command, and no other card MUST show it

### Requirement: Availability comes from the running server

The status of each entry SHALL come from `GET /v1/integrations`, resolved through the runtime probes the server already owns (PDF reader and sparse backend resolution, vector-store and community registries, import checks for the optional providers). The page SHALL state that availability reflects the running launch. When the server can install, the page SHALL say that Install adds the packages and that a restart makes them available. When it cannot, the page SHALL say that installing requires running the command outside the app and restarting the server.

#### Scenario: Installed versus absent

- **WHEN** the pdf-inspector backend is installed and the chroma extra is not
- **THEN** the pdf entries MUST show an available status and the chroma entry MUST show a not-installed status, each stated in text

#### Scenario: Server unreachable

- **WHEN** the integrations request fails
- **THEN** the page MUST show the friendly failure line with a Retry action

#### Scenario: Installed, restart needed

- **WHEN** an install of `anthropic` succeeded in this launch
- **THEN** the `anthropic` entry MUST show the status "Installed, restart to use" and a Restart action

### Requirement: Install commands copy from the page

Each entry's install command SHALL be copyable with one action. The command SHALL match how the server is installed: `uv tool install --reinstall "omrs[<extras>] @ <source>"` for a `uv tool` install, with the current extras plus the entry's extra and the source from the install receipt; `uv sync --extra <extra>` for a development checkout; and `pip install "omrs[<extra>]"` otherwise. For a `uv tool` install, the page SHALL say that this command keeps the extra after a later reinstall.

#### Scenario: Copy the command

- **WHEN** the server runs from a checkout and the user copies the azure entry's install command
- **THEN** the clipboard MUST hold `uv sync --extra azure`

#### Scenario: Copy the command for a uv tool install

- **WHEN** the receipt lists the extras `web` and `hybrid` and the source folder `~/src/omrs`, and the user copies the anthropic entry's command
- **THEN** the clipboard MUST hold `uv tool install --reinstall "omrs[web,hybrid,anthropic] @ ~/src/omrs"`

### Requirement: An entry can be installed from the page

When an entry reports `installable: true`, the entry SHALL show an Install button. Pressing it SHALL open a confirm dialog that names the extra and the packages it adds, and says that the server needs a restart afterwards. Confirming SHALL call the install route. While the install runs, the entry SHALL show a progress line, and the other Install buttons SHALL be disabled. A failure SHALL show the last output lines and a Retry action. When `installable` is false, the entry SHALL show the copy command only.

#### Scenario: Install the Anthropic extra

- **WHEN** the user presses Install on the Anthropic entry and confirms
- **THEN** the page MUST call `POST /v1/integrations/anthropic/install`, show the progress line, and on success show "Installed, restart to use" with a Restart action

#### Scenario: Cancel the dialog

- **WHEN** the user presses Install and then Cancel
- **THEN** the page MUST NOT call the install route

#### Scenario: Not installable here

- **WHEN** the server runs from a development checkout
- **THEN** no entry MUST show an Install button, and each MUST show its copy command

#### Scenario: Phone width

- **WHEN** the page is 390 px wide
- **THEN** the Install button, the progress line and the output lines MUST fit without sideways page scroll

### Requirement: A card warns before an install that changes other packages

An entry MAY carry an `install_caution` line. While the entry is `not-installed` or `unknown`, the card SHALL show that line in a red callout above the Install button and the copy command. The card SHALL NOT show the callout once the entry is `available` or waits for a restart.

#### Scenario: Anthropic caution

- **WHEN** the Anthropic entry is not installed and carries a caution about `python-dateutil`
- **THEN** the card MUST show the caution in a red callout before the Install button

#### Scenario: Installed entry

- **WHEN** the Anthropic entry is `available`
- **THEN** the card MUST NOT show the caution

#### Scenario: PyTorch size caution

- **WHEN** the PyTorch entry is not installed
- **THEN** the card MUST show a caution that gives the download size and says that search uses PyTorch only when `retrieval.rerank_backend` is `torch`

### Requirement: An installed entry can be uninstalled from the page

An installed entry that is not a base entry and is not `web` SHALL show Uninstall when the server can uninstall. Uninstall SHALL open a dialog that lists the packages to remove and the packages kept because something else needs them, with Cancel and Uninstall. While the job runs, the card SHALL show progress; after success it SHALL show "Removed, restart to apply" with the restart action. When the server refuses because a setting uses the extra, the card SHALL show the reason and the setting, and no Uninstall and no lasting command. When the extra is in the install receipt and no setting uses it, the card SHALL also show the lasting command without the extra. The card SHALL take its restart state from the entry's `pending_restart`, never from the last job alone.

#### Scenario: Uninstall Chroma

- **WHEN** Chroma is installed and unused, and the user presses Uninstall, then Uninstall in the dialog
- **THEN** the dialog MUST have listed the Chroma packages, and the card MUST show "Removed, restart to apply"

#### Scenario: In use

- **WHEN** `vector_store` is `chroma`
- **THEN** the Chroma card MUST show that `vector_store` uses it, and MUST NOT show Uninstall or the lasting command

#### Scenario: Base entry

- **WHEN** the user opens the Magika or pdf-inspector card
- **THEN** the card MUST NOT show Uninstall

#### Scenario: Extra in the receipt

- **WHEN** the live install is `omrs[web,hybrid]` and the user views the Hybrid search card
- **THEN** the card MUST show Uninstall and the lasting command `uv tool install --reinstall "omrs[web] @ <source>"`

#### Scenario: Removed stays removed after another job

- **WHEN** Chroma was uninstalled in this launch and an install of Azure then succeeded
- **THEN** the Chroma card MUST still show "Removed, restart to apply", and the Azure card MUST show "Installed, restart to use"

### Requirement: The card names the profile that uses an extra

When the server refuses an uninstall because a saved user profile uses the extra, the card SHALL name the profile and the setting inside it, SHALL link to that profile in Studio, and SHALL show no Uninstall button and no lasting command.

#### Scenario: A profile uses pypdfium2

- **WHEN** the entry reports `in-use` with the setting `pdf_reader` and the profile "Scans"
- **THEN** the PDF reader: pypdfium2 card MUST say that the profile "Scans" uses this extra through `pdf_reader`, MUST link to `#/studio/<profile id>`, and MUST NOT show Uninstall or the lasting command

#### Scenario: A refused uninstall names the profile

- **WHEN** the uninstall request answers 409 `in-use` with a `profile`
- **THEN** the card MUST show a line that names that profile
