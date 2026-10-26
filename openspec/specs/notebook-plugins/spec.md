# notebook-plugins Specification

## Purpose
Connect independently managed local notebook editors to OMRS without adding their runtime dependencies or release cycle to the base application.

## Requirements

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

### Requirement: Plugin manifests are constrained data
A plugin manifest SHALL declare its identity, schema/version, capabilities, executable reference, tested compatibility range, and supported structured launch/probe arguments. When a manifest declares a structured conversion recipe, the recipe's only substitutions SHALL be a source path and an output path that the host sets. Registration and enabling SHALL require explicit trust. Manifests SHALL not supply shell strings, Python hooks, credentials, or installation commands.

#### Scenario: Manifest attempts executable hooks
- **WHEN** a manifest requests a shell command, dynamic Python import, unsupported substitution, or installer action
- **THEN** registration SHALL reject it without launching a process

#### Scenario: Manifest is approved
- **WHEN** the operator approves a valid manifest and executable
- **THEN** the registration SHALL retain their identity and approval
- **AND** a changed manifest or executable reference SHALL require revalidation and approval

#### Scenario: Conversion recipe uses a launch substitution
- **WHEN** a manifest's conversion recipe uses a substitution other than the source path and the output path
- **THEN** registration SHALL reject the manifest

### Requirement: Compatibility is checked before launch
The host SHALL probe tool version and required launch capabilities before starting an editor. Unsupported versions or missing capabilities SHALL remain disabled with an actionable message. It SHALL not silently replace or upgrade an incompatible executable.

#### Scenario: Editor loses a required capability
- **WHEN** a probe cannot confirm loopback binding, authentication, or safe startup controls
- **THEN** launch SHALL be refused
- **AND** the message SHALL identify the required capability

#### Scenario: Independently updated version is supported
- **WHEN** the updated editor passes the manifest's compatibility checks
- **THEN** the same OMRS installation SHALL be able to launch it

### Requirement: Editor lifecycle is explicit and locally protected
The initial plugin SHALL launch an editable local notebook interface only after user consent. It SHALL bind to loopback, retain authentication, disable startup cell execution and automatic package/update behaviour, and expose explicit start/stop states. The host SHALL own only processes it starts.

#### Scenario: Notebook is opened
- **WHEN** a user approves launching a trusted notebook
- **THEN** its editable interface SHALL open in a separate local browser tab
- **AND** the notebook SHALL not execute its cells automatically on startup

#### Scenario: An unrelated editor owns the port
- **WHEN** a requested port is occupied by an unrelated process
- **THEN** the host SHALL choose another permitted port or fail clearly
- **AND** it SHALL not adopt or terminate that process

#### Scenario: Stop is approved
- **WHEN** the user approves Stop or the agreed application shutdown begins
- **THEN** the host SHALL stop its owned editor processes with graceful termination and bounded escalation
- **AND** notebook files SHALL remain intact

### Requirement: Notebook runs share the graph contract
A starter notebook SHALL submit explicit graph revisions through the same protected graph API and record the effective settings, backend/index identities, inputs, and output references. Long evaluations SHALL use explicit execution controls and checkpoints. Notebook reactivity SHALL not authorise repeated expensive runs by itself.

#### Scenario: A parameter cell changes
- **WHEN** a notebook parameter changes without an explicit run request
- **THEN** no new graph evaluation SHALL be admitted

#### Scenario: Canvas and notebook select the same revision
- **WHEN** both submit the same graph revision and valid inputs
- **THEN** both SHALL use the same core validation and operations
- **AND** each run SHALL record its own resource/index snapshot

### Requirement: Experiment writes stay in approved experiment workspaces
Notebook credentials SHALL identify an approved experiment workspace and permitted actions. Ingestion experiments SHALL use separate experiment-local stores and record their identities. The initial default SHALL be LanceDB unless store choice is a declared experiment factor. The editor's ordinary filesystem permissions SHALL be disclosed.

#### Scenario: Notebook targets the live library
- **WHEN** an experiment credential requests any run or read against the ordinary library context, ingestion included
- **THEN** the server SHALL refuse the request before any graph work or mutation
- **AND** read-only live-library requests SHALL be refused the same way as mutating ones

#### Scenario: An approved ingestion experiment runs
- **WHEN** the operator registers an experiment workspace and explicitly starts its graph
- **THEN** its index and outputs SHALL remain below that approved experiment workspace
- **AND** its backend, index identity, graph revision, and measured outputs SHALL be recorded

#### Scenario: Trust warning is displayed
- **WHEN** an editor is registered or opened
- **THEN** the workspace SHALL explain that trusted notebook Python has the user's filesystem/network permissions
- **AND** it SHALL not claim that a dependency environment provides operating-system containment

### Requirement: The shipped manifest is found in an installed application

The marimo manifest SHALL ship inside the `omrs` package as package data and SHALL be found through the package resources, both in a source checkout and in an installed wheel. It SHALL stay data only. The plugin list SHALL name the path of each shipped manifest. The starter notebook and the plugin README SHALL stay outside the wheel.

#### Scenario: Installed wheel

- **WHEN** the application runs from a built wheel
- **THEN** the shipped manifest path exists, parses as a valid manifest and is an approved manifest for registration

#### Scenario: Wheel contents

- **WHEN** the wheel is built
- **THEN** it holds the marimo manifest below the `omrs` package
- **AND** it holds no file from the top-level `plugins/` folder

### Requirement: An editor launch can use a project environment

An editor launch SHALL be able to run its notebook kernel in a given project virtual environment when the manifest declares the `project_environment` capability. The host SHALL supply the environment path in the private launch configuration, SHALL keep the registered executable and the manifest launch arguments unchanged, and SHALL mark the environment as not writable. A launch that asks for a project environment SHALL be refused when the manifest does not declare the capability.

#### Scenario: Launch configuration

- **WHEN** the host launches an editor with a project environment
- **THEN** the private launch configuration names the absolute environment path, marks it not writable and turns off automatic `.env` loading
- **AND** the argv is the registered executable followed by the manifest launch arguments

#### Scenario: Manifest without the capability

- **WHEN** a launch asks for a project environment and the manifest does not declare `project_environment`
- **THEN** the launch is refused and no process starts

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
