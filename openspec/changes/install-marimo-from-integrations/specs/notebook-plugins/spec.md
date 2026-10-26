## MODIFIED Requirements

### Requirement: Notebook integration is separately managed
Notebook editors SHALL be optional external-tool plugins with versioned manifests and explicitly registered executables. Their installation and updates SHALL remain outside OMRS's dependency environment: an editor SHALL never enter the OMRS environment or lock file. The workspace SHALL NOT install or update an editor on its own. It MAY install marimo into marimo's own `uv tool` environment when the user presses Install on the marimo card of the Integrations page, with the fixed requirement that the shipped marimo manifest qualifies. An install SHALL NOT register the editor.

#### Scenario: marimo is absent
- **WHEN** the user opens Experiments without a registered marimo installation
- **THEN** the workspace SHALL say that marimo can be installed from the marimo card on the Integrations page, with a link to that card, and how to register it
- **AND** ordinary OMRS functions SHALL remain available

#### Scenario: Editor is updated independently
- **WHEN** the operator updates the external editor and requests a compatibility recheck
- **THEN** the host SHALL probe the updated executable without changing OMRS's dependency lock

#### Scenario: Install does not register
- **WHEN** an install of marimo from the Integrations page succeeds and no marimo registration exists
- **THEN** `GET /v1/plugins` SHALL still list no plugin
- **AND** it SHALL give the installed executable path, so that the registration form can fill it in

## ADDED Requirements

### Requirement: Registration accepts the executable that the marimo card found
Registration SHALL accept, in addition to the executables already approved, the exact absolute executable path that the server found for the marimo `uv tool` environment, also when its folder is not on the server's `PATH`. It SHALL accept no other path in that folder. `GET /v1/plugins` SHALL give that path for the marimo plugin, or nothing when marimo is not installed. The registration form SHALL fill in the shipped manifest path and this executable path until the user types. The user SHALL still tick the approval box. After a successful registration, the page SHALL run the compatibility check once.

#### Scenario: Login item without the tool folder on PATH
- **WHEN** the server's `PATH` does not hold `~/.local/bin`, the marimo card found `~/.local/bin/marimo`, and the user registers that path with approval
- **THEN** the registration SHALL succeed

#### Scenario: Another executable in the same folder
- **WHEN** the user registers another file in the folder of the found marimo executable, and that folder is not on the server's `PATH`
- **THEN** the server SHALL refuse with 403 and record nothing

#### Scenario: Register and check
- **WHEN** the user ticks approval and registers the filled-in paths
- **THEN** the page SHALL call the registration route and then the recheck route once, and show the checked state

### Requirement: No marimo editor opens while marimo is installed or removed
While an install or uninstall of marimo from the Integrations page runs, the server SHALL refuse to open a marimo editor, from the Code editor and from the Library, with 409 and the reason `tool_install_running`. The refusal SHALL start no process and issue no credential.

#### Scenario: Open during an install
- **WHEN** a marimo install runs and the user opens a notebook in the Code editor
- **THEN** the server SHALL answer 409 `tool_install_running` and start no process

#### Scenario: Library open during an uninstall
- **WHEN** a marimo uninstall runs and the user selects Open in marimo in the Library
- **THEN** the server SHALL answer 409 `tool_install_running` and the page SHALL say to wait until the marimo job ends
