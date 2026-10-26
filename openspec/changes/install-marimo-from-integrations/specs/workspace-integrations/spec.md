## ADDED Requirements

### Requirement: The Integrations page has a marimo card

The Integrations page SHALL show a marimo card in an "External tools" group, below the extras. The card SHALL use the same layout as an extra's card: name, one-line purpose, a status badge with text, and the actions. Its state SHALL come from `GET /v1/integrations`, which SHALL list marimo in a `tools` list, apart from the extras. The state SHALL be one of:

- `ready`: a `uv tool` environment named `marimo` holds a marimo version inside the range of the shipped marimo manifest, and jupytext.
- `needs-jupytext`: marimo is in range, and jupytext is missing.
- `outside-range`: the marimo version is outside the range.
- `not-installed`: no `uv tool` environment named `marimo` exists.
- `unknown`: the server could not find `uv`, or could not read the tool environment.

The card SHALL show the installed marimo version and the absolute executable path when it knows them. It SHALL show the copy command `uv tool install "marimo>=<minimum>,<<below>" --with jupytext`, with the range of the shipped manifest. The state SHALL NOT depend on the server's own install type, because marimo does not go into the server's environment.

#### Scenario: marimo is not installed

- **WHEN** no `uv tool` environment named `marimo` exists and `uv` is found
- **THEN** the marimo card MUST show "Not installed", the copy command and an Install button

#### Scenario: Not installed shows in red

- **WHEN** an extra or the marimo tool is not installed
- **THEN** its card MUST show the "Not installed" badge in the error (red) colour, as the "Installed" badge shows in green

#### Scenario: marimo without jupytext

- **WHEN** the marimo tool environment holds marimo 0.25.1 and no jupytext
- **THEN** the card MUST show that jupytext is missing and that the Library cannot convert `analysis.py` without it, and MUST show an Install button

#### Scenario: marimo is ready

- **WHEN** the marimo tool environment holds marimo 0.25.1 and jupytext
- **THEN** the card MUST show "Installed", the version 0.25.1 and the executable path, and MUST NOT show an Install button

#### Scenario: uv is not found

- **WHEN** the server finds no `uv` program
- **THEN** the card MUST show the state `unknown`, the copy command, and no Install or Uninstall button

#### Scenario: Phone width

- **WHEN** the page is 390 px wide
- **THEN** the marimo card, its executable path, its progress line and its output lines MUST fit without sideways page scroll

### Requirement: marimo can be installed from its card

When the marimo card reports `installable: true`, Install SHALL open a confirm dialog that names the command, says that marimo goes into its own tool environment outside OMRS, and says that no restart is needed. Confirming SHALL call `POST /v1/integrations/tools/marimo/install`. The route SHALL need the browser session with the `manage` scope. The server SHALL run `uv tool install "marimo>=<minimum>,<<below>" --with jupytext` as an argument list with no shell, built only from the shipped manifest range. It SHALL use the one install job of the server: one job at a time, a 600 s limit, no `*_API_KEY` variable in the process environment, and the last 40 redacted output lines. After exit code 0, the server SHALL read the tool environment again and SHALL report success only when the state is `ready`. Otherwise the job SHALL fail with `check-failed`.

The server SHALL refuse with 409 and a `reason`: `already-installed` when the state is `ready`, `status-unknown` when it is `unknown`, `uv-not-found` when no `uv` is found, `install-running` when another job runs, and `editor-running` when a marimo editor that OMRS started is running. A refusal SHALL start no process.

When the state is `outside-range` or `needs-jupytext`, the card SHALL show a red caution before Install that names the installed version and says that Install replaces the existing marimo tool environment.

#### Scenario: Install marimo

- **WHEN** marimo is not installed and the user presses Install and confirms
- **THEN** the page MUST call `POST /v1/integrations/tools/marimo/install`, show the progress line, and on success show "Installed" with a link to Experiments, Code editor

#### Scenario: Fixed command

- **WHEN** the install starts
- **THEN** the process argument list MUST be `<uv> tool install marimo>=0.25.1,<0.26.0 --with jupytext` with no shell, and no request text in it

#### Scenario: Replace a marimo outside the range

- **WHEN** the tool environment holds marimo 0.27.0
- **THEN** the card MUST show a caution that names 0.27.0 and says that Install replaces it, before the Install button

#### Scenario: An editor runs

- **WHEN** a marimo editor that OMRS started is running and the install route is called
- **THEN** the server MUST answer 409 `editor-running` and start no process

#### Scenario: One job at a time

- **WHEN** an install of the `chroma` extra runs and the marimo install route is called
- **THEN** the server MUST answer 409 `install-running`, and every Install and Uninstall button on the page MUST be disabled

#### Scenario: The install leaves marimo unusable

- **WHEN** `uv` exits with code 0 but the tool environment then has no jupytext
- **THEN** the job MUST end as failed with the reason `check-failed`, and the card MUST show the last output lines and a Retry action

### Requirement: marimo can be uninstalled from its card when the card installed it

The marimo card SHALL show Uninstall only when the tool environment's `uv` receipt holds exactly the requirements the card installs: marimo with the shipped manifest range, and jupytext. Uninstall SHALL open a dialog that says the whole marimo tool environment goes, and that a marimo registration in Code editor then shows as unavailable. Confirming SHALL call `POST /v1/integrations/tools/marimo/uninstall`, which SHALL need the `manage` scope and SHALL run `uv tool uninstall marimo` through the same job and limits. After exit code 0 the server SHALL report success only when the tool environment is gone.

The server SHALL refuse with 409 and a `reason`: `not-installed` when no marimo tool environment exists, `not-installed-by-app` when the receipt holds other requirements, `status-unknown`, `uv-not-found`, `install-running` and `editor-running`. For `not-installed-by-app` the card SHALL show the copy command `uv tool uninstall marimo` and no Uninstall button.

#### Scenario: Uninstall the marimo the card installed

- **WHEN** the receipt holds `marimo>=0.25.1,<0.26.0` and jupytext, no editor runs, and the user presses Uninstall and confirms
- **THEN** the page MUST call `POST /v1/integrations/tools/marimo/uninstall`, and on success the card MUST show "Not installed"

#### Scenario: A marimo the user installed

- **WHEN** the receipt holds only `marimo` with no version range
- **THEN** the card MUST NOT show Uninstall, and MUST show the command `uv tool uninstall marimo`

#### Scenario: Uninstall while an editor runs

- **WHEN** a marimo editor that OMRS started is running
- **THEN** the uninstall route MUST answer 409 `editor-running` and start no process
