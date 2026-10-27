# workspace-experiments Specification

## Purpose
Experiments as the research area: the Library and Notebooks sections for research experiments, named sandbox folders holding experiment contexts, marimo notebook loading through plugin approval in the Code editor section, and the pipeline runs list.

## Requirements

### Requirement: Experiment contexts group under named folders

The Experiments view SHALL have a Sandboxes section that groups experiment contexts under their parent directories below the approved experiment roots, showing named main folders that each list their sub-experiments. A main folder with no contexts SHALL still be listed. When no root is approved, the section SHALL say so and name the `--experiment-root` server flag.

#### Scenario: Grouped listing

- **WHEN** two contexts exist under `reranker-calibration` and one under `input-quality`
- **THEN** the view MUST show both folders with their contexts listed beneath them

#### Scenario: Empty folder

- **WHEN** a main folder exists on disk with no registered context
- **THEN** the folder MUST appear with an empty indication

### Requirement: Folders are created from the view

The user SHALL create a main folder by name, which creates a directory below an approved experiment root through a session-scoped endpoint, and SHALL create a sub-experiment inside a folder by registering an experiment context in that directory with its declared factors. Path validation SHALL reject relative escapes and paths outside approved roots.

#### Scenario: Create a main folder

- **WHEN** the user creates a folder named `hybrid-search` under the approved root
- **THEN** the directory MUST be created and the folder MUST appear in the listing

#### Scenario: Create a sub-experiment

- **WHEN** the user registers an experiment named `run-1` inside `hybrid-search`
- **THEN** a context MUST be approved for that workspace and listed under the folder with its factors

#### Scenario: Rejected path

- **WHEN** a folder name containing path traversal is submitted
- **THEN** the request MUST fail with a validation error and no directory MUST be created

### Requirement: Marimo loads through plugin approval

The Experiments view SHALL have a Code editor section that keeps the notebook tool registration, trust notice, one-time credentials and editor launch panels. Opening a notebook editor for an experiment workspace SHALL launch the registered marimo tool, and stopping it SHALL end the launch.

#### Scenario: Open the marimo editor

- **WHEN** marimo is registered and the user opens the editor for an experiment workspace
- **THEN** an editor launch MUST start and its status MUST be shown with a stop action

### Requirement: The registration form fills in the shipped manifest path

The registration form SHALL fill in the manifest path that the installed application ships.

#### Scenario: Register from an installed application

- **WHEN** the user opens the registration form in an installed application
- **THEN** the manifest path field holds the shipped manifest path

### Requirement: The running editors list includes Library editors

The running editors list SHALL also show editors that the Library opened, with their project and experiment folder, and SHALL stop them the same way.

#### Scenario: Library editor in the list

- **WHEN** the Library opened an editor for an experiment
- **THEN** the running editors list shows it with its project and folder
- **AND** Stop ends that launch

### Requirement: Pipeline runs live in Experiments

The Experiments view SHALL include the pipeline runs list with its status filter and refresh. Selecting a run SHALL open `#/experiments/runs/<run-id>`, showing its snapshot, node outcomes and evidence, following the `pipeline-canvas` and `pipeline-run-records` requirements.

#### Scenario: Runs are available

- **WHEN** the user opens the runs section of Experiments
- **THEN** the run list, status filter and run detail with snapshot, node outcomes and evidence MUST be available

#### Scenario: Run detail has its own address

- **WHEN** the user reloads the page at `#/experiments/runs/<run-id>`
- **THEN** the detail for that run MUST be shown

### Requirement: Experiments sections

The Experiments view SHALL offer the sections Library, Notebooks, Sandboxes, Code editor and Runs, and SHALL open on Library. The library experiment page SHALL have the address `#/experiments/library/<project-id>/<folder>`, and a notebook page SHALL have the address `#/experiments/notebooks/<notebook-id>`, so that a reload shows the same page.

#### Scenario: Default section

- **WHEN** the user opens `#/experiments`
- **THEN** the Library section is shown

#### Scenario: Reload an experiment page

- **WHEN** the user reloads `#/experiments/library/<project-id>/<folder>`
- **THEN** that experiment page is shown
