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

The status of each entry SHALL come from `GET /v1/integrations`, resolved through the runtime probes the server already owns (PDF reader and sparse backend resolution, vector-store and community registries, import checks for the optional providers). The page SHALL state that availability reflects the running launch.

#### Scenario: Installed versus absent

- **WHEN** the pdf-inspector backend is installed and the chroma extra is not
- **THEN** the pdf entries MUST show an available status and the chroma entry MUST show a not-installed status, each stated in text

#### Scenario: Server unreachable

- **WHEN** the integrations request fails
- **THEN** the page MUST show the friendly failure line with a Retry action

### Requirement: The page says how an installed extra becomes available

When the server can install, the page SHALL say that Install adds the packages and that a restart makes them available. When it cannot, the page SHALL say that installing requires running the command outside the app and restarting the server.

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

When an entry reports `installable: true`, the entry SHALL show an Install button. Pressing it SHALL open a confirm dialog that names the extra and the packages it adds, and says that the server needs a restart afterwards. Confirming SHALL call the install route. When `installable` is false, the entry SHALL show the copy command only.

#### Scenario: Install the Anthropic extra

- **WHEN** the user presses Install on the Anthropic entry and confirms
- **THEN** the page MUST call `POST /v1/integrations/anthropic/install`, show the progress line, and on success show "Installed, restart to use" with a Restart action

#### Scenario: Cancel the dialog

- **WHEN** the user presses Install and then Cancel
- **THEN** the page MUST NOT call the install route

#### Scenario: Not installable here

- **WHEN** the server runs from a development checkout
- **THEN** no entry MUST show an Install button, and each MUST show its copy command

### Requirement: An entry shows install progress and failure output

While the install runs, the entry SHALL show a progress line, and the other Install buttons SHALL be disabled. A failure SHALL show the last output lines and a Retry action.

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

An installed entry that is not a base entry and is not `web` SHALL show Uninstall when the server can uninstall. Uninstall SHALL open a dialog that lists the packages to remove and the packages kept because something else needs them, with Cancel and Uninstall. While the job runs, the card SHALL show progress; after success it SHALL show "Removed, restart to apply" with the restart action.

#### Scenario: Uninstall Chroma

- **WHEN** Chroma is installed and unused, and the user presses Uninstall, then Uninstall in the dialog
- **THEN** the dialog MUST have listed the Chroma packages, and the card MUST show "Removed, restart to apply"

#### Scenario: Base entry

- **WHEN** the user opens the Magika or pdf-inspector card
- **THEN** the card MUST NOT show Uninstall

### Requirement: The card shows why an extra stays and the lasting command

When the server refuses because a setting uses the extra, the card SHALL show the reason and the setting, and no Uninstall and no lasting command. When the extra is in the install receipt and no setting uses it, the card SHALL also show the lasting command without the extra.

#### Scenario: In use

- **WHEN** `vector_store` is `chroma`
- **THEN** the Chroma card MUST show that `vector_store` uses it, and MUST NOT show Uninstall or the lasting command

#### Scenario: Extra in the receipt

- **WHEN** the live install is `omrs[web,hybrid]` and the user views the Hybrid search card
- **THEN** the card MUST show Uninstall and the lasting command `uv tool install --reinstall "omrs[web] @ <source>"`

### Requirement: The card takes its restart state from the entry

The card SHALL take its restart state from the entry's `pending_restart`, never from the last job alone.

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

### Requirement: The Integrations page has a marimo card


The Integrations page SHALL show a marimo card in an "External tools" group, below the extras. The card SHALL use the same layout as an extra's card: name, one-line purpose, a status badge with text, and the actions. Its state SHALL come from `GET /v1/integrations`, which SHALL list marimo in a `tools` list, apart from the extras.

#### Scenario: Not installed shows in red

- **WHEN** an extra or the marimo tool is not installed
- **THEN** its card MUST show the "Not installed" badge in the error (red) colour, as the "Installed" badge shows in green

#### Scenario: Phone width

- **WHEN** the page is 390 px wide
- **THEN** the marimo card, its executable path, its progress line and its output lines MUST fit without sideways page scroll

### Requirement: The marimo card shows one of five states

The state SHALL be one of:

- `ready`: a `uv tool` environment named `marimo` holds a marimo version inside the range of the shipped marimo manifest, and jupytext.
- `needs-jupytext`: marimo is in range, and jupytext is missing.
- `outside-range`: the marimo version is outside the range.
- `not-installed`: no `uv tool` environment named `marimo` exists.
- `unknown`: the server could not find `uv`, or could not read the tool environment.

#### Scenario: marimo is not installed

- **WHEN** no `uv tool` environment named `marimo` exists and `uv` is found
- **THEN** the marimo card MUST show "Not installed", the copy command and an Install button

#### Scenario: marimo without jupytext

- **WHEN** the marimo tool environment holds marimo 0.25.1 and no jupytext
- **THEN** the card MUST show that jupytext is missing and that the Library cannot convert `analysis.py` without it, and MUST show an Install button

#### Scenario: uv is not found

- **WHEN** the server finds no `uv` program
- **THEN** the card MUST show the state `unknown`, the copy command, and no Install or Uninstall button

### Requirement: The marimo card shows its version, path and copy command

The card SHALL show the installed marimo version and the absolute executable path when it knows them. It SHALL show the copy command `uv tool install "marimo>=<minimum>,<<below>" --with jupytext`, with the range of the shipped manifest. The state SHALL NOT depend on the server's own install type, because marimo does not go into the server's environment.

#### Scenario: marimo is ready

- **WHEN** the marimo tool environment holds marimo 0.25.1 and jupytext
- **THEN** the card MUST show "Installed", the version 0.25.1 and the executable path, and MUST NOT show an Install button

### Requirement: marimo can be installed from its card

When the marimo card reports `installable: true`, Install SHALL open a confirm dialog that names the command, says that marimo goes into its own tool environment outside OMRS, and says that no restart is needed. Confirming SHALL call `POST /v1/integrations/tools/marimo/install`. The route SHALL need the browser session with the `manage` scope.

#### Scenario: Install marimo

- **WHEN** marimo is not installed and the user presses Install and confirms
- **THEN** the page MUST call `POST /v1/integrations/tools/marimo/install`, show the progress line, and on success show "Installed" with a link to Experiments, Code editor

### Requirement: The marimo install runs a fixed command in the shared install job

The server SHALL run `uv tool install "marimo>=<minimum>,<<below>" --with jupytext` as an argument list with no shell, built only from the shipped manifest range. It SHALL use the one install job of the server: one job at a time, a 600 s limit, no `*_API_KEY` variable in the process environment, and the last 40 redacted output lines.

#### Scenario: Fixed command

- **WHEN** the install starts
- **THEN** the process argument list MUST be `<uv> tool install marimo>=0.25.1,<0.26.0 --with jupytext` with no shell, and no request text in it

#### Scenario: One job at a time

- **WHEN** an install of the `chroma` extra runs and the marimo install route is called
- **THEN** the server MUST answer 409 `install-running`, and every Install and Uninstall button on the page MUST be disabled

### Requirement: The marimo install succeeds only when the tool is ready

After exit code 0, the server SHALL read the tool environment again and SHALL report success only when the state is `ready`. Otherwise the job SHALL fail with `check-failed`.

#### Scenario: The install leaves marimo unusable

- **WHEN** `uv` exits with code 0 but the tool environment then has no jupytext
- **THEN** the job MUST end as failed with the reason `check-failed`, and the card MUST show the last output lines and a Retry action

### Requirement: The server refuses a marimo install it cannot run

The server SHALL refuse with 409 and a `reason`: `already-installed` when the state is `ready`, `status-unknown` when it is `unknown`, `uv-not-found` when no `uv` is found, `install-running` when another job runs, and `editor-running` when a marimo editor that OMRS started is running. A refusal SHALL start no process.

#### Scenario: An editor runs

- **WHEN** a marimo editor that OMRS started is running and the install route is called
- **THEN** the server MUST answer 409 `editor-running` and start no process

### Requirement: The card warns before it replaces an existing marimo

When the state is `outside-range` or `needs-jupytext`, the card SHALL show a red caution before Install that names the installed version and says that Install replaces the existing marimo tool environment.

#### Scenario: Replace a marimo outside the range

- **WHEN** the tool environment holds marimo 0.27.0
- **THEN** the card MUST show a caution that names 0.27.0 and says that Install replaces it, before the Install button

### Requirement: marimo can be uninstalled from its card when the card installed it

The marimo card SHALL show Uninstall only when the tool environment's `uv` receipt holds exactly the requirements the card installs: marimo with the shipped manifest range, and jupytext. Uninstall SHALL open a dialog that says the whole marimo tool environment goes, and that a marimo registration in Code editor then shows as unavailable.

#### Scenario: A marimo the user installed

- **WHEN** the receipt holds only `marimo` with no version range
- **THEN** the card MUST NOT show Uninstall, and MUST show the command `uv tool uninstall marimo`

### Requirement: The marimo uninstall removes the tool environment

Confirming SHALL call `POST /v1/integrations/tools/marimo/uninstall`, which SHALL need the `manage` scope and SHALL run `uv tool uninstall marimo` through the same job and limits. After exit code 0 the server SHALL report success only when the tool environment is gone.

#### Scenario: Uninstall the marimo the card installed

- **WHEN** the receipt holds `marimo>=0.25.1,<0.26.0` and jupytext, no editor runs, and the user presses Uninstall and confirms
- **THEN** the page MUST call `POST /v1/integrations/tools/marimo/uninstall`, and on success the card MUST show "Not installed"

### Requirement: The server refuses a marimo uninstall it cannot run

The server SHALL refuse with 409 and a `reason`: `not-installed` when no marimo tool environment exists, `not-installed-by-app` when the receipt holds other requirements, `status-unknown`, `uv-not-found`, `install-running` and `editor-running`. For `not-installed-by-app` the card SHALL show the copy command `uv tool uninstall marimo` and no Uninstall button.

#### Scenario: Uninstall while an editor runs

- **WHEN** a marimo editor that OMRS started is running
- **THEN** the uninstall route MUST answer 409 `editor-running` and start no process
