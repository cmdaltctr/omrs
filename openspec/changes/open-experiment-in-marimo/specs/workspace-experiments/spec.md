## MODIFIED Requirements

### Requirement: Marimo loads through plugin approval

The Experiments view SHALL have a Code editor section that keeps the notebook tool registration, trust notice, one-time credentials and editor launch panels. Opening a notebook editor for an experiment workspace SHALL launch the registered marimo tool, and stopping it SHALL end the launch. The registration form SHALL fill in the manifest path that the installed application ships. The running editors list SHALL also show editors that the Library opened, with their project and experiment folder, and SHALL stop them the same way.

#### Scenario: Open the marimo editor

- **WHEN** marimo is registered and the user opens the editor for an experiment workspace
- **THEN** an editor launch MUST start and its status MUST be shown with a stop action

#### Scenario: Register from an installed application

- **WHEN** the user opens the registration form in an installed application
- **THEN** the manifest path field holds the shipped manifest path

#### Scenario: Library editor in the list

- **WHEN** the Library opened an editor for an experiment
- **THEN** the running editors list shows it with its project and folder
- **AND** Stop ends that launch
